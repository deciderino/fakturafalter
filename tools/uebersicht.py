# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kurzübersicht eines Messordners von ``tools/messen.sh`` (oder Vergleich zweier):

    python tools/uebersicht.py ORDNER [ORDNER2]
Je Verfahren: Feldtreffer, fehlerfreie Belege, Fehlschläge leer/prüfen/still falsch; Seeds summiert; Kopffeld
(Fehlerart je Weg). Mit zwei Ordnern: „vorher -> nachher“ und am Ende jede Verschlechterung.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _bench(p: Path) -> dict[str, tuple]:
    e = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for v, tab in e["tabellen"].items():
        t, g = sum(z["treffer"] for z in tab), sum(z["gesamt"] for z in tab)
        fa = e.get("fehlarten", {}).get(v, {})
        b = e["belege_fehlerfrei"].get(v, [0, 0])
        out[v] = (t, g, b[0], fa.get("leer", 0), fa.get("pruefen", 0), fa.get("still", 0))
    return out


def _seeds(o: Path) -> dict[str, tuple]:
    out = {}
    for p in sorted(o.glob("seed*.json")):
        out[f"assistent {p.stem}"] = _bench(p)["assistent"]
    return out


def _kopffeld(o: Path) -> dict[str, tuple]:
    out, an = {}, False
    for z in (o / "kopffeld.md").read_text(encoding="utf-8").splitlines():
        if z.startswith("## Fehlerart"):
            an = True
        elif z.startswith("## "):
            an = False
        elif an and z.startswith("| ") and not z.startswith("| Weg") and not z.startswith("|---"):
            c = [x.strip() for x in z.strip("|").split("|")]
            out[f"kopffeld {c[0]} {c[1]}"] = tuple(int(x) for x in c[2:7])
    return out


def laden(o: Path) -> dict[str, dict[str, tuple]]:
    return {"benchmark": _bench(o / "benchmark.json"), "seeds": _seeds(o), "kopffeld": _kopffeld(o)}


KOPF = {"benchmark": "Verfahren | Felder richtig | Belege fehlerfrei | leer | prüfen | still falsch",
        "seeds": "Seed (100 Generator + feste Belege) | Felder richtig | Belege fehlerfrei | leer | prüfen | still falsch",
        "kopffeld": "Kopffeld Weg/Teil | richtig | leer | prüfen | still falsch | Fehlalarm"}


def _zelle(x: tuple | None, i: int, art: str) -> str:
    if x is None:
        return "–"
    if art != "kopffeld" and i == 0:
        return f"{x[0]}/{x[1]}"
    return str(x[i + 1] if art != "kopffeld" else x[i])


def _schlechter(art: str, a: tuple, b: tuple) -> bool:
    if art == "kopffeld":     # richtig, leer, prüfen, still, Fehlalarm
        return b[0] < a[0] or b[3] > a[3]
    return b[0] < a[0] or b[2] < a[2] or b[5] > a[5]


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    a = laden(Path(argv[0]))
    b = laden(Path(argv[1])) if len(argv) > 1 else None
    schlecht = []
    for art in ("benchmark", "seeds", "kopffeld"):
        print(f"\n| {KOPF[art]} |\n|" + "---|" * (KOPF[art].count("|") + 1))
        n = 5
        for k in list(a[art]) + [k for k in (b or {}).get(art, {}) if k not in a[art]]:
            x, y = a[art].get(k), (b[art].get(k) if b else None)
            if b is None:
                print(f"| {k} | " + " | ".join(_zelle(x, i, art) for i in range(n)) + " |")
            else:
                zellen = []
                for i in range(n):
                    s, t = _zelle(x, i, art), _zelle(y, i, art)
                    zellen.append(s if s == t else f"{s} → **{t}**")
                print(f"| {k} | " + " | ".join(zellen) + " |")
                if x and y and _schlechter(art, x, y) or (x and not y):
                    schlecht.append(k)
    if b is not None:
        print("\nVerschlechtert:", ", ".join(schlecht) if schlecht else "nichts")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
