# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Dialog für abgelehnte CSV-Profile (Profilformat 2, keine Migration)."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QMessageBox, QWidget

from .texte import _

TITEL = "Dieses Profil passt nicht mehr zu Fakturafalter 1.0"


def baue(parent: QWidget | None, meldung: str, titel: str | None = None) -> tuple[QMessageBox, object]:
    """-> (Dialog, Knopf „Assistent öffnen“). Für Tests ohne exec() nutzbar."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_(titel or TITEL))
    box.setText(_(titel or TITEL))
    box.setInformativeText(meldung)
    assistent = box.addButton(_("Assistent öffnen"), QMessageBox.ButtonRole.AcceptRole)
    schliessen = box.addButton(_("Schließen"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(assistent)
    box.setEscapeButton(schliessen)
    return box, assistent


def zeigen(parent: QWidget | None, meldung: str, titel: str | None = None) -> bool:
    """Zeigt die Ablehnung. True, wenn „Assistent öffnen“ gewählt wurde. Die Datei bleibt unangetastet."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("FF_DIALOGE_IN_TESTS"):
        return False  # automatisierte Tests dürfen nicht an modalen Dialogen hängen
    box, assistent = baue(parent, meldung, titel)
    box.exec()
    return box.clickedButton() is assistent
