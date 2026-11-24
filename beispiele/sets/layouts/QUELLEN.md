# Quellen der Layout-Familien

Jede Familie bildet den **Aufbau** einer öffentlich zugänglichen Rechnungsvorlage nach. Texte, Namen, Nummern
und Beträge sind frei erfunden. Aus den Vorlagen wurde nichts ins Repo kopiert, kein Logo und kein PDF. Die
Recherche-PDFs lagen nur unter `/tmp`. Stand der URLs: 03.11.2026.

| Nr. | Quelle | URL | Familie |
|---|---|---|---|
| Q1 | weclapp Rechnungsvorlage 2020 | https://www.weclapp.com/de/wp-content/uploads/sites/4/2021/06/rechnungsvorlage-2020.pdf | F1 `f01_infozeilen` |
| Q2 | Lexware Vorlage Honorarrechnung | https://www.lexware.de/fileadmin/noindex-follow/wissen-tipps/vorlagen/lexware_vorlage_honorarrechnung.pdf (Übersicht https://www.lexware.de/tools/vorlage-rechnung/) | F2 `f02_briefkopf` |
| Q3 | easybill Rechnungsvorlage mit USt 2023 | https://www.easybill.de/wp-content/uploads/Rechnungsvorlage_mit_Umsatzsteuer_2023.pdf | F4 `f04_kontaktblock` |
| Q4 | JTL-Wawi Druckvorlage „business 2.0“ | https://www.formularkompetenz.de/mediafiles/Sonstiges/druckvorlagen-pdf/Rechnung-MUSTER-business-2-0.pdf | F3 `f03_seitenleiste` |
| Q5 | JTL-Wawi Druckvorlage „creativ 1.4“ (dazu „Flexible B2B 2.0“) | https://www.formularkompetenz.de/mediafiles/Sonstiges/druckvorlagen-pdf/Rechnung-MUSTER-creativ-1-4.pdf | F5 `f05_versatz` |
| Q6 | DATEV Warenwirtschaft, Musterauswertungen Auftragsbearbeitung | https://www.steuerberater-muenchen24.de/cmshandler/download/id.224/WarenwirtschaftMusterauswertungenAuftragsbearbeitung.pdf | F6 `f06_schreibmaschine` |
| Q7 | ZUGFeRD-Korpus, Mustangproject | https://github.com/ZUGFeRD/corpus/tree/master/ZUGFeRDv2/correct/Mustangproject | F10 `f10_satztabelle` |
| Q8 | ZUGFeRD-Korpus, Symtrax | https://github.com/ZUGFeRD/corpus/tree/master/ZUGFeRDv2/correct/symtrax | F9 `f09_steuerspalte` |
| Q9 | Odoo `l10n_din5008` Report | https://github.com/odoo/odoo/blob/master/addons/l10n_din5008/report/din5008_report.xml | F7 `f07_din5008` |
| Q10 | Microsoft Dynamics 365 Business Central, Report 1306 „Standard Sales – Invoice“ | https://learn.microsoft.com/en-us/dynamics365/business-central/application/base-application/report/microsoft.sales.history.standard-sales---invoice | F8 `f08_bildkopf` |

Nicht als öffentliches Muster-PDF gefunden: sevDesk, SAP Business One, Sage, Billbee.

## Layout-Notizen und Abweichungen

Regel: Wortlaut und Anordnung folgen der Vorlage. Die Familien sind **nicht** an den heutigen Erkennungscode
angepasst; was der Code damit nicht liest, steht als „bekannte Lücke“ in der README der Familie und ist ein
Befund, kein Fehler im Set. Abweichungen von der Vorlage gibt es nur aus drei Gründen: (1) das Merkmal ist OUT
(siehe `README.md`), (2) es gibt im Datenmodell kein Feld dafür, (3) eine Variante, die die Vorlage nicht zeigt
(z. B. Skonto), musste im Satzbau der Vorlage ergänzt werden.

**Q1 weclapp → F1**
- Übernommen: Kontaktblock rechts oben, Absenderzeile, „Rechnung“, Infoblock links Rechnungs-Nr. / Auftrags-Nr. /
  Komission (Schreibweise der Vorlage) / Kunden-Nr. / Bestell-Nr., rechts Rechnungsdatum / Lieferdatum /
  Bearbeiter / Telefon / E-Mail; Tabelle mit „Preis/Einh. (€)“ und „Gesamt (€)“; Summen „Summe Netto“,
  „19,00% USt. auf … €“, „Endsumme“ mit vorangestelltem €; „Lieferbedingung“; „10 Tage 5% Skonto, 30 Tage ohne
  Abzug“; Fuß mit Konto/BLZ/IBAN/BIC.
- Ergänzt (Grund 3): „N Tage ohne Abzug“ ohne Skonto; festes Datum „Zahlbar bis TT.MM.JJ ohne Abzug“.
- Die Auftrags-Nr. ist die Nummer des Verkäufers; sie steht in `test_flags.auftragsnummer`, nicht in BT-13.

**Q2 Lexware → F2**
- Übernommen: Logo rechts oben, unterstrichene Absenderzeile, rechter Block mit „Tel.:“, „E-Mail:“,
  „Kundennummer:“, „Liefer-/Leistungsdatum:“; „Honorarrechnung Nr. …“ links, „Ort, den …“ rechts (ohne eigenes
  Rechnungsdatum-Label); Anrede und Einleitungssatz; Tabelle Pos. / Menge („1 Stk.“) / Bezeichnung /
  Einzelpreis / Gesamtpreis mit grauer Kopfzeile; Zwischensumme / 19% MwSt. / Gesamtbetrag; Zahltext „Zahlung
  innerhalb von 14 Tagen ab Rechnungseingang ohne Abzüge an die unten angegebene Bankverbindung.“; „Bei Rückfragen
  …“, „Herzliche Grüße,“; zweizeiliger Fuß.
- Abweichung: Das Datum in „Ort, den …“ ist ausgeschrieben (Vorlage: TT.MM.JJJJ) – das ist die Datumsvariante
  dieser Familie.
- Ergänzt (Grund 3): Skonto („… mit 2 % Skonto, innerhalb von 30 Tagen ohne Abzüge …“) und festes Datum („Zahlung
  bis zum 19. November 2026 ohne Abzüge …“) im Satzbau der Vorlage.
- A5 (Beleg 4): Fuß in vier statt zwei Zeilen, weil die Zeilen bei 7 pt nicht in die Breite passen.

**Q4 JTL business 2.0 → F3**
- Übernommen: großes Logo, rechte Seitenleiste mit senkrechter Linie auf jeder Seite (Absender, USt-IdNr.,
  Gläubiger-IdNr., Tel/Fax, Mail/Web, Bearbeiter, Bankblock), darunter auf Höhe der Tabelle die Belegdaten als
  „Label über Wert“ auf jeder Seite; „RECHNUNG“, „Ort, den …“, „Seite: 1 / 3“; Tabelle neben der Leiste mit
  Pos / Menge („2 Stück“) / Art. Nr. / Bezeichnung / Netto EP / MwSt / Netto GP und kleiner Druckbeschreibung;
  „Zwischensumme“ unten, „Übertrag von Seite 1 42760,41“ ohne Tausenderpunkt und € oben; Gesamt Netto / zzgl.
  MwSt (19 %) / Rechnungsbetrag; Versandart / Zahlungsart / „Zahlungsziel: N Tage“ und Anmerkung; kein Fuß.
- Weggelassen: Rabattzeile, Lieferadresse (beide OUT), „Ihre USt.-Ident.Nr“ des Käufers (Grund 2).
- Ergänzt (Grund 3): Skonto als Anmerkungszeile; Eigentumsvorbehalt als zweite Anmerkung.
- Die Auftragsnummer ist die Nummer des Verkäufers (`test_flags.auftragsnummer`); BT-13 ist leer.

**Q3 easybill → F4**
- Übernommen: Logo-Kasten rechts oben, kleine Absenderzeile, Block „So erreichen Sie uns“ (Internet / E-Mail /
  Telefon / Telefax / Mobil / Steuer-Nr. / USt-IDNr.), darunter Datum: / Kunde: / Rechnung:; Anrede,
  „nachfolgend berechnen wir Ihnen wie vorab besprochen:“, „Rechnung <Nr.>“ fett, „Das Rechnungsdatum entspricht
  dem Leistungsdatum“; Tabelle Pos / Art-Nr. / Bezeichnung / Menge („4,5 Std.“) / Einzelpreis / Betrag;
  Nettobetrag / Umsatzsteuer 19% / Rechnungsbetrag; „Bitte begleichen Sie den offenen Betrag bis zum … an die
  unten aufgeführte Bankverbindung.“; Fuß in drei Spalten. Schrift Helvetica statt Arial.
- Ergänzt (Grund 3): Skontosatz vor dem Zahlsatz.
- Keine Bestellnummer, weil die Vorlage keine hat. Prüfen-Fall: Satz zum Leistungsdatum weggelassen (Beleg 5).

**Q5 JTL creativ 1.4 → F5**
- Übernommen: Logo links, Firmenblock rechts, Rechnung-Nr: / Auftrag-Nr: / Datum: / Kunden-Nr: mit um 1,8 pt
  tiefer gesetzten Werten (wie im Vorlagen-PDF), „Rechnung“, „Seite: 1 von N“; Tabelle Pos. / Menge („2 Stück“) /
  Art.-Nr. / Bezeichnung / MwSt. („19,00 %“) / E-Preis / G-Preis, Beträge ohne Tausenderpunkt mit „EUR“;
  „Zwischensumme“ / „Übertrag von Seite N“; Gesamt Netto / zzgl. 19,00 MwSt. / Gesamtbetrag; „Zahlungsart:
  Rechnung“, „Zahlungsziel: N Tage“; Fuß in vier Spalten mit „Seite: N / M“.
- Weggelassen: Rabattspalte und Vorauszahlungs-/Gutscheinzeilen (Grund 1), „USt-Nr:“ des Kunden (Grund 2).
- Ergänzt (Grund 3): Skontosatz unter dem Zahlungsziel.
- Die Auftrag-Nr. ist die Nummer des Verkäufers (`test_flags.auftragsnummer`); BT-13 ist leer.

**Q6 DATEV → F6**
- Übernommen: durchgehend Courier, Firmenname groß links oben, „RECHNUNG“ mit Nummer / Datum / Kunden-Nr. /
  Lieferdatum / Auftragsnummer ohne Doppelpunkt, „Lieferung frei Haus“, „Seite N“; Tabelle Pos / Artikel /
  Bezeichnung / Menge / Einheit / USt% / Preis / Betrag EUR; Gruppen-„Zwischensumme“ in der Tabelle;
  „Übertrag“; Zwischensumme / „19% MWSt auf EUR …“ / Endbetrag; „Zahlung: 30 Tage 2,0%; 60 Tage netto“; Fuß mit
  Bank, BLZ, Konto, IBAN, BIC und Registerzeile.
- Ergänzt (Grund 3): „Zahlung: N Tage netto“ ohne Skonto.
- Die Auftragsnummer ist die Nummer des Verkäufers (`test_flags.auftragsnummer`); BT-13 ist leer.

**Q7 Mustangproject → F10**
- Übernommen (Beispielrechnung RE-20201121/508, deutsch gedruckt): Datum oben links, Absenderzeile, Firmenblock
  rechts; „Kunde:“, „Ihre Bestellung“, „Rechnung Nr. … vom …“, „Lieferdatum“; Gittertabelle Menge / Produkt /
  USt / Preis / Gesamt, Einheit im Produktnamen; Nettosumme, „zzgl. USt“, Steuertabelle je Satz, „USt gesamt“,
  „Zahlbetrag“, „Bitte überweisen bis …“; Fuß rechts, „Seite 1/1“.
- Weggelassen: Preise mit drei Nachkommastellen (Grund 2, BT-146 hat im Rahmen zwei Stellen).
- Ergänzt (Grund 3): Skontosatz „Bei Zahlung bis … gewähren wir X % Skonto.“
- Ganze Familie Hold-out; kein Label über Wert.

**Q8 Symtrax → F9**
- Übernommen (Compleo-Beispiel „Handelsrechnung“): Courier, „Handelsrechnung Nr. … vom …“, „Label : Wert“ mit
  ausgerichteten Doppelpunkten, Blöcke „Verkäufer:“ / „Käufer:“, „Rechnung gemäß Bestellung vom …“; zweizeiliger
  Tabellenkopf, Steuerspalte je Position („7 % VAT (S)“), Menge „20 Stk“; Positionssumme / Rechnungssumme ohne
  USt. / Steuerbetrag / Bruttosumme / Zahlbetrag mit einem Steuerbetrag über beide Sätze; „Zahlbar innerhalb
  30 Tagen netto bis …, 3% Skonto innerhalb 10 Tagen bis …“.
- Weggelassen: Steuer-Aufschlüsselungstabelle (Vorgabe: eine USt-Zeile), Zu-/Abschläge auf Belegebene
  (Grund 1, BG-20/21), Anzahlungen (Grund 2).
- Ergänzt (Grund 3): „Rechnung gemäß Lieferung“ für Belege ohne Bestellnummer.

**Q9 Odoo l10n_din5008 → F7**
- Übernommen: Logo links, Firmenanschrift rechts, Anschriftfeld mit Absenderzeile, Informationsblock
  Rechnungsnr. / Rechnungsdatum / Fälligkeitsdatum / Lieferdatum / Quelle / Referenz (Bezeichnungen der deutschen
  Übersetzung); „Rechnung INV/2026/000NN“; Tabelle Beschreibung / Menge / Einzelpreis / Steuern / Betrag;
  Nettobetrag / Umsatzsteuer 19% / Gesamt; „Zahlungsbedingungen: N Tage“, „Bitte verwenden Sie die folgende
  Mitteilung für Ihre Zahlung: …“; Fuß mit USt-IdNr., HRB Nr:, IBAN:, BIC:. Schrift Helvetica statt Lato.
- Keine Kundennummer, weil der Bericht keine druckt (`kundennummer_gedruckt = False`, Soll leer).
- „Quelle“ = Verkaufsauftrag des Verkäufers (`test_flags.quelle`), „Referenz“ = BT-13.

**Q10 Business Central 1306 → F8**
- Übernommen: Times, Firmenblock rechts in zwei Spalten (Telefonnr. / E-Mail / Homepage / USt-IdNr. / Bank /
  IBAN / SWIFT-Code), Debitorennr. und „Ihre Referenz“ unter der Anschrift, „Rechnung“ mit Rechnungsnr. /
  Buchungsdatum / Fälligkeitsdatum / Lieferdatum / Zahlungsbedingungen / Lieferbedingungen; Tabelle Nr. /
  Beschreibung / Menge / Einheit / VK-Preis / MwSt. % / Betrag; Zwischensumme / Gesamt EUR ohne MwSt. / 19 %
  MwSt. / Gesamt EUR inkl. MwSt.; Folgeseiten mit Kopf und „Seite N“, kein Übertrag.
- Abweichung: Briefkopf und Fußzeile als Bild (Briefpapier als Bild, wie es BC-Kunden hinterlegen); das ist das
  Merkmal dieser Familie.
- Weggelassen: Lieferadresse (Grund 1), Zeilenrabatt (Grund 1).
- Ganze Familie Hold-out; genau ein Postfach-Beleg (Nr. 4).
