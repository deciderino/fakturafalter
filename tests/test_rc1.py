# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""1.0.0-rc1: Profilablehnung, Schlüssel, Kundenname-Pflicht, XRechnung-Liste, Suche/Gruppen."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from fakturafalter import csv_einrichtung as ce
from fakturafalter.aufbau import rechnung_bauen
from fakturafalter.konfig import (
    XRechnungEintrag,
    lade_konfig,
    xrechnung_liste_aus,
    xrechnung_treffer,
)
from fakturafalter.modell import Herkunft
from fakturafalter.pipeline import _soll_xrechnung
from fakturafalter.profilformat import ALTE_SCHLUESSEL, PROFILFORMAT, ProfilVeraltet, pruefen

from .conftest import BEISPIELE

H = Herkunft("test", 1.0)
POS = [
    {
        "BT-126": ("1", H),
        "BT-153": ("Test", H),
        "BT-129": (Decimal("1"), H),
        "BT-146": (Decimal("10"), H),
        "steuer": ("1", H),
    }
]
STEUER = {"steuer": {"1": {"BT-151": "S", "BT-152": 19}}}


def _altprofil(**extra) -> dict:
    p = {
        "profil": "alt-export",
        "version": extra.pop("version", 1),
        "felder": {
            "kopf": {"BT-1": {"spalte": "Nr"}, "BT-44": {"spalte": "Name"}},
            "position": {"BT-153": {"spalte": "Text"}},
        },
    }
    p.update(extra)
    return p


def test_profilformat_ist_zwei():
    assert PROFILFORMAT == 2
    assert ALTE_SCHLUESSEL == {"gesamt_kontrolle", "kaeufer_name_2", "kaeufer_name_3"}


@pytest.mark.parametrize("version", [None, 1, "1", 0])
def test_altes_profil_wird_abgelehnt(version, tmp_path):
    p = _altprofil()
    if version is None:
        p.pop("version")
    else:
        p["version"] = version
    ziel = tmp_path / "profil-alt.yaml"
    ziel.write_text(yaml.safe_dump(p, allow_unicode=True), encoding="utf-8")
    davor = ziel.read_bytes()
    with pytest.raises(ProfilVeraltet) as exc:
        pruefen(p, datei=ziel)
    m = exc.value.meldung()
    assert "nicht weiter" in m
    assert "neu einrichten" in m
    assert "0.9.11" in m
    assert "unvera" in m.replace("ändert", "andert") or "unverändert" in m
    assert "du " in m or "deiner" in m
    assert ziel.read_bytes() == davor


def test_alte_schluessel_werden_abgelehnt(tmp_path):
    p = _altprofil(version=2)
    p["felder"]["position"]["gesamt_kontrolle"] = {"spalte": "Summe", "zweck": "pruefung"}
    with pytest.raises(ProfilVeraltet) as exc:
        pruefen(p)
    assert "gesamt_kontrolle" in exc.value.meldung()
    p = _altprofil(version=2)
    p["felder"]["kopf"]["kaeufer_name_2"] = {"spalte": "Name2"}
    with pytest.raises(ProfilVeraltet) as exc:
        pruefen(p)
    assert "kaeufer_name_2" in exc.value.meldung()


def test_profil_format_2_wird_angenommen():
    pruefen(_altprofil(version=2))


def test_pdf_vorlage_wird_nicht_als_csv_profil_geprueft():
    # version: 1 bleibt bei Druckvorlagen gültig
    vorlage = yaml.safe_load((BEISPIELE / "vorlage-wawi-druck.yaml").read_text(encoding="utf-8"))
    assert vorlage.get("version") == 1 and "vorlage" in vorlage
    # lade_konfig darf die Vorlage nicht ablehnen
    k = lade_konfig(BEISPIELE / "konfiguration.yaml")
    assert any(v.get("vorlage") == "wawi-alt-a4" for v in k.pdf_vorlagen)
    assert "vorlage-wawi-druck.yaml" not in " ".join(str(x) for x in (k.abgelehnte_profile or []))


def test_konfig_lehnt_altes_csv_profil_ab_und_laesst_datei(tmp_path):
    import shutil

    shutil.copy(BEISPIELE / "konfiguration.yaml", tmp_path / "konfiguration.yaml")
    alt = tmp_path / "profil-alt-format.yaml"
    alt.write_text("profil: alt\nversion: 1\nfelder:\n  kopf:\n    BT-1: {spalte: Nr}\n", encoding="utf-8")
    # Minimal: eine Konfig, die nur dieses Profil nennt
    kfg = tmp_path / "konfiguration.yaml"
    t = kfg.read_text(encoding="utf-8")
    t = t.replace(
        "csv_profile: [profil-variante-blo.yaml, profil-variante-zjp-textzeilen.yaml, profil-variante-a.json, profil-variante-b.yaml, profil-variante-c.yaml, profil-variante-d.yaml, profil-variante-k.yaml, profil-variante-s.yaml]",
        "csv_profile: [profil-alt-format.yaml]",
    )
    kfg.write_text(t, encoding="utf-8")
    davor = alt.read_bytes()
    k = lade_konfig(kfg)
    assert k.abgelehnte_profile
    assert alt.read_bytes() == davor
    assert not any((p.get('_datei') or '').endswith('profil-alt-format.yaml') or p.get('profil') == 'alt' for p in k.csv_profile)
    m = k.abgelehnte_profile[0][1]
    assert "0.9.11" in m and "neu einrichten" in m


def test_neue_schluessel_gesamtpreis_position_und_kunden_name():
    assert "gesamtpreis_position" in ce.FELD
    assert "gesamt_kontrolle" not in ce.FELD
    assert "kunden_name_2" in ce.FELD and "kunden_name_3" in ce.FELD
    assert "kaeufer_name_2" not in ce.FELD
    # Label behält den Kontrollhinweis
    assert "Kontrolle" in ce.FELD["gesamtpreis_position"][1]
    assert ce.FELD["BT-44"][4] is True  # Pflicht
    assert ce.FELD["kundennummer"][4] is False


def test_kundenname_ist_pflicht_auch_wenn_kunde_als_nummer_erkannt_wird():
    kopf = ["Nr", "Datum", "Kunde", "Text", "Anzahl", "ME", "Preis", "MwSt"]
    zeilen = [["R-1", "01.10.2026", "K-1001", "Beratung", "2", "Std.", "80,00", "19"]]
    z = ce.spalten_vorschlagen(kopf, zeilen)
    assert z.get("kundennummer") == "Kunde"
    assert "BT-44" not in z
    fehl = ce.fehlende_pflicht(z)
    assert any("Kundenname" in t or "BT-44" in t or "Name" in t for t in fehl)


def test_spalte_kunde_mit_namen_bleibt_kundenname():
    kopf = ["Nr", "Datum", "Kunde", "Text", "Anzahl", "ME", "Preis", "MwSt"]
    zeilen = [["R-1", "01.10.2026", "Fiktiv AG", "Beratung", "2", "Std.", "80,00", "19"]]
    z = ce.spalten_vorschlagen(kopf, zeilen)
    assert z.get("BT-44") == "Kunde"
    assert "kundennummer" not in z
    assert not any("Kundenname" in t for t in ce.fehlende_pflicht(z))


def _konfig_liste(k, *, zusatz=True, liste=None):
    k.xrechnung_zusatz = zusatz
    k.xrechnung_liste = liste if liste is not None else [
        XRechnungEintrag(name="Stadtverwaltung Musterhausen", nummer="K-1002", leitweg_id="04011000-12345-03"),
        XRechnungEintrag(name="Probe Kleinbetrieb e.K.", nummer="K-1003"),
    ]
    return k


def test_xrechnung_liste_treffer_per_name(konfig):
    k = _konfig_liste(konfig)
    e = xrechnung_treffer(k, name="  stadtverwaltung  MUSTERHAUSEN ", nummer="")
    assert e and e.nummer == "K-1002" and e.leitweg_id.startswith("04011000")
    r = rechnung_bauen(
        {"BT-1": ("X-1", H), "BT-2": (date(2026, 10, 28), H), "BT-44": ("Stadtverwaltung Musterhausen", H)},
        POS,
        {"mappings": STEUER},
        k,
        "t",
    )
    assert _soll_xrechnung(r, k)


def test_xrechnung_liste_treffer_per_nummer(konfig):
    k = _konfig_liste(konfig)
    e = xrechnung_treffer(k, name="Unbekannt", nummer="k-1003")
    assert e and e.name.startswith("Probe")
    r = rechnung_bauen(
        {
            "BT-1": ("X-1", H),
            "BT-2": (date(2026, 10, 28), H),
            "BT-44": ("Unbekannter Name GmbH", H),
            "kundennummer": ("K-1003", H),
        },
        POS,
        {"mappings": STEUER},
        k,
        "t",
    )
    assert _soll_xrechnung(r, k)


def test_xrechnung_liste_kein_treffer(konfig):
    k = _konfig_liste(konfig)
    assert xrechnung_treffer(k, name="Beispiel Handel GmbH", nummer="K-1001") is None
    r = rechnung_bauen(
        {
            "BT-1": ("X-1", H),
            "BT-2": (date(2026, 10, 28), H),
            "BT-44": ("Beispiel Handel GmbH", H),
            "kundennummer": ("K-1001", H),
        },
        POS,
        {"mappings": STEUER},
        k,
        "t",
    )
    assert not _soll_xrechnung(r, k)


def test_xrechnung_liste_schalter_aus(konfig):
    k = _konfig_liste(konfig, zusatz=False)
    assert xrechnung_treffer(k, name="Stadtverwaltung Musterhausen", nummer="K-1002") is None
    r = rechnung_bauen(
        {
            "BT-1": ("X-1", H),
            "BT-2": (date(2026, 10, 28), H),
            "BT-44": ("Stadtverwaltung Musterhausen", H),
            "kundennummer": ("K-1002", H),
        },
        POS,
        {"mappings": STEUER},
        k,
        "t",
    )
    assert not _soll_xrechnung(r, k)


def test_xrechnung_liste_aus_alten_schluesseln():
    opt = {
        "xrechnung_liste": [
            {"kundenname": "A GmbH", "kundennummer": "A-1", "leitweg_id_bt10": "99"},
        ]
    }
    (e,) = xrechnung_liste_aus(opt)
    assert (e.name, e.nummer, e.leitweg_id) == ("A GmbH", "A-1", "99")


def test_felder_sind_gruppiert_und_suche_findet_beleg_und_gesamtpreis():
    assert ce.GRUPPE_REIHENFOLGE
    alle = []
    for g in ce.GRUPPE_REIHENFOLGE:
        alle.extend(ce.felder_in_gruppe(g, wiederholend=True))
    assert "BT-1" in alle and "BT-44" in alle and "gesamtpreis_position" in alle
    # Suche über Label, Synonym und Tooltip
    treffer = ce.suche_felder("Belegname", wiederholend=True)
    assert "BT-1" in treffer
    treffer = ce.suche_felder("Belegnummer", wiederholend=True)
    assert "BT-1" in treffer
    treffer = ce.suche_felder("gesamtpreis", wiederholend=True)
    assert "gesamtpreis_position" in treffer
    assert ce.anzeige_feld("BT-1").startswith("Rechnungsnummer")
    assert "*" in ce.anzeige_feld("BT-44")


def test_startkonfig_ohne_migrationshinweis(tmp_path):
    """Neue Installationen sollen nicht den Hinweis „Kundenstamm entfällt“ sehen."""
    import shutil

    from fakturafalter.konfig import lade_konfig

    src = Path(__file__).resolve().parent.parent / "src" / "fakturafalter" / "ressourcen" / "start" / "konfiguration.yaml"
    ziel = tmp_path / "konfiguration.yaml"
    shutil.copy(src, ziel)
    k = lade_konfig(ziel)
    assert k.xrechnung_zusatz is False
    assert k.xrechnung_liste == []
    assert k.konfig_hinweise == []



def test_wizard_blockformat_euro_und_sub(konfig, tmp_path):
    """Fiktive Kopie des Blockformats (Kopf-/Positionsblöcke, 0x1A-Endzeile, EURO) bis zur Rechnung."""
    import shutil

    from fakturafalter import adapter_csv, pipeline, rechnen
    from fakturafalter.aufbau import waehrung_code

    quelle = BEISPIELE / "beispiel-satzart-pos-kopf-und-restzeile.csv"
    roh = quelle.read_bytes()
    # DOS-Dateiende statt der Restzeile "."
    if roh.endswith(b".\r\n"):
        roh = roh[: -3] + b"\x1a"
    elif roh.endswith(b".\n"):
        roh = roh[: -2] + b"\x1a"
    elif b"\x1a" not in roh:
        roh = roh.rstrip() + b"\x1a"
    datei = tmp_path / "fiktiv-block-euro-sub.csv"
    datei.write_bytes(roh)
    assert datei.read_bytes().endswith(b"\x1a") or b"\x1a" in datei.read_bytes()

    fmt = ce.format_erkennen(datei)
    bloecke, sa = ce.bloecke_vorschlagen(fmt)
    assert bloecke, "keine Blöcke erkannt"
    zu: dict[str, dict[str, str]] = {}
    steuer, einheiten = {}, {}
    for b in bloecke:
        kopf = list(b.get("kopf") or [])
        zeilen = [r for _n, r in b.get("daten") or []]
        v = ce.spalten_vorschlagen(kopf, zeilen) if kopf else {}
        if not b.get("wiederholend"):
            v = {f: s for f, s in v.items() if f not in ce.positionsfelder()}
        zu[b.get("id") or b["typ"]] = v
    # Steuer/Einheiten aus den Positionszeilen, wie der Assistent sie vorschlägt
    for b in bloecke:
        if not b.get("wiederholend"):
            continue
        kopf = list(b.get("kopf") or [])
        z = zu.get(b.get("id") or b["typ"]) or {}
        if z.get("steuer"):
            try:
                i = kopf.index(z["steuer"])
                werte = [r[i] for _n, r in (b.get("daten") or []) if i < len(r)]
                steuer.update(ce.steuer_vorschlag(werte))
            except ValueError:
                pass
        if z.get("BT-130"):
            try:
                i = kopf.index(z["BT-130"])
                werte = [r[i] for _n, r in (b.get("daten") or []) if i < len(r)]
                einheiten.update(ce.einheiten_vorschlag(werte))
            except ValueError:
                pass

    profil = ce.profil_bauen_bloecke(
        "fiktiv-rc1-block", datei, fmt, bloecke, zu, steuer, einheiten, {}, sa
    )
    # wie der Assistent: leere Einheit einer Positionszeile als Stück
    profil.setdefault("aufbau", {})["einheit_fehlt_stueck"] = True
    assert profil.get("version") == 2
    felder_ids = set()
    for b in profil.get("bloecke") or []:
        felder_ids.update((b.get("felder") or {}))
    assert "BT-44" in felder_ids
    assert "BT-1" in felder_ids

    rs = adapter_csv.lesen(datei, profil, konfig)
    assert rs, "keine Rechnung gelesen"
    r = rs[0]
    rechnen.berechnen(r)
    assert waehrung_code(r.waehrung) == "EUR" or r.waehrung in ("EUR", "EURO")
    assert r.kaeufer.name
    assert r.nummer

    # Fertige Datei über die Pipeline (ohne Java-Nachprüfung in diesem Test)
    ziel = konfig.eingang / datei.name
    shutil.copy(datei, ziel)
    # Profil in die Laufzeit-Konfig legen
    konfig.csv_profile = [profil] + [p for p in konfig.csv_profile if not p.get("_eingebaut")]
    lauf = pipeline.verarbeiten([ziel], konfig)
    assert lauf.ok or lauf.ergebnisse, (getattr(lauf, "datei_fehler", None), [(e.nummer, e.hinweise) for e in (lauf.ergebnisse or [])])
    (e,) = lauf.ergebnisse
    assert e.dateien, e.hinweise
    pdfs = [p for p in e.dateien if p.suffix.lower() == ".pdf"]
    assert pdfs and pdfs[0].stat().st_size > 1000


@pytest.mark.parametrize("welche", ["minimal", "voll"])
def test_standardvorlagen_tragen_kundennamen(konfig, tmp_path, welche):
    """rc1: Kundenname ist Pflicht – die Vorlagen und Beispieldateien müssen ihn in jeder Rechnung haben."""
    from fakturafalter import adapter_csv, csv_standard, rechnen

    f = tmp_path / f"{welche}.csv"
    f.write_bytes(getattr(csv_standard, f"vorlage_{welche}")())
    assert f.read_bytes() == (BEISPIELE / f"fakturafalter-standard-{welche}.csv").read_bytes()
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    rs = adapter_csv.lesen(f, std, konfig)
    assert [r.nummer for r in rs] == ["RE-2026-1001", "RE-2026-1002"]
    for r in rs:
        rechnen.berechnen(r)
        assert r.kaeufer.name == "Beispiel Handel GmbH", r.kaeufer.name
        assert not [h for h in r.hinweise if "BT-44" in str(h)], r.hinweise
