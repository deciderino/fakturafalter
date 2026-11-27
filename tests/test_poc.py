# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Proof of Concept (beispiele/poc/): Käufer aus der CSV, Verkäufer/Zahlung/Format aus dem Profil, Käufer nur aus der Quelle."""
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pikepdf
import pytest
from lxml import etree

from fakturafalter.aufbau import rechnung_bauen
from fakturafalter.gui.daten import absender_fehlt
from fakturafalter.konfig import lade_konfig
from fakturafalter.modell import Herkunft, Partei
from fakturafalter.pipeline import verarbeiten

POC = Path(__file__).resolve().parent.parent / "beispiele" / "poc"
BEISPIELE = POC.parent
NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}
H = Herkunft("test", 1.0)


@pytest.fixture
def poc(tmp_path):
    k = lade_konfig(POC / "konfiguration.yaml")
    for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen"):
        setattr(k, n, tmp_path / n)
    k.eingang.mkdir()
    return k


def _xml(pdf_pfad):
    with pikepdf.open(pdf_pfad) as pdf:
        return etree.fromstring(pdf.attachments["factur-x.xml"].get_file().read_bytes())


def _kopf(**extra):
    k = {"BT-1": ("X-1", H), "BT-2": (date(2026, 10, 28), H), "BT-72": (date(2026, 10, 23), H), "kundennummer": ("K-1001", H)}
    k.update({f: (v, H) for f, v in extra.items()})
    return k


POS = [{"BT-126": ("1", H), "BT-153": ("Test", H), "BT-129": (Decimal("1"), H), "BT-146": (Decimal("10"), H),
        "steuer": ("1", H)}]
STEUER = {"steuer": {"1": {"BT-151": "S", "BT-152": 19}}}


def test_poc_ende_zu_ende_aus_der_quelle(poc):
    assert "kundenstamm" not in poc.csv_profile[0]
    assert not poc.absender.name                       # Konfiguration ohne Absender
    dateien = [Path(shutil.copy(POC / n, poc.eingang / n)) for n in ("TM-2026-0042.csv", "TM-2026-0042.pdf")]
    lauf = verarbeiten(dateien, poc)
    assert lauf.ok, (lauf.datei_fehler, [(e.nummer, e.hinweise) for e in lauf.ergebnisse])
    (e,) = lauf.ergebnisse
    assert e.status == "ok" and len(e.quellen) == 2
    assert not [h for h in e.hinweise if not h.startswith("INFO")], e.hinweise
    assert any("Gegenprüfung" in h for h in e.hinweise)
    assert [p.name for p in e.dateien] == ["TM-2026-0042_zugferd.pdf"]   # nur ZUGFeRD, keine XRechnung
    x = _xml(e.dateien[0])
    f = lambda p: x.findtext(p, namespaces=NS)  # noqa: E731
    assert f(".//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == "urn:cen.eu:en16931:2017"
    assert f(".//ram:SellerTradeParty/ram:Name") == "Tischlerei Muster GmbH"
    assert f(".//ram:BuyerTradeParty/ram:Name") == "Beispiel Bau GmbH"
    assert f(".//ram:BuyerTradeParty/ram:ID") == "K-2001"
    assert f(".//ram:BuyerTradeParty/ram:SpecifiedTaxRegistration/ram:ID") == "DE000000003"
    assert f(".//ram:BuyerTradeParty/ram:URIUniversalCommunication/ram:URIID") == "rechnung@beispiel-bau.example"
    assert x.find(".//ram:BuyerReference", namespaces=NS) is None    # Leitweg-ID leer -> kein BT-10
    assert f(".//ram:IBANID") == "DE36000000000000000000"
    assert f(".//ram:AccountName") == "Tischlerei Muster GmbH"
    assert f(".//ram:TaxBasisTotalAmount") == "2259.75"
    assert f(".//ram:TaxTotalAmount") == "429.35"
    assert f(".//ram:GrandTotalAmount") == "2689.10"
    assert f(".//ram:DueDateDateTime/*") == "20261111"
    assert not list(poc.eingang.iterdir()) and len(list(poc.erledigt.iterdir())) == 2


def test_poc_einrichtung_vollstaendig_durch_profil(poc):
    assert absender_fehlt(poc) == []


def test_leitweg_id_aus_csv_auch_bei_zugferd(poc, tmp_path):
    text = (POC / "TM-2026-0042.csv").read_text(encoding="utf-8")
    zeilen = text.splitlines()
    neu = [zeilen[0]] + [z.replace(";rechnung@beispiel-bau.example;;", ";rechnung@beispiel-bau.example;04011000-12345-03;")
                         for z in zeilen[1:]]
    d = poc.eingang / "TM-2026-0042.csv"
    d.write_text("\n".join(neu) + "\n", encoding="utf-8")
    lauf = verarbeiten([d], poc)
    (e,) = lauf.ergebnisse
    assert e.status == "ok", e.hinweise
    assert _xml(e.dateien[0]).findtext(".//ram:BuyerReference", namespaces=NS) == "04011000-12345-03"


def test_csv_kaeufer_kommt_nur_aus_der_quelle():
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    dfn = {"_basis": BEISPIELE, "mappings": STEUER}
    r = rechnung_bauen(_kopf(**{"BT-44": "Neuer Name GmbH", "BT-50": "Beispielweg 5", "BT-10": "991-12345-99"}), POS, dfn, k, "t")
    assert r.kaeufer.name == "Neuer Name GmbH"
    assert r.kaeufer.anschrift.strasse == "Beispielweg 5"
    assert r.kaeufer.kennung == "K-1001"
    assert r.leitweg_id == "991-12345-99"
    assert r.status == "ok", r.hinweise


def test_ohne_kaeufernamen_bleibt_pruefen():
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    r = rechnung_bauen(_kopf(), POS, {"_basis": BEISPIELE, "mappings": STEUER}, k, "t")
    assert r.status == "pruefen"
    assert any("Name des Käufers fehlt" in h.text for h in r.hinweise)


def test_kaeufer_nur_aus_quelle_ohne_kundenstamm():
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    r = rechnung_bauen(_kopf(**{"BT-44": "Firma X", "BT-53": "01234", "BT-52": "Ort", "zahlungsziel_tage": "30"}),
                       POS, {"_basis": BEISPIELE, "mappings": STEUER}, k, "t")
    assert r.status == "ok", r.hinweise
    assert (r.kaeufer.name, r.kaeufer.anschrift.plz, r.kaeufer.anschrift.land) == ("Firma X", "01234", "DE")
    assert r.zahlung.ziel_tage == 30 and r.zahlung.faellig == date(2026, 11, 27)


def test_verkaeufer_und_zahlung_im_profil_mischen_mit_konfig():
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    dfn = {"_basis": BEISPIELE, "mappings": STEUER,
           "verkaeufer": {"name": "Andere GmbH"}, "zahlung": {"iban": "DE02 1203 0000 0000 2020 51", "ziel_tage": 7},
           "bemerkungen": []}
    r = rechnung_bauen(_kopf(**{"BT-44": "Beispiel Handel GmbH"}), POS, dfn, k, "t")
    assert r.verkaeufer.name == "Andere GmbH"
    assert r.verkaeufer.ust_id == k.absender.ust_id              # nicht genannt -> aus der Konfiguration
    assert r.zahlung.iban == "DE02120300000000202051"
    assert r.zahlung.kontoinhaber == "Andere GmbH"                # neuer Verkäufer -> dessen Name
    assert r.zahlung.ziel_tage == 7                              # Profil zahlt vor der Konfiguration
    assert r.bemerkungen == []
    assert k.absender.name == "Muster GmbH" and k.zahlung.iban != r.zahlung.iban   # Konfig unverändert


def test_ohne_profilbloecke_bleibt_alles_wie_bisher():
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    r = rechnung_bauen(_kopf(**{"BT-44": "Beispiel Handel GmbH"}), POS, {"_basis": BEISPIELE, "mappings": STEUER}, k, "t")
    assert r.verkaeufer == k.absender and r.verkaeufer is not k.absender
    assert r.zahlung.iban == k.zahlung.iban and r.bemerkungen == k.bemerkungen
    assert r.ausgabeformat == "ZUGFERD_EN16931" and r.status == "ok"


@pytest.mark.parametrize("fmt,erwartet,status", [
    ("XRECHNUNG_CII", "XRECHNUNG_CII", "ok"),
    ("aus_kundenstamm", "ZUGFERD_EN16931", "ok"),  # alter Schlüssel gilt als ZUGFeRD
    ("QUATSCH", "ZUGFERD_EN16931", "pruefen"),
])
def test_ausgabeformat_im_profil(fmt, erwartet, status):
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    # Kunde steht in der XRechnung-Liste – rc1: dann braucht es die E-Rechnungsadresse (BT-49)
    kopf = _kopf(**{"BT-44": "Stadtverwaltung Musterhausen", "BT-49": "rechnung@musterhausen.example"})
    kopf["kundennummer"] = ("K-1002", H)
    r = rechnung_bauen(kopf, POS, {"_basis": BEISPIELE, "mappings": STEUER, "ausgabe": {"format": fmt}}, k, "t")
    assert r.ausgabeformat == erwartet and r.status == status, r.hinweise


def test_zugferd_fest_leitweg_aus_der_liste():
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    kopf = _kopf(**{"BT-44": "Stadtverwaltung Musterhausen"})
    kopf["kundennummer"] = ("K-1002", H)
    r = rechnung_bauen(kopf, POS, {"_basis": BEISPIELE, "mappings": STEUER, "ausgabe": {"format": "ZUGFERD_EN16931"}}, k, "t")
    assert r.ausgabeformat == "ZUGFERD_EN16931"
    assert isinstance(r.kaeufer, Partei) and r.leitweg_id == "04011000-12345-03"
