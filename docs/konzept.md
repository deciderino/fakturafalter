# Fakturafalter (E-Rechnungs-Konverter) – Recherche & Konzept

> **Entscheidungen Phase 2a (31.10.2026):** Name „Fakturafalter“ (Paket `fakturafalter`), Lizenz **Apache-2.0**
> (LICENSE + NOTICE), freie Open Source ohne Gewähr/Support, Oberfläche **PySide6** (LGPL-3.0), Sprachen DE + EN,
> komplett offline ohne Telemetrie, kein Dienst-Modus in v1 („folgt später“), Input v1: PDF + CSV,
> Prüfmodul (Java) erst ganz zum Schluss als optionaler Download. Ältere GPL/PyQt6-Aussagen unten sind überholt.

Stand: 31.10.2026 (Abschnitt 3b Input ergänzt) · Status: **nur Konzept, nichts gebaut** · Arbeitstitel: „ERechnung-Wandler“

> **Stand 1.0.0-rc1 (27.11.2026):** Dieses Dokument ist die frühe Recherche.
> Der **Kundenstamm** ist in der App entfallen. Käuferangaben kommen aus der Quelle
> (CSV, XML oder Rechnungsdruck). Eine zusätzliche XRechnung (CII) entsteht über die
> einfache Liste in den Einstellungen. Die Skizzen unten beschreiben den alten Entwurf.


Legende: ✅ geprüft (Quelle am 31.10.2026 abgerufen) · ⚠️ unsicher / nur Sekundärquelle / bitte nachprüfen

---

## 0. Gibt es das schon? (Marktcheck)

| Tool | Was es kann | Lizenz/Preis | Lücke ggü. unserem Ziel |
|---|---|---|---|
| **e-invoice-eu** – https://github.com/gflohr/e-invoice-eu | JSON oder Calc/Excel → XRechnung CII/UBL, ZUGFeRD alle Profile; CLI, REST, JS-Lib; nutzt LibreOffice für Tabellen→PDF | Open Source (⚠️ Lizenz im Repo prüfen, vermutlich WTFPL) | Node.js-Runtime, kein Hotfolder, keine Desktop-UI, kein Dienst, kein docx als Sichtteil |
| **csv2zugferd** – https://github.com/rillsoft/csv2zugferd · https://zugferd-tools.de/ | CSV + vorhandene PDF + YAML-Mapping → ZUGFeRD-PDF/A-3 | Apache-2.0, .NET-CLI | **kein XRechnung-XML**, kein Hotfolder, keine UI, PDF muss schon da sein, Basis ZUGFeRD-csharp (Wartung endet 30.11.2026, s.u.) |
| **Mustang CLI** – https://github.com/ZUGFeRD/mustangproject | Validieren, PDF+XML kombinieren, Visualisierung | Apache-2.0, Java | reine Kommandozeile, kein Hotfolder, keine UI |
| **Rechnungsfuchs** – https://github.com/oskarwalluga-cmyk/rechnungsfuchs | Rechnungseditor, XRechnung-UBL, ZUGFeRD (Pro) | Open Core | Editor zum Tippen, **keine** Massen-/Ordnerverarbeitung |
| **W-Pferd** – https://x-pferd.de/w-pferd/ | E-Rechnung aus mitgelieferter Word-Vorlage | ⚠️ ca. 85 € netto/Rechner (lt. Suchergebnis) | nur eigene Vorlage, kein Hotfolder |
| **XRechnung PRO Konverter** – https://xrechnung.pro/xrechnung-konverter-tool/ | Hotfolder, Windows-Dienst | ⚠️ kommerziell, volumenabhängig, lt. Suchergebnis Internet nötig | Cloud-Abhängigkeit, Windows-only |
| **PDF2PDFA-FM** – https://www.pdfa.at/ | PDF→PDF/A/ZUGFeRD, Ordnerüberwachung, Windows-Dienst | kommerziell | erwartet fertiges XML bzw. PDF; Windows-only |

**Nische:** Es gibt kein Tool, das *lokal, offline, portabel, Windows + Linux* einen **Hotfolder mit docx/txt + CSV/JSON** paart, daraus **XRechnung (CII/UBL) und ZUGFeRD** erzeugt, **gegen KoSIT/CEN-Schematron + veraPDF validiert** und sowohl als **Tray-App als auch Dienst** läuft – mit einfacher UI. Bausteine existieren (Mustang, drafthorse, factur-x), die „Klebe-Schicht“ für Büro-Anwender fehlt.

---

## 1. Rechtsstand & Standards (verifiziert)

### 1.1 E-Rechnungspflicht (§ 14 UStG, Wachstumschancengesetz)
- ✅ Seit **1.1.2025** gilt bei inländischen B2B-Umsätzen grundsätzlich die E-Rechnung (strukturiertes Format nach EN 16931, das eine elektronische Verarbeitung ermöglicht); reines PDF = „sonstige Rechnung“. **Empfang** müssen alle Unternehmen seit 1.1.2025 können. – BMF-FAQ (Stand März 2026): https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html
- ✅ Übergangsregeln, **§ 27 Abs. 38 UStG** (Wortlaut abgerufen): https://www.gesetze-im-internet.de/ustg_1980/__27.html
  - **2025 + 2026:** alle dürfen noch sonstige Rechnungen ausstellen (Papier immer; anderes elektronisches Format nur mit Zustimmung des Empfängers). **Läuft am 31.12.2026 aus – also in 2 Monaten.**
  - **2027:** nur noch Unternehmen mit **Vorjahres-Gesamtumsatz (2026) ≤ 800.000 €**; außerdem EDI-Verfahren (mit Zustimmung) bis 31.12.2027.
  - **ab 1.1.2028:** E-Rechnungspflicht für alle inländischen B2B-Umsätze.
  - Dauerhaft ausgenommen: Kleinbetragsrechnungen ≤ 250 € (§ 33 UStDV), Fahrausweise (§ 34 UStDV), Kleinunternehmer (§ 19 UStG) als Aussteller; steuerfreie Umsätze nach § 4 Nr. 8–29 UStG. (Quelle u.a. Haufe-Zusammenfassung, ⚠️ Sekundärquelle: https://www.haufe.de/steuern/finanzverwaltung/bmf-ergaenzende-regelungen-zur-e-rechnung_164_700638.html)
- ✅ **BMF-Schreiben:**
  1. 15.10.2024, BStBl 2024 I S. 1320 (Grundsatzschreiben).
  2. ✅ 15.10.2025, III C 2 – S 7287-a/00019/007/243, BStBl 2025 I S. 1806: https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Umsatzsteuer/Umsatzsteuer-Anwendungserlass/2025-10-15-einfuehrung-obligatorische-e-rechnung.html – Kernpunkte: **alle Pflichtangaben nach §§ 14, 14a UStG müssen im strukturierten Teil stehen** (Rn. 35); Verweis auf PDF-Anlage oder externen Link genügt nicht; Unterscheidung Format- vs. Geschäftsregelfehler; Validierung empfohlen.
  3. ⚠️ **15.10.2026, III C 5 – S 7287-a/00019/021/017** („Ergänzende Regelungen“: Anzahlungs-/Abschlags-/Schlussrechnungen, Rabatte, Bruttopreise, Berichtigung, Geschäftsregelfehler; Nichtbeanstandung für bis 31.12.2026 nach alten Vorgaben ausgestellte E-Rechnungen). Nur über Sekundärquellen gefunden (BGA: https://bga.de/bga-update/bga-update-231026/drittes-bmf-schreiben-zur-e-rechnung-veroeffentlicht/ , NWB: https://datenbank.nwb.de/Dokument/1103671/). **bundesfinanzministerium.de blockiert automatisierte Abrufe (Bot-Check) – Originaltext bitte manuell prüfen.**
- ⚠️ Laut BGA hat das BMF am 16.10.2026 eine Verschiebung der 800.000-€-Stufe abgelehnt. Meldesystem (ViDA) laut IHK/Haufe für 1.7.2030 geplant, gesetzlich noch nicht umgesetzt.

### 1.2 EN 16931
- ✅ **EN 16931-1:2026** von CEN am 13.03.2026 angenommen, Text seit 18.03.2026 verfügbar; ersetzt EN 16931-1:2017+A1:2019, **nicht rückwärtskompatibel**; die 2017er-Fassung bleibt in der Migrationsphase konform. EU-Kommission: https://ec.europa.eu/newsroom/digital/items/930407/en · https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108661/European+Standard+and+Specifications
- ⚠️ Deutscher Migrationszeitplan (wann 2026er-Syntax in XRechnung/ZUGFeRD Pflicht wird) noch offen → **Konsequenz fürs Design: Format-Versionen austauschbar halten.**

### 1.3 XRechnung
- ✅ In Kraft: **XRechnung 3.0** (seit 01.02.2024), aktuelles technisches Bundle **3.0.2 „Summer 2026 Bugfix“ vom 31.08.2026** (Validator 1.6.3, CEN-Artefakte 1.3.16), Visualisierungs-Bugfix 13.10.2026. **Gilt mindestens bis 31.07.2027.** https://xeinkauf.de/xrechnung/versionen-und-bundles/ · https://xeinkauf.de/aktuelles/xrechnung/xrechnung-bugfix-summer-2026/
- ✅ **XRechnung 4.0** (Basis EN 16931:2026) nur als **Vorversion vom 15.09.2026** – nicht produktiv nutzen; final voraussichtlich Frühjahr 2027. https://xeinkauf.de/app/uploads/2026/09/XRechnung-4.0.0-Vorversion-2026-09-15.pdf
- Syntaxen: UBL 2.1 (Invoice/CreditNote) und UN/CEFACT CII. Spezifikationskennung BT-24: `urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`.
- KoSIT-Validator: Validator 1.6.x braucht Java ≥ 11 (Java-8-Support mit 1.6.0 entfernt); Konfiguration: https://github.com/itplr-kosit/validator-configuration-xrechnung

### 1.4 ZUGFeRD / Factur-X
- ✅ Aktuell: **ZUGFeRD 2.5.2 / Factur-X 1.09.2**, veröffentlicht 04.08.2026, gültig seit 01.09.2026. https://www.ferd-net.de/aktuelles-veranstaltungen/aktuelles/news/zugferd-252-veroeffentlicht
  - Vorgänger 2.4/1.08 (gültig ab 15.01.2026) – https://www.ferd-net.de/publikationen-produkte/publikationen/detailseite/zugferd-24-deutsch
  - ⚠️ Nächstes Release (Bruttorechnungen, weitere EN 16931:2026-Funktionen) „voraussichtlich Herbst 2026“ – zum 31.10.2026 kein Release gefunden.
- Profile: MINIMUM, BASIC WL, BASIC, EN 16931 (COMFORT), EXTENDED, XRECHNUNG.
  - **Als E-Rechnung nach § 14 UStG zählen:** BASIC, EN 16931, EXTENDED, XRECHNUNG.
  - **Nicht:** MINIMUM und BASIC WL (enthalten keine Positionsdaten → nicht alle Pflichtangaben strukturiert). Quelle: BMF-Schreiben 15.10.2024 (Abschnitt zu hybriden Formaten) ⚠️ genaue Randnummer nicht am Original geprüft (BMF-Seite blockiert); deckt sich mit Rn. 35 des Schreibens 2025 (alle Pflichtangaben strukturiert).
  - Empfehlung Tool: Default **EN 16931**, wählbar XRECHNUNG und EXTENDED; MINIMUM/BASIC WL gar nicht anbieten.
- ✅ **PDF/A-3**: Die XML wird in eine **PDF/A-3**-Datei eingebettet (Dateiname `factur-x.xml` bzw. bei Profil XRECHNUNG `xrechnung.xml`, AFRelationship, XMP-Erweiterungsschema `fx:`). FeRD: „In der hybriden Ausprägung werden … die strukturierten Rechnungsdaten in einer PDF/A-3 Datei eingebettet.“ Bei Abweichungen zwischen PDF und XML ist steuerlich die **XML maßgeblich** (BMF 2024, ⚠️ Rn. nicht geprüft).

---

## 2. Technologie-Optionen

### 2.1 Vergleich

| Option | Erzeugung | Validierung KoSIT/CEN | PDF/A-3 | Self-contained Win + Linux | Lizenz | Bewertung |
|---|---|---|---|---|---|---|
| **Java: Mustangproject** 2.27.0 (09.10.2026) | CII alle ZF-Profile + XRechnung CII; UBL nur Import (CII→UBL via phax/en16931-cii2ubl) | ✅ integriert: XRechnung-Schematron, CEN 1.3.17, **veraPDF** | ✅ PDF/A-1→A-3, eigene PDF-Erzeugung via FOP | jlink/jpackage, ~60–90 MB | Apache-2.0 (Deps: MPL-2.0 veraPDF/Saxon-HE, EUPL-1.2 CEN-Artefakte) | fachlich stärkste Engine |
| **Java: KoSIT-Validator** 1.6.3 | – | ✅ Referenz (offizielle Prüfung) | ❌ keine PDF-Prüfung | jlink | Apache-2.0 | Referenz, aber nur XML |
| **.NET: ZUGFeRD-csharp** 18.0.1 | CII + UBL, XRechnung | ❌ (nur extern) | teilweise | .NET self-contained single-file | Apache-2.0 | ⚠️ **letztes OSS-Release 09.10.2026, Wartung endet 30.11.2026**, Nachfolger FactoorSharp kommerziell → **nicht empfehlen** |
| **Python: drafthorse** 2025.2.0 | CII (ZF-Profile inkl. XRechnung-Guideline), Attach an PDF | ❌ (empfiehlt selbst Mustang) | XML-Einbettung + XMP, keine A-3-Konvertierung | PyInstaller | Apache-2.0 (pdf.py: BSD) | gute, schlanke Erzeugung |
| **Python: factur-x** (Akretion) 7.9 | nur Einbettung/Extraktion, XSD-Check | nur XSD | Einbettung + XMP, erwartet PDF/A-Eingang | PyInstaller | BSD-3 | Einbettungsschicht |
| **Python: saxonche** (Saxon-HE C) | – | XSLT-Schematron der KoSIT ohne JVM möglich ⚠️ (Machbarkeit testen) | ❌ | Wheel | MPL-2.0 | Option „ohne Java“, aber ohne veraPDF |

### 2.2 docx/txt → PDF/A-3 (Sichtkomponente für ZUGFeRD)

| Option | Qualität docx | PDF/A | Bundle | Lizenz | Anmerkung |
|---|---|---|---|---|---|
| **LibreOffice headless** (`soffice --headless --convert-to pdf:writer_pdf_Export:{"SelectPdfVersion":…}`) | sehr gut | PDF/A-1b/2b/3b direkt ⚠️ Filteroption je Version testen | **groß**: ~300–400 MB; Windows: LibreOffice Portable (PortableApps), Linux: offizielle LO-AppImage | MPL-2.0 | beste Wahl; eigenes `-env:UserInstallation`-Profil, Prozess-Queue (nicht parallel) |
| MS Word per COM (docx2pdf) | perfekt | nur PDF/A-1b/2b (⚠️), Nachkonvertierung nötig | 0 MB, aber Word nötig | proprietär | nur Windows, nicht im Dienst (Session 0) – nur als „wenn vorhanden“-Option |
| python-docx + fpdf2/reportlab + pikepdf | schwach (Layout geht verloren) | selbst bauen (Fonts einbetten, OutputIntent, XMP) | klein | MIT/LGPL/BSD/MPL | **gut für .txt**, schlecht für docx |
| docx4j + Apache FOP (Java) | mittel | PDF/A via FOP ⚠️ A-3-Support prüfen | im JRE-Bundle | Apache-2.0 | Fallback ohne LO |
| Ghostscript (PDF → PDF/A) | – | PDF/A-2b/3b | ~50 MB | **AGPL-3.0** | nur zur Nachkonvertierung; AGPL mit GPL-3 kompatibel, aber Pflichten beachten |
| **Mustang-Visualisierung** (XML → PDF via FOP) | – (erzeugt PDF aus den Daten) | PDF/A-3 | im JRE-Bundle | Apache-2.0 | Option „Sichtteil aus Daten erzeugen“ → PDF und XML stimmen garantiert überein |

Hinweis: Für **XRechnung (reines XML) wird kein PDF gebraucht**. Das docx/txt kann optional als PDF-Anlage (BG-24, Base64) mitgegeben werden.

### 2.3 Empfehlung

**Python 3.13 + PyQt6 als App/UI/Worker, plus gebündelte Mini-JRE mit Mustang als „Prüf- und PDF/A-Engine“, plus optional gebündeltes LibreOffice für docx.**

Begründung:
1. **Bewährte Build-Kette wiederverwenden:** Eine bestehende, erprobte Build-Kette eines anderen Projekts baut bereits PyInstaller-onedir → AppImage (`linux/build-appimage.sh` + `AppRun` + `.desktop`) und Windows-zip per Wine + Windows-Python 3.13 (`windows/build-windows.sh` → `build.py`; onedir statt onefile wegen Startzeit/AV-Fehlalarmen, Lizenzordner). Wine-Prefix mit `C:\Python313` liegt lokal auf der Build-Maschine. Zusätzliche Bundles (JRE, LO) analog zu einem gebündelten Kommandozeilenwerkzeug (Pfad + SHA256 gepinnt, `licenses/`-Ordner).
2. **Erzeugung in Python:** CII via **drafthorse** (Apache-2.0), UBL über **eigene lxml-Vorlage** (EN 16931-Mapping, überschaubar) oder CII→UBL via Mustang/phax; Einbettung via **factur-x/drafthorse** (BSD/Apache).
3. **Validierung in Java (Mustang-Validator)**: einziger Baustein, der XRechnung-Schematron, CEN-Schematron **und veraPDF (PDF/A-3)** in einem Aufruf prüft; Apache-2.0. JRE per `jlink` (Temurin 21) für win-x64 und linux-x64 ~45–60 MB. Optional zusätzlich der **offizielle KoSIT-Validator** mit `validator-configuration-xrechnung` für XRechnung-XML (Referenzprüfung, wichtig für B2G). Prüfartefakte als austauschbares „Regelpaket“ (Update ohne neue App-Version → XRechnung 4.0/EN 16931:2026 vorbereitet).
4. **Lizenz:** ~~PyQt6/GPL-3.0~~ → **entschieden: Apache-2.0 mit PySide6 (LGPL-3.0, dynamisch gelinkt)**, siehe „Entscheidungen Phase 2a“.
5. Alternativen: **Reines Java** (Mustang + JavaFX + jpackage) wäre technisch „aus einem Guss“ (kein Sprachmix), aber neue Build-Kette und weniger Wiederverwendung. **.NET** scheidet wegen Wartungsende von ZUGFeRD-csharp aus.

### 2.4 Hintergrund / Dienst
- Eine Binary, drei Modi: `erechnung` (UI + Tray, Worker im Prozess), `erechnung --headless` (nur Worker, für Dienst), `erechnung --einmal` (Ordner einmal abarbeiten, für Aufgabenplanung/cron).
- **Windows-Dienst:** WinSW (MIT, einzelne exe + XML) mitliefern; Einrichtung per Knopf in den Einstellungen (UAC-Bestätigung = einziger Popup). Hinweis: Dienst läuft in Session 0 → kein Tray; Netzlaufwerke brauchen Dienstkonto.
- **Linux:** systemd **User-Unit** (`~/.config/systemd/user/erechnung.service`, kein root) mit Pfad zum AppImage; optional `loginctl enable-linger`.
- **Autostart (Tray):** HKCU\…\Run bzw. `~/.config/autostart/*.desktop`.
- **Kein Doppelbetrieb:** Lock-Datei im Datenordner; läuft der Dienst, zeigt die UI nur Status/Protokoll (liest `status.json` + JSONL-Protokoll) und bearbeitet Einstellungen; Worker lädt Konfig bei Änderung neu.
- Ordnerüberwachung: `watchdog` (Apache-2.0) + Polling-Fallback für Netzlaufwerke; Datei gilt als „fertig“, wenn Größe/mtime 2 s stabil.
- Portabel: Konfig/Protokoll in `daten/` neben der exe, falls beschreibbar, sonst `%APPDATA%\ERechnung` bzw. `~/.config/erechnung`.

---

## 3. Datenmodell & Matching

### 3.1 Grundsatz
Das docx/txt ist **nur Sichtkomponente**. Alle steuerlich relevanten Angaben kommen aus **CSV/JSON + Absender-Stammdaten** (BMF 2025 Rn. 35). Summen und USt-Aufschlüsselung **berechnet das Tool** selbst; mitgelieferte Summen werden nur gegengeprüft (Abweichung > 0,01 € = Fehler). Warnung in der UI: Inhalt von docx und Daten wird nicht automatisch verglichen → Option „Sichtteil aus Daten erzeugen“.

### 3.2 Herkunft der Felder
- **Stammdaten (Einstellungen, einmalig):** Verkäufer BG-4/BG-5/BG-6, Steuer-IDs, Bank, Standard-Zahlungsziel, elektronische Adresse.
- **Je Rechnung (JSON/CSV):** Kopf, Käufer, Leistungsdatum, Positionen, ggf. Abweichungen.

### 3.3 Pflichtfelder (EN 16931 + XRechnung 3.0 + § 14 Abs. 4 UStG)

| Gruppe | BT | Feld (JSON-Schlüssel) | Pflicht | Quelle |
|---|---|---|---|---|
| Kopf | BT-1 | `rechnungsnummer` | ja | Daten |
| | BT-2 | `rechnungsdatum` (JJJJ-MM-TT) | ja | Daten |
| | BT-3 | `rechnungsart` (380 Rechnung, 381 Gutschrift/Korrektur, 384 Korrektur, 326 Teilrechnung, 875/876/877 Bau ⚠️) | ja, Default 380 | Daten |
| | BT-5 | `waehrung` | ja, Default EUR | Daten |
| | BT-9 / BT-20 | `faellig_am` / `zahlungsbedingungen` | eins davon (BR-CO-25) | Daten/Stamm |
| | BT-10 | `kaeuferreferenz` (B2G: **Leitweg-ID**) | XRechnung: ja (BR-DE-15) | Daten |
| | BT-23 | Geschäftsprozess | XRechnung: ja | Tool (fix) |
| | BT-24 | Spezifikationskennung | ja | Tool (aus Profil) |
| | BT-13 | `bestellnummer` | nein | Daten |
| | BT-25/26 | `bezug_rechnung` (+Datum) | bei Korrektur | Daten |
| Verkäufer | BT-27 | Name | ja | Stamm |
| | BT-35/37/38/40 | Straße, Ort, PLZ, Land | ja (XR: Ort+PLZ BR-DE-3/4) | Stamm |
| | BT-31 / BT-32 | USt-IdNr. / Steuernummer | eins davon (§14) | Stamm |
| | BT-34 | elektronische Adresse | XRechnung 3.0: ja | Stamm |
| | BT-41/42/43 | Kontakt Name/Tel/E-Mail | XRechnung: ja (BR-DE-2) | Stamm |
| Käufer | BT-44 | `kaeufer.name` | ja | Daten |
| | BT-50/52/53/55 | `kaeufer.strasse/ort/plz/land` | ja | Daten |
| | BT-48 | `kaeufer.ust_id` | bei Reverse Charge/igL | Daten |
| | BT-49 | `kaeufer.email` (elektr. Adresse) | XRechnung 3.0: ja | Daten |
| Leistung | BT-72 oder BT-73/74 | `leistungsdatum` oder `zeitraum_von/bis` | ja (§14 Abs.4 Nr.6) | Daten |
| Zahlung | BT-81 | `zahlungsart` (58 = SEPA-Überweisung, 59 Lastschrift) | XR: ja | Stamm/Daten |
| | BT-84 / BT-86 | IBAN / BIC | bei 58 | Stamm |
| Positionen BG-25 (≥1) | BT-126 | `pos` | ja | Daten (auto) |
| | BT-153 | `bezeichnung` | ja | Daten |
| | BT-129 / BT-130 | `menge` / `einheit` (UN/ECE Rec 20: C62 Stück, HUR Stunde, DAY, KGM …) | ja | Daten |
| | BT-146 | `einzelpreis_netto` | ja | Daten |
| | BT-131 | Positionsnetto | ja | **Tool** |
| | BT-151 / BT-152 | `ust_kategorie` (S, Z, E, AE, K, G, O) / `ust_satz` | ja | Daten (Default S/19) |
| Steuer BG-23 | BT-116–119 | Aufschlüsselung je Satz | ja | **Tool** |
| | BT-120/121 | `befreiungsgrund` (Text/Code) | bei E, AE, K, G, O | Daten/Stamm (z.B. §19-Hinweis, „Steuerschuldnerschaft des Leistungsempfängers“) |
| Summen BG-22 | BT-106/109/110/112/115 | Summen | ja | **Tool** (Gegencheck optional) |
| Anlagen BG-24 | BT-125 | Original-PDF als Anlage | nein | Tool (Option) |

Optional später: Nachlässe/Zuschläge (BG-20/21/27/28), Lieferanschrift (BG-15), Skonto (in BT-20 nach XRechnung-Syntax `#SKONTO#`).

### 3.4 Formate
**JSON (empfohlen, eine Datei je Rechnung):**
```json
{
  "rechnungsnummer": "RE-2026-0042",
  "rechnungsdatum": "2026-11-03",
  "leistungsdatum": "2026-10-31",
  "faellig_am": "2026-11-17",
  "kaeuferreferenz": "04011000-12345-03",
  "kaeufer": { "name": "Beispiel GmbH", "strasse": "Musterweg 1", "plz": "12345",
               "ort": "Musterstadt", "land": "DE", "email": "rechnung@beispiel.example",
               "ust_id": "DE123456789" },
  "positionen": [
    { "bezeichnung": "Beratung Oktober", "menge": 8, "einheit": "HUR",
      "einzelpreis_netto": 95.00, "ust_kategorie": "S", "ust_satz": 19 }
  ],
  "quelldatei": "RE-2026-0042.docx"
}
```
**CSV:** Variante A „eine Zeile je Position“ (Kopf-/Käuferfelder werden je Zeile wiederholt, gruppiert über `rechnungsnummer`), UTF-8, `;`-getrennt, Dezimalkomma oder -punkt einstellbar. Spaltenköpfe akzeptieren JSON-Schlüssel **oder** BT-Nummern (`BT-1`, `BT-153` …); Mapping-Datei für fremde Exporte (DATEV/ERP) als Ausbaustufe. Eine CSV darf mehrere Rechnungen enthalten.
Validierung des Eingangs per JSON-Schema (mitgeliefert) → verständliche deutsche Fehlermeldungen *vor* der Schematron-Prüfung.

### 3.5 Matching docx/txt ↔ Daten
1. **Gleicher Dateiname (Stem):** `RE-2026-0042.docx` + `RE-2026-0042.json` → Paar. (Standard)
2. **Feld `quelldatei`** im JSON/CSV verweist auf das Dokument.
3. **Rechnungsnummer im Dateinamen:** Stem des Dokuments == BT-1 einer Zeile in einer Sammel-CSV.
4. Wartefrist (Default 60 s): Teil ohne Partner → Status „wartet“; danach „Partner fehlt“ (Fehlerordner). Für XRechnung ohne Anlage ist **nur die Datendatei** nötig.
5. Doppelte BT-1 (bereits erzeugt) → Fehler, nichts überschreiben.

### 3.6 Ablauf & Ordner
`Eingang/` → Paar stabil → JSON-Schema-Check → XML erzeugen → (ZUGFeRD: docx/txt → PDF/A-3 → XML einbetten) → Mustang-/KoSIT-Validierung → bei Erfolg `Ausgang/RE-2026-0042.xml|.pdf` + `Ausgang/berichte/…html`, Eingangsdateien nach `Eingang/erledigt/JJJJ-MM/`; bei Fehler nach `Eingang/fehler/` + `…fehler.txt`. Optional: Warnungen als Fehler behandeln.

---

## 3b. Input: CSV und Druck (PDF) – Folgekonzept 31.10.2026

> Entscheidung des Nutzers: Start mit **zwei Eingängen** – (1) **CSV-Export** kleiner ERP/WaWi, (2) **Druck auf einen virtuellen Drucker** → PDF mit Textebene (oder reiner Text), ausgelesen per **Zonen-Vorlage** je Layout. Schrittweise erweitern. Kein echter Beispiel-Input vorhanden → erfundene Beispiele unter `beispiele/`.
> Der docx/txt-Weg aus Abschnitt 2.2/3.5 bleibt als spätere Ausbaustufe.

### 3b.1 Architektur: Adapter → Modell → Stamm → Prüfung → Ausgabe

```
 CSV-Datei ──► CSV-Adapter (Profil) ──┐
                                       ├─► internes EN-16931-Modell ─► Nachschlagen ─► Prüfung ─┬─► Ausgabe (XRechnung/ZUGFeRD)
 Druckauftrag ─► Druckannahme ─► PDF/Text-Adapter (Vorlage) ┘   (je Feld: Wert,     Kundenstamm,   Regeln +   │
   (Port 9100 / Ordner)                                          Herkunft,          Stammdaten     Schematron └─► Prüfansicht (unsicher)
                                                                 Sicherheit)
```

- **Jedes Feld** im Modell ist ein Tripel `{wert, herkunft, sicherheit}`; Beispiel: `BT-1 = {"RE-2026-0101", "pdf:s1:anker 'Rechnungsnr.:'", 0.95}`, `BT-49 = {"rechnung@beispiel-handel.example", "kundenstamm:K-1001", 1.0}`.
- **Herkunftsarten:** `csv:<zeile>:<spalte>`, `pdf:<seite>:<anker|bereich>`, `text:<zeile>:<spalte>`, `kundenstamm:<nr>`, `stammdaten`, `fest:<profil>`, `berechnet`.
- **Sicherheit:** CSV-Spalte/Stamm = 1.0; PDF-Anker mit passendem Muster = 0.95; PDF-Bereich ohne Muster = 0.8; Mapping-Treffer über „unbekannt“-Regel = 0.5; fehlend = 0. Schwelle (Default 0.9) je Profil einstellbar.
- **In die Prüfansicht** (statt Ausgabe) geht eine Rechnung, wenn: ein Pflichtfeld unter Schwelle/fehlt, Kunde nicht im Stamm, unbekannte Einheit/Steuerschlüssel, mitgedruckte Summe ≠ berechnete Summe (> 0,01 €), Seitenfolge „Seite n von m“ lückenhaft, Vorlage nicht eindeutig erkannt, Schematron-Fehler. Korrekturen in der Prüfansicht werden mit Herkunft `manuell:<nutzer>:<zeit>` protokolliert; optional „als Regel merken“ (z. B. neues Einheiten-Mapping).
- Summen und Steuer **rechnet immer das Tool**; gedruckte/exportierte Summen sind nur Kontrollwerte.

### 3b.2 Virtueller Drucker – Optionen (verifiziert 31.10.2026)

**Wichtige Rahmenbedingung Windows:** Microsoft beendet die Pflege von Drittanbieter-Druckertreibern: ab 15.01.2026 keine neuen Treiber über Windows Update (Win 11/Server 2025), **ab 01.07.2026 bevorzugt Windows beim Hinzufügen den eingebauten IPP-Klassentreiber („Windows Ready Print“)**, ab 01.07.2027 nur noch Sicherheitsupdates für Drittanbieter-Treiber. Im optionalen **Windows protected print mode** werden Drucker mit Drittanbieter-Treibern sogar **deinstalliert**. ✅ https://learn.microsoft.com/en-us/windows-hardware/drivers/print/end-of-servicing-plan-for-third-party-printer-drivers-on-windows · https://learn.microsoft.com/en-us/windows/modern-print/windows-protected-print-mode/windows-protected-print-mode · https://techcommunity.microsoft.com/blog/windows-itpro-blog/introducing-windows-ready-print-and-modernized-driver-selection/4527563
→ **Konsequenz:** keinen eigenen Druckertreiber bauen/mitliefern; nur **Windows-eigene Treiber** + eigener **Port/Empfänger**.

| Option | OS | Speichert ohne Dialog | Textebene | Mitliefern/Einrichten | Lizenz / GPL-3-verträglich | Netzwerk | Bewertung |
|---|---|---|---|---|---|---|---|
| **Microsoft Print to PDF + TCP/IP-Port 127.0.0.1:9100 → eigene Druckannahme** | Win 10/11 | ja (Port statt `PORTPROMPT:`) | ja (Treiber erzeugt Vektor-PDF mit Text) | nichts mitzuliefern, Treiber ist eingebaut; `Add-PrinterPort`/`Add-Printer` brauchen **Admin** (einmal UAC) | Windows-Bestandteil | **ja**: andere Windows-PCs legen denselben Drucker mit Ziel `<unser-PC>:9100` an | **Empfehlung** ⚠️ Kombination Treiber+TCP-Port per Prototyp prüfen (dokumentiert ist nur Datei-Port) |
| Microsoft Print to PDF + **lokaler Datei-Port** (`Add-PrinterPort -Name "C:\…\druck.pdf"`) | Win | ja | ja | wie oben, Admin | Windows | nein | Fallback; **fester Dateiname** → jeder Auftrag überschreibt den vorigen, App muss sofort wegräumen ✅ https://stackoverflow.com/questions/69169267/how-to-skip-choosing-folder-in-microsoft-pdf-printer |
| **Generic / Text Only** + TCP/IP-Port | Win | ja | – (liefert reinen Text) | eingebaut ⚠️ in Win 11 noch vorhanden? Codepage (CP850/1252?) testen | Windows | ja | für alte WaWi mit Textdruck |
| **clawPDF** 0.9.x | Win | ja (Profil „Auto-Save“, Zielordner, eindeutige Namen) | ja, auch PDF/A-3b | eigener MSI-Installer (Admin), **nicht** in unser Paket einbetten; Ghostscript-basiert | **AGPL-3.0** (GPL-3 §13: kombinierbar; als separates Programm unkritisch) ✅ https://github.com/clawsoftware/clawPDF | ja (Netzwerkdrucker-Modus mit Dienstkonto) ✅ https://github.com/clawsoftware/clawPDF/wiki/Install-as-Network-Printer | gute **Alternative**, falls Port-Weg scheitert; aber Drittanbieter-Treiber (s. Rahmenbedingung) |
| PDFCreator | Win | ja (Automatic-Modus) | ja | eigener Installer | **Free nur privat**; geschäftlich kostenpflichtig ✅ https://support.pdfforge.org/pdfcreator-licensing | ja (Server-Edition) | **nicht empfehlen** |
| RedMon / eigener Port-Monitor (DLL) | Win | ja | je Treiber | Port-Monitor-DLL im Spooler, Admin, Signatur | RedMon GPL ⚠️ (Projekt alt, nicht für Win 11 geprüft) | – | **nicht empfehlen** (Spooler-DLL = Sicherheits-/Wartungsrisiko) |
| Eigener IPP-Drucker (unsere App als IPP-Everywhere-Server) + Windows IPP-Klassentreiber | Win | ja | ⚠️ Windows schickt meist **PWG-Raster (Bild)**, PDF nur wenn angeboten und gewählt → ohne Text wäre OCR nötig | kein Treiber; Drucker per IPP-URL hinzufügen | eigener Code (Basis z. B. ipp-server, BSD-2 ⚠️) https://github.com/h2g2bob/ipp-server | ja | **Zukunftsweg** (passt zu Windows Ready Print), erst nach Test |
| **CUPS-Warteschlange → `socket://127.0.0.1:9100` → eigene Druckannahme** | Linux | ja | ja (Linux-Programme drucken PDF) | `lpadmin` braucht root/Gruppe `lpadmin` (pkexec) | CUPS Apache-2.0 | ja: auch fremde Rechner/CUPS drucken auf `<host>:9100` | **Empfehlung Linux v1** ⚠️ Raw-Queues sind seit CUPS 2.2 „deprecated“, in CUPS 3 entfallen ✅ https://openprinting.github.io/cups/drivers.html |
| **Eigene App als IPP-Everywhere-Drucker** + `lpadmin -m everywhere -v ipp://localhost:8631/ipp/print` | Linux | ja | ja (wenn wir `application/pdf` anbieten, schickt CUPS PDF) | lpadmin wie oben | eigener Code; PAPPL (Apache-2.0) wäre C-Alternative ✅ https://github.com/michaelrsweet/pappl/ | ja | **Linux v2** (zukunftssicher für CUPS 3) |
| CUPS-PDF (3.0.3, 2026) | Linux | ja (`Out`-Verzeichnis in `/etc/cups/cups-pdf.conf`) | ja | Distributionspaket, root, Konfig systemweit | **GPL-2.0-or-later** ✅ https://www.cups-pdf.de/licensing.shtml | über CUPS-Freigabe | Fallback, wenn schon installiert; wir überwachen nur den `Out`-Ordner |
| Eigenes CUPS-Backend (Skript in `/usr/lib/cups/backend/`) | Linux | ja | ja | root, CUPS-Interna | – | ja | nicht nötig – Socket-Queue leistet dasselbe |

**Druckannahme (Teil unserer App, kein Treiber):**
- Lauscht auf **TCP 9100 (Raw/AppSocket)**, Port einstellbar (z. B. 9101, falls belegt); später optional **LPD 515** (Windows-Bordmittel „LPR-Port“; unter Linux < 1024 nur mit Rechten) und **IPP**.
- Je Verbindung = ein Druckauftrag → Datei `eingang/druck/JJJJMMTT-hhmmss-<quelle>.bin`, dann Inhalt erkennen: `%PDF` → PDF-Adapter; `@PJL`/`ESC%-12345X` → PJL-Hülle entfernen; `%!PS` → ⚠️ PostScript nur mit Ghostscript (AGPL) → zunächst „nicht unterstützt“ mit Hinweis „Treiber Microsoft Print to PDF wählen“; sonst Text (Kodierung erkennen) → Text-Adapter.
- Netzwerk: Standard **nur 127.0.0.1**; Schalter „auch aus dem Netz annehmen“ + erlaubte Absender-IPs; Firewall-Regel braucht Admin. Kein Auth bei Raw-9100 → nur im LAN, IP-Liste Pflicht.
- Im Dienst-Modus läuft die Druckannahme im Worker (Windows-Dienst / systemd-User-Unit), damit Druck auch ohne angemeldete Oberfläche funktioniert.

**Empfehlung:**
- **Windows:** Drucker „E-Rechnung“ = eingebauter Treiber **Microsoft Print to PDF** + **Standard-TCP/IP-Port 127.0.0.1:9100 (Raw)** → unsere Druckannahme. Einrichtung per Knopf (PowerShell `Add-PrinterPort -Name ERechnung9100 -PrinterHostAddress 127.0.0.1 -PortNumber 9100` + `Add-Printer -Name "E-Rechnung" -DriverName "Microsoft Print to PDF" -PortName ERechnung9100`, eine UAC-Bestätigung). Für Text-WaWis zusätzlich „E-Rechnung (Text)“ mit **Generic / Text Only**. Fallback: Datei-Port; Alternative: clawPDF (separat installiert, Auto-Save in unseren Eingangsordner).
- **Linux:** CUPS-Warteschlange „E-Rechnung“ → `socket://127.0.0.1:9100` (v1), später IPP-Everywhere-Server (v2). Wo CUPS-PDF schon läuft: dessen `Out`-Ordner als Eingangsordner.
- **Netzwerk:** ERP-Rechner richtet Drucker auf `<unser-PC>:9100` ein – unter Windows mit Treiber Microsoft Print to PDF (liefert PDF), unter Linux CUPS-Queue `socket://<host>:9100`; Alt-Systeme mit Textdruck → Text-Adapter.

### 3b.3 PDF/Text auslesen

| Bibliothek | Lizenz | Stärken | Schwächen | Rolle |
|---|---|---|---|---|
| **pdfplumber** 0.11 | MIT ✅ https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt | Wörter mit Koordinaten (`extract_words`), Bereiche (`crop`), Tabellenhilfen, visuelles Debugging | langsamer als MuPDF | **Empfehlung: Auslesen** |
| pdfminer.six | MIT | Basis von pdfplumber, Layout-Analyse | Low-Level | indirekt |
| **pypdfium2** | Apache-2.0 / BSD-3 ✅ https://github.com/pypdfium2-team/pypdfium2/ | schnelles Rendern als Bild (Vorschau im Assistenten), Text | Tabellenlogik fehlt | **Empfehlung: Vorschau** (alternativ QtPdf aus PyQt6 ⚠️ prüfen) |
| PyMuPDF | **AGPL-3.0** oder kommerziell ✅ https://pymupdf.io/licensing | sehr schnell, alles in einem | AGPL zieht Pflichten nach sich, Lizenzwechsel später schwer | **vermeiden** |
| invoice2data | MIT ✅ https://github.com/invoice-x/invoice2data | YAML-Vorlagen mit Regex je Lieferant | arbeitet auf Fließtext (Regex), keine Koordinaten/Spalten | nur als **Ideengeber** für Vorlagen-Erkennung (`keywords`) |

**Vorgehen (am Beispiel `beispiele/druckauftrag-wawi.pdf` + `vorlage-wawi-druck.yaml` als Machbarkeitsprobe in /tmp erfolgreich durchgespielt: 3 Seiten → 2 Rechnungen, alle Kopf- und Positionsfelder korrekt):**
1. **Vorlage wählen:** alle Vorlagen prüfen `erkennung.enthaelt_text`; genau eine muss passen, sonst Prüfansicht.
2. **Wörter + Koordinaten** je Seite (pdfplumber), zu Zeilen gruppieren (gleiche `top` ± 3 pt).
3. **Anker-Felder:** Anker-Text suchen (auch mehrwortig, z. B. „Ihre Bestellung:“), Wert = Wörter **rechts daneben** in derselben Zeile (max. Abstand) oder **darunter**; Wert gegen `muster` (Regex) prüfen → Sicherheit 0.95, sonst 0.5. Anker sind robuster als feste Koordinaten, weil alte WaWis Zeilen verschieben (z. B. zusätzliche Zeile „Ihre Bestellung“).
4. **Bereichs-Felder:** fester Rahmen (x0/top/x1/bottom) für Dinge ohne Anker (Anschriftenfenster) → nur zur Gegenprüfung mit Kundenstamm.
5. **Positionstabelle:** Start nach Kopfzeile (`^Pos\s+Art\.-Nr\.`), Ende vor „Nettobetrag“ bzw. vor Fußzeilenbereich; Trennlinien/„Übertrag“ ignorieren. **Textspalten über linke Kante, Zahlenspalten über rechte Kante** (rechtsbündig) – so stören zu lange Bezeichnungen nicht (im Beispiel absichtlich eingebaut). Zeile ohne Pos.-Nr. = Fortsetzung der Bezeichnung.
6. **Mehrseitig:** Tabelle über Seiten fortsetzen; BT-1 muss auf allen Seiten gleich sein; „Seite n von m“ lückenlos.
7. **Mehrere Rechnungen in einem Auftrag trennen:** neue Rechnung, wenn BT-1 wechselt **oder** „Seite 1 von …“ erscheint; Plausibilität: Summenblock nur auf letzter Seite.
8. **Text-Druck** (Generic/Text Only): gleiche Logik auf Zeichenraster (Zeile/Spalte statt pt), Seiten über Formfeed `\f`; Kodierung erkennen (UTF-8 → CP1252 → CP850).
9. **Kein OCR im Start.** Bild-PDFs (keine Textebene) → Prüfansicht „Keine Textebene – Druckertreiber prüfen“. OCR (Tesseract, Apache-2.0) später.

### 3b.4 CSV-Zuordnungsprofil (Kurzfassung, Details in `beispiele/profil-*.yaml|json`)

Profil = YAML oder JSON, gleiche Struktur:
- `datei`: `muster`, `kodierung` (`auto`: strikt UTF-8 versuchen [BOM → utf-8-sig] → sonst Windows-1252; CP850/ISO-8859-15 wählbar), `trennzeichen` (`auto` = csv.Sniffer über `; , TAB |`), `textbegrenzer`, `kopfzeile`, `zeilen_ueberspringen`.
- `zahlen`: `dezimal` (`,`/`.`), `tausender`; `datum.format` (strftime, z. B. `%d.%m.%Y`, `%Y-%m-%d`, `%d%m%Y`).
- `aufbau.art`:
  - `zeile_je_position` – Kopf in jeder Zeile wiederholt, gruppiert über `rechnung_schluessel`, Kopfwerte müssen je Gruppe gleich sein;
  - `satzart` – Spalte mit K/P (oder 1/2 …);
  - `kopf_und_positionsdatei` – zwei Dateien (Kopf `*_kopf.csv`, Positionen `*_pos.csv`) mit gemeinsamer Belegnummer, Wartezeit auf Partner wie 3.5;
  - `feste_breite` – Satzart-Stelle + `von`/`bis` je Feld, `implizite_nachkommastellen`.
- `felder.kopf` / `felder.position`: Ziel = **BT-Nummer** (oder `kundennummer`, `steuer`), Quelle = `spalte` oder `fest`; `typ` (text/zahl/datum/ganzzahl), `optional`, `zweck: pruefung` (nur Kontrollwert).
- `mappings.einheiten`: Hausbezeichnung → **UN/ECE Rec 20** (Stück→C62, Std→HUR, m→MTR, kg→KGM, l→LTR, Tag→DAY, pauschal→LS), `unbekannt: pruefen|fehler|<Code>`.
- `mappings.steuer`: WaWi-Schlüssel → BT-151 (S, Z, E, AE, K, G, O) + BT-152 Satz, bei E/AE/K/G/O zusätzlich BT-120 Text + BT-121 VATEX-Code.
- `kundenstamm`: Datei + Schlüssel; liefert BT-44 ff. (Name, Anschrift), BT-48 USt-Id, **BT-49 elektronische Adresse**, **BT-10 Leitweg-ID**, Zahlungsziel, Ausgabeformat je Kunde.
- `sicherheit`: was bei fehlendem Pflichtfeld/unbekanntem Mapping/Summenabweichung passiert (`pruefen` = Prüfansicht, `fehler` = Fehlerordner).

### 3b.5 Beispieldateien (`beispiele/`, alles erfunden)
`variante-a_positionen_utf8.csv`, `variante-b_wawi_cp1252.csv` (Windows-1252, `;`, Dezimalkomma, Satzart), `variante-c_festbreite_cp1252.txt`, `profil-variante-a.json`, `profil-variante-b.yaml`, `profil-variante-c.yaml`, `kundenstamm.csv`, `druckauftrag-wawi.pdf` (2 Rechnungen, 3 Seiten, Courier, Textebene), `vorlage-wawi-druck.yaml`, `textdruck-wawi_cp1252.txt`, `README.md` (mit Soll-Summen).

### 3b.6 UI-Skizzen Input (Assistent)

Gleiche Leitlinien wie Abschnitt 4: Ziele ≥ 48 px, ░ = ausgegraut/inaktiv, Toasts statt Popups, nichts blinkt, kurze Zeiten.

**(a) CSV-Zuordnung**
```
┌─ Neues Eingangsprofil: CSV ─────────────────────────────────────────────────────┐
│ ① Datei   ② Vorschau   ③ Zuordnen   ④ Testlauf                     Schritt 2/4 │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Datei:  variante-b_wawi_cp1252.csv                          [ Andere Datei… ]   │
│                                                                                 │
│ Erkannt:  Kodierung [Windows-1252 ▾]  Trennz. [ ; ▾]  Dezimal [ , ▾]            │
│           Datum [TT.MM.JJJJ ▾]  Kopfzeile [✓]  Aufbau [Satzart-Spalte ▾]        │
│           ✓ Umlaute lesbar („Stück“, „für“)   ✓ 11 Zeilen, 14 Spalten           │
│                                                                                 │
│ ┌─────────┬──────────────┬────────────┬─────────┬──────────────────────┬──────┐ │
│ │ Satzart │ Belegnr      │ Belegdatum │ Kundennr│ Bezeichnung          │ ME   │ │
│ ├─────────┼──────────────┼────────────┼─────────┼──────────────────────┼──────┤ │
│ │ K       │ RE-2026-0101 │ 05.10.2026 │ K-1001  │                      │      │ │
│ │ P       │ RE-2026-0101 │            │         │ Schraube M8 verzinkt │ Stück│ │
│ │ P       │ RE-2026-0101 │            │         │ Montagearbeit vor Ort│ Std. │ │
│ └─────────┴──────────────┴────────────┴─────────┴──────────────────────┴──────┘ │
│                                                                                 │
│                                            [ Zurück ]   [ Weiter: Zuordnen ]    │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─ ③ Zuordnen ────────────────────────────────────────────────────────────────────┐
│ Spalte der Datei          →  Feld der E-Rechnung              Status            │
│ Belegnr                   →  [Rechnungsnummer (BT-1)     ▾]   ✓                 │
│ Belegdatum                →  [Rechnungsdatum (BT-2)      ▾]   ✓ 05.10.2026      │
│ Kundennr                  →  [Kundennummer → Kundenstamm ▾]   ✓ 3/3 gefunden    │
│ Lieferdatum               →  [Leistungsdatum (BT-72)     ▾]   ✓                 │
│ Ihre Bestellung           →  [Bestellnummer (BT-13)      ▾]   ✓ 1× gefüllt      │
│ Menge                     →  [Menge (BT-129)             ▾]   ✓ 3,5 → 3.5       │
│ ME                        →  [Einheit (BT-130)           ▾]   ⚠ 1 unbekannt     │
│ EP netto                  →  [Einzelpreis netto (BT-146) ▾]   ✓                 │
│ StSchl                    →  [Steuerschlüssel            ▾]   ✓ 1→S 19 %, 2→S 7%│
│ Summe brutto              →  [nur Kontrolle (BT-112)     ▾]   ✓                 │
│ Pos, Artikelnr, Bezeichn. →  BT-126, BT-155, BT-153            ✓                │
│                                                                                 │
│ Einheiten:  Stück→C62 ✓   Std.→HUR ✓   m→MTR ✓   psch.→ [ wählen… ▾ ] ⚠        │
│ Fehlende Pflichtfelder: keine      Fest: Währung EUR, Art 380 (Rechnung)        │
│                                            [ Zurück ]   [ Weiter: Testlauf ]    │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─ ④ Testlauf (nichts wird gespeichert) ──────────────────────────────────────────┐
│ Rechnung      Kunde                  Netto     USt   Brutto  Kontr.  Ergebnis   │
│ RE-2026-0101  Beispiel Handel GmbH  327,40   57,42   384,82    ✓    ✓ gültig   │
│ RE-2026-0102  Stadtverw. Musterh.   174,50   33,16   207,66    ✓    ✓ gültig   │
│ RE-2026-0103  Probe Kleinbetrieb    145,00   27,55   172,55    ✓    ⚠ Prüfen   │
│               └ Einheit „psch.“ ohne Zuordnung                                  │
│ [ XML ansehen ]  [ Prüfbericht ]                                                │
│ Profilname: [ WaWi Semikolon          ]                                         │
│                                            [ Zurück ]   [ Profil speichern ]    │
└─────────────────────────────────────────────────────────────────────────────────┘
   Toast unten rechts: „Profil gespeichert“
```

**(b) PDF / Druck – Vorlage anlernen**
```
┌─ Neue Druck-Vorlage ────────────────────────────────────────────────────────────┐
│ ① Beispieldruck  ② Kopffelder  ③ Positionen  ④ Testlauf             Schritt 2/4 │
├──────────────────────────────────────────────────┬──────────────────────────────┤
│ druckauftrag-wawi.pdf          [◀] Seite 1/3 [▶] │ Feld wählen, im Bild klicken │
│ ┌──────────────────────────────────────────────┐ │                              │
│ │ Muster GmbH * Musterstraße 1 * 12345 …       │ │ Rechnungsnummer (BT-1)       │
│ │                                              │ │  ✓ RE-2026-0101              │
│ │ Beispiel Handel  ┃Rechnungsnr.:┃[RE-2026-0101] │ │  Anker „Rechnungsnr.:“ →     │
│ │ Einkauf          ┃Datum:       ┃[05.10.2026]   │ │ Rechnungsdatum (BT-2)        │
│ │ Beispielweg 5    ┃Kunden-Nr.:  ┃[K-1001]       │ │  ✓ 05.10.2026                │
│ │ 12345 Musterst.  ┃Lieferdatum: ┃[02.10.2026]   │ │ Kundennummer                 │
│ │                   Seite:        1 von 2       │ │  ✓ K-1001 (im Kundenstamm)   │
│ │ R E C H N U N G                              │ │ Leistungsdatum (BT-72) ✓     │
│ │ Pos Art.-Nr. Bezeichnung      Menge ME …     │ │ Bestellnummer (BT-13)        │
│ │  1  A-100    Schraube M8 …      500 Stk …    │ │  ░ optional, nicht gesetzt   │
│ └──────────────────────────────────────────────┘ │                              │
│ [ − ]  [ + ]  Zoom                               │ ┃Anker┃  [Wert]              │
│                                                  │ [ Bereich ziehen ] [Entfernen]│
├──────────────────────────────────────────────────┴──────────────────────────────┤
│ Trennung: [✓] neue Rechnungsnr.  [✓] „Seite 1 von“      Erkannt: 2 Rechnungen   │
│                                            [ Zurück ]   [ Weiter: Positionen ]  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─ ③ Positionstabelle markieren ──────────────────────────────────────────────────┐
│ 1. Kopfzeile anklicken: ✓ „Pos Art.-Nr. Bezeichnung …“                          │
│ 2. Spaltengrenzen ziehen (Zahlen rechtsbündig ⇥):                               │
│   │Pos│Art.-Nr.│Bezeichnung                 ⇥Menge│ME │ ⇥Einzelpr.│ ⇥Gesamt│St│ │
│   │ 1 │A-100   │Schraube M8 verzinkt        │  500│Stk│      0,12 │   60,00│A │ │
│   │ 2 │A-200   │Montagearbeit vor Ort       │  3,5│Std│     65,00 │  227,50│A │ │
│   │ 3 │B-010   │Fachbuch „Montage für Einst…│    1│Stk│     39,90 │   39,90│B │ │
│ 3. Spalte → Feld: Pos→BT-126  Art.-Nr.→BT-155  Bezeichnung→BT-153               │
│    Menge→BT-129  ME→BT-130  Einzelpr.→BT-146  Gesamt→[nur Kontrolle]  St→Steuer │
│ 4. Ende der Tabelle: [ „Nettobetrag“ ▾ ]  Zeilen ignorieren: [ Übertrag, ---- ] │
│ Steuer: A→ [S 19 % ▾]  B→ [S 7 % ▾]     Einheiten: Stk→C62  Std→HUR             │
│ ✓ Tabelle läuft über 2 Seiten weiter (Übertrag erkannt)                         │
│                                            [ Zurück ]   [ Weiter: Testlauf ]    │
└─────────────────────────────────────────────────────────────────────────────────┘
   ④ Testlauf: wie (a) ④, zusätzlich Spalte „Seiten“ (1–2, 3) und „Kontrolle Gesamtbetrag ✓“.
```

**(c) Prüfansicht für unsichere Fälle**
```
┌─ Prüfen (2 offen) ──────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────┐ ┌───────────────────────────────────────────────┐ │
│ │ ● RE-2026-0103  vor 3 Min │ │ RE-2026-0103 · Probe Kleinbetrieb e.K.         │ │
│ │   CSV · 1 Hinweis         │ │ Quelle: variante-b_wawi_cp1252.csv, Zeile 10   │ │
│ │ ○ (ohne Nr.)    14:05     │ │                                               │ │
│ │   Druck · Vorlage unklar  │ │ Feld              Wert         Herkunft   Sich.│ │
│ └───────────────────────────┘ │ Rechnungsnr.      RE-2026-0103 CSV Belegnr  ✓ │ │
│                               │ Kunde (BT-44)     Probe Klei…  Kundenstamm  ✓ │ │
│                               │ E-Adresse (BT-49) buchhaltung@ Kundenstamm  ✓ │ │
│                               │ Pos 1 Einheit     [ psch. → LS ▾ ]  CSV     ⚠ │ │
│                               │   └ „psch.“ ist keiner Einheit zugeordnet     │ │
│                               │ Summe brutto      172,55 = 172,55 berechnet ✓ │ │
│                               │                                               │ │
│                               │ [✓] Zuordnung „psch. → LS“ fürs Profil merken │ │
│                               │                                               │ │
│                               │ [ Original ansehen ]                           │ │
│                               │ [ Verwerfen ]  [ Später ]  [ Freigeben ]       │ │
│                               └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
  „Verwerfen“ fragt nach (einziges Popup): „RE-2026-0103 verwerfen? Datei geht nach fehler/.“ [Abbrechen] [Verwerfen]
  „Freigeben“ → Toast „RE-2026-0103 erzeugt“. Freigeben bleibt ░ ausgegraut, solange ein ⚠-Feld offen ist.
  Bei Druck-Fällen links das Seitenbild mit markiertem Feld, rechts dieselbe Tabelle.
```

**(d) Drucker einrichten**
```
┌─ Einstellungen › Drucker ───────────────────────────────────────────────────────┐
│ Druckannahme                                                                     │
│   Status: ● läuft auf Port [ 9100 ]   letzter Auftrag 14:05 (2 Rechnungen)       │
│   [✓] nur von diesem PC (127.0.0.1)                                              │
│   [ ] auch aus dem Netz annehmen   erlaubte Absender: [ 192.0.2.10        ] ░    │
│                                                                                  │
│ Drucker auf diesem PC                                                            │
│   E-Rechnung         Microsoft Print to PDF → 127.0.0.1:9100   ✓ eingerichtet    │
│                      [ Testseite drucken ]  [ Entfernen ]                         │
│   E-Rechnung (Text)  Generic / Text Only → 127.0.0.1:9100      ░ nicht vorhanden │
│                      [ Einrichten ]                                               │
│   Hinweis: Einrichten braucht einmal Administratorrechte.                         │
│                                                                                  │
│ Andere Rechner (ERP-Server)                                                       │
│   Drucker dort anlegen mit Ziel  192.0.2.20 : 9100  (Raw)                         │
│   Treiber Windows: „Microsoft Print to PDF“ · Linux: socket://192.0.2.20:9100     │
│   [ Anleitung kopieren ]                                                         │
│                                                                                  │
│ Zuordnung Druck → Vorlage:  [ automatisch erkennen ▾ ]   Vorlagen: 1  [ Neu… ]    │
└─────────────────────────────────────────────────────────────────────────────────┘
  Linux-Variante: „E-Rechnung → socket://127.0.0.1:9100 (CUPS)“, Einrichten fragt per pkexec nach dem Passwort.
  „Testseite drucken“ → Toast „Testseite angekommen (vor 2 s)“ oder „Keine Testseite angekommen – Port prüfen“.
```

### 3b.7 Offene Punkte Input (für Prototyp)
1. ⚠️ **Microsoft Print to PDF auf TCP/IP-Port** testen (dokumentiert/verbreitet ist nur Datei-Port); Fallback Datei-Port oder clawPDF.
2. ⚠️ „Generic / Text Only“ unter Windows 11 vorhanden? Welche Codepage? Umlaute testen.
3. ⚠️ Windows IPP-Klassentreiber: sendet er PDF, wenn unser IPP-Server `application/pdf` anbietet? Sonst nur Raster → OCR nötig.
4. ⚠️ Lizenz ipp-server (BSD-2 laut Suche) im Repo bestätigen, falls als Basis genutzt.
5. Welche WaWi/ERP nutzt der Nutzer konkret (Exportformat, Druckweg, Netzwerk)? Ohne echtes Beispiel bleiben Profile/Vorlagen generisch.

---

## 4. UI-Skizzen (Deutsch)

Leitlinien: schlicht, ein Fenster mit 3 Reitern; alle Schaltflächen/Zeilen **≥ 48 px** hoch; inaktive Elemente **ausgegraut** (░); **Toasts** unten rechts (verschwinden nach 4 s, ohne Animation/Blinken); **Popups nur für Bestätigungen**; kurze Zeitangaben („vor 2 Min“, „14:05“).

### 4.1 Hauptfenster / Status
```
┌──────────────────────────────────────────────────────────────────────┐
│ ERechnung-Wandler                                          [–][□][×] │
├──────────────────────────────────────────────────────────────────────┤
│ [ Status ]   [ Einstellungen ]   [ Protokoll ]                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ● Überwachung aktiv          Modus: Tray-App      Profil: XRechnung │
│    Eingang:  D:\Rechnungen\Eingang                       (CII)       │
│    Ausgang:  D:\Rechnungen\Ausgang                                   │
│                                                                      │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐      │
│  │  Heute erzeugt   │ │  Wartet          │ │  Fehler          │      │
│  │       12         │ │        1         │ │        2         │      │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘      │
│                                                                      │
│  Letzte Vorgänge                                                     │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ ✔ RE-2026-0042   XRechnung   gültig            vor 2 Min       │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ ⏳ RE-2026-0043   wartet auf Datendatei (.json)  vor 3 Min       │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ ✖ RE-2026-0041   BR-DE-15: Käuferreferenz fehlt   14:05  [Details]│
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ ✔ RE-2026-0040   ZUGFeRD EN16931  gültig            13:52       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  [ ⏸ Pausieren ]  [ ▶ Jetzt prüfen ]  [ 📂 Ausgang öffnen ]          │
│                                                                      │
│                              ┌─────────────────────────────────────┐ │
│                              │ ✔ RE-2026-0042.xml erzeugt          │ │ ← Toast
│                              └─────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
Läuft als Dienst:  Kopfzeile „● Dienst aktiv (Hintergrund)“, [Pausieren]
bleibt nutzbar (steuert Dienst), sonst identisch.
Pausiert: Punkt grau „○ Pausiert seit 14:10“, [▶ Fortsetzen].

Tray-Menü (Rechtsklick):
  ┌─────────────────────────┐
  │ Fenster öffnen          │
  │ Pausieren               │
  │ Ausgang öffnen          │
  │ ─────────────────────── │
  │ Beenden                 │
  └─────────────────────────┘
```

### 4.2 Einstellungen
```
┌──────────────────────────────────────────────────────────────────────┐
│ [ Status ]   [ Einstellungen ]   [ Protokoll ]                       │
├──────────────────────────────────────────────────────────────────────┤
│ Bereiche:  (•) Ordner  ( ) Format  ( ) Absender  ( ) Hintergrund     │
├──────────────────────────────────────────────────────────────────────┤
│ ORDNER                                                               │
│  Eingang   [ D:\Rechnungen\Eingang                  ] [ Wählen… ]   │
│  Ausgang   [ D:\Rechnungen\Ausgang                  ] [ Wählen… ]   │
│  Erledigte Dateien  (•) nach Eingang\erledigt verschieben            │
│                     ( ) löschen                                      │
│  Wartezeit auf Partnerdatei  [ 60 ] s                                │
│  [✓] Netzlaufwerk: zusätzlich alle 30 s abfragen                     │
├──────────────────────────────────────────────────────────────────────┤
│ FORMAT                                                               │
│  Ausgabe   (•) XRechnung   ( ) ZUGFeRD / Factur-X                    │
│  Syntax    (•) CII  ( ) UBL                 ← nur bei XRechnung      │
│  Profil    [ EN 16931         ▾ ]  ░ nur bei ZUGFeRD (ausgegraut) ░  │
│            (Auswahl: BASIC · EN 16931 · EXTENDED · XRECHNUNG)        │
│  Sichtteil (ZUGFeRD)  (•) aus Dokument (docx/txt)                    │
│                       ( ) aus Daten erzeugen                         │
│  [✓] Original als PDF-Anlage beilegen (XRechnung)                    │
│  [ ] Warnungen wie Fehler behandeln                                  │
│  Regelpaket: XRechnung 3.0.2 (31.08.2026) · ZUGFeRD 2.5.2            │
│              [ Regelpaket aktualisieren… ]                           │
├──────────────────────────────────────────────────────────────────────┤
│ ABSENDER (Stammdaten)                                                │
│  Firma         [ Muster Handwerk GmbH                ]               │
│  Straße        [ Beispielstraße 5                     ]              │
│  PLZ / Ort     [ 12345 ] [ Musterstadt               ]               │
│  Land          [ DE ▾ ]                                              │
│  USt-IdNr.     [ DE123456788      ]  Steuernr. [ 12/345/67890 ]      │
│  E-Mail (BT-34)[ rechnung@muster.example              ]              │
│  Kontakt       [ Erika Beispiel ] Tel. [ 01234 567890 ]              │
│  IBAN          [ DE00 0000 0000 0000 0000 00 ]  BIC [ OPTIONAL   ]   │
│  Zahlungsziel  [ 14 ] Tage                                           │
│  [ ] Kleinunternehmer (§ 19 UStG)                                    │
├──────────────────────────────────────────────────────────────────────┤
│ HINTERGRUND                                                          │
│  (•) Tray-App, beim Anmelden starten                                 │
│  ( ) Systemdienst (läuft ohne Anmeldung)                             │
│      Dienststatus: nicht eingerichtet                                │
│      [ Dienst einrichten ]   ░[ Dienst entfernen ]░                  │
│  [✓] Beim Schließen in den Tray minimieren                           │
├──────────────────────────────────────────────────────────────────────┤
│                         ░[ Verwerfen ]░   ░[ Speichern ]░            │
│   (aktiv erst nach Änderung; Pflichtfeld leer → Feld rot umrandet,   │
│    Speichern bleibt ausgegraut)                                      │
└──────────────────────────────────────────────────────────────────────┘

Einzige Popups (Bestätigungen):
  ┌──────────────────────────────────────────────┐
  │ Dienst einrichten?                           │
  │ Dafür sind Administratorrechte nötig.        │
  │ Die Tray-App wird danach beendet.            │
  │                                              │
  │          [ Abbrechen ]   [ Einrichten ]      │
  └──────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────┐
  │ Ungespeicherte Änderungen verwerfen?         │
  │          [ Abbrechen ]   [ Verwerfen ]       │
  └──────────────────────────────────────────────┘
Toast nach Speichern: „✔ Einstellungen gespeichert“
```

### 4.3 Protokoll / Fehleransicht
```
┌──────────────────────────────────────────────────────────────────────┐
│ [ Status ]   [ Einstellungen ]   [ Protokoll ]                       │
├──────────────────────────────────────────────────────────────────────┤
│ Filter: [ Alle ▾ ]  [ Heute ▾ ]  Suche: [ RE-2026-00          ]      │
├──────────────────────────────────────────────────────────────────────┤
│ Zeit   │ Rechnung      │ Ergebnis                                    │
│────────┼───────────────┼─────────────────────────────────────────────│
│ 14:21  │ RE-2026-0042  │ ✔ gültig (XRechnung CII)                    │
│ 14:05  │ RE-2026-0041  │ ✖ 2 Fehler, 1 Warnung               ▸       │
│ 13:52  │ RE-2026-0040  │ ✔ gültig (ZUGFeRD EN16931)                  │
│ gestern│ RE-2026-0039  │ ⚠ Partner fehlt (nur .docx)                 │
├──────────────────────────────────────────────────────────────────────┤
│ Details  RE-2026-0041                         Eingang: 14:04         │
│  ✖ BR-DE-15  Käuferreferenz (BT-10) fehlt.                           │
│     → In JSON „kaeuferreferenz“ ergänzen (bei Behörden: Leitweg-ID). │
│  ✖ BR-CO-10  Summe der Positionen 760,00 ≠ angegeben 670,00.         │
│     → Summe aus Daten entfernen oder korrigieren.                    │
│  ⚠ PDF/A: Schrift „Calibri“ nicht eingebettet (behoben beim Export). │
│  Dateien: RE-2026-0041.docx · RE-2026-0041.json                      │
│                                                                      │
│  [ 📂 Ordner öffnen ]  [ 📄 Prüfbericht ]  [ ↻ Erneut verarbeiten ]   │
│  ░[ Fehler kopieren ]░ (aktiv sobald Eintrag gewählt)                │
├──────────────────────────────────────────────────────────────────────┤
│ Protokoll wird 90 Tage aufbewahrt.          [ Exportieren (CSV) ]    │
└──────────────────────────────────────────────────────────────────────┘
„Erneut verarbeiten“ verschiebt die Dateien aus fehler\ zurück in Eingang
→ Toast „↻ RE-2026-0041 erneut eingereiht“ (kein Popup).
```

---

## 5. Packaging-Skizze

```
erechnung/
  app/ (PyQt6-UI, worker/, formats/{cii,ubl,zugferd}, validate/, convert/)
  rules/            ← Regelpakete (XRechnung-Bundle, ZF-XSD), austauschbar
  packaging/
    linux/  ERechnung.spec, build-appimage.sh, AppRun, .desktop, licenses/
    windows/ ERechnung.spec, build.py, build-windows.sh (Wine), winsw/, licenses/
  third_party/ (gepinnt + SHA256): jre-21-jlink-{win,linux}, mustang-cli.jar,
               kosit-validator.jar (opt.), libreoffice-portable (opt.)
```
Größen grob: App ~80 MB + JRE ~50 MB + Mustang ~60 MB = **~190 MB ohne LibreOffice, ~550 MB mit**. ⚠️ Schätzung.

---

## 6. Offene Fragen an den Nutzer
1. **docx-Treue vs. Größe:** LibreOffice mitliefern (+~350 MB, beste Darstellung) oder Variante „Sichtteil aus Daten erzeugen“ / installiertes LibreOffice/Word nutzen?
2. **Hauptziel:** Überwiegend XRechnung (z. B. Behörden, Leitweg-ID) oder ZUGFeRD an Firmen? Davon hängt der Default und die Priorität der docx-Konvertierung ab.
3. **Woher kommen CSV/JSON?** Eigenes Tool/ERP-Export (welches Format, eine Datei je Rechnung oder Sammel-CSV) oder von Hand? Braucht es Gutschriften/Korrekturen, Abschlagsrechnungen, Reverse Charge, Kleinunternehmer?
4. ~~Lizenz: GPL-3.0 oder PySide6?~~ → entschieden: Apache-2.0 + PySide6 (Phase 2a).
5. **Input (neu):** Welche WaWi/ERP konkret? Druckt sie über Windows-Treiber (dann PDF) oder als Text/DOS? Läuft sie auf demselben PC oder auf einem Server (dann Druckannahme im Netz, Firewall, Dienst-Modus)?
6. Soll die Druckannahme den Druck **zusätzlich** an einen echten Drucker weiterreichen (Papier + E-Rechnung) oder nur umwandeln?
7. Wer pflegt den Kundenstamm (BT-49 E-Mail, Leitweg-ID) – CSV-Datei, Export aus der WaWi, oder Pflege in unserer UI?

## 7. Quellen (Auswahl)
- § 27 Abs. 38 UStG: https://www.gesetze-im-internet.de/ustg_1980/__27.html
- BMF-FAQ E-Rechnung: https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html
- BMF-Schreiben 15.10.2025: https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Umsatzsteuer/Umsatzsteuer-Anwendungserlass/2025-10-15-einfuehrung-obligatorische-e-rechnung.html
- BMF-Schreiben 15.10.2026 (⚠️ Sekundär): https://bga.de/bga-update/bga-update-231026/drittes-bmf-schreiben-zur-e-rechnung-veroeffentlicht/
- XRechnung Versionen: https://xeinkauf.de/xrechnung/versionen-und-bundles/
- ZUGFeRD 2.5.2: https://www.ferd-net.de/aktuelles-veranstaltungen/aktuelles/news/zugferd-252-veroeffentlicht
- EN 16931-1:2026: https://ec.europa.eu/newsroom/digital/items/930407/en
- Mustang History: https://raw.githubusercontent.com/ZUGFeRD/mustangproject/master/History.md · NOTICE: https://github.com/ZUGFeRD/mustangproject/blob/master/NOTICE
- drafthorse: https://pypi.org/project/drafthorse/ · factur-x: https://pypi.org/project/factur-x/
- ZUGFeRD-csharp: https://github.com/stephanstapel/ZUGFeRD-csharp/releases
- KoSIT Validator-Konfiguration: https://github.com/itplr-kosit/validator-configuration-xrechnung
- Microsoft Treiber-Wartungsende: https://learn.microsoft.com/en-us/windows-hardware/drivers/print/end-of-servicing-plan-for-third-party-printer-drivers-on-windows · Protected Print Mode: https://learn.microsoft.com/en-us/windows/modern-print/windows-protected-print-mode/windows-protected-print-mode
- clawPDF: https://github.com/clawsoftware/clawPDF · PDFCreator-Lizenz: https://support.pdfforge.org/pdfcreator-licensing
- CUPS-PDF Lizenz: https://www.cups-pdf.de/licensing.shtml · CUPS Treiber/Printer Applications: https://openprinting.github.io/cups/drivers.html · PAPPL: https://github.com/michaelrsweet/pappl/
- pdfplumber: https://github.com/jsvine/pdfplumber · pypdfium2: https://github.com/pypdfium2-team/pypdfium2/ · PyMuPDF-Lizenz: https://pymupdf.io/licensing · invoice2data: https://github.com/invoice-x/invoice2data

## Phase 1 – Umsetzung (Stand 31.10.2026)

### PDF/A-3-Lösung
- Eigenbau mit **pikepdf** (MPL-2.0, auf qpdf Apache-2.0) + **fontTools** (MIT): nicht eingebettete Standard-14-Schriften (WinAnsi) werden durch metrisch kompatible **Liberation**-Subsets (OFL 1.1) ersetzt; sRGB-OutputIntent (ICC aus LittleCMS, MIT); XMP mit pdfaid 3/B, pdfaExtension-Schema und fx-Schema (Factur-X, EN 16931); factur-x.xml als EmbeddedFile mit AFRelationship /Alternative.
- Nicht reparierbare Druck-PDFs (unbekannte/nicht-WinAnsi-Schriften, Verschlüsselung) → neues Sichtbild mit **reportlab** (BSD).
- Verworfen: Ghostscript (AGPL), PyMuPDF (AGPL), python `factur-x` (hängt an LGPL python-stdnum, kein OutputIntent).

### Lizenzen (Laufzeit)
| Komponente | Lizenz |
|---|---|
| pikepdf / qpdf | MPL-2.0 / Apache-2.0 |
| fontTools | MIT |
| reportlab | BSD |
| lxml | BSD |
| pdfplumber / pdfminer.six | MIT / MIT |
| pypdfium2 (PDFium) | Apache-2.0 bzw. BSD-3 |
| Pillow | MIT-CMU (HPND) |
| cryptography | Apache-2.0 oder BSD |
| PyYAML | MIT |
| watchdog | Apache-2.0 |
| Liberation Fonts | SIL OFL 1.1 |
| sRGB-ICC (LittleCMS) | MIT |

Validierung (optional, nicht für die Erzeugung nötig): Mustang-CLI (Apache-2.0), veraPDF (GPLv3+ / MPL-2.0 dual, in Mustang enthalten), KoSIT-Validator (Apache-2.0), XRechnung-Konfiguration (Apache-2.0), Temurin JRE (GPLv2+Classpath Exception).

### Validierung
Mustang 2.26.0 (inkl. veraPDF) und KoSIT 1.6.3 + XRechnung-Konfiguration 3.0.2 (31.08.2026): alle Beispiele 0 Fehler / 0 Warnungen, PDF/A-3b konform.
