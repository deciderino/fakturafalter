# Fakturafalter 0.9.9.1

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Genauere CSV-Profilerkennung im Eingang und Korrektur des Vorschlags „Gesamt USt“. Vorheriger Stand: 0.9.9.

## Was sich ändert

- **Block-Profilerkennung:** Ein Block-Profil greift nur noch, wenn alle ihm zugeordneten Spalten als Kopfzeile in der Datei stehen. Ein älteres Profil (zum Beispiel eine Hotel-Zuordnung mit Muster `*.csv`) zieht eine fremde Blockdatei nicht mehr nur wegen gemeinsamer Namen wie Rechnungsnr oder Artikel an sich. Passen mehrere Profile eindeutig, gewinnt weiterhin das oberste aktive; das eingebaute Standardprofil bleibt zuletzt. Weitere Treffer weiter unten stehen im Protokoll und unter **Profil testen…**. Die Probe im Assistenten warnt, wenn im Eingang ein anderes Profil greifen würde.

- **Synonym „Gesamt USt“:** Die Spalte wird der Summe USt (BT-110) zugeordnet, nicht mehr dem Positionsbetrag netto (Kontrolle).

- **Hinweis im Block-Schritt:** Ist dasselbe Kopffeld in mehreren Blöcken angehakt, weist der Assistent darauf hin, dass die Werte verglichen werden und eine Abweichung nach „Zu prüfen“ führt.

Ein neuer Assistent mit farbigem Festlegen der Blöcke und Spalten je Block (Satzart als Anfangsregel) ist geplant und nicht Teil dieser Version.

## Prüfung

Lokal: gezielte Tests zur Profilerkennung (einschließlich fiktiver Blockdatei mit Satzart und älterem Hotel-Profil), Synonym „Gesamt USt“, bestehende Block-, CSV- und Textzeilen-Tests, Stichprobe Skonto und Standardprofil, plus Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
