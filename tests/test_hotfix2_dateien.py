# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.4.3+hotfix2: „PermissionError“ beim Speichern der ersten angelernten Vorlage (Windows, Ordner auf dem
Desktop).  Windows-Sperren (WinError 5/32) werden hier per monkeypatch nachgestellt – nur erfundene Daten."""

import logging
import os
import shutil
from pathlib import Path

import pytest
import yaml

from fakturafalter import anlernen, dateien, konfig, pipeline

IND = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"


def gesperrt(winerror=32):
    e = PermissionError(13, "Der Prozess kann nicht auf die Datei zugreifen")
    e.winerror = winerror
    return e


@pytest.fixture(autouse=True)
def ohne_pausen(monkeypatch):
    monkeypatch.setattr(dateien, "PAUSEN", (0, 0, 0))


@pytest.fixture
def k(tmp_path):
    roh = yaml.safe_load((IND / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    pfad = tmp_path / "konfiguration.yaml"
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    k = konfig.lade_konfig(pfad)
    k.ordner_anlegen()
    k.nachpruefen = False
    k.pfad_datei = pfad
    return k


def sitzung(k, nr="NB-26-1001"):
    p = anlernen.in_warteschlange(k, [IND / "eingang" / f"{nr}.pdf"])[0]
    s = anlernen.Sitzung(p, k)
    for f in s.fehlende():
        s.bestaetigen(f)
    assert s.fertig(), s.fehlende()
    return s


# -------------------------------------------------------------------------------------------- dateien
def test_ersetzen_wartet_kurz_gesperrtes_ziel_ab(tmp_path, monkeypatch):
    ziel = tmp_path / "vorlage.yaml"
    ziel.write_text("alt", encoding="utf-8")
    echt, n = os.replace, []

    def replace(a, b):
        n.append(1)
        if len(n) <= 2:  # OneDrive/Virenscanner hält die Datei kurz fest
            raise gesperrt(32)
        echt(a, b)

    monkeypatch.setattr(dateien.os, "replace", replace)
    dateien.schreiben(ziel, "neu")
    assert ziel.read_text(encoding="utf-8") == "neu" and len(n) == 3
    assert not list(tmp_path.glob("*.tmp"))


def test_dauerhaft_gesperrt_klare_meldung(tmp_path, monkeypatch, caplog):
    ziel = tmp_path / "vorlage.yaml"
    ziel.write_text("alt", encoding="utf-8")
    monkeypatch.setattr(dateien.os, "replace", lambda a, b: (_ for _ in ()).throw(gesperrt(32)))
    with (
        caplog.at_level(logging.INFO, logger="fakturafalter"),
        pytest.raises(dateien.DateiNichtSchreibbar) as ei,
    ):
        dateien.schreiben(ziel, "neu")
    assert str(ei.value) == "Datei ist gerade in Benutzung (vorlage.yaml)"
    assert isinstance(ei.value, PermissionError)
    assert ziel.read_text(encoding="utf-8") == "alt"  # nichts Halbes
    assert not list(tmp_path.glob("*.tmp"))  # Temp-Datei aufgeräumt
    log = caplog.text
    assert str(ziel) in log and "winerror=32" in log and "errno=13" in log


def test_zugriff_verweigert_heisst_nicht_in_benutzung(tmp_path, monkeypatch):
    monkeypatch.setattr(dateien.os, "replace", lambda a, b: (_ for _ in ()).throw(gesperrt(5)))
    with pytest.raises(dateien.DateiNichtSchreibbar) as ei:
        dateien.schreiben(tmp_path / "x.yaml", "neu")
    assert str(ei.value) == "Kein Schreibzugriff (x.yaml)"


def test_andere_fehler_nicht_wiederholt(tmp_path, monkeypatch):
    n = []

    def replace(a, b):
        n.append(1)
        raise FileNotFoundError(2, "weg")

    monkeypatch.setattr(dateien.os, "replace", replace)
    with pytest.raises(FileNotFoundError):
        dateien.schreiben(tmp_path / "x.yaml", "neu")
    assert len(n) == 1


def test_verschieben_gesperrte_quelle_hinterlaesst_keine_kopie(tmp_path, monkeypatch):
    """Genau der Windows-Fall von 0.4.3: shutil.move kopierte, konnte die offene Quelle nicht löschen und ließ
    eine Doppelte in „Erledigt“ zurück."""
    q = tmp_path / "a.pdf"
    q.write_bytes(b"%PDF-1.7")
    (tmp_path / "Erledigt").mkdir()
    monkeypatch.setattr(dateien.os, "rename", lambda a, b: (_ for _ in ()).throw(gesperrt(32)))
    with pytest.raises(dateien.DateiNichtSchreibbar):
        dateien.verschieben(q, tmp_path / "Erledigt" / "a.pdf")
    assert q.exists() and not (tmp_path / "Erledigt" / "a.pdf").exists()


def test_protokoll_in_excel_offen(tmp_path, monkeypatch):
    p = tmp_path / "protokoll.tsv"
    p.write_text("", encoding="utf-8")
    echt = open

    def oeffnen(datei, modus="r", *a, **kw):
        if Path(datei) == p and "a" in modus:
            raise gesperrt(32)
        return echt(datei, modus, *a, **kw)

    monkeypatch.setattr("builtins.open", oeffnen)
    with pytest.raises(dateien.DateiNichtSchreibbar, match="in Benutzung"):
        dateien.beschreibbar_pruefen(tmp_path, p)


def test_schreibschutz_eigener_datei_wird_aufgehoben(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root ignoriert Schreibschutz")
    ziel = tmp_path / "profil-x.yaml"
    ziel.write_text("alt", encoding="utf-8")
    ziel.chmod(0o444)
    dateien.schreiben(ziel, "neu")  # POSIX: os.replace geht ohnehin – Hauptsache kein Fehler
    assert ziel.read_text(encoding="utf-8") == "neu"


def test_warteschlange_uebernimmt_schreibschutz_nicht(tmp_path, k):
    q = tmp_path / "rechnung.pdf"
    shutil.copy(IND / "eingang" / "NB-26-1001.pdf", q)
    q.chmod(0o444)
    (z,) = anlernen.in_warteschlange(k, [q])
    assert os.access(z, os.W_OK) or os.geteuid() == 0
    assert int(z.stat().st_mtime) == int(q.stat().st_mtime)  # Reihenfolge der Warteschlange bleibt


# -------------------------------------------------------------------------------------- Anlernen speichern
def test_pdf_gesperrt_rechnung_und_vorlage_trotzdem_gespeichert(k, monkeypatch):
    s = sitzung(k)
    monkeypatch.setattr(dateien.os, "rename", lambda a, b: (_ for _ in ()).throw(gesperrt(32)))
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok" and v is not None
    assert isinstance(s.nicht_verschoben, dateien.DateiNichtSchreibbar)
    assert s.pfad.exists() and not list(k.erledigt.glob("*.pdf"))  # PDF bleibt, keine Doppelte
    assert erg.nummer in (k.ausgang / "protokoll.tsv").read_text(encoding="utf-8")
    assert list((k.basis / "angelernt").glob("*.yaml"))


def test_vorlage_gesperrt_nichts_halbes_und_zweiter_versuch_klappt(k, monkeypatch):
    s = sitzung(k)
    echt = dateien.ersetzen

    def ersetzen(tmp, ziel):
        if Path(ziel).parent.name == "angelernt":
            Path(tmp).unlink(missing_ok=True)
            raise dateien.DateiNichtSchreibbar(Path(ziel), gesperrt(32), "ersetzen")
        echt(tmp, ziel)

    monkeypatch.setattr(dateien, "ersetzen", ersetzen)
    with pytest.raises(dateien.DateiNichtSchreibbar):
        s.speichern(k.pfad_datei)
    assert not list(k.ausgang.glob("*.pdf"))  # Ausgabe zurückgenommen
    assert s.pfad.exists()
    monkeypatch.setattr(dateien, "ersetzen", echt)
    erg, v = s.speichern(k.pfad_datei)  # früher: „Ausgabe … existiert bereits“
    assert erg.status == "ok", erg.hinweise
    assert not s.pfad.exists()


def test_protokoll_gesperrt_vorab_erkannt(k, monkeypatch):
    s = sitzung(k)
    (k.ausgang / "protokoll.tsv").write_text("", encoding="utf-8")
    echt = dateien.beschreibbar_pruefen

    def pruefen(ordner, datei=None):
        if datei is not None and Path(datei).name == "protokoll.tsv":
            raise dateien.DateiNichtSchreibbar(Path(datei), gesperrt(32), "öffnen")
        echt(ordner, datei)

    monkeypatch.setattr(dateien, "beschreibbar_pruefen", pruefen)
    with pytest.raises(dateien.DateiNichtSchreibbar, match="protokoll.tsv"):
        s.speichern(k.pfad_datei)
    assert not list(k.ausgang.glob("*.pdf")) and not list(k.basis.glob("profil-*.yaml"))


def test_ausgabe_rest_ohne_protokoll_wird_ersetzt(k):
    """Rest eines abgebrochenen Speicherns (0.4.3 auf Windows): Ausgabe da, aber nicht im Protokoll."""
    s = sitzung(k)
    n_pdf, _ = pipeline.ausgabe_namen(s.rechnung().nummer)
    (k.ausgang / n_pdf).write_bytes(b"%PDF-1.7 rest")
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    s2 = sitzung(k)  # echtes Doppel bleibt gesperrt
    erg2, v2 = s2.speichern(k.pfad_datei)
    assert erg2.status != "ok" and v2 is None


def test_erste_meldung_ueberspringt_info():
    h = [
        "INFO: [BT-109] Kontrollwert 138.79 stimmt",
        "INFO: [BT-112] Kontrollwert 165.16 stimmt",
        "PRUEFEN: [BT-1] Ausgabe X.pdf existiert bereits – Rechnung wurde schon erzeugt?",
    ]
    assert (
        anlernen.erste_meldung(h)
        == "[BT-1] Ausgabe X.pdf existiert bereits – Rechnung wurde schon erzeugt?"
    )
    assert anlernen.erste_meldung(h[:2]) == ""


# ------------------------------------------------------------------------------------------- Orte
def test_benutzerordner_windows(tmp_path, monkeypatch):
    from fakturafalter.gui import orte

    monkeypatch.setattr(orte.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert orte.benutzer_ordner() == tmp_path / "Local" / "Fakturafalter"
    (tmp_path / "Roaming" / "Fakturafalter").mkdir(parents=True)
    (tmp_path / "Roaming" / "Fakturafalter" / "konfiguration.yaml").write_text(
        "{}", encoding="utf-8"
    )
    assert orte.benutzer_ordner() == tmp_path / "Roaming" / "Fakturafalter"  # bisherige bleibt


def test_portabel_nur_wenn_wirklich_beschreibbar(tmp_path, monkeypatch):
    from fakturafalter.gui import orte

    monkeypatch.setattr(orte.sys, "frozen", True, raising=False)
    monkeypatch.setattr(orte.sys, "executable", str(tmp_path / "Fakturafalter.exe"))
    assert orte.portabel_ordner() == tmp_path / "daten"
    (tmp_path / "daten" / "konfiguration.yaml").write_text("{}", encoding="utf-8")
    echt = open

    def oeffnen(datei, modus="r", *a, **kw):
        if Path(datei).name == "konfiguration.yaml" and "a" in modus:
            raise PermissionError(13, "Zugriff verweigert")
        return echt(datei, modus, *a, **kw)

    monkeypatch.setattr("builtins.open", oeffnen)
    assert orte.portabel_ordner() is None
