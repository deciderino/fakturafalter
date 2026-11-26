# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""CSV-Blocklayout 0.9.9: freie Felder, Marker, Textzeilen, Migration (fiktive Daten)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from fakturafalter import adapter_csv, csv_bloecke, rechnen, sicht

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
D = Decimal


def _profil(name: str) -> dict:
    return yaml.safe_load((BEISPIELE / name).read_text(encoding="utf-8"))


def _lesen(csv_name: str, profil_name: str, konfig):
    (r,) = adapter_csv.lesen(BEISPIELE / csv_name, _profil(profil_name), konfig)
    rechnen.berechnen(r)
    return r


def test_klassisch_kopf_positionen_zahlung(konfig):
    r = _lesen(
        "beispiel-bloecke-klassisch.csv", "profil-beispiel-bloecke-klassisch.yaml", konfig
    )
    assert r.nummer == "RE-2026-2101"
    assert r.datum == date(2026, 11, 12)
    assert r.leistungsdatum == date(2026, 11, 11)
    assert r.kaeufer.name == "Beispiel Technik GmbH"
    assert len(r.positionen) == 2
    assert r.positionen[0].bezeichnung == "Schutzblech hinten"
    assert r.positionen[0].einheit == "H87"
    assert r.positionen[1].einheit == "HUR"
    assert (r.summen.netto, r.summen.brutto) == (D("163.00"), D("193.97"))
    assert r.zahlung.ziel_tage == 30
    assert r.zahlung.faellig == date(2026, 12, 12)
    assert [(s.tage, s.satz) for s in r.zahlung.skonto] == [(10, D("2"))]
    assert "#SKONTO#" not in (r.zahlung.bedingungen or "")
    assert r.status == "ok", [str(h) for h in r.hinweise]


def test_frei_felder_kommentar_und_leer(konfig):
    r = _lesen("beispiel-bloecke-frei.csv", "profil-beispiel-bloecke-frei.yaml", konfig)
    assert r.nummer == "RE-2026-2102"
    assert r.lieferung.name == "Lager Nord" or (r.lieferung and "Nord" in (r.lieferung.name or ""))
    assert len(r.positionen) == 2
    p0 = r.positionen[0]
    assert p0.bezeichnung == "Bürostuhl Modell Münster"
    assert "Lieferung frei Haus" in (p0.beschreibung or "")
    uz = [t for t, _g in sicht.unterzeilen(p0)]
    assert any(t == "" for t in uz) or "\n\n" in (p0.beschreibung or "")
    assert r.positionen[1].bezeichnung == "Montage vor Ort"
    assert [(s.tage, s.satz) for s in r.zahlung.skonto] == [(10, D("2"))]
    assert (r.summen.netto, r.summen.brutto) == (D("363.00"), D("431.97"))
    assert r.status == "ok", [str(h) for h in r.hinweise]


def test_marker_kommentar_kein_marker_und_leer(konfig):
    r = _lesen("beispiel-bloecke-marker.csv", "profil-beispiel-bloecke-marker.yaml", konfig)
    assert r.nummer == "RE-2026-2103"
    assert r.kaeufer.name == "Beispiel Werkstätten GmbH"
    assert len(r.positionen) == 2
    p0 = r.positionen[0]
    assert p0.bezeichnung == "Dichtungssatz DN 50"
    assert "bitte nicht mit Lösungsmitteln reinigen" in (p0.beschreibung or "")
    uz = [t for t, _g in sicht.unterzeilen(p0)]
    assert any(t == "" for t in uz) or "\n\n" in (p0.beschreibung or "")
    assert r.positionen[1].bezeichnung == "Einbau pauschal"
    assert r.positionen[1].einheit == "LS"
    assert r.zahlung.ziel_tage == 14
    assert r.status == "ok", [str(h) for h in r.hinweise]


def test_alte_hotelprofile_laufen_weiter(konfig):
    r = _lesen("variante-blo_hotel.csv", "profil-variante-blo.yaml", konfig)
    assert r.nummer == "SK-2026-0413"
    assert len(r.positionen) == 4
    assert r.status == "ok", [str(h) for h in r.hinweise]


def test_zwischen_nachher_an_untere_position(konfig, tmp_path):
    prof = _profil("profil-beispiel-bloecke-frei.yaml")
    (prof.get("aufbau") or {}).setdefault("textzeile", {})["zwischen"] = "nachher"
    text = (
        "Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        "Bürostuhl;2;Stück;149,00;19\n"
        "Lieferung frei Haus;;;\n"
        "Montage;1;Stunde;65,00;19\n"
    )
    # with kopf first so the invoice is complete enough
    kopf = (
        "Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde;Strasse;PLZ;Ort;"
        "Skonto;Zahlungsziel mit Skonto;Zahlungsziel ohne Abzug\n"
        "RE-2026-2199;13.11.2026;13.11.2026;K-2102;Beispiel Handel GmbH;"
        "Beispielweg 5;12345;Musterstadt;2,00;10;30\n\n"
    )
    f = tmp_path / "n.csv"
    f.write_text(kopf + text, encoding="utf-8-sig")
    (r,) = adapter_csv.lesen(f, prof, konfig)
    rechnen.berechnen(r)
    assert "Lieferung frei Haus" not in (r.positionen[0].beschreibung or "")
    assert "Lieferung frei Haus" in (r.positionen[1].beschreibung or "")


def test_null_menge_ist_kommentar(konfig, tmp_path):
    prof = _profil("profil-beispiel-bloecke-frei.yaml")
    text = (
        "Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde;Strasse;PLZ;Ort;"
        "Skonto;Zahlungsziel mit Skonto;Zahlungsziel ohne Abzug\n"
        "RE-2026-2198;13.11.2026;13.11.2026;K-2102;Beispiel Handel GmbH;"
        "Beispielweg 5;12345;Musterstadt;;;\n\n"
        "Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        "Bürostuhl;2;Stück;149,00;19\n"
        "Hinweis zur Montage;0;Stück;0,00;19\n"
        "Montage;1;Stunde;65,00;19\n"
    )
    f = tmp_path / "z.csv"
    f.write_text(text, encoding="utf-8-sig")
    (r,) = adapter_csv.lesen(f, prof, konfig)
    rechnen.berechnen(r)
    assert len(r.positionen) == 2
    assert "Hinweis zur Montage" in (r.positionen[0].beschreibung or "")


def test_marker_ohne_hash_und_optionale_kopfzeile(konfig, tmp_path):
    prof = _profil("profil-beispiel-bloecke-marker.yaml")
    for b in prof["bloecke"]:
        if b.get("typ") == "kopf":
            b["marker"] = "KOPF"
        elif b.get("typ") == "positionen":
            b["marker"] = "POSITIONEN"
        elif b.get("typ") == "summen":
            b["marker"] = "SUMMEN"
    # no header after POSITIONEN: data in stored column order
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
    f = tmp_path / "m.csv"
    f.write_text(text, encoding="utf-8-sig")
    (r,) = adapter_csv.lesen(f, prof, konfig)
    rechnen.berechnen(r)
    assert r.nummer == "RE-2026-2197"
    assert len(r.positionen) == 2
    assert r.positionen[0].bezeichnung == "Dichtungssatz DN 50"
    assert r.zahlung.ziel_tage == 14


def test_start_ohne_kopfzeile_zu_pruefen(konfig, tmp_path):
    prof = _profil("profil-beispiel-bloecke-klassisch.yaml")
    text = "RE-2026-2196;12.11.2026;11.11.2026;K-2101;Beispiel Technik GmbH;Musterweg 4;38100;Braunschweig\n"
    f = tmp_path / "s.csv"
    f.write_text(
        text
        + "\nRechnungsnr;Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        + "RE-2026-2196;Schutzblech;2;Stück;49,00;19\n",
        encoding="utf-8-sig",
    )
    (r,) = adapter_csv.lesen(f, prof, konfig)
    assert any("beginnt nicht" in (h.text or "") and h.stufe == "pruefen" for h in r.hinweise)


def test_hash_leer_ist_kein_marker():
    prof = _profil("profil-beispiel-bloecke-marker.yaml")
    assert csv_bloecke.ist_markerzeile(["#LEER", "", ""], prof) == ""
    assert csv_bloecke.ist_markerzeile(["#Positionen", "", ""], prof) == "positionen"
    assert csv_bloecke.ist_markerzeile(["# bitte nicht mit Lösungsmitteln reinigen", "", ""], prof) == ""
    assert not csv_bloecke.sieht_nach_marker_heuristik(
        ["# bitte nicht mit Lösungsmitteln reinigen", "", ""]
    )
    assert csv_bloecke.sieht_nach_marker_heuristik(["#Positionen", "", ""])
    assert not csv_bloecke.sieht_nach_marker_heuristik(["#LEER", "", ""])


def test_profil_passt_ohne_pflicht_im_positionsblock():
    prof = _profil("profil-beispiel-bloecke-frei.yaml")
    ok, grund = adapter_csv.profil_passt_grund(BEISPIELE / "beispiel-bloecke-frei.csv", prof)
    assert ok, grund
    assert "Block" in grund


def test_assistent_erkennt_marker_ohne_profil():
    from fakturafalter import csv_einrichtung as ce

    fmt = ce.format_erkennen(BEISPIELE / "beispiel-bloecke-marker.csv")
    marken = ce.marker_aus_datei(fmt)
    assert [m["marker"] for m in marken] == ["#Kopf", "#Positionen", "#Summen"]
    assert [m["typ"] for m in marken] == ["kopf", "positionen", "summen"]
    bloecke = ce.bloecke_schneiden_zuordnung(fmt, {})
    typen = [b.get("typ") for b in bloecke]
    assert typen == ["kopf", "positionen", "summen"]
    assert [b.get("marker_wort") for b in bloecke] == ["#Kopf", "#Positionen", "#Summen"]
    # keine Phantom-Blöcke vor dem ersten Marker
    assert bloecke[0].get("start") == 1
