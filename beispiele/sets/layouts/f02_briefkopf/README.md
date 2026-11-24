# F2 Briefkopf (nach Lexware Honorarrechnung, Q2)

Absender: Ingenieurbüro Brandauer GmbH, Göttingen (fiktiv). Schrift Times 10 pt, Logo als PNG-Bild.
Wortlaut wie in der Vorlage.

Was ist besonders:
- Briefstil: Logo rechts oben, unterstrichene Absenderzeile, Anrede, Einleitungssatz, „Herzliche Grüße,“,
  zweizeiliger Fuß.
- Rechter Block mit „Tel.:“, „E-Mail:“, „Kundennummer:“, „Liefer-/Leistungsdatum:“.
- Das Rechnungsdatum steht **nur** in „Göttingen, den 15. Oktober 2026“ (ausgeschrieben, ohne Label) neben
  „Honorarrechnung Nr. …“.
- Tabelle Pos. | Menge („1,5 Std.“ in einer Spalte) | Bezeichnung | Einzelpreis | Gesamtpreis, graue Kopfzeile,
  gepunktete Trennlinien, Beträge mit „EUR“.
- Zahltext „Zahlung innerhalb von 14 Tagen ab Rechnungseingang ohne Abzüge an die unten angegebene
  Bankverbindung.“ (zweizeilig); Skonto und festes Datum im selben Satzbau, das Datum ausgeschrieben.
- Keine Bestellnummer (die Vorlage hat keine).

Fälle: 1–3 Training (14 Tage; Skonto in Tagen; 3 Namenszeilen und festes Datum ausgeschrieben).
4–5 Hold-out (**A5**: Koordinaten × 0,7071, Fuß vierzeilig; **Prüfen**: gedruckter Gesamtbetrag 1,00 € über
Netto + USt).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `iban_pruefziffer` (IBAN im Fuß ungültig). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Stand der Erkennung bei Erstellung (nicht angepasst, Befunde):
- BT-2: „Ort, den <ausgeschriebenes Datum>“ ohne Label „Datum“ wird nicht als Rechnungsdatum gelesen.
- BT-9: „Zahlung innerhalb von N Tagen ab Rechnungseingang“ und „Zahlung bis zum <ausgeschriebenes Datum>“
  passen nicht auf die Fälligkeitsmuster; „Zahlung …“ startet keinen Zahltext (BT-20).
- „Menge“ mit Einheit in einer Spalte („1,5 Std.“) kann die Einheitenerkennung verfehlen.
