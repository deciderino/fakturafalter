# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.5.0: PDF + CSV/XML – verarbeitet wird erst, wenn beide Dateien mit gleichem Namen im Eingang liegen."""
from pathlib import Path

from fakturafalter import ueberwachung
from fakturafalter.ueberwachung import Waechter, nach_gegenstueck

P = Path("/eingang")


def test_paar_bereit_einzelne_warten(konfig):
    konfig.modus = "pdf_csv"
    d = [P / "R-123.pdf", P / "R-123.CSV", P / "R-124.pdf", P / "R-125.xml", P / "notiz.doc"]
    bereit, wartend = nach_gegenstueck(d, konfig, {p: 100.0 for p in d}, 100.0 + 60)
    assert bereit == [P / "R-123.pdf", P / "R-123.CSV", P / "notiz.doc"]
    assert wartend == [P / "R-124.pdf", P / "R-125.xml"]
    # nach der Wartezeit allein in den Lauf (dort Paarung über die Rechnungsnummer)
    bereit, wartend = nach_gegenstueck(d, konfig, {p: 100.0 for p in d}, 100.0 + konfig.gegenstueck_minuten * 60)
    assert bereit == d and wartend == []


def test_nur_pdf_und_abgeschaltet_wie_bisher(konfig):
    d = [P / "R-124.pdf"]
    konfig.modus = "nur_pdf"
    assert nach_gegenstueck(d, konfig, {}, 0.0) == (d, [])
    konfig.modus, konfig.gegenstueck_minuten = "pdf_xml", 0
    assert nach_gegenstueck(d, konfig, {}, 0.0) == (d, [])


def test_waechter_wartet_ohne_fehler(konfig, monkeypatch):
    konfig.modus, konfig.stabil_sekunden = "pdf_csv", 0
    for n in ("R-1.pdf", "R-1.csv", "R-2.pdf"):
        (konfig.eingang / n).write_bytes(b"x")
    gesehen = []
    monkeypatch.setattr(ueberwachung, "verarbeiten", lambda dateien, k: gesehen.append(sorted(p.name for p in dateien)))
    w = Waechter(konfig)
    w.einmal()                                   # erster Blick: Größe merken
    w.einmal()
    assert gesehen == [["R-1.csv", "R-1.pdf"]]
    assert [p.name for p in w.wartend] == ["R-2.pdf"]
    assert not konfig.fehler.exists()
