# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Wo liegen Konfiguration und Arbeitsordner?  Portabel: ``daten/`` neben der exe (wenn beschreibbar),
sonst %APPDATA%\\Fakturafalter bzw. $XDG_CONFIG_HOME/fakturafalter.  Erststart legt eine Konfiguration an."""

from __future__ import annotations

import logging
import os
import sys
from importlib import resources
from pathlib import Path

import yaml

from .. import dateien
from ..konfig import UNTERORDNER

log = logging.getLogger("fakturafalter")

APP = "Fakturafalter"
KONFIG_NAME = "konfiguration.yaml"
START = resources.files("fakturafalter") / "ressourcen" / "start"

UI_STANDARD = {
    "sprache": "de",  # de | en
    "thema": "system",  # system | hell | dunkel
    "minimiert_starten": False,
    "schliessen_in_tray": True,
    "tray_hinweis_gezeigt": False,
    "eingerichtet": False,  # Erststart-Assistent abgeschlossen oder übersprungen
}


def portabel_ordner() -> Path | None:
    """Gebündelte exe/AppImage: ``daten/`` daneben, sofern beschreibbar (USB-Stick, entpacktes Zip).
    Geprüft wird wirklich (Probe-Datei anlegen und löschen, vorhandene Konfiguration zum Schreiben öffnen) –
    liegt die exe z. B. unter „C:\\Programme“ oder verbietet ein Schutzprogramm das Schreiben, geht es mit
    dem Benutzerordner weiter."""
    if not getattr(sys, "frozen", False):
        return None
    basis = Path(os.environ.get("APPIMAGE", sys.executable)).resolve().parent
    daten = basis / "daten"
    try:
        daten.mkdir(exist_ok=True)
        probe = daten / ".schreibtest"
        probe.write_text("x")
        probe.unlink()
        if (daten / KONFIG_NAME).exists():
            with open(daten / KONFIG_NAME, "ab"):
                pass
        return daten
    except OSError as e:
        log.warning(
            "Portabler Ordner %s nicht beschreibbar (%s: %s) – nehme den Benutzerordner %s",
            daten,
            type(e).__name__,
            e,
            benutzer_ordner(),
        )
        return None


def benutzer_ordner() -> Path:
    """Windows: %LOCALAPPDATA%\\Fakturafalter (bis 0.4.3: %APPDATA% – eine dort vorhandene Konfiguration gilt
    weiter).  Sonst $XDG_CONFIG_HOME/fakturafalter."""
    if sys.platform == "win32":
        alt = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP
        if (alt / KONFIG_NAME).exists():
            return alt
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP.lower()


def standard_konfig() -> Path:
    """Pfad der Konfiguration; legt sie beim ersten Start an."""
    port = portabel_ordner()
    ordner = port or benutzer_ordner()
    pfad = ordner / KONFIG_NAME
    if not pfad.exists():
        erststart(ordner, arbeitsordner=(Path("..") if port else Path.home() / APP))
    log.info(
        "Konfiguration: %s (%s), Programm: %s, Arbeitsverzeichnis: %s",
        pfad,
        "portabel" if port else "Benutzerordner",
        Path(sys.executable).resolve().parent,
        Path.cwd(),
    )
    return pfad


def erststart(ordner: Path, arbeitsordner: Path) -> Path:
    """Startkonfiguration + Beispielprofile anlegen. Absender bleibt leer (muss in den Einstellungen rein)."""
    ordner.mkdir(parents=True, exist_ok=True)
    for f in START.iterdir():
        if f.name != KONFIG_NAME and f.is_file() and not (ordner / f.name).exists():
            (ordner / f.name).write_bytes(f.read_bytes())
    d = yaml.safe_load((START / KONFIG_NAME).read_text(encoding="utf-8"))
    d.pop("ordner", None)
    d["arbeitsordner"] = str(
        arbeitsordner
    )  # Unterordner Eingang, Ausgang, … legt die App selbst an
    for _, name in UNTERORDNER:
        (ordner / arbeitsordner / name).mkdir(
            parents=True, exist_ok=True
        )  # absolut: ordner wird ignoriert
    speichern(ordner / KONFIG_NAME, d)
    return ordner / KONFIG_NAME


def lesen(pfad: Path) -> dict:
    return yaml.safe_load(Path(pfad).read_text(encoding="utf-8")) or {}


def ui_optionen(roh: dict) -> dict:
    o = dict(UI_STANDARD)
    o.update(roh.get("oberflaeche") or {})
    return o


def _ruamel():
    from ruamel.yaml import YAML

    y = YAML()  # Round-Trip: Kommentare, Reihenfolge und Schreibweisen bleiben erhalten
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)  # Listen eingerückt wie in den mitgelieferten Dateien
    return y


def _gleich(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, str) and isinstance(b, str):
        return str(a) == str(b)
    return (
        type(a) is type(b)
        and a == b
        or (isinstance(a, int) and isinstance(b, int) and int(a) == int(b))
    )


def _mischen(alt, neu):
    """Neue Werte in die geladene Round-Trip-Struktur übernehmen; Unverändertes (mit Kommentaren) bleibt stehen."""
    if isinstance(alt, dict) and isinstance(neu, dict):
        for k in [k for k in alt if k not in neu]:
            del alt[k]
        for k, v in neu.items():
            alt[k] = _mischen(alt[k], v) if k in alt else v
        return alt
    if isinstance(alt, list) and isinstance(neu, list) and len(alt) == len(neu):
        for i, v in enumerate(neu):
            alt[i] = _mischen(alt[i], v)
        return alt
    return alt if _gleich(alt, neu) else neu


def _yaml_text(pfad: Path, roh: dict) -> str:
    import io

    y = _ruamel()
    basis = None
    for quelle in (pfad, START / KONFIG_NAME):  # neue Datei: Kommentare der Startvorlage übernehmen
        try:
            if Path(quelle).is_file():
                basis = y.load(Path(quelle).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 – kaputte Datei: dann eben ohne Kommentare
            basis = None
        if isinstance(basis, dict):
            break
    daten = _mischen(basis, roh) if isinstance(basis, dict) else roh
    puffer = io.StringIO()
    y.dump(daten, puffer)
    return puffer.getvalue()


def speichern(pfad: Path, roh: dict) -> None:
    """Konfiguration schreiben (atomar über Temp-Datei, vorherige Fassung als .bak).

    YAML wird per ruamel.yaml (MIT) im Round-Trip geschrieben: Kommentare der Datei bleiben erhalten."""
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".json":
        import json

        text = json.dumps(roh, ensure_ascii=False, indent=2) + "\n"
    else:
        text = _yaml_text(pfad, roh)
    if pfad.exists():
        bak = pfad.with_suffix(pfad.suffix + ".bak")
        try:  # Sicherung ist nett, aber kein Grund, nicht zu speichern
            dateien.schreiben(bak, pfad.read_bytes())
        except OSError as e:
            log.warning("Sicherung %s nicht geschrieben: %s", bak, e)
    dateien.schreiben(pfad, text)
