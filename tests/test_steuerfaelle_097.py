"""0.9.7: Steuer-Sonderfälle (AE/K/G/O/§ 19), Fremdwährung (BT-6/BT-111), Leitweg-ID (Mod 97-10) – Kern, CSV,
XML-Eingang, Nur-PDF mit angelernten Vorlagen. Alle Beispieldaten erfunden."""

import shutil
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from lxml import etree

from fakturafalter import (
    anschrift,
    aufbau,
    konfig,
    pdferkennung,
    pipeline,
    rechnen,
    sicht,
    steuerfaelle,
)
from fakturafalter.modell import Steuer
from fakturafalter.pflichtpruefung import leitweg_aehnlich, leitweg_gueltig

from .conftest import BEISPIELE

NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}
SF = BEISPIELE / "steuerfaelle"


def _xml(konfig_, nummer: str) -> etree._Element:
    import pikepdf

    with pikepdf.open(konfig_.ausgang / f"{nummer}_zugferd.pdf") as pdf:
        daten = pdf.attachments["factur-x.xml"].get_file().read_bytes()
    return etree.fromstring(daten)


def _kategorien(x) -> list[str]:
    return [e.text for e in x.iterfind(".//ram:SpecifiedLineTradeSettlement//ram:CategoryCode", NS)]


# ------------------------------------------------------------------ Erkennung
@pytest.mark.parametrize(
    "text,fall",
    [
        ("Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)", "AE"),
        ("Reverse Charge", "AE"),
        ("Steuerfreie innergemeinschaftliche Lieferung (§ 4 Nr. 1b UStG)", "K"),
        ("Steuerfreie Ausfuhrlieferung (§ 4 Nr. 1a UStG)", "G"),
        ("Nicht im Inland steuerbare Leistung", "O"),
        ("Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.", "KU"),
        ("Zahlbar innerhalb 14 Tagen", None),
    ],
)
def test_steuerhinweis_erkennen(text, fall):
    assert steuerfaelle.erkennen(text) == fall


def test_kurzkennungen_und_laender():
    assert steuerfaelle.erkennen_kurz("RC") == "AE"
    assert steuerfaelle.erkennen_kurz("§ 19") == "KU"
    assert steuerfaelle.erkennen_kurz("19 %") is None
    assert (
        steuerfaelle.land_code("Österreich") == "AT" and steuerfaelle.land_code("Schweiz") == "CH"
    )
    assert steuerfaelle.ist_eu("AT") and not steuerfaelle.ist_eu("CH")


def test_kurs_lesen_richtung():
    assert steuerfaelle.kurs_lesen("1 EUR = 1,0850 USD", "USD")[0] == D("1.0850")
    k, _ = steuerfaelle.kurs_lesen("Umrechnungskurs: 1 EUR = 1,0850 USD (Stand 31.10.2026)", "USD")
    assert k == D("1.0850")


def test_steuer_aus_code_hinweis_modus():
    rc = "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)"
    assert aufbau.steuer_aus_code({"fall": "hinweis"}, rc).kategorie == "AE"
    s = aufbau.steuer_aus_code({"fall": "hinweis", "BT-151": "S", "BT-152": "19"}, "")
    assert (s.kategorie, s.satz) == ("S", D("19"))
    assert aufbau.steuer_aus_code({"fall": "hinweis"}, "") is None  # nicht raten
    assert aufbau.steuer_aus_code("K", "").kategorie == "K"


# ------------------------------------------------------------------ Leitweg-ID
def test_leitweg_mod97():
    assert leitweg_gueltig("04011000-12345-03")
    assert leitweg_gueltig("04011000-1234512345-06")
    assert not leitweg_gueltig("04011000-12345-04")
    assert leitweg_aehnlich("04011000-12345-04")
    assert not leitweg_aehnlich("K-1002")  # Kundennummer als Ersatz: nicht streng geprüft


# ------------------------------------------------------------------ Rechnen / Sichtteil
def test_fremdwaehrung_ust_in_eur_und_warnungen():
    from fakturafalter.modell import Position, Rechnung

    r = Rechnung()
    r.nummer, r.datum, r.waehrung, r.kurs, r.kursdatum = (
        "X",
        date(2026, 11, 13),
        "USD",
        D("1.0850"),
        date(2026, 8, 1),
    )
    r.positionen = [
        Position(nr="1", bezeichnung="A", menge=D(4), einzelpreis=D(500), steuer=Steuer("S", D(19)))
    ]
    r.zahlung.art = "58"
    rechnen.berechnen(r)
    assert r.summen.ust == D("380.00") and r.summen.ust_steuerwaehrung == D("350.23")
    warn = [h.text for h in r.hinweise if h.stufe == "warnung"]
    assert any("SEPA" in t for t in warn) and any("älter als zwei Monate" in t for t in warn)
    rechnen.berechnen(r)  # nicht doppelt
    assert len([h for h in r.hinweise if h.stufe == "warnung"]) == len(warn)
    assert "1 EUR = 1,0850 USD" in steuerfaelle.kurs_text(r)
    assert any("Umsatzsteuer in EUR" in t for t in sicht.steuer_texte(r))


# ------------------------------------------------------------------ Anschrift mit Landzeile
def test_auslandsanschrift_mit_landzeile():
    t = anschrift.anschrift_teilen(
        ["Bluewater Instruments Inc.", "200 Harbor Drive", "Boston, MA 02110", "USA"]
    )
    assert (t["BT-53"], t["BT-52"], t["BT-55"]) == ("02110", "Boston, MA", "US")
    assert pdferkennung.wert_passt("BT-53", "9020", ausland=True)
    assert not pdferkennung.wert_passt("BT-53", "9020") and not pdferkennung.wert_passt(
        "BT-53", "Wien", ausland=True
    )


# ------------------------------------------------------------------ CSV (Variante S, U)
def test_csv_variante_s_alle_faelle(konfig, eingang):
    lauf = pipeline.verarbeiten(eingang("variante-s_steuerfaelle.csv"), konfig)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert st == {f"RE-S-2026-00{i}": "ok" for i in range(1, 7)}, [
        e.hinweise for e in lauf.ergebnisse
    ]
    erwartet = {
        "001": {"AE"},
        "002": {"K"},
        "003": {"G"},
        "004": {"O"},
        "005": {"S"},
        "006": {"AE", "S"},
    }
    for n, kat in erwartet.items():
        assert set(_kategorien(_xml(konfig, f"RE-S-2026-{n}"))) == kat, n
    o = _xml(konfig, "RE-S-2026-004")
    assert o.find(".//ram:SellerTradeParty/ram:SpecifiedTaxRegistration", NS) is None  # BR-O-02
    assert o.find(".//ram:ApplicableTradeTax/ram:RateApplicablePercent", NS) is None  # BR-O-05
    usd = _xml(konfig, "RE-S-2026-005")
    assert usd.findtext(".//ram:TaxCurrencyCode", namespaces=NS) == "EUR"
    betraege = {e.get("currencyID"): e.text for e in usd.iterfind(".//ram:TaxTotalAmount", NS)}
    assert set(betraege) == {"USD", "EUR"}


def test_csv_kleinunternehmer(tmp_path, eingang, konfig):
    konfig.absender.kleinunternehmer = True
    lauf = pipeline.verarbeiten(eingang("variante-u_kleinunternehmer.csv"), konfig)
    (e,) = lauf.ergebnisse
    assert e.status == "ok", e.hinweise
    x = _xml(konfig, e.nummer)
    assert set(_kategorien(x)) == {"E"}
    assert "§ 19 UStG" in x.findtext(".//ram:ApplicableTradeTax/ram:ExemptionReason", namespaces=NS)


# ------------------------------------------------------------------ XML-Eingang in USD
@pytest.mark.parametrize("datei", ["XU-2026-0007_ubl_usd.xml", "XC-2026-0008_cii_usd.xml"])
def test_xml_eingang_usd(konfig, eingang, datei):
    konfig.modus = "pdf_xml"
    shutil.copy(BEISPIELE / "xml-eingang" / datei, konfig.eingang / datei)
    lauf = pipeline.verarbeiten([konfig.eingang / datei], konfig)
    (e,) = lauf.ergebnisse
    assert e.status == "ok", e.hinweise
    x = _xml(konfig, e.nummer)
    assert x.findtext(".//ram:InvoiceCurrencyCode", namespaces=NS) == "USD"
    assert {a.get("currencyID"): a.text for a in x.iterfind(".//ram:TaxTotalAmount", NS)}[
        "EUR"
    ] == "350.23"
    notizen = [n.text for n in x.iterfind(".//ram:IncludedNote/ram:Content", NS)]
    assert sum("Umrechnungskurs" in (n or "") for n in notizen) == 1  # nicht doppelt


# ------------------------------------------------------------------ Nur PDF mit angelernten Vorlagen
def _nur_pdf_konfig(tmp_path, monkeypatch):
    for f in SF.glob("profil-*.yaml"):
        shutil.copy(f, tmp_path / f.name)
    shutil.copytree(SF / "angelernt", tmp_path / "angelernt")
    roh = yaml.safe_load((SF / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    (tmp_path / "k.yaml").write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(pdferkennung, "ablage", lambda profil: tmp_path / "angelernt")
    k = konfig.lade_konfig(tmp_path / "k.yaml")
    k.ordner_anlegen()
    return k


def test_nur_pdf_steuerfaelle(tmp_path, monkeypatch):
    k = _nur_pdf_konfig(tmp_path, monkeypatch)
    dateien = [
        Path(shutil.copy(p, k.eingang / p.name)) for p in sorted((SF / "eingang").glob("*.pdf"))
    ]
    lauf = pipeline.verarbeiten(dateien, k)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert len(st) == 11 and set(st.values()) == {"ok"}, [
        (e.nummer, e.hinweise) for e in lauf.ergebnisse
    ]
    erwartet = {
        "LM-26-2001": {"S"},
        "LM-26-2002": {"AE"},
        "LM-26-2003": {"K"},
        "LM-26-2004": {"G"},
        "LM-26-2005": {"O"},
        "LM-26-2006": {"S"},
        "LM-26-2007": {"AE", "S"},
        "WE-26-0301": {"S"},
        "WE-26-0302": {"AE"},
        "GL-26-0014": {"E"},
        "GL-26-0015": {"E"},
    }
    for n, kat in erwartet.items():
        assert set(_kategorien(_xml(k, n))) == kat, n
    k3 = _xml(k, "LM-26-2003")
    assert k3.findtext(".//ram:BuyerTradeParty//ram:CountryID", namespaces=NS) == "AT"
    assert (
        k3.findtext(".//ram:BuyerTradeParty/ram:SpecifiedTaxRegistration/ram:ID", namespaces=NS)
        == "ATU99999999"
    )
    usd = _xml(k, "LM-26-2006")
    assert usd.findtext(".//ram:InvoiceCurrencyCode", namespaces=NS) == "USD"
    assert usd.findtext(".//ram:TaxCurrencyCode", namespaces=NS) == "EUR"


def test_steuer_fest_aus_druck():
    z = [
        SimpleNamespace(text="Nettobetrag 1.390,60 EUR"),
        SimpleNamespace(text="zzgl. 19 % USt 264,21 EUR"),
    ]
    m = {"*": {"fall": "hinweis"}}
    pdferkennung.steuer_fest_aus_druck(m, {}, z)
    assert m["*"].get("BT-152") == "19"
    m = {"*": {"fall": "hinweis"}}
    pdferkennung.steuer_fest_aus_druck(m, {"steuerhinweis": ("Reverse Charge", None)}, z)
    assert "BT-152" not in m["*"]
