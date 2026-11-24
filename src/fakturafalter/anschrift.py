# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Deutsche Anschriften (N1) aus Textzeilen lesen – eine Quelle für Käufer (Assistent, Vorlage) und Absender.

Muster für PLZ, Straße, Postfach und die feste Regel „von unten nach oben“ (``anschrift_zerlegen``)."""

from __future__ import annotations

import re

from .pflichtpruefung import iban_gueltig
from .werte import ohne_steuerzeichen

# Straße + Hausnummer: „Talstraße 12“, „Am Markt 3–5“, „Hafenstraße 10 - 12“; Mannheimer Quadrate „Q 7, 12“
_HAUSNR = r"\d+\s?[a-zA-Z]?(?:\s?[-/–]\s?\d+[a-z]?)?"
_STRASSE = re.compile(rf"^(?:[^\W\d_][\w .'äöüÄÖÜß-]*?\s|[A-U]\s?\d{{1,2}},\s?){_HAUSNR}$")
# Die eine deutsche PLZ (N1: nur DE): 5 Ziffern, davor optional „D“/„DE“ mit Bindestrich oder Leerzeichen
PLZ_MUSTER = r"(?:DE?\s?-?\s?)?(\d{5})"
PLZ_ORT = re.compile(rf"^{PLZ_MUSTER}\s+([^\W\d_][\w .äöüÄÖÜß()/-]*)$")
_NUR_PLZ = re.compile(rf"^{PLZ_MUSTER}$")
_PLZ_IN_ZEILE = re.compile(rf"(?:^|[\s,·•|]){PLZ_MUSTER}\s+[^\W\d_]")  # „Fa, Weg 1, 12345 Ort“

_LAND = re.compile(r"^(?:deutschland|germany|de|d)$", re.I)
_STRASSE_PLZ = re.compile(rf"^(.+?{_HAUSNR})\s*,\s*({PLZ_MUSTER}\s+.+)$")


_POSTFACH = re.compile(r"^postfach\b", re.I)
# Straße ohne Hausnummer („Am Hafen“, „Lange Reihe“, „Straße des 17. Juni“): nur Wörter und Ordnungszahlen,
# Anfang und Ende ein Wort, keine Satzzeichen wie Komma, Doppelpunkt, @
_WORT = r"[^\W\d_](?:[^\W\d_]|['.-])*"
_STRASSE_OHNE_NR = re.compile(rf"^{_WORT}(?:(?:\s\d{{1,2}}\.)?\s{_WORT})*$")


_BIC = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")


def kontozeile(t: str) -> bool:
    """Gültige IBAN oder BIC (typisch durchgehend groß) – niemals eine Straße.
    Nur die Form (ohne Prüfsumme) würde „DE-54321 Neustadt“ fälschlich treffen."""
    k = re.sub(r"\s+", "", t or "")
    return iban_gueltig(k) or bool(_BIC.fullmatch(k))


def strasse_mit_nr(t: str) -> bool:
    """Straße mit Hausnummer, ohne IBAN/BIC."""
    t = " ".join(t.split())
    return bool(_STRASSE.match(t) and not kontozeile(t))


def strassenzeile(t: str) -> bool:
    """Zeile hat die Form einer Straße (mit oder ohne Hausnummer) oder eines Postfachs."""
    t = " ".join(t.split())
    if kontozeile(t):
        return False
    return bool(
        strasse_mit_nr(t) or _POSTFACH.match(t) or (len(t) <= 40 and _STRASSE_OHNE_NR.match(t))
    )


# Zeilen ohne Inhalt für die Anschrift: Beschriftung, reine Anrede
_ANSCHRIFT_LABEL = re.compile(
    r"^(?:(?:rechnungs|liefer)?anschrift|rechnungsempfänger(?:in)?|empfänger(?:in)?|"
    r"an|firma|herrn?|frau|bill to|ship to)$",
    re.I,
)


# Zusatz- und Vermerkzeilen der Anschrift nach DIN 5008 (geschlossene Liste, keine Layout-Sonderfälle). Nur am
# Zeilenanfang und als ganzes Wort („Gebäudemanagement“ bleibt Name). Nutzer-Entscheid 23.11.2026: „Abteilung
# nach Adresszeile 2 und z. Hd. in die Kontaktstelle“ – hebt für diese Zeilen die 0.4.4-Regel „alles über der
# Straße = Name“ auf.
_KONTAKTVERMERK = re.compile(r"^(?:z\.\s?hd\.?|z\.\s?h\.|zu\s+händen|attn\.?:?)(?=\s|$)\s*", re.I)
_ZUSATZVERMERK = re.compile(r"^(?:abteilung|abt\.|c/o|gebäude)(?=\s|$)", re.I)


def vermerkzeile(t: str) -> bool:
    """Zeile beginnt mit einem Kontakt- („z. Hd.“, „Attn.“) oder Zusatzvermerk („Abteilung“, „c/o“, „Gebäude“)."""
    t = " ".join(t.split())
    return bool(_KONTAKTVERMERK.match(t) or _ZUSATZVERMERK.match(t))


def zusatz_trennen(namen: list[str]) -> tuple[dict[str, str], list[str]] | None:
    """Zeilen über der Straße (nach den Ausnahmen Namenszeilen) -> (Teile, Rolle je Zeile) oder None (alte Regel:
    alles BT-44). Namenszeilen zuerst, danach Vermerkzeilen: „z. Hd. …“ -> BT-56 (ohne den Vermerk), „Abteilung“/
    „Abt.“/„c/o“/„Gebäude“ -> BT-51, eine zweite solche Zeile -> BT-163. Im Zweifel None: keine Vermerkzeile,
    Namenszeile nach einer Vermerkzeile, mehr als zwei Zusatz- oder mehr als eine Kontaktzeile, Name bliebe leer
    oder Vermerk ohne Text."""
    rollen: list[str] = []
    name: list[str] = []
    zusatz: list[str] = []
    kontakt: list[str] = []
    for t in namen:
        if _KONTAKTVERMERK.match(t):
            rollen.append("kontakt")
            kontakt.append(_KONTAKTVERMERK.sub("", t, count=1).strip())
        elif _ZUSATZVERMERK.match(t):
            rollen.append("zusatz")
            zusatz.append(t)
        elif zusatz or kontakt:
            return None
        else:
            rollen.append("name")
            name.append(t)
    if not name or not (zusatz or kontakt) or len(zusatz) > 2 or len(kontakt) > 1 or "" in kontakt:
        return None
    teile = {"BT-44": " ".join(name)}
    for f, t in zip(("BT-51", "BT-163"), zusatz):
        teile[f] = t
    if kontakt:
        teile["BT-56"] = kontakt[0]
    return teile, rollen


def anschrift_zerlegen(zeilen: list[str], zusatz: bool = True) -> tuple[dict[str, str], list[str]]:
    """Anschriftblock (eine Zeile je Eintrag) von unten nach oben lesen -> (Teile, Rolle je Eingabezeile).

    Teile: BT-44 Name, BT-50 Straße, BT-53 PLZ, BT-52 Ort. Rollen: name, strasse, plz, weg (leer, Beschriftung,
    Land, Absenderzeile). Feste Regel (seit 0.4.4, ohne Sonderfälle für „z. Hd.“, „Abteilung“ usw.):

    - leere Zeilen zählen nicht
    - die unterste Zeile mit Inhalt = PLZ + Ort (eine reine Landzeile darunter zählt nicht;
      „Straße 1, 12345 Ort“ in einer Zeile wird geteilt)
    - die nächste Zeile mit Inhalt darüber = Straße + Hausnummer
    - alles darüber = Name, mit Leerzeichen verbunden (nie Zeilenumbrüche)

    Strukturelle Ausnahmen (Schritt 3, ohne Schlüsselwörter; nur unter deutscher „PLZ Ort“ und wenn darüber
    noch eine Namenszeile bleibt):

    - Straßenzeile ist nur eine Hausnummer und die Zeile darüber ein Straßenname ohne Nummer -> beide = Straße
    - Straßenzeile hat Ziffern, aber keine Straßenform, die Zeile darüber ist Straße/Postfach -> diese ist die
      Straße, die untere Zeile („Gebäude C, 3. Stock“) wird hinten an den Namen gehängt (BT-51 bleibt leer)

    ``zusatz`` (Käufer, Voreinstellung): Vermerkzeilen über der Straße nach ``zusatz_trennen`` -> BT-51/BT-163/BT-56
    (Rollen „zusatz“/„kontakt“). Der Absender liest ohne (``zusatz=False``)."""
    ls = [" ".join(ohne_steuerzeichen(z).split()) for z in zeilen]
    rollen = ["weg"] * len(ls)
    ein: list[tuple[int, str]] = []
    for i, z in enumerate(ls):
        if not z or z.endswith(":") or _ANSCHRIFT_LABEL.match(z.rstrip(".")) or kontozeile(z):
            continue  # IBAN/BIC gehören nicht zur Anschrift
        if re.search(r"[·•|]", z) or (
            re.search(r"\s[-–]\s", z) and re.search(r"\b\d{5}\b", z) and not PLZ_ORT.match(z)
        ):
            continue  # Absenderzeile über dem Fenster
        m = _STRASSE_PLZ.match(z)
        if m and PLZ_ORT.match(m.group(2)):
            ein += [(i, m.group(1)), (i, m.group(2))]
        else:
            ein.append((i, z))
    if len(ein) > 1 and _LAND.match(ein[-1][1].rstrip(".")) and PLZ_ORT.match(ein[-2][1]):
        ein.pop()  # „Deutschland“ unter PLZ/Ort
    if not ein:
        return {}, rollen
    out: dict[str, str] = {}
    i, t = ein.pop()
    mp = PLZ_ORT.match(t)
    if mp:
        out["BT-53"], out["BT-52"] = mp.group(1), mp.group(2).strip()
    else:
        out["BT-52"] = t
    rollen[i] = "plz"
    unten: list[tuple[int, str]] = []
    if ein:
        i, t = ein.pop()
        # Strukturelle Ausnahmen (Konzept Schritt 3), nur unter deutscher „PLZ Ort“ und wenn darüber noch ein
        # Name bleibt (Ausland bleibt bei der festen Regel + Prüfhinweis, N1)
        if mp and len(ein) >= 2 and rollen[i] != "plz":
            j, oben = ein[-1]
            if (
                _NUR_HAUSNR.match(t)
                and strassenzeile(oben)
                and not strasse_mit_nr(oben)
                and not _POSTFACH.match(oben)
            ):
                ein.pop()  # „Lange Reihe“ / „7a“ -> eine Straße
                rollen[j], t = "strasse", f"{oben} {t}"
            elif (
                re.search(r"\d", t)
                and not (strasse_mit_nr(t) or _POSTFACH.match(t) or _NUR_HAUSNR.match(t))
                and (strasse_mit_nr(oben) or _POSTFACH.match(oben))
            ):
                ein.pop()  # Zusatz mit Ziffer unter der Straße -> zum Namen
                unten, (i, t) = [(i, t)], (j, oben)
        out["BT-50"] = t
        if rollen[i] != "plz":
            rollen[i] = "strasse"
    ein = [
        (i, t) for i, t in ein if not _PLZ_IN_ZEILE.search(ls[i])
    ]  # Absenderzeile „Fa, Weg 1, 12345 Ort“
    getrennt = zusatz_trennen([t for _, t in ein]) if zusatz and ein else None
    if getrennt:
        teile, rz = getrennt
        for (i, _), r in zip(ein, rz):
            rollen[i] = r
        ein = [(i, t) for (i, t), r in zip(ein, rz) if r == "name"] + unten
        out.update(teile)
        out["BT-44"] = " ".join(t for _, t in ein)
        for i, _ in unten:
            rollen[i] = "name"
        return out, rollen
    ein += unten
    if ein:
        out["BT-44"] = " ".join(t for _, t in ein)
        for i, _ in ein:
            rollen[i] = "name"
    return out, rollen


_NUR_HAUSNR = re.compile(
    r"^(?:nr\.?\s*)?\d{1,4}\s?[a-zA-Z]?(?:\s?[-/–]\s?\d{1,4}\s?[a-zA-Z]?)?$", re.I
)


def anschrift_teilen(zeilen: list[str]) -> dict[str, str]:
    """Anschriftblock -> {BT-44 Name, BT-50 Straße, BT-53 PLZ, BT-52 Ort} (s. ``anschrift_zerlegen``)."""
    return anschrift_zerlegen(zeilen)[0]
