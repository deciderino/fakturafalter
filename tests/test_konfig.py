# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Konfiguration: ein Arbeitsordner mit automatischen Unterordnern, alte Einzelordner, Nur-PDF-Profile."""
from pathlib import Path

import yaml

from fakturafalter.gui import orte
from fakturafalter.konfig import gemeinsamer_ordner, lade_konfig


def _schreiben(p: Path, d: dict) -> Path:
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return p


def test_arbeitsordner_mit_unterordnern(tmp_path):
    k = lade_konfig(_schreiben(tmp_path / "k.yaml", {"arbeitsordner": "Rechnungen"}))
    assert k.eingang == tmp_path / "Rechnungen" / "Eingang"
    assert k.pruefen == tmp_path / "Rechnungen" / "Pruefen"
    assert k.anlernen == tmp_path / "Rechnungen" / "Pruefen" / "Anlernen"
    assert k.arbeitsordner == tmp_path / "Rechnungen"
    k.ordner_anlegen()
    assert k.protokoll == tmp_path / "Rechnungen" / "Protokoll"   # ab 0.9.6, sichtbar, nicht im Ausgang
    assert sorted(p.name for p in (tmp_path / "Rechnungen").iterdir()) == \
        ["Ausgang", "Eingang", "Erledigt", "Fehler", "Protokoll", "Pruefen"]


def test_alte_einzelordner_bleiben_gueltig(tmp_path):
    alt = {"ordner": {"eingang": "a/Eingang", "ausgang": "a/Ausgang", "erledigt": "a/Erledigt",
                      "fehler": "a/Fehler", "pruefen": "a/Pruefen"}}
    k = lade_konfig(_schreiben(tmp_path / "k.yaml", alt))
    assert k.ausgang == tmp_path / "a" / "Ausgang"
    assert k.arbeitsordner == tmp_path / "a"            # alle Standardnamen -> einfacher Modus möglich
    alt["ordner"]["fehler"] = "/anderswo/Fehler"
    k = lade_konfig(_schreiben(tmp_path / "k.yaml", alt))
    assert k.fehler == Path("/anderswo/Fehler") and k.arbeitsordner is None


def test_einzelner_ordner_geht_vor_arbeitsordner(tmp_path):
    k = lade_konfig(_schreiben(tmp_path / "k.yaml", {"arbeitsordner": "R", "ordner": {"ausgang": "/srv/aus"}}))
    assert k.ausgang == Path("/srv/aus") and k.eingang == tmp_path / "R" / "Eingang"
    assert gemeinsamer_ordner({"eingang": tmp_path / "R" / "Eingang"}) is None


def test_erststart_schreibt_arbeitsordner(tmp_path):
    pfad = orte.erststart(tmp_path / "daten", arbeitsordner=tmp_path / "Fakturafalter")
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    assert roh["arbeitsordner"] == str(tmp_path / "Fakturafalter") and "ordner" not in roh
    assert (tmp_path / "Fakturafalter" / "Eingang").is_dir()
    k = lade_konfig(pfad)
    assert k.erledigt == tmp_path / "Fakturafalter" / "Erledigt"


def test_nur_pdf_profile(tmp_path):
    _schreiben(tmp_path / "profil-x.yaml", {"profil": "x", "verkaeufer": {"name": "X GmbH"}})
    k = lade_konfig(_schreiben(tmp_path / "k.yaml", {"pdf_profile": ["profil-x.yaml"], "modus": "nur_pdf"}))
    assert [p["quelle"] for p in k.pdf_profile] == ["pdf"] and not k.csv_profile
    assert k.profile == k.pdf_profile and k.modus == "nur_pdf"


def test_modus_migration_alt_und_neu(tmp_path):
    from fakturafalter.konfig import modus_und_pdf

    assert modus_und_pdf({"modus": "pdf_csv"}) == ("csv", True)
    assert modus_und_pdf({"modus": "pdf_xml"}) == ("xml", True)
    opt = {"pdf_verwenden": False}
    assert modus_und_pdf({"modus": "pdf_csv", "optionen": opt}) == ("csv", False)
    assert modus_und_pdf({"modus": "csv"}) == ("csv", False)
    assert modus_und_pdf({"modus": "xml", "optionen": {"pdf_verwenden": True}}) == ("xml", True)
    assert modus_und_pdf({"modus": "nur_pdf"}) == ("nur_pdf", False)
    # Bestehende Datei ohne modus: bisheriger Lauf (pdf_csv) bleibt.
    assert modus_und_pdf({}) == ("csv", True)
    assert modus_und_pdf({"optionen": {"pdf_verwenden": False}}) == ("csv", False)

    alt = {"modus": "pdf_xml", "optionen": {"gegenstueck_minuten": 7}}
    k = lade_konfig(_schreiben(tmp_path / "alt.yaml", alt))
    assert k.modus == "xml" and k.pdf_verwenden is True and k.gegenstueck_minuten == 7
    k = lade_konfig(_schreiben(tmp_path / "neu.yaml", {"modus": "csv"}))
    assert k.modus == "csv" and k.pdf_verwenden is False


def test_bestehende_modi_bleiben_beim_laden(tmp_path):
    """Gespeicherte Werte inkl. alter Aliase ändern sich beim Laden nicht."""
    k = lade_konfig(_schreiben(tmp_path / "np.yaml", {"modus": "nur_pdf"}))
    assert k.modus == "nur_pdf" and k.pdf_verwenden is False
    k = lade_konfig(_schreiben(tmp_path / "alt.yaml", {"modus": "pdf_csv"}))
    assert k.modus == "csv" and k.pdf_verwenden is True
    k = lade_konfig(_schreiben(tmp_path / "ohne.yaml", {"absender": {"name": "Alt GmbH"}}))
    assert k.modus == "csv" and k.pdf_verwenden is True


def test_startkonfiguration_ist_csv_ohne_haken(tmp_path):
    pfad = orte.erststart(tmp_path / "cfg", tmp_path / "Arbeit")
    k = lade_konfig(pfad)
    assert k.modus == "csv" and k.pdf_verwenden is False
    roh = yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))
    assert roh["modus"] == "csv"
    assert roh["optionen"]["pdf_verwenden"] is False
