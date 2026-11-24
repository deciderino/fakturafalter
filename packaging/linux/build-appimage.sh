#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Fakturafalter-<Version>-x86_64.AppImage bauen (PyInstaller onedir + appimagetool).
#
#   packaging/linux/build-appimage.sh            (aus dem Projektordner)
#
# Umgebung:
#   PYTHON=/pfad/zu/python3.13   Python für das Bau-venv. Empfohlen: python-build-standalone
#                                (z.B. „uv python install 3.13“, dann „uv python find 3.13 --managed-python“),
#                                damit das AppImage nicht an die glibc des Bau-Rechners gebunden ist.
#   APPIMAGETOOL=appimagetool    appimagetool (oder ein Wrapper mit --runtime-file …)
#   EXTRA_LIBS_DIR=…             optional: libxcb-cursor0, -icccm4, -image0, -keysyms1, -render-util0, -util1
#                                (Ubuntu 22.04), die Qts xcb-Plugin braucht und manchen Distributionen fehlen
#   VENV=build/venv-linux        Bau-venv (wird bei Bedarf angelegt)
#   JDK, WERKZEUG_QUELLE         Prüfwerkzeuge (Java-Laufzeit per jlink, Mustang, KoSIT), siehe
#                                packaging/werkzeuge.sh; ohne JDK entsteht ein Paket ohne Prüfwerkzeuge
# Ergebnis: dist/Fakturafalter-<Version>-x86_64.AppImage (+ dist/Fakturafalter/ als onedir)
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"; PKG="$ROOT/packaging/linux"; OUT="$ROOT/dist"
PYTHON="${PYTHON:-python3}"; VENV="${VENV:-$ROOT/build/venv-linux}"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/fakturafalter/__init__.py)"
: "${VERSION:?__version__ nicht gefunden}"

if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
fi
"$VENV/bin/pip" install -q ".[gui]" "pyinstaller>=6.10"
# nur die Abhängigkeiten behalten: PyInstaller soll fakturafalter aus src/ nehmen (aktueller Stand)
"$VENV/bin/pip" uninstall -q -y fakturafalter
PY="$VENV/bin/python"

rm -rf build/linux-stage build/pyi-linux "$OUT/Fakturafalter" AppDir
mkdir -p build/linux-stage "$OUT"
"$PY" packaging/lizenzen.py build/linux-stage/lizenzen
if [ -n "${EXTRA_LIBS_DIR:-}" ]; then
  echo "xcb-util-Bibliotheken aus Ubuntu 22.04 (MIT/X11-Lizenz, siehe /usr/share/doc/libxcb-*/copyright)" \
    > build/linux-stage/lizenzen/xcb-util.txt
  ls "$EXTRA_LIBS_DIR" >> build/linux-stage/lizenzen/xcb-util.txt
fi

FF_ROOT="$ROOT" "$VENV/bin/pyinstaller" --noconfirm --clean --distpath "$OUT" --workpath build/pyi-linux \
  "$PKG/Fakturafalter.spec"

if [ -n "${JDK:-}" ]; then
  packaging/werkzeuge.sh "$OUT/Fakturafalter/werkzeuge" linux
else
  echo "WARNUNG: JDK nicht gesetzt – AppImage ohne Prüfwerkzeuge" >&2
fi

mkdir -p AppDir/usr/lib AppDir/usr/share/licenses/fakturafalter
cp -a "$OUT/Fakturafalter" AppDir/usr/lib/
cp -a build/linux-stage/lizenzen/. AppDir/usr/share/licenses/fakturafalter/
cp "$PKG/AppRun" AppDir/AppRun
cp "$PKG/fakturafalter.desktop" AppDir/
echo "X-AppImage-Version=$VERSION" >> AppDir/fakturafalter.desktop
cp packaging/fakturafalter.png AppDir/fakturafalter.png
cp packaging/fakturafalter.png AppDir/.DirIcon
for n in 16 24 32 48 64 128 256; do
  mkdir -p "AppDir/usr/share/icons/hicolor/${n}x${n}/apps"
  cp "packaging/icons/fakturafalter-$n.png" "AppDir/usr/share/icons/hicolor/${n}x${n}/apps/fakturafalter.png"
done
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp src/fakturafalter/ressourcen/fakturafalter.svg AppDir/usr/share/icons/hicolor/scalable/apps/fakturafalter.svg
ZIEL="$OUT/Fakturafalter-$VERSION-x86_64.AppImage"
ARCH=x86_64 VERSION="$VERSION" "$APPIMAGETOOL" --no-appstream AppDir "$ZIEL"
rm -rf AppDir
ls -la "$ZIEL"
sha256sum "$ZIEL"
