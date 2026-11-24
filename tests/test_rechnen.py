# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
from datetime import date
from decimal import Decimal as D

from fakturafalter.modell import Anschrift, Partei, Position, Rechnung, Steuer
from fakturafalter.rechnen import berechnen, runden


def _r(*pos, kontrolle=None):
    r = Rechnung(nummer="T-1", datum=date(2026, 10, 1), verkaeufer=Partei("V", Anschrift("s", "1", "o")),
                 kaeufer=Partei("K", Anschrift("s", "1", "o")))
    for i, (m, p, satz) in enumerate(pos, 1):
        kat = "S" if satz else "E"
        r.positionen.append(Position(nr=str(i), bezeichnung="x", menge=D(m), einheit="C62", einzelpreis=D(p),
                                     steuer=Steuer(kat, D(satz), "befreit" if not satz else "")))
    if kontrolle:
        r.kontrolle.update(kontrolle)
    return r


def test_runden_kaufmaennisch():
    assert runden(D("0.005")) == D("0.01")
    assert runden(D("2.345")) == D("2.35")
    assert runden(D("-2.345")) == D("-2.35")


def test_beispiel_0101_mischsteuersatz():
    r = _r(("500", "0.12", "19"), ("3.5", "65.00", "19"), ("1", "39.90", "7"))
    s = berechnen(r)
    assert [p.netto for p in r.positionen] == [D("60.00"), D("227.50"), D("39.90")]
    assert s.netto == D("327.40")
    assert {z.steuer.satz: z.betrag for z in s.steuerzeilen} == {D("19"): D("54.63"), D("7"): D("2.79")}
    assert s.ust == D("57.42")
    assert s.brutto == D("384.82") == s.zahlbar


def test_steuer_je_satz_nicht_je_position():
    # 3 x 0,33 € mit 19 %: je Position gerundet wäre 3 x 0,06 = 0,18; richtig: 0,99 * 19 % = 0,19
    r = _r(("1", "0.33", "19"), ("1", "0.33", "19"), ("1", "0.33", "19"))
    assert berechnen(r).ust == D("0.19")


def test_kontrollwert_abweichung_fuehrt_zu_pruefen():
    r = _r(("1", "10", "19"), kontrolle={"BT-112": D("11.99")})
    berechnen(r)
    assert r.status == "pruefen"


def test_kontrollwert_ok():
    r = _r(("1", "10", "19"), kontrolle={"BT-112": D("11.90")})
    berechnen(r)
    assert r.status == "ok"


def test_steuerbefreit_mit_grund():
    r = _r(("2", "50", "0"))
    s = berechnen(r)
    assert s.ust == D("0.00") and s.brutto == D("100.00")
    assert r.status == "ok"


def test_preiseinheit_pro_100_stueck():
    # 500 Stk zu 4,80 € pro 100 Stk = 24,00 €; daneben eine Position pro 1 Stk
    r = _r(("500", "4.80", "19"), ("3", "2.50", "19"))
    r.positionen[0].preiseinheit = D("100")
    s = berechnen(r)
    assert [p.netto for p in r.positionen] == [D("24.00"), D("7.50")]
    assert s.netto == D("31.50") and s.brutto == D("37.49")


def test_preiseinheit_im_cii():
    from fakturafalter import cii
    r = _r(("500", "4.80", "19"), ("3", "2.50", "19"))
    r.positionen[0].preiseinheit = D("100")
    r.positionen[0].einheit = "H87"
    berechnen(r)
    xml = cii.erzeugen(r, "EN16931").decode("utf-8")
    assert xml.count("<ram:BasisQuantity") == 1
    assert '<ram:BasisQuantity unitCode="H87">100</ram:BasisQuantity>' in xml
    assert "<ram:LineTotalAmount>24.00</ram:LineTotalAmount>" in xml


def test_positionsbetrag_toleranz_ein_cent():
    from decimal import Decimal as D
    from fakturafalter import rechnen
    assert rechnen.positionsbetrag(D("10"), D("0.34"), D("1000")) == D("0.00")
    assert rechnen.positionsbetrag(D("1000"), D("0.0034"), D("1")) == D("3.40")
    assert rechnen.positionsbetrag(D("100"), D("3.40"), D("100")) == D("3.40")
    assert rechnen.positionsbetrag(None, D("3.40"), None) == D("0.00")
    assert rechnen.betrag_passt(D("3.40"), D("3.41")) and rechnen.betrag_passt(D("3.40"), D("3.39"))
    assert not rechnen.betrag_passt(D("3.40"), D("3.42")) and rechnen.betrag_passt(D("1"), None)
