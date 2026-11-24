# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Skizze: Käuferfelder Kontaktstelle (BT-56) und Adresszeile 3 (BT-163) im Anlern-Assistenten.

Nur fiktive Werte. Offscreen-PNGs nach /tmp/e2-skizze-adresszusatz/.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 skizzen/adresszusatz_felder.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT / "src"))

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from fakturafalter.gui import thema  # noqa: E402
from fakturafalter.gui.anlernen import Feldzeile  # noqa: E402
from fakturafalter.gui.bausteine import lbl, trenner  # noqa: E402

ZIEL = Path("/tmp/e2-skizze-adresszusatz")


def _zeile(c, name, wert="", zustand="fehlt", hilfe="", passt=False):
    z = Feldzeile(c, name, lambda: None, lambda t: None, lambda: None, lambda: None)
    z.setzen(wert, zustand, hilfe, passt=passt)
    return z


def _seite(c, variant: str) -> QWidget:
    w = QWidget()
    w.setObjectName("wurzel")
    v = QVBoxLayout(w)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(6)
    v.addWidget(lbl("Vorlage anlernen: Muster GmbH  ·  PDF 1 von 2", "titel", umbruch=True))
    v.addWidget(lbl("Rechnungsdaten", "titel"))
    v.addWidget(
        lbl(
            "Feld anklicken, dann den Wert in der PDF anklicken. Oder einfach eintippen. "
            "Kontaktstelle und Adresszeile 3 bleiben stehen, auch wenn Name oder Zusatz geändert werden.",
            "hinweis",
            umbruch=True,
        )
    )
    v.addWidget(trenner())
    v.addWidget(lbl("Käufer", "sektion"))

    if variant == "voll":
        v.addWidget(_zeile(c, "Käufer: Name", "Beispiel AG", "erkannt"))
        v.addWidget(_zeile(c, "Käufer: Adresszusatz (freiwillig)", "Abteilung Einkauf", "erkannt"))
        v.addWidget(_zeile(c, "Käufer: Adresszeile 3 (freiwillig)", "Gebäude C", "erkannt"))
        v.addWidget(_zeile(c, "Käufer: Kontaktstelle (freiwillig)", "Frau Muster", "erkannt"))
    elif variant == "name_geaendert":
        # Name/Zusatz vom Nutzer geändert – Kontaktstelle und Zeile 3 bleiben sichtbar und korrigierbar
        v.addWidget(_zeile(c, "Käufer: Name", "Beispiel Werkzeugbau GmbH", "erkannt"))
        v.addWidget(_zeile(c, "Käufer: Adresszusatz (freiwillig)", "", "fehlt"))
        v.addWidget(_zeile(c, "Käufer: Adresszeile 3 (freiwillig)", "Gebäude C", "pruefen"))
        v.addWidget(
            _zeile(
                c,
                "Käufer: Kontaktstelle (freiwillig)",
                "Frau Muster",
                "pruefen",
                "Bleibt stehen, wenn Name oder Zusatz geändert werden.",
            )
        )
    else:  # nur_vermerk
        v.addWidget(
            _zeile(
                c,
                "Käufer: Name",
                "Abteilung Einkauf",
                "pruefen",
                "BT-44: Name beginnt mit einem Vermerk („z. Hd.“, „Abteilung“ …), "
                "kein Firmenname darüber – prüfen",
            )
        )
        v.addWidget(_zeile(c, "Käufer: Adresszusatz (freiwillig)", "", "fehlt"))
        v.addWidget(_zeile(c, "Käufer: Adresszeile 3 (freiwillig)", "", "fehlt"))
        v.addWidget(_zeile(c, "Käufer: Kontaktstelle (freiwillig)", "", "fehlt"))

    v.addWidget(_zeile(c, "Käufer: Straße und Hausnummer", "Musterweg 12", "erkannt"))
    v.addWidget(_zeile(c, "Käufer: PLZ", "12345", "erkannt"))
    v.addWidget(_zeile(c, "Käufer: Ort", "Musterstadt", "erkannt"))
    v.addStretch(1)
    v.addWidget(
        lbl(
            "Skizze · nur erfundene Daten · Ziel-Knopf 48 px, Hinweis ohne Popup.",
            "sub",
            umbruch=True,
        )
    )
    return w


def main() -> None:
    app = QApplication.instance() or QApplication(["skizze-adresszusatz"])
    c = thema.anwenden(app, "hell")
    ZIEL.mkdir(parents=True, exist_ok=True)
    seiten = [
        ("voll", "kaeufer-adresszusatz.png", 720, 860),
        ("name_geaendert", "kaeufer-name-geaendert.png", 720, 900),
        ("nur_vermerk", "kaeufer-nur-vermerk.png", 720, 900),
    ]
    for variant, name, b, h in seiten:
        w = _seite(c, variant)
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
