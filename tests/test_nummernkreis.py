# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Rechnungsnummer prüfen und Dateiname je Belegart (0.9.5). Fakturafalter vergibt keine Nummern (fiktive Daten)."""

import os
import shutil
from datetime import date

import pytest
import yaml

from fakturafalter import nummernkreis as nk
from fakturafalter import pflichtpruefung, pipeline
from fakturafalter.konfig import lade_konfig
from fakturafalter.modell import Partei, Rechnung

from .conftest import BEISPIELE

VARIANTE_K = "variante-k_kundenbezeichnung_erp.csv"


@pytest.mark.parametrize(
    "muster, ja, nein",
    [
        ("JJJJ######", ["2026000101", "1999123456"], ["202600010", "2026-00010", "3026000101", "GS2026000101"]),
        ("RE-JJJJ-####", ["RE-2026-0001", "re-2026-0001"], ["RE-2026-001", "RE2026-0001"]),
        ("GS-JJ/MM-###", ["GS-26/11-007"], ["GS-26/13-007"]),
        ("A*-####", ["A-0001", "AB.C-0001"], ["B-0001"]),
        ("R.####", ["R.0001"], ["RX0001"]),  # Punkt ist wörtlich, kein Regex
    ],
)
def test_pruefmuster(muster, ja, nein):
    assert nk.muster_pruefen(muster) == ""
    assert all(nk.passt(n, muster) for n in ja)
    assert not any(nk.passt(n, muster) for n in nein)


def test_luecke():
    m = "JJJJ######"
    assert nk.luecke("2026000105", {"2026000101", "2026000102"}, m) == ("2026000102", 2)
    assert nk.luecke("2026000103", {"2026000101", "2026000102"}, m) is None
    assert nk.luecke("2026000001", {"2025000999"}, m) is None  # neues Jahr = neuer Kreis
    assert nk.luecke("2026000101", set(), m) is None
    assert nk.luecke("2026000102", {"2026000109"}, m) is None  # nur Vorgänger zählen
    assert nk.luecke("RE-2026-0005", {"RE-2026-0003"}, "RE-JJJJ-####") == ("RE-2026-0003", 1)


def _r(nr="2026000101", art="380", name="Café Morgenrot", kdnr="K-1001"):
    return Rechnung(nummer=nr, datum=date(2026, 11, 24), art=art, kundennummer=kdnr, kaeufer=Partei(name=name))


def test_dateiname_platzhalter_und_bereinigung():
    r = _r(name='Müller & Söhne GmbH: "Werk/Süd" <Lager>* ' + "x" * 80)
    n = nk.dateiname("{jahr}_{rechnungsnummer}_{kunde}", r, ".pdf")
    assert n.startswith("2026_2026000101_Mueller_Soehne_GmbH_Werk_Sued_Lager")
    assert n.endswith(".pdf") and len(n) <= 5 + 1 + 10 + 1 + nk.KUNDE_MAX + 4
    assert not set(n) & set('\\/:*?"<>|') and n.isascii()
    assert nk.dateiname("{belegart_kurz}-{datum}-{kundennummer}.pdf", r, ".pdf") == "RE-2026-11-24-K-1001.pdf"
    assert nk.dateiname("{belegart} {monat}{tag}", _r(art="381"), ".xml") == "Gutschrift 1124.xml"
    assert nk.dateiname("{kunde}_{rechnungsnummer}", _r(name=""), ".pdf") == "2026000101.pdf"
    assert nk.dateiname("{rechnungsnummer}", _r(nr="RE/2026\\7:1"), ".pdf") == "RE_2026_7_1.pdf"
    assert nk.dateiname("CON", _r(), ".pdf") == "_CON.pdf"
    assert nk.dateiname("{rechnungsnummer}...", _r(), ".pdf") == "2026000101.pdf"
    assert nk.dateiname("{rechnungsnummer}_zugferd", _r(), ".pdf") == "2026000101_zugferd.pdf"


@pytest.mark.parametrize("muster", ["{nummer}.pdf", "a/b", "a:b", "x;y", "a,b", "{jahr", "a*b"])
def test_dateiname_ungueltig(muster):
    assert nk.dateiname_pruefen(muster)
    with pytest.raises(nk.MusterFehler):
        nk.dateiname(muster, _r(), ".pdf")


def test_optionen_hin_und_zurueck():
    assert nk.aus_optionen({}) == {} and nk.aus_optionen({"nummernkreise": None}) == {}
    opt = {"nummernkreise": {"rechnung": {"pruefmuster": "JJJJ######", "luecken_warnen": True},
                             "gutschrift": {"dateiname": "{belegart}_{rechnungsnummer}"}}}
    k = nk.aus_optionen(opt)
    assert k["rechnung"].pruefmuster == "JJJJ######" and k["gutschrift"].pruefmuster == ""
    assert nk.in_optionen(k) == opt["nummernkreise"]
    assert nk.in_optionen({"rechnung": nk.Kreis()}) == {}
    assert nk.muster_beispiel("JJJJ######") == "2026000123"
    assert nk.muster_beispiel("GS-JJ-MM-####") == "GS-26-11-0123"


def test_alte_konfiguration_unveraendert(konfig):
    assert konfig.nummernkreise == {}
    r = _r(nr="RE-2026-0001")
    assert pipeline.ausgabe_namen(r.nummer, r, konfig) == ("RE-2026-0001_zugferd.pdf", "RE-2026-0001_xrechnung.xml")
    assert pipeline.ausgabe_namen("RE-2026-0001") == pipeline.ausgabe_namen(r.nummer, r, konfig)
    ctx = pipeline.pflicht_kontext(konfig)
    assert ctx.nummernkreise == {}
    pflichtpruefung._luecken_warnungen(r, ctx)
    assert r.hinweise == []
    assert list(pflichtpruefung._nummer_muster(r, ctx)) == []


def _kreise(**kw):
    return nk.aus_optionen({"nummernkreise": kw})


def test_namen_je_belegart(konfig):
    konfig.nummernkreise = _kreise(rechnung={"dateiname": "{jahr}_{rechnungsnummer}_{kunde}"})
    assert pipeline.ausgabe_namen("2026000101", _r(), konfig) == ("2026_2026000101_Cafe_Morgenrot.pdf",
                                                          "2026000101_xrechnung.xml")
    gs = _r(nr="GS-2026-0011", art="381")
    assert pipeline.ausgabe_namen(gs.nummer, gs, konfig)[0] == "2026_GS-2026-0011_Cafe_Morgenrot.pdf"  # wie Rechnungen
    konfig.nummernkreise = _kreise(rechnung={"dateiname": "{jahr}_{rechnungsnummer}"},
                                   gutschrift={"dateiname": "{belegart}_{rechnungsnummer}.pdf",
                                               "dateiname_xrechnung": "GS_{rechnungsnummer}"})
    assert pipeline.ausgabe_namen(gs.nummer, gs, konfig) == ("Gutschrift_GS-2026-0011.pdf", "GS_GS-2026-0011.xml")
    konfig.nummernkreise = _kreise(gutschrift={"pruefmuster": "GS-JJJJ-####"})  # nur Prüfung, Namen wie bisher
    assert pipeline.ausgabe_namen(gs.nummer, gs, konfig) == ("GS-2026-0011_zugferd.pdf", "GS-2026-0011_xrechnung.xml")


def _pruefen(r, kreise, bekannte=(), lauf=()):
    ctx = pflichtpruefung.Kontext(bekannte_nummern=frozenset(bekannte), nummernkreise=kreise,
                                  lauf_nummern=frozenset(lauf))
    pflichtpruefung.pruefen(r, ctx)
    return r


def test_pflichtpruefung_muster_und_luecke(konfig):
    kreise = _kreise(rechnung={"pruefmuster": "JJJJ######", "luecken_warnen": True},
                     gutschrift={"pruefmuster": "GS-JJJJ-####"})
    r = _pruefen(_r(nr="RE-2026-1"), kreise)
    assert [h for h in r.hinweise if h.feld == "BT-1" and "Prüfmuster" in h.text and h.stufe == "pruefen"]
    assert r.nummer == "RE-2026-1"  # nie geändert
    r = _pruefen(_r(nr="2026000105"), kreise, bekannte={"2026000101"}, lauf={"2026000102", "2026000105"})
    w = [h for h in r.hinweise if h.stufe == "warnung" and "Lücke" in h.text]
    assert len(w) == 1 and "2026000102" in w[0].text and "2 Nummern" in w[0].text
    assert not [h for h in r.hinweise if h.feld == "BT-1" and h.stufe == "pruefen"]
    gs = _pruefen(_r(nr="2026000106", art="381"), kreise)  # Gutschrift hat ihr eigenes Muster
    assert [h for h in gs.hinweise if "GS-JJJJ-####" in h.text]
    ohne = _kreise(rechnung={"luecken_warnen": True})  # ohne Prüfmuster keine Lückenwarnung
    r = _pruefen(_r(nr="2026000105"), ohne, bekannte={"2026000101"})
    assert not [h for h in r.hinweise if "Lücke" in h.text]
    doppelt = _pruefen(_r(nr="2026000101"), kreise, bekannte={"2026000101"})
    assert doppelt.status == "pruefen"  # Dubletten bleiben gestoppt


def _mit_kreisen(konfig):
    konfig.sichtteil = "neu"
    konfig.nummernkreise = _kreise(
        rechnung={"pruefmuster": "JJJJ######", "luecken_warnen": True, "dateiname": "{jahr}_{rechnungsnummer}_{kunde}"},
        gutschrift={"pruefmuster": "GS-JJJJ-####", "dateiname": "{belegart}_{rechnungsnummer}"},
    )


def test_pipeline_eigene_namen_und_kollision(konfig, eingang):
    _mit_kreisen(konfig)
    lauf = pipeline.verarbeiten(eingang(VARIANTE_K), konfig)
    st = {e.nummer: e for e in lauf.ergebnisse}
    assert {n: e.status for n, e in st.items()} == {"2026000101": "ok", "2026000102": "ok", "GS-2026-0011": "ok"}
    namen = sorted(p.name for p in konfig.ausgang.glob("*.pdf"))
    assert namen == ["2026_2026000101_Feinmechanik_Beispiel_GmbH_Werk_Sued_War.pdf",
                     "2026_2026000102_Hofladen_Beispiel_Inh._Erika_Musterfrau.pdf",
                     "Gutschrift_GS-2026-0011.pdf"]
    # gleiche Namen, aber neue Nummer: Datei existiert -> Zu prüfen, nichts überschrieben
    konfig.nummernkreise["rechnung"].dateiname = "fest"
    vorher = (konfig.ausgang / namen[0]).stat().st_mtime_ns
    csv = konfig.eingang / "k2.csv"
    t = (BEISPIELE / VARIANTE_K).read_text(encoding="utf-8")
    csv.write_text(t.replace("2026000101", "2026000201").replace("2026000102", "2026000202"), encoding="utf-8")
    lauf = pipeline.verarbeiten([csv], konfig)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert sorted(st.values()) == ["ok", "pruefen", "pruefen"]  # 0201 ok -> fest.pdf, 0202 kollidiert; GS doppelt
    assert (konfig.ausgang / "fest.pdf").exists()
    assert (konfig.ausgang / namen[0]).stat().st_mtime_ns == vorher


def test_pipeline_ungueltiges_muster_haelt_an(konfig, eingang):
    konfig.sichtteil = "neu"
    konfig.nummernkreise = {"rechnung": nk.Kreis(dateiname="{unbekannt}")}
    lauf = pipeline.verarbeiten(eingang(VARIANTE_K), konfig)
    assert {e.status for e in lauf.ergebnisse} == {"pruefen"}
    assert not list(konfig.ausgang.glob("*.pdf"))


def test_pipeline_nummer_passt_nicht(konfig, eingang):
    konfig.sichtteil = "neu"
    konfig.nummernkreise = _kreise(rechnung={"pruefmuster": "RE-JJJJ-####"})
    lauf = pipeline.verarbeiten(eingang(VARIANTE_K), konfig)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert st == {"2026000101": "pruefen", "2026000102": "pruefen", "GS-2026-0011": "ok"}


def test_konfiguration_yaml(tmp_path):
    cfg = tmp_path / "cfg"
    shutil.copytree(BEISPIELE, cfg)
    p = cfg / "konfiguration.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["optionen"]["nummernkreise"] = {"rechnung": {"pruefmuster": "JJJJ######", "dateiname": "{rechnungsnummer}"}}
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    k = lade_konfig(p)
    assert k.nummernkreise["rechnung"].pruefmuster == "JJJJ######" and "gutschrift" not in k.nummernkreise


# ----------------------------------------------------------------------------------------- Oberfläche
@pytest.fixture
def dialog(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")

    from fakturafalter.gui import texte
    from fakturafalter.gui.app import anwendung
    from fakturafalter.gui.einstellungen import Einstellungen
    from fakturafalter.gui.hauptfenster import Hauptfenster

    app = anwendung()
    cfg = tmp_path / "cfg"
    shutil.copytree(BEISPIELE, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {n: str(tmp_path / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")}
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    texte.sprache_setzen("de")
    w = Hauptfenster(cfg / "konfiguration.yaml", tray_erlaubt=False)
    dlg = Einstellungen(w)
    yield dlg, app
    dlg.reject()
    w.beenden()
    app.processEvents()


def test_gui_vorschau_und_ergebnis(dialog):
    from PySide6.QtWidgets import QCheckBox, QLineEdit

    d, app = dialog
    vr = d.kreis_felder["rechnung"]["vorschau"]
    assert "2026000123_zugferd.pdf" in vr.text() and "2026000123_xrechnung.xml" in vr.text()
    assert "nummernkreise" not in d.ergebnis()["optionen"]  # nichts eingestellt -> Datei bleibt wie bisher
    luecken = d.findChild(QCheckBox, "luecken_rechnung")
    assert not luecken.isEnabled()
    d.findChild(QLineEdit, "pruefmuster_rechnung").setText("JJJJ######")
    d.findChild(QLineEdit, "dateiname_rechnung").setText("{jahr}_{rechnungsnummer}_{kunde}")
    app.processEvents()
    assert luecken.isEnabled()
    luecken.setChecked(True)
    assert "2026_2026000123_Cafe_Morgenrot_Werk_Sued.pdf" in vr.text()
    vg = d.kreis_felder["gutschrift"]["vorschau"]
    assert "2026_GS-2026-0007_Cafe_Morgenrot_Werk_Sued.pdf" in vg.text()  # Gutschrift: wie Rechnungen
    d.findChild(QLineEdit, "dateiname_gutschrift").setText("{belegart}_{rechnungsnummer}")
    assert "Gutschrift_GS-2026-0007.pdf" in vg.text()
    o = d.ergebnis()["optionen"]["nummernkreise"]
    assert o == {"rechnung": {"pruefmuster": "JJJJ######", "luecken_warnen": True,
                              "dateiname": "{jahr}_{rechnungsnummer}_{kunde}"},
                 "gutschrift": {"dateiname": "{belegart}_{rechnungsnummer}"}}
    d.findChild(QLineEdit, "dateiname_rechnung").setText("{nummer}")
    assert "Unbekannter Platzhalter" in vr.text() and vr.objectName() == "warn"
    d._speichern()
    assert "Unbekannter Platzhalter" in d.fehler.text()
    assert d.result() == 0
