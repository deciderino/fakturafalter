# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Windows-Paket bauen: dist/win/Fakturafalter-<Version>-Windows-x86_64.zip (PyInstaller onedir).

Mit einem *Windows*-Python 3.13 ausführen (nativ oder unter Wine über build-windows.sh), in dessen
Umgebung „fakturafalter[gui]“ und „pyinstaller“ installiert sind:

    python packaging\\windows\\build.py

Warum onedir + ZIP statt onefile: startet schnell, entpackt nicht bei jedem Start nach %TEMP%
(klassischer Virenscanner-Fehlalarm), und der Ordner ist portabel: Konfiguration und Protokolle
landen im Ordner „daten“ daneben, sofern beschreibbar.
Prüfwerkzeuge: liegt build/werkzeuge-win vor (packaging/werkzeuge.sh … windows, ruft build-windows.sh
auf), kommt es als Ordner „werkzeuge“ ins Paket (Java-Laufzeit, Mustang, KoSIT) – Prüfung ohne Installation.
"""
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "packaging" / "windows"
STAGE = ROOT / "build" / "win-stage"
DIST = ROOT / "dist" / "win"

LIESMICH = """Fakturafalter {v} für Windows (x86_64), portable Version
============================================================

Start:   Fakturafalter.exe (Doppelklick). Der erste Start legt eine Startkonfiguration und
         die Ordner Eingang, Ausgang, Erledigt, Fehler und Pruefen an. Danach in den
         Einstellungen den eigenen Absender eintragen.
Konsole: fakturafalter-cli.exe --help | --config DATEI --einmal | --config DATEI --headless

Daten:   Fakturafalter legt neben Fakturafalter.exe den Ordner „daten“ an und speichert
         Konfiguration und Protokolle dort (portabel, z.B. auf einem USB-Stick). Ist der
         Ordner nicht beschreibbar (z.B. unter C:\\Program Files), nimmt es %APPDATA%\\Fakturafalter.
Beispiele: Ordner „beispiele“ (Beispieldaten und Profile, frei erfunden).
Prüfung: Jede erzeugte E-Rechnung wird direkt danach lokal geprüft (Mustang: PDF/A-3 und
         ZUGFeRD; KoSIT: EN 16931). Java und die Prüfwerkzeuge liegen im Ordner „werkzeuge“,
         eine Java-Installation ist nicht nötig, das Internet wird nicht benutzt. Ungültige
         Rechnungen landen mit Begründung im Ordner Fehler. Abschalten: Einstellungen → Prüfung.
         Von Hand: fakturafalter-cli.exe --pruefe DATEI.pdf
Lizenzen: Ordner „_internal\\lizenzen“ (Fakturafalter: Apache-2.0; Qt/PySide6: LGPL-3.0;
         Prüfwerkzeuge: Unterordner Pruefwerkzeuge und werkzeuge\\lizenzen, Java: werkzeuge\\jre\\legal).

Windows SmartScreen kann beim ersten Start warnen, weil die Programme nicht signiert sind
(„Weitere Informationen“ → „Trotzdem ausführen“).
"""


def version() -> str:
    t = (ROOT / "src" / "fakturafalter" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^__version__ = "(.+)"$', t, re.M).group(1)


def version_info(v: str) -> str:
    n = tuple(([int(x) if x.isdigit() else 0 for x in v.split("-")[0].split(".")] + [0, 0, 0, 0])[:4])
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={n}, prodvers={n}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', 'Fakturafalter-Mitwirkende'),
      StringStruct('FileDescription', 'Fakturafalter - E-Rechnungen aus Warenwirtschafts-Exporten'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'Fakturafalter'),
      StringStruct('LegalCopyright', 'Apache-2.0'),
      StringStruct('OriginalFilename', 'Fakturafalter.exe'),
      StringStruct('ProductName', 'Fakturafalter'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])])
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if sys.platform != "win32":
        sys.exit("build.py braucht ein Windows-Python (nativ oder unter Wine)")
    v = version()
    shutil.rmtree(STAGE, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    STAGE.mkdir(parents=True)
    subprocess.run([sys.executable, str(ROOT / "packaging" / "lizenzen.py"), str(STAGE / "lizenzen")], check=True)
    (STAGE / "version-info.txt").write_text(version_info(v), encoding="utf-8")

    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(STAGE / "pyi"),
                    str(PKG / "Fakturafalter.spec")], check=True)

    app = DIST / "Fakturafalter"
    for exe in ("Fakturafalter.exe", "fakturafalter-cli.exe"):
        if not (app / exe).is_file():
            sys.exit(f"{exe} fehlt")
    # ohne Laufzeitreste (Protokolle, angelernte Vorlagen, Bytecode) – wie packaging/testdaten.sh
    # Ausnahme ab 0.9.7: beispiele/steuerfaelle/angelernt sind mitgelieferte Beispielvorlagen (in git)
    reste = shutil.ignore_patterns("logs", "angelernt", "__pycache__", "*.pyc")

    def ohne_reste(ordner, namen):
        weg = reste(ordner, namen)
        if Path(ordner).name == "steuerfaelle":
            weg.discard("angelernt")
        return weg

    shutil.copytree(ROOT / "beispiele", app / "beispiele", ignore=ohne_reste)
    werkzeuge = ROOT / "build" / "werkzeuge-win"
    if (werkzeuge / "jre" / "bin" / "java.exe").is_file():
        shutil.copytree(werkzeuge, app / "werkzeuge")
    else:
        print("WARNUNG: build/werkzeuge-win fehlt – Paket ohne Prüfwerkzeuge", file=sys.stderr)
    (app / "LIESMICH.txt").write_text(LIESMICH.format(v=v).replace("\n", "\r\n"), encoding="utf-8-sig")

    zpfad = DIST / f"Fakturafalter-{v}-Windows-x86_64.zip"
    with zipfile.ZipFile(zpfad, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(app.rglob("*")):
            if f.is_file():
                z.write(f, Path("Fakturafalter") / f.relative_to(app))
    s = sha256(zpfad)
    (zpfad.parent / (zpfad.name + ".sha256")).write_text(f"{s}  {zpfad.name}\n", encoding="utf-8")
    print(f"{zpfad}  {zpfad.stat().st_size} Bytes  sha256 {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
