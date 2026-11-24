"""Gemeinsamer Rahmen für das Layout-Robustheits-Set ``beispiele/sets/layouts``.

Jede Familie (``fNN_<name>/familie.py``) beschreibt nur ihr Layout (Kopf, Tabelle, Summen, Fuß) und ihre
Belegvarianten; Daten, Rechnen, Seitenumbruch, Selbstcheck, Rücklesen und das Schreiben der Sollwerte macht
dieser Rahmen. Alle Inhalte sind erfunden: Domains ``*.example``, Bankleitzahl ``00000000``; USt-IdNr. und
IBAN tragen gültige Prüfziffern (geprüft mit ``fakturafalter.pflichtpruefung``), gehören aber niemandem.

Aufruf: ``.venv/bin/python beispiele/sets/layouts/erzeuge.py [fNN_name ...]``
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

SET = Path(__file__).resolve().parent
REPO = SET.parents[2]
sys.path.insert(0, str(REPO / "src"))
from fakturafalter.pflichtpruefung import iban_gueltig, ust_id_de_gueltig  # noqa: E402

A4 = (595.28, 841.89)
A5 = (419.53, 595.28)
CENT = Decimal("0.01")
SATZ = Decimal("19")                    # Regelsatz; F9/F10 mischen 7 und 19 % je Position (Pos.satz)
GRAU = Color(0.35, 0.35, 0.35)
HELLGRAU = Color(0.75, 0.75, 0.75)
SCHWARZ = black
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
VALIDIERUNG = "lokal nicht validierbar / spätere Phase (KoSIT/veraPDF prüfen die App-Ausgabe, nicht diese PDFs)"
KORREKTUREN = "erst beim echten Anlernen messbar"


# ------------------------------------------------------------------ Zahlen und Daten
def cent(d) -> Decimal:
    return Decimal(d).quantize(CENT, rounding=ROUND_HALF_UP)


def zahl(d, stellen: int = 2, tausender: bool = True) -> str:
    """Deutsche Schreibweise: 1.234,56 (``tausender=False``: 1234,56)."""
    s = f"{Decimal(d):,.{stellen}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", "." if tausender else "")
    return s


def menge(q: Decimal, stellen: int | None = None) -> str:
    """Menge ohne Nachkommastellen, wenn ganzzahlig (``stellen`` erzwingt eine feste Zahl)."""
    if stellen is not None:
        return zahl(q, stellen)
    return zahl(q, 0) if q == q.to_integral() else zahl(q.normalize(), max(1, -q.normalize().as_tuple().exponent))


def de(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def de_kurz(d: date) -> str:
    return d.strftime("%d.%m.%y")


def de_lang(d: date) -> str:
    return f"{d.day}. {MONATE[d.month - 1]} {d.year}"


def werktag(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ------------------------------------------------------------------ Prüfziffern (erfunden, aber gültig)
def ust_id_de(acht: str) -> str:
    """DE + 8 Ziffern + Prüfziffer ISO 7064 MOD 11,10."""
    produkt = 10
    for z in acht:
        summe = (int(z) + produkt) % 10 or 10
        produkt = (2 * summe) % 11
    pz = 11 - produkt
    u = f"DE{acht}{0 if pz == 10 else pz}"
    assert ust_id_de_gueltig(u), u
    return u


def iban_de(konto: str, blz: str = "00000000") -> str:
    bban = blz + konto.zfill(10)
    pz = 98 - int("".join(str(int(c, 36)) for c in bban + "DE00")) % 97
    i = f"DE{pz:02d}{bban}"
    assert iban_gueltig(i), i
    return " ".join(i[k:k + 4] for k in range(0, len(i), 4))


@dataclass
class Absender:
    name: str
    strasse: str
    plz: str
    ort: str
    ust_id: str
    iban: str
    bic: str
    bank: str
    email: str
    web: str
    telefon: str
    register: str
    gf: str

    def __post_init__(self):
        assert ust_id_de_gueltig(self.ust_id) and iban_gueltig(self.iban), self.name
        assert self.email.endswith(".example") and self.web.endswith(".example"), self.name

    def soll(self) -> dict:
        return {"name": self.name, "street": self.strasse, "postal_code": self.plz, "city": self.ort,
                "ust_id": self.ust_id, "iban": self.iban, "bic": self.bic, "bank": self.bank, "email": self.email,
                "register": self.register, "ceo": self.gf}


# ------------------------------------------------------------------ Kunden (erfunden, nur Inland)
@dataclass(frozen=True)
class Kunde:
    namen: tuple[str, ...]
    strasse: str            # Straße oder „Postfach 12 34 56“ (nur ein Hold-out-Beleg im ganzen Set)
    plz: str
    ort: str
    nummer: str


KUNDEN = [
    Kunde(("Habicht Gebäudetechnik GmbH",), "Ostring 14", "44787", "Bochum", "10231"),
    Kunde(("Stadtwerke Beispielstadt", "Abteilung Netzbetrieb"), "Kraftwerkstraße 2", "06844", "Dessau-Roßlau",
          "20417"),
    Kunde(("Klinikum am Ziegelberg gGmbH", "Technischer Einkauf", "z. Hd. Frau Yilmaz"), "Ziegelbergweg 60",
          "97074", "Würzburg", "30088"),
    Kunde(("Brauerei Kesselring", "GmbH & Co. KG"), "Am Hopfengarten 3", "95444", "Bayreuth", "10587"),
    Kunde(("Weißenfels Kältetechnik e. K.",), "Hauptstraße 117b", "06667", "Weißenfels", "41120"),
    Kunde(("Wohnbau Nordheide eG", "z. Hd. Herrn Kowalczyk"), "Lüneburger Straße 9", "21244",
          "Buchholz in der Nordheide", "20963"),
    Kunde(("Rösner Metallbau GmbH",), "Industriegebiet Süd 5", "36037", "Fulda", "10044"),
    Kunde(("Gemeinde Obertal", "Bauamt"), "Rathausplatz 1", "79874", "Breitnau", "50012"),
    Kunde(("Ehrlich & Partner", "Steuerberatungsgesellschaft mbH"), "Königsallee 8", "40212", "Düsseldorf", "K-7713"),
    Kunde(("Fahrradhaus Lindemann",), "Bahnhofstraße 22", "86899", "Landsberg am Lech", "100734"),
    Kunde(("Zweirad Schuster OHG", "Werkstatt"), "Mühlenweg 4", "24103", "Kiel", "100892"),
    Kunde(("Velo-Kontor Hamburg GmbH", "Wareneingang", "z. Hd. Herrn Petersen"), "Billstraße 140", "20539",
          "Hamburg", "101215"),
    Kunde(("Radsport Ellwanger",), "Marktplatz 7", "73479", "Ellwangen (Jagst)", "101377"),
    Kunde(("Pedalwerk Leipzig UG (haftungsbeschränkt)",), "Karl-Heine-Straße 93", "04229", "Leipzig", "101502"),
    Kunde(("Architekturbüro Sandvoss",), "Lindenstraße 31", "49074", "Osnabrück", "2026-118"),
    Kunde(("Hotel Seeblick Inh. M. Grüner", "Verwaltung"), "Uferpromenade 12", "88131", "Lindau (Bodensee)",
          "2026-121"),
    Kunde(("Kreisverwaltung Musterkreis", "Fachbereich Hochbau", "z. Hd. Frau Dr. Albers"), "Schlossplatz 3",
          "55469", "Simmern/Hunsrück", "2026-097"),
    Kunde(("Bäckerei Ohlendorf GmbH",), "Brückenstraße 5", "37083", "Göttingen", "2026-130"),
    # ab hier Phase 2 (F4–F10)
    Kunde(("Praxis für Physiotherapie", "Annika Vogelsang"), "Am Stadtgraben 11", "34117", "Kassel", "K10045"),  # 18
    Kunde(("Weingut Hohenrain GbR",), "Rheinstraße 70", "65375", "Oestrich-Winkel", "K10077"),
    Kunde(("Kita Sonnenblume e. V.", "Vorstand", "z. Hd. Frau Brückner"), "Gartenweg 2", "34246", "Vellmar",
          "K10112"),
    Kunde(("Copyshop Altstadt OHG",), "Pfarrgasse 4", "93047", "Regensburg", "4711"),                 # 21
    Kunde(("Steuerkanzlei Rademacher", "Partnerschaft mbB"), "Theaterstraße 15", "30159", "Hannover", "4788"),
    Kunde(("Landratsamt Musterhausen", "Sachgebiet IT"), "Bahnhofplatz 2", "84028", "Landshut", "4802"),
    Kunde(("Hofladen Brinkmann",), "Dorfstraße 23", "48291", "Telgte", "D-20031"),                    # 24
    Kunde(("Gasthaus Zur Linde", "Inh. Peter Hausmann"), "Lindenplatz 1", "79100", "Freiburg im Breisgau",
          "D-20042"),
    Kunde(("Ladenbau Schwarzwald GmbH", "Einkauf", "z. Hd. Herrn Faller"), "Gewerbestraße 30", "78112",
          "St. Georgen im Schwarzwald", "D-20058"),
    Kunde(("Agentur Lichtblick GmbH",), "Friedrichstraße 133", "10117", "Berlin", "C00318"),           # 27
    Kunde(("Zahnarztpraxis Dr. Okafor", "z. Hd. Praxismanagement"), "Marktstraße 8", "33602", "Bielefeld",
          "C00322"),
    Kunde(("Spedition Albrecht GmbH",), "Postfach 12 34 56", "28001", "Bremen", "30215"),             # 29 Postfach
    Kunde(("Elektro Wittkowski GmbH & Co. KG", "Kreditorenbuchhaltung"), "Hafenstraße 41", "26725", "Emden",
          "30227"),
    Kunde(("Kunsthandwerk Ilse Marbach",), "Kirchgasse 9", "07743", "Jena", "30240"),
    Kunde(("Feinkost Albers KG", "Filiale Eppendorf", "z. Hd. Herrn Albers"), "Eppendorfer Weg 201", "20253",
          "Hamburg", "30252"),                                                                         # 32
    Kunde(("Stadtbibliothek Neustadt",), "Schulstraße 1", "67433", "Neustadt an der Weinstraße", "7001"),
    Kunde(("Café Morgenrot",), "Am Markt 3", "17489", "Greifswald", "7012"),
    Kunde(("Buchhandlung Seitenweise", "Inh. Jana Roth"), "Hauptstraße 52", "69117", "Heidelberg", "7020"),  # 35
    Kunde(("Gesamtschule am Mühlbach", "Schulsekretariat", "z. Hd. Herrn Demir"), "Mühlbachweg 10", "53111",
          "Bonn", "7033"),
]


# ------------------------------------------------------------------ Positionen
@dataclass
class Pos:
    qty: Decimal
    unit: str                    # Schlüssel im Soll: „Stk.“ | „Std.“ (benchmark FIKTIV_EINHEITEN)
    beschreibung: list[str]      # gedruckte Zeilen; nie über einen Seitenwechsel
    preis: Decimal
    artnr: str = ""
    kind: str = "regular"        # regular | shipping (Versand als normale Position)
    satz: Decimal = SATZ         # USt-Satz der Position (7 oder 19; gemischt nur in F9/F10)
    gesamt_druck: Decimal | None = None   # nur Fehlerart „zeile“: gedruckter (falscher) Betrag

    @property
    def gesamt(self) -> Decimal:
        return self.gesamt_druck if self.gesamt_druck is not None else cent(self.qty * self.preis)

    @property
    def gesamt_berechnet(self) -> Decimal:
        return cent(self.qty * self.preis)


@dataclass
class Artikel:
    artnr: str
    bez: str
    preise: tuple[float, float]
    unit: str = "Stk."
    mengen: tuple = (1, 2, 3, 4, 5, 6, 10, 12, 20)
    satz: int = 19


def preis_zufall(rng: random.Random, spanne) -> Decimal:
    lo, hi = spanne
    p = Decimal(str(round(rng.uniform(lo, hi), 2)))
    if p >= 20:
        p = (p * 4).quantize(Decimal(1)) / 4
    return cent(p)


def umbrechen(text: str, breite: float, schrift: str, groesse: float) -> list[str]:
    zeilen, akt = [], ""
    for w in text.split():
        probe = (akt + " " + w).strip()
        if pdfmetrics.stringWidth(probe, schrift, groesse) <= breite or not akt:
            akt = probe
        else:
            zeilen.append(akt)
            akt = w
    zeilen.append(akt)
    return zeilen


def positionen(rng: random.Random, katalog: list[Artikel], anzahl: int, lang: int, langtexte: list[str],
               breite: float, schrift: str, groesse: float, versand: tuple[str, str, str] | None = None,
               max_zeilen: int = 4) -> list[Pos]:
    """``anzahl`` Positionen aus dem Katalog (ohne Wiederholung, solange möglich); ``lang`` davon mit
    umbrechendem Zusatztext (höchstens ``max_zeilen`` Zeilen); ``versand`` = (Art-Nr, Text, Preis) als letzte
    normale Position mit Menge 1."""
    pool = list(katalog)
    rng.shuffle(pool)
    lang_bei = set(rng.sample(range(anzahl), min(lang, anzahl)))
    out, preise = [], {}
    for i in range(anzahl):
        a = pool[i % len(pool)]
        q = Decimal(rng.choice(a.mengen))
        if a.bez not in preise:              # gleicher Artikel, gleicher Preis innerhalb eines Belegs
            preise[a.bez] = preis_zufall(rng, a.preise)
        text = a.bez
        if i in lang_bei:
            text += ", " + rng.choice(langtexte)
        zeilen = umbrechen(text, breite, schrift, groesse)[:max_zeilen]
        out.append(Pos(q, a.unit, zeilen, preise[a.bez], a.artnr, satz=Decimal(a.satz)))
    if versand:
        out.append(Pos(Decimal(1), "Stk.", [versand[1]], Decimal(versand[2]), versand[0], "shipping"))
    return out


# ------------------------------------------------------------------ Seitenplan (Zeileneinheiten)
@dataclass
class Seite:
    nr: int
    pos: list[int]
    vortrag: Decimal | None      # Übertrag oben auf der Folgeseite
    uebertrag: Decimal | None    # Übertrag/Zwischensumme unten
    summen: bool


def seitenplan(ps: list[Pos], hoehe, erste: int, folge: int, summen: int, vortrag: bool = True) -> list[Seite]:
    """Positionen auf Seiten verteilen (``hoehe(p)`` = Zeileneinheiten einer Position einschließlich Abstand).
    Seite 1 fasst ``erste``, Folgeseiten ``folge`` Einheiten. Unten auf einer nicht letzten Seite steht eine
    Übertragszeile (1 Einheit), oben auf Folgeseiten ein Vortrag (1 Einheit, wenn ``vortrag``); die letzte Seite
    braucht ``summen`` Einheiten für den Summenblock. Eine Bezeichnung endet immer vor dem Seitenwechsel."""
    seiten, i, kum, nr = [], 0, Decimal(0), 1
    while True:
        platz = erste if nr == 1 else folge
        vt = kum if (nr > 1 and vortrag) else None
        start = 1 if vt is not None else 0
        rest = sum(hoehe(p) for p in ps[i:])
        if start + rest + summen <= platz:
            seiten.append(Seite(nr, list(range(i, len(ps))), vt, None, True))
            return seiten
        idx, z = [], start
        while i < len(ps) and z + hoehe(ps[i]) <= platz - 1:
            z += hoehe(ps[i])
            kum += ps[i].gesamt
            idx.append(i)
            i += 1
        if i == len(ps):                       # alles passt, nur die Summen nicht: letzte Position weiter
            i -= 1
            idx.pop()
            kum -= ps[i].gesamt
        assert idx, "Seite ohne Position"
        seiten.append(Seite(nr, idx, vt, cent(kum), False))
        nr += 1


# ------------------------------------------------------------------ Zeichnen
class Blatt:
    """Dünne Hülle um den reportlab-Canvas; ``y`` ist die Grundlinie, gemessen von OBEN."""

    def __init__(self, c: canvas.Canvas, hoehe: float):
        self.c, self.h = c, hoehe

    def text(self, x, y, s, schrift="Helvetica", groesse=9.0, farbe=SCHWARZ, art="l"):
        c = self.c
        c.setFont(schrift, groesse)
        c.setFillColor(farbe)
        if art == "r":
            c.drawRightString(x, self.h - y, s)
        elif art == "m":
            c.drawCentredString(x, self.h - y, s)
        else:
            c.drawString(x, self.h - y, s)

    def linie(self, x0, y, x1, breite=0.5, farbe=SCHWARZ):
        self.c.setStrokeColor(farbe)
        self.c.setLineWidth(breite)
        self.c.line(x0, self.h - y, x1, self.h - y)

    def kasten(self, x0, y0, x1, y1, breite=0.6, farbe=SCHWARZ, fuellung=None):
        c = self.c
        c.setStrokeColor(farbe)
        c.setLineWidth(breite)
        if fuellung is not None:
            c.setFillColor(fuellung)
        c.rect(x0, self.h - y1, x1 - x0, y1 - y0, stroke=1, fill=fuellung is not None)


def leinwand(pfad: Path, format_, titel: str, autor: str) -> canvas.Canvas:
    c = canvas.Canvas(str(pfad), pagesize=format_, invariant=1, pageCompression=1)
    c.setTitle(titel)
    c.setAuthor(f"{autor} – fiktiver Rechnungssteller")
    c.setSubject("Fiktive Testrechnung (Layout-Robustheit) für Fakturafalter; keine echte Forderung")
    c.setCreator("beispiele/sets/layouts/erzeuge.py")
    return c


def logo_png(kuerzel: str, breite=360, hoehe=120, farbe=(40, 70, 110)) -> io.BytesIO:
    """Deterministisches Logo-Bild (nur Kürzel und Balken, kein Pflichtwert)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (breite, hoehe), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, hoehe - 1, hoehe - 1], fill=farbe)
    f = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", int(hoehe * 0.45))
    d.text((hoehe / 2, hoehe / 2), kuerzel, font=f, fill=(255, 255, 255), anchor="mm")
    for k in range(4):
        d.rectangle([hoehe + 20, 20 + k * 24, breite - 10 - k * 40, 32 + k * 24], fill=farbe)
    b = io.BytesIO()
    img.save(b, format="PNG", optimize=False)
    b.seek(0)
    return b


# ------------------------------------------------------------------ Beleg (Soll)
@dataclass
class Spez:
    kunde: int
    anzahl: int = 4                  # Positionen (ohne Versand)
    lang: int = 0                    # davon mit mehrzeiliger Bezeichnung
    zahlung: str = "netto"           # netto | skonto | fest (je Familie formuliert)
    skonto: int | None = None
    skonto_tage: int = 10
    ziel: int = 30                   # Zahlungsziel in Tagen
    versand: bool = False
    bestellung: bool = True
    holdout: bool = False
    pruefen: str | None = None       # None | "netto" (Σ Positionen ≠ Netto) | "brutto" (Netto + USt ≠ Brutto)
    #                                  | "ust" (gedruckte USt ≠ Netto × Satz, Brutto = Netto + gedruckte USt)
    #                                  | "ohne_leistungsdatum" (Pflichtangabe BT-72 fehlt im Druck)
    seiten: int = 1
    format: str = "A4"
    notiz: str = ""
    extra: dict = field(default_factory=dict)
    fehler: str | None = None        # A1: absichtlicher Fehler (nur Hold-out), Schlüssel aus FEHLERARTEN
    falle: str | None = None         # A1: Ablenker für False Positives (nur Hold-out), Schlüssel aus FALLEN
    falle_detail: dict = field(default_factory=dict)   # gedruckte Ablenker-Werte (Familie zeichnet sie)


# ------------------------------------------------------------------ A1 (20.11.2026): Fehler- und Fallenbelege
FEHLERARTEN = {
    "summe_positionen": "Σ Positionen ≠ gedrucktes Netto: die letzte Position (Versand) ist nicht mitsummiert; "
                        "USt und Brutto sind aus dem gedruckten Netto richtig weitergerechnet",
    "zeile": "Menge × Preis ≠ gedruckter Betrag einer Position (Zahlendreher); Netto, USt und Brutto sind aus den "
             "gedruckten Beträgen richtig weitergerechnet",
    "netto_brutto": "gedrucktes Brutto ≠ Netto + USt (Zahlendreher im Endbetrag); Netto und USt richtig",
    "iban_pruefziffer": "IBAN des Verkäufers mit vertauschten Prüfziffern (MOD 97 ungültig); sonst alles richtig",
    "ust_id_pruefziffer": "USt-IdNr. des Verkäufers mit falscher Prüfziffer (ISO 7064 MOD 11,10); sonst alles richtig",
    "rechnungsnummer_fehlt": "Rechnungsnummer nicht gedruckt (Feld leer); sonst alles richtig",
    "rechnungsdatum_fehlt": "Rechnungsdatum nicht gedruckt (Feld leer, Lieferdatum vorhanden); sonst alles richtig",
    "faelligkeit_vor_datum": "Fälligkeitsdatum = Rechnungsdatum − Zahlungsziel, liegt vor dem Rechnungsdatum "
                             "(Vorzeichenfehler); sonst alles richtig",
}
FALLEN = {
    "angebot_nr": "zusätzliche Zeile „Angebots-Nr.“ mit ähnlichem Nummernformat direkt unter der Rechnungs-Nr.",
    "zweites_datum": "zusätzliches „Auftragsdatum“ direkt über dem Rechnungsdatum (früheres Datum)",
    "nummer_aehnlich": "zusätzliche „Projektnr.“ im gleichen sechsstelligen Format wie die Rechnungsnummer",
}


def _dreher(betrag: Decimal) -> Decimal:
    """Zahlendreher: erste zwei benachbarte, verschiedene Ziffern tauschen (ohne führende Null)."""
    z = list(f"{betrag:.2f}".replace(".", ""))
    j = next(j for j in range(len(z) - 1) if z[j] != z[j + 1] and (j or z[1] != "0"))
    z[j], z[j + 1] = z[j + 1], z[j]
    return Decimal("".join(z)) / 100


def _falsche_pruefziffer_iban(iban: str) -> str:
    i = iban[:2] + iban[3] + iban[2] + iban[4:]
    assert not iban_gueltig(i), i
    return i


def _falsche_pruefziffer_ust_id(u: str) -> str:
    f = u[:-1] + str((int(u[-1]) + 3) % 10)
    assert not ust_id_de_gueltig(f), f
    return f


@dataclass
class Familie:
    nr: int
    ordner: str
    titel: str
    absender: Absender
    quelle: str                      # Schlüssel in QUELLEN.md
    seed: int
    schrift: str
    spez: list[Spez]
    nummer: callable                 # (n, rng, datum) -> Rechnungsnummer
    bestellnr: callable              # (rng) -> Bestellnummer
    zahlungstext: callable           # (spez, datum, brutto, faellig, sk_datum, sk_betrag) -> [Zeilen]
    pos_erzeugen: callable           # (rng, spez) -> [Pos]
    plan: callable                   # (ps, spez) -> [Seite]
    zeichnen: callable               # (pfad, d, ps, seiten, spez)
    datum_druck: callable = de       # gedruckte Form des Rechnungsdatums
    datum_format: str = "TT.MM.JJJJ"
    kundennummer_gedruckt: bool = True   # False: Vorlage druckt keine Kundennummer -> Soll ""
    datum0: date = date(2026, 10, 5)
    leistung_tage: tuple = (0, 1, 2, 3, 6)   # Abstand Leistungsdatum → Rechnungsdatum (zufällig gewählt)


def beleg(f: Familie, n: int, s: Spez, rng: random.Random, datum: date) -> tuple[dict, list[Pos], list[Seite]]:
    k = KUNDEN[s.kunde]
    ps = f.pos_erzeugen(rng, s)
    detail = {}
    if s.fehler == "zeile":
        i = rng.choice([i for i, p in enumerate(ps) if p.kind == "regular" and p.gesamt >= 10])
        ps[i].gesamt_druck = _dreher(ps[i].gesamt)
        detail = {"position": i + 1, "gedruckt": f"{ps[i].gesamt:.2f}", "berechnet": f"{ps[i].gesamt_berechnet:.2f}"}
    seiten = f.plan(ps, s)
    netto = sum(p.gesamt for p in ps)
    saetze = sorted({p.satz for p in ps})
    aufteilung = [(r, sum(p.gesamt for p in ps if p.satz == r)) for r in saetze]
    aufteilung = [(r, n_, cent(n_ * r / 100)) for r, n_ in aufteilung]      # USt je Satz gerundet (EN 16931 BG-23)
    ust = sum(v for _, _, v in aufteilung)
    brutto = netto + ust
    gedruckt = {"net": netto, "vat": ust, "gross": brutto}
    hinweise = []
    if s.pruefen == "netto":                     # gedrucktes Netto weicht von Σ Positionen ab
        gedruckt["net"] = netto + Decimal("10.00")       # USt und Brutto bleiben richtig gedruckt
        hinweise = ["PRUEFEN [BT-109] Kontrollwert der Quelle ≠ berechnet (gedrucktes Netto 10,00 € über Σ Positionen)"]
    elif s.pruefen == "brutto":                  # gedrucktes Brutto ≠ Netto + USt
        gedruckt["gross"] = brutto + Decimal("1.00")
        hinweise = ["PRUEFEN [BT-112] Kontrollwert der Quelle ≠ berechnet (gedrucktes Brutto 1,00 € über Netto + USt)"]
    elif s.pruefen == "ust":                     # gedruckte USt ≠ Netto × Satz; Brutto folgt der falschen USt
        gedruckt["vat"] = ust + Decimal("0.10")
        gedruckt["gross"] = netto + gedruckt["vat"]
        hinweise = ["PRUEFEN [BT-110] Kontrollwert der Quelle ≠ berechnet (gedruckte USt 0,10 € über Netto × Satz, "
                    "Brutto folgt der gedruckten USt)"]
    elif s.pruefen == "ohne_leistungsdatum":     # Pflichtangabe fehlt; Summen stimmen
        hinweise = ["PRUEFEN [BT-72] Leistungsdatum fehlt (Pflichtangabe nach § 14 Abs. 4 Nr. 6 UStG; "
                    "kein Liefer- oder Leistungsdatum und kein Hinweis „Rechnungsdatum = Leistungsdatum“ gedruckt)"]
    else:
        assert s.pruefen is None, s.pruefen
    if s.fehler == "summe_positionen":           # letzte Position nicht summiert, Rest folgerichtig
        assert ps[-1].kind == "shipping"
        gedruckt["net"] = netto - ps[-1].gesamt
        gedruckt["vat"] = cent(gedruckt["net"] * SATZ / 100)
        gedruckt["gross"] = gedruckt["net"] + gedruckt["vat"]
    elif s.fehler == "netto_brutto":
        gedruckt["gross"] = _dreher(brutto)
    leistung = datum - timedelta(days=rng.choice(list(f.leistung_tage)))
    ohne_leistung = s.pruefen == "ohne_leistungsdatum"
    if s.zahlung == "skonto":
        sk_datum = datum + timedelta(days=s.skonto_tage)
        sk_betrag = cent(gedruckt["gross"] * s.skonto / 100)
    else:
        sk_datum = sk_betrag = None
    faellig = datum + timedelta(days=s.ziel)
    if s.fehler == "faelligkeit_vor_datum":
        faellig = datum - timedelta(days=s.ziel)
    text = f.zahlungstext(s, datum, gedruckt["gross"], faellig, sk_datum, sk_betrag)
    nummer = f.nummer(n, rng, datum)
    datei_nr = re.sub(r'[^A-Za-z0-9-]', '-', nummer)
    if s.fehler == "rechnungsnummer_fehlt":
        nummer, datei_nr = "", "ohne-Nummer"
    d = {
        "datei": f"Rechnung_{n:03d}_{datei_nr}.pdf",
        "format": f"PDF 1.4 (reportlab), {s.format}, Schrift {f.schrift} (Standard-14, nicht eingebettet)",
        "familie": f.ordner,
        "quelle": f.quelle,
        "holdout": s.holdout,
        "split": "holdout" if s.holdout else "training",
        "seller": f.absender.soll(),
        "buyer": {"name_lines": list(k.namen), "street": k.strasse, "postal_code": k.plz, "city": k.ort,
                  "customer_number": k.nummer if f.kundennummer_gedruckt else ""},
        "invoice": {"number": nummer, "date": de(datum), "service_date": "" if ohne_leistung else de(leistung),
                    "order_number": f.bestellnr(rng) if s.bestellung else "", "shipping": ""},
        "druck": {"datum_format": f.datum_format, "schrift": f.schrift, "seitenformat": s.format},
        "BT-72": None if ohne_leistung else de(leistung),
        "BT-119": "19.00",
        "positions": [{"qty": format(p.qty.normalize(), "f"), "unit": p.unit, "description": p.beschreibung,
                       "article_number": p.artnr, "unit_price": f"{p.preis:.2f}", "kind": p.kind,
                       "price_unit": None, "price_unit_qty": 1, "total": f"{p.gesamt:.2f}"} for p in ps],
        "vat_rate": "19.00",
        "discount_percent": f"{s.skonto:.2f}" if s.zahlung == "skonto" else None,
        "discount_days": s.skonto_tage if s.zahlung == "skonto" else None,
        "payment_days": s.ziel,
        "totals": {"net": f"{netto:.2f}", "vat": f"{ust:.2f}", "gross": f"{brutto:.2f}"},
        "totals_printed": {k2: f"{v:.2f}" for k2, v in gedruckt.items()},
        "payment": {"discount_date": de(sk_datum) if sk_datum else None, "due_date": de(faellig),
                    "discount_amount": f"{sk_betrag:.2f}" if sk_betrag is not None else None,
                    "discount_base": "gross" if sk_datum else None},
        "payment_terms_text": text,
        "page_count": len(seiten),
        "pages": [{"page": se.nr, "position_indices": [i + 1 for i in se.pos],
                   "transfer": None if se.uebertrag is None else f"{se.uebertrag:.2f}",
                   "carry_forward": None if se.vortrag is None else f"{se.vortrag:.2f}",
                   "summary_present": se.summen} for se in seiten],
        "erwarteter_status": "prüfen" if s.pruefen else "ok",
        "erwartete_hinweise": hinweise,
        "kosit": None, "verapdf": None, "validierung_hinweis": VALIDIERUNG,
        "korrekturen": None, "korrekturen_hinweis": KORREKTUREN,
        "test_flags": {"address_name_lines": len(k.namen), "po_box": k.strasse.startswith("Postfach"),
                       "multi_line_positions": sum(len(p.beschreibung) > 1 for p in ps),
                       "shipping_position": any(p.kind == "shipping" for p in ps),
                       "page_format": s.format, "payment": s.zahlung, "pruefen": s.pruefen,
                       "missing_order_number": not s.bestellung, "note": s.notiz, **s.extra},
    }
    if len(saetze) > 1:                          # gemischte Sätze (F9/F10): Satz je Position und Aufteilung
        d["BT-119"] = [f"{r:.2f}" for r in saetze]
        d["vat_rate_hinweis"] = ("vat_rate bleibt 19.00 für tools/benchmark.py (kennt nur einen Satz); "
                                 "maßgeblich sind BT-119 und vat_breakdown")
        for pj, p in zip(d["positions"], ps):
            pj["vat_rate"] = f"{p.satz:.2f}"
        d["vat_breakdown"] = [{"rate": f"{r:.2f}", "net": f"{n_:.2f}", "vat": f"{v:.2f}"} for r, n_, v in aufteilung]
    if f.datum_druck(datum) != de(datum):
        d["invoice"]["date_printed"] = f.datum_druck(datum)
    if s.fehler or s.falle:
        a1_zusatz(d, ps, s, netto, ust, brutto, datum, faellig, detail)
    return d, ps, seiten


def a1_zusatz(d: dict, ps: list, s: Spez, netto, ust, brutto, datum: date, faellig: date, detail: dict):
    """Soll-Felder der A1-Hold-out-Belege. ``totals`` = gedruckte Werte (wie ``totals_printed``), die
    rechnerisch richtigen stehen in ``totals_berechnet``. Seller/Rechnungskopf enthalten, was gedruckt ist."""
    tp = d["totals_printed"]
    hinweise, folge = [], []
    if s.fehler == "summe_positionen":
        hinweise = [f"PRUEFEN [BT-109] Kontrollwert der Quelle ≠ berechnet (gedrucktes Netto {zahl(tp['net'])} €, "
                    f"Σ Positionen {zahl(netto)} €)"]
        folge = ["PRUEFEN [BT-110] / [BT-112] Kontrollwert der Quelle ≠ berechnet (USt und Brutto folgen dem "
                 "gedruckten Netto)"]
        detail = {"nicht_summiert": f"Pos {len(ps)} ({ps[-1].beschreibung[0]}, {zahl(ps[-1].gesamt)} €)"}
    elif s.fehler == "zeile":
        hinweise = [f"PRUEFEN [BT-131] Pos {detail['position']}: Menge × Preis = "
                    f"{zahl(Decimal(detail['berechnet']))} €, gedruckt {zahl(Decimal(detail['gedruckt']))} €"]
        folge = ["PRUEFEN [BT-109] Kontrollwert der Quelle ≠ berechnet (gedrucktes Netto enthält den falschen "
                 "Zeilenbetrag)"]
    elif s.fehler == "netto_brutto":
        hinweise = [f"PRUEFEN [BT-112] Kontrollwert der Quelle ≠ berechnet (gedrucktes Brutto {zahl(tp['gross'])} €, "
                    f"Netto + USt = {zahl(brutto)} €)"]
        detail = {"gedruckt": tp["gross"], "berechnet": f"{brutto:.2f}"}
    elif s.fehler == "iban_pruefziffer":
        hinweise = [f"FEHLER [BT-84] IBAN (BT-84) „{d['seller']['iban']}“ ist ungültig (Prüfsumme oder Länge "
                    "stimmt nicht)."]
    elif s.fehler == "ust_id_pruefziffer":
        hinweise = [f"FEHLER [BT-31] Verkäufer – USt-IdNr. (BT-31) „{d['seller']['ust_id']}“ ist ungültig "
                    "(Aufbau DE + 9 Ziffern, Prüfziffer nach BZSt stimmt nicht)."]
    elif s.fehler == "rechnungsnummer_fehlt":
        hinweise = ["FEHLER [BT-1] Rechnungsnummer (BT-1) fehlt. Pflichtangabe nach § 14 Abs. 4 Nr. 4 UStG."]
    elif s.fehler == "rechnungsdatum_fehlt":
        hinweise = ["FEHLER [BT-2] Rechnungsdatum (BT-2) fehlt. Pflichtangabe nach § 14 Abs. 4 Nr. 3 UStG."]
        detail = {"nicht_gedruckt": de(datum), "hinweis": "Zahl- und Skontodaten im Soll aus dem nicht gedruckten "
                                                          "Datum berechnet"}
        d["invoice"]["date"] = ""
        d["invoice"].pop("date_printed", None)
    elif s.fehler == "faelligkeit_vor_datum":
        hinweise = [f"FEHLER [BT-9] Fälligkeitsdatum (BT-9) {de(faellig)} liegt vor dem Rechnungsdatum."]
        detail = {"faellig_gedruckt": de(faellig), "rechnungsdatum": de(datum)}
    if s.falle == "zweites_datum":               # früheres Auftragsdatum direkt über dem Rechnungsdatum
        detail = {"auftragsdatum": de(datum - timedelta(days=12))}
    elif s.falle:
        detail = dict(s.falle_detail)
    d["totals"] = dict(tp)
    d.update({
        "rolle": "holdout-fehler" if s.fehler else "holdout-falle",
        "erwarteter_status": "fehler" if s.fehler else "ok",
        "erwartete_hinweise": hinweise,
        "moegliche_folgehinweise": folge,
        "fehlerart": s.fehler,
        "fehler_beschreibung": FEHLERARTEN.get(s.fehler),
        "falle": s.falle,
        "falle_beschreibung": FALLEN.get(s.falle),
        "fehler_detail" if s.fehler else "falle_detail": detail,
        "totals_berechnet": {"net": f"{netto:.2f}", "vat": f"{ust:.2f}", "gross": f"{brutto:.2f}"},
    })
    if s.fehler == "zeile":
        r = sum(p.gesamt_berechnet for p in ps)
        d["totals_berechnet"] = {"net": f"{r:.2f}", "vat": f"{cent(r * SATZ / 100):.2f}",
                                 "gross": f"{r + cent(r * SATZ / 100):.2f}"}


def selbstcheck(d: dict, ps: list[Pos], seiten: list[Seite], s: Spez):
    if s.fehler or s.falle:
        return selbstcheck_a1(d, ps, seiten, s)
    nr = d["invoice"]["number"]
    netto, ust, brutto = (Decimal(d["totals"][k]) for k in ("net", "vat", "gross"))
    for p in ps:
        assert p.qty > 0 and p.preis > 0 and p.gesamt == cent(p.qty * p.preis), nr
        assert p.unit in ("Stk.", "Std."), (nr, p.unit)
    assert sum(p.gesamt for p in ps) == netto, f"{nr}: Σ Positionen ≠ Netto"
    saetze = sorted({p.satz for p in ps})
    assert all(r in (Decimal(7), Decimal(19)) for r in saetze), nr
    if len(saetze) == 1:
        assert cent(netto * saetze[0] / 100) == ust and "vat_breakdown" not in d, nr
    else:                                        # USt je Satz: Σ Positionen je Satz, gerundet je Satz
        auf = d["vat_breakdown"]
        assert [Decimal(a["rate"]) for a in auf] == saetze == [Decimal(r) for r in d["BT-119"]], nr
        for a in auf:
            r = Decimal(a["rate"])
            n_ = sum(p.gesamt for p in ps if p.satz == r)
            assert Decimal(a["net"]) == n_ and Decimal(a["vat"]) == cent(n_ * r / 100), f"{nr}: Satz {r}"
            assert [pj["vat_rate"] for pj in d["positions"]] == [f"{p.satz:.2f}" for p in ps], nr
        assert sum(Decimal(a["net"]) for a in auf) == netto, nr
        assert sum(Decimal(a["vat"]) for a in auf) == ust, f"{nr}: Σ USt je Satz ≠ USt"
    assert netto + ust == brutto, f"{nr}: Netto + USt ≠ Brutto"
    g = {k: Decimal(v) for k, v in d["totals_printed"].items()}
    if s.pruefen in (None, "ohne_leistungsdatum"):
        assert g == {"net": netto, "vat": ust, "gross": brutto}, nr
    elif s.pruefen == "netto":
        assert g["net"] != netto and g["vat"] == ust and g["gross"] == brutto, nr
    elif s.pruefen == "ust":
        assert g["net"] == netto and g["vat"] != ust and g["gross"] == g["net"] + g["vat"] != brutto, nr
    else:
        assert g["net"] == netto and g["vat"] == ust and g["gross"] != brutto, nr
    if s.pruefen == "ohne_leistungsdatum":
        assert d["BT-72"] is None and d["invoice"]["service_date"] == "", nr
    else:
        assert d["BT-72"] == d["invoice"]["service_date"] != "", nr
    if d["payment"]["discount_amount"]:
        assert Decimal(d["payment"]["discount_amount"]) == cent(g["gross"] * s.skonto / 100), nr
    assert len(seiten) == s.seiten, f"{nr}: {len(seiten)} Seiten statt {s.seiten}"
    assert [i for se in seiten for i in se.pos] == list(range(len(ps))), nr
    kum = Decimal(0)
    for se in seiten:
        if se.vortrag is not None:
            assert se.vortrag == kum, f"{nr}: Vortrag"
        kum += sum(ps[i].gesamt for i in se.pos)
        if se.uebertrag is not None:
            assert se.uebertrag == kum, f"{nr}: Übertrag"
    assert kum == netto and 1 <= len(d["buyer"]["name_lines"]) <= 3


def selbstcheck_a1(d: dict, ps: list[Pos], seiten: list[Seite], s: Spez):
    """A1-Belege: alles stimmt bis auf genau den einen beabsichtigten Bruch (Fallen: gar keiner)."""
    nr = d["datei"]
    assert s.holdout and s.pruefen is None and not (s.fehler and s.falle), nr
    assert (s.fehler in FEHLERARTEN) if s.fehler else (s.falle in FALLEN), nr
    assert {p.satz for p in ps} == {SATZ} and "vat_breakdown" not in d, f"{nr}: nur 19 % (v1)"
    g = {k: Decimal(v) for k, v in d["totals"].items()}
    assert d["totals"] == d["totals_printed"], nr
    brueche = []
    falsch = [i for i, p in enumerate(ps) if p.gesamt != p.gesamt_berechnet]
    if falsch:
        brueche.append("zeile")
    if sum(p.gesamt for p in ps) != g["net"]:
        brueche.append("summe_positionen")
    if cent(g["net"] * SATZ / 100) != g["vat"]:
        brueche.append("ust_betrag")
    if g["net"] + g["vat"] != g["gross"]:
        brueche.append("netto_brutto")
    if not iban_gueltig(d["seller"]["iban"]):
        brueche.append("iban_pruefziffer")
    if not ust_id_de_gueltig(d["seller"]["ust_id"]):
        brueche.append("ust_id_pruefziffer")
    if not d["invoice"]["number"]:
        brueche.append("rechnungsnummer_fehlt")
    if not d["invoice"]["date"]:
        brueche.append("rechnungsdatum_fehlt")
    else:
        rd = date(*reversed([int(x) for x in d["invoice"]["date"].split(".")]))
        fd = date(*reversed([int(x) for x in d["payment"]["due_date"].split(".")]))
        if fd < rd:
            brueche.append("faelligkeit_vor_datum")
    assert brueche == ([s.fehler] if s.fehler else []), f"{nr}: Brüche {brueche}, erwartet {s.fehler}"
    assert len(falsch) == (s.fehler == "zeile"), nr
    assert d["BT-72"] == d["invoice"]["service_date"] != "", nr
    if d["payment"]["discount_amount"]:
        assert Decimal(d["payment"]["discount_amount"]) == cent(g["gross"] * s.skonto / 100), nr
    assert len(seiten) == s.seiten, f"{nr}: {len(seiten)} Seiten statt {s.seiten}"
    assert [i for se in seiten for i in se.pos] == list(range(len(ps))), nr
    kum = Decimal(0)
    for se in seiten:
        if se.vortrag is not None:
            assert se.vortrag == kum, f"{nr}: Vortrag"
        kum += sum(ps[i].gesamt for i in se.pos)
        if se.uebertrag is not None:
            assert se.uebertrag == kum, f"{nr}: Übertrag"


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def zurueckgelesen(pdf: Path, d: dict, muss: list[tuple[int, str]]):
    """Liest die PDF mit pdfplumber zurück; ``muss`` = [(Seite 1.., Text)], der auf der Seite stehen muss."""
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        assert len(doc.pages) == d["page_count"], pdf.name
        texte = [_norm(p.extract_text() or "") for p in doc.pages]
    alle = " ".join(texte)
    assert d["invoice"]["number"] in texte[0], (pdf.name, "Nummer")
    for z in d["buyer"]["name_lines"] + [d["buyer"]["street"], d["buyer"]["city"]]:
        assert z in texte[0], (pdf.name, z)
    for t in d["payment_terms_text"]:
        assert _norm(t) in alle, (pdf.name, t)
    assert d["seller"]["iban"] in alle and d["seller"]["ust_id"] in alle, (pdf.name, "IBAN/USt-IdNr.")
    for seite, t in muss:
        assert _norm(t) in texte[seite - 1], (pdf.name, seite, t)
    for v in (d.get("falle_detail") or {}).values():
        assert v in texte[0], (pdf.name, "Falle", v)


MATRIX = ["Datei", "Split", "Rechnungsnummer", "Rechnungsdatum", "Kundennummer", "Namenszeilen", "Seiten",
          "Format", "Positionen", "Mehrzeilig", "Versand", "Zahlung", "Skonto", "Netto", "USt", "Brutto",
          "Status", "Notiz", "SHA256"]


def erzeuge(f: Familie, muss) -> list[dict]:
    """Erzeugt alle Belege einer Familie in ``<ordner>/Rechnungen`` und ``<ordner>/Referenzdaten``."""
    rng = random.Random(f.seed)
    basis = SET / f.ordner
    rech, ref = basis / "Rechnungen", basis / "Referenzdaten"
    for o in (rech, ref):
        if o.exists():
            shutil.rmtree(o)
    rech.mkdir(parents=True)
    ref.mkdir(parents=True)
    if any(s.holdout for s in f.spez):
        (ref / "holdout").mkdir()
    datum, out, zeilen = f.datum0, [], []
    for n, s in enumerate(f.spez, start=1):
        datum = werktag(datum + timedelta(days=rng.choice([2, 3, 5, 7])))
        ab, alt = f.absender, (f.absender.iban, f.absender.ust_id)
        try:
            if s.fehler == "iban_pruefziffer":       # die Familie zeichnet aus ``AB`` -> nur für diesen Beleg
                ab.iban = _falsche_pruefziffer_iban(ab.iban)
            elif s.fehler == "ust_id_pruefziffer":
                ab.ust_id = _falsche_pruefziffer_ust_id(ab.ust_id)
            d, ps, seiten = beleg(f, n, s, rng, datum)
            if s.fehler in ("iban_pruefziffer", "ust_id_pruefziffer"):
                d["fehler_detail"] = {"gedruckt": ab.iban if s.fehler == "iban_pruefziffer" else ab.ust_id,
                                      "richtig": alt[0] if s.fehler == "iban_pruefziffer" else alt[1]}
            selbstcheck(d, ps, seiten, s)
            pdf = rech / d["datei"]
            f.zeichnen(pdf, d, ps, seiten, s)
        finally:
            ab.iban, ab.ust_id = alt
        zurueckgelesen(pdf, d, muss(d, ps, seiten, s))
        d["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        ziel = (ref / "holdout" if s.holdout else ref) / (pdf.stem + ".json")
        ziel.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        t = d["totals_printed"]
        zeilen.append([d["datei"], d["split"], d["invoice"]["number"], d["invoice"]["date"],
                       d["buyer"]["customer_number"], len(d["buyer"]["name_lines"]), d["page_count"], s.format,
                       len(ps), sum(len(p.beschreibung) > 1 for p in ps), "ja" if s.versand else "",
                       s.zahlung, s.skonto or "", t["net"], t["vat"], t["gross"], d["erwarteter_status"], s.notiz,
                       d["sha256"]])
        out.append(d)
        print(f"  {f.ordner}/{d['datei']:38s} {d['page_count']} S. {len(ps):2d} Pos. {d['split']:8s} "
              f"{d['erwarteter_status']}")
    with open(ref / "Testfallmatrix.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(MATRIX)
        w.writerows(zeilen)
    return out
