# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kundenbezeichnung 1–3 (0.9.5): je eine Zeile im Adressblock, in der XML ein Käufername BT-44 (fiktive Daten)."""

import io
import re
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pdfplumber
import pytest

from fakturafalter import aufbau, cii, layout, pipeline, rechnen, sicht
from fakturafalter import csv_einrichtung as ce
from fakturafalter.adapter_csv import lesen
from fakturafalter.modell import Herkunft, Partei

from .conftest import BEISPIELE

H = Herkunft("test", 1.0)
VARIANTE_K = BEISPIELE / "variante-k_kundenbezeichnung_erp.csv"


def _roh(**werte):
    return {k: (v, H) for k, v in werte.items()}


def _bauen(konfig, kopf: dict, definition: dict | None = None):
    kopf = {"BT-1": "RE-1", "BT-2": date(2026, 11, 20), "BT-50": "Weg 1", "BT-53": "12345", "BT-52": "Ort",
            **kopf}
    pos = [_roh(**{"BT-153": "Ware", "BT-129": D("1"), "BT-146": D("10"), "steuer": "19"})]
    d = {"mappings": {"steuer": {"unbekannt": "satz"}}, **(definition or {})}
    r = aufbau.rechnung_bauen(_roh(**{k: v for k, v in kopf.items() if v is not None}), pos, d, konfig, "t")
    rechnen.berechnen(r)
    return r


def _name_xml(r) -> str:
    xml = cii.erzeugen(r, "EN16931").decode()
    kaeufer = xml.split("<ram:BuyerTradeParty>")[1]
    return re.search(r"<ram:Name>([^<]*)</ram:Name>", kaeufer).group(1)


def _zeilen(pdf: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return (d.pages[0].extract_text() or "").splitlines()


def test_nur_alte_spalte_kunde_bleibt_wie_bisher(konfig):
    r = _bauen(konfig, {"BT-44": "  Café Morgenrot "})
    assert r.kaeufer.name == "Café Morgenrot" and r.kaeufer.name_zeilen == []
    assert r.kaeufer.namenszeilen() == ["Café Morgenrot"]
    assert _name_xml(r) == "Café Morgenrot"


def test_drei_zeilen_xml_ein_name_sicht_drei_zeilen(konfig):
    r = _bauen(
        konfig,
        {"BT-44": "Firma Alpha", "kunden_name_2": "Werk Süd", "kunden_name_3": "Niederlassung West",
         "BT-56": "z. Hd. Frau Beispiel", "BT-51": "Abteilung Einkauf"},
    )
    assert r.status == "ok"
    assert _name_xml(r) == "Firma Alpha Werk Süd Niederlassung West"
    xml = cii.erzeugen(r, "EN16931").decode()
    assert "<ram:LineTwo>Abteilung Einkauf</ram:LineTwo>" in xml  # BT-51 bleibt Adresszusatz
    assert "Werk Süd</ram:LineTwo>" not in xml and "LineThree" not in xml
    for pdf in (sicht.erzeugen(r, sprache="de"), sicht.erzeugen(r, sprache="de", vorlage=layout.standard())):
        z = _zeilen(pdf)
        i = [n for n, t in enumerate(z) if t.startswith("Firma Alpha")][0]
        block = "\n".join(z[i : i + 12])  # rechte Spalte (Rechnungsnr. …) kann dazwischen stehen
        assert block.index("Firma Alpha") < block.index("Werk Süd") < block.index("Niederlassung West")
        assert block.index("Niederlassung West") < block.index("z. Hd. Frau Beispiel")
        assert block.index("z. Hd. Frau Beispiel") < block.index("Abteilung Einkauf") < block.index("Weg 1")
        assert "Firma Alpha Werk Süd" not in block


def test_zeile_2_leer_keine_luecke(konfig):
    r = _bauen(konfig, {"BT-44": "Firma Alpha", "kunden_name_2": "  ", "kunden_name_3": "Niederlassung West"})
    assert _name_xml(r) == "Firma Alpha Niederlassung West"
    assert r.kaeufer.namenszeilen() == ["Firma Alpha", "Niederlassung West"]


def test_zellen_werden_bereinigt(konfig):
    r = _bauen(konfig, {"BT-44": " Firma  Alpha\n", "kunden_name_2": "Werk\nSüd ", "kunden_name_3": "\tWest"})
    assert r.kaeufer.name == "Firma Alpha Werk Süd West"
    assert r.kaeufer.name_zeilen == ["Firma Alpha", "Werk Süd", "West"]


def test_zeile_1_fehlt_haelt_an_und_rueckt_nicht_nach(konfig):
    r = _bauen(konfig, {"BT-44": "", "kunden_name_2": "Werk Süd"})
    assert r.status == "pruefen"
    bt44 = [h for h in r.hinweise if h.feld == "BT-44"]
    assert len(bt44) == 1 and "fehlt" in bt44[0].text and ("Zeile 1" in bt44[0].text or "Kundenname" in bt44[0].text)
    assert r.kaeufer.name == "" and r.kaeufer.name_zeilen == []


def test_alle_leer_kein_name_ohne_quelle(konfig):
    r = _bauen(konfig, {"kundennummer": "K-1001", "BT-44": "", "kunden_name_2": "", "kunden_name_3": ""})
    assert r.kaeufer.name == "" and r.kaeufer.name_zeilen == []
    assert r.status == "pruefen"
    assert any(h.feld == "BT-44" for h in r.hinweise)


def test_name_geaendert_dann_eine_zeile():
    p = Partei(name="Firma Alpha Werk Süd", name_zeilen=["Firma Alpha", "Werk Süd"])
    assert p.namenszeilen() == ["Firma Alpha", "Werk Süd"]
    p.name = "Firma Beta"  # z. B. in der Prüfansicht korrigiert
    assert p.namenszeilen() == ["Firma Beta"]


def test_beispiel_csv_variante_k(konfig):
    prof = next(p for p in konfig.csv_profile if p["_datei"].endswith("profil-variante-k.yaml"))
    rs = {r.nummer: r for r in lesen(VARIANTE_K, prof, konfig)}
    a, b = rs["2026000101"], rs["2026000102"]
    assert a.kaeufer.name_zeilen == ["Feinmechanik Beispiel GmbH", "Werk Süd", "Wareneingang Tor 3"]
    assert b.kaeufer.name == "Hofladen Beispiel Inh. Erika Musterfrau"
    assert rs["GS-2026-0011"].art == "381"


@pytest.mark.parametrize(
    "kopf, erwartet",
    [
        (["Kundenbezeichnung 1", "Kundenbezeichnung 2", "Kundenbezeichnung 3"],
         {"BT-44": "Kundenbezeichnung 1", "kunden_name_2": "Kundenbezeichnung 2",
          "kunden_name_3": "Kundenbezeichnung 3"}),
        (["Kunde", "Kundenbezeichnung 2", "Kundenbezeichnung 3"],
         {"BT-44": "Kunde", "kunden_name_2": "Kundenbezeichnung 2", "kunden_name_3": "Kundenbezeichnung 3"}),
        (["Kunde", "Kundenbezeichnung 1"], {"BT-44": "Kundenbezeichnung 1"}),
        (["Kundenname", "Kd.-Nr."], {"BT-44": "Kundenname"}),
    ],
)
def test_assistent_ordnet_kundenbezeichnungen_zu(kopf, erwartet):
    zeilen = [["Firma Alpha", "Werk Süd", "West"][: len(kopf)]]
    v = ce.spalten_vorschlagen(kopf, zeilen)
    for f, s in erwartet.items():
        assert v.get(f) == s, (f, v)


def test_assistent_felder_optional_und_profil():
    for f in ("kunden_name_2", "kunden_name_3", "zeichnungsnummer", "index", "BT-128", "BT-143", "BT-144"):
        assert f in ce.FELD and ce.FELD[f][4] is False
    assert "kunden_name_2" not in ce.NUR_GENAU and "index" in ce.NUR_GENAU
    fmt = ce.Format("utf-8", ";", ",", ".", "%d.%m.%Y", ["Nr", "Kundenbezeichnung 1", "Kundenbezeichnung 2"], [])
    p = ce.profil_bauen("t", Path("x.csv"), fmt, {"BT-1": "Nr", "BT-44": "Kundenbezeichnung 1",
                                                   "kunden_name_2": "Kundenbezeichnung 2"}, {}, {}, None)
    assert p["felder"]["kopf"]["kunden_name_2"] == {"spalte": "Kundenbezeichnung 2", "optional": True}
    assert "Kundennummer oder Kunde – Name" not in ce.fehlende_pflicht({"BT-44": "Kundenbezeichnung 1"})


def test_pipeline_variante_k_sichtteil(konfig, eingang):
    konfig.sichtteil = "neu"
    lauf = pipeline.verarbeiten(eingang(VARIANTE_K.name), konfig)
    assert {e.nummer: e.status for e in lauf.ergebnisse} == {
        "2026000101": "ok", "2026000102": "ok", "GS-2026-0011": "ok"}
    pdf = (konfig.ausgang / "2026000101_zugferd.pdf").read_bytes()
    z = _zeilen(pdf)
    assert any(t.startswith("Werk Süd") for t in z) and any(t.startswith("Wareneingang Tor 3") for t in z)
