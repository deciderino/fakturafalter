# Layout-Robustheitsset `layouts/`

Zehn Layout-Familien mit je fünf fiktiven Rechnungen. Jede Familie hat einen eigenen erfundenen Absender. Jede
Familie bildet den Aufbau einer echten, öffentlich zugänglichen Vorlage nach; Quellen und Abweichungen stehen in
[`QUELLEN.md`](QUELLEN.md). Es gibt keine echten Mandantendaten. Alle Domains enden auf `.example`. USt-IdNr. und
IBAN sind prüfziffernrichtig, die Bankleitzahl ist 00000000.

**Stand Phase 2 (03.11.2026):** Alle zehn Familien sind fertig (50 Belege). Jede Familie-README hat einen
Abschnitt „Bekannte Lücke“ mit den Befunden aus dem Benchmark.

**Stand A1 (20.11.2026):** 60 Belege (10 neue Hold-out-Belege mit Fehler oder Falle in F1–F8, Abschnitt „A1“).
**Version 1.0.0, eingefroren** (`MANIFEST.json`).

## Aufbau

```
layouts/
  _rahmen.py            gemeinsamer Generator: Zahlen, Daten, Positionen, Seitenplan, JSON, Selbstcheck, Rücklesen
  erzeuge.py            erzeugt alle oder einzelne Familien
  QUELLEN.md            Vorlagen mit URL, Layout-Notizen und Abweichungen
  fNN_<name>/
    familie.py          Absender, Layout (Zeichnen) und die fünf Fälle (Spez)
    README.md           was an dieser Familie besonders ist
    Rechnungen/         PDFs (Training und Hold-out)
    Referenzdaten/      Soll-JSON der Trainingsbelege, Testfallmatrix.csv
    Referenzdaten/holdout/   Soll-JSON der Hold-out-Belege
```

## Erzeugen

```bash
# Im Projektwurzelverzeichnis:
python beispiele/sets/layouts/erzeuge.py                     # alle Familien
python beispiele/sets/layouts/erzeuge.py f03_seitenleiste    # eine Familie
```

- Der Lauf ist deterministisch: fester Seed je Familie und reportlab `invariant=1`. Zwei Läufe sind byte-gleich (geprüft mit sha256 über alle PDF/JSON/CSV).
- Jeder Beleg durchläuft zwei Prüfungen:
  - Selbstcheck: Summen centgenau, Seitenzahl, Übertrag und Vortrag kumuliert, Prüfen-Fälle wie gewollt falsch.
  - Rücklesen mit pdfplumber: Nummer, Anschrift, Zahltext, IBAN und USt-IdNr. stehen im PDF.

## Benchmark

```bash
# Im Projektwurzelverzeichnis:
python tools/benchmark.py --verfahren fiktiv-kaltstart fiktiv-angelernt --lernen 2 \
  --set beispiele/sets/layouts/f01_infozeilen \
  --json /tmp/bench_f01.json --md /tmp/bench_f01.md --max-fehl 0
```

**Hinweise zu `--set`**
- Den Pfad zur Familie angeben (relativ zum Projektwurzelverzeichnis oder absolut).
- `--set` nimmt **eine Familie**, nicht `layouts/`. `testsets()` sucht `Rechnungen/` und `Referenzdaten/` nur genau eine Ebene tief.
- Jeder Lauf misst zusätzlich das Hauptset `tests/daten/fiktiv`.
- Die Testsets laufen mit fester Regel: Namenszeilen 2–3 zählen zu BT-44.

**`--lernen 3` misst „angelernt“ nicht.** Der Benchmark lernt nur, wenn `len(Training) > lernen`. Bei drei
Trainingsbelegen braucht man also `--lernen 2`. Dann wird auf Beleg 1–2 gelernt und Beleg 3 plus Hold-out
geprüft.

## Hold-out-Plan

| Familie | Training | Hold-out |
|---|---|---|
| F1–F7, F9 | Beleg 1–3 | Beleg 4–5 (`Referenzdaten/holdout/`), ab A1 auch Beleg 6–7 (Fehler/Falle) |
| F8, F10 | – | alle (ganze Familie Hold-out; F8 mit Beleg 6 als Falle) |

## Abdeckungsmatrix (Familie × Merkmal)

✓ = Training, H = nur im Hold-out, · = nicht enthalten.

| Merkmal | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Vorlage (Quelle) | weclapp | Lexware | JTL business | easybill | JTL creativ | DATEV WaWi | Odoo DIN 5008 | BC 1306 | Symtrax | Mustang |
| Schrift | Helvetica | Times | Helvetica | Helvetica | Helvetica | Courier | Helvetica | Times | Courier | Helvetica |
| Infoblock „Label: Wert“ nebeneinander | ✓ | · | · | ✓ | ✓ | ✓ | ✓ | H | ✓ | H |
| Label und Wert ohne Doppelpunkt | · | · | · | · | · | ✓ | ✓ | H | · | · |
| Werte gegen die Labels versetzt (Grundlinie) | · | · | · | · | ✓ | · | · | · | · | · |
| Briefkopf mit Logo-Bild | · | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | · | · |
| Seitenleiste rechts (Form XObject) | · | · | ✓ | · | · | · | · | · | · | · |
| Label über Wert (nur angelernte Familien) | · | · | ✓ | · | · | · | · | · | · | · |
| Umgekehrte Reihenfolge im Content-Stream | · | · | ✓ | · | · | · | · | · | · | · |
| Kopf/Fuß als Bild | · | · | · | · | · | · | · | H | · | · |
| Datum TT.MM.JJ | ✓ | · | · | · | · | · | · | · | · | · |
| Datum TT.MM.JJJJ | · | (✓) | ✓ | ✓ | ✓ | ✓ | ✓ | H | ✓ | H |
| Datum ausgeschrieben („8. Oktober 2026“) | · | ✓ | · | · | · | · | · | · | · | · |
| A5 | · | H | · | · | · | · | · | · | · | · |
| Mehrseitig mit Übertrag | · | · | ✓ | · | ✓ | ✓ | · | · | · | · |
| Mehrseitig ohne Übertrag | · | · | · | · | · | · | · | H | · | · |
| Gruppen-Zwischensumme in der Tabelle | · | · | · | · | · | ✓ | · | · | · | · |
| Mehrzeilige Positionstexte | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | H | ✓ | H |
| Artikelnummer-Spalte | ✓ | · | ✓ | ✓ | ✓ | ✓ | · | H | ✓ | · |
| Einheit nur im Produktnamen | · | · | · | · | · | · | · | · | · | H |
| Kunde 3 Namenszeilen | ✓ | ✓ | ✓ | ✓ | H | ✓ | H | H | ✓ | H |
| ohne Bestellnummer | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | H | ✓ | H |
| Auftrags-Nr. des Verkäufers (nicht BT-13) | ✓ | · | ✓ | · | ✓ | ✓ | ✓ | · | · | · |
| keine Kundennummer gedruckt | · | · | · | · | · | · | ✓ | · | · | · |
| Skonto | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | H | ✓ | H |
| festes Zahldatum | ✓ | ✓ | · | ✓ | · | · | · | · | · | H |
| Postfach statt Straße (einmal im ganzen Set) | · | · | · | · | · | · | · | H | · | · |
| 19 % einheitlich | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | H | · | · |
| 7/19 % gemischt, Satz je Position, eine USt-Summenzeile | · | · | · | · | · | · | · | · | ✓ | · |
| 7/19 % gemischt, USt-Tabelle je Satz | · | · | · | · | · | · | · | · | · | H |
| Prüfen: Summenblock rechnet falsch | H (Netto) | H (Brutto) | · | · | · | · | H (Brutto) | · | H (USt) | · |
| Prüfen: Pflichtangabe fehlt | · | · | · | H (BT-72) | · | · | · | · | · | · |

**Postfach:** Genau ein Hold-out-Beleg in F8 (Nr. 4) bekommt eine Postfach-Anschrift. Er wird im JSON unter
`test_flags.po_box` markiert. Sonst kommt im Set kein Postfach vor.

**Festes Zahldatum F10:** „Bitte überweisen bis TT.MM.JJJJ.“ ist der Zahltext der Vorlage (alle Belege).
F4 druckt ebenfalls immer ein festes Datum („Bitte begleichen Sie … bis zum …“).

**GUI-Grenzfall USt-Tabelle je Satz (F10):** Der Druck hat unter „zzgl. USt“ eine kleine Tabelle mit einer Zeile
je Satz (7 % und 19 %, jeweils Nettobetrag und USt-Betrag), darunter „USt gesamt“. Der Benchmark vergleicht
BT-110 als Summe. In der GUI ist der Fall nur sauber, wenn „USt gesamt“ oder beide Satzzeilen als BT-110
bestätigt werden. Wird nur eine Satzzeile angeklickt, ist BT-110 zu klein. Das ist ein bewusster Grenzfall,
darum ist F10 ganz Hold-out.

**Grenze des Benchmarks bei gemischten Sätzen (F9, F10):** `fiktiv_soll` setzt BT-119 aus dem einen Feld
`vat_rate` („19.00“). Die Aufschlüsselung steht in `vat_breakdown`. BT-119 ist für F9/F10 deshalb nicht
aussagekräftig.

**Weggelassen im ganzen Set (OUT):** Rabattspalte, Zu-/Abschläge (BG-20/21), Steuerkategorien A/B, 0 %,
Reverse Charge, §13b, nachgestelltes Minus, Positionstext über einen Seitenumbruch, Glyphen-Tricks, AT/CH,
Lieferadresse, Vermerkzone, BT-51, Scans/OCR. Was je Vorlage dadurch fehlt, steht in `QUELLEN.md`.

## A1 (20.11.2026): Fehler- und Fallenbelege, Set eingefroren

Zehn neue Belege, alle **Hold-out** (`Referenzdaten/holdout/`), je Familie hinten angehängt (Beleg 6 bzw. 7).
Die 50 alten Belege sind byte-gleich geblieben (SHA-256 vor/nach geprüft). Keine neuen Belege in F9/F10
(7/19 %, außerhalb v1). Alle neuen Belege: Inland, B2B, nur 19 %, keine Rabatte, keine negativen Beträge.

| Familie | Beleg | Rolle | Art | Was gedruckt ist |
|---|---|---|---|---|
| F1 | 006 K261703 | holdout-fehler | `summe_positionen` | Versandposition (11,90 €) nicht im gedruckten Netto; USt/Endsumme aus dem gedruckten Netto richtig |
| F1 | 007 K261721 | holdout-falle | `angebot_nr` | „Angebots-Nr.: A261662“ direkt unter „Rechnungs-Nr.: K261721“ |
| F2 | 006 2026-0450 | holdout-fehler | `iban_pruefziffer` | IBAN im Fuß mit vertauschten Prüfziffern |
| F3 | 006 RE202603351 | holdout-fehler | `ust_id_pruefziffer` | USt-IdNr. in der Seitenleiste mit falscher Prüfziffer |
| F4 | 006 (ohne Nummer) | holdout-fehler | `rechnungsnummer_fehlt` | „Rechnung:“ ohne Wert, Überschrift nur „Rechnung“; Datei `Rechnung_006_ohne-Nummer.pdf` |
| F5 | 006 RE26-11006 | holdout-fehler | `rechnungsdatum_fehlt` | „Datum:“ ohne Wert, Lieferdatum steht da |
| F6 | 006 60611 | holdout-fehler | `netto_brutto` | Endbetrag mit Zahlendreher (≠ Zwischensumme + MWSt) |
| F6 | 007 40711 | holdout-falle | `zweites_datum` | „Auftragsdatum“ (12 Tage früher) direkt über „Datum“ |
| F7 | 006 INV/2026/00342 | holdout-fehler | `faelligkeit_vor_datum` | Fälligkeitsdatum = Rechnungsdatum − 30 Tage |
| F8 | 006 103006 | holdout-falle | `nummer_aehnlich` | „Projektnr. 103619“ (gleiches Format wie die Rechnungsnummer) unter Debitorennr./Ihre Referenz |

Zusätzliche Soll-Felder (nur diese zehn Belege):
- `rolle`, `erwarteter_status` (`fehler` / `ok`), `erwartete_hinweise` (BT und Wortlaut angelehnt an
  `pflichtpruefung`/`rechnen`; maßgeblich ist das BT), `moegliche_folgehinweise`
- `fehlerart`, `fehler_beschreibung`, `fehler_detail` bzw. `falle`, `falle_beschreibung`, `falle_detail`
- `totals_berechnet` (rechnerisch richtig). **Bei diesen Belegen ist `totals` = `totals_printed` = gedruckt.**
  Achtung: Bei den fünf alten Prüfen-Fällen (Phase 2) ist `totals` weiterhin berechnet und nur
  `totals_printed` gedruckt.
- Seller, Rechnungskopf und Zahldaten enthalten, was gedruckt ist (falsche IBAN/USt-IdNr., leere Nummer bzw.
  leeres Datum, Fälligkeit vor dem Datum). Bei F5/006 sind Fälligkeit/Skonto aus dem nicht gedruckten
  Datum berechnet (`fehler_detail.nicht_gedruckt`).

Je Fehlerbeleg genau ein Bruch (Selbstcheck `selbstcheck_a1` prüft alle Bruchsorten gegeneinander), Fallen
haben keinen Bruch. Bestand: 60 Belege; 24 Training (fehlerfrei), 21 Hold-out, 12 Hold-out-Fehler
(7 neu + 5 alte Prüfen-Fälle), 3 Hold-out-Fallen; 10 Belege (F9/F10) außerhalb v1.

**Eingefroren als Version 1.0.0** (`MANIFEST.json`: Hash je Datei, Rolle je Beleg, `ausserhalb_v1` für
F9/F10). Änderungen an Belegen nur mit neuer Version im Manifest.

## Referenz-JSON

- Schema wie `tests/daten/fiktiv`, zusätzlich `BT-72` (Leistungsdatum) und `BT-119` („19.00“).
- Weitere Felder:
  - `erwarteter_status` (`ok` / `prüfen`) und `erwartete_hinweise`
  - `totals` (berechnet) und `totals_printed` (gedruckt)
  - `pages[]` mit Übertrag und Vortrag
  - `druck` (Datumsformat, Schrift, Seitenformat)
  - `test_flags`
- `kosit` und `verapdf` sind `null`. Hinweis im JSON: lokal nicht validierbar, folgt in einer späteren Phase.
- `korrekturen` ist `null`. Hinweis im JSON: erst beim echten Anlernen messbar.

**Prüfen-Fälle:** Rechenfehler im Summenblock oder eine fehlende Pflichtangabe, höchstens ein Fall je Familie,
im ganzen Set fünf Fälle (F1, F2, F4, F7, F9; alle im Hold-out).
Der Benchmark liest die gedruckten Werte, deshalb schlägt beim Prüfen-Fall genau das falsch gedruckte Feld
erwartbar fehl.
