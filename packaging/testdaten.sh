#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Testdaten-Paket bauen: beispiele/ (ohne Laufzeitreste) + ANLEITUNG.txt
#
#   packaging/testdaten.sh     Ergebnis: dist/Fakturafalter-<Version>-Testdaten.zip
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/fakturafalter/__init__.py)"
NAME="Fakturafalter-$VERSION-Testdaten"
STAGE="build/$NAME"
rm -rf "$STAGE"; mkdir -p "$STAGE" dist
git ls-files -z beispiele | xargs -0 -I{} cp --parents {} "$STAGE/"
cp packaging/testdaten/ANLEITUNG.txt "$STAGE/"
rm -f "dist/$NAME.zip"
python3 - "$NAME" <<'PY'
import os, sys, zipfile
name = sys.argv[1]
with zipfile.ZipFile(f"dist/{name}.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for wurzel, _ordner, dateien in sorted(os.walk(f"build/{name}")):
        for d in sorted(dateien):
            pfad = os.path.join(wurzel, d)
            z.write(pfad, os.path.relpath(pfad, "build"))
PY
ls -l "dist/$NAME.zip"
