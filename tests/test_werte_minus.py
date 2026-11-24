# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Nachgestelltes Minus („10,00-“) ist ein negativer Betrag – bereits in werte.zahl und pdferkennung."""

from decimal import Decimal

from fakturafalter.pdferkennung import betraege, zahlen
from fakturafalter.werte import zahl


def test_nachgestelltes_minus_ist_negativ():
    assert zahl("10,00-") == Decimal("-10.00")
    assert zahl("10,00 -") == Decimal("-10.00")
    assert zahl("1.234,56-") == Decimal("-1234.56")
    assert zahlen("10,00-")[0][0] == Decimal("-10.00")
    assert betraege("1.234,56-")[0][0] == Decimal("-1234.56")
    assert zahlen("-10,00")[0][0] == Decimal("-10.00")
