# F4 Kontaktblock (nach easybill Rechnungsvorlage 2023, Q3)

Absender: Grünwerk Gartenplanung GmbH, Kassel (fiktiv). Schrift Helvetica 9 pt (Vorlage: Arial), Logo-Kasten
„GW“ als PNG-Bild. Wortlaut wie in der Vorlage.

Was ist besonders:
- Rechts oben der Block „So erreichen Sie uns“ (Internet, E-Mail, Telefon, Telefax, Mobil, Steuer-Nr.,
  USt-IDNr.), darunter Datum: / Kunde: / Rechnung: als „Label: Wert“.
- „Rechnung <Nr.>“ fett und der Satz „Das Rechnungsdatum entspricht dem Leistungsdatum“: Das Leistungsdatum
  steht nur als Verweis auf das Rechnungsdatum, nie als eigenes Datum.
- Tabelle Pos | Art-Nr. | Bezeichnung | Menge („4,5 Std.“) | Einzelpreis | Betrag €.
- Summen Nettobetrag / Umsatzsteuer 19% / Rechnungsbetrag.
- Zahltext mit festem Datum „Bitte begleichen Sie den offenen Betrag bis zum TT.MM.JJJJ an die unten aufgeführte
  Bankverbindung.“; bei Skonto steht der Skontosatz davor.
- Fuß in drei Spalten. Keine Bestellnummer (die Vorlage hat keine).

Fälle: 1–3 Training (Stunden und festes Datum; Waren und Stunden mit Skonto; 3 Namenszeilen, mehrzeilige
Bezeichnungen). 4–5 Hold-out (8 Positionen; **Prüfen**: der Satz zum Leistungsdatum fehlt, damit fehlt die
Pflichtangabe BT-72, `PRUEFEN [BT-72]`).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `rechnungsnummer_fehlt` (Feld „Rechnung:“ leer). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- BT-1: Gelesen wird die Telefonvorwahl „0561“ (bzw. „70“) aus dem Kontaktblock statt „Rechnung: <Nr.>“ –
  kaltstart und angelernt 0/5.
- BT-72: „Das Rechnungsdatum entspricht dem Leistungsdatum“ wird nicht als Leistungsdatum gelesen (0/4).
- BT-20/BT-9: „Bitte begleichen Sie den offenen Betrag bis zum …“ startet keinen Zahltext; die Fälligkeit fehlt
  meist.
- Einheit: „Std.“ in der Mengenspalte wird als Stück (H87) statt Stunde (HUR) gelesen.
- Prüfen-Fall Beleg 5: Die Erkennung meldet das fehlende Leistungsdatum nicht gezielt als BT-72; der Fall ist
  im Benchmark nur über die Prüfliste sichtbar.
