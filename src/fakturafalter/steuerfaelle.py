# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Steuersonderfälle (ab 0.9.7): Reverse Charge, innergemeinschaftliche Lieferung, Ausfuhr, nicht steuerbar,
Kleinunternehmer – dazu Länder, Formate ausländischer USt-IdNr., Währungszeichen und Umrechnungskurs.

Alles offline: keine VIES-Abfrage, kein Kursabruf. Ein Kurs kommt immer aus den Daten (CSV, XML, Druck).

Ein *Steuerfall* ist die Kennung eines Falls („AE“, „K“, „G“, „O“, „KU“; „S“ = Regelbesteuerung). Er legt
Kategorie (BT-151/BT-118), Satz 0, Befreiungscode (BT-121) und den Standardtext (BT-120) fest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .codelisten import LAENDER, WAEHRUNGEN
from .modell import Steuer


@dataclass(frozen=True)
class Fall:
    kennung: str
    kategorie: str
    code: str  # BT-121 (VATEX), "" = keiner
    text_de: str  # Standardtext BT-120 / Sichtseite
    text_en: str
    name: str  # für Meldungen und Auswahllisten
    muster: str  # Hinweistext im Druck (casefold)
    kurz: str = ""  # Kennzeichen in einer Steuerspalte („RC“, „igL“)


FAELLE: dict[str, Fall] = {
    "AE": Fall(
        "AE", "AE", "VATEX-EU-AE",
        "Steuerschuldnerschaft des Leistungsempfängers",
        "Reverse charge",
        "Reverse Charge (§ 13b UStG, Steuerschuldnerschaft des Leistungsempfängers)",
        r"steuerschuldnerschaft\s+des\s+leistungsempf|reverse[\s-]*charge|§\s*13\s?b\b|\b13\s?b\s+ustg"
        r"|art\.?\s*196\b|umkehr(?:ung)?\s+der\s+steuerschuld|autoliquidation|inversione\s+contabile",
        r"rc|r\.c\.|reverse(?:\s*charge)?|13b|§\s*13b|ae",
    ),
    "K": Fall(
        "K", "K", "VATEX-EU-IC",
        "Steuerfreie innergemeinschaftliche Lieferung",
        "Intra-community supply (VAT exempt)",
        "Innergemeinschaftliche Lieferung (§ 4 Nr. 1 Buchst. b, § 6a UStG)",
        r"innergemeinschaftliche[nr]?\s+lieferung|§\s*4\s*nr\.?\s*1\s*(?:buchst\.?\s*)?b\b|§\s*6\s?a\b"
        r"|intra[\s-]*community\s+suppl|art\.?\s*138\b",
        r"igl|ig\.?\s*l\.?|innergem\.?|ig|k",
    ),
    "G": Fall(
        "G", "G", "VATEX-EU-G",
        "Steuerfreie Ausfuhrlieferung",
        "Export outside the EU (VAT exempt)",
        "Ausfuhrlieferung in ein Drittland (§ 4 Nr. 1 Buchst. a, § 6 UStG)",
        r"ausfuhrlieferung|§\s*4\s*nr\.?\s*1\s*(?:buchst\.?\s*)?a\b|export(?:ed)?\s+outside|art\.?\s*146\b"
        r"|steuerfreie\s+ausfuhr",
        r"ausfuhr|export|g",
    ),
    "O": Fall(
        "O", "O", "VATEX-EU-O",
        "Nicht im Inland steuerbare Leistung",
        "Not subject to German VAT",
        "Nicht steuerbare Leistung",
        r"nicht\s+(?:im\s+inland\s+)?steuerbar|not\s+subject\s+to\s+(?:german\s+)?vat|outside\s+the\s+scope",
        r"n\.?\s*st\.?|nicht\s*steuerbar|o",
    ),
    "KU": Fall(
        "KU", "E", "",
        "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        "No VAT is charged under the small business scheme (§ 19 UStG).",
        "Kleinunternehmer (§ 19 UStG)",
        r"§\s*19\b(?:\s*abs\.?\s*\d)?\s*ustg|\b19\s+ustg|kleinunternehmer",
        r"§\s*19|ku|kleinunternehmer",
    ),
}
# Reihenfolge der Erkennung: Kleinunternehmer zuerst (der Text nennt oft auch „steuerfrei“)
REIHENFOLGE = ("KU", "AE", "K", "G", "O")
NAMEN = {"S": "Regelbesteuerung (Steuersatz aus dem Druck)", **{k: f.name for k, f in FAELLE.items()}}


def erkennen(text: str) -> str | None:
    """Hinweistext (Druck, BT-120) -> Kennung des Steuerfalls oder None."""
    t = " ".join(str(text or "").split()).casefold()
    if not t:
        return None
    for k in REIHENFOLGE:
        if re.search(FAELLE[k].muster, t):
            return k
    return None


def alle_erkennen(text: str) -> list[str]:
    t = " ".join(str(text or "").split()).casefold()
    return [k for k in REIHENFOLGE if t and re.search(FAELLE[k].muster, t)]


def erkennen_kurz(wert: str) -> str | None:
    """Kennzeichen einer Steuerspalte („RC“, „igL“, „0 % igL“, „Ausfuhr“) -> Kennung oder None.
    Einzelbuchstaben (außer bei vollem Wort) gelten nicht – die sind Steuerbuchstaben („A“, „B“)."""
    t = re.sub(r"(?<![§\d])(?<!§ )\b\d+(?:[.,]\d+)?\s*%?(?!\w)", " ", str(wert or "")).strip().casefold()
    t = " ".join(t.split())
    if not t:
        return None
    if lang := erkennen(t):
        return lang
    if len(t.rstrip(".")) <= 1:
        return None
    for k in REIHENFOLGE:
        if re.fullmatch(rf"(?:{FAELLE[k].kurz})\.?", t):
            return k
    return None


def mapping(kennung: str, text: str = "", satz: str | Decimal | None = None) -> dict:
    """Steuer-Mapping (wie in Profilen: BT-151/152/120/121) für einen Fall; „S“ braucht den Satz."""
    if kennung == "S":
        return {"BT-151": "S", "BT-152": str(satz if satz is not None else "19")}
    f = FAELLE[kennung]
    m = {"BT-151": f.kategorie, "BT-152": "0", "BT-120": " ".join(str(text or "").split()) or f.text_de}
    if f.code:
        m["BT-121"] = f.code
    return m


def steuer(kennung: str, text: str = "") -> Steuer:
    m = mapping(kennung, text)
    return Steuer(m["BT-151"], Decimal(m["BT-152"]), m.get("BT-120", ""), m.get("BT-121", ""))


def fall_von(st: Steuer) -> str:
    """Steuer einer Position/Zeile -> Kennung („S“, „Z“, „E“, „AE“, „K“, „G“, „O“, „KU“, „L“, „M“)."""
    if st.kategorie == "E" and re.search(FAELLE["KU"].muster, (st.befreiungsgrund or "").casefold()):
        return "KU"
    return st.kategorie


def standardtext(kennung: str, sprache: str = "de") -> str:
    f = FAELLE.get(kennung)
    if not f:
        return ""
    return f.text_en if sprache == "en" else f.text_de


# ------------------------------------------------------------------ Länder
EU = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split()
)
# Länderpräfix der USt-IdNr. ≠ ISO-Code
UST_PRAEFIX = {"GR": "EL"}
# Ländernamen (deutsch/englisch, kleingeschrieben) -> ISO 3166-1 alpha-2; nur die häufigen, sonst Code eintragen
_NAMEN = {
    "AT": "österreich austria", "BE": "belgien belgium", "BG": "bulgarien bulgaria", "CY": "zypern cyprus",
    "CZ": "tschechien tschechische_republik czechia czech_republic", "DE": "deutschland germany brd",
    "DK": "dänemark denmark", "EE": "estland estonia", "ES": "spanien spain españa", "FI": "finnland finland",
    "FR": "frankreich france", "GR": "griechenland greece", "HR": "kroatien croatia", "HU": "ungarn hungary",
    "IE": "irland ireland", "IT": "italien italy italia", "LT": "litauen lithuania", "LU": "luxemburg luxembourg",
    "LV": "lettland latvia", "MT": "malta", "NL": "niederlande netherlands holland", "PL": "polen poland polska",
    "PT": "portugal", "RO": "rumänien romania", "SE": "schweden sweden", "SI": "slowenien slovenia",
    "SK": "slowakei slovakia", "CH": "schweiz switzerland suisse svizzera", "LI": "liechtenstein",
    "NO": "norwegen norway", "IS": "island iceland", "GB": "großbritannien grossbritannien vereinigtes_königreich "
    "united_kingdom uk england", "US": "usa vereinigte_staaten united_states", "CA": "kanada canada",
    "CN": "china", "JP": "japan", "TR": "türkei turkey türkiye", "AU": "australien australia",
    "IN": "indien india", "BR": "brasilien brazil", "MX": "mexiko mexico", "AE": "vereinigte_arabische_emirate "
    "united_arab_emirates", "SG": "singapur singapore", "KR": "südkorea south_korea", "UA": "ukraine",
    "RS": "serbien serbia", "BA": "bosnien bosnia", "MK": "nordmazedonien north_macedonia", "AL": "albanien albania",
    "ME": "montenegro", "IL": "israel", "ZA": "südafrika south_africa", "MC": "monaco", "SM": "san_marino",
    "AD": "andorra", "VA": "vatikan vatican",
}
LAENDERNAMEN = {n.replace("_", " "): code for code, ns in _NAMEN.items() for n in ns.split()}


def land_code(text: str) -> str:
    """„AT“, „Österreich“, „Austria“, „A-1010 Wien“ (nur Name/Code) -> ISO-Code oder ""."""
    t = " ".join(str(text or "").split()).strip(" .,;")
    if not t:
        return ""
    if t.upper() in LAENDER and len(t) == 2:
        return t.upper()
    if t.upper() == "EL":
        return "GR"
    return LAENDERNAMEN.get(t.casefold(), "")


def ist_eu(land: str) -> bool:
    return (land or "").strip().upper() in EU


# ------------------------------------------------------------------ USt-IdNr. (Aufbau laut BZSt, nur Format)
UST_FORMATE = {
    "AT": r"ATU\d{8}", "BE": r"BE[01]\d{9}", "BG": r"BG\d{9,10}", "CY": r"CY\d{8}[A-Z]",
    "CZ": r"CZ\d{8,10}", "DE": r"DE\d{9}", "DK": r"DK\d{8}", "EE": r"EE\d{9}", "EL": r"EL\d{9}",
    "ES": r"ES[A-Z0-9]\d{7}[A-Z0-9]", "FI": r"FI\d{8}", "FR": r"FR[A-HJ-NP-Z0-9]{2}\d{9}", "HR": r"HR\d{11}",
    "HU": r"HU\d{8}", "IE": r"IE\d[A-Z0-9+*]\d{5}[A-Z]{1,2}", "IT": r"IT\d{11}", "LT": r"LT(?:\d{9}|\d{12})",
    "LU": r"LU\d{8}", "LV": r"LV\d{11}", "MT": r"MT\d{8}", "NL": r"NL\d{9}B\d{2}", "PL": r"PL\d{10}",
    "PT": r"PT\d{9}", "RO": r"RO\d{2,10}", "SE": r"SE\d{10}01", "SI": r"SI\d{8}", "SK": r"SK\d{10}",
    "XI": r"XI(?:\d{9}|\d{12}|GD\d{3}|HA\d{3})",
}


def ust_id_kompakt(u: str) -> str:
    return re.sub(r"[\s.\-]", "", str(u or "")).upper()


def ust_id_land(u: str) -> str:
    """Präfix der USt-IdNr. als ISO-Land (EL -> GR, XI -> GB); "" ohne Buchstabenpräfix."""
    p = ust_id_kompakt(u)[:2]
    if not re.fullmatch(r"[A-Z]{2}", p):
        return ""
    return {"EL": "GR", "XI": "GB"}.get(p, p)


def ust_id_format_ok(u: str) -> bool | None:
    """True/False nach dem Aufbau des Landes; None, wenn das Präfix kein EU-Format ist (z. B. CHE…)."""
    k = ust_id_kompakt(u)
    rx = UST_FORMATE.get(k[:2])
    if rx is None:
        return None
    return bool(re.fullmatch(rx, k))


# ------------------------------------------------------------------ Währung und Kurs
SYMBOLE = {"€": "EUR", "$": "USD", "US$": "USD", "£": "GBP", "¥": "JPY", "Fr.": "CHF", "SFr.": "CHF",
           "sFr.": "CHF", "zł": "PLN", "Kč": "CZK", "kr": None}
_SYM_RX = re.compile(r"US\$|SFr\.|sFr\.|Fr\.|zł|Kč|[€$£¥]")
_CODE_RX = re.compile(r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])")


def waehrungen_im_text(text: str) -> list[str]:
    """Währungscodes, die im Text vorkommen (Symbole oder ISO-Codes), in der Reihenfolge des Auftretens."""
    out: list[str] = []
    t = str(text or "")
    for m in sorted(list(_SYM_RX.finditer(t)) + list(_CODE_RX.finditer(t)), key=lambda m: m.start()):
        c = SYMBOLE.get(m.group(0)) if m.re is _SYM_RX else m.group(1)
        if c and c in WAEHRUNGEN and c not in out:
            out.append(c)
    return out


def dezimal(text: str) -> Decimal | None:
    """„1,0850“, „1.0850“, „1.234,56“, „1,234.56“ -> Decimal (letztes Trennzeichen = Dezimal)."""
    t = re.sub(r"[^\d,.\-]", "", str(text or ""))
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if t.count(",") == 1 else t.replace(",", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


_ZAHL = r"(\d+(?:[.,]\d+)*)"


def kurs_lesen(text: str, waehrung: str = "") -> tuple[Decimal | None, str]:
    """Kurszeile -> (Kurs „1 EUR = x Fremdwährung“, Fremdwährung). Versteht „1 EUR = 1,0850 USD“,
    „USD 1 = EUR 0,9217“, „EUR/USD 1,0850“, „Kurs: 1,0850“ (dann Richtung 1 EUR = x, Währung = ``waehrung``)."""
    t = " ".join(str(text or "").replace("€", " EUR ").split())
    codes = r"([A-Z]{3})"
    m = re.search(rf"(?:1\s*)?EUR\s*=\s*{_ZAHL}\s*{codes}", t)
    if m and m.group(2) != "EUR":
        return dezimal(m.group(1)), m.group(2)
    m = re.search(rf"(?:1\s*)?{codes}\s*=\s*{_ZAHL}\s*EUR", t) or re.search(
        rf"{codes}\s*1\s*=\s*EUR\s*{_ZAHL}", t
    )
    if m and m.group(1) != "EUR":
        wert = dezimal(m.group(2))
        if wert:
            return (Decimal(1) / wert).quantize(Decimal("0.000001")), m.group(1)
    m = re.search(rf"EUR\s*/\s*{codes}\s*:?\s*{_ZAHL}", t)
    if m:
        return dezimal(m.group(2)), m.group(1)
    m = re.search(rf"(?:kurs|rate)\D*{_ZAHL}", t, re.I)
    if m:
        return dezimal(m.group(1)), waehrung
    return None, ""


def kurs_text(r, sprache: str = "de") -> str:
    """„Umrechnungskurs: 1 EUR = 1,0850 USD (Stand 01.11.2026)“ – leer ohne Kurs."""
    if not r.kurs or (r.waehrung or "EUR").upper() == "EUR":
        return ""
    stellen = max(4, -r.kurs.normalize().as_tuple().exponent)
    k = f"{r.kurs:.{stellen}f}".replace(".", ",")
    if sprache == "en":
        t = f"Exchange rate: 1 EUR = {k.replace(',', '.')} {r.waehrung}"
        return t + (f" (as of {r.kursdatum:%Y-%m-%d})" if r.kursdatum else "")
    return f"Umrechnungskurs: 1 EUR = {k} {r.waehrung}" + (
        f" (Stand {r.kursdatum:%d.%m.%Y})" if r.kursdatum else ""
    )
