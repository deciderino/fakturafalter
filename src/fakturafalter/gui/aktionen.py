# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Dateien/Ordner mit dem Standardprogramm des Systems öffnen (lokal, kein Netz)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

geoeffnet: list[Path] = []  # für Tests nachvollziehbar
NUR_MERKEN = False  # Tests/Screenshots: nichts wirklich öffnen


def oeffnen(pfad: Path) -> bool:
    pfad = Path(pfad)
    geoeffnet.append(pfad)
    if NUR_MERKEN:
        return True
    if pfad.suffix == "" and not pfad.exists():
        pfad.mkdir(parents=True, exist_ok=True)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))
