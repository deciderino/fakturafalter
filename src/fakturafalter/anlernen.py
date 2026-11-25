# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Anlern-Assistent für „Nur PDF“ (ohne CSV): Werte vorschlagen, Klicks und Eingaben annehmen,
Positionstabelle beschreiben, Rechnung erzeugen und die Vorlage fortschreiben.

Die Oberfläche (gui/anlernen.py) ist nur eine Hülle um ``Sitzung``. Gelernt wird wie bei PDF + CSV:
``pdferkennung.lernen`` sucht die bestätigten Werte im Druck und merkt sich ihre Lage. Ein Klick in die PDF
liefert also nur den Wert; wo er steht, findet die Erkennung selbst. Nach 5 Rechnungen in Folge, bei denen die
Vorlage alles richtig gelesen hat (also nichts korrigiert werden musste), gilt sie als sicher."""

from __future__ import annotations

import copy
import logging
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field, fields
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import (
    adapter_pdf,
    dateien,
    pdferkennung,
    pflichtpruefung,
    protokoll,
    rechnen,
    steuerfaelle,
    zahlungsziel,
)
from .absender import Absender, erkennen_aus_zeilen
from .anschrift import _STRASSE, PLZ_ORT
from .aufbau import rechnung_bauen
from .konfig import Konfig
from .modell import Herkunft, Rechnung
from .pdferkennung import (  # EINHEIT_NAMEN/EINHEITEN: Re-Export für GUI und Tests
    EINHEIT_NAMEN,  # noqa: F401
    EINHEITEN,  # noqa: F401
    Wort,
    Zeile,
    betraege,
    daten,
    einheit_code,
    norm,
    zahlen,
    zeitraum,
)

log = logging.getLogger(__name__)

# Feld: (Bezeichnung, Typ, Pflicht?). Reihenfolge = Reihenfolge im Assistenten.
FELDER: dict[str, tuple[str, str, bool]] = {
    "BT-1": ("Rechnungsnummer", "text", True),
    "BT-2": ("Rechnungsdatum", "datum", True),
    "leistung": ("Leistungsdatum oder -zeitraum", "leistung", True),
    "BT-44": ("Käufer: Name", "text", True),
    "BT-51": ("Käufer: Adresszusatz (freiwillig)", "text", False),
    "BT-163": ("Käufer: Adresszeile 3 (freiwillig)", "text", False),
    "BT-56": ("Käufer: Kontaktstelle (freiwillig)", "text", False),
    "BT-50": ("Käufer: Straße und Hausnummer", "text", True),
    "BT-53": ("Käufer: PLZ", "text", True),
    "BT-52": ("Käufer: Ort", "text", True),
    "BT-109": ("Nettobetrag", "betrag", True),
    "BT-119": ("Steuersatz", "satz", True),
    "BT-110": ("Umsatzsteuer", "betrag", False),
    "BT-112": ("Bruttobetrag", "betrag", True),
    "BT-20": ("Fälligkeit oder Zahlungsbedingung", "text", False),
    "BT-13": ("Bestellnummer (freiwillig)", "text", False),
    "kundennummer": ("Kundennummer (freiwillig)", "text", False),
    # Gutschrift: nur über einen Rahmen um den Titel bzw. die Bezugszeile (keine Suche auf der ganzen Seite)
    "BT-3": ("Belegart: Titel im Druck (freiwillig)", "text", False),
    "BT-25": ("Bezug: Nummer der Ursprungsrechnung (bei Gutschrift)", "text", False),
    # ab 0.9.7: Bereich „Steuerhinweis & Kennungen“ (alles freiwillig)
    "steuerhinweis": ("Steuerhinweis (z. B. Reverse Charge, § 19 UStG)", "text", False),
    "BT-48": ("Käufer: USt-IdNr. (freiwillig)", "text", False),
    "BT-47": ("Käufer: Registernummer (freiwillig)", "text", False),
    "BT-55": ("Käufer: Land (freiwillig)", "land", False),
    "BT-80": ("Lieferland (freiwillig)", "land", False),
    "BT-10": ("Leitweg-ID / Käuferreferenz (freiwillig)", "text", False),
    "BT-5": ("Währung (freiwillig, z. B. USD)", "text", False),
    "kurs": ("Umrechnungskurs (1 EUR = …)", "kurs", False),
    "BT-111": ("Umsatzsteuer in EUR", "betrag", False),
}
# Steuerfall der Vorlage (Auswahl im Assistenten): "" = aus dem Hinweistext im Druck vorschlagen
STEUERFAELLE = ("S", *steuerfaelle.REIHENFOLGE)
STEUERFELDER = ("steuerhinweis", "BT-48", "BT-47", "BT-55", "BT-80", "BT-10", "BT-5", "kurs", "BT-111")
PFLICHT = [f for f, (_, _, p) in FELDER.items() if p]
ZONEN_FELDER = pdferkennung.BEREICHE  # Bereich -> Felder (siehe „Bereiche festlegen“)
ZONEN = tuple(pdferkennung.BEREICHE)
KAEUFER_FELDER_ANLERNEN = (
    pdferkennung.BLOCKFELDER
)  # Name, Zusatz (BT-51, Altvorlagen/Hand), Straße, PLZ, Ort
KAEUFER_NEBENFELDER = ("BT-56", "BT-163")  # Kontaktstelle, Adresszeile 3 (eigene Assistentenfelder)
TYP_HINWEIS = {
    "BT-53": "Gelesener Wert ist keine PLZ (5 Ziffern) – nicht übernommen.",
    "BT-2": "Gelesener Wert ist kein gültiges Datum – nicht übernommen.",
    "BT-109": "Gelesener Wert ist kein Betrag – nicht übernommen.",
    "BT-110": "Gelesener Wert ist kein Betrag – nicht übernommen.",
    "BT-112": "Gelesener Wert ist kein Betrag – nicht übernommen.",
    "BT-119": "Gelesener Wert ist kein Steuersatz – nicht übernommen.",
    "BT-3": "Gelesener Wert ist kein Belegtitel – nicht übernommen.",
    "BT-25": "Gelesener Wert enthält keine Rechnungsnummer – nicht übernommen.",
    "BT-48": "Gelesener Wert ist keine USt-IdNr. – nicht übernommen.",
    "BT-55": "Gelesener Wert ist kein Land – nicht übernommen.",
    "BT-80": "Gelesener Wert ist kein Land – nicht übernommen.",
    "BT-111": "Gelesener Wert ist kein Betrag – nicht übernommen.",
}
BELEGART_HINWEIS = {
    "381": "Gutschrift erkannt (Belegart 381).",
    "380": "Rechnung (Belegart 380).",
}
BEZUG_FEHLT = (
    "Gutschrift: Bitte die Nummer der Ursprungsrechnung angeben (Rahmen um die Bezugszeile ziehen) – "
    "ohne Bezug kann die Gutschrift nicht gespeichert werden (§ 31 Abs. 5 UStDV)."
)
BEZUG_NUR_GUTSCHRIFT = "Bezug gilt nur für Gutschriften – bei einer Rechnung leer lassen."


def steuerwert_mapping(wahl: str, text: str = "") -> dict:
    """Auswahl im Assistenten („S:19“, „S:7“, „AE“, „K“, „G“, „O“, „KU“) -> Steuer-Mapping der Vorlage."""
    if wahl.startswith("S:"):
        return {"BT-151": "S", "BT-152": wahl[2:]}
    if wahl == "hinweis":
        return {"fall": "hinweis"}
    m = {"fall": wahl, **steuerfaelle.mapping(wahl, text)}
    if not text:
        m.pop("BT-120", None)  # Text je Rechnung aus dem Druck, sonst Standardtext
    return m


def steuerwert_kennung(m: dict | None) -> str:
    """Steuer-Mapping -> Auswahlwert („S:19“, „AE“ …); "" wenn nicht zuzuordnen."""
    if not m:
        return ""
    f = str(m.get("fall") or "")
    if f in steuerfaelle.FAELLE or (f == "hinweis" and "BT-152" not in m):
        return f
    if str(m.get("BT-151", "S")) == "S":
        return f"S:{pdferkennung._satz(Decimal(str(m.get('BT-152', 0))))}".replace(",", ".")
    return ""


def wert_passt_feld(feld: str, text: str) -> bool:
    """Typprüfung je Feld (PLZ, Datum, Betrag, Satz); Felder ohne Typregel passen immer."""
    if feld in ("leistung", "BT-55", "BT-80", "BT-111"):
        return lesen(feld, text) is not None
    return feld not in TYP_HINWEIS or pdferkennung.wert_passt(feld, text)


# Spalten der Positionstabelle: Schlüssel -> Bezeichnung im Auswahlfeld
SPALTEN: dict[str, str] = {
    "BT-153": "Bezeichnung",
    "BT-129": "Menge",
    "BT-130": "Einheit",
    "BT-146": "Einzelpreis",
    "BT-149": "Preiseinheit (z. B. pro 100)",
    "gesamt": "Gesamt",
    "steuer": "USt-Satz",
    "BT-155": "Artikelnummer",
    "BT-126": "Positionsnummer",
    "ignorieren": "ignorieren",
}
PFLICHTSPALTEN = ("BT-153", "BT-129", "BT-146", "gesamt")
_KOPFWORTE = (  # Spaltenüberschrift -> Spalte (erste passende Regel gilt)
    # „Gesamtpreis“, „Gesamt-Betrag“, „Pos.-Gesamt“, „Preis gesamt“: vor Pos.- und Preis-Regel, sonst BT-126/BT-146
    (
        r"^(pos\.?\s*-?\s*)?gesamt\s*-?\s*(preis|betrag|summe|wert|netto)|^pos\.?\s*-?\s*gesamt|^(preis|betrag)\s+gesamt$"
        r"|^g\.?\s*-?\s*preis$",  # „G-Preis“ (Gesamtpreis) neben „E-Preis“
        "gesamt",
    ),
    (r"art.*nr|artikel-?nr|art\.?-?nr|sku|material", "BT-155"),
    (r"^pos|^nr\.?$|^lfd|^#$", "BT-126"),
    (r"^pe$|preiseinh|^per$|^je$|pro\s?\d", "BT-149"),
    (r"bezeichnung|beschreibung|leistung|artikel|text|description|item|produkt", "BT-153"),
    (r"menge|anzahl|stück$|qty|quantity|^anz", "BT-129"),
    (r"einzel|preis|^(netto\s*)?ep$|price|stückpreis", "BT-146"),  # „Netto EP“
    (r"^me$|einheit|^einh|^eh$|unit", "BT-130"),
    (r"betrag|gesamt|summe|total|amount|wert|^(netto\s*)?gp$", "gesamt"),  # „Netto GP“
    (r"ust|mwst|steuer|vat|%", "steuer"),
)

HERKUNFT = "anlern-assistent"

# Beschriftung im Druck -> Feld (Wert rechts daneben oder darunter)
_BESCHRIFTUNG: dict[str, str] = {
    "BT-1": r"^(?:rechnung(?:s)?[- ]?(?:nr|nummer|no)|beleg-?(?:nr|nummer)|invoice no|rechnungs-?nr)",
    "BT-2": r"^(?:rechnungsdatum|belegdatum|datum|invoice date|date)\b",
    "leistung": r"^(?:leistungs(?:datum|zeitraum)|liefer(?:datum|termin)|versand(?:datum|tag)?\b|service period|leistung vom|lieferung vom)",
    "BT-13": r"^(?:ihre bestellung|bestell-?(?:nr|nummer|ung)|ihr auftrag|auftrags?-?(?:nr|nummer)|order no|po no|"
    r"purchase order|ihre referenz|referenz-?(?:nr|nummer))",
    "kundennummer": r"^(?:kunden-?(?:nr|nummer)|kd\.?-?(?:nr|nummer)|kunde\s*:|customer (?:no|id)|ihre kunden-?nr|"
    r"debitoren?-?(?:nr|nummer))",
    # ab 0.9.7 – nur eindeutige Beschriftungen des Kunden (die eigene USt-IdNr. steht im Briefkopf/Fuß)
    "BT-48": r"^(?:ihre\s+ust|ust-?id(?:nr)?\.?\s*(?:des\s+)?(?:kunden|empfängers|leistungsempfängers)|"
    r"kunden-?ust|your\s+vat|customer\s+vat|vat\s+(?:no|id)\.?\s+(?:of\s+)?(?:the\s+)?customer)",
    "BT-10": r"^(?:leitweg-?id|käuferreferenz|buyer\s+reference)",
    "BT-111": r"^(?:ust|umsatzsteuer|mwst|vat)\.?\s+in\s+(?:eur|€)",
}
# Beschriftungen über dem Anschriftfeld u. Ä.: nur Text, kein Wert
_BESCHRIFTUNG_ALLGEMEIN = (
    r"^(?:kunde|kundin|rechnungsempfänger(?:in)?|empfänger(?:in)?|(?:rechnungs|liefer)?anschrift|"
    r"käufer|auftraggeber(?:in)?|bill to|ship to|customer|zahlungsbedingung(?:en)?|fälligkeit|"
    r"zahlungsziel|payment terms)\b"
)
# Text-Felder, deren Wert eine Nummer ist (mindestens eine Ziffer)
_NUMMERNFELDER = ("BT-1", "BT-13", "kundennummer")


# Steuersatz in einer Steuerzeile: „19 %“ oder ohne Prozentzeichen direkt vor der Steuer („zzgl. 19,00 MwSt.“)
_STEUERSATZ = re.compile(
    r"(?<![\d.,])(\d{1,2}(?:,\d{1,2})?)\s?(?:%|(?=\s*(?:mwst|ust|umsatzsteuer)\b))", re.I
)


def steuersaetze_im_text(text: str) -> list[str]:
    """Steuersätze einer Zeile, die nach Steuer klingt („19 %“, „19,00 MwSt.“) -> ["19", "19,00"]."""
    return _STEUERSATZ.findall(text or "")


def ist_beschriftung(feld: str, text: str) -> bool:
    """Ist ``text`` eine Beschriftung („Kunden-Nr.:“, „Rechnungsempfänger“) statt eines Werts?"""
    t = norm(text)
    if not t:
        return False
    if t.endswith(":"):
        return True
    if re.search(r"\d", t) or len(t) > 40:
        return False
    if feld in _BESCHRIFTUNG and re.search(_BESCHRIFTUNG[feld], t):
        return True
    return bool(re.search(_BESCHRIFTUNG_ALLGEMEIN, t))


# ---------------------------------------------------------------- Werte lesen und anzeigen
def _de(d: Decimal, stellen: int = 2) -> str:
    s = f"{d:,.{stellen}f}"
    return s.replace(",", "\u2009").replace(".", ",").replace("\u2009", ".")


def lesen(feld: str, text: str):
    """Eingabe/Klick -> Wert (date, (von, bis), Decimal, str) oder None, wenn nicht lesbar."""
    t = " ".join(str(text or "").split()).strip(" ,;:")
    if not t:
        return None
    typ = FELDER[feld][1]
    if typ == "datum":
        d = daten(t)
        return d[0] if d else None
    if typ == "leistung":
        z = zeitraum(t)
        if z:
            return z
        d = daten(t)
        return d[0] if d else None
    if typ == "betrag":
        b = betraege(t) or zahlen(t)
        return b[0][0] if b else None
    if typ == "land":
        return steuerfaelle.land_code(t)
    if typ == "kurs":
        return t if pdferkennung.kurs_aus_text(t) else None
    if typ == "satz":
        m = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%?", t)
        if not m:
            return None
        try:
            s = Decimal(m[1].replace(",", "."))
        except InvalidOperation:  # pragma: no cover
            return None
        return s if Decimal(0) <= s <= Decimal(30) else None
    return t


def anzeigen(feld: str, w) -> str:
    """Wert -> Text im Eingabefeld (deutsche Schreibweise)."""
    if w is None:
        return ""
    if isinstance(w, tuple):
        return f"{w[0]:%d.%m.%Y} – {w[1]:%d.%m.%Y}"
    if isinstance(w, date):
        return f"{w:%d.%m.%Y}"
    if isinstance(w, Decimal):
        if FELDER[feld][1] == "satz":
            return f"{pdferkennung._satz(w)} %"
        return _de(w)
    return str(w)


# ---------------------------------------------------------------- Vorschläge
@dataclass
class Vorschlag:
    feld: str
    wert: str = ""  # Text im Eingabefeld
    status: str = "fehlt"  # erkannt | pruefen | fehlt
    woerter: list[Wort] = field(default_factory=list)  # Fundstelle in der PDF (für die Markierung)
    hinweis: str = ""
    beschriftung: list[Wort] = field(
        default_factory=list
    )  # angeklickte Beschriftung, Wert steht daneben/darunter
    bereich: tuple | None = None  # vom Nutzer gezogener Rahmen: (Seite, (x0, top, x1, bottom))
    geklickt: bool = (
        False  # Fundstelle per Klick in die PDF bestätigt (Vorlage lernt genau diese Stelle)
    )


@dataclass
class Tabelle:
    """Rahmen um die Positionstabelle (PDF-Punkte) + Spaltengrenzen mit Zuordnung."""

    seite: int = 0
    x0: float = 0
    top: float = 0
    x1: float = 0
    bottom: float = 0
    grenzen: list[float] = field(default_factory=list)  # linker Rand jeder Spalte, aufsteigend
    spalten: list[str] = field(default_factory=list)  # Zuordnung je Spalte (Schlüssel aus SPALTEN)
    preiseinheit: str = "1"  # "1", "100", "1000" oder "spalte"
    einheiten: dict[str, str] = field(
        default_factory=dict
    )  # Text im Druck -> Code (vom Nutzer geändert)
    # Spalten als eigene Rahmen („Spalte hinzufügen“): [Code, x0, x1], nach x0 sortiert. Sind welche da, gelten
    # sie statt grenzen/spalten; Wörter außerhalb aller Spaltenrahmen zählen nicht, die Betragsspalte trägt die Zeile.
    spaltenrahmen: list[list] = field(default_factory=list)
    # ab 0.9.7: Wert der Steuerspalte -> Steuerfall („S:19“, „AE“, „K“ …), vom Nutzer gewählt
    steuerwerte: dict[str, str] = field(default_factory=dict)

    def leer(self) -> bool:
        return self.x1 <= self.x0 or self.bottom <= self.top

    def codes(self) -> list[str]:
        """Zugeordnete Spalten – aus den Spaltenrahmen, sonst aus den Spaltenlinien."""
        return [r[0] for r in self.spaltenrahmen] if self.spaltenrahmen else list(self.spalten)


def _text(ws: list[Wort]) -> str:
    return " ".join(w.t for w in ws)


def _mit_doppelpunkt(abschnitte: list[list[Wort]], i: int) -> list[Wort]:
    """Abschnitt ``i`` – samt eines abgesetzten Doppelpunkts dahinter („Versandart   :“ = Beschriftung)."""
    seg = abschnitte[i]
    if i + 1 < len(abschnitte) and _text(abschnitte[i + 1]) == ":":
        return seg + abschnitte[i + 1]
    return seg


def _fremde_beschriftung(ws: list[Wort]) -> bool:
    """Beginnt der Abschnitt mit einer eigenen Beschriftung („Datum: 05.10.2026“)? Dann ist er nicht der Wert
    einer anderen, leeren Beschriftung daneben oder darüber."""
    i = next((i for i, w in enumerate(ws) if re.search(r"\w", w.t)), None)
    return i is not None and any(w.t.endswith(":") for w in ws[i : i + 3])  # auch „Versandart :“


# Anschriftfeld des Käufers, als Anteil der ersten Seite (auf A4 genau die bisherigen 380/380/100 pt)
A4_BREITE, A4_HOEHE = 595.28, 841.89
ANSCHRIFT_RECHTS = (
    380 / A4_BREITE
)  # Anschrift beginnt links davon (Fenster links, Infoblock rechts)
ANSCHRIFT_UNTEN = 380 / A4_HOEHE  # „PLZ Ort“ steht darüber (Fensterbereich, nicht Fließtext)
ANSCHRIFT_OBEN = 100 / A4_HOEHE  # und darunter (oberhalb steht der Briefkopf des Absenders)
ANSCHRIFT_HOEHE = (
    9.0  # Schrifthöhen über „PLZ Ort“: bis drei Namenszeilen, Zusatz, Straße (früher 80 pt)
)
ANSCHRIFT_BUENDIG = (
    6  # pt: so weit seitlich versetzt gehört eine Zeile darüber noch zum Anschriftblock
)


class Sitzung:
    """Eine PDF im Assistenten. Ohne Qt; die Oberfläche ruft nur diese Methoden."""

    def __init__(self, pfad: str | Path, k: Konfig):
        self.pfad = Path(pfad)
        self.k = k
        self.seiten = adapter_pdf.seiten_lesen(self.pfad)
        self.zeilen: list[Zeile] = pdferkennung.zeilen_aus(self.seiten)
        prof, v = pdferkennung.vorlage_suchen(self.zeilen, k.pdf_profile)
        self.profil: dict | None = prof
        self.vorlage: dict | None = v
        self.zaehler_grund = ""  # nach dem Speichern: warum der Freigabe-Zähler zurückgesetzt wurde
        if prof is not None:
            self.absender = Absender.aus_bloecken(prof.get("verkaeufer"), prof.get("zahlung"))
            self.absender_neu = False
        else:
            self.absender = erkennen_aus_zeilen(self._ohne_anschriftfeld())
            self.absender_neu = True
            self._absender_ergaenzen()
        # „Anschrift als Block“: (Seite, Rahmen, zerlegte Teile) – die Vorlage lernt dann einen Rahmen statt 5 Felder
        self.anschrift_block: tuple | None = None
        # Firmenname über zwei Zeilen: Wörter beider Zeilen und vorgeschlagener Anschriftblock (Seite, Rahmen,
        # Teile) – ein Feld kann nur eine Zeile lernen, der Block alle
        self._name_zeilen: list[Wort] = []
        self._block_vorschlag: tuple | None = None
        self._bt20_rahmen: tuple | None = None  # mehrzeilige Zahlungsbedingung: (Seite, Rahmen)
        # strukturelle Brüche im Anschriftblock (``pdferkennung.anschrift_brueche``) je Leseweg: Feld -> Hinweis;
        # ``anschrift_hinweise`` = die für die Vorschläge geltenden
        self._brueche: dict[str, dict[str, str]] = {"kalt": {}, "bereich": {}, "vorlage": {}}
        self.anschrift_hinweise: dict[str, str] = {}
        # „Bereiche festlegen“: Bereich -> {rahmen, seiten} (wie in der Vorlage unter ``bereiche``); Seite, auf
        # der der Nutzer den Rahmen gezogen hat (nur für die Anzeige und das Lesen in dieser PDF)
        self.zonen: dict[str, dict] = pdferkennung.bereiche_laden(v)
        self.zonen_seite: dict[str, int] = {}
        self.werte: dict[str, Vorschlag] = self.vorschlagen()
        # Steuerfall der Vorlage: "" = Vorschlag aus dem Hinweistext; sonst S/AE/K/G/O/KU (Auswahl im Assistenten)
        self.steuerfall: str = self._steuerfall_aus_vorlage()
        self.tabelle: Tabelle = self.tabelle_vorschlagen()
        self.summen_gegenprobe()
        # nach dem Speichern: Selbstkontrolle mit der neuen Vorlage -> {Feld: (bestätigt, neu gelesen)}
        self.selbstkontrolle: dict[str, tuple[str, str]] = {}
        # offene Selbstkontrolle aus der Vorlage (auch aus früheren Sitzungen): Felder hier markieren
        self.kontrolle_offen: list[str] = pdferkennung.kontrolle_offen(v)
        self.kontrolle_markieren(self.kontrolle_offen)

    def _absender_ergaenzen(self) -> None:
        """Was im Druck fehlt (z. B. IBAN), aus dem Standard-Absender der Konfiguration übernehmen –
        aber nur, wenn es derselbe Absender ist (oder im Druck gar keiner gefunden wurde)."""
        std = Absender.aus_bloecken(self.k.roh.get("absender"), self.k.roh.get("zahlung"))
        if not std.name:
            return
        a = self.absender
        if a.name and norm(a.name) != norm(std.name):
            return
        for f in fields(Absender):
            if not getattr(a, f.name) and getattr(std, f.name):
                setattr(a, f.name, getattr(std, f.name))

    # -- Wörter und Fundstellen -------------------------------------------------------------------
    def woerter(self, seite: int = 0) -> list[Wort]:
        return [w for z in self.zeilen if z.seite == seite for w in z.woerter]

    def wort_an(self, seite: int, x: float, y: float) -> tuple[str, list[Wort]] | None:
        """Klick in die PDF (Punkte) -> Text des angeklickten Abschnitts (zusammenhängende Wörter)."""
        beste = None
        for z in self.zeilen:
            if z.seite != seite or not (z.top - 3 <= y <= z.top + 12):
                continue
            for seg in z.abschnitte:
                if seg[0].x0 - 3 <= x <= seg[-1].x1 + 3:
                    d = abs(y - (z.top + 4))
                    if beste is None or d < beste[0]:
                        beste = (d, seg)
        if beste is None:
            return None
        seg = beste[1]
        # Beschriftung vor einem Doppelpunkt gehört nicht zum Wert („Rechnung Nr.: NB-26-1001“)
        for i, w in enumerate(seg[:-1]):
            if w.t.endswith(":") and w.x1 < x:
                seg = seg[i + 1 :]
        return _text(seg), seg

    def fundstelle(self, text: str, feld: str | None = None) -> list[Wort]:
        """Wo steht dieser Wert in der PDF? Erste passende Wortfolge innerhalb eines Abschnitts."""
        wert = lesen(feld, text) if feld else None
        typ = FELDER[feld][1] if feld else "text"
        ziel = norm(text)
        if not ziel:
            return []
        n_max = min(12, len(ziel.split()) + 4)
        for z in self.zeilen:
            for seg in z.abschnitte:
                for i in range(len(seg)):
                    for j in range(i + 1, min(len(seg), i + n_max) + 1):
                        t = _text(seg[i:j])
                        if norm(t) == ziel:
                            return seg[i:j]
                        if (
                            wert is not None
                            and typ in ("datum", "leistung", "betrag", "satz")
                            and (typ != "satz" or "%" in t)
                            and lesen(feld, t) == wert
                            and len(t) <= len(text) + 6
                        ):
                            return seg[i:j]
        return []

    # -- Vorschläge -------------------------------------------------------------------------------
    def _aus_vorlage(self, feld: str):
        v = self.vorlage
        if not v:
            return None
        v = {**v, "bereiche": self.zonen}  # Bereiche dieser Sitzung (evtl. gerade geändert)
        regeln = v.get("felder") or {}
        if feld in pdferkennung.BLOCKFELDER and pdferkennung.ANSCHRIFT_BLOCK in regeln:
            br: dict[str, str] = {}
            teile = pdferkennung.vorlage_anschrift_lesen(
                v, regeln[pdferkennung.ANSCHRIFT_BLOCK], self.zeilen, br
            )
            self._brueche["vorlage"] = br if teile else {}
            self._vorlage_teile = {f: t for f, (t, _ws) in teile.items()}
            return teile.get(feld)
        if feld in pdferkennung.BLOCKFELDER and self._block_vorschlag:
            return None  # alte Vorlage mit Einzelfeldern: die Regel „von unten“ gilt (Block)
        kand = ["BG-14", "BT-72"] if feld == "leistung" else [feld]
        for f in kand:
            if f in regeln:
                erg = pdferkennung.vorlage_feld_lesen(v, f, regeln[f], self.zeilen)
                if (
                    erg
                    and lesen(feld, erg[0]) is not None
                    and (
                        f not in pdferkennung.OPTIONALE_NUMMERN or pdferkennung.nummer_passt(erg[0])
                    )
                ):
                    return erg
        if feld == "BT-119":
            st = (v.get("positionen") or {}).get("steuer_fest")
            if st:
                s = Decimal(str(st.get("BT-152", "0")))
                return f"{pdferkennung._satz(s)} %", []
        return None

    def volltext(self) -> str:
        return " ".join(z.text for z in self.zeilen)

    def zahlungsbedingung_im_druck(self) -> bool:
        """Nennt der Druck eine Zahlungsbedingung (Zahlungsziel, Skonto …)? Dann ist BT-20 empfohlen."""
        return bool(
            re.search(
                r"skonto|zahlbar|ohne\s+abzug|zahlungsziel|zahlungsbeding", self.volltext(), re.I
            )
        )

    def skonto_im_druck(self) -> bool:
        return bool(re.search(r"skonto", self.volltext(), re.I))

    def zahlung_hinweis(self) -> str:
        """Hinweis zu BT-20: Skontobetrag passt nicht zu Brutto × Satz, oder Skonto im Druck, aber BT-20 leer."""
        vs = self.werte["BT-20"]
        if not vs.wert:
            if self.skonto_im_druck():
                return (
                    "Empfohlen: Die Rechnung nennt Skonto. Bitte die Zahlungsbedingung übernehmen – sonst "
                    "kann sie nicht gespeichert werden."
                )
            return (
                "Empfohlen: Die Rechnung nennt eine Zahlungsbedingung."
                if self.zahlungsbedingung_im_druck()
                else ""
            )
        brutto = self.wert("BT-112")
        return " ".join(
            zahlungsziel.skonto_hinweise(
                zahlungsziel.lesen(vs.wert), brutto if isinstance(brutto, Decimal) else None
            )
        )

    def belegart(self) -> str | None:
        """BT-3 aus dem Titel im Rahmen: „381“ (Gutschrift), „380“ – oder None, wenn kein Titel gesetzt ist."""
        t = self.werte["BT-3"].wert if "BT-3" in self.werte else ""
        return pdferkennung.belegart_code(t) if t else None

    def belegart_hinweis(self) -> str:
        """Hinweis zu BT-3/BT-25 für die Oberfläche: erkannte Belegart; bei Gutschrift ohne Bezug, was fehlt."""
        art = self.belegart()
        if art is None:
            return ""
        if art == "381" and not self.werte["BT-25"].wert:
            return BELEGART_HINWEIS[art] + " " + BEZUG_FEHLT
        return BELEGART_HINWEIS[art]

    def vorschlagen(self) -> dict[str, Vorschlag]:
        out: dict[str, Vorschlag] = {}
        kaeufer = self._kaeufer_suchen()
        zone_kaeufer = self._anschrift_aus_zone()
        for feld in FELDER:
            if feld in ZONEN_FELDER.get("kopf", ()) + ZONEN_FELDER.get("summen", ()) + ZONEN_FELDER.get(
                "steuer", ()
            ) + ("BT-20",) and self._zone_von(feld):
                out[feld] = self._vorschlag_in_zone(feld)
                continue
            if (
                feld in KAEUFER_FELDER_ANLERNEN
                and zone_kaeufer is not None
                and not self._aus_vorlage(feld)
            ):
                vs = Vorschlag(feld)
                t = zone_kaeufer.get(feld, "")
                vs.wert, vs.status = t, "pruefen" if t else "fehlt"
                vs.woerter = self.fundstelle(t, feld) if t else []
                out[feld] = vs
                continue
            vs = Vorschlag(feld)
            erg = self._aus_vorlage(feld)
            if erg:
                vs.wert = anzeigen(feld, lesen(feld, erg[0]))
                vs.woerter = list(erg[1]) or self.fundstelle(vs.wert, feld)
                vs.status = "erkannt"
            elif self._eigener_rahmen(feld):
                # Benutzerrahmen hat Vorrang: keine Suche nach der Beschriftung auf der ganzen Seite als Ersatz
                vs.hinweis = "Im gezogenen Rahmen nicht gefunden."
            elif (
                feld == "BT-119"
                and "summen" in self.zonen
                and self._vorschlag_in_zone(feld, "summen").wert
            ):
                vs = self._vorschlag_in_zone(feld, "summen")
            else:
                text, hinweis = self._heuristik(feld, kaeufer)
                if text:
                    w = lesen(feld, text)
                    vs.wert = anzeigen(feld, w) if w is not None else text
                    vs.woerter = self._kaeufer_woerter(feld, text) or self.fundstelle(text, feld)
                    vs.status = "pruefen"
                    vs.hinweis = hinweis
                    if feld == "BT-20" and self._bt20_rahmen:  # mehrzeilig: als Rahmen anbieten
                        seite, (x0, top, x1, bottom) = self._bt20_rahmen
                        vs.woerter = [
                            w
                            for zz in pdferkennung.woerter_im_bereich(
                                [z for z in self.zeilen if z.seite == seite], x0, top, x1, bottom
                            )
                            for w in zz
                        ]
                        vs.bereich = self._bt20_rahmen
            out[feld] = vs
        self._nebenfelder_fuellen(out, zone_kaeufer)
        self._anschrift_pruefen(out, zone_kaeufer is not None)
        for feld, vs in out.items():
            if vs.wert and not wert_passt_feld(feld, vs.wert):
                log.info(
                    "Anlernen %s: gelesener Wert für %s passt nicht zum Feldtyp – nicht übernommen",
                    self.pfad.name,
                    FELDER[feld][0],
                )
                out[feld] = Vorschlag(
                    feld, hinweis=TYP_HINWEIS.get(feld, "Gelesener Wert passt nicht zum Feld.")
                )
        titel = out.get("BT-3")
        bezug = out.get("BT-25")
        if bezug and bezug.wert and not (titel and pdferkennung.belegart_code(titel.wert) == "381"):
            bezug.status, bezug.hinweis = "pruefen", BEZUG_NUR_GUTSCHRIFT
        return out

    def _nebenfelder_fuellen(self, out: dict[str, Vorschlag], zone_teile: dict | None) -> None:
        """Kontaktstelle und Adresszeile 3 aus dem zerlegten Block in die Assistentenfelder übernehmen."""
        teile = (
            (self.anschrift_block or (None, None, None))[2]
            or zone_teile
            or getattr(self, "_vorlage_teile", None)
            or (self._block_vorschlag or (None, None, None))[2]
            or {}
        )
        for f in KAEUFER_NEBENFELDER:
            vs = out.get(f)
            t = (teile or {}).get(f) or ""
            if vs is None or vs.wert or not t:
                continue
            vs.wert, vs.status = t, "pruefen"
            vs.woerter = self.fundstelle(t, f)

    def _anschrift_pruefen(self, out: dict[str, Vorschlag], zone: bool) -> None:
        """Strukturelle Brüche des Anschriftblocks, aus dem die Vorschläge stammen, als „prüfen“ mit Hinweis
        melden (Werte bleiben, wie die feste Regel sie liest)."""
        quelle = [vs for f, vs in out.items() if f in KAEUFER_FELDER_ANLERNEN and vs.wert]
        if not quelle:
            self.anschrift_hinweise = {}
            return
        vorlage = any(vs.status == "erkannt" for vs in quelle)
        weg = "vorlage" if vorlage else "bereich" if zone else "kalt"
        self.anschrift_hinweise = dict(self._brueche[weg])
        for f, text in self.anschrift_hinweise.items():
            vs = out.get(f)
            if vs is None:
                continue
            if vs.status == "erkannt":
                vs.status = "pruefen"
            vs.hinweis = text
            if weg == "vorlage":
                log.info("Anlernen %s: Anschrift (Vorlage) prüfen – %s", self.pfad.name, text)

    def _eigener_rahmen(self, feld: str) -> bool:
        """Hat die Vorlage für das Feld einen vom Nutzer gezogenen Rahmen (Regel „bereich“)?"""
        regeln = (self.vorlage or {}).get("felder") or {}
        kand = ["BG-14", "BT-72"] if feld == "leistung" else [feld]
        if feld in pdferkennung.BLOCKFELDER and pdferkennung.ANSCHRIFT_BLOCK in regeln:
            kand.append(pdferkennung.ANSCHRIFT_BLOCK)
        return any((regeln.get(f) or {}).get("lage") == "bereich" for f in kand)

    def summen_gegenprobe(self) -> str:
        """Rechnerische Gegenprobe als Schiedsrichter: Summe der Positionen = Netto, Netto + USt = Brutto.
        Gehen die Vorschläge nicht auf, gewinnt die Lesart aus den Summenzeilen am Tabellenende, die aufgeht
        (Status „prüfen“); geht keine auf, werden die Summenfelder auf „prüfen“ gesetzt. -> „ok“, „gewählt“,
        „geht nicht auf“ oder „“ (nichts zu prüfen)."""
        felder = ("BT-109", "BT-110", "BT-112")
        ps = self.positionen()
        if not ps:
            return ""
        summe = sum((p.gesamt for p in ps if p.gesamt is not None), Decimal("0"))
        gelesen = {f: (w if isinstance(w := self.wert(f), Decimal) else None) for f in felder}
        block = pdferkennung.summenblock(self.pv(), self.zeilen)
        neu, art = pdferkennung.summen_lesart(summe, gelesen, [b for b, _ in block])
        if art == "gewählt":
            woerter = {b: ws for b, ws in reversed(block)}
            for f in felder:
                if neu[f] is not None and neu[f] != gelesen[f]:
                    vs = self.werte[f]
                    vs.wert, vs.status = anzeigen(f, neu[f]), "pruefen"
                    vs.woerter = list(woerter.get(neu[f], [])) or self.fundstelle(vs.wert, f)
                    vs.hinweis = (
                        "Rechnerisch bestimmt: Summe der Positionen = Netto, Netto + USt = Brutto. "
                        "Passt das?"
                    )
            log.info("Anlernen %s: Summen rechnerisch gewählt (Gegenprobe)", self.pfad.name)
        elif art == "geht nicht auf" and any(gelesen.values()):
            for f in felder:
                vs = self.werte[f]
                if vs.wert and vs.status == "erkannt":
                    vs.status = "pruefen"
                    vs.hinweis = (
                        "Summen gehen nicht auf (Positionen, Netto, USt, Brutto) – bitte prüfen."
                    )
            log.info("Anlernen %s: Summen gehen rechnerisch nicht auf – prüfen", self.pfad.name)
        return art

    # -- Bereiche („Bereiche festlegen“) ----------------------------------------------------------
    def _zone_von(self, feld: str) -> str | None:
        name = pdferkennung.bereich_von(feld)
        return name if name in self.zonen else None

    def zone_seitenfolge(self, name: str) -> list[int]:
        """Seiten, auf denen der Bereich in dieser PDF gesucht wird; die Seite, auf der er gezogen wurde, zuerst."""
        seiten = pdferkennung.bereich_seitenfolge(name, self.zonen[name], self.zeilen)
        s0 = self.zonen_seite.get(name)
        return ([s0] + [s for s in seiten if s != s0]) if s0 in seiten else seiten

    def zone_seiten(self, name: str) -> list[int]:
        """Seiten, auf denen der Rahmen angezeigt wird (nach „Gilt auf“)."""
        seiten = sorted({z.seite for z in self.zeilen}) or [0]
        art = self.zonen.get(name, {}).get("seiten", "alle")
        return seiten[:1] if art == "erste" else seiten[-1:] if art == "letzte" else seiten

    def _vorschlag_in_zone(self, feld: str, name: str | None = None) -> Vorschlag:
        """Vorschlag für ein Feld nur aus seinem Bereich (Vorlage, sonst Heuristik) – Seite für Seite."""
        name = name or self._zone_von(feld)
        b = self.zonen[name]
        alle = self.zeilen
        vs = Vorschlag(feld)
        erg = self._aus_vorlage(feld)  # liest selbst nur im Bereich (auch mitgewandert)
        if erg:
            vs.wert = anzeigen(feld, lesen(feld, erg[0]))
            vs.woerter = list(erg[1]) or self.fundstelle(vs.wert, feld)
            vs.status = "erkannt"
            return vs
        try:
            for s in self.zone_seitenfolge(name):
                rahmen = pdferkennung.bereich_rahmen_auf(self.vorlage, b, alle, s)
                self.zeilen = pdferkennung.zeilen_im_rahmen(alle, s, rahmen)
                if not self.zeilen:
                    continue
                if feld == "BT-20":  # Zahlungsbedingungen: der ganze Bereich ist der Wert
                    zeilen_ws = pdferkennung.woerter_im_bereich(self.zeilen, *rahmen)
                    if zeilen_ws:
                        vs.wert = " ".join(_text(z) for z in zeilen_ws)
                        vs.woerter = [w for z in zeilen_ws for w in z]
                        vs.bereich = (s, tuple(rahmen))
                        vs.status = "pruefen"
                        vs.hinweis = "Gelesen aus dem Bereich „Zahlungsbedingungen“. Passt das?"
                        return vs
                    continue
                text, hinweis = self._heuristik(feld, {})
                if text:
                    w = lesen(feld, text)
                    vs.wert = anzeigen(feld, w) if w is not None else text
                    vs.woerter = self.fundstelle(text, feld)
                    vs.status, vs.hinweis = "pruefen", hinweis
                    return vs
        finally:
            self.zeilen = alle
        vs.hinweis = "Im festgelegten Bereich nicht gefunden."
        return vs

    def _anschrift_aus_zone(self) -> dict[str, str] | None:
        """Bereich „Anschrift Empfänger“ gesetzt: Anschrift nur aus diesem Rahmen (nie kleiner, nur nach unten bis
        „PLZ Ort“ verlängert). Setzt den Block-Vorschlag. -> Teile oder None (kein Bereich)."""
        if "anschrift" not in self.zonen:
            return None
        b = self.zonen["anschrift"]
        for s in self.zone_seitenfolge("anschrift"):
            zs = [z for z in self.zeilen if z.seite == s]
            teile, zeilen_ws = pdferkennung.anschrift_im_rahmen(
                zs, b["rahmen"], f"Bereich S. {s + 1}"
            )
            if teile and "BT-53" in teile:
                self._brueche["bereich"] = pdferkennung.anschrift_brueche(zeilen_ws)
                ws = [w for z in zeilen_ws for w in z]
                r = b["rahmen"]
                rahmen = (
                    r[0],
                    r[1],
                    max(r[2], max(w.x1 for w in ws) + 2),
                    max(r[3], max(w.bottom for w in ws) + 2),
                )
                self._name_zeilen = []
                self._block_vorschlag = (s, tuple(round(x, 1) for x in rahmen), teile)
                return teile
        self._block_vorschlag = None
        self._brueche["bereich"] = {}
        return {}

    def zone_setzen(
        self,
        name: str,
        seite: int,
        rahmen: tuple[float, float, float, float],
        seiten: str | None = None,
        neu_lesen: bool = True,
    ) -> list[str]:
        """Bereich gezogen (oder Vorschlag übernommen): Rahmen merken und die Felder darin neu lesen – ein neuer
        Rahmen ersetzt den alten. -> Felder, deren Vorschlag sich geändert hat."""
        x0, top, x1, bottom = rahmen
        rahmen = (min(x0, x1), min(top, bottom), max(x0, x1), max(top, bottom))
        alt = self.zonen.get(name, {})
        self.zonen[name] = {
            "rahmen": [round(v, 1) for v in rahmen],
            "seiten": seiten or alt.get("seiten") or "alle",
        }
        self.zonen_seite[name] = seite
        log.info(
            "Bereich „%s“ gesetzt (S. %d, Gilt auf: %s)",
            pdferkennung.BEREICH_NAMEN[name],
            seite + 1,
            self.zonen[name]["seiten"],
        )
        return self._zone_neu_lesen(name) if neu_lesen else []

    def zone_seiten_setzen(self, name: str, seiten: str) -> list[str]:
        if name not in self.zonen or seiten not in pdferkennung.BEREICH_SEITEN:
            return []
        self.zonen[name]["seiten"] = seiten
        log.info("Bereich „%s“: Gilt auf %s", pdferkennung.BEREICH_NAMEN[name], seiten)
        return self._zone_neu_lesen(name, rahmen_neu=False)

    def zone_entfernen(self, name: str) -> list[str]:
        if self.zonen.pop(name, None) is None:
            return []
        self.zonen_seite.pop(name, None)
        log.info("Bereich „%s“ entfernt", pdferkennung.BEREICH_NAMEN[name])
        if name == "tabelle":
            return []
        alt = {f: (vs.wert, vs.status) for f, vs in self.werte.items()}
        if name == "anschrift":
            self.anschrift_block = None
        self.werte = self.vorschlagen()
        return [f for f, vs in self.werte.items() if (vs.wert, vs.status) != alt[f]]

    def _zone_neu_lesen(self, name: str, rahmen_neu: bool = True) -> list[str]:
        b = self.zonen[name]
        seite = self.zonen_seite.get(name, self.zone_seitenfolge(name)[0] if self.zeilen else 0)
        alt = {f: (vs.wert, vs.status) for f, vs in self.werte.items()}
        if name == "tabelle":
            if rahmen_neu:
                self.rahmen_setzen(seite, *b["rahmen"])
            return []
        if name == "anschrift":
            self.anschrift_block = None
            teile = self._anschrift_aus_zone() or {}
            if self._block_vorschlag:
                s, rahmen, _t = self._block_vorschlag
                self.anschrift_setzen(s, rahmen)
            else:
                for f in KAEUFER_FELDER_ANLERNEN:
                    vs = self.werte[f]
                    vs.wert, vs.status, vs.woerter, vs.beschriftung, vs.bereich = (
                        "",
                        "fehlt",
                        [],
                        [],
                        None,
                    )
                    vs.hinweis = (
                        "Im Bereich „Anschrift Empfänger“ keine Zeile „PLZ Ort“ gefunden."
                        if f in ("BT-53", "BT-52")
                        else ""
                    )
            del teile
        else:
            for f in ZONEN_FELDER[name]:
                self.werte[f] = self._vorschlag_in_zone(f)
            if name == "zahlung" and self.werte["BT-20"].bereich:
                s, r = self.werte["BT-20"].bereich
                self.bereich_setzen("BT-20", s, *r)
            if name == "summen":
                self.summen_gegenprobe()
        return [f for f, vs in self.werte.items() if (vs.wert, vs.status) != alt[f]]

    def zone_vorschlag(self, name: str) -> tuple[int, tuple[float, float, float, float]] | None:
        """Rahmen, den die automatische Erkennung für diesen Bereich vorschlägt (um die erkannten Werte samt
        Beschriftung, 4 pt Luft) -> (Seite, Rahmen) oder None."""
        if name == "tabelle":
            t = self.tabelle
            return None if t.leer() else (t.seite, (t.x0, t.top, t.x1, t.bottom))
        if name == "anschrift":
            block = self.anschrift_block or self._block_vorschlag
            if block:
                return block[0], tuple(block[1])
        if name == "zahlung":
            vs = self.werte["BT-20"]
            if vs.bereich:
                return vs.bereich[0], tuple(vs.bereich[1])
            if self._bt20_rahmen:
                return self._bt20_rahmen[0], tuple(self._bt20_rahmen[1])
        ws: list[Wort] = []
        for f in ZONEN_FELDER[name]:
            vs = self.werte[f]
            ws += list(vs.beschriftung) + list(vs.woerter)
            if name in ("kopf", "summen") and vs.woerter:  # Beschriftung links daneben gehört dazu
                w0 = vs.woerter[0]
                for z in self.zeilen:
                    if z.seite == w0.seite and any(w is w0 for w in z.woerter):
                        ws += [w for w in z.woerter if w.x1 <= w0.x0 and w.x0 >= w0.x0 - 250]
        if not ws:
            return None
        seite = max(
            {w.seite for w in ws},
            key=lambda s: (sum(w.seite == s for w in ws), -s if name != "summen" else s),
        )
        ws = [w for w in ws if w.seite == seite]
        return seite, (
            min(w.x0 for w in ws) - 4,
            min(w.top for w in ws) - 4,
            max(w.x1 for w in ws) + 4,
            max(max(w.bottom, w.top + 9) for w in ws) + 4,
        )

    def zonen_geaendert(self) -> list[str]:
        """Bereiche, die von der gespeicherten Vorlage abweichen (zählt beim Speichern als Korrektur)."""
        if self.vorlage is None:
            return []
        return pdferkennung.bereiche_unterschied(self.vorlage.get("bereiche"), self.zonen)

    def _beschriftet(self, feld: str) -> str:
        """Wert hinter oder unter einer Beschriftung („Rechnungsdatum: 05.10.2026“ / Kopfzeile mit Werten darunter)."""
        rx = _BESCHRIFTUNG[feld]
        typ = FELDER[feld][1]
        for zi, z in enumerate(self.zeilen):
            for si, seg in enumerate(z.abschnitte):
                if not re.search(rx, norm(_text(seg))):
                    continue
                if feld in pdferkennung.OPTIONALE_NUMMERN:  # nur rechts daneben, sonst leer lassen
                    ws = self._nummer_neben(zi, si, 1)
                    if ws:
                        return ws[0].t
                    continue
                for ws in self._nachbarn(zi, si, 1):
                    ws = list(ws)
                    while ws and not re.search(r"\w", ws[0].t):
                        ws = ws[1:]
                    if not ws:
                        continue
                    t = _text(ws)
                    if typ == "text":
                        w = next(
                            (w.t for w in ws if re.search(r"\d", w.t) and not w.t.endswith(":")),
                            None,
                        )
                        if w and ws[0].t == w:
                            return w
                    elif lesen(feld, t) is not None and not re.search(rx, norm(t)):
                        return t
        return ""

    def _nummer_neben(self, zi: int, si: int, ab: int) -> list[Wort]:
        """Optionales Nummernfeld (Bestell-, Kundennummer): Wert nur rechts neben der Beschriftung in derselben
        Zeile und in Nummernform – nicht darunter, nicht weit weg, kein Datum/Betrag."""
        z = self.zeilen[zi]
        seg = z.abschnitte[si]
        k = next((k for k, w in enumerate(seg) if k >= ab - 1 and w.t.endswith(":")), None)
        offen = k is None
        k = max(ab - 1 if k is None else k, 0)
        rest = seg[k + 1 :]
        if any(w.t.endswith(":") and re.search(r"\w", w.t) for w in rest[:1]):
            return []  # gleich die nächste Beschriftung: Feld leer
        nxt = _mit_doppelpunkt(z.abschnitte, si + 1) if si + 1 < len(z.abschnitte) else None
        if nxt and _fremde_beschriftung(nxt):
            nxt = None
        return pdferkennung.nummer_rechts(rest, nxt, seg[k].x1 if seg else 0, label_offen=offen)

    def _nachbarn(self, zi: int, si: int, ab: int) -> list[list[Wort]]:
        """Wo steht der Wert zu einer Beschriftung (Abschnitt ``si`` der Zeile ``zi``, Beschriftung beginnt bei
        Wort ``ab - 1``)? Reihenfolge: Rest des Abschnitts, nächster Abschnitt rechts, direkt darunter."""
        z = self.zeilen[zi]
        seg = z.abschnitte[si]
        rest = seg[ab:]
        j = next(
            (j for j, w in enumerate(rest) if re.search(r"\w", w.t) and w.t.endswith(":")), None
        )
        if j is not None:  # „Versanddatum : Datum: 05.01.2025“: nicht den Wert von „Datum:“
            rest = rest[:j]
        kand = [rest[i:] for i in range(len(rest))]
        if si + 1 < len(z.abschnitte):
            kand.append(_mit_doppelpunkt(z.abschnitte, si + 1))
        for zj, s2 in pdferkennung.abschnitte_darunter(
            self.zeilen,
            zi,
            seg[0].x0,
            seg[-1].x1,
            pdferkennung.DARUNTER_ASSISTENT * pdferkennung._hoehe(seg[0]),
        ):
            ab = self.zeilen[zj].abschnitte
            kand.append(_mit_doppelpunkt(ab, next(i for i, a in enumerate(ab) if a is s2)))
        return [k for k in kand if not _fremde_beschriftung(k)]

    def neben_leer(self, woerter: list[Wort]) -> bool:
        """Steht neben/unter der angeklickten Beschriftung gar nichts (leeres Feld im Druck)?"""
        for zi, z in enumerate(self.zeilen):
            for si, seg in enumerate(z.abschnitte):
                i = next((i for i, w in enumerate(seg) if woerter and w is woerter[0]), None)
                if i is not None:
                    return not any(
                        re.search(r"\w", w.t)
                        for k in self._nachbarn(zi, si, i + len(woerter))
                        for w in k
                    )
        return False

    def wert_neben(self, feld: str, woerter: list[Wort]) -> tuple[str, list[Wort]] | None:
        """Angeklickt wurde eine Beschriftung („Versanddatum“) statt des Werts: lesbaren Wert rechts daneben
        (gleiche Zeile) oder direkt darunter suchen. -> (Text, Wörter des Werts) oder None."""
        if not woerter:
            return None
        for zi, z in enumerate(self.zeilen):
            for si, seg in enumerate(z.abschnitte):
                i = next((i for i, w in enumerate(seg) if w is woerter[0]), None)
                if i is None:
                    continue
                if feld in pdferkennung.OPTIONALE_NUMMERN:
                    ws = self._nummer_neben(zi, si, i + len(woerter))
                    return (_text(ws), ws) if ws else None
                for ws in self._nachbarn(zi, si, i + len(woerter)):
                    ws = list(ws)
                    while ws and not re.search(r"\w", ws[0].t):
                        ws = ws[1:]
                    if not ws:
                        continue
                    if (
                        FELDER[feld][1] == "text"
                    ):  # Text: ganzer Abschnitt, aber keine weitere Beschriftung
                        t = _text(ws)
                        if ist_beschriftung(feld, t) or (
                            feld in _NUMMERNFELDER and not re.search(r"\d", t)
                        ):
                            continue
                        return t, ws
                    for n in range(
                        min(len(ws), 5), 0, -1
                    ):  # längste lesbare Wortfolge (Zeitraum vor Datum)
                        t = _text(ws[:n])
                        if lesen(feld, t) is not None:
                            return t, ws[:n]
                return None
        return None

    def _heuristik(self, feld: str, kaeufer: dict[str, str]) -> tuple[str, str]:
        if feld in kaeufer:
            return kaeufer[feld], ""
        if feld in _BESCHRIFTUNG:
            t = self._beschriftet(feld)
            if t:
                zr = feld == "leistung" and isinstance(lesen(feld, t), tuple)
                return t, (
                    "Gelesen als Zeitraum. Stimmt das?"
                    if zr and not re.search(r"[–-]|bis", t)
                    else ""
                )
        if feld == "leistung":
            for f in ("BT-72", "BG-14"):
                t = pdferkennung._druckwert_suchen(f, self.zeilen, None)
                if t != pdferkennung.NICHT_GEFUNDEN:
                    t = t.replace("\u00a0", " ").replace("–", " – ")
                    return t, ("Gelesen als Zeitraum. Stimmt das?" if f == "BG-14" else "")
            return "", ""
        if feld == "BT-119":
            saetze = []
            for z in self.zeilen:
                if re.search(r"ust|mwst|vat|umsatzsteuer|steuer", norm(z.text)):
                    saetze += steuersaetze_im_text(z.text)
            saetze = list(dict.fromkeys(saetze))
            if len(saetze) > 1:
                return (
                    f"{saetze[0]} %",
                    "Mehrere Steuersätze gefunden. Ordne in den Positionen die Spalte USt-Satz zu.",
                )
            return (f"{saetze[0]} %", "") if saetze else ("", "")
        if feld in STEUERFELDER and feld not in _BESCHRIFTUNG or feld == "BT-111":
            return self._steuer_heuristik(feld)
        if feld == "BT-20":
            self._bt20_rahmen = None
            baustein = pdferkennung.zahlungsbaustein(self.zeilen)
            if baustein is None:
                return "", ""
            seite, ws = baustein
            if len(pdferkennung._zeilen_von(ws)) > 1:
                self._bt20_rahmen = (seite, pdferkennung.rahmen_um(ws))
            return " ".join(_text(g) for g in pdferkennung._zeilen_von(ws)), (
                "Empfohlen: Zahlungsbedingung aus dem Druck. Steht sie über mehrere Zeilen, den ganzen "
                "Absatz einrahmen."
                if self._bt20_rahmen is None
                else "Empfohlen: Zahlungsbedingung über mehrere Zeilen. Passt der Rahmen?"
            )
        if feld in pdferkennung.OPTIONALE_NUMMERN:
            t = pdferkennung._druckwert_suchen(
                feld, self.zeilen, None
            )  # nur gleiche Zeile, Nummernform
            return ("", "") if t == pdferkennung.NICHT_GEFUNDEN else (t, "")
        if feld in ("BT-1", "BT-2", "BT-109", "BT-110", "BT-112"):
            t = pdferkennung._druckwert_suchen(feld, self.zeilen, None)
            if t == pdferkennung.NICHT_GEFUNDEN:
                return "", ""
            t = t.replace("\u00a0", " ")
            if FELDER[feld][1] == "betrag":
                try:
                    return _de(Decimal(t)), ""
                except InvalidOperation:
                    return t, ""
            if FELDER[feld][1] == "datum":
                d = daten(t) or [None]
                if d[0] is None:
                    try:
                        d = [date.fromisoformat(t)]
                    except ValueError:
                        return t, ""
                return anzeigen(feld, d[0]), ""
            return t, ""
        return "", ""

    def _steuer_heuristik(self, feld: str) -> tuple[str, str]:
        """Steuerhinweis, Währung, Kurs und USt in EUR aus dem Druck vorschlagen (ab 0.9.7)."""
        kopf: dict = {}
        pdferkennung.steuer_kopf_ergaenzen(kopf, self.zeilen, None)
        w = kopf.get(feld, (None,))[0]
        if w is None or w == "":
            return "", ""
        if feld == "steuerhinweis":
            return str(w), "Steuerhinweis im Druck gefunden. Steuerfall unten bei den Positionen prüfen."
        if feld == "BT-5":
            return str(w), "Fremdwährung im Druck gefunden – Kurs oder USt in EUR angeben."
        if isinstance(w, Decimal):
            return _de(w), ""
        return str(w), ""

    # -- Steuerfall (ab 0.9.7) ---------------------------------------------------------------------
    def steuerfall_vorschlag(self) -> str:
        """Steuerfall aus dem Hinweistext (Feld oder Druck), Kleinunternehmer-Schalter des Absenders, sonst S."""
        f = steuerfaelle.erkennen(self.werte["steuerhinweis"].wert if "steuerhinweis" in self.werte else "")
        if f:
            return f
        if getattr(self.absender, "kleinunternehmer", False):
            return "KU"
        return "S"

    def steuerfall_setzen(self, fall: str) -> None:
        """Auswahl im Assistenten ("" = Vorschlag). Kleinunternehmer ist eine Eigenschaft des Absenders: die Wahl
        setzt dessen Schalter (wird mit der Vorlage im Profil gespeichert)."""
        self.steuerfall = fall if fall in STEUERFAELLE else ""
        if fall == "KU":
            self.absender.kleinunternehmer = True
        elif fall and self.absender.kleinunternehmer:
            self.absender.kleinunternehmer = False

    def steuerfall_wirksam(self) -> str:
        return getattr(self, "steuerfall", "") or self.steuerfall_vorschlag()

    def _steuerfall_aus_vorlage(self) -> str:
        st = ((self.vorlage or {}).get("positionen") or {}).get("steuer_fest") or {}
        f = str(st.get("fall") or "")
        return f if f in steuerfaelle.FAELLE else ""

    def steuerfall_text(self) -> str:
        """BT-120 für den Steuerfall: Hinweistext aus dem Druck, sonst der Standardtext."""
        f = self.steuerfall_wirksam()
        t = self.werte["steuerhinweis"].wert if "steuerhinweis" in self.werte else ""
        return t if t and steuerfaelle.erkennen(t) == f else steuerfaelle.standardtext(f)

    def _seite0(self) -> tuple[float, float]:
        """Breite und Höhe der ersten Seite in pt (A4, wenn unbekannt)."""
        s = self.seiten[0] if getattr(self, "seiten", None) else None
        return (s.breite, s.hoehe) if s and s.breite and s.hoehe else (A4_BREITE, A4_HOEHE)

    def _anschrift_bloecke(self):
        """Mögliche Anschriftfelder links oben: (Treffer „PLZ Ort“, Abschnitt, [(Zeile, Abschnitt) darüber])."""
        breite, hoehe = self._seite0()
        zs = [z for z in self.zeilen if z.seite == 0]
        for zi, z in enumerate(zs):
            if z.top > ANSCHRIFT_UNTEN * hoehe:
                break
            for seg in z.abschnitte:
                if seg[0].x0 > ANSCHRIFT_RECHTS * breite:
                    continue
                if pdferkennung._NUR_PLZ.match(
                    _text(seg)
                ):  # „12345      Musterstadt“: Ort mit großem Abstand
                    nachbarn = [
                        s
                        for z2 in zs[max(0, zi - 1) : zi + 2]
                        for s in z2.abschnitte
                        if s[0].x0 > seg[-1].x1
                        and pdferkennung.ort_neben_plz(seg[-1].x1, s[0].x0)
                        and pdferkennung.auf_linie(
                            pdferkennung._mitte(s[0]),
                            pdferkennung._mitte(seg[0]),
                            pdferkennung._hoehe(seg[0]),
                        )
                    ]
                    if nachbarn:
                        seg = seg + min(nachbarn, key=lambda s: s[0].x0)
                m = PLZ_ORT.match(_text(seg))
                if not m:
                    continue
                darueber = []
                for z2 in reversed(zs[max(0, zi - 10) : zi]):
                    if z.top - z2.top > ANSCHRIFT_HOEHE * pdferkennung._hoehe(
                        seg[0]
                    ):  # Namen, Zusatz, Straße
                        break
                    teil = [
                        s for s in z2.abschnitte if abs(s[0].x0 - seg[0].x0) <= ANSCHRIFT_BUENDIG
                    ]
                    if teil and not re.search(r"[·|•*]|^[-=_. ]+$|:$", _text(teil[0])):
                        darueber.insert(0, (z2, teil[0]))
                    elif teil:
                        break  # Absenderzeile über dem Anschriftfeld
                yield m, (z, seg), darueber

    def anschriftfeld(self) -> list[tuple[Zeile, list[Wort]]]:
        """Das Anschriftfeld des Käufers (Fensterbereich, ab etwa 100 pt von oben), ohne den Absender zu kennen.

        Gehört nie zum Absender – auch wenn der Briefkopf nur als Bild im Druck steht."""
        for _, plz, darueber in self._anschrift_bloecke():
            if plz[0].top >= ANSCHRIFT_OBEN * self._seite0()[1] and any(
                _STRASSE.match(_text(sg)) for _, sg in darueber
            ):
                return darueber + [plz]
        return []

    def _ohne_anschriftfeld(self) -> list[Zeile]:
        weg = {id(sg) for _, sg in self.anschriftfeld()}
        if not weg:
            return self.zeilen
        out = []
        for z in self.zeilen:
            ab = [sg for sg in z.abschnitte if id(sg) not in weg]
            if len(ab) != len(z.abschnitte):
                z = Zeile(z.seite, z.top, [w for sg in ab for w in sg], ab)
            out.append(z)
        return out

    def _kaeufer_woerter(self, feld: str, text: str) -> list[Wort]:
        if feld == "BT-44" and self._name_zeilen and text == _text(self._name_zeilen):
            return list(self._name_zeilen)
        return []

    def _block_rahmen(self, sgs: list[list[Wort]]) -> tuple[float, float, float, float]:
        """Rahmen um die Anschriftzeilen, nach rechts bis kurz vor den nächsten Text (längere Namen passen)."""
        ws = [w for sg in sgs for w in sg]
        x0, top, x1, bottom = pdferkennung.rahmen_um(ws)
        drin = {id(w) for w in ws}
        rechts = [
            w.x0
            for z in self.zeilen
            if z.seite == ws[0].seite
            for w in z.woerter
            if id(w) not in drin and w.x0 > x1 and w.bottom > top and w.top < bottom
        ]
        x1 = max(x1, min(rechts + [x0 + 250]) - 4)
        # nach oben Platz für bis zu zwei weitere Namenszeilen, wenn dort nichts steht
        oben = [
            w.bottom
            for z in self.zeilen
            if z.seite == ws[0].seite
            for w in z.woerter
            if id(w) not in drin and w.bottom <= top + 2 and w.x1 > x0 and w.x0 < x1
        ]
        return x0, max(top - 26, max(oben + [top - 26]) + 1), x1, bottom

    def _kaeufer_suchen(self) -> dict[str, str]:
        """Anschriftfeld links oben von unten nach oben lesen (``pdferkennung.anschrift_zerlegen``): unterste
        Zeile „PLZ Ort“ (nicht die des Absenders), darüber Straße, Zusatz und Name (1–3 Zeilen)."""
        self._name_zeilen, self._block_vorschlag = [], None
        self._brueche["kalt"] = {}
        bloecke = list(self._anschrift_bloecke())
        for n, (m, plz, darueber) in enumerate(bloecke):
            if any(any(sg is plz[1] for _, sg in d) for _, _, d in bloecke[n + 1 :]):
                continue  # tiefere PLZ-Zeile im selben Block zählt
            sgs = [sg for _, sg in darueber] + [plz[1]]
            teile, rollen = pdferkennung.anschrift_zerlegen([_text(sg) for sg in sgs])
            strasse = teile.get("BT-50", "")
            if strasse and norm(strasse) == norm(self.absender.strasse or "-"):
                continue  # Briefkopf des Absenders
            # Straße auch ohne Hausnummer (Konzept Schritt 2), aber nur mit Namen darüber
            if not (_STRASSE.match(strasse) or pdferkennung._POSTFACH.match(strasse)) and not (
                teile.get("BT-44") and pdferkennung.strassenzeile(strasse)
            ):
                return {"BT-53": m.group(1), "BT-52": m.group(2).strip()}
            namen = [sg for sg, r in zip(sgs, rollen) if r == "name"]
            if len(namen) > 1:
                self._name_zeilen = [w for sg in namen for w in sg]
            genutzt = [sg for sg, r in zip(sgs, rollen) if r != "weg"]
            self._brueche["kalt"] = pdferkennung.anschrift_brueche(sgs)
            if teile.get("BT-44"):  # Vorlage liest die Anschrift dann auch von unten nach oben
                self._block_vorschlag = (
                    plz[0].seite,
                    tuple(round(v, 1) for v in self._block_rahmen(genutzt)),
                    teile,
                )
            return {f: teile[f] for f in KAEUFER_FELDER_ANLERNEN if teile.get(f)}
        return {}

    def kaeufer_neu_vorschlagen(self) -> list[str]:
        """Absender geändert: Käufer-Vorschläge neu ermitteln (was der Nutzer bestätigt hat, bleibt). -> geänderte Felder."""
        kaeufer = self._kaeufer_suchen()
        neu = []
        for feld in KAEUFER_FELDER_ANLERNEN:
            vs = self.werte[feld]
            if vs.status == "erkannt":
                continue
            text = kaeufer.get(feld, "")
            if text == (vs.wert or ""):
                continue
            vs.wert = text
            vs.woerter = (
                (self._kaeufer_woerter(feld, text) or self.fundstelle(text, feld)) if text else []
            )
            vs.status = "pruefen" if text else "fehlt"
            vs.hinweis = ""
            neu.append(feld)
        teile = (self._block_vorschlag or (None, None, None))[2] or {}
        for feld in KAEUFER_NEBENFELDER:
            vs = self.werte.get(feld)
            if vs is None or vs.status == "erkannt":
                continue
            text = teile.get(feld, "")
            if text == (vs.wert or ""):
                continue
            vs.wert = text
            vs.woerter = self.fundstelle(text, feld) if text else []
            vs.status = "pruefen" if text else "fehlt"
            vs.hinweis = ""
            neu.append(feld)
        if not self.vorlage and "anschrift" not in self.zonen:
            self.anschrift_hinweise = dict(self._brueche["kalt"]) if kaeufer else {}
            for f, text in self.anschrift_hinweise.items():
                if self.werte[f].status == "pruefen":
                    self.werte[f].hinweis = text
        return neu

    # -- Eingaben ---------------------------------------------------------------------------------
    def setzen(self, feld: str, text: str, woerter: list[Wort] | None = None) -> Vorschlag:
        """Klick oder Eingabe übernehmen. Lesbarer Wert = erkannt (der Nutzer hat ihn selbst bestätigt)."""
        vs = self.werte[feld]
        text = " ".join(str(text or "").split())
        w = lesen(feld, text)
        vs.hinweis = ""
        if (
            woerter is None or woerter is not vs.woerter
        ):  # neue Eingabe; „Passt“ behält die Beschriftung
            vs.beschriftung = []
            vs.bereich = None
            vs.geklickt = bool(woerter)
        if woerter:
            # „Kunden-Nr.: 4711“ / „Datum: 05.10.2026“ in einem Abschnitt angeklickt: Beschriftung bis zum
            # Doppelpunkt abtrennen
            i = max((i for i, x in enumerate(woerter[:-1]) if x.t.endswith(":")), default=None)
            if i is None and re.search(r"\d", woerter[-1].t):
                # ohne Doppelpunkt („Rechnung Nr. 2026-04711“): Beschriftung vorn bis vor den Wert
                i = max(
                    (
                        i
                        for i in range(len(woerter) - 1)
                        if ist_beschriftung(feld, _text(woerter[: i + 1]))
                    ),
                    default=None,
                )
            if i is not None:
                vs.beschriftung = list(woerter[: i + 1])
                woerter = list(woerter[i + 1 :])
                text = _text(woerter)
                w = lesen(feld, text)
        if woerter and (
            (w is None and FELDER[feld][1] != "text")
            or (FELDER[feld][1] == "text" and ist_beschriftung(feld, text))
        ):
            neben = self.wert_neben(feld, woerter)
            if neben:
                vs.beschriftung = [x for x in woerter if x not in neben[1]]
                text, woerter = neben
                w = lesen(feld, text)
            elif ist_beschriftung(feld, text) and self.neben_leer(woerter):
                # „Bestellnummer:“ / „Versanddatum :“ ohne Wert im Druck: die Beschriftung ist nicht der Wert
                name = text.rstrip(" :")
                vs.wert, vs.status, vs.woerter, vs.beschriftung = "", "fehlt", [], []
                vs.hinweis = f"Neben „{name}“ steht in dieser PDF kein Wert. " + {
                    "datum": "Bitte das Datum eintippen.",
                    "leistung": "Bitte Datum oder Zeitraum eintippen (z. B. 01.10.2026 – 31.10.2026).",
                }.get(FELDER[feld][1], "Bitte eintippen oder leer lassen.")
                return vs
        if not text:
            vs.wert, vs.status, vs.woerter = "", "fehlt", []
            return vs
        if w is None:
            vs.wert, vs.status = text, "pruefen"
            vs.hinweis = {
                "datum": "Kein Datum erkannt (z. B. 05.10.2026).",
                "leistung": "Kein Datum oder Zeitraum erkannt (z. B. 01.10.2026 – 31.10.2026).",
                "betrag": "Kein Betrag erkannt (z. B. 1.075,28).",
                "satz": "Kein Steuersatz erkannt (z. B. 19 %).",
            }.get(FELDER[feld][1], "")
        else:
            vs.wert, vs.status = anzeigen(feld, w), "erkannt"
            if FELDER[feld][1] == "satz" and w == 0:
                vs.status = "pruefen"
                vs.hinweis = "Steuerfreie Rechnungen kommen erst in Version 2.0."
        vs.woerter = woerter if woerter else self.fundstelle(text, feld)
        if not vs.woerter and vs.status == "erkannt":
            vs.hinweis = "Nicht in der PDF gefunden. Der Wert gilt nur für diese Rechnung."
        elif not vs.geklickt and vs.status == "erkannt" and self._ausserhalb_zone(feld, vs.woerter):
            # eingetippt, steht aber nicht im Bereich des Felds: seitenweit lernen nur nach Klick oder Rahmen
            vs.hinweis = (
                "Wert in der PDF anklicken oder Rahmen ziehen, damit die Vorlage ihn sich merkt."
            )
        return vs

    def _ausserhalb_zone(self, feld: str, woerter: list[Wort]) -> bool:
        """Hat das Feld einen Bereich und liegt die Fundstelle ganz außerhalb davon?"""
        name = self._zone_von(feld)
        if not name or not woerter:
            return False
        x0, top, x1, bottom = self.zonen[name]["rahmen"]
        return not any(
            x0 - 2 <= w.x0 and w.x1 <= x1 + 2 and top - 2 <= w.top <= bottom + 2 for w in woerter
        )

    def bestaetigen(self, feld: str) -> Vorschlag:
        """„Passt“: Vorschlag ohne Änderung übernehmen."""
        vs = self.werte[feld]
        if vs.bereich:
            return self.bereich_setzen(feld, vs.bereich[0], *vs.bereich[1])
        return self.setzen(feld, vs.wert, vs.woerter)

    def fehlende(self) -> list[str]:
        """Pflichtfelder, die noch nicht bestätigt sind (Status ≠ erkannt). Ab 0.9.7: ohne Umsatzsteuer
        (Reverse Charge, igL, Ausfuhr, nicht steuerbar, § 19 UStG) ist der Steuersatz keine Pflicht (0 %)."""
        frei = ("BT-119",) if self.steuerfall_wirksam() != "S" else ()
        return [f for f in PFLICHT if f not in frei and self.werte[f].status != "erkannt"]

    def wert(self, feld: str):
        vs = self.werte[feld]
        return lesen(feld, vs.wert) if vs.wert else None

    # -- Positionstabelle -------------------------------------------------------------------------
    def tabelle_vorschlagen(self) -> Tabelle:
        """Aus der Vorlage (falls vorhanden), sonst über die Kopfzeile mit Spaltenüberschriften."""
        pv = (self.vorlage or {}).get("positionen")
        if pv:
            t = self._tabelle_aus_pv(pv)
            if t:
                return t
        for zi, z in enumerate(self.zeilen):
            treffer = {_spalte_fuer(_text(seg)) for seg in z.abschnitte} - {None}
            if (
                len(treffer) >= 3
                and {"BT-153", "gesamt"} <= treffer | {"BT-153"}
                and "gesamt" in treffer
            ):
                bottom = self._tabellenende(zi)
                # Wörter, die erst rechts neben der Kopfzeile beginnen, gehören nicht zur Tabelle (Seitenleiste
                # mit Bankdaten neben den Positionen)
                kopf_x1 = max(w.x1 for w in z.woerter)
                rows = [
                    w
                    for z2 in self.zeilen
                    if z2.seite == z.seite and z.top <= z2.top <= bottom
                    for w in z2.woerter
                    if not (pdferkennung.TRENNLINIE.match(w.t) and len(w.t) <= 3)
                    and w.x0 <= kopf_x1 + 12
                ]  # Falz-/Lochmarken
                x0 = min(w.x0 for w in rows) - 4
                x1 = max(w.x1 for w in rows) + 4
                t = Tabelle(seite=z.seite, x0=x0, top=z.top - 3, x1=x1, bottom=bottom)
                self.spalten_erkennen(t)
                return t
        return Tabelle()

    def _tabellenende(self, kopf_i: int) -> float:
        kopf = self.zeilen[kopf_i]
        x1 = max(w.x1 for w in kopf.woerter)
        letzte = kopf.top
        stopp = None  # erste Zeile, die nicht mehr dazugehört (exklusive Grenze)
        breite = x1 - min(w.x0 for w in kopf.woerter)
        for z in self.zeilen[kopf_i + 1 :]:
            if z.seite != kopf.seite:
                break
            if (
                (
                    pdferkennung.summentext(z.text)
                    or "übertrag" in norm(z.text)
                    or pdferkennung.ist_uebertrag(z)
                )
                and not betraege(_text(z.woerter[:1]))
                and sum(1 for w in z.woerter if pdferkennung.zahlen(w.t)) < 3
            ):
                stopp = z.top  # Summe direkt unter der letzten Position (Abstand ≤ 12 pt);
                break  # mit Menge, Preis und Betrag bleibt sie Position (Mindestauftrag)
            # vor der ersten Position darf mehr Platz sein (Trennlinie + Leerzeilen unter der Kopfzeile)
            if z.top - letzte > (40 if letzte > kopf.top else 64):
                break
            if pdferkennung.ist_trennlinie(z):
                if (
                    letzte > kopf.top
                    and max(w.x1 for w in z.woerter) - min(w.x0 for w in z.woerter) >= breite * 0.4
                ):
                    break  # Linie unter den Positionen
                continue  # Linie unter der Kopfzeile, Falz- oder Lochmarke am Rand
            if max(w.x1 for w in z.woerter) <= x1 + 30:
                letzte = z.top
        return letzte + 12 if stopp is None else min(letzte + 12, stopp - 0.5)

    def _tabelle_aus_pv(self, pv: dict) -> Tabelle | None:
        kopf = next(
            (i for i, z in enumerate(self.zeilen) if pdferkennung._passt_zeile(pv["kopf"], z)), None
        )
        if kopf is None:
            return None
        z = self.zeilen[kopf]
        sp = sorted(pv["spalten"].items(), key=lambda kv: kv[1][0])
        grenzen = [sp[0][1][0] - 2] + [(a[1][1] + b[1][0]) / 2 for a, b in zip(sp, sp[1:])]
        pe = "spalte" if "BT-149" in pv["spalten"] else str(pv.get("preiseinheit_fest", "1"))
        t = Tabelle(
            seite=z.seite,
            x0=min(grenzen[0], min(w.x0 for w in z.woerter)) - 2,
            top=z.top - 3,
            x1=max(sp[-1][1][1], max(w.x1 for w in z.woerter)) + 4,
            bottom=self._tabellenende(kopf),
            grenzen=grenzen,
            spalten=[n for n, _ in sp],
            preiseinheit=pe,
            einheiten=dict(pv.get("einheiten") or {}),
            steuerwerte={k: steuerwert_kennung(m) for k, m in (pv.get("steuer") or {}).items()
                         if steuerwert_kennung(m)},
        )
        if pv.get("spalten_fest"):
            t.spaltenrahmen = [[n, a, b] for n, (a, b) in sp]
        return t

    def _zeilen_im_rahmen(self, t: Tabelle) -> list[Zeile]:
        return [z for z in self.zeilen if z.seite == t.seite and t.top <= z.top + 4 <= t.bottom]

    @staticmethod
    def _kopfworte(z: Zeile, t: Tabelle) -> int:
        return sum(
            1 for w in z.woerter if t.x0 - 2 <= w.x0 and w.x1 <= t.x1 + 2 and _spalte_fuer(w.t)
        )

    def _kopf_ueber(self, t: Tabelle) -> Zeile | None:
        """Erste Zeile im Rahmen ist keine Kopfzeile, aber knapp darüber steht eine -> diese Kopfzeile."""
        zs = self._zeilen_im_rahmen(t)
        if zs and self._kopfworte(zs[0], t) >= 2:
            return None
        oben = [z for z in self.zeilen if z.seite == t.seite and t.top - 50 <= z.top + 4 < t.top]
        for z in reversed(oben):
            if self._kopfworte(z, t) >= 2:
                return z
        return None

    def _tabellenzeilen(self, t: Tabelle) -> list[Zeile]:
        """Kopfzeile und Zeilen bis vor die erste Summen-/Übertragszeile im Rahmen, ohne Trennlinien –
        ein großzügig gezogener Rahmen mit Summenblock verschiebt so keine Spaltengrenzen."""
        zs = self._zeilen_im_rahmen(t)
        if not zs:
            return zs
        ende = self._tabellenende(self.zeilen.index(zs[0]))
        return zs[:1] + [z for z in zs[1:] if z.top < ende and not pdferkennung.ist_trennlinie(z)]

    def spalten_erkennen(self, t: Tabelle) -> None:
        """Spaltengrenzen aus der Kopfzeile im Rahmen; Lücken, die in allen Zeilen frei sind, gehen vor."""
        zs = self._tabellenzeilen(t)
        if not zs:
            t.grenzen, t.spalten = [], []
            return
        kopf = zs[0]
        kopfsegs = []
        for seg in kopf.abschnitte:
            ws = [w for w in seg if t.x0 <= (w.x0 + w.x1) / 2 <= t.x1]
            if ws:
                kopfsegs.append(ws)
        # Abschnitte mit mehreren Überschriften („Menge ME“) trennen, wenn beide Wörter Spalten sind
        teile: list[list[Wort]] = []
        for seg in kopfsegs:
            akt: list[Wort] = []
            for w in seg:
                if (
                    akt
                    and w.t not in ("€", "EUR", "(€)")
                    and _spalte_fuer(_text(akt))
                    and _spalte_fuer(w.t)
                    and w.x0 - akt[-1].x1 > 3
                ):
                    teile.append(akt)
                    akt = []
                akt.append(w)
            teile.append(akt)
        daten_w = [
            w
            for z in zs[1:]
            for w in z.woerter
            if t.x0 <= w.x0 and w.x1 <= t.x1 + 2 and not pdferkennung.TRENNLINIE.match(w.t)
        ]
        frei = _freie_luecken(
            daten_w + [w for w in kopf.woerter if t.x0 <= w.x0 and w.x1 <= t.x1 + 2], t.x0, t.x1
        )
        mitten = [(w.x0 + w.x1) / 2 for w in daten_w]
        grenzen = [t.x0]
        for a, b in zip(teile, teile[1:]):
            links, rechts = (
                a[0].x0 + 1,
                b[-1].x1,
            )  # Lücke zwischen Beginn der linken und Ende der rechten Überschrift
            kand = []
            for f0, f1 in frei:
                f0, f1 = max(f0, links), min(f1, rechts)
                if f1 - f0 < 2.5:
                    continue
                # links und rechts der Lücke müssen Werte stehen, sonst bliebe eine Spalte leer
                if mitten and not (
                    any(grenzen[-1] < m < f0 for m in mitten)
                    and any(f1 < m < rechts + 30 for m in mitten)
                ):
                    continue
                ueberlapp = max(0.0, min(f1, b[0].x0) - max(f0, a[-1].x1))
                kand.append((ueberlapp, f1 - f0, f0, f1))
            if kand:
                _, _, f0, f1 = max(kand)
                grenzen.append(round((f0 + f1) / 2, 1))
            else:
                grenzen.append(round((a[-1].x1 + b[0].x0) / 2, 1))
        t.grenzen = grenzen
        t.spalten = [_spalte_fuer(_text(s)) or "ignorieren" for s in teile]
        if "BT-153" not in t.spalten and "ignorieren" in t.spalten:
            t.spalten[t.spalten.index("ignorieren")] = "BT-153"
        t.preiseinheit = "spalte" if "BT-149" in t.spalten else t.preiseinheit

    def spalten_titel(self) -> list[str]:
        """Überschrift je Spalte (Text der Kopfzeile zwischen den Grenzen), für die Auswahlfelder."""
        t = self.tabelle
        zs = self._zeilen_im_rahmen(t)
        if not zs or not t.grenzen:
            return []
        g = list(t.grenzen) + [t.x1 + 30]
        out = []
        for i in range(len(t.spalten)):
            ws = [w for w in zs[0].woerter if g[i] <= (w.x0 + w.x1) / 2 < g[i + 1]]
            out.append(_text(ws) or f"{i + 1}")
        return out

    def grenze_setzen(self, i: int, x: float) -> Tabelle:
        """Nutzer hat die Spaltenlinie ``i`` (1 … n-1) verschoben: Lage begrenzen, Zuordnung der beiden
        Nachbarspalten aus den Überschriften neu bestimmen. Manuell Gewähltes bleibt, wenn nichts erkannt wird."""
        t = self.tabelle
        if t.leer() or not 1 <= i < len(t.grenzen):
            return t
        rechts = t.grenzen[i + 1] if i + 1 < len(t.grenzen) else t.x1
        t.grenzen[i] = round(min(max(x, t.grenzen[i - 1] + 4), rechts - 4), 1)
        zs = self._zeilen_im_rahmen(t)
        g = list(t.grenzen) + [t.x1 + 30]
        andere = [sp for j, sp in enumerate(t.spalten) if j not in (i - 1, i)]
        erkannt = {}
        for j in (i - 1, i):
            titel = (
                _text([w for w in zs[0].woerter if g[j] <= (w.x0 + w.x1) / 2 < g[j + 1]])
                if zs
                else ""
            )
            code = _spalte_fuer(titel) if titel else None
            erkannt[j] = bool(code and code not in andere)
            if not titel:  # Überschrift ganz in die Nachbarspalte gerutscht
                t.spalten[j] = "ignorieren"
            elif erkannt[j]:
                t.spalten[j] = code
        if (
            t.spalten[i - 1] == t.spalten[i] != "ignorieren"
        ):  # doppelt: die Spalte mit passender Überschrift gewinnt
            t.spalten[i - 1 if erkannt[i] and not erkannt[i - 1] else i] = "ignorieren"
        if "BT-149" in t.spalten:
            t.preiseinheit = "spalte"
        elif t.preiseinheit == "spalte":
            t.preiseinheit = "1"
        log.info("Spaltenlinie %d auf x=%.1f verschoben: %s", i, t.grenzen[i], t.spalten)
        return t

    def rahmen_setzen(self, seite: int, x0: float, top: float, x1: float, bottom: float) -> Tabelle:
        """Nutzer hat einen neuen Rahmen gezogen: Spalten neu erkennen, Einheiten-Änderungen behalten."""
        einh, pe = self.tabelle.einheiten, self.tabelle.preiseinheit
        stw = self.tabelle.steuerwerte
        t = Tabelle(
            seite=seite,
            x0=min(x0, x1),
            top=min(top, bottom),
            x1=max(x0, x1),
            bottom=max(top, bottom),
            preiseinheit=pe if pe != "spalte" else "1",
            einheiten=einh,
            steuerwerte=stw,
        )
        kopf = self._kopf_ueber(t)
        if kopf is not None:  # Rahmen erst unter der Kopfzeile begonnen
            t.top = kopf.top - 3
        self.spalten_erkennen(t)
        alt = self.tabelle
        if (
            alt.spaltenrahmen and alt.seite == t.seite
        ):  # gezogene Spalten bleiben, soweit sie im neuen Rahmen liegen
            t.spaltenrahmen = [r for r in alt.spaltenrahmen if r[2] > t.x0 and r[1] < t.x1]
        self.tabelle = t
        return t

    # -- Spalten als eigene Rahmen --------------------------------------------------------------------
    def spalten_aus_linien(self) -> list[list]:
        """Spaltenlinien -> Spaltenrahmen (Übergang in den Spalten-Modus, bisherige Zuordnung bleibt)."""
        t = self.tabelle
        if t.spaltenrahmen or t.leer() or not t.grenzen:
            return t.spaltenrahmen
        g = list(t.grenzen) + [t.x1]
        t.spaltenrahmen = [
            [n, round(g[i] + 1, 1), round(g[i + 1] - 1, 1)]
            for i, n in enumerate(t.spalten)
            if n != "ignorieren" and i + 1 < len(g)
        ]
        return t.spaltenrahmen

    def _kopf_im_rahmen(self) -> Zeile | None:
        zs = self._zeilen_im_rahmen(self.tabelle)
        return zs[0] if zs else None

    def spalte_hinzufuegen(
        self, seite: int, x0: float, top: float, x1: float, bottom: float, code: str | None = None
    ) -> int:
        """Rahmen über eine Spalte gezogen -> Index des Spaltenrahmens. Ohne Tabellenrahmen wird der Rahmen zur
        Tabelle; ragt er über die Tabelle hinaus, wächst sie mit. Die Bedeutung kommt aus der Überschrift im
        Rahmen; ist sie schon vergeben, ersetzt ein deckungsgleicher Rahmen den alten, sonst „ignorieren“."""
        x0, x1 = sorted((x0, x1))
        top, bottom = sorted((top, bottom))
        t = self.tabelle
        if t.leer() or t.seite != seite:
            kopf = next(
                (z for z in self.zeilen if z.seite == seite and top - 4 <= z.top <= bottom), None
            )
            ende = self._tabellenende(self.zeilen.index(kopf)) if kopf else bottom
            self.rahmen_setzen(seite, x0 - 4, top, x1 + 4, max(bottom, ende))
            t = self.tabelle
            t.spaltenrahmen, t.spalten, t.grenzen = (
                [],
                [],
                [],
            )  # neue Tabelle: nur die gezogenen Spalten zählen
        else:
            self.spalten_aus_linien()
        t.top, t.bottom = min(t.top, top), max(t.bottom, bottom)
        t.x0, t.x1 = min(t.x0, x0 - 2), max(t.x1, x1 + 2)
        kopf = self._kopf_im_rahmen()
        if code is None:
            titel = _text(
                [w for w in (kopf.woerter if kopf else []) if x0 <= (w.x0 + w.x1) / 2 <= x1]
            )
            code = _spalte_fuer(titel) if titel else None
        breite = x1 - x0
        for r in list(t.spaltenrahmen):  # deckungsgleich (mehr als die Hälfte) -> ersetzt
            ueber = min(r[2], x1) - max(r[1], x0)
            if ueber > 0.5 * min(breite, r[2] - r[1]):
                code = code or r[0]
                t.spaltenrahmen.remove(r)
        if code is None or (code != "ignorieren" and code in t.codes()):
            frei = [c for c in PFLICHTSPALTEN if c not in t.codes()]
            code = frei[0] if code is None and frei else "ignorieren"
        for r in t.spaltenrahmen:  # Nachbarn nicht überlappen lassen
            if r[1] < x0 < r[2]:
                r[2] = round(x0 - 1, 1)
            if r[1] < x1 < r[2]:
                r[1] = round(x1 + 1, 1)
        t.spaltenrahmen = [r for r in t.spaltenrahmen if r[2] - r[1] >= 3]
        neu = [code, round(x0, 1), round(x1, 1)]
        t.spaltenrahmen.append(neu)
        t.spaltenrahmen.sort(key=lambda r: r[1])
        self._pe_nachziehen()
        log.info("Spaltenrahmen %s x=%.1f–%.1f", code, x0, x1)
        return t.spaltenrahmen.index(neu)

    def spalte_bedeutung(self, i: int, code: str) -> None:
        """Bedeutung eines Spaltenrahmens ändern; eine andere Spalte mit derselben Bedeutung wird getauscht."""
        rs = self.tabelle.spaltenrahmen
        if not 0 <= i < len(rs):
            return
        if code != "ignorieren":
            for j, r in enumerate(rs):
                if j != i and r[0] == code:
                    r[0] = rs[i][0]
        rs[i][0] = code
        self._pe_nachziehen()

    def spalte_verschieben(self, i: int, x0: float, x1: float) -> None:
        """Spaltenrahmen verschoben oder in der Breite geändert (begrenzt auf die Nachbarn und den Tabellenrahmen)."""
        t = self.tabelle
        rs = t.spaltenrahmen
        if not 0 <= i < len(rs):
            return
        x0, x1 = sorted((x0, x1))
        lo = rs[i - 1][2] + 1 if i > 0 else t.x0
        hi = rs[i + 1][1] - 1 if i + 1 < len(rs) else t.x1
        breite = x1 - x0
        if (
            abs(breite - (rs[i][2] - rs[i][1])) < 0.05 and breite <= hi - lo
        ):  # verschoben: Breite bleibt
            x0 = min(max(x0, lo), hi - breite)
            x1 = x0 + breite
        x0, x1 = max(x0, lo), min(x1, hi)
        if x1 - x0 >= 3:
            rs[i][1], rs[i][2] = round(x0, 1), round(x1, 1)

    def spalte_entfernen(self, i: int) -> None:
        rs = self.tabelle.spaltenrahmen
        if 0 <= i < len(rs):
            del rs[i]
            if not rs:  # alle Spalten gelöscht: die alten Linien kommen nicht zurück
                self.tabelle.grenzen, self.tabelle.spalten = [], []
            self._pe_nachziehen()

    def _pe_nachziehen(self) -> None:
        t = self.tabelle
        if "BT-149" in t.codes():
            t.preiseinheit = "spalte"
        elif t.preiseinheit == "spalte":
            t.preiseinheit = "1"

    def spalten_zustand(self) -> list[tuple[str, int]]:
        """Je Spaltenrahmen: (Code, Zahl der Positionen mit einem Wert in dieser Spalte) – für die Liste."""
        pv = self.pv()
        if not pv:
            return [(r[0], 0) for r in self.tabelle.spaltenrahmen]
        feld = {
            "BT-153": "bezeichnung",
            "BT-129": "menge",
            "BT-130": "einheit_text",
            "BT-146": "einzelpreis",
            "BT-149": "preiseinheit",
            "gesamt": "gesamt",
            "BT-155": "artikelnummer",
            "BT-126": "nr",
            "steuer": "steuer_text",
        }
        bereiche = pdferkennung._bereiche(pv)
        n: dict[str, int] = {}
        prot: list = []
        pdferkennung.positionen_auslesen(pv, self.zeilen, prot)  # alle Seiten
        for z in [z for z, g in prot if g.startswith("Position")]:
            p, sp, _g = pdferkennung.zeile_lesen(z, pv, bereiche)
            if p:
                for c in sp:
                    n[c] = n.get(c, 0) + 1
        return [(r[0], n.get(r[0], 0) if r[0] in feld else 0) for r in self.tabelle.spaltenrahmen]

    def _seitenuebertrag(self, z: Zeile, nach: list[Zeile]) -> bool:
        """„Übertrag“/„Zwischensumme“ am Seitenende: danach kommt erst eine neue Seite, dann die echte Summe."""
        if re.search(r"übertrag|uebertrag", norm(z.text)):
            return True
        if not pdferkennung.ist_uebertrag(z):
            return False
        i = nach.index(z)
        return any(z2.seite != z.seite for z2 in nach[i + 1 :])

    def _letzte_tabellenzeile(self, pv: dict, t: Tabelle, zs: list[Zeile]) -> tuple[int, float]:
        """(Seite, top) der letzten Position – bei mehrseitigen Tabellen auf der letzten Seite mit Positionen.
        Vorlauf ohne Tabellenende – das Ende erkennt ``positionen_auslesen`` selbst (``ist_summenzeile``)."""
        letzte = (t.seite, zs[-1].top)
        prot: list = []
        pdferkennung.positionen_auslesen(
            {k: v for k, v in pv.items() if k != "ende"}, self.zeilen, prot
        )
        for z, grund in prot:
            if grund.startswith("Position") and (z.seite, z.top) > letzte:
                letzte = (z.seite, z.top)
        return letzte

    def pv(self) -> dict | None:
        """Tabelle -> Positionsbeschreibung der Vorlage (wie positionen_lernen sie anlegt)."""
        t = self.tabelle
        if t.leer() or not (t.grenzen or t.spaltenrahmen):
            return None
        zs = self._tabellenzeilen(t)
        if len(zs) < 2:
            return None
        kopf = zs[0]
        if t.spaltenrahmen:  # Spalten als eigene Rahmen: genau diese Bereiche
            spalten = {}
            for name, a, b in t.spaltenrahmen:
                if (
                    name in pdferkennung.ZAHLSPALTEN
                ):  # rechtsbündige Zahlen, die über den Rahmen ragen
                    xs = [
                        w.x1
                        for z in zs[1:]
                        for w in z.woerter
                        if a <= w.x1 and w.x0 <= b and re.match(r"^-?[\d.,]+$", w.t)
                    ]
                    b = max([b] + xs)
                spalten[name] = [
                    round(a + 2, 1),
                    round(b - 2, 1) if name not in pdferkennung.ZAHLSPALTEN else round(b, 1),
                ]
            spalten = {n: v for n, v in spalten.items() if n != "ignorieren"}
        else:
            grenzen = list(t.grenzen) + [t.x1]
            ausdehnung: dict[str, list[float]] = {}
            for i, name in enumerate(t.spalten):
                ausdehnung[name] = [grenzen[i] + 2, grenzen[i + 1] - 2]
            for name in pdferkennung.ZAHLSPALTEN:  # rechter Rand = rechtester Wert in der Spalte
                if name in t.spalten:
                    i = t.spalten.index(name)
                    xs = [
                        w.x1
                        for z in zs[1:]
                        for w in z.woerter
                        if grenzen[i] <= (w.x0 + w.x1) / 2 < grenzen[i + 1]
                        and re.match(r"^-?[\d.,]+$", w.t)
                    ]
                    if xs:
                        ausdehnung[name][1] = max(xs)
            spalten = {
                n: [round(a, 1), round(b, 1)]
                for n, (a, b) in ausdehnung.items()
                if n not in ("ignorieren",)
            }
            if "ignorieren" in t.spalten:  # eigene Spalte, damit Wörter dort nicht woanders landen
                i = t.spalten.index("ignorieren")
                spalten["ignorieren"] = [round(grenzen[i] + 2, 1), round(grenzen[i + 1] - 2, 1)]
        fmt = None
        for z in zs[1:]:
            for w in z.woerter:
                b = betraege(w.t)
                if b:
                    fmt = b[0][1]
                    break
            if fmt:
                break
        pv: dict = {
            "kopf": pdferkennung._zeilen_tokens(kopf),
            "format": fmt,
            "spalten": spalten,
            "zeilenabstand": 14.0,
            "rahmen": [round(t.x0, 1), round(t.top, 1), round(t.x1, 1), round(t.bottom, 1)],
        }
        if t.spaltenrahmen:
            pv["spalten_fest"] = True
            pv["anker_betrag"] = True
        letzte = self._letzte_tabellenzeile(pv, t, zs)
        nach = [z for z in self.zeilen if (z.seite, z.top) > letzte]
        summe = [
            z
            for z in nach
            if pdferkennung.summentext(z.text) and not self._seitenuebertrag(z, nach)
        ]
        if summe:  # mehrseitig: „Übertrag“/„Zwischensumme“ beendet die Tabelle nicht
            nach = summe
        else:  # erste Zeile nach der Tabelle, die keine Position ist
            nach = self._nach_tabelle(pv, [z for z in nach if z.seite == letzte[0]], letzte[1])
        if nach:
            toks = pdferkennung._zeilen_tokens(nach[0])
            vorn = []
            for tk in toks:
                if tk == "#":
                    break
                vorn.append(tk)
            pv["ende"] = vorn[:3] if vorn else toks
        if t.preiseinheit != "spalte":
            pv["spalten"].pop("BT-149", None)
            if t.preiseinheit != "1":
                pv["preiseinheit_fest"] = t.preiseinheit
        pos = pdferkennung.positionen_auslesen(pv, self.zeilen)
        tops = sorted({round(z.top, 1) for z in zs[1:]})
        if len(tops) > 1:
            abst = sorted(b - a for a, b in zip(tops, tops[1:]))
            pv["zeilenabstand"] = round(abst[len(abst) // 2], 1)
        if "BT-130" in pv["spalten"]:
            pv["einheiten"] = {
                p.einheit_text: (
                    t.einheiten.get(p.einheit_text) or einheit_code(p.einheit_text) or ""
                )
                for p in pos
                if p.einheit_text
            }
            if any(
                not p.einheit_text for p in pos
            ):  # Zeile ohne Einheit: nicht still raten, einmal wählen
                pv["einheiten"][pdferkennung.OHNE_EINHEIT] = (
                    t.einheiten.get(pdferkennung.OHNE_EINHEIT) or ""
                )
        else:
            pv.update(pdferkennung.einheit_ohne_spalte(pos, t.einheiten))
        satz = self.wert("BT-119")
        fall = self.steuerfall_wirksam()
        if "steuer" in pv["spalten"]:
            # Steuerspalte: Steuerfall je Position (ab 0.9.7 auch „RC“, „igL“, „0 %“ mit Hinweis; Auswahl je Wert)
            st = {}
            buchstaben = pdferkennung.steuerbuchstaben_aus_zeilen(self.zeilen)
            wahl = getattr(t, "steuerwerte", {}) or {}
            for p in pos:
                w = wahl.get(p.steuer_text)
                kurz = steuerfaelle.erkennen_kurz(p.steuer_text)
                m = re.search(r"(\d{1,2}(?:,\d{1,2})?)", p.steuer_text)
                if w:
                    st[p.steuer_text] = steuerwert_mapping(w, self.steuerfall_text() if w == fall else "")
                elif kurz:
                    st[p.steuer_text] = steuerwert_mapping(kurz, self.steuerfall_text() if kurz == fall else "")
                elif m and Decimal(m[1].replace(",", ".")) == 0 and fall != "S":
                    # 0 % ohne Kennzeichen: Steuerfall aus der Auswahl, sonst je Rechnung aus dem Hinweistext
                    st[p.steuer_text] = (
                        steuerwert_mapping(fall, self.steuerfall_text()) if self.steuerfall else {"fall": "hinweis"}
                    )
                elif m:
                    st[p.steuer_text] = {"BT-151": "S", "BT-152": m[1].replace(",", ".")}
                elif pdferkennung.ist_steuerbuchstabe(p.steuer_text):
                    if p.steuer_text in buchstaben:
                        st[p.steuer_text] = buchstaben[p.steuer_text]
                    # sonst: nicht still den Rechnungssatz zuordnen → prüfen
                elif satz is not None:
                    st[p.steuer_text] = {"BT-151": "S", "BT-152": str(satz)}
            pv["steuer"] = st
        elif self.steuerfall and self.steuerfall != "S":  # ausgewählt: fester Steuerfall der Vorlage
            pv["steuer_fest"] = steuerwert_mapping(self.steuerfall)
        elif not self.steuerfall and (fall != "S" or (satz is not None and satz > 0)):
            # Steuersatz nur im Summenblock: ein Steuerfall je Rechnung – aus dem Steuerhinweis im Druck, ohne
            # Hinweis der Steuersatz (Regelbesteuerung)
            pv["steuer_fest"] = {"fall": "hinweis"}
            if satz is not None and satz > 0:
                pv["steuer_fest"].update({"BT-151": "S", "BT-152": str(satz)})
        elif (
            satz is not None
        ):  # ohne Steuersatz kein stiller Standard (19 %): Positionen bleiben „prüfen“
            pv["steuer_fest"] = {"BT-151": "S", "BT-152": str(satz)}
        return pv

    def steuerwerte_offen(self) -> dict[str, str]:
        """Werte der Steuerspalte -> gewählter/erkannter Steuerfall („S:19“, „AE“ …) oder "" (offen)."""
        pv = self.pv() or {}
        if "steuer" not in (pv.get("spalten") or {}):
            return {}
        wahl = getattr(self.tabelle, "steuerwerte", {}) or {}
        out = {}
        for text, m in (pv.get("steuer") or {}).items():
            out[text] = wahl.get(text) or steuerwert_kennung(m)
        for p in self.positionen():
            if p.steuer_text and p.steuer_text not in out:
                out[p.steuer_text] = wahl.get(p.steuer_text, "")
        return out

    @staticmethod
    def _nach_tabelle(pv: dict, nach: list[Zeile], letzte_top: float) -> list[Zeile]:
        """Zeilen unter dem Rahmen: Positions-, Fortsetzungs- und Trennzeilen überspringen (Rahmen zu knapp
        gezogen), ab der ersten anderen Zeile zurückgeben – dort endet die Tabelle, nicht am Rahmenrand.
        Eine Trennlinie taugt nicht als Tabellenende: dieselbe Linie steht oft auch unter der Kopfzeile."""
        bereiche = pdferkennung._bereiche(pv)
        vorige = letzte_top
        for i, z in enumerate(nach):
            if pdferkennung.ist_trennlinie(z):
                continue
            p, sp, _g = pdferkennung.zeile_lesen(z, pv, bereiche)
            if p:
                vorige = z.top
                continue
            if not sp or (
                pdferkennung.fortsetzung_text(sp) is not None
                and z.top - vorige <= pv.get("zeilenabstand", 14) * 1.6 + 2
            ):
                vorige = z.top if sp else vorige
                continue
            return nach[i:]
        return []

    def tabellen_bereiche(self) -> dict[int, tuple[float, float]]:
        """Seite -> (top, bottom) der Tabelle: auf der Rahmenseite der gezogene Rahmen, auf Folgeseiten der Bereich
        von wiederholter Kopfzeile bis zur letzten Position (der Rahmen gilt dort mit denselben Spalten)."""
        t = self.tabelle
        if t.leer():
            return {}
        out = {t.seite: (t.top, t.bottom)}
        pv = self.pv()
        if not pv:
            return out
        prot: list = []
        pdferkennung.positionen_auslesen(pv, self.zeilen, prot)
        for z, grund in prot:
            if z.seite == t.seite or not (
                grund == "Kopfzeile" or grund.startswith(("Position", "Fortsetzung"))
            ):
                continue
            unten = max((w.bottom for w in z.woerter), default=z.top + 10)
            a, b = out.get(z.seite, (z.top - 2, unten + 2))
            out[z.seite] = (min(a, z.top - 2), max(b, unten + 2))
        return out

    def positionen(self) -> list[pdferkennung.PosRoh]:
        pv = self.pv()
        return pdferkennung.positionen_auslesen(pv, self.zeilen) if pv else []

    def einheiten_offen(self) -> dict[str, str]:
        """Einheiten im Druck -> Code ("" = unbekannt, muss der Nutzer wählen)."""
        pv = self.pv() or {}
        return dict(pv.get("einheiten") or {})

    def tabellen_diagnose(self) -> str:
        """Aufbau der Tabelle ohne Rechnungstext, zum Weitergeben, wenn keine Positionen erkannt werden:
        je Zeile die Höhe, je Wort x-Bereich und Form (Buchstaben -> a/A, Ziffern -> 9, Satzzeichen bleiben)
        und welche Regel die Zeile angenommen oder verworfen hat."""
        from . import __version__

        t = self.tabelle
        out = [
            f"Fakturafalter {__version__} – Tabellendiagnose (Buchstaben = a/A, Ziffern = 9, kein Rechnungstext)"
        ]
        if t.leer():
            return "\n".join(out + ["kein Tabellenrahmen"])
        out.append(
            f"Seite {t.seite + 1}, Rahmen x {t.x0:.1f}–{t.x1:.1f}, y {t.top:.1f}–{t.bottom:.1f}"
        )
        if t.spaltenrahmen:
            out.append(
                "Spaltenrahmen: " + "  ".join(f"{c} {a:.1f}–{b:.1f}" for c, a, b in t.spaltenrahmen)
            )
        else:
            out.append(
                "Spaltenlinien: "
                + " ".join(f"{g:.1f}" for g in t.grenzen)
                + " | "
                + " ".join(t.spalten)
            )
        pv = self.pv()
        protokoll: list = []
        if pv:
            out.append(
                "Vorlage: "
                + "  ".join(
                    f"{c} {a:.1f}–{b:.1f}"
                    for c, (a, b) in sorted(pv["spalten"].items(), key=lambda kv: kv[1][0])
                )
            )
            out.append(
                "Kopf: "
                + " ".join(maskieren(x) for x in pv["kopf"])
                + "  |  Ende: "
                + (" ".join(maskieren(x) for x in pv["ende"]) if pv.get("ende") else "–")
                + f"  |  Format: {pv.get('format') or '–'}  |  PE fest: {t.preiseinheit}"
                + ("  |  feste Spalten, Betrag trägt die Zeile" if pv.get("spalten_fest") else "")
            )
            pdferkennung.positionen_auslesen(pv, self.zeilen, protokoll)
        else:
            out.append(
                "Keine Vorlage möglich (weniger als zwei Zeilen im Rahmen oder keine Spalten)"
            )
        grund = {id(z): g for z, g in protokoll}
        zs = [
            z for z in self.zeilen if z.seite == t.seite and t.top - 30 <= z.top <= t.bottom + 120
        ]
        for z in zs:
            ws = "  ".join(f"{w.x0:.1f}–{w.x1:.1f} {maskieren(w.t)}" for w in z.woerter)
            ort = "im Rahmen" if t.top <= z.top + 4 <= t.bottom else "außerhalb"
            out.append(f"y {z.top:6.1f} [{ort}; {grund.get(id(z), 'nicht gelesen')}]  {ws}")
        return "\n".join(out)

    def tabelle_fehlt(self) -> list[str]:
        """Was fehlt noch an der Tabelle? (Texte für die Fußzeile, leer = fertig)"""
        t = self.tabelle
        if t.leer():
            return ["Rahmen um die Tabelle ziehen"]
        pflicht = ("BT-153", "gesamt") if t.spaltenrahmen else PFLICHTSPALTEN
        out = [f"Spalte „{SPALTEN[s]}“ zuordnen" for s in pflicht if s not in t.codes()]
        if out:
            return out
        if not self.positionen():
            schluessel = (
                t.seite,
                t.x0,
                t.top,
                t.x1,
                t.bottom,
                tuple(t.grenzen),
                tuple(t.spalten),
                tuple(tuple(r) for r in t.spaltenrahmen),
            )
            if getattr(self, "_diagnose_geloggt", None) != schluessel:
                self._diagnose_geloggt = schluessel
                log.info(
                    "Keine Positionen im Rahmen erkannt – Diagnose ohne Rechnungstext:\n%s",
                    self.tabellen_diagnose(),
                )
            return ["Keine Positionen im Rahmen erkannt"]
        if any(not c for c in self.einheiten_offen().values()):
            return ["Unbekannte Einheit zuordnen"]
        abw = self.betrag_abweichungen()
        if abw:
            nr, *_rest = abw[0]
            return [
                f"Pos {nr}: Menge × Preis ÷ Preiseinheit ergibt nicht den Betrag – „Preis gilt für“ prüfen"
            ]
        return []

    def betrag_abweichungen(
        self,
    ) -> list[tuple[str, Decimal | None, Decimal | None, Decimal, Decimal, Decimal]]:
        """Positionen, deren Betrag sich beim Speichern nicht nachrechnen lässt – mit genau der Rechnung und den
        Werten, die ``rechnung()`` verwendet: (Pos, Menge, Preis, Preiseinheit, berechnet, Quelle)."""
        pv = self.pv() or {"spalten": {}}
        out = []
        for i, p in enumerate(self.positionen(), 1):
            pe = pdferkennung.pos_preiseinheit(pv, p)
            netto = rechnen.positionsbetrag(p.menge, p.einzelpreis, pe)
            if p.gesamt is not None and not rechnen.betrag_passt(netto, p.gesamt):
                out.append((p.nr or str(i), p.menge, p.einzelpreis, pe, netto, p.gesamt))
        if out and getattr(self, "_abw_geloggt", None) != out:
            self._abw_geloggt = out
            for nr, m, e, pe, netto, q in out:
                log.info(
                    "Vorschau Pos %s: Menge %s × Preis %s ÷ Preiseinheit %s = berechnet %s, Quelle %s",
                    nr,
                    m,
                    e,
                    pe,
                    netto,
                    q,
                )
        return out

    def summenpruefung(self) -> tuple[Decimal, Decimal | None, bool]:
        """-> (Summe der Positionen, Netto laut Rechnung, passt?)."""
        summe = sum((p.gesamt for p in self.positionen() if p.gesamt is not None), Decimal("0"))
        netto = self.wert("BT-109")
        return (
            summe,
            netto,
            netto is not None and abs(summe - netto) <= pdferkennung.SUMMEN_TOLERANZ,
        )

    def fertig(self) -> bool:
        a_ok = not self.absender.fehlt()
        return (
            a_ok and not self.fehlende() and not self.tabelle_fehlt() and self.summenpruefung()[2]
        )

    # -- Rechnung bauen und speichern -------------------------------------------------------------
    def _definition(self) -> dict:
        prof = (
            copy.deepcopy(self.profil)
            if self.profil
            else profil_daten(self.absender, ziel_tage(self.werte["BT-20"].wert))
        )
        vk, zb = self.absender.bloecke()
        prof["verkaeufer"] = {**(prof.get("verkaeufer") or {}), **vk}
        if not self.absender.kleinunternehmer:
            prof["verkaeufer"].pop("kleinunternehmer", None)
        prof["zahlung"] = {**(prof.get("zahlung") or {}), **zb}
        return prof

    def _kaeufer_nebenfelder(self) -> dict[str, str]:
        """Kontaktstelle (BT-56) und Adresszeile 3 (BT-163): zuerst die Assistentenfelder, sonst der zerlegte
        Anschriftblock, solange Name und Zusatz noch zum Block passen."""
        out = {
            f: vs.wert.strip()
            for f in KAEUFER_NEBENFELDER
            if (vs := self.werte.get(f)) and (vs.wert or "").strip()
        }
        if len(out) == len(KAEUFER_NEBENFELDER):
            return out
        for teile in (
            (self.anschrift_block or (None, None, None))[2],
            getattr(self, "_vorlage_teile", None),
            (self._block_vorschlag or (None, None, None))[2],
        ):
            if teile and all(
                norm(self.werte[f].wert or "") == norm(teile.get(f, "")) for f in ("BT-44", "BT-51")
            ):
                for f in KAEUFER_NEBENFELDER:
                    if teile.get(f):
                        out.setdefault(f, teile[f])
                break
        return out

    def rechnung(self) -> Rechnung:
        h = Herkunft(HERKUNFT, 1.0)
        kopf: dict = {}
        for f in (
            "BT-1",
            "BT-2",
            "BT-109",
            "BT-110",
            "BT-112",
            "BT-13",
            "BT-20",
            "kundennummer",
            *KAEUFER_FELDER_ANLERNEN,
            *KAEUFER_NEBENFELDER,
            *STEUERFELDER,
        ):
            w = self.wert(f)
            if w is not None and w != "":
                kopf[f] = (w, h)
        if "steuerhinweis" not in kopf and self.steuerfall_wirksam() not in ("S", "KU"):
            kopf["steuerhinweis"] = (self.steuerfall_text(), h)
        art = self.belegart()
        if art:
            kopf["BT-3"] = (art, h)
        if art == "381" and self.werte["BT-25"].wert:  # BG-3 nur bei Gutschrift
            nummer, datum = pdferkennung.bezug_zerlegen(self.werte["BT-25"].wert)
            kopf["BT-25"] = (nummer or self.werte["BT-25"].wert, h)
            if datum:
                kopf["BT-26"] = (datum, h)
        lw = self.wert("leistung")
        if isinstance(lw, tuple):
            kopf["BT-73"], kopf["BT-74"] = (lw[0], h), (lw[1], h)
        elif lw is not None:
            kopf["BT-72"] = (lw, h)
        pv = self.pv() or {"spalten": {}}
        pos = []
        for p in self.positionen():
            roh = {
                "BT-153": (p.bezeichnung, h),
                "BT-129": (p.menge, h),
                "BT-146": (p.einzelpreis, h),
                "gesamt_kontrolle": (p.gesamt, h),
                "steuer": (p.steuer_text if "steuer" in pv else "*", h),
                "BT-130": (pdferkennung.einheit_schluessel(pv, p), h),
            }
            if p.nr:
                roh["BT-126"] = (p.nr, h)
            if p.artikelnummer:
                roh["BT-155"] = (p.artikelnummer, h)
            if pdferkennung.pos_preiseinheit(pv, p) != 1:
                roh["BT-149"] = (pdferkennung.pos_preiseinheit(pv, p), h)
            pos.append(roh)
        definition = self._definition()
        definition["mappings"] = {
            "einheiten": pdferkennung.einheiten_mapping(pv, [roh["BT-130"][0] for roh in pos]),
            "steuer": pdferkennung.steuer_zuordnung(pv),
        }
        for f, t_ in self._kaeufer_nebenfelder().items():
            kopf.setdefault(f, (t_, h))
        r = rechnung_bauen(kopf, pos, definition, self.k, quelle=str(self.pfad))
        zahlungsziel.profiltext_sperren(r, self.volltext())
        druck = pdferkennung.steuerhinweis_im_druck(self.zeilen)
        pdferkennung.steuerfall_abgleichen(r, (druck[1] if druck else "") or self.werte["steuerhinweis"].wert)
        r.profil = pdferkennung.profil_name(definition)
        r.sicht_pdf = (str(self.pfad), sorted({z.seite for z in self.zeilen}))
        rechnen.berechnen(r)
        pdferkennung.summen_pruefen(r)
        return r

    def speichern(self, konfig_pfad: Path | None = None):
        """Rechnung erzeugen, Vorlage fortschreiben, PDF nach „Erledigt“.

        -> (Ergebnis, Vorlage). Bei Status ≠ ok wird nichts erzeugt und nichts gelernt; die Hinweise erklären
        warum (die Oberfläche zeigt den ersten, alles andere steht im Log)."""
        from . import pipeline
        from .pipeline import Ergebnis, Lauf

        r = self.rechnung()
        pflichtpruefung.pruefen(r, pipeline.pflicht_kontext(self.k))
        erg = Ergebnis(
            nummer=r.nummer,
            status=r.status,
            quellen=[str(self.pfad)],
            kunde=r.kaeufer.name,
            brutto=str(r.summen.brutto) if r.summen.brutto else "",
        )
        namen = pipeline.ausgabe_namen_oder_hinweis(r, self.k) if erg.status == "ok" else None
        n_pdf = namen[0] if namen else ""
        if namen is None and erg.status == "ok":
            erg.status = r.status
        if erg.status == "ok" and (self.k.ausgang / n_pdf).exists():
            eigener_name = n_pdf != pipeline.ausgabe_namen(r.nummer)[0]  # Dateinamen-Muster (ab 0.9.5)
            if eigener_name or r.nummer in protokoll.bekannte_nummern(self.k):
                r.hinweis(
                    "pruefen",
                    f"Ausgabe {n_pdf} existiert bereits – Rechnung wurde schon erzeugt?",
                    "BT-1",
                )
                erg.status = r.status
            else:  # Rest eines abgebrochenen Speicherns (nicht im Protokoll): wird ersetzt
                log.info(
                    "Anlernen %s: %s ohne Protokolleintrag (abgebrochenes Speichern?) – wird ersetzt",
                    self.pfad.name,
                    self.k.ausgang / n_pdf,
                )
        erg.hinweise = pipeline._hinweise(r)
        if erg.status != "ok":
            for hw in erg.hinweise:
                log.info("Anlernen %s: %s", self.pfad.name, hw)
            return erg, None
        # Erst prüfen, ob überall geschrieben werden kann – dann entsteht nichts Halbes
        dateien.beschreibbar_pruefen(self.k.ausgang)
        dateien.beschreibbar_pruefen(self.k.protokoll, protokoll.pfad(self.k))
        dateien.beschreibbar_pruefen(
            pdferkennung.ablage(self.profil) if self.profil else self.k.basis / "angelernt"
        )
        dateien.beschreibbar_pruefen(self.k.basis)
        ent = pipeline.entwurf_erzeugen(r, self.k)  # im System-Temp; in den Ausgang erst nach der Prüfung
        erg.dateien = ent.dateien
        try:
            try:
                if self.k.nachpruefen and pipeline.nachpruefen([erg], self.k):
                    for hw in erg.hinweise:
                        log.warning("Anlernen %s: %s", self.pfad.name, hw)
                    erg.status = "fehler"
                    raise _Verworfen
                erg.dateien = pipeline.ablegen(ent, self.k)
            finally:
                ent.verwerfen()
            prof = self.profil
            if prof is None:
                prof = profil_anlegen(
                    self.absender, self.k, konfig_pfad, ziel_tage(self.werte["BT-20"].wert)
                )
                self.profil = prof
            elif self.absender_geaendert():
                profil_absender_schreiben(prof, self.absender)
            es = pdferkennung.einstellungen(prof)
            v, quote = pdferkennung.lernen(
                r,
                self.zeilen,
                prof,
                self.vorlage,
                es,
                pv_vorgabe=self.pv(),
                stellen=self.stellen(),
                bereiche=self.bereiche(),
                flaechen=copy.deepcopy(self.zonen),
            )
            try:
                kontrolle = self.selbst_kontrollieren(v)
            except Exception:  # noqa: BLE001 – die Kontrolle darf das Speichern nie verhindern
                log.exception("Anlernen %s: Selbstkontrolle fehlgeschlagen", self.pfad.name)
                kontrolle = {}
            pdferkennung.kontrolle_setzen(v, self._kontrolle_neu(kontrolle))
            pdferkennung.vorlage_speichern(v, prof)
            pipeline._protokoll(Lauf(ergebnisse=[erg]), self.k)
        except _Verworfen:
            for d in erg.dateien:
                Path(d).unlink(missing_ok=True)
            return erg, None
        except BaseException:  # nichts Halbes liegen lassen: ohne Protokoll keine Ausgabe
            log.warning(
                "Anlernen %s: Speichern abgebrochen – erzeugte Dateien werden entfernt",
                self.pfad.name,
            )
            for d in erg.dateien:
                Path(d).unlink(missing_ok=True)
            raise
        self.vorlage = v
        self.selbstkontrolle = kontrolle
        self.kontrolle_offen = pdferkennung.kontrolle_offen(v)
        log.info(
            "Anlernen %s: Vorlage %s-%s, Trefferquote %s, %s in Folge",
            self.pfad.name,
            v["profil"],
            v["kennung"],
            quote,
            v["statistik"].get("folge_treffer", 0),
        )
        self.zaehler_grund = v["statistik"].get("zurueckgesetzt", "") if quote is not None else ""
        if self.zaehler_grund:
            log.info("Anlernen %s: Zähler zurückgesetzt: %s", self.pfad.name, self.zaehler_grund)
        self.nicht_verschoben = None
        if self.pfad.exists() and self.pfad.parent != self.k.erledigt:
            try:  # Rechnung und Vorlage sind gespeichert; die PDF bleibt notfalls liegen
                pipeline._verschieben(self.pfad, self.k.erledigt)
            except OSError as e:
                self.nicht_verschoben = e
                log.warning(
                    "Anlernen %s: PDF nicht nach %s verschoben: %s",
                    self.pfad.name,
                    self.k.erledigt,
                    e.details() if isinstance(e, dateien.DateiNichtSchreibbar) else e,
                )
        return erg, v

    def _kontrolle_neu(self, kontrolle: dict) -> list[str]:
        """Offene Selbstkontrolle nach dem Speichern: bisher offene Felder bleiben offen, außer sie sind in dieser PDF
        bestätigt und werden mit der neuen Vorlage richtig gelesen; neue Abweichungen kommen dazu."""
        bestaetigt = {
            f for f in FELDER if self.werte[f].status == "erkannt" and self.wert(f) is not None
        }
        if self.positionen():
            bestaetigt.add("positionen")
        alt = [f for f in self.kontrolle_offen if f not in bestaetigt or f in kontrolle]
        return alt + list(kontrolle)

    def selbst_kontrollieren(self, v: dict | None = None) -> dict[str, tuple[str, str]]:
        """Selbstkontrolle direkt nach dem Speichern: dieselbe PDF mit der neuen Vorlage noch einmal lesen und
        mit den bestätigten Werten vergleichen. -> {Feld: (bestätigt, neu gelesen)} – leer, wenn alles gleich
        gelesen wird. Abweichungen stehen mit Werten im Log (lokal), in der Oberfläche nur die Feldnamen.
        ``v``: die neue Vorlage (Standard: die der Sitzung)."""
        if v is not None and v is not self.vorlage:
            alt, self.vorlage = self.vorlage, v
            try:
                return self.selbst_kontrollieren()
            finally:
                self.vorlage = alt
        v = self.vorlage or {}
        regeln = v.get("felder") or {}
        out: dict[str, tuple[str, str]] = {}
        for feld in FELDER:
            kand = ["BG-14", "BT-72"] if feld == "leistung" else [feld]
            if feld in pdferkennung.BLOCKFELDER and pdferkennung.ANSCHRIFT_BLOCK in regeln:
                kand = [pdferkennung.ANSCHRIFT_BLOCK]
            soll = self.wert(feld)
            if soll is None or self.werte[feld].status != "erkannt":
                continue  # nur bestätigte Felder: Unbestätigtes wird nicht gelernt
            if not any(f in regeln for f in kand):
                # im Druck gefunden, im Bereich aber nicht gelernt (Rahmen hat Vorrang): als Abweichung zeigen
                if (
                    self._zone_von(feld)
                    and self.werte[feld].woerter
                    and feld not in ("BT-119", "leistung")
                ):
                    out[feld] = (anzeigen(feld, soll), "")
                continue
            erg = self._aus_vorlage(feld)
            ist = lesen(feld, erg[0]) if erg else None
            if ist != soll:
                out[feld] = (anzeigen(feld, soll), anzeigen(feld, ist) if ist is not None else "")
        pv = v.get("positionen")
        if pv:
            alt = self.positionen()
            neu = pdferkennung.positionen_auslesen(pv, self.zeilen)
            s_alt = sum((p.gesamt for p in alt if p.gesamt is not None), Decimal("0"))
            s_neu = sum((p.gesamt for p in neu if p.gesamt is not None), Decimal("0"))
            if len(alt) != len(neu) or s_alt != s_neu:
                out["positionen"] = (
                    f"{len(alt)} Positionen, {s_alt}",
                    f"{len(neu)} Positionen, {s_neu}",
                )
        for feld, (soll, ist) in out.items():
            log.warning(
                "Anlernen %s: Selbstkontrolle %s: bestätigt „%s“, mit der neuen Vorlage gelesen „%s“",
                self.pfad.name,
                FELDER.get(feld, ("Positionen",))[0],
                soll,
                ist or "–",
            )
        return out

    def kontrolle_markieren(self, felder) -> list[str]:
        """Felder, die die Selbstkontrolle nach dem letzten Speichern anders gelesen hat, in dieser PDF auf
        „prüfen“ setzen (Markierung am Feld). -> markierte Felder."""
        out = []
        for f in felder:
            vs = self.werte.get(f)
            if vs is None:
                continue
            if vs.status == "erkannt":
                vs.status = "pruefen"
            vs.hinweis = (
                "Selbstkontrolle: Nach dem letzten Speichern hat die Vorlage dieses Feld anders gelesen "
                "– bitte prüfen."
            )
            out.append(f)
        return out

    def bereiche_diagnose(self) -> str:
        """Kopf, Summen und Zahlung ohne Rechnungstext (wie die Tabellendiagnose): je Bereich der Rahmen (mit
        Verschiebung), je Feld die Regel und ob sie liest, je Zeile im Rahmen Lage und Form der Wörter."""
        from . import __version__

        out = [
            f"Fakturafalter {__version__} – Bereichsdiagnose Kopf/Summen/Zahlung "
            "(Buchstaben = a/A, Ziffern = 9, kein Rechnungstext)"
        ]
        v = {**(self.vorlage or {}), "bereiche": self.zonen}
        regeln = v.get("felder") or {}
        for name in ("kopf", "summen", "zahlung"):
            titel = pdferkennung.BEREICH_NAMEN.get(name, name)
            b = self.zonen.get(name)
            out.append(f"[{titel}]")
            if not b:
                out.append("  kein Rahmen – Felder werden auf der ganzen Seite gesucht")
            else:
                for s in self.zone_seitenfolge(name):
                    d = pdferkennung.bereich_verschiebung(v, b, self.zeilen, s)
                    r = pdferkennung.bereich_rahmen_auf(v, b, self.zeilen, s)
                    out.append(
                        f"  Seite {s + 1}: Rahmen x {r[0]:.1f}–{r[2]:.1f}, y {r[1]:.1f}–{r[3]:.1f}"
                        + (f", mit Tabellenende verschoben um {d:+.1f}" if d else "")
                    )
                    for z in pdferkennung.zeilen_im_rahmen(self.zeilen, s, r):
                        ws = "  ".join(f"{w.x0:.1f}–{w.x1:.1f} {maskieren(w.t)}" for w in z.woerter)
                        out.append(f"    y {z.top:6.1f}  {ws}")
            for feld in pdferkennung.BEREICHE.get(name, ()):
                if feld not in FELDER:
                    continue
                regel = regeln.get(feld)
                vs = self.werte.get(feld)
                art = (
                    "keine Regel"
                    if not regel
                    else (
                        f"Regel {regel.get('lage')}"
                        + (
                            " mit Anker " + " ".join(maskieren(a) for a in regel["anker"])
                            if regel.get("anker")
                            else ""
                        )
                        + (" (ohne Bereich)" if regel.get("ohne_bereich") else "")
                    )
                )
                st = vs.status if vs else "–"
                form = maskieren(vs.wert) if vs and vs.wert else "leer"
                out.append(
                    f"  {feld}: {art}; Status {st}; Wert {form}"
                    + (f"; {vs.hinweis}" if vs and vs.hinweis and vs.status != "erkannt" else "")
                )
        return "\n".join(out)

    def bereich_setzen(
        self, feld: str, seite: int, x0: float, top: float, x1: float, bottom: float
    ) -> Vorschlag:
        """„Bereich ziehen“: alle Wörter im Rahmen sind der Wert (mehrere Wörter oder Zeilen, ohne Beschriftungs-
        Logik). Die Vorlage merkt sich den Rahmen (Regel „bereich“, relativ zur nächsten Beschriftung)."""
        zs = [z for z in self.zeilen if z.seite == seite]
        zeilen_ws = pdferkennung.woerter_im_bereich(zs, x0, top, x1, bottom)
        vs = self.werte[feld]
        if not zeilen_ws:
            vs.hinweis = "Im Rahmen steht kein Text."
            return vs
        ws = [w for z in zeilen_ws for w in z]
        self.setzen(feld, " ".join(_text(z) for z in zeilen_ws), None)
        vs.woerter = ws
        vs.bereich = (seite, (x0, top, x1, bottom))
        if vs.hinweis.startswith(("Nicht in der PDF", "Wert in der PDF anklicken")):
            vs.hinweis = ""
        return vs

    def anschrift_setzen(
        self,
        seite: int,
        rahmen: tuple[float, float, float, float] | None = None,
        woerter: list[Wort] | None = None,
    ) -> dict[str, str]:
        """„Anschrift als Block“: Rahmen um die Käuferanschrift – oder die per Strg+Klick gewählten Zeilen
        (``woerter``) – in Name, Adresszusatz, Straße, PLZ und Ort zerlegen und eintragen. -> zerlegte Teile."""
        if woerter:
            ws = [w for w in woerter if w.seite == seite]
            rahmen = pdferkennung.rahmen_um(ws)
            zeilen_ws = pdferkennung._zeilen_von(ws)
            teile = pdferkennung.anschrift_teilen([_text(z) for z in zeilen_ws])
        else:
            zs = [z for z in self.zeilen if z.seite == seite]
            teile, zeilen_ws = pdferkennung.anschrift_im_rahmen(
                zs, rahmen, f"Rahmen S. {seite + 1}"
            )
            if zeilen_ws:  # verlängert bis „PLZ Ort“ / Ort neben der PLZ: Rahmen mitziehen
                ws = [w for z in zeilen_ws for w in z]
                r2 = pdferkennung.rahmen_um(ws)
                rahmen = (
                    min(rahmen[0], r2[0]),
                    min(rahmen[1], r2[1]),
                    max(rahmen[2], r2[2]),
                    max(rahmen[3], r2[3]),
                )
        self.anschrift_block = None
        if not zeilen_ws or not teile:
            return {}
        self.anschrift_hinweise = pdferkennung.anschrift_brueche(zeilen_ws)
        for f in (*pdferkennung.BLOCKFELDER, *KAEUFER_NEBENFELDER):
            t = teile.get(f, "")
            if f not in self.werte:
                continue
            vs = self.setzen(f, t, None)
            vs.woerter = (
                next((z for z in zeilen_ws if t and (t in _text(z) or _text(z) in t)), [])
                if t
                else []
            )
            vs.hinweis = self.anschrift_hinweise.get(
                f, ""
            )  # Wert gilt (selbst gezogen), Hinweis zum Prüfen
        self.anschrift_block = (seite, tuple(round(v, 1) for v in rahmen), teile)
        return teile

    def bereiche(self) -> dict[str, tuple]:
        """Felder mit gezogenem Rahmen -> (Seite, Rahmen, Block?) für ``pdferkennung.lernen``."""
        out = {}
        block = (
            self.anschrift_block or self._block_vorschlag
        )  # Name über zwei Zeilen: Block statt Einzelfelder
        if block:
            seite, rahmen, teile = block
            if all(
                norm(self.werte[f].wert) == norm(teile.get(f, "")) for f in pdferkennung.BLOCKFELDER
            ):
                out[pdferkennung.ANSCHRIFT_BLOCK] = (seite, rahmen, True)
        for f, vs in self.werte.items():
            if vs.bereich and vs.status == "erkannt":
                if f == "leistung":
                    f = "BG-14" if isinstance(self.wert(f), tuple) else "BT-72"
                out[f] = (vs.bereich[0], vs.bereich[1], False)
        return out

    def stellen(self) -> dict[str, list[Wort]]:
        """Werte, die der Nutzer angeklickt hat (über ihre Beschriftung oder direkt) -> Fundstelle des Werts. Die
        Vorlage lernt dann genau diese Stelle (Anker = Beschriftung), auch wenn die Beschriftung kein bekanntes
        Schlüsselwort ist – und auch außerhalb des Bereichs des Felds (dann seitenweit, ``ohne_bereich``)."""
        out = {}
        for f, vs in self.werte.items():
            if (vs.beschriftung or vs.geklickt) and vs.woerter and vs.status == "erkannt":
                if f == "leistung":
                    f = "BG-14" if isinstance(self.wert(f), tuple) else "BT-72"
                out[f] = vs.woerter
        return out

    def profil_waehlen(self, prof: dict | None) -> None:
        """Schritt 1: bekannten Absender wählen (neues Layout eines bekannten Absenders) oder ``None`` = neuer
        Absender aus dem Druck. Eine gefundene Vorlage bleibt nur, wenn sie zu diesem Profil gehört."""
        if prof is self.profil:
            return
        if prof is not None:
            self.absender = Absender.aus_bloecken(prof.get("verkaeufer"), prof.get("zahlung"))
            self.absender_neu = False
        else:
            self.absender = erkennen_aus_zeilen(self._ohne_anschriftfeld())
            self.absender_neu = True
            self._absender_ergaenzen()
        if self.vorlage is not None:
            self.vorlage = None  # Vorlage gehörte zum alten Profil: neues Layout lernen
        self.profil = prof
        self.kaeufer_neu_vorschlagen()

    def absender_geaendert(self) -> bool:
        if self.profil is None:
            return True
        alt = Absender.aus_bloecken(self.profil.get("verkaeufer"), self.profil.get("zahlung"))
        return alt != self.absender

    def fortschritt(self) -> tuple[int, int]:
        """-> (Rechnungen in Folge ohne Korrektur, nötige Anzahl) der Vorlage dieser PDF."""
        return fortschritt(self.vorlage, self.profil)


def _spalte_fuer(text: str) -> str | None:
    t = norm(text).replace("€", "").replace("eur", "").strip(" ()")
    if not t:
        return None
    for rx, name in _KOPFWORTE:
        if re.search(rx, t):
            return name
    return None


def _freie_luecken(woerter: list[Wort], x0: float, x1: float) -> list[tuple[float, float]]:
    """x-Bereiche, in denen in keiner Zeile ein Wort steht."""
    belegt = sorted((w.x0, w.x1) for w in woerter)
    frei, pos = [], x0
    for a, b in belegt:
        if a > pos + 1:
            frei.append((pos, a))
        pos = max(pos, b)
    if x1 > pos + 1:
        frei.append((pos, x1))
    return frei


# ---------------------------------------------------------------- Profil und Fortschritt
def fortschritt(v: dict | None, prof: dict | None) -> tuple[int, int]:
    ab = pdferkennung.einstellungen(prof or {})["nur_pdf_ab"]
    n = int(((v or {}).get("statistik") or {}).get("folge_treffer", 0))
    return min(n, ab), ab


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.casefold())
    s = s.replace("ß", "ss")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\b(gmbh|mbh|ag|kg|ohg|gbr|ug|co|e\.?\s?k\.?)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] or "absender"


def ziel_tage(bedingung: str | None) -> int | None:
    """Netto-Zahlungsziel aus der Zahlungsbedingung („14 Tage 2 % Skonto, 30 Tage netto“ -> 30)."""
    return zahlungsziel.netto_tage(bedingung)


def profil_daten(a: Absender, tage: int | None = None) -> dict:
    vk, zb = a.bloecke()
    return {
        "profil": _slug(a.name),
        "quelle": "pdf",
        "name": a.name,
        "verkaeufer": vk,
        "zahlung": {
            **zb,
            "ziel_tage": tage or 14,
            "bedingungen": "Zahlbar innerhalb von {zahlungsziel_tage} Tagen ohne Abzug.",
        },
        "pdf_erkennung": {"nur_pdf": False, "nur_pdf_ab": 5},
    }


class _Verworfen(Exception):
    """Nachprüfung hat die erzeugte Rechnung verworfen."""


def erste_meldung(hinweise: list[str]) -> str:
    """Für den Toast: der erste Hinweis, der wirklich aufhält (FEHLER/PRUEFEN), ohne Stufen-Präfix.
    INFO-Zeilen wie „Kontrollwert … stimmt“ sind Erfolgsmeldungen und gehören nie in einen Fehler-Toast."""
    for stufe in ("FEHLER: ", "PRUEFEN: ", "WARNUNG: "):
        for h in hinweise:
            if h.startswith(stufe):
                return h[len(stufe) :]
    return ""


def profil_anlegen(
    a: Absender, k: Konfig, konfig_pfad: Path | None = None, tage: int | None = None
) -> dict:
    """Neues Nur-PDF-Profil ``profil-<name>.yaml`` neben der Konfiguration; trägt es in ``k`` (und, wenn
    ``konfig_pfad`` angegeben ist, auch in die Konfigurationsdatei) ein."""
    from .konfig import lade_datei

    d = profil_daten(a, tage)
    basis = k.basis
    datei = basis / f"profil-{d['profil']}.yaml"
    n = 2
    while datei.exists():
        datei = basis / f"profil-{d['profil']}-{n}.yaml"
        d["profil"] = f"{_slug(a.name)}-{n}"
        n += 1
    _yaml_schreiben(datei, d)
    prof = lade_datei(datei)
    prof["_basis"], prof["_datei"] = datei.parent, str(datei)
    prof.setdefault("quelle", "pdf")
    k.pdf_profile.append(prof)
    liste = list(k.roh.get("pdf_profile") or [])
    liste.append(datei.name)
    k.roh["pdf_profile"] = liste
    if konfig_pfad is not None:
        konfig_eintragen(Path(konfig_pfad), "pdf_profile", liste)
    log.info("Neues Profil angelegt: %s", datei)
    return prof


def profil_absender_schreiben(prof: dict, a: Absender) -> None:
    """Geänderte Absenderdaten ins Profil zurückschreiben (Kommentare bleiben, wenn ruamel da ist)."""
    vk, zb = a.bloecke()
    datei = Path(prof["_datei"])
    from .konfig import lade_datei

    roh = lade_datei(datei)
    roh["verkaeufer"] = {**(roh.get("verkaeufer") or {}), **vk}
    if not a.kleinunternehmer:
        roh["verkaeufer"].pop("kleinunternehmer", None)
    roh["zahlung"] = {**(roh.get("zahlung") or {}), **zb}
    _yaml_schreiben(datei, roh)
    prof["verkaeufer"], prof["zahlung"] = roh["verkaeufer"], roh["zahlung"]


def nur_pdf_schalten(prof: dict, an: bool) -> None:
    """„Automatisch, ohne Nachfrage“ im Profil speichern."""
    datei = Path(prof["_datei"])
    from .konfig import lade_datei

    roh = lade_datei(datei)
    roh["pdf_erkennung"] = {**(roh.get("pdf_erkennung") or {}), "nur_pdf": bool(an)}
    _yaml_schreiben(datei, roh)
    prof["pdf_erkennung"] = {**(prof.get("pdf_erkennung") or {}), "nur_pdf": bool(an)}


_KOPF_PROFIL = (
    "# Profil für Rechnungen ohne CSV (Nur PDF), angelegt vom Anlern-Assistenten.\n"
    "# Die gelernte Vorlage liegt im Ordner angelernt/. Absender in den Einstellungen ändern.\n"
)


def _yaml_schreiben(datei: Path, roh: dict) -> None:
    if not datei.exists():  # neue Datei: ohne Kommentare der Startkonfiguration
        import yaml

        dateien.schreiben(
            datei, _KOPF_PROFIL + yaml.safe_dump(roh, allow_unicode=True, sort_keys=False)
        )
        return
    try:
        from .gui.orte import speichern

        speichern(datei, roh)
        return
    except ImportError:
        pass
    import yaml

    dateien.schreiben(datei, yaml.safe_dump(roh, allow_unicode=True, sort_keys=False))


def konfig_eintragen(konfig_pfad: Path, schluessel: str, wert) -> None:
    from .konfig import lade_datei

    roh = lade_datei(konfig_pfad)
    roh[schluessel] = wert
    _yaml_schreiben(konfig_pfad, roh)


def warteschlange(k: Konfig) -> list[Path]:
    """PDFs, die auf den Assistenten warten (älteste zuerst)."""
    if not k.anlernen.is_dir():
        return []
    return sorted(
        (p for p in k.anlernen.iterdir() if p.suffix.lower() == ".pdf"),
        key=lambda p: p.stat().st_mtime,
    )


def in_warteschlange(k, dateien: list[Path]) -> list[Path]:
    """Gewählte PDFs in den Anlern-Ordner kopieren (die Originale bleiben, wo sie sind)."""
    k.anlernen.mkdir(parents=True, exist_ok=True)
    out = []
    for d in dateien:
        ziel = k.anlernen / d.name
        if Path(d).resolve().parent != k.anlernen.resolve():
            n = 2
            while ziel.exists():
                ziel = k.anlernen / f"{d.stem}-{n}{d.suffix}"
                n += 1
            shutil.copyfile(d, ziel)  # ohne Attribute: ein schreibgeschütztes Original bleibt es
            st = Path(d).stat()  # nicht in der Warteschlange; Zeitstempel = Reihenfolge
            os.utime(ziel, (st.st_atime, st.st_mtime))
        out.append(ziel)
    return out


def maskieren(text: str) -> str:
    """Form eines Wortes ohne Inhalt: Buchstaben -> a/A, Ziffern -> 9, alles andere bleibt (für die Diagnose)."""
    return "".join(
        "9" if ch.isdigit() else ("A" if ch.isupper() else "a") if ch.isalpha() else ch
        for ch in text
    )
