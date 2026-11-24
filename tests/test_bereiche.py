# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""„Bereiche festlegen“: vom Nutzer gezogene Rahmen für Anschrift, Rechnungskopf, Summen und
Zahlungsbedingungen – Lesen nur im Rahmen, Seitensuche bei „allen Seiten“, Speichern/Laden, alte Vorlagen.
Alle Rechnungen sind erfunden (tests/erp_roh.py)."""

import shutil
from pathlib import Path

import pytest
import yaml

from fakturafalter import anlernen, konfig, pdferkennung

from . import erp_roh

IND = Path(__file__).resolve().parent.parent / "beispiele" / "industrie"
ZAHLUNG = [
    " Zahlbar innerhalb 14 Tagen ohne Abzug,",
    " bei Zahlung binnen 8 Tagen 2 % Skonto.",
    " Bitte bei Zahlung die Belegnummer angeben.",
]
# Rahmen in pt (x0, top, x1, bottom) passend zu erp_roh.rechnung_mehrseitig ohne Briefkopf auf Folgeseiten
ANSCHRIFT = (20, 140, 300, 195)  # Seite 1
KOPF = (20, 225, 560, 268)  # Seite 1
SUMMEN = (300, 132, 560, 176)  # letzte Seite
ZAHLUNGSBEREICH = (20, 182, 400, 224)  # letzte Seite


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


def _pdf(k, name, seiten, beleg="26000042"):
    return erp_roh.rechnung_mehrseitig(
        k.eingang / f"{name}.pdf",
        seiten,
        briefkopf_folgeseiten=False,
        nach=erp_roh.fuss() + [""] + ZAHLUNG,
        beleg=beleg,
    )


def _zwei_seiten(k, name="m1", beleg="26000042"):
    return _pdf(k, name, [erp_roh.STANDARD[:2], erp_roh.STANDARD[2:]], beleg)


def _alle_bereiche(s):
    s.zone_setzen("anschrift", 0, ANSCHRIFT)
    s.zone_setzen("kopf", 0, KOPF)
    s.zone_setzen("summen", 1, SUMMEN)
    s.zone_setzen("zahlung", 1, ZAHLUNGSBEREICH)


def _speichern(k, s):
    s.absender = anlernen.Sitzung(
        shutil.copy(IND / "eingang" / "NB-26-1001.pdf", k.eingang), k
    ).absender
    if s.werte["BT-52"].status == "fehlt":  # ohne Bereich: Anschrift wie bisher als Block ziehen
        s.anschrift_setzen(0, ANSCHRIFT)
    if s.werte["leistung"].status == "fehlt":
        s.setzen("leistung", "05.10.2026")
    for f in s.fehlende():
        s.bestaetigen(f)
    assert s.fertig(), s.fehlende()
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    return v


def _werte(s, *felder):
    return {f: s.werte[f].wert for f in felder}


def test_bereiche_auf_allen_seiten_summen_hinten_anschrift_vorn(k):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    _alle_bereiche(s)
    assert _werte(s, "BT-44", "BT-50", "BT-53", "BT-52") == {
        "BT-44": "Beispiel Werkzeugbau GmbH",
        "BT-50": "Musterweg 12",
        "BT-53": "12345",
        "BT-52": "Musterstadt",
    }
    assert s.werte["BT-109"].wert == "1.271,00" and s.werte["BT-109"].woerter[0].seite == 1
    assert s.werte["BT-1"].wert == "26000042"
    v = _speichern(k, s)
    assert set(v["bereiche"]) == {"anschrift", "kopf", "summen", "zahlung"}
    assert all(b["seiten"] == "alle" for b in v["bereiche"].values())

    # nächste Rechnung: drei Seiten – Summen jetzt auf Seite 3, Anschrift weiter auf Seite 1
    s2 = anlernen.Sitzung(
        _pdf(
            k, "m2", [erp_roh.STANDARD[:1], erp_roh.STANDARD[1:2], erp_roh.STANDARD[2:]], "26000043"
        ),
        k,
    )
    assert s2.vorlage is not None and set(s2.zonen) == set(v["bereiche"])
    for f in ("BT-1", "BT-2", "BT-109", "BT-112", "BT-20", "BT-44", "BT-53", "BT-52"):
        assert s2.werte[f].status == "erkannt", (f, s2.werte[f].wert, s2.werte[f].hinweis)
    assert s2.werte["BT-1"].wert == "26000043"
    assert s2.werte["BT-109"].wert == "1.271,00" and s2.werte["BT-109"].woerter[0].seite == 2
    assert (
        s2.werte["BT-44"].wert == "Beispiel Werkzeugbau GmbH"
        and s2.werte["BT-52"].wert == "Musterstadt"
    )


def test_nur_im_rahmen_gelesen(k):
    """Liegt ein Wert außerhalb des Rahmens, wird er nicht gefunden – auch wenn er anderswo auf der Seite steht."""
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    assert s.werte["BT-109"].wert == "1.271,00"
    s.zone_setzen("summen", 0, (300, 600, 560, 700))  # Rahmen an einer leeren Stelle
    assert s.werte["BT-109"].wert == "" and "Bereich" in s.werte["BT-109"].hinweis


def test_gilt_auf_erste_und_letzte_seite(k):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    s.zone_setzen("summen", 1, SUMMEN, seiten="erste")
    assert s.zone_seiten("summen") == [0] and s.werte["BT-109"].wert == ""
    s.zone_seiten_setzen("summen", "letzte")
    assert s.zone_seiten("summen") == [1] and s.werte["BT-109"].wert == "1.271,00"
    zs = s.zeilen
    assert pdferkennung.bereich_seitenfolge("summen", {"seiten": "alle"}, zs) == [1, 0]
    assert pdferkennung.bereich_seitenfolge("kopf", {"seiten": "alle"}, zs) == [0, 1]


def test_zu_kleiner_autorahmen_wird_durch_nutzerrahmen_ersetzt(k):
    """Die Vorlage kennt nur einen zu knappen Anschriftrahmen (nur die erste Zeile); der Bereich des Nutzers
    gilt – nie kleiner als sein Rahmen, bis „PLZ Ort“."""
    zeilen = anlernen.Sitzung(_zwei_seiten(k), k).zeilen
    knapp = {
        "typ": "text",
        "lage": "bereich",
        "block": True,
        "seite": 0,
        "rahmen": [20, 140, 120, 150],
    }
    ohne = pdferkennung.vorlage_anschrift_lesen({}, knapp, zeilen)
    assert "BT-52" not in ohne  # automatischer Rahmen allein: Ort fehlt
    v = {"bereiche": {"anschrift": {"rahmen": list(ANSCHRIFT), "seiten": "alle"}}}
    mit = pdferkennung.vorlage_anschrift_lesen(v, knapp, zeilen)
    assert mit["BT-44"][0] == "Beispiel Werkzeugbau GmbH" and mit["BT-50"][0] == "Musterweg 12"
    assert mit["BT-53"][0] == "12345" and mit["BT-52"][0] == "Musterstadt"


def test_vorschlag_uebernehmen_und_vergroessern(k):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    seite, r = s.zone_vorschlag("summen")
    assert seite == 1 and r[0] < r[2] and r[1] < r[3]
    s.zone_setzen("summen", seite, r)
    assert s.werte["BT-109"].wert == "1.271,00"
    groesser = (r[0] - 20, r[1] - 10, r[2] + 20, r[3] + 10)
    s.zone_setzen("summen", seite, groesser)
    assert s.zonen["summen"]["rahmen"] == [
        round(x, 1) for x in groesser
    ]  # neuer Rahmen ersetzt den alten
    assert s.werte["BT-109"].wert == "1.271,00"


def test_zahlungsbedingungen_im_rahmen_mehrzeilig(k):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    s.zone_setzen("zahlung", 1, ZAHLUNGSBEREICH)
    assert s.werte["BT-20"].wert == " ".join(z.strip() for z in ZAHLUNG)
    v = _speichern(k, s)
    assert v["felder"]["BT-20"]["lage"] == "bereich"
    s2 = anlernen.Sitzung(_zwei_seiten(k, "m2", "26000043"), k)
    assert s2.werte["BT-20"].status == "erkannt"
    assert s2.werte["BT-20"].wert == " ".join(z.strip() for z in ZAHLUNG)


def test_bereiche_speichern_und_laden(k):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    _alle_bereiche(s)
    s.zone_seiten_setzen("anschrift", "erste")
    _speichern(k, s)
    (datei,) = (Path(k.pdf_profile[-1]["_basis"]) / "angelernt").glob("*.yaml")
    roh = yaml.safe_load(datei.read_text(encoding="utf-8"))
    assert roh["bereiche"]["anschrift"] == {
        "rahmen": [float(x) for x in ANSCHRIFT],
        "seiten": "erste",
    }
    assert roh["bereiche"]["summen"]["rahmen"] == [float(x) for x in SUMMEN]
    s2 = anlernen.Sitzung(_zwei_seiten(k, "m2", "26000043"), k)
    assert s2.zonen == pdferkennung.bereiche_laden(roh)
    assert not s2.zonen_geaendert()
    s2.zone_entfernen("zahlung")
    assert s2.zonen_geaendert() == ["zahlung"]


def test_alte_vorlage_ohne_bereiche_laedt(k):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    _speichern(k, s)
    (datei,) = (Path(k.pdf_profile[-1]["_basis"]) / "angelernt").glob("*.yaml")
    roh = yaml.safe_load(datei.read_text(encoding="utf-8"))
    assert "bereiche" not in roh  # ohne Bereiche wird auch keiner geschrieben
    s2 = anlernen.Sitzung(_zwei_seiten(k, "m2", "26000043"), k)
    assert s2.vorlage is not None and s2.zonen == {}
    assert s2.werte["BT-1"].wert == "26000043" and s2.werte["BT-1"].status == "erkannt"
    assert s2.werte["BT-109"].status == "erkannt"


@pytest.mark.parametrize(
    "roh",
    [
        None,
        {},
        {"bereiche": None},
        {"bereiche": {"anschrift": "kaputt"}},
        {"bereiche": {"unbekannt": {"rahmen": [0, 0, 10, 10]}}},
        {"bereiche": {"summen": {"rahmen": [1, 2]}}},
        {"bereiche": {"summen": {"rahmen": [10, 10, 10, 10]}}},
    ],
)
def test_bereiche_laden_robust(roh):
    assert pdferkennung.bereiche_laden(roh) == {}


def test_bereiche_laden_standard_alle_seiten():
    assert pdferkennung.bereiche_laden(
        {"bereiche": {"kopf": {"rahmen": [1, 2, 30, 40], "seiten": "x"}}}
    ) == {"kopf": {"rahmen": [1.0, 2.0, 30.0, 40.0], "seiten": "alle"}}


def test_bereich_geaendert_zaehlt_als_korrektur(k, caplog):
    s = anlernen.Sitzung(_zwei_seiten(k), k)
    _alle_bereiche(s)
    _speichern(k, s)
    s2 = anlernen.Sitzung(_zwei_seiten(k, "m2", "26000043"), k)
    _speichern(k, s2)
    (datei,) = (Path(k.pdf_profile[-1]["_basis"]) / "angelernt").glob("*.yaml")
    vor = yaml.safe_load(datei.read_text(encoding="utf-8"))
    assert vor["statistik"]["folge_treffer"] >= 1
    s3 = anlernen.Sitzung(_zwei_seiten(k, "m3", "26000044"), k)
    s3.zone_setzen("summen", 1, (SUMMEN[0] - 10, SUMMEN[1], SUMMEN[2], SUMMEN[3] + 10))
    assert s3.zonen_geaendert() == ["summen"]
    with caplog.at_level("INFO"):
        _speichern(k, s3)
    nach = yaml.safe_load(datei.read_text(encoding="utf-8"))
    assert nach["statistik"]["folge_treffer"] == 0
    assert "Bereiche geändert (Summen)" in caplog.text


def test_summen_und_zahlung_wandern_mit_der_tabelle(k):
    """Summen/Zahlungsbedingungen unter der Tabelle: bei weniger/mehr Positionen steht der Inhalt höher/tiefer –
    der Rahmen wandert mit dem Tabellenende mit (``bezug``), der Zähler läuft weiter."""
    erste = anlernen.Sitzung(shutil.copy(IND / "eingang" / "NB-26-1001.pdf", k.eingang), k)
    for z in anlernen.ZONEN:
        vs = erste.zone_vorschlag(z)
        if vs:
            erste.zone_setzen(z, *vs)
    for f in erste.fehlende():
        erste.bestaetigen(f)
    erg, v = erste.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    assert "bezug" in v["bereiche"]["summen"] and "bezug" not in v["bereiche"]["kopf"]
    # NB-26-1002 hat weniger Positionen: Summen stehen gut 30 pt höher als beim Anlernen
    s = anlernen.Sitzung(shutil.copy(IND / "eingang" / "NB-26-1002.pdf", k.eingang), k)
    assert s.fehlende() == []
    assert _werte(s, "BT-109", "BT-112") == {"BT-109": "568,50", "BT-112": "676,52"}
    assert s.werte["BT-20"].wert
    assert pdferkennung.bereiche_unterschied(s.vorlage.get("bereiche"), s.zonen) == []
    erg, v = s.speichern(k.pfad_datei)
    assert erg.status == "ok", erg.hinweise
    assert v["statistik"]["folge_treffer"] == 1 and "zurueckgesetzt" not in v["statistik"]


def test_bezug_zaehlt_nicht_als_aenderung():
    alt = {"summen": {"rahmen": [300, 400, 560, 450], "seiten": "alle", "bezug": 395.9}}
    neu = {"summen": {"rahmen": [300, 400, 560, 450], "seiten": "alle"}}
    assert pdferkennung.bereiche_unterschied(alt, neu) == []
    assert pdferkennung._zonen_rahmen(alt["summen"], -30) == [300, 370, 560, 450]  # nie kleiner
    assert pdferkennung._zonen_rahmen(alt["summen"], 20) == [300, 400, 560, 470]
