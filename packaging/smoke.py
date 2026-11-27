# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Rauchtest für ein gebautes Programm: beispiele/ einmal durchschicken (--einmal), Ausgaben prüfen.

    python packaging/smoke.py -- dist/Fakturafalter-0.9.8-x86_64.AppImage
    python packaging/smoke.py --wine -- wine dist/win/Fakturafalter/fakturafalter-cli.exe

Je Beispielvariante (a/b/c/d: CSV/Text, x: PDF + XML, e: nur XML – UBL/CII mit Rabatt, Gutschrift, Lastschrift,
l: CSV mit eigener Layout-Vorlage aus dem Layouteditor – Logo, Briefpapier-PDF, eigene Felder, k: Kundenbezeichnung
1–3, Positions-Unterzeilen mit sehr langer Art.-Nr. und Zeichnungs-Nr./Index, Prüfmuster und eigenes
Dateinamen-Muster je Belegart; ab 0.9.7 s: Steuer-Sonderfälle AE/K/G/O + USD, u: Kleinunternehmer, w: XML-Eingang in
USD mit USt in EUR, p: Nur PDF mit angelernten Vorlagen für alle Steuerfälle) ein eigener Arbeitsordner unter /tmp/Fakturafalter-Beispiel-smoke/ (sonst
meldet Fakturafalter die gleichen Rechnungsnummern zu Recht als doppelt). Erwartet je Variante
ZUGFeRD-PDFs im Ausgang und nichts im Fehlerordner. Das gebaute Programm prüft dabei selbst mit den
mitgelieferten Werkzeugen (eigene Java-Laufzeit, Mustang, KoSIT): erwartet wird „gültig“ in der
Prüfspalte von protokoll.tsv für jede Rechnung, dazu ein „--pruefe“-Aufruf auf eine Ausgabe aus a und alle
Ausgaben aus d, e, l, k, s, u, w und p.
Ab 0.9.6 zusätzlich: der Ausgang enthält nur fertige Dateien (keine .tmp/.part, kein protokoll.tsv), das Protokoll
liegt im Ordner „Protokoll“, im System-Temp bleibt kein „fakturafalter-…“-Ordner zurück, Variante b legt die
XRechnung-Zusatzdateien in den Unterordner „XRechnung“. Mit --headless-sekunden läuft die Überwachung ohne Netz
(``unshare -rn``): die Updateprüfung muss still bleiben (keine Meldung auf der Konsole, nur Debug im Log).
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
    "x": ["xml/NB-26-1001.pdf", "xml/NB-26-1001.xml"],  # PDF + XML (ZUGFeRD/CII mit gleichem Namen)
    "d": [
        "variante-d_rabatt_gutschrift_lastschrift.csv"
    ],  # Rabatt, Gutschrift, Lastschrift, Anzahlung
    "e": [
        "xml-eingang/XR-2026-0301_ubl_rabatt_lastschrift.xml",
        "xml-eingang/GS-2026-0008_cii_gutschrift.xml",
        "xml-eingang/GS-2026-0009_ubl_gutschrift.xml",
    ],  # nur XML (UBL/CII), ohne PDF
    "l": ["variante-a_positionen_utf8.csv"],  # eigene Layout-Vorlage (beispiele/layout/)
    "k": ["variante-k_kundenbezeichnung_erp.csv"],  # Kundenbezeichnung 1–3, Unterzeilen, Dateiname
    # ab 0.9.7: Steuer-Sonderfälle und Fremdwährung
    "s": ["variante-s_steuerfaelle.csv"],  # AE, K, G, O, USD mit Kurs, gemischt
    "u": ["variante-u_kleinunternehmer.csv"],  # Kleinunternehmer (§ 19 UStG)
    "w": [
        "xml-eingang/XU-2026-0007_ubl_usd.xml",
        "xml-eingang/XC-2026-0008_cii_usd.xml",
    ],  # USD, USt in EUR
    "p": [
        f"steuerfaelle/eingang/{n}.pdf"
        for n in (  # Nur PDF mit angelernten Vorlagen
            "LM-26-2001",
            "LM-26-2002",
            "LM-26-2003",
            "LM-26-2004",
            "LM-26-2005",
            "LM-26-2006",
            "LM-26-2007",
            "WE-26-0301",
            "WE-26-0302",
            "GL-26-0014",
            "GL-26-0015",
        )
    ],
    "blo": ["variante-blo_hotel.csv"],  # ab 0.9.8: CSV-Blöcke mit eigener Kopfzeile
}
# Variante k: Rechnungsnummer prüfen und Dateiname je Belegart (Einstellungen → Ausgabe, ab 0.9.5)
NUMMERNKREISE = {
    "rechnung": {
        "pruefmuster": "JJJJ######",
        "luecken_warnen": True,
        "dateiname": "{jahr}_{rechnungsnummer}_{kunde}",
    },
    "gutschrift": {"pruefmuster": "GS-JJJJ-####", "dateiname": "{belegart}_{rechnungsnummer}"},
}
NAMEN_K = [
    "2026_2026000101_Feinmechanik_Beispiel_GmbH_Werk_Sued_War.pdf",
    "2026_2026000102_Hofladen_Beispiel_Inh._Erika_Musterfrau.pdf",
    "Gutschrift_GS-2026-0011.pdf",
]
MODUS = {"x": "pdf_xml", "e": "pdf_xml", "w": "pdf_xml"}
XRECHNUNG_B = [
    "RE-2026-0102_xrechnung.xml",
    "RE-2026-0103_xrechnung.xml",
]  # Variante b: Unterordner XRechnung
ALLE_PRUEFEN = ("d", "e", "l", "k", "s", "u", "w", "p", "blo")


def winpfad(p: Path) -> str:
    return "Z:" + str(p).replace("/", "\\")


def leer_oder_fehlt(p: Path) -> list[str]:
    return sorted(x.name for x in p.iterdir()) if p.exists() else []


def temp_ordner(wine: bool) -> list[Path]:
    """System-Temp des Programms (unter Wine der Temp-Ordner im Präfix)."""
    orte = [Path(os.environ.get("TMPDIR") or "/tmp")]
    if wine:
        pre = Path(os.environ.get("WINEPREFIX") or Path.home() / ".wine")
        orte += list(pre.glob("drive_c/users/*/AppData/Local/Temp")) + list(
            pre.glob("drive_c/users/*/Temp")
        )
        orte += [pre / "drive_c" / "windows" / "temp"]
    return orte


def temp_reste(wine: bool) -> set[str]:
    return {str(p) for t in temp_ordner(wine) if t.exists() for p in t.glob("fakturafalter-*")}


def ausgang_sauber(ausgang: Path) -> list[str]:
    """Unerwartetes im Ausgang: Temp-/Zwischendateien, versteckte Dateien, ein protokoll.tsv."""
    return sorted(
        str(x.relative_to(ausgang))
        for x in ausgang.rglob("*")
        if x.name.startswith((".", "~"))
        or x.suffix in (".tmp", ".part")
        or x.name == "protokoll.tsv"
    )


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--wine", action="store_true", help="Pfade für Wine (Z:\\…) schreiben")
    ap.add_argument(
        "--headless-sekunden",
        type=float,
        default=0,
        help="zusätzlich --headless so lange laufen lassen und eine Datei einwerfen",
    )
    ap.add_argument(
        "--ohne-werkzeuge", action="store_true", help="Paket ohne Prüfwerkzeuge: „nicht geprüft“"
    )
    ap.add_argument("programm", nargs="+")
    a = ap.parse_args()
    pf = winpfad if a.wine else str
    shutil.rmtree(BASIS, ignore_errors=True)
    env = {n: w for n, w in os.environ.items() if not n.startswith("FAKTURAFALTER_")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    erwartet = "nicht geprüft" if a.ohne_werkzeuge else "gültig"
    temp_vorher = temp_reste(a.wine)
    ok = True
    pdfs = []
    zu_pruefen = []
    for v, dateien in VARIANTEN.items():
        b = BASIS / v
        (b / "cfg").mkdir(parents=True)
        for f in BSP.iterdir():
            if f.suffix in (".yaml", ".json"):
                shutil.copy(f, b / "cfg")
        d = yaml.safe_load((b / "cfg" / "konfiguration.yaml").read_text(encoding="utf-8"))
        if v in MODUS:
            d["modus"] = MODUS[v]
        if v == "l":  # Layouteditor: Vorlage + Bilder/Briefpapier
            shutil.copytree(BSP / "layout", b / "cfg" / "layout")
            d["layout"] = yaml.safe_load(
                (BSP / "layout" / "layout-beispiel.yaml").read_text(encoding="utf-8")
            )["layout"]
        if v == "k":
            d.setdefault("optionen", {})["nummernkreise"] = NUMMERNKREISE
        if v == "b":
            d.setdefault("optionen", {})["xrechnung_ablage"] = "unterordner"
        if v == "u":  # ab 0.9.7: Schalter Kleinunternehmer am Absender
            d["absender"]["kleinunternehmer"] = True
        if v == "p":  # ab 0.9.7: Nur PDF, Profile + angelernte Vorlagen
            sf = BSP / "steuerfaelle"
            for f in sf.glob("profil-*.yaml"):
                shutil.copy(f, b / "cfg")
            shutil.copytree(sf / "angelernt", b / "cfg" / "angelernt")
            d = yaml.safe_load((sf / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
            d.pop("arbeitsordner", None)
        d["ordner"] = {
            n: pf(b / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")
        }
        (b / "cfg" / "konfiguration.yaml").write_text(
            yaml.safe_dump(d, allow_unicode=True), encoding="utf-8"
        )
        (b / "eingang").mkdir()
        for f in dateien:
            shutil.copy(BSP / f, b / "eingang" / Path(f).name)
        cmd = a.programm + ["--config", pf(b / "cfg" / "konfiguration.yaml"), "--einmal"]
        r = subprocess.run(
            cmd, env=env, capture_output=True, text=True, errors="replace", timeout=600
        )
        neu = sorted((b / "ausgang").glob("*.pdf"))  # Variante k: eigene Dateinamen
        fehler = leer_oder_fehlt(b / "fehler")
        prot = b / "Protokoll" / "protokoll.tsv"  # ab 0.9.6: eigener Ordner neben dem Eingang
        schmutz = ausgang_sauber(b / "ausgang")
        pruef = (
            [(z.split("\t") + [""] * 8)[7] for z in prot.read_text(encoding="utf-8").splitlines()]
            if prot.exists()
            else []
        )
        gut = (
            r.returncode == 0
            and bool(neu)
            and not fehler
            and not leer_oder_fehlt(b / "eingang")
            and bool(pruef)
            and set(pruef) == {erwartet}
            and not schmutz
        )
        if v == "b":
            gut &= leer_oder_fehlt(b / "ausgang" / "XRechnung") == XRECHNUNG_B
        if v == "l":  # Logo/Bildfeld (Image) und Briefpapier (Form) drin
            gut &= all(b"/Image" in x.read_bytes() and b"/Form" in x.read_bytes() for x in neu)
        if v == "k":
            gut &= [x.name for x in neu] == NAMEN_K
        print(
            f"Variante {v}: exit {r.returncode}, {len(neu)} PDF(s), Prüfung {sorted(set(pruef))}, "
            f"Fehlerordner {fehler or 'leer'}, Ausgang {schmutz or 'sauber'}, Protokoll "
            f"{'ja' if prot.exists() else 'FEHLT'} -> {'OK' if gut else 'FEHLER'}"
        )
        if not gut:
            print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
        ok &= gut
        pdfs += neu
        zu_pruefen += neu if v in ALLE_PRUEFEN else neu[:1] if v == "a" else []

    if a.headless_sekunden:
        b = BASIS / "a"
        cfg = (
            b / "cfg" / "konfiguration.yaml"
        )  # einzelne CSV: nicht auf ein PDF gleichen Namens warten
        d = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        d.setdefault("optionen", {})["gegenstueck_minuten"] = 0
        cfg.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        vorher = len(leer_oder_fehlt(b / "fehler"))
        prot = b / "Protokoll" / "protokoll.tsv"
        zeilen = len(prot.read_text(encoding="utf-8").splitlines())

        def fertig():
            return (
                not (b / "eingang" / "nochmal.csv").exists()
                and len(prot.read_text(encoding="utf-8").splitlines()) > zeilen
            )

        logf = BASIS / "headless.log"
        with open(logf, "w") as lf:  # eigene Prozessgruppe: AppImage/Wine starten Kinder
            ohne_netz = ["unshare", "-rn"]  # Updateprüfung ohne Netz: muss still bleiben
            p = subprocess.Popen(
                ohne_netz
                + a.programm
                + ["--config", pf(b / "cfg" / "konfiguration.yaml"), "--headless"],
                env=env,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(
                min(10, a.headless_sekunden / 2)
            )  # Wächter starten lassen, dann Datei einwerfen
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
        applog = "\n".join(
            x.read_text(errors="replace") for x in (b / "cfg" / "logs").glob("*.log*")
        )
        still = (
            "Update" not in out
            and "Traceback" not in out
            and "Updateprüfung nicht möglich" in applog
        )
        print(
            f"--headless ohne Netz: Updateprüfung still (nur Debug im Log) -> {'OK' if still else 'FEHLER'}"
        )
        ok &= still
        gut = fertig()
        neu = prot.read_text(encoding="utf-8").splitlines()[zeilen:]
        print(
            f"--headless: Datei abgeholt und verarbeitet ({len(neu)} Protokollzeile(n), Fehlerordner "
            f"{vorher} -> {len(leer_oder_fehlt(b / 'fehler'))}) -> {'OK' if gut else 'FEHLER'}"
        )
        if not gut:
            print((out or "")[-3000:])
        ok &= gut

    rest = temp_reste(a.wine) - temp_vorher
    print(
        f"System-Temp: {'aufgeräumt' if not rest else 'RESTE ' + ', '.join(sorted(rest))} -> "
        f"{'OK' if not rest else 'FEHLER'}"
    )
    ok &= not rest

    if zu_pruefen and not a.ohne_werkzeuge:  # Prüfung von Hand mit der mitgelieferten Java-Laufzeit
        r = subprocess.run(
            a.programm + ["--pruefe", *map(pf, zu_pruefen)],
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
        )
        gut = (
            r.returncode == 0
            and r.stdout.count("OK  Mustang") == len(zu_pruefen)
            and r.stdout.count("OK  KoSIT") == len(zu_pruefen)
        )
        print(
            f"--pruefe {', '.join(p.name for p in zu_pruefen)}: exit {r.returncode} -> {'OK' if gut else 'FEHLER'}"
        )
        print("   " + r.stdout.strip().replace("\n", "\n   "))
        if not gut:
            print(r.stderr[-3000:])
        ok &= gut
    print("RAUCHTEST", "BESTANDEN" if ok else "FEHLGESCHLAGEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
