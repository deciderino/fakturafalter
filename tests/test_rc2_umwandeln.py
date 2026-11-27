# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""rc2: Umwandeln von Hand („Umwandeln …“, Ziehen ins Fenster) – gleiche Strecke wie der Eingang,
Originale bleiben unangetastet (fiktive Beispieldaten)."""

import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fakturafalter.ueberwachung import Waechter, manuell_sammeln  # noqa: E402

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_sammeln_ordner_und_gegenstueck(konfig, tmp_path):
    quelle = tmp_path / "export"
    quelle.mkdir()
    shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", quelle / "RE-1.csv")
    shutil.copy(BEISPIELE / "druckauftrag-wawi.pdf", quelle / "RE-1.pdf")
    (quelle / "brief.docx").write_bytes(b"PK\x03\x04")
    (quelle / "notiz.odt").write_bytes(b"PK\x03\x04")
    (quelle / "halb.tmp").write_text("x")
    (quelle / ".versteckt.csv").write_text("x")
    (quelle / "unter").mkdir()
    (quelle / "unter" / "tief.csv").write_text("x")
    assert konfig.pdf_als_gegenstueck()
    a = manuell_sammeln([quelle], konfig)
    assert sorted(p.name for p in a.dateien) == ["RE-1.csv", "RE-1.pdf"]
    assert {p.name for p, _g in a.uebersprungen} == {"brief.docx", "notiz.odt"}
    assert all("nicht unterstützt" in g for _p, g in a.uebersprungen)
    # nur die CSV gewählt: gleichnamige PDF kommt dazu (Sichtteil wie gewohnt)
    b = manuell_sammeln([quelle / "RE-1.csv"], konfig)
    assert sorted(p.name for p in b.dateien) == ["RE-1.csv", "RE-1.pdf"]
    # doppelt gewählt zählt einmal
    c = manuell_sammeln([quelle / "RE-1.csv", quelle, quelle / "RE-1.pdf"], konfig)
    assert len(c.dateien) == 2
    # ohne PDF-Verwendung: keine PDF
    konfig.pdf_verwenden = False
    konfig.modus = "csv"
    d = manuell_sammeln([quelle], konfig)
    assert [p.name for p in d.dateien] == ["RE-1.csv"]
    assert any(p.name == "RE-1.pdf" and "passt nicht" in g for p, g in d.uebersprungen)
    e = manuell_sammeln([tmp_path / "gibt-es-nicht.csv"], konfig)
    assert not e.dateien and e.uebersprungen[0][1] == "nicht gefunden"


def test_nur_pdf_nimmt_nur_pdf(konfig, tmp_path):
    konfig.modus = "nur_pdf"
    q = tmp_path / "q"
    q.mkdir()
    (q / "a.pdf").write_bytes((BEISPIELE / "druckauftrag-wawi.pdf").read_bytes())
    (q / "b.csv").write_text("x")
    a = manuell_sammeln([q], konfig)
    assert [p.name for p in a.dateien] == ["a.pdf"]


def test_manuell_originale_bleiben_ergebnis_im_ausgang(konfig, tmp_path):
    quelle = tmp_path / "irgendwo"
    quelle.mkdir()
    csv = Path(shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", quelle))
    vorher = (_hash(csv), csv.stat().st_mtime)
    temp_vorher = set(Path(tempfile.gettempdir()).glob("fakturafalter-umwandeln-*"))
    laeufe = []
    w = Waechter(konfig, bei_lauf=laeufe.append)
    auswahl = manuell_sammeln([quelle], konfig)
    lauf = w.manuell(auswahl.dateien)
    assert lauf is not None and laeufe == [lauf]
    assert lauf.ergebnisse and all(e.status == "ok" for e in lauf.ergebnisse), [
        (e.nummer, e.status, e.hinweise) for e in lauf.ergebnisse
    ]
    assert list(konfig.ausgang.glob("*_zugferd.pdf"))
    # Original unverändert am alten Platz, die Kopie liegt in Erledigt (wie aus dem Eingang)
    assert csv.exists() and (_hash(csv), csv.stat().st_mtime) == vorher
    assert (konfig.erledigt / csv.name).exists()
    assert not any(konfig.eingang.iterdir())
    # Arbeitsordner wieder weg
    assert set(Path(tempfile.gettempdir()).glob("fakturafalter-umwandeln-*")) <= temp_vorher


def test_manuell_prueffall_mit_kopie(konfig, tmp_path):
    """Prüffall: die Kopie wandert nach „Zu prüfen“, das Original bleibt – Freigeben fasst es nicht an."""
    from fakturafalter import pipeline

    quelle = tmp_path / "q"
    quelle.mkdir()
    csv = Path(shutil.copy(BEISPIELE / "variante-b_wawi_cp1252.csv", quelle))
    pdf = Path(shutil.copy(BEISPIELE / "druckauftrag-wawi.pdf", quelle))
    t = csv.read_bytes().decode("cp1252").replace(
        "P;RE-2026-0102;;;;;;;;;;;;;;1;C-300;Kabel NYM 3x1,5 mm²;50;",
        "P;RE-2026-0102;;;;;;;;;;;;;;1;C-300;Kabel NYM 3x1,5 mm²;60;",
    ).replace(";;;;;;;;207,66", ";;;;;;;;218,25")
    csv.write_bytes(t.encode("cp1252"))
    vorher = {p: _hash(p) for p in (csv, pdf)}
    lauf = Waechter(konfig).manuell(manuell_sammeln([csv, pdf], konfig).dateien)
    pr = [e for e in lauf.ergebnisse if e.status == "pruefen"]
    assert pr, [(e.nummer, e.status) for e in lauf.ergebnisse]
    json_pfad = konfig.pruefen / f"{pipeline.sicherer_name(pr[0].nummer)}.json"
    assert json_pfad.exists()
    assert str(quelle) not in json_pfad.read_text(encoding="utf-8")  # zeigt auf die Kopie
    assert {p: _hash(p) for p in (csv, pdf)} == vorher


def test_gleichnamige_aus_zwei_ordnern(konfig, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", a / "export.csv")
    shutil.copy(BEISPIELE / "variante-k_kundenbezeichnung_erp.csv", b / "export.csv")
    lauf = Waechter(konfig).manuell(manuell_sammeln([a, b], konfig).dateien)
    assert lauf is not None
    assert len({str(Path(q).name) for e in lauf.ergebnisse for q in e.quellen}) >= 1
    assert (a / "export.csv").exists() and (b / "export.csv").exists()
    assert len(list(konfig.erledigt.iterdir())) + len(list(konfig.fehler.glob("*.csv"))) + len(
        list(konfig.pruefen.glob("*.csv"))
    ) == 2


# ------------------------------------------------------------------------------ Oberfläche
@pytest.fixture(scope="session")
def qapp():
    from fakturafalter.gui.app import anwendung

    return anwendung()


@pytest.fixture
def fenster(qapp, tmp_path, monkeypatch):
    from fakturafalter.gui import aktionen, texte

    aktionen.NUR_MERKEN = True
    cfg = tmp_path / "cfg"
    shutil.copytree(BEISPIELE, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {n: str(tmp_path / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")}
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    texte.sprache_setzen("de")
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(cfg / "konfiguration.yaml", tray_erlaubt=False)
    w.resize(900, 760)
    w.show()
    qapp.processEvents()
    yield w
    w.beenden()
    qapp.processEvents()


def _warten(qapp, bed, s=60.0):
    ende = time.time() + s
    while time.time() < ende:
        qapp.processEvents()
        if bed():
            return True
        time.sleep(0.02)
    return False


def test_knopf_mit_menue_neben_jetzt_einlesen(fenster, qapp):
    leiste = fenster.b_jetzt.parentWidget().layout()
    reihe = [leiste.itemAt(i).widget() for i in range(leiste.count()) if leiste.itemAt(i).widget()]
    assert reihe.index(fenster.b_umwandeln) == reihe.index(fenster.b_jetzt) + 1
    assert fenster.b_umwandeln.text() == "Umwandeln …"
    assert [a.text() for a in fenster.m_umwandeln.actions()] == ["Dateien wählen …", "Ordner wählen …"]
    assert fenster.b_umwandeln.height() >= 48
    assert fenster.acceptDrops()


def test_umwandeln_bei_ueberwachung_aus(fenster, qapp, tmp_path):
    fenster.pause_umschalten()
    assert _warten(qapp, lambda: fenster.zust == "pausiert")
    assert fenster.b_umwandeln.isEnabled() and not fenster.b_jetzt.isEnabled()
    q = tmp_path / "manuell"
    q.mkdir()
    csv = Path(shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", q))
    laeufe = []
    fenster.arbeiter.lauf_fertig.connect(laeufe.append)
    assert fenster.umwandeln([q])
    assert not fenster.b_umwandeln.isEnabled()
    assert _warten(qapp, lambda: bool(laeufe))
    qapp.processEvents()
    assert list(fenster.k.ausgang.glob("*_zugferd.pdf")) and csv.exists()
    assert fenster.zust == "pausiert"  # Schalter unverändert
    assert fenster.b_umwandeln.isEnabled()
    toasts = fenster.toasts.sichtbare()
    assert toasts and toasts[-1].art == "ok" and "umgewandelt" in toasts[-1].titel.text()


def test_ziehen_ins_fenster(fenster, qapp, tmp_path):
    from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    q = tmp_path / "zieh"
    q.mkdir()
    csv = Path(shutil.copy(BEISPIELE / "variante-a_positionen_utf8.csv", q))
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(csv))])
    ein = QDragEnterEvent(QPoint(50, 50), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)
    fenster.dragEnterEvent(ein)
    assert ein.isAccepted() and fenster.ablage.isVisible()
    assert csv.name in fenster.l_ablage.text()
    laeufe = []
    fenster.arbeiter.lauf_fertig.connect(laeufe.append)
    ab = QDropEvent(QPoint(50, 50), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    fenster.dropEvent(ab)
    assert not fenster.ablage.isVisible()
    assert _warten(qapp, lambda: bool(laeufe))
    assert list(fenster.k.ausgang.glob("*_zugferd.pdf")) and csv.exists()
    # Text ohne Datei: wird nicht angenommen
    md2 = QMimeData()
    md2.setText("hallo")
    ein2 = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, md2, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
    fenster.dragEnterEvent(ein2)
    assert not ein2.isAccepted()


def test_nichts_passendes_und_einrichtung_fehlt(fenster, qapp, tmp_path, monkeypatch):
    q = tmp_path / "leer"
    q.mkdir()
    (q / "brief.docx").write_bytes(b"PK")
    assert not fenster.umwandeln([q])
    titel = [t.titel.text() for t in fenster.toasts.sichtbare()]
    assert any("übersprungen" in t for t in titel) and any("Nichts zum Umwandeln" in t for t in titel)
    detail = " ".join(t.detail.text() for t in fenster.toasts.sichtbare())
    assert "als PDF speichern" in detail and "Nur PDF" in detail and ".xlsx" in detail  # Tipp für Word/ODT/.xls
    monkeypatch.setattr(fenster, "einrichtung_fehlt", lambda: ["Absender"])
    assert not fenster.umwandeln([q])
    assert any("Einrichtung" in t.titel.text() for t in fenster.toasts.sichtbare())


def test_ablage_kontrast():
    from fakturafalter.gui import thema

    from .test_rc1_suche import _kontrast

    for hell in (True, False):
        c = thema.farben(hell)
        assert _kontrast(c["fg"], c["card"]) >= 4.5 and _kontrast(c["sub"], c["card"]) >= 4.5
        assert _kontrast(c["acc"], c["card"]) >= 3.0  # Rahmen (Nicht-Text, WCAG 1.4.11)


@pytest.mark.parametrize("endung", [".docx", ".odt", ".rtf", ".doc"])
def test_word_im_eingang_mit_tipp(konfig, endung):
    """Word/ODT im Eingang: Fehler mit klarem „nicht unterstützt“ und Tipp, kein Absturz (rc2)."""
    from fakturafalter import pipeline

    d = konfig.eingang / f"brief{endung}"
    d.write_bytes(b"PK\x03\x04fiktiv")
    pipeline.verarbeiten([d], konfig)
    txt = (konfig.fehler / f"brief{endung}_fehler.txt").read_text(encoding="utf-8")
    assert "nicht unterstützt" in txt and "als PDF speichern" in txt and "Nur PDF" in txt and "CSV" in txt


def test_xls_im_eingang_mit_tipp(konfig):
    from fakturafalter import pipeline

    d = konfig.eingang / "alt.xls"
    d.write_bytes(b"\xd0\xcf\x11\xe0fiktiv")
    pipeline.verarbeiten([d], konfig)
    txt = (konfig.fehler / "alt.xls_fehler.txt").read_text(encoding="utf-8")
    assert ".xls wird nicht unterstützt" in txt and ".xlsx" in txt
