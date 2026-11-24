# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Rauchtest für ein gebautes Programm: beispiele/ einmal durchschicken (--einmal), Ausgaben prüfen.

    python packaging/smoke.py -- dist/Fakturafalter-0.9.4-x86_64.AppImage
    python packaging/smoke.py --wine -- wine dist/win/Fakturafalter/fakturafalter-cli.exe

Je Beispielvariante (a/b/c/d: CSV/Text, x: PDF + XML, e: nur XML – UBL/CII mit Rabatt, Gutschrift, Lastschrift,
l: CSV mit eigener Layout-Vorlage aus dem Layouteditor – Logo, Briefpapier-PDF, eigene Felder) ein eigener Arbeitsordner unter /tmp/Fakturafalter-Beispiel-smoke/ (sonst
meldet Fakturafalter die gleichen Rechnungsnummern zu Recht als doppelt). Erwartet je Variante
ZUGFeRD-PDFs im Ausgang und nichts im Fehlerordner. Das gebaute Programm prüft dabei selbst mit den
mitgelieferten Werkzeugen (eigene Java-Laufzeit, Mustang, KoSIT): erwartet wird „gültig“ in der
Prüfspalte von protokoll.tsv für jede Rechnung, dazu ein „--pruefe“-Aufruf auf eine Ausgabe aus a und alle
Ausgaben aus d und e.
FAKTURAFALTER_* aus der Umgebung werden entfernt, damit wirklich das Paket prüft.
Mit --ohne-werkzeuge (Paket ohne Prüfwerkzeuge) wird stattdessen „nicht geprüft“ erwartet.
Keine Online-Dienste.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BSP = ROOT / "beispiele"
BASIS = Path("/tmp/Fakturafalter-Beispiel-smoke")
VARIANTEN = {
    "a": ["variante-a_positionen_utf8.csv"],
    "b": ["variante-b_wawi_cp1252.csv", "druckauftrag-wawi.pdf"],
    "c": ["variante-c_festbreite_cp1252.txt"],
    "x": ["xml/NB-26-1001.pdf", "xml/NB-26-1001.xml"],          # PDF + XML (ZUGFeRD/CII mit gleichem Namen)
    "d": ["variante-d_rabatt_gutschrift_lastschrift.csv"],       # Rabatt, Gutschrift, Lastschrift, Anzahlung
    "e": ["xml-eingang/XR-2026-0301_ubl_rabatt_lastschrift.xml", "xml-eingang/GS-2026-0008_cii_gutschrift.xml",
          "xml-eingang/GS-2026-0009_ubl_gutschrift.xml"],         # nur XML (UBL/CII), ohne PDF
    "l": ["variante-a_positionen_utf8.csv"],                    # eigene Layout-Vorlage (beispiele/layout/)
}
MODUS = {"x": "pdf_xml", "e": "pdf_xml"}
ALLE_PRUEFEN = ("d", "e", "l")


def winpfad(p: Path) -> str:
    return "Z:" + str(p).replace("/", "\\")


def leer_oder_fehlt(p: Path) -> list[str]:
    return sorted(x.name for x in p.iterdir()) if p.exists() else []


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--wine", action="store_true", help="Pfade für Wine (Z:\\…) schreiben")
    ap.add_argument("--headless-sekunden", type=float, default=0,
                    help="zusätzlich --headless so lange laufen lassen und eine Datei einwerfen")
    ap.add_argument("--ohne-werkzeuge", action="store_true", help="Paket ohne Prüfwerkzeuge: „nicht geprüft“")
    ap.add_argument("programm", nargs="+")
    a = ap.parse_args()
    pf = winpfad if a.wine else str
    shutil.rmtree(BASIS, ignore_errors=True)
    env = {n: w for n, w in os.environ.items() if not n.startswith("FAKTURAFALTER_")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    erwartet = "nicht geprüft" if a.ohne_werkzeuge else "gültig"
    ok = True
    pdfs = []
    zu_pruefen = []
    for v, dateien in VARIANTEN.items():
        b = BASIS / v
        (b / "cfg").mkdir(parents=True)
        for f in BSP.iterdir():
            if f.suffix in (".yaml", ".json") or f.name == "kundenstamm.csv":
                shutil.copy(f, b / "cfg")
        d = yaml.safe_load((b / "cfg" / "konfiguration.yaml").read_text(encoding="utf-8"))
        if v in MODUS:
            d["modus"] = MODUS[v]
        if v == "l":                                          # Layouteditor: Vorlage + Bilder/Briefpapier
            shutil.copytree(BSP / "layout", b / "cfg" / "layout")
            d["layout"] = yaml.safe_load((BSP / "layout" / "layout-beispiel.yaml").read_text(encoding="utf-8"))["layout"]
        d["ordner"] = {n: pf(b / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")}
        (b / "cfg" / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        (b / "eingang").mkdir()
        for f in dateien:
            shutil.copy(BSP / f, b / "eingang")
        cmd = a.programm + ["--config", pf(b / "cfg" / "konfiguration.yaml"), "--einmal"]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace", timeout=600)
        neu = sorted((b / "ausgang").glob("*_zugferd.pdf"))
        fehler = leer_oder_fehlt(b / "fehler")
        prot = b / "ausgang" / "protokoll.tsv"
        pruef = [(z.split("\t") + [""] * 8)[7] for z in prot.read_text(encoding="utf-8").splitlines()] \
            if prot.exists() else []
        gut = (r.returncode == 0 and bool(neu) and not fehler and not leer_oder_fehlt(b / "eingang")
               and bool(pruef) and set(pruef) == {erwartet})
        if v == "l":                                          # Logo/Bildfeld (Image) und Briefpapier (Form) drin
            gut &= all(b"/Image" in x.read_bytes() and b"/Form" in x.read_bytes() for x in neu)
        print(f"Variante {v}: exit {r.returncode}, {len(neu)} PDF(s), Prüfung {sorted(set(pruef))}, "
              f"Fehlerordner {fehler or 'leer'} -> {'OK' if gut else 'FEHLER'}")
        if not gut:
            print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
        ok &= gut
        pdfs += neu
        zu_pruefen += neu if v in ALLE_PRUEFEN else neu[:1] if v == "a" else []

    if a.headless_sekunden:
        b = BASIS / "a"
        cfg = b / "cfg" / "konfiguration.yaml"          # einzelne CSV: nicht auf ein PDF gleichen Namens warten
        d = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        d.setdefault("optionen", {})["gegenstueck_minuten"] = 0
        cfg.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        vorher = len(leer_oder_fehlt(b / "fehler"))
        prot = b / "ausgang" / "protokoll.tsv"
        zeilen = len(prot.read_text(encoding="utf-8").splitlines())

        def fertig():
            return (not (b / "eingang" / "nochmal.csv").exists() and
                    len(prot.read_text(encoding="utf-8").splitlines()) > zeilen)
        logf = BASIS / "headless.log"
        with open(logf, "w") as lf:                         # eigene Prozessgruppe: AppImage/Wine starten Kinder
            p = subprocess.Popen(a.programm + ["--config", pf(b / "cfg" / "konfiguration.yaml"), "--headless"],
                                 env=env, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
            time.sleep(min(10, a.headless_sekunden / 2))    # Wächter starten lassen, dann Datei einwerfen
            shutil.copy(BSP / "variante-a_positionen_utf8.csv", b / "eingang" / "nochmal.csv")
            ende = time.time() + a.headless_sekunden
            while time.time() < ende and not fertig():
                time.sleep(0.5)
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    p.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    pass
        out = logf.read_text(errors="replace")
        gut = fertig()
        neu = prot.read_text(encoding="utf-8").splitlines()[zeilen:]
        print(f"--headless: Datei abgeholt und verarbeitet ({len(neu)} Protokollzeile(n), Fehlerordner "
              f"{vorher} -> {len(leer_oder_fehlt(b / 'fehler'))}) -> {'OK' if gut else 'FEHLER'}")
        if not gut:
            print((out or "")[-3000:])
        ok &= gut

    if zu_pruefen and not a.ohne_werkzeuge:              # Prüfung von Hand mit der mitgelieferten Java-Laufzeit
        r = subprocess.run(a.programm + ["--pruefe", *map(pf, zu_pruefen)], env=env, capture_output=True, text=True,
                           errors="replace", timeout=900)
        gut = (r.returncode == 0 and r.stdout.count("OK  Mustang") == len(zu_pruefen)
               and r.stdout.count("OK  KoSIT") == len(zu_pruefen))
        print(f"--pruefe {', '.join(p.name for p in zu_pruefen)}: exit {r.returncode} -> {'OK' if gut else 'FEHLER'}")
        print("   " + r.stdout.strip().replace("\n", "\n   "))
        if not gut:
            print(r.stderr[-3000:])
        ok &= gut
    print("RAUCHTEST", "BESTANDEN" if ok else "FEHLGESCHLAGEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
