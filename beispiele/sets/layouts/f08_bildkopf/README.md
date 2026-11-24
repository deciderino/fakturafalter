# F8 Bildkopf (nach Business Central Bericht 1306 „Standard-Verkaufsrechnung“, Q10)

Absender: Weserblick Elektrotechnik GmbH, Bremen (fiktiv). Schrift Times. **Volles Hold-out**: kein Beleg wird
angelernt, der Benchmark wertet nur „kaltstart (Hold-out)“.

Was ist besonders:
- Briefkopf (Firmenname mit Zeile darunter) und Fußzeile (Sitz, Register, Geschäftsführung) als **eingebettetes
  Bild** (Pillow, deterministisch); im Textlayer fehlen sie.
- Firmenblock rechts als Text in zwei Spalten (Telefonnr. / E-Mail / Homepage / USt-IdNr. / Bank / IBAN /
  SWIFT-Code).
- Anschrift links, darunter Debitorennr. und – falls vorhanden – Ihre Referenz (= BT-13).
- Rechts „Rechnung“ mit Rechnungsnr. / Buchungsdatum / Fälligkeitsdatum / Lieferdatum / Zahlungsbedingungen /
  Lieferbedingungen, Label und Wert nebeneinander ohne Doppelpunkt, **nie Label über Wert**.
- Tabelle Nr. | Beschreibung | Menge | Einheit („Stück“/„Stunde“) | VK-Preis | MwSt. % | Betrag; Summen
  Zwischensumme / Gesamt EUR ohne MwSt. / 19 % MwSt. / Gesamt EUR inkl. MwSt.
- Folgeseiten wiederholen Kopf und Tabellenkopf mit „Seite N“, **kein Übertrag** (`test_flags.uebertrag_gedruckt`
  = false; die Seitenwerte im JSON sind nur Rechenwerte).
- Genau ein Beleg (Nr. 4) mit Postfach-Anschrift (`test_flags.po_box`).

Fälle (alle Hold-out): 1 Ihre Referenz; 2 drei Namenszeilen, Skonto in den Zahlungsbedingungen; 3 zwei Seiten
ohne Übertrag, 34 Positionen; 4 Postfach; 5 ohne Referenz, mehrzeilige Bezeichnungen. Kein Prüfen-Fall.

A1 (20.11.2026), alle Hold-out: 6 **Falle** `nummer_aehnlich` (Projektnr. im Format der Rechnungsnummer). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- BT-112: „Gesamt EUR inkl. MwSt.“ wird nicht gelesen (0/5); Netto und USt stimmen.
- BT-20/BT-9/Skonto: Als Zahltext wird das Label „Fälligkeitsdatum“ gelesen, die Fälligkeit fehlt (0/5).
- Kundennummer: „Debitorennr.“ wird nicht als Kundennummer erkannt (0/5).
- Positionen 275/275, auch über die Seite ohne Übertrag; Postfach (Beleg 4) wird als Straße gelesen wie gedruckt.
