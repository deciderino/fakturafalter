# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""UN/CEFACT CII (D16B/D22B-kompatibel) für ZUGFeRD 2.x / Factur-X Profil EN 16931 und XRechnung 3.0 (CII).

Eigene Erzeugung mit lxml (BSD) – keine weitere Abhängigkeit, volle Kontrolle über Reihenfolge der Elemente.
"""

from __future__ import annotations

import base64
import copy
from datetime import date
from decimal import Decimal

from lxml import etree

from . import sicht, steuerfaelle
from .modell import Anschrift, Lieferung, Partei, Rechnung, ZuAbschlag

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
GUIDELINE = {
    "EN16931": "urn:cen.eu:en16931:2017",
    "XRECHNUNG": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
}
PROZESS_PEPPOL = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


def _q(tag: str) -> str:
    p, n = tag.split(":")
    return f"{{{NS[p]}}}{n}"


def _e(parent, tag: str, text=None, **attrib):
    el = etree.SubElement(parent, _q(tag), {k: str(v) for k, v in attrib.items()})
    if text is not None:
        el.text = str(text)
    return el


def betrag(d: Decimal) -> str:
    return f"{d.quantize(Decimal('0.01')):f}"


def _zahl(d: Decimal, min_stellen: int = 0, max_stellen: int = 4) -> str:
    d = d.quantize(Decimal(1).scaleb(-max_stellen)).normalize()
    s = f"{d:f}"
    if min_stellen:
        ganz, _, frac = s.partition(".")
        s = f"{ganz}.{frac.ljust(min_stellen, '0')}"
    return s


def satz(d: Decimal) -> str:
    return _zahl(d, 2, 2)


def _datum(parent, tag: str, d: date):
    w = _e(parent, tag)
    _e(w, "udt:DateTimeString", d.strftime("%Y%m%d"), format="102")


def _anschrift(parent, a: Anschrift, land_standard: str = "DE"):
    el = _e(parent, "ram:PostalTradeAddress")
    for tag, wert in (
        ("ram:PostcodeCode", a.plz),
        ("ram:LineOne", a.strasse),
        ("ram:LineTwo", a.zusatz),
        ("ram:LineThree", a.zeile3),
        ("ram:CityName", a.ort),
    ):
        if wert:
            _e(el, tag, wert)
    _e(el, "ram:CountryID", a.land or land_standard)
    if a.region:
        _e(el, "ram:CountrySubDivisionName", a.region)  # BT-39/54/79
    return el


def _partei(
    parent, tag: str, p: Partei, verkaeufer: bool, mit_kennung: bool = True, ohne_ust_id: bool = False
):
    """``ohne_ust_id``: Kategorie O (nicht steuerbar) – BR-O-02 verbietet BT-31/BT-48 im XML."""
    tp = _e(parent, tag)
    if mit_kennung and p.kennung:
        _e(tp, "ram:ID", p.kennung)  # BT-29 / BT-46
    _e(tp, "ram:Name", p.name)  # BT-27 / BT-44
    if verkaeufer and p.rechtliches:
        _e(tp, "ram:Description", p.rechtliches)  # BT-33
    if p.register or p.handelsname:
        lo = _e(tp, "ram:SpecifiedLegalOrganization")
        if p.register:
            _e(lo, "ram:ID", p.register)  # BT-30 / BT-47
        if p.handelsname:
            _e(lo, "ram:TradingBusinessName", p.handelsname)  # BT-28 / BT-45
    if p.kontakt_name or p.kontakt_telefon or p.kontakt_email:  # BG-6 / BG-9
        c = _e(tp, "ram:DefinedTradeContact")
        if p.kontakt_name:
            _e(c, "ram:PersonName", p.kontakt_name)
        if p.kontakt_telefon:
            _e(
                _e(c, "ram:TelephoneUniversalCommunication"),
                "ram:CompleteNumber",
                p.kontakt_telefon,
            )
        if p.kontakt_email:
            _e(_e(c, "ram:EmailURIUniversalCommunication"), "ram:URIID", p.kontakt_email)
    _anschrift(tp, p.anschrift)
    if p.elektronische_adresse:
        _e(
            _e(tp, "ram:URIUniversalCommunication"),
            "ram:URIID",
            p.elektronische_adresse,
            schemeID="EM",
        )  # BT-34/BT-49
    if p.ust_id and not ohne_ust_id:
        _e(_e(tp, "ram:SpecifiedTaxRegistration"), "ram:ID", p.ust_id, schemeID="VA")
    if verkaeufer and p.steuernummer:
        _e(_e(tp, "ram:SpecifiedTaxRegistration"), "ram:ID", p.steuernummer, schemeID="FC")
    return tp


def _zu_abschlag(parent, za: ZuAbschlag, beleg: bool):
    """BG-20/21 (beleg=True, mit Steuer) bzw. BG-27/28."""
    el = _e(parent, "ram:SpecifiedTradeAllowanceCharge")
    _e(_e(el, "ram:ChargeIndicator"), "udt:Indicator", "true" if za.zuschlag else "false")
    if za.prozent is not None:
        _e(el, "ram:CalculationPercent", _zahl(za.prozent, 2))
    if za.ist_basis is not None:
        _e(el, "ram:BasisAmount", betrag(za.ist_basis))
    _e(el, "ram:ActualAmount", betrag(za.ist_betrag))
    if za.grund_code:
        _e(el, "ram:ReasonCode", za.grund_code)
    if za.grund:
        _e(el, "ram:Reason", za.grund)
    if beleg and za.steuer is not None:
        t = _e(el, "ram:CategoryTradeTax")
        _e(t, "ram:TypeCode", "VAT")
        _e(t, "ram:CategoryCode", za.steuer.kategorie)
        if za.steuer.kategorie != "O":  # BR-O-06/07: ohne Satz
            _e(t, "ram:RateApplicablePercent", satz(za.steuer.satz))
    return el


def _zeitraum(parent, von: date | None, bis: date | None):
    if von or bis:
        bp = _e(parent, "ram:BillingSpecifiedPeriod")
        if von:
            _datum(bp, "ram:StartDateTime", von)
        if bis:
            _datum(bp, "ram:EndDateTime", bis)


def _referenz(parent, tag: str, nummer: str, typ: str = "", schema: str = ""):
    d = _e(parent, tag)
    _e(d, "ram:IssuerAssignedID", nummer)
    if typ:
        _e(d, "ram:TypeCode", typ)
    if schema:
        _e(d, "ram:ReferenceTypeCode", schema)
    return d


def lieferung_fuer_xml(r: Rechnung) -> Lieferung:
    """Innergemeinschaftliche Lieferung braucht das Lieferland BT-80 (BR-IC-12): ohne eigene Lieferanschrift gilt
    die Anschrift des Käufers (vollständig, damit auch BR-DE-10/11 der XRechnung halten)."""
    lf = r.lieferung
    if lf.anschrift or not any(z.steuer.kategorie == "K" for z in r.summen.steuerzeilen):
        return lf
    k = r.kaeufer
    neu = copy.deepcopy(lf)
    neu.name = neu.name or k.name
    neu.anschrift = copy.deepcopy(k.anschrift)
    neu.anschrift.land = neu.anschrift.land or "DE"
    return neu


kurs_text = steuerfaelle.kurs_text  # ab 0.9.7 in steuerfaelle (auch für den Sichtteil)


def bemerkungen_fuer_xml(r: Rechnung) -> list[tuple[str, str]]:
    """BG-1: Bemerkungen; bei Fremdwährung zusätzlich der Kurs (EN 16931 hat kein eigenes Kursfeld)."""
    out = list(r.bemerkungen)
    kt = kurs_text(r)
    if kt and not any(t.strip().casefold().startswith(("umrechnungskurs", "exchange rate")) for t, _ in out):
        out.append((kt, ""))
    return out


def erzeugen(r: Rechnung, profil: str = "EN16931") -> bytes:
    """Rechnung -> CII-XML (bytes, UTF-8). ``profil``: EN16931 | XRECHNUNG.
    Reihenfolge der Elemente nach dem CII-D16B-Schema (CrossIndustryInvoice_100pD16B.xsd)."""
    s = r.summen
    root = etree.Element(_q("rsm:CrossIndustryInvoice"), nsmap=NS)
    ctx = _e(root, "rsm:ExchangedDocumentContext")
    if profil == "XRECHNUNG":
        _e(
            _e(ctx, "ram:BusinessProcessSpecifiedDocumentContextParameter"),
            "ram:ID",
            PROZESS_PEPPOL,
        )  # BT-23
    _e(
        _e(ctx, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", GUIDELINE[profil]
    )  # BT-24

    doc = _e(root, "rsm:ExchangedDocument")
    _e(doc, "ram:ID", r.nummer)  # BT-1
    _e(doc, "ram:TypeCode", r.art)  # BT-3
    _datum(doc, "ram:IssueDateTime", r.datum)  # BT-2
    for text, code in bemerkungen_fuer_xml(r):  # BG-1
        n = _e(doc, "ram:IncludedNote")
        _e(n, "ram:Content", text)
        if code:
            _e(n, "ram:SubjectCode", code)

    tx = _e(root, "rsm:SupplyChainTradeTransaction")
    for p in r.positionen:  # BG-25
        li = _e(tx, "ram:IncludedSupplyChainTradeLineItem")
        ld = _e(li, "ram:AssociatedDocumentLineDocument")
        _e(ld, "ram:LineID", p.nr)  # BT-126
        if p.notiz:
            _e(_e(ld, "ram:IncludedNote"), "ram:Content", p.notiz)  # BT-127
        prod = _e(li, "ram:SpecifiedTradeProduct")
        if p.standard_id:
            _e(
                prod,
                "ram:GlobalID",
                p.standard_id,
                **({"schemeID": p.standard_schema} if p.standard_schema else {}),
            )  # BT-157
        if p.artikelnummer:
            _e(prod, "ram:SellerAssignedID", p.artikelnummer)  # BT-155
        if p.kaeufer_artikelnummer:
            _e(prod, "ram:BuyerAssignedID", p.kaeufer_artikelnummer)  # BT-156
        _e(prod, "ram:Name", p.bezeichnung)  # BT-153
        if p.beschreibung:
            _e(prod, "ram:Description", p.beschreibung)  # BT-154
        for m in p.merkmale:  # BG-32
            pc = _e(prod, "ram:ApplicableProductCharacteristic")
            _e(pc, "ram:Description", m.name)  # BT-160
            _e(pc, "ram:Value", m.wert)  # BT-161
        for k in p.klassifizierungen:  # BT-158
            attr = {"listID": k.schema} if k.schema else {}
            if k.version:
                attr["listVersionID"] = k.version
            _e(_e(prod, "ram:DesignatedProductClassification"), "ram:ClassCode", k.code, **attr)
        if p.ursprungsland:
            _e(_e(prod, "ram:OriginTradeCountry"), "ram:ID", p.ursprungsland)  # BT-159
        ag = _e(li, "ram:SpecifiedLineTradeAgreement")
        if p.bestellposition:
            _e(
                _e(ag, "ram:BuyerOrderReferencedDocument"), "ram:LineID", p.bestellposition
            )  # BT-132
        if p.bruttopreis is not None:
            gp = _e(ag, "ram:GrossPriceProductTradePrice")
            _e(gp, "ram:ChargeAmount", _zahl(p.bruttopreis, 2))  # BT-148
            if p.preiseinheit != 1:
                _e(gp, "ram:BasisQuantity", _zahl(p.preiseinheit), unitCode=p.einheit)
            if p.preisrabatt:
                ac = _e(gp, "ram:AppliedTradeAllowanceCharge")
                _e(_e(ac, "ram:ChargeIndicator"), "udt:Indicator", "false")
                _e(ac, "ram:ActualAmount", _zahl(p.preisrabatt, 2))  # BT-147
        np_ = _e(ag, "ram:NetPriceProductTradePrice")
        _e(np_, "ram:ChargeAmount", _zahl(p.einzelpreis, 2))  # BT-146
        if p.preiseinheit != 1:
            _e(np_, "ram:BasisQuantity", _zahl(p.preiseinheit), unitCode=p.einheit)  # BT-149/BT-150
        _e(
            _e(li, "ram:SpecifiedLineTradeDelivery"),
            "ram:BilledQuantity",
            _zahl(p.menge),
            unitCode=p.einheit,
        )  # BT-129/130
        st = _e(li, "ram:SpecifiedLineTradeSettlement")
        t = _e(st, "ram:ApplicableTradeTax")
        _e(t, "ram:TypeCode", "VAT")
        _e(t, "ram:CategoryCode", p.steuer.kategorie)  # BT-151
        if p.steuer.kategorie != "O":  # BR-O-05: „nicht steuerbar“ ohne Satz
            _e(t, "ram:RateApplicablePercent", satz(p.steuer.satz))  # BT-152
        _zeitraum(st, p.leistung_von, p.leistung_bis)  # BG-26
        for za in p.zu_abschlaege:  # BG-27/BG-28
            _zu_abschlag(st, za, beleg=False)
        _e(
            _e(st, "ram:SpecifiedTradeSettlementLineMonetarySummation"),
            "ram:LineTotalAmount",
            betrag(p.netto),
        )  # BT-131
        if p.objektkennung:
            _referenz(st, "ram:AdditionalReferencedDocument", p.objektkennung, "130")  # BT-128
        if p.buchungsreferenz:
            _e(
                _e(st, "ram:ReceivableSpecifiedTradeAccountingAccount"),
                "ram:ID",
                p.buchungsreferenz,
            )  # BT-133

    ref = r.referenzen
    ag = _e(tx, "ram:ApplicableHeaderTradeAgreement")
    buyer_ref = r.leitweg_id
    if profil == "XRECHNUNG" and not buyer_ref:
        buyer_ref = r.kundennummer
    if buyer_ref:
        _e(ag, "ram:BuyerReference", buyer_ref)  # BT-10
    nicht_steuerbar = any(z.steuer.kategorie == "O" for z in s.steuerzeilen)
    _partei(ag, "ram:SellerTradeParty", r.verkaeufer, True, ohne_ust_id=nicht_steuerbar)  # BG-4
    _partei(ag, "ram:BuyerTradeParty", r.kaeufer, False, ohne_ust_id=nicht_steuerbar)  # BG-7
    sv = r.steuervertreter
    if sv and sv.name:  # BG-11
        tp = _e(ag, "ram:SellerTaxRepresentativeTradeParty")
        _e(tp, "ram:Name", sv.name)  # BT-62
        _anschrift(tp, sv.anschrift)  # BG-12
        if sv.ust_id and not nicht_steuerbar:
            _e(_e(tp, "ram:SpecifiedTaxRegistration"), "ram:ID", sv.ust_id, schemeID="VA")  # BT-63
    if ref.auftrag:
        _referenz(ag, "ram:SellerOrderReferencedDocument", ref.auftrag)  # BT-14
    if r.bestellnummer:
        _referenz(ag, "ram:BuyerOrderReferencedDocument", r.bestellnummer)  # BT-13
    if ref.vertrag:
        _referenz(ag, "ram:ContractReferencedDocument", ref.vertrag)  # BT-12
    for a in r.anhaenge:  # BG-24
        d = _e(ag, "ram:AdditionalReferencedDocument")
        _e(d, "ram:IssuerAssignedID", a.kennung)  # BT-122
        if a.uri:
            _e(d, "ram:URIID", a.uri)  # BT-124
        _e(d, "ram:TypeCode", "916")
        if a.beschreibung:
            _e(d, "ram:Name", a.beschreibung)  # BT-123
        if a.daten:
            _e(
                d,
                "ram:AttachmentBinaryObject",
                base64.b64encode(a.daten).decode("ascii"),
                mimeCode=a.mime,
                filename=a.dateiname or a.kennung,
            )  # BT-125
    if ref.ausschreibung:
        _referenz(ag, "ram:AdditionalReferencedDocument", ref.ausschreibung, "50")  # BT-17
    if ref.objekt:
        _referenz(
            ag, "ram:AdditionalReferencedDocument", ref.objekt, "130", ref.objekt_schema
        )  # BT-18
    if ref.projekt:
        pj = _e(ag, "ram:SpecifiedProcuringProject")
        _e(pj, "ram:ID", ref.projekt)  # BT-11
        _e(pj, "ram:Name", ref.projekt_name or ref.projekt)

    de = _e(tx, "ram:ApplicableHeaderTradeDelivery")
    lf = lieferung_fuer_xml(r)
    if lf:  # BG-13
        tp = _e(de, "ram:ShipToTradeParty")
        if lf.ort_id:
            if lf.ort_schema:
                _e(tp, "ram:GlobalID", lf.ort_id, schemeID=lf.ort_schema)  # BT-71
            else:
                _e(tp, "ram:ID", lf.ort_id)
        if lf.name:
            _e(tp, "ram:Name", lf.name)  # BT-70
        if lf.anschrift:
            _anschrift(tp, lf.anschrift, r.kaeufer.anschrift.land or "DE")  # BG-15
    if r.leistungsdatum:
        _datum(
            _e(de, "ram:ActualDeliverySupplyChainEvent"), "ram:OccurrenceDateTime", r.leistungsdatum
        )  # BT-72
    if ref.lieferschein:
        _referenz(de, "ram:DespatchAdviceReferencedDocument", ref.lieferschein)  # BT-16
    if ref.wareneingang:
        _referenz(de, "ram:ReceivingAdviceReferencedDocument", ref.wareneingang)  # BT-15

    se = _e(tx, "ram:ApplicableHeaderTradeSettlement")
    z = r.zahlung
    if z.lastschrift and z.glaeubiger_id:
        _e(se, "ram:CreditorReferenceID", z.glaeubiger_id)  # BT-90
    _e(se, "ram:PaymentReference", z.verwendungszweck or r.nummer)  # BT-83
    if r.steuerwaehrung and s.ust_steuerwaehrung is not None:
        _e(se, "ram:TaxCurrencyCode", r.steuerwaehrung)  # BT-6
    _e(se, "ram:InvoiceCurrencyCode", r.waehrung)  # BT-5
    ze = r.zahlungsempfaenger
    if ze and ze.name:  # BG-10
        tp = _e(se, "ram:PayeeTradeParty")
        if ze.kennung:
            _e(tp, "ram:ID", ze.kennung)  # BT-60
        _e(tp, "ram:Name", ze.name)  # BT-59
        if ze.register:
            _e(_e(tp, "ram:SpecifiedLegalOrganization"), "ram:ID", ze.register)  # BT-61
    if z.art:
        pm = _e(se, "ram:SpecifiedTradeSettlementPaymentMeans")  # BG-16
        _e(pm, "ram:TypeCode", z.art)  # BT-81
        if z.info:
            _e(pm, "ram:Information", z.info)  # BT-82
        if z.karte:  # BG-18
            fc = _e(pm, "ram:ApplicableTradeSettlementFinancialCard")
            _e(fc, "ram:ID", z.karte)  # BT-87
            if z.karteninhaber:
                _e(fc, "ram:CardholderName", z.karteninhaber)  # BT-88
        if z.lastschrift and z.lastschrift_iban:
            _e(
                _e(pm, "ram:PayerPartyDebtorFinancialAccount"), "ram:IBANID", z.lastschrift_iban
            )  # BT-91
        if z.iban and not z.lastschrift:
            acc = _e(pm, "ram:PayeePartyCreditorFinancialAccount")
            _e(acc, "ram:IBANID", z.iban)  # BT-84
            if z.kontoinhaber:
                _e(acc, "ram:AccountName", z.kontoinhaber)  # BT-85
        if z.bic and not z.lastschrift:
            _e(
                _e(pm, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID", z.bic
            )  # BT-86
    for zl in s.steuerzeilen:  # BG-23
        t = _e(se, "ram:ApplicableTradeTax")
        _e(t, "ram:CalculatedAmount", betrag(zl.betrag))  # BT-117
        _e(t, "ram:TypeCode", "VAT")
        if zl.steuer.befreiungsgrund:
            _e(t, "ram:ExemptionReason", zl.steuer.befreiungsgrund)  # BT-120
        _e(t, "ram:BasisAmount", betrag(zl.basis))  # BT-116
        _e(t, "ram:CategoryCode", zl.steuer.kategorie)  # BT-118
        if zl.steuer.befreiungscode:
            _e(t, "ram:ExemptionReasonCode", zl.steuer.befreiungscode)  # BT-121
        if zl.steuer.kategorie != "O":  # BR-O-10: ohne Satz
            _e(t, "ram:RateApplicablePercent", satz(zl.steuer.satz))  # BT-119
    _zeitraum(se, r.leistung_von, r.leistung_bis)  # BG-14 Rechnungszeitraum
    for za in r.zu_abschlaege:  # BG-20/BG-21
        _zu_abschlag(se, za, beleg=True)
    mandat = z.mandat if z.lastschrift else ""
    if r.art == "381":
        bedingungen, faellig = sicht.satz("gutschrift", r, "de"), None  # wie Sichtteil, ohne BT-9
    else:
        bedingungen, faellig = z.bedingungen, z.faellig
    if bedingungen or faellig or mandat:
        pt = _e(se, "ram:SpecifiedTradePaymentTerms")  # BT-20 / BT-9 / BT-89
        if bedingungen:
            _e(pt, "ram:Description", bedingungen)
        if faellig:
            _datum(pt, "ram:DueDateDateTime", faellig)
        if mandat:
            _e(pt, "ram:DirectDebitMandateID", mandat)
    ms = _e(se, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")  # BG-22
    _e(ms, "ram:LineTotalAmount", betrag(s.positionen_netto))  # BT-106
    if any(za.zuschlag for za in r.zu_abschlaege):
        _e(ms, "ram:ChargeTotalAmount", betrag(s.zuschlaege))  # BT-108
    if any(not za.zuschlag for za in r.zu_abschlaege):
        _e(ms, "ram:AllowanceTotalAmount", betrag(s.abschlaege))  # BT-107
    _e(ms, "ram:TaxBasisTotalAmount", betrag(s.netto))  # BT-109
    _e(ms, "ram:TaxTotalAmount", betrag(s.ust), currencyID=r.waehrung)  # BT-110
    if r.steuerwaehrung and s.ust_steuerwaehrung is not None:
        _e(
            ms, "ram:TaxTotalAmount", betrag(s.ust_steuerwaehrung), currencyID=r.steuerwaehrung
        )  # BT-111
    if s.rundung:
        _e(ms, "ram:RoundingAmount", betrag(s.rundung))  # BT-114
    _e(ms, "ram:GrandTotalAmount", betrag(s.brutto))  # BT-112
    _e(ms, "ram:TotalPrepaidAmount", betrag(s.vorausbezahlt))  # BT-113
    _e(ms, "ram:DuePayableAmount", betrag(s.zahlbar))  # BT-115
    if r.bezuege:  # BG-3 (CII: höchstens einer)
        b = r.bezuege[0]
        d = _e(se, "ram:InvoiceReferencedDocument")
        _e(d, "ram:IssuerAssignedID", b.nummer)  # BT-25
        if b.datum:
            _e(
                _e(d, "ram:FormattedIssueDateTime"),
                "qdt:DateTimeString",
                b.datum.strftime("%Y%m%d"),
                format="102",
            )  # BT-26
    if ref.buchung:
        _e(_e(se, "ram:ReceivableSpecifiedTradeAccountingAccount"), "ram:ID", ref.buchung)  # BT-19
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
