# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Hinweis beim Start: keine Gewährleistung, kein Support (Apache-2.0 §7/§8), offscreen."""

import os

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from .test_gui import fenster, konfig_datei, qapp  # noqa: E402,F401


def test_hinweis_sichtbar_ohne_popup(fenster, qapp):
    h = fenster.starthinweis
    assert h is not None and h.isVisibleTo(fenster)
    assert "Gewährleistung" in " ".join(l_.text() for l_ in h.findChildren(type(fenster.l_titel)))
    assert fenster.b_nie.height() >= 48 and fenster.b_hinweis_zu.height() >= 48
    assert fenster.zust == "aktiv"  # Überwachung läuft trotzdem


def test_schliessen_nur_bis_zum_neustart(fenster, qapp, konfig_datei):
    fenster.b_hinweis_zu.click()
    qapp.processEvents()
    assert fenster.starthinweis is None
    roh = yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))
    assert not (roh.get("oberflaeche") or {}).get("starthinweis_aus")


def test_nicht_mehr_anzeigen_bleibt(fenster, qapp, konfig_datei):
    from fakturafalter.gui.hauptfenster import Hauptfenster

    fenster.b_nie.click()
    qapp.processEvents()
    assert fenster.starthinweis is None
    assert (
        yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))["oberflaeche"]["starthinweis_aus"]
        is True
    )
    w2 = Hauptfenster(konfig_datei, tray_erlaubt=False, auto_start=False)
    try:
        assert w2.starthinweis is None
    finally:
        w2.beenden()
        qapp.processEvents()


def test_englisch(qapp, konfig_datei, monkeypatch, tmp_path):
    from fakturafalter.gui import texte
    from fakturafalter.gui.hauptfenster import Hauptfenster

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    roh = yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))
    roh.setdefault("oberflaeche", {})["sprache"] = "en"
    konfig_datei.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    w = Hauptfenster(konfig_datei, tray_erlaubt=False, auto_start=False)
    try:
        assert w.b_nie.text() == "Don’t show again" and w.b_hinweis_zu.text() == "Close"
    finally:
        w.beenden()
        qapp.processEvents()
        texte.sprache_setzen("de")
