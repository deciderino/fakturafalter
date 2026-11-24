# F5 Versatz (nach JTL-Wawi „creativ 1.4“, Q5)

Absender: Kerber Bürobedarf GmbH, Straubing (fiktiv). Schrift Helvetica 8 pt, Logo als PNG-Bild.
Wortlaut wie in der Vorlage.

Was ist besonders:
- Infoblock Rechnung-Nr: / Auftrag-Nr: / Datum: / Kunden-Nr: als „Label: Wert“, die **Werte
  1,8 pt tiefer** als die Labels (Grundlinienversatz wie im Vorlagen-PDF). Das ersetzt in F5 das „Label über
  Wert“ des Plans.
- Die Auftrag-Nr. (AU…) ist die Nummer des Verkäufers: `test_flags.auftragsnummer`, BT-13 leer.
- „Rechnung“, „Seite: 1 von N“; Tabelle Pos. | Menge („2 Stück“) | Art.-Nr. | Bezeichnung | MwSt. („19,00 %“) |
  E-Preis | G-Preis, Beträge ohne Tausenderpunkt mit „EUR“.
- Seitenumbruch mit „Zwischensumme“ unten und „Übertrag von Seite N“ oben.
- Summen Gesamt Netto / zzgl. 19,00 MwSt. / Gesamtbetrag; danach „Zahlungsart: Rechnung“ und
  „Zahlungsziel: N Tage“; Fuß in vier Spalten mit „Seite: n / m“.

Fälle: 1–3 Training (Versandkosten als Position; 2 Seiten mit Übertrag und Skonto; Stunden gemischt). 4–5 Hold-out (3 Namenszeilen;
87 Positionen auf 3 Seiten mit zwei Überträgen).

Weggelassen (OUT): Rabattspalte, Vorauszahlungs-/Gutscheinzeilen, „USt-Nr:“ des Kunden (kein Datenfeld).

A1 (20.11.2026), alle Hold-out: 6 **Fehler** `rechnungsdatum_fehlt` (Feld „Datum:“ leer, Lieferdatum vorhanden). Details in `../README.md`, Abschnitt „A1“.

## Bekannte Lücke

Benchmark vom 03.11.2026 (`--lernen 2`), nicht an die Erkennung angepasst, Befunde:
- Positionen: Im Kaltstart wird keine Position gelesen (0/5). Die Tabelle hat keine Spalte „Gesamt“
  (`tabelle_vorschlagen` braucht sie; hier heißt sie „G-Preis“).
- BT-1: Gelesen wird eine Zahl aus dem Firmenblock bzw. Fuß statt „Rechnung-Nr:“; der Grundlinienversatz trennt
  Label und Wert (0/5).
- BT-13: Die Auftrag-Nr. des Verkäufers landet in BT-13 (soll leer).
- BT-119: „zzgl. 19,00 MwSt.“ ohne Prozentzeichen liefert keinen Steuersatz.
- BT-112 bei mehrseitigen Belegen: Gelesen wird die Seitenzahl („2“, „3“) aus „Seite: n / m“.
- Angelernt: Nach zwei Paaren gilt die Vorlage noch nicht als sicher, Beleg 3–5 werden nicht gelesen.
