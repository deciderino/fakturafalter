# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""1.0.0-rc2 Ende-zu-Ende mit fiktiven Daten → lokale Prüfung mit Mustang und KoSIT (offline):
Excel/ODS über ein Profil, Layoutformat 2 (Briefpapier enthält …, Platzhalter), Skonto, Umwandeln von Hand."""

from __future__ import annotations

import shutil
from pathlib import Path

import pdfplumber
import pytest
import yaml
from lxml import etree

from fakturafalter import pipeline, validierung
from fakturafalter.ueberwachung import Waechter

from .conftest import BEISPIELE

RC2 = BEISPIELE / "rc2"
NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}

pytestmark = pytest.mark.skipif(not all(validierung.verfuegbar().values()), reason="Mustang/KoSIT nicht vorhanden")


def _yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _pruefen_alles(dateien: list[Path]) -> None:
    erg = validierung.pruefen(dateien)
    assert erg and all(e.gueltig and not e.fehler for e in erg), [e.zeile() for e in erg]
    werkzeuge = {e.werkzeug for e in erg}
    assert any("ustang" in w or "veraPDF" in w for w in werkzeuge), werkzeuge
    assert any("KoSIT" in w for w in werkzeuge), werkzeuge


def _xml_aus_pdf(pdf: Path) -> etree._Element:
    import pikepdf

    with pikepdf.open(pdf) as doc:
        return etree.fromstring(next(iter(doc.attachments.values())).get_file().read_bytes())


@pytest.mark.validierung
@pytest.mark.parametrize(("datei", "profil"), [("rechnungen-export-fiktiv.xlsx", "profil-rc2-excel.yaml"),
                                               ("rechnungen-export-fiktiv.ods", "profil-rc2-ods.yaml")])
def test_e2e_tabelle_layout2_platzhalter(konfig, datei, profil):
    konfig.csv_profile = [_yaml(RC2 / profil)]
    konfig.pdf_verwenden = False
    konfig.modus = "csv"
    konfig.roh["layout"] = _yaml(RC2 / "layout-platzhalter-fiktiv.yaml")["layout"]
    ziel = Path(shutil.copy(RC2 / datei, konfig.eingang / datei))
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert not lauf.datei_fehler, lauf.datei_fehler
    assert [e.status for e in lauf.ergebnisse] == ["ok", "ok"], [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    pdfs = sorted(konfig.ausgang.glob("*_zugferd.pdf"))
    x = _xml_aus_pdf(pdfs[0])
    assert x.findtext(".//ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID", namespaces=NS) == "PO-77801"
    assert x.findtext(".//ram:DuePayableAmount", namespaces=NS) == "264.78"
    _pruefen_alles(pdfs)


@pytest.mark.validierung
def test_e2e_skonto_mit_layout_briefpapier_format2(konfig):
    konfig.roh["layout"] = _yaml(BEISPIELE / "layout" / "layout-beispiel.yaml")["layout"]
    ziel = Path(shutil.copy(BEISPIELE / "fakturafalter-standard-voll.csv", konfig.eingang / "standard-voll.csv"))
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert not lauf.datei_fehler, lauf.datei_fehler
    assert all(e.status == "ok" for e in lauf.ergebnisse), [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    pdfs = [Path(p) for e in lauf.ergebnisse for p in e.dateien if Path(p).suffix == ".pdf"]
    pdf = next(p for p in pdfs if p.name.startswith("RE-2026-1001"))
    bt20 = _xml_aus_pdf(pdf).findtext(".//ram:SpecifiedTradePaymentTerms/ram:Description", namespaces=NS)
    assert "#SKONTO#TAGE=10#PROZENT=2.00#" in bt20, bt20
    with pdfplumber.open(pdf) as doc:
        text = doc.pages[0].extract_text()
    # Briefpapier enthält den Namen: Absender/Fußzeile drucken ihn nicht noch einmal (nur das Briefpapier)
    assert "Muster GmbH ·" not in text and "Musterstraße 1 · 12345 Musterstadt" in text
    assert b"/Form" in pdf.read_bytes()  # Briefpapier eingebettet
    _pruefen_alles(pdfs)


@pytest.mark.validierung
def test_e2e_umwandeln_von_hand_excel(konfig, tmp_path):
    konfig.csv_profile = [_yaml(RC2 / "profil-rc2-excel.yaml")]
    konfig.pdf_verwenden = False
    konfig.modus = "csv"
    quelle = tmp_path / "irgendwo"
    quelle.mkdir()
    datei = Path(shutil.copy(RC2 / "rechnungen-export-fiktiv.xlsx", quelle / "export.xlsx"))
    vorher = datei.read_bytes()
    lauf = Waechter(konfig).manuell([datei])
    assert lauf is not None and [e.status for e in lauf.ergebnisse] == ["ok", "ok"]
    assert datei.read_bytes() == vorher  # Original unangetastet
    _pruefen_alles(sorted(konfig.ausgang.glob("*_zugferd.pdf")))
