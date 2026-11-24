# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Layouteditor (0.7.0): Vorlagenformat, Renderer, Briefpapier, Pipeline und echte Prüfung (fiktive Daten)."""

import copy
import io
import shutil
from pathlib import Path

import pdfplumber
import pikepdf
import pytest
import yaml
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from fakturafalter import (
    beispielrechnung,
    cii,
    layout,
    pdfa,
    pipeline,
    sicht,
    sicht_layout,
    validierung,
)
from fakturafalter.modell import Zahlung

BSP = Path(__file__).resolve().parent.parent / "beispiele"
BEISPIEL_YAML = BSP / "layout" / "layout-beispiel.yaml"
werkzeuge = validierung.verfuegbar()


def _beispiel_roh() -> dict:
    return yaml.safe_load(BEISPIEL_YAML.read_text(encoding="utf-8"))["layout"]


def _woerter(pdf: bytes, seite: int = 0):
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return d.pages[seite].extract_words()


def _text(pdf: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return [p.extract_text() or "" for p in d.pages]


def _im_rahmen(ws, e: layout.Element, woerter: set[str]) -> bool:
    treffer = [w for w in ws if w["text"] in woerter]
    return bool(treffer) and all(
        e.x * mm - 1 <= w["x0"]
        and w["x1"] <= (e.x + e.breite) * mm + 1
        and e.y * mm - 1 <= w["top"]
        and w["bottom"] <= (e.y + e.hoehe) * mm + 1
        for w in treffer
    )


def _bilder(pdf: bytes, seite: int = 0) -> int:
    """Gezeichnete Bilder (Do-Aufrufe auf Bild-XObjects) einer Seite."""
    with pikepdf.open(io.BytesIO(pdf)) as p:
        s = p.pages[seite]
        xo = s.obj.Resources.get("/XObject") or {}
        return sum(
            1
            for ops, op in pikepdf.parse_content_stream(s)
            if str(op) == "Do"
            and xo.get(str(ops[0])) is not None
            and xo[str(ops[0])].get("/Subtype") == "/Image"
        )


def _cmyk_briefpapier(p: Path) -> Path:
    c = canvas.Canvas(str(p), pagesize=A4)
    c.setFillColorCMYK(0.8, 0.1, 0, 0.2)
    c.rect(0, A4[1] - 30 * mm, A4[0], 30 * mm, stroke=0, fill=1)
    c.showPage()
    c.save()
    return p


def _schrift_briefpapier(p: Path) -> Path:
    """Briefpapier mit nicht eingebetteter Fremdschrift (ohne freien Ersatz)."""
    pdf = pikepdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.TrueType,
            BaseFont=pikepdf.Name("/Fantasie-Grotesk"),
            Encoding=pikepdf.Name.WinAnsiEncoding,
        )
    )
    pdf.add_blank_page(page_size=A4)
    seite = pdf.pages[0]
    seite.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
    seite.obj.Contents = pdf.make_stream(b"BT /F1 12 Tf 50 800 Td (Briefkopf) Tj ET")
    pdf.save(p)
    return p


# ---------------------------------------------------------------- Format
def test_standard_rundweg_yaml():
    v = layout.standard()
    assert layout.pruefen(v) == []
    d = v.als_dict()
    v2 = layout.aus_dict(yaml.safe_load(yaml.safe_dump(d, allow_unicode=True)))
    assert v2.als_dict() == d
    assert set(v2.seite1.bausteine) == set(layout.BAUSTEINE)
    assert "empfaenger" not in v2.folgeseite.bausteine  # nur auf Seite 1


def test_beispielvorlage_laden_speichern(tmp_path):
    v = layout.laden(_beispiel_roh(), BSP)
    assert v.logo == "layout/logo.png" and v.pfad(v.logo).exists()
    assert v.seite1.briefpapier.endswith(".pdf") and v.pfad(v.folgeseite.briefpapier).exists()
    assert [f.art for f in v.seite1.felder] == ["text", "bild"]
    assert layout.aus_dict(v.als_dict(), BSP).als_dict() == v.als_dict()


def test_leer_heisst_standardlayout_und_fehlende_bausteine_aus_dem_standard():
    assert layout.aus_dict(None) is None and layout.aus_dict({}) is None
    v = layout.aus_dict(
        {"seite1": {"bausteine": {"logo": {"x": 30, "y": 10, "breite": 40, "hoehe": 20}}}}
    )
    std = layout.standard()
    assert (v.seite1.bausteine["logo"].x, v.seite1.bausteine["logo"].y) == (30, 10)
    assert (
        v.seite1.bausteine["positionen"].als_dict() == std.seite1.bausteine["positionen"].als_dict()
    )


def test_pflichtbausteine_bleiben_sichtbar_auch_wenn_die_datei_anderes_sagt():
    v = layout.aus_dict(
        {"seite1": {"bausteine": {"summen": {"sichtbar": False}, "logo": {"sichtbar": False}}}}
    )
    assert v.seite1.bausteine["summen"].sichtbar is True
    assert v.seite1.bausteine["logo"].sichtbar is False


@pytest.mark.parametrize(
    "roh, teil",
    [
        ({"version": 99}, "neuer"),
        ({"seite1": {"felder": [{"art": "video"}]}}, "unbekannt"),
        ({"seite1": {"bausteine": {"kopf": {"x": "links"}}}}, "keine Zahl"),
    ],
)
def test_unlesbare_vorlage(roh, teil):
    with pytest.raises(layout.LayoutFehler, match=teil):
        layout.laden(roh, None)


def test_regeln_ueberlappung_rand_groesse():
    v = layout.standard()
    v.seite1.bausteine["summen"].y = v.seite1.bausteine["positionen"].y + 10  # über die Tabelle
    v.folgeseite.bausteine["kopf"].x = 200  # über den Rand
    v.seite1.bausteine["positionen"].breite = 100
    f = layout.pruefen(v)
    assert any("Positionstabelle und Summenblock überlappen" in x for x in f), f
    assert any("Folgeseite: Rechnungskopf ragt über den Seitenrand" in x for x in f), f
    assert any("mindestens 120" in x for x in f), f
    with pytest.raises(layout.LayoutFehler):
        layout.laden(v.als_dict(), None)
    # freie Bausteine/Felder dürfen überlappen (Ebenen)
    v = layout.standard()
    v.seite1.felder.append(
        layout.Element("text", 20, 40, 100, 50, text="Über dem Empfänger", kennung="text1")
    )
    v.seite1.bausteine["logo"].x, v.seite1.bausteine["logo"].y = 20, 14
    assert layout.pruefen(v) == []


def test_zeichenfolge_ebenen_und_pflicht_oben():
    v = layout.standard()
    s = v.seite1
    s.felder.append(layout.Element("bild", 20, 40, 95, 40, ebene=9, kennung="bild1"))
    s.bausteine["logo"].ebene = 10
    folge = [e.art for e in s.zeichenfolge()]
    assert folge.index("logo") > folge.index("bild")  # höhere Ebene später
    letzte = folge[-len(layout.PFLICHT) :]
    assert set(letzte) == layout.PFLICHT  # Pflicht ganz oben


def test_vorlage_je_absender_profil():
    roh = {
        "absender": {"name": "Muster GmbH"},
        "layout": {"raster": 5},
        "absender_profile": [
            {"absender": {"name": "Zweitfirma  KG"}, "layout": {"raster": 10}},
            {"absender": {"name": "Ohne Layout AG"}},
        ],
    }
    assert layout.roh_fuer(roh, "Muster GmbH") == {"raster": 5}
    assert layout.roh_fuer(roh, "zweitfirma kg") == {"raster": 10}  # Leerzeichen/Groß egal
    assert layout.roh_fuer(roh, "Ohne Layout AG") is None  # eigenes Profil ohne Layout
    assert layout.roh_fuer(roh, "Fremd GmbH") == {"raster": 5}  # wie die Stammdaten


def test_bestehende_konfiguration_ohne_layout_unveraendert(konfig):
    assert "layout" not in konfig.roh
    r = beispielrechnung.rechnung()
    assert pipeline.vorlage_fuer(r, konfig) is None
    assert sicht.erzeugen(r, sprache="de") == sicht._erzeugen_standard(
        r, "de"
    )  # fester Weg wie bis 0.6.2


def test_ungueltige_vorlage_in_der_konfiguration_gibt_standard_und_hinweis(konfig):
    v = layout.standard()
    v.seite1.bausteine["summen"].y = v.seite1.bausteine["positionen"].y
    konfig.roh = {**konfig.roh, "layout": v.als_dict()}
    r = beispielrechnung.rechnung()
    assert pipeline.vorlage_fuer(r, konfig) is None
    assert any("Standardlayout" in h.text for h in r.hinweise)


# ---------------------------------------------------------------- Renderer
def test_bausteine_an_ihrer_position():
    v = layout.standard()
    s = v.seite1.bausteine
    s["empfaenger"].x, s["kopf"].x = 115, 20  # getauscht wie in der Skizze
    s["empfaenger"].breite, s["kopf"].breite = 75, 80
    ws = _woerter(sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v, sprache="de"))
    assert _im_rahmen(ws, s["empfaenger"], {"Nordlicht", "Hafenstraße", "20457"})
    assert _im_rahmen(ws, s["kopf"], {"RE-2026-0042", "K-1042", "03.11.2026"})
    assert _im_rahmen(ws, s["summen"], {"Gesamtbetrag", "919,87"})
    assert _im_rahmen(ws, s["positionen"], {"Konferenztisch,", "ART-3102"})
    assert _im_rahmen(ws, s["fusszeile"], {"DE123456788"})  # USt-IdNr.
    assert _im_rahmen(ws, s["zahlung"], {"DE89"})


def test_ausrichtung_rechts():
    v = layout.standard()
    e = v.seite1.bausteine["empfaenger"]
    e.ausrichtung = "rechts"
    ws = _woerter(sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v, sprache="de"))
    w = next(w for w in ws if w["text"] == "Hamburg")
    assert abs(w["x1"] - (e.x + e.breite) * mm) < 1.5


def test_freiwillige_bausteine_ausblenden_skonto_bleibt():
    v = layout.standard()
    v.seite1.bausteine["zahlung"].sichtbar = False
    v.seite1.bausteine["hinweise"].sichtbar = False
    r = beispielrechnung.rechnung(
        zahlung=Zahlung(
            iban="DE89370400440532013000",
            ziel_tage=30,
            bedingungen="Zahlbar in 14 Tagen mit 2 % Skonto, 30 Tage netto.",
        )
    )
    t = _text(sicht.erzeugen(r, vorlage=v, sprache="de"))[0]
    assert "Bitte überweisen" not in t and "strukturierten Rechnungsdaten" not in t
    assert "2 % Skonto" in t  # § 14 Abs. 4 Nr. 7 UStG – im Summenblock
    assert "IBAN DE89" in t  # Bank dann in der Fußzeile
    r2 = beispielrechnung.rechnung()  # ohne Skonto: keine Zahlungsbedingung
    assert "Zahlbar innerhalb" not in _text(sicht.erzeugen(r2, vorlage=v, sprache="de"))[0]


def test_pflichtangabe_liegt_ueber_eigenem_bild(tmp_path):
    blau = tmp_path / "blau.png"
    Image.new("RGB", (400, 200), (0, 0, 255)).save(blau)
    v = layout.standard()
    v.basis = tmp_path
    e = v.seite1.bausteine["empfaenger"]
    v.seite1.felder.append(
        layout.Element(
            "bild", e.x, e.y, e.breite, e.hoehe, ebene=99, datei="blau.png", kennung="bild1"
        )
    )
    pdf = sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v, sprache="de")
    import pypdfium2 as pdfium

    bild = pdfium.PdfDocument(pdf)[0].render(scale=2).to_pil().convert("RGB")
    k = 2 * 72 / 25.4
    box = bild.crop(
        (int(e.x * k), int(e.y * k), int((e.x + e.breite) * k), int((e.y + e.hoehe) * k))
    )
    farben = box.getcolors(1 << 20)
    blau_anteil = sum(n for n, c in farben if c[2] > 200 and c[0] < 60) / (box.width * box.height)
    dunkel = sum(n for n, c in farben if max(c) < 70)
    assert blau_anteil > 0.5 and dunkel > 200  # Bild liegt darunter, Text ist darüber sichtbar


def test_folgeseiten_umbruch_kopf_und_uebertrag():
    v = layout.standard()
    r = beispielrechnung.rechnung(positionen=40)
    pdf = sicht.erzeugen(r, vorlage=v, sprache="de")
    seiten = _text(pdf)
    assert len(seiten) >= 2
    for t in seiten:
        assert "Bezeichnung" in t and "Einzelpreis" in t  # Tabellenkopf wiederholt
    assert "Übertrag" in seiten[0] and "Übertrag" in seiten[1]
    assert "Gesamtbetrag" not in seiten[0] and "Gesamtbetrag" in seiten[-1]
    n = len(seiten)
    assert f"1 von {n}" in seiten[0] and f"{n} von {n}" in seiten[-1]
    teile = sicht_layout.seiten_aufteilen(r, v)
    assert sum(len(t) for t in teile) == 40
    zwischen = sum(z.pos.netto for z in teile[0])
    assert sicht.eur(zwischen) in seiten[0] and sicht.eur(zwischen) in seiten[1]
    ws = [w for w in _woerter(pdf, 0)]
    tab = v.seite1.bausteine["positionen"]
    assert all(
        w["bottom"] <= (tab.y + tab.hoehe) * mm + 1 for w in ws if w["text"].startswith("ART-")
    )
    assert "Nordlicht" not in seiten[1]  # Empfänger nur auf Seite 1


def test_eigene_text_und_bildfelder(tmp_path):
    shutil.copy(BSP / "layout" / "logo.png", tmp_path / "logo.png")
    v = layout.standard()
    v.basis = tmp_path
    v.logo = "logo.png"
    t = layout.Element(
        "text", 20, 230, 80, 15, schrift=10, kennung="text1", text="Gruß aus dem Testlabor"
    )
    b = layout.Element("bild", 150, 235, 30, 15, kennung="bild1", datei="logo.png")
    v.seite1.felder += [t, b]
    pdf = sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v, sprache="de")
    assert _im_rahmen(_woerter(pdf), t, {"Gruß", "Testlabor"})
    assert _bilder(pdf) == 2  # Logo + Bildfeld
    v.seite1.bausteine["logo"].sichtbar = False
    assert _bilder(sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v)) == 1


def test_zu_langer_text_wird_gemeldet_pflicht_nie_gekuerzt():
    v = layout.standard()
    v.seite1.bausteine["empfaenger"].hoehe = 8
    r = beispielrechnung.rechnung()
    bericht: list[str] = []
    t = _text(sicht.erzeugen(r, vorlage=v, bericht=bericht))[0]
    assert "20457 Hamburg" in t and any("Empfängeranschrift" in b for b in bericht)


def test_fehlende_bilddatei_nur_hinweis(tmp_path):
    v = layout.standard()
    v.basis = tmp_path
    v.logo = "weg.png"
    bericht: list[str] = []
    assert sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v, bericht=bericht).startswith(
        b"%PDF"
    )
    assert any("Logo fehlt" in b for b in bericht)


# ---------------------------------------------------------------- Briefpapier
def test_briefpapier_vektor_getrennt_seite1_folgeseite():
    v = layout.laden(_beispiel_roh(), BSP)
    pdf = sicht.erzeugen(beispielrechnung.rechnung(positionen=40), vorlage=v, sprache="de")
    t = _text(pdf)
    assert "Objekteinrichtung" in t[0] and "Objekteinrichtung" in t[1]
    with pikepdf.open(io.BytesIO(pdf)) as p:
        xo = [
            [
                n
                for n, x in (s.obj.Resources.get("/XObject") or {}).items()
                if x.get("/Subtype") == "/Form"
            ]
            for s in p.pages
        ]
        assert all(xo)  # unterlegt als Formular-XObject


def test_briefpapier_pruefen_statisch(tmp_path):
    assert layout.briefpapier_pruefen(BSP / "layout" / "briefpapier-seite1.pdf").ok
    b = layout.briefpapier_pruefen(_cmyk_briefpapier(tmp_path / "cmyk.pdf"))
    assert not b.ok and any("CMYK" in g for g in b.gruende)
    b = layout.briefpapier_pruefen(_schrift_briefpapier(tmp_path / "schrift.pdf"))
    assert not b.ok and any("Fantasie-Grotesk" in g for g in b.gruende)
    (tmp_path / "kaputt.pdf").write_bytes(b"%PDF-1.4 kaputt")
    assert layout.briefpapier_pruefen(tmp_path / "kaputt.pdf").seiten == 0


def test_briefpapier_als_bild(tmp_path):
    ziel = layout.briefpapier_als_bild(
        _cmyk_briefpapier(tmp_path / "cmyk.pdf"), tmp_path / "bp.jpg", dpi=100
    )
    im = Image.open(ziel)
    assert im.mode == "RGB" and abs(im.size[0] / im.size[1] - 210 / 297) < 0.01
    v = layout.standard()
    v.basis = tmp_path
    v.seite1.briefpapier = "bp.jpg"
    assert _bilder(sicht.erzeugen(beispielrechnung.rechnung(), vorlage=v)) == 1


def _konfig_mit_layout(konfig, tmp_path, roh: dict) -> None:
    shutil.copytree(BSP / "layout", tmp_path / "layout")
    konfig.basis = tmp_path
    konfig.roh = {**konfig.roh, "layout": roh}


def test_pipeline_ohne_briefpapier_wenn_nicht_reparierbar(konfig, tmp_path):
    roh = _beispiel_roh()
    _konfig_mit_layout(konfig, tmp_path, roh)
    _schrift_briefpapier(tmp_path / "layout" / "schrift.pdf")
    roh["seite1"]["briefpapier"] = "layout/schrift.pdf"
    r = beispielrechnung.rechnung()
    pdf = pipeline._sichtteil_neu(r, konfig, cii.erzeugen(r, "EN16931"), "t", "b")
    assert any("Briefpapier nicht PDF/A-tauglich" in h.text for h in r.hinweise)
    assert "Briefkopf" not in _text(pdf)[0] and "Nordlicht" in _text(pdf)[0]


def test_pipeline_csv_mit_eigener_vorlage(konfig, eingang, tmp_path):
    _konfig_mit_layout(konfig, tmp_path, _beispiel_roh())
    lauf = pipeline.verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert lauf.ergebnisse and all(e.status != "fehler" for e in lauf.ergebnisse), lauf.datei_fehler
    pdfs = sorted(konfig.ausgang.glob("*_zugferd.pdf"))
    assert pdfs
    t = _text(pdfs[0].read_bytes())[0]
    assert "Objekteinrichtung" in t and "Vielen Dank für Ihren Auftrag!" in t


# ---------------------------------------------------------------- echte Prüfung (Mustang/veraPDF + KoSIT)
@pytest.mark.validierung
@pytest.mark.skipif(not all(werkzeuge.values()), reason="Java/KoSIT/Mustang nicht vorhanden")
def test_veraPDF_und_kosit_mit_vorlage_briefpapier_und_feldern(konfig, eingang, tmp_path):
    _konfig_mit_layout(konfig, tmp_path, _beispiel_roh())
    out = tmp_path / "pruef"
    out.mkdir()
    v = layout.laden(_beispiel_roh(), tmp_path)
    for n in (3, 40):  # eine Seite / Folgeseiten
        r = beispielrechnung.rechnung(positionen=n)
        (out / f"vektor-{n}.pdf").write_bytes(
            pdfa.zugferd_pdf(
                sicht.erzeugen(r, vorlage=v),
                cii.erzeugen(r, "EN16931"),
                titel="t",
                autor=r.verkaeufer.name,
            )
        )
    bild = copy.deepcopy(v)  # umgewandeltes (CMYK-)Briefpapier als Bild
    layout.briefpapier_als_bild(
        _cmyk_briefpapier(tmp_path / "cmyk.pdf"), tmp_path / "layout" / "bp.jpg"
    )
    bild.seite1.briefpapier = bild.folgeseite.briefpapier = "layout/bp.jpg"
    r = beispielrechnung.rechnung(positionen=40)
    (out / "bild-40.pdf").write_bytes(
        pdfa.zugferd_pdf(
            sicht.erzeugen(r, vorlage=bild),
            cii.erzeugen(r, "EN16931"),
            titel="t",
            autor=r.verkaeufer.name,
        )
    )
    pipeline.verarbeiten(eingang("variante-d_rabatt_gutschrift_lastschrift.csv"), konfig)
    dateien = sorted(out.glob("*.pdf")) + sorted(konfig.ausgang.glob("*_zugferd.pdf"))
    assert len(dateien) > 3
    erg = validierung.pruefen(dateien)
    assert erg and all(e.gueltig and not e.fehler for e in erg), [
        e.zeile() + str(e.fehler[:3]) for e in erg
    ]
    assert all("konform=true" in e.info for e in erg if e.werkzeug == "Mustang"), [
        e.info for e in erg
    ]
