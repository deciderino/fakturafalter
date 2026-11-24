# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Anlern-Assistent (Modus „Nur PDF“): Vorschläge, Klick ins PDF, Pflichtfelder, Positionstabelle und der
ganze Ablauf bis zur automatischen Freigabe nach fünf Rechnungen ohne Korrektur."""

import re
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from fakturafalter import anlernen, konfig, pdferkennung, pipeline

BSP = Path(__file__).resolve().parent.parent / "beispiele"
IND = BSP / "industrie"


@pytest.fixture
def k(tmp_path):
    roh = yaml.safe_load((IND / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    pfad = tmp_path / "konfiguration.yaml"
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    k = konfig.lade_konfig(pfad)
    k.ordner_anlegen()
    k.pfad_datei = pfad
    return k


def sitzung(k, nr):
    return anlernen.Sitzung(shutil.copy(IND / "eingang" / f"{nr}.pdf", k.eingang), k)


def test_vorschlaege_erste_rechnung(k):
    s = sitzung(k, "NB-26-1001")
    assert s.profil is None and s.vorlage is None
    assert s.absender.name == "Normteile Brückner GmbH" and not s.absender.fehlt()
    assert s.werte["BT-1"].wert == "NB-26-1001"
    assert s.werte["BT-1"].woerter  # Fundstelle im PDF zum Markieren
    assert s.werte["BT-119"].wert == "19 %"
    assert not s.fehlende() or all(s.werte[f].status == "pruefen" for f in s.fehlende())
    pos = s.positionen()
    assert pos and s.summenpruefung()[2]
    assert any(p.preiseinheit for p in pos) or s.tabelle.preiseinheit == "spalte"
    assert not s.tabelle_fehlt()


def test_klick_ins_pdf(k):
    s = sitzung(k, "NB-26-1001")
    (w,) = [w for w in s.woerter(0) if w.t == "NB-26-1001" and w.top < 200]
    text, ws = s.wort_an(0, (w.x0 + w.x1) / 2, w.top + 2)
    assert text == "NB-26-1001" and ws
    assert s.wort_an(0, 2, 2) is None


def test_setzen_hinweise(k):
    s = sitzung(k, "NB-26-1001")
    assert s.setzen("BT-2", "morgen").status == "pruefen"
    assert "Datum" in s.werte["BT-2"].hinweis
    assert "BT-2" in s.fehlende()
    vs = s.setzen("BT-119", "0 %")
    assert vs.status == "pruefen" and "Version 2.0" in vs.hinweis
    vs = s.setzen("BT-1", "XY-999")
    assert vs.status == "erkannt" and "Nicht in der PDF gefunden" in vs.hinweis
    assert s.setzen("BT-1", "").status == "fehlt"


def test_pflichtfelder_sperren_speichern(k):
    s = sitzung(k, "NB-26-1001")
    for f in anlernen.PFLICHT:
        s.bestaetigen(f)
    assert s.fertig()
    s.setzen("BT-112", "")
    assert not s.fertig() and s.fehlende() == ["BT-112"]


def test_ohne_steuersatz_kein_stiller_standard(k):
    """Steuersatz leer: Speichern gesperrt (Pflichtfeld) und die Vorschau nimmt nicht still 19 % an."""
    s = sitzung(k, "NB-26-1001")
    s.setzen("BT-119", "")
    assert not s.fertig() and "BT-119" in s.fehlende()
    assert "steuer_fest" not in s.pv()
    r = s.rechnung()
    assert any(h.stufe == "pruefen" and h.feld.endswith("BT-151") for h in r.hinweise)


def test_spalten_dropdown_und_rahmen(k):
    s = sitzung(k, "NB-26-1001")
    t = s.tabelle
    assert set(anlernen.PFLICHTSPALTEN) <= set(t.spalten)
    t.spalten[t.spalten.index("BT-146")] = "ignorieren"
    assert s.tabelle_fehlt()  # Einzelpreis fehlt -> Speichern gesperrt
    assert not s.fertig()


@pytest.mark.parametrize(
    "datei",
    [
        "EF-1043.pdf",
        "PW-INV-2026-0087.pdf",
        "SK-2026-0412.pdf",
        "GL-2026-118.pdf",
        "MK-26-0412.pdf",
    ],
)
def test_tabellen_fremder_layouts(k, datei):
    pfad = BSP / "pdf-erkennung" / "eingang" / datei
    if not pfad.exists():
        pytest.skip(datei)
    s = anlernen.Sitzung(shutil.copy(pfad, k.eingang), k)
    netto, soll, ok = s.summenpruefung()
    assert s.positionen() and ok, (netto, soll)


@pytest.mark.validierung
def test_ablauf_bis_nur_pdf(k):
    for n in range(1001, 1007):
        s = sitzung(k, f"NB-26-{n}")
        for f in s.fehlende():
            s.bestaetigen(f)
        assert s.fertig(), s.fehlende()
        erg, v = s.speichern(k.pfad_datei)
        assert erg.status == "ok", erg.hinweise
        assert not (k.eingang / f"NB-26-{n}.pdf").exists()
    (prof,) = k.pdf_profile
    assert prof["verkaeufer"]["name"] == "Normteile Brückner GmbH"
    assert s.fortschritt()[0] >= 5
    assert pdferkennung.sicher(v, pdferkennung.einstellungen(prof))
    gespeichert = yaml.safe_load(k.pfad_datei.read_text(encoding="utf-8"))
    assert gespeichert["pdf_profile"]

    anlernen.nur_pdf_schalten(prof, True)
    shutil.copy(IND / "eingang" / "NB-26-1008.pdf", k.eingang)
    (e,) = pipeline.verarbeiten(sorted(k.eingang.iterdir()), k).ergebnisse
    assert e.status == "ok", e.hinweise
    assert Decimal(e.brutto) > 0


# ---------------------------------------------------------------- Beschriftung statt Wert angeklickt
def _versand_pdf(
    ziel: Path, i: int, lieferung, fmt: str = "%d.%m.%y", darunter: bool = False
) -> Path:
    """Normteile-Layout, aber „Versanddatum:“ statt „Lieferdatum:“ (kein bekanntes Schlüsselwort); der Wert
    steht rechts daneben oder – mit ``darunter`` – direkt unter der Beschriftung."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "industrie_beispiele", IND / "erzeuge_beispiele.py"
    )
    eb = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = eb  # für @dataclass nötig
    spec.loader.exec_module(eb)
    r = eb.rechnungen()[i]
    r.lieferung = lieferung
    alt, neu = f"{lieferung:%d.%m.%Y}", f"{lieferung:{fmt}}"

    class Blatt(eb.Blatt):
        def t(self, x, top, text, size=9, **kw):
            if text == "Lieferdatum:":
                text = "Versanddatum:"
            elif text == alt and x == 545:
                text = neu
                if darunter:
                    x, top, kw = 350, top + 7, {}
            super().t(x, top, text, size, **kw)

    pfad = ziel / f"{r.nr}.pdf"
    eb.Blatt = Blatt  # eigene Modulkopie, nur für diesen Test
    eb.zeichnen(r, pfad)
    return pfad


def _klick(s, text):
    (w,) = [w for w in s.woerter(0) if w.t == text]
    return s.wort_an(0, (w.x0 + w.x1) / 2, w.top + 2)


@pytest.mark.parametrize(
    "fmt, darunter", [("%d.%m.%y", False), ("%d.%m.%Y", False), ("%d.%m.%y", True)]
)
def test_beschriftung_angeklickt_wert_daneben(k, fmt, darunter):
    from datetime import date

    s = anlernen.Sitzung(_versand_pdf(k.eingang, 0, date(2026, 10, 29), fmt, darunter), k)
    text, ws = _klick(s, "Versanddatum:")
    assert text == "Versanddatum:"
    vs = s.setzen("leistung", text, ws)
    assert vs.status == "erkannt", vs.hinweis
    assert s.wert("leistung") == date(2026, 10, 29)
    assert vs.wert == "29.10.2026"
    assert [w.t for w in vs.woerter] == [f"{date(2026, 10, 29):{fmt}}"]  # Markierung auf dem Wert
    assert s.bestaetigen("leistung").beschriftung  # „Passt“ behält die Beschriftung


def test_beschriftung_ohne_datum_bleibt_fehler(k):
    from datetime import date

    s = anlernen.Sitzung(_versand_pdf(k.eingang, 0, date(2026, 10, 29)), k)
    text, ws = _klick(s, "Bestellung:")
    vs = s.setzen("leistung", text, ws)
    assert vs.status == "pruefen"
    assert "Kein Datum oder Zeitraum erkannt" in vs.hinweis
    assert not vs.beschriftung


def test_zweistelliges_jahr():
    from datetime import date

    assert anlernen.lesen("BT-2", "29.10.26") == date(2026, 10, 29)
    assert anlernen.lesen("leistung", "29.10.26") == date(2026, 10, 29)
    assert anlernen.lesen("leistung", "01.10.26 – 31.10.26") == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )


def test_beschriftung_vorlage_rundlauf(k):
    """Gelernt wird die Stelle neben „Versanddatum:“; die nächste PDF im selben Layout liest den Wert selbst."""
    from datetime import date

    s = anlernen.Sitzung(_versand_pdf(k.eingang, 0, date(2026, 10, 29)), k)
    s.setzen("leistung", *_klick(s, "Versanddatum:"))
    for f in s.fehlende():
        s.bestaetigen(f)
    assert s.fertig(), s.fehlende()
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    regel = v["felder"]["BT-72"]
    assert regel["lage"] == "naechster" and regel["anker"] == ["Versanddatum:"]

    s2 = anlernen.Sitzung(_versand_pdf(k.eingang, 1, date(2026, 11, 3)), k)
    assert s2.vorlage is not None
    assert s2.werte["leistung"].status == "erkannt"
    assert s2.wert("leistung") == date(2026, 11, 3)


def _industrie_modul():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "industrie_beispiele", IND / "erzeuge_beispiele.py"
    )
    eb = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = eb  # für @dataclass nötig
    spec.loader.exec_module(eb)
    return eb


def _lf_pdf(ziel: Path) -> Path:
    """Normteile-Layout, aber mit einem Zeilenumbruch (Byte 0x0A) im Textstring hinter IBAN, Lieferdatum und
    Firmenname – so wie manche Warenwirtschaften drucken. pdfminer liest ihn als „(cid:10)“."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    eb = _industrie_modul()
    r = eb.rechnungen()[0]
    iban = eb.iban_gruppiert(eb.IBAN)

    class Blatt(eb.Blatt):
        def t(self, x, top, text, size=9, fett=False, rechts=False, **kw):
            text = text.replace(f"IBAN {iban} ", f"IBAN {iban}\n ")
            if text in ("Lieferdatum:", f"{r.lieferung:%d.%m.%Y}", eb.NAME):
                text += "\n"
            if "\n" not in text:
                return super().t(x, top, text, size, fett=fett, rechts=rechts, **kw)
            f = self.schrift + ("-Bold" if fett else "")
            teile = text.split("\n")
            x -= stringWidth("".join(teile), f, size) if rechts else 0
            y = self.c._pagesize[1] - top - size
            for j, teil in enumerate(teile):
                if j:  # roher Textstring mit 0x0A, ohne Breite
                    self.c._code.append(
                        f"BT {self.c._doc.getInternalFontName(f)} {size} Tf "
                        f"1 0 0 1 {x:.2f} {y:.2f} Tm (\\012) Tj ET"
                    )
                super().t(x, top, teil, size, fett=fett)
                x += stringWidth(teil, f, size)

    pfad = ziel / f"{r.nr}.pdf"
    eb.Blatt = Blatt
    eb.zeichnen(r, pfad)
    return pfad


def test_steuerzeichen_cid10_nicht_im_wert(k):
    """Ein 0x0A im Textstring kommt aus pdfminer als „(cid:10)“ am Wort davor. Er darf weder in der Anzeige
    stehen noch die Prüfung (IBAN-Prüfziffer, Datum, Absender vollständig) scheitern lassen."""
    from datetime import date

    from fakturafalter.pflichtpruefung import iban_gueltig

    eb = _industrie_modul()
    s = anlernen.Sitzung(_lf_pdf(k.eingang), k)
    assert not [w.t for p in range(len(s.seiten)) for w in s.woerter(p) if "cid" in w.t.lower()]
    assert s.absender.name == eb.NAME
    assert s.absender.iban.replace(" ", "") == eb.IBAN and iban_gueltig(eb.IBAN)
    assert not s.absender.fehlt()
    assert s.wert("leistung") == date(2026, 10, 4)
    text, ws = _klick(s, "Lieferdatum:")
    assert text == "Lieferdatum:"


def test_alte_vorlage_mit_cid_anker(k):
    """Vorlagen, die vor der Bereinigung gelernt wurden, tragen „(cid:10)“ im Anker – sie greifen weiter."""
    from fakturafalter import adapter_pdf

    assert adapter_pdf.ohne_steuerzeichen("Lieferdatum:(cid:10)") == "Lieferdatum:"
    assert (
        adapter_pdf.ohne_steuerzeichen("A(cid:65)") == "A(cid:65)"
    )  # echte, nicht zuordenbare Glyphe bleibt
    zs = pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(_lf_pdf(k.eingang)))
    regel = {"lage": "naechster", "anker": ["Lieferdatum:(cid:10)"], "seite": 0}
    assert pdferkennung.feld_auslesen(regel, zs)[0] == "04.10.2026"
    assert pdferkennung.feld_auslesen({**regel, "anker": ["(cid:10)"]}, zs) is None
    a = anlernen.Absender.aus_bloecken(
        {"name": "Beispiel GmbH"}, {"iban": "DE89370400440532013000(CID:10)"}
    )
    assert a.iban == "DE89370400440532013000"  # im Assistenten großgeschrieben gespeichert


# ---------------------------------------------------------------- Beschriftung bei Text-Feldern
@pytest.mark.parametrize(
    "feld, beschriftung, wert",
    [("BT-1", "Rechnung Nr.:", "NB-26-1001"), ("BT-13", "Ihre Bestellung:", "B-4500")],
)
def test_text_beschriftung_angeklickt_wert_daneben(k, feld, beschriftung, wert):
    s = sitzung(k, "NB-26-1001")
    (seg,) = [seg for z in s.zeilen for seg in z.abschnitte if _text_von(seg) == beschriftung]
    text, ws = s.wort_an(0, (seg[0].x0 + seg[0].x1) / 2, seg[0].top + 2)
    assert text == beschriftung
    vs = s.setzen(feld, text, ws)
    assert vs.status == "erkannt" and vs.wert == wert
    assert [w.t for w in vs.woerter] == [wert]
    assert vs.beschriftung and feld in s.stellen()


def test_text_beschriftung_im_selben_abschnitt():
    """„Kunden-Nr.: 4711“ als ein Abschnitt: die Beschriftung gehört nicht zum Wert."""
    assert anlernen.ist_beschriftung("kundennummer", "Kunden-Nr.:")
    assert anlernen.ist_beschriftung("BT-44", "Rechnungsempfänger")
    assert not anlernen.ist_beschriftung("BT-44", "Maschinenbau Halder KG")
    assert not anlernen.ist_beschriftung("BT-1", "NB-26-1001")


def test_text_beschriftung_mit_wert_in_einem_abschnitt(k):
    s = sitzung(k, "NB-26-1001")
    ws = [
        anlernen.Wort("Kunden-Nr.:", 300, 340, 600, 0, 609),
        anlernen.Wort("K-4711", 342, 370, 600, 0, 609),
    ]
    vs = s.setzen("kundennummer", "Kunden-Nr.: K-4711", ws)
    assert vs.wert == "K-4711" and [w.t for w in vs.woerter] == ["K-4711"]


def _text_von(seg):
    return " ".join(w.t for w in seg)


# ---------------------------------------------------------------- Altlasten in gespeicherten Profilen
def test_profil_cid_reste_beim_laden_bereinigt(k, tmp_path):
    from fakturafalter import konfig as km

    prof = anlernen.profil_anlegen(
        anlernen.Absender(name="Normteile Brückner GmbH", plz="42897", ort="Remscheid"),
        k,
        konfig_pfad=k.pfad_datei,
    )
    datei = Path(prof["_datei"])
    roh = yaml.safe_load(datei.read_text(encoding="utf-8"))
    roh["verkaeufer"]["name"] = "Normteile Brückner GmbH(CID:10)"  # wie von 0.4.1 gespeichert
    roh["verkaeufer"]["anschrift"] = {
        **(roh["verkaeufer"].get("anschrift") or {}),
        "strasse": "Gewerbering\x0a14",
    }
    roh["zahlung"]["iban"] = "DE34000000000071100842(CID:10)"
    datei.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    k2 = km.lade_konfig(k.pfad_datei)
    (p2,) = [p for p in k2.pdf_profile if p["_datei"] == str(datei)]
    assert p2["verkaeufer"]["name"] == "Normteile Brückner GmbH"
    assert p2["verkaeufer"]["anschrift"]["strasse"] == "Gewerbering 14"
    assert p2["zahlung"]["iban"] == "DE34000000000071100842"
    neu = datei.read_text(encoding="utf-8")
    assert "cid" not in neu.lower() and "Gewerbering 14" in neu  # zurückgeschrieben


def test_bereinigt_laesst_saubere_werte_und_mehrzeiliges():
    from fakturafalter.werte import bereinigt

    assert bereinigt("  Muster GmbH  ") == "  Muster GmbH  "  # unverändert, wenn nichts zu tun
    assert bereinigt("Zahlbar sofort.\nDanke.", mehrzeilig=True) == "Zahlbar sofort.\nDanke."
    assert bereinigt("A(cid:9)\x01B") == "A B"


# ---------------------------------------------------------------- Tabellenende nicht am Rahmenrand
def test_tabellenende_nicht_am_rahmenrand(k, monkeypatch):
    """Rahmen zu knapp (endet nach Pos. 40), keine Summenzeile erkannt: Die Tabelle endet erst an der
    ersten Zeile, die keine Position ist – nicht an Pos. 50 direkt unter dem Rahmen."""
    monkeypatch.setattr(pdferkennung, "summentext", lambda text: False)
    s = sitzung(k, "NB-26-1001")
    t = s.tabelle
    assert len(s.positionen()) == 6
    pos40 = next(z for z in s.zeilen if z.text.startswith("40 "))
    s.rahmen_setzen(t.seite, t.x0, t.top, t.x1, pos40.top + 12)
    pv = s.pv()
    assert pv["ende"][0].lower() == "warenwert"
    assert [p.nr for p in s.positionen()] == ["10", "20", "30", "40", "50", "60"]


# ---------------------------------------------------------------- Briefkopf nur als Bild
def _bildkopf_pdf(ziel: Path, i: int = 0):
    """Normteile-Layout, aber Briefkopf, Absenderzeile und Fußzeile nur als Bild (kein Text im Druck)."""
    eb = _industrie_modul()

    class Blatt(eb.Blatt):
        def t(self, x, top, text, size=9, **kw):
            if top < 110 or top > 770 or top == 128:
                return
            super().t(x, top, text, size, **kw)

    eb.Blatt = Blatt
    r = eb.rechnungen()[i]
    p = ziel / f"{r.nr}.pdf"
    eb.zeichnen(r, p)
    return p, eb


def test_bildkopf_anschriftfeld_ist_nicht_der_absender(k):
    p, eb = _bildkopf_pdf(k.eingang)
    s = anlernen.Sitzung(p, k)
    assert [anlernen._text(sg) for _, sg in s.anschriftfeld()] == [
        "Maschinenbau Halder KG",
        "Talsperrenweg 3",
        "58511 Lüdenscheid",
    ]
    assert s.absender.name != "Maschinenbau Halder KG" and s.absender.strasse != "Talsperrenweg 3"
    assert s.werte["BT-44"].wert == "Maschinenbau Halder KG"
    assert s.werte["BT-50"].wert == "Talsperrenweg 3"
    assert (s.werte["BT-53"].wert, s.werte["BT-52"].wert) == ("58511", "Lüdenscheid")


def test_kaeufer_neu_vorschlagen_nach_absenderaenderung(k):
    p, eb = _bildkopf_pdf(k.eingang)
    s = anlernen.Sitzung(p, k)
    # Nutzer hält versehentlich das Anschriftfeld für den Absender: Käufer-Vorschlag verschwindet …
    s.absender.strasse = "Talsperrenweg 3"
    s.kaeufer_neu_vorschlagen()
    assert s.werte["BT-50"].status == "fehlt" and not s.werte["BT-50"].wert
    # … und kommt zurück, sobald der richtige Absender eingetragen ist; Bestätigtes bleibt unangetastet
    s.setzen("BT-44", "Halder Maschinenbau KG")
    s.absender.strasse = eb.STRASSE
    assert set(s.kaeufer_neu_vorschlagen()) == {"BT-50", "BT-53", "BT-52"}
    assert s.werte["BT-50"].wert == "Talsperrenweg 3" and s.werte["BT-50"].status == "pruefen"
    assert s.werte["BT-44"].wert == "Halder Maschinenbau KG"


# ---------------------------------------------------------------- bekannter Absender, neues Layout
def test_profil_waehlen_neues_layout(k):
    s = sitzung(k, "NB-26-1001")
    for f in s.fehlende():
        s.bestaetigen(f)
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok"
    p, eb = _bildkopf_pdf(k.eingang, 1)  # anderes Layout (Briefkopf als Bild)
    s2 = anlernen.Sitzung(p, k)
    assert s2.profil is None and s2.absender.fehlt()
    s2.profil_waehlen(k.pdf_profile[0])
    assert s2.profil is k.pdf_profile[0] and s2.absender.name == eb.NAME and not s2.absender.fehlt()
    assert not s2.absender_geaendert()
    for f in s2.fehlende():
        s2.bestaetigen(f)
    erg2, v2 = s2.speichern(k.pfad_datei)
    assert erg2.status == "ok", erg2.hinweise
    assert (
        len(k.pdf_profile) == 1 and v2["kennung"] != v["kennung"]
    )  # zweite Vorlage im selben Profil
    s2.profil_waehlen(None)
    assert s2.profil is None and s2.absender_neu


# ---------------------------------------------------------------- Bereich ziehen (Regel „bereich“)
def _verschoben(zeilen, dy):
    from dataclasses import replace

    neu = []
    for z in zeilen:
        ab = [
            [replace(w, top=w.top + dy, bottom=w.bottom + dy) for w in seg] for seg in z.abschnitte
        ]
        neu.append(
            replace(z, top=z.top + dy, woerter=[w for seg in ab for w in seg], abschnitte=ab)
        )
    return neu


def test_bereich_ziehen_lernt_regel_relativ_zur_beschriftung(k):
    s = sitzung(k, "NB-26-1001")
    vs = s.bereich_setzen("BT-13", 0, 505, 172, 550, 186)
    assert vs.wert == "B-4500" and vs.status == "erkannt" and vs.bereich
    assert [w.t for w in vs.woerter] == ["B-4500"]
    for f in s.fehlende():
        s.bestaetigen(f)
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    regel = v["felder"]["BT-13"]
    assert regel["lage"] == "bereich" and regel["anker"] == ["Ihre", "Bestellung:"]
    # Beschriftung steht im nächsten Druck 20 pt tiefer: der Rahmen wandert mit
    assert pdferkennung.feld_auslesen(regel, _verschoben(s.zeilen, 20))[0] == "B-4500"
    # ohne Anker (fester Rahmen) gilt die Stelle auf der Seite
    fest = {k_: w for k_, w in regel.items() if not k_.startswith("anker")}
    assert pdferkennung.feld_auslesen(fest, s.zeilen)[0] == "B-4500"
    assert pdferkennung.feld_auslesen(fest, _verschoben(s.zeilen, 20))[0] != "B-4500"
    s2 = sitzung(k, "NB-26-1002")
    assert s2.werte["BT-13"].status == "erkannt" and s2.werte["BT-13"].wert.startswith("B-")


def test_bereich_mehrere_zeilen_und_neue_eingabe(k):
    s = sitzung(k, "NB-26-1001")
    vs = s.bereich_setzen("BT-44", 0, 45, 140, 200, 166)
    assert vs.wert == "Maschinenbau Halder KG Talsperrenweg 3"
    assert s.bereich_setzen("BT-13", 0, 300, 600, 400, 700).hinweis == "Im Rahmen steht kein Text."
    s.setzen("BT-44", "Maschinenbau Halder KG")
    assert s.werte["BT-44"].bereich is None


# ---------------------------------------------------------------- Anschrift als Block (0.4.2)
def test_anschrift_teilen():
    t = pdferkennung.anschrift_teilen
    assert t(["Maschinenbau Halder KG", "Talsperrenweg 3", "58511 Lüdenscheid"]) == {
        "BT-44": "Maschinenbau Halder KG",
        "BT-50": "Talsperrenweg 3",
        "BT-53": "58511",
        "BT-52": "Lüdenscheid",
    }
    assert t(
        [
            "Rechnungsanschrift:",
            "Beispiel AG",
            "Abteilung Einkauf",
            "Haus B",
            "Beispielweg 2",
            "D-54321 Beispielstadt",
            "Deutschland",
        ]
    ) == {
        "BT-44": "Beispiel AG Abteilung Einkauf Haus B",
        "BT-50": "Beispielweg 2",
        "BT-53": "54321",
        "BT-52": "Beispielstadt",
    }
    # Straße und Ort in einer Zeile; keine typische Straße -> Zeile über PLZ/Ort
    assert t(["Muster GmbH", "Musterstraße 1a, 12345 Musterstadt"])["BT-50"] == "Musterstraße 1a"
    assert t(["Muster GmbH", "z. Hd. Frau Beispiel", "Postfach", "12345 Musterstadt"]) == {
        "BT-44": "Muster GmbH",
        "BT-56": "Frau Beispiel",
        "BT-50": "Postfach",
        "BT-53": "12345",
        "BT-52": "Musterstadt",
    }
    assert t([]) == {}


def test_anschrift_block_rahmen_und_strg_klick(k):
    s = sitzung(k, "NB-26-1001")
    teile = s.anschrift_setzen(0, (45, 138, 260, 178))
    assert teile == {
        "BT-44": "Maschinenbau Halder KG",
        "BT-50": "Talsperrenweg 3",
        "BT-53": "58511",
        "BT-52": "Lüdenscheid",
    }
    assert all(s.werte[f].status == "erkannt" for f in ("BT-44", "BT-50", "BT-53", "BT-52"))
    assert s.werte["BT-51"].status == "fehlt" and s.werte["BT-50"].woerter
    assert pdferkennung.ANSCHRIFT_BLOCK in s.bereiche()
    s.setzen("BT-50", "Anderer Weg 1")  # Nutzer korrigiert ein Teil: kein Block mehr lernen
    assert pdferkennung.ANSCHRIFT_BLOCK not in s.bereiche()
    # Strg+Klick: Zeilen einzeln gewählt
    ws = [
        w
        for z in s.zeilen
        if z.seite == 0 and 140 <= z.top <= 172 and z.woerter[0].x0 < 60
        for w in z.abschnitte[0]
    ]
    assert s.anschrift_setzen(0, woerter=ws)["BT-52"] == "Lüdenscheid"
    assert s.werte["BT-50"].wert == "Talsperrenweg 3"
    assert s.anschrift_setzen(0, (300, 600, 400, 700)) == {}


def test_anschrift_block_lernt_eine_regel(k):
    s = sitzung(k, "NB-26-1001")
    s.anschrift_setzen(0, (45, 138, 260, 178))
    for f in s.fehlende():
        s.bestaetigen(f)
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    regel = v["felder"][pdferkennung.ANSCHRIFT_BLOCK]
    assert regel["lage"] == "bereich" and regel["block"] is True
    assert not {"BT-44", "BT-50", "BT-53", "BT-52"} & set(v["felder"])
    gelesen = pdferkennung.anschrift_auslesen(
        regel, _verschoben(s.zeilen, 20) if regel.get("anker") else s.zeilen
    )
    assert gelesen["BT-52"][0] == "Lüdenscheid"
    s2 = sitzung(k, "NB-26-1002")
    assert all(s2.werte[f].status == "erkannt" for f in ("BT-44", "BT-50", "BT-53", "BT-52"))
    r2 = s2.rechnung()
    assert (
        r2.kaeufer.name == s2.werte["BT-44"].wert
        and r2.kaeufer.anschrift.plz == s2.werte["BT-53"].wert
    )


def test_spaltenlinie_verschieben(k):
    """Spaltenlinie ziehen: Lage bleibt zwischen den Nachbarn, Zuordnung folgt den Überschriften."""
    s = sitzung(k, "NB-26-1001")
    t = s.tabelle
    alt_g, alt_sp = list(t.grenzen), list(t.spalten)
    i = alt_sp.index("BT-130")  # Linie zwischen „Menge“ und „ME“
    s.grenze_setzen(i, alt_g[i - 1] + 4)  # „Menge“ rutscht nach rechts in die ME-Spalte
    assert t.spalten[i - 1] == "ignorieren" and t.spalten[i] == "BT-129"
    pos = s.positionen()
    # „10 Stk“ in einer Spalte: Menge bleibt lesbar, Einheit aus der Mengenzelle
    assert pos and all(
        p.menge is not None and pdferkennung.einheit_code(p.einheit_text) for p in pos
    )
    s.grenze_setzen(i, alt_g[i])  # zurück: alles wie vorher
    assert t.grenzen == alt_g and t.spalten == alt_sp and s.summenpruefung()[2]
    s.grenze_setzen(i, -50)  # nie über die Nachbarlinie hinaus
    assert t.grenzen[i] == alt_g[i - 1] + 4
    s.grenze_setzen(i, 9999)
    assert t.grenzen[i] == alt_g[i + 1] - 4
    s.grenze_setzen(0, 10)  # linker Rand ist keine verschiebbare Linie
    assert t.grenzen[0] == alt_g[0]


# ---------------------------------------------------------------- ERP-Druck: Courier, leere Felder (0.4.3)
def _erp_pdf(
    ziel: Path,
    name=("Beispiel Werkzeug- und", "Anlagenbau GmbH"),
    datum_unter_versand=False,
    versanddatum="",
    bestellnummer="",
) -> Path:
    """Fiktiver ERP-Druck (Schreibmaschinenschrift): Briefkopf nur als Fläche, Firmenname über zwei Zeilen,
    „Versanddatum :“ in der Zeile von PLZ/Ort, leere Bestellnummer, Tabellenkopf ohne Positionen."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pfad = ziel / (
        "erp-"
        + "-".join(name).replace(" ", "_")
        + f"{int(datum_unter_versand)}"
        + re.sub(r"\W", "_", bestellnummer)
        + ".pdf"
    )
    c = canvas.Canvas(str(pfad), pagesize=A4)
    h = A4[1]

    def t(x, top, text, font="Courier"):
        c.setFont(font, 10)
        c.drawString(x, h - top - 8, text)

    c.setFillGray(0.85)
    c.rect(0, h - 100, A4[0], 100, stroke=0, fill=1)  # Briefkopf als Fläche (kein Text)
    c.setFillGray(0)
    t(42, 147, name[0])
    t(42, 159, name[1])
    t(42, 171, "Musterweg 12")
    t(42, 195, "12345 Musterstadt")
    rechts = [
        ("Bestellnummer: " + bestellnummer, 183),
        ("Versanddatum : " + versanddatum, 195),
        ("Versandart  :", 207),
        ("Kunde: 40711", 219),
        ("Datum: 05.10.2026", 231),
        ("Seite: 1/1", 243),
    ]
    if datum_unter_versand:
        rechts = [("Versanddatum :", 195), ("Datum: 05.10.2026", 207)]
    for text, top in rechts:
        t(360, top, text.rstrip())
    t(42, 255, "Rechnung - (Duplikat)")
    t(432, 255, "Beleg: 26000042", "Courier-Bold")
    t(42, 315, "Menge ME  Bezeichnung                    Preis EURO   Betrag EURO")
    t(42, 700, "Leistungsdatum = Versanddatum")
    t(42, 712, "zahlbar bis 04.11.2026 ohne Abzug.")
    c.save()
    return pfad


def _klick_oben(s, text):
    w = min((w for w in s.woerter(0) if w.t == text), key=lambda w: w.top)
    return s.wort_an(0, (w.x0 + w.x1) / 2, w.top + 2)


def test_erp_druck_vorschlaege(k):
    s = anlernen.Sitzung(_erp_pdf(k.eingang), k)
    assert s.werte["BT-1"].wert == "26000042"
    assert s.werte["BT-2"].wert == "05.10.2026"
    assert s.werte["BT-44"].wert == "Beispiel Werkzeug- und Anlagenbau GmbH"
    assert [w.t for w in s.werte["BT-44"].woerter][-2:] == ["Anlagenbau", "GmbH"]
    assert (s.werte["BT-50"].wert, s.werte["BT-53"].wert, s.werte["BT-52"].wert) == (
        "Musterweg 12",
        "12345",
        "Musterstadt",
    )
    assert s.werte["leistung"].status == "fehlt"
    assert s.tabelle_fehlt() and not s.positionen()  # Tabellenkopf ohne Zeilen: kein Absturz


def test_erp_druck_zweizeiliger_name_lernt_block(k):
    s = anlernen.Sitzung(_erp_pdf(k.eingang), k)
    for f in ("BT-44", "BT-50", "BT-53", "BT-52"):
        assert s.bestaetigen(f).status == "erkannt"
    assert not s.werte["BT-44"].hinweis  # nicht „Nicht in der PDF gefunden“
    seite, rahmen, block = s.bereiche()[pdferkennung.ANSCHRIFT_BLOCK]
    assert block
    regel = pdferkennung.bereich_regel(
        pdferkennung.ANSCHRIFT_BLOCK, s.zeilen, seite, rahmen, set(), True
    )
    # nächste Rechnung, anderer (längerer) Käufer im selben Layout: der Block liest beide Zeilen
    s2 = anlernen.Sitzung(
        _erp_pdf(k.eingang, ("Muster Feinmechanik und", "Gerätebau Nord GmbH")), k
    )
    assert (
        pdferkennung.anschrift_auslesen(regel, s2.zeilen)["BT-44"][0]
        == "Muster Feinmechanik und Gerätebau Nord GmbH"
    )
    s.setzen("BT-44", "Beispiel Anlagenbau GmbH")  # Nutzer ändert den Namen: kein Block
    assert pdferkennung.ANSCHRIFT_BLOCK not in s.bereiche()


def test_anschrift_teilen_name_zwei_zeilen():
    t = pdferkennung.anschrift_teilen
    assert (
        t(["Beispiel Werkzeug- und", "Anlagenbau GmbH", "Musterweg 12", "12345 Musterstadt"])[
            "BT-44"
        ]
        == "Beispiel Werkzeug- und Anlagenbau GmbH"
    )
    # über der Straße ist Name, auch Personen; nur Zeilen mit DIN-5008-Vermerk am Anfang gehen nach BT-51/BT-56
    # (Nutzer-Entscheid 23.11.2026)
    t2 = t(["Muster GmbH", "Abteilung Einkauf GmbH", "Musterweg 1", "12345 Musterstadt"])
    assert (t2["BT-44"], t2["BT-51"]) == ("Muster GmbH", "Abteilung Einkauf GmbH")
    assert t(["Frau Erika Beispiel", "Beispiel GmbH", "Musterweg 1", "12345 Musterstadt"]) == {
        "BT-44": "Frau Erika Beispiel Beispiel GmbH",
        "BT-50": "Musterweg 1",
        "BT-53": "12345",
        "BT-52": "Musterstadt",
    }
    assert (
        t(["Herrn Max Beispiel", "Musterweg 1", "12345 Musterstadt"])["BT-44"]
        == "Herrn Max Beispiel"
    )
    t3 = t(["Beispiel Handel", "z. Hd. Einkauf", "Musterweg 1", "12345 Musterstadt"])
    assert (t3["BT-44"], t3["BT-56"]) == ("Beispiel Handel", "Einkauf")


def test_erp_druck_beschriftung_mit_wert_im_abschnitt(k):
    """„Datum: 05.10.2026“ ist ein Abschnitt: Klick darauf liefert das Datum, nicht „Kein Datum erkannt“."""
    s = anlernen.Sitzung(_erp_pdf(k.eingang), k)
    vs = s.setzen("BT-2", *_klick_oben(s, "Datum:"))
    assert vs.status == "erkannt" and vs.wert == "05.10.2026"
    assert [w.t for w in vs.beschriftung] == ["Datum:"] and [w.t for w in vs.woerter] == [
        "05.10.2026"
    ]


@pytest.mark.parametrize(
    "feld, label, hinweis",
    [
        ("BT-13", "Bestellnummer:", "Bitte eintippen oder leer lassen."),
        ("leistung", "Versanddatum", "Bitte Datum oder Zeitraum eintippen"),
    ],
)
def test_erp_druck_leere_beschriftung_ist_kein_wert(k, feld, label, hinweis):
    s = anlernen.Sitzung(_erp_pdf(k.eingang), k)
    vs = s.setzen(feld, *_klick_oben(s, label))
    assert vs.status == "fehlt" and vs.wert == "" and not vs.woerter
    assert vs.hinweis.startswith(f"Neben „{label.rstrip(':')}“ steht in dieser PDF kein Wert.")
    assert hinweis in vs.hinweis
    assert feld not in s.stellen()


def test_erp_druck_versanddatum_gefuellt(k):
    s = anlernen.Sitzung(_erp_pdf(k.eingang, versanddatum="02.10.2026"), k)
    vs = s.setzen("leistung", *_klick_oben(s, "Versanddatum"))
    assert vs.status == "erkannt" and vs.wert == "02.10.2026"


def test_erp_druck_leere_beschriftung_nimmt_nicht_den_wert_darunter(k):
    """Unter dem leeren „Versanddatum :“ steht „Datum: …“ – das ist das Rechnungsdatum, nicht die Leistung."""
    s = anlernen.Sitzung(_erp_pdf(k.eingang, datum_unter_versand=True), k)
    vs = s.setzen("leistung", *_klick_oben(s, "Versanddatum"))
    assert vs.status == "fehlt" and s.wert("leistung") is None


# ---------------------------------------------------------------- ERP-Druck mit Positionen (0.4.3)
# Fiktive Rechnungen im Rohformat einer Warenwirtschaft (tests/erp_roh.py): je Wort ein TJ, Leerstellen als
# Tm-Sprünge, „\012“ am Zeilenende, „\[EURO\]“ in der Kopfzeile.
from . import erp_roh  # noqa: E402

S_ = erp_roh.STANDARD
ERP_VARIANTEN = {
    "ohne_trennlinie": {},
    "linie_gezeichnet": dict(vektorlinie=True),
    "trennlinie_minus": dict(zeilen=[erp_roh.trenn("-")] + S_ + [erp_roh.trenn("-")]),
    "trennlinie_gleich": dict(zeilen=[erp_roh.trenn("=")] + S_ + [erp_roh.trenn("=")]),
    "trennlinie_unterstrich": dict(zeilen=[erp_roh.trenn("_")] + S_ + [erp_roh.trenn("_")]),
    "trennlinie_ohne_summe": dict(
        zeilen=[erp_roh.trenn("-")] + S_ + ["", erp_roh.trenn("-")], nach=[" Vielen Dank."]
    ),
    "leerzeilen_nach_kopf": dict(zeilen=[erp_roh.trenn("-"), "", ""] + S_, leer_nach_kopf=1),
    "falzmarken": dict(falzmarken=(281.7, 340.7)),
    "falzmarke_linie_leerzeilen": dict(
        falzmarken=(281.7, 352.7), vektorlinie=True, leer_nach_kopf=2
    ),
    "zwischensumme": dict(nach=erp_roh.fuss(wort="Zwischensumme")),
    "uebertrag": dict(nach=[" " * 50 + "Übertrag".ljust(20) + "1.271,00".rjust(12)]),
}


def _erp(k, name="rechnung", **kw):
    return anlernen.Sitzung(erp_roh.rechnung(k.eingang / f"{name}.pdf", **kw), k)


def _erp_kopf(s):
    return next(z for z in s.zeilen if z.text.startswith("Menge"))


def _pos_werte(s):
    return [(p.menge, p.einzelpreis, p.gesamt) for p in s.positionen()]


ERP_SOLL = [
    (Decimal("10"), Decimal("1.25"), Decimal("12.50")),
    (Decimal("2"), Decimal("85"), Decimal("170")),
    (Decimal("1"), Decimal("1088.50"), Decimal("1088.50")),
]


@pytest.mark.parametrize("variante", ERP_VARIANTEN)
@pytest.mark.parametrize("rahmen", ["vorschlag", "knapp", "weit", "unter_kopfzeile"])
def test_erp_positionen_trennlinie_und_rahmen(k, variante, rahmen):
    """Trennlinie unter der Kopfzeile (gezeichnet oder „-----“/„=====“/„_____“), Leerzeilen, Falzmarken am Rand:
    alle drei Positionen, egal ob der Rahmen vorgeschlagen, knapp, großzügig (mit Summen) oder erst unter der
    Kopfzeile gezogen wurde."""
    s = _erp(k, variante, **ERP_VARIANTEN[variante])
    kopf = _erp_kopf(s)
    letzte = max(
        z.top for z in s.zeilen if any(w.t == "1.088,50" for w in z.woerter) and z.top < 500
    )
    if rahmen == "knapp":
        s.rahmen_setzen(0, 28, kopf.top - 3, 560, letzte + 12)
    elif rahmen == "weit":
        s.rahmen_setzen(0, 5, kopf.top - 3, 590, 620)
    elif rahmen == "unter_kopfzeile":
        s.rahmen_setzen(0, 28, kopf.top + 14, 560, letzte + 12)
    assert _pos_werte(s) == ERP_SOLL, s.tabellen_diagnose()
    assert s.positionen()[0].bezeichnung == "4711-0815 Sechskantschraube M8x40 DIN 933, verzinkt"
    assert not pdferkennung.TRENNLINIE.match(s.positionen()[-1].bezeichnung.split()[-1])
    assert s.tabelle_fehlt() == []
    assert not any(pdferkennung.TRENNLINIE.match(t) for t in s.pv()["ende"])


def test_erp_einzelpreis_drei_stellen_und_steuerkennzeichen(k):
    s = _erp(
        k,
        "preis3",
        zeilen=[
            erp_roh.pos("10", "Stk", "Schraube", "1,250", "12,50", " A"),
            erp_roh.pos("4", "Std", "Montage", "85", "340,00", " A"),
            erp_roh.pos("3", "ST", "Halter", "0,3333", "1,00*", " A"),
        ],
    )
    assert _pos_werte(s) == [
        (Decimal("10"), Decimal("1.250"), Decimal("12.50")),
        (Decimal("4"), Decimal("85"), Decimal("340.00")),
        (Decimal("3"), Decimal("0.3333"), Decimal("1.00")),
    ]


def test_escape_eckige_klammern_bleiben(k):
    """„\\[EURO\\]“ im Druck: Klammern bleiben, nichts rutscht nach links (pdfminer verwarf das Zeichen)."""
    s = _erp(k)
    kopf = _erp_kopf(s)
    toks = [w.t for w in kopf.woerter]
    assert toks == ["Menge", "ME", "Bezeichnung", "Preis", "[EURO]", "Betrag", "[EURO]"]
    betrag = kopf.woerter[toks.index("Betrag")]
    assert betrag.x0 == pytest.approx(30 + 6 * erp_roh.KOPF.index("Betrag"), abs=0.5)
    # ältere Vorlagen lernten die Kopfzeile ohne Klammern – sie passt weiter
    assert pdferkennung._passt_zeile(
        ["Menge", "ME", "Bezeichnung", "Preis", "EURO", "Betrag", "EURO"], kopf
    )


def test_alte_vorlage_mit_trennlinie_als_ende(k):
    """Ältere Vorlage lernte „-----“ als Tabellenende: dieselbe Linie unter der Kopfzeile beendet nichts."""
    s = _erp(
        k, "alt", zeilen=[erp_roh.trenn("-")] + S_ + [erp_roh.trenn("-")], nach=[" Vielen Dank."]
    )
    pv = s.pv()
    pv["ende"] = ["-" * 82]
    assert len(pdferkennung.positionen_auslesen(pv, s.zeilen)) == 3


def test_falzmarke_nicht_in_der_menge(k):
    s = _erp(k, "falz", falzmarken=(328.7, 352.7))
    assert s.tabelle.x0 > 20
    s.rahmen_setzen(
        0, 5, s.tabelle.top, s.tabelle.x1, s.tabelle.bottom
    )  # Rahmen schließt die Marke ein
    assert _pos_werte(s) == ERP_SOLL


# ---------------------------------------------------------------- Spalten als eigene Rahmen
def _wort(s, text):
    return min((w for w in s.woerter(0) if w.t == text), key=lambda w: w.top)


def test_spaltenrahmen_aus_linien_bleiben_erhalten(k):
    s = _erp(k)
    alt = list(s.tabelle.spalten)
    rs = s.spalten_aus_linien()
    assert [r[0] for r in rs] == alt  # bisherige Zuordnung verschwindet nicht
    assert s.pv()["spalten_fest"] and _pos_werte(s) == ERP_SOLL


def test_spalte_hinzufuegen_ersetzt_deckungsgleiche_und_kennt_ueberschrift(k):
    s = _erp(k)
    b = _wort(s, "Betrag")
    i = s.spalte_hinzufuegen(0, b.x0 - 4, b.top - 2, b.x1 + 44, b.top + 60)
    rs = s.tabelle.spaltenrahmen
    assert rs[i][0] == "gesamt" and [r[0] for r in rs].count("gesamt") == 1
    assert len(rs) == 5 and _pos_werte(s) == ERP_SOLL
    assert dict(s.spalten_zustand())["gesamt"] == 3


def test_spaltenrahmen_aendern_verschieben_entfernen(k):
    s = _erp(k)
    s.spalten_aus_linien()
    codes = lambda: [r[0] for r in s.tabelle.spaltenrahmen]  # noqa: E731
    i_m, i_p = codes().index("BT-129"), codes().index("BT-146")
    s.spalte_bedeutung(i_m, "BT-146")  # gleiche Bedeutung -> getauscht, nicht doppelt
    assert codes()[i_m] == "BT-146" and codes()[i_p] == "BT-129"
    s.spalte_bedeutung(i_m, "BT-129")
    rs = s.tabelle.spaltenrahmen
    links_nachbar = rs[i_p - 1][2]
    s.spalte_verschieben(i_p, 0, rs[i_p][2])  # nie in den Nachbarn hinein
    assert rs[i_p][1] == pytest.approx(links_nachbar + 1)
    s.spalte_entfernen(codes().index("BT-129"))
    s.spalte_entfernen(codes().index("BT-146"))
    assert s.tabelle_fehlt() == []  # Betrag trägt die Zeile
    assert [(p.menge, p.einzelpreis, p.gesamt) for p in s.positionen()][0] == (
        Decimal("1"),
        Decimal("12.50"),
        Decimal("12.50"),
    )
    s.spalte_entfernen(codes().index("gesamt"))
    assert s.tabelle_fehlt() == ["Spalte „Gesamt“ zuordnen"]
    while s.tabelle.spaltenrahmen:
        s.spalte_entfernen(0)
    b = _wort(s, "Betrag")
    s.spalte_hinzufuegen(0, b.x0 - 4, b.top - 2, b.x1 + 44, b.top + 60)
    assert codes() == ["gesamt"]  # gelöschte Spalten kommen nicht wieder


def test_spaltenrahmen_ohne_tabellenrahmen_und_nur_betrag(k):
    """Erst Spalten ziehen, ohne Tabellenrahmen: der erste Spaltenrahmen legt die Tabelle an; Menge fehlt
    -> Menge = Betrag ÷ Einzelpreis, Wörter außerhalb aller Spaltenrahmen zählen nicht."""
    s = _erp(k)
    s.tabelle = anlernen.Tabelle()
    kopf = _erp_kopf(s)
    letzte = max(
        z.top for z in s.zeilen if any(w.t == "1.088,50" for w in z.woerter) and z.top < 500
    )
    for text, rechts in (("Bezeichnung", 120), ("Preis", 48), ("Betrag", 44)):
        w = _wort(s, text)
        s.spalte_hinzufuegen(0, w.x0 - 4, kopf.top - 2, w.x0 + rechts, letzte + 10)
    assert [r[0] for r in s.tabelle.spaltenrahmen] == ["BT-153", "BT-146", "gesamt"]
    assert _pos_werte(s) == ERP_SOLL
    assert s.positionen()[0].bezeichnung.startswith("4711-0815")


def test_spaltenrahmen_in_vorlage_und_naechste_rechnung(k):
    s = _erp(k)
    s.absender = sitzung(k, "NB-26-1001").absender  # Briefkopf des Beispiels: fiktiver Verkäufer
    s.spalten_aus_linien()
    s.spalte_entfernen([r[0] for r in s.tabelle.spaltenrahmen].index("BT-130"))
    for f in s.fehlende():
        s.bestaetigen(f)
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    pv = v["positionen"]
    assert pv["spalten_fest"] and pv["anker_betrag"] and "BT-130" not in pv["spalten"]
    zeilen = [
        erp_roh.pos("3", "Stk", "Flachdichtung 20 mm", "2,10", "6,30"),
        erp_roh.pos("1,500", "Std", "Prüfung", "70,00", "105,00"),
    ]
    s2 = _erp(
        k,
        "zweite",
        zeilen=[erp_roh.trenn("=")] + zeilen,
        vektorlinie=True,
        beleg="26000043",
        nach=erp_roh.fuss("111,30"),
    )
    assert s2.tabelle.spaltenrahmen  # aus der Vorlage wiederhergestellt
    assert [(p.menge, p.gesamt) for p in pdferkennung.positionen_auslesen(pv, s2.zeilen)] == [
        (Decimal("3"), Decimal("6.30")),
        (Decimal("1.500"), Decimal("105.00")),
    ]


def test_tabellendiagnose_ohne_rechnungstext(k, caplog):
    s = _erp(k, "diag", vektorlinie=True, falzmarken=(340.7,), zeilen=[erp_roh.trenn("=")] + S_)
    s.tabelle.spalten = ["ignorieren"] * len(s.tabelle.spalten)
    s.tabelle.spalten[s.tabelle.spalten.index("ignorieren")] = "BT-153"
    import logging

    with caplog.at_level(logging.INFO, logger="fakturafalter.anlernen"):
        assert s.tabelle_fehlt()
    d = s.tabellen_diagnose()
    original = {w.t for z in s.zeilen for w in z.woerter}
    for wort in original:
        kern = re.sub(r"[^\w]", "", wort)
        # Spaltennamen in den Gründen („Betrag leer“) sind Text des Programms, nicht der Rechnung
        bedeutsam = (
            re.search(r"[^\W\d]", kern) or "," in wort or len(kern) >= 4
        )  # Koordinaten sind „10.0“
        if len(kern) >= 2 and bedeutsam and wort not in ("Menge", "Betrag"):
            assert not re.search(
                r"(?<![\w.,])" + re.escape(wort) + r"(?![\w])", d.split("\n", 1)[1]
            ), wort
    for zeile in d.splitlines()[1:]:
        if zeile.startswith("y "):
            masken = re.findall(r"\d+\.\d–\d+\.\d (\S+)", zeile)
            assert masken and all(re.fullmatch(r"[aA9\W_]+", m) for m in masken), zeile
    assert "Trennlinie" in d and "verworfen" in d and "Kopfzeile" in d
    s.tabelle.spalten = list(s.tabelle.spalten)
    s.tabelle_fehlt()
    s.rahmen_setzen(0, 28, s.tabelle.top, 560, s.tabelle.bottom)
    assert _pos_werte(s) == ERP_SOLL


# 0.4.3+hotfix1: „Positionsbetrag 0,00 weicht von Quelle 3,40 ab“ beim Speichern, obwohl Vorschau und Summen
# stimmten. Aufbau wie in der (anonymisierten) Diagnose: Textzeile unter der Kopfzeile, Preis mit „/1“ in der
# Lücke vor dem Betrag, eine Zeile ohne Einheit, Bezeichnungs-Fortsetzungen. Alle Inhalte erfunden.
PE_ZEILEN = [
    "",
    "                    Unser Lieferschein 26004711:",
    "",
    erp_roh.pos_pe("10", "Stück", "Kabelbinder schwarz", "0,34", "/1", "3,40"),
    "                    4711001",
    "",
    erp_roh.pos_pe("20", "Stück", "Unterlegscheibe M8 verzinkt", "0,85", "/1", "17,00"),
    "                    4711002",
    erp_roh.pos_pe("1", "", "Versandkostenpauschale", "12,50", "/1", "12,50"),
    "                    0815#Abholung-Lager",
]


def _pe_sitzung(k, name="pe", zeilen=PE_ZEILEN, netto="32,90", beleg="26000042"):
    n = Decimal(netto.replace(",", "."))
    ust = (n * Decimal("0.19")).quantize(Decimal("0.01"))
    de = lambda d: f"{d:.2f}".replace(".", ",")  # noqa: E731
    fuss = [
        " " * 50 + w.ljust(20) + b.rjust(12)
        for w, b in (("Nettobetrag", netto), ("USt 19 %", de(ust)), ("Endbetrag", de(n + ust)))
    ]
    s = _erp(
        k, name, kopf=erp_roh.KOPF_PE, zeilen=zeilen, falzmarken=(414.7,), nach=fuss, beleg=beleg
    )
    s.absender = sitzung(k, "NB-26-1001").absender
    for f in s.fehlende():
        s.bestaetigen(f)
    return s


def test_preiseinheit_am_preis_textzeile_und_zeile_ohne_einheit_speichern(k):
    s = _pe_sitzung(k)
    assert [(p.menge, p.einzelpreis, p.preiseinheit, p.gesamt) for p in s.positionen()] == [
        (Decimal("10"), Decimal("0.34"), Decimal("1"), Decimal("3.40")),
        (Decimal("20"), Decimal("0.85"), Decimal("1"), Decimal("17.00")),
        (Decimal("1"), Decimal("12.50"), Decimal("1"), Decimal("12.50")),
    ]
    assert "Lieferschein" not in " ".join(
        p.bezeichnung for p in s.positionen()
    )  # Textzeile: keine Position
    assert not s.betrag_abweichungen()
    # Zeile ohne Einheit: nicht still raten, sondern einmal wählen lassen (wie eine unbekannte Einheit)
    assert s.einheiten_offen() == {"Stück": "H87", pdferkennung.OHNE_EINHEIT: ""}
    assert s.tabelle_fehlt() == ["Unbekannte Einheit zuordnen"] and not s.fertig()
    s.tabelle.einheiten[pdferkennung.OHNE_EINHEIT] = "LS"
    assert s.fertig()
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    assert not any("weicht" in h for h in erg.hinweise)
    assert v["positionen"]["einheiten"][pdferkennung.OHNE_EINHEIT] == "LS"
    s2 = _pe_sitzung(
        k, "pe-zweite", beleg="26000043"
    )  # nächste Rechnung: aus der Vorlage, ohne Nachfrage
    assert s2.einheiten_offen()[pdferkennung.OHNE_EINHEIT] == "LS" and s2.fertig()
    erg2, _v2 = s2.speichern(k.pfad_datei)
    assert erg2.status == "ok", erg2.hinweise


def test_preis_gilt_fuer_1000_vorschau_meldet_was_speichern_meldet(k, caplog):
    """Stand „Preis gilt für“ auf 1000 (z. B. beim Überscrollen verstellt), stimmte die Summe der Beträge in der
    Vorschau trotzdem – erst Speichern rechnete 10 × 0,34 ÷ 1000 = 0,00. Die Vorschau rechnet jetzt genauso. Eine
    gedruckte Preiseinheit am Preis („/1“) gilt vor dem festen Wert; ohne sie greift der feste Wert."""
    import logging

    zeilen = [z.replace(" /1", "   ") for z in PE_ZEILEN]
    s = _pe_sitzung(k, "pe1000", zeilen)
    s.tabelle.einheiten[pdferkennung.OHNE_EINHEIT] = "LS"
    s.tabelle.preiseinheit = "1000"
    with caplog.at_level(logging.INFO, logger="fakturafalter.anlernen"):
        abw = s.betrag_abweichungen()
        assert abw[0] == (
            "1",
            Decimal("10"),
            Decimal("0.34"),
            Decimal("1000"),
            Decimal("0.00"),
            Decimal("3.40"),
        )
        assert s.tabelle_fehlt() and s.tabelle_fehlt()[0].startswith("Pos 1:") and not s.fertig()
    assert "Menge 10 × Preis 0.34 ÷ Preiseinheit 1000 = berechnet 0.00, Quelle 3.40" in caplog.text
    with caplog.at_level(logging.INFO, logger="fakturafalter.rechnen"):
        erg, v = s.speichern(k.pfad_datei)
    assert erg.status != "ok" and v is None
    assert (
        erg.hinweise[0] == "PRUEFEN: [Pos 1 BT-131] Positionsbetrag 0.00 weicht von Quelle 3.40 ab"
    )
    assert (
        "Pos 1: Menge 10 × Preis 0.34 ÷ Preiseinheit 1000 = berechnet 0.00, Quelle 3.40"
        in caplog.text
    )
    s2 = _pe_sitzung(k, "pe1000b")  # „/1“ gedruckt: gilt vor dem festen Wert
    s2.tabelle.einheiten[pdferkennung.OHNE_EINHEIT] = "LS"
    s2.tabelle.preiseinheit = "1000"
    assert not s2.betrag_abweichungen() and s2.fertig()


def test_zaehler_zaehlt_mit_zeile_ohne_einheit_bis_fuenf(k):
    """0.4.4: Mit einer Zeile ohne Einheit blieb der Zähler bei 0 – die Bewertung suchte die Einheit unter dem
    leeren Text statt unter „(ohne Einheit)“, die Position galt bei jeder Rechnung als korrigiert."""
    stand = []
    for i in range(6):
        s = _pe_sitzung(k, f"pe-folge-{i}", beleg=f"2600010{i}")
        if i == 0:
            s.tabelle.einheiten[pdferkennung.OHNE_EINHEIT] = "LS"
        assert s.fertig(), s.tabelle_fehlt()
        erg, v = s.speichern(k.pfad_datei)
        assert erg.status == "ok", erg.hinweise
        stand.append(s.fortschritt()[0])
        assert not s.zaehler_grund
    assert stand == [0, 1, 2, 3, 4, 5]


def test_position_ohne_preis_wird_position_zu_null(k):
    """0.4.4: Menge + Bezeichnung, aber weder Einzelpreis noch Betrag (z. B. ein Zuschlag, der diesmal nicht
    berechnet wird) -> Position 0,00 × Menge = 0,00 statt Abbruch. Ohne Menge bleibt eine Zeile Text."""
    zeilen = PE_ZEILEN + [
        "",
        erp_roh.pos_pe("1", "", "Mindermengenzuschlag entfällt", "", "", ""),
        "",
        erp_roh.pos_pe("", "", "Hinweis: Lieferung frei Haus", "", "", ""),
    ]
    s = _pe_sitzung(k, "ohne-preis", zeilen)
    pos = s.positionen()
    assert [(p.menge, p.einzelpreis, p.gesamt) for p in pos][-1] == (
        Decimal("1"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    assert pos[-1].bezeichnung.startswith("Mindermengenzuschlag entfällt")
    assert len(pos) == 4 and not any("Lieferschein" in p.bezeichnung for p in pos)
    s.tabelle.einheiten[pdferkennung.OHNE_EINHEIT] = "LS"
    assert not s.betrag_abweichungen() and s.fertig(), s.tabelle_fehlt()
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    import pikepdf

    with pikepdf.open(next(d for d in erg.dateien if str(d).endswith(".pdf"))) as pdf:
        xml = pdf.attachments["factur-x.xml"].get_file().read_bytes().decode("utf-8")
    assert "Mindermengenzuschlag" in xml and "<ram:ChargeAmount>0.00</ram:ChargeAmount>" in xml
    from fakturafalter import validierung

    if all(
        validierung.verfuegbar().values()
    ):  # lokal mit Mustang/KoSIT: auch die 0,00-Position ist gültig
        pdf_pfad = next(d for d in erg.dateien if str(d).endswith(".pdf"))
        pruef = validierung.pruefen([Path(pdf_pfad)])
        assert pruef and all(e.gueltig for e in pruef), [e.zeile() for e in pruef] + [
            f for e in pruef for f in e.fehler
        ]
    s2 = _pe_sitzung(k, "ohne-preis-2", zeilen, beleg="26000044")  # Vorlage liest sie wieder gleich
    assert s2.fertig()
    s2.speichern(k.pfad_datei)
    assert s2.fortschritt()[0] == 1 and not s2.zaehler_grund


def test_zaehler_grund_klartext():
    g = pdferkennung.zaehler_grund
    assert g({"BT-1": True, "BT-2": True, "positionen": True}) == ""
    assert (
        g({"BT-1": True, "BT-13": False, "kundennummer": False, "BT-51": False, "positionen": True})
        == ""
    )
    assert g({"BT-2": False, "positionen": True}) == "Rechnungsdatum geändert"
    assert g({"BT-44": False, "positionen": True}) == "Kundenname geändert"
    assert g({"kaeufer_block": False}) == "Anschrift des Kunden geändert"
    assert g({"BT-1": True, "positionen": False, "_position": 3}) == "Position 3 geändert"
    assert g({"positionen": False, "_position": 0}) == "Anzahl der Positionen geändert"
    assert not re.search(r"BT-\d", g({"BT-20": False}))


@pytest.mark.parametrize(
    "menge,me,preis,pe,soll_pe",
    [
        ("2", "Stk", "1,70", "/1", "1"),
        ("0,5", "Std", "6,80", "/1", "1"),
        ("1.000", "Stk", "0,0034", "", None),
        ("100", "Stk", "3,40", "/100", "100"),
        ("1.000", "Stk", "3,40", "/1000", "1000"),
        ("100", "Stk", "3,40", "je 100", "100"),
        ("100", "Stk", "3,40", "/ 100", "100"),
        # mit Währung: „3,40 € /10“, „3,40 €/10“, „3,40 EUR /100“, „3,40€/10“, „3,40 € /1“
        ("10", "Stk", "3,40 €", "/10", "10"),
        ("10", "Stk", "3,40", "€/10", "10"),
        ("100", "Stk", "3,40 EUR", "/100", "100"),
        ("10", "Stk", "3,40€/10", "", "10"),
        ("1", "Stk", "3,40 €", "/1", "1"),
    ],
)
def test_kleine_betraege_und_preiseinheit_am_preis(k, menge, me, preis, pe, soll_pe):
    zeilen = ["", erp_roh.pos_pe(menge, me, "Splint 2x20", preis, pe, "3,40")]
    s = _pe_sitzung(k, "klein", zeilen, "3,40")
    (p,) = s.positionen()
    assert p.gesamt == Decimal("3.40") and p.preiseinheit == (Decimal(soll_pe) if soll_pe else None)
    assert not s.betrag_abweichungen() and s.fertig()
    erg, _v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise


def test_preiseinheit_am_preis_angehaengt():
    from fakturafalter.pdferkennung import Wort, preiseinheit_abtrennen

    sp = {"BT-146": [Wort("3,40/100", 390, 438, 0, 0)], "gesamt": [Wort("3,40", 498, 522, 0, 0)]}
    assert preiseinheit_abtrennen(sp, "de") == Decimal("100") and sp["BT-146"][0].t == "3,40"
    sp = {
        "BT-146": [Wort("3,40", 390, 420, 0, 0)],
        "gesamt": [Wort("/0", 426, 438, 0, 0), Wort("3,40", 498, 522, 0, 0)],
    }
    assert preiseinheit_abtrennen(sp, "de") is None  # „/0“ ist keine Preiseinheit
    sp = {"BT-146": [Wort("3,40€/10", 390, 438, 0, 0)], "gesamt": [Wort("3,40", 498, 522, 0, 0)]}
    assert preiseinheit_abtrennen(sp, "de") == Decimal("10") and [w.t for w in sp["BT-146"]] == [
        "3,40",
        "€",
    ]
    sp = {"BT-146": [Wort("3,40", 390, 420, 0, 0), Wort("EUR/100", 424, 460, 0, 0)], "gesamt": []}
    assert preiseinheit_abtrennen(sp, "de") == Decimal("100") and [w.t for w in sp["BT-146"]] == [
        "3,40",
        "EUR",
    ]


@pytest.mark.parametrize(
    "zeilen, soll",
    [
        # z. Hd. geht ohne Vermerk in die Kontaktstelle (BT-56), Landzeile zählt nicht
        (
            [
                "Beispiel Planungs-",
                "und Ingenieurgesellschaft",
                "für Anlagenbau mbH",
                "z. Hd. Herrn Muster",
                "Musterweg 12",
                "12345 Musterstadt",
                "Deutschland",
            ],
            {
                "BT-44": "Beispiel Planungs- und Ingenieurgesellschaft für Anlagenbau mbH",
                "BT-56": "Herrn Muster",
                "BT-50": "Musterweg 12",
                "BT-53": "12345",
                "BT-52": "Musterstadt",
            },
        ),
        # Name ohne Rechtsform über zwei Zeilen
        (
            [
                "Gemeinschaftspraxis",
                "Dr. Muster und Dr. Beispiel",
                "Am Markt 3",
                "12345 Musterstadt",
            ],
            {
                "BT-44": "Gemeinschaftspraxis Dr. Muster und Dr. Beispiel",
                "BT-50": "Am Markt 3",
                "BT-53": "12345",
                "BT-52": "Musterstadt",
            },
        ),
        # Postfach statt Straße, c/o ist Adresszeile 2
        (
            ["Beispiel AG", "c/o Muster Verwaltung", "Postfach 12 34 56", "12345 Musterstadt"],
            {
                "BT-44": "Beispiel AG",
                "BT-51": "c/o Muster Verwaltung",
                "BT-50": "Postfach 12 34 56",
                "BT-53": "12345",
                "BT-52": "Musterstadt",
            },
        ),
        # leere Zeilen zwischen den Teilen zählen nicht
        (
            [
                "Beispiel Handels-",
                "gesellschaft mbH",
                "",
                "Musterweg 1",
                "",
                "12345 Musterstadt",
                "",
            ],
            {
                "BT-44": "Beispiel Handels- gesellschaft mbH",
                "BT-50": "Musterweg 1",
                "BT-53": "12345",
                "BT-52": "Musterstadt",
            },
        ),
        # Straße ohne Hausnummer: trotzdem die Zeile über PLZ/Ort
        (
            ["Beispiel KG", "Am Hafen", "12345 Musterstadt"],
            {"BT-44": "Beispiel KG", "BT-50": "Am Hafen", "BT-53": "12345", "BT-52": "Musterstadt"},
        ),
        # Absenderzeile und Anrede „Firma“ über dem Fenster; Abteilung ist Adresszeile 2
        (
            [
                "Muster GmbH · Musterweg 9 · 54321 Musterort",
                "Firma",
                "Beispiel KG",
                "Abteilung Buchhaltung",
                "Beispielallee 7",
                "12345 Musterstadt",
            ],
            {
                "BT-44": "Beispiel KG",
                "BT-51": "Abteilung Buchhaltung",
                "BT-50": "Beispielallee 7",
                "BT-53": "12345",
                "BT-52": "Musterstadt",
            },
        ),
    ],
)
def test_anschrift_von_unten(zeilen, soll):
    teile = pdferkennung.anschrift_teilen(zeilen)
    assert teile == soll
    assert not any("\n" in v for v in teile.values())


def _anschrift_pdf(pfad, zeilen):
    """Fiktive Rechnung mit Anschriftfeld aus ``zeilen`` (Fenster links oben)."""
    return erp_roh.rechnung(pfad, anschrift=zeilen)


def test_kaeufer_name_drei_zeilen_als_block(k, tmp_path):
    zeilen = [
        "Beispiel Planungs-",
        "und Ingenieurgesellschaft",
        "für Anlagenbau mbH",
        "z. Hd. Frau Muster",
        "Kundenweg 5",
        "12345 Kundenstadt",
    ]
    s = anlernen.Sitzung(_anschrift_pdf(tmp_path / "a.pdf", zeilen), k)
    assert (
        s.werte["BT-44"].wert == "Beispiel Planungs- und Ingenieurgesellschaft für Anlagenbau mbH"
    )
    assert not s.werte["BT-51"].wert
    assert s.rechnung().kaeufer.kontakt_name == "Frau Muster"  # Kontaktstelle BT-56, ohne „z. Hd.“
    assert s.werte["BT-50"].wert == "Kundenweg 5" and s.werte["BT-53"].wert == "12345"
    assert pdferkennung.ANSCHRIFT_BLOCK in s.bereiche()


@pytest.mark.parametrize(
    "bestellnummer, soll",
    [
        ("", ""),  # leer: nicht das Datum zwei Zeilen tiefer
        ("05.10.2026", ""),  # Datum ist keine Bestellnummer
        ("1.234,50", ""),  # Betrag auch nicht
        ("B-4711/26", "B-4711/26"),
    ],
)
def test_optionale_bestellnummer_nur_rechts_daneben(k, bestellnummer, soll):
    s = anlernen.Sitzung(_erp_pdf(k.eingang, bestellnummer=bestellnummer), k)
    assert s.werte["BT-13"].wert == soll
    assert s.werte["kundennummer"].wert == "40711"
    assert s.werte["BT-2"].wert == "05.10.2026"  # Pflichtfelder wie bisher


def test_nummer_passt():
    p = pdferkennung.nummer_passt
    assert p("B-4711") and p("40711") and p("PO 2026-17")
    assert (
        not p("05.10.2026")
        and not p("1.234,50")
        and not p("19 %")
        and not p("Datum:")
        and not p("Muster")
    )


# -- Positionen über mehrere Seiten (fiktive Drucke) ------------------------------------------------
_S1, _S2 = erp_roh.STANDARD[:2], erp_roh.STANDARD[2:]
MEHRSEITIG = {
    "kopf_wiederholt": {},
    "ohne_kopf": dict(kopf_wiederholen=False),
    "ohne_briefkopf": dict(kopf_wiederholen=False, briefkopf_folgeseiten=False),
    "zwischensumme_trennlinie": dict(trennlinie=True, uebertrag="Zwischensumme"),
    "nur_trennlinie": dict(uebertrag="", trennlinie=True, kopf_wiederholen=False),
    "ohne_uebertrag": dict(uebertrag="", kopf_wiederholen=False),
}


@pytest.mark.parametrize("variante", MEHRSEITIG)
def test_positionen_ueber_zwei_seiten(k, variante):
    s = anlernen.Sitzung(
        erp_roh.rechnung_mehrseitig(
            k.eingang / f"m-{variante}.pdf", [_S1, _S2], **MEHRSEITIG[variante]
        ),
        k,
    )
    assert _pos_werte(s) == ERP_SOLL
    assert "DIN 933" in s.positionen()[0].bezeichnung  # Zusatzzeile bleibt an ihrer Position
    assert not any("Übertrag" in p.bezeichnung or "Seite" in p.bezeichnung for p in s.positionen())
    assert not s.tabelle_fehlt()
    assert s.pv()["ende"] == ["Nettobetrag"]  # Ende an der Summe, nicht am Übertrag


@pytest.mark.parametrize(
    "variante", ["kopf_wiederholt", "ohne_kopf", "ohne_briefkopf", "nur_trennlinie"]
)
def test_vorlage_liest_drei_seiten(k, variante):
    kw = MEHRSEITIG[variante]
    s = anlernen.Sitzung(erp_roh.rechnung_mehrseitig(k.eingang / "lern.pdf", [_S1, _S2], **kw), k)
    pv = s.pv()
    seiten = [
        [erp_roh.pos("3", "Stk", "Flachdichtung 20 mm", "2,10", "6,30")],
        [
            erp_roh.pos("1,500", "Std", "Prüfung", "70,00", "105,00"),
            erp_roh.pos("2", "Stk", "Dichtring", "1,00", "2,00"),
        ],
        [erp_roh.pos("4", "Stk", "Klemme", "0,50", "2,00")],
    ]
    s2 = anlernen.Sitzung(
        erp_roh.rechnung_mehrseitig(
            k.eingang / "drei.pdf", seiten, beleg="26000043", nach=erp_roh.fuss("115,30"), **kw
        ),
        k,
    )
    assert [(p.menge, p.gesamt) for p in pdferkennung.positionen_auslesen(pv, s2.zeilen)] == [
        (Decimal("3"), Decimal("6.30")),
        (Decimal("1.500"), Decimal("105.00")),
        (Decimal("2"), Decimal("2.00")),
        (Decimal("4"), Decimal("2.00")),
    ]


def test_uebertrag_erkennung():
    z = lambda t: pdferkennung.Zeile(0, 0, [pdferkennung.Wort(w, 0, 1, 0, 0, 1) for w in t.split()])  # noqa: E731
    assert pdferkennung.ist_uebertrag(z("Übertrag 1.000,00"))
    assert pdferkennung.ist_uebertrag(z("Zwischensumme 99,00"))
    assert not pdferkennung.ist_uebertrag(z("Fortsetzungsfeder Typ A"))
    assert not pdferkennung.ist_uebertrag(z("1 Stk Wartung Fortsetzung 10,00"))


@pytest.mark.parametrize("variante", ["kopf_wiederholt", "ohne_kopf"])
def test_tabellen_bereiche_auf_folgeseite(k, variante):
    """Der Tabellenrahmen gilt auf jeder Seite: auf Seite 2 liegt der Bereich um die dort gelesenen Positionen."""
    s = anlernen.Sitzung(
        erp_roh.rechnung_mehrseitig(
            k.eingang / f"b-{variante}.pdf", [_S1, _S2], **MEHRSEITIG[variante]
        ),
        k,
    )
    b = s.tabellen_bereiche()
    assert set(b) == {0, 1} and b[0] == (s.tabelle.top, s.tabelle.bottom)
    pos2 = [
        z for z in s.zeilen if z.seite == 1 and re.search(r"Montage vor Ort|Werkzeugwagen", z.text)
    ]
    assert len(pos2) == 2 and all(b[1][0] <= z.top <= b[1][1] for z in pos2)
    assert not any(
        b[1][0] <= z.top <= b[1][1]
        for z in s.zeilen
        if z.seite == 1 and re.search(r"Nettobetrag|Seite \d", z.text)
    )


SKONTO = [" zahlbar bis 08.11.26 bei 3 % Skonto (1,17 EUR)", " bis 28.11.2026 ohne Abzug"]


def _skonto_sitzung(k, name="skonto", bedingung=SKONTO, beleg="26000042"):
    fuss = [
        " " * 50 + w.ljust(20) + b.rjust(12)
        for w, b in (("Nettobetrag", "32,90"), ("USt 19 %", "6,25"), ("Endbetrag", "39,15"))
    ]
    s = _erp(
        k,
        name,
        kopf=erp_roh.KOPF_PE,
        zeilen=PE_ZEILEN,
        falzmarken=(414.7,),
        nach=fuss + [""] + bedingung,
        beleg=beleg,
    )
    s.absender = sitzung(k, "NB-26-1001").absender
    for f in s.fehlende():
        s.bestaetigen(f)
    s.tabelle.einheiten[pdferkennung.OHNE_EINHEIT] = "LS"
    return s


def test_zahlungsbedingung_mit_skonto_zweizeilig(k):
    """0.4.4: Skonto + Netto-Datum über zwei Zeilen -> BT-20 = Originaltext (verbunden), BT-9 = „ohne Abzug“-Datum;
    der Assistent bietet BT-20 als Rahmen an, und die Vorlage liest ihn bei der nächsten Rechnung wieder."""
    s = _skonto_sitzung(k)
    vs = s.werte["BT-20"]
    assert vs.wert == "zahlbar bis 08.11.26 bei 3 % Skonto (1,17 EUR) bis 28.11.2026 ohne Abzug"
    assert vs.bereich and vs.hinweis.startswith("Empfohlen")
    assert s.zahlung_hinweis() == ""  # 3 % von 39,15 = 1,17: passt
    s.bestaetigen("BT-20")
    assert s.werte["BT-20"].status == "erkannt" and "BT-20" in s.bereiche()
    r = s.rechnung()
    assert r.zahlung.bedingungen == vs.wert and str(r.zahlung.faellig) == "2026-11-28"
    assert not any(h.feld == "BT-20" for h in r.hinweise)
    erg, _v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    import pdfplumber
    import pikepdf

    pdf_pfad = next(d for d in erg.dateien if str(d).endswith(".pdf"))
    with pikepdf.open(pdf_pfad) as pdf:
        xml = pdf.attachments["factur-x.xml"].get_file().read_bytes().decode("utf-8")
    assert "3 % Skonto (1,17 EUR) bis 28.11.2026 ohne Abzug</ram:Description>" in xml
    assert "20261128" in xml and "ohne Abzug." not in xml.replace(
        "ohne Abzug</", ""
    )  # kein Profiltext
    with pdfplumber.open(pdf_pfad) as d:
        sicht_text = " ".join(p.extract_text() or "" for p in d.pages)
    assert "Fällig am" not in sicht_text  # Datum steht schon im Text
    s2 = _skonto_sitzung(k, "skonto-2", beleg="26000043")
    assert s2.werte["BT-20"].status == "erkannt" and s2.werte["BT-20"].wert == vs.wert


def test_skonto_betrag_falsch_ist_hinweis(k):
    s = _skonto_sitzung(
        k,
        "skonto-falsch",
        [" zahlbar bis 08.11.26 bei 3 % Skonto (2,00 EUR)", " bis 28.11.2026 ohne Abzug"],
    )
    assert "passt nicht" in s.zahlung_hinweis()
    s.bestaetigen("BT-20")
    r = s.rechnung()
    assert any(h.stufe == "info" and "Skonto" in h.text for h in r.hinweise)
    assert r.status != "fehler"


def test_skonto_ohne_bt20_kein_profiltext(k):
    """Druck nennt Skonto, BT-20 leer: der Profil-Standardtext „… ohne Abzug“ darf nicht still ins XML."""
    s = _skonto_sitzung(k, "skonto-leer")
    s.setzen("BT-20", "")
    assert "Skonto" in s.zahlung_hinweis()
    r = s.rechnung()
    assert r.zahlung.bedingungen == "" and r.zahlung.faellig is None
    erg, _v = s.speichern(k.pfad_datei)
    assert erg.status != "ok"


# ---------------------------------------------------------------- Anschriftfeld: PLZ und Ort in einer Zeile (0.4.5)
def _fenster_pdf(pfad: Path, anschrift, *, rechts=True, seiten=1) -> Path:
    """Fiktive Text-PDF mit Anschriftfeld: ``anschrift`` = [(top, x, Text[, Schrift, Größe])]; rechts daneben
    Belegangaben wie im ERP-Druck („Versanddatum :“ in der Zeile von PLZ/Ort). Weitere Seiten ohne Anschrift."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(pfad), pagesize=A4)
    h = A4[1]

    def t(x, top, text, font="Courier", groesse=10):
        c.setFont(font, groesse)
        c.drawString(x, h - top - 0.8 * groesse, text)

    for n in range(seiten):
        if n == 0:
            for top, x, text, *schrift in anschrift:
                t(x, top, text, *schrift)
            if rechts:
                for text, top in (
                    ("Versanddatum :", 195),
                    ("Kunde: 40711", 219),
                    ("Datum: 05.10.2026", 231),
                ):
                    t(360, top, text)
            t(42, 255, "Rechnung")
            t(432, 255, "Beleg: 26000042", "Courier-Bold")
        t(42, 315, "Menge ME  Bezeichnung                    Preis EURO   Betrag EURO")
        t(42, 700, "zahlbar bis 04.11.2026 ohne Abzug.")
        c.showPage()
    c.save()
    return pfad


_NAME = [(147, 42, "Beispiel Werkzeugbau"), (159, 42, "Handels GmbH"), (171, 42, "Musterweg 12")]
_SOLL = {
    "BT-44": "Beispiel Werkzeugbau Handels GmbH",
    "BT-50": "Musterweg 12",
    "BT-53": "12345",
    "BT-52": "Musterstadt",
}


@pytest.mark.parametrize(
    "plz_ort",
    [
        [(195, 42, "12345 Musterstadt")],
        [(195, 42, "12345"), (195.4, 78, "Musterstadt")],  # Grundlinie minimal versetzt
        [(195, 42, "12345"), (193.6, 78, "Musterstadt")],
        [(195, 42, "12345"), (197.5, 78, "Musterstadt")],  # 2,5 pt tiefer
        [(195, 42, "12345"), (192.5, 78, "Musterstadt")],
        [
            (195, 42, "12345"),
            (193.2, 78, "Musterstadt", "Helvetica", 12),
        ],  # andere Schriftgröße, kleineres top
        [(195, 42, "12345"), (195, 140, "Musterstadt")],  # großer Abstand (Tabulator)
        [(195, 42, "D-12345 Musterstadt")],
    ],
)
def test_anschrift_plz_und_ort_in_einer_zeile(k, tmp_path, plz_ort):
    soll = dict(_SOLL)
    pdf = _fenster_pdf(tmp_path / "a.pdf", _NAME + plz_ort)
    s = anlernen.Sitzung(pdf, k)
    assert {f: s.werte[f].wert for f in soll} == soll  # Vorschlag ohne Rahmen
    for rahmen in (
        (36, 130, 300, 210),  # weiter Rahmen
        (36, 140, 100, 207),
    ):  # eng: Ort ragt rechts hinaus
        assert anlernen.Sitzung(pdf, k).anschrift_setzen(0, rahmen) == soll, rahmen


def test_anschrift_wort_am_rechten_rand_angeschnitten(k, tmp_path):
    pdf = _fenster_pdf(tmp_path / "a.pdf", _NAME + [(195, 42, "12345 Frankfurt am Main")])
    teile = anlernen.Sitzung(pdf, k).anschrift_setzen(
        0, (36, 140, 120, 207)
    )  # Rahmen endet in „Frankfurt“
    assert (teile["BT-53"], teile["BT-52"], teile["BT-50"]) == (
        "12345",
        "Frankfurt am Main",
        "Musterweg 12",
    )
    assert teile["BT-44"] == "Beispiel Werkzeugbau Handels GmbH"  # Name nicht abgeschnitten


@pytest.mark.parametrize(
    "absender",
    [
        "Muster Absender GmbH · Absenderweg 1 · 99999 Absenderstadt",
        "Muster Absender GmbH, Absenderweg 1, 99999 Absenderstadt",
        "Muster Absender GmbH - Absenderweg 1 - 99999 Absenderstadt",
    ],
)
def test_anschrift_absenderzeile_klein_im_rahmen(k, tmp_path, absender):
    pdf = _fenster_pdf(
        tmp_path / "a.pdf",
        [(135, 42, absender, "Helvetica", 6)] + _NAME + [(195, 42, "12345 Musterstadt")],
    )
    s = anlernen.Sitzung(pdf, k)
    assert {f: s.werte[f].wert for f in _SOLL} == _SOLL
    assert anlernen.Sitzung(pdf, k).anschrift_setzen(0, (36, 125, 300, 210)) == _SOLL


@pytest.mark.parametrize(
    "name",
    [
        ["Kunde KG"],
        ["Beispiel Werkzeugbau", "Handels GmbH"],
        ["Beispiel Planungs- und", "Ingenieurgesellschaft mbH", "z. Hd. Frau Muster"],
    ],
)
@pytest.mark.parametrize("leer", [False, True])
def test_anschrift_name_ein_bis_drei_zeilen(k, tmp_path, name, leer):
    """Von unten: PLZ Ort, (Leerzeile), Straße, darüber 1–3 Namenszeilen mit Leerzeichen verbunden."""
    plz_top = 195
    str_top = plz_top - (24 if leer else 12)
    zeilen = [(str_top - 12 * (len(name) - i), 42, n) for i, n in enumerate(name)]
    zeilen += [(str_top, 42, "Kundenweg 5"), (plz_top, 42, "54321 Neustadt")]
    pdf = _fenster_pdf(tmp_path / "a.pdf", zeilen, seiten=2)
    soll = {
        "BT-44": " ".join(name[:2]),
        "BT-50": "Kundenweg 5",
        "BT-53": "54321",
        "BT-52": "Neustadt",
    }
    s = anlernen.Sitzung(pdf, k)
    assert {f: s.werte[f].wert for f in soll} == soll
    if len(name) == 3:  # „z. Hd. …“ geht in die Kontaktstelle
        soll["BT-56"] = "Frau Muster"
    assert anlernen.Sitzung(pdf, k).anschrift_setzen(0, (36, 100, 300, 210)) == soll


def test_vorlage_anschrift_im_naechsten_druck_eine_zeile_laenger(k, tmp_path):
    """Gemeldet (0.4.4): Vorlage mit Rahmen aus Rechnung A; Rechnung B hat eine Namenszeile mehr, das Feld wächst
    nach unten. Die Zeile „PLZ Ort“ lag unter dem gelernten Rahmen: PLZ kam aus der Suche, als Ort stand die
    Straße und als Straße die letzte Namenszeile. Jetzt: unterste Zeile muss „PLZ Ort“ sein, sonst wird
    ein Stück tiefer gesucht."""
    a = _fenster_pdf(k.eingang / "a.pdf", _NAME + [(195, 42, "12345 Musterstadt")])
    s = anlernen.Sitzung(a, k)
    seite, rahmen, block = s.bereiche()[pdferkennung.ANSCHRIFT_BLOCK]
    assert block and rahmen[3] < 207 + 5  # Rahmen endet an A's Zeile „PLZ Ort“
    regel = pdferkennung.bereich_regel(
        pdferkennung.ANSCHRIFT_BLOCK, s.zeilen, seite, rahmen, set(), True
    )
    b = _fenster_pdf(
        tmp_path / "b.pdf",
        [
            (147, 42, "Kunde"),
            (159, 42, "Planungs- und Ingenieur-"),
            (171, 42, "gesellschaft mbH"),
            (183, 42, "Kundenweg 5"),
            (207, 42, "54321 Neustadt-Süd"),
        ],
        rechts=False,
    )
    s2 = anlernen.Sitzung(b, k)
    soll = {
        "BT-44": "Kunde Planungs- und Ingenieur- gesellschaft mbH",
        "BT-50": "Kundenweg 5",
        "BT-53": "54321",
        "BT-52": "Neustadt-Süd",
    }
    assert {f: t for f, (t, _) in pdferkennung.anschrift_auslesen(regel, s2.zeilen).items()} == soll


def test_vorlage_anschrift_ohne_plz_unten_liest_nichts(k, tmp_path):
    """Ohne Zeile „PLZ Ort“ unten im (verlängerten) Rahmen liefert der Block nichts – nie die Straße als Ort."""
    s = anlernen.Sitzung(_fenster_pdf(tmp_path / "a.pdf", _NAME, rechts=False), k)
    assert (
        pdferkennung.anschrift_auslesen({"rahmen": [36, 140, 300, 185], "seite": 0}, s.zeilen) == {}
    )
    assert (
        anlernen.Sitzung(
            _fenster_pdf(tmp_path / "b.pdf", _NAME + [(195, 42, "12345 Musterstadt")]), k
        ).anschrift_setzen(0, (36, 140, 300, 185))
        == _SOLL
    )  # Zeile „PLZ Ort“ knapp unter dem Rahmen


def test_anschrift_diagnose_ohne_inhalt(k, tmp_path, caplog):
    pdf = _fenster_pdf(tmp_path / "a.pdf", _NAME + [(195, 42, "12345"), (195, 140, "Musterstadt")])
    with caplog.at_level("INFO", logger="fakturafalter.pdferkennung"):
        anlernen.Sitzung(pdf, k).anschrift_setzen(0, (36, 140, 100, 207))
    log = caplog.text
    assert "Anschrift" in log and "→ plz" in log and "→ strasse" in log and "→ name" in log
    assert "„99999 Xxxxxxxxxxx“" in log and "großem Abstand" in log
    assert not re.search(r"Muster|Beispiel|12345", log)  # nur x/X/9, keine Inhalte


@pytest.mark.parametrize(
    "kopf, spalte",
    [
        ("Gesamtpreis", "gesamt"),
        ("Gesamtpreis EUR", "gesamt"),
        ("Gesamt-Preis", "gesamt"),
        ("Gesamtbetrag", "gesamt"),
        ("Pos.-Gesamt", "gesamt"),
        ("Pos. Gesamt", "gesamt"),
        ("Preis gesamt", "gesamt"),
        ("Gesamt", "gesamt"),
        ("Betrag", "gesamt"),
        ("Einzelpreis", "BT-146"),
        ("Preis", "BT-146"),
        ("Einzelbetrag", "BT-146"),
        ("Gesamtmenge", "BT-129"),
        ("Pos.", "BT-126"),
        ("Pos.-Nr.", "BT-126"),
    ],
)
def test_kopfwort_gesamtpreis_vor_preis_und_pos(kopf, spalte):
    """Regression: „Gesamtpreis“ wurde als Einzelpreis (BT-146) erkannt, „Pos.-Gesamt“ als Positionsnummer."""
    assert anlernen._spalte_fuer(kopf) == spalte


def test_kaltstart_liest_tabelle_mit_gesamtpreis_spalte(k):
    """Regression: Kopf „… Einzelpreis Gesamtpreis“ ohne Gesamt-Spalte -> keine Tabelle, 0 Positionen."""
    import json

    fik = Path(__file__).resolve().parent / "daten" / "fiktiv"
    soll = json.loads(
        (fik / "Referenzdaten" / "Rechnung_001_RE-2026-00125.json").read_text(encoding="utf-8")
    )
    k.pdf_profile = []
    s = anlernen.Sitzung(fik / "Rechnungen" / "Rechnung_001_RE-2026-00125.pdf", k)
    pos = s.rechnung().positionen
    assert len(pos) == len(soll["positions"])
    assert [p.netto for p in pos] == [Decimal(p["total"]) for p in soll["positions"]]
    assert sum(p.netto for p in pos) == Decimal(soll["totals"]["net"])


def _fiktiv(nr: str):
    import json

    fik = Path(__file__).resolve().parent / "daten" / "fiktiv"
    pdf = next((fik / "Rechnungen").glob(f"*{nr}.pdf"))
    soll = json.loads((fik / "Referenzdaten" / (pdf.stem + ".json")).read_text(encoding="utf-8"))
    return pdf, soll


@pytest.mark.parametrize("nr", ["00171", "00172", "00173"])
def test_folgeseite_tabelle_tiefer_als_rahmen(k, nr):
    """Regression: Auf Folgeseiten reicht die Tabelle tiefer als der Rahmen auf Seite 1. Die letzten Zeilen
    vor dem „Übertrag“ (00172 Pos. 32/33, 00173 Pos. 32 „Fixpreis“, 00171 letzte Bezeichnungszeile Pos. 35)
    gingen als „unter dem Tabellenrahmen“ verloren."""
    pdf, soll = _fiktiv(nr)
    k.pdf_profile = []
    s = anlernen.Sitzung(pdf, k)
    pos = s.rechnung().positionen
    assert len(pos) == len(soll["positions"])
    assert [(p.netto or 0) for p in pos] == [Decimal(p["total"] or 0) for p in soll["positions"]]
    assert [p.bezeichnung for p in pos] == [" ".join(p["description"]) for p in soll["positions"]]
    assert sum(p.netto for p in pos) == Decimal(soll["totals"]["net"])
    t = s.tabelle
    assert s.tabellen_bereiche()[t.seite] == (
        t.top,
        t.bottom,
    )  # gezogener Rahmen bleibt unverändert


def test_folgeseite_abgesetzte_zeile_bleibt_draussen(k):
    """Gegenprobe: Steht eine Zeile auf der Folgeseite mit Lücke unter dem Rahmen und ohne Übertrag oder Summe
    darunter, gehört sie nicht zur Tabelle. Die Summe geht dann nicht auf, und das wird als „prüfen“ gemeldet."""
    from dataclasses import replace

    pdf, soll = _fiktiv("00172")
    k.pdf_profile = []
    s = anlernen.Sitzung(pdf, k)
    pv = s.pv()
    ab = next(z for z in s.zeilen if z.seite == 1 and z.text.startswith("2 Stk. Nachbearbeitung"))
    zeilen = []
    for z in s.zeilen:  # ab Pos. 33 auf Seite 2 alles 60 pt tiefer, Übertrag entfernt
        if z.seite == 1 and z.top >= ab.top:
            if pdferkennung.ist_uebertrag(z):
                continue
            z = replace(z, top=z.top + 60, woerter=[replace(w, top=w.top + 60) for w in z.woerter])
        zeilen.append(z)
    pos = pdferkennung.positionen_auslesen(pv, zeilen)
    assert len(pos) == len(soll["positions"]) - 1
    assert "Nachbearbeitung 895781" not in [p.bezeichnung for p in pos]


# ---------------------------------------------------------------- Zahlungsbaustein BT-20 (Schritt 4)
def _fiktiv_anlernen(k, nrs=("00125", "00126"), zone=False):
    """Wie der Benchmark „fiktiv-angelernt“: Belege im Assistenten anlernen (nur Tabellenrahmen ziehen, BT-20
    nicht anfassen); ``zone``: Bereich „Zahlungsbedingungen“ wie vorgeschlagen übernehmen. -> Profil"""
    import copy
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import benchmark

    k.pdf_profile = []
    prof = None
    for nr in nrs:
        s = anlernen.Sitzung(_fiktiv(nr)[0], k)
        if s.vorlage is None:
            benchmark.tabelle_korrigieren(s)
        if zone and "zahlung" not in s.zonen:
            zv = s.zone_vorschlag("zahlung")
            s.zone_setzen("zahlung", zv[0], zv[1])
        r = s.rechnung()
        if prof is None:
            prof = anlernen.profil_daten(s.absender, anlernen.ziel_tage(s.werte["BT-20"].wert))
            k.pdf_profile = [prof]
            s.profil = prof
        vl, _ = pdferkennung.lernen(
            r,
            s.zeilen,
            prof,
            s.vorlage,
            pdferkennung.einstellungen(prof),
            pv_vorgabe=s.pv(),
            stellen=s.stellen(),
            bereiche=s.bereiche(),
            flaechen=copy.deepcopy(s.zonen),
        )
        pdferkennung.vorlage_speichern(vl, prof)
    prof["pdf_erkennung"] = {"nur_pdf": True, "nur_pdf_ab": 1}
    return prof


def _fiktiv_lesen(k, prof, nr):
    from fakturafalter import adapter_pdf

    pdf, soll = _fiktiv(nr)
    r, grund = pdferkennung.nur_pdf(
        pdf, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), [prof], k
    )
    assert r is not None, grund
    return r, soll


def _bt20_soll(soll):
    return f"Zahlbar innerhalb von {soll['payment_days']} Tagen bis {soll['payment']['due_date']} ohne Abzug"


def test_bt20_baustein_ohne_rahmen_angelernt(k):
    """Regression: Zahlungsbedingung unter der Überschrift „Zahlungsbedingungen“, beim Anlernen nicht angefasst
    (Vorschlag „prüfen“). Die Vorlage lernt den Baustein trotzdem als Rahmen mit der Überschrift als Anker und liest
    bei Skonto-Rechnungen beide Zeilen – vorher Profiltext ohne Datum bzw. leer mit „prüfen“."""
    s = anlernen.Sitzung(_fiktiv("00125")[0], k)
    assert (
        s.werte["BT-20"].wert == "Zahlbar innerhalb von 30 Tagen bis 02.09.2026 ohne Abzug."
    )  # ohne Überschrift
    prof = _fiktiv_anlernen(k)
    regel = pdferkennung.vorlagen_laden(prof)[0]["felder"]["BT-20"]
    assert regel["lage"] == "bereich" and regel["anker"] == ["Zahlungsbedingungen"]
    for nr in ("00133", "00134"):  # mit Skonto (zweizeilig) / ohne
        r, soll = _fiktiv_lesen(k, prof, nr)
        assert _bt20_soll(soll) in r.zahlung.bedingungen
        assert r.zahlung.faellig.strftime("%d.%m.%Y") == soll["payment"]["due_date"]
        if soll.get("discount_percent"):
            assert "Skonto" in r.zahlung.bedingungen
        assert not any(h.feld == "BT-20" and h.stufe == "pruefen" for h in r.hinweise)


@pytest.mark.parametrize("oben", [697.3, 649.7])
def test_bt20_alte_vorlage_rahmen_wandert_nicht_in_fusszeile(k, oben):
    """Regression Protokoll 00133/145/146/149/150/151/152/155/159: alte Vorlage mit Bereich „Zahlungsbedingungen“
    (Bezug = Tabellenende der ersten Rechnung) und BT-20-Rahmen ohne Anker. Bei langer Tabelle wanderte der Rahmen
    mit dem Tabellenende in die Fußzeile: BT-20 leer oder Fußzeilentext („GF: …“) ohne Hinweis."""
    prof = _fiktiv_anlernen(k, zone=True)
    v = pdferkennung.vorlagen_laden(prof)[0]
    v["bereiche"]["zahlung"] = {
        "rahmen": [51.9, 697.3, 281.9, 726.3],
        "seiten": "alle",
        "bezug": 476.8,
    }
    v["felder"]["BT-20"] = {
        "typ": "text",
        "lage": "bereich",
        "seite": 0,
        "rahmen": [51.9, oben, 281.9, 726.3],
    }
    pdferkennung.vorlage_speichern(v, prof)
    for nr in ("00145", "00146", "00159"):  # Tabellenende 643.5 / 631.6 / 631.6
        r, soll = _fiktiv_lesen(k, prof, nr)
        assert _bt20_soll(soll) in r.zahlung.bedingungen
        assert not re.search(r"GF:|FIKTIVE|Alberon", r.zahlung.bedingungen)
        assert r.zahlung.faellig.strftime("%d.%m.%Y") == soll["payment"]["due_date"]


def test_bt20_regel_liest_anderes_baustein_zur_pruefung(k):
    """Liest die angelernte Regel nichts, das nach Zahlungsbedingung klingt, kommt der Zahlungsbaustein aus dem
    Druck – mit „prüfen“, nie still; vorher BT-20 leer (BR-CO-25)."""
    prof = _fiktiv_anlernen(k)
    v = pdferkennung.vorlagen_laden(prof)[0]
    v["felder"]["BT-20"] = {
        "typ": "text",
        "lage": "bereich",
        "seite": 0,
        "rahmen": [51.9, 780.0, 281.9, 800.0],
    }
    pdferkennung.vorlage_speichern(v, prof)
    r, soll = _fiktiv_lesen(k, prof, "00134")
    assert _bt20_soll(soll) in r.zahlung.bedingungen
    assert any(
        h.feld == "BT-20" and h.stufe == "pruefen" and "angelernten Stelle" in h.text
        for h in r.hinweise
    )


def test_zahlungsbaustein_reine_ueberschrift(k):
    """Nur die Überschrift „Zahlungsbedingungen“ ohne Text darunter ist kein Zahlungsbaustein."""
    w = pdferkennung.Wort("Zahlungsbedingungen", 50, 150, 100, 0, 110)
    z = [pdferkennung.Zeile(0, 100, [w], [[w]])]
    assert pdferkennung.zahlungsbaustein(z) is None


def _z(*teile, top=100):
    ws, x = [], 50
    for txt in teile:
        w = pdferkennung.Wort(txt, x, x + 7 * len(txt), top, 0, top + 10)
        ws.append(w)
        x = w.x1 + 4
    return pdferkennung.Zeile(0, top, ws, [ws])


def test_faelligkeitsdatum_kein_zahlungsbaustein(k):
    """„Fälligkeitsdatum 11.11.2026“ ist die Beschriftung von BT-9, nicht BT-20/Skonto."""
    feld = _z("Fälligkeitsdatum", "11.11.2026", top=100)
    echte = _z(
        "Zahlungsbedingungen", "2", "%", "Skonto", "8", "Tage,", "30", "Tage", "netto", top=120
    )
    assert pdferkennung.zahlungsbaustein([feld]) is None
    s, ws = pdferkennung.zahlungsbaustein([feld, echte])
    assert "Skonto" in pdferkennung.zahlungsbaustein_text(ws)
    assert "Fälligkeitsdatum" not in pdferkennung.zahlungsbaustein_text(ws)
    # Überschrift und Wert in einer Zeile, großer Abstand (zwei Abschnitte)
    k = pdferkennung.Wort("Zahlungsbedingungen", 50, 160, 200, 0, 210)
    v = pdferkennung.Wort("30", 320, 335, 200, 0, 210)
    v2 = pdferkennung.Wort("Tage", 338, 360, 200, 0, 210)
    v3 = pdferkennung.Wort("netto", 363, 400, 200, 0, 210)
    z = pdferkennung.Zeile(0, 200, [k, v, v2, v3], [[k], [v, v2, v3]])
    _, ws2 = pdferkennung.zahlungsbaustein([z])
    assert pdferkennung.zahlungsbaustein_text(ws2) == "30 Tage netto"


def test_zahlungsbaustein_ohne_zahlbar(k):
    """Zahlungstexte ohne „zahlbar“: „Zahlung: 14 Tage netto“, „14 Tage ohne Abzug“, „Bitte überweisen bis …“;
    ein Satz, der in der nächsten Zeile bündig weitergeht, gehört ganz dazu. Ein „Zahlung“ mitten im Satz
    („… für Ihre Zahlung: INV/1“) ist keine Zahlungsbedingung."""
    for teile in (
        ("Zahlung:", "14", "Tage", "netto"),
        ("14", "Tage", "ohne", "Abzug"),
        ("Bitte", "überweisen", "bis", "02.11.2026."),
    ):
        _, ws = pdferkennung.zahlungsbaustein([_z(*teile)])
        assert pdferkennung.zahlungsbaustein_text(ws) == " ".join(teile)
    assert (
        pdferkennung.zahlungsbaustein(
            [_z("Bitte", "verwenden", "für", "Ihre", "Zahlung:", "INV/1")]
        )
        is None
    )
    satz = _z(
        "Zahlung",
        "innerhalb",
        "von",
        "14",
        "Tagen",
        "ohne",
        "Abzüge",
        "an",
        "die",
        "unten",
        top=100,
    )
    rest = _z("Bankverbindung.", top=112)
    danach = _z("Mit", "freundlichen", "Grüßen", top=124)
    _, ws = pdferkennung.zahlungsbaustein([satz, rest, danach])
    assert pdferkennung.zahlungsbaustein_text(ws).endswith("an die unten Bankverbindung.")


def test_steuersatz_ohne_prozentzeichen():
    """„zzgl. 19,00 MwSt.“ nennt den Satz ohne %; die Endziffern eines Betrags („1.056,49 MwSt“) sind kein
    Satz."""
    assert anlernen.steuersaetze_im_text("zzgl. 19,00 MwSt. 56,49 EUR") == ["19,00"]
    assert anlernen.steuersaetze_im_text("19% MWSt auf EUR 1.361,50") == ["19"]
    assert anlernen.steuersaetze_im_text("Summe 1.056,49 MwSt") == []


def test_zwischensumme_mitten_in_der_tabelle(k):
    """„Zwischensumme“ zwischen zwei Positionen beendet die Tabelle nicht, wenn darunter Positionen folgen;
    am Ende (vor USt/Brutto) bleibt sie das Tabellenende."""
    from dataclasses import replace

    pdf, soll = _fiktiv("00125")
    k.pdf_profile = []
    s = anlernen.Sitzung(pdf, k)
    pv = s.pv()
    vorher = pdferkennung.positionen_auslesen(pv, s.zeilen)
    assert len(vorher) >= 2
    prot = []
    pdferkennung.positionen_auslesen(pv, s.zeilen, prot)
    pos_zeilen = [
        z for z, g in prot if g not in ("Kopfzeile",) and not g.startswith("Tabellenende")
    ]
    zweite = next(z for z in pos_zeilen if z.top > pos_zeilen[0].top + 1)
    x_bez = pv["spalten"]["BT-153"][0] + 1
    x_ges = pv["spalten"]["gesamt"][0] + 1
    top = zweite.top
    ws = [
        pdferkennung.Wort("Zwischensumme", x_bez, x_bez + 70, top, zweite.seite, top + 8),
        pdferkennung.Wort("99,00", x_ges, x_ges + 25, top, zweite.seite, top + 8),
    ]
    zs = pdferkennung.Zeile(zweite.seite, top, ws, [ws[:1], ws[1:]])
    zeilen = []
    for z in s.zeilen:
        if z is zweite:
            zeilen.append(zs)
        if z.seite == zweite.seite and z.top >= top:
            z = replace(z, top=z.top + 14, woerter=[replace(w, top=w.top + 14) for w in z.woerter])
        zeilen.append(z)
    nachher = pdferkennung.positionen_auslesen(pv, zeilen)
    assert [p.gesamt for p in nachher] == [p.gesamt for p in vorher]


def _mit_zeilen_unter_pos1(s, pv, neue):
    """Fiktive Zeilen ``neue`` [(dy, [(x, text, höhe)])] unter die erste Position setzen, Rest nach unten."""
    from dataclasses import replace

    prot = []
    pdferkennung.positionen_auslesen(pv, s.zeilen, prot)
    erste = next(z for z, g in prot if g != "Kopfzeile")
    platz = max(dy for dy, _ in neue) + 14
    zeilen = []
    for z in s.zeilen:
        if z.seite == erste.seite and z.top > erste.top:
            z = replace(
                z, top=z.top + platz, woerter=[replace(w, top=w.top + platz) for w in z.woerter]
            )
        zeilen.append(z)
        if z is erste:
            for dy, ws in neue:
                top = erste.top + dy
                wl = [
                    pdferkennung.Wort(t, x, x + 4 * len(t), top, erste.seite, top + h)
                    for x, t, h in ws
                ]
                zeilen.append(pdferkennung.Zeile(erste.seite, top, wl, [[w] for w in wl]))
    return zeilen


def test_bezeichnung_kleindruck_und_seitenleiste(k):
    """Unter einer Position: kleiner gedruckter Zusatz („Artikelbeschreibung kurz“) gehört nicht zur
    Bezeichnung; eine Zeile ganz rechts neben der Tabelle (Seitenleiste) unterbricht die Fortsetzung nicht."""
    pdf, _ = _fiktiv("00125")
    k.pdf_profile = []
    s = anlernen.Sitzung(pdf, k)
    pv = s.pv()
    vorher = pdferkennung.positionen_auslesen(pv, s.zeilen)[0].bezeichnung
    x_bez = pv["spalten"]["BT-153"][0] + 1
    x_rechts = max(b for _, b in pv["spalten"].values()) + 40
    prot = []
    pdferkennung.positionen_auslesen(pv, s.zeilen, prot)
    h = pdferkennung._schrifthoehe(next(z for z, g in prot if g != "Kopfzeile").woerter)
    zeilen = _mit_zeilen_unter_pos1(
        s, pv, [(5, [(x_rechts, "DE00SEITENLEISTE", h)]), (9, [(x_bez, "Edelstahl", h)])]
    )
    assert pdferkennung.positionen_auslesen(pv, zeilen)[0].bezeichnung == vorher + " Edelstahl"
    zeilen = _mit_zeilen_unter_pos1(s, pv, [(9, [(x_bez, "Kleindruck", h * 0.6)])])
    assert pdferkennung.positionen_auslesen(pv, zeilen)[0].bezeichnung == vorher


def test_zahlungsbaustein_skonto_satz_darunter(k):
    """„Zahlungsziel: 30 Tage“ und zwei Zeilen tiefer, bündig, „Bei Zahlung innerhalb von 8 Tagen … Skonto.“:
    der Skonto-Satz gehört zur Zahlungsbedingung."""
    k_ = pdferkennung.Wort("Zahlungsziel:", 40, 90, 600, 0, 607)
    v = pdferkennung.Wort("30", 126, 134, 600, 0, 607)
    v2 = pdferkennung.Wort("Tage", 136, 152, 600, 0, 607)
    z1 = pdferkennung.Zeile(0, 600, [k_, v, v2], [[k_], [v, v2]])
    z2 = _z("Bei", "Zahlung", "innerhalb", "von", "8", "Tagen", "3", "%", "Skonto.", top=620)
    _, ws = pdferkennung.zahlungsbaustein([z1, z2])
    assert (
        pdferkennung.zahlungsbaustein_text(ws)
        == "30 Tage Bei Zahlung innerhalb von 8 Tagen 3 % Skonto."
    )


def test_kopfworte_netto_ep_und_g_preis():
    """Spaltenüberschriften „Netto EP“/„Netto GP“ und „E-Preis“/„G-Preis“."""
    sp = anlernen._spalte_fuer
    assert (sp("Netto EP"), sp("Netto GP")) == ("BT-146", "gesamt")
    assert (sp("E-Preis"), sp("G-Preis")) == ("BT-146", "gesamt")
    assert (sp("EP"), sp("GP"), sp("Einzelpreis")) == ("BT-146", "gesamt", "BT-146")


def test_bt20_vorlage_ohne_regel_nimmt_druck_statt_profiltext(k):
    """Vorlage ohne Stelle für BT-20: Der Zahlungsbaustein im Druck gilt statt des Profiltexts (sonst still falsch,
    z. B. Profil „30 Tage ohne Abzug“ gegen „… bis <Datum> …“ mit Skonto), mit Hinweis „prüfen“."""
    prof = _fiktiv_anlernen(k)
    v = pdferkennung.vorlagen_laden(prof)[0]
    v["felder"].pop("BT-20")
    pdferkennung.vorlage_speichern(v, prof)
    for nr in ("00133", "00134"):
        r, soll = _fiktiv_lesen(k, prof, nr)
        assert _bt20_soll(soll) in r.zahlung.bedingungen
        assert any(h.feld == "BT-20" and h.stufe == "pruefen" for h in r.hinweise)


# -- Adresszusatz beim Käufer (Nutzer-Entscheid 23.11.2026): Abteilung → BT-51, z. Hd. → BT-56 ----------------
@pytest.mark.parametrize(
    "oben, soll",
    [
        (
            ["Beispiel AG", "Abteilung Einkauf"],
            {"BT-44": "Beispiel AG", "BT-51": "Abteilung Einkauf"},
        ),
        (["Beispiel AG", "z. Hd. Frau Muster"], {"BT-44": "Beispiel AG", "BT-56": "Frau Muster"}),
        (
            ["Beispiel AG", "Abt. Einkauf", "Gebäude C", "zu Händen Herrn Beispiel"],
            {
                "BT-44": "Beispiel AG",
                "BT-51": "Abt. Einkauf",
                "BT-163": "Gebäude C",
                "BT-56": "Herrn Beispiel",
            },
        ),
        (
            ["Beispiel AG", "c/o Muster Verwaltung"],
            {"BT-44": "Beispiel AG", "BT-51": "c/o Muster Verwaltung"},
        ),
        # zweizeiliger Firmenname bleibt ganz, auch mit Vermerk darunter
        (
            ["Beispiel Sondermaschinenbau", "GmbH & Co. KG", "Attn. Einkauf"],
            {"BT-44": "Beispiel Sondermaschinenbau GmbH & Co. KG", "BT-56": "Einkauf"},
        ),
        (
            ["Beispiel Sondermaschinenbau", "GmbH & Co. KG"],
            {"BT-44": "Beispiel Sondermaschinenbau GmbH & Co. KG"},
        ),
        # Zweifel: alte Regel (alles in BT-44) – Name nach Vermerk, nur Vermerk, Wort nur am Anfang ähnlich
        (["Beispiel AG", "Abteilung V", "Werk Süd"], {"BT-44": "Beispiel AG Abteilung V Werk Süd"}),
        (["z. Hd. Herrn Muster"], {"BT-44": "z. Hd. Herrn Muster"}),
        (["Gebäudemanagement Beispiel GmbH"], {"BT-44": "Gebäudemanagement Beispiel GmbH"}),
    ],
)
def test_adresszusatz_kaeufer(oben, soll):
    teile = pdferkennung.anschrift_teilen(oben + ["Musterweg 1", "12345 Musterstadt"])
    assert teile == {**soll, "BT-50": "Musterweg 1", "BT-53": "12345", "BT-52": "Musterstadt"}


def test_adresszusatz_absender_bleibt():
    """Der Absender (BT-35/36) ist nicht Teil der Regel: dort bleibt alles über der Straße im Namen."""
    from fakturafalter import anschrift

    teile = anschrift.anschrift_zerlegen(
        ["Beispiel AG", "Abteilung Vertrieb", "Musterweg 1", "12345 Musterstadt"], zusatz=False
    )
    assert teile[0]["BT-44"] == "Beispiel AG Abteilung Vertrieb" and "BT-51" not in teile[0]


def test_adresszusatz_sitzung_und_alte_vorlage(k, tmp_path):
    """Kaltstart: Abteilung in Adresszeile 2, z. Hd. als Kontaktstelle in der Rechnung. Eine Blockregel aus einem
    Druck ohne Zusatz (alte Vorlage, keine neuen Schlüssel) zerlegt den nächsten Druck nach der neuen Regel."""
    adr = [
        (135, 42, "Beispiel AG"),
        (147, 42, "Abteilung Einkauf"),
        (159, 42, "z. Hd. Frau Muster"),
        (171, 42, "Musterweg 12"),
        (195, 42, "12345 Musterstadt"),
    ]
    s = anlernen.Sitzung(_fenster_pdf(tmp_path / "z.pdf", adr), k)
    assert (s.werte["BT-44"].wert, s.werte["BT-51"].wert) == ("Beispiel AG", "Abteilung Einkauf")
    assert s.werte["BT-56"].wert == "Frau Muster"
    r = s.rechnung()
    assert (
        r.kaeufer.kontakt_name == "Frau Muster"
        and r.kaeufer.anschrift.zusatz == "Abteilung Einkauf"
    )
    s.werte["BT-51"].wert = ""  # Name/Zusatz ändern: Kontaktstelle bleibt (eigenes Feld)
    assert s.rechnung().kaeufer.kontakt_name == "Frau Muster"
    s.werte["BT-56"].wert = ""
    assert not s.rechnung().kaeufer.kontakt_name

    alt = anlernen.Sitzung(
        _fenster_pdf(k.eingang / "a.pdf", _NAME + [(195, 42, "12345 Musterstadt")]), k
    )
    seite, rahmen, _ = alt.bereiche()[pdferkennung.ANSCHRIFT_BLOCK]
    regel = pdferkennung.bereich_regel(
        pdferkennung.ANSCHRIFT_BLOCK, alt.zeilen, seite, rahmen, set(), True
    )
    assert not {"zusatz", "kontakt", "BT-56", "BT-163"} & set(regel)
    neu = anlernen.Sitzung(_fenster_pdf(tmp_path / "b.pdf", adr), k)
    assert {f: t for f, (t, _) in pdferkennung.anschrift_auslesen(regel, neu.zeilen).items()} == {
        "BT-44": "Beispiel AG",
        "BT-51": "Abteilung Einkauf",
        "BT-56": "Frau Muster",
        "BT-50": "Musterweg 12",
        "BT-53": "12345",
        "BT-52": "Musterstadt",
    }


def test_adresszusatz_name_nur_vermerk_prueft():
    """Steht über der Straße nur ein Vermerk, bleibt er Name (alte Regel), aber mit Hinweis „prüfen“."""

    def zeile(top, text):
        return [
            pdferkennung.Wort(w, 40 + 60 * i, 95 + 60 * i, top, 0, top + 10)
            for i, w in enumerate(text.split())
        ]

    ws = [
        zeile(100, "Abteilung Einkauf"),
        zeile(112, "Musterweg 1"),
        zeile(124, "12345 Musterstadt"),
    ]
    assert "BT-44" in pdferkennung.anschrift_brueche(ws)
    ws[0] = zeile(100, "Beispiel AG")
    assert "BT-44" not in pdferkennung.anschrift_brueche(ws)


# 0.9.0 Nutzerfund: Positionszeile mit Dezimalmenge und leerer Einheit („0,5 | | Transportpauschale | 35,00 /1 |
# 17,50“) wurde nicht als Position erkannt. Nachbau fiktiv.
@pytest.mark.parametrize(
    "menge,me,preis,betrag",
    [
        ("0,5", "", "35,00", "17,50"),
        ("0,5", "Std", "35,00", "17,50"),
        ("1,25", "", "35,00", "43,75"),
        ("2", "", "35,00", "70,00"),
        ("1.000,5", "", "0,10", "100,05"),
    ],
)
def test_dezimalmenge_ohne_einheit(k, menge, me, preis, betrag):
    zeilen = ["", erp_roh.pos_pe(menge, me, "Transportpauschale", preis, "/1", betrag)]
    s = _pe_sitzung(k, "dezimal", zeilen, betrag)
    pos = s.positionen()
    assert [(p.menge, p.einzelpreis, p.preiseinheit, p.gesamt) for p in pos] == [
        (
            Decimal(menge.replace(".", "").replace(",", ".")),
            Decimal(preis.replace(",", ".")),
            Decimal("1"),
            Decimal(betrag.replace(",", ".")),
        )
    ]
    assert pos[0].bezeichnung.startswith("Transportpauschale")
    assert not s.betrag_abweichungen()
