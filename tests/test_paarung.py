# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
import json

import pikepdf
from lxml import etree

from fakturafalter.pipeline import verarbeiten


def _xml(pdf_pfad):
    with pikepdf.open(pdf_pfad) as pdf:
        assert list(pdf.attachments) == ["factur-x.xml"]
        return etree.fromstring(pdf.attachments["factur-x.xml"].get_file().read_bytes())


NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}


def test_pdf_und_csv_werden_gepaart(konfig, eingang):
    dateien = eingang("druckauftrag-wawi.pdf", "variante-b_wawi_cp1252.csv")
    lauf = verarbeiten(dateien, konfig)
    assert lauf.ok, [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    erg = {e.nummer: e for e in lauf.ergebnisse}
    assert set(erg) == {"RE-2026-0101", "RE-2026-0102", "RE-2026-0103"}
    assert len(erg["RE-2026-0101"].quellen) == 2  # CSV + Druck
    assert len(erg["RE-2026-0103"].quellen) == 1  # nur CSV -> Sichtteil neu
    assert any("Gegenprüfung" in h for h in erg["RE-2026-0101"].hinweise)
    # Druck mit 2 Seiten für 0101, 1 Seite für 0102
    assert len(pikepdf.open(konfig.ausgang / "RE-2026-0101_zugferd.pdf").pages) == 2
    assert len(pikepdf.open(konfig.ausgang / "RE-2026-0102_zugferd.pdf").pages) == 1
    # XRechnung zusätzlich für K-1002 (CII) und K-1003 (UBL gewünscht -> CII)
    assert (konfig.ausgang / "RE-2026-0102_xrechnung.xml").exists()
    assert (konfig.ausgang / "RE-2026-0103_xrechnung.xml").exists()
    assert not (konfig.ausgang / "RE-2026-0101_xrechnung.xml").exists()
    x = _xml(konfig.ausgang / "RE-2026-0101_zugferd.pdf")
    assert x.findtext(".//ram:GrandTotalAmount", namespaces=NS) == "384.82"
    assert (
        x.findtext(".//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID", namespaces=NS)
        == "urn:cen.eu:en16931:2017"
    )
    # Eingang geleert
    assert not list(konfig.eingang.iterdir())
    assert sorted(p.name for p in konfig.erledigt.iterdir()) == [
        "druckauftrag-wawi.pdf",
        "variante-b_wawi_cp1252.csv",
    ]


def test_abweichung_csv_druck_geht_in_pruefung(konfig, eingang):
    (csv,) = eingang("variante-b_wawi_cp1252.csv")
    eingang("druckauftrag-wawi.pdf")
    t = (
        csv.read_bytes()
        .decode("cp1252")
        .replace(
            'P;RE-2026-0102;;;;;;;;;;;;;;1;C-300;Kabel NYM 3x1,5 mm²;50;',
            'P;RE-2026-0102;;;;;;;;;;;;;;1;C-300;Kabel NYM 3x1,5 mm²;60;',
        )
    )
    csv.write_bytes(t.encode("cp1252"))
    lauf = verarbeiten(list(konfig.eingang.iterdir()), konfig)
    erg = {e.nummer: e for e in lauf.ergebnisse}
    assert erg["RE-2026-0102"].status == "pruefen"
    assert erg["RE-2026-0101"].status == "ok"
    d = json.loads((konfig.pruefen / "RE-2026-0102.json").read_text(encoding="utf-8"))
    assert any("weichen ab" in h["text"] for h in d["hinweise"])
    assert not (konfig.ausgang / "RE-2026-0102_zugferd.pdf").exists()
    assert (konfig.pruefen / "druckauftrag-wawi.pdf").exists()


def test_nur_pdf(konfig, eingang):
    lauf = verarbeiten(eingang("druckauftrag-wawi.pdf"), konfig)
    assert lauf.ok and [e.nummer for e in lauf.ergebnisse] == ["RE-2026-0101", "RE-2026-0102"]


def test_doppelte_rechnungsnummer_und_unbekannte_datei(konfig, eingang):
    dateien = eingang(
        "variante-a_positionen_utf8.csv", "variante-b_wawi_cp1252.csv", "textdruck-wawi_cp1252.txt"
    )
    lauf = verarbeiten(dateien, konfig)
    assert "textdruck-wawi_cp1252.txt" in " ".join(lauf.datei_fehler)
    assert sum(e.status == "fehler" for e in lauf.ergebnisse) == 3  # 3 Nummern doppelt
    assert (konfig.fehler / "textdruck-wawi_cp1252.txt").exists()


def test_bereits_erzeugt_wird_nicht_ueberschrieben(konfig, eingang):
    verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    lauf = verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert all(e.status == "pruefen" for e in lauf.ergebnisse)
