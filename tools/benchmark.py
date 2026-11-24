# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Erkennungs-Benchmark: Trefferquote je Feld über alle Beispiel-PDFs und einen festen Satz erzeugter Drucke.

Drei Verfahren, jedes gegen Sollwerte (Beträge exakt auf den Cent):

* ``assistent`` – Anlern-Assistent ohne Vorlage (Kaltstart): Vorschläge von ``anlernen.Sitzung``.
  Quellen: ``beispiele/pdf-erkennung`` (Soll: CSV), ``beispiele/industrie`` (Soll: CSV), ``beispiele/poc``
  (Soll: CSV) und ``generator`` (``tests/erp_roh.py`` mit Layout-Varianten, Soll: Erzeugungsdaten, Seed fest).
* ``angelernt`` – je Verkäufer die ersten N Paare PDF + CSV anlernen (``pdferkennung.pruefen_und_lernen``), dann
  die übrigen PDFs „Nur PDF“ (``pdferkennung.nur_pdf``) lesen und mit der CSV vergleichen.
* ``handvorlage`` – mitgelieferte Hand-Vorlagen (``adapter_pdf.lesen``): WaWi-Druckauftrag und PoC.
* ``fiktiv-*`` – 50 fiktive Rechnungen mit JSON-Sollwerten (``tests/daten/fiktiv``, Pfad mit ``--fiktiv``):
  ``fiktiv-kaltstart`` (Assistent ohne Eingriff), ``fiktiv-korrigiert`` (Assistent plus die übliche
  Nutzerkorrektur: Tabellenrahmen auf Seite 1 ziehen, Spalte „Gesamtpreis“ als Gesamt wählen) und
  ``fiktiv-angelernt`` (die ersten N mit Tabellenrahmen und den Soll-Werten als Nutzerkorrektur anlernen,
  die übrigen „Nur PDF“). Zusätzlich je Beleg die
  Prüfhinweise der Pflichtprüfung (Einheit fehlt, Zahlungsbedingung fehlt, Summenabweichung).
  Die USt-IdNr. des Absenders ist in diesen Drucken absichtlich falsch: sie wird nicht bewertet, der Hinweis
  dazu (BT-31) nicht gezählt.
* Testsets ``beispiele/sets/<name>`` (oder ``--set ORDNER``): dieselben drei Verfahren als ``<name>-…``,
  Belege unter ``Referenzdaten/holdout/`` getrennt als ``<name>-… (Hold-out)``. Optionale Sollfelder
  ``payment_terms_text`` (BT-20) und ``price_unit_qty`` (Preiseinheit) werden gewertet, wenn vorhanden. Anschrift
  nach der festen Regel: alle Namenszeilen in BT-44 (Name + Zusatz), BT-51 wird nicht gewertet. Ist ein
  ``--set``-Ordner selbst kein Testset, laufen alle Testsets darunter (rekursiv) als Familien; dazu kommt eine
  Tabelle je Familie, gesamt und Hold-out gesamt. Hat das Set ein ``MANIFEST.json`` (Version, Rolle je Beleg),
  gelten die Rollen ``anlernen``, ``nachlesen``, ``holdout``, ``holdout-fehler`` und ``holdout-falle``;
  Fehler- und Fallenbelege werden getrennt ausgewiesen, Belege mit ``ausserhalb_v1`` nicht in der v1-Quote.
  Soll-Summen sind die berechneten Werte (``totals_berechnet``, sonst ``totals``); weicht der Druck ab, ist das
  der erwartete Prüf-Anlass. ``--lernen N`` lernt auf genau N Trainingsbelegen, wenn danach
  noch Belege (Rest, Nachlesen oder Hold-out) zu messen sind.

Offline, deterministisch, ohne OCR; angelernte Vorlagen und erzeugte PDFs landen nur im Temp-Ordner.
Absichtliche Fehlerfälle (``beispiele/pdf-erkennung/fehlerfaelle``) sind nicht dabei.

    python tools/benchmark.py                       # Tabelle + Fehlschläge auf der Konsole
    python tools/benchmark.py --md ergebnis.md --json ergebnis.json
    python tools/benchmark.py --generator 20 --seed 7 --verfahren assistent
    python tools/benchmark.py --verfahren fiktiv-korrigiert fiktiv-angelernt --fiktiv /pfad/zu/testdaten
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import random
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
for p in (WURZEL / "src", WURZEL):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fakturafalter import (  # noqa: E402
    adapter_csv,
    adapter_pdf,
    anlernen,
    pdferkennung,
    pflichtpruefung,
    pipeline,
    rechnen,
)
from fakturafalter.konfig import lade_konfig  # noqa: E402
from fakturafalter.modell import Position, Steuer  # noqa: E402

BEISPIELE = WURZEL / "beispiele"
PE = BEISPIELE / "pdf-erkennung"
FIKTIV = WURZEL / "tests" / "daten" / "fiktiv"
VERFAHREN = [
    "assistent",
    "angelernt",
    "handvorlage",
    "fiktiv-kaltstart",
    "fiktiv-korrigiert",
    "fiktiv-angelernt",
]

KOPFFELDER = [
    "BT-1",
    "BT-2",
    "leistung",
    "BT-44",
    "BT-51",
    "BT-50",
    "BT-53",
    "BT-52",
    "kundennummer",
    "BT-13",
    "BT-20",
    "BT-109",
    "BT-110",
    "BT-112",
    "BT-119",
]
ABSENDERFELDER = ["Absender.name", "Absender.ust_id", "Absender.steuernummer", "Absender.iban"]
FREIWILLIG = {"BT-13", "kundennummer", "BT-51"}  # fehlen in mancher CSV, obwohl sie im Druck stehen
POSFELDER = [
    "Pos.anzahl",
    "Pos.menge",
    "Pos.einzelpreis",
    "Pos.preiseinheit",
    "Pos.gesamt",
    "Pos.bezeichnung",
]
FELDNAMEN = {
    "BT-1": "Rechnungsnummer",
    "BT-2": "Rechnungsdatum",
    "leistung": "Leistung (BT-72/BG-14)",
    "BT-44": "Kunde",
    "BT-51": "Adresszusatz",
    "BT-163": "Adresszeile 3",
    "BT-56": "Kontaktstelle (z. Hd.)",
    "BT-50": "Straße",
    "BT-53": "PLZ",
    "BT-52": "Ort",
    "kundennummer": "Kundennummer",
    "BT-13": "Bestellnummer",
    "BT-20": "Zahlungsbedingung",
    "BT-109": "Netto",
    "BT-110": "USt",
    "BT-112": "Brutto",
    "BT-119": "Steuersatz",
    "Pos.anzahl": "Positionen: Anzahl",
    "Pos.menge": "Pos.: Menge",
    "Pos.einzelpreis": "Pos.: Einzelpreis",
    "Pos.preiseinheit": "Pos.: Preiseinheit",
    "Pos.gesamt": "Pos.: Gesamt",
    "Pos.bezeichnung": "Pos.: Bezeichnung",
    "Pos.einheit": "Pos.: Einheit (Code)",
    "Pos.steuersatz": "Pos.: Steuersatz (nur Belege mit mehreren Sätzen)",
    "Absender.name": "Absender: Name",
    "Absender.ust_id": "Absender: USt-IdNr.",
    "Absender.steuernummer": "Absender: Steuernummer",
    "Absender.iban": "Absender: IBAN",
    "BT-9": "Fälligkeit (BT-9)",
    "skonto": "Skonto im BT-20",
}


# ---------------------------------------------------------------- Datenmodell des Vergleichs
@dataclass
class Beleg:
    """Soll oder Ist eines Belegs, flach: Kopffelder und Positionen als Dicts."""

    kopf: dict = field(default_factory=dict)
    positionen: list[dict] = field(default_factory=list)
    pruefen: set = field(
        default_factory=set
    )  # Felder mit Status/Hinweis „prüfen“ („Pos“ = Positionen)
    beleg_pruefen: bool = False  # irgendein Hinweis „prüfen“/„fehler“: Beleg geht nicht still durch


@dataclass
class Fall:
    verfahren: str
    quelle: str
    datei: str
    soll: Beleg
    ist: Beleg | None  # None = nicht gelesen (z. B. Nur PDF abgelehnt, Ausnahme)
    grund: str = ""
    felder: list[str] = field(default_factory=list)  # zu bewertende Kopffelder
    posfelder: list[str] = field(default_factory=list)
    soll_vollstaendig: bool = (
        False  # Generator: Soll kennt jedes Feld; CSV: freiwillige Felder evtl. nicht exportiert
    )
    hinweise: list[str] | None = None  # fiktiv: Prüfhinweise der erkannten Rechnung (ohne BT-31)
    gruppe: str = ""  # Testset-Gruppe mit Familien (--set auf einen Ordner über den Familien)
    rolle: str = ""  # MANIFEST-Rolle (anlernen, holdout, holdout-fehler, holdout-falle, nachlesen)
    ausserhalb_v1: bool = False
    erwarteter_status: str = ""  # ok / prüfen / fehler
    erwartete_hinweise: list[str] = field(default_factory=list)


def _text(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _leer(v) -> bool:
    return v is None or v == "" or v == [] or v == ()


def _dez(v) -> Decimal | None:
    return None if v is None else Decimal(v)


def _gleich(feld: str, soll, ist) -> bool:
    if feld in ("BT-20", "skonto"):  # Druck darf mehr enthalten (z. B. zweisprachig)
        return bool(soll) and _text(soll).lower().rstrip(".") in _text(ist).lower()
    if feld in ("Absender.ust_id", "Absender.steuernummer", "Absender.iban"):
        return pdferkennung.kompakt(soll or "") == pdferkennung.kompakt(ist or "")
    if isinstance(soll, str) or isinstance(ist, str):
        return _text(soll) == _text(ist)
    return soll == ist


def _zeigen(v) -> str:
    if v is None or v == "":
        return "–"
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, tuple):
        return " – ".join(_zeigen(x) for x in v)
    if isinstance(v, list):
        return ", ".join(_zeigen(x) for x in v) or "–"
    if isinstance(v, Decimal):
        return format(v.normalize() if v == v.to_integral() else v, "f")
    return _text(v)


# ---------------------------------------------------------------- Soll / Ist aus Rechnung und Sitzung
def _leistung(r) -> object:
    if r.leistung_von or r.leistung_bis:
        return (r.leistung_von, r.leistung_bis)
    return r.leistungsdatum


def _saetze(positionen) -> list[Decimal]:
    return sorted(
        {
            Decimal(p.steuer.satz).normalize()
            for p in positionen
            if p.steuer and p.steuer.satz is not None
        }
    )


def _satz(p) -> Decimal | None:
    return Decimal(p.steuer.satz).normalize() if p.steuer and p.steuer.satz is not None else None


def aus_rechnung(r, summen_aus_kontrolle: bool = False) -> Beleg:
    """Beleg aus einer Rechnung (CSV-Soll oder Nur-PDF-Ergebnis); Summen nach ``rechnen.berechnen``."""
    rechnen.berechnen(r)
    a = r.kaeufer.anschrift
    kopf = {
        "BT-1": r.nummer,
        "BT-2": r.datum,
        "leistung": _leistung(r),
        "BT-44": r.kaeufer.name,
        "BT-51": a.zusatz,
        "BT-163": a.zeile3,
        "BT-56": r.kaeufer.kontakt_name,
        "BT-50": a.strasse,
        "BT-53": a.plz,
        "BT-52": a.ort,
        "kundennummer": r.kundennummer,
        "BT-13": r.bestellnummer,
        "BT-20": r.zahlung.bedingungen,
        "BT-9": r.zahlung.faellig,
        "skonto": r.zahlung.bedingungen,
        "BT-109": r.summen.netto,
        "BT-110": r.summen.ust,
        "BT-112": r.summen.brutto,
        "BT-119": _saetze(r.positionen),
    }
    if summen_aus_kontrolle:
        for f in ("BT-109", "BT-110", "BT-112"):
            if f in r.kontrolle:
                kopf[f] = r.kontrolle[f]
    pos = [
        {
            "menge": p.menge,
            "einzelpreis": p.einzelpreis,
            "preiseinheit": p.preiseinheit or Decimal(1),
            "gesamt": p.netto,
            "bezeichnung": p.bezeichnung,
            "einheit": p.einheit,
            "steuersatz": _satz(p),
        }
        for p in r.positionen
    ]
    b = Beleg(kopf, pos)
    _pruefen_aus_hinweise(b, r.hinweise)
    return b


_FELD_ALIAS = {
    "BT-72": "leistung",
    "BT-73": "leistung",
    "BT-74": "leistung",
    "BT-153": "Pos",
    "BT-129": "Pos",
    "BT-146": "Pos",
    "BT-131": "Pos",
    "BT-130": "Pos",
    "BT-149": "Pos",
    "BT-152": "BT-119",
}


def _pruefen_aus_hinweise(b: Beleg, hinweise) -> None:
    for h in hinweise:
        if getattr(h, "stufe", "") in ("pruefen", "fehler") and "BT-31" not in str(h):
            b.beleg_pruefen = True
            if h.feld:
                b.pruefen.add(_FELD_ALIAS.get(h.feld, h.feld))


def absender_soll(profil: dict) -> dict:
    vk, zb = profil.get("verkaeufer") or {}, profil.get("zahlung") or {}
    return {
        "Absender.name": vk.get("name", ""),
        "Absender.ust_id": vk.get("ust_id", ""),
        "Absender.steuernummer": vk.get("steuernummer", ""),
        "Absender.iban": zb.get("iban", ""),
    }


def aus_sitzung(s: anlernen.Sitzung) -> Beleg:
    kopf = {}
    for f in KOPFFELDER:
        try:
            v = s.wert(f)
        except Exception as e:  # Wert lässt sich nicht lesen -> Fehlschlag mit Grund
            v = f"<{type(e).__name__}: {e}>"
        if f == "BT-119":
            v = [] if v is None else [Decimal(v).normalize()]
        kopf[f] = v
    ab = s.absender
    kopf.update(
        {
            "Absender.name": ab.name,
            "Absender.ust_id": ab.ust_id,
            "Absender.steuernummer": ab.steuernummer,
            "Absender.iban": ab.iban,
        }
    )
    pos = [
        {
            "menge": p.menge,
            "einzelpreis": p.einzelpreis,
            "preiseinheit": p.preiseinheit or Decimal(1),
            "gesamt": p.gesamt,
            "bezeichnung": p.bezeichnung,
        }
        for p in s.positionen()
    ]
    b = Beleg(kopf, pos)
    b.pruefen = {f for f, v in s.werte.items() if v.status == "pruefen"}
    try:
        if s.tabelle_fehlt() or not s.summenpruefung()[2]:
            b.pruefen.add("Pos")
    except Exception:
        b.pruefen.add("Pos")
    return b


# ---------------------------------------------------------------- Konfigurationen und Quellen
def _konfig(pfad: Path, tmp: Path):
    k = lade_konfig(pfad)
    for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen"):
        setattr(k, n, tmp / "laufzeit" / n)
    return k


def _profil(k, name: str) -> dict:
    return next(p for p in k.csv_profile if pdferkennung.profil_name(p) == name)


def _csv_soll(csv: Path, profil: dict, k) -> list:
    return adapter_csv.lesen(csv, profil, k)


def beispiel_paare() -> list[tuple[str, str, Path, Path, Path]]:
    """-> [(Quelle, Profilname, Konfiguration, CSV, PDF)] aller Beispielpaare, sortiert."""
    out = []
    for csv in sorted((PE / "eingang").glob("*.csv")):
        kurz, nr = csv.stem.split("_", 1)
        out.append(
            ("pdf-erkennung", kurz, PE / "konfiguration.yaml", csv, PE / "eingang" / f"{nr}.pdf")
        )
    ind = BEISPIELE / "industrie"
    for csv in sorted((ind / "eingang").glob("*.csv")):
        nr = csv.stem.split("_", 1)[1]
        out.append(
            (
                "industrie",
                "normteile",
                ind / "konfiguration-pdf-csv.yaml",
                csv,
                ind / "eingang" / f"{nr}.pdf",
            )
        )
    poc = BEISPIELE / "poc"
    out.append(
        (
            "poc",
            "poc-tischlerei",
            poc / "konfiguration.yaml",
            poc / "TM-2026-0042.csv",
            poc / "TM-2026-0042.pdf",
        )
    )
    return [p for p in out if p[4].exists()]


# ---------------------------------------------------------------- Generator (tests/erp_roh.py)
ANSCHRIFTEN = [  # (Zeilen im Anschriftfeld, Soll)
    (
        None,
        dict(
            name="Beispiel Werkzeugbau GmbH",
            strasse="Musterweg 12",
            zusatz="",
            plz="12345",
            ort="Musterstadt",
        ),
    ),
    (
        ["Hofmann Antriebstechnik KG", "Industriestraße 7a", "", "70565 Stuttgart"],
        dict(
            name="Hofmann Antriebstechnik KG",
            strasse="Industriestraße 7a",
            zusatz="",
            plz="70565",
            ort="Stuttgart",
        ),
    ),
    (
        ["Stadtwerke Nordheim GmbH", "Abteilung Einkauf", "Am Wasserturm 3", "01067 Dresden"],
        dict(
            name="Stadtwerke Nordheim GmbH",
            strasse="Am Wasserturm 3",
            zusatz="Abteilung Einkauf",
            plz="01067",
            ort="Dresden",
        ),
    ),
    (
        ["Alpen Maschinen GmbH", "Innrain 15", "", "6020 Innsbruck"],
        dict(
            name="Alpen Maschinen GmbH",
            strasse="Innrain 15",
            zusatz="",
            plz="6020",
            ort="Innsbruck",
        ),
    ),
    (
        ["Alpen Maschinen GmbH", "Innrain 15", "", "A-6020 Innsbruck"],
        dict(
            name="Alpen Maschinen GmbH",
            strasse="Innrain 15",
            zusatz="",
            plz="6020",
            ort="Innsbruck",
        ),
    ),
    (
        ["Seefeld Präzision AG", "Bahnhofstrasse 40", "", "8001 Zürich"],
        dict(
            name="Seefeld Präzision AG",
            strasse="Bahnhofstrasse 40",
            zusatz="",
            plz="8001",
            ort="Zürich",
        ),
    ),
]
ARTIKEL = [
    ("Stk", "Sechskantschraube M10x60 DIN 933"),
    ("Std", "Montage vor Ort"),
    ("ST", "Werkzeugwagen Typ C"),
    ("m", "Hydraulikschlauch DN12"),
    ("kg", "Rundstahl S355 Ø 30"),
    ("Stk", "Kugellager 6204-2RS"),
    ("Std", "Fahrtzeit Techniker"),
    ("ST", "Prüfprotokoll nach DGUV V3"),
    ("Stk", "Dichtring 40x52x7 NBR"),
    ("psch", "Anfahrtspauschale"),
]
LAYOUTS = [
    "ohne_trennlinie",
    "linie_gezeichnet",
    "trennlinie_minus",
    "trennlinie_gleich",
    "trennlinie_unterstrich",
    "leerzeilen_nach_kopf",
    "falzmarken",
    "falzmarke_linie_leerzeilen",
    "kopf_versatz",
    "preiseinheit",
    "mehrseitig",
]
NETTOWORTE = ["Nettobetrag", "Zwischensumme", "Warenwert", "Summe netto"]


def _de(d: Decimal, stellen: int = 2) -> str:
    s = f"{d:,.{stellen}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _cent(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")


ANSCHRIFT_GEWICHTE = [4, 3, 3, 1, 1, 1]


def generator_belege(anzahl: int, seed: int) -> list[dict]:
    """Fester, seed-basierter Satz Druckbeschreibungen (ohne Datei)."""
    rnd = random.Random(seed)
    belege = []
    for i in range(anzahl):
        layout = LAYOUTS[i % len(LAYOUTS)]
        # überwiegend DE-Anschriften; AT/CH je ein Gewicht, damit sie die Quote nicht dominieren
        adr_zeilen, adr = rnd.choices(ANSCHRIFTEN, weights=ANSCHRIFT_GEWICHTE)[0]
        n = rnd.randint(2, 7) if layout != "mehrseitig" else rnd.randint(6, 9)
        pos = []
        for me, bez in rnd.sample(ARTIKEL, n):
            menge = (
                Decimal(rnd.choice([1, 2, 3, 5, 10, 12, 25, 100])) if me != "psch" else Decimal(1)
            )
            if me in ("Std", "m", "kg") and rnd.random() < 0.5:
                menge = Decimal(rnd.randint(5, 95)) / 2
            pe = Decimal(100) if layout == "preiseinheit" and me == "Stk" else Decimal(1)
            preis = Decimal(rnd.randint(50, 250000)) / 100
            gesamt = _cent(menge * preis / pe)
            pos.append(
                dict(
                    me=me,
                    bezeichnung=bez,
                    menge=menge,
                    einzelpreis=preis,
                    preiseinheit=pe,
                    gesamt=gesamt,
                )
            )
        netto = sum((p["gesamt"] for p in pos), Decimal(0))
        ust = _cent(netto * Decimal("0.19"))
        belege.append(
            dict(
                nr=f"{i + 1:03d}-{layout}",
                layout=layout,
                beleg=str(26100000 + rnd.randint(0, 899999)),
                adr_zeilen=adr_zeilen,
                adr=adr,
                pos=pos,
                netto=netto,
                ust=ust,
                brutto=netto + ust,
                nettowort=rnd.choice(NETTOWORTE),
            )
        )
    return belege


def _menge_text(m: Decimal) -> str:
    return str(int(m)) if m == m.to_integral() else _de(m, 3)


def generator_pdf(b: dict, ordner: Path) -> Path:
    from tests import erp_roh

    lay = b["layout"]
    if lay == "preiseinheit":
        zeilen = [
            erp_roh.pos_pe(
                _menge_text(p["menge"]),
                p["me"],
                p["bezeichnung"],
                _de(p["einzelpreis"]),
                f"/{int(p['preiseinheit'])}" if p["preiseinheit"] != 1 else "",
                _de(p["gesamt"]),
            )
            for p in b["pos"]
        ]
    else:
        zeilen = [
            erp_roh.pos(
                _menge_text(p["menge"]),
                p["me"],
                p["bezeichnung"],
                _de(p["einzelpreis"]),
                _de(p["gesamt"]),
            )
            for p in b["pos"]
        ]
    nach = [
        " " * 50 + b["nettowort"].ljust(20) + _de(b["netto"]).rjust(12),
        " " * 50 + "USt 19 %".ljust(20) + _de(b["ust"]).rjust(12),
        " " * 50 + "Endbetrag".ljust(20) + _de(b["brutto"]).rjust(12),
    ]
    pfad = ordner / f"gen-{b['nr']}.pdf"
    if lay == "mehrseitig":
        h = len(zeilen) // 2
        return erp_roh.rechnung_mehrseitig(
            pfad, [zeilen[:h], zeilen[h:]], nach=nach, beleg=b["beleg"], uebertrag=""
        )
    kw: dict = dict(nach=nach, beleg=b["beleg"], anschrift=b["adr_zeilen"])
    t = erp_roh.trenn
    kw.update(
        {
            "linie_gezeichnet": dict(vektorlinie=True),
            "trennlinie_minus": dict(zeilen=[t("-")] + zeilen + [t("-")]),
            "trennlinie_gleich": dict(zeilen=[t("=")] + zeilen + [t("=")]),
            "trennlinie_unterstrich": dict(zeilen=[t("_")] + zeilen + [t("_")]),
            "leerzeilen_nach_kopf": dict(zeilen=[t("-"), "", ""] + zeilen, leer_nach_kopf=1),
            "falzmarken": dict(falzmarken=(281.7, 340.7)),
            "falzmarke_linie_leerzeilen": dict(
                falzmarken=(281.7, 352.7), vektorlinie=True, leer_nach_kopf=2
            ),
            "kopf_versatz": dict(kopf_versatz=6),
            "preiseinheit": dict(kopf=erp_roh.KOPF_PE),
        }.get(lay, {})
    )
    kw.setdefault("zeilen", zeilen)
    return erp_roh.rechnung(pfad, **kw)


def generator_soll(b: dict) -> Beleg:
    a = b["adr"]
    kopf = {
        "BT-1": b["beleg"],
        "BT-2": date(2026, 10, 5),
        "leistung": date(2026, 10, 5),
        "BT-44": a["name"],
        "BT-51": a["zusatz"],
        "BT-50": a["strasse"],
        "BT-53": a["plz"],
        "BT-52": a["ort"],
        "kundennummer": "",
        "BT-13": "",
        "BT-20": "Leistungsdatum = Rechnungsdatum, zahlbar bis 04.11.2026 ohne Abzug.",
        "BT-109": b["netto"],
        "BT-110": b["ust"],
        "BT-112": b["brutto"],
        "BT-119": [Decimal(19)],
    }
    if (
        b["layout"] == "mehrseitig"
    ):  # erp_roh.rechnung_mehrseitig druckt weder Anschrift noch Fußtext
        kopf.update(
            {f: "" for f in ("BT-44", "BT-51", "BT-50", "BT-53", "BT-52", "BT-20")}, leistung=None
        )
    pos = [
        {
            "menge": p["menge"],
            "einzelpreis": p["einzelpreis"],
            "preiseinheit": p["preiseinheit"],
            "gesamt": p["gesamt"],
            "bezeichnung": p["bezeichnung"],
        }
        for p in b["pos"]
    ]
    return Beleg(kopf, pos)


# ---------------------------------------------------------------- Verfahren
def _sitzung(pdf: Path, k) -> tuple[Beleg | None, str]:
    try:
        return aus_sitzung(anlernen.Sitzung(pdf, k)), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def lauf_assistent(tmp: Path, generator: int, seed: int) -> list[Fall]:
    faelle = []
    # Kaltstart: Konfiguration ohne PDF-Profile und ohne Standard-Absender
    k_kalt = _konfig(PE / "konfiguration.yaml", tmp)
    k_kalt.pdf_profile = []
    konfigs: dict[Path, object] = {}
    for quelle, prof, kpfad, csv, pdf in beispiel_paare():
        k = konfigs.setdefault(kpfad, _konfig(kpfad, tmp))
        profil = _profil(k, prof)
        soll_r = _csv_soll(csv, profil, k)
        soll = aus_rechnung(soll_r[0])
        soll.kopf.update(absender_soll(profil))
        ist, grund = _sitzung(pdf, k_kalt)
        faelle.append(
            Fall(
                "assistent",
                quelle,
                str(pdf.relative_to(WURZEL)),
                soll,
                ist,
                grund,
                KOPFFELDER + ABSENDERFELDER,
                POSFELDER,
            )
        )
    gen_ordner = tmp / "generator"
    gen_ordner.mkdir()
    for b in generator_belege(generator, seed):
        pdf = generator_pdf(b, gen_ordner)
        ist, grund = _sitzung(pdf, k_kalt)
        faelle.append(
            Fall(
                "assistent",
                "generator",
                f"generator/{pdf.name}",
                generator_soll(b),
                ist,
                grund,
                list(KOPFFELDER),
                list(POSFELDER),
                soll_vollstaendig=True,
            )
        )
    return faelle


def lauf_angelernt(tmp: Path, lernen: int, freigaben: dict) -> list[Fall]:
    """Je Profil die ersten ``lernen`` Paare anlernen, die übrigen nur aus dem PDF lesen."""
    faelle = []
    gruppen: dict[tuple[str, str], list] = {}
    for p in beispiel_paare():
        gruppen.setdefault((p[0], p[1]), []).append(p)
    for (quelle, prof), paare in sorted(gruppen.items()):
        if len(paare) <= lernen:
            continue
        k = _konfig(paare[0][2], tmp)
        profil = copy.deepcopy(_profil(k, prof))
        # Lesequalität messen, nicht die Freigabe: Nur PDF an, ab dem ersten Treffer „sicher“. Ob die Vorlage mit
        # der Voreinstellung (``nur_pdf_ab``) schon frei wäre, steht in ``freigabe``.
        ab = pdferkennung.einstellungen(profil)["nur_pdf_ab"]
        profil["pdf_erkennung"] = {
            **(profil.get("pdf_erkennung") or {}),
            "nur_pdf": True,
            "nur_pdf_ab": 1,
        }
        k.csv_profile = [profil]
        gelernt = 0
        for _, _, _, csv, pdf in paare[:lernen]:
            (r,) = _csv_soll(csv, profil, k)
            rechnen.berechnen(r)
            pdferkennung.pruefen_und_lernen(
                r, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), profil, pdf.name
            )
            gelernt += not any(h.stufe == "pruefen" for h in r.hinweise)
        folge = max(
            (
                int((v.get("statistik") or {}).get("folge_treffer", 0))
                for v in pdferkennung.vorlagen_laden(profil)
            ),
            default=0,
        )
        freigaben[f"{quelle}/{prof}"] = {
            "angelernt": lernen,
            "ohne_abweichung": gelernt,
            "folge_treffer": folge,
            "nur_pdf_ab": ab,
            "frei": folge >= ab,
        }
        for _, _, _, csv, pdf in paare[lernen:]:
            (soll_r,) = _csv_soll(csv, profil, k)
            soll = aus_rechnung(soll_r)
            try:
                ist_r, grund = pdferkennung.nur_pdf(
                    pdf, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), [profil], k
                )
                ist = aus_rechnung(ist_r, summen_aus_kontrolle=True) if ist_r else None
            except Exception as e:
                ist, grund = None, f"{type(e).__name__}: {e}"
            if ist is None:
                grund = f"{grund} (angelernt ohne Abweichung: {gelernt} von {lernen})"
            faelle.append(
                Fall(
                    "angelernt",
                    quelle,
                    str(pdf.relative_to(WURZEL)),
                    soll,
                    ist,
                    grund,
                    list(KOPFFELDER),
                    POSFELDER + ["Pos.einheit"],
                )
            )
    return faelle


def lauf_handvorlage(tmp: Path) -> list[Fall]:
    """Mitgelieferte Hand-Vorlagen (Zonen/Anker) gegen die CSV mit denselben Rechnungen."""
    faelle = []
    ohne_bt20 = [
        f for f in KOPFFELDER if f != "BT-20"
    ]  # Zahlungsbedingung kommt aus der Konfiguration
    kaeufer = {"BT-44", "BT-50", "BT-51", "BT-52", "BT-53"}
    for quelle, kpfad, vorlage_name, prof, pdf, csv, felder in [
        # WaWi: Käufer über Kundennummer aus dem Kundenstamm
        (
            "wawi-druck",
            BEISPIELE / "konfiguration.yaml",
            "vorlage-wawi-druck.yaml",
            "wawi-semikolon",
            BEISPIELE / "druckauftrag-wawi.pdf",
            BEISPIELE / "variante-b_wawi_cp1252.csv",
            ohne_bt20,
        ),
        # PoC: die Vorlage liest keinen Käufer (der kommt aus der CSV)
        (
            "poc",
            BEISPIELE / "poc" / "konfiguration.yaml",
            "vorlage-poc.yaml",
            "poc-tischlerei",
            BEISPIELE / "poc" / "TM-2026-0042.pdf",
            BEISPIELE / "poc" / "TM-2026-0042.csv",
            [f for f in ohne_bt20 if f not in kaeufer],
        ),
    ]:
        k = _konfig(kpfad, tmp)
        vorlage = next(v for v in k.pdf_vorlagen if Path(v["_datei"]).name == vorlage_name)
        try:
            ist_nr, grund = {r.nummer: r for r in adapter_pdf.lesen(pdf, vorlage, k)}, ""
        except Exception as e:
            ist_nr, grund = {}, f"{type(e).__name__}: {e}"
        soll_nr = {r.nummer: r for r in _csv_soll(csv, _profil(k, prof), k)}
        # Bewertet werden die Rechnungen, die im Druck stehen (die CSV kann mehr enthalten)
        nummern = sorted(n for n in soll_nr if n in ist_nr) if ist_nr else sorted(soll_nr)
        for nr in nummern:
            ist = aus_rechnung(ist_nr[nr], summen_aus_kontrolle=True) if nr in ist_nr else None
            faelle.append(
                Fall(
                    "handvorlage",
                    quelle,
                    f"{pdf.relative_to(WURZEL)}#{nr}",
                    aus_rechnung(soll_nr[nr]),
                    ist,
                    grund or "Rechnung nicht im Druck gefunden",
                    felder,
                    POSFELDER + ["Pos.einheit"],
                )
            )
    return faelle


# ---------------------------------------------------------------- Fiktive Testrechnungen (JSON-Sollwerte)
FIKTIV_FELDER = [
    "BT-1",
    "BT-2",
    "leistung",
    "BT-44",
    "BT-51",
    "BT-163",
    "BT-56",
    "BT-50",
    "BT-53",
    "BT-52",
    "kundennummer",
    "BT-13",
    "BT-9",
    "BT-20",
    "skonto",
    "BT-109",
    "BT-110",
    "BT-112",
    "BT-119",
    "Absender.name",
    "Absender.iban",
]  # USt-IdNr. des Absenders absichtlich falsch: nicht bewertet
FIKTIV_EINHEITEN = {"Stk.": "H87", "Std.": "HUR"}
HINWEISKLASSEN = [  # (Klasse, erkennt einen Hinweistext) – Klassen aus dem Verarbeitungsprotokoll
    ("Einheit fehlt (BT-130)", lambda t: "BT-130" in t),
    (
        "Zahlungsbedingung/Fälligkeit fehlt (BT-20/BT-9)",
        lambda t: "[BT-20]" in t and ("fehlen" in t or "fehlt" in t),
    ),
    ("Summenabweichung (Kontrollwert ≠ berechnet)", lambda t: "Kontrollwert der Quelle" in t),
]


def _datum(t: str) -> date | None:
    return datetime.strptime(t, "%d.%m.%Y").date() if t else None


# Zielabbildung der Käufer-Namenszeilen (Nutzer-Entscheid 23.11.2026, unabhängig vom Produktcode nachgebaut):
# Namenszeilen zuerst, dann Vermerkzeilen nach DIN 5008 – „z. Hd./z. H./zu Händen/Attn.“ -> BT-56 (ohne Vermerk),
# „Abteilung/Abt./c/o/Gebäude“ -> BT-51, die zweite -> BT-163. Sonst (auch im Zweifel) alles BT-44.
_SOLL_KONTAKT = re.compile(r"^(?:z\.\s?hd\.?|z\.\s?h\.|zu\s+händen|attn\.?:?)(?=\s|$)\s*", re.I)
_SOLL_ZUSATZ = re.compile(r"^(?:abteilung|abt\.|c/o|gebäude)(?=\s|$)", re.I)


def kaeufer_ziel(zeilen: list[str]) -> dict[str, str]:
    """Namenszeilen über der Straße -> {BT-44, BT-51, BT-163, BT-56} nach der Zielabbildung."""
    name, zusatz, kontakt = [], [], []
    for t in (" ".join(z.split()) for z in zeilen):
        if _SOLL_KONTAKT.match(t):
            kontakt.append(_SOLL_KONTAKT.sub("", t, count=1).strip())
        elif _SOLL_ZUSATZ.match(t):
            zusatz.append(t)
        elif zusatz or kontakt:
            name = []
            break
        else:
            name.append(t)
    if not name or not (zusatz or kontakt) or len(zusatz) > 2 or len(kontakt) > 1 or "" in kontakt:
        return {"BT-44": " ".join(zeilen), "BT-51": "", "BT-163": "", "BT-56": ""}
    return {
        "BT-44": " ".join(name),
        "BT-51": zusatz[0] if zusatz else "",
        "BT-163": zusatz[1] if len(zusatz) > 1 else "",
        "BT-56": kontakt[0] if kontakt else "",
    }


def fiktiv_soll(d: dict) -> Beleg:
    """JSON-Sollwerte -> Beleg. Optionale Felder der Testsets (``beispiele/sets``), wenn vorhanden:
    ``payment_terms_text`` (gedruckte Zeilen des Zahlungsblocks) als BT-20, ``positions[].price_unit_qty`` als
    Preiseinheit. Käufername/Zusatz/Kontaktstelle nach ``kaeufer_ziel`` (für alle Sets gleich)."""
    b, inv, z = d["buyer"], d["invoice"], d["payment"]
    sk = d.get("discount_percent")
    name = kaeufer_ziel(b["name_lines"])
    bt20 = (
        " ".join(d["payment_terms_text"])
        if d.get("payment_terms_text")
        else f"Zahlbar innerhalb von {d['payment_days']} Tagen bis {z['due_date']} ohne Abzug"
    )
    kopf = {
        "BT-1": inv["number"],
        "BT-2": _datum(inv["date"]),
        "leistung": _datum(inv["service_date"]),
        **name,
        "BT-50": b["street"],
        "BT-53": b["postal_code"],
        "BT-52": b["city"],
        "kundennummer": b["customer_number"],
        "BT-13": inv["order_number"],
        "BT-9": _datum(z["due_date"]),
        "BT-20": bt20,
        "skonto": f"{format(Decimal(sk).normalize(), 'f')} % Skonto" if sk else "",
        "BT-109": Decimal(totals_soll_und_druck(d)[0]["net"]),
        "BT-110": Decimal(totals_soll_und_druck(d)[0]["vat"]),
        "BT-112": Decimal(totals_soll_und_druck(d)[0]["gross"]),
        "BT-119": [Decimal(d["vat_rate"]).normalize()],
        "Absender.name": d["seller"]["name"],
        "Absender.iban": d["seller"]["iban"],
    }
    pos = [
        {
            "menge": Decimal(p["qty"]),
            "einzelpreis": Decimal(p["unit_price"] or 0),
            "preiseinheit": Decimal(str(p.get("price_unit_qty") or 1)),
            "gesamt": pos_gesamt_soll(p, d),
            "bezeichnung": " ".join(p["description"]),
            "einheit": FIKTIV_EINHEITEN.get(p["unit"]),
        }
        for p in d["positions"]
    ]
    saetze = soll_saetze(d)
    kopf["BT-119"] = saetze
    if len(saetze) > 1:  # Satz je Position nur werten, wenn der Beleg mehrere Sätze hat
        for q, p in zip(pos, d["positions"]):
            q["steuersatz"] = Decimal(p.get("vat_rate") or d["vat_rate"]).normalize()
    return Beleg(kopf, pos)


def soll_saetze(d: dict) -> list[Decimal]:
    """Soll-Steuersätze: ``vat_breakdown[].rate`` oder ``BT-119`` (Liste oder Wert), sonst ``vat_rate``."""
    if d.get("vat_breakdown"):
        roh = [x["rate"] for x in d["vat_breakdown"]]
    elif d.get("BT-119"):
        roh = d["BT-119"] if isinstance(d["BT-119"], list) else [d["BT-119"]]
    else:
        roh = [d["vat_rate"]]
    return sorted({Decimal(x).normalize() for x in roh})


def fiktiv_belege(ordner: Path, unter: str = "Referenzdaten") -> list[tuple[Path, dict]]:
    """-> [(PDF, Sollwerte)] sortiert; Sollwerte aus ``<unter>/<Name>.json`` (Hold-out: Referenzdaten/holdout)."""
    out = []
    for js in sorted((ordner / unter).glob("Rechnung_*.json")):
        d = json.loads(js.read_text(encoding="utf-8"))
        out.append((ordner / "Rechnungen" / d["datei"], d))
    return out


def totals_soll_und_druck(d: dict) -> tuple[dict, dict]:
    """-> (berechnete Summen fürs Soll, gedruckte Summen).

    A1-Fehlerbelege: ``totals`` ist das Gedruckte, ``totals_berechnet`` das Richtige.
    Alte Prüfen-Fälle: ``totals`` ist berechnet, ``totals_printed`` gedruckt.
    """
    t = d.get("totals") or {}
    if d.get("totals_berechnet"):
        return d["totals_berechnet"], d.get("totals_printed") or t
    return t, d.get("totals_printed") or t


def pos_gesamt_soll(p: dict, d: dict) -> Decimal:
    """Positionsbetrag: berechnet, wenn der Druck vom Rechenwert abweicht (A1-Zeilenfehler)."""
    gedruckt = Decimal(str(p.get("total") or 0))
    if not d.get("totals_berechnet"):
        return gedruckt
    pe = Decimal(str(p.get("price_unit_qty") or 1)) or Decimal(1)
    berechnet = Decimal(str(p.get("qty") or 0)) * Decimal(str(p.get("unit_price") or 0)) / pe
    if berechnet.quantize(Decimal("0.01")) != gedruckt.quantize(Decimal("0.01")):
        return berechnet
    return gedruckt


def manifest_pfad(ordner: Path) -> Path | None:
    """Nächstes ``MANIFEST.json`` in diesem Ordner oder einem Elternordner."""
    for basis in (ordner, *ordner.parents):
        p = basis / "MANIFEST.json"
        if p.is_file():
            return p
    return None


def manifest_belege(ordner: Path) -> list[dict] | None:
    """MANIFEST-Einträge, die zu diesem Testset-Ordner gehören, oder None."""
    pfad = manifest_pfad(ordner)
    if pfad is None:
        return None
    man = json.loads(pfad.read_text(encoding="utf-8"))
    basis = pfad.parent
    belege = man.get("belege") or []
    if basis == ordner:
        return belege
    try:
        rel = ordner.resolve().relative_to(basis.resolve()).as_posix()
    except ValueError:
        return None
    return [b for b in belege if str(b.get("pdf") or "").startswith(rel + "/")]


def _soll_mit_rolle(d: dict, eintrag: dict) -> dict:
    return dict(
        d,
        _rolle=eintrag.get("rolle") or "",
        _ausserhalb_v1=bool(eintrag.get("ausserhalb_v1")),
        _erwarteter_status=eintrag.get("erwarteter_status") or d.get("erwarteter_status") or "",
        _erwartete_hinweise=list(d.get("erwartete_hinweise") or []),
    )


def set_belege(ordner: Path, name: str = "") -> dict[str, list[tuple[Path, dict]]]:
    """Belege eines Testsets nach Rolle. Mit MANIFEST aus den Rollen, sonst Ordnerstruktur (Training / Hold-out)."""
    out: dict[str, list[tuple[Path, dict]]] = {
        "anlernen": [],
        "nachlesen": [],
        "holdout": [],
        "holdout-fehler": [],
        "holdout-falle": [],
    }
    eintraege = manifest_belege(ordner)
    if eintraege is not None:
        basis = manifest_pfad(ordner).parent
        for b in eintraege:
            pdf, js = basis / b["pdf"], basis / b["soll"]
            d = _soll_mit_rolle(json.loads(js.read_text(encoding="utf-8")), b)
            out.setdefault(b.get("rolle") or "anlernen", []).append((pdf, d))
        for rolle in out:
            out[rolle].sort(key=lambda x: x[0].name)
        return out
    if name != "fiktiv":
        out["holdout"] = [
            (
                pdf,
                dict(
                    d,
                    _rolle="holdout",
                    _ausserhalb_v1=False,
                    _erwarteter_status="ok",
                    _erwartete_hinweise=[],
                ),
            )
            for pdf, d in fiktiv_belege(ordner, "Referenzdaten/holdout")
        ]
    out["anlernen"] = [
        (
            pdf,
            dict(
                d,
                _rolle="anlernen",
                _ausserhalb_v1=False,
                _erwarteter_status="ok",
                _erwartete_hinweise=[],
            ),
        )
        for pdf, d in fiktiv_belege(ordner)
    ]
    return out


_TEIL_SUFFIX = (
    (" (Hold-out-Fehler)", "Hold-out-Fehler"),
    (" (Hold-out-Falle)", "Hold-out-Falle"),
    (" (Hold-out)", "Hold-out"),
    (" (Nachlesen)", "Nachlesen"),
)
_ROLLE_TEIL = {
    "holdout-fehler": "Hold-out-Fehler",
    "holdout-falle": "Hold-out-Falle",
    "holdout": "Hold-out",
    "nachlesen": "Nachlesen",
}


def weg_und_teil(familie: str, verfahren: str) -> tuple[str, str]:
    """-> (Weg, Teil) aus dem Verfahrensnamen ``<familie>-<weg>`` plus optionalem Suffix."""
    rest = verfahren[len(familie) + 1 :] if verfahren.startswith(familie + "-") else verfahren
    for suf, teil in _TEIL_SUFFIX:
        if rest.endswith(suf):
            return rest[: -len(suf)], teil
    return rest, "Training"


def hinweis_bt(text: str) -> str | None:
    """Maßgeblich ist das BT im Hinweis, nicht der Wortlaut."""
    m = re.search(r"\[(BT-\d+|BG-\d+)\]", text or "")
    return m.group(1) if m else None


def status_ist(f: Fall) -> str:
    """Ist-Status des Belegs: leer / fehler / prüfen / ok."""
    if f.ist is None or f.hinweise is None:
        return "leer"
    if any(str(t).startswith("FEHLER") for t in f.hinweise):
        return "fehler"
    if f.ist.beleg_pruefen or any(str(t).startswith("PRUEFEN") for t in f.hinweise):
        return "prüfen"
    return "ok"


def status_treffer(f: Fall, still: bool = False) -> bool | None:
    """Hold-out-Fehler: erwarteter Status erreicht. Hold-out-Falle: nicht still falsch. Sonst None."""
    if f.rolle == "holdout-falle":
        return not still and status_ist(f) != "leer"
    soll = f.erwarteter_status
    if f.rolle != "holdout-fehler" or not soll:
        return None
    ist = status_ist(f)
    if soll == "prüfen":
        return ist in ("prüfen", "fehler")
    return ist == soll


def tabelle_korrigieren(s: anlernen.Sitzung) -> None:
    """Was ein Nutzer im Assistenten tut, wenn kein Tabellenrahmen erkannt wird: Rahmen von der Kopfzeile bis zur
    Übertrags-/Summenzeile der ersten Tabellenseite ziehen und die Spalte „Gesamtpreis“ als Gesamt wählen.
    Beginnt keine Zeile mit „Menge“ (andere Layouts: „Pos. … Menge …“), gilt die erste Kopfzeile mit „Menge“ und
    einer Bezeichnungsspalte; Ende auch an Zwischen-/Endsumme, Gesamt als letzte Betrags-/Gesamtspalte."""
    kopf = next((z for z in s.zeilen if re.match(r"Menge\b", z.text)), None)
    breit = kopf is None
    if breit:
        kopf = next(
            (
                z
                for z in s.zeilen
                if re.search(r"\bMenge\b", z.text)
                and len(z.woerter) >= 4
                and re.search(r"Bezeichnung|Beschreibung|Produkt|Artikel", z.text)
            ),
            None,
        )
    if kopf is None:
        return
    ende_re = (
        r"(Übertrag|Netto|Summe|Zwischensumme|Endsumme|Gesamt|Rechnungsbetrag|Warenwert)\b"
        if breit
        else r"(Übertrag|Netto|Summe)\b"
    )
    ende = next(
        (
            z
            for z in s.zeilen
            if z.seite == kopf.seite and z.top > kopf.top and re.match(ende_re, z.text)
        ),
        None,
    )
    unten = (
        ende.top - 1
        if ende
        else max(
            max(w.bottom or w.top + 10 for w in z.woerter)
            for z in s.zeilen
            if z.seite == kopf.seite
        )
    )
    s.rahmen_setzen(
        kopf.seite,
        min(w.x0 for w in kopf.woerter) - 30,
        kopf.top - 2,
        max(w.x1 for w in kopf.woerter) + 5,
        unten,
    )
    titel = s.spalten_titel()
    for i, t in enumerate(titel):
        if t.lower().startswith("gesamt"):
            s.tabelle.spalten[i] = "gesamt"
    if breit and "gesamt" not in s.tabelle.spalten:
        kand = [
            i for i, t in enumerate(titel) if re.search(r"gesamt|betrag|g-?preis|\bgp\b", t.lower())
        ]
        if kand:
            s.tabelle.spalten[kand[-1]] = "gesamt"


def _hinweise(r, k) -> list[str]:
    rechnen.berechnen(r)  # setzt u. a. den Kontrollwert-Vergleich
    pflichtpruefung.pruefen(r, pipeline.pflicht_kontext(k))
    return [str(h) for h in r.hinweise if "BT-31" not in str(h)]  # USt-IdNr. absichtlich falsch


def _ist_aus_sitzung(s: anlernen.Sitzung, k) -> tuple[Beleg, list[str]]:
    ist = aus_sitzung(s)
    r = s.rechnung()
    ist.kopf["BT-9"] = r.zahlung.faellig
    ist.kopf["BT-163"] = r.kaeufer.anschrift.zeile3
    ist.kopf["BT-56"] = r.kaeufer.kontakt_name
    ist.kopf["skonto"] = ist.kopf.get("BT-20")
    if len(r.positionen) == len(ist.positionen):
        for p, q in zip(ist.positionen, r.positionen):
            p["einheit"] = q.einheit
            p["steuersatz"] = _satz(q)
    if (
        len(_saetze(r.positionen)) > 1
    ):  # gemischte Sätze: BT-119 ist die Menge der Sätze der Positionen
        ist.kopf["BT-119"] = _saetze(r.positionen)
    h = _hinweise(r, k)
    _pruefen_aus_hinweise(ist, r.hinweise)
    return ist, h


def sitzung_soll_korrigieren(s: anlernen.Sitzung, d: dict) -> None:
    """Soll-Werte wie eine Nutzerkorrektur in den Assistenten übernehmen.

    Weicht der Vorschlag vom Soll ab, wird der Soll-Text eingetippt (die Fundstelle in der PDF
    wird neu gesucht). Stimmt er schon, gilt „Passt“: Status erkannt, Beschriftung bleibt.
    Mehrere Steuersätze bleiben der Tabelle überlassen (BT-119 im Kopf ist ein Wert).
    """
    soll = fiktiv_soll(d)
    for feld in anlernen.FELDER:
        w = soll.kopf.get(feld)
        if feld == "BT-119" and isinstance(w, list):
            if len(w) != 1:
                continue
            w = w[0]
        text = "" if _leer(w) else (w if isinstance(w, str) else anlernen.anzeigen(feld, w))
        text = " ".join(str(text).split())
        vs = s.werte[feld]
        try:
            ist = s.wert(feld)
        except Exception:
            ist = None
        soll_w = anlernen.lesen(feld, text) if text else None
        if not text:
            if vs.wert:
                s.setzen(feld, "")
            continue
        if ist == soll_w:
            if vs.status != "erkannt":
                s.setzen(feld, vs.wert or text, vs.woerter or None)
            continue
        s.setzen(feld, text)


def rechnung_soll_uebernehmen(r, d: dict) -> None:
    """Kopf und Positionen der Rechnung auf die Soll-Werte setzen (Lernziel, nicht der Kaltstart)."""
    soll = fiktiv_soll(d)
    k = soll.kopf
    if k.get("BT-1"):
        r.nummer = k["BT-1"]
    if k.get("BT-2") is not None:
        r.datum = k["BT-2"]
    lw = k.get("leistung")
    if isinstance(lw, tuple) and len(lw) == 2:
        r.leistung_von, r.leistung_bis = lw
        r.leistungsdatum = None
    elif lw:
        r.leistungsdatum = lw
        r.leistung_von = r.leistung_bis = None
    r.kaeufer.name = k.get("BT-44") or ""
    r.kaeufer.anschrift.zusatz = k.get("BT-51") or ""
    r.kaeufer.anschrift.zeile3 = k.get("BT-163") or ""
    r.kaeufer.kontakt_name = k.get("BT-56") or ""
    r.kaeufer.anschrift.strasse = k.get("BT-50") or ""
    r.kaeufer.anschrift.plz = k.get("BT-53") or ""
    r.kaeufer.anschrift.ort = k.get("BT-52") or ""
    r.kundennummer = k.get("kundennummer") or ""
    r.bestellnummer = k.get("BT-13") or ""
    if k.get("BT-20"):
        r.zahlung.bedingungen = k["BT-20"]
    if k.get("BT-9") is not None:
        r.zahlung.faellig = k["BT-9"]
    default_satz = Decimal(str(d.get("vat_rate") or "19")).normalize()
    neu = []
    for sp in soll.positionen:
        satz = sp.get("steuersatz")
        if satz is None:
            satz = default_satz
        neu.append(
            Position(
                bezeichnung=sp["bezeichnung"] or "",
                menge=sp["menge"],
                einzelpreis=sp["einzelpreis"],
                preiseinheit=sp["preiseinheit"] or Decimal(1),
                einheit=sp.get("einheit") or "",
                steuer=Steuer(satz=satz),
                kontrolle_gesamt=sp["gesamt"],
                netto=sp["gesamt"],
            )
        )
    r.positionen = neu
    for f in ("BT-109", "BT-110", "BT-112"):
        if k.get(f) is not None:
            r.kontrolle[f] = k[f]
    rechnen.berechnen(r)


def soll_anlernen(s: anlernen.Sitzung, d: dict):
    """Nutzerkorrektur der Soll-Werte in der Sitzung, danach die Rechnung zum Lernen."""
    sitzung_soll_korrigieren(s, d)
    r = s.rechnung()
    rechnung_soll_uebernehmen(r, d)
    return r


def lauf_fiktiv(
    tmp: Path,
    ordner: Path,
    verfahren: list[str],
    lernen: int,
    freigaben: dict,
    name: str = "fiktiv",
    gruppe: str = "",
) -> list[Fall]:
    """Fiktive Belege (JSON-Soll) in den Verfahren fiktiv-kaltstart/-korrigiert/-angelernt. Für ein Testset
    (``name`` ≠ „fiktiv“) heißen die Verfahren „<name>-…“; Belege unter Referenzdaten/holdout laufen getrennt als
    „<name>-… (Hold-out)“ (angelernt: mit der an den Tuning-Belegen angelernten Vorlage, ohne weiteres Lernen)."""
    faelle: list[Fall] = []
    rollen = set_belege(ordner, name)
    belege = rollen["anlernen"]
    nachlesen = rollen["nachlesen"]
    holdout = rollen["holdout"] + rollen["holdout-fehler"] + rollen["holdout-falle"]
    posfelder = POSFELDER + ["Pos.einheit", "Pos.steuersatz"]
    felder = list(FIKTIV_FELDER)

    def fall(v: str, pdf: Path, d: dict, ist, grund, hinweise):
        teil = _ROLLE_TEIL.get(d.get("_rolle") or "")
        v = v.replace("fiktiv", name, 1) + (f" ({teil})" if teil else "")
        faelle.append(
            Fall(
                v,
                name,
                pdf.name,
                fiktiv_soll(d),
                ist,
                grund,
                list(felder),
                posfelder,
                soll_vollstaendig=True,
                hinweise=hinweise,
                gruppe=gruppe,
                rolle=d.get("_rolle") or "",
                ausserhalb_v1=bool(d.get("_ausserhalb_v1")),
                erwarteter_status=d.get("_erwarteter_status") or "",
                erwartete_hinweise=list(d.get("_erwartete_hinweise") or []),
            )
        )

    messen = nachlesen + holdout
    for v in ("fiktiv-kaltstart", "fiktiv-korrigiert"):
        if v not in verfahren:
            continue
        k = _konfig(PE / "konfiguration.yaml", tmp)
        k.pdf_profile = []
        for pdf, d in belege + messen:
            try:
                s = anlernen.Sitzung(pdf, k)
                if v == "fiktiv-korrigiert":
                    tabelle_korrigieren(s)
                ist, h = _ist_aus_sitzung(s, k)
                fall(v, pdf, d, ist, "", h)
            except Exception as e:
                fall(v, pdf, d, None, f"{type(e).__name__}: {e}", None)
    # erste ``lernen`` Anlern-Belege (oder alle, wenn weniger), wenn danach noch etwas zu messen bleibt
    n_lernen = min(lernen, len(belege))
    if "fiktiv-angelernt" in verfahren and n_lernen and (belege[n_lernen:] + messen):
        k = _konfig(PE / "konfiguration.yaml", tmp)
        k.pdf_profile = []
        prof = None
        for pdf, d in belege[:n_lernen]:
            s = anlernen.Sitzung(pdf, k)
            if s.vorlage is None:
                tabelle_korrigieren(s)
            r = soll_anlernen(s, d)
            if prof is None:  # wie Sitzung.speichern: neues Nur-PDF-Profil aus dem Absender
                prof = anlernen.profil_daten(s.absender, anlernen.ziel_tage(s.werte["BT-20"].wert))
                k.pdf_profile = [prof]
                s.profil = prof
            vl, _ = pdferkennung.lernen(
                r,
                s.zeilen,
                prof,
                s.vorlage,
                pdferkennung.einstellungen(prof),
                pv_vorgabe=s.pv(),
                stellen=s.stellen(),
                bereiche=s.bereiche(),
                flaechen=copy.deepcopy(s.zonen),
            )
            pdferkennung.vorlage_speichern(vl, prof)
        ab = pdferkennung.einstellungen(prof)["nur_pdf_ab"]
        folge = max(
            (
                int((x.get("statistik") or {}).get("folge_treffer", 0))
                for x in pdferkennung.vorlagen_laden(prof)
            ),
            default=0,
        )
        freigaben[f"{name}/" + prof["profil"]] = {
            "angelernt": n_lernen,
            "ohne_abweichung": folge + 1,
            "folge_treffer": folge,
            "nur_pdf_ab": ab,
            "frei": folge >= ab,
        }
        # Lesequalität messen, nicht die Freigabe: auch nach einem Zähler-Reset im letzten Trainingsbeleg lesen
        prof["pdf_erkennung"] = {"nur_pdf": True, "nur_pdf_ab": 0}
        for pdf, d in belege[n_lernen:] + messen:
            try:
                r, grund = pdferkennung.nur_pdf(
                    pdf, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), [prof], k
                )
                if r is None:
                    fall("fiktiv-angelernt", pdf, d, None, grund, None)
                    continue
                h = _hinweise(r, k)
                ist = aus_rechnung(r, summen_aus_kontrolle=True)
                ist.kopf.update(
                    {"Absender.name": r.verkaeufer.name, "Absender.iban": r.zahlung.iban}
                )
                fall("fiktiv-angelernt", pdf, d, ist, "", h)
            except Exception as e:
                fall("fiktiv-angelernt", pdf, d, None, f"{type(e).__name__}: {e}", None)
    return faelle


def hinweise_auswerten(faelle: list[Fall]) -> dict:
    """-> {Verfahren: [{klasse, anzahl, dateien, beispiel}]} plus „Σ Positionen ≠ Soll-Netto“."""
    out: dict[str, list[dict]] = {}
    for v in sorted({f.verfahren for f in faelle if f.hinweise is not None}):
        fs = [f for f in faelle if f.verfahren == v and f.hinweise is not None]
        zeilen = []
        for name, passt in HINWEISKLASSEN:
            treffer = [
                (f, next(t for t in f.hinweise if passt(t)))
                for f in fs
                if any(passt(t) for t in f.hinweise)
            ]
            zeilen.append(
                {
                    "klasse": name,
                    "anzahl": len(treffer),
                    "dateien": [_nr(f) for f, _ in treffer],
                    "beispiel": treffer[0][1] if treffer else "",
                }
            )
        summe = []
        for f in fs:
            ist = sum((p["gesamt"] or 0 for p in f.ist.positionen), Decimal(0))
            if ist != f.soll.kopf["BT-109"]:
                summe.append(
                    (
                        f,
                        f"Σ Positionen {ist} ≠ Netto {f.soll.kopf['BT-109']} "
                        f"(Diff {f.soll.kopf['BT-109'] - ist})",
                    )
                )
        zeilen.append(
            {
                "klasse": "Σ Positionen ≠ Soll-Netto",
                "anzahl": len(summe),
                "dateien": [_nr(f) for f, _ in summe],
                "beispiel": summe[0][1] if summe else "",
                "diff": {
                    _nr(f): str(
                        f.soll.kopf["BT-109"]
                        - sum((p["gesamt"] or 0 for p in f.ist.positionen), Decimal(0))
                    )
                    for f, _ in summe
                },
            }
        )
        zeilen.append(
            {
                "klasse": "Belege mit Hinweis „prüfen“ (ohne BT-31)",
                "dateien": [],
                "anzahl": sum(
                    any(t.startswith("PRUEFEN") or t.startswith("FEHLER") for t in f.hinweise)
                    for f in fs
                ),
                "beispiel": "",
            }
        )
        out[v] = zeilen
    return out


def _nr(f: Fall) -> str:
    m = re.search(r"(\d{5})\.pdf$", f.datei)
    return m.group(1) if m else f.datei


# ---------------------------------------------------------------- Auswertung
def bewerten(faelle: list[Fall]) -> tuple[dict, list[dict]]:
    """-> ({(Verfahren, Feld): [Treffer, Gesamt]}, Fehlschläge). Ein Feld zählt, wenn Soll oder Ist gefüllt ist;
    Positionsfelder je Soll-Position in Reihenfolge (fehlende Ist-Position = Fehlschlag)."""
    zaehler: dict[tuple[str, str], list[int]] = {}
    fehl: list[dict] = []

    def zaehlen(f: Fall, feld: str, soll, ist, wo: str = ""):
        z = zaehler.setdefault((f.verfahren, feld), [0, 0])
        z[1] += 1
        if f.ist is not None and _gleich(feld, soll, ist):
            z[0] += 1
        else:
            fehl.append(
                {
                    "verfahren": f.verfahren,
                    "quelle": f.quelle,
                    "datei": f.datei,
                    "feld": feld + wo,
                    "soll": _zeigen(soll),
                    "ist": _zeigen(ist),
                    "art": _fehlart(f, feld, ist),
                }
            )

    for f in faelle:
        start = len(fehl)  # nicht gelesen: alle Felder Fehlschlag, eine Zeile in der Liste
        ist = f.ist or Beleg()
        for feld in f.felder:
            s, i = f.soll.kopf.get(feld), ist.kopf.get(feld)
            if (
                (_leer(s) and _leer(i))
                or (_leer(s) and feld in FREIWILLIG and not f.soll_vollstaendig)
                or (feld == "skonto" and _leer(s))
            ):
                continue
            zaehlen(f, feld, s, i)
        if "Pos.anzahl" in f.posfelder:
            zaehlen(f, "Pos.anzahl", len(f.soll.positionen), len(ist.positionen))
        vor_pos = len(fehl)
        for n, sp in enumerate(f.soll.positionen):
            ip = ist.positionen[n] if n < len(ist.positionen) else {}
            for feld in f.posfelder:
                if feld == "Pos.anzahl":
                    continue
                a = feld.split(".", 1)[1]
                s, i = sp.get(a), ip.get(a)
                if a == "preiseinheit" and s == 1 and i in (None, 1):
                    continue  # ohne Preiseinheit nicht bewerten
                if a in ("einheit", "steuersatz") and _leer(s):
                    continue  # Druck ohne Mengeneinheit / nur ein Satz: nicht werten
                zaehlen(f, feld, s, i, f"[{n + 1}]")
        if (
            f.ist is not None and f.soll.positionen and not ist.positionen
        ):  # eine Zeile statt einer je Position
            del fehl[vor_pos:]
            fehl.append(
                {
                    "verfahren": f.verfahren,
                    "quelle": f.quelle,
                    "datei": f.datei,
                    "feld": "Pos.* (alle)",
                    "soll": f"{len(f.soll.positionen)} Positionen",
                    "ist": "keine Position gelesen",
                    "art": "leer",
                }
            )
        if f.ist is None:
            del fehl[start:]
            fehl.append(
                {
                    "verfahren": f.verfahren,
                    "quelle": f.quelle,
                    "datei": f.datei,
                    "feld": "(ganzer Beleg)",
                    "soll": f.soll.kopf.get("BT-1", ""),
                    "ist": f"nicht gelesen: {f.grund}",
                    "art": "leer",
                }
            )
    return zaehler, fehl


def _fehlart(f: Fall, feld: str, ist) -> str:
    """Fehlschlag einordnen: „leer“ (nichts gelesen), „pruefen“ (Feld/Beleg mit Hinweis), „still“ (falscher Wert
    ohne Hinweis – das Schlimmste)."""
    if f.ist is None or _leer(ist) or ist == []:
        return "leer"
    b = f.ist
    if feld in b.pruefen or (feld.startswith("Pos") and "Pos" in b.pruefen) or b.beleg_pruefen:
        return "pruefen"
    return "still"


def status_auswerten(faelle: list[Fall], fehl: list[dict]) -> dict:
    """Status-Treffer für Hold-out-Fehler/Fallen und BT-Abgleich der erwarteten Hinweise."""
    still = {(x["verfahren"], x["datei"]) for x in fehl if x["art"] == "still"}
    faelle_s, hinweise = [], []
    for f in faelle:
        if f.rolle not in ("holdout-fehler", "holdout-falle"):
            continue
        hat_still = (f.verfahren, f.datei) in still
        treffer = status_treffer(f, still=hat_still)
        faelle_s.append(
            {
                "verfahren": f.verfahren,
                "quelle": f.quelle,
                "datei": f.datei,
                "rolle": f.rolle,
                "ausserhalb_v1": f.ausserhalb_v1,
                "erwartet": f.erwarteter_status,
                "ist": status_ist(f),
                "still": hat_still,
                "treffer": treffer,
            }
        )
        soll_bt = {hinweis_bt(x) for x in f.erwartete_hinweise if hinweis_bt(x)}
        ist_bt = {hinweis_bt(x) for x in (f.hinweise or []) if hinweis_bt(x)}
        if soll_bt:
            hinweise.append(
                {
                    "verfahren": f.verfahren,
                    "quelle": f.quelle,
                    "datei": f.datei,
                    "rolle": f.rolle,
                    "ausserhalb_v1": f.ausserhalb_v1,
                    "erwartet": sorted(soll_bt),
                    "gefunden": sorted(ist_bt),
                    "treffer": soll_bt <= ist_bt,
                }
            )
    return {"belege": faelle_s, "hinweise_bt": hinweise}


def zusammenfassen(faelle: list[Fall], args) -> dict:
    zaehler, fehl = bewerten(faelle)
    quellen: dict[str, dict[str, int]] = {}
    for f in faelle:
        q = quellen.setdefault(f.verfahren, {})
        q[f.quelle] = q.get(f.quelle, 0) + 1
    gelesen = {}
    for f in faelle:
        g = gelesen.setdefault(f.verfahren, [0, 0])
        g[1] += 1
        g[0] += f.ist is not None
    belege_ok = {}
    fehl_dateien = {(x["verfahren"], x["datei"]) for x in fehl}
    for f in faelle:
        b = belege_ok.setdefault(f.verfahren, [0, 0])
        b[1] += 1
        b[0] += (f.verfahren, f.datei) not in fehl_dateien
    arten: dict[str, dict[str, int]] = {}
    for x in fehl:
        a = arten.setdefault(x["verfahren"], {"leer": 0, "pruefen": 0, "still": 0})
        a[x["art"]] += 1
    tabellen = {}
    reihenfolge = (
        KOPFFELDER
        + ["BT-9", "skonto", "BT-163", "BT-56"]
        + ABSENDERFELDER
        + POSFELDER
        + ["Pos.einheit", "Pos.steuersatz"]
    )
    for (v, feld), (t, g) in zaehler.items():
        tabellen.setdefault(v, []).append(
            {
                "feld": feld,
                "name": FELDNAMEN.get(feld, feld),
                "treffer": t,
                "gesamt": g,
                "quote": round(t / g, 4) if g else None,
            }
        )
    for v in tabellen:
        tabellen[v].sort(key=lambda z: reihenfolge.index(z["feld"]))
    return {
        "parameter": {
            "generator": args.generator,
            "seed": args.seed,
            "lernen": args.lernen,
            "verfahren": args.verfahren,
        },
        "hinweise": hinweise_auswerten(faelle),
        "quellen": quellen,
        "gelesen": gelesen,
        "belege_fehlerfrei": belege_ok,
        "tabellen": tabellen,
        "fehlarten": arten,
        "fehlschlaege": sorted(
            fehl, key=lambda x: (x["verfahren"], x["quelle"], x["datei"], x["feld"])
        ),
        "status": status_auswerten(faelle, fehl),
    }


def markdown(e: dict, max_fehl: int | None = None) -> str:
    zeilen = [
        "# Erkennungs-Benchmark",
        "",
        f"Parameter: Generator {e['parameter']['generator']} Drucke, Seed {e['parameter']['seed']}, "
        f"angelernt mit {e['parameter']['lernen']} Paaren je Verkäufer. Erzeugt mit `python tools/benchmark.py`.",
        "",
    ]
    for v, tab in e["tabellen"].items():
        q = ", ".join(f"{k} {n}" for k, n in sorted(e["quellen"][v].items()))
        g, b = e["gelesen"][v], e["belege_fehlerfrei"][v]
        fa = e.get("fehlarten", {}).get(v, {})
        zeilen += [
            f"## Verfahren „{v}“",
            "",
            f"Belege: {q} (gelesen {g[0]}/{g[1]}, ganz fehlerfrei {b[0]}/{b[1]})",
            "",
            f"Fehlschläge: leer {fa.get('leer', 0)}, prüfen {fa.get('pruefen', 0)}, "
            f"still falsch {fa.get('still', 0)}",
            "",
            "| Feld | Treffer | Gesamt | Quote |",
            "|---|---:|---:|---:|",
        ]
        for z in tab:
            zeilen.append(
                f"| {z['name']} | {z['treffer']} | {z['gesamt']} | "
                f"{'–' if z['quote'] is None else format(z['quote'], '.1%')} |"
            )
        zeilen.append("")
        if v in e.get("hinweise", {}):
            zeilen += [
                f"Prüfhinweise „{v}“ (Klassen des Verarbeitungsprotokolls; BT-31 nicht gezählt):",
                "",
                "| Klasse | Belege | Nummern | Beispiel |",
                "|---|---:|---|---|",
            ]
            for h in e["hinweise"][v]:
                nummern = []
                for d in h["dateien"]:
                    if "diff" in h and len(h["dateien"]) <= 5:
                        nummern.append(f"{d} (Diff {h['diff'][d]})")
                    else:
                        nummern.append(d)
                zeilen.append(
                    f"| {h['klasse']} | {h['anzahl']} | {', '.join(nummern)} | "
                    f"{h['beispiel'].replace('|', '/')} |"
                )
            zeilen.append("")
    if e.get("freigabe"):
        zeilen += [
            "## Freigabe „Nur PDF“ (Voreinstellung)",
            "",
            "| Verkäufer | angelernt | ohne Abweichung | Treffer in Folge | nötig | frei |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for n, x in e["freigabe"].items():
            zeilen.append(
                f"| {n} | {x['angelernt']} | {x['ohne_abweichung']} | {x['folge_treffer']} | "
                f"{x['nur_pdf_ab']} | {'ja' if x['frei'] else 'nein'} |"
            )
        zeilen.append("")
    for gruppe, liste in e.get("familien", {}).items():
        zeilen += [
            f"## Familien „{gruppe}“",
            "",
            "Felder: richtig / leer / prüfen / still falsch. v1-Quote ohne Belege mit ausserhalb_v1.",
            "",
            "| Familie | Weg | Teil | v1 | Belege | ganz fehlerfrei | Felder | richtig | leer | prüfen | still falsch |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for z in liste:
            kreis = "ja" if z.get("v1", True) else "nein"
            zeilen.append(
                f"| {z['familie']} | {z['weg']} | {z['teil']} | {kreis} | {z['belege']} | {z['fehlerfrei']} | "
                f"{z['felder']} | {z['richtig']} | {z['leer']} | {z['pruefen']} | {z['still']} |"
            )
        zeilen.append("")
    st = e.get("status") or {}
    if st.get("belege"):
        zeilen += [
            "## Status Hold-out-Fehler und -Fallen",
            "",
            "Treffer: erwarteter Status erreicht (prüfen/fehler) bzw. Falle nicht still falsch. Hinweise: BT zählt, nicht der Wortlaut.",
            "",
            "| Verfahren | Datei | Rolle | erwartet | ist | still | Treffer |",
            "|---|---|---|---|---|---|---|",
        ]
        for x in st["belege"]:
            zeilen.append(
                f"| {x['verfahren']} | {x['datei']} | {x['rolle']} | {x['erwartet'] or '–'} | "
                f"{x['ist']} | {'ja' if x['still'] else 'nein'} | {'ja' if x['treffer'] else 'nein'} |"
            )
        zeilen.append("")
        if st.get("hinweise_bt"):
            zeilen += [
                "| Datei | erwartet (BT) | gefunden (BT) | Treffer |",
                "|---|---|---|---|",
            ]
            for x in st["hinweise_bt"]:
                zeilen.append(
                    f"| {x['datei']} | {', '.join(x['erwartet']) or '–'} | "
                    f"{', '.join(x['gefunden']) or '–'} | {'ja' if x['treffer'] else 'nein'} |"
                )
            zeilen.append("")
    fl = e["fehlschlaege"]
    zeilen += [
        f"## Fehlschläge ({len(fl)})",
        "",
        "| Verfahren | Datei | Feld | Soll | Ist |",
        "|---|---|---|---|---|",
    ]
    for x in fl[:max_fehl] if max_fehl else fl:
        zeilen.append(
            f"| {x['verfahren']} | {x['datei']} | {x['feld']} | {x['soll'].replace('|', '/')} | "
            f"{x['ist'].replace('|', '/')} |"
        )
    if max_fehl and len(fl) > max_fehl:
        zeilen.append(f"| … | {len(fl) - max_fehl} weitere | | | |")
    return "\n".join(zeilen) + "\n"


def ausfuehren(args) -> dict:
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="ff-benchmark-") as t:
        tmp = Path(t)
        alt = pdferkennung.ablage
        pdferkennung.ablage = lambda profil: tmp / "angelernt" / pdferkennung.profil_name(profil)
        try:
            faelle, freigaben = [], {}
            if "assistent" in args.verfahren:
                faelle += lauf_assistent(tmp, args.generator, args.seed)
            if "angelernt" in args.verfahren:
                faelle += lauf_angelernt(tmp, args.lernen, freigaben)
            if "handvorlage" in args.verfahren:
                faelle += lauf_handvorlage(tmp)
            if any(v.startswith("fiktiv") for v in args.verfahren):
                faelle += lauf_fiktiv(tmp, args.fiktiv, args.verfahren, args.lernen, freigaben)
                for ordner, gruppe in testsets_mit_gruppe(args.set):
                    faelle += lauf_fiktiv(
                        tmp,
                        ordner,
                        args.verfahren,
                        args.lernen,
                        freigaben,
                        name=ordner.name,
                        gruppe=gruppe,
                    )
        finally:
            pdferkennung.ablage = alt
            logging.disable(logging.NOTSET)
    e = zusammenfassen(faelle, args)
    fam = familien_auswerten(faelle, e)
    if fam:
        e["familien"] = fam
    e["freigabe"] = dict(sorted(freigaben.items()))
    return e


SETS = BEISPIELE / "sets"


def _ist_set(p: Path) -> bool:
    return (p / "Rechnungen").is_dir() and (p / "Referenzdaten").is_dir()


def testsets_mit_gruppe(gewaehlt: list[Path] | None) -> list[tuple[Path, str]]:
    """-> [(Testset, Gruppe)]. Testsets sind Ordner mit Rechnungen/ und Referenzdaten/: ``--set`` gewählt, sonst
    alle unter beispiele/sets/. Ist ein gewählter Ordner selbst kein Testset, zählen alle Testsets darunter
    (rekursiv, sortiert) als Familien der Gruppe ``<Ordnername>``; direkt gewählte Testsets haben keine Gruppe."""
    if gewaehlt is None:
        return [(p, "") for p in sorted(p for p in SETS.glob("*") if p.is_dir()) if _ist_set(p)]
    out = []
    for p in gewaehlt:
        if _ist_set(p):
            out.append((p, ""))
        elif p.is_dir():
            out += [
                (r.parent, p.name)
                for r in sorted(p.rglob("Rechnungen"))
                if r.is_dir() and _ist_set(r.parent)
            ]
    return out


def testsets(gewaehlt: list[Path] | None) -> list[Path]:
    return [p for p, _ in testsets_mit_gruppe(gewaehlt)]


def familien_auswerten(faelle: list[Fall], e: dict) -> dict:
    """Testset-Gruppen mit Familien: je Gruppe Zeilen (Familie, Weg, Teil) mit Belegen, ganz fehlerfrei und den
    Feldern richtig/leer/prüfen/still falsch; dazu „gesamt“ und „Hold-out gesamt“ je Weg. „leer“ ist der Rest
    (nicht gelesene Belege und fehlende Positionen stehen in den Fehlschlägen nur als eine Zeile)."""
    out: dict[str, list[dict]] = {}
    arten: dict[tuple[str, str], int] = {}
    for x in e["fehlschlaege"]:
        arten[(x["verfahren"], x["art"])] = arten.get((x["verfahren"], x["art"]), 0) + 1
    for gruppe in sorted({f.gruppe for f in faelle if f.gruppe}):
        zeilen: dict[tuple[str, str, str, bool], dict] = {}
        for v in dict.fromkeys(f.verfahren for f in faelle if f.gruppe == gruppe):
            fam = next(f.quelle for f in faelle if f.verfahren == v)
            weg, teil = weg_und_teil(fam, v)
            v1 = not any(f.ausserhalb_v1 for f in faelle if f.verfahren == v)
            tab = e["tabellen"].get(v, [])
            z = {
                "familie": fam,
                "weg": weg,
                "teil": teil,
                "v1": v1,
                "belege": e["belege_fehlerfrei"][v][1],
                "fehlerfrei": e["belege_fehlerfrei"][v][0],
                "felder": sum(t["gesamt"] for t in tab),
                "richtig": sum(t["treffer"] for t in tab),
                "pruefen": arten.get((v, "pruefen"), 0),
                "still": arten.get((v, "still"), 0),
            }
            z["leer"] = z["felder"] - z["richtig"] - z["pruefen"] - z["still"]
            zeilen[(fam, weg, teil, v1)] = z
        liste = list(zeilen.values())
        summen = (
            ("gesamt", lambda z: True, "alle"),
            ("gesamt v1", lambda z: z["v1"], "alle"),
            ("ausserhalb_v1", lambda z: not z["v1"], "alle"),
            ("Hold-out gesamt", lambda z: z["teil"] == "Hold-out" and z["v1"], "Hold-out"),
            (
                "Hold-out-Fehler",
                lambda z: z["teil"] == "Hold-out-Fehler" and z["v1"],
                "Hold-out-Fehler",
            ),
            (
                "Hold-out-Falle",
                lambda z: z["teil"] == "Hold-out-Falle" and z["v1"],
                "Hold-out-Falle",
            ),
            (
                "Hold-out gesamt (ausserhalb_v1)",
                lambda z: z["teil"] == "Hold-out" and not z["v1"],
                "Hold-out",
            ),
        )
        for name, auswahl, teilname in summen:
            for weg in dict.fromkeys(z["weg"] for z in zeilen.values()):
                teil = [z for z in zeilen.values() if z["weg"] == weg and auswahl(z)]
                if teil:
                    liste.append(
                        {
                            "familie": name,
                            "weg": weg,
                            "teil": teilname,
                            "v1": all(z["v1"] for z in teil),
                            **{
                                k: sum(z[k] for z in teil)
                                for k in (
                                    "belege",
                                    "fehlerfrei",
                                    "felder",
                                    "richtig",
                                    "leer",
                                    "pruefen",
                                    "still",
                                )
                            },
                        }
                    )
        out[gruppe] = liste
    return out


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--generator", type=int, default=44, help="Anzahl erzeugter Drucke (Standard 44)"
    )
    ap.add_argument("--seed", type=int, default=2026, help="Seed des Generators (Standard 2026)")
    ap.add_argument(
        "--lernen", type=int, default=5, help="Paare je Verkäufer zum Anlernen (Standard 5)"
    )
    ap.add_argument("--verfahren", nargs="+", default=list(VERFAHREN), choices=VERFAHREN)
    ap.add_argument(
        "--fiktiv",
        type=Path,
        default=FIKTIV,
        help="Ordner mit Rechnungen/ und Referenzdaten/ der fiktiven Testrechnungen",
    )
    ap.add_argument(
        "--set",
        type=Path,
        nargs="*",
        default=None,
        help="Testset-Ordner (Rechnungen/, Referenzdaten/, optional Referenzdaten/holdout/); "
        "Standard: alle unter beispiele/sets/, „--set“ ohne Ordner: keine",
    )
    ap.add_argument("--md", type=Path, help="Ergebnis als Markdown speichern")
    ap.add_argument("--json", type=Path, help="Ergebnis als JSON speichern")
    ap.add_argument(
        "--max-fehl", type=int, default=60, help="Fehlschläge auf der Konsole (0 = alle)"
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    e = ausfuehren(args)
    print(markdown(e, max_fehl=args.max_fehl or None))
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(markdown(e), encoding="utf-8")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(e, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
