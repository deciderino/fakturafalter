# CSV-Format für Fakturafalter

Fakturafalter liest Rechnungsdaten aus einem CSV-Export der Warenwirtschaft (ERP). Ein **Profil**
(YAML-Datei) beschreibt, wie der Export aussieht. Hier steht, welches Format erwartet wird und
welche Spalten mindestens vorhanden sein müssen.

Wer den Export festlegen oder in der Warenwirtschaft implementieren will, nimmt die
[CSV-Exportspezifikation](csv-standard.md) (ab 0.9.9). Trägt die Kopfzeile die neun
Pflichtnamen (`Rechnungsnummer`, `Rechnungsdatum`, `Leistungsdatum`, `Kundennummer`,
`Bezeichnung`, `Menge`, `Einheit`, `Einzelpreis`, `Steuersatz`), greift das **eingebaute
Standardprofil** – ohne Assistenten, mit letzter Priorität. Vorlagen speicherst du unter
Einstellungen → Eingang & Vorlagen → „CSV-Vorlage speichern…“. Abweichende Spaltennamen
richtest du weiterhin mit „Neue CSV einrichten…“ ein.

## Erwartete Form

- Kodierung **UTF-8**
- Trennzeichen **Semikolon** (`;`), Textbegrenzer `"`
- erste Zeile = Spaltennamen
- Zahlen mit **Dezimalkomma** (`1234,50`; Tausenderpunkt erlaubt: `1.234,50`)
- Datum **TT.MM.JJJJ** (`02.10.2026`)
- **eine Zeile je Position**; die Kopfwerte (Rechnungsnummer, Datum, Kunde …) stehen in jeder
  Zeile der Rechnung gleich. Zeilen mit derselben Rechnungsnummer bilden eine Rechnung.
  Eine Zeile ohne Menge und Preis, aber mit Text (z. B. in der Bezeichnung), ist eine
  **Textzeile**; eine Zeile, die nur Kopffelder trägt, eine **gewollte Leerzeile**.
  Beides gilt ab 0.9.8.1 auch in diesem Standardaufbau (nicht nur bei `bloecke`).

## Was das Profil sonst zulässt

| Einstellung | Möglich |
|---|---|
| Kodierung | `auto`, `utf-8`, `utf-8-sig` (mit BOM), `cp1252`, `cp850`, `iso-8859-15` |
| Trennzeichen | `;` `,` Tabulator `\|` oder `auto` |
| Kopfzeile / Zeilen überspringen | ja/nein, Anzahl |
| Zahlen | Dezimal- und Tausenderzeichen frei (`1.234,50` oder `1,234.50`) |
| Datum | jedes feste Format, z. B. `%d.%m.%Y`, `%d.%m.%y`, `%Y-%m-%d` |
| Aufbau | `zeile_je_position` (Standard, mehrere Rechnungen je Datei), `bloecke` (ab 0.9.8, eine Datei = eine Rechnung; ab 0.9.9: Marker und freie Felder; ab 0.9.10: Satzart als Anfangsregel, Spalten je Block), `satzart` (Kopf- und Positionszeilen, z. B. K/P), `feste_breite` |
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
| Kundenbezeichnung 1 (oder Kunde) | Name des Käufers, Zeile 1 (Zeilen 2 und 3 optional, siehe unten) | BT-44 | `Café Morgenrot` |
| Strasse | Straße und Hausnummer des Käufers | BT-50 | `Lindenplatz 2` |
| PLZ | Postleitzahl des Käufers | BT-53 | `31134` |
| Ort | Ort des Käufers | BT-52 | `Hildesheim` |
| Artikel | Bezeichnung der Leistung | BT-153 | `Dinkelbrötchen` |
| Menge | Menge | BT-129 | `30` |
| Einheit | Mengeneinheit (Hausbezeichnung, im Profil übersetzt) | BT-130 | `Stk` |
| Einzelpreis | Einzelpreis netto | BT-146 | `0,55` |
| USt-Satz | Steuersatz oder Steuerschlüssel (im Profil übersetzt in Kategorie und Satz; bei Befreiung mit Grund) | BT-151/BT-152 | `7` |

Kundenbezeichnung 1, Strasse, PLZ und Ort können entfallen, wenn stattdessen eine **Kundennummer** geliefert wird
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

## Blöcke mit eigener Kopfzeile (ab 0.9.8, überarbeitet ab 0.9.9)

Manche Exporte legen in **einer Datei eine Rechnung** ab, aber in mehreren
Abschnitten: zuerst die Positionen, darunter Zahlung oder Summen – jeder Abschnitt
mit einer eigenen Kopfzeile. Im Profil: `aufbau.art: bloecke`. Welche Felder in
welchem Block stehen, ist frei wählbar; die Pflichtprüfung läuft am Ende über die
zusammengeführte Rechnung. Positionsfelder (Bezeichnung, Menge, Preis, Einheit,
Zeilensteuer, …) gehören nur in den **einen wiederholenden** Block
(`wiederholend: true`; in älteren Profilen: `typ: positionen`).

- Eine Zeile gilt als neue Block-Kopfzeile, wenn mindestens *n* Zellen (Standard
  `kopfzeile_schwelle: 2`) **zugeordnete** Spaltennamen sind, oder wenn sie
  **exakt** einer im Profil gespeicherten `kopfzeile` entspricht. Unbenutzte Namen
  zählen nicht für die Schwelle, dürfen aber stehen. Beginnt die Datei weder mit
  einer Kopfzeile noch mit einem Marker, geht die Rechnung nach „Zu prüfen“.
- Optional erkennt ein Block eine **Markerzeile** (`bloecke[].marker`, z. B.
  `#Kopf`, `#Positionen`; auch ohne `#` erlaubt). Vergleich: erste nicht-leere
  Zelle, ohne Groß/Klein-Unterschied (`name_norm`), alle anderen Zellen leer,
  exakter Wortlaut. Die Markerzeile erscheint nicht auf der Rechnung. Die nächste
  Zeile darf eine Kopfzeile sein; kennt das Profil die Spalten schon und die
  nächste Zeile ist keine Kopfzeile, sind das bereits Daten. `#LEER` (bzw. der
  eingestellte Platzhalter) kann kein Marker sein. Ein Kommentar wie
  `# bitte nicht …` ist kein Marker.
- Leere Zeilen zwischen Blöcken trennen nur; sie erscheinen nicht auf der Sichtseite.
- Kopffelder (Rechnungsnummer, Datum, Kunde, Skonto, Summen, Lieferanschrift …)
  dürfen in jedem Block stehen, auch wiederholt. Gleiche Werte werden
  zusammengeführt, abweichende Werte halten die Rechnung in „Zu prüfen“ an.
  Zwei verschiedene Rechnungsnummern oder ein zweiter Positionsblock → „Zu prüfen“.
- **Textzeilen** (wie im Standardaufbau, ab 0.9.9 vollständig angeschlossen):
  Menge und Preis leer oder `0` / `0,00`, Text vorhanden → der Text hängt
  standardmäßig als Beschreibung (BT-154) an der Position darüber (`zwischen:
  vorher`; Option `nachher`: untere Position). Eine Textzeile *vor* der ersten
  Position: Standard Hinweistext (BT-22), optionale `verwaist`.
- **Gewollte Leerzeile** auf der Sichtseite: Platzhalter (Standard `#LEER`)
  und/oder eine Zeile, die nur Kopffelder trägt (`leerzeile_modus`).
- Steht nur der Preis, entscheidet `preis_ohne_menge` (`pruefen` / `eins` / `kommentar`).
- Im Assistenten (ab 0.9.10, erweitert ab 0.9.11): nach dem Format **Blöcke festlegen**.
  Blöcke lassen sich frei anlegen, umbenennen und als Bereich aufziehen. Die Blockart
  (*normaler Block* oder *sich wiederholend / Positionsblock*) wählst du selbst;
  sie wird nicht aus zugeordneten Feldern abgeleitet. Ein normaler Block liefert nur
  einen Teil der Rechnungsinfo (z. B. Kunde, Beleg, Summen); die Rechnung entsteht
  aus allen Blöcken zusammen. Mehrere normale Blöcke dürfen nicht kollidieren
  (Kunde und Beleg nicht beide als Typ `kopf`). Die Anfangsregel wird aus den ersten
  inhaltlichen Zeilen abgeleitet: Satzart-Wert (auch in einer Datenzeile, z. B.
  `#Kopf;Testkunde;…`), dann die enge Markerform, dann Kopfzeile
  (*verfügbar ab 0.9.10*; Marker *verfügbar ab 0.9.9*; Satzart in der Datenzeile
  *verfügbar ab 0.9.11*). Zeilennummern werden nicht gespeichert. Blockende ist der
  nächste erkannte Blockstart oder das Dateiende. Weiter auf dieser Seite ist nur
  gesperrt, wenn kein Block existiert oder ein Block keine Zeilen hat; fehlende
  Anfangsregel und abweichende Anzahl wiederholender Blöcke sind Warnungen.
  Danach **Spalten je Block** – dieselbe Position darf je Block ein anderes Feld
  sein. Weiter erst, wenn die Pflichtfelder zugeordnet sind: Rechnungsnummer,
  Rechnungsdatum, Bezeichnung, Menge, Einzelpreis, Steuer, und Käufername (BT-44)
  oder Kundennummer (über den Kundenstamm). Gespeichert werden Name und 1-basierte
  Position; beim Lesen hat der Name Vorrang, wenn die Kopfzeile ihn trägt. Ein
  Kopffeld in mehreren Blöcken wird verglichen (Abweichung → Zu prüfen). Probe
  und Eingang nutzen denselben Lesepfad. Dunkles und helles Theme setzen eigene
  Blockfarben mit fester Schriftfarbe (WCAG AA).
- Der Aufbau `satzart` bleibt parallel bestehen; alte Profile ohne `anfang`
  werden aus `marker` bzw. `kopfzeile` abgeleitet und laufen unverändert.
- Bestehende Block-Profile ohne `marker` und `wiederholend` laufen unverändert weiter.


Skonto und Zahlungsziel stehen in eigenen Spalten (`Skonto`, `Zahlungsziel mit
Skonto`, `Zahlungsziel`). Fakturafalter setzt das Fälligkeitsdatum (BT-9) auf
Rechnungsdatum plus **Nettotage** – das Skontodatum ersetzt BT-9 nicht. Sobald
Satz *und* Tage einer Stufe gesetzt sind, stehen in BT-20 zuerst maschinenlesbare
Zeilen der XRechnung-Konvention, danach der bisherige deutsche Klartext:

```
#SKONTO#TAGE=10#PROZENT=2.00#
2 % Skonto innerhalb von 10 Tagen (bis 10.12.2026), zahlbar innerhalb von 14 Tagen ohne Abzug (bis 14.12.2026).
```

In der CSV bleibt das Dezimalkomma (`2` oder `2,00`); in der Konventionszeile
steht der Dezimalpunkt mit genau zwei Nachkommastellen, und nach jeder Stufe
folgt ein Zeilenumbruch. Optional: `Skonto-Basisbetrag`, wenn nicht der volle
Zahlbetrag gilt, sowie eine zweite Stufe (`Skonto 2`, `Zahlungsziel mit Skonto 2`,
`Skonto-Basisbetrag 2`). Fehlt Satz oder Tage einer Stufe, entfällt die
Konventionszeile. Der Sichtteil der PDF zeigt nur den Klartext. Werte können
auch aus dem Kundenstamm oder als Profil-Standard kommen (CSV hat Vorrang).
Bei Gutschrift (381) entfällt strukturiertes Skonto typischerweise.

Verzug oder Mahnung nur als Klartext ohne `#`, etwa in der Bemerkung (BT-22).
Eine Zeile `#VERZUG#` ist in XRechnung 3.0.2 unzulässig und wird nicht erzeugt.
Einzelheiten: [csv-standard.md](csv-standard.md#46-zahlung-und-skonto).

Beispiele (fiktiv): `beispiele/variante-blo_hotel.csv` (SK-2026-0413) und
`beispiele/variante-blo_getrennt.csv`. Profil: `beispiele/profil-variante-blo.yaml`.
Ab 0.9.9 außerdem `beispiele/beispiel-bloecke-klassisch.csv` (Kopf, Positionen,
Zahlung), `beispiele/beispiel-bloecke-frei.csv` (Felder frei verteilt, Kommentar
und `#LEER`) und `beispiele/beispiel-bloecke-marker.csv` (Erkennung über `#Kopf`,
`#Positionen`, `#Summen`) mit den zugehörigen `profil-beispiel-bloecke-*.yaml`.
Ab 0.9.10 außerdem `beispiele/beispiel-satzart-bloecke-koepfe.csv` (Satzart und eigene Kopfzeile je Block),
`beispiele/beispiel-satzart-bloecke-marker.csv`,
`beispiele/beispiel-satzart-gleiche-positionen.csv` (gleiche Spaltenposition, andere Bedeutung) und
`beispiele/beispiel-satzart-ohne-blockkopf.csv` (nur Satzart K/P/S) mit den zugehörigen
`profil-beispiel-satzart-*.yaml`.
Ab 0.9.11 außerdem `beispiele/beispiel-satzart-marker-in-spalte.csv` (fiktiv: `#Kopf` und `#Beleg` als Satzart-Wert in der Datenzeile, kurze Datumsangaben TT.MM.JJ, getrennte Blöcke Kunde und Beleg).
Standardaufbau: `beispiele/variante-zjp_textzeilen.csv` (fiktiv, RE-2026-0818:
Kommentar und Leerzeile über der Position, Kommentar darunter; netto 394,40 /
USt 74,94 / brutto 469,34). Profil: `beispiele/profil-variante-zjp-textzeilen.yaml`.

## Textzeilen, Darstellung und Mengen (ab 0.9.8.1, ab 0.9.9 auch im Blockaufbau)

In den Aufbauten `zeile_je_position` und `bloecke` gilt:

- **Leer** sind leere Zellen, nur Leerzeichen sowie `0` / `0,00`. Menge *und* Preis leer oder 0 → keine Position (Textzeile oder gewollte Leerzeile). Steht nur die Menge, ist es eine Position. Steht nur der Preis, entscheidet `aufbau.textzeile.preis_ohne_menge`: `pruefen` (Standard), `eins` (Menge 1) oder `kommentar`.
- Spalten auf „nicht verwenden“ zählen nirgends mit, auch nicht bei der Erkennung von Kommentar- und Leerzeilen.
- Ohne zugeordnete Positionsspalte erhalten echte Positionen die Nummern 1, 2, 3 … Mit Spalte gilt die Nummer aus der Warenwirtschaft (BT-126 in der XML immer eindeutig). `sicht.positionsnummer: false` blendet die Nummer nur auf der Sichtseite aus.
- `sicht.menge_exakt: true` (Standard): die Sichtseite zeigt die Menge wie in der CSV (`40,00`). In der XML bleibt der Zahlenwert normal.
- `sicht.einheit: csv` zeigt den Einheitentext aus der CSV; Standard `kurz` (z. B. `Stk.`). In der XML steht weiter der Rec-20-Code in BT-130.
- `aufbau.einheit_fehlt_stueck: true` (ab 0.9.8.3): Positionen mit Menge und Preis, aber leerer Einheit, erhalten Stück (Rec 20 H87, auf der Sichtseite der Text „Stück“). Im Protokoll erscheint der Hinweis „Einheit fehlte, Stück angenommen“ (kein Prüffall). Standard `false`: fehlende Einheit bleibt „Zu prüfen“. Die Option wirkt in der gemeinsamen Rechnungserzeugung, also auch in anderen Aufbauten, wenn sie im Profil steht. Kommentarzeilen bleiben unverändert.
- Kommentarzeilen stehen auf der Sichtseite ohne Vorsatz „Beschreibung:“ direkt unter der Position (XML: BT-154). Der Vorsatz gilt nur für eine eigene Beschreibungsspalte. `sicht.kommentar_ohne_bezeichnungen: true` blendet auch Labels wie „Art.-Nr.:“ an Kommentarzeilen aus.
- Im Assistenten folgen (beim Blockaufbau nach „Blöcke festlegen“ und „Spalten je Block“) die Schritte „Textzeilen“ und „Darstellung“ (PDF-Bezeichnung umbenennen, optionale Felder ausblenden, Schalter „Fehlende Einheit = Stück verwenden“). „Darstellung…“ ist später auch direkt in den Einstellungen am Profil erreichbar.

## Profile in den Einstellungen (ab 0.9.8)

In der Konfiguration darf `csv_profile` eine Zeichenkette (Pfad) oder
`{datei: …, aktiv: true|false}` sein. Fehlt `aktiv`, gilt das Profil als aktiv
(bestehende Konfigurationen bleiben gültig). Die Reihenfolge in der Liste ist
die Prüf-Reihenfolge: das erste *aktive* passende Profil gewinnt. Ein
Block-Profil passt ab 0.9.9.1 nur, wenn seine zugeordneten Spalten als
Kopfzeilen in der Datei vorkommen (nicht schon bei ein paar gemeinsamen Namen).
Das Protokoll (`protokoll.tsv`) hat eine neunte Spalte mit dem Profilnamen;
weitere passende Profile weiter unten werden dort erwähnt.
Ab 0.9.10 richtet der Assistent Blockdateien farbig ein (Blöcke festlegen, ab 0.9.11 frei benennbar,
Spalten je Block, Satzart als Anfangsregel). Probe und Eingang nutzen denselben
Lesepfad; bei mehreren passenden Profilen gewinnt das spezifischste, bei
Gleichstand das weiter vorne in der Liste.

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
| `BT-141`/`BT-143` (`typ: prozent`), `BT-144` | Zuschlag je Position: Betrag oder %, Grund | `5,00` |
| `BT-148`, `BT-147` | Listenpreis und Preisnachlass je Einheit (Einzelpreis = Listenpreis − Nachlass) | `85,00`, `5,00` |
| `zeilenart` | Position oder Rabatt-/Zuschlagszeile | leer/`Position`, `Rabatt`, `Zuschlag`, `Fracht`, `Versand` |
| `BT-11` … `BT-19` | Projekt, Vertrag, Auftrag, Wareneingang, Lieferschein, Vergabe, Objekt, Kostenstelle | |
| `BT-70`, `BT-75` … `BT-80` | Lieferanschrift | |
| `BT-22`, `BT-83`, `BT-124`, `BT-59` | Bemerkung, Verwendungszweck, Link auf Unterlage, abweichender Zahlungsempfänger | |
| `BT-128` | Objektkennung je Position | `OBJ-7` |
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

## Kundenbezeichnung 1–3 und Angaben unter der Positionsbezeichnung (ab 0.9.5)

Auch hier ist alles freiwillig bis auf eine Ausnahme: die **Kundenbezeichnung 1** ersetzt die bisherige
Pflichtspalte Kunde. Alte CSVs mit einer Spalte `Kunde` (oder Kundenname, Firma …) laufen unverändert, diese
Spalte gilt als Zeile 1.

| Feld im Profil | Spalte (Beispiel) | Wirkung |
|---|---|---|
| `BT-44` | `Kundenbezeichnung 1` | Pflicht (sofern kein Kundenstamm den Namen liefert) |
| `kaeufer_name_2`, `kaeufer_name_3` | `Kundenbezeichnung 2`, `Kundenbezeichnung 3` | optional; leer = keine Zeile |
| `zeichnungsnummer`, `index` | `Zeichnungsnummer`, `Index` | optional; im XML Artikelmerkmal (BT-160/BT-161) „Zeichnungsnummer“ bzw. „Index“ |

- **Im PDF** steht jede gefüllte Kundenbezeichnung in einer eigenen Zeile des Adressblocks, leere Zeilen
  entfallen (keine Lücke). **Im XML** gibt es nur einen Käufernamen: BT-44 = die gefüllten Zeilen mit je einem
  Leerzeichen verbunden (`Feinmechanik Beispiel GmbH Werk Süd Wareneingang Tor 3`). Adresszusatz (BT-51) und
  Ansprechpartner (BT-56) bleiben eigene Felder.
- Fehlt Zeile 1, aber Zeile 2 oder 3 ist gefüllt, rückt nichts nach: die Rechnung geht nach „Zu prüfen“.
- **Positionstabelle.** Die Spalte Art.-Nr. gibt es nicht mehr, die Bezeichnung ist breiter. Alles Weitere
  steht klein unter der Bezeichnung – nur, wenn es gefüllt ist, in dieser Reihenfolge:
  1. grau: Art.-Nr. (BT-155), Ihre Art.-Nr. (BT-156), „Zeichnungs-Nr. X, Index Y“ (eine Zeile), GTIN (BT-157)
  2. Beschreibung (BT-154), weitere Merkmale „Name: Wert“ (BT-160/BT-161), Ursprungsland (BT-159)
  3. Bestellposition (BT-132), Kostenstelle (BT-133), Objekt (BT-128), Leistungszeitraum (BT-134/BT-135)
  4. Hinweis (BT-127)
  5. Listenpreis/Nachlass, Rabatt und Zuschlag der Position

  Lange Werte (z. B. sehr lange Artikelnummern) werden umbrochen, nie gekürzt. Die Beschriftungen folgen der
  Sprache der Rechnung (Deutsch/Englisch). Klassifizierung (BT-158), Steuer-Kategorie (BT-151) und
  Kostenkonto (BT-121) stehen nur im XML.
- Der CSV-Assistent schlägt `Kundenbezeichnung 1/2/3` von selbst vor, Zeichnungsnummer und Index nur bei genau
  passendem Spaltennamen.

Beispiel: `beispiele/variante-k_kundenbezeichnung_erp.csv` mit `beispiele/profil-variante-k.yaml`.
Rechnungsnummer prüfen und Dateinamen festlegen: siehe [Handbuch](handbuch.md#dateiname-und-rechnungsnummer-ab-095).

## Steuerfälle und Fremdwährung (ab 0.9.7)

Alles freiwillig; ohne diese Spalten bleibt es bei Regelbesteuerung in EUR.

| Feld im Profil | Spalte (Beispiel) | Wirkung |
|---|---|---|
| `steuer` (Position) | `Steuer` | neben Sätzen auch Kennzeichen; im Mapping je Wert ein Fall: `AE` (Reverse Charge), `K` (igL), `G` (Ausfuhr), `O` (nicht steuerbar), `KU` (§ 19) oder `{BT-151: S, BT-152: 19}` |
| `steuerhinweis` | `Steuerhinweis` | Pflichthinweis auf der Rechnung (BT-120); fehlt er, gilt der Standardtext des Falls |
| `BT-48` | `USt-IdNr Kunde` | USt-IdNr. des Käufers (Pflicht bei igL, empfohlen bei Reverse Charge) |
| `BT-47` | `Register Kunde` | Registernummer des Käufers |
| `BT-55`, `BT-80` | `Land`, `Lieferland` | ISO-Code oder Ländername („Österreich“); Lieferland nur, wenn anders als das Käuferland |
| `BT-5` | `Waehrung` | Rechnungswährung (`EUR`, `USD`, auch `$`); Standard EUR |
| `kurs`, `kursdatum` | `Kurs`, `Kursdatum` | Kurs „1 EUR = x Fremdwährung“ und sein Stand |
| `BT-111` | `USt EUR` | Umsatzsteuer in EUR, wenn die Warenwirtschaft sie selbst liefert |

- Bei Fremdwährung muss **Kurs oder USt in EUR** in den Daten stehen, sonst „Zu prüfen“. Fakturafalter ruft keinen
  Kurs ab.
- Kleinunternehmer stellst du am **Absender** ein (Einstellungen → Absender), nicht in der CSV. Die Steuerspalte
  darf dann fehlen oder `0` enthalten; ein Satz über 0 % hält die Rechnung an.
- Der CSV-Assistent erkennt Kennzeichen wie `RC`, `13b`, `igL`, `EX`, `§19` und schlägt den Fall vor.

Beispiele: `beispiele/variante-s_steuerfaelle.csv` mit `beispiele/profil-variante-s.yaml` (Reverse Charge, igL nach
Österreich, Ausfuhr in die Schweiz, nicht steuerbar in USD, 19 % in USD mit Kurs, gemischt) und
`beispiele/variante-u_kleinunternehmer.csv` (Absender mit Schalter Kleinunternehmer).

## XML-Eingang (XRechnung/ZUGFeRD, CII und UBL)

XML-Dateien liest Fakturafalter mit allen Feldern nach EN 16931: Rechnungen und Gutschriften (UBL `Invoice`
und `CreditNote`), Nachlässe und Zuschläge, Lastschrift, Anzahlung, Anhänge, Lieferung und Referenzen.
Für jedes Element, das nicht übernommen wird (z. B. aus dem Profil EXTENDED), steht im Protokoll eine
Warnung „XML-Element nicht übernommen: …“. Die Rechnung wird trotzdem erzeugt.
Ab 0.9.7 auch AE/K/G/O/E und Fremdwährung mit Steuerwährung EUR (BT-6/BT-111, Kurs aus einer Notiz
„Umrechnungskurs …“). Beispiele: `beispiele/xml-eingang/` (u. a. `XU-2026-0007_ubl_usd.xml`,
`XC-2026-0008_cii_usd.xml`).

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
