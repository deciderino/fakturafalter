# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Layout-Vorlage für den neu erzeugten Sichtteil (Layouteditor, seit 0.7.0; Layoutformat 2 ab 1.0.0-rc2).

Eine Vorlage beschreibt zwei A4-Seiten (Seite 1 und Folgeseiten) mit Bausteinen, eigenen Text- und Bildfeldern und
optional einem Briefpapier-PDF als Hintergrund. Gespeichert wird sie als Block ``layout`` in der Konfiguration – beim
aktiven Absender oben in der Datei, bei gemerkten Absendern im jeweiligen Eintrag von ``absender_profile``. Ohne
Block gilt das bisherige feste Layout unverändert (``sicht.erzeugen`` ohne Vorlage).

Maße in mm, Ursprung oben links (wie im Editor). Die XML-Rechnung bleibt davon unberührt.

Layoutformat 2 (1.0.0-rc2):
- Empfänger, Rechnungskopf, Positionen und Summen bleiben ganze Bausteine mit Schloss (``PFLICHT``).
- Absender und Fußzeile sind ausblendbar; je Baustein wählst du die Verkäufer-Angaben (``angaben``), am Briefpapier
  hakst du an, was schon draufsteht (``briefpapier_enthaelt`` – das druckt Fakturafalter auf der Seite nicht noch
  einmal). Die Empfängeranschrift hat einen Schalter für die Rücksendezeile.
- Statt fester Pflichtbausteine prüft :func:`pflicht_pruefen`, ob jede Pflichtangabe nach § 14 Abs. 4 UStG
  mindestens einmal auf der Rechnung steht (fehlend = Fehler, doppelt = Hinweis).
- Layouts im Format 1 (oder ohne Version) werden abgelehnt (:class:`LayoutAlt`), ohne Migration; die Datei bleibt
  unangetastet.
"""
from __future__ import annotations

import copy
import hashlib
import io
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("fakturafalter")

VERSION = 2
SEITE_B, SEITE_H = 210.0, 297.0
BAUSTEINE = ("logo", "absender", "empfaenger", "kopf", "positionen", "summen", "zahlung", "hinweise", "fusszeile")
PFLICHT = frozenset({"empfaenger", "kopf", "positionen", "summen"})  # Schloss: ganze Bausteine, immer sichtbar
OBEN = PFLICHT | {"absender", "fusszeile"}  # liegen über allen freien Ebenen (wie bis rc1)
NAMEN = {"logo": "Logo", "absender": "Absender", "empfaenger": "Empfängeranschrift", "kopf": "Rechnungskopf",
         "positionen": "Positionstabelle", "summen": "Summenblock", "zahlung": "Zahlung / Bank",
         "hinweise": "Hinweise", "fusszeile": "Fußzeile", "text": "Textfeld", "bild": "Bildfeld"}
SEITEN = ("seite1", "folgeseite")
NUR_SEITE1 = frozenset({"empfaenger"})              # auf Folgeseiten nicht nötig
NUR_LETZTE = frozenset({"summen", "zahlung", "hinweise"})   # nur auf der letzten Seite
AUSRICHTUNG = ("links", "mitte", "rechts")
OHNE_AUSRICHTUNG = frozenset({"kopf", "positionen", "summen"})   # Tabellen: Spalten fest
MIN_MASS = 5.0
BILD_ENDUNGEN = (".png", ".jpg", ".jpeg")
ORDNER = "layout"                                   # Bilder/Briefpapier, relativ zur Konfiguration

# Verkäufer-Angaben (Layoutformat 2)
ANGABEN = ("name", "anschrift", "ust_id", "steuernummer", "register", "bank", "kontakt", "ruecksendezeile")
ANGABEN_NAMEN = {"name": "Name", "anschrift": "Anschrift", "ust_id": "USt-IdNr.", "steuernummer": "Steuernummer",
                 "register": "Handelsregister", "bank": "Bank (IBAN/BIC)", "kontakt": "Kontakt",
                 "ruecksendezeile": "Rücksendezeile"}
ANGABEN_JE = {
    "absender": ("name", "anschrift"),
    "empfaenger": ("ruecksendezeile",),
    "fusszeile": ("name", "anschrift", "register", "ust_id", "steuernummer", "bank", "kontakt"),
}
BRIEFPAPIER_ANGABEN = ("name", "anschrift", "ust_id", "steuernummer", "register", "bank", "kontakt")

_SCHLUESSEL_LAYOUT = {"version", "raster", "raster_an", "logo", "seite1", "folgeseite"}
_SCHLUESSEL_SEITE = {"bausteine", "felder", "briefpapier", "briefpapier_enthaelt"}
_SCHLUESSEL_ELEMENT = {"x", "y", "breite", "hoehe", "schrift", "ausrichtung", "sichtbar", "ebene", "text", "datei",
                       "kennung", "art", "angaben"}


@dataclass
class Element:
    art: str                       # Baustein-Schlüssel oder „text“/„bild“ (eigene Felder)
    x: float
    y: float
    breite: float
    hoehe: float
    schrift: float = 9.0
    ausrichtung: str = "links"
    sichtbar: bool = True
    ebene: int = 0                 # nur für freie Bausteine und eigene Felder
    text: str = ""                 # Textfeld (mit Platzhaltern {Spalte}/{BT-xx})
    datei: str = ""                # Bildfeld (relativ zur Konfiguration)
    kennung: str = ""              # eigene Felder: eindeutig je Seite
    angaben: list[str] | None = None   # Absender/Empfänger/Fußzeile: gezeigte Verkäufer-Angaben

    def __post_init__(self) -> None:
        if self.angaben is None and self.art in ANGABEN_JE:
            self.angaben = list(ANGABEN_JE[self.art])

    @property
    def pflicht(self) -> bool:
        """Schloss: ganzer Baustein, immer sichtbar (Empfänger, Kopf, Positionen, Summen)."""
        return self.art in PFLICHT

    @property
    def oben(self) -> bool:
        """Liegt über allen freien Ebenen (Schloss-Bausteine, Absender, Fußzeile)."""
        return self.art in OBEN

    @property
    def eigen(self) -> bool:
        return self.art in ("text", "bild")

    def zeigt(self, angabe: str) -> bool:
        return self.sichtbar and angabe in (self.angaben or ())

    def rahmen(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.x + self.breite, self.y + self.hoehe

    def als_dict(self) -> dict:
        d = {"x": _r(self.x), "y": _r(self.y), "breite": _r(self.breite), "hoehe": _r(self.hoehe)}
        if self.art != "bild" and self.art != "logo":
            d["schrift"] = _r(self.schrift)
            if self.art not in OHNE_AUSRICHTUNG:
                d["ausrichtung"] = self.ausrichtung
        elif self.art in ("bild", "logo"):
            d["ausrichtung"] = self.ausrichtung
        if not self.pflicht:
            d["sichtbar"] = bool(self.sichtbar)
        if not self.oben:
            d["ebene"] = int(self.ebene)
        if self.art in ANGABEN_JE:  # immer vollständig (kein Default-Raten beim nächsten Öffnen)
            d["angaben"] = [a for a in ANGABEN_JE[self.art] if a in (self.angaben or ())]
        if self.eigen:
            d = {"art": self.art, "kennung": self.kennung, **d}
            if self.art == "text":
                d["text"] = self.text
            else:
                d["datei"] = self.datei
        return d


@dataclass
class Seite:
    bausteine: dict[str, Element]
    felder: list[Element] = field(default_factory=list)
    briefpapier: str = ""          # PDF oder (umgewandelt) JPEG/PNG, relativ zur Konfiguration
    briefpapier_enthaelt: list[str] = field(default_factory=list)   # steht schon auf dem Briefpapier

    def elemente(self) -> list[Element]:
        return list(self.bausteine.values()) + list(self.felder)

    def zeichenfolge(self) -> list[Element]:
        """Reihenfolge beim Zeichnen: zuerst freie Bausteine und eigene Felder nach Ebene (stabil), dann
        Absender, Fußzeile und die Schloss-Bausteine – die liegen damit immer oben."""
        frei = [e for e in self.elemente() if not e.oben]
        frei.sort(key=lambda e: e.ebene)
        return frei + [e for e in self.bausteine.values() if e.oben]

    def im_briefpapier(self, angabe: str) -> bool:
        return bool(self.briefpapier) and angabe in self.briefpapier_enthaelt

    def gedruckt(self, e: Element) -> list[str]:
        """Angaben, die der Baustein auf dieser Seite wirklich druckt (ohne das, was das Briefpapier zeigt)."""
        return [a for a in (e.angaben or ()) if not self.im_briefpapier(a)]


@dataclass
class Vorlage:
    seite1: Seite
    folgeseite: Seite
    logo: str = ""                 # Bild des Bausteins „Logo“ (relativ zur Konfiguration)
    raster: float = 5.0
    raster_an: bool = True
    basis: Path | None = None      # Ordner der Konfiguration (für relative Dateien)

    def seite(self, name: str) -> Seite:
        return self.seite1 if name == "seite1" else self.folgeseite

    def pfad(self, datei: str) -> Path | None:
        if not datei:
            return None
        p = Path(datei).expanduser()
        if not p.is_absolute() and self.basis is not None:
            p = self.basis / p
        return p

    def dateien(self) -> list[str]:
        out = [self.logo, self.seite1.briefpapier, self.folgeseite.briefpapier]
        out += [f.datei for s in (self.seite1, self.folgeseite) for f in s.felder if f.art == "bild"]
        return [d for d in out if d]

    def als_dict(self) -> dict:
        d: dict = {"version": VERSION, "raster": _r(self.raster), "raster_an": bool(self.raster_an)}
        if self.logo:
            d["logo"] = self.logo
        for name in SEITEN:
            s = self.seite(name)
            sd: dict = {"bausteine": {k: e.als_dict() for k, e in s.bausteine.items()}}
            if s.felder:
                sd["felder"] = [f.als_dict() for f in s.felder]
            if s.briefpapier:
                sd["briefpapier"] = s.briefpapier
                sd["briefpapier_enthaelt"] = [a for a in BRIEFPAPIER_ANGABEN if a in s.briefpapier_enthaelt]
            d[name] = sd
        return d


def _r(v: float) -> float:
    return round(float(v), 1)


# ---------------------------------------------------------------- Standard
_STANDARD = {
    "seite1": {"logo": (150, 12, 40, 18, 9), "absender": (20, 14, 125, 20, 9), "empfaenger": (20, 42, 95, 40, 10),
               "kopf": (125, 42, 65, 52, 9), "positionen": (20, 100, 170, 120, 9), "zahlung": (20, 224, 85, 34, 9),
               "summen": (110, 224, 80, 34, 9), "hinweise": (20, 260, 170, 12, 7), "fusszeile": (20, 276, 170, 12, 7)},
    "folgeseite": {"logo": (150, 12, 40, 18, 9), "absender": (20, 14, 100, 20, 9), "kopf": (125, 14, 65, 26, 9),
                   "positionen": (20, 46, 170, 174, 9), "zahlung": (20, 224, 85, 34, 9),
                   "summen": (110, 224, 80, 34, 9), "hinweise": (20, 260, 170, 12, 7),
                   "fusszeile": (20, 276, 170, 12, 7)},
}
_STANDARD_EBENE = {"logo": 0, "zahlung": 1, "hinweise": 2}


def standard() -> Vorlage:
    """Startpunkt im Editor: ähnlich dem bisherigen festen Layout, als frei verschiebbare Bausteine (Format 2,
    alle Angaben an – optisch wie rc1)."""
    seiten = {}
    for name, bs in _STANDARD.items():
        seiten[name] = Seite({k: Element(k, *bs[k][:4], schrift=bs[k][4], ebene=_STANDARD_EBENE.get(k, 0))
                              for k in BAUSTEINE if k in bs})
    return Vorlage(seiten["seite1"], seiten["folgeseite"])


# ---------------------------------------------------------------- Laden / Speichern
class LayoutFehler(ValueError):
    """Vorlage unlesbar oder verletzt eine feste Regel (z. B. Pflichtbausteine überlappen)."""


class LayoutAlt(LayoutFehler):
    """Layout im Format 1 (bzw. ohne/mit unbekannter Version): wird abgelehnt, nicht migriert."""

    def __init__(self, gefunden):
        self.gefunden = gefunden
        super().__init__(
            f"Layoutformat {gefunden if gefunden not in (None, '') else 'ohne Angabe'} – dieses Fakturafalter erwartet "
            f"Layoutformat {VERSION}. Bitte das Layout im Layouteditor neu einrichten (die Datei bleibt unverändert)."
        )


ALT_TITEL = "Dieses Layout passt nicht mehr zu Fakturafalter 1.0"
ALT_TEXT = (
    "Das Layout des Absenders „{name}“ wurde mit einer älteren Version eingerichtet ({format}, dieses Fakturafalter "
    "erwartet Layoutformat 2).\n\n"
    "Fakturafalter übernimmt es deshalb nicht – die Pflichtangaben und die Briefpapier-Haken haben sich geändert, "
    "und es gibt keine automatische Übernahme.\n\n"
    "Was du tun kannst:\n\n"
    "• Das Layout im Editor neu einrichten. Dein Briefpapier und deine Bilder liegen weiter im Ordner „layout/“, du "
    "lädst sie dort erneut.\n\n"
    "• Oder bei der Version 0.9.11 bzw. 1.0.0-rc1 bleiben; dort funktioniert das bisherige Layout weiter.\n\n"
    "Die Konfiguration bleibt unverändert."
)


def format_text(gefunden) -> str:
    """„Layoutformat 1“ / „ohne Layoutformat“ – nie nur „Version“ (Verwechslung mit dem Profilformat)."""
    if gefunden in (None, ""):
        return "ohne Layoutformat"
    return f"Layoutformat {gefunden}"


def _zahl(d: dict, k: str, alt: float) -> float:
    try:
        return float(d.get(k, alt))
    except (TypeError, ValueError):
        raise LayoutFehler(f"„{k}“ ist keine Zahl: {d.get(k)!r}") from None


def _unbekannt(d: dict, erlaubt: set, wo: str) -> None:
    fremd = sorted(str(k) for k in d if k not in erlaubt)
    if fremd:
        raise LayoutFehler(f"{wo}: unbekannter Schlüssel {', '.join(fremd)}")


def _element(art: str, d: dict, alt: Element | None) -> Element:
    if not isinstance(d, dict):
        raise LayoutFehler(f"Baustein „{art}“: Angaben fehlen")
    _unbekannt(d, _SCHLUESSEL_ELEMENT, f"Baustein „{art}“")
    a = alt or Element(art, 20, 20, 50, 20)
    angaben = None
    if art in ANGABEN_JE:
        roh = d.get("angaben", list(ANGABEN_JE[art]))
        if not isinstance(roh, list) or any(str(x) not in ANGABEN_JE[art] for x in roh):
            raise LayoutFehler(
                f"Baustein „{art}“: angaben erlaubt nur {', '.join(ANGABEN_JE[art])} (gefunden: {roh!r})"
            )
        angaben = [x for x in ANGABEN_JE[art] if x in {str(y) for y in roh}]
    elif "angaben" in d:
        raise LayoutFehler(f"Baustein „{art}“: hat keine Angaben-Liste")
    e = Element(art, _zahl(d, "x", a.x), _zahl(d, "y", a.y), _zahl(d, "breite", a.breite), _zahl(d, "hoehe", a.hoehe),
                schrift=_zahl(d, "schrift", a.schrift), ausrichtung=str(d.get("ausrichtung", a.ausrichtung)),
                sichtbar=bool(d.get("sichtbar", True)), ebene=int(_zahl(d, "ebene", a.ebene)),
                text=str(d.get("text") or ""), datei=str(d.get("datei") or ""), kennung=str(d.get("kennung") or ""),
                angaben=angaben)
    if e.ausrichtung not in AUSRICHTUNG:
        e.ausrichtung = "links"
    if e.pflicht:
        e.sichtbar = True
    return e


def version_von(d) -> object:
    return d.get("version") if isinstance(d, dict) else None


def aus_dict(d: dict | None, basis: Path | None = None) -> Vorlage | None:
    """Block ``layout`` -> Vorlage; leer/fehlend -> None (= bisheriges festes Layout). Nur Layoutformat 2; ältere
    Layouts -> :class:`LayoutAlt` (keine Migration). Fehlende Bausteine kommen aus dem Standard."""
    if not d:
        return None
    if not isinstance(d, dict):
        raise LayoutFehler("Block „layout“ ist keine Zuordnung")
    ver = d.get("version")
    try:
        ver_i = int(ver)
    except (TypeError, ValueError):
        raise LayoutAlt(ver) from None
    if ver_i > VERSION:
        raise LayoutFehler(f"Layoutformat {ver} ist neuer als dieses Programm (Layoutformat {VERSION})")
    if ver_i < VERSION:
        raise LayoutAlt(ver)
    _unbekannt(d, _SCHLUESSEL_LAYOUT, "Layout")
    std = standard()
    seiten = {}
    for name in SEITEN:
        sd = d.get(name) or {}
        if not isinstance(sd, dict):
            raise LayoutFehler(f"„{name}“ ist keine Zuordnung")
        _unbekannt(sd, _SCHLUESSEL_SEITE, "Seite 1" if name == "seite1" else "Folgeseite")
        bs_roh = sd.get("bausteine") or {}
        fremd = sorted(str(k) for k in bs_roh if k not in BAUSTEINE)
        if fremd:
            raise LayoutFehler(f"Unbekannter Baustein {', '.join(fremd)}")
        bs = {}
        for k in BAUSTEINE:
            alt = std.seite(name).bausteine.get(k)
            if alt is None:
                continue
            bs[k] = _element(k, bs_roh[k], alt) if k in bs_roh else copy.deepcopy(alt)
        felder = []
        for i, f in enumerate(sd.get("felder") or []):
            art = str((f or {}).get("art", ""))
            if art not in ("text", "bild"):
                raise LayoutFehler(f"Eigenes Feld {i + 1}: Art „{art}“ unbekannt (text oder bild)")
            e = _element(art, f, Element(art, 20, 20, 50, 15, schrift=10))
            e.kennung = e.kennung or f"{art}{i + 1}"
            felder.append(e)
        enth = sd.get("briefpapier_enthaelt") or []
        if not isinstance(enth, list) or any(str(x) not in BRIEFPAPIER_ANGABEN for x in enth):
            raise LayoutFehler(
                f"briefpapier_enthaelt erlaubt nur {', '.join(BRIEFPAPIER_ANGABEN)} (gefunden: {enth!r})"
            )
        enth = [a for a in BRIEFPAPIER_ANGABEN if a in {str(x) for x in enth}]
        seiten[name] = Seite(bs, felder, str(sd.get("briefpapier") or ""), enth)
    return Vorlage(seiten["seite1"], seiten["folgeseite"], logo=str(d.get("logo") or ""),
                   raster=_zahl(d, "raster", 5.0), raster_an=bool(d.get("raster_an", True)), basis=basis)


def traegt_pflicht(e: Element) -> bool:
    """Baustein mit Pflichtangaben (darf nicht verdeckt werden): Schloss-Bausteine sowie sichtbare Absender/Fußzeile
    mit mindestens einer Angabe."""
    if e.pflicht:
        return True
    return e.art in ("absender", "fusszeile") and e.sichtbar and bool(e.angaben)


def pruefen(v: Vorlage, t=lambda s: s) -> list[str]:
    """Feste Regeln; leer = in Ordnung. ``t`` übersetzt die Texte (Oberfläche), Standard Deutsch.
    - Alles liegt auf der Seite und ist mindestens 5 mm groß, Schrift 4–40 pt.
    - Die Positionstabelle ist mindestens 120 mm breit und 30 mm hoch (Spalten bleiben lesbar).
    - Bausteine mit Pflichtangaben überlappen sich nicht (sonst wäre eine Pflichtangabe verdeckt/unlesbar).
    Ob jede Pflichtangabe auf der Rechnung steht, prüft :func:`pflicht_pruefen` (braucht das Absenderprofil)."""
    fehler = []
    for name in SEITEN:
        s = v.seite(name)
        titel = t("Seite 1") if name == "seite1" else t("Folgeseite")
        for e in s.elemente():
            n = t(NAMEN.get(e.art, e.art)) + (f" „{e.text[:20]}“" if e.art == "text" and e.text.strip() else "")
            if e.breite < MIN_MASS or e.hoehe < MIN_MASS:
                fehler.append(t("{seite}: {name} ist kleiner als {mm} mm").format(seite=titel, name=n, mm=f"{MIN_MASS:g}"))
            if e.x < -0.05 or e.y < -0.05 or e.x + e.breite > SEITE_B + 0.05 or e.y + e.hoehe > SEITE_H + 0.05:
                fehler.append(t("{seite}: {name} ragt über den Seitenrand").format(seite=titel, name=n))
            if not 4 <= e.schrift <= 40:
                fehler.append(t("{seite}: {name}: Schriftgröße {pt} pt (erlaubt 4–40)").format(
                    seite=titel, name=n, pt=f"{e.schrift:g}"))
        tab = s.bausteine["positionen"]
        if tab.breite < 120 - 0.05 or tab.hoehe < 30 - 0.05:
            fehler.append(t("{seite}: Positionstabelle muss mindestens 120 × 30 mm groß sein").format(seite=titel))
        pfl = [e for e in s.bausteine.values() if traegt_pflicht(e)]
        for i, a in enumerate(pfl):
            for b in pfl[i + 1:]:
                if ueberlappen(a, b):
                    fehler.append(t("{seite}: {a} und {b} überlappen (Pflichtangaben dürfen sich nicht verdecken)")
                                  .format(seite=titel, a=t(NAMEN[a.art]), b=t(NAMEN[b.art])))
    return fehler


# ---------------------------------------------------------------- Pflichtangaben (§ 14 Abs. 4 UStG)
@dataclass
class Pflichtbefund:
    fehler: list[str] = field(default_factory=list)    # blockiert Speichern / Erzeugen
    doppelt: list[str] = field(default_factory=list)   # Hinweis, Speichern möglich
    hinweise: list[str] = field(default_factory=list)  # ruhige Hinweise (z. B. Folgeseite ohne Verkäufer)

    @property
    def ok(self) -> bool:
        return not self.fehler


_ANGABE_SATZ = {
    "name": "Der Verkäufername",
    "anschrift": "Die Anschrift des Verkäufers",
    "steuer": "Die USt-IdNr. bzw. Steuernummer",
    "ust_id": "Die USt-IdNr.",
    "steuernummer": "Die Steuernummer",
    "register": "Der Handelsregistereintrag",
    "bank": "Die Bankverbindung (IBAN)",
}


def _quellen(s: Seite, angabe: str, t) -> list[str]:
    """Wo eine Angabe auf dieser Seite steht (Briefpapier und sichtbare Bausteine, ohne Zahlung)."""
    out = []
    if s.im_briefpapier(angabe):
        out.append(t("Briefpapier"))
    for k in ("absender", "fusszeile"):
        e = s.bausteine.get(k)
        if e is not None and e.zeigt(angabe):
            out.append(t(NAMEN[k]))
    return out


def _bank_einmal(s1: Seite, sf: Seite) -> bool:
    """Bank (IBAN) steht auf jeder Rechnung: einseitig (Seite 1 ist die letzte) und mehrseitig."""
    z1, zf = s1.bausteine.get("zahlung"), sf.bausteine.get("zahlung")
    seite1 = bool(_quellen(s1, "bank", str))
    einseitig = seite1 or bool(z1 and z1.sichtbar)
    mehrseitig = seite1 or bool(_quellen(sf, "bank", str)) or bool(zf and zf.sichtbar)
    return einseitig and mehrseitig


def pflicht_pruefen(v: Vorlage, verkaeufer=None, zahlung=None, t=lambda s: s) -> Pflichtbefund:
    """Steht jede Pflichtangabe mindestens einmal auf der Rechnung? Maßstab ist das Absenderprofil
    (``verkaeufer``: modell.Partei, ``zahlung``: modell.Zahlung – welche Werte dort wirklich stehen).

    - Seite 1: Name, Anschrift, USt-IdNr. oder Steuernummer (die, die im Profil steht), Handelsregister nur ohne
      USt-IdNr. (wenn eingetragen) – im Briefpapier oder in einem sichtbaren Baustein.
    - Bank nur bei Überweisung mit IBAN im Profil, rechnungsweit (Zahlung, Fußzeile oder Briefpapier).
    - Folgeseite: Rechnungskopf und Positionen; ohne Verkäufer nur ein ruhiger Hinweis.
    - Doppelt (Briefpapier und Baustein oder zwei Bausteine): Hinweis."""
    b = Pflichtbefund()
    s1, sf = v.seite1, v.folgeseite
    ust = bool(getattr(verkaeufer, "ust_id", "")) if verkaeufer is not None else True
    stnr = bool(getattr(verkaeufer, "steuernummer", "")) if verkaeufer is not None else False
    reg = bool(getattr(verkaeufer, "register", "")) if verkaeufer is not None else False
    seite = t("Seite 1")

    def fehlt(satz: str) -> None:
        b.fehler.append(
            t("{seite}: {angabe} fehlt. Zeige die Angabe in einem Baustein oder hake am Briefpapier an, dass sie "
              "schon drauf ist.").format(seite=seite, angabe=t(satz))
        )

    for a in ("name", "anschrift"):
        if not _quellen(s1, a, t):
            fehlt(_ANGABE_SATZ[a])
    # USt-IdNr. oder Steuernummer – passend zum Profil
    if ust and stnr:
        if not (_quellen(s1, "ust_id", t) or _quellen(s1, "steuernummer", t)):
            fehlt(_ANGABE_SATZ["steuer"])
    elif ust:
        if not _quellen(s1, "ust_id", t):
            fehlt(_ANGABE_SATZ["ust_id"])
    elif stnr:
        if not _quellen(s1, "steuernummer", t):
            fehlt(_ANGABE_SATZ["steuernummer"])
    else:  # Profil ohne beides: wenigstens eine der beiden Angaben muss gewählt sein
        if not (_quellen(s1, "ust_id", t) or _quellen(s1, "steuernummer", t)):
            fehlt(_ANGABE_SATZ["steuer"])
    if not ust and reg and not _quellen(s1, "register", t):
        fehlt(_ANGABE_SATZ["register"])
    z = zahlung
    bank_pflicht = bool(z is not None and getattr(z, "iban", "") and getattr(z, "art", "") != "59"
                        and not getattr(z, "mandat", ""))
    if bank_pflicht and not _bank_einmal(s1, sf):
        b.fehler.append(
            t("Die Bankverbindung (IBAN) fehlt auf mindestens einer Seite, auf der die Zahlung steht. Zeige sie in "
              "„Zahlung / Bank“ oder in der Fußzeile, oder hake am Briefpapier an, dass sie schon drauf ist.")
        )
    # Folgeseite: Kopf und Positionen (Schloss-Bausteine – hier nur zur Sicherheit)
    for k in ("kopf", "positionen", "summen"):
        e = sf.bausteine.get(k)
        if e is None or not e.sichtbar:
            b.fehler.append(t("Folgeseite: {name} fehlt.").format(name=t(NAMEN[k])))
    if not _quellen(sf, "name", t):
        b.hinweise.append(t("Folgeseite: Der Verkäufer steht hier nicht – das ist in Ordnung, er steht auf Seite 1."))
    # Doppeltes
    for name in SEITEN:
        s = v.seite(name)
        titel = t("Seite 1") if name == "seite1" else t("Folgeseite")
        for a in ("name", "anschrift", "ust_id", "steuernummer", "register", "bank"):
            q = _quellen(s, a, t)
            if len(q) > 1:
                satz = t(_ANGABE_SATZ[a])
                if s.im_briefpapier(a):
                    b.doppelt.append(
                        t("{seite}: {angabe} steht im Briefpapier und ist zusätzlich in {wo} angehakt – gedruckt wird "
                          "sie dort nicht noch einmal.").format(seite=titel, angabe=satz, wo=", ".join(q[1:]))
                    )
                else:
                    b.doppelt.append(
                        t("{seite}: {angabe} steht doppelt ({wo}).").format(seite=titel, angabe=satz, wo=" und ".join(q))
                    )
    return b


def ueberlappen(a: Element, b: Element, toleranz: float = 0.05) -> bool:
    ax0, ay0, ax1, ay1 = a.rahmen()
    bx0, by0, bx1, by1 = b.rahmen()
    return ax0 < bx1 - toleranz and bx0 < ax1 - toleranz and ay0 < by1 - toleranz and by0 < ay1 - toleranz


def laden(roh: dict | None, basis: Path | None, verkaeufer=None, zahlung=None) -> Vorlage | None:
    """Wie :func:`aus_dict`, verletzte Regeln -> LayoutFehler. Mit ``verkaeufer`` auch die Pflichtangaben."""
    v = aus_dict(roh, basis)
    if v is not None:
        f = pruefen(v)
        if verkaeufer is not None:
            f += pflicht_pruefen(v, verkaeufer, zahlung).fehler
        if f:
            raise LayoutFehler("; ".join(f))
    return v


# ---------------------------------------------------------------- Zuordnung zur Rechnung
def roh_fuer(roh: dict, verkaeufer_name: str) -> dict | None:
    """Layout-Block für einen Verkäufer: gemerktes Absender-Profil mit gleichem Namen, sonst das des aktiven
    Absenders (gilt wie dessen Stammdaten für alle Rechnungen ohne eigenes Profil)."""
    name = " ".join((verkaeufer_name or "").split()).casefold()
    aktiv = (roh.get("absender") or {}).get("name") or ""
    if name and " ".join(aktiv.split()).casefold() == name:
        return roh.get("layout") or None
    for p in roh.get("absender_profile") or []:
        if isinstance(p, dict) and name and " ".join(((p.get("absender") or {}).get("name") or "").split()).casefold() == name:
            return p.get("layout") or None
    return roh.get("layout") or None


# ---------------------------------------------------------------- Dateien
def datei_uebernehmen(quelle: Path, basis: Path, praefix: str) -> str:
    """Bild/Briefpapier in den Unterordner ``layout`` neben der Konfiguration kopieren (Name mit Prüfsumme,
    damit gleiche Dateien nicht doppelt liegen) -> relativer Pfad für die YAML."""
    daten = Path(quelle).read_bytes()
    h = hashlib.sha256(daten).hexdigest()[:10]
    ziel_dir = Path(basis) / ORDNER
    ziel_dir.mkdir(parents=True, exist_ok=True)
    ziel = ziel_dir / f"{praefix}-{h}{Path(quelle).suffix.lower()}"
    if not ziel.exists():
        shutil.copyfile(quelle, ziel)
    return f"{ORDNER}/{ziel.name}"


def bild_laden(pfad: Path, max_px: int = 2400):
    """PNG/JPEG -> PIL-Bild in RGB bzw. RGBA (PDF/A mit sRGB-OutputIntent: kein CMYK, keine 16 bit)."""
    from PIL import Image
    im = Image.open(pfad)
    im.load()
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
    else:
        im = im.convert("RGB")
    if max(im.size) > max_px:
        im.thumbnail((max_px, max_px))
    return im


# ---------------------------------------------------------------- Briefpapier
@dataclass
class BriefpapierBefund:
    ok: bool                       # als Vektor-PDF verwendbar
    gruende: list[str] = field(default_factory=list)
    seiten: int = 0
    format_passt: bool = True


def _farbraum_problem(cs) -> str | None:
    import pikepdf
    from pikepdf import Array, Name
    if isinstance(cs, Name):
        return "CMYK-Farben ohne Farbprofil" if cs == Name.DeviceCMYK else None
    if isinstance(cs, Array) and len(cs):
        art = cs[0]
        if art in (Name.Separation, Name.DeviceN):
            return "Sonderfarben (Separation/DeviceN)"
        if art == Name.Indexed and len(cs) > 1:
            return _farbraum_problem(cs[1])
        if art == Name.ICCBased:
            try:
                n = int(cs[1].get("/N", 3))
            except (AttributeError, pikepdf.PdfError):
                return None
            return "CMYK-Farbprofil (Ausgabe ist sRGB)" if n == 4 else None
    return None


def _ressourcen_pruefen(res, gruende: set[str], gesehen: set, tiefe: int = 0) -> None:
    import pikepdf
    from pikepdf import Name
    from . import pdfa
    if res is None or tiefe > 8:
        return
    for _, f in (res.get("/Font") or {}).items():
        if f.objgen in gesehen and f.objgen != (0, 0):
            continue
        gesehen.add(f.objgen)
        if not pdfa._ist_eingebettet(f):
            base = str(f.get("/BaseFont", "")).lstrip("/")
            if not (pdfa.STANDARD14.get(base) or pdfa.STANDARD14.get(base.split("+")[-1])):
                gruende.add(f"Schrift „{base}“ nicht eingebettet")
    for _, cs in (res.get("/ColorSpace") or {}).items():
        p = _farbraum_problem(cs)
        if p:
            gruende.add(p)
    for _, gs in (res.get("/ExtGState") or {}).items():
        if "/TR" in gs or "/TR2" in gs and gs.get("/TR2") != Name.Default:
            gruende.add("Transferfunktion im Grafikzustand")
        bm = gs.get("/BM")
        if bm is not None and isinstance(bm, pikepdf.Name) and str(bm) not in (
                "/Normal", "/Compatible", "/Multiply", "/Screen", "/Overlay", "/Darken", "/Lighten",
                "/ColorDodge", "/ColorBurn", "/HardLight", "/SoftLight", "/Difference", "/Exclusion"):
            gruende.add(f"Füllmethode {bm}")
    for _, x in (res.get("/XObject") or {}).items():
        if x.objgen in gesehen and x.objgen != (0, 0):
            continue
        gesehen.add(x.objgen)
        st = x.get("/Subtype")
        if st == Name.Image:
            p = _farbraum_problem(x.get("/ColorSpace"))
            if p:
                gruende.add(p)
            if x.get("/BitsPerComponent", 8) == 16:
                gruende.add("Bild mit 16 bit je Farbe")
            if x.get("/Filter") == Name.JPXDecode:
                gruende.add("JPEG-2000-Bild")
        elif st == Name.Form:
            if "/OC" in x:
                gruende.add("Optionale Inhalte (Ebenen)")
            if "/PS" in x or x.get("/Subtype2") == Name.PS:
                gruende.add("PostScript-Inhalt")
            _ressourcen_pruefen(x.get("/Resources"), gruende, gesehen, tiefe + 1)
        elif st == Name.PS:
            gruende.add("PostScript-Inhalt")
    for _, sh in (res.get("/Shading") or {}).items():
        p = _farbraum_problem(sh.get("/ColorSpace"))
        if p:
            gruende.add(p)
    for _, pat in (res.get("/Pattern") or {}).items():
        sh = pat.get("/Shading")
        if sh is not None:
            p = _farbraum_problem(sh.get("/ColorSpace"))
            if p:
                gruende.add(p)
        _ressourcen_pruefen(pat.get("/Resources"), gruende, gesehen, tiefe + 1)


_CMYK_OPS = {"k", "K"}


def briefpapier_pruefen(pfad: Path) -> BriefpapierBefund:
    """Statische PDF/A-Prüfung des Briefpapiers (erste Seite) – ohne Java, schnell:
    verschlüsselt, nicht eingebettete Schriften ohne freien Ersatz, CMYK-/Sonderfarben (Ausgabe ist sRGB),
    16-bit-/JPEG-2000-Bilder, optionale Inhalte, Formularfelder/JavaScript/Multimedia.
    Die endgültige Prüfung macht veraPDF auf einer Probe-Ausgabe (siehe GUI)."""
    import pikepdf
    from pikepdf import Name
    gruende: set[str] = set()
    try:
        pdf = pikepdf.open(pfad)
    except pikepdf.PasswordError:
        return BriefpapierBefund(False, ["PDF ist verschlüsselt"])
    except Exception as e:  # noqa: BLE001
        return BriefpapierBefund(False, [f"PDF nicht lesbar ({type(e).__name__})"])
    with pdf:
        if pdf.is_encrypted:
            gruende.add("PDF ist verschlüsselt")
        if not len(pdf.pages):
            return BriefpapierBefund(False, ["PDF hat keine Seite"])
        root = pdf.Root
        if "/AcroForm" in root:
            gruende.add("Formularfelder")
        if "/OCProperties" in root:
            gruende.add("Optionale Inhalte (Ebenen)")
        if "/OpenAction" in root and "/JS" in str(root.OpenAction):
            gruende.add("JavaScript")
        seite = pdf.pages[0]
        mb = [float(x) for x in seite.mediabox]
        b, h = (mb[2] - mb[0]) / 72 * 25.4, (mb[3] - mb[1]) / 72 * 25.4
        passt = abs(b - SEITE_B) < 3 and abs(h - SEITE_H) < 3
        if int(seite.obj.get("/Rotate", 0)) % 360:
            gruende.add("Seite ist gedreht")
        for a in seite.obj.get("/Annots") or []:
            if a.get("/Subtype") not in (Name.Link,):
                gruende.add(f"Anmerkung {a.get('/Subtype')}")
        _ressourcen_pruefen(seite.obj.get("/Resources"), gruende, set())
        try:
            for operanden, op in pikepdf.parse_content_stream(seite):
                o = str(op)
                if o in _CMYK_OPS:
                    gruende.add("CMYK-Farben ohne Farbprofil")
                elif o in ("BDC", "BMC") and operanden and operanden[0] == Name.OC:
                    gruende.add("Optionale Inhalte (Ebenen)")
                elif o == "BI":
                    gruende.add("Eingebettetes Inline-Bild")
        except pikepdf.PdfError as e:
            gruende.add(f"Seiteninhalt nicht lesbar ({e})")
        return BriefpapierBefund(not gruende, sorted(gruende), len(pdf.pages), passt)


def briefpapier_als_bild(pfad: Path, ziel: Path, dpi: int = 200) -> Path:
    """Erste Seite des Briefpapiers als sRGB-JPEG (A4) – sicherer Weg für nicht PDF/A-taugliches Briefpapier.
    pypdfium2 (Apache-2.0/BSD-3, kommt mit pdfplumber) rendert, Pillow speichert."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pfad))
    try:
        seite = doc[0]
        bild = seite.render(scale=dpi / 72, may_draw_forms=False).to_pil().convert("RGB")
    finally:
        doc.close()
    soll = (round(SEITE_B / 25.4 * dpi), round(SEITE_H / 25.4 * dpi))
    if bild.size != soll:
        from PIL import Image
        bild = bild.resize(soll, Image.LANCZOS)
    buf = io.BytesIO()
    bild.save(buf, "JPEG", quality=90, optimize=True, dpi=(dpi, dpi))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(buf.getvalue())
    return ziel


def ist_bild(datei: str) -> bool:
    return Path(datei).suffix.lower() in BILD_ENDUNGEN
