# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Wächter im eigenen Thread; Ergebnisse kommen per Qt-Signal (queued) in den GUI-Thread."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from ..konfig import Konfig
from ..ueberwachung import Waechter

log = logging.getLogger("fakturafalter")


class Arbeiter(QObject):
    lauf_fertig = Signal(object)  # pipeline.Lauf
    zustand = Signal(str)  # "aktiv" | "pausiert" | "beschaeftigt" | "fehler"
    problem = Signal(str)  # Klartext für Toast
    fortschritt = Signal(object)  # pipeline.Stand (queued in den GUI-Thread)

    def __init__(self, k: Konfig, polling: bool = False, parent=None):
        super().__init__(parent)
        self.k = k
        self.polling = polling
        self._w: Waechter | None = None
        self._t: threading.Thread | None = None
        self._jetzt_t: threading.Thread | None = None

    # ------------------------------------------------------------------ Steuerung (GUI-Thread)
    @property
    def aktiv(self) -> bool:
        return self._t is not None and self._t.is_alive()

    @property
    def beschaeftigt(self) -> bool:
        return self._jetzt_t is not None and self._jetzt_t.is_alive()

    @property
    def wartend(self) -> list:
        """Dateien, die auf ihr Gegenstück warten (PDF + CSV/XML), laut Überwachung."""
        return list(self._w.wartend) if self._w else []

    def starten(self) -> None:
        if self.aktiv:
            return
        self._w = Waechter(
            self.k,
            polling=self.polling,
            bei_lauf=self.lauf_fertig.emit,
            bei_fortschritt=self.fortschritt.emit,
        )
        self._t = threading.Thread(
            target=self._schleife, args=(self._w,), name="fakturafalter-waechter", daemon=True
        )
        self._t.start()
        self.zustand.emit("aktiv")

    def _schleife(self, w: Waechter) -> None:
        try:
            w.starten()
        except Exception as e:  # noqa: BLE001 – z.B. Eingang nicht erreichbar
            log.exception("Überwachung beendet")
            self.problem.emit(f"{type(e).__name__}: {e}")
            self.zustand.emit("fehler")

    def pausieren(self, warten: float = 5.0) -> None:
        if self._w:
            self._w.anhalten()
        if self._t:
            self._t.join(timeout=warten)
        self._t = self._w = None
        self.zustand.emit("pausiert")

    def jetzt_einlesen(self) -> bool:
        """Eingang sofort abarbeiten (eigener Thread, gleiche Sperre wie die Überwachung)."""
        if self.beschaeftigt:
            return False
        w = self._w or Waechter(
            self.k,
            polling=self.polling,
            bei_lauf=self.lauf_fertig.emit,
            bei_fortschritt=self.fortschritt.emit,
        )

        def los():
            try:
                if w.jetzt() is None:
                    self.lauf_fertig.emit(None)
            except Exception as e:  # noqa: BLE001
                log.exception("Einlesen fehlgeschlagen")
                self.problem.emit(f"{type(e).__name__}: {e}")

        self._jetzt_t = threading.Thread(target=los, name="fakturafalter-jetzt", daemon=True)
        self._jetzt_t.start()
        return True

    def neu_konfigurieren(self, k: Konfig, polling: bool) -> None:
        lief = self.aktiv
        if lief:
            self.pausieren()
        self.k, self.polling = k, polling
        if lief:
            self.starten()

    def beenden(self) -> None:
        if self._w:
            self._w.anhalten()
        for t in (self._t, self._jetzt_t):
            if t:
                t.join(timeout=10)
        self._t = self._w = None


class _LogSignal(QObject):
    zeile = Signal(str)


class LogBruecke(logging.Handler):
    """Logzeilen (aus beliebigen Threads) als Qt-Signal ``signal.zeile`` in die Protokoll-Ansicht."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.signal = _LogSignal()
        from ..logdatei import ANONYM

        self.addFilter(ANONYM)  # „Logs anonymisieren“ gilt auch für die Protokoll-Ansicht
        self.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            self.signal.zeile.emit(self.format(record))
        except RuntimeError:  # Qt-Objekt schon weg (Programmende)
            pass
