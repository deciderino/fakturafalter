# Fakturafalter 0.9.11

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Freies Festlegen der Blöcke, manuelle Blockart, Satzart-Wert in der Datenzeile, lesbare Farben im dunklen Theme und ruhigeres Scrollen. Vorheriger Stand: 0.9.10.

## Was sich ändert

- **Blöcke festlegen:** Blöcke kannst du selbst anlegen, entfernen, umbenennen und als Bereich aufziehen. Die Anfangsregel wird aus den ersten inhaltlichen Zeilen abgeleitet: Satzart-Wert (auch wenn weitere Zellen in derselben Zeile Daten tragen, z. B. `#Kopf;Testkunde;…`), dann die enge Markerform, dann die Kopfzeile davor. Das Blockende ist der nächste erkannte Blockstart oder das Dateiende. Zeilennummern werden nicht gespeichert.

- **Blockart manuell:** Jeder Block ist ein *normaler Block* oder *sich wiederholend (Positionsblock)*. Die Art wird nicht aus zugeordneten Feldern abgeleitet. Im Positionsblock ist jede Zeile eine Position. Ein normaler Block liefert nur einen Teil der Rechnungsinfo (Kunde, Beleg, Summen); die Rechnung entsteht aus allen Blöcken zusammen. Dasselbe Feld in mehreren Blöcken wird verglichen, eine Abweichung führt die Rechnung nach „Zu prüfen“. Mehrere normale Blöcke (z. B. Kunde und Beleg, früher beide typ `kopf`) teilen sich die Zuordnung nicht mehr – die Rechnungsnummer geht nicht verloren.

- **Weiter:** Auf der Blockseite ist Weiter nur gesperrt, wenn kein Block existiert oder ein Block keine Zeilen hat. Fehlende Anfangsregel oder nicht genau ein wiederholender Block sind Warnungen. In **Spalten je Block** geht Weiter erst, wenn Rechnungsnummer (BT-1), Rechnungsdatum (BT-2), Bezeichnung, Menge, Einzelpreis, Steuer und Käufername (BT-44) oder Kundennummer (über den Kundenstamm) zugeordnet sind. Die Tabelle in diesem Schritt ist höher.

- **Farben und Scrollen:** Eigenes dunkles Blockfarben-Set mit fest hinterlegter Schriftfarbe (WCAG AA); auch im hellen Theme ist die Schriftfarbe gesetzt. Es scrollt nur die Tabelle, nicht die ganze Seite. Beim Ziehen einer Grenze wird zuerst nur umgefärbt, übernommen wird beim Loslassen; die Scrollposition bleibt, am Rand rollt die Tabelle selbst nach. Getestet unter Bazzite/KDE (Wayland) in der Planung; der automatische Rauchtest läuft offscreen.

- **Satzart und Migration:** Der Aufbau `art: satzart` bleibt parallel. Profile aus 0.9.10 und 0.9.9.x werden weiter geladen. Optionale Felder bleiben optional. Die Exportspezifikation liegt unter `docs/csv-standard.md` (Stand 1.5); der Export-Standard bleibt eine Zeile je Position.

## Prüfung

Lokal: gezielte Tests zur fiktiven Datei mit `#Kopf`/`#Beleg` in der Satzart-Spalte einer Datenzeile (kurze Datumsangaben, getrennte Blöcke Kunde und Beleg, Rechnungsnummer erhalten), Kontrast der Blockpalette, Migration älterer Blockprofile, bestehende Block-, Assistenten-, Standardprofil- und Skonto-Tests, Übersetzungen, plus Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
