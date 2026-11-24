# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Adapter PDF (Textebene): Druck-PDF + Zonen-/Anker-Vorlage -> Rechnungen.

Nutzt pdfplumber (MIT). Koordinaten in Punkt, Ursprung oben links.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pdfplumber
from pdfminer import psparser as _psparser

from .aufbau import Roh, rechnung_bauen
from .konfig import Konfig, kundenstamm_fuer
from .modell import Herkunft, Rechnung
from .werte import WertFehler, datum, ohne_steuerzeichen, zahl

S_ANKER_MUSTER = 0.95
S_ANKER = 0.9
S_BEREICH = 0.8
S_MUSTER_FALSCH = 0.5
S_TABELLE = 0.95


@dataclass
class Seite:
    nr: int  # 0-basiert
    woerter: list[dict]
    text: str
    breite: float
    hoehe: float


@dataclass
class Teil:  # eine Rechnung innerhalb eines Druckauftrags
    seiten: list[Seite] = field(default_factory=list)
    nummer: str | None = None


def _escape_behalten() -> None:
    """pdfminer verwirft ein unbekanntes Escape wie „\\[“ samt Zeichen; laut PDF-Norm (7.3.4.2) bleibt das Zeichen
    stehen. Manche Warenwirtschaften schreiben „\\[EURO\\]“ – ohne Korrektur fehlen die Klammern und alle
    folgenden Zeichen der Zeile rutschen nach links. Zeilenfortsetzung („\\“ + Zeilenende) bleibt unberührt."""
    original = _psparser.PSBaseParser._parse_string_1
    if getattr(original, "_fakturafalter", False):
        return

    def _parse_string_1(self, s: bytes, i: int) -> int:
        c = s[i : i + 1]
        if (
            not self.oct
            and c
            and not _psparser.OCT_STRING.match(c)
            and c not in _psparser.ESC_STRING
            and c not in (b"\r", b"\n")
        ):
            self._curtoken += c
            self._parse1 = self._parse_string
            return i + 1
        return original(self, s, i)

    _parse_string_1._fakturafalter = True
    _psparser.PSBaseParser._parse_string_1 = _parse_string_1


_escape_behalten()


def _ist_weiss(farbe) -> bool:
    """Füll- oder Strichfarbe ist Weiß (RGB/Grau ≈ 1, CMYK ≈ 0)."""
    if farbe is None:
        return False
    if isinstance(farbe, (int, float)):
        return float(farbe) >= 0.99
    if not isinstance(farbe, (list, tuple)) or not farbe:
        return False
    werte = [float(x) for x in farbe]
    if len(werte) == 4:  # CMYK: Papierweiß
        return all(v <= 0.01 for v in werte)
    return all(v >= 0.99 for v in werte)


def _ueberlappt(a: dict, b: dict) -> bool:
    return (
        a["x0"] < b["x1"]
        and a["x1"] > b["x0"]
        and a["top"] < b["bottom"]
        and a["bottom"] > b["top"]
    )


def _seite_ohne_artefakte(page):
    """Doppelte Zeichen entfernen; weiße Zeichen ohne dunklen Hintergrund und gedrehte Zeichen weglassen.

    Weißer Text auf einem dunklen Balken (Tabellenkopf) oder Logo bleibt – das ist lesbarer Druck, kein Artefakt.
    """
    hinter = [
        o
        for o in list(page.rects) + list(page.curves) + list(getattr(page, "images", None) or [])
        if o.get("object_type") == "image"
        or (o.get("fill") and not _ist_weiss(o.get("non_stroking_color")))
    ]

    def sichtbar(obj) -> bool:
        if obj.get("object_type") != "char":
            return True
        if obj.get("upright") is False:
            return False
        if not _ist_weiss(obj.get("non_stroking_color")):
            return True
        return any(_ueberlappt(obj, h) for h in hinter)

    return page.dedupe_chars().filter(sichtbar)


def seiten_lesen(pfad: Path) -> list[Seite]:
    out = []
    with pdfplumber.open(str(pfad)) as pdf:
        for i, p in enumerate(pdf.pages):
            p = _seite_ohne_artefakte(p)
            ws = p.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
            for w in ws:  # „(cid:10)“ u. ä. – siehe werte.ohne_steuerzeichen
                w["text"] = ohne_steuerzeichen(w["text"])
            ws = [w for w in ws if w["text"]]
            out.append(
                Seite(
                    i,
                    ws,
                    ohne_steuerzeichen(p.extract_text() or ""),
                    float(p.width),
                    float(p.height),
                )
            )
    return out


def zeilen(woerter: list[dict], tol: float = 3) -> list[tuple[float, list[dict]]]:
    out: list[list] = []
    for w in sorted(woerter, key=lambda w: (round(w["top"]), w["x0"])):
        if out and abs(out[-1][0] - w["top"]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    return [(t, sorted(ws, key=lambda w: w["x0"])) for t, ws in out]


def _anker_finden(woerter: list[dict], anker: str):
    aw = anker.split()
    srt = sorted(woerter, key=lambda w: (round(w["top"]), w["x0"]))
    for i in range(len(srt)):
        kette = srt[i : i + len(aw)]
        if [w["text"] for w in kette] == aw and all(
            abs(w["top"] - kette[0]["top"]) <= 3 for w in kette
        ):
            return kette[-1]
    return None


def wert_rechts(woerter: list[dict], anker: str, max_abstand: float = 150) -> str | None:
    a = _anker_finden(woerter, anker)
    if a is None:
        return None
    kand = [
        w
        for w in woerter
        if abs(w["top"] - a["top"]) <= 3 and 0 <= w["x0"] - a["x1"] <= max_abstand
    ]
    if not kand:
        return ""
    # bis zur ersten großen Lücke (> 3 Leerzeichen breit) lesen
    kand.sort(key=lambda w: w["x0"])
    teile, ende = [kand[0]], kand[0]["x1"]
    for w in kand[1:]:
        if w["x0"] - ende > 20:
            break
        teile.append(w)
        ende = w["x1"]
    return " ".join(w["text"] for w in teile)


def bereich_text(seite: Seite, b: dict, ignorieren: list[str] = ()) -> str:
    ws = [
        w
        for w in seite.woerter
        if w["x0"] >= b["x0"]
        and w["x1"] <= b["x1"]
        and w["top"] >= b["top"]
        and w["bottom"] <= b["bottom"]
    ]
    out = []
    for _, line in zeilen(ws):
        t = " ".join(w["text"] for w in line)
        if not any(re.search(m, t) for m in ignorieren):
            out.append(t)
    return "\n".join(out)


def vorlage_passt(seiten: list[Seite], vorlage: dict) -> bool:
    if not seiten:
        return False
    erk = vorlage.get("erkennung", {})
    text = seiten[0].text
    if not all(ohne_steuerzeichen(t) in text for t in erk.get("enthaelt_text", [])):
        return False
    if erk.get("seitengroesse") == "A4":
        s = seiten[0]
        if not (abs(s.breite - 595) < 5 and abs(s.hoehe - 842) < 5):
            return False
    return True


def zerlegen(seiten: list[Seite], vorlage: dict) -> list[Teil]:
    tr = vorlage.get("trennung", {})
    bt1 = vorlage.get("felder", {}).get("BT-1", {})
    teile: list[Teil] = []
    for s in seiten:
        if not s.woerter:
            continue  # leere Seite
        nr = (
            wert_rechts(s.woerter, bt1.get("anker", ""), bt1.get("max_abstand", 150))
            if bt1
            else None
        )
        neu = not teile
        for regel in tr.get("neue_rechnung_wenn", []):
            if "feld_wechselt" in regel and teile and nr and nr != teile[-1].nummer:
                neu = True
            if "text_muster" in regel and re.search(regel["text_muster"], s.text):
                neu = True
        if neu:
            teile.append(Teil(nummer=nr))
        teile[-1].seiten.append(s)
    return teile


def _typ(roh: str, d: dict, vorlage: dict):
    zs = vorlage.get("zahlen", {})
    if d.get("typ") == "zahl":
        return zahl(roh, zs.get("dezimal", ","), zs.get("tausender", "."))
    if d.get("typ") == "datum":
        return datum(roh, d.get("format", "%d.%m.%Y"))
    return roh


def _kopf(teil: Teil, vorlage: dict, pfad: Path, fehler: list[str], hinweise: list[tuple]) -> Roh:
    roh: Roh = {}
    for feld, d in vorlage.get("felder", {}).items():
        if d.get("zweck") == "pruefung":
            continue
        gefunden = None
        for s in teil.seiten:
            if "anker" in d:
                v = wert_rechts(s.woerter, d["anker"], d.get("max_abstand", 150))
                if v:
                    sich = S_ANKER
                    if d.get("muster"):
                        m = re.search(d["muster"], v)
                        if m:
                            v, sich = m.group(0), S_ANKER_MUSTER
                        else:
                            sich = S_MUSTER_FALSCH
                    gefunden = (
                        v,
                        Herkunft(f"pdf:{pfad.name} S.{s.nr + 1} Anker „{d['anker']}“", sich),
                    )
            elif "bereich" in d:
                b = d["bereich"]
                if b.get("seite", 1) - 1 == s.nr - teil.seiten[0].nr:
                    v = bereich_text(s, b, d.get("zeilen_ignorieren", []))
                    if v:
                        gefunden = (v, Herkunft(f"pdf:{pfad.name} S.{s.nr + 1} Bereich", S_BEREICH))
            if gefunden:
                if d.get("alle_seiten_gleich") and feld in roh and roh[feld][0] != gefunden[0]:
                    fehler.append(f"{feld} unterscheidet sich zwischen den Seiten")
                if feld not in roh:
                    roh[feld] = gefunden
                if not d.get("alle_seiten_gleich"):
                    break
        if feld in roh:
            try:
                roh[feld] = (_typ(roh[feld][0], d, vorlage), roh[feld][1])
            except WertFehler as e:
                hinweise.append(("pruefen", f"{e}", feld))
                del roh[feld]
        elif not d.get("optional"):
            hinweise.append(("pruefen", "nicht gefunden", feld))
    return roh


def _positionen(teil: Teil, vorlage: dict, pfad: Path, hinweise: list[tuple]) -> list[Roh]:
    pv = vorlage.get("positionen", {})
    spalten: dict = pv.get("spalten", {})
    # Zahlen (rechte Kante) zuerst, dann Text nach linker Kante; Rest-Spalte zuletzt
    reihenfolge = sorted(
        spalten.items(),
        key=lambda kv: (
            0 if "rechte_kante" in kv[1] else (2 if kv[1].get("rest_bis_naechste_spalte") else 1)
        ),
    )
    out: list[Roh] = []
    ende = False
    for s in teil.seiten:
        if ende:
            break
        in_tab = False
        for top, line in zeilen(s.woerter):
            txt = " ".join(w["text"] for w in line)
            if re.search(pv.get("start_nach_zeile", "$^"), txt):
                in_tab = True
                continue
            if not in_tab:
                continue
            if any(re.search(m, txt) for m in pv.get("zeilen_ignorieren", [])):
                continue
            if any(re.search(m, txt) for m in pv.get("ende_vor_zeile", [])):
                ende = True
                break
            if top > pv.get("bereich_bis_top", 1e9):
                break
            row: dict[str, list[str]] = {}
            for w in line:
                for k, d in reihenfolge:
                    if "rechte_kante" in d:
                        if abs(w["x1"] - d["rechte_kante"]) <= d.get("toleranz", 3):
                            row.setdefault(k, []).append(w["text"])
                            break
                    elif w["x0"] >= d.get("links_ab", 0) and (
                        d.get("rest_bis_naechste_spalte") or w["x0"] <= d.get("bis", 1e9)
                    ):
                        row.setdefault(k, []).append(w["text"])
                        break
            werte = {k: " ".join(v) for k, v in row.items()}
            herk = Herkunft(f"pdf:{pfad.name} S.{s.nr + 1} y={top:.0f}", S_TABELLE)
            if werte.get("BT-126"):
                roh: Roh = {}
                for k, v in werte.items():
                    try:
                        roh[k] = (_typ(v, spalten[k], vorlage), herk)
                    except WertFehler as e:
                        hinweise.append(("pruefen", f"{e}", f"Pos {werte['BT-126']} {k}"))
                out.append(roh)
            elif out and werte.get("BT-153") and pv.get("folgezeile_ohne_pos") and len(werte) == 1:
                v, h = out[-1].get("BT-153", ("", herk))
                out[-1]["BT-153"] = ((v + " " + werte["BT-153"]).strip(), h)
    return out


def _kontrolle(teil: Teil, vorlage: dict, roh: Roh, hinweise: list[tuple]):
    k = vorlage.get("kontrolle", {})
    letzte = teil.seiten[-1]
    for feld, d in k.items():
        if not isinstance(d, dict) or "anker" not in d:
            continue
        v = wert_rechts(letzte.woerter, d["anker"], d.get("max_abstand", 250))
        if v:
            try:
                roh[feld] = (
                    _typ(v.split()[-1], {"typ": "zahl"}, vorlage),
                    Herkunft("pdf:kontrolle", 1.0),
                )
            except WertFehler:
                hinweise.append(("warnung", f"Kontrollwert unlesbar: {v!r}", feld))


def lesen(
    pfad: Path, vorlage: dict, konfig: Konfig, seiten: list[Seite] | None = None
) -> list[Rechnung]:
    seiten = seiten if seiten is not None else seiten_lesen(pfad)
    rechnungen: list[Rechnung] = []
    tr = vorlage.get("trennung", {})
    for teil in zerlegen(seiten, vorlage):
        fehler: list[str] = []
        hinweise: list[tuple] = []
        kopf = _kopf(teil, vorlage, pfad, fehler, hinweise)
        pos = _positionen(teil, vorlage, pfad, hinweise)
        _kontrolle(teil, vorlage, kopf, hinweise)
        r = rechnung_bauen(kopf, pos, vorlage, konfig, quelle=str(pfad))
        r.sicht_pdf = (str(pfad), [s.nr for s in teil.seiten])
        for f in fehler:
            r.hinweis("fehler", f)
        for st, t, f in hinweise:
            r.hinweis(st, t, f)
        # Seitenzählung lückenlos?
        pv = tr.get("pruefe_vollstaendig", {})
        if pv.get("muster"):
            nummern = []
            for s in teil.seiten:
                m = re.search(pv["muster"], s.text)
                if m:
                    nummern.append((int(m.group("seite")), int(m.group("von"))))
            if nummern and [n for n, _ in nummern] != list(range(1, nummern[0][1] + 1)):
                r.hinweis("pruefen", f"Seitenfolge unvollständig: {nummern}", "Seiten")
        # Anschrift gegen Kundenstamm
        for feld, d in vorlage.get("felder", {}).items():
            if d.get("zweck") == "pruefung" and "bereich" in d and r.kaeufer.name:
                b = d["bereich"]
                s = teil.seiten[min(b.get("seite", 1) - 1, len(teil.seiten) - 1)]
                t = bereich_text(s, b, d.get("zeilen_ignorieren", []))
                erste = r.kaeufer.name.split()[0]
                if erste.lower() not in t.lower():
                    r.hinweis(
                        "warnung",
                        f"Anschrift im Druck passt nicht zum Kundenstamm ({r.kaeufer.name})",
                        feld,
                    )
        rechnungen.append(r)
    return rechnungen


def vorlage_finden(seiten: list[Seite], vorlagen: list[dict]) -> dict | None:
    for v in vorlagen:
        if vorlage_passt(seiten, v):
            return v
    return None


__all__ = ["lesen", "seiten_lesen", "vorlage_finden", "Decimal", "kundenstamm_fuer"]
