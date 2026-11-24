# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Steuerbuchstaben A/B in der Positionszeile: Satz aus der Steuerzeile, sonst prüfen, nie still raten."""

from fakturafalter import pdferkennung
from fakturafalter.pdferkennung import PosRoh, Wort, Zeile


def _z(text, top=500):
    ws, x = [], 40
    for t in text.split():
        w = Wort(t, x, x + 7 * len(t), top, 0, top + 10)
        ws.append(w)
        x = w.x1 + 8
    return Zeile(0, top, ws, [ws])


def test_steuerbuchstabe_aus_summenzeile():
    assert pdferkennung.ist_steuerbuchstabe("A")
    assert pdferkennung.ist_steuerbuchstabe("B.")
    assert not pdferkennung.ist_steuerbuchstabe("19")
    assert not pdferkennung.ist_steuerbuchstabe("A19")
    zeilen = [
        _z("USt A 19 % 19,00", 500),
        _z("USt B 7 % 7,00", 515),
    ]
    m = pdferkennung.steuerbuchstaben_aus_zeilen(zeilen)
    assert m["A"]["BT-152"] == "19"
    assert m["B"]["BT-152"] == "7"


def test_steuerbuchstabe_ohne_zuordnung_nicht_steuer_fest():
    """Buchstabe in der Steuerspalte ohne Mapping: nicht den festen 19 %-Satz still zuordnen."""
    p = PosRoh(bezeichnung="Teil", menge=None, steuer_text="B")
    pv = {
        "spalten": {"steuer": [400, 420], "BT-153": [70, 200]},
        "steuer_fest": {"BT-151": "S", "BT-152": "19"},
        "steuer": {"A": {"BT-151": "S", "BT-152": "19"}},
    }
    assert pdferkennung._pos_steuer(pv, PosRoh(steuer_text="A")) == {"BT-151": "S", "BT-152": "19"}
    assert pdferkennung._pos_steuer(pv, p) is None
