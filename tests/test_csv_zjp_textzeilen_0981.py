# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.9.8.1: Text- und Leerzeilen auch im Standardaufbau zeile_je_position (fiktive Daten)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from fakturafalter import adapter_csv, layout, pipeline, rechnen, sicht, sicht_layout, validierung
from fakturafalter import csv_einrichtung as ce
from fakturafalter.konfig import lade_datei

from .conftest import BEISPIELE

D = Decimal
CSV = BEISPIELE / "variante-zjp_textzeilen.csv"
CSV_ZWEI = BEISPIELE / "variante-zjp_textzeilen_zwei.csv"
PROFIL = BEISPIELE / "profil-variante-zjp-textzeilen.yaml"


def _profil(zusatz=None):
    p = yaml.safe_load(PROFIL.read_text(encoding="utf-8"))
    if zusatz:
        p.setdefault("aufbau", {}).setdefault("textzeile", {}).update(zusatz)
    return p


def _lesen(konfig, name=CSV, profil=None):
    (r,) = adapter_csv.lesen(Path(name), profil or _profil(), konfig)
    rechnen.berechnen(r)
    return r


def test_assistent_erkennt_standardaufbau_und_preisbasis():
    fmt = ce.format_erkennen(CSV)
    assert (fmt.trennzeichen, fmt.dezimal, fmt.datum) == (";", ",", "%d.%m.%Y")
    assert len(fmt.zeilen) == 4  # DOS-Dateiende \\x1a zählt nicht als Zeile
    assert not ce.satzart(fmt) and not ce.bloecke_erkannt(fmt)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    assert z["BT-1"] == "Belegname"
    assert z["BT-153"] == "Bezeichnung"
    assert z["BT-129"] == "Menge"
    assert z["BT-146"] == "Einzelpreis"
    assert z["BT-149"] == "Preisbasis"
    assert z["steuer"] == "Ust-Satz"
    assert not ce.fehlende_pflicht(z)
    p = ce.profil_bauen(
        "zjp-textzeilen",
        CSV,
        fmt,
        z,
        ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])),
        None,
        {"ziel": "BT-154", "verwaist": "BT-22", "zwischen": "vorher"},
    )
    assert p["aufbau"]["art"] == "zeile_je_position"
    assert p["aufbau"]["textzeile"]["verwaist"] == "BT-22"
    assert "BT-149" in p["felder"]["position"]


def test_eine_position_vorspann_und_bt154(konfig):
    r = _lesen(konfig)
    assert r.nummer == "RE-2026-0818"
    assert r.datum == date(2026, 11, 25)
    assert r.kaeufer.name.startswith("Beispielbau GmbH")
    assert len(r.positionen) == 1
    p = r.positionen[0]
    assert p.bezeichnung == "Grundplatte"
    assert p.artikelnummer == "#ART-0000-1111-222/01"
    assert (p.menge, p.einzelpreis, p.preiseinheit) == (D("40.00"), D("9.86"), D("1"))
    assert p.steuer.satz == D("19")
    assert p.nr == "1"
    assert p.menge_roh == "40,00"
    assert p.zeilen_davor == ["Unser Lieferschein B-2026-1650:", ""]
    assert p.kommentar_unten == ["000000-1111-222/01"]
    assert (r.summen.netto, r.summen.ust, r.summen.brutto) == (D("394.40"), D("74.94"), D("469.34"))
    assert r.status == "ok", [str(h) for h in r.hinweise]
    texte = [t for t, _c in r.bemerkungen]
    assert any("Unser Lieferschein B-2026-1650:" in (t or "") for t in texte)
    uz = [t for t, _g in sicht.unterzeilen(p)]
    assert any(t == "000000-1111-222/01" for t in uz)
    assert not any(t.startswith("Beschreibung:") for t in uz)


def test_ohne_positionsspalte_gleiche_erkennung(konfig):
    """Spalte „Position“ auf „nicht verwenden“ (kein BT-126) – so gemeldet, nicht die Ursache."""
    profil = _profil()
    (profil.get("felder") or {}).get("position", {}).pop("BT-126", None)
    r = _lesen(konfig, profil=profil)
    assert len(r.positionen) == 1
    p = r.positionen[0]
    assert p.bezeichnung == "Grundplatte"
    assert p.nr == "1"
    assert p.zeilen_davor == ["Unser Lieferschein B-2026-1650:", ""]
    assert p.kommentar_unten == ["000000-1111-222/01"]
    assert (r.summen.netto, r.summen.ust, r.summen.brutto) == (D("394.40"), D("74.94"), D("469.34"))
    assert r.status == "ok", [str(h) for h in r.hinweise]


def test_kein_zweites_dokument_durch_dateiende(konfig):
    rs = adapter_csv.lesen(CSV, _profil(), konfig)
    assert [r.nummer for r in rs] == ["RE-2026-0818"]


def test_sichtseite_zeigt_kommentar_und_leerzeile_an_ort(konfig):
    r = _lesen(konfig)
    pdf = sicht_layout.erzeugen(r, layout.standard())
    import pdfplumber

    with pdfplumber.open(__import__("io").BytesIO(pdf)) as doc:
        text = doc.pages[0].extract_text() or ""
    # Reihenfolge: Kommentar, (Leerzeile unsichtbar im Text), dann Position
    assert "Unser Lieferschein B-2026-1650:" in text
    assert "Grundplatte" in text
    assert "000000-1111-222/01" in text
    assert text.index("Unser Lieferschein B-2026-1650:") < text.index("Grundplatte")
    assert text.index("Grundplatte") < text.index("000000-1111-222/01")
    assert "Beschreibung:" not in text
    assert "40,00" in text
    assert "394,40 €" in text or "394,40€" in text
    assert "469,34 €" in text or "469,34€" in text
    assert "Gesamtbetrag EUR" not in text
    # Positionsnummer ohne Spalte: 1, nicht die CSV-Zeile 003
    assert (
        " 1 " in f" {text} "
        or text.strip().startswith("1")
        or "\n1 " in text
        or "1 Grundplatte" in text.replace("\n", " ")
    )


def test_platzhalter_und_text_zwischen_positionen(konfig):
    r = _lesen(konfig, CSV_ZWEI)
    assert r.nummer == "RE-2026-0819"
    assert len(r.positionen) == 2
    a, b = r.positionen
    assert a.bezeichnung == "Platte A"
    assert a.nr == "1" and b.nr == "2"
    assert a.zeilen_davor == ["Vorbemerkung zur ersten Position"]
    assert a.kommentar_unten == ["Hinweis zwischen den Positionen"]
    assert b.bezeichnung == "Platte B"
    assert b.zeilen_davor == []
    assert "Nachsatz zur zweiten Position" in "\n".join(b.kommentar_unten)
    uz = [t for t, _g in sicht.unterzeilen(b)]
    assert any(t == "" for t in uz)
    assert (r.summen.netto, r.summen.ust, r.summen.brutto) == (D("70.00"), D("13.30"), D("83.30"))
    assert r.status == "ok", [str(h) for h in r.hinweise]


def test_zwischen_nachher_wird_vorspann_der_naechsten(konfig):
    r = _lesen(konfig, CSV_ZWEI, _profil({"zwischen": "nachher"}))
    a, b = r.positionen
    assert "Hinweis zwischen den Positionen" not in "\n".join(a.kommentar_unten)
    assert b.zeilen_davor == ["Hinweis zwischen den Positionen"]
    assert "Nachsatz zur zweiten Position" in "\n".join(b.kommentar_unten)


def test_verwaist_naechste_haengt_an_erster_position(konfig):
    r = _lesen(konfig, CSV, _profil({"verwaist": "naechste"}))
    p = r.positionen[0]
    assert p.zeilen_davor[0] == "Unser Lieferschein B-2026-1650:"
    assert "Unser Lieferschein B-2026-1650:" in (p.beschreibung or "")
    assert not any("Unser Lieferschein B-2026-1650:" in (t or "") for t, _c in r.bemerkungen)


def test_handprofil_passt_und_laedt(konfig):
    p = lade_datei(PROFIL)
    assert adapter_csv.profil_passt(CSV, p)
    assert adapter_csv.profil_passt(CSV_ZWEI, p)


@pytest.mark.skipif(
    not all(validierung.verfuegbar().values()), reason="Java/KoSIT/Mustang nicht vorhanden"
)
def test_validierung_zjp_textzeilen(konfig):
    r = _lesen(konfig)
    dateien = pipeline.erzeugen(r, konfig, konfig.ausgang)
    erg = validierung.pruefen(dateien)
    assert erg and all(e.gueltig and not e.fehler for e in erg), [e.zeile() for e in erg]


def _mini_csv(tmp_path, zeilen, name="x.csv"):
    kopf = "Belegname;Belegdatum;Kunde1;Strasse;PLZ;Ort;Bezeichnung;Menge;Einheit;Einzelpreis;Ust-Satz;Position"
    d = tmp_path / name
    d.write_text(kopf + "\n" + "\n".join(zeilen) + "\n", encoding="utf-8")
    return d


def _mini_profil(sicht=None, textzeile=None, mit_pos=False):
    p = _profil(textzeile)
    if not mit_pos:
        (p.get("felder") or {}).get("position", {}).pop("BT-126", None)
    else:
        p["felder"]["position"]["BT-126"] = {"spalte": "Position", "optional": True}
    if sicht:
        p.setdefault("sicht", {}).update(sicht)
    return p


def test_null_menge_und_preis_sind_keine_position(konfig, tmp_path):
    csv = _mini_csv(
        tmp_path,
        [
            "RE-1;25.11.2026;Beispielbau GmbH;Musterweg 12;12345;Musterstadt;Kommentar dazu;0,00;Stück;0,00;19;001",
            "RE-1;25.11.2026;Beispielbau GmbH;Musterweg 12;12345;Musterstadt;Platte;2,00;Stück;10,00;19;002",
        ],
    )
    r = _lesen(konfig, csv, _mini_profil())
    assert len(r.positionen) == 1
    assert r.positionen[0].nr == "1"
    assert r.positionen[0].bezeichnung == "Platte"
    assert r.positionen[0].zeilen_davor == ["Kommentar dazu"]
    assert r.summen.netto == D("20.00")


def test_menge_ohne_preis_ist_position(konfig, tmp_path):
    csv = _mini_csv(
        tmp_path,
        [
            "RE-1;25.11.2026;Beispielbau GmbH;Musterweg 12;12345;Musterstadt;Platte;5;Stück;;19;001",
        ],
    )
    r = _lesen(konfig, csv, _mini_profil())
    assert len(r.positionen) == 1
    assert r.positionen[0].menge == D("5")
    assert r.positionen[0].einzelpreis is None


def test_preis_ohne_menge_pruefen_eins_kommentar(konfig, tmp_path):
    zeile = "RE-1;25.11.2026;Beispielbau GmbH;Musterweg 12;12345;Musterstadt;Pauschale;;Stück;50,00;19;001"
    csv = _mini_csv(tmp_path, [zeile])
    r = _lesen(konfig, csv, _mini_profil())
    assert len(r.positionen) == 1
    assert r.positionen[0].einzelpreis == D("50.00")
    assert r.status == "pruefen"

    r2 = _lesen(konfig, csv, _mini_profil(textzeile={"preis_ohne_menge": "eins"}))
    assert r2.positionen[0].menge == D("1")
    assert r2.summen.netto == D("50.00")

    r3 = _lesen(konfig, csv, _mini_profil(textzeile={"preis_ohne_menge": "kommentar"}))
    assert r3.positionen == [] or (len(r3.positionen) == 0)
    # keine Position, Text vor der ersten → BT-22 / keine Summe
    assert r3.summen.netto == 0 or not r3.positionen


def test_erp_nummer_wenn_spalte_zugeordnet(konfig):
    profil = _profil()
    profil["felder"]["position"]["BT-126"] = {"spalte": "Position", "optional": True}
    r = _lesen(konfig, profil=profil)
    assert r.positionen[0].nr == "003"


def test_einheit_wie_in_csv_und_positionsnummer_aus(konfig):
    r = _lesen(konfig, profil=_mini_profil(sicht={"einheit": "csv", "positionsnummer": False}))
    assert r.positionen[0].einheit_roh == "Stück"
    assert sicht.einheit_anzeige(r.positionen[0], r) == "Stück"
    assert r.positionen[0].einheit == "C62"
    pdf = sicht_layout.erzeugen(r, layout.standard())
    import pdfplumber

    with pdfplumber.open(__import__("io").BytesIO(pdf)) as doc:
        text = doc.pages[0].extract_text() or ""
    assert "Stück" in text
    # Positionsnummer ausgeblendet, Inhalt der Position bleibt
    assert "Grundplatte" in text


def test_alte_profile_ohne_sicht_bleiben_lesbar(konfig):
    p = _profil()
    p.pop("sicht", None)
    r = _lesen(konfig, profil=p)
    assert r.positionen[0].nr == "1"
    assert sicht.menge_anzeige(r.positionen[0], r) == "40,00"
    assert sicht.einheit_anzeige(r.positionen[0], r) == "Stk."


def test_xml_bt154_und_bt130(konfig):
    from lxml import etree

    from fakturafalter import cii

    r = _lesen(konfig)
    xml = cii.erzeugen(r, "EN16931")
    wurzel = etree.fromstring(xml)
    ns = {
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    }
    desc = wurzel.find(".//ram:Description", ns)
    assert desc is not None and "000000-1111-222/01" in (desc.text or "")
    qty = wurzel.find(".//ram:BilledQuantity", ns)
    assert qty.get("unitCode") == "C62"
    assert "40" in (qty.text or "")
