# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Sichtteil: lange Namen bleiben in ihrer Spalte, Einheiten als Klartext, Preiseinheit sichtbar (fiktive Daten)."""

import io
from datetime import date
from decimal import Decimal

import pdfplumber
import pytest
from reportlab.lib.units import mm

from fakturafalter import sicht
from fakturafalter.modell import Anschrift, Partei, Position, Rechnung, Summen, Zahlung

LANG = "Beispiel Planungs- und Ingenieurgesellschaft für Sondermaschinen- und Anlagenbau Nord mbH & Co. KG"


def _rechnung(**pos) -> Rechnung:
    p = Position(
        nr="1",
        bezeichnung="Sechskantschraube " + "M8x40 verzinkt DIN 933 " * 6,
        menge=Decimal("10"),
        einheit="H87",
        einzelpreis=Decimal("3.40"),
        preiseinheit=Decimal("10"),
        netto=Decimal("3.40"),
    )
    for k, v in pos.items():
        setattr(p, k, v)
    return Rechnung(
        nummer="RE-2026-0001",
        datum=date(2026, 10, 5),
        leistungsdatum=date(2026, 10, 5),
        kundennummer="K-4711",
        bestellnummer="PO-" + "1234567890" * 4,
        verkaeufer=Partei(name=LANG, anschrift=Anschrift("Musterweg 12", "12345", "Musterstadt")),
        kaeufer=Partei(
            name=LANG,
            anschrift=Anschrift(
                "Beispielallee 1234",
                "54321",
                "Beispielstadt",
                zusatz="z. Hd. Frau Erika Beispiel, Abteilung Einkauf",
            ),
        ),
        positionen=[p],
        summen=Summen(netto=Decimal("3.40"), brutto=Decimal("4.05")),
        zahlung=Zahlung(iban="DE02120300000000202051"),
    )


def _woerter(pdf: bytes):
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return d.pages[0].extract_words(), d.pages[0].height


def test_lange_namen_laufen_nicht_in_den_infoblock():
    ws, h = _woerter(sicht.erzeugen(_rechnung(), sprache="de"))
    info_x = 125 * mm
    info = [w for w in ws if w["x0"] >= info_x - 1 and 35 * mm < w["top"] < 85 * mm]
    oben, unten = min(w["top"] for w in info), max(w["bottom"] for w in info)
    links = [w for w in ws if w["x0"] < info_x - 1 and w["bottom"] > oben and w["top"] < unten]
    assert links and all(w["x1"] <= info_x for w in links), [
        w["text"] for w in links if w["x1"] > info_x
    ]
    text = " ".join(w["text"] for w in ws)
    assert "Nord" in text and "Einkauf" in text  # umbrochen, nicht abgeschnitten
    assert all(w["x1"] <= 210 * mm - 20 * mm + 1 for w in ws)  # nichts über den rechten Rand


def test_bezeichnung_umbrochen_und_spalten_frei():
    ws, _ = _woerter(sicht.erzeugen(_rechnung(), sprache="de"))
    bez = [w for w in ws if w["text"] in ("verzinkt", "DIN", "933")]
    assert len({round(w["top"]) for w in bez}) >= 2  # mehrere Zeilen
    assert all(w["x1"] <= 20 * mm + 30 * mm + 56 * mm + 1 for w in bez)


@pytest.mark.parametrize(
    "sprache, einheit, preis",
    [("de", "Stk.", "3,40 € / 10 Stück"), ("en", "pc.", "3,40 € / 10 pcs.")],
)
def test_einheit_klartext_und_preiseinheit(sprache, einheit, preis):
    ws, _ = _woerter(sicht.erzeugen(_rechnung(), sprache=sprache))
    text = " ".join(w["text"] for w in ws)
    assert f" {einheit} " in f" {text} " and "H87" not in text
    assert preis in text


def test_einheit_text():
    assert (
        sicht.einheit_text("H87", "de") == "Stk."
        and sicht.einheit_text("C62", "de", lang=True) == "Stück"
    )
    assert sicht.einheit_text("HUR", "de") == "Std." and sicht.einheit_text("HUR", "en") == "hr"
    assert sicht.einheit_text("XYZ", "de") == "XYZ"  # unbekannt: Code
    assert sicht.preis_text(Decimal("3.4"), Decimal("1"), "H87", "de") == "3,40"


def test_sicht_xml_behaelt_code():
    r = _rechnung(einheit="HUR")
    ws, _ = _woerter(sicht.erzeugen(r, sprache="de"))
    assert "Std." in " ".join(w["text"] for w in ws) and r.positionen[0].einheit == "HUR"


def test_lange_bestellnummer_umbrochen_statt_gekuerzt():
    """TODO 0.4.x: Die Bestellnummer stand mit „…“ gekürzt im Sichtteil (im XML vollständig)."""
    r = _rechnung()
    ws, _ = _woerter(sicht.erzeugen(r, sprache="de"))
    info = [w for w in ws if w["x0"] >= 155 * mm - 1 and 35 * mm < w["top"] < 95 * mm]
    text = "".join(w["text"] for w in info)
    assert r.bestellnummer in text and "…" not in text
    assert all(w["x1"] <= 210 * mm - 20 * mm + 1 for w in info)
    zeilen = sorted({round(w["top"]) for w in info})
    assert len(zeilen) == len(set(zeilen))  # keine Überlappung


def test_kurze_werte_unveraendert_einzeilig():
    r = _rechnung()
    r.bestellnummer = "PO-4711"
    ws, _ = _woerter(sicht.erzeugen(r, sprache="de"))
    po = [w for w in ws if w["text"] == "PO-4711"]
    assert len(po) == 1


def test_kontakt_und_adresszeile3_im_sichtteil():
    """Kontaktstelle (BT-56) und Adresszeile 3 (BT-163) stehen im Sichtteil neben Name und Zusatz."""
    r = _rechnung()
    r.kaeufer.kontakt_name = "Frau Muster"
    r.kaeufer.anschrift.zusatz = "Abteilung Einkauf"
    r.kaeufer.anschrift.zeile3 = "Gebäude C"
    text = " ".join(w["text"] for w in _woerter(sicht.erzeugen(r, sprache="de"))[0])
    assert "Frau Muster" in text
    assert "Abteilung Einkauf" in text
    assert "Gebäude C" in text
