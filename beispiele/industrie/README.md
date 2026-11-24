# Test-Setup „Industrie“ (alle Daten erfunden)

**Normteile Brückner GmbH**, Remscheid – Schrauben-/Normteile-Großhandel mit eigener Lohnzerspanung.
Acht Rechnungen NB-26-1001 … NB-26-1008 (Oktober 2026) an vier erfundene Industriekunden, 19 % Inland.

| Besonderheit | Im Druck | In der CSV / E-Rechnung |
|---|---|---|
| Schrauben, Muttern, Scheiben | Preis „pro 100 Stk“, Spalte **PE** = 100 | `Preiseinheit` 100 → BT-149 |
| Gewindestange, Drehteil, Frästeil | Preis pro Stück, PE = 1 | Preiseinheit 1 |
| Zerspanung, Rüstzeit | Einheit `Std` | `HUR` |
| Stückware | Einheit `Stk` | `H87` |

Dateien:

- `eingang/` – je Rechnung das Druck-PDF und der schlanke CSV-Export `normteile_<Nr>.csv`
  (nur Mindestspalten aus [csv-format.md](../../docs/csv-format.md) plus `Preiseinheit`)
- `profil-normteile.yaml` – Zuordnungsprofil für PDF + CSV
- `konfiguration-pdf-csv.yaml`, `konfiguration-nur-pdf.yaml` – fertige Konfigurationen, Arbeitsordner unter `laufzeit/`
- `absender-normteile.csv` – Absenderdaten zum Importieren
- `erzeuge_beispiele.py` – erzeugt alles neu (deterministisch)

USt-IdNr. DE290319664 und IBAN DE34 0000 0000 0071 1008 42 haben gültige Prüfziffern (Bankleitzahl 00000000).

Erwartete Summen NB-26-1001: netto 903,60 · USt 171,68 · brutto 1.075,28.

## Ablauf A: PDF + CSV (Vorlage lernt mit)

1. Starten: `fakturafalter -c beispiele/industrie/konfiguration-pdf-csv.yaml`
2. Die Dateien von `eingang/` (PDFs und CSVs) in den Ordner `laufzeit/industrie-pdf-csv/Eingang` kopieren.
3. Alle acht Rechnungen erscheinen als **Fertig** (geprüft mit Mustang und KoSIT).
   Jedes Paar ohne Abweichung trainiert die Vorlage.
4. Einstellungen → **Vorlagen & Anlernen**: Die Karte „normteile“ zeigt den Fortschritt (Rechnungen in
   Folge ohne Korrektur, 5 nötig). Danach kann „Automatisch, ohne Nachfrage“ eingeschaltet werden: Ab dann
   reicht das PDF allein.
5. Probe: ein PDF ohne CSV in den Eingang legen – es wird ohne Nachfrage erzeugt.

Ohne Oberfläche: `fakturafalter -c beispiele/industrie/konfiguration-pdf-csv.yaml --einmal`

## Ablauf B: Nur PDF (Anlern-Assistent)

1. Starten: `fakturafalter -c beispiele/industrie/konfiguration-nur-pdf.yaml`
2. Nur die PDFs aus `eingang/` in `laufzeit/industrie-nur-pdf/Eingang` kopieren.
3. Hauptfenster: „8 PDFs zum Anlernen“ → **Anlernen**.
4. Schritt 1 **Bereiche** (freiwillig): Bereich anklicken (Anschrift, Rechnungskopf, Positionstabelle, Summen,
   Zahlungsbedingungen) und im PDF einen Rahmen darum ziehen oder „Vorschlag übernehmen“; „Gilt auf“ allen,
   der ersten oder der letzten Seite. Diese Angaben werden danach nur im Rahmen gelesen. „Weiter ▶“.
   Schritt 2 **Absender**: aus dem Druck erkannt; prüfen oder „Aus Datei importieren…“ mit
   `absender-normteile.csv`.
5. Schritt 3 **Rechnungsdaten**: erkannte Felder mit „Passt“ bestätigen; fehlt etwas, Feld anklicken und
   im PDF auf den Wert klicken (oder den Wert eintippen – die Fundstelle wird gesucht).
6. Schritt 4 **Positionen**: Rahmen um die Tabelle ziehen, je Spalte die Bedeutung wählen
   (Menge, ME, Preis, **PE = Preiseinheit**, Betrag). Die Summenprüfung muss „Summe Positionen = Netto“ zeigen.
7. „Speichern & nächste PDF“. Ab der zweiten Rechnung ist fast alles erkannt; nach fünf Rechnungen in Folge
   ohne Korrektur ist die Vorlage freigabebereit („Automatisch, ohne Nachfrage“).
