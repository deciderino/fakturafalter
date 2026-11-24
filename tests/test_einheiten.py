# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Einheiten aus 0.4.8: jeder Code steht in BR-CL-23, hat einen Anzeigenamen (Sichtteil DE/EN, GUI EN)
und wird vom KoSIT-Validator angenommen. Alle Daten erfunden."""

from datetime import date
from decimal import Decimal as D

import pytest

from fakturafalter import anlernen, codelisten, rechnen, sicht, validierung
from fakturafalter.cii import erzeugen as cii_erzeugen
from fakturafalter.gui import texte
from fakturafalter.modell import Anschrift, Partei, Position, Rechnung, Zahlung

NEU = (
    "WEE",
    "MON",
    "ANN",
    "MMT",
    "CMT",
    "MLT",
    "KWH",
    "DZN",
    "XPX",
    "XSA",
    "XBX",
    "XBO",
    "XPK",
    "XRO",
    "XCT",
    "XST",
)
BEDEUTUNG = {
    "DZN": ("Dutzend", "dozen"),
    "XPX": ("Palette", "pallet"),
    "XSA": ("Sack", "sack"),
    "XBO": ("Flasche", "bottle"),
    "XBX": ("Kiste", "box"),
    "XPK": ("Pack", "pack"),
    "XRO": ("Rolle", "roll"),
    "XCT": ("Karton", "carton"),
    "XST": ("Blatt", "sheet"),
}
braucht_werkzeuge = pytest.mark.skipif(
    not all(validierung.verfuegbar().values()), reason="Java/KoSIT/Mustang nicht vorhanden"
)


@pytest.mark.parametrize("code", NEU)
def test_neuer_code_in_codeliste_und_benannt(code):
    assert code in codelisten.EINHEITEN
    assert code in anlernen.EINHEIT_NAMEN.values() or code in anlernen.EINHEIT_NAMEN
    for sprache in ("de", "en"):
        assert code in sicht._EINHEIT[sprache], (code, sprache)
    name = anlernen.EINHEIT_NAMEN[code]
    assert texte.EN.get(name), name


@pytest.mark.parametrize("code", sorted(BEDEUTUNG))
def test_bedeutung_der_verpackungscodes(code):
    de, en = BEDEUTUNG[code]
    assert anlernen.EINHEIT_NAMEN[code].startswith(de)
    assert any(t.startswith(de) for t in sicht._EINHEIT["de"][code])
    assert any(t.startswith(en) for t in sicht._EINHEIT["en"][code])


def test_alle_namen_uebersetzt():
    fehlt = sorted(n for n in anlernen.EINHEIT_NAMEN.values() if not texte.EN.get(n))
    assert not fehlt, fehlt


def _rechnung() -> Rechnung:
    r = Rechnung(
        nummer="E-48",
        datum=date(2026, 10, 28),
        leistungsdatum=date(2026, 10, 23),
        leitweg_id="04011000-12345-34",
        verkaeufer=Partei(
            "Muster GmbH",
            Anschrift("Musterstraße 1", "12345", "Musterstadt"),
            ust_id="DE123456788",
            kontakt_email="info@muster.example",
            kontakt_name="Erika Muster",
            kontakt_telefon="+49 30 1234567",
            elektronische_adresse="rechnung@muster.example",
        ),
        kaeufer=Partei(
            "Beispiel AG",
            Anschrift("Beispielweg 2", "54321", "Beispielstadt"),
            elektronische_adresse="eingang@beispiel.example",
        ),
        zahlung=Zahlung(
            iban="DE36000000000000000000",
            bedingungen="Zahlbar innerhalb 14 Tagen ohne Abzug.",
            faellig=date(2026, 11, 11),
        ),
        positionen=[
            Position(
                str(i), bezeichnung=f"Posten {c}", menge=D("2"), einheit=c, einzelpreis=D("10")
            )
            for i, c in enumerate(NEU, 1)
        ],
    )
    rechnen.berechnen(r)
    return r


@braucht_werkzeuge
@pytest.mark.parametrize("profil", ["EN16931", "XRECHNUNG"])
def test_kosit_nimmt_neue_einheiten_an(tmp_path, profil):
    x = tmp_path / f"einheiten-{profil}.xml"
    x.write_bytes(cii_erzeugen(_rechnung(), profil))
    for c in NEU:
        assert f'unitCode="{c}"' in x.read_text(encoding="utf-8")
    (e,) = validierung.kosit([x])
    assert e.gueltig, e.fehler
    assert not [f for f in e.fehler + e.warnungen if "BR-CL-23" in f]


def test_verpackung_und_blatt_auf_gueltige_codes():
    got = {
        t: anlernen.einheit_code(t) for t in ("Pkt.", "Pak", "Rolle", "Karton", "Blatt", "Bogen")
    }
    assert got == {
        "Pkt.": "XPK",
        "Pak": "XPK",
        "Rolle": "XRO",
        "Karton": "XCT",
        "Blatt": "XST",
        "Bogen": "XST",
    }
    alle = set(anlernen.EINHEITEN.values()) | set(anlernen.EINHEIT_NAMEN)
    assert alle <= codelisten.EINHEITEN, sorted(alle - codelisten.EINHEITEN)


def test_alte_vorlage_mit_pk_wird_beim_laden_umgeschrieben(tmp_path):
    from fakturafalter import pdferkennung

    (tmp_path / "angelernt").mkdir()
    (tmp_path / "angelernt" / "druck-alt.yaml").write_text(
        "profil: druck\nkennung: alt\npositionen:\n  einheiten: {Pkt.: PK, Rolle: RO, Karton: CT, Stk.: H87}\n"
        "  einheit_fest: PK\n",
        encoding="utf-8",
    )
    (v,) = pdferkennung.vorlagen_laden({"profil": "druck", "_basis": str(tmp_path)})
    assert v["positionen"]["einheiten"] == {
        "Pkt.": "XPK",
        "Rolle": "XRO",
        "Karton": "XCT",
        "Stk.": "H87",
    }
    assert v["positionen"]["einheit_fest"] == "XPK"


@pytest.mark.parametrize("alt,neu", [("PK", "XPK"), ("RO", "XRO"), ("CT", "XCT")])
def test_alte_codes_zeigen_weiter_denselben_klartext(alt, neu):
    """CSV-Profile mit PK/RO/CT werden nicht umgeschrieben: der Sichtteil zeigt dafür weiter den Klartext."""
    for sprache in ("de", "en"):
        assert sicht._EINHEIT[sprache][alt] == sicht._EINHEIT[sprache][neu]
