<p align="center">
  <img src="src/fakturafalter/ressourcen/fakturafalter.svg" width="96" height="96" alt="Logo von Fakturafalter">
</p>

<h1 align="center">Fakturafalter</h1>

<p align="center">Erstellt lokal ZUGFeRD-Rechnungen (EN 16931, PDF/A-3 mit eingebettetem XML) aus CSV oder XML. Mit Layout-Editor und automatischer Prüfung – ohne Cloud.</p>

![Hauptfenster von Fakturafalter, Überwachung aktiv, heute 3 Rechnungen erstellt](docs/bilder/hauptfenster.png)

Fakturafalter überwacht einen Ordner auf deinem Rechner, liest CSV- oder XML-Exporte deiner Warenwirtschaft und erzeugt daraus die E-Rechnung. Die Oberfläche ist auf Deutsch und Englisch, für Windows und Linux.

## Was es kann

- **Eingabe:** CSV (Export aus der Warenwirtschaft) oder XML (ZUGFeRD / Factur-X oder XRechnung, CII oder UBL). Optional der Haken „Zusätzlich das PDF der Rechnung verwenden“, dann gilt der Original-Druck als Sichtseite.
- **Ausgabe:** ZUGFeRD als PDF/A-3 (Profil EN 16931, eingebettete `factur-x.xml`) und optional zusätzlich eine XRechnung-CII
- **Layout-Editor** für den sichtbaren Teil, wenn die Sichtseite aus den Daten neu gebaut wird (Einstellungen → Absender → „Layout gestalten…“)
- **Automatische Prüfung** nach jeder Erstellung, lokal und offline: Mustang (mit veraPDF) für PDF/A-3 und den ZUGFeRD-Rahmen, KoSIT für die Rechnungsdaten nach EN 16931. Dazu Plausibilität und Pflichtangaben (Summen, fehlende Felder, Gutschrift ohne Rechnungsbezug). Unklares landet in „Zu prüfen“, Ungültiges in „Fehler“ – nichts geht still raus.
- **Ordnerüberwachung** mit Fortschrittsanzeige, während verarbeitet wird
- **Kundenbezeichnung 1–3** als eigene Zeilen im Adressblock, Artikel-, Zeichnungs- und Bestellangaben klein unter der Positionsbezeichnung
- **Rechnungsnummer prüfen, Dateiname festlegen:** Die Nummer kommt immer aus dem ERP. Optional prüft Fakturafalter sie gegen ein Muster (z. B. `JJJJ######`) und meldet Lücken; Dateiname je Belegart mit Platzhaltern (Einstellungen → Ausgabe)

**Nur PDF** (Angaben allein aus dem Rechnungsdruck) wird weiterhin unterstützt, ist aber nicht der empfohlene Weg: Die Erkennung kann fehlgehen, Layouts müssen angelernt und Ergebnisse kontrolliert werden. Details im [Handbuch](docs/handbuch.md#nur-pdf-unterstutzt-aber-nicht-empfohlen).

![Layout-Editor mit Briefpapier und markiertem Rechnungskopf](docs/bilder/layouteditor.png)

![Fortschrittsanzeige: Rechnung 3 von 12, Schritt Prüfen mit KoSIT](docs/bilder/fortschritt.png)

![Einrichtungsassistent: Arbeitsordner festlegen](docs/bilder/einrichtung.png)

![Prüfdialog: Abweichung oder Hinweis zur Rechnung](docs/bilder/pruefen.png)

Die Screenshots zeigen ausschließlich erfundene Beispieldaten.

## Schnellstart: CSV

1. Fakturafalter starten. Beim ersten Mal führt ein kurzer Assistent durch Arbeitsordner und Absender.
2. Einstellungen → **Eingang & Vorlagen** → Eingangsformat **CSV**.
3. **Neue CSV einrichten…**: eine echte Export-Datei wählen, der Zuordnung einen Namen geben, Weiter. Format (Trennzeichen, Zeichensatz, Dezimalzeichen) ist erkannt und lässt sich umstellen; danach die Spalten prüfen, eine Probe ansehen und speichern.
4. Den Haken **„Zusätzlich das PDF der Rechnung verwenden“** nur setzen, wenn der Original-Druck die Sichtseite bleiben soll. Ohne Haken (Standard für eine neue CSV-Einstellung) baut Fakturafalter die Sichtseite aus den Daten neu und wartet nicht auf ein PDF.
5. Schalter **Überwachung** einschalten und die CSV in den Ordner `Eingang` legen.

Die fertige ZUGFeRD-PDF liegt im `Ausgang` und ist, wenn die mitgelieferten Prüfwerkzeuge da sind, bereits lokal geprüft.

## Schnellstart: XML

1. Einstellungen → **Eingang & Vorlagen** → **XML (ZUGFeRD / XRechnung)**. Eine Zuordnung ist nicht nötig: CII und UBL liest Fakturafalter fest.
2. Optional **Probe mit einer XML…**, um eine Beispiel-Datei zu prüfen, ohne etwas zu erzeugen.
3. Wie bei CSV: Haken nur, wenn ein Original-PDF die Sichtseite sein soll. Ohne Haken wird die Sichtseite neu gebaut.
4. Überwachung an, XML in den `Eingang` legen. Fehlt der Verkäufer in der XML, gilt der Absender aus den Einstellungen.

Andere XML-Formate (zum Beispiel DATEV oder Lexware) werden nicht gelesen; die Datei kommt mit Begründung in den Fehlerordner.

## Download und Start

Unter [Releases](https://github.com/deciderino/fakturafalter/releases) liegen ein Linux-AppImage und ein portables Windows-ZIP. Beide bringen Java-Laufzeit und Prüfwerkzeuge mit.

- **Linux:** AppImage ausführbar machen und starten.
- **Windows:** ZIP entpacken und `fakturafalter.exe` starten.

## Offline und Lizenz

Alles läuft offline, ohne Cloud und ohne Telemetrie. Lizenz: [Apache-2.0](LICENSE) (Drittkomponenten in [NOTICE](NOTICE)).

Freie Open-Source-Software – ohne Gewährleistung und ohne Support. Die eingebaute Prüfung ersetzt keine eigene Kontrolle der Rechnungen vor dem Versand.

## Entwickeln

```bash
python -m venv .venv && .venv/bin/pip install -e ".[gui,test]"
fakturafalter
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
```

Die Anleitung für den Alltag steht im [Handbuch](docs/handbuch.md). Ausführlichere Hinweise zu Eingabevarianten, Prüfung, Layout-Editor und PDF-Erkennung stehen in [docs/details.md](docs/details.md). Zum CSV-Spaltenformat siehe [docs/csv-format.md](docs/csv-format.md).
