# F7 DIN 5008 (nach Odoo-Rechnungsbericht, Modul l10n_din5008, Q9)

Absender: Nordlicht Software GmbH, Kiel (fiktiv). Schrift Helvetica 9 pt (Odoo: Lato). Wortlaut wie im
Odoo-Bericht.

Was ist besonders:
- Informationsblock rechts mit Rechnungsnr. / Rechnungsdatum / Fälligkeitsdatum / Lieferdatum / Quelle / Referenz,
  Label und Wert in zwei Spalten **ohne Doppelpunkt**.
- „Quelle“ ist der Verkaufsauftrag des Verkäufers (`test_flags.quelle`, nicht BT-13), „Referenz“ die
  Kundenreferenz = BT-13. Beleg 2 und 5 ohne Referenz.
- **Keine Kundennummer**: Der Odoo-Bericht druckt keine (`Familie.kundennummer_gedruckt = False`, Soll leer).
- Überschrift „Rechnung INV/2026/000NN“; Tabelle Beschreibung | Menge („2,00 Stück“) | Einzelpreis | Steuern
  („19%“) | Betrag („240,00 €“).
- Summen rechts Nettobetrag / Umsatzsteuer 19% / Gesamt; „Zahlungsbedingungen: N Tage“ und „Bitte verwenden Sie
  die folgende Mitteilung für Ihre Zahlung: INV/…“. Fuß in vier Spalten mit USt-IdNr., HRB Nr:, IBAN:, BIC:.

Fälle: 1–3 Training (Lizenzen und Stunden mit Referenz; ohne Referenz, mehrzeilig; Behörde mit Sachgebiet als
2. Namenszeile). 4–5 Hold-out (3 Namenszeilen; **Prüfen**: gedrucktes Gesamt 1,00 € über Netto + USt).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `faelligkeit_vor_datum` (Fälligkeitsdatum 30 Tage vor dem Rechnungsdatum). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- Positionen im Kaltstart nur teilweise: Die Tabelle ohne Pos.-Spalte wird bei mehrzeiligen Beschreibungen
  zerlegt; Σ Positionen ≠ Netto.
- Angelernt: Die gelernte Vorlage liest die Summen aus der ersten Positionszeile (BT-109/110/112 falsch) und
  die Positionsspalten verschoben.
- BT-20: Als Zahltext wird „Fälligkeitsdatum“ aus dem Infoblock gelesen statt „Zahlungsbedingungen: N Tage“;
  BT-9 fehlt, obwohl „Fälligkeitsdatum“ mit Datum gedruckt ist.
- Einheit: „Stunde(n)“ wird als H87 gelesen bzw. fehlt.
- Prüfen-Fall Beleg 5 wird im Kaltstart erkannt (BT-112 gelesen 1192,38 statt Soll 1191,38, Hinweis
  Summenabweichung).
