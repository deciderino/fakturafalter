# Fakturafalter 1.0.0-rc1

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Erstes Release Candidate auf dem Weg zu 1.0. Profile aus 0.9.11 werden
abgelehnt und nicht umgeschrieben. Der Kundenstamm entfällt; der Kundenname
kommt aus der Quelle. Eine zusätzliche XRechnung hängt an einer einfachen
Liste in den Einstellungen. Vorheriger Stand: 0.9.11.2 (bleibt die aktuelle
stabile Linie, bis 1.0 erscheint).

## Was sich ändert

- **Profilformat 2.** CSV-Profile tragen `version: 2`. Eine Zuordnung aus
  0.9.11 (oder mit den alten Schlüsseln `gesamt_kontrolle`, `kaeufer_name_2`,
  `kaeufer_name_3`) wird nicht gelesen. Die Datei bleibt unverändert liegen.
  In der Oberfläche steht in der Du-Form, was du tun kannst: die Zuordnung im
  Assistenten **neu einrichten** (eine Beispiel-CSV aus deiner Warenwirtschaft
  (ERP) reicht) oder bei **0.9.11** bleiben. PDF-Druckvorlagen bleiben im
  bisherigen Format und werden nicht als CSV-Profil geprüft.

- **Feldschlüssel.** `gesamt_kontrolle` heißt jetzt `gesamtpreis_position`
  (Label behält „nur Kontrolle“; Fakturafalter rechnet weiter selbst
  Menge × Einzelpreis ÷ Preisbasis). Nur `kaeufer_name_2` / `kaeufer_name_3`
  werden zu `kunden_name_2` / `kunden_name_3`. BT-IDs, `steuer`, die
  Skonto-Schlüssel und die Textzeilen-Schlüssel bleiben.

- **Rechnungsnummer.** Das Pflichtlabel bleibt „Rechnungsnummer“. Tooltip und
  Suche kennen zusätzlich Belegname und Belegnummer.

- **Kein Kundenstamm.** `kundenstamm.csv`, `kundenstamm_fuer` und das
  Ausgabeformat `aus_kundenstamm` entfallen. Der Kundenname (BT-44) ist Pflicht
  und kommt aus der Quelle (CSV, XML oder Rechnungsdruck). Die Kundennummer
  (BT-46) ist optional. Die Pflichtkarte heißt „Kundenname“. Eine Spalte
  „Kunde“ mit Werten wie `K-1001` wird weiter als Kundennummer vorgeschlagen;
  trotzdem muss eine Namensspalte zugeordnet werden. Lastschrift-Mandat und
  Kunden-IBAN stehen ebenfalls in der Quelle.

- **XRechnung-Liste.** Unter Einstellungen → Ausgabe gibt es den Schalter
  „XRechnung zusätzlich erzeugen“ und eine einfache Liste (Kundenname und/oder
  Kundennummer, optionale Leitweg-ID BT-10). Ist der Schalter an, bekommt jede
  Rechnung, deren Name oder Nummer einen Eintrag trifft, zusätzlich zur
  ZUGFeRD-PDF eine XRechnung (CII, XRechnung-konform, lokal mit KoSIT geprüft).
  Die Leitweg-ID aus der Quelle hat Vorrang. Die XRechnung braucht die
  E-Rechnungsadresse des Kunden (BT-49) aus der Quelle; fehlt sie, entsteht
  keine ungültige Datei, sondern die Rechnung geht mit klarem Hinweis nach
  „Zu prüfen“. Der Listenvergleich nimmt den ganzen Kundennamen oder die erste
  Namenszeile (Groß/Klein und Leerzeichen egal). Eine frühere Einstellung „XRechnung,
  wenn der Kundenstamm es verlangt“ ohne Liste wird nicht still auf alle
  Rechnungen angewendet, sondern mit einem klaren Hinweis angezeigt.
  *Nicht unterstützt:* XRechnung UBL als zusätzliche Datei (ein altes
  `XRECHNUNG_UBL` erzeugt CII und einen Hinweis).

- **Feld suchen.** In beiden Assistentenwegen (Spalten je Block und eine Zeile
  je Position) steht über der gruppierten Liste das Feld „Feld suchen …“. Es
  filtert beim Tippen nach Label, Tooltip und typischen Spaltennamen
  („gesamtpreis“, „ustsatz“, „belegname“). Enter wählt den ersten Treffer,
  Escape leert die Suche. Gruppenköpfe sind nicht wählbar, Pflichtfelder tragen
  einen Stern, amtliche Felder ihre BT-Nummer. Jedes der 98 Felder hat einen
  Tooltip mit kurzem Beispiel.

- **Neue Bezeichnungen.** Zum Beispiel „Gesamtpreis der Position (nur
  Kontrolle)“, „Preiseinheit / Preisbasis“, „Steuersatz oder Steuerschlüssel“,
  „Leistungs- oder Lieferdatum“, „Kundenname (Zeile 1–3)“. Die Pflichtkarte
  nutzt dieselben Wörter. Die Schalter heißen jetzt z. B. „Wenn die Einheit
  fehlt, Stück eintragen“ und „Es gibt Zeilen nur mit Text, ohne Menge und
  Preis“ und zeigen ein Beispiel als Hinweis.

- **Automatik.** „Gesamtpreis“ im Positionsblock wird der Gesamtpreis der
  Position, nicht der Rechnungsbetrag. „Gesamtnetto“ im Positionsblock ebenso,
  sonst der Rechnungsbetrag netto. „Rabatt“ allein wird nicht mehr automatisch
  als Prozentsatz zugeordnet (dafür „Rabatt%“ oder „Rabattsatz“).

- **Wo die Ablehnung erscheint.** Beim Start (Dialog mit „Assistent öffnen“ und
  „Schließen“), an der Profilkarte in den Einstellungen („Warum?“), bei
  „Profil übernehmen…“ (es wird nichts kopiert), bei „Profil testen…“ und im
  Eingang (Fehlermeldung nennt das abgelehnte Profil).

- **Beispiel-CSV und Vorlagen.** „CSV-Vorlage speichern…“ schrieb in der
  Minimalvorlage die Kundennummer in die Spalte Kundenname. Behoben; die
  Vorlagen tragen jetzt Kundenname und Anschrift, die Vollvorlage auch die
  E-Rechnungsadresse. Beide Beispielrechnungen gehen ohne Prüffall durch.

- **Standard-CSV.** Die Pflichtnamen des eingebauten Formats enthalten
  `Kundenname` statt `Kundennummer`. `Kundennummer` bleibt eine optionale
  Spalte. Einzelheiten: [csv-standard.md](csv-standard.md) (Spezifikation 1.6)
  und [csv-format.md](csv-format.md). Geplante und nicht unterstützte Punkte
  stehen dort in den Statusmarkern.

## Neu einrichten

1. Eine typische Export-Datei aus der Warenwirtschaft (ERP) bereitlegen – mit
   einer Spalte für den Kundennamen.
2. Einstellungen → Eingang & Vorlagen → **Neue CSV einrichten…** und die
   Zuordnung speichern (Profilformat 2).
3. Wer zusätzlich XRechnungen braucht: Einstellungen → Ausgabe → Schalter
   einschalten und die Liste (Name und/oder Nummer, optional Leitweg-ID)
   ausfüllen.
4. Mit einer fiktiven Testdatei und „Profil testen…“ gegenprüfen.

Die alte Profildatei kannst du als Erinnerung liegen lassen; Fakturafalter
ändert sie nicht.

## Prüfung

Lokal, ohne CI, nur fiktive Daten. Volle Testsuite, neue Tests zu
Profilablehnung, Schlüssel-Umbenennung, Kundenname-Pflicht, XRechnung-Liste
(Treffer per Name, per Nummer, kein Treffer, Schalter aus) und Suche/Gruppen.
Mustang- und KoSIT-Prüfung der Beispielrechnungen (ZUGFeRD und XRechnung).
Wizard-Durchlauf mit einem fiktiven Blockformat (Kopf-/Positionsblöcke,
0x1A-Endzeile, EURO). AppImage und Windows-ZIP mit Rauchtest.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
