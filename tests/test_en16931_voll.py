# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.6.0: CSV- und XML-Eingang vollständig nach EN 16931 – je Feldgruppe CSV, CII und UBL hin und zurück,
nicht übernommene XML-Elemente als Warnung, Prüfung mit KoSIT (XRechnung 3.0.2) und Mustang/veraPDF.
Alle Daten erfunden."""

import subprocess
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml

from fakturafalter import adapter_csv, adapter_xml, cii, pipeline, rechnen, sicht, validierung
from fakturafalter import csv_einrichtung as ce
from fakturafalter.gui import texte

from .conftest import BEISPIELE
from .voll import volle_rechnung

braucht_werkzeuge = pytest.mark.skipif(
    not all(validierung.verfuegbar().values()), reason="Java/KoSIT/Mustang nicht vorhanden"
)
XML = BEISPIELE / "xml-eingang"
VARIANTE_D = BEISPIELE / "variante-d_rabatt_gutschrift_lastschrift.csv"
FALLE = [("380", False), ("381", True), ("384", False)]


def _lesen(pfad: Path, konfig):
    _, rs = pipeline.einlesen(pfad, konfig)
    for r in rs:
        rechnen.berechnen(r)
    return {r.nummer: r for r in rs}


def _warnungen(r):
    return [h.text for h in r.hinweise if h.stufe in ("warnung", "pruefen", "fehler")]


# --- CII: alle Gruppen hin und zurück ------------------------------------------------------------------------


@pytest.mark.parametrize("art,lastschrift", FALLE)
@pytest.mark.parametrize("profil", ["EN16931", "XRECHNUNG"])
def test_cii_hin_und_zurueck_bytegleich(konfig, tmp_path, art, lastschrift, profil):
    r = volle_rechnung(konfig, art, lastschrift)
    x = cii.erzeugen(r, profil)
    (tmp_path / "r.xml").write_bytes(x)
    y = adapter_xml.lesen(tmp_path / "r.xml", konfig)[0]
    rechnen.berechnen(y)
    assert not _warnungen(y)
    assert y.status == "ok"
    assert cii.erzeugen(y, profil) == x


def test_cii_gruppen_einzeln(konfig, tmp_path):
    r = volle_rechnung(konfig, "381", True)
    (tmp_path / "r.xml").write_bytes(cii.erzeugen(r, "XRECHNUNG"))
    y = adapter_xml.lesen(tmp_path / "r.xml", konfig)[0]
    s = rechnen.berechnen(y)
    assert y.art == "381" and [(b.nummer, b.datum) for b in y.bezuege] == [
        ("RE-2026-0815", date(2026, 9, 30))
    ]
    assert y.referenzen == r.referenzen and y.lieferung == r.lieferung
    assert y.zahlungsempfaenger == r.zahlungsempfaenger and y.steuervertreter == r.steuervertreter
    assert [(a.kennung, a.daten, a.uri) for a in y.anhaenge] == [
        (a.kennung, a.daten, a.uri) for a in r.anhaenge
    ]
    assert (y.zahlung.mandat, y.zahlung.glaeubiger_id, y.zahlung.lastschrift_iban) == (
        r.zahlung.mandat,
        r.zahlung.glaeubiger_id,
        r.zahlung.lastschrift_iban,
    )
    p, q = y.positionen[0], r.positionen[0]
    assert (
        p.bruttopreis,
        p.preisrabatt,
        p.merkmale,
        p.klassifizierungen,
        p.leistung_von,
        p.standard_id,
    ) == (
        q.bruttopreis,
        q.preisrabatt,
        q.merkmale,
        q.klassifizierungen,
        q.leistung_von,
        q.standard_id,
    )
    assert [(z.zuschlag, z.prozent, z.grund) for z in p.zu_abschlaege] == [
        (False, D("10"), "Mengenrabatt")
    ]
    assert [(z.zuschlag, z.ist_betrag) for z in y.zu_abschlaege] == [
        (z.zuschlag, z.ist_betrag) for z in r.zu_abschlaege
    ]
    assert (s.abschlaege, s.zuschlaege, s.vorausbezahlt, s.zahlbar) == (
        r.summen.abschlaege,
        r.summen.zuschlaege,
        r.summen.vorausbezahlt,
        r.summen.zahlbar,
    )


# --- UBL -----------------------------------------------------------------------------------------------------


def test_ubl_rechnung_mit_rabatt_und_lastschrift(konfig):
    r = _lesen(XML / "XR-2026-0301_ubl_rabatt_lastschrift.xml", konfig)["XR-2026-0301"]
    assert r.status == "ok" and not _warnungen(r), r.hinweise
    z = r.zahlung
    assert (z.art, z.mandat, z.glaeubiger_id, z.lastschrift_iban) == (
        "59",
        "MANDAT-2026-011",
        "DE98ZZZ09999999999",
        "DE75512108001245126199",
    )
    s = r.summen
    assert (
        s.positionen_netto,
        s.abschlaege,
        s.zuschlaege,
        s.netto,
        s.brutto,
        s.vorausbezahlt,
        s.zahlbar,
    ) == (
        D("1040.00"),
        D("20.80"),
        D("15.00"),
        D("1034.20"),
        D("1230.70"),
        D("230.70"),
        D("1000.00"),
    )
    p1, p2 = r.positionen
    assert (p1.bruttopreis, p1.preisrabatt, p1.einzelpreis) == (D("85.00"), D("5.00"), D("80.00"))
    assert [(a.zuschlag, a.prozent) for a in p1.zu_abschlaege] == [(False, D("10"))]
    assert [(a.zuschlag, a.ist_betrag) for a in p2.zu_abschlaege] == [(True, D("20.00"))]
    assert (r.referenzen.projekt, r.referenzen.vertrag, r.referenzen.buchung) == (
        "PRJ-31",
        "V-2026-03",
        "8400",
    )
    assert r.lieferung.anschrift.ort == "Musterhausen"
    assert any(a.daten for a in r.anhaenge) and any(a.uri for a in r.anhaenge)
    assert all(
        r.kontrolle[bt] == wert
        for bt, wert in (("BT-109", s.netto), ("BT-112", s.brutto), ("BT-115", s.zahlbar))
    )


def test_ubl_creditnote_und_cii_gutschrift(konfig):
    u = _lesen(XML / "GS-2026-0009_ubl_gutschrift.xml", konfig)["GS-2026-0009"]
    c = _lesen(XML / "GS-2026-0008_cii_gutschrift.xml", konfig)["GS-2026-0008"]
    for r in (u, c):
        assert r.art == "381" and r.status == "ok" and not _warnungen(r), r.hinweise
        assert r.bezuege and all(p.menge > 0 and p.einzelpreis >= 0 for p in r.positionen)
    assert (u.summen.netto, u.summen.brutto, u.bezuege[0].nummer) == (
        D("297.00"),
        D("353.43"),
        "XR-2026-0301",
    )
    assert (c.summen.netto, c.summen.brutto, c.bezuege[0].nummer) == (
        D("137.40"),
        D("158.72"),
        "RE-2026-0101",
    )


# --- Nicht übernommene Elemente ------------------------------------------------------------------------------


def test_unbekannte_elemente_werden_gewarnt(konfig, tmp_path):
    x = cii.erzeugen(volle_rechnung(konfig), "EN16931").decode()
    x = x.replace(
        "</ram:ApplicableHeaderTradeAgreement>",  # EXTENDED-Feld, in EN 16931 nicht vorgesehen
        "<ram:SalesAgentTradeParty><ram:Name>Vertreter Beispiel</ram:Name></ram:SalesAgentTradeParty>"
        "</ram:ApplicableHeaderTradeAgreement>",
        1,
    )
    (tmp_path / "c.xml").write_text(x, encoding="utf-8")
    r = adapter_xml.lesen(tmp_path / "c.xml", konfig)[0]
    w = [h.text for h in r.hinweise if h.stufe == "warnung"]
    assert len(w) == 1 and w[0].endswith("SalesAgentTradeParty/Name – „Vertreter Beispiel“"), w
    assert r.status == "ok"  # Warnung hält nicht an

    u = (XML / "GS-2026-0009_ubl_gutschrift.xml").read_text(encoding="utf-8")
    u = u.replace(
        "<cbc:DocumentCurrencyCode>",
        "<cbc:TaxPointDate>2026-10-22</cbc:TaxPointDate>"
        "<cbc:LineCountNumeric>1</cbc:LineCountNumeric><cbc:DocumentCurrencyCode>",
        1,
    )
    (tmp_path / "u.xml").write_text(u, encoding="utf-8")
    r = adapter_xml.lesen(tmp_path / "u.xml", konfig)[0]
    w = [h.text for h in r.hinweise if h.stufe == "warnung"]
    assert (
        len(w) == 2
        and any("TaxPointDate" in t for t in w)
        and any("LineCountNumeric" in t for t in w)
    ), w


def test_kaputter_anhang_ist_warnung(konfig, tmp_path):
    u = (XML / "XR-2026-0301_ubl_rabatt_lastschrift.xml").read_text(encoding="utf-8")
    a = u.index("<cbc:EmbeddedDocumentBinaryObject")
    b = u.index(">", a) + 1
    u = u[:b] + "%%%kein-base64%%%" + u[u.index("</cbc:EmbeddedDocumentBinaryObject>") :]
    (tmp_path / "k.xml").write_text(u, encoding="utf-8")
    r = adapter_xml.lesen(tmp_path / "k.xml", konfig)[0]
    assert r.status == "ok" and any(
        "Anhang" in h.text for h in r.hinweise if h.stufe == "warnung"
    ), r.hinweise


# --- CSV -----------------------------------------------------------------------------------------------------


def test_csv_rabatt_gutschrift_lastschrift(konfig):
    rs = _lesen(VARIANTE_D, konfig)
    assert all(r.status == "ok" for r in rs.values()), {n: r.hinweise for n, r in rs.items()}
    a, g, v = rs["RE-2026-0201"], rs["GS-2026-0007"], rs["RE-2026-0202"]
    assert (a.summen.netto, a.summen.ust, a.summen.brutto) == (D("361.50"), D("68.69"), D("430.19"))
    assert [(z.prozent, z.ist_betrag) for z in a.positionen[0].zu_abschlaege] == [
        (D("10"), D("12.00"))
    ]
    assert [(z.zuschlag, z.ist_betrag, z.grund_code) for z in a.zu_abschlaege] == [
        (False, D("15.00"), "95"),
        (True, D("8.50"), "FC"),
    ]
    assert (
        a.zahlung.art,
        a.zahlung.mandat,
        a.zahlung.lastschrift_iban,
        a.zahlung.glaeubiger_id,
    ) == ("59", "MANDAT-2026-007", "DE75512108001245126199", "DE98ZZZ09999999999")
    assert g.art == "381" and (g.summen.netto, g.summen.brutto) == (D("137.40"), D("158.72"))
    assert [(b.nummer, b.datum) for b in g.bezuege] == [("RE-2026-0101", date(2026, 10, 5))]
    assert all(p.menge > 0 and p.einzelpreis > 0 for p in g.positionen)
    assert (v.summen.brutto, v.summen.vorausbezahlt, v.summen.zahlbar) == (
        D("297.50"),
        D("100.00"),
        D("197.50"),
    )


SATZART = """Satzart;Belegnr;Belegdatum;Kundennr;Pos;Bezeichnung;Menge;ME;EP netto;StSchl
K;RE-2026-0401;20.10.2026;K-1001;;;;;;
P;RE-2026-0401;;;1;Schraube M8 verzinkt;100;Stk;0,50;1
R;RE-2026-0401;;;;Sonderrabatt;1;;5,00;1
Z;RE-2026-0401;;;;Versandkosten;1;;4,90;1
"""


def test_csv_satzart_rabatt_und_zuschlag(konfig, tmp_path):
    profil = yaml.safe_load((BEISPIELE / "profil-variante-b.yaml").read_text(encoding="utf-8"))
    profil["aufbau"].update(rabatt="R", zuschlag="Z")
    del (
        profil["felder"]["kopf"]["BT-112"],
        profil["felder"]["kopf"]["BT-72"],
        profil["felder"]["kopf"]["BT-13"],
    )
    profil["felder"]["position"]["BT-155"] = {"spalte": "Bezeichnung", "optional": True}
    (tmp_path / "s.csv").write_text(SATZART, encoding="utf-8")
    (r,) = adapter_csv.lesen(tmp_path / "s.csv", profil, konfig)
    s = rechnen.berechnen(r)
    assert [(z.zuschlag, z.ist_betrag, z.grund, z.grund_code) for z in r.zu_abschlaege] == [
        (False, D("5.00"), "Sonderrabatt", "95"),
        (True, D("4.90"), "Versandkosten", "FC"),
    ]
    assert len(r.positionen) == 1 and (s.netto, s.brutto) == (D("49.90"), D("59.38"))


def test_csv_belegart_werte_und_negative_preise(konfig, tmp_path):
    text = VARIANTE_D.read_text(encoding="utf-8").replace("Gutschrift", "GS")
    (tmp_path / "gs.csv").write_text(text, encoding="utf-8")
    profil = yaml.safe_load((BEISPIELE / "profil-variante-d.yaml").read_text(encoding="utf-8"))
    rs = {r.nummer: r for r in adapter_csv.lesen(tmp_path / "gs.csv", profil, konfig)}
    assert rs["GS-2026-0007"].art == "381"


def test_assistent_schlaegt_neue_spalten_nur_genau_vor():
    z = ce.spalten_vorschlagen(ce.format_erkennen(VARIANTE_D).kopf)
    assert {
        z.get(f) for f in ("belegart", "zeilenart", "BT-138", "BT-113", "zahlungsart", "BT-89")
    } == {"Belegart", "Zeilenart", "Rabatt %", "Vorauszahlung", "Zahlart", "Mandat"}
    assert "BT-90" not in ce.spalten_vorschlagen(["Gläubiger"])  # nur bei genauem Spaltennamen
    assert all(f[1] in texte.EN for f in ce.FELDER)


# --- Sichtteil -----------------------------------------------------------------------------------------------


def test_sichtteil_zeigt_neue_angaben(konfig, tmp_path):
    rs = _lesen(VARIANTE_D, konfig)
    rs.update(_lesen(XML / "XR-2026-0301_ubl_rabatt_lastschrift.xml", konfig))

    def text(r):
        p = tmp_path / f"{r.nummer}.pdf"
        p.write_bytes(sicht.erzeugen(r))
        return " ".join(
            subprocess.run(
                ["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True
            ).stdout.split()
        )

    a, g, x = text(rs["RE-2026-0201"]), text(rs["GS-2026-0007"]), text(rs["XR-2026-0301"])
    assert (
        "Summe Positionen" in a
        and "Versandkosten +8,50" in a
        and "SEPA-Lastschrift" in a
        and "MANDAT-2026-007" in a
    )
    assert (
        "Gutschrift" in g
        and "Zu Rechnung: RE-2026-0101 vom 05.10.2026" in g
        and "gutgeschrieben" in g
    )
    assert (
        "Bereits gezahlt −230,70" in x
        and "Zahlbetrag EUR 1.000,00" in x
        and "Listenpreis 85,00" in x
    )
    assert "Lieferanschrift: Bauhof Halle 3" in x


# --- Prüfung mit den echten Werkzeugen ---------------------------------------------------------------------


@braucht_werkzeuge
@pytest.mark.validierung
def test_kosit_alle_beispiele_und_ausgaben(konfig, tmp_path):
    dateien = sorted(XML.glob("*.xml"))
    for art, ls in FALLE:
        f = tmp_path / f"voll-{art}.xml"
        f.write_bytes(cii.erzeugen(volle_rechnung(konfig, art, ls), "XRECHNUNG"))
        dateien.append(f)
    for quelle in (VARIANTE_D, *sorted(XML.glob("*.xml"))):
        for r in _lesen(quelle, konfig).values():
            f = tmp_path / f"aus-{quelle.stem}-{r.nummer}.xml"
            f.write_bytes(cii.erzeugen(r, "XRECHNUNG"))
            dateien.append(f)
    erg = validierung.kosit(dateien)
    assert [
        (e.datei if hasattr(e, "datei") else i, e.fehler)
        for i, e in enumerate(erg)
        if not e.gueltig
    ] == []


@braucht_werkzeuge
@pytest.mark.validierung
def test_pdf_mustang_verapdf(konfig):
    pdfs = []
    for quelle in (VARIANTE_D, XML / "XR-2026-0301_ubl_rabatt_lastschrift.xml"):
        for r in _lesen(quelle, konfig).values():
            pdfs += [p for p in pipeline.erzeugen(r, konfig, konfig.ausgang) if p.suffix == ".pdf"]
    erg = validierung.pruefen(pdfs)
    assert erg and all(e.gueltig for e in erg), [(e.fehler) for e in erg if not e.gueltig]
