# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Einstellung „Logs anonymisieren“ (nur fiktive Werte)."""

import logging

import pytest

from fakturafalter import anlernen, logdatei, pipeline


@pytest.fixture(autouse=True)
def logging_an():
    """Logging für jeden Test hier einschalten und den vorherigen Zustand wiederherstellen.

    Andere Tests (z. B. tools/kopffeld_messung.messen über test_kopffeld) rufen
    ``logging.disable(logging.CRITICAL)`` auf und setzen es nicht zurück. Ohne diese Fixture
    hinge das Ergebnis von der Testreihenfolge ab.
    """
    vorher = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    yield
    logging.disable(vorher)


@pytest.fixture
def anonym():
    logdatei.anonym_setzen(True)
    yield logdatei.ANONYM
    logdatei.anonym_setzen(False)


@pytest.mark.parametrize(
    "roh, weg, ersatz",
    [
        ("Kunde: Probe Kleinbetrieb e.K.", "Probe", "[Name]"),
        ("an Beispiel Anlagenbau GmbH & Co. KG", "Anlagenbau", "[Name]"),
        ("IBAN DE36 0000 0000 0000 0000 00", "0000", "[IBAN]"),
        ("IBAN DE02120300000000202051", "DE0212", "[IBAN]"),
        ("USt-IdNr. DE123456788", "DE123456788", "[USt-IdNr.]"),
        ("Musterstraße 1, 12345 Musterstadt", "Muster", "[Straße]"),
        ("12347 Musterstadt", "12347", "[PLZ Ort]"),
        ("Brutto 1.234,50 € (Netto 120.00)", "1.234", "[Betrag]"),
        ("Kontakt buchhaltung@muster-gmbh.example", "@", "[E-Mail]"),
    ],
)
def test_maskiert(roh, weg, ersatz):
    aus = logdatei.anonymisieren(roh)
    assert weg not in aus and ersatz in aus, aus


def test_technik_bleibt():
    t = "RE-2026-0101 am 05.10.2026 um 08:43, Version 0.7.0, Seite 1 von 2, 42 %"
    assert logdatei.anonymisieren(t) == t


def test_diagnoseformat_a_A_9_unveraendert():
    zeilen = [
        "Probe Kleinbetrieb e.K. 12347 Musterstadt",
        "Wartungspauschale 1 psch. 120,00 120,00 A",
        "IBAN DE36 0000 0000 0000 0000 00",
    ]
    diagnose = "\n".join(" ".join(anlernen.maskieren(w) for w in z.split()) for z in zeilen)
    assert logdatei.anonymisieren(diagnose) == diagnose


def test_filter_wirkt_auf_logdatei(tmp_path, anonym):
    pfad = logdatei.einrichten(tmp_path / "logs")
    try:
        anonym.merken("Erika Beispiel")
        log = logging.getLogger("fakturafalter.test")
        log.info(
            "Kontakt %s, IBAN %s, Betrag %s", "Erika Beispiel", "DE02120300000000202051", "4,05 €"
        )
        try:
            raise ValueError("Musterweg 12 fehlt")
        except ValueError:
            log.exception("Fehler bei Kunde: Beispiel Planungs-GmbH")
        logdatei._handler.flush()
        text = pfad.read_text(encoding="utf-8")
    finally:
        logdatei.beenden()
    for weg in ("Erika", "DE0212", "4,05", "Musterweg", "Planungs"):
        assert weg not in text, weg
    assert "[Name]" in text and "[IBAN]" in text and "[Betrag]" in text


def test_aus_laesst_alles_durch():
    logdatei.anonym_setzen(False)
    r = logging.LogRecord(
        "fakturafalter", logging.INFO, "", 0, "IBAN %s", ("DE02120300000000202051",), None
    )
    assert logdatei.ANONYM.filter(r) and r.getMessage() == "IBAN DE02120300000000202051"


def test_pipeline_merkt_kaeufer(konfig, eingang, anonym):
    pipeline.verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert anonym.namen  # Käufer aus dem Lauf


def test_konfig_option_standard_aus(konfig):
    assert konfig.logs_anonym is False
