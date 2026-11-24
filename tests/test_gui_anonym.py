# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Schalter „Logs anonymisieren“ in den Einstellungen (offscreen)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from fakturafalter import logdatei  # noqa: E402

from .test_gui import fenster, konfig_datei, qapp  # noqa: E402,F401


def test_schalter_speichert_und_wirkt(fenster, qapp):
    from fakturafalter.gui.einstellungen import Einstellungen

    d = Einstellungen(fenster)
    assert not d.anonym.isChecked()
    d.anonym.setChecked(True)
    roh = d.ergebnis()
    assert roh["optionen"]["logs_anonymisieren"] is True
    try:
        assert fenster.einstellungen_uebernehmen(roh)
        assert fenster.k.logs_anonym and logdatei.ANONYM.an
        assert "Muster GmbH" in logdatei.ANONYM.namen  # eigene Stammdaten
        d2 = Einstellungen(fenster)
        assert d2.anonym.isChecked()
    finally:
        logdatei.anonym_setzen(False)
