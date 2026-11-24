"""F3 „Seitenleiste“ – nach JTL-Wawi/List & Label „business 2.0“ (QUELLEN.md, Q4).

Wortlaut und Anordnung wie in der Vorlage: großes Logo oben links, rechte Seitenleiste (senkrechte Linie, als Form
XObject auf jeder Seite per ``Do`` eingesetzt) mit Absender, USt-IdNr., Gläubiger-IdNr., Tel/Fax, Mail/Web,
Bearbeiter und Bankblock (Name / IBAN: / BIC: / Bank); darunter, auf Höhe der Tabelle und auf jeder Seite, die
Belegdaten als „Label über Wert“ (Rechnungsnummer, Rechnungsdatum, Auftragsnummer, Kundennummer, Zahlungsart,
Versandart, Lieferdatum (vorauss.)). „RECHNUNG“ links, „Landsberg am Lech, den TT.MM.JJJJ“ und „Seite: 1 / 3“
rechts. Tabelle neben der Seitenleiste: Pos | Menge („2 Stück“) | Art. Nr. | Bezeichnung | Netto EP | MwSt
(„19 %“) | Netto GP mit „€“, darunter klein die Druckbeschreibung. Mehrseitig: unten „Zwischensumme 42.760,41 €“,
oben auf der Folgeseite „Übertrag von Seite 1 42760,41“ (ohne Tausenderpunkt und ohne €, wie in der Vorlage).
Summen Gesamt Netto / zzgl. MwSt (19 %) / Rechnungsbetrag, danach „Versandart:“, „Zahlungsart:“,
„Zahlungsziel: N Tage“ und eine Anmerkung. Kein Fuß. Helvetica 7,5 pt. Content-Stream-Reihenfolge ≠
Lesereihenfolge: Seitenleiste, Belegdaten, Summen, Tabellenzeilen von unten nach oben, Tabellenkopf, Überschrift,
zuletzt die Anschrift.

Die Auftragsnummer ist die Auftragsnummer des Verkäufers (``test_flags.auftragsnummer``), keine Bestellnummer
des Käufers; BT-13 bleibt leer. Weggelassen (OUT bzw. ohne Datenfeld): Rabattzeile, Lieferadresse,
„Ihre USt.-Ident.Nr“ des Käufers."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, SCHWARZ, Absender, Artikel, Blatt, Familie, Spez, iban_de,  # noqa: E402
                     leinwand, logo_png, menge, positionen, seitenplan, ust_id_de, zahl)

R, B = "Helvetica", "Helvetica-Bold"
G = 7.5
AB = Absender("Seeberger Radsport-Teile GmbH", "Gewerbering 27", "86899", "Landsberg am Lech",
              ust_id_de("13072295"), iban_de("0868990050"), "SEEBDEX1LAL", "Beispiel-Sparkasse Landsberg",
              "buchhaltung@seeberger-rad.example", "www.seeberger-rad.example", "08191 00000-0",
              "Amtsgericht Augsburg HRB 00000", "Korbinian Seeberger")
KATALOG = [
    Artikel("SR-11020", "Kettenblatt 34 Z., 4-Loch, Aluminium schwarz eloxiert", (14, 39)),
    Artikel("SR-11410", "Kassette 11-fach 11-34 Z.", (32, 68)),
    Artikel("SR-12001", "Kette 11-fach, 116 Glieder, mit Kettenschloss", (17, 42), mengen=(2, 5, 10, 20)),
    Artikel("SR-13550", "Scheibenbremsbeläge organisch, Satz", (6.5, 15), mengen=(5, 10, 20, 25)),
    Artikel("SR-14090", "Bremsscheibe 180 mm, 6-Loch", (16, 36), mengen=(2, 4, 6, 10)),
    Artikel("SR-15300", "Faltreifen 29 x 2,35, Tubeless Ready", (28, 54), mengen=(2, 4, 6, 8, 12)),
    Artikel("SR-15812", "Schlauch 28\", Sclaverandventil 60 mm", (3.9, 8.5), mengen=(10, 20, 50)),
    Artikel("SR-16020", "Lenkerband, Kork, schwarz", (7, 19), mengen=(3, 5, 10)),
    Artikel("SR-17101", "Sattelstütze 31,6 x 400 mm, Carbon", (59, 129), mengen=(1, 2, 3)),
    Artikel("SR-18044", "Schaltzug-Set Edelstahl, beschichtet", (6, 14), mengen=(5, 10, 20)),
    Artikel("SR-19003", "Pedal-Paar Plattform, Aluminium", (21, 58), mengen=(2, 4, 6)),
    Artikel("SR-19870", "Werkstattstunde Laufradzentrierung", (48, 62), unit="Std.", mengen=(1, 2, 3)),
    Artikel("SR-20500", "Lichtset Akku StVZO, Front- und Rücklicht", (24, 69), mengen=(2, 5, 10)),
    Artikel("SR-21002", "Flaschenhalter Aluminium", (4.5, 12), mengen=(5, 10, 25)),
]
LANG = ["Restposten aus Saisonware 2026, Rückgabe ausgeschlossen",
        "Lieferung erfolgt in Einzelverpackung mit EAN-Etikett für den Ladenverkauf",
        "kompatibel mit gängigen Schaltgruppen, Montageanleitung liegt bei",
        "Farbe nach Verfügbarkeit, bei Nachbestellung bitte Artikelnummer und Farbcode angeben"]
X_POS, X_MENGE, X_ART, X_BEZ, X_EP, X_UST, X_GP = 40, 58, 106, 158, 330, 362, 444
X_LEISTE = 458
BEZ_BREITE = 124
TAKT = 9.0
Y_KOPF1, Y_KOPF2 = 318.0, 151.0
UNTEN = 790.0
GLAEUBIGER = "DE98ZZZ09999999999"           # Beispiel-Gläubiger-ID aus der Bundesbank-Dokumentation
BEARBEITER = ["Theresa Gail", "Lorenz Huber", "Sina Wörle"]
KURZ = "Artikelbeschreibung kurz"
EINHEIT = {"Stk.": "Stück", "Std.": "Std."}


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    # Vorlage: „Zahlungsziel: 30 Tage“; Skonto steht als Anmerkung darunter (nicht in der Vorlage, im Stil der
    # Anmerkungszeile formuliert).
    z = [f"Zahlungsziel: {s.ziel} Tage"]
    if s.zahlung == "skonto":
        z.append(f"Bei Zahlung innerhalb von {s.skonto_tage} Tagen gewähren wir {s.skonto} % Skonto.")
    return z


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def _hoehe(p):
    return len(p.beschreibung) + 1.3              # + Druckbeschreibung (klein) + Abstand


def _kap(y0):
    return int((UNTEN - (y0 + 16)) // TAKT)


def plan(ps, s):
    return seitenplan(ps, _hoehe, erste=_kap(Y_KOPF1), folge=_kap(Y_KOPF2), summen=14)


def seitenleiste(c):
    """Form XObject: Absender, Kontakt, Bank in der rechten Spalte (auf jeder Seite gleich)."""
    c.beginForm("Seitenleiste")
    b = Blatt(c, A4[1])
    x = X_LEISTE
    b.text(x, 140, AB.name, B, 6.5)
    for j, z in enumerate([AB.strasse, f"{AB.plz} {AB.ort}", "Deutschland"]):
        b.text(x, 150 + 8 * j, z, R, 6.5)
    b.text(x, 184, "USt-IdNr.:", R, 6.5)
    b.text(x, 192, AB.ust_id, R, 6.5)
    b.text(x, 204, "Gläubiger-IdNr.:", R, 6.5)
    b.text(x, 212, GLAEUBIGER, R, 6.5)
    b.text(x, 228, f"Tel:    {AB.telefon}", R, 6.5)
    b.text(x, 236, f"Fax:    {AB.telefon[:-1]}9", R, 6.5)
    b.text(x, 252, AB.email, R, 6.5)
    b.text(x, 260, AB.web, R, 6.5)
    b.text(x, 292, "Bearbeiter:", R, 6.5)
    b.text(x, 322, AB.name, B, 6.5)
    b.text(x, 330, "IBAN:", B, 6.5)
    b.text(x, 338, AB.iban, R, 6.5)
    b.text(x, 346, "BIC:", B, 6.5)
    b.text(x, 354, AB.bic, R, 6.5)
    b.text(x, 362, AB.bank, B, 6.5)
    c.endForm()


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t, fl = d["buyer"], d["invoice"], d["totals_printed"], d["test_flags"]
    seitenleiste(c)
    n = len(seiten)
    from reportlab.lib.utils import ImageReader
    for se in seiten:
        c.drawImage(ImageReader(logo_png("SR")), 40, A4[1] - 112, 270, 90)
        c.doForm("Seitenleiste")
        c.setStrokeColor(SCHWARZ)
        c.setLineWidth(0.6)
        c.line(X_LEISTE - 6, A4[1] - 132, X_LEISTE - 6, A4[1] - 790)
        b.text(X_LEISTE, 300, fl["bearbeiter"], R, 6.5)
        infos = [("Rechnungsnummer:", inv["number"]), ("Rechnungsdatum:", inv["date"]),
                 ("Auftragsnummer:", fl["auftragsnummer"]), ("Kundennummer:", k["customer_number"]),
                 ("Zahlungsart:", "Rechnung"), ("Versandart:", fl["versandart"]),
                 ("Lieferdatum (vorauss.):", inv["service_date"])]
        for j, (lab, w) in enumerate(infos):
            b.text(X_LEISTE, 490 + 18 * j, lab, B, 6.5)
            b.text(X_LEISTE, 498 + 18 * j, w, R, 6.5)
        y_kopf = Y_KOPF1 if se.nr == 1 else Y_KOPF2
        zeilen = []                          # (y, [(x, text, schrift, größe, art)]) – später rückwärts gezeichnet
        y = y_kopf + 12
        if se.vortrag is not None:
            zeilen.append((y, [(X_BEZ, f"Übertrag von Seite {se.nr - 1}", R, G, "l"),
                               (X_GP, f"{se.vortrag:.2f}".replace(".", ","), R, G, "r")]))
            b.linie(X_BEZ, y + 3, X_GP, 0.4)
            y += TAKT + 2
        for i in se.pos:
            p = ps[i]
            zellen = [(X_POS, str(i + 1), R, G, "l"), (X_MENGE, f"{menge(p.qty)} {EINHEIT[p.unit]}", R, G, "l"),
                      (X_ART, p.artnr, R, G, "l"), (X_EP, zahl(p.preis) + " €", R, G, "r"),
                      (X_UST, "19 %", R, G, "r"), (X_GP, zahl(p.gesamt) + " €", R, G, "r")]
            zeilen.append((y, zellen + [(X_BEZ, p.beschreibung[0], R, G, "l")]))
            for j, zl in enumerate(p.beschreibung[1:], start=1):
                zeilen.append((y + TAKT * j, [(X_BEZ, zl, R, G, "l")]))
            zeilen.append((y + TAKT * len(p.beschreibung) - 1, [(X_BEZ, KURZ, R, 5.5, "l")]))
            y += TAKT * _hoehe(p)
        if se.uebertrag is not None:
            b.linie(X_BEZ, y - 6, X_GP, 0.4)
            zeilen.append((y + 2, [(X_BEZ, "Zwischensumme", R, G, "l"), (X_GP, zahl(se.uebertrag) + " €", R, G, "r")]))
        if se.summen:
            yk = y + 6
            b.linie(260, yk - 6, X_GP, 0.4)
            for j, (lab, w, f) in enumerate([("Gesamt Netto", t["net"], R), ("zzgl. MwSt (19 %)", t["vat"], R),
                                             ("Rechnungsbetrag", t["gross"], B)]):
                b.text(X_EP - 6, yk + 4 + 11 * j, lab, f, 8, art="r")
                b.text(X_GP, yk + 4 + 11 * j, zahl(Decimal(w)) + " €", f, 8, art="r")
            ya = yk + 56
            zz = d["payment_terms_text"]
            for j, (lab, w) in enumerate([("Versandart:", fl["versandart"]), ("Zahlungsart:", "Rechnung"),
                                          ("Zahlungsziel:", zz[0].split(": ", 1)[1])]):
                b.text(40, ya + 10 * j, lab, R, G)
                b.text(126, ya + 10 * j, w, R, G)
            ya += 40
            for j, zl in enumerate(zz[1:] + ["Die Ware bleibt bis zur vollständigen Bezahlung unser Eigentum."]):
                b.text(40, ya + 10 * j, zl, R, G)
        for yy, zellen in reversed(zeilen):  # Lesereihenfolge ≠ Stream-Reihenfolge
            for x, txt, f, gr, a in reversed(zellen):
                b.text(x, yy, txt, f, gr, art=a)
        for x, txt, a in [(X_POS, "Pos", "l"), (X_MENGE, "Menge", "l"), (X_ART, "Art. Nr.", "l"),
                          (X_BEZ, "Bezeichnung", "l"), (X_EP, "Netto EP", "r"), (X_UST, "MwSt", "r"),
                          (X_GP, "Netto GP", "r")]:
            b.text(x, y_kopf, txt, B, G, art=a)
        b.linie(40, y_kopf + 3, X_GP, 0.8)
        if se.nr == 1:
            b.text(X_GP, 268, f"{AB.ort}, den {inv['date']}", R, G, art="r")
            b.text(X_GP, 278, f"Seite: 1 / {n}", R, G, art="r")
            b.text(40, 280, "RECHNUNG", R, 16)
            for j, z in reversed(list(enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}",
                                                                   "Deutschland"]))):
                b.text(40, 160 + 10 * j, z, R, 8.5)
            sl = f"{AB.name} | {AB.strasse} | {AB.plz} {AB.ort}"
            b.text(40, 140, sl, B, 6.5)
            b.linie(40, 142, X_GP, 0.4)
        else:
            b.text(X_GP, 138, f"Seite: {se.nr} / {n}", R, G, art="r")
        c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"RE{datum:%Y}{3100 + n * 41 + rng.randint(0, 30):05d}"


def bestellnr(rng):
    return f"{rng.choice(['EK', 'B', 'PO'])}-{rng.randint(1000, 9999)}"


def muss(d, ps, seiten, s):
    t = d["totals_printed"]
    m = [(len(seiten), f"Rechnungsbetrag {zahl(Decimal(t['gross']))} €"),
         (len(seiten), f"Zahlungsziel: {s.ziel} Tage")]
    for se in seiten:
        if se.uebertrag is not None:
            m.append((se.nr, f"Zwischensumme {zahl(se.uebertrag)} €"))
        if se.vortrag is not None:
            m.append((se.nr, f"Übertrag von Seite {se.nr - 1} {se.vortrag:.2f}".replace(".", ",")))
    return m


SPEZ = [
    Spez(9, anzahl=6, lang=2, zahlung="netto", ziel=30, bestellung=False, notiz="1 Seite, Zahlungsziel 30 Tage"),
    Spez(10, anzahl=26, lang=10, zahlung="skonto", skonto=2, skonto_tage=10, ziel=30, seiten=2, bestellung=False,
         notiz="2 Seiten mit Zwischensumme / Übertrag von Seite 1, Skonto als Anmerkung"),
    Spez(11, anzahl=8, lang=3, zahlung="netto", ziel=14, bestellung=False,
         notiz="3 Namenszeilen, Zahlungsziel 14 Tage"),
    Spez(12, anzahl=24, lang=12, zahlung="netto", ziel=30, seiten=2, holdout=True, bestellung=False,
         notiz="Hold-out: 2 Seiten, Übertrag"),
    Spez(13, anzahl=46, lang=26, zahlung="skonto", skonto=3, skonto_tage=8, ziel=30, seiten=3, holdout=True,
         bestellung=False, notiz="Hold-out: 3 Seiten, zwei Überträge, 3 % Skonto als Anmerkung"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(9, anzahl=7, lang=2, zahlung="netto", ziel=30, holdout=True, bestellung=False, fehler="ust_id_pruefziffer",
         notiz="Hold-out FEHLER: USt-IdNr. in der Seitenleiste mit falscher Prüfziffer"),
]


def _beleg_extra(fam):
    import random
    r = random.Random(fam.seed * 7)
    for sp in fam.spez:
        sp.extra = {"bearbeiter": r.choice(BEARBEITER), "auftragsnummer": f"{r.randint(20210000, 20219999)}",
                    "versandart": r.choice(["Postpaket", "DHL Paket", "Spedition"])}


FAMILIE = Familie(
    nr=3, ordner="f03_seitenleiste", titel="Seitenleiste mit Label über Wert, mehrseitig (nach JTL business 2.0)",
    absender=AB, quelle="Q4", seed=26_4723, schrift="Helvetica", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
_beleg_extra(FAMILIE)
