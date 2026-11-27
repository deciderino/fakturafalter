# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Sichtteil nach einer Layout-Vorlage (``layout.Vorlage``) – derselbe Renderer für Editor-Vorschau und Ausgabe.

Zeichenreihenfolge je Seite: Briefpapier ganz unten, dann Logo, Zahlung/Bank, Hinweise und eigene Felder nach
ihrer Ebene, zuletzt die Pflichtbausteine (§ 14 Abs. 4 UStG) – die kann nichts verdecken. Pflichtangaben werden
nie abgeschnitten: Passt ein Text nicht, wird die Schrift bis 6 pt kleiner, danach läuft er über den Rahmen
hinaus und ``bericht`` bekommt einen Hinweis. Die Positionstabelle bricht auf Folgeseiten um (Kopf wiederholt,
Übertrag unten und oben). Briefpapier als PDF wird mit pikepdf unter die Seite gelegt, als Bild gezeichnet.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from . import layout as lay
from . import platzhalter, zahlungsziel
from .modell import Rechnung
from .sicht import (
    GESAMT_RECHTS,
    GRAU,
    UNTERZEILE_PT,
    _schriften,
    betrag,
    datum,
    einheit_anzeige,
    einpassen,
    feld_sichtbar,
    feld_titel,
    ist_gutschrift,
    kaeufer_ust_info,
    leistung,
    menge,
    menge_anzeige,
    preis_text,
    rechtsbuendig_passend,
    satz,
    sicht_von,
    steuer_texte,
    summen_zeilen,
    titel,
    umbrechen,
    unterzeilen_umbrochen,
)

W, H = A4
PT = 25.4 / 72  # 1 pt in mm
ZEILE = 1.2  # Zeilenabstand als Vielfaches der Schriftgröße
MIN_PT = 6.0
F, FB = "ER-Sans", "ER-Sans-Bold"
SKONTO = re.compile(r"skonto|\d+(?:[.,]\d+)?\s*%", re.I)


@dataclass
class Zeile:
    text: str
    fett: bool = False
    faktor: float = 1.0  # relativ zur Schriftgröße des Bausteins


def _y(top_mm: float) -> float:
    return H - top_mm * mm


def _ausgerichtet(
    c, x0: float, breite: float, y: float, text: str, font: str, g: float, ausr: str
) -> None:
    c.setFont(font, g)
    if ausr == "rechts":
        c.drawRightString(x0 + breite, y, text)
    elif ausr == "mitte":
        c.drawCentredString(x0 + breite / 2, y, text)
    else:
        c.drawString(x0, y, text)


def _umbrochen(zeilen: list[Zeile], g: float, breite: float) -> list[tuple[str, str, float]]:
    out = []
    for z in zeilen:
        font, gg = (FB if z.fett else F), g * z.faktor
        for t in umbrechen(_Breite, z.text, font, gg, breite):
            out.append((t, font, gg))
    return out


class _Breite:  # Ersatz für den Canvas in ``umbrechen`` (nur stringWidth)
    stringWidth = staticmethod(stringWidth)


def _textblock(
    c, e: lay.Element, zeilen: list[Zeile], bericht: list[str] | None, kuerzen: bool = False
) -> None:
    """Zeilen in den Rahmen: umbrechen, Schrift bis 6 pt verkleinern. ``kuerzen`` (nur freie Felder): was dann
    noch nicht passt, entfällt; sonst (Pflichtangaben) läuft der Text über den Rahmen hinaus."""
    zeilen = [z for z in zeilen if z.text]
    if not zeilen:
        return
    breite, hoehe = e.breite * mm, e.hoehe * mm
    g = e.schrift
    while True:
        teile = _umbrochen(zeilen, g, breite)
        noetig = sum(gg * ZEILE for _t, _f, gg in teile) * PT * mm
        if noetig <= hoehe + 0.01 or g <= MIN_PT:
            break
        g = max(MIN_PT, g - 0.5)
    if noetig > hoehe + 0.01 and bericht is not None:
        bericht.append(
            f"{lay.NAMEN.get(e.art, e.art)}: Text passt nicht in den Rahmen"
            + (" (gekürzt)" if kuerzen else " (läuft darüber hinaus)")
        )
    unten = _y(e.y + e.hoehe)
    y = _y(e.y) - teile[0][2] * 0.82 * PT * mm
    for i, (t, font, gg) in enumerate(teile):
        if i:
            y -= (teile[i - 1][2] * (ZEILE - 0.82) + gg * 0.82) * PT * mm
        if kuerzen and y - gg * 0.2 * PT * mm < unten - 0.01:
            break
        _ausgerichtet(c, e.x * mm, breite, y, t, font, gg, e.ausrichtung)


def _bild(c, e: lay.Element, pfad, bericht: list[str] | None) -> None:
    if pfad is None:
        return
    try:
        im = lay.bild_laden(pfad)
    except Exception as ex:  # noqa: BLE001
        if bericht is not None:
            bericht.append(
                f"{lay.NAMEN.get(e.art, e.art)}: Bild nicht lesbar ({pfad.name}: {type(ex).__name__})"
            )
        return
    b, h = im.size
    s = min(e.breite / b, e.hoehe / h)
    bw, bh = b * s, h * s
    x = e.x + {"rechts": e.breite - bw, "mitte": (e.breite - bw) / 2}.get(e.ausrichtung, 0)
    c.drawImage(
        ImageReader(im),
        x * mm,
        _y(e.y + bh),
        bw * mm,
        bh * mm,
        mask="auto" if im.mode == "RGBA" else None,
    )


# ---------------------------------------------------------------- Inhalte der Bausteine
def _teile(*t: str) -> str:
    return " · ".join(x.strip() for x in t if x and x.strip())


_ALLE = ("name", "anschrift", "ust_id", "steuernummer", "register", "bank", "kontakt", "ruecksendezeile")


def _absender(r: Rechnung, angaben=_ALLE) -> list[Zeile]:
    v = r.verkaeufer
    out = []
    if "name" in angaben:
        out.append(Zeile(v.name, True, 16 / 9))
    if "anschrift" in angaben:
        out.append(Zeile(_teile(v.anschrift.strasse, f"{v.anschrift.plz} {v.anschrift.ort}")))
    return out


def _empfaenger(r: Rechnung, ruecksendezeile: bool = True) -> list[Zeile]:
    v, k = r.verkaeufer, r.kaeufer
    ruecksende = f"{v.name}, {v.anschrift.strasse}, {v.anschrift.plz} {v.anschrift.ort}"
    return (
        ([Zeile(ruecksende, False, 0.7)] if ruecksendezeile else [])
        + [
            Zeile(t)
            for t in (
                *k.namenszeilen(),  # Kundenbezeichnung 1–3 je eine Zeile (sonst der Name)
                k.kontakt_name,
                k.anschrift.zusatz,
                k.anschrift.zeile3,
                k.anschrift.strasse,
            )
            if t
        ]
        + [Zeile(f"{k.anschrift.plz} {k.anschrift.ort}")]
    )


def _kopf_info(r: Rechnung, seite: int, seiten: int, kurz: bool) -> list[tuple[str, str]]:
    info = [("Rechnungsnr." if r.art == "380" else "Belegnr.", r.nummer), ("Datum", datum(r.datum))]
    if not kurz:
        for b in r.bezuege[:2]:  # BG-3
            info.append(("Zu Rechnung", b.nummer + (f" vom {datum(b.datum)}" if b.datum else "")))
    if r.kundennummer:
        info.append(("Kunden-Nr.", r.kundennummer))
    info += kaeufer_ust_info(r)
    if not kurz:
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
            if b:
                info.append((a, b))
    info.append(("Seite", f"{seite} von {seiten}"))
    return info


def _kopf(c, e: lay.Element, r: Rechnung, seite: int, seiten: int, bericht) -> None:
    """Titel (BT-3) und zweispaltige Angaben; Werte umbrechen statt abschneiden."""
    info = _kopf_info(r, seite, seiten, kurz=seite > 1)
    breite = e.breite * mm
    lab_b = breite * 0.46
    g = e.schrift
    while True:
        tg = g * 13 / 9
        zeilen = [(a, umbrechen(_Breite, b or "", F, g, breite - lab_b)) for a, b in info]
        noetig = (tg * 1.5 + sum(len(z) for _a, z in zeilen) * g * ZEILE * 1.15) * PT * mm
        if noetig <= e.hoehe * mm + 0.01 or g <= MIN_PT:
            break
        g = max(MIN_PT, g - 0.5)
    if noetig > e.hoehe * mm + 0.01 and bericht is not None:
        bericht.append("Rechnungskopf: Angaben passen nicht in den Rahmen (laufen darüber hinaus)")
    x0 = e.x * mm
    y = _y(e.y) - tg * 0.82 * PT * mm
    tt = einpassen(_Breite, [titel(r)], FB, tg, breite, MIN_PT)[0]
    c.setFont(FB, tt)
    c.drawString(x0, y, titel(r))
    y -= tg * 1.5 * PT * mm
    zh = g * ZEILE * 1.15 * PT * mm
    for a, zs in zeilen:
        ag, al = einpassen(_Breite, [a + ":"], F, g, lab_b - 1 * mm, MIN_PT, max_zeilen=1)
        c.setFont(F, ag)
        c.drawString(x0, y, al[0])
        c.setFont(F, g)
        for z in zs:
            c.drawString(x0 + lab_b, y, z)
            y -= zh


def _summen_zeilen(r: Rechnung) -> list[tuple[str, str]]:
    return summen_zeilen(r)


def _bedingungen(r: Rechnung) -> str:
    if not r.zahlung.bedingungen or ist_gutschrift(r, r.summen.zahlbar):
        return ""
    f = r.zahlung.faellig
    bed = zahlungsziel.klartext_fuer_sicht(r.zahlung.bedingungen)
    if not bed:
        return ""
    return bed + (f" Fällig am {datum(f)}." if f and not zahlungsziel.datum_im_text(f, bed) else "")


def _summen(c, e: lay.Element, r: Rechnung, zusatz: list[str], bericht) -> None:
    """Beträge rechtsbündig, darunter Steuerbefreiungsgründe (§ 14 Abs. 4 Nr. 8) und ggf. die
    Entgeltminderung aus den Zahlungsbedingungen (Nr. 7), wenn „Zahlung / Bank“ ausgeblendet ist."""
    zeilen = _summen_zeilen(r)
    texte = steuer_texte(r) + zusatz
    breite = e.breite * mm
    g = e.schrift
    while True:
        lab_b = breite - max(stringWidth(b, F, g + 1) for _a, b in zeilen) - 3 * mm
        tz = [u for t in texte for u in umbrechen(_Breite, t, F, g, breite)]
        noetig = (
            (len(zeilen) * g * ZEILE * 1.25 + (len(tz) * g * ZEILE + (g * 0.5 if tz else 0)))
            * PT
            * mm
        )
        if noetig <= e.hoehe * mm + 0.01 or g <= MIN_PT:
            break
        g = max(MIN_PT, g - 0.5)
    if noetig > e.hoehe * mm + 0.01 and bericht is not None:
        bericht.append("Summenblock: Angaben passen nicht in den Rahmen (laufen darüber hinaus)")
    x0 = e.x * mm
    y = _y(e.y) - g * 0.9 * PT * mm
    zh = g * ZEILE * 1.25 * PT * mm
    for i, (a, b) in enumerate(zeilen):
        letzte = i == len(zeilen) - 1
        font, gg = (FB, g + 1) if letzte else (F, g)
        ag, al = einpassen(_Breite, [a], font, gg, max(lab_b, 10 * mm), MIN_PT, max_zeilen=1)
        c.setFont(font, ag)
        c.drawString(x0, y, al[0])
        c.setFont(font, gg)
        c.drawRightString(x0 + breite, y, b)
        y -= zh
    if tz:
        y -= g * 0.5 * PT * mm
        c.setFont(F, g)
        for t in tz:
            c.drawString(x0, y, t)
            y -= g * ZEILE * PT * mm


def _zahlung(r: Rechnung, sprache: str | None) -> list[Zeile]:
    z, s = r.zahlung, r.summen
    out = [Zeile(_bedingungen(r))]
    if ist_gutschrift(r, s.zahlbar):
        out.append(Zeile(satz("gutschrift", r, sprache)))
    elif z.art == "59" or z.mandat:  # BG-19
        konto = f" von Ihrem Konto IBAN …{z.lastschrift_iban[-4:]}" if z.lastschrift_iban else ""
        out.append(
            Zeile(
                f"Der Betrag wird per SEPA-Lastschrift{konto} eingezogen (Mandatsreferenz {z.mandat}"
                + (f", Gläubiger-ID {z.glaeubiger_id}" if z.glaeubiger_id else "")
                + ")."
            )
        )
    elif s.zahlbar > 0:
        out.append(Zeile(f"Bitte überweisen Sie unter Angabe der Rechnungsnummer {r.nummer}."))
    iban = " ".join(z.iban[i : i + 4] for i in range(0, len(z.iban or ""), 4))
    if iban and not (z.art == "59" or z.mandat):
        out.append(
            Zeile(
                _teile(
                    f"IBAN {iban}",
                    f"BIC {z.bic}" if z.bic else "",
                    f"Kontoinhaber {z.kontoinhaber}"
                    if z.kontoinhaber and z.kontoinhaber != r.verkaeufer.name
                    else "",
                )
            )
        )
    return out


def _hinweise(r: Rechnung, sprache: str | None) -> list[Zeile]:
    lf = r.lieferung
    an = lf.anschrift
    lieferung = ", ".join(t for t in (lf.name, an.strasse, f"{an.plz} {an.ort}".strip()) if t)
    return ([Zeile(f"Lieferanschrift: {lieferung}")] if lieferung else []) + [
        Zeile(satz("fuss", r, sprache))
    ]


def _fusszeile(r: Rechnung, mit_bank: bool, angaben=_ALLE) -> list[Zeile]:
    v, z = r.verkaeufer, r.zahlung
    a = set(angaben)
    mit_bank = mit_bank and "bank" in a
    iban = " ".join(z.iban[i : i + 4] for i in range(0, len(z.iban or ""), 4))
    kontakt = _teile(v.kontakt_name, v.kontakt_telefon, v.kontakt_email) if "kontakt" in a else ""
    out = [
        Zeile(
            _teile(
                v.name if "name" in a else "",
                v.anschrift.strasse if "anschrift" in a else "",
                f"{v.anschrift.plz} {v.anschrift.ort}" if "anschrift" in a else "",
                v.register if "register" in a else "",
            )
        ),
        Zeile(
            _teile(
                f"USt-IdNr. {v.ust_id}" if v.ust_id and "ust_id" in a else "",
                f"Steuernr. {v.steuernummer}" if v.steuernummer and "steuernummer" in a else "",
                f"IBAN {iban}" if iban and mit_bank else "",
                f"BIC {z.bic}" if z.bic and mit_bank else "",
            )
        ),
        Zeile(f"Kontakt: {kontakt}" if kontakt else ""),
    ]
    if a >= set(lay.ANGABEN_JE["fusszeile"]):
        return out  # alle Angaben: genau wie bis rc1
    return [x for x in out if x.text]


# ---------------------------------------------------------------- Positionstabelle
# Spalten als Anteil der Tabellenbreite (Standardbreite 170 mm wie im festen Layout)
_SP = {
    "pos": 0,
    "bez": 10,  # bis 0.9.4: 30 (davor die Spalte Art.-Nr., jetzt Unterzeile)
    "menge": 105,
    "einh": 107,
    "preis": 140,
    "gesamt": 157,
    "ust": 170,
}


@dataclass
class _Zeile:
    pos: object
    bez: list[str]
    extra: list[tuple[str, bool]]  # Unterzeilen (Text, grau), schon umbrochen
    preis: list[str]
    pg: float
    hoehe: float  # in pt-Einheiten der Zeichenfläche
    davor: list[str] = field(default_factory=list)  # Kommentar-/Leerzeilen über der Position


def _spalten(e: lay.Element) -> dict[str, float]:
    return {k: e.x * mm + v / 170 * e.breite * mm for k, v in _SP.items()}


def _zeilen_bauen(r: Rechnung, e: lay.Element, sprache) -> list[_Zeile]:
    g = e.schrift
    f = e.breite / 170
    bez_b, preis_b = 76 * mm * f, 25 * mm * f  # bis 0.9.4: 56 mm (Art.-Nr.-Spalte)
    lh = g * 0.44 * mm
    out = []
    for p in r.positionen:
        bez = umbrechen(_Breite, p.bezeichnung, F, g, bez_b)
        pg, preis = einpassen(
            _Breite,
            [preis_text(p.einzelpreis, p.preiseinheit, p.einheit, sprache, r.waehrung)],
            F,
            g,
            preis_b,
            MIN_PT,
        )
        extra = unterzeilen_umbrochen(
            _Breite,
            p,
            sprache,
            F,
            g * UNTERZEILE_PT / 9,
            bez_b,
            sicht=sicht_von(r),
            waehrung=r.waehrung,
        )
        davor: list[str] = []
        for ztext in getattr(p, "zeilen_davor", None) or []:
            if ztext == "":
                davor.append("")
            else:
                davor.extend(umbrechen(_Breite, ztext, F, g, bez_b) or [ztext])
        n = max(len(davor) + len(bez) + len(extra), len(preis))
        out.append(_Zeile(p, bez, extra, preis, pg, lh * n + 1 * mm, davor))
    return out


def _tabellenkopf_hoehe(g: float) -> float:
    return g * 0.44 * mm + 2.5 * mm + 2 * mm


def seiten_aufteilen(r: Rechnung, v: lay.Vorlage, sprache=None) -> list[list[_Zeile]]:
    """Positionen auf Seiten verteilen: Seite 1 nach ihrer Tabelle, danach die Tabelle der Folgeseite.
    Unten bleibt Platz für die Übertragszeile, oben auf Folgeseiten kommt der Übertrag dazu."""
    e1, ef = v.seite1.bausteine["positionen"], v.folgeseite.bausteine["positionen"]
    zeilen = _zeilen_bauen(r, e1, sprache)
    zeilen_f = (
        _zeilen_bauen(r, ef, sprache)
        if (ef.breite, ef.schrift) != (e1.breite, e1.schrift)
        else zeilen
    )
    seiten: list[list[_Zeile]] = [[]]
    e = e1
    rest = e.hoehe * mm - _tabellenkopf_hoehe(e.schrift)
    for i in range(len(zeilen)):
        z = (zeilen if e is e1 else zeilen_f)[i]
        uebertrag = e.schrift * 0.44 * mm + 3 * mm
        letzte = i == len(zeilen) - 1
        if seiten[-1] and z.hoehe + (0 if letzte else uebertrag) > rest:
            seiten.append([])
            e = ef
            z = zeilen_f[i]
            rest = e.hoehe * mm - _tabellenkopf_hoehe(e.schrift) - uebertrag
        seiten[-1].append(z)
        rest -= z.hoehe
    return seiten


def _tabelle(
    c,
    e: lay.Element,
    zeilen: list[_Zeile],
    sprache,
    vortrag: Decimal | None,
    uebertrag: Decimal | None,
    bericht,
    r: Rechnung | None = None,
) -> None:
    g = e.schrift
    sp = _spalten(e)
    rechts = e.x * mm + e.breite * mm
    f = e.breite / 170
    lh = g * 0.44 * mm
    y = _y(e.y) - g * 0.82 * PT * mm
    c.setFont(FB, g)
    titel = {
        "pos": feld_titel(r, "BT-126", "Pos"),
        "bez": feld_titel(r, "BT-153", "Bezeichnung"),
        "menge": feld_titel(r, "BT-129", "Menge"),
        "einh": feld_titel(r, "BT-130", "Einh."),
        "preis": feld_titel(r, "BT-146", "Einzelpreis"),
        "gesamt": feld_titel(r, "gesamt", "Gesamt"),
        "ust": feld_titel(r, "steuer", "USt"),
    }
    for k, txt, r_ in (
        ("pos", titel["pos"], False),
        ("bez", titel["bez"], False),
        ("menge", titel["menge"], True),
        ("einh", titel["einh"], False),
        ("preis", titel["preis"], True),
        ("gesamt", titel["gesamt"], True),
        ("ust", titel["ust"], True),
    ):
        if k == "pos" and not feld_sichtbar(r, "BT-126"):
            continue
        x = rechts - GESAMT_RECHTS * f if k == "gesamt" else sp[k]
        (c.drawRightString if r_ else c.drawString)(x, y, txt)
    c.line(e.x * mm, y - 1.5 * mm, rechts, y - 1.5 * mm)
    y -= lh + 2.5 * mm
    if vortrag is not None:
        c.setFont(F, g)
        c.drawString(sp["bez"], y, "Übertrag")
        rechtsbuendig_passend(
            c,
            rechts - GESAMT_RECHTS * f,
            y,
            betrag(vortrag, r.waehrung if r else "EUR"),
            F,
            g,
            (rechts - GESAMT_RECHTS * f) - sp["preis"],
        )
        y -= lh + 2 * mm
    unten = _y(e.y + e.hoehe)
    for z in zeilen:
        p = z.pos
        c.setFont(F, g)
        for i, txt in enumerate(z.davor):
            if txt:
                c.drawString(sp["bez"], y - i * lh, txt)
        y_p = y - len(z.davor) * lh
        if feld_sichtbar(r, "BT-126"):
            c.drawString(sp["pos"], y_p, p.nr)
        for i, txt in enumerate(z.bez):
            c.drawString(sp["bez"], y_p - i * lh, txt)
        if z.extra:  # Unterzeilen (Art.-Nr., Zeichnung, Beschreibung, …, Rabatt)
            c.setFont(F, g * UNTERZEILE_PT / 9)
            for i, (txt, grau) in enumerate(z.extra, len(z.bez)):
                c.setFillColorRGB(*(GRAU if grau else (0, 0, 0)))
                c.drawString(sp["bez"], y_p - i * lh, txt)
            c.setFillColorRGB(0, 0, 0)
            c.setFont(F, g)
        c.drawRightString(sp["menge"], y_p, menge_anzeige(p, r))
        c.drawString(sp["einh"], y_p, einheit_anzeige(p, r, sprache))
        rechtsbuendig_passend(
            c,
            rechts - GESAMT_RECHTS * f,
            y_p,
            betrag(p.netto, r.waehrung if r else "EUR"),
            F,
            g,
            (rechts - GESAMT_RECHTS * f) - sp["preis"],
        )
        c.setFont(F, g)
        c.drawRightString(rechts, y_p, f"{menge(p.steuer.satz)} %")
        c.setFont(F, z.pg)
        for i, txt in enumerate(z.preis):  # BT-149
            c.drawRightString(sp["preis"], y_p - i * lh, txt)
        y -= z.hoehe
    if y < unten - 0.5 and bericht is not None:
        bericht.append("Positionstabelle: Position höher als der Rahmen (läuft darüber hinaus)")
    if uebertrag is not None:  # unten im Rahmen (Platz hält seiten_aufteilen frei)
        yu = unten + 1.5 * mm
        c.line(e.x * mm, yu + lh + 0.5 * mm, rechts, yu + lh + 0.5 * mm)
        c.setFont(FB, g)
        c.drawString(sp["bez"], yu, "Übertrag")
        rechtsbuendig_passend(
            c,
            rechts - GESAMT_RECHTS * f,
            yu,
            betrag(uebertrag, r.waehrung if r else "EUR"),
            FB,
            g,
            (rechts - GESAMT_RECHTS * f) - sp["preis"],
        )


# ---------------------------------------------------------------- Seite
def _seite(
    c,
    v: lay.Vorlage,
    s: lay.Seite,
    r: Rechnung,
    nr: int,
    seiten: int,
    zeilen: list[_Zeile],
    sprache,
    vortrag,
    uebertrag,
    bericht,
) -> None:
    letzte = nr == seiten
    bp = v.pfad(s.briefpapier)
    if bp is not None and lay.ist_bild(s.briefpapier):
        if bp.exists():
            c.drawImage(ImageReader(lay.bild_laden(bp, max_px=4000)), 0, 0, W, H)
        elif bericht is not None:
            bericht.append(f"Briefpapier fehlt: {bp.name}")
    zahlung_an = s.bausteine["zahlung"].sichtbar
    for e in s.zeichenfolge():
        if not e.sichtbar:
            continue
        if e.art in lay.NUR_LETZTE and not letzte:
            continue
        if e.art == "logo":
            p = v.pfad(v.logo)
            if p is not None and not p.exists():
                bericht is not None and bericht.append(f"Logo fehlt: {p.name}")
            else:
                _bild(c, e, p, bericht)
        elif e.art == "bild":
            p = v.pfad(e.datei)
            if p is not None and not p.exists():
                bericht is not None and bericht.append(f"Bildfeld: Datei fehlt ({p.name})")
            else:
                _bild(c, e, p, bericht)
        elif e.art == "text":
            text = platzhalter.ersetzen(e.text, r)  # {Spalte}/{BT-xx} (rc2), fehlender Wert = leer
            _textblock(c, e, [Zeile(t) for t in text.splitlines()], bericht, kuerzen=True)
        elif e.art == "zahlung":
            _textblock(c, e, _zahlung(r, sprache), bericht, kuerzen=True)
        elif e.art == "hinweise":
            _textblock(c, e, _hinweise(r, sprache), bericht, kuerzen=True)
        elif e.art == "absender":
            zeilen_a = _absender(r, s.gedruckt(e))
            if zeilen_a:
                _textblock(c, e, zeilen_a, bericht)
        elif e.art == "empfaenger":
            if nr == 1:
                _textblock(c, e, _empfaenger(r, "ruecksendezeile" in (e.angaben or ())), bericht)
        elif e.art == "kopf":
            _kopf(c, e, r, nr, seiten, bericht)
        elif e.art == "positionen":
            _tabelle(c, e, zeilen, sprache, vortrag, uebertrag, bericht, r)
        elif e.art == "summen":
            bed = _bedingungen(r)
            zusatz = (
                [bed] if not zahlung_an and bed and SKONTO.search(bed) else []
            )  # § 14 Abs. 4 Nr. 7 UStG
            _summen(c, e, r, zusatz, bericht)
        elif e.art == "fusszeile":
            zeilen_f = _fusszeile(r, mit_bank=not zahlung_an or not letzte, angaben=tuple(s.gedruckt(e)))
            if any(z.text for z in zeilen_f):
                _textblock(c, e, zeilen_f, bericht)


def erzeugen(
    r: Rechnung, v: lay.Vorlage, sprache: str | None = None, bericht: list[str] | None = None
) -> bytes:
    _schriften()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"{titel(r)} {r.nummer}")
    c.setAuthor(r.verkaeufer.name)
    c.setSubject(f"{titel(r)} {r.nummer}")
    c.setCreator("fakturafalter")
    c.setProducer("fakturafalter")
    seiten = seiten_aufteilen(r, v, sprache)
    summe = Decimal("0")
    for i, zeilen in enumerate(seiten, 1):
        vortrag = summe if i > 1 else None
        summe += sum((z.pos.netto or Decimal("0")) for z in zeilen)
        uebertrag = summe if i < len(seiten) else None
        s = v.seite1 if i == 1 else v.folgeseite
        _seite(c, v, s, r, i, len(seiten), zeilen, sprache, vortrag, uebertrag, bericht)
        c.showPage()
    c.save()
    daten = buf.getvalue()
    return _briefpapier_unterlegen(daten, v, len(seiten), bericht)


def _briefpapier_unterlegen(daten: bytes, v: lay.Vorlage, seiten: int, bericht) -> bytes:
    """Briefpapier-PDF (erste Seite) unter jede Seite legen – Seite 1 und Folgeseiten getrennt."""
    pdfs = {
        n: v.pfad(v.seite(n).briefpapier)
        for n in lay.SEITEN
        if v.seite(n).briefpapier and not lay.ist_bild(v.seite(n).briefpapier)
    }
    if not pdfs:
        return daten
    import pikepdf

    pdf = pikepdf.open(io.BytesIO(daten))
    offen = {}
    try:
        for n, p in pdfs.items():
            if not p.exists():
                bericht is not None and bericht.append(f"Briefpapier fehlt: {p.name}")
                continue
            offen[n] = pikepdf.open(p)
        for i, seite in enumerate(pdf.pages):
            bp = offen.get("seite1" if i == 0 else "folgeseite")
            if bp is not None:
                seite.add_underlay(bp.pages[0], pikepdf.Rectangle(0, 0, W, H))
        out = io.BytesIO()
        pdf.save(out, deterministic_id=True)
        return out.getvalue()
    finally:
        for x in offen.values():
            x.close()
        pdf.close()
