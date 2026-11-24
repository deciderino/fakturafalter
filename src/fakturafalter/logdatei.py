# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Rotierende, ausführliche Logdatei (alles Technische: Feldquellen, Konfidenz, Dateiwege …).

Die Oberfläche zeigt nur das Nötigste; Details stehen hier. Größe begrenzt: 1 MB × 5 Dateien.
"""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

NAME = "fakturafalter.log"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_handler: RotatingFileHandler | None = None
NUR_DATEI = {"nur_datei": True}          # extra=NUR_DATEI: nur in die Logdatei, nicht auf die Konsole


class _OhneNurDatei(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "nur_datei", False)


# ---------------------------------------------------------------- Anonymisierung (Einstellung „Logs anonymisieren“)
_FIRMA = r"(?:GmbH(?:\s&\sCo\.\s?KG)?|mbH|AG|KGaA|KG|OHG|GbR|UG|e\.\s?K\.|e\.\s?V\.|eG|PartG|Ltd\.?|Inc\.?|S\.A\.|B\.V\.)"
MUSTER: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(Kunde|Käufer|Verkäufer|Absender|Empfänger|Kontakt|Kontoinhaber):\s*[^·\n;]+"), r"\1: [Name]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[E-Mail]"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b"), "[IBAN]"),
    (re.compile(r"\b(?:ATU\d{8}|DE\d{9}|[A-Z]{2}\d{8,12})\b"), "[USt-IdNr.]"),
    (re.compile(r"(?:[A-ZÄÖÜ0-9][\w&.'-]*\s){1,6}" + _FIRMA + r"(?!\w)"), "[Name]"),
    (re.compile(r"\b[A-ZÄÖÜ][\wäöüß.-]*(?:straße|strasse|str\.|weg|gasse|allee|platz|ring|damm|ufer|chaussee|"
                r"steig|pfad)\s*\d+\s?[a-zA-Z]?(?![\w])", re.I), "[Straße]"),
    (re.compile(r"\b(?:Postfach|PF)\s*\d[\d\s]*\d\b", re.I), "[Postfach]"),
    (re.compile(r"\b\d{5}\s+[A-ZÄÖÜ][\wäöüß.-]+(?:\s(?:an\s(?:der|dem)\s|am\s|im\s|bei\s)?[A-ZÄÖÜ][\wäöüß.-]+)?"),
     "[PLZ Ort]"),
    (re.compile(r"(?<![\w.,])[-+]?\d{1,3}(?:[.\s]\d{3})*,\d{2}(?![\d,])(?:\s?(?:€|EUR))?"), "[Betrag]"),
    (re.compile(r"(?<![\w.,])[-+]?\d+\.\d{2}(?![\d.])(?:\s?(?:€|EUR))?"), "[Betrag]"),
]
_NUR_FORM = re.compile(r"^[aA9\W_]*$")      # Diagnose-Form der Erkennung (a/A/9) bleibt unverändert


def anonymisieren(text: str, namen: set[str] | frozenset[str] = frozenset()) -> str:
    """Namen, Anschriften, IBAN, USt-IdNr., E-Mail und Beträge maskieren. Wortformen aus der Diagnose
    (nur a/A/9 und Satzzeichen, z. B. „Aaaa 99,99“) bleiben, wie sie sind."""
    for n in sorted(namen, key=len, reverse=True):
        if len(n) >= 3:
            text = text.replace(n, "[Name]")

    def ersetzen(ersatz):
        return lambda m: m.group(0) if _NUR_FORM.match(m.group(0)) else m.expand(ersatz)
    for rx, ersatz in MUSTER:
        text = rx.sub(ersetzen(ersatz), text)
    return text


class Anonymisierer(logging.Filter):
    """Filter für alle Log-Ausgaben (Datei, Konsole, Protokoll-Ansicht). Aus: lässt alles durch."""

    def __init__(self):
        super().__init__()
        self.an = False
        self.namen: set[str] = set()

    def merken(self, *texte: str) -> None:
        """Bekannte vertrauliche Texte (z. B. Käufername, Straße) zusätzlich wörtlich maskieren."""
        if not self.an:
            return
        for t in texte:
            t = (t or "").strip()
            if len(t) >= 3 and len(self.namen) < 5000:
                self.namen.add(t)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.an or getattr(record, "_anonym", False):
            return True
        try:
            record.msg = anonymisieren(record.getMessage(), self.namen)
            record.args = None
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = anonymisieren(record.exc_text, self.namen)
        except Exception:  # noqa: BLE001 – Logging darf nie scheitern
            pass
        record._anonym = True
        return True


ANONYM = Anonymisierer()


def anonym_setzen(an: bool, k=None) -> None:
    """Einstellung „Logs anonymisieren“ übernehmen (wirkt sofort auf alle Handler). Mit ``k`` (Konfig) werden
    die eigenen Stammdaten (Firma, Anschrift, Kontakt) zusätzlich wörtlich maskiert."""
    ANONYM.an = bool(an)
    if not an:
        ANONYM.namen.clear()
    elif k is not None:
        v = k.absender
        ANONYM.merken(v.name, v.anschrift.strasse, v.anschrift.ort, v.kontakt_name, v.kontakt_telefon,
                      v.kontakt_email, v.elektronische_adresse)
    for h in [*logging.getLogger().handlers, *logging.getLogger("fakturafalter").handlers]:
        if ANONYM not in h.filters:
            h.addFilter(ANONYM)


def aktuell() -> Path | None:
    """Pfad der aktiven Logdatei (oder None)."""
    return Path(_handler.baseFilename) if _handler else None


def einrichten(ordner: Path, ebene: int = logging.DEBUG, max_bytes: int = 1_000_000, anzahl: int = 5) -> Path | None:
    """Logdatei unter `ordner` anlegen (einmal pro Prozess; erneuter Aufruf mit anderem Ordner wechselt).

    Konsolen-Handler, die noch keine eigene Stufe haben, werden auf INFO gesetzt, damit DEBUG nur in der Datei landet.
    """
    global _handler
    lg = logging.getLogger("fakturafalter")
    ziel = Path(ordner) / NAME
    if _handler is not None:
        if Path(_handler.baseFilename) == ziel.resolve():
            return ziel
        lg.removeHandler(_handler)
        _handler.close()
        _handler = None
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(ziel, maxBytes=max_bytes, backupCount=anzahl, encoding="utf-8", delay=True)
    except OSError:
        return None
    h.setLevel(ebene)
    h.setFormatter(logging.Formatter(FORMAT))
    h.addFilter(ANONYM)
    wurzel = logging.getLogger()
    for wurzel_h in wurzel.handlers:          # Konsole: bisherige Schwelle beibehalten
        if wurzel_h.level == logging.NOTSET:
            wurzel_h.setLevel(wurzel.level)
        if not any(isinstance(f, _OhneNurDatei) for f in wurzel_h.filters):
            wurzel_h.addFilter(_OhneNurDatei())
        if ANONYM not in wurzel_h.filters:
            wurzel_h.addFilter(ANONYM)
    lg.addHandler(h)
    if lg.level == logging.NOTSET or lg.level > ebene:
        lg.setLevel(ebene)
    _handler = h
    return ziel


def beenden() -> None:
    global _handler
    if _handler is not None:
        logging.getLogger("fakturafalter").removeHandler(_handler)
        _handler.close()
        _handler = None
