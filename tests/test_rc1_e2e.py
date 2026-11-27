# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""1.0.0-rc1 Ende-zu-Ende mit fiktiven Daten: Assistent → Eingang → ZUGFeRD (+ XRechnung aus der Liste)
→ lokale Prüfung mit Mustang und KoSIT (offline)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from lxml import etree

from fakturafalter import csv_einrichtung as ce
from fakturafalter import pipeline, validierung
from fakturafalter.konfig import XRechnungEintrag

from .conftest import BEISPIELE

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
}


def profil_per_assistent(datei: Path, name: str) -> dict:
    """Dieselben Schritte wie der Block-Assistent mit seinen Vorschlägen (ohne Oberfläche)."""
    fmt = ce.format_erkennen(datei)
    bloecke, sa = ce.bloecke_vorschlagen(fmt)
    assert bloecke
    zu, steuer, einheiten = {}, {}, {}
    for b in bloecke:
        kopf = list(b.get("kopf") or [])
        zeilen = [r for _n, r in b.get("daten") or []]
        v = ce.spalten_vorschlagen(kopf, zeilen, wiederholend=bool(b.get("wiederholend"))) if kopf else {}
        if not b.get("wiederholend"):
            v = {f: s for f, s in v.items() if f not in ce.positionsfelder()}
        zu[b.get("id") or b["typ"]] = v
        if b.get("wiederholend"):
            for feld, ziel, fn in (("steuer", steuer, ce.steuer_vorschlag), ("BT-130", einheiten, ce.einheiten_vorschlag)):
                if v.get(feld) and v[feld] in kopf:
                    i = kopf.index(v[feld])
                    ziel.update(fn([r[i] for _n, r in b.get("daten") or [] if i < len(r)]))
    alle = {}
    for z in zu.values():
        for f, s in z.items():
            alle.setdefault(f, s)
    assert not ce.fehlende_pflicht(alle), ce.fehlende_pflicht(alle)
    profil = ce.profil_bauen_bloecke(name, datei, fmt, bloecke, zu, steuer, einheiten, {}, sa)
    profil.setdefault("aufbau", {})["einheit_fehlt_stueck"] = True
    assert profil.get("version") == 2
    return profil


def _pruefen_alles(dateien: list[Path]) -> None:
    erg = validierung.pruefen(dateien)
    assert erg and all(e.gueltig and not e.fehler for e in erg), [e.zeile() for e in erg]
    werkzeuge = {e.werkzeug for e in erg}
    assert any("ustang" in w or "veraPDF" in w for w in werkzeuge) or not any(
        d.suffix == ".pdf" for d in dateien
    ), werkzeuge
    assert any("KoSIT" in w for w in werkzeuge), werkzeuge


pytestmark = pytest.mark.skipif(
    not all(validierung.verfuegbar().values()), reason="Mustang/KoSIT nicht vorhanden"
)


@pytest.mark.validierung
def test_e2e_blockformat_zugferd_und_xrechnung_aus_liste(konfig, tmp_path):
    roh = (BEISPIELE / "beispiel-satzart-pos-kopf-und-restzeile.csv").read_bytes()
    roh = roh.rstrip()
    if roh.endswith(b"."):
        roh = roh[:-1].rstrip()
    text = roh.decode("utf-8")
    text = text.replace("Satzart;Kunde1;Kunde2;Kunde3;Strasse;PLZ;Ort;USt.-ID;", "Satzart;Kunde1;Kunde2;Kunde3;Strasse;PLZ;Ort;USt.-ID;E-Rechnungsadresse;", 1)
    text = text.replace("#Kunde;Nordlicht Bürobedarf GmbH;Einkauf;;Musterweg 12;20144;Hamburg;DE812345673;", "#Kunde;Nordlicht Bürobedarf GmbH;Einkauf;;Musterweg 12;20144;Hamburg;DE812345673;rechnung@nordlicht.example;", 1)
    assert "rechnung@nordlicht.example" in text
    datei = tmp_path / "fiktiv-block.csv"
    datei.write_bytes(text.encode("utf-8") + b"\r\n\x1a")
    profil = profil_per_assistent(datei, "fiktiv-e2e-block")
    konfig.csv_profile = [profil] + [p for p in konfig.csv_profile if not p.get("_eingebaut")]
    konfig.xrechnung_zusatz = True
    konfig.xrechnung_liste = [XRechnungEintrag(name="Nordlicht Bürobedarf GmbH", leitweg_id="04011000-12345-03")]
    ziel = konfig.eingang / datei.name
    shutil.copy(datei, ziel)
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert not lauf.datei_fehler, lauf.datei_fehler
    (e,) = lauf.ergebnisse
    assert e.status == "ok", (e.status, e.hinweise)
    pdf = next(p for p in e.dateien if p.suffix == ".pdf")
    xml = next(p for p in e.dateien if p.suffix == ".xml")
    baum = etree.parse(str(xml))
    assert baum.findtext(".//ram:BuyerReference", namespaces=NS) == "04011000-12345-03"
    assert baum.findtext(".//ram:BuyerTradeParty/ram:Name", namespaces=NS).startswith("Nordlicht")
    assert baum.findtext(".//ram:InvoiceCurrencyCode", namespaces=NS) == "EUR"
    _pruefen_alles([pdf, xml])


@pytest.mark.validierung
@pytest.mark.parametrize("eintrag", ["name", "nummer"])
def test_e2e_standard_skonto_und_xrechnung(konfig, tmp_path, eintrag):
    ziel = konfig.eingang / "fakturafalter-standard-voll.csv"
    shutil.copy(BEISPIELE / "fakturafalter-standard-voll.csv", ziel)
    konfig.xrechnung_zusatz = True
    konfig.xrechnung_liste = [
        XRechnungEintrag(name="Beispiel Handel GmbH")
        if eintrag == "name"
        else XRechnungEintrag(nummer="K-1001", leitweg_id="04011000-12345-03")
    ]
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert not lauf.datei_fehler, lauf.datei_fehler
    assert len(lauf.ergebnisse) == 2
    dateien = []
    for e in lauf.ergebnisse:
        assert e.status == "ok", (e.nummer, e.status, e.hinweise)
        xs = [p for p in e.dateien if p.suffix == ".xml"]
        assert len(xs) == 1, e.dateien
        dateien += e.dateien
        if e.nummer == "RE-2026-1001":
            bt20 = etree.parse(str(xs[0])).findtext(".//ram:SpecifiedTradePaymentTerms/ram:Description", namespaces=NS)
            assert "#SKONTO#TAGE=10#PROZENT=2.00#" in bt20 and "#SKONTO#TAGE=20#PROZENT=1.00#" in bt20, bt20
    _pruefen_alles([Path(d) for d in dateien])


@pytest.mark.validierung
@pytest.mark.parametrize("zusatz,name", [(True, "Andere GmbH"), (False, "Beispiel Handel GmbH")])
def test_e2e_ohne_treffer_und_schalter_aus_keine_xrechnung(konfig, zusatz, name):
    ziel = konfig.eingang / "fakturafalter-standard-minimal.csv"
    shutil.copy(BEISPIELE / "fakturafalter-standard-minimal.csv", ziel)
    konfig.xrechnung_zusatz, konfig.xrechnung_liste = zusatz, [XRechnungEintrag(name=name)]
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert not lauf.datei_fehler, lauf.datei_fehler
    assert all(e.status == "ok" for e in lauf.ergebnisse), [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    assert not [p for e in lauf.ergebnisse for p in e.dateien if p.suffix == ".xml"]
    _pruefen_alles([p for e in lauf.ergebnisse for p in e.dateien])


def test_xrechnung_ohne_e_rechnungsadresse_zur_pruefung(konfig):
    """XRechnung 3.0 verlangt BT-49: ohne Adresse keine ungültige Datei, sondern ein klarer Prüffall."""
    ziel = konfig.eingang / "fakturafalter-standard-minimal.csv"
    shutil.copy(BEISPIELE / "fakturafalter-standard-minimal.csv", ziel)
    konfig.xrechnung_zusatz = True
    konfig.xrechnung_liste = [XRechnungEintrag(name="Beispiel Handel GmbH", leitweg_id="04011000-12345-03")]
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert lauf.ergebnisse
    for e in lauf.ergebnisse:
        assert e.status == "pruefen"
        assert any("E-Rechnungsadresse des Kunden (BT-49) fehlt" in h for h in e.hinweise), e.hinweise
        assert not [p for p in e.dateien if str(p).endswith(".xml")]
