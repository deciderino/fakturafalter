# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Internes Rechnungsmodell nach EN 16931 (alle Business Terms, die CSV- und XML-Eingang übernehmen; seit 0.6.0
auch Zu-/Abschläge, Gutschrift/Korrektur, Lastschrift, Lieferung, Referenzen, Anhänge).

Jedes Feld kann Herkunft und Sicherheit tragen (``Rechnung.herkunft``), damit spätere
Prüfansichten zeigen können, woher ein Wert stammt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Herkunft:
    quelle: str  # z.B. "csv:variante-b.csv Zeile 3", "pdf:druck.pdf S.1", "stamm", "berechnet"
    sicherheit: float = 1.0


@dataclass
class Hinweis:
    stufe: str  # "info" | "warnung" | "pruefen" | "fehler"
    text: str
    feld: str | None = None

    def __str__(self) -> str:
        f = f"[{self.feld}] " if self.feld else ""
        return f"{self.stufe.upper()}: {f}{self.text}"


@dataclass
class Anschrift:
    strasse: str = ""  # BT-35 / BT-50
    plz: str = ""  # BT-38 / BT-53
    ort: str = ""  # BT-37 / BT-52
    land: str = "DE"  # BT-40 / BT-55
    zusatz: str = ""  # BT-36 / BT-51 Adresszeile 2 (z. B. Abteilung, Gebäude, Postfach)
    zeile3: str = ""  # BT-162 / BT-163 / BT-165 Adresszeile 3
    region: str = ""  # BT-39 / BT-54 / BT-79 Bundesland/Region

    def __bool__(self) -> bool:
        return any((self.strasse, self.plz, self.ort, self.zusatz, self.zeile3, self.region))


@dataclass
class Partei:
    name: str = ""  # BT-27 / BT-44
    anschrift: Anschrift = field(default_factory=Anschrift)
    ust_id: str = ""  # BT-31 / BT-48
    steuernummer: str = ""  # BT-32 (nur Verkäufer)
    elektronische_adresse: str = ""  # BT-34 / BT-49 (schemeID EM)
    kontakt_name: str = ""  # BT-41 / BT-56
    kontakt_telefon: str = ""  # BT-42 / BT-57
    kontakt_email: str = ""  # BT-43 / BT-58
    register: str = (
        ""  # BT-30 Registernummer Verkäufer bzw. BT-47 Registerkennung Käufer (ab 0.9.7)
    )
    kennung: str = ""  # interne Kundennummer (BT-46 Buyer identifier)
    handelsname: str = ""  # BT-28 / BT-45
    rechtliches: str = ""  # BT-33 weitere rechtliche Angaben (nur Verkäufer)
    # Käufer aus der CSV (ab 0.9.5): Kundenbezeichnung 1–3 als eigene Zeilen im Adressblock der Sichtseite.
    # ``name`` (BT-44) ist dann die Verbindung dieser Zeilen mit je einem Leerzeichen. Leer = eine Zeile ``name``.
    name_zeilen: list[str] = field(default_factory=list)
    # Verkäufer (ab 0.9.7): Kleinunternehmer nach § 19 UStG – alle Positionen Kategorie E, 0 %, Hinweistext
    kleinunternehmer: bool = False
    kleinunternehmer_text: str = ""  # leer = Standardtext (steuerfaelle.FAELLE["KU"])

    def namenszeilen(self) -> list[str]:
        """Namenszeilen für den Adressblock. Passen die gespeicherten Zeilen nicht mehr zu ``name`` (z. B. Name
        in der Prüfansicht geändert), gilt ``name`` als eine Zeile – so steht in PDF und XML derselbe Name."""
        if self.name_zeilen and " ".join(self.name_zeilen) == self.name:
            return list(self.name_zeilen)
        return [self.name] if self.name else []


@dataclass
class Steuer:
    kategorie: str = "S"  # BT-151 / BT-118
    satz: Decimal = Decimal("19")  # BT-152 / BT-119
    befreiungsgrund: str = ""  # BT-120
    befreiungscode: str = ""  # BT-121

    @property
    def schluessel(self) -> tuple:
        return (self.kategorie, self.satz, self.befreiungsgrund, self.befreiungscode)


@dataclass
class ZuAbschlag:  # BG-20/BG-21 (Beleg) bzw. BG-27/BG-28 (Position)
    zuschlag: bool = False  # ChargeIndicator: False = Abschlag/Nachlass, True = Zuschlag
    betrag: Decimal | None = None  # BT-92/99, BT-136/141 (None = aus Prozent × Basis rechnen)
    basis: Decimal | None = None  # BT-93/100, BT-137/142
    prozent: Decimal | None = None  # BT-94/101, BT-138/143
    grund: str = ""  # BT-97/104, BT-139/144
    grund_code: str = ""  # BT-98/105 (UNTDID 5189 / 7161), BT-140/145
    steuer: Steuer | None = (
        None  # BT-95/96 bzw. BT-102/103 (nur Belegebene; None = wie die Positionen)
    )
    ist_betrag: Decimal = Decimal(
        "0"
    )  # berechnet (rechnen.py): gerundeter Betrag für Ausgabe und Summen
    ist_basis: Decimal | None = None  # berechnet: Basis, falls nur Prozent angegeben war

    @property
    def vorzeichen(self) -> int:
        return 1 if self.zuschlag else -1


@dataclass
class Merkmal:  # BG-32
    name: str  # BT-160
    wert: str  # BT-161


@dataclass
class Klassifizierung:  # BT-158
    code: str
    schema: str = ""  # BT-158-1 (UNTDID 7143, z. B. „TST“, „IB“)
    version: str = ""  # BT-158-2


@dataclass
class Position:
    nr: str = ""  # BT-126
    artikelnummer: str = ""  # BT-155
    bezeichnung: str = ""  # BT-153
    menge: Decimal | None = None  # BT-129 (None = fehlt in der Quelle -> Pflichtprüfung hält an)
    einheit: str = ""  # BT-130 (UN/ECE Rec 20); "" = fehlt, kein stilles C62
    menge_roh: str = ""  # Mengenangabe wie in der CSV (Sichtseite, Option menge_exakt)
    einheit_roh: str = ""  # Einheitentext wie in der CSV (Sichtseite, Option einheit=csv)
    einheit_angenommen: bool = False  # BT-130 fehlte, Stück (H87) aus dem Profil gesetzt
    einzelpreis: Decimal | None = None  # BT-146 (netto); None = fehlt
    preiseinheit: Decimal = Decimal(
        "1"
    )  # BT-149 Basismenge des Preises (z. B. 100 = „pro 100 Stk“)
    steuer: Steuer = field(default_factory=Steuer)
    netto: Decimal | None = None  # BT-131 (wird berechnet)
    kontrolle_gesamt: Decimal | None = None  # Gesamt laut Quelle (nur Prüfung)
    bruttopreis: Decimal | None = None  # BT-148 Brutto-Einzelpreis (vor Preisnachlass)
    preisrabatt: Decimal | None = (
        None  # BT-147 Preisnachlass je Preiseinheit (BT-146 = BT-148 − BT-147)
    )
    zu_abschlaege: list[ZuAbschlag] = field(default_factory=list)  # BG-27/BG-28
    notiz: str = ""  # BT-127
    leistung_von: date | None = None  # BT-134 (BG-26)
    leistung_bis: date | None = None  # BT-135
    beschreibung: str = ""  # BT-154
    # Text-/Leerzeilen ÜBER der Position auf der Sichtseite (in der Bezeichnungsspalte).
    # Leerer String = gewollte Leerzeile. Gehört nicht in die XML der Position;
    # Text vor der ersten Position steht standardmäßig in Rechnung.bemerkungen (BT-22).
    zeilen_davor: list[str] = field(default_factory=list)
    # Kommentarzeilen UNTER der Position (Sichtseite ohne Vorsatz „Beschreibung:“).
    # In der XML bleiben sie BT-154. Leerer String = gewollte Leerzeile.
    kommentar_unten: list[str] = field(default_factory=list)
    kaeufer_artikelnummer: str = ""  # BT-156
    standard_id: str = ""  # BT-157 (z. B. GTIN)
    standard_schema: str = ""  # BT-157-1 (ISO 6523 ICD, GTIN = 0160)
    ursprungsland: str = ""  # BT-159
    merkmale: list[Merkmal] = field(default_factory=list)  # BG-32
    klassifizierungen: list[Klassifizierung] = field(default_factory=list)  # BT-158
    bestellposition: str = ""  # BT-132
    objektkennung: str = ""  # BT-128
    buchungsreferenz: str = ""  # BT-133


@dataclass
class SteuerZeile:  # BG-23
    steuer: Steuer
    basis: Decimal  # BT-116
    betrag: Decimal  # BT-117


@dataclass
class Summen:  # BG-22
    positionen_netto: Decimal = Decimal("0")  # BT-106
    abschlaege: Decimal = Decimal("0")  # BT-107
    zuschlaege: Decimal = Decimal("0")  # BT-108
    netto: Decimal = Decimal("0")  # BT-109
    ust: Decimal = Decimal("0")  # BT-110
    ust_steuerwaehrung: Decimal | None = None  # BT-111 (nur bei BT-6, ab 0.9.7)
    brutto: Decimal = Decimal("0")  # BT-112
    vorausbezahlt: Decimal = Decimal("0")  # BT-113
    rundung: Decimal = Decimal("0")  # BT-114
    zahlbar: Decimal = Decimal("0")  # BT-115
    steuerzeilen: list[SteuerZeile] = field(default_factory=list)


@dataclass
class SkontoStufe:
    """Eine maschinenlesbare Skontostufe für BT-20 (XRechnung-Konvention #SKONTO#)."""

    tage: int
    satz: Decimal
    basisbetrag: Decimal | None = None


@dataclass
class Zahlung:
    art: str = "58"  # BT-81 (58 = SEPA-Überweisung)
    iban: str = ""  # BT-84
    bic: str = ""  # BT-86
    kontoinhaber: str = ""  # BT-85
    bedingungen: str = ""  # BT-20 Klartext, ohne #SKONTO#-Zeilen
    faellig: date | None = None  # BT-9 (Netto-Fälligkeit, nicht das Skontodatum)
    ziel_tage: int | None = None
    skonto: list[SkontoStufe] = field(default_factory=list)  # bis zu 2 Stufen für #SKONTO#
    verwendungszweck: str = ""  # BT-83 (leer = Rechnungsnummer)
    info: str = ""  # BT-82 Zahlungsart als Text
    mandat: str = ""  # BT-89 Mandatsreferenz (Lastschrift, BG-19)
    glaeubiger_id: str = ""  # BT-90 Gläubiger-ID
    lastschrift_iban: str = ""  # BT-91 belastetes Konto (IBAN des Käufers)
    karte: str = ""  # BT-87 Kartennummer (nur letzte Stellen)
    karteninhaber: str = ""  # BT-88

    @property
    def lastschrift(self) -> bool:
        return self.art in ("49", "59")


@dataclass
class Rechnungsbezug:  # BG-3
    nummer: str  # BT-25
    datum: date | None = None  # BT-26


@dataclass
class Lieferung:  # BG-13
    name: str = ""  # BT-70
    ort_id: str = ""  # BT-71
    ort_schema: str = ""  # BT-71-1
    anschrift: Anschrift = field(default_factory=lambda: Anschrift(land=""))  # BG-15 (BT-75..80)

    def __bool__(self) -> bool:
        return bool(self.name or self.ort_id or self.anschrift)


@dataclass
class Referenzen:
    auftrag: str = ""  # BT-14 Auftragsbestätigung (Verkäufer)
    wareneingang: str = ""  # BT-15
    projekt: str = ""  # BT-11
    projekt_name: str = ""  # (CII: Name des Projekts; leer = BT-11)
    vertrag: str = ""  # BT-12
    lieferschein: str = ""  # BT-16
    ausschreibung: str = ""  # BT-17
    objekt: str = ""  # BT-18
    objekt_schema: str = ""  # BT-18-1
    buchung: str = ""  # BT-19

    def __bool__(self) -> bool:
        return any(vars(self).values())


@dataclass
class Zahlungsempfaenger:  # BG-10
    name: str = ""  # BT-59
    kennung: str = ""  # BT-60
    register: str = ""  # BT-61


@dataclass
class Steuervertreter:  # BG-11
    name: str = ""  # BT-62
    ust_id: str = ""  # BT-63
    anschrift: Anschrift = field(default_factory=Anschrift)  # BG-12


@dataclass
class Anhang:  # BG-24
    kennung: str  # BT-122
    beschreibung: str = ""  # BT-123
    uri: str = ""  # BT-124
    daten: bytes = b""  # BT-125 (eingebettet)
    mime: str = ""  # BT-125-1
    dateiname: str = ""  # BT-125-2


@dataclass
class Rechnung:
    nummer: str = ""  # BT-1
    datum: date | None = None  # BT-2
    art: str = "380"  # BT-3
    waehrung: str = "EUR"  # BT-5
    # Fremdwährung (ab 0.9.7): Steuerwährung BT-6 (immer EUR), Kurs „1 EUR = x BT-5“ aus den Daten, BT-111 laut Quelle
    steuerwaehrung: str = ""  # BT-6
    kurs: Decimal | None = None
    kursdatum: date | None = None
    ust_eur_quelle: Decimal | None = None  # BT-111 aus CSV/XML/Druck (Gegenprüfung mit dem Kurs)
    steuerhinweis: str = (
        ""  # Hinweistext zur Steuer aus dem Druck/der Quelle (z. B. „Steuerschuldnerschaft …“)
    )
    leistungsdatum: date | None = None  # BT-72
    leistung_von: date | None = None  # BT-73 (BG-14 Rechnungszeitraum)
    leistung_bis: date | None = None  # BT-74
    bestellnummer: str = ""  # BT-13
    leitweg_id: str = ""  # BT-10 (Käuferreferenz)
    kundennummer: str = ""
    verkaeufer: Partei = field(default_factory=Partei)
    kaeufer: Partei = field(default_factory=Partei)
    zahlung: Zahlung = field(default_factory=Zahlung)
    positionen: list[Position] = field(default_factory=list)
    bemerkungen: list[tuple[str, str]] = field(default_factory=list)  # (Text, SubjectCode) BG-1
    summen: Summen = field(default_factory=Summen)
    kontrolle: dict[str, Decimal] = field(default_factory=dict)  # z.B. {"BT-112": ...} laut Quelle
    ausgabeformat: str = "ZUGFERD_EN16931"
    herkunft: dict[str, Herkunft] = field(default_factory=dict)
    hinweise: list[Hinweis] = field(default_factory=list)
    quelle: str = ""  # Datei, aus der die Daten stammen
    sicht_pdf: object | None = None  # (Pfad, [Seitenindizes]) des Original-Drucks oder None
    sicht: dict = field(default_factory=dict)  # Darstellung Sichtseite (Profil, nicht XML)
    profil: str = ""  # Name des CSV-Profils (für Gegenprüfung/Anlernen)
    zu_abschlaege: list[ZuAbschlag] = field(default_factory=list)  # BG-20/BG-21
    vorausbezahlt: Decimal = Decimal("0")  # BT-113 laut Quelle (geht in die Summen)
    rundung: Decimal = Decimal("0")  # BT-114
    bezuege: list[Rechnungsbezug] = field(default_factory=list)  # BG-3
    lieferung: Lieferung = field(default_factory=Lieferung)  # BG-13
    referenzen: Referenzen = field(default_factory=Referenzen)
    zahlungsempfaenger: Zahlungsempfaenger | None = None  # BG-10
    steuervertreter: Steuervertreter | None = None  # BG-11
    anhaenge: list[Anhang] = field(default_factory=list)  # BG-24

    def hinweis(self, stufe: str, text: str, feld: str | None = None) -> None:
        self.hinweise.append(Hinweis(stufe, text, feld))

    @property
    def status(self) -> str:
        stufen = {h.stufe for h in self.hinweise}
        if "fehler" in stufen:
            return "fehler"
        if "pruefen" in stufen:
            return "pruefen"
        return "ok"
