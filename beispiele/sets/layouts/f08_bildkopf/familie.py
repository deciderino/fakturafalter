"""F8 „Bildkopf“ – nach dem Business-Central-Bericht 1306 „Standard-Verkaufsrechnung“ (QUELLEN.md, Q10).
Volles Hold-out: kein Beleg dieser Familie wird angelernt.

Wortlaut und Anordnung wie im Bericht, Times: Briefkopf (Firmenname, Zeile darunter) und Fußzeile (Sitz,
Register, Geschäftsführung) als eingebettetes Bild, wie bei Unternehmen, die ihr Briefpapier als Bild hinterlegen.
Firmenblock rechts als Text in zwei Spalten (Telefonnr. / E-Mail / Homepage / USt-IdNr. / Bank / IBAN /
SWIFT-Code). Anschrift links, darunter Debitorennr. und – falls vorhanden – Ihre Referenz. Rechts „Rechnung“
mit Rechnungsnr. / Buchungsdatum / Fälligkeitsdatum / Lieferdatum / Zahlungsbedingungen / Lieferbedingungen,
jeweils Label und Wert nebeneinander ohne Doppelpunkt; nie Label über Wert. Tabelle Nr. | Beschreibung | Menge |
Einheit („Stück“/„Stunde“) | VK-Preis | MwSt. % | Betrag. Summen Zwischensumme / Gesamt EUR ohne MwSt. /
19 % MwSt. / Gesamt EUR inkl. MwSt. Folgeseiten wiederholen Kopf und Tabellenkopf mit „Seite N“; der Bericht
druckt keinen Übertrag (``test_flags.uebertrag_gedruckt`` = false, die Seitenwerte im JSON sind nur Rechenwerte).
Genau ein Beleg (Nr. 4) hat eine Postfach-Anschrift (``test_flags.po_box``)."""
from __future__ import annotations

import io
import sys
from decimal import Decimal
from pathlib import Path

from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, Absender, Artikel, Blatt, Familie, Spez, iban_de, leinwand, menge,  # noqa: E402
                     positionen, seitenplan, ust_id_de, zahl)

R, B = "Times-Roman", "Times-Bold"
G = 9.0
AB = Absender("Weserblick Elektrotechnik GmbH", "Am Speicher XI 7", "28217", "Bremen",
              ust_id_de("31477520"), iban_de("0045120098"), "WESBDEX1BRE", "Beispielbank Bremen",
              "rechnungen@weserblick-elektro.example", "www.weserblick-elektro.example", "0421 000000-0",
              "Amtsgericht Bremen HRB 00000 HB", "Gesa Thormählen")
EINHEIT = {"Stk.": "Stück", "Std.": "Stunde"}
KATALOG = [
    Artikel("1896-S", "Kabeltrommel 25 m, IP44", (39, 69), mengen=(1, 2, 4)),
    Artikel("1900-S", "LED-Hallenleuchte 150 W", (89, 149), mengen=(2, 4, 6, 10)),
    Artikel("1906-S", "Bewegungsmelder Decke 360°", (24, 45), mengen=(2, 4, 8)),
    Artikel("1908-S", "Fehlerstromschutzschalter 40 A", (32, 58), mengen=(1, 2, 3)),
    Artikel("1920-S", "Installationskabel NYM-J 3×1,5, Ring 50 m", (38, 59), mengen=(1, 2, 5)),
    Artikel("1925-W", "Unterverteilung 3-reihig, Aufputz", (110, 189), mengen=(1, 2)),
    Artikel("1928-S", "Steckdose Schuko Aufputz, grau", (4.9, 8.5), mengen=(10, 20, 30)),
    Artikel("1929-S", "Abzweigdose IP65 mit Klemmen", (2.9, 5.5), mengen=(10, 20, 40)),
    Artikel("1936-S", "Notleuchte Rettungszeichen", (65, 99), mengen=(1, 2, 4)),
    Artikel("1960-S", "Kabelkanal 40 × 60, 2 m", (6.5, 11), mengen=(5, 10, 20)),
    Artikel("1964-W", "Messprotokoll DGUV V3 je Anlage", (45, 75), mengen=(1, 2, 3)),
    Artikel("1968-S", "Wallbox 11 kW inkl. Montagematerial", (590, 890), mengen=(1, 2)),
    Artikel("MONTAGE", "Montage Elektrofachkraft", (58, 72), unit="Std.", mengen=(2, 4, 6, 8, 10)),
    Artikel("HELFER", "Montagehelfer", (38, 48), unit="Std.", mengen=(2, 4, 8)),
    Artikel("ANFAHRT", "Anfahrtspauschale Stadtgebiet", (29, 49), mengen=(1, 2)),
]
LANG = ["laut Leistungsverzeichnis Pos. 3.2, Abnahme durch Bauleitung",
        "inklusive Prüfung und Dokumentation nach DIN VDE 0100-600",
        "Lieferung auf Baustelle, Entsorgung der Verpackung"]
X_NR, X_BEZ, X_MENGE, X_EH, X_EP, X_UST, X_GP = 50, 105, 345, 352, 438, 492, 545
BEZ_BREITE = 200
TAKT = 11.0
Y_KOPF1, Y_KOPF2 = 352.0, 200.0


def _bild(zeilen, breite, hoehe, linie_oben=False) -> io.BytesIO:
    """Kopf/Fuß als Bild (Pillow, Liberation Serif; deterministisch)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (breite, hoehe), (255, 255, 255))
    d = ImageDraw.Draw(img)
    pfad = "/usr/share/fonts/truetype/liberation/LiberationSerif-{}.ttf"
    y = 6
    if linie_oben:
        d.rectangle([0, 0, breite - 1, 3], fill=(20, 60, 100))
        y = 14
    for text, groesse, fett in zeilen:
        f = ImageFont.truetype(pfad.format("Bold" if fett else "Regular"), groesse)
        d.text((4, y), text, font=f, fill=(20, 60, 100) if fett else (70, 70, 70))
        y += int(groesse * 1.3)
    b = io.BytesIO()
    img.save(b, format="PNG", optimize=False)
    b.seek(0)
    return b


KOPF = _bild([("WESERBLICK", 64, True), ("Elektrotechnik · Gebäudetechnik · E-Mobilität", 26, False)], 900, 130)
FUSS = _bild([(f"Sitz der Gesellschaft: {AB.ort} · {AB.register} · Geschäftsführerin: {AB.gf}", 22, False)],
             1500, 50, linie_oben=True)


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    if s.zahlung == "skonto":
        return [f"{s.skonto} % Skonto {s.skonto_tage} Tage, {s.ziel} Tage netto"]
    return [f"{s.ziel} Tage netto"]


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 0.2, erste=34, folge=46, summen=7, vortrag=False)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t, z = d["buyer"], d["invoice"], d["totals_printed"], d["payment"]
    kopf, fuss = ImageReader(KOPF), ImageReader(FUSS)
    for se in seiten:
        c.drawImage(kopf, 50, A4[1] - 90, 270, 39)
        c.drawImage(fuss, 50, A4[1] - 815, 495, 16.5)
        firma = [("", AB.name), ("", AB.strasse), ("", f"{AB.plz} {AB.ort}"), ("", ""),
                 ("Telefonnr.", AB.telefon), ("E-Mail", AB.email), ("Homepage", AB.web),
                 ("USt-IdNr.", AB.ust_id), ("Bank", AB.bank), ("IBAN", AB.iban), ("SWIFT-Code", AB.bic)]
        for j, (lab, w) in enumerate(firma):
            b.text(380, 50 + 9.5 * j, lab, R, 7.5)
            b.text(430, 50 + 9.5 * j, w, R, 7.5)
        b.text(545, 170, f"Seite {se.nr}", R, 8, art="r")
        if se.nr == 1:
            b.text(50, 150, f"{AB.name} · {AB.strasse} · {AB.plz} {AB.ort}", R, 6.5)
            for j, zl in enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}"]):
                b.text(50, 166 + 11 * j, zl, R, 10)
            kd = [("Debitorennr.", k["customer_number"])]
            if inv["order_number"]:
                kd.append(("Ihre Referenz", inv["order_number"]))
            if d.get("falle") == "nummer_aehnlich":
                kd.append(("Projektnr.", d["falle_detail"]["projektnr"]))
            for j, (lab, w) in enumerate(kd):
                b.text(50, 248 + 11 * j, lab, R, G)
                b.text(130, 248 + 11 * j, w, R, G)
            b.text(330, 196, "Rechnung", B, 15)
            rechts = [("Rechnungsnr.", inv["number"]), ("Buchungsdatum", inv["date"]),
                      ("Fälligkeitsdatum", z["due_date"]), ("Lieferdatum", inv["service_date"]),
                      ("Zahlungsbedingungen", d["payment_terms_text"][0]), ("Lieferbedingungen", "frei Baustelle")]
            for j, (lab, w) in enumerate(rechts):
                b.text(330, 214 + 11 * j, lab, R, G)
                b.text(425, 214 + 11 * j, w, R, G)
        else:
            b.text(50, 166, f"Rechnung {inv['number']}", B, 11)
            b.text(50, 180, f"Buchungsdatum {inv['date']}", R, G)
        y_kopf = Y_KOPF1 if se.nr == 1 else Y_KOPF2
        for x, txt, a in [(X_NR, "Nr.", "l"), (X_BEZ, "Beschreibung", "l"), (X_MENGE, "Menge", "r"),
                          (X_EH, "Einheit", "l"), (X_EP, "VK-Preis", "r"), (X_UST, "MwSt. %", "r"),
                          (X_GP, "Betrag", "r")]:
            b.text(x, y_kopf, txt, B, G, art=a)
        b.linie(50, y_kopf + 4, 545, 0.5)
        y = y_kopf + 17
        for i in se.pos:
            p = ps[i]
            b.text(X_NR, y, p.artnr, R, G)
            b.text(X_MENGE, y, menge(p.qty), R, G, art="r")
            b.text(X_EH, y, EINHEIT[p.unit], R, G)
            b.text(X_EP, y, zahl(p.preis), R, G, art="r")
            b.text(X_UST, y, "19", R, G, art="r")
            b.text(X_GP, y, zahl(p.gesamt), R, G, art="r")
            for j, zl in enumerate(p.beschreibung):
                b.text(X_BEZ, y + TAKT * j, zl, R, G)
            y += TAKT * (len(p.beschreibung) + 0.2)
        if se.summen:
            b.linie(330, y - 5, 545, 0.5)
            zeilen = [("Zwischensumme", t["net"], R), ("Gesamt EUR ohne MwSt.", t["net"], B),
                      ("19 % MwSt.", t["vat"], R), ("Gesamt EUR inkl. MwSt.", t["gross"], B)]
            for j, (lab, w, f) in enumerate(zeilen):
                b.text(330, y + 7 + 12 * j, lab, f, G)
                b.text(X_GP, y + 7 + 12 * j, zahl(Decimal(w)), f, G, art="r")
            b.linie(330, y + 7 + 12 * 3 - 9, 545, 0.4)
        c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"10{rng.randint(30, 39)}{n:02d}"


def bestellnr(rng):
    return f"{rng.randint(4500000000, 4500999999)}"


def muss(d, ps, seiten, s):
    t, inv = d["totals_printed"], d["invoice"]
    return [(len(seiten), f"Gesamt EUR inkl. MwSt. {zahl(Decimal(t['gross']))}"),
            (1, f"Rechnungsnr. {inv['number']}"), (1, f"Buchungsdatum {inv['date']}"),
            (1, f"Zahlungsbedingungen {d['payment_terms_text'][0]}")]


SPEZ = [
    Spez(30, anzahl=4, lang=1, zahlung="netto", ziel=14, holdout=True,
         notiz="Hold-out: Kopf/Fuß als Bild, Ihre Referenz"),
    Spez(32, anzahl=6, lang=2, zahlung="skonto", skonto=2, skonto_tage=8, ziel=30, holdout=True,
         notiz="Hold-out: 3 Namenszeilen, Skonto in Zahlungsbedingungen"),
    Spez(31, anzahl=34, lang=4, zahlung="netto", ziel=30, holdout=True, bestellung=False, seiten=2,
         notiz="Hold-out: 2 Seiten, kein Übertrag gedruckt"),
    Spez(29, anzahl=3, zahlung="netto", ziel=14, holdout=True,
         notiz="Hold-out: Postfach-Anschrift (einziger Postfach-Beleg der Familie)"),
    Spez(26, anzahl=7, lang=3, zahlung="skonto", skonto=3, skonto_tage=10, ziel=30, holdout=True,
         bestellung=False, notiz="Hold-out: ohne Referenz, mehrzeilige Bezeichnungen"),
]
for _s in SPEZ:
    _s.extra = {"uebertrag_gedruckt": False, "kopf_fuss_als_bild": True}
# A1 (20.11.2026): neuer Hold-out-Beleg, nur angehängt (Belege 1–5 bleiben byte-gleich)
SPEZ.append(Spez(30, anzahl=5, lang=1, zahlung="skonto", skonto=2, skonto_tage=8, ziel=30, holdout=True,
                 falle="nummer_aehnlich", falle_detail={"projektnr": "103619"},
                 extra={"uebertrag_gedruckt": False, "kopf_fuss_als_bild": True},
                 notiz="Hold-out FALLE: Projektnr. im Format der Rechnungsnummer neben der Debitorennr."))

FAMILIE = Familie(
    nr=8, ordner="f08_bildkopf", titel="Kopf und Fuß als Bild, Label neben Wert (nach Business Central 1306)",
    absender=AB, quelle="Q10", seed=26_4728, schrift="Times", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
