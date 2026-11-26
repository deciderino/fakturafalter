# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.9.8.3: Fehlende Einheit als Stück annehmen (Profiloption, fiktive Daten)."""

from pathlib import Path

import yaml

from fakturafalter import adapter_csv, cii, pflichtpruefung, rechnen, sicht
from fakturafalter import csv_einrichtung as ce

from .conftest import BEISPIELE

CSV = Path(__file__).resolve().parent / "daten" / "variante-zjp_pauschale-ohne-einheit.csv"
PROFIL = BEISPIELE / "profil-variante-zjp-textzeilen.yaml"


def _profil(einheit_fehlt_stueck=False):
    p = yaml.safe_load(PROFIL.read_text(encoding="utf-8"))
    if einheit_fehlt_stueck:
        p.setdefault("aufbau", {})["einheit_fehlt_stueck"] = True
    else:
        p.setdefault("aufbau", {}).pop("einheit_fehlt_stueck", None)
    return p


def _lesen(konfig, *, einheit_fehlt_stueck=False):
    (r,) = adapter_csv.lesen(CSV, _profil(einheit_fehlt_stueck), konfig)
    rechnen.berechnen(r)
    pflichtpruefung.pruefen(r, pflichtpruefung.Kontext(bekannte_nummern=frozenset()))
    return r


def _pauschale(r):
    treffer = [p for p in r.positionen if p.bezeichnung == "Versandpauschale"]
    assert len(treffer) == 1, [p.bezeichnung for p in r.positionen]
    return treffer[0]


def test_standard_leere_einheit_bleibt_prueffall(konfig):
    r = _lesen(konfig, einheit_fehlt_stueck=False)
    assert len(r.positionen) == 5
    p = _pauschale(r)
    assert p.nr == "5"
    assert p.menge == 1
    assert p.einzelpreis is not None
    assert p.einheit == ""
    assert not p.einheit_angenommen
    texte = [str(h) for h in r.hinweise]
    assert any("Einheit" in t and "fehlt" in t.lower() for t in texte)
    assert not any("Stück angenommen" in t for t in texte)
    assert r.status == "pruefen"


def test_option_setzt_stueck_h87_ohne_prueffall(konfig):
    r = _lesen(konfig, einheit_fehlt_stueck=True)
    assert len(r.positionen) == 5
    p = _pauschale(r)
    assert p.nr == "5"
    assert p.einheit == "H87"
    assert p.einheit_roh == "Stück"
    assert p.einheit_angenommen
    assert sicht.einheit_anzeige(p, r) == "Stück"
    texte = [str(h) for h in r.hinweise]
    assert any("Einheit fehlte, Stück angenommen" in t for t in texte)
    assert not any(h.stufe == "pruefen" and "BT-130" in (h.feld or "") for h in r.hinweise)
    # nur Hinweis, kein Prüffall wegen der Einheit
    unit_pruefen = [h for h in r.hinweise if h.stufe == "pruefen" and "Einheit" in h.text]
    assert unit_pruefen == []
    # gesetzte Einheiten aus der CSV bleiben, kein Annahme-Hinweis
    andere = [q for q in r.positionen if q is not p]
    assert all(q.einheit and not q.einheit_angenommen for q in andere)
    # Kommentar-/Leerzeilen sind keine Positionen
    assert all(q.bezeichnung for q in r.positionen)
    assert not any("Lieferschein" in (q.bezeichnung or "") for q in r.positionen)


def test_sicht_zeigt_stueck_auch_bei_kurzform(konfig):
    profil = _profil(True)
    profil.setdefault("sicht", {})["einheit"] = "kurz"
    (r,) = adapter_csv.lesen(CSV, profil, konfig)
    rechnen.berechnen(r)
    p = _pauschale(r)
    assert sicht.einheit_anzeige(p, r) == "Stück"
    # andere Positionen mit Einheit in der CSV: Kurzform
    andere = next(q for q in r.positionen if q.bezeichnung.startswith("Beispielplatte"))
    assert sicht.einheit_anzeige(andere, r) == "Stk."


def test_kommentarzeilen_unveraendert(konfig):
    aus = _lesen(konfig, einheit_fehlt_stueck=True)
    aus0 = _lesen(konfig, einheit_fehlt_stueck=False)
    assert [p.bezeichnung for p in aus.positionen] == [p.bezeichnung for p in aus0.positionen]
    assert [p.zeilen_davor for p in aus.positionen] == [p.zeilen_davor for p in aus0.positionen]
    assert [p.kommentar_unten for p in aus.positionen] == [
        p.kommentar_unten for p in aus0.positionen
    ]


def test_probe_zeigt_hinweis_aber_status_ok_fuer_einheit(konfig):
    probe = ce.probe(adapter_csv.lesen(CSV, _profil(True), konfig), konfig)
    assert len(probe) == 1
    e = probe[0]
    assert any("Einheit fehlte, Stück angenommen" in h for h in e.hinweise)
    assert not any(
        "Einheit" in h and "fehlt" in h.lower() and "angenommen" not in h for h in e.hinweise
    )
    # Status darf durch die angenommene Einheit nicht auf pruefen gehen
    assert not any(
        h.startswith("PRUEFEN") and ("BT-130" in h or "Einheit fehlt" in h) for h in e.hinweise
    )


def test_cii_schreibt_h87(konfig):
    r = _lesen(konfig, einheit_fehlt_stueck=True)
    xml = cii.erzeugen(r).decode("utf-8")
    # die angenommene Position trägt H87 als unitCode
    assert 'unitCode="H87"' in xml


def test_profil_bauen_schreibt_option_nur_wenn_gesetzt():
    fmt = ce.format_erkennen(CSV)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    p = ce.profil_bauen(
        "pauschale",
        CSV,
        fmt,
        z,
        ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])),
        None,
    )
    assert "einheit_fehlt_stueck" not in (p.get("aufbau") or {})
    p2 = ce.profil_bauen(
        "pauschale",
        CSV,
        fmt,
        z,
        ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])),
        None,
        einheit_fehlt_stueck=True,
    )
    assert p2["aufbau"]["einheit_fehlt_stueck"] is True
    # Assistenten-Vorschlag für „Stück“ ist H87
    assert p2["mappings"]["einheiten"].get("Stück") == "H87"
