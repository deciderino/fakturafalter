# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""PDF-Erkennung als zweite Quelle neben der CSV (die CSV bleibt die maßgebliche Quelle).

1. Gegenprüfung: Werte aus der CSV werden im Druck-PDF (Textebene) gesucht. Fehlt ein Wert
   im Druck, geht die Rechnung nach „Zu prüfen“ – mit Feld, CSV-Wert und Druck-Wert.
2. Anlernen: Aus Paaren PDF + CSV lernt das Programm je Layout, *wo* die Werte stehen
   (Anker-Text davor/darüber oder feste Lage, Tabellenspalten). Die Vorlage liegt lesbar als
   YAML im Ordner ``angelernt/`` neben dem Profil, mit Fingerabdruck und Trefferquote.
3. Nur-PDF: Erst wenn eine Vorlage über N Rechnungen in Folge alle Werte richtig gefunden hat,
   darf ein PDF ohne CSV verarbeitet werden – immer mit Pflichtprüfung und Summenprüfung.

Alles lokal und nachvollziehbar: Wörter + Koordinaten aus pdfplumber, feste Regeln, kein ML.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from . import adapter_pdf, rechnen, steuerfaelle, zahlungsziel
from .anschrift import (  # noqa: F401
    _LAND,
    _NUR_HAUSNR,
    _NUR_PLZ,
    _PLZ_IN_ZEILE,
    _POSTFACH,
    _STRASSE,
    PLZ_ORT,
    anschrift_teilen,
    anschrift_zerlegen,
    strassenzeile,
    vermerkzeile,
)
from .aufbau import KAEUFER_FELDER, rechnung_bauen
from .modell import Herkunft, Rechnung
from .pflichtpruefung import iban_gueltig

log = logging.getLogger(__name__)

# Einstellungen im Profil (Block „pdf_erkennung“); fehlt der Block, gelten diese Werte.
PRUEFFELDER = {  # Feld: (Typ, Name in Meldungen)
    "BT-1": ("text", "Rechnungsnummer"),
    "BT-2": ("datum", "Rechnungsdatum"),
    "BT-72": ("datum", "Leistungsdatum"),
    "BG-14": ("zeitraum", "Leistungszeitraum"),
    "BT-31": ("kennung", "USt-IdNr."),
    "BT-32": ("kennung", "Steuernummer"),
    "BT-84": ("kennung", "IBAN"),
    "BT-109": ("betrag", "Nettosumme"),
    "BT-110": ("betrag", "Umsatzsteuer"),
    "BT-112": ("betrag", "Bruttosumme"),
    "BT-119": ("saetze", "Steuersatz"),
}
STANDARD = {
    "gegenpruefung": True,
    "felder": list(PRUEFFELDER),
    "toleranz": str(rechnen.TOLERANZ),
    "anlernen": True,
    "nur_pdf": False,
    "nur_pdf_ab": 5,
}
_KAEUFER_NAMEN = {
    "BT-44": "Kundenname",
    "BT-50": "Straße des Kunden",
    "BT-51": "Adresszusatz des Kunden",
    "BT-53": "PLZ des Kunden",
    "BT-52": "Ort des Kunden",
    "BT-55": "Land des Kunden",
    "BT-48": "USt-IdNr. des Kunden",
    "BT-47": "Registernummer des Kunden",
    "BT-49": "E-Mail-Adresse des Kunden für E-Rechnungen",
    "BT-56": "Ansprechpartner des Kunden",
    "BT-57": "Telefon des Kunden",
    "BT-58": "E-Mail des Kunden",
}
ZUSATZFELDER = {
    "kundennummer": "Kundennummer",
    "BT-13": "Bestellnummer",
    "BT-20": "Zahlungsbedingung",
    **{f: _KAEUFER_NAMEN.get(f, f"Kunde {f}") for f in KAEUFER_FELDER},
    # ab 0.9.7: Steuer-Sonderfälle, Leitweg-ID, Fremdwährung
    "steuerhinweis": "Steuerhinweis",
    "BT-10": "Leitweg-ID",
    "BT-80": "Lieferland",
    "BT-5": "Währung",
    "kurs": "Umrechnungskurs",
    "BT-111": "Umsatzsteuer in EUR",
}
# Typ der Zusatzfelder, die keine Texte sind (Vergleich beim Lernen/Bewerten, Lesen im Nur-PDF-Lauf)
ZUSATZ_TYP = {"BT-111": "betrag", "kurs": "kurs", "BT-55": "land", "BT-80": "land"}
# Freiwillige Kopffelder, die ein Nur-PDF-Lauf aus der Vorlage übernimmt (zusätzlich zu den Käuferfeldern)
NUR_PDF_ZUSATZ = ("steuerhinweis", "BT-10", "BT-80", "BT-5", "kurs", "BT-111")
# Freiwillige Felder: eine Abweichung setzt den Freigabe-Zähler („N Rechnungen in Folge ohne Korrektur“)
# nicht zurück – nur Pflichtfelder, Beträge, Zahlungsbedingung und Positionen zählen.
ZAEHLER_FREIWILLIG = ("BT-13", "kundennummer", "BT-51")

LUECKE = 8.0  # Abstand in pt, ab dem zwei Wörter zu verschiedenen Abschnitten gehören
NICHT_GEFUNDEN = "fehlt"  # Druck-Wert in Meldungen, wenn nichts gefunden wurde (ohne Leerzeichen)

# Woran ein Wert im Druck zu erkennen ist (Text davor/darüber). (positiv, negativ, Pflicht positiv?)
KAEUFERANSCHRIFT = ("BT-50", "BT-51", "BT-53", "BT-52", "BT-55")
# Regel „Anschrift als Block“: ein Rahmen um die ganze Käuferanschrift, beim Lesen in Teile zerlegt
ANSCHRIFT_BLOCK = "kaeufer_block"
BLOCKFELDER = ("BT-44", "BT-51", "BT-50", "BT-53", "BT-52")
SCHLUESSELWOERTER = {
    "BT-1": (
        r"nr|nummer|\bno\b|beleg|rechnung|invoice",
        r"kund|bestell|auftrag|steuer|ust|customer|order|iban|datum|date|"
        r"telefon|\btel\b|fax|vorwahl|mobil|phone|artikel|art\.?-?nr|sku|\bpos\b",
        False,
    ),
    "BT-2": (
        r"datum|date",
        r"liefer|leistung|versand|fällig|due|service|delivery|shipping|bestell|zeitraum|period",
        True,
    ),
    "BT-72": (
        r"liefer|leistung|versand|service|delivery|shipping|ausgeführt",
        r"fällig|due|zeitraum|period",
        True,
    ),
    "BG-14": (r"leistung|zeitraum|monat|period|abrechnung|service", r"fällig|due", True),
    "BT-109": (
        r"netto|zwischensumme|subtotal|\bnet\b|summe|warenwert|ohne (?:mwst|ust)",
        r"brutto|ust|mwst|umsatzsteuer|vat|\btax\b|zahl|gesamtbetrag|endbetrag|endsumme|\btotal\b",
        True,
    ),
    "BT-110": (
        r"ust|mwst|umsatzsteuer|steuer|vat|\btax\b",
        r"netto|brutto|nr|id|gesamtbetrag|\btotal\b",
        True,
    ),
    "BT-112": (
        r"brutto|gesamt|\btotal\b|zahl|endbetrag|endsumme|rechnungsbetrag|amount due",
        r"netto|zwischen|subtotal|\bnet\b|ust|mwst|vat|seite|blatt|page|anzahl",
        True,
    ),
    "BT-31": (r"ust|vat|id", r"", False),
    "BT-32": (r"steuer|st\.?-?nr|stnr|tax", r"", False),
    "BT-84": (r"iban", r"", False),
    "kundennummer": (r"kund|customer|kd|debitor", r"", False),
    "BT-13": (r"bestell|auftrag|order|ihre|referenz", r"", False),
}
_MONATE = {
    "januar": 1,
    "jan": 1,
    "january": 1,
    "februar": 2,
    "feb": 2,
    "february": 2,
    "märz": 3,
    "mär": 3,
    "mrz": 3,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "juni": 6,
    "jun": 6,
    "june": 6,
    "juli": 7,
    "jul": 7,
    "july": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
    "december": 12,
    "dec": 12,
}


# ---------------------------------------------------------------- Wörter, Zeilen, Abschnitte
@dataclass
class Wort:
    t: str
    x0: float
    x1: float
    top: float
    seite: int
    bottom: float = 0.0  # nur für die Anzeige (Markierung im Anlern-Assistenten)


@dataclass
class Zeile:
    seite: int
    top: float
    woerter: list[Wort]
    abschnitte: list[list[Wort]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.t for w in self.woerter)


def abschnitte_bilden(woerter: list[Wort]) -> list[list[Wort]]:
    """Wörter einer Zeile (links nach rechts) -> Abschnitte; eine Lücke über ``LUECKE`` beginnt einen neuen."""
    out: list[list[Wort]] = []
    for w in woerter:
        if out and w.x0 - out[-1][-1].x1 <= LUECKE:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def zeilen_aus(seiten: list[adapter_pdf.Seite], indizes: list[int] | None = None) -> list[Zeile]:
    """Seiten -> Zeilen in Lesereihenfolge; jede Zeile in Abschnitte (große Lücken) geteilt."""
    out = []
    for s in seiten:
        if indizes is not None and s.nr not in indizes:
            continue
        for top, ws in adapter_pdf.zeilen(s.woerter, tol=3):
            woerter = [
                Wort(
                    unicodedata.normalize("NFC", w["text"]),
                    float(w["x0"]),
                    float(w["x1"]),
                    float(w["top"]),
                    s.nr,
                    float(w.get("bottom") or float(w["top"]) + 9),
                )
                for w in ws
            ]
            out.append(Zeile(s.nr, float(top), woerter, abschnitte_bilden(woerter)))
    return out


# ---------------------------------------------------------------- Werte lesen und vergleichen
def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(s)).split()).casefold()


def kompakt(s: str) -> str:
    return re.sub(r"\s+", "", str(s)).upper()


_BETRAG = {
    "de": (r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}", ".", ","),
    "en": (r"-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}", ",", "."),
}
_ZAHL = {
    "de": (r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", ".", ","),
    "en": (r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", ",", "."),
}


# Währungszeichen neben Beträgen (ab 0.9.7 nicht nur €/EUR): werden beim Lesen entfernt und zählen in der Tabelle
# weder als Einheit noch als Steuerkennzeichen. Welche Währung gilt, ermittelt ``waehrung_im_druck``.
WAEHRUNGSZEICHEN = (
    "€",
    "EUR",
    "(€)",
    "$",
    "US$",
    "USD",
    "£",
    "GBP",
    "CHF",
    "Fr.",
    "SFr.",
    "JPY",
    "¥",
)
_WAEHRUNG_RX = re.compile(r"\s+|€|EUR|US\$|\$|USD|£|GBP|CHF|S?Fr\.|JPY|¥")


def _zahl(text: str, muster: dict, fmt: str | None = None) -> list[tuple[Decimal, str]]:
    t = _WAEHRUNG_RX.sub("", str(text)).replace("\u2212", "-")
    if t.endswith("-") and not t.startswith("-"):
        t = "-" + t[:-1]
    out = []
    for f, (rx, tausend, dez) in muster.items():
        if (fmt is None or f == fmt) and re.fullmatch(rx, t):
            try:
                out.append((Decimal(t.replace(tausend, "").replace(dez, ".")), f))
            except InvalidOperation:  # pragma: no cover
                pass
    return out


def betraege(text: str, fmt: str | None = None) -> list[tuple[Decimal, str]]:
    """„1.234,56 €“ -> [(1234.56, 'de')]; „1,234.56“ -> [(1234.56, 'en')]."""
    return _zahl(text, _BETRAG, fmt)


def zahlen(text: str, fmt: str | None = None) -> list[tuple[Decimal, str]]:
    """Mengen: beliebig viele Nachkommastellen, auch ganze Zahlen."""
    return _zahl(text, _ZAHL, fmt)


def daten(text: str) -> list[date]:
    """Datum in üblichen Schreibweisen: 28.10.2026, 28.10.26, 2026-10-28, 28/10/2026, 28. Oktober 2026."""
    t = " ".join(str(text).split()).strip(" ,;:")
    out = []
    for rx, reihenfolge in (
        (r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})", "tmj"),
        (r"(\d{4})-(\d{2})-(\d{2})", "jmt"),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "tmj"),
    ):
        m = re.fullmatch(rx, t)
        if m:
            w = dict(zip(reihenfolge, (int(x) for x in m.groups())))
            j = w["j"] + 2000 if w["j"] < 100 else w["j"]
            try:
                out.append(date(j, w["m"], w["t"]))
            except ValueError:
                pass
    m = re.fullmatch(r"(\d{1,2})\.?\s*([^\W\d_]+)\.?\s+(\d{4})", t)
    if m and m[2].casefold() in _MONATE:
        try:
            out.append(date(int(m[3]), _MONATE[m[2].casefold()], int(m[1])))
        except ValueError:
            pass
    return out


_D = r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\.\s?[^\W\d_]+\.?\s\d{4}"


def zeitraum(text: str) -> tuple[date, date] | None:
    """„01.10.2026 – 31.10.2026“, „vom … bis …“, „Oktober 2026“, „10/2026“, „2026-10“ -> (von, bis)."""
    import calendar

    t = " ".join(str(text).split()).strip(" ,;:")
    m = re.fullmatch(rf"(?:vom\s+)?({_D})\s*(?:–|—|-|bis)\s*({_D})", t)
    if m:
        a, b = daten(m[1]), daten(m[2])
        return (a[0], b[0]) if a and b else None
    j = mo = None
    m = re.fullmatch(r"([^\W\d_]+)\.?\s+(\d{4})", t)
    if m and m[1].casefold() in _MONATE:
        j, mo = int(m[2]), _MONATE[m[1].casefold()]
    m = re.fullmatch(r"(\d{1,2})[./](\d{4})", t) or None
    if m:
        j, mo = int(m[2]), int(m[1])
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m:
        j, mo = int(m[1]), int(m[2])
    if j and mo and 1 <= mo <= 12:
        return date(j, mo, 1), date(j, mo, calendar.monthrange(j, mo)[1])
    return None


def gleich(typ: str, soll, text: str, tol: Decimal = rechnen.TOLERANZ) -> bool:
    if typ == "text":
        return norm(text) == norm(soll)
    if typ == "kennung":
        return kompakt(text) == kompakt(soll)
    if typ == "datum":
        return soll in daten(text)
    if typ == "betrag":
        return any(abs(d - Decimal(str(soll))) <= tol for d, _ in betraege(text))
    if typ == "zeitraum":
        return zeitraum(text) == tuple(soll)
    if typ == "zahl":
        return any(d == Decimal(str(soll)) for d, _ in zahlen(text))
    if typ == "kurs":
        return kurs_aus_text(text) == Decimal(str(soll))
    if typ == "land":
        return steuerfaelle.land_code(text) == str(soll).upper()
    return False


def kurs_aus_text(text: str, waehrung: str = "") -> Decimal | None:
    """„1 EUR = 1,0850 USD“, „Kurs 1,0850“ oder nur „1,0850“ -> 1.0850 (Richtung 1 EUR = x Fremdwährung)."""
    k, _fw = steuerfaelle.kurs_lesen(text, waehrung)
    return k if k is not None else steuerfaelle.dezimal(text)


def anzeige(typ: str, w) -> str:
    """Wert für Meldungen – ohne Leerzeichen (die Prüfansicht trennt daran)."""
    if w is None or w == "":
        return NICHT_GEFUNDEN
    if typ == "datum" and isinstance(w, date):
        return w.strftime("%d.%m.%Y")
    if typ == "zeitraum" and isinstance(w, tuple):
        return f"{w[0]:%d.%m.%Y}–{w[1]:%d.%m.%Y}"
    if typ == "betrag" and isinstance(w, Decimal):
        return str(w.quantize(rechnen.CENT))
    if typ == "saetze" and isinstance(w, (list, tuple)):
        return "+".join(f"{_satz(s)}%" for s in w) or NICHT_GEFUNDEN
    return re.sub(r"\s+", "\u00a0", str(w).strip())


def _satz(s) -> str:
    d = Decimal(str(s))
    return (
        str(d.quantize(Decimal(1)))
        if d == d.to_integral()
        else str(d.normalize()).replace(".", ",")
    )


# Optionale Nummernfelder: lieber leer als falsch (ein Datum oder Betrag als Bestellnummer)
OPTIONALE_NUMMERN = ("BT-13", "kundennummer")
_DATUM_FORM = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})$|^\d{4}-\d{2}-\d{2}$")
_BETRAG_FORM = re.compile(r"^-?\d{1,3}(?:[.\s]\d{3})*,\d{2}$|^-?\d+,\d{2}$")
# Wie weit rechts neben der Beschriftung der Wert noch stehen darf (pt; ein Tabstopp, keine halbe Seite)
NEBEN_MAX = 120


def nummer_passt(text: str) -> bool:
    """Taugt ``text`` als Bestell-/Kundennummer? Ziffer nötig; kein Datum, Betrag, Prozentsatz, keine weitere
    Beschriftung („Datum:“) und nicht überlang."""
    t = " ".join(str(text).split())
    if not t or len(t) > 35 or not re.search(r"\d", t):
        return False
    if re.search(r"[€%]|\bEUR\b", t, re.I) or any(w.endswith(":") for w in t.split()):
        return False
    return not (_DATUM_FORM.match(t) or _BETRAG_FORM.match(t) or daten(t) and len(t) <= 12)


def nummer_rechts(
    seg_rest: list[Wort], naechster: list[Wort] | None, ende_label: float, label_offen: bool = False
) -> list[Wort]:
    """Wert einer Nummernbeschriftung: das erste Wort rechts daneben in derselben Zeile – Rest des Abschnitts
    oder nächster Abschnitt, höchstens ``NEBEN_MAX`` pt entfernt. [] = Feld im Druck leer. ``label_offen``:
    Beschriftung ohne Doppelpunkt („Ihre Bestellung Nr. 4711“) – bis zu drei Wörter ohne Ziffer gehören noch
    zur Beschriftung."""
    if label_offen:
        n = 0
        while n < min(3, len(seg_rest)) and re.fullmatch(r"[^\W\d_][\w.-]{0,13}", seg_rest[n].t):
            n += 1
        if n:
            ende_label, seg_rest = seg_rest[n - 1].x1, seg_rest[n:]
    for ws in (seg_rest, naechster or []):
        ws = [w for w in ws if re.search(r"\w", w.t)]
        if not ws:
            continue
        if ws[0].x0 - ende_label > NEBEN_MAX:
            return []
        return [ws[0]] if nummer_passt(ws[0].t) else []
    return []


def lesen_als(typ: str, text: str):
    if typ == "datum":
        d = daten(text)
        return d[0] if d else None
    if typ == "betrag":
        b = betraege(text)
        return b[0][0] if b else None
    if typ == "zeitraum":
        return zeitraum(text)
    if typ == "land":
        return steuerfaelle.land_code(text) or None
    if typ == "kurs":
        return " ".join(text.split()) or None  # Kurszeile; aufbau liest Richtung und Wert
    return " ".join(text.split()) or None


_TYP_JE_FELD = {
    "BT-53": "plz",
    "BT-2": "datum",
    "BT-72": "datum",
    "BT-109": "betrag",
    "BT-110": "betrag",
    "BT-112": "betrag",
    "BT-119": "satz",
    "BT-31": "ustid",
    "BT-48": "ustid",
    "BT-84": "iban",
    "BT-3": "belegart",
    "BT-25": "bezug",
}

# ---------------------------------------------------------------- Belegart (BT-3) und Rechnungsbezug (BG-3)
# Nur aus einem angelernten Rahmen (Titel im Druck bzw. Bezugszeile), nie aus der ganzen Seite geraten.
BELEG_NAMEN = {"BT-3": "Belegart", "BT-25": "Bezugsrechnung"}
_GUTSCHRIFT = re.compile(r"\bgutschrift\b", re.I)


def belegart_code(text: str) -> str:
    """Titel im Druck -> BT-3: enthält er das Wort „Gutschrift“, 381 (Credit Note), sonst 380. Self-Billing
    (389) und Korrektur (384) werden nicht aus dem Druck abgeleitet."""
    return "381" if _GUTSCHRIFT.search(str(text or "")) else "380"


def bezug_zerlegen(text: str) -> tuple[str, date | None]:
    """Bezugszeile („NB-26-0990 vom 01.10.2026“, „zu Rechnung Nr. 4711, 1. Oktober 2026“) -> (BT-25, BT-26):
    das erste Wort mit Ziffer, das kein Datum ist, und das Datum daneben (oder None)."""
    t = " ".join(str(text or "").split())
    d = next((x for m in re.finditer(_D, t) for x in daten(m[0])), None)
    for w in re.sub(_D, " ", t).split():
        w = w.strip(",;:()")
        if re.search(r"\d", w) and nummer_passt(w):
            return w, d
    return "", d


_AUSLAND_PLZ = re.compile(r"^(?:[A-Z]{1,2}-)?\d{4}(?:\s?[A-Z]{2})?$|^\d{5}-\d{4}$")


def wert_passt(feld: str, text: str, ausland: bool = False) -> bool:
    """Typprüfung je Feld, bevor ein gelesener Wert übernommen wird: PLZ 5 Ziffern, gültiges Datum,
    USt-IdNr. (DE + 9 Ziffern), IBAN mit Prüfziffer, Betrag, Steuersatz 0–30 %. Leerer Text passt nie."""
    t = " ".join(str(text or "").split())
    if not t:
        return False
    art = _TYP_JE_FELD.get(feld)
    if (
        art == "plz"
    ):  # ab 0.9.7 mit Landzeile (ausland) auch „9020“, „A-9020“, „1012 AB“, „02110-1234“
        return _NUR_PLZ.match(t) is not None or (ausland and _AUSLAND_PLZ.match(t) is not None)
    if art == "datum":
        d = daten(t)
        return bool(d) and 2000 <= d[0].year <= 2099
    if art == "betrag":
        return bool(betraege(t) or zahlen(t))
    if art == "satz":
        m = re.fullmatch(r"(\d{1,2}(?:[.,]\d{1,2})?)\s?%?", t)
        return m is not None and Decimal(m[1].replace(",", ".")) <= 30
    if art == "ustid":
        u = t.replace(" ", "").upper()
        return (
            re.fullmatch(r"DE\d{9}", u) is not None
            if u.startswith("DE")
            else re.fullmatch(r"[A-Z]{2}[0-9A-Z+*]{2,13}", u) is not None
        )
    if art == "iban":
        return iban_gueltig(t)
    if art == "belegart":
        return len(t) <= 60 and re.search(r"[^\W\d_]", t) is not None
    if art == "bezug":
        return bool(bezug_zerlegen(t)[0])
    return True


def _maxlaenge(typ: str, soll) -> list[int]:
    if typ == "text":
        return [len(str(soll).split())]
    return {
        "kennung": [1, 2, 3, 4, 5, 6],
        "betrag": [1, 2],
        "datum": [1, 2, 3],
        "zeitraum": [1, 2, 3, 4, 5],
        "kurs": [1, 2, 3, 4, 5, 6],
        "land": [1, 2, 3],
    }.get(typ, [1])


def _spannen(zeilen: list[Zeile], laengen: list[int]):
    """Alle zusammenhängenden Wortfolgen innerhalb eines Abschnitts: (zeile, abschnitt, von, bis)."""
    for zi, z in enumerate(zeilen):
        for si, seg in enumerate(z.abschnitte):
            for i in range(len(seg)):
                for n in laengen:
                    if i + n <= len(seg):
                        yield zi, si, i, i + n


def _text(ws: list[Wort]) -> str:
    return " ".join(w.t for w in ws)


def kommt_vor(zeilen: list[Zeile], typ: str, soll, tol: Decimal) -> bool:
    if typ == "kennung":
        k = kompakt(soll)
        return any(k in kompakt(z.text) for z in zeilen)
    return any(
        gleich(typ, soll, _text(zeilen[zi].abschnitte[si][i:j]), tol)
        for zi, si, i, j in _spannen(zeilen, _maxlaenge(typ, soll))
    )


# ---------------------------------------------------------------- Soll-Werte aus der CSV-Rechnung
def soll_wert(r: Rechnung, feld: str):
    s = r.summen
    if feld in KAEUFER_FELDER:
        obj = r.kaeufer
        for teil in KAEUFER_FELDER[feld].split("."):
            obj = getattr(obj, teil)
        if feld == "BT-55" and obj == "DE":
            return None  # Inland: steht selten im Druck, nicht als Regel lernen
        return obj or None
    werte = {
        "BT-1": r.nummer or None,
        "BT-2": r.datum,
        "BT-72": r.leistungsdatum,
        "BG-14": (r.leistung_von, r.leistung_bis) if r.leistung_von and r.leistung_bis else None,
        "BT-31": r.verkaeufer.ust_id or None,
        "BT-32": r.verkaeufer.steuernummer or None,
        "BT-84": r.zahlung.iban or None,
        "BT-109": s.netto,
        "BT-110": s.ust if s.ust else None,
        "BT-112": s.brutto,
        # nur Regelbesteuerung (S): bei AE/K/G/O/E steht kein Satz im Druck, der gelernt werden könnte
        "BT-119": sorted({z.steuer.satz for z in s.steuerzeilen if z.steuer.kategorie == "S"})
        or None,
        "kundennummer": r.kundennummer or None,
        "BT-13": r.bestellnummer or None,
        "steuerhinweis": r.steuerhinweis or None,
        "BT-10": r.leitweg_id or None,
        "BT-80": (r.lieferung.anschrift.land or None)
        if r.lieferung.anschrift.land not in ("", "DE")
        else None,
        "BT-5": r.waehrung if (r.waehrung or "EUR") != "EUR" else None,
        "kurs": r.kurs,
        "BT-111": r.ust_eur_quelle,
        "BT-20": r.zahlung.bedingungen or None,
        "BT-3": r.art or None,
        "BT-25": (r.bezuege[0].nummer or None) if r.bezuege else None,
    }
    return werte.get(feld)


def feldtyp(feld: str) -> str:
    return PRUEFFELDER[feld][0] if feld in PRUEFFELDER else ZUSATZ_TYP.get(feld, "text")


def feldname(feld: str) -> str:
    if feld == ANSCHRIFT_BLOCK:
        return "Anschrift des Kunden"
    if feld in BELEG_NAMEN:
        return BELEG_NAMEN[feld]
    return PRUEFFELDER[feld][1] if feld in PRUEFFELDER else ZUSATZFELDER.get(feld, feld)


# ---------------------------------------------------------------- Einstellungen und Ablage
def profil_name(profil: dict) -> str:
    return str(
        profil.get("profil") or profil.get("name") or Path(profil.get("_datei", "profil")).stem
    )


def einstellungen(profil: dict) -> dict:
    e = dict(STANDARD)
    e.update(profil.get("pdf_erkennung") or {})
    e["toleranz"] = Decimal(str(e["toleranz"]))
    e["nur_pdf_ab"] = int(e["nur_pdf_ab"])
    e["felder"] = [f for f in e["felder"] if f in PRUEFFELDER]
    return e


def ablage(profil: dict) -> Path:
    """Ordner der angelernten Vorlagen: ``angelernt/`` neben dem Profil."""
    return Path(profil.get("_basis", ".")) / "angelernt"


# Einheitencodes, die bis 0.4.8 gelernt wurden, aber nicht in BR-CL-23 stehen -> gültiger Code (Rec 21)
# Einheiten im Druck -> UN/ECE-Code (Rec. 20) und Name für die Anzeige
EINHEITEN: dict[str, str] = {
    "stk": "H87",
    "st": "H87",
    "stück": "H87",
    "stck": "H87",
    "pc": "H87",
    "pcs": "H87",
    "x": "H87",
    "std": "HUR",
    "h": "HUR",
    "stunde": "HUR",
    "stunden": "HUR",
    "hrs": "HUR",
    "min": "MIN",
    "tag": "DAY",
    "tage": "DAY",
    "kg": "KGM",
    "g": "GRM",
    "t": "TNE",
    "m": "MTR",
    "lfm": "MTR",
    "m²": "MTK",
    "m2": "MTK",
    "qm": "MTK",
    "m³": "MTQ",
    "m3": "MTQ",
    "cbm": "MTQ",
    "km": "KMT",
    "l": "LTR",
    "ltr": "LTR",
    "psch": "LS",
    "pausch": "LS",
    "pauschal": "LS",
    "pauschale": "LS",
    "ls": "LS",
    "satz": "SET",
    "set": "SET",
    "paar": "PR",
    "pkt": "XPK",
    "pak": "XPK",
    "rolle": "XRO",
    "karton": "XCT",
    "woche": "WEE",
    "wochen": "WEE",
    "monat": "MON",
    "monate": "MON",
    "mon": "MON",
    "mtl": "MON",
    "jahr": "ANN",
    "jahre": "ANN",
    "mm": "MMT",
    "cm": "CMT",
    "ml": "MLT",
    "kwh": "KWH",
    "dutzend": "DZN",
    "dtzd": "DZN",
    "pal": "XPX",
    "palette": "XPX",
    "paletten": "XPX",
    "sack": "XSA",
    "säcke": "XSA",
    "kiste": "XBX",
    "kisten": "XBX",
    "flasche": "XBO",
    "flaschen": "XBO",
    "blatt": "XST",
    "bogen": "XST",
}
EINHEIT_NAMEN: dict[str, str] = {
    "H87": "Stück",
    "C62": "Einheit",
    "HUR": "Stunde",
    "MIN": "Minute",
    "DAY": "Tag",
    "KGM": "Kilogramm",
    "GRM": "Gramm",
    "TNE": "Tonne",
    "MTR": "Meter",
    "MTK": "Quadratmeter",
    "MTQ": "Kubikmeter",
    "KMT": "Kilometer",
    "LTR": "Liter",
    "LS": "Pauschale",
    "SET": "Satz",
    "PR": "Paar",
    "XPK": "Packung",
    "XRO": "Rolle",
    "XCT": "Karton",
    "WEE": "Woche",
    "MON": "Monat",
    "ANN": "Jahr",
    "MMT": "Millimeter",
    "CMT": "Zentimeter",
    "MLT": "Milliliter",
    "KWH": "Kilowattstunde",
    "DZN": "Dutzend",
    "XPX": "Palette",
    "XSA": "Sack",
    "XBX": "Kiste",
    "XBO": "Flasche",
    "XST": "Blatt",
}


def einheit_code(text: str) -> str | None:
    """Einheit im Druck („Stk.“, „Std.“) -> UN/ECE-Code, sonst None (allgemeine Zuordnung; Gelerntes geht vor)."""
    t = norm(text).strip(".")
    return EINHEITEN.get(t) or (t.upper() if t.upper() in EINHEIT_NAMEN else None)


# ganze Zahl mit oder ohne Tausenderpunkte, optional Dezimalteil („5000“, „5.000“, „12,5“)
_MENGE_ZAHL = r"[+-]?(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:[,.]\d+)?"


def einheit_aus_menge(text: str) -> str | None:
    """Einheit hinter der Mengenzahl („12 Std.“, „3 Stk“, „5000 Stk“), sonst None."""
    t = " ".join((text or "").split())
    m = re.match(rf"^({_MENGE_ZAHL})\s*(.*?)$", t)
    if not m:
        return None
    rest = m[2].strip()
    return rest if rest and einheit_code(rest) else None


def menge_ohne_einheit(text: str) -> str:
    """Mengenzahl ohne angehängte Einheit („12 Std.“ -> „12“)."""
    t = " ".join((text or "").split())
    m = re.match(rf"^({_MENGE_ZAHL})\s*(.*?)$", t)
    if m and einheit_code(m[2].strip(" .,;")):
        return m[1]
    return t


def einheit_ohne_spalte(pos: list, gewaehlt: dict[str, str] | None = None) -> dict:
    """Vorlagenfelder ohne Einheitenspalte: Einheit aus der Mengenzelle, sonst H87.
    Ein stilles H87 zu streichen würde auf Belegen ohne gedruckte Einheit (Soll H87) die Quote
    „richtig“ senken; Nutzerwahl unter ``*`` hat Vorrang."""
    gewaehlt = gewaehlt or {}
    if gewaehlt.get("*"):
        return {"einheit_fest": gewaehlt["*"]}
    lesbar = {
        p.einheit_text: gewaehlt.get(p.einheit_text) or einheit_code(p.einheit_text)
        for p in pos
        if p.einheit_text and einheit_code(p.einheit_text)
    }
    if lesbar and all(p.einheit_text in lesbar for p in pos):
        if len(set(lesbar.values())) == 1:
            return {"einheit_fest": next(iter(lesbar.values()))}
        return {"einheiten": dict(lesbar)}
    if lesbar:
        return {
            "einheiten": {
                **lesbar,
                OHNE_EINHEIT: gewaehlt.get(OHNE_EINHEIT) or "H87",
            }
        }
    return {"einheit_fest": "H87"}


def einheiten_mapping(pv: dict, schluessel: list[str] | None = None) -> dict:
    """Einheiten-Mapping für ``rechnung_bauen``: Gelerntes, sonst Code aus dem Druck, sonst fest / prüfen."""
    einh = dict(pv.get("einheiten") or {"*": pv.get("einheit_fest", "")})
    for k in schluessel or []:
        if k and k != OHNE_EINHEIT and k not in einh and (c := einheit_code(k)):
            einh[k] = c
    return {**einh, "unbekannt": "pruefen"}


ALTE_EINHEITEN = {"PK": "XPK", "RO": "XRO", "CT": "XCT"}


def einheiten_aktualisieren(v: dict) -> None:
    """Ältere Vorlage: ungültige Einheitencodes in ``positionen.einheiten``/``einheit_fest`` beim Laden ersetzen
    (Format bleibt gleich; gespeichert wird beim nächsten Fortschreiben)."""
    pv = v.get("positionen")
    if not isinstance(pv, dict):
        return
    if isinstance(pv.get("einheiten"), dict):
        pv["einheiten"] = {
            k: ALTE_EINHEITEN.get(c, c) if isinstance(c, str) else c
            for k, c in pv["einheiten"].items()
        }
    if isinstance(pv.get("einheit_fest"), str):
        pv["einheit_fest"] = ALTE_EINHEITEN.get(pv["einheit_fest"], pv["einheit_fest"])


def vorlagen_laden(profil: dict) -> list[dict]:
    out = []
    for p in sorted(ablage(profil).glob(f"{profil_name(profil)}-*.yaml")):
        try:
            v = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(v, dict) and v.get("profil") == profil_name(profil):
            einheiten_aktualisieren(v)
            v["_datei"] = str(p)
            out.append(v)
    return out


def vorlage_speichern(v: dict, profil: dict) -> Path:
    ziel = ablage(profil) / f"{v['profil']}-{v['kennung']}.yaml"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    daten_ = {k: w for k, w in v.items() if not k.startswith("_")}
    kopf = (
        "# Angelernte PDF-Vorlage (automatisch erzeugt). Lesbar und änderbar; gelöscht wird sie\n"
        "# beim nächsten Paar PDF + CSV neu angelernt. Koordinaten in pt, Seite 0 = erste, -1 = letzte.\n"
    )
    from . import dateien

    dateien.schreiben(
        ziel, kopf + yaml.safe_dump(daten_, allow_unicode=True, sort_keys=False, width=120)
    )
    v["_datei"] = str(ziel)
    return ziel


def passt(v: dict, zeilen: list[Zeile]) -> bool:
    """Fingerabdruck: alle festen Texte und Kennungen (USt-IdNr./IBAN) des Layouts kommen im PDF vor."""
    alles = " ".join(norm(z.text) for z in zeilen)
    kpt = kompakt(alles)
    e = v.get("erkennung") or {}
    o = adapter_pdf.ohne_steuerzeichen  # ältere Vorlagen: „(cid:10)“
    return (
        bool(e.get("texte") or e.get("kennungen"))
        and all(norm(o(t)) in alles for t in e.get("texte", []))
        and all(kompakt(o(k)) in kpt for k in e.get("kennungen", []))
    )


def vorlage_finden(vorlagen: list[dict], zeilen: list[Zeile]) -> dict | None:
    kand = [v for v in vorlagen if passt(v, zeilen)]
    e = lambda v: (
        len((v.get("erkennung") or {}).get("texte", []))
        + len((v.get("erkennung") or {}).get("kennungen", []))
    )  # noqa: E731
    return max(kand, key=e) if kand else None


def sicher(v: dict | None, es: dict) -> bool:
    if not v or not v.get("positionen") or not {"BT-1", "BT-2"} <= set(v.get("felder", {})):
        return False
    return int((v.get("statistik") or {}).get("folge_treffer", 0)) >= es["nur_pdf_ab"]


def trefferquote(v: dict) -> float | None:
    """Mittel der Trefferquoten aller Rechnungen nach der ersten (die erste lernt nur)."""
    verlauf = (v.get("statistik") or {}).get("verlauf") or []
    return round(sum(verlauf) / len(verlauf), 3) if verlauf else None


# ---------------------------------------------------------------- Kopffelder: Regeln lernen und anwenden
def _tok(t: str) -> str:
    return "#" if re.search(r"\d", t) else t


def _anker_passt(ws: list[Wort], anker: list[str]) -> bool:
    return len(ws) == len(anker) and all(
        (a == "#" and re.search(r"\d", w.t)) or a == w.t for w, a in zip(ws, anker)
    )


def _seite_rel(seite: int, zeilen: list[Zeile]) -> int:
    seiten = sorted({z.seite for z in zeilen})
    i = seiten.index(seite)
    return 0 if i == 0 else -1 if i == len(seiten) - 1 else i


def _seite_zeilen(zeilen: list[Zeile], rel: int) -> list[Zeile]:
    seiten = sorted({z.seite for z in zeilen})
    try:
        s = seiten[rel]
    except IndexError:
        return []
    return [z for z in zeilen if z.seite == s]


def _anker_ok(anker: list[str], variabel: set[str]) -> bool:
    """Ein Anker muss mindestens ein festes Wort enthalten, das kein Wert dieser Rechnung ist."""
    return any(a != "#" and norm(a) not in variabel for a in anker) and not any(
        norm(a) in variabel for a in anker
    )


def _nehmen(ws: list[Wort], regel: dict) -> list[Wort]:
    return ws if regel.get("ende") else ws[: regel.get("n", 1)]


def woerter_im_bereich(
    zs: list[Zeile], x0: float, top: float, x1: float, bottom: float
) -> list[list[Wort]]:
    """Wörter, deren Mitte im Rahmen liegt, zeilenweise (oben nach unten, links nach rechts)."""
    out = []
    for z in sorted(zs, key=lambda z: z.top):
        ws = [
            w
            for w in z.woerter
            if x0 <= (w.x0 + w.x1) / 2 <= x1 and top <= (w.top + w.bottom) / 2 <= bottom
        ]
        if ws:
            out.append(sorted(ws, key=lambda w: w.x0))
    return out


def _bereich_rahmen(regel: dict, zs: list[Zeile]) -> tuple[float, float, float, float] | None:
    """Rahmen der Regel „bereich“ auf dieser Seite: fest – oder, mit Anker, um den Versatz der nächsten passenden
    Beschriftung verschoben. -> None, wenn der Anker fehlt."""
    x0, top, x1, bottom = regel["rahmen"]
    anker = [a for a in map(adapter_pdf.ohne_steuerzeichen, regel.get("anker") or []) if a]
    if anker:
        treffer = []
        for z in zs:
            for seg in z.abschnitte:
                for k in range(len(seg) - len(anker) + 1):
                    if _anker_passt(seg[k : k + len(anker)], anker):
                        treffer.append(
                            (
                                abs(z.top - regel["anker_top"])
                                + abs(seg[k].x0 - regel["anker_x0"]) / 4,
                                seg[k].x0 - regel["anker_x0"],
                                z.top - regel["anker_top"],
                            )
                        )
        if not treffer:
            return None
        _, dx, dy = min(treffer)
        x0, x1, top, bottom = x0 + dx, x1 + dx, top + dy, bottom + dy
    return x0, top, x1, bottom


def _bereich_auslesen(regel: dict, zs: list[Zeile]) -> tuple[str, list[Wort]] | None:
    """Regel „bereich“: fester Rahmen auf der Seite – oder, mit Anker, relativ zur nächsten passenden
    Beschriftung (der Rahmen wandert mit, wenn die Beschriftung im nächsten Druck höher/tiefer steht)."""
    rahmen = _bereich_rahmen(regel, zs)
    if rahmen is None:
        return None
    zeilen_ws = woerter_im_bereich(zs, *rahmen)
    if not zeilen_ws:
        return None
    ws = [w for z in zeilen_ws for w in z]
    trenner = "\n" if regel.get("block") else " "
    return trenner.join(_text(z) for z in zeilen_ws), ws


SCHRIFT_KLEINER = (
    0.8  # pt: so viel kleiner als die übrige Anschrift gilt eine Namenszeile als Vermerk
)
SPALTEN_LUECKE = 2 * LUECKE  # pt: größere Lücke in Name/Straße = zweite Spalte im Rahmen mitgelesen


def anschrift_brueche(zeilen_ws: list[list[Wort]]) -> dict[str, str]:
    """Strukturelle Brüche im gelesenen Anschriftblock -> Feld -> kurzer Prüfhinweis (mit BT-Nummer).

    Ändert die Zuordnung NICHT (Regel inkl. Ausnahmen in ``anschrift_zerlegen``), meldet nur „prüfen“ statt
    still falsch zu füllen, wo die Regel nicht eindeutig greift. Rein strukturell, ohne Schlüsselwörter:

    - unterste Zeile ist keine deutsche „PLZ Ort“ (Auslands-PLZ, Länderpräfix, Landzeile)
    - Zeile über PLZ/Ort ist nur eine Hausnummer (Straßenname eine Zeile höher)
    - Zeile über PLZ/Ort hat keine Straßenstruktur, die Zeile darüber schon (Zusatz unter der Straße)
    - erste Namenszeile kleiner gedruckt als die übrige Anschrift (Vermerk-/Rücksendezone im Namen)
    - große waagrechte Lücke in Name oder Straße (zweite Spalte im Rahmen mitgelesen)"""
    texte = [_text(z) for z in zeilen_ws]
    teile, rollen = anschrift_zerlegen(texte)
    out: dict[str, str] = {}
    if not teile:
        return out
    if "BT-53" not in teile and teile.get("BT-52"):
        out["BT-52"] = (
            "BT-52/BT-53: unterste Zeile ist keine deutsche „PLZ Ort“ (Ausland/Landzeile?) – prüfen"
        )
    strasse = teile.get("BT-50", "")
    namen = [i for i, r in enumerate(rollen) if r == "name"]
    if strasse and _NUR_HAUSNR.match(strasse):
        out["BT-50"] = (
            "BT-50: Straßenzeile ist nur eine Hausnummer – Straßenname steht evtl. im Namen, prüfen"
        )
    elif (
        strasse
        and "BT-52" not in out
        and not _STRASSE.match(strasse)
        and not _POSTFACH.match(strasse)
        and namen
        and _STRASSE.match(" ".join(texte[namen[-1]].split()))
    ):
        out["BT-50"] = (
            "BT-50: Straße steht evtl. eine Zeile höher (Zusatz unter der Straße?) – prüfen"
        )
    if (
        namen
        and all(vermerkzeile(texte[i]) for i in namen[:1])
        and not (teile.get("BT-51") or teile.get("BT-56"))
    ):
        out["BT-44"] = (
            "BT-44: Name beginnt mit einem Vermerk („z. Hd.“, „Abteilung“ …), kein Firmenname darüber – prüfen"
        )
    if len(namen) > 1:
        hoehe = [
            min(map(_hoehe, zeilen_ws[i]))
            for i, r in enumerate(rollen)
            if r != "weg" and zeilen_ws[i]
        ]
        rest = sorted(hoehe[1:])
        if rest and min(map(_hoehe, zeilen_ws[namen[0]])) < rest[len(rest) // 2] - SCHRIFT_KLEINER:
            out["BT-44"] = (
                "BT-44: erste Namenszeile kleiner gedruckt (Vermerk/Absender im Namen?) – prüfen"
            )
    for i, r in enumerate(rollen):
        z = zeilen_ws[i]
        if r in ("name", "strasse") and any(b.x0 - a.x1 > SPALTEN_LUECKE for a, b in zip(z, z[1:])):
            f = "BT-44" if r == "name" else "BT-50"
            out.setdefault(
                f, f"{f}: große Lücke in der Zeile – zweite Spalte im Rahmen mitgelesen? Prüfen"
            )
    return out


ANSCHRIFT_TIEFER = 40.0  # so weit (pt) unter dem Rahmen wird die Zeile „PLZ Ort“ noch gesucht


def _mitte(w: Wort) -> float:
    return (w.top + (w.bottom or w.top + 9)) / 2


def _hoehe(w: Wort) -> float:
    return max(1.0, (w.bottom or w.top + 9) - w.top)


RAHMEN_RAND = 2.0  # pt: Rand um gelesene Wörter, wenn daraus ein Rahmen (Markierung, Vorlage) wird


def rahmen_um(ws: list[Wort], rand: float = RAHMEN_RAND) -> tuple[float, float, float, float]:
    """Rahmen (x0, top, x1, bottom) um Wörter, mit ``rand`` pt Luft rundherum."""
    return (
        min(w.x0 for w in ws) - rand,
        min(w.top for w in ws) - rand,
        max(w.x1 for w in ws) + rand,
        max(max(w.bottom, w.top + 1) for w in ws) + rand,
    )


ORT_NEBEN_PLZ = (
    200.0  # pt: so weit rechts neben einer allein stehenden PLZ darf der Ort noch stehen
)


def auf_linie(mitte_a: float, mitte_b: float, hoehe: float) -> bool:
    """Gleiche Textzeile, wenn die Mitten höchstens ~40 % der Schrifthöhe (mindestens 2,5 pt) auseinanderliegen."""
    return abs(mitte_a - mitte_b) <= max(2.5, 0.4 * hoehe)


def ort_neben_plz(plz_x1: float, x0: float) -> bool:
    """Steht etwas, das bei ``x0`` beginnt, als Ort rechts neben einer PLZ, die bei ``plz_x1`` endet?"""
    return plz_x1 <= x0 <= plz_x1 + ORT_NEBEN_PLZ


def _zeilen_von(ws: list[Wort]) -> list[list[Wort]]:
    """Wörter -> Zeilen (oben nach unten, je Zeile links nach rechts). Gleiche Zeile, wenn die Mitten höchstens
    ~40 % der Schrifthöhe auseinanderliegen – leicht versetzte Grundlinie, andere Schriftgröße oder Fett
    trennen PLZ und Ort also nicht; Rundung von ``top`` spielt keine Rolle."""
    out: list[list[Wort]] = []
    for w in sorted(ws, key=lambda w: (w.seite, _mitte(w), w.x0)):
        if out and out[-1][0].seite == w.seite:
            z = out[-1]
            m = sum(map(_mitte, z)) / len(z)
            if auf_linie(_mitte(w), m, min(_hoehe(w), min(map(_hoehe, z)))):
                z.append(w)
                continue
        out.append([w])
    return [sorted(z, key=lambda w: w.x0) for z in out]


def _anschrift_woerter(zs: list[Zeile], rahmen) -> tuple[list[list[Wort]], list[str]]:
    """Wörter der Käuferanschrift im Rahmen -> (Zeilen, Hinweise für das Log).

    - ein Wort zählt, wenn es den Rahmen waagrecht überlappt und seine Mitte senkrecht im Rahmen liegt
      (am rechten Rand angeschnittene Wörter gehören dazu);
    - jede Zeile wird nach rechts um direkt anschließende Wörter ergänzt (Lücke ≤ LUECKE), damit ein Ort
      wie „Frankfurt am Main“ nicht am Rahmen endet;
    - steht unten nur die PLZ, kommt der Ort aus derselben Zeile – auch mit großem Abstand;
    - ist die unterste Zeile keine „PLZ Ort“ (Anschrift im nächsten Druck eine Zeile länger), wird bis
      ``ANSCHRIFT_TIEFER`` pt unter dem Rahmen nach ihr gesucht."""
    x0, top, x1, bottom = rahmen
    alle = [w for z in zs for w in z.woerter]
    hinweise: list[str] = []

    def drin(w: Wort, unten: float) -> bool:
        return w.x1 > x0 and w.x0 < x1 and top <= _mitte(w) <= unten

    def zeilen_bis(unten: float) -> list[list[Wort]]:
        zeilen = _zeilen_von([w for w in alle if drin(w, unten)])
        for z in zeilen:
            m, h = sum(map(_mitte, z)) / len(z), min(map(_hoehe, z))
            rechts = sorted(
                (w for w in alle if w.x0 >= z[-1].x1 and auf_linie(_mitte(w), m, h) and w not in z),
                key=lambda w: w.x0,
            )
            for w in rechts:
                if w.x0 - z[-1].x1 > LUECKE:
                    break
                z.append(w)
            rest = [w for w in rechts if w not in z]
            if (
                _NUR_PLZ.match(_text(z))
                and rest
                and ort_neben_plz(z[-1].x1, rest[0].x0)
                and re.match(r"[^\W\d_]", rest[0].t)
            ):
                ort = [rest[0]]
                for w in rest[1:]:
                    if w.x0 - ort[-1].x1 > LUECKE:
                        break
                    ort.append(w)
                z.extend(ort)
                hinweise.append("Ort mit großem Abstand neben der PLZ übernommen")
        return zeilen

    def plz_unten(zeilen) -> bool:
        return bool(zeilen) and "BT-53" in anschrift_zerlegen([_text(z) for z in zeilen])[0]

    zeilen = zeilen_bis(bottom)
    if zeilen and not plz_unten(zeilen):
        kand = sorted(
            {
                round(_mitte(w), 1)
                for w in alle
                if w.x1 > x0 and w.x0 < x1 and bottom < _mitte(w) <= bottom + ANSCHRIFT_TIEFER
            }
        )
        for m in kand:
            z2 = zeilen_bis(m + 0.5)
            if plz_unten(z2):
                hinweise.append(
                    f"Rahmen bis zur Zeile „PLZ Ort“ {m - bottom:.0f} pt tiefer verlängert"
                )
                zeilen = z2
                break
        else:
            hinweise.append("unterste Zeile im Rahmen ist keine „PLZ Ort“")
    return zeilen, hinweise


def _anon(s: str) -> str:
    """Text fürs Log ohne Inhalt: Buchstaben -> x/X, Ziffern -> 9 (Länge, Leerzeichen, Satzzeichen bleiben)."""
    return re.sub(r"[^\W\d_]", lambda m: "X" if m.group().isupper() else "x", re.sub(r"\d", "9", s))


def anschrift_diagnose(
    zeilen_ws: list[list[Wort]], rahmen, hinweise: list[str], wo: str = ""
) -> str:
    """Log-Zeile: welche Zeilen im Anschriftrahmen gelesen und wie sie zugeordnet wurden – anonymisiert
    (Buchstaben x, Ziffern 9), damit Nutzer sie weitergeben können, ohne die Rechnung zu schicken."""
    texte = [_text(z) for z in zeilen_ws]
    _, rollen = anschrift_zerlegen(texte)
    teile = [
        f"top {z[0].top:.0f} x {z[0].x0:.0f}–{z[-1].x1:.0f} h {min(map(_hoehe, z)):.0f} "
        f"„{_anon(t)}“ → {r}"
        for z, t, r in zip(zeilen_ws, texte, rollen)
    ]
    r = ", ".join(f"{v:.0f}" for v in rahmen)
    return (
        f"Anschrift{(' ' + wo) if wo else ''}: Rahmen ({r}), {len(texte)} Zeile(n): "
        + "; ".join(teile)
        + (f" [{'; '.join(hinweise)}]" if hinweise else "")
    )


def anschrift_im_rahmen(
    zs: list[Zeile], rahmen, wo: str = ""
) -> tuple[dict[str, str], list[list[Wort]]]:
    """Rahmen um die Käuferanschrift (eine Seite) -> (Teile, gelesene Zeilen); schreibt die Diagnose ins Log."""
    zeilen_ws, hinweise = _anschrift_woerter(zs, rahmen)
    if zeilen_ws:
        log.info("%s", anschrift_diagnose(zeilen_ws, rahmen, hinweise, wo))
    return anschrift_teilen([_text(z) for z in zeilen_ws]), zeilen_ws


def anschrift_auslesen(
    regel: dict, zeilen: list[Zeile], brueche: dict[str, str] | None = None
) -> dict[str, tuple[str, list[Wort]]]:
    """Regel „Anschrift als Block“ lesen -> Feld -> (Text, Wörter der Zeile). Ohne Zeile „PLZ Ort“ unten: nichts
    (lieber kein Vorschlag als die Straße als Ort). ``brueche`` (optional) bekommt die Prüfhinweise
    (``anschrift_brueche``) des gelesenen Blocks."""
    zs = _seite_zeilen(zeilen, regel.get("seite", 0))
    rahmen = _bereich_rahmen(regel, zs)
    if rahmen is None:
        return {}
    teile, zeilen_ws = anschrift_im_rahmen(zs, rahmen, "Vorlage")
    if "BT-53" not in teile:
        return {}
    if brueche is not None:
        brueche.update(anschrift_brueche(zeilen_ws))
    out = {}
    for f, t in teile.items():
        ws = next((z for z in zeilen_ws if t in _text(z) or _text(z) in t), [])
        out[f] = (t, ws)
    return out


# ---------------------------------------------------------------- Bereiche („Bereiche festlegen“, ab 0.4.5)
# Vom Nutzer gezogene Rahmen, in denen bestimmte Angaben stehen. Die Vorlage speichert sie unter ``bereiche``:
#   bereiche: {kopf: {rahmen: [x0, top, x1, bottom], seiten: alle|erste|letzte}, ...}
# Felder eines Bereichs werden danach NUR in diesem Rahmen gelesen. Ältere Vorlagen ohne ``bereiche`` lesen
# wie bisher die ganze Seite.
BEREICHE: dict[str, tuple[str, ...]] = {
    "anschrift": BLOCKFELDER,
    "kopf": ("BT-1", "BT-2", "kundennummer", "BT-13"),
    "tabelle": (),  # Positionstabelle: Rahmen über alle Seiten wie bisher
    "summen": ("BT-109", "BT-110", "BT-112"),
    "zahlung": ("BT-20",),
    # ab 0.9.7: Steuerhinweis, Kennungen des Kunden, Leitweg-ID, Währung/Kurs
    "steuer": (
        "steuerhinweis",
        "BT-48",
        "BT-47",
        "BT-55",
        "BT-80",
        "BT-10",
        "BT-5",
        "kurs",
        "BT-111",
    ),
}
BEREICH_NAMEN = {
    "anschrift": "Anschrift Empfänger",
    "kopf": "Rechnungskopf (Nr., Datum, Kd.-Nr., Best.-Nr.)",
    "tabelle": "Positionstabelle",
    "summen": "Summen",
    "zahlung": "Zahlungsbedingungen",
    "steuer": "Steuerhinweis & Kennungen",
}
BEREICH_SEITEN = ("alle", "erste", "letzte")
_HINTEN_ZUERST = ("summen", "zahlung", "steuer")  # „alle Seiten“: von der letzten Seite her suchen


def bereich_von(feld: str) -> str | None:
    """Bereich, zu dem ein Feld gehört (Anschrift-Block -> „anschrift“), sonst None."""
    if feld == ANSCHRIFT_BLOCK:
        return "anschrift"
    return next((b for b, fs in BEREICHE.items() if feld in fs), None)


def bereiche_laden(v: dict | None) -> dict[str, dict]:
    """Gültige Bereiche einer Vorlage (Unbekanntes und Kaputtes wird still übergangen)."""
    out = {}
    for name, b in ((v or {}).get("bereiche") or {}).items():
        if name not in BEREICHE or not isinstance(b, dict):
            continue
        try:
            x0, top, x1, bottom = (float(x) for x in b.get("rahmen") or ())
        except (TypeError, ValueError):
            continue
        if x1 - x0 < 1 or bottom - top < 1:
            continue
        seiten = b.get("seiten") if b.get("seiten") in BEREICH_SEITEN else "alle"
        out[name] = {
            "rahmen": [round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)],
            "seiten": seiten,
        }
        if isinstance(b.get("bezug"), (int, float)) and not isinstance(b.get("bezug"), bool):
            out[name]["bezug"] = round(float(b["bezug"]), 1)
    return out


def tabellenende(pv: dict | None, zeilen: list[Zeile]) -> tuple[int, float] | None:
    """(Seite, top) der Zeile, an der die Positionstabelle endet (z. B. „Warenwert netto“), sonst None."""
    if not pv or not pv.get("kopf") or not pv.get("ende"):
        return None
    prot: list = []
    positionen_auslesen(pv, zeilen, prot)
    return next(((z.seite, z.top) for z, grund in prot if grund.startswith("Tabellenende")), None)


def bereich_verschiebung(v: dict | None, b: dict, zeilen: list[Zeile], seite: int) -> float:
    """Bereiche unter der Tabelle (Summen, Zahlungsbedingungen) wandern mit ihr: ``bezug`` ist die Lage des
    Tabellenendes, als der Rahmen gezogen wurde. -> Abstand, um den das Tabellenende auf ``seite`` jetzt tiefer
    (oder höher) steht; 0, wenn die Tabelle nicht auf dieser Seite endet."""
    if "bezug" not in b:
        return 0.0
    ende = tabellenende((v or {}).get("positionen"), zeilen)
    if not ende or ende[0] != seite:
        return 0.0
    return ende[1] - b["bezug"]


def _regel_verschieben(regel: dict, d: float) -> dict:
    """Lage einer Regel (``top``, ``rahmen``) senkrecht um ``d`` verschieben (in place)."""
    if d:
        if regel.get("rahmen"):
            r = regel["rahmen"]
            regel["rahmen"] = [r[0], round(r[1] + d, 1), r[2], round(r[3] + d, 1)]
        for k in ("top", "anker_top"):
            if isinstance(regel.get(k), (int, float)):
                regel[k] = round(regel[k] + d, 1)
    return regel


def _zonen_rahmen(b: dict, d: float) -> list[float]:
    """Rahmen auf dieser Seite: der gezogene Rahmen, um die Verschiebung ``d`` erweitert – nie kleiner."""
    x0, top, x1, bottom = b["rahmen"]
    return [x0, min(top, top + d), x1, max(bottom, bottom + d)]


def anker_verschiebung(regel: dict, zeilen: list[Zeile], seite: int, weit: float = 150.0) -> float:
    """Kopffelder hängen an ihrer Beschriftung: Steht der Anker der Regel (z. B. „Rechnungs-Nr.“) auf dieser
    Seite höher oder tiefer als beim Anlernen, -> um wie viel (nächste Fundstelle, höchstens ``weit`` pt); sonst 0."""
    anker = [a for a in map(adapter_pdf.ohne_steuerzeichen, regel.get("anker") or []) if a]
    ref = regel.get("anker_top", regel.get("top"))
    if not anker or not isinstance(ref, (int, float)):
        return 0.0
    best = None
    for z in zeilen:
        if z.seite != seite:
            continue
        for seg in z.abschnitte:
            for k in range(len(seg) - len(anker) + 1):
                if _anker_passt(seg[k : k + len(anker)], anker):
                    d = z.top - ref
                    if abs(d) <= weit and (best is None or abs(d) < abs(best)):
                        best = d
    return round(best, 1) if best else 0.0


def bereich_rahmen_auf(v: dict | None, b: dict, zeilen: list[Zeile], seite: int) -> list[float]:
    """Rahmen des Bereichs auf ``seite`` dieser PDF – mit der Tabelle mitgewandert, nie kleiner als gezogen."""
    return _zonen_rahmen(b, bereich_verschiebung(v, b, zeilen, seite))


_UNTER_DER_TABELLE = ("summen", "zahlung")  # nur diese wandern mit dem Tabellenende


def bereich_bezug_setzen(v: dict, zeilen: list[Zeile]) -> None:
    """Beim Anlernen: Bereiche unter dem Tabellenende merken sich dessen Lage (``bezug``), damit sie auf
    Rechnungen mit mehr oder weniger Positionen mitwandern. Schon gesetzte Bezüge bleiben."""
    ende = tabellenende(v.get("positionen"), zeilen)
    for name, b in (v.get("bereiche") or {}).items():
        if name not in _UNTER_DER_TABELLE or "bezug" in b or not ende:
            continue
        if b["rahmen"][1] >= ende[1] - 20:
            b["bezug"] = round(ende[1], 1)


def bereich_seitenfolge(name: str, b: dict, zeilen: list[Zeile]) -> list[int]:
    """Seiten, auf denen der Bereich gesucht wird – in dieser Reihenfolge (erster Treffer gilt)."""
    seiten = sorted({z.seite for z in zeilen})
    if not seiten:
        return []
    art = b.get("seiten", "alle")
    if art == "erste":
        return seiten[:1]
    if art == "letzte":
        return seiten[-1:]
    return list(reversed(seiten)) if name in _HINTEN_ZUERST else seiten


def zeilen_im_rahmen(zeilen: list[Zeile], seite: int, rahmen) -> list[Zeile]:
    """Nur die Wörter dieser Seite, deren Mitte (senkrecht) im Rahmen liegt und die ihn waagrecht berühren –
    als eigene Zeilen mit neu bestimmten Abschnitten. Der Rest der Seite ist für das Lesen unsichtbar."""
    x0, top, x1, bottom = rahmen
    out = []
    for z in zeilen:
        if z.seite != seite:
            continue
        ws = [
            w
            for w in z.woerter
            if top <= (w.top + max(w.bottom, w.top + 1)) / 2 <= bottom and w.x1 > x0 and w.x0 < x1
        ]
        if not ws:
            continue
        out.append(Zeile(z.seite, z.top, ws, abschnitte_bilden(ws)))
    return out


def _gelesen_ok(feld: str, typ: str, text: str) -> bool:
    if feld in OPTIONALE_NUMMERN and not nummer_passt(text):
        return False
    return lesen_als(typ, text) is not None and wert_passt(feld, text)


def vorlage_feld_lesen(
    v: dict | None, feld: str, regel: dict, zeilen: list[Zeile]
) -> tuple[str, list[Wort]] | None:
    """Feld mit seiner Regel lesen – liegt es in einem Bereich der Vorlage, nur dort (Seiten nach „Gilt auf“).
    BT-20 wird zusätzlich mit dem Zahlungsbaustein im Druck abgeglichen (``_bt20_abgleichen``)."""
    erg = _vorlage_feld_lesen(v, feld, regel, zeilen)
    if feld != "BT-20":
        return erg
    kand = [erg]
    if bereiche_laden(v).get("zahlung") is not None and not regel.get("ohne_bereich"):
        kand.append(feld_auslesen(regel, zeilen))  # Rahmen, ohne mit dem Tabellenende zu wandern
    return _bt20_abgleichen(kand, zeilen)


def _vorlage_feld_lesen(
    v: dict | None, feld: str, regel: dict, zeilen: list[Zeile]
) -> tuple[str, list[Wort]] | None:
    name = bereich_von(feld)
    b = bereiche_laden(v).get(name) if name else None
    if b is None or regel.get("ohne_bereich"):
        return feld_auslesen(regel, zeilen)
    erstes = None
    for s in bereich_seitenfolge(name, b, zeilen):
        d = bereich_verschiebung(v, b, zeilen, s)
        einzeln = {**regel, "seite": 0}
        _regel_verschieben(einzeln, d)  # Inhalt steht tiefer/höher: Regel wandert mit
        rahmen = _zonen_rahmen(b, d)
        da = anker_verschiebung(einzeln, zeilen, s)
        if da:  # Beschriftung verrutscht (Kopfzeile tiefer): Rahmen wandert mit
            rahmen = [
                rahmen[0],
                min(rahmen[1], rahmen[1] + da),
                rahmen[2],
                max(rahmen[3], rahmen[3] + da),
            ]
        erg = feld_auslesen(einzeln, zeilen_im_rahmen(zeilen, s, rahmen))
        if erg and _gelesen_ok(feld, regel.get("typ", feldtyp(feld)), erg[0]):
            return erg
        erstes = erstes or erg
    return erstes


# ---------------------------------------------------------------- Zahlungsbaustein (BT-20)
# Zahlungsbedingungen stehen oft über mehrere Zeilen unter einer Überschrift („Zahlungsbedingungen“), mit Skonto
# eine Zeile mehr. Die Suche hier ist dieselbe wie im Anlern-Assistenten (Vorschlag für BT-20).
_ZAHLUNG_START = re.compile(
    r"zahlbar|fällig|zahlungsziel|zahlungsbeding|skonto|payable|due"
    # ohne „zahlbar“: „Zahlung innerhalb/bis …“, „Zahlung: 14 Tage netto“, „Bitte überweisen/begleichen … bis“,
    # „14 Tage ohne Abzug“
    r"|^zahlung\s*(?::|innerhalb\b|binnen\b|bis\b)"
    r"|\b(?:überweisen|begleichen)\b.*\bbis\b"
    r"|\b\d{1,3}\s+tage\b.*\b(?:netto|ohne\s+abzug)",
    re.I,
)
# reine Feldbeschriftung (+ optional Datum): kein Zahlungstext/Skonto (F8: „Fälligkeitsdatum 11.11.2026“)
_ZAHLUNG_FELD = re.compile(
    r"^(?:fälligkeits?(?:\s*-?\s*datum)?|due\s*date)\s*:?\s*(?:\d{1,2}\.\d{1,2}\.\d{2,4})?\s*$",
    re.I,
)
_ZAHLUNG_FOLGE = re.compile(
    r"^(bis|ab|nach|innerhalb|danach|sonst)\b|skonto|abzug|netto|tage|zahlbar|\d{1,2}\.\d{1,2}\.\d{2}",
    re.I,
)
_ZAHLUNG_UEBERSCHRIFT = re.compile(
    r"^(zahlungsbedingung(en)?|zahlungskonditionen|zahlungsziel|payment terms)\s*:?$", re.I
)


def _bedingung_folgezeilen(zeilen: list[Zeile], zi: int, seg: list[Wort]) -> list[Wort]:
    """Fortsetzung einer Zahlungsbedingung in den nächsten Zeilen („bis 28.11.2026 ohne Abzug“): Abschnitte,
    die ungefähr bündig darunter stehen und nach Zahlungsbedingung klingen."""
    out: list[Wort] = []
    z0 = zeilen[zi]
    hoehe = max(w.bottom - w.top for w in seg)
    hoehe = hoehe if hoehe > 0 else 10
    unten = max(w.top for w in seg) + hoehe
    for z in zeilen[zi + 1 : zi + 4]:
        if z.seite != z0.seite or z.top - unten > 1.2 * hoehe:
            break
        treffer = [
            g
            for g in z.abschnitte
            if abs(g[0].x0 - seg[0].x0) < 60
            or g[0].x0 >= seg[0].x0 - 2
            and g[0].x0 <= max(w.x1 for w in seg)
        ]
        # klingt nach Zahlungsbedingung – oder der Satz darüber (eine Textzeile, keine Überschrift) ist noch
        # nicht zu Ende und geht bündig weiter („… an die unten angegebene“ / „Bankverbindung.“)
        offen = len(_text(seg)) >= 40 and not re.search(r"[.!?:]$", (out or seg)[-1].t)
        treffer = [
            g
            for g in treffer
            if _ZAHLUNG_FOLGE.search(_text(g)) or offen and abs(g[0].x0 - seg[0].x0) < 3
        ]
        if not treffer:
            break
        out += treffer[0]
        unten = max(w.top for w in treffer[0]) + hoehe
    return out


def _skonto_darunter(zeilen: list[Zeile], zi: int, seg: list[Wort], ws: list[Wort]) -> list[Wort]:
    """Skonto als eigener Satz wenige Zeilen unter dem Zahlungsziel („Zahlungsziel: 30 Tage“ … „Bei Zahlung
    innerhalb von 8 Tagen gewähren wir 3 % Skonto.“), ungefähr bündig: gehört zur Zahlungsbedingung."""
    if re.search(r"skonto", _text(ws), re.I):
        return []
    hoehe = max(w.bottom - w.top for w in seg) or 10
    unten = max(w.top for w in ws)
    for z in zeilen[zi + 1 : zi + 6]:
        if z.seite != zeilen[zi].seite or z.top - unten > 3.5 * hoehe:
            break
        for g in z.abschnitte:
            if abs(g[0].x0 - seg[0].x0) < 60 and re.search(r"skonto", _text(g), re.I):
                return list(g)
    return []


def zahlungsbaustein(zeilen: list[Zeile]) -> tuple[int, list[Wort]] | None:
    """Zahlungsbedingung im Druck suchen: erster Abschnitt, der danach klingt („Zahlbar innerhalb …“, „Skonto“),
    samt bündiger Folgezeilen. Eine reine Überschrift („Zahlungsbedingungen“) gehört nicht zum Wert – dann zählen
    nur die Zeilen darunter. -> (Seite, Wörter) oder None."""
    for zi, z in enumerate(zeilen):
        for si, seg in enumerate(z.abschnitte):
            t = _text(seg)
            if (
                not _ZAHLUNG_START.search(t)
                or re.search(r"fälligkeit:?$", t, re.I)
                or _ZAHLUNG_FELD.match(t.strip())
                or len(t) <= 12
            ):
                continue
            folge = _bedingung_folgezeilen(zeilen, zi, seg)
            if _ZAHLUNG_UEBERSCHRIFT.match(t.strip()):
                if not folge and si + 1 < len(z.abschnitte):
                    nxt = z.abschnitte[si + 1]
                    if _ZAHLUNG_FOLGE.search(_text(nxt)):
                        folge = list(nxt)
                if not folge:
                    continue  # nur die Überschrift: weitersuchen
                return z.seite, folge + _skonto_darunter(zeilen, zi, seg, folge)
            ws = list(seg) + folge
            return z.seite, ws + _skonto_darunter(zeilen, zi, seg, ws)
    return None


def zahlungsbaustein_text(ws: list[Wort]) -> str:
    return " ".join(_text(z) for z in _zeilen_von(ws))


_ZAHLUNG_TEXT = re.compile(
    r"zahlbar|fällig|zahlungsziel|zahlungsbeding|skonto|netto|abzug|\btage\b|payable|due\b"
    r"|überweisen|begleichen",
    re.I,
)


def _bt20_abgleichen(kand: list, zeilen: list[Zeile]) -> tuple[str, list[Wort]] | None:
    """Gelesene Zahlungsbedingung (Kandidaten der Regel, erster zuerst) mit dem Zahlungsbaustein im Druck
    abgleichen: Trifft die Regel den Baustein, kommt der ganze Baustein dazu (eine Skonto-Zeile mehr als beim
    Anlernen wird nicht abgeschnitten; nie weniger als gelesen). Liest die Regel etwas anderes, das nicht nach
    Zahlungsbedingung klingt (z. B. die Fußzeile, weil der Rahmen mit dem Tabellenende gewandert ist), gilt sie
    als nicht gelesen – lieber prüfen als falsch. Ohne Baustein im Druck bleibt es beim Gelesenen."""
    kand = [e for e in kand if e and e[0].strip()]
    baustein = zahlungsbaustein(zeilen)
    if baustein is None:
        return kand[0] if kand else None
    hws = baustein[1]
    hid = {id(w) for w in hws}
    for text, ws in kand:
        ids = {id(w) for w in ws}
        if ids & hid:
            dazu = [w for w in hws if id(w) not in ids]
            if not dazu:
                return text, ws
            alle = list(ws) + dazu
            return zahlungsbaustein_text(alle), alle
    for e in kand:
        if _ZAHLUNG_TEXT.search(e[0]):
            return e  # eigene Wahl des Nutzers, klingt nach Zahlungsbedingung
    return None


def vorlage_anschrift_lesen(
    v: dict | None, regel: dict, zeilen: list[Zeile], brueche: dict[str, str] | None = None
) -> dict[str, tuple[str, list[Wort]]]:
    """Anschrift-Block lesen – mit Bereich „anschrift“ im Rahmen des Nutzers: nie kleiner als der Rahmen, nur
    nach unten bis „PLZ Ort“ verlängert (``anschrift_im_rahmen``); Seiten nach „Gilt auf“. ``brueche``
    (optional) bekommt die Prüfhinweise des gelesenen Blocks."""
    b = bereiche_laden(v).get("anschrift")
    if b is None:
        return anschrift_auslesen(regel, zeilen, brueche)
    r = regel.get("rahmen") or b["rahmen"]
    rahmen = (
        [
            min(b["rahmen"][0], r[0]),
            b["rahmen"][1],
            max(b["rahmen"][2], r[2]),
            max(b["rahmen"][3], r[3]),
        ]
        if not regel.get("anker")
        else list(b["rahmen"])
    )
    einzeln = {k: x for k, x in regel.items() if k not in ("anker", "anker_top", "anker_x0")}
    einzeln.update(seite=0, rahmen=rahmen)
    for s in bereich_seitenfolge("anschrift", b, zeilen):
        erg = anschrift_auslesen(einzeln, [z for z in zeilen if z.seite == s], brueche)
        if erg:
            return erg
    return {}


def bereiche_unterschied(alt: dict | None, neu: dict | None) -> list[str]:
    """Bereiche, die sich zwischen zwei Vorlagen-Ständen unterscheiden (neu, weg, anderer Rahmen/„Gilt auf“)."""
    a, n = bereiche_laden({"bereiche": alt}), bereiche_laden({"bereiche": neu})

    def kern(x):
        return None if x is None else (x["rahmen"], x["seiten"])

    return [b for b in BEREICHE if kern(a.get(b)) != kern(n.get(b))]


# Anker für einen gelernten Bereich (Beschriftung links daneben oder darüber), pt
BEREICH_ANKER_HOEHER = 6.0  # Beschriftung links darf so viel höher beginnen als der Bereich
BEREICH_ANKER_UEBER = 60.0  # Beschriftung darüber höchstens so weit über dem Bereich
BEREICH_ANKER_OBEN_GEWICHT = (
    1.5  # Abstand nach oben zählt 1,5-fach (links daneben ist der bessere Anker)
)


def bereich_regel(
    feld: str,
    zeilen: list[Zeile],
    seite: int,
    rahmen: tuple[float, float, float, float],
    variabel: set[str],
    block: bool = False,
) -> dict | None:
    """Regel aus einem vom Nutzer gezogenen Rahmen. Bevorzugt relativ zur nächsten Beschriftung links daneben
    oder darüber (höchstens 60 pt entfernt); sonst fest auf der Seite. Prüft, dass die Regel den Rahmen
    auf dieser Rechnung wieder liest."""
    zs = [z for z in zeilen if z.seite == seite]
    if not zs:
        return None
    x0, top, x1, bottom = (round(v, 1) for v in rahmen)
    innen = {id(w) for z in woerter_im_bereich(zs, x0, top, x1, bottom) for w in z}
    if not innen:
        return None
    basis = {
        "typ": feldtyp(feld),
        "lage": "bereich",
        "seite": _seite_rel(seite, zeilen),
        "rahmen": [x0, top, x1, bottom],
        **({"block": True} if block else {}),
    }
    soll = _bereich_auslesen(basis, zs)
    kand = []
    for z in zs:
        for seg in z.abschnitte:
            if any(id(w) in innen for w in seg):
                continue
            links = seg[-1].x1 <= x0 + RAHMEN_RAND and top - BEREICH_ANKER_HOEHER <= z.top <= bottom
            oben = (
                z.top < top
                and top - z.top <= BEREICH_ANKER_UEBER
                and seg[0].x0 <= x1
                and seg[-1].x1 >= x0 - SPALTE_RAND
            )
            if not (links or oben):
                continue
            teil = seg[-3:] if links else seg[:3]
            anker = [_tok(w.t) for w in teil]
            if _anker_ok(anker, variabel):
                d = (x0 - teil[-1].x1) if links else (top - z.top) * BEREICH_ANKER_OBEN_GEWICHT
                kand.append((d, anker, teil[0]))
    for _, anker, w in sorted(kand, key=lambda k: k[0]):
        regel = {**basis, "anker": anker, "anker_top": round(w.top, 1), "anker_x0": round(w.x0, 1)}
        if _bereich_auslesen(regel, zs) == soll:
            return regel
    return basis


# Gelernte Vorlagen speichern Lagen in pt; beim Wiederlesen derselben Rechnungsart (gleiches Layout) gelten
# diese festen Toleranzen
REGEL_TOL = (
    4.0  # pt: Zeile/Abschnitt einer Regel „fest“ bzw. Zielzeile von „unten“ darf so weit abweichen
)
REGEL_TOL_UNTEN_X = 6.0  # pt: waagrechte Abweichung des Werts bei „unten“ (Anker darüber)


def feld_auslesen(regel: dict, zeilen: list[Zeile]) -> tuple[str, list[Wort]] | None:
    zs = _seite_zeilen(zeilen, regel.get("seite", 0))
    lage = regel.get("lage")
    if lage == "bereich":
        return _bereich_auslesen(regel, zs)
    if lage == "fest":
        kand = []
        for z in zs:
            if abs(z.top - regel["top"]) > REGEL_TOL:
                continue
            for seg in z.abschnitte:
                if abs(seg[0].x0 - regel["x0"]) <= REGEL_TOL and len(seg) > regel.get("i", 0):
                    kand.append((abs(z.top - regel["top"]), seg[regel.get("i", 0) :]))
        if not kand:
            return None
        ws = _nehmen(min(kand, key=lambda k: k[0])[1], regel)
        return (_text(ws), ws) if ws else None
    # ältere Vorlagen können „(cid:10)“-Platzhalter im Anker enthalten (siehe adapter_pdf.ohne_steuerzeichen)
    anker = [a for a in map(adapter_pdf.ohne_steuerzeichen, regel.get("anker") or []) if a]
    if not anker:
        return None
    treffer = []
    for zi, z in enumerate(zs):
        for si, seg in enumerate(z.abschnitte):
            for k in range(len(seg) - len(anker) + 1):
                if _anker_passt(seg[k : k + len(anker)], anker):
                    treffer.append((abs(z.top - regel.get("top", z.top)), zi, si, k))
    for _, zi, si, k in sorted(treffer, key=lambda t: t[0]):
        z = zs[zi]
        seg = z.abschnitte[si]
        ws: list[Wort] = []
        if lage == "rechts":
            ws = seg[k + len(anker) :]
        elif lage == "naechster" and k + len(anker) == len(seg) and si + 1 < len(z.abschnitte):
            ws = z.abschnitte[si + 1]
        elif lage == "unten":
            ziel_top, ziel_x = z.top + regel["dy"], seg[k].x0 + regel["dx"]
            for z2 in sorted(zs, key=lambda z2: abs(z2.top - ziel_top)):
                if abs(z2.top - ziel_top) > REGEL_TOL:
                    break
                for seg2 in z2.abschnitte:
                    for m, w in enumerate(seg2):
                        if abs(w.x0 - ziel_x) <= REGEL_TOL_UNTEN_X:
                            ws = seg2[m:]
                            break
                    if ws:
                        break
                if ws:
                    break
        ws = _nehmen(ws, regel)
        if ws:
            return _text(ws), ws
    return None


# Beschriftung über bzw. Wert unter einer Fundstelle. Senkrecht in Schrifthöhen (``_hoehe``, auf den
# Testbelegen 8–9,5 pt; bei 9 pt die früheren festen Werte), waagrecht in pt (Spalten/Tabstopps)
UEBER_MAX = (
    5.0  # Schrifthöhen: so weit darüber (höchstens drei Zeilen) steht eine Spaltenbeschriftung
)
DARUNTER_ASSISTENT = 2.5  # Schrifthöhen: Wert unter einer angeklickten Beschriftung (früher 22 pt)
DARUNTER_NUMMER = 3.4  # Schrifthöhen: Nummer unter ihrer Beschriftung beim Lesen (früher 30 pt)
SPALTE_RAND = 10.0  # so weit seitlich versetzt zählt ein Abschnitt darüber noch als dieselbe Spalte
UNTER_RAND = (
    5.0  # so weit seitlich versetzt zählt ein Abschnitt darunter noch als „unter der Beschriftung“
)


def abschnitt_darueber(
    zeilen: list[Zeile], zi: int, x0: float, x1: float, hoehe: float
) -> tuple[Zeile, list[Wort]] | None:
    """Nächster Abschnitt über Zeile ``zi``, der waagrecht ``x0``–``x1`` (± SPALTE_RAND) überlappt – höchstens
    drei Zeilen und ``UEBER_MAX`` Schrifthöhen (``hoehe``) darüber, gleiche Seite."""
    z = zeilen[zi]
    for z2 in reversed(zeilen[max(0, zi - 3) : zi]):
        if z2.seite != z.seite or z.top - z2.top > UEBER_MAX * hoehe:
            return None
        ueber = [
            s for s in z2.abschnitte if s[0].x0 - SPALTE_RAND <= x1 and s[-1].x1 + SPALTE_RAND >= x0
        ]
        if ueber:
            return z2, ueber[0]
    return None


def abschnitte_darunter(
    zeilen: list[Zeile], zi: int, x0: float, x1: float, max_dy: float
) -> list[tuple[int, list[Wort]]]:
    """Abschnitte der nächsten zwei Zeilen unter Zeile ``zi`` (weniger als ``max_dy`` pt tiefer, gleiche Seite),
    die waagrecht ``x0``–``x1`` (± UNTER_RAND) überlappen: [(Zeilenindex, Abschnitt)]."""
    z = zeilen[zi]
    return [
        (zi + 1 + k, s2)
        for k, z2 in enumerate(zeilen[zi + 1 : zi + 3])
        if z2.seite == z.seite and 0 < z2.top - z.top < max_dy
        for s2 in z2.abschnitte
        if s2[0].x0 <= x1 + UNTER_RAND and s2[-1].x1 >= x0 - UNTER_RAND
    ]


def _beschriftung(zeilen: list[Zeile], zi: int, si: int, i: int) -> str:
    """Text vor bzw. über einer Fundstelle (für die Zuordnung zum richtigen Feld)."""
    z = zeilen[zi]
    seg = z.abschnitte[si]
    teile = [_text(seg[max(0, i - 4) : i])]
    if si > 0:
        teile.append(_text(z.abschnitte[si - 1][-4:]))
    ueber = abschnitt_darueber(
        zeilen, zi, seg[i].x0, seg[min(i + 1, len(seg) - 1)].x1, _hoehe(seg[i])
    )
    if ueber:
        teile.append(_text(ueber[1]))
    return norm(" ".join(teile))


def _punkte(feld: str, zeilen: list[Zeile], zi: int, si: int, i: int) -> tuple[int, bool]:
    pos, neg, muss = SCHLUESSELWOERTER.get(feld, ("", "", False))
    lab = _beschriftung(zeilen, zi, si, i)
    p = 0
    if pos and re.search(pos, lab):
        p += 10
    if neg and re.search(neg, lab):
        p -= 8
    return p, (p > 0 or not muss)


def _regeln(zeilen: list[Zeile], zi: int, si: int, i: int, j: int, variabel: set[str]):
    """Mögliche Regeln für eine Fundstelle, die stabilste zuerst."""
    z = zeilen[zi]
    seg = z.abschnitte[si]
    basis = {"seite": _seite_rel(z.seite, zeilen), "top": round(z.top, 1)}
    if j == len(seg):
        basis["ende"] = True
    else:
        basis["n"] = j - i
    if i > 0:
        anker = [_tok(w.t) for w in seg[max(0, i - 3) : i]]
        if _anker_ok(anker, variabel):
            yield {"lage": "rechts", "anker": anker, **basis}
    if i == 0 and si > 0:
        anker = [_tok(w.t) for w in z.abschnitte[si - 1][-3:]]
        if _anker_ok(anker, variabel):
            yield {"lage": "naechster", "anker": anker, **basis}
    if i == 0:
        ueber = abschnitt_darueber(zeilen, zi, seg[0].x0, seg[-1].x1, _hoehe(seg[0]))
        if ueber:
            z2, s2 = ueber
            anker = [_tok(w.t) for w in s2]
            if _anker_ok(anker, variabel):
                yield {
                    "lage": "unten",
                    "anker": anker,
                    "dy": round(z.top - z2.top, 1),
                    "dx": round(seg[0].x0 - s2[0].x0, 1),
                    **basis,
                }
    yield {"lage": "fest", "x0": round(seg[0].x0, 1), "i": i, **basis}


def feld_lernen(
    feld: str,
    soll,
    zeilen: list[Zeile],
    variabel: set[str],
    tol: Decimal,
    bezug: float | None = None,
    stelle: list[Wort] | None = None,
) -> dict | None:
    """bezug: Höhe (top) eines verwandten, schon gelernten Feldes – bei Gleichstand gewinnt die nächste
    Fundstelle (z. B. Ort des Käufers in dessen Anschriftblock statt in der Absenderzeile).
    stelle: vom Nutzer bestätigte Fundstelle (Anlern-Assistent) – geht vor und braucht kein Schlüsselwort."""
    typ = feldtyp(feld)
    kand = []
    for zi, si, i, j in _spannen(zeilen, _maxlaenge(typ, soll)):
        if typ == "betrag" and _ist_seitenzahl(zeilen[zi]):
            continue
        ws = zeilen[zi].abschnitte[si][i:j]
        if not gleich(typ, soll, _text(ws), tol):
            continue
        p, erlaubt = _punkte(feld, zeilen, zi, si, i)
        if stelle and ws[0] is stelle[0]:
            p, erlaubt = p + 100, True
        if erlaubt:
            kand.append((p, zi, si, i, j))
    if not kand:
        return None
    letzte = feld in ("BT-109", "BT-110", "BT-112")  # Summen: bei Gleichstand die letzte Fundstelle

    def abstand(zi: int) -> float:  # Anschriftzeilen folgen unter dem Namen
        d = zeilen[zi].top - bezug
        return d if d >= 0 else 1000 - d

    kand.sort(
        key=lambda k: (-k[0], abstand(k[1]) if bezug is not None else 0, -k[1] if letzte else k[1])
    )
    for _, zi, si, i, j in kand:
        for regel in _regeln(zeilen, zi, si, i, j, variabel):
            regel = {"typ": typ, **regel}
            if typ == "betrag":
                regel["format"] = betraege(_text(zeilen[zi].abschnitte[si][i:j]))[0][1]
            if letzte and regel["seite"] == 0 and len({z.seite for z in zeilen}) == 1:
                regel["seite"] = -1  # Summen stehen auf der letzten Seite
            erg = feld_auslesen(regel, zeilen)
            if erg and gleich(typ, soll, erg[0], tol):
                return regel
    return None


def _variabel(r: Rechnung, felder: list[str]) -> set[str]:
    """Wörter, die Werte dieser Rechnung sind – taugen nicht als Anker."""
    v = set(_MONATE)
    for f in felder:
        w = soll_wert(r, f)
        if isinstance(w, str):
            v.update(norm(t) for t in w.split())
    for p in r.positionen:
        v.update(norm(t) for t in p.bezeichnung.split())
    return v


# ---------------------------------------------------------------- Positionen: Tabelle lernen und lesen
ZAHLSPALTEN = ("BT-129", "BT-146", "BT-149", "gesamt")
# Trennlinie aus Zeichen („-----“, „=====“, „_____“, „– – –“, „────“); Linien als Grafik haben keine Wörter
TRENNLINIE = re.compile(r"^[-=_.*~\u2013\u2014\u2500\u2501\u2550]+$")


def ist_trennlinie(z: Zeile) -> bool:
    return bool(z.woerter) and all(TRENNLINIE.match(w.t) for w in z.woerter)


def _zeilen_tokens(z: Zeile) -> list[str]:
    return [_tok(w.t) for w in z.woerter]


def positionen_lernen(r: Rechnung, zeilen: list[Zeile], tol: Decimal) -> dict | None:
    """Sucht jede CSV-Position als Tabellenzeile (Gesamt + Einzelpreis + erstes Wort der Bezeichnung)."""
    spalten: dict[str, list[tuple[float, float]]] = {}
    einheiten: dict[str, str] = {}
    steuer: dict[str, dict] = {}
    steuer_ohne_spalte: list[dict] = []
    pe_ohne_spalte: set[Decimal] = set()
    pe_spalte = False
    erste = letzte = None
    abstaende = []
    fmt = None
    cursor = 0
    for p in r.positionen:
        desc = p.bezeichnung.split()
        if not desc or p.netto is None or p.einzelpreis is None:
            return None
        gefunden = False
        for zi in range(cursor, len(zeilen)):
            ws = zeilen[zi].woerter
            g = [k for k, w in enumerate(ws) if gleich("betrag", p.netto, w.t, tol)]
            if not g or norm(desc[0]) not in [norm(w.t) for w in ws]:
                continue
            g = g[-1]
            pr = [
                k for k, w in enumerate(ws) if k != g and gleich("betrag", p.einzelpreis, w.t, tol)
            ]
            if not pr:
                continue
            pr = pr[-1]
            fmt = fmt or betraege(ws[g].t)[0][1]
            benutzt = {g: "gesamt", pr: "BT-146"}
            # Bezeichnung: erstes passendes Wort, dann so viele Wörter wie passen
            d0 = next(
                k for k, w in enumerate(ws) if norm(w.t) == norm(desc[0]) and k not in benutzt
            )
            k, di = d0, 0
            while (
                k < len(ws)
                and di < len(desc)
                and norm(ws[k].t) == norm(desc[di])
                and k not in benutzt
            ):
                benutzt[k] = "BT-153"
                k, di = k + 1, di + 1
            m = [
                k
                for k, w in enumerate(ws)
                if k not in benutzt
                and p.menge is not None
                and any(d == p.menge for d, _ in zahlen(w.t, fmt))
            ]
            if not m:
                continue
            m = min(
                m,
                key=lambda k: (
                    abs(ws[pr].x0 - ws[k].x1) if ws[k].x1 < ws[pr].x0 else 9999 + ws[k].x0
                ),
            )
            benutzt[m] = "BT-129"
            # Preiseinheit (BT-149) als eigene Spalte gedruckt? „1“ zählt nur zwischen Einzelpreis und Gesamt
            pe = [
                k
                for k, w in enumerate(ws)
                if k not in benutzt
                and any(d == p.preiseinheit for d, _ in zahlen(w.t.lstrip("/"), fmt))
                and (p.preiseinheit != 1 or ws[pr].x1 < w.x0 and w.x1 < ws[g].x0)
            ]
            if pe:
                benutzt[min(pe, key=lambda k: abs(ws[k].x0 - ws[pr].x1))] = "BT-149"
                pe_spalte = True
            else:
                pe_ohne_spalte.add(p.preiseinheit)
            if p.artikelnummer:
                a = [k for k, w in enumerate(ws) if k not in benutzt and w.t == p.artikelnummer]
                if a:
                    benutzt[a[0]] = "BT-155"
            nr = [
                k for k, w in enumerate(ws) if k not in benutzt and w.t == p.nr and w.x1 < ws[d0].x0
            ]
            if nr:
                benutzt[nr[0]] = "BT-126"
            if p.einheit:
                # Einheit: Wort mit Buchstaben, das direkt neben der Menge steht
                abst = lambda k: max(ws[k].x0 - ws[m].x1, ws[m].x0 - ws[k].x1)  # noqa: E731
                e = [
                    k
                    for k, w in enumerate(ws)
                    if k not in benutzt
                    and re.search(r"[^\W\d_]", w.t)
                    and w.t not in WAEHRUNGSZEICHEN
                    and abst(k) < 80
                ]
                if e:
                    e = min(e, key=abst)
                    benutzt[e] = "BT-130"
                    einheiten[ws[e].t] = p.einheit
            # Restwörter links der Bezeichnung (Pos.-/Artikelnummer ohne CSV-Gegenstück): eigene Spalte, die beim
            # Auslesen übergangen wird – kein Steuerkennzeichen und kein Teil der Bezeichnung
            for k in range(len(ws)):
                if k not in benutzt and ws[k].t not in WAEHRUNGSZEICHEN and ws[k].x1 < ws[d0].x0:
                    benutzt[k] = "ignorieren"
            rest = [
                k for k in range(len(ws)) if k not in benutzt and ws[k].t not in WAEHRUNGSZEICHEN
            ]
            st = {"BT-151": p.steuer.kategorie, "BT-152": _satz(p.steuer.satz).replace(",", ".")}
            if p.steuer.befreiungsgrund:
                st["BT-120"] = p.steuer.befreiungsgrund
            if p.steuer.befreiungscode:
                st["BT-121"] = p.steuer.befreiungscode
            if rest:
                for k in rest:
                    benutzt[k] = "steuer"
                text = _text([ws[k] for k in rest])
                if steuer.get(text, st) != st:
                    return None
                steuer[text] = st
            else:
                steuer_ohne_spalte.append(st)
            for k, sp in benutzt.items():
                spalten.setdefault(sp, []).append((ws[k].x0, ws[k].x1))
            # Folgezeilen der Bezeichnung
            ende = zi
            z2i = zi + 1
            while di < len(desc) and z2i < len(zeilen) and zeilen[z2i].seite == zeilen[zi].seite:
                ws2 = zeilen[z2i].woerter
                if [norm(w.t) for w in ws2] != [norm(t) for t in desc[di : di + len(ws2)]]:
                    break
                for w in ws2:
                    spalten["BT-153"].append(
                        (w.x0, w.x0)
                    )  # nur Anfang zählt (Bezeichnung ist links bündig)
                abstaende.append(zeilen[z2i].top - zeilen[z2i - 1].top)
                di += len(ws2)
                ende = z2i
                z2i += 1
            if erste is None:
                erste = zi
            elif letzte is not None and zeilen[zi].seite == zeilen[letzte].seite:
                abstaende.append(zeilen[zi].top - zeilen[letzte].top)
            letzte = ende
            cursor = ende + 1
            gefunden = True
            break
        if not gefunden:
            return None
    if erste is None or erste == 0 or zeilen[erste - 1].seite != zeilen[erste].seite:
        return None
    pv: dict = {
        "kopf": _zeilen_tokens(zeilen[erste - 1]),
        "format": fmt,
        "spalten": {
            sp: [round(min(a for a, _ in xs), 1), round(max(b for _, b in xs), 1)]
            for sp, xs in spalten.items()
        },
        "zeilenabstand": round(statistics.median(abstaende), 1) if abstaende else 14.0,
    }
    if (
        zeilen[letzte].seite != zeilen[erste].seite
    ):  # mehrseitig: Rahmen der ersten Seite gilt auf jeder Seite
        s0 = [
            z
            for z in zeilen[erste : letzte + 1]
            if z.seite == zeilen[erste].seite and _zeilen_tokens(z)
        ]
        xs = [x for v in pv["spalten"].values() for x in v]
        pv["rahmen"] = [
            round(min(xs) - 2, 1),
            round(zeilen[erste - 1].top, 1),
            round(max(xs) + 2, 1),
            round(max(z.top for z in s0), 1),
        ]
    if letzte + 1 < len(zeilen) and zeilen[letzte + 1].seite == zeilen[letzte].seite:
        toks = _zeilen_tokens(zeilen[letzte + 1])
        vorn = []
        for t in toks:
            if t == "#":
                break
            vorn.append(t)
        pv["ende"] = vorn[:3] if vorn else toks
    if einheiten:
        pv["einheiten"] = einheiten
    elif r.positionen and len({p.einheit for p in r.positionen}) == 1 and r.positionen[0].einheit:
        pv["einheit_fest"] = r.positionen[0].einheit
    if steuer and steuer_ohne_spalte:
        return None
    if pe_spalte:
        if pe_ohne_spalte - {Decimal("1")}:
            return None  # Spalte vorhanden, aber nicht in jeder Zeile lesbar
    elif len(pe_ohne_spalte) > 1:
        return None  # gemischte Preiseinheiten ohne Spalte im Druck: nicht lernbar
    elif pe_ohne_spalte and pe_ohne_spalte != {Decimal("1")}:
        pv["preiseinheit_fest"] = str(next(iter(pe_ohne_spalte)))
    if steuer:
        pv["steuer"] = steuer
    else:
        arten = {tuple(sorted(s.items())) for s in steuer_ohne_spalte}
        if len(arten) != 1:
            return None  # gemischte Sätze ohne Steuerspalte im Druck: nicht lernbar
        pv["steuer_fest"] = steuer_ohne_spalte[0]
    return pv


def _bereiche(pv: dict) -> list[tuple[str, float, float]]:
    sp = sorted(pv["spalten"].items(), key=lambda kv: kv[1][0])
    out = []
    for n, (name, (x0, x1)) in enumerate(sp):
        hi = x1 + 2
        if name == "BT-153" and n + 1 < len(sp):
            hi = max(hi, sp[n + 1][1][0] - 2)
        out.append((name, x0 - 2, hi))
    return out


def _zuordnen(z: Zeile, bereiche, fest: bool = False) -> dict[str, list[Wort]]:
    """Wörter einer Zeile auf die Spalten verteilen. Wörter ganz links vor der Tabelle (Falzmarken, Lochmarken)
    und rechts hinter einer Zahlenspalte am Ende bleiben draußen. ``fest`` (Spalten als eigene Rahmen
    gezogen): nur Wörter in einem Spaltenrahmen zählen."""
    out: dict[str, list[Wort]] = {}
    if not bereiche:
        return out
    rechtsbuendig = [b for b in bereiche if b[0] in ZAHLSPALTEN]
    links = min(b[1] for b in bereiche)
    letzte = max(bereiche, key=lambda b: b[2])
    mb = next((b for b in bereiche if b[0] == "BT-129"), None)
    for w in z.woerter:
        if w.t in WAEHRUNGSZEICHEN or (
            len(w.t) <= 3 and TRENNLINIE.match(w.t)
        ):  # Falz-/Lochmarke „--“
            continue
        # Zahlen stehen meist rechtsbündig: rechter Rand passt -> diese Spalte, auch wenn die Zahl breiter ist
        rb = [
            b
            for b in rechtsbuendig
            if abs(w.x1 - (b[2] - 2)) <= 3 and re.match(r"^-?[\d.,]+$", w.t)
        ]
        if rb:
            out.setdefault(rb[0][0], []).append(w)
            continue
        if w.x1 < links or (letzte[0] in ZAHLSPALTEN and w.x0 > letzte[2] + 6):
            continue
        c = (w.x0 + w.x1) / 2
        drin = [b for b in bereiche if b[1] <= c <= b[2]]
        if fest and not drin:
            continue
        best = drin[0] if drin else min(bereiche, key=lambda b: min(abs(c - b[1]), abs(c - b[2])))
        if (
            mb
            and best[0] in ("BT-130", "BT-153")
            and best[1] > mb[1]
            and mb[1] <= w.x0 <= mb[2]
            and re.fullmatch(_MENGE_ZAHL, w.t)
        ):
            # Menge breiter als alle angelernten („1,25“ am Dezimalkomma, „1.000,5“ linksbündig): Sie beginnt in
            # der Mengenspalte und ragt nur nach rechts in die Nachbarspalte – eine Zahl ist nie Einheit, und
            # die Bezeichnung beginnt nicht in der Mengenspalte
            best = mb
        out.setdefault(best[0], []).append(w)
    return out


def _passt_zeile(toks: list[str], z: Zeile, praefix: bool = False) -> bool:
    # ältere Vorlagen: „(cid:10)“; eckige Klammern vergleichen wir nicht (ältere Fassungen verloren „\\[“, s. adapter_pdf)
    def ohne(ts):
        return [t for t in (adapter_pdf.ohne_steuerzeichen(t).strip("[]") for t in ts) if t]

    toks, zt = ohne(toks), ohne(_zeilen_tokens(z))
    return zt[: len(toks)] == toks if praefix else zt == toks


@dataclass
class PosRoh:
    nr: str = ""
    artikelnummer: str = ""
    bezeichnung: str = ""
    menge: Decimal | None = None
    einheit_text: str = ""
    einzelpreis: Decimal | None = None
    steuer_text: str = ""
    gesamt: Decimal | None = None
    preiseinheit: Decimal | None = None


def _beiwerk(t: str) -> bool:
    """Zusatz neben einer Zahl in einer Zahlenspalte: Währung („EURO“, „[EURO]“), Steuerkennzeichen („A“, „1“), „*“."""
    return len(t) <= 2 or (len(t) <= 6 and not re.search(r"\d", t))


def _spaltenwert(ws: list[Wort], lesen, fmt: str | None) -> list[tuple[Decimal, str]]:
    """Zahl einer Spalte: ganzer Spaltentext, sonst genau ein Zahlwort neben Beiwerk (Kennzeichen, Währung)."""
    v = lesen(_text(ws), fmt)
    if v or len(ws) < 2:
        return v
    treffer = [w for w in ws if lesen(w.t.rstrip("*"), fmt)]
    if len(treffer) == 1 and all(_beiwerk(w.t) for w in ws if w is not treffer[0]):
        return lesen(treffer[0].t.rstrip("*"), fmt)
    return []


_PE_WORT = re.compile(r"^(?:/|je|pro|per)$", re.I)
_PE_ZAHL = re.compile(r"^\d{1,4}(?:\.\d{3})?$")


def _pe_wert(t: str, fmt: str | None) -> Decimal | None:
    v = (
        [d for d, _ in zahlen(t, fmt) if d > 0 and d == d.to_integral_value()]
        if _PE_ZAHL.match(t)
        else []
    )
    return v[0] if v else None


def preiseinheit_abtrennen(sp: dict[str, list[Wort]], fmt: str | None) -> Decimal | None:
    """Preiseinheit direkt am Einzelpreis („3,40 /1“, „3,40/100“, „3,40 / 100“, „je 100“, „pro 1000“) aus den
    Spalten Einzelpreis/Gesamt herauslösen -> BT-149 der Zeile (None = nicht gedruckt). Das Zeichen steht oft
    in der Lücke zwischen Preis und Betrag und landet sonst als Beiwerk im Betrag – die Preiseinheit ginge
    verloren und Vorschau und Speichern rechneten mit verschiedenen Werten."""
    pe = None
    for c in ("BT-146", "gesamt"):
        ws = sp.get(c)
        if not ws:
            continue
        neu: list[Wort] = []
        i = 0
        while i < len(ws):
            w = ws[i]
            # „3,40/100“, „3,40€/10“, „€/10“, „EUR/100“ (Währung bleibt als eigenes Wort stehen)
            m = re.fullmatch(r"(-?[\d.,]*\d)?(€|EUR|EURO)?/(\S+)", w.t, re.I)
            if (
                pe is None
                and m
                and (m.group(1) or m.group(2))
                and _pe_wert(m.group(3), fmt)
                and (not m.group(1) or (c == "BT-146" and zahlen(m.group(1), fmt)))
            ):
                pe = _pe_wert(m.group(3), fmt)
                for t in (m.group(1), m.group(2)):
                    if t:
                        neu.append(Wort(t, w.x0, w.x1, w.top, w.seite, w.bottom))
            elif pe is None and w.t.startswith("/") and _pe_wert(w.t[1:], fmt):
                pe = _pe_wert(w.t[1:], fmt)
            elif (
                pe is None
                and _PE_WORT.match(w.t)
                and i + 1 < len(ws)
                and _pe_wert(ws[i + 1].t, fmt)
                and not betraege(ws[i + 1].t, fmt)
            ):
                pe = _pe_wert(ws[i + 1].t, fmt)
                i += 1
            else:
                neu.append(w)
            i += 1
        sp[c] = neu
    return pe


def _einheit_text(sp: dict, pv: dict, z: Zeile | None = None) -> str:
    """Text der Einheitenspalte, sonst lesbare Einheit in oder direkt neben der Mengenzelle
    (nur ohne Einheitenspalte)."""
    t = _text(sp.get("BT-130", []))
    if t or "BT-130" in pv.get("spalten", {}):
        return t
    return (
        einheit_aus_menge(_text(sp.get("BT-129", [])))
        or (einheit_neben_menge(z, sp) if z is not None else None)
        or ""
    )


def einheit_neben_menge(z: Zeile, sp: dict) -> str | None:
    """Unzugeordnetes Wort direkt rechts neben der Menge, wenn es eine Einheit ist (Spalte wurde
    nicht zugeordnet, der Druck steht aber noch da)."""
    mws = sp.get("BT-129") or []
    if not mws:
        return None
    benutzt = {id(w) for ws in sp.values() for w in ws}
    rechts = mws[-1].x1
    nachbarn = [w for w in z.woerter if id(w) not in benutzt and rechts - 1 <= w.x0 <= rechts + 40]
    t = _text(nachbarn)
    return t if t and einheit_code(t) else None


_WAEHRUNG_WORT = re.compile(r"^(?:€|EUR|EURO|USD|CHF|[%*])$", re.I)


def _ist_preiswort(t: str, fmt: str | None) -> bool:
    """Zahl, Währung oder Preiseinheit – bleibt in der Preis-/Betragsspalte."""
    if zahlen(t, fmt) or betraege(t, fmt):
        return True
    if _WAEHRUNG_WORT.match(t) or t.startswith("/") or _PE_WORT.match(t):
        return True
    return bool(re.fullmatch(r"(?:€|EUR|EURO)?/\S+", t, re.I))


def einheit_zur_menge(sp: dict[str, list[Wort]]) -> None:
    """Ohne Einheitenspalte: Einheit direkt hinter der Menge („2,00 Stunden“, „1 Stk.“) gehört zur Mengenzelle,
    auch wenn sie über den Spaltenrand in die Nachbarspalte ragt (Spalten vom Kopf bzw. von den Zahlen aus
    geschnitten)."""
    mws = sp.get("BT-129")
    if not mws:
        return
    for c in ("BT-153", "BT-146"):
        ws = sp.get(c)
        if not ws:
            continue
        w = min(ws, key=lambda w: w.x0)
        if 0 <= w.x0 - mws[-1].x1 <= 6 and w.top == mws[-1].top and einheit_code(w.t):
            sp["BT-129"] = mws + [w]
            sp[c] = [x for x in ws if x is not w]
            return


def beschreibung_aus_zahlspalten(sp: dict[str, list[Wort]], fmt: str | None) -> None:
    """Wörter vor dem Betrag in Preis-/Betragsspalte gehören zur Bezeichnung.

    Die angelernte Bezeichnungsspalte ist oft schmaler als der längste Text einer späteren
    Rechnung: überstehende Wörter („mit“, „auf“) landen in BT-146, die Folgezeile gilt dann
    nicht als Fortsetzung und der Rest der Bezeichnung entfällt.
    """
    for c in ("BT-146", "BT-149", "gesamt"):
        ws = list(sp.get(c) or [])
        if not ws:
            continue
        i = 0
        while i < len(ws) and not (zahlen(ws[i].t, fmt) or betraege(ws[i].t, fmt)):
            # Einheit, Preiseinheit („3,40€/10“) und Betrag mit Beiwerk („1,00*“) bleiben
            # in der Zahlspalte. Nur Text ohne Ziffern („mit“, „auf“) wandert.
            if _ist_preiswort(ws[i].t, fmt) or einheit_code(ws[i].t) or re.search(r"\d", ws[i].t):
                break
            i += 1
        if not i:
            continue
        prefix, rest = ws[:i], ws[i:]
        sp.setdefault("BT-153", []).extend(prefix)
        sp["BT-153"].sort(key=lambda w: (w.x0, w.top))
        if rest:
            sp[c] = rest
        else:
            sp.pop(c, None)


def zeile_lesen(
    z: Zeile, pv: dict, bereiche=None
) -> tuple[PosRoh | None, dict[str, list[Wort]], str]:
    """Eine Tabellenzeile -> (Position oder None, Wörter je Spalte, Grund der Ablehnung).

    Menge und Bezeichnung ohne Einzelpreis und Betrag (beide Spalten leer) ergeben eine Position zu 0,00.

    Mit ``anker_betrag`` (Spalten als eigene Rahmen gezogen) trägt die Betragsspalte die Zeile: fehlen Menge oder
    Einzelpreis, werden sie aus dem Betrag ergänzt (Menge 1 bzw. Betrag ÷ Menge), wenn die Rechnung aufgeht."""
    fmt = pv.get("format")
    sp = _zuordnen(
        z, bereiche if bereiche is not None else _bereiche(pv), bool(pv.get("spalten_fest"))
    )
    if "BT-130" not in pv.get("spalten", {}):
        einheit_zur_menge(sp)
    beschreibung_aus_zahlspalten(sp, fmt)
    pe_text = preiseinheit_abtrennen(sp, fmt) if "BT-149" not in pv.get("spalten", {}) else None
    sp = {c: ws for c, ws in sp.items() if ws}
    g = _spaltenwert(sp.get("gesamt", []), betraege, fmt)
    e = _spaltenwert(sp.get("BT-146", []), zahlen, fmt)  # Einzelpreis auch mit 3–4 Nachkommastellen
    m = _spaltenwert(sp.get("BT-129", []), zahlen, fmt)
    if not m and sp.get("BT-129"):
        m = zahlen(menge_ohne_einheit(_text(sp.get("BT-129", []))), fmt)
    if g and pv.get("anker_betrag") and not (e and m):
        gv = g[0][0]
        if m and not sp.get("BT-146") and m[0][0]:
            e = [(gv / m[0][0], m[0][1])] if (gv / m[0][0]) * m[0][0] == gv else []
        elif e and not sp.get("BT-129") and e[0][0]:
            q = gv / e[0][0]
            m = [(q, e[0][1])] if q == q.to_integral_value() or q * e[0][0] == gv else []
        elif not sp.get("BT-146") and not sp.get("BT-129"):
            m, e = [(Decimal("1"), g[0][1])], [(gv, g[0][1])]
    if (
        m
        and m[0][0] > 0
        and not g
        and not e
        and sp.get("BT-153")
        and not sp.get("gesamt")
        and not sp.get("BT-146")
    ):
        # Menge + Bezeichnung ohne Preis und Betrag (z. B. „1 Mindermengenzuschlag“ ohne Berechnung):
        # Position mit 0,00 – BR-27 erlaubt 0; ohne Menge bleibt die Zeile Text
        g, e = [(Decimal("0.00"), m[0][1])], [(Decimal("0.00"), m[0][1])]
    if not (g and e and m):
        gruende = [
            f"{n} {'keine Zahl' if sp.get(c) else 'leer'}"
            for n, v, c in (
                ("Betrag", g, "gesamt"),
                ("Einzelpreis", e, "BT-146"),
                ("Menge", m, "BT-129"),
            )
            if not v
        ]
        return None, sp, ", ".join(gruende)
    pe = zahlen(_text(sp.get("BT-149", [])).lstrip("/"), fmt)
    pe_w = pe[0][0] if pe else pe_text
    mw, ew, pe_w = _lesart_waehlen(
        m,
        e,
        g[0][0],
        pe_w,
        Decimal(str(pv.get("preiseinheit_fest", "1"))),
        pe_raten=not pe and pe_text is None and "BT-149" not in pv.get("spalten", {}),
    )
    return (
        PosRoh(
            nr=_text(sp.get("BT-126", [])),
            artikelnummer=_text(sp.get("BT-155", [])),
            preiseinheit=pe_w,
            bezeichnung=_text(sp.get("BT-153", [])),
            menge=mw,
            einheit_text=_einheit_text(sp, pv, z),
            einzelpreis=ew,
            steuer_text=_text(sp.get("steuer", [])),
            gesamt=g[0][0],
        ),
        sp,
        "Position",
    )


def _lesart_waehlen(
    m: list, e: list, g: Decimal, pe: Decimal | None, pe_fest: Decimal, pe_raten: bool
):
    """Rechnerische Gegenprobe je Position: Menge × Preis ÷ Preiseinheit = Positionsbetrag. Hat eine Zahl mehrere
    Lesarten (z. B. „1.000“) oder fehlt die Preiseinheit im Druck, gewinnt die Lesart, die aufgeht; geht keine
    auf, bleibt die erste (rechnen.berechnen meldet die Abweichung dann als „prüfen“). -> (Menge, Preis, PE)."""
    erste = (m[0][0], e[0][0], pe)
    pes = [pe] + ([Decimal(100), Decimal(1000)] if pe_raten else [])
    for p_ in pes:
        for mm, _ in m[:3]:
            for ee, _ in e[:3]:
                if (
                    abs(rechnen.positionsbetrag(mm, ee, p_ if p_ is not None else pe_fest) - g)
                    <= rechnen.TOLERANZ
                ):
                    if (mm, ee, p_) != erste:
                        log.info(
                            "Position: Lesart gewählt, die aufgeht (Menge × Preis ÷ PE = Betrag)"
                        )
                    return mm, ee, p_
    return erste


# Zeilen am Seitenwechsel einer mehrseitigen Tabelle: „Übertrag“, „Zwischensumme“, „Fortsetzung auf Seite 2“ …
UEBERTRAG = re.compile(
    r"^(?:übertrag|uebertrag|saldovortrag|vortrag|zwischensumme|seitensumme|summe\s+(?:seite|blatt)|"
    r"fortsetzung|forts\.|weiter\s+(?:auf|nächste)|continued|carried\s+forward|"
    r"brought\s+forward)(?!\w)",
    re.I,
)
# Seitenzahl als eigene Zeile („Seite 2 von 3“, „Blatt 2/3“, „Page 2 of 3“) – gehört nie zur Tabelle
SEITENZAHL = re.compile(
    r"^(?:-\s*)?(?:seite|blatt|page)\s*:?\s*\d+\s*(?:(?:von|/|of)\s*\d+)?(?:\s*-)?$", re.I
)


def ist_uebertrag(z: Zeile) -> bool:
    """Zeile beginnt mit „Übertrag“, „Zwischensumme“ … (Falz-/Lochmarken und Zeichen davor zählen nicht) –
    eine Bezeichnung „Fortsetzung Wartung“ mitten in einer Position ist damit kein Übertrag."""
    t = re.sub(r"^[\W\d_]*?(?=[^\W\d_])", "", adapter_pdf.ohne_steuerzeichen(z.text).strip())
    return bool(UEBERTRAG.match(t))


def _ist_seitenzahl(z: Zeile) -> bool:
    return bool(SEITENZAHL.match(" ".join(adapter_pdf.ohne_steuerzeichen(z.text).split())))


# Die eine Wortliste für Summenzeilen (Assistent und Vorlage): Netto/Summe/Warenwert …, USt/MwSt,
# Brutto/Rechnungsbetrag als ganze Wörter, Zusammensetzungen auf „-summe“ (Rechnungssumme, Nettosumme)
SUMMENWORT = re.compile(
    r"(?<![^\W\d_])(?:netto\w*|gesamt\s*netto|nettobetrag|\w*summe|"
    r"warenwert|subtotal|gesamtbetrag|endbetrag|endsumme|rechnungsbetrag|brutto\w*|total|mwst|ust|"
    r"umsatzsteuer|mehrwertsteuer)(?![^\W\d_])",
    re.I,
)
SUMMENANFANG = re.compile(
    r"^[\W\d_]*(?:gesamt|endsumme)(?![^\W\d_])", re.I
)  # „Gesamt 1.234,00“ – nur am Zeilenanfang


def summentext(text: str) -> bool:
    """Steht ein Summenwort in der Zeile? Nur der Text – ob die Zeile wirklich Summen trägt (Betrag in der
    Gesamt-Spalte, keine Menge/kein Preis), prüft ``ist_summenzeile``."""
    t = adapter_pdf.ohne_steuerzeichen(text)
    return bool(SUMMENWORT.search(t) or SUMMENANFANG.search(t))


SUMMENZEILE_GRUND = "Summenzeile (Netto/USt/Brutto)"


def ist_summenzeile(z: Zeile, pv: dict, bereiche=None) -> bool:
    """Sieht die Zeile nach Summen aus? Summenwort (Netto, Summe, Warenwert, USt, Brutto …), ein Betrag in der
    Gesamt-Spalte und weder Menge noch Einzelpreis – so beendet sie die Tabelle, auch ohne Abstand direkt unter
    den Positionen und noch im Tabellenrahmen. Eine Sammelzeile mit Menge und Einzelpreis bleibt Position."""
    if not summentext(z.text):
        return False
    fmt = pv.get("format")
    sp = _zuordnen(
        z, bereiche if bereiche is not None else _bereiche(pv), bool(pv.get("spalten_fest"))
    )
    if "BT-149" not in pv.get("spalten", {}):
        preiseinheit_abtrennen(sp, fmt)
    if not _spaltenwert(sp.get("gesamt", []), betraege, fmt):
        return False
    return not (
        _spaltenwert(sp.get("BT-129", []), zahlen, fmt)
        or _spaltenwert(sp.get("BT-146", []), zahlen, fmt)
    )


def _geht_weiter(zeilen: list[Zeile], i: int) -> bool:
    """Endet die Tabelle an Zeile ``i`` (z. B. Trennlinie) nur auf dieser Seite? Ja, wenn darunter auf der Seite
    ein „Übertrag“ folgt, bevor eine Summenzeile kommt – oder die Seite ohne Summenzeile endet und noch Seiten
    folgen."""
    seite = zeilen[i].seite
    for z in zeilen[i + 1 :]:
        if z.seite != seite:
            return True
        if ist_uebertrag(z):
            return True
        if summentext(z.text) and betraege(z.text):
            return False
    return False


_BINDEWORT = re.compile(r"^(?:und|oder|bzw\.?|sowie|bis)\b")


def bezeichnung_fortsetzen(alt: str, fort: str) -> str:
    """Folgezeile an die Bezeichnung hängen. Trennstrich am Zeilenende: „Montage-“ + „material“ ->
    „Montagematerial“, „Edelstahl-“ + „Schraube“ -> „Edelstahl-Schraube“; „Front-“ + „und Rücklicht“ bleibt
    „Front- und Rücklicht“."""
    if re.search(r"[^\W\d_]-$", alt) and fort and not _BINDEWORT.match(fort):
        if fort[0].islower():
            return alt[:-1] + fort
        if fort[0].isupper():
            return alt + fort
    return alt + " " + fort


def _schrifthoehe(ws: list[Wort]) -> float:
    """Typische Schrifthöhe einer Zeile (Median der Worthöhen), 0 ohne Wörter."""
    h = sorted(w.bottom - w.top for w in ws if w.bottom > w.top)
    return h[len(h) // 2] if h else 0.0


def _position_folgt(zeilen: list[Zeile], i: int, pv: dict, bereiche: dict, abstand: float) -> bool:
    """„Zwischensumme“ mitten in der Tabelle: Folgt direkt darunter (gleiche Seite, ohne Lücke) eine Zeile, die
    sich als Position lesen lässt, endet die Tabelle hier nicht."""
    if i + 1 >= len(zeilen):
        return False
    z, n = zeilen[i], zeilen[i + 1]
    if n.seite != z.seite or n.top - z.top > 2 * abstand + 2:
        return False
    if ist_uebertrag(n) or summentext(n.text) or ist_trennlinie(n):
        return False
    return zeile_lesen(n, pv, bereiche)[0] is not None


def _bis_tabellenende(
    zeilen: list[Zeile], i: int, pv: dict, bereiche: dict, abstand: float
) -> bool:
    """Folgeseite, Zeile ``i`` liegt unter dem Rahmen: gehört sie trotzdem zur Tabelle? Ja, wenn von hier ohne
    Lücke (Zeilenabstand ≤ 2 Zeilen) auf derselben Seite ein „Übertrag“ oder die Summenzeile folgt – die Tabelle
    reicht auf dieser Seite tiefer als auf der Rahmenseite. Der Rahmen wird damit nur nach unten ergänzt."""
    seite, vorige = (
        zeilen[i].seite,
        zeilen[i - 1].top if i and zeilen[i - 1].seite == zeilen[i].seite else None,
    )
    for z in zeilen[i:]:
        if z.seite != seite or (vorige is not None and z.top - vorige > 2 * abstand + 2):
            return False
        if ist_uebertrag(z) or ist_summenzeile(z, pv, bereiche):
            return True
        vorige = z.top
    return False


def summenblock(pv: dict | None, zeilen: list[Zeile]) -> list[tuple[Decimal, list[Wort]]]:
    """Beträge der Summenzeilen am Tabellenende (Gesamt-Spalte), von oben nach unten – Lesarten für die
    rechnerische Gegenprobe (``summen_lesart``)."""
    if not pv or not pv.get("kopf"):
        return []
    prot: list = []
    positionen_auslesen(pv, zeilen, prot)
    out = []
    for z, grund in prot:
        if SUMMENZEILE_GRUND not in grund:
            continue
        sp = _zuordnen(z, _bereiche(pv), bool(pv.get("spalten_fest")))
        b = _spaltenwert(sp.get("gesamt", []), betraege, pv.get("format"))
        if b:
            out.append((b[0][0], sp["gesamt"]))
    return out


SUMMEN_TOLERANZ = rechnen.SUMMEN_TOLERANZ


def summen_lesart(
    pos_summe: Decimal | None, gelesen: dict[str, Decimal | None], kandidaten: list[Decimal]
) -> tuple[dict[str, Decimal | None], str]:
    """Rechnerische Gegenprobe als Schiedsrichter für Netto (BT-109), USt (BT-110) und Brutto (BT-112):
    Summe der Positionen = Netto und Netto + USt = Brutto (USt auch als Summe mehrerer Steuerzeilen).
    Gehen die gelesenen Werte auf -> („ok“); sonst gewinnt die Lesart aus ``kandidaten`` (Beträge der
    Summenzeilen), die aufgeht -> („gewählt“); geht keine auf -> gelesene Werte und „geht nicht auf“
    (dann „prüfen“ statt still falscher Werte). Fehlt die USt im Druck, prüft nur Netto (und Brutto ≥ Netto)."""
    from itertools import combinations

    tol = SUMMEN_TOLERANZ

    def nah(a, b):
        return a is not None and b is not None and abs(a - b) <= tol

    def netto_ok(n):
        return n is not None and (pos_summe is None or nah(n, pos_summe))

    n0, u0, b0 = gelesen.get("BT-109"), gelesen.get("BT-110"), gelesen.get("BT-112")
    if netto_ok(n0) and (
        b0 is None or (u0 is None and b0 >= n0 - tol) or nah(n0 + (u0 or Decimal(0)), b0)
    ):
        return dict(gelesen), "ok"
    kand = list(dict.fromkeys(kandidaten))
    netto = [n for n in dict.fromkeys(([n0] if n0 is not None else []) + kand) if netto_ok(n)]
    brutto = list(dict.fromkeys(([b0] if b0 is not None else []) + kand))
    for n in netto:
        for b in brutto:
            if not b > n + tol:
                continue
            ust = [
                x
                for x in dict.fromkeys(([u0] if u0 is not None else []) + kand)
                if 0 < x < b and x != n
            ]
            if any(nah(n + u, b) for u in ust):
                u = next(u for u in ust if nah(n + u, b))
                return {**gelesen, "BT-109": n, "BT-110": u, "BT-112": b}, "gewählt"
            for k in (2, 3):  # mehrere Steuersätze: USt = Summe der Steuerzeilen
                for teil in combinations(ust, k):
                    if nah(n + sum(teil), b):
                        return {**gelesen, "BT-109": n, "BT-110": sum(teil), "BT-112": b}, "gewählt"
    return dict(gelesen), "geht nicht auf"


def fortsetzung_text(sp: dict[str, list[Wort]]) -> str | None:
    """Text einer Zeile, die nur die Bezeichnung der Position darüber fortsetzt, sonst None: Wörter nur in der
    Bezeichnung – oder eine Kommentarzeile, die in der Einheitenspalte beginnt und ohne Lücke in die Bezeichnung
    läuft („davon mit Härtung 12 Stück“). Ohne Menge, Preis und Betrag (die stehen dann in keiner Spalte)."""
    if not sp or not set(sp) <= {"BT-153", "BT-130"} or "BT-153" not in sp:
        return None
    if "BT-130" in sp:
        ein, bez = (
            sorted(sp["BT-130"], key=lambda w: w.x0),
            sorted(sp["BT-153"], key=lambda w: w.x0),
        )
        if ein[-1].x0 > bez[0].x0:
            return None
        zw = (ein[-1].x1 - ein[-1].x0) / max(len(ein[-1].t), 1)  # Zeichenbreite
        if (
            bez[0].x0 - ein[-1].x1 > 2.5 * zw + 1
        ):  # Lücke wie zwischen zwei Spalten: kein durchlaufender Text
            return None
        return _text(ein + bez)
    return _text(sp["BT-153"])


def positionen_auslesen(
    pv: dict, zeilen: list[Zeile], protokoll: list | None = None
) -> list[PosRoh]:
    """Positionen zwischen Kopfzeile und Ende, auch über mehrere Seiten. ``protokoll`` bekommt je Zeile
    (Zeile, Grund) – für die Diagnose.

    Mehrseitig: Die Tabelle geht auf der nächsten Seite weiter, wenn sie auf der vorigen nicht geendet hat (Ende
    erst an der Summe, nicht am „Übertrag“). Dort beginnt sie an einer wiederholten Kopfzeile oder – ohne
    Kopfzeile – am oberen Rand des Tabellenrahmens (``pv["rahmen"]``, gilt auf jeder Seite gleich). Übertrags-,
    Zwischensummen- und Seitenzahlzeilen gehören nicht dazu."""
    bereiche = _bereiche(pv)
    rahmen = pv.get("rahmen")
    abstand = pv.get("zeilenabstand", 14)
    out: list[PosRoh] = []
    pos_hoehe = 0.0  # Schrifthöhe der letzten Positionszeile
    zustand = "vor"  # vor | aktiv | seitenende | folge (nächste Seite: Tabelle geht weiter) | ende
    seite = None
    vorige_top = None
    auf_seite = 0  # Positionen auf der aktuellen Seite
    tiefste = 0.0  # tiefste Position bisher (Grenze nach unten auf Folgeseiten ohne Kopfzeile)
    erste_seite = None
    notiz = protokoll.append if protokoll is not None else (lambda _x: None)
    for i, z in enumerate(zeilen):
        if z.seite != seite:
            seite, vorige_top, auf_seite = z.seite, None, 0
            if zustand in ("aktiv", "seitenende"):
                zustand = "folge"
        if zustand == "ende":  # nur noch für die Diagnose: Summenblock darunter benennen
            if i and zeilen[i - 1].seite == z.seite and ist_summenzeile(z, pv, bereiche):
                notiz((z, SUMMENZEILE_GRUND))
                continue
            break
        if _passt_zeile(pv["kopf"], z):
            zustand, vorige_top = "aktiv", None
            if erste_seite is None:
                erste_seite = z.seite
            notiz((z, "Kopfzeile"))
            continue
        if zustand == "vor":
            continue
        if zustand == "folge":  # Folgeseite ohne (bisher) wiederholte Kopfzeile
            if ist_uebertrag(
                z
            ):  # „Übertrag“ oben auf der Seite: Tabelle geht direkt darunter weiter
                zustand = "aktiv"
                notiz((z, "Übertrag von der vorigen Seite"))
                continue
            if rahmen and z.top >= rahmen[1] - 2:
                zustand = "aktiv"
            else:
                continue
        if zustand == "seitenende":
            notiz((z, "nach dem Übertrag (Seitenende)"))
            continue
        if _ist_seitenzahl(z):
            notiz((z, "Seitenzahl"))
            continue
        if ist_uebertrag(z):
            if auf_seite and _position_folgt(zeilen, i, pv, bereiche, abstand):
                notiz((z, "Zwischensumme in der Tabelle"))  # darunter geht es mit Positionen weiter
                continue
            if auf_seite and ist_summenzeile(z, pv, bereiche) and not _geht_weiter(zeilen, i):
                notiz((z, f"Tabellenende – {SUMMENZEILE_GRUND}"))  # „Zwischensumme“ am Ende = Netto
                zustand = "ende"
                continue
            if auf_seite:
                zustand = "seitenende"
                notiz((z, "Übertrag (Tabelle geht auf der nächsten Seite weiter)"))
            else:
                notiz((z, "Übertrag von der vorigen Seite"))
            continue
        if (
            rahmen
            and z.seite != erste_seite
            and z.top > max(rahmen[3], tiefste) + 2 * abstand
            and not _bis_tabellenende(zeilen, i, pv, bereiche, abstand)
        ):
            zustand = "seitenende"
            notiz((z, "unter dem Tabellenrahmen"))
            continue
        if ist_trennlinie(z):  # Linie unter der Kopfzeile oder vor den Summen
            if out and pv.get("ende") and _passt_zeile(pv["ende"], z, praefix=True):
                if auf_seite and _geht_weiter(zeilen, i):
                    zustand = "seitenende"
                    notiz((z, "Trennlinie am Seitenende"))
                    continue
                notiz(
                    (z, "Tabellenende")
                )  # ältere Vorlagen: Ende = Trennlinie, erst nach Positionen
                zustand = "ende"
                continue
            notiz((z, "Trennlinie"))
            continue
        if ist_summenzeile(
            z, pv, bereiche
        ):  # sieht nach Summen aus (auch im Rahmen): nie eine Position
            if out:  # nach Positionen: hier endet die Tabelle
                notiz((z, f"Tabellenende – {SUMMENZEILE_GRUND}"))
                zustand = "ende"
            else:
                notiz((z, SUMMENZEILE_GRUND))
            continue
        if pv.get("ende") and _passt_zeile(pv["ende"], z, praefix=True):
            notiz((z, "Tabellenende"))
            zustand = "ende"
            continue
        p, sp, grund = zeile_lesen(z, pv, bereiche)
        if p:
            out.append(p)
            pos_hoehe = _schrifthoehe(z.woerter)
            vorige_top = z.top
            auf_seite += 1
            tiefste = max(tiefste, z.top)
            notiz((z, grund if z.seite == erste_seite else f"{grund} (Seite {z.seite + 1})"))
        elif (
            out
            and (fort := fortsetzung_text(sp)) is not None
            and (
                (vorige_top is not None and z.top - vorige_top <= abstand * 1.6 + 2)
                or (vorige_top is None and auf_seite == 0)
            )
        ):
            vorige_top = z.top
            tiefste = max(tiefste, z.top)
            if pos_hoehe and _schrifthoehe(sp.get("BT-153") or z.woerter) < 0.8 * pos_hoehe:
                # kleiner gedruckt als die Position („Artikelbeschreibung kurz“): Zusatz, nicht Bezeichnung
                notiz((z, "kleiner gedruckter Zusatz unter der Position"))
                continue
            out[-1].bezeichnung = bezeichnung_fortsetzen(out[-1].bezeichnung, fort)
            notiz((z, "Fortsetzung der Bezeichnung"))
        else:
            if (
                sp
            ):  # eine Zeile ganz neben den Spalten (Seitenleiste) unterbricht die Bezeichnung nicht
                vorige_top = None
            if not sp:
                grund = "kein Wort in den Spalten"
            elif set(sp) <= {"BT-153"}:
                grund = "nur Bezeichnung, keine Position direkt darüber"
            notiz((z, f"verworfen: {grund}"))
    return out


OHNE_EINHEIT = (
    "(ohne Einheit)"  # Zeilen ohne Text in der Einheitenspalte – Code wählt der Nutzer einmal
)


def einheit_schluessel(pv: dict, p: PosRoh) -> str:
    """Schlüssel der Einheit für ``mappings.einheiten``: Text aus Spalte oder Mengenzelle, sonst ``*`` (feste
    Einheit) bzw. OHNE_EINHEIT, wenn die Vorlage dafür einen Code kennt."""
    if p.einheit_text:
        return p.einheit_text
    if "einheiten" not in pv:
        return "*"
    return OHNE_EINHEIT if (pv.get("einheiten") or {}).get(OHNE_EINHEIT) else ""


def _pos_einheit(pv: dict, p: PosRoh) -> str | None:
    if "einheit_fest" in pv:
        return pv["einheit_fest"]
    return (pv.get("einheiten") or {}).get(einheit_schluessel(pv, p))


def pos_preiseinheit(pv: dict, p: PosRoh) -> Decimal:
    """BT-149: Spalte oder Zeichen am Preis im Druck („/100“), sonst fester Wert der Vorlage, sonst 1."""
    if p.preiseinheit is not None:
        return p.preiseinheit
    return Decimal(str(pv.get("preiseinheit_fest", "1")))


def steuer_zuordnung(pv: dict) -> dict:
    """Steuer-Mapping für ``rechnung_bauen`` aus der Positionsbeschreibung: Steuerspalte oder fester Satz der
    Vorlage. Ohne beides kein stiller Standard (sonst gälte modell.Steuer = S 19 %): Steuerschlüssel „*“ bleibt
    unzugeordnet -> Prüfhinweis je Position."""
    st = dict(pv.get("steuer") or ({"*": pv["steuer_fest"]} if pv.get("steuer_fest") else {}))
    return {**st, "unbekannt": "pruefen"}


def ist_steuerbuchstabe(t: str) -> bool:
    """Steuerkennzeichen in der Positionszeile: einzelner Buchstabe („A“, „B“), ohne Satz."""
    return bool(re.fullmatch(r"[A-Za-z]\.?", (t or "").strip()))


def steuerbuchstaben_aus_zeilen(zeilen: list[Zeile]) -> dict[str, dict]:
    """Buchstabe → Steuersatz aus den Steuerzeilen des Summenblocks („USt A 19 % …“)."""
    out: dict[str, dict] = {}
    for z in zeilen:
        if not re.search(r"ust|mwst|umsatzsteuer|steuer|vat|%", z.text, re.I):
            continue
        buch = re.findall(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])", z.text)
        satz = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", z.text)
        if len(buch) != 1 or not satz:
            continue
        key = buch[0].rstrip(".")
        out[key] = {"BT-151": "S", "BT-152": satz[1].replace(",", ".")}
        if key != key.upper():
            out[key.upper()] = out[key]
    return out


def _pos_steuer(pv: dict, p: PosRoh) -> dict | None:
    if p.steuer_text and "steuer" in (pv.get("spalten") or {}):
        st = (pv.get("steuer") or {}).get(p.steuer_text)
        if st is not None:
            return st
        # Buchstabe ohne Zuordnung: nicht still den festen Satz der Rechnung nehmen
        if ist_steuerbuchstabe(p.steuer_text):
            return None
    if "steuer_fest" in pv:
        return pv["steuer_fest"]
    return (pv.get("steuer") or {}).get(p.steuer_text)


def _pos_gleich(pv: dict, ex: PosRoh, p, tol: Decimal, hinweis: str = "") -> bool:
    st = _pos_steuer(pv, ex) or {}
    if "fall" in st or isinstance(
        st, str
    ):  # Steuerfall (ab 0.9.7): über den Hinweis der Rechnung auflösen
        from .aufbau import steuer_aus_code

        s = steuer_aus_code(st, hinweis)
        st = {"BT-151": s.kategorie, "BT-152": str(s.satz)} if s else {}
    ok = (
        norm(ex.bezeichnung) == norm(p.bezeichnung)
        and ex.menge == p.menge
        and ex.einzelpreis is not None
        and abs(ex.einzelpreis - (p.einzelpreis or Decimal(0))) <= tol
        and (_pos_einheit(pv, ex) or "") == (p.einheit or "")
        and pos_preiseinheit(pv, ex) == (p.preiseinheit or Decimal("1"))
        and st.get("BT-151") == p.steuer.kategorie
        and Decimal(str(st.get("BT-152", "-1"))) == p.steuer.satz
    )
    if "BT-155" in pv["spalten"]:
        ok = ok and ex.artikelnummer == p.artikelnummer
    if "BT-126" in pv["spalten"]:
        ok = ok and ex.nr == p.nr
    return ok


# ---------------------------------------------------------------- Vorlage lernen und bewerten
def lernfelder(r: Rechnung, profil: dict) -> list[str]:
    kopf = (profil.get("felder") or {}).get("kopf") or {}
    zusatz = [f for f in ZUSATZFELDER if f in kopf and "spalte" in kopf[f]]
    if "leistungsmonat" in kopf:
        zusatz.append("BG-14")
    if profil.get("quelle") == "pdf":  # Nur PDF: alles, was der Assistent abfragt, steht im Druck
        zusatz = list(ZUSATZFELDER) + ["BT-25"]  # BT-25 nur bei Gutschrift (sonst kein Sollwert)
    felder = [f for f in PRUEFFELDER if f != "BT-119"] + zusatz
    return [f for f in dict.fromkeys(felder) if soll_wert(r, f) is not None]


def feld_gleich(feld: str, typ: str, soll, text: str, tol: Decimal) -> bool:
    """Gelesener Text = Sollwert? Belegart als Code (Titel -> 380/381), Bezug als Nummer (ohne Datum)."""
    if feld == "BT-3":
        return belegart_code(text) == str(soll)
    if feld == "BT-25":
        return norm(bezug_zerlegen(text)[0]) == norm(str(soll))
    return gleich(typ, soll, text, tol)


def bewerten(
    v: dict, r: Rechnung, zeilen: list[Zeile], tol: Decimal
) -> tuple[int, int, dict[str, bool]]:
    """-> (Treffer, Anzahl, je Feld richtig?) – wie gut liest die Vorlage diese Rechnung? Weichen die Positionen
    ab, steht unter „_position“ die erste abweichende (1-basiert; 0 = Anzahl weicht ab)."""
    ergebnis: dict[str, bool] = {}
    for f, regel in (v.get("felder") or {}).items():
        if f == ANSCHRIFT_BLOCK:
            ergebnis[f] = _block_passt(regel, r, zeilen, v)
            continue
        soll = soll_wert(r, f)
        if soll is None:
            continue
        erg = vorlage_feld_lesen(v, f, regel, zeilen)
        ergebnis[f] = bool(erg and feld_gleich(f, regel["typ"], soll, erg[0], tol))
    treffer, anzahl = sum(ergebnis.values()), len(ergebnis)
    pv = v.get("positionen")
    if (
        pv
        and isinstance(pv.get("steuer_fest"), dict)
        and pv["steuer_fest"].get("fall") == "hinweis"
    ):
        m = {
            "*": pv["steuer_fest"]
        }  # „je Rechnung“ ohne Satz: Satz aus dem Druck wie beim Lesen (nur_pdf)
        steuer_fest_aus_druck(m, {"steuerhinweis": (r.steuerhinweis, None)}, zeilen)
        pv = {**pv, "steuer_fest": m["*"]}
    if pv:
        ex = positionen_auslesen(pv, zeilen)
        gleich_je = [_pos_gleich(pv, e, p, tol, r.steuerhinweis) for e, p in zip(ex, r.positionen)]
        pt = sum(gleich_je)
        anzahl += max(len(ex), len(r.positionen))
        treffer += pt
        ergebnis["positionen"] = pt == len(r.positionen) == len(ex)
        if not ergebnis["positionen"]:
            if False in gleich_je:
                ergebnis["_position"] = gleich_je.index(False) + 1
            else:
                ergebnis["_position"] = 0  # Anzahl der Positionen weicht ab
    else:
        anzahl += len(r.positionen)
        ergebnis["positionen"] = False
    return treffer, anzahl, ergebnis


def zaehler_grund(erg: dict) -> str:
    """Warum zählt diese Rechnung nicht für die Freigabe? -> Klartext („Rechnungsdatum geändert“,
    „Position 3 geändert“) oder "" (zählt). Freiwillige Felder (``ZAEHLER_FREIWILLIG``) zählen nicht."""
    for f, ok in erg.items():
        if not ok and not f.startswith("_") and f != "positionen" and f not in ZAEHLER_FREIWILLIG:
            return f"{feldname(f)} geändert"
    if not erg.get("positionen", True):
        nr = erg.get("_position") or 0
        return f"Position {nr} geändert" if nr else "Anzahl der Positionen geändert"
    return ""


def _block_passt(regel: dict, r: Rechnung, zeilen: list[Zeile], v: dict | None = None) -> bool:
    gelesen = vorlage_anschrift_lesen(v, regel, zeilen)
    for f in BLOCKFELDER:
        soll = soll_wert(r, f) or ""
        if norm(str(soll)) != norm(gelesen.get(f, ("", []))[0]):
            return False
    return True


def lernen(
    r: Rechnung,
    zeilen: list[Zeile],
    profil: dict,
    v: dict | None,
    es: dict,
    pv_vorgabe: dict | None = None,
    stellen: dict[str, list[Wort]] | None = None,
    bereiche: dict[str, tuple] | None = None,
    flaechen: dict[str, dict] | None = None,
) -> tuple[dict, float | None]:
    """Vorlage neu anlernen oder fortschreiben. -> (Vorlage, Trefferquote dieser Rechnung oder None).

    ``pv_vorgabe``: Tabellenbeschreibung aus dem Anlern-Assistenten (Rahmen + Spalten) – gilt dann statt der
    selbst gelernten. ``stellen``: Feld -> vom Nutzer bestätigte Fundstelle (siehe ``feld_lernen``).
    ``bereiche``: Feld -> (Seite, (x0, top, x1, bottom), Block?) – vom Nutzer gezogener Rahmen (Regel „bereich“).
    ``flaechen``: Bereiche aus „Bereiche festlegen“ (siehe ``BEREICHE``); None = die der Vorlage bleiben. Geänderte
    Bereiche zählen als Korrektur (Zähler 0) und ihre Felder werden im neuen Rahmen neu gelernt."""
    stellen = stellen or {}
    bereiche = bereiche or {}
    tol = es["toleranz"]
    felder = lernfelder(r, profil)
    variabel = _variabel(r, felder)
    quote = None
    if v is None:
        v = {
            "profil": profil_name(profil),
            "kennung": "",
            "erkennung": {},
            "statistik": {"rechnungen": 0, "folge_treffer": 0, "verlauf": []},
            "felder": {},
        }
        neu = felder
        pos_neu = True
    else:
        treffer, anzahl, erg = bewerten(v, r, zeilen, tol)
        quote = round(treffer / anzahl, 3) if anzahl else 0.0
        neu = [f for f in felder if not erg.get(f, False) or f in stellen]
        pos_neu = not erg.get("positionen")
        st = v["statistik"]
        grund = zaehler_grund(erg)
        st["folge_treffer"] = st.get("folge_treffer", 0) + 1 if anzahl > 0 and not grund else 0
        if grund:
            st["zurueckgesetzt"] = grund
        else:
            st.pop("zurueckgesetzt", None)
        st["verlauf"] = (st.get("verlauf") or [])[-49:] + [quote]
        geaendert = (
            bereiche_unterschied(v.get("bereiche"), flaechen) if flaechen is not None else []
        )
        if geaendert:
            namen = ", ".join(BEREICH_NAMEN[b].split(" (")[0] for b in geaendert)
            st["folge_treffer"] = 0
            st["zurueckgesetzt"] = f"Bereiche geändert ({namen})"
            log.info(
                "Vorlage %s-%s: Bereiche geändert (%s) – Zähler zurückgesetzt, Felder darin neu gelernt",
                v.get("profil"),
                v.get("kennung"),
                namen,
            )
            neu += [f for b in geaendert for f in BEREICHE[b] if f in felder and f not in neu]
    if flaechen is not None:
        fl = bereiche_laden({"bereiche": flaechen})
        if fl:
            v["bereiche"] = fl
        else:
            v.pop("bereiche", None)
    vb = bereiche_laden(v)
    for f, (seite, rahmen, block) in bereiche.items():
        b = vb.get(bereich_von(f) or "")
        regel = None
        if b is not None:  # im Bereich lernen (Anker nur aus dem Bereich)
            d = bereich_verschiebung(v, b, zeilen, seite)
            regel = bereich_regel(
                f,
                zeilen_im_rahmen(zeilen, seite, _zonen_rahmen(b, d)),
                seite,
                rahmen,
                variabel,
                block,
            )
            if regel and f != ANSCHRIFT_BLOCK:
                _regel_verschieben(regel, -d)
        if regel is None:
            regel = bereich_regel(f, zeilen, seite, rahmen, variabel, block)
            if regel and b is not None:
                regel["ohne_bereich"] = True
                log.info(
                    "Vorlage: Rahmen für %s liegt außerhalb des Bereichs – gilt auf der ganzen Seite",
                    feldname(f) if f != ANSCHRIFT_BLOCK else "Anschrift",
                )
        if f == ANSCHRIFT_BLOCK:
            if regel and _block_passt(regel, r, zeilen, v):  # ersetzt die einzelnen Käuferregeln
                v["felder"][f] = regel
                for bf in BLOCKFELDER:
                    v["felder"].pop(bf, None)
                    if bf in (v.get("nicht_im_druck") or []):
                        v["nicht_im_druck"].remove(bf)
                neu = [x for x in neu if x not in BLOCKFELDER]
            continue
        if regel:
            v["felder"][f] = regel
            if f in (v.get("nicht_im_druck") or []):
                v["nicht_im_druck"].remove(f)
    neu = [f for f in neu if f not in bereiche or f not in v["felder"]]
    if ANSCHRIFT_BLOCK in v["felder"]:
        if (
            v["felder"][ANSCHRIFT_BLOCK]
            and ANSCHRIFT_BLOCK not in bereiche
            and not _block_passt(v["felder"][ANSCHRIFT_BLOCK], r, zeilen, v)
            and any(f in neu for f in BLOCKFELDER)
        ):
            v["felder"].pop(
                ANSCHRIFT_BLOCK
            )  # Block liest diese Rechnung falsch: einzeln neu lernen
        else:
            neu = [x for x in neu if x not in BLOCKFELDER]
    for f in neu:
        verwandt = v["felder"].get("BT-44") if f in KAEUFERANSCHRIFT else None
        regel = (
            _bt20_baustein_lernen(v, soll_wert(r, f), zeilen, variabel, tol)
            if f == "BT-20" and f not in stellen
            else None
        )
        regel = regel or _im_bereich_lernen(
            v, f, soll_wert(r, f), zeilen, variabel, tol, stellen.get(f)
        )
        if regel is None and bereich_von(f) in vb and stellen.get(f):
            # von Hand angeklickt, steht aber außerhalb des Bereichs: diese Stelle seitenweit lernen (wie ein
            # gezogener Rahmen außerhalb, s. oben); ohne Klick bleibt der Bereich maßgeblich
            regel = feld_lernen(f, soll_wert(r, f), zeilen, variabel, tol, stelle=stellen[f])
            if regel:
                regel["ohne_bereich"] = True
                log.info(
                    "Vorlage: %s außerhalb des Bereichs angeklickt – gilt auf der ganzen Seite",
                    feldname(f),
                )
        if regel is None and bereich_von(f) in vb:
            # Benutzerrahmen hat Vorrang: keine Suche nach der Beschriftung auf der ganzen Seite als Ersatz
            log.info(
                "Vorlage: %s steht nicht im Bereich „%s“ – nicht gelernt (Rahmen prüfen)",
                feldname(f),
                BEREICH_NAMEN[bereich_von(f)],
            )
            v["felder"].pop(f, None)
        elif regel is None:
            regel = feld_lernen(
                f,
                soll_wert(r, f),
                zeilen,
                variabel,
                tol,
                bezug=verwandt.get("top") if verwandt else None,
                stelle=stellen.get(f),
            )
        if regel:
            v["felder"][f] = regel
            v.setdefault("nicht_im_druck", [])
            if f in v["nicht_im_druck"]:
                v["nicht_im_druck"].remove(f)
        elif f not in v["felder"]:
            v.setdefault("nicht_im_druck", [])
            if f not in v["nicht_im_druck"]:
                v["nicht_im_druck"].append(f)
    if not v.get("nicht_im_druck"):
        v.pop("nicht_im_druck", None)
    if pos_neu or pv_vorgabe:
        pv = copy.deepcopy(pv_vorgabe) if pv_vorgabe else positionen_lernen(r, zeilen, tol)
        if pv:
            alt = v.get("positionen") or {}
            for k in ("einheiten", "steuer"):  # früher gelernte Einheiten/Steuertexte behalten
                if alt.get(k) and k in pv:
                    pv[k] = {**alt[k], **pv[k]}
            v["positionen"] = pv
    if v.get("bereiche"):
        bereich_bezug_setzen(v, zeilen)
    v["statistik"]["rechnungen"] = v["statistik"].get("rechnungen", 0) + 1
    if not v["kennung"]:
        texte = []
        for f in ("BT-1", "BT-2", "BT-112"):
            a = (v["felder"].get(f) or {}).get("anker") or []
            if a and "#" not in a:
                texte.append(" ".join(a))
        if v.get("positionen"):
            k = [t for t in v["positionen"]["kopf"] if t != "#"]
            if k:
                texte.append(" ".join(k))
        kennungen = [
            kompakt(w)
            for w in (r.verkaeufer.ust_id, r.zahlung.iban, r.verkaeufer.steuernummer)
            if w and kommt_vor(zeilen, "kennung", w, tol)
        ]
        v["erkennung"] = {"texte": list(dict.fromkeys(texte)), "kennungen": kennungen}
        roh = v["profil"] + "|" + "|".join(sorted(texte + kennungen))
        v["kennung"] = hashlib.sha1(roh.encode("utf-8")).hexdigest()[:8]
    return v, quote


def _bt20_baustein_lernen(
    v: dict, soll, zeilen: list[Zeile], variabel: set[str], tol: Decimal
) -> dict | None:
    """BT-20 ohne gezogenen Rahmen: Ist die Zahlungsbedingung genau der Zahlungsbaustein im Druck (auch über
    mehrere Zeilen), lernt die Vorlage ihn als Rahmen (Regel „bereich“, Anker = Überschrift darüber) – der Nutzer
    muss „Absatz einrahmen“ nicht wählen. Beim Lesen ergänzt ``_bt20_abgleichen`` weitere Zeilen des Bausteins
    (Skonto). -> Regel oder None (Wert anders als der Baustein: wie bisher lernen)."""
    baustein = zahlungsbaustein(zeilen)
    if not soll or baustein is None or norm(zahlungsbaustein_text(baustein[1])) != norm(str(soll)):
        return None
    seite, ws = baustein
    rahmen = rahmen_um(ws)
    b = bereiche_laden(v).get("zahlung")
    regel = None
    if b is not None:
        d = bereich_verschiebung(v, b, zeilen, seite)
        regel = bereich_regel(
            "BT-20", zeilen_im_rahmen(zeilen, seite, _zonen_rahmen(b, d)), seite, rahmen, variabel
        )
        if regel:
            _regel_verschieben(regel, -d)
    if regel is None:
        regel = bereich_regel("BT-20", zeilen, seite, rahmen, variabel)
        if regel and b is not None:
            regel["ohne_bereich"] = True
    if not regel:
        return None
    erg = vorlage_feld_lesen(v, "BT-20", regel, zeilen)
    return regel if erg and gleich(regel["typ"], soll, erg[0], tol) else None


def _im_bereich_lernen(
    v: dict,
    f: str,
    soll,
    zeilen: list[Zeile],
    variabel: set[str],
    tol: Decimal,
    stelle: list[Wort] | None,
) -> dict | None:
    """Feld in seinem Bereich lernen (Seiten nach „Gilt auf“); die Regel muss über ``vorlage_feld_lesen`` den
    Sollwert wieder lesen. -> Regel oder None (kein Bereich oder dort nicht gefunden)."""
    name = bereich_von(f)
    b = bereiche_laden(v).get(name) if name else None
    if b is None or soll is None:
        return None
    for s in bereich_seitenfolge(name, b, zeilen):
        d = bereich_verschiebung(v, b, zeilen, s)
        regel = feld_lernen(
            f, soll, zeilen_im_rahmen(zeilen, s, _zonen_rahmen(b, d)), variabel, tol, stelle=stelle
        )
        if regel:
            regel["seite"] = 0
            _regel_verschieben(regel, -d)  # gespeichert in der Lage von damals (Bezug)
            erg = vorlage_feld_lesen(v, f, regel, zeilen)
            if erg and gleich(regel["typ"], soll, erg[0], tol):
                return regel
    return None


# ---------------------------------------------------------------- Gegenprüfung (Paar PDF + CSV)
@dataclass
class Abweichung:
    feld: str
    name: str
    csv: str
    druck: str

    def text(self) -> str:
        return f"CSV und Druck weichen ab: {self.name} {self.csv} ≠ {self.druck}"


def _ist_telefonnummer(t: str) -> bool:
    """Deutsche Telefon- oder Vorwahlform (führt mit 0 oder +49), keine typische Rechnungsnummer."""
    s = (t or "").strip()
    if s.startswith("+49") or s.startswith("0049"):
        return True
    k = re.sub(r"[\s/().-]", "", s)
    return bool(re.match(r"^0\d{5,}$", k))


# „Gesamt EUR inkl. MwSt.“ ist die Bruttosumme, „Gesamt EUR ohne MwSt.“ die Nettosumme: der Zusatz zählt dort
# nicht als Steuerzeile
_STEUERZUSATZ = {
    "BT-112": re.compile(r"\b(?:inkl|incl|inklusive)\b\.?\s*(?:mwst|ust|umsatzsteuer|vat)\b\.?"),
    "BT-109": re.compile(r"\b(?:ohne|exkl|excl)\b\.?\s*(?:mwst|ust|umsatzsteuer|vat)\b\.?"),
}


def _ohne_steuerzusatz(feld: str, lab: str) -> str:
    return _STEUERZUSATZ[feld].sub(" ", lab) if feld in _STEUERZUSATZ else lab


def _druckwert_suchen(feld: str, zeilen: list[Zeile], v: dict | None) -> str:
    """Was steht im Druck an dieser Stelle? Erst die angelernte Vorlage, dann Text nach einem Schlüsselwort."""
    typ = feldtyp(feld)
    if v and feld in (v.get("felder") or {}):
        erg = vorlage_feld_lesen(v, feld, v["felder"][feld], zeilen)
        if erg and (feld not in OPTIONALE_NUMMERN or nummer_passt(erg[0])):
            return anzeige(typ, lesen_als(typ, erg[0]))
    if v and feld in BLOCKFELDER and ANSCHRIFT_BLOCK in (v.get("felder") or {}):
        t = vorlage_anschrift_lesen(v, v["felder"][ANSCHRIFT_BLOCK], zeilen).get(feld)
        if t:
            return t[0]
    if feld == "BT-110":  # USt je Satz gedruckt („USt 7 % … 18,04“): Summe der Zeilen
        je_satz = []
        for z in zeilen:
            if re.search(r"ust|mwst|vat|umsatzsteuer", norm(z.text)) and "%" in z.text:
                b = [betraege(w.t) for w in z.woerter if betraege(w.t)]
                if b:
                    je_satz.append(b[-1][0][0])
        if je_satz:
            return anzeige(typ, sum(je_satz, Decimal("0")))
    pos, neg, _ = SCHLUESSELWOERTER.get(feld, ("", "", False))
    if not pos:
        return NICHT_GEFUNDEN
    funde = []
    for zi, z in enumerate(zeilen):
        if typ == "betrag" and _ist_seitenzahl(z):
            continue
        for si, seg in enumerate(z.abschnitte):
            lab = norm(_text(seg))
            if not re.search(pos, lab) or (neg and re.search(neg, _ohne_steuerzusatz(feld, lab))):
                continue
            nach = z.abschnitte[si + 1 :]
            if nach and _text(nach[0]).strip() == ":" and len(nach) > 1:
                nach = nach[1:]  # „Bruttosumme | : | 649,09“: Doppelpunkt als eigener Abschnitt
            rest = seg[1:] + (nach[0] if nach else [])
            if (
                feld in OPTIONALE_NUMMERN
            ):  # nur rechts daneben, gleiche Zeile, passende Form – sonst leer
                if not re.match(pos, lab):
                    continue
                k = next((k for k, w in enumerate(seg) if w.t.endswith(":")), None)
                nxt = z.abschnitte[si + 1] if si + 1 < len(z.abschnitte) else None
                if nxt and any(w.t.endswith(":") for w in nxt[:3]):
                    nxt = None  # rechts steht die nächste Beschriftung („Datum: …“)
                ws = nummer_rechts(seg[(k or 0) + 1 :], nxt, seg[k or 0].x1, label_offen=k is None)
                if ws:
                    funde.append(ws[0].t)
                continue
            if typ == "text":  # Nummern: erstes Wort mit Ziffer rechts daneben oder darunter
                darunter = [
                    s2
                    for _, s2 in abschnitte_darunter(
                        zeilen, zi, seg[0].x0, seg[0].x1, DARUNTER_NUMMER * _hoehe(seg[0])
                    )
                ]
                for w in rest + [w for s2 in darunter[:1] for w in s2]:
                    if re.search(r"\d", w.t):
                        if feld == "BT-1" and _ist_telefonnummer(w.t):
                            continue
                        funde.append(w.t)
                        break
                continue
            for n in range(min(len(rest), 4), 0, -1):
                for i in range(len(rest) - n + 1):
                    w = (
                        lesen_als(typ, _text(rest[i : i + n]))
                        if typ not in ("text", "kennung")
                        else None
                    )
                    if w is not None:
                        funde.append(anzeige(typ, w))
                        break
                else:
                    continue
                break
    if not funde and feld == "BT-2":
        funde = _datum_ohne_beschriftung(zeilen)
    if not funde:
        return NICHT_GEFUNDEN
    return funde[-1] if feld in ("BT-109", "BT-110", "BT-112") else funde[0]


# Rechnungsdatum ohne Beschriftung „Datum“: Briefdatum „Göttingen, den 8. Oktober 2026“ oder in der Titelzeile
# „Rechnung Nr. 2026-0417 vom 07.10.2026“ (nicht „Rechnung gemäß Bestellung vom …“)
_DATUM_ORT_DEN = re.compile(r"^[^\W\d][^,:]{1,40},\s*den\s+(.+)$", re.I)
_DATUM_VOM = re.compile(r"rechnung\b(.*?)\bvom\s+(.+)$", re.I)
_DATUM_VOM_FREMD = re.compile(r"bestell|auftrag|order|liefer|angebot|vertrag|schreiben", re.I)


def _datum_ohne_beschriftung(zeilen: list[Zeile]) -> list[str]:
    funde = []
    for z in zeilen:
        for seg in z.abschnitte:
            t = _text(seg)
            m = _DATUM_ORT_DEN.match(t)
            rest = m[1] if m else None
            if rest is None and (m := _DATUM_VOM.search(t)) and not _DATUM_VOM_FREMD.search(m[1]):
                rest = m[2]
            if rest is None:
                continue
            woerter = rest.split()
            for n in range(min(len(woerter), 3), 0, -1):
                d = lesen_als("datum", " ".join(woerter[:n]))
                if d is not None:
                    funde.append(anzeige("datum", d))
                    break
    return funde


def gegenpruefen(
    r: Rechnung, zeilen: list[Zeile], v: dict | None, es: dict
) -> tuple[list[Abweichung], int]:
    """-> (Abweichungen, Anzahl geprüfter Werte). Die CSV gilt; der Druck muss sie zeigen."""
    tol = es["toleranz"]
    abw, n = [], 0
    for feld in es["felder"]:
        soll = soll_wert(r, feld)
        if soll is None:
            continue
        typ, name = PRUEFFELDER[feld]
        n += 1
        if typ == "saetze":
            fehlt = [s for s in soll if not _satz_im_druck(zeilen, s, r)]
            if fehlt:
                da = [s for s in soll if s not in fehlt]
                abw.append(Abweichung(feld, name, anzeige("saetze", soll), anzeige("saetze", da)))
            continue
        ok = kommt_vor(zeilen, typ, soll, tol)
        if not ok and feld == "BT-110":  # nur USt je Satz gedruckt, keine Gesamt-USt
            ok = all(
                kommt_vor(zeilen, "betrag", z.betrag, tol)
                for z in r.summen.steuerzeilen
                if z.betrag
            )
        if not ok and feld == "BG-14":  # Zeitraum als zwei getrennte Daten gedruckt
            ok = kommt_vor(zeilen, "datum", soll[0], tol) and kommt_vor(
                zeilen, "datum", soll[1], tol
            )
        if not ok and typ == "kennung":
            # Kennungen stammen meist aus den Stammdaten; fehlen sie im Druck, ist das kein Widerspruch.
            # Steht dort aber eine *andere* Kennung derselben Art, ist es einer.
            andere = [
                w
                for w in _KENNUNG_RX[feld].findall("\n".join(z.text for z in zeilen))
                if kompakt(w) != kompakt(soll)
            ]
            if andere:
                abw.append(Abweichung(feld, name, anzeige(typ, soll), kompakt(andere[0])))
            continue
        if not ok:
            abw.append(
                Abweichung(feld, name, anzeige(typ, soll), _druckwert_suchen(feld, zeilen, v))
            )
    return abw, n


_KENNUNG_RX = {
    "BT-31": re.compile(r"(?<![A-Z0-9])DE ?\d{3} ?\d{3} ?\d{3}(?!\d)"),
    "BT-32": re.compile(r"(?<![\d/])\d{2,3}/\d{3,4}/\d{4,5}(?![\d/])"),
    "BT-84": re.compile(
        r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?(?![A-Z0-9])"
    ),
}


def _satz_im_druck(zeilen: list[Zeile], satz, r: Rechnung) -> bool:
    s = _satz(satz)
    rx = re.compile(rf"(?<![\d,.]){re.escape(s)}(?:[,.]0+)?\s?%")
    text = "\n".join(z.text for z in zeilen)
    if rx.search(text):
        return True
    if Decimal(str(satz)) == 0:  # steuerfrei: Befreiungsgrund statt „0 %“ genügt
        gruende = [
            z.steuer.befreiungsgrund for z in r.summen.steuerzeilen if z.steuer.befreiungsgrund
        ]
        return any(norm(g) in norm(text) for g in gruende) or bool(
            re.search(r"steuerfrei|befreit", text, re.I)
        )
    return False


def pruefen_und_lernen(r: Rechnung, zeilen: list[Zeile], profil: dict, druckname: str) -> None:
    """Paar CSV + Druck: gegenprüfen (Hinweise an r), bei Übereinstimmung Vorlage fortschreiben."""
    es = einstellungen(profil)
    if not (es["gegenpruefung"] or es["anlernen"]):
        return
    v = vorlage_finden(vorlagen_laden(profil), zeilen)
    abw, n = gegenpruefen(r, zeilen, v, es)
    if es["gegenpruefung"]:
        for a in abw:
            r.hinweis("pruefen", a.text(), a.feld)
        if not abw:
            r.hinweis("info", f"Gegenprüfung mit Druck {druckname} ohne Abweichung ({n} Werte)")
    if es["anlernen"] and not abw:
        v, quote = lernen(r, zeilen, profil, v, es)
        vorlage_speichern(v, profil)
        st = v["statistik"]
        q = "–" if quote is None else f"{quote:.0%}"
        r.hinweis(
            "info",
            f"PDF-Erkennung: Vorlage {v['profil']}-{v['kennung']} angelernt, Treffer {q}, "
            f"{st['folge_treffer']} von {es['nur_pdf_ab']} in Folge"
            + (
                f" (Zähler zurückgesetzt: {st['zurueckgesetzt']})"
                if quote is not None and st.get("zurueckgesetzt")
                else ""
            ),
        )


# ---------------------------------------------------------------- Offene Selbstkontrolle
# Liest eine frisch gespeicherte Vorlage ein bestätigtes Feld anders als bestätigt (``Sitzung.selbst_kontrollieren``),
# merkt sich die Vorlage das Feld unter ``kontrolle_offen`` (Feldschlüssel des Assistenten, z. B. „BT-1“, „leistung“,
# „positionen“). Bis eine spätere bestätigte PDF desselben Layouts das Feld richtig liest, ist es in jeder Sitzung
# markiert und im Nur-PDF-Pfad „prüfen“. Vorlagen ohne den Schlüssel (alle bis 0.8.0) gelten als bestätigt.
KONTROLLE_OFFEN = "kontrolle_offen"
_KONTROLLE_ZIEL = {"leistung": ("BT-72", "Leistungsdatum"), "positionen": ("BG-25", "Positionen")}


def kontrolle_offen(v: dict | None) -> list[str]:
    """Felder mit offener Selbstkontrolle (Kaputtes oder Fehlendes = keine)."""
    offen = (v or {}).get(KONTROLLE_OFFEN)
    return [f for f in offen if isinstance(f, str) and f] if isinstance(offen, list) else []


def kontrolle_setzen(v: dict, offen) -> None:
    """Offene Felder in die Vorlage schreiben (leer: Schlüssel entfernen, die Vorlage bleibt wie vor 0.9.0)."""
    offen = list(dict.fromkeys(offen))
    if offen:
        v[KONTROLLE_OFFEN] = offen
    else:
        v.pop(KONTROLLE_OFFEN, None)


def kontrolle_bestaetigen(profil: dict, kennung: str, felder=None) -> list[str]:
    """Offene Selbstkontrolle der Vorlage ``kennung`` als bestätigt austragen (alle oder nur ``felder``), z. B. nachdem
    der Nutzer einen Nur-PDF-Beleg in der Prüfansicht bestätigt hat. -> ausgetragene Felder."""
    for v in vorlagen_laden(profil):
        if v.get("kennung") != kennung:
            continue
        offen = kontrolle_offen(v)
        weg = [f for f in offen if felder is None or f in felder]
        if weg:
            kontrolle_setzen(v, [f for f in offen if f not in weg])
            vorlage_speichern(v, profil)
        return weg
    return []


def _kontrolle_hinweise(r: Rechnung, v: dict) -> None:
    for f in kontrolle_offen(v):
        feld, name = _KONTROLLE_ZIEL.get(f, (f, feldname(f)))
        r.hinweis(
            "pruefen",
            f"Selbstkontrolle offen: Die Vorlage {v['profil']}-{v['kennung']} hat {name} nach dem letzten Anlernen "
            "anders gelesen als bestätigt – bitte prüfen. Bestätigt ist es, sobald eine angelernte PDF dieses "
            "Absenders das Feld wieder richtig liest.",
            feld,
        )


# ---------------------------------------------------------------- Nur-PDF
def _herkunft(v: dict, wo: str) -> Herkunft:
    return Herkunft(f"pdf-angelernt:{v['profil']}-{v['kennung']} {wo}", 0.95)


def vorlage_suchen(zeilen: list[Zeile], profile: list[dict]) -> tuple[dict | None, dict | None]:
    """-> (Profil, Vorlage) der passenden angelernten Vorlage; sonst (Profil, None), wenn der Druck den
    Absender eines Profils trägt (USt-IdNr., IBAN oder Steuernummer), sonst (None, None)."""
    for prof in profile:
        v = vorlage_finden(vorlagen_laden(prof), zeilen)
        if v:
            return prof, v
    text = kompakt(" ".join(z.text for z in zeilen))
    for prof in profile:
        vk, zb = prof.get("verkaeufer") or {}, prof.get("zahlung") or {}
        kennungen = [
            kompakt(w) for w in (vk.get("ust_id"), vk.get("steuernummer"), zb.get("iban")) if w
        ]
        if kennungen and any(k in text for k in kennungen):
            return prof, None
    return None, None


BELEGART_FEHLT = (
    "Belegart nicht an der angelernten Stelle gefunden – als Rechnung (380) übernommen. Ist es eine "
    "Gutschrift? Bitte prüfen."
)


# ---------------------------------------------------------------- Steuer-Sonderfälle und Fremdwährung (ab 0.9.7)
_WZ = r"US\$|SFr\.|sFr\.|Fr\.|[€$£¥]|(?<![A-Za-z])[A-Z]{3}(?![A-Za-z])"
_BETRAG_MIT_WAEHRUNG = re.compile(rf"(?:({_WZ})\s?-?\d[\d.,]*\d|\d[\d.,]*\d\s?({_WZ}))")


def waehrung_im_druck(zeilen: list[Zeile]) -> tuple[str, list[str]]:
    """Währung aus Zeichen/Codes direkt an Beträgen („1.234,56 $“, „USD 980.00“). -> (Code, Fremdwährungen).
    Code ist „EUR“ ohne Fremdwährung, die Fremdwährung bei genau einer, sonst leer (mehrere: prüfen)."""
    gef: list[str] = []
    for z in zeilen:
        for m in _BETRAG_MIT_WAEHRUNG.finditer(z.text):
            t = m.group(1) or m.group(2)
            c = steuerfaelle.SYMBOLE.get(t, t)
            if c and c in steuerfaelle.WAEHRUNGEN and c not in gef:
                gef.append(c)
    fremd = [c for c in gef if c != "EUR"]
    return ("EUR" if not fremd else fremd[0] if len(fremd) == 1 else ""), fremd


def steuerhinweis_im_druck(zeilen: list[Zeile]) -> tuple[str, str] | None:
    """Erste Zeile mit einem Steuerhinweis (Reverse Charge, igL, Ausfuhr, nicht steuerbar, § 19 UStG).
    -> (Steuerfall, Text). Sehr lange Zeilen (Fließtext) -> der Standardtext des Falls."""
    for z in zeilen:
        fall = steuerfaelle.erkennen(z.text)
        if fall:
            t = " ".join(z.text.split())
            return fall, (t if len(t) <= 160 else steuerfaelle.standardtext(fall))
    return None


def steuer_kopf_ergaenzen(kopf: dict, zeilen: list[Zeile], h) -> list[tuple[str, str, str]]:
    """Nicht angelernte Angaben aus dem Druck ergänzen: Steuerhinweis, Währung, Kurs, Kursdatum, USt in EUR.
    -> Hinweise (Art, Text, Feld) für die Rechnung."""
    meld: list[tuple[str, str, str]] = []
    if "steuerhinweis" not in kopf:
        f = steuerhinweis_im_druck(zeilen)
        if f:
            kopf["steuerhinweis"] = (f[1], h)
    if "BT-5" not in kopf:
        code, fremd = waehrung_im_druck(zeilen)
        if len(fremd) > 1:
            meld.append(
                (
                    "pruefen",
                    f"Mehrere Währungen im Druck ({', '.join(fremd)}) – Rechnungswährung prüfen.",
                    "BT-5",
                )
            )
        elif code and code != "EUR":
            kopf["BT-5"] = (code, h)
    w = str(kopf.get("BT-5", ("EUR",))[0] or "EUR").upper()
    if w == "EUR":
        return meld
    if "kurs" not in kopf:
        for z in zeilen:
            if not re.search(r"kurs|exchange|\bEUR\s*=|=\s*EUR\b|EUR\s*/\s*[A-Z]{3}", z.text, re.I):
                continue
            k, fw = steuerfaelle.kurs_lesen(z.text, w)
            if k is not None and fw in (None, "", w):
                kopf["kurs"] = (z.text, h)
                if "kursdatum" not in kopf:
                    m = re.search(
                        r"(?:stand|vom|as of|per)\s*:?\s*(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2})",
                        z.text,
                        re.I,
                    )
                    d = daten(m[1]) if m else []
                    if d:
                        kopf["kursdatum"] = (d[0], h)
                break
    if "BT-111" not in kopf:
        for z in zeilen:
            m = re.search(
                r"(?:ust|umsatzsteuer|mwst|vat)\b[^0-9]{0,25}?\bin\s+(?:eur|€)\b", z.text, re.I
            )
            if not m:
                continue
            for tok in z.text[m.end() :].split():
                b = betraege(tok.strip(":()"))
                if b:
                    kopf["BT-111"] = (b[0][0], h)
                    break
            if "BT-111" in kopf:
                break
    return meld


def ust_saetze_im_druck(zeilen: list[Zeile]) -> list[str]:
    """Steuersätze > 0 aus Summenzeilen wie „zzgl. 19 % USt“ oder „MwSt 7 %“ (ohne Doppelte)."""
    out: list[str] = []
    for z in zeilen:
        if not re.search(r"ust|mwst|umsatzsteuer|mehrwertsteuer|\bvat\b", z.text, re.I):
            continue
        for m in re.finditer(r"(?<![\d,.])(\d{1,2}(?:[.,]\d{1,2})?)\s*%", z.text):
            satz = m[1].replace(",", ".")
            if Decimal(satz) > 0 and satz not in out:
                out.append(satz)
    return out


def steuer_fest_aus_druck(mapping: dict, kopf: dict, zeilen: list[Zeile]) -> None:
    """Steuerfall je Rechnung („fall: hinweis“) ohne gelernten Satz: Steht kein Steuerhinweis im Druck, gilt der
    eine Steuersatz aus den Summenzeilen (Regelbesteuerung). Mehrere oder keiner -> bleibt offen (prüfen)."""
    fest = mapping.get("*")
    if not (isinstance(fest, dict) and fest.get("fall") == "hinweis" and "BT-152" not in fest):
        return
    if steuerfaelle.erkennen(str((kopf.get("steuerhinweis") or ("",))[0] or "")):
        return
    saetze = ust_saetze_im_druck(zeilen)
    if len(saetze) == 1:
        mapping["*"] = {**fest, "BT-151": "S", "BT-152": saetze[0]}


def steuerfall_abgleichen(r: Rechnung, hinweis: str) -> None:
    """Steuerfall der Positionen gegen den Hinweis im Druck: Widerspruch oder fehlender Pflichthinweis
    (§ 14a UStG, § 19 UStG) -> prüfen. Mehrere Fälle im Hinweis zählen als „passt“, wenn einer passt."""
    druck = steuerfaelle.alle_erkennen(hinweis)
    faelle = {steuerfaelle.fall_von(p.steuer) for p in r.positionen} - {None}
    sonder = faelle & set(steuerfaelle.FAELLE)
    mit_ust = any(p.steuer.kategorie == "S" and p.steuer.satz > 0 for p in r.positionen)
    if druck and mit_ust and not sonder:
        r.hinweis(
            "pruefen",
            (
                f"Der Druck nennt „{steuerfaelle.FAELLE[druck[0]].name}“, die Vorlage rechnet aber "
                "mit Umsatzsteuer – Steuerfall der Vorlage prüfen (Anlernen)."
            ),
            "BT-151",
        )
        return
    for f in sorted(sonder):
        if not druck:
            r.hinweis(
                "pruefen",
                (
                    f"Die Vorlage rechnet mit „{steuerfaelle.FAELLE[f].name}“, im Druck steht aber kein "
                    "passender Hinweis – Pflichtangabe auf der Rechnung prüfen."
                ),
                "steuerhinweis",
            )
        elif f not in druck:
            r.hinweis(
                "pruefen",
                (
                    f"Die Vorlage rechnet mit „{steuerfaelle.FAELLE[f].name}“, der Druck nennt "
                    f"„{steuerfaelle.FAELLE[druck[0]].name}“ – Steuerfall prüfen."
                ),
                "BT-151",
            )


def nur_pdf(
    pfad: Path, zeilen: list[Zeile], profile: list[dict], konfig
) -> tuple[Rechnung | None, str]:
    """PDF ohne CSV: nur mit sicherer angelernter Vorlage und eingeschaltetem Nur-PDF-Modus.
    -> (Rechnung, "") oder (None, Grund)."""
    beste = None
    for prof in profile:
        v = vorlage_finden(vorlagen_laden(prof), zeilen)
        if v:
            beste = beste or (prof, v)
            if sicher(v, einstellungen(prof)) and einstellungen(prof)["nur_pdf"]:
                beste = (prof, v)
                break
    if not beste:
        return None, "Kein CSV-Export zu diesem PDF gefunden und keine angelernte Vorlage passt"
    prof, v = beste
    es = einstellungen(prof)
    if not es["nur_pdf"]:
        return None, (
            f"Kein CSV-Export zu diesem PDF gefunden; „Automatisch, ohne Nachfrage“ ist im Profil "
            f"{v['profil']} ausgeschaltet"
        )
    if not sicher(v, es):
        return None, (
            f"Kein CSV-Export zu diesem PDF gefunden; Vorlage {v['profil']}-{v['kennung']} noch nicht sicher "
            f"({v['statistik'].get('folge_treffer', 0)} von {es['nur_pdf_ab']} Rechnungen in Folge)"
        )
    kopf: dict = {}
    brueche: dict[str, str] = {}
    bezug = None
    for f, regel in v["felder"].items():
        if f == ANSCHRIFT_BLOCK:
            block = vorlage_anschrift_lesen(v, regel, zeilen, brueche)
            ausland = block.get("BT-55", ("DE",))[0] not in ("", "DE")
            for bf, (t, ws) in block.items():
                if bf in _TYP_JE_FELD and not wert_passt(bf, t, ausland):
                    log.info("Nur-PDF: %s passt nicht zum Feldtyp – nicht übernommen", feldname(bf))
                    continue
                kopf[bf] = (t, _herkunft(v, f"S.{ws[0].seite + 1}" if ws else "Block"))
            continue
        if f in BLOCKFELDER and ANSCHRIFT_BLOCK in v["felder"]:
            continue  # Block gilt; alte Einzelregel daneben nicht
        erg = vorlage_feld_lesen(v, f, regel, zeilen)
        if not erg or (f in OPTIONALE_NUMMERN and not nummer_passt(erg[0])):
            continue  # optionales Feld: lieber leer als ein Datum o. Ä.
        w = lesen_als(regel["typ"], erg[0])
        if w is None or (f in _TYP_JE_FELD and not wert_passt(f, erg[0])):
            if w is not None:
                log.info("Nur-PDF: %s passt nicht zum Feldtyp – nicht übernommen", feldname(f))
            continue
        h = _herkunft(v, f"S.{erg[1][0].seite + 1}")
        if f == "BG-14":
            kopf["BT-73"], kopf["BT-74"] = (w[0], h), (w[1], h)
        elif f == "BT-3":
            kopf["BT-3"] = (belegart_code(w), h)
        elif f == "BT-25":
            bezug = (bezug_zerlegen(w), h)
        elif (
            f
            in (
                "BT-1",
                "BT-2",
                "BT-72",
                "BT-13",
                "BT-20",
                "kundennummer",
                "BT-109",
                "BT-110",
                "BT-112",
                *NUR_PDF_ZUSATZ,
            )
            or f in KAEUFER_FELDER
        ):
            kopf[f] = (w, h)
    if bezug and kopf.get("BT-3", ("380",))[0] == "381":  # BG-3 nur bei Gutschrift
        (nummer, datum), h = bezug
        kopf["BT-25"] = (nummer, h)
        if datum:
            kopf["BT-26"] = (datum, h)
    elif bezug:
        log.info("Nur-PDF: Bezugsrechnung gelesen, Beleg ist keine Gutschrift – nicht übernommen")
    bt20_ersatz = None
    if "BT-20" in v["felder"] and "BT-20" not in kopf:
        # angelernt, aber an der Stelle nichts Passendes: Zahlungsbaustein aus dem Druck (zur Prüfung), sonst leer –
        # kein Profiltext statt dessen
        baustein = zahlungsbaustein(zeilen)
        bt20_ersatz = zahlungsbaustein_text(baustein[1]) if baustein else None
        kopf["BT-20"] = (
            bt20_ersatz or "",
            _herkunft(v, f"S.{baustein[0] + 1}" if baustein else "Vorlage"),
        )
    bt20_druck = None
    if "BT-20" not in v["felder"] and "BT-20" not in kopf:
        # Vorlage ohne Stelle für BT-20: steht ein Zahlungsbaustein im Druck, gilt er statt des Profiltexts
        baustein = zahlungsbaustein(zeilen)
        bt20_druck = zahlungsbaustein_text(baustein[1]) if baustein else None
        if bt20_druck and _wie_profiltext(bt20_druck, prof, konfig):
            bt20_druck = None  # Druck nennt den Profiltext: der bleibt, ohne Hinweis
        if bt20_druck:
            kopf["BT-20"] = (bt20_druck, _herkunft(v, f"S.{baustein[0] + 1}"))
    steuer_meld = steuer_kopf_ergaenzen(kopf, zeilen, _herkunft(v, "Druck"))
    pv = v["positionen"]
    pos = []
    gelesen_pos = positionen_auslesen(pv, zeilen)
    schiedsrichter = summen_schiedsrichter(
        kopf, gelesen_pos, pv, zeilen, _herkunft(v, "Summenzeile")
    )
    for i, p in enumerate(gelesen_pos, 1):
        h = _herkunft(v, "Tabelle")
        roh = {
            "BT-153": (p.bezeichnung, h),
            "BT-129": (p.menge, h),
            "BT-146": (p.einzelpreis, h),
            "gesamtpreis_position": (p.gesamt, h),
            "steuer": (p.steuer_text if "steuer" in pv else "*", h),
        }
        if p.nr:
            roh["BT-126"] = (p.nr, h)
        if p.artikelnummer:
            roh["BT-155"] = (p.artikelnummer, h)
        if pos_preiseinheit(pv, p) != 1:
            roh["BT-149"] = (pos_preiseinheit(pv, p), h)
        roh["BT-130"] = (einheit_schluessel(pv, p), h)
        pos.append(roh)
    definition = copy.deepcopy(prof)
    definition["mappings"] = {
        "einheiten": einheiten_mapping(pv, [roh["BT-130"][0] for roh in pos]),
        "steuer": steuer_zuordnung(pv),
    }
    steuer_fest_aus_druck(definition["mappings"]["steuer"], kopf, zeilen)
    # BT-56/BT-163 (Kontaktstelle, Adresszeile 3) laufen über KAEUFER_FELDER
    r = rechnung_bauen(kopf, pos, definition, konfig, quelle=str(pfad))
    zahlungsziel.profiltext_sperren(r, " ".join(z.text for z in zeilen))
    for art, text, feld in steuer_meld:
        r.hinweis(art, text, feld)
    steuerfall_abgleichen(r, r.steuerhinweis)
    if bt20_ersatz:
        r.hinweis(
            "pruefen",
            f"Zahlungsbedingung nicht an der angelernten Stelle – aus dem Druck übernommen: "
            f"„{bt20_ersatz}“. Bitte prüfen.",
            "BT-20",
        )
    if bt20_druck:
        r.hinweis(
            "pruefen",
            f"Zahlungsbedingung aus dem Druck übernommen (in der Vorlage nicht angelernt): "
            f"„{bt20_druck}“. Bitte prüfen.",
            "BT-20",
        )
    if schiedsrichter:
        r.hinweis(*schiedsrichter)
    for bf, text in brueche.items():
        r.hinweis("pruefen", "Anschrift: " + text.split(": ", 1)[-1], bf)
    if "BT-3" in v["felder"] and "BT-3" not in kopf:
        r.hinweis("pruefen", BELEGART_FEHLT, "BT-3")
    r.profil = profil_name(prof)
    r.sicht_pdf = (str(pfad), sorted({z.seite for z in zeilen}))
    _kontrolle_hinweise(r, v)
    r.hinweis(
        "info",
        f"Automatisch (Nur PDF): gelesen mit Vorlage {v['profil']}-{v['kennung']} "
        f"(Trefferquote {trefferquote(v) or 0:.0%}, {v['statistik'].get('folge_treffer', 0)} in Folge)",
    )
    return r, ""


def _wie_profiltext(druck: str, prof: dict, konfig) -> bool:
    """Steht der Profiltext (Zahlungsbedingung des Profils) wörtlich im Zahlungsbaustein des Drucks?"""
    from .konfig import zahlung_aus

    z = zahlung_aus(prof.get("zahlung") or {}, getattr(konfig, "zahlung", None))
    profiltext = z.bedingungen.replace("{zahlungsziel_tage}", str(z.ziel_tage or ""))
    return bool(profiltext.strip()) and norm(profiltext) in norm(druck)


def _pos_summe(ps: list[PosRoh], pv: dict) -> Decimal | None:
    if not ps:
        return None
    return sum(
        (rechnen.positionsbetrag(p.menge, p.einzelpreis, pos_preiseinheit(pv, p)) for p in ps),
        Decimal("0"),
    )


def summen_schiedsrichter(
    kopf: dict, ps: list[PosRoh], pv: dict, zeilen: list[Zeile], h
) -> tuple | None:
    """Nur-PDF: gelesene Summen gegen die Positionen prüfen; geht eine andere Lesart aus den Summenzeilen auf,
    gewinnt sie (``kopf`` wird angepasst). -> Hinweis (Art, Text, Feld) oder None."""
    gelesen = {f: (kopf[f][0] if f in kopf else None) for f in ("BT-109", "BT-110", "BT-112")}
    if gelesen["BT-109"] is None and gelesen["BT-112"] is None:
        return None
    kand = [b for b, _ in summenblock(pv, zeilen)]
    neu, art = summen_lesart(_pos_summe(ps, pv), gelesen, kand)
    if art != "gewählt":
        return None  # „ok“ – oder geht nicht auf: rechnen.berechnen meldet „prüfen“
    for f, w in neu.items():
        if w is not None and w != gelesen[f]:
            log.info("Nur-PDF: %s rechnerisch gewählt: %s statt %s", feldname(f), w, gelesen[f])
            kopf[f] = (w, h)
    return (
        "info",
        "Summen rechnerisch gewählt (Summe Positionen = Netto, Netto + USt = Brutto)",
        "BT-109",
    )


def summen_pruefen(r: Rechnung) -> None:
    """Nur-PDF: Die Summe der Positionen muss die gedruckten Summen ergeben. Den Vergleich selbst macht
    rechnen.berechnen über ``r.kontrolle`` (BT-109/110/112); hier nur: gibt es überhaupt Kontrollwerte?"""
    if not ({"BT-109", "BT-112"} & set(r.kontrolle)):
        r.hinweis(
            "pruefen",
            "Summenprüfung nicht möglich: keine gedruckte Netto- oder Bruttosumme erkannt",
            "BT-112",
        )
    if not r.positionen:
        r.hinweis(
            "pruefen", "Summenprüfung nicht möglich: keine Positionen im Druck erkannt", "BG-25"
        )
    for text in zahlungsziel.skonto_hinweise(
        zahlungsziel.lesen(r.zahlung.bedingungen), r.summen.brutto
    ):
        r.hinweis(
            "info", text, "BT-20"
        )  # Hinweis, kein Fehler: der Text geht so ins XML wie gedruckt
    einheit_in_klammern_pruefen(r)


_EINHEIT_KLAMMER = re.compile(r"\(([^()]{1,12})\)")


def einheit_in_klammern_pruefen(r: Rechnung) -> None:
    """Position mit „Stück“ (H87), deren Bezeichnung eine andere Einheit in Klammern nennt
    („Regalberatung (Stunden)“): Die Einheit ist wohl nur in der Bezeichnung gedruckt – prüfen statt still H87."""
    for i, p in enumerate(r.positionen, 1):
        if p.einheit != "H87":
            continue
        for m in _EINHEIT_KLAMMER.finditer(p.bezeichnung or ""):
            code = einheit_code(m[1].strip(" .,;:"))
            if code and code != "H87":
                r.hinweis(
                    "pruefen",
                    f"Position {i}: Einheit „Stück“, die Bezeichnung nennt aber „{m[1]}“ – bitte Einheit "
                    "prüfen",
                    "BT-130",
                )
                break
