# Fakturafalter – Details

Die kurze Übersicht mit Bildern steht in der [README](../README.md).
Die Anleitung für den Alltag (CSV und XML zuerst, Nur PDF weiter unten) steht im [Handbuch](handbuch.md).

Alle Beispieldaten in `beispiele/` sind erfunden.

## Installation (Entwicklung)
    python -m venv .venv && .venv/bin/pip install -e .[gui,test]

## Nutzung
    fakturafalter                        # Oberfläche (Standard, falls PySide6 installiert)
    fakturafalter --minimiert            # Oberfläche, startet im Tray / minimiert
    fakturafalter --headless             # ohne Oberfläche: Eingangsordner überwachen
    fakturafalter --einmal               # Eingang einmal abarbeiten und beenden
    fakturafalter -c beispiele/konfiguration.yaml --einmal
    fakturafalter --einmal --ohne-pruefung       # ohne Prüfung nach Erstellung (nur dieser Aufruf)
    fakturafalter --pruefe datei.pdf datei.xml   # vorhandene Dateien lokal prüfen

Ohne `--config` wird gesucht: `./konfiguration.yaml`, dann der portable Ordner neben
dem Programm, dann der Benutzerordner (beim ersten Start mit Beispielwerten angelegt).

Ein **Arbeitsordner**, die Unterordner legt Fakturafalter selbst an: `Eingang` → `Ausgang` (Ergebnis +
`protokoll.tsv`), Quellen nach `Erledigt`, `Pruefen` (Abweichung CSV ↔ Druck-PDF, Freigabe/Verwerfen in der
Oberfläche; `Pruefen/Anlernen` = PDFs, die auf den Anlern-Assistenten warten) oder `Fehler`.
Wer Ordner getrennt braucht (z. B. Ausgang auf einem Netzlaufwerk): Einstellungen → Ordner →
„Ordner einzeln festlegen“. Ältere Konfigurationen mit einzelnen Ordnern laufen unverändert weiter.

## Eingabevarianten

Der empfohlene Weg ist **CSV** oder **XML**. **Nur PDF** bleibt unterstützt, ist aber nicht empfohlen
(Erkennung kann fehlgehen, Kontrolle nötig); siehe [Handbuch](handbuch.md#nur-pdf-unterstutzt-aber-nicht-empfohlen).

| Eingangsformat (Einstellungen → Eingang & Vorlagen) | Was im Eingang liegt | Schritte der Verarbeitung |
|---|---|---|
| **CSV** | CSV/Text-Export | Lesen → Einlesen (CSV) → XML erzeugen → Sichtseite neu → Prüfen → Ablegen |
| **XML (ZUGFeRD / XRechnung)** | ZUGFeRD- oder XRechnung-XML (CII oder UBL) | Lesen → Einlesen (XML) → XML übernehmen → Sichtseite neu → Prüfen → Ablegen |
| **CSV oder XML plus Haken „Zusätzlich das PDF der Rechnung verwenden“** | Datendatei und Druck-PDF | Original-PDF als Sichtseite, sonst wie CSV bzw. XML |
| **Nur PDF** (unterstützt, nicht empfohlen) | Druck-PDF mit Textebene | Lesen → Erkennen → XML erzeugen → PDF/A → Prüfen → Ablegen |

Ohne den Haken (Standard bei CSV/XML) wird die Sichtseite aus den Daten neu gebaut
(Standardlayout oder die Vorlage unter Absender → „Layout gestalten…“). Die Überwachung
verarbeitet die CSV bzw. XML sofort. Liegt trotzdem ein PDF mit gleichem Dateinamen daneben,
wird es nicht als Sichtseite genommen und nicht als eigene Nur-PDF-Rechnung gelesen;
es wandert mit der Datendatei nach `Erledigt`. Ein PDF ohne passende Datendatei landet
mit Begründung im Fehlerordner.

Mit Haken startet die Verarbeitung erst, wenn PDF und CSV bzw. XML mit gleichem Namen im
Eingang liegen. Bis dahin zeigt die Karte „Zu tun“ z. B. „R-123.pdf wartet auf die passende CSV“.
Kommt die zweite Datei nicht, geht die erste nach `optionen.gegenstueck_minuten` (Standard 10)
allein in den Lauf (Paarung über die Rechnungsnummer). 0 = nicht warten.

Ältere Konfigurationen mit `modus: pdf_csv` bzw. `pdf_xml` werden als CSV bzw. XML mit
gesetztem Haken geladen; die bisherige Wartezeit bleibt. Beim Speichern schreibt Fakturafalter
`modus: csv` oder `modus: xml` und `optionen.pdf_verwenden`.

## Hauptfenster und Fortschritt

Das Hauptfenster beantwortet drei Fragen: Läuft es? Muss ich etwas tun? Wie viele heute? Technische Details stehen
in der Logdatei, nicht in der Oberfläche.

- **Fortschritt:** Während einer Verarbeitung erscheint über der Statusleiste ein eigener Bereich mit Textzeile
  (z. B. „Rechnung 3 von 12 · Prüfen (KoSIT) · RE-2026-0042.pdf“, bei einer einzelnen Datei ohne „1 von 1“),
  einem ruhigen Balken (Rechnungen × 6 Schritte, ohne Animation) und den sechs Schritten mit Symbol: Haken =
  erledigt, volle Scheibe = läuft, leere Scheibe = steht aus. Die Prüfung läuft für alle Rechnungen eines Stapels
  in einer Java-Laufzeit; dann steht dort „12 Rechnungen · Prüfen (veraPDF)“ bzw. „(KoSIT)“.
- Solange verarbeitet wird, ist „Jetzt einlesen“ ausgegraut und die Statuskarte zeigt „Verarbeitung läuft“; im
  Leerlauf ist der Bereich ausgeblendet und links in der Statusleiste steht „Bereit“.
- Scheitert eine Datei, nennt ein kurzer Hinweis über dem Balken die Datei („liegt im Ordner Fehler“); der Lauf
  geht mit der nächsten weiter.
- Am Ende: reiner Erfolg → kein Toast, nur der Zähler „Heute: n erstellt“ steigt. Mit Prüffällen → Toast
  „12 verarbeitet, 1 prüfen“ mit Knopf „Prüfen“. Mit Fehlern → ein zusammengefasster Toast.
- **Starthinweis:** Beim Start steht oben eine Karte „Ohne Gewährleistung und ohne Support“ (Apache-2.0
  Abschnitt 7 und 8). „Schließen“ blendet sie bis zum nächsten Start aus, „Nicht mehr anzeigen“ für immer
  (`oberflaeche.starthinweis_aus`).

## Datenschutz und Logs

Fakturafalter arbeitet vollständig offline. Die Logdatei liegt im Ordner `logs/` neben der Konfiguration
(1 MB × 5 Dateien). Einstellungen → Allgemein → Datenschutz → **„Logs anonymisieren“**
(`optionen.logs_anonymisieren`, Standard aus) ersetzt in allen Log-Ausgaben Namen, Anschriften (Straße, PLZ Ort,
Postfach), IBAN, USt-IdNr., E-Mail-Adressen und Beträge durch Platzhalter wie `[Name]`, `[IBAN]` oder `[Betrag]`.
Die eigenen Stammdaten und die Käufer eines Laufs werden zusätzlich wörtlich maskiert. Das gilt ab dem Einschalten;
ältere Zeilen bleiben, wie sie sind. Die Tabellen-Diagnose der Erkennung (nur Wortformen wie `Aaaa 99,99`) bleibt
unverändert. `protokoll.tsv` im Ausgang ist keine Logdatei und bleibt vollständig.

## Einrichtung und Anlernen

Beim ersten Start führt ein Assistent in vier Schritten durch die Einrichtung: **Ordner** → **Absender**
(eintippen, aus einer Datei importieren oder aus einer Rechnung übernehmen) → **Rechnungen anlernen** →
**Fertig**. „Später einrichten“ ist jederzeit möglich; das Hauptfenster zeigt dann, was noch fehlt.

Zwei Arbeitsweisen (Einstellungen → Vorlagen & Anlernen):

- **Nur PDF** – die Rechnungen kommen als Druck-PDF. Unbekannte Layouts landen in der Anlern-Warteschlange;
  der **Anlern-Assistent** zeigt das PDF, schlägt Absender, Rechnungsdaten und Positionen vor, du bestätigst
  mit „Passt“ oder klickst den richtigen Wert im PDF an. Der Absender gehört zur Vorlage (mehrere Absender
  möglich) und wird aus dem Druck erkannt oder aus einer CSV importiert. Bei einem neuen Layout eines bekannten
  Absenders wählst du den Absender in Schritt 2 einfach aus. Im ersten Schritt **„Bereiche festlegen“** ziehst du
  auf Wunsch Rahmen um Anschrift, Rechnungskopf, Positionstabelle, Summen und Zahlungsbedingungen (gilt auf
  allen, der ersten oder der letzten Seite); diese Angaben werden dann nur noch dort gelesen (Einstellungen →
  Absender → „Bereiche bearbeiten…“). Werte über mehrere Wörter oder Zeilen holst du mit
  **„Bereich ziehen“**, die ganze Käuferanschrift mit **„Anschrift als Block“** (Rahmen ziehen oder Zeilen mit
  Strg+Klick; wird in Name, Adresszusatz, Straße, PLZ und Ort zerlegt). Sitzt eine Spaltenlinie der
  Positionstabelle falsch, ziehst du sie im PDF an die richtige Stelle. Klappt die automatische Spaltenerkennung
  nicht, legst du die Spalten mit **„Spalte hinzufügen“** einzeln fest: Rahmen über eine Spalte ziehen
  (Überschrift bis letzte Position) und die Bedeutung wählen (Menge, Einheit, Bezeichnung, Einzelpreis,
  Preiseinheit, Betrag, Artikelnr. oder ignorieren). Die Rahmen bleiben farbig sichtbar, lassen sich verschieben,
  in der Breite ändern und entfernen und werden mit der Vorlage gespeichert. Werden trotzdem keine Positionen
  erkannt, kopiert **„Diagnose kopieren“** eine Beschreibung der Tabelle ohne Rechnungstext (nur Lage der
  Wörter und Zeichenmuster wie `9.999,99`) in die Zwischenablage – zum Weitergeben an den Support.
- **PDF + CSV** – die CSV ist die Quelle, das PDF dient zur Gegenprüfung und trainiert die Vorlage mit. Ein
  Assistent (Datei → Format → Vorschau → Probe → Fertig) erkennt Trennzeichen, Zeichensatz und Dezimalzeichen und
  schlägt je Spalte vor, wofür sie steht; das Ergebnis ist ein normales CSV-Profil ([csv-format.md](csv-format.md)).
- **PDF + XML** – die Software legt zu jeder PDF eine ZUGFeRD/Factur-X- oder XRechnung-XML (CII oder UBL) mit
  gleichem Namen ab; feste Zuordnung nach EN 16931, nichts einzurichten. Andere XML-Formate (z. B. DATEV,
  Lexware) werden nicht gelesen.

Jede Vorlage hat in den Einstellungen eine Karte mit Fortschritt („3 von 5 ohne Korrektur“). Nach 5 Rechnungen
in Folge ohne Korrektur lässt sich **„Automatisch, ohne Nachfrage“** einschalten: Ab dann reicht das PDF allein.
Pflichtangaben- und Summenprüfung laufen trotzdem bei jeder Rechnung.

Testdaten zum Ausprobieren (erfundener Industrie-Großhändler, mit und ohne CSV):
[beispiele/industrie/](../beispiele/industrie/README.md).

## Prüfung nach Erstellung

Jede erzeugte E-Rechnung wird sofort lokal geprüft (Einstellung „Nach Erstellung prüfen“,
`optionen.nach_erstellung_pruefen`, Standard an). Keine Online-Dienste, keine Downloads zur Laufzeit.

- **Mustang** (mit veraPDF): PDF/A-3 und ZUGFeRD-Aufbau. Gültig nur, wenn veraPDF die Datei als PDF/A-konform
  meldet (`isCompliant=true`); fehlt diese Angabe, gilt die Rechnung als „nicht geprüft“.
- **KoSIT-Validator** mit XRechnung-Konfiguration: Rechnungsdaten nach EN 16931 (Schematron),
  für die eingebettete `factur-x.xml` und eine eventuelle XRechnung.
- **Gültig** → bleibt im `Ausgang`. **Ungültig** → Ausgaben und Quellen nach `Fehler`, mit deutschem
  Fehlerbericht (Regel, Kurzbeschreibung, „Was tun“); der technische Prüfbericht steht im Log.
- Kann die Prüfung technisch nicht laufen, wird die Rechnung trotzdem ausgegeben, Status „nicht geprüft“.
- Prüfstatus: Spalte 8 in `protokoll.tsv`, Prüfansicht der Oberfläche und Statusleiste.
- Ein Java-Prozess pro Stapel (nicht pro Rechnung).

Die fertigen Pakete bringen alles mit (Ordner `werkzeuge/`: Java-Laufzeit, Mustang, KoSIT,
Konfiguration). Gesucht wird in `$FAKTURAFALTER_WERKZEUGE`, `werkzeuge/` neben dem Programm, dann
`werkzeuge/` im Arbeitsverzeichnis; Java über `$FAKTURAFALTER_JAVA`, `werkzeuge/jre*/`, dann PATH.
In der Entwicklung: `packaging/werkzeuge.sh werkzeuge linux` (siehe packaging/README.md).

Welche CSV erwartet wird und welche Spalten mindestens nötig sind: [csv-format.md](csv-format.md).

## Layouteditor (Sichtteil gestalten)

Einstellungen → Absender → **„Layout gestalten…“** öffnet den Layouteditor für das gewählte Absender-Profil
(links die Bausteine, Mitte die Seite mit Beispieldaten, rechts die Eigenschaften in mm).
Er gestaltet den sichtbaren Teil der **erzeugten** ZUGFeRD-PDF; die XML bleibt unverändert. Er gilt immer dann,
wenn der Sichtteil neu aufgebaut wird: CSV/XML ohne Druck oder Einstellungen → Ausgabe → Sichtbild
„Immer neu erzeugen“. Mit „Original-Druck verwenden“ bleibt der Druck der Warenwirtschaft sichtbar.

- Bausteine Logo, Absender, Empfängeranschrift, Rechnungskopf, Positionstabelle, Summenblock, Zahlung/Bank,
  Hinweise und Fußzeile mit der Maus verschieben, an Kanten und Ecken in der Größe ändern (Raster 5 mm,
  Einrasten an/aus, Pfeiltasten 1 mm, mit Umschalt 5 mm). Rechts: X/Y/Breite/Höhe in mm, Schriftgröße, Ausrichtung.
- Pflichtangaben nach § 14 Abs. 4 UStG (Absender, Empfänger, Rechnungskopf, Positionen, Summen mit Steuer,
  Fußzeile mit USt-IdNr./Steuernummer) haben ein Schloss: nicht ausblendbar, dürfen sich nicht überlappen und
  liegen immer über allem anderen. Freiwillig: Logo, Zahlung/Bank (ausgeblendet steht ein vereinbartes Skonto
  trotzdem im Summenblock, Nr. 7), Hinweise.
- Eigene Felder: Text- und Bildfelder (PNG/JPEG) hinzufügen und löschen – nur Gestaltung, nicht in der XML.
  Freiwillige Bausteine und eigene Felder lassen sich mit „Ebene nach vorn/hinten“ stapeln.
- Briefpapier-PDF als Hintergrund, getrennt für Seite 1 und Folgeseiten. Beim Laden wird es geprüft (Schriften
  eingebettet, keine CMYK-/Sonderfarben, keine Formulare; mit Prüfwerkzeugen zusätzlich veraPDF an einer
  Probe-Rechnung). Nicht taugliches Briefpapier wird als Bild (sRGB) übernommen, nicht umwandelbares abgelehnt;
  Ergebnis als Hinweis, Details im Log.
- Lange Werte im Rechnungskopf (z. B. eine lange Bestellnummer) brechen um, statt abgeschnitten zu werden; das
  gilt auch für das Standardlayout ohne eigene Vorlage.
- Die Positionstabelle bricht auf Folgeseiten um (Tabellenkopf wiederholt, Übertrag unten und oben), Folgeseiten
  haben ein eigenes Layout. Die Vorschau nutzt denselben Renderer wie die Ausgabe, mit fiktiven Beispieldaten.
- Gespeichert wird als Block `layout:` in der Konfiguration (beim aktiven Absender oben, bei gemerkten Absendern
  in `absender_profile`), Bilder und Briefpapier liegen im Ordner `layout/` daneben. Ohne Block gilt das bisherige
  Layout unverändert; „Zurücksetzen auf Standard“ entfernt den Block. Beispiel: [beispiele/layout/](../beispiele/layout/).

## PDF-Erkennung

Die CSV bleibt die Quelle. Das Druck-PDF dient als zweite Quelle (Profil-Abschnitt `pdf_erkennung`,
in der Oberfläche unter Einstellungen → Vorlagen & Anlernen):

- **Gegenprüfung** (an): Rechnungsnummer, Rechnungsdatum, Leistungsdatum/-zeitraum, USt-IdNr./Steuernummer,
  IBAN, Netto/USt/Brutto und Steuersätze werden im Druck gesucht. Weicht ein Wert ab (Toleranz 0,01 €),
  geht die Rechnung nach `Prüfen` – mit Feld, CSV-Wert und Druck-Wert.
- **Anlernen** (an): Aus jedem Paar CSV + PDF ohne Abweichung lernt Fakturafalter das Layout als lesbare
  YAML-Vorlage in `angelernt/` neben dem Profil (Fingerabdruck, Fundstellen, Trefferquote). Ohne KI,
  deterministisch, mit pdfplumber.
- **Nur PDF** (aus, in der Oberfläche „Automatisch, ohne Nachfrage“): Erst wenn eine Vorlage `nur_pdf_ab`
  Rechnungen in Folge (Standard 5) vollständig getroffen hat, darf ein PDF ohne CSV verarbeitet werden. Auch dann laufen Pflichtangaben- und Summenprüfung.

```yaml
pdf_erkennung:
  gegenpruefung: true
  felder: [BT-1, BT-2, BT-72, BG-14, BT-31, BT-32, BT-84, BT-109, BT-110, BT-112, BT-119]
  toleranz: 0.01
  anlernen: true
  nur_pdf: false
  nur_pdf_ab: 5
```

Beispiele mit sechs erfundenen Verkäufern und Layouts: [beispiele/pdf-erkennung/](../beispiele/pdf-erkennung/).

## Fertige Pakete

Linux-AppImage und portables Windows-ZIP (jeweils mit Java-Laufzeit und Prüfwerkzeugen) werden mit den Skripten in
`packaging/` gebaut, siehe [packaging/README.md](../packaging/README.md).

## Tests
    QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
    FAKTURAFALTER_WERKZEUGE=$PWD/werkzeuge QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q   # inkl. echter Prüfung
