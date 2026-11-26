# Fakturafalter 0.9.8.3

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Neuer Schalter im CSV-Assistenten. Vorheriger Stand: 0.9.8.2.

## Was sich ändert

- **Fehlende Einheit = Stück verwenden:** Im Assistenten, Schritt „Darstellung auf der Rechnung“ (auch über „Darstellung…“ am Profil). Wenn der Schalter eingeschaltet ist, erhalten Positionen mit Menge und Preis, aber leerer Einheit, Stück (UN/ECE Rec 20 H87). Im Protokoll erscheint der Hinweis „Einheit fehlte, Stück angenommen“ – kein Prüffall. Standard bleibt aus: fehlende Einheit ist wie bisher „Zu prüfen“.

## Prüfung

Lokal: gezielte Tests zur neuen Option, Assistent und Sichtseite, plus Mustang/KoSIT und Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
