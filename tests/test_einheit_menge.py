# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Einheit aus der Mengenzelle lesen; ohne lesbare Einheit und ohne Spalte kein stilles H87."""

from decimal import Decimal

from fakturafalter import pdferkennung
from fakturafalter.pdferkennung import Wort, Zeile


def _zeile(*zellen: tuple[str, float, float]) -> Zeile:
    ws = [Wort(t, x0, x1, 100, 0, 110) for t, x0, x1 in zellen]
    return Zeile(0, 100, ws, [ws])


def _pv(*spalten: tuple[str, float, float], **extra) -> dict:
    return {"spalten": {n: (a, b) for n, a, b in spalten}, "format": "de", **extra}


SPALTEN = (
    ("BT-153", 10, 200),
    ("BT-129", 210, 280),
    ("BT-146", 290, 370),
    ("gesamt", 380, 460),
)


def test_einheit_aus_mengenzelle_std_und_stk():
    pv = _pv(*SPALTEN)
    z = _zeile(
        ("Wartung", 10, 180),
        ("12 Std.", 210, 270),
        ("80,00", 300, 360),
        ("960,00", 390, 450),
    )
    p, _, grund = pdferkennung.zeile_lesen(z, pv)
    assert grund == "Position" and p is not None
    assert p.menge == Decimal("12") and p.einheit_text == "Std."
    assert pdferkennung.einheit_code(p.einheit_text) == "HUR"
    sch = pdferkennung.einheit_schluessel(pv, p)
    assert sch == "Std."
    assert pdferkennung.einheiten_mapping(pv, [sch])["Std."] == "HUR"

    z2 = _zeile(
        ("Dichtung", 10, 180),
        ("3 Stk", 210, 270),
        ("2,10", 300, 360),
        ("6,30", 390, 450),
    )
    p2, _, _ = pdferkennung.zeile_lesen(z2, pv)
    assert p2 and p2.menge == Decimal("3") and p2.einheit_text == "Stk"
    assert pdferkennung.einheit_code(p2.einheit_text) == "H87"

    z3 = _zeile(
        ("Mutter", 10, 180),
        ("5000", 210, 250),
        ("Stk", 252, 275),
        ("1,90", 300, 360),
        ("95,00", 390, 450),
    )
    p3, _, _ = pdferkennung.zeile_lesen(z3, pv)
    assert p3 and p3.menge == Decimal("5000") and p3.einheit_text == "Stk"


def test_ohne_einheit_und_ohne_spalte_bleibt_h87():
    """Ohne lesbare Einheit bleibt H87 (Messregel: Soll-H87 ohne Druck sonst nicht mehr „richtig“)."""
    pv = _pv(*SPALTEN)
    z = _zeile(
        ("Dichtung", 10, 180),
        ("3", 210, 240),
        ("2,10", 300, 360),
        ("6,30", 390, 450),
    )
    p, _, _ = pdferkennung.zeile_lesen(z, pv)
    assert p and p.menge == Decimal("3") and p.einheit_text == ""
    assert pdferkennung.einheit_ohne_spalte([p]) == {"einheit_fest": "H87"}


def test_einheitenspalte_bleibt_massgeblich():
    """Mandantenlayout: Einheit kommt aus der Spalte, nicht aus der Mengenzelle."""
    pv = _pv(*SPALTEN, ("BT-130", 282, 320))
    # Spalte nach der Menge, vor dem Preis
    pv["spalten"]["BT-146"] = (330, 390)
    pv["spalten"]["gesamt"] = (400, 460)
    z = _zeile(
        ("Wartung", 10, 180),
        ("12", 210, 240),
        ("Stk.", 285, 315),
        ("80,00", 340, 385),
        ("960,00", 410, 450),
    )
    p, _, _ = pdferkennung.zeile_lesen(z, pv)
    assert p and p.menge == Decimal("12") and p.einheit_text == "Stk."
    assert pdferkennung.einheit_code(p.einheit_text) == "H87"


def test_einheit_ragt_in_die_einzelpreisspalte():
    """Menge rechtsbündig am Spaltenrand, Einheit dahinter in der Einzelpreisspalte („2,00 Stunden“, Spalten vom
    Kopf geschnitten): Einheit gehört zur Menge, die Zeile ist eine Position."""
    pv = _pv(*SPALTEN)
    z = _zeile(
        ("Einrichtung", 10, 120),
        ("2,00", 262, 279),
        ("Stunden", 282, 315),
        ("97,25", 340, 362),
        ("194,50", 420, 450),
    )
    p, _, grund = pdferkennung.zeile_lesen(z, pv)
    assert grund == "Position" and p is not None
    assert (p.menge, p.einzelpreis, p.einheit_text) == (
        Decimal("2.00"),
        Decimal("97.25"),
        "Stunden",
    )
    assert pdferkennung.einheit_code(p.einheit_text) == "HUR"


def test_einheit_ragt_in_die_bezeichnungsspalte():
    """„1 Stk.“ in einer Mengenspalte, die nur so breit wie die Zahlen gelernt ist: „Stk.“ gehört zur Menge,
    nicht an den Anfang der Bezeichnung."""
    pv = _pv(("BT-129", 10, 20), ("BT-153", 28, 200), ("BT-146", 290, 370), ("gesamt", 380, 460))
    z = _zeile(
        ("1", 10, 15),
        ("Stk.", 18, 44),
        ("Fahrtkosten", 60, 110),
        ("Pauschale", 113, 150),
        ("35,75", 340, 362),
        ("35,75", 430, 450),
    )
    p, _, grund = pdferkennung.zeile_lesen(z, pv)
    assert grund == "Position" and p is not None
    assert (p.bezeichnung, p.einheit_text) == ("Fahrtkosten Pauschale", "Stk.")
