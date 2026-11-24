# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Skizze: neue Sektion „Gutschrift“ im Anlern-Assistenten (Rechnungsdaten).

Nur fiktive Werte. Offscreen-PNGs nach /tmp/e2-skizze-gutschrift/.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 skizzen/gutschrift_anlernen.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT / "src"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget  # noqa: E402

from fakturafalter.gui.anlernen import Feldzeile  # noqa: E402
from fakturafalter.gui.bausteine import lbl, trenner  # noqa: E402
from fakturafalter.gui.texte import _  # noqa: E402
from fakturafalter.gui import thema  # noqa: E402

ZIEL = Path("/tmp/e2-skizze-gutschrift")
BREITE, HOEHE = 720, 780


def _zeile(c, name, wert="", zustand="fehlt", hilfe="", passt=False, aktiv=False, bereich=False):
    z = Feldzeile(c, name, lambda: None, lambda t: None, lambda: None, lambda: None)
    z.setzen(wert, zustand, hilfe, passt=passt)
    if aktiv:
        z.aktiv(True, bereich=bereich)
    return z


def _seite(c, variant: str) -> QWidget:
    w = QWidget()
    w.setObjectName("wurzel")
    v = QVBoxLayout(w)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(6)
    v.addWidget(lbl("Rechnungsdaten", "titel", umbruch=True))
    v.addWidget(
        lbl(
            "Feld anklicken, dann den Wert in der PDF anklicken. Oder einfach eintippen – "
            "die App sucht ihn dann selbst. Über den Rahmen-Knopf ziehst du einen Bereich "
            "um mehrere Wörter oder Zeilen.",
            "hinweis",
            umbruch=True,
        )
    )
    v.addWidget(trenner())

    v.addWidget(lbl("Rechnungsnummer", umbruch=True))
    v.addWidget(_zeile(c, "Rechnungsnummer", "GS-2026-0001" if variant != "rechnung" else "NB-26-1001", "erkannt"))
    v.addWidget(_zeile(c, "Rechnungsdatum", "05.10.2026", "erkannt"))

    v.addSpacing(8)
    v.addWidget(lbl("Gutschrift", "sektion"))
    v.addWidget(
        lbl(
            "Freiwillig: Rahmen um den Titel im Druck und – bei einer Gutschrift – "
            "um die Nummer der ursprünglichen Rechnung. Weicht der Kopf der Gutschrift "
            "vom Rechnungslayout ab, als eigene Vorlage anlernen.",
            "hinweis",
            umbruch=True,
        )
    )

    if variant == "ohne_bezug":
        v.addWidget(
            _zeile(
                c,
                "Belegart: Titel im Druck (freiwillig)",
                "Gutschrift",
                "erkannt",
                "Gutschrift erkannt (Belegart 381). Gutschrift: Bitte die Nummer der "
                "Ursprungsrechnung angeben (Rahmen um die Bezugszeile ziehen) – ohne Bezug "
                "kann die Gutschrift nicht gespeichert werden (§ 31 Abs. 5 UStDV).",
            )
        )
        v.addWidget(
            _zeile(
                c,
                "Bezug: Nummer der Ursprungsrechnung (bei Gutschrift)",
                "",
                "fehlt",
                "Gutschrift: Bitte die Nummer der Ursprungsrechnung angeben "
                "(Rahmen um die Bezugszeile ziehen) – ohne Bezug kann die Gutschrift "
                "nicht gespeichert werden (§ 31 Abs. 5 UStDV).",
                aktiv=True,
                bereich=True,
            )
        )
    elif variant == "mit_bezug":
        v.addWidget(
            _zeile(
                c,
                "Belegart: Titel im Druck (freiwillig)",
                "Gutschrift",
                "erkannt",
                "Gutschrift erkannt (Belegart 381).",
            )
        )
        v.addWidget(
            _zeile(
                c,
                "Bezug: Nummer der Ursprungsrechnung (bei Gutschrift)",
                "NB-26-0990 vom 01.10.2026",
                "erkannt",
                "Gutschrift erkannt (Belegart 381).",
            )
        )
    else:
        v.addWidget(
            _zeile(
                c,
                "Belegart: Titel im Druck (freiwillig)",
                "Rechnung",
                "erkannt",
                "Rechnung (Belegart 380).",
            )
        )
        v.addWidget(
            _zeile(
                c,
                "Bezug: Nummer der Ursprungsrechnung (bei Gutschrift)",
                "",
                "aus",
            )
        )

    v.addSpacing(8)
    v.addWidget(lbl("Weitere Angaben (freiwillig)", "sektion"))
    v.addWidget(_zeile(c, "Bestellnummer (freiwillig)", "B-4500", "erkannt"))
    v.addStretch(1)
    fuss = lbl(
        "Skizze · nur erfundene Daten · Rahmen-Knopf 48 px, Hinweis ohne Popup.",
        "sub",
        umbruch=True,
    )
    v.addWidget(fuss)
    return w


def main() -> None:
    app = QApplication.instance() or QApplication(["skizze-gutschrift"])
    c = thema.anwenden(app, "hell")
    ZIEL.mkdir(parents=True, exist_ok=True)
    dateien = {
        "ohne_bezug": "gutschrift-ohne-bezug.png",
        "mit_bezug": "gutschrift-mit-bezug.png",
        "rechnung": "rechnung-belegart-380.png",
    }
    for variant, name in dateien.items():
        w = _seite(c, variant)
        w.resize(BREITE, HOEHE)
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
