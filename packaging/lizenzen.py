# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Lizenztexte aller mitgelieferten Python-Pakete sammeln (Linux und Windows).

    python packaging/lizenzen.py ZIELORDNER

Geht die Abhängigkeiten von fakturafalter[gui] durch, kopiert die Lizenzdateien aus den
*.dist-info-Ordnern nach ZIELORDNER/<Paket>/ und schreibt DRITTANBIETER.txt (Name, Version,
Lizenz). Dazu Fakturafalters LICENSE/NOTICE und Pythons LICENSE.txt (enthält auch OpenSSL,
libffi, zlib, expat, …). Bricht ab, wenn eine Lizenz aus der Sperrliste auftaucht.

Die Prüfwerkzeuge (Java-Laufzeit, Mustang, KoSIT; Ordner „werkzeuge“, siehe packaging/werkzeuge.sh)
stehen in DRITTANBIETER.txt mit eigenem Abschnitt; ihre Lizenztexte, die Quelltext-Hinweise
(GPL-2.0 der Java-Laufzeit, EUPL-1.2, MPL-2.0) und das schriftliche Angebot kommen aus
packaging/lizenzen/werkzeuge/ nach ZIELORDNER/Pruefwerkzeuge/.
"""
import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WURZELN = ["PySide6-Essentials", "ruamel.yaml", "pdfplumber", "pikepdf", "reportlab", "lxml", "PyYAML",
           "fonttools", "watchdog", "openpyxl"]
GESPERRT = re.compile(r"\bAGPL|Affero", re.I)      # z.B. PyMuPDF, Ghostscript
NAMEN = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS|COPYRIGHT)", re.I)


def _norm(n: str) -> str:
    return re.sub(r"[-_.]+", "-", n).lower()


def huelle() -> list[metadata.Distribution]:
    gesehen, offen, aus = set(), list(WURZELN), []
    while offen:
        n = _norm(offen.pop())
        if n in gesehen:
            continue
        gesehen.add(n)
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            continue
        aus.append(d)
        for r in d.requires or []:
            if ";" in r and "extra ==" in r.split(";", 1)[1]:
                continue
            if ";" in r:
                from packaging.markers import Marker  # „packaging“ kommt mit PyInstaller ins Bau-venv
                try:
                    if not Marker(r.split(";", 1)[1]).evaluate():
                        continue
                except Exception:
                    pass
            offen.append(re.split(r"[ ;<>=!~\[(]", r.strip(), maxsplit=1)[0])
    return sorted(aus, key=lambda d: _norm(d.metadata["Name"]))


def lizenz(d: metadata.Distribution) -> str:
    m = d.metadata
    if (m.get("License-Expression") or "").strip():
        return m["License-Expression"].strip()
    k = [c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    if k:
        return "; ".join(k)
    t = (m.get("License") or "").strip()
    return t.splitlines()[0][:80] if t else "?"


def main() -> int:
    ziel = Path(sys.argv[1])
    shutil.rmtree(ziel, ignore_errors=True)
    ziel.mkdir(parents=True)
    zeilen = ["Mitgelieferte Drittanbieter-Software (Name, Version, Lizenz)", ""]
    for d in huelle():
        name, l_ = d.metadata["Name"], lizenz(d)
        if GESPERRT.search(l_):
            sys.exit(f"Gesperrte Lizenz: {name} {l_}")
        zeilen.append(f"{name} {d.version}: {l_}")
        unter = ziel / _norm(name)
        for f in d.files or []:
            if (NAMEN.search(f.name) or ".dist-info/licenses/" in str(f)) and not f.name.endswith((".py", ".pyc")):
                quelle = Path(d.locate_file(f))
                if quelle.is_file():
                    unter.mkdir(exist_ok=True)
                    rel = str(f).split(".dist-info/", 1)[-1].replace("/", "_")
                    shutil.copy2(quelle, unter / rel)
    zeilen += ["", "Qt 6 (in PySide6-Essentials) steht unter LGPL-3.0 und wird dynamisch gelinkt; die",
               "Qt-Bibliotheken liegen als eigene Dateien im Programmordner und können ersetzt werden.",
               "Quelltext: https://download.qt.io/official_releases/qt/ und https://code.qt.io/",
               "", f"Python {sys.version.split()[0]}: PSF-2.0 (siehe Python-LICENSE.txt)"]
    werkzeuge = ROOT / "packaging" / "lizenzen" / "werkzeuge"
    hinweis = (werkzeuge / "PRUEFWERKZEUGE.txt").read_text(encoding="utf-8")
    if GESPERRT.search(hinweis.replace("Keine der Komponenten steht unter AGPL", "")):
        sys.exit("Gesperrte Lizenz bei den Prüfwerkzeugen")
    zeilen += ["", "", "Prüfwerkzeuge (Ordner „werkzeuge“) – Lizenztexte in Pruefwerkzeuge/", "", hinweis]
    shutil.copytree(werkzeuge, ziel / "Pruefwerkzeuge")
    (ziel / "DRITTANBIETER.txt").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    for f in (ROOT / "packaging" / "lizenzen").glob("*.txt"):
        if f.name != "README.txt":
            shutil.copy2(f, ziel / f.name)
    for f in ("LICENSE", "NOTICE"):
        shutil.copy2(ROOT / f, ziel / f"Fakturafalter-{f}.txt")
    py = Path(sys.base_prefix) / "LICENSE.txt"
    if not py.exists():
        py = Path(sys.base_prefix) / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "LICENSE.txt"
    if py.exists():
        shutil.copy2(py, ziel / "Python-LICENSE.txt")
    print("\n".join(zeilen[2:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
