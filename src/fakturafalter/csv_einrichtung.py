# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""CSV einrichten (Assistent „PDF + CSV“): Format erkennen, Spalten zuordnen, normales CSV-Profil schreiben.

Ergebnis ist ein Profil ``aufbau.art: zeile_je_position`` wie ``beispiele/profil-variante-a.json`` – es läuft
durch denselben Adapter wie jedes handgeschriebene Profil. Ohne GUI testbar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from . import codelisten, steuerfaelle, tabellen
from .pdferkennung import einheit_code
from .werte import csv_lesen, dekodieren, trennzeichen_erkennen

# (Feld, Anzeige, Teil, Typ, Pflicht)
FELDER: list[tuple[str, str, str, str, bool]] = [
    ("BT-1", "Rechnungsnummer", "kopf", "text", True),
    ("BT-2", "Rechnungsdatum", "kopf", "datum", True),
    ("BT-72", "Leistungs- oder Lieferdatum", "kopf", "datum", False),
    ("kundennummer", "Kundennummer", "kopf", "text", False),
    ("BT-44", "Kundenname (Zeile 1)", "kopf", "text", True),
    ("kunden_name_2", "Kundenname (Zeile 2)", "kopf", "text", False),
    ("kunden_name_3", "Kundenname (Zeile 3)", "kopf", "text", False),
    ("BT-50", "Kunde – Straße", "kopf", "text", False),
    ("BT-51", "Kunde – Adresszusatz", "kopf", "text", False),
    ("BT-53", "Kunde – PLZ", "kopf", "text", False),
    ("BT-52", "Kunde – Ort", "kopf", "text", False),
    ("BT-55", "Kunde – Land", "kopf", "text", False),
    ("BT-48", "Kunde – USt-IdNr.", "kopf", "text", False),
    ("BT-49", "E-Rechnungsadresse des Kunden", "kopf", "text", False),
    ("BT-10", "Leitweg-ID / Käuferreferenz", "kopf", "text", False),
    ("BT-13", "Bestellnummer", "kopf", "text", False),
    ("BT-112", "Rechnungsbetrag brutto (nur Kontrolle)", "kopf", "zahl", False),
    ("BT-109", "Rechnungsbetrag netto (nur Kontrolle)", "kopf", "zahl", False),
    ("BT-110", "Summe USt der Rechnung (nur Kontrolle)", "kopf", "zahl", False),
    ("skonto_satz", "Skonto", "kopf", "prozent", False),
    ("skonto_tage", "Skontofrist (Tage)", "kopf", "tage", False),
    ("skonto_basisbetrag", "Skonto-Basisbetrag", "kopf", "zahl", False),
    ("skonto_satz_2", "Skonto 2", "kopf", "prozent", False),
    ("skonto_tage_2", "Skontofrist 2 (Tage)", "kopf", "tage", False),
    ("skonto_basisbetrag_2", "Skonto-Basisbetrag 2", "kopf", "zahl", False),
    ("zahlungsziel_tage", "Zahlungsziel (netto, ohne Skonto)", "kopf", "tage", False),
    ("BT-126", "Positionsnummer", "position", "text", False),
    ("BT-155", "Artikelnummer", "position", "text", False),
    ("BT-153", "Bezeichnung der Position", "position", "text", True),
    ("BT-129", "Menge", "position", "zahl", True),
    ("BT-130", "Einheit", "position", "text", False),
    ("BT-146", "Einzelpreis (netto)", "position", "zahl", True),
    ("BT-149", "Preiseinheit / Preisbasis", "position", "zahl", False),
    ("gesamtpreis_position", "Gesamtpreis der Position (nur Kontrolle)", "position", "zahl", False),
    ("steuer", "Steuersatz oder Steuerschlüssel", "position", "text", True),
    # freiwillig (EN 16931 vollständig, ab 0.6.0)
    ("belegart", "Belegart (Rechnung/Gutschrift/Korrektur)", "kopf", "text", False),
    ("BT-25", "Bezug: ursprüngliche Rechnungsnummer", "kopf", "text", False),
    ("BT-26", "Bezug: Datum der ursprünglichen Rechnung", "kopf", "datum", False),
    ("BT-73", "Leistungszeitraum von", "kopf", "datum", False),
    ("BT-74", "Leistungszeitraum bis", "kopf", "datum", False),
    ("zeilenart", "Zeilenart (Position/Rabatt/Zuschlag)", "position", "text", False),
    ("BT-138", "Rabatt % (Position)", "position", "prozent", False),
    ("BT-136", "Rabatt Betrag (Position)", "position", "zahl", False),
    ("BT-139", "Rabattgrund (Position)", "position", "text", False),
    ("BT-141", "Zuschlag Betrag (Position)", "position", "zahl", False),
    ("BT-148", "Listenpreis der Position (brutto vor Nachlass)", "position", "zahl", False),
    ("BT-147", "Preisnachlass je Einheit", "position", "zahl", False),
    ("BT-94", "Rabatt % (ganze Rechnung)", "kopf", "prozent", False),
    ("BT-92", "Rabatt Betrag (ganze Rechnung)", "kopf", "zahl", False),
    ("BT-97", "Rabattgrund (ganze Rechnung)", "kopf", "text", False),
    ("BT-99", "Zuschlag Betrag (z. B. Fracht)", "kopf", "zahl", False),
    ("BT-101", "Zuschlag % (ganze Rechnung)", "kopf", "prozent", False),
    ("BT-104", "Zuschlaggrund", "kopf", "text", False),
    ("BT-113", "Bereits gezahlt (Anzahlung)", "kopf", "zahl", False),
    ("zahlungsart", "Zahlungsart (Überweisung/Lastschrift)", "kopf", "text", False),
    ("BT-89", "Mandatsreferenz (Lastschrift)", "kopf", "text", False),
    ("BT-91", "IBAN des Kunden (Lastschrift)", "kopf", "text", False),
    ("BT-90", "Gläubiger-ID (Lastschrift)", "kopf", "text", False),
    ("BT-83", "Verwendungszweck", "kopf", "text", False),
    ("BT-22", "Bemerkung zur Rechnung", "kopf", "text", False),
    ("BT-14", "Auftragsnummer", "kopf", "text", False),
    ("BT-11", "Projektnummer", "kopf", "text", False),
    ("BT-12", "Vertragsnummer", "kopf", "text", False),
    ("BT-16", "Lieferscheinnummer", "kopf", "text", False),
    ("BT-15", "Wareneingangsnummer", "kopf", "text", False),
    ("BT-17", "Vergabe-/Losnummer", "kopf", "text", False),
    ("BT-18", "Objektkennung", "kopf", "text", False),
    ("BT-19", "Buchungsreferenz des Kunden (Kostenstelle)", "kopf", "text", False),
    ("BT-70", "Lieferanschrift – Name", "kopf", "text", False),
    ("BT-75", "Lieferanschrift – Straße", "kopf", "text", False),
    ("BT-78", "Lieferanschrift – PLZ", "kopf", "text", False),
    ("BT-77", "Lieferanschrift – Ort", "kopf", "text", False),
    ("BT-80", "Lieferanschrift – Land", "kopf", "text", False),
    ("BT-59", "Zahlungsempfänger (falls abweichend)", "kopf", "text", False),
    ("BT-124", "Link auf Unterlage", "kopf", "text", False),
    ("BT-127", "Positionstext / Notiz", "position", "text", False),
    ("BT-154", "Artikelbeschreibung (lang)", "position", "text", False),
    ("BT-156", "Artikelnummer des Kunden", "position", "text", False),
    ("BT-157", "GTIN / EAN", "position", "text", False),
    ("BT-158", "Warengruppe / Klassifizierung", "position", "text", False),
    ("BT-159", "Ursprungsland", "position", "text", False),
    ("BT-160", "Artikelmerkmal – Name", "position", "text", False),
    ("BT-161", "Artikelmerkmal – Wert", "position", "text", False),
    ("BT-132", "Bestellposition", "position", "text", False),
    ("BT-133", "Buchungsreferenz (Position)", "position", "text", False),
    ("BT-134", "Leistung von (Position)", "position", "datum", False),
    ("BT-135", "Leistung bis (Position)", "position", "datum", False),
    # ab 0.9.5: Zeichnung (als Artikelmerkmale BT-160/161), Objekt und Zuschlag der Position
    ("zeichnungsnummer", "Zeichnungsnummer", "position", "text", False),
    ("index", "Index (Zeichnung)", "position", "text", False),
    ("BT-128", "Objektkennung (Position)", "position", "text", False),
    ("BT-143", "Zuschlag % (Position)", "position", "prozent", False),
    ("BT-144", "Zuschlaggrund (Position)", "position", "text", False),
    # ab 0.9.7: Steuer-Sonderfälle und Fremdwährung
    ("BT-47", "Kunde – Handelsregister / Registernummer", "kopf", "text", False),
    ("steuerhinweis", "Steuerhinweis (z. B. Reverse Charge)", "kopf", "text", False),
    ("BT-5", "Währung", "kopf", "text", False),
    ("kurs", "Umrechnungskurs (1 EUR = … Fremdwährung)", "kopf", "zahl", False),
    ("kursdatum", "Kursdatum", "kopf", "datum", False),
    ("BT-111", "Umsatzsteuer in EUR", "kopf", "zahl", False),
]
FELD = {f[0]: f for f in FELDER}

# Gruppen der Feldliste im Assistenten (rc1).
GRUPPE_REIHENFOLGE = (
    "position",
    "beleg",
    "kunde",
    "summen",
    "nachlass",
    "zahlung",
    "lieferung",
    "referenz",
)
GRUPPE_TITEL = {
    "position": "Position",
    "beleg": "Beleg",
    "kunde": "Kunde / Käufer",
    "summen": "Summen (nur Kontrolle)",
    "nachlass": "Nachlässe und Zuschläge der Rechnung",
    "zahlung": "Zahlung und Skonto",
    "lieferung": "Lieferung",
    "referenz": "Weitere Referenzen",
}
_FELD_GRUPPE_IDS = {
    "position": (
        "BT-153", "BT-129", "BT-146", "steuer", "BT-126", "BT-155", "BT-130", "BT-149",
        "gesamtpreis_position", "BT-148", "BT-147", "BT-138", "BT-136", "BT-139",
        "BT-141", "BT-143", "BT-144", "zeilenart", "BT-154", "BT-127", "BT-156",
        "BT-157", "BT-158", "BT-159", "BT-160", "BT-161", "zeichnungsnummer", "index",
        "BT-132", "BT-133", "BT-128", "BT-134", "BT-135",
    ),
    "beleg": (
        "BT-1", "BT-2", "BT-72", "BT-73", "BT-74", "belegart", "BT-5", "kurs",
        "kursdatum", "BT-25", "BT-26", "BT-22", "steuerhinweis",
    ),
    "kunde": (
        "kundennummer", "BT-44", "kunden_name_2", "kunden_name_3", "BT-50", "BT-51",
        "BT-53", "BT-52", "BT-55", "BT-48", "BT-49", "BT-47",
    ),
    "summen": ("BT-109", "BT-110", "BT-112", "BT-113", "BT-111"),
    "nachlass": ("BT-94", "BT-92", "BT-97", "BT-99", "BT-101", "BT-104"),
    "zahlung": (
        "zahlungsart", "zahlungsziel_tage", "skonto_satz", "skonto_tage",
        "skonto_basisbetrag", "skonto_satz_2", "skonto_tage_2", "skonto_basisbetrag_2",
        "BT-89", "BT-91", "BT-90", "BT-83", "BT-59",
    ),
    "lieferung": ("BT-70", "BT-75", "BT-78", "BT-77", "BT-80", "BT-16", "BT-15"),
    "referenz": ("BT-13", "BT-14", "BT-11", "BT-12", "BT-17", "BT-18", "BT-19", "BT-10", "BT-124"),
}
FELD_GRUPPE = {fid: g for g, ids in _FELD_GRUPPE_IDS.items() for fid in ids}

FELD_TOOLTIP = {
    "gesamtpreis_position": (
        "Wird nicht in die Rechnung übernommen. Fakturafalter rechnet selbst, z. B. "
        "10 Stück × 1,00 € ÷ Preiseinheit 1 = 10,00 €. Weicht die Spalte ab, erscheint "
        "ein Prüffall. In Exporten oft „Gesamtpreis“."
    ),
    "BT-146": "Nettopreis je Preiseinheit, nicht die Zeilensumme. Beispiel: 1,00 € je Stück.",
    "BT-149": (
        "Auf wie viele Einheiten sich der Einzelpreis bezieht, oft 1. Beispiel: "
        "500 Stück zu 4,80 € je 100 Stück = 24,00 €. Leer zählt als 1. In Exporten oft „Preisbasis“."
    ),
    "BT-112": (
        "Summe der ganzen Rechnung laut Warenwirtschaft, nur zum Abgleich – nicht der "
        "Gesamtpreis einer Position."
    ),
    "BT-109": "Nettosumme der ganzen Rechnung, nur zum Abgleich.",
    "BT-110": "Umsatzsteuer der ganzen Rechnung, nur zum Abgleich.",
    "steuer": (
        "Zum Beispiel 19, 19 %, 7 oder ein Schlüssel aus der Warenwirtschaft "
        "(wird später zugeordnet). Nicht die Summe USt. In Exporten oft „USt-Satz“."
    ),
    "BT-44": (
        "Name oder Firma in der Anschrift, erste Zeile. In Exporten oft Kunde1 oder "
        "Kundenbezeichnung 1."
    ),
    "kunden_name_2": "Weitere Namenszeile, z. B. Abteilung oder z. Hd. Nicht die Straße.",
    "kunden_name_3": "Dritte Namenszeile. Nicht die Straße.",
    "BT-1": (
        "Eindeutige Nummer des Belegs. In manchen Exporten „Belegname“, „Belegnummer“ oder „Belegnr“."
    ),
    "BT-2": "Ausstellungsdatum der Rechnung. In Exporten oft „Belegdatum“.",
    "BT-72": (
        "Tag der Leistung oder Lieferung. Alternative: Leistungszeitraum von/bis. "
        "Nicht das Rechnungsdatum."
    ),
    "BT-153": (
        "Artikel- oder Leistungstext der Zeile. In Kommentarzeilen (Menge und Preis leer) "
        "steht hier der Text."
    ),
    "BT-148": (
        "Listenpreis vor einem Nachlass je Einheit. Nicht der Rechnungsbetrag und nicht der "
        "Gesamtpreis der Position."
    ),
    "BT-5": "Zum Beispiel EUR, EURO, € oder USD – wird zu einem ISO-Code (EUR).",
    "BT-49": (
        "Elektronische Adresse für den Rechnungseingang, oft eine E-Mail, aber nicht "
        "automatisch jede Kontakt-Mail."
    ),
    "zahlungsziel_tage": "Frist in Tagen bis zur Zahlung ohne Abzug.",
    "skonto_satz": "Skontosatz in Prozent, z. B. 2 für 2 %. Die Frist steht in „Skontofrist (Tage)“.",
    "skonto_tage": "Anzahl der Tage, binnen derer Skonto gilt.",
    "skonto_tage_2": "Frist der zweiten Skontostufe.",
    "skonto_satz_2": "Satz der zweiten Skontostufe, z. B. 1 für 1 %.",
    "BT-129": "Abgerechnete Menge der Zeile, z. B. 4 oder 4,00.",
    "BT-130": "Mengeneinheit, z. B. Stück oder Stunde. Kann später einem Code zugeordnet werden.",
    "kundennummer": "Nummer des Kunden in der Warenwirtschaft (Käuferkennung, BT-46). Optional.",
    "BT-155": "Eure Artikel- oder Leistungsnummer, z. B. ART-1042.",
}


# Einzeiler für alle übrigen Felder: Bedeutung plus kleines Beispiel (rc1, Skizze § 2.2)
FELD_TOOLTIP.update(
    {
        "BT-50": "Straße und Hausnummer des Kunden. Beispiel: Musterweg 1.",
        "BT-51": "Zweite Adresszeile, z. B. Hinterhaus oder Postfach. Nicht der Name.",
        "BT-53": "Postleitzahl des Kunden. Beispiel: 12345.",
        "BT-52": "Ort des Kunden. Beispiel: Musterstadt.",
        "BT-55": "Land des Kunden als Code oder Name, z. B. DE oder Deutschland.",
        "BT-48": "Umsatzsteuer-Identifikationsnummer des Kunden. Beispiel: DE123456789.",
        "BT-10": "Leitweg-ID oder Referenz des Kunden, bei Behörden Pflicht für die XRechnung. "
        "Beispiel: 991-12345-67.",
        "BT-13": "Bestellnummer des Kunden. Beispiel: B-2026-0815.",
        "skonto_basisbetrag": "Betrag, auf den Skonto gerechnet wird, wenn nicht die ganze Rechnung. "
        "Leer = Rechnungsbetrag.",
        "skonto_basisbetrag_2": "Basisbetrag der zweiten Skontostufe. Leer = Rechnungsbetrag.",
        "BT-126": "Laufende Nummer der Position. Beispiel: 1, 2, 3.",
        "belegart": "Rechnung, Gutschrift oder Korrektur. Leer = Rechnung.",
        "BT-25": "Bei Gutschrift oder Korrektur: Nummer der ursprünglichen Rechnung.",
        "BT-26": "Bei Gutschrift oder Korrektur: Datum der ursprünglichen Rechnung.",
        "BT-73": "Beginn des Leistungszeitraums. Beispiel: 01.11.2026.",
        "BT-74": "Ende des Leistungszeitraums. Beispiel: 30.11.2026.",
        "zeilenart": "Markiert eine Zeile als Position, Rabatt oder Zuschlag. Leer = Position.",
        "BT-138": "Rabatt der Zeile in Prozent, z. B. 10 für 10 %. Nicht der Betrag.",
        "BT-136": "Rabatt der Zeile als Betrag, z. B. 5,00. Nicht der Prozentsatz.",
        "BT-139": "Grund des Rabatts der Zeile. Beispiel: Mengenrabatt.",
        "BT-141": "Zuschlag auf die Zeile als Betrag, z. B. 2,50.",
        "BT-147": "Nachlass je Einheit auf den Listenpreis. Beispiel: Liste 10,00, Nachlass 1,00 "
        "→ Einzelpreis 9,00.",
        "BT-94": "Rabatt auf die ganze Rechnung in Prozent, z. B. 3 für 3 %.",
        "BT-92": "Rabatt auf die ganze Rechnung als Betrag, z. B. 20,00.",
        "BT-97": "Grund des Rabatts auf die ganze Rechnung. Beispiel: Treuerabatt.",
        "BT-99": "Zuschlag auf die ganze Rechnung als Betrag, z. B. Fracht 12,50.",
        "BT-101": "Zuschlag auf die ganze Rechnung in Prozent.",
        "BT-104": "Grund des Zuschlags. Beispiel: Fracht oder Verpackung.",
        "BT-113": "Schon bezahlter Betrag, z. B. eine Anzahlung. Wird vom Zahlbetrag abgezogen.",
        "zahlungsart": "Überweisung oder Lastschrift. Leer = wie in den Zahlungsdaten eingestellt.",
        "BT-89": "Mandatsreferenz der SEPA-Lastschrift. Nur bei Lastschrift.",
        "BT-91": "IBAN, von der abgebucht wird. Nur bei Lastschrift.",
        "BT-90": "Gläubiger-Identifikationsnummer für die Lastschrift. Beispiel: DE98ZZZ09999999999.",
        "BT-83": "Text für die Überweisung. Leer = Rechnungsnummer.",
        "BT-22": "Freier Hinweis auf der Rechnung. Beispiel: Vielen Dank für Ihren Auftrag.",
        "BT-14": "Auftragsnummer, oft aus der Auftragsbestätigung.",
        "BT-11": "Projektnummer oder -bezeichnung des Kunden.",
        "BT-12": "Nummer des Vertrags, auf den sich die Rechnung bezieht.",
        "BT-16": "Nummer des Lieferscheins. Beispiel: LS-4711.",
        "BT-15": "Wareneingangsnummer des Kunden.",
        "BT-17": "Vergabe- oder Losnummer bei öffentlichen Aufträgen.",
        "BT-18": "Kennung eines Objekts, z. B. Zählernummer oder Gebäude.",
        "BT-19": "Kostenstelle oder Buchungskonto des Kunden.",
        "BT-70": "Name der Lieferanschrift, wenn sie von der Rechnungsanschrift abweicht.",
        "BT-75": "Straße der Lieferanschrift.",
        "BT-78": "Postleitzahl der Lieferanschrift.",
        "BT-77": "Ort der Lieferanschrift.",
        "BT-80": "Land der Lieferanschrift, z. B. DE.",
        "BT-59": "Name des Zahlungsempfängers, nur wenn nicht du selbst, z. B. ein Factoring-Dienst.",
        "BT-124": "Link (URL) auf eine Unterlage zur Rechnung.",
        "BT-127": "Notiz zu einer Position. Beispiel: Lieferung KW 48.",
        "BT-154": "Lange Beschreibung des Artikels, zusätzlich zur Bezeichnung.",
        "BT-156": "Artikelnummer, die der Kunde für den Artikel verwendet.",
        "BT-157": "GTIN oder EAN des Artikels. Beispiel: 4012345678901.",
        "BT-158": "Warengruppe oder Klassifizierung, z. B. Zolltarifnummer.",
        "BT-159": "Ursprungsland des Artikels als Code, z. B. DE.",
        "BT-160": "Name eines Artikelmerkmals. Beispiel: Farbe.",
        "BT-161": "Wert eines Artikelmerkmals. Beispiel: blau.",
        "BT-132": "Positionsnummer in der Bestellung des Kunden.",
        "BT-133": "Kostenstelle oder Buchungskonto des Kunden für diese Zeile.",
        "BT-134": "Beginn der Leistung dieser Zeile.",
        "BT-135": "Ende der Leistung dieser Zeile.",
        "zeichnungsnummer": "Zeichnungsnummer des Teils. Beispiel: Z-1001.",
        "index": "Änderungsindex der Zeichnung. Beispiel: B.",
        "BT-128": "Kennung eines Objekts für diese Zeile.",
        "BT-143": "Zuschlag auf die Zeile in Prozent.",
        "BT-144": "Grund des Zuschlags der Zeile.",
        "BT-47": "Handelsregister- oder Registernummer des Kunden. Beispiel: HRB 12345.",
        "steuerhinweis": "Hinweis zur Steuer, z. B. Steuerschuldnerschaft des Leistungsempfängers.",
        "kurs": "Umrechnungskurs bei Fremdwährung: 1 EUR = … Fremdwährung. Beispiel: 1,08.",
        "kursdatum": "Datum des Umrechnungskurses.",
        "BT-111": "Umsatzsteuer der Rechnung in EUR, wenn die Rechnung in einer Fremdwährung ist.",
    }
)


# Offizielle Bezeichnungen nach EN 16931-1 (deutsche Fassung / englisch), rc2. Unsere Labels bleiben
# verständlich („Kunde – Ort“); im Tooltip steht zusätzlich der Name im Standard.
STANDARD_NAME: dict[str, tuple[str, str]] = {
    "BT-1": ("Rechnungsnummer", "Invoice number"),
    "BT-2": ("Rechnungsdatum", "Invoice issue date"),
    "BT-3": ("Code für den Rechnungstyp", "Invoice type code"),
    "BT-5": ("Code für die Rechnungswährung", "Invoice currency code"),
    "BT-9": ("Fälligkeitsdatum der Zahlung", "Payment due date"),
    "BT-10": ("Käuferreferenz", "Buyer reference"),
    "BT-11": ("Projektreferenz", "Project reference"),
    "BT-12": ("Vertragsreferenz", "Contract reference"),
    "BT-13": ("Bestellreferenz", "Purchase order reference"),
    "BT-14": ("Auftragsreferenz", "Sales order reference"),
    "BT-15": ("Referenz auf die Wareneingangsmeldung", "Receiving advice reference"),
    "BT-16": ("Referenz auf die Versandanzeige", "Despatch advice reference"),
    "BT-17": ("Referenz auf die Ausschreibung oder das Los", "Tender or lot reference"),
    "BT-18": ("Objektkennung", "Invoiced object identifier"),
    "BT-19": ("Buchungsreferenz des Käufers", "Buyer accounting reference"),
    "BT-20": ("Zahlungsbedingungen", "Payment terms"),
    "BT-22": ("Bemerkung zur Rechnung", "Invoice note"),
    "BT-25": ("Referenz auf die vorausgegangene Rechnung", "Preceding Invoice reference"),
    "BT-26": ("Ausstellungsdatum der vorausgegangenen Rechnung", "Preceding Invoice issue date"),
    "BT-44": ("Name des Käufers", "Buyer name"),
    "BT-46": ("Kennung des Käufers", "Buyer identifier"),
    "BT-47": ("Kennung der rechtlichen Registrierung des Käufers", "Buyer legal registration identifier"),
    "BT-48": ("Umsatzsteuer-Identifikationsnummer des Käufers", "Buyer VAT identifier"),
    "BT-49": ("Elektronische Adresse des Käufers", "Buyer electronic address"),
    "BT-50": ("Zeile 1 der Anschrift des Käufers", "Buyer address line 1"),
    "BT-51": ("Zeile 2 der Anschrift des Käufers", "Buyer address line 2"),
    "BT-52": ("Ort des Käufers", "Buyer city"),
    "BT-53": ("Postleitzahl des Käufers", "Buyer post code"),
    "BT-55": ("Ländercode des Käufers", "Buyer country code"),
    "BT-59": ("Name des Zahlungsempfängers", "Payee name"),
    "BT-70": ("Name des Waren- oder Dienstleistungsempfängers", "Deliver to party name"),
    "BT-72": ("Tatsächliches Lieferdatum", "Actual delivery date"),
    "BT-73": ("Anfangsdatum des Rechnungszeitraums", "Invoicing period start date"),
    "BT-74": ("Enddatum des Rechnungszeitraums", "Invoicing period end date"),
    "BT-75": ("Zeile 1 der Lieferanschrift", "Deliver to address line 1"),
    "BT-77": ("Ort der Lieferanschrift", "Deliver to city"),
    "BT-78": ("Postleitzahl der Lieferanschrift", "Deliver to post code"),
    "BT-80": ("Ländercode der Lieferanschrift", "Deliver to country code"),
    "BT-81": ("Code für die Zahlungsart", "Payment means type code"),
    "BT-83": ("Verwendungszweck", "Remittance information"),
    "BT-89": ("Kennung der Mandatsreferenz", "Mandate reference identifier"),
    "BT-90": ("Kennung des Gläubigers", "Bank assigned creditor identifier"),
    "BT-91": ("Kennung des zu belastenden Kontos", "Debited account identifier"),
    "BT-92": ("Betrag des Nachlasses auf Dokumentenebene", "Document level allowance amount"),
    "BT-94": ("Prozentsatz des Nachlasses auf Dokumentenebene", "Document level allowance percentage"),
    "BT-97": ("Grund für den Nachlass auf Dokumentenebene", "Document level allowance reason"),
    "BT-99": ("Betrag der Abgabe auf Dokumentenebene", "Document level charge amount"),
    "BT-101": ("Prozentsatz der Abgabe auf Dokumentenebene", "Document level charge percentage"),
    "BT-104": ("Grund für die Abgabe auf Dokumentenebene", "Document level charge reason"),
    "BT-109": ("Gesamtbetrag ohne Umsatzsteuer", "Invoice total amount without VAT"),
    "BT-110": ("Gesamtbetrag der Umsatzsteuer", "Invoice total VAT amount"),
    "BT-111": (
        "Gesamtbetrag der Umsatzsteuer in der Abrechnungswährung",
        "Invoice total VAT amount in accounting currency",
    ),
    "BT-112": ("Gesamtbetrag einschließlich Umsatzsteuer", "Invoice total amount with VAT"),
    "BT-113": ("Vorauszahlungsbetrag", "Paid amount"),
    "BT-120": ("Grund der Steuerbefreiung", "VAT exemption reason text"),
    "BT-124": ("Externe Unterlage (Speicherort)", "External document location"),
    "BT-126": ("Kennung der Rechnungsposition", "Invoice line identifier"),
    "BT-127": ("Bemerkung zur Rechnungsposition", "Invoice line note"),
    "BT-128": ("Objektkennung auf Ebene der Rechnungsposition", "Invoice line object identifier"),
    "BT-129": ("In Rechnung gestellte Menge", "Invoiced quantity"),
    "BT-130": ("Einheit der in Rechnung gestellten Menge", "Invoiced quantity unit of measure code"),
    "BT-131": ("Nettobetrag der Rechnungsposition", "Invoice line net amount"),
    "BT-132": ("Referenz auf die Bestellposition", "Referenced purchase order line reference"),
    "BT-133": ("Buchungsreferenz des Käufers für die Rechnungsposition", "Invoice line Buyer accounting reference"),
    "BT-134": ("Anfangsdatum des Zeitraums der Rechnungsposition", "Invoice line period start date"),
    "BT-135": ("Enddatum des Zeitraums der Rechnungsposition", "Invoice line period end date"),
    "BT-136": ("Betrag des Nachlasses auf Ebene der Rechnungsposition", "Invoice line allowance amount"),
    "BT-138": ("Prozentsatz des Nachlasses auf Ebene der Rechnungsposition", "Invoice line allowance percentage"),
    "BT-139": ("Grund für den Nachlass auf Ebene der Rechnungsposition", "Invoice line allowance reason"),
    "BT-141": ("Betrag der Abgabe auf Ebene der Rechnungsposition", "Invoice line charge amount"),
    "BT-143": ("Prozentsatz der Abgabe auf Ebene der Rechnungsposition", "Invoice line charge percentage"),
    "BT-144": ("Grund für die Abgabe auf Ebene der Rechnungsposition", "Invoice line charge reason"),
    "BT-146": ("Nettopreis des Artikels", "Item net price"),
    "BT-147": ("Nachlass auf den Artikelpreis", "Item price discount"),
    "BT-148": ("Bruttopreis des Artikels", "Item gross price"),
    "BT-149": ("Basismenge zum Artikelpreis", "Item price base quantity"),
    "BT-151": ("Code der Umsatzsteuerkategorie des Artikels", "Invoiced item VAT category code"),
    "BT-152": ("Umsatzsteuersatz des Artikels", "Invoiced item VAT rate"),
    "BT-153": ("Artikelname", "Item name"),
    "BT-154": ("Artikelbeschreibung", "Item description"),
    "BT-155": ("Artikelkennung des Verkäufers", "Item Seller's identifier"),
    "BT-156": ("Artikelkennung des Käufers", "Item Buyer's identifier"),
    "BT-157": ("Kennung des Artikels nach registriertem Schema", "Item standard identifier"),
    "BT-158": ("Kennung der Artikelklassifizierung", "Item classification identifier"),
    "BT-159": ("Ursprungsland des Artikels", "Item country of origin"),
    "BT-160": ("Name des Artikelattributs", "Item attribute name"),
    "BT-161": ("Wert des Artikelattributs", "Item attribute value"),
}

# Eigene Schlüssel → BT-Nummern im Standard (für Tooltip und Suche); leer = kein eigenes Feld im Standard
FELD_STANDARD: dict[str, tuple[str, ...]] = {
    "kundennummer": ("BT-46",),
    "kunden_name_2": ("BT-44",),
    "kunden_name_3": ("BT-44",),
    "gesamtpreis_position": ("BT-131",),
    "steuer": ("BT-151", "BT-152"),
    "belegart": ("BT-3",),
    "zahlungsart": ("BT-81",),
    "zahlungsziel_tage": ("BT-9",),
    "skonto_satz": ("BT-20",),
    "skonto_tage": ("BT-20",),
    "skonto_basisbetrag": ("BT-20",),
    "skonto_satz_2": ("BT-20",),
    "skonto_tage_2": ("BT-20",),
    "skonto_basisbetrag_2": ("BT-20",),
    "zeichnungsnummer": ("BT-160", "BT-161"),
    "index": ("BT-160", "BT-161"),
    "steuerhinweis": ("BT-120",),
    "zeilenart": (),
    "kurs": (),
    "kursdatum": (),
}

_STANDARD_ZUSATZ = {
    "kunden_name_2": ("Teil von", "part of"),
    "kunden_name_3": ("Teil von", "part of"),
    "skonto_satz": ("als Skonto-Angabe in", "as discount entry in"),
    "skonto_tage": ("als Skonto-Angabe in", "as discount entry in"),
    "skonto_basisbetrag": ("als Skonto-Angabe in", "as discount entry in"),
    "skonto_satz_2": ("als Skonto-Angabe in", "as discount entry in"),
    "skonto_tage_2": ("als Skonto-Angabe in", "as discount entry in"),
    "skonto_basisbetrag_2": ("als Skonto-Angabe in", "as discount entry in"),
    "zahlungsziel_tage": ("daraus berechnet:", "used to calculate"),
    "zeichnungsnummer": ("als Artikelattribut", "as item attribute"),
    "index": ("als Artikelattribut", "as item attribute"),
}
_KEIN_FELD = {
    "zeilenart": (
        "kein eigenes Feld; steuert Nachlass oder Abgabe der Position (BG-27/BG-28)",
        "no field of its own; controls line allowance or charge (BG-27/BG-28)",
    ),
    "kurs": (
        "kein eigenes Feld; dient der Umrechnung für BT-111",
        "no field of its own; used for the conversion of BT-111",
    ),
    "kursdatum": ("kein eigenes Feld; Angabe zum Umrechnungskurs", "no field of its own; exchange rate date"),
}


def standard_bts(fid: str) -> tuple[str, ...]:
    """BT-Nummern im Standard zu einem Feld (eigene Schlüssel über FELD_STANDARD)."""
    if fid.startswith("BT-"):
        return (fid,)
    return FELD_STANDARD.get(fid, ())


def standard_zeile(fid: str, sprache: str = "de") -> str:
    """Letzte Tooltip-Zeile: „Im Standard: BT-52 Ort des Käufers (Buyer city)“ (rc2)."""
    en = sprache == "en"
    kopf = "In the standard:" if en else "Im Standard:"
    if fid in _KEIN_FELD:
        return f"{kopf} {_KEIN_FELD[fid][1 if en else 0]}"
    teile = []
    for bt in standard_bts(fid):
        de_name, en_name = STANDARD_NAME[bt]
        teile.append(f"{bt} {en_name}" if en else f"{bt} {de_name} ({en_name})")
    if not teile:
        return ""
    zusatz = _STANDARD_ZUSATZ.get(fid)
    text = (" and " if en else " und ").join(teile)
    if zusatz:
        text = f"{zusatz[1 if en else 0]} {text}"
    return f"{kopf} {text}"


def tooltip(fid: str, sprache: str = "de", erklaerung: str | None = None) -> str:
    """Tooltip eines Feldes: Erklärung (übersetzt übergeben) und am Ende der Name im Standard."""
    tip = erklaerung if erklaerung is not None else FELD_TOOLTIP.get(fid, "")
    std = standard_zeile(fid, sprache)
    return f"{tip}\n{std}" if tip and std else (tip or std)


def bt_kurz(fid: str) -> str:
    """Grau neben dem Label: die amtliche BT-Nummer, nur bei echten BT-Feldern (wie rc1)."""
    return fid if fid.startswith("BT-") else ""


def felder_in_gruppe(gruppe: str, *, wiederholend: bool) -> list[str]:
    """Feld-IDs einer Gruppe, Pflichtfelder zuerst. Positionsfelder nur im wiederholenden Block."""
    ids = [f for f in _FELD_GRUPPE_IDS.get(gruppe, ()) if f in FELD]
    if not wiederholend:
        ids = [f for f in ids if FELD[f][2] != "position"]
    reihe = list(ids)
    ids.sort(key=lambda f: (0 if FELD[f][4] else 1, reihe.index(f)))
    return ids


def _such(s: str) -> str:
    """Normalisiert für die Suche; Umlaute und ae/oe/ue gelten gleich („Kaeufer“ = „Käufer“)."""
    return _norm(s or "").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def suche_felder(frage: str, *, wiederholend: bool) -> list[str]:
    """Feld-IDs, deren Label, Tooltip, Synonym, BT-Nummer oder Name im Standard zur Frage passen
    (Reihenfolge der Gruppen). „Käufer“/„Buyer“ finden die Kundenfelder, „Verkäufer“/„Seller“ die des
    Verkäufers (rc2)."""
    q = _such(frage)
    treffer: list[str] = []
    for g in GRUPPE_REIHENFOLGE:
        if g == "position" and not wiederholend:
            continue
        for fid in felder_in_gruppe(g, wiederholend=wiederholend):
            if not q:
                treffer.append(fid)
                continue
            label = _such(FELD[fid][1])
            tip = _such(FELD_TOOLTIP.get(fid, ""))
            syn = _such(_SYNONYME.get(fid, ""))
            std = _such(" ".join(" ".join((bt, *STANDARD_NAME.get(bt, ()))) for bt in standard_bts(fid)))
            rolle = _such(_KUNDE_KAEUFER.get(fid, ""))
            if "verkaeufer" not in q:  # „Käufer“ soll nicht über „Verkäufer“ treffen
                tip, std, rolle = (x.replace("verkaeufer", "-") for x in (tip, std, rolle))
            if (
                q in label
                or q in tip
                or q in syn
                or q in std
                or q in rolle
                or q in fid.lower().replace("-", "").replace("_", "")
            ):
                treffer.append(fid)
    return treffer


def anzeige_feld(fid: str, mit_bt: bool = False) -> str:
    """Sichtbare Zeile in der Auswahlliste: Label und Pflichtstern. Die amtliche BT-Nummer zeichnet die
    Liste ab rc2 grau daneben (``bt_kurz``); ``mit_bt`` hängt sie für reine Texte in Klammern an."""
    if fid not in FELD:
        return fid
    _i, label, _teil, _typ, pflicht = FELD[fid]
    stern = " *" if pflicht else ""
    bt = f" ({fid})" if mit_bt and fid.startswith("BT-") else ""
    return f"{label}{stern}{bt}"


# Suche: „Käufer“/„Buyer“ finden alle Kundenfelder, „Verkäufer“/„Seller“ die Felder des Verkäufers (rc2)
_KUNDE_KAEUFER = {
    fid: "käuferbuyer" for fid in ("kundennummer", "BT-44", "kunden_name_2", "kunden_name_3", "BT-50", "BT-51",
                                   "BT-53", "BT-52", "BT-55", "BT-48", "BT-49", "BT-47", "BT-10", "BT-19")
}
_KUNDE_KAEUFER.update({fid: "verkäuferseller" for fid in ("BT-155", "BT-59")})

# Freiwillige Felder ab 0.6.0 nur bei genauem Spaltennamen vorschlagen (kein Wortanfang: „Versanddatum“ ≠ Fracht)
NUR_GENAU = frozenset(f[0] for f in FELDER[FELDER.index(FELD["belegart"]) :])

_SYNONYME = {
    "BT-1": "rechnungsnummer rechnungsnr renr rgnr belegnr belegnummer belegname invoicenumber invoiceno invoice rechnung beleg nr nummer",
    "BT-2": "rechnungsdatum belegdatum rgdatum redatum datum invoicedate issuedate date",
    "BT-72": "leistungsdatum lieferdatum deliverydate leistung",
    "kundennummer": "kundennummer kundennr kdnr kdnummer kundenid customerid customerno debitor debitornr",
    "BT-44": "kundenbezeichnung1 kundenbezeichnung kundename1 name1 "
    "kundenname kunde name firma empfaenger empfänger customername customer",
    "kunden_name_2": "kundenbezeichnung2 kundename2 kunde2 name2 firma2",
    "kunden_name_3": "kundenbezeichnung3 kundename3 kunde3 name3 firma3",
    "BT-50": "strasse straße street anschrift adresse",
    "BT-51": "adresszusatz zusatz adresszeile2",
    "BT-53": "plz postleitzahl zip postcode",
    "BT-52": "ort stadt city",
    "BT-55": "land country",
    "BT-48": "ustid ustidnr kundeustid vatid",
    "BT-49": "email emailadresse erechnungsadresse",
    "BT-10": "leitwegid leitweg buyerreference käuferreferenz kaeuferreferenz",
    "BT-13": "bestellnummer bestellnr ihrebestellung bestellung ordernumber order",
    "BT-112": "summebrutto bruttosumme gesamtbrutto brutto gesamtbetrag total",
    "BT-109": "summenetto nettosumme gesamtnetto nettototal",
    "BT-110": "summeust ustsumme gesamtust mwstsumme",
    "skonto_satz": "skonto skontosatz skonto% skontobetrag",
    "skonto_tage": "zahlungszielmitskonto skontofrist skontotage",
    "skonto_basisbetrag": "skontobasisbetrag basisbetragskonto skontobasis",
    "skonto_satz_2": "skonto2 skontosatz2 skonto%2",
    "skonto_tage_2": "zahlungszielmitskonto2 skontofrist2 skontotage2",
    "skonto_basisbetrag_2": "skontobasisbetrag2 basisbetragskonto2 skontobasis2",
    "zahlungsziel_tage": "zahlungszielohneabzug zahlungsziel nettoziel nettotage zieltage",
    "BT-126": "pos position posnr zeile line",
    "BT-155": "artikelnummer artikelnr artnr sku artikel",
    "BT-153": "bezeichnung artikelbezeichnung beschreibung text description leistungstext",
    "BT-129": "menge anzahl qty quantity",
    "BT-130": "einheit me mengeneinheit unit",
    "BT-146": "einzelpreisnetto einzelpreis epnetto ep nettopreis preis unitprice price",
    "BT-149": "preiseinheit pe preisbasis",
    "gesamtpreis_position": "gesamtpreis positionsgesamtpreis positionsgesamt zeilenbetrag zeilensumme lineamount posgesamt gpnetto gp positionsbetrag nettobetrag betrag",
    "steuer": "steuersatz steuerschluessel steuerschlüssel stschl mwst mwstsatz ust ustsatz steuer vat tax",
    "belegart": "belegart belegtyp dokumentart rechnungsart doctype documenttype",
    "BT-25": "bezugauf bezugsrechnungsnummer ursprungsrechnung bezugsrechnung originalrechnung rechnungsbezug korrekturzu",
    "BT-26": "bezugvom bezugsrechnungsdatum ursprungsdatum bezugsdatum originaldatum",
    "BT-73": "zeitraumvon leistungvon abrechnungvon",
    "BT-74": "zeitraumbis leistungbis abrechnungbis",
    "zeilenart": "zeilenart positionsart postyp linetype",
    "BT-138": "rabattprozent rabattsatz rabatt% nachlassprozent discountpercent",
    "BT-136": "rabattbetrag nachlassbetrag nachlass discountamount",
    "BT-139": "rabattgrund nachlassgrund",
    "BT-141": "zuschlagbetrag zuschlag",
    "BT-148": "bruttopreis listenpreis bruttoeinzelpreis",
    "BT-147": "preisnachlass",
    "BT-94": "belegrabattprozent gesamtrabattprozent",
    "BT-92": "belegrabatt gesamtrabatt",
    "BT-97": "belegrabattgrund",
    "BT-99": "fracht frachtkosten versandkosten versand porto",
    "BT-104": "zuschlaggrund frachtgrund",
    "BT-113": "anzahlung vorauszahlung bereitsgezahlt prepaid",
    "zahlungsart": "zahlungsart zahlart zahlweise paymentmethod",
    "BT-89": "mandatsreferenz mandatsref mandat mandateid",
    "BT-91": "ibankunde ibandeskunden kundeniban zahleriban lastschriftiban iban",
    "BT-90": "glaeubigerid gläubigerid creditorid",
    "BT-83": "verwendungszweck",
    "BT-22": "bemerkung rechnungstext",
    "BT-14": "auftragsnummer auftragsnr auftrag",
    "BT-11": "projektnummer projektnr projekt",
    "BT-12": "vertragsnummer vertragsnr vertrag",
    "BT-16": "lieferscheinnummer lieferscheinnr lieferschein",
    "BT-15": "wareneingang wareneingangsnummer",
    "BT-17": "vergabenummer losnummer",
    "BT-18": "objektkennung objektnummer",
    "BT-19": "kostenstelle buchungsreferenz",
    "BT-70": "liefername lieferempfaenger lieferempfänger",
    "BT-75": "lieferstrasse lieferstraße",
    "BT-78": "lieferplz",
    "BT-77": "lieferort",
    "BT-80": "lieferland",
    "BT-59": "zahlungsempfaenger zahlungsempfänger",
    "BT-127": "positionstext positionsnotiz notiz",
    "BT-154": "langtext artikelbeschreibung",
    "BT-156": "kundenartikelnummer ihreartikelnummer",
    "BT-157": "gtin ean",
    "BT-159": "ursprungsland herkunftsland",
    "BT-132": "bestellposition",
    "zeichnungsnummer": "zeichnungsnummer zeichnungsnr zeichnnr zeichnung drawingnumber drawingno drawing",
    "index": "index zeichnungsindex indexstand aenderungsindex änderungsindex revision",
    "BT-128": "objektkennungposition positionsobjekt",
    "BT-143": "zuschlagprozent zuschlagsatz",
    "BT-144": "zuschlaggrundposition",
    "BT-47": "handelsregister registernummer kundenregister hrb",
    "steuerhinweis": "steuerhinweis steuervermerk steuertext mwsthinweis",
    "BT-5": "waehrung währung currency whg",
    "kurs": "kurs umrechnungskurs wechselkurs exchangerate devisenkurs",
    "kursdatum": "kursdatum kursvom wechselkursdatum",
    "BT-111": "usteur steuereur mwsteur vateur umsatzsteuereur",
}
DATUMSFORMATE = ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%d/%m/%Y", "%Y%m%d")
SAETZE = (19, 7, 0, 16, 5)
# Zuordnung je Steuerwert: Anzeige -> Mapping-Eintrag (None = „prüfen“)
STEUER_WAHL: dict[str, dict | None] = {
    "19 %": {"BT-151": "S", "BT-152": 19},
    "7 %": {"BT-151": "S", "BT-152": 7},
    "0 % – Steuerschuldnerschaft des Leistungsempfängers": steuerfaelle.mapping("AE"),
    "0 % – innergemeinschaftliche Lieferung": steuerfaelle.mapping("K"),
    "0 % – Ausfuhrlieferung (Drittland)": steuerfaelle.mapping("G"),
    "0 % – nicht im Inland steuerbar": steuerfaelle.mapping("O"),
    "0 % – Kleinunternehmer (§ 19 UStG)": steuerfaelle.mapping("KU"),
    "0 % – steuerfrei": {"BT-151": "E", "BT-152": 0, "BT-120": "Steuerfrei", "BT-121": ""},
    "prüfen": None,
}
_FALL_WAHL = {
    "AE": "0 % – Steuerschuldnerschaft des Leistungsempfängers",
    "K": "0 % – innergemeinschaftliche Lieferung",
    "G": "0 % – Ausfuhrlieferung (Drittland)",
    "O": "0 % – nicht im Inland steuerbar",
    "KU": "0 % – Kleinunternehmer (§ 19 UStG)",
}


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", s.lower())


@dataclass
class Format:
    kodierung: str
    trennzeichen: str
    dezimal: str
    tausender: str
    datum: str
    kopf: list[str] = field(default_factory=list)
    zeilen: list[list[str]] = field(default_factory=list)
    # Excel/ODS (ab rc2): gewähltes Blatt, Zeile der Kopfzeile (1 = erste Zeile), alle Blätter der Datei
    blatt: str = ""
    startzeile: int = 1
    blaetter: list[str] = field(default_factory=list)

    @property
    def ist_tabelle(self) -> bool:
        return bool(self.blaetter)

    @property
    def zusammenfassung(self) -> str:
        t = {";": "Semikolon", ",": "Komma", "\t": "Tabulator", "|": "Senkrechter Strich"}.get(
            self.trennzeichen, self.trennzeichen
        )
        k = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8", "cp1252": "Windows-1252"}.get(
            self.kodierung, self.kodierung
        )
        if self.ist_tabelle:
            return f"Blatt „{self.blatt}“ ab Zeile {self.startzeile} · Dezimal{'komma' if self.dezimal == ',' else 'punkt'}"
        return f"{t} · {k} · Dezimal{'komma' if self.dezimal == ',' else 'punkt'}"


def spalte(fmt: Format, name: str) -> list[str]:
    i = fmt.kopf.index(name)
    return [z[i].strip() for z in fmt.zeilen if i < len(z)]


def format_erkennen(
    datei: Path,
    kodierung: str = "auto",
    trennzeichen: str = "auto",
    *,
    blatt: str | None = None,
    startzeile: int | None = None,
    dezimal: str | None = None,
    datum_format: str | None = None,
) -> Format:
    """Kodierung, Trennzeichen, Dezimalzeichen und Datumsformat vorschlagen (alles änderbar).

    Excel/ODS (ab rc2): ``blatt`` (Standard: das aktive Blatt), ``startzeile`` (Standard: erste Zeile, die wie
    eine Kopfzeile aussieht), ``dezimal``/``datum_format`` für Zahl- und Datumszellen (Standard: wie die
    Text-Zellen der Datei, sonst Komma und TT.MM.JJJJ)."""
    if tabellen.ist_tabelle(datei):
        t = tabellen.lesen(Path(datei), blatt)
        start = int(startzeile or tabellen.startzeile_vorschlagen(t))
        d2, f2 = tabellen.erkennen(t, start)
        dez, dfmt = dezimal or d2, datum_format or f2
        roh = [z for z in tabellen.zeilen_als_text(t, start, dez, dfmt) if any(w.strip() for w in z)]
        if not roh:
            raise ValueError(f"Blatt „{t.blatt}“ ist ab Zeile {start} leer")
        breite = max(len(z) for z in roh)
        roh = [z + [""] * (breite - len(z)) for z in roh]
        kopf, daten = [c.strip() for c in roh[0]], roh[1:]
        return Format(
            "utf-8", tabellen.TRENNZEICHEN, dez, "." if dez == "," else "", dfmt, kopf, daten,
            blatt=t.blatt, startzeile=start, blaetter=list(t.blaetter),
        )
    text, kod = dekodieren(Path(datei).read_bytes(), kodierung)
    trenn = trennzeichen_erkennen(text) if trennzeichen in ("auto", "", None) else trennzeichen
    zeilen = [z for z in csv_lesen(text, trenn) if any((w or "").strip().strip("\x1a") for w in z)]
    if not zeilen:
        raise ValueError("Datei ist leer")
    kopf, daten = [c.strip() for c in zeilen[0]], zeilen[1:]
    werte = [w.strip() for z in daten for w in z if w.strip()]
    komma = sum(bool(re.fullmatch(r"-?\d{1,3}(\.\d{3})*,\d+-?|-?\d+,\d+-?", w)) for w in werte)
    punkt = sum(
        bool(re.fullmatch(r"-?\d{1,3}(,\d{3})*\.\d+-?|-?\d+\.\d+-?", w))
        for w in werte
        if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{2,4}", w)
    )
    dez = "." if punkt > komma else ","
    tau = "." if dez == "," else ""
    treffer = {f: sum(_ist_datum(w, f) for w in werte) for f in DATUMSFORMATE}
    datum = max(DATUMSFORMATE, key=lambda f: treffer[f]) if any(treffer.values()) else "%d.%m.%Y"
    return Format(kod if kod != "utf-8-sig" else "utf-8-sig", trenn, dez, tau, datum, kopf, daten)


def _ist_datum(w: str, f: str) -> bool:
    if not re.fullmatch(r"[\d./-]{6,10}", w):
        return False
    try:
        datetime.strptime(w, f)
        return True
    except ValueError:
        return False


def satzart(fmt: Format) -> bool:
    """Kopf- und Positionszeilen getrennt (Satzart-Spalte erkannt)?"""
    return any(_norm(s) in ("satzart", "satztyp", "zeilentyp", "recordtype") for s in fmt.kopf)


# Im Positionsblock meint „Gesamtnetto“ die Zeile, nicht die Rechnung
_GESAMT_IM_POSITIONSBLOCK = frozenset(("gesamtnetto", "nettogesamt", "gesamtbetrag", "betragnetto"))

# Spaltennamen, die Name oder Nummer des Kunden sein können – entschieden wird an den Werten
_KUNDE_MEHRDEUTIG = frozenset(("kunde", "kunden", "customer", "kd"))


def _sieht_nach_nummer_aus(werte: list[str]) -> bool:
    """„K-1001“, „10023“, „KD/77“ – kurz, ohne Leerzeichen, mit Ziffer."""
    werte = [w.strip() for w in werte if w.strip()]
    return bool(werte) and all(
        len(w) <= 20 and re.fullmatch(r"[A-Za-z]{0,4}[-./]?\d[\w./-]*", w) for w in werte
    )


def spalten_vorschlagen(
    kopf: list[str], zeilen: list[list[str]] | None = None, *, wiederholend: bool | None = None
) -> dict[str, str]:
    """-> {Feld: Spalte}. Erst exakte Treffer (normalisiert), dann Wortanfänge; jede Spalte höchstens einmal.
    Mit ``zeilen`` wird eine Spalte „Kunde“ mit Werten wie „K-1001“ als Kundennummer vorgeschlagen, sonst als Name.
    ``wiederholend=True`` (Positionsblock): „Gesamtnetto“ ist der Gesamtpreis der Position, nicht die
    Rechnungssumme."""
    fest = spalten_nach_bt(kopf)
    aus = _spalten_nach_namen([s for s in kopf if s not in fest.values()], ausser=set(fest))
    # „Rabatt“ allein ist mehrdeutig (Prozent oder Betrag) – nur „Rabatt%“ / „Rabattsatz“ automatisch
    r = aus.get("BT-138")
    if r and "%" not in r and _norm(r) == "rabatt":
        aus.pop("BT-138")
    if wiederholend and "gesamtpreis_position" not in aus:
        for f in ("BT-109", "BT-112"):
            sp = aus.get(f)
            if sp and _norm(sp) in _GESAMT_IM_POSITIONSBLOCK:
                aus["gesamtpreis_position"] = aus.pop(f)
                break
    s = aus.get("BT-44")
    if s and "kundennummer" not in aus and _norm(s) in _KUNDE_MEHRDEUTIG and zeilen:
        i = kopf.index(s)
        if _sieht_nach_nummer_aus([z[i] for z in zeilen if i < len(z)]):
            aus["kundennummer"] = aus.pop("BT-44")
    # Zweite Spalte „Kunde“ mit Werten wie K-1001, obwohl der Name schon zugeordnet ist
    if "kundennummer" not in aus and zeilen:
        belegt = set(aus.values())
        for sp in kopf:
            if not sp or sp in belegt or _norm(sp) not in _KUNDE_MEHRDEUTIG:
                continue
            i = kopf.index(sp)
            if _sieht_nach_nummer_aus([z[i] for z in zeilen if i < len(z)]):
                aus["kundennummer"] = sp
                break
    # „Artikel“ allein ist meist die Bezeichnung; nur Artikelnummer, wenn es schon eine Bezeichnung gibt
    if "BT-153" not in aus and _norm(aus.get("BT-155") or "") == "artikel":
        aus["BT-153"] = aus.pop("BT-155")
    # BT-Nummern und eigene Feldschlüssel im Kopf haben Vorrang (rc2) – die Regeln oben gelten nur für Wörter
    return {**fest, **aus}


# BT-Nummern des Standards, die bei uns unter einem eigenen Schlüssel stehen (EN 16931)
BT_ZU_FELD = {
    "BT-46": "kundennummer",  # Käuferkennung
    "BT-131": "gesamtpreis_position",  # Nettobetrag der Rechnungsposition (nur Kontrolle)
    "BT-152": "steuer",  # Umsatzsteuersatz der Position
    "BT-81": "zahlungsart",  # Code für die Zahlungsart
}

_BT_IM_KOPF = re.compile(r"(?<![0-9a-z])bt[\s_\-.]*0*([0-9]{1,3})(?![0-9])", re.IGNORECASE)


def bt_feld(spalte: str) -> str | None:
    """Feld-ID zu einem Spaltenkopf mit BT-Nummer oder eigenem Feldschlüssel, sonst None (rc2).

    Erkannt werden „BT-1“, „bt1“, „BT 1“, „BT_1“, „Rechnungsnummer (BT-1)“, „BT-1 Rechnungsnummer“ und
    unsere Schlüssel wie „kundennummer“ oder „gesamtpreis_position“ (genau, Groß/klein egal). „BT-1“ ist
    nie „BT-10“ oder „BT-115“. Steht mehr als eine BT-Nummer im Kopf, gilt er als mehrdeutig (None)."""
    t = str(spalte or "").strip()
    if not t:
        return None
    klein = t.lower()
    for fid in FELD:
        if not fid.startswith("BT-") and klein == fid.lower():
            return fid
    nummern = {int(m.group(1)) for m in _BT_IM_KOPF.finditer(t)}
    if len(nummern) != 1:
        return None
    bt = f"BT-{nummern.pop()}"
    if bt in FELD:
        return bt
    return BT_ZU_FELD.get(bt)


def spalten_nach_bt(kopf: list[str]) -> dict[str, str]:
    """{Feld: Spalte} nur aus BT-Nummern bzw. Feldschlüsseln im Kopf; je Feld die erste Spalte."""
    aus: dict[str, str] = {}
    for sp in kopf:
        fid = bt_feld(sp)
        if fid and fid not in aus:
            aus[fid] = sp
    return aus


def _spalten_nach_namen(kopf: list[str], ausser: set[str] | None = None) -> dict[str, str]:
    frei = {_norm(s): s for s in kopf if s}
    aus: dict[str, str] = {}
    ausser = ausser or set()
    for genau in (True, False):
        for f, syn in _SYNONYME.items():
            if f in aus or f in ausser or (not genau and f in NUR_GENAU):
                continue
            for w in syn.split():
                w = _norm(w)
                treffer = [
                    n for n in frei if (n == w if genau else len(w) >= 4 and n.startswith(w))
                ]
                if treffer:
                    aus[f] = frei.pop(treffer[0])
                    break
    return aus


def fehlende_pflicht(zuordnung: dict[str, str]) -> list[str]:
    return [FELD[f][1] for f, *_r, pflicht in FELDER if pflicht and not zuordnung.get(f)]


def _zahl(w: str) -> Decimal | None:
    try:
        return Decimal(w.replace("%", "").replace(",", ".").strip())
    except InvalidOperation:
        return None


def steuer_ist_satz(werte: list[str]) -> bool:
    """Steht in der Steuerspalte der Satz selbst („19“, „7,00“, „19 %“)?"""
    zahlen = [_zahl(w) for w in werte if w]
    return (
        bool(zahlen)
        and all(z is not None and z in SAETZE for z in zahlen)
        and any(z for z in zahlen)
    )


def steuer_vorschlag(werte: list[str]) -> dict[str, str]:
    """Steuerwert -> Anzeige aus STEUER_WAHL. Schlüssel (1, 2 …) werden nicht geraten: „prüfen“. Eindeutige
    Kürzel/Texte der Sonderfälle („RC“, „igL“, „Reverse Charge“, „§ 19“) werden vorgeschlagen (ab 0.9.7)."""
    aus = {}
    for w in sorted({w for w in werte if w}):
        z = _zahl(w)
        fall = steuerfaelle.erkennen_kurz(w) or steuerfaelle.erkennen(w)
        aus[w] = (
            "19 %"
            if z == 19
            else "7 %"
            if z == 7
            else _FALL_WAHL[fall]
            if fall in _FALL_WAHL
            else "prüfen"
        )
    return aus


def einheiten_vorschlag(werte: list[str]) -> dict[str, str]:
    """Einheit in der CSV -> UN/ECE-Code (allgemeine Liste); unbekannt -> ""."""
    aus = {}
    for w in sorted({w for w in werte if w}):
        aus[w] = w if w in codelisten.EINHEITEN else (einheit_code(w) or "")
    return aus


def _tabelle_ins_profil(p: dict, fmt: Format) -> None:
    """Excel/ODS: Blatt und Kopfzeile im Profil merken (rc2). Trennzeichen/Zeichensatz gelten intern."""
    if getattr(fmt, "ist_tabelle", False):
        p["datei"]["blatt"] = fmt.blatt
        p["datei"]["startzeile"] = int(fmt.startzeile or 1)


def profil_spalten(profil: dict) -> list[str]:
    """Spaltennamen eines CSV-/Tabellenprofils für die Platzhalter-Auswahl: gemerkte Kopfzeile (ab rc2), sonst die
    zugeordneten Spalten; Blockprofile: Kopfzeilen der Nicht-Positionsblöcke."""
    from .csv_bloecke import block_wiederholend

    out: list[str] = []
    d = profil.get("datei") or {}
    out += [str(x) for x in d.get("spalten") or []]
    for b in profil.get("bloecke") or []:
        if isinstance(b, dict) and not block_wiederholend(b):
            out += [str(x) for x in (b.get("kopf") or b.get("kopfzeile") or [])]
            out += [str(v.get("spalte")) for v in (b.get("felder") or {}).values() if isinstance(v, dict) and v.get("spalte")]
    for v in ((profil.get("felder") or {}).get("kopf") or {}).values():
        if isinstance(v, dict) and v.get("spalte"):
            out.append(str(v["spalte"]))
    return [x for x in dict.fromkeys(s.strip() for s in out) if x]


def profil_bauen(
    name: str,
    datei: Path,
    fmt: Format,
    zuordnung: dict[str, str],
    steuer: dict[str, str],
    einheiten: dict[str, str],
    textzeile: dict | None = None,
    sicht: dict | None = None,
    einheit_fehlt_stueck: bool = False,
) -> dict:
    """Normales CSV-Profil (zeile_je_position). ``steuer``: Wert -> Anzeige aus STEUER_WAHL."""
    kopf, pos = {}, {}
    for f, sp in zuordnung.items():
        if not sp or f not in FELD:
            continue
        _f, _anz, teil, typ, pflicht = FELD[f]
        d: dict = {"spalte": sp}
        if typ != "text":
            d["typ"] = typ
        if f in ("BT-112", "BT-109", "BT-110", "gesamtpreis_position"):
            d["zweck"] = "pruefung"
        if f == "BT-130":
            d["mapping"] = "einheiten"
        if f == "steuer":
            d["mapping"] = "steuer"
        if not pflicht:
            d["optional"] = True
        (kopf if teil == "kopf" else pos)[f] = d
    kopf["BT-3"] = {"fest": "380"}
    kopf.setdefault("BT-5", {"fest": "EUR"})
    st: dict = {w: STEUER_WAHL[a] for w, a in steuer.items() if STEUER_WAHL.get(a)}
    st["unbekannt"] = "satz" if steuer_ist_satz(list(steuer)) else "pruefen"
    eh: dict = {w: c for w, c in einheiten.items() if c}
    eh["unbekannt"] = "allgemein"
    gleich = [zuordnung[f] for f in ("BT-2", "BT-44", "kundennummer") if zuordnung.get(f)]
    p = {
        "profil": name,
        "version": 2,
        "beschreibung": f"Eingerichtet mit dem Assistenten aus {Path(datei).name}: {fmt.zusammenfassung}",
        "datei": {
            "muster": f"*{Path(datei).suffix.lower() or '.csv'}",
            "kodierung": fmt.kodierung,
            "trennzeichen": fmt.trennzeichen,
            "textbegrenzer": '"',
            "kopfzeile": True,
        },
        "zahlen": {"dezimal": fmt.dezimal, "tausender": fmt.tausender},
        "datum": {"format": fmt.datum},
        "aufbau": {
            "art": "zeile_je_position",
            "rechnung_schluessel": zuordnung["BT-1"],
            "kopf_muss_gleich_sein": gleich,
        },
        "felder": {"kopf": kopf, "position": pos},
        "mappings": {"einheiten": eh, "steuer": st},
    }
    _tabelle_ins_profil(p, fmt)
    # alle Spaltennamen (rc2): Auswahl der Platzhalter im Layouteditor, auch nicht zugeordnete Spalten
    p["datei"]["spalten"] = [c for c in dict.fromkeys(str(x).strip() for x in fmt.kopf) if c]
    if textzeile:
        p["aufbau"]["textzeile"] = textzeile
    if einheit_fehlt_stueck:
        p["aufbau"]["einheit_fehlt_stueck"] = True
    p["sicht"] = sicht or {
        "positionsnummer": True,
        "einheit": "kurz",
        "menge_exakt": True,
        "kommentar_ohne_bezeichnungen": False,
        "felder": {},
    }
    return p


def profil_zuordnung(profil: dict) -> dict[str, str]:
    """Vorhandenes Assistenten-Profil -> {Feld: Spalte} (zum Ändern)."""
    aus: dict[str, str] = {}
    f = profil.get("felder", {})
    for teil in ("kopf", "position"):
        for k, d in (f.get(teil) or {}).items():
            if isinstance(d, dict) and d.get("spalte"):
                aus[k] = d["spalte"]
    for b in profil.get("bloecke") or []:
        for k, d in (b.get("felder") or {}).items():
            if isinstance(d, dict) and d.get("spalte"):
                aus[k] = d["spalte"]
    return aus


def spalte_in_datei(fmt: Format, name: str) -> list[str]:
    """Werte einer Spalte über alle Blöcke, nicht nur die erste Kopfzeile."""
    from . import csv_bloecke

    if not name:
        return []
    try:
        return spalte(fmt, name)
    except ValueError:
        pass
    rows = [fmt.kopf] + list(fmt.zeilen or [])
    namen = synonym_namen()
    aus: list[str] = []
    idx = None
    kopf: list[str] = []
    for row in rows:
        if csv_bloecke._leer_zeile(row):
            continue
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            idx = None
            continue
        if csv_bloecke.ist_kopfzeile(row, namen, 2) or (
            idx is None
            and any(csv_bloecke.name_norm(c) == csv_bloecke.name_norm(name) for c in row)
        ):
            kopf = [c.strip() for c in row]
            try:
                idx = next(
                    i
                    for i, c in enumerate(kopf)
                    if csv_bloecke.name_norm(c) == csv_bloecke.name_norm(name)
                )
            except StopIteration:
                idx = None
            continue
        if idx is not None and idx < len(row) and (row[idx] or "").strip():
            aus.append(row[idx].strip())
    return aus


def bearbeitbar(profil: dict) -> bool:
    art = (profil.get("aufbau") or {}).get("art", "zeile_je_position")
    return art in ("zeile_je_position", "satzart", "bloecke")


def dateiname(name: str, ordner: Path) -> Path:
    stamm = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower() or "csv"
    return ordner / f"profil-{stamm}.yaml"


def speichern(profil: dict, ziel: Path) -> Path:
    sauber = {k: v for k, v in profil.items() if not k.startswith("_")}
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(".tmp")
    tmp.write_text(
        "# CSV-Zuordnungsprofil – mit dem Assistenten eingerichtet (Fakturafalter)\n"
        + yaml.safe_dump(sauber, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(ziel)
    return ziel




@dataclass
class Probe:
    nummer: str
    kunde: str
    brutto: str
    status: str
    hinweise: list[str]


def probe(rechnungen, k) -> list[Probe]:
    """Probe ohne Schreiben: rechnen + Pflichtprüfung wie im Lauf (ohne Ausgabe, ohne Verschieben)."""
    from . import pflichtpruefung, rechnen

    ctx = pflichtpruefung.Kontext(bekannte_nummern=frozenset())
    aus = []
    for r in rechnungen:
        rechnen.berechnen(r)
        pflichtpruefung.pruefen(r, ctx)
        aus.append(
            Probe(
                r.nummer,
                r.kaeufer.name,
                str(r.summen.brutto),
                r.status,
                [str(h) for h in r.hinweise if h.stufe != "info"],
            )
        )
    return aus


def probe_csv(datei: Path, profil: dict, k) -> list[Probe]:
    from . import adapter_csv

    p = {**profil, "_basis": Path(k.basis), "_datei": str(Path(k.basis) / "assistent.yaml")}
    return probe(adapter_csv.lesen(Path(datei), p, k), k)


class _NamenMitBT(set):
    """Normalisierte Spaltennamen; zählt zusätzlich Köpfe mit BT-Nummer („bt1“, „rechnungsnummerbt1“,
    „bt1rechnungsnummer“) als bekannt (rc2), wenn die Nummer zu einem unserer Felder gehört."""

    _RE = re.compile(r"^bt0*([0-9]{1,3})(?![0-9])|(?:^|[a-z])bt0*([0-9]{1,3})$")

    def __contains__(self, n: object) -> bool:
        if set.__contains__(self, n):
            return True
        m = self._RE.search(str(n or ""))
        if not m:
            return False
        bt = f"BT-{int(m.group(1) or m.group(2))}"
        return bt in FELD or bt in BT_ZU_FELD


def synonym_namen() -> set[str]:
    """Alle bekannten Spalten-Synonyme, normalisiert (für Block-Kopfzeilen ohne Profil)."""
    from . import csv_bloecke

    aus: set[str] = _NamenMitBT()
    for syn in _SYNONYME.values():
        for w in syn.split():
            aus.add(csv_bloecke.name_norm(w))
    for f, _a, *_r in FELDER:
        aus.add(csv_bloecke.name_norm(_a))
        aus.add(csv_bloecke.name_norm(f))
    aus.discard("")
    return aus


def bloecke_erkannt(fmt: Format) -> bool:
    """Mehr als eine Kopfzeile oder erkennbare Marker? Nur Hinweis im Format-Schritt."""
    from . import csv_bloecke

    namen = synonym_namen()
    kopfzeilen = 0
    marker = 0
    rows = [fmt.kopf] + list(fmt.zeilen or [])
    for row in rows:
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            marker += 1
        elif csv_bloecke.ist_kopfzeile(row, namen, 2):
            kopfzeilen += 1
    if kopfzeilen >= 2 or marker >= 2 or (marker >= 1 and kopfzeilen >= 1):
        return True
    return _satzart_sieht_nach_einer_rechnung_aus(rows)


def bloecke_schneiden_fmt(fmt: Format) -> list[dict]:
    from . import csv_bloecke

    rows = [fmt.kopf] + list(fmt.zeilen or [])
    # format_erkennen already used first row as header; include it as row 1
    return csv_bloecke.schneiden(rows, 1, synonym_namen(), 2)


def einzigartige_spalten(fmt: Format) -> list[str]:
    """Einmalige Spaltennamen aller Kopfzeilen (und der Zeile nach einem Marker)."""
    from . import csv_bloecke

    namen = synonym_namen()
    rows = [fmt.kopf] + list(fmt.zeilen or [])
    gesehen: list[str] = []
    gesehen_n: set[str] = set()
    nach_marker = False
    for row in rows:
        if csv_bloecke._leer_zeile(row):
            continue
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            nach_marker = True
            continue
        kopf = csv_bloecke.ist_kopfzeile(row, namen, 2) or nach_marker
        nach_marker = False
        if not kopf:
            continue
        for c in row:
            s = (c or "").strip()
            if not s:
                continue
            n = csv_bloecke.name_norm(s)
            if n in gesehen_n:
                continue
            gesehen_n.add(n)
            gesehen.append(s)
    return gesehen


def typ_aus_marker(wort: str) -> str:
    """#Kopf / Positionen / Summen → typ; unbekannte Wortlaute bleiben als typ erhalten."""
    from . import csv_bloecke

    n = csv_bloecke.name_norm((wort or "").lstrip("#"))
    return {
        "kopf": "kopf",
        "header": "kopf",
        "positionen": "positionen",
        "position": "positionen",
        "pos": "positionen",
        "summen": "summen",
        "summe": "summen",
        "zahlung": "zahlung",
        "zahlungsbedingungen": "zahlung",
        "lieferung": "lieferung",
        "lieferanschrift": "lieferung",
    }.get(n, n or "kopf")


def marker_aus_datei(fmt: Format) -> list[dict]:
    """Marker-ähnliche Zeilen der Datei als vorläufige Block-Liste (für den Assistenten)."""
    from . import csv_bloecke

    rows = [fmt.kopf] + list(fmt.zeilen or [])
    namen = synonym_namen()
    aus: list[dict] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        if csv_bloecke._leer_zeile(row):
            i += 1
            continue
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            wort = next((str(c).strip() for c in row if str(c).strip()), "")
            typ = typ_aus_marker(wort)
            kopf: list[str] = []
            j = i + 1
            while j < len(rows) and csv_bloecke._leer_zeile(rows[j]):
                j += 1
            if j < len(rows) and not csv_bloecke.sieht_nach_marker_heuristik(rows[j]):
                if csv_bloecke.ist_kopfzeile(rows[j], namen, 2):
                    kopf = [c.strip() for c in rows[j]]
            aus.append({"typ": typ, "marker": wort, "kopfzeile": kopf})
        i += 1
    return aus


def bloecke_schneiden_zuordnung(
    fmt: Format, zuordnung: dict[str, str], profil: dict | None = None
) -> list[dict]:
    """Blöcke über zugeordnete Spalten; erkannte Marker werden ohne gespeichertes Profil mitgeführt."""
    from . import csv_bloecke

    if profil:
        return csv_bloecke.schneiden_profil([fmt.kopf] + list(fmt.zeilen or []), 1, profil)
    spalten = [s for s in zuordnung.values() if s]
    felder = {f"f{i}": {"spalte": s} for i, s in enumerate(spalten)}
    roh = {
        "aufbau": {"art": "bloecke", "kopfzeile_schwelle": 2},
        "felder": {"kopf": felder},
        "bloecke": marker_aus_datei(fmt),
    }
    return csv_bloecke.schneiden_profil([fmt.kopf] + list(fmt.zeilen or []), 1, roh)


def positionsfelder() -> set[str]:
    return {f for f, _n, teil, _t, _p in FELDER if teil == "position"}




def _satzart_sieht_nach_einer_rechnung_aus(zeilen: list[list[str]]) -> bool:
    """Eine Satzart-Datei mit einem Kopf-Lauf und einem Positions-Lauf (optional Summen)."""
    sa = satzart_spalte_erkennen(zeilen)
    if sa is None:
        return False
    namen = synonym_namen()
    from . import csv_bloecke

    laeufe: list[str] = []
    kopf = []
    for row in zeilen:
        if csv_bloecke._leer_zeile(row) or csv_bloecke.sieht_nach_marker_heuristik(row):
            continue
        if csv_bloecke.ist_kopfzeile(row, namen, 2) or (
            not isinstance(sa, int) and any(_norm(c) == _norm(str(sa)) for c in row)
        ):
            if not kopf:
                kopf = [c.strip() for c in row]
            continue
        if isinstance(sa, int):
            i = sa - 1
            wert = (row[i] or "").strip() if 0 <= i < len(row) else ""
        else:
            wert = ""
            for i, name in enumerate(kopf or row):
                if _norm(name) == _norm(str(sa)) and i < len(row):
                    wert = (row[i] or "").strip()
                    break
        typ = typ_aus_satzart_wert(wert)
        if not typ:
            continue
        if not laeufe or laeufe[-1] != typ:
            laeufe.append(typ)
    if laeufe.count("kopf") > 1:
        return False
    if "kopf" in laeufe and "positionen" in laeufe:
        return True
    if not kopf and laeufe:
        return True
    return False


def typ_aus_satzart_wert(wert: str) -> str:
    """K/P/S und gängige Wörter → Blocktyp; unbekannte Werte bleiben leer (Nutzer trägt nach)."""
    from . import csv_bloecke

    n = csv_bloecke.name_norm((wert or "").lstrip("#"))
    return {
        "k": "kopf",
        "kopf": "kopf",
        "header": "kopf",
        "head": "kopf",
        "p": "positionen",
        "pos": "positionen",
        "position": "positionen",
        "positionen": "positionen",
        "s": "summen",
        "summe": "summen",
        "summen": "summen",
        "r": "zahlung",
        "zahlung": "zahlung",
        "l": "lieferung",
        "lieferung": "lieferung",
    }.get(n, "")


def satzart_spalte_erkennen(zeilen: list[list[str]]):
    """Name oder 1-basierte Nummer der Satzart-Spalte, sonst None."""
    from . import csv_bloecke

    if not zeilen:
        return None
    # Namens-Treffer in einer Kopfzeile
    for row in zeilen:
        if csv_bloecke._leer_zeile(row):
            continue
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            continue
        if csv_bloecke.ist_kopfzeile(row, synonym_namen(), 2) or any(
            _norm(c) in ("satzart", "satztyp", "zeilentyp", "recordtype") for c in row
        ):
            for c in row:
                if _norm(c) in ("satzart", "satztyp", "zeilentyp", "recordtype"):
                    return c.strip()
            break
    # Werte: kurze wiederholte Kennzeichen
    max_cols = max((len(r) for r in zeilen), default=0)
    beste = None
    best_score = 0
    for i in range(max_cols):
        werte = []
        for row in zeilen:
            if csv_bloecke._leer_zeile(row) or csv_bloecke.sieht_nach_marker_heuristik(row):
                continue
            if csv_bloecke.ist_kopfzeile(row, synonym_namen(), 2):
                continue
            if i >= len(row):
                continue
            w = (row[i] or "").strip()
            if w:
                werte.append(w)
        if len(werte) < 2:
            continue
        unique = set(werte)
        if not (2 <= len(unique) <= 8):
            continue
        if not all(len(u) <= 12 and typ_aus_satzart_wert(u) for u in unique):
            continue
        score = len(werte) + (5 if i == 0 else 0)
        if score > best_score:
            best_score = score
            beste = i + 1
    return beste


def _spaeter_andere_koepfe(zeilen, ab, dieser, namen, sa) -> bool:
    """True, wenn nach dieser Zeile eine Kopfzeile mit anderen Namen folgt."""
    from . import csv_bloecke

    dieser_n = [csv_bloecke.name_norm(c) for c in dieser]
    for row in zeilen[ab + 1 :]:
        if csv_bloecke._leer_zeile(row) or csv_bloecke.sieht_nach_marker_heuristik(row):
            continue
        ist_sa_kopf = sa is not None and not isinstance(sa, int) and any(
            csv_bloecke.name_norm(c) == csv_bloecke.name_norm(str(sa)) for c in row
        )
        if csv_bloecke.ist_kopfzeile(row, namen, 2) or ist_sa_kopf:
            andere = [csv_bloecke.name_norm(c) for c in row]
            if andere != dieser_n:
                return True
    return False


def bloecke_vorschlagen(fmt: Format) -> tuple[list[dict], object]:
    """Blöcke und optionale Satzart-Spalte aus der Datei vorschlagen (Assistent)."""
    from . import csv_bloecke

    zeilen = [fmt.kopf] + list(fmt.zeilen or [])
    namen = synonym_namen()
    sa = satzart_spalte_erkennen(zeilen)
    aus: list[dict] = []
    aktuell: dict | None = None
    gemeinsame_kopf: list[str] | None = None
    nr0 = 1

    def _sa_wert(row, kopf):
        if sa is None:
            return ""
        if isinstance(sa, int):
            i = sa - 1
            return (row[i] or "").strip() if 0 <= i < len(row) else ""
        for i, name in enumerate(kopf or []):
            if csv_bloecke.name_norm(name) == csv_bloecke.name_norm(str(sa)) and i < len(row):
                return (row[i] or "").strip()
        return ""

    def _neu(nr, typ, **extra):
        nonlocal aktuell
        kopf = list(extra.pop("kopf", []) or [])
        vergeben = {str(b.get("typ") or "") for b in aus}
        typ_e = eindeutiger_typ(kopf, typ or "kopf", vergeben)
        wdh = extra.pop("wiederholend", typ == "positionen" or typ_e == "positionen")
        bl = {
            "typ": typ_e,
            "id": typ_e,
            "name": typ_e,
            "start": nr,
            "kopf": kopf,
            "daten": [],
            "anfang": list(extra.pop("anfang", []) or []),
            "wiederholend": bool(wdh),
            "ohne_anfang": bool(extra.pop("ohne_anfang", False)),
            **extra,
        }
        aus.append(bl)
        aktuell = bl
        return bl

    for i, row in enumerate(zeilen):
        nr = nr0 + i
        if csv_bloecke._leer_zeile(row):
            continue
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            wort = next((str(c).strip() for c in row if str(c).strip()), "")
            typ = typ_aus_marker(wort)
            _neu(
                nr,
                typ,
                marker=wort,
                marker_wort=wort,
                anfang=[{"art": "marker", "wert": wort}],
                ohne_kopfzeile=True,
            )
            # nächste Zeile kann Kopfzeile sein: wird unten gesetzt
            aktuell["_wartet_kopf"] = True
            continue
        if aktuell is not None and aktuell.pop("_wartet_kopf", False):
            if csv_bloecke.ist_kopfzeile(row, namen, 2) or not typ_aus_satzart_wert(
                _sa_wert(row, gemeinsame_kopf)
            ):
                if csv_bloecke.ist_kopfzeile(row, namen, 2) or all(
                    not (c or "").strip().isdigit() for c in row
                ):
                    aktuell["kopf"] = [c.strip() for c in row]
                    aktuell["ohne_kopfzeile"] = False
                    if not any(r.get("art") == "kopfzeile" for r in aktuell["anfang"]):
                        aktuell["anfang"].append({"art": "kopfzeile"})
                    continue
        kopf_ctx = (aktuell or {}).get("kopf") or gemeinsame_kopf or []
        wert = _sa_wert(row, kopf_ctx)
        # Die Kopfzelle „Satzart“ ist kein Satzart-Wert
        if wert and sa is not None and _norm(str(wert)) == _norm(str(sa) if not isinstance(sa, int) else "satzart"):
            wert = ""
        typ_sa = typ_aus_satzart_wert(wert) if wert else ""
        if typ_sa:
            rolle = typ_vorschlag((aktuell or {}).get("kopf") or []) if aktuell else ""
            gleicher = aktuell is not None and typ_sa in {aktuell.get("typ"), rolle}
            if (
                not gleicher
                and aktuell is not None
                and typ_sa == "kopf"
                and str(aktuell.get("typ") or "") in {"kopf", "kunde", "beleg"}
            ):
                gleicher = True
            if gleicher:
                aktuell["daten"].append((nr, row))
                if not any(r.get("art") == "satzart" for r in (aktuell.get("anfang") or [])):
                    aktuell.setdefault("anfang", []).append({"art": "satzart", "wert": wert})
                continue
            kopf = list(gemeinsame_kopf or [])
            anfang = [{"art": "satzart", "wert": wert}]
            _neu(
                nr,
                typ_sa,
                kopf=kopf,
                satzart=True,
                satzart_wert=wert,
                anfang=anfang,
                ohne_kopfzeile=not bool(kopf),
            )
            aktuell["daten"].append((nr, row))
            continue
        ist_sa_kopf = sa is not None and not isinstance(sa, int) and any(
            _norm(c) == _norm(str(sa)) for c in row
        )
        if csv_bloecke.ist_kopfzeile(row, namen, 2) or ist_sa_kopf:
            typ = typ_vorschlag([c.strip() for c in row])
            dieser = [c.strip() for c in row]
            if sa is not None and aktuell is None and not aus:
                gemeinsame_kopf = dieser
                # Eigene Kopfzeile je Block (später andere Namen) beginnt hier.
                # Eine gemeinsame Kopfzeile (gleiche Positionen) bleibt nur Kontext.
                if not _spaeter_andere_koepfe(zeilen, i, dieser, namen, sa):
                    continue
            _neu(
                nr,
                typ,
                kopf=dieser,
                anfang=[{"art": "kopfzeile"}],
            )
            continue
        if aktuell is None:
            _neu(
                nr,
                "kopf",
                kopf=list(gemeinsame_kopf or []),
                ohne_anfang=True,
                ohne_kopfzeile=not bool(gemeinsame_kopf),
            )
            aktuell["daten"].append((nr, row))
        else:
            aktuell["daten"].append((nr, row))

    # genau ein wiederholender: der Positionsblock, sonst der längste Datenblock
    if not any(b.get("wiederholend") for b in aus):
        kandidat = next((b for b in aus if b.get("typ") == "positionen"), None)
        if kandidat is None and aus:
            # nur vorschlagen, wenn die Kopfzeile nach Positionen aussieht – nicht den längsten Block zwingen
            for b in aus:
                if typ_vorschlag(b.get("kopf") or []) == "positionen":
                    kandidat = b
                    break
        if kandidat is not None:
            kandidat["wiederholend"] = True
    if sa is not None:
        for b in aus:
            for _nr, row in b.get("daten") or []:
                w = _sa_wert(row, b.get("kopf") or gemeinsame_kopf or [])
                if not w:
                    continue
                if not isinstance(sa, int) and csv_bloecke.name_norm(w) == csv_bloecke.name_norm(str(sa)):
                    continue
                if not any(r.get("art") == "satzart" for r in (b.get("anfang") or [])):
                    b.setdefault("anfang", []).append({"art": "satzart", "wert": w})
                break
    for b in aus:
        if "wiederholend" not in b:
            b["wiederholend"] = b.get("typ") == "positionen"
        if not b.get("id"):
            b["id"] = b.get("typ") or f"block{aus.index(b) + 1}"
        if not b.get("name"):
            b["name"] = b.get("typ") or b["id"]
    # nur ein wiederholender
    gesehen = False
    for b in aus:
        if b.get("wiederholend"):
            if gesehen:
                b["wiederholend"] = False
                if b.get("typ") == "positionen":
                    b["typ"] = typ_vorschlag(b.get("kopf") or []) or "summen"
            else:
                gesehen = True
    return aus, sa


def typ_vorschlag(kopf: list[str]) -> str:
    n = set()
    from . import csv_bloecke

    bt = {bt_feld(c) for c in kopf} - {None}
    if bt & {"BT-129", "BT-146", "BT-153", "steuer"}:
        return "positionen"

    n = {csv_bloecke.name_norm(c) for c in kopf}
    if n & {
        csv_bloecke.name_norm(x)
        for x in ("menge", "einzelpreis", "artikel", "bezeichnung", "ustsatz")
    }:
        return "positionen"
    if n & {
        csv_bloecke.name_norm(x)
        for x in ("gesamtbrutto", "gesamtnetto", "gesamtust", "summebrutto", "summenetto")
    }:
        return "summen"
    if n & {
        csv_bloecke.name_norm(x)
        for x in ("skonto", "zahlungsziel", "zahlungszielohneabzug", "iban")
    }:
        return "zahlung"
    if n & {csv_bloecke.name_norm(x) for x in ("liefername", "lieferstrasse", "lieferort")}:
        return "lieferung"
    if n & {csv_bloecke.name_norm(x) for x in ("rechnungsnr", "rechnungsnummer", "kunde", "datum")}:
        return "kopf"
    return "kopf"



def eindeutiger_typ(kopf: list[str], rolle: str, vergeben: set[str]) -> str:
    """Anzeigename/typ, eindeutig in der Datei (Kunde und Beleg nicht beide „kopf“)."""
    from . import csv_bloecke

    rolle = rolle or "kopf"
    n = {csv_bloecke.name_norm(c) for c in kopf}
    if rolle == "kopf":
        hat_beleg = any("beleg" in csv_bloecke.name_norm(c) for c in kopf)
        hat_kunde = any(csv_bloecke.name_norm(c).startswith("kunde") for c in kopf)
        hat_nr = n & {
            csv_bloecke.name_norm(x)
            for x in ("rechnungsnr", "rechnungsnummer", "belegname", "belegnr")
        }
        if hat_beleg or (hat_nr and "belegname" in n or "belegdatum" in n):
            basis = "beleg"
        elif hat_kunde and not hat_nr:
            basis = "kunde"
        else:
            basis = "kopf"
    else:
        basis = rolle
    name = basis
    i = 2
    while name in vergeben:
        name = f"{basis}_{i}"
        i += 1
    return name


def block_id_von(block: dict, index: int) -> str:
    """Stabile Block-ID: gespeichertes id, sonst typ wenn eindeutig, sonst typ+Index."""
    if str(block.get("id") or "").strip():
        return str(block.get("id")).strip()
    typ = str(block.get("typ") or "").strip()
    return typ or f"block{index + 1}"


def anfang_ableiten(
    zeilen: list[list[str]], start: int, ende: int, satzart_spalte=None
) -> list[dict]:
    """Anfangsregeln aus den ersten inhaltlichen Zeilen eines Blocks ableiten."""
    from . import csv_bloecke

    anfang: list[dict] = []
    kopf: list[str] = []
    namen = synonym_namen()
    for nr in range(start, ende + 1):
        if nr < 1 or nr > len(zeilen):
            continue
        row = zeilen[nr - 1]
        if csv_bloecke._leer_zeile(row):
            continue
        if csv_bloecke.sieht_nach_marker_heuristik(row):
            wort = next((str(c).strip() for c in row if str(c).strip()), "")
            if wort and not any(r.get("art") == "marker" for r in anfang):
                anfang.append({"art": "marker", "wert": wort})
            continue
        ist_sa_titel = satzart_spalte is not None and not isinstance(satzart_spalte, int) and any(
            csv_bloecke.name_norm(c) == csv_bloecke.name_norm(str(satzart_spalte)) for c in row
        )
        if (not kopf) and (csv_bloecke.ist_kopfzeile(row, namen, 2) or ist_sa_titel):
            kopf = [c.strip() for c in row]
            if not any(r.get("art") == "kopfzeile" for r in anfang):
                anfang.append({"art": "kopfzeile"})
            continue
        # Satzart-Wert auch in einer Datenzeile (z. B. #Kopf;Testkunde;…)
        wert = ""
        if satzart_spalte is not None:
            if isinstance(satzart_spalte, int):
                i = satzart_spalte - 1
                wert = (row[i] or "").strip() if 0 <= i < len(row) else ""
            else:
                suche = kopf or row
                for i, name in enumerate(suche):
                    if csv_bloecke.name_norm(name) == csv_bloecke.name_norm(str(satzart_spalte)) and i < len(row):
                        wert = (row[i] or "").strip()
                        break
                if not wert and row:
                    # Fallback: erste Zelle, wenn sie nach einem Markerwort aussieht
                    w0 = (row[0] or "").strip()
                    if w0.startswith("#") and len(w0) > 1:
                        wert = w0
        if wert and csv_bloecke.name_norm(wert) != csv_bloecke.name_norm(str(satzart_spalte) or "satzart"):
            if not any(r.get("art") == "satzart" for r in anfang):
                anfang.append({"art": "satzart", "wert": wert})
        break
    return anfang


def merkmale(profil: dict) -> str:
    """Kurzer Text für die Profilkarte: Aufbau und erkannte Spalten."""
    art = (profil.get("aufbau") or {}).get("art", "zeile_je_position")
    if art == "bloecke":
        typen = [str(b.get("typ") or "?") for b in (profil.get("bloecke") or [])]
        return "Blöcke: " + (", ".join(typen) if typen else "ohne Typen")
    if art == "satzart":
        a = profil.get("aufbau") or {}
        return "Satzarten " + "/".join(
            str(a.get(k) or "") for k in ("kopf", "position", "rabatt", "zuschlag") if a.get(k)
        )
    if art == "feste_breite":
        return "Feste Breite"
    spalten = []
    for teil in (profil.get("felder") or {}).values():
        if isinstance(teil, dict):
            for d in teil.values():
                if isinstance(d, dict) and d.get("spalte"):
                    spalten.append(str(d["spalte"]))
    if not spalten:
        return "eine Zeile je Position"
    return "eine Zeile je Position · " + ", ".join(spalten[:8]) + ("…" if len(spalten) > 8 else "")


def profil_bauen_bloecke(
    name: str,
    datei: Path,
    fmt: Format,
    bloecke: list[dict],
    zuordnung_je: dict[str, dict[str, str]],
    steuer: dict[str, str],
    einheiten: dict[str, str],
    textzeile: dict,
    satzart_spalte=None,
) -> dict:
    """Profil art=bloecke aus dem Assistenten."""
    st: dict = {w: STEUER_WAHL[a] for w, a in steuer.items() if STEUER_WAHL.get(a)}
    st["unbekannt"] = "satz" if steuer_ist_satz(list(steuer)) else "pruefen"
    eh: dict = {w: c for w, c in einheiten.items() if c}
    eh["unbekannt"] = "allgemein"
    tz = {
        "leer": ["BT-129", "BT-146", "text"],
        "ziel": "BT-154",
        "trenner": "\n",
        "platzhalter": "#LEER",
        "verwaist": "BT-22",
        "leerzeile_modus": "beides",
    }
    tz.update(textzeile or {})
    aus_bloecke = []
    gesehen_ids: set[str] = set()
    for i, b in enumerate(bloecke):
        typ = b.get("typ") or typ_vorschlag(b.get("kopf") or [])
        bid = block_id_von(b, i)
        if bid in gesehen_ids:
            bid = f"{bid}_{i + 1}"
        gesehen_ids.add(bid)
        zu = (
            zuordnung_je.get(bid)
            or zuordnung_je.get(str(b.get("id") or ""))
            or zuordnung_je.get(typ)
            or zuordnung_je.get(str(i))
            or zuordnung_je.get(str(b.get("start")))
            or {}
        )
        felder = {}
        quelle = {**zu}
        # typ kopf/zahlung: kopf-Felder; positionen: beides
        for f, sp in quelle.items():
            if not sp or f not in FELD:
                continue
            _f, _anz, teil, typf, pflicht = FELD[f]
            d: dict = {"spalte": sp}
            kopf_namen = list(b.get("kopf") or b.get("kopfzeile") or [])
            pos_map = b.get("feld_pos") or {}
            if f in pos_map:
                try:
                    d["position"] = int(pos_map[f])
                except (TypeError, ValueError):
                    pass
            elif sp in kopf_namen:
                d["position"] = kopf_namen.index(sp) + 1
            if typf != "text":
                d["typ"] = typf
            if f in ("BT-112", "BT-109", "BT-110"):
                d["zweck"] = "pruefung"
            if f == "BT-130":
                d["mapping"] = "einheiten"
            if f == "steuer":
                d["mapping"] = "steuer"
            if not pflicht or typ != "positionen" or teil == "kopf":
                d["optional"] = True
            felder[f] = d
        # BT-3/BT-5 fest nur einmal, nach dem Schleifendurchlauf, und nur wenn
        # keine Spalte das Feld liefert – sonst kollidieren fest EUR und „€“.
        if tz.get("text_spalte") and typ == "positionen":
            pass
        ein: dict = {
            "id": bid,
            "typ": typ,
            "name": str(b.get("name") or typ),
            "wiederholend": bool(b.get("wiederholend"))
            if "wiederholend" in b
            else typ == "positionen",
            "kopfzeile": list(b.get("kopf") or b.get("kopfzeile") or []),
            "felder": felder,
        }
        if str(b.get("marker") or "").strip():
            ein["marker"] = str(b.get("marker")).strip()
        if b.get("anfang"):
            ein["anfang"] = [dict(r) for r in b["anfang"] if isinstance(r, dict)]
        aus_bloecke.append(ein)
    def _hat_spalte(feld: str) -> bool:
        for b in aus_bloecke:
            d = (b.get("felder") or {}).get(feld) or {}
            if isinstance(d, dict) and (d.get("spalte") or d.get("position")):
                return True
        return False

    # Ein festes Fallback (nicht in jeden Block kopieren)
    ziel = next((b for b in aus_bloecke if not b.get("wiederholend")), None)
    if ziel is not None:
        felder = ziel.setdefault("felder", {})
        felder.setdefault("BT-3", {"fest": "380"})
        if not _hat_spalte("BT-5"):
            felder.setdefault("BT-5", {"fest": "EUR"})
    p = {
        "profil": name,
        "version": 2,
        "beschreibung": f"Blöcke, eingerichtet mit dem Assistenten aus {Path(datei).name}: {fmt.zusammenfassung}",
        "datei": {
            "muster": f"*{Path(datei).suffix.lower() or '.csv'}",
            "kodierung": fmt.kodierung,
            "trennzeichen": fmt.trennzeichen,
            "textbegrenzer": '"',
            "kopfzeile": False,
        },
        "zahlen": {"dezimal": fmt.dezimal, "tausender": fmt.tausender},
        "datum": {"format": fmt.datum},
        "aufbau": {"art": "bloecke", "kopfzeile_schwelle": 2, "textzeile": tz},
        "bloecke": aus_bloecke,
        "mappings": {"einheiten": eh, "steuer": st},
    }
    _tabelle_ins_profil(p, fmt)
    sa = satzart_spalte
    if sa in (None, ""):
        sa = next(
            ((b.get("satzart_spalte") or None) for b in bloecke if b.get("satzart_spalte")),
            None,
        )
    if sa in (None, ""):
        for b in bloecke:
            for r in b.get("anfang") or []:
                if isinstance(r, dict) and r.get("art") == "satzart" and r.get("spalte"):
                    sa = r.get("spalte")
                    break
    if sa not in (None, ""):
        p["aufbau"]["satzart_spalte"] = sa
    return p
