# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.5.0: XML-Eingang (ZUGFeRD/Factur-X, XRechnung CII/UBL) – fiktive Daten."""

from decimal import Decimal

import pytest

from fakturafalter import adapter_xml, cii, pipeline, rechnen

UBL = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
 <cbc:ID>UBL-2026-7</cbc:ID><cbc:IssueDate>2026-10-05</cbc:IssueDate><cbc:DueDate>2026-10-19</cbc:DueDate>
 <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
 <cbc:BuyerReference>04011000-12345-03</cbc:BuyerReference>
 <cac:AccountingSupplierParty><cac:Party><cbc:EndpointID schemeID="EM">rechnung@muster-bau.invalid</cbc:EndpointID>
  <cac:PostalAddress><cbc:StreetName>Musterweg 1</cbc:StreetName><cbc:CityName>Musterstadt</cbc:CityName>
  <cbc:PostalZone>12345</cbc:PostalZone><cac:Country><cbc:IdentificationCode>DE</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
  <cac:PartyTaxScheme><cbc:CompanyID>DE123456788</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
  <cac:PartyLegalEntity><cbc:RegistrationName>Muster Bau GmbH</cbc:RegistrationName></cac:PartyLegalEntity>
 </cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID>K-77</cbc:ID></cac:PartyIdentification>
  <cac:PostalAddress><cbc:StreetName>Amtsplatz 2</cbc:StreetName><cbc:CityName>Beispielhausen</cbc:CityName>
  <cbc:PostalZone>54321</cbc:PostalZone><cac:Country><cbc:IdentificationCode>DE</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
  <cac:PartyLegalEntity><cbc:RegistrationName>Gemeinde Beispielhausen</cbc:RegistrationName></cac:PartyLegalEntity>
 </cac:Party></cac:AccountingCustomerParty>
 <cac:Delivery><cbc:ActualDeliveryDate>2026-09-30</cbc:ActualDeliveryDate></cac:Delivery>
 <cac:PaymentMeans><cbc:PaymentMeansCode>58</cbc:PaymentMeansCode>
  <cac:PayeeFinancialAccount><cbc:ID>DE02120300000000202051</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>
 <cac:PaymentTerms><cbc:Note>Zahlbar in 14 Tagen</cbc:Note></cac:PaymentTerms>
 <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">19.00</cbc:TaxAmount></cac:TaxTotal>
 <cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
  <cbc:TaxInclusiveAmount currencyID="EUR">119.00</cbc:TaxInclusiveAmount></cac:LegalMonetaryTotal>
 <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="HUR">4</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
  <cac:Item><cbc:Name>Montage</cbc:Name><cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent>
  <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>
  <cac:Price><cbc:PriceAmount currencyID="EUR">25.00</cbc:PriceAmount></cac:Price></cac:InvoiceLine>
</Invoice>"""


def _aus_csv(konfig):
    art, rs = pipeline.einlesen(
        pipeline.Path(__file__).parent.parent / "beispiele" / "variante-a_positionen_utf8.csv",
        konfig,
    )
    r = rs[0]
    rechnen.berechnen(r)
    return r


@pytest.mark.parametrize(
    "profil, text, format_",
    [
        ("EN16931", "ZUGFeRD / Factur-X (CII) – Profil EN 16931", "ZUGFERD_EN16931"),
        ("XRECHNUNG", "XRechnung (CII)", "XRECHNUNG_CII"),
    ],
)
def test_cii_rundreise(konfig, tmp_path, profil, text, format_):
    r = _aus_csv(konfig)
    xml = cii.erzeugen(r, profil)
    assert adapter_xml.erkennen(xml) == ("CII", text)
    (tmp_path / "r.xml").write_bytes(xml)
    x = adapter_xml.lesen(tmp_path / "r.xml", konfig)[0]
    assert (x.nummer, x.datum, x.kaeufer.name, x.verkaeufer.ust_id) == (
        r.nummer,
        r.datum,
        r.kaeufer.name,
        r.verkaeufer.ust_id,
    )
    assert [
        (p.bezeichnung, p.menge, p.einheit, p.einzelpreis, p.steuer.satz) for p in x.positionen
    ] == [(p.bezeichnung, p.menge, p.einheit, p.einzelpreis, p.steuer.satz) for p in r.positionen]
    assert x.ausgabeformat == format_ and x.zahlung.iban == r.zahlung.iban
    assert rechnen.berechnen(x).brutto == r.summen.brutto
    assert not [h for h in x.hinweise if h.stufe in ("pruefen", "fehler")]


def test_ubl_und_pipeline(konfig):
    konfig.modus, konfig.pdf_vorlagen = "pdf_xml", []
    (konfig.eingang / "UBL-2026-7.xml").write_text(UBL, encoding="utf-8")
    assert adapter_xml.erkennen(UBL.encode()) == ("UBL", "XRechnung (UBL)")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    assert not lauf.datei_fehler, lauf.datei_fehler
    e = lauf.ergebnisse[0]
    assert not [h for h in e.hinweise if h.startswith("PRUEFEN")], e.hinweise
    assert (e.nummer, e.status, e.brutto, e.kunde) == (
        "UBL-2026-7",
        "ok",
        "119.00",
        "Gemeinde Beispielhausen",
    )
    assert (konfig.ausgang / "UBL-2026-7_zugferd.pdf").exists()


def test_fremdes_xml_und_entitaeten(konfig, tmp_path):
    with pytest.raises(ValueError, match="keine XRechnung"):
        adapter_xml.erkennen(b"<bestellung/>")
    boese = (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        b'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"><cbc:ID>&e;</cbc:ID></Invoice>'
    )
    (tmp_path / "b.xml").write_bytes(boese)
    r = adapter_xml.lesen(tmp_path / "b.xml", konfig)[0]
    assert "root" not in r.nummer
    assert any(h.stufe == "pruefen" for h in r.hinweise)
    assert Decimal("0") == sum((p.menge or 0 for p in r.positionen), Decimal("0"))
