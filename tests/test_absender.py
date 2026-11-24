# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Absender aus dem Druck erkennen und aus einer CSV-Zeile übernehmen."""

from pathlib import Path

import pytest

from fakturafalter import absender, adapter_pdf, pdferkennung

BSP = Path(__file__).resolve().parent.parent / "beispiele" / "pdf-erkennung" / "eingang"


@pytest.mark.parametrize(
    "datei, name, ort, kennung",
    [
        ("EF-1041.pdf", "Elektro Funke e.K.", "Bochum", "DE314159262"),
        ("GL-2026-118.pdf", "Gartenbau Lindgrün GmbH", "Freiburg", "DE445566772"),
        ("KR-2026-031.pdf", "Musikschule Klangraum e.V.", "Regensburg", "21/815/08150"),
        ("MK-26-0412.pdf", "Metallbau Kessler GmbH", "Hagen", "DE800800808"),
        ("PW-INV-2026-0087.pdf", "Pixelwerk Software GmbH", "Leipzig", "DE607080900"),
        ("SK-2026-0412.pdf", "Bäckerei Sonnenkorn GmbH", "Hildesheim", "DE271408158"),
    ],
)
def test_absender_aus_druck(datei, name, ort, kennung):
    a = absender.erkennen_aus_zeilen(pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(BSP / datei)))
    assert (a.name, a.ort) == (name, ort)
    assert kennung in (a.ust_id, a.steuernummer)
    assert absender.iban_gueltig(a.iban) and a.strasse and a.plz
    assert a.fehlt() == []


def test_absender_aus_csv_und_bloecke():
    daten = (
        "Name;Straße;PLZ;Ort;USt-IdNr;IBAN;E-Mail\n"
        "Muster Normteile GmbH;Werkstraße 4;12345;Musterstadt;DE123456789;DE02 1203 0000 0000 2020 51;"
        "rechnung@muster.invalid\n"
    ).encode("cp1252")
    a = absender.aus_csv(daten)
    assert (
        a.name == "Muster Normteile GmbH"
        and a.strasse == "Werkstraße 4"
        and a.iban == "DE02120300000000202051"
    )
    vk, zb = a.bloecke()
    assert (
        vk["anschrift"]["ort"] == "Musterstadt"
        and vk["elektronische_adresse"] == "rechnung@muster.invalid"
    )
    assert absender.Absender.aus_bloecken(vk, zb) == a


def test_absender_csv_ohne_bekannte_spalte():
    with pytest.raises(ValueError, match="Keine bekannte Spalte"):
        absender.aus_csv(b"a;b\n1;2\n")
    with pytest.raises(ValueError, match="nur die Kopfzeile"):
        absender.aus_csv(b"Name;Ort\n")


def test_adresszusatz_round_trip_und_csv():
    from fakturafalter import absender as ab

    a = ab.Absender(
        name="Muster GmbH",
        strasse="Musterstraße 1",
        zusatz="Haus B",
        plz="12345",
        ort="Musterstadt",
    )
    vk, zb = a.bloecke()
    assert vk["anschrift"]["zusatz"] == "Haus B"
    assert ab.Absender.aus_bloecken(vk, zb).zusatz == "Haus B"
    assert "zusatz" not in ab.Absender(name="X").bloecke()[0]["anschrift"]
    csv = "Name;Strasse;Adresszusatz;PLZ;Ort\nMuster GmbH;Musterstraße 1;Haus B;12345;Musterstadt\n".encode()
    assert ab.aus_csv(csv).zusatz == "Haus B"


def test_briefkopf_name_mehrzeilig_feste_regel():
    """Briefkopf über mehrere Zeilen, feste Regel (0.4.4): PLZ/Ort, die Zeile darüber ist die Straße, alles
    darüber gehört zum Namen – „Niederlassung“, „c/o“ werden kein Adresszusatz mehr."""
    a = absender.erkennen(
        [
            "Beispiel Werkzeug- und",
            "Anlagenbau GmbH",
            "Niederlassung Süd",
            "Musterweg 12",
            "12345 Musterstadt",
            "Deutschland",
        ]
    )
    assert a.name == "Beispiel Werkzeug- und Anlagenbau GmbH Niederlassung Süd"
    assert (a.zusatz, a.strasse, a.plz, a.ort) == ("", "Musterweg 12", "12345", "Musterstadt")
    a = absender.erkennen(
        ["Muster & Partner GmbH · c/o Beispiel AG · Postfach 12 34 · 12345 Musterstadt"]
    )
    assert (a.name, a.zusatz, a.strasse, a.plz) == (
        "Muster & Partner GmbH c/o Beispiel AG",
        "",
        "Postfach 12 34",
        "12345",
    )


def test_iban_und_bic_nicht_als_absender_strasse():
    """IBAN/BIC dürfen nicht als Straße gelesen werden, auch wenn _STRASSE die Form akzeptieren würde."""
    from fakturafalter.anschrift import anschrift_zerlegen, kontozeile, strassenzeile

    iban, bic = "DE89 3704 0044 0532 0130 00", "COBADEFFXXX"
    assert kontozeile(iban) and kontozeile(bic)
    assert not strassenzeile(iban) and not strassenzeile(bic)
    a = absender.erkennen(["Muster GmbH", iban, "Musterweg 12", "12345 Musterstadt", bic])
    assert a.strasse == "Musterweg 12" and a.plz == "12345" and a.ort == "Musterstadt"
    a2 = absender.erkennen(["Muster GmbH", iban, "12345 Musterstadt"])
    assert "DE89" not in (a2.strasse or "") and a2.plz == "12345"
    teile, _ = anschrift_zerlegen(["Muster GmbH", iban, "Musterweg 12", "12345 Musterstadt"])
    assert teile["BT-50"] == "Musterweg 12" and teile["BT-44"] == "Muster GmbH"
