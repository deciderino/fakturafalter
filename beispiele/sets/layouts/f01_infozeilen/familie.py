"""F1 „Infozeilen“ – nach der weclapp-Rechnungsvorlage (QUELLEN.md, Q1).

Wortlaut und Anordnung wie in der Vorlage: Absenderzeile über der Anschrift links, Kontaktblock rechts oben,
Infoblock als zwei Spalten „Label: Wert“ zwischen Überschrift und Tabelle (links Rechnungs-Nr., Auftrags-Nr.,
Komission, Kunden-Nr., Bestell-Nr.; rechts Rechnungsdatum, Lieferdatum, Bearbeiter, Telefon, E-Mail), Daten als
TT.MM.JJ, Tabelle Pos. | Art-Nr. | Bezeichnung | Menge | Einheit | Preis/Einh. (€) | Gesamt (€) mit Preisen ohne
€-Zeichen, Versand als normale Position, Summen rechts mit vorangestelltem € („Summe Netto“ / „19,00% USt. auf
… €“ / „Endsumme“), „Lieferbedingung“, Zahlungsbedingung „10 Tage 5% Skonto, 30 Tage ohne Abzug“, Bank mit
Konto/BLZ/IBAN/BIC im Fuß. Helvetica 9 pt.

Die Auftrags-Nr. ist die Auftragsnummer des Verkäufers und steht nur in ``test_flags.auftragsnummer``; BT-13 ist
die Bestell-Nr. des Käufers."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, GRAU, Absender, Artikel, Blatt, Familie, Spez, de_kurz, iban_de, leinwand,  # noqa: E402
                     menge, positionen, seitenplan, ust_id_de, zahl)

R, B = "Helvetica", "Helvetica-Bold"
G = 9.0
AB = Absender("Kaltwasser Armaturen GmbH", "Lindenallee 4", "34117", "Kassel", ust_id_de("27183104"),
              iban_de("0041170012"), "KALTDEX1XXX", "Beispielbank Kassel", "info@kaltwasser.example",
              "www.kaltwasser-armaturen.example", "0561 000000-0", "Amtsgericht Kassel HRB 00000", "Henrike Kaltwasser")
KATALOG = [
    Artikel("KH-1015-MS", "Kugelhahn DN15 Messing vernickelt", (7, 19)),
    Artikel("KH-1025-MS", "Kugelhahn DN25 Messing vernickelt", (14, 32)),
    Artikel("RV-2020-RG", "Rückflussverhinderer DN20 Rotguss", (18, 46)),
    Artikel("DM-3010-ED", "Druckminderer 1/2\" mit Manometer", (39, 89)),
    Artikel("SF-4032-VA", "Schmutzfänger DN32 Edelstahl", (45, 120)),
    Artikel("TH-5100-WS", "Thermostatkopf weiß, Fühler eingebaut", (9, 24), mengen=(5, 10, 20, 25)),
    Artikel("SV-6015-MS", "Strangregulierventil DN15", (36, 78)),
    Artikel("FL-7065-ST", "Flanschdichtung DN65 PN16", (2.4, 7.8), mengen=(10, 20, 50)),
    Artikel("MA-8040-GL", "Manometer 0–10 bar, Ø 63 mm", (8, 21)),
    Artikel("MS-9001", "Montage Armaturengruppe vor Ort", (58, 74), unit="Std.", mengen=(2, 3, 4, 6)),
]
LANG = ["Farbe Grün, Musterartikel", "mit Entleerung und Kappe, Gewinde nach DIN EN 10226-1",
        "Ausführung für Trinkwasser, DVGW-geprüft", "inkl. Anfahrt im Stadtgebiet Kassel"]
KONTO = "41 17 00 12"
VERSAND = ("V-13KG", "Versand und Verpackung", "11.90")
X_POS, X_ART, X_BEZ, X_MENGE, X_EH, X_EP, X_GP = 56, 84, 152, 378, 384, 486, 540
TAB_KOPF, TAB0, TAKT = 352.0, 371.0, 11.5
BEZ_BREITE = X_MENGE - X_BEZ - 36


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    if s.zahlung == "skonto":
        return [f"{s.skonto_tage} Tage {s.skonto}% Skonto, {s.ziel} Tage ohne Abzug"]
    if s.zahlung == "fest":                      # nicht in der Vorlage; im Stil der Vorlage formuliert
        return [f"Zahlbar bis {de_kurz(faellig)} ohne Abzug"]
    return [f"{s.ziel} Tage ohne Abzug"]


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G,
                      VERSAND if s.versand else None, max_zeilen=2)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 1, erste=28, folge=50, summen=5)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t = d["buyer"], d["invoice"], d["totals_printed"]
    # Kontaktblock rechts
    for j, (txt, f) in enumerate([(AB.name, B), (AB.strasse, R), (f"{AB.plz} {AB.ort}", R),
                                  (f"+49 (0) {AB.telefon[1:]}", R), (AB.email, R), (AB.web, R)]):
        b.text(400, 52 + 11 * j, txt, f, 8.5)
    # Absenderzeile und Anschrift
    b.text(56, 132, f"{AB.name} {AB.strasse} | {AB.plz} {AB.ort}", R, 7, GRAU)
    zeilen = k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}"]
    for j, z in enumerate(zeilen):
        b.text(56, 150 + 12 * j, z, R, 10)
    b.text(56, 250, "Rechnung", B, 14)
    fl = d["test_flags"]
    links = [("Rechnungs-Nr.:", inv["number"]), ("Auftrags-Nr.:", fl["auftragsnummer"]),
             ("Komission:", fl["komission"]), ("Kunden-Nr.:", k["customer_number"])]
    if inv["order_number"]:
        links.append(("Bestell-Nr.:", inv["order_number"]))
    if d.get("falle") == "angebot_nr":
        links.insert(1, ("Angebots-Nr.:", d["falle_detail"]["angebots_nr"]))
    rechts = [("Rechnungsdatum:", de_kurz(_d(inv["date"]))), ("Lieferdatum:", de_kurz(_d(inv["service_date"]))),
              ("Bearbeiter:", fl["bearbeiter"]), ("Telefon:", AB.telefon), ("E-Mail:", AB.email)]
    for j, (lab, w) in enumerate(links):
        b.text(56, 272 + 12 * j, lab, R, 8.5)
        b.text(140, 272 + 12 * j, w, R, 8.5)
    for j, (lab, w) in enumerate(rechts):
        b.text(360, 272 + 12 * j, lab, R, 8.5)
        b.text(440, 272 + 12 * j, w, R, 8.5)
    # Tabelle
    for x, txt, a in [(X_POS, "Pos.", "l"), (X_ART, "Art-Nr.", "l"), (X_BEZ, "Bezeichnung", "l"),
                      (X_MENGE, "Menge", "r"), (X_EH, "Einheit", "l"), (X_EP, "Preis/Einh. (€)", "r"),
                      (X_GP, "Gesamt (€)", "r")]:
        b.text(x, TAB_KOPF, txt, B, 8.5, art=a)
    b.linie(56, TAB_KOPF + 4, 540, 0.6)
    z = 0
    for i, p in enumerate(ps):
        y = TAB0 + TAKT * z
        b.text(X_POS, y, str(i + 1), R, G)
        b.text(X_ART, y, p.artnr, R, G)
        b.text(X_MENGE, y, menge(p.qty, 2), R, G, art="r")
        b.text(X_EH, y, p.unit, R, G)
        b.text(X_EP, y, zahl(p.preis), R, G, art="r")
        b.text(X_GP, y, zahl(p.gesamt), R, G, art="r")
        for j, zl in enumerate(p.beschreibung):
            b.text(X_BEZ, y + TAKT * j, zl, R, G)
        z += len(p.beschreibung) + 1
    y = TAB0 + TAKT * z
    b.linie(330, y - 8, 540, 0.4)
    for j, (lab, w, f) in enumerate([("Summe Netto", t["net"], R),
                                     (f"19,00% USt. auf {zahl(Decimal(t['net']))} €", t["vat"], R),
                                     ("Endsumme", t["gross"], B)]):
        b.text(470, y + 6 + 14 * j, lab, f, G, art="r")
        b.text(X_GP, y + 6 + 14 * j, "€ " + zahl(Decimal(w)), f, G, art="r")
    y += 6 + 14 * 3 + 16
    b.text(56, y, "Lieferbedingung: " + ("Postversand" if s.versand else "Abholung"), R, G)
    for j, zl in enumerate(d["payment_terms_text"]):
        b.text(56, y + 22 + 12 * j, zl, R, G)
    # Fuß
    b.text(297.6, 795, f"{AB.name} · {AB.bank} · Konto {KONTO} · BLZ 000 000 00 · IBAN {AB.iban} · BIC {AB.bic}",
           R, 7, art="m")
    b.text(297.6, 805, f"Sitz der Gesellschaft: {AB.ort} · Geschäftsführung: {AB.gf} · Handelsregister: "
                       f"{AB.register} · USt-IdNr. {AB.ust_id}", R, 7, art="m")
    c.showPage()
    c.save()


def _d(s):
    from datetime import date
    t, m, j = map(int, s.split("."))
    return date(j, m, t)


def nummer(n, rng, datum):
    return f"K{datum:%y}{1600 + n * 17 + rng.randint(0, 9)}"


def bestellnr(rng):
    return str(rng.randint(360000, 389999))


def muss(d, ps, seiten, s):
    t = d["totals_printed"]
    return [(1, f"Summe Netto € {zahl(Decimal(t['net']))}"), (1, f"Endsumme € {zahl(Decimal(t['gross']))}"),
            (1, f"Rechnungsdatum: {de_kurz(_d(d['invoice']['date']))}"),
            (1, f"Auftrags-Nr.: {d['test_flags']['auftragsnummer']}")]


SPEZ = [
    Spez(0, anzahl=4, lang=1, zahlung="skonto", skonto=2, skonto_tage=10, ziel=30, versand=True,
         notiz="einzeilige Anschrift, 2% Skonto 10 Tage, Versandposition"),
    Spez(3, anzahl=5, lang=2, zahlung="netto", ziel=14, notiz="Firmenname zweizeilig, 14 Tage ohne Abzug"),
    Spez(2, anzahl=3, zahlung="fest", ziel=21, versand=True, bestellung=False,
         notiz="3 Namenszeilen, festes Zahldatum TT.MM.JJ (nicht in der Vorlage), ohne Bestellnummer"),
    Spez(5, anzahl=6, lang=2, zahlung="skonto", skonto=3, skonto_tage=14, ziel=30, versand=True, holdout=True,
         notiz="Hold-out: z. Hd.-Zeile, 3 % Skonto 14 Tage"),
    Spez(6, anzahl=4, zahlung="netto", ziel=14, holdout=True, pruefen="netto",
         notiz="Hold-out PRÜFEN: gedrucktes Netto 10,00 € über Σ Positionen"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(1, anzahl=5, lang=1, zahlung="skonto", skonto=2, skonto_tage=10, ziel=30, versand=True, holdout=True,
         fehler="summe_positionen", notiz="Hold-out FEHLER: Versandposition nicht im gedruckten Netto"),
    Spez(4, anzahl=4, lang=1, zahlung="netto", ziel=14, holdout=True, falle="angebot_nr",
         falle_detail={"angebots_nr": "A261662"},
         notiz="Hold-out FALLE: Angebots-Nr. direkt unter der Rechnungs-Nr."),
]
BEARBEITER = ["Dorothea Schäfer", "Malte Riedel", "Ilka Brosowski"]
KOMISSION = ["Lager Nord", "Baustelle Fuldaer Straße", "Wartung Heizzentrale", "Neubau Halle 3",
             "Ersatzteile Pumpenhaus"]


def _beleg_extra(fam):
    import random
    r = random.Random(fam.seed * 7)
    for s in fam.spez:
        s.extra = {"bearbeiter": r.choice(BEARBEITER), "auftragsnummer": f"O{r.randint(1700, 1999)}",
                   "komission": r.choice(KOMISSION)}


FAMILIE = Familie(
    nr=1, ordner="f01_infozeilen", titel="Infozeilen-Block über der Tabelle (nach weclapp-Vorlage)",
    absender=AB, quelle="Q1", seed=26_4721, schrift="Helvetica", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen,
    datum_druck=de_kurz, datum_format="TT.MM.JJ")
_beleg_extra(FAMILIE)
