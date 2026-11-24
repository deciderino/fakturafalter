# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kommandozeile.

  fakturafalter                                        Oberfläche (Tray, Überwachung im Hintergrund-Thread)
  fakturafalter --config konfiguration.yaml --einmal      Eingang einmal abarbeiten, dann beenden
  fakturafalter --config konfiguration.yaml --headless    Eingang dauerhaft überwachen (Dienst/Autostart)
  fakturafalter --pruefe datei.pdf datei.xml              lokal validieren (Mustang/veraPDF + KoSIT, im Paket enthalten)

Nach --einmal/--headless/--dateien wird jede erzeugte Rechnung lokal geprüft (Einstellung
optionen.nach_erstellung_pruefen, Standard an; --ohne-pruefung schaltet für diesen Aufruf ab).
  fakturafalter --config ... --dateien a.csv b.pdf        bestimmte Dateien verarbeiten (bleiben liegen)
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fakturafalter", description="CSV/PDF -> ZUGFeRD 2.x (EN 16931) + XRechnung")
    ap.add_argument("--config", "-c", help="Konfigurationsdatei (YAML/JSON); Standard: Benutzer- bzw. portabler "
                    "Ordner (Oberfläche) oder ./konfiguration.yaml (Kommandozeile)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--einmal", action="store_true", help="Eingangsordner einmal verarbeiten und beenden")
    g.add_argument("--headless", action="store_true", help="ohne Oberfläche dauerhaft überwachen")
    g.add_argument("--dateien", nargs="+", type=Path, help="nur diese Dateien verarbeiten (nicht verschieben)")
    g.add_argument("--pruefe", nargs="+", type=Path, metavar="DATEI", help="PDF/XML lokal validieren")
    g.add_argument("--gui", action="store_true", help="Oberfläche starten (Standard ohne andere Modus-Option)")
    ap.add_argument("--minimiert", action="store_true", help="Oberfläche nur im Infobereich (Tray) starten")
    ap.add_argument("--polling", action="store_true", help="Ordner abfragen statt Ereignisse (Netzlaufwerke)")
    ap.add_argument("--validieren", action="store_true",
                    help="Prüfung nach Erstellung erzwingen (auch wenn in der Konfiguration abgeschaltet)")
    ap.add_argument("--ohne-pruefung", action="store_true", help="Prüfung nach Erstellung für diesen Aufruf aus")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"fakturafalter {__version__}")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("fakturafalter")
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    logging.getLogger("pikepdf").setLevel(logging.WARNING)

    if a.pruefe:
        from .validierung import bereit, pruefen
        if not bereit():
            print("Prüfwerkzeuge nicht gefunden (Ordner „werkzeuge“ neben dem Programm oder "
                  "FAKTURAFALTER_WERKZEUGE).", file=sys.stderr)
            return 2
        erg = pruefen(a.pruefe)
        for e in erg:
            print(e.zeile())
            for t in e.fehler:
                print("   F:", t)
            for t in e.warnungen:
                print("   W:", t)
        return 0 if all(e.gueltig for e in erg) else 1

    if not (a.einmal or a.headless or a.dateien):
        try:
            import PySide6  # noqa: F401

            from .gui.app import starten
        except ImportError as e:
            if a.gui:
                print(f"Oberfläche nicht verfügbar (PySide6 fehlt?): {e}", file=sys.stderr)
                return 2
            log.warning("Oberfläche nicht verfügbar (%s) – starte im Hintergrundmodus (wie --headless).", e)
        else:
            return starten(Path(a.config) if a.config else None, a.minimiert)

    if not a.config:
        from .gui.orte import benutzer_ordner, portabel_ordner
        kandidaten = [Path("konfiguration.yaml")]
        if portabel_ordner():
            kandidaten.append(portabel_ordner() / "konfiguration.yaml")
        kandidaten.append(benutzer_ordner() / "konfiguration.yaml")
        a.config = next((p for p in kandidaten if p.exists()), kandidaten[0])

    from .konfig import lade_konfig
    from .pipeline import SCHON_ERZEUGT, verarbeiten
    from .ueberwachung import Waechter, relevant
    try:
        k = lade_konfig(a.config)
    except FileNotFoundError:
        print(f"Konfiguration nicht gefunden: {a.config}", file=sys.stderr)
        return 2
    if a.validieren:
        k.nachpruefen = True
    if a.ohne_pruefung:
        k.nachpruefen = False
    from . import logdatei
    logdatei.einrichten(Path(a.config).resolve().parent / "logs")
    logdatei.anonym_setzen(k.logs_anonym, k)

    def bericht(lauf) -> None:
        for e in lauf.ergebnisse:
            pr = f"[{e.pruefung}] " if e.pruefung else ""
            print(f"{e.status.upper():8} {e.nummer:16} {pr}{', '.join(str(p) for p in e.dateien)}")
            for h in e.hinweise:
                if not h.startswith("INFO"):
                    print("         ", h)
        for d, nr in lauf.schon_erzeugt.items():
            print(f"ERLEDIGT {Path(d).name}: {SCHON_ERZEUGT.format(nr=nr)}")
        for d, grund in lauf.datei_fehler.items():
            print(f"FEHLER   {Path(d).name}: {grund}")
        for vorlage, werte in lauf.meldungen:
            print(f"HINWEIS  {vorlage.format(**werte)}")

    if a.dateien or a.einmal:
        if a.dateien:
            lauf = verarbeiten([p.resolve() for p in a.dateien], k, verschieben=False)
        else:
            k.eingang.mkdir(parents=True, exist_ok=True)
            dateien = [p for p in k.eingang.iterdir() if relevant(p)]
            if not dateien:
                print(f"Keine Dateien in {k.eingang}")
                return 0
            lauf = verarbeiten(dateien, k)
        bericht(lauf)
        return 0 if lauf.ok else 1

    if k.updatepruefung:  # Hintergrundmodus: nur eine Logzeile, wenn es eine neuere Version gibt
        from . import updatepruefung

        updatepruefung.im_hintergrund(k.updates_vorab)
    w = Waechter(k, polling=a.polling, bei_lauf=bericht)
    signal.signal(signal.SIGINT, lambda *_: w.anhalten())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: w.anhalten())
    w.starten()
    return 0


if __name__ == "__main__":
    sys.exit(main())
