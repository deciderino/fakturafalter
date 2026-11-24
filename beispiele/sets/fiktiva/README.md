# Testset „Fiktiva Antriebstechnik GmbH“

30 fiktive Rechnungen eines erfundenen Absenders im Layout der Mandanten-Testrechnungen
(`tests/daten/fiktiv`, Branch `erkennung/benchmark`). Das Set dient als zweiter Absender mit
demselben Layout, damit die Erkennung nicht nur auf „Alberon“ gemessen wird.
16 Rechnungen sind zum Tunen und Anlernen gedacht (fehlerfrei), 14 sind Hold-out und nur zur Kontrolle,
davon 4 mit absichtlichem Fehler und 2 mit Falle (Abschnitt „A1“). **Version 1.0.0, eingefroren** (`MANIFEST.json`).

**Alle Daten sind erfunden.** Absender, Kunden, Artikel, Nummern, IBAN und USt-IdNr. sind
ausgedacht. Domains enden auf `.example`. Nichts stammt aus echten Rechnungen oder Mandantendaten.

## Herkunft

- Layout nachgebaut nach den 50 fiktiven Rechnungen in `tests/daten/fiktiv` (Geometrie mit
  pdfplumber ausgemessen) und nach dem v1-Umfang, den E-Rechnung festgelegt und der Nutzer bestätigt hat.
- Erzeugt mit `erzeuge.py` (reportlab, fester Seed 264711). Der Lauf ist deterministisch:
  zwei Läufe ergeben byte-gleiche PDFs, die SHA-256-Werte stehen in den Referenzdaten.
- Die Originale sind PDF/A-2b, das Ghostscript erzeugt. Auf dem Erzeugungsrechner gibt es kein Ghostscript,
  deshalb sind die PDFs hier normale PDF 1.4 mit eingebetteter Liberation Sans. Text und Geometrie sind gleich.

## Layout (wie im Original)

- A4, Ränder links 53,86 pt und rechts 552,76 pt, Schrift Liberation Sans / Liberation Sans Bold.
- Kopf: Logo-Kachel „FA“ (Vektor), „FIKTIVA“ / „Antriebstechnik GmbH“, Adresse, Telefon und E-Mail rechts.
- Absenderzeile über der Anschrift. Anschrift mit 1–3 Namenszeilen (Firma, zweite Firmenzeile,
  „Abteilung …“, „z. Hd. …“), Straße, 1–2 Leerzeilen, PLZ Ort. Die PLZ-Zeile steht immer an derselben Stelle.
- Kopffelder rechts: Rechnungsnummer (fett), RE-Datum, Leistungsdatum (= RE-Datum), Kundennummer,
  Bestellnummer (optional leer), Versandart.
- Tabelle „Rechnungspositionen“ mit den Spalten Menge | ME | Bezeichnung | Preis | PE | Gesamtpreis.
  Units are Stk. and Std. PE is /1 or /100. Long descriptions wrap onto continuation lines.
- Netto, „MwSt. 19 %“ und „Rechnungsbetrag“ (doppelt unterstrichen) stehen direkt unter der letzten Position.
- Zahlungsbedingungen nur auf Seite 1, immer an derselben Stelle, in genau zwei Formen:
  - `zahlbar bis TT.MM.JJ bei X % Skonto (Betrag €)` / `bis TT.MM.JJJJ ohne Abzug`
  - `zahlbar bis TT.MM.JJJJ ohne Abzug`
  Skonto ist 2 % oder 3 % vom Brutto, das Zahlungsziel ist 30 Tage.
- Mindestauftrag: Artikel nur mit Menge und Bezeichnung, danach eine Sammelzeile mit Menge 1, ohne ME,
  mit PE /1, Preis und Gesamtpreis. Die Bezeichnung der Sammelzeile wechselt
  (Mindestauftrag, Gesamtpreis, Mindestauftragswert, Gesamtpreis lt. Angebot …).
- Mehrseitig: Kopf, Anschrift und Tabellenkopf werden wiederholt. Am Seitenende steht „Übertrag“.
  Ein Teil der Rechnungen hat auf der Folgeseite zusätzlich „Vortrag“ als erste Zeile (das Original hat das nicht).
  Fußzeile mit Firma, Bank und „Seite x von y“ auf jeder Seite.
- Nicht enthalten (bewusst): fremde Layouts, AT/CH-Anschriften, gemischte Steuersätze, Rabatte oder
  negative Beträge, Fehlerfälle.

## Varianz je Rechnung

HO = Hold-out. Namenszeilen/Leer = Namenszeilen der Anschrift / Leerzeilen vor PLZ Ort.
„letzte Zeile“ = Tabellenzeilen-Index (0-basiert) der Zeile „Rechnungsbetrag“ auf der letzten Seite.
Seite 1 fasst bis Index 19 (mit Zahlungsblock), Folgeseiten bis Index 23.

| Nr. | Rechnungsnummer | HO | Seiten | Pos. | Namenszeilen/Leer | Bestell-Nr. | Skonto | PE /100 | Mindestauftrag (ohne Preis/Pauschale) | Übertrag/Vortrag | letzte Zeile | Schwerpunkt |
|---|---|---|---:|---:|---|---|---|---:|---|---|---:|---|
| 001 | FA-26-10312 |  | 1 | 3 | 1/1 | ja | – | 0 | – | – | 5 | einfach |
| 002 | FA-26-10315 |  | 1 | 4 | 2/1 | ja | 2 % | 0 | – | – | 6 | zweizeiliger Firmenname, Skonto |
| 003 | FA-26-10323 |  | 1 | 5 | 3/1 | nein | – | 2 | – | – | 7 | 3 Namenszeilen mit Abteilung und z. Hd. |
| 004 | FA-26-10329 |  | 1 | 4 | 2/1 | ja | 3 % | 4 | – | – | 6 | Preiseinheit /100 |
| 005 | FA-26-10340 |  | 1 | 6 | 1/1 | ja | – | 0 | – | – | 8 | Tausenderpunkt Menge |
| 006 | FA-26-10343 |  | 1 | 8 | 2/1 | ja | 2 % | 0 | 7/1 | – | 10 | reiner Mindestauftrag |
| 007 | FA-26-10351 | ja | 1 | 6 | 3/1 | ja | 3 % | 1 | – | – | 9 | zweizeiliger Firmenname + z. Hd., /1 und /100 |
| 008 | FA-26-10356 |  | 2 | 26 | 1/1 | ja | – | 10 | – | Ü | 10 | 2 Seiten, Übertrag ohne Vortrag |
| 009 | FA-26-10366 |  | 2 | 27 | 2/1 | ja | 2 % | 0 | – | Ü+V | 15 | 2 Seiten, Übertrag und Vortrag |
| 010 | FA-26-10372 | ja | 2 | 28 | 2/1 | nein | – | 0 | 4/1 | Ü+V | 13 | 2 Seiten mit Vortrag, Mindestauftrag-Gruppe |
| 011 | FA-26-10380 |  | 1 | 17 | 1/1 | ja | – | 0 | – | – | 19 | einseitig knapp am Seitenende (Netto-Zeile 643,5 pt) |
| 012 | FA-26-10387 |  | 1 | 15 | 2/1 | ja | 3 % | 3 | – | – | 18 | einseitig knapp am Seitenende (Netto-Zeile 631,6 pt), Skonto |
| 013 | FA-26-10396 | ja | 1 | 6 | 2/2 | nein | – | 0 | 2/1 | – | 8 | Mindestauftrag gemischt, 2 Leerzeilen in der Anschrift |
| 014 | FA-26-10401 |  | 3 | 49 | 3/1 | ja | 3 % | 11 | – | Ü+V | 15 | 3 Seiten, Übertrag und Vortrag, Skonto |
| 015 | FA-26-10410 | ja | 3 | 48 | 1/1 | ja | – | 0 | – | Ü | 11 | 3 Seiten ohne Vortrag |
| 016 | FA-26-10412 |  | 2 | 24 | 3/1 | nein | 2 % | 24 | – | Ü | 8 | 2 Seiten, nur /100 |
| 017 | FA-26-10419 |  | 1 | 5 | 1/1 | ja | – | 5 | – | – | 7 | /100 mit Mengen ≥ 1.000 |
| 018 | FA-26-10428 |  | 2 | 38 | 1/2 | ja | – | 15 | – | Ü | 23 | 2 Seiten, Endseite bis knapp vor die Fußzeile, 2 Leerzeilen |
| 019 | FA-26-10437 | ja | 1 | 5 | 2/1 | ja | – | 0 | – | – | 11 | lange umbrechende Bezeichnungen |
| 020 | FA-26-10443 |  | 2 | 22 | 2/1 | ja | 2 % | 0 | 4/1 | Ü | 6 | 2 Seiten, Mindestauftrag-Gruppe |
| 021 | FA-26-10449 | ja | 1 | 4 | 2/1 | ja | 3 % | 0 | – | – | 8 | nur Stunden, Skonto |
| 022 | FA-26-10458 |  | 1 | 15 | 2/1 | ja | – | 3 | – | – | 17 | einseitig, Netto-Zeile 619,7 pt |
| 023 | FA-26-10464 | ja | 2 | 38 | 2/1 | ja | 2 % | 38 | – | Ü+V | 23 | 2 Seiten mit Vortrag, /100, Endseite knapp vor der Fußzeile |
| 024 | FA-26-10468 | ja | 1 | 5 | 1/1 | nein | 2 % | 0 | 4/1 | – | 7 | reiner Mindestauftrag, Skonto |

Coverage of the v1 points:

1. Anschrift: 1, 2 und 3 Namenszeilen, „Abteilung“ und „z. Hd.“, zweizeilige Firmennamen, 2 Leerzeilen
   (013, 018), PLZ mit führender Null (01159, 08523; Absender 04179), Orte mit Zusatz (Freiburg im Breisgau,
   Leer (Ostfriesland), Ludwigshafen am Rhein).
2. Netto, MwSt. 19 % und Rechnungsbetrag stehen direkt unter der Tabelle, centgenau.
3. 12 Rechnungen mit Skonto, 12 ohne Skonto.
4. Mindestauftrag: rein (006, 024) und gemischt (010, 013, 020).
5. 1, 2 und 3 Seiten, mit Übertrag, teilweise mit Vortrag. Knapp am Seitenende: 011, 012 und 022 einseitig
   (Netto-Zeile bei 643,5 / 631,6 / 619,7 pt), 018 und 023 mit Endseite bis knapp vor die Fußzeile.
6. PE /1 und /100 (auch Rechnungen nur mit /100). ME Stk. und Std.
7. Bestellnummer fehlt in 003, 010, 013, 016 und 024.
8. Umbrechende Bezeichnungen (bis 3 Zeilen), Tausenderpunkt in Menge und Beträgen, Leistungsdatum = RE-Datum.

## A1 (20.11.2026): Fehler- und Fallenbelege, Set eingefroren

Sechs neue Belege 025–030, alle **Hold-out** (`Referenzdaten/holdout/`), angehängt an das Ende. Die Belege
001–024 sind byte-gleich geblieben (SHA-256 vor/nach geprüft). Die Anlern-/Tuning-Belege sind fehlerfrei.

| Nr. | Rechnungsnummer | Rolle | Art | Was gedruckt ist |
|---|---|---|---|---|
| 025 | FA-26-10475 | holdout-fehler | `zeile` | Pos 2: 200 Stk. × 11,32 € /100 = 22,64 €, gedruckt 26,24 € (Zahlendreher); Netto/MwSt./Brutto aus den gedruckten Zeilen richtig weitergerechnet |
| 026 | FA-26-10486 | holdout-fehler | `ust_betrag` | „MwSt. 19 %“, gedruckt sind aber 16 % (820,56 € statt 974,42 €); Brutto = Netto + gedruckte MwSt., Skonto vom gedruckten Brutto |
| 027 | FA-26-10491 | holdout-fehler | `iban_pruefziffer` | IBAN im Fuß beider Seiten „DE17 …“ statt „DE71 …“ (MOD 97 ungültig) |
| 028 | FA-26-10496 | holdout-fehler | `faelligkeit_vor_datum` | „zahlbar bis 05.12.2025“ bei RE-Datum 05.11.2026 (Jahr vertippt) |
| 029 | FA-26-10504 | holdout-falle | `lieferschein_nr` | Kopfzeile „Lieferschein-Nr.: LS-26-10495“ direkt unter der Rechnungsnummer |
| 030 | FA-26-10510 | holdout-falle | `hinweis_betrag` | Zeile „Hinweis: Ab einem Bestellwert von 250,00 € netto liefern wir frachtfrei.“ unter den Zahlungsbedingungen |

Zusätzliche Soll-Felder (nur 025–030):
- `rolle` (`holdout-fehler` / `holdout-falle`), `erwarteter_status` (`fehler` / `ok`)
- `erwartete_hinweise`: was die App melden sollte (BT und Wortlaut angelehnt an `pflichtpruefung`/`rechnen`;
  maßgeblich ist das BT, nicht der genaue Text). Bei Fallen leer.
- `moegliche_folgehinweise`: Hinweise, die als Folge des einen Fehlers zusätzlich kommen dürfen.
- `fehlerart`, `fehler_beschreibung`, `fehler_detail` bzw. `falle`, `falle_beschreibung`, `falle_detail`
- `totals_berechnet`: rechnerisch richtige Werte aus Menge × Preis. **`totals` ist immer das Gedruckte.**
- 027: `seller.iban` ist die gedruckte (falsche) IBAN. 028: `payment.due_date` ist das gedruckte Datum,
  `payment_days` ist `null`.

Je Fehlerbeleg ist genau ein Bruch drin (Selbstcheck prüft das), Fallen sind rechnerisch und formal korrekt.
Damit: 30 Belege, 16 Tuning (fehlerfrei), 8 Hold-out, 4 Hold-out-Fehler, 2 Hold-out-Fallen.

**Eingefroren als Version 1.0.0** (`MANIFEST.json`: Hash je Datei, Rolle je Beleg). Änderungen an Belegen nur
mit neuer Version im Manifest.

## Ordner

- `Rechnungen/Rechnung_NNN_<Nr>.pdf`: alle 30 PDFs, auch die Hold-out-PDFs.
- `Referenzdaten/Rechnung_*.json`: Soll-Werte der 16 Tuning-Rechnungen im Schema von `tests/daten/fiktiv`.
- `Referenzdaten/holdout/Rechnung_*.json`: Soll-Werte der 14 Hold-out-Rechnungen (8 Kontrolle, 4 Fehler, 2 Fallen).
- `MANIFEST.json`: Version, Inhalts-Commit, Seed, Generator-Aufruf, SHA-256 und Größe je Datei, Rolle je Beleg.
- `Referenzdaten/Testfallmatrix.csv`: Übersicht (Semikolon, UTF-8 mit BOM).

Die Hold-out-PDFs können in `Rechnungen/` bleiben. `tools/benchmark.py` liest nur
`Referenzdaten/Rechnung_*.json`, nicht rekursiv, und PDFs ohne passende JSON übergeht es. So zählt der
normale Lauf nur die 16 Tuning-Rechnungen.

## Schema-Erweiterungen (zusätzlich, optional)

The base schema is the same as in `tests/daten/fiktiv`. These fields are added and can be ignored:

- `holdout` (bool)
- `positions[].price_unit` („/1“ oder „/100“), `positions[].price_unit_qty` (1 oder 100), `positions[].min_order` (bool)
- `payment.discount_base` (Skonto-Basis = Brutto), `payment_terms_text` (gedruckte Zeilen des Zahlungsblocks)
- `pages[].carry_forward` (Vortrag der Seite oder null)
- weitere `test_flags` (u. a. `address_blank_lines`, `price_unit_100_count`, `carry_forward`,
  `last_table_row_index`, `note`)

## Erzeugen

Aus der Repo-Wurzel (Python 3.13, reportlab 5.1.0, pdfplumber; `src/` wird für `pflichtpruefung` eingebunden):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python beispiele/sets/fiktiva/erzeuge.py
```

Ein Neulauf muss byte-gleich zu den Hashes in `MANIFEST.json` sein (geprüft mit reportlab 5.1.0).

The script deletes `Rechnungen/` and `Referenzdaten/` and writes them again. Afterwards it runs a self-check:
- Positionssumme = Menge × Preis / PE
- Σ = Netto, MwSt., Brutto, Skonto
- Seitenzahl, Übertrag und Vortrag
- Zeilengrenzen je Seite
- PDF read back with pdfplumber

If any check fails, it stops with an AssertionError. Requires reportlab and pdfplumber.

## Messen

On a branch that has `tools/benchmark.py`:

```sh
.venv/bin/python tools/benchmark.py --fiktiv beispiele/sets/fiktiva --verfahren fiktiv-kaltstart fiktiv-angelernt
```

Hold-out: build a temporary folder with `Rechnungen/` (link) and `Referenzdaten` → `Referenzdaten/holdout`:

```sh
mkdir -p /tmp/fiktiva-ho
ln -sfn "$PWD/beispiele/sets/fiktiva/Rechnungen" /tmp/fiktiva-ho/Rechnungen
ln -sfn "$PWD/beispiele/sets/fiktiva/Referenzdaten/holdout" /tmp/fiktiva-ho/Referenzdaten
.venv/bin/python tools/benchmark.py --fiktiv /tmp/fiktiva-ho --verfahren fiktiv-kaltstart fiktiv-angelernt
```

`fiktiv-angelernt` lernt mit den ersten `--lernen` Rechnungen (Standard 5) an und misst den Rest.

Known benchmark limits (as of `erkennung/kopffeld` f6b4a11). These come from the benchmark, not from the recognition:
- **BT-20:** `fiktiv_soll` erwartet den festen Wortlaut „Zahlbar innerhalb von N Tagen bis … ohne Abzug“.
  Dieses Layout druckt aber „zahlbar bis …“. Der richtige Soll-Text steht in `payment_terms_text`.
- **Pos.: Preiseinheit:** Das Soll ist im Benchmark immer 1, deshalb gelten richtig erkannte /100 als Fehler.
  Der richtige Wert steht in `price_unit_qty`.
- **BT-44/BT-51:** Der Benchmark erwartet `name_lines[0]` als BT-44 und den Rest als BT-51.
  Bei zweizeiligen Firmennamen ist das eine Auslegungsfrage.
