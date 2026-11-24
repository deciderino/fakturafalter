# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.9.2: Eingangsformat CSV/XML mit optionalem PDF-Haken (fiktive Daten)."""
from pathlib import Path

import pikepdf

from fakturafalter.pipeline import verarbeiten
from fakturafalter.ueberwachung import nach_gegenstueck


def test_ohne_haken_kein_warten(konfig):
    konfig.modus, konfig.pdf_verwenden, konfig.gegenstueck_minuten = "csv", False, 10
    d = [Path("/eingang/R-124.pdf"), Path("/eingang/R-124.csv")]
    assert nach_gegenstueck(d, konfig, {}, 0.0) == (d, [])


def test_mit_haken_wartet_wie_bisher(konfig):
    konfig.modus, konfig.pdf_verwenden, konfig.gegenstueck_minuten = "csv", True, 10
    d = [Path("/eingang/R-124.pdf"), Path("/eingang/R-125.csv")]
    bereit, wartend = nach_gegenstueck(d, konfig, {p: 100.0 for p in d}, 160.0)
    assert wartend == d and bereit == []


def test_csv_ohne_haken_baut_sichtseite_und_legt_begleit_pdf_ab(konfig, eingang):
    konfig.modus, konfig.pdf_verwenden = "csv", False
    (csv,) = eingang("variante-a_positionen_utf8.csv")
    pdf = konfig.eingang / "variante-a_positionen_utf8.pdf"
    quelle = Path(__file__).parent.parent / "beispiele" / "druckauftrag-wawi.pdf"
    pdf.write_bytes(quelle.read_bytes())
    lauf = verarbeiten([csv, pdf], konfig)
    assert lauf.ok, [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    assert not lauf.datei_fehler
    erg = {e.nummer: e for e in lauf.ergebnisse}
    assert "RE-2026-0101" in erg
    # Sichtteil neu (1 Seite), nicht der mehrseitige Begleit-Druck
    zugferd = konfig.ausgang / "RE-2026-0101_zugferd.pdf"
    assert zugferd.exists()
    assert len(pikepdf.open(zugferd).pages) == 1
    # gleiches Namensstamm-PDF wandert mit nach Erledigt, nicht in Anlernen/Fehler
    assert (konfig.erledigt / "variante-a_positionen_utf8.pdf").exists()
    assert (konfig.erledigt / "variante-a_positionen_utf8.csv").exists()
    assert not konfig.anlernen.exists() or not any(konfig.anlernen.iterdir())


def test_csv_ohne_haken_fremdes_pdf_wird_nicht_als_rechnung_gelesen(konfig, eingang):
    konfig.modus, konfig.pdf_verwenden = "csv", False
    (csv,) = eingang("variante-a_positionen_utf8.csv")
    fremd = konfig.eingang / "allein.pdf"
    quelle = Path(__file__).parent.parent / "beispiele" / "druckauftrag-wawi.pdf"
    fremd.write_bytes(quelle.read_bytes())
    lauf = verarbeiten([csv, fremd], konfig)
    assert all(e.status == "ok" for e in lauf.ergebnisse)
    assert any(Path(d).name == "allein.pdf" for d in lauf.datei_fehler)
    assert "nicht verwendet" in " ".join(lauf.datei_fehler.values())
    assert (konfig.fehler / "allein.pdf").exists()
    assert (konfig.ausgang / "RE-2026-0101_zugferd.pdf").exists()
    # keine zweite Rechnung aus dem Druck
    assert {e.nummer for e in lauf.ergebnisse} == {"RE-2026-0101", "RE-2026-0102", "RE-2026-0103"}


def test_csv_mit_haken_nutzt_pdf_als_sichtteil(konfig, eingang):
    konfig.modus, konfig.pdf_verwenden = "csv", True
    dateien = eingang("druckauftrag-wawi.pdf", "variante-b_wawi_cp1252.csv")
    lauf = verarbeiten(dateien, konfig)
    assert lauf.ok, [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    # 0101 hat im Druck 2 Seiten – Sichtteil vom Original
    assert len(pikepdf.open(konfig.ausgang / "RE-2026-0101_zugferd.pdf").pages) == 2
