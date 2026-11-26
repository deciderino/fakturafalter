# Fakturafalter 0.9.9

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Strukturiertes Skonto, eingebautes CSV-Standardprofil und überarbeitetes CSV-Blocklayout. Vorheriger Stand: 0.9.8.4.

## Was sich ändert

- **Strukturiertes Skonto:** Bis zu zwei Stufen aus der CSV, dem Kundenstamm oder einer Vorgabe im Absenderprofil. Sobald Satz und Tage einer Stufe gesetzt sind, stehen in den Zahlungsbedingungen (BT-20) zuerst die maschinenlesbaren Zeilen `#SKONTO#TAGE=…#PROZENT=…#` (optional `BASISBETRAG`), danach derselbe deutsche Klartext wie bisher. Der sichtbare Rechnungsteil zeigt nur den Klartext. Das Fälligkeitsdatum (BT-9) bleibt das Netto-Ziel. Verzug oder Mahnung nur als Klartext in der Bemerkung, nie als `#VERZUG#`. Ein XML-Import übernimmt vorhandene `#SKONTO#`-Zeilen.

- **Eingebautes CSV-Standardprofil:** Trägt die Kopfzeile die neun Pflichtnamen (`Rechnungsnummer`, `Rechnungsdatum`, `Leistungsdatum`, `Kundennummer`, `Bezeichnung`, `Menge`, `Einheit`, `Einzelpreis`, `Steuersatz`), greift das Profil `fakturafalter-standard` – mit letzter Priorität, bestehende Zuordnungen bleiben unangetastet. Unbekannte Spalten werden ignoriert und im Protokoll erwähnt (kein Prüffall). Widersprüchliche Kopffelder derselben Rechnung und unbekannte Einheiten gehen nach „Zu prüfen“. `Stück` wird zu H87, Tausenderpunkte werden gelesen. Unter Einstellungen → Eingang & Vorlagen → „CSV-Vorlage speichern…“ gibt es eine Minimal- und eine Vollvorlage (UTF-8 mit BOM). Die Exportspezifikation liegt unter `docs/csv-standard.md` (Stand 1.3).

- **CSV-Blocklayout:** Eine Datei bleibt eine Rechnung. Welche Felder in welchem Block stehen, ist frei wählbar; die Pflichtprüfung läuft am Ende. Optional erkennt ein Block eine Markerzeile (`#Kopf`, `#Positionen`, auch ohne `#`; `#LEER` bleibt reserviert). Die Kopfzeile nach einem Marker ist optional, wenn das Profil die Spalten kennt. Text zwischen zwei Positionen gehört standardmäßig zur oberen; `zwischen: nachher` wird ausgewertet. `0` / `0,00` in Menge oder Preis gilt wie im Standardaufbau als leer. Bestehende Block-Profile laufen ohne Anpassung weiter. Im Assistenten: zuerst die Spalten, dann die Blöcke, dann die Textzeilen. Fiktive Beispiele: `beispiele/beispiel-bloecke-klassisch.csv`, `beispiel-bloecke-frei.csv`, `beispiel-bloecke-marker.csv`.

- **Zielgruppe:** In README und Handbuch steht, für wen Fakturafalter gedacht ist (regelmäßiger Einsatz, wenn die Warenwirtschaft kein ZUGFeRD erzeugt).

## Prüfung

Lokal: gezielte Tests zu Skonto (inkl. Mustang 2.26.0 und KoSIT 1.6.3 / XRechnung 3.0.2, eine und zwei Stufen), Standardprofil, Blocklayout (drei Beispiele und Grenzfälle, bestehende Block- und Textzeilen-Tests), Sichtseite und betroffene Module, plus Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
