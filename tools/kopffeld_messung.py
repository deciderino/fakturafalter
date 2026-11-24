# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Messung der Kopffeld-Erkennung (Käufer- und Absenderanschrift) am Testset tests/daten/kopffeld/.

Drei Wege je Variante, alles offline (die Messung selbst ändert nichts am Produktionscode):

* ``kalt``    – Assistent ohne Vorlage (``anlernen.Sitzung``: Fensterblock-Heuristik, Absender aus dem Druck),
* ``rahmen``  – Nutzer-Rahmen um die DIN-5008-Anschriftzone (``pdferkennung.anschrift_im_rahmen``),
* ``vorlage`` – Block-Regel am Vorlagen-Beleg (einfacher Inlandskunde) angelernt, dann den Beleg gelesen
  (``pdferkennung.anschrift_auslesen``); kein Block am Vorlagen-Beleg -> alle Felder „fehlt“.

Bewertung: Vermerkzeilen über der Straße („Abteilung“, „c/o“, „z. Hd.“ …) nach der Zielabbildung
``benchmark.kaeufer_ziel`` (Nutzer-Entscheid 23.11.2026: BT-51/BT-163/BT-56). Sonst feste Regel 0.4.4: Name = BT-44
gleich „Namenszeilen + Zusatz über der Straße“ (BT-51 leer) oder
BT-44 = Namenszeilen und BT-51 = Zusatz. Zusatz unter der Straße darf in BT-44/BT-51 stehen oder fehlen, aber nicht
in Straße/Ort. Straße, PLZ, Ort, Land (leer = DE, Vorgabe im Modell) müssen exakt stimmen (Leerraum normiert).
Falsch gefüllt mit Prüfhinweis zur Anschrift (``pdferkennung.anschrift_brueche``) zählt als „prüfen“, ohne Hinweis
als „still falsch“; ein Hinweis an einem richtig gelesenen Beleg ist ein Fehlalarm.

    python tools/kopffeld_messung.py [--md kopffeld.md] [--json kopffeld.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "src"))
sys.path.insert(0, str(WURZEL / "tools"))

import benchmark  # noqa: E402

from fakturafalter import anlernen, pdferkennung  # noqa: E402

SET = WURZEL / "tests" / "daten" / "kopffeld"
FELDER = ("name", "zusatz", "strasse", "plz", "ort", "land")
WEGE = ("kalt", "rahmen", "vorlage")
ABS_FELDER = ("name", "strasse", "plz", "ort")


def _n(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def bewerten(soll: dict, ist: dict) -> dict[str, bool | None]:
    """Soll-Käufer gegen gelesene Teile (BT-44 … BT-55) -> Feld -> richtig (None = nicht anwendbar)."""
    name, oben, unten = soll["name_zeilen"], soll["zusatz_oben"], soll["zusatz_unten"]
    b44, b51 = _n(ist.get("BT-44")), _n(ist.get("BT-51"))
    voll = _n(" ".join(name + oben))
    ziel = benchmark.kaeufer_ziel(name + oben)
    rest = " ".join(_n(ist.get(f)) for f in ("BT-50", "BT-52", "BT-53"))
    zus = None
    if ziel["BT-51"] or ziel["BT-56"]:  # Vermerkzeilen über der Straße: nur die Zielabbildung (23.11.2026) zählt
        ok_name = all(_n(ist.get(f)) == _n(ziel[f]) for f in ("BT-44", "BT-51", "BT-163", "BT-56"))
        zus = ok_name and not any(_n(t) in rest for t in oben + unten)
    else:
        ok_name = (b44 == voll and (not b51 or b51 == _n(" ".join(unten)))) \
            or (bool(oben) and b44 == _n(" ".join(name)) and b51 == _n(" ".join(oben + unten))) \
            or (bool(unten) and b44 == _n(" ".join(name + oben + unten)) and not b51)
        if oben or unten:
            zus = bool(b44) and all(_n(t) in f"{b44} {b51}" for t in oben) \
                and not any(_n(t) in rest for t in oben + unten)
    land = _n(ist.get("BT-55")) or "DE"
    return {"name": ok_name, "zusatz": zus, "strasse": _n(ist.get("BT-50")) == _n(soll["strasse"]),
            "plz": _n(ist.get("BT-53")) == soll["plz"], "ort": _n(ist.get("BT-52")) == _n(soll["ort"]),
            "land": land == soll["land"]}


def _sitzung(pdf: Path, k) -> anlernen.Sitzung:
    return anlernen.Sitzung(Path(shutil.copy(pdf, k.eingang)), k)


def messen(set_ordner: Path = SET) -> list[dict]:
    vorher = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return _messen(set_ordner)
    finally:
        logging.disable(vorher)


def _messen(set_ordner: Path) -> list[dict]:
    soll = json.loads((set_ordner / "soll.json").read_text(encoding="utf-8"))
    out = []
    with tempfile.TemporaryDirectory(prefix="ff-kopffeld-") as t:
        tmp = Path(t)
        alt = pdferkennung.ablage
        pdferkennung.ablage = lambda profil: tmp / "angelernt" / pdferkennung.profil_name(profil)
        try:
            k = benchmark._konfig(benchmark.PE / "konfiguration.yaml", tmp)
            k.eingang.mkdir(parents=True, exist_ok=True)
            for v in soll:
                pdf = set_ordner / f"{v['id']}.pdf"
                s = _sitzung(pdf, k)
                ist = {"kalt": {f: s.werte[f].wert for f in pdferkennung.BLOCKFELDER + ("BT-55",) if f in s.werte}}
                ist["kalt"].update(s._kaeufer_nebenfelder())  # BT-56/BT-163 aus dem Block
                hinweise = {"kalt": dict(getattr(s, "anschrift_hinweise", {}))}   # vor Kopffeld Schritt 1: keine
                zs = [z for z in s.zeilen if z.seite == 0]
                ist["rahmen"], zeilen_ws = pdferkennung.anschrift_im_rahmen(zs, tuple(v["layout"]["zone"]))
                brueche = getattr(pdferkennung, "anschrift_brueche", lambda _: {})
                hinweise["rahmen"] = brueche(zeilen_ws) if zeilen_ws else {}
                sv = _sitzung(set_ordner / f"{v['id']}-vorlage.pdf", k)
                block = sv.anschrift_block or sv._block_vorschlag
                hinweise["vorlage"] = {}
                try:
                    ist["vorlage"] = pdferkennung.anschrift_auslesen({"seite": block[0], "rahmen": list(block[1])}, zs,
                                                                     hinweise["vorlage"]) if block else {}
                except TypeError:                     # vor Kopffeld Schritt 1: ohne Hinweis-Ausgabe
                    ist["vorlage"] = pdferkennung.anschrift_auslesen({"seite": block[0], "rahmen": list(block[1])},
                                                                     zs) if block else {}
                ist["vorlage"] = {f: (x[0] if isinstance(x, tuple) else x) for f, x in ist["vorlage"].items()}
                erg = {w: bewerten(v["kaeufer"], ist[w]) for w in WEGE}
                a = s.absender
                erg["absender"] = {f: _n(getattr(a, f)) == _n(v["absender"][f]) for f in ABS_FELDER}
                out.append({"id": v["id"], "text": v["text"], "holdout": v["holdout"], "ist": ist, "hinweise": hinweise,
                            "vorlage_block": bool(block), "ergebnis": erg,
                            "absender_ist": {f: getattr(a, f) for f in ABS_FELDER}})
        finally:
            pdferkennung.ablage = alt
    return out


def _quote(faelle, weg, feld) -> str:
    werte = [f["ergebnis"][weg][feld] for f in faelle if f["ergebnis"][weg][feld] is not None]
    return f"{sum(werte)}/{len(werte)}" if werte else "–"


def _ganz(f, weg) -> bool:
    return all(x is not False for x in f["ergebnis"][weg].values())


QUELLE = {"name": "BT-44", "zusatz": "BT-44", "strasse": "BT-50", "plz": "BT-53", "ort": "BT-52", "land": "BT-55"}


def _hinweise(f, weg) -> dict:
    return (f.get("hinweise") or {}).get(weg) or {}


def status(f, weg) -> str:
    """„richtig“, „leer“ (Fehler nur durch fehlende Werte – der Nutzer sieht die Lücke), „prüfen“ (falsch gefüllt,
    aber mit Prüfhinweis zum Anschriftblock gemeldet) oder „falsch“ (mindestens ein Feld still falsch gefüllt)."""
    if _ganz(f, weg):
        return "richtig"
    ist = f["ist"][weg]
    falsch = [x for x, ok in f["ergebnis"][weg].items() if ok is False and _n(ist.get(QUELLE[x]))]
    if not falsch:
        return "leer"
    return "prüfen" if _hinweise(f, weg) else "falsch"


def fehlalarm(f, weg) -> bool:
    """Richtig gelesen, trotzdem ein Prüfhinweis zum Anschriftblock."""
    return _ganz(f, weg) and bool(_hinweise(f, weg))


def bericht(faelle: list[dict]) -> str:
    z = ["# Kopffeld-Messung (Ist-Stand)", "",
         f"{len(faelle)} Varianten, davon {sum(f['holdout'] for f in faelle)} Hold-out. "
         "Bewertung siehe tools/kopffeld_messung.py (feste Regel: Name + Zusatz zusammen in BT-44 ist richtig).", "",
         "## Quoten je Feld", "", "| Weg | Teil | " + " | ".join(FELDER) + " | alle Felder |",
         "|---|---|" + "---|" * (len(FELDER) + 1)]
    for weg in WEGE:
        for teil, fs in (("Entwicklung", [f for f in faelle if not f["holdout"]]),
                         ("Hold-out", [f for f in faelle if f["holdout"]])):
            z.append(f"| {weg} | {teil} | " + " | ".join(_quote(fs, weg, x) for x in FELDER)
                     + f" | {sum(_ganz(f, weg) for f in fs)}/{len(fs)} |")
    z += ["", "## Fehlerart je Weg (lieber prüfen als falsch)", "",
          "„leer“ = Felder bleiben leer (Nutzer muss nachtragen), „prüfen“ = falsch gefüllt, aber mit Prüfhinweis "
          "zum Anschriftblock gemeldet, „still falsch“ = mindestens ein Feld ohne Hinweis falsch gefüllt; "
          "Fehlalarm = richtig, trotzdem Prüfhinweis.", "",
          "| Weg | Teil | richtig | leer | prüfen | still falsch | Fehlalarm |", "|---|---|---|---|---|---|---|"]
    for weg in WEGE:
        for teil, fs in (("alle", faelle), ("Hold-out", [f for f in faelle if f["holdout"]])):
            c = Counter(status(f, weg) for f in fs)
            z.append(f"| {weg} | {teil} | {c['richtig']} | {c['leer']} | {c['prüfen']} | {c['falsch']} | "
                     f"{sum(fehlalarm(f, weg) for f in fs)} |")
    z += ["", "Absender (Assistent, aus dem Druck): " + ", ".join(
        f"{x} {sum(f['ergebnis']['absender'][x] for f in faelle)}/{len(faelle)}" for x in ABS_FELDER), "",
        "## Je Variante", "", "Zeichen: ✓ richtig, ✗ falsch, · nicht anwendbar; Reihenfolge Name Zusatz Straße PLZ Ort "
        "Land; Absender Name Straße PLZ Ort.", "",
        "| Variante | HO | Beschreibung | kalt | rahmen | vorlage | Absender |", "|---|---|---|---|---|---|---|"]
    kurz = {"richtig": "", "leer": " (leer)", "prüfen": " (prüfen)", "falsch": " (falsch)"}

    def zeichen(d, fs):
        return "".join("·" if d[x] is None else ("✓" if d[x] else "✗") for x in fs)
    for f in faelle:
        e = f["ergebnis"]
        z.append(f"| {f['id']} | {'H' if f['holdout'] else ''} | {f['text']} | "
                 + " | ".join(zeichen(e[w], FELDER) + kurz[status(f, w)] for w in WEGE) + " | "
                 + f"{zeichen(e['absender'], ABS_FELDER)} |")
    z += ["", "## Gelesene Werte bei Fehlern (Weg kalt)", "", "| Variante | BT-44 | BT-51 | BT-50 | BT-53 | BT-52 |",
          "|---|---|---|---|---|---|"]
    for f in faelle:
        if not _ganz(f, "kalt"):
            i = f["ist"]["kalt"]
            z.append(f"| {f['id']} | " + " | ".join(_n(i.get(x)).replace("|", "/") or "–"
                                                   for x in ("BT-44", "BT-51", "BT-50", "BT-53", "BT-52")) + " |")
    z += ["", "## Gelesene Werte bei Fehlern (Weg rahmen)", "", "| Variante | BT-44 | BT-51 | BT-50 | BT-53 | BT-52 |",
          "|---|---|---|---|---|---|"]
    for f in faelle:
        if not _ganz(f, "rahmen"):
            i = f["ist"]["rahmen"]
            z.append(f"| {f['id']} | " + " | ".join(_n(i.get(x)).replace("|", "/") or "–"
                                                   for x in ("BT-44", "BT-51", "BT-50", "BT-53", "BT-52")) + " |")
    z += ["", "## Prüfhinweise Anschrift (je Weg)", "", "| Variante | Weg | Feld | Hinweis |", "|---|---|---|---|"]
    for f in faelle:
        for weg in WEGE:
            for feld, text in sorted(_hinweise(f, weg).items()):
                z.append(f"| {f['id']} | {weg} | {feld} | {text} |")
    fehl = Counter()
    for f in faelle:
        for weg in WEGE:
            for x in FELDER:
                if f["ergebnis"][weg][x] is False:
                    fehl[(weg, x)] += 1
    z += ["", "## Fehler je Weg und Feld", "", "| Weg | Feld | Fehler |", "|---|---|---|"]
    z += [f"| {w} | {x} | {n} |" for (w, x), n in sorted(fehl.items(), key=lambda kv: -kv[1])]
    return "\n".join(z) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", type=Path, default=SET)
    ap.add_argument("--md", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    faelle = messen(a.set)
    text = bericht(faelle)
    if a.md:
        a.md.parent.mkdir(parents=True, exist_ok=True)
        a.md.write_text(text, encoding="utf-8")
    if a.json:
        a.json.write_text(json.dumps(faelle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
