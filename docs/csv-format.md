# CSV-Format für Fakturafalter

Fakturafalter liest Rechnungsdaten aus einem CSV-Export der Warenwirtschaft. Ein **Profil**
(YAML-Datei) beschreibt, wie der Export aussieht. Hier steht, welches Format erwartet wird und
welche Spalten mindestens vorhanden sein müssen.

## Erwartete Form

- Kodierung **UTF-8**
- Trennzeichen **Semikolon** (`;`), Textbegrenzer `"`
- erste Zeile = Spaltennamen
- Zahlen mit **Dezimalkomma** (`1234,50`; Tausenderpunkt erlaubt: `1.234,50`)
- Datum **TT.MM.JJJJ** (`02.10.2026`)
- **eine Zeile je Position**; die Kopfwerte (Rechnungsnummer, Datum, Kunde …) stehen in jeder
  Zeile der Rechnung gleich. Zeilen mit derselben Rechnungsnummer bilden eine Rechnung.

## Was das Profil sonst zulässt

| Einstellung | Möglich |
|---|---|
| Kodierung | `auto`, `utf-8`, `utf-8-sig` (mit BOM), `cp1252`, `cp850`, `iso-8859-15` |
| Trennzeichen | `;` `,` Tabulator `\|` oder `auto` |
| Kopfzeile / Zeilen überspringen | ja/nein, Anzahl |
| Zahlen | Dezimal- und Tausenderzeichen frei (`1.234,50` oder `1,234.50`) |
| Datum | jedes feste Format, z. B. `%d.%m.%Y`, `%d.%m.%y`, `%Y-%m-%d` |
| Aufbau | `zeile_je_position` (Standard), `satzart` (Kopf- und Positionszeilen, z. B. K/P), `feste_breite` |
| Spaltennamen | frei; das Profil ordnet jede Spalte einem Feld zu |
| Einheiten, Steuer | Hausbezeichnungen (`Stk`, `Std`, Steuerschlüssel `1`/`2` …) werden im Profil übersetzt |

## Mindestspalten

Pflichtangaben nach § 14 Abs. 4 UStG bzw. EN 16931, soweit sie **nicht fest im Profil** stehen.
Fest im Profil stehen: Verkäufer (Name, Anschrift, USt-IdNr. oder Steuernummer), IBAN,
Währung (EUR), Rechnungsart (380), Land des Käufers (DE), Einheiten- und Steuerübersetzung.
Die Rechnungsbeträge rechnet Fakturafalter selbst aus.

| Spalte (Beispielname) | Bedeutung | BT | Beispiel |
|---|---|---|---|
| Rechnungsnr | fortlaufende, einmalige Rechnungsnummer | BT-1 | `SK-2026-0412` |
| Datum | Rechnungsdatum | BT-2 | `02.10.2026` |
| Lieferdatum | Tag der Lieferung/Leistung – **oder** stattdessen zwei Spalten Leistung von/bis (BT-73/BT-74) **oder** eine Spalte Leistungsmonat (`10/2026`, § 31 Abs. 4 UStDV) | BT-72 | `01.10.2026` |
| Kunde | Name des Käufers | BT-44 | `Café Morgenrot` |
| Strasse | Straße und Hausnummer des Käufers | BT-50 | `Lindenplatz 2` |
| PLZ | Postleitzahl des Käufers | BT-53 | `31134` |
| Ort | Ort des Käufers | BT-52 | `Hildesheim` |
| Artikel | Bezeichnung der Leistung | BT-153 | `Dinkelbrötchen` |
| Menge | Menge | BT-129 | `30` |
| Einheit | Mengeneinheit (Hausbezeichnung, im Profil übersetzt) | BT-130 | `Stk` |
| Einzelpreis | Einzelpreis netto | BT-146 | `0,55` |
| USt-Satz | Steuersatz oder Steuerschlüssel (im Profil übersetzt in Kategorie und Satz; bei Befreiung mit Grund) | BT-151/BT-152 | `7` |

Kunde, Strasse, PLZ und Ort können entfallen, wenn stattdessen eine **Kundennummer** geliefert wird
und das Profil einen Kundenstamm (eigene CSV) nennt.

## Optionale Spalten

- Kundennummer (mit Kundenstamm statt Anschrift)
- Positionsnummer (BT-126), Artikelnummer (BT-155)
- Bestellnummer (BT-13), Leitweg-ID (BT-10)
- USt-IdNr. (BT-48) und E-Mail (BT-49) des Käufers, Land (BT-55)
- **Adresszusatz** des Käufers (BT-51, Adresszeile 2, z. B. Abteilung oder Gebäude; im XML `ram:LineTwo`).
  Im Profil: `BT-51: {spalte: Adresszusatz}`
- Netto-, USt- und Bruttosumme laut Warenwirtschaft (BT-109/BT-110/BT-112) – nur zur Kontrolle
- **Preiseinheit** (BT-149): auf wie viele Einheiten sich der Einzelpreis bezieht, z. B. `100` für
  „Preis pro 100 Stk“. Fehlt die Spalte oder ist die Zelle leer, gilt `1`. Gesamt = Menge × Einzelpreis
  ÷ Preiseinheit (500 Stk zu 4,80 € pro 100 Stk = 24,00 €). Im Profil: `BT-149: {spalte: Preiseinheit, typ: zahl}`

## Rabatt, Zuschlag, Gutschrift, Lastschrift und weitere Felder (ab 0.6.0)

Alle Felder sind freiwillig. Fehlt eine Spalte, bleibt alles wie bisher. Bestehende Profile laufen unverändert.
Der CSV-Assistent schlägt diese Felder nur vor, wenn der Spaltenname genau passt, z. B. „Belegart“,
„Zeilenart“, „Rabatt %“, „Mandatsreferenz“. Sonst ordnet man sie in der Vorschau von Hand zu.

| Feld im Profil | Bedeutung | Werte / Beispiel |
|---|---|---|
| `belegart` | Belegart → BT-3 | `Rechnung`/`RE` = 380, `Gutschrift`/`GS` = 381, `Korrektur`/`KO` = 384, `Teilrechnung` = 326; eigene Werte unter `mappings.belegart` |
| `BT-25`, `BT-26` | Bezug auf die ursprüngliche Rechnung (Nummer, Datum) | `RE-2026-0101`, `05.10.2026` |
| `zahlungsart` | Zahlungsart → BT-81 | `Überweisung` = 58, `Lastschrift`/`LS` = 59, `Bar` = 10, `Karte` = 48; eigene Werte unter `mappings.zahlungsart` |
| `BT-89`, `BT-91` | SEPA-Lastschrift: Mandatsreferenz, IBAN des Kunden | `MANDAT-2026-007` |
| `BT-90` | Gläubiger-ID (sonst aus Einstellungen → Absender) | `DE98ZZZ09999999999` |
| `BT-113` | bereits gezahlt (Anzahlung) | `100,00` |
| `BT-92`/`BT-94`, `BT-97` | Rabatt auf die ganze Rechnung: Betrag oder %, Grund | `15,00` / `2` |
| `BT-99`/`BT-101`, `BT-104` | Zuschlag auf die ganze Rechnung (z. B. Fracht): Betrag oder %, Grund | `8,50`, `Versandkosten` |
| `BT-138` (`typ: prozent`), `BT-136`, `BT-139` | Rabatt je Position: % oder Betrag, Grund | `10`, `10 %` |
| `BT-141`, `BT-144` | Zuschlag je Position: Betrag, Grund | `5,00` |
| `BT-148`, `BT-147` | Listenpreis und Preisnachlass je Einheit (Einzelpreis = Listenpreis − Nachlass) | `85,00`, `5,00` |
| `zeilenart` | Position oder Rabatt-/Zuschlagszeile | leer/`Position`, `Rabatt`, `Zuschlag`, `Fracht`, `Versand` |
| `BT-11` … `BT-19` | Projekt, Vertrag, Auftrag, Wareneingang, Lieferschein, Vergabe, Objekt, Kostenstelle | |
| `BT-70`, `BT-75` … `BT-80` | Lieferanschrift | |
| `BT-22`, `BT-83`, `BT-124`, `BT-59` | Bemerkung, Verwendungszweck, Link auf Unterlage, abweichender Zahlungsempfänger | |
| `BT-127`, `BT-154` … `BT-161`, `BT-132`, `BT-133`, `BT-134`/`BT-135` | Positionsnotiz, Beschreibung, Kunden-Artikelnr., GTIN, Klassifizierung, Ursprungsland, Merkmal, Bestellposition, Kostenstelle, Leistungszeitraum je Position | |

- **Rabatt- und Zuschlagszeilen.** Ist die Spalte `zeilenart` auf `Rabatt` oder `Zuschlag` gesetzt, wird
  die Zeile keine Position. Sie wird zu einem Nachlass oder Zuschlag auf die ganze Rechnung (BG-20/BG-21).
  Der Betrag ist Menge × Preis bzw. der Positionsbetrag. Das Vorzeichen spielt keine Rolle. Die Steuer kommt
  aus der Steuerspalte der Zeile. Bei `aufbau.art: satzart` geht das Gleiche über eigene Satzarten:
  `aufbau: {rabatt: R, zuschlag: Z}`.
- **Gutschrift.** Ist `belegart` = Gutschrift, dürfen Mengen oder Preise negativ sein. Fakturafalter übernimmt
  sie als positive Beträge, denn bei Belegart 381 steckt das Vorzeichen in der Belegart.
  Negative Preise auf normalen Rechnungen werden als negative Menge übernommen (BR-27).
- **Kundenstamm.** Die Spalten `mandat_bt89` und `iban_bt91` liefern die Lastschriftdaten je Kunde.
  Eine Mandatsreferenz ohne Zahlungsart-Spalte bedeutet Lastschrift.

Beispiel: `beispiele/variante-d_rabatt_gutschrift_lastschrift.csv` mit `beispiele/profil-variante-d.yaml`.

## XML-Eingang (XRechnung/ZUGFeRD, CII und UBL)

XML-Dateien liest Fakturafalter mit allen Feldern nach EN 16931: Rechnungen und Gutschriften (UBL `Invoice`
und `CreditNote`), Nachlässe und Zuschläge, Lastschrift, Anzahlung, Anhänge, Lieferung und Referenzen.
Für jedes Element, das nicht übernommen wird (z. B. aus dem Profil EXTENDED), steht im Protokoll eine
Warnung „XML-Element nicht übernommen: …“. Die Rechnung wird trotzdem erzeugt.
Beispiele: `beispiele/xml-eingang/`.

## Beispiel

```csv
Rechnungsnr;Datum;Lieferdatum;Kunde;Strasse;PLZ;Ort;Artikel;Menge;Einheit;Einzelpreis;USt-Satz
SK-2026-0412;02.10.2026;01.10.2026;Café Morgenrot;Lindenplatz 2;31134;Hildesheim;Quarkbällchen;2,5;kg;9,60;7
SK-2026-0412;02.10.2026;01.10.2026;Café Morgenrot;Lindenplatz 2;31134;Hildesheim;Brotkorb Leihgebühr;30;Stk;2,50;19
```

Das passende Profil: `beispiele/pdf-erkennung/profil-baeckerei.yaml`. Alle Daten sind erfunden.

## Absender importieren

Die eigenen Firmendaten (Verkäufer) erkennt Fakturafalter meist aus dem Druck-PDF. Alternativ lassen sie
sich aus einer CSV übernehmen (Einstellungen → Absender → „Aus CSV übernehmen“, ebenso im Anlern-Assistenten).
Eine Kopfzeile und **eine** Datenzeile, Trennzeichen `;` (auch `,` oder Tab), UTF-8 oder Windows-1252:

```csv
Name;Strasse;PLZ;Ort;USt-IdNr;Steuernummer;IBAN;BIC;Telefon;E-Mail;Register
Normteile Brückner GmbH;Gewerbering 14;42897;Remscheid;DE290319664;126/5743/0815;DE34000000000071100842;;02191 990420;rechnung@normteile-brueckner.invalid;Amtsgericht Wuppertal HRB 990042
```

Nötig sind Name, Strasse, PLZ, Ort, IBAN und USt-IdNr. **oder** Steuernummer; der Rest ist freiwillig.
Freiwillig ist auch eine Spalte **Adresszusatz** (BT-36, Adresszeile 2; auch „Zusatz“ oder „Adresszeile 2“).
Gängige Schreibweisen der Spaltennamen werden erkannt (z. B. „Firma“, „Straße“, „USt-Id“, „Mail“).
Beispiel: `beispiele/industrie/absender-normteile.csv` (erfunden).
