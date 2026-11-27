# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Layouteditor offscreen: Bausteine, Schloss, Verschieben, eigene Felder, Ebenen, Briefpapier, Einstellungen."""

import os
import shutil
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QCheckBox  # noqa: E402

from fakturafalter import layout, validierung  # noqa: E402
from fakturafalter.gui import texte  # noqa: E402

BSP = Path(__file__).resolve().parent.parent / "beispiele"


@pytest.fixture(scope="session")
def qapp():
    from fakturafalter.gui.app import anwendung

    return anwendung()


@pytest.fixture
def editor(qapp, tmp_path):
    from fakturafalter.gui import thema
    from fakturafalter.gui.layouteditor import LayoutEditor

    texte.sprache_setzen("de")
    c = thema.anwenden(qapp, "hell")
    w = LayoutEditor(None, c, None, tmp_path, profil="Musterwerk GmbH")
    w.resize(1400, 900)
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _item(w, art):
    return next(i for i in w._items if i.e.art == art)


def test_editor_aufbau_schloss_und_klickziele(editor, qapp):
    w = editor
    namen = [w.liste.item(i).text() for i in range(w.liste.count())]
    assert (
        namen[:4] == ["Logo", "Absender", "Empfängeranschrift", "Rechnungskopf"]
        and "Fußzeile" in namen
    )
    for i in range(w.liste.count()):
        it = w.liste.item(i)
        pflicht = it.text() in (  # rc2: Absender und Fußzeile ohne Schloss (ausblendbar)
            "Empfängeranschrift",
            "Rechnungskopf",
            "Positionstabelle",
            "Summenblock",
        )
        assert bool(it.flags() & Qt.ItemFlag.ItemIsUserCheckable) is not pflicht, it.text()
    assert all(
        b.height() >= 48
        for b in w.findChildren(QAbstractButton)
        if b.isVisibleTo(w) and not isinstance(b, QCheckBox)
    )
    assert not w.blatt.pixmap().isNull()  # Vorschau aus dem echten Renderer
    w.waehlen(w.seite.bausteine["summen"])
    assert not w.sichtbar.isEnabled() and "§ 14" in w.e_hinweis.text()


def test_verschieben_einrasten_und_vorschau(editor, qapp):
    w = editor
    e = w.seite.bausteine["empfaenger"]
    it = _item(w, "empfaenger")
    it.setPos(117.3 * 4, 61.9 * 4)  # Maus: Raster 5 mm
    assert (e.x, e.y) == (115, 60)
    w.waehlen(e)
    w.spins["breite"].setValue(72)
    assert e.breite == 72 and it.rect().width() == 72 * 4
    w.b_raster.click()  # Raster aus: frei
    it.setPos(116.2 * 4, 61.9 * 4)
    assert abs(e.x - 116.2) < 0.05
    alt = w.blatt.pixmap().cacheKey()
    w.neu_zeichnen()
    assert w.blatt.pixmap().cacheKey() != alt


def test_ueberlappung_blockiert_speichern(editor, qapp):
    w = editor
    w.waehlen(w.seite.bausteine["summen"])
    w.spins["y"].setValue(w.seite.bausteine["positionen"].y + 10)
    assert _item(w, "summen").fehler and "überlappen" in w.status.text()
    w.speichern()
    assert not w.result() and w.isVisible()


def test_eigene_felder_ebenen_loeschen(editor, qapp, tmp_path):
    w = editor
    w.feld_hinzufuegen("text")
    t = w.seite.felder[-1]
    assert t.art == "text" and w.element() is t
    w.text.setPlainText("Grüße aus dem Test")
    assert t.text == "Grüße aus dem Test"
    frei = lambda: [
        x.art
        for x in sorted((x for x in w.seite.elemente() if not x.oben), key=lambda x: x.ebene)
    ]
    assert frei()[-1] == "text"
    w.ebene(-1)
    assert frei()[-2] == "text"
    w.ebene(+1)
    w.ebene(+1)  # schon ganz vorn: Toast, keine Änderung
    assert frei()[-1] == "text"
    z = [i.e.art for i in sorted(w._items, key=lambda i: i.zValue())]
    assert set(z[-len(layout.OBEN) :]) == layout.OBEN  # Absender, Fußzeile, Pflicht bleiben oben
    from PIL import Image

    Image.new("RGB", (60, 30), (200, 30, 30)).save(tmp_path / "siegel.png")
    w._bild_dialog = lambda: tmp_path / "siegel.png"
    w.feld_hinzufuegen("bild")
    b = w.seite.felder[-1]
    assert b.art == "bild" and (tmp_path / b.datei).exists() and b.datei.startswith("layout/")
    w.waehlen(t)
    w.feld_loeschen()
    assert t not in w.seite.felder
    w.speichern()
    assert w.result()
    d = w.ergebnis()
    assert [f["art"] for f in d["seite1"]["felder"]] == ["bild"]
    assert (
        layout.laden(yaml.safe_load(yaml.safe_dump(d)), tmp_path).seite1.felder[0].datei == b.datei
    )


def test_ausblenden_und_zuruecksetzen(editor, qapp):
    w = editor
    logo = next(w.liste.item(i) for i in range(w.liste.count()) if w.liste.item(i).text() == "Logo")
    logo.setCheckState(Qt.CheckState.Unchecked)
    assert w.seite.bausteine["logo"].sichtbar is False
    assert w.ergebnis()["seite1"]["bausteine"]["logo"]["sichtbar"] is False
    w.zuruecksetzen()
    assert w.ergebnis() is None and w.b_eigen.isVisibleTo(w)
    assert not any(i.isVisible() for i in w._items)
    w._eigen_anlegen()
    assert w.ergebnis() is not None


def test_folgeseite(editor, qapp):
    w = editor
    w.b_sf.click()
    assert w.seite_name == "folgeseite" and "empfaenger" not in [i.e.art for i in w._items]
    assert "Folgeseite" in w.seiten_info.text()


def test_briefpapier_tauglich_und_umgewandelt(editor, qapp, tmp_path, monkeypatch):
    w = editor
    monkeypatch.setattr(validierung, "bereit", lambda: False)
    w.briefpapier_laden(BSP / "layout" / "briefpapier-seite1.pdf")
    assert w.seite.briefpapier.endswith(".pdf") and (tmp_path / w.seite.briefpapier).exists()
    from tests.test_layout import _cmyk_briefpapier

    w.b_sf.click()
    w.briefpapier_laden(_cmyk_briefpapier(tmp_path / "cmyk.pdf"))
    assert w.seite.briefpapier.endswith(".jpg")  # sauber als sRGB-Bild übernommen
    assert w.vorlage.seite1.briefpapier.endswith(".pdf")  # Seite 1 getrennt
    (tmp_path / "kaputt.pdf").write_bytes(b"kein pdf")
    vorher = w.seite.briefpapier
    w.briefpapier_laden(tmp_path / "kaputt.pdf")
    assert w.seite.briefpapier == vorher  # abgelehnt
    assert any(t.art == "fehler" for t in w.toasts.sichtbare())


@pytest.mark.validierung
@pytest.mark.skipif(
    not all(validierung.verfuegbar().values()), reason="Java/KoSIT/Mustang nicht vorhanden"
)
def test_briefpapier_mit_verapdf_geprueft(editor, qapp):
    editor.briefpapier_laden(BSP / "layout" / "briefpapier-seite1.pdf", warten=True)
    qapp.processEvents()
    assert editor.seite.briefpapier.endswith(".pdf")
    assert "PDF/A-tauglich" in editor.brief_status.text()


def test_englisch(qapp, tmp_path):
    from fakturafalter.gui import thema
    from fakturafalter.gui.layouteditor import LayoutEditor

    texte.sprache_setzen("en")
    try:
        w = LayoutEditor(
            None, thema.anwenden(qapp, "hell"), None, tmp_path, profil="Musterwerk GmbH"
        )
        namen = [w.liste.item(i).text() for i in range(w.liste.count())]
        assert "Recipient address" in namen and w.b_speichern.text() == "Save"
        w.close()
    finally:
        texte.sprache_setzen("de")


# ---------------------------------------------------------------- aus den Einstellungen
@pytest.fixture
def fenster(qapp, tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    shutil.copytree(BSP, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {
        n: str(tmp_path / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")
    }
    d["absender_profile"] = [
        {"absender": {"name": "Zweitfirma KG"}, "zahlung": {"iban": "DE02120300000000202051"}}
    ]
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    texte.sprache_setzen("de")
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(cfg / "konfiguration.yaml", tray_erlaubt=False)
    w.show()
    qapp.processEvents()
    yield w
    w.beenden()
    qapp.processEvents()


def test_einstellungen_layout_je_absender(fenster, qapp, monkeypatch):
    from fakturafalter.gui import layouteditor
    from fakturafalter.gui.einstellungen import Einstellungen

    d = Einstellungen(fenster, "Absender")
    d.show()
    qapp.processEvents()
    assert (
        d.b_layout.isVisibleTo(d)
        and d.b_layout.height() >= 48
        and "Standardlayout" in d.layout_info.text()
    )
    gesehen = []

    def exec_(self):
        gesehen.append(self.profil)
        self.seite.bausteine["logo"].x = 25
        return 1

    monkeypatch.setattr(layouteditor.LayoutEditor, "exec", exec_)
    d.b_layout.click()
    assert gesehen == ["Muster GmbH"] and "Eigenes Layout" in d.layout_info.text()
    r = d.ergebnis()
    assert r["layout"]["seite1"]["bausteine"]["logo"]["x"] == 25
    assert "layout" not in r["absender_profile"][0]
    d._absender_wechseln(1)  # zweites Profil: eigenes (leeres) Layout
    assert "Standardlayout" in d.layout_info.text()
    monkeypatch.setattr(
        layouteditor.LayoutEditor, "exec", lambda self: (setattr(self, "eigen", False), 1)[1]
    )
    d.b_layout.click()
    r = d.ergebnis()
    assert "layout" not in r  # aktiv ist jetzt die Zweitfirma ohne Layout
    muster = next(p for p in r["absender_profile"] if p["absender"]["name"] == "Muster GmbH")
    assert muster["layout"]["seite1"]["bausteine"]["logo"]["x"] == 25
    assert fenster.einstellungen_uebernehmen(r)  # speichert und lädt die Konfiguration
    assert fenster.k.roh["absender_profile"][0]["layout"]["seite1"]["bausteine"]["logo"]["x"] == 25
