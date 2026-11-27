# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""1.0.0-rc1: Ablehnung alter Profile in der Oberfläche und im Eingang (nur fiktive Daten)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml

pytest.importorskip("PySide6")

from fakturafalter.profilformat import ProfilVeraltet, pruefen

from .test_gui import BEISPIELE, fenster, konfig_datei, qapp, warten  # noqa: F401 – Fixtures

ALT = (
    "profil: Muster-Warenwirtschaft\nversion: 1\ndatei: {muster: 'alt-*.csv'}\n"
    "felder:\n  kopf:\n    BT-1: {spalte: Nr}\n  position:\n    gesamt_kontrolle: {spalte: Summe}\n"
)


@pytest.mark.parametrize(
    "text,erwartet",
    [
        ("profil: P\nversion: 1\nfelder: {kopf: {BT-1: {spalte: Nr}}}\n", "Profilformat 1"),
        ("profil: P\nfelder: {kopf: {BT-1: {spalte: Nr}}}\n", "ohne Profilformat"),
        ("profil: P\nversion: 2\nfelder: {position: {gesamt_kontrolle: {spalte: S}}}\n", "gesamt_kontrolle"),
        ("profil: P\nversion: 2\nfelder: {kopf: {kaeufer_name_2: {spalte: N2}}}\n", "kaeufer_name_2"),
        ("profil: P\nversion: 2\nfelder: {kopf: {kaeufer_name_3: {spalte: N3}}}\n", "kaeufer_name_3"),
    ],
)
def test_meldung_in_du_form_mit_name_und_format(text, erwartet):
    with pytest.raises(ProfilVeraltet) as exc:
        pruefen(yaml.safe_load(text))
    m = exc.value.meldung()
    assert "„P“" in m and erwartet in m
    assert "Was du tun kannst" in m and "Warenwirtschaft (ERP)" in m and "0.9.11" in m
    assert "unverändert" in m
    assert "Profilformat 2" in m
    assert " Sie " not in m and " Ihre " not in m


def test_dialog_knoepfe(qapp):
    from fakturafalter.gui import profilablehnung

    box, assistent = profilablehnung.baue(None, "Text")
    namen = [b.text() for b in box.buttons()]
    assert namen == ["Assistent öffnen", "Schließen"] or sorted(namen) == sorted(
        ["Assistent öffnen", "Schließen"]
    )
    assert box.defaultButton() is assistent
    assert box.windowTitle() == "Dieses Profil passt nicht mehr zu Fakturafalter 1.0"
    box.deleteLater()


def test_profil_uebernehmen_lehnt_altes_ab_und_kopiert_nicht(fenster, qapp, tmp_path):
    from fakturafalter.gui.einstellungen import Einstellungen

    quelle = tmp_path / "import" / "profil-alt.yaml"
    quelle.parent.mkdir()
    quelle.write_text(ALT, encoding="utf-8")
    davor = quelle.read_bytes()
    d = Einstellungen(fenster)
    vorher = list(d._csv_eintraege())
    assert d._csv_uebernehmen_datei(quelle) is False
    assert not (fenster.k.basis / "profil-alt.yaml").exists()
    assert list(d._csv_eintraege()) == vorher
    assert quelle.read_bytes() == davor
    # Format 2 wird übernommen
    neu = tmp_path / "import" / "profil-neu.yaml"
    neu.write_text(ALT.replace("version: 1", "version: 2").replace("gesamt_kontrolle", "gesamtpreis_position"), encoding="utf-8")
    assert d._csv_uebernehmen_datei(neu) is True
    assert (fenster.k.basis / "profil-neu.yaml").exists()
    d.close()


def test_einstellungen_markieren_altes_profil_und_probe(fenster, qapp, monkeypatch, tmp_path):
    from fakturafalter.gui import einstellungen as einst_mod
    from fakturafalter.gui.einstellungen import Einstellungen

    alt = fenster.k.basis / "profil-alt.yaml"
    alt.write_text(ALT, encoding="utf-8")
    d = Einstellungen(fenster)
    ein = list(d._csv_eintraege()) + [{"datei": "profil-alt.yaml", "aktiv": True}]
    d.roh["csv_profile"] = ein
    profs = d._csv_profile_laden()
    p = next(x for x in profs if (x.get("profil") == "Muster-Warenwirtschaft"))
    assert p.get("_abgelehnt") and "Altes Profilformat" in p["_fehler"]
    assert "Profilformat 2" in p["_abgelehnt"][1]
    # Probe zeigt „abgelehnt“
    csv = tmp_path / "alt-1.csv"
    csv.write_text("Nr;Summe\n1;2\n", encoding="utf-8")
    monkeypatch.setattr(einst_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(csv), ""))
    gezeigt = {}

    def _exec(self):
        from PySide6.QtWidgets import QTextEdit

        gezeigt["text"] = self.findChild(QTextEdit).toPlainText()
        return 0

    monkeypatch.setattr(einst_mod.QDialog, "exec", _exec)
    d._csv_testen()
    assert "Muster-Warenwirtschaft: abgelehnt" in gezeigt["text"]
    assert alt.read_text(encoding="utf-8") == ALT
    d.close()


def test_eingang_nennt_abgelehntes_profil(tmp_path):
    import shutil

    from fakturafalter.konfig import lade_konfig
    from fakturafalter.pipeline import verarbeiten

    cfg = tmp_path / "cfg"
    shutil.copytree(BEISPIELE, cfg)
    d = yaml.safe_load((cfg / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["ordner"] = {n: str(tmp_path / n) for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen")}
    (cfg / "profil-alt.yaml").write_text(ALT, encoding="utf-8")
    d["csv_profile"] = ["profil-alt.yaml"]
    d.setdefault("optionen", {})["csv_standard"] = False
    (cfg / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    k = lade_konfig(cfg / "konfiguration.yaml")
    assert k.abgelehnte_profile
    k.eingang.mkdir(parents=True, exist_ok=True)
    f = k.eingang / "alt-1.csv"
    f.write_text("Nr;Summe\n1;2\n", encoding="utf-8")
    lauf = verarbeiten([f], k)
    text = " ".join(str(x) for x in (lauf.datei_fehler or {}).values())
    text += " ".join(str(h) for e in (lauf.ergebnisse or []) for h in e.hinweise)
    assert "profil-alt.yaml" in text and "Profilformat 2" in text, text
    assert (cfg / "profil-alt.yaml").read_text(encoding="utf-8") == ALT
