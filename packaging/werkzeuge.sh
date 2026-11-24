#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Ordner „werkzeuge“ für die lokale Prüfung zusammenstellen (Linux oder Windows):
# verkleinerte Java-Laufzeit (jlink), Mustang-CLI, KoSIT-Prüftool + Konfiguration, Prüfdienst-Helfer,
# Lizenztexte. Wird von build-appimage.sh und build-windows.sh aufgerufen.
#
#   packaging/werkzeuge.sh ZIELORDNER linux|windows
#
# Umgebung:
#   WERKZEUG_QUELLE=/opt/erech-tools  Mustang-CLI-*.jar, validator-*-standalone.jar, kosit-xr/
#   JDK=…/jdk-21.0.13+9               Linux-JDK (jlink, javac, jar) – Temurin 21
#   JMODS_WIN=…/win/jdk-21.0.13+9/jmods  jmods des Windows-JDK (nur für „windows“)
set -euo pipefail
cd "$(dirname "$0")/.."
ZIEL="$(realpath -m "${1:?Zielordner fehlt}")"; ZIELOS="${2:?linux|windows fehlt}"
QUELLE="${WERKZEUG_QUELLE:-/opt/erech-tools}"
JDK="${JDK:?JDK (Temurin 21, Linux) angeben}"
case "$ZIELOS" in
  linux)   JMODS="$JDK/jmods" ;;
  windows) JMODS="${JMODS_WIN:?JMODS_WIN angeben}" ;;
  *) echo "Ziel-OS: linux oder windows" >&2; exit 2 ;;
esac
# jdeps: Mustang braucht base, compiler, desktop, instrument, management, naming, sql, xml.dom;
# KoSIT zusätzlich logging, httpserver. Rest: Abhängigkeiten zur Laufzeit (Skripte, Zeichensätze, zip).
MODULE=java.base,java.compiler,java.desktop,java.instrument,java.management,java.naming,java.sql,java.xml,\
java.scripting,java.logging,java.prefs,java.datatransfer,jdk.xml.dom,jdk.httpserver,jdk.unsupported,\
jdk.charsets,jdk.zipfs

rm -rf "$ZIEL"; mkdir -p "$ZIEL/lizenzen/jar-Lizenzen/Mustang" "$ZIEL/lizenzen/jar-Lizenzen/KoSIT"
"$JDK/bin/jlink" --module-path "$JMODS" --add-modules "$MODULE" --strip-debug --no-man-pages \
  --no-header-files --compress=zip-6 --output "$ZIEL/jre.tmp"
cp -rL "$ZIEL/jre.tmp" "$ZIEL/jre"; rm -rf "$ZIEL/jre.tmp"          # legal/ ohne Symlinks (ZIP)
chmod -R u+w "$ZIEL/jre"                                          # jlink legt legal/ schreibgeschützt an; sonst scheitert das Aufräumen späterer Builds
cp "$JDK/NOTICE" "$ZIEL/jre/NOTICE"

MUSTANG="$(ls "$QUELLE"/Mustang-CLI-*.jar | sort -V | tail -1)"
KOSIT="$(ls "$QUELLE"/validator-*-standalone.jar | sort -V | tail -1)"
cp "$MUSTANG" "$KOSIT" "$ZIEL/"
cp -r "$QUELLE/kosit-xr" "$ZIEL/kosit-xr"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
"$JDK/bin/javac" --release 21 -encoding UTF-8 -cp "$MUSTANG" -d "$TMP/klassen" packaging/werkzeuge/Pruefdienst.java
"$JDK/bin/jar" --create --file "$ZIEL/fakturafalter-pruefdienst.jar" -C "$TMP/klassen" .

cp packaging/lizenzen/werkzeuge/*.txt "$ZIEL/lizenzen/"
(cd "$TMP" && unzip -q -o "$MUSTANG" 'META-INF/*LICENSE*' 'META-INF/*NOTICE*' 'META-INF/licenses/*' -d m 2>/dev/null || true
 cp -r m/META-INF/. "$ZIEL/lizenzen/jar-Lizenzen/Mustang/" 2>/dev/null || true
 unzip -q -o "$KOSIT" 'LICENSE*' 'META-INF/NOTICE' 'org/xmlresolver/notices/*' -d k 2>/dev/null || true
 cp -r k/. "$ZIEL/lizenzen/jar-Lizenzen/KoSIT/" 2>/dev/null || true)
sed -n 's/^JAVA_VERSION="\(.*\)"/Java-Laufzeit: Temurin \1/p' "$ZIEL/jre/release" > "$ZIEL/VERSIONEN.txt"
echo "Mustang: $(basename "$MUSTANG")  KoSIT: $(basename "$KOSIT")" >> "$ZIEL/VERSIONEN.txt"
# appimagetool warnt, wenn Ordner (typisch kosit-xr aus der Quelle) Modus 0700 haben
chmod -R a+rX "$ZIEL"
du -sh "$ZIEL"
