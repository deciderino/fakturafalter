# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.9.11.1: Blockspalten nach YAML neu laden wie im Eingang; Währung und Blockname."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml

pytest.importorskip("PySide6")

from fakturafalter import adapter_csv
from fakturafalter import csv_einrichtung as ce

from .test_gui import fenster, konfig_datei, qapp  # noqa: F401

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
FIKTIV = BEISPIELE / "beispiel-satzart-marker-in-spalte.csv"

def _hinweise(r) -> list[str]:
    return [str(h) for h in r.hinweise]


def test_assistent_yaml_eingang_gleiche_spalten(fenster, qapp, tmp_path):
    """Echter Assistenten-Speicherweg: YAML schreiben, neu laden, Eingang = Probe."""
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(FIKTIV)
    d.name.setText("fiktiv-09111")
    qapp.processEvents()
    for _ in range(6):
        folge = d._folge()
        if folge[d.i][0] == 4 and getattr(d, "c_einheit_fehlt_stueck", None):
            d.c_einheit_fehlt_stueck.setChecked(True)
        d.b_weiter.click()
        qapp.processEvents()
    assert d._folge()[d.i][0] == 5  # Probe
    p = d.profil()
    assert (p.get("aufbau") or {}).get("art") == "bloecke"
    assert not p.get("felder")
    typen = [b.get("typ") for b in p["bloecke"]]
    assert typen == ["kunde", "beleg", "positionen", "summen"]
    beleg = next(b for b in p["bloecke"] if b["id"] == "beleg")
    assert beleg["felder"]["BT-1"]["spalte"] == "Belegname"
    pos = next(b for b in p["bloecke"] if b.get("wiederholend"))
    assert pos["felder"]["BT-130"]["spalte"] == "Einheit"

    ziel = tmp_path / "profil-fiktiv-09111.yaml"
    ce.speichern(p, ziel)
    geladen = yaml.safe_load(ziel.read_text(encoding="utf-8"))

    rs_probe = adapter_csv.lesen(FIKTIV, p, fenster.k)
    rs_yaml = adapter_csv.lesen(FIKTIV, geladen, fenster.k)
    geladen["_datei"] = str(ziel)
    geladen["_basis"] = str(ziel.parent)
    _gew, rs_ein = adapter_csv.lesen_mit_auswahl(FIKTIV, [geladen], fenster.k)
    assert len(rs_probe) == len(rs_yaml) == len(rs_ein) == 1
    a, b, c = rs_probe[0], rs_yaml[0], rs_ein[0]
    assert a.nummer == b.nummer == c.nummer == "784395789"
    assert (a.kaeufer.name or "").startswith("Testkunde")
    assert b.kaeufer.name == a.kaeufer.name
    assert len(a.positionen) == len(b.positionen) == 2
    assert a.positionen[0].einheit and a.positionen[1].einheit
    assert a.waehrung == "EUR"
    for r in (a, b, c):
        txt = " ".join(_hinweise(r))
        assert "Spalte" not in txt or "fehlt" not in txt, txt
        assert "kopf“ und „kopf" not in txt
    # Probe-Liste und Lesen: dieselben Nicht-Info-Hinweise (ohne Profil-Präfix)
    erg = ce.probe_csv(FIKTIV, geladen, fenster.k)
    assert erg[0].nummer == "784395789"
    d.reject()


def test_waehrung_euro_zeichen_und_fest_ohne_kollision(konfig, tmp_path):
    """fest EUR in Kunde und Spalte „€“ im Beleg sind dieselbe Währung; Meldung mit freiem Namen."""
    csv = tmp_path / "fiktiv-waehrung.csv"
    text = FIKTIV.read_text(encoding="utf-8").replace(";EUR", ";€")
    csv.write_text(text, encoding="utf-8")
    fmt = ce.format_erkennen(csv)
    bloecke, sa = ce.bloecke_vorschlagen(fmt)
    zu: dict[str, dict[str, str]] = {}
    for b in bloecke:
        if b.get("kopf"):
            v = ce.spalten_vorschlagen(list(b["kopf"]), [r for _n, r in b.get("daten") or []])
            if not b.get("wiederholend"):
                v = {f: s for f, s in v.items() if f not in ce.positionsfelder()}
            zu[b.get("id") or b["typ"]] = v
    profil = ce.profil_bauen_bloecke(
        "fiktiv-waehrung", csv, fmt, bloecke, zu, {}, {}, {}, None, sa
    )
    # wie ein älteres 0.9.11-Profil: fest EUR zusätzlich in jedem Block
    for b in profil["bloecke"]:
        if b.get("typ") in ("kunde", "beleg", "positionen") or b.get("wiederholend"):
            b["felder"].setdefault("BT-5", {"fest": "EUR"})
            b["felder"].setdefault("BT-3", {"fest": "380"})
    (r,) = adapter_csv.lesen(csv, profil, konfig)
    assert r.nummer == "784395789"
    assert r.waehrung == "EUR"
    txt = " ".join(_hinweise(r))
    assert "Währung" not in txt or "weicht" not in txt, txt
    assert "Spalte" not in txt or "fehlt" not in txt


def test_alte_typ_kopf_profile_ueber_kopfzeile_repariert(konfig):
    """Bestehendes Profil mit typ=kopf für Kunde und Beleg wird über die Kopfzeile richtig gelesen."""
    fmt = ce.format_erkennen(FIKTIV)
    bloecke, sa = ce.bloecke_vorschlagen(fmt)
    zu: dict[str, dict[str, str]] = {}
    for b in bloecke:
        if b.get("kopf"):
            v = ce.spalten_vorschlagen(list(b["kopf"]), [r for _n, r in b.get("daten") or []])
            if not b.get("wiederholend"):
                v = {f: s for f, s in v.items() if f not in ce.positionsfelder()}
            zu[b.get("id") or b["typ"]] = v
    profil = ce.profil_bauen_bloecke(
        "fiktiv-typ-kopf", FIKTIV, fmt, bloecke, zu, {}, {}, {}, None, sa
    )
    for b in profil["bloecke"]:
        if b.get("typ") in ("kunde", "beleg"):
            b["typ"] = "kopf"
            b["name"] = "kopf"
            # id bleibt eindeutig (kunde / beleg)
    (r,) = adapter_csv.lesen(FIKTIV, profil, konfig)
    assert r.nummer == "784395789"
    assert r.datum is not None
    txt = " ".join(_hinweise(r))
    assert "Spalte „Belegname“ fehlt" not in txt
    assert "Spalte „Bezeichnung“ fehlt" not in txt
    assert "kopf“ und „kopf" not in txt

    # härter: auch id doppelt „kopf“ – Zuordnung über die Kopfzeile
    for b in profil["bloecke"]:
        if b.get("id") in ("kunde", "beleg"):
            b["id"] = "kopf"
    (r2,) = adapter_csv.lesen(FIKTIV, profil, konfig)
    assert r2.nummer == "784395789"
    txt2 = " ".join(_hinweise(r2))
    assert "Spalte „Belegname“ fehlt" not in txt2
    assert "Spalte „Bezeichnung“ fehlt" not in txt2


def test_einheit_nur_leere_zelle_nicht_verlorene_spalte(konfig, tmp_path):
    """Zugordnete Einheit bleibt; nur wirklich leere Zelle löst die Stück-Warnung aus."""
    csv = tmp_path / "fiktiv-einheit.csv"
    lines = FIKTIV.read_text(encoding="utf-8").strip().splitlines()
    aus = []
    for ln in lines:
        if ln.startswith("Satzart;Gesamt"):
            aus.append("#Positionen;Dichtung 20 mm;1;;12,00;19")
        aus.append(ln)
    csv.write_text("\n".join(aus) + "\n", encoding="utf-8")
    fmt = ce.format_erkennen(csv)
    bloecke, sa = ce.bloecke_vorschlagen(fmt)
    zu: dict[str, dict[str, str]] = {}
    for b in bloecke:
        if b.get("kopf"):
            v = ce.spalten_vorschlagen(list(b["kopf"]), [r for _n, r in b.get("daten") or []])
            if not b.get("wiederholend"):
                v = {f: s for f, s in v.items() if f not in ce.positionsfelder()}
            zu[b.get("id") or b["typ"]] = v
    profil = ce.profil_bauen_bloecke(
        "fiktiv-einheit", csv, fmt, bloecke, zu, {}, {}, {}, None, sa
    )
    profil.setdefault("aufbau", {})["einheit_fehlt_stueck"] = True
    (r,) = adapter_csv.lesen(csv, profil, konfig)
    assert len(r.positionen) == 3
    assert r.positionen[0].einheit  # Stück zugeordnet, nicht verloren
    assert r.positionen[1].einheit
    assert r.positionen[2].einheit_angenommen is True
    txt = " ".join(_hinweise(r))
    assert "Pos 3 BT-130" in txt and "Einheit fehlte" in txt
    assert "Pos 1 BT-130" not in txt
    assert "Spalte „Einheit“ fehlt" not in txt


def test_neue_profile_kopieren_fest_waehrung_nicht_in_jeden_block():
    fmt = ce.format_erkennen(FIKTIV)
    bloecke, sa = ce.bloecke_vorschlagen(fmt)
    zu: dict[str, dict[str, str]] = {}
    for b in bloecke:
        if b.get("kopf"):
            v = ce.spalten_vorschlagen(list(b["kopf"]), [r for _n, r in b.get("daten") or []])
            if not b.get("wiederholend"):
                v = {f: s for f, s in v.items() if f not in ce.positionsfelder()}
            zu[b.get("id") or b["typ"]] = v
    profil = ce.profil_bauen_bloecke(
        "fiktiv-fest", FIKTIV, fmt, bloecke, zu, {}, {}, {}, None, sa
    )
    mit_fest = [
        b["id"]
        for b in profil["bloecke"]
        if isinstance((b.get("felder") or {}).get("BT-5"), dict)
        and "fest" in (b["felder"]["BT-5"])
        and not (b["felder"]["BT-5"].get("spalte") or b["felder"]["BT-5"].get("position"))
    ]
    # Währung kommt aus der Beleg-Spalte – kein fest EUR in anderen Blöcken
    assert mit_fest == []
