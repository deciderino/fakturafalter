# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
from datetime import date
from decimal import Decimal as D

import pytest

from fakturafalter import adapter_csv, adapter_pdf, rechnen
from fakturafalter.werte import WertFehler, dekodieren, zahl

from .conftest import BEISPIELE

SOLL = {
    "RE-2026-0101": ("327.40", "57.42", "384.82"),
    "RE-2026-0102": ("174.50", "33.16", "207.66"),
    "RE-2026-0103": ("145.00", "27.55", "172.55"),
}


@pytest.mark.parametrize(
    "text,dez,tsd,impl,soll",
    [
        ("1.234,56", ",", ".", 0, "1234.56"),
        ("1,234.56", ".", ",", 0, "1234.56"),
        ("-3,5", ",", ".", 0, "-3.5"),
        ("3,50-", ",", ".", 0, "-3.50"),
        ("000000038482", ",", "", 2, "384.82"),
    ],
)
def test_zahl(text, dez, tsd, impl, soll):
    assert zahl(text, dez, tsd, impl) == D(soll)


def test_zahl_unlesbar():
    with pytest.raises(WertFehler):
        zahl("12a", ",", ".")


def test_kodierung_cp1252_erkannt():
    text, kod = dekodieren("Fachbuch „Montage“ Stück".encode("cp1252"))
    assert (
        "„Montage“" in text
        and "Stück" in text
        and kod.lower().replace("-", "") in ("cp1252", "windows1252")
    )


def _profil(konfig, name: str):
    return next(p for p in konfig.csv_profile if p.get("profil") == name)


@pytest.mark.parametrize(
    "datei,profil_name",
    [
        ("variante-a_positionen_utf8.csv", "export-utf8-komma"),
        ("variante-b_wawi_cp1252.csv", "wawi-semikolon"),
        ("variante-c_festbreite_cp1252.txt", "festbreite-kp"),
    ],
)
def test_csv_varianten(konfig, datei, profil_name):
    pfad = BEISPIELE / datei
    prof = _profil(konfig, profil_name)
    assert adapter_csv.profil_passt(pfad, prof)
    # andere Profile dürfen nicht passen
    assert not any(
        adapter_csv.profil_passt(pfad, p)
        for p in konfig.csv_profile
        if p.get("profil") != profil_name
    )
    rs = {r.nummer: r for r in adapter_csv.lesen(pfad, prof, konfig)}
    assert set(rs) == set(SOLL)
    for nr, r in rs.items():
        s = rechnen.berechnen(r)
        assert (str(s.netto), str(s.ust), str(s.brutto)) == SOLL[nr], nr
        assert r.status == "ok", [str(h) for h in r.hinweise]
    r1 = rs["RE-2026-0101"]
    assert r1.datum == date(2026, 10, 5) and r1.leistungsdatum == date(2026, 10, 2)
    assert [p.einheit for p in r1.positionen] == ["C62", "HUR", "C62"]
    assert r1.positionen[2].bezeichnung == "Fachbuch „Montage für Einsteiger“"
    assert rs["RE-2026-0102"].bestellnummer == "B-2026-77"
    assert rs["RE-2026-0102"].leitweg_id == "04011000-12345-03"
    assert r1.kaeufer.name == "Beispiel Handel GmbH"


def test_pdf_druckauftrag_zerlegen_und_lesen(konfig):
    pfad = BEISPIELE / "druckauftrag-wawi.pdf"
    seiten = adapter_pdf.seiten_lesen(pfad)
    v = adapter_pdf.vorlage_finden(seiten, konfig.pdf_vorlagen)
    assert v is not None
    rs = adapter_pdf.lesen(pfad, v, konfig, seiten)
    assert [r.nummer for r in rs] == ["RE-2026-0101", "RE-2026-0102"]
    assert rs[0].sicht_pdf[1] == [0, 1] and rs[1].sicht_pdf[1] == [2]
    for r in rs:
        s = rechnen.berechnen(r)
        assert (str(s.netto), str(s.ust), str(s.brutto)) == SOLL[r.nummer]
        if r.nummer == "RE-2026-0102":
            # rc1: Stadtverwaltung Musterhausen steht in der XRechnung-Liste, der Druck hat keine
            # E-Rechnungsadresse (BT-49) -> einziger Prüfgrund
            assert [h.feld for h in r.hinweise if h.stufe == "pruefen"] == ["BT-49"], r.hinweise
        else:
            assert r.status == "ok", [str(h) for h in r.hinweise]
    # lange Bezeichnung ragt in Menge-Spalte, Übertrag-Zeile ignoriert
    assert len(rs[0].positionen) == 3
    assert rs[0].positionen[1].menge == D("3.5")


def test_unbekannte_einheit_fuehrt_zu_pruefen(konfig, tmp_path):
    src = (
        (BEISPIELE / "variante-a_positionen_utf8.csv")
        .read_text(encoding="utf-8")
        .replace(",Std,", ",Kiste,", 1)
    )
    p = tmp_path / "x.csv"
    p.write_text(src, encoding="utf-8")
    rs = {r.nummer: r for r in adapter_csv.lesen(p, _profil(konfig, "export-utf8-komma"), konfig)}
    assert rs["RE-2026-0101"].status == "pruefen"
    assert rs["RE-2026-0102"].status == "ok"


def test_unlesbare_datei_klartext(konfig, tmp_path):
    """Datei, die nur scheinbar zu einem Profil passt, liefert Klartext statt nackter Python-Ausnahme."""
    import shutil
    from pathlib import Path

    from fakturafalter import pipeline

    d = tmp_path / "scan-unbekannt.txt"
    shutil.copy(Path(__file__).parents[1] / "beispiele" / "textdruck-wawi_cp1252.txt", d)
    with pytest.raises(ValueError, match="nicht lesbar|Kein passendes CSV-Profil"):
        pipeline.einlesen(d, konfig)


def test_festbreite_kp_textdruck_kein_absturz(konfig, tmp_path):
    """Regression ValueError „tri“: Das Muster „*.txt“ von festbreite-kp passte auf Textdrucke, dann brach
    ``int("tri")`` den Lauf mit einer nackten Python-Ausnahme ab."""
    import shutil
    from pathlib import Path

    from fakturafalter import adapter_csv, pipeline

    prof = next(p for p in konfig.csv_profile if p.get("profil") == "festbreite-kp")
    beisp = Path(__file__).parents[1] / "beispiele"
    druck = Path(shutil.copy(beisp / "textdruck-wawi_cp1252.txt", tmp_path / "druck.txt"))
    assert not adapter_csv.profil_passt(druck, prof)
    assert adapter_csv.profil_passt(beisp / "variante-c_festbreite_cp1252.txt", prof)
    with pytest.raises(ValueError, match="Kein passendes CSV-Profil"):
        pipeline.einlesen(druck, konfig)
    # Auch direkt gelesen: Klartext je Zeile statt Absturz
    for r in adapter_csv.lesen(druck, prof, konfig):
        assert r.status in ("fehler", "pruefen")


def test_festbreite_ganzzahl_klartext(konfig):
    from fakturafalter import adapter_csv
    from fakturafalter.werte import WertFehler

    with pytest.raises(WertFehler, match="keine ganze Zahl"):
        adapter_csv._typisieren("tri", {"typ": "ganzzahl"}, {})
