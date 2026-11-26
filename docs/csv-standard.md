# CSV-Exportspezifikation für Fakturafalter

**Spezifikation 1.3** · Stand 26.11.2026 (Europe/Berlin) · Grundlage App **0.9.9**

Diese Beschreibung richtet sich an Systemadmins und Entwickler einer
**Warenwirtschaft (ERP)**. Sie legt fest, wie ein Rechnungs-CSV aussehen soll,
damit Fakturafalter daraus eine geprüfte ZUGFeRD-Rechnung (EN 16931, PDF/A-3)
erzeugen kann. Sie ist eine Schnittstellenbeschreibung, keine Pflicht zum
Mitliefern einer Vorlagendatei.

Fakturafalter liest dieses Format **heute**, sobald ein CSV-Profil die Spalten
zuordnet (Einstellungen → Eingang & Vorlagen → „Neue CSV einrichten…“, oder ein
handgeschriebenes Profil). Ein **eingebautes Standardprofil**, das die hier
genannten Spaltennamen ohne Assistent erkennt, mit letzter Priorität greift und
unbekannte Spalten im Protokoll erwähnt, ist *verfügbar ab 0.9.9*. Vorlagen speicherst du unter Einstellungen → Eingang & Vorlagen → „CSV-Vorlage speichern…“.

### Statusmarker

Damit sich die Spezifikation beim Release nur an den Markern und der
Versionsgeschichte (§ 10) drehen muss:

| Marker | Bedeutung |
|---|---|
| ohne Marker bzw. **verfügbar ab 0.9.8.4** | Verhalten seit 0.9.8.4, soweit nicht anders markiert. |
| **verfügbar ab 0.9.9** | Eingebautes Standardprofil und strukturiertes Skonto in BT-20 (`#SKONTO#`). |
| **geplant, später** | Beschlossen, aber noch nicht in der aktuellen Lieferung. |
| **nicht vorgesehen** | Wird nicht umgesetzt, siehe § 8. |

Absenderdaten (Verkäufer, Steuernummer bzw. USt-IdNr., IBAN) stehen nicht in der
CSV, sondern in den Einstellungen. Die Rechnungsnummer vergibt weiterhin die
Warenwirtschaft.

---

## 1. Zweck und Zielgruppe

Die Warenwirtschaft soll Rechnungen so exportieren, dass Fakturafalter sie im
Hotfolder automatisch verarbeiten kann – ohne die Rechnungsdaten in der App
abzutippen. Adressaten sind Personen, die den Export implementieren oder
konfigurieren. Kleinere Betriebe, typischerweise mit regelmäßigem Belegaufkommen,
nutzen Fakturafalter als Alternative, wenn die Warenwirtschaft selbst kein
ZUGFeRD erzeugt.

---

## 2. Dateiformat

| Eigenschaft | Vorgabe | Verhalten (*verfügbar ab 0.9.8.4*, Abweichungen markiert) |
|---|---|---|
| Kodierung | **UTF-8 mit BOM** | Ohne BOM wird gültiges UTF-8 ebenfalls gelesen. Schlägt UTF-8 fehl, versucht die Automatik Windows-1252. Andere Kodierungen (z. B. CP1252 fest) sind per Profil möglich, gehören aber nicht zu diesem Standard. |
| Trennzeichen | **Semikolon** (`;`) | Ein Profil kann Komma, Tabulator oder `\|` festlegen oder automatisch erkennen. Für diesen Standard fest Semikolon verwenden. |
| Textbegrenzer | `"` | Feld, das Semikolon, Anführungszeichen oder Zeilenumbruch enthält, in Anführungszeichen setzen; ein `"` im Wert als `""`. |
| Zeilenende | `LF` oder `CRLF` | Beides wird gelesen. |
| Kopfzeile | **Pflicht**, erste Zeile = genaue Spaltennamen | Ohne Kopfzeile nur mit abweichendem Profil. Spaltennamen ohne führende/trailing Leerzeichen (die App trimmt sie). |
| Dezimaltrennzeichen | **Komma** (`149,00`, `1234,50`) | |
| Tausenderpunkt | optional `1.234,50` | Wird nur gelesen, wenn das Profil `zahlen.tausender: "."` setzt (der Assistent tut das typischerweise bei DezimalKomma). Ohne diese Einstellung wird `1.234,50` nicht als Zahl erkannt (*verfügbar ab 0.9.9:* das Standardprofil setzt den Tausenderpunkt). Empfehlung an den Export: Beträge **ohne** Tausendergruppierung schreiben, das ist eindeutig. |
| Datum | **`TT.MM.JJJJ`** (`02.11.2026`) | Andere Formate nur mit abweichendem Profil. |
| Leere Zelle | kein Wert | Nur Leerzeichen gilt als leer. Bei **Menge** und **Einzelpreis** gelten außerdem `0`, `0,00` und `0.0` als leer (keine Position). |
| Dateiname | Extension `.csv`, kein führender Punkt oder `~` | Dateien, deren Name mit `.` oder `~` beginnt oder auf `.tmp`, `.part` bzw. `.crdownload` endet, **werden ignoriert**. Groß/Kleinschreibung der Endung ist egal. Ein festes Namensmuster ist nicht vorgeschrieben; sinnvoll z. B. `RE-2026-1001.csv` oder eine Sammeldatei `rechnungen-2026-11-26.csv`. |
| Rechnungen je Datei | **eine oder mehrere** | Im Standardaufbau (eine Zeile je Position) bilden alle Zeilen mit derselben Rechnungsnummer eine Rechnung. Der Blockmodus (eine Datei = eine Rechnung, optionale Marker, freie Felder je Block, Textzeilen wie hier) ist ein **anderer, optionaler Eingang** (*verfügbar ab 0.9.9*), nicht Bestandteil dieses Export-Standards. Wer neu exportiert, liefert weiter eine Zeile je Position. Einzelheiten: [csv-format.md](csv-format.md#blöcke-mit-eigener-kopfzeile-ab-098-überarbeitet-ab-099). |

### Hotfolder (Eingangsordner)

Fakturafalter überwacht den Ordner `Eingang`. Eine Datei wird erst verarbeitet,
wenn **Größe und Änderungszeit** für `stabil_sekunden` (Standard **2 Sekunden**)
unverändert bleiben, die Datei größer als 0 Byte ist und sich zum Lesen öffnen
lässt (unter Windows schlägt das fehl, solange der Exporter die Datei noch offen
hält).

**Empfehlung:** zuerst vollständig nach `….csv.tmp` schreiben und anschließend
in `….csv` umbenennen. Dateien mit der Endung `.tmp` werden während des
Schreibens ignoriert; nach dem Umbenennen wartet die App die Stabilitätszeit ab.
Nicht die fertige Datei stückweise direkt als `.csv` wachsen lassen, ohne sie
am Ende zu schließen.

Ist zusätzlich „PDF der Rechnung verwenden“ aktiv, wartet die App auf eine
PDF mit **gleichem Dateinamen ohne Endung** (z. B. `RE-2026-1001.csv` und
`RE-2026-1001.pdf`), höchstens `gegenstueck_minuten` (Standard 10). Nach der
Verarbeitung wandert die Quelle nach `Erledigt`, die ZUGFeRD-PDF nach `Ausgang`.

---

## 3. Satzaufbau

- Genau **eine Datenzeile je Rechnungsposition**.
- **Kopffelder** (Rechnungsnummer, Datum, Kunde, …) stehen in **jeder** Zeile
  derselben Rechnung, auch in Kommentarzeilen, und müssen **identisch** sein.
- Gruppierung: Spalte `Rechnungsnummer`. Fehlt sie in einer Zeile, landet die
  Zeile in einer namenlosen Gruppe und die Rechnung ist unvollständig.
- **Widerspruch in Kopffeldern:** Ein mit dem Assistenten erzeugtes Profil
  prüft heute nur **Rechnungsdatum** und **Kundennummer**. Weichen sie innerhalb
  der Rechnung ab, geht die Datei nach „Zu prüfen“. Andere Kopffelder werden
  aus der **ersten** Zeile der Rechnung genommen, spätere Abweichungen bleiben
  ohne Hinweis. *verfügbar ab 0.9.9:* das Standardprofil prüft alle wiederholten
  Kopffelder der Pflicht- und Beleggruppe.
- **Kommentarzeile:** Menge und Einzelpreis leer (oder 0), aber Text in
  `Bezeichnung`. Text *vor* der ersten Position wird Rechnungs-Hinweis
  (BT-22); Text *unter* einer Position wird Artikelbeschreibung (BT-154).
  Das ist der Standard; ein Profil kann das umstellen.
- **Gewollte Leerzeile** auf der Sichtseite: in `Bezeichnung` den Platzhalter
  `#LEER` (anpassbar im Profil). Vollständig leere Zeilen werden übersprungen
  und erscheinen nicht auf der PDF.
- **Preis ohne Menge:** Standard „Zu prüfen“. Ein Profil kann Menge 1 setzen
  oder die Zeile als Kommentar behandeln.
- **Spaltenreihenfolge:** empfohlen wie in Abschnitt 4 (Pflichtspalten vorn).
  Die App ordnet über den Namen, nicht über die Position. Unbenutzte optionale
  Spalten darf der Export weglassen.
- *verfügbar ab 0.9.9:* unbekannte Spaltennamen werden weiterhin nicht gelesen, künftig
  aber mit einem **Hinweis im Protokoll** (kein Prüffall) vermerkt. Heute
  werden sie still ignoriert.

---

## 4. Feldreferenz

Pflicht: **ja** = immer nötig für eine gültige Rechnung. **bed.** = nur in
bestimmten Fällen. **opt.** = darf fehlen oder leer sein.

Typen: *Text* (keine Längenprüfung in der App; die nachgelagerte Prüfung mit
Mustang/KoSIT kann zu lange oder unzulässige Werte ablehnen), *Datum*
(`TT.MM.JJJJ`), *Zahl* (DezimalKomma), *Tage* (ganze Zahl, optional mit
„Tage“/„Tagen“), *Prozent* (Zahl, optional mit `%`).

### 4.1 Pflichtspalten (stehen vorn)

| Spaltenname | BT | Pflicht | Typ | Beispiel | Wenn die Spalte fehlt |
|---|---|---|---|---|---|
| Rechnungsnummer | BT-1 | ja | Text, eindeutig, von der Warenwirtschaft vergeben | `RE-2026-1001` | Zu prüfen |
| Rechnungsdatum | BT-2 | ja | Datum, nicht in der Zukunft | `02.11.2026` | Zu prüfen |
| Leistungsdatum | BT-72 | bed. | Datum | `31.10.2026` | Alternativ `Leistung von`/`Leistung bis` (BT-73/74) oder Leistungsmonat (`10/2026`). Mindestens eines ist Pflicht (§ 14 UStG). |
| Kundennummer | — | bed. | Text, Schlüssel zum Kundenstamm | `K-1001` | Dann die Käuferspalten (Name, Anschrift) liefern; sonst Zu prüfen. Die Nummer wird zur Käuferkennung (BT-46). |
| Bezeichnung | BT-153 | ja | Text | `Bürostuhl Modell Münster` | Zu prüfen. In Kommentarzeilen steht hier der Text. |
| Menge | BT-129 | ja | Zahl, in der XML bis 4 Nachkommastellen | `2` / `1,5` | Zusammen mit leerem Preis: Kommentar- oder Leerzeile. Nur Preis ohne Menge: siehe § 3. |
| Einheit | BT-130 | ja | Klartext aus der Einheitenliste (§ 5) | `Stück` | Zu prüfen. Profiloption „Fehlende Einheit = Stück“ (ab 0.9.8.3) setzt H87 und schreibt einen Hinweis ins Protokoll, kein Prüffall. |
| Einzelpreis | BT-146 | ja | Zahl, Netto je Preiseinheit, nicht negativ | `149,00` | Zu prüfen (bzw. Kommentar, siehe Menge). |
| Steuersatz | BT-151/152 | ja | Satz oder Steuerfall, siehe § 5 | `19 %` | Zu prüfen (kein stilles 19 %). |

### 4.2 Beleg

| Spaltenname | BT | Pflicht | Typ / Werte | Beispiel | Wenn fehlt |
|---|---|---|---|---|---|
| Belegart | BT-3 | opt. | siehe § 5 | `Rechnung` | 380 (Rechnung) |
| Währung | BT-5 | opt. | ISO 4217 | `EUR` | EUR |
| Leistung von | BT-73 | bed. | Datum | `01.10.2026` | nur ohne Leistungsdatum nötig |
| Leistung bis | BT-74 | bed. | Datum | `31.10.2026` | wie vor |
| Bestellnummer | BT-13 | opt. | Text | `AB-44019` | leer |
| Leitweg-ID | BT-10 | bed. | Leitweg-ID (Prüfziffer Mod 97-10, wird geprüft, wenn der Wert wie eine Leitweg-ID aussieht) | | Kundenstamm `leitweg_id_bt10`; bei XRechnung Fallback: Kundennummer |
| Summe netto | BT-109 | opt. | Zahl, nur Kontrolle | `363,00` | keine Gegenprüfung |
| Summe USt | BT-110 | opt. | Zahl, nur Kontrolle | `68,97` | keine Gegenprüfung |
| Summe brutto | BT-112 | opt. | Zahl, nur Kontrolle | `431,97` | keine Gegenprüfung |

### 4.3 Käufer

Reihenfolge: Zuerst der **Kundenstamm** zur `Kundennummer`. **Gefüllte
Käuferspalten in der CSV haben Vorrang** (Feld für Feld). Eine leere Zelle
ändert den Stammwert nicht. Ohne treffende Nummer und ohne Namen: Zu prüfen.

| Spaltenname | BT | Pflicht | Typ | Beispiel | Wenn fehlt |
|---|---|---|---|---|---|
| Kundenname | BT-44 | bed. | Text | `Beispiel Handel GmbH` | Stamm `name` |
| Kundenbezeichnung 2 | — | opt. | Text, zweite Namenszeile; in der XML mit Leerzeichen an BT-44 gehängt | | leer |
| Kundenbezeichnung 3 | — | opt. | wie Zeile 2 | | leer |
| Straße | BT-50 | bed. | Text | `Beispielweg 5` | Stamm `strasse` |
| Adresszusatz | BT-51 | opt. | Text, Adresszeile 2 | `Gebäude C` | Stamm `zusatz` |
| PLZ | BT-53 | bed. | Text; in DE 5 Ziffern | `12345` | Stamm `plz` |
| Ort | BT-52 | bed. | Text | `Musterstadt` | Stamm `ort` |
| Land | BT-55 | bed. | ISO 3166-1 alpha-2, häufige Namen werden übersetzt (`Österreich` → `AT`) | `DE` | Stamm, sonst DE |
| Kunde-USt-IdNr. | BT-48 | bed. | USt-IdNr., Format wird geprüft | `DE000000003` | Stamm `ust_id`. Pflicht u. a. bei igL und Reverse Charge. |
| E-Rechnungsadresse | BT-49 | opt. | E-Mail (Schema in der XML immer `EM`) | `rechnung@beispiel-handel.example` | Stamm `elektr_adresse_bt49` |
| Handelsregister | BT-47 | opt. | Text | `HRB 12345` | Stamm `register` |

### 4.4 Lieferung (nur bei abweichender Lieferanschrift)

| Spaltenname | BT | Pflicht | Wenn fehlt |
|---|---|---|---|
| Liefername | BT-70 | opt. | keine eigene Lieferanschrift; bei innergemeinschaftlicher Lieferung übernimmt die App die Käuferanschrift |
| Lieferstraße | BT-75 | opt. | wie vor |
| Liefer-PLZ | BT-78 | bed., wenn Lieferanschrift | wenn eine Lieferanschrift da ist: Ort, PLZ und Land nötig |
| Lieferort | BT-77 | bed., wenn Lieferanschrift | |
| Lieferland | BT-80 | bed., wenn Lieferanschrift oder igL/Ausfuhr | ISO-Code bzw. Name wie beim Käufer |

### 4.5 Weitere Positionsangaben

| Spaltenname | BT | Pflicht | Typ / Hinweis | Wenn fehlt |
|---|---|---|---|---|
| Positionsnummer | BT-126 | opt. | Text, in der XML eindeutig | 1, 2, 3 … |
| Artikelnummer | BT-155 | opt. | Nummer des Verkäufers | leer |
| Preiseinheit | BT-149 | opt. | Zahl > 0, „Preis gilt je …“ | 1 |
| Positionsbetrag | — | opt. | Zahl, Kontrolle gegen BT-131 (Toleranz 0,01) | App rechnet |
| Positionstext | BT-127 | opt. | Notiz zur Zeile | leer |
| Artikelbeschreibung | BT-154 | opt. | Langtext; Kommentarzeilen darunter werden hier ergänzt | leer bzw. Kommentar |
| Kundenartikelnummer | BT-156 | opt. | | leer |
| GTIN | BT-157 | opt. | Schema standardmäßig 0160; Prüfziffer nur Warnung | leer |
| Zeichnungsnummer | BT-160/161 | opt. | wird als Merkmal „Zeichnungsnummer“ geschrieben | leer |
| Index | BT-160/161 | opt. | Merkmal „Index“ | leer |
| Bestellposition | BT-132 | opt. | | leer |
| Ursprungsland | BT-159 | opt. | ISO-Ländercode | leer |
| Warengruppe | BT-158 | opt. | Code, Schema-Standard ZZZ | leer |
| Objektkennung Position | BT-128 | opt. | | leer |
| Buchungsreferenz Position | BT-133 | opt. | z. B. Kostenstelle der Zeile | leer |
| Leistung von Position | BT-134 | opt. | Datum, wenn abweichend vom Beleg | leer |
| Leistung bis Position | BT-135 | opt. | Datum | leer |
| Merkmal | BT-160 | opt. | Name, zusammen mit Merkmalwert | leer |
| Merkmalwert | BT-161 | opt. | | leer |
| Rabatt Prozent | BT-138 | opt. | Prozent; ohne Betrag wird aus dem Positionsnetto gerechnet | kein Positionsrabatt |
| Rabatt Betrag | BT-136 | opt. | Zahl | |
| Rabattgrund | BT-139 | opt. | Text, Code in der XML typisch 95 | „Rabatt“ |
| Zuschlag Prozent | BT-143 | opt. | | kein Positionszuschlag |
| Zuschlag Betrag | BT-141 | opt. | | |
| Zuschlaggrund Position | BT-144 | opt. | | „Zuschlag“ |
| Bruttopreis | BT-148 | opt. | Listenpreis vor Nachlass | nur Nettoeinzelpreis |
| Preisnachlass | BT-147 | opt. | Nachlass je Einheit (BT-146 = BT-148 − BT-147) | |

### 4.6 Zahlung und Skonto

Das Fälligkeitsdatum (BT-9) ist das **Netto-Ziel** (Rechnungsdatum + Nettotage).
Es wird nicht durch ein Skontodatum ersetzt. Bei Gutschrift (381) schreibt die
App keinen Fälligkeitstermin, sondern den Satz „Der Betrag wird Ihnen
gutgeschrieben.“

EN 16931 hat kein eigenes Skontofeld. XRechnung 3.0 übermittelt Skonto
maschinenlesbar in den Zahlungsbedingungen (BT-20) über die Konvention
`#SKONTO#` (Regel BR-DE-18, bei XRechnung fatal).

Bis 0.9.8.4 flossen die Spalten `Skonto` und `Zahlungsziel mit Skonto` nur in
einen **deutschen Klartext** in BT-20 (zusammen mit dem Netto-Satz aus
`Zahlungsziel`); es entstand keine `#SKONTO#`-Zeile.

*verfügbar ab 0.9.9:* Sobald Satz *und* Tage einer Stufe gesetzt sind, schreibt
die App in BT-20 zuerst die Konventionszeilen, danach denselben Klartext wie
bisher. Der Sichtteil der PDF zeigt nur den Klartext, nicht die Hash-Zeilen.
Die Ausgabe wird mit Mustang (ZUGFeRD) und KoSIT (XRechnung, BR-DE-18) geprüft.
Die strukturierten Zeilen stehen auch im ZUGFeRD-XML, nicht nur in einer
optionalen XRechnung.

Syntax je Stufe (Großbuchstaben, kein Leerzeichen in der Zeile, die Zeile
beginnt und endet mit `#`, nach *jeder* Zeile ein XML-Zeilenumbruch, auch nach
der letzten):

```
#SKONTO#TAGE=10#PROZENT=2.00#
```

In der CSV bleibt das Dezimal**komma** (`2` oder `2,00`); in der Konventionszeile
steht der Dezimal**punkt** mit genau zwei Nachkommastellen (`2.00`). `TAGE` ist
eine ganze Zahl. `BASISBETRAG` nur, wenn die Spalte `Skonto-Basisbetrag`
gefüllt ist (wenn die Bemessung nicht der volle Zahlbetrag BT-115 ist), Format
in der XML wie Amount (`1500.00`).

Fiktives Beispiel, eine Stufe plus Klartext:

```
#SKONTO#TAGE=10#PROZENT=2.00#
2 % Skonto innerhalb von 10 Tagen (bis 10.12.2026), zahlbar innerhalb von 14 Tagen ohne Abzug (bis 14.12.2026).
```

Fehlt Satz oder Tage einer Stufe, entsteht für diese Stufe keine
Konventionszeile. Bei Gutschrift (381) entfällt strukturiertes Skonto
typischerweise (weiterhin der festgelegte Gutschrift-Satz). Der Klartext in
BT-20 darf **kein `#`** enthalten; die App setzt keines.

**Verzug und Mahnung** (*verfügbar ab 0.9.9*, nur Dokumentation und
Klartext, kein eigenes Feld): Es gibt **keine** zulässige Konvention `#VERZUG#`
(in XRechnung 3.0.2 würde sie BR-DE-18 fatal verletzen). Einen Verzugs- oder
Mahnhinweis als normalen Satz ohne `#` in `Bemerkung` (BT-22) schreiben.

| Spaltenname | BT | Pflicht | Typ / Werte | Wenn fehlt | Status |
|---|---|---|---|---|---|
| Zahlungsziel | BT-9 / BT-20 | opt. | Tage netto | Kundenstamm `zahlungsziel_tage`, sonst typisch 14 Tage aus der Konfiguration | verfügbar ab 0.9.8.4 |
| Skonto | BT-20 | opt. | Prozent (erste Stufe) | kein Skonto | verfügbar ab 0.9.8.4 (Klartext), ab 0.9.9 zusätzlich `#SKONTO#`-Zeile |
| Zahlungsziel mit Skonto | BT-20 | opt. | Tage (erste Stufe) | | wie `Skonto` |
| Skonto-Basisbetrag | BT-20 | opt. | Zahl, nur wenn nicht der volle BT-115 gilt | Segment `BASISBETRAG` entfällt | *verfügbar ab 0.9.9* |
| Skonto 2 | BT-20 | opt. | Prozent der zweiten Stufe | keine zweite Konventionszeile | *verfügbar ab 0.9.9* |
| Zahlungsziel mit Skonto 2 | BT-20 | opt. | Tage der zweiten Stufe | | *verfügbar ab 0.9.9* |
| Skonto-Basisbetrag 2 | BT-20 | opt. | wie `Skonto-Basisbetrag`, für Stufe 2 | Segment entfällt | *verfügbar ab 0.9.9* |
| Zahlungsart | BT-81 | opt. | siehe § 5 | 58 (SEPA-Überweisung); eine Mandatsreferenz ohne Zahlungsart setzt 59 | verfügbar ab 0.9.8.4 |
| Verwendungszweck | BT-83 | opt. | Text | Rechnungsnummer | verfügbar ab 0.9.8.4 |
| Mandatsreferenz | BT-89 | bed. bei Lastschrift | Text | Kundenstamm `mandat_bt89` | verfügbar ab 0.9.8.4 |
| Gläubiger-ID | BT-90 | bed. bei Lastschrift | Text | Absender | verfügbar ab 0.9.8.4 |
| Kunden-IBAN | BT-91 | bed. bei Lastschrift | IBAN, Prüfsumme wird geprüft | Kundenstamm `iban_bt91` | verfügbar ab 0.9.8.4 |
| Zahlungsempfänger | BT-59 | opt. | nur wenn abweichend vom Verkäufer | Verkäufer (IBAN bleibt die des Absenders) | verfügbar ab 0.9.8.4 |

### 4.7 Zu- und Abschläge auf die Rechnung

| Spaltenname | BT | Pflicht | Wenn fehlt |
|---|---|---|---|
| Belegrabatt Prozent | BT-94 | opt. | kein Belegrabatt (Code in der XML typisch 95) |
| Belegrabatt Betrag | BT-92 | opt. | |
| Belegrabattgrund | BT-97 | opt. | „Rabatt“ |
| Fracht | BT-99 | opt. | kein Zuschlag; Code typisch FC bei Fracht, sonst ABL |
| Zuschlag Prozent | BT-101 | opt. | im Assistenten-Katalog nicht enthalten, im Profil zuordenbar |
| Zuschlaggrund | BT-104 | opt. | „Zuschlag“ |
| Anzahlung | BT-113 | opt. | 0 (wird in der XML geschrieben) |

Statt eigener Spalten kann eine Positionszeile mit `Zeilenart` `Rabatt` oder
`Zuschlag` als Nachlass bzw. Zuschlag auf Belegebene gelesen werden.

### 4.8 Referenzen und Sonstiges

| Spaltenname | BT | Pflicht | Wenn fehlt |
|---|---|---|---|
| Auftragsnummer | BT-14 | opt. | leer |
| Projektnummer | BT-11 | opt. | leer |
| Vertragsnummer | BT-12 | opt. | leer |
| Lieferscheinnummer | BT-16 | opt. | leer |
| Wareneingang | BT-15 | opt. | leer |
| Vergabenummer | BT-17 | opt. | leer |
| Objektkennung | BT-18 | opt. | leer |
| Kostenstelle | BT-19 | opt. | leer |
| Bemerkung | BT-22 | opt. | zusätzlich möglich: Profil-Hinweise, Kommentar vor der ersten Position, bei Fremdwährung der Kurstext |
| Steuerhinweis | — | opt. | hilft, den Steuerfall zu erkennen, wenn der Satz allein nicht reicht |
| Kurs | — | bed. bei Fremdwährung | „1 EUR = x Rechnungswährung“; ohne Kurs und ohne `USt EUR` bei USt ≠ 0: Zu prüfen |
| Kursdatum | — | opt. | steht im Hinweistext, kein eigenes BT |
| USt EUR | BT-111 | bed. bei Fremdwährung | sonst aus USt ÷ Kurs gerechnet |
| Link auf Unterlage | BT-124 | opt. | URI, keine eingebettete Datei (*geplant, später:* eingebettete Anlagen über BT-125, siehe § 8) |
| Zeilenart | — | opt. | `Position`, `Rabatt`, `Zuschlag` (und Synonyme wie Nachlass, Fracht) | Position |
| Bezugsrechnung | BT-25 | bed. bei Gutschrift/Korrektur (381/384) | Zu prüfen, wenn sie fehlt |
| Bezugsdatum | BT-26 | opt. | leer. CII gibt nur **eine** Bezugsrechnung aus. |

---

## 5. Codelisten

### 5.1 Einheiten (BT-130)

In der CSV den **Klartext** schreiben, nicht den Rec-20-Code. Das Profil
übersetzt. Die folgende Liste entspricht der in der App hinterlegten Erkennung
(Auszug der üblichen Werte). **Stück wird als H87** geliefert, nicht als C62
(C62 erscheint auf der Sichtseite ebenfalls als „Stück“, ist aber nicht der
Standard). Unbekannte Einheiten: Zu prüfen, kein stilles C62. Wenn das Profil
`unbekannt: allgemein` setzt (Assistent), gelten dieselben Klartexte wie in der
PDF-Erkennung.

| Klartext in der CSV | Rec 20 |
|---|---|
| Stück, Stk, Stk., Stck, St. | H87 |
| Stunde, Stunden, Std, Std., h | HUR |
| m, Meter, lfm | MTR |
| m², m2, qm | MTK |
| m³, m3, cbm | MTQ |
| kg | KGM |
| g | GRM |
| t | TNE |
| l, Ltr | LTR |
| pauschal, pausch, Pauschale, psch | LS |
| Tag, Tage | DAY |
| Woche, Wochen | WEE |
| Monat | MON |
| Paar | PR |
| Set, Satz | SET |
| Rolle | XRO |
| Karton | XCT |
| Paket, Pkt, Pak | XPK |

### 5.2 Steuersatz und Steuerkategorie

Empfohlene Werte in der Spalte `Steuersatz` und die Zuordnung, die ein
Standard- bzw. Assistenten-Profil vornehmen soll. Befreiungsgrund (BT-120) und
Code (BT-121) setzt die App aus dem Steuerfall, sofern nicht anders angegeben.
Kategorien AE, K, G, O, E und Kleinunternehmer brauchen einen Befreiungsgrund
(sonst Zu prüfen).

| Wert in der CSV | Kategorie (BT-151/118) | Satz | BT-120 (Standardtext) | BT-121 |
|---|---|---|---|---|
| `19 %`, `19` | S | 19 | — | — |
| `7 %`, `7` | S | 7 | — | — |
| `0 %` / `steuerfrei` | E | 0 | Steuerfrei | — |
| `Reverse Charge`, `RC` | AE | 0 | Steuerschuldnerschaft des Leistungsempfängers | VATEX-EU-AE |
| `igL` | K | 0 | Steuerfreie innergemeinschaftliche Lieferung | VATEX-EU-IC |
| `Ausfuhr` | G | 0 | Steuerfreie Ausfuhrlieferung | VATEX-EU-G |
| `nicht steuerbar` | O | 0 (Satz entfällt in der XML) | Nicht im Inland steuerbare Leistung | VATEX-EU-O |
| `Kleinunternehmer` | E | 0 | Gemäß § 19 UStG wird keine Umsatzsteuer berechnet. | — |

Heute wirkt das nur, wenn das Profil den Wert zuordnet. Numerische Sätze
(`19`, `7,00 %`) erkennt der Assistent oft automatisch (`unbekannt: satz`).
Kurzformen wie `igL` oder `RC` müssen im Mapping stehen oder als
`steuerhinweis` mitgeliefert werden. Der Schalter „Kleinunternehmer“ am
Absender setzt alle Positionen auf E/0 % mit dem §-19-Text, unabhängig von der
Spalte.

Mischsätze in einer Rechnung sind zulässig (verschiedene Kategorien bzw. 19 und
7). Bei Reverse Charge braucht der Käufer in der Regel eine USt-IdNr. (im Inland
ersatzweise BT-47); bei igL USt-IdNr. von Verkäufer und Käufer sowie ein anderes
EU-Lieferland; bei Ausfuhr ein Drittland als Lieferland.

### 5.3 Belegart (BT-3, UNTDID 1001)

| Wert in der CSV | Code |
|---|---|
| Rechnung, RE, RG, Invoice, 380 | 380 |
| Gutschrift, GS, Credit Note, 381 | 381 |
| Korrektur, Rechnungskorrektur, KO, 384 | 384 |
| Anzahlung, Anzahlungsrechnung, AR, 386 | 386 |
| Teilrechnung, TR, 326 | 326 |
| Schlussrechnung | 380 |

Unbekannte Werte: Zu prüfen. Ohne Spalte: 380.

*verfügbar ab 0.9.8.4:* `Schlussrechnung` wird als 380 ausgegeben. Code 386
(Anzahlung) ist in EN 16931 zulässig; in einer XRechnung erzeugt er die
KoSIT-Warnung BR-DE-17.

*geplant, später:* die Baurechnungstypen 875 (Abschlag), 876 (Teilschluss) und
877 (Schluss) sowie ein dokumentiertes Muster für Schlussrechnungen mit
Anzahlung (BT-113 und Bezug BT-25).

### 5.4 Zahlungsart (BT-81, UNTDID 4461)

| Wert in der CSV | Code |
|---|---|
| Überweisung, SEPA-Überweisung, UE, 58 | 58 |
| 30 | 30 (ebenfalls Überweisung, IBAN Pflicht wie bei 58) |
| Lastschrift, SEPA-Lastschrift, Einzug, LS, 59 | 59 |
| 49 | 49 (Lastschrift) |
| Bar, Barzahlung, 10 | 10 |
| Karte, Kartenzahlung, EC, 48 | 48 |
| Kreditkarte, 54 | 54 |
| PayPal, 68 | 68 |
| Verrechnung, 97 | 97 |

Ohne Spalte: 58. Bei 30 und 58 ist die IBAN des Absenders Pflicht.

### 5.5 Land und Währung

- **Land:** ISO 3166-1 alpha-2 (`DE`, `AT`, `CH`, …). Häufige deutsche und
  englische Namen werden erkannt. Der Verkäufer muss in **Deutschland** sitzen;
  ein anderes Verkäuferland ist *nicht vorgesehen*.
- **Währung:** ISO 4217 (`EUR`, `USD`, …). Standard EUR. Bei einer anderen
  Währung muss die Umsatzsteuer zusätzlich in EUR stehen (Kurs und/oder Spalte
  `USt EUR`). Fakturafalter ruft keinen Kurs ab.

---

## 6. Berechnung

Fakturafalter **rechnet alle Summen selbst**. Werte der Warenwirtschaft in
`Summe netto`, `Summe USt`, `Summe brutto` oder `Positionsbetrag` dienen nur
der Gegenprüfung.

- Positionsbetrag (BT-131) = runden(Menge × Einzelpreis ÷ Preiseinheit) ±
  Positions-Zu-/Abschläge. Preiseinheit leer oder ≤ 0 zählt als 1.
- Rundung: kaufmännisch auf **0,01** (`ROUND_HALF_UP`).
- Steuer je Gruppe: runden(Basis × Satz / 100).
- Rechnungsnetto (BT-109) = Summe der Positionen − Belegrabatte + Belegzuschläge.
- Brutto (BT-112) = Netto + USt (BT-110).
- Zahlbetrag (BT-115) = Brutto − Anzahlung + Rundung (Rundung kommt nicht aus
  dieser CSV-Schnittstelle).
- **Kontrolltoleranz bei CSV:** Abweichung größer als **0,01** (ein Cent)
  gegenüber Positionsbetrag oder den Summenspalten → Zu prüfen. (Die Konstante
  „Summentoleranz 0,02“ gilt nur für den Vergleich mit einem **Druck-PDF**,
  nicht für CSV-Kontrollspalten.)
- Mengen und Einzelpreise dürfen in der Quelle mehr Nachkommastellen haben;
  in der XML wird der Preis auf 2, die Menge auf höchstens 4 Stellen geschrieben.
- Negative Einzelpreise werden als negative Menge übernommen (Hinweis). Bei
  Gutschrift 381 mit negativen Beträgen dreht die App die Vorzeichen auf positiv.

---

## 7. Validierung und Fehlerverhalten

Nach dem Einlesen prüft Fakturafalter Pflichtangaben und Plausibilität und
danach lokal mit **Mustang** (PDF/A-3 und ZUGFeRD) und **KoSIT** (EN 16931 /
XRechnung). Unklares oder Ungültiges geht **nicht still** in den Ausgang.

**Zu prüfen** (Auswahl, die Datei bleibt im Ordner `Pruefen`):

- Pflichtfeld fehlt oder ist unlesbar (Nummer, Datum, Bezeichnung, Menge,
  Einheit, Einzelpreis, Leistungsdatum bzw. -zeitraum, Käufername).
- Kopfwiderpruch bei den im Profil genannten Feldern (heute typisch Datum und
  Kundennummer).
- Kontrollbetrag weicht um mehr als 0,01 ab.
- Einheit oder Steuersatz nicht zugeordnet.
- Preis ohne Menge (Standardoption).
- Ungültige IBAN, USt-IdNr., Leitweg-ID (wenn sie wie eine aussieht).
- Gutschrift/Korrektur ohne Bezugsrechnung; Lastschrift ohne Mandat, Gläubiger-ID
  oder Kunden-IBAN.
- Steuerfall ohne nötigen Befreiungsgrund oder ohne die dazu gehörenden
  Parteien-/Länderangaben.
- Fremdwährung mit USt, aber ohne Kurs und ohne USt in EUR.
- Verkäufer nicht in DE.

**Hinweis** (Rechnung kann trotzdem raus, je nach Stufe auch nur Information):

- Einheit wurde als Stück angenommen (`einheit_fehlt_stueck`).
- GTIN-Prüfziffer ungültig (Warnung).
- Lücke in der Rechnungsnummernfolge (Warnung, erlaubt).
- Gutschrift mit negativen Beträgen umgedreht; negativer Preis als negative Menge.
- Gläubiger-ID aus dem Absender ergänzt.
- *verfügbar ab 0.9.9:* unbekannte CSV-Spalte ignoriert (Hinweis im Protokoll, kein Prüffall).

**Fehler:** Validierung durch Mustang oder KoSIT nicht bestanden, oder ein
unbehebbarer Lesefehler (leere Datei, Pflichtspalte laut Profil fehlt in der
Kopfzeile). Zielordner `Fehler`.

---

## 8. Geplant und nicht vorgesehen

Strukturiertes Skonto (§ 4.6) und das eingebaute Standardprofil sind
*verfügbar ab 0.9.9*.

### 8.1 Geplant, später

- **Abschlags-, Teilschluss- und Schlussrechnung:** BT-3-Codes 875, 876, 877
  und ein Muster für den Bezug auf Anzahlungen (BT-113, BT-25). Heute sind 326
  und 386 gemappt, `Schlussrechnung` ergibt 380 (siehe § 5.3).
- **Eingebettete Anlagen** (BG-24, BT-125) über diese CSV-Schnittstelle. Heute
  nur die URI in `Link auf Unterlage` (BT-124); Einbetten ist über den
  XML-Import möglich.

### 8.2 Nicht vorgesehen

- **Verkäufer außerhalb Deutschlands** (BT-40 ≠ DE).
- **Positionsgruppen bzw. Zwischensummen** im EN-16931-Profil (nur ZUGFeRD
  EXTENDED). Zwischenzeilen auf der Sichtseite über Kommentarzeilen (§ 3).
- **Eigenes Lieferscheindatum:** EN 16931 hat im Kernprofil kein solches Feld.
  `Lieferscheinnummer` (BT-16) und Leistungsdatum (BT-72) verwenden.
- **Strukturierte Verzugsangabe `#VERZUG#`** in BT-20 (in XRechnung 3.0.2
  unzulässig, siehe § 4.6).
- **BT-7 / BT-8** (Datum bzw. Code der Steuerfälligkeit) – nicht im Modell.
- **Mehrere Ursprungsrechnungen** (BG-3) – CII gibt nur die erste aus.
- **Elektronische Adresse** nur mit Schema `EM` (E-Mail); andere Schemas
  (z. B. 0204, 0088, 9930) gehen beim Schreiben verloren.
- **Steuervertreter (BG-11)** nicht über diese CSV-Schnittstelle (wohl über
  XML-Import).
- Handelsname, Verkäuferkennung, Adresszeile 3 und Region sowie Zahlungskarte
  und Rundungsbetrag: nicht über die CSV-Pflicht- oder Assistentenspalten.
- Andere XML-Formate der Warenwirtschaft (DATEV, Lexware usw.) werden nicht
  als Eingang gelesen – nur CII/UBL (ZUGFeRD/XRechnung) oder eben CSV in diesem
  Format.

---

## 9. Checkliste für Entwickler

1. Datei als **UTF-8 mit BOM**, Trennung **Semikolon**, erste Zeile die
   Spaltennamen genau wie in § 4.
2. Datum `TT.MM.JJJJ`, Beträge mit **Dezimalkomma**, möglichst **ohne**
   Tausenderpunkt.
3. **Eine Zeile je Position**, Kopffelder in jeder Zeile gleich, auch bei
   Kommentaren. Mehrere Rechnungen in einer Datei über die Rechnungsnummer
   unterscheiden.
4. Die neun Pflichtspalten sind immer vorhanden. `Kundennummer` zeigt in einen
   gepflegten Kundenstamm, sonst Käuferspalten mitliefern.
5. `Einheit` als Klartext der Liste in § 5.1 (`Stück` → H87, `Stunde` → HUR,
   `pauschal` → LS).
6. `Steuersatz` als `19 %` / `7 %` oder benannter Fall (`igL`, `Reverse Charge`,
   …), nicht als interner Steuerschlüssel ohne Mapping.
7. Kommentar: Text in `Bezeichnung`, Menge und Preis leer – nicht `0` als
   Menge einer echten Position verwenden, wenn keine Position gemeint ist.
8. Semikolon oder Zeilenumbruch im Textfeld in Anführungszeichen setzen.
9. In den Eingangsordner **erst nach vollständigem Schreiben** legen
   (z. B. `*.csv.tmp` schreiben, dann in `*.csv` umbenennen).
10. Prüfung: in Fakturafalter **„Profil testen…“** (Einstellungen → Eingang &
    Vorlagen), anschließend eine fiktive Testdatei durchlaufen lassen und die
    ZUGFeRD-PDF (Mustang/KoSIT im Paket) kontrollieren. Im Testdaten-ZIP liegen
    weitere fiktive Beispiele.

### Minimalbeispiel

Nur die neun Pflichtspalten, zwei Rechnungen, eine Kommentarzeile. Datei:
[`fakturafalter-standard-minimal.csv`](../beispiele/fakturafalter-standard-minimal.csv)
(fiktiv, UTF-8 mit BOM).

```csv
Rechnungsnummer;Rechnungsdatum;Leistungsdatum;Kundennummer;Bezeichnung;Menge;Einheit;Einzelpreis;Steuersatz
RE-2026-1001;02.11.2026;31.10.2026;K-1001;Bürostuhl Modell Münster;2;Stück;149,00;19 %
RE-2026-1001;02.11.2026;31.10.2026;K-1001;Lieferung frei Haus;;;;
RE-2026-1001;02.11.2026;31.10.2026;K-1001;Montage vor Ort;1;Stunde;65,00;19 %
RE-2026-1002;03.11.2026;03.11.2026;K-1001;Beratung Einrichtung;3;Stunde;90,00;19 %
RE-2026-1002;03.11.2026;03.11.2026;K-1001;Dokumentation;1;Stück;120,00;19 %
```

Voraussetzung: Absender in den Einstellungen und Kundenstamm-Eintrag `K-1001`.

### Vollbeispiel

Dieselben Rechnungen mit den in § 4 genannten optionalen Spalten, einschließlich
der Skonto-Spalten *verfügbar ab 0.9.9* (leere Zellen und weglassbare Spalten
sind zulässig). Datei:
[`fakturafalter-standard-voll.csv`](../beispiele/fakturafalter-standard-voll.csv).

Die Vollvorlage enthält `Skonto`, `Zahlungsziel mit Skonto`, `Skonto-Basisbetrag`
sowie die zweite Stufe (`Skonto 2`, `Zahlungsziel mit Skonto 2`,
`Skonto-Basisbetrag 2`).

Die ersten Pflichtfelder der ersten Positionszeile:

```csv
Rechnungsnummer;Rechnungsdatum;Leistungsdatum;Kundennummer;Bezeichnung;Menge;Einheit;Einzelpreis;Steuersatz;Belegart;…
RE-2026-1001;02.11.2026;31.10.2026;K-1001;Bürostuhl Modell Münster;2;Stück;149,00;19 %;Rechnung;…
```

---

## 10. Pflege dieser Spezifikation

Diese Spezifikation liegt im Repository als `docs/csv-standard.md`.

**Regel:** Jede Änderung am CSV-Verhalten oder an den Feldern wird im **selben
Release** an allen folgenden Stellen nachgezogen:

- diese Spezifikation (`docs/csv-standard.md`)
- `docs/csv-format.md`
- das Handbuch (`docs/handbuch.md`)
- die `README.md`

Dabei die **Statusmarker** umstellen (zum Beispiel *geplant (ab
Skonto-Release)* → *verfügbar ab 0.9.x*), die Versionsnummer dieser
Spezifikation erhöhen und die Änderung in der Liste unten eintragen.

### Versionsgeschichte

| Version | Datum (Europe/Berlin) | Änderung |
|---|---|---|
| 1.0 | 26.11.2026 | Erste Fassung, gilt für App 0.9.8.4. |
| 1.1 | 26.11.2026 | Statusmarker vereinheitlicht. Strukturiertes Skonto (`#SKONTO#` in BT-20, inkl. Basisbetrag und Stufe 2) und Verzug als Klartext: *verfügbar ab 0.9.9*. Abschnitt 8 aufgeteilt in geplant / nicht vorgesehen. Abschlags-/Schlussrechnung (875/876/877) und eingebettete Anlagen: *geplant, später*. Dieser Pflegeabschnitt ergänzt. |
| 1.2 | 26.11.2026 | Eingebautes Standardprofil und strukturiertes Skonto (`#SKONTO#` in BT-20, inkl. Basisbetrag und Stufe 2) sowie Verzug nur als Klartext in `Bemerkung`: *verfügbar ab 0.9.9*. Vollvorlage um die neuen Skonto-Spalten ergänzt. Diese Datei liegt jetzt im Repository.
| 1.3 | 26.11.2026 | Optionaler Block-Eingang (freie Felder je Block, optionale Marker, Textzeilen einschließlich `zwischen` und `0` / `0,00`) als *verfügbar ab 0.9.9* beschrieben. Der Export-Standard bleibt eine Zeile je Position.
