# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Rechnungsnummer prüfen und Dateinamen der Ausgabe bilden (ab 0.9.5).

Fakturafalter vergibt **keine** Nummern: BT-1 kommt immer aus der Quelle (CSV/XML/ERP). Je Belegart
(Rechnung, Gutschrift) lässt sich optional einstellen:

- ein **Prüfmuster** für die Nummer (weicht sie ab -> „Zu prüfen“, nichts wird geändert),
- eine **Lückenwarnung** (nur Warnung, die Rechnung läuft durch; Lücken sind erlaubt, UStAE 14.5 Abs. 10),
- ein **Dateinamen-Muster** für die ZUGFeRD-PDF und die XRechnung-XML im Ausgang.

Konfiguration (alle Schlüssel optional; fehlen sie, gilt das bisherige Verhalten)::

    optionen:
      nummernkreise:
        rechnung:   {pruefmuster: "JJJJ######", luecken_warnen: true,
                     dateiname: "{jahr}_{rechnungsnummer}_{kunde}", dateiname_xrechnung: ""}
        gutschrift: {pruefmuster: "GS-JJJJ-####", luecken_warnen: false, dateiname: ""}

Belegart „gutschrift“ = BT-3 381, alles andere (380, 384, 386, 326 …) zählt zum Kreis „rechnung“.
Ein leeres Dateinamen-Muster der Gutschrift heißt „wie bei der Rechnung“; ein leeres Prüfmuster heißt
„keine Formatprüfung“ (jeder Kreis für sich).

Prüfmuster: ``JJJJ`` Jahr (4 Ziffern), ``JJ`` Jahr (2 Ziffern), ``MM`` Monat (01–12), ``#`` eine Ziffer,
``*`` beliebig viele Zeichen; alles andere steht wörtlich da (Groß-/Kleinschreibung egal). Der letzte
``#``-Block ist der Zähler für die Lückenwarnung; alles davor und danach bildet den Kreis (z. B. das Jahr).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

KREISE = ("rechnung", "gutschrift")
STANDARD_PDF = "{rechnungsnummer}_zugferd"
STANDARD_XML = "{rechnungsnummer}_xrechnung"

BELEGART_NAME = {
    "380": "Rechnung",
    "381": "Gutschrift",
    "384": "Rechnungskorrektur",
    "386": "Anzahlungsrechnung",
    "326": "Teilrechnung",
}
BELEGART_KURZ = {"380": "RE", "381": "GS", "384": "KO", "386": "AR", "326": "TR"}

# Platzhalter im Dateinamen-Muster -> Beschreibung (auch für die Oberfläche)
PLATZHALTER = {
    "rechnungsnummer": "Rechnungsnummer (BT-1)",
    "jahr": "Jahr des Rechnungsdatums",
    "monat": "Monat des Rechnungsdatums (01–12)",
    "tag": "Tag des Rechnungsdatums (01–31)",
    "datum": "Rechnungsdatum JJJJ-MM-TT",
    "kundennummer": "Kundennummer",
    "kunde": "Name des Kunden (gekürzt)",
    "belegart": "Belegart (Rechnung, Gutschrift …)",
    "belegart_kurz": "Belegart kurz (RE, GS, KO …)",
}
_PLATZ_RE = re.compile(r"\{([^{}]*)\}")
_VERBOTEN = set('\\/:*?"<>|,;')
_RESERVIERT = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_UMLAUTE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)
KUNDE_MAX = 40
STAMM_MAX = 180


class MusterFehler(ValueError):
    """Ungültiges Prüf- oder Dateinamen-Muster (Klartext für Oberfläche und Log)."""


@dataclass
class Kreis:
    pruefmuster: str = ""
    luecken_warnen: bool = False
    dateiname: str = ""
    dateiname_xrechnung: str = ""

    @property
    def leer(self) -> bool:
        return not (
            self.pruefmuster or self.luecken_warnen or self.dateiname or self.dateiname_xrechnung
        )


def aus_optionen(opt: dict | None) -> dict[str, Kreis]:
    """``optionen.nummernkreise`` -> {kreis: Kreis}. Fehlt der Block: {} (bisheriges Verhalten)."""
    roh = (opt or {}).get("nummernkreise") or {}
    aus: dict[str, Kreis] = {}
    if not isinstance(roh, dict):
        return aus
    for name in KREISE:
        d = roh.get(name) or {}
        if not isinstance(d, dict):
            continue
        k = Kreis(
            str(d.get("pruefmuster") or "").strip(),
            bool(d.get("luecken_warnen", False)),
            str(d.get("dateiname") or "").strip(),
            str(d.get("dateiname_xrechnung") or "").strip(),
        )
        if not k.leer:
            aus[name] = k
    return aus


def in_optionen(kreise: dict[str, Kreis]) -> dict:
    """Gegenstück zu ``aus_optionen`` (nur belegte Werte, für ``konfiguration.yaml``)."""
    aus = {}
    for name in KREISE:
        k = kreise.get(name)
        if not k or k.leer:
            continue
        d: dict = {}
        if k.pruefmuster:
            d["pruefmuster"] = k.pruefmuster
        if k.luecken_warnen:
            d["luecken_warnen"] = True
        if k.dateiname:
            d["dateiname"] = k.dateiname
        if k.dateiname_xrechnung:
            d["dateiname_xrechnung"] = k.dateiname_xrechnung
        aus[name] = d
    return aus


def kreis_von(art: str) -> str:
    return "gutschrift" if str(art).strip() == "381" else "rechnung"


# ---------------------------------------------------------------- Prüfmuster
def _teile(muster: str) -> list[tuple[str, str]]:
    """Prüfmuster -> [(art, text)], art: jahr4 | jahr2 | monat | ziffern | stern | text."""
    aus: list[tuple[str, str]] = []
    i = 0
    m = muster
    while i < len(m):
        ch = m[i]
        if ch in "Jj":
            n = len(m[i:]) - len(m[i:].lstrip("Jj"))
            if n == 4:
                aus.append(("jahr4", m[i : i + 4]))
                i += 4
                continue
            if n == 2:
                aus.append(("jahr2", m[i : i + 2]))
                i += 2
                continue
            aus.append(("text", m[i : i + n]))
            i += n
            continue
        if ch in "Mm" and m[i : i + 2] in ("MM", "mm") and m[i + 2 : i + 3] not in ("M", "m"):
            aus.append(("monat", m[i : i + 2]))
            i += 2
            continue
        if ch == "#":
            n = len(m[i:]) - len(m[i:].lstrip("#"))
            aus.append(("ziffern", m[i : i + n]))
            i += n
            continue
        if ch == "*":
            aus.append(("stern", "*"))
            i += 1
            continue
        if aus and aus[-1][0] == "text":
            aus[-1] = ("text", aus[-1][1] + ch)
        else:
            aus.append(("text", ch))
        i += 1
    return aus


def muster_regex(muster: str) -> re.Pattern:
    """Prüfmuster -> Regex mit Gruppen ``kreis`` (alles außer dem Zähler) und ``zaehler`` (letzter #-Block)."""
    muster = (muster or "").strip()
    if not muster:
        raise MusterFehler("Prüfmuster ist leer")
    teile = _teile(muster)
    letzte = max((i for i, (a, _t) in enumerate(teile) if a == "ziffern"), default=None)
    rx = []
    for i, (art, t) in enumerate(teile):
        if art == "jahr4":
            r = r"(?:19|20)\d\d"
        elif art == "jahr2":
            r = r"\d\d"
        elif art == "monat":
            r = r"(?:0[1-9]|1[0-2])"
        elif art == "ziffern":
            r = rf"\d{{{len(t)}}}"
        elif art == "stern":
            r = r".*?"
        else:
            r = re.escape(t)
        rx.append(f"(?P<zaehler>{r})" if i == letzte else f"({r})")
    return re.compile("^" + "".join(rx) + "$", re.IGNORECASE)


def muster_pruefen(muster: str) -> str:
    """Leer = in Ordnung, sonst Fehlertext (für die Oberfläche)."""
    if not (muster or "").strip():
        return ""
    try:
        muster_regex(muster)
    except (MusterFehler, re.error) as e:
        return str(e)
    return ""


def passt(nummer: str, muster: str) -> bool:
    return bool(muster_regex(muster).match((nummer or "").strip()))


def hat_zaehler(muster: str) -> bool:
    return any(a == "ziffern" for a, _t in _teile(muster or ""))


def zaehler(nummer: str, muster: str) -> tuple[str, int] | None:
    """-> (Kreis-Schlüssel, Zähler) oder None (Nummer passt nicht oder Muster ohne #)."""
    m = muster_regex(muster).match((nummer or "").strip())
    if not m or "zaehler" not in m.groupdict():
        return None
    start, ende = m.span("zaehler")
    n = (nummer or "").strip()
    return (n[:start] + "\x00" + n[ende:]).upper(), int(m.group("zaehler"))


def luecke(nummer: str, andere: set[str] | frozenset[str], muster: str) -> tuple[str, int] | None:
    """Lücke vor ``nummer`` im selben Kreis -> (Vorgänger-Nummer, Anzahl fehlender Nummern) oder None.
    Vorgänger = größte bekannte Nummer desselben Kreises, die kleiner ist. Ohne Vorgänger keine Warnung."""
    z = zaehler(nummer, muster)
    if z is None:
        return None
    schl, wert = z
    best: tuple[int, str] | None = None
    for a in andere:
        if a == nummer:
            continue
        za = zaehler(a, muster)
        if za is None or za[0] != schl or za[1] >= wert:
            continue
        if best is None or za[1] > best[0]:
            best = (za[1], a)
    if best is None or wert - best[0] <= 1:
        return None
    return best[1], wert - best[0] - 1


# ---------------------------------------------------------------- Dateiname
def _wert_bereinigen(t: str) -> str:
    t = unicodedata.normalize("NFC", str(t or "")).translate(_UMLAUTE)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^A-Za-z0-9._-]+", "_", t)
    return re.sub(r"_+", "_", t).strip("_.-")


def dateiname_pruefen(muster: str) -> str:
    """Leer = in Ordnung, sonst Fehlertext (unbekannter Platzhalter, unzulässiges Zeichen)."""
    m = (muster or "").strip()
    if not m:
        return ""
    if m.count("{") != m.count("}"):
        return "Klammern { } passen nicht zusammen"
    for name in _PLATZ_RE.findall(m):
        if name not in PLATZHALTER:
            return f"Unbekannter Platzhalter {{{name}}}"
    rest = _PLATZ_RE.sub("", m)
    schlecht = sorted({c for c in rest if c in _VERBOTEN or ord(c) < 32})
    if schlecht:
        return "Unzulässige Zeichen im Dateinamen: " + " ".join(schlecht)
    return ""


def _werte(r) -> dict[str, str]:
    d: date | None = r.datum if isinstance(r.datum, date) else None
    kunde = _wert_bereinigen(r.kaeufer.name)[:KUNDE_MAX].strip("_.-")
    return {
        "rechnungsnummer": _wert_bereinigen(r.nummer),
        "jahr": f"{d:%Y}" if d else "",
        "monat": f"{d:%m}" if d else "",
        "tag": f"{d:%d}" if d else "",
        "datum": f"{d:%Y-%m-%d}" if d else "",
        "kundennummer": _wert_bereinigen(r.kundennummer),
        "kunde": kunde,
        "belegart": BELEGART_NAME.get(str(r.art), "Rechnung"),
        "belegart_kurz": BELEGART_KURZ.get(str(r.art), "RE"),
    }


def dateiname(muster: str, r, endung: str) -> str:
    """Dateinamen aus dem Muster bilden (``endung`` z. B. ``.pdf``). Werte werden für Windows und Linux
    bereinigt (Umlaute ä -> ae, Sonderzeichen -> _), leere Platzhalter fallen weg, Reservenamen (CON …) und
    Punkte am Ende werden vermieden, der Stamm wird auf 180 Zeichen gekürzt."""
    fehler = dateiname_pruefen(muster)
    if fehler:
        raise MusterFehler(fehler)
    m = muster.strip()
    if m.lower().endswith(endung.lower()):
        m = m[: -len(endung)]
    werte = _werte(r)
    stamm = _PLATZ_RE.sub(lambda x: werte.get(x.group(1), ""), m)
    stamm = re.sub(r"\s+", " ", stamm)
    stamm = re.sub(r"([_-])[_-]+", r"\1", stamm)  # durch leere Platzhalter doppelte Trenner
    stamm = stamm.strip(" _-.")[:STAMM_MAX].rstrip(" .")
    if not stamm:
        stamm = "ohne_nummer"
    if stamm.split(".")[0].upper() in _RESERVIERT:
        stamm = "_" + stamm
    return stamm + endung


def muster_beispiel(muster: str, zaehler_wert: int = 123, jahr: int = 2026, monat: int = 11) -> str:
    """Eine Beispielnummer, die zum Prüfmuster passt (für die Vorschau), z. B. JJJJ###### -> 2026000123."""
    teile = _teile((muster or "").strip())
    letzte = max((i for i, (a, _t) in enumerate(teile) if a == "ziffern"), default=None)
    aus = []
    for i, (art, t) in enumerate(teile):
        if art == "jahr4":
            aus.append(f"{jahr:04d}")
        elif art == "jahr2":
            aus.append(f"{jahr % 100:02d}")
        elif art == "monat":
            aus.append(f"{monat:02d}")
        elif art == "ziffern":
            n = zaehler_wert if i == letzte else 0
            aus.append(str(n).zfill(len(t))[-len(t) :])
        elif art == "stern":
            aus.append("X")
        else:
            aus.append(t)
    return "".join(aus)


BEISPIEL_NUMMER = {"rechnung": "2026000123", "gutschrift": "GS-2026-0007"}


def beispiel(kreis: str, pruefmuster: str = ""):
    """Beispielbeleg für die Live-Vorschau in den Einstellungen (fiktive Werte). Mit Prüfmuster trägt er eine
    passende Nummer."""
    from .modell import Partei, Rechnung

    nummer = BEISPIEL_NUMMER.get(kreis, "2026000123")
    if (pruefmuster or "").strip() and not muster_pruefen(pruefmuster):
        nummer = muster_beispiel(pruefmuster)
    return Rechnung(
        nummer=nummer,
        datum=date(2026, 11, 24),
        art="381" if kreis == "gutschrift" else "380",
        kundennummer="K-1001",
        kaeufer=Partei(name="Café Morgenrot Werk Süd"),
    )
