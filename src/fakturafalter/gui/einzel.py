# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Nur eine Oberfläche pro Benutzer und Konfiguration: ein zweiter Start holt das vorhandene Fenster nach vorn.

Lokal über QLocalServer/QLocalSocket (Unix-Socket bzw. Named Pipe) – kein Netzwerk.
"""

from __future__ import annotations

import getpass
import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

ZEIGEN, STILL = b"zeigen\n", b"still\n"


def server_name(konfig: Path) -> str:
    try:
        nutzer = getpass.getuser()
    except Exception:  # noqa: BLE001 – ohne Benutzernamen trotzdem eindeutig genug
        nutzer = "?"
    h = hashlib.sha256(f"{nutzer}\0{Path(konfig).resolve()}".encode()).hexdigest()[:16]
    return f"fakturafalter-{h}"


class Einzelinstanz(QObject):
    geweckt = Signal(bool)  # True = Fenster zeigen

    def __init__(self, konfig: Path, parent=None):
        super().__init__(parent)
        self.name = server_name(konfig)
        self.server: QLocalServer | None = None

    def andere_wecken(self, zeigen: bool = True, warte_ms: int = 800) -> bool:
        """True, wenn schon eine Instanz läuft (die dann benachrichtigt wurde)."""
        s = QLocalSocket()
        s.connectToServer(self.name)
        if not s.waitForConnected(warte_ms):
            return False
        s.write(ZEIGEN if zeigen else STILL)
        s.flush()
        s.waitForBytesWritten(warte_ms)
        s.disconnectFromServer()
        return True

    def lauschen(self) -> bool:
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(self.name):
            # Reste eines abgestürzten Laufs (Unix-Socket-Datei) entfernen und nochmal
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                return False
        self.server.newConnection.connect(self._neu)
        return True

    def _neu(self) -> None:
        while self.server and self.server.hasPendingConnections():
            s = self.server.nextPendingConnection()
            s.readyRead.connect(lambda s=s: self._lesen(s))
            s.disconnected.connect(s.deleteLater)
            if s.bytesAvailable():
                self._lesen(s)

    def _lesen(self, s: QLocalSocket) -> None:
        daten = bytes(s.readAll().data())
        if daten:
            self.geweckt.emit(not daten.startswith(STILL.strip()))

    def schliessen(self) -> None:
        if self.server:
            self.server.close()
            self.server.deleteLater()  # Qt räumt Server samt Verbindungen in der Ereignisschleife ab
            self.server = None
