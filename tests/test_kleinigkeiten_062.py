# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.6.2: Gutschrift ohne Fälligkeit in der CII, Prüfziffer USt-IdNr. des Käufers (BT-48),
GTIN-Warnung (BT-157). Alle Daten erfunden."""
from lxml import etree

import pytest

from fakturafalter import cii, pflichtpruefung as pp, pipeline, rechnen, sicht
from fakturafalter.cii import NS
from .conftest import BEISPIELE
from .test_pflichtpruefung import CTX, felder, gueltig
from .voll import volle_rechnung

VARIANTE_D = BEISPIELE / "variante-d_rabatt_gutschrift_lastschrift.csv"
XML = BEISPIELE / "xml-eingang"
GUTSCHRIFT_SATZ = "Der Betrag wird Ihnen gutgeschrieben."


def _lesen(pfad, konfig):
    _, rs = pipeline.einlesen(pfad, konfig)
    for r in rs:
        rechnen.berechnen(r)
    return {r.nummer: r for r in rs}


def _cii(r):
    return etree.fromstring(cii.erzeugen(r, "EN16931"))


def test_gutschrift_ohne_faelligkeit_in_modell_und_cii(konfig):
    rs = _lesen(VARIANTE_D, konfig)
    g, a = rs["GS-2026-0007"], rs["RE-2026-0201"]
    assert g.art == "381" and g.zahlung.bedingungen == GUTSCHRIFT_SATZ
    assert g.zahlung.faellig is None and g.zahlung.ziel_tage is None
    gx = _cii(g)
    pt = gx.find(".//ram:SpecifiedTradePaymentTerms", NS)
    assert pt is not None and pt.findtext("ram:Description", namespaces=NS) == GUTSCHRIFT_SATZ
    assert pt.find("ram:DueDateDateTime", NS) is None
    assert a.zahlung.faellig is not None and "Zahlbar innerhalb" in a.zahlung.bedingungen
    ax = _cii(a)
    assert ax.find(".//ram:DueDateDateTime", NS) is not None
    assert "Zahlbar innerhalb" in (ax.findtext(".//ram:Description", namespaces=NS) or "")


def test_gutschrift_xml_eingang_ohne_faelligkeit(konfig):
    for name in ("GS-2026-0008_cii_gutschrift.xml", "GS-2026-0009_ubl_gutschrift.xml"):
        r = _lesen(XML / name, konfig)[name.split("_")[0]]
        assert r.art == "381" and r.zahlung.faellig is None
        assert r.zahlung.bedingungen == GUTSCHRIFT_SATZ
        x = _cii(r)
        pt = x.find(".//ram:SpecifiedTradePaymentTerms", NS)
        assert pt.findtext("ram:Description", namespaces=NS) == GUTSCHRIFT_SATZ
        assert pt.find("ram:DueDateDateTime", NS) is None


def test_sicht_und_cii_derselbe_gutschrift_satz(konfig, tmp_path):
    import subprocess
    r = _lesen(VARIANTE_D, konfig)["GS-2026-0007"]
    p = tmp_path / "gs.pdf"
    p.write_bytes(sicht.erzeugen(r))
    text = " ".join(subprocess.run(["pdftotext", "-layout", str(p), "-"],
                                   capture_output=True, text=True).stdout.split())
    assert GUTSCHRIFT_SATZ in text and "Zahlbar" not in text and "Fällig am" not in text
    assert _cii(r).findtext(".//ram:Description", namespaces=NS) == GUTSCHRIFT_SATZ


def test_kaeufer_ust_id_pruefziffer():
    r = gueltig()
    r.kaeufer.ust_id = "DE000000001"
    f = felder(r)
    assert "ungültig" in f["BT-48"] and r.status == "pruefen"
    r = gueltig()
    r.kaeufer.ust_id = "DE000000003"
    assert felder(r) == {} and r.status == "ok"


def test_beispiele_kaeufer_ust_id_und_leitweg_gueltig(konfig):
    rs = _lesen(VARIANTE_D, konfig)
    rs.update(_lesen(XML / "XR-2026-0301_ubl_rabatt_lastschrift.xml", konfig))
    for r in rs.values():
        if r.kaeufer.ust_id:
            assert pp.ust_id_de_gueltig(r.kaeufer.ust_id), r.kaeufer.ust_id
        assert felder(r) == {} and r.status == "ok", r.hinweise
    assert rs["RE-2026-0201"].kaeufer.ust_id == "DE000000003"
    assert rs["GS-2026-0007"].leitweg_id == "04011000-12345-03"
    assert rs["XR-2026-0301"].leitweg_id == "04011000-12345-03"


@pytest.mark.parametrize("nr,ok", [
    ("4000000000013", True), ("4000000000006", True), ("4000000000017", False),
    ("4000000000000", False), ("12345670", True), ("", False), ("ABC", False),
])
def test_gtin_pruefziffer(nr, ok):
    assert pp.gtin_gueltig(nr) is ok


def test_gtin_ungueltig_ist_warnung_nicht_pruefen():
    r = trans = gueltig()
    r.positionen[0].standard_id, r.positionen[0].standard_schema = "4000000000017", "0160"
    assert felder(r) == {} and r.status == "ok"
    w = [h for h in r.hinweise if h.stufe == "warnung" and h.feld == "Pos 1 BT-157"]
    assert len(w) == 1 and "Prüfziffer" in w[0].text


def test_gtin_in_beispielen_gueltig(konfig):
    r = _lesen(XML / "XR-2026-0301_ubl_rabatt_lastschrift.xml", konfig)["XR-2026-0301"]
    gtin = next(p.standard_id for p in r.positionen if p.standard_schema == "0160")
    assert gtin == "4000000000013" and pp.gtin_gueltig(gtin)
    pp.pruefen(r, CTX)
    assert r.status == "ok"
    assert not any("GTIN" in (h.text or "") for h in r.hinweise)
    v = volle_rechnung(konfig)
    assert pp.gtin_gueltig(v.positionen[0].standard_id)
    pp.pruefen(v, CTX)
    assert v.status == "ok"
    assert not any("GTIN" in (h.text or "") for h in v.hinweise)


def test_leitweg_pruefung_ab_097_aktiv():
    """0.6.2 ließ die Leitweg-Prüfung aus; ab 0.9.7 ist sie aktiv (nur für Werte, die wie eine Leitweg-ID aussehen)."""
    regel = next(g for g in pp.REGELN if g.id == "xrechnung_leitweg")
    assert regel.aktiv is True
