# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Absender (Verkäufer) aus dem Rechnungsdruck erkennen oder aus einer CSV-Zeile übernehmen.

Der Absender gilt entweder für alle Rechnungen (Block ``absender``/``zahlung`` der Konfiguration) oder für
ein Profil (Blöcke ``verkaeufer``/``zahlung`` im Profil). Hier nur: Werte finden, umwandeln, prüfen."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, fields

from .anschrift import PLZ_ORT, anschrift_zerlegen, strasse_mit_nr
from .pflichtpruefung import iban_gueltig
from .werte import dekodieren, ohne_steuerzeichen, trennzeichen_erkennen

# Spalten der Importdatei (docs/csv-format.md, Abschnitt „Absender importieren“) -> Feld; Groß/Klein egal
CSV_SPALTEN = {
    "name": "name",
    "firma": "name",
    "strasse": "strasse",
    "straße": "strasse",
    "plz": "plz",
    "ort": "ort",
    "ust-idnr": "ust_id",
    "ust-id": "ust_id",
    "ustidnr": "ust_id",
    "steuernummer": "steuernummer",
    "iban": "iban",
    "bic": "bic",
    "telefon": "telefon",
    "e-mail": "email",
    "email": "email",
    "register": "register",
    "registernummer": "register",
    "mail": "email",
    "tel": "telefon",
    "stnr": "steuernummer",
    "st-nr": "steuernummer",
    "ustid": "ust_id",
    "zusatz": "zusatz",
    "adresszusatz": "zusatz",
    "adresszeile 2": "zusatz",
    "adresszeile2": "zusatz",
}
CSV_KOPF = "Name;Strasse;PLZ;Ort;USt-IdNr;Steuernummer;IBAN;BIC;Telefon;E-Mail;Register"


@dataclass
class Absender:
    name: str = ""
    strasse: str = ""
    zusatz: str = ""  # Adresszeile 2 (BT-36), freiwillig
    plz: str = ""
    ort: str = ""
    ust_id: str = ""
    steuernummer: str = ""
    iban: str = ""
    bic: str = ""
    telefon: str = ""
    email: str = ""
    register: str = ""
    kleinunternehmer: bool = False  # ab 0.9.7: § 19 UStG (Schalter am Absender)

    def gefunden(self) -> list[str]:
        return [f.name for f in fields(self) if getattr(self, f.name)]

    def fehlt(self) -> list[str]:
        """Pflicht: Name, Anschrift, USt-IdNr. oder Steuernummer, IBAN (Überweisung)."""
        f = [n for n in ("name", "strasse", "plz", "ort", "iban") if not getattr(self, n)]
        if not (self.ust_id or self.steuernummer):
            f.append("ust_id")
        return f

    # -- Umwandeln: Profil-/Konfigurationsblöcke
    def bloecke(self) -> tuple[dict, dict]:
        """-> (verkaeufer-Block, zahlung-Block) wie in Profil/Konfiguration."""
        vk: dict = {
            "name": self.name,
            "anschrift": {"strasse": self.strasse, "plz": self.plz, "ort": self.ort},
        }
        if self.zusatz:
            vk["anschrift"]["zusatz"] = self.zusatz
        for schl in ("ust_id", "steuernummer", "register"):
            if getattr(self, schl):
                vk[schl] = getattr(self, schl)
        if self.kleinunternehmer:
            vk["kleinunternehmer"] = True
        kon = {k: w for k, w in (("telefon", self.telefon), ("email", self.email)) if w}
        if kon:
            vk["kontakt"] = {"name": self.name, **kon}
            if self.email:
                vk["elektronische_adresse"] = self.email
        zb = {"iban": self.iban.replace(" ", "")}
        if self.bic:
            zb["bic"] = self.bic
        return vk, zb

    @classmethod
    def aus_bloecken(cls, vk: dict | None, zb: dict | None) -> "Absender":
        vk, zb = vk or {}, zb or {}
        adr, kon = vk.get("anschrift") or {}, vk.get("kontakt") or {}
        s = lambda d, k: ohne_steuerzeichen(str(d.get(k) or ""))  # noqa: E731 – ältere Profile: „(CID:10)“
        return cls(
            name=s(vk, "name"),
            strasse=s(adr, "strasse"),
            zusatz=s(adr, "zusatz"),
            plz=s(adr, "plz"),
            ort=s(adr, "ort"),
            ust_id=s(vk, "ust_id"),
            steuernummer=s(vk, "steuernummer"),
            iban=s(zb, "iban"),
            bic=s(zb, "bic"),
            telefon=s(kon, "telefon"),
            email=s(kon, "email") or s(vk, "elektronische_adresse"),
            register=s(vk, "register"),
            kleinunternehmer=bool(vk.get("kleinunternehmer")),
        )


# ---------------------------------------------------------------- Aus dem Druck erkennen
_FIRMA = r"(?:GmbH(?:\s?&\s?Co\.?\s?KG)?|mbH|AG|KG|OHG|GbR|UG(?:\s?\(haftungsbeschränkt\))?|e\.\s?K\.|e\.\s?Kfm\.|e\.\s?V\.)"
_TRENNER = re.compile(r"\s*[·•|]\s*|\s+[–*-]\s+")


def _erstes(rx: str, text: str, gruppe: int = 1, flags: int = re.I) -> str:
    m = re.search(rx, text, flags)
    return " ".join(m.group(gruppe).split()) if m else ""


def erkennen_aus_zeilen(zeilen) -> Absender:
    """Zeilen der PDF-Erkennung (mit Abschnitten) -> Absender; Abschnitte werden wie Trenner behandelt."""
    return erkennen([" | ".join(" ".join(w.t for w in s) for s in z.abschnitte) for z in zeilen])


def erkennen(zeilen: list[str]) -> Absender:
    """Absenderangaben aus den Textzeilen eines Drucks (Briefkopf, Absenderzeile, Fußzeile).

    Erkannt wird, was eindeutig aussieht; der Assistent zeigt alles zum Prüfen an."""
    text = "\n".join(zeilen)
    a = Absender()
    m = re.search(r"\bDE\s?(\d{3})\s?(\d{3})\s?(\d{3})\b", text)
    if m:
        a.ust_id = "DE" + "".join(m.groups())
    for m in re.finditer(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b", text):
        if iban_gueltig(m.group(0)):
            a.iban = re.sub(r"\s", "", m.group(0))
            break
    a.bic = _erstes(r"\bBIC[:\s]*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b", text, flags=0)
    a.steuernummer = _erstes(
        r"(?:St\.?\s?-?\s?Nr\.?|Steuer-?nummer|StNr\.?)[:\s]*(\d{2,3}/\d{3,4}/\d{4,5}|\d{10,13})",
        text,
    )
    a.register = _erstes(
        r"((?:Amtsgericht|AG)\s+[^\W\d_][\w.äöüÄÖÜß-]*(?:\s[^\W\d_][\w.]*)?,?\s+HR[AB]\s?\d+\s?[A-Z]?)\b",
        text,
    )
    # § 19 UStG im Druck: Kleinunternehmer (Schalter wird vorbelegt, der Assistent zeigt ihn zum Prüfen)
    a.kleinunternehmer = bool(
        re.search(r"§\s*19\b(?:\s*Abs\.?\s*\d)?\s*UStG|Kleinunternehmer", text, re.I)
    )
    a.telefon = _erstes(r"\bTel(?:efon)?\.?[:\s]*(\+?[\d][\d /()-]{5,}\d)", text)
    a.email = _erstes(r"\b([\w.+-]+@[\w-]+(?:\.[\w-]+)+)\b", text)

    # Name + Anschrift: Abschnitt mit Rechtsform; bevorzugt eine Zeile mit Trennern (Absenderzeile/Fußzeile)
    kandidaten = []
    for zi, z in enumerate(zeilen):
        teile = [t.strip() for t in _TRENNER.split(z) if t.strip()]
        for ti, t in enumerate(teile):
            if re.search(rf"\s{_FIRMA}$", t) and len(t) <= 70:
                rest = teile[ti + 1 :]
                gewicht = (
                    (len(teile) > 1) * 2
                    + (sum(1 for z2 in zeilen if t in z2) > 1)
                    + 3 * any(PLZ_ORT.match(r) for r in rest)
                )
                kandidaten.append((-gewicht, zi, t, rest))
    if kandidaten:
        _, zi, a.name, rest = min(kandidaten)
        if not rest:  # Briefkopf mehrzeilig: Anschrift in den nächsten Zeilen
            rest = [
                t.strip() for z in zeilen[zi + 1 : zi + 6] for t in _TRENNER.split(z) if t.strip()
            ]
            # Name über mehrere Zeilen: die Zeile darüber endet offen („Beispiel Werkzeug- und“, „… &“)
            for z in reversed(zeilen[max(0, zi - 2) : zi]):
                vor = " ".join(z.split())
                if (
                    vor
                    and not _TRENNER.search(vor)
                    and re.search(r"(?:[-&+,]|\bund)$", vor)
                    and len(vor) <= 60
                ):
                    a.name = f"{vor} {a.name}"
                else:
                    break
        _anschrift_von_unten(a, rest)
    return a


def _anschrift_von_unten(a: Absender, rest: list[str]) -> None:
    """Teile nach dem Namen mit derselben festen Regel wie beim Käufer (``anschrift.anschrift_zerlegen``):
    erste Zeile „PLZ Ort“, die Zeile mit Inhalt direkt darüber ist die Straße, Zeilen zwischen Name und Straße
    gehören zum Namen. Ohne Straße über der PLZ zählt die erste Straßenzeile darunter."""
    rest = [" ".join(t.split()) for t in rest if t.strip()]
    plz_i = next((i for i, t in enumerate(rest) if PLZ_ORT.match(t)), None)
    if plz_i is None:
        a.strasse = next((t for t in rest if strasse_mit_nr(t)), "")
        return
    teile, _ = anschrift_zerlegen(rest[: plz_i + 1], zusatz=False)
    a.plz, a.ort = teile.get("BT-53", ""), teile.get("BT-52", "")
    a.strasse = teile.get("BT-50", "") or next(
        (t for t in rest[plz_i + 1 :] if strasse_mit_nr(t)), ""
    )
    if teile.get("BT-44"):
        a.name = " ".join([a.name, teile["BT-44"]]).strip()


# ---------------------------------------------------------------- Aus einer CSV-Datei übernehmen
def aus_csv(daten: bytes) -> Absender:
    """Erste Datenzeile einer CSV mit Kopfzeile (Spalten siehe ``CSV_KOPF``) -> Absender.

    ValueError mit deutscher Begründung, wenn keine bekannte Spalte oder keine Datenzeile da ist."""
    text, _ = dekodieren(daten)
    trenn = trennzeichen_erkennen(text)
    reader = csv.DictReader(text.splitlines(), delimiter=trenn)
    spalten = {s: CSV_SPALTEN.get((s or "").strip().lower()) for s in (reader.fieldnames or [])}
    if not any(spalten.values()):
        raise ValueError(f"Keine bekannte Spalte gefunden. Erwartet: {CSV_KOPF}")
    zeile = next(reader, None)
    if not zeile:
        raise ValueError("Die Datei enthält nur die Kopfzeile.")
    a = Absender()
    for s, feld in spalten.items():
        if feld and (zeile.get(s) or "").strip():
            setattr(a, feld, " ".join(zeile[s].split()))
    a.iban = a.iban.replace(" ", "")
    return a
