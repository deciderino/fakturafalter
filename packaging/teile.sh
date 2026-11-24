#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Gebaute Pakete in Teile zu je 20 000 000 Bytes zerlegen (für Übertragungswege mit Größenlimit).
#
#   packaging/teile.sh [DATEI …]     Standard: dist/*.AppImage und dist/win/*.zip
#
# Ergebnis in dist/teile/: DATEI.teil-aa, -ab, …, SHA256SUMS (ganze Dateien und Teile), ZUSAMMENSETZEN.txt
set -euo pipefail
cd "$(dirname "$0")/.."
GROESSE=20000000
ZIEL=dist/teile
if [ $# -eq 0 ]; then set -- dist/*.AppImage dist/win/*.zip; fi
rm -rf "$ZIEL"; mkdir -p "$ZIEL"
: > "$ZIEL/SHA256SUMS"
{
  echo "Teile wieder zusammensetzen"
  echo "==========================="
  echo
  echo "Alle Teile einer Datei in denselben Ordner legen, dann:"
  echo
} > "$ZIEL/ZUSAMMENSETZEN.txt"
for f in "$@"; do
  n="$(basename "$f")"
  split -b "$GROESSE" -a 2 "$f" "$ZIEL/$n.teil-"
  (cd "$(dirname "$f")" && sha256sum "$n") >> "$ZIEL/SHA256SUMS"
  teile=("$ZIEL/$n".teil-*)
  namen=(); for t in "${teile[@]}"; do namen+=("$(basename "$t")"); done
  {
    echo "$n  (${#teile[@]} Teile, $(stat -c %s "$f") Bytes)"
    echo "  Linux/macOS:  cat ${n}.teil-* > $n"
    echo "  Windows:      copy /b $(IFS=+; echo "${namen[*]}") $n"
    echo "  Prüfen:       sha256sum -c SHA256SUMS --ignore-missing     (Windows: certutil -hashfile $n SHA256)"
    echo "  Erwartet:     $(sha256sum "$f" | cut -d' ' -f1)"
    echo
  } >> "$ZIEL/ZUSAMMENSETZEN.txt"
done
(cd "$ZIEL" && sha256sum ./*.teil-* | sed 's#  \./#  #') >> "$ZIEL/SHA256SUMS"
echo "Die Teile selbst lassen sich vorab mit „sha256sum -c SHA256SUMS --ignore-missing“ prüfen." >> "$ZIEL/ZUSAMMENSETZEN.txt"
echo "AppImage danach ausführbar machen: chmod +x Fakturafalter-*.AppImage" >> "$ZIEL/ZUSAMMENSETZEN.txt"
ls -l "$ZIEL"
