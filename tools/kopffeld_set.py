# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kopffeld-Testset: fiktive Rechnungen mit abweichenden Anschriftblöcken und Sollwerten (alle Inhalte erfunden).

Je Variante zwei einseitige PDFs mit gleichem Layout:

* ``<id>.pdf`` – der zu lesende Beleg mit der abweichenden Käuferanschrift,
* ``<id>-vorlage.pdf`` – derselbe Briefbogen mit einem einfachen Inlandskunden (zum Anlernen der Vorlage).

``soll.json`` enthält je Variante Käufer (Namenszeilen, Zusatz über/unter der Straße, Straße, PLZ, Ort, Land),
Absender, Layout-Angaben (Fensterlage nach DIN 5008, Rahmen der Anschriftzone) und ``holdout`` (jede dritte
Variante der ersten 55 sowie alle nachträglichen ``h*``-Varianten; nicht zum Abstimmen von Regeln verwenden).
Deterministisch, offline:

    python tools/kopffeld_set.py                    # schreibt tests/daten/kopffeld/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

WURZEL = Path(__file__).resolve().parent.parent
ZIEL = WURZEL / "tests" / "daten" / "kopffeld"
W, H = A4
MM = 72 / 25.4

# DIN 5008: Fenster 85 × 45 mm, 20 mm vom linken Rand; Form A ab 27 mm, Form B ab 45 mm von oben.
# Zusatz- und Vermerkzone oben (A 12,7 mm, B 17,7 mm), darunter die Anschriftzone (27,3 mm).
FORM = {"A": (27 * MM, 12.7 * MM), "B": (45 * MM, 17.7 * MM)}
FENSTER_X, FENSTER_B, FENSTER_H, ZONE_H = 20 * MM, 85 * MM, 45 * MM, 27.3 * MM

ABSENDER = [
    {"name": "Nordlicht Normteile GmbH", "strasse": "Kaistraße 8", "plz": "24103", "ort": "Kiel"},
    {"name": "Hartwig & Söhne Metallbau KG", "strasse": "Mühlenweg 21", "plz": "33602", "ort": "Bielefeld"},
    {"name": "Tannberg Elektrotechnik e.K.", "strasse": "Bahnhofstraße 3", "plz": "79098", "ort": "Freiburg"},
]
IBAN = "DE89370400440532013000"     # bekannte Beispiel-IBAN (Prüfziffer gültig)

NAMEN = {
    1: [["Kessler Antriebstechnik GmbH"], ["Lohmann Kältebau AG"], ["Stadtwerke Talheim"]],
    2: [["Beispiel Werkzeug- und", "Anlagenbau GmbH"], ["Ingenieurbüro Hessel", "Planung und Statik"],
        ["Verein der Freunde des", "Heimatmuseums Talheim e.V."]],
    3: [["Gemeinschaftspraxis für", "Physiotherapie", "Dr. Anna Muster und Ben Beispiel"],
        ["Ostwind Logistik", "Verwaltungs GmbH & Co.", "Speditions KG"],
        ["Kreisverwaltung Talheim", "Fachbereich Hochbau", "Gebäudemanagement"]],
}
STANDARD_KUNDE = {"name": ["Normalkunde Handel GmbH"], "strasse": "Lindenweg 4", "plz": "12345",
                  "ort": "Musterstadt"}


def _kaeufer(n: int, i: int, **kw) -> dict:
    k = {"name": NAMEN[n][i % 3], "zusatz_oben": [], "strasse_zeilen": None, "strasse": "Talstraße 12",
         "zusatz_unten": [], "plz": "54321", "ort": "Neustadt", "plz_zeile": None, "land": "DE",
         "land_zeile": None}
    k.update(kw)
    return k


def varianten() -> list[dict]:
    """Varianten: id, Beschreibung, Käufer, Layout. Namenslänge 1–3 bei allen Grenzfällen Name/Straße."""
    v: list[dict] = []

    def neu(vid, text, kaeufer, **layout):
        v.append({"id": vid, "text": text, "kaeufer": kaeufer, "layout": layout})

    # Grenze Name/Straße × Name 1, 2, 3 Zeilen
    for n in (1, 2, 3):
        neu(f"g1-n{n}", f"Standard (Straße mit Hausnummer), Name {n}-zeilig", _kaeufer(n, 0))
        neu(f"g2-n{n}", f"Straße ohne Hausnummer („Am Hafen“), Name {n}-zeilig", _kaeufer(n, 1, strasse="Am Hafen"))
        neu(f"g3-n{n}", f"Postfach statt Straße, Name {n}-zeilig", _kaeufer(n, 2, strasse="Postfach 10 20 30",
                                                                           plz="54290"))
        neu(f"g4-n{n}", f"Straße und Hausnummer in zwei Zeilen, Name {n}-zeilig",
            _kaeufer(n, 0, strasse="Carl-Benz-Straße 14", strasse_zeilen=["Carl-Benz-Straße", "14"]))
        neu(f"g5-n{n}", f"Zusatz unter der Straße („Hinterhaus, 2. OG“), Name {n}-zeilig",
            _kaeufer(n, 1, zusatz_unten=["Hinterhaus, 2. OG"]))
        neu(f"g6-n{n}", f"Kontaktzeile „Herrn …“ unter dem Namen, Name {n}-zeilig",
            _kaeufer(n, 2, zusatz_oben=["Herrn Jonas Beispiel"]))
        neu(f"g7-n{n}", f"Gewerbegebiet/Ortsteil über der Straße, Name {n}-zeilig",
            _kaeufer(n, 0, zusatz_oben=["Gewerbegebiet Ost"]))
    # Land, PLZ-Formen
    neu("l1", "Land „DEUTSCHLAND“ als letzte Zeile", _kaeufer(1, 0, land_zeile="DEUTSCHLAND"))
    neu("l2", "Österreich: 4-stellige PLZ, „ÖSTERREICH“ als letzte Zeile",
        _kaeufer(2, 0, strasse="Museumstraße 5", plz="6020", ort="Innsbruck", land="AT", land_zeile="ÖSTERREICH"))
    neu("l3", "Schweiz: 4-stellige PLZ, „SCHWEIZ“ als letzte Zeile",
        _kaeufer(3, 1, strasse="Hardturmstrasse 101", plz="8005", ort="Zürich", land="CH", land_zeile="SCHWEIZ"))
    neu("l4", "PLZ mit Länderkürzel „D-12345“", _kaeufer(1, 1, plz_zeile="D-54321 Neustadt"))
    neu("l5", "„A-1010 Wien“ ohne Landzeile", _kaeufer(2, 1, strasse="Kärntner Ring 12", plz="1010", ort="Wien",
                                                       land="AT", plz_zeile="A-1010 Wien"))
    neu("l6", "„CH-4051 Basel“ ohne Landzeile", _kaeufer(1, 2, strasse="Steinenvorstadt 2", plz="4051",
                                                         ort="Basel", land="CH", plz_zeile="CH-4051 Basel"))
    neu("l7", "„DE-12345“ und „GERMANY“", _kaeufer(3, 0, plz_zeile="DE-54321 Neustadt", land_zeile="GERMANY"))
    neu("l8", "Ort mit Zusatz „Frankfurt am Main“", _kaeufer(2, 2, plz="60311", ort="Frankfurt am Main"))
    neu("l9", "Ort mit Klammer „Halle (Saale)“", _kaeufer(1, 0, plz="06108", ort="Halle (Saale)"))
    neu("l10", "Niederlande: „1012 AB Amsterdam“, „NIEDERLANDE“",
        _kaeufer(1, 1, strasse="Damrak 70", plz="1012 AB", ort="Amsterdam", land="NL", land_zeile="NIEDERLANDE"))
    # Lage und Umfeld des Blocks
    neu("f1", "DIN 5008 Form A (Fenster höher)", _kaeufer(2, 0), form="A")
    neu("f2", "Anschrift rechts, Infoblock links", _kaeufer(2, 1), anschrift_x=115 * MM, info_x=FENSTER_X)
    neu("f3", "Infoblock dicht rechts neben der Anschrift (gleiche Zeilenhöhen)", _kaeufer(3, 2), info_x=95 * MM)
    neu("f4", "Rücksendeangabe mit Kommas", _kaeufer(1, 2), ruecksende=", ")
    neu("f5", "Rücksendeangabe mit „ - “, unterstrichen", _kaeufer(2, 0), ruecksende=" - ", unterstrichen=True)
    neu("f6", "keine Rücksendeangabe", _kaeufer(3, 0), ruecksende=None)
    neu("f7", "Vermerk „Einschreiben“ in der Vermerkzone", _kaeufer(1, 1), vermerk=["Einschreiben"])
    neu("f8", "Beschriftung „Rechnungsanschrift:“ über dem Block", _kaeufer(2, 2), beschriftung="Rechnungsanschrift:")
    neu("f9", "Leerzeilen zwischen Name, Straße und Ort", _kaeufer(3, 1), leerzeilen=True)
    neu("f10", "Name fett 12 pt, Rest 10 pt", _kaeufer(2, 1), name_fett=True)
    neu("f11", "kleine Schrift 8 pt, enger Zeilenabstand 9,5 pt", _kaeufer(3, 2), schrift=8, abstand=9.5)
    neu("f12", "weiter Zeilenabstand 15 pt", _kaeufer(3, 0), abstand=15)
    neu("f13", "Briefkopf des Absenders links oben über dem Fenster", _kaeufer(1, 0), kopf="links")
    neu("f14", "Briefkopf nur als Grafik, Absender nur in der Fußzeile", _kaeufer(2, 1), kopf="grafik")
    neu("f15", "Straße „Q 7, 12“ (Quadrat)", _kaeufer(1, 1, strasse="Q 7, 12", plz="68161", ort="Mannheim"))
    neu("f16", "Straße „Straße des 17. Juni 112“", _kaeufer(2, 2, strasse="Straße des 17. Juni 112", plz="10623",
                                                             ort="Berlin"))
    neu("f17", "Straße „Am Markt 3–5“ und Name mit „c/o“", _kaeufer(1, 2, strasse="Am Markt 3–5",
                                                                  zusatz_oben=["c/o Muster Verwaltung"]))
    neu("f18", "„z. Hd. Frau Muster“ und „Abteilung Einkauf“", _kaeufer(1, 0, zusatz_oben=["Abteilung Einkauf",
                                                                                       "z. Hd. Frau Muster"]))
    neu("f19", "Rechnungs- und Lieferanschrift nebeneinander", _kaeufer(2, 0), lieferanschrift=True)
    neu("f20", "PLZ und Ort mit großem Abstand (Tabulator)", _kaeufer(1, 1), plz_abstand=60)
    neu("f21", "Kundennummer als Vermerk über dem Namen", _kaeufer(2, 2), vermerk=["Kd.-Nr. 10023"])
    neu("f22", "Absenderzeile ohne Trenner, nur Leerzeichen", _kaeufer(3, 1), ruecksende="  ")
    neu("f23", "Fenster-Rücksendeangabe zweizeilig", _kaeufer(1, 0), ruecksende_zweizeilig=True)
    neu("f24", "Name in Großbuchstaben", _kaeufer(1, 0, name=["KESSLER ANTRIEBSTECHNIK GMBH"]))
    for i, x in enumerate(v):
        x["holdout"] = i % 3 == 2
        x["absender"] = ABSENDER[i % 3]
    # Nachträgliche Hold-out-Varianten (vor Konzeptschritt 2/3 angelegt, nur zum Prüfen, nie zum Abstimmen):
    # weitere Straßenformen, Hausnummer in eigener Zeile, Zusatz unter der Straße, Gegenproben.
    alt = len(v)
    neu("h1", "Straße ohne Hausnummer „Lange Reihe“, Name 2-zeilig", _kaeufer(2, 2, strasse="Lange Reihe"))
    neu("h2", "Hausnummernbereich mit Leerzeichen „Hafenstraße 10 - 12“",
        _kaeufer(1, 0, strasse="Hafenstraße 10 - 12"))
    neu("h3", "Hausnummernbereich mit Gedankenstrich „Am Kai 3 – 5“, Name 3-zeilig",
        _kaeufer(3, 1, strasse="Am Kai 3 – 5"))
    neu("h4", "Straße „P 7, 20“ (Quadrat), Name 2-zeilig", _kaeufer(2, 0, strasse="P 7, 20", plz="68161",
                                                                  ort="Mannheim"))
    neu("h5", "Straße „Straße des 17. Juni“ ohne Hausnummer", _kaeufer(1, 1, strasse="Straße des 17. Juni",
                                                                      plz="10623", ort="Berlin"))
    neu("h6", "Hausnummer „7a“ in eigener Zeile unter „Lange Reihe“, Name 2-zeilig",
        _kaeufer(2, 1, strasse="Lange Reihe 7a", strasse_zeilen=["Lange Reihe", "7a"]))
    neu("h7", "Hausnummer „12–14“ in eigener Zeile, Name 3-zeilig",
        _kaeufer(3, 2, strasse="Industriestraße 12–14", strasse_zeilen=["Industriestraße", "12–14"]))
    neu("h8", "Zusatz unter der Straße „Gebäude C, 3. Stock“, Name 2-zeilig",
        _kaeufer(2, 0, zusatz_unten=["Gebäude C, 3. Stock"]))
    neu("h9", "Zusatz unter der Straße ohne Ziffer („Hintereingang“), Name 1-zeilig",
        _kaeufer(1, 2, zusatz_unten=["Hintereingang"]))
    neu("h10", "Gegenprobe: Namenszeile „Werk 2“ über Straße ohne Hausnummer „Am Hafen“",
        _kaeufer(1, 0, name=["Kessler Antriebstechnik GmbH", "Werk 2"], strasse="Am Hafen"))
    neu("h11", "Gegenprobe: Namenszeile „Halle 3“ über „Talstraße 12“",
        _kaeufer(1, 1, name=["Lohmann Kältebau AG", "Halle 3"]))
    neu("h12", "Gegenprobe: Name mit Ziffer „Werkstatt 3000 GmbH“, Straße „Am Hafen 2“",
        _kaeufer(1, 2, name=["Werkstatt 3000 GmbH"], strasse="Am Hafen 2"))
    for i, x in enumerate(v[alt:], alt):
        x["holdout"] = True
        x["absender"] = ABSENDER[i % 3]
    return v


def _block_zeilen(k: dict, lay: dict) -> list[tuple[str, bool]]:
    """Käufer -> Zeilen (Text, fett) in Druckreihenfolge; ``""`` = Leerzeile."""
    z = [(n, lay.get("name_fett", False)) for n in k["name"]] + [(t, False) for t in k["zusatz_oben"]]
    if lay.get("leerzeilen"):
        z.append(("", False))
    z += [(t, False) for t in (k["strasse_zeilen"] or [k["strasse"]])]
    z += [(t, False) for t in k["zusatz_unten"]]
    if lay.get("leerzeilen"):
        z.append(("", False))
    z.append((k["plz_zeile"] or f"{k['plz']} {k['ort']}", False))
    if k["land_zeile"]:
        z.append((k["land_zeile"], False))
    return z


def _text(c, x, top, s, schrift="Helvetica", groesse=10.0):
    c.setFont(schrift, groesse)
    c.drawString(x, H - top - groesse * 0.8, s)


def zeichnen(pfad: Path, var: dict, kaeufer: dict) -> dict:
    """Ein PDF schreiben -> Layout-Angaben (Rahmen der Anschriftzone in pt, top-Koordinaten)."""
    lay, ab = var["layout"], var["absender"]
    c = canvas.Canvas(str(pfad), pagesize=A4, invariant=1)
    c.setTitle(f"Kopffeld {var['id']}")
    fenster_top, vermerk_h = FORM[lay.get("form", "B")]
    ax = lay.get("anschrift_x", FENSTER_X + 5 * MM)
    gr, ab_z = lay.get("schrift", 10.0), lay.get("abstand", 12.0)
    absender_zeile = [ab["name"], ab["strasse"], f"{ab['plz']} {ab['ort']}"]
    # Briefkopf
    kopf = lay.get("kopf", "rechts")
    if kopf == "rechts":
        for i, (t, f, g) in enumerate([(ab["name"], "Helvetica-Bold", 12), (ab["strasse"], "Helvetica", 9),
                                       (f"{ab['plz']} {ab['ort']}", "Helvetica", 9),
                                       ("Telefon 0431 123456", "Helvetica", 9)]):
            _text(c, 125 * MM, 30 + 13 * i, t, f, g)
    elif kopf == "links":
        for i, (t, f, g) in enumerate([(ab["name"], "Helvetica-Bold", 12), (ab["strasse"], "Helvetica", 9),
                                       (f"{ab['plz']} {ab['ort']}", "Helvetica", 9)]):
            _text(c, ax, 24 + 12 * i, t, f, g)
    else:                                                       # nur Grafik: Logo aus Flächen
        c.setFillGray(0.3)
        for i in range(5):
            c.rect(125 * MM + i * 14, H - 70, 10, 34 - i * 5, fill=1, stroke=0)
        c.setFillGray(0)
    # Rücksendeangabe oben in der Vermerkzone
    trenner = lay.get("ruecksende", " · ")
    rs_top = fenster_top + 3
    if lay.get("ruecksende_zweizeilig"):
        _text(c, ax, rs_top, ab["name"], groesse=7)
        _text(c, ax, rs_top + 8, f"{ab['strasse']} · {ab['plz']} {ab['ort']}", groesse=7)
    elif trenner is not None:
        s = trenner.join(absender_zeile)
        _text(c, ax, rs_top, s, groesse=7)
        if lay.get("unterstrichen"):
            c.setLineWidth(0.4)
            c.line(ax, H - rs_top - 7.5, ax + c.stringWidth(s, "Helvetica", 7), H - rs_top - 7.5)
    for i, t in enumerate(lay.get("vermerk", [])):
        _text(c, ax, fenster_top + vermerk_h - 12 - 10 * i, t, groesse=9)
    # Anschriftzone
    zone_top = fenster_top + vermerk_h
    top = zone_top + 2
    if lay.get("beschriftung"):
        _text(c, ax, top, lay["beschriftung"], groesse=8)
        top += 10
    unten = top
    for t, fett in _block_zeilen(kaeufer, lay):
        if t:
            g = 12 if fett else gr
            if lay.get("plz_abstand") and t == f"{kaeufer['plz']} {kaeufer['ort']}":
                _text(c, ax, top, kaeufer["plz"], groesse=g)
                _text(c, ax + lay["plz_abstand"], top, kaeufer["ort"], groesse=g)
            else:
                _text(c, ax, top, t, "Helvetica-Bold" if fett else "Helvetica", g)
            unten = top + g
        top += ab_z if not fett else 14
    if lay.get("lieferanschrift"):
        _text(c, 115 * MM, zone_top - 10, "Lieferanschrift:", groesse=8)
        for i, t in enumerate(["Lager Süd", "Hafenring 9", "54329 Neustadt-Süd"]):
            _text(c, 115 * MM, zone_top + 2 + 12 * i, t)
    # Infoblock
    ix = lay.get("info_x", 125 * MM)
    if lay.get("lieferanschrift"):
        ix, it = 125 * MM, 290 - 60
    else:
        it = zone_top + 2
    for i, t in enumerate(["Kundennummer: 10023", "Rechnungsnr.: RE-2026-0815", "Datum: 05.10.2026"]):
        _text(c, ix, it + ab_z * i, t, groesse=gr)
    # Rumpf
    _text(c, FENSTER_X + 5 * MM, 330, "Rechnung RE-2026-0815", "Helvetica-Bold", 13)
    kopfzeile = [("Pos", 60), ("Menge", 90), ("Einheit", 135), ("Bezeichnung", 185), ("Einzelpreis", 400),
                 ("Gesamtpreis", 490)]
    for t, x in kopfzeile:
        _text(c, x, 360, t, "Helvetica-Bold", 9)
    zeilen = [("1", "10", "Stk", "Sechskantschraube M8x40", "1,25", "12,50"),
              ("2", "2", "Std", "Montage vor Ort", "85,00", "170,00")]
    for j, z in enumerate(zeilen):
        for (_, x), t in zip(kopfzeile, z):
            _text(c, x, 376 + 14 * j, t, groesse=9)
    for j, (t, b) in enumerate([("Nettobetrag", "182,50"), ("USt 19 %", "34,68"), ("Gesamtbetrag", "217,18")]):
        _text(c, 400, 420 + 14 * j, t, groesse=9)
        _text(c, 490, 420 + 14 * j, b, groesse=9)
    _text(c, 60, 480, "Zahlbar innerhalb von 30 Tagen ohne Abzug.", groesse=9)
    fuss = (f"{ab['name']} · {ab['strasse']} · {ab['plz']} {ab['ort']} · USt-IdNr. DE123456789 · "
            f"IBAN {IBAN}")
    _text(c, 60, 800, fuss, groesse=7)
    c.showPage()
    c.save()
    x1 = ax + (FENSTER_B - 5 * MM if lay.get("anschrift_x") is None else 80 * MM)
    return {"form": lay.get("form", "B"), "zone": [round(ax - 3, 1), round(zone_top, 1), round(x1, 1),
                                                   round(fenster_top + FENSTER_H, 1)],
            "block_unten": round(unten, 1)}


def soll_kaeufer(k: dict) -> dict:
    return {"name_zeilen": k["name"], "zusatz_oben": k["zusatz_oben"], "zusatz_unten": k["zusatz_unten"],
            "strasse": k["strasse"], "plz": k["plz"], "ort": k["ort"], "land": k["land"]}


def schreiben(ziel: Path = ZIEL) -> list[dict]:
    ziel.mkdir(parents=True, exist_ok=True)
    out = []
    for var in varianten():
        lay = zeichnen(ziel / f"{var['id']}.pdf", var, var["kaeufer"])
        vk = _kaeufer(1, 0, name=STANDARD_KUNDE["name"], strasse=STANDARD_KUNDE["strasse"],
                      plz=STANDARD_KUNDE["plz"], ort=STANDARD_KUNDE["ort"])
        zeichnen(ziel / f"{var['id']}-vorlage.pdf", var, vk)
        out.append({"id": var["id"], "text": var["text"], "holdout": var["holdout"],
                    "kaeufer": soll_kaeufer(var["kaeufer"]), "vorlage_kaeufer": soll_kaeufer(vk),
                    "absender": var["absender"], "layout": lay})
    (ziel / "soll.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ziel / "LIESMICH.txt").write_text(
        "Kopffeld-Testset (alle Inhalte erfunden), erzeugt mit tools/kopffeld_set.py.\n"
        "<id>.pdf: Beleg mit abweichender Käuferanschrift; <id>-vorlage.pdf: gleicher Briefbogen, einfacher\n"
        "Inlandskunde (zum Anlernen). soll.json: Sollwerte, Layout (Anschriftzone nach DIN 5008), holdout.\n"
        "Hold-out (jede dritte der ersten 55 Varianten und alle h*-Varianten) nicht zum Abstimmen von Regeln\n"
        "verwenden.\n"
        "Messung: python tools/kopffeld_messung.py --md kopffeld.md --json kopffeld.json\n",
        encoding="utf-8")
    return out


if __name__ == "__main__":
    n = schreiben(Path(sys.argv[1]) if len(sys.argv) > 1 else ZIEL)
    print(f"{len(n)} Varianten ({sum(x['holdout'] for x in n)} Hold-out) nach {ZIEL}")
