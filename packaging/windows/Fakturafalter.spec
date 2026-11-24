# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
# PyInstaller-Spec für Windows (Aufruf über build.py mit einem Windows-Python, nativ oder unter Wine).
# Ergebnis: onedir dist/win/Fakturafalter mit zwei Programmen, die sich _internal teilen:
#   Fakturafalter.exe      Fensterprogramm (console=False) für Doppelklick/Autostart, ohne Konsolenfenster
#   fakturafalter-cli.exe  Konsolenprogramm für --einmal, --headless, --pruefe, Skripte
# Nicht gebündelt: opengl32sw.dll (Mesa-Software-OpenGL, nur für Qt Quick/GL-Rückfall) und
# d3dcompiler_47.dll – Fakturafalter ist eine Qt-Widgets-Anwendung und braucht sie nicht.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
SRC = os.path.join(ROOT, "src")
STAGE = os.path.join(ROOT, "build", "win-stage")
ICON = os.path.join(ROOT, "packaging", "windows", "fakturafalter.ico")
VERSION = os.path.join(STAGE, "version-info.txt")

a = Analysis(
    [os.path.join(ROOT, "packaging", "start.py")],
    pathex=[SRC],
    datas=[
        (os.path.join(SRC, "fakturafalter", "ressourcen"), os.path.join("fakturafalter", "ressourcen")),
        (os.path.join(STAGE, "lizenzen"), "lizenzen"),
    ],
    hiddenimports=["PySide6.QtNetwork", "PySide6.QtSvg"],
    excludes=["tkinter", "numpy", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtConcurrent"],
)

WEG = {"opengl32sw.dll", "d3dcompiler_47.dll"}
print("Nicht gebündelt:", " ".join(sorted({os.path.basename(b[0]) for b in a.binaries
                                            if os.path.basename(b[0]).lower() in WEG})) or "-")
a.binaries = [b for b in a.binaries if os.path.basename(b[0]).lower() not in WEG]

pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Fakturafalter",
          console=False, strip=False, upx=False, icon=ICON, version=VERSION)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fakturafalter-cli",
          console=True, strip=False, upx=False, icon=ICON, version=VERSION)
coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="Fakturafalter")
