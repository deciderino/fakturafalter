# F3 Seitenleiste (nach JTL-Wawi business 2.0, Q4)

Absender: Seeberger Radsport-Teile GmbH, Landsberg am Lech (fiktiv). Schrift Helvetica 7,5 pt. Wortlaut und
Anordnung wie in der Vorlage.

Was ist besonders:
- Rechte Seitenleiste (Form XObject, per `Do` auf jeder Seite) mit Absender, USt-IdNr., Gläubiger-IdNr.,
  Kontakt, Bearbeiter und Bank.
- Belegdaten auf **jeder** Seite als **Label über Wert** auf Höhe der Tabelle (Rechnungsnummer, -datum,
  Auftragsnummer, Kundennummer, Zahlungsart, Versandart, Lieferdatum (vorauss.)).
- Tabelle **neben** der Seitenleiste: Pos | Menge („10 Stück“) | Art. Nr. | Bezeichnung | Netto EP | MwSt | Netto GP,
  darunter klein „Artikelbeschreibung kurz“.
- Content-Stream in umgekehrter Reihenfolge: Leiste, Belegdaten, Summen, Zeilen rückwärts, Kopf, Anschrift zuletzt.
- Mehrseitig: „Zwischensumme 3.090,20 €“ unten, „Übertrag von Seite 1 3090,20“ (ohne Tausenderpunkt, ohne €) oben.
- „Zahlungsziel: 30 Tage“; Skonto als Anmerkung („Bei Zahlung innerhalb von 10 Tagen gewähren wir 2 % Skonto.“).
- Kein Fuß, Bank nur in der Leiste.

Soll-Werte: Die Auftragsnummer ist die Nummer des Verkäufers (`test_flags.auftragsnummer`); BT-13 ist leer.

Fälle: 1–3 Training (1 Seite; 2 Seiten mit Skonto; 3 Namenszeilen, 14 Tage).
4–5 Hold-out (2 Seiten; 3 Seiten mit Skonto).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `ust_id_pruefziffer` (USt-IdNr. in der Seitenleiste ungültig). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Stand der Erkennung bei Erstellung (nicht angepasst, Befunde):
- Kaltstart liest „Label über Wert“ nicht: Rechnungsnummer, Rechnungsdatum, Kundennummer fehlen ohne Anlernen.
- Der Tabellenvorschlag braucht eine Kopfspalte „Gesamt“; „Netto GP“ zählt nicht, die Positionen fehlen.
- Zeilen laufen über die ganze Seitenbreite; Text der Seitenleiste auf gleicher Höhe hängt sich an Positionszeilen.
- „Zahlungsziel: N Tage“ ohne Bezugsdatum ergibt kein BT-9 aus dem Text.
