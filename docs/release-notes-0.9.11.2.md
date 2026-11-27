# Fakturafalter 0.9.11.2

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Korrektur zum Positionsblock und zur Währung nach 0.9.11.1: Eine kurze Restzeile
nach den Positionen (oder eine Text-/Leerzeile) löst nicht mehr „Spalte … fehlt“
aus, die Schreibweisen EURO / Euro / € / EUR werden zu EUR, und Hinweise nennen
den Block. Vorheriger Stand: 0.9.11.1.

## Was sich ändert

- **Positionsblock:** Die Kopfzeile vor den `#Pos`-Zeilen gehört zum
  Positionsblock und gilt für alle folgenden Positionszeilen. Steht in einer
  Instanz keine eigene Kopfzeile, gelten die gespeicherte Kopfzeile und die
  Spaltenposition aus dem Profil. Text-, Leer- und kurze Restzeilen werden
  erkannt, bevor Pflichtspalten geprüft werden – eine einzelne Restzeile am
  Dateiende führt nicht mehr zu „Spalte Bezeichnung/Menge/Einzelpreis/Ust-Satz
  fehlt“. Die Warnung „Einheit fehlte, Stück angenommen“ erscheint weiter nur
  bei wirklich leerer Einheit und eingeschaltetem Schalter.

- **Währung:** Die Schreibweisen `EURO`, `Euro`, `€` und `EUR` werden beim
  Lesen einheitlich zu `EUR` (ISO 4217). Die Pflichtprüfung „kein ISO-4217-Code“
  und die Warnung BT-81 (Rechnung vs. SEPA in EUR) bleiben dann aus. Steht im
  Profil Windows-1252, die Datei ist aber gültiges UTF-8, wird UTF-8 verwendet
  (sonst zerfällt z. B. „Währung“).

- **Meldungen:** Fehlt eine Pflichtspalte wirklich, nennt der Hinweis den
  Block (und den Profilnamen, falls gesetzt), nicht nur den Spaltennamen.

- **Bestehende Profile:** Ein in 0.9.11 oder 0.9.11.1 gespeichertes Blockprofil
  musst du nicht neu anlegen.

## Prüfung

Lokal: fiktive Datei `beispiele/beispiel-satzart-pos-kopf-und-restzeile.csv`
(`#Kunde` / `#Beleg` / `#Pos`, Kopfzeile vor den Positionszeilen, Währung
`EURO`, Textzeilen mit Menge 0, eine dritte Position ohne Einheit, eine
einspaltige Restzeile am Ende). Probe-Liste, Sichtseiten-Lesen und Eingang
dasselbe Ergebnis: drei Positionen, Währung EUR, keine Meldung „Spalte … fehlt“,
Warnung nur bei der dritten Einheit. Ältere typ-`kopf`-Profile und neue Profile
(Anfangsregel Satzart zuerst, ohne festes EUR) werden beide geladen.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
