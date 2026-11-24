# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""protokoll.tsv – ab 0.9.6 im eigenen, sichtbaren Ordner „Protokoll“ (nicht mehr im Ausgang).

Der Ausgang ist eine reine Postbox: Archiv, Mensch oder ein anderes Programm darf ihn jederzeit leeren. Das
Protokoll ist die Grundlage der Doppelprüfung (bekannte Rechnungsnummern) und der Lückenwarnung; es liegt darum
getrennt davon.  Zeilen werden je Rechnung sofort angehängt, nicht erst am Laufende.  Ist die Datei gerade
gesperrt (z. B. in Excel geöffnet), landen die Zeilen in ``protokoll-nachtrag.tsv`` (im Protokollordner, sonst
neben der Logdatei) und werden beim nächsten Lauf übernommen.  Ein altes protokoll.tsv im Ausgang wird nicht
übernommen und nicht mehr gelesen."""

from __future__ import annotations

import logging
from pathlib import Path

from . import dateien, logdatei, pflichtpruefung

log = logging.getLogger("fakturafalter")

DATEI = "protokoll.tsv"
NACHTRAG = "protokoll-nachtrag.tsv"

# Meldungen für Oberfläche/Log: (Vorlage, Werte) – die Oberfläche übersetzt die Vorlage
FEHLT = (
    "Kein Protokoll in {ordner} gefunden, obwohl schon Rechnungen erzeugt wurden. Ein neues Protokoll wird "
    "angelegt; die Doppelprüfung kennt Rechnungsnummern erst ab jetzt."
)
NICHT_BESCHREIBBAR = "Protokollordner {ordner} ist nicht beschreibbar – Protokollzeilen gehen ersatzweise in die Logdatei."
ERSATZ = "Protokoll {datei} ist gerade gesperrt – Zeilen stehen vorerst in {ersatz} und werden nachgetragen."


def pfad(k) -> Path:
    return Path(k.protokoll) / DATEI


def _ersatz(k) -> list[Path]:
    orte = [Path(k.protokoll) / NACHTRAG]
    lg = logdatei.aktuell()
    if lg is not None:
        orte.append(lg.parent / NACHTRAG)
    return orte


def vorhandene(k) -> list[Path]:
    """Alle Protokolldateien, die gelesen werden (Hauptdatei zuerst, dann Nachträge)."""
    return [p for p in (pfad(k), *_ersatz(k)) if p.exists()]


def bekannte_nummern(k) -> frozenset[str]:
    aus: set[str] = set()
    for p in vorhandene(k):
        aus |= pflichtpruefung.bekannte_nummern(p)
    return frozenset(aus)


def zeilen(k) -> list[str]:
    out: list[str] = []
    for p in vorhandene(k):
        try:
            out += p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            log.warning("Protokoll %s nicht lesbar: %s", p, e)
    return out


def _fruehere_laeufe(k) -> bool:
    """Gab es offenbar schon Läufe? (Dateien in Erledigt/Ausgang oder ein altes protokoll.tsv im Ausgang)"""
    try:
        if (Path(k.ausgang) / DATEI).exists():
            return True
        for ordner, muster in ((k.erledigt, "*"), (k.ausgang, "*.pdf"), (k.ausgang, "*.xml")):
            if Path(ordner).is_dir() and any(p.is_file() for p in Path(ordner).glob(muster)):
                return True
    except OSError:
        return False
    return False


def _nachtraege_uebernehmen(k) -> None:
    haupt = pfad(k)
    for n in _ersatz(k):
        if not n.exists():
            continue
        try:
            text = n.read_text(encoding="utf-8", errors="replace")
            if text and not text.endswith("\n"):
                text += "\n"
            dateien.anhaengen(haupt, text)
            n.unlink()
            log.info("Protokoll-Nachtrag %s in %s übernommen", n, haupt)
        except OSError as e:
            log.info("Protokoll-Nachtrag %s bleibt vorerst: %s", n, e)


def vorbereiten(k) -> list[tuple[str, dict]]:
    """Vor dem Lauf: Ordner anlegen und Beschreibbarkeit prüfen, Nachträge übernehmen, fehlendes Protokoll
    melden. Hält nie an (fire and forget). -> Meldungen [(Vorlage, Werte)]."""
    meldungen: list[tuple[str, dict]] = []
    ordner = Path(k.protokoll)
    try:
        dateien.beschreibbar_pruefen(ordner)
    except OSError as e:
        log.error("Protokollordner %s nicht beschreibbar: %s", ordner, e)
        meldungen.append((NICHT_BESCHREIBBAR, {"ordner": str(ordner)}))
        return meldungen
    if not vorhandene(k) and _fruehere_laeufe(k):
        log.warning(FEHLT.format(ordner=ordner))
        meldungen.append((FEHLT, {"ordner": str(ordner)}))
    _nachtraege_uebernehmen(k)
    return meldungen


def schreiben(k, zeilen_: list[str]) -> tuple[str, dict] | None:
    """Zeilen sofort anhängen; gesperrt -> Nachtrag, sonst Logdatei. -> Meldung bei Ersatzweg, sonst None."""
    if not zeilen_:
        return None
    text = "\n".join(zeilen_) + "\n"
    haupt = pfad(k)
    for i, ziel in enumerate((haupt, *_ersatz(k))):
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            dateien.anhaengen(ziel, text)
        except OSError as e:
            log.warning("Protokoll %s nicht beschreibbar: %s", ziel, e)
            continue
        if i == 0:
            return None
        log.warning(ERSATZ.format(datei=haupt, ersatz=ziel))
        return (ERSATZ, {"datei": str(haupt), "ersatz": str(ziel)})
    log.error("Protokollzeilen konnten nirgends gespeichert werden:\n%s", text.rstrip())
    return (NICHT_BESCHREIBBAR, {"ordner": str(haupt.parent)})
