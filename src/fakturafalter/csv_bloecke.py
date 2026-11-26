# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""CSV-Aufbau „bloecke“: eine Datei ergibt eine Rechnung.

Anfangsregeln in dieser Reihenfolge: Marker, Satzart-Wert, Kopfzeile.
Spalten je Block über Name (Vorrang) und 1-basierte Position.
Siehe docs/csv-format.md und docs/csv-standard.md.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

from .modell import Herkunft
from .werte import WertFehler

# Default: welche Positionsfelder leer sein müssen, damit eine Zeile als gewollte
# Leerzeile (Kopffeldzeile) gilt – Menge, Preis, Text.
_LEER_STANDARD = ("BT-129", "BT-146", "text")


def name_norm(s: str) -> str:
    """Spaltennamen vergleichen: Kleinbuchstaben, Umlaute aufgelöst, ohne Satzzeichen."""
    t = (
        (s or "")
        .casefold()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return re.sub(r"[^a-z0-9]+", "", t)


def _pruefen(text: str):
    from . import adapter_csv as ac

    return ac.Pruefen(text)


def schwelle(profil: dict) -> int:
    return max(1, int((profil.get("aufbau") or {}).get("kopfzeile_schwelle") or 2))


def genutzte_namen(profil: dict) -> set[str]:
    """Nur zugeordnete Spalten (`felder.spalte`) – unbenutzte Namen zählen nicht für die Schwelle."""
    aus: set[str] = set()
    for b in profil.get("bloecke") or []:
        for d in (b.get("felder") or {}).values():
            if isinstance(d, dict) and d.get("spalte"):
                aus.add(name_norm(str(d["spalte"])))
    for teil in (profil.get("felder") or {}).values():
        if isinstance(teil, dict):
            for d in teil.values():
                if isinstance(d, dict) and d.get("spalte"):
                    aus.add(name_norm(str(d["spalte"])))
    aus.discard("")
    return aus


def bekannte_namen(profil: dict) -> set[str]:
    """Ab 0.9.9: nur noch genutzte Spalten. Exakte Kopfzeilen prüft `ist_exakte_kopfzeile`."""
    return genutzte_namen(profil)


def _norm_zeile(zellen: list[str]) -> list[str]:
    aus = [name_norm(str(c).strip()) for c in zellen]
    while aus and not aus[-1]:
        aus.pop()
    return aus


def gespeicherte_kopfzeilen(profil: dict, typ: str | None = None) -> list[list[str]]:
    aus: list[list[str]] = []
    for b in profil.get("bloecke") or []:
        if typ is not None and str(b.get("typ") or "") != typ:
            continue
        k = _norm_zeile([str(x) for x in (b.get("kopfzeile") or []) if x is not None])
        if k:
            aus.append(k)
    return aus


def ist_exakte_kopfzeile(zellen: list[str], profil: dict, typ: str | None = None) -> bool:
    haben = _norm_zeile(zellen)
    if not haben:
        return False
    return any(haben == soll for soll in gespeicherte_kopfzeilen(profil, typ))


def block_wiederholend(b: dict) -> bool:
    """Altes Profil ohne Flag: typ positionen gilt als wiederholend."""
    if "wiederholend" in b:
        return bool(b.get("wiederholend"))
    return str(b.get("typ") or "") == "positionen"


def wiederholender_typ(profil: dict) -> str:
    for b in profil.get("bloecke") or []:
        if block_wiederholend(b) and b.get("typ"):
            return str(b["typ"])
    return "positionen"


def kopfzeile_des_typs(profil: dict, typ: str) -> list[str]:
    for b in profil.get("bloecke") or []:
        if str(b.get("typ") or "") == typ:
            return [str(x) for x in (b.get("kopfzeile") or [])]
    return []


def platzhalter_von(profil: dict) -> str:
    p = ((profil.get("aufbau") or {}).get("textzeile") or {}).get("platzhalter")
    return "#LEER" if p is None else str(p)


def anfang_regeln(block: dict) -> list[dict]:
    """Gespeicherte Anfangsregeln, sonst aus marker/kopfzeile abgeleitet (0.9.8/0.9.9)."""
    raw = block.get("anfang")
    if isinstance(raw, list) and raw:
        aus = [dict(r) for r in raw if isinstance(r, dict) and r.get("art")]
        if aus:
            return aus
    m = str(block.get("marker") or "").strip()
    if m:
        return [{"art": "marker", "wert": m}]
    if block.get("kopfzeile"):
        return [{"art": "kopfzeile"}]
    return []


def hat_satzart_anfang(profil: dict) -> bool:
    return any(
        r.get("art") == "satzart" for b in (profil.get("bloecke") or []) for r in anfang_regeln(b)
    )


def satzart_spalte_von(profil: dict):
    """Name oder 1-basierte Nummer aus aufbau.satzart_spalte, sonst None."""
    v = (profil.get("aufbau") or {}).get("satzart_spalte")
    if v in (None, ""):
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.isdigit():
        return int(s)
    return s


def satzart_wert(zellen: list[str], profil: dict, kopf: list[str] | None = None) -> str:
    """Satzart-Zelle laut Profil (Spaltenname oder 1-basierte Nummer)."""
    sp = satzart_spalte_von(profil)
    if sp is None:
        return ""
    if isinstance(sp, int):
        i = sp - 1
        return (zellen[i] or "").strip() if 0 <= i < len(zellen) else ""
    namen = list(kopf or [])
    for i, name in enumerate(namen):
        if name_norm(name) == name_norm(sp) and i < len(zellen):
            return (zellen[i] or "").strip()
    return ""



def profil_block_fuer_satzart(wert: str, profil: dict) -> dict | None:
    """Profilblock zur Satzart-Wert-Anfangsregel (auch #Beleg in einer Datenzeile)."""
    w = (wert or "").strip()
    if not w:
        return None
    for b in profil.get("bloecke") or []:
        for r in anfang_regeln(b):
            if r.get("art") == "satzart" and str(r.get("wert") or "").strip() == w:
                return b
    return None


def profil_block_zu(bl: dict, profil: dict) -> dict:
    """Passenden Profilblock finden: zuerst id, dann eindeutiger typ, dann Kopfzeile."""
    bid = str(bl.get("id") or "").strip()
    typ = str(bl.get("typ") or "").strip()
    liste = list(profil.get("bloecke") or [])
    if bid:
        for b in liste:
            if str(b.get("id") or "").strip() == bid:
                return b
        for b in liste:
            if str(b.get("typ") or "").strip() == bid:
                # nur wenn typ in diesem Profil eindeutig ist
                if sum(1 for x in liste if str(x.get("typ") or "") == bid) == 1:
                    return b
    if typ:
        treffer = [b for b in liste if str(b.get("typ") or "").strip() == typ]
        if len(treffer) == 1:
            return treffer[0]
        kopf = [name_norm(x) for x in (bl.get("kopf") or [])]
        for b in treffer:
            soll = [name_norm(x) for x in (b.get("kopfzeile") or [])]
            if kopf and soll and kopf == soll:
                return b
        if treffer:
            return treffer[0]
    return {}


def profil_block_id(b: dict, index: int = 0) -> str:
    if str(b.get("id") or "").strip():
        return str(b.get("id")).strip()
    typ = str(b.get("typ") or "").strip()
    return typ or f"block{index + 1}"


def typ_fuer_satzart(wert: str, profil: dict) -> str:
    w = (wert or "").strip()
    if not w:
        return ""
    for b in profil.get("bloecke") or []:
        typ = str(b.get("typ") or "")
        for r in anfang_regeln(b):
            if r.get("art") == "satzart" and str(r.get("wert") or "").strip() == w:
                return typ
    return ""


def feld_anzeige(name: str) -> str:
    from .csv_einrichtung import FELD

    meta = FELD.get(name)
    return str(meta[1]) if meta else name


def zeile_zu_row(werte: list[str], kopf: list[str]) -> dict:
    """Zeile als dict: Spaltennamen und 1-basierte Positionsnummern."""
    row: dict = {}
    for i, val in enumerate(werte):
        row[i + 1] = val
        row[str(i + 1)] = val
        if i < len(kopf) and kopf[i]:
            row[str(kopf[i])] = val
    return row


def _feld_aus_zeile(row: dict, d: dict):
    """(Schlüssel, Rohtext-or-None). Name hat Vorrang, wenn die Kopfzeile ihn trägt."""
    name = d.get("spalte")
    pos = d.get("position")
    if isinstance(name, str) and name and name in row:
        val = row[name]
        return name, "" if val is None else str(val)
    if pos is not None:
        try:
            i = int(pos)
        except (TypeError, ValueError):
            i = 0
        if i in row:
            val = row[i]
            return i, "" if val is None else str(val)
        if str(i) in row:
            val = row[str(i)]
            return str(i), "" if val is None else str(val)
    if isinstance(name, str) and name:
        return name, None
    return None, None


def spezifitaet(profil: dict, zeilen: list[list[str]]) -> int:
    """Höher = genauer (Marker/Satzart/exakte Kopfzeile vor bloßer Namensschwelle)."""
    bloecke = schneiden_profil(zeilen, 1, profil)
    score = 0
    for b in profil.get("bloecke") or []:
        typ = str(b.get("typ") or "")
        getroffene = {str(bl.get("typ") or "") for bl in bloecke}
        if typ not in getroffene:
            continue
        for r in anfang_regeln(b):
            art = r.get("art")
            treffer = [bl for bl in bloecke if str(bl.get("typ") or "") == typ]
            if art == "marker" and any(bl.get("marker") for bl in treffer):
                score += 20
            elif art == "satzart" and any(bl.get("satzart") for bl in treffer):
                score += 15
            elif art == "kopfzeile" and any(not bl.get("ohne_kopfzeile") for bl in treffer):
                score += 10
    vorhanden = kopf_namen_in_datei(zeilen, profil)
    score += sum(1 for w in genutzte_spalten_wortlaut(profil) if name_norm(w) in vorhanden)
    return score


def marker_im_profil(profil: dict) -> list[tuple[str, str]]:
    """[(typ, normierter Marker), …] – Platzhalter #LEER kann kein Marker sein."""
    platz = name_norm(platzhalter_von(profil))
    aus: list[tuple[str, str]] = []
    gesehen: set[tuple[str, str]] = set()
    for b in profil.get("bloecke") or []:
        typ = str(b.get("typ") or "")
        werte: list[str] = []
        if str(b.get("marker") or "").strip():
            werte.append(str(b.get("marker")).strip())
        for r in anfang_regeln(b):
            if r.get("art") == "marker" and str(r.get("wert") or "").strip():
                werte.append(str(r.get("wert")).strip())
        for m in werte:
            n = name_norm(m)
            if not n or n == platz or (typ, n) in gesehen:
                continue
            gesehen.add((typ, n))
            aus.append((typ, n))
    return aus


def ist_markerzeile(zellen: list[str], profil: dict) -> str:
    """Typ, wenn die erste nicht-leere Zelle exakt einem Marker entspricht und der Rest leer ist."""
    if not marker_im_profil(profil):
        return ""
    erste = ""
    for c in zellen:
        if not (c or "").strip():
            continue
        if erste:
            return ""
        erste = c.strip()
    if not erste:
        return ""
    if name_norm(erste) == name_norm(platzhalter_von(profil)):
        return ""
    n = name_norm(erste)
    for typ, mn in marker_im_profil(profil):
        if n == mn:
            return typ
    return ""


def sieht_nach_marker_heuristik(zellen: list[str]) -> bool:
    """Format-Schritt: eine einzelne Zelle der Form #Wort ohne Leerzeichen, nicht #LEER.

    Kommentare wie „# bitte nicht …“ sind keine Marker. Ohne „#“ prüft erst das Profil.
    """
    fuell = [(c or "").strip() for c in zellen if (c or "").strip()]
    if len(fuell) != 1:
        return False
    t0 = fuell[0]
    if not t0.startswith("#") or len(t0) < 2:
        return False
    if name_norm(t0) == name_norm("#LEER"):
        return False
    wort = t0[1:]
    return bool(wort) and not any(ch.isspace() for ch in wort)


def ist_kopfzeile(zellen: list[str], namen: set[str], n: int) -> bool:
    if not namen:
        return False
    treffer = sum(1 for c in zellen if name_norm(c) and name_norm(c) in namen)
    return treffer >= n


def ist_block_kopfzeile(zellen: list[str], profil: dict) -> bool:
    """Genutzte Namen ab Schwelle, oder exakt eine gespeicherte Kopfzeile."""
    if ist_kopfzeile(zellen, genutzte_namen(profil), schwelle(profil)):
        return True
    return ist_exakte_kopfzeile(zellen, profil)


def _leer_zeile(werte: list[str]) -> bool:
    return not any((w or "").strip() for w in werte)


def schneiden(zeilen: list[list[str],], start: int, namen: set[str], n: int) -> list[dict]:
    """Datei in Blöcke (Kopfzeile + Datenzeilen) zerlegen. Komplett leere Zeilen trennen nur, beenden nichts."""
    aus: list[dict] = []
    aktuell: dict | None = None
    for i, row in enumerate(zeilen):
        nr = start + i
        if _leer_zeile(row):
            continue
        if ist_kopfzeile(row, namen, n):
            aktuell = {"kopf": [c.strip() for c in row], "start": nr, "daten": []}
            aus.append(aktuell)
        elif aktuell is None:
            aktuell = {"kopf": [], "start": nr, "daten": [(nr, row)], "ohne_kopfzeile": True}
            aus.append(aktuell)
        else:
            aktuell["daten"].append((nr, row))
    return aus


def schneiden_profil(zeilen: list[list[str]], start: int, profil: dict) -> list[dict]:
    """Zerlegen nach Profil: Marker, Satzart-Wert, dann Kopfzeile. Leere Zeilen trennen nur."""
    namen = genutzte_namen(profil)
    n = schwelle(profil)
    hat_marker = bool(marker_im_profil(profil))
    satzart_aktiv = hat_satzart_anfang(profil) and satzart_spalte_von(profil) is not None
    wieder = wiederholender_typ(profil)
    aus: list[dict] = []
    aktuell: dict | None = None
    optional_kopf = False
    gemeinsame_kopf: list[str] | None = None
    gesehen_satzart_typ: set[str] = set()
    kopf_fuer_satzart: list[str] = list(gemeinsame_kopf or [])

    def _hinweis(bl: dict, text: str) -> None:
        bl.setdefault("hinweise", []).append(_pruefen(text))

    def _neuer_block(nr: int, typ: str, **extra) -> dict:
        nonlocal aktuell, optional_kopf
        kopf = list(extra.pop("kopf", []) or [])
        bl = {
            "kopf": kopf,
            "start": nr,
            "daten": [],
            "typ": typ,
            **extra,
        }
        if not kopf and extra.get("ohne_kopfzeile"):
            # später evtl. gespeicherte oder gemeinsame Kopfzeile
            stored = kopfzeile_des_typs(profil, typ)
            if stored:
                bl["kopf"] = list(stored)
            elif gemeinsame_kopf:
                bl["kopf"] = list(gemeinsame_kopf)
        aus.append(bl)
        aktuell = bl
        return bl

    for i, row in enumerate(zeilen):
        nr = start + i
        if _leer_zeile(row):
            continue
        typ_m = ist_markerzeile(row, profil) if hat_marker else ""
        if typ_m:
            wort = next((str(c).strip() for c in row if str(c).strip()), "")
            _neuer_block(
                nr,
                typ_m,
                kopf=kopfzeile_des_typs(profil, typ_m),
                marker=True,
                marker_wort=wort,
                ohne_kopfzeile=True,
            )
            optional_kopf = True
            continue

        # Satzart-Wert: nur prüfen, wenn das Profil diese Anfangsregel hat
        sa_kopf = (aktuell or {}).get("kopf") or gemeinsame_kopf or kopf_fuer_satzart
        wert_sa = satzart_wert(row, profil, sa_kopf) if satzart_aktiv else ""
        pb_sa = profil_block_fuer_satzart(wert_sa, profil) if wert_sa else None
        typ_sa = typ_fuer_satzart(wert_sa, profil) if wert_sa else ""
        if typ_sa:
            if aktuell is not None and typ_sa == str(aktuell.get("typ") or ""):
                if optional_kopf:
                    optional_kopf = False
                    aktuell["ohne_kopfzeile"] = True
                aktuell["daten"].append((nr, row))
                continue
            if typ_sa != wieder and typ_sa in gesehen_satzart_typ:
                # zweite nicht-wiederholende Satzart (typisch zweite Kopf-Rechnung)
                vorg = aus[-1] if aus else None
                msg = (
                    "weitere Rechnung in derselben Datei – im Block-Modus nicht vorgesehen"
                )
                if vorg is not None:
                    _hinweis(vorg, f"Zeile {nr}: {msg}")
                else:
                    pass
            gesehen_satzart_typ.add(typ_sa)
            kopf = list(gemeinsame_kopf or kopfzeile_des_typs(profil, typ_sa) or [])
            bl = _neuer_block(
                nr,
                typ_sa,
                kopf=kopf,
                satzart=True,
                satzart_wert=wert_sa,
                ohne_kopfzeile=not bool(kopf),
                id=profil_block_id(pb_sa) if pb_sa else typ_sa,
            )
            if typ_sa != wieder and typ_sa in gesehen_satzart_typ:
                # already added typ; second time flagged above before add
                pass
            optional_kopf = False
            bl["daten"].append((nr, row))
            # second-time flag: we added typ to gesehen before checking? Fixed below after loop logic
            continue

        if optional_kopf and aktuell is not None:
            optional_kopf = False
            typ = str(aktuell.get("typ") or "")
            if (
                ist_kopfzeile(row, namen, n)
                or ist_exakte_kopfzeile(row, profil, typ)
                or ist_exakte_kopfzeile(row, profil)
            ):
                aktuell["kopf"] = [c.strip() for c in row]
                aktuell["ohne_kopfzeile"] = False
                kopf_fuer_satzart = aktuell["kopf"]
                continue

        if ist_kopfzeile(row, namen, n) or ist_exakte_kopfzeile(row, profil):
            typ = typ_fuer([c.strip() for c in row], profil)
            # Gemeinsame Kopfzeile vor dem ersten Satzart-Block
            if satzart_aktiv and aktuell is None and not aus:
                gemeinsame_kopf = [c.strip() for c in row]
                kopf_fuer_satzart = gemeinsame_kopf
                continue
            aktuell = {
                "kopf": [c.strip() for c in row],
                "start": nr,
                "daten": [],
                "typ": typ,
            }
            pb = profil_block_zu(aktuell, profil)
            if pb:
                aktuell["id"] = profil_block_id(pb)
                if pb.get("typ"):
                    aktuell["typ"] = str(pb.get("typ"))
            aus.append(aktuell)
            kopf_fuer_satzart = aktuell["kopf"]
        elif aktuell is None:
            aktuell = {
                "kopf": list(gemeinsame_kopf or []),
                "start": nr,
                "daten": [(nr, row)],
                "ohne_kopfzeile": not bool(gemeinsame_kopf),
                "ohne_anfang": True,
            }
            aus.append(aktuell)
        else:
            aktuell["daten"].append((nr, row))

    return aus



def _sieht_nach_positionen_aus(kopf: list[str]) -> bool:
    """Kopfzeile enthält typische Positions-Spalten (Menge, Preis, Artikel)."""
    n = {name_norm(c) for c in kopf}
    return bool(
        n
        & {
            name_norm(x)
            for x in ("menge", "einzelpreis", "artikel", "bezeichnung", "ustsatz", "ust-satz")
        }
    )


def typ_fuer(kopf: list[str], profil: dict) -> str:
    best, punkte = "", -1
    haben = {name_norm(c) for c in kopf if name_norm(c)}
    treffer_je: list[tuple[int, str]] = []
    for b in profil.get("bloecke") or []:
        typ = str(b.get("typ") or "")
        if not typ:
            continue
        soll = {name_norm(str(x)) for x in (b.get("kopfzeile") or []) if x}
        if not soll:
            soll = {
                name_norm(str(d["spalte"]))
                for d in (b.get("felder") or {}).values()
                if isinstance(d, dict) and d.get("spalte")
            }
        treffer = len(haben & soll)
        treffer_je.append((treffer, typ))
        if treffer > punkte:
            best, punkte = typ, treffer
    if punkte <= 0:
        return ""
    # eindeutiger Höchstwert
    if sum(1 for t, typ in treffer_je if t == punkte) > 1:
        return best  # erster im Profil gewinnt
    return best


def textzeile_konfig(profil: dict) -> dict:
    t = dict((profil.get("aufbau") or {}).get("textzeile") or {})
    t.setdefault("leer", list(_LEER_STANDARD))
    t.setdefault("ziel", "BT-154")
    t.setdefault("trenner", "\n")
    t.setdefault("platzhalter", "#LEER")
    t.setdefault("verwaist", "BT-22")
    t.setdefault("leerzeile_modus", "beides")
    t.setdefault("zwischen", "vorher")
    t.setdefault("preis_ohne_menge", "pruefen")
    return t


def _feld_wert(row: dict, felder: dict, name: str):
    """Rohtext eines logischen Feldes (vor dem Typisieren), über die Spaltenzuordnung."""
    if name == "text":
        d = felder.get("BT-153") or felder.get("text") or {}
        _k, val = _feld_aus_zeile(row, d)
        return (val or "").strip() if val is not None else ""
    d = felder.get(name) or {}
    _k, val = _feld_aus_zeile(row, d)
    return (val or "").strip() if val is not None else ""


def _ist_kopffeld(name: str) -> bool:
    """Positionsfelder (Bezeichnung, Menge, Preis, Steuer …) gehören nicht in den Rechnungskopf."""
    from .csv_einrichtung import FELD

    meta = FELD.get(name)
    return True if not meta else meta[2] == "kopf"


def feldsatz(row: dict, defs: dict, zeile: int, fehler: list, profil: dict, pfad: Path) -> dict:
    roh: dict = {}
    for feld, d in defs.items():
        schl, val = _feld_aus_zeile(row, d)
        label = d.get("spalte") if d.get("spalte") not in (None, "") else d.get("position", "fest")
        h = Herkunft(f"csv:{pfad.name} Zeile {zeile} Spalte {label}", 1.0)
        if "fest" in d:
            roh[feld] = (str(d["fest"]), Herkunft("profil:fest", 1.0))
            continue
        if val is None or schl is None:
            if not d.get("optional"):
                fehler.append(f"Spalte „{label}“ fehlt")
            continue
        try:
            from . import adapter_csv as ac

            roh[feld] = (
                ac._typisieren(val if isinstance(val, str) else str(val), d, profil),
                h,
            )
        except ac.Zweifel as e:
            fehler.append(_pruefen(f"Zeile {zeile}, {feld}: {e}"))
        except WertFehler as e:
            fehler.append(f"Zeile {zeile}, {feld}: {e}")
    return roh


def kopf_mergen(ziel: dict, neu: dict, zeile: int, fehler: list, typ: str = "") -> None:
    for k, v in neu.items():
        wert, herkunft = v if isinstance(v, tuple) else (v, None)
        if wert in (None, ""):
            continue
        alt = ziel.get(k)
        if alt is None or alt[0] in (None, ""):
            ziel[k] = (wert, herkunft)
            if typ:
                ziel[f"_typ_{k}"] = typ
        elif str(alt[0]).strip() != str(wert).strip():
            anzeige = feld_anzeige(k)
            alt_typ = ziel.get(f"_typ_{k}") or ""
            if typ and alt_typ:
                fehler.append(
                    _pruefen(
                        f"„{anzeige}“ weicht zwischen Block „{alt_typ}“ und „{typ}“ ab"
                    )
                )
            else:
                fehler.append(_pruefen(f"Zeile {zeile}: Kopfwert „{k}“ weicht ab"))


def _anhaengen(alt: str, neu: str, trenner: str, leerzeile: bool = False) -> str:
    if leerzeile:
        if not alt:
            return "\n"
        return alt if alt.endswith("\n\n") else (alt.rstrip("\n") + "\n\n")
    if not (neu or "").strip() and neu != "":
        # explizit leerer Zusatz ohne Platzhalter
        return alt
    if not neu:
        return alt
    if not alt:
        return neu
    return alt + trenner + neu


def _text_aus_zeile(row: dict, felder: dict, tz: dict) -> str:
    if tz.get("text_spalte"):
        d = {"spalte": tz.get("text_spalte")}
        if tz.get("text_position"):
            d["position"] = tz.get("text_position")
    else:
        d = felder.get("BT-153") or felder.get("text") or {}
    _k, val = _feld_aus_zeile(row, d)
    return (val or "").strip() if val is not None else ""


def zeile_ohne_inhalt(werte) -> bool:
    """Leer oder nur Steuerzeichen (z. B. DOS-Dateiende \x1a) – kein Inhalt."""
    return not any((w or "").strip().strip("\x1a") for w in werte)


def textzeile_erkennen(row: dict, felder: dict, tz: dict) -> tuple[str, str] | None:
    """None = normale Positionszeile. Sonst ('text', Inhalt), ('leer', '') oder ('skip', '')."""
    from . import csv_zeilen

    menge = (_feld_wert(row, felder, "BT-129") or "").strip()
    preis = (_feld_wert(row, felder, "BT-146") or "").strip()
    if not csv_zeilen.wert_ist_leer(menge):
        return None
    if not csv_zeilen.wert_ist_leer(preis):
        return ("preis_ohne_menge", _text_aus_zeile(row, felder, tz))
    text = _text_aus_zeile(row, felder, tz)
    modus = str(tz.get("leerzeile_modus") or "beides")
    platz = tz.get("platzhalter")
    platz = "#LEER" if platz is None else str(platz)
    if text and platz and text == platz and modus in ("platzhalter", "beides"):
        return ("leer", "")
    if text:
        return ("text", text)
    if modus in ("kopffeldzeile", "beides") and _kopffelder_ohne_leerpflicht(row, felder, tz):
        return ("leer", "")
    return ("skip", "")


def text_an_roh(pos: dict, text: str, leerzeile: bool, tz: dict, zeile: int, pfad: Path) -> None:
    """Text- oder Leerzeile an die vorherige Positions-Rohzeile (BT-154 bzw. konfiguriertes Ziel)."""
    ziel = str(tz.get("ziel") or "BT-154")
    trenner = tz.get("trenner")
    trenner = "\n" if trenner is None else str(trenner)
    alt = str((pos.get(ziel) or ("",))[0] or "")
    herkunft = Herkunft(f"csv:{Path(pfad).name} Zeile {zeile} Textzeile", 1.0)
    pos[ziel] = (_anhaengen(alt, text, trenner, leerzeile=leerzeile), herkunft)
    if ziel == "BT-153" and leerzeile:
        alt4 = str((pos.get("BT-154") or ("",))[0] or "")
        pos["BT-154"] = (_anhaengen(alt4, "", "\n", leerzeile=True), herkunft)


def _ist_fuellung(val) -> bool:
    return val not in (None, "") and str(val).strip() != ""


def lesen(text_zeilen: list[list[str]], profil: dict, pfad: Path, start: int) -> OrderedDict:
    """-> {schlüssel: (kopf, positionen, fehler)} – im Block-Modus höchstens eine Rechnung."""
    roh_bloecke = schneiden_profil(text_zeilen, start, profil)
    wieder = wiederholender_typ(profil)
    tz = textzeile_konfig(profil)
    modus = str(tz.get("leerzeile_modus") or "beides")
    platz = str(tz.get("platzhalter") if tz.get("platzhalter") is not None else "#LEER")
    ziel_feld = str(tz.get("ziel") or "BT-154")
    trenner = tz.get("trenner")
    trenner = "\n" if trenner is None else str(trenner)
    verwaist = str(tz.get("verwaist") or "BT-22")

    kopf: dict = {}
    positionen: list[dict] = []
    fehler: list = []
    notiz_teile: list[str] = []
    gesehen_positionen = 0
    nummern: set[str] = set()

    def defs_fuer(pdef: dict, typ: str, art: str) -> dict:
        b = pdef or {}
        felder = dict(b.get("felder") or {})
        ist_pos = block_wiederholend(b) or typ == "positionen" or typ == wieder
        if ist_pos and art == "kopf":
            # Kopffelder aller normalen Blöcke (Kunde und Beleg nicht über typ kollidieren)
            for pb in profil.get("bloecke") or []:
                if block_wiederholend(pb) or str(pb.get("typ") or "") == "positionen":
                    continue
                for k, d in (pb.get("felder") or {}).items():
                    if k not in felder and isinstance(d, dict):
                        d2 = dict(d)
                        d2["optional"] = True
                        d2.pop("position", None)
                        felder[k] = d2
        global_f = (profil.get("felder") or {}).get("kopf" if art == "kopf" else "position") or {}
        for k, d in global_f.items():
            felder.setdefault(k, d)
        if art == "kopf":
            return {k: v for k, v in felder.items() if _ist_kopffeld(k)}
        return {k: v for k, v in felder.items() if not _ist_kopffeld(k)}

    for bl in roh_bloecke:
        typ = str(bl.get("typ") or typ_fuer(bl["kopf"], profil) or "")
        pdef = profil_block_zu(bl, profil)
        if pdef.get("typ") and not typ:
            typ = str(pdef.get("typ") or "")
        if bl.get("ohne_anfang"):
            fehler.append(
                _pruefen(
                    f"Zeile {bl['start']}: Datei beginnt nicht mit einer Kopfzeile, einem Marker oder einem Satzart-Wert"
                )
            )
        for h in bl.get("hinweise") or []:
            fehler.append(h)
        ist_pos = typ == wieder or typ == "positionen" or block_wiederholend(pdef) or block_wiederholend(bl)
        if ist_pos:
            gesehen_positionen += 1
            if gesehen_positionen > 1:
                fehler.append(
                    _pruefen(
                        f"Zeile {bl['start']}: weitere Rechnung in derselben Datei – im Block-Modus nicht vorgesehen"
                    )
                )
        if ist_pos:
            _positionsblock(
                bl,
                defs_fuer(pdef, typ or "positionen", "position"),
                defs_fuer(pdef, typ or "positionen", "kopf"),
                profil,
                pfad,
                kopf,
                positionen,
                fehler,
                notiz_teile,
                tz,
                modus,
                platz,
                ziel_feld,
                trenner,
                verwaist,
                nummern,
            )
        else:
            felder = defs_fuer(pdef, typ, "kopf")
            # auch Zahlungs-/Summenfelder des getroffenen Blocks
            if pdef.get("felder"):
                felder = {**felder, **(pdef.get("felder") or {})}
            for zeile, werte in bl["daten"]:
                row = zeile_zu_row(werte, bl["kopf"])
                roh = feldsatz(row, felder, zeile, fehler, profil, pfad)
                kopf_mergen(kopf, roh, zeile, fehler, typ=typ)
                if "BT-1" in roh and roh["BT-1"][0] not in (None, ""):
                    nummern.add(str(roh["BT-1"][0]).strip())

    if gesehen_positionen == 0 and not positionen:
        fehler.append("Keine Position")
    if len(nummern) > 1:
        fehler.append(
            _pruefen(
                "weitere Rechnung in derselben Datei – im Block-Modus nicht vorgesehen "
                f"({', '.join(sorted(nummern))})"
            )
        )
    if notiz_teile:
        text = "\n".join(notiz_teile).strip("\n")
        if text or any(t == "" for t in notiz_teile):
            alt = kopf.get("BT-22")
            bisher = "" if not alt or alt[0] in (None, "") else str(alt[0])
            kopf["BT-22"] = (
                _anhaengen(bisher, text, "\n"),
                Herkunft(f"csv:{pfad.name} Textzeile", 1.0),
            )

    for k in [x for x in kopf if str(x).startswith("_typ_")]:
        kopf.pop(k, None)
    key = str((kopf.get("BT-1") or ("",))[0] or "")
    return OrderedDict([(key, (kopf, positionen, fehler))])


def _positionsblock(
    bl,
    pos_felder,
    kopf_felder,
    profil,
    pfad,
    kopf,
    positionen,
    fehler,
    notiz_teile,
    tz,
    modus,
    platz,
    ziel_feld,
    trenner,
    verwaist,
    nummern,
):
    felder = {**kopf_felder, **pos_felder}
    # text_spalte ins Textfeld hängen
    if tz.get("text_spalte") and "text" not in felder:
        felder = {**felder, "text": {"spalte": tz["text_spalte"], "optional": True}}

    typ = str(bl.get("typ") or "positionen")
    for zeile, werte in bl["daten"]:
        row = zeile_zu_row(werte, bl["kopf"])
        if _leer_zeile(werte):
            continue
        roh_pos = feldsatz(row, pos_felder, zeile, fehler, profil, pfad)
        roh_kopf = feldsatz(row, kopf_felder, zeile, fehler, profil, pfad)
        kopf_mergen(kopf, roh_kopf, zeile, fehler, typ=typ)
        if roh_kopf.get("BT-1") and roh_kopf["BT-1"][0] not in (None, ""):
            nummern.add(str(roh_kopf["BT-1"][0]).strip())

        from . import csv_zeilen

        art = csv_zeilen.erkennen(row, pos_felder, kopf_felder, tz)
        if art and art[0] == "preis_ohne_menge":
            pom = str(tz.get("preis_ohne_menge") or "pruefen")
            if pom == "kommentar":
                art = ("text", art[1])
            else:
                if pom == "eins":
                    roh_pos["_menge_eins"] = True
                art = None
        if art is None:
            wartend = bl.setdefault("_zeilen_davor", [])
            if wartend:
                verw = str(tz.get("verwaist") or "BT-22")
                if not positionen and verw == "naechste":
                    for txt in wartend:
                        text_an_roh(roh_pos, txt, txt == "", tz, zeile, pfad)
                elif not positionen:
                    notiz_teile.extend(wartend)
                else:
                    for txt in wartend:
                        text_an_roh(roh_pos, txt, txt == "", tz, zeile, pfad)
                wartend.clear()
            positionen.append(roh_pos)
            continue

        kind, text = art
        if kind == "skip":
            continue
        leerzeile = kind == "leer"
        zwischen = str(tz.get("zwischen") or "vorher")
        if not positionen:
            if verwaist == "pruefen":
                fehler.append(_pruefen(f"Zeile {zeile}: Textzeile ohne Position"))
            elif verwaist == "naechste" or zwischen == "nachher":
                bl.setdefault("_zeilen_davor", []).append("" if leerzeile else text)
            else:
                notiz_teile.append("" if leerzeile else text)
            continue
        if zwischen == "nachher":
            bl.setdefault("_zeilen_davor", []).append("" if leerzeile else text)
            continue
        last = positionen[-1]
        text_an_roh(last, text, leerzeile, tz, zeile, pfad)

    # Rest nach der letzten Position (zwischen=nachher)
    rest = bl.get("_zeilen_davor") or []
    if rest and positionen:
        for txt in rest:
            text_an_roh(positionen[-1], txt, txt == "", tz, 0, pfad)
        rest.clear()


def _kopffelder_ohne_leerpflicht(row: dict, felder: dict, tz: dict) -> bool:
    """Zeile hat mindestens ein Kopffeld, und die als „leer“ konfigurierten Felder sind leer."""
    leer_felder = tz.get("leer") or list(_LEER_STANDARD)
    for name in leer_felder:
        if name == "text":
            if _text_aus_zeile(row, felder, tz):
                return False
            continue
        d = felder.get(name) or {}
        sp = d.get("spalte")
        if sp and (row.get(sp) or "").strip():
            return False
    # irgendein anderes, nicht-leeres Feld (typisch Rechnungsnr)
    Pflicht = set()
    for name in leer_felder:
        if name == "text":
            Pflicht.add(tz.get("text_spalte") or (felder.get("BT-153") or {}).get("spalte"))
        else:
            Pflicht.add((felder.get(name) or {}).get("spalte"))
    for sp, val in row.items():
        if sp in Pflicht or not (val or "").strip():
            continue
        return True
    return False


def genutzte_spalten_wortlaut(profil: dict) -> list[str]:
    """Zugeordnete Spaltennamen in der Schreibweise des Profils (jeder normierte Name einmal)."""
    gesehen: set[str] = set()
    aus: list[str] = []

    def add(s: str) -> None:
        n = name_norm(s)
        if n and n not in gesehen:
            gesehen.add(n)
            aus.append(s.strip())

    for b in profil.get("bloecke") or []:
        for d in (b.get("felder") or {}).values():
            if isinstance(d, dict) and d.get("spalte"):
                add(str(d["spalte"]))
    for teil in (profil.get("felder") or {}).values():
        if isinstance(teil, dict):
            for d in teil.values():
                if isinstance(d, dict) and d.get("spalte"):
                    add(str(d["spalte"]))
    return aus


def kopf_namen_in_datei(zeilen: list[list[str]], profil: dict) -> set[str]:
    """Normierte Namen in erkannten Kopfzeilen der Datei (nicht in gespeicherten kopfzeile-Vorgaben)."""
    aus: set[str] = set()
    namen = genutzte_namen(profil)
    n = schwelle(profil)
    nach_marker = False
    for row in zeilen:
        if _leer_zeile(row):
            continue
        if ist_markerzeile(row, profil) or (
            not marker_im_profil(profil) and sieht_nach_marker_heuristik(row)
        ):
            nach_marker = True
            continue
        if (
            nach_marker
            or ist_exakte_kopfzeile(row, profil)
            or ist_kopfzeile(row, namen, n)
        ):
            for c in row:
                nn = name_norm(c)
                if nn:
                    aus.add(nn)
        nach_marker = False
    return aus


def _namen_ohne_kopfzeile(profil: dict, bloecke: list[dict]) -> set[str]:
    """Spalten eines per Marker ohne Kopfzeile erkannten Blocks müssen nicht in der Datei stehen."""
    typen = {
        str(bl.get("typ") or "")
        for bl in bloecke
        if bl.get("ohne_kopfzeile") and (bl.get("marker") or bl.get("satzart"))
    }
    typen.discard("")
    aus: set[str] = set()
    for b in profil.get("bloecke") or []:
        if str(b.get("typ") or "") not in typen:
            continue
        for d in (b.get("felder") or {}).values():
            if isinstance(d, dict) and d.get("spalte"):
                aus.add(name_norm(str(d["spalte"])))
    return aus


def passt(zeilen: list[list[str]], profil: dict) -> tuple[bool, str]:
    """Ob die Datei zu diesem Block-Profil passt. Pflichtprüfung erst an der Rechnung.

    Ab 0.9.9.1 müssen alle zugeordneten Spaltennamen als Kopfzeile in der Datei
    vorkommen (außer in einem per Marker ohne Kopfzeile eröffneten Block).
    So zieht ein älteres Profil eine fremde Datei nicht mehr nur wegen ein paar
    gemeinsamer Namen (z. B. Rechnungsnr, Artikel) an sich.
    """
    if not genutzte_namen(profil) and not any(
        (b.get("kopfzeile") or b.get("marker")) for b in (profil.get("bloecke") or [])
    ):
        return False, "Im Profil sind keine Spaltennamen hinterlegt"
    bloecke = schneiden_profil(zeilen, 1, profil)
    if not bloecke:
        return False, "Keine Block-Kopfzeile erkannt"
    wieder = wiederholender_typ(profil)
    typen = [str(b.get("typ") or typ_fuer(b["kopf"], profil) or "") for b in bloecke]
    if wieder not in typen and "positionen" not in typen:
        return False, "Kein Positionsblock erkannt"
    vorhanden = kopf_namen_in_datei(zeilen, profil)
    erlassen = _namen_ohne_kopfzeile(profil, bloecke)
    fehlend = [
        w
        for w in genutzte_spalten_wortlaut(profil)
        if name_norm(w) not in vorhanden and name_norm(w) not in erlassen
    ]
    if fehlend:
        return False, "Spalten des Profils fehlen in der Datei: " + ", ".join(fehlend)
    pos = next(b for b, typ in zip(bloecke, typen) if typ == wieder or typ == "positionen")
    return True, f"{len(bloecke)} Block/Blöcke erkannt, Positionsblock in Zeile {pos['start']}"
