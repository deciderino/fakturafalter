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

from . import codelisten, steuerfaelle
from .pdferkennung import einheit_code
from .werte import csv_lesen, dekodieren, trennzeichen_erkennen

# (Feld, Anzeige, Teil, Typ, Pflicht)
FELDER: list[tuple[str, str, str, str, bool]] = [
    ("BT-1", "Rechnungsnummer", "kopf", "text", True),
    ("BT-2", "Rechnungsdatum", "kopf", "datum", True),
    ("BT-72", "Leistungsdatum", "kopf", "datum", False),
    ("kundennummer", "Kundennummer", "kopf", "text", False),
    ("BT-44", "Kunde – Name (Zeile 1)", "kopf", "text", False),
    ("kaeufer_name_2", "Kunde – Name (Zeile 2)", "kopf", "text", False),
    ("kaeufer_name_3", "Kunde – Name (Zeile 3)", "kopf", "text", False),
    ("BT-50", "Kunde – Straße", "kopf", "text", False),
    ("BT-51", "Kunde – Adresszusatz", "kopf", "text", False),
    ("BT-53", "Kunde – PLZ", "kopf", "text", False),
    ("BT-52", "Kunde – Ort", "kopf", "text", False),
    ("BT-55", "Kunde – Land", "kopf", "text", False),
    ("BT-48", "Kunde – USt-IdNr.", "kopf", "text", False),
    ("BT-49", "Kunde – E-Rechnungsadresse", "kopf", "text", False),
    ("BT-10", "Leitweg-ID / Käuferreferenz", "kopf", "text", False),
    ("BT-13", "Bestellnummer", "kopf", "text", False),
    ("BT-112", "Summe brutto (Kontrolle)", "kopf", "zahl", False),
    ("BT-109", "Summe netto (Kontrolle)", "kopf", "zahl", False),
    ("BT-110", "Summe USt (Kontrolle)", "kopf", "zahl", False),
    ("skonto_satz", "Skonto", "kopf", "prozent", False),
    ("skonto_tage", "Zahlungsziel mit Skonto", "kopf", "tage", False),
    ("skonto_basisbetrag", "Skonto-Basisbetrag", "kopf", "zahl", False),
    ("skonto_satz_2", "Skonto 2", "kopf", "prozent", False),
    ("skonto_tage_2", "Zahlungsziel mit Skonto 2", "kopf", "tage", False),
    ("skonto_basisbetrag_2", "Skonto-Basisbetrag 2", "kopf", "zahl", False),
    ("zahlungsziel_tage", "Zahlungsziel ohne Abzug", "kopf", "tage", False),
    ("BT-126", "Positionsnummer", "position", "text", False),
    ("BT-155", "Artikelnummer", "position", "text", False),
    ("BT-153", "Bezeichnung", "position", "text", True),
    ("BT-129", "Menge", "position", "zahl", True),
    ("BT-130", "Einheit", "position", "text", False),
    ("BT-146", "Einzelpreis netto", "position", "zahl", True),
    ("BT-149", "Preiseinheit (pro 100 …)", "position", "zahl", False),
    ("gesamt_kontrolle", "Positionsbetrag netto (Kontrolle)", "position", "zahl", False),
    ("steuer", "Steuer (Satz oder Schlüssel)", "position", "text", True),
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
    ("BT-148", "Bruttopreis vor Preisnachlass", "position", "zahl", False),
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
    ("BT-5", "Währung (z. B. EUR, USD)", "kopf", "text", False),
    ("kurs", "Umrechnungskurs (1 EUR = … Fremdwährung)", "kopf", "zahl", False),
    ("kursdatum", "Kursdatum", "kopf", "datum", False),
    ("BT-111", "Umsatzsteuer in EUR", "kopf", "zahl", False),
]
FELD = {f[0]: f for f in FELDER}
# Freiwillige Felder ab 0.6.0 nur bei genauem Spaltennamen vorschlagen (kein Wortanfang: „Versanddatum“ ≠ Fracht)
NUR_GENAU = frozenset(f[0] for f in FELDER[FELDER.index(FELD["belegart"]) :])

_SYNONYME = {
    "BT-1": "rechnungsnummer rechnungsnr renr rgnr belegnr belegnummer invoicenumber invoiceno invoice rechnung beleg nr nummer",
    "BT-2": "rechnungsdatum belegdatum rgdatum redatum datum invoicedate issuedate date",
    "BT-72": "leistungsdatum lieferdatum deliverydate leistung",
    "kundennummer": "kundennummer kundennr kdnr kdnummer kundenid customerid customerno debitor debitornr",
    "BT-44": "kundenbezeichnung1 kundenbezeichnung kundename1 name1 "
    "kundenname kunde name firma empfaenger empfänger customername customer",
    "kaeufer_name_2": "kundenbezeichnung2 kundename2 kunde2 name2 firma2",
    "kaeufer_name_3": "kundenbezeichnung3 kundename3 kunde3 name3 firma3",
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
    "gesamt_kontrolle": "gesamtnetto gpnetto gp positionsbetrag nettobetrag betrag",
    "steuer": "steuersatz steuerschluessel steuerschlüssel stschl mwst mwstsatz ust ustsatz steuer vat tax",
    "belegart": "belegart belegtyp dokumentart rechnungsart doctype documenttype",
    "BT-25": "bezugauf bezugsrechnungsnummer ursprungsrechnung bezugsrechnung originalrechnung rechnungsbezug korrekturzu",
    "BT-26": "bezugvom bezugsrechnungsdatum ursprungsdatum bezugsdatum originaldatum",
    "BT-73": "zeitraumvon leistungvon abrechnungvon",
    "BT-74": "zeitraumbis leistungbis abrechnungbis",
    "zeilenart": "zeilenart positionsart postyp linetype",
    "BT-138": "rabattprozent rabatt rabattsatz nachlassprozent discountpercent",
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

    @property
    def zusammenfassung(self) -> str:
        t = {";": "Semikolon", ",": "Komma", "\t": "Tabulator", "|": "Senkrechter Strich"}.get(
            self.trennzeichen, self.trennzeichen
        )
        k = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8", "cp1252": "Windows-1252"}.get(
            self.kodierung, self.kodierung
        )
        return f"{t} · {k} · Dezimal{'komma' if self.dezimal == ',' else 'punkt'}"


def spalte(fmt: Format, name: str) -> list[str]:
    i = fmt.kopf.index(name)
    return [z[i].strip() for z in fmt.zeilen if i < len(z)]


def format_erkennen(datei: Path, kodierung: str = "auto", trennzeichen: str = "auto") -> Format:
    """Kodierung, Trennzeichen, Dezimalzeichen und Datumsformat vorschlagen (alles änderbar)."""
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


# Spaltennamen, die Name oder Nummer des Kunden sein können – entschieden wird an den Werten
_KUNDE_MEHRDEUTIG = frozenset(("kunde", "kunden", "customer", "kd"))


def _sieht_nach_nummer_aus(werte: list[str]) -> bool:
    """„K-1001“, „10023“, „KD/77“ – kurz, ohne Leerzeichen, mit Ziffer."""
    werte = [w.strip() for w in werte if w.strip()]
    return bool(werte) and all(
        len(w) <= 20 and re.fullmatch(r"[A-Za-z]{0,4}[-./]?\d[\w./-]*", w) for w in werte
    )


def spalten_vorschlagen(kopf: list[str], zeilen: list[list[str]] | None = None) -> dict[str, str]:
    """-> {Feld: Spalte}. Erst exakte Treffer (normalisiert), dann Wortanfänge; jede Spalte höchstens einmal.
    Mit ``zeilen`` wird eine Spalte „Kunde“ mit Werten wie „K-1001“ als Kundennummer vorgeschlagen, sonst als Name."""
    aus = _spalten_nach_namen(kopf)
    s = aus.get("BT-44")
    if s and "kundennummer" not in aus and _norm(s) in _KUNDE_MEHRDEUTIG and zeilen:
        i = kopf.index(s)
        if _sieht_nach_nummer_aus([z[i] for z in zeilen if i < len(z)]):
            aus["kundennummer"] = aus.pop("BT-44")
    # „Artikel“ allein ist meist die Bezeichnung; nur Artikelnummer, wenn es schon eine Bezeichnung gibt
    if "BT-153" not in aus and _norm(aus.get("BT-155") or "") == "artikel":
        aus["BT-153"] = aus.pop("BT-155")
    return aus


def _spalten_nach_namen(kopf: list[str]) -> dict[str, str]:
    frei = {_norm(s): s for s in kopf if s}
    aus: dict[str, str] = {}
    for genau in (True, False):
        for f, syn in _SYNONYME.items():
            if f in aus or (not genau and f in NUR_GENAU):
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
    fehlt = [FELD[f][1] for f, *_r, pflicht in FELDER if pflicht and not zuordnung.get(f)]
    if not (zuordnung.get("kundennummer") or zuordnung.get("BT-44")):
        fehlt.append("Kundennummer oder Kunde – Name")
    return fehlt


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


def profil_bauen(
    name: str,
    datei: Path,
    fmt: Format,
    zuordnung: dict[str, str],
    steuer: dict[str, str],
    einheiten: dict[str, str],
    kundenstamm: str | None,
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
        if f == "BT-112":
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
    gleich = [zuordnung[f] for f in ("BT-2", "kundennummer") if zuordnung.get(f)]
    p = {
        "profil": name,
        "version": 1,
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
    if kundenstamm and zuordnung.get("kundennummer"):
        p["kundenstamm"] = {"datei": kundenstamm, "schluessel": "kundennummer", "fehlt": "pruefen"}
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


def kundenstamm_vorschlag(k) -> str | None:
    """Vorhandenen Kundenstamm der anderen Profile weiterverwenden (relativ zum Profilordner, wenn möglich)."""
    for prof in k.csv_profile:
        d = (prof.get("kundenstamm") or {}).get("datei")
        if d:
            p = Path(d) if Path(d).is_absolute() else Path(prof["_basis"]) / d
            if p.exists():
                try:
                    return str(p.resolve().relative_to(Path(k.basis).resolve()))
                except ValueError:
                    return str(p.resolve())
    p = Path(k.basis) / "kundenstamm.csv"
    return p.name if p.exists() else None


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


def synonym_namen() -> set[str]:
    """Alle bekannten Spalten-Synonyme, normalisiert (für Block-Kopfzeilen ohne Profil)."""
    from . import csv_bloecke

    aus: set[str] = set()
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
    kundenstamm: str | None,
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
        if typ in ("kopf", "positionen", "beleg", "kunde") or bool(b.get("wiederholend")):
            felder.setdefault("BT-3", {"fest": "380"})
            felder.setdefault("BT-5", {"fest": "EUR"})
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
    p = {
        "profil": name,
        "version": 1,
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
    if kundenstamm:
        p["kundenstamm"] = {"datei": kundenstamm, "schluessel": "kundennummer", "fehlt": "pruefen"}
    return p
