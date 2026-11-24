# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Zahlungsbedingung aus dem Druck (BT-20) lesen: Netto-Fälligkeit (BT-9), Zahlungsziel in Tagen, Skonto.

Der Text bleibt, wie er gedruckt ist (BT-20, Zeilen mit Leerzeichen verbunden). Daraus abgeleitet wird nur, was
eindeutig ist:

* „zahlbar bis 8.11.26 bei 3 % Skonto (12,34 €)“ + „bis 28.11.2026 ohne Abzug“ -> BT-9 = 28.11.2026,
  Skonto 3 % bis 08.11.2026 (Betrag gegen Brutto × Satz geprüft: Abweichung ist ein Hinweis, kein Fehler)
* „zahlbar bis 28.11.2026 ohne Abzug“ -> BT-9 = 28.11.2026
* „14 Tage 2 % Skonto, 30 Tage netto“ -> Zahlungsziel 30 Tage (das Netto-Ziel, nicht die Skontofrist)

Strukturiertes Skonto (ApplicableTradePaymentDiscountTerms) gibt es im Profil EN 16931 nicht; der Freitext in
BT-20 genügt (BMF-Schreiben vom 15.10.2025, Abschn. 14.5 Abs. 19 UStAE).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from . import rechnen

_DATUM = r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)"
_NETTO = r"(?:ohne\s+(?:jeden\s+)?abzug|rein\s+netto|netto(?:\s+kasse)?|net)\b"
_BETRAG = r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}|-?\d+\.\d{2}"


@dataclass
class Skonto:
    satz: Decimal
    bis: date | None = None
    betrag: Decimal | None = (
        None  # gedruckter Betrag in Klammern (Abzug oder Zahlbetrag), falls vorhanden
    )


@dataclass
class Zahlungsziel:
    text: str = ""
    faellig: date | None = None  # Netto-Fälligkeit („bis … ohne Abzug“)
    tage: int | None = None  # Netto-Zahlungsziel in Tagen
    skonto: list[Skonto] = field(default_factory=list)


def _datum(t: tuple[str, str, str]) -> date | None:
    tag, monat, jahr = (int(x) for x in t)
    if jahr < 100:
        jahr += 2000
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


def _betrag(t: str) -> Decimal | None:
    t = t.strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def text_verbinden(text: str) -> str:
    """Zeilen des Drucks zu einem BT-20-Text: Zeilenumbrüche und Mehrfach-Leerzeichen -> ein Leerzeichen."""
    return " ".join(str(text or "").split())


def netto_tage(text: str | None) -> int | None:
    """Netto-Zahlungsziel in Tagen: die Zahl vor „Tage“, die mit „netto“/„ohne Abzug“ steht, sonst die
    größte (eine Skontofrist ist kürzer als das Netto-Ziel)."""
    t = text or ""
    treffer = list(re.finditer(r"(\d{1,3})\s*(?:Tage|Tagen|days)\b", t, re.I))
    if not treffer:
        return None
    for m in treffer:
        rest = t[m.end() : m.end() + 30]
        if re.match(r"\s*[,:;]?\s*" + _NETTO, rest, re.I) or re.search(
            _NETTO + r"\s*$", t[max(0, m.start() - 25) : m.start()], re.I
        ):
            return int(m[1])
    return max(int(m[1]) for m in treffer)


def lesen(text: str | None) -> Zahlungsziel:
    t = text_verbinden(text or "")
    z = Zahlungsziel(text=t)
    if not t:
        return z
    # „bis <Datum> … ohne Abzug“ (Netto-Fälligkeit); mehrere: das späteste
    netto = [
        _datum(m.groups()[:3])
        for m in re.finditer(r"bis\s+(?:zum\s+)?" + _DATUM + r"[^0-9%]{0,25}?" + _NETTO, t, re.I)
    ]
    netto = [d for d in netto if d]
    if not netto:
        # ohne „bis … netto/ohne Abzug“: „Bitte überweisen bis 02.11.2026.“ – jedes „bis <Datum>“ in einem
        # Satzteil ohne Skonto ist die Netto-Fälligkeit (das späteste)
        netto = [
            d
            for teil in re.split(r"[,;]|\.\s", t)
            if not re.search(r"%|skonto", teil, re.I)
            for m in re.finditer(r"bis\s+(?:zum\s+)?" + _DATUM, teil + " ", re.I)
            if (d := _datum(m.groups()[:3]))
        ]
    if netto:
        z.faellig = max(netto)
    # „bis <Datum> bei/mit X % Skonto (Betrag)“ oder „bis <Datum> X % Skonto“
    for m in re.finditer(
        r"bis\s+(?:zum\s+)?" + _DATUM + r"\s*(?:bei|mit|abzüglich|abzgl\.?)?\s*"
        r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*Skonto\s*(?:\(\s*(?:EUR|€)?\s*("
        + _BETRAG
        + r")\s*(?:EUR|€)?\s*\))?",
        t,
        re.I,
    ):
        z.skonto.append(
            Skonto(
                satz=_betrag(m[4]),
                bis=_datum(m.groups()[:3]),
                betrag=_betrag(m[5]) if m[5] else None,
            )
        )
    if z.faellig is None:
        z.tage = netto_tage(t)
    return z


def skonto_hinweise(z: Zahlungsziel, brutto: Decimal | None) -> list[str]:
    """Gedruckten Skontobetrag gegen Brutto × Satz prüfen (Toleranz 0,01). Passt auch der Zahlbetrag nach
    Abzug (Brutto − Skonto), ist das in Ordnung. -> Hinweise (keine Fehler)."""
    out = []
    if brutto is None:
        return out
    for s in z.skonto:
        if s.betrag is None or s.satz is None:
            continue
        abzug = (brutto * s.satz / 100).quantize(rechnen.CENT)
        if (
            abs(s.betrag - abzug) <= rechnen.TOLERANZ
            or abs(s.betrag - (brutto - abzug)) <= rechnen.TOLERANZ
        ):
            continue
        out.append(
            f"Skonto {_de(s.satz)} %: gedruckter Betrag {_de(s.betrag, 2)} passt nicht zu "
            f"{_de(s.satz)} % von {_de(brutto, 2)} = {_de(abzug, 2)} – bitte prüfen"
        )
    return out


def _de(d: Decimal, stellen: int | None = None) -> str:
    if stellen is not None:
        s = f"{d:,.{stellen}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return format(d.normalize(), "f").replace(".", ",")


def datum_im_text(d: date, text: str) -> bool:
    """Steht das Datum ``d`` schon im Text (8.11.26, 08.11.2026 …)?"""
    for m in re.finditer(_DATUM, text or ""):
        if _datum(m.groups()) == d:
            return True
    return False


def profiltext_sperren(r, quelltext: str) -> bool:
    """Nennt die Quelle (Druck) Skonto, darf der Standardtext des Profils („… ohne Abzug“) nicht still ins XML:
    er widerspräche der gedruckten Bedingung. Dann bleiben BT-20 und BT-9 leer und die Rechnung geht in
    „Prüfen“. -> True, wenn gesperrt wurde."""
    h = r.herkunft.get("BT-20")
    if h is None or h.quelle != "profil":
        return False
    if not re.search(r"skonto", quelltext or "", re.I):
        return profilziel_anpassen(r, quelltext)
    alt = r.zahlung.bedingungen
    r.zahlung.bedingungen = ""
    r.zahlung.ziel_tage = None
    r.zahlung.faellig = None
    r.hinweis(
        "pruefen",
        "Der Druck nennt Skonto, die Zahlungsbedingung fehlt aber in den Daten. Der Standardtext "
        f"des Profils{f' („{alt}“)' if alt else ''} wird deshalb nicht übernommen – bitte die "
        "Zahlungsbedingung angeben",
        "BT-20",
    )
    return True


_ZAHLUNG_SPRACHE = re.compile(
    r"zahlbar|zahlungsziel|zahlungsbeding|"
    r"(?:tage|tagen)\s+(?:netto|ohne)|netto\s*(?:kasse|tage)|"
    r"ohne\s+(?:jeden\s+)?abzug|skonto|rein\s+netto|"
    r"innerhalb\s+von\s+\d",
    re.I,
)
_UNGELESEN = re.compile(
    r"nach\s+vereinbarung|laut\s+vereinbarung|\bsofort\b|im\s+voraus|"
    r"vorkasse|gegen\s+bar|bei\s+lieferung|netto\s+kasse",
    re.I,
)
_FAELLIG_DATUM = re.compile(r"f[äa]llig(?:keitsdatum|keit|es datum| am| bis)?:?\s*" + _DATUM, re.I)


def _zahlungspassagen(text: str) -> str:
    """Textfenster um Zahlungsbegriffe, damit Lieferdaten und Positionsangaben nicht mitgelesen werden."""
    teile = []
    for m in _ZAHLUNG_SPRACHE.finditer(text or ""):
        a, b = max(0, m.start() - 20), min(len(text), m.end() + 80)
        teile.append(text[a:b])
    for m in _FAELLIG_DATUM.finditer(text or ""):
        teile.append(m.group(0))
    return " ".join(teile)


def _passage_fuer_tage(text: str, tage: int) -> str:
    for m in re.finditer(r".{0,40}" + str(tage) + r"\s*(?:Tage|Tagen)\b.{0,40}", text or "", re.I):
        s = text_verbinden(m.group(0).strip(" .,;:"))
        if netto_tage(s) == tage:
            return s
    return ""


def _faellig_im_text(text: str) -> date | None:
    z = lesen(_zahlungspassagen(text))
    if z.faellig:
        return z.faellig
    treffer = [_datum(m.groups()) for m in _FAELLIG_DATUM.finditer(text or "")]
    treffer = [d for d in treffer if d]
    return max(treffer) if treffer else None


def profilziel_anpassen(r, quelltext: str) -> bool:
    """BT-20 kommt aus dem Profil, der Druck nennt aber ein anderes oder unlesbares Ziel: gedrucktes Ziel
    übernehmen oder BT-9/BT-20 leeren und prüfen – nie still die 14 Tage des Profils stehen lassen. -> True,
    wenn angepasst wurde. Ohne Zahlungsangabe im Druck bleibt das Profil unberührt."""
    h = r.herkunft.get("BT-20")
    if h is None or h.quelle != "profil":
        return False
    t = quelltext or ""
    passage = _zahlungspassagen(t)
    tage = netto_tage(passage) if passage else None
    faellig_druck = _faellig_im_text(t)
    profil_tage = r.zahlung.ziel_tage
    profil_faellig = r.zahlung.faellig

    if tage is not None and tage != profil_tage:
        r.zahlung.ziel_tage = tage
        r.zahlung.faellig = (r.datum + timedelta(days=tage)) if r.datum else None
        r.zahlung.bedingungen = _passage_fuer_tage(t, tage)
        return True
    if faellig_druck is not None and faellig_druck != profil_faellig:
        r.zahlung.faellig = faellig_druck
        r.zahlung.ziel_tage = (faellig_druck - r.datum).days if r.datum else None
        # Profiltext („14 Tagen“) würde zur gedruckten Fälligkeit widersprechen
        r.zahlung.bedingungen = text_verbinden(passage) if passage else ""
        return True
    if _UNGELESEN.search(t) and (tage is None or tage != profil_tage):
        alt = r.zahlung.bedingungen
        r.zahlung.bedingungen = ""
        r.zahlung.ziel_tage = None
        r.zahlung.faellig = None
        r.hinweis(
            "pruefen",
            "Der Druck nennt eine Zahlungsbedingung, die sich nicht eindeutig lesen lässt. Das "
            f"Zahlungsziel aus dem Profil{f' („{alt}“)' if alt else ''} wird deshalb nicht "
            "übernommen – bitte die Zahlungsbedingung angeben",
            "BT-20",
        )
        return True
    return False
