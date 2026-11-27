# Fakturafalter 1.0.0-rc2

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Zweites Release Candidate auf dem Weg zu 1.0 (fasst die geplanten rc2 und rc3
zusammen). Neu sind Excel- und LibreOffice-Tabellen als Eingang, Umwandeln von
Hand und per Ziehen ins Fenster sowie ein flexiblerer Layout-Editor
(Layoutformat 2). CSV-Profile aus 1.0.0-rc1 bleiben gültig. Layouts aus älteren
Versionen (bis 1.0.0-rc1) werden abgelehnt und im Editor neu eingerichtet.
Vorheriger Stand: 1.0.0-rc1; die stabile Linie bleibt 0.9.11.2, bis 1.0
erscheint.

## Was sich ändert

- **Umwandeln von Hand.** Im Hauptfenster neben „Jetzt einlesen“ steht
  **Umwandeln …** mit „Dateien wählen …“ und „Ordner wählen …“. Dateien oder
  einen Ordner kannst du auch ins Fenster ziehen. Das geht auch bei
  ausgeschalteter Überwachung. Es gilt dieselbe Strecke wie beim Eingang
  (Profil, Pflicht- und Validierungsprüfung, Prüfansicht, Ausgang). Deine
  Originale bleiben unangetastet; verarbeitet wird eine Kopie. Bei einem Ordner
  zählen nur die Dateien direkt darin. Passt eine Datei zu keinem
  Eingangsformat, sagt Fakturafalter das.

- **Excel und LibreOffice Calc.** `.xlsx` und `.ods` richtest du im Assistenten
  wie eine CSV ein. Statt Trennzeichen und Zeichensatz wählst du
  **Tabellenblatt** und die Zeile der **Kopfzeile** (Titelzeilen darüber
  erkennt der Assistent). Zahlen- und Datumszellen werden genau übernommen:
  Beträge als Dezimalzahl ohne Rundungsreste, Datumszellen als Datum, `19 %`
  als Steuersatz 19. Bei Formeln zählt der zuletzt gespeicherte Wert. Fehlt
  das Blatt später, passt das Profil nicht (Meldung mit Blattnamen).
  *Nicht unterstützt:* das alte `.xls` und verschlüsselte Mappen. Neue
  Abhängigkeit: openpyxl (MIT, Lizenz im Paket). ODS liest Fakturafalter
  selbst.

- **BT-Nummern als Spaltennamen.** Heißt eine Spalte `BT-13`, `bt_13`,
  `BT 13` oder `Bestellnummer (BT-13)`, ordnet der Assistent sie direkt dem
  Feld zu, auch in Block-Kopfzeilen. `BT-1` und `BT-10` werden sicher
  unterschieden.

- **Amtliche Namen im Assistenten.** Neben jedem Feld steht grau die
  BT-Nummer; der Tooltip nennt den Namen aus EN 16931 („Im Standard: BT-13
  Bestellreferenz (Purchase order reference)“). „Feld suchen …“ findet auch
  Käufer/Verkäufer, Buyer/Seller und BT-Nummern.

- **„Unterzeilen ohne Vorsatz anzeigen“.** Der Schalter heißt jetzt so, wie er
  wirkt: Unterzeilen erscheinen ohne „Beschreibung:“, „Art.-Nr.“ und die
  anderen Vorsätze – für alle Vorsätze gleich.

- **Angenommene Einheit „Stk.“.** Mit „Wenn die Einheit fehlt, Stück
  eintragen“ zeigt die Sichtseite die normale Kurzform „Stk.“ wie bei den
  übrigen Positionen (bei „Einheit wie in der CSV anzeigen“ die Schreibweise,
  die deine Datei bei anderen Positionen für Stück verwendet) statt immer
  „Stück“. In den Rechnungsdaten steht weiter der Code H87.

- **Layout-Editor, Layoutformat 2.**
  - Das Schloss tragen nur noch Empfänger, Rechnungskopf, Positionen und
    Summen. Absender und Fußzeile kannst du ausblenden.
  - Bei Absender und Fußzeile wählst du unter „Dieser Baustein zeigt:“, welche
    Verkäufer-Angaben er druckt (Name, Anschrift, Handelsregister, USt-IdNr.,
    Steuernummer, Bank, Kontakt). Die Rücksendezeile über der Empfängeranschrift
    ist schaltbar.
  - Nach dem Laden eines Briefpapiers hakst du an, was schon draufsteht
    („Briefpapier enthält: …“), getrennt für Seite 1 und Folgeseite. Das druckt
    Fakturafalter dort nicht noch einmal.
  - Prüfung nach § 14 Abs. 4 UStG: Fehlt eine Pflichtangabe auf der Rechnung,
    steht sie im roten Kasten und Speichern ist gesperrt. Doppelte Angaben
    ergeben nur einen gelben Hinweis. Fakturafalter hakt nichts von selbst ab.
    Handelsregister nur ohne USt-IdNr., Bank nur bei Überweisung mit IBAN.
  - Die Folgeseite braucht Rechnungskopf und Positionen.
  - **Platzhalter** in Textfeldern: „Platzhalter einfügen…“ bietet
    Rechnungsangaben wie `{BT-13}` und die nicht zugeordneten Spalten deiner
    CSV-Profile (z. B. `{Projektleiter}`). Nur Kopfwerte; fehlt ein Wert,
    bleibt die Stelle leer.

- **Alte Layouts.** Ein Layout ohne `version: 2` übernimmt Fakturafalter nicht.
  Der Editor erklärt das und startet auf dem Standard; die Konfiguration bleibt
  unverändert, bis du speicherst. Muss die Sichtseite neu erzeugt werden, geht
  die Rechnung mit diesem Grund nach „Zu prüfen“ – nie still ins
  Standardlayout. Mit „Original-Druck verwenden“ ändert sich nichts.
  CSV-Profile (Profilformat 2) sind nicht betroffen.

- **Nicht unterstützt: Word und Textdateien.** `.docx`, `.doc`, `.odt`, `.rtf`
  werden nicht gelesen. Tipp: als PDF speichern und unter „Nur PDF“ anlernen,
  oder aus der Warenwirtschaft (ERP) als CSV exportieren.

- **Dokumente.** [csv-standard.md](csv-standard.md) (Spezifikation 1.7),
  [csv-format.md](csv-format.md) und das [Handbuch](handbuch.md) beschreiben
  die Neuerungen mit Statusmarkern.

## Layout neu einrichten

1. Einstellungen → Absender → „Layout gestalten…“. Der Hinweis zum alten Layout
   erscheint; der Editor startet auf dem Standard.
2. Briefpapier aus dem Ordner `layout/` erneut laden und anhaken, was schon
   draufsteht.
3. Bei Absender und Fußzeile die Angaben wählen, bis der rote Kasten leer ist.
4. Speichern und mit einer fiktiven Testrechnung die Vorschau prüfen.

Wer das alte Layout behalten will, bleibt bei 0.9.11.2 oder 1.0.0-rc1.

## Prüfung

Lokal, ohne CI, nur fiktive Daten. Volle Testsuite mit neuen Tests zu
Excel/ODS, Umwandeln von Hand, BT-Spaltennamen, Standardnamen, Vorsatz,
„Stk.“ und Layoutformat 2 (Pflichtprüfung, Briefpapier-Haken, Platzhalter,
Ablehnung alter Layouts). Mustang- und KoSIT-Prüfung der Beispielrechnungen,
auch mit Skonto, aus einer Excel-Tabelle und mit einem Layout im Format 2.
AppImage und Windows-ZIP mit Rauchtest.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
