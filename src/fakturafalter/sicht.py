# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Sichtteil neu aufbauen (für CSV-Rechnungen ohne Druck oder wenn das Original nicht PDF/A-tauglich ist).

reportlab (BSD) mit eingebetteten Liberation-Schriften (SIL OFL 1.1). Ergebnis wird danach von
``pdfa.py`` zu PDF/A-3b ergänzt (OutputIntent, XMP, Anhang).
"""

from __future__ import annotations

import copy
import io
from datetime import timedelta
from decimal import Decimal
from importlib import resources

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from . import steuerfaelle, zahlungsziel
from .modell import Rechnung

# Einheiten im Sichtteil als Klartext (im XML bleibt der UN/ECE-Code): Code -> (kurz, lang) je Sprache
# PK/RO/CT (nicht in BR-CL-23) bleiben für die Anzeige: CSV-Profile (mappings.einheiten) werden beim Laden nicht
# umgeschrieben und können diese Codes weiter liefern; ohne Eintrag stünde im Sichtteil nur der rohe Code.
_EINHEIT: dict[str, dict[str, tuple[str, str]]] = {
    "de": {
        "H87": ("Stk.", "Stück"),
        "C62": ("Stk.", "Stück"),
        "EA": ("Stk.", "Stück"),
        "XPP": ("Stk.", "Stück"),
        "HUR": ("Std.", "Std."),
        "MIN": ("Min.", "Min."),
        "DAY": ("Tag", "Tage"),
        "WEE": ("Woche", "Wochen"),
        "MON": ("Monat", "Monate"),
        "ANN": ("Jahr", "Jahre"),
        "KGM": ("kg", "kg"),
        "GRM": ("g", "g"),
        "TNE": ("t", "t"),
        "MTR": ("m", "m"),
        "LM": ("lfm", "lfm"),
        "CMT": ("cm", "cm"),
        "MMT": ("mm", "mm"),
        "KMT": ("km", "km"),
        "MTK": ("m²", "m²"),
        "MTQ": ("m³", "m³"),
        "LTR": ("l", "l"),
        "MLT": ("ml", "ml"),
        "KWH": ("kWh", "kWh"),
        "LS": ("pausch.", "pausch."),
        "SET": ("Satz", "Satz"),
        "PR": ("Paar", "Paar"),
        "PK": ("Pack.", "Pack."),
        "XPK": ("Pack.", "Pack."),
        "RO": ("Rolle", "Rollen"),
        "XRO": ("Rolle", "Rollen"),
        "CT": ("Karton", "Kartons"),
        "XCT": ("Karton", "Kartons"),
        "XST": ("Blatt", "Blatt"),
        "XBX": ("Kiste", "Kisten"),
        "DZN": ("Dtzd.", "Dutzend"),
        "XPX": ("Palette", "Paletten"),
        "XSA": ("Sack", "Säcke"),
        "XBO": ("Flasche", "Flaschen"),
        "P1": ("%", "%"),
    },
    "en": {
        "H87": ("pc.", "pcs."),
        "C62": ("pc.", "pcs."),
        "EA": ("ea.", "each"),
        "XPP": ("pc.", "pcs."),
        "HUR": ("hr", "hrs"),
        "MIN": ("min", "min"),
        "DAY": ("day", "days"),
        "WEE": ("week", "weeks"),
        "MON": ("month", "months"),
        "ANN": ("year", "years"),
        "KGM": ("kg", "kg"),
        "GRM": ("g", "g"),
        "TNE": ("t", "t"),
        "MTR": ("m", "m"),
        "LM": ("lin. m", "lin. m"),
        "CMT": ("cm", "cm"),
        "MMT": ("mm", "mm"),
        "KMT": ("km", "km"),
        "MTK": ("m²", "m²"),
        "MTQ": ("m³", "m³"),
        "LTR": ("l", "l"),
        "MLT": ("ml", "ml"),
        "KWH": ("kWh", "kWh"),
        "LS": ("lump sum", "lump sum"),
        "SET": ("set", "sets"),
        "PR": ("pair", "pairs"),
        "PK": ("pack", "packs"),
        "XPK": ("pack", "packs"),
        "RO": ("roll", "rolls"),
        "XRO": ("roll", "rolls"),
        "CT": ("carton", "cartons"),
        "XCT": ("carton", "cartons"),
        "XST": ("sheet", "sheets"),
        "XBX": ("box", "boxes"),
        "DZN": ("doz.", "dozen"),
        "XPX": ("pallet", "pallets"),
        "XSA": ("sack", "sacks"),
        "XBO": ("bottle", "bottles"),
        "P1": ("%", "%"),
    },
}
_registriert = False


def _sprache(sprache: str | None) -> str:
    if sprache:
        return sprache if sprache in _EINHEIT else "de"
    try:  # Sprache der Oberfläche (ohne Qt importierbar)
        from .gui.texte import sprache as ui_sprache

        return ui_sprache() if ui_sprache() in _EINHEIT else "de"
    except Exception:  # noqa: BLE001
        return "de"


def einheit_text(code: str, sprache: str | None = None, lang: bool = False) -> str:
    """UN/ECE-Code -> Klartext für den Sichtteil („H87“ -> „Stk.“, lang „Stück“); unbekannt: der Code."""
    t = _EINHEIT[_sprache(sprache)].get((code or "").upper())
    return (t[1] if lang else t[0]) if t else (code or "")


def sicht_von(r) -> dict:
    return getattr(r, "sicht", None) or {}


def menge_anzeige(p, r=None) -> str:
    """Mengentext für die Sichtseite: Standard exakt wie in der CSV, sonst formatiert."""
    roh = str(getattr(p, "menge_roh", "") or "").strip()
    if (sicht_von(r).get("menge_exakt", True) if r is not None else True) and roh:
        return roh
    return menge(p.menge)


def einheit_anzeige(p, r=None, sprache: str | None = None) -> str:
    """Einheit auf der Sichtseite: Kurzform aus der Tabelle oder unveränderter CSV-Text.

    Wurde die Einheit als Stück angenommen (``einheit_angenommen``), steht auf der
    Sichtseite immer der lange Text „Stück“, unabhängig von ``sicht.einheit``.
    """
    if getattr(p, "einheit_angenommen", False):
        return einheit_text(p.einheit, sprache, lang=True)
    roh = str(getattr(p, "einheit_roh", "") or "").strip()
    if r is not None and sicht_von(r).get("einheit") == "csv" and roh:
        return roh
    return einheit_text(p.einheit, sprache)


def feld_titel(r, schluessel: str, standard: str) -> str:
    d = (sicht_von(r).get("felder") or {}).get(schluessel) or {}
    t = d.get("titel")
    return str(t) if t else standard


def feld_sichtbar(r, schluessel: str, default: bool = True) -> bool:
    d = (sicht_von(r).get("felder") or {}).get(schluessel) or {}
    if "sichtbar" in d:
        return bool(d["sichtbar"])
    if schluessel == "BT-126":
        return bool(sicht_von(r).get("positionsnummer", True))
    return default


def preis_text(
    einzelpreis: Decimal | None,
    preiseinheit: Decimal | None,
    code: str = "",
    sprache: str | None = None,
    waehrung: str = "EUR",
) -> str:
    """Einzelpreis mit Preiseinheit (BT-149) für den Sichtteil: „3,40 €“ oder „3,40 € / 10 Stück“ (Fremdwährung:
    „3,40 USD“ bzw. „3,40 USD / 10 Stück“)."""
    if preiseinheit is None or preiseinheit == 1:
        return betrag(einzelpreis, waehrung)
    # Zeichen nur einmal, vor dem „/ 10 Stück“
    return (
        f"{betrag(einzelpreis, waehrung)} / {menge(preiseinheit)} "
        f"{einheit_text(code, sprache, lang=True)}"
    ).rstrip()


def umbrechen(c, text: str, font: str, groesse: float, breite: float) -> list[str]:
    """Text auf Zeilen von höchstens ``breite`` umbrechen (an Leerzeichen, zu lange Wörter hart).

    Explizite Zeilenumbrüche und leere Zeilen bleiben erhalten (ab 0.9.8, Positionstext).
    """
    aus: list[str] = []
    teile = str(text or "").split("\n")
    for i, teil in enumerate(teile):
        if teil == "":
            aus.append("")
            continue
        zeilen: list[str] = []
        akt = ""
        for wort in teil.split():
            while c.stringWidth(wort, font, groesse) > breite and len(wort) > 1:
                n = len(wort)
                while n > 1 and c.stringWidth(wort[:n], font, groesse) > breite:
                    n -= 1
                if akt:
                    zeilen.append(akt)
                    akt = ""
                zeilen.append(wort[:n])
                wort = wort[n:]
            probe = f"{akt} {wort}".strip()
            if akt and c.stringWidth(probe, font, groesse) > breite:
                zeilen.append(akt)
                akt = wort
            else:
                akt = probe
        if akt:
            zeilen.append(akt)
        aus.extend(zeilen or [""])
    return aus or [""]


def einpassen(
    c,
    texte: list[str],
    font: str,
    groesse: float,
    breite: float,
    min_groesse: float,
    max_zeilen: int | None = None,
) -> tuple[float, list[str]]:
    """Texte in eine Spalte fester Breite: erst Schrift verkleinern (bis ``min_groesse``), dann umbrechen.
    -> (Schriftgröße, Zeilen). ``max_zeilen``: danach wird gekürzt (letzte Zeile mit „…“)."""
    g = groesse
    while g > min_groesse and any(c.stringWidth(t, font, g) > breite for t in texte):
        g = max(min_groesse, g - 0.5)
    zeilen = [z for t in texte for z in umbrechen(c, t, font, g, breite)]
    if max_zeilen and len(zeilen) > max_zeilen:
        zeilen = zeilen[:max_zeilen]
        z = zeilen[-1]
        while z and c.stringWidth(z + "…", font, g) > breite:
            z = z[:-1]
        zeilen[-1] = z.rstrip() + "…"
    return g, zeilen


def _schriften():
    global _registriert
    if _registriert:
        return
    d = resources.files("fakturafalter") / "ressourcen" / "schriften"
    pdfmetrics.registerFont(TTFont("ER-Sans", str(d / "LiberationSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("ER-Sans-Bold", str(d / "LiberationSans-Bold.ttf")))
    _registriert = True


def eur(d: Decimal | None) -> str:
    """Zahl im Sichtteil ohne Währungszeichen: 1234.56 → „1.234,56“."""
    if d is None:
        return ""
    s = f"{d.quantize(Decimal('0.01')):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def waehrung_zeichen(waehrung: str | None = "EUR") -> str:
    """EUR → „€“, sonst der ISO-Code („USD“)."""
    w = (waehrung or "EUR").upper()
    return "€" if w == "EUR" else w


def betrag(d: Decimal | None, waehrung: str | None = "EUR") -> str:
    """Geldbetrag im Sichtteil: „1.234,56 €“ bzw. „1.234,56 USD“."""
    s = eur(d)
    return f"{s} {waehrung_zeichen(waehrung)}" if s else ""


def rechtsbuendig_passend(
    c, x, y, text: str, font: str, groesse: float, breite: float, min_groesse: float = 7
):
    """Rechtsbündig in fester Breite zeichnen; Schrift verkleinern statt umbrechen oder überlaufen."""
    g = groesse
    while g > min_groesse and c.stringWidth(text, font, g) > breite:
        g = max(min_groesse, g - 0.5)
    c.setFont(font, g)
    c.drawRightString(x, y, text)
    return g


def summen_zeilen(r: Rechnung) -> list[tuple[str, str]]:
    """Summenblock (Standardlayout und Layoutvorlage). Beträge mit Währungszeichen aus BT-5;
    keine USt-Zeile beim Kleinunternehmer (§ 19 UStG – dort steht nur der Hinweis)."""
    s = r.summen
    w = r.waehrung or "EUR"
    zeilen = []
    if r.zu_abschlaege:  # BG-20/BG-21
        zeilen.append(("Summe Positionen", betrag(s.positionen_netto, w)))
        zeilen += [_za_text(za, waehrung=w) for za in r.zu_abschlaege]
    ku = bool(s.steuerzeilen) and all(
        steuerfaelle.fall_von(z.steuer) == "KU" for z in s.steuerzeilen
    )
    if not ku:  # Kleinunternehmer: nur der Gesamtbetrag
        zeilen.append(("Nettobetrag", betrag(s.netto, w)))
    for z in s.steuerzeilen:
        if steuerfaelle.fall_von(z.steuer) == "KU":
            continue
        zeilen.append((f"USt {menge(z.steuer.satz)} % auf {eur(z.basis)}", betrag(z.betrag, w)))
    zeilen.append(("Gesamtbetrag", betrag(s.brutto, w)))
    if s.vorausbezahlt or s.rundung:  # BT-113/114/115
        if s.vorausbezahlt:
            zeilen.append(("Bereits gezahlt", "−" + betrag(s.vorausbezahlt, w)))
        if s.rundung:
            zeilen.append(("Rundung", betrag(s.rundung, w)))
        zeilen.append(("Zahlbetrag", betrag(s.zahlbar, w)))
    return zeilen


def steuer_texte(r: Rechnung) -> list[str]:
    """Texte unter den Summen: Befreiungsgründe/Hinweise (§ 14 Abs. 4 Nr. 8, § 14a UStG) und bei Fremdwährung
    die Umsatzsteuer in EUR mit Kurs (§ 16 Abs. 6 UStG)."""
    texte = []
    for z in r.summen.steuerzeilen:
        t = z.steuer.befreiungsgrund
        if t and t not in texte:
            texte.append(t)
    kt = steuerfaelle.kurs_text(r)
    if r.summen.ust_steuerwaehrung is not None:
        texte.append(
            f"Umsatzsteuer in EUR: {eur(r.summen.ust_steuerwaehrung)} €"
            + (f" ({kt})" if kt else "")
        )
    elif kt:
        texte.append(kt)
    return texte


def kaeufer_ust_info(r: Rechnung) -> list[tuple[str, str]]:
    """§ 14a UStG: bei Reverse Charge / innergemeinschaftlicher Lieferung die USt-IdNr. des Kunden."""
    if r.kaeufer.ust_id and any(z.steuer.kategorie in ("AE", "K") for z in r.summen.steuerzeilen):
        return [("Ihre USt-IdNr.", r.kaeufer.ust_id)]
    return []


def menge(d: Decimal | None) -> str:
    if d is None:
        return ""
    s = f"{d.normalize():f}"
    return s.replace(".", ",")


def datum(d) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def leistung(r: Rechnung) -> tuple[str, str]:
    """Leistungsdatum (BT-72) oder Leistungszeitraum (BG-14) für den Rechnungskopf."""
    if r.leistungsdatum:
        return "Leistungsdatum", datum(r.leistungsdatum)
    von, bis = r.leistung_von, r.leistung_bis
    if (
        von
        and bis
        and von.day == 1
        and (bis + timedelta(days=1)).day == 1
        and (von.year, von.month) == (bis.year, bis.month)
    ):
        return "Leistungsmonat", von.strftime("%m/%Y")
    if von or bis:
        return "Leistungszeitraum", f"{datum(von)} – {datum(bis)}"
    return "Leistungsdatum", ""


TITEL = {
    "326": "Teilrechnung",
    "380": "Rechnung",
    "381": "Gutschrift",
    "384": "Rechnungskorrektur",
    "386": "Anzahlungsrechnung",
    "389": "Rechnung (Gutschriftverfahren)",
    "875": "Teilrechnung",
    "876": "Teilschlussrechnung",
    "877": "Schlussrechnung",
}  # BT-3 (UNTDID 1001, Auswahl der XRechnung-Codeliste)


TITEL_EN = {
    "326": "partial invoice",
    "380": "invoice",
    "381": "credit note",
    "384": "corrected invoice",
    "386": "prepayment invoice",
    "389": "self-billed invoice",
    "875": "partial invoice",
    "876": "partial final invoice",
    "877": "final invoice",
}
# Feste Sätze im Sichtteil, Sprache wie die Einheiten (Oberfläche bzw. ``sprache``)
_SATZ = {
    "de": {
        "gutschrift": "Der Betrag wird Ihnen gutgeschrieben.",
        "fuss": "Diese {titel} enthält die strukturierten Rechnungsdaten als eingebettete XML-Datei "
        "(ZUGFeRD/Factur-X, Profil EN 16931).",
    },
    "en": {
        "gutschrift": "The amount will be credited to you.",
        "fuss": "This {titel} contains the structured invoice data as an embedded XML file "
        "(ZUGFeRD/Factur-X, profile EN 16931).",
    },
}


def titel(r: Rechnung) -> str:
    return TITEL.get(r.art, "Rechnung")


def ist_gutschrift(r: Rechnung, zahlbar: Decimal) -> bool:
    """Gutschrift (381) oder Korrektur (384) mit negativem Betrag: kein Zahlungsziel, keine Überweisungsbitte."""
    return r.art == "381" or (r.art == "384" and zahlbar < 0)


def gutschrift_zahlung_setzen(r: Rechnung) -> None:
    """Gutschrift (Typ 381): kein Fälligkeitsdatum (BT-9); Zahlungsbedingungen (BT-20) = Gutschrift-Satz
    wie im Sichtteil, damit XML und sichtbarer Teil dieselben Angaben tragen (ZUGFeRD 2.x Teil A)."""
    if r.art != "381":
        return
    text = satz("gutschrift", r, "de")
    z = r.zahlung
    if z.faellig is None and z.ziel_tage is None and z.bedingungen == text:
        return
    r.zahlung = copy.copy(z)
    r.zahlung.faellig = None
    r.zahlung.ziel_tage = None
    r.zahlung.bedingungen = text


def satz(schluessel: str, r: Rechnung, sprache: str | None = None) -> str:
    sp = "en" if _sprache(sprache) == "en" else "de"
    t = TITEL_EN.get(r.art, "invoice") if sp == "en" else titel(r)
    return _SATZ[sp][schluessel].format(titel=t)


def _za_text(
    za, vorzeichen: bool = True, sprache: str | None = None, waehrung: str | None = "EUR"
) -> tuple[str, str]:
    """Zu-/Abschlag als („Rabatt 10 % – Grund“, „−12,34 €“). ``sprache="en"``: „Discount“/„Charge“ (nur die
    Unterzeilen der Positionen; ohne ``sprache`` wie bisher deutsch)."""
    en = sprache == "en"
    art = ("Charge" if en else "Zuschlag") if za.zuschlag else ("Discount" if en else "Rabatt")
    allgemein = ("rabatt", "zuschlag", "discount", "charge", art.lower())
    grund = "" if za.grund.strip().lower() in allgemein else za.grund
    teile = [art + (f" {menge(za.prozent)} %" if za.prozent is not None else ""), grund]
    wert = betrag(za.ist_betrag, waehrung)
    return " – ".join(t for t in teile if t), (
        ("+" if za.zuschlag else "−") + wert
    ) if vorzeichen else wert


# Unterzeilen einer Position (ab 0.9.5): Präfixe je Sprache
_UZ = {
    "de": {
        "art": "Art.-Nr.",
        "kunde_art": "Ihre Art.-Nr.",
        "zeichnung": "Zeichnungs-Nr.",
        "index": "Index",
        "gtin": "GTIN",
        "std": "Standard-ID",
        "beschreibung": "Beschreibung:",
        "ursprung": "Ursprungsland:",
        "bestellpos": "Bestellpos.",
        "kostenstelle": "Kostenstelle:",
        "objekt": "Objekt:",
        "zeitraum": "Leistungszeitraum:",
        "ab": "ab",
        "bis": "bis",
        "hinweis": "Hinweis:",
        "listenpreis": "Listenpreis {liste}, Nachlass {nachlass} je Einheit",
        "nachlass": "Preisnachlass {nachlass} je Einheit",
    },
    "en": {
        "art": "Item no.",
        "kunde_art": "Your item no.",
        "zeichnung": "Drawing no.",
        "index": "revision",
        "gtin": "GTIN",
        "std": "Standard ID",
        "beschreibung": "Description:",
        "ursprung": "Country of origin:",
        "bestellpos": "Order line",
        "kostenstelle": "Cost centre:",
        "objekt": "Object:",
        "zeitraum": "Service period:",
        "ab": "from",
        "bis": "until",
        "hinweis": "Note:",
        "listenpreis": "List price {liste}, discount {nachlass} per unit",
        "nachlass": "Price discount {nachlass} per unit",
    },
}
# Merkmale (BT-160) mit eigener Zeile in der Identifikation statt „Name: Wert“
MERKMAL_ZEICHNUNG = "zeichnungsnummer"
MERKMAL_INDEX = "index"
UNTERZEILE_PT = 7.5  # Schriftgröße der Unterzeilen bei 9 pt Tabellenschrift
GRAU = (0.4, 0.4, 0.4)


def _ein(t) -> str:
    """Whitespace in einer Zeile zusammenziehen; Zeilenumbrüche und Leerzeilen bleiben (ab 0.9.8)."""
    return "\n".join(" ".join(z.split()) for z in str(t or "").split("\n"))


def unterzeilen(
    p, sprache: str | None = None, sicht: dict | None = None, waehrung: str | None = "EUR"
) -> list[tuple[str, bool]]:
    """Belegte Zusatzangaben einer Position als Unterzeilen unter der Bezeichnung -> [(Text, grau)].

    Reihenfolge: Kommentarzeilen (ohne Vorsatz „Beschreibung:“) direkt unter der Position;
    danach (a) Identifikation … wie bisher. Der Vorsatz „Beschreibung:“ gilt nur für eine
    eigene Beschreibungsspalte (BT-154), nicht für angehängte Kommentarzeilen."""
    sicht = sicht or {}
    ohne = bool(sicht.get("kommentar_ohne_bezeichnungen"))
    felder = sicht.get("felder") or {}
    sp = "en" if _sprache(sprache) == "en" else "de"
    t = _UZ[sp]
    aus: list[tuple[str, bool]] = []

    def dazu(text: str, grau: bool = False) -> None:
        if text or text == "":  # leerer String = gewollte Leerzeile (ab 0.9.8)
            aus.append((text, grau))

    def sichtbar(key: str, default: bool = True) -> bool:
        d = felder.get(key) or {}
        return bool(d["sichtbar"]) if "sichtbar" in d else default

    def mit_label(pref: str, wert: str, grau: bool = False) -> None:
        if not wert:
            return
        dazu(wert if ohne else f"{pref} {wert}", grau)

    for ztext in getattr(p, "kommentar_unten", None) or []:
        dazu(ztext)

    zeichnung = index = ""
    merkmale = []
    for m in p.merkmale or []:
        name, wert = _ein(m.name), _ein(m.wert)
        if name.casefold() == MERKMAL_ZEICHNUNG and not zeichnung:
            zeichnung = wert
        elif name.casefold() == MERKMAL_INDEX and not index:
            index = wert
        elif wert:
            merkmale.append(f"{name}: {wert}" if name else wert)
    # (a) Identifikation
    if _ein(p.artikelnummer) and sichtbar("BT-155"):
        mit_label(t["art"], _ein(p.artikelnummer), True)
    if _ein(p.kaeufer_artikelnummer) and sichtbar("BT-156"):
        mit_label(t["kunde_art"], _ein(p.kaeufer_artikelnummer), True)
    if zeichnung and index:
        dazu(f"{t['zeichnung']} {zeichnung}, {t['index']} {index}", True)
    elif zeichnung:
        dazu(f"{t['zeichnung']} {zeichnung}", True)
    elif index:
        dazu(f"{t['index'][:1].upper()}{t['index'][1:]} {index}", True)
    if _ein(p.standard_id):
        art = t["gtin"] if (p.standard_schema or "0160").strip() in ("", "0160") else t["std"]
        dazu(f"{art} {_ein(p.standard_id)}", True)
    # (b) Beschreibung, Merkmale, Ursprung
    beschr = _ein(p.beschreibung)
    if beschr and beschr != _ein(p.bezeichnung):
        teile = beschr.split("\n")
        while teile and teile[0] == "":
            teile.pop(0)
        erste = True
        for teil in teile:
            if erste and teil:
                dazu(f"{t['beschreibung']} {teil}")
                erste = False
            else:
                dazu(teil)  # auch leer: gewollte Leerzeile auf der Sichtseite
    for m in merkmale:
        dazu(m)
    if _ein(p.ursprungsland):
        dazu(f"{t['ursprung']} {_ein(p.ursprungsland)}")
    # (c) Zuordnung beim Kunden
    if _ein(p.bestellposition):
        dazu(f"{t['bestellpos']} {_ein(p.bestellposition)}")
    if _ein(p.buchungsreferenz):
        dazu(f"{t['kostenstelle']} {_ein(p.buchungsreferenz)}")
    if _ein(p.objektkennung):
        dazu(f"{t['objekt']} {_ein(p.objektkennung)}")
    von, bis = p.leistung_von, p.leistung_bis
    if von and bis:
        dazu(f"{t['zeitraum']} {datum(von)} – {datum(bis)}")
    elif von:
        dazu(f"{t['zeitraum']} {t['ab']} {datum(von)}")
    elif bis:
        dazu(f"{t['zeitraum']} {t['bis']} {datum(bis)}")
    # (d) Hinweis
    if _ein(p.notiz):
        dazu(f"{t['hinweis']} {_ein(p.notiz)}")
    # (e) Preis: Listenpreis/Nachlass, Rabatt/Zuschlag
    if p.preisrabatt:
        dazu(
            t["listenpreis"].format(liste=eur(p.bruttopreis), nachlass=eur(p.preisrabatt))
            if p.bruttopreis is not None
            else t["nachlass"].format(nachlass=eur(p.preisrabatt))
        )
    for a, b in (_za_text(za, sprache=sp, waehrung=waehrung) for za in p.zu_abschlaege):
        dazu(f"{a}: {b}")
    return aus


def _umbrechen_fuellend(c, text: str, font: str, groesse: float, breite: float) -> list[str]:
    """Wie ``umbrechen``, aber ein Wort, das auch allein nicht in eine Zeile passt (lange Artikelnummer), beginnt
    direkt hinter dem Präfix und wird hart umbrochen – „Art.-Nr.“ steht so nie allein in einer Zeile.

    Explizite Zeilenumbrüche und leere Zeilen bleiben erhalten (ab 0.9.8).
    """
    if "\n" in str(text or ""):
        aus: list[str] = []
        for teil in str(text or "").split("\n"):
            if teil == "":
                aus.append("")
            else:
                aus.extend(_umbrechen_fuellend(c, teil, font, groesse, breite))
        return aus or [""]
    zeilen: list[str] = []
    akt = ""
    for wort in (text or "").split():
        probe = f"{akt} {wort}".strip()
        if c.stringWidth(probe, font, groesse) <= breite:
            akt = probe
            continue
        if c.stringWidth(wort, font, groesse) <= breite:
            zeilen.append(akt)
            akt = wort
            continue
        rest = wort
        while rest:
            vor = f"{akt} " if akt else ""
            n = len(rest)
            while n > 1 and c.stringWidth(vor + rest[:n], font, groesse) > breite:
                n -= 1
            if c.stringWidth(vor + rest[:n], font, groesse) > breite and akt:
                zeilen.append(akt)  # nicht einmal ein Zeichen passt noch dahinter
                akt = ""
                continue
            if n < len(
                rest
            ):  # lieber hinter einem Bindestrich/Schrägstrich trennen, wenn das nicht zu früh ist
                k = max(rest.rfind("-", 0, n), rest.rfind("/", 0, n), rest.rfind(".", 0, n)) + 1
                n = k if k > n // 2 else n
            akt = vor + rest[:n]
            rest = rest[n:]
            if rest:
                zeilen.append(akt)
                akt = ""
    if akt:
        zeilen.append(akt)
    return zeilen or [""]


def unterzeilen_umbrochen(
    c,
    p,
    sprache: str | None,
    font: str,
    groesse: float,
    breite: float,
    sicht: dict | None = None,
    waehrung: str | None = "EUR",
) -> list[tuple[str, bool]]:
    """Unterzeilen auf die Breite der Bezeichnung umbrechen (ohne Zeichenverlust) -> [(Zeile, grau)]."""
    return [
        (z, grau)
        for text, grau in unterzeilen(p, sprache, sicht=sicht, waehrung=waehrung)
        for z in _umbrechen_fuellend(c, text, font, groesse, breite)
    ]


def erzeugen(
    r: Rechnung, sprache: str | None = None, vorlage=None, bericht: list[str] | None = None
) -> bytes:
    """Sichtteil als PDF. Ohne ``vorlage`` (``layout.Vorlage``) das feste Standardlayout – unverändert wie bis
    0.6.2; mit Vorlage frei angeordnete Bausteine (Layouteditor, ``sicht_layout``). ``bericht`` sammelt Hinweise
    (Text passt nicht in den Rahmen, Bild fehlt …). Editor-Vorschau und Ausgabe nutzen beide diese Funktion."""
    if vorlage is not None:
        from .sicht_layout import erzeugen as mit_vorlage

        return mit_vorlage(r, vorlage, sprache, bericht)
    return _erzeugen_standard(r, sprache)


# Abstand des Positions-Gesamtbetrags vom rechten Rand (USt-Spalte). 10 mm lässt
# „123.456,78 €“ in 9 pt zu; zuvor 13 mm, das war für das Zeichen zu knapp.
GESAMT_RECHTS = 10 * mm


def _erzeugen_standard(r: Rechnung, sprache: str | None = None) -> bytes:
    """Sichtteil als PDF. Lange Namen, Anschriften und Bezeichnungen bleiben in ihrer Spalte (kleinere Schrift,
    Zeilenumbruch); Einheiten als Klartext in der Sprache der Oberfläche (``sprache`` überschreibt)."""
    _schriften()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"{titel(r)} {r.nummer}")
    c.setAuthor(r.verkaeufer.name)
    c.setSubject(f"{titel(r)} {r.nummer}")
    c.setCreator("fakturafalter")
    c.setProducer("fakturafalter")
    W, H = A4
    L, R = 20 * mm, W - 20 * mm
    seite = [0]

    ZEILE_INFO = 3.3 * mm  # Folgezeile eines umbrochenen Werts im Infoblock
    REF_NAMEN = ("Projekt", "Vertrag", "Lieferschein", "Auftrag", "Ihre Kostenstelle")
    INFO_X = 125 * mm  # rechter Infoblock; links davon bleibt alles in seiner Spalte
    LINKS_BREITE = INFO_X - L - 5 * mm

    def kopf():
        seite[0] += 1
        v = r.verkaeufer
        g, zs = einpassen(c, [v.name], "ER-Sans-Bold", 16, R - L, 11, max_zeilen=2)
        c.setFont("ER-Sans-Bold", g)
        for i, z in enumerate(zs):
            c.drawString(L, H - 25 * mm + (len(zs) - 1 - i) * g * 0.42 * mm, z)
        g, zs = einpassen(
            c,
            [f"{v.anschrift.strasse} · {v.anschrift.plz} {v.anschrift.ort}"],
            "ER-Sans",
            9,
            R - L,
            7,
            max_zeilen=1,
        )
        c.setFont("ER-Sans", g)
        c.drawString(L, H - 31 * mm, zs[0])
        y0 = H - 50 * mm
        if seite[0] == 1:
            g, zs = einpassen(
                c,
                [f"{v.name}, {v.anschrift.strasse}, {v.anschrift.plz} {v.anschrift.ort}"],
                "ER-Sans",
                7,
                LINKS_BREITE,
                5.5,
                max_zeilen=1,
            )
            c.setFont("ER-Sans", g)
            c.drawString(L, y0 + 6 * mm, zs[0])
            k = r.kaeufer
            g, zs = einpassen(
                c,
                [
                    t
                    for t in (
                        *k.namenszeilen(),  # Kundenbezeichnung 1–3 je eine Zeile (sonst der Name)
                        k.kontakt_name,
                        k.anschrift.zusatz,
                        k.anschrift.zeile3,
                        k.anschrift.strasse,
                    )
                    if t
                ]
                + [f"{k.anschrift.plz} {k.anschrift.ort}"],
                "ER-Sans",
                10,
                LINKS_BREITE,
                8,
                max_zeilen=8,
            )
            c.setFont("ER-Sans", g)
            for i, z in enumerate(zs):
                c.drawString(L, y0 - i * g * 0.5 * mm, z)
        info = [
            ("Rechnungsnr." if r.art == "380" else "Belegnr.", r.nummer),
            ("Datum", datum(r.datum)),
        ]
        for b in r.bezuege[:2]:  # BG-3
            info.append(("Zu Rechnung", b.nummer + (f" vom {datum(b.datum)}" if b.datum else "")))
        if r.kundennummer:
            info.append(("Kunden-Nr.", r.kundennummer))
        info += kaeufer_ust_info(r)
        info.append(leistung(r))
        if r.bestellnummer:
            info.append(("Ihre Bestellung", r.bestellnummer))
        if r.leitweg_id:
            info.append(("Leitweg-ID", r.leitweg_id))
        ref = r.referenzen
        for a, b in (
            ("Projekt", ref.projekt),
            ("Vertrag", ref.vertrag),
            ("Lieferschein", ref.lieferschein),
            ("Auftrag", ref.auftrag),
            ("Ihre Kostenstelle", ref.buchung),
        ):
            if b and len(info) < 10:  # Infoblock (mit „Seite“) endet über dem Titel
                info.append((a, b))
        info.append(("Seite", str(seite[0])))
        wert_b = R - 155 * mm

        def wert(b: str, max_zeilen: int) -> tuple[float, list[str]]:
            """Passt der Wert bei 6 pt in eine Zeile, bleibt alles wie bisher. Sonst umbrechen (z. B. lange
            Bestellnummer), statt mit „…“ abzuschneiden."""
            if c.stringWidth(b, "ER-Sans", 6) <= wert_b or max_zeilen == 1:
                return einpassen(c, [b], "ER-Sans", 9, wert_b, 6, max_zeilen=1)
            zs = umbrechen(c, b, "ER-Sans", 8, wert_b)
            if len(zs) <= max_zeilen:
                return 8, zs
            return einpassen(c, [b], "ER-Sans", 6, wert_b, 6, max_zeilen=max_zeilen)

        def hoehe(liste, max_zeilen) -> float:
            return sum(
                4.5 * mm + (len(wert(b or "", max_zeilen)[1]) - 1) * ZEILE_INFO for _a, b in liste
            )

        platz = 10 * 4.5 * mm  # Infoblock (mit „Seite“) endet über dem Titel
        max_z = 4
        while hoehe(info, max_z) > platz + 0.01:
            optional = [i for i, (a, _b) in enumerate(info) if a in REF_NAMEN]
            if optional:
                del info[optional[-1]]
            elif max_z > 1:
                max_z -= 1
            else:
                break
        y = y0 + 6 * mm
        for a, b in info:
            c.setFont("ER-Sans", 9)
            c.drawString(INFO_X, y, a + ":")
            g, zs = wert(b or "", max_z)
            c.setFont("ER-Sans", g)
            for j, z in enumerate(zs):
                c.drawString(155 * mm, y - j * ZEILE_INFO, z)
            y -= 4.5 * mm + (len(zs) - 1) * ZEILE_INFO
        fuss()
        return H - 95 * mm

    def fuss():
        v, z = r.verkaeufer, r.zahlung

        def teile(
            *t: str,
        ) -> str:  # leere Angaben weglassen (kein „Kontakt: · ·“, kein nacktes „IBAN“)
            return " · ".join(x.strip() for x in t if x and x.strip())

        iban = " ".join(z.iban[i : i + 4] for i in range(0, len(z.iban or ""), 4))
        kontakt = teile(v.kontakt_name, v.kontakt_telefon, v.kontakt_email)
        zeilen = [
            teile(v.name, v.anschrift.strasse, f"{v.anschrift.plz} {v.anschrift.ort}", v.register),
            teile(
                f"USt-IdNr. {v.ust_id}" if v.ust_id else "",
                f"Steuernr. {v.steuernummer}" if v.steuernummer else "",
                f"IBAN {iban}" if iban else "",
                f"BIC {z.bic}" if z.bic else "",
            ),
            f"Kontakt: {kontakt}" if kontakt else "",
        ]
        zeilen = [t for t in zeilen if t]
        for i, t in enumerate(zeilen):
            g, zs = einpassen(c, [t], "ER-Sans", 7, R - L, 5.5, max_zeilen=1)
            c.setFont("ER-Sans", g)
            c.drawString(L, 18 * mm - i * 3.5 * mm, zs[0])

    def tabellenkopf(y):
        c.setFont("ER-Sans-Bold", 9)
        koepfe = [
            (L, feld_titel(r, "BT-126", "Pos"), False, "BT-126"),
            (L + 10 * mm, feld_titel(r, "BT-153", "Bezeichnung"), False, "BT-153"),
            (L + 105 * mm, feld_titel(r, "BT-129", "Menge"), True, "BT-129"),
            (L + 107 * mm, feld_titel(r, "BT-130", "Einh."), False, "BT-130"),
            (L + 140 * mm, feld_titel(r, "BT-146", "Einzelpreis"), True, "BT-146"),
            (R - GESAMT_RECHTS, feld_titel(r, "gesamt", "Gesamt"), True, "gesamt"),
            (R, feld_titel(r, "steuer", "USt"), True, "steuer"),
        ]
        for x, txt, rechts, key in koepfe:
            if key == "BT-126" and not feld_sichtbar(r, "BT-126"):
                continue
            (c.drawRightString if rechts else c.drawString)(x, y, txt)
        c.line(L, y - 1.5 * mm, R, y - 1.5 * mm)
        return y - 6 * mm

    y = kopf()
    c.setFont("ER-Sans-Bold", 13)
    c.drawString(L, y, titel(r))
    y = tabellenkopf(y - 9 * mm)
    BEZ_X = L + 10 * mm  # Bezeichnung ab L+10 mm (ab 0.9.5 keine eigene Art.-Nr.-Spalte mehr)
    BEZ_BREITE = 76 * mm  # bis vor die Mengenspalte (rechter Rand unverändert)
    PREIS_BREITE = 25 * mm  # Einzelpreis rechtsbündig bis L+140 mm, links bis hinter „Einh.“
    for p in r.positionen:
        bez = umbrechen(c, p.bezeichnung, "ER-Sans", 9, BEZ_BREITE)
        pg, preis = einpassen(
            c,
            [preis_text(p.einzelpreis, p.preiseinheit, p.einheit, sprache, r.waehrung)],
            "ER-Sans",
            9,
            PREIS_BREITE,
            7,
        )
        # Unterzeilen (Art.-Nr., Zeichnung, Beschreibung, …, Rabatt), umbrochen, nie abgeschnitten
        extra = unterzeilen_umbrochen(
            c,
            p,
            sprache,
            "ER-Sans",
            UNTERZEILE_PT,
            BEZ_BREITE,
            sicht=sicht_von(r),
            waehrung=r.waehrung,
        )
        davor: list[str] = []
        for ztext in getattr(p, "zeilen_davor", None) or []:
            if ztext == "":
                davor.append("")
            else:
                davor.extend(umbrechen(c, ztext, "ER-Sans", 9, BEZ_BREITE) or [ztext])
        hoehe = max(len(davor) + len(bez) + len(extra), len(preis))
        if y - (hoehe - 1) * 4 * mm < 45 * mm:
            c.showPage()
            y = tabellenkopf(kopf())
        c.setFont("ER-Sans", 9)
        for i, z in enumerate(davor):
            if z:
                c.drawString(BEZ_X, y - i * 4 * mm, z)
        y_p = y - len(davor) * 4 * mm
        if feld_sichtbar(r, "BT-126"):
            c.drawString(L, y_p, p.nr)
        for i, z in enumerate(bez):
            c.drawString(BEZ_X, y_p - i * 4 * mm, z)
        if extra:
            c.setFont("ER-Sans", UNTERZEILE_PT)
            for i, (z, grau) in enumerate(extra, len(bez)):
                c.setFillColorRGB(*(GRAU if grau else (0, 0, 0)))
                c.drawString(BEZ_X, y_p - i * 4 * mm, z)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("ER-Sans", 9)
        c.drawRightString(L + 105 * mm, y_p, menge_anzeige(p, r))
        c.drawString(L + 107 * mm, y_p, einheit_anzeige(p, r, sprache))
        rechtsbuendig_passend(
            c,
            R - GESAMT_RECHTS,
            y_p,
            betrag(p.netto, r.waehrung),
            "ER-Sans",
            9,
            (R - GESAMT_RECHTS) - (L + 140 * mm),
        )
        c.setFont("ER-Sans", 9)
        c.drawRightString(R, y_p, f"{menge(p.steuer.satz)} %")
        c.setFont("ER-Sans", pg)
        for i, z in enumerate(preis):  # BT-149
            c.drawRightString(L + 140 * mm, y_p - i * 4 * mm, z)
        y -= 5 * mm + (hoehe - 1) * 4 * mm
    if y < 75 * mm + 5 * mm * (len(r.zu_abschlaege) + 3):
        c.showPage()
        y = kopf()
    s = r.summen
    c.line(L + 100 * mm, y, R, y)
    y -= 5 * mm
    zeilen = summen_zeilen(r)
    for i, (a, b) in enumerate(zeilen):
        a = a if len(a) <= 40 else a[:39] + "…"  # langer Rabattgrund bleibt links vom Betrag
        c.setFont(
            "ER-Sans-Bold" if i == len(zeilen) - 1 else "ER-Sans", 10 if i == len(zeilen) - 1 else 9
        )
        c.drawString(L + 100 * mm, y, a)
        c.drawRightString(R, y, b)
        y -= 5 * mm
    y -= 4 * mm
    c.setFont("ER-Sans", 9)
    for t in steuer_texte(r):
        for zt in umbrechen(c, t, "ER-Sans", 9, R - L):
            c.drawString(L, y, zt)
            y -= 4.5 * mm
    gutschrift = ist_gutschrift(r, s.zahlbar)
    if r.zahlung.bedingungen and not gutschrift:
        # Text wie gedruckt; „Fällig am“ nur, wenn das Netto-Datum eindeutig ist und nicht schon im Text steht
        f = r.zahlung.faellig
        txt = r.zahlung.bedingungen + (
            f" Fällig am {datum(f)}."
            if f and not zahlungsziel.datum_im_text(f, r.zahlung.bedingungen)
            else ""
        )
        g, zs = einpassen(c, [txt], "ER-Sans", 9, R - L, 8, max_zeilen=4)
        c.setFont("ER-Sans", g)
        for t in zs:
            c.drawString(L, y, t)
            y -= 4.5 * mm
        c.setFont("ER-Sans", 9)
    z = r.zahlung
    if gutschrift:
        zsatz = satz("gutschrift", r, sprache)
    elif z.art == "59" or z.mandat:  # BG-19
        konto = f" von Ihrem Konto IBAN …{z.lastschrift_iban[-4:]}" if z.lastschrift_iban else ""
        zsatz = (
            f"Der Betrag wird per SEPA-Lastschrift{konto} eingezogen (Mandatsreferenz {z.mandat}"
            + (f", Gläubiger-ID {z.glaeubiger_id}" if z.glaeubiger_id else "")
            + ")."
        )
    elif s.zahlbar <= 0:
        zsatz = ""
    else:
        zsatz = f"Bitte überweisen Sie unter Angabe der Rechnungsnummer {r.nummer}."
    lf = r.lieferung
    an = lf.anschrift
    lieferung = ", ".join(t for t in (lf.name, an.strasse, f"{an.plz} {an.ort}".strip()) if t)
    for t in ([zsatz] if zsatz else []) + ([f"Lieferanschrift: {lieferung}"] if lieferung else []):
        g, zs = einpassen(c, [t], "ER-Sans", 9, R - L, 7, max_zeilen=2)
        c.setFont("ER-Sans", g)
        for u in zs:
            c.drawString(L, y, u)
            y -= 4.5 * mm
    y -= 3.5 * mm
    c.setFont("ER-Sans", 7)
    g, zs = einpassen(c, [satz("fuss", r, sprache)], "ER-Sans", 7, R - L, 6, max_zeilen=2)
    c.setFont("ER-Sans", g)
    for u in zs:
        c.drawString(L, y, u)
        y -= 3.5 * mm
    c.showPage()
    c.save()
    return buf.getvalue()
