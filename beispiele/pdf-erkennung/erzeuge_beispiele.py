# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Erzeugt die Beispiele zur PDF-Erkennung: sechs erfundene Verkäufer mit je eigenem Druck-Layout,
je acht Rechnungen (sieben zum Anlernen, die achte für „nur PDF“) (CSV-Export + Druck-PDF) und einige absichtlich fehlerhafte Fälle.

Alle Namen, Anschriften, Kennungen und Bankdaten sind erfunden. USt-IdNr. und IBAN haben gültige
Prüfziffern (BLZ 000 000 00 gibt es nicht). Aufruf:  python erzeuge_beispiele.py
Das Ergebnis ist deterministisch (fester Zufallsstartwert)."""
from __future__ import annotations

import calendar
import csv
import io
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HIER = Path(__file__).parent
EINGANG = HIER / "eingang"
FEHLER = HIER / "fehlerfaelle"
B, H = A4
C2 = Decimal("0.01")
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]


# ------------------------------------------------------------------ Prüfziffern
def ust_id(basis8: str) -> str:
    """DE + 8 Ziffern + Prüfziffer nach ISO 7064 MOD 11,10."""
    produkt = 10
    for z in basis8:
        summe = (int(z) + produkt) % 10 or 10
        produkt = (2 * summe) % 11
    pz = 11 - produkt
    return f"DE{basis8}{0 if pz == 10 else pz}"


def iban(konto10: str) -> str:
    """Deutsche IBAN mit erfundener BLZ 00000000, Prüfziffer nach ISO 13616 (mod 97)."""
    bban = "00000000" + konto10
    pz = 98 - int(bban + "131400") % 97
    return f"DE{pz:02d}{bban}"


def iban_gruppiert(i: str) -> str:
    return " ".join(i[k:k + 4] for k in range(0, len(i), 4))


# ------------------------------------------------------------------ Zahlen
def de(d: Decimal) -> str:
    s = f"{d:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def en(d: Decimal) -> str:
    return f"{d:,.2f}"


def menge_de(m: Decimal) -> str:
    return str(m.normalize()).replace(".", ",") if m != m.to_integral() else str(int(m))


def menge_en(m: Decimal) -> str:
    return str(m.normalize()) if m != m.to_integral() else str(int(m))


def satz_txt(s: int) -> str:
    return f"{s} %"


@dataclass
class Pos:
    text: str
    menge: Decimal
    einheit: str           # wie in WaWi/Druck
    preis: Decimal
    satz: int              # 0 = steuerfrei
    artnr: str = ""

    @property
    def betrag(self) -> Decimal:
        return (self.menge * self.preis).quantize(C2, ROUND_HALF_UP)


@dataclass
class Rechnung:
    nr: str
    datum: date
    kunde: dict
    pos: list[Pos]
    leistung: date | None = None
    von: date | None = None
    bis: date | None = None
    monat: tuple[int, int] | None = None
    extra: dict = field(default_factory=dict)

    def netto_je_satz(self) -> dict[int, Decimal]:
        out: dict[int, Decimal] = {}
        for p in self.pos:
            out[p.satz] = out.get(p.satz, Decimal("0")) + p.betrag
        return dict(sorted(out.items()))

    def ust_je_satz(self) -> dict[int, Decimal]:
        return {s: (n * s / 100).quantize(C2, ROUND_HALF_UP) for s, n in self.netto_je_satz().items()}

    @property
    def netto(self) -> Decimal:
        return sum((p.betrag for p in self.pos), Decimal("0"))

    @property
    def ust(self) -> Decimal:
        return sum(self.ust_je_satz().values(), Decimal("0"))

    @property
    def brutto(self) -> Decimal:
        return self.netto + self.ust


# ------------------------------------------------------------------ Zeichnen (Koordinaten von oben)
class Blatt:
    def __init__(self, pfad: Path, schrift="Helvetica"):
        self.c = canvas.Canvas(str(pfad), pagesize=A4, invariant=1)
        self.c.setTitle(pfad.stem)
        self.c.setAuthor("Fakturafalter-Beispiel (erfunden)")
        self.schrift = schrift

    def t(self, x, top, text, size=9, fett=False, rechts=False, mitte=False, schrift=None):
        f = schrift or self.schrift
        f = f + "-Bold" if fett else f
        self.c.setFont(f, size)
        y = H - top - size
        if rechts:
            self.c.drawRightString(x, y, text)
        elif mitte:
            self.c.drawCentredString(x, y, text)
        else:
            self.c.drawString(x, y, text)

    def linie(self, x0, top, x1, dick=0.5, strich=None):
        self.c.setLineWidth(dick)
        self.c.setDash(*strich) if strich else self.c.setDash()
        self.c.line(x0, H - top, x1, H - top)
        self.c.setDash()

    def senk(self, x, top0, top1, dick=0.5):
        self.c.setLineWidth(dick)
        self.c.line(x, H - top0, x, H - top1)

    def flaeche(self, x, top, b, h, grau=0.92):
        self.c.setFillGray(grau)
        self.c.rect(x, H - top - h, b, h, stroke=0, fill=1)
        self.c.setFillGray(0)

    def seite(self):
        self.c.showPage()

    def fertig(self):
        self.c.showPage()
        self.c.save()


def umbrechen(text: str, breite: int) -> list[str]:
    zeilen, akt = [], ""
    for w in text.split():
        if akt and len(akt) + 1 + len(w) > breite:
            zeilen.append(akt)
            akt = w
        else:
            akt = f"{akt} {w}".strip()
    return zeilen + [akt]


def ust_saetze_satz(r: Rechnung) -> list[int]:
    return [s for s in r.netto_je_satz() if s]


# ------------------------------------------------------------------ Verkäufer und Layouts
class Verkaeufer:
    kurz = ""
    name = ""
    profil_kopf = ""

    def __init__(self):
        self.zz = random.Random(self.kurz)

    def rechnungen(self) -> list[Rechnung]:
        raise NotImplementedError

    def zeichnen(self, r: Rechnung, pfad: Path, **abw) -> None:
        raise NotImplementedError

    def csv_zeilen(self, r: Rechnung) -> list[list[str]]:
        raise NotImplementedError

    spalten: list[str] = []
    trenn = ";"
    kodierung = "utf-8"

    def csv_schreiben(self, r: Rechnung, pfad: Path) -> None:
        puffer = io.StringIO()
        w = csv.writer(puffer, delimiter=self.trenn, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(self.spalten)
        for z in self.csv_zeilen(r):
            w.writerow(z)
        pfad.write_bytes(puffer.getvalue().encode(self.kodierung))


# --- 1 Bäckerei: Anschrift links, Infoblock rechts „Etikett: Wert“, Tabelle mit Gitterlinien, 7/19 %
class Baeckerei(Verkaeufer):
    kurz = "baeckerei"
    name = "Bäckerei Sonnenkorn GmbH"
    ust = ust_id("27140815")
    iban = iban("0004711001")
    spalten = ["Rechnungsnr", "Datum", "Lieferdatum", "Kunde", "Strasse", "PLZ", "Ort",
               "Artikel", "Menge", "Einheit", "Einzelpreis", "USt-Satz"]
    ARTIKEL = [("Roggenmischbrot 1000 g", "Stk", "3.40", 7), ("Dinkelbrötchen", "Stk", "0.55", 7),
               ("Butterhörnchen", "Stk", "0.95", 7), ("Apfelkuchen Blech", "kg", "11.80", 7),
               ("Kaffee Bohne Hausröstung", "kg", "24.90", 7), ("Quarkbällchen", "kg", "9.60", 7),
               ("Brotkorb Leihgebühr", "Stk", "2.50", 19), ("Lieferpauschale Innenstadt", "Stk", "6.00", 19)]
    KUNDEN = [{"name": "Café Morgenrot", "strasse": "Lindenplatz 2", "plz": "31134", "ort": "Hildesheim"},
              {"name": "Hotel Am Stadtpark GmbH", "strasse": "Parkallee 18", "plz": "31135", "ort": "Hildesheim"},
              {"name": "Kantine Werkhof eG", "strasse": "Industriestraße 40", "plz": "31137", "ort": "Hildesheim"}]

    def rechnungen(self):
        out = []
        for i in range(8):
            d = date(2026, 10, 2) + timedelta(days=4 * i)
            # immer 7 % und 19 % gemischt (Druck zeigt die USt nur je Satz)
            art = self.zz.sample(self.ARTIKEL[:6], self.zz.randint(2, 4)) + self.zz.sample(self.ARTIKEL[6:], self.zz.randint(1, 2))
            pos = [Pos(a, Decimal(str(self.zz.choice([12, 24, 30, 40, 60]))) if e == "Stk"
                       else Decimal(str(self.zz.choice(["2.5", "4", "1.75", "6"]))), e, Decimal(p), s)
                   for a, e, p, s in art]
            out.append(Rechnung(f"SK-2026-{412 + i:04d}", d, self.KUNDEN[i % 3], pos, leistung=d - timedelta(days=1)))
        return out

    def csv_zeilen(self, r):
        k = r.kunde
        return [[r.nr, f"{r.datum:%d.%m.%Y}", f"{r.leistung:%d.%m.%Y}", k["name"], k["strasse"], k["plz"], k["ort"],
                 p.text, menge_de(p.menge), p.einheit, de(p.preis), str(p.satz)] for p in r.pos]

    def zeichnen(self, r, pfad, nr=None, ib=None):
        b = Blatt(pfad)
        b.t(50, 40, self.name, 16, fett=True)
        b.t(50, 60, "Feines aus Korn und Ofen · Kornweg 3 · 31134 Hildesheim", 8)
        b.t(50, 120, f"{self.name} · Kornweg 3 · 31134 Hildesheim", 6)
        for j, z in enumerate([r.kunde["name"], r.kunde["strasse"], f"{r.kunde['plz']} {r.kunde['ort']}"]):
            b.t(50, 132 + j * 13, z, 10)
        for j, (lab, w) in enumerate([("Rechnungsnr.:", nr or r.nr), ("Datum:", f"{r.datum:%d.%m.%Y}"),
                                      ("Lieferdatum:", f"{r.leistung:%d.%m.%Y}"), ("Seite:", "1 von 1")]):
            b.t(360, 120 + j * 14, lab, 9)
            b.t(450, 120 + j * 14, w, 9)
        b.t(50, 220, "Rechnung", 14, fett=True)
        xs = [45, 75, 270, 330, 375, 445, 490, 550]
        kopf = ["Pos", "Artikel", "Menge", "Einheit", "Einzelpreis", "USt", "Gesamt"]
        top = 250
        b.flaeche(45, top, 505, 16, 0.85)
        for x, k in zip(xs, kopf):
            b.t(x + 3, top + 4, k, 8, fett=True)
        b.linie(45, top, 550)
        top += 16
        b.linie(45, top, 550)
        for n, p in enumerate(r.pos, 1):
            b.t(48, top + 4, str(n), 9)
            b.t(78, top + 4, p.text, 9)
            b.t(xs[3] - 4, top + 4, menge_de(p.menge), 9, rechts=True)
            b.t(xs[3] + 3, top + 4, p.einheit, 9)
            b.t(xs[5] - 4, top + 4, de(p.preis) + " €", 9, rechts=True)
            b.t(xs[6] - 4, top + 4, satz_txt(p.satz), 9, rechts=True)
            b.t(xs[7] - 4, top + 4, de(p.betrag) + " €", 9, rechts=True)
            top += 17
            b.linie(45, top, 550)
        for x in xs:
            b.senk(x, 250, top)
        top += 14
        b.t(380, top, "Summe netto", 9)
        b.t(546, top, de(r.netto) + " €", 9, rechts=True)
        for s, u in r.ust_je_satz().items():           # nur USt je Satz, keine USt-Gesamtsumme
            top += 13
            b.t(380, top, f"USt {s} % auf {de(r.netto_je_satz()[s])}", 9)
            b.t(546, top, de(u) + " €", 9, rechts=True)
        top += 16
        b.t(380, top, "Rechnungsbetrag", 10, fett=True)
        b.t(546, top, de(r.brutto) + " €", 10, fett=True, rechts=True)
        b.t(50, top + 40, "Zahlbar innerhalb 14 Tagen ohne Abzug.", 9)
        b.linie(45, 780, 550)
        b.t(50, 786, f"{self.name} · Kornweg 3 · 31134 Hildesheim · Amtsgericht Hildesheim HRB 990001", 7)
        b.t(50, 796, f"USt-IdNr.: {self.ust} · Beispielbank · IBAN: {iban_gruppiert(ib or self.iban)}", 7)
        b.fertig()


# --- 2 Elektro: Seitenband links mit Etikett über Wert, Anschrift rechts, Tabelle ohne Linien,
#     Spalten Menge/Einh./Bezeichnung, mehrzeilige Bezeichnungen, eine Rechnung über zwei Seiten
class Elektro(Verkaeufer):
    kurz = "elektro"
    name = "Elektro Funke e.K."
    ust = ust_id("31415926")
    iban = iban("0002718281")
    trenn = ","
    kodierung = "cp1252"
    spalten = ["belegnr", "belegdatum", "leistungsdatum", "kunde", "strasse", "plz", "ort",
               "menge", "einheit", "bezeichnung", "preis", "ust"]
    ARTIKEL = [("Arbeitszeit Elektromeister", "h", "68.00"), ("Arbeitszeit Geselle", "h", "54.50"),
               ("Mantelleitung NYM-J 3x1,5 mm² grau, Ring 50 m, verlegt auf Putz inklusive Schellen", "m", "1.85"),
               ("Schalterprogramm reinweiß Wechselschalter mit Rahmen einfach", "Stk", "12.40"),
               ("Steckdose Schuko mit Klappdeckel für Feuchtraum IP44", "Stk", "9.90"),
               ("LED-Panel 60x60 cm neutralweiß 4000 K, Einbau in Rasterdecke", "Stk", "79.00"),
               ("Fehlerstromschutzschalter 40 A 30 mA vierpolig", "Stk", "64.80"),
               ("Kabelkanal 40x60 mm", "m", "7.20"), ("Anfahrt Stadtgebiet", "Stk", "29.00")]
    KUNDEN = [{"name": "Wohnbau Nordring GmbH", "strasse": "Nordring 14", "plz": "44787", "ort": "Bochum"},
              {"name": "Praxis Dr. Beispiel", "strasse": "Hellweg 3", "plz": "44787", "ort": "Bochum"}]

    def rechnungen(self):
        out = []
        for i in range(8):
            d = date(2026, 10, 5) + timedelta(days=3 * i)
            n = 32 if i == 2 else self.zz.randint(3, 6)
            pos = []
            for j in range(n):
                a, e, p = self.ARTIKEL[j % len(self.ARTIKEL)] if n > 9 else self.zz.choice(self.ARTIKEL)
                m = Decimal(str(self.zz.choice([1, 2, 3, 4.5, 6, 25, 40]))) if e != "Stk" else Decimal(self.zz.randint(1, 8))
                pos.append(Pos(a if n <= 9 else f"{a} Raum {j // len(self.ARTIKEL) + 1}", m, e, Decimal(p), 19))
            out.append(Rechnung(f"EF-{1041 + i}", d, self.KUNDEN[i % 2], pos, leistung=d - timedelta(days=2)))
        return out

    def csv_zeilen(self, r):
        k = r.kunde
        return [[r.nr, f"{r.datum:%d.%m.%Y}", f"{r.leistung:%d.%m.%Y}", k["name"], k["strasse"], k["plz"], k["ort"],
                 menge_en(p.menge), p.einheit, p.text, f"{p.preis:.2f}", "19"] for p in r.pos]

    def _kopf(self, b, r, seite, seiten, nr):
        b.flaeche(30, 30, 125, 230, 0.90)
        b.t(40, 40, "ELEKTRO", 15, fett=True)
        b.t(40, 58, "FUNKE e.K.", 11, fett=True)
        for j, (lab, w) in enumerate([("Beleg-Nr.", nr), ("Belegdatum", f"{r.datum:%d.%m.%Y}"),
                                      ("Leistungsdatum", f"{r.leistung:%d.%m.%Y}"), ("Seite", f"{seite} / {seiten}")]):
            b.t(40, 100 + j * 36, lab, 7)
            b.t(40, 111 + j * 36, w, 10, fett=True)
        if seite == 1:
            b.t(330, 70, "Elektro Funke e.K. · Hellweg 120 · 44787 Bochum", 6)
            for j, z in enumerate([r.kunde["name"], r.kunde["strasse"], f"{r.kunde['plz']} {r.kunde['ort']}"]):
                b.t(330, 84 + j * 13, z, 10)
            b.t(330, 200, "RECHNUNG", 16, fett=True)

    def _fuss(self, b, ib):
        b.t(40, 790, f"Elektro Funke e.K., Inh. Jan Funke · Hellweg 120 · 44787 Bochum · HRA 77001 AG Bochum", 7)
        b.t(40, 800, f"USt-IdNr. {self.ust} · Bank: IBAN {iban_gruppiert(ib or self.iban)}", 7)

    def zeichnen(self, r, pfad, nr=None, ib=None):
        b = Blatt(pfad)
        x_m, x_e, x_b, x_p, x_g = 70, 78, 118, 470, 550
        zeilen = []
        for p in r.pos:
            teile = umbrechen(p.text, 52)
            zeilen.append((p, teile))
        # Seitenumbruch planen
        seiten, akt, hoehe = [], [], 0
        for p, teile in zeilen:
            h = 13 * len(teile) + 3
            if hoehe + h > 440:
                seiten.append(akt)
                akt, hoehe = [], 0
            akt.append((p, teile))
            hoehe += h
        seiten.append(akt)
        uebertrag = Decimal("0")
        for sn, inhalt in enumerate(seiten, 1):
            self._kopf(b, r, sn, len(seiten), nr or r.nr)
            top = 280
            for x, k, re_ in ((x_m, "Menge", True), (x_e, "Einh.", False), (x_b, "Bezeichnung", False),
                              (x_p, "E-Preis", True), (x_g, "Betrag", True)):
                b.t(x, top, k, 8, fett=True, rechts=re_)
            top += 18
            if sn > 1:
                b.t(x_p, top, "Übertrag:", 9, rechts=True)
                b.t(x_g, top, de(uebertrag), 9, rechts=True)
                top += 18
            for p, teile in inhalt:
                b.t(x_m, top, menge_de(p.menge), 9, rechts=True)
                b.t(x_e, top, p.einheit, 9)
                b.t(x_p, top, de(p.preis), 9, rechts=True)
                b.t(x_g, top, de(p.betrag), 9, rechts=True)
                for t_ in teile:
                    b.t(x_b, top, t_, 9)
                    top += 13
                top += 3
                uebertrag += p.betrag
            if sn < len(seiten):
                top += 8
                b.t(x_p, top, "Übertrag:", 9, rechts=True)
                b.t(x_g, top, de(uebertrag), 9, rechts=True)
                self._fuss(b, ib)
                b.seite()
        top += 14
        b.t(380, top, "Nettobetrag", 9)
        b.t(x_g, top, de(r.netto), 9, rechts=True)
        top += 13
        b.t(380, top, "zzgl. 19 % USt", 9)
        b.t(x_g, top, de(r.ust), 9, rechts=True)
        top += 15
        b.t(380, top, "Rechnungsbetrag EUR", 10, fett=True)
        b.t(x_g, top, de(r.brutto), 10, fett=True, rechts=True)
        b.t(118, top + 40, "Zahlbar innerhalb 14 Tagen ohne Abzug.", 9)
        self._fuss(b, ib)
        b.fertig()


# --- 3 Gartenbau: Kopf mittig, Anschrift rechts, Etikettenzeile über Wertezeile, nur waagerechte
#     Linien, Leistungsmonat als „Oktober 2026“, Nachlass als Zeile mit negativer Menge
class Gartenbau(Verkaeufer):
    kurz = "gartenbau"
    name = "Gartenbau Lindgrün GmbH"
    ust = ust_id("44556677")
    iban = iban("0001230456")
    trenn = "\t"
    spalten = ["Rechnungsnummer", "Rechnungsdatum", "Leistungsmonat", "Kunde", "Strasse", "PLZ", "Ort",
               "Leistung", "Menge", "Einheit", "Preis", "MwSt"]
    ARTIKEL = [("Rasen mähen inkl. Grünschnittentsorgung", "m²", "0.18"), ("Heckenschnitt Liguster", "m", "4.20"),
               ("Pflege Staudenbeete", "h", "46.00"), ("Laub aufnehmen und abfahren", "pauschal", "120.00"),
               ("Baumschnitt Obstgehölze", "h", "52.00"), ("Rindenmulch liefern und verteilen", "m²", "3.90")]
    KUNDEN = [{"name": "WEG Am Weiher 4-8", "strasse": "Am Weiher 4", "plz": "79098", "ort": "Freiburg im Breisgau"},
              {"name": "Seniorenstift Rosenhof gGmbH", "strasse": "Rosenweg 1", "plz": "79100", "ort": "Freiburg im Breisgau"}]

    def rechnungen(self):
        out = []
        for i in range(8):
            j, m = 2026, 2 + i
            d = date(j, m, calendar.monthrange(j, m)[1]) + timedelta(days=2)
            pos = []
            for a, e, p in self.zz.sample(self.ARTIKEL, self.zz.randint(3, 5)):
                menge = {"m²": Decimal(self.zz.choice([350, 420, 800])), "m": Decimal(self.zz.choice([35, 60])),
                         "h": Decimal(self.zz.choice(["2", "3.5", "6"])), "pauschal": Decimal(1)}[e]
                pos.append(Pos(a, menge, e, Decimal(p), 19))
            if i % 2 == 0:
                pos.append(Pos("Nachlass Pflegevertrag", Decimal(-1), "pauschal", Decimal("25.00"), 19))
            out.append(Rechnung(f"GL-2026-{118 + i}", d, self.KUNDEN[i % 2], pos, monat=(j, m)))
        return out

    def csv_zeilen(self, r):
        k = r.kunde
        return [[r.nr, f"{r.datum:%Y-%m-%d}", f"{r.monat[0]}-{r.monat[1]:02d}", k["name"], k["strasse"], k["plz"],
                 k["ort"], p.text, menge_de(p.menge), p.einheit, de(p.preis), "19"] for p in r.pos]

    def zeichnen(self, r, pfad, nr=None, ib=None):
        b = Blatt(pfad)
        b.t(B / 2, 36, "Lindgrün", 22, fett=True, mitte=True)
        b.t(B / 2, 62, "Gartenbau Lindgrün GmbH · Garten- und Landschaftspflege", 9, mitte=True)
        b.linie(60, 80, B - 60, 1.2)
        b.t(330, 112, "Gartenbau Lindgrün GmbH · Wiesenpfad 12 · 79098 Freiburg", 6)
        for j, z in enumerate([r.kunde["name"], r.kunde["strasse"], f"{r.kunde['plz']} {r.kunde['ort']}"]):
            b.t(330, 124 + j * 13, z, 10)
        b.t(60, 200, "Rechnung", 15, fett=True)
        monat = f"{MONATE[r.monat[1] - 1]} {r.monat[0]}"
        for x, lab, w in ((60, "Rechnungsnummer", nr or r.nr), (190, "Rechnungsdatum", f"{r.datum:%d.%m.%Y}"),
                          (320, "Leistungszeitraum", monat)):
            b.t(x, 232, lab, 7)
            b.t(x, 244, w, 10)
        top = 285
        b.linie(60, top - 4, B - 60, 1)
        for x, k, re_ in ((60, "Leistung", False), (360, "Menge", True), (368, "Einheit", False),
                          (470, "Preis", True), (535, "Betrag", True)):
            b.t(x, top, k, 8, fett=True, rechts=re_)
        top += 14
        b.linie(60, top - 2, B - 60, 0.6)
        for p in r.pos:
            top += 5
            b.t(60, top, p.text, 9)
            b.t(360, top, menge_de(p.menge), 9, rechts=True)
            b.t(368, top, p.einheit, 9)
            b.t(470, top, de(p.preis), 9, rechts=True)
            b.t(535, top, de(p.betrag), 9, rechts=True)
            top += 14
            b.linie(60, top, B - 60, 0.3)
        top += 12
        for lab, w, f in (("Nettobetrag", r.netto, False), ("MwSt. 19 %", r.ust, False), ("Gesamtbetrag", r.brutto, True)):
            b.t(368, top, lab, 9, fett=f)
            b.t(535, top, de(w) + " EUR", 9, fett=f, rechts=True)
            top += 14
        b.t(60, top + 30, "Zahlbar innerhalb 14 Tagen ohne Abzug.", 9)
        b.linie(60, 778, B - 60, 0.6)
        b.t(B / 2, 784, "Gartenbau Lindgrün GmbH · Wiesenpfad 12 · 79098 Freiburg · AG Freiburg HRB 990003", 7, mitte=True)
        b.t(B / 2, 794, f"USt-IdNr. {self.ust} · IBAN {iban_gruppiert(ib or self.iban)}", 7, mitte=True)
        b.fertig()


# --- 4 Musikschule: nur Steuernummer, Vereinsregister, Datum ausgeschrieben, Leistungszeitraum von–bis,
#     steuerfreier Unterricht (§ 4 Nr. 21 UStG) und Noten mit 7 %, Privatkunde
class Musikschule(Verkaeufer):
    kurz = "musikschule"
    name = "Musikschule Klangraum e.V."
    stnr = "21/815/08150"
    iban = iban("0008150815")
    spalten = ["Rechnungsnummer", "Rechnungsdatum", "Leistung von", "Leistung bis", "Name", "Strasse", "PLZ",
               "Ort", "Leistung", "Menge", "Einheit", "Preis", "Steuersatz"]
    UNTERRICHT = [("Einzelunterricht Klavier", "h", "48.00"), ("Einzelunterricht Gitarre", "h", "44.00"),
                  ("Bandprobe Jugendensemble", "pauschal", "35.00"), ("Musikalische Früherziehung", "pauschal", "28.00")]
    NOTEN = [("Notenheft Klavierschule Band 1", "Stk", "14.50"), ("Gitarrensaiten Satz", "Stk", "9.80")]
    KUNDEN = [{"name": "Lena Beispiel", "strasse": "Amselweg 7", "plz": "93047", "ort": "Regensburg"},
              {"name": "Familie Muster", "strasse": "Domplatz 9", "plz": "93047", "ort": "Regensburg"}]

    def rechnungen(self):
        out = []
        for i in range(8):
            von = date(2026, 2 + i, 1)
            bis = date(von.year, von.month, calendar.monthrange(von.year, von.month)[1])
            pos = [Pos(a, Decimal(self.zz.choice(["3", "3.75", "4", "4.5"])) if e == "h" else Decimal(1), e, Decimal(p), 0)
                   for a, e, p in self.zz.sample(self.UNTERRICHT, 2)]
            pos += [Pos(a, Decimal(self.zz.randint(1, 2)), e, Decimal(p), 7) for a, e, p in self.zz.sample(self.NOTEN, 1)]
            out.append(Rechnung(f"KR-2026-{31 + i:03d}", bis + timedelta(days=3), self.KUNDEN[i % 2], pos, von=von, bis=bis))
        return out

    def csv_zeilen(self, r):
        k = r.kunde
        v = f"{r.von:%d.%m.%Y}" if r.von else ""
        b_ = f"{r.bis:%d.%m.%Y}" if r.bis else ""
        return [[r.nr, f"{r.datum:%d.%m.%Y}", v, b_, k["name"], k["strasse"], k["plz"], k["ort"], p.text,
                 menge_de(p.menge), p.einheit, de(p.preis), str(p.satz)] for p in r.pos]

    def zeichnen(self, r, pfad, nr=None, ib=None, ohne_zeitraum=False):
        b = Blatt(pfad)
        b.t(50, 40, "Musikschule Klangraum e.V.", 18, fett=True)
        b.t(50, 64, "Unterricht · Ensembles · Früherziehung", 9)
        b.t(50, 105, "Musikschule Klangraum e.V. · Am Ölberg 5 · 93047 Regensburg", 6)
        for j, z in enumerate([r.kunde["name"], r.kunde["strasse"], f"{r.kunde['plz']} {r.kunde['ort']}"]):
            b.t(50, 117 + j * 13, z, 10)
        info = [f"Rechnungsnummer: {nr or r.nr}", f"Rechnungsdatum: {r.datum.day}. {MONATE[r.datum.month - 1]} {r.datum.year}"]
        if not ohne_zeitraum:
            info.append(f"Leistungszeitraum: {r.von:%d.%m.%Y} – {r.bis:%d.%m.%Y}")
        for j, z in enumerate(info):
            b.t(50, 185 + j * 14, z, 10)
        top = 250
        b.linie(50, top - 4, 545, 0.8)
        for x, k, re_ in ((50, "Leistung", False), (300, "Anzahl", True), (306, "Einheit", False),
                          (400, "Preis", True), (440, "Steuer", False), (545, "Betrag", True)):
            b.t(x, top, k, 8, fett=True, rechts=re_)
        top += 16
        for p in r.pos:
            b.t(50, top, p.text, 9)
            b.t(300, top, menge_de(p.menge), 9, rechts=True)
            b.t(306, top, p.einheit, 9)
            b.t(400, top, de(p.preis), 9, rechts=True)
            b.t(440, top, "frei" if p.satz == 0 else satz_txt(p.satz), 9)
            b.t(545, top, de(p.betrag), 9, rechts=True)
            top += 15
        b.linie(50, top, 545, 0.8)
        top += 10
        b.t(330, top, "Summe netto", 9)
        b.t(545, top, de(r.netto), 9, rechts=True)
        for s, u in r.ust_je_satz().items():
            if s:
                top += 13
                b.t(330, top, f"zzgl. {s} % USt", 9)
                b.t(545, top, de(u), 9, rechts=True)
        top += 15
        b.t(330, top, "Rechnungsbetrag", 10, fett=True)
        b.t(545, top, de(r.brutto) + " €", 10, fett=True, rechts=True)
        b.t(50, top + 35, "Unterrichtsleistungen sind umsatzsteuerfrei nach § 4 Nr. 21 UStG.", 9)
        b.t(50, top + 49, "Zahlbar innerhalb 14 Tagen ohne Abzug.", 9)
        b.t(50, 786, "Musikschule Klangraum e.V. · Am Ölberg 5 · 93047 Regensburg · Vereinsregister VR 990004 AG Regensburg", 7)
        b.t(50, 796, f"Steuernummer {self.stnr} · IBAN {iban_gruppiert(ib or self.iban)}", 7)
        b.fertig()


# --- 5 Pixelwerk: englische Etiketten („Invoice No“), ISO-Datum, Zahlen 1,234.56, Zebrastreifen
class Pixelwerk(Verkaeufer):
    kurz = "pixelwerk"
    name = "Pixelwerk Software GmbH"
    ust = ust_id("60708090")
    iban = iban("0004040404")
    trenn = "|"
    kodierung = "utf-8-sig"
    spalten = ["rechnung", "datum", "von", "bis", "kunde", "strasse", "plz", "ort", "text", "menge", "einheit",
               "preis", "ust"]
    ARTIKEL = [("Lizenz Pixelwerk Studio Team", "Stk", "39.00"), ("Support-Stunden", "h", "95.00"),
               ("Hosting Paket M", "pauschal", "149.00"), ("Einrichtung Schnittstelle Warenwirtschaft", "pauschal", "480.00"),
               ("Schulung online", "h", "85.00")]
    KUNDEN = [{"name": "Druckerei Blattwerk GmbH", "strasse": "Papierstraße 21", "plz": "04109", "ort": "Leipzig"},
              {"name": "Agentur Fernblick UG (haftungsbeschränkt)", "strasse": "Karl-Liebknecht-Straße 3", "plz": "04107", "ort": "Leipzig"}]

    def rechnungen(self):
        out = []
        for i in range(8):
            von = date(2026, 2 + i, 1)
            bis = date(von.year, von.month, calendar.monthrange(von.year, von.month)[1])
            pos = [Pos(a, Decimal(self.zz.choice([5, 10, 25])) if e == "Stk" else Decimal(self.zz.choice(["1", "2.5", "4"]))
                       if e == "h" else Decimal(1), e, Decimal(p), 19) for a, e, p in self.zz.sample(self.ARTIKEL, 3)]
            out.append(Rechnung(f"PW-INV-2026-{87 + i:04d}", bis + timedelta(days=1), self.KUNDEN[i % 2], pos, von=von, bis=bis))
        return out

    def csv_zeilen(self, r):
        k = r.kunde
        return [[r.nr, f"{r.datum:%Y-%m-%d}", f"{r.von:%Y-%m-%d}", f"{r.bis:%Y-%m-%d}", k["name"], k["strasse"], k["plz"],
                 k["ort"], p.text, menge_de(p.menge), p.einheit, de(p.preis), "19"] for p in r.pos]

    def zeichnen(self, r, pfad, nr=None, ib=None, datum=None):
        b = Blatt(pfad)
        b.t(545, 36, "PIXELWERK", 20, fett=True, rechts=True)
        b.t(545, 60, "Software · Hosting · Support", 8, rechts=True)
        b.t(50, 110, "Pixelwerk Software GmbH · Gleis 7 · 04109 Leipzig", 6)
        for j, z in enumerate([r.kunde["name"], r.kunde["strasse"], f"{r.kunde['plz']} {r.kunde['ort']}"]):
            b.t(50, 122 + j * 13, z, 10)
        for j, (lab, w) in enumerate([("Invoice No", nr or r.nr), ("Invoice Date", f"{(datum or r.datum):%Y-%m-%d}"),
                                      ("Service period", f"{r.von:%Y-%m-%d} – {r.bis:%Y-%m-%d}")]):
            b.t(340, 110 + j * 14, lab, 8)
            b.t(420, 110 + j * 14, w, 9)
        b.t(50, 205, "Rechnung / Invoice", 14, fett=True)
        top = 240
        b.flaeche(50, top - 4, 495, 16, 0.25)
        b.c.setFillGray(1)
        for x, k, re_ in ((55, "#", False), (75, "Description", False), (360, "Qty", True), (368, "Unit", False),
                          (470, "Unit price", True), (540, "Amount", True)):
            b.t(x, top, k, 8, fett=True, rechts=re_)
        b.c.setFillGray(0)
        top += 18
        for n, p in enumerate(r.pos, 1):
            if n % 2 == 0:
                b.flaeche(50, top - 4, 495, 16, 0.93)
            b.t(55, top, str(n), 9)
            b.t(75, top, p.text, 9)
            b.t(360, top, menge_en(p.menge), 9, rechts=True)
            b.t(368, top, p.einheit, 9)
            b.t(470, top, en(p.preis), 9, rechts=True)
            b.t(540, top, en(p.betrag), 9, rechts=True)
            top += 16
        top += 12
        for lab, w, f in (("Subtotal", r.netto, False), ("VAT 19 %", r.ust, False), ("Total EUR", r.brutto, True)):
            b.t(400, top, lab, 9, fett=f)
            b.t(540, top, en(w), 9, fett=f, rechts=True)
            top += 14
        b.t(50, top + 30, "Zahlbar innerhalb 14 Tagen ohne Abzug. / Payable within 14 days.", 9)
        b.t(50, 786, "Pixelwerk Software GmbH · Gleis 7 · 04109 Leipzig · Amtsgericht Leipzig HRB 990005", 7)
        b.t(50, 796, f"VAT ID {self.ust} · IBAN {iban_gruppiert(ib or self.iban)}", 7)
        b.fertig()


# --- 6 Metallbau: Schreibmaschinen-Optik (Courier), gestrichelte Linien, Datum TT.MM.JJ,
#     Etiketten mit Punktleitern, Artikelnummern, Käufer aus der CSV
class Metallbau(Verkaeufer):
    kurz = "metallbau"
    name = "Metallbau Kessler GmbH"
    ust = ust_id("80080080")
    stnr = "321/5710/4321"
    iban = iban("0000580970")
    kodierung = "cp1252"
    spalten = ["ReNr", "ReDatum", "LiefDatum", "KdNr", "KdName", "Strasse", "PLZ", "Ort", "ArtNr", "Text", "Menge", "ME", "Preis", "MwSt"]
    ARTIKEL = [("ST-4005", "Flachstahl S235 40x5 mm", "m", "6.85"), ("ST-2020", "Winkelstahl 20x20x3", "m", "4.10"),
               ("BL-0200", "Riffelblech 2 mm verzinkt", "kg", "3.95"), ("RO-0040", "Quadratrohr 40x40x2", "m", "8.20"),
               ("SC-0001", "Schweißarbeiten Werkstatt", "Stk", "65.00"), ("VZ-0100", "Feuerverzinkung Lohnarbeit", "kg", "0.92")]
    KUNDEN = [("40117", {"name": "Schlosserei Brandt GmbH", "strasse": "Hammerweg 2", "plz": "58097", "ort": "Hagen"}),
              ("40125", {"name": "Bauhof Ennepetal", "strasse": "Bahnhofstraße 50", "plz": "58256", "ort": "Ennepetal"})]

    def rechnungen(self):
        out = []
        for i in range(8):
            d = date(2026, 9, 20) + timedelta(days=5 * i)
            pos = []
            for a, t, e, p in self.zz.sample(self.ARTIKEL, self.zz.randint(3, 5)):
                m = {"m": Decimal(self.zz.choice(["6", "12", "18.5"])), "kg": Decimal(self.zz.choice(["35", "120.5", "64"])),
                     "Stk": Decimal(self.zz.randint(1, 4))}[e]
                pos.append(Pos(t, m, e, Decimal(p), 19, artnr=a))
            kd, kunde = self.KUNDEN[i % 2]
            out.append(Rechnung(f"MK-26-{412 + i:04d}", d, kunde, pos, leistung=d - timedelta(days=3), extra={"kd": kd}))
        return out

    def csv_zeilen(self, r):
        k = r.kunde
        return [[r.nr, f"{r.datum:%d.%m.%y}", f"{r.leistung:%d.%m.%y}", r.extra["kd"],
                 k["name"], k["strasse"], k["plz"], k["ort"], p.artnr, p.text,
                 menge_de(p.menge), p.einheit, de(p.preis), "19"] for p in r.pos]

    def zeichnen(self, r, pfad, nr=None, ib=None):
        b = Blatt(pfad, "Courier")
        z = []
        z.append(f"{'METALLBAU KESSLER GMBH':<46}R E C H N U N G")
        z.append("Ambossweg 9 * 58097 Hagen")
        z.append("-" * 74)
        k = r.kunde
        rechts = [f"Rechnung-Nr. ...: {nr or r.nr}", f"Datum ..........: {r.datum:%d.%m.%y}",
                  f"Lieferdatum ....: {r.leistung:%d.%m.%y}", f"Kunden-Nr. .....: {r.extra['kd']}"]
        links = ["Kunde:", k["name"], k["strasse"], f"{k['plz']} {k['ort']}"]
        for a, c in zip(links, rechts):
            z.append(f"{a:<40}{c}")
        z.append("-" * 74)
        z.append("")
        z.append(f"{'Pos':<5}{'Art.-Nr.':<10}{'Bezeichnung':<28}{'Menge':>7} {'ME':<4}{'Preis':>9}{'Betrag':>11}")
        z.append(f"{'---':<5}{'--------':<10}{'-' * 26:<28}{'-----':>7} {'--':<4}{'-------':>9}{'---------':>11}")
        for n, p in enumerate(r.pos, 1):
            z.append(f"{n:<5}{p.artnr:<10}{p.text:<28}{menge_de(p.menge):>7} {p.einheit:<4}{de(p.preis):>9}{de(p.betrag):>11}")
        z.append("=" * 74)
        z.append(f"{'':<42}{'Nettobetrag ....:':<20}{de(r.netto):>12}")
        z.append(f"{'':<42}{'MwSt 19 % ......:':<20}{de(r.ust):>12}")
        z.append(f"{'':<42}{'Gesamtbetrag ...:':<20}{de(r.brutto):>12}")
        z.append("")
        z.append("Zahlbar innerhalb 14 Tagen ohne Abzug.")
        for j, t_ in enumerate(z):
            b.t(40, 40 + j * 13, t_, 9, fett=(j == 0))
        b.linie(40, 772, 555, 0.5, strich=(3, 2))
        b.t(40, 778, "Metallbau Kessler GmbH * Ambossweg 9 * 58097 Hagen * AG Hagen HRB 990006", 7)
        b.t(40, 788, f"USt-IdNr. {self.ust} * St.-Nr. {self.stnr}", 7)
        b.t(40, 798, f"IBAN {iban_gruppiert(ib or self.iban)}", 7)
        b.fertig()


VERKAEUFER = [Baeckerei(), Elektro(), Gartenbau(), Musikschule(), Pixelwerk(), Metallbau()]


def main() -> None:
    for d in (EINGANG, FEHLER):
        d.mkdir(exist_ok=True)
        for alt in d.iterdir():
            alt.unlink()
    for v in VERKAEUFER:
        for r in v.rechnungen():
            v.csv_schreiben(r, EINGANG / f"{v.kurz}_{r.nr}.csv")
            v.zeichnen(r, EINGANG / f"{r.nr}.pdf")
            print(f"{r.nr:18} {v.name:28} netto {de(r.netto):>10}  USt {de(r.ust):>8}  brutto {de(r.brutto):>10}"
                  f"  {len(r.pos)} Pos.")
    fehlerfaelle()


def fehlerfaelle() -> None:
    """Absichtlich fehlerhafte Fälle (eigene Rechnungsnummern)."""
    # 1 Bäckerei: Preis in der CSV geändert -> Summen weichen vom Druck ab
    v = Baeckerei()
    r = v.rechnungen()[0]
    r.nr = "SK-2026-0499"
    v.zeichnen(r, FEHLER / f"{r.nr}.pdf")
    r.pos[0].preis += Decimal("0.20")
    v.csv_schreiben(r, FEHLER / f"baeckerei_{r.nr}.csv")
    # 2 Pixelwerk: Rechnungsdatum im Druck anders als in der CSV
    v = Pixelwerk()
    r = v.rechnungen()[1]
    r.nr = "PW-INV-2026-0199"
    v.zeichnen(r, FEHLER / f"{r.nr}.pdf", datum=r.datum + timedelta(days=1))
    v.csv_schreiben(r, FEHLER / f"pixelwerk_{r.nr}.csv")
    # 3 Gartenbau: andere Rechnungsnummer im Druck, gleicher Dateiname -> Zuordnung über den Dateinamen
    v = Gartenbau()
    r = v.rechnungen()[2]
    r.nr = "GL-2026-199"
    v.zeichnen(r, FEHLER / "gartenbau_GL-2026-199.pdf", nr="GL-2026-919")
    v.csv_schreiben(r, FEHLER / "gartenbau_GL-2026-199.csv")
    # 4 Musikschule: Leistungszeitraum fehlt in CSV und Druck (Pflichtangabe nach § 14 Abs. 4 Nr. 6 UStG)
    v = Musikschule()
    r = v.rechnungen()[3]
    r.nr = "KR-2026-099"
    v.zeichnen(r, FEHLER / f"{r.nr}.pdf", ohne_zeitraum=True)
    r.von = r.bis = None
    v.csv_schreiben(r, FEHLER / f"musikschule_{r.nr}.csv")
    # 5 Elektro: andere IBAN im Druck als im Profil
    v = Elektro()
    r = v.rechnungen()[4]
    r.nr = "EF-1099"
    v.zeichnen(r, FEHLER / f"{r.nr}.pdf", ib=iban("0009999999"))
    v.csv_schreiben(r, FEHLER / f"elektro_{r.nr}.csv")
    print("Fehlerfälle:", ", ".join(sorted(p.name for p in FEHLER.iterdir())))


if __name__ == "__main__":
    main()
