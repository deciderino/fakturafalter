# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Zwei Benchmark-Ergebnisse (JSON von ``tools/benchmark.py``) vergleichen: Treffer je Verfahren und Feld,
Fehlarten (leer/prüfen/still falsch) und jeder Fehlschlag, der neu ist oder sich verändert hat.

    python tools/vergleich.py vorher.json nachher.json      # Exit 1, wenn etwas schlechter wurde
"""
from __future__ import annotations

import json
import sys

RANG = {"leer": 1, "pruefen": 0, "still": 2}     # still falsch ist das Schlimmste; leer schlechter als prüfen


def _schluessel(x: dict) -> tuple:
    return x["verfahren"], x["datei"], x["feld"]


def vergleichen(a: dict, b: dict) -> tuple[list[str], bool]:
    out, schlechter = [], False
    for v in sorted(set(a["tabellen"]) | set(b["tabellen"])):
        ta = {z["feld"]: z for z in a["tabellen"].get(v, [])}
        tb = {z["feld"]: z for z in b["tabellen"].get(v, [])}
        for f in list(ta) + [f for f in tb if f not in ta]:
            x, y = ta.get(f), tb.get(f)
            tx, ty = (x or {}).get("treffer", 0), (y or {}).get("treffer", 0)
            gx, gy = (x or {}).get("gesamt", 0), (y or {}).get("gesamt", 0)
            if (tx, gx) != (ty, gy):
                schlechter |= ty < tx or (gx - tx) < (gy - ty)
                out.append(f"{v} | {f}: {tx}/{gx} -> {ty}/{gy}")
        fa, fb = a.get("fehlarten", {}).get(v, {}), b.get("fehlarten", {}).get(v, {})
        if fa != fb:
            schlechter |= fb.get("still", 0) > fa.get("still", 0)
            out.append(f"{v} | Fehlarten: {fa} -> {fb}")
    fa = {_schluessel(x): x for x in a["fehlschlaege"]}
    fb = {_schluessel(x): x for x in b["fehlschlaege"]}
    for k in sorted(set(fa) | set(fb)):
        x, y = fa.get(k), fb.get(k)
        if x and not y:
            out.append(f"  behoben: {k} soll {x['soll']!r} war {x['ist']!r} ({x.get('art')})")
        elif y and not x:
            schlechter = True
            out.append(f"  NEU:     {k} soll {y['soll']!r} ist {y['ist']!r} ({y.get('art')})")
        elif (x["ist"], x.get("art")) != (y["ist"], y.get("art")):
            if RANG.get(y.get("art"), 0) > RANG.get(x.get("art"), 0):
                schlechter = True
            out.append(f"  anders:  {k} soll {y['soll']!r}: {x['ist']!r} ({x.get('art')}) -> {y['ist']!r} ({y.get('art')})")
    return out, schlechter


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    a, b = (json.load(open(p, encoding="utf-8")) for p in argv[:2])
    out, schlechter = vergleichen(a, b)
    print("\n".join(out) or "identisch")
    print("SCHLECHTER" if schlechter else "nicht schlechter")
    return 1 if schlechter else 0


if __name__ == "__main__":
    sys.exit(main())
