"""F4 „Kontaktblock“ – nach der easybill-Rechnungsvorlage 2023 (QUELLEN.md, Q3).

Wortlaut und Anordnung wie in der Vorlage: Logo-Kasten rechts oben, kleine Absenderzeile über der Anschrift,
rechts der Block „So erreichen Sie uns“ mit Internet / E-Mail / Telefon / Telefax / Mobil / Steuer-Nr. /
USt-IDNr. und darunter Datum / Kunde / Rechnung (Label: Wert). Anrede, „nachfolgend berechnen wir Ihnen wie vorab
besprochen:“, „Rechnung <Nr.>“ fett und „Das Rechnungsdatum entspricht dem Leistungsdatum“ (Leistungsdatum =
Rechnungsdatum). Tabelle Pos | Art-Nr. | Bezeichnung | Menge („4,5 Std.“) | Einzelpreis (ohne €) | Betrag
(mit €). Summen Nettobetrag / Umsatzsteuer 19% / Rechnungsbetrag (fett). „Vielen Dank für Ihren Auftrag!“,
„Bitte begleichen Sie den offenen Betrag bis zum TT.MM.JJJJ an die unten aufgeführte Bankverbindung.“,
„Mit freundlichen Grüßen“. Fuß in drei Spalten Zahlungsempfänger / Bankverbindung / BIC, IBAN. Helvetica
(Vorlage: Arial) 9 pt. Keine Bestellnummer (die Vorlage hat keine)."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, GRAU, Absender, Artikel, Blatt, Familie, Spez, de, iban_de,  # noqa: E402
                     leinwand, logo_png, menge, positionen, seitenplan, ust_id_de, zahl)

R, B = "Helvetica", "Helvetica-Bold"
G = 9.0
AB = Absender("Grünwerk Gartenplanung GmbH", "Wilhelmshöher Allee 210", "34119", "Kassel",
              ust_id_de("27104417"), iban_de("0310044170"), "GRUEDEX1KSL", "Beispielbank Nordhessen",
              "rechnung@gruenwerk.example", "www.gruenwerk.example", "0561 000000-40",
              "Amtsgericht Kassel HRB 00000", "Lotte Grünewald")
STEUERNR = "026 000 00000"
KATALOG = [
    Artikel("GP-100", "Planung Außenanlage, Entwurf", (68, 85), unit="Std.", mengen=(2, 3.5, 4.5, 6, 8)),
    Artikel("GP-110", "Pflanzplan mit Pflanzliste", (62, 78), unit="Std.", mengen=(1.5, 2, 3)),
    Artikel("GP-120", "Baustellentermin vor Ort", (58, 72), unit="Std.", mengen=(1, 1.5, 2, 2.5)),
    Artikel("GP-130", "Aufmaß und Bestandsplan", (55, 70), unit="Std.", mengen=(2, 3, 4)),
    Artikel("GP-200", "Pflanzarbeiten Gehölze", (48, 59), unit="Std.", mengen=(4, 6, 8, 12)),
    Artikel("GP-210", "Rasenansaat inkl. Bodenvorbereitung, je m²", (3.2, 4.9), unit="Stk.", mengen=(80, 120, 200)),
    Artikel("GP-300", "Hainbuche Heckenpflanze 100–125 cm", (6.5, 11), mengen=(20, 40, 60)),
    Artikel("GP-310", "Rhododendron 40–50 cm, Container", (19, 32), mengen=(3, 5, 8)),
    Artikel("GP-320", "Rindenmulch 40 l Sack", (4.2, 6.9), mengen=(10, 20, 30)),
    Artikel("GP-330", "Natursteinpflaster Granit, je m²", (42, 64), mengen=(6, 12, 18)),
    Artikel("GP-400", "Anfahrtspauschale", (25, 45), mengen=(1,)),
]
LANG = ["gemäß Angebot und Abstimmung vor Ort",
        "inklusive Entsorgung des Grünschnitts über den Wertstoffhof",
        "Ausführung nach Pflanzplan, Anwachsgarantie zwölf Monate"]
X_POS, X_ART, X_BEZ, X_MENGE, X_EP, X_GP = 56, 82, 138, 392, 470, 540
BEZ_BREITE = 210
TAKT = 11.5
Y_KOPF = 372.0


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    # Vorlage: festes Datum. Skonto ist nicht in der Vorlage und steht im selben Satzbau davor.
    z = []
    if s.zahlung == "skonto":
        z.append(f"Bei Zahlung bis zum {de(sk_datum)} gewähren wir {s.skonto} % Skonto.")
    z.append(f"Bitte begleichen Sie den offenen Betrag bis zum {de(faellig)} an die unten aufgeführte "
             "Bankverbindung.")
    return z


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 0.4, erste=30, folge=50, summen=6)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t = d["buyer"], d["invoice"], d["totals_printed"]
    c.drawImage(ImageReader(logo_png("GW", farbe=(60, 120, 60))), 400, A4[1] - 100, 140, 56)
    b.kasten(396, 40, 544, 104, 0.4, GRAU)
    b.text(56, 142, f"{AB.name} · {AB.strasse} · {AB.plz} {AB.ort}", R, 6.5)
    for j, z in enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}"]):
        b.text(56, 160 + 12 * j, z, R, 10)
    b.text(380, 140, "So erreichen Sie uns", B, 8)
    rechts = [("Internet:", AB.web), ("E-Mail:", AB.email), ("Telefon:", AB.telefon),
              ("Telefax:", AB.telefon[:-1] + "9"), ("Mobil:", "0170 0000000"), ("Steuer-Nr.:", STEUERNR),
              ("USt-IDNr.:", AB.ust_id), None, ("Datum:", inv["date"]), ("Kunde:", k["customer_number"]),
              ("Rechnung:", inv["number"])]
    for j, r in enumerate(rechts):
        if r:
            b.text(380, 152 + 10 * j, r[0], R, 8)
            b.text(440, 152 + 10 * j, r[1], R, 8)
    b.text(56, 290, "Sehr geehrte Damen und Herren,", R, G)
    b.text(56, 303, "nachfolgend berechnen wir Ihnen wie vorab besprochen:", R, G)
    b.text(56, 330, f"Rechnung {inv['number']}", B, 12)
    if inv["service_date"]:
        b.text(56, 344, "Das Rechnungsdatum entspricht dem Leistungsdatum", R, 8)
    for x, txt, a in [(X_POS, "Pos", "l"), (X_ART, "Art-Nr.", "l"), (X_BEZ, "Bezeichnung", "l"),
                      (X_MENGE, "Menge", "r"), (X_EP, "Einzelpreis", "r"), (X_GP, "Betrag", "r")]:
        b.text(x, Y_KOPF, txt, B, 8.5, art=a)
    b.linie(56, Y_KOPF + 4, 540, 0.5)
    y = Y_KOPF + 18
    for i, p in enumerate(ps):
        b.text(X_POS, y, str(i + 1), R, G)
        b.text(X_ART, y, p.artnr, R, G)
        b.text(X_MENGE, y, f"{menge(p.qty)} {p.unit}", R, G, art="r")
        b.text(X_EP, y, zahl(p.preis), R, G, art="r")
        b.text(X_GP, y, zahl(p.gesamt) + " €", R, G, art="r")
        for j, zl in enumerate(p.beschreibung):
            b.text(X_BEZ, y + TAKT * j, zl, R, G)
        y += TAKT * (len(p.beschreibung) + 0.4)
    b.linie(56, y - 6, 540, 0.5)
    for j, (lab, w, f) in enumerate([("Nettobetrag", t["net"], R), ("Umsatzsteuer 19%", t["vat"], R),
                                     ("Rechnungsbetrag", t["gross"], B)]):
        b.text(X_EP, y + 8 + 13 * j, lab, f, G, art="r")
        b.text(X_GP, y + 8 + 13 * j, zahl(Decimal(w)) + " €", f, G, art="r")
    y += 8 + 13 * 3 + 20
    b.text(56, y, "Vielen Dank für Ihren Auftrag!", R, G)
    for j, zl in enumerate(d["payment_terms_text"]):
        b.text(56, y + 16 + 12 * j, zl, R, G)
    y += 16 + 12 * len(d["payment_terms_text"]) + 14
    b.text(56, y, "Mit freundlichen Grüßen", R, G)
    b.text(56, y + 26, AB.gf, R, G)
    for x, kopf, zz in [(56, "Zahlungsempfänger", [AB.name, f"{AB.strasse}, {AB.plz} {AB.ort}"]),
                        (240, "Bankverbindung", [AB.bank, AB.register]),
                        (390, "BIC, IBAN", [AB.bic, AB.iban])]:
        b.text(x, 780, kopf, B, 7, GRAU)
        for j, zl in enumerate(zz):
            b.text(x, 789 + 8.5 * j, zl, R, 7, GRAU)
    c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"{datum:%Y%m}{rng.randint(1, 9) * 10 + n:03d}"


def bestellnr(rng):
    return ""


def muss(d, ps, seiten, s):
    t = d["totals_printed"]
    m = [(1, f"Rechnungsbetrag {zahl(Decimal(t['gross']))} €"), (1, f"Rechnung {d['invoice']['number']}"),
         (1, f"Datum: {d['invoice']['date']}")]
    if d["invoice"]["service_date"]:
        m.append((1, "Das Rechnungsdatum entspricht dem Leistungsdatum"))
    return m


SPEZ = [
    Spez(18, anzahl=4, lang=1, zahlung="fest", ziel=14, bestellung=False,
         notiz="Planungsleistung in Std., festes Zahldatum wie in der Vorlage"),
    Spez(19, anzahl=6, lang=2, zahlung="skonto", skonto=2, skonto_tage=7, ziel=21, bestellung=False,
         notiz="Waren und Std. gemischt, Skontosatz vor dem Zahlsatz"),
    Spez(20, anzahl=5, lang=2, zahlung="fest", ziel=30, bestellung=False,
         notiz="3 Namenszeilen, Bezeichnungen mehrzeilig"),
    Spez(24, anzahl=8, lang=3, zahlung="fest", ziel=14, holdout=True, bestellung=False,
         notiz="Hold-out: 8 Positionen, Mengen mit Komma"),
    Spez(25, anzahl=3, zahlung="fest", ziel=14, holdout=True, bestellung=False, pruefen="ohne_leistungsdatum",
         notiz="Hold-out PRÜFEN: Satz „Das Rechnungsdatum entspricht dem Leistungsdatum“ fehlt, kein BT-72"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(19, anzahl=4, lang=1, zahlung="fest", ziel=14, holdout=True, bestellung=False,
         fehler="rechnungsnummer_fehlt", notiz="Hold-out FEHLER: Rechnungsnummer nicht gedruckt"),
]

FAMILIE = Familie(
    nr=4, ordner="f04_kontaktblock", titel="Kontaktblock „So erreichen Sie uns“ (nach easybill-Vorlage)",
    absender=AB, quelle="Q3", seed=26_4724, schrift="Helvetica", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen, leistung_tage=(0,))
