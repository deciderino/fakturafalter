# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Zahlen, Daten, Kodierungen lesen."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class WertFehler(ValueError):
    pass


# Steuerzeichen (Code 0–31, z. B. ein Zeilenumbruch 0x0A im Textstring einer PDF), denen die Schrift kein
# Unicode-Zeichen zuordnet, gibt pdfminer als Platzhalter „(cid:10)“ aus – angeklebt an das Wort davor.
# Unsichtbar im Druck, gehören nie zum Wert. Groß/klein egal: im Assistenten wurde IBAN/USt-IdNr. großgeschrieben.
_CID_STEUER = re.compile(r"\(cid:(?:[0-9]|[12][0-9]|3[01])\)", re.IGNORECASE)


def ohne_steuerzeichen(text: str) -> str:
    return _CID_STEUER.sub("", text)


_STEUER = re.compile(r"[\x00-\x1f\x7f]+")
_STEUER_MEHRZEILIG = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]+")  # Zeilenumbruch bleibt


def bereinigt(text: str, mehrzeilig: bool = False) -> str:
    """Gespeicherter Wert ohne „(cid:10)“-Platzhalter und ohne echte Steuerzeichen (-> Leerzeichen).

    ``mehrzeilig``: Zeilenumbrüche bleiben (z. B. Zahlungsbedingung)."""
    t = (_STEUER_MEHRZEILIG if mehrzeilig else _STEUER).sub(" ", ohne_steuerzeichen(text))
    return re.sub(r" {2,}", " ", t).strip() if t != text else text


def bloecke_bereinigen(d: dict, schluessel=("verkaeufer", "zahlung", "absender")) -> list[str]:
    """Strings in den genannten Blöcken von ``d`` bereinigen (verschachtelt); -> geänderte Pfade."""
    geaendert: list[str] = []

    def rein(x, pfad):
        if isinstance(x, str):
            neu = bereinigt(x, mehrzeilig="bedingung" in pfad or "text" in pfad)
            if neu != x:
                geaendert.append(pfad)
            return neu
        if isinstance(x, dict):
            for k2 in list(x):
                x[k2] = rein(x[k2], f"{pfad}.{k2}")
            return x
        if isinstance(x, list):
            return [rein(v, f"{pfad}[{i}]") for i, v in enumerate(x)]
        return x

    for s in schluessel:
        if isinstance(d.get(s), dict):
            rein(d[s], s)
    return geaendert


def zahl(text: str, dezimal: str = ",", tausender: str = ".", implizit: int = 0) -> Decimal:
    t = (text or "").strip().replace("\u00a0", "").replace(" ", "")
    if not t:
        raise WertFehler("leere Zahl")
    neg = False
    if t.endswith("-"):
        neg, t = True, t[:-1]
    if tausender:
        t = t.replace(tausender, "")
    if dezimal and dezimal != ".":
        t = t.replace(dezimal, ".")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", t):
        raise WertFehler(f"keine Zahl: {text!r}")
    try:
        d = Decimal(t)
    except InvalidOperation as e:  # pragma: no cover
        raise WertFehler(f"keine Zahl: {text!r}") from e
    if implizit:
        d = d.scaleb(-implizit)
    return -d if neg else d


def datum(text: str, fmt: str = "%d.%m.%Y") -> date:
    t = (text or "").strip()
    try:
        return datetime.strptime(t, fmt).date()
    except ValueError as e:
        raise WertFehler(f"kein Datum ({fmt}): {text!r}") from e


def dekodieren(raw: bytes, kodierung: str = "auto") -> tuple[str, str]:
    """Bytes -> Text. ``auto``: BOM/UTF-8 strikt, sonst Windows-1252."""
    if kodierung and kodierung != "auto":
        return raw.decode(kodierung), kodierung
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


def trennzeichen_erkennen(text: str) -> str:
    erste = text.splitlines()[0] if text else ""
    try:
        return csv.Sniffer().sniff(erste, delimiters=";,\t|").delimiter
    except csv.Error:
        return max(";,\t|", key=erste.count)


def csv_lesen(text: str, trenn: str, quote: str = '"') -> list[list[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=trenn, quotechar=quote or '"'))
