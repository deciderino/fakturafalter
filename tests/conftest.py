# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
import shutil
from pathlib import Path

import pytest

from fakturafalter import pdferkennung, validierung
from fakturafalter.konfig import lade_konfig

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"


@pytest.fixture
def konfig(tmp_path):
    """Konfiguration aus beispiele/, Laufzeit-Ordner im tmp-Verzeichnis."""
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen"):
        setattr(k, n, tmp_path / n)
    k.eingang.mkdir()
    return k


@pytest.fixture
def eingang(konfig):
    def kopieren(*namen):
        return [Path(shutil.copy(BEISPIELE / n, konfig.eingang / n)) for n in namen]
    return kopieren


@pytest.fixture(autouse=True)
def angelernt_im_tmp(tmp_path, monkeypatch):
    """Angelernte PDF-Vorlagen nie ins Repository schreiben."""
    monkeypatch.setattr(pdferkennung, "ablage", lambda profil: tmp_path / "angelernt")


@pytest.fixture(autouse=True)
def ohne_nachpruefung(request, monkeypatch):
    """Die Prüfung nach Erstellung startet Java – nur in Tests mit Marker „validierung“ echt.
    Sonst gelten die Werkzeuge als nicht vorhanden (Ausgaben: „nicht geprüft“)."""
    if "validierung" not in request.keywords:
        monkeypatch.setattr(validierung, "bereit", lambda: False)
