"""F2 „Briefkopf“ – nach der Lexware-Vorlage Honorarrechnung (QUELLEN.md, Q2).

Wortlaut und Anordnung wie in der Vorlage: Logo als Bild rechts oben (enthält keinen Pflichtwert), Absenderzeile
unterstrichen, Anschrift links, rechts Absenderblock mit „Tel.:“, „E-Mail:“, „Kundennummer:“ und
„Liefer-/Leistungsdatum:“ (Label: Wert). „Honorarrechnung Nr. …“ links, „Göttingen, den 3. November 2026“ rechts
– das Rechnungsdatum steht nur dort, ohne eigenes Label, und ist ausgeschrieben (Datumsvariante dieser Familie).
Anrede und Einleitungssatz, Tabelle Pos. | Menge („2 Std.“) | Bezeichnung | Einzelpreis | Gesamtpreis mit grau
hinterlegter Kopfzeile, gepunkteten Trennlinien und „EUR“, Summen Zwischensumme / 19% MwSt. / Gesamtbetrag,
Zahltext „Zahlung innerhalb von 14 Tagen ab Rechnungseingang ohne Abzüge an die unten angegebene
Bankverbindung.“, „Herzliche Grüße,“, zweizeiliger Fuß. Times-Roman 10 pt; ein Beleg in A5."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _rahmen import (A4, A5, GRAU, Absender, Artikel, Blatt, Familie, Spez, de, de_lang, iban_de,  # noqa: E402
                     leinwand, logo_png, menge, positionen, seitenplan, ust_id_de, zahl)

R, B = "Times-Roman", "Times-Bold"
AB = Absender("Ingenieurbüro Brandauer GmbH", "Am Klosterhof 9", "37073", "Göttingen", ust_id_de("31559027"),
              iban_de("0270730091"), "BRANDEX1GOE", "Beispiel-Volksbank Göttingen",
              "info@ib-brandauer.example", "www.ib-brandauer.example", "0551 000000-20",
              "Amtsgericht Göttingen HRB 00000", "Dipl.-Ing. Jakob Brandauer")
KATALOG = [
    Artikel("", "Planungsleistung Technische Gebäudeausrüstung", (88, 118), unit="Std.",
            mengen=(Decimal("2.5"), 4, 6, Decimal("7.5"), 8, 12)),
    Artikel("", "Bauüberwachung vor Ort", (78, 96), unit="Std.", mengen=(3, 4, Decimal("5.5"), 8)),
    Artikel("", "Erstellung Brandschutznachweis", (480, 1250), mengen=(1,)),
    Artikel("", "Thermografie-Messung Gebäudehülle", (290, 640), mengen=(1, 2)),
    Artikel("", "Statische Vorbemessung Deckendurchbruch", (350, 900), mengen=(1,)),
    Artikel("", "Fahrtkosten Pauschale", (35, 65), mengen=(1, 2, 3)),
    Artikel("", "Besprechung mit Bauherr und Fachplanern", (85, 110), unit="Std.", mengen=(1, Decimal("1.5"), 2)),
]
LANG = ["gemäß Angebot vom 14. September 2026, Leistungsphasen 3 bis 5 nach HOAI",
        "einschließlich Protokoll und Fotodokumentation",
        "für das Bauvorhaben Erweiterung Lagerhalle, Abschnitt B"]


class Geo:
    def __init__(self, fmt):
        self.fmt = fmt
        self.g = 1.0 if fmt == "A4" else 0.7071
        self.seite = A4 if fmt == "A4" else A5

    def __call__(self, v):
        return v * self.g

    def s(self, pt):                     # Schriftgröße, nie unter 7 pt
        return max(7.0, round(pt * self.g * 1.06, 2)) if self.g < 1 else pt


BANKTEXT = "an die unten angegebene Bankverbindung."


def zahlungstext(s, datum, brutto, faellig, sk_datum, sk_betrag):
    # Vorlage: „Zahlung innerhalb von 14 Tagen ab Rechnungseingang ohne Abzüge an die unten angegebene
    # Bankverbindung.“ (zweizeilig gesetzt). Skonto und festes Datum gibt es in der Vorlage nicht; sie sind im
    # selben Satzbau formuliert, das feste Datum ausgeschrieben wie das Rechnungsdatum.
    if s.zahlung == "skonto":
        return [f"Zahlung innerhalb von {s.skonto_tage} Tagen ab Rechnungseingang mit {s.skonto} % Skonto, innerhalb",
                f"von {s.ziel} Tagen ohne Abzüge {BANKTEXT}"]
    if s.zahlung == "fest":
        return [f"Zahlung bis zum {de_lang(faellig)} ohne Abzüge an die unten angegebene",
                "Bankverbindung."]
    return [f"Zahlung innerhalb von {s.ziel} Tagen ab Rechnungseingang ohne Abzüge an die unten angegebene",
            "Bankverbindung."]


def pos_erzeugen(rng, s):
    g = Geo(s.format)
    return positionen(rng, KATALOG, s.anzahl, s.lang, LANG, g(260), R, g.s(10), max_zeilen=3)


def plan(ps, s):
    return seitenplan(ps, lambda p: len(p.beschreibung) + 1, erste=19, folge=40, summen=4)


def zeichnen(pfad, d, ps, seiten, s):
    from reportlab.lib.colors import Color
    from reportlab.pdfbase.pdfmetrics import stringWidth
    g = Geo(s.format)
    W, H = g.seite
    c = leinwand(pfad, g.seite, f"Rechnung {d['invoice']['number']}", AB.name)
    b = Blatt(c, H)
    k, inv, t = d["buyer"], d["invoice"], d["totals_printed"]
    L, RR = g(56), W - g(56)
    grau = Color(0.93, 0.93, 0.93)
    c.drawImage(ImageReader(logo_png("IB")), g(400), H - g(78), g(140), g(46))
    sl = f"{AB.name}, {AB.strasse}, {AB.plz} {AB.ort}"
    b.text(L, g(140), sl, B, g.s(7))
    b.linie(L, g(141.5), L + stringWidth(sl, B, g.s(7)), 0.3)
    for j, z in enumerate(k["name_lines"] + [k["street"], f"{k['postal_code']} {k['city']}"]):
        b.text(L, g(160 + 12.5 * j), z, B if j == 0 else R, g.s(10.5))
    rechts = [(AB.name, "", B), (AB.strasse, "", R), (f"{AB.plz} {AB.ort}", "", R), ("", "", R),
              ("Tel.:", AB.telefon, B), ("E-Mail:", AB.email, B), ("", "", R),
              ("Kundennummer:", k["customer_number"], B),
              ("Liefer-/Leistungsdatum:", de(_d(inv["service_date"])), B)]
    for j, (lab, w, f) in enumerate(rechts):
        y = g(160 + 11.5 * j)
        b.text(g(338), y, lab, f, g.s(9.5) if j < 3 else g.s(9))
        if w:
            b.text(g(446), y, w, R, g.s(9))
    y0 = g(300)
    b.text(L, y0, f"Honorarrechnung Nr. {inv['number']}", B, g.s(12))
    b.text(RR, y0, f"{AB.ort}, den {de_lang(_d(inv['date']))}", R, g.s(10), art="r")
    b.text(L, y0 + g(26), "Sehr geehrte Damen und Herren,", R, g.s(10))
    b.text(L, y0 + g(48), "Wir bedanken uns für die gute Zusammenarbeit und stellen Ihnen vereinbarungsgemäß "
                          "folgende", R, g.s(10))
    b.text(L, y0 + g(61), "Lieferungen und Leistungen in Rechnung:", R, g.s(10))
    xs = dict(pos=g(62), menge=g(98), bez=g(162), ep=g(456), gp=RR - g(4))
    yk = y0 + g(90)
    b.kasten(L, yk - g(12), RR, yk + g(6), 0, grau, grau)
    for x, txt, a in [(xs["pos"], "Pos.", "l"), (xs["menge"], "Menge", "l"), (xs["bez"], "Bezeichnung", "l"),
                      (xs["ep"], "Einzelpreis", "r"), (xs["gp"], "Gesamtpreis", "r")]:
        b.text(x, yk, txt, B, g.s(9.5), art=a)
    takt, z = g(13), 0
    y1 = yk + g(22)
    c.setDash(1, 2)
    for i, p in enumerate(ps):
        y = y1 + takt * z
        b.text(xs["pos"], y, f"{i + 1}", R, g.s(10))
        b.text(xs["menge"], y, f"{menge(p.qty)} {p.unit}", R, g.s(10))
        for j, zl in enumerate(p.beschreibung):
            b.text(xs["bez"], y + takt * j, zl, R, g.s(10))
        b.text(xs["ep"], y, zahl(p.preis) + " EUR", R, g.s(10), art="r")
        b.text(xs["gp"], y, zahl(p.gesamt) + " EUR", R, g.s(10), art="r")
        z += len(p.beschreibung) + 1
        b.linie(L, y1 + takt * z - takt * 0.9, RR, 0.4, GRAU)
    c.setDash()
    y = y1 + takt * z + g(10)
    for j, (lab, w, f) in enumerate([("Zwischensumme", t["net"], R), ("19% MwSt.", t["vat"], R),
                                     ("Gesamtbetrag", t["gross"], B)]):
        yy = y + g(15) * j
        if j == 2:
            b.kasten(g(330), yy - g(11), RR, yy + g(5), 0, grau, grau)
        b.text(g(430), yy, lab, f, g.s(10), art="r")
        b.text(xs["gp"], yy, zahl(Decimal(w)) + " EUR", f, g.s(10), art="r")
    y += g(15) * 3 + g(24)
    for j, zl in enumerate(d["payment_terms_text"]):
        b.text(L, y + g(13) * j, zl, R, g.s(10))
    y += g(13) * len(d["payment_terms_text"]) + g(14)
    b.text(L, y, "Bei Rückfragen stehen wir Ihnen jederzeit zur Verfügung.", R, g.s(10))
    b.text(L, y + g(26), "Herzliche Grüße,", R, g.s(10))
    b.text(L, y + g(39), AB.gf, R, g.s(10))
    fuss = [f"{AB.name} · {AB.bank} · IBAN {AB.iban} · BIC {AB.bic}",
            f"Sitz der Gesellschaft: {AB.ort}, Deutschland · Geschäftsführung: {AB.gf} · Handelsregister: "
            f"{AB.register} · USt-IdNr. {AB.ust_id}"]
    if g.g < 1:                              # A5: zweite Fußzeile passt bei 7 pt nicht in die Breite
        a1, b1 = fuss[0].split(" · IBAN ")
        a2, b2 = fuss[1].split(" · Handelsregister: ")
        fuss = [a1, "IBAN " + b1, a2, "Handelsregister: " + b2]
    fy = H - g(52) - (g(10) if g.g < 1 else 0)
    for j, zl in enumerate(fuss):
        b.text(L, fy + max(8, g(10)) * j, zl, R, g.s(6.5), GRAU)
    c.showPage()
    c.save()


def _d(s):
    from datetime import date
    t, m, j = map(int, s.split("."))
    return date(j, m, t)


def nummer(n, rng, datum):
    return f"{datum:%Y}-{410 + n * 6 + rng.randint(0, 4):04d}"


def bestellnr(rng):
    return f"BV-{rng.randint(100, 999)}/26"


def muss(d, ps, seiten, s):
    t = d["totals_printed"]
    return [(1, f"Gesamtbetrag {zahl(Decimal(t['gross']))} EUR"),
            (1, f"{AB.ort}, den {de_lang(_d(d['invoice']['date']))}"),
            (1, f"Honorarrechnung Nr. {d['invoice']['number']}")]


SPEZ = [
    Spez(14, anzahl=3, zahlung="netto", ziel=14, bestellung=False,
         notiz="Leistungen in Std., 14 Tage ab Rechnungseingang"),
    Spez(15, anzahl=4, lang=2, zahlung="skonto", skonto=2, skonto_tage=7, ziel=30, bestellung=False,
         notiz="Firmenname zweizeilig, Skonto in Tagen"),
    Spez(16, anzahl=3, lang=1, zahlung="fest", ziel=30, bestellung=False,
         notiz="3 Namenszeilen, festes Zahldatum ausgeschrieben"),
    Spez(17, anzahl=2, zahlung="netto", ziel=14, holdout=True, format="A5", bestellung=False,
         notiz="Hold-out: A5 (Koordinaten × 0,7071, Schrift ≥ 7 pt)"),
    Spez(7, anzahl=4, lang=1, zahlung="skonto", skonto=3, skonto_tage=10, ziel=30, holdout=True, pruefen="brutto",
         bestellung=False,
         notiz="Hold-out PRÜFEN: gedruckter Gesamtbetrag 1,00 € über Netto + USt"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege, nur angehängt (Belege 1–5 bleiben byte-gleich)
    Spez(15, anzahl=3, lang=1, zahlung="netto", ziel=14, holdout=True, bestellung=False, fehler="iban_pruefziffer",
         notiz="Hold-out FEHLER: IBAN im Fuß mit vertauschten Prüfziffern"),
]

FAMILIE = Familie(
    nr=2, ordner="f02_briefkopf", titel="Briefkopf mit Logo und ausgeschriebenem Datum (nach Lexware-Vorlage)",
    absender=AB, quelle="Q2", seed=26_4722, schrift="Times-Roman", spez=SPEZ, nummer=nummer, bestellnr=bestellnr,
    zahlungstext=zahlungstext, pos_erzeugen=pos_erzeugen, plan=plan, zeichnen=zeichnen,
    datum_druck=lambda d: de_lang(d), datum_format="ausgeschrieben („3. November 2026“)")
