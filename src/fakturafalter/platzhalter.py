# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Platzhalter in Textfeldern des Layouteditors (ab 1.0.0-rc2).

``{BT-13}`` setzt den Wert eines Kopf-BT der Rechnung ein, ``{Bestellnummer}`` den Wert der gleichnamigen Spalte
aus der CSV/Tabelle (auch Spalten, die keinem Feld zugeordnet sind) oder – wenn es keine solche Spalte gibt – das
Feld mit diesem Namen. Nur Kopfwerte (eine Rechnung, ein Wert), keine Positionswerte. Fehlt ein Wert, bleibt die
Stelle leer. ``{{`` und ``}}`` schreiben eine geschweifte Klammer.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

MUSTER = re.compile(r"\{\{|\}\}|\{([^{}\r\n]{1,80})\}")
_BT = re.compile(r"^\s*BT[\s_\-.]*0*(\d{1,3})\s*$", re.I)


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, Decimal):
        return format(v, "f").replace(".", ",")
    return str(v).strip()


def kopf_bt(r) -> dict[str, str]:
    """Kopfwerte der Rechnung nach BT-Nummer (unabhängig von der Quelle: CSV, XML, PDF)."""
    ref, z, k, v = r.referenzen, r.zahlung, r.kaeufer, r.verkaeufer
    werte = {
        "BT-1": r.nummer, "BT-2": r.datum, "BT-3": r.art, "BT-5": r.waehrung, "BT-9": z.faellig,
        "BT-10": r.leitweg_id, "BT-11": ref.projekt, "BT-12": ref.vertrag, "BT-13": r.bestellnummer,
        "BT-14": ref.auftrag, "BT-15": ref.wareneingang, "BT-16": ref.lieferschein, "BT-17": ref.ausschreibung,
        "BT-18": ref.objekt, "BT-19": ref.buchung, "BT-20": z.bedingungen,
        "BT-25": r.bezuege[0].nummer if r.bezuege else "",
        "BT-27": v.name, "BT-31": v.ust_id, "BT-32": v.steuernummer,
        "BT-44": k.name, "BT-45": k.handelsname, "BT-46": k.kennung or r.kundennummer, "BT-48": k.ust_id,
        "BT-49": k.elektronische_adresse, "BT-50": k.anschrift.strasse, "BT-52": k.anschrift.ort,
        "BT-53": k.anschrift.plz, "BT-56": k.kontakt_name, "BT-57": k.kontakt_telefon, "BT-58": k.kontakt_email,
        "BT-70": r.lieferung.name, "BT-72": r.leistungsdatum, "BT-73": r.leistung_von, "BT-74": r.leistung_bis,
        "BT-83": z.verwendungszweck or r.nummer,
        "BT-112": r.summen.brutto if r.summen.brutto else None, "BT-115": r.summen.zahlbar if r.positionen else None,
    }
    return {bt: _text(w) for bt, w in werte.items()}


def _feldnamen() -> dict[str, str]:
    """Feldbezeichnung (Assistent) und amtlicher Name -> BT, kleingeschrieben – z. B. „bestellnummer“ -> BT-13."""
    from . import csv_einrichtung as ce

    out: dict[str, str] = {}
    for fid, label, teil, _typ, _p in ce.FELDER:
        if teil != "kopf":
            continue
        bts = (fid,) if fid.startswith("BT-") else tuple(ce.FELD_STANDARD.get(fid, ()))
        if len(bts) != 1:
            continue
        for name in (label, *ce.STANDARD_NAME.get(bts[0], ())):
            if name:
                out.setdefault(_schl(name), bts[0])
    return out


def _schl(s: str) -> str:
    return " ".join(str(s).split()).casefold()


def wert(r, name: str) -> str:
    """Wert eines Platzhalters; unbekannt oder leer -> ""."""
    m = _BT.match(name)
    if m:
        return kopf_bt(r).get(f"BT-{int(m.group(1))}", "")
    spalten = {_schl(k): v for k, v in (getattr(r, "spalten", None) or {}).items()}
    if _schl(name) in spalten:
        return _text(spalten[_schl(name)])
    bt = _feldnamen().get(_schl(name))
    if bt:
        return kopf_bt(r).get(bt, "")
    if _schl(name) == "kundennummer":
        return _text(r.kundennummer or r.kaeufer.kennung)
    return ""


def ersetzen(text: str, r) -> str:
    """Alle Platzhalter im Text ersetzen (ohne Rechnung bleibt der Text unverändert)."""
    if r is None or "{" not in (text or ""):
        return text

    def ein(m: re.Match) -> str:
        g = m.group(0)
        if g == "{{":
            return "{"
        if g == "}}":
            return "}"
        return wert(r, m.group(1)).replace("\n", " ")

    return MUSTER.sub(ein, text)


def namen(text: str) -> list[str]:
    """Platzhalter, die im Text vorkommen (Reihenfolge, ohne Doppelte)."""
    out: list[str] = []
    for m in MUSTER.finditer(text or ""):
        if m.group(1) and m.group(1) not in out:
            out.append(m.group(1))
    return out
