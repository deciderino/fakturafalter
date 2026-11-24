# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Gutschrift im Nur-PDF-Pfad: Belegart (BT-3) aus einem Rahmen um den Titel, Rechnungsbezug (BT-25/26) aus
einem Rahmen um die Bezugszeile. Fiktives Normteile-Layout (beispiele/industrie), Titel und Bezug je Test
umgezeichnet."""

import copy
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from fakturafalter import (
    adapter_pdf,
    anlernen,
    cii,
    konfig,
    pdferkennung,
    pflichtpruefung,
    pipeline,
    rechnen,
)

IND = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"


@pytest.fixture
def k(tmp_path):
    roh = yaml.safe_load((IND / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    pfad = tmp_path / "konfiguration.yaml"
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    k = konfig.lade_konfig(pfad)
    k.ordner_anlegen()
    k.pfad_datei = pfad
    return k


def _druck(
    ziel: Path, i: int, titel: str = "RECHNUNG", bezug: str = "", negativ: bool = False
) -> Path:
    """Normteile-Rechnung ``i`` mit anderem Titel, optional Bezugszeile („Bezug:“ im Infoblock) und mit
    negativ gedruckten Mengen, Beträgen und Summen."""
    spec = importlib.util.spec_from_file_location("industrie_gs", IND / "erzeuge_beispiele.py")
    eb = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = eb  # für @dataclass nötig
    spec.loader.exec_module(eb)
    r = eb.rechnungen()[i]

    class Blatt(eb.Blatt):
        def t(self, x, top, text, size=9, **kw):
            if text == "RECHNUNG":
                text = titel
                if bezug:
                    super().t(350, 188, "Bezug:", 9)
                    super().t(545, 188, bezug, 9, rechts=True)
            elif negativ and x in (378, 545) and top > 280 and text[:1].isdigit():
                text = "-" + text
            super().t(x, top, text, size, **kw)

    pfad = ziel / f"{r.nr}.pdf"
    eb.Blatt = Blatt
    eb.zeichnen(r, pfad)
    return pfad


def _rahmen(s, *texte):
    ws = [w for w in s.woerter(0) if w.t in texte]
    return 0, *pdferkennung.rahmen_um(ws)


def _anlernen(k, s, rahmen: dict, v=None):
    """Bestätigen, Rahmen ziehen, Rechnung bauen und die Vorlage lernen (ohne Ausgabe/Validierung)."""
    for f, r in rahmen.items():
        s.bereich_setzen(f, *r)
    for f in s.fehlende():
        s.bestaetigen(f)
    r = s.rechnung()
    if s.profil is None:
        s.profil = anlernen.profil_anlegen(s.absender, k, k.pfad_datei)
    es = pdferkennung.einstellungen(s.profil)
    v, _ = pdferkennung.lernen(
        r, s.zeilen, s.profil, v, es, pv_vorgabe=s.pv(), stellen=s.stellen(), bereiche=s.bereiche()
    )
    pdferkennung.vorlage_speichern(v, s.profil)
    return r, v


def _sicher(v, prof):
    v["statistik"]["folge_treffer"] = 5
    pdferkennung.vorlage_speichern(v, prof)
    prof["pdf_erkennung"] = {"nur_pdf": True}


def _nur_pdf(k, pdf):
    zs = pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf))
    r, grund = pdferkennung.nur_pdf(pdf, zs, k.pdf_profile, k)
    assert r is not None, grund
    rechnen.berechnen(r)
    pdferkennung.summen_pruefen(r)
    pflichtpruefung.pruefen(r, pipeline.pflicht_kontext(k))
    return r


@pytest.fixture
def gelernt(k, tmp_path):
    """Vorlage aus Rechnung 0 (Titelrahmen) und Gutschrift 1 (Titel aus der Vorlage, Bezugsrahmen)."""
    quelle = tmp_path / "quelle"
    quelle.mkdir()
    s = anlernen.Sitzung(_druck(quelle, 0), k)
    r0, v = _anlernen(k, s, {"BT-3": _rahmen(s, "RECHNUNG")})
    assert r0.art == "380" and not r0.bezuege
    assert v["felder"]["BT-3"]["lage"] == "bereich"
    gs = _druck(quelle, 1, "GUTSCHRIFT", "NB-26-0990 vom 01.10.2026")
    s = anlernen.Sitzung(gs, k)
    assert s.werte["BT-3"].status == "erkannt" and s.belegart() == "381"
    assert "Ursprungsrechnung" in s.belegart_hinweis()
    r1, v = _anlernen(k, s, {"BT-25": _rahmen(s, "NB-26-0990", "vom", "01.10.2026")}, s.vorlage)
    assert r1.art == "381" and r1.bezuege[0].nummer == "NB-26-0990"
    assert "BT-25" in v["felder"]
    _sicher(v, s.profil)
    return quelle, v, s.profil


def test_gutschrift_rahmen_381_mit_bezug(k, gelernt):
    quelle = gelernt[0]
    r = _nur_pdf(k, _druck(quelle, 2, "GUTSCHRIFT", "NB-26-0991 vom 02.10.2026"))
    assert r.art == "381"
    (b,) = r.bezuege
    assert (b.nummer, b.datum) == ("NB-26-0991", date(2026, 10, 2))
    assert r.status == "ok", [h.text for h in r.hinweise if h.stufe != "info"]
    xml = cii.erzeugen(r).decode("utf-8")
    assert "<ram:TypeCode>381</ram:TypeCode>" in xml and "NB-26-0991</ram:IssuerAssignedID>" in xml


def test_rechnung_rahmen_380_ohne_bezug(k, gelernt):
    r = _nur_pdf(k, _druck(gelernt[0], 3))
    assert r.art == "380" and not r.bezuege
    assert r.status == "ok", [h.text for h in r.hinweise if h.stufe != "info"]


def test_alte_vorlage_ohne_felder_bleibt_380(k, gelernt):
    quelle, v, prof = gelernt
    alt = copy.deepcopy(v)
    for f in ("BT-3", "BT-25"):
        alt["felder"].pop(f)
    pdferkennung.vorlage_speichern(alt, prof)
    r = _nur_pdf(k, _druck(quelle, 2, "GUTSCHRIFT", "NB-26-0991 vom 02.10.2026"))
    assert r.art == "380" and not r.bezuege
    assert not [h for h in r.hinweise if h.feld == "BT-3"]


def test_gutschrift_ohne_bezug_pruefen(k, gelernt):
    r = _nur_pdf(k, _druck(gelernt[0], 2, "GUTSCHRIFT"))
    assert r.art == "381" and not r.bezuege
    assert r.status == "pruefen"
    assert any(h.feld == "BT-25" and "§ 31 Abs. 5 UStDV" in h.text for h in r.hinweise)


def test_gutschrift_negativ_gedruckt_positiv(k, gelernt):
    r = _nur_pdf(k, _druck(gelernt[0], 2, "GUTSCHRIFT", "NB-26-0991 vom 02.10.2026", negativ=True))
    assert r.art == "381"
    assert r.summen.netto > 0 and r.summen.brutto > 0
    assert all(p.menge > 0 and p.einzelpreis > 0 for p in r.positionen)
    assert r.status == "ok", [h.text for h in r.hinweise if h.stufe != "info"]
    assert any(h.feld == "BT-3" and "positive Beträge" in h.text for h in r.hinweise)


def test_belegart_und_bezug_lesen():
    assert pdferkennung.belegart_code("GUTSCHRIFT Nr. 12") == "381"
    assert pdferkennung.belegart_code("Rechnung") == "380"
    assert pdferkennung.belegart_code("Gutschriftsanzeige") == "380"  # nur das ganze Wort
    assert pdferkennung.bezug_zerlegen("zu Rechnung Nr. 4711 vom 1. Oktober 2026") == (
        "4711",
        date(2026, 10, 1),
    )
    assert pdferkennung.bezug_zerlegen("RE-77") == ("RE-77", None)
    assert not anlernen.wert_passt_feld("BT-25", "Ursprungsrechnung")
