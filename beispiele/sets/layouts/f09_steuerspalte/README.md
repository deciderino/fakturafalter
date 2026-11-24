# F9 Steuerspalte (nach der Symtrax-Compleo-Beispielrechnung „Handelsrechnung“, ZUGFeRD-Korpus, Q8)

Absender: Lüders Kaffeerösterei GmbH, Hamburg (fiktiv). Schrift Courier 8 pt. **Gemischte Steuersätze 7/19 %**
(Kaffee, Tee, Kakao, Zucker 7 %; Maschinen, Zubehör 19 %).

Was ist besonders:
- „Handelsrechnung Nr. <Nr.> vom <Datum>“ (Datum nur in der Überschrift), darunter „Label : Wert“-Zeilen mit
  Doppelpunkt in einer Spalte: Liefer- und Leistungsdatum, Kundennummer, Bestellnummer, Währung EUR.
- Blöcke „Verkäufer:“ und „Käufer:“; im Verkäuferblock „Steuernummer :“ und „USt.-Id.-Nr. :“.
- „Rechnung gemäß Bestellung vom …“ bzw. „Rechnung gemäß Lieferung“.
- Tabelle mit zweizeiligem Kopf Pos | Art.-Nr. | Bezeichnung | Menge („5 Stk“) | Nettopreis je Einheit |
  Steuer Satz (Kat.) („7 % VAT (S)“) | Nettobetrag EUR – **Steuersatz je Position**.
- Belegsummen Positionssumme / Rechnungssumme ohne USt. / Steuerbetrag / Bruttosumme / Zahlbetrag: **eine
  USt-Zeile** für beide Sätze, keine Aufschlüsselung je Satz (die JSON hat sie in `vat_breakdown`).
- „Zahlungsbedingungen:“ mit „Zahlbar innerhalb N Tagen netto bis …[, X% Skonto innerhalb T Tagen bis …]“;
  Bank als „Label : Wert“, Fuß zweizeilig zentriert.

Fälle: 1–3 Training (Skonto mit Datum; ohne Bestellnummer; 3 Namenszeilen, mehrzeilig). 4–5 Hold-out (einfach;
**Prüfen**: gedruckter Steuerbetrag 59,62 statt 59,52, Brutto folgt dem gedruckten Wert).

Weggelassen: Aufschlüsselung je Satz, Zu-/Abschläge, Anzahlungen (siehe QUELLEN.md, Q8).

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- Summen: BT-109 fehlt, als BT-110 wird das Netto gelesen, BT-112 fehlt (je 0/5). „Rechnungssumme ohne USt.“,
  „Steuerbetrag“, „Bruttosumme“ werden nicht zugeordnet.
- BT-2: Datum aus „Handelsrechnung Nr. … vom <Datum>“ nicht gelesen (0/5).
- BT-9 und Skonto: „netto bis <Datum>“ liefert keine Fälligkeit; Skonto = ganzer Satz.
- BT-119: Gelesen wird „7“, Soll im Benchmark „19“. Der Benchmark kennt nur einen Satz (`vat_rate`); für
  gemischte Sätze ist das eine Grenze des Benchmarks, kein Fehler der Erkennung.
- Prüfen-Fall Beleg 5 bleibt durch die Summenlücke verdeckt (BT-110 liest Netto, nicht 59,62).
- Angelernt: Nach zwei Paaren gilt die Vorlage noch nicht als sicher, Beleg 3–5 werden nicht gelesen.
