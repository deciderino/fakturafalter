# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Fiktive ERP-Rechnungen im Rohformat eines Warenwirtschaftsdrucks (alle Inhalte erfunden).

So wie manche Warenwirtschaften drucken: Courier 10 pt, je Wort ein ``TJ`` mit führendem Leerzeichen, jede
Leerstelle als eigener ``Tm``-Sprung, Zeilenende als ``\\012`` (pdfminer liest „(cid:10)“), eckige Klammern als
``\\[`` maskiert. Dazu wahlweise eine gezeichnete Linie unter der Kopfzeile, Text-Trennlinien und Falzmarken
links am Rand (Times „--“)."""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

H = 842
KOPF = "       Menge ME     Bezeichnung                       Preis [EURO]     Betrag [EURO]"
KOPF_TOP = 315


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("[", "\\[").replace("]", "\\]")


def _zeile_ops(s: str, top: float, x0: float = 30) -> list[str]:
    y = H - top - 8
    ops = [f"1 0 0 1 {x0} {y} Tm"]
    woerter = [(m.start(), m.group()) for m in re.finditer(r"\S+", s)]
    pos = 0
    for i, (c, w) in enumerate(woerter):
        while pos < c - 1:
            pos += 1
            ops.append(f"1 0 0 1 {x0 + 6 * pos} {y} Tm")
        ende = "\\012" if i == len(woerter) - 1 else ""
        ops.append(f"[ ( {_esc(w)}{ende}) ] TJ")
        pos = c + len(w)
    if not woerter:
        ops.append("[ ( \\012) ] TJ")
    return ops


def pos(menge: str, me: str, bez: str, preis: str, betrag: str, nach_betrag: str = "") -> str:
    """Positionszeile, Zahlen rechtsbündig unter „Menge“, „Preis [EURO]“ und „Betrag [EURO]“."""
    s = (" " * (12 - len(menge)) + menge + " " + me).ljust(20) + bez
    s = s.ljust(65 - len(preis)) + preis
    return s.ljust(82 - len(betrag)) + betrag + nach_betrag


# Variante „Preis mit Preiseinheit“: Menge linksbündig unter „Menge“, hinter dem Preis „/1“, „/100“ …
KOPF_PE = "       Menge ME     Bezeichnung                      Preis [EURO]    Betrag [EURO]"


def pos_pe(menge: str, me: str, bez: str, preis: str, pe: str, betrag: str) -> str:
    """Positionszeile mit Preiseinheit direkt hinter dem Preis (``pe`` z. B. „/1“, „/100“, „“ = keine)."""
    s = ((" " * (9 - len(menge)) + menge).ljust(13) + me).ljust(20) + bez
    s = s.ljust(65 - len(preis)) + preis + (" " + pe if pe else "")
    return s.ljust(82 - len(betrag)) + betrag


def trenn(zeichen: str = "-") -> str:
    return " " + zeichen * 82


STANDARD = [pos("10", "Stk", "4711-0815 Sechskantschraube M8x40", "1,25", "12,50"),
            "                    DIN 933, verzinkt",
            pos("2,000", "Std", "Montage vor Ort", "85,00", "170,00"),
            pos("1", "ST", "Werkzeugwagen Typ B", "1.088,50", "1.088,50")]
SUMME = Decimal("1271.00")


def fuss(netto: str = "1.271,00", wort: str = "Nettobetrag") -> list[str]:
    return [" " * 50 + wort.ljust(20) + netto.rjust(12),
            " " * 50 + "USt 19 %".ljust(20) + "241,49".rjust(12),
            " " * 50 + "Endbetrag".ljust(20) + "1.512,49".rjust(12)]


def rechnung(pfad: Path, zeilen: list[str] = STANDARD, *, kopf: str = KOPF, vektorlinie: bool = False,
             falzmarken: tuple[float, ...] = (), leer_nach_kopf: int = 0, nach: list[str] | None = None,
             beleg: str = "26000042", anschrift: list[str] | None = None, kopf_versatz: float = 0) -> Path:
    """Eine Seite: Briefkopf, Kopfzeile bei top=315, ``leer_nach_kopf`` Leerzeilen, die Zeilen, danach ``nach``
    (Standard: Nettobetrag/USt/Endbetrag). ``vektorlinie``: gezeichnete Linie 12 pt unter der Kopfzeile und
    unter den Positionen. ``falzmarken``: tops für „--“ in Times bei x=10. ``anschrift``: eigene Zeilen des
    Anschriftfelds (die letzte steht bei top=183). ``kopf_versatz``: Datum und Beleg so viele pt tiefer."""
    import pikepdf
    pdf = pikepdf.new()
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Courier,
                              Encoding=pikepdf.Name.WinAnsiEncoding)
    times = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                               BaseFont=pikepdf.Name("/Times-Roman"), Encoding=pikepdf.Name.WinAnsiEncoding)
    adr = ([(183 - 12 * (len(anschrift) - 1 - i), " " + a) for i, a in enumerate(anschrift)] if anschrift else
           [(147, " Beispiel Werkzeugbau GmbH"), (159, " Musterweg 12"), (183, " 12345 Musterstadt")])
    rumpf = adr + [(231 + kopf_versatz, " " * 55 + "Datum: 05.10.2026"),
                   (255 + kopf_versatz, " Rechnung" + " " * 47 + f"Beleg: {beleg}")]
    top = KOPF_TOP
    rumpf.append((top, kopf))
    top += 12 * (1 + leer_nach_kopf)
    for s in zeilen:
        rumpf.append((top, s))
        top += 12
    letzte = top
    top += 12
    for s in (fuss() if nach is None else nach):
        rumpf.append((top, s))
        top += 12
    rumpf.append((top + 24, " Leistungsdatum = Rechnungsdatum, zahlbar bis 04.11.2026 ohne Abzug."))
    ops = ["BT", "/F1 10 Tf"]
    for t, s in rumpf:
        ops += _zeile_ops(s, t)
    ops.append("ET")
    for t in falzmarken:
        ops += ["BT", "/F2 10 Tf", f"1 0 0 1 10 {H - t - 8} Tm", "(--) Tj", "ET"]
    if vektorlinie:
        for t in (KOPF_TOP + 12, letzte + 2):
            ops += ["0.5 w", f"36 {H - t} m 547 {H - t} l S"]
    page = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 595, 842],
                              Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font, F2=times)),
                              Contents=pdf.make_stream("\n".join(ops).encode("cp1252")))
    pdf.pages.append(pikepdf.Page(page))
    pdf.save(str(pfad))
    return pfad


def rechnung_mehrseitig(pfad: Path, seiten: list[list[str]], *, kopf_wiederholen: bool = True,
                        uebertrag: str = "Übertrag", trennlinie: bool = False, briefkopf_folgeseiten: bool = True,
                        nach: list[str] | None = None, beleg: str = "26000042") -> Path:
    """Mehrere Seiten, Positionen je Seite aus ``seiten``. Seite 1 wie ``rechnung`` (Kopfzeile bei top=315); am
    Ende jeder Seite außer der letzten wahlweise eine Trennlinie, die Zeile ``uebertrag`` mit Betrag
    („“ = keine) und „Seite x von n“. Folgeseiten: mit Briefkopf (gleiches Layout, Tabelle bei top=315) oder
    ohne (Tabelle ab top=80, darüber „Übertrag“); Kopfzeile wiederholt oder nicht. Nach den Positionen der
    letzten Seite ``nach`` (Standard: Nettobetrag/USt/Endbetrag)."""
    import pikepdf
    pdf = pikepdf.new()
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Courier,
                              Encoding=pikepdf.Name.WinAnsiEncoding)
    n = len(seiten)
    for si, zeilen in enumerate(seiten):
        rumpf: list[tuple[float, str]] = []
        if si == 0 or briefkopf_folgeseiten:
            rumpf += [(147, " Beispiel Werkzeugbau GmbH"), (159, " Musterweg 12"), (183, " 12345 Musterstadt"),
                      (231, " " * 55 + "Datum: 05.10.2026"), (255, " Rechnung" + " " * 47 + f"Beleg: {beleg}")]
            top = KOPF_TOP
        else:
            rumpf.append((40, " Rechnung " + beleg + " " * 40 + f"Seite {si + 1} von {n}"))
            top = 80
            if uebertrag:
                rumpf.append((top, " " * 50 + uebertrag.ljust(20) + "1.000,00".rjust(12)))
                top += 12
        if si == 0 or kopf_wiederholen:
            rumpf.append((top, KOPF))
            top += 12
        for s in zeilen:
            rumpf.append((top, s))
            top += 12
        if si < n - 1:
            if trennlinie:
                rumpf.append((top, trenn()))
                top += 12
            if uebertrag:
                rumpf.append((top, " " * 50 + uebertrag.ljust(20) + "1.000,00".rjust(12)))
                top += 12
            rumpf.append((top + 12, " " * 60 + f"Seite {si + 1} von {n}"))
        else:
            top += 12
            for s in (fuss() if nach is None else nach):
                rumpf.append((top, s))
                top += 12
        rumpf.append((800, " Beispiel Werkzeugbau GmbH * Musterweg 12 * 12345 Musterstadt"))
        ops = ["BT", "/F1 10 Tf"]
        for t, s in rumpf:
            ops += _zeile_ops(s, t)
        ops.append("ET")
        page = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 595, 842],
                                  Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
                                  Contents=pdf.make_stream("\n".join(ops).encode("cp1252")))
        pdf.pages.append(pikepdf.Page(page))
    pdf.save(str(pfad))
    return pfad
