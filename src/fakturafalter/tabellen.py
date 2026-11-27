# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Excel (.xlsx) und LibreOffice/OpenDocument (.ods) als Eingabe (ab 1.0.0-rc2).

Ein Tabellenblatt wird in denselben Text verwandelt, den eine CSV-Datei liefern würde (Trennzeichen „;“).
Danach laufen Assistent, Profil, BT-Kopf-Erkennung, Blöcke und Prüfungen unverändert wie bei einer CSV.

- Zahlen werden nie als float weitergegeben: Excel speichert Zahlen als Gleitkomma; der Wert wird über die
  kürzeste Darstellung in ``Decimal`` übernommen und auf 15 signifikante Stellen gerundet (wie Excel rechnet),
  damit z. B. 0,30000000000000004 als 0,3 ankommt. ODS liefert den Wert als Text (``office:value``).
- Zahlen schreibt Fakturafalter mit dem Dezimalzeichen des Profils und ohne Tausenderpunkt; Datumszellen im
  Datumsformat des Profils. Text-Zellen bleiben, wie sie sind.
- Prozentzellen (19 % = 0,19) kommen als „19 %“.
- Formeln: verwendet wird der zuletzt gespeicherte Wert. Ohne gespeicherten Wert bleibt die Zelle leer.
- Alles offline und nur lesend; die Datei wird nicht verändert.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path

ENDUNGEN = {".xlsx", ".ods"}
TRENNZEICHEN = ";"
MAX_ZEILEN = 200_000  # Schutz vor „1 048 576 leere Zeilen“ in ODS
MAX_SPALTEN = 1_000


class TabellenFehler(ValueError):
    """Klartext-Fehler beim Lesen einer Tabelle (Blatt fehlt, Datei kaputt, verschlüsselt …)."""


def ist_tabelle(pfad: Path | str) -> bool:
    return Path(pfad).suffix.lower() in ENDUNGEN


@dataclass
class Zelle:
    """Wert einer Zelle: Text, Decimal (Zahl), Prozent (Decimal mit ``prozent``), date/datetime oder None."""

    wert: object = None
    prozent: bool = False


@dataclass
class Tabelle:
    blaetter: list[str] = field(default_factory=list)
    blatt: str = ""
    zeilen: list[list[Zelle]] = field(default_factory=list)  # ab Zeile 1 des Blatts, ohne Kürzung


# ---------------------------------------------------------------------------------------------- Zahlen
def zahl_aus_float(f: float) -> Decimal:
    """float aus Excel -> Decimal ohne Gleitkomma-Rauschen (15 signifikante Stellen, wie Excel)."""
    d = Decimal(repr(float(f)))
    if not d.is_finite():
        raise TabellenFehler(f"Zahl nicht darstellbar: {f!r}")
    if d == 0:
        return Decimal(0)
    stellen = d.adjusted()  # Exponent der ersten Ziffer
    d = d.quantize(Decimal(1).scaleb(stellen - 14), rounding=ROUND_HALF_EVEN)
    return _ohne_nullen(d)


def _ohne_nullen(d: Decimal) -> Decimal:
    d = d.normalize()
    if d.as_tuple().exponent > 0:  # 1E+2 -> 100
        d = d.quantize(Decimal(1))
    return d


def zahl_text(d: Decimal, dezimal: str = ",") -> str:
    """Decimal -> „1234,5“ bzw. „1234.5“ (ohne Tausenderzeichen, ohne Exponent)."""
    t = format(_ohne_nullen(d), "f")
    return t.replace(".", dezimal) if dezimal != "." else t


# ---------------------------------------------------------------------------------------------- Lesen
def blaetter(pfad: Path) -> list[str]:
    return lesen(pfad, nur_namen=True).blaetter


def lesen(pfad: Path, blatt: str | None = None, nur_namen: bool = False) -> Tabelle:
    pfad = Path(pfad)
    suf = pfad.suffix.lower()
    try:
        if suf == ".xlsx":
            return _xlsx(pfad, blatt, nur_namen)
        if suf == ".ods":
            return _ods(pfad, blatt, nur_namen)
    except TabellenFehler:
        raise
    except zipfile.BadZipFile as e:
        raise TabellenFehler(
            f"{pfad.name} ist keine lesbare {suf[1:].upper()}-Datei (beschädigt oder mit Passwort geschützt)"
        ) from e
    except (OSError, KeyError, ValueError) as e:
        raise TabellenFehler(f"{pfad.name} lässt sich nicht lesen ({type(e).__name__}: {e})") from e
    raise TabellenFehler(f"Dateityp {suf} ist keine Tabelle")


def _blatt_waehlen(namen: list[str], blatt: str | None, standard: str, pfad: Path) -> str:
    if not namen:
        raise TabellenFehler(f"{pfad.name} enthält kein Tabellenblatt")
    if blatt:
        if blatt in namen:
            return blatt
        raise TabellenFehler(
            f"Tabellenblatt „{blatt}“ fehlt in {pfad.name} (vorhanden: {', '.join(namen)})"
        )
    return standard if standard in namen else namen[0]


def _xlsx(pfad: Path, blatt: str | None, nur_namen: bool) -> Tabelle:
    import warnings

    import openpyxl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # z. B. „Data Validation extension is not supported“
        wb = openpyxl.load_workbook(pfad, read_only=True, data_only=True)
    try:
        namen = list(wb.sheetnames)
        sichtbar = [ws.title for ws in wb.worksheets if getattr(ws, "sheet_state", "visible") == "visible"]
        try:
            aktiv = wb.active.title if wb.active is not None else ""
        except (IndexError, AttributeError):
            aktiv = ""
        standard = aktiv if aktiv in sichtbar else (sichtbar[0] if sichtbar else (namen[0] if namen else ""))
        t = Tabelle(blaetter=namen)
        if nur_namen:
            t.blatt = standard
            return t
        t.blatt = _blatt_waehlen(namen, blatt, standard, pfad)
        ws = wb[t.blatt]
        if hasattr(ws, "reset_dimensions"):
            ws.reset_dimensions()  # falsche <dimension> mancher Exporte würde Zeilen abschneiden
        for i, row in enumerate(ws.iter_rows()):
            if i >= MAX_ZEILEN:
                break
            zeile: list[Zelle] = []
            for c in row[:MAX_SPALTEN]:
                zeile.append(_xlsx_zelle(c))
            t.zeilen.append(zeile)
        return t
    finally:
        wb.close()


def _xlsx_zelle(c) -> Zelle:
    v = getattr(c, "value", None)
    if v is None:
        return Zelle()
    if isinstance(v, bool):
        return Zelle("1" if v else "0")
    fmt = str(getattr(c, "number_format", "") or "")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        d = Decimal(v) if isinstance(v, int) else zahl_aus_float(v)
        if "%" in fmt.replace('"%"', "").replace("\\%", ""):
            return Zelle(_ohne_nullen(d * 100), prozent=True)
        return Zelle(d)
    if isinstance(v, (datetime, date, time)):
        return Zelle(v)
    if isinstance(v, Decimal):
        return Zelle(v)
    return Zelle(str(v))


# ODS (OpenDocument): content.xml direkt mit lxml lesen – keine weitere Abhängigkeit
_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


def _q(ns: str, name: str) -> str:
    return f"{{{_NS[ns]}}}{name}"


def _ods(pfad: Path, blatt: str | None, nur_namen: bool) -> Tabelle:
    from lxml import etree

    with zipfile.ZipFile(pfad) as z:
        if "content.xml" not in z.namelist():
            raise TabellenFehler(f"{pfad.name}: content.xml fehlt (keine ODS-Datei?)")
        if "META-INF/manifest.xml" in z.namelist():
            man = z.read("META-INF/manifest.xml")
            if b"encryption-data" in man:
                raise TabellenFehler(f"{pfad.name} ist mit einem Passwort geschützt")
        daten = z.read("content.xml")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)
    wurzel = etree.fromstring(daten, parser)
    tabellen = wurzel.findall(f".//{_q('office', 'spreadsheet')}/{_q('table', 'table')}")
    namen = [tb.get(_q("table", "name")) or f"Tabelle{i + 1}" for i, tb in enumerate(tabellen)]
    t = Tabelle(blaetter=namen)
    standard = namen[0] if namen else ""
    if nur_namen:
        t.blatt = standard
        return t
    t.blatt = _blatt_waehlen(namen, blatt, standard, pfad)
    tb = tabellen[namen.index(t.blatt)]
    leer_offen = 0
    for row in tb.iter(_q("table", "table-row")):
        wdh = int(row.get(_q("table", "number-rows-repeated"), "1") or 1)
        zeile: list[Zelle] = []
        for zelle in row:
            if zelle.tag not in (_q("table", "table-cell"), _q("table", "covered-table-cell")):
                continue
            n = int(zelle.get(_q("table", "number-columns-repeated"), "1") or 1)
            z = _ods_zelle(zelle)
            if z.wert is None and n > 1:
                n = min(n, max(0, MAX_SPALTEN - len(zeile)))
            zeile.extend(Zelle(z.wert, z.prozent) for _ in range(min(n, MAX_SPALTEN - len(zeile))))
        if all(z.wert in (None, "") for z in zeile):
            leer_offen += wdh  # erst übernehmen, wenn danach noch Daten kommen (Zeilennummern bleiben stimmig)
            continue
        if len(t.zeilen) + leer_offen + wdh > MAX_ZEILEN:
            raise TabellenFehler(f"{pfad.name}: Blatt „{t.blatt}“ hat mehr als {MAX_ZEILEN} Zeilen")
        t.zeilen.extend([] for _ in range(leer_offen))
        leer_offen = 0
        for _ in range(wdh):
            t.zeilen.append(list(zeile))
    return t


def _ods_text(el) -> str:
    teile: list[str] = []

    def lauf(e) -> None:
        if e.text:
            teile.append(e.text)
        for k in e:
            if k.tag == _q("text", "s"):
                teile.append(" " * int(k.get(_q("text", "c"), "1") or 1))
            elif k.tag == _q("text", "tab"):
                teile.append("\t")
            elif k.tag == _q("text", "line-break"):
                teile.append("\n")
            else:
                lauf(k)
            if k.tail:
                teile.append(k.tail)

    lauf(el)
    return "".join(teile)


def _ods_zelle(zelle) -> Zelle:
    typ = zelle.get(_q("office", "value-type"))
    if typ in ("float", "currency", "percentage"):
        roh = zelle.get(_q("office", "value"))
        try:
            d = Decimal(str(roh).strip())
        except (InvalidOperation, TypeError):
            return Zelle(_absatz_text(zelle))
        if typ == "percentage":
            return Zelle(_ohne_nullen(d * 100), prozent=True)
        return Zelle(_ohne_nullen(d) if d != 0 else Decimal(0))
    if typ == "date":
        roh = (zelle.get(_q("office", "date-value")) or "").strip()
        try:
            if "T" in roh:
                return Zelle(datetime.fromisoformat(roh))
            return Zelle(date.fromisoformat(roh))
        except ValueError:
            return Zelle(_absatz_text(zelle))
    if typ == "boolean":
        return Zelle("1" if (zelle.get(_q("office", "boolean-value")) or "").lower() == "true" else "0")
    text = _absatz_text(zelle)
    return Zelle(text if text != "" else None)


def _absatz_text(zelle) -> str:
    absaetze = zelle.findall(_q("text", "p"))
    return "\n".join(_ods_text(p) for p in absaetze)


# ---------------------------------------------------------------------------------------------- als CSV
def zelle_text(z: Zelle, dezimal: str = ",", datum: str = "%d.%m.%Y") -> str:
    v = z.wert
    if v is None:
        return ""
    if isinstance(v, Decimal):
        t = zahl_text(v, dezimal)
        return f"{t} %" if z.prozent else t
    if isinstance(v, datetime):
        if v.time() == time(0, 0):
            return v.strftime(datum)
        return f"{v.strftime(datum)} {v:%H:%M}"
    if isinstance(v, date):
        return v.strftime(datum)
    if isinstance(v, time):
        return v.strftime("%H:%M")
    return str(v)


def zeilen_als_text(
    t: Tabelle, startzeile: int = 1, dezimal: str = ",", datum: str = "%d.%m.%Y"
) -> list[list[str]]:
    """Zeilen ab ``startzeile`` (1 = erste Zeile des Blatts) als Texte, rechts leere Spalten gekürzt,
    am Ende leere Zeilen entfernt."""
    aus: list[list[str]] = []
    for z in t.zeilen[max(int(startzeile or 1), 1) - 1 :]:
        werte = [zelle_text(c, dezimal, datum) for c in z]
        while werte and werte[-1] == "":
            werte.pop()
        aus.append(werte)
    while aus and not any(aus[-1]):
        aus.pop()
    return aus


def als_csv_text(
    pfad: Path,
    blatt: str | None = None,
    startzeile: int = 1,
    dezimal: str | None = ",",
    datum: str | None = "%d.%m.%Y",
) -> str:
    """Tabellenblatt als CSV-Text (Trennzeichen „;“, Textbegrenzer „"“). ``dezimal``/``datum`` aus dem Profil;
    ``None`` = erkennen (für den Assistenten)."""
    t = lesen(pfad, blatt)
    if dezimal is None or datum is None:
        d2, f2 = erkennen(t, startzeile)
        dezimal = dezimal or d2
        datum = datum or f2
    zeilen = zeilen_als_text(t, startzeile, dezimal, datum)
    breite = max((len(z) for z in zeilen), default=0)
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=TRENNZEICHEN, quotechar='"', lineterminator="\n")
    for z in zeilen:
        w.writerow(z + [""] * (breite - len(z)))
    return puffer.getvalue()


def erkennen(t: Tabelle, startzeile: int = 1) -> tuple[str, str]:
    """Dezimalzeichen und Datumsformat für die Ausgabe vorschlagen: wie die Text-Zellen der Datei
    (z. B. „12,50“ als Text), sonst deutsches Format (Komma, TT.MM.JJJJ)."""
    import re

    komma = punkt = 0
    datum_treffer = {"%d.%m.%Y": 0, "%Y-%m-%d": 0, "%d/%m/%Y": 0}
    for z in t.zeilen[max(int(startzeile or 1), 1) - 1 :]:
        for c in z:
            if not isinstance(c.wert, str):
                continue
            w = c.wert.strip()
            if re.fullmatch(r"-?\d{1,3}(\.\d{3})*,\d+|-?\d+,\d+", w):
                komma += 1
            elif re.fullmatch(r"-?\d{1,3}(,\d{3})*\.\d+|-?\d+\.\d+", w) and not re.fullmatch(
                r"\d{1,2}\.\d{1,2}\.\d{2,4}", w
            ):
                punkt += 1
            for f in datum_treffer:
                try:
                    datetime.strptime(w, f)
                    datum_treffer[f] += 1
                except ValueError:
                    pass
    dez = "." if punkt > komma else ","
    datum = max(datum_treffer, key=lambda f: datum_treffer[f]) if any(datum_treffer.values()) else "%d.%m.%Y"
    return dez, datum


def startzeile_vorschlagen(t: Tabelle) -> int:
    """Erste Zeile, die wie eine Kopfzeile aussieht: mindestens zwei belegte Zellen und so breit wie die
    meisten folgenden Zeilen (überspringt Titel wie „Rechnungsexport November“)."""
    belegt = [sum(1 for c in z if c.wert not in (None, "")) for z in t.zeilen[:200]]
    if not belegt:
        return 1
    ziel = max(belegt)
    for i, n in enumerate(belegt):
        if n >= 2 and n >= ziel * 0.6:
            return i + 1
    for i, n in enumerate(belegt):
        if n:
            return i + 1
    return 1
