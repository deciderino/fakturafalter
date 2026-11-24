"""F10 „Satztabelle“ – nach der Mustangproject-Beispielrechnung RE-20201121/508 (ZUGFeRD-Korpus; QUELLEN.md, Q7),
deutsch gedruckt. Gemischte Sätze 7 % und 19 %, USt getrennt je Satz in einer kleinen Steuertabelle.

Wortlaut und Anordnung wie im Muster: Datum oben links, Absenderzeile über der Anschrift, Firmenblock rechts
(Anschrift, Telefon, Register, Web, Geschäftsführer). Darunter „Kunde: <Nr.>“, „Ihre Bestellung <Nr.>“,
„Rechnung Nr. … vom …“, „Lieferdatum …“. Tabelle Menge | Produkt | USt | Preis | Gesamt mit Gitterlinien, Menge
mit zwei Nachkommastellen ohne Einheitenspalte (die Einheit steht wie im Muster im Produktnamen, z. B.
„(Stunden)“). Summen: „Nettosumme:“, „zzgl. USt“, Steuertabelle USt | Nettobetrag | USt-Betrag je Satz,
„USt gesamt:“, „Zahlbetrag:“, danach „Bitte überweisen bis …“. Fuß rechts mit USt-IdNr., IBAN, BIC, Bank,
Kontoinhaber, „Seite 1/1“ in der Mitte.

Ganze Familie Hold-out (GUI-Grenzfall: mehrere USt-Zeilen, siehe README). Kein Label über Wert.
Weggelassen: Preise mit drei Nachkommastellen (0,025 €) aus dem Muster – BT-146 hat im Rahmen zwei Stellen."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, Absender, Artikel, Blatt, Familie, Spez, de, iban_de, leinwand,  # noqa: E402
                     positionen, seitenplan, ust_id_de, zahl)

R, B = "Helvetica", "Helvetica-Bold"
G = 9.0
AB = Absender("Leselust Medienvertrieb GmbH", "Kohlgartenstraße 18", "04315", "Leipzig",
              ust_id_de("13660597"), iban_de("0086055310"), "LESEDEX1LEJ", "Beispielbank Leipzig",
              "info@leselust-medien.example", "www.leselust-medien.example", "0341 000000-0",
              "HRB 000000", "Ingrid Fohlmann")
KATALOG = [
    Artikel("B-01", "Sachbuch: Stadtgeschichte Leipzig, gebunden", (24, 34), mengen=(1, 2, 5, 10), satz=7),
    Artikel("B-02", "Kinderbuch: Die kleine Eule, Pappbilderbuch", (9, 14), mengen=(5, 10, 20), satz=7),
    Artikel("B-03", "Roman: Nebel über der Elster, Taschenbuch", (11, 13), mengen=(5, 10, 25), satz=7),
    Artikel("B-04", "Wörterbuch Deutsch–Englisch, Schulausgabe", (18, 26), mengen=(10, 20, 30), satz=7),
    Artikel("B-05", "Hörbuch: Klassiker für Kinder, 3 CDs", (14, 22), mengen=(2, 5, 10), satz=7),
    Artikel("P-11", "Notizbücher: A5 kariert, 96 Blatt", (2.5, 4.5), mengen=(20, 50, 100), satz=19),
    Artikel("P-12", "Füllhalter: Schulfüller mit Patronen", (9, 16), mengen=(10, 20, 30), satz=19),
    Artikel("P-13", "Geschenkpapier: Rolle 2 m, sortiert", (1.8, 3.2), mengen=(25, 50, 100), satz=19),
    Artikel("P-14", "Lesezeichen: Leder, geprägt", (3, 6), mengen=(20, 50), satz=19),
    Artikel("D-21", "Autorenlesung (Stunden): Lesung mit Gespräch", (120, 180), unit="Std.", mengen=(1, 2, 3),
            satz=19),
    Artikel("D-22", "Regalberatung (Stunden): Sortimentsplanung vor Ort", (75, 95), unit="Std.",
            mengen=(1, 2, 4), satz=19),
]
LANG = ["Lieferung in Kartons zu je 20 Stück", "inklusive Anfahrt im Stadtgebiet",
        "Remission ausgeschlossen, Sonderbestellung"]
X0, X1, X2, X3, X4, X5 = 40, 100, 380, 430, 490, 555      # Spaltengrenzen des Gitters
BEZ_BREITE = X2 - X1 - 10
TAKT = 11.0


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    t = [f"Bitte überweisen bis {de(faellig)}."]
    if s.zahlung == "skonto":
        t.append(f"Bei Zahlung bis {de(sk_datum)} gewähren wir {s.skonto} % Skonto.")
    return t


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 0.4, erste=30, folge=50, summen=14)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t = d["buyer"], d["invoice"], d["totals_printed"]
    b.text(40, 50, inv["date"], R, G)
    for j, zl in enumerate([AB.name, AB.strasse, f"{AB.plz} {AB.ort}", f"Telefon {AB.telefon}", AB.register,
                            AB.web, f"Geschäftsführerin: {AB.gf}", AB.email]):
        b.text(400, 80 + 11 * j, zl, R, 8)
    b.text(45, 130, f"{AB.name}  ●  {AB.strasse}  ●  {AB.plz} {AB.ort}", R, 6.5)
    for j, zl in enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}"]):
        b.text(50, 150 + 14 * j, zl, R, 10)
    y = 255
    b.text(40, y, f"Kunde: {k['customer_number']}", R, G)
    y += 22
    if inv["order_number"]:
        b.text(40, y, f"Ihre Bestellung {inv['order_number']}", R, G)
        y += 13
    b.text(40, y, f"Rechnung Nr. {inv['number']} vom {inv['date']}", B, 11)
    b.text(40, y + 14, f"Lieferdatum {inv['service_date']}", R, G)
    y += 36
    b.kasten(X0, y - 11, X5, y + 4, 0.5)
    for x, tx, a in [(X0 + 4, "Menge", "l"), (X1 + 4, "Produkt", "l"), (X2 + 4, "USt", "l"),
                     (X4 - 4, "Preis", "r"), (X5 - 4, "Gesamt", "r")]:
        b.text(x, y, tx, B, G, art=a)
    for x in (X1, X2, X3, X4):
        c.line(x, A4[1] - (y - 11), x, A4[1] - (y + 4))
    y += 4
    for p in ps:
        h = TAKT * len(p.beschreibung) + 5
        b.kasten(X0, y, X5, y + h, 0.5)
        for x in (X1, X2, X3, X4):
            c.line(x, A4[1] - y, x, A4[1] - (y + h))
        yy = y + 11
        b.text(X0 + 4, yy, zahl(p.qty), R, G)
        for j, zl in enumerate(p.beschreibung):
            b.text(X1 + 4, yy + TAKT * j, zl, R, G)
        b.text(X2 + 4, yy, f"{p.satz}%", R, G)
        b.text(X4 - 4, yy, f"{zahl(p.preis)} €", R, G, art="r")
        b.text(X5 - 4, yy, f"{zahl(p.gesamt)} €", R, G, art="r")
        y += h
    y += 16
    b.text(40, y, f"Nettosumme: {zahl(Decimal(t['net']))} €", B, G)
    y += 20
    b.text(40, y, "zzgl. USt", R, G)
    y += 16
    for x, tx in [(40, "USt"), (150, "Nettobetrag"), (260, "USt-Betrag")]:
        b.text(x, y, tx, B, G)
    for z in d["vat_breakdown"]:
        y += 13
        b.text(40, y, f"{Decimal(z['rate']):.0f}%", R, G)
        b.text(150, y, f"{zahl(Decimal(z['net']))} €", R, G)
        b.text(260, y, f"{zahl(Decimal(z['vat']))} €", R, G)
    y += 22
    b.text(150, y, f"USt gesamt: {zahl(Decimal(t['vat']))} €", R, G)
    y += 14
    b.text(40, y, f"Zahlbetrag: {zahl(Decimal(t['gross']))} €", B, G)
    y += 34
    for j, zl in enumerate(d["payment_terms_text"]):
        b.text(40, y + 13 * j, zl, R, G)
    for j, zl in enumerate([f"USt-IdNr.: {AB.ust_id}", f"IBAN {AB.iban}", f"BIC {AB.bic}", AB.bank,
                            f"Kontoinhaber: {AB.name}"]):
        b.text(400, 760 + 10 * j, zl, R, 7.5)
    b.text(297.6, 790, "Seite 1/1", R, 8, art="m")
    c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"RE-{datum:%Y%m%d}/{rng.randint(500, 899)}"


def bestellnr(rng):
    return f"AB{rng.randint(100, 999)}"


def muss(d, ps, seiten, s):
    t, inv = d["totals_printed"], d["invoice"]
    return [(1, f"Rechnung Nr. {inv['number']} vom {inv['date']}"), (1, f"USt gesamt: {zahl(Decimal(t['vat']))} €"),
            (1, f"Zahlbetrag: {zahl(Decimal(t['gross']))} €")]


SPEZ = [
    Spez(33, anzahl=5, lang=1, zahlung="fest", ziel=21, holdout=True, notiz="Hold-out: 7/19 %, Bücher und Papeterie"),
    Spez(36, anzahl=4, zahlung="fest", ziel=30, holdout=True, notiz="Hold-out: Kunde mit drei Namenszeilen"),
    Spez(27, anzahl=3, zahlung="skonto", skonto=2, skonto_tage=10, ziel=30, bestellung=False, holdout=True,
         notiz="Hold-out: ohne Bestellnummer, Skonto"),
    Spez(31, anzahl=7, lang=2, zahlung="fest", ziel=14, holdout=True, notiz="Hold-out: mehrzeilige Produkte"),
    Spez(22, anzahl=4, zahlung="fest", ziel=30, holdout=True, notiz="Hold-out: mit Dienstleistung in Stunden"),
]

FAMILIE = Familie(
    nr=10, ordner="f10_satztabelle", titel="USt je Satz in eigener Tabelle, 7/19 % (nach Mustangproject)",
    absender=AB, quelle="Q7", seed=26_5081, schrift="Helvetica", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
