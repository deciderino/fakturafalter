# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Positionstabelle 0.9.5: keine Art.-Nr.-Spalte mehr, Angaben als Unterzeilen unter der Bezeichnung (fiktive Daten)."""

import io
import re
from datetime import date
from decimal import Decimal as D

import pdfplumber
import pytest
from reportlab.lib.units import mm

from fakturafalter import aufbau, beispielrechnung, cii, layout, rechnen, sicht, sicht_layout
from fakturafalter.modell import Herkunft, Merkmal, Position, ZuAbschlag

H = Herkunft("test", 1.0)
LANG = "ART-2026-M8X40-DIN933-VZ-L500-0047281590-SONDERANFERTIGUNG-REV-C-0815-4711-EXTRA-LANG"


def _voll() -> Position:
    return Position(
        nr="1", artikelnummer="A-1", bezeichnung="Schraube", beschreibung="Langtext", kaeufer_artikelnummer="KD-1",
        standard_id="4012345678901", standard_schema="0160", ursprungsland="DE",
        merkmale=[Merkmal("Zeichnungsnummer", "Z-9"), Merkmal("Index", "C"), Merkmal("Farbe", "blau")],
        bestellposition="10", buchungsreferenz="KST-1", objektkennung="OBJ-7",
        leistung_von=date(2026, 11, 1), leistung_bis=date(2026, 11, 30), notiz="Teillieferung",
        bruttopreis=D("12"), preisrabatt=D("2"),
        zu_abschlaege=[ZuAbschlag(prozent=D("5"), grund="Rabatt"), ZuAbschlag(zuschlag=True, betrag=D("1"))],
    )


def test_reihenfolge_de():
    z = [t for t, _ in sicht.unterzeilen(_voll(), "de")]
    assert z[:4] == ["Art.-Nr. A-1", "Ihre Art.-Nr. KD-1", "Zeichnungs-Nr. Z-9, Index C", "GTIN 4012345678901"]
    assert z[4:10] == [
        "Beschreibung: Langtext", "Farbe: blau", "Ursprungsland: DE", "Bestellpos. 10", "Kostenstelle: KST-1",
        "Objekt: OBJ-7",
    ]
    assert z[10] == "Leistungszeitraum: 01.11.2026 – 30.11.2026"
    assert z[11] == "Hinweis: Teillieferung"
    assert z[12].startswith("Listenpreis") and "Rabatt" in z[13] and "Zuschlag" in z[14]
    assert len(z) == 15
    assert not any("Zeichnungsnummer:" in t or t.startswith("Index:") for t in z)  # nicht doppelt
    grau = [g for _, g in sicht.unterzeilen(_voll(), "de")]
    assert grau[:4] == [True] * 4 and not any(grau[4:])


def test_reihenfolge_en():
    z = [t for t, _ in sicht.unterzeilen(_voll(), "en")]
    assert z[:4] == ["Item no. A-1", "Your item no. KD-1", "Drawing no. Z-9, revision C", "GTIN 4012345678901"]
    assert "Description: Langtext" in z and "Country of origin: DE" in z and "Order line 10" in z
    assert "Service period: 01.11.2026 – 30.11.2026" in z and "Note: Teillieferung" in z
    assert any(t.startswith("List price") for t in z)
    assert any(t.startswith("Discount 5 %") for t in z) and any(t.startswith("Charge") for t in z)


def test_leer_keine_unterzeile():
    assert sicht.unterzeilen(Position(nr="1", bezeichnung="Ware"), "de") == []
    p = Position(nr="1", bezeichnung="Ware", beschreibung="Ware", merkmale=[Merkmal("Index", "B")])
    assert [t for t, _ in sicht.unterzeilen(p, "de")] == ["Index B"]  # Beschreibung = Bezeichnung entfällt
    p = Position(nr="1", bezeichnung="Ware", merkmale=[Merkmal("Zeichnungsnummer", "Z-1")], leistung_von=date(2026, 1, 2))
    assert [t for t, _ in sicht.unterzeilen(p, "de")] == ["Zeichnungs-Nr. Z-1", "Leistungszeitraum: ab 02.01.2026"]


def _roh(**w):
    return {k: (v, H) for k, v in w.items()}


def test_zeichnung_index_als_merkmal_im_xml(konfig):
    kopf = _roh(**{"BT-1": "RE-1", "BT-2": date(2026, 11, 20), "BT-44": "Firma Alpha", "BT-50": "Weg 1",
                   "BT-53": "12345", "BT-52": "Ort"})
    pos = [
        _roh(**{"BT-153": "Teil", "BT-129": D("2"), "BT-146": D("5"), "steuer": "19", "zeichnungsnummer": "Z-4711",
                "index": "C", "BT-155": LANG}),
        _roh(**{"BT-153": "Teil 2", "BT-129": D("1"), "BT-146": D("5"), "steuer": "19", "zeichnungsnummer": "",
                "index": ""}),
    ]
    r = aufbau.rechnung_bauen(kopf, pos, {"mappings": {"steuer": {"unbekannt": "satz"}}}, konfig, "t")
    rechnen.berechnen(r)
    assert r.status == "ok"
    assert [(m.name, m.wert) for m in r.positionen[0].merkmale] == [("Zeichnungsnummer", "Z-4711"), ("Index", "C")]
    assert r.positionen[1].merkmale == []
    xml = cii.erzeugen(r, "EN16931").decode()
    assert re.search(r"<ram:Description>Zeichnungsnummer</ram:Description>\s*<ram:Value>Z-4711</ram:Value>", xml)
    assert re.search(r"<ram:Description>Index</ram:Description>\s*<ram:Value>C</ram:Value>", xml)
    assert f"<ram:SellerAssignedID>{LANG}</ram:SellerAssignedID>" in xml


def _text(pdf: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return [p.extract_text() or "" for p in d.pages]


def _renderer():
    return [pytest.param(None, id="standard"), pytest.param("layout", id="layout")]


def _pdf(r, art, sprache="de"):
    return sicht.erzeugen(r, sprache=sprache, vorlage=layout.standard() if art else None)


@pytest.mark.parametrize("art", _renderer())
def test_kopf_ohne_artnr_spalte_und_lange_artnr_vollstaendig(art):
    r = beispielrechnung.rechnung()
    r.positionen[0].artikelnummer = LANG
    r.positionen[0].merkmale = [Merkmal("Zeichnungsnummer", "4711-0815-22"), Merkmal("Index", "C")]
    pdf = _pdf(r, art)
    t = _text(pdf)[0]
    kopf = [z for z in t.splitlines() if "Bezeichnung" in z and "Einzelpreis" in z][0]
    assert "Art.-Nr." not in kopf and kopf.split()[:2] == ["Pos", "Bezeichnung"]
    assert LANG in t.replace("\n", "").replace(" ", "")  # nie gekürzt, nur umbrochen
    assert "Zeichnungs-Nr. 4711-0815-22, Index C" in t
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        ws = d.pages[0].extract_words()
        bez = [w for w in ws if w["text"] == "Bezeichnung"][0]
        menge = [w for w in ws if w["text"] == "Menge"][0]
        grau = [w for w in ws if w["text"].startswith("ART-2026")]
        assert grau and all(w["x0"] >= bez["x0"] - 1 and w["x1"] <= menge["x0"] for w in grau)
        assert abs(bez["x0"] - 30 * mm) < 1.5  # L (20 mm) + 10 mm
        farben = {c.get("non_stroking_color") for c in d.pages[0].chars if c["text"] == "A" and c["size"] < 8.5}
        assert any(f and len(f) >= 1 and abs(f[0] - 0.4) < 0.01 for f in farben)


@pytest.mark.parametrize("art", _renderer())
@pytest.mark.parametrize("sprache", ["de", "en"])
def test_seitenumbruch_mit_vielen_unterzeilen_ohne_ueberlappung(art, sprache):
    r = beispielrechnung.rechnung(positionen=30)
    for i, p in enumerate(r.positionen):
        p.artikelnummer = f"{LANG}-{i}"
        p.kaeufer_artikelnummer = f"KD-{i}"
        p.merkmale = [Merkmal("Zeichnungsnummer", f"Z-{i}"), Merkmal("Index", "A")]
        p.beschreibung = "Ein etwas längerer Beschreibungstext, der in der schmalen Spalte umbrechen muss."
        p.notiz = "Hinweis zur Position"
    rechnen.berechnen(r)
    pdf = _pdf(r, art, sprache)
    seiten = _text(pdf)
    assert len(seiten) >= 3
    alles = "".join(seiten).replace("\n", "").replace(" ", "")
    for i in range(30):
        assert f"Z-{i}," in alles and f"{LANG}-{i}" in alles
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        for seite in d.pages:
            ws = seite.extract_words()
            for a in ws:  # kein Wort liegt über einem anderen
                for b in ws:
                    if a is b:
                        continue
                    ueber_x = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                    ueber_y = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
                    assert not (ueber_x > 1 and ueber_y > 1), (a["text"], b["text"])
            fuss = [w for w in ws if w["text"].startswith("USt-IdNr")]
            if fuss:
                tabelle = [w for w in ws if w["text"].startswith(("ART-", "KD-", "Z-"))]
                assert all(w["bottom"] < fuss[0]["top"] for w in tabelle)
    if art:
        teile = sicht_layout.seiten_aufteilen(r, layout.standard())
        assert sum(len(t) for t in teile) == 30


def test_preiseinheit_bleibt_in_preiszelle():
    r = beispielrechnung.rechnung()
    r.positionen[0].preiseinheit = D("100")
    rechnen.berechnen(r)
    t = _text(_pdf(r, None))[0]
    zeile = [z for z in t.splitlines() if "/ 100" in z or "je 100" in z or "pro 100" in z]
    assert zeile
