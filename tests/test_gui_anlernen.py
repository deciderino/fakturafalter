# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Oberflächentests (offscreen) für Anlern-Assistent, Ersteinrichtung und die neuen Einstellungen."""

import os
import shutil
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pypdfium2")

from fakturafalter import anlernen  # noqa: E402
from fakturafalter.gui import aktionen, orte, texte  # noqa: E402
from fakturafalter.konfig import lade_konfig  # noqa: E402

IND = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"
aktionen.NUR_MERKEN = True


@pytest.fixture(scope="session")
def qapp():
    from fakturafalter.gui.app import anwendung

    return anwendung()


@pytest.fixture
def nur_pdf(tmp_path):
    """Konfiguration „Nur PDF“ ohne Vorlage, Arbeitsordner im tmp."""
    roh = yaml.safe_load((IND / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    pfad = tmp_path / "konfiguration.yaml"
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    return pfad


@pytest.fixture
def fenster(qapp, nur_pdf, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    texte.sprache_setzen("de")
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(nur_pdf, tray_erlaubt=False, auto_start=False)
    w.resize(900, 760)
    w.show()
    qapp.processEvents()
    yield w
    w.beenden()
    qapp.processEvents()


def test_assistent_lernt_und_erzeugt(qapp, fenster):
    from fakturafalter.gui.anlernen import AnlernAssistent

    k = fenster.k
    pdfs = anlernen.in_warteschlange(k, sorted((IND / "eingang").glob("*.pdf"))[:2])
    assert all(p.parent == k.anlernen for p in pdfs)
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    qapp.processEvents()
    for _n in range(2):
        assert d.s is not None
        for f in list(d.s.fehlende()):
            d._passt(f)
        d.schritt_setzen(3)
        qapp.processEvents()
        assert d.s.fertig(), d.s.fehlende()
        assert d.b_speichern.isEnabled()
        d.speichern()
        qapp.processEvents()
    assert d.gespeichert == 2
    assert d.result() == 1
    neu = lade_konfig(fenster.konfig_pfad)
    assert len(neu.pdf_profile) == 1  # zweite PDF hat die Vorlage wiedererkannt
    assert len(list(neu.ausgang.glob("*.pdf"))) == 2
    assert not anlernen.warteschlange(neu)


@pytest.mark.parametrize("breite", [1280, 700])
def test_vorschau_zeigt_alle_positionen(qapp, fenster, breite):
    """Die Vorschau-Tabelle ist so hoch, dass keine Zeile unter Kopf, Rahmen oder Bildlaufleiste verschwindet –
    auch im schmalen Fenster, in dem die waagrechte Leiste erscheint (früher feste +44 px)."""
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    d.resize(breite, 800)
    qapp.processEvents()
    d.schritt_setzen(3)
    qapp.processEvents()
    v = d.vorschau
    assert v.rowCount() == 6
    unten = max(v.visualRect(v.model().index(r, 0)).bottom() for r in range(v.rowCount()))
    assert unten < v.viewport().height(), (
        unten,
        v.viewport().height(),
        v.horizontalScrollBar().isVisible(),
    )
    d.reject()


def test_zu_tun_zeigt_warteschlange(qapp, fenster):
    anlernen.in_warteschlange(fenster.k, [next((IND / "eingang").glob("*.pdf"))])
    fenster.aktualisieren()
    assert fenster.anlern_zeile.isVisibleTo(fenster)
    assert "1 Rechnung" in fenster.l_anlern.text()
    assert not fenster.einricht_zeile.isVisibleTo(
        fenster
    )  # „Nur PDF“ braucht keinen gemeinsamen Absender


def test_ersteinrichtung(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    pfad = orte.erststart(tmp_path / "cfg", tmp_path / "arbeit")
    from fakturafalter.gui.einrichtung import Einrichtung
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(pfad, tray_erlaubt=False, auto_start=False)
    try:
        assert w.einrichtung_fehlt()
        e = Einrichtung(w)
        e.show()
        e.arbeitsordner.setText(str(tmp_path / "neu"))
        e._weiter()
        assert e.i == 1 and w.k.arbeitsordner == tmp_path / "neu"
        assert e.abs_form.pdf_uebernehmen(next((IND / "eingang").glob("*.pdf")))
        assert e.abs_form.felder["name"].text() == "Normteile Brückner GmbH"
        e._weiter()
        assert e.i == 2 and e.modus_code() == "csv"
        assert e.b_weiter.text() == texte._("Weiter")
        from PySide6.QtWidgets import QLabel, QRadioButton

        assert [b.property("code") for b in e.modus.buttons()] == ["csv", "xml", "nur_pdf"]
        r_np = e.findChild(QRadioButton, "modus_nur_pdf")
        assert r_np.minimumHeight() >= 48
        assert any(
            wgt.text() == texte._("nicht empfohlen")
            for wgt in e.findChildren(QLabel)
        )
        r_np.setChecked(True)
        assert e.b_weiter.text() == texte._("Ohne Anlernen weiter")
        e.findChild(QRadioButton, "modus_csv").setChecked(True)
        assert e.b_weiter.text() == texte._("Weiter")
        e._weiter()
        assert e.i == 3
        e._weiter()
        roh = orte.lesen(pfad)
        assert roh["modus"] == "csv"
        assert (roh.get("optionen") or {}).get("pdf_verwenden") is False
        assert roh["oberflaeche"]["eingerichtet"] is True
        assert roh["absender"]["name"] == "Normteile Brückner GmbH"
        assert not w.einrichtung_fehlt()
    finally:
        w.beenden()
        qapp.processEvents()


def test_einstellungen_bereiche_und_ordner(qapp, fenster):
    from fakturafalter.gui.einstellungen import Einstellungen

    d = Einstellungen(fenster)
    d.show()
    d.resize(900, 700)
    qapp.processEvents()
    assert d.nav.isVisible() and not d.auswahl.isVisible()
    d.resize(560, 700)  # große Skalierung: Auswahl oben statt Liste links
    qapp.processEvents()
    assert not d.nav.isVisible() and d.auswahl.isVisible()
    d.auswahl.setCurrentIndex(2)
    assert d.stapel.currentIndex() == 2 and d.nav.currentRow() == 2
    assert not d.einzeln.isChecked() and not d.ordner["eingang"].isEnabled()
    d.arbeitsordner.setText("/tmp/x/arbeit")
    assert d.ordner["eingang"].text() == str(Path("/tmp/x/arbeit") / "Eingang")
    r = d.ergebnis()
    assert r["arbeitsordner"] == "/tmp/x/arbeit" and "ordner" not in r
    d.einzeln.setChecked(True)
    d.ordner["ausgang"].setText("/tmp/netz/ausgang")
    r = d.ergebnis()
    assert r["ordner"]["ausgang"] == "/tmp/netz/ausgang"
    d.reject()


def test_einstellungen_alte_konfig_einzeln(qapp, fenster, tmp_path):
    """Alte Konfiguration mit einzelnen Ordnern: bleibt einzeln, nichts geht verloren."""
    roh = orte.lesen(fenster.konfig_pfad)
    roh["ordner"] = {
        s: str(tmp_path / f"alt_{s}")
        for s in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")
    }
    assert fenster.einstellungen_uebernehmen(roh)
    from fakturafalter.gui.einstellungen import Einstellungen

    d = Einstellungen(fenster)
    assert d.einzeln.isChecked()
    assert d.ordner["fehler"].text() == str(tmp_path / "alt_fehler")
    assert d.ergebnis()["ordner"]["fehler"] == str(tmp_path / "alt_fehler")
    d.reject()


def test_einstellungen_vorlagenkarte(qapp, fenster):
    """Karte je Vorlage: Fortschritt, „Automatisch, ohne Nachfrage“ erst bei sicherer Vorlage."""
    from PySide6.QtWidgets import QCheckBox

    from fakturafalter.gui.einstellungen import Einstellungen

    k = fenster.k
    pdfs = anlernen.in_warteschlange(k, [next((IND / "eingang").glob("*.pdf"))])
    s = anlernen.Sitzung(pdfs[0], k)
    for f in list(s.fehlende()):
        s.bestaetigen(f)
    erg, v = s.speichern(fenster.konfig_pfad)
    assert v is not None, erg.hinweise
    fenster.einstellungen_uebernehmen(orte.lesen(fenster.konfig_pfad))
    d = Einstellungen(fenster, 2)
    auto = [c for c in d.findChildren(QCheckBox) if c.objectName().startswith("auto_")]
    assert len(auto) == 1 and not auto[0].isEnabled()
    d.reject()


def test_absender_csv_import(qapp, fenster, tmp_path):
    from fakturafalter.gui.absender_form import AbsenderFormular

    meldungen = []
    f = AbsenderFormular({}, lambda *a: meldungen.append(a))
    assert f.csv_importieren(IND / "absender-normteile.csv")
    assert f.felder["iban"].text() and f.felder["name"].text()
    kaputt = tmp_path / "x.csv"
    kaputt.write_bytes(b"\x00\x01")
    assert not f.csv_importieren(kaputt)
    assert meldungen[-1][0] == "fehler"


def test_bekannten_absender_waehlen(qapp, fenster):
    from fakturafalter.gui.anlernen import AnlernAssistent

    k = fenster.k
    pdfs = anlernen.in_warteschlange(k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    qapp.processEvents()
    assert not d.cb_profil.isEnabled()  # noch kein Profil: ausgegraut
    assert d.cb_profil.minimumHeight() >= 48
    d.reject()
    k.pdf_profile.append(
        {
            "name": "Beispiel Werkzeugbau GmbH",
            "_datei": str(k.basis / "profil-beispiel.yaml"),
            "verkaeufer": {
                "name": "Beispiel Werkzeugbau GmbH",
                "anschrift": {"strasse": "Musterweg 1", "plz": "12345", "ort": "Musterstadt"},
                "ust_id": "DE123456789",
            },
            "zahlung": {"iban": "DE89370400440532013000"},
        }
    )
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    qapp.processEvents()
    assert d.cb_profil.isEnabled() and d.cb_profil.count() == 2
    d.cb_profil.setCurrentIndex(1)
    d._profil_gewaehlt(1)
    assert d.s.profil is k.pdf_profile[-1]
    assert d.abs_zeilen["name"].e.text() == "Beispiel Werkzeugbau GmbH"
    d._profil_gewaehlt(0)
    assert d.s.profil is None and d.abs_zeilen["name"].e.text() == "Normteile Brückner GmbH"
    d.reject()


def test_bereich_ziehen_knopf(qapp, fenster):
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    d.schritt_setzen(2)
    qapp.processEvents()
    z = d.zeilen["BT-13"]
    assert z.b_bereich.isVisible() and z.b_bereich.width() >= 48 and z.b_bereich.height() >= 48
    z.b_bereich.click()
    assert d.ziel == ("bereich", "BT-13") and d.pdf.seite.modus == "rahmen"
    d.pdf.seite.rahmen_gezogen.emit(505, 172, 550, 186)
    qapp.processEvents()
    assert d.ziel is None and z.e.text() == "B-4500" and d.s.werte["BT-13"].bereich
    d.reject()


def test_anschrift_als_block(qapp, fenster):
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    d.schritt_setzen(2)
    qapp.processEvents()
    b = d.b_anschrift
    assert b.isVisible() and b.height() >= 48 and "BT-51" in d.zeilen
    b.click()
    assert d.ziel == ("block", "kaeufer") and d.pdf.seite.modus == "block"
    assert (
        d.pdf.b_banner_ok.isVisible() and not d.pdf.b_banner_ok.isEnabled()
    )  # erst nach einer Zeile
    d.pdf.seite.rahmen_gezogen.emit(45, 138, 260, 178)
    qapp.processEvents()
    assert d.ziel is None and d.zeilen["BT-52"].e.text() == "Lüdenscheid"
    assert d.zeilen["BT-50"].e.text() == "Talsperrenweg 3"
    # Strg+Klick auf Zeilen, dann „Übernehmen“
    b.click()
    zs = [z for z in d.s.zeilen if z.seite == 0 and 140 <= z.top <= 172 and z.woerter[0].x0 < 60]
    for z in zs:
        d.pdf.seite.wort_geklickt.emit("", z.abschnitte[0])
    d.pdf.seite.wort_geklickt.emit(
        "", zs[0].abschnitte[0]
    )  # zweiter Klick nimmt die Zeile wieder weg
    assert len(d._block_ws) == len(zs) - 1 and d.pdf.b_banner_ok.isEnabled()
    d.pdf.b_banner_ok.click()
    qapp.processEvents()
    assert d.ziel is None and d.zeilen["BT-52"].e.text() == "Lüdenscheid"
    # ohne erste Zeile: von unten gelesen bleibt die Straße Straße, der Name fehlt (statt Straße als Name)
    assert d.zeilen["BT-50"].e.text() == "Talsperrenweg 3" and d.zeilen["BT-44"].e.text() == ""
    d.reject()


def test_spaltenlinie_ziehen_und_vorschau_spalten(qapp, fenster):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QHeaderView

    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    qapp.processEvents()
    d.schritt_setzen(3)
    qapp.processEvents()
    hh = d.vorschau.horizontalHeader()
    assert hh.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive and hh.stretchLastSection()
    seite, t = d.pdf.seite, d.s.tabelle
    i = t.spalten.index("BT-130")
    alt = t.grenzen[i]
    z = seite.zoom
    y = (t.top + t.bottom) / 2 * z + 1

    def maus(art, x):
        ev = QMouseEvent(
            art,
            QPointF(x * z + 1, y),
            QPointF(x * z + 1, y),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        {
            QMouseEvent.Type.MouseButtonPress: seite.mousePressEvent,
            QMouseEvent.Type.MouseMove: seite.mouseMoveEvent,
            QMouseEvent.Type.MouseButtonRelease: seite.mouseReleaseEvent,
        }[art](ev)

    maus(QMouseEvent.Type.MouseButtonPress, alt)
    assert seite._grenze == (i, alt)
    maus(QMouseEvent.Type.MouseMove, t.grenzen[i - 1] + 4)
    maus(QMouseEvent.Type.MouseButtonRelease, t.grenzen[i - 1] + 4)
    assert t.grenzen[i] < alt and t.spalten[i] == "BT-129"
    assert d._spalten_combos[i].currentData() == "BT-129"  # Auswahlfelder folgen
    d.s.grenze_setzen(i, alt)
    d._tabelle_anzeigen()
    assert t.spalten[i] == "BT-130" and d.s.summenpruefung()[2]
    d.reject()


def test_vorschau_passt_ohne_bildlauf_und_banner_ganz_lesbar(qapp, fenster):
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.resize(1280, 900)
    d.show()
    d.schritt_setzen(2)
    for _ in range(5):
        qapp.processEvents()
    d.b_anschrift.click()
    for _ in range(5):
        qapp.processEvents()
    lb = d.pdf.l_banner
    assert lb.height() >= lb.heightForWidth(lb.width())  # umgebrochener Text nicht abgeschnitten
    d._ziel_setzen(None)
    d.schritt_setzen(3)
    for _ in range(5):
        qapp.processEvents()
    hh = d.vorschau.horizontalHeader()
    assert sum(hh.sectionSize(i) for i in range(5)) <= d.vorschau.viewport().width()
    d.reject()


def _maus(seite, art, x, y):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    z = seite.zoom
    p = QPointF(x * z + 1, y * z + 1)
    ev = QMouseEvent(
        art,
        p,
        p,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    {
        QMouseEvent.Type.MouseButtonPress: seite.mousePressEvent,
        QMouseEvent.Type.MouseMove: seite.mouseMoveEvent,
        QMouseEvent.Type.MouseButtonRelease: seite.mouseReleaseEvent,
    }[art](ev)


def _ziehen(seite, a, b):
    from PySide6.QtGui import QMouseEvent

    _maus(seite, QMouseEvent.Type.MouseButtonPress, *a)
    _maus(seite, QMouseEvent.Type.MouseMove, *b)
    _maus(seite, QMouseEvent.Type.MouseButtonRelease, *b)


@pytest.mark.parametrize("sprache", ["de", "en"])
def test_spalten_als_rahmen_im_assistenten(qapp, fenster, tmp_path, sprache):
    """Fiktiver ERP-Druck: Spalte hinzufügen -> Linien werden Rahmen (Zuordnung bleibt), neuen Rahmen ziehen,
    Bedeutung wählen, Rahmen verbreitern und entfernen; Vorschau folgt live, Knöpfe 48 px, Diagnose ohne Text."""
    from PySide6.QtWidgets import QApplication, QComboBox

    from fakturafalter.gui.anlernen import AnlernAssistent

    from . import erp_roh

    texte.sprache_setzen(sprache)
    pdf = erp_roh.rechnung(
        tmp_path / "erp.pdf", zeilen=[erp_roh.trenn("-")] + erp_roh.STANDARD, vektorlinie=True
    )
    pdfs = anlernen.in_warteschlange(fenster.k, [pdf])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.resize(1280, 900)
    d.show()
    d.schritt_setzen(3)
    qapp.processEvents()
    s, seite = d.s, d.pdf.seite
    assert len(s.positionen()) == 3 and d.vorschau.rowCount() == 3
    for b in (d.b_spalte_neu, d.b_tabelle_neu, d.b_diagnose):
        assert b.minimumHeight() >= 48 and b.isEnabled()
    alt = [c for c in s.tabelle.spalten if c != "ignorieren"]
    d.b_spalte_neu.click()
    qapp.processEvents()
    assert (
        seite.modus == "spalte" and [r[0] for r in s.tabelle.spaltenrahmen] == alt
    )  # nichts verschwindet
    assert len(d._spalten_zeilen) == len(alt)
    t = s.tabelle
    # Einheit ignorieren -> Rahmen bleibt, Status grau
    i_me = [r[0] for r in t.spaltenrahmen].index("BT-130")
    d._spaltenrahmen_bedeutung(i_me, "ignorieren")
    assert t.spaltenrahmen[i_me][0] == "ignorieren" and d._spalten_zeilen[i_me][1].zustand == "aus"
    # Betragsspalte schmal neu ziehen ersetzt die alte
    kopf = next(z for z in s.zeilen if z.text.startswith("Menge"))
    b = next(w for w in kopf.woerter if w.t == "Betrag")
    _ziehen(seite, (b.x0 - 3, kopf.top - 2), (b.x1 + 40, t.bottom - 1))
    qapp.processEvents()
    codes = [r[0] for r in t.spaltenrahmen]
    assert codes.count("gesamt") == 1 and len(s.positionen()) == 3
    # rechte Kante des Betrags mit der Maus verbreitern
    i_g = codes.index("gesamt")
    x1 = t.spaltenrahmen[i_g][2]
    y = (t.top + t.bottom) / 2
    _ziehen(seite, (x1, y), (x1 + 8, y))
    assert t.spaltenrahmen[i_g][2] == pytest.approx(min(x1 + 8, t.x1), abs=0.6)
    # am Etikett über der Tabelle verschieben (die Fläche bleibt frei für neue Rahmen)
    a0, b0 = t.spaltenrahmen[i_g][1:]
    yt = t.top - 8 / seite.zoom
    _ziehen(seite, ((a0 + b0) / 2, yt), ((a0 + b0) / 2 - 2, yt))
    nachbar = t.spaltenrahmen[i_g - 1][2]
    assert t.spaltenrahmen[i_g][1] == pytest.approx(
        max(a0 - 2, nachbar + 1), abs=0.6
    )  # nie in den Nachbarn
    assert t.spaltenrahmen[i_g][2] - t.spaltenrahmen[i_g][1] == pytest.approx(b0 - a0, abs=0.6)
    assert len(s.positionen()) == 3
    # Menge entfernen -> Betrag trägt, Menge = 1 bzw. Betrag ÷ Preis
    zeile = d._spalten_zeilen[codes.index("BT-129")]
    zeile[3].click()
    qapp.processEvents()
    assert "BT-129" not in t.codes() and d.vorschau.rowCount() == 3
    assert all(
        isinstance(z[0], QComboBox) and z[0].minimumSizeHint().height() > 0
        for z in d._spalten_zeilen
    )
    # Diagnose in die Zwischenablage, ohne Rechnungstext
    d.b_diagnose.click()
    qapp.processEvents()
    text = QApplication.clipboard().text()
    assert text.startswith("Fakturafalter") and "Spaltenrahmen" in text
    for geheim in ("Werkzeugbau", "Sechskantschraube", "1.088,50", "26000042", "Musterstadt"):
        assert geheim not in text
    # Tabellenrahmen neu ziehen: Spaltenrahmen bleiben
    d.b_tabelle_neu.click()
    assert seite.modus == "rahmen"
    _ziehen(seite, (t.x0 - 2, t.top), (t.x1 + 2, t.bottom))
    assert t.spaltenrahmen and len(s.positionen()) == 3
    seite.grab()  # malt ohne Fehler
    d.reject()
    texte.sprache_setzen("de")


def test_auswahl_dreht_beim_scrollen_nicht_mit(qapp):
    """0.4.3+hotfix1: Mausrad über „Preis gilt für“ beim Scrollen der Seite stellte still auf 1000 um."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from fakturafalter.gui.anlernen import PREISEINHEIT, Auswahl

    cb = Auswahl()
    for code, name in PREISEINHEIT:
        cb.addItem(name, code)
    gewaehlt = []
    cb.activated.connect(lambda _i: gewaehlt.append(cb.currentData()))
    cb.show()
    qapp.processEvents()

    def rad():
        ev = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(cb, ev)
        return ev.isAccepted()

    cb.clearFocus()
    assert not rad() and not rad()  # nicht fokussiert: Ereignis geht an die Seite (scrollt)
    assert cb.currentData() == "1" and not gewaehlt
    cb.setFocus()
    qapp.processEvents()
    if cb.hasFocus():  # offscreen bekommt nicht jedes Fenster den Fokus
        rad()
        assert cb.currentData() == "100"
    cb.close()


def test_hotfix2_ansicht_haelt_pdf_nicht_offen(qapp, fenster, monkeypatch):
    """pdfium bekommt die Bytes, nicht den Pfad – sonst sperrt Windows das Verschieben nach „Erledigt“."""
    import pypdfium2

    from fakturafalter.gui.anlernen import AnlernAssistent

    args = []
    echt = pypdfium2.PdfDocument

    def doc(quelle, *a, **kw):
        args.append(quelle)
        return echt(quelle, *a, **kw)

    monkeypatch.setattr(pypdfium2, "PdfDocument", doc)
    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    assert args and all(isinstance(a, bytes) for a in args)
    d.reject()


def test_hotfix2_fehlertoast_zeigt_den_grund_nicht_die_info(qapp, fenster, monkeypatch):
    from fakturafalter import pipeline
    from fakturafalter.gui.anlernen import AnlernAssistent

    k = fenster.k
    k.nachpruefen = False
    pdfs = anlernen.in_warteschlange(k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    for f in list(d.s.fehlende()):
        d._passt(f)
    k.ausgang.mkdir(parents=True, exist_ok=True)
    nr = d.s.rechnung().nummer
    (k.ausgang / "protokoll.tsv").write_text(
        f"2026-11-01 10:00:00\tok\t{nr}\t\t\t\t\t\n", encoding="utf-8"
    )
    (k.ausgang / pipeline.ausgabe_namen(nr)[0]).write_bytes(b"%PDF")
    gezeigt = []
    monkeypatch.setattr(
        d, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d.speichern()
    ((art, titel, detail),) = gezeigt
    assert art == "fehler" and "schon einmal erzeugt" in detail and "Kontrollwert" not in detail
    d.reject()


def test_hotfix2_weiter_mit_nachgereichter_pdf(qapp, fenster, monkeypatch):
    """Nach dem Speichern der letzten gewählten PDF macht der Assistent mit inzwischen eingetroffenen weiter."""
    from fakturafalter.gui.anlernen import AnlernAssistent

    k = fenster.k
    k.nachpruefen = False
    pdfs = anlernen.in_warteschlange(k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    for f in list(d.s.fehlende()):
        d._passt(f)
    anlernen.in_warteschlange(
        k, [IND / "eingang" / "NB-26-1002.pdf"]
    )  # kommt während des Anlernens
    gezeigt = []
    monkeypatch.setattr(
        d, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d.speichern()
    qapp.processEvents()
    assert d.s is not None and d.s.pfad.name == "NB-26-1002.pdf" and d.result() == 0
    assert gezeigt[-1][0] == "ok" and "nächsten PDF (2 von 2)" in gezeigt[-1][2]
    d.reject()


def test_hotfix2_keine_weitere_pdf_sagt_was_zu_tun_ist(qapp, fenster, monkeypatch):
    from fakturafalter.gui.anlernen import AnlernAssistent

    k = fenster.k
    k.nachpruefen = False
    pdfs = anlernen.in_warteschlange(k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    for f in list(d.s.fehlende()):
        d._passt(f)
    gezeigt = []
    monkeypatch.setattr(
        fenster, "toast", lambda art, titel, detail="", *a, **kw: gezeigt.append((art, detail))
    )
    d.speichern()
    assert d.result() == 1
    assert gezeigt and gezeigt[-1][0] == "ok" and "Eingang" in gezeigt[-1][1]


def test_neuer_rahmen_ueber_vorhandenen_und_folgeseite(qapp, fenster, tmp_path):
    """Beim Aufziehen eines Rahmens fängt eine vorhandene Spaltenlinie den Zug nicht ab (senkrecht weiter =
    neuer Rahmen); vorhandene Marken werden blass. Der Tabellenrahmen erscheint auch auf Seite 2."""
    from fakturafalter.gui.anlernen import PdfSeite

    from . import erp_roh

    pdf = erp_roh.rechnung_mehrseitig(
        tmp_path / "zwei.pdf", [erp_roh.STANDARD[:2], erp_roh.STANDARD[2:]]
    )
    s = anlernen.Sitzung(pdf, fenster.k)
    seite = PdfSeite(fenster.c)
    seite.laden(s)
    seite.rahmen_zeigen = True
    seite.modus_setzen("rahmen")
    t = s.tabelle
    assert not t.leer() and len(t.grenzen) > 1 and not t.spaltenrahmen
    gezogen = []
    seite.rahmen_gezogen.connect(lambda *r: gezogen.append(r))
    linie = []
    seite.grenze_gezogen.connect(lambda *g: linie.append(g))
    x, alt = t.grenzen[1], list(t.grenzen)
    y = (t.top + t.bottom) / 2
    from PySide6.QtGui import QMouseEvent

    _maus(seite, QMouseEvent.Type.MouseButtonPress, x, y)
    _maus(seite, QMouseEvent.Type.MouseMove, x + 60, y + 40)
    assert seite.zieht()  # aus dem Linienzug wurde ein neuer Rahmen
    seite.grab()  # malt blass ohne Fehler
    _maus(seite, QMouseEvent.Type.MouseButtonRelease, x + 60, y + 40)
    assert gezogen and gezogen[0][0] == pytest.approx(x, abs=1) and t.grenzen == alt
    # waagerecht bleibt es Linie verschieben
    _ziehen(seite, (x, y), (x - 3, y))
    assert (
        len(gezogen) == 1
        and linie
        and linie[0][0] == 1
        and linie[0][1] == pytest.approx(x - 3, abs=0.6)
    )
    seite.seite = 1
    assert seite.tabellen_bereich() is not None
    seite.grab()
    seite.schliessen()


def test_etikett_verdeckt_keinen_text(qapp):
    from PySide6.QtCore import QRectF

    from fakturafalter.gui.anlernen import PdfSeite

    r = QRectF(100, 100, 80, 16)
    wort_drueber = QRectF(90, 80, 200, 12)  # Zeile direkt darüber
    tag = PdfSeite._etikett_platz(r, 40, [r], [QRectF(103, 104, 74, 10), wort_drueber])
    assert (
        tag is not None
        and not tag.intersects(wort_drueber)
        and not tag.intersects(QRectF(103, 104, 74, 10))
    )
    assert abs(tag.center().y() - r.bottom()) < 8  # auf dem unteren Rand statt über dem Text


def _rad(qapp, ziel, pos, delta, strg=True):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    mod = Qt.KeyboardModifier.ControlModifier if strg else Qt.KeyboardModifier.NoModifier
    ev = QWheelEvent(
        QPointF(pos),
        QPointF(ziel.mapToGlobal(pos.toPoint())),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        mod,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    qapp.sendEvent(ziel, ev)
    qapp.processEvents()


def test_pdf_zoom_mit_strg_rad_zur_maus_und_doppelklick(qapp, fenster):
    """0.4.4: Strg+Mausrad zoomt zur Mausposition (der Punkt unter der Maus bleibt stehen), das Rad allein
    scrollt, Doppelklick auf eine leere Stelle passt die Seite ein; ein Rahmen, der gerade gezogen wird, bleibt
    beim Zoomen an seiner Stelle auf der Seite."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    d.resize(1100, 800)
    qapp.processEvents()
    b, seite = d.pdf, d.pdf.seite
    vp = b.scroll.viewport()
    z0 = seite.zoom
    anker = QPointF(vp.width() * 0.7, vp.height() * 0.4)
    vorher = seite._in_pt(QPointF(seite.mapFrom(vp, anker.toPoint())))
    _rad(qapp, vp, anker, 240)  # zwei Rasten = 1,44×
    assert seite.zoom == pytest.approx(min(3.0, z0 * 1.44), rel=1e-3)
    nachher = seite._in_pt(QPointF(seite.mapFrom(vp, anker.toPoint())))
    assert nachher == pytest.approx(vorher, abs=2.0)  # PDF-Punkt unter der Maus bleibt
    # Rad allein: kein Zoom
    z1 = seite.zoom
    _rad(qapp, vp, anker, -120, strg=False)
    assert seite.zoom == z1
    # Rahmen ziehen und dabei zoomen: Startpunkt bleibt auf derselben Stelle der Seite
    seite.modus_setzen("rahmen")
    start = QPointF(100, 120)
    seite._zug = (start, QPointF(200, 220))
    start_pt = seite._in_pt(start)
    _rad(qapp, vp, anker, -120)
    assert seite._in_pt(seite._zug[0]) == pytest.approx(start_pt, abs=0.5)
    seite._zug = None
    # Rad über der Seite selbst (nicht dem grauen Rand) kommt ebenfalls an
    z2 = seite.zoom
    _rad(qapp, seite, QPointF(50, 50), 120)
    assert seite.zoom == pytest.approx(min(3.0, z2 * 1.2), rel=1e-3)
    # Doppelklick auf eine leere Stelle (oben links, Rand): einpassen
    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(3, 3),
        QPointF(seite.mapToGlobal(QPointF(3, 3))),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    qapp.sendEvent(seite, ev)
    qapp.processEvents()
    assert b._eingepasst
    d.reject()


def test_ort_befund_fehlender_ordner_nicht_als_fehler(tmp_path):
    """0.4.4: „Pruefen\\Anlernen“ gibt es vor der ersten Anlern-Rechnung noch nicht – das Log meldete
    irreführend „NICHT beschreibbar“."""
    from fakturafalter.gui.app import _ort_befund

    assert _ort_befund(tmp_path) == "beschreibbar"
    befund = _ort_befund(tmp_path / "Pruefen" / "Anlernen")
    assert "noch nicht angelegt" in befund and "NICHT" not in befund


# ---------------------------------------------------------------- Schritt „Bereiche festlegen“ (0.4.5)
@pytest.mark.parametrize("sprache", ["de", "en"])
def test_bereiche_festlegen_schritt(qapp, fenster, monkeypatch, tmp_path, sprache):
    from fakturafalter.gui.anlernen import S_BEREICHE, S_DATEN, AnlernAssistent

    from . import test_bereiche as tb

    texte.sprache_setzen(sprache)
    fenster.k.ordner_anlegen()
    pdf = tb._zwei_seiten(fenster.k)
    pdfs = anlernen.in_warteschlange(fenster.k, [pdf])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    gezeigt = []
    monkeypatch.setattr(
        d, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d.resize(1280, 900)
    d.show()
    qapp.processEvents()
    assert d.schritt == S_BEREICHE  # ohne Bereiche beginnt der Assistent hier
    ui = d.zonen_ui
    assert set(ui) == {"anschrift", "kopf", "tabelle", "summen", "zahlung"}
    for z in ui.values():
        assert z["knopf"].minimumHeight() >= 48 and z["vorschlag"].minimumHeight() >= 48
        assert z["status"].text() == "○" and not z["weg"].isEnabled()
    assert not ui["tabelle"]["gilt"].isVisible() and ui["summen"]["gilt"].isVisible()
    if sprache == "en":
        assert ui["summen"]["knopf"].text() == "Totals" and d.b_weiter.text() == "Next ▶"

    # Summen: anklicken, auf Seite 2 blättern, Rahmen ziehen – vorhandene Rahmen fangen nichts ab
    ui["summen"]["knopf"].click()
    assert d.ziel == ("zone", "summen") and d.pdf.seite.modus == "rahmen"
    d.pdf.zeige_seite(1)
    seite = d.pdf.seite
    from PySide6.QtCore import QPointF

    for x, y in ((310, 140), (400, 330), (60, 100)):
        p = QPointF(x * seite.zoom, y * seite.zoom)
        assert seite._spaltenrahmen_an(p) is None and seite._grenze_an(p) is None
    seite.rahmen_gezogen.emit(*tb.SUMMEN)
    qapp.processEvents()
    assert d.ziel is None and d.s.zonen["summen"]["rahmen"] == list(tb.SUMMEN)
    assert ui["summen"]["status"].text() == "✔" and ui["summen"]["weg"].isEnabled()
    assert d.s.werte["BT-109"].wert == "1.271,00"
    art, titel, detail = gezeigt[-1]
    assert art == "ok" and titel == texte._("Bereich gesetzt: {name}").format(
        name=texte._("Summen")
    )
    assert any(
        et for et, _r, _a, seiten in seite.zonen if 1 in seiten
    )  # Rahmen sichtbar auf Seite 2

    # Vorschlag übernehmen (Anschrift) und „Gilt auf“
    assert ui["kopf"]["vorschlag"].isEnabled()
    ui["kopf"]["vorschlag"].click()
    qapp.processEvents()
    assert "kopf" in d.s.zonen and d.s.werte["BT-1"].wert == "26000042"
    assert gezeigt[-1][1] == texte._("Vorschlag übernommen: {name}").format(
        name=d._zone_name("kopf")
    )
    g = ui["summen"]["gilt"]
    g.setCurrentIndex(g.findData("letzte"))
    qapp.processEvents()
    assert d.s.zonen["summen"]["seiten"] == "letzte" and d.s.werte["BT-109"].wert == "1.271,00"

    # Entfernen und weiter
    ui["summen"]["weg"].click()
    qapp.processEvents()
    assert "summen" not in d.s.zonen and ui["summen"]["status"].text() == "○"
    d.b_weiter.click()
    qapp.processEvents()
    assert d.schritt > S_BEREICHE
    d.schritt_setzen(S_DATEN)
    qapp.processEvents()
    assert not seite.zonen  # Bereiche nur im ersten Schritt
    d.reject()
    texte.sprache_setzen("de")


def test_bereiche_aendern_zaehlt_als_korrektur(qapp, fenster, monkeypatch):
    from fakturafalter.gui.anlernen import S_BEREICHE, AnlernAssistent

    from . import test_bereiche as tb

    k = fenster.k
    k.pfad_datei = fenster.konfig_pfad
    k.ordner_anlegen()
    s = anlernen.Sitzung(tb._zwei_seiten(k), k)
    tb._alle_bereiche(s)
    tb._speichern(k, s)
    pdfs = anlernen.in_warteschlange(k, [tb._zwei_seiten(k, "m2", "26000043")])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    gezeigt = []
    monkeypatch.setattr(
        d, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d.show()
    qapp.processEvents()
    assert d.s.vorlage is not None and d.schritt != S_BEREICHE  # Bereiche vorhanden: gleich weiter
    d2 = AnlernAssistent(
        fenster,
        k,
        fenster.konfig_pfad,
        anlernen.in_warteschlange(k, [tb._zwei_seiten(k, "m3", "26000044")]),
        fenster.c,
        bereiche_zuerst=True,
    )
    monkeypatch.setattr(
        d2, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d2.show()
    qapp.processEvents()
    assert d2.schritt == S_BEREICHE and d2.zonen_ui["summen"]["status"].text() == "✔"
    d2.zonen_ui["summen"]["knopf"].click()
    d2.pdf.zeige_seite(1)
    d2.pdf.seite.rahmen_gezogen.emit(290, 130, 560, 180)
    qapp.processEvents()
    assert "Korrektur" in gezeigt[-1][2] and "Summen" in gezeigt[-1][2]
    d2.reject()
    d.reject()


def test_einstellungen_bereiche_bearbeiten(qapp, fenster, monkeypatch):
    """Vorlagenkarte: „Bereiche bearbeiten…“ öffnet den Assistenten mit dem Schritt „Bereiche festlegen“;
    „Weiter anlernen“ wie bisher."""
    from PySide6.QtWidgets import QFileDialog, QPushButton

    from fakturafalter.gui.einstellungen import Einstellungen

    k = fenster.k
    pdfs = anlernen.in_warteschlange(k, [next((IND / "eingang").glob("*.pdf"))])
    s = anlernen.Sitzung(pdfs[0], k)
    for f in list(s.fehlende()):
        s.bestaetigen(f)
    erg, v = s.speichern(fenster.konfig_pfad)
    assert v is not None, erg.hinweise
    fenster.einstellungen_uebernehmen(orte.lesen(fenster.konfig_pfad))
    aufrufe = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **kw: (["/tmp/x.pdf"], ""))
    )
    monkeypatch.setattr(
        fenster, "anlernen_oeffnen", lambda dateien=None, eltern=None, **kw: aufrufe.append(kw)
    )
    d = Einstellungen(fenster, 2)
    knoepfe = {b.text(): b for b in d.findChildren(QPushButton)}
    b = knoepfe[texte._("Bereiche bearbeiten…")]
    assert b.minimumHeight() >= 48 and b.toolTip()
    b.click()
    knoepfe[texte._("Weiter anlernen")].click()
    assert aufrufe == [{"bereiche": True}, {}]
    d.reject()


# ---------------------------------------------------------------- Robustheit (0.4.6)
def test_summenrahmen_ueber_tabellenrahmen_ziehen(qapp, fenster, monkeypatch):
    """Im Schritt „Bereiche festlegen“ lässt sich ein Rahmen über einen vorhandenen ziehen: der Zug im
    Tabellenrahmen (auch auf einer Spaltenlinie) wird ein neuer Summenrahmen, die Tabelle bleibt."""
    from PySide6.QtGui import QMouseEvent

    from fakturafalter.gui.anlernen import S_BEREICHE, AnlernAssistent

    from . import test_robustheit as tr

    k = fenster.k
    k.ordner_anlegen()
    pdfs = anlernen.in_warteschlange(k, [tr._direkt(k)])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    gezeigt = []
    monkeypatch.setattr(
        d, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d.resize(1280, 900)
    d.show()
    qapp.processEvents()
    assert d.schritt == S_BEREICHE
    t = d.s.tabelle
    d.zonen_ui["tabelle"]["vorschlag"].click()
    qapp.processEvents()
    assert "tabelle" in d.s.zonen
    d.zonen_ui["summen"]["knopf"].click()
    seite = d.pdf.seite
    assert d.ziel == ("zone", "summen") and seite.modus == "rahmen"
    x = t.grenzen[-1]  # Start auf der Spaltenlinie vor „Gesamt“
    _maus(seite, QMouseEvent.Type.MouseButtonPress, x, t.bottom - 20)
    _maus(seite, QMouseEvent.Type.MouseMove, 560, t.bottom + 45)
    _maus(seite, QMouseEvent.Type.MouseButtonRelease, 560, t.bottom + 45)
    qapp.processEvents()
    assert "summen" in d.s.zonen and "tabelle" in d.s.zonen
    assert d.s.zonen["summen"]["rahmen"][1] < d.s.zonen["tabelle"]["rahmen"][3]  # überlappt
    assert d.s.werte["BT-109"].wert == "1.271,50" and d.s.werte["BT-112"].wert == "1.513,09"
    assert [p.gesamt for p in d.s.positionen()] == [g for _, _, g in tr.SOLL_POS]
    assert gezeigt and gezeigt[-1][0] == "ok"
    d.reject()


@pytest.mark.parametrize("sprache", ["de", "en"])
def test_selbstkontrolle_nach_speichern_toast_und_markierung(qapp, fenster, monkeypatch, sprache):
    from fakturafalter.gui.anlernen import AnlernAssistent

    from . import test_robustheit as tr

    texte.sprache_setzen(sprache)
    k = fenster.k
    k.ordner_anlegen()
    pdfs = anlernen.in_warteschlange(k, [tr._direkt(k, "a1"), tr._direkt(k, "a2")])
    d = AnlernAssistent(fenster, k, fenster.konfig_pfad, pdfs, fenster.c)
    gezeigt = []
    monkeypatch.setattr(
        d, "toast", lambda art, titel, detail="", **kw: gezeigt.append((art, titel, detail))
    )
    d.show()
    qapp.processEvents()
    echt = anlernen.Sitzung._aus_vorlage

    def anders(self, feld):
        r = echt(self, feld)
        return ("99999999", r[1]) if feld == "BT-1" and r else r

    monkeypatch.setattr(anlernen.Sitzung, "_aus_vorlage", anders)
    d.s.absender = anlernen.Sitzung(
        shutil.copy(IND / "eingang" / "NB-26-1001.pdf", k.eingang), k
    ).absender
    if d.s.werte["leistung"].status == "fehlt":
        d.s.setzen("leistung", "05.10.2026")
    for f in list(d.s.fehlende()):
        d._passt(f)
    d.schritt_setzen(3)
    qapp.processEvents()
    assert d.s.fertig(), d.s.fehlende()
    d.speichern()
    qapp.processEvents()
    monkeypatch.setattr(anlernen.Sitzung, "_aus_vorlage", echt)
    art, _titel, detail = next(
        g for g in gezeigt if "Selbstkontrolle" in g[2] or "Self-check" in g[2]
    )
    assert art == "info"
    erwartet = texte._(
        "Selbstkontrolle: Mit der neuen Vorlage anders gelesen: {felder}. Die Felder sind bei der "
        "nächsten PDF markiert – Details im Log."
    ).format(felder=texte._(anlernen.FELDER["BT-1"][0]))
    assert erwartet in detail
    assert d.s is not None and d.s.pfad.name.startswith("a2")  # nächste PDF: Feld markiert
    assert d.s.werte["BT-1"].status == "pruefen" and "Selbstkontrolle" in d.s.werte["BT-1"].hinweis
    d.reject()
    texte.sprache_setzen("de")


def test_gutschrift_sektion_rahmen_und_hinweis(qapp, fenster):
    """Sektion Gutschrift: BT-3 und BT-25 mit Rahmen-Knopf (48 px) und Hinweis über belegart_hinweis()."""
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    d.schritt_setzen(2)
    qapp.processEvents()
    assert "BT-3" in d.zeilen and "BT-25" in d.zeilen
    z3, z25 = d.zeilen["BT-3"], d.zeilen["BT-25"]
    assert "Belegart" in z3.l_name.text() and "Ursprungsrechnung" in z25.l_name.text()
    for z in (z3, z25):
        assert z.b_bereich.isVisible() and z.b_bereich.width() >= 48 and z.b_bereich.height() >= 48
    z3.b_bereich.click()
    assert d.ziel == ("bereich", "BT-3") and d.pdf.seite.modus == "rahmen"
    d._ziel_setzen(None)
    z25.b_bereich.click()
    assert d.ziel == ("bereich", "BT-25") and d.pdf.seite.modus == "rahmen"
    d._ziel_setzen(None)

    d._feld_text("BT-3", "Gutschrift")
    qapp.processEvents()
    assert d.s.belegart() == "381"
    assert "Gutschrift erkannt (Belegart 381)." in z3.l_hilfe.text()
    assert "Ursprungsrechnung" in z3.l_hilfe.text()
    assert z25.l_hilfe.isVisible() and "Ursprungsrechnung" in z25.l_hilfe.text()

    d._feld_text("BT-25", "NB-26-0990")
    qapp.processEvents()
    assert "Gutschrift erkannt (Belegart 381)." in z3.l_hilfe.text()
    assert "ohne Bezug" not in z3.l_hilfe.text()
    assert "ohne Bezug" not in z25.l_hilfe.text()

    d._feld_text("BT-3", "Rechnung")
    qapp.processEvents()
    assert d.s.belegart() == "380"
    assert "Rechnung (Belegart 380)." in z3.l_hilfe.text()
    d.reject()


def test_kontrolle_positionen_hinweis_im_assistenten(qapp, fenster):
    """Ohne Feldzeile für Positionen: Hinweis an der Sektion, wenn positionen in kontrolle_offen steht."""
    from fakturafalter.gui.anlernen import S_POSITIONEN, AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    qapp.processEvents()
    assert d.s is not None
    d.s.kontrolle_offen = ["positionen"]
    d.schritt_setzen(S_POSITIONEN)
    qapp.processEvents()
    assert d.l_kontrolle_pos.isVisibleTo(d)
    assert "Positionen" in d.l_kontrolle_pos.text()
    d.s.kontrolle_offen = []
    d._kontrolle_positionen_anzeigen()
    qapp.processEvents()
    assert not d.l_kontrolle_pos.isVisibleTo(d)
    d.reject()


def test_kontrolle_bestaetigen_knopf_in_pruefansicht(qapp, fenster):
    """Prüfansicht: Knopf nur bei offener Selbstkontrolle, 48 px, bestätigt per Toast und trägt aus."""
    import json

    from PySide6.QtWidgets import QPushButton

    from fakturafalter import pdferkennung

    k = fenster.k
    k.ordner_anlegen()
    prof = {"name": "Muster GmbH", "_basis": str(k.basis)}
    k.pdf_profile.append(prof)
    v = {
        "profil": "Muster GmbH",
        "kennung": "a1b2c3d4",
        "kontrolle_offen": ["BT-1", "positionen"],
        "felder": {},
    }
    pdferkennung.vorlage_speichern(v, prof)
    hinweis = (
        "Selbstkontrolle offen: Die Vorlage Muster GmbH-a1b2c3d4 hat Rechnungsnummer nach dem letzten Anlernen "
        "anders gelesen als bestätigt – bitte prüfen. Bestätigt ist es, sobald eine angelernte PDF dieses "
        "Absenders das Feld wieder richtig liest."
    )
    fall = {
        "nummer": "RE-2026-0042",
        "profil": "Muster GmbH",
        "kaeufer": {"name": "Beispiel Werkzeugbau GmbH"},
        "summen": {"brutto": "1271.50"},
        "herkunft": {
            "BT-1": {"quelle": "pdf-angelernt:Muster GmbH-a1b2c3d4 S.1", "sicherheit": 0.95}
        },
        "hinweise": [{"stufe": "pruefen", "feld": "BT-1", "text": hinweis}],
    }
    k.pruefen.mkdir(parents=True, exist_ok=True)
    (k.pruefen / "RE-2026-0042.json").write_text(json.dumps(fall), encoding="utf-8")

    fenster.pruefansicht_oeffnen(0)
    pa = fenster.pruef_fenster
    qapp.processEvents()
    btn = pa.findChild(QPushButton, "kontrolle_bestaetigen")
    assert btn is not None and btn.isVisibleTo(pa)
    assert btn.text() == "Felder bestätigen"
    assert btn.minimumHeight() >= 48 and btn.height() >= 48
    from PySide6.QtWidgets import QLabel

    texte_karte = " ".join(w.text() for w in pa.findChildren(QLabel))
    assert "Selbstkontrolle offen" in texte_karte and "Rechnungsnummer" in texte_karte

    btn.click()
    qapp.processEvents()
    assert "kontrolle_offen" not in pdferkennung.vorlagen_laden(prof)[0]
    assert pa.findChild(QPushButton, "kontrolle_bestaetigen") is None
    toasts = pa.toasts.sichtbare()
    assert toasts and toasts[-1].titel.text() == "Felder bestätigt"
    assert "Muster GmbH-a1b2c3d4" in (toasts[-1].detail.text() if toasts[-1].detail else "")


def test_adresszusatz_felder_im_assistenten(qapp, fenster):
    """Kontaktstelle und Adresszeile 3 sind korrigierbar und bleiben, wenn Name oder Zusatz geändert werden."""
    from fakturafalter.gui.anlernen import AnlernAssistent

    pdfs = anlernen.in_warteschlange(fenster.k, [IND / "eingang" / "NB-26-1001.pdf"])
    d = AnlernAssistent(fenster, fenster.k, fenster.konfig_pfad, pdfs, fenster.c)
    d.show()
    d.schritt_setzen(2)
    qapp.processEvents()
    assert "BT-56" in d.zeilen and "BT-163" in d.zeilen
    assert "Kontaktstelle" in d.zeilen["BT-56"].l_name.text()
    assert "Adresszeile 3" in d.zeilen["BT-163"].l_name.text()
    for z in (d.zeilen["BT-56"], d.zeilen["BT-163"]):
        assert z.b_ziel.isVisible() and z.b_ziel.width() >= 48 and z.b_ziel.height() >= 48
    d.s.setzen("BT-163", "Gebäude C")
    d.s.setzen("BT-56", "Frau Muster")
    d._feld_anzeigen("BT-163")
    d._feld_anzeigen("BT-56")
    d.s.setzen("BT-44", "Beispiel Werkzeugbau GmbH")
    d.s.setzen("BT-51", "")
    d._feld_anzeigen("BT-44")
    d._feld_anzeigen("BT-51")
    d._feld_anzeigen("BT-163")
    d._feld_anzeigen("BT-56")
    qapp.processEvents()
    assert d.zeilen["BT-163"].e.text() == "Gebäude C"
    assert d.zeilen["BT-56"].e.text() == "Frau Muster"
    r = d.s.rechnung()
    assert r.kaeufer.anschrift.zeile3 == "Gebäude C"
    assert r.kaeufer.kontakt_name == "Frau Muster"
    d.reject()
