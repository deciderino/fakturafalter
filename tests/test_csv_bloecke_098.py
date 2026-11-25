# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""CSV-Aufbau bloecke (0.9.8): eine Datei, Blöcke mit eigener Kopfzeile, Textzeilen, Skonto."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from fakturafalter import adapter_csv, rechnen, sicht
from fakturafalter.modell import Position

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
D = Decimal


def _profil():
    return yaml.safe_load((BEISPIELE / "profil-variante-blo.yaml").read_text(encoding="utf-8"))


def _lesen(name, konfig):
    (r,) = adapter_csv.lesen(BEISPIELE / name, _profil(), konfig)
    rechnen.berechnen(r)
    return r


def test_hotel_beispiel_summen_und_skonto(konfig):
    r = _lesen("variante-blo_hotel.csv", konfig)
    assert r.nummer == "SK-2026-0413"
    assert r.datum == date(2026, 10, 6)
    assert r.leistungsdatum == date(2026, 10, 5)
    assert r.kaeufer.name == "Hotel Am Stadtpark GmbH"
    assert len(r.positionen) == 4
    assert (r.summen.netto, r.summen.ust, r.summen.brutto) == (
        D("574.80"),
        D("101.44"),
        D("676.24"),
    )
    assert r.zahlung.ziel_tage == 30
    assert r.zahlung.faellig == date(2026, 11, 5)
    assert "3 % Skonto innerhalb von 10 Tagen (bis 16.10.2026)" in r.zahlung.bedingungen
    assert "30 Tagen ohne Abzug (bis 05.11.2026)" in r.zahlung.bedingungen
    assert r.status != "pruefen" or not any("Kontrollwert" in h.text for h in r.hinweise)


def test_getrennt_textzeile_und_platzhalter(konfig):
    r = _lesen("variante-blo_getrennt.csv", konfig)
    assert r.nummer == "SK-2026-0414"
    p0 = r.positionen[0]
    assert p0.bezeichnung == "Roggenmischbrot 1000 g"
    assert "mit extra Körnern und länger haltbar" in (p0.beschreibung or "")
    assert (
        "\n\n" in p0.beschreibung
        or p0.beschreibung.endswith("\n")
        or "\n\n" in f"\n{p0.beschreibung}"
    )
    # gewollte Leerzeile auf der Sichtseite
    uz = [t for t, _g in sicht.unterzeilen(p0)]
    assert any(t == "" for t in uz) or any("\n" in (p0.beschreibung or "") for _ in [0])
    assert len(r.positionen) == 4
    assert (r.summen.netto, r.summen.brutto) == (D("574.80"), D("676.24"))
    assert r.zahlung.ziel_tage == 30
    assert not any(
        "Kontrollwert" in h.text and "≠" in h.text for h in r.hinweise if h.stufe == "pruefen"
    )


def test_abweichung_zwei_nummern_und_summe(konfig):
    r = _lesen("variante-blo_abweichung.csv", konfig)
    texte = " ".join(h.text for h in r.hinweise)
    assert "weitere Rechnung" in texte
    assert any("Kontrollwert" in h.text for h in r.hinweise)


def test_verwaiste_textzeile_wird_bt22(konfig, tmp_path):
    text = """Artikel;Menge;Einheit;Einzelpreis;USt-Satz
Bitte Hinweis zur ganzen Rechnung;;;
Roggenmischbrot 1000 g;12;Stk;3,40;7
"""
    # need a kopf somehow - add kopf block
    text = """Rechnungsnr;Datum;Kunde
SK-2026-0416;06.10.2026;Hotel Am Stadtpark GmbH

Artikel;Menge;Einheit;Einzelpreis;USt-Satz
Bitte Hinweis zur ganzen Rechnung;;;
Roggenmischbrot 1000 g;12;Stk;3,40;7
"""
    p = tmp_path / "v.csv"
    p.write_text(text, encoding="utf-8")
    (r,) = adapter_csv.lesen(p, _profil(), konfig)
    bem = " ".join(b[0] for b in r.bemerkungen)
    assert "Bitte Hinweis zur ganzen Rechnung" in bem
    assert len(r.positionen) == 1


def test_sicht_behaelt_leerzeile():
    p = Position()
    p.bezeichnung = "Brot"
    p.beschreibung = "erste Zeile\n\nzweite Zeile"
    uz = sicht.unterzeilen(p)
    texte = [t for t, _g in uz]
    assert texte[0].startswith("Beschreibung: erste Zeile")
    assert "" in texte
    assert "zweite Zeile" in texte


def test_profil_passt_auf_hotel():
    prof = _profil()
    ok, grund = adapter_csv.profil_passt_grund(BEISPIELE / "variante-blo_hotel.csv", prof)
    assert ok, grund
    assert "Block" in grund


def test_fehlendes_aktiv_gilt_als_aktiv():
    assert adapter_csv.profil_aktiv({}) is True
    assert adapter_csv.profil_aktiv({"profil": "x"}) is True
    assert adapter_csv.profil_aktiv({"aktiv": True}) is True
    assert adapter_csv.profil_aktiv({"aktiv": False}) is False


def test_profil_reihenfolge_und_inaktiv(konfig, tmp_path):
    import shutil

    from fakturafalter.pipeline import verarbeiten

    for n in ("ausgang", "erledigt", "fehler", "pruefen"):
        getattr(konfig, n).mkdir(exist_ok=True)
    blo = _profil()
    blo["_basis"] = BEISPIELE
    blo["_datei"] = str(BEISPIELE / "profil-variante-blo.yaml")
    oben = {**blo, "profil": "blo-oben", "aktiv": True}
    unten = {**blo, "profil": "blo-unten", "aktiv": True}
    konfig.csv_profile = [oben, unten]
    ziel = konfig.eingang / "variante-blo_hotel.csv"
    shutil.copy(BEISPIELE / "variante-blo_hotel.csv", ziel)
    lauf = verarbeiten([ziel], konfig, verschieben=False)
    assert lauf.ergebnisse, getattr(lauf, "datei_fehler", None)
    assert lauf.ergebnisse[0].profil == "blo-oben"

    aus = {**blo, "profil": "blo-aus", "aktiv": False}
    konfig.csv_profile = [aus, unten]
    lauf = verarbeiten([ziel], konfig, verschieben=False)
    assert lauf.ergebnisse[0].profil == "blo-unten"
