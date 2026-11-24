"""F9 „Steuerspalte“ – nach der Symtrax-Compleo-Beispielrechnung „Handelsrechnung“ (ZUGFeRD-Muster; QUELLEN.md,
Q8). Gemischte Sätze 7 % und 19 % je Position, aber nur EINE USt-Zeile in den Belegsummen.

Wortlaut und Anordnung wie im Muster, durchgehend Courier: „Handelsrechnung Nr. … vom …“, darunter Zeilen
„Label : Wert“ mit ausgerichteten Doppelpunkten (Liefer- und Leistungsdatum, Kundennummer, Bestellnummer,
Währung). Blöcke „Verkäufer:“ und „Käufer:“ nebeneinander statt Anschriftfeld, „Rechnung gemäß Bestellung vom …“.
Tabelle mit zweizeiligem Kopf; Steuerspalte je Position „19 % VAT (S)“ bzw. „7 % VAT (S)“ wie im Muster,
Menge „20 Stk“. Belegsummen Positionssumme / Rechnungssumme ohne USt. / Steuerbetrag / Bruttosumme / Zahlbetrag –
ein einziger Steuerbetrag über beide Sätze, keine Aufschlüsselung je Satz im Druck. Zahlungsbedingungen
„Zahlbar innerhalb 30 Tagen netto bis …, 3% Skonto innerhalb 10 Tagen bis …“.

Weggelassen (OUT bzw. kein Datenfeld): die Steuer-Aufschlüsselungstabelle des Musters, Zu-/Abschläge auf
Belegebene, Anzahlungen."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, Absender, Artikel, Blatt, Familie, Spez, de, iban_de, leinwand, menge,  # noqa: E402
                     positionen, seitenplan, ust_id_de, zahl)

R, B = "Courier", "Courier-Bold"
G = 8.0
AB = Absender("Lüders Kaffeerösterei GmbH", "Sandtorkai 31", "20457", "Hamburg",
              ust_id_de("11823604"), iban_de("0037766120"), "LUEDDEX1HAM", "Beispielbank Hamburg",
              "rechnung@lueders-kaffee.example", "www.lueders-kaffee.example", "040 000000-0",
              "Amtsgericht Hamburg HRB 000000", "Jens Lüders")
STEUERNR = "27/000/00000"
EINHEIT = {"Stk.": "Stk", "Std.": "Std"}
KATALOG = [
    Artikel("KF-1001", "Röstkaffee Espresso, ganze Bohne 1 kg", (17, 24), mengen=(5, 10, 20), satz=7),
    Artikel("KF-1002", "Röstkaffee Crema, ganze Bohne 1 kg", (15, 21), mengen=(5, 10, 20), satz=7),
    Artikel("KF-1010", "Filterkaffee gemahlen 500 g", (7.5, 10.5), mengen=(10, 20, 40), satz=7),
    Artikel("KF-1020", "Bio-Tee Darjeeling lose 250 g", (8, 12), mengen=(4, 6, 10), satz=7),
    Artikel("KF-1030", "Kakaopulver 1 kg", (9, 14), mengen=(2, 4, 6), satz=7),
    Artikel("KF-1040", "Rohrzucker-Sticks, Karton 1000 Stück", (16, 23), mengen=(1, 2, 3), satz=7),
    Artikel("ZB-2001", "Siebträgermaschine 2-gruppig", (1890, 2690), mengen=(1,), satz=19),
    Artikel("ZB-2002", "Kaffeemühle mit Mahlgradverstellung", (390, 640), mengen=(1, 2), satz=19),
    Artikel("ZB-2010", "Milchkännchen Edelstahl 0,6 l", (9, 15), mengen=(2, 4, 6), satz=19),
    Artikel("ZB-2020", "Reinigungstabletten, Dose 100 Stück", (11, 19), mengen=(2, 3, 5), satz=19),
    Artikel("ZB-2030", "Porzellantassen Cappuccino, 6er-Set", (24, 38), mengen=(2, 4, 8), satz=19),
    Artikel("ZB-2040", "Coffee-to-go-Becher 300 ml, 1000 Stück", (49, 79), mengen=(1, 2), satz=19),
]
LANG = ["Röstdatum maximal zwei Wochen vor Lieferung", "Lieferung auf Europalette, Mehrweg",
        "Gerät inklusive Einweisung des Personals"]
X_POS, X_ART, X_BEZ, X_MENGE, X_EP, X_ST, X_GP = 40, 62, 112, 338, 400, 410, 555
BEZ_BREITE = 178
TAKT = 10.0
Y_KOPF = 280.0
X_DP = 178          # Doppelpunkt-Spalte der „Label : Wert“-Zeilen


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    t = f"Zahlbar innerhalb {s.ziel} Tagen netto bis {de(faellig)}"
    if s.zahlung == "skonto":
        t += f", {s.skonto}% Skonto innerhalb {s.skonto_tage} Tagen bis {de(sk_datum)}"
    return [t]


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 0.3, erste=30, folge=50, summen=12)


def zeile(b, y, lab, w, f=R, x0=40):
    b.text(x0, y, lab, f, G)
    b.text(X_DP, y, ":", f, G)
    b.text(X_DP + 9.6, y, w, f, G)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Handelsrechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t = d["buyer"], d["invoice"], d["totals_printed"]
    b.text(40, 60, f"Handelsrechnung Nr. {inv['number']} vom {inv['date']}", B, 12)
    kopf = [("Liefer- und Leistungsdatum", inv["service_date"]), ("Kundennummer", k["customer_number"])]
    if inv["order_number"]:
        kopf.append(("Bestellnummer", inv["order_number"]))
    kopf.append(("Währung", "EUR"))
    for j, (lab, w) in enumerate(kopf):
        zeile(b, 84 + 11 * j, lab, w)
    vk = [AB.name, AB.strasse, f"{AB.plz} {AB.ort}", "Deutschland", f"Steuernummer : {STEUERNR}",
          f"USt.-Id.-Nr. : {AB.ust_id}"]
    kf = k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}", "Deutschland"]
    b.text(40, 148, "Verkäufer:", B, G)
    b.text(310, 148, "Käufer:", B, G)
    for j, zl in enumerate(vk):
        b.text(40, 160 + 10 * j, zl, R, G)
    for j, zl in enumerate(kf):
        b.text(310, 160 + 10 * j, zl, R, G)
    if inv["order_number"]:
        bd = datetime.strptime(inv["date"], "%d.%m.%Y").date() - timedelta(days=9)
        b.text(40, 250, f"Rechnung gemäß Bestellung vom {de(bd)}", R, G)
    else:
        b.text(40, 250, "Rechnung gemäß Lieferung", R, G)
    b.linie(40, Y_KOPF - 10, 555, 0.6)
    for x, t1, t2, a in [(X_POS, "Pos", "", "l"), (X_ART, "Art.-Nr.", "", "l"), (X_BEZ, "Bezeichnung", "", "l"),
                         (X_MENGE, "Menge", "", "r"), (X_EP, "Nettopreis", "je Einheit", "r"),
                         (X_ST, "Steuer", "Satz (Kat.)", "l"), (X_GP, "Nettobetrag", "EUR", "r")]:
        b.text(x, Y_KOPF, t1, B, G, art=a)
        if t2:
            b.text(x, Y_KOPF + 9, t2, R, G, art=a)
    b.linie(40, Y_KOPF + 13, 555, 0.6)
    y = Y_KOPF + 25
    for i, p in enumerate(ps):
        b.text(X_POS, y, f"{i + 1:>3}", R, G)
        b.text(X_ART, y, p.artnr, R, G)
        b.text(X_MENGE, y, f"{menge(p.qty)} {EINHEIT[p.unit]}", R, G, art="r")
        b.text(X_EP, y, zahl(p.preis), R, G, art="r")
        b.text(X_ST, y, f"{p.satz} % VAT (S)", R, G)
        b.text(X_GP, y, zahl(p.gesamt), R, G, art="r")
        for j, zl in enumerate(p.beschreibung):
            b.text(X_BEZ, y + TAKT * j, zl, R, G)
        y += TAKT * (len(p.beschreibung) + 0.3)
    b.linie(40, y - 5, 555, 0.6)
    y += 10
    b.text(300, y, "Belegsummen", B, G)
    pos_summe = sum(p.gesamt for p in ps)
    for j, (lab, w, f) in enumerate([("Positionssumme", pos_summe, R), ("Rechnungssumme ohne USt.", t["net"], R),
                                     ("Steuerbetrag", t["vat"], R), ("Bruttosumme", t["gross"], R),
                                     ("Zahlbetrag", t["gross"], B)]):
        yy = y + 12 + 11 * j
        b.text(300, yy, lab, f, G)
        b.text(430, yy, ":", f, G)
        b.text(X_GP, yy, zahl(Decimal(w)), f, G, art="r")
    y += 12 + 55 + 16
    b.text(40, y, "Zahlungsbedingungen:", B, G)
    for j, zl in enumerate(d["payment_terms_text"]):
        b.text(40, y + 11 * (j + 1), zl, R, G)
    y += 11 * (len(d["payment_terms_text"]) + 1) + 14
    for j, (lab, w) in enumerate([("Bank", AB.bank), ("IBAN", AB.iban), ("BIC", AB.bic)]):
        zeile(b, y + 11 * j, lab, w)
    for j, zl in enumerate([f"{AB.name} · {AB.strasse} · {AB.plz} {AB.ort} · Tel. {AB.telefon} · {AB.email}",
                            f"{AB.register} · Geschäftsführer: {AB.gf} · {AB.web}"]):
        b.text(297.6, 800 + 9 * j, zl, R, 6.5, art="m")
    c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"{datum:%Y}-{rng.randint(470, 499)}{n:02d}"


def bestellnr(rng):
    return f"B{rng.randint(10000, 99999)}"


def muss(d, ps, seiten, s):
    t, inv = d["totals_printed"], d["invoice"]
    m = [(1, f"Handelsrechnung Nr. {inv['number']} vom {inv['date']}"),
         (1, f"Steuerbetrag : {zahl(Decimal(t['vat']))}"), (1, f"Zahlbetrag : {zahl(Decimal(t['gross']))}")]
    if len({p.satz for p in ps}) > 1:
        m += [(1, "7 % VAT (S)"), (1, "19 % VAT (S)")]
    return m


SPEZ = [
    Spez(32, anzahl=5, lang=1, zahlung="skonto", skonto=3, skonto_tage=10, ziel=30,
         notiz="gemischt 7/19 %, eine USt-Zeile, Skonto mit Datum"),
    Spez(33, anzahl=4, zahlung="netto", ziel=30, bestellung=False,
         notiz="gemischt 7/19 %, ohne Bestellnummer"),
    Spez(34, anzahl=7, lang=2, zahlung="skonto", skonto=2, skonto_tage=14, ziel=30,
         notiz="gemischt 7/19 %, mehrzeilige Bezeichnungen"),
    Spez(18, anzahl=6, lang=1, zahlung="netto", ziel=14, holdout=True,
         notiz="Hold-out: gemischt 7/19 %"),
    Spez(35, anzahl=5, zahlung="skonto", skonto=3, skonto_tage=10, ziel=30, holdout=True, pruefen="ust",
         notiz="Hold-out PRÜFEN: Steuerbetrag 0,10 € über Netto × Satz, Brutto folgt"),
]

FAMILIE = Familie(
    nr=9, ordner="f09_steuerspalte", titel="Steuerspalte je Position, 7/19 %, eine USt-Zeile (nach Symtrax Compleo)",
    absender=AB, quelle="Q8", seed=26_4729, schrift="Courier", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
