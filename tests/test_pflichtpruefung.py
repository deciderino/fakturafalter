# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Pflichtangaben/Plausibilität (pflichtpruefung.py): je Regel ein Positiv- und ein Negativfall,
dazu Einbindung in Pipeline, Prüfansicht und Freigabe. Alle Daten erfunden."""
import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from fakturafalter import pflichtpruefung as pp
from fakturafalter import rechnen
from fakturafalter.aufbau import rechnung_bauen
from fakturafalter.cii import erzeugen as cii_erzeugen
from fakturafalter.modell import (
    Anschrift,
    Herkunft,
    Lieferung,
    Partei,
    Position,
    Rechnung,
    Rechnungsbezug,
    Steuer,
    Zahlung,
)
from fakturafalter.pipeline import prueffall_freigeben, verarbeiten

HEUTE = date(2026, 11, 1)
CTX = pp.Kontext(heute=HEUTE)
H = Herkunft("test", 1.0)
BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"


def gueltig(**aendern) -> Rechnung:
    """Vollständige Inlandsrechnung (erfunden), die alle Regeln besteht."""
    r = Rechnung(
        nummer="T-1", datum=date(2026, 10, 28), leistungsdatum=date(2026, 10, 23),
        verkaeufer=Partei("Muster GmbH", Anschrift("Musterstraße 1", "12345", "Musterstadt"), ust_id="DE123456788",
                          kontakt_email="info@muster.example", register="Amtsgericht Musterstadt HRB 00000"),
        kaeufer=Partei("Beispiel AG", Anschrift("Beispielweg 2", "54321", "Beispielstadt")),
        zahlung=Zahlung(iban="DE36000000000000000000", bedingungen="Zahlbar innerhalb 14 Tagen ohne Abzug.",
                        faellig=date(2026, 11, 11)),
        positionen=[Position("1", bezeichnung="Beratung", menge=D("2"), einheit="HUR", einzelpreis=D("50"))])
    for k, v in aendern.items():
        setattr(r, k, v)
    rechnen.berechnen(r)
    return r


def felder(r: Rechnung, ctx=CTX) -> dict[str, str]:
    return dict(pp.pruefen(r, ctx))


def test_gueltige_rechnung_ohne_treffer():
    r = gueltig()
    assert felder(r) == {} and r.status == "ok"


# ------------------------------------------------------------------ Hilfsfunktionen
@pytest.mark.parametrize("u,ok", [("DE123456788", True), ("DE000000003", True), ("de 123 456 788", True),
                                  ("DE000000000", False), ("DE123456789", False), ("DE12345678", False), ("", False)])
def test_ust_id_pruefziffer(u, ok):
    assert pp.ust_id_de_gueltig(u) is ok


@pytest.mark.parametrize("i,ok", [("DE36000000000000000000", True), ("DE89 3704 0044 0532 0130 00", True),
                                  ("DE37000000000000000000", False), ("DE3600000000000000000", False), ("", False)])
def test_iban_mod97(i, ok):
    assert pp.iban_gueltig(i) is ok


# ------------------------------------------------------------------ Parteien
@pytest.mark.parametrize("wer,attr,bt", [
    ("verkaeufer", "name", "BT-27"), ("verkaeufer", "strasse", "BT-35"), ("verkaeufer", "plz", "BT-38"),
    ("verkaeufer", "ort", "BT-37"), ("kaeufer", "name", "BT-44"), ("kaeufer", "strasse", "BT-50"),
    ("kaeufer", "plz", "BT-53"), ("kaeufer", "ort", "BT-52")])
def test_name_und_anschrift_pflicht(wer, attr, bt):
    r = gueltig()
    p = getattr(r, wer)
    setattr(p if attr == "name" else p.anschrift, attr, "")
    f = felder(r)
    assert bt in f and "fehlt" in f[bt] and "§ 14 Abs. 4 Nr. 1 UStG" in f[bt]
    assert r.status == "pruefen"


def test_ausland_nicht_unterstuetzt():
    r = gueltig()
    r.kaeufer.anschrift.land = "AT"
    f = felder(r)
    assert "nicht unterstützt" in f["BT-55"]
    r = gueltig()
    r.kaeufer.anschrift.land = "DE"
    assert "BT-55" not in felder(r)


def test_plz_fuenfstellig():
    r = gueltig()
    r.kaeufer.anschrift.plz = "1234"
    assert "5 Ziffern" in felder(r)["BT-53"]


# ------------------------------------------------------------------ Steuer-ID Verkäufer
def test_verkaeufer_ohne_steuer_id():
    r = gueltig()
    r.verkaeufer.ust_id = ""
    assert "§ 14 Abs. 4 Nr. 2 UStG" in felder(r)["BT-31"]


def test_verkaeufer_ust_id_pruefziffer_falsch():
    r = gueltig()
    r.verkaeufer.ust_id = "DE000000000"
    assert "ungültig" in felder(r)["BT-31"]


def test_verkaeufer_nur_steuernummer_mit_register_ok():
    r = gueltig()
    r.verkaeufer.ust_id, r.verkaeufer.steuernummer = "", "12/345/67890"
    assert felder(r) == {}


def test_verkaeufer_nur_steuernummer_ohne_register_br_co_26():
    r = gueltig()
    r.verkaeufer.ust_id, r.verkaeufer.steuernummer, r.verkaeufer.register = "", "12/345/67890", ""
    assert "BR-CO-26" in felder(r)["BT-30"]


def test_steuernummer_format():
    r = gueltig()
    r.verkaeufer.steuernummer = "123"
    assert "BT-32" in felder(r)


# ------------------------------------------------------------------ Positionen
@pytest.mark.parametrize("attr,wert,bt,text", [
    ("menge", None, "BT-129", "fehlt"), ("menge", D("0"), "BT-129", "ist 0"),
    ("einzelpreis", None, "BT-146", "fehlt"), ("einzelpreis", D("-1"), "BT-146", "BR-27"),
    ("einheit", "", "BT-130", "fehlt"), ("einheit", "Stk", "BT-130", "Rec 20"),
    ("bezeichnung", "", "BT-153", "fehlt")])
def test_position_pflichtwerte(attr, wert, bt, text):
    r = gueltig()
    setattr(r.positionen[0], attr, wert)
    rechnen.berechnen(r)
    f = felder(r)
    assert text in f[f"Pos 1 {bt}"]


def test_position_einzelpreis_null_ist_erlaubt():
    r = gueltig()
    r.positionen.append(Position("2", bezeichnung="Kulanz", menge=D("1"), einheit="C62", einzelpreis=D("0")))
    rechnen.berechnen(r)
    assert felder(r) == {}


def test_keine_positionen():
    r = gueltig(positionen=[])
    assert "BG-25" in felder(r)


def test_aufbau_keine_stille_null_und_kein_stilles_c62(tmp_path, konfig):
    kopf = {"BT-1": ("X-1", H), "BT-2": (date(2026, 10, 28), H), "BT-72": (date(2026, 10, 23), H),
            "kundennummer": ("K-1001", H)}
    pos = [{"BT-126": ("1", H), "BT-153": ("Test", H), "steuer": ("1", H)}]        # ohne Menge, Preis, Einheit
    r = rechnung_bauen(kopf, pos, {"mappings": {"steuer": {"1": {"BT-151": "S", "BT-152": 19}}}}, konfig, "t.csv")
    p = r.positionen[0]
    assert p.menge is None and p.einzelpreis is None and p.einheit == ""
    rechnen.berechnen(r)
    f = felder(r)
    assert {"Pos 1 BT-129", "Pos 1 BT-130", "Pos 1 BT-146"} <= set(f)


# ------------------------------------------------------------------ Steuer
@pytest.mark.parametrize("kat,satz,grund,ok", [
    ("S", "19", "", True), ("S", "7", "", True), ("S", "16", "", False), ("S", "0", "", False),
    ("Z", "0", "", True), ("Z", "0", "steuerfrei", False), ("Z", "7", "", False),
    ("E", "0", "Steuerfrei nach § 4 Nr. 14 UStG", True), ("E", "0", "", False), ("E", "19", "§ 4 Nr. 14 UStG", False)])
def test_steuer_kategorie_und_satz(kat, satz, grund, ok):
    r = gueltig()
    r.positionen[0].steuer = Steuer(kat, D(satz), grund)
    rechnen.berechnen(r)
    f = felder(r)
    assert ("Pos 1 BT-151" not in f) is ok, f


@pytest.mark.parametrize("st", [Steuer("AE", D("0"), "Steuerschuldnerschaft des Leistungsempfängers"),
                                Steuer("K", D("0"), "Innergemeinschaftliche Lieferung"),
                                Steuer("G", D("0"), "Ausfuhr"), Steuer("O", D("0"), "nicht steuerbar"),
                                Steuer("E", D("0"), "Kein Steuerausweis, Kleinunternehmer gem. § 19 UStG"),
                                Steuer("E", D("0"), "Steuerschuldnerschaft nach § 13b UStG")])
def test_reverse_charge_kleinunternehmer_ausland_nicht_unterstuetzt(st):
    r = gueltig()
    r.positionen[0].steuer = st
    rechnen.berechnen(r)
    assert "nicht unterstützt" in felder(r)["Pos 1 BT-151"]


# ------------------------------------------------------------------ Leistungszeit
def test_leistungsdatum_fehlt_haelt_an():
    r = gueltig(leistungsdatum=None)
    f = felder(r)
    assert "§ 14 Abs. 4 Nr. 6 UStG" in f["BT-72"] and r.status == "pruefen"


def test_leistungszeitraum_statt_datum_ok():
    r = gueltig(leistungsdatum=None, leistung_von=date(2026, 10, 1), leistung_bis=date(2026, 10, 31))
    assert felder(r) == {}


def test_leistungszeitraum_ende_vor_beginn():
    r = gueltig(leistung_von=date(2026, 10, 31), leistung_bis=date(2026, 10, 1))
    assert "BG-14" in felder(r)


@pytest.mark.parametrize("wert", ["10/2026", "2026-10", "10.2026", date(2026, 10, 17)])
def test_leistungsmonat_aus_profil(konfig, wert):
    kopf = {"BT-1": ("X-1", H), "BT-2": (date(2026, 10, 28), H), "leistungsmonat": (wert, H),
            "kundennummer": ("K-1001", H)}
    r = rechnung_bauen(kopf, [], {}, konfig, "t.csv")
    assert (r.leistung_von, r.leistung_bis) == (date(2026, 10, 1), date(2026, 10, 31))


def test_leistungszeitraum_im_xml():
    r = gueltig(leistungsdatum=None, leistung_von=date(2026, 10, 1), leistung_bis=date(2026, 10, 31))
    x = cii_erzeugen(r, "EN16931").decode()
    assert "<ram:BillingSpecifiedPeriod>" in x and "20261001" in x and "20261031" in x
    assert x.index("BillingSpecifiedPeriod") < x.index("SpecifiedTradePaymentTerms")


# ------------------------------------------------------------------ Zahlung
def test_iban_fehlt_oder_ungueltig():
    r = gueltig()
    r.zahlung.iban = ""
    assert "fehlt" in felder(r)["BT-84"]
    r = gueltig()
    r.zahlung.iban = "DE37000000000000000000"
    assert "ungültig" in felder(r)["BT-84"]


def test_ohne_ueberweisung_keine_iban_noetig():
    r = gueltig()
    r.zahlung.art, r.zahlung.iban = "10", ""            # bar
    assert felder(r) == {}


def test_faelligkeit_oder_bedingungen_noetig():
    r = gueltig()
    r.zahlung.faellig, r.zahlung.bedingungen = None, ""
    assert "BR-CO-25" in felder(r)["BT-20"]
    r = gueltig()
    r.zahlung.faellig = None                            # nur Bedingungen reicht
    assert felder(r) == {}


def test_faelligkeit_vor_rechnungsdatum():
    r = gueltig()
    r.zahlung.faellig = date(2026, 10, 1)
    assert "BT-9" in felder(r)


def test_zahlungsziel_platzhalter_ohne_tage_wird_leer(konfig):
    kopf = {"BT-1": ("X-1", H), "BT-2": (date(2026, 10, 28), H), "kundennummer": ("K-1001", H)}
    konfig.zahlung.ziel_tage = None
    r = rechnung_bauen(kopf, [], {}, konfig, "t.csv")
    assert "{" not in r.zahlung.bedingungen and "innerhalb  Tagen" not in r.zahlung.bedingungen


# ------------------------------------------------------------------ Nummer, Datum, Währung, E-Mail
def test_nummer_einmalig_ueber_laeufe():
    ctx = pp.Kontext(heute=HEUTE, bekannte_nummern=frozenset({"T-1"}))
    assert "schon einmal erzeugt" in felder(gueltig(), ctx)["BT-1"]
    assert felder(gueltig(nummer="T-2"), ctx) == {}


def test_bekannte_nummern_nur_ok_zeilen(tmp_path):
    p = tmp_path / "protokoll.tsv"
    p.write_text("2026-10-28 10:00:00\tok\tA-1\tA-1_zugferd.pdf\t\t\t\n"
                 "2026-10-28 10:00:00\tpruefen\tA-2\tA-2.json\t\t\t\n", encoding="utf-8")
    assert pp.bekannte_nummern(p) == {"A-1"}
    assert pp.bekannte_nummern(tmp_path / "fehlt.tsv") == frozenset()


def test_rechnungsdatum_in_der_zukunft():
    assert "Zukunft" in felder(gueltig(datum=date(2026, 11, 2)))["BT-2"]
    assert felder(gueltig(datum=HEUTE)) == {}


def test_nummer_und_datum_fehlen():
    f = felder(gueltig(nummer="", datum=None))
    assert "BT-1" in f and "BT-2" in f


@pytest.mark.parametrize("w,bt", [("EURO", "BT-5"), ("USD", "BT-5")])
def test_waehrung(w, bt):
    f = felder(gueltig(waehrung=w))
    assert bt in f
    assert ("ISO-4217" in f[bt]) if w == "EURO" else ("nicht unterstützt" in f[bt])


@pytest.mark.parametrize("attr,bt", [("kontakt_email", "BT-43"), ("elektronische_adresse", "BT-34")])
def test_email_format(attr, bt):
    r = gueltig()
    setattr(r.verkaeufer, attr, "info(at)muster.example")
    assert "E-Mail" in felder(r)[bt]
    r = gueltig()
    r.kaeufer.kontakt_email = "einkauf@beispiel.example"
    assert felder(r) == {}


# ------------------------------------------------------------------ Aufbau des Moduls
def test_regeln_nach_umfang_und_stubs_inaktiv():
    umf = {g.umfang for g in pp.REGELN}
    assert {"alle", "inland", "ausland", "xrechnung"} <= umf
    aktiv = pp.aktive_regeln(CTX)
    assert all(g.umfang in ("alle", "inland") for g in aktiv)
    assert not [g for g in pp.REGELN if g.umfang in ("ausland", "xrechnung") and g.aktiv]


def test_kein_doppelter_hinweis_zum_selben_feld():
    r = gueltig()
    r.positionen[0].bezeichnung = ""
    r.hinweis("pruefen", "Bezeichnung fehlt", "Pos 1 BT-153")       # wie aus aufbau
    pp.pruefen(r, CTX)
    assert [h.feld for h in r.hinweise].count("Pos 1 BT-153") == 1


# ------------------------------------------------------------------ Pipeline / Prüfansicht / Freigabe
def _ohne_leistungsdatum(eingang, konfig):
    (d,) = eingang("variante-a_positionen_utf8.csv")
    t = d.read_text(encoding="utf-8").replace("2026-10-02", "")
    d.write_text(t, encoding="utf-8")
    return d


def test_pipeline_angehaltene_rechnung_nach_pruefen(konfig, eingang):
    from fakturafalter.gui import daten
    d = _ohne_leistungsdatum(eingang, konfig)
    lauf = verarbeiten([d], konfig)
    st = {e.nummer: e.status for e in lauf.ergebnisse}
    assert st["RE-2026-0101"] == "pruefen", st
    j = json.loads((konfig.pruefen / "RE-2026-0101.json").read_text(encoding="utf-8"))
    assert any(h["feld"] == "BT-72" and h["stufe"] == "pruefen" for h in j["hinweise"])
    assert not (konfig.ausgang / "RE-2026-0101_zugferd.pdf").exists()
    prot = (konfig.protokoll / "protokoll.tsv").read_text(encoding="utf-8")
    assert "RE-2026-0101" in prot and "Leistungsdatum (BT-72)" in prot
    fall = next(f for f in daten.prueffaelle(konfig) if f.nummer == "RE-2026-0101")
    assert any("Leistungsdatum (BT-72)" in s for s in fall.sonstige)


def test_pipeline_nummer_aus_frueherem_lauf(konfig, eingang):
    (d,) = eingang("variante-a_positionen_utf8.csv")
    assert verarbeiten([d], konfig).ok
    for p in konfig.ausgang.glob("*.pdf"):          # Ausgabe weg – nur das Protokoll erinnert sich
        p.unlink()
    (d,) = eingang("variante-a_positionen_utf8.csv")
    lauf = verarbeiten([d], konfig)
    assert all(e.status == "pruefen" for e in lauf.ergebnisse)
    assert all(any("schon einmal erzeugt" in h for h in e.hinweise) for e in lauf.ergebnisse)


def test_freigabe_prueft_pflichtangaben_erneut(konfig, eingang):
    d = _ohne_leistungsdatum(eingang, konfig)
    verarbeiten([d], konfig)
    erg = prueffall_freigeben(konfig.pruefen / "RE-2026-0101.json", konfig)
    assert erg.status == "pruefen" and any("BT-72" in h for h in erg.hinweise)
    assert (konfig.pruefen / "RE-2026-0101.json").exists()


def test_beispieldaten_bestehen_alle_regeln(konfig, eingang):
    dateien = eingang("variante-a_positionen_utf8.csv")
    lauf = verarbeiten(dateien, konfig)
    assert lauf.ok, [(e.nummer, e.hinweise) for e in lauf.ergebnisse]


# ------------------------------------------------------------------ Gutschrift / Lieferanschrift (0.9.0)
def test_gutschrift_ohne_rechnungsbezug():
    r = gueltig(art="381")
    f = felder(r)
    assert "BT-25" in f and "Ursprungsrechnung" in f["BT-25"] and "§ 31 Abs. 5 UStDV" in f["BT-25"]
    assert r.status == "pruefen"


def test_rechnungskorrektur_ohne_rechnungsbezug():
    r = gueltig(art="384")
    f = felder(r)
    assert "BT-25" in f and "Rechnungskorrektur (384)" in f["BT-25"]
    assert r.status == "pruefen"


def test_gutschrift_mit_rechnungsbezug_und_positivem_betrag_ok():
    r = gueltig(art="381", bezuege=[Rechnungsbezug("RE-2026-0100", date(2026, 10, 1))])
    f = felder(r)
    assert "BT-25" not in f and "BT-112" not in f
    assert r.status == "ok"


def test_gutschrift_betrag_nicht_positiv():
    r = gueltig(art="381", bezuege=[Rechnungsbezug("RE-2026-0100")])
    r.positionen[0].menge = D("-2")
    rechnen.berechnen(r)
    f = felder(r)
    assert "BT-112" in f and "nicht positiv" in f["BT-112"] and "BR-27" in f["BT-112"]
    assert r.status == "pruefen"


def test_gutschrift_betrag_null():
    r = gueltig(art="381", bezuege=[Rechnungsbezug("RE-2026-0100")])
    r.summen.brutto = D("0")
    f = felder(r)
    assert "BT-112" in f and "nicht positiv" in f["BT-112"]
    assert r.status == "pruefen"


def test_rechnung_380_negativer_betrag_nicht_als_gutschrift_betrag():
    r = gueltig()
    r.positionen[0].menge = D("-2")
    rechnen.berechnen(r)
    f = felder(r)
    assert "BT-112" not in f
    assert any(h.feld == "BT-3" and "negativer Rechnungsbetrag" in h.text for h in r.hinweise)


def test_lieferanschrift_fehlt_wenn_nicht_angegeben():
    r = gueltig()
    f = felder(r)
    assert "BT-80" not in f and "BT-77" not in f and "BT-78" not in f


def test_lieferung_nur_name_ohne_anschrift_kein_treffer():
    r = gueltig()
    r.lieferung = Lieferung(name="Lager Nord")
    f = felder(r)
    assert "BT-80" not in f and "BT-77" not in f and "BT-78" not in f


def test_lieferanschrift_vollstaendig_ok():
    r = gueltig()
    r.lieferung = Lieferung(anschrift=Anschrift("Lagerweg 1", "12345", "Musterstadt", "DE"))
    f = felder(r)
    assert "BT-80" not in f and "BT-77" not in f and "BT-78" not in f
    assert r.status == "ok"


def test_lieferanschrift_unvollstaendig():
    r = gueltig()
    r.lieferung = Lieferung(anschrift=Anschrift(strasse="Lagerweg 1", land=""))
    f = felder(r)
    assert "BT-80" in f and "BT-77" in f and "BT-78" in f
    assert "Land (BT-80)" in f["BT-80"] and "Ort (BT-77)" in f["BT-77"] and "Postleitzahl (BT-78)" in f["BT-78"]
    assert r.status == "pruefen"


def test_lieferanschrift_plz_nicht_fuenfstellig():
    r = gueltig()
    r.lieferung = Lieferung(anschrift=Anschrift("Lagerweg 1", "1234", "Musterstadt", "DE"))
    f = felder(r)
    assert "BT-78" in f and "1234" in f["BT-78"] and "5 Ziffern" in f["BT-78"]
    assert r.status == "pruefen"
