# F1 Infozeilen (nach weclapp, Q1)

Absender: Kaltwasser Armaturen GmbH, Kassel (fiktiv). Schrift Helvetica 9 pt, A4. Wortlaut wie in der Vorlage.

Was ist besonders:
- Zweispaltiger Infoblock „Label: Wert“ unter dem Titel: Rechnungs-Nr., Auftrags-Nr., Komission, Kunden-Nr.,
  Bestell-Nr. | Rechnungsdatum, Lieferdatum, Bearbeiter, Telefon, E-Mail.
- Datum kurz als TT.MM.JJ, auch im Zahltext.
- Menge mit zwei Nachkommastellen, Preise ohne €, Summen mit vorangestelltem € („€ 1.023,42“).
- Summen „Summe Netto“ / „19,00% USt. auf 860,02 €“ / „Endsumme“.
- Leerzeile zwischen Positionen; Versand als letzte Position; „Lieferbedingung“ zwischen Summen und Zahltext.
- Zahltext „10 Tage 2% Skonto, 30 Tage ohne Abzug“ bzw. „14 Tage ohne Abzug“.

Soll-Werte: BT-13 ist die Bestell-Nr. Die Auftrags-Nr. (O1xxx) ist die Nummer des Verkäufers und steht nur in
`test_flags.auftragsnummer`.

Fälle: 1–3 Training (Skonto; 14 Tage ohne Abzug; 3 Namenszeilen und festes Datum ohne Bestellnummer).
4–5 Hold-out (3 % Skonto; **Prüfen**: gedrucktes Netto 10,00 € über Σ Positionen, USt und Brutto richtig).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `summe_positionen` (Versand nicht im Netto), 7 **Falle** `angebot_nr` (Angebots-Nr. unter der Rechnungs-Nr.). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Stand der Erkennung bei Erstellung (nicht angepasst, Befunde):
- „Endsumme“ trifft das Netto-Muster („summe“) und fehlt im Brutto-Muster: Netto/Brutto werden falsch oder gar
  nicht gelesen.
- „Auftrags-Nr.“ trifft das BT-13-Muster (`auftrag`) und kann vor der Bestell-Nr. gewinnen.
- „N Tage ohne Abzug“ ohne „zahlbar/fällig/Zahlungsziel“ startet keinen Zahltext; BT-9 und BT-20 können fehlen.
