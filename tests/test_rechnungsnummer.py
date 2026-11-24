# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""BT-1 nicht aus Telefon-/Vorwahl oder Artikel-/Positionsnummer lesen."""

from fakturafalter import pdferkennung
from fakturafalter.pdferkennung import Wort, Zeile


def _z(*teile, top=100):
    ws, x = [], 40
    for txt in teile:
        w = Wort(txt, x, x + 7 * len(txt), top, 0, top + 10)
        ws.append(w)
        x = w.x1 + 12
    # Abschnitte: jede Beschriftung+Wert-Gruppe getrennt, hier jedes Paar
    return Zeile(0, top, ws, pdferkennung.abschnitte_bilden(ws))


def test_telefon_und_artikelnr_nicht_als_bt1():
    zeilen = [
        _z("Telefonnr.", "0421 000000-0", top=80),
        _z("Art.-Nr.", "64-4728", top=100),
        _z("Pos.", "4", top=200),
        _z("Rechnungsnr.", "103603", top=120),
    ]
    assert pdferkennung._ist_telefonnummer("0421 000000-0")
    assert not pdferkennung._ist_telefonnummer("103603")
    assert pdferkennung._druckwert_suchen("BT-1", zeilen, None) == "103603"


def test_bt13_schluessel_unveraendert():
    """Bestellnummer (BT-13) bleibt von der BT-1-Negativliste unberührt."""
    pos, neg, _ = pdferkennung.SCHLUESSELWOERTER["BT-13"]
    assert "bestell" in pos and "telefon" not in neg
    zeilen = [_z("Bestellnr.", "AB-9001", top=90)]
    assert pdferkennung._druckwert_suchen("BT-13", zeilen, None).replace("\u00a0", " ") == "AB-9001"
