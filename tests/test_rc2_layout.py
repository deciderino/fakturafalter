# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""rc2: Flexibler Layouteditor (Layoutformat 2) – Angaben je Baustein, „Briefpapier enthält …“, Pflichtprüfung
nach § 14 Abs. 4 UStG, Ablehnung alter Layouts, Platzhalter in Textfeldern. Alle Daten fiktiv."""

import copy
import io
import os
from pathlib import Path

import pdfplumber
import pytest
import yaml

from fakturafalter import adapter_csv, beispielrechnung, layout, pipeline, platzhalter, sicht
from fakturafalter import csv_einrichtung as ce
from fakturafalter.modell import Zahlung

BSP = Path(__file__).resolve().parent.parent / "beispiele"
BEISPIEL_YAML = BSP / "layout" / "layout-beispiel.yaml"


def _text(pdf: bytes, seite: int = 0) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return d.pages[seite].extract_text() or ""


def _woerter_in(pdf: bytes, e: layout.Element) -> str:
    from reportlab.lib.units import mm

    with pdfplumber.open(io.BytesIO(pdf)) as d:
        ws = d.pages[0].extract_words()
    return " ".join(
        w["text"] for w in ws
        if e.x * mm - 1 <= w["x0"] and w["x1"] <= (e.x + e.breite) * mm + 1
        and e.y * mm - 1 <= w["top"] and w["bottom"] <= (e.y + e.hoehe) * mm + 1
    )


def _r():
    return beispielrechnung.rechnung()


# ------------------------------------------------------------------ Format
def test_standard_ist_format2_und_wie_rc1():
    v = layout.standard()
    d = v.als_dict()
    assert d["version"] == 2
    b = d["seite1"]["bausteine"]
    assert b["absender"]["angaben"] == ["name", "anschrift"] and b["absender"]["sichtbar"] is True
    assert b["empfaenger"]["angaben"] == ["ruecksendezeile"] and "sichtbar" not in b["empfaenger"]
    assert b["fusszeile"]["angaben"] == list(layout.ANGABEN_JE["fusszeile"])
    assert "angaben" not in b["kopf"]
    assert layout.aus_dict(d).als_dict() == d
    # Ausgabe: Verkäufer wie bis rc1 in Absender, Rücksendezeile und Fußzeile
    r = _r()
    pdf = sicht.erzeugen(r, vorlage=v, sprache="de")
    assert _text(pdf).count(r.verkaeufer.name) == 3
    assert r.verkaeufer.ust_id in _text(pdf)
    befund = layout.pflicht_pruefen(v, r.verkaeufer, r.zahlung)
    assert befund.ok and befund.doppelt  # Name/Anschrift in Absender und Fußzeile: nur Hinweis


@pytest.mark.parametrize("roh", [{"version": 1, "raster": 5}, {"raster": 5}, {"version": "eins"}])
def test_altes_layout_wird_abgelehnt(roh):
    with pytest.raises(layout.LayoutAlt) as e:
        layout.aus_dict(roh)
    assert "Layoutformat 2" in str(e.value) and "Version 2" not in str(e.value)


def test_beispiel_yaml_ist_format2_und_vollstaendig():
    roh = yaml.safe_load(BEISPIEL_YAML.read_text(encoding="utf-8"))["layout"]
    assert roh["version"] == 2
    r = _r()
    v = layout.laden(roh, BSP, r.verkaeufer, r.zahlung)
    assert v.seite1.briefpapier_enthaelt == ["name"]
    pdf = sicht.erzeugen(r, vorlage=v, sprache="de")
    s = v.seite1
    assert r.verkaeufer.name not in _woerter_in(pdf, s.bausteine["absender"])  # steht im Briefpapier
    assert r.verkaeufer.anschrift.ort in _woerter_in(pdf, s.bausteine["absender"])


# ------------------------------------------------------------------ Renderer
def test_briefpapier_enthaelt_druckt_nicht_doppelt():
    r = _r()
    v = layout.standard()
    v.basis = BSP
    s = v.seite1
    s.briefpapier = "layout/briefpapier-seite1.pdf"
    s.briefpapier_enthaelt = ["name", "anschrift", "ust_id", "bank"]
    pdf = sicht.erzeugen(r, vorlage=v, sprache="de")
    t = _text(pdf)
    assert "USt-IdNr." not in t and t.count("IBAN") == 1  # IBAN nur noch im Zahlungsbaustein
    assert r.verkaeufer.register in t  # Register bleibt (nicht angehakt)
    assert t.count(r.verkaeufer.anschrift.strasse) == 1  # nur noch in der Rücksendezeile
    assert _woerter_in(pdf, s.bausteine["absender"]) == ""  # Absender entfällt
    # Empfänger, Kopf, Positionen, Summen bleiben
    assert r.kaeufer.anschrift.ort in _woerter_in(pdf, s.bausteine["empfaenger"])
    assert r.nummer in _woerter_in(pdf, s.bausteine["kopf"])
    assert "Gesamtbetrag" in _text(pdf) or "Summe" in _text(pdf)
    b = layout.pflicht_pruefen(v, r.verkaeufer, r.zahlung)
    assert b.ok, b.fehler
    assert any("Briefpapier" in x and "nicht noch einmal" in x for x in b.doppelt)
    # ohne Briefpapier zählt der Haken nicht (z. B. nicht PDF/A-taugliches Briefpapier entfernt)
    s.briefpapier = ""
    pdf2 = sicht.erzeugen(r, vorlage=v, sprache="de")
    assert "USt-IdNr." in _text(pdf2)


def test_ruecksendezeile_aus():
    r = _r()
    v = layout.standard()
    e = v.seite1.bausteine["empfaenger"]
    mit = _woerter_in(sicht.erzeugen(r, vorlage=v, sprache="de"), e)
    e.angaben = []
    ohne = _woerter_in(sicht.erzeugen(r, vorlage=v, sprache="de"), e)
    assert r.verkaeufer.name.split()[0] in mit and r.verkaeufer.name.split()[0] not in ohne
    assert r.kaeufer.anschrift.ort in ohne
    assert layout.aus_dict(v.als_dict()).seite1.bausteine["empfaenger"].angaben == []


def test_absender_ausblendbar_fusszeile_traegt():
    r = _r()
    v = layout.standard()
    v.seite1.bausteine["absender"].sichtbar = False
    assert layout.pflicht_pruefen(v, r.verkaeufer, r.zahlung).ok
    pdf = sicht.erzeugen(r, vorlage=v, sprache="de")
    assert _text(pdf).count(r.verkaeufer.name) == 2  # Rücksendezeile + Fußzeile


# ------------------------------------------------------------------ Pflichtprüfung
def test_pflicht_fehlt_blockiert_mit_wortlaut():
    r = _r()
    v = layout.standard()
    v.seite1.bausteine["absender"].sichtbar = False
    v.seite1.bausteine["fusszeile"].angaben = ["name", "ust_id", "bank"]
    b = layout.pflicht_pruefen(v, r.verkaeufer, r.zahlung)
    assert b.fehler == [
        "Seite 1: Die Anschrift des Verkäufers fehlt. Zeige die Angabe in einem Baustein oder hake am Briefpapier "
        "an, dass sie schon drauf ist."
    ]
    with pytest.raises(layout.LayoutFehler, match="Anschrift"):
        layout.laden(v.als_dict(), None, r.verkaeufer, r.zahlung)
    sicht.erzeugen(r, vorlage=v, sprache="de")  # Vorschau zeichnet trotzdem


def test_ust_steuernummer_register_bank_bedingt():
    r = _r()
    v = layout.standard()
    f = v.seite1.bausteine["fusszeile"]
    f.angaben = ["name", "anschrift", "steuernummer", "bank"]
    vk = copy.deepcopy(r.verkaeufer)
    vk.ust_id, vk.steuernummer, vk.register = "DE123456789", "", ""
    assert any("USt-IdNr." in x for x in layout.pflicht_pruefen(v, vk, r.zahlung).fehler)
    vk.ust_id, vk.steuernummer = "", "12/345/67890"
    assert layout.pflicht_pruefen(v, vk, r.zahlung).ok  # Steuernummer reicht, kein Register eingetragen
    vk.register = "HRB 99999 (fiktiv)"
    assert any("Handelsregister" in x for x in layout.pflicht_pruefen(v, vk, r.zahlung).fehler)
    vk.ust_id = "DE123456789"
    f.angaben.append("ust_id")
    assert layout.pflicht_pruefen(v, vk, r.zahlung).ok  # mit USt-IdNr. kein Register nötig
    # Bank: Zahlung aus, Fußzeile ohne Bank -> fehlt; Lastschrift -> nicht nötig
    f.angaben = ["name", "anschrift", "ust_id"]
    v.folgeseite.bausteine["fusszeile"].angaben = ["name", "anschrift", "ust_id"]
    for s in (v.seite1, v.folgeseite):
        s.bausteine["zahlung"].sichtbar = False
    assert any("Bankverbindung" in x for x in layout.pflicht_pruefen(v, vk, r.zahlung).fehler)
    assert layout.pflicht_pruefen(v, vk, Zahlung(art="59", iban="DE89370400440532013000", mandat="M-1")).ok
    assert layout.pflicht_pruefen(v, vk, Zahlung(iban="")).ok
    # Zahlung nur auf Seite 1 sichtbar: mehrseitige Rechnung hätte keine Bank -> fehlt
    v.seite1.bausteine["zahlung"].sichtbar = True
    assert any("Bankverbindung" in x for x in layout.pflicht_pruefen(v, vk, r.zahlung).fehler)
    v.folgeseite.bausteine["zahlung"].sichtbar = True
    assert layout.pflicht_pruefen(v, vk, r.zahlung).ok


def test_folgeseite_ohne_verkaeufer_nur_hinweis():
    r = _r()
    v = layout.standard()
    v.folgeseite.bausteine["absender"].sichtbar = False
    v.folgeseite.bausteine["fusszeile"].angaben = ["bank"]
    b = layout.pflicht_pruefen(v, r.verkaeufer, r.zahlung)
    assert b.ok
    assert "Folgeseite: Der Verkäufer steht hier nicht – das ist in Ordnung, er steht auf Seite 1." in b.hinweise


def test_doppelt_ist_nur_hinweis():
    r = _r()
    b = layout.pflicht_pruefen(layout.standard(), r.verkaeufer, r.zahlung)
    assert b.ok
    assert "Seite 1: Der Verkäufername steht doppelt (Absender und Fußzeile)." in b.doppelt


def test_ueberlappung_absender_ausgeblendet_erlaubt():
    v = layout.standard()
    a = v.seite1.bausteine["absender"]
    a.y = v.seite1.bausteine["empfaenger"].y
    assert any("überlappen" in x for x in layout.pruefen(v))
    a.sichtbar = False  # ausgeblendet: trägt keine Pflichtangabe
    assert layout.pruefen(v) == []


# ------------------------------------------------------------------ Pipeline
def test_pipeline_altes_layout_zu_pruefen_original_unberuehrt(konfig):
    alt = {"version": 1, "raster": 5.0, "seite1": {"bausteine": {}}}
    konfig.roh = {**konfig.roh, "layout": alt}
    vorher = copy.deepcopy(konfig.roh["layout"])
    r = _r()
    pipeline.layout_vorpruefen(r, konfig)
    assert r.status == "pruefen"
    assert any("Layoutformat 1" in h.text and "Layoutformat 2" in h.text for h in r.hinweise)
    assert konfig.roh["layout"] == vorher  # nichts migriert
    # Original-Druck als Sichtteil: Layout wird nicht gebraucht, Rechnung läuft weiter
    r2 = _r()
    r2.sicht_pdf = ("x.pdf", [0])
    konfig.sichtteil = "original"
    pipeline.layout_vorpruefen(r2, konfig)
    assert r2.status == "ok"


def test_pipeline_layout_ohne_pflicht_zu_pruefen(konfig):
    v = layout.standard()
    for s in (v.seite1, v.folgeseite):
        s.bausteine["absender"].sichtbar = False
        s.bausteine["fusszeile"].sichtbar = False
    konfig.roh = {**konfig.roh, "layout": v.als_dict()}
    r = _r()
    pipeline.layout_vorpruefen(r, konfig)
    assert r.status == "pruefen" and any("Verkäufername" in h.text for h in r.hinweise)


# ------------------------------------------------------------------ Platzhalter
def test_platzhalter_ersetzen():
    r = _r()
    r.bestellnummer = "B-2026-17"
    r.spalten = {"Projektleiter": "Erika Beispiel", "Bestellnummer": "B-2026-17"}
    t = "Bestellung {Bestellnummer} ({BT-13}) · PL {projektleiter} · {Gibt es nicht}· {{wörtlich}} · {BT-1}"
    assert platzhalter.ersetzen(t, r) == (
        f"Bestellung B-2026-17 (B-2026-17) · PL Erika Beispiel · · {{wörtlich}} · {r.nummer}"
    )
    assert platzhalter.ersetzen("Lieferung {BT-72}", r).startswith("Lieferung ")
    assert platzhalter.namen("{A} {B} {A}") == ["A", "B"]
    v = layout.standard()
    v.seite1.felder.append(
        layout.Element("text", 20, 200, 100, 10, text="Projekt: {Projektleiter} / {BT-13}", kennung="text1", ebene=5)
    )
    assert "Erika Beispiel / B-2026-17" in _text(sicht.erzeugen(r, vorlage=v, sprache="de"))


def test_platzhalter_aus_csv_nur_kopfwerte(tmp_path, konfig):
    csv = tmp_path / "export.csv"
    csv.write_text(
        "Rechnungsnummer;Rechnungsdatum;Kunde;Straße;PLZ;Ort;Lieferdatum;Artikel;Menge;Einheit;Einzelpreis;USt;"
        "Projektleiter;Bemerkung intern\n"
        "RE-9101;03.11.2026;Beispiel Handel GmbH;Beispielweg 1;10115;Berlin;30.10.2026;Schraube;10;Stück;1,50;19;"
        "Erika Beispiel;\n"
        "RE-9101;03.11.2026;Beispiel Handel GmbH;Beispielweg 1;10115;Berlin;30.10.2026;Mutter;5;Stück;0,20;19;"
        "Erika Beispiel;eilig\n",
        encoding="utf-8",
    )
    fmt = ce.format_erkennen(csv)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    z.pop("BT-22", None)
    z = {k: v for k, v in z.items() if v not in ("Projektleiter", "Bemerkung intern")}
    p = ce.profil_bauen("PH", csv, fmt, z, ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
                        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])))
    assert "Projektleiter" in p["datei"]["spalten"] and "Projektleiter" in ce.profil_spalten(p)
    r = adapter_csv.lesen(csv, p, konfig)[0]
    assert r.spalten["Projektleiter"] == "Erika Beispiel"
    assert r.spalten["Bemerkung intern"] == "eilig"  # erster nicht leerer Kopfwert
    assert "Artikel" not in r.spalten and "Menge" not in r.spalten  # Positionsspalten nicht
    assert platzhalter.ersetzen("{Projektleiter}", r) == "Erika Beispiel"


# ------------------------------------------------------------------ Editor (offscreen)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from fakturafalter.gui.app import anwendung

    return anwendung()


def _editor(qapp, tmp_path, roh=None, hell=True):
    from fakturafalter.gui import texte, thema
    from fakturafalter.gui.layouteditor import LayoutEditor

    texte.sprache_setzen("de")
    c = thema.anwenden(qapp, "hell" if hell else "dunkel")
    r = _r()
    w = LayoutEditor(None, c, roh, tmp_path, profil="Musterwerk GmbH", verkaeufer=r.verkaeufer,
                     zahlung=r.zahlung, spalten=["Projektleiter", "Kostenträger"])
    w.resize(1400, 900)
    w.show()
    qapp.processEvents()
    return w


def test_editor_angaben_und_pruefung(qapp, tmp_path):
    w = _editor(qapp, tmp_path)
    try:
        fuss = w.seite.bausteine["fusszeile"]
        w.waehlen(fuss)
        assert w.sichtbar.isEnabled() and "nicht fest vorgeschrieben" in w.e_hinweis.text()
        assert not w.angaben["bank"].isHidden() and w.angaben["ruecksendezeile"].isHidden()
        assert w.pruef_fehler.isHidden() and not w.pruef_doppelt.isHidden()  # Doppeltes: gelber Hinweis
        w.angaben["anschrift"].setChecked(False)
        assert fuss.angaben and "anschrift" not in fuss.angaben
        w.waehlen(w.seite.bausteine["absender"])
        w.sichtbar.setChecked(False)
        qapp.processEvents()
        assert not w.pruef_fehler.isHidden() and "Anschrift" in w.pruef_fehler.text()
        w.speichern()
        assert w.result() == 0 and w.isVisible()  # Speichern blockiert
        # kein stilles Abhaken: Briefpapier-Haken ändern die Bausteine nicht
        w.vorlage.seite1.briefpapier = "layout/x.pdf"
        dlg = w.briefpapier_dialog("seite1")
        assert dlg.windowTitle() == "Briefpapier – Seite 1"
        dlg.haken["anschrift"].setChecked(True)
        assert w.vorlage.seite1.briefpapier_enthaelt == ["anschrift"]
        assert "anschrift" not in fuss.angaben and not w.seite.bausteine["absender"].sichtbar
        assert w.pruef_fehler.isHidden()
        dlg.b_weg.click()
        assert w.vorlage.seite1.briefpapier == "" and w.vorlage.seite1.briefpapier_enthaelt == []
        # Empfänger: Rücksendezeile
        w.waehlen(w.seite.bausteine["empfaenger"])
        assert not w.sichtbar.isEnabled() and not w.angaben["ruecksendezeile"].isHidden()
        assert "Fensterkuverts" in w.l_angaben_hinweis.text()
    finally:
        w.close()


def test_editor_platzhalter_picker(qapp, tmp_path):
    w = _editor(qapp, tmp_path)
    try:
        w.feld_hinzufuegen("text")
        e = w.element()
        assert e.art == "text" and not w.b_platzhalter.isHidden()
        m = w.platzhalter_menue()
        daten = [a.data() for a in m.actions() if a.data()]
        assert "{BT-13}" in daten and "{Projektleiter}" in daten and "{Kostenträger}" in daten
        w.text.setPlainText("Bestellung: ")
        cur = w.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        w.text.setTextCursor(cur)
        next(a for a in m.actions() if a.data() == "{BT-13}").trigger()
        assert e.text == "Bestellung: {BT-13}"
        w.waehlen(w.seite.bausteine["kopf"])
        assert w.b_platzhalter.isHidden()
    finally:
        w.close()


def test_editor_lehnt_format1_ab_datei_unveraendert(qapp, tmp_path):
    roh = {"version": 1, "raster": 5.0, "seite1": {"briefpapier": "layout/alt.pdf"}}
    vorher = copy.deepcopy(roh)
    w = _editor(qapp, tmp_path, roh)
    try:
        qapp.processEvents()
        assert "Layoutformat 1" in w.alt_meldung and "1.0.0-rc1" in w.alt_meldung
        assert w.findChild(object, "layout_alt") is not None
        assert w.vorlage.seite1.briefpapier == ""  # kein automatisch angehängtes Briefpapier
        assert roh == vorher
        assert w.ergebnis()["version"] == 2
    finally:
        w.close()


@pytest.mark.parametrize("hell", [True, False])
def test_pruefkaesten_wcag_aa(hell):
    from fakturafalter.gui import thema

    def lum(h):
        h = h.lstrip("#")
        rgb = [int(h[i: i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def k(a, b):
        la, lb = sorted((lum(a), lum(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)

    c = thema.farben(hell)
    assert k(c["er_t"], c["er_bg"]) >= 4.5 and k(c["in_t"], c["in_bg"]) >= 4.5


@pytest.mark.parametrize("hell", [True, False])
def test_briefpapier_dialog_hinweis_nicht_abgeschnitten(qapp, tmp_path, hell):
    w = _editor(qapp, tmp_path, hell=hell)
    try:
        w.vorlage.seite1.briefpapier = "layout/x.pdf"
        dlg = w.briefpapier_dialog("seite1")
        dlg.show()
        for _ in range(3):
            qapp.processEvents()
        lab = dlg.l_hinweis
        assert lab.height() >= lab.heightForWidth(lab.width()) - 1, (lab.height(), lab.heightForWidth(lab.width()))
        assert dlg.b_fertig.geometry().top() >= lab.geometry().bottom()
        dlg.accept()
    finally:
        w.close()


@pytest.mark.parametrize("sprache", ["de", "en"])
def test_platzhalter_namen_ohne_rohe_bt_nummer(qapp, tmp_path, sprache):
    from fakturafalter.gui import texte

    w = _editor(qapp, tmp_path)
    try:
        texte.sprache_setzen(sprache)
        (_g, rechnung), *_rest = w.platzhalter_liste()
        for anzeige, ph in rechnung:
            bt = ph.strip("{}")
            assert not anzeige.startswith(bt), anzeige  # immer ein Name vor der Nummer, nie „BT-56 (BT-56)“
        namen = dict((ph, a) for a, ph in rechnung)
        if sprache == "en":
            assert namen["{BT-9}"].startswith("Payment due date") and namen["{BT-56}"].startswith("Buyer contact point")
        else:
            assert namen["{BT-56}"].startswith("Kontaktstelle des Käufers")
    finally:
        texte.sprache_setzen("de")
        w.close()
