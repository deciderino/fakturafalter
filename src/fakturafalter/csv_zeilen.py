# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Text-/Leerzeilen und leere Mengen/Preise im Aufbau „eine Zeile je Position“.

Ab 0.9.9 gilt 0 / 0,00 auch im Blockmodus als leer; unzugeordnete Spalten zählen
dort nicht mehr für die Kopfzeilen-Schwelle.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from . import csv_bloecke as cb


def wert_ist_leer(val) -> bool:
    """Leer, nur Leerzeichen, 0, 0,00, 0.0 – keine Positionsware."""
    s = str(val or "").strip()
    if s == "":
        return True
    t = s.replace("\u00a0", "").replace(" ", "").replace("%", "")
    try:
        return Decimal(t.replace(",", ".")) == 0
    except (InvalidOperation, ValueError, ArithmeticError):
        return False


def zugeordnete_spalten(felder_kopf: dict, felder_pos: dict, tz: dict | None = None) -> set[str]:
    """Nur Spalten, die im Profil zugeordnet sind – „nicht verwenden“ zählt nicht."""
    aus: set[str] = set()
    for defs in (felder_kopf or {}, felder_pos or {}):
        for d in defs.values():
            if isinstance(d, dict) and isinstance(d.get("spalte"), str) and d["spalte"]:
                aus.add(d["spalte"])
    tz = tz or {}
    if isinstance(tz.get("text_spalte"), str) and tz["text_spalte"]:
        aus.add(tz["text_spalte"])
    return aus


def _zahl_zelle(row: dict, felder: dict, name: str) -> str:
    return (cb._feld_wert(row, felder, name) or "").strip()


def erkennen(
    row: dict,
    felder_pos: dict,
    felder_kopf: dict | None,
    tz: dict,
) -> tuple[str, str] | None:
    """None = normale Positionszeile.

    Sonst ('text', Inhalt), ('leer', ''), ('skip', ''),
    oder ('preis_ohne_menge', Inhalt) wenn der Aufrufer die Option selbst auswertet.
    """
    menge = _zahl_zelle(row, felder_pos, "BT-129")
    preis = _zahl_zelle(row, felder_pos, "BT-146")
    menge_leer, preis_leer = wert_ist_leer(menge), wert_ist_leer(preis)
    text = cb._text_aus_zeile(row, felder_pos, tz)
    modus = str(tz.get("leerzeile_modus") or "beides")
    platz = tz.get("platzhalter")
    platz = "#LEER" if platz is None else str(platz)

    if not menge_leer and not preis_leer:
        return None
    if not menge_leer and preis_leer:
        return None  # Menge ohne Preis = Position
    if menge_leer and not preis_leer:
        return ("preis_ohne_menge", text)

    # Menge und Preis leer/0
    if text and platz and text == platz and modus in ("platzhalter", "beides"):
        return ("leer", "")
    if text:
        return ("text", text)
    if modus in ("kopffeldzeile", "beides") and _kopffeldzeile(
        row, felder_pos, felder_kopf or {}, tz
    ):
        return ("leer", "")
    return ("skip", "")


def _kopffeldzeile(row: dict, felder_pos: dict, felder_kopf: dict, tz: dict) -> bool:
    """Gewollte Leerzeile: zugeordnete Leer-Felder leer, mindestens ein anderes zugeordnetes Feld belegt."""
    leer_felder = tz.get("leer") or list(cb._LEER_STANDARD)
    spalten_leer: set[str] = set()
    for name in leer_felder:
        if name == "text":
            if cb._text_aus_zeile(row, felder_pos, tz):
                return False
            sp = tz.get("text_spalte") or (felder_pos.get("BT-153") or {}).get("spalte")
            if sp:
                spalten_leer.add(sp)
            continue
        d = felder_pos.get(name) or felder_kopf.get(name) or {}
        sp = d.get("spalte") if isinstance(d, dict) else None
        if sp:
            spalten_leer.add(sp)
            if not wert_ist_leer(row.get(sp)):
                return False
    erlaubt = zugeordnete_spalten(felder_kopf, felder_pos, tz)
    for sp, val in row.items():
        if sp not in erlaubt or sp in spalten_leer:
            continue
        if str(val or "").strip():
            return True
    return False


def kommentar_an(pos: dict, text: str, leerzeile: bool, tz: dict, zeile: int, pfad) -> None:
    """Kommentar-/Leerzeile unter der Position: Sichtseite ohne Vorsatz, XML über kommentar_unten → BT-154."""
    lst = pos.setdefault("_kommentar_unten", [])
    if not isinstance(lst, list):
        lst = list(lst)
        pos["_kommentar_unten"] = lst
    lst.append("" if leerzeile else text)
