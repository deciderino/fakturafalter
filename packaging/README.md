# Pakete bauen

Alle Pakete sind PyInstaller-onedir-Builds (kein onefile: schneller Start, kein Entpacken nach %TEMP%).
Beide Pakete enthalten die Prüfwerkzeuge im Ordner `werkzeuge/` neben dem Programm (siehe unten).
Ergebnisse landen in `dist/` (nicht im Repository).

| Ziel | Befehl | Ergebnis |
|---|---|---|
| Linux AppImage | `JDK=… PYTHON=… APPIMAGETOOL=… EXTRA_LIBS_DIR=… packaging/linux/build-appimage.sh` | `dist/Fakturafalter-<V>-x86_64.AppImage` |
| Windows ZIP (Wine) | `JDK=… JMODS_WIN=… WINEPREFIX=… packaging/windows/build-windows.sh` | `dist/win/Fakturafalter-<V>-Windows-x86_64.zip` |
| Windows ZIP (nativ) | venv, `pip install .[gui] pyinstaller`, `build/werkzeuge-win` vorher erzeugen, `python packaging\windows\build.py` | wie oben |
| nur Prüfwerkzeuge | `JDK=… [JMODS_WIN=…] packaging/werkzeuge.sh ZIEL linux\|windows` | `ZIEL/` |
| Teile à 20 MB | `packaging/teile.sh` | `dist/teile/` + `SHA256SUMS` + `ZUSAMMENSETZEN.txt` |
| Testdaten | `packaging/testdaten.sh` | `dist/Fakturafalter-<V>-Testdaten.zip` (beispiele/ + ANLEITUNG.txt) |

Details zu den Umgebungsvariablen stehen jeweils im Kopf der Skripte.

## Prüfwerkzeuge (`werkzeuge/`)

`packaging/werkzeuge.sh` stellt zusammen (alles offline aus lokalen Quellen):

- `jre/` – minimale Java-Laufzeit per `jlink` aus Eclipse Temurin 21 (`JDK=` Linux-JDK für jlink;
  für Windows zusätzlich `JMODS_WIN=` = `jmods/` eines Windows-Temurin-JDK derselben Version)
- `Mustang-CLI-*.jar` (enthält veraPDF), `validator-*-standalone.jar` (KoSIT) und `kosit-xr/`
  (XRechnung-Konfiguration mit EN-16931-Schematron), Quelle `WERKZEUG_QUELLE` (Standard `/opt/erech-tools`)
- `fakturafalter-pruefdienst.jar` – kleiner Helfer aus `werkzeuge/Pruefdienst.java`: prüft alle PDFs
  eines Stapels in einer JVM
- `lizenzen/` (Texte aus `lizenzen/werkzeuge/` + Lizenzdateien aus den Jars), `VERSIONEN.txt`

Größe: rund 135 MB entpackt. Ohne `JDK` bauen die Skripte ein Paket ohne Prüfung (mit Warnung);
das Programm meldet dann „Prüfung: Werkzeuge fehlen“.

Lizenzen: Temurin GPLv2 mit Classpath Exception (schriftliches Quellcode-Angebot in
`lizenzen/werkzeuge/PRUEFWERKZEUGE.txt`), Mustang und KoSIT Apache-2.0, Saxon-HE/veraPDF MPL-2.0,
EN-16931-Schematron EUPL-1.2. Keine AGPL. `lizenzen.py` hängt die Übersicht an `DRITTANBIETER.txt` an.

## Rauchtest

```
python packaging/smoke.py --headless-sekunden 90 -- dist/Fakturafalter-<V>-x86_64.AppImage
python packaging/smoke.py --wine --headless-sekunden 120 -- wine dist/win/Fakturafalter/fakturafalter-cli.exe
```

Schickt `beispiele/` (Varianten a, b, c) mit `--einmal` durch, prüft Ausgänge und Fehlerordner und testet
`--headless` (Datei nachlegen, Protokoll muss wachsen). Arbeitsordner: `/tmp/Fakturafalter-Beispiel-smoke`.
Das Programm prüft dabei mit seiner eigenen Java-Laufzeit: erwartet wird „gültig“ in Spalte 8 von
`Protokoll/protokoll.tsv`, dazu ein `--pruefe`-Aufruf. Ab 0.9.6 außerdem: Ausgang ohne Temp-/Zwischendateien
und ohne `protokoll.tsv`, kein `fakturafalter-…`-Rest im System-Temp, XRechnung im Unterordner (Variante b) und
`--headless` ohne Netz (`unshare -rn`) mit stiller Updateprüfung. `FAKTURAFALTER_*` wird vorher aus der Umgebung
entfernt.
Paket ohne Werkzeuge: `--ohne-werkzeuge`.
Im Container ohne FUSE: `APPIMAGE_EXTRACT_AND_RUN=1`.

## Weitere Dateien

- `start.py` – Einstieg der gebündelten Programme
- `lizenzen.py` – sammelt Lizenztexte aller Abhängigkeiten, bricht bei AGPL ab
- `lizenzen/` – LGPL-3.0/GPL-3.0-Texte für Qt/PySide6 (das Wheel bringt keine mit)
- `icon.py` – zeichnet `fakturafalter.png` und `windows/fakturafalter.ico`

Windows: `Fakturafalter.exe` (ohne Konsole, für Doppelklick/Autostart) und `fakturafalter-cli.exe`
(Konsole, für `--einmal`/`--headless`/Skripte) teilen sich `_internal/`. Die Programme sind nicht signiert.
