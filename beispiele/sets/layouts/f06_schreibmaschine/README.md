# F6 Schreibmaschine (nach DATEV Warenwirtschaft, Musterbeleg Rechnung, Q6)

Absender: Holzwerkstatt Brenneisen GmbH, Titisee-Neustadt (fiktiv), Zeile „Schreinerei und Ladenbau“.
Durchgehend Courier. Wortlaut wie im Musterbeleg.

Was ist besonders:
- Rechts „RECHNUNG“ mit Nummer / Datum / Kunden-Nr. / Lieferdatum / Auftragsnummer **ohne Doppelpunkt** in zwei
  Spalten, darunter „Lieferung frei Haus“ und „Seite N“.
- Die Auftragsnummer ist die Nummer des Verkäufers: `test_flags.auftragsnummer`, BT-13 leer.
- Tabelle Pos | Artikel | Bezeichnung | Menge (zwei Nachkommastellen) | Einheit („Stück“/„Stunden“) | USt% |
  Preis | Betrag EUR.
- Gruppen-„Zwischensumme“ mitten in der Tabelle (`test_flags.gruppen_zwischensumme`), beim Seitenumbruch
  „Übertrag“ unten und oben.
- Summen Zwischensumme / „19% MWSt auf EUR <Netto>“ / Endbetrag; „Zahlung: 30 Tage 2,0%; 60 Tage netto“ bzw.
  „Zahlung: N Tage netto“; Fuß mit Bank, BLZ, Konto, IBAN, BIC.

Fälle: 1–3 Training (Skonto 30/60 wie im Muster; Gruppen-Zwischensumme; 3 Namenszeilen, 2 Seiten). 4–5 Hold-out
(Gruppen-Zwischensumme mit mehrzeiligen Bezeichnungen; einfach mit Skonto).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `netto_brutto` (Zahlendreher im Endbetrag), 7 **Falle** `zweites_datum` (Auftragsdatum über dem Datum). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- Gruppen-Zwischensumme: Die Tabelle endet an der ersten „Zwischensumme“; die Positionen danach fehlen
  (Beleg 2: 5 von 10, Beleg 4: 4 von 8).
- Absender.name: Der Firmenname groß links oben wird nicht als Absender gelesen (0/5).
- BT-13: Die Auftragsnummer des Verkäufers landet in BT-13 (soll leer).
- BT-20/BT-9/Skonto: „Zahlung: 30 Tage 2,0%; 60 Tage netto“ startet keinen Zahltext; als Fälligkeit wird das
  Lieferdatum gelesen.
- Angelernt: Nach zwei Paaren gilt die Vorlage noch nicht als sicher, Beleg 3–5 werden nicht gelesen.
