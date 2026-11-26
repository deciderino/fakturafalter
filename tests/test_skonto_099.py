# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Strukturiertes Skonto in BT-20 (#SKONTO#), Sichtteil nur Klartext (fiktive Daten, ab 0.9.9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from fakturafalter import (
    adapter_csv,
    adapter_xml,
    cii,
    pdfa,
    rechnen,
    sicht,
    validierung,
    zahlungsziel,
)
from fakturafalter.beispielrechnung import rechnung as beispiel
from fakturafalter.modell import SkontoStufe

D = Decimal
NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}


def _bt20(xml: bytes) -> str:
    root = etree.fromstring(xml)
    el = root.find(".//ram:SpecifiedTradePaymentTerms/ram:Description", NS)
    return el.text or "" if el is not None else ""


def test_skonto_zeile_format():
    z = zahlungsziel.stufe_aus_werten(10, D("2"), None)
    assert zahlungsziel.skonto_zeile(z) == "#SKONTO#TAGE=10#PROZENT=2.00#"
    z2 = zahlungsziel.stufe_aus_werten("10", "2,00", "1.500,00")
    assert zahlungsziel.skonto_zeile(z2) == "#SKONTO#TAGE=10#PROZENT=2.00#BASISBETRAG=1500.00#"
    assert zahlungsziel.stufe_aus_werten(10, None) is None
    assert zahlungsziel.stufe_aus_werten(None, D("2")) is None
    assert zahlungsziel.stufe_aus_werten(10, D("-1")) is None


def test_bt20_bauen_umbruch_nach_jeder_stufe():
    s1 = SkontoStufe(10, D("2.00"))
    s2 = SkontoStufe(20, D("1.00"))
    text = zahlungsziel.bt20_bauen([s1, s2], "zahlbar innerhalb von 30 Tagen ohne Abzug.")
    assert text.startswith("#SKONTO#TAGE=10#PROZENT=2.00#\n#SKONTO#TAGE=20#PROZENT=1.00#\n")
    assert text.endswith("zahlbar innerhalb von 30 Tagen ohne Abzug.")
    # auch ohne Klartext steht der Umbruch nach der letzten Stufe
    nur = zahlungsziel.bt20_bauen([s1], "")
    assert nur == "#SKONTO#TAGE=10#PROZENT=2.00#\n"


def test_bt20_kein_hash_im_klartext_kein_verzug():
    text = zahlungsziel.bt20_bauen([SkontoStufe(10, D("2"))], "2 % Skonto, siehe #Hinweis#.")
    assert "#Hinweis#" not in text
    assert "VERZUG" not in text
    assert text.count("#SKONTO#") == 1
    stufen, klar, probleme = zahlungsziel.bt20_zerlegen(
        "#VERZUG#TAGE=30#PROZENT=9.62#\nMahnung nach 14 Tagen."
    )
    assert stufen == []
    assert "Mahnung nach 14 Tagen." in klar
    assert any("Unzulässige" in p for p in probleme)
    assert "#VERZUG#" not in klar


def test_fehlformat_wird_nicht_als_stufe_gelesen():
    for roh in (
        "#SKONTO#TAGE=10#PROZENT=2,00#",
        "#SKONTO#TAGE=10#PROZENT=2#",
        "#SKONTO#TAGE=10#PROZENT=2.00",
        "#SKONTO#TAGE=10#PROZENT=2.0#",
    ):
        stufen, klar, probleme = zahlungsziel.bt20_zerlegen(roh + "\nKlartext")
        assert stufen == [], roh
        assert probleme, roh
        assert "Klartext" in klar


def test_roundtrip_xml_bt20():
    r = beispiel()
    r.zahlung.skonto = [SkontoStufe(10, D("2.00")), SkontoStufe(20, D("1.00"))]
    r.zahlung.bedingungen = zahlungsziel.aus_stufen(r.datum, r.zahlung.skonto, r.zahlung.ziel_tage)
    r.zahlung.ziel_tage = 14
    r.zahlung.faellig = date(2026, 11, 17)
    xml = cii.erzeugen(r, "EN16931")
    text = _bt20(xml)
    stufen, klar, probleme = zahlungsziel.bt20_zerlegen(text)
    assert not probleme
    assert [(s.tage, s.satz, s.basisbetrag) for s in stufen] == [
        (10, D("2.00"), None),
        (20, D("1.00"), None),
    ]
    assert "2 % Skonto innerhalb von 10 Tagen" in klar
    assert "1 % innerhalb von 20 Tagen" in klar
    assert "#" not in klar
    # erneut schreiben, Werte bleiben gleich
    r2 = beispiel()
    r2.zahlung.skonto = stufen
    r2.zahlung.bedingungen = klar
    r2.zahlung.ziel_tage = 14
    r2.zahlung.faellig = date(2026, 11, 17)
    assert _bt20(cii.erzeugen(r2, "EN16931")) == text


def test_sichtteil_zeigt_nur_klartext():
    r = beispiel()
    r.zahlung.skonto = [SkontoStufe(10, D("2.00"))]
    r.zahlung.bedingungen = zahlungsziel.aus_stufen(r.datum, r.zahlung.skonto, 14)
    import subprocess

    pdf = sicht.erzeugen(r, sprache="de")
    proc = subprocess.run(
        ["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True, check=True
    )
    text = proc.stdout.decode("utf-8")
    assert "2 % Skonto innerhalb von 10 Tagen" in text
    assert "#SKONTO#" not in text
    assert "PROZENT=" not in text


def test_gutschrift_ohne_strukturiertes_skonto():
    r = beispiel()
    r.art = "381"
    r.zahlung.skonto = [SkontoStufe(10, D("2.00"))]
    r.zahlung.bedingungen = zahlungsziel.aus_stufen(r.datum, r.zahlung.skonto, 14)
    text = _bt20(cii.erzeugen(r, "EN16931"))
    assert "#SKONTO#" not in text
    assert "gutgeschrieben" in text.lower() or "Gutschrift" in text or "Betrag" in text


def test_ohne_skonto_unveraendert():
    r = beispiel()
    assert not r.zahlung.skonto
    text = _bt20(cii.erzeugen(r, "EN16931"))
    assert "#SKONTO#" not in text
    assert "#" not in text
    assert "ohne Abzug" in text


def test_xml_import_uebernimmt_skonto(tmp_path, konfig):
    r = beispiel()
    r.zahlung.skonto = [SkontoStufe(10, D("2.00"), D("1500.00"))]
    r.zahlung.bedingungen = zahlungsziel.aus_stufen(r.datum, r.zahlung.skonto, 14)
    xml = cii.erzeugen(r, "EN16931")
    f = tmp_path / "ein.xml"
    f.write_bytes(xml)
    (r2,) = adapter_xml.lesen(f, konfig)
    assert len(r2.zahlung.skonto) == 1
    s = r2.zahlung.skonto[0]
    assert (s.tage, s.satz, s.basisbetrag) == (10, D("2.00"), D("1500.00"))
    assert "#SKONTO#" not in (r2.zahlung.bedingungen or "")
    assert "bezogen auf 1.500,00 EUR" in r2.zahlung.bedingungen


def _csv_profil():
    return {
        "profil": "skonto-test",
        "datei": {"kodierung": "utf-8", "trennzeichen": ";", "kopfzeile": True},
        "zahlen": {"dezimal": ",", "tausender": "."},
        "datum": {"format": "%d.%m.%Y"},
        "aufbau": {"art": "zeile_je_position", "rechnung_schluessel": "Rechnungsnummer"},
        "felder": {
            "kopf": {
                "BT-1": {"spalte": "Rechnungsnummer"},
                "BT-2": {"spalte": "Rechnungsdatum", "typ": "datum"},
                "BT-72": {"spalte": "Leistungsdatum", "typ": "datum", "optional": True},
                "BT-44": {"spalte": "Kundenname"},
                "BT-50": {"spalte": "Straße"},
                "BT-53": {"spalte": "PLZ"},
                "BT-52": {"spalte": "Ort"},
                "skonto_satz": {"spalte": "Skonto", "typ": "prozent", "optional": True},
                "skonto_tage": {
                    "spalte": "Zahlungsziel mit Skonto",
                    "typ": "tage",
                    "optional": True,
                },
                "skonto_basisbetrag": {
                    "spalte": "Skonto-Basisbetrag",
                    "typ": "zahl",
                    "optional": True,
                },
                "skonto_satz_2": {"spalte": "Skonto 2", "typ": "prozent", "optional": True},
                "skonto_tage_2": {
                    "spalte": "Zahlungsziel mit Skonto 2",
                    "typ": "tage",
                    "optional": True,
                },
                "zahlungsziel_tage": {"spalte": "Zahlungsziel", "typ": "tage", "optional": True},
            },
            "position": {
                "BT-153": {"spalte": "Bezeichnung"},
                "BT-129": {"spalte": "Menge", "typ": "zahl"},
                "BT-130": {"spalte": "Einheit", "optional": True},
                "BT-146": {"spalte": "Einzelpreis", "typ": "zahl"},
                "steuer": {"spalte": "Steuersatz"},
            },
        },
        "mappings": {"steuer": {"unbekannt": "satz"}, "einheiten": {"unbekannt": "allgemein"}},
    }


def test_csv_zwei_stufen(konfig, tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text(
        "Rechnungsnummer;Rechnungsdatum;Leistungsdatum;Kundenname;Straße;PLZ;Ort;"
        "Bezeichnung;Menge;Einheit;Einzelpreis;Steuersatz;"
        "Zahlungsziel;Skonto;Zahlungsziel mit Skonto;Skonto 2;Zahlungsziel mit Skonto 2\n"
        "RE-2026-1101;26.11.2026;26.11.2026;Beispiel Handel GmbH;Beispielweg 5;12345;Musterstadt;"
        "Beratung;1;Stück;100,00;19;30;2;10;1;20\n",
        encoding="utf-8",
    )
    (r,) = adapter_csv.lesen(csv, _csv_profil(), konfig)
    rechnen.berechnen(r)
    assert [(s.tage, s.satz) for s in r.zahlung.skonto] == [(10, D("2")), (20, D("1"))]
    assert r.zahlung.ziel_tage == 30
    assert r.zahlung.faellig == date(2026, 12, 26)
    assert "2 % Skonto innerhalb von 10 Tagen (bis 06.12.2026)" in r.zahlung.bedingungen
    assert "#SKONTO#" not in r.zahlung.bedingungen
    text = _bt20(cii.erzeugen(r, "EN16931"))
    assert text.startswith("#SKONTO#TAGE=10#PROZENT=2.00#\n#SKONTO#TAGE=20#PROZENT=1.00#\n")


def test_csv_ohne_skonto_unveraendert(konfig, tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text(
        "Rechnungsnummer;Rechnungsdatum;Leistungsdatum;Kundenname;Straße;PLZ;Ort;"
        "Bezeichnung;Menge;Einheit;Einzelpreis;Steuersatz;Zahlungsziel\n"
        "RE-2026-1102;26.11.2026;26.11.2026;Beispiel Handel GmbH;Beispielweg 5;12345;Musterstadt;"
        "Beratung;1;Stück;100,00;19;14\n",
        encoding="utf-8",
    )
    (r,) = adapter_csv.lesen(csv, _csv_profil(), konfig)
    rechnen.berechnen(r)
    assert r.zahlung.skonto == []
    assert "#SKONTO#" not in (r.zahlung.bedingungen or "")
    assert "#" not in _bt20(cii.erzeugen(r, "EN16931"))


def _xr_fertig(r):
    """Pflichtangaben für eine gültige XRechnung 3.0 (fiktiv)."""
    r.leitweg_id = r.leitweg_id or "04011000-12345-03"
    r.verkaeufer.elektronische_adresse = r.verkaeufer.elektronische_adresse or "rechnung@musterwerk.example"
    r.verkaeufer.kontakt_name = r.verkaeufer.kontakt_name or "Erika Muster"
    r.verkaeufer.kontakt_telefon = r.verkaeufer.kontakt_telefon or "+49 711 000000"
    r.kaeufer.elektronische_adresse = r.kaeufer.elektronische_adresse or "rechnung@nordlicht.example"
    return r


def _pruefen(r, profil="EN16931"):
    xml = cii.erzeugen(r, profil)
    pdf = pdfa.zugferd_pdf(
        sicht.erzeugen(r, sprache="de"),
        xml,
        titel=f"Rechnung {r.nummer}",
        autor=r.verkaeufer.name,
        beschreibung=f"Rechnung {r.nummer}",
    )
    return xml, pdf


@pytest.mark.validierung
@pytest.mark.skipif(
    not all(validierung.verfuegbar().values()), reason="Java/KoSIT/Mustang nicht vorhanden"
)
def test_validierung_eine_und_zwei_stufen(tmp_path, konfig):
    faelle = []
    r1 = beispiel()
    r1.nummer = "RE-2026-2101"
    _xr_fertig(r1)
    r1.zahlung.skonto = [SkontoStufe(10, D("2.00"))]
    r1.zahlung.bedingungen = zahlungsziel.aus_stufen(r1.datum, r1.zahlung.skonto, 14)
    r1.zahlung.faellig = date(2026, 11, 17)
    faelle.append(("eine", r1))
    r2 = beispiel()
    r2.nummer = "RE-2026-2102"
    _xr_fertig(r2)
    r2.zahlung.skonto = [SkontoStufe(10, D("2.00")), SkontoStufe(20, D("1.00"))]
    r2.zahlung.bedingungen = zahlungsziel.aus_stufen(r2.datum, r2.zahlung.skonto, 14)
    r2.zahlung.faellig = date(2026, 11, 17)
    faelle.append(("zwei", r2))
    dateien = []
    for name, r in faelle:
        xml, pdf = _pruefen(r, "XRECHNUNG")
        xf = tmp_path / f"{name}.xml"
        pf = tmp_path / f"{name}.pdf"
        xf.write_bytes(xml)
        pf.write_bytes(pdf)
        dateien.extend([xf, pf])
        # ZUGFeRD (EN16931) ebenfalls, Strukturzeilen müssen auch dort stehen
        _zxml, zpdf = _pruefen(r, "EN16931")
        assert "#SKONTO#" in _bt20(_zxml)
        zf = tmp_path / f"{name}-zf.pdf"
        zf.write_bytes(zpdf)
        dateien.append(zf)
    erg = validierung.pruefen(dateien)
    assert erg and all(e.gueltig and not e.fehler for e in erg), [e.zeile() for e in erg]
