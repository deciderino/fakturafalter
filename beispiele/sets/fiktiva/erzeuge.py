#!/usr/bin/env python3
"""Testdaten-Set „Fiktiva Antriebstechnik GmbH“: 30 erfundene Rechnungen im Mandanten-Layout.

Seit A1 (20.11.2026): Belege 025–030 sind Hold-out mit absichtlichem Fehler (``Spez.fehler``) bzw. mit Falle
(``Spez.falle``); sie hängen am Ende, damit 001–024 byte-gleich bleiben.

Nachgebaut nach dem Layout von ``tests/daten/fiktiv`` (Branch ``erkennung/benchmark``) und den Vorgaben von
E-Rechnung zum v1-Umfang (ein Mandant, Inland, B2B, 19 %). Alle Namen, Anschriften, Nummern und Beträge sind
erfunden. Domains ``*.example``, Bankleitzahl ``00000000``.

Aufruf (aus der Repo-Wurzel):

    .venv/bin/python beispiele/sets/fiktiva/erzeuge.py

Deterministisch: fester Seed (``SEED``), reportlab mit ``invariant=1`` (keine Zeitstempel, feste Datei-ID).
Ausgabe: ``Rechnungen/Rechnung_NNN_<NR>.pdf``, ``Referenzdaten/Rechnung_*.json`` (Belege zum Messen und Tunen),
``Referenzdaten/holdout/Rechnung_*.json`` (Hold-out: nur messen) und ``Referenzdaten/Testfallmatrix.csv``.
Vor dem Schreiben rechnet der Selbstcheck jede Rechnung nach (Σ Positionen = Netto, Netto + USt = Brutto,
Menge × Preis / PE = Gesamt, Skonto = Brutto × Satz, Überträge) und liest danach jede PDF mit pdfplumber zurück.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

SEED = 26_4711
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parents[2] / "src"))         # fakturafalter.pflichtpruefung für den Selbstcheck
SCHRIFT = Path("/usr/share/fonts/truetype/liberation")
pdfmetrics.registerFont(TTFont("LiberationSans", str(SCHRIFT / "LiberationSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("LiberationSans-Bold", str(SCHRIFT / "LiberationSans-Bold.ttf")))
R, B = "LiberationSans", "LiberationSans-Bold"

# ------------------------------------------------------------------ Geometrie (pt, von oben) wie tests/daten/fiktiv
BREITE, HOEHE = 595.28, 841.89
LINKS, RECHTS = 53.86, 552.76
ASC = 0.7896                         # pdfplumber-top + ASC × Größe = Grundlinie (LiberationSans)
DUNKEL = Color(0.105957, 0.14502, 0.18042)
AKZENT = Color(0.14502, 0.223633, 0.298096)
GRAU = Color(0.403809, 0.447021, 0.482422)
HELL = Color(0.716797, 0.761719, 0.796875)
HELLER = Color(0.894531, 0.914063, 0.929688)
WEISS = Color(1, 1, 1)
X_MENGE, X_ME, X_BEZ, X_PREIS, X_PE, X_GES = 96.38, 110.55, 153.07, 428.03, 453.54, 549.92
ZEILE0 = 448.128                     # Grundlinie der ersten Tabellenzeile
TAKT = 11.9055                       # Zeilenabstand Tabelle
BEZ_BREITE = 215.0                   # Umbruchbreite der Bezeichnung (8,8 pt)
S1_LETZTE = 19                       # einseitig/Endseite 1: letzte Zeile (Rechnungsbetrag) höchstens Index 19
S1_INHALT = 18                       # Seite 1 mehrseitig: Inhalt Index 0..17, Übertrag Index 18
SN_LETZTE = 23                       # Folgeseiten: Übertrag bzw. Rechnungsbetrag höchstens Index 23

VERKAEUFER = {
    "name": "Fiktiva Antriebstechnik GmbH",
    "street": "Musterring 12",
    "postal_code": "04179",
    "city": "Leipzig",
    "ust_id": "DE314159262",                      # DE-Prüfziffer (ISO 7064 MOD 11,10) gültig, erfunden
    "iban": "DE71 0000 0000 0047 1108 15",       # MOD-97 gültig, BLZ 00000000, erfundenes Konto
    "bic": "FIKTDEX1XXX",
    "bank": "Beispielbank Leipzig",
    "email": "rechnung@fiktiva.example",
    "register": "Amtsgericht Leipzig, HRB 000000",
    "ceo": "Jana Mustermann",
}
TELEFON = "Tel. 0341 000000-0"
MARKE, MARKE_ZUSATZ, KUERZEL = "FIKTIVA", "Antriebstechnik GmbH", "FA"

# ------------------------------------------------------------------ Stammdaten (erfunden)
KUNDEN = [  # Namenszeilen (Firmenname ggf. zweizeilig), Straße, PLZ, Ort, Kundennummer
    (["Brennecke Verpackungsanlagen GmbH"], "Industriestraße 41", "33609", "Bielefeld", "10427"),
    (["Hollerbach Sondermaschinenbau", "GmbH & Co. KG"], "Am Kanalhafen 7", "47059", "Duisburg", "K-20815"),
    (["Werkzeugbau Lindqvist KG"], "Talweg 3", "72764", "Reutlingen", "0008815"),
    (["Oderbruch Fördertechnik GmbH"], "Gewerbepark 12", "15344", "Strausberg", "31002"),
    (["Kremer & Sohn Anlagenbau GmbH"], "Hafenstraße 88", "28217", "Bremen", "K-20977"),
    (["Pumpenwerk Ahrens AG"], "Wehrstraße 5", "57439", "Attendorn", "40118"),
    (["Mühlhausener Kunststofftechnik", "Beispiel GmbH"], "Ziegeleiweg 19", "99974", "Mühlhausen", "0012044"),
    (["Seewald Präzisionsdreherei e. K."], "Bachgasse 2", "79098", "Freiburg im Breisgau", "52260"),
    (["Vogtland Textilmaschinen GmbH"], "Spinnereistraße 14", "08523", "Plauen", "0003391"),
    (["Landtechnik Eilers GmbH"], "Deichweg 30", "26789", "Leer (Ostfriesland)", "61907"),
    (["Rheinauen Galvanik GmbH"], "Am Altrhein 1a", "67059", "Ludwigshafen am Rhein", "K-21330"),
    (["Elbtal Steuerungsbau GmbH"], "Werkstättenstraße 120", "01159", "Dresden", "70014"),
]
ZUSATZ = ["Abteilung Einkauf", "Abteilung Instandhaltung", "Abteilung Konstruktion", "z. Hd. Frau Brandt",
          "z. Hd. Herrn Okafor", "z. Hd. Frau Dr. Weißgerber", "Abteilung Rechnungsprüfung"]
VERSAND = ["DHL", "Spedition", "Abholung", "UPS", "Lieferung frei Haus", ""]

STK = [  # Bezeichnung, Preisspanne (€ je Stück)
    ("Lagerbock LB-40 Stahl verzinkt", (18, 65)), ("Zahnriemenscheibe T10 Z=32", (24, 90)),
    ("Distanzbuchse 20x30x15", (1.2, 6)), ("Wellenkupplung WK-25 elastisch", (38, 140)),
    ("Getriebeflansch GF-80", (55, 210)), ("Motorkonsole MK-112 geschweißt", (85, 320)),
    ("Spannsatz SP-30 Ø 30 mm", (19, 48)), ("Kettenrad 1/2\" Z=19", (14, 39)),
    ("Antriebswelle nach Zeichnung", (120, 480)), ("Schutzhaube Riementrieb", (45, 160)),
    ("Klemmhebel M8 Kunststoff", (2.4, 7.9)), ("Lagerdeckel LD-62", (6.5, 22)),
]
STK100 = [  # Kleinteile, Preis je 100 Stück
    ("Zylinderschraube ISO 4762 M6x20 8.8 verzinkt", (4, 14)), ("Sechskantmutter ISO 4032 M8 verzinkt", (2.5, 8)),
    ("Scheibe ISO 7089 8 verzinkt", (1.2, 4.5)), ("Gewindestift ISO 4026 M5x8", (5, 16)),
    ("Zylinderstift ISO 8734 6x24", (9, 28)), ("Sicherungsring DIN 471 20x1,2", (6, 19)),
    ("O-Ring 20x2 NBR 70", (7, 24)), ("Passfeder DIN 6885 A 8x7x40", (18, 55)),
]
STD = [  # Dienstleistungen je Stunde
    ("Montagearbeit vor Ort", (58, 78)), ("Inbetriebnahme Antriebseinheit", (72, 95)),
    ("Programmierung Frequenzumrichter", (78, 98)), ("Konstruktionsstunden", (68, 88)),
    ("Fahrzeit Monteur", (45, 60)), ("Fehlersuche und Instandsetzung", (62, 84)),
]
LANG = [  # Zusatztexte, die mit der Bezeichnung umbrechen
    "gefertigt nach Zeichnung 26-0412 Rev. C, Werkstoff C45, Toleranzen nach ISO 2768-mK, Kanten gebrochen",
    "Bohrung H7 Ø 20 mm mit Passfedernut DIN 6885, Gewindebohrungen 4x M6 auf Teilkreis 70 mm",
    "inkl. Prüfprotokoll und Werkszeugnis 2.2 nach EN 10204",
    "Ausführung wie Muster vom 14.09.2026, Oberfläche schwarz brüniert",
    "laut Serviceauftrag, Arbeiten an Linie 3 einschließlich Probelauf und Einweisung des Personals",
]
MIND_ARTIKEL = ["Passscheibe 10x16x0,5", "Senkschraube ISO 10642 M4x12", "Kabelbinder 200x4,8 schwarz",
                "Spannstift ISO 8752 4x20", "Federring DIN 127 B6", "Stellring 12 mm verzinkt",
                "Gummipuffer 20x15 M6", "Blindniet 4x10 Alu"]
MIND_TITEL = ["Mindestauftrag", "Gesamtpreis", "Mindestauftragswert", "Gesamtpreis lt. Angebot 26-118"]

# ------------------------------------------------------------------ Varianz je Beleg
@dataclass
class Spez:
    kunde: int
    zusatz: list[str] = field(default_factory=list)   # Zusatzzeilen (Teil des Namens), max. 3 Namenszeilen gesamt
    leer: int = 1                                       # Leerzeilen zwischen Straße und PLZ Ort
    skonto: int | None = None                           # Prozent
    skonto_tage: int = 10
    bestellung: bool = True
    zeilen: int = 4                                     # Ziel: Inhaltszeilen der Tabelle (ohne Summen/Übertrag)
    mix: str = "stk"                                    # stk | stk100 | std | mischung
    lang: int = 0                                       # Positionen mit umbrechender Bezeichnung
    mindest: str | None = None                          # None | "rein" | "teil"
    vortrag: bool = False
    seiten: int = 1                                     # erwartete Seitenzahl (Selbstcheck)
    holdout: bool = False
    tausend: bool = False                               # mindestens eine Menge ≥ 1.000
    notiz: str = ""
    fehler: str | None = None                           # absichtlicher Fehler (nur Hold-out), siehe FEHLERARTEN
    falle: str | None = None                            # Ablenker für False Positives (nur Hold-out), siehe FALLEN


SPEZ = [
    Spez(0, zeilen=3, notiz="einfach"),
    Spez(1, skonto=2, zeilen=4, notiz="zweizeiliger Firmenname, Skonto"),
    Spez(2, ["Abteilung Instandhaltung", "z. Hd. Herrn Okafor"], bestellung=False, zeilen=5, mix="mischung",
         notiz="3 Namenszeilen mit Abteilung und z. Hd."),
    Spez(3, ["Abteilung Einkauf"], skonto=3, zeilen=4, mix="stk100", notiz="Preiseinheit /100"),
    Spez(4, zeilen=6, mix="stk", tausend=True, notiz="Tausenderpunkt Menge"),
    Spez(5, ["z. Hd. Frau Brandt"], skonto=2, skonto_tage=14, zeilen=8, mindest="rein",
         notiz="reiner Mindestauftrag"),
    Spez(6, ["z. Hd. Frau Dr. Weißgerber"], skonto=3, zeilen=7, mix="mischung", lang=1, holdout=True,
         notiz="zweizeiliger Firmenname + z. Hd., /1 und /100"),
    Spez(7, zeilen=26, mix="mischung", seiten=2, notiz="2 Seiten, Übertrag ohne Vortrag"),
    Spez(8, ["Abteilung Konstruktion"], skonto=2, zeilen=30, mix="stk", lang=2, vortrag=True, seiten=2,
         notiz="2 Seiten, Übertrag und Vortrag"),
    Spez(9, ["Abteilung Instandhaltung"], zeilen=28, mindest="teil", vortrag=True, seiten=2, holdout=True,
         bestellung=False, notiz="2 Seiten mit Vortrag, Mindestauftrag-Gruppe"),
    Spez(10, zeilen=17, mix="stk", notiz="einseitig knapp am Seitenende (Netto-Zeile 643,5 pt)"),
    Spez(11, ["Abteilung Einkauf"], skonto=3, zeilen=16, mix="mischung", lang=1,
         notiz="einseitig knapp am Seitenende (Netto-Zeile 631,6 pt), Skonto"),
    Spez(0, ["Abteilung Rechnungsprüfung"], leer=2, zeilen=6, mindest="teil", holdout=True, bestellung=False,
         notiz="Mindestauftrag gemischt, 2 Leerzeilen in der Anschrift"),
    Spez(1, ["z. Hd. Herrn Okafor"], skonto=3, zeilen=52, mix="mischung", lang=2, vortrag=True, seiten=3,
         tausend=True, notiz="3 Seiten, Übertrag und Vortrag, Skonto"),
    Spez(2, zeilen=50, mix="stk", lang=1, seiten=3, holdout=True, notiz="3 Seiten ohne Vortrag"),
    Spez(3, ["Abteilung Einkauf", "z. Hd. Frau Brandt"], skonto=2, zeilen=24, mix="stk100", bestellung=False,
         seiten=2, notiz="2 Seiten, nur /100"),
    Spez(4, zeilen=5, mix="stk100", tausend=True, notiz="/100 mit Mengen ≥ 1.000"),
    Spez(5, leer=2, zeilen=39, mix="mischung", lang=1, seiten=2,
         notiz="2 Seiten, Endseite bis knapp vor die Fußzeile, 2 Leerzeilen"),
    Spez(6, zeilen=9, mix="stk", lang=3, holdout=True, notiz="lange umbrechende Bezeichnungen"),
    Spez(7, ["Abteilung Konstruktion"], skonto=2, zeilen=22, mindest="teil", seiten=2,
         notiz="2 Seiten, Mindestauftrag-Gruppe"),
    Spez(8, ["Abteilung Instandhaltung"], skonto=3, skonto_tage=14, zeilen=6, mix="std", lang=1, holdout=True,
         notiz="nur Stunden, Skonto"),
    Spez(9, ["Abteilung Einkauf"], zeilen=15, mix="mischung", notiz="einseitig, Netto-Zeile 619,7 pt"),
    Spez(10, ["z. Hd. Frau Dr. Weißgerber"], skonto=2, zeilen=38, mix="stk100", vortrag=True, seiten=2,
         holdout=True, notiz="2 Seiten mit Vortrag, /100, Endseite knapp vor der Fußzeile"),
    Spez(11, zeilen=5, mindest="rein", holdout=True, bestellung=False, skonto=2,
         notiz="reiner Mindestauftrag, Skonto"),
    # ---- A1 (20.11.2026): neue Hold-out-Belege mit absichtlichem Fehler bzw. mit Falle; nur angehängt, damit
    #      die Belege 001–024 byte-gleich bleiben (gleicher Zufallsstrom bis Beleg 024).
    Spez(4, ["Abteilung Einkauf"], zeilen=7, mix="mischung", holdout=True, fehler="zeile",
         notiz="FEHLER: Zahlendreher im Gesamtpreis einer Position"),
    Spez(6, skonto=2, zeilen=5, mix="stk", holdout=True, fehler="ust_betrag",
         notiz="FEHLER: MwSt. mit 16 % gerechnet, Beschriftung 19 %"),
    Spez(9, ["z. Hd. Herrn Okafor"], zeilen=26, mix="mischung", seiten=2, holdout=True, fehler="iban_pruefziffer",
         notiz="FEHLER: IBAN im Fuß mit vertauschter Prüfziffer (2 Seiten)"),
    Spez(10, zeilen=4, bestellung=False, holdout=True, fehler="faelligkeit_vor_datum",
         notiz="FEHLER: Zahldatum mit Vorjahr, liegt vor dem RE-Datum"),
    Spez(11, ["Abteilung Rechnungsprüfung"], skonto=3, zeilen=6, mix="stk100", holdout=True, falle="lieferschein_nr",
         notiz="FALLE: Lieferschein-Nr. im Format der Rechnungsnummer direkt darunter"),
    Spez(3, skonto=2, zeilen=9, mindest="teil", holdout=True, falle="hinweis_betrag",
         notiz="FALLE: Hinweis mit anderem Betrag unter den Zahlungsbedingungen"),
]

FEHLERARTEN = {
    "zeile": "Menge × Preis / PE ≠ gedruckter Gesamtpreis einer Position (Zahlendreher); Netto, MwSt. und "
             "Brutto sind aus den gedruckten Zeilenbeträgen richtig weitergerechnet",
    "ust_betrag": "MwSt.-Betrag mit 16 % statt 19 % gerechnet (Beschriftung „MwSt. 19 %“); Brutto = Netto + "
                  "gedruckte MwSt., Skonto vom gedruckten Brutto",
    "iban_pruefziffer": "IBAN im Fuß mit vertauschten Prüfziffern (MOD 97 ungültig); sonst alles richtig",
    "faelligkeit_vor_datum": "Zahldatum „zahlbar bis …“ mit Vorjahr, liegt damit vor dem RE-Datum; sonst alles richtig",
}
FALLEN = {
    "lieferschein_nr": "zusätzliche Kopfzeile „Lieferschein-Nr.:“ mit einer Nummer im Format der Rechnungsnummer "
                       "(LS-26-… statt FA-26-…) direkt unter der Rechnungsnummer; BT-1 bleibt die Rechnungsnummer",
    "hinweis_betrag": "Hinweiszeile mit einem anderen Betrag unter den Zahlungsbedingungen (Bestellwert für "
                      "frachtfreie Lieferung); weder Summe noch Skonto",
}

# ------------------------------------------------------------------ Hilfen
CENT = Decimal("0.01")


def cent(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def betrag(d: Decimal) -> str:
    s = f"{cent(d):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def menge(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def preis_zufall(rng: random.Random, spanne) -> Decimal:
    lo, hi = spanne
    p = Decimal(str(round(rng.uniform(lo, hi), 2)))
    if p >= 20:
        p = (p * 4).quantize(Decimal(1)) / 4          # Viertel-Euro bei größeren Preisen
    return cent(p)


def umbrechen(text: str, breite: float = BEZ_BREITE, schrift=R, groesse=8.8) -> list[str]:
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


@dataclass
class Pos:
    qty: int
    unit: str                 # "Stk." | "Std." | ""
    beschreibung: list[str]
    preis: Decimal | None
    pe: int | None            # 1 | 100 | None (nicht gedruckt)
    art: str                  # regular | without_price | flat_rate
    mindest: bool = False
    gesamt_druck: Decimal | None = None   # nur Fehlerart „zeile“: gedruckter (falscher) Gesamtpreis

    @property
    def gesamt(self) -> Decimal | None:
        if self.gesamt_druck is not None:
            return self.gesamt_druck
        return None if self.preis is None else cent(self.qty * self.preis / self.pe)

    @property
    def gesamt_berechnet(self) -> Decimal | None:
        return None if self.preis is None else cent(self.qty * self.preis / self.pe)


def artikel(rng: random.Random, art: str, nummer: str, lang: bool, tausend: bool) -> Pos:
    if art == "std":
        bez, sp = rng.choice(STD)
        qty = rng.choice([2, 3, 4, 6, 8, 12, 16, 24, 40])
        p = Pos(qty, "Std.", [bez], preis_zufall(rng, sp), 1, "regular")
    elif art == "stk100":
        bez, sp = rng.choice(STK100)
        qty = (rng.choice([1000, 2000, 2500, 5000, 10000]) if tausend
               else rng.choice([150, 200, 250, 300, 400, 500, 750]))
        p = Pos(qty, "Stk.", [f"{bez} {nummer}"], preis_zufall(rng, sp), 100, "regular")
    else:
        bez, sp = rng.choice(STK)
        qty = rng.choice([1000, 1200, 2500]) if tausend else rng.choice([1, 2, 4, 5, 6, 10, 12, 20, 25, 40, 50])
        if tausend:
            sp = (min(sp[0], 3), min(sp[1], 9))
        p = Pos(qty, "Stk.", [f"{bez} {nummer}"], preis_zufall(rng, sp), 1, "regular")
    if lang:
        p.beschreibung = umbrechen(p.beschreibung[0] + " " + rng.choice(LANG))
    return p


def positionen(rng: random.Random, s: Spez) -> list[Pos]:
    """Positionen, bis die Tabelle genau ``s.zeilen`` Inhaltszeilen hat."""
    out: list[Pos] = []
    def zeilen() -> int:
        return sum(len(p.beschreibung) for p in out)
    def nummer() -> str:
        return f"{rng.randint(10, 89)}-{rng.randint(1000, 9999)}"
    def art() -> str:
        if s.mix == "mischung":
            return rng.choice(["stk", "stk", "stk100", "std"])
        return s.mix
    lang_rest, tausend_rest = s.lang, s.tausend

    def mindest_gruppe(anzahl: int):
        for _ in range(anzahl):
            out.append(Pos(rng.choice([10, 20, 25, 50, 100, 200]), "", [f"{rng.choice(MIND_ARTIKEL)} {nummer()}"],
                           None, None, "without_price", mindest=True))
        out.append(Pos(1, "", [rng.choice(MIND_TITEL)], Decimal(rng.choice(["75.00", "95.00", "120.00", "150.00"])),
                       1, "flat_rate", mindest=True))

    if s.mindest == "rein":
        mindest_gruppe(s.zeilen - 1)
        return out
    gruppe_bei = (s.zeilen // 2) if s.mindest == "teil" else None
    while zeilen() < s.zeilen:
        rest = s.zeilen - zeilen()
        if gruppe_bei is not None and zeilen() >= gruppe_bei and rest >= 3:
            mindest_gruppe(min(4, rest - 1))
            gruppe_bei = None
            continue
        lang_jetzt = lang_rest > 0 and rest >= 4 and (rest <= 4 * lang_rest + 4 or rng.random() < 0.4)
        p = artikel(rng, art(), nummer(), lang_jetzt, tausend_rest)
        if len(p.beschreibung) > rest:
            p = artikel(rng, art(), nummer(), False, tausend_rest)
        if lang_jetzt and len(p.beschreibung) > 1:
            lang_rest -= 1
        if tausend_rest and p.qty >= 1000:
            tausend_rest = False
        out.append(p)
    if lang_rest > 0:
        raise AssertionError(f"lange Bezeichnungen nicht untergebracht ({lang_rest})")
    return out


@dataclass
class Seite:
    nr: int
    pos: list[int]            # 0-basierte Positionsindizes
    zeilen: int               # Inhaltszeilen (ohne Vortrag/Übertrag/Summen)
    vortrag: Decimal | None
    uebertrag: Decimal | None
    summen: bool


def umbruch(ps: list[Pos], vortrag: bool) -> list[Seite]:
    seiten: list[Seite] = []
    i, kum, nr = 0, Decimal(0), 1
    while True:
        start = 0 if nr == 1 or not vortrag else 1
        letzte = S1_LETZTE if nr == 1 else SN_LETZTE
        inhalt_bis = S1_INHALT if nr == 1 else SN_LETZTE           # Übertrag-Zeile = erster freier Index
        rest = ps[i:]
        bedarf = sum(len(p.beschreibung) for p in rest)
        vt = kum if (nr > 1 and vortrag) else None
        if start + bedarf + 3 - 1 <= letzte:                        # alles + 3 Summenzeilen passt
            seiten.append(Seite(nr, list(range(i, len(ps))), bedarf, vt, None, True))
            return seiten
        idx, z = [], start
        while i < len(ps) and z + len(ps[i].beschreibung) <= inhalt_bis:
            z += len(ps[i].beschreibung)
            kum += ps[i].gesamt or 0
            idx.append(i)
            i += 1
        if i == len(ps):                                             # Rest passt, Summen nicht: letzte Pos. weiter
            i -= 1
            idx.pop()
            kum -= ps[i].gesamt or 0
            z -= len(ps[i].beschreibung)
        seiten.append(Seite(nr, idx, z - start, vt, cent(kum), False))
        nr += 1


# ------------------------------------------------------------------ Zeichnen
class Blatt:
    def __init__(self, c: canvas.Canvas):
        self.c = c

    def text(self, x, top, s, schrift=R, groesse=8.8, farbe=DUNKEL, rechts=False, mitte=False):
        c = self.c
        c.setFont(schrift, groesse)
        c.setFillColor(farbe)
        y = HOEHE - (top + ASC * groesse)
        if rechts:
            c.drawRightString(x, y, s)
        elif mitte:
            c.drawCentredString(x, y, s)
        else:
            c.drawString(x, y, s)

    def zeile(self, x, top, s, **kw):      # Tabellen-Text auf Grundlinie ``top`` (= Grundlinie)
        groesse = kw.pop("groesse", 8.8)
        self.text(x, top - ASC * groesse, s, groesse=groesse, **kw)

    def linie(self, x0, top, x1, breite, farbe):
        c = self.c
        c.setStrokeColor(farbe)
        c.setLineWidth(breite)
        c.line(x0, HOEHE - top, x1, HOEHE - top)


def kopf_fuss(b: Blatt, d: dict, seite: int, seiten: int):
    v = d["seller"]
    c = b.c
    c.setFillColor(AKZENT)
    c.roundRect(LINKS, HOEHE - 85.04, 36.85, 36.85, 2.5, stroke=0, fill=1)
    b.text(72.28, 64.12, KUERZEL, B, 12.5, WEISS, mitte=True)
    b.text(102.05, 48.04, MARKE, B, 16, AKZENT)
    b.text(102.61, 69.40, MARKE_ZUSATZ, R, 9, GRAU)
    b.text(RECHTS, 57.44, f"{v['street']} · {v['postal_code']} {v['city']}", R, 8, GRAU, rechts=True)
    b.text(552.75, 73.50, f"{TELEFON}  ·  {v['email']}", R, 7.4, GRAU, rechts=True)
    b.linie(LINKS, 103.46, RECHTS, 0.85, AKZENT)
    b.text(LINKS, 144.76, f"{v['name']} · {v['street']} · {v['postal_code']} {v['city']}", R, 6.9, GRAU)
    # Anschrift: PLZ Ort fest, darüber Leerzeile(n), Straße, Namenszeilen
    k = d["buyer"]
    plz_top = 298.12
    str_top = plz_top - 11.34 * (1 + d["test_flags"]["address_blank_lines"])
    b.text(LINKS, plz_top, f"{k['postal_code']} {k['city']}", R, 9.4, DUNKEL)
    b.text(LINKS, str_top, k["street"], R, 9.4, DUNKEL)
    for j, n in enumerate(reversed(k["name_lines"])):
        b.text(LINKS, str_top - 11.34 * (j + 1), n, R, 9.4, DUNKEL)
    # Rechnungskopf
    inv = d["invoice"]
    b.text(337.32, 147.93, "RECHNUNG", B, 15.5, AKZENT)
    felder = [("Rechnungsnummer:", inv["number"], B), ("RE-Datum:", inv["date"], R),
              ("Leistungsdatum:", inv["service_date"], R), ("Kundennummer:", k["customer_number"], R),
              ("Bestellnummer:", inv["order_number"], R), ("Versandart:", inv["shipping"], R)]
    if d.get("falle") == "lieferschein_nr":
        felder.insert(1, ("Lieferschein-Nr.:", d["falle_detail"]["lieferschein_nr"], R))
    for j, (lab, wert, schrift) in enumerate(felder):
        top = 190.58 + 15.307 * j
        b.text(337.32, top, lab, R, 8.1, GRAU)
        if wert:
            b.text(445.04, top - 0.28, wert, schrift, 8.5, DUNKEL)
    # Tabellenkopf
    b.text(LINKS, 378.03, "Rechnungspositionen", B, 10.2, AKZENT)
    b.linie(LINKS, 401.39, RECHTS, 0.8, AKZENT)
    for x, t, art in [(X_MENGE, "Menge", "r"), (X_ME, "ME", "l"), (X_BEZ, "Bezeichnung", "l"),
                      (X_PREIS, "Preis", "r"), (X_PE, "PE", "m"), (X_GES, "Gesamtpreis", "r")]:
        b.text(x, 413.22, t, B, 8, AKZENT, rechts=art == "r", mitte=art == "m")
    b.linie(LINKS, 428.03, RECHTS, 0.45, HELL)
    # Zahlungsblock nur Seite 1, fest
    if seite == 1:
        b.linie(LINKS, 688.82, RECHTS, 0.45, HELLER)
        b.text(LINKS, 699.29, "Zahlungsbedingungen", B, 9, AKZENT)
        for j, t in enumerate(d["payment_terms_text"]):
            b.text(LINKS, 715.89 + 11.91 * j, t, R, 8.4, DUNKEL)
        if d.get("falle") == "hinweis_betrag":
            b.text(LINKS, 715.89 + 11.91 * len(d["payment_terms_text"]) + 4, d["falle_detail"]["hinweis"],
                   R, 8.4, GRAU)
    # Fuß
    b.linie(LINKS, 763.09, RECHTS, 0.65, AKZENT)
    b.text(LINKS, 773.74, v["name"], B, 7.7, AKZENT)
    b.text(LINKS, 785.24, f"GF: {v['ceo']} · AG Leipzig, HRB 000000", R, 7.1, GRAU)
    b.text(LINKS, 796.29, f"USt-IdNr.: {v['ust_id']}", R, 7.1, GRAU)
    b.text(314.65, 773.74, v["bank"], B, 7.7, AKZENT)
    b.text(314.65, 785.24, f"IBAN: {v['iban']}", R, 7.1, GRAU)
    b.text(314.65, 796.29, f"BIC: {v['bic']}", R, 7.1, GRAU)
    b.text(LINKS, 820.93, "FIKTIVE MUSTERRECHNUNG · TESTDATEN · KEINE ZAHLUNG", B, 6.8, GRAU)
    b.text(552.75, 820.75, f"Seite {seite} von {seiten}", R, 7.0, GRAU, rechts=True)


def zeichnen(pfad: Path, d: dict, ps: list[Pos], seiten: list[Seite]):
    c = canvas.Canvas(str(pfad), pagesize=(BREITE, HOEHE), invariant=1, pageCompression=1)
    c.setTitle(f"Rechnung {d['invoice']['number']}")
    c.setAuthor(f"{VERKAEUFER['name']} – fiktiver Rechnungssteller")
    c.setSubject("Fiktive Testrechnung für Fakturafalter; keine echte Forderung")
    c.setCreator("beispiele/sets/fiktiva/erzeuge.py")
    b = Blatt(c)
    t = d["totals"]
    for s in seiten:
        kopf_fuss(b, d, s.nr, len(seiten))
        z = 0
        def gl() -> float:
            return ZEILE0 + TAKT * z
        if s.vortrag is not None:
            b.zeile(X_BEZ, gl(), "Vortrag", schrift=B, groesse=8.9, farbe=AKZENT)
            b.zeile(X_GES, gl(), betrag(s.vortrag), schrift=B, groesse=8.9, farbe=AKZENT, rechts=True)
            z += 1
        for i in s.pos:
            p = ps[i]
            b.zeile(X_MENGE, gl(), menge(p.qty), groesse=9.0, rechts=True)
            if p.unit:
                b.zeile(X_ME, gl(), p.unit)
            if p.preis is not None:
                b.zeile(X_PREIS, gl(), betrag(p.preis), rechts=True)
                b.zeile(X_PE, gl(), f"/{p.pe}", mitte=True)
                b.zeile(X_GES, gl(), betrag(p.gesamt), rechts=True)
            for zeile in p.beschreibung:
                b.zeile(X_BEZ, gl(), zeile)
                z += 1
        if s.uebertrag is not None:
            b.zeile(X_BEZ, gl(), "Übertrag", schrift=B, groesse=8.9, farbe=AKZENT)
            b.zeile(X_GES, gl(), betrag(s.uebertrag), schrift=B, groesse=8.9, farbe=AKZENT, rechts=True)
        if s.summen:
            b.zeile(X_BEZ, gl(), "Netto", groesse=8.9)
            b.zeile(X_GES, gl(), betrag(Decimal(t["net"])), groesse=8.9, rechts=True)
            z += 1
            b.zeile(X_BEZ, gl(), "MwSt. 19 %", groesse=8.9)
            b.zeile(X_GES, gl(), betrag(Decimal(t["vat"])), groesse=8.9, rechts=True)
            z += 1
            b.zeile(X_BEZ, gl(), "Rechnungsbetrag", schrift=B, groesse=9.0, farbe=AKZENT)
            txt = betrag(Decimal(t["gross"]))
            b.zeile(X_GES, gl(), txt, schrift=B, groesse=9.3, farbe=AKZENT, rechts=True)
            x0 = X_GES - pdfmetrics.stringWidth(txt, B, 9.3)
            for off in (1.99, 4.09):
                b.linie(x0, gl() + off, X_GES, 0.55, AKZENT)
        c.showPage()
    c.save()


# ------------------------------------------------------------------ Soll
def de(d: date, kurz=False) -> str:
    return d.strftime("%d.%m.%y" if kurz else "%d.%m.%Y")


def beleg(n: int, s: Spez, rng: random.Random, datum: date) -> tuple[dict, list[Pos], list[Seite]]:
    namen, strasse, plz, ort, kdnr = KUNDEN[s.kunde]
    name_lines = list(namen) + list(s.zusatz)
    assert 1 <= len(name_lines) <= 3, name_lines
    ps = positionen(rng, s)
    detail = {}
    if s.fehler == "zeile":                      # Zahlendreher im Gesamtpreis einer Position mit Preis
        k = rng.choice([i for i, p in enumerate(ps) if p.art == "regular" and p.gesamt >= 10])
        richtig = ps[k].gesamt
        ziffern = list(f"{richtig:.2f}".replace(".", ""))
        j = next(j for j in range(len(ziffern) - 1) if ziffern[j] != ziffern[j + 1] and (j or ziffern[1] != "0"))
        ziffern[j], ziffern[j + 1] = ziffern[j + 1], ziffern[j]
        ps[k].gesamt_druck = Decimal("".join(ziffern)) / 100
        detail = {"position": k + 1, "gedruckt": f"{ps[k].gesamt:.2f}", "berechnet": f"{richtig:.2f}"}
    seiten = umbruch(ps, s.vortrag)
    netto = sum((p.gesamt or Decimal(0)) for p in ps)
    ust = cent(netto * Decimal("0.16" if s.fehler == "ust_betrag" else "0.19"))
    brutto = netto + ust
    faellig = datum + timedelta(days=30)
    if s.fehler == "faelligkeit_vor_datum":      # Tippfehler im Jahr: Vorjahr
        faellig = faellig.replace(year=faellig.year - 1)
    nummer = f"FA-26-{10300 + n * 7 + rng.randint(0, 5)}"
    if s.skonto:
        sk_datum = datum + timedelta(days=s.skonto_tage)
        sk_betrag = cent(brutto * s.skonto / 100)
        text = [f"zahlbar bis {de(sk_datum, True)} bei {s.skonto} % Skonto ({betrag(sk_betrag)})",
                f"bis {de(faellig)} ohne Abzug"]
    else:
        sk_datum, sk_betrag = None, None
        text = [f"zahlbar bis {de(faellig)} ohne Abzug"]
    bestell = (rng.choice(["4500", "4700"]) + str(rng.randint(100000, 999999)) if rng.random() < 0.6
               else f"BE-26-{rng.randint(100, 999)}") if s.bestellung else ""
    verkaeufer = dict(VERKAEUFER)
    if s.fehler == "iban_pruefziffer":           # Prüfziffern vertauscht: DE71 → DE17
        i = verkaeufer["iban"]
        verkaeufer["iban"] = i[:2] + i[3] + i[2] + i[4:]
        detail = {"gedruckt": verkaeufer["iban"], "richtig": VERKAEUFER["iban"]}
    d = {
        "datei": f"Rechnung_{n:03d}_{nummer}.pdf",
        "format": "PDF 1.4 (reportlab, Schriften eingebettet)",
        "holdout": s.holdout,
        "seller": verkaeufer,
        "buyer": {"name_lines": name_lines, "street": strasse, "postal_code": plz, "city": ort,
                  "customer_number": kdnr},
        "invoice": {"number": nummer, "date": de(datum), "service_date": de(datum), "order_number": bestell,
                    "shipping": rng.choice(VERSAND)},
        "positions": [{"qty": p.qty, "unit": p.unit, "description": p.beschreibung,
                       "unit_price": None if p.preis is None else f"{p.preis:.2f}", "kind": p.art,
                       "price_unit": None if p.pe is None else f"/{p.pe}",
                       "price_unit_qty": p.pe, "min_order": p.mindest,
                       "total": None if p.gesamt is None else f"{p.gesamt:.2f}"} for p in ps],
        "vat_rate": "19.00",
        "discount_percent": f"{s.skonto:.2f}" if s.skonto else None,
        "discount_days": s.skonto_tage if s.skonto else None,
        "payment_days": 30,
        "totals": {"net": f"{netto:.2f}", "vat": f"{ust:.2f}", "gross": f"{brutto:.2f}"},
        "payment": {"discount_date": de(sk_datum) if sk_datum else None, "due_date": de(faellig),
                    "discount_amount": f"{sk_betrag:.2f}" if sk_betrag is not None else None,
                    "discount_base": "gross" if s.skonto else None},
        "payment_terms_text": text,
        "page_count": len(seiten),
        "pages": [{"page": se.nr, "position_indices": [i + 1 for i in se.pos], "line_count": se.zeilen,
                   "transfer": None if se.uebertrag is None else f"{se.uebertrag:.2f}",
                   "carry_forward": None if se.vortrag is None else f"{se.vortrag:.2f}",
                   "summary_present": se.summen, "payment_block_present": se.nr == 1} for se in seiten],
        "test_flags": {
            "address_name_lines": len(name_lines),
            "address_blank_lines": s.leer,
            "address_attention_line": any(z.startswith("z. Hd.") for z in name_lines),
            "address_department_line": any(z.startswith("Abteilung") for z in name_lines),
            "two_line_company_name": len(namen) == 2,
            "missing_order_number": not s.bestellung,
            "shipping_empty": False,
            "discount_applied": bool(s.skonto),
            "blank_unit_flat_rate": any(p.art == "flat_rate" and not p.unit for p in ps),
            "without_price_count": sum(p.art == "without_price" for p in ps),
            "flat_rate_count": sum(p.art == "flat_rate" for p in ps),
            "min_order": s.mindest,
            "price_unit_100_count": sum(p.pe == 100 for p in ps),
            "two_three_line_positions": sum(2 <= len(p.beschreibung) <= 3 for p in ps),
            "four_five_line_positions": sum(4 <= len(p.beschreibung) <= 5 for p in ps),
            "has_qty_thousands": any(p.qty >= 1000 for p in ps),
            "carry_forward": s.vortrag,
            "last_table_row_index": None,
            "note": s.notiz,
        },
    }
    d["test_flags"]["shipping_empty"] = d["invoice"]["shipping"] == ""
    if s.fehler or s.falle:
        a1_zusatz(d, ps, s, nummer, datum, faellig, netto, detail)
    return d, ps, seiten


def a1_zusatz(d: dict, ps: list[Pos], s: Spez, nummer: str, datum: date, faellig: date, netto: Decimal,
              detail: dict):
    """Soll-Felder der A1-Hold-out-Belege (Fehler/Falle). Das Soll enthält, was gedruckt ist."""
    netto_r = sum((p.gesamt_berechnet or Decimal(0)) for p in ps)
    ust_r = cent(netto_r * Decimal("0.19"))
    hinweise, folge = [], []
    if s.fehler == "zeile":
        hinweise = [f"PRUEFEN [BT-131] Pos {detail['position']}: Menge × Preis ÷ Preiseinheit = "
                    f"{betrag(Decimal(detail['berechnet']))}, gedruckt {betrag(Decimal(detail['gedruckt']))}"]
        folge = ["PRUEFEN [BT-109] Kontrollwert der Quelle ≠ berechnet (gedrucktes Netto enthält den falschen "
                 "Zeilenbetrag)"]
    elif s.fehler == "ust_betrag":
        hinweise = [f"PRUEFEN [BT-110] Kontrollwert der Quelle ≠ berechnet (gedruckte MwSt. "
                    f"{betrag(Decimal(d['totals']['vat']))} = 16 %, richtig 19 % = {betrag(ust_r)})"]
        folge = ["PRUEFEN [BT-112] Kontrollwert der Quelle ≠ berechnet (Brutto folgt der gedruckten MwSt.)"]
    elif s.fehler == "iban_pruefziffer":
        hinweise = [f"FEHLER [BT-84] IBAN (BT-84) „{d['seller']['iban']}“ ist ungültig (Prüfsumme oder Länge "
                    "stimmt nicht)."]
    elif s.fehler == "faelligkeit_vor_datum":
        hinweise = [f"FEHLER [BT-9] Fälligkeitsdatum (BT-9) {de(faellig)} liegt vor dem Rechnungsdatum."]
        d["payment_days"] = None
        detail = {"faellig_gedruckt": de(faellig), "rechnungsdatum": de(datum)}
    if s.falle == "lieferschein_nr":
        detail = {"lieferschein_nr": "LS-26-" + str(int(nummer[-5:]) - 9)}
    elif s.falle == "hinweis_betrag":
        detail = {"hinweis": "Hinweis: Ab einem Bestellwert von 250,00 € netto liefern wir frachtfrei."}
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
        "totals_berechnet": {"net": f"{netto_r:.2f}", "vat": f"{ust_r:.2f}", "gross": f"{netto_r + ust_r:.2f}"},
    })


def selbstcheck(d: dict, ps: list[Pos], seiten: list[Seite], s: Spez):
    nr = d["invoice"]["number"]
    netto, ust, brutto = (Decimal(d["totals"][k]) for k in ("net", "vat", "gross"))
    falsch = 0
    for p in ps:
        if p.preis is not None:
            falsch += p.gesamt != cent(p.qty * p.preis / p.pe)
            assert p.preis > 0 and p.qty > 0
    assert falsch == (s.fehler == "zeile"), f"{nr}: {falsch} falsche Zeilenbeträge"
    assert sum((p.gesamt or 0) for p in ps) == netto, f"{nr}: Σ Positionen ≠ Netto"
    assert (cent(netto * Decimal("0.19")) == ust) == (s.fehler != "ust_betrag"), f"{nr}: USt"
    assert netto + ust == brutto, f"{nr}: Netto + USt ≠ Brutto"
    from fakturafalter.pflichtpruefung import iban_gueltig, ust_id_de_gueltig
    assert iban_gueltig(d["seller"]["iban"]) == (s.fehler != "iban_pruefziffer"), f"{nr}: IBAN"
    assert ust_id_de_gueltig(d["seller"]["ust_id"]), f"{nr}: USt-IdNr."
    re_datum = date(*reversed([int(x) for x in d["invoice"]["date"].split(".")]))
    faellig = date(*reversed([int(x) for x in d["payment"]["due_date"].split(".")]))
    assert (faellig < re_datum) == (s.fehler == "faelligkeit_vor_datum"), f"{nr}: Fälligkeit"
    assert not (s.fehler and s.falle) and (s.fehler is None or s.fehler in FEHLERARTEN)
    assert (s.falle is None or s.falle in FALLEN) and (s.holdout or not (s.fehler or s.falle))
    if s.skonto:
        assert Decimal(d["payment"]["discount_amount"]) == cent(brutto * s.skonto / 100), f"{nr}: Skonto"
    assert len(seiten) == s.seiten, f"{nr}: {len(seiten)} Seiten statt {s.seiten}"
    assert sorted(i for se in seiten for i in se.pos) == list(range(len(ps))), nr
    kum = Decimal(0)
    for se in seiten:
        if se.vortrag is not None:
            assert se.vortrag == kum, f"{nr}: Vortrag"
        kum += sum((ps[i].gesamt or 0) for i in se.pos)
        if se.uebertrag is not None:
            assert se.uebertrag == kum, f"{nr}: Übertrag"
    assert kum == netto
    # Zeilen pro Seite in den Grenzen des Layouts
    for se in seiten:
        start = 1 if se.vortrag is not None else 0
        ende = start + se.zeilen + (2 if se.summen else 0)   # Index der letzten Zeile (Übertrag = start+zeilen)
        assert ende <= (S1_LETZTE if se.nr == 1 else SN_LETZTE), f"{nr}: Seite {se.nr} zu lang"
    d["test_flags"]["last_table_row_index"] = ende
    if s.mindest:
        assert any(p.art == "flat_rate" and p.mindest for p in ps)


def zurueckgelesen(pdf: Path, d: dict):
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        assert len(doc.pages) == d["page_count"], pdf.name
        texte = [p.extract_text() or "" for p in doc.pages]
    alle = "\n".join(texte)
    for t in d["payment_terms_text"]:
        assert t in texte[0], (pdf.name, t)
    assert betrag(Decimal(d["totals"]["gross"])) in texte[-1], pdf.name
    assert d["invoice"]["number"] in texte[0] and "MwSt. 19 %" in texte[-1]
    for se in d["pages"]:
        if se["transfer"]:
            assert "Übertrag " + betrag(Decimal(se["transfer"])) in texte[se["page"] - 1], pdf.name
        if se["carry_forward"]:
            assert "Vortrag " + betrag(Decimal(se["carry_forward"])) in texte[se["page"] - 1], pdf.name
    for z in d["buyer"]["name_lines"]:
        assert z in alle
    assert all(f"IBAN: {d['seller']['iban']}" in t for t in texte), pdf.name
    for v in (d.get("falle_detail") or {}).values():
        assert v in texte[0], (pdf.name, v)


MATRIX = ["Datei", "Holdout", "Rechnungsnummer", "Rechnungsdatum", "Kundennummer", "Kunde", "Namenszeilen",
          "Leerzeilen", "Seiten", "Positionen", "Positionszeilen", "Ohne_Preis", "Pauschalen", "PE_100",
          "Mehrzeilig", "Bestellnummer", "Skonto_Prozent", "Skonto_Betrag", "Netto", "MwSt_19", "Brutto",
          "Uebertraege", "Vortraege", "Letzte_Tabellenzeile", "Notiz", "SHA256"]


def main():
    rng = random.Random(SEED)
    rech, ref = HIER / "Rechnungen", HIER / "Referenzdaten"
    for o in (rech, ref):
        if o.exists():
            shutil.rmtree(o)
    (ref / "holdout").mkdir(parents=True)
    rech.mkdir()
    datum = date(2026, 10, 1)
    zeilen = []
    for n, s in enumerate(SPEZ, start=1):
        datum += timedelta(days=rng.choice([0, 1, 1, 2]))
        while datum.weekday() >= 5:
            datum += timedelta(days=1)
        d, ps, seiten = beleg(n, s, rng, datum)
        selbstcheck(d, ps, seiten, s)
        pdf = rech / d["datei"]
        zeichnen(pdf, d, ps, seiten)
        zurueckgelesen(pdf, d)
        d["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        ziel = (ref / "holdout" if s.holdout else ref) / (pdf.stem + ".json")
        ziel.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tf = d["test_flags"]
        zeilen.append([d["datei"], "ja" if s.holdout else "", d["invoice"]["number"], d["invoice"]["date"],
                       d["buyer"]["customer_number"], " | ".join(d["buyer"]["name_lines"]),
                       len(d["buyer"]["name_lines"]),
                       s.leer, d["page_count"], len(ps), sum(len(p.beschreibung) for p in ps),
                       tf["without_price_count"], tf["flat_rate_count"], tf["price_unit_100_count"],
                       sum(len(p.beschreibung) > 1 for p in ps), d["invoice"]["order_number"],
                       s.skonto or "", d["payment"]["discount_amount"] or "", d["totals"]["net"], d["totals"]["vat"],
                       d["totals"]["gross"], " ".join(p["transfer"] for p in d["pages"] if p["transfer"]),
                       " ".join(p["carry_forward"] for p in d["pages"] if p["carry_forward"]),
                       tf["last_table_row_index"], s.notiz, d["sha256"]])
        print(f"{d['datei']:34s} {d['page_count']} S. {len(ps):2d} Pos. "
              f"letzte Zeile {tf['last_table_row_index']:2d} {'Hold-out' if s.holdout else ''}")
    with open(ref / "Testfallmatrix.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(MATRIX)
        w.writerows(zeilen)
    print(f"{len(zeilen)} Belege, davon {sum(s.holdout for s in SPEZ)} Hold-out. Selbstcheck ok.")


if __name__ == "__main__":
    main()
