# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""rc2: verständliche Labels bleiben, BT-Nummer grau daneben, Tooltip mit Namen im Standard, Suche nach
Käufer/Verkäufer/Buyer/Seller/BT-Nummer."""

import re

import pytest
from PySide6.QtCore import Qt

from fakturafalter import csv_einrichtung as ce


@pytest.fixture(scope="session")
def qapp():
    from fakturafalter.gui.app import anwendung

    return anwendung()


def test_jedes_bt_feld_hat_standardnamen():
    for fid in ce.FELD:
        for bt in ce.standard_bts(fid):
            assert bt in ce.STANDARD_NAME, (fid, bt)
        if fid.startswith("BT-"):
            assert fid in ce.STANDARD_NAME, fid
    # eigene Schlüssel: entweder BT-Zuordnung oder ausdrücklich „kein eigenes Feld“
    for fid in ce.FELD:
        if not fid.startswith("BT-"):
            assert fid in ce.FELD_STANDARD, fid
            assert ce.standard_zeile(fid), fid
    for bt, (de, en) in ce.STANDARD_NAME.items():
        assert re.fullmatch(r"BT-\d{1,3}", bt) and de and en


def test_tooltip_endet_mit_standard():
    assert ce.tooltip("BT-52").endswith("Im Standard: BT-52 Ort des Käufers (Buyer city)")
    assert ce.tooltip("BT-52").startswith("Ort des Kunden.")
    assert ce.FELD["BT-52"][1] == "Kunde – Ort"  # Label bleibt verständlich
    assert ce.tooltip("kundennummer").endswith("BT-46 Kennung des Käufers (Buyer identifier)")
    assert ce.standard_zeile("BT-52", "en") == "In the standard: BT-52 Buyer city"
    for fid in ce.FELD:
        assert ce.tooltip(fid).split("\n")[-1].startswith("Im Standard:"), fid


@pytest.mark.parametrize(
    ("frage", "erwartet", "nicht"),
    [
        ("Käufer", {"BT-44", "BT-52", "BT-48", "kundennummer"}, {"BT-155"}),
        ("kaeufer", {"BT-44", "BT-52"}, {"BT-155"}),
        ("Buyer", {"BT-44", "BT-52", "BT-49"}, {"BT-155"}),
        ("Verkäufer", {"BT-155"}, {"BT-44"}),
        ("Seller", {"BT-155"}, {"BT-44"}),
        ("BT-52", {"BT-52"}, set()),
        ("BT-46", {"kundennummer"}, set()),
        ("Buyer city", {"BT-52"}, {"BT-44"}),
        ("Ort des Käufers", {"BT-52"}, set()),
    ],
)
def test_suche(frage, erwartet, nicht):
    t = set(ce.suche_felder(frage, wiederholend=True))
    assert erwartet <= t, (frage, t)
    assert not (nicht & t), (frage, t)


def test_feldsuche_zeigt_bt_grau(qapp):
    from fakturafalter.gui.feldsuche import BT_ROLLE, FeldSuche

    fs = FeldSuche(wiederholend=True)
    gefunden = {}
    for i in range(fs.liste.count()):
        it = fs.liste.item(i)
        fid = it.data(Qt.ItemDataRole.UserRole)
        if fid:
            gefunden[fid] = (it.text(), it.data(BT_ROLLE), it.toolTip())
    text, bt, tip = gefunden["BT-52"]
    assert text == "Kunde – Ort" and bt == "BT-52" and tip.endswith("(Buyer city)")
    assert gefunden["kundennummer"][1] == ""
    fs.suche.setText("Buyer city")
    sichtbar = [fs.liste.item(i).data(Qt.ItemDataRole.UserRole) for i in range(fs.liste.count())]
    assert "BT-52" in sichtbar and "BT-44" not in sichtbar
    fs.liste.resize(500, 400)
    fs.liste.grab()  # Delegate zeichnet ohne Fehler


@pytest.mark.parametrize("hell", [True, False])
def test_bt_grau_kontrast(hell):
    from fakturafalter.gui import thema

    from .test_rc1_suche import _kontrast

    c = thema.farben(hell)
    assert _kontrast(c["sub"], c["base"]) >= 4.5
    assert _kontrast(c["fg"], c["sel"]) >= 4.5  # markiert: Schriftfarbe
