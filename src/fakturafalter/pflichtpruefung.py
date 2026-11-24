# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Pflichtangaben und Plausibilität vor dem Erzeugen (regelbasiert).

Warum eigene Prüfungen? Eine ZUGFeRD-Datei (Profil EN16931) kann die Validatoren mit 0 Fehlern bestehen,
obwohl sie umsatzsteuerlich keine ordnungsgemäße Rechnung ist: EN 16931 verlangt z. B. bei der Anschrift
nur den Ländercode und kein Leistungsdatum. § 14 Abs. 4 UStG verlangt mehr, und nach dem BMF-Schreiben
vom 15.10.2025 (Rn. 35) müssen die Angaben im XML stehen. Details: docs/recherche/pflichtangaben-pruefmatrix.md.

Aufbau:
- Jede Regel ist eine Funktion ``(Rechnung, Kontext) -> Iterable[(feld, text)]`` und trägt einen
  ``umfang``: ``alle`` | ``inland`` | ``ausland`` | ``xrechnung``.
- Version 1 prüft ``alle`` + ``inland`` (Käufer und Verkäufer in Deutschland, ZUGFeRD EN16931,
  keine Leitweg-ID). Regeln für ``ausland``/``xrechnung`` sind als TODO-Stubs angelegt und inaktiv.
- Jeder Treffer hält die Rechnung an (Stufe ``pruefen`` -> Ordner „Zu prüfen“). Gibt es zum selben Feld
  schon einen anhaltenden Hinweis (z. B. aus ``aufbau``), wird kein zweiter angehängt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

from .codelisten import EINHEITEN, WAEHRUNGEN
from .modell import Partei, Rechnung

STUFE = "pruefen"
UMFAENGE_V1 = frozenset({"alle", "inland"})

Treffer = tuple[str, str]                      # (feld, text)


@dataclass
class Kontext:
    heute: date = field(default_factory=date.today)
    bekannte_nummern: frozenset[str] = frozenset()     # BT-1 aus früheren Läufen (protokoll.tsv, Status ok)
    nummernkreise: dict = field(default_factory=dict)  # ab 0.9.5: {kreis: nummernkreis.Kreis}
    lauf_nummern: frozenset[str] = frozenset()         # BT-1 der Rechnungen im selben Lauf (Lückenwarnung)
    umfaenge: frozenset[str] = UMFAENGE_V1


@dataclass(frozen=True)
class Regel:
    id: str
    umfang: str
    beschreibung: str
    pruefe: Callable[[Rechnung, Kontext], Iterable[Treffer]]
    aktiv: bool = True


REGELN: list[Regel] = []


def regel(id: str, umfang: str, beschreibung: str, aktiv: bool = True):
    def deko(fn):
        REGELN.append(Regel(id, umfang, beschreibung, fn, aktiv))
        return fn
    return deko


# ------------------------------------------------------------------ Hilfen (auch für Tests/GUI nutzbar)
def ust_id_de_gueltig(ust_id: str) -> bool:
    """DE + 9 Ziffern, Prüfziffer nach ISO 7064 MOD 11,10 (Verfahren laut BZSt)."""
    u = re.sub(r"\s", "", ust_id or "").upper()
    if not re.fullmatch(r"DE\d{9}", u):
        return False
    produkt = 10
    for z in u[2:10]:
        summe = (int(z) + produkt) % 10 or 10
        produkt = (2 * summe) % 11
    pz = 11 - produkt
    return (0 if pz == 10 else pz) == int(u[10])


def gtin_gueltig(nr: str) -> bool:
    """GTIN-8/12/13/14, Prüfziffer nach GS1 Mod 10 (ISO/IEC 15420)."""
    z = re.sub(r"\s", "", nr or "")
    if not re.fullmatch(r"\d{8}|\d{12,14}", z):
        return False
    ziffern = [int(c) for c in z]
    s, faktor = 0, 3
    for d in reversed(ziffern[:-1]):
        s += d * faktor
        faktor = 1 if faktor == 3 else 3
    return (10 - s % 10) % 10 == ziffern[-1]


def steuernummer_plausibel(stnr: str) -> bool:
    """Deutsche Steuernummer: Länderformat (10–11 Ziffern, z. B. 12/345/67890) oder bundeseinheitlich (13)."""
    ziffern = re.sub(r"[\s/\-]", "", stnr or "")
    return ziffern.isdigit() and 10 <= len(ziffern) <= 13


def iban_gueltig(iban: str) -> bool:
    """ISO 13616: Länderformat grob, Prüfsumme mod 97 == 1; DE-IBAN genau 22 Stellen."""
    i = re.sub(r"\s", "", iban or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", i):
        return False
    if i.startswith("DE") and len(i) != 22:
        return False
    zahl = "".join(str(int(c, 36)) for c in i[4:] + i[:4])
    return int(zahl) % 97 == 1


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")


def email_gueltig(s: str) -> bool:
    return bool(_EMAIL.fullmatch((s or "").strip()))


def bekannte_nummern(protokoll: Path) -> frozenset[str]:
    """Rechnungsnummern, die laut protokoll.tsv schon erfolgreich erzeugt wurden (alle Läufe)."""
    if not Path(protokoll).exists():
        return frozenset()
    aus = set()
    for z in Path(protokoll).read_text(encoding="utf-8", errors="replace").splitlines():
        t = z.split("\t")
        if len(t) >= 3 and t[1] == "ok" and t[2].strip():
            aus.add(t[2].strip())
    return frozenset(aus)


def _leer(s) -> bool:
    return not str(s or "").strip()


def _rolle(verkaeufer: bool) -> tuple[str, dict[str, str]]:
    if verkaeufer:
        return "Verkäufer", {"name": "BT-27", "strasse": "BT-35", "ort": "BT-37", "plz": "BT-38", "land": "BT-40"}
    return "Käufer", {"name": "BT-44", "strasse": "BT-50", "ort": "BT-52", "plz": "BT-53", "land": "BT-55"}


GESETZ_NR1 = "Pflichtangabe nach § 14 Abs. 4 Nr. 1 UStG"


def _partei_pruefen(p: Partei, verkaeufer: bool) -> Iterable[Treffer]:
    rolle, bt = _rolle(verkaeufer)
    a = p.anschrift
    for attr, name, wert in (("name", "Name", p.name), ("strasse", "Straße und Hausnummer", a.strasse),
                             ("plz", "Postleitzahl", a.plz), ("ort", "Ort", a.ort)):
        if _leer(wert):
            yield bt[attr], f"{rolle} – {name} ({bt[attr]}) fehlt. {GESETZ_NR1}."


# ------------------------------------------------------------------ Regeln: alle Umfänge
@regel("nummer", "alle", "Rechnungsnummer BT-1 vorhanden")
def _nummer(r: Rechnung, k: Kontext):
    if _leer(r.nummer):
        yield "BT-1", "Rechnungsnummer (BT-1) fehlt. Pflichtangabe nach § 14 Abs. 4 Nr. 4 UStG."


@regel("nummer_muster", "alle", "Rechnungsnummer passt zum Prüfmuster der Belegart (Einstellungen → Ausgabe)")
def _nummer_muster(r: Rechnung, k: Kontext):
    from . import nummernkreis as nk

    kreis = k.nummernkreise.get(nk.kreis_von(r.art))
    if not kreis or not kreis.pruefmuster or _leer(r.nummer):
        return
    name = "Gutschrift" if nk.kreis_von(r.art) == "gutschrift" else "Rechnung"
    try:
        ok = nk.passt(r.nummer, kreis.pruefmuster)
    except (nk.MusterFehler, re.error) as e:
        yield "BT-1", f"Prüfmuster „{kreis.pruefmuster}“ ({name}) ist ungültig: {e}. Einstellungen → Ausgabe."
        return
    if not ok:
        yield "BT-1", (f"Rechnungsnummer {r.nummer} passt nicht zum Prüfmuster „{kreis.pruefmuster}“ ({name}). "
                       "Fakturafalter ändert die Nummer nicht – bitte im ERP bzw. unter Einstellungen → Ausgabe "
                       "prüfen.")


@regel("nummer_einmalig", "alle", "Rechnungsnummer über alle Läufe einmalig (protokoll.tsv)")
def _nummer_einmalig(r: Rechnung, k: Kontext):
    if r.nummer and r.nummer in k.bekannte_nummern:
        yield "BT-1", (f"Rechnungsnummer {r.nummer} (BT-1) wurde schon einmal erzeugt (laut Protokoll). "
                       "Sie muss einmalig sein, § 14 Abs. 4 Nr. 4 UStG.")


@regel("datum", "alle", "Rechnungsdatum BT-2 vorhanden und nicht in der Zukunft")
def _datum(r: Rechnung, k: Kontext):
    if not r.datum:
        yield "BT-2", "Rechnungsdatum (BT-2) fehlt. Pflichtangabe nach § 14 Abs. 4 Nr. 3 UStG."
    elif r.datum > k.heute:
        yield "BT-2", f"Rechnungsdatum (BT-2) {r.datum:%d.%m.%Y} liegt in der Zukunft."


@regel("waehrung", "alle", "Währung BT-5 nach ISO 4217")
def _waehrung(r: Rechnung, k: Kontext):
    w = (r.waehrung or "").strip()
    if w not in WAEHRUNGEN:
        yield "BT-5", f"Währung (BT-5) „{w}“ ist kein ISO-4217-Code (z. B. EUR)."


@regel("leistungszeit", "alle", "Leistungsdatum BT-72 oder Leistungszeitraum BG-14 vorhanden")
def _leistungszeit(r: Rechnung, k: Kontext):
    von, bis = r.leistung_von, r.leistung_bis
    if not (r.leistungsdatum or von or bis):
        yield "BT-72", ("Leistungsdatum (BT-72) bzw. Leistungszeitraum (BT-73/BT-74) fehlt. Pflichtangabe nach "
                        "§ 14 Abs. 4 Nr. 6 UStG; der Kalendermonat genügt (§ 31 Abs. 4 UStDV).")
    if von and bis and bis < von:
        yield "BG-14", f"Leistungszeitraum: Ende (BT-74) {bis:%d.%m.%Y} liegt vor Beginn (BT-73) {von:%d.%m.%Y}."


@regel("parteien", "alle", "Name und vollständige Anschrift von Verkäufer und Käufer")
def _parteien(r: Rechnung, k: Kontext):
    yield from _partei_pruefen(r.verkaeufer, True)
    yield from _partei_pruefen(r.kaeufer, False)


@regel("verkaeufer_steuer_id", "alle", "USt-IdNr. BT-31 oder Steuernummer BT-32 des Verkäufers")
def _verkaeufer_steuer_id(r: Rechnung, k: Kontext):
    v = r.verkaeufer
    if _leer(v.ust_id) and _leer(v.steuernummer):
        yield "BT-31", ("Verkäufer – USt-IdNr. (BT-31) oder Steuernummer (BT-32) fehlt. "
                        "Pflichtangabe nach § 14 Abs. 4 Nr. 2 UStG.")
        return
    if not _leer(v.ust_id) and v.ust_id.strip().upper().startswith("DE") and not ust_id_de_gueltig(v.ust_id):
        yield "BT-31", (f"Verkäufer – USt-IdNr. (BT-31) „{v.ust_id}“ ist ungültig "
                        "(Aufbau DE + 9 Ziffern, Prüfziffer nach BZSt stimmt nicht).")
    if not _leer(v.steuernummer) and not steuernummer_plausibel(v.steuernummer):
        yield "BT-32", f"Verkäufer – Steuernummer (BT-32) „{v.steuernummer}“ hat kein gültiges Format (10–13 Ziffern)."
    if _leer(v.ust_id) and _leer(v.register):
        # BR-CO-26: BT-29, BT-30 oder BT-31 nötig – nur Steuernummer (BT-32) reicht der EN 16931 nicht.
        yield "BT-30", ("Verkäufer hat nur eine Steuernummer: Dann ist die Registernummer (BT-30, z. B. "
                        "„Amtsgericht … HRB …“) oder die USt-IdNr. (BT-31) nötig (EN 16931, BR-CO-26).")


@regel("kaeufer_ust_id", "alle", "USt-IdNr. BT-48 des Käufers: Prüfziffer wie BT-31")
def _kaeufer_ust_id(r: Rechnung, k: Kontext):
    u = r.kaeufer.ust_id
    if not _leer(u) and u.strip().upper().startswith("DE") and not ust_id_de_gueltig(u):
        yield "BT-48", (f"Käufer – USt-IdNr. (BT-48) „{u}“ ist ungültig "
                        "(Aufbau DE + 9 Ziffern, Prüfziffer nach BZSt stimmt nicht).")


@regel("positionen", "alle", "Positionen: Bezeichnung, Menge, Einheit, Einzelpreis tatsächlich vorhanden")
def _positionen(r: Rechnung, k: Kontext):
    if not r.positionen:
        yield "BG-25", "Keine Rechnungsposition gefunden (BG-25)."
    for p in r.positionen:
        pre = f"Position {p.nr}"
        if _leer(p.bezeichnung):
            yield f"Pos {p.nr} BT-153", f"{pre} – Bezeichnung (BT-153) fehlt. Pflichtangabe nach § 14 Abs. 4 Nr. 5 UStG."
        if p.menge is None:
            yield f"Pos {p.nr} BT-129", f"{pre} – Menge (BT-129) fehlt. Pflichtangabe nach § 14 Abs. 4 Nr. 5 UStG."
        elif p.menge == 0:
            yield f"Pos {p.nr} BT-129", f"{pre} – Menge (BT-129) ist 0."
        if _leer(p.einheit):
            yield f"Pos {p.nr} BT-130", f"{pre} – Einheit (BT-130) fehlt."
        elif p.einheit not in EINHEITEN:
            yield f"Pos {p.nr} BT-130", f"{pre} – Einheit (BT-130) „{p.einheit}“ ist kein Code nach UN/ECE Rec 20."
        if p.einzelpreis is None:
            yield f"Pos {p.nr} BT-146", f"{pre} – Einzelpreis netto (BT-146) fehlt."
        elif p.einzelpreis < 0:
            yield f"Pos {p.nr} BT-146", f"{pre} – Einzelpreis netto (BT-146) ist negativ (EN 16931, BR-27)."
        if p.preiseinheit is None or p.preiseinheit <= 0:
            yield f"Pos {p.nr} BT-149", f"{pre} – Preiseinheit (BT-149) muss größer als 0 sein."


@regel("email", "alle", "E-Mail-Adressen BT-34/BT-49/BT-43/BT-58 im gültigen Format")
def _email(r: Rechnung, k: Kontext):
    for p, rolle, adr_bt, kon_bt in ((r.verkaeufer, "Verkäufer", "BT-34", "BT-43"),
                                     (r.kaeufer, "Käufer", "BT-49", "BT-58")):
        for wert, bt, was in ((p.elektronische_adresse, adr_bt, "elektronische Adresse"),
                              (p.kontakt_email, kon_bt, "Kontakt-E-Mail")):
            if not _leer(wert) and not email_gueltig(wert):
                yield bt, f"{rolle} – {was} ({bt}) „{wert}“ ist keine gültige E-Mail-Adresse."


@regel("zahlung", "alle", "Überweisung: IBAN gültig; Fälligkeit oder Zahlungsbedingungen")
def _zahlung(r: Rechnung, k: Kontext):
    z = r.zahlung
    if z.art in ("30", "58"):
        if _leer(z.iban):
            yield "BT-84", "Zahlung per Überweisung, aber die IBAN (BT-84) fehlt (EN 16931, BR-61)."
        elif not iban_gueltig(z.iban):
            yield "BT-84", f"IBAN (BT-84) „{z.iban}“ ist ungültig (Prüfsumme oder Länge stimmt nicht)."
    if r.summen.zahlbar > 0 and not z.faellig and _leer(z.bedingungen):
        yield "BT-20", ("Fälligkeitsdatum (BT-9) oder Zahlungsbedingungen (BT-20) fehlen "
                        "(EN 16931, BR-CO-25). Zahlungsziel im Profil/Kundenstamm angeben.")
    if z.faellig and r.datum and z.faellig < r.datum:
        yield "BT-9", f"Fälligkeitsdatum (BT-9) {z.faellig:%d.%m.%Y} liegt vor dem Rechnungsdatum."


@regel("lastschrift", "alle", "SEPA-Lastschrift: Mandatsreferenz BT-89, Gläubiger-ID BT-90, Konto BT-91")
def _lastschrift(r: Rechnung, k: Kontext):
    z = r.zahlung
    if not z.lastschrift:
        return
    if _leer(z.mandat):
        yield "BT-89", "Zahlung per Lastschrift, aber die Mandatsreferenz (BT-89) fehlt."
    if _leer(z.glaeubiger_id):
        yield "BT-90", ("Zahlung per Lastschrift, aber die Gläubiger-ID (BT-90) fehlt – im Absenderprofil "
                        "eintragen (XRechnung BR-DE-30).")
    if _leer(z.lastschrift_iban):
        yield "BT-91", "Zahlung per Lastschrift, aber die IBAN des Kunden (BT-91) fehlt (XRechnung BR-DE-31)."
    elif not iban_gueltig(z.lastschrift_iban):
        yield "BT-91", f"IBAN des Kunden (BT-91) „{z.lastschrift_iban}“ ist ungültig."


@regel("korrektur_bezug", "alle", "Gutschrift/Rechnungskorrektur 381/384 nennt die Ursprungsrechnung (BG-3)")
def _korrektur_bezug(r: Rechnung, k: Kontext):
    if r.art in ("381", "384") and not any(b.nummer.strip() for b in r.bezuege):
        art = "Gutschrift (381)" if r.art == "381" else "Rechnungskorrektur (384)"
        yield "BT-25", (f"{art} ohne Nummer der Ursprungsrechnung (BT-25). Eine Berichtigung muss sich eindeutig "
                        "auf die Rechnung beziehen (§ 31 Abs. 5 UStDV; XRechnung BR-DE-26).")


def _bg15_vorhanden(a) -> bool:
    """Lieferanschrift (BG-15) ist gesetzt, sobald irgendein Adressfeld (inkl. Land) steht."""
    return bool(a) or bool((a.land or "").strip())


@regel("gutschrift_betrag", "alle",
       "Gutschrift/Rechnungskorrektur 381/384 hat einen positiven Rechnungsbetrag (EN 16931, BR-27)")
def _gutschrift_betrag(r: Rechnung, k: Kontext):
    if r.art not in ("381", "384"):
        return
    if r.summen.brutto <= 0:
        art = "Gutschrift (381)" if r.art == "381" else "Rechnungskorrektur (384)"
        yield "BT-112", (f"{art}: Der Rechnungsbetrag ist nicht positiv. In EN 16931 sind die Beträge positiv; "
                         "das Vorzeichen steckt in der Belegart (BR-27).")


@regel("lieferanschrift", "alle", "Lieferanschrift (BG-15): wenn vorhanden, Land (BT-80) sowie Ort und PLZ")
def _lieferanschrift(r: Rechnung, k: Kontext):
    a = r.lieferung.anschrift
    if not _bg15_vorhanden(a):
        return
    if _leer(a.land):
        yield "BT-80", ("Lieferanschrift (BG-15) ohne Land (BT-80). Ist eine Lieferanschrift angegeben, "
                        "muss das Land stehen (EN 16931).")
    if _leer(a.ort):
        yield "BT-77", ("Lieferanschrift (BG-15) ohne Ort (BT-77). Ist eine Lieferanschrift angegeben, "
                        "müssen Ort und Postleitzahl stehen.")
    if _leer(a.plz):
        yield "BT-78", ("Lieferanschrift (BG-15) ohne Postleitzahl (BT-78). Ist eine Lieferanschrift angegeben, "
                        "müssen Ort und Postleitzahl stehen.")
    elif (a.land or "DE").strip().upper() == "DE" and not re.fullmatch(r"\d{5}", a.plz.strip()):
        yield "BT-78", f"Lieferanschrift – Postleitzahl (BT-78) „{a.plz}“ hat nicht 5 Ziffern."


# ------------------------------------------------------------------ Regeln: Inland (Version 1)
NICHT_UNTERSTUETZT = "wird in dieser Version nicht unterstützt (nur Inland, Regelbesteuerung)"


@regel("inland_laender", "inland", "Verkäufer und Käufer in Deutschland")
def _inland_laender(r: Rechnung, k: Kontext):
    for p, verkaeufer in ((r.verkaeufer, True), (r.kaeufer, False)):
        rolle, bt = _rolle(verkaeufer)
        land = (p.anschrift.land or "DE").strip().upper()
        if land != "DE":
            yield bt["land"], f"{rolle} im Ausland (Land {bt['land']} = „{land}“) {NICHT_UNTERSTUETZT}."


@regel("inland_plz", "inland", "Deutsche Postleitzahl hat 5 Ziffern")
def _inland_plz(r: Rechnung, k: Kontext):
    for p, verkaeufer in ((r.verkaeufer, True), (r.kaeufer, False)):
        rolle, bt = _rolle(verkaeufer)
        plz = (p.anschrift.plz or "").strip()
        if plz and not re.fullmatch(r"\d{5}", plz):
            yield bt["plz"], f"{rolle} – Postleitzahl ({bt['plz']}) „{plz}“ hat nicht 5 Ziffern."


@regel("inland_waehrung", "inland", "Rechnungswährung EUR")
def _inland_waehrung(r: Rechnung, k: Kontext):
    w = (r.waehrung or "").strip()
    if w in WAEHRUNGEN and w != "EUR":
        # TODO(ausland): Fremdwährung braucht die Steuer zusätzlich in EUR (BT-6/BT-111, § 16 Abs. 6 UStG).
        yield "BT-5", f"Rechnungswährung {w} (BT-5) {NICHT_UNTERSTUETZT}; nur EUR."


SAETZE_S = (Decimal("19"), Decimal("7"))
_RC_KU = re.compile(r"§\s*13b|13b\s*UStG|§\s*19\b|19\s*(Abs\.?\s*1\s*)?UStG|Kleinunternehmer|Steuerschuldnerschaft",
                    re.IGNORECASE)


@regel("inland_steuer", "inland", "Steuerkategorie und Satz passen zusammen (S 19/7, Z 0 ohne Grund, E 0 mit Grund)")
def _inland_steuer(r: Rechnung, k: Kontext):
    gesehen = set()
    for p in r.positionen:
        st = p.steuer
        key = st.schluessel
        if key in gesehen:
            continue
        gesehen.add(key)
        kat, satz, grund = st.kategorie, st.satz, (st.befreiungsgrund or st.befreiungscode).strip()
        f = f"Pos {p.nr} BT-151"
        txt = f"Steuer {kat} {satz:g} % (Position {p.nr})"
        if kat == "S":
            if satz not in SAETZE_S:
                yield f, f"{txt}: Kategorie S (BT-151) braucht 19 % oder 7 % (BT-152)."
            if grund:
                yield f, f"{txt}: Kategorie S darf keinen Befreiungsgrund (BT-120/121) haben (EN 16931, BR-S-10)."
        elif kat == "Z":
            if satz != 0:
                yield f, f"{txt}: Kategorie Z (Nullsatz) braucht 0 % (BT-152) (EN 16931, BR-Z-05)."
            if grund:
                yield f, f"{txt}: Kategorie Z darf keinen Befreiungsgrund (BT-120/121) haben (EN 16931, BR-Z-10)."
        elif kat == "E":
            if _RC_KU.search(grund):
                yield f, f"{txt}: Kleinunternehmer (§ 19 UStG) bzw. Reverse Charge (§ 13b UStG) {NICHT_UNTERSTUETZT}."
                continue
            if satz != 0:
                yield f, f"{txt}: Kategorie E (steuerfrei) braucht 0 % (BT-152) (EN 16931, BR-E-05)."
            if not grund:
                yield f, (f"{txt}: Kategorie E braucht einen Befreiungsgrund (BT-120/121), § 14 Abs. 4 Nr. 8 UStG "
                          "(EN 16931, BR-E-10).")
        elif kat in ("AE", "K", "G", "O", "L", "M"):
            art = {"AE": "Reverse Charge (§ 13b UStG / Steuerschuldnerschaft des Leistungsempfängers)",
                   "K": "Innergemeinschaftliche Lieferung", "G": "Ausfuhrlieferung",
                   "O": "Nicht steuerbare Leistung", "L": "Kanarische Inseln (IGIC)", "M": "Ceuta/Melilla (IPSI)"}[kat]
            yield f, f"{txt}: {art} (Kategorie {kat}) {NICHT_UNTERSTUETZT}."
        else:
            yield f, f"{txt}: Steuerkategorie „{kat}“ (BT-151) ist unbekannt."


# ------------------------------------------------------------------ Stubs für später (inaktiv)
@regel("ausland_ust_id", "ausland", "TODO: § 14a UStG – USt-IdNr. beider Parteien bei AE/K, BZSt-Länderformate",
       aktiv=False)
def _ausland_ust_id(r: Rechnung, k: Kontext):
    # TODO: AE (BR-AE-02: BT-31/32 + BT-48 oder BT-47, Hinweis „Steuerschuldnerschaft des Leistungsempfängers“),
    #       K (BR-IC-02/11/12: BT-31 + BT-48, BT-72/BG-14 und Lieferland BT-80 – BG-15 fehlt noch in cii.py),
    #       ausländische USt-IdNr. mit ISO-Präfix (BR-CO-09, Griechenland EL), Länder BT-40/BT-55 gegen ISO 3166.
    return ()


@regel("ausland_waehrung", "ausland", "TODO: Fremdwährung mit Steuerbetrag in EUR (BT-6/BT-111)", aktiv=False)
def _ausland_waehrung(r: Rechnung, k: Kontext):
    return ()


@regel("xrechnung_leitweg", "xrechnung", "TODO: Leitweg-ID BT-10 (Format + Prüfziffer ISO 7064 Mod 97-10)", aktiv=False)
def _xrechnung_leitweg(r: Rechnung, k: Kontext):
    # TODO: BR-DE-15 (BT-10 Pflicht), bei Behörden kein Rückfall auf die Kundennummer.
    return ()


@regel("xrechnung_kontakt", "xrechnung", "TODO: BT-34, BT-49, Verkäuferkontakt BG-6, BG-16 (BR-DE-1/2/5/6/7)",
       aktiv=False)
def _xrechnung_kontakt(r: Rechnung, k: Kontext):
    return ()


# ------------------------------------------------------------------ Ausführen
def aktive_regeln(k: Kontext) -> list[Regel]:
    return [g for g in REGELN if g.aktiv and g.umfang in k.umfaenge]


def pruefen(r: Rechnung, k: Kontext | None = None) -> list[Treffer]:
    """Alle aktiven Regeln anwenden; Treffer als Hinweise (Stufe „pruefen“) an die Rechnung hängen.
    -> neu angehängte Treffer. GTIN-Prüfziffern (BT-157, Scheme 0160) nur als Warnung."""
    k = k or Kontext()
    schon = {h.feld for h in r.hinweise if h.stufe in ("pruefen", "fehler") and h.feld}
    neu = []
    for g in aktive_regeln(k):
        for feld, text in g.pruefe(r, k):
            if feld in schon:
                continue
            schon.add(feld)
            r.hinweis(STUFE, text, feld)
            neu.append((feld, text))
    _gtin_warnungen(r)
    _luecken_warnungen(r, k)
    return neu


def _luecken_warnungen(r: Rechnung, k: Kontext) -> None:
    """Lücke im Nummernkreis (ab 0.9.5, nur wenn eingeschaltet und ein Prüfmuster mit # gesetzt ist): nur eine
    Warnung, die Rechnung läuft weiter. Lücken sind erlaubt (Abschn. 14.5 Abs. 10 UStAE)."""
    from . import nummernkreis as nk

    kreis = k.nummernkreise.get(nk.kreis_von(r.art))
    if not kreis or not kreis.luecken_warnen or not kreis.pruefmuster or _leer(r.nummer):
        return
    try:
        if not nk.hat_zaehler(kreis.pruefmuster):
            return
        l = nk.luecke(r.nummer, set(k.bekannte_nummern) | set(k.lauf_nummern), kreis.pruefmuster)
    except (nk.MusterFehler, re.error):
        return
    if l:
        vorher, fehlen = l
        r.hinweis("warnung", (f"Lücke im Nummernkreis: vor {r.nummer} zuletzt {vorher}, "
                              f"{fehlen} Nummer{'n' if fehlen != 1 else ''} dazwischen fehlt{'en' if fehlen != 1 else ''}. "
                              "Lücken sind erlaubt (UStAE 14.5 Abs. 10) – nur zur Kontrolle."), "BT-1")


def _gtin_warnungen(r: Rechnung) -> None:
    schon = {h.feld for h in r.hinweise if h.feld}
    for p in r.positionen:
        if (p.standard_schema or "").strip() != "0160" or _leer(p.standard_id):
            continue
        feld = f"Pos {p.nr} BT-157"
        if feld in schon:
            continue
        if not gtin_gueltig(p.standard_id):
            r.hinweis("warnung", (f"Position {p.nr} – GTIN (BT-157) „{p.standard_id}“ hat eine ungültige "
                                  "Prüfziffer (GS1 Mod 10)."), feld)
