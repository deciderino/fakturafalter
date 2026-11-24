"""F7 „DIN 5008“ – nach dem Odoo-Rechnungsbericht mit deutschem DIN-5008-Layout (l10n_din5008; QUELLEN.md, Q9).

Wortlaut und Anordnung wie im Odoo-Bericht: Logo links oben, Firmenanschrift rechts im Kopf, Anschriftfeld mit
Absenderzeile links, Informationsblock rechts mit Rechnungsnr. / Rechnungsdatum / Fälligkeitsdatum / Lieferdatum /
Quelle / Referenz (Label und Wert in zwei Spalten, ohne Doppelpunkt; „Quelle“ = Verkaufsauftrag des Verkäufers,
„Referenz“ = Kundenreferenz). Überschrift „Rechnung INV/2026/000NN“. Tabelle Beschreibung | Menge
(„2,00 Stück“) | Einzelpreis | Steuern („19%“) | Betrag („240,00 €“). Summen rechts Nettobetrag /
Umsatzsteuer 19% / Gesamt. Darunter „Zahlungsbedingungen: N Tage“ und „Bitte verwenden Sie die folgende Mitteilung
für Ihre Zahlung: INV/…“. Fuß in vier Spalten mit USt-IdNr., HRB Nr:, IBAN:, BIC: und „Seite: 1 / 1“.
Helvetica (Odoo: Lato) 9 pt."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, GRAU, Absender, Artikel, Blatt, Familie, Spez, iban_de, leinwand, logo_png,  # noqa: E402
                     positionen, seitenplan, ust_id_de, zahl)

R, B = "Helvetica", "Helvetica-Bold"
G = 9.0
AB = Absender("Nordlicht Software GmbH", "Holtenauer Straße 88", "24105", "Kiel",
              ust_id_de("29811046"), iban_de("0090117736"), "NORLDEX1KIE", "Beispielbank Kiel",
              "buchhaltung@nordlicht-software.example", "www.nordlicht-software.example", "0431 000000-0",
              "HRB 00000 KI", "Henrike Jansen")
EINHEIT = {"Stk.": "Stück", "Std.": "Stunden"}
KATALOG = [
    Artikel("NL-LIZ-01", "Lizenz Terminplaner Pro, 12 Monate", (19, 39), mengen=(1, 3, 5, 10)),
    Artikel("NL-LIZ-02", "Lizenz Terminplaner Team, 12 Monate", (49, 89), mengen=(1, 2, 5)),
    Artikel("NL-LIZ-03", "Zusatzmodul Online-Buchung", (9, 19), mengen=(1, 5, 10)),
    Artikel("NL-SUP-01", "Supportpaket Standard, Quartal", (120, 180), mengen=(1,)),
    Artikel("NL-SUP-02", "Supportpaket Premium, Quartal", (240, 360), mengen=(1,)),
    Artikel("NL-DL-01", "Einrichtung und Datenübernahme", (85, 110), unit="Std.", mengen=(2, 4, 6, 8)),
    Artikel("NL-DL-02", "Schulung Anwender (online)", (75, 95), unit="Std.", mengen=(1.5, 2, 3)),
    Artikel("NL-DL-03", "Anpassung Druckvorlagen", (85, 110), unit="Std.", mengen=(1, 2, 3.5)),
    Artikel("NL-DL-04", "Projektleitung", (95, 125), unit="Std.", mengen=(2, 4)),
    Artikel("NL-HW-01", "Kartenleser USB für eGK", (39, 69), mengen=(1, 2, 4)),
]
LANG = ["Abrechnungszeitraum laut Vertrag, Verlängerung automatisch um zwölf Monate",
        "gemäß Ticket und Freigabe durch die Praxisleitung",
        "inklusive Dokumentation der Einstellungen"]
X_BEZ, X_MENGE, X_EP, X_UST, X_GP = 60, 350, 425, 470, 535
BEZ_BREITE = 210
TAKT = 11.0
Y_KOPF = 330.0


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    return [f"Zahlungsbedingungen: {s.ziel} Tage"]


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 0.6, erste=28, folge=50, summen=8)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t, fl, z = d["buyer"], d["invoice"], d["totals_printed"], d["test_flags"], d["payment"]
    c.drawImage(ImageReader(logo_png("NL", farbe=(20, 90, 110))), 60, A4[1] - 80, 150, 50)
    for j, zl in enumerate([AB.name, AB.strasse, f"{AB.plz} {AB.ort}", "Deutschland"]):
        b.text(535, 40 + 10 * j, zl, R, 8, art="r")
    b.text(60, 140, f"{AB.name}, {AB.strasse}, {AB.plz} {AB.ort}", R, 6.5)
    for j, zl in enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}", "Deutschland"]):
        b.text(60, 158 + 11 * j, zl, R, G)
    info = [("Rechnungsnr.", inv["number"]), ("Rechnungsdatum", inv["date"]), ("Fälligkeitsdatum", z["due_date"]),
            ("Lieferdatum", inv["service_date"]), ("Quelle", fl["quelle"])]
    if inv["order_number"]:
        info.append(("Referenz", inv["order_number"]))
    for j, (lab, w) in enumerate(info):
        b.text(370, 140 + 11 * j, lab, R, 8)
        b.text(450, 140 + 11 * j, w, R, 8)
    b.text(60, 290, f"Rechnung {inv['number']}", R, 16)
    for x, txt, a in [(X_BEZ, "Beschreibung", "l"), (X_MENGE, "Menge", "r"), (X_EP, "Einzelpreis", "r"),
                      (X_UST, "Steuern", "r"), (X_GP, "Betrag", "r")]:
        b.text(x, Y_KOPF, txt, B, G, art=a)
    b.linie(60, Y_KOPF + 5, 535, 1.0)
    y = Y_KOPF + 20
    for p in ps:
        b.text(X_MENGE, y, f"{zahl(p.qty)} {EINHEIT[p.unit]}", R, G, art="r")
        b.text(X_EP, y, zahl(p.preis), R, G, art="r")
        b.text(X_UST, y, "19%", R, G, art="r")
        b.text(X_GP, y, zahl(p.gesamt) + " €", R, G, art="r")
        for j, zl in enumerate(p.beschreibung):
            b.text(X_BEZ, y + TAKT * j, zl, R, G)
        y += TAKT * (len(p.beschreibung) + 0.9)
        b.linie(60, y - 10, 535, 0.3, GRAU)
    y += 6
    for j, (lab, w, f) in enumerate([("Nettobetrag", t["net"], B), ("Umsatzsteuer 19%", t["vat"], R),
                                     ("Gesamt", t["gross"], B)]):
        b.text(360, y + 14 * j, lab, f, G)
        b.text(X_GP, y + 14 * j, zahl(Decimal(w)) + " €", f, G, art="r")
        b.linie(360, y + 14 * j + 4, 535, 0.3, GRAU)
    y += 14 * 3 + 20
    b.text(60, y, d["payment_terms_text"][0], R, G)
    b.text(60, y + 14, f"Bitte verwenden Sie die folgende Mitteilung für Ihre Zahlung: {inv['number']}", R, G)
    spalten = [[AB.name, AB.strasse, f"{AB.plz} {AB.ort}"],
               [f"Tel.: {AB.telefon}", AB.email, AB.web],
               [f"USt-IdNr.: {AB.ust_id}", f"HRB Nr: {AB.register.split()[1]} Amtsgericht {AB.ort}",
                f"Geschäftsführung: {AB.gf}"],
               [AB.bank, f"IBAN: {AB.iban}", f"BIC: {AB.bic}"]]
    for x, zz in zip((60, 175, 290, 415), spalten):
        for j, zl in enumerate(zz):
            b.text(x, 786 + 8 * j, zl, R, 6, GRAU)
    b.text(535, 820, "Seite: 1 / 1", R, 6, GRAU, art="r")
    c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"INV/{datum:%Y}/{rng.randint(1, 4) * 100 + n * 7:05d}"


def bestellnr(rng):
    return f"BE-{rng.randint(2026001, 2026999)}"


def muss(d, ps, seiten, s):
    t, inv = d["totals_printed"], d["invoice"]
    return [(1, f"Gesamt {zahl(Decimal(t['gross']))} €"), (1, f"Rechnungsnr. {inv['number']}"),
            (1, f"Fälligkeitsdatum {d['payment']['due_date']}"),
            (1, f"Bitte verwenden Sie die folgende Mitteilung für Ihre Zahlung: {inv['number']}")]


SPEZ = [
    Spez(28, anzahl=3, lang=1, zahlung="netto", ziel=14,
         notiz="Lizenzen und Std., Kundenreferenz als „Referenz“"),
    Spez(27, anzahl=5, lang=2, zahlung="netto", ziel=30, bestellung=False,
         notiz="ohne Referenz, Bezeichnungen mehrzeilig"),
    Spez(23, anzahl=4, lang=1, zahlung="netto", ziel=21,
         notiz="Behörde mit Sachgebiet als 2. Namenszeile"),
    Spez(36, anzahl=6, lang=2, zahlung="netto", ziel=30, holdout=True,
         notiz="Hold-out: 3 Namenszeilen"),
    Spez(19, anzahl=4, zahlung="netto", ziel=14, holdout=True, bestellung=False, pruefen="brutto",
         notiz="Hold-out PRÜFEN: gedrucktes Gesamt 1,00 € über Netto + USt"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(27, anzahl=4, lang=1, zahlung="netto", ziel=30, holdout=True, fehler="faelligkeit_vor_datum",
         notiz="Hold-out FEHLER: Fälligkeitsdatum = Rechnungsdatum − 30 Tage"),
]


def _beleg_extra(fam):
    import random
    r = random.Random(fam.seed * 7)
    for sp in fam.spez:
        sp.extra = {"quelle": f"S{r.randint(100, 999):05d}"}


FAMILIE = Familie(
    nr=7, ordner="f07_din5008", titel="DIN-5008-Informationsblock ohne Doppelpunkt (nach Odoo l10n_din5008)",
    absender=AB, quelle="Q9", seed=26_4727, schrift="Helvetica", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    kundennummer_gedruckt=False, zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
_beleg_extra(FAMILIE)
