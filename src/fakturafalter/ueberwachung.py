# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Eingangsordner überwachen (watchdog), Dateien erst verarbeiten, wenn sie fertig geschrieben sind.

- Datei gilt als stabil, wenn Größe und Änderungszeit ``stabil_sekunden`` lang gleich bleiben und sie
  sich zum Lesen öffnen lässt (unter Windows schlägt das fehl, solange der Drucker/Export schreibt).
- Verarbeitet wird stapelweise, wenn ``paarung_sekunden`` lang keine neue Datei kam – so landen
  PDF und CSV derselben Rechnung im selben Lauf und werden gepaart.
- PDF + CSV/XML: eine Datei wartet, bis ihr Gegenstück mit gleichem Namen da ist (R-123.pdf + R-123.csv);
  erst nach ``gegenstueck_minuten`` geht sie allein in den Lauf (dort Paarung über die Rechnungsnummer).
- ``polling=True`` nutzt den PollingObserver (Netzlaufwerke/SMB, wo Dateisystem-Ereignisse fehlen).
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from .konfig import Konfig
from .pipeline import Lauf, verarbeiten

log = logging.getLogger("fakturafalter")


def relevant(p: Path) -> bool:
    n = p.name
    return p.is_file() and not (n.startswith((".", "~")) or n.endswith((".tmp", ".part", ".crdownload")))


DATEN_ENDUNGEN = {".csv", ".txt", ".tsv", ".xml"}


def mehrfach_eingabe(k: Konfig) -> bool:
    """PDF + CSV oder PDF + XML: zu jedem Druck gehört eine Datendatei."""
    return k.pdf_als_gegenstueck() and k.gegenstueck_minuten > 0


def nach_gegenstueck(dateien: list[Path], k: Konfig, seit: dict[Path, float], jetzt: float
                     ) -> tuple[list[Path], list[Path]]:
    """-> (bereit, wartend). Bereit: Paare mit gleichem Namen (PDF + Daten) und alles, was schon länger als
    ``gegenstueck_minuten`` allein liegt. Ohne Mehrfach-Eingabe ist alles bereit."""
    if not mehrfach_eingabe(k):
        return list(dateien), []
    arten: dict[str, set[str]] = {}
    for p in dateien:
        art = "pdf" if p.suffix.lower() == ".pdf" else "daten" if p.suffix.lower() in DATEN_ENDUNGEN else "sonst"
        arten.setdefault(p.stem.lower(), set()).add(art)
    bereit, wartend = [], []
    for p in dateien:
        a = arten[p.stem.lower()]
        if {"pdf", "daten"} <= a or "sonst" in a or jetzt - seit.get(p, jetzt) >= k.gegenstueck_minuten * 60:
            bereit.append(p)
        else:
            wartend.append(p)
    return bereit, wartend


def lesbar(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


class _Sammler(FileSystemEventHandler):
    def __init__(self):
        self.lock = threading.Lock()
        self.letztes = time.monotonic()
        self.neu = threading.Event()

    def on_any_event(self, event: FileSystemEvent) -> None:
        # nur Schreib-Ereignisse zählen; "opened"/"closed_no_write" entstehen auch durch unsere eigene Lesbarkeitsprüfung
        if event.is_directory or event.event_type not in ("created", "modified", "moved", "deleted", "closed"):
            return
        with self.lock:
            self.letztes = time.monotonic()
        self.neu.set()


class Waechter:
    def __init__(self, k: Konfig, polling: bool = False, bei_lauf=None, bei_fortschritt=None):
        self.k = k
        self.polling = polling
        self.bei_lauf = bei_lauf or (lambda lauf: None)
        self.bei_fortschritt = bei_fortschritt          # pipeline.Stand je Schritt (Fortschrittsanzeige)
        self.stopp = threading.Event()
        self._sperre = threading.Lock()        # Ein Lauf zur Zeit (Überwachung und „Jetzt einlesen“)
        self._stand: dict[Path, tuple[int, float, float]] = {}   # pfad -> (größe, mtime, seit)
        self.wartend: list[Path] = []          # warten auf ihr Gegenstück (PDF + CSV/XML)

    def _stabile_dateien(self) -> tuple[list[Path], bool]:
        """-> (stabile Dateien, alle_stabil)."""
        jetzt = time.monotonic()
        stabil, alle = [], True
        vorhanden = [p for p in self.k.eingang.iterdir() if relevant(p)]
        for p in vorhanden:
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            alt = self._stand.get(p)
            if not alt or alt[:2] != (st.st_size, st.st_mtime):
                self._stand[p] = (st.st_size, st.st_mtime, jetzt)
                alle = False
                continue
            if jetzt - alt[2] >= self.k.stabil_sekunden and st.st_size > 0 and lesbar(p):
                stabil.append(p)
            else:
                alle = False
        for p in list(self._stand):
            if p not in vorhanden:
                del self._stand[p]
        return stabil, alle

    def _bereit(self, stabil: list[Path]) -> list[Path]:
        seit = {p: v[2] for p, v in self._stand.items()}
        bereit, wartend = nach_gegenstueck(stabil, self.k, seit, time.monotonic())
        for p in wartend:
            if p not in self.wartend:
                log.info("%s wartet auf die Datei mit gleichem Namen (PDF bzw. CSV/XML), höchstens %g Minuten",
                         p.name, self.k.gegenstueck_minuten)
        for p in bereit:
            if p in self.wartend:
                log.info("%s: kein Gegenstück nach %g Minuten – wird allein verarbeitet (Paarung über die "
                         "Rechnungsnummer)", p.name, self.k.gegenstueck_minuten)
        self.wartend = wartend
        return bereit

    def einmal(self) -> Lauf | None:
        stabil, _ = self._stabile_dateien()
        return self._lauf(self._bereit(stabil))

    def jetzt(self) -> Lauf | None:
        """Alles, was im Eingang liegt und lesbar ist, sofort verarbeiten (ohne Ruhezeit abzuwarten)."""
        self.k.eingang.mkdir(parents=True, exist_ok=True)
        return self._lauf([p for p in self.k.eingang.iterdir() if relevant(p) and lesbar(p)])

    def _lauf(self, dateien: list[Path]) -> Lauf | None:
        with self._sperre:
            dateien = [p for p in dateien if p.exists()]
            if not dateien:
                return None
            log.info("Verarbeite %d Datei(en): %s", len(dateien), ", ".join(p.name for p in dateien))
            if self.bei_fortschritt is None:
                lauf = verarbeiten(dateien, self.k)
            else:
                try:
                    lauf = verarbeiten(dateien, self.k, fortschritt=self.bei_fortschritt)
                except Exception:
                    self.bei_fortschritt(None)          # Anzeige beenden, Fehler geht wie bisher weiter
                    raise
            for p in dateien:
                self._stand.pop(p, None)
        self.bei_lauf(lauf)
        return lauf

    def starten(self) -> None:
        self.k.ordner_anlegen()
        sammler = _Sammler()
        obs = (PollingObserver(timeout=2) if self.polling else Observer())
        obs.schedule(sammler, str(self.k.eingang), recursive=False)
        obs.start()
        log.info("Überwache %s (Ausgang %s)", self.k.eingang, self.k.ausgang)
        try:
            while not self.stopp.is_set():
                sammler.neu.wait(timeout=1.0)
                sammler.neu.clear()
                stabil, alle = self._stabile_dateien()
                with sammler.lock:
                    ruhig = time.monotonic() - sammler.letztes >= self.k.paarung_sekunden
                bereit = self._bereit(stabil) if alle and ruhig else []
                if bereit:
                    try:
                        self._lauf(bereit)
                    except Exception:  # noqa: BLE001 – Dienst darf nicht sterben
                        log.exception("Lauf fehlgeschlagen")
        finally:
            obs.stop()
            obs.join()

    def anhalten(self) -> None:
        self.stopp.set()
