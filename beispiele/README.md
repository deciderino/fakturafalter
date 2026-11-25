# Beispieldateien (alle Daten erfunden)

Absender immer **Muster GmbH**, USt-IdNr. DE123456788, Domains `*.example`. Keine echten Personen/Firmen.

| Datei | Zweck | Kodierung / Aufbau |
|---|---|---|
| `variante-a_positionen_utf8.csv` | CSV: eine Zeile je Position, Kopf wiederholt | UTF-8, `,`, Dezimalpunkt, ISO-Datum |
| `variante-b_wawi_cp1252.csv` | CSV: Satzart-Spalte K/P (Kopf/Position) | **Windows-1252**, `;`, **Dezimalkomma**, TT.MM.JJJJ, Umlaute/„“/² |
| `variante-c_festbreite_cp1252.txt` | Feste Spaltenbreiten, Satzart in Spalte 1 | Windows-1252, implizite Nachkommastellen |
| `profil-variante-a.json` | Zuordnungsprofil zu A (JSON-Form) | |
| `profil-variante-b.yaml` | Zuordnungsprofil zu B (vollständigste Form, kommentiert) | |
| `profil-variante-c.yaml` | Zuordnungsprofil zu C (Spaltenpositionen) | |
| `variante-d_rabatt_gutschrift_lastschrift.csv` | CSV: Rabatt in % je Position, Rabatt-/Zuschlagszeile (Spalte Zeilenart), Gutschrift über Belegart mit negativen Beträgen und Bezug, SEPA-Lastschrift, Anzahlung | UTF-8, `;`, Dezimalkomma |
| `profil-variante-d.yaml` | Zuordnungsprofil zu D | |
| `variante-s_steuerfaelle.csv` | CSV (ab 0.9.7): Reverse Charge, igL nach Österreich, Ausfuhr in die Schweiz, nicht steuerbar (USD), 19 % in USD mit Kurs, gemischt RC + 19 % | UTF-8, `;`, Dezimalkomma |
| `profil-variante-s.yaml` | Zuordnungsprofil zu S (Steuerkennzeichen RC/IGL/EX/NSTB, Währung, Kurs, Steuerhinweis) | |
| `variante-u_kleinunternehmer.csv` | CSV (ab 0.9.7): Kleinunternehmer, Steuer 0 – braucht `absender: kleinunternehmer: true` | UTF-8, `;` |
| `kundenstamm.csv` | Kundennummer → Name, Anschrift, USt-Id, BT-49, Leitweg-ID (BT-10), Ziel, Format | UTF-8, `;` |
| `druckauftrag-wawi.pdf` | **Ein** Druckauftrag mit **zwei** Rechnungen (RE-2026-0101 über 2 Seiten mit Übertrag, RE-2026-0102), Courier, Textebene | PDF |
| `vorlage-wawi-druck.yaml` | Zonen-/Anker-Vorlage zum PDF | |
| `textdruck-wawi_cp1252.txt` | Reiner Textdruck (Generic/Text Only), RE-2026-0103, Seitenende = Formfeed | Windows-1252 ⚠️ echte Treiber liefern evtl. CP850 |

Ordner **`layout/`**: Layouteditor (0.7.0) – `layout-beispiel.yaml` (Block `layout:` für die Konfiguration: Logo rechts, Empfänger rechts, Zahlung neben den Summen, eigenes Text- und Bildfeld), `logo.png` (Fantasie-Logo „Musterwerk“), `briefpapier-seite1.pdf` und `briefpapier-folgeseite.pdf` (PDF/A-taugliches Briefpapier). Erzeugt mit `tools/layout_beispiel.py`.

Ordner **`poc/`**: Proof of Concept (Tischlerei Muster GmbH → Beispiel Bau GmbH, TM-2026-0042: CSV mit Käuferdaten + Druck-PDF, Profil mit Verkäufer/Bank und festem Format ZUGFeRD EN 16931, ohne Kundenstamm).

Erwartete Summen (zum Gegenprüfen): RE-2026-0101 netto 327,40 / USt 57,42 / brutto 384,82 · RE-2026-0102 174,50 / 33,16 / 207,66 · RE-2026-0103 145,00 / 27,55 / 172,55.
Variante S (brutto in Rechnungswährung): RE-S-2026-001 1.784,00 · 002 160,00 · 003 498,00 · 004 2.160,00 USD · 005 3.174,92 USD (USt 506,92 USD = 467,21 EUR) · 006 892,65. Variante U: KU-2026-014 217,00.
Variante D: RE-2026-0201 361,50 / 68,69 / 430,19 (Lastschrift) · GS-2026-0007 (Gutschrift) 137,40 / 21,32 / 158,72 · RE-2026-0202 250,00 / 47,50 / 297,50, zahlbar 197,50.

Fallen, die absichtlich drin sind: lange Bezeichnung ragt in die Menge-Spalte (PDF), Absenderzeile im Anschriftenfeld, Übertrag-Zeilen, Bestellnummer nur bei einer Rechnung, Steuerschlüssel A/B (PDF) bzw. 1/2 (CSV), Einheiten „Stück“/„Std.“/„psch.“.

## Ordner `pdf-erkennung/` (PDF-Erkennung: Gegenprüfung, Anlernen, nur PDF)

Sechs erfundene Verkäufer mit je acht Rechnungen (CSV + Druck-PDF) in `eingang/` – sieben zum Anlernen,
die achte zum Test „nur PDF“. Prüfziffern von USt-IdNr. und IBAN sind gültig (Bankleitzahl 00000000).
Erzeugt mit `erzeuge_beispiele.py` (deterministisch); Konfiguration `konfiguration.yaml`.

| Profil | Nummern | CSV | Druck-Layout und Besonderheiten |
|---|---|---|---|
| `baeckerei` | SK-2026-0412…0419 | UTF-8, `;`, Dezimalkomma | Tabelle mit Gitter, 7 % und 19 % gemischt, USt nur je Satz gedruckt |
| `elektro` | EF-1041…1048 | cp1252, `,`, Dezimalpunkt | Seitenleiste links, EF-1043 mit 32 Positionen über 2 Seiten und Übertrag |
| `gartenbau` | GL-2026-118…125 | Tabulator, ISO-Datum | Beschriftung über dem Wert, Leistungsmonat, Rabattzeile mit negativem Preis |
| `musikschule` | KR-2026-031…038 | UTF-8, `;` | Spalten von/bis je Position, nur Steuernummer, steuerfrei (§ 4 Nr. 21 UStG) und 7 % |
| `pixelwerk` | PW-INV-2026-0087…0094 | UTF-8 mit BOM, `\|`, ISO-Datum | englische Beschriftung, Zahlen 1,234.56, Zebrastreifen, Leistungszeitraum |
| `metallbau` | MK-26-0412…0419 | cp1252, `;`, TT.MM.JJ | Schreibmaschinenschrift (Courier), Käufer über Kundennummer und `kundenstamm-metallbau.csv` |

`fehlerfaelle/` – jeweils CSV und Druck passen absichtlich nicht zusammen:

| Fall | Fehler | Erwartet |
|---|---|---|
| SK-2026-0499 | Einzelpreis in der CSV 0,20 € höher | Prüfen: Netto, USt, Brutto weichen ab |
| PW-INV-2026-0199 | Rechnungsdatum im Druck einen Tag später | Prüfen: Rechnungsdatum |
| GL-2026-199 | Druck zeigt GL-2026-919 | Prüfen: Rechnungsnummer |
| KR-2026-099 | kein Leistungszeitraum | Prüfen: Pflichtangabe BT-72/BG-14 fehlt |
| EF-1099 | andere IBAN im Druck | Prüfen: IBAN |

## Ordner `xml/` (Modus „PDF + XML“)

`NB-26-1001.pdf` (Druck aus `industrie/eingang/`) und `NB-26-1001.xml` (ZUGFeRD/CII, EN 16931, mit Fakturafalter
aus `industrie/` erzeugt) mit gleichem Namen; `konfiguration-pdf-xml.yaml`. Erwartet: brutto 1.075,28, „gültig“.

## Ordner `xml-eingang/` (nur XML, alle Feldgruppen nach EN 16931)

| Datei | Inhalt | Erwartet |
|---|---|---|
| `XR-2026-0301_ubl_rabatt_lastschrift.xml` | XRechnung UBL: Rabatt 2 % und Fracht auf Belegebene, Positionsrabatt 10 %, Listenpreis mit Nachlass, Positionszuschlag, Anzahlung, SEPA-Lastschrift, Anhänge, Lieferanschrift, Referenzen | brutto 1.230,70, zahlbar 1.000,00 |
| `GS-2026-0008_cii_gutschrift.xml` | XRechnung CII: Gutschrift (381) mit Bezug auf RE-2026-0101 | brutto 158,72 |
| `GS-2026-0009_ubl_gutschrift.xml` | XRechnung UBL `CreditNote` mit Bezug und Rabatt | brutto 353,43 |

| `XU-2026-0007_ubl_usd.xml` | UBL in USD mit Steuerwährung EUR (BT-6/BT-111) und Kursnotiz (ab 0.9.7) | brutto 2.380,00 USD, USt 350,23 EUR |
| `XC-2026-0008_cii_usd.xml` | dasselbe als CII | wie oben |

Alle werden ohne Warnung gelesen, und KoSIT (XRechnung 3.0.2) meldet sie als gültig.

## Ordner `steuerfaelle/` (Nur PDF, ab 0.9.7)

Elf Druck-PDFs dreier erfundener Absender mit fertig angelernten Vorlagen: Steuerspalte je Position (AE, K, G, O,
USD mit Kurs, gemischt), Satz nur in den Summen (Fall aus dem Steuerhinweis) und Kleinunternehmer. Einzelheiten in
[steuerfaelle/README.md](steuerfaelle/README.md).
