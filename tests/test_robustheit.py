# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Robustheit beim Anlernen und Nur-PDF (0.4.6): Summenzeilen direkt unter den Positionen, Rahmen des Nutzers
vor Seitensuche, rechnerische Gegenprobe als Schiedsrichter, Typprüfung je Feld, Anker im Kopf,
Selbstkontrolle nach dem Speichern, anonymisierte Diagnose. Alle Rechnungen und Werte sind erfunden."""

import shutil
from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml

from fakturafalter import adapter_pdf, anlernen, konfig, pdferkennung

from . import erp_roh

IND = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"
KOPF = (20, 225, 560, 268)  # Rahmen um Datum/Beleg (erp_roh.rechnung)


@pytest.fixture
def k(tmp_path):
    roh = yaml.safe_load((IND / "konfiguration-nur-pdf.yaml").read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    pfad = tmp_path / "konfiguration.yaml"
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    k = konfig.lade_konfig(pfad)
    k.ordner_anlegen()
    k.pfad_datei = pfad
    return k


def _summe(wort, betrag):
    return (" " * 20 + wort).ljust(82 - len(betrag)) + betrag + " €"


POS = [
    erp_roh.pos_pe("10", "Stk.", "Kabelbinder 470011", "1,25 €", "/1", "12,50 €"),
    erp_roh.pos_pe("2", "Std.", "Montage vor Ort 470012", "85,00 €", "/1", "170,00 €"),
    erp_roh.pos_pe("100", "Stk.", "Schraube M8x40 470013", "10,89 €", "/1", "1.089,00 €"),
]


def _summen(wort="Netto", netto="1.271,50", ust="241,59", brutto="1.513,09"):
    return [
        _summe(wort, netto),
        (" " * 20 + "MwSt. 19 %").ljust(82 - len(ust)) + ust + " €",
        _summe("Rechnungsbetrag", brutto),
    ]


def _direkt(k, name="sz", wort="Netto", pos=POS, beleg="26000042", nach=(), **kw):
    """Summenzeilen ohne Leerzeile direkt unter den Positionen (im Tabellenrahmen)."""
    return erp_roh.rechnung(
        k.eingang / f"{name}.pdf",
        zeilen=pos + _summen(wort, **kw),
        kopf=erp_roh.KOPF_PE,
        nach=list(nach),
        beleg=beleg,
    )


def _pos(s):
    return [(p.menge, p.einzelpreis, p.gesamt) for p in s.positionen()]


SOLL_POS = [
    (D("10"), D("1.25"), D("12.50")),
    (D("2"), D("85.00"), D("170.00")),
    (D("100"), D("10.89"), D("1089.00")),
]


def _speichern(k, s):
    s.absender = anlernen.Sitzung(
        shutil.copy(IND / "eingang" / "NB-26-1001.pdf", k.eingang), k
    ).absender
    if s.werte["leistung"].status == "fehlt":
        s.setzen("leistung", "05.10.2026")
    for f in s.fehlende():
        s.bestaetigen(f)
    assert s.fertig(), s.fehlende()
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    return v


# ------------------------------------------------------------ 3. Summenzeilen strukturell erkannt
@pytest.mark.parametrize("wort", ["Netto", "Total", "Gesamt", "Warenwert", "Summe netto"])
def test_summenzeile_direkt_unter_positionen(k, wort):
    s = anlernen.Sitzung(_direkt(k, wort=wort), k)
    assert _pos(s) == SOLL_POS  # keine 0,00-Position aus der Summenzeile
    assert {f: s.werte[f].wert for f in ("BT-109", "BT-110", "BT-112")} == {
        "BT-109": "1.271,50",
        "BT-110": "241,59",
        "BT-112": "1.513,09",
    }
    diag = s.tabellen_diagnose()
    assert pdferkennung.SUMMENZEILE_GRUND in diag


def test_summenzeile_im_weiten_rahmen_und_alte_vorlage(k):
    """Rahmen bis weit unter die Summen gezogen – und eine alte Vorlage mit Ende nur „MwSt.“: die Netto-Zeile
    beendet die Tabelle trotzdem."""
    s = anlernen.Sitzung(_direkt(k), k)
    t = s.tabelle
    s.rahmen_setzen(0, t.x0 - 10, t.top, t.x1 + 20, 600)
    assert _pos(s) == SOLL_POS
    pv = dict(s.pv(), ende=["MwSt."])
    prot = []
    ps = pdferkennung.positionen_auslesen(pv, s.zeilen, prot)
    assert [p.gesamt for p in ps] == [g for _, _, g in SOLL_POS]
    assert any(pdferkennung.SUMMENZEILE_GRUND in g for _, g in prot)


def test_sammelzeile_mit_menge_und_preis_bleibt_position(k):
    """„Mindestauftrag“ / „Summe“ in der Bezeichnung mit Menge und Preis ist eine Position, keine Summenzeile."""
    pos = POS + [
        erp_roh.pos_pe("1", "Stk.", "Zuschlag Mindestauftrag Summe", "15,00 €", "/1", "15,00 €")
    ]
    s = anlernen.Sitzung(_direkt(k, pos=pos, netto="1.286,50", ust="244,44", brutto="1.530,94"), k)
    assert len(s.positionen()) == 4 and s.positionen()[-1].gesamt == D("15.00")
    assert s.werte["BT-109"].wert == "1.286,50"


@pytest.mark.parametrize("wort", ["Vortrag", "Saldovortrag"])
def test_vortrag_als_uebertrag(k, wort):
    pdf = erp_roh.rechnung_mehrseitig(
        k.eingang / "v.pdf", [erp_roh.STANDARD[:2], erp_roh.STANDARD[2:]], uebertrag=wort
    )
    s = anlernen.Sitzung(pdf, k)
    assert sum(p.gesamt for p in s.positionen()) == erp_roh.SUMME
    assert all(p.gesamt != D("1000.00") for p in s.positionen())
    assert pdferkennung.ist_uebertrag(next(z for z in s.zeilen if z.text.strip().startswith(wort)))


def test_ueberlappende_summen_und_tabelle_auch_mit_mehr_positionen(k):
    """Der Summenrahmen darf über dem Tabellenrahmen liegen; bei mehr Positionen wandert er mit."""
    s = anlernen.Sitzung(_direkt(k), k)
    t = s.tabelle
    s.zone_setzen("tabelle", 0, (t.x0, t.top, t.x1, t.bottom + 40))
    s.zone_setzen("summen", 0, (300, t.bottom - 30, 560, t.bottom + 40))  # überlappt die Tabelle
    assert _pos(s) == SOLL_POS
    assert s.werte["BT-109"].wert == "1.271,50" and s.werte["BT-112"].wert == "1.513,09"
    _speichern(k, s)
    mehr = POS + [
        erp_roh.pos_pe("4", "Stk.", "Mutter M8 470014", "0,50 €", "/1", "2,00 €"),
        erp_roh.pos_pe("1", "Stk.", "Scheibe M8 470015", "3,00 €", "/1", "3,00 €"),
    ]
    s2 = anlernen.Sitzung(
        _direkt(k, "sz2", pos=mehr, netto="1.276,50", ust="242,54", brutto="1.519,04"), k
    )
    assert s2.vorlage is not None
    assert len(s2.positionen()) == 5
    assert s2.werte["BT-109"].wert == "1.276,50" and s2.werte["BT-112"].wert == "1.519,04"


# ------------------------------------------------------------ 2. Rechnerische Gegenprobe
def test_summen_lesart():
    g = {"BT-109": D("100.00"), "BT-110": D("19.00"), "BT-112": D("119.00")}
    assert pdferkennung.summen_lesart(D("100.00"), g, [])[1] == "ok"
    assert pdferkennung.summen_lesart(D("100.01"), g, [])[1] == "ok"  # Rundungstoleranz
    falsch = {"BT-109": D("19.00"), "BT-110": D("100.00"), "BT-112": D("119.00")}
    neu, art = pdferkennung.summen_lesart(
        D("100.00"), falsch, [D("100.00"), D("19.00"), D("119.00")]
    )
    assert art == "gewählt" and neu == g
    mehr = {
        "BT-109": D("200.00"),
        "BT-110": D("19.00"),
        "BT-112": D("226.00"),
    }  # nur ein Satz gelesen
    neu, art = pdferkennung.summen_lesart(
        D("200.00"), mehr, [D("200.00"), D("7.00"), D("19.00"), D("226.00")]
    )
    assert art == "gewählt" and neu["BT-110"] == D("26.00") and neu["BT-112"] == D("226.00")
    assert (
        pdferkennung.summen_lesart(
            D("100.00"), {"BT-109": D("100.00"), "BT-110": None, "BT-112": None}, []
        )[1]
        == "ok"
    )
    assert pdferkennung.summen_lesart(D("90.00"), g, [D("50.00")])[1] == "geht nicht auf"


def test_lesart_je_position_preiseinheit_100():
    """Menge × Preis ÷ PE = Betrag: fehlt die Preiseinheit im Druck, gewinnt die, die aufgeht."""
    m, e, p = pdferkennung._lesart_waehlen(
        [(D("250"), "")], [(D("12.00"), "")], D("30.00"), None, D(1), True
    )
    assert (m, e, p) == (D("250"), D("12.00"), D(100))
    m, e, p = pdferkennung._lesart_waehlen(
        [(D("2"), "")], [(D("5.00"), "")], D("10.00"), None, D(1), True
    )
    assert p is None  # geht schon auf: bleibt
    m, e, p = pdferkennung._lesart_waehlen(
        [(D("2"), "")], [(D("5.00"), "")], D("99.00"), None, D(1), False
    )
    assert (m, e, p) == (
        D("2"),
        D("5.00"),
        None,
    )  # geht nicht auf: erste Lesart, berechnen meldet „prüfen“


def test_gegenprobe_im_anlernen_waehlt_was_aufgeht(k, monkeypatch):
    s = anlernen.Sitzung(_direkt(k), k)
    s.werte["BT-109"].wert, s.werte["BT-109"].status = "241,59", "erkannt"  # falsch gelesen
    assert s.summen_gegenprobe() == "gewählt"
    assert s.werte["BT-109"].wert == "1.271,50" and s.werte["BT-109"].status == "pruefen"
    assert "Rechnerisch" in s.werte["BT-109"].hinweis


def test_gegenprobe_geht_nicht_auf_heisst_pruefen(k):
    s = anlernen.Sitzung(_direkt(k, netto="1.300,00", ust="247,00", brutto="1.600,00"), k)
    for f in ("BT-109", "BT-112"):
        s.werte[f].status = "erkannt"
    assert s.summen_gegenprobe() == "geht nicht auf"
    assert s.werte["BT-109"].status == "pruefen" and "gehen nicht auf" in s.werte["BT-109"].hinweis


def test_nur_pdf_schiedsrichter():
    zeilen = []
    kopf = {
        "BT-109": (D("19.00"), None),
        "BT-110": (D("100.00"), None),
        "BT-112": (D("119.00"), None),
    }
    ps = [
        pdferkennung.PosRoh(
            **{
                **_posroh_leer(),
                "menge": D(1),
                "einzelpreis": D("100.00"),
                "gesamt": D("100.00"),
                "preiseinheit": D(1),
            }
        )
    ]
    import fakturafalter.pdferkennung as pe

    orig = pe.summenblock
    try:
        pe.summenblock = lambda pv, z: [(D("100.00"), []), (D("19.00"), []), (D("119.00"), [])]
        h = pe.summen_schiedsrichter(kopf, ps, {}, zeilen, None)
    finally:
        pe.summenblock = orig
    assert (
        h
        and h[0] == "info"
        and kopf["BT-109"][0] == D("100.00")
        and kopf["BT-110"][0] == D("19.00")
    )


def _posroh_leer():
    import dataclasses

    return {
        f.name: None
        for f in dataclasses.fields(pdferkennung.PosRoh)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }


# ------------------------------------------------------------ 4. Typprüfung je Feld
@pytest.mark.parametrize(
    "feld,text,ok",
    [
        ("BT-53", "12345", True),
        ("BT-53", "D-12345", True),
        ("BT-53", "1234", False),
        ("BT-53", "Musterstadt", False),
        ("BT-2", "05.10.2026", True),
        ("BT-2", "31.02.2026", False),
        ("BT-2", "Beleg", False),
        ("BT-31", "DE123456789", True),
        ("BT-31", "DE12345", False),
        ("BT-31", "ATU12345678", True),
        ("BT-84", "DE02120300000000202051", True),
        ("BT-84", "DE02120300000000202052", False),
        ("BT-109", "1.271,50", True),
        ("BT-109", "Netto", False),
        ("BT-119", "19 %", True),
        ("BT-119", "7", True),
        ("BT-119", "190 %", False),
        ("BT-119", "", False),
        ("BT-1", "26000042", True),
    ],
)
def test_wert_passt(feld, text, ok):
    assert pdferkennung.wert_passt(feld, text) is ok


def test_unpassender_wert_wird_nicht_vorgeschlagen(k, monkeypatch):
    echt = anlernen.Sitzung._aus_vorlage
    pdf = _direkt(k)

    def falsch(self, feld):
        if feld == "BT-2":
            return "Rechnung", []
        return echt(self, feld)

    monkeypatch.setattr(anlernen.Sitzung, "_aus_vorlage", falsch)
    s = anlernen.Sitzung(pdf, k)
    assert s.werte["BT-2"].wert != "Rechnung"
    assert anlernen.wert_passt_feld("BT-2", "05.10.2026") and not anlernen.wert_passt_feld(
        "BT-2", "Rechnung"
    )


# ------------------------------------------------------------ 1. Rahmen des Nutzers haben Vorrang
def test_rahmen_vorrang_keine_seitensuche(k):
    s = anlernen.Sitzung(_direkt(k), k)
    assert s.werte["BT-1"].wert == "26000042"
    s.zone_setzen(
        "kopf", 0, (300, 600, 560, 700)
    )  # leere Stelle: nicht von woanders auf der Seite holen
    assert s.werte["BT-1"].wert == "" and s.werte["BT-2"].wert == ""


def test_lernen_ohne_seitenweite_suche_wenn_bereich(k, caplog):
    """Liegt ein Feld nicht im Bereich, lernt die Vorlage keine seitenweite Regel dafür."""
    s = anlernen.Sitzung(_direkt(k), k)
    s.zone_setzen("kopf", 0, (20, 225, 560, 240))  # nur die Datumszeile
    s.setzen("BT-1", "26000042")
    with caplog.at_level("INFO"):
        v = _speichern(k, s)
    assert s.werte["BT-1"].status == "erkannt"  # vom Nutzer gesetzt
    assert "BT-1" not in v["felder"]  # keine Regel aus einer Seitensuche
    assert s.selbstkontrolle["BT-1"] == (
        "26000042",
        "",
    )  # Selbstkontrolle meldet: so nicht wieder lesbar
    assert any("nicht gelernt" in r.message for r in caplog.records)


# ------------------------------------------------------------ 5. Anker: Kopffelder wandern mit
def test_anker_kopf_tiefer(k):
    s = anlernen.Sitzung(erp_roh.rechnung(k.eingang / "a1.pdf", beleg="26000042"), k)
    s.zone_setzen("kopf", 0, KOPF)
    assert s.werte["BT-1"].wert == "26000042" and s.werte["BT-2"].wert == "05.10.2026"
    v = _speichern(k, s)
    regel = v["felder"]["BT-1"]
    s2 = anlernen.Sitzung(
        erp_roh.rechnung(k.eingang / "a2.pdf", beleg="26000077", kopf_versatz=30), k
    )
    assert pdferkennung.anker_verschiebung(regel, s2.zeilen, 0) == pytest.approx(30, abs=1)
    assert s2.werte["BT-1"].wert == "26000077" and s2.werte["BT-2"].wert == "05.10.2026"


def test_anker_verschiebung_ohne_anker_null(k):
    s = anlernen.Sitzung(_direkt(k), k)
    assert pdferkennung.anker_verschiebung({"top": 100}, s.zeilen, 0) == 0
    assert pdferkennung.anker_verschiebung({"anker": ["Gibtsnicht:"], "top": 100}, s.zeilen, 0) == 0


# ------------------------------------------------------------ 6. Selbstkontrolle nach dem Speichern
def test_selbstkontrolle_ohne_abweichung(k):
    s = anlernen.Sitzung(_direkt(k), k)
    _speichern(k, s)
    assert s.selbstkontrolle == {}


def test_selbstkontrolle_meldet_abweichung_und_markiert(k, monkeypatch, caplog):
    s = anlernen.Sitzung(_direkt(k), k)
    echt = anlernen.Sitzung._aus_vorlage

    def anders(self, feld):
        r = echt(self, feld)
        return ("99999999", r[1]) if feld == "BT-1" and r else r

    monkeypatch.setattr(anlernen.Sitzung, "_aus_vorlage", anders)
    with caplog.at_level("WARNING"):
        _speichern(k, s)
    assert set(s.selbstkontrolle) == {"BT-1"}
    assert s.selbstkontrolle["BT-1"] == ("26000042", "99999999")
    assert any("Selbstkontrolle" in r.message for r in caplog.records)
    monkeypatch.setattr(anlernen.Sitzung, "_aus_vorlage", echt)
    s2 = anlernen.Sitzung(_direkt(k, "sz2"), k)
    s2.werte["BT-1"].status = "erkannt"
    assert s2.kontrolle_markieren(["BT-1"]) == ["BT-1"]
    assert s2.werte["BT-1"].status == "pruefen" and "Selbstkontrolle" in s2.werte["BT-1"].hinweis


def _nur_pdf(k, pdf):
    (prof,) = k.pdf_profile
    (v,) = pdferkennung.vorlagen_laden(prof)
    v["statistik"]["folge_treffer"] = 5  # sicher: Nur-PDF liest
    pdferkennung.vorlage_speichern(v, prof)
    anlernen.nur_pdf_schalten(prof, True)
    prof["pdf_erkennung"] = {"nur_pdf": True}
    r, grund = pdferkennung.nur_pdf(
        pdf, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), k.pdf_profile, k
    )
    assert r is not None, grund
    return r, [h for h in r.hinweise if h.text.startswith("Selbstkontrolle offen")]


def test_selbstkontrolle_bleibt_offen_ueber_die_sitzung(k, monkeypatch):
    """Abweichung der Selbstkontrolle steht in der Vorlage: spätere Sitzungen markieren das Feld, Nur-PDF prüft."""
    s = anlernen.Sitzung(_direkt(k), k)
    echt = anlernen.Sitzung._aus_vorlage
    monkeypatch.setattr(
        anlernen.Sitzung,
        "_aus_vorlage",
        lambda self, f: ("99999999", []) if f == "BT-1" and echt(self, f) else echt(self, f),
    )
    v = _speichern(k, s)
    monkeypatch.setattr(anlernen.Sitzung, "_aus_vorlage", echt)
    assert v["kontrolle_offen"] == ["BT-1"]
    (prof,) = k.pdf_profile
    assert pdferkennung.kontrolle_offen(pdferkennung.vorlagen_laden(prof)[0]) == ["BT-1"]
    r, offen = _nur_pdf(k, _direkt(k, "n1", beleg="26000043"))
    assert r.status == "pruefen" and [h.feld for h in offen] == ["BT-1"]
    # neue Sitzung, Vorlage von der Platte
    s2 = anlernen.Sitzung(_direkt(k, "sz2", beleg="26000044"), k)
    assert s2.werte["BT-1"].status == "pruefen" and "Selbstkontrolle" in s2.werte["BT-1"].hinweis
    v2 = _speichern(k, s2)  # Nutzer bestätigt, die Vorlage liest richtig: Kontrolle erledigt
    assert "kontrolle_offen" not in v2 and s2.kontrolle_offen == []
    r, offen = _nur_pdf(k, _direkt(k, "n2", beleg="26000045"))
    assert not offen and r.status == "ok", [h.text for h in r.hinweise if h.stufe != "info"]


def test_alte_vorlage_ohne_kontrolle_gilt_als_bestaetigt(k):
    """Vorlagen bis 0.8.0 haben kein ``kontrolle_offen``: nichts markiert, Nur-PDF ohne Prüfhinweis."""
    _speichern(k, anlernen.Sitzung(_direkt(k), k))
    (prof,) = k.pdf_profile
    (v,) = pdferkennung.vorlagen_laden(prof)
    assert "kontrolle_offen" not in v
    assert "kontrolle_offen" not in Path(v["_datei"]).read_text(encoding="utf-8")
    s2 = anlernen.Sitzung(_direkt(k, "sz2", beleg="26000044"), k)
    assert s2.kontrolle_offen == [] and s2.werte["BT-1"].status == "erkannt"
    r, offen = _nur_pdf(k, _direkt(k, "n1", beleg="26000043"))
    assert not offen and r.status == "ok"
    assert pdferkennung.kontrolle_offen({"kontrolle_offen": "kaputt"}) == []


def test_kontrolle_bestaetigen_api(k):
    _speichern(k, anlernen.Sitzung(_direkt(k), k))
    (prof,) = k.pdf_profile
    (v,) = pdferkennung.vorlagen_laden(prof)
    pdferkennung.kontrolle_setzen(v, ["BT-1", "positionen"])
    pdferkennung.vorlage_speichern(v, prof)
    assert pdferkennung.kontrolle_bestaetigen(prof, v["kennung"], ["positionen"]) == ["positionen"]
    assert pdferkennung.kontrolle_offen(pdferkennung.vorlagen_laden(prof)[0]) == ["BT-1"]
    assert pdferkennung.kontrolle_bestaetigen(prof, v["kennung"]) == ["BT-1"]
    assert "kontrolle_offen" not in pdferkennung.vorlagen_laden(prof)[0]


# ------------------------------------------------------------ 7. Anonymisierte Diagnose
def test_bereiche_diagnose_anonym(k):
    s = anlernen.Sitzung(_direkt(k), k)
    s.zone_setzen("kopf", 0, KOPF)
    t = s.tabelle
    s.zone_setzen("summen", 0, (300, t.bottom - 30, 560, t.bottom + 40))
    d = s.bereiche_diagnose()
    for name in ("Rechnungskopf", "Summen"):
        assert name in d
    for klar in ("26000042", "05.10.2026", "1.271,50", "Musterstadt", "Beispiel Werkzeugbau"):
        assert klar not in d


@pytest.mark.parametrize("wort", ["Gesamt", "Total"])
def test_nur_pdf_summenzeile_direkt_unter_positionen(k, wort):
    """Nach dem Anlernen liest Nur-PDF die nächste Rechnung: Summen aus der Gesamt-Spalte, keine 0,00-Position."""
    for i in range(6):  # erste legt die Vorlage an, dann fünf in Folge ohne Korrektur: sicher
        s = anlernen.Sitzung(_direkt(k, f"l{i}", wort=wort, beleg=f"2600005{i}"), k)
        _speichern(k, s)
        assert s.selbstkontrolle == {}
    mehr = POS + [erp_roh.pos_pe("4", "Stk.", "Mutter M8 470014", "0,50 €", "/1", "2,00 €")]
    pdf = _direkt(k, "n2", wort=wort, pos=mehr, netto="1.273,50", ust="241,97", brutto="1.515,47")
    (prof,) = k.pdf_profile
    anlernen.nur_pdf_schalten(prof, True)
    r, grund = pdferkennung.nur_pdf(
        pdf, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), k.pdf_profile, k
    )
    assert r is not None, grund
    assert [p.menge for p in r.positionen] == [D("10"), D("2"), D("100"), D("4")]
    assert r.kontrolle["BT-109"] == D("1273.50") and r.kontrolle["BT-112"] == D("1515.47")


def test_selbstkontrolle_ignoriert_unbestaetigte_felder(k):
    """Eine gedruckte Zahlungsbedingung im Zahlungsrahmen, die nicht bestätigt wurde (optional, Status „prüfen“),
    wird nicht gelernt – die Selbstkontrolle meldet sie nicht als Abweichung."""
    pdf = _direkt(k, nach=["", " Zahlbar innerhalb von 30 Tagen ohne Abzug."])
    s = anlernen.Sitzung(pdf, k)
    vs = s.zone_vorschlag("zahlung")
    assert vs
    s.zone_setzen("zahlung", *vs)
    s.werte = s.vorschlagen()  # neu gelesen, BT-20 nicht bestätigt
    assert s.werte["BT-20"].woerter and s.werte["BT-20"].status == "pruefen"
    _speichern(k, s)
    assert s.selbstkontrolle == {}
    s.vorlage["felder"].pop("BT-20", None)  # wie bei der Test-PDF: Zahlungsbedingung nicht gelernt
    assert s.selbst_kontrollieren() == {}


def test_nur_pdf_einheit_nicht_angelernt_allgemein_zugeordnet(k):
    """0.4.8: Gelernt sind nur „Stk.“/„Std.“; die nächste Rechnung hat „Paar“ und „Pal.“ -> allgemeine
    Einheitenliste (PR, XPX) statt „unbekannt“. Gelerntes geht vor (eigene Zuordnung von „Stk.“ bleibt)."""
    s = anlernen.Sitzung(_direkt(k, "e0"), k)
    s.tabelle.einheiten["Stk."] = "C62"  # bewusst anders als die allgemeine Liste (H87)
    _speichern(k, s)
    mehr = POS + [
        erp_roh.pos_pe("1", "Paar", "Handschuhe 470015", "2,00 €", "/1", "2,00 €"),
        erp_roh.pos_pe("1", "Pal.", "Einweg 470016", "0,00 €", "/1", "0,00 €"),
    ]
    pdf = _direkt(
        k, "e1", pos=mehr, beleg="26000043", netto="1.273,50", ust="241,97", brutto="1.515,47"
    )
    (prof,) = k.pdf_profile
    anlernen.nur_pdf_schalten(prof, True)
    prof["pdf_erkennung"]["nur_pdf_ab"] = 0  # nur für den Test: schon nach einer Rechnung sicher
    r, grund = pdferkennung.nur_pdf(
        pdf, pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf)), k.pdf_profile, k
    )
    assert r is not None, grund
    assert [p.einheit for p in r.positionen] == ["C62", "HUR", "C62", "PR", "XPX"]


# ------------------------------------------------------------ 0.9.0 Nutzerfund: Dezimalmenge ohne Einheit
_TRANSPORT = {
    "0,5 ohne": ("0,5", "", "35,00 €", "17,50 €", D("0.5"), D("35.00"), D("17.50")),
    "0,5 mit": ("0,5", "Std.", "35,00 €", "17,50 €", D("0.5"), D("35.00"), D("17.50")),
    "1,25 ohne": ("1,25", "", "35,00 €", "43,75 €", D("1.25"), D("35.00"), D("43.75")),
    "2 ohne": ("2", "", "35,00 €", "70,00 €", D("2"), D("35.00"), D("70.00")),
    "1.000,5 ohne": ("1.000,5", "", "0,10 €", "100,05 €", D("1000.5"), D("0.10"), D("100.05")),
}


def _de(d: D) -> str:
    return f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@pytest.mark.parametrize("fall", _TRANSPORT)
def test_dezimalmenge_ohne_einheit_vorlage_und_nur_pdf(k, fall):
    """Vorlage an einem Druck ohne die Zeile angelernt; der nächste Druck hat zusätzlich „0,5 | | Transportpauschale
    | 35,00 € /1 | 17,50 €“ (anteilige Pauschale): Position mit Menge 0,5, Preis 35,00 je 1, Betrag 17,50."""
    menge, me, preis, betrag, sm, sp, sg = _TRANSPORT[fall]
    s = anlernen.Sitzung(_direkt(k), k)
    _speichern(k, s)
    pos = POS[:2] + [erp_roh.pos_pe(menge, me, "Transportpauschale", preis, "/1", betrag)] + POS[2:]
    netto = D("1271.50") + sg
    ust = (netto * D("0.19")).quantize(D("0.01"))
    pdf = _direkt(
        k, "t2", pos=pos, beleg="26000043", netto=_de(netto), ust=_de(ust), brutto=_de(netto + ust)
    )
    s2 = anlernen.Sitzung(pdf, k)
    assert s2.vorlage is not None
    soll = SOLL_POS[:2] + [(sm, sp, sg)] + SOLL_POS[2:]
    assert _pos(s2) == soll
    assert s2.positionen()[2].preiseinheit == D("1")
    r, _ = _nur_pdf(k, pdf)
    p = r.positionen[2]
    assert (p.menge, p.einzelpreis, p.preiseinheit, p.kontrolle_gesamt) == (sm, sp, D("1"), sg)
    if not me:  # leere Einheit: kein stilles C62 – die Pflichtprüfung meldet BT-130 als „prüfen“
        from fakturafalter import pflichtpruefung, rechnen

        assert p.einheit == ""
        rechnen.berechnen(r)
        pflichtpruefung.pruefen(r)
        assert any(h.stufe == "pruefen" and "BT-130" in (h.feld or "") for h in r.hinweise)


KOPF_EH = " Menge   Einheit  Bezeichnung                       Einzelpreis           Gesamt"
KOPF_EH_SCHMAL = " Menge Einh.   Bezeichnung                         Einzelpreis           Gesamt"


def _pos_eh(menge, me, bez, preis, betrag, links=False):
    """Eigene Einheitenspalte. ``links``: False rechtsbündig, True linksbündig (breite Mengenspalte); „schmal“
    linksbündig, Spalten aus einstelligen Mengen gelernt; „mitte“ zentriert; „komma“ am Dezimalkomma
    ausgerichtet (Dezimaltabulator)."""
    if links == "schmal":
        s = (" " + menge).ljust(7) + me
        s = s.ljust(14) + bez
    elif links == "komma":
        ganz, _, rest = menge.partition(",")
        s = ganz.rjust(5) + ("," + rest if rest else "").ljust(3) + " " + me
        s = s.ljust(14) + bez
    elif links == "mitte":
        s = (" " + menge.center(5)).ljust(7) + me
        s = s.ljust(14) + bez
    else:
        m = (" " + menge).ljust(9) if links else menge.rjust(6).ljust(9)
        s = (m + me).ljust(18) + bez
    s = s.ljust(65 - len(preis)) + preis
    return s.ljust(82 - len(betrag)) + betrag


@pytest.mark.parametrize("links", [False, True, "schmal", "mitte", "komma"])
@pytest.mark.parametrize("fall", _TRANSPORT)
def test_dezimalmenge_eigene_einheitenspalte(k, fall, links):
    """Nachbau des Fehlers: Ist die Menge breiter als alle angelernten („1,25“ am Komma, „1.000,5“ linksbündig in
    der schmalen Spalte), fiel ihre Mitte in die leere Einheitenspalte – „Menge leer“, Zeile verworfen."""
    menge, me, preis, betrag, sm, sp, sg = _TRANSPORT[fall]
    q = ("1", "2", "4") if links in ("schmal", "mitte", "komma") else ("10", "2", "100")
    ep = (
        ("12,50 €", "85,00 €", "272,25 €")
        if links in ("schmal", "mitte", "komma")
        else ("1,25 €", "85,00 €", "10,89 €")
    )
    basis = [
        _pos_eh(q[0], "Stk.", "Kabelbinder 470011", ep[0] + " /1", "12,50 €", links),
        _pos_eh(q[1], "Std.", "Montage vor Ort 470012", ep[1] + " /1", "170,00 €", links),
        _pos_eh(q[2], "Stk.", "Schraube M8x40 470013", ep[2] + " /1", "1.089,00 €", links),
    ]
    soll_basis = [
        (D(a), D(b.split()[0].replace(",", ".")), g) for a, b, (_, _, g) in zip(q, ep, SOLL_POS)
    ]

    def druck(name, pos, beleg, netto):
        ust = (netto * D("0.19")).quantize(D("0.01"))
        return erp_roh.rechnung(
            k.eingang / f"{name}.pdf",
            zeilen=pos + _summen(netto=_de(netto), ust=_de(ust), brutto=_de(netto + ust)),
            kopf=KOPF_EH_SCHMAL if links in ("schmal", "mitte", "komma") else KOPF_EH,
            nach=[],
            beleg=beleg,
        )

    s = anlernen.Sitzung(druck("e1", basis, "26000042", D("1271.50")), k)
    assert _pos(s) == soll_basis, s.tabellen_diagnose()
    _speichern(k, s)
    pos = (
        basis[:2]
        + [_pos_eh(menge, me, "Transportpauschale", preis + " /1", betrag, links)]
        + basis[2:]
    )
    pdf = druck("e2", pos, "26000043", D("1271.50") + sg)
    soll = soll_basis[:2] + [(sm, sp, sg)] + soll_basis[2:]
    s0 = anlernen.Sitzung(shutil.copy(pdf, k.eingang / "kalt.pdf"), k)  # Assistent mit Vorlage
    assert _pos(s0) == soll, s0.tabellen_diagnose()
    r, _ = _nur_pdf(k, pdf)
    assert [(p.menge, p.einzelpreis, p.preiseinheit, p.kontrolle_gesamt) for p in r.positionen] == [
        (m, e, D("1"), g) for m, e, g in soll
    ]
