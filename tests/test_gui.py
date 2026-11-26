# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Oberflächentests (offscreen). Laufen nur mit installiertem PySide6 (Extra „gui“)."""

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QCheckBox, QLabel  # noqa: E402

from fakturafalter import pipeline, validierung  # noqa: E402
from fakturafalter.gui import aktionen, autostart, daten, orte, texte  # noqa: E402
from fakturafalter.konfig import lade_konfig  # noqa: E402

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
GUI = Path(__file__).resolve().parent.parent / "src" / "fakturafalter" / "gui"
aktionen.NUR_MERKEN = True


@pytest.fixture(scope="session")
def qapp():
    from fakturafalter.gui.app import anwendung

    return anwendung()


@pytest.fixture
def konfig_datei(tmp_path):
    cfg = tmp_path / "cfg"
    shutil.copytree(BEISPIELE, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {
        n: str(tmp_path / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")
    }
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return cfg / "konfiguration.yaml"


@pytest.fixture
def fenster(qapp, konfig_datei, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    texte.sprache_setzen("de")
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(konfig_datei, tray_erlaubt=False)
    w.resize(900, 760)
    w.show()
    qapp.processEvents()
    yield w
    w.beenden()
    qapp.processEvents()
    texte.sprache_setzen("de")


def warten(qapp, bedingung, s=30.0):
    ende = time.time() + s
    while time.time() < ende:
        qapp.processEvents()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def pruef_fall_anlegen(k):
    """wie test_paarung: CSV-Menge für RE-2026-0102 geändert -> Prüffall."""
    k.eingang.mkdir(parents=True, exist_ok=True)
    csv = Path(shutil.copy(BEISPIELE / "variante-b_wawi_cp1252.csv", k.eingang))
    shutil.copy(BEISPIELE / "druckauftrag-wawi.pdf", k.eingang)
    t = (
        csv.read_bytes()
        .decode("cp1252")
        .replace(
            'P;RE-2026-0102;;;;;1;C-300;"Kabel NYM 3x1,5 mm²";50;',
            'P;RE-2026-0102;;;;;1;C-300;"Kabel NYM 3x1,5 mm²";60;',
        )
    )
    t = t.replace(";;;;;;;;207,66", ";;;;;;;;218,25")  # CSV in sich stimmig, weicht vom Druck ab
    csv.write_bytes(t.encode("cp1252"))
    return pipeline.verarbeiten(list(k.eingang.iterdir()), k)


def sichtbare_knoepfe(w):
    return [
        b
        for b in w.findChildren(QAbstractButton)
        if b.isVisibleTo(w) and not isinstance(b, QCheckBox)
    ]


# ------------------------------------------------------------------------------------ Hauptfenster
def test_hauptfenster_startet_aktiv_und_ziele_48px(fenster, qapp):
    assert fenster.zust == "aktiv"
    assert fenster.arbeiter.aktiv
    kn = sichtbare_knoepfe(fenster)
    assert kn
    zu_klein = [(b.text(), b.height()) for b in kn if b.height() < 48 or b.width() < 48]
    assert not zu_klein
    assert fenster.l_pruefmodul.text() in ("Prüfung: an", "Prüfung: Werkzeuge fehlen")


def test_pausieren_graut_jetzt_einlesen_aus(fenster, qapp):
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    assert not fenster.b_jetzt.isEnabled()
    assert fenster.b_pause.text() == "Überwachung aus" and not fenster.b_pause.isChecked()
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "aktiv")
    assert fenster.b_jetzt.isEnabled()


def test_jetzt_einlesen_verarbeitet_im_thread(fenster, qapp):
    k = fenster.k
    k.eingang.mkdir(parents=True, exist_ok=True)
    fenster.pause_umschalten()  # Wächter aus, damit nur „Jetzt einlesen“ greift
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", k.eingang)
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "aktiv")
    ergebnisse = []
    fenster.arbeiter.lauf_fertig.connect(lambda l: ergebnisse.append(l))
    fenster.jetzt_einlesen()
    assert warten(
        qapp, lambda: (k.protokoll / "protokoll.tsv").exists() and daten.heute_erstellt(k) >= 1, 60
    )
    assert warten(qapp, lambda: bool(ergebnisse))
    qapp.processEvents()
    assert list(k.ausgang.glob("*_zugferd.pdf"))
    assert not fenster.toasts.sichtbare()  # Erfolg: kein Toast …
    n = daten.heute_erstellt(k)
    assert fenster.l_heute.text() == f"Heute: {n} erstellt"  # … nur der Zähler steigt
    assert "RE-2026-" in fenster.l_zuletzt.text()
    assert fenster.nichts_zeile.isVisibleTo(fenster)


def test_hauptfenster_ohne_pfade_und_technik(fenster, qapp):
    k = fenster.k
    texte_ = " ".join(l_.text() for l_ in fenster.findChildren(QLabel) if l_.isVisibleTo(fenster))
    for pfad in (k.eingang, k.ausgang, k.pruefen, k.fehler):
        assert str(pfad) not in texte_
    for wort in ("CSV-Profil", "PDF-Vorlage", "Absender", "Ergebnis", "XRechnung"):
        assert wort not in texte_, wort


def test_pruefen_und_fehler_ein_toast_und_aufgaben(fenster, qapp):
    k = fenster.k
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    lauf = pruef_fall_anlegen(k)
    fenster._bei_lauf(lauf)
    (k.eingang / "kaputt.txt").write_text("unbekannt\n", encoding="utf-8")
    lauf2 = pipeline.verarbeiten([k.eingang / "kaputt.txt"], k)
    fenster._bei_lauf(lauf2)
    qapp.processEvents()
    toasts = fenster.toasts.sichtbare()
    assert len(toasts) == 1  # zusammengefasst, nicht gestapelt
    t = toasts[0]
    assert t.art == "fehler" and "1 zu prüfen" in t.titel.text() and "Fehler" in t.titel.text()
    assert fenster.pruef_zeile.isVisibleTo(fenster) and fenster.fehler_zeile.isVisibleTo(fenster)
    assert not fenster.nichts_zeile.isVisibleTo(fenster)
    assert fenster.l_pruef.text() == "1 Rechnung braucht deine Prüfung"
    assert fenster._tray_farbe() == fenster.c["err"]
    t.knopf.click()
    qapp.processEvents()
    assert fenster.pruef_fenster is not None and fenster.pruef_fenster.isVisible()
    assert fenster.pruef_fenster.reiter.currentIndex() == 0
    assert not fenster.toasts.sichtbare()


def test_toast_mit_schluessel_wird_aktualisiert(fenster, qapp):
    a = fenster.toast("info", "eins", schluessel="x")
    b = fenster.toast("info", "zwei", schluessel="x")
    assert a is b and a.titel.text() == "zwei" and len(fenster.toasts.sichtbare()) == 1
    fenster.toast("fehler", "drei", schluessel="x")
    qapp.processEvents()
    (t,) = fenster.toasts.sichtbare()
    assert t.art == "fehler" and t.titel.text() == "drei"


def test_toast_rueckgaengig_bei_verwerfen(fenster, qapp):
    k = fenster.k
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    pruef_fall_anlegen(k)
    fenster.aktualisieren()
    fenster.pruefansicht_oeffnen(0)
    pa = fenster.pruef_fenster
    assert pa.reiter.tabText(0) == "Zu prüfen (1)"
    (fall,) = daten.prueffaelle(k)
    assert fall.abweichungen and fall.abweichungen[0][0]
    pa.verwerfen(fall)
    assert not daten.prueffaelle(k)
    assert daten.fehlerberichte(k)
    t = pa.toasts.sichtbare()[-1]
    assert t.knopf is not None
    t.knopf.click()
    qapp.processEvents()
    assert len(daten.prueffaelle(k)) == 1
    assert not daten.fehlerberichte(k)


def test_prueffall_freigeben_erzeugt_rechnung(fenster, qapp):
    k = fenster.k
    fenster.pause_umschalten()
    assert warten(qapp, lambda: fenster.zust == "pausiert")
    pruef_fall_anlegen(k)
    fenster.pruefansicht_oeffnen(0)
    (fall,) = daten.prueffaelle(k)
    fenster.pruef_fenster.freigeben(fall)
    assert (k.ausgang / "RE-2026-0102_zugferd.pdf").exists()
    assert not daten.prueffaelle(k)
    assert not list(k.pruefen.iterdir())  # Quellen nach „Erledigt“, JSON gelöscht
    assert (k.erledigt / "druckauftrag-wawi.pdf").exists()
    assert daten.protokoll(k, 1)[0].nummer == "RE-2026-0102"


def test_sprache_und_thema_umschalten(fenster, qapp, konfig_datei):
    roh = json.loads(json.dumps(fenster.k.roh))
    roh.setdefault("oberflaeche", {}).update(sprache="en", thema="dunkel")
    assert fenster.einstellungen_uebernehmen(roh)
    assert fenster.b_pause.text() == "Monitoring on"
    from fakturafalter.gui import thema

    assert fenster.c == thema.farben(False) and fenster.ui["thema"] == "dunkel"
    gespeichert = yaml.safe_load(konfig_datei.read_text(encoding="utf-8"))
    assert gespeichert["oberflaeche"]["sprache"] == "en"
    assert (konfig_datei.parent / (konfig_datei.name + ".bak")).exists()
    qapp.processEvents()
    assert [b.text() for b in sichtbare_knoepfe(fenster) if b.height() < 48] == []


def test_fehlerhafte_einstellungen_werden_zurueckgerollt(fenster, qapp, konfig_datei):
    vorher = konfig_datei.read_text(encoding="utf-8")
    roh = json.loads(json.dumps(fenster.k.roh))
    roh["absender"] = "kein-block"
    assert not fenster.einstellungen_uebernehmen(roh)
    assert yaml.safe_load(konfig_datei.read_text(encoding="utf-8")) == yaml.safe_load(vorher)


def test_einrichtung_unvollstaendig_pausiert(fenster, qapp):
    roh = json.loads(json.dumps(fenster.k.roh))
    roh["absender"]["name"] = ""
    assert fenster.einstellungen_uebernehmen(roh)
    assert warten(qapp, lambda: fenster.zust == "einrichten")
    assert not fenster.b_jetzt.isEnabled()
    assert "Firma" in fenster.l_einricht.text()


# ------------------------------------------------------------------------------------ Einstellungen
def test_einstellungen_dialog(fenster, qapp):
    from fakturafalter.gui.einstellungen import Einstellungen

    d = Einstellungen(fenster)
    d.show()
    qapp.processEvents()
    np = d.findChild(QCheckBox, "nach_erstellung_pruefen")
    assert np.isEnabled() == validierung.bereit()
    assert np.isChecked() == validierung.bereit()  # Standard: an (sofern Werkzeuge da)
    assert not [
        c for c in d.findChildren(QCheckBox) if "Dienst" in c.text()
    ]  # Platzhalter entfernt (0.5.0)
    assert all(
        b.height() >= 48
        for b in d.findChildren(QAbstractButton)
        if b.isVisibleTo(d) and not isinstance(b, QCheckBox)
    )
    d.abs["iban"].setText("de02 1203 0000 0000 2020 51")
    d.sprache.setCurrentIndex(d.sprache.findData("en"))
    r = d.ergebnis()
    assert r["zahlung"]["iban"].startswith("DE02")
    assert r["oberflaeche"]["sprache"] == "en"
    assert r["ordner"] == fenster.k.roh["ordner"]  # unverändert -> Schreibweise bleibt
    assert d.autostart_gewuenscht() is None
    d.autostart.setChecked(True)
    assert d.autostart_gewuenscht() is True
    d.ordner["fehler"].setText(d.ordner["eingang"].text())
    d._speichern()
    assert d.fehler.isVisibleTo(d) and d.result() == 0
    d.reject()


# ------------------------------------------------------------------------------------ Autostart
def test_autostart_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    k = tmp_path / "mit leer zeichen" / "konfiguration.yaml"
    assert not autostart.ist_aktiv()
    autostart.setzen(True, k)
    t = autostart.desktop_datei().read_text(encoding="utf-8")
    assert autostart.ist_aktiv() and "--minimiert" in t and '"' + str(k) + '"' in t
    autostart.setzen(False)
    assert not autostart.ist_aktiv()


def test_autostart_windows_mit_falscher_registry(monkeypatch):
    class Schl:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class WR:
        HKEY_CURRENT_USER = KEY_READ = KEY_SET_VALUE = REG_SZ = 0
        werte = {}

        def OpenKey(self, *a):
            return Schl()

        def CreateKeyEx(self, *a):
            return Schl()

        def QueryValueEx(self, s, n):
            if n not in self.werte:
                raise FileNotFoundError
            return self.werte[n], 1

        def SetValueEx(self, s, n, _r, _t, v):
            self.werte[n] = v

        def DeleteValue(self, s, n):
            if n not in self.werte:
                raise FileNotFoundError
            del self.werte[n]

    wr = WR()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(autostart, "_winreg", lambda: wr)
    assert not autostart.ist_aktiv()
    autostart.setzen(True, Path("C:/Daten mit Leerzeichen/konfiguration.yaml"))
    assert autostart.ist_aktiv()
    assert '"' in wr.werte["Fakturafalter"] and "--minimiert" in wr.werte["Fakturafalter"]
    autostart.setzen(False)
    assert not autostart.ist_aktiv()


# ------------------------------------------------------------------------------------ Hilfsfunktionen
def test_erststart_und_konfig_ladbar(tmp_path):
    p = orte.erststart(tmp_path / "cfg", tmp_path / "Arbeit")
    k = lade_konfig(p)
    from fakturafalter import csv_standard

    assert k.pdf_vorlagen
    assert [p.get("profil") for p in k.csv_profile] == [csv_standard.PROFIL_ID]
    assert k.eingang.is_dir() and k.eingang.parent == tmp_path / "Arbeit"
    assert daten.absender_fehlt(k)  # Startkonfiguration: Absender leer -> Einrichtung nötig
    assert k.modus == "csv" and k.pdf_verwenden is False


def test_betrag_und_protokoll_alt(konfig_datei):
    assert daten.betrag("1249.5", "de") == "1.249,50 €"
    assert daten.betrag("1249.5", "en") == "€1,249.50"
    k = lade_konfig(konfig_datei)
    k.ausgang.mkdir(parents=True)
    k.protokoll.mkdir(parents=True, exist_ok=True)
    (k.protokoll / "protokoll.tsv").write_text(
        "2026-10-30T10:00:00\tok\tRE-1\ta.pdf\t\n"
        "2026-10-31T10:00:00\tok\tRE-2\tb.pdf\t\tMuster GmbH\t10.00\n",
        encoding="utf-8",
    )
    e = daten.protokoll(k)
    assert (
        [x.nummer for x in e] == ["RE-2", "RE-1"]
        and e[0].kunde == "Muster GmbH"
        and e[1].kunde == ""
    )


def test_konfig_speichern_behaelt_kommentare(tmp_path):
    p = tmp_path / "konfiguration.yaml"
    shutil.copy(BEISPIELE / "konfiguration.yaml", p)
    vorher = p.read_text(encoding="utf-8")
    d = yaml.safe_load(vorher)
    d["absender"]["name"] = "Neu GmbH"
    d["oberflaeche"] = {"thema": "dunkel"}
    orte.speichern(p, d)
    nachher = p.read_text(encoding="utf-8")
    assert yaml.safe_load(nachher) == d
    kommentare = [z.strip() for z in vorher.splitlines() if z.strip().startswith("#")]
    assert kommentare and all(c in nachher for c in kommentare)
    geaendert = [z for z in vorher.splitlines() if z not in nachher.splitlines()]
    assert geaendert == ["  name: Muster GmbH"]
    neu = tmp_path / "neu" / "konfiguration.yaml"  # neue Datei: Kommentare der Startvorlage
    neu.parent.mkdir()
    orte.speichern(neu, yaml.safe_load((orte.START / orte.KONFIG_NAME).read_text(encoding="utf-8")))
    assert neu.read_text(encoding="utf-8").startswith("#")
    vorlage = (orte.START / orte.KONFIG_NAME).read_text(encoding="utf-8")
    roh = yaml.safe_load(vorlage)
    roh["absender"]["name"] = "Beispiel AG"
    orte.speichern(neu, roh)
    text = neu.read_text(encoding="utf-8")
    assert [z for z in vorlage.splitlines() if "#" in z] == [
        z for z in text.splitlines() if "#" in z
    ]
    assert yaml.safe_load(text) == roh


def test_einzelinstanz_weckt_erste(qapp, tmp_path):
    from fakturafalter.gui.einzel import Einzelinstanz

    k = tmp_path / "konfiguration.yaml"
    erste = Einzelinstanz(k)
    assert not erste.andere_wecken(warte_ms=200)
    assert erste.lauschen()
    geweckt = []
    erste.geweckt.connect(geweckt.append)
    zweite = Einzelinstanz(k)
    assert zweite.name == erste.name
    assert zweite.andere_wecken()
    assert warten(qapp, lambda: geweckt == [True], 5)
    assert Einzelinstanz(tmp_path / "andere.yaml").name != erste.name
    erste.schliessen()
    assert not Einzelinstanz(k).andere_wecken(warte_ms=200)
    qapp.sendPostedEvents(
        None, QEvent.Type.DeferredDelete.value
    )  # Sockets jetzt abräumen, nicht im Folgetest
    qapp.processEvents()


def test_logdatei_enthaelt_technische_details(konfig_datei, tmp_path):
    from fakturafalter import logdatei

    datei = logdatei.einrichten(tmp_path / "logs")
    try:
        k = lade_konfig(konfig_datei)
        k.eingang.mkdir(parents=True, exist_ok=True)
        shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", k.eingang)
        pipeline.verarbeiten(list(k.eingang.iterdir()), k)
        text = datei.read_text(encoding="utf-8")
        assert "CSV-Profil" in text and "Rechnung RE-2026-" in text and "Verschoben:" in text
        assert "INFO: " in text  # Info-Hinweise (Feldquellen, Kontrollwerte)
    finally:
        logdatei.beenden()


def test_tray_symbol_mit_zahl(qapp):
    from fakturafalter.gui.bausteine import symbol

    a = symbol("#e53935", zahl=0).pixmap(64, 64).toImage()
    b = symbol("#e53935", zahl=3).pixmap(64, 64).toImage()
    assert not a.isNull() and a != b


def test_alle_texte_uebersetzt():
    gefunden = set(texte.DYNAMISCH)
    for p in GUI.glob("*.py"):
        for m in re.finditer(r'_\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)\)', p.read_text(encoding="utf-8")):
            gefunden.add(eval("(" + m.group(1) + ")"))  # noqa: S307 – nur String-Literale
    fehlt = sorted(gefunden - set(texte.EN))
    assert not fehlt, fehlt
    for de, en in texte.EN.items():
        assert set(re.findall(r"\{(\w+)\}", de)) == set(re.findall(r"\{(\w+)\}", en)), de


def test_einstellung_nach_erstellung_pruefen(fenster, qapp, monkeypatch):
    from fakturafalter.gui.einstellungen import Einstellungen

    monkeypatch.setattr(validierung, "bereit", lambda: True)
    monkeypatch.setattr(validierung, "werkzeug_versionen", lambda: "Mustang 2.26.0, KoSIT 1.6.3")
    d = Einstellungen(fenster)
    np = d.findChild(QCheckBox, "nach_erstellung_pruefen")
    assert np.isEnabled() and np.isChecked()
    np.setChecked(False)
    roh = d.ergebnis()
    d.reject()
    d.deleteLater()
    qapp.processEvents()
    assert roh["optionen"]["nach_erstellung_pruefen"] is False
    assert fenster.einstellungen_uebernehmen(roh)
    assert fenster.k.nachpruefen is False
    assert fenster.l_pruefmodul.text() == "Prüfung: aus" and not fenster.l_pruefmodul.isEnabled()
    roh["optionen"]["nach_erstellung_pruefen"] = True
    assert fenster.einstellungen_uebernehmen(roh)
    assert fenster.l_pruefmodul.text() == "Prüfung: an" and fenster.l_pruefmodul.isEnabled()
