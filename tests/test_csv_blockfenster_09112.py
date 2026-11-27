# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.9.11.2: Positionsblock mit Kopfzeile vor #Pos, Restzeile, Währung EURO."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml

pytest.importorskip("PySide6")

from fakturafalter import adapter_csv
from fakturafalter import csv_einrichtung as ce
from fakturafalter.aufbau import waehrung_code
from fakturafalter.werte import dekodieren

from .test_gui import fenster, konfig_datei, qapp  # noqa: F401

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
FIKTIV = BEISPIELE / "beispiel-satzart-pos-kopf-und-restzeile.csv"


def _hinweise(r) -> list[str]:
    return [str(h) for h in r.hinweise]


def _profil(
    anfang_satzart_zuerst: bool, typen: tuple[str, str, str], fest_eur: bool, kodierung: str
) -> dict:
    """Fiktives Blockprofil in zwei typischen Speicherformen (älter / neu)."""
    t_kunde, t_beleg, t_pos = typen

    def anfang(wert: str, kopf_zuerst: bool) -> list[dict]:
        sa = {"art": "satzart", "wert": wert}
        kz = {"art": "kopfzeile"}
        return [kz, sa] if kopf_zuerst and not anfang_satzart_zuerst else [sa, kz]

    kunde_felder = {
        "BT-44": {"spalte": "Kunde1", "position": 2, "optional": True},
        "kunden_name_2": {"spalte": "Kunde2", "position": 3, "optional": True},
        "kunden_name_3": {"spalte": "Kunde3", "position": 4, "optional": True},
        "BT-50": {"spalte": "Strasse", "position": 5, "optional": True},
        "BT-53": {"spalte": "PLZ", "position": 6, "optional": True},
        "BT-52": {"spalte": "Ort", "position": 7, "optional": True},
        "BT-48": {"spalte": "USt.-ID", "position": 8, "optional": True},
        "BT-3": {"fest": "380"},
    }
    if fest_eur:
        kunde_felder["BT-5"] = {"fest": "EUR"}
    beleg_felder = {
        "BT-1": {"spalte": "Belegname", "position": 2, "optional": True},
        "BT-2": {"spalte": "Belegdatum", "position": 3, "typ": "datum", "optional": True},
        "BT-72": {"spalte": "Leistungsdatum", "position": 4, "typ": "datum", "optional": True},
        "BT-5": {"spalte": "Währung", "position": 5, "optional": True},
        "BT-3": {"fest": "380"},
    }
    pos_felder = {
        "BT-153": {"spalte": "Bezeichnung", "position": 3},
        "BT-129": {"spalte": "Menge", "position": 4, "typ": "zahl"},
        "BT-130": {"spalte": "Einheit", "position": 5, "optional": True, "mapping": "einheiten"},
        "BT-146": {"spalte": "Einzelpreis", "position": 6, "typ": "zahl"},
        "BT-149": {"spalte": "Preisbasis", "position": 7, "typ": "zahl", "optional": True},
        "gesamtpreis_position": {
            "spalte": "Gesamtpreis", "position": 8, "typ": "zahl", "optional": True
        },
        "steuer": {"spalte": "Ust-Satz", "position": 9, "mapping": "steuer"},
        "BT-3": {"fest": "380"},
    }
    if fest_eur:
        pos_felder["BT-5"] = {"fest": "EUR"}
    return {
        "profil": "fiktiv-09112",
        "name": "fiktiv-09112",
        "version": 2,
        "datei": {
            "muster": "*.csv",
            "kodierung": kodierung,
            "trennzeichen": ";",
            "textbegrenzer": '"',
            "kopfzeile": False,
        },
        "zahlen": {"dezimal": ",", "tausender": "."},
        "datum": {"format": "%d.%m.%Y"},
        "aufbau": {
            "art": "bloecke",
            "kopfzeile_schwelle": 2,
            "satzart_spalte": "Satzart",
            "einheit_fehlt_stueck": True,
            "textzeile": {
                "leer": ["BT-129", "BT-146"],
                "ziel": "BT-154",
                "trenner": "\n",
                "platzhalter": "",
                "verwaist": "BT-22",
                "leerzeile_modus": "beides",
                "zwischen": "vorher",
                "text_spalte": "Bezeichnung",
                "preis_ohne_menge": "pruefen",
            },
        },
        "mappings": {
            "einheiten": {"Stück": "H87", "unbekannt": "allgemein"},
            "steuer": {"unbekannt": "satz"},
        },
        "sicht": {"positionsnummer": True, "einheit": "csv", "menge_exakt": True},
        "aktiv": True,
        "bloecke": [
            {
                "id": "kunde",
                "typ": t_kunde,
                "name": "kunde",
                "wiederholend": False,
                "kopfzeile": [
                    "Satzart",
                    "Kunde1",
                    "Kunde2",
                    "Kunde3",
                    "Strasse",
                    "PLZ",
                    "Ort",
                    "USt.-ID",
                    "",
                ],
                "felder": kunde_felder,
                "anfang": anfang("#Kunde", kopf_zuerst=False),
            },
            {
                "id": "beleg",
                "typ": t_beleg,
                "name": "beleg",
                "wiederholend": False,
                "kopfzeile": [
                    "Satzart",
                    "Belegname",
                    "Belegdatum",
                    "Leistungsdatum",
                    "Währung",
                ],
                "felder": beleg_felder,
                "anfang": anfang("#Beleg", kopf_zuerst=not anfang_satzart_zuerst),
            },
            {
                "id": "positionen",
                "typ": t_pos,
                "name": "positionen",
                "wiederholend": True,
                "kopfzeile": [
                    "Satzart",
                    "Artikel-Nr.",
                    "Bezeichnung",
                    "Menge",
                    "Einheit",
                    "Einzelpreis",
                    "Preisbasis",
                    "Gesamtpreis",
                    "Ust-Satz",
                    "",
                ],
                "felder": pos_felder,
                "anfang": anfang("#Pos", kopf_zuerst=not anfang_satzart_zuerst),
            },
        ],
    }


PROFIL_ALT = _profil(False, ("kopf", "kopf", "positionen"), True, "cp1252")
PROFIL_NEU = _profil(True, ("kunde", "beleg", "positionen"), False, "utf-8")


def _erwartung(r, *, einheit_warnung_pos3: bool = True) -> str:
    txt = " ".join(_hinweise(r))
    assert r.nummer == "RE-47110815"
    assert (r.kaeufer.name or "").startswith("Nordlicht")
    assert len(r.positionen) == 3
    assert r.waehrung == "EUR"
    assert "Spalte" not in txt or "fehlt" not in txt, txt
    assert "kein ISO-4217" not in txt, txt
    assert "BT-81" not in txt and "SEPA" not in txt, txt
    if einheit_warnung_pos3:
        assert "Pos 3" in txt and "Einheit fehlte" in txt, txt
    return txt


@pytest.mark.parametrize(
    "profil", [PROFIL_ALT, PROFIL_NEU], ids=["alt-kopf-typ-cp1252", "neu-satzart-zuerst-utf8"]
)
def test_probe_preview_eingang_ohne_spalte_fehlt(fenster, profil):
    """Probe-Liste, Lesen und Eingang: drei Positionen, EURO→EUR, Restzeile ohne Spaltenfehler."""
    k = fenster.k
    p = deepcopy(profil)
    rs_probe = adapter_csv.lesen(FIKTIV, p, k)
    geladen_text = yaml.safe_dump(p, allow_unicode=True, sort_keys=False)
    geladen = yaml.safe_load(geladen_text)
    rs_yaml = adapter_csv.lesen(FIKTIV, geladen, k)
    geladen["_datei"] = "profil-fiktiv-09112.yaml"
    _gew, rs_ein = adapter_csv.lesen_mit_auswahl(FIKTIV, [geladen], k)
    assert len(rs_probe) == len(rs_yaml) == len(rs_ein) == 1
    for r in (rs_probe[0], rs_yaml[0], rs_ein[0]):
        _erwartung(r)
    erg = ce.probe_csv(FIKTIV, geladen, k)
    assert erg[0].nummer == "RE-47110815"
    probe_txt = " ".join(str(h) for h in erg[0].hinweise)
    assert "Spalte" not in probe_txt or "fehlt" not in probe_txt, probe_txt
    assert any("Einheit fehlte" in str(h) for h in erg[0].hinweise)
    assert rs_probe[0].waehrung == rs_yaml[0].waehrung == rs_ein[0].waehrung == "EUR"


def test_waehrung_euro_euro_eur():
    for roh in ("EURO", "Euro", "euro", "€", "EUR", "eur"):
        assert waehrung_code(roh) == "EUR", roh


def test_dekodieren_bevorzugt_utf8_trotz_cp1252_im_profil():
    raw = FIKTIV.read_bytes()
    text, kod = dekodieren(raw, "cp1252")
    assert kod == "utf-8"
    assert "Währung" in text
    assert "StÃ¼ck" not in text
    # echte Windows-1252-Datei bleibt Windows-1252
    cp = "Fachbuch „Montage“ Stück".encode("cp1252")
    t2, k2 = dekodieren(cp, "cp1252")
    assert k2 == "cp1252"
    assert "Stück" in t2


def test_meldungen_nennen_block_wenn_spalte_wirklich_fehlt(fenster):
    p = deepcopy(PROFIL_NEU)
    # Pflichtspalte umbenennen, damit sie in der Zeile fehlt
    pos = next(b for b in p["bloecke"] if b.get("wiederholend"))
    pos["felder"]["BT-153"] = {"spalte": "GibtsNicht", "position": 99}
    rs = adapter_csv.lesen(FIKTIV, p, fenster.k)
    txt = " ".join(_hinweise(rs[0]))
    assert "Block „positionen“" in txt
    assert "Spalte „GibtsNicht“ fehlt" in txt


def test_assistent_probe_ohne_spalte_fehlt(fenster, qapp):
    """Echter Assistent bis zur Probe: Restzeile und EURO führen nicht zu Spaltenfehlern."""
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(FIKTIV)
    d.name.setText("fiktiv-09112")
    qapp.processEvents()
    for _ in range(8):
        folge = d._folge()
        if folge[d.i][0] == 4 and getattr(d, "c_einheit_fehlt_stueck", None):
            d.c_einheit_fehlt_stueck.setChecked(True)
        if folge[d.i][0] == 5:
            break
        d.b_weiter.click()
        qapp.processEvents()
    assert d._folge()[d.i][0] == 5  # Probe
    p = d.profil()
    assert (p.get("aufbau") or {}).get("art") == "bloecke"
    rs = adapter_csv.lesen(FIKTIV, p, fenster.k)
    assert len(rs) == 1
    _erwartung(rs[0])
    erg = ce.probe_csv(FIKTIV, p, fenster.k)
    probe_txt = " ".join(str(h) for h in erg[0].hinweise)
    assert "Spalte" not in probe_txt or "fehlt" not in probe_txt, probe_txt
    assert erg[0].nummer == "RE-47110815"
    d.reject()
