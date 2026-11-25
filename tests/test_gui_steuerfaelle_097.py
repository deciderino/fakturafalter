"""0.9.7 Oberfläche (offscreen): Steuerfall-Auswahl und Steuerspalte im Anlern-Assistenten, Schalter
Kleinunternehmer im Absender-Formular. Daten: beispiele/steuerfaelle (erfunden)."""

from pathlib import Path

import pytest
import yaml

pytest.importorskip("PySide6")
pytest.importorskip("pypdfium2")

from fakturafalter import anlernen  # noqa: E402
from fakturafalter.gui import aktionen, texte  # noqa: E402

SF = Path(__file__).resolve().parent.parent / "beispiele" / "steuerfaelle"
IND = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"
aktionen.NUR_MERKEN = True


@pytest.fixture(scope="session")
def qapp():
    from fakturafalter.gui.app import anwendung

    return anwendung()


@pytest.fixture
def fenster(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    texte.sprache_setzen("de")
    roh = yaml.safe_load((IND / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    pfad = tmp_path / "konfiguration.yaml"
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(pfad, tray_erlaubt=False, auto_start=False)
    w.show()
    qapp.processEvents()
    yield w
    w.beenden()
    qapp.processEvents()


def _assistent(qapp, fenster, name):
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [SF / "eingang" / name])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    qapp.processEvents()
    d.schritt_setzen(3)
    qapp.processEvents()
    return d


def test_steuerfall_vorschlag_und_auswahl(qapp, fenster):
    d = _assistent(qapp, fenster, "WE-26-0302.pdf")
    assert d.steuerfall.objectName() == "steuerfall"
    assert d.steuerfall.currentData() == ""  # automatisch
    assert "Reverse Charge" in d.l_steuerfall.text()
    assert d.s.pv()["steuer_fest"] == {"fall": "hinweis"}
    d.steuerfall.setCurrentIndex(d.steuerfall.findData("KU"))
    d._steuerfall_gewaehlt()
    assert d.s.absender.kleinunternehmer is True
    assert d.s.pv()["steuer_fest"]["fall"] == "KU"
    d.steuerfall.setCurrentIndex(d.steuerfall.findData("AE"))
    d._steuerfall_gewaehlt()
    assert d.s.absender.kleinunternehmer is False
    d.reject()


def test_steuerspalte_je_wert(qapp, fenster):
    d = _assistent(qapp, fenster, "LM-26-2007.pdf")
    pv = d.s.pv()
    assert "steuer" in pv["spalten"]
    assert pv["steuer"]["19 %"] == {"BT-151": "S", "BT-152": "19"}
    assert pv["steuer"]["0 %"] == {"fall": "hinweis"}
    d.reject()


def test_absender_kleinunternehmer_schalter(qapp):
    from fakturafalter.gui.absender_form import AbsenderFormular, in_roh, pflicht_fehlt

    f = AbsenderFormular({"absender": {"kleinunternehmer": True}}, lambda *a: None)
    assert f.ku.objectName() == "abs_kleinunternehmer" and f.ku.isChecked()
    assert f.werte()["kleinunternehmer"] == "1"
    roh: dict = {}
    in_roh(roh, f.werte())
    assert roh["absender"]["kleinunternehmer"] is True
    f.ku.setChecked(False)
    in_roh(roh, f.werte())
    assert "kleinunternehmer" not in roh["absender"]
    ku = "USt-IdNr., Steuernummer oder Handelsregister"
    assert ku in pflicht_fehlt({"kleinunternehmer": "1"})
    assert ku not in pflicht_fehlt(
        {"kleinunternehmer": "1", "register": "Amtsgericht Musterstadt HRB 1"}
    )
