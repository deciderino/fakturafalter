# Pflichtangaben & Prüfmatrix für Fakturafalter

Stand: 01.11.2026 · Nur Recherche. Am Code wurde nichts geändert. Diese Datei ist nicht committet.

Legende:
- ✅ verifiziert: im Primärtext oder in einem offiziellen Artefakt nachgelesen, Quelle angegeben.
- ⚠️ unsicher: Sekundärquelle, nicht wörtlich geprüft oder Auslegungsfrage.
- **[Gesetz]**, **[EN]**, **[XR]** = Pflicht aus UStG/UStDV, EN 16931 oder XRechnung-CIUS.
- **[Empfehlung]** = unser Vorschlag, keine Rechtspflicht.

Geprüfte Artefakte, lokal unter `/opt/erech-tools`, nicht online:
- KoSIT-Konfiguration XRechnung 3.0.2 (Release 31.08.2026)
- XRechnung-Schematron 2.6.0
- CEN-Schematron EN 16931 1.3.16
- KoSIT-Validator 1.6.3

Die Regeltexte wurden aus den `.sch`/`.xsl`-Dateien extrahiert.

---

## 1. Rechtliche Grundlage

### 1.1 § 14 Abs. 4 UStG, Pflichtangaben jeder Rechnung ✅
Quelle: https://www.gesetze-im-internet.de/ustg_1980/__14.html

| Nr. | Angabe | BT-Felder (EN 16931) |
|---|---|---|
| 1 | Vollständiger Name und vollständige Anschrift des leistenden Unternehmers und des Leistungsempfängers | Verkäufer: BT-27, BG-5 (BT-35 Straße, BT-37 Ort, BT-38 PLZ, BT-40 Land). Käufer: BT-44, BG-8 (BT-50, BT-52 Ort, BT-53 PLZ, BT-55 Land) |
| 2 | Steuernummer **oder** USt-IdNr. des Leistenden | BT-32 (Steuernummer, CII schemeID FC) oder BT-31 (USt-IdNr., schemeID VA) |
| 3 | Ausstellungsdatum | BT-2 |
| 4 | Fortlaufende, einmalige Rechnungsnummer | BT-1 |
| 5 | Menge und Art (handelsübliche Bezeichnung) | BT-129 + BT-130 (Menge/Einheit), BT-153 (Bezeichnung) |
| 6 | Zeitpunkt der Lieferung/Leistung bzw. der Vereinnahmung des Entgelts | BT-72 **oder** BG-14 (BT-73/74) **oder** BG-26 (Positionszeitraum) |
| 7 | Entgelt nach Steuersätzen/-befreiungen aufgeschlüsselt, jede im Voraus vereinbarte Minderung | BG-23: BT-116 je BT-118/BT-119. Minderung (Skonto/Bonus): BT-20 (XR-Skontosyntax BR-DE-18), BG-20/21 |
| 8 | Steuersatz und Steuerbetrag **oder** Hinweis auf Steuerbefreiung | BT-119/BT-117, Summe BT-110. Befreiung: BT-120/BT-121 |
| 9 | In Fällen des § 14b Abs. 1 S. 5: Hinweis auf Aufbewahrungspflicht des Empfängers (Bauleistung an Privat) | BT-22 (BG-1). Für unser B2B-Szenario praktisch nicht relevant |
| 10 | Bei Gutschrift: Angabe „Gutschrift“ | BT-3 = 389 (self-billed) + Text „Gutschrift“, z. B. BT-22 ⚠️ (Abbildung im Text ist Auslegung) |

- § 31 Abs. 2 UStDV ✅: Name und Anschrift müssen eindeutig feststellbar sein.
- § 31 Abs. 4 UStDV ✅: Als Leistungszeitpunkt reicht der Kalendermonat.
- Quelle: https://www.gesetze-im-internet.de/ustdv_1980/__31.html
- ⚠️ nicht wörtlich geprüft: Nach UStAE 14.5 Abs. 16 genügt der Hinweis „Leistungsdatum = Rechnungsdatum“. Das Datum muss aber trotzdem erkennbar angegeben sein.

### 1.2 § 14a UStG, zusätzliche Angaben in Sonderfällen ✅
Quelle: https://www.gesetze-im-internet.de/ustg_1980/__14a.html

| Fall | Zusätzliche Pflicht | EN-Abbildung |
|---|---|---|
| Abs. 1: Leistung in anderem EU-Staat, Empfänger schuldet die Steuer | USt-IdNr. des Leistenden **und** des Empfängers | BT-31 + BT-48, Kategorie AE |
| Abs. 3: innergemeinschaftliche Lieferung | USt-IdNr. beider Parteien | BT-31 + BT-48, Kategorie K |
| Abs. 5: § 13b (Reverse Charge) | Angabe „Steuerschuldnerschaft des Leistungsempfängers“; kein gesonderter Steuerausweis | Kategorie AE, BT-120 (Text) / BT-121 (VATEX-EU-AE), Steuer 0 |
| Abs. 6/7: Reiseleistungen, Differenzbesteuerung, Dreiecksgeschäft | jeweilige Hinweise | Für uns nicht relevant, nur erwähnt |

### 1.3 Erleichterungen
- **§ 33 UStDV, Kleinbetragsrechnung bis 250 € brutto** ✅
  - Nötig sind nur: Name und vollständige Anschrift des Leistenden, Ausstellungsdatum, Menge/Art, Entgelt + Steuerbetrag in einer Summe, Steuersatz bzw. Befreiungshinweis.
  - **Nicht nötig:** Empfänger, Steuernummer, Rechnungsnummer.
  - **Gilt nicht** für §§ 3c, 6a (i.g. Lieferung) und 13b (Reverse Charge).
  - Quelle: https://www.gesetze-im-internet.de/ustdv_1980/__33.html
  - ✅ Nach § 33 UStDV darf eine Kleinbetragsrechnung immer als sonstige Rechnung (z. B. Papier/PDF) ausgestellt werden. Wird sie als E-Rechnung im EN-Format erzeugt, bleiben die EN-Pflichtfelder trotzdem Pflicht (BT-1, BT-44 usw.).
- **§ 34a UStDV, Kleinunternehmer (§ 19 UStG)** ✅
  - Nötig: Name/Anschrift beider Parteien, Steuernummer **oder** USt-IdNr. **oder** Kleinunternehmer-Identifikationsnummer, Datum, Menge/Art, Leistungszeitpunkt, Entgelt.
  - Pflichthinweis: Für die Leistung gilt die Steuerbefreiung nach § 19 UStG.
  - Quellen: https://www.gesetze-im-internet.de/ustdv_1980/__34a.html, https://www.gesetze-im-internet.de/ustg_1980/__19.html
  - EN-Abbildung: Kategorie E + BT-120 mit Hinweis. ⚠️ Gängige Praxis, nicht normativ geprüft.

### 1.4 Wo die Angaben stehen müssen ✅
BMF-Schreiben vom 15.10.2025 (Einführung der obligatorischen E-Rechnung), Rn. 35: Alle Angaben nach §§ 14, 14a UStG müssen im **strukturierten Teil** stehen. Bei hybriden Formaten (ZUGFeRD) ist das XML führend. Was nur im PDF steht, zählt nicht.
- https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Umsatzsteuer/Umsatzsteuer-Anwendungserlass/2025-10-15-einfuehrung-obligatorische-e-rechnung.html
- Hinweis: Das PDF ließ sich per curl nicht laden (Bot-Schutz). Rn. 35 wurde über den Seitenauszug und die BMF-FAQ verifiziert.

### 1.5 Die zentrale Lücke zwischen Gesetz und Norm ✅

| Angabe | UStG | EN 16931 / ZUGFeRD EN16931 | XRechnung |
|---|---|---|---|
| Anschrift Käufer | **vollständig** (§ 14 Abs. 4 Nr. 1) | nur BG-8 mit **Ländercode** Pflicht (BR-10, BR-11). Straße/PLZ/Ort optional | Ort und PLZ Pflicht (BR-DE-8/9). Straße optional |
| Anschrift Verkäufer | vollständig | nur Ländercode Pflicht (BR-08, BR-09) | Ort/PLZ Pflicht (BR-DE-3/4) |
| Leistungsdatum | Pflicht (Nr. 6) | optional. Nur bei K Pflicht (BR-IC-11) | nur Information (BR-DE-TMP-32) |
| Steuernummer/USt-IdNr. | Pflicht (Nr. 2) | nur indirekt, je Kategorie (BR-S-02, BR-AE-02 …) | wie EN, zusätzlich BR-DE-16 |

**Folge:** Eine ZUGFeRD-Datei kann mit 0 Validierungsfehlern durchgehen, obwohl sie umsatzsteuerlich keine ordnungsgemäße Rechnung ist. Genau das ist im PoC passiert:
- Der ZUGFeRD-Guideline `urn:cen.eu:en16931:2017` läuft im KoSIT-Szenario „EN16931 (CII)“ ✅ (`/opt/erech-tools/kosit-xr/scenarios.xml`, Zeilen 652–689). Dort laufen nur CEN-Regeln, keine BR-DE-Regeln.
- Die Käuferadresse bestand nur aus dem Land, weil `cii.py` den Ländercode auf `DE` setzt.

**Fakturafalter muss Anschrift, Leistungsdatum und Steuer-ID deshalb selbst prüfen.**

---

## 2. Normative Regeln (aus den lokalen Artefakten extrahiert)

### 2.1 EN 16931 (CEN-Schematron 1.3.16), relevante Auswahl ✅
Quelle: https://github.com/ConnectingEurope/eInvoicing-EN16931 (Release validation-1.3.16)

| Regel | Inhalt |
|---|---|
| BR-01…BR-07 | Spezifikation, BT-1, BT-2, BT-3, BT-5, BT-27 (Verkäufername), BT-44 (Käufername) Pflicht |
| BR-08 / BR-09 | Verkäufer-Postanschrift BG-5 / Ländercode BT-40 Pflicht |
| BR-10 / BR-11 | Käufer-Postanschrift BG-8 / Ländercode BT-55 Pflicht |
| BR-12…BR-15 | Summen BT-106, BT-109, BT-112, BT-115 Pflicht |
| BR-16 | mind. eine Position |
| BR-21…BR-26 | Position: ID, Menge, Einheit, Nettobetrag, Bezeichnung, Nettopreis Pflicht |
| BR-27 | Nettopreis (BT-146) **nicht negativ** |
| BR-61 | Bei Überweisung (Code 30/58) Kontokennung BT-84 Pflicht |
| BR-CO-09 | USt-IdNr. mit ISO-Länderpräfix (Griechenland: EL) |
| BR-CO-10…18 | Summenarithmetik, mind. eine USt-Aufschlüsselung (BR-CO-18) |
| BR-CO-25 | Bei positivem BT-115: Fälligkeitsdatum BT-9 **oder** Zahlungsbedingungen BT-20. ⚠️ Fehlt in den 1.3.16-Artefakten, bleibt aber Normtext. Siehe https://github.com/ConnectingEurope/eInvoicing-EN16931/issues/541 (offen) und #511 |
| BR-CO-26 | Verkäufer braucht BT-29 **oder** BT-30 **oder** BT-31. Nur Steuernummer BT-32 reicht **nicht** |
| BR-S-02 / -05 / -10 | S: Verkäufer-USt-IdNr./Steuernummer Pflicht, Satz > 0, **kein** Befreiungsgrund |
| BR-Z-05 / **BR-Z-10** | Z: Satz 0, **kein** Befreiungsgrund (BT-120/121 verboten) |
| BR-E-05 / -10 | E: Satz 0, Befreiungsgrund Pflicht |
| BR-AE-02 / -05 / -10 | AE: Verkäufer-ID **und** Käufer BT-48 oder BT-47; Satz 0; Grund Pflicht |
| BR-IC-02 / -05 / -10 / -11 / -12 | K: BT-31 **und** BT-48; Satz 0; Grund; **BT-72 oder BG-14**; **Lieferland BT-80** Pflicht |
| BR-G-*, BR-O-02 | G (Export): Grund; O (nicht steuerbar): **keine** USt-IdNr. |
| BR-CL-01/04/14/16/17/23 | Codelisten: BT-3 (UNTDID 1001), Währung (ISO 4217), Land (ISO 3166-1), Zahlart (UNTDID 4461), Kategorie (UNCL 5305), Einheit (UN/ECE Rec 20/21) |
| BR-DEC-* | Beträge mit höchstens 2 Nachkommastellen |

**Korrektur zum Auftrag:** „Z mit Befreiungsgrund“ ist falsch. BR-Z-10 verbietet einen Grund bei Z. Den Grund brauchen E, AE, K, G und O.

### 2.2 ZUGFeRD-Profil EN16931 (COMFORT) vs. EN 16931
- ✅ Das Profil bildet EN 16931 vollständig ab. Es gilt in DE als vollständige Rechnung, Empfänger müssen es verarbeiten können.
  - FeRD-FAQ: https://www.ferd-net.de/standards/zugferd-faq
- ✅ Validiert wird gegen dieselben CEN-Regeln, ohne BR-DE-Regeln (KoSIT-Szenario, siehe 1.5).
- ✅ BT-10 ist im ZUGFeRD-Profil optional (0..1). Mustang meldet bei fehlendem BT-10 nur eine Warnung.
  - Quelle: Maintainer-Aussage in https://github.com/ZUGFeRD/mustangproject/issues/236
- ⚠️ Nicht wörtlich gegen die Spezifikation geprüft: Die Unterschiede zu XRechnung liegen vor allem in der Leitweg-ID, Überweisung, Verkäuferkontakt und elektronischen Adressen.
  - Quelle: https://zugferd.org/e-invoicing/1.0.0/faq.en.html

### 2.3 XRechnung 3.0.x (Schematron 2.6.0), zusätzlich zu EN ✅
Quellen:
- https://github.com/itplr-kosit/xrechnung-schematron
- https://github.com/itplr-kosit/validator-configuration-xrechnung

| Regel | Inhalt | Schwere |
|---|---|---|
| BR-DE-1 | Zahlungsanweisungen BG-16 | fatal |
| BR-DE-2, -5, -6, -7 | Verkäuferkontakt BG-6: Name BT-41, Telefon BT-42, E-Mail BT-43 | fatal |
| BR-DE-3 / -4 | Verkäufer Ort / PLZ | fatal |
| BR-DE-8 / -9 | Käufer Ort / PLZ | fatal |
| BR-DE-10 / -11 | Lieferort Ort / PLZ (falls BG-15 vorhanden) | fatal |
| BR-DE-14 | Steuersatz BT-119 | fatal |
| BR-DE-15 | Käuferreferenz BT-10 (bei öffentlichen Auftraggebern: Leitweg-ID) | fatal |
| BR-DE-16 | Bei S/Z/E/AE/K/G/L/M: BT-31 oder BT-32 oder BG-11 | fatal |
| BR-DE-17 | BT-3 aus erlaubter Teilmenge | Warnung |
| BR-DE-18 | Skonto-Syntax in BT-20 | fatal |
| BR-DE-19 | IBAN-Format | Warnung |
| BR-DE-21 | Spezifikationskennung BT-24 | Warnung |
| BR-DE-23-a/b | Bei 30/58: BG-17 Pflicht, keine Karte/Lastschrift | fatal |
| BR-DE-26 | Korrekturrechnung 384 braucht BG-3 (Bezug auf Vorrechnung) | fatal |
| BR-DE-27 / -28 | Telefon mit mind. 3 Ziffern / E-Mail-Format | Warnung |
| BR-DE-TMP-32 | Lieferdatum BT-72 / BG-14 / BG-26 | Information |
| PEPPOL-EN16931-R010 / R020 | Elektronische Adresse Käufer BT-49 / Verkäufer BT-34 | fatal |
| PEPPOL-EN16931-R008 | keine leeren Elemente | fatal |

---

## 3. Code-Analyse: was heute geprüft wird

Dateien: `src/fakturafalter/aufbau.py`, `rechnen.py`, `pipeline.py`, `cii.py`, `adapter_csv.py`, `werte.py`.
Ein Status „fehler“ oder „pruefen“ hält die Rechnung an. „warnung“ und „info“ halten **nicht** an.

| Prüfung heute | Wo | Reaktion |
|---|---|---|
| CSV-Spalte fehlt, Zahl/Datum unlesbar | adapter_csv | fehler |
| BT-1 / BT-2 fehlt | aufbau | pruefen |
| BT-72 fehlt | aufbau | **nur warnung** |
| keine Positionen | aufbau | pruefen |
| BT-153 fehlt | aufbau | pruefen |
| Einheit/Steuerschlüssel nicht zugeordnet | aufbau `_map` | pruefen/fehler (bzw. fester Ersatz laut Mapping) |
| Kundenname (BT-44) fehlt in der Quelle | aufbau | pruefen |
| Ausgabeformat unbekannt | aufbau | pruefen |
| Konfidenz unter Schwelle | aufbau | pruefen |
| Positionsbetrag ≠ Kontrollwert, BT-109/112 ≠ Kontrollwert | rechnen | pruefen |
| E/AE/K/G/O ohne BT-120/121 | rechnen | pruefen |
| negativer Bruttobetrag bei 380 | rechnen | pruefen |
| doppelte BT-1 im selben Lauf | pipeline | fehler |
| Ausgabedatei existiert schon | pipeline | pruefen |
| CSV ↔ PDF-Gegenprüfung (Brutto, Netto, Positionen, Kunde, Datum) | pipeline | pruefen |
| XRechnung ohne Leitweg-ID | pipeline/cii | **nur info**, BT-10 wird still mit der Kundennummer gefüllt |
| KoSIT/Mustang | validierung | nur auf Anforderung (Java), nicht im Standardlauf |

### Lücken (verifiziert am Code)
1. **Käuferanschrift** (Straße BT-50, PLZ BT-53, Ort BT-52) wird nicht geprüft. `cii.py` schreibt PLZ/Ort nur, wenn vorhanden, und setzt das Land standardmäßig auf `DE`. Folge: Ein ZUGFeRD-XML ohne Adresse besteht die EN-Validierung.
2. **Verkäuferdaten** (Name, Anschrift, BT-31/BT-32) werden gar nicht geprüft. Sie kommen aus Profil/Konfig.
3. **Menge/Preis leer → still 0** (`aufbau.py` Z. 97–98, `adapter_csv._typisieren` gibt bei leerer Zelle `None` zurück). Eine Position mit Menge 0 oder Preis 0 läuft durch, sofern keine Kontrollsumme widerspricht.
4. **Leistungsdatum** fehlt → nur warnung, obwohl § 14 Abs. 4 Nr. 6 es verlangt.
5. **BR-CO-25**: Fälligkeit/Zahlungsbedingungen werden nicht geprüft. Die Fälligkeit wird zwar aus `ziel_tage` berechnet, aber nur, wenn ein Ziel gesetzt ist.
6. **BR-CO-26**: Ein Verkäufer mit nur Steuernummer und ohne BT-30 erzeugt ein ungültiges EN-XML. Ungeprüft.
7. **Satz vs. Kategorie** (S > 0; Z/E/AE/K/G/O = 0; Z ohne Grund nach BR-Z-10) wird nicht geprüft.
8. **AE**: Käufer-USt-IdNr. BT-48 nicht geprüft. **K**: BT-31 + BT-48, BT-72 und **Lieferland BT-80** nicht geprüft. `cii.py` schreibt BG-15 gar nicht, also scheitert K immer an BR-IC-12.
9. **IBAN** bei Zahlart 58 nicht auf Vorhandensein oder Prüfziffer geprüft (BR-61, BR-DE-23).
10. **Codelisten** (BT-3, BT-5, BT-40/55, BT-130) werden nicht gegen die Listen geprüft. Fehlt die Einheit, wird still `C62` gesetzt.
11. **XRechnung-Pflichten** (BT-34, BT-49, Verkäuferkontakt BG-6, BT-10) werden nicht vor dem Erzeugen geprüft. BT-10 fällt still auf die Kundennummer zurück. Bei Behörden ist das falsch (Leitweg-ID).
12. **Dublette über Läufe hinweg**: Nur die Existenz der Ausgabedatei wird geprüft, nicht das Protokoll (`protokoll.tsv`). Datei verschoben → Dublette unentdeckt.
13. **Negativer Einzelpreis** (BR-27) wird nicht abgefangen.
14. Kleinbetrag (§ 33) und Kleinunternehmer (§ 34a) werden nicht unterstützt bzw. nicht erkannt.
15. Beispieldaten: Die Demo-USt-IdNr. `DE000000000` (`beispiele/poc/profil-poc.yaml`) hat eine **ungültige Prüfziffer** (lokal nachgerechnet). Mit einer Prüfziffernprüfung müsste sie z. B. auf `DE123456788` geändert werden (prüfziffergültig, ein bekannter Platzhalter). Die Demo-IBAN `DE36 0000 …` ist prüfziffergültig.

---

## 4. Prüfmatrix

Spalten:
- „ZF“ = ZUGFeRD EN16931, „XR“ = XRechnung.
- Pflicht-Spalten: P = Pflicht durch Standard/Validator, – = nicht durch den Standard erzwungen.
- Reaktion = unser Vorschlag. **fehler** = blockiert, nicht korrigierbar ohne Datenänderung. **pruefen** = blockiert, manuelle Freigabe. **warnung** = läuft durch.

### 4.1 Gesetzliche/normative Pflichtfelder

| Feld/Regel | Quelle | ZF | XR | Reaktion (Vorschlag) | heute geprüft |
|---|---|---|---|---|---|
| BT-1 Rechnungsnummer | § 14 Abs. 4 Nr. 4; BR-02 | P | P | fehler | ja (pruefen) |
| BT-2 Rechnungsdatum | Nr. 3; BR-03 | P | P | fehler | ja (pruefen) |
| BT-3 Typ aus UNTDID 1001 (XR: erlaubte Teilmenge) | BR-CL-01; BR-DE-17 | P | P (Warn.) | fehler | nein |
| BT-5 Währung ISO 4217 | BR-05, BR-CL-04 | P | P | fehler | nein |
| BT-27 Verkäufername | Nr. 1; BR-06 | P | P | fehler | nein |
| BT-35 Straße Verkäufer | Nr. 1 (Gesetz) | – | – | fehler | nein |
| BT-37/38 Ort/PLZ Verkäufer | Nr. 1; BR-DE-3/4 | – | P | fehler | nein |
| BT-40 Land Verkäufer (ISO 3166) | BR-09, BR-CL-14 | P | P | fehler | nein |
| BT-31 oder BT-32 Verkäufer | Nr. 2; BR-DE-16; BR-S-02 | indirekt | P | fehler | nein |
| BT-29/30/31 vorhanden (nicht nur BT-32) | BR-CO-26 | P | P | fehler | nein |
| BT-44 Käufername | Nr. 1; BR-07 | P | P | fehler | ja (pruefen) |
| BT-50 Straße Käufer | Nr. 1 (Gesetz) | – | – | **pruefen** (Postfach möglich) | nein |
| BT-52/53 Ort/PLZ Käufer | Nr. 1; BR-DE-8/9 | – | P | **fehler** | nein |
| BT-55 Land Käufer | BR-11 | P | P | fehler, **kein stilles DE** | nein (Default DE) |
| BT-72 / BG-14 Leistungsdatum/-zeitraum | Nr. 6; BR-IC-11; BR-DE-TMP-32 | nur K | Info | **pruefen** (Kalendermonat genügt, § 31 Abs. 4 UStDV) | nur warnung |
| BT-129 Menge (vorhanden, ≠ 0) | Nr. 5; BR-22 | P | P | fehler | nein (leer → 0) |
| BT-130 Einheit (Rec 20/21) | Nr. 5; BR-23, BR-CL-23 | P | P | pruefen | teils (Mapping) |
| BT-153 Bezeichnung | Nr. 5; BR-25 | P | P | fehler | ja (pruefen) |
| BT-146 Nettopreis vorhanden, ≥ 0 | BR-26, BR-27 | P | P | fehler | nein (leer → 0) |
| BT-151/152 Kategorie + Satz | Nr. 7/8; BR-CO-18, BR-S/Z/E-05, BR-DE-14 | P | P | fehler | teils (Mapping) |
| Satz passt zur Kategorie (S > 0, sonst 0) | BR-S-05, BR-Z-05, BR-E-05, BR-AE-05, BR-IC-05 | P | P | fehler | nein |
| Z ohne Befreiungsgrund | BR-Z-10 | P | P | fehler | nein |
| E/AE/K/G/O mit BT-120/121 | Nr. 8; BR-E-10, BR-AE-10, BR-IC-10 … | P | P | fehler | ja (pruefen) |
| AE: BT-31/32 Verkäufer + BT-48 (oder BT-47) Käufer + Hinweis „Steuerschuldnerschaft des Leistungsempfängers“ | § 14a Abs. 1/5; BR-AE-02 | P | P | fehler | nur Grund |
| K: BT-31 + BT-48 + BT-72/BG-14 + BT-80 | § 14a Abs. 3; BR-IC-02/11/12 | P | P | fehler (BG-15 fehlt in cii.py) | nein |
| O: keine USt-IdNr. | BR-O-02 | P | P | fehler | nein |
| Summen/Arithmetik | BR-CO-10…17 | P | P | fehler | ja (Kontrollwerte) |
| BT-9 oder BT-20 bei Zahlbetrag > 0 | BR-CO-25 ⚠️ (nicht im 1.3.16-Schematron) | P (Norm) | P (Norm) | pruefen | nein |
| BT-84 IBAN bei Zahlart 30/58 | BR-61; BR-DE-23 | P | P | fehler | nein |
| BG-16 Zahlungsanweisung | BR-DE-1 | – | P | fehler (nur XR) | nein |
| BT-10 Käuferreferenz | BR-DE-15 | – | P | XR: fehler bei Behörde ohne Leitweg-ID, sonst pruefen | info, stiller Fallback |
| BT-34 / BT-49 elektronische Adresse | PEPPOL-R020/R010 | – | P | fehler (nur XR) | nein |
| BG-6 Verkäuferkontakt (Name, Telefon, E-Mail) | BR-DE-2/5/6/7 | – | P | fehler (nur XR) | nein |
| BG-3 Vorrechnung bei 384 | BR-DE-26 | – | P | fehler (nur XR) | nein |
| „Gutschrift“-Hinweis bei 389 | § 14 Abs. 4 Nr. 10 | – | – | pruefen ⚠️ | nein |
| § 19-Hinweis bei Kleinunternehmer | § 34a Nr. 5 UStDV | – | – | fehler (falls Modus aktiv) | nein |
| Kleinbetrag ≤ 250 € nur ohne 13b/6a/3c | § 33 UStDV | – | – | Info, keine Lockerung der EN-Pflichtfelder | nein |

### 4.2 Plausibilitätsprüfungen [Empfehlung, keine Rechtspflicht]

| Prüfung | Grundlage | Reaktion |
|---|---|---|
| USt-IdNr. DE = `DE` + 9 Ziffern, Prüfziffer ISO 7064 MOD 11,10 | ✅ BZSt-Merkblatt https://www.bzst.de/SharedDocs/Downloads/DE/Merkblaetter/ust_idnr_aufbau.html; Algorithmus ZMDV Anl. 3 (aufgehoben, weiter gültiges Verfahren) ✅ | fehler |
| Ausländische USt-IdNr.: ISO-Präfix (EL für GR) + Länderformat | BR-CO-9 ✅, BZSt-Merkblatt | pruefen |
| Existenz der USt-IdNr. (VIES/eVatR) | ⚠️ Online-Abfrage, Datenschutz/Netz beachten | optional, nicht im Standardlauf |
| IBAN Mod-97 (ISO 13616) | BR-DE-19 (nur Format) | fehler |
| Rechnungsdatum nicht in der Zukunft (> heute + 1) | Empfehlung | pruefen |
| BT-9 ≥ BT-2; Leistungsdatum nicht weit nach dem Rechnungsdatum | Empfehlung | pruefen |
| Leistungsdatum > 12 Monate vor dem Rechnungsdatum | Empfehlung | warnung |
| Menge ≠ 0; Preis 0 nur mit Hinweis | Empfehlung | pruefen |
| Negative Menge bei 380 (Gutschriftposition) | Empfehlung | pruefen |
| Steuersatz in DE ∈ {19, 7, 0}, sonst pruefen | Empfehlung (Satz laut § 12 UStG ⚠️ nicht separat zitiert) | pruefen |
| Käuferland ≠ DE und Kategorie S mit DE-Satz | Empfehlung | pruefen |
| Käufer mit ausländischer USt-IdNr., aber Kategorie S | Empfehlung (möglicher RC/i.g.-Fall) | pruefen |
| PLZ DE = 5 Ziffern | Empfehlung | fehler |
| Einheiten/Länder/Währung gegen die Codelisten der KoSIT-Konfiguration (offline vorhanden) | BR-CL-* ✅ | fehler |
| Dubletten-Prüfung BT-1 gegen `protokoll.tsv` (alle früheren Läufe) | § 14 Abs. 4 Nr. 4 „einmalig“ ✅ + Empfehlung | fehler |
| Lücken/Sprünge im Nummernkreis | Empfehlung (Lücken sind nicht per se verboten ⚠️) | warnung |
| E-Mail-Format BT-43/BT-58/BT-34/BT-49 | BR-DE-28 (Warnung) | pruefen |
| Telefon mind. 3 Ziffern | BR-DE-27 (Warnung) | pruefen |
| Leitweg-ID: Format `Grob(2–12 Ziffern)[-Fein(≤30 alnum)]-PP`, Länge 5–46, Prüfziffer ISO 7064 Mod 97-10 | ✅ Leitweg-ID-Formatspezifikation v2.0.2, Kap. 2.3/2.4: https://leitweg-id.de/wp-content/uploads/2021/08/Leitweg-ID-Formatspezifikation-v2-0-2.pdf | fehler (bei XR an Behörde) |
| Kunde als öffentlicher Auftraggeber markiert → Leitweg-ID Pflicht, kein Fallback auf die Kundennummer | Empfehlung (BR-DE-15 verlangt nur irgendein BT-10) | fehler |
| Bruttobetrag ≤ 250 € → Hinweis Kleinbetrag | § 33 UStDV ✅ | info |
| Höchstens 2 Nachkommastellen bei Beträgen | BR-DEC ✅ | fehler (vorher runden) |
| Leerzeichen/Steuerzeichen in IDs, leere XML-Elemente | PEPPOL-R008 ✅ | fehler |
| Validator (KoSIT bzw. Mustang) im Standardlauf, wenn Java vorhanden | Empfehlung | fehler bei fatal |

---

## 5. Empfohlene harte Prüfungen (Kurzfassung)

Reaktion „fehler“, die Rechnung läuft nicht weiter:
1. Käufer: Name + Straße + PLZ + Ort + Land (Land nie still auf DE setzen). Bei Straße eventuell „pruefen“ (Postfach).
2. Verkäufer: Name + vollständige Anschrift + (USt-IdNr. oder Steuernummer). Nur Steuernummer → BT-30 (Register) Pflicht wegen BR-CO-26.
3. Positionen: Menge und Preis tatsächlich vorhanden (kein stilles 0), Preis ≥ 0, Bezeichnung, Einheit gültig.
4. Steuer: Kategorie und Satz konsistent. Z ohne Grund. E/AE/K/G/O mit Grund. AE mit Käufer-USt-IdNr. K mit beiden USt-IdNrn., Leistungsdatum und Lieferland.
5. Leistungsdatum oder Leistungszeitraum: mindestens „pruefen“ statt „warnung“.
6. Zahlung: IBAN vorhanden + Mod-97 bei Zahlart 58. Fälligkeit oder Zahlungsbedingungen vorhanden.
7. Rechnungsnummer einmalig über alle Läufe (`protokoll.tsv`).
8. Nur XRechnung: BT-10 (Leitweg-ID bei Behörden, mit Prüfziffer), BT-34, BT-49, Verkäuferkontakt, BG-16.

---

## 6. Quellen
- UStG § 14: https://www.gesetze-im-internet.de/ustg_1980/__14.html ✅
- UStG § 14a: https://www.gesetze-im-internet.de/ustg_1980/__14a.html ✅
- UStG § 19: https://www.gesetze-im-internet.de/ustg_1980/__19.html ✅
- UStDV § 31: https://www.gesetze-im-internet.de/ustdv_1980/__31.html ✅
- UStDV § 33: https://www.gesetze-im-internet.de/ustdv_1980/__33.html ✅
- UStDV § 34a: https://www.gesetze-im-internet.de/ustdv_1980/__34a.html ✅
- BMF-Schreiben vom 15.10.2025 (E-Rechnung), Rn. 35 ✅
- EN 16931 Validierungsartefakte: https://github.com/ConnectingEurope/eInvoicing-EN16931 ✅. BR-CO-25: Issue #541 ⚠️
- XRechnung-Schematron: https://github.com/itplr-kosit/xrechnung-schematron ✅
- KoSIT-Konfiguration: https://github.com/itplr-kosit/validator-configuration-xrechnung ✅
- FeRD ZUGFeRD-FAQ: https://www.ferd-net.de/standards/zugferd-faq ✅
- Mustang Issue #236 (BT-10 in ZUGFeRD optional): https://github.com/ZUGFeRD/mustangproject/issues/236 ✅
- BZSt Aufbau der USt-IdNr.: https://www.bzst.de/SharedDocs/Downloads/DE/Merkblaetter/ust_idnr_aufbau.html ✅
- Leitweg-ID-Formatspezifikation v2.0.2: https://leitweg-id.de/wp-content/uploads/2021/08/Leitweg-ID-Formatspezifikation-v2-0-2.pdf ✅
