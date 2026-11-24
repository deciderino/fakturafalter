# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Fortschritt der Verarbeitung: Rückruf aus der Pipeline (fiktive Beispieldaten)."""

from fakturafalter import pipeline


def _staende(dateien, konfig):
    staende = []
    lauf = pipeline.verarbeiten(dateien, konfig, fortschritt=staende.append)
    return lauf, staende


def test_schritte_und_anteil_steigen(konfig, eingang):
    lauf, st = _staende(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert lauf.ergebnisse and st
    anteile = [s.anteil for s in st]
    assert anteile == sorted(anteile)  # ruhig: nie zurück
    assert anteile[-1] == 1.0 and anteile[0] == 0.0
    assert {s.schritt for s in st} >= {0, 1, 2, 3, 5}
    assert all(s.eingabe == "csv" for s in st)
    assert all(0 <= s.nr <= s.gesamt for s in st)


def test_pdf_und_csv(konfig, eingang):
    _lauf, st = _staende(eingang("druckauftrag-wawi.pdf", "variante-a_positionen_utf8.csv"), konfig)
    assert any(s.eingabe == "pdf_csv" for s in st if s.schritt >= 2)
    xml = [s for s in st if s.schritt == 2]
    assert xml and xml[0].gesamt >= 2 and xml[0].datei.endswith(".pdf")


def test_nur_pdf(konfig, eingang):
    _lauf, st = _staende(eingang("druckauftrag-wawi.pdf"), konfig)
    assert {s.eingabe for s in st} == {"pdf"}


def test_fehler_laeuft_weiter(konfig, eingang):
    lauf, st = _staende(
        eingang("textdruck-wawi_cp1252.txt", "variante-a_positionen_utf8.csv"), konfig
    )
    assert any(s.fehler == "textdruck-wawi_cp1252.txt" for s in st)
    assert st[-1].anteil == 1.0 and lauf.ergebnisse


def test_rueckruf_fehler_stoert_nicht(konfig, eingang):
    def kaputt(_s):
        raise RuntimeError("Anzeige weg")

    lauf = pipeline.verarbeiten(
        eingang("variante-a_positionen_utf8.csv"), konfig, fortschritt=kaputt
    )
    assert lauf.ergebnisse


def test_eingabe_art():
    e = pipeline.eingabe_art
    assert (
        e(["a.pdf"]) == "pdf"
        and e(["a.csv", "a.pdf"]) == "pdf_csv"
        and e(["a.xml", "a.pdf"]) == "pdf_xml"
    )
    assert e(["a.csv"]) == "csv" and e(["a.xml"]) == "xml" and e(["a.txt"]) == "csv"
