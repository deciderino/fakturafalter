# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Profilerkennung 0.9.9.1: kein fremder Block-Treffer, Synonym Gesamt USt (fiktive Daten)."""

from __future__ import annotations

from pathlib import Path

import yaml

from fakturafalter import adapter_csv, pipeline
from fakturafalter import csv_einrichtung as ce

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"

# Blockdatei mit Satzart-Spalte und eigenen Kopfzeilen je Block (fiktiv).
_SATZART_BLOECKE = (
    "Satzart;Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde\n"
    "K;RE-2026-2201;16.11.2026;16.11.2026;K-2201;Mustertechnik Nord GmbH\n"
    "\n"
    "Satzart;Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
    "P;Dichtungssatz DN 40;3;Stück;18,50;19\n"
    "P;Montage vor Ort;2;Stunde;65,00;19\n"
    "\n"
    "Satzart;Gesamt Netto;Gesamt USt;Gesamt Brutto;Zahlungsziel ohne Abzug\n"
    "S;186,50;35,44;221,94;30\n"
)


def _hotel():
    p = yaml.safe_load((BEISPIELE / "profil-variante-blo.yaml").read_text(encoding="utf-8"))
    p["datei"] = dict(p.get("datei") or {})
    p["datei"]["muster"] = "*.csv"
    p["_basis"] = BEISPIELE
    p["_datei"] = str(BEISPIELE / "profil-variante-blo.yaml")
    return p


def _passendes_profil(datei: Path) -> dict:
    fmt = ce.format_erkennen(datei)
    unique = ce.einzigartige_spalten(fmt) or list(fmt.kopf)
    zu = ce.spalten_vorschlagen(unique, fmt.zeilen)
    roh = ce.bloecke_schneiden_zuordnung(fmt, zu)
    bloecke = []
    for b in roh:
        typ = b.get("typ") or ce.typ_vorschlag(b.get("kopf") or [])
        namen = {ce._norm(c) for c in (b.get("kopf") or [])}
        wahl = {f for f, s in zu.items() if ce._norm(s) in namen}
        bloecke.append(
            {
                **b,
                "typ": typ,
                "wiederholend": typ == "positionen",
                "marker": b.get("marker_wort") or "",
                "felder_wahl": wahl,
            }
        )
    zu_je = {}
    for b in bloecke:
        typ = str(b.get("typ") or "")
        wahl = b.get("felder_wahl") or set()
        zu_je[typ] = {f: s for f, s in zu.items() if f in wahl}
    steuer = {}
    p = ce.profil_bauen_bloecke(datei.stem, datei, fmt, bloecke, zu_je, steuer, {}, {})
    p["_basis"] = datei.parent
    p["_datei"] = str(datei.parent / "profil-satzart-bloecke.yaml")
    return p


def test_gesamt_ust_ist_summe_ust_nicht_positionsbetrag():
    z = ce.spalten_vorschlagen(["Gesamt Netto", "Gesamt USt", "Gesamt Brutto"])
    assert z["BT-109"] == "Gesamt Netto"
    assert z["BT-110"] == "Gesamt USt"
    assert z["BT-112"] == "Gesamt Brutto"
    assert "gesamtpreis_position" not in z


def test_hotel_profil_passt_weiter_auf_hoteldei():
    ok, grund = adapter_csv.profil_passt_grund(BEISPIELE / "variante-blo_hotel.csv", _hotel())
    assert ok, grund


def test_hotel_mit_stern_csv_passt_nicht_auf_fremde_blockdatei(tmp_path):
    datei = tmp_path / "satzart-bloecke-koepfe.csv"
    datei.write_text(_SATZART_BLOECKE, encoding="utf-8-sig")
    ok, grund = adapter_csv.profil_passt_grund(datei, _hotel())
    assert not ok
    assert "Strasse" in grund or "Straße" in grund or "PLZ" in grund
    assert "fehlen" in grund.lower()


def test_eingang_nimmt_nicht_das_hotel_bei_fremder_blockdatei(konfig, tmp_path):
    datei = tmp_path / "satzart-bloecke-koepfe.csv"
    datei.write_text(_SATZART_BLOECKE, encoding="utf-8-sig")
    eigen = _passendes_profil(datei)
    konfig.csv_profile = [_hotel(), eigen]
    art, rs = pipeline.einlesen(datei, konfig)
    assert art == "csv"
    assert len(rs) == 1
    r = rs[0]
    assert r.nummer == "RE-2026-2201"
    assert len(r.positionen) == 2
    assert r.profil == eigen["profil"]
    texte = " ".join(h.text or "" for h in r.hinweise)
    assert "Strasse" not in texte and "Straße" not in texte
    assert "Spalte" not in texte or "fehlt" not in texte


def test_oberstes_gewinnt_wenn_beide_passen(konfig):
    hotel = _hotel()
    oben = {**hotel, "profil": "blo-oben", "aktiv": True}
    unten = {**hotel, "profil": "blo-unten", "aktiv": True}
    gewinner, grund = adapter_csv.profil_fuer_datei(
        BEISPIELE / "variante-blo_hotel.csv", [oben, unten]
    )
    assert gewinner is not None
    assert adapter_csv.profil_name(gewinner) == "blo-oben"
    assert "blo-unten" in grund


def test_standard_bleibt_zuletzt_wenn_eigenes_auch_passt(konfig, tmp_path):
    from fakturafalter import csv_standard

    mini = tmp_path / "x.csv"
    mini.write_bytes(csv_standard.vorlage_minimal())
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    eigen = csv_standard.profil()
    eigen["profil"] = "eigen-test"
    eigen["_eingebaut"] = False
    treffer, _g = adapter_csv.profil_fuer_datei(mini, [eigen, std])
    assert treffer is not None
    assert treffer.get("profil") == "eigen-test"


def test_eingang_anderes_profil_warnt_nur_bei_anderem_treffer(tmp_path):
    datei = tmp_path / "satzart-bloecke-koepfe.csv"
    datei.write_text(_SATZART_BLOECKE, encoding="utf-8-sig")
    eigen = _passendes_profil(datei)
    # Hotel passt nicht mehr: keine Warnung
    assert adapter_csv.eingang_anderes_profil(datei, eigen, [_hotel()]) is None
    # Zwei passende: das obere würde greifen
    a = {**eigen, "profil": "oben-passend"}
    b = {**eigen, "profil": "unten-neu"}
    assert adapter_csv.eingang_anderes_profil(datei, b, [a]) == "oben-passend"


def test_passt_bei_marker_ohne_positions_kopfzeile(tmp_path):
    """Kopfzeile nach Marker darf fehlen – die Spalten des Blocks stehen im Profil."""
    prof = yaml.safe_load(
        (BEISPIELE / "profil-beispiel-bloecke-marker.yaml").read_text(encoding="utf-8")
    )
    for b in prof["bloecke"]:
        if b.get("typ") == "kopf":
            b["marker"] = "KOPF"
        elif b.get("typ") == "positionen":
            b["marker"] = "POSITIONEN"
        elif b.get("typ") == "summen":
            b["marker"] = "SUMMEN"
    text = (
        "KOPF\n"
        "Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde\n"
        "RE-2026-2197;14.11.2026;14.11.2026;K-2103;Beispiel Werkstätten GmbH\n\n"
        "POSITIONEN\n"
        "Dichtungssatz DN 50;4;Stück;12,50;19\n"
        "Einbau pauschal;1;pauschal;80,00;19\n\n"
        "SUMMEN\n"
        "130,00;24,70;154,70;14\n"
    )
    f = tmp_path / "beispiel-bloecke-ohne-kopf.csv"
    f.write_text(text, encoding="utf-8-sig")
    ok, grund = adapter_csv.profil_passt_grund(f, prof)
    assert ok, grund
