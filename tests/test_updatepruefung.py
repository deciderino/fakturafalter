# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Updateprüfung (ab 0.9.6): einziger Netzzugriff. Alle Tests mit gemocktem Netz – nie ein echter Aufruf."""

import io
import json
import logging
import threading
import urllib.request

import pytest

from fakturafalter import __version__, updatepruefung

REL = [
    {
        "tag_name": "v9.0.0-rc1",
        "prerelease": True,
        "draft": False,
        "html_url": "https://github.com/deciderino/fakturafalter/releases/tag/v9.0.0-rc1",
    },
    {
        "tag_name": "v8.1.0",
        "prerelease": False,
        "draft": False,
        "html_url": "https://github.com/deciderino/fakturafalter/releases/tag/v8.1.0",
    },
    {
        "tag_name": "v99.0.0",
        "prerelease": False,
        "draft": True,
        "html_url": "https://example.invalid/x",
    },
    {
        "tag_name": "v0.1.0",
        "prerelease": False,
        "draft": False,
        "html_url": "https://github.com/deciderino/fakturafalter/releases/tag/v0.1.0",
    },
]


def test_version_tupel():
    t = updatepruefung.version_tupel
    assert t("v0.9.6") > t("0.9.5") > t("0.9.4")
    assert t("0.9.6rc1") < t("0.9.6") and t("0.9.6-beta.2") < t("0.9.6rc1")
    assert t("0.10.0") > t("0.9.9") and t("kaputt") == ()


def test_auswerten_ohne_und_mit_vorab():
    neu = updatepruefung.auswerten(REL, vorab=False, aktuell="0.9.6")
    assert (neu.version, neu.vorab) == ("8.1.0", False)
    assert neu.url.endswith("/releases/tag/v8.1.0")
    neu = updatepruefung.auswerten(REL, vorab=True, aktuell="0.9.6")
    assert (neu.version, neu.vorab) == ("9.0.0-rc1", True)
    assert updatepruefung.auswerten(REL, vorab=True, aktuell="99.0.0") is None  # Entwurf zählt nie
    assert updatepruefung.auswerten([], aktuell="0.9.6") is None
    assert updatepruefung.auswerten({"message": "rate limit"}, aktuell="0.9.6") is None


def test_fremder_link_wird_nicht_weitergegeben():
    rel = [{"tag_name": "v50.0.0", "html_url": "https://boese.example/x"}]
    assert updatepruefung.auswerten(rel, aktuell="0.9.6").url == updatepruefung.RELEASES


def test_anfrage_nur_get_ohne_daten(monkeypatch):
    monkeypatch.undo()  # konftest-Schutz aus, dafür urlopen gemockt
    gesehen = {}

    class Antwort(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        gesehen.update(
            url=req.full_url,
            methode=req.get_method(),
            daten=req.data,
            kopf=dict(req.header_items()),
            timeout=timeout,
        )
        return Antwort(json.dumps(REL).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    erreichbar, neu = updatepruefung.jetzt(vorab=False)
    assert erreichbar and neu.version == "8.1.0"
    assert (
        gesehen["url"]
        == "https://api.github.com/repos/deciderino/fakturafalter/releases?per_page=30"
    )
    assert gesehen["methode"] == "GET" and gesehen["daten"] is None
    assert set(gesehen["kopf"]) == {"User-agent", "Accept"}
    assert gesehen["kopf"]["User-agent"] == f"Fakturafalter/{__version__}"
    assert gesehen["timeout"] <= 5


def test_ohne_netz_still(caplog):
    caplog.set_level(logging.DEBUG, logger="fakturafalter")
    assert updatepruefung.jetzt() == (False, None)  # konftest: kein Netz
    assert all(r.levelno <= logging.DEBUG for r in caplog.records)
    assert "Updateprüfung nicht möglich" in caplog.text


def test_im_hintergrund_blockiert_nicht(monkeypatch):
    los = threading.Event()

    def langsam(*a, **kw):
        los.wait(5)
        return REL

    monkeypatch.setattr(updatepruefung, "_abrufen", langsam)
    ergebnis = []
    fertig = threading.Event()
    t = updatepruefung.im_hintergrund(False, lambda e, n: (ergebnis.append((e, n)), fertig.set()))
    assert t.daemon and t.is_alive() and not ergebnis  # Aufrufer läuft sofort weiter
    los.set()
    assert fertig.wait(5)
    assert ergebnis[0][0] is True


def test_headless_nur_logzeile(monkeypatch, tmp_path, caplog):
    from fakturafalter import cli, ueberwachung

    aufrufe = []
    monkeypatch.setattr(
        updatepruefung, "im_hintergrund", lambda vorab=False, rueckruf=None: aufrufe.append(vorab)
    )
    monkeypatch.setattr(ueberwachung.Waechter, "starten", lambda self: None)
    (tmp_path / "k.yaml").write_text("arbeitsordner: R\n", encoding="utf-8")
    assert cli.main(["--config", str(tmp_path / "k.yaml"), "--headless"]) == 0
    assert aufrufe == [False]
    (tmp_path / "k.yaml").write_text(
        "arbeitsordner: R\noptionen: {updatepruefung: false}\n", encoding="utf-8"
    )
    assert cli.main(["--config", str(tmp_path / "k.yaml"), "--headless"]) == 0
    assert aufrufe == [False]


@pytest.mark.parametrize("an", [True, False])
def test_gui_start_und_einstellungen(qapp_gui, gui_konfig, monkeypatch, an):
    import yaml
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit

    from fakturafalter.gui import texte
    from fakturafalter.gui.einstellungen import Einstellungen
    from fakturafalter.gui.hauptfenster import Hauptfenster

    d = yaml.safe_load(gui_konfig.read_text(encoding="utf-8"))
    d.setdefault("optionen", {})["updatepruefung"] = an
    gui_konfig.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    aufrufe = []
    monkeypatch.setattr(
        updatepruefung,
        "im_hintergrund",
        lambda vorab=False, rueckruf=None: aufrufe.append((vorab, rueckruf)),
    )
    monkeypatch.setattr("fakturafalter.gui.hauptfenster.QTimer.singleShot", lambda ms, f: f())
    texte.sprache_setzen("de")
    w = Hauptfenster(gui_konfig, tray_erlaubt=False, auto_start=False)
    try:
        assert len(aufrufe) == (1 if an else 0)
        if an:
            neu = updatepruefung.Neu(
                "9.9.9", "https://github.com/deciderino/fakturafalter/releases/tag/v9.9.9"
            )
            w.update_ergebnis.emit(True, neu)
            qapp_gui.processEvents()
            titel = [x.text() for x in w.findChildren(QLabel)]
            assert any("Neue Version verfügbar: Fakturafalter 9.9.9" in t for t in titel)
        dlg = Einstellungen(w)
        assert dlg.findChild(QCheckBox, "updatepruefung").isChecked() is an
        assert dlg.findChild(QCheckBox, "updates_vorab").isChecked() is False
        assert dlg.findChild(QComboBox, "xrechnung_ablage").currentData() == "ausgang"
        assert dlg.findChild(QLineEdit, "protokoll_ordner").text() == ""
        dlg.findChild(QCheckBox, "updates_vorab").setChecked(True)
        dlg.b_update.click()
        assert aufrufe[-1][0] is True
        dlg.update_ergebnis.emit(False, None)
        qapp_gui.processEvents()
        assert "Keine Verbindung" in dlg.update_info.text()
        dlg.update_ergebnis.emit(True, None)
        qapp_gui.processEvents()
        assert "ist aktuell" in dlg.update_info.text()
        roh = dlg.ergebnis()
        assert roh["optionen"]["updatepruefung"] is an and roh["optionen"]["updates_vorab"] is True
        assert "xrechnung_ablage" not in roh["optionen"] and "protokoll_ordner" not in roh
        dlg.xr.setCurrentIndex(dlg.xr.findData("unterordner"))
        dlg.protokoll_ordner.setText(str(gui_konfig.parent / "P"))
        roh = dlg.ergebnis()
        assert (
            roh["optionen"]["xrechnung_ablage"] == "unterordner"
            and roh["optionen"]["xrechnung_zusatz"]
        )
        assert roh["protokoll_ordner"] == str(gui_konfig.parent / "P")
        dlg.c_xr.setChecked(False)
        assert dlg.ergebnis()["optionen"]["xrechnung_zusatz"] is False
        dlg.reject()
        dlg.deleteLater()
    finally:
        w.beenden()
        qapp_gui.processEvents()


@pytest.fixture
def qapp_gui():
    pytest.importorskip("PySide6")
    from fakturafalter.gui.app import anwendung

    return anwendung()


@pytest.fixture
def gui_konfig(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    import yaml

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    beispiele = Path(__file__).resolve().parent.parent / "beispiele"
    cfg = tmp_path / "cfg"
    shutil.copytree(beispiele, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {
        n: str(tmp_path / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")
    }
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return cfg / "konfiguration.yaml"
