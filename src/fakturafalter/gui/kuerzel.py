# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Label, das lange Pfade in der Mitte kürzt („C:\\…\\eingang“), voller Pfad im Tooltip."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class KurzLabel(QLabel):
    def __init__(self, text: str = "", name: str | None = "sub"):
        super().__init__()
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(80)
        self.voll = ""
        self.setze(text)

    def setze(self, text: str) -> None:
        self.voll = text
        self.setToolTip(text)
        self._kuerzen()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._kuerzen()

    def _kuerzen(self) -> None:
        self.setText(
            self.fontMetrics().elidedText(
                self.voll, Qt.TextElideMode.ElideMiddle, max(self.width(), 80)
            )
        )
