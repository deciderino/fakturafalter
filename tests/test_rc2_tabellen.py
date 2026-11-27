# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""rc2: Excel (.xlsx) und ODS als Eingabe – über Assistent/Profil wie eine CSV, Beträge als Decimal (fiktiv)."""

from decimal import Decimal as D
from pathlib import Path

import pytest

from fakturafalter import adapter_csv, pipeline, tabellen
from fakturafalter import csv_einrichtung as ce

from .tabellen_hilfe import ods_schreiben, xlsx_schreiben


@pytest.mark.parametrize(
    ("f", "erwartet"),
    [(0.1 + 0.2, "0.3"), (12.3, "12.3"), (19.99, "19.99"), (2.675, "2.675"), (1234567.89, "1234567.89"),
     (100.0, "100"), (-0.07, "-0.07"), (1e-7, "1E-7"), (0.0, "0"), (24.9 * 3, "74.7")],
)
def test_zahl_aus_float(f, erwartet):
    assert tabellen.zahl_aus_float(f) == D(erwartet)
    assert "E" not in tabellen.zahl_text(tabellen.zahl_aus_float(f), ".")


def test_zahl_text():
    assert tabellen.zahl_text(D("1234.50"), ",") == "1234,5"
    assert tabellen.zahl_text(D("1E+2"), ",") == "100"
    assert tabellen.zahl_text(D("0.0000001"), ".") == "0.0000001"


@pytest.mark.parametrize("art", ["xlsx", "ods"])
def test_format_erkennen_blatt_startzeile(tmp_path, art):
    datei = (xlsx_schreiben if art == "xlsx" else ods_schreiben)(tmp_path / f"export.{art}")
    fmt = ce.format_erkennen(datei)
    assert fmt.ist_tabelle and fmt.blatt == "Export" and "Export" in fmt.blaetter
    assert fmt.startzeile == 3
    assert fmt.kopf[:3] == ["Rechnungsnummer", "Rechnungsdatum", "Kunde"]
    assert len(fmt.zeilen) == 3
    z0 = fmt.zeilen[0]
    assert z0[1] == "03.11.2026" and z0[6] == "0,3" and z0[7] == "19 %" and z0[4] == "100"
    assert fmt.dezimal == "," and fmt.datum == "%d.%m.%Y"
    # anderes Dezimalzeichen: Zahlzellen folgen
    fmt2 = ce.format_erkennen(datei, dezimal=".", datum_format="%Y-%m-%d")
    assert fmt2.zeilen[1][6] == "19.99" and fmt2.zeilen[0][1] == "2026-11-03"
    # anderes Blatt
    with pytest.raises(ValueError):
        ce.format_erkennen(datei, blatt="Gibt es nicht")


@pytest.mark.parametrize("art", ["xlsx", "ods"])
def test_profil_und_lesen_decimal(tmp_path, konfig, art):
    datei = (xlsx_schreiben if art == "xlsx" else ods_schreiben)(tmp_path / f"export.{art}")
    fmt = ce.format_erkennen(datei)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    assert not ce.fehlende_pflicht(z), z
    p = ce.profil_bauen("Tabelle", datei, fmt, z, ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
                        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])))
    assert p["datei"]["muster"] == f"*.{art}" and p["datei"]["blatt"] == "Export" and p["datei"]["startzeile"] == 3
    assert adapter_csv.profil_passt(datei, p)
    rs = adapter_csv.lesen(datei, p, konfig)
    assert [r.nummer for r in rs] == ["RE-2026-9001", "RE-2026-9002"]
    r1 = rs[0]
    assert [(q.menge, q.einzelpreis, q.steuer.satz) for q in r1.positionen] == [
        (D("100"), D("0.3"), D("19")), (D("2.5"), D("19.99"), D("19"))]
    assert all(isinstance(q.einzelpreis, D) for q in r1.positionen)
    assert r1.datum.isoformat() == "2026-11-03" and r1.kaeufer.name == "Beispiel Handel GmbH"
    assert rs[1].positionen[0].steuer.satz == D("7")
    # Blatt fehlt: Profil passt nicht (kein Absturz), lesen meldet Klartext
    p2 = dict(p, datei=dict(p["datei"], blatt="Anderes"))
    assert not adapter_csv.profil_passt(datei, p2)
    with pytest.raises(tabellen.TabellenFehler, match="Anderes"):
        adapter_csv.lesen(datei, p2, konfig)


def test_pipeline_xlsx_bis_zugferd(tmp_path, konfig):
    datei = xlsx_schreiben(konfig.eingang / "export.xlsx")
    fmt = ce.format_erkennen(datei)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    p = ce.profil_bauen("Tabelle", datei, fmt, z, ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
                        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])))
    konfig.csv_profile = [p]
    konfig.pdf_verwenden = False
    konfig.modus = "csv"
    lauf = pipeline.verarbeiten([datei], konfig)
    assert [e.status for e in lauf.ergebnisse] == ["ok", "ok"], [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    assert len(list(konfig.ausgang.glob("*_zugferd.pdf"))) == 2
    import pikepdf

    pdf = sorted(konfig.ausgang.glob("RE-2026-9001*_zugferd.pdf"))[0]
    with pikepdf.open(pdf) as doc:
        xml = next(iter(doc.attachments.values())).get_file().read_bytes().decode("utf-8")
    assert "<ram:ChargeAmount>0.30</ram:ChargeAmount>" in xml or ">0.3<" in xml or "0.3000" in xml
    assert "30.00" in xml  # 100 × 0,30
    assert "49.98" in xml or "49.97" in xml  # 2,5 × 19,99 = 49,975 → kaufmännisch gerundet


def test_kaputt_und_verschluesselt(tmp_path, konfig):
    k = tmp_path / "kaputt.xlsx"
    k.write_bytes(b"kein zip")
    with pytest.raises(tabellen.TabellenFehler, match="beschädigt"):
        tabellen.lesen(k)
    p = {"datei": {"muster": "*.xlsx"}, "felder": {"kopf": {"BT-1": {"spalte": "Nr"}}}}
    assert not adapter_csv.profil_passt(k, p)
    konfig.csv_profile = [p]
    with pytest.raises(ValueError, match="Tabelle nicht lesbar|Kein passendes"):
        pipeline.einlesen(k, konfig)


def test_ods_lange_leere_zeilen_schnell(tmp_path):
    import time

    datei = ods_schreiben(tmp_path / "x.ods")
    t0 = time.time()
    t = tabellen.lesen(datei)
    assert time.time() - t0 < 5
    assert len(t.zeilen) == 6  # Titel, Leerzeile, Kopf, 3 Daten – keine Million Leerzeilen
    assert tabellen.blaetter(datei) == ["Export", "Leer"]


def test_formel_ohne_gespeicherten_wert_bleibt_leer(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["A", "B", "Summe"])
    ws.append([1, 2, "=A2+B2"])
    f = tmp_path / "formel.xlsx"
    wb.save(f)
    zeilen = tabellen.zeilen_als_text(tabellen.lesen(f))
    assert zeilen[1] == ["1", "2"]  # kein gespeicherter Wert → leer, kein „=A2+B2“


def test_umwandeln_von_hand_nimmt_tabellen(konfig, tmp_path):
    from fakturafalter.ueberwachung import manuell_sammeln

    konfig.pdf_verwenden = False
    konfig.modus = "csv"
    q = tmp_path / "q"
    q.mkdir()
    xlsx_schreiben(q / "a.xlsx")
    ods_schreiben(q / "b.ods")
    (q / "c.xls").write_bytes(b"\xd0\xcf")
    a = manuell_sammeln([q], konfig)
    assert sorted(p.name for p in a.dateien) == ["a.xlsx", "b.ods"]
    assert [p.name for p, _g in a.uebersprungen] == ["c.xls"]


def test_lizenz_openpyxl_erlaubt():
    import re
    from importlib import metadata

    root = Path(__file__).resolve().parent.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"openpyxl>=3\.1"', text)
    lic = metadata.metadata("openpyxl").get("License") or ""
    assert "MIT" in lic
    assert "openpyxl" in (root / "packaging" / "lizenzen.py").read_text(encoding="utf-8")


# --- Assistent (GUI) ---------------------------------------------------------------------------

from .test_gui import fenster, konfig_datei, qapp  # noqa: E402,F401 – Fixtures


def test_assistent_tabelle_blatt_und_kopfzeile(fenster, qapp, tmp_path):
    import yaml

    from fakturafalter.gui.datenassistent import CsvAssistent

    datei = xlsx_schreiben(tmp_path / "export.xlsx")
    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(datei)
    d.name.setText("Excel-Test")
    qapp.processEvents()
    assert not d.box_tabelle.isHidden() and d.f_trenn.isHidden() and d.f_kod.isHidden()
    assert [d.f_blatt.itemText(i) for i in range(d.f_blatt.count())] == ["Export", "Notizen"]
    assert d.f_start.value() == 3 and d.fmt.kopf[0] == "Rechnungsnummer"
    d.f_start.setValue(1)  # falsche Zeile: Titel wird Kopf
    assert d.fmt.startzeile == 1 and d.fmt.kopf[0].startswith("Rechnungsexport")
    d.f_start.setValue(3)
    d.f_blatt.setCurrentIndex(1)  # anderes Blatt: Kopfzeile neu vorgeschlagen
    assert d.fmt.blatt == "Notizen" and d.fmt.startzeile == 1
    d.f_blatt.setCurrentIndex(0)
    assert d.fmt.blatt == "Export" and d.fmt.startzeile == 3 and d.f_start.value() == 3
    probe = next(i for i, (st, _n) in enumerate(d._folge()) if st == 5)
    d.gehe(probe)
    qapp.processEvents()
    assert d.t_probe.rowCount() >= 1
    ziel = d.speichern()
    assert ziel and ziel.exists()
    p = yaml.safe_load(ziel.read_text(encoding="utf-8"))
    assert p["datei"]["muster"] == "*.xlsx" and p["datei"]["blatt"] == "Export" and p["datei"]["startzeile"] == 3
    d.reject()
    # „Ändern…“: gespeichertes Blatt/Zeile wird übernommen, auch wenn das erste Blatt anders heißt
    d2 = CsvAssistent(fenster, fenster, dict(p, datei=dict(p["datei"], startzeile=3)))
    d2.datei_setzen(datei)
    assert d2.fmt.blatt == "Export" and d2.f_start.value() == 3
    d2.reject()


def test_csv_zeigt_keine_tabellenfelder(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    from .test_gui import BEISPIELE

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(BEISPIELE / "variante-a_positionen_utf8.csv")
    assert d.box_tabelle.isHidden() and not d.f_trenn.isHidden()
    d.reject()
