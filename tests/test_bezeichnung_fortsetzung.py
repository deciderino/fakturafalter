# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Folgezeilen der Bezeichnung: überstehende Wörter der angelernten Preisspalte und Seitenumbruch."""

from decimal import Decimal

from fakturafalter import pdferkennung
from fakturafalter.pdferkennung import Wort, Zeile


def _w(t, x0, x1, top, seite=0):
    return Wort(t, x0, x1, top, seite, top + 10)


def _zeile(*ws):
    ws = list(ws)
    return Zeile(ws[0].seite, ws[0].top, ws, pdferkennung.abschnitte_bilden(ws))


# Schmale Bezeichnung wie nach dem Anlernen (Preisspalte beginnt früh)
PV = {
    "kopf": ["Pos", "Bezeichnung", "Menge", "Preis", "Betrag"],
    "format": "de",
    "zeilenabstand": 12,
    "spalten": {
        "BT-126": [40, 60],
        "BT-153": [70, 280],
        "BT-129": [290, 330],
        "BT-146": [340, 400],
        "gesamt": [410, 480],
    },
}


def _kopf(seite=0, top=100):
    return _zeile(
        _w("Pos", 40, 60, top, seite),
        _w("Bezeichnung", 70, 150, top, seite),
        _w("Menge", 290, 330, top, seite),
        _w("Preis", 340, 380, top, seite),
        _w("Betrag", 410, 460, top, seite),
    )


def test_ueberstand_in_preisspalte_bleibt_in_der_bezeichnung():
    """Wort am rechten Rand der Bezeichnung fällt in die angelernte Preisspalte („mit“, „auf“)."""
    zeilen = [
        _kopf(),
        _zeile(
            _w("4", 42, 50, 120),
            _w("Lagerdeckel", 70, 160, 120),
            _w("LD-62", 165, 200, 120),
            _w("mit", 348, 372, 120),
            _w("2", 300, 320, 120),
            _w("9,27", 350, 385, 120),
            _w("18,54", 420, 470, 120),
        ),
        _zeile(
            _w("Passfedernut", 70, 180, 132),
            _w("DIN", 185, 210, 132),
            _w("6885,", 215, 260, 132),
            _w("auf", 350, 375, 132),
        ),
        _zeile(
            _w("Teilkreis", 70, 150, 144),
            _w("70", 155, 175, 144),
            _w("mm", 180, 200, 144),
        ),
    ]
    pos = pdferkennung.positionen_auslesen(PV, zeilen)
    assert len(pos) == 1
    assert pos[0].menge == Decimal("2") and pos[0].einzelpreis == Decimal("9.27")
    b = pos[0].bezeichnung
    assert "Lagerdeckel LD-62 mit" in b
    assert "Passfedernut DIN 6885, auf" in b
    assert "Teilkreis 70 mm" in b


def test_seitenumbruch_setzt_bezeichnung_fort():
    """Erste Tabellenzeile der Folgeseite ohne Menge/Preis hängt an der letzten Position an."""
    zeilen = [
        _kopf(0, 400),
        _zeile(
            _w("1", 42, 50, 420),
            _w("Lagerdeckel", 70, 160, 420),
            _w("mit", 348, 372, 420),
            _w("2", 300, 320, 420),
            _w("9,27", 350, 385, 420),
            _w("18,54", 420, 470, 420),
        ),
        _zeile(_w("Übertrag", 70, 140, 700)),
        _kopf(1, 80),
        _zeile(_w("Übertrag", 70, 140, 100, 1)),
        _zeile(
            _w("Passfedernut", 70, 180, 120, 1),
            _w("DIN", 185, 210, 120, 1),
            _w("6885", 215, 255, 120, 1),
        ),
        _zeile(
            _w("2", 42, 50, 140, 1),
            _w("Lagerbock", 70, 150, 140, 1),
            _w("1", 300, 320, 140, 1),
            _w("5,00", 350, 385, 140, 1),
            _w("5,00", 420, 470, 140, 1),
        ),
    ]
    pos = pdferkennung.positionen_auslesen(PV, zeilen)
    assert len(pos) == 2
    assert "Lagerdeckel mit" in pos[0].bezeichnung
    assert "Passfedernut DIN 6885" in pos[0].bezeichnung
    assert pos[1].bezeichnung == "Lagerbock"


def test_einheit_in_preisspalte_nicht_in_bezeichnung():
    """„Stk.“/„Std.“ in der Preisspalte bleiben Einheit, sie hängen nicht an der Bezeichnung."""
    zeilen = [
        _kopf(),
        _zeile(
            _w("1", 42, 50, 120),
            _w("Rhododendron", 70, 170, 120),
            _w("Container", 175, 240, 120),
            _w("Stk.", 348, 375, 120),
            _w("3", 300, 320, 120),
            _w("12,00", 350, 385, 120),
            _w("36,00", 420, 470, 120),
        ),
        _zeile(
            _w("2", 42, 50, 136),
            _w("Aufmaß", 70, 130, 136),
            _w("Std.", 348, 375, 136),
            _w("2", 300, 320, 136),
            _w("80,00", 350, 385, 136),
            _w("160,00", 420, 470, 136),
        ),
    ]
    pos = pdferkennung.positionen_auslesen(PV, zeilen)
    assert len(pos) == 2
    assert pos[0].bezeichnung == "Rhododendron Container"
    assert pos[1].bezeichnung == "Aufmaß"
    assert "Stk." not in pos[0].bezeichnung and "Std." not in pos[1].bezeichnung


def test_betrag_mit_beiwerk_und_preiseinheit_bleiben_in_der_spalte():
    """„1,00*“ und „3,40€/10“ enthalten Ziffern: nicht in die Bezeichnung ziehen."""
    pv = {
        **PV,
        "spalten": {
            "BT-153": [70, 280],
            "BT-129": [290, 330],
            "BT-146": [340, 430],
            "gesamt": [440, 520],
        },
    }
    z1 = _zeile(
        _w("Halter", 70, 130, 120),
        _w("3", 300, 320, 120),
        _w("0,3333", 350, 400, 120),
        _w("1,00*", 450, 500, 120),
        _w("A", 505, 515, 120),
    )
    p, _, grund = pdferkennung.zeile_lesen(z1, pv)
    assert grund == "Position" and p is not None
    assert (
        p.menge == Decimal("3")
        and p.einzelpreis == Decimal("0.3333")
        and p.gesamt == Decimal("1.00")
    )
    assert "1,00*" not in p.bezeichnung and p.bezeichnung == "Halter"
    z2 = _zeile(
        _w("Splint", 70, 130, 140),
        _w("10", 300, 320, 140),
        _w("3,40€/10", 350, 430, 140),
        _w("3,40", 450, 500, 140),
    )
    p, _, grund = pdferkennung.zeile_lesen(z2, pv)
    assert grund == "Position" and p is not None
    assert p.gesamt == Decimal("3.40") and p.preiseinheit == Decimal("10")
    assert "3,40" not in p.bezeichnung
