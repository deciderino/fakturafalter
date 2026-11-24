#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Windows-ZIP unter Linux mit Wine + Windows-Python bauen (Cross-Build).
#
#   packaging/windows/build-windows.sh
#
# Umgebung:
#   WINEPREFIX   Wine-Präfix mit installiertem Windows-Python 3.13 (python.org-Installer)
#   WINPY        Windows-Python, Standard C:\Python313\python.exe – nur zum Anlegen des Bau-venv;
#                alle Pakete landen im eigenen venv, das Basis-Python bleibt unverändert
#   VENV_WIN     Bau-venv, Standard build/venv-win
#   JDK, JMODS_WIN, WERKZEUG_QUELLE  für die Prüfwerkzeuge (siehe packaging/werkzeuge.sh);
#                ohne JDK entsteht ein Paket ohne Prüfwerkzeuge (Warnung)
# Nativ unter Windows: venv anlegen, „pip install .[gui] pyinstaller“, dann packaging\windows\build.py.
# Ergebnis: dist/win/Fakturafalter-<Version>-Windows-x86_64.zip (+ .sha256, + onedir dist/win/Fakturafalter)
#
# Hinweis: Wine reserviert beim Start viel Adressraum. Steht vm.overcommit_memory auf 0 und hat der
# Rechner wenig RAM, stürzt wine sofort mit „Segmentation fault“ ab (dmesg: __vm_enough_memory);
# dann vorübergehend „sudo sysctl vm.overcommit_memory=1“.
set -euo pipefail
cd "$(dirname "$0")/../.."
WINPY="${WINPY:-C:\\Python313\\python.exe}"
VENV_WIN="${VENV_WIN:-build/venv-win}"
if [ ! -f "$VENV_WIN/Scripts/python.exe" ]; then
  wine "$WINPY" -m venv "$(winepath -w "$VENV_WIN")"
  wine "$(winepath -w "$VENV_WIN/Scripts/python.exe")" -m pip install -q --upgrade pip
fi
PY="$(winepath -w "$VENV_WIN/Scripts/python.exe")"
wine "$PY" -m pip install -q "$(winepath -w "$PWD")[gui]" "pyinstaller>=6.10"
# nur die Abhängigkeiten behalten: PyInstaller soll fakturafalter aus src/ nehmen (aktueller Stand)
wine "$PY" -m pip uninstall -q -y fakturafalter
rm -rf build/werkzeuge-win
if [ -n "${JDK:-}" ]; then
  packaging/werkzeuge.sh build/werkzeuge-win windows
fi
wine "$PY" "$(winepath -w packaging/windows/build.py)"
