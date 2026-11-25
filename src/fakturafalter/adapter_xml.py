# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""XML-Eingang: ZUGFeRD/Factur-X bzw. XRechnung (CII) und XRechnung UBL -> ``modell.Rechnung``.

Feste Zuordnung nach EN 16931 – nichts anzulernen. Gelesen werden alle Business Terms des Modells (seit 0.6.0
auch Zu-/Abschläge, Anzahlung, Gutschrift/Korrektur mit Bezug, Lastschrift, Lieferung, Referenzen, Anhänge).
Jedes Element mit Inhalt, das nicht übernommen wird (z. B. EXTENDED-Felder), erzeugt eine „warnung“ – nichts
wird still verworfen. Geparst wird ohne DTD, ohne Entitäten und ohne Netz (XXE-sicher)."""

from __future__ import annotations

import base64
import binascii
from collections import OrderedDict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

from . import sicht, steuerfaelle
from .konfig import Konfig
from .modell import (
    Anhang,
    Anschrift,
    Herkunft,
    Klassifizierung,
    Merkmal,
    Partei,
    Position,
    Rechnung,
    Rechnungsbezug,
    Steuer,
    Steuervertreter,
    Zahlung,
    Zahlungsempfaenger,
    ZuAbschlag,
)

CII = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}
UBL = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


def _baum(daten: bytes):
    try:
        return etree.fromstring(daten, _PARSER)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"keine lesbare XML-Datei ({e})") from e


def erkennen(daten: bytes) -> tuple[str, str]:
    """-> (syntax „CII“|„UBL“, Klartext wie „XRechnung (UBL)“). ValueError bei anderem XML."""
    root = _baum(daten)
    q = etree.QName(root)
    if q.namespace == CII["rsm"] and q.localname == "CrossIndustryInvoice":
        g = (
            root.findtext(".//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID", "", CII) or ""
        ).lower()
        return "CII", (
            "XRechnung (CII)"
            if "xrechnung" in g
            else "ZUGFeRD / Factur-X (CII)"
            + (f" – Profil {_profil_name(g)}" if _profil_name(g) else "")
        )
    if q.namespace in (UBL["inv"], UBL["cn"]):
        c = (root.findtext("cbc:CustomizationID", "", UBL) or "").lower()
        return "UBL", "XRechnung (UBL)" if "xrechnung" in c else "EN 16931 (UBL)"
    raise ValueError(
        "kein ZUGFeRD/Factur-X und keine XRechnung (erwartet CII „CrossIndustryInvoice“ "
        "oder UBL „Invoice“)"
    )


def _profil_name(g: str) -> str:
    for teil, name in (
        ("minimum", "MINIMUM"),
        ("basicwl", "BASIC WL"),
        ("basic", "BASIC"),
        ("extended", "EXTENDED"),
        ("en16931", "EN 16931"),
    ):
        if teil in g:
            return name
    return ""


def _dez(s: str | None) -> Decimal | None:
    if s is None or not s.strip():
        return None
    try:
        return Decimal(s.strip())
    except InvalidOperation:
        return None


def _datum(s: str | None) -> date | None:
    s = (s or "").strip().replace("-", "")
    if len(s) >= 8 and s[:8].isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    return None


def lesen(datei: Path, k: Konfig) -> list[Rechnung]:
    daten = Path(datei).read_bytes()
    syntax, _art = erkennen(daten)
    root = _baum(daten)
    lz = _Leser(root, CII if syntax == "CII" else UBL)
    r = _cii(lz, k) if syntax == "CII" else _ubl(lz, k)
    r.quelle = str(datei)
    r.profil = ""
    quelle = f"xml:{Path(datei).name}"
    for feld in ("BT-1", "BT-2", "BT-44", "BT-109", "BT-112"):
        r.herkunft[feld] = Herkunft(quelle)
    if not r.verkaeufer.name:  # ohne Verkäufer in der XML: Absender aus den Einstellungen
        r.verkaeufer = k.absender
    z = r.zahlung
    if not (z.iban or z.bedingungen or z.faellig or z.art or z.mandat):
        r.zahlung = k.zahlung
    elif z.lastschrift and not z.glaeubiger_id and k.zahlung.glaeubiger_id:
        z.glaeubiger_id = k.zahlung.glaeubiger_id  # BR-DE-30: Gläubiger-ID aus dem Absenderprofil
        r.hinweis("info", "Gläubiger-ID aus dem Absenderprofil ergänzt", "BT-90")
    if not r.positionen:
        r.hinweis(
            "pruefen",
            "XML enthält keine Positionen (z. B. ZUGFeRD MINIMUM/BASIC WL) – bitte prüfen",
        )
    for text in lz.uebrig():
        r.hinweis("warnung", text)
    sicht.gutschrift_zahlung_setzen(r)
    return [r]


class _Leser:
    """Liest Elemente und merkt sich, welche übernommen wurden. ``uebrig()`` nennt den Rest (Blätter mit Inhalt)."""

    def __init__(self, root, ns: dict):
        self.root, self.ns, self._baum = root, ns, root.getroottree()
        self.gelesen: set[str] = set()

    def _merk(self, el) -> None:
        if el is not None:
            self.gelesen.add(self._baum.getpath(el))

    def el(self, parent, pfad: str):
        if parent is None:
            return None
        e = parent.find(pfad, self.ns)
        self._merk(e)
        return e

    def alle(self, parent, pfad: str) -> list:
        if parent is None:
            return []
        es = parent.findall(pfad, self.ns)
        for e in es:
            self._merk(e)
        return es

    def t(self, parent, pfad: str) -> str:
        e = self.el(parent, pfad)
        return (e.text or "").strip() if e is not None else ""

    def att(self, parent, pfad: str, name: str) -> str:
        e = self.el(parent, pfad)
        return (e.get(name) or "").strip() if e is not None else ""

    def egal(self, parent, *pfade: str) -> None:
        """Wird bewusst nicht übernommen, weil Fakturafalter es selbst neu bildet (Summen, Steuerzeilen …)."""
        for pfad in pfade:
            self.alle(parent, pfad)

    def uebrig(self) -> list[str]:
        gruppen: OrderedDict[str, list[str]] = OrderedDict()
        for e in self.root.iter():
            if not isinstance(e.tag, str) or len(e):
                continue
            text = (e.text or "").strip()
            if not text and not e.attrib:
                continue
            if self._baum.getpath(e) in self.gelesen:
                continue
            kette = [etree.QName(a).localname for a in reversed(list(e.iterancestors()))][1:]
            pfad = "/".join([*kette, etree.QName(e).localname])
            gruppen.setdefault(pfad, []).append(text)
        aus = []
        for pfad, werte in gruppen.items():
            w = werte[0] if len(werte[0]) <= 60 else werte[0][:57] + "…"
            n = f" ({len(werte)}×)" if len(werte) > 1 else ""
            aus.append(f"XML-Element nicht übernommen: {pfad}{n}" + (f" – „{w}“" if w else ""))
        return aus


# ---------------------------------------------------------------------------------------------- CII
def _cii_anschrift(lz: _Leser, a, land_standard: str = "DE") -> Anschrift:
    return Anschrift(
        strasse=lz.t(a, "ram:LineOne"),
        zusatz=lz.t(a, "ram:LineTwo"),
        zeile3=lz.t(a, "ram:LineThree"),
        plz=lz.t(a, "ram:PostcodeCode"),
        ort=lz.t(a, "ram:CityName"),
        land=lz.t(a, "ram:CountryID") or land_standard,
        region=lz.t(a, "ram:CountrySubDivisionName"),
    )


def _cii_partei(lz: _Leser, tp) -> Partei:
    p = Partei()
    if tp is None:
        return p
    p.name = lz.t(tp, "ram:Name")
    p.kennung = lz.t(tp, "ram:ID") or lz.t(tp, "ram:GlobalID")
    p.rechtliches = lz.t(tp, "ram:Description")
    p.register = lz.t(tp, "ram:SpecifiedLegalOrganization/ram:ID")
    p.handelsname = lz.t(tp, "ram:SpecifiedLegalOrganization/ram:TradingBusinessName")
    c = lz.el(tp, "ram:DefinedTradeContact")
    p.kontakt_name = lz.t(c, "ram:PersonName") or lz.t(c, "ram:DepartmentName")
    p.kontakt_telefon = lz.t(c, "ram:TelephoneUniversalCommunication/ram:CompleteNumber")
    p.kontakt_email = lz.t(c, "ram:EmailURIUniversalCommunication/ram:URIID")
    p.anschrift = _cii_anschrift(lz, lz.el(tp, "ram:PostalTradeAddress"))
    p.elektronische_adresse = lz.t(tp, "ram:URIUniversalCommunication/ram:URIID")
    for reg in lz.alle(tp, "ram:SpecifiedTaxRegistration/ram:ID"):
        if reg.get("schemeID") == "VA":
            p.ust_id = (reg.text or "").strip()
        elif reg.get("schemeID") == "FC":
            p.steuernummer = (reg.text or "").strip()
    return p


def _cii_za(lz: _Leser, el, befreiung: dict | None) -> ZuAbschlag:
    za = ZuAbschlag(zuschlag=lz.t(el, "ram:ChargeIndicator/udt:Indicator").lower() == "true")
    za.prozent = _dez(lz.t(el, "ram:CalculationPercent"))
    za.basis = _dez(lz.t(el, "ram:BasisAmount"))
    za.betrag = _dez(lz.t(el, "ram:ActualAmount"))
    za.grund_code = lz.t(el, "ram:ReasonCode")
    za.grund = lz.t(el, "ram:Reason")
    if befreiung is not None and lz.el(el, "ram:CategoryTradeTax") is not None:
        lz.egal(el, "ram:CategoryTradeTax/ram:TypeCode")
        za.steuer = _steuer(
            lz.t(el, "ram:CategoryTradeTax/ram:CategoryCode"),
            _dez(lz.t(el, "ram:CategoryTradeTax/ram:RateApplicablePercent")),
            befreiung,
        )
    return za


def _cii_zeitraum(lz: _Leser, bp) -> tuple[date | None, date | None]:
    return (
        _datum(lz.t(bp, "ram:StartDateTime/udt:DateTimeString")),
        _datum(lz.t(bp, "ram:EndDateTime/udt:DateTimeString")),
    )


def _cii(lz: _Leser, k: Konfig) -> Rechnung:
    root = lz.root
    r = Rechnung()
    g = lz.t(
        root, "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"
    ).lower()
    lz.egal(
        root,
        "rsm:ExchangedDocumentContext/ram:BusinessProcessSpecifiedDocumentContextParameter/ram:ID",
    )  # BT-23
    r.ausgabeformat = "XRECHNUNG_CII" if "xrechnung" in g else "ZUGFERD_EN16931"
    doc = lz.el(root, "rsm:ExchangedDocument")
    r.nummer = lz.t(doc, "ram:ID")
    r.art = lz.t(doc, "ram:TypeCode") or "380"
    r.datum = _datum(lz.t(doc, "ram:IssueDateTime/udt:DateTimeString"))
    for n in lz.alle(doc, "ram:IncludedNote"):
        r.bemerkungen.append((lz.t(n, "ram:Content"), lz.t(n, "ram:SubjectCode")))
    tx = root.find("rsm:SupplyChainTradeTransaction", CII)
    if tx is None:
        raise ValueError("CII ohne SupplyChainTradeTransaction")
    ag = lz.el(tx, "ram:ApplicableHeaderTradeAgreement")
    r.leitweg_id = lz.t(ag, "ram:BuyerReference")
    r.verkaeufer = _cii_partei(lz, lz.el(ag, "ram:SellerTradeParty"))
    r.kaeufer = _cii_partei(lz, lz.el(ag, "ram:BuyerTradeParty"))
    r.kundennummer = r.kaeufer.kennung
    sv = lz.el(ag, "ram:SellerTaxRepresentativeTradeParty")
    if sv is not None:  # BG-11
        r.steuervertreter = Steuervertreter(
            lz.t(sv, "ram:Name"),
            lz.t(sv, "ram:SpecifiedTaxRegistration/ram:ID"),
            _cii_anschrift(lz, lz.el(sv, "ram:PostalTradeAddress")),
        )
    ref = r.referenzen
    ref.auftrag = lz.t(ag, "ram:SellerOrderReferencedDocument/ram:IssuerAssignedID")  # BT-14
    r.bestellnummer = lz.t(ag, "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID")  # BT-13
    ref.vertrag = lz.t(ag, "ram:ContractReferencedDocument/ram:IssuerAssignedID")  # BT-12
    for d in ag.findall("ram:AdditionalReferencedDocument", CII) if ag is not None else []:
        typ = lz.t(d, "ram:TypeCode")
        nr = lz.t(d, "ram:IssuerAssignedID")
        if typ == "50":
            ref.ausschreibung = nr  # BT-17
        elif typ == "130":
            ref.objekt, ref.objekt_schema = nr, lz.t(d, "ram:ReferenceTypeCode")  # BT-18
        elif typ == "916":  # BG-24
            r.anhaenge.append(
                _anhang(
                    r,
                    nr,
                    lz.t(d, "ram:Name"),
                    lz.t(d, "ram:URIID"),
                    lz.el(d, "ram:AttachmentBinaryObject"),
                )
            )
    pj = lz.el(ag, "ram:SpecifiedProcuringProject")
    ref.projekt, ref.projekt_name = lz.t(pj, "ram:ID"), lz.t(pj, "ram:Name")  # BT-11
    if ref.projekt_name == ref.projekt:
        ref.projekt_name = ""

    de = lz.el(tx, "ram:ApplicableHeaderTradeDelivery")
    st = lz.el(de, "ram:ShipToTradeParty")
    if st is not None:  # BG-13
        lf = r.lieferung
        gid = lz.el(st, "ram:GlobalID")
        lf.ort_id = lz.t(st, "ram:ID") or ((gid.text or "").strip() if gid is not None else "")
        lf.ort_schema = gid.get("schemeID", "") if gid is not None else ""
        lf.name = lz.t(st, "ram:Name")
        if st.find("ram:PostalTradeAddress", CII) is not None:
            lf.anschrift = _cii_anschrift(lz, lz.el(st, "ram:PostalTradeAddress"), "")
    r.leistungsdatum = _datum(
        lz.t(de, "ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/udt:DateTimeString")
    )
    ref.lieferschein = lz.t(
        de, "ram:DespatchAdviceReferencedDocument/ram:IssuerAssignedID"
    )  # BT-16
    ref.wareneingang = lz.t(
        de, "ram:ReceivingAdviceReferencedDocument/ram:IssuerAssignedID"
    )  # BT-15

    se = lz.el(tx, "ram:ApplicableHeaderTradeSettlement")
    r.waehrung = lz.t(se, "ram:InvoiceCurrencyCode") or "EUR"
    steuerwaehrung = lz.t(se, "ram:TaxCurrencyCode")  # BT-6
    befreiung = {}
    for t in lz.alle(se, "ram:ApplicableTradeTax"):
        befreiung[(lz.t(t, "ram:CategoryCode"), _dez(lz.t(t, "ram:RateApplicablePercent")))] = (
            lz.t(t, "ram:ExemptionReason"),
            lz.t(t, "ram:ExemptionReasonCode"),
        )
        lz.egal(
            t, "ram:CalculatedAmount", "ram:BasisAmount", "ram:TypeCode"
        )  # BG-23: neu gerechnet
    z = Zahlung(art="", ziel_tage=None)
    z.glaeubiger_id = lz.t(se, "ram:CreditorReferenceID")  # BT-90
    vz = lz.t(se, "ram:PaymentReference")  # BT-83
    z.verwendungszweck = "" if vz == r.nummer else vz
    pe = lz.el(se, "ram:PayeeTradeParty")
    if pe is not None:  # BG-10
        r.zahlungsempfaenger = Zahlungsempfaenger(
            lz.t(pe, "ram:Name"),
            lz.t(pe, "ram:ID") or lz.t(pe, "ram:GlobalID"),
            lz.t(pe, "ram:SpecifiedLegalOrganization/ram:ID"),
        )
    pm = lz.el(se, "ram:SpecifiedTradeSettlementPaymentMeans")
    if pm is not None:
        z.art = lz.t(pm, "ram:TypeCode")
        z.info = lz.t(pm, "ram:Information")
        z.karte = lz.t(pm, "ram:ApplicableTradeSettlementFinancialCard/ram:ID")
        z.karteninhaber = lz.t(pm, "ram:ApplicableTradeSettlementFinancialCard/ram:CardholderName")
        z.lastschrift_iban = lz.t(pm, "ram:PayerPartyDebtorFinancialAccount/ram:IBANID")
        z.iban = lz.t(pm, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID") or lz.t(
            pm, "ram:PayeePartyCreditorFinancialAccount/ram:ProprietaryID"
        )
        z.kontoinhaber = lz.t(pm, "ram:PayeePartyCreditorFinancialAccount/ram:AccountName")
        z.bic = lz.t(pm, "ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID")
    r.leistung_von, r.leistung_bis = _cii_zeitraum(lz, lz.el(se, "ram:BillingSpecifiedPeriod"))
    for el in lz.alle(se, "ram:SpecifiedTradeAllowanceCharge"):  # BG-20/BG-21
        r.zu_abschlaege.append(_cii_za(lz, el, befreiung))
    pt = lz.el(se, "ram:SpecifiedTradePaymentTerms")
    z.bedingungen = lz.t(pt, "ram:Description")
    z.faellig = _datum(lz.t(pt, "ram:DueDateDateTime/udt:DateTimeString"))
    z.mandat = lz.t(pt, "ram:DirectDebitMandateID")  # BT-89
    r.zahlung = z
    ms = lz.el(se, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    _kontrolle(
        r,
        {
            "BT-106": lz.t(ms, "ram:LineTotalAmount"),
            "BT-107": lz.t(ms, "ram:AllowanceTotalAmount"),
            "BT-108": lz.t(ms, "ram:ChargeTotalAmount"),
            "BT-109": lz.t(ms, "ram:TaxBasisTotalAmount"),
            "BT-110": _steuerbetrag(lz.alle(ms, "ram:TaxTotalAmount"), r, steuerwaehrung),
            "BT-112": lz.t(ms, "ram:GrandTotalAmount"),
            "BT-115": lz.t(ms, "ram:DuePayableAmount"),
        },
        lz.t(ms, "ram:TotalPrepaidAmount"),
        lz.t(ms, "ram:RoundingAmount"),
    )
    for d in lz.alle(se, "ram:InvoiceReferencedDocument"):  # BG-3
        r.bezuege.append(
            Rechnungsbezug(
                lz.t(d, "ram:IssuerAssignedID"),
                _datum(lz.t(d, "ram:FormattedIssueDateTime/qdt:DateTimeString")),
            )
        )
    ref.buchung = lz.t(se, "ram:ReceivableSpecifiedTradeAccountingAccount/ram:ID")  # BT-19

    for li in tx.findall("ram:IncludedSupplyChainTradeLineItem", CII):
        p = Position()
        ld = lz.el(li, "ram:AssociatedDocumentLineDocument")
        p.nr = lz.t(ld, "ram:LineID")
        p.notiz = "\n".join(
            lz.t(n, "ram:Content") for n in lz.alle(ld, "ram:IncludedNote")
        )  # BT-127
        prod = lz.el(li, "ram:SpecifiedTradeProduct")
        gid = lz.el(prod, "ram:GlobalID")
        if gid is not None:
            p.standard_id, p.standard_schema = (
                (gid.text or "").strip(),
                gid.get("schemeID", ""),
            )  # BT-157
        p.artikelnummer = lz.t(prod, "ram:SellerAssignedID")
        p.kaeufer_artikelnummer = lz.t(prod, "ram:BuyerAssignedID")
        p.bezeichnung = lz.t(prod, "ram:Name")
        p.beschreibung = lz.t(prod, "ram:Description")
        for pc in lz.alle(prod, "ram:ApplicableProductCharacteristic"):  # BG-32
            p.merkmale.append(Merkmal(lz.t(pc, "ram:Description"), lz.t(pc, "ram:Value")))
        for cc in lz.alle(prod, "ram:DesignatedProductClassification/ram:ClassCode"):  # BT-158
            p.klassifizierungen.append(
                Klassifizierung(
                    (cc.text or "").strip(), cc.get("listID", ""), cc.get("listVersionID", "")
                )
            )
        p.ursprungsland = lz.t(prod, "ram:OriginTradeCountry/ram:ID")  # BT-159
        la = lz.el(li, "ram:SpecifiedLineTradeAgreement")
        p.bestellposition = lz.t(la, "ram:BuyerOrderReferencedDocument/ram:LineID")  # BT-132
        gp = lz.el(la, "ram:GrossPriceProductTradePrice")
        if gp is not None:
            p.bruttopreis = _dez(lz.t(gp, "ram:ChargeAmount"))  # BT-148
            lz.egal(
                gp,
                "ram:BasisQuantity",
                "ram:AppliedTradeAllowanceCharge/ram:ChargeIndicator/udt:Indicator",
            )
            p.preisrabatt = _dez(
                lz.t(gp, "ram:AppliedTradeAllowanceCharge/ram:ActualAmount")
            )  # BT-147
        preis = lz.el(la, "ram:NetPriceProductTradePrice")
        p.einzelpreis = _dez(lz.t(preis, "ram:ChargeAmount"))
        p.preiseinheit = _dez(lz.t(preis, "ram:BasisQuantity")) or Decimal("1")
        menge = lz.el(li, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity")
        p.menge = _dez(menge.text if menge is not None else None)
        p.einheit = menge.get("unitCode", "") if menge is not None else ""
        st = lz.el(li, "ram:SpecifiedLineTradeSettlement")
        lz.egal(st, "ram:ApplicableTradeTax/ram:TypeCode")
        kat, s_ = (
            lz.t(st, "ram:ApplicableTradeTax/ram:CategoryCode"),
            _dez(lz.t(st, "ram:ApplicableTradeTax/ram:RateApplicablePercent")),
        )
        p.steuer = _steuer(kat, s_, befreiung)
        p.leistung_von, p.leistung_bis = _cii_zeitraum(
            lz, lz.el(st, "ram:BillingSpecifiedPeriod")
        )  # BG-26
        for el in lz.alle(st, "ram:SpecifiedTradeAllowanceCharge"):  # BG-27/BG-28
            p.zu_abschlaege.append(_cii_za(lz, el, None))
        p.kontrolle_gesamt = _dez(
            lz.t(st, "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount")
        )
        for d in st.findall("ram:AdditionalReferencedDocument", CII) if st is not None else []:
            if (d.findtext("ram:TypeCode", "", CII) or "").strip() == "130":
                lz.egal(d, "ram:TypeCode")
                p.objektkennung = lz.t(d, "ram:IssuerAssignedID")  # BT-128
        p.buchungsreferenz = lz.t(
            st, "ram:ReceivableSpecifiedTradeAccountingAccount/ram:ID"
        )  # BT-133
        r.positionen.append(p)
    return r


# ---------------------------------------------------------------------------------------------- UBL
def _ubl_anschrift(lz: _Leser, a, land_standard: str = "DE") -> Anschrift:
    return Anschrift(
        strasse=lz.t(a, "cbc:StreetName"),
        zusatz=lz.t(a, "cbc:AdditionalStreetName"),
        zeile3=lz.t(a, "cac:AddressLine/cbc:Line"),
        plz=lz.t(a, "cbc:PostalZone"),
        ort=lz.t(a, "cbc:CityName"),
        land=lz.t(a, "cac:Country/cbc:IdentificationCode") or land_standard,
        region=lz.t(a, "cbc:CountrySubentity"),
    )


def _ubl_partei(lz: _Leser, pt, z: Zahlung | None = None) -> Partei:
    p = Partei()
    if pt is None:
        return p
    reg_name, kurz = (
        lz.t(pt, "cac:PartyLegalEntity/cbc:RegistrationName"),
        lz.t(pt, "cac:PartyName/cbc:Name"),
    )
    p.name = reg_name or kurz
    if reg_name and kurz and kurz != reg_name:
        p.handelsname = kurz  # BT-28 / BT-45
    for pid in lz.alle(pt, "cac:PartyIdentification/cbc:ID"):
        if pid.get("schemeID") == "SEPA" and z is not None:
            z.glaeubiger_id = (pid.text or "").strip()  # BT-90 (UBL)
        elif not p.kennung:
            p.kennung = (pid.text or "").strip()
    p.register = lz.t(pt, "cac:PartyLegalEntity/cbc:CompanyID")
    p.rechtliches = lz.t(pt, "cac:PartyLegalEntity/cbc:CompanyLegalForm")
    p.elektronische_adresse = lz.t(pt, "cbc:EndpointID")
    p.anschrift = _ubl_anschrift(lz, lz.el(pt, "cac:PostalAddress"))
    for ts in lz.alle(pt, "cac:PartyTaxScheme"):
        if lz.t(ts, "cac:TaxScheme/cbc:ID") == "VAT":
            p.ust_id = lz.t(ts, "cbc:CompanyID")
        else:
            p.steuernummer = lz.t(ts, "cbc:CompanyID")
    c = lz.el(pt, "cac:Contact")
    p.kontakt_name = lz.t(c, "cbc:Name")
    p.kontakt_telefon = lz.t(c, "cbc:Telephone")
    p.kontakt_email = lz.t(c, "cbc:ElectronicMail")
    return p


def _ubl_za(lz: _Leser, el, befreiung: dict | None) -> ZuAbschlag:
    za = ZuAbschlag(zuschlag=lz.t(el, "cbc:ChargeIndicator").lower() == "true")
    za.grund_code = lz.t(el, "cbc:AllowanceChargeReasonCode")
    za.grund = lz.t(el, "cbc:AllowanceChargeReason")
    za.prozent = _dez(lz.t(el, "cbc:MultiplierFactorNumeric"))
    za.betrag = _dez(lz.t(el, "cbc:Amount"))
    za.basis = _dez(lz.t(el, "cbc:BaseAmount"))
    if befreiung is not None and el.find("cac:TaxCategory", UBL) is not None:
        lz.egal(el, "cac:TaxCategory/cac:TaxScheme/cbc:ID")
        za.steuer = _steuer(
            lz.t(el, "cac:TaxCategory/cbc:ID"),
            _dez(lz.t(el, "cac:TaxCategory/cbc:Percent")),
            befreiung,
        )
    return za


def _ubl(lz: _Leser, k: Konfig) -> Rechnung:
    root = lz.root
    gutschrift = etree.QName(root).namespace == UBL["cn"]
    r = Rechnung()
    t = lz.t
    lz.egal(root, "cbc:UBLVersionID", "cbc:ProfileID")
    r.ausgabeformat = (
        "XRECHNUNG_CII"
        if "xrechnung" in t(root, "cbc:CustomizationID").lower()
        else "ZUGFERD_EN16931"
    )
    r.nummer = t(root, "cbc:ID")
    r.datum = _datum(t(root, "cbc:IssueDate"))
    r.art = t(root, "cbc:CreditNoteTypeCode" if gutschrift else "cbc:InvoiceTypeCode") or (
        "381" if gutschrift else "380"
    )
    r.waehrung = t(root, "cbc:DocumentCurrencyCode") or "EUR"
    steuerwaehrung = t(root, "cbc:TaxCurrencyCode")  # BT-6
    r.leitweg_id = t(root, "cbc:BuyerReference")
    ref = r.referenzen
    ref.buchung = t(root, "cbc:AccountingCost")  # BT-19
    r.bestellnummer = t(root, "cac:OrderReference/cbc:ID")
    ref.auftrag = t(root, "cac:OrderReference/cbc:SalesOrderID")  # BT-14
    for n in lz.alle(root, "cbc:Note"):
        r.bemerkungen.append(((n.text or "").strip(), ""))
    for b in lz.alle(root, "cac:BillingReference"):  # BG-3
        r.bezuege.append(
            Rechnungsbezug(
                t(b, "cac:InvoiceDocumentReference/cbc:ID"),
                _datum(t(b, "cac:InvoiceDocumentReference/cbc:IssueDate")),
            )
        )
    ref.lieferschein = t(root, "cac:DespatchDocumentReference/cbc:ID")  # BT-16
    ref.wareneingang = t(root, "cac:ReceiptDocumentReference/cbc:ID")  # BT-15
    ref.ausschreibung = t(root, "cac:OriginatorDocumentReference/cbc:ID")  # BT-17
    ref.vertrag = t(root, "cac:ContractDocumentReference/cbc:ID")  # BT-12
    ref.projekt = t(root, "cac:ProjectReference/cbc:ID")  # BT-11
    for d in root.findall("cac:AdditionalDocumentReference", UBL):
        if (d.findtext("cbc:DocumentTypeCode", "", UBL) or "").strip() == "130":  # BT-18
            lz.egal(d, "cbc:DocumentTypeCode")
            ref.objekt, ref.objekt_schema = t(d, "cbc:ID"), lz.att(d, "cbc:ID", "schemeID")
        else:  # BG-24
            lz.egal(d, "cbc:DocumentTypeCode")
            r.anhaenge.append(
                _anhang(
                    r,
                    t(d, "cbc:ID"),
                    t(d, "cbc:DocumentDescription"),
                    t(d, "cac:Attachment/cac:ExternalReference/cbc:URI"),
                    lz.el(d, "cac:Attachment/cbc:EmbeddedDocumentBinaryObject"),
                )
            )
    z = Zahlung(art="", ziel_tage=None)
    r.verkaeufer = _ubl_partei(lz, lz.el(root, "cac:AccountingSupplierParty/cac:Party"), z)
    r.kaeufer = _ubl_partei(lz, lz.el(root, "cac:AccountingCustomerParty/cac:Party"))
    r.kundennummer = r.kaeufer.kennung
    pe = lz.el(root, "cac:PayeeParty")
    if pe is not None:  # BG-10
        ze = Zahlungsempfaenger(
            t(pe, "cac:PartyName/cbc:Name"), register=t(pe, "cac:PartyLegalEntity/cbc:CompanyID")
        )
        for pid in lz.alle(pe, "cac:PartyIdentification/cbc:ID"):
            if pid.get("schemeID") == "SEPA":
                z.glaeubiger_id = (pid.text or "").strip()
            else:
                ze.kennung = (pid.text or "").strip()
        r.zahlungsempfaenger = ze
    sv = lz.el(root, "cac:TaxRepresentativeParty")
    if sv is not None:  # BG-11
        lz.egal(sv, "cac:PartyTaxScheme/cac:TaxScheme/cbc:ID")
        r.steuervertreter = Steuervertreter(
            t(sv, "cac:PartyName/cbc:Name"),
            t(sv, "cac:PartyTaxScheme/cbc:CompanyID"),
            _ubl_anschrift(lz, lz.el(sv, "cac:PostalAddress")),
        )
    dl = lz.el(root, "cac:Delivery")
    r.leistungsdatum = _datum(t(dl, "cbc:ActualDeliveryDate"))
    lf = r.lieferung
    lf.ort_id = t(dl, "cac:DeliveryLocation/cbc:ID")  # BT-71
    lf.ort_schema = lz.att(dl, "cac:DeliveryLocation/cbc:ID", "schemeID")
    if dl is not None and dl.find("cac:DeliveryLocation/cac:Address", UBL) is not None:
        lf.anschrift = _ubl_anschrift(lz, lz.el(dl, "cac:DeliveryLocation/cac:Address"), "")
    lf.name = t(dl, "cac:DeliveryParty/cac:PartyName/cbc:Name")  # BT-70
    r.leistung_von = _datum(t(root, "cac:InvoicePeriod/cbc:StartDate"))
    r.leistung_bis = _datum(t(root, "cac:InvoicePeriod/cbc:EndDate"))
    pm = lz.el(root, "cac:PaymentMeans")
    if pm is not None:
        z.art = t(pm, "cbc:PaymentMeansCode")
        z.info = lz.att(pm, "cbc:PaymentMeansCode", "name")  # BT-82
        vz = t(pm, "cbc:PaymentID")  # BT-83
        z.verwendungszweck = "" if vz == r.nummer else vz
        z.karte = t(pm, "cac:CardAccount/cbc:PrimaryAccountNumberID")
        lz.egal(pm, "cac:CardAccount/cbc:NetworkID")
        z.karteninhaber = t(pm, "cac:CardAccount/cbc:HolderName")
        z.iban = t(pm, "cac:PayeeFinancialAccount/cbc:ID")
        z.kontoinhaber = t(pm, "cac:PayeeFinancialAccount/cbc:Name")
        z.bic = t(pm, "cac:PayeeFinancialAccount/cac:FinancialInstitutionBranch/cbc:ID")
        z.mandat = t(pm, "cac:PaymentMandate/cbc:ID")  # BT-89
        z.lastschrift_iban = t(pm, "cac:PaymentMandate/cac:PayerFinancialAccount/cbc:ID")  # BT-91
    z.bedingungen = t(root, "cac:PaymentTerms/cbc:Note")
    z.faellig = _datum(t(root, "cbc:DueDate"))
    r.zahlung = z
    befreiung = {}
    for sub in lz.alle(root, "cac:TaxTotal/cac:TaxSubtotal"):
        befreiung[
            (t(sub, "cac:TaxCategory/cbc:ID"), _dez(t(sub, "cac:TaxCategory/cbc:Percent")))
        ] = (
            t(sub, "cac:TaxCategory/cbc:TaxExemptionReason"),
            t(sub, "cac:TaxCategory/cbc:TaxExemptionReasonCode"),
        )
        lz.egal(sub, "cbc:TaxableAmount", "cbc:TaxAmount", "cac:TaxCategory/cac:TaxScheme/cbc:ID")
    for el in lz.alle(root, "cac:AllowanceCharge"):  # BG-20/BG-21
        r.zu_abschlaege.append(_ubl_za(lz, el, befreiung))
    ms = lz.el(root, "cac:LegalMonetaryTotal")
    _kontrolle(
        r,
        {
            "BT-106": t(ms, "cbc:LineExtensionAmount"),
            "BT-107": t(ms, "cbc:AllowanceTotalAmount"),
            "BT-108": t(ms, "cbc:ChargeTotalAmount"),
            "BT-109": t(ms, "cbc:TaxExclusiveAmount"),
            "BT-110": _steuerbetrag(
                [lz.el(tt, "cbc:TaxAmount") for tt in lz.alle(root, "cac:TaxTotal")], r, steuerwaehrung
            ),
            "BT-112": t(ms, "cbc:TaxInclusiveAmount"),
            "BT-115": t(ms, "cbc:PayableAmount"),
        },
        t(ms, "cbc:PrepaidAmount"),
        t(ms, "cbc:PayableRoundingAmount"),
    )
    zeile, menge_tag = (
        ("cac:CreditNoteLine", "cbc:CreditedQuantity")
        if gutschrift
        else ("cac:InvoiceLine", "cbc:InvoicedQuantity")
    )
    for li in root.findall(zeile, UBL):
        p = Position()
        p.nr = t(li, "cbc:ID")
        p.notiz = "\n".join((n.text or "").strip() for n in lz.alle(li, "cbc:Note"))  # BT-127
        p.buchungsreferenz = t(li, "cbc:AccountingCost")  # BT-133
        p.leistung_von = _datum(t(li, "cac:InvoicePeriod/cbc:StartDate"))  # BG-26
        p.leistung_bis = _datum(t(li, "cac:InvoicePeriod/cbc:EndDate"))
        p.bestellposition = t(li, "cac:OrderLineReference/cbc:LineID")  # BT-132
        for d in li.findall("cac:DocumentReference", UBL):
            if (d.findtext("cbc:DocumentTypeCode", "", UBL) or "").strip() == "130":
                lz.egal(d, "cbc:DocumentTypeCode")
                p.objektkennung = t(d, "cbc:ID")  # BT-128
        it = lz.el(li, "cac:Item")
        p.beschreibung = t(it, "cbc:Description")
        p.bezeichnung = t(it, "cbc:Name")
        p.kaeufer_artikelnummer = t(it, "cac:BuyersItemIdentification/cbc:ID")
        p.artikelnummer = t(it, "cac:SellersItemIdentification/cbc:ID")
        p.standard_id = t(it, "cac:StandardItemIdentification/cbc:ID")
        p.standard_schema = lz.att(it, "cac:StandardItemIdentification/cbc:ID", "schemeID")
        p.ursprungsland = t(it, "cac:OriginCountry/cbc:IdentificationCode")
        for cc in lz.alle(it, "cac:CommodityClassification/cbc:ItemClassificationCode"):
            p.klassifizierungen.append(
                Klassifizierung(
                    (cc.text or "").strip(), cc.get("listID", ""), cc.get("listVersionID", "")
                )
            )
        lz.egal(it, "cac:ClassifiedTaxCategory/cac:TaxScheme/cbc:ID")
        p.steuer = _steuer(
            t(it, "cac:ClassifiedTaxCategory/cbc:ID"),
            _dez(t(it, "cac:ClassifiedTaxCategory/cbc:Percent")),
            befreiung,
        )
        for ap in lz.alle(it, "cac:AdditionalItemProperty"):  # BG-32
            p.merkmale.append(Merkmal(t(ap, "cbc:Name"), t(ap, "cbc:Value")))
        menge = lz.el(li, menge_tag)
        p.menge = _dez(menge.text if menge is not None else None)
        p.einheit = menge.get("unitCode", "") if menge is not None else ""
        pr = lz.el(li, "cac:Price")
        p.einzelpreis = _dez(t(pr, "cbc:PriceAmount"))
        p.preiseinheit = _dez(t(pr, "cbc:BaseQuantity")) or Decimal("1")
        pac = lz.el(pr, "cac:AllowanceCharge")
        if pac is not None:
            lz.egal(pac, "cbc:ChargeIndicator")
            p.preisrabatt = _dez(t(pac, "cbc:Amount"))  # BT-147
            p.bruttopreis = _dez(t(pac, "cbc:BaseAmount"))  # BT-148
        p.kontrolle_gesamt = _dez(t(li, "cbc:LineExtensionAmount"))
        for el in lz.alle(li, "cac:AllowanceCharge"):  # BG-27/BG-28
            p.zu_abschlaege.append(_ubl_za(lz, el, None))
        r.positionen.append(p)
    return r


# ---------------------------------------------------------------------------------------------- gemeinsam
def _steuer(kat: str, satz: Decimal | None, befreiung: dict) -> Steuer:
    grund, code = befreiung.get((kat, satz), ("", ""))
    return Steuer(
        kategorie=kat or "S",
        satz=satz if satz is not None else Decimal("0"),
        befreiungsgrund=grund,
        befreiungscode=code,
    )


GROESSTER_ANHANG = 15 * 1024 * 1024


def _anhang(r: Rechnung, kennung: str, beschreibung: str, uri: str, binaer) -> Anhang:
    """BG-24. Eingebettete Datei (BT-125) wird übernommen, wenn sie sich einfach dekodieren lässt; sonst Warnung."""
    a = Anhang(kennung=kennung or "Anlage", beschreibung=beschreibung, uri=uri)
    if binaer is not None and (binaer.text or "").strip():
        try:
            daten = base64.b64decode("".join((binaer.text or "").split()), validate=True)
        except (binascii.Error, ValueError):
            r.hinweis(
                "warnung",
                f"Anhang „{a.kennung}“: eingebettete Datei nicht lesbar – nicht übernommen",
                "BT-125",
            )
            return a
        if len(daten) > GROESSTER_ANHANG:
            r.hinweis(
                "warnung", f"Anhang „{a.kennung}“ größer als 15 MB – nicht übernommen", "BT-125"
            )
            return a
        a.daten, a.mime, a.dateiname = daten, binaer.get("mimeCode", ""), binaer.get("filename", "")
    return a


def _steuerbetrag(elemente: list, r: Rechnung, steuerwaehrung: str) -> str:
    """BT-110 (Rechnungswährung) aus einem oder zwei Steuerbeträgen; der in der Steuerwährung (BT-6) wird BT-111
    und gilt ab 0.9.7 als Quelle für „USt in EUR“. Dazu der Kurs aus den Bemerkungen (eigene Ausgabe schreibt ihn
    dort hin), falls vorhanden."""
    els = [e for e in elemente if e is not None]
    rw = (r.waehrung or "EUR").upper()
    sw = (steuerwaehrung or "").upper()
    haupt = next((e for e in els if (e.get("currencyID") or rw).upper() == rw), els[0] if els else None)
    if sw and sw != rw:
        neben = next((e for e in els if e is not haupt and (e.get("currencyID") or "").upper() == sw), None)
        if sw != "EUR":
            r.hinweis("pruefen", f"Steuerwährung (BT-6) {sw} wird nicht unterstützt – nur EUR.", "BT-6")
        elif neben is not None:
            r.ust_eur_quelle = _dez(neben.text or "")
        else:
            r.hinweis("pruefen", "Steuerwährung EUR (BT-6) angegeben, aber kein Steuerbetrag in EUR (BT-111).",
                      "BT-111")
    if rw != "EUR" and r.kurs is None:
        for text, _ in r.bemerkungen:
            kurs, fw = steuerfaelle.kurs_lesen(text, rw)
            if kurs is not None and fw in (None, "", rw):
                r.kurs = kurs
                break
    return (haupt.text or "").strip() if haupt is not None else ""


def _kontrolle(r: Rechnung, werte: dict[str, str], vorausbezahlt: str, rundung: str = "") -> None:
    for feld, s in werte.items():
        d = _dez(s)
        if d is not None:
            r.kontrolle[feld] = d
    r.vorausbezahlt = _dez(vorausbezahlt) or Decimal("0")  # BT-113
    r.rundung = _dez(rundung) or Decimal("0")  # BT-114
