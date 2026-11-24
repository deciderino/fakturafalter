# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
# PyInstaller-Spec für das Linux-AppImage (Aufruf über build-appimage.sh).
# Gebündelt: Python (python-build-standalone), PySide6/Qt aus dem Wheel, alle Python-Abhängigkeiten
# samt ihren mitgelieferten Bibliotheken (*.libs), Ressourcen, Lizenztexte. Systembibliotheken des
# Zielsystems (glibc, X11/xcb, Wayland, GL, fontconfig, glib, dbus …) werden NICHT gebündelt, außer
# den xcb-util-Bibliotheken aus EXTRA_LIBS_DIR, die Qts xcb-Plugin braucht und vielen Distributionen fehlen.
import os
import sys

ROOT = os.environ["FF_ROOT"]
SRC = os.path.join(ROOT, "src")
STAGE = os.path.join(ROOT, "build", "linux-stage")
EXTRA = os.environ.get("EXTRA_LIBS_DIR", "")
BEHALTEN = tuple(os.path.realpath(p) for p in {sys.prefix, sys.base_prefix})

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


def _behalten(eintrag):
    return os.path.realpath(eintrag[1]).startswith(BEHALTEN)


weg = sorted({os.path.basename(b[0]) for b in a.binaries if not _behalten(b)})
print("Nicht gebündelt (Systembibliotheken):", " ".join(weg))
a.binaries = [b for b in a.binaries if _behalten(b)]
if EXTRA:
    for f in sorted(os.listdir(EXTRA)):
        if ".so" in f:
            a.binaries.append((f, os.path.join(EXTRA, f), "BINARY"))

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fakturafalter",
          console=True, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Fakturafalter")
