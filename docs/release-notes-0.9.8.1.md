# Fakturafalter 0.9.8.1

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Nachbesserungen zum Standardaufbau „eine Zeile je Position“ (nicht zur Block-Logik, die weiterhin geplant wird).

## Was sich ändert

- Kommentar- und Leerzeilen im Standardaufbau: ohne Menge und Preis (auch 0 / 0,00), aber mit Text = Kommentarzeile; nur Kopffelder = gewollte Leerzeile; Platzhalter `#LEER` bleibt. Spalten auf „nicht verwenden“ werden ignoriert.
- Positionsnummern: ohne Positionsspalte fortlaufend 1, 2, 3 nur für echte Positionen. Mit Spalte gilt die Nummer aus der Warenwirtschaft. In der XML steht BT-126 immer; auf der Sichtseite kann die Nummer ausgeblendet werden.
- Sichtseite: Kommentarzeilen ohne Vorsatz „Beschreibung:“ direkt unter der Position (XML weiter BT-154). Menge standardmäßig exakt wie in der CSV (z. B. 40,00). Optional Einheit unverändert aus der CSV; XML weiter Rec-20 in BT-130.
- Assistent (nur Standardaufbau): Schritt „Textzeilen“ (ob Kommentare/Leerzeilen zu erwarten sind, welche Spalten leer sein müssen, Vorschau) und Schritt „Darstellung auf der Rechnung“ (Bezeichnungen, ausblenden, Live-Vorschau). Später über „Darstellung…“ am Profil erreichbar, ohne den ganzen Assistenten.
- Preis ohne Menge: im Assistenten „Zu prüfen“ (Standard), „Menge 1 setzen“ oder „als Kommentarzeile“.

Bestehende Profile bleiben gültig. Neue Defaults: Menge auf der Sichtseite exakt wie in der CSV; Kommentarzeilen ohne Vorsatz „Beschreibung:“.

## Prüfung

Lokal: gezielte Tests zu CSV-Adapter, Assistent, Sichtseite, CII/XML und Rückwärtskompatibilität, plus Mustang/KoSIT und Rauchtest AppImage/Windows.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
