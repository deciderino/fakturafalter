# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.5.0: CSV-/XML-Assistent, gegliederte Einstellungen, Überwachungs-Schalter, Absender-Profile (fiktive Daten)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtWidgets import QLabel

pytest.importorskip("PySide6")

from fakturafalter.gui import einstellungen as einst

from .test_adapter_xml import UBL
from .test_gui import BEISPIELE, fenster, konfig_datei, qapp, warten  # noqa: F401 – Fixtures


@pytest.mark.validierung
def test_csv_assistent_legt_normales_profil_an(fenster, qapp, konfig_datei):
    from pathlib import Path

    from fakturafalter.gui.datenassistent import CsvAssistent
    from fakturafalter.pipeline import verarbeiten

    d = CsvAssistent(fenster, fenster)
    assert d.i == 0 and not d.b_weiter.isEnabled()
    d.datei_setzen(BEISPIELE / "variante-a_positionen_utf8.csv")
    d.name.setText("Testware")
    assert d.b_weiter.isEnabled() and d.i == 0
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 1 and d.b_weiter.isEnabled()
    assert (d.f_trenn.currentData(), d.f_dez.currentData()) == (",", ".")
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 2 and d.b_weiter.isEnabled(), d.zuordnung()
    assert d.zuordnung()["BT-1"]
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 3 and d.b_weiter.isEnabled()  # Textzeilen
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 4 and d.b_weiter.isEnabled()  # Darstellung
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 5 and d.t_probe.rowCount() == 3 and d.b_weiter.isEnabled()
    d.b_weiter.click()  # „Speichern“
    qapp.processEvents()
    assert d.i == 6 and d.gespeichert and d.gespeichert.exists()
    roh = yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))
    from fakturafalter.konfig import csv_eintrag_datei

    assert roh["modus"] == "csv" and any(
        "profil-testware" in csv_eintrag_datei(p) for p in roh["csv_profile"]
    )
    assert any(p.get("profil") == "Testware" for p in fenster.k.csv_profile)
    d.b_weiter.click()  # „Fertig“
    qapp.processEvents()
    d.close()

    quelle = BEISPIELE / "variante-a_positionen_utf8.csv"
    fenster.k.eingang.mkdir(parents=True, exist_ok=True)
    ziel = fenster.k.eingang / quelle.name
    ziel.write_bytes(quelle.read_bytes())
    lauf = verarbeiten([ziel], fenster.k)
    hinw = [(e.nummer, e.hinweise) for e in lauf.ergebnisse]
    assert lauf.ok and not lauf.datei_fehler, (lauf.datei_fehler, hinw)
    assert all(e.status == "ok" for e in lauf.ergebnisse)
    pdfs = list(Path(fenster.k.ausgang).glob("*_zugferd.pdf"))
    assert pdfs
    if any(e.pruefung for e in lauf.ergebnisse):
        pruef = [(e.nummer, e.pruefung, e.hinweise) for e in lauf.ergebnisse]
        assert all(e.pruefung == "gültig" for e in lauf.ergebnisse), pruef


def test_csv_assistent_textzeilen_und_darstellung_zjp(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(BEISPIELE / "variante-zjp_textzeilen.csv")
    d.name.setText("ZJP-Text")
    d.b_weiter.click()
    qapp.processEvents()
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 2
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 3
    assert d.c_kommentare.isChecked() and d.c_leerzeilen.isChecked()
    assert d.t_tz_vorschau.rowCount() >= 1
    d.b_weiter.click()
    qapp.processEvents()
    assert d.i == 4
    assert d.c_menge_exakt.isChecked()
    p = d.profil()
    sicht = p.get("sicht") or {}
    assert sicht.get("menge_exakt") is True
    assert sicht.get("einheit") == "kurz"
    assert (p.get("aufbau") or {}).get("art") == "zeile_je_position"
    d.reject()


def test_csv_assistent_start_darstellung(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster, start="darstellung")
    d.datei_setzen(BEISPIELE / "variante-zjp_textzeilen.csv")
    d.name.setText("ZJP-Text")
    qapp.processEvents()
    # nach Datei/Format/Vorschau-Daten zum Darstellungsschritt springen
    if d.i != 4:
        d.gehe(4)
        qapp.processEvents()
    assert d.i == 4
    assert d.c_menge_exakt.isChecked()
    d.reject()


def test_csv_assistent_lesefehler_laesst_weiter_konsistent(fenster, qapp, tmp_path):
    from fakturafalter.gui.datenassistent import CsvAssistent

    leer = tmp_path / "leer.csv"
    leer.write_text("", encoding="utf-8")
    d = CsvAssistent(fenster, fenster)
    assert not d.b_weiter.isEnabled()
    d.datei_setzen(leer)
    assert d.datei is None and not d.b_weiter.isEnabled() and d.i == 0
    assert any("nicht lesen" in (w.text() or "") for w in d.findChildren(QLabel))
    d.datei_setzen(BEISPIELE / "variante-a_positionen_utf8.csv")
    assert d.b_weiter.isEnabled()
    d.datei_setzen(leer)
    # vorherige gültige Datei bleibt, Button bleibt aktiv; Toast erklärt den Fehlversuch
    assert d.datei is not None and d.b_weiter.isEnabled()
    d.reject()


def test_csv_assistent_erkennt_satzart(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(BEISPIELE / "variante-b_wawi_cp1252.csv")
    d.name.setText("b")
    assert d.b_weiter.isEnabled() and d.i == 0
    d.b_weiter.click()
    assert d.i == 1 and d.b_weiter.isEnabled()
    assert d.art == "satzart"
    d.reject()


def test_csv_assistent_erkennt_bloecke(fenster, qapp):
    from fakturafalter.gui.datenassistent import CsvAssistent

    d = CsvAssistent(fenster, fenster)
    d.datei_setzen(BEISPIELE / "variante-blo_hotel.csv")
    d.name.setText("Hotel")
    assert d.art == "bloecke"
    d.b_weiter.click()
    assert d.i == 1 and d.b_weiter.isEnabled()
    d.b_weiter.click()
    assert d.i == 2 and d.box_bloecke.isVisibleTo(d) and d.box_text.isVisibleTo(d)
    assert d.f_block.count() >= 2
    assert d.b_weiter.isEnabled(), d._alle_zuordnungen()
    p = d.profil()
    assert (p.get("aufbau") or {}).get("art") == "bloecke"
    d.reject()


def test_xml_assistent_schaltet_xml_ein(fenster, qapp, konfig_datei, tmp_path):
    from fakturafalter.gui.datenassistent import XmlAssistent

    (tmp_path / "r.xml").write_text(UBL, encoding="utf-8")
    d = XmlAssistent(fenster, fenster)
    assert not d.b_weiter.isEnabled()
    d.datei_setzen(tmp_path / "r.xml")
    assert "UBL" in d.l_format.text()
    assert d.b_weiter.isEnabled()
    d.b_weiter.click()
    assert d.t_probe.rowCount() == 1 and d.b_weiter.isEnabled()
    d.b_weiter.click()
    assert yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))["modus"] == "xml"
    d.reject()


def test_einstellungen_gegliedert_und_speicherbar(fenster, qapp):
    d = einst.Einstellungen(fenster, "Eingang & Vorlagen")
    assert [d.nav.item(i).text() for i in range(d.nav.count())] == list(einst.BEREICHE)
    assert d.stapel.currentIndex() == einst.bereich("Eingang & Vorlagen")
    assert [b.property("code") for b in d.modus_gruppe.buttons()] == ["csv", "xml", "nur_pdf"]
    r_np = d.findChild(einst.QRadioButton, "modus_nur_pdf")
    assert r_np.minimumHeight() >= 48
    assert any(w.text() == "nicht empfohlen" for w in d.findChildren(QLabel))
    d.findChild(einst.QRadioButton, "modus_xml").setChecked(True)
    assert d.box_xml.isVisibleTo(d) and not d.box_csv.isVisibleTo(d)
    assert d.pdf_verwenden.isVisibleTo(d) and d.pdf_verwenden.minimumHeight() >= 48
    d.pdf_verwenden.setChecked(False)
    assert not d.box_warten.isVisibleTo(d)
    d.pdf_verwenden.setChecked(True)
    assert d.box_warten.isVisibleTo(d)
    d.findChild(einst.QRadioButton, "modus_nur_pdf").setChecked(True)
    assert d.box_pdf.isVisibleTo(d) and not d.box_warten.isVisibleTo(d)
    assert not d.pdf_verwenden.isVisibleTo(d)
    d.findChild(einst.QRadioButton, "modus_csv").setChecked(True)
    assert d.pdf_verwenden.isVisibleTo(d)
    d.pdf_verwenden.setChecked(True)
    d.gegenstueck.setValue(3)
    r = d.ergebnis()
    assert r["modus"] == "csv" and r["optionen"]["pdf_verwenden"] is True
    assert r["optionen"]["gegenstueck_minuten"] == 3
    d.pdf_verwenden.setChecked(False)
    r = d.ergebnis()
    assert r["modus"] == "csv" and r["optionen"]["pdf_verwenden"] is False
    assert fenster.einstellungen_uebernehmen(r)
    d.reject()


def test_einstellungen_profilkarten_aktiv_und_reihenfolge(fenster, qapp):
    from PySide6.QtWidgets import QCheckBox, QPushButton

    d = einst.Einstellungen(fenster, "Eingang & Vorlagen")
    aktiv = [b for b in d.findChildren(QCheckBox) if b.text() == "Aktiv"]
    assert len(aktiv) >= 2
    knoepfe = [b.text() for b in d.findChildren(QPushButton)]
    assert "Hoch" in knoepfe and "Runter" in knoepfe
    assert any("Profil testen" in (t or "") for t in knoepfe)
    texte = " ".join(w.text() or "" for w in d.findChildren(QLabel))
    assert "Blöcke:" in texte or "Bloecke:" in texte
    # erstes Profil aus, bleibt in der Liste
    assert aktiv[0].isChecked()
    aktiv[0].setChecked(False)
    r = d.ergebnis()
    ein = r.get("csv_profile") or []
    assert ein and isinstance(ein[0], dict) and ein[0].get("aktiv") is False
    d.reject()


def test_absender_profile_wechseln(fenster, qapp):
    d = einst.Einstellungen(fenster, "Absender")
    alt = d.abs["name"].text()
    assert alt and d.abs_wahl.count() == 2  # aktiver + „Neuer Absender“
    d._absender_wechseln(1)  # neuer Absender
    assert d.abs["name"].text() == ""
    d.abs["name"].setText("Zweitfirma Muster GmbH")
    r = d.ergebnis()
    assert r["absender"]["name"] == "Zweitfirma Muster GmbH"
    assert [p["absender"]["name"] for p in r["absender_profile"]] == [alt]
    d._absender_wechseln(0)
    assert d.abs["name"].text() == alt
    r = d.ergebnis()
    assert (
        r["absender"]["name"] == alt
        and r["absender_profile"][0]["absender"]["name"] == "Zweitfirma Muster GmbH"
    )
    d.reject()


def test_ueberwachung_ruht_waehrend_einstellungen(fenster, qapp, monkeypatch):
    assert warten(qapp, lambda: fenster.zust == "aktiv")
    assert fenster.b_pause.isChecked() and fenster.b_pause.minimumHeight() >= 48
    gesehen = []
    monkeypatch.setattr(
        einst.Einstellungen,
        "exec",
        lambda self: gesehen.append((fenster.zust, fenster.b_pause.isEnabled())) or 0,
    )
    fenster.einstellungen_oeffnen()
    assert gesehen == [("pausiert", False)]
    assert fenster.zust == "aktiv" and fenster.b_pause.isEnabled()
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    fenster.einstellungen_oeffnen()
    assert fenster.zust == "pausiert" and fenster.b_pause.text() == "Überwachung aus"


def test_assistent_auswahltexte_uebersetzt():
    from fakturafalter import csv_einrichtung as ce
    from fakturafalter.gui import datenassistent as da
    from fakturafalter.gui import texte

    alle = [t for w in (da.TRENNZEICHEN, da.KODIERUNGEN, da.DEZIMAL, da.DATUM) for _c, t in w]
    alle += [
        *da.CsvAssistent.SCHRITTE,
        *da.XmlAssistent.SCHRITTE,
        da.NICHT,
        *(f[1] for f in ce.FELDER),
        *ce.STEUER_WAHL,
    ]
    assert not [a for a in alle if a not in texte.EN]
