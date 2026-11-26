# Fakturafalter 0.9.10

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Farbiger Assistent für CSV-Blockdateien, Satzart als Anfangsregel und gemeinsamer Lesepfad für Probe und Eingang. Vorheriger Stand: 0.9.9.1.

## Was sich ändert

- **Blöcke festlegen:** Bei erkanntem oder gewähltem Aufbau „Blöcke“ folgt nach dem Format die farbige Tabelle (Kopf blau, Positionen grün, Summen orange). Grenzen lassen sich mit der Maus ziehen oder Zeilen markieren und einem Typ zuweisen. Genau ein Block wiederholt sich (Positionen). Jeder Block braucht eine Anfangsregel: zuerst Marker, dann Satzart-Wert, dann Kopfzeile. Zeilennummern werden nicht gespeichert. Einen Bereich ohne Regel zu markieren ist in der Sitzung erlaubt; Weiter und Speichern erst mit Regel, sonst der Hinweis „Block ohne erkennbaren Anfang“.

- **Spalten je Block:** In Reitern pro Block eine Spalte anklicken, das Feld zuordnen und den ersten Beispielwert sehen. Dieselbe Position darf im Kopf ein anderes Feld sein als in den Positionen. Name und 1-basierte Position werden gespeichert; beim Lesen hat der Name Vorrang, wenn die Kopfzeile ihn trägt. Positionsfelder gehören nur in den wiederholenden Block. Ein Kopffeld in mehreren Blöcken wird verglichen (Abweichung → Zu prüfen). Pflichtprüfung erst an der ganzen Rechnung.

- **Gemeinsamer Lesepfad:** Probe und Eingang lesen eine Blockdatei mit derselben Funktion. Alte 0.9.8/0.9.9/0.9.9.1-Blockprofile bleiben gültig (`anfang` wird aus Marker oder Kopfzeile abgeleitet). Passen mehrere Profile, gewinnt das spezifischste, bei Gleichstand das weiter vorne in der Liste. Endet das Lesen mit „Spalte fehlt“, wird das nächste passende Profil versucht oder die Meldung um den Profilnamen ergänzt.

- **Satzart:** Im Blockmodus eine Anfangsregel, auch neben Markern und Kopfzeilen (K, P, S oder ein eigener Kennwert). Eine zweite Kopf-Satzart in derselben Datei geht nach „Zu prüfen“ (eine Datei = eine Rechnung); wiederholte Positions-Satzart (P, P, …) ist normal. Der bisherige Aufbau `art: satzart` bleibt parallel; dort sind Kennwerte außer K/P ebenfalls eintragbar.

- **Nicht-Blockdateien** (`zeile_je_position`) behalten den bisherigen Assistenten-Ablauf.

Ein Block-Assistent mit farbigem Festlegen war in 0.9.9.1 noch als geplant gekennzeichnet; er ist Teil dieser Version. Die Exportspezifikation liegt unter `docs/csv-standard.md` (Stand 1.4); der Export-Standard bleibt eine Zeile je Position.

## Prüfung

Lokal: gezielte Tests zu den fiktiven Satzart-Blockdateien (eigene Kopfzeilen, Marker, gleiche Position mit anderer Bedeutung, ohne Block-Kopf), Probe und Eingang trotz älterem Hotel-Profil, Migration der bisherigen Blockbeispiele, Kopffeld-Vergleich, zweite Kopf-Satzart, Synonym „Gesamt USt“, bestehende Block-, Textzeilen-, Assistenten-, Standardprofil- und Skonto-Tests, Übersetzungen, plus Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
