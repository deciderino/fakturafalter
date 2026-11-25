# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kopffeld-Testset (tests/daten/kopffeld/) und Messung: Set reproduzierbar, Ist-Stand wird nicht schlechter."""

import json
import logging
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tools"))

import kopffeld_messung  # noqa: E402
import kopffeld_set  # noqa: E402

SET = WURZEL / "tests" / "daten" / "kopffeld"


def test_set_reproduzierbar(tmp_path):
    neu = kopffeld_set.schreiben(tmp_path)
    alt = [v for v in neu if not v["id"].startswith("h")]
    assert len(alt) == 55 and sum(v["holdout"] for v in alt) == len(alt) // 3
    assert all(v["holdout"] for v in neu if v["id"].startswith("h")) and len(neu) <= 80
    for v in neu:
        for name in (f"{v['id']}.pdf", f"{v['id']}-vorlage.pdf"):
            assert (tmp_path / name).read_bytes() == (SET / name).read_bytes(), name
    assert json.loads((SET / "soll.json").read_text(encoding="utf-8")) == neu


def test_name_laengen_je_grenzfall():
    """Jede Grenzvariante Name/Straße mit 1-, 2- und 3-zeiligem Namen (Nutzer: Name 1–3 Zeilen)."""
    soll = {v["id"]: v for v in json.loads((SET / "soll.json").read_text(encoding="utf-8"))}
    for g in range(1, 8):
        assert [len(soll[f"g{g}-n{n}"]["kaeufer"]["name_zeilen"]) for n in (1, 2, 3)] == [1, 2, 3]
    assert soll["g2-n3"]["kaeufer"]["strasse"] == "Am Hafen"


def test_bewertung_feste_regel():
    """Ohne Vermerkzeile: feste Regel 0.4.4 (Name + Zusatz in BT-44 oder getrennt). Mit „z. Hd.“/„Abteilung“: nur die
    Zielabbildung (Nutzer-Entscheid 23.11.2026) zählt."""
    soll = {
        "name_zeilen": ["A GmbH"],
        "zusatz_oben": ["Gewerbegebiet Ost"],
        "zusatz_unten": [],
        "strasse": "Weg 1",
        "plz": "12345",
        "ort": "Ort",
        "land": "DE",
    }
    ist = {"BT-44": "A GmbH Gewerbegebiet Ost", "BT-50": "Weg 1", "BT-53": "12345", "BT-52": "Ort"}
    assert all(kopffeld_messung.bewerten(soll, ist).values())
    assert all(
        kopffeld_messung.bewerten(
            soll, dict(ist, **{"BT-44": "A GmbH", "BT-51": "Gewerbegebiet Ost"})
        ).values()
    )
    assert not kopffeld_messung.bewerten(soll, dict(ist, **{"BT-50": "z. Hd. B"}))["strasse"]
    soll = dict(soll, zusatz_oben=["Abteilung Einkauf", "z. Hd. B"])
    ist = dict(ist, **{"BT-44": "A GmbH", "BT-51": "Abteilung Einkauf", "BT-56": "B"})
    assert all(kopffeld_messung.bewerten(soll, ist).values())
    alt = dict(ist, **{"BT-44": "A GmbH Abteilung Einkauf z. Hd. B", "BT-51": "", "BT-56": ""})
    assert not kopffeld_messung.bewerten(soll, alt)["name"]


def test_ist_stand_haelt():
    """Untergrenze = gemessener Ist-Stand (alle Felder richtig); darf nur steigen."""
    vorher = logging.root.manager.disable
    faelle = kopffeld_messung.messen(SET)
    assert logging.root.manager.disable == vorher  # Messung schaltet das Logging nicht dauerhaft ab
    ganz = {w: sum(kopffeld_messung._ganz(f, w) for f in faelle) for w in kopffeld_messung.WEGE}
    assert (
        ganz["kalt"] >= 58 and ganz["rahmen"] >= 60 and ganz["vorlage"] >= 59
    )  # Schritt 3 (67 Varianten)


def test_pruefen_statt_still_falsch():
    """Konzept-Schritt 1: strukturelle Brüche -> „prüfen“; still falsch je Weg ≤ 2, kein Fehlalarm bei richtig."""
    faelle = kopffeld_messung.messen(SET)
    for w in kopffeld_messung.WEGE:
        still = [f["id"] for f in faelle if kopffeld_messung.status(f, w) == "falsch"]
        assert len(still) <= (1 if w == "kalt" else 2), (w, still)
        # h10 („Werk 2“ über „Am Hafen“) ist strukturell nicht von einem Zusatz unter der Straße zu unterscheiden
        assert {f["id"] for f in faelle if kopffeld_messung.fehlalarm(f, w)} <= {"h10"}, w


def _zeilen(*zeilen, hoehe=10.0):
    """[(Text, Schrifthöhe) | Text] -> Zeilen aus Wörtern (gleicher Wortabstand 3 pt)."""
    from fakturafalter.pdferkennung import Wort

    out, top = [], 100.0
    for z in zeilen:
        t, h = z if isinstance(z, tuple) else (z, hoehe)
        x, ws = 50.0, []
        for teil in t.split(" "):
            if not teil:
                x += 40
                continue
            ws.append(Wort(teil, x, x + 5 * len(teil), top, 0, top + h))
            x += 5 * len(teil) + 3
        out.append(ws)
        top += 12
    return out


def test_anschrift_brueche_strukturell():
    from fakturafalter import pdferkennung as pe

    b = pe.anschrift_brueche
    assert b(_zeilen("Muster GmbH", "Hauptstraße 5", "12345 Musterstadt")) == {}
    assert b(_zeilen("Stadtwerke Talheim", "Am Hafen", "12345 Talheim")) == {}  # Straße ohne Nummer
    assert b(_zeilen("Muster GmbH", "Postfach 12 34", "12345 Musterstadt")) == {}
    assert b(_zeilen("Muster GmbH", "Hauptstraße 5", "12345 Musterstadt", "Deutschland")) == {}
    assert (
        b(_zeilen("Muster GmbH", "Carl-Benz-Straße", "14", "12345 Ort")) == {}
    )  # Schritt 3: zusammengefügt
    assert (
        b(_zeilen("Muster GmbH", "Talstraße 12", "Hinterhaus, 2. OG", "12345 Ort")) == {}
    )  # Schritt 3: Zusatz
    assert set(b(_zeilen("Carl-Benz-Straße", "14", "12345 Ort"))) == {"BT-50"}  # kein Name darüber
    assert set(b(_zeilen("Muster GmbH", "Talstraße 12", "Hintereingang", "12345 Ort"))) == {
        "BT-50"
    }  # ohne Ziffer
    assert set(b(_zeilen("Muster AG", "Bahnhofstr. 3", "6020 Innsbruck", "ÖSTERREICH"))) == {
        "BT-52"
    }
    assert set(b(_zeilen("Muster AG", "Ring 3", "A-1010 Wien"))) == {"BT-52"}
    assert set(
        b(_zeilen(("Persönlich/Vertraulich", 9.0), "Muster GmbH", "Hauptstraße 5", "12345 Ort"))
    ) == {"BT-44"}
    assert (
        b(_zeilen(("Muster GmbH", 12.0), "Hauptstraße 5", "12345 Ort")) == {}
    )  # Name größer: kein Vermerk
    assert set(b(_zeilen("Muster GmbH     Kundennr.: 4711", "Hauptstraße 5", "12345 Ort"))) == {
        "BT-44"
    }
    assert (
        b(_zeilen("Muster GmbH", "Hauptstraße 5", "12345     Ort")) == {}
    )  # PLZ/Ort-Lücke zählt nicht
    # der Hinweis ändert die Zuordnung nicht (feste Regel, wo keine Ausnahme greift)
    assert pe.anschrift_teilen(["Carl-Benz-Straße", "14", "12345 Ort"]) == {
        "BT-44": "Carl-Benz-Straße",
        "BT-50": "14",
        "BT-53": "12345",
        "BT-52": "Ort",
    }


def test_vorlage_block_liefert_brueche():
    """Angelernter Anschriftblock (``anschrift_auslesen``): Werte nach fester Regel, Prüfhinweis mit BT-Nummer."""
    from fakturafalter import pdferkennung as pe

    zs = [pe.Zeile(0, ws[0].top, ws) for ws in _zeilen("Carl-Benz-Straße", "14", "12345 Ort")]
    br: dict = {}
    teile = pe.anschrift_auslesen({"seite": 0, "rahmen": [40, 90, 300, 150]}, zs, br)
    assert teile["BT-50"][0] == "14" and teile["BT-53"][0] == "12345"
    assert list(br) == ["BT-50"] and br["BT-50"].startswith("BT-50:")
    assert (
        pe.anschrift_auslesen({"seite": 0, "rahmen": [40, 90, 300, 150]}, zs).keys() == teile.keys()
    )


def test_strassenformen_schritt2():
    """Konzept-Schritt 2: Hausnummernbereiche mit Gedankenstrich, Quadrate, Straßen ohne Hausnummer."""
    from fakturafalter.anschrift import _STRASSE
    from fakturafalter.pdferkennung import strassenzeile

    for t in (
        "Talstraße 12",
        "Am Markt 3–5",
        "Am Kai 3 – 5",
        "Hafenstraße 10 - 12",
        "Q 7, 12",
        "Weg 1/2",
    ):
        assert _STRASSE.match(t), t
    for t in ("Am Hafen", "14", "Hinterhaus, 2. OG", "X 12, 3"):
        assert not _STRASSE.match(t), t
    for t in (
        "Am Hafen",
        "Lange Reihe",
        "Straße des 17. Juni",
        "St. Annen-Straße",
        "Postfach 10 20 30",
    ):
        assert strassenzeile(t), t
    for t in (
        "Hinterhaus, 2. OG",
        "14",
        "Kundennummer: 10023",
        "info@beispiel.de",
        "Straße des 17.",
        "Datum 05.10.2026",
    ):
        assert not strassenzeile(t), t


def test_kalt_ohne_hausnummer():
    """Assistent ohne Vorlage: Straße ohne Hausnummer wird gelesen (nur mit Namen darüber)."""
    faelle = {f["id"]: f for f in kopffeld_messung.messen(SET)}
    for vid in ("g2-n1", "g2-n3", "f15", "f17"):
        assert kopffeld_messung.status(faelle[vid], "kalt") == "richtig", vid
    assert faelle["g2-n1"]["ist"]["kalt"]["BT-50"] == "Am Hafen"


def test_ausnahmen_schritt3():
    """Konzept-Schritt 3: strukturelle Ausnahmen von der festen Regel, ohne Schlüsselwörter (N2)."""
    from fakturafalter.pdferkennung import anschrift_zerlegen as z

    t, r = z(
        ["Muster GmbH", "Lange Reihe", "7a", "12345 Ort"]
    )  # Hausnummer allein -> an die Straße
    assert (t["BT-44"], t["BT-50"], r) == (
        "Muster GmbH",
        "Lange Reihe 7a",
        ["name", "strasse", "strasse", "plz"],
    )
    assert (
        z(["A AG", "B", "Industriestraße", "12–14", "12345 Ort"])[0]["BT-50"]
        == "Industriestraße 12–14"
    )
    t, r = z(
        ["Muster GmbH", "Talstraße 12", "Gebäude C, 3. Stock", "12345 Ort"]
    )  # Zusatz -> hinten an BT-44
    assert (t["BT-44"], t["BT-50"], r) == (
        "Muster GmbH Gebäude C, 3. Stock",
        "Talstraße 12",
        ["name", "strasse", "name", "plz"],
    )
    assert "BT-51" not in t  # N3: BT-51 bleibt aus
    # keine Ausnahme: kein Name darüber, Zusatz ohne Ziffer, Straße schon mit Nummer, Ausland (N1)
    assert z(["Muster GmbH", "12", "12345 Ort"])[0]["BT-50"] == "12"
    assert z(["Talstraße 12", "Gebäude C", "12345 Ort"])[0]["BT-50"] == "Gebäude C"
    assert (
        z(["Muster GmbH", "Talstraße 12", "Hintereingang", "12345 Ort"])[0]["BT-50"]
        == "Hintereingang"
    )
    assert z(["Muster GmbH", "Halle 3", "Talstraße 12", "12345 Ort"])[0] == {
        "BT-44": "Muster GmbH Halle 3",
        "BT-50": "Talstraße 12",
        "BT-53": "12345",
        "BT-52": "Ort",
    }
    # Ausland mit Landzeile (ab 0.9.7): PLZ/Ort in ausländischer Form + BT-55
    assert z(["Muster AG", "Bahnhofstr. 3", "6020 Innsbruck", "ÖSTERREICH"])[0] == {
        "BT-44": "Muster AG",
        "BT-50": "Bahnhofstr. 3",
        "BT-53": "6020",
        "BT-52": "Innsbruck",
        "BT-55": "AT",
    }
    assert z(["Muster AG", "Bahnhofstr. 3", "6020 Innsbruck"])[0]["BT-50"] == "6020 Innsbruck"  # ohne Land: N1
    faelle = {f["id"]: f for f in kopffeld_messung.messen(SET)}
    for vid in ("g4-n1", "g4-n2", "g4-n3", "g5-n1", "g5-n2", "g5-n3", "h6", "h7", "h8"):
        for w in kopffeld_messung.WEGE:
            assert kopffeld_messung.status(faelle[vid], w) == "richtig", (vid, w)
    assert kopffeld_messung.status(faelle["h9"], "rahmen") == "prüfen"
