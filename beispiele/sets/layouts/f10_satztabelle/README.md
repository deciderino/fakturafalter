# F10 Satztabelle (nach der Mustangproject-Beispielrechnung RE-20201121/508, ZUGFeRD-Korpus, Q7)

Absender: Leselust Medienvertrieb GmbH, Leipzig (fiktiv). Schrift Helvetica 9 pt. **Gemischte Steuersätze
7/19 %** (Bücher 7 %; Papeterie und Dienstleistungen 19 %). **Volles Hold-out**.

Was ist besonders:
- Datum links oben, Firmenblock rechts klein, Absenderzeile mit „●“, Anschrift in zwei Spalten.
- Infozeilen „Kunde: <Nr.>“, „Ihre Bestellung AB###“ (= BT-13), „Rechnung Nr. RE-JJJJMMTT/### vom …“ fett,
  „Lieferdatum …“.
- Gittertabelle Menge | Produkt | USt | Preis | Gesamt; Menge als „1,00“ **ohne Einheit**, die Einheit steht
  im Produktnamen („Autorenlesung (Stunden): …“).
- Summen: „Nettosumme“, „zzgl. USt“ und eine **Tabelle je Satz** USt | Nettobetrag | USt-Betrag, dann
  „USt gesamt“ und „Zahlbetrag“ fett.
- GUI-Grenzfall: Mehrere USt-Beträge stehen untereinander; liest die Erkennung nur die erste Satzzeile, ist die
  USt zu klein.
- „Bitte überweisen bis ….“ und bei Skonto „Bei Zahlung bis … gewähren wir X % Skonto.“; Fuß rechts mit
  USt-IdNr., IBAN, BIC, Bank, Kontoinhaber; „Seite 1/1“.

Fälle (alle Hold-out): 1 Bücher und Papeterie; 2 drei Namenszeilen; 3 ohne Bestellnummer, Skonto; 4 sieben
Positionen, mehrzeilig; 5 mit Dienstleistung in Stunden. Kein Prüfen-Fall.

Weggelassen: Preise mit drei Nachkommastellen (siehe QUELLEN.md, Q7).

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- BT-2: Datum aus „Rechnung Nr. … vom <Datum>“ nicht gelesen (0/5).
- BT-13: „Ihre Bestellung AB###“ nicht gelesen (0/4).
- BT-20/BT-9: „Bitte überweisen bis …“ startet keinen Zahltext, keine Fälligkeit (0/5).
- Einheit: „(Stunden)“ im Produktnamen wird nicht als HUR erkannt.
- BT-119 fehlt (0/5); Soll im Benchmark nur „19“ (ein Satz), Grenze des Benchmarks bei gemischten Sätzen.
- GUI-Grenzfall: BT-109/110/112 werden richtig gelesen, die USt ist nicht zu klein.
