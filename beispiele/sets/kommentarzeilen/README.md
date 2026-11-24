# Testset „Kommentarzeilen“ (Testoria Zerspanungstechnik GmbH)

Zwei fiktive Rechnungen im Mandanten-Layout (wie `beispiele/sets/fiktiva`) für einen Fix in der Erkennung:
Kommentarzeilen unter Positionen und eine Rechnungsnummer außerhalb des Kopfblocks.

**Alle Daten sind erfunden.** Absender, Kunden, Artikel, Nummern, IBAN (BLZ 00000000) und USt-IdNr. sind
ausgedacht. Domains enden auf `.example`. USt-IdNr. und IBAN haben gültige Prüfziffern
(`pflichtpruefung.ust_id_de_gueltig` / `iban_gueltig`, im Selbstcheck geprüft).

**Version 1.0.0, eingefroren** (`MANIFEST.json`, 20.11.2026). Bei A1 inhaltlich unverändert (keine Fehler-
oder Fallenbelege); die Belege sind byte-gleich zum Stand d62a2f4.

## Belege und Rollen

| Datei | Rechnungsnummer | Rolle | Kommentarzeilen (unter Position) |
|---|---|---|---|
| `Rechnung_001_2026-04711.pdf` | 2026-04711 | **anlernen** | Pos. 2 „davon mit Härtung 12 Stück“, Pos. 4 „davon Restmenge folgt“ |
| `Rechnung_002_2026-04738.pdf` | 2026-04738 | **nachlesen** | Pos. 1 „davon 8 Stück brüniert“, Pos. 4 „Restmenge 2 Stück folgt in KW 46“ |

Beleg 1 dient zum Anlernen, Beleg 2 (gleiches Layout, andere Nummer, Kunde, Positionen und Kommentare) zum
Nachlesen mit dem angelernten Profil. Die Rolle steht auch im JSON-Feld `rolle`. Beide JSONs liegen in
`Referenzdaten/` (kein Hold-out); `fiktiv-angelernt` mit `--lernen 1` entspricht genau dieser Aufteilung.

## Was getestet wird

- **Kommentarzeilen:** Unter zwei normalen Positionen je Beleg steht eine Zeile ohne Menge, Preis und Betrag.
  Der Text beginnt auf x der Einheitenspalte (110,55 pt) und läuft quer bis in die Bezeichnungsspalte
  (ab 153,07 pt), Ende 198,6–244,6 pt. **Soll:** Der Kommentar wird als weitere Zeile an `description[]` der
  Position darüber angehängt (wie eine umbrechende Bezeichnung). Die Position behält ihre Einheit
  (`Stk.`), der Kommentar erzeugt keine eigene Position und hat keine Einheit.
  Zusätzlich (optional): `positions[].comment_lines` mit dem Kommentartext.
- **Rechnungsnummer außerhalb des Kopfblocks:** „Rechnung Nr. 2026-04711“ fett oben links unter dem Briefkopf
  (top 116,5 pt), in beiden Belegen an derselben Stelle. Der Kopfblock rechts enthält RE-Datum,
  Leistungsdatum (= RE-Datum), Kundennummer, Bestellnummer und Versandart, aber keine Rechnungsnummer.
- Spalten: Menge | Einheit | Bezeichnung | Einzelpreis | Gesamt. Der Einzelpreis steht als „X € /N“ in einer
  Spalte (z. B. „51,75 € /1“, „13,33 € /100“). Je Beleg /1 und /100, Einheiten Stk. und Std.
- Summen (Netto, „MwSt. 19 %“, Rechnungsbetrag) direkt unter der Tabelle, Zahlungsblock wie fiktiva
  (Beleg 1 mit 2 % Skonto, Beleg 2 ohne). Einseitig, Inland, 19 %.

## Ordner

- `Rechnungen/`: die zwei PDFs.
- `Referenzdaten/Rechnung_*.json`: Soll im Schema von `tests/daten/fiktiv` bzw. fiktiva.
  Zusätzliche, optionale Felder: `rolle`, `positions[].comment_lines`, `test_flags.comment_line_*`,
  `test_flags.invoice_number_outside_header_block`, `test_flags.invoice_number_label`.

## Erzeugen

Aus der Repo-Wurzel (die venv des Hauptbaums genügt):

```sh
.venv/bin/python beispiele/sets/kommentarzeilen/erzeuge.py
```

Importiert Geometrie und Hilfen aus `beispiele/sets/fiktiva/erzeuge.py` (Abhängigkeit, steht mit Hash im
Manifest; die A1-Erweiterung von fiktiva ändert an diesen Belegen nichts).
Fester Seed 264712, deterministisch (byte-gleiche PDFs). Selbstcheck: Menge × Preis / PE = Gesamt,
Σ = Netto, Netto + USt = Brutto, Skonto, Prüfziffern, und Rücklesen mit pdfplumber: Nummer oben links,
Kommentar-Wortboxen beginnen auf x der Einheit und enden rechts von x der Bezeichnung.

## Messen

```sh
.venv/bin/python tools/benchmark.py --fiktiv beispiele/sets/kommentarzeilen --verfahren fiktiv-kaltstart
```

Stand `erkennung/kopffeld` (Kaltstart, 03.11.2026): Rechnungsnummer 2/2 trotz Lage außerhalb des Blocks,
Beträge und Positionen vollständig; **Pos.: Bezeichnung 6/10**: die vier Kommentarzeilen fehlen in der
Bezeichnung (der Fix). BT-44/BT-51 bei „Abteilung Einkauf“ ist die bekannte Auslegungsfrage (feste Regel 0.4.4).
