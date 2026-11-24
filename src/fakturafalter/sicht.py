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

from . import zahlungsziel
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


def preis_text(
    einzelpreis: Decimal | None,
    preiseinheit: Decimal | None,
    code: str = "",
    sprache: str | None = None,
) -> str:
    """Einzelpreis mit Preiseinheit (BT-149) für den Sichtteil: „3,40“ oder „3,40 € / 10 Stück“."""
    if preiseinheit is None or preiseinheit == 1:
        return eur(einzelpreis)
    return f"{eur(einzelpreis)} € / {menge(preiseinheit)} {einheit_text(code, sprache, lang=True)}".rstrip()


def umbrechen(c, text: str, font: str, groesse: float, breite: float) -> list[str]:
    """Text auf Zeilen von höchstens ``breite`` umbrechen (an Leerzeichen, zu lange Wörter hart)."""
    zeilen: list[str] = []
    akt = ""
    for wort in (text or "").split():
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
    return zeilen or [""]


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
    if d is None:
        return ""
    s = f"{d.quantize(Decimal('0.01')):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


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


def _za_text(za, vorzeichen: bool = True) -> tuple[str, str]:
    """Zu-/Abschlag als („Rabatt 10 % – Grund“, „−12,34“)."""
    art = "Zuschlag" if za.zuschlag else "Rabatt"
    grund = "" if za.grund.strip().lower() in ("rabatt", "zuschlag", art.lower()) else za.grund
    teile = [art + (f" {menge(za.prozent)} %" if za.prozent is not None else ""), grund]
    betrag = eur(za.ist_betrag)
    return " – ".join(t for t in teile if t), (
        ("+" if za.zuschlag else "−") + betrag
    ) if vorzeichen else betrag


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
                        k.name,
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
        for x, t, rechts in [
            (L, "Pos", False),
            (L + 10 * mm, "Art.-Nr.", False),
            (L + 30 * mm, "Bezeichnung", False),
            (L + 105 * mm, "Menge", True),
            (L + 107 * mm, "Einh.", False),
            (L + 140 * mm, "Einzelpreis", True),
            (R - 13 * mm, "Gesamt", True),
            (R, "USt", True),
        ]:
            (c.drawRightString if rechts else c.drawString)(x, y, t)
        c.line(L, y - 1.5 * mm, R, y - 1.5 * mm)
        return y - 6 * mm

    y = kopf()
    c.setFont("ER-Sans-Bold", 13)
    c.drawString(L, y, titel(r))
    y = tabellenkopf(y - 9 * mm)
    BEZ_BREITE = 56 * mm  # Bezeichnung: L+30 mm bis vor die Mengenspalte
    PREIS_BREITE = 25 * mm  # Einzelpreis rechtsbündig bis L+140 mm, links bis hinter „Einh.“
    for p in r.positionen:
        bez = umbrechen(c, p.bezeichnung, "ER-Sans", 9, BEZ_BREITE)
        pg, preis = einpassen(
            c,
            [preis_text(p.einzelpreis, p.preiseinheit, p.einheit, sprache)],
            "ER-Sans",
            9,
            PREIS_BREITE,
            7,
        )
        extra = []  # BT-147/148, BG-27/28
        if p.preisrabatt:
            extra.append(
                f"Listenpreis {eur(p.bruttopreis)}, Nachlass {eur(p.preisrabatt)} je Einheit"
                if p.bruttopreis is not None
                else f"Preisnachlass {eur(p.preisrabatt)} je Einheit"
            )
        extra += [f"{a}: {b}" for a, b in map(_za_text, p.zu_abschlaege)]
        hoehe = max(len(bez) + len(extra), len(preis))
        if y - (hoehe - 1) * 4 * mm < 45 * mm:
            c.showPage()
            y = tabellenkopf(kopf())
        c.setFont("ER-Sans", 9)
        c.drawString(L, y, p.nr)
        c.drawString(L + 10 * mm, y, p.artikelnummer)
        for i, z in enumerate(bez):
            c.drawString(L + 30 * mm, y - i * 4 * mm, z)
        if extra:
            c.setFont("ER-Sans", 7.5)
            for i, z in enumerate(extra, len(bez)):
                g, zs = einpassen(c, [z], "ER-Sans", 7.5, BEZ_BREITE + 20 * mm, 6, max_zeilen=1)
                c.setFont("ER-Sans", g)
                c.drawString(L + 30 * mm, y - i * 4 * mm, zs[0])
            c.setFont("ER-Sans", 9)
        c.drawRightString(L + 105 * mm, y, menge(p.menge))
        c.drawString(L + 107 * mm, y, einheit_text(p.einheit, sprache))
        c.drawRightString(R - 13 * mm, y, eur(p.netto))
        c.drawRightString(R, y, f"{menge(p.steuer.satz)} %")
        c.setFont("ER-Sans", pg)
        for i, z in enumerate(preis):  # BT-149
            c.drawRightString(L + 140 * mm, y - i * 4 * mm, z)
        y -= 5 * mm + (hoehe - 1) * 4 * mm
    if y < 75 * mm + 5 * mm * (len(r.zu_abschlaege) + 3):
        c.showPage()
        y = kopf()
    s = r.summen
    c.line(L + 100 * mm, y, R, y)
    y -= 5 * mm
    zeilen = []
    if r.zu_abschlaege:  # BG-20/BG-21
        zeilen.append(("Summe Positionen", eur(s.positionen_netto)))
        zeilen += [_za_text(za) for za in r.zu_abschlaege]
    zeilen.append(("Nettobetrag", eur(s.netto)))
    for z in s.steuerzeilen:
        zeilen.append((f"USt {menge(z.steuer.satz)} % auf {eur(z.basis)}", eur(z.betrag)))
    zeilen.append(("Gesamtbetrag EUR", eur(s.brutto)))
    if s.vorausbezahlt or s.rundung:  # BT-113/114/115
        if s.vorausbezahlt:
            zeilen.append(("Bereits gezahlt", "−" + eur(s.vorausbezahlt)))
        if s.rundung:
            zeilen.append(("Rundung", eur(s.rundung)))
        zeilen.append(("Zahlbetrag EUR", eur(s.zahlbar)))
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
    for z in s.steuerzeilen:
        if z.steuer.befreiungsgrund:
            c.drawString(L, y, z.steuer.befreiungsgrund)
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
