"""F6 „Schreibmaschine“ – nach dem DATEV-Musterbeleg „Rechnung“ (Auftragswesen; QUELLEN.md, Q6).

Wortlaut und Anordnung wie im Musterbeleg, durchgehend Courier: Firmenname groß links oben, Anschrift und
Kontakt rechts, Absenderzeile und Anschrift links, rechts „RECHNUNG“ mit Nummer / Datum / Kunden-Nr. /
Lieferdatum / Auftragsnummer (Label und Wert in zwei Spalten, ohne Doppelpunkt), darunter „Lieferung frei Haus“
und „Seite N“. Tabelle Pos | Artikel | Bezeichnung | Menge | Einheit („Stück“/„Stunden“) | USt% („19“) | Preis |
Betrag EUR. In längeren Belegen eine Gruppen-„Zwischensumme“ mitten in der Tabelle (wie im Muster), beim
Seitenumbruch „Übertrag“ unten und oben. Summen Zwischensumme / „19% MWSt auf EUR <Netto>“ / Endbetrag.
„Zahlung: 30 Tage 2,0%; 60 Tage netto“. Fuß mit Bank, BLZ, Konto, IBAN, BIC und Registerzeile."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, Absender, Artikel, Blatt, Familie, Spez, iban_de, leinwand, menge,  # noqa: E402
                     positionen, seitenplan, ust_id_de, zahl)

R, B = "Courier", "Courier-Bold"
G = 8.0
AB = Absender("Holzwerkstatt Brenneisen GmbH", "Am Sägewerk 4", "79822", "Titisee-Neustadt",
              ust_id_de("14290613"), iban_de("0004418230"), "BRENDEX1TNS", "Beispielsparkasse Hochschwarzwald",
              "buero@brenneisen-holz.example", "www.brenneisen-holz.example", "07651 000000",
              "Amtsgericht Freiburg i. Br. HRB 000000", "Markus Brenneisen")
KONTO = "4418230"
EINHEIT = {"Stk.": "Stück", "Std.": "Stunden"}
KATALOG = [
    Artikel("TS-1001", "Arbeitsplatte Eiche massiv 40 mm, je lfm", (180, 260), mengen=(1, 2, 3)),
    Artikel("TS-1002", "Thekenfront Multiplex, lackiert", (420, 690), mengen=(1, 2)),
    Artikel("TS-1010", "Regalboden Buche 25 mm, 80 cm", (38, 56), mengen=(4, 6, 10, 12)),
    Artikel("TS-1011", "Wandregal Lärche geölt, 120 cm", (95, 140), mengen=(1, 2, 4)),
    Artikel("TS-1020", "Schubkastenführung Vollauszug", (24, 39), mengen=(4, 8, 12)),
    Artikel("TS-1021", "Topfband 110°, Clip", (3.8, 6.4), mengen=(10, 20, 40)),
    Artikel("TS-1030", "Möbelgriff Edelstahl 128 mm", (4.5, 9.0), mengen=(6, 12, 24)),
    Artikel("TS-1040", "Sockelleiste Eiche, je lfm", (8, 14), mengen=(10, 20, 30)),
    Artikel("TS-1050", "Hartwachsöl 0,75 l", (22, 31), mengen=(1, 2, 3)),
    Artikel("TS-2001", "Montage vor Ort", (52, 64), unit="Std.", mengen=(4, 6, 8, 12)),
    Artikel("TS-2002", "Aufmaß und Planung", (58, 70), unit="Std.", mengen=(2, 3, 4)),
    Artikel("TS-2003", "Werkstattarbeit Zuschnitt und Kanten", (48, 58), unit="Std.", mengen=(3, 5, 8)),
    Artikel("TS-2010", "Anfahrt Montagefahrzeug", (35, 55), mengen=(1, 2)),
    Artikel("TS-2020", "Entsorgung Altmöbel, Pauschale", (60, 120), mengen=(1,)),
]
LANG = ["nach Aufmaß vom Kundentermin, Kanten gefast",
        "Oberfläche zweimal geölt und zwischengeschliffen",
        "inklusive Befestigungsmaterial und Abdeckkappen"]
X_POS, X_ART, X_BEZ, X_MENGE, X_EH, X_UST, X_EP, X_GP = 50, 74, 120, 352, 358, 418, 478, 545
BEZ_BREITE = 190
TAKT = 10.0
Y_KOPF1, Y_KOPF2 = 318.0, 150.0


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    if s.zahlung == "skonto":
        return [f"Zahlung: {s.skonto_tage} Tage {s.skonto},0%; {s.ziel} Tage netto"]
    return [f"Zahlung: {s.ziel} Tage netto"]


def pos_erzeugen(rng, s):
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, BEZ_BREITE, R, G, max_zeilen=3)


def _gruppe(ps, s):
    """Index der Position, nach der die Gruppen-Zwischensumme steht (oder None)."""
    return len(ps) // 2 - 1 if s.extra.get("gruppen_zwischensumme") else None


def plan(ps, s):
    k = _gruppe(ps, s)
    return seitenplan(ps, lambda p: len(p.beschreibung) + 0.3 + (2 if k is not None and p is ps[k] else 0),
                      erste=34, folge=52, summen=10)


def zeichnen(pfad, d, ps, seiten, s):
    c = leinwand(pfad, A4, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, A4[1])
    k, inv, t, fl = d["buyer"], d["invoice"], d["totals_printed"], d["test_flags"]
    gk = _gruppe(ps, s)
    for se in seiten:
        b.text(50, 60, AB.name, B, 14)
        b.text(50, 74, "Schreinerei und Ladenbau", R, 9)
        for j, zl in enumerate([AB.strasse, f"{AB.plz} {AB.ort}", f"Telefon {AB.telefon}", AB.email, AB.web]):
            b.text(545, 52 + 9 * j, zl, R, 7, art="r")
        if se.nr == 1:
            b.text(50, 140, f"{AB.name}, {AB.strasse}, {AB.plz} {AB.ort}", R, 6)
            for j, zl in enumerate(k["name_lines"] + [k["street"], "", f"{k['postal_code']} {k['city']}"]):
                b.text(50, 158 + 11 * j, zl, R, 9.5)
            b.text(350, 150, "RECHNUNG", B, 12)
            info = [("Nummer", inv["number"]), ("Datum", inv["date"]),
                    ("Kunden-Nr.", k["customer_number"]), ("Lieferdatum", inv["service_date"]),
                    ("Auftragsnummer", fl["auftragsnummer"])]
            if d.get("falle") == "zweites_datum":
                info.insert(1, ("Auftragsdatum", d["falle_detail"]["auftragsdatum"]))
            for j, (lab, w) in enumerate(info):
                b.text(350, 168 + 11 * j, lab, R, G)
                b.text(440, 168 + 11 * j, w, R, G)
            b.text(350, 232, "Lieferung frei Haus", R, G)
            b.text(350, 244, "Seite 1", R, G)
        else:
            b.text(350, 120, f"Rechnung {inv['number']} vom {inv['date']}", R, G)
            b.text(350, 131, f"Seite {se.nr}", R, G)
        y_kopf = Y_KOPF1 if se.nr == 1 else Y_KOPF2
        b.linie(50, y_kopf - 9, 545, 0.5)
        for x, txt, a in [(X_POS, "Pos", "l"), (X_ART, "Artikel", "l"), (X_BEZ, "Bezeichnung", "l"),
                          (X_MENGE, "Menge", "r"), (X_EH, "Einheit", "l"), (X_UST, "USt%", "r"),
                          (X_EP, "Preis", "r"), (X_GP, "Betrag EUR", "r")]:
            b.text(x, y_kopf, txt, B, G, art=a)
        b.linie(50, y_kopf + 3, 545, 0.5)
        y = y_kopf + 14
        if se.vortrag is not None:
            b.text(X_BEZ, y, "Übertrag", R, G)
            b.text(X_GP, y, zahl(se.vortrag), R, G, art="r")
            y += TAKT + 3
        for i in se.pos:
            p = ps[i]
            b.text(X_POS, y, f"{i + 1:>3}", R, G)
            b.text(X_ART, y, p.artnr, R, G)
            b.text(X_MENGE, y, menge(p.qty, 2), R, G, art="r")
            b.text(X_EH, y, EINHEIT[p.unit], R, G)
            b.text(X_UST, y, "19", R, G, art="r")
            b.text(X_EP, y, zahl(p.preis), R, G, art="r")
            b.text(X_GP, y, zahl(p.gesamt), R, G, art="r")
            for j, zl in enumerate(p.beschreibung):
                b.text(X_BEZ, y + TAKT * j, zl, R, G)
            y += TAKT * (len(p.beschreibung) + 0.3)
            if i == gk:
                b.linie(X_EP + 10, y - 6, 545, 0.4)
                b.text(X_BEZ, y + 3, "Zwischensumme", R, G)
                b.text(X_GP, y + 3, zahl(sum(q.gesamt for q in ps[:i + 1])), R, G, art="r")
                y += TAKT * 2
        if se.uebertrag is not None:
            b.linie(50, y - 6, 545, 0.4)
            b.text(X_BEZ, y + 3, "Übertrag", R, G)
            b.text(X_GP, y + 3, zahl(se.uebertrag), R, G, art="r")
        if se.summen:
            b.linie(50, y - 6, 545, 0.5)
            for j, (lab, w, f) in enumerate([("Zwischensumme", t["net"], R),
                                             (f"19% MWSt auf EUR {zahl(Decimal(t['net']))}", t["vat"], R),
                                             ("Endbetrag", t["gross"], B)]):
                b.text(X_BEZ, y + 6 + 12 * j, lab, f, G)
                b.text(X_GP, y + 6 + 12 * j, zahl(Decimal(w)), f, G, art="r")
            b.linie(X_EP + 10, y + 6 + 26, 545, 0.5)
            y += 6 + 36 + 16
            for j, zl in enumerate(d["payment_terms_text"]):
                b.text(50, y + 11 * j, zl, R, G)
        for j, zl in enumerate([f"Bank: {AB.bank} · BLZ 000 000 00 · Konto {KONTO}",
                                f"IBAN {AB.iban} · BIC {AB.bic}",
                                f"Sitz {AB.ort} · {AB.register} · Geschäftsführer {AB.gf} · USt-IdNr. {AB.ust_id}"]):
            b.text(297.6, 790 + 8.5 * j, zl, R, 6, art="m")
        c.showPage()
    c.save()


def nummer(n, rng, datum):
    return f"{rng.randint(4, 6)}{n:02d}{datum:%m}"


def bestellnr(rng):
    return ""


def muss(d, ps, seiten, s):
    t = d["totals_printed"]
    m = [(len(seiten), f"Endbetrag {zahl(Decimal(t['gross']))}"),
         (len(seiten), f"19% MWSt auf EUR {zahl(Decimal(t['net']))} {zahl(Decimal(t['vat']))}"),
         (1, f"Nummer {d['invoice']['number']}"), (1, "Lieferung frei Haus")]
    for se in seiten:
        if se.uebertrag is not None:
            m.append((se.nr, f"Übertrag {zahl(se.uebertrag)}"))
        if se.vortrag is not None:
            m.append((se.nr, f"Übertrag {zahl(se.vortrag)}"))
    return m


SPEZ = [
    Spez(24, anzahl=4, lang=1, zahlung="skonto", skonto=2, skonto_tage=30, ziel=60, bestellung=False,
         notiz="Zahlung wie im Muster: 30 Tage 2,0%; 60 Tage netto"),
    Spez(25, anzahl=10, lang=2, zahlung="netto", ziel=30, bestellung=False,
         notiz="Gruppen-Zwischensumme mitten in der Tabelle", extra={"gruppen_zwischensumme": True}),
    Spez(26, anzahl=30, lang=4, zahlung="skonto", skonto=3, skonto_tage=8, ziel=30, bestellung=False, seiten=2,
         notiz="3 Namenszeilen, 2 Seiten mit Übertrag"),
    Spez(27, anzahl=8, lang=3, zahlung="netto", ziel=14, holdout=True, bestellung=False,
         notiz="Hold-out: Gruppen-Zwischensumme, mehrzeilige Bezeichnungen", extra={"gruppen_zwischensumme": True}),
    Spez(22, anzahl=5, zahlung="skonto", skonto=2, skonto_tage=14, ziel=30, holdout=True, bestellung=False,
         notiz="Hold-out: einfach, Skonto"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(25, anzahl=6, lang=1, zahlung="netto", ziel=30, holdout=True, bestellung=False, fehler="netto_brutto",
         notiz="Hold-out FEHLER: Zahlendreher im Endbetrag (≠ Netto + USt)"),
    Spez(26, anzahl=5, lang=2, zahlung="skonto", skonto=2, skonto_tage=14, ziel=30, holdout=True, bestellung=False,
         falle="zweites_datum", notiz="Hold-out FALLE: Auftragsdatum direkt über dem Rechnungsdatum"),
]


def _beleg_extra(fam):
    import random
    r = random.Random(fam.seed * 7)
    for sp in fam.spez:
        sp.extra = {**sp.extra, "auftragsnummer": f"{r.randint(10000, 19999)}"}


FAMILIE = Familie(
    nr=6, ordner="f06_schreibmaschine", titel="Courier-Beleg mit Gruppen-Zwischensumme (nach DATEV-Musterbeleg)",
    absender=AB, quelle="Q6", seed=26_4726, schrift="Courier", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen)
_beleg_extra(FAMILIE)
