# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Fortschrittsanzeige im Hauptfenster (offscreen, fiktive Daten)."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from fakturafalter.gui import texte  # noqa: E402
from fakturafalter.gui.fortschritt import schritt_namen, text_zeile  # noqa: E402
from fakturafalter.pipeline import Ergebnis, Lauf, Stand  # noqa: E402

from .test_gui import fenster, konfig_datei, pruef_fall_anlegen, qapp  # noqa: E402,F401


def kurz(e):
    return [k for k, _l in schritt_namen(e)]


def test_beschriftung_je_eingabe():
    texte.sprache_setzen("de")
    assert [lg for _k, lg in schritt_namen("pdf")] == [
        "Lesen",
        "Erkennen",
        "XML erzeugen",
        "PDF/A",
        "Prüfen",
        "Ablegen",
    ]
    assert (
        schritt_namen("pdf_csv")[1][1] == "Einlesen (CSV)"
        and schritt_namen("pdf_csv")[2][1] == "XML erzeugen"
    )
    assert (
        schritt_namen("pdf_xml")[1][1] == "Einlesen (XML)"
        and schritt_namen("pdf_xml")[2][1] == "XML übernehmen"
    )
    assert (
        kurz("csv")[3] == "Sichtseite"
        and kurz("xml")[3] == "Sichtseite"
        and kurz("pdf_xml")[3] == "PDF/A"
    )


def test_textzeile():
    texte.sprache_setzen("de")
    s = Stand(4, 3, 12, "RE-2026-0042.pdf", "pdf", 0.42, werkzeug="KoSIT")
    assert text_zeile(s) == "Rechnung 3 von 12 · Prüfen (KoSIT) · RE-2026-0042.pdf"
    assert (
        text_zeile(Stand(2, 1, 1, "RE-2026-0042.pdf", "pdf", 0.4))
        == "XML erzeugen · RE-2026-0042.pdf"
    )
    assert (
        text_zeile(Stand(0, 2, 5, "a.csv", "pdf_csv", 0.1, zaehlt="datei"))
        == "Datei 2 von 5 · Lesen · a.csv"
    )
    assert (
        text_zeile(Stand(4, 0, 12, "", "pdf", 0.7, werkzeug="veraPDF"))
        == "12 Rechnungen · Prüfen (veraPDF)"
    )
    texte.sprache_setzen("en")
    try:
        assert text_zeile(s) == "Invoice 3 of 12 · Validating (KoSIT) · RE-2026-0042.pdf"
    finally:
        texte.sprache_setzen("de")


def test_bereich_nur_waehrend_der_verarbeitung(fenster, qapp):
    assert not fenster.fortschritt.isVisibleTo(fenster)
    assert fenster.l_bereit.text() == "Bereit"
    fenster._bei_fortschritt(Stand(4, 3, 12, "RE-2026-0042.pdf", "pdf", 0.42, werkzeug="KoSIT"))
    qapp.processEvents()
    assert fenster.fortschritt.isVisibleTo(fenster)
    assert not fenster.b_jetzt.isEnabled()
    assert fenster.l_status.text() == "Verarbeitung läuft" and fenster.l_bereit.text() == ""
    assert fenster.fortschritt.l_prozent.text() == "42 %"
    assert [k.zustand for k in fenster.fortschritt.kreise] == ["erkannt"] * 4 + ["aktiv", "aus"]
    # Fehler einer Datei: Hinweis, Balken läuft weiter
    fenster._bei_fortschritt(
        Stand(4, 4, 12, "RE-2026-0043.pdf", "pdf", 0.45, fehler="RE-2026-0042.pdf")
    )
    assert fenster.fortschritt.l_fehler.isVisibleTo(fenster)
    fenster._bei_lauf(Lauf(ergebnisse=[Ergebnis("RE-1", "ok")]))
    qapp.processEvents()
    assert not fenster.fortschritt.isVisibleTo(fenster)
    assert fenster.b_jetzt.isEnabled() and fenster.l_bereit.text() == "Bereit"
    assert not fenster.toasts.sichtbare()  # reiner Erfolg: kein Toast


def test_abbruch_blendet_aus(fenster, qapp):
    fenster._bei_fortschritt(Stand(1, 0, 3, "", "pdf", 0.2))
    fenster._bei_fortschritt(None)
    assert not fenster.fortschritt.isVisibleTo(fenster) and fenster.b_jetzt.isEnabled()


def test_fertig_toast_mit_pruefen(fenster, qapp):
    from .test_gui import warten

    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    lauf = pruef_fall_anlegen(fenster.k)
    fenster._bei_lauf(lauf)
    qapp.processEvents()
    (t,) = fenster.toasts.sichtbare()
    n = len(lauf.ergebnisse)
    assert t.titel.text() == f"{n} verarbeitet, 1 prüfen" and t.knopf.text() == "Prüfen"
    assert t.knopf.height() >= 48


def test_warten_auf_gegenstueck(fenster, qapp, monkeypatch):
    fenster.k.modus = "pdf_csv"
    monkeypatch.setattr(type(fenster.arbeiter), "wartend", property(lambda s: [Path("R-123.pdf")]))
    fenster.aktualisieren()
    assert fenster.l_warten.isVisibleTo(fenster)
    assert fenster.l_warten.text() == "R-123.pdf wartet auf die passende CSV"
    assert not fenster.l_nichts.isVisibleTo(fenster)
