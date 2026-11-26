# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Block-Assistent 0.9.10: Satzart-Anfang, Spalte je Block, gemeinsamer Lesepfad (fiktiv)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from fakturafalter import adapter_csv, csv_bloecke, pipeline, rechnen
from fakturafalter import csv_einrichtung as ce

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
D = Decimal


def _profil(name: str) -> dict:
    return yaml.safe_load((BEISPIELE / name).read_text(encoding="utf-8"))


def _lesen(csv_name: str, profil_name: str, konfig):
    (r,) = adapter_csv.lesen(BEISPIELE / csv_name, _profil(profil_name), konfig)
    rechnen.berechnen(r)
    return r


def _hotel():
    p = _profil("profil-variante-blo.yaml")
    p["datei"] = dict(p.get("datei") or {})
    p["datei"]["muster"] = "*.csv"
    p["_basis"] = BEISPIELE
    p["_datei"] = str(BEISPIELE / "profil-variante-blo.yaml")
    return p


def test_satzart_koepfe_eigene_namen(konfig):
    r = _lesen(
        "beispiel-satzart-bloecke-koepfe.csv",
        "profil-beispiel-satzart-bloecke-koepfe.yaml",
        konfig,
    )
    assert r.nummer == "RE-2026-2201"
    assert r.datum == date(2026, 11, 16)
    assert r.kaeufer.name == "Mustertechnik Nord GmbH"
    assert len(r.positionen) == 2
    assert r.positionen[0].bezeichnung == "Dichtungssatz DN 40"
    assert r.positionen[1].bezeichnung == "Montage vor Ort"
    assert (r.summen.netto, r.summen.brutto) == (D("185.50"), D("220.75"))
    assert r.zahlung.ziel_tage == 30
    texte = " ".join(h.text or "" for h in r.hinweise)
    assert "fehlt" not in texte


def test_satzart_marker_kommentar_und_leer(konfig):
    r = _lesen(
        "beispiel-satzart-bloecke-marker.csv",
        "profil-beispiel-satzart-bloecke-marker.yaml",
        konfig,
    )
    assert r.nummer == "RE-2026-2202"
    assert r.kaeufer.name == "Beispiel Elektro KG"
    assert len(r.positionen) == 2
    assert r.positionen[0].bezeichnung == "Schaltaktor 8-fach"
    komment = " ".join(
        [r.positionen[0].beschreibung or ""]
        + list(r.positionen[0].kommentar_unten or [])
        + list(r.positionen[0].zeilen_davor or [])
    )
    assert "bitte nicht lackieren" in komment
    assert r.positionen[1].bezeichnung == "Einbau pauschal"
    assert r.summen.brutto == D("211.82")


def test_gleiche_position_andere_bedeutung(konfig):
    r = _lesen(
        "beispiel-satzart-gleiche-positionen.csv",
        "profil-beispiel-satzart-gleiche-positionen.yaml",
        konfig,
    )
    assert r.nummer == "RE-2026-2203"
    assert r.kaeufer.name == "Feinwerk Muster AG"
    assert len(r.positionen) == 2
    assert r.positionen[0].bezeichnung == "Führungsbuchse"
    assert r.positionen[1].bezeichnung == "Anpassung Welle"
    assert r.positionen[0].menge == D("8")


def test_ohne_blockkopf_nur_satzart_position(konfig):
    r = _lesen(
        "beispiel-satzart-ohne-blockkopf.csv",
        "profil-beispiel-satzart-ohne-blockkopf.yaml",
        konfig,
    )
    assert r.nummer == "RE-2026-2204"
    assert r.kaeufer.name == "Lagerhaus Beispiel GmbH"
    assert len(r.positionen) == 2
    assert r.positionen[0].bezeichnung == "Kantenschutz 2 m"
    assert r.positionen[1].bezeichnung == "Zuschnitt"
    assert r.positionen[1].menge == D("0.5")
    assert r.summen.brutto == D("85.68")
    assert r.zahlung.ziel_tage == 30


def test_probe_und_eingang_gleich_trotz_altem_hotel(konfig, tmp_path):
    datei = BEISPIELE / "beispiel-satzart-bloecke-koepfe.csv"
    neu = _profil("profil-beispiel-satzart-bloecke-koepfe.yaml")
    neu["_basis"] = BEISPIELE
    neu["_datei"] = str(BEISPIELE / "profil-beispiel-satzart-bloecke-koepfe.yaml")
    hotel = _hotel()
    konfig.csv_profile = [hotel, neu]
    probe = ce.probe_csv(datei, neu, konfig)
    art, rs = pipeline.einlesen(datei, konfig)
    assert art == "csv"
    assert len(rs) == 1 and len(probe) == 1
    r = rs[0]
    rechnen.berechnen(r)
    assert r.nummer == "RE-2026-2201"
    assert r.nummer == probe[0].nummer
    assert len(r.positionen) == 2
    texte = " ".join(h.text or "" for h in r.hinweise)
    assert "Strasse" not in texte and "Straße" not in texte
    assert r.profil == neu["profil"]


def test_name_hat_vorrang_vor_position(konfig, tmp_path):
    """Steht der Name in der Kopfzeile, gilt er – nicht eine abweichende Positionsnummer."""
    prof = _profil("profil-beispiel-satzart-bloecke-koepfe.yaml")
    # bewusst falsche Position, richtiger Name
    prof["bloecke"][0]["felder"]["BT-1"] = {"spalte": "Rechnungsnr", "position": 6}
    (r,) = adapter_csv.lesen(BEISPIELE / "beispiel-satzart-bloecke-koepfe.csv", prof, konfig)
    assert r.nummer == "RE-2026-2201"
    assert r.kaeufer.name == "Mustertechnik Nord GmbH"


def test_migration_alte_profile_ohne_anfang(konfig):
    for csv_n, p_n, nr in (
        ("variante-blo_hotel.csv", "profil-variante-blo.yaml", "SK-2026-0413"),
        (
            "beispiel-bloecke-klassisch.csv",
            "profil-beispiel-bloecke-klassisch.yaml",
            "RE-2026-2101",
        ),
        ("beispiel-bloecke-marker.csv", "profil-beispiel-bloecke-marker.yaml", "RE-2026-2103"),
    ):
        prof = _profil(p_n)
        assert all(not b.get("anfang") for b in prof["bloecke"])
        (r,) = adapter_csv.lesen(BEISPIELE / csv_n, prof, konfig)
        assert r.nummer == nr, (csv_n, r.nummer)


def test_kopffeld_abweichung_wird_zu_pruefen(konfig, tmp_path):
    datei = tmp_path / "abweichung.csv"
    datei.write_text(
        "Satzart;Rechnungsnr;Gesamt Netto\n"
        "K;RE-2026-2205;10,00\n"
        "Satzart;Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        "P;Dichtung;1;Stück;10,00;19\n"
        "Satzart;Gesamt Netto\n"
        "S;11,00\n",
        encoding="utf-8-sig",
    )
    prof = _profil("profil-beispiel-satzart-bloecke-koepfe.yaml")
    # Gesamt Netto auch im Kopf
    prof["bloecke"][0]["felder"]["BT-109"] = {
        "spalte": "Gesamt Netto",
        "typ": "zahl",
        "optional": True,
        "zweck": "pruefung",
        "position": 3,
    }
    prof["datei"]["muster"] = "*.csv"
    (r,) = adapter_csv.lesen(datei, prof, konfig)
    texte = " ".join(h.text or "" for h in r.hinweise)
    assert "weicht" in texte
    assert "Gesamt" in texte or "netto" in texte.lower() or "BT-109" in texte


def test_zweite_kopf_satzart_zu_pruefen(konfig, tmp_path):
    datei = tmp_path / "zwei-koepfe.csv"
    datei.write_text(
        "Satzart;Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde\n"
        "K;RE-2026-2206;16.11.2026;16.11.2026;K-2206;Erste GmbH\n"
        "Satzart;Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde\n"
        "K;RE-2026-2207;16.11.2026;16.11.2026;K-2207;Zweite GmbH\n"
        "Satzart;Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        "P;Dichtung;1;Stück;10,00;19\n",
        encoding="utf-8-sig",
    )
    prof = _profil("profil-beispiel-satzart-bloecke-koepfe.yaml")
    prof["datei"]["muster"] = "*.csv"
    (r,) = adapter_csv.lesen(datei, prof, konfig)
    texte = " ".join(h.text or "" for h in r.hinweise)
    assert "weitere Rechnung" in texte


def test_wiederholte_positions_satzart_ist_normal(konfig):
    r = _lesen(
        "beispiel-satzart-bloecke-koepfe.csv",
        "profil-beispiel-satzart-bloecke-koepfe.yaml",
        konfig,
    )
    assert len(r.positionen) == 2
    texte = " ".join(h.text or "" for h in r.hinweise)
    assert "weitere Rechnung" not in texte


def test_hash_leer_weiter_kein_marker():
    prof = _profil("profil-beispiel-satzart-bloecke-marker.yaml")
    assert csv_bloecke.ist_markerzeile(["#LEER", "", ""], prof) == ""
    assert csv_bloecke.ist_markerzeile(["#Positionen", "", ""], prof) == "positionen"
    assert csv_bloecke.ist_markerzeile(["# bitte nicht lackieren", "", ""], prof) == ""


def test_marker_ohne_hash(konfig, tmp_path):
    prof = _profil("profil-beispiel-satzart-bloecke-marker.yaml")
    for b in prof["bloecke"]:
        if b.get("typ") == "kopf":
            b["marker"] = "KOPF"
            b["anfang"] = [{"art": "marker", "wert": "KOPF"}]
        elif b.get("typ") == "positionen":
            b["marker"] = "POSITIONEN"
            b["anfang"] = [{"art": "marker", "wert": "POSITIONEN"}]
        elif b.get("typ") == "summen":
            b["marker"] = "SUMMEN"
            b["anfang"] = [{"art": "marker", "wert": "SUMMEN"}]
    text = (
        "KOPF\n"
        "Satzart;Rechnungsnr;Datum;Leistungsdatum;Kundennummer;Kunde\n"
        "K;RE-2026-2208;16.11.2026;16.11.2026;K-2208;Werkstatt Beispiel GmbH\n\n"
        "POSITIONEN\n"
        "Satzart;Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        "P;Dichtung;1;Stück;10,00;19\n\n"
        "SUMMEN\n"
        "Satzart;Gesamt Netto;Gesamt USt;Gesamt Brutto;Zahlungsziel ohne Abzug\n"
        "S;10,00;1,90;11,90;14\n"
    )
    f = tmp_path / "beispiel-satzart-bloecke-marker.csv"
    f.write_text(text, encoding="utf-8-sig")
    (r,) = adapter_csv.lesen(f, prof, konfig)
    assert r.nummer == "RE-2026-2208"
    assert len(r.positionen) == 1


def test_freier_satzart_wert(konfig, tmp_path):
    datei = tmp_path / "frei.csv"
    datei.write_text(
        "Satzart;Rechnungsnr;Kunde\n"
        "KOPF;RE-2026-2209;Frei Beispiel GmbH\n"
        "Satzart;Artikel;Menge;Einheit;Einzelpreis;USt-Satz\n"
        "POS;Dichtung;1;Stück;10,00;19\n",
        encoding="utf-8-sig",
    )
    prof = _profil("profil-beispiel-satzart-bloecke-koepfe.yaml")
    prof["datei"]["muster"] = "*.csv"
    prof["bloecke"][0]["anfang"] = [{"art": "satzart", "wert": "KOPF"}]
    prof["bloecke"][1]["anfang"] = [{"art": "satzart", "wert": "POS"}]
    prof["bloecke"] = [b for b in prof["bloecke"] if b["typ"] != "summen"]
    (r,) = adapter_csv.lesen(datei, prof, konfig)
    assert r.nummer == "RE-2026-2209"
    assert len(r.positionen) == 1


def test_anfang_regeln_migration():
    prof = _profil("profil-beispiel-bloecke-marker.yaml")
    kopf = next(b for b in prof["bloecke"] if b["typ"] == "kopf")
    regeln = csv_bloecke.anfang_regeln(kopf)
    assert regeln[0]["art"] == "marker"
    assert "#Kopf" in regeln[0]["wert"] or "Kopf" in regeln[0]["wert"]
    klassisch = _profil("profil-beispiel-bloecke-klassisch.yaml")
    k = next(b for b in klassisch["bloecke"] if b["typ"] == "kopf")
    assert csv_bloecke.anfang_regeln(k)[0]["art"] == "kopfzeile"


def test_koepfe_block_beginnt_mit_kopfzeile():
    """Eigene Kopfzeile je Block gehört zum Block (Start = Kopfzeile, nicht erst K)."""
    from fakturafalter.csv_einrichtung import bloecke_vorschlagen, format_erkennen

    fmt = format_erkennen(BEISPIELE / "beispiel-satzart-bloecke-koepfe.csv")
    bloecke, _sa = bloecke_vorschlagen(fmt)
    typen = [b.get("typ") for b in bloecke]
    assert typen[:3] == ["kopf", "positionen", "summen"] or typen[:2] == ["kopf", "positionen"]
    assert int(bloecke[0]["start"]) == 1
    assert "Rechnungsnr" in (bloecke[0].get("kopf") or [])
    assert int(bloecke[1]["start"]) <= 3


def test_gleiche_positionen_gemeinsame_kopfzeile():
    """Eine gemeinsame Kopfzeile wird nicht als eigener leerer Block angelegt."""
    from fakturafalter.csv_einrichtung import bloecke_vorschlagen, format_erkennen

    fmt = format_erkennen(BEISPIELE / "beispiel-satzart-gleiche-positionen.csv")
    bloecke, _sa = bloecke_vorschlagen(fmt)
    typen = [b.get("typ") for b in bloecke]
    assert typen[0] in ("kopf",)
    assert typen.count("positionen") == 1
    # erster Block startet bei der Satzart-Zeile K, nicht bei der gemeinsamen Kopfzeile
    assert int(bloecke[0]["start"]) == 2
