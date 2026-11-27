# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""rc2: BT-Nummern und eigene Feldschlüssel als CSV-Kopf erkennen (fiktive Köpfe)."""

import pytest

from fakturafalter import csv_einrichtung as ce


@pytest.mark.parametrize(
    "kopf",
    ["BT-1", "bt1", "BT 1", "BT_1", "bt-01", "Rechnungsnummer (BT-1)", "BT-1 Rechnungsnummer", "BT-1: Nummer", " bt.1 "],
)
def test_bt1_schreibweisen(kopf):
    assert ce.bt_feld(kopf) == "BT-1"


@pytest.mark.parametrize(
    ("kopf", "feld"),
    [("BT-10", "BT-10"), ("BT-115", None), ("BT-11", "BT-11"), ("BT 100", None), ("BT-1000", None), ("Abt1", None),
     ("Debt 1", None), ("BT-1/BT-2", None), ("BT-2", "BT-2"), ("BT-46", "kundennummer"), ("BT-131", "gesamtpreis_position"),
     ("BT-152", "steuer"), ("Text", None), ("", None), ("BT", None), ("BT-999", None)],
)
def test_keine_verwechslung(kopf, feld):
    assert ce.bt_feld(kopf) == feld


def test_spalten_vorschlagen_reine_bt_kopfzeile():
    kopf = ["BT-1", "BT-2", "BT-44", "BT-153", "BT-129", "BT-146", "BT-152", "BT-130", "BT-10", "BT-115"]
    z = ce.spalten_vorschlagen(kopf)
    assert z == {
        "BT-1": "BT-1", "BT-2": "BT-2", "BT-44": "BT-44", "BT-153": "BT-153", "BT-129": "BT-129",
        "BT-146": "BT-146", "steuer": "BT-152", "BT-130": "BT-130", "BT-10": "BT-10",
    }
    assert not ce.fehlende_pflicht(z)


def test_eigene_schluessel_und_vorrang_vor_woertern():
    # „Rechnung“ würde per Wort BT-1 treffen; der BT-Kopf hat Vorrang, „Rechnung“ bleibt frei
    kopf = ["Rechnung", "Rechnungsnummer (BT-1)", "kundennummer", "gesamtpreis_position", "Datum", "Menge"]
    z = ce.spalten_vorschlagen(kopf, wiederholend=True)
    assert z["BT-1"] == "Rechnungsnummer (BT-1)"
    assert z["kundennummer"] == "kundennummer"
    assert z["gesamtpreis_position"] == "gesamtpreis_position"
    assert z["BT-2"] == "Datum" and z["BT-129"] == "Menge"
    assert "Rechnung" not in z.values()


def test_bt44_mit_nummernwerten_bleibt_name():
    kopf = ["BT-1", "BT-44"]
    zeilen = [["RE-1", "K-1001"], ["RE-2", "K-1002"]]
    z = ce.spalten_vorschlagen(kopf, zeilen)
    assert z["BT-44"] == "BT-44" and "kundennummer" not in z


def test_jede_spalte_hoechstens_einmal():
    z = ce.spalten_vorschlagen(["BT-1", "bt1", "Menge"])
    assert z["BT-1"] == "BT-1" and list(z.values()).count("bt1") == 0
    assert len(set(z.values())) == len(z)


def test_bloecke_kopfzeile_mit_bt():
    from fakturafalter import csv_bloecke

    namen = ce.synonym_namen()
    assert csv_bloecke.ist_kopfzeile(["Rechnungsnummer (BT-1)", "BT-2 Datum", "x"], namen, 2)
    assert csv_bloecke.ist_kopfzeile(["BT-153", "BT-129"], namen, 2)
    assert not csv_bloecke.ist_kopfzeile(["BT-999", "Debt1x", "Schraube"], namen, 2)
    assert not csv_bloecke.ist_kopfzeile(["RE-1", "12.11.2026", "Schraube"], namen, 2)
    assert ce.typ_vorschlag(["BT-153", "BT-129", "BT-146"]) == "positionen"


def test_e2e_bt_kopf_csv(konfig, tmp_path):
    """CSV mit reinen BT-Köpfen → Vorschlag → Profil → Rechnung (fiktive Daten)."""
    from decimal import Decimal

    from fakturafalter import adapter_csv

    csv = tmp_path / "bt-export.csv"
    csv.write_text(
        "BT-1;bt2;BT 44;BT_153;Menge (BT-129);BT-130;BT-146 Preis;BT-152\n"
        "R-77;01.10.2026;Fiktiv AG;Beratung;2;Std.;80,00;19\n"
        "R-77;01.10.2026;Fiktiv AG;Buch;1;Stück;20,00;7\n",
        encoding="utf-8",
    )
    fmt = ce.format_erkennen(csv)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    assert not ce.fehlende_pflicht(z)
    p = ce.profil_bauen("bt", csv, fmt, z, ce.steuer_vorschlag(ce.spalte(fmt, "BT-152")),
                        ce.einheiten_vorschlag(ce.spalte(fmt, "BT-130")))
    (r,) = adapter_csv.lesen(csv, p, konfig)
    assert r.nummer == "R-77" and r.kaeufer.name == "Fiktiv AG"
    assert [(q.menge, q.einzelpreis, q.steuer.satz) for q in r.positionen] == [
        (Decimal("2"), Decimal("80.00"), Decimal("19")), (Decimal("1"), Decimal("20.00"), Decimal("7"))]
