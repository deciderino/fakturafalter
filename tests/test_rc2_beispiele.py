# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""rc2: Beispieldateien unter beispiele/rc2/ und beispiele/layout/ (alle Daten fiktiv) laufen wie beschrieben."""

import shutil
import sys
from pathlib import Path

import pdfplumber
import pytest
import yaml

from fakturafalter import layout, pipeline

ROOT = Path(__file__).resolve().parents[1]
RC2 = ROOT / "beispiele" / "rc2"


def _yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("datei", "profil"), [("rechnungen-export-fiktiv.xlsx", "profil-rc2-excel.yaml"),
                                               ("rechnungen-export-fiktiv.ods", "profil-rc2-ods.yaml")])
def test_tabelle_mit_profil_und_platzhalterlayout(konfig, datei, profil):
    konfig.csv_profile = [_yaml(RC2 / profil)]
    konfig.pdf_verwenden = False
    konfig.modus = "csv"
    konfig.roh["layout"] = _yaml(RC2 / "layout-platzhalter-fiktiv.yaml")["layout"]
    d = Path(shutil.copy(RC2 / datei, konfig.eingang / datei))
    lauf = pipeline.verarbeiten([d], konfig)
    assert [(e.nummer, e.status) for e in lauf.ergebnisse] == [("RE-2026-9101", "ok"), ("RE-2026-9102", "ok")], \
        [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    with pdfplumber.open(konfig.ausgang / "RE-2026-9101_zugferd.pdf") as pdf:
        t1 = pdf.pages[0].extract_text()
    with pdfplumber.open(konfig.ausgang / "RE-2026-9102_zugferd.pdf") as pdf:
        t2 = pdf.pages[0].extract_text()
    assert "Bestellung PO-77801 · Bauleiter Hans Beispiel" in t1
    assert "Bestellung · Bauleiter" in t2  # fehlende Werte bleiben leer
    assert "2,5 Std. 65,00 € 162,50 €" in t1 and "500 Stk. 0,12 € 60,00 €" in t1


def test_altes_layout_wird_abgelehnt():
    roh = _yaml(RC2 / "layout-alt-format1-fiktiv.yaml")["layout"]
    with pytest.raises(layout.LayoutAlt):
        layout.laden(roh, ROOT / "beispiele")


def test_layout_beispiel_entspricht_dem_generator():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import layout_beispiel
    finally:
        sys.path.remove(str(ROOT / "tools"))
    d = _yaml(ROOT / "beispiele" / "layout" / "layout-beispiel.yaml")["layout"]
    assert d == layout_beispiel.vorlage()
    assert d["version"] == layout.VERSION == 2
