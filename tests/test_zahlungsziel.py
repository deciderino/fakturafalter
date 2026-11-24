# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Zahlungsbedingung aus dem Druck (BT-20): Netto-Fälligkeit, Zahlungsziel, Skonto – und der sichtbare Teil
(fiktive Daten)."""

import io
from datetime import date
from decimal import Decimal

import pdfplumber
import pytest

from fakturafalter import sicht, zahlungsziel
from fakturafalter.aufbau import rechnung_bauen
from fakturafalter.modell import Anschrift, Herkunft, Partei, Position, Rechnung, Summen, Zahlung

H = Herkunft("test", 1.0)


@pytest.mark.parametrize(
    "text, faellig, skonto",
    [
        (
            "zahlbar bis 08.11.26 bei 3 % Skonto (1,17 EUR)\nbis 28.11.2026 ohne Abzug",
            date(2026, 11, 28),
            [(Decimal("3"), date(2026, 11, 8), Decimal("1.17"))],
        ),
        (
            "zahlbar bis 8.11.2026 bei 2,5% Skonto bis 28.11.26 ohne Abzug",
            date(2026, 11, 28),
            [(Decimal("2.5"), date(2026, 11, 8), None)],
        ),
        ("zahlbar bis 28.11.2026 ohne Abzug.", date(2026, 11, 28), []),
        ("Zahlbar bis 04.11.26 netto", date(2026, 11, 4), []),
        # ohne „netto“: „bis <Datum>“ in einem Satzteil ohne Skonto ist die Fälligkeit
        (
            "Bitte überweisen bis 18.11.2026. Bei Zahlung bis 29.10.2026 2 % Skonto.",
            date(2026, 11, 18),
            [(Decimal("2"), date(2026, 10, 29), None)],
        ),
        (
            "Zahlbar innerhalb 30 Tagen netto bis 06.11.2026, 3% Skonto innerhalb 10 Tagen bis 17.10.2026",
            date(2026, 11, 6),
            [],
        ),
    ],
)
def test_lesen(text, faellig, skonto):
    z = zahlungsziel.lesen(text)
    assert z.text == " ".join(text.split())
    assert z.faellig == faellig and z.tage is None
    assert [(s.satz, s.bis, s.betrag) for s in z.skonto] == skonto


@pytest.mark.parametrize(
    "text, tage",
    [
        ("14 Tage 2 % Skonto, 30 Tage netto", 30),
        ("30 Tage netto, 14 Tage 2 % Skonto", 30),
        ("Zahlbar innerhalb von 14 Tagen ohne Abzug.", 14),
        ("10 Tage 3 % Skonto, 60 Tage", 60),
        ("sofort", None),
    ],
)
def test_netto_tage(text, tage):
    assert zahlungsziel.netto_tage(text) == tage
    assert zahlungsziel.lesen(text).tage == tage


@pytest.mark.parametrize(
    "betrag, ok", [("1,17", True), ("37,98", True), ("1,18", True), ("1,20", False)]
)
def test_skonto_betrag_pruefen(betrag, ok):
    z = zahlungsziel.lesen(
        f"zahlbar bis 08.11.26 bei 3 % Skonto ({betrag} €) bis 28.11.2026 ohne Abzug"
    )
    h = zahlungsziel.skonto_hinweise(z, Decimal("39.15"))  # 3 % = 1,17; Zahlbetrag 37,98
    assert (h == []) is ok


def test_datum_im_text():
    assert zahlungsziel.datum_im_text(date(2026, 11, 28), "bis 28.11.26 ohne Abzug")
    assert not zahlungsziel.datum_im_text(date(2026, 11, 28), "bis 08.11.26 ohne Abzug")


def _kopf(**extra):
    return {
        "BT-1": ("X-1", H),
        "BT-2": (date(2026, 10, 28), H),
        "kundennummer": ("K-1001", H),
        **extra,
    }


def test_druck_bt20_ersetzt_profil_ziel(konfig):
    """BT-20 aus dem Druck: BT-9 nur aus dem Text, nie aus dem Zahlungsziel des Profils."""
    r = rechnung_bauen(
        _kopf(**{"BT-20": ("zahlbar bis 08.11.26 bei 3 % Skonto", H)}), [], {}, konfig, "t.pdf"
    )
    assert (
        r.zahlung.bedingungen == "zahlbar bis 08.11.26 bei 3 % Skonto" and r.zahlung.faellig is None
    )
    r = rechnung_bauen(
        _kopf(**{"BT-20": ("14 Tage 2 % Skonto, 30 Tage netto", H)}), [], {}, konfig, "t.pdf"
    )
    assert r.zahlung.faellig == date(2026, 11, 27)
    r = rechnung_bauen(
        _kopf(**{"BT-20": ("", H)}), [], {}, konfig, "t.pdf"
    )  # angelernt, nicht gelesen
    assert r.zahlung.bedingungen == "" and r.zahlung.faellig is None
    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")  # ohne BT-20: Profil wie bisher
    assert r.zahlung.bedingungen and r.herkunft["BT-20"].quelle == "profil"


def test_profiltext_bei_skonto_gesperrt(konfig):
    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")
    # ohne Skonto nicht gesperrt: die gedruckte Fälligkeit gilt statt der 14 Tage des Profils
    zahlungsziel.profiltext_sperren(r, "Endbetrag 39,15 zahlbar bis 28.11.2026")
    assert r.zahlung.faellig == date(2026, 11, 28)
    assert not any(h.feld == "BT-20" for h in r.hinweise)
    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")
    assert zahlungsziel.profiltext_sperren(r, "zahlbar bis 08.11.26 bei 3 % Skonto")
    assert r.zahlung.bedingungen == "" and r.zahlung.faellig is None
    assert any(h.stufe == "pruefen" and h.feld == "BT-20" for h in r.hinweise)
    r = rechnung_bauen(_kopf(**{"BT-20": ("2 % Skonto bis 08.11.26", H)}), [], {}, konfig, "t.pdf")
    assert not zahlungsziel.profiltext_sperren(r, "2 % Skonto")  # Text aus dem Druck bleibt


def _rechnung(**z) -> Rechnung:
    p = Position(
        nr="1",
        bezeichnung="Prüfung",
        menge=Decimal("1"),
        einheit="H87",
        einzelpreis=Decimal("10"),
        netto=Decimal("10"),
    )
    return Rechnung(
        nummer="RE-1",
        datum=date(2026, 10, 28),
        verkaeufer=Partei(
            name="Beispiel GmbH", anschrift=Anschrift("Musterweg 1", "12345", "Musterstadt")
        ),
        kaeufer=Partei(
            name="Muster AG", anschrift=Anschrift("Beispielweg 2", "54321", "Beispielstadt")
        ),
        positionen=[p],
        summen=Summen(netto=Decimal("10"), brutto=Decimal("11.90")),
        zahlung=Zahlung(**z),
    )


def _text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return d.pages[0].extract_text()


def test_sicht_fuss_ohne_leere_angaben():
    t = _text(sicht.erzeugen(_rechnung(bedingungen="Zahlbar sofort."), sprache="de"))
    assert "Kontakt" not in t and "IBAN" not in t and "· ·" not in t


def test_sicht_faellig_nur_wenn_nicht_im_text():
    t = _text(
        sicht.erzeugen(
            _rechnung(bedingungen="zahlbar bis 28.11.26 ohne Abzug", faellig=date(2026, 11, 28)),
            sprache="de",
        )
    )
    assert "Fällig am" not in t and "zahlbar bis 28.11.26 ohne Abzug" in t
    t = _text(
        sicht.erzeugen(
            _rechnung(
                bedingungen="Zahlbar innerhalb von 30 Tagen ohne Abzug.", faellig=date(2026, 11, 27)
            ),
            sprache="de",
        )
    )
    assert "Fällig am 27.11.2026" in t


def test_profilziel_nicht_14_wenn_druck_anders(konfig):
    """Profil-Standard (14 Tage) nicht still übernehmen, wenn der Druck ein anderes Ziel nennt."""
    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")
    assert r.herkunft["BT-20"].quelle == "profil" and r.zahlung.ziel_tage == 14
    assert r.zahlung.faellig == date(2026, 11, 11)  # 28.10. + 14
    assert zahlungsziel.profiltext_sperren(r, "Zahlungsbedingungen: 30 Tage netto")
    assert r.zahlung.ziel_tage == 30
    assert r.zahlung.faellig == date(2026, 11, 27)
    assert "30" in (r.zahlung.bedingungen or "")

    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")
    assert zahlungsziel.profiltext_sperren(r, "Fälligkeitsdatum 18.11.2026")
    assert r.zahlung.faellig == date(2026, 11, 18)
    assert r.zahlung.bedingungen != "Zahlbar innerhalb von 14 Tagen ohne Abzug."

    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")
    assert zahlungsziel.profiltext_sperren(r, "Zahlbar nach Vereinbarung")
    assert r.zahlung.faellig is None and r.zahlung.bedingungen == ""
    assert any(h.stufe == "pruefen" and h.feld == "BT-20" for h in r.hinweise)

    r = rechnung_bauen(_kopf(), [], {}, konfig, "t.csv")
    assert not zahlungsziel.profiltext_sperren(r, "Endbetrag 39,15 EUR Lieferdatum 15.11.2026")
    assert r.zahlung.ziel_tage == 14 and r.zahlung.faellig == date(2026, 11, 11)
