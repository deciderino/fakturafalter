# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kleinigkeiten nach dem 0.6.0-Test: Spalte „Kunde“, Zuordnung IBAN/Bezug, Gutschrift-Ansicht, Probe mit Hinweisen,
Probe-Tabelle in voller Breite, umbrechendes Protokoll. Alle Daten erfunden."""
import os
import subprocess

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from fakturafalter import adapter_xml, cii, csv_einrichtung as ce, pipeline, rechnen, sicht

from .conftest import BEISPIELE
from .test_gui import fenster, konfig_datei, qapp  # noqa: F401 – Fixtures
from .voll import volle_rechnung

VARIANTE_D = BEISPIELE / "variante-d_rabatt_gutschrift_lastschrift.csv"


# --- 1 + 2: Spaltenvorschläge ---------------------------------------------------------------------------------

def test_kunde_mit_nummern_wird_kundennummer():
    fmt = ce.format_erkennen(VARIANTE_D)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    assert z["kundennummer"] == "Kunde" and "BT-44" not in z
    assert (z["BT-91"], z["BT-25"], z["BT-26"]) == ("IBAN Kunde", "Bezug auf", "Bezug vom")


@pytest.mark.parametrize("kopf,zeilen,erwartet", [
    (["Nr", "Kunde"], [["R-1", "Fiktiv AG"], ["R-2", "Beispiel GmbH & Co. KG"]], {"BT-44": "Kunde"}),
    (["Nr", "Kunde"], [["R-1", "K-1001"], ["R-2", "10023"]], {"kundennummer": "Kunde"}),
    (["Nr", "Kunde"], None, {"BT-44": "Kunde"}),                   # ohne Werte wie bisher der Name
    (["Nr", "Kd.-Nr.", "Kundenname"], [["R-1", "K-1", "Fiktiv AG"]], {"kundennummer": "Kd.-Nr.", "BT-44": "Kundenname"}),
    (["Nr", "Kunden-Nr", "Kunde"], [["R-1", "K-1", "K-1"]], {"kundennummer": "Kunden-Nr", "BT-44": "Kunde"}),
])
def test_kunde_name_oder_nummer(kopf, zeilen, erwartet):
    z = ce.spalten_vorschlagen(kopf, zeilen)
    assert {f: z[f] for f in ("kundennummer", "BT-44") if f in z} == erwartet


def test_beispiel_mit_kundennamen_bleibt_name():
    fmt = ce.format_erkennen(BEISPIELE / "industrie" / "eingang" / "normteile_NB-26-1001.csv")
    assert ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)["BT-44"] == "Kunde"


# --- 3: Gutschrift-Ansicht -----------------------------------------------------------------------------------

def _text(r, tmp_path, sprache="de"):
    p = tmp_path / f"{r.nummer}-{sprache}.pdf"
    p.write_bytes(sicht.erzeugen(r, sprache=sprache))
    return " ".join(subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout.split())


def _variante_d(konfig):
    _, rs = pipeline.einlesen(VARIANTE_D, konfig)
    for r in rs:
        rechnen.berechnen(r)
    return {r.nummer: r for r in rs}


def test_gutschrift_ohne_zahlungsziel_und_mit_eigenem_fusstext(konfig, tmp_path):
    rs = _variante_d(konfig)
    g = _text(rs["GS-2026-0007"], tmp_path)
    assert "Zahlbar" not in g and "Fällig am" not in g and "überweisen" not in g
    assert "Der Betrag wird Ihnen gutgeschrieben." in g
    assert "Diese Gutschrift enthält die strukturierten Rechnungsdaten" in g and "Diese Rechnung enthält" not in g
    e = _text(rs["GS-2026-0007"], tmp_path, "en")
    assert "The amount will be credited to you." in e and "This credit note contains the structured" in e
    a = _text(rs["RE-2026-0201"], tmp_path)                       # Rechnung unverändert
    assert "Zahlbar innerhalb" in a and "Diese Rechnung enthält die strukturierten Rechnungsdaten" in a
    assert "This invoice contains" in _text(rs["RE-2026-0201"], tmp_path, "en")


def test_korrektur_negativ_wie_gutschrift_positiv_wie_rechnung(konfig, tmp_path):
    r = _variante_d(konfig)["RE-2026-0202"]
    r.art = "384"
    t = _text(r, tmp_path)
    assert "Diese Rechnungskorrektur enthält" in t and "gutgeschrieben" not in t
    assert sicht.ist_gutschrift(r, -1) and not sicht.ist_gutschrift(r, 1)
    r.art = "380"
    assert not sicht.ist_gutschrift(r, -1)


# --- 4 + 5: Probe-Tabelle ------------------------------------------------------------------------------------

def test_probe_zeigt_hinweise_und_fuellt_breite(konfig, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel
    from fakturafalter.gui.datenassistent import _Assistent
    app = QApplication.instance() or QApplication([])
    x = cii.erzeugen(volle_rechnung(konfig), "EN16931").decode()
    x = x.replace("</ram:ApplicableHeaderTradeAgreement>",
                  "<ram:SalesAgentTradeParty><ram:Name>Vertreter Beispiel</ram:Name></ram:SalesAgentTradeParty>"
                  "</ram:ApplicableHeaderTradeAgreement>", 1)
    (tmp_path / "c.xml").write_text(x, encoding="utf-8")
    erg = ce.probe(adapter_xml.lesen(tmp_path / "c.xml", konfig), konfig)
    assert erg[0].status == "ok" and erg[0].hinweise
    t = _Assistent._probe_tabelle(None)
    t.resize(560, 300)
    t.show()
    l_sum = QLabel()
    _Assistent._probe_zeigen(None, t, l_sum, erg)
    app.processEvents()
    assert t.item(0, 3).text().startswith("bereit, mit Hinweisen: ") and "SalesAgentTradeParty" in t.item(0, 3).text()
    assert l_sum.objectName() == "warn" and "1 davon mit Hinweisen" in l_sum.text()
    h = t.horizontalHeader()
    assert h.stretchLastSection() and sum(h.sectionSize(i) for i in range(4)) >= t.viewport().width() - 2
    assert not t.horizontalScrollBar().isVisible() and t.rowHeight(0) > 40          # langer Hinweis bricht um
    _Assistent._probe_zeigen(None, t, l_sum, [ce.Probe("R-1", "Fiktiv AG", "10.00", "ok", [])])
    app.processEvents()
    assert t.item(0, 3).text() == "bereit" and l_sum.objectName() == "gut" and t.rowHeight(0) >= 40
    assert sum(h.sectionSize(i) for i in range(4)) >= t.viewport().width() - 2
    t.close()


def test_protokoll_bricht_um(fenster, qapp):
    from PySide6.QtWidgets import QPlainTextEdit
    fenster.pruefansicht_oeffnen(2)
    pa = fenster.pruef_fenster
    assert pa.protokoll.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    pa.close()
