# Fakturafalter 0.9.8.2

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Fehlerbehebung und überarbeitete Einstiegstexte. Vorheriger Stand: 0.9.8.1.

## Was sich ändert

- **Profile löschen:** Fehlende oder gelöschte Profildateien lassen das Speichern der Einstellungen nicht mehr mit „No such file or directory“ scheitern (beobachtet unter Windows). Gelöschte Profile bleiben weg und werden nicht wieder eingetragen.
- **CSV-Assistent:** Ein bereits angelegtes Profil lässt sich im letzten Schritt wieder speichern; der Assistent bleibt nicht mehr offen, wenn eine andere gelistete Profildatei fehlt.
- **README und Handbuch** sind überarbeitet: warum es Fakturafalter gibt, CSV/XML als bevorzugter Weg, Nur-PDF weiterhin unterstützt (eigener Abschnitt), geplante Features.

## Prüfung

Lokal: gezielte Tests zu Profil-Löschen, Assistenten-Speichern und Konfiguration, plus Mustang/KoSIT und Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
