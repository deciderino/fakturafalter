# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""1.0.0-rc1: „Feld suchen …“, gruppierte Liste in beiden Assistentenwegen (nur fiktive Daten)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from fakturafalter import csv_einrichtung as ce

from .test_gui import BEISPIELE, fenster, konfig_datei, qapp, warten  # noqa: F401 – Fixtures

ERWARTET = {
    "gesamtpreis": "gesamtpreis_position",
    "ustsatz": "steuer",
    "belegname": "BT-1",
    "kundenbezeichnung": "BT-44",
    "lieferdatum": "BT-72",
    "preisbasis": "BT-149",
}


def _sichtbare_ids(fs) -> list[str]:
    aus = []
    for i in range(fs.liste.count()):
        v = fs.liste.item(i).data(Qt.ItemDataRole.UserRole)
        if v:
            aus.append(str(v))
    return aus


@pytest.mark.parametrize("frage,fid", sorted(ERWARTET.items()))
def test_suche_trifft_feld(qapp, frage, fid):
    from fakturafalter.gui.feldsuche import FeldSuche

    fs = FeldSuche(wiederholend=True)
    fs.suche.setText(frage)
    ids = _sichtbare_ids(fs)
    assert ids and ids[0] == fid, (frage, ids)
    # Enter wählt den ersten Treffer
    gewaehlt = []
    fs.geaendert.connect(gewaehlt.append)
    QTest.keyClick(fs.suche, Qt.Key.Key_Return)
    assert gewaehlt == [fid]
    assert fs.feld() == fid


def test_suche_gruppen_nicht_waehlbar_und_nicht_verwenden_oben(qapp):
    from fakturafalter.gui.feldsuche import FeldSuche

    fs = FeldSuche(wiederholend=True)
    erst = fs.liste.item(0)
    assert erst.data(Qt.ItemDataRole.UserRole) == ""  # „– nicht verwenden –“
    koepfe = [
        fs.liste.item(i).text()
        for i in range(fs.liste.count())
        if not (fs.liste.item(i).flags() & Qt.ItemFlag.ItemIsSelectable)
    ]
    assert koepfe[0] == "Position"
    assert koepfe == [ce.GRUPPE_TITEL[g] for g in ce.GRUPPE_REIHENFOLGE]
    # Suche filtert Gruppen ohne Treffer weg, „nicht verwenden“ bleibt
    fs.suche.setText("gesamtpreis")
    koepfe2 = [
        fs.liste.item(i).text()
        for i in range(fs.liste.count())
        if not (fs.liste.item(i).flags() & Qt.ItemFlag.ItemIsSelectable)
    ]
    assert "Lieferung" not in koepfe2 and "Position" in koepfe2
    assert fs.liste.item(0).data(Qt.ItemDataRole.UserRole) == ""
    # Escape leert die Suche
    QTest.keyClick(fs.suche, Qt.Key.Key_Escape)
    assert fs.suche.text() == ""
    # normaler Block: keine Positionsgruppe
    fs2 = FeldSuche(wiederholend=False)
    assert "gesamtpreis_position" not in _sichtbare_ids(fs2)
    assert "BT-1" in _sichtbare_ids(fs2)


def test_liste_pflichtstern_und_bt_nur_amtlich():
    for fid, (_i, label, _t, _ty, pflicht) in ce.FELD.items():
        z = ce.anzeige_feld(fid)
        assert ("*" in z) == pflicht, z
        if fid.startswith("BT-"):
            assert z.endswith(f"({fid})"), z
        else:
            assert "(BT-" not in z and fid not in z.replace(label, ""), z
    assert all(f in ce.FELD_TOOLTIP for f in ce.FELD), "jedes Feld braucht einen Tooltip"


def test_pflichtkarte_dieselben_woerter_wie_liste():
    fehlt = ce.fehlende_pflicht({})
    labels = {ce.FELD[f][1] for f in ce.FELD if ce.FELD[f][4]}
    assert set(fehlt) == labels
    assert "Kundenname (Zeile 1)" in fehlt and "Kundennummer" not in " ".join(fehlt)


@pytest.mark.parametrize(
    "kopf,wdh,feld",
    [
        (["Gesamtpreis"], True, "gesamtpreis_position"),
        (["Preisbasis"], True, "BT-149"),
        (["Ust-Satz"], True, "steuer"),
        (["Belegname"], False, "BT-1"),
        (["Kundenbezeichnung 1"], False, "BT-44"),
        (["Lieferdatum"], False, "BT-72"),
        (["Gesamtnetto"], True, "gesamtpreis_position"),
        (["Gesamtnetto"], False, "BT-109"),
        (["Rabatt%"], True, "BT-138"),
    ],
)
def test_automatik_spaltennamen(kopf, wdh, feld):
    assert ce.spalten_vorschlagen(kopf, wiederholend=wdh) == {feld: kopf[0]}


def test_automatik_rabatt_allein_nicht_prozent():
    assert "BT-138" not in ce.spalten_vorschlagen(["Rabatt"], wiederholend=True)
    assert "BT-112" not in ce.spalten_vorschlagen(["Gesamtpreis"], wiederholend=True)


def test_eine_zeile_je_position_hat_suche_und_gruppen(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(BEISPIELE / "variante-a_positionen_utf8.csv")
    d.name.setText("Suche-Test")
    d.b_weiter.click()
    qapp.processEvents()
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 2
    b = d.spalten[0]
    # Gruppenköpfe in der Spaltenauswahl sind nicht wählbar
    gesperrt = [
        b.itemText(i) for i in range(b.count()) if not b.model().item(i).isEnabled()
    ]
    assert gesperrt[0] == "Position" and "Kunde / Käufer" in gesperrt
    # Spalte wählen, über die Suche zuordnen
    leer = next(j for j, x in enumerate(d.spalten) if not x.currentData())
    d._map_spalte_waehlen(leer)
    assert d._map_spalte == leer and d.box_feldsuche.isVisibleTo(d)
    d.map_suche.suche.setText("belegnr")
    QTest.keyClick(d.map_suche.suche, Qt.Key.Key_Return)
    qapp.processEvents()
    assert d.spalten[leer].currentData() == "BT-1"
    # die frühere Spalte mit BT-1 ist frei geworden (jedes Feld nur einmal)
    assert [x.currentData() for x in d.spalten].count("BT-1") == 1
    d.close()


def _kontrast(a: str, b: str) -> float:
    def lum(h):
        h = h.lstrip("#")
        rgb = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("hell", [True, False])
def test_listen_und_tabellen_wcag_aa(hell):
    """rc1: Listen/Tabellen (Feldsuche, XRechnung-Liste, Spaltenzuordnung) haben im Stylesheet eigene
    Farben – auch im dunklen Thema bei hellem System – und erreichen WCAG AA (4,5:1)."""
    from fakturafalter.gui import thema

    c = thema.farben(hell)
    css = thema.css(c)
    assert "QAbstractItemView" in css and "QHeaderView::section" in css
    for vg, hg in (("fg", "base"), ("fg", "sel"), ("fg", "btn"), ("fg", "card"), ("sub", "base"), ("gut_t", "card"), ("warn_t", "card")):
        assert _kontrast(c[vg], c[hg]) >= 4.5, (hell, vg, hg, round(_kontrast(c[vg], c[hg]), 2))
