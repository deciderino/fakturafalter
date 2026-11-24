"""Fiktives Set „kommentarzeilen“ (testdaten/fiktiva d62a2f4): Kommentarzeilen unter Positionen, die in der
Einheitenspalte beginnen, und eine Rechnungsnummer oben links außerhalb des Kopfblocks."""

import shutil
from pathlib import Path

import yaml

from fakturafalter import anlernen, konfig, pdferkennung

DATEN = Path(__file__).parent / "daten" / "kommentarzeilen"
BEISPIEL = Path(__file__).parent.parent / "beispiele" / "industrie" / "konfiguration-nur-pdf.yaml"
PDF1, PDF2 = DATEN / "Rechnung_001_2026-04711.pdf", DATEN / "Rechnung_002_2026-04738.pdf"


def _k(tmp_path):
    roh = yaml.safe_load(BEISPIEL.read_text(encoding="utf-8"))
    roh["arbeitsordner"] = str(tmp_path / "lauf")
    tmp_path.mkdir(parents=True, exist_ok=True)
    pf = tmp_path / "k.yaml"
    pf.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
    k = konfig.lade_konfig(pf)
    k.ordner_anlegen()
    k.pfad_datei = pf
    return k


def _sitzung(k, pdf):
    return anlernen.Sitzung(Path(shutil.copy(pdf, k.eingang)), k)


def _speichern(k, s):
    for f in s.fehlende():
        s.bestaetigen(f)
    erg, v = s.speichern(k.pfad_datei)
    assert v is not None, erg.hinweise
    return v


def test_kommentarzeile_ab_einheitenspalte_gehoert_zur_bezeichnung(tmp_path):
    k = _k(tmp_path)
    s = _sitzung(k, PDF1)
    pos = s.positionen()
    assert [p.einheit_text for p in pos] == ["Stk."] * 4 + ["Std."]
    assert pos[1].bezeichnung.endswith("26-0731 davon mit Härtung 12 Stück")
    assert pos[3].bezeichnung.endswith("44-1907 davon Restmenge folgt")
    v = _speichern(k, s)
    pos2 = pdferkennung.positionen_auslesen(v["positionen"], _sitzung(k, PDF2).zeilen)
    assert len(pos2) == 5 and all(p.einheit_text == "Stk." for p in pos2)
    assert pos2[0].bezeichnung.endswith("18-6604 davon 8 Stück brüniert")
    assert pos2[3].bezeichnung.endswith("63-3390 Restmenge 2 Stück folgt in KW 46")


def test_rechnungsnummer_ausserhalb_kopfbereich_nur_nach_klick_gelernt(tmp_path):
    for art in ("klick", "getippt"):
        k = _k(tmp_path / art)
        s = _sitzung(k, PDF1)
        s.zone_setzen(
            "kopf", 0, (330, 140, 570, 250)
        )  # Kopfblock rechts; „Rechnung Nr.“ steht links oben
        if art == "klick":
            s.setzen("BT-1", *s.wort_an(0, 140, 119))  # Klick auf den Wert, Beschriftung ohne „:“
            assert (s.werte["BT-1"].wert, s.werte["BT-1"].hinweis) == ("2026-04711", "")
        else:
            s.setzen("BT-1", "2026-04711", None)
            assert "anklicken oder Rahmen ziehen" in s.werte["BT-1"].hinweis
        v = _speichern(k, s)
        if art == "klick":
            assert v["felder"]["BT-1"].get("ohne_bereich") is True
            assert _sitzung(k, PDF2).werte["BT-1"].wert == "2026-04738"
        else:
            assert "BT-1" not in v["felder"]
