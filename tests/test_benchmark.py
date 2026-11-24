"""Der Erkennungs-Benchmark (tools/benchmark.py) läuft offline, deterministisch und liefert seine Tabellen."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import benchmark  # noqa: E402


def _lauf(tmp_path: Path, name: str) -> tuple[dict, str]:
    md, js = tmp_path / f"{name}.md", tmp_path / f"{name}.json"
    assert (
        benchmark.main(
            [
                "--generator",
                "3",
                "--verfahren",
                "assistent",
                "handvorlage",
                "--md",
                str(md),
                "--json",
                str(js),
            ]
        )
        == 0
    )
    return json.loads(js.read_text(encoding="utf-8")), md.read_text(encoding="utf-8")


def test_benchmark_laeuft_und_ist_deterministisch(tmp_path, capsys):
    e, md = _lauf(tmp_path, "a")
    capsys.readouterr()
    assert set(e) >= {"parameter", "quellen", "tabellen", "fehlschlaege", "freigabe"}
    assert e["quellen"]["assistent"]["generator"] == 3
    assert e["quellen"]["handvorlage"] == {"poc": 1, "wawi-druck": 2}
    zeilen = {z["feld"]: z for z in e["tabellen"]["assistent"]}
    for feld in ("BT-1", "BT-2", "BT-109", "BT-110", "BT-112", "Pos.gesamt"):
        assert zeilen[feld]["gesamt"] > 0
        assert 0 <= zeilen[feld]["treffer"] <= zeilen[feld]["gesamt"]
    assert "| Feld | Treffer | Gesamt | Quote |" in md
    assert _lauf(tmp_path, "b") == (e, md)


def test_betraege_centgenau():
    from decimal import Decimal

    assert benchmark._gleich("BT-109", Decimal("10.00"), Decimal("10"))
    assert not benchmark._gleich("BT-109", Decimal("10.00"), Decimal("10.01"))


def test_fiktiv_hinweisklassen(tmp_path, capsys):
    """Fiktive Belege: BT-130-Klasse wie im Verarbeitungsprotokoll, keine Summenabweichung mehr (Folgeseiten-Unterkante); Absender-USt-Id nicht gewertet."""
    js = tmp_path / "f.json"
    assert (
        benchmark.main(
            ["--verfahren", "fiktiv-korrigiert", "--md", str(tmp_path / "f.md"), "--json", str(js)]
        )
        == 0
    )
    capsys.readouterr()
    e = json.loads(js.read_text(encoding="utf-8"))
    assert e["quellen"]["fiktiv-korrigiert"] == {"fiktiv": 50}
    h = {z["klasse"]: z for z in e["hinweise"]["fiktiv-korrigiert"]}
    assert h["Einheit fehlt (BT-130)"]["anzahl"] == 15
    for kl in ("Σ Positionen ≠ Soll-Netto", "Summenabweichung (Kontrollwert ≠ berechnet)"):
        assert h.get(kl, {}).get("anzahl", 0) == 0
    felder = {z["feld"] for z in e["tabellen"]["fiktiv-korrigiert"]}
    assert "Absender.ust_id" not in felder and "BT-31" not in felder
    assert {"BT-109", "BT-9", "Pos.gesamt"} <= felder


def test_fiktiv_soll_optionale_felder_und_kaeufer_ziel():
    """Testset-Felder werden gewertet, wenn vorhanden; sonst bisheriges Soll. Käufer nach der Zielabbildung:
    „z. Hd.“ -> BT-56 ohne Vermerk, „Abteilung“ -> BT-51, zweizeiliger Firmenname bleibt BT-44."""
    from decimal import Decimal

    js = sorted((benchmark.FIKTIV / "Referenzdaten").glob("Rechnung_*.json"))[0]
    d = json.loads(js.read_text(encoding="utf-8"))
    alt = benchmark.fiktiv_soll(d)
    assert alt.kopf["BT-20"].startswith("Zahlbar innerhalb von")
    assert all(p["preiseinheit"] == 1 for p in alt.positionen)
    d["payment_terms_text"] = [
        "zahlbar bis 15.10.26 bei 2 % Skonto (54,65 €)",
        "bis 04.11.2026 ohne Abzug",
    ]
    d["positions"][0]["price_unit_qty"] = 100
    d["buyer"]["name_lines"] = [
        "Werkzeugbau Muster KG",
        "Abteilung Einkauf",
        "z. Hd. Herrn Beispiel",
    ]
    neu = benchmark.fiktiv_soll(d)
    assert (
        neu.kopf["BT-20"]
        == "zahlbar bis 15.10.26 bei 2 % Skonto (54,65 €) bis 04.11.2026 ohne Abzug"
    )
    assert (
        neu.positionen[0]["preiseinheit"] == Decimal(100) and neu.positionen[1]["preiseinheit"] == 1
    )
    assert (neu.kopf["BT-44"], neu.kopf["BT-51"], neu.kopf["BT-163"], neu.kopf["BT-56"]) == (
        "Werkzeugbau Muster KG",
        "Abteilung Einkauf",
        "",
        "Herrn Beispiel",
    )
    for zeilen, name in (
        (["Muster Sondermaschinenbau", "GmbH & Co. KG"], "Muster Sondermaschinenbau GmbH & Co. KG"),
        (
            ["Muster AG", "Abteilung Vorrichtungsbau", "Werk Süd"],
            "Muster AG Abteilung Vorrichtungsbau Werk Süd",
        ),
    ):
        assert benchmark.kaeufer_ziel(zeilen) == {
            "BT-44": name,
            "BT-51": "",
            "BT-163": "",
            "BT-56": "",
        }


def test_testset_mit_holdout(tmp_path, capsys):
    """Ein Testset-Ordner (--set): eigene Verfahren „<name>-…“, Hold-out getrennt, BT-51 nicht gewertet."""
    import shutil

    s = tmp_path / "mini"
    (s / "Referenzdaten" / "holdout").mkdir(parents=True)
    (s / "Rechnungen").mkdir()
    for i, js in enumerate(
        sorted((benchmark.FIKTIV / "Referenzdaten").glob("Rechnung_*.json"))[:4]
    ):
        d = json.loads(js.read_text(encoding="utf-8"))
        shutil.copy(benchmark.FIKTIV / "Rechnungen" / d["datei"], s / "Rechnungen")
        shutil.copy(js, s / "Referenzdaten" / ("holdout" if i >= 3 else ""))
    assert benchmark.testsets([s, tmp_path / "fehlt"]) == [s]
    e = benchmark.ausfuehren(
        benchmark.parser().parse_args(
            ["--verfahren", "fiktiv-kaltstart", "--fiktiv", str(tmp_path / "leer"), "--set", str(s)]
        )
    )
    capsys.readouterr()
    assert e["quellen"] == {"mini-kaltstart": {"mini": 3}, "mini-kaltstart (Hold-out)": {"mini": 1}}
    felder = {z["feld"] for z in e["tabellen"]["mini-kaltstart"]}
    assert "BT-44" in felder and "BT-51" not in felder
    assert (
        benchmark.parser().parse_args([]).set is None
        and benchmark.parser().parse_args(["--set"]).set == []
    )


def test_layoutset_familien_lernen_n_und_mehrere_saetze(tmp_path, capsys):
    """--set findet Familien-Unterordner, --lernen n lernt genau n Belege (auch ohne Rest, nur Hold-out),
    Tabelle je Familie mit Hold-out; BT-119 bei mehreren Steuersätzen als Menge der Sätze."""
    import shutil
    from decimal import Decimal

    s = tmp_path / "layouts" / "f01_mini"
    (s / "Referenzdaten" / "holdout").mkdir(parents=True)
    (s / "Rechnungen").mkdir()
    for i, js in enumerate(
        sorted((benchmark.FIKTIV / "Referenzdaten").glob("Rechnung_*.json"))[:3]
    ):
        d = json.loads(js.read_text(encoding="utf-8"))
        shutil.copy(benchmark.FIKTIV / "Rechnungen" / d["datei"], s / "Rechnungen")
        shutil.copy(js, s / "Referenzdaten" / ("holdout" if i >= 2 else ""))
    assert benchmark.testsets_mit_gruppe([tmp_path / "layouts"]) == [(s, "layouts")]
    e = benchmark.ausfuehren(
        benchmark.parser().parse_args(
            [
                "--verfahren",
                "fiktiv-kaltstart",
                "fiktiv-angelernt",
                "--lernen",
                "2",
                "--fiktiv",
                str(tmp_path / "leer"),
                "--set",
                str(tmp_path / "layouts"),
            ]
        )
    )
    capsys.readouterr()
    assert e["quellen"]["f01_mini-angelernt (Hold-out)"] == {"f01_mini": 1}
    fr = (
        e["freigabe"].items()
        if isinstance(e["freigabe"], dict)
        else [(x["verkaeufer"], x) for x in e["freigabe"]]
    )
    assert [x["angelernt"] for k, x in fr if k.startswith("f01_mini/")] == [2]
    zeilen = e["familien"]["layouts"]
    assert {(z["familie"], z["weg"], z["teil"]) for z in zeilen} >= {
        ("f01_mini", "kaltstart", "Training"),
        ("f01_mini", "kaltstart", "Hold-out"),
        ("f01_mini", "angelernt", "Hold-out"),
        ("gesamt", "kaltstart", "alle"),
        ("Hold-out gesamt", "angelernt", "Hold-out"),
    }
    for z in zeilen:
        assert (
            z["richtig"] + z["leer"] + z["pruefen"] + z["still"] == z["felder"] and z["leer"] >= 0
        )
    assert "## Familien „layouts“" in benchmark.markdown(e)
    d = {"vat_rate": "19.00", "vat_breakdown": [{"rate": "19.00"}, {"rate": "7.00"}]}
    assert benchmark.soll_saetze(d) == [Decimal("7.00"), Decimal("19.00")]
    assert benchmark.soll_saetze({"vat_rate": "19.00"}) == [Decimal("19.00")]


def test_angelernt_uebernimmt_soll_als_korrektur(tmp_path):
    """Im Assistenten überschreiben die Soll-Werte einen falschen Kaltstart, bevor gelernt wird."""
    js = sorted((benchmark.FIKTIV / "Referenzdaten").glob("Rechnung_*.json"))[0]
    d = json.loads(js.read_text(encoding="utf-8"))
    pdf = benchmark.FIKTIV / "Rechnungen" / d["datei"]
    k = benchmark._konfig(benchmark.PE / "konfiguration.yaml", tmp_path)
    k.pdf_profile = []
    s = benchmark.anlernen.Sitzung(pdf, k)
    s.setzen("BT-1", "FALSCH-999")
    assert s.rechnung().nummer == "FALSCH-999"
    r = benchmark.soll_anlernen(s, d)
    assert r.nummer == d["invoice"]["number"]
    assert r.datum == benchmark._datum(d["invoice"]["date"])
    assert s.rechnung().nummer == d["invoice"]["number"]
    assert len(r.positionen) == len(d["positions"])
    assert r.positionen[0].bezeichnung == " ".join(d["positions"][0]["description"])


def test_totals_soll_und_druck_und_positionsbruch():
    """A1: totals ist gedruckt, totals_berechnet das Soll. Alte Prüfen-Fälle umgekehrt."""
    alt = {
        "totals": {"net": "774.32", "vat": "147.12", "gross": "921.44"},
        "totals_printed": {"net": "784.32", "vat": "147.12", "gross": "921.44"},
    }
    soll, druck = benchmark.totals_soll_und_druck(alt)
    assert soll["net"] == "774.32" and druck["net"] == "784.32"
    neu = {
        "totals": {"net": "1711.14", "vat": "325.12", "gross": "2036.26"},
        "totals_berechnet": {"net": "1723.04", "vat": "327.38", "gross": "2050.42"},
        "totals_printed": {"net": "1711.14", "vat": "325.12", "gross": "2036.26"},
    }
    soll, druck = benchmark.totals_soll_und_druck(neu)
    assert soll["net"] == "1723.04" and druck["net"] == "1711.14"
    p = {"qty": "200", "unit_price": "11.32", "price_unit_qty": 100, "total": "26.24"}
    from decimal import Decimal as D

    assert benchmark.pos_gesamt_soll(p, neu) == D("22.64")
    assert benchmark.pos_gesamt_soll(p, alt) == D("26.24")  # ohne totals_berechnet unverändert


def test_manifest_rollen_und_status(tmp_path):
    """MANIFEST steuert Rollen; v1-Quote ohne ausserhalb_v1; Status-Treffer nach erwarteter_status."""
    import shutil
    from decimal import Decimal

    s = tmp_path / "layouts" / "f01_mini"
    (s / "Referenzdaten" / "holdout").mkdir(parents=True)
    (s / "Rechnungen").mkdir()
    js = sorted((benchmark.FIKTIV / "Referenzdaten").glob("Rechnung_*.json"))
    dateien = []
    for i, quelle in enumerate(js[:4]):
        d = json.loads(quelle.read_text(encoding="utf-8"))
        shutil.copy(benchmark.FIKTIV / "Rechnungen" / d["datei"], s / "Rechnungen")
        unter = s / "Referenzdaten" / ("holdout" if i >= 2 else "")
        unter.mkdir(parents=True, exist_ok=True)
        ziel = unter / quelle.name
        if i == 2:
            d = dict(
                d,
                totals_berechnet={"net": "0.00", "vat": "0.00", "gross": "0.00"},
                erwarteter_status="prüfen",
                erwartete_hinweise=["PRUEFEN [BT-109] Kontrollwert"],
            )
            ziel.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        else:
            shutil.copy(quelle, ziel)
        rolle = ("anlernen", "anlernen", "holdout-fehler", "holdout-falle")[i]
        dateien.append(
            {
                "pdf": f"f01_mini/Rechnungen/{d['datei']}",
                "soll": f"f01_mini/Referenzdaten/{'holdout/' if i >= 2 else ''}{quelle.name}",
                "rechnungsnummer": d["invoice"]["number"],
                "rolle": rolle,
                "fehler": "netto" if i == 2 else None,
                "falle": "ablenker" if i == 3 else None,
                "ausserhalb_v1": False,
                "erwarteter_status": "prüfen" if i == 2 else "ok",
            }
        )
    man = {"version": "1.0.0", "belege": dateien}
    (tmp_path / "layouts" / "MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")
    rollen = benchmark.set_belege(s)
    assert [r for r, xs in rollen.items() if xs] == ["anlernen", "holdout-fehler", "holdout-falle"]
    assert len(rollen["anlernen"]) == 2 and len(rollen["holdout-fehler"]) == 1
    # Soll-Netto des Fehlerbelegs kommt aus totals_berechnet
    assert benchmark.fiktiv_soll(rollen["holdout-fehler"][0][1]).kopf["BT-109"] == Decimal("0.00")
    assert benchmark.hinweis_bt("PRUEFEN [BT-109] irgendwas") == "BT-109"
    f = benchmark.Fall(
        "x-kaltstart (Hold-out-Fehler)",
        "x",
        "a.pdf",
        benchmark.Beleg(),
        benchmark.Beleg(pruefen={"BT-109"}, beleg_pruefen=True),
        hinweise=["PRUEFEN: [BT-109] Abweichung"],
        rolle="holdout-fehler",
        erwarteter_status="prüfen",
    )
    assert benchmark.status_ist(f) == "prüfen" and benchmark.status_treffer(f) is True
    falle = benchmark.Fall(
        "x-kaltstart (Hold-out-Falle)",
        "x",
        "b.pdf",
        benchmark.Beleg(),
        benchmark.Beleg(),
        hinweise=[],
        rolle="holdout-falle",
        erwarteter_status="ok",
    )
    assert benchmark.status_treffer(falle, still=True) is False
    assert benchmark.status_treffer(falle, still=False) is True
    assert benchmark.weg_und_teil("f01", "f01-kaltstart (Hold-out-Fehler)") == (
        "kaltstart",
        "Hold-out-Fehler",
    )
