# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""README-Bilder aus der echten Oberfläche, nur fiktive Beispieldaten.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python skizzen/readme_bilder.py

Rohbilder: /tmp/e2-readme-shots/roh/   Ziel: docs/bilder/
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/e2-readme-shots/xdg")

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT / "src"))

import yaml  # noqa: E402

from fakturafalter import anlernen, pipeline  # noqa: E402
from fakturafalter.gui import aktionen, texte  # noqa: E402
from fakturafalter.gui.app import anwendung  # noqa: E402
from fakturafalter.konfig import lade_konfig  # noqa: E402
from fakturafalter.pipeline import Stand  # noqa: E402

aktionen.NUR_MERKEN = True

BEISPIELE = PROJEKT / "beispiele"
INDUSTRIE = BEISPIELE / "industrie"
BASIS = Path("/tmp/e2-readme-shots/arbeit")
ROH = Path("/tmp/e2-readme-shots/roh")
ZIEL = PROJEKT / "docs" / "bilder"
BREITE = 1100
GROESSEN = {
    "hauptfenster.png": (BREITE, 580),
    "fortschritt.png": (BREITE, 580),
    "einrichtung.png": (BREITE, 620),
    "pruefen.png": (BREITE, 500),
    "layouteditor.png": (BREITE, 750),
    "anlernen.png": (BREITE, 750),
}


def vorbereiten() -> Path:
    shutil.rmtree(BASIS, ignore_errors=True)
    cfg = BASIS / "Einstellungen"
    shutil.copytree(
        BEISPIELE,
        cfg,
        ignore=shutil.ignore_patterns("variante-*", "druck*", "textdruck*", "README*", "sets", "logs"),
    )
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {
        n: str(BASIS / t)
        for n, t in (
            ("eingang", "Eingang"),
            ("ausgang", "Ausgang"),
            ("erledigt", "Erledigt"),
            ("fehler", "Fehler"),
            ("pruefen", "Pruefen"),
        )
    }
    d.setdefault("oberflaeche", {})
    d["oberflaeche"]["thema"] = "hell"
    d["oberflaeche"]["sprache"] = "de"
    d["oberflaeche"]["tray_hinweis_gezeigt"] = True
    d["oberflaeche"]["starthinweis_aus"] = True
    d.setdefault("optionen", {})
    d["optionen"]["nach_erstellung_pruefen"] = False
    (cfg / "konfiguration.yaml").write_text(
        yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    k = lade_konfig(cfg / "konfiguration.yaml")
    k.eingang.mkdir(parents=True)

    csv = Path(shutil.copy(BEISPIELE / "variante-b_wawi_cp1252.csv", k.eingang))
    shutil.copy(BEISPIELE / "druckauftrag-wawi.pdf", k.eingang)
    t = csv.read_bytes().decode("cp1252")
    t = t.replace(
        'P;RE-2026-0102;;;;;1;C-300;"Kabel NYM 3x1,5 mm²";50;',
        'P;RE-2026-0102;;;;;1;C-300;"Kabel NYM 3x1,5 mm²";60;',
    )
    t = t.replace(";;;;;;;;207,66", ";;;;;;;;218,25")
    csv.write_bytes(t.encode("cp1252"))
    lauf1 = pipeline.verarbeiten(sorted(k.eingang.iterdir()), k)

    a = (BEISPIELE / "variante-a_positionen_utf8.csv").read_text(encoding="utf-8")
    a = a.replace("RE-2026-0101", "RE-2026-0201")
    zeilen = a.splitlines(keepends=True)
    kopf, rest = zeilen[0], zeilen[1:]
    erste = [z for z in rest if "RE-2026-0201" in z]
    (k.eingang / "export-positionen.csv").write_text(kopf + "".join(erste), encoding="utf-8")
    lauf2 = pipeline.verarbeiten(sorted(k.eingang.iterdir()), k)
    print("lauf1", [(e.nummer, e.status) for e in lauf1.ergebnisse], "fehler", lauf1.datei_fehler)
    print("lauf2", [(e.nummer, e.status) for e in lauf2.ergebnisse], "fehler", lauf2.datei_fehler)
    return cfg / "konfiguration.yaml"


def warten(app, s=0.5):
    ende = time.time() + s
    while time.time() < ende:
        app.processEvents()
        time.sleep(0.02)


def speichern(app, widget, name: str, pause=0.4) -> Path:
    warten(app, pause)
    p = ROH / name
    ok = widget.grab().save(str(p), "PNG")
    if not ok or not p.exists():
        raise RuntimeError(f"Screenshot fehlgeschlagen: {name}")
    print(f"{name}: {widget.width()}x{widget.height()} -> {p.stat().st_size} Bytes")
    return p


def pruefung_anzeigen(w) -> None:
    """Paket-Ansicht: die Prüfwerkzeuge liegen im AppImage und im Windows-ZIP."""
    w.l_pruefmodul.setText("Prüfung: an")
    w.l_pruefmodul.setEnabled(True)


def haupt(app, konfig: Path):
    texte.sprache_setzen("de")
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w = Hauptfenster(konfig, tray_erlaubt=False, auto_start=False)
    w.resize(*GROESSEN["hauptfenster.png"])
    w.show()
    warten(app, 0.4)
    if w.starthinweis is not None:
        w._starthinweis_schliessen(False)
        warten(app, 0.2)
    if w.zust != "aktiv":
        w.pause_umschalten()
        ende = time.time() + 5
        while time.time() < ende and w.zust != "aktiv":
            warten(app, 0.1)
        if w.zust != "aktiv":
            raise RuntimeError(f"Überwachung startet nicht (zustand={w.zust})")
    w.aktualisieren()
    warten(app)
    return w


def main() -> int:
    shutil.rmtree(ROH, ignore_errors=True)
    ROH.mkdir(parents=True)
    app = anwendung()
    texte.sprache_setzen("de")
    konfig = vorbereiten()
    w = haupt(app, konfig)

    for toast in list(w.toasts.sichtbare()):
        toast.schliessen()
    w.b_jetzt.setEnabled(True)
    pruefung_anzeigen(w)
    warten(app, 0.2)
    speichern(app, w, "hauptfenster.png")

    w._bei_fortschritt(Stand(4, 3, 12, "RE-2026-0042.pdf", "pdf", 0.42, werkzeug="KoSIT"))
    pruefung_anzeigen(w)
    warten(app, 0.3)
    speichern(app, w, "fortschritt.png")
    w._lauf_ende()
    w.b_jetzt.setEnabled(w.zust == "aktiv")
    w.aktualisieren()
    warten(app, 0.2)

    w.pruefansicht_oeffnen(0)
    pa = w.pruef_fenster
    pa.resize(*GROESSEN["pruefen.png"])
    pa.show()
    warten(app, 0.4)
    speichern(app, pa, "pruefen.png")
    pa.close()

    from fakturafalter.gui.einrichtung import Einrichtung

    e = Einrichtung(w)
    e.resize(*GROESSEN["einrichtung.png"])
    e.arbeitsordner.setText("/home/Beispiel/Fakturafalter")
    e.einzeln.setChecked(False)
    e.gehe(0)
    e.show()
    warten(app, 0.4)
    speichern(app, e, "einrichtung.png")
    e.reject()

    from fakturafalter.gui import thema
    from fakturafalter.gui.layouteditor import LayoutEditor

    roh = yaml.safe_load((BEISPIELE / "layout" / "layout-beispiel.yaml").read_text(encoding="utf-8"))
    block = roh.get("layout", roh)
    c = thema.anwenden(app, "hell")
    le = LayoutEditor(None, c, block, BEISPIELE, profil="Muster GmbH")
    le.resize(*GROESSEN["layouteditor.png"])
    le.show()
    warten(app, 1.2)
    for toast in list(le.toasts.sichtbare()):
        toast.schliessen()
    kopf = next(i for i in le._items if i.e.art == "kopf")
    kopf.setSelected(True)
    le.auswahl_geaendert()
    warten(app, 0.3)
    speichern(app, le, "layouteditor.png", pause=0.6)
    le.close()

    # eigener Anlern-Kontext „Nur PDF“, damit der Assistent ein Druck-PDF zeigt
    tmp = Path("/tmp/e2-readme-shots/anlernen")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    roh_np = yaml.safe_load((INDUSTRIE / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh_np["arbeitsordner"] = str(tmp / "lauf")
    roh_np.setdefault("oberflaeche", {})
    roh_np["oberflaeche"]["thema"] = "hell"
    roh_np["oberflaeche"]["sprache"] = "de"
    roh_np["oberflaeche"]["starthinweis_aus"] = True
    roh_np["oberflaeche"]["tray_hinweis_gezeigt"] = True
    np_pfad = tmp / "konfiguration.yaml"
    np_pfad.write_text(yaml.safe_dump(roh_np, allow_unicode=True, sort_keys=False), encoding="utf-8")
    from fakturafalter.gui.anlernen import AnlernAssistent
    from fakturafalter.gui.hauptfenster import Hauptfenster

    w2 = Hauptfenster(np_pfad, tray_erlaubt=False, auto_start=False)
    k2 = w2.k
    pdfs = anlernen.in_warteschlange(k2, sorted((INDUSTRIE / "eingang").glob("NB-26-1001.pdf")))
    d = AnlernAssistent(w2, k2, np_pfad, pdfs, w2.c)
    d.resize(*GROESSEN["anlernen.png"])
    d.show()
    warten(app, 1.5)
    # Rechnungsdaten: PDF links, erkannte Felder rechts
    if d.s is not None:
        d.schritt_setzen(2)
        warten(app, 0.8)
        # ein paar vorgeschlagene Werte bestätigen, Rest bleibt „bitte prüfen“
        offen = list(d.s.fehlende())
        for f in offen[:4]:
            d._passt(f)
        warten(app, 0.5)
    speichern(app, d, "anlernen.png", pause=0.8)
    d.reject()
    w2.beenden()
    w.beenden()
    warten(app, 0.2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
