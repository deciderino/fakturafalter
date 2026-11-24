# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Skizze: Selbstkontrolle in der Prüfansicht und im Anlern-Assistenten.

Nur fiktive Werte. Offscreen-PNGs nach /tmp/e2-skizze-kontrolle/.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 skizzen/kontrolle_bestaetigen.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT / "src"))

from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget  # noqa: E402

from fakturafalter.gui import thema  # noqa: E402
from fakturafalter.gui.bausteine import karte, knopf, lbl, trenner  # noqa: E402

ZIEL = Path("/tmp/e2-skizze-kontrolle")
HINWEIS = (
    "Selbstkontrolle offen: Die Vorlage muster-a1b2c3d4 hat Rechnungsnummer nach dem letzten "
    "Anlernen anders gelesen als bestätigt – bitte prüfen. Bestätigt ist es, sobald eine "
    "angelernte PDF dieses Absenders das Feld wieder richtig liest."
)
POS_HINWEIS = (
    "Selbstkontrolle: Nach dem letzten Speichern hat die Vorlage die Positionen anders gelesen "
    "– bitte prüfen."
)


def _karte_pruefen(c, offen: bool) -> QWidget:
    k, kv = karte()
    kv.addWidget(
        lbl("RE-2026-0042  ·  Beispiel Werkzeugbau GmbH  ·  1.271,50 €", "titel", umbruch=True)
    )
    kv.addWidget(lbl("heute 08:16", "sub"))
    kv.addWidget(trenner())
    kv.addWidget(
        lbl("Rechnungsnummer    CSV: 26000042    Druck: 26000099", "hinweis", umbruch=True)
    )
    if offen:
        kv.addWidget(lbl(HINWEIS, "hinweis", umbruch=True))
    zeile = QWidget()
    h = QHBoxLayout(zeile)
    h.setContentsMargins(0, 8, 0, 0)
    h.setSpacing(8)
    h.addWidget(knopf("Druck-PDF"))
    h.addWidget(knopf("CSV"))
    if offen:
        h.addWidget(knopf("Felder bestätigen", primary=True))
    h.addStretch(1)
    h.addWidget(knopf("Verwerfen"))
    kv.addWidget(zeile)
    return k


def _seite_pruefen(c, offen: bool) -> QWidget:
    w = QWidget()
    w.setObjectName("wurzel")
    v = QVBoxLayout(w)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(10)
    v.addWidget(lbl("Zu prüfen (1)", "titel"))
    v.addWidget(
        lbl(
            "Hinweise erscheinen hier und im Protokoll, ohne extra Fenster. "
            "Offene Selbstkontrolle: die Felder der Vorlage bitte prüfen oder bestätigen.",
            "hinweis",
            umbruch=True,
        )
    )
    v.addWidget(_karte_pruefen(c, offen))
    v.addStretch(1)
    return w


def _seite_positionen(c, offen: bool) -> QWidget:
    w = QWidget()
    w.setObjectName("wurzel")
    v = QVBoxLayout(w)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(8)
    v.addWidget(lbl("Vorlage anlernen: Muster GmbH  ·  PDF 2 von 4", "titel", umbruch=True))
    v.addWidget(lbl("Positionen", "titel"))
    if offen:
        hin = lbl(POS_HINWEIS, "hinweis", umbruch=True)
        hin.setStyleSheet(f"color:{c['err']}; font-weight:600;")
        v.addWidget(hin)
    v.addWidget(
        lbl(
            "Zieh in der PDF einen Rahmen um die Tabelle (mit Kopfzeile). Dann sag pro Spalte, "
            "was drinsteht.",
            "hinweis",
            umbruch=True,
        )
    )
    k, kv = karte()
    kv.addWidget(lbl("Spalten zuordnen", "sektion"))
    kv.addWidget(lbl("Pos.  |  Art-Nr.  |  Bezeichnung  |  Menge  |  Einzel  |  Gesamt", "hinweis"))
    kv.addWidget(lbl("1     |  470011   |  Schraube M8  |  10     |  0,80 €  |  8,00 €", "hinweis"))
    kv.addWidget(lbl("2     |  470014   |  Mutter M8    |  10     |  0,50 €  |  5,00 €", "hinweis"))
    v.addWidget(k)
    v.addStretch(1)
    return w


def main() -> None:
    app = QApplication.instance() or QApplication(["skizze-kontrolle"])
    c = thema.anwenden(app, "hell")
    ZIEL.mkdir(parents=True, exist_ok=True)
    seiten = [
        (_seite_pruefen(c, True), "pruefansicht-offen.png", 820, 520),
        (_seite_pruefen(c, False), "pruefansicht-bestaetigt.png", 820, 420),
        (_seite_positionen(c, True), "anlernen-positionen.png", 720, 560),
        (_seite_positionen(c, False), "anlernen-positionen-ok.png", 720, 520),
    ]
    for w, name, b, h in seiten:
        w.resize(b, h)
        w.show()
        app.processEvents()
        bild = w.grab()
        pfad = ZIEL / name
        bild.save(str(pfad), "PNG")
        w.close()
        print(pfad, bild.width(), "x", bild.height())
    print("fertig", ZIEL)


if __name__ == "__main__":
    main()
