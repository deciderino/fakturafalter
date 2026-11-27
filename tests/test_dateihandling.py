# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Dateihandling ab 0.9.6: Ausgang = reine Postbox (nur fertige, geprüfte Dateien, atomar, XML vor PDF),
Protokoll im eigenen sichtbaren Ordner, fehlendes Protokoll nur Hinweis, XRechnung-Ablage einstellbar."""

import errno
import os
import tempfile
from pathlib import Path

import pytest

from fakturafalter import dateien, pipeline, protokoll, validierung
from fakturafalter.konfig import lade_konfig

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"

CSV = "variante-b_wawi_cp1252.csv"  # 3 Rechnungen, 0102 und 0103 mit XRechnung (Liste in den Einstellungen)
TEMP = Path(tempfile.gettempdir())


def _temp_reste() -> set[str]:
    return {p.name for p in TEMP.glob("fakturafalter-*")}


def _alles_im_ausgang(k) -> list[str]:
    return sorted(str(p.relative_to(k.ausgang)) for p in k.ausgang.rglob("*"))


def _validierung_falsch(monkeypatch, urteil, gesehen: list):
    """Prüfwerkzeuge „da“; ``urteil(pfad) -> bool``. Merkt sich, wo die geprüften Dateien lagen."""
    monkeypatch.setattr(validierung, "bereit", lambda: True)
    monkeypatch.setattr(validierung, "werkzeug_versionen", lambda: "Mustang x, KoSIT y")

    def pruefen(pfade, bei_werkzeug=None):
        aus = []
        for p in pfade:
            gesehen.append(Path(p))
            assert Path(p).exists()
            ok = urteil(Path(p))
            aus.append(
                validierung.Pruefergebnis(str(p), "KoSIT", ok, [] if ok else ["[BR-01] kaputt"])
            )
        return aus

    monkeypatch.setattr(validierung, "pruefen", pruefen)


def test_pruefung_ausserhalb_des_ausgangs_dann_atomar_xml_vor_pdf(konfig, eingang, monkeypatch):
    vorher = _temp_reste()
    gesehen: list[Path] = []
    _validierung_falsch(monkeypatch, lambda p: True, gesehen)
    reihenfolge = []
    echt = dateien.ablegen

    def ablegen(quelle, ziel, zwischen=()):
        reihenfolge.append(Path(ziel).name)
        assert Path(quelle).parent.parent == TEMP  # fertige Datei kommt aus dem System-Temp
        return echt(quelle, ziel, zwischen)

    monkeypatch.setattr(dateien, "ablegen", ablegen)
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert [e.status for e in lauf.ergebnisse] == ["ok", "ok", "ok"]
    assert all(e.pruefung == "gültig" for e in lauf.ergebnisse)
    assert gesehen and all(
        konfig.ausgang not in p.parents for p in gesehen
    )  # nie im Ausgang geprüft
    i_xml, i_pdf = (
        reihenfolge.index("RE-2026-0102_xrechnung.xml"),
        reihenfolge.index("RE-2026-0102_zugferd.pdf"),
    )
    assert i_xml < i_pdf
    assert _alles_im_ausgang(konfig) == [
        "RE-2026-0101_zugferd.pdf",
        "RE-2026-0102_xrechnung.xml",
        "RE-2026-0102_zugferd.pdf",
        "RE-2026-0103_xrechnung.xml",
        "RE-2026-0103_zugferd.pdf",
    ]  # kein .tmp/.part, kein protokoll.tsv
    assert [Path(d).parent for e in lauf.ergebnisse for d in e.dateien] == [konfig.ausgang] * 5
    assert _temp_reste() <= vorher  # Temp-Ordner sofort gelöscht


def test_ungueltig_direkt_nach_fehler_nie_im_ausgang(konfig, eingang, monkeypatch):
    vorher = _temp_reste()
    _validierung_falsch(monkeypatch, lambda p: "0101" not in p.name, [])
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert st == {"RE-2026-0101": "fehler", "RE-2026-0102": "ok", "RE-2026-0103": "ok"}
    assert not (konfig.ausgang / "RE-2026-0101_zugferd.pdf").exists()
    assert (konfig.fehler / "RE-2026-0101_zugferd.pdf").exists()
    assert (konfig.fehler / "RE-2026-0101_fehler.txt").exists()
    assert _temp_reste() <= vorher


def test_ohne_pruefwerkzeuge_wie_bisher_nicht_geprueft(konfig, eingang):
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert {e.pruefung for e in lauf.ergebnisse} == {"nicht geprüft"}
    assert (konfig.ausgang / "RE-2026-0101_zugferd.pdf").exists()


def test_protokoll_im_eigenen_ordner_sofort_je_rechnung(konfig, eingang, monkeypatch):
    stand = []
    echt = dateien.ablegen

    def ablegen(quelle, ziel, zwischen=()):
        p = protokoll.pfad(konfig)
        stand.append(p.read_text(encoding="utf-8").count("\tok\t") if p.exists() else 0)
        return echt(quelle, ziel, zwischen)

    monkeypatch.setattr(dateien, "ablegen", ablegen)
    pipeline.verarbeiten(eingang(CSV), konfig)
    assert stand == [
        0,
        1,
        1,
        2,
        2,
    ]  # 0101 (PDF), 0102 (XML, PDF), 0103 (XML, PDF): Zeile je Rechnung sofort
    assert konfig.protokoll == konfig.eingang.parent / "Protokoll"
    assert protokoll.pfad(konfig).exists() and not (konfig.ausgang / "protokoll.tsv").exists()
    assert protokoll.bekannte_nummern(konfig) == {"RE-2026-0101", "RE-2026-0102", "RE-2026-0103"}


def test_doppelt_erkannt_auch_wenn_ausgang_geleert(konfig, eingang):
    pipeline.verarbeiten(eingang(CSV), konfig)
    for p in konfig.ausgang.iterdir():  # Archiv holt die Dateien ab
        p.unlink()
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert {e.status for e in lauf.ergebnisse} == {"pruefen"}
    assert not list(konfig.ausgang.iterdir())


def test_fehlendes_protokoll_nur_hinweis_altes_im_ausgang_ignoriert(konfig, eingang):
    konfig.ausgang.mkdir(parents=True)
    (konfig.ausgang / "protokoll.tsv").write_text(
        "2026-01-01 10:00:00\tok\tRE-2026-0101\t\t\t\t\t\n", "utf-8"
    )
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert [m[0] for m in lauf.meldungen] == [protokoll.FEHLT]  # Hinweis, kein Halt
    assert {e.status for e in lauf.ergebnisse} == {"ok"}  # altes Protokoll wird nicht gelesen
    assert (konfig.ausgang / "protokoll.tsv").exists()  # und nicht angefasst (keine Migration)
    # nächster Lauf: Protokoll da -> kein Hinweis mehr
    lauf = pipeline.verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert lauf.meldungen == []


def test_erster_lauf_ohne_hinweis(konfig, eingang):
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert lauf.meldungen == []


def test_protokoll_gesperrt_nachtrag_und_uebernahme(konfig, eingang, monkeypatch):
    monkeypatch.setattr(dateien, "PAUSEN", ())
    konfig.protokoll.mkdir(parents=True)
    protokoll.pfad(konfig).write_text("", encoding="utf-8")
    echt = dateien.anhaengen

    def anhaengen(ziel, text, encoding="utf-8"):
        if Path(ziel).name == protokoll.DATEI:
            raise dateien.DateiNichtSchreibbar(Path(ziel), PermissionError(13, "gesperrt"))
        return echt(ziel, text, encoding)

    monkeypatch.setattr(dateien, "anhaengen", anhaengen)
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert {e.status for e in lauf.ergebnisse} == {"ok"}
    assert [m[0] for m in lauf.meldungen] == [protokoll.ERSATZ]
    nachtrag = konfig.protokoll / protokoll.NACHTRAG
    assert nachtrag.exists()
    assert protokoll.bekannte_nummern(konfig) == {"RE-2026-0101", "RE-2026-0102", "RE-2026-0103"}
    monkeypatch.setattr(dateien, "anhaengen", echt)
    lauf = pipeline.verarbeiten(eingang("variante-a_positionen_utf8.csv"), konfig)
    assert lauf.meldungen == [] and not nachtrag.exists()
    assert "RE-2026-0102" in protokoll.pfad(konfig).read_text(encoding="utf-8")


def test_protokollordner_nicht_beschreibbar_haelt_nicht_an(konfig, eingang, monkeypatch):
    def nie(ordner, datei=None):
        raise dateien.DateiNichtSchreibbar(Path(ordner), PermissionError(13, "nein"))

    monkeypatch.setattr(dateien, "beschreibbar_pruefen", nie)
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert protokoll.NICHT_BESCHREIBBAR in [m[0] for m in lauf.meldungen]
    assert {e.status for e in lauf.ergebnisse} == {"ok"}


def test_kollision_im_selben_lauf_bleibt_erkannt(konfig, eingang):
    from fakturafalter import nummernkreis

    konfig.nummernkreise = {"rechnung": nummernkreis.Kreis(dateiname="fest")}
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    assert [e.status for e in lauf.ergebnisse] == ["ok", "pruefen", "pruefen"]
    assert [p.name for p in konfig.ausgang.glob("*.pdf")] == ["fest.pdf"]


@pytest.mark.parametrize(
    ("ablage", "erwartet"),
    [
        ("ausgang", ["RE-2026-0102_xrechnung.xml", "RE-2026-0102_zugferd.pdf"]),
        (
            "unterordner",
            ["RE-2026-0102_zugferd.pdf", "XRechnung", "XRechnung/RE-2026-0102_xrechnung.xml"],
        ),
        ("keine", ["RE-2026-0102_zugferd.pdf"]),
    ],
)
def test_xrechnung_ablage(tmp_path, eingang, konfig, ablage, erwartet):
    roh = (BEISPIELE / "konfiguration.yaml").read_text(encoding="utf-8")
    datei = BEISPIELE / "konfiguration.yaml"
    k = lade_konfig(datei)
    assert k.xrechnung_ablage == "ausgang" and k.xrechnung_zusatz  # Standard wie bisher
    k.roh.setdefault("optionen", {})
    for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen"):
        setattr(k, n, getattr(konfig, n))
    k.xrechnung_ablage = "unterordner" if ablage == "unterordner" else "ausgang"
    k.xrechnung_zusatz = ablage != "keine"
    lauf = pipeline.verarbeiten(eingang(CSV), k)
    assert {e.status for e in lauf.ergebnisse} == {"ok"}
    assert [x for x in _alles_im_ausgang(k) if "0102" in x or x == "XRechnung"] == erwartet
    assert (BEISPIELE / "konfiguration.yaml").read_text(encoding="utf-8") == roh


def test_konfig_xrechnung_ablage_und_protokollordner(tmp_path):
    import yaml

    def laden(extra):
        d = {"arbeitsordner": "R", **extra}
        (tmp_path / "k.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
        return lade_konfig(tmp_path / "k.yaml")

    k = laden({})
    assert (k.xrechnung_ablage, k.xrechnung_zusatz, k.protokoll) == (
        "ausgang",
        True,
        tmp_path / "R" / "Protokoll",
    )
    assert k.updatepruefung is True and k.updates_vorab is False
    k = laden({"optionen": {"xrechnung_ablage": "unterordner"}, "protokoll_ordner": "P"})
    assert (
        k.xrechnung_ordner == tmp_path / "R" / "Ausgang" / "XRechnung"
        and k.protokoll == tmp_path / "P"
    )
    k = laden({"optionen": {"xrechnung_ablage": "keine"}})
    assert k.xrechnung_zusatz is False
    k = laden({"optionen": {"xrechnung_zusatz": False}})
    assert k.xrechnung_zusatz is False and k.xrechnung_ablage == "ausgang"


def _anderes_laufwerk(monkeypatch, gesperrt):
    """os.replace scheitert mit EXDEV, wenn Quelle in einem der ``gesperrt``-Ordner liegt."""
    echt = os.replace

    def replace(a, b):
        if any(Path(a).parent == g for g in gesperrt):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return echt(a, b)

    monkeypatch.setattr(os, "replace", replace)


def test_ablegen_anderes_laufwerk_ueber_zwischenordner(tmp_path, monkeypatch):
    q = tmp_path / "temp" / "a.pdf"
    q.parent.mkdir()
    q.write_bytes(b"%PDF fertig")
    ziel = tmp_path / "Ausgang" / "a.pdf"
    zwischen = tmp_path / "Protokoll"
    _anderes_laufwerk(monkeypatch, [q.parent])
    dateien.ablegen(q, ziel, (zwischen,))
    assert ziel.read_bytes() == b"%PDF fertig" and not q.exists()
    assert sorted(p.name for p in ziel.parent.iterdir()) == ["a.pdf"]
    assert not list(zwischen.iterdir())


def test_ablegen_notfall_versteckt_im_ziel_ohne_reste(tmp_path, monkeypatch):
    q = tmp_path / "temp" / "a.pdf"
    q.parent.mkdir()
    q.write_bytes(b"%PDF fertig")
    ziel = tmp_path / "Ausgang" / "a.pdf"
    zwischen = tmp_path / "Protokoll"
    _anderes_laufwerk(monkeypatch, [q.parent, zwischen])
    dateien.ablegen(q, ziel, (zwischen,))
    assert ziel.read_bytes() == b"%PDF fertig"
    assert sorted(p.name for p in ziel.parent.iterdir()) == ["a.pdf"]


def test_ablegen_scheitert_xml_wird_zurueckgenommen(konfig, eingang, monkeypatch):
    monkeypatch.setattr(dateien, "PAUSEN", ())
    echt = dateien.ablegen

    def ablegen(quelle, ziel, zwischen=()):
        if Path(ziel).name == "RE-2026-0102_zugferd.pdf":
            raise dateien.DateiNichtSchreibbar(Path(ziel), PermissionError(13, "nein"))
        return echt(quelle, ziel, zwischen)

    monkeypatch.setattr(dateien, "ablegen", ablegen)
    lauf = pipeline.verarbeiten(eingang(CSV), konfig)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert st == {"RE-2026-0101": "ok", "RE-2026-0102": "fehler", "RE-2026-0103": "ok"}
    assert not (konfig.ausgang / "RE-2026-0102_xrechnung.xml").exists()  # nichts Halbes
    assert "RE-2026-0102" not in protokoll.bekannte_nummern(konfig)
