# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Test-Setup „Industrie“ (beispiele/industrie/, erfunden): Normteile-Großhandel mit Preisen „pro 100 Stk“
neben Stückpreisen und Stunden. PDF + CSV lernt die Vorlage, danach liest „Nur PDF“ dieselben Werte."""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from fakturafalter import (
    absender,
    adapter_csv,
    adapter_pdf,
    pdferkennung,
    pipeline,
    rechnen,
    validierung,
)
from fakturafalter.konfig import lade_konfig
from fakturafalter.pflichtpruefung import iban_gueltig, ust_id_de_gueltig

BSP = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"


@pytest.fixture
def k(tmp_path):
    k = lade_konfig(BSP / "konfiguration-pdf-csv.yaml")
    for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen"):
        setattr(k, n, tmp_path / n)
        (tmp_path / n).mkdir()
    return k


def lauf(k, *dateien):
    for d in dateien:
        shutil.copy(d, k.eingang)
    return pipeline.verarbeiten(sorted(k.eingang.iterdir()), k)


def nummern():
    return [p.stem for p in sorted((BSP / "eingang").glob("NB-26-*.pdf"))]


def test_setup_vollstaendig_und_pruefziffern(k):
    assert len(nummern()) == 8
    (p,) = [x for x in k.csv_profile if not x.get("_eingebaut")]
    assert ust_id_de_gueltig(p["verkaeufer"]["ust_id"]) and iban_gueltig(p["zahlung"]["iban"])
    a = absender.aus_csv((BSP / "absender-normteile.csv").read_bytes())
    assert a.name == "Normteile Brückner GmbH" and not a.fehlt()
    zeilen = pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(BSP / "eingang" / "NB-26-1001.pdf"))
    erkannt = absender.erkennen_aus_zeilen(zeilen)
    assert (erkannt.name, erkannt.ust_id, erkannt.iban) == (a.name, a.ust_id, a.iban)


@pytest.mark.validierung
def test_pdf_csv_lernt_dann_nur_pdf(k):
    nrn = nummern()
    for nr in nrn[:7]:
        (e,) = lauf(
            k, BSP / "eingang" / f"normteile_{nr}.csv", BSP / "eingang" / f"{nr}.pdf"
        ).ergebnisse
        assert e.status == "ok", e.hinweise
        assert any("ohne Abweichung" in h for h in e.hinweise)
    (p,) = [x for x in k.csv_profile if not x.get("_eingebaut")]
    (v,) = pdferkennung.vorlagen_laden(p)
    assert "steuer_fest" in v["positionen"] and "BT-149" in v["positionen"]["spalten"]
    assert pdferkennung.sicher(v, pdferkennung.einstellungen(p)), v["statistik"]

    p["pdf_erkennung"] = {"nur_pdf": True}
    pdf8 = BSP / "eingang" / f"{nrn[7]}.pdf"
    (e,) = lauf(k, pdf8).ergebnisse
    assert e.status == "ok", e.hinweise
    (soll,) = adapter_csv.lesen(BSP / "eingang" / f"normteile_{nrn[7]}.csv", p, k)
    soll.summen = rechnen.berechnen(soll)
    assert any(h.startswith("INFO: Automatisch (Nur PDF)") for h in e.hinweise)
    ist, grund = pdferkennung.nur_pdf(
        pdf8, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf8)), k.profile, k
    )
    assert ist is not None, grund
    ist.summen = rechnen.berechnen(ist)
    assert any(x.preiseinheit == 100 for x in ist.positionen) and any(
        x.preiseinheit == 1 for x in ist.positionen
    )
    assert Decimal(e.brutto) == soll.summen.brutto
    assert [(x.menge, x.einheit, x.einzelpreis, x.preiseinheit) for x in ist.positionen] == [
        (x.menge, x.einheit, x.einzelpreis, x.preiseinheit) for x in soll.positionen
    ]
    assert (ist.summen.netto, ist.summen.brutto) == (soll.summen.netto, soll.summen.brutto)
    assert {x.einheit for x in ist.positionen} <= {"H87", "HUR"}
    if all(validierung.verfuegbar().values()):
        erg = validierung.pruefen(sorted(k.ausgang.rglob("*.pdf")))
        assert len(erg) == 16 and all(x.gueltig and not x.fehler for x in erg), [
            x.zeile() for x in erg
        ]


@pytest.mark.validierung
def test_adresszeile_2_als_cii_linetwo(k, tmp_path):
    from lxml import etree

    from fakturafalter import cii

    (p,) = [x for x in k.csv_profile if not x.get("_eingebaut")]
    (r,) = adapter_csv.lesen(BSP / "eingang" / "normteile_NB-26-1001.csv", p, k)
    r.kaeufer.anschrift.zusatz = "Abteilung Einkauf"
    r.verkaeufer.anschrift.zusatz = "Haus B"
    r.summen = rechnen.berechnen(r)
    xml = cii.erzeugen(r)
    baum = etree.fromstring(xml)
    ns = {
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    }
    for rolle, soll in (("BuyerTradeParty", "Abteilung Einkauf"), ("SellerTradeParty", "Haus B")):
        (a,) = baum.findall(f".//ram:{rolle}/ram:PostalTradeAddress", ns)
        namen = [etree.QName(e).localname for e in a]
        assert namen.index("LineOne") + 1 == namen.index("LineTwo") < namen.index("CityName")
        assert a.find("ram:LineTwo", ns).text == soll
    if all(validierung.verfuegbar().values()):
        d = tmp_path / "linetwo.xml"
        d.write_bytes(xml)
        (e,) = validierung.kosit([d])
        assert e.gueltig and not e.fehler, e.zeile()


def test_adresszeile_3_und_kontakt_im_cii(k):
    """BT-163 -> ram:LineThree, BT-56 -> ram:PersonName in BuyerTradeParty; BT-51 bleibt LineTwo."""
    from lxml import etree

    from fakturafalter import aufbau, cii

    assert aufbau.KAEUFER_FELDER["BT-163"] == "anschrift.zeile3"
    assert aufbau.KAEUFER_FELDER["BT-51"] == "anschrift.zusatz"
    assert aufbau.KAEUFER_FELDER["BT-56"] == "kontakt_name"
    (p,) = [x for x in k.csv_profile if not x.get("_eingebaut")]
    (r,) = adapter_csv.lesen(BSP / "eingang" / "normteile_NB-26-1001.csv", p, k)
    r.kaeufer.anschrift.zusatz = "Abteilung Einkauf"
    r.kaeufer.anschrift.zeile3 = "Gebäude C"
    r.kaeufer.kontakt_name = "Frau Muster"
    r.summen = rechnen.berechnen(r)
    baum = etree.fromstring(cii.erzeugen(r))
    ns = {
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    }
    (a,) = baum.findall(".//ram:BuyerTradeParty/ram:PostalTradeAddress", ns)
    namen = [etree.QName(e).localname for e in a]
    assert namen.index("LineOne") + 1 == namen.index("LineTwo")
    assert namen.index("LineTwo") + 1 == namen.index("LineThree") < namen.index("CityName")
    assert a.find("ram:LineTwo", ns).text == "Abteilung Einkauf"
    assert a.find("ram:LineThree", ns).text == "Gebäude C"
    (c,) = baum.findall(".//ram:BuyerTradeParty/ram:DefinedTradeContact/ram:PersonName", ns)
    assert c.text == "Frau Muster"
