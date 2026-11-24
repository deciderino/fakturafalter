# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Seitenzahl und „Anzahl Seiten“ nicht als Brutto (BT-112) lesen."""

from fakturafalter import pdferkennung
from fakturafalter.pdferkennung import Wort, Zeile


def _z(*teile, top=100, seite=0):
    ws, x = [], 40
    for txt in teile:
        w = Wort(txt, x, x + 7 * len(txt), top, seite, top + 10)
        ws.append(w)
        x = w.x1 + 8
    return Zeile(seite, top, ws, [ws])


def test_seitenzahl_und_anzahl_seiten_nicht_als_bt112():
    zeilen = [
        _z("Rechnungsbetrag", "119,00", top=400),
        _z("Seite", "2", "von", "3", top=780),
        _z("Anzahl", "Seiten:", "2", top=800),
    ]
    assert pdferkennung._ist_seitenzahl(zeilen[1])
    assert pdferkennung._druckwert_suchen("BT-112", zeilen, None) == "119.00"
