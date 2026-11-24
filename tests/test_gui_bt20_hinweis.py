# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Prüfhinweis BT-20 (Zahlungsbedingung im Druck nicht lesbar) erreicht Karte „Zu tun“, Prüfansicht,
Protokoll und Logdatei. Nur fiktive Daten (Muster GmbH, variante-a)."""

import logging
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel  # noqa: E402

from fakturafalter import logdatei, pipeline  # noqa: E402
from fakturafalter.gui import daten  # noqa: E402

from .test_gui import BEISPIELE, fenster, konfig_datei, qapp, warten  # noqa: E402,F401

HINWEIS = "Der Druck nennt eine Zahlungsbedingung, die sich nicht eindeutig lesen lässt."
REST = "wird deshalb nicht übernommen – bitte die Zahlungsbedingung angeben"


def _beleg(k) -> list[Path]:
    """CSV ohne Zahlungsbedingung (BT-20 kommt aus dem Profil) + Druck mit „Zahlbar nach Vereinbarung“."""
    from reportlab.pdfgen import canvas

    k.eingang.mkdir(parents=True, exist_ok=True)
    zeilen = (BEISPIELE / "variante-a_positionen_utf8.csv").read_text(encoding="utf-8").splitlines()
    csv = k.eingang / "export.csv"
    csv.write_text(
        "\n".join([zeilen[0], *(z for z in zeilen[1:] if z.startswith("RE-2026-0101"))]) + "\n",
        encoding="utf-8",
    )
    pdf = k.eingang / "druck-0101.pdf"
    c = canvas.Canvas(str(pdf))
    for i, s in enumerate(
        (
            "Muster GmbH · Musterstraße 1 · 12345 Musterstadt",
            "Rechnung Nr. RE-2026-0101",
            "Rechnungsdatum 05.10.2026",
            "Zahlbar nach Vereinbarung.",
        )
    ):
        c.drawString(60, 800 - 20 * i, s)
    c.save()
    return [csv, pdf]


def test_bt20_hinweis_in_zu_tun_pruefansicht_und_log(fenster, qapp, tmp_path):
    k = fenster.k
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    vorher = logging.root.manager.disable  # andere Tests schalten Logging ggf. global ab
    logging.disable(logging.NOTSET)
    datei = logdatei.einrichten(tmp_path / "logs")
    try:
        lauf = pipeline.verarbeiten(_beleg(k), k)
        logdatei._handler.flush()
        log = datei.read_text(encoding="utf-8")
    finally:
        logdatei.beenden()
        logging.disable(vorher)
    (e,) = lauf.ergebnisse
    assert e.status == "pruefen"
    assert any(h.startswith("PRUEFEN: [BT-20] " + HINWEIS) for h in e.hinweise), e.hinweise

    # Logdatei: vollständiger Text mit Feld
    assert "[BT-20] " + HINWEIS in log and REST in log
    assert "(„Zahlbar innerhalb 14 Tagen ohne Abzug.“)" in log

    # Karte „Zu tun“
    fenster._bei_lauf(lauf)
    fenster.aktualisieren()
    qapp.processEvents()
    assert fenster.pruef_zeile.isVisibleTo(fenster)
    assert fenster.l_pruef.text() == "1 Rechnung braucht deine Prüfung"

    # Prüfansicht: Hinweis als eigener, umbrechender Punkt
    (fall,) = daten.prueffaelle(k)
    assert any(t.startswith(HINWEIS) and REST in t for t in fall.sonstige)
    fenster.pruefansicht_oeffnen(0)
    qapp.processEvents()
    pa = fenster.pruef_fenster
    assert pa.reiter.tabText(0) == "Zu prüfen (1)"
    (l_,) = [x for x in pa.findChildren(QLabel) if x.text().startswith("• " + HINWEIS)]
    assert REST in l_.text() and l_.wordWrap() and l_.isVisibleTo(pa)

    # Protokoll (Reiter 3): Hinweis steht in der Zeile der Rechnung
    pa.reiter.setCurrentIndex(2)
    pa.aktualisieren()
    qapp.processEvents()
    assert HINWEIS in pa.protokoll.toPlainText()
