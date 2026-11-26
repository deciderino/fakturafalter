# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.9.8.2: fehlende Profildateien dürfen Speichern nicht abbrechen; gelöscht bleibt gelöscht."""

import os
import shutil
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from fakturafalter.konfig import csv_eintrag_datei, lade_konfig  # noqa: E402

from .test_gui import BEISPIELE, fenster, konfig_datei, qapp  # noqa: F401


def test_lade_konfig_ueberspringt_fehlende_csv_und_vorlage(tmp_path):
    cfg = tmp_path / "cfg"
    shutil.copytree(BEISPIELE, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["csv_profile"] = list(d["csv_profile"]) + ["gibt-es-nicht.yaml"]
    d["pdf_vorlagen"] = list(d.get("pdf_vorlagen") or []) + ["vorlage-fehlt.yaml"]
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    k = lade_konfig(cfg / "konfiguration.yaml")
    assert "gibt-es-nicht.yaml" not in [
        csv_eintrag_datei(p) for p in k.roh.get("csv_profile") or []
    ]
    assert all(Path(p["_datei"]).is_file() for p in k.csv_profile)
    assert len(k.csv_profile) >= 1
    assert "vorlage-fehlt.yaml" not in (k.roh.get("pdf_vorlagen") or [])
    assert k.pdf_vorlagen  # die vorhandene Vorlage bleibt


def test_einstellungen_uebernehmen_bei_fehlender_profildatei(fenster, qapp, konfig_datei):
    """Früher: FileNotFoundError, Toast, Rollback – die gelöschten Einträge kamen zurück."""
    vorher = list(fenster.k.roh.get("csv_profile") or [])
    assert vorher
    roh = yaml.safe_load(yaml.safe_dump(fenster.k.roh))
    roh["csv_profile"] = list(roh["csv_profile"]) + ["fehlt-windows.yaml"]
    assert fenster.einstellungen_uebernehmen(roh)
    namen = [csv_eintrag_datei(p) for p in fenster.k.roh.get("csv_profile") or []]
    assert "fehlt-windows.yaml" not in namen
    assert namen == [csv_eintrag_datei(p) for p in vorher]
    fest = yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))
    assert "fehlt-windows.yaml" not in [csv_eintrag_datei(p) for p in fest.get("csv_profile") or []]


def test_geloeschtes_beispielprofil_bleibt_weg(fenster, qapp, konfig_datei, monkeypatch):
    from fakturafalter.gui.einstellungen import Einstellungen

    assert len(fenster.k.csv_profile) >= 2
    datei = Path(fenster.k.csv_profile[0]["_datei"])
    name = datei.name
    assert datei.is_file()
    monkeypatch.setattr(
        "fakturafalter.gui.einstellungen.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    d = Einstellungen(fenster, "Eingang & Vorlagen")
    d._csv_loeschen(0)
    qapp.processEvents()
    assert not datei.exists()
    assert name not in [csv_eintrag_datei(e) for e in d._csv_eintraege()]
    roh = d.ergebnis()
    d.reject()
    assert fenster.einstellungen_uebernehmen(roh)
    assert name not in [csv_eintrag_datei(p) for p in fenster.k.roh.get("csv_profile") or []]
    assert all(Path(p["_datei"]).name != name for p in fenster.k.csv_profile)
    fest = yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))
    assert name not in [csv_eintrag_datei(p) for p in fest.get("csv_profile") or []]


def _assistent_bis_probe(fenster, qapp, profil, csv):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster, profil)
    d.datei_setzen(csv)
    d.name.setText(str(profil.get("profil") or "MeinProfil"))
    qapp.processEvents()
    probe = next(i for i, (st, _n) in enumerate(d._folge()) if st == 5)
    d.gehe(probe)
    qapp.processEvents()
    return d


def test_assistent_speichert_geaendertes_profil(fenster, qapp):
    """Auch unter Linux: ein bestehendes eigenes Profil lässt sich im letzten Schritt speichern."""
    prof = next(p for p in fenster.k.csv_profile if p.get("profil") == "export-utf8-komma")
    d = _assistent_bis_probe(fenster, qapp, prof, BEISPIELE / "variante-a_positionen_utf8.csv")
    assert d.t_probe.rowCount() >= 1
    ziel = d.speichern()
    assert ziel and ziel.exists() and d.gespeichert == ziel
    d.b_weiter.click()  # nach erfolgreichem Speichern weiter auf „Fertig“
    qapp.processEvents()
    assert d.i == d._folge()[-1][0] or d.gespeichert
    d.reject()


def test_assistent_speichert_trotz_fehlender_fremder_profildatei(fenster, qapp, konfig_datei):
    """Genau der Windows-Fall: andere (mitgelieferte) Dateien fehlen, eigenes Profil ändern."""
    roh = yaml.safe_load(yaml.safe_dump(fenster.k.roh))
    roh["csv_profile"] = list(roh["csv_profile"]) + ["profil-variante-verschwunden.yaml"]
    assert fenster.einstellungen_uebernehmen(roh)
    assert "profil-variante-verschwunden.yaml" not in [
        csv_eintrag_datei(p) for p in fenster.k.roh.get("csv_profile") or []
    ]
    # Eintrag erneut in die gespeicherte Liste mischen, als hätte die Datei
    # zwischenzeitlich gefehlt, während die App schon lief.
    fenster.k.roh.setdefault("csv_profile", []).append("profil-variante-verschwunden.yaml")
    prof = next(p for p in fenster.k.csv_profile if p.get("profil") == "export-utf8-komma")
    d = _assistent_bis_probe(fenster, qapp, prof, BEISPIELE / "variante-a_positionen_utf8.csv")
    ziel = d.speichern()
    assert ziel and ziel.exists()
    namen = [csv_eintrag_datei(p) for p in fenster.k.roh.get("csv_profile") or []]
    assert "profil-variante-verschwunden.yaml" not in namen
    d.reject()
