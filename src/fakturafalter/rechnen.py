# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Summen und Umsatzsteuer nach EN 16931 rechnen, Kontrollwerte vergleichen."""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from . import sicht
from .modell import Rechnung, Steuer, SteuerZeile, Summen, ZuAbschlag

# Die Geld-Toleranzen der Erkennung und Rechnung – nur hier festlegen:
CENT = Decimal("0.01")                  # Rundung auf ganze Cent
TOLERANZ = Decimal("0.01")              # ein Betrag gegen sein Soll (Rundung je Position/Kontrollwert)
SUMMEN_TOLERANZ = 2 * TOLERANZ          # eine Summe aus vielen Positionen gegen den gedruckten Wert
log = logging.getLogger(__name__)


def runden(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def positionsbetrag(menge: Decimal | None, preis: Decimal | None, preiseinheit: Decimal | None) -> Decimal:
    """BT-131 = BT-129 × BT-146 ÷ BT-149 (gerundet). Fehlende Menge/Preis zählen als 0, Preiseinheit ≤ 0 als 1 –
    dieselbe Rechnung für Vorschau und Speichern."""
    basis = preiseinheit if preiseinheit and preiseinheit > 0 else Decimal("1")
    return runden((menge or Decimal("0")) * (preis or Decimal("0")) / basis)


def betrag_passt(berechnet: Decimal, quelle: Decimal | None) -> bool:
    return quelle is None or abs(quelle - berechnet) <= TOLERANZ


def _za_rechnen(za: ZuAbschlag, basis_standard: Decimal) -> Decimal:
    """Betrag eines Zu-/Abschlags (BT-92/99, BT-136/141): angegeben oder Basis × Prozent ÷ 100 (EN 16931
    lässt beides zu; die Basis fehlt oft und ist dann der Zeilen- bzw. Gruppenbetrag)."""
    za.ist_basis = za.basis
    if za.betrag is not None:
        za.ist_betrag = runden(za.betrag)
    elif za.prozent is not None:
        za.ist_basis = za.basis if za.basis is not None else runden(basis_standard)
        za.ist_betrag = runden(za.ist_basis * za.prozent / Decimal(100))
    else:
        za.ist_betrag = Decimal("0")
    return za.ist_betrag * za.vorzeichen


def _preis_ergaenzen(r: Rechnung, p) -> None:
    """BT-146 = BT-148 − BT-147 (EN 16931, Preisnachlass): fehlende Seite ergänzen, Widerspruch melden."""
    if p.bruttopreis is None:
        return
    rabatt = p.preisrabatt or Decimal("0")
    if p.einzelpreis is None:
        p.einzelpreis = p.bruttopreis - rabatt
    elif p.preisrabatt is None:
        if p.bruttopreis >= p.einzelpreis:
            p.preisrabatt = p.bruttopreis - p.einzelpreis
    elif abs(p.bruttopreis - rabatt - p.einzelpreis) > Decimal("0.0001"):
        r.hinweis("pruefen", f"Brutto-Einzelpreis {p.bruttopreis} − Preisnachlass {rabatt} ≠ Einzelpreis "
                  f"{p.einzelpreis}", f"Pos {p.nr} BT-146")


def _text_abgleichen(r: Rechnung, erste: Steuer, st: Steuer) -> None:
    """Eine Gruppe je Kategorie: weicht der Befreiungstext einer weiteren Position ab, gilt der erste (Hinweis)."""
    if erste is st or erste.kategorie not in EINE_GRUPPE:
        return
    a, b = (erste.befreiungsgrund or "").strip(), (st.befreiungsgrund or "").strip()
    if a and b and a != b and not any(h.feld == "BT-120" and b in h.text for h in r.hinweise):
        r.hinweis("warnung", f"Kategorie {st.kategorie}: abweichender Befreiungsgrund „{b}“ – in der "
                  f"Steueraufschlüsselung gilt „{a}“ (eine Gruppe je Kategorie, EN 16931)", "BT-120")


def _steuerwaehrung(r: Rechnung, s: Summen) -> None:
    """Fremdwährung: USt zusätzlich in EUR (BT-6/BT-111, Art. 230 MwStSystRL, Umrechnung § 16 Abs. 6 UStG).
    Kurs „1 EUR = x BT-5“ und/oder BT-111 kommen aus den Daten; ohne beides hält die Pflichtprüfung an."""
    r.steuerwaehrung = ""
    s.ust_steuerwaehrung = None
    if (r.waehrung or "EUR").strip().upper() == "EUR" or s.ust == 0:
        return
    berechnet = runden(s.ust / r.kurs) if r.kurs and r.kurs > 0 else None
    quelle = r.ust_eur_quelle
    if berechnet is None and quelle is None:
        return
    r.steuerwaehrung = "EUR"
    if quelle is not None and berechnet is not None:
        tol = TOLERANZ * max(1, len(s.steuerzeilen))
        if abs(abs(quelle) - berechnet) > tol:
            r.hinweis("pruefen", f"USt in EUR laut Quelle {quelle} ≠ USt {s.ust} {r.waehrung} ÷ Kurs {r.kurs} = "
                      f"{berechnet} EUR", "BT-111")
        s.ust_steuerwaehrung = runden(abs(quelle))
    else:
        s.ust_steuerwaehrung = berechnet if berechnet is not None else runden(abs(quelle))


def _beleg_steuer_zuordnen(r: Rechnung, gruppen: "OrderedDict[tuple, list]") -> None:
    """Belegebene ohne Steuersatz: bei nur einem Satz diesen nehmen; Prozent-Nachlässe bei mehreren Sätzen je
    Satz aufteilen (Basis = Gruppenbetrag); feste Beträge bei mehreren Sätzen nicht still verteilen."""
    neu: list[ZuAbschlag] = []
    for za in r.zu_abschlaege:
        if za.steuer is not None:
            neu.append(za)
        elif len(gruppen) <= 1:
            za.steuer = next(iter(gruppen.values()))[0] if gruppen else Steuer()
            neu.append(za)
        elif za.betrag is None and za.prozent is not None and za.basis is None:
            neu.extend(replace(za, steuer=st) for st, _ in gruppen.values())
        else:
            st = max(gruppen.values(), key=lambda g: g[1])[0]
            za.steuer = st
            neu.append(za)
            was = "Zuschlag" if za.zuschlag else "Nachlass"
            r.hinweis("pruefen", f"{was} „{za.grund or za.grund_code}“ ohne Steuersatz bei mehreren Steuersätzen – "
                      f"vorläufig {st.kategorie} {st.satz:g} % zugeordnet", "BT-95" if not za.zuschlag else "BT-102")
    r.zu_abschlaege = neu


# Kategorien, die in BG-23 genau eine Gruppe bilden (BR-AE-01, BR-IC-01, BR-G-01, BR-O-01, BR-E-01): gruppiert
# wird nur nach der Kategorie, nicht nach dem Befreiungstext.
EINE_GRUPPE = ("AE", "K", "G", "O", "E")


def gruppe(st: Steuer) -> tuple:
    return (st.kategorie,) if st.kategorie in EINE_GRUPPE else (st.kategorie, st.satz)


def berechnen(r: Rechnung) -> Summen:
    gruppen: "OrderedDict[tuple, list]" = OrderedDict()
    for p in r.positionen:
        _preis_ergaenzen(r, p)
        # fehlende Menge/Preis (None) zählen hier als 0 – die Pflichtprüfung hält die Rechnung ohnehin an
        grund = positionsbetrag(p.menge, p.einzelpreis, p.preiseinheit)      # BT-129 x BT-146 / BT-149
        p.netto = grund + sum((_za_rechnen(za, grund) for za in p.zu_abschlaege), Decimal("0"))  # BT-131
        if not betrag_passt(p.netto, p.kontrolle_gesamt):
            log.info("Pos %s: Menge %s × Preis %s ÷ Preiseinheit %s ± Zu-/Abschläge = berechnet %s, Quelle %s "
                     "(Toleranz %s)", p.nr, p.menge, p.einzelpreis, p.preiseinheit, p.netto, p.kontrolle_gesamt,
                     TOLERANZ)
            r.hinweis("pruefen", f"Positionsbetrag {p.netto} weicht von Quelle {p.kontrolle_gesamt} ab",
                      f"Pos {p.nr} BT-131")
        g = gruppen.setdefault(gruppe(p.steuer), [p.steuer, Decimal("0")])
        _text_abgleichen(r, g[0], p.steuer)
        g[1] += p.netto
    s = Summen()
    s.positionen_netto = sum((p.netto for p in r.positionen), Decimal("0"))   # BT-106
    _beleg_steuer_zuordnen(r, gruppen)
    for za in r.zu_abschlaege:                                                 # BG-20/BG-21
        g = gruppen.setdefault(gruppe(za.steuer), [za.steuer, Decimal("0")])
        wert = _za_rechnen(za, g[1])
        g[1] += wert
        if za.zuschlag:
            s.zuschlaege += za.ist_betrag                                      # BT-108
        else:
            s.abschlaege += za.ist_betrag                                      # BT-107
    s.netto = s.positionen_netto - s.abschlaege + s.zuschlaege                 # BT-109
    for st, basis in gruppen.values():
        betrag = runden(basis * st.satz / Decimal(100))                       # BT-117 je Kategorie/Satz
        s.steuerzeilen.append(SteuerZeile(st, runden(basis), betrag))
    s.ust = sum((z.betrag for z in s.steuerzeilen), Decimal("0"))             # BT-110
    _steuerwaehrung(r, s)                                                      # BT-6 / BT-111
    s.brutto = s.netto + s.ust                                                 # BT-112
    s.vorausbezahlt = runden(r.vorausbezahlt or Decimal("0"))                  # BT-113
    s.rundung = runden(r.rundung or Decimal("0"))                              # BT-114
    s.zahlbar = s.brutto - s.vorausbezahlt + s.rundung                         # BT-115
    r.summen = s

    for feld, soll in (("BT-106", s.positionen_netto), ("BT-107", s.abschlaege), ("BT-108", s.zuschlaege),
                       ("BT-109", s.netto), ("BT-110", s.ust), ("BT-112", s.brutto), ("BT-115", s.zahlbar)):
        if feld in r.kontrolle:
            ist = Decimal(str(r.kontrolle[feld]))
            if abs(ist - soll) > TOLERANZ:
                r.hinweis("pruefen", f"Kontrollwert der Quelle {ist} ≠ berechnet {soll}", feld)
            else:
                r.hinweis("info", f"Kontrollwert {ist} stimmt", feld)
    for z in s.steuerzeilen:
        if z.steuer.kategorie in ("E", "AE", "K", "G", "O") and not (z.steuer.befreiungsgrund or z.steuer.befreiungscode):
            r.hinweis("pruefen", f"Steuerkategorie {z.steuer.kategorie} braucht Befreiungsgrund (BT-120/121)", "BG-23")
    if len(r.bezuege) > 1:
        r.hinweis("warnung", f"{len(r.bezuege)} Bezüge auf frühere Rechnungen – CII (EN 16931) nimmt nur einen auf, "
                  f"übernommen: {r.bezuege[0].nummer}", "BG-3")
    if s.brutto < 0 and r.art == "380":
        r.hinweis("pruefen", "negativer Rechnungsbetrag – Gutschrift/Korrektur (381/384)?", "BT-3")
    sicht.gutschrift_zahlung_setzen(r)
    return s
