# Fakturafalter 0.9.8.4

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Währungszeichen auf dem sichtbaren Rechnungsteil. Vorheriger Stand: 0.9.8.3.

## Was sich ändert

- **Beträge mit Währung:** Auf dem sichtbaren PDF stehen Einzelpreis, Positionsbetrag, Übertrag und alle Summen (Netto, USt, Zu-/Abschläge, bereits gezahlt, Rundung, Gesamt, Zahlbetrag) mit Währung: bei Euro als „1.234,56 €“, sonst mit ISO-Code, zum Beispiel „1.234,56 USD“. Die Beschriftungen Gesamtbetrag und Zahlbetrag tragen kein nachgestelltes ISO-Kürzel mehr. Im Fließtext, etwa „USt 19 % auf 394,40“, bleibt die reine Zahl. Bei einer Preiseinheit ungleich 1 erscheint das Zeichen nur einmal („3,40 € / 10 Stück“). Lange Beträge werden in der Spalte angepasst, statt umzubrechen.

## Prüfung

Lokal: gezielte Tests zu Format, Sichtseite und Spaltenbreite, plus Mustang/KoSIT und Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
