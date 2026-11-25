# Test-Setup „Steuerfälle“ (ab 0.9.7, alle Daten erfunden)

Druck-PDFs dreier erfundener Absender für den Modus **Nur PDF** mit fertig angelernten Vorlagen.

| Rechnung | Absender | Fall | Besonderheit |
|---|---|---|---|
| LM-26-2001 | Lichtbogen Messtechnik | S 19 % | Steuerspalte „19 %“ |
| LM-26-2002 | Lichtbogen Messtechnik | AE | Reverse Charge § 13b, „Ihre USt-IdNr.“ |
| LM-26-2003 | Lichtbogen Messtechnik | K | igL nach Österreich (ATU…), Landzeile in der Anschrift |
| LM-26-2004 | Lichtbogen Messtechnik | G | Ausfuhr in die Schweiz |
| LM-26-2005 | Lichtbogen Messtechnik | O | nicht im Inland steuerbar, Kunde USA |
| LM-26-2006 | Lichtbogen Messtechnik | S, USD | Kurszeile „1 EUR = 1,0850 USD“ + USt in EUR |
| LM-26-2007 | Lichtbogen Messtechnik | AE + S | gemischt: Steuerfall je Position |
| WE-26-0301 | Estrichbau Wendel | S 19 % | Satz nur in den Summen |
| WE-26-0302 | Estrichbau Wendel | AE | Satz nur in den Summen, Fall aus dem Steuerhinweis |
| GL-26-0014/15 | Gartenpflege Lindner | § 19 UStG | Kleinunternehmer (Schalter am Absender) |

- **Steuerspalte im Druck** (Lichtbogen): Die Spalte „USt“ ist als Spaltenrahmen „USt-Satz“ angelernt; „19 %“ → S,
  „0 %“ → Steuerfall je Rechnung aus dem Steuerhinweis im Druck (AE/K/G/O). Gemischte Rechnungen gehen.
- **Satz nur in den Summen** (Wendel): ein Steuerfall je Rechnung – mit Steuerhinweis der Sonderfall, ohne Hinweis
  der Satz aus der Summenzeile („zzgl. 19 % USt“).
- **Kleinunternehmer** (Lindner): Steuerfall „Kleinunternehmer (§ 19 UStG)“, fest.

Dateien: `eingang/` (PDFs), `profil-*.yaml` + `angelernt/` (Profile und Vorlagen), `absender-*.csv`,
`konfiguration-nur-pdf.yaml`, `erzeuge_beispiele.py` (erzeugt alles neu; `--anlernen` lernt die Vorlagen wie im
Assistenten an). In den Beispielprofilen steht `nur_pdf_ab: 1` (üblich 5), damit die Vorlagen sofort gelten.

Ablauf: `fakturafalter -c beispiele/steuerfaelle/konfiguration-nur-pdf.yaml`, dann die PDFs aus `eingang/` in
`laufzeit/steuerfaelle-nur-pdf/Eingang` legen. Alle elf Rechnungen werden ohne Nachfrage erzeugt (Mustang + KoSIT
gültig); LM-26-2006 zeigt zusätzlich die Warnung „Rechnung in USD, Zahlungsart SEPA …“.
