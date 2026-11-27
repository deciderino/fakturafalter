# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.5.0: CSV-Assistent – Format erkennen, Spalten vorschlagen, Profil schreiben (fiktive Beispieldaten)."""
from decimal import Decimal

from fakturafalter import adapter_csv, csv_einrichtung as ce
from fakturafalter.konfig import lade_datei

from .conftest import BEISPIELE


def test_format_und_vorschlag():
    a = ce.format_erkennen(BEISPIELE / "variante-a_positionen_utf8.csv")
    assert (a.trennzeichen, a.dezimal, a.tausender, a.datum) == (",", ".", "", "%Y-%m-%d")
    b = ce.format_erkennen(BEISPIELE / "variante-b_wawi_cp1252.csv")
    assert (b.trennzeichen, b.kodierung, b.dezimal, b.datum) == (";", "cp1252", ",", "%d.%m.%Y")
    assert ce.satzart(b) and not ce.satzart(a)
    z = ce.spalten_vorschlagen(a.kopf)
    assert z["BT-146"] == "einzelpreis_netto" and z["steuer"] == "steuerschluessel" and not ce.fehlende_pflicht(z)
    assert ce.steuer_vorschlag(["1", "2", "19,00", "7"]) == {"1": "prüfen", "19,00": "19 %", "2": "prüfen", "7": "7 %"}
    assert ce.einheiten_vorschlag(["Stk", "HUR", "Eimerchen"]) == {"Eimerchen": "", "HUR": "HUR", "Stk": "H87"}


def test_profil_liest_wie_handprofil(konfig, tmp_path):
    datei = BEISPIELE / "variante-a_positionen_utf8.csv"
    fmt = ce.format_erkennen(datei)
    z = ce.spalten_vorschlagen(fmt.kopf)
    p = ce.profil_bauen("Mein Export", datei, fmt, z, {"1": "19 %", "2": "7 %"},
                        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])))
    ziel = ce.speichern(p, ce.dateiname("Mein Export", tmp_path))
    assert ziel.name == "profil-mein-export.yaml"
    neu = lade_datei(ziel)
    assert adapter_csv.profil_passt(datei, neu) and ce.profil_zuordnung(neu) == z
    hand = next(pr for pr in konfig.csv_profile if pr.get("profil") == "export-utf8-komma")
    alt, jetzt = adapter_csv.lesen(datei, hand, konfig), adapter_csv.lesen(datei, neu, konfig)
    assert [r.nummer for r in jetzt] == [r.nummer for r in alt]
    for x, y in zip(alt, jetzt):
        assert [(p.menge, p.einzelpreis, p.steuer.satz) for p in x.positionen] == \
               [(p.menge, p.einzelpreis, p.steuer.satz) for p in y.positionen]
        assert y.kaeufer.name == x.kaeufer.name
        assert all(p.einheit for p in y.positionen)


def test_allgemeine_einheit_und_satzspalte(konfig, tmp_path):
    csv = tmp_path / "export.csv"
    csv.write_text("Nr;Datum;Kunde;Text;Anzahl;ME;Preis;MwSt\n"
                   "R-9;01.10.2026;Fiktiv AG;Beratung;2;Std.;80,00;19\n"
                   "R-9;01.10.2026;Fiktiv AG;Buch;1;Stück;20,00;7,00\n", encoding="utf-8")
    fmt = ce.format_erkennen(csv)
    z = ce.spalten_vorschlagen(fmt.kopf)
    assert (z["BT-1"], z["BT-44"], z["steuer"], z["BT-146"]) == ("Nr", "Kunde", "MwSt", "Preis")
    p = ce.profil_bauen("x", csv, fmt, z, ce.steuer_vorschlag(ce.spalte(fmt, "MwSt")), {})
    r = adapter_csv.lesen(csv, p, konfig)[0]
    assert [(q.einheit, q.steuer.satz) for q in r.positionen] == [("HUR", 19), ("H87", Decimal("7"))]
    assert r.kaeufer.name == "Fiktiv AG"
