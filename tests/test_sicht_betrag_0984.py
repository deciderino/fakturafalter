# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Sichtteil: Währungszeichen an jedem Geldbetrag (fiktive Daten, ab 0.9.8.4)."""

import io
import subprocess
import tempfile
from datetime import date
from decimal import Decimal

import pdfplumber
import yaml
from reportlab.lib.units import mm

from fakturafalter import adapter_csv, layout, rechnen, sicht
from fakturafalter.modell import Anschrift, Partei, Position, Rechnung, Steuer, Summen, Zahlung

from .conftest import BEISPIELE

D = Decimal
CSV = BEISPIELE / "variante-zjp_textzeilen.csv"
PROFIL = BEISPIELE / "profil-variante-zjp-textzeilen.yaml"


def test_betrag_eur_und_usd():
    assert sicht.betrag(D("1234.56"), "EUR") == "1.234,56 €"
    assert sicht.betrag(D("1234.56"), "eur") == "1.234,56 €"
    assert sicht.betrag(D("1234.56"), "USD") == "1.234,56 USD"
    assert sicht.betrag(None, "EUR") == ""
    assert sicht.eur(D("1234.56")) == "1.234,56"  # unverändert ohne Zeichen


def test_preis_text_ohne_doppeltes_zeichen():
    assert sicht.preis_text(D("3.40"), D("1"), "H87", "de", "EUR") == "3,40 €"
    assert sicht.preis_text(D("3.40"), D("10"), "H87", "de", "EUR") == "3,40 € / 10 Stück"
    assert sicht.preis_text(D("3.40"), D("1"), "H87", "de", "USD") == "3,40 USD"
    assert sicht.preis_text(D("3.40"), D("10"), "H87", "de", "USD") == "3,40 USD / 10 Stück"


def test_summen_zeilen_zeichen_ohne_iso_im_label():
    r = Rechnung(
        waehrung="EUR",
        summen=Summen(
            netto=D("100.00"),
            ust=D("19.00"),
            brutto=D("119.00"),
            zahlbar=D("89.00"),
            vorausbezahlt=D("30.00"),
        ),
    )
    r.summen.steuerzeilen = []  # keine USt-Zeilen, nur Netto/Gesamt/Zahlbetrag
    # ohne Steuerzeilen bleibt Netto + Gesamt + Voraus + Zahlbetrag
    z = sicht.summen_zeilen(r)
    texte = " | ".join(f"{a}={b}" for a, b in z)
    assert "Gesamtbetrag=119,00 €" in texte
    assert "Zahlbetrag=89,00 €" in texte
    assert "Nettobetrag=100,00 €" in texte
    assert "Bereits gezahlt=−30,00 €" in texte
    assert "Gesamtbetrag EUR" not in texte and "Zahlbetrag EUR" not in texte

    r.waehrung = "USD"
    r.summen.vorausbezahlt = D("0")
    r.summen.zahlbar = D("119.00")
    texte = " | ".join(f"{a}={b}" for a, b in sicht.summen_zeilen(r))
    assert "Gesamtbetrag=119,00 USD" in texte
    assert "Gesamtbetrag USD" not in texte


def _pdf_text(pdf: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf)
        f.flush()
        r = subprocess.run(
            ["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, check=True
        )
        return r.stdout


def _gross() -> Rechnung:
    r = Rechnung(
        nummer="RE-2026-9100",
        datum=date(2026, 11, 26),
        waehrung="EUR",
        verkaeufer=Partei(
            name="Beispielverkauf GmbH", anschrift=Anschrift("Musterweg 1", "12345", "Musterstadt")
        ),
        kaeufer=Partei(
            name="Beispielbau GmbH",
            anschrift=Anschrift("Beispielallee 2", "54321", "Beispielstadt"),
        ),
        positionen=[
            Position(
                nr="1",
                bezeichnung="Beispielmaschine",
                menge=D("1"),
                einheit="H87",
                einzelpreis=D("123456.78"),
                preiseinheit=D("1"),
                netto=D("123456.78"),
                steuer=Steuer(satz=D("19")),
            )
        ],
        summen=Summen(
            netto=D("123456.78"),
            ust=D("23456.79"),
            brutto=D("146913.57"),
            zahlbar=D("146913.57"),
        ),
        zahlung=Zahlung(iban="DE02120300000000202051"),
    )
    rechnen.berechnen(r)
    return r


def test_sichtseite_csv_pdftotext_zeigt_zeichen(konfig):
    profil = yaml.safe_load(PROFIL.read_text(encoding="utf-8"))
    (r,) = adapter_csv.lesen(CSV, profil, konfig)
    rechnen.berechnen(r)
    text = _pdf_text(sicht.erzeugen(r))
    assert "9,86 €" in text
    assert "394,40 €" in text
    assert "74,94 €" in text
    assert "469,34 €" in text
    assert "Gesamtbetrag" in text and "Gesamtbetrag EUR" not in text
    assert r.waehrung == "EUR"


def test_grosse_betraege_eine_zeile_ohne_ueberlauf():
    r = _gross()
    for vorlage in (None, layout.standard()):
        pdf = sicht.erzeugen(r, sprache="de", vorlage=vorlage)
        text = _pdf_text(pdf)
        assert "123.456,78 €" in text
        assert "146.913,57 €" in text
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            ws = doc.pages[0].extract_words()
        # die Zahl bleibt ein Token (kein Umbruch mitten im Betrag)
        assert not any("123.456" in w["text"] and w["text"] not in ("123.456,78",) for w in ws)
        assert all(w["x1"] <= 210 * mm - 20 * mm + 1.5 for w in ws)
        zahlen = [w for w in ws if w["text"] == "123.456,78"]
        # Spalten: Einzelpreis rechts 160 mm, Gesamt rechts 180 mm (USt rechts 190 mm)
        einzel = next(w for w in zahlen if w["x1"] <= 160 * mm + 1.5 and w["x0"] >= 135 * mm)
        gesamt = next(w for w in zahlen if w["x0"] >= 160 * mm and w["x1"] <= 180 * mm + 1.5)
        assert abs(einzel["top"] - gesamt["top"]) < 3  # dieselbe Positionszeile
        assert einzel["x1"] <= gesamt["x0"] + 0.5
        euro = [w for w in ws if w["text"] == "€" and abs(w["top"] - einzel["top"]) < 3]
        assert any(abs(w["x1"] - 160 * mm) <= 1.5 for w in euro)
        assert any(abs(w["x1"] - 180 * mm) <= 1.5 for w in euro)


def test_usd_sichtseite_iso_am_betrag():
    r = _gross()
    r.waehrung = "USD"
    text = _pdf_text(sicht.erzeugen(r, sprache="de"))
    assert "123.456,78 USD" in text
    assert "146.913,57 USD" in text
    assert "€" not in text
    assert "Gesamtbetrag USD" not in text
