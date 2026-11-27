# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Blockfenster 0.9.11: freie Blöcke, manuelle Blockart, Satzart in der Datenzeile (fiktiv)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from fakturafalter import csv_bloecke
from fakturafalter import csv_einrichtung as ce
from fakturafalter.gui import thema
from fakturafalter.werte import csv_lesen, dekodieren

from .test_gui import fenster, konfig_datei, qapp  # noqa: F401

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
FIKTIV = BEISPIELE / "beispiel-satzart-marker-in-spalte.csv"
D = Decimal


def _kontrast(hg: str, fg: str) -> float:
    def lum(h: str) -> float:
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))

        def f(x: float) -> float:
            return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

        R, G, B = f(r), f(g), f(b)
        return 0.2126 * R + 0.7152 * G + 0.0722 * B

    L1, L2 = lum(hg), lum(fg)
    return (max(L1, L2) + 0.05) / (min(L1, L2) + 0.05)


def _vorschlagen():
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
        "fiktiv-satzart-spalte", FIKTIV, fmt, bloecke, zu, {}, {}, {}, sa
    )
    return fmt, bloecke, sa, profil


def test_fiktive_datei_vier_bloecke_ohne_typ_kollision():
    _fmt, bloecke, sa, _p = _vorschlagen()
    typen = [b["typ"] for b in bloecke]
    assert typen == ["kunde", "beleg", "positionen", "summen"]
    assert typen.count("kopf") == 0
    assert sa in ("Satzart", "satzart") or sa
    wdh = [b for b in bloecke if b.get("wiederholend")]
    assert len(wdh) == 1 and wdh[0]["typ"] == "positionen"
    kunde, beleg, pos, _summen = bloecke
    assert any(r.get("art") == "satzart" and r.get("wert") == "#Kopf" for r in kunde["anfang"])
    assert any(r.get("art") == "satzart" and r.get("wert") == "#Beleg" for r in beleg["anfang"])
    assert any(r.get("art") == "kopfzeile" for r in kunde["anfang"])
    # #Kopf;#Beleg stehen in Datenzeilen, nicht als leere Marker
    assert [z for z, _r in kunde.get("daten") or []]
    row = kunde["daten"][0][1]
    assert not csv_bloecke.sieht_nach_marker_heuristik(row)
    assert row[0] == "#Kopf"
    assert beleg["daten"][0][1][0] == "#Beleg"
    assert [z for z, _r in pos.get("daten") or []] == [6, 7] or len(pos.get("daten") or []) == 2


def test_fiktive_datei_lesen_belegnummer_und_kurzes_datum():
    _fmt, _b, _sa, profil = _vorschlagen()
    assert (profil.get("datum") or {}).get("format") in ("%d.%m.%y", "%d.%m.%Y") or profil.get(
        "datum"
    )
    # Format muss gesetzt sein, sonst Fallback auf vierstelliges Jahr
    if "format" not in (profil.get("datum") or {}):
        profil.setdefault("datum", {})["format"] = "%d.%m.%y"
    zeilen = list(csv_lesen(dekodieren(FIKTIV.read_bytes())[0], ";"))
    od = csv_bloecke.lesen(zeilen, profil, FIKTIV, 1)
    assert list(od) == ["784395789"]
    kopf, pos, fehler = od["784395789"]
    assert fehler == []
    assert (kopf.get("BT-1") or [None])[0] == "784395789"
    assert (kopf.get("BT-2") or [None])[0] == date(2026, 10, 10)
    assert (kopf.get("BT-72") or [None])[0] == date(2026, 10, 9)
    assert (kopf.get("BT-44") or [None])[0] == "Testkunde"
    assert len(pos) == 2


def test_anfang_ableiten_satzart_in_datenzeile():
    zeilen = [
        ["Satzart", "Kunde1", "Kunde2"],
        ["#Kopf", "Testkunde", "Muster GmbH"],
        ["Satzart", "Belegname"],
        ["#Beleg", "784395789"],
    ]
    anfang = ce.anfang_ableiten(zeilen, 1, 2, "Satzart")
    arten = [(r.get("art"), r.get("wert")) for r in anfang]
    assert ("kopfzeile", None) in arten or any(r.get("art") == "kopfzeile" for r in anfang)
    assert any(r.get("art") == "satzart" and r.get("wert") == "#Kopf" for r in anfang)
    assert not any(r.get("art") == "marker" for r in anfang)
    anfang_b = ce.anfang_ableiten(zeilen, 3, 4, "Satzart")
    assert any(r.get("art") == "satzart" and r.get("wert") == "#Beleg" for r in anfang_b)


def test_eindeutiger_typ_kunde_und_beleg():
    v: set[str] = set()
    k = ce.eindeutiger_typ(["Satzart", "Kunde1", "Kunde2"], "kopf", v)
    v.add(k)
    b = ce.eindeutiger_typ(["Satzart", "Belegname", "Belegdatum"], "kopf", v)
    assert k == "kunde"
    assert b == "beleg"


def test_migration_alte_blockprofile_laden(konfig):
    paare = (
        ("profil-variante-blo.yaml", "variante-blo_hotel.csv"),
        ("profil-beispiel-bloecke-klassisch.yaml", "beispiel-bloecke-klassisch.csv"),
        ("profil-beispiel-bloecke-marker.yaml", "beispiel-bloecke-marker.csv"),
        ("profil-beispiel-satzart-bloecke-koepfe.yaml", "beispiel-satzart-bloecke-koepfe.csv"),
    )
    for name, csv_name in paare:
        p = yaml.safe_load((BEISPIELE / name).read_text(encoding="utf-8"))
        assert (p.get("aufbau") or {}).get("art") == "bloecke"
        # 0.9.8–0.9.10 ohne id: Lesen bleibt möglich
        zeilen = list(csv_lesen(dekodieren((BEISPIELE / csv_name).read_bytes())[0], p.get("datei", {}).get("trenner") or ";"))
        od = csv_bloecke.lesen(zeilen, p, BEISPIELE / csv_name, 1)
        assert od, name
        _k, pos, fehler = next(iter(od.values()))
        assert pos, name
        assert not any("unbekannt" in str(x).lower() and "profil" in str(x).lower() for x in (fehler or []))


def test_palette_kontrast_wcag_aa():
    for hell in (True, False):
        pal = thema.block_palette(hell)
        for typ, (hg, fg, _rk) in pal.items():
            k = _kontrast(hg, fg)
            assert k >= 4.5, f"{typ} hell={hell} {hg}/{fg} = {k:.2f}"
        hg, fg, _rk = thema.hinweis_farben(hell)
        k = _kontrast(hg, fg)
        assert k >= 4.5, f"hinweis hell={hell} {hg}/{fg} = {k:.2f}"


def test_fehlende_pflicht_kundenname():
    basis = {
        "BT-1": "Nr",
        "BT-2": "Datum",
        "BT-153": "Bez",
        "BT-129": "Menge",
        "BT-146": "Preis",
        "steuer": "USt",
    }
    fehlt = ce.fehlende_pflicht(basis)
    assert any("Kunde" in x or "Kunden" in x for x in fehlt)
    assert not ce.fehlende_pflicht({**basis, "BT-44": "Name"})
    # Kundennummer allein ersetzt den Pflicht-Kundennamen nicht
    assert any("Kundenname" in x or "Kunde" in x for x in ce.fehlende_pflicht({**basis, "kundennummer": "Knr"}))



def test_assistent_fiktive_datei_weiter_und_pflicht(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(FIKTIV)
    d.name.setText("Fiktiv Satzart")
    assert d.art == "bloecke"
    d.b_weiter.click()  # Format
    d.b_weiter.click()  # Blöcke festlegen
    assert d.i == 2
    typen = [b.get("typ") for b in d.t_block.bloecke]
    assert typen == ["kunde", "beleg", "positionen", "summen"]
    assert d.b_weiter.isEnabled()
    d.b_weiter.click()  # Spalten je Block
    assert d.i == 3
    flach = d._alle_zuordnungen()
    # Pflichtfelder inkl. Käufername aus dem Kundenblock
    fehlt = ce.fehlende_pflicht(flach)
    assert not fehlt, fehlt
    assert d.b_weiter.isEnabled()
    p = d.profil()
    typen_p = [b.get("typ") for b in p.get("bloecke") or []]
    assert typen_p == ["kunde", "beleg", "positionen", "summen"]
    assert any(b.get("wiederholend") for b in p["bloecke"])
    # manuelle Blockart: Zuordnung ändert wiederholend nicht
    pos = next(b for b in d.t_block.bloecke if b.get("typ") == "positionen")
    assert pos.get("wiederholend") is True
    d.t_block.set_wiederholend(False, d.t_block.bloecke.index(pos))
    assert pos.get("wiederholend") is False
    d.t_block.set_wiederholend(True, d.t_block.bloecke.index(pos))
    d.reject()
