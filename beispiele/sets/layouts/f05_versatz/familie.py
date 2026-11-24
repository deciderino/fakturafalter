"""F5 „Versatz“ – nach der JTL-Wawi-Vorlage „creativ 1.4“ (QUELLEN.md, Q5).

Wortlaut und Anordnung wie in der Vorlage: Logo links oben, Firmenblock rechts oben, Absenderzeile und Anschrift
links, rechts daneben Rechnung-Nr: / Auftrag-Nr: / Datum: / Kunden-Nr: als „Label: Wert“, die Werte 1,8 pt
tiefer als die Labels gesetzt (Versatz der Grundlinie wie im Vorlagen-PDF). Überschrift „Rechnung“ und
„Seite: 1 von N“. Tabelle Pos. | Menge („2 Stück“) | Art.-Nr. | Bezeichnung | MwSt. („19,00 %“) | E-Preis |
G-Preis, Beträge ohne Tausenderpunkt mit „EUR“. Seitenumbruch mit „Zwischensumme“ unten und „Übertrag von
Seite N“ oben. Summen Gesamt Netto / zzgl. 19,00 MwSt. / Gesamtbetrag. Danach „Zahlungsart: Rechnung“ und
„Zahlungsziel: N Tage“. Fuß in vier Spalten, rechts „Seite: N / M“. Helvetica 8 pt.

Weggelassen (OUT): Rabattspalte, Vorauszahlungs-/Gutscheinzeilen. „USt-Nr:“ des Kunden fehlt, weil das Set
für Käufer keine USt-IdNr. führt."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, GRAU, Absender, Artikel, Blatt, Familie, Spez, iban_de, leinwand, logo_png,  # noqa: E402
                     menge, positionen, seitenplan, ust_id_de, zahl)

R, B = "Helvetica", "Helvetica-Bold"
G = 8.0
AB = Absender("Kerber Bürobedarf GmbH", "Stadtgraben 17", "94315", "Straubing",
              ust_id_de("13905521"), iban_de("0752009915"), "KERBDEX1STR", "Beispielbank Niederbayern",
              "service@kerber-buero.example", "www.kerber-buero.example", "09421 000000",
              "Amtsgericht Straubing HRB 0000", "Thomas Kerber")
EINHEIT = {"Stk.": "Stück", "Std.": "Std."}
KATALOG = [
    Artikel("100234", "Kopierpapier A4 80 g, 500 Blatt", (3.9, 5.4), mengen=(5, 10, 20, 50)),
    Artikel("100251", "Recyclingpapier A4 80 g, 500 Blatt", (4.2, 5.9), mengen=(5, 10, 25)),
    Artikel("110410", "Ordner A4 breit 8 cm, blau", (2.1, 3.6), mengen=(10, 20, 30)),
    Artikel("110411", "Ordner A4 schmal 5 cm, rot", (2.0, 3.4), mengen=(10, 20)),
    Artikel("110520", "Trennblätter A4, 100 Stück", (3.5, 5.2), mengen=(2, 5, 10)),
    Artikel("120013", "Kugelschreiber blau, Druckmechanik", (0.45, 0.9), mengen=(20, 50, 100)),
    Artikel("120020", "Textmarker 4er-Set", (2.9, 4.6), mengen=(5, 10)),
    Artikel("120031", "Bleistift HB mit Radierer", (0.25, 0.55), mengen=(24, 48, 96)),
    Artikel("130100", "Haftnotizen 76 × 76 mm, gelb", (0.9, 1.6), mengen=(12, 24, 36)),
    Artikel("130122", "Briefumschläge DIN lang, 1000 Stück", (16, 24), mengen=(1, 2, 3)),
    Artikel("130140", "Versandtaschen C4, 250 Stück", (21, 33), mengen=(1, 2)),
    Artikel("140001", "Tonerkartusche schwarz, kompatibel", (29, 59), mengen=(1, 2, 4)),
    Artikel("140002", "Tintenpatronen Multipack 4-farbig", (24, 39), mengen=(1, 2, 3)),
    Artikel("150300", "Schreibtischunterlage 60 × 40 cm", (7, 12), mengen=(1, 2, 5)),
    Artikel("150310", "Locher bis 25 Blatt", (5.5, 9.9), mengen=(1, 2, 3)),
    Artikel("150320", "Heftgerät bis 30 Blatt", (6.9, 12.5), mengen=(1, 2, 3)),
    Artikel("150330", "Heftklammern 24/6, 1000 Stück", (0.8, 1.5), mengen=(5, 10)),
    Artikel("160050", "Laminierfolien A4 125 mic, 100 Stück", (11, 19), mengen=(1, 2)),
    Artikel("160060", "Etiketten 70 × 37 mm, 2400 Stück", (13, 22), mengen=(1, 2, 3)),
    Artikel("170200", "Archivkarton für 5 Ordner", (2.8, 4.9), mengen=(5, 10, 20)),
    Artikel("170210", "Hängeregistratur A4, 25 Stück", (8, 14), mengen=(1, 2, 4)),
    Artikel("180001", "Whiteboard-Marker 4er-Set", (4.5, 7.9), mengen=(2, 5)),
    Artikel("180010", "Moderationskarten 250 Stück", (6, 10), mengen=(1, 2, 3)),
    Artikel("190900", "Einrichtung Druckerfreigabe vor Ort", (65, 85), unit="Std.", mengen=(1, 1.5, 2)),
]
LANG = ["Restposten, solange Vorrat reicht", "Lieferung in Teilmengen nach Abruf",
        "FSC-zertifiziert, chlorfrei gebleicht"]
VERSAND = ("900001", "Versandkosten Paket", "6.90")
X_POS, X_MENGE, X_ART, X_BEZ, X_UST, X_EP, X_GP = 50, 70, 116, 160, 418, 476, 545
BEZ_BREITE = 220
TAKT = 10.0
Y_KOPF1, Y_KOPF2 = 330.0, 150.0
VERSATZ = 1.8


def z2(x) -> str:
    return zahl(Decimal(x), tausender=False)


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    z = [f"Zahlungsziel: {s.ziel} Tage"]
    if s.zahlung == "skonto":
        z.append(f"Bei Zahlung innerhalb von {s.skonto_tage} Tagen gewähren wir {s.skonto},00 % Skonto.")
    return z


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G,
                      VERSAND if s.versand else None, max_zeilen=2)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung), erste=33, folge=51, summen=9)


def fuss(b, se, n):
    spalten = [[AB.name, AB.strasse, f"{AB.plz} {AB.ort}"],
               [f"Tel.: {AB.telefon}", f"E-Mail: {AB.email}", f"Web: {AB.web}"],
               [AB.bank, f"IBAN: {AB.iban}", f"BIC: {AB.bic}"],
               [f"Geschäftsführer: {AB.gf}", AB.register, f"USt-IdNr.: {AB.ust_id}"]]
    b.linie(50, 778, 545, 0.4, GRAU)
    for x, zz in zip((50, 170, 300, 425), spalten):
        for j, zl in enumerate(zz):
            b.text(x, 788 + 8 * j, zl, R, 6, GRAU)
    b.text(545, 822, f"Seite: {se.nr} / {n}", R, 6, GRAU, art="r")


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t, fl = d["buyer"], d["invoice"], d["totals_printed"], d["test_flags"]
    n = len(seiten)
    for se in seiten:
        c.drawImage(ImageReader(logo_png("KB", farbe=(30, 70, 140))), 50, A4[1] - 92, 180, 60)
        for j, zl in enumerate([AB.name, AB.strasse, f"{AB.plz} {AB.ort}", f"Tel.: {AB.telefon}",
                                f"E-Mail: {AB.email}"]):
            b.text(545, 44 + 9 * j, zl, B if j == 0 else R, 7, art="r")
        if se.nr == 1:
            b.text(50, 140, f"{AB.name} - {AB.strasse} - {AB.plz} {AB.ort}", R, 6)
            b.linie(50, 142, 230, 0.3)
            for j, zl in enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}"]):
                b.text(50, 158 + 11 * j, zl, R, 9)
            for j, (lab, w) in enumerate([("Rechnung-Nr:", inv["number"]), ("Auftrag-Nr:", fl["auftragsnummer"]),
                                          ("Datum:", inv["date"]), ("Kunden-Nr:", k["customer_number"]),
                                          ("Lieferdatum:", inv["service_date"])]):
                b.text(380, 160 + 12 * j, lab, R, G)
                b.text(450, 160 + 12 * j + VERSATZ, w, R, G)
            b.text(50, 300, "Rechnung", B, 14)
            b.text(545, 300, f"Seite: 1 von {n}", R, G, art="r")
        y_kopf = Y_KOPF1 if se.nr == 1 else Y_KOPF2
        for x, txt, a in [(X_POS, "Pos.", "l"), (X_MENGE, "Menge", "l"), (X_ART, "Art.-Nr.", "l"),
                          (X_BEZ, "Bezeichnung", "l"), (X_UST, "MwSt.", "r"), (X_EP, "E-Preis", "r"),
                          (X_GP, "G-Preis", "r")]:
            b.text(x, y_kopf, txt, B, G, art=a)
        b.linie(50, y_kopf + 3, 545, 0.6)
        y = y_kopf + 14
        if se.vortrag is not None:
            b.text(X_BEZ, y, f"Übertrag von Seite {se.nr - 1}", B, G)
            b.text(X_GP, y, z2(se.vortrag) + " EUR", B, G, art="r")
            y += TAKT + 3
        for i in se.pos:
            p = ps[i]
            b.text(X_POS, y, f"{i + 1}.", R, G)
            b.text(X_MENGE, y, f"{menge(p.qty)} {EINHEIT[p.unit]}", R, G)
            b.text(X_ART, y, p.artnr, R, G)
            b.text(X_UST, y, "19,00 %", R, G, art="r")
            b.text(X_EP, y, z2(p.preis) + " EUR", R, G, art="r")
            b.text(X_GP, y, z2(p.gesamt) + " EUR", R, G, art="r")
            for j, zl in enumerate(p.beschreibung):
                b.text(X_BEZ, y + TAKT * j, zl, R, G)
            y += TAKT * len(p.beschreibung)
        if se.uebertrag is not None:
            b.linie(X_BEZ, y - 6, 545, 0.4)
            b.text(X_BEZ, y + 3, "Zwischensumme", B, G)
            b.text(X_GP, y + 3, z2(se.uebertrag) + " EUR", B, G, art="r")
        if se.summen:
            b.linie(330, y - 4, 545, 0.6)
            for j, (lab, w, f) in enumerate([("Gesamt Netto", t["net"], R), ("zzgl. 19,00 MwSt.", t["vat"], R),
                                             ("Gesamtbetrag", t["gross"], B)]):
                b.text(340, y + 8 + 12 * j, lab, f, G)
                b.text(X_GP, y + 8 + 12 * j, z2(w) + " EUR", f, G, art="r")
            y += 8 + 36 + 14
            b.text(50, y, "Zahlungsart: Rechnung", R, G)
            for j, zl in enumerate(d["payment_terms_text"]):
                b.text(50, y + 11 * (j + 1), zl, R, G)
            y += 11 * (len(d["payment_terms_text"]) + 1) + 6
            b.text(50, y, "Vielen Dank für Ihren Einkauf.", R, G)
        fuss(b, se, n)
        c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"RE{datum:%y}-{rng.randint(10, 99)}{n:03d}"


def bestellnr(rng):
    return ""


def muss(d, ps, seiten, s):
    t = d["totals_printed"]
    m = [(len(seiten), f"Gesamtbetrag {z2(t['gross'])} EUR"), (len(seiten), f"Zahlungsziel: {s.ziel} Tage"),
         (1, f"Rechnung-Nr: {d['invoice']['number']}")]
    for se in seiten:
        if se.uebertrag is not None:
            m.append((se.nr, f"Zwischensumme {z2(se.uebertrag)} EUR"))
        if se.vortrag is not None:
            m.append((se.nr, f"Übertrag von Seite {se.nr - 1} {z2(se.vortrag)} EUR"))
    return m


SPEZ = [
    Spez(21, anzahl=5, lang=1, zahlung="netto", ziel=10, versand=True, bestellung=False,
         notiz="einfach, Versandkosten als Position"),
    Spez(22, anzahl=30, lang=3, zahlung="skonto", skonto=2, skonto_tage=7, ziel=30, bestellung=False, seiten=2,
         notiz="2 Seiten mit Zwischensumme/Übertrag, Skonto"),
    Spez(23, anzahl=7, lang=2, zahlung="netto", ziel=14, versand=True, bestellung=False,
         notiz="Versatz-Infoblock, Dienstleistung in Std. gemischt"),
    Spez(20, anzahl=9, lang=2, zahlung="netto", ziel=10, holdout=True, bestellung=False,
         notiz="Hold-out: 3 Namenszeilen"),
    Spez(28, anzahl=86, lang=4, zahlung="skonto", skonto=3, skonto_tage=10, ziel=30, versand=True, holdout=True,
         bestellung=False, seiten=3, notiz="Hold-out: 3 Seiten, zwei Überträge"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(23, anzahl=6, lang=1, zahlung="netto", ziel=14, versand=True, holdout=True, bestellung=False,
         fehler="rechnungsdatum_fehlt", notiz="Hold-out FEHLER: Rechnungsdatum nicht gedruckt (Lieferdatum steht da)"),
]


def _beleg_extra(fam):
    import random
    r = random.Random(fam.seed * 7)
    for sp in fam.spez:
        sp.extra = {"auftragsnummer": f"AU{r.randint(100000, 199999)}"}


FAMILIE = Familie(
    nr=5, ordner="f05_versatz", titel="Infoblock mit Grundlinien-Versatz, mehrseitig (nach JTL creativ 1.4)",
    absender=AB, quelle="Q5", seed=26_4725, schrift="Helvetica", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
_beleg_extra(FAMILIE)
