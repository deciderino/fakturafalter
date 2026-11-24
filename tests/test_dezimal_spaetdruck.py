# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.5.0: „anderes“ Dezimaltrennzeichen -> prüfen; Druck nach seiner CSV -> „schon erzeugt“ statt Fehler."""
import shutil

import pytest

from fakturafalter import adapter_csv
from fakturafalter.pipeline import verarbeiten


@pytest.mark.parametrize("roh, dez, tau, zweifel", [
    ("2.5", ",", ".", True), ("1.234,50", ",", ".", False), ("1.234", ",", ".", False), ("12.34,5", ",", ".", True),
    ("2,5", ".", "", True), ("2,5", ".", ",", True), ("1,234.50", ".", ",", False), ("2,5", ",", ".", False),
    ("25", ",", ".", False)])
def test_trennzeichen_zweifel(roh, dez, tau, zweifel):
    assert adapter_csv._trennzeichen_zweifel(roh, dez, tau) is zweifel


def test_punkt_im_kommaprofil_wird_pruefen_nicht_still_umgerechnet(konfig, eingang):
    (csv,) = eingang("variante-b_wawi_cp1252.csv")
    t = csv.read_bytes().decode("cp1252")
    alt = "P;RE-2026-0102;;;;;1;C-300;\"Kabel NYM 3x1,5 mm²\";50;"
    assert alt in t
    csv.write_bytes(t.replace(alt, alt.replace(";50;", ";2.5;")).encode("cp1252"))
    lauf = verarbeiten([csv], konfig)
    erg = {e.nummer: e for e in lauf.ergebnisse}
    assert erg["RE-2026-0102"].status == "pruefen"
    assert any("2.5" in h and "Dezimalzeichen" in h for h in erg["RE-2026-0102"].hinweise)
    assert erg["RE-2026-0101"].status == "ok"


def test_komma_im_punktprofil_wird_pruefen(konfig, eingang):
    (csv,) = eingang("variante-a_positionen_utf8.csv")
    t = csv.read_text(encoding="utf-8")
    csv.write_text(t.replace("Montagearbeit vor Ort\",3.5,", "Montagearbeit vor Ort\",\"3,5\","), encoding="utf-8")
    erg = {e.nummer: e for e in verarbeiten([csv], konfig).ergebnisse}
    assert erg["RE-2026-0101"].status == "pruefen"
    assert not any(h.startswith("FEHLER") for h in erg["RE-2026-0101"].hinweise)


def test_druck_nach_csv_landet_nicht_im_fehlerordner(konfig, eingang, tmp_path):
    konfig.pdf_vorlagen = []                       # Druck ohne Hand-Vorlage (Paarung über die Nummer)
    konfig.modus = "pdf_csv"
    lauf = verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert {e.nummer for e in lauf.ergebnisse if e.status == "ok"} >= {"RE-2026-0102"}
    spaet = konfig.eingang / "spaeter-druck.pdf"   # fiktiver Druck einer schon erzeugten Rechnung
    shutil.copy(konfig.ausgang / "RE-2026-0102_zugferd.pdf", spaet)
    lauf = verarbeiten([spaet], konfig)
    assert not lauf.datei_fehler and not lauf.ergebnisse
    assert lauf.schon_erzeugt == {str(spaet): "RE-2026-0102"}
    assert (konfig.erledigt / "spaeter-druck.pdf").exists()
    assert not (konfig.fehler / "spaeter-druck.pdf").exists()
    prot = (konfig.protokoll / "protokoll.tsv").read_text(encoding="utf-8")
    assert "\terledigt\tRE-2026-0102\tspaeter-druck.pdf\tschon erzeugt" in prot
