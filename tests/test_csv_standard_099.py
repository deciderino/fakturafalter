# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Eingebautes CSV-Standardprofil und Vorlagen (fiktive Daten, ab 0.9.9)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fakturafalter import adapter_csv, csv_standard, rechnen
from fakturafalter.pdferkennung import einheit_code

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"
D = Decimal


def test_einheiten_stueck_ist_h87():
    assert csv_standard.EINHEITEN["Stück"] == "H87"
    assert csv_standard.EINHEITEN["Stk"] == "H87"
    assert einheit_code("Stück") == "H87"


def test_standardprofil_wird_angehaengt_ohne_ueberschreiben(konfig):
    ids = [p.get("profil") for p in konfig.csv_profile]
    assert ids[-1] == csv_standard.PROFIL_ID
    assert ids.count(csv_standard.PROFIL_ID) == 1
    # zweites Anhängen ändert nichts
    csv_standard.anhaengen(konfig.csv_profile, konfig.roh)
    assert [p.get("profil") for p in konfig.csv_profile].count(csv_standard.PROFIL_ID) == 1


def test_erkennung_an_neun_pflichtnamen(tmp_path, konfig):
    mini = tmp_path / "x.csv"
    mini.write_bytes(csv_standard.vorlage_minimal())
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    assert adapter_csv.profil_passt(mini, std)
    # abweichender Name -> kein Treffer
    text = mini.read_text(encoding="utf-8-sig").replace("Rechnungsnummer", "Renr", 1)
    falsch = tmp_path / "y.csv"
    falsch.write_text(text, encoding="utf-8-sig")
    assert not adapter_csv.profil_passt(falsch, std)


def test_minimalvorlage_zwei_rechnungen(konfig, tmp_path):
    f = tmp_path / "m.csv"
    f.write_bytes(csv_standard.vorlage_minimal())
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    rs = adapter_csv.lesen(f, std, konfig)
    assert [r.nummer for r in rs] == ["RE-2026-1001", "RE-2026-1002"]
    for r in rs:
        rechnen.berechnen(r)
    a, b = rs
    assert a.positionen[0].einheit == "H87"
    assert a.positionen[1].einheit == "HUR"
    assert a.summen.netto == D("363.00")
    # Kommentarzeile ohne Menge/Preis
    assert any(
        "Lieferung frei Haus" in (p.bezeichnung or "")
        or "Lieferung frei Haus" in " ".join(p.kommentar_unten)
        or any("Lieferung frei Haus" in (t or "") for t, _c in a.bemerkungen)
        or "Lieferung frei Haus" in (a.positionen[0].beschreibung or "")
        for p in a.positionen
    )


def test_vollvorlage_skonto_zwei_stufen(konfig, tmp_path):
    f = tmp_path / "v.csv"
    f.write_bytes(csv_standard.vorlage_voll())
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    (r, r2) = adapter_csv.lesen(f, std, konfig)
    rechnen.berechnen(r)
    assert [(s.tage, s.satz) for s in r.zahlung.skonto] == [(10, D("2")), (20, D("1"))]
    assert r.zahlung.ziel_tage == 30
    assert "#SKONTO#" not in (r.zahlung.bedingungen or "")


def test_unbekannte_spalte_info_kein_prueffall(konfig, tmp_path):
    kopf = ";".join(csv_standard.PFLICHTNAMEN + ("RabattIntern",))
    zeile = "RE-2026-1003;04.11.2026;04.11.2026;K-1001;Test;1;Stück;10,00;19 %;geheim"
    f = tmp_path / "u.csv"
    f.write_text(kopf + "\n" + zeile + "\n", encoding="utf-8-sig")
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    (r,) = adapter_csv.lesen(f, std, konfig)
    rechnen.berechnen(r)
    texte = [h.text for h in r.hinweise if h.stufe == "info"]
    assert any("RabattIntern" in t and "nicht gelesen" in t for t in texte)
    assert not any("RabattIntern" in h.text and h.stufe == "pruefen" for h in r.hinweise)


def test_widerspruch_kopffeld_zu_pruefen(konfig, tmp_path):
    kopf = ";".join(csv_standard.PFLICHTNAMEN)
    z1 = "RE-2026-1004;04.11.2026;04.11.2026;K-1001;A;1;Stück;10,00;19 %"
    z2 = "RE-2026-1004;05.11.2026;04.11.2026;K-1001;B;1;Stück;10,00;19 %"
    f = tmp_path / "w.csv"
    f.write_text(kopf + "\n" + z1 + "\n" + z2 + "\n", encoding="utf-8-sig")
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    (r,) = adapter_csv.lesen(f, std, konfig)
    assert any(
        h.stufe == "pruefen" and "Rechnungsdatum" in h.text and "weicht" in h.text
        for h in r.hinweise
    )


def test_unbekannte_einheit_zu_pruefen(konfig, tmp_path):
    kopf = ";".join(csv_standard.PFLICHTNAMEN)
    z = "RE-2026-1005;04.11.2026;04.11.2026;K-1001;A;1;Fässchen;10,00;19 %"
    f = tmp_path / "e.csv"
    f.write_text(kopf + "\n" + z + "\n", encoding="utf-8-sig")
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    (r,) = adapter_csv.lesen(f, std, konfig)
    assert any(h.stufe == "pruefen" and "Fässchen" in h.text for h in r.hinweise)


def test_tausenderpunkt_wird_gelesen(konfig, tmp_path):
    kopf = ";".join(csv_standard.PFLICHTNAMEN)
    z = "RE-2026-1006;04.11.2026;04.11.2026;K-1001;A;1;Stück;1.234,50;19 %"
    f = tmp_path / "t.csv"
    f.write_text(kopf + "\n" + z + "\n", encoding="utf-8-sig")
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    (r,) = adapter_csv.lesen(f, std, konfig)
    rechnen.berechnen(r)
    assert r.positionen[0].einzelpreis == D("1234.50")


def test_beispiel_dateien_im_repo():
    assert (
        (BEISPIELE / "fakturafalter-standard-minimal.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    )
    assert (BEISPIELE / "fakturafalter-standard-voll.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (BEISPIELE / "profil-fakturafalter-standard.yaml").is_file()


def test_eigene_profile_behalten_vorrang(konfig, tmp_path):
    """Ein früheres eigenes Profil gewinnt, auch wenn die 9 Pflichtnamen passen."""
    std = next(p for p in konfig.csv_profile if csv_standard.ist_standard(p))
    f = tmp_path / "p.csv"
    f.write_bytes(csv_standard.vorlage_minimal())
    # vorhandene Profile in beispiele greifen typischerweise nicht (andere Spaltennamen);
    # ein eigens vorangestelltes Profil mit denselben Namen gewinnt.
    eigen = csv_standard.profil()
    eigen["profil"] = "eigen-test"
    eigen["_eingebaut"] = False
    eigen["felder"]["kopf"]["BT-22"] = {"spalte": "Rechnungsnummer", "optional": True}
    konfig.csv_profile = (
        [eigen] + [p for p in konfig.csv_profile if not csv_standard.ist_standard(p)] + [std]
    )

    # Datei liegt nicht im Eingang; wir prüfen nur profil_passt-Reihenfolge analog zur Pipeline
    treffer = next(
        p
        for p in konfig.csv_profile
        if adapter_csv.profil_aktiv(p) and adapter_csv.profil_passt(f, p)
    )
    assert treffer.get("profil") == "eigen-test"
