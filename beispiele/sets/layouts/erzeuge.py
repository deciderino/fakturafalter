#!/usr/bin/env python3
"""Erzeugt das Layout-Robustheits-Set (alle oder die genannten Familien).

    .venv/bin/python beispiele/sets/layouts/erzeuge.py                # alle Familien
    .venv/bin/python beispiele/sets/layouts/erzeuge.py f01_infozeilen  # nur eine

Deterministisch (fester Seed je Familie, reportlab ``invariant=1``): zwei Läufe sind byte-gleich.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import _rahmen  # noqa: E402


def familien() -> list[Path]:
    return sorted(p for p in HIER.glob("f[0-9][0-9]_*/familie.py"))


def laden(pfad: Path):
    spec = importlib.util.spec_from_file_location(f"layouts_{pfad.parent.name}", pfad)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(argv: list[str]) -> None:
    gewaehlt = set(argv)
    n = 0
    for pfad in familien():
        if gewaehlt and pfad.parent.name not in gewaehlt:
            continue
        m = laden(pfad)
        print(f"{m.FAMILIE.ordner}: {m.FAMILIE.titel}")
        n += len(_rahmen.erzeuge(m.FAMILIE, m.muss))
    print(f"{n} Belege erzeugt. Selbstcheck und Rücklesen ok.")


if __name__ == "__main__":
    main(sys.argv[1:])
