#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Schematisches README-GIF für Fakturafalter: Datei wandert Eingang -> Fakturafalter -> Ausgang.

    python tools/readme_gif.py                    # docs/bilder/ablauf.gif
    python tools/readme_gif.py --storyboard x.png # zusätzlich Schlüsselbilder (zum Abstimmen)

Schrift: Liberation Sans aus src/fakturafalter/ressourcen/schriften (SIL Open Font License, siehe NOTICE).

Rein schematisch, fiktiv, flach. Anpassen: Farben (FARBEN), Zeiten (PHASEN), Eingabedateien (EINGABEN).
Gezeichnet wird in doppelter Größe und verkleinert (glatte Kanten), danach auf eine feste Palette reduziert.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
SCHRIFTEN = REPO / "src" / "fakturafalter" / "ressourcen" / "schriften"
S = 2                                   # Überabtastung
B, H = 800, 260                         # Endgröße
FPS = 15
FARBEN = {
    "grund": (255, 255, 255),
    "linie": (74, 85, 104),             # Schiefergrau
    "text": (45, 55, 72),
    "leise": (113, 128, 150),
    "ordner": (226, 232, 240),
    "ordner_dunkel": (203, 213, 224),
    "akzent": (43, 108, 176),           # Blau (Fakturafalter)
    "akzent_hell": (235, 244, 255),
    "gruen": (47, 133, 90),
    "gruen_hell": (230, 245, 236),
    "papier": (255, 255, 255),
}
# Eingabedatei je Durchlauf: (Dateiname, Kennfarbe des Etiketts)
EINGABEN = [("rechnung.csv", (56, 161, 105)), ("rechnung.xml", (214, 158, 46)), ("rechnung.pdf", (197, 48, 48))]
# Phasen eines Durchlaufs in Sekunden
PHASEN = [("warten", 0.5), ("hinein", 1.2), ("arbeiten", 0.9), ("geprueft", 0.7), ("hinaus", 1.2), ("ruhe", 0.9)]

SCHRIFT = SCHRIFTEN / "LiberationSans-Regular.ttf"
SCHRIFT_FETT = SCHRIFTEN / "LiberationSans-Bold.ttf"


def f(groesse: int, fett: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(SCHRIFT_FETT if fett else SCHRIFT), groesse * S)


def sanft(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# Lage (Endpixel)
EIN_X, AUS_X, MITTE_X = 120, 680, 400
ORDNER_Y = 150
BOX = (300, 70, 500, 210)               # Fakturafalter-Box


def ordner(d: ImageDraw.ImageDraw, cx: float, titel: str, voll: float = 0.0, inhalt=None) -> None:
    """Flaches Ordnersymbol mit Beschriftung darunter. ``inhalt``: zeichnet eine Datei zwischen Rückwand und
    Vorderseite (sie schaut oben heraus)."""
    w, h = 130, 92
    x0, y0 = cx - w / 2, ORDNER_Y - h / 2
    c = FARBEN
    d.rounded_rectangle(_s(x0, y0 - 12, x0 + 52, y0 + 6), 6 * S, fill=c["ordner_dunkel"], outline=c["linie"], width=2 * S)
    d.rounded_rectangle(_s(x0, y0, x0 + w, y0 + h), 8 * S, fill=c["ordner_dunkel"], outline=c["linie"], width=2 * S)
    if inhalt is not None:
        inhalt()
    d.rounded_rectangle(_s(x0, y0 + 18, x0 + w, y0 + h), 8 * S, fill=c["ordner"], outline=c["linie"], width=2 * S)
    _text(d, cx, y0 + h + 22, titel, f(17, True), c["text"])


def datei(d: ImageDraw.ImageDraw, cx: float, cy: float, name: str, farbe, ausgabe: bool = False,
          beschriftung: bool = True) -> None:
    """Datei-Symbol (Blatt mit Eselsohr), Etikett unten. Ausgabe: PDF/A-3 mit angedeuteter eingebetteter XML."""
    c = FARBEN
    w, h = (62, 78) if ausgabe else (54, 68)
    x0, y0 = cx - w / 2, cy - h / 2
    ohr = 14
    pts = [(x0, y0), (x0 + w - ohr, y0), (x0 + w, y0 + ohr), (x0 + w, y0 + h), (x0, y0 + h)]
    d.polygon([(px * S, py * S) for px, py in pts], fill=c["papier"], outline=c["linie"], width=2 * S)
    d.polygon(_sp([(x0 + w - ohr, y0), (x0 + w - ohr, y0 + ohr), (x0 + w, y0 + ohr)]), fill=c["ordner"], outline=c["linie"], width=2 * S)
    for i in range(3):                                         # Textzeilen andeuten
        y = y0 + 16 + i * 9
        d.line(_s(x0 + 9, y, x0 + w - (18 if i == 0 else 10), y), fill=c["ordner_dunkel"], width=3 * S)
    if ausgabe:                                                # eingebettete XML als kleines Blatt
        d.rounded_rectangle(_s(x0 + w - 26, y0 + h - 36, x0 + w - 6, y0 + h - 18), 3 * S, fill=c["akzent_hell"], outline=c["akzent"], width=S)
        _text(d, x0 + w - 16, y0 + h - 27, "XML", f(7, True), c["akzent"])
        d.rounded_rectangle(_s(x0 - 4, y0 + h - 14, x0 + w + 4, y0 + h + 4), 4 * S, fill=c["akzent"])
        _text(d, cx, y0 + h - 5, "PDF/A-3", f(10, True), c["papier"])
    else:
        d.rounded_rectangle(_s(x0 - 4, y0 + h - 18, x0 + w - 10, y0 + h - 4), 4 * S, fill=farbe)
        _text(d, x0 - 4 + (w - 6) / 2, y0 + h - 11, name.rsplit(".", 1)[1].upper(), f(10, True), c["papier"])
    if beschriftung:
        _text(d, cx, y0 + h + 14, name, f(12), c["leise"])


def fakturafalter(d: ImageDraw.ImageDraw, zahnrad: float, haken: float, aktiv: float) -> None:
    """Mittlere Box: Name, Zahnrad (dreht beim Arbeiten), Haken „geprüft“."""
    c = FARBEN
    rand = c["akzent"] if aktiv else c["linie"]
    d.rounded_rectangle(_s(*BOX), 16 * S, fill=c["akzent_hell"], outline=rand, width=(3 if aktiv else 2) * S)
    _text(d, MITTE_X, BOX[1] + 24, "Fakturafalter", f(19, True), c["akzent"])
    # gefaltete Ecke als Logo-Andeutung
    x1, y0 = BOX[2], BOX[1]
    d.polygon(_sp([(x1 - 30, y0), (x1, y0 + 30), (x1 - 30, y0 + 30)]), fill=c["ordner"], outline=c["akzent"], width=S)
    cx, cy = MITTE_X, BOX[1] + 82
    if haken <= 0:
        _zahnrad(d, cx, cy, 24, zahnrad, c["akzent"] if aktiv else c["leise"])
        _text(d, MITTE_X, BOX[3] - 14, "prüft …" if aktiv else "bereit", f(12), c["leise"])
    else:
        r = 25
        d.ellipse(_s(cx - r, cy - r, cx + r, cy + r), fill=c["gruen_hell"], outline=c["gruen"], width=3 * S)
        k = sanft(haken)                                     # Haken zeichnet sich
        p1, p2, p3 = (cx - 12, cy + 1), (cx - 3, cy + 10), (cx + 13, cy - 9)
        if k < 0.4:
            q = k / 0.4
            d.line(_sp([p1, (p1[0] + (p2[0] - p1[0]) * q, p1[1] + (p2[1] - p1[1]) * q)]), fill=c["gruen"], width=5 * S, joint="curve")
        else:
            q = (k - 0.4) / 0.6
            d.line(_sp([p1, p2, (p2[0] + (p3[0] - p2[0]) * q, p2[1] + (p3[1] - p2[1]) * q)]), fill=c["gruen"], width=5 * S, joint="curve")
        _text(d, MITTE_X, BOX[3] - 14, "geprüft · EN 16931", f(12, True), c["gruen"])


def _zahnrad(d, cx, cy, r, winkel, farbe) -> None:
    zaehne = 8
    pts = []
    for i in range(zaehne * 2):
        a0 = winkel + i * math.pi / zaehne
        rr = r if i % 2 == 0 else r * 0.74
        for da in (-0.17, 0.17):
            pts.append((cx + rr * math.cos(a0 + da), cy + rr * math.sin(a0 + da)))
    d.polygon(_sp(pts), fill=farbe)
    d.ellipse(_s(cx - r * 0.33, cy - r * 0.33, cx + r * 0.33, cy + r * 0.33), fill=FARBEN["akzent_hell"])


def pfeil(d, x0, x1, y, staerke: float) -> None:
    farbe = _misch(FARBEN["ordner_dunkel"], FARBEN["akzent"], staerke)
    for x in range(int(x0), int(x1) - 10, 12):              # gestrichelt
        d.line(_s(x, y, min(x + 6, x1 - 10), y), fill=farbe, width=2 * S)
    d.polygon(_sp([(x1, y), (x1 - 10, y - 6), (x1 - 10, y + 6)]), fill=farbe)


def _misch(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _s(*xy):
    return tuple(v * S for v in xy)


def _sp(pts):
    return [(x * S, y * S) for x, y in pts]


def _text(d, cx, cy, text, schrift, farbe) -> None:
    d.text((cx * S, cy * S), text, font=schrift, fill=farbe, anchor="mm")


def bild(eingabe: int, phase: str, t: float) -> Image.Image:
    """Ein Bild: ``eingabe`` = Index in EINGABEN, ``phase`` aus PHASEN, ``t`` 0..1 innerhalb der Phase."""
    im = Image.new("RGB", (B * S, H * S), FARBEN["grund"])
    d = ImageDraw.Draw(im)
    name, farbe = EINGABEN[eingabe]
    pfeil(d, EIN_X + 78, BOX[0] - 8, ORDNER_Y - 10, 1.0 if phase == "hinein" else 0.0)
    pfeil(d, BOX[2] + 8, AUS_X - 78, ORDNER_Y - 10, 1.0 if phase == "hinaus" else 0.0)
    y_ordner, y_box = ORDNER_Y - 22, BOX[1] + 82
    ein = (lambda: datei(d, EIN_X, y_ordner - 14 - 6 * sanft(t), name, farbe, beschriftung=False)) if phase == "warten" else None
    aus = (lambda: datei(d, AUS_X, y_ordner - 20 + 6 * sanft(t), "", None, ausgabe=True, beschriftung=False)) \
        if phase == "ruhe" else None
    ordner(d, EIN_X, "Eingang", inhalt=ein)
    ordner(d, AUS_X, "Ausgang", inhalt=aus)
    if phase == "warten":                                     # Dateiname über dem Ordner
        _text(d, EIN_X, ORDNER_Y - 86, name, f(12), FARBEN["leise"])
    if phase == "ruhe":
        _text(d, AUS_X, ORDNER_Y - 86, "rechnung_zugferd.pdf", f(12), FARBEN["leise"])
    arbeit = phase in ("arbeiten", "geprueft")
    winkel = (t * math.pi / 2) if phase == "arbeiten" else 0.0
    if phase == "hinein":                                     # gleitet hinter die Box (wird „aufgenommen“)
        k = sanft(t)
        x = EIN_X + (MITTE_X - EIN_X) * k
        y = (y_ordner - 8) + (y_box - (y_ordner - 8)) * k - 12 * math.sin(math.pi * k)
        datei(d, x, y, name, farbe, beschriftung=k < 0.55)
    fakturafalter(d, winkel, t if phase == "geprueft" else 0.0, arbeit)
    if phase == "hinaus":                                     # kommt vor der Box heraus
        k = sanft(t)
        x = MITTE_X + (AUS_X - MITTE_X) * k
        y = y_box + (y_ordner - 8 - y_box) * k - 12 * math.sin(math.pi * k)
        datei(d, x, y, "rechnung_zugferd.pdf", None, ausgabe=True, beschriftung=k > 0.4)
    return im.resize((B, H), Image.LANCZOS)


def auf_palette(im: Image.Image, pal: Image.Image) -> Image.Image:
    """Exakt nächstgelegene Palettenfarbe (Pillows quantize rundet grob und trifft Weiß nicht sicher)."""
    farben = pal.getpalette()[: 3 * _N_FARBEN]
    tab = [tuple(farben[i : i + 3]) for i in range(0, len(farben), 3)]
    cache: dict[tuple, int] = {}

    def index(c):
        i = cache.get(c)
        if i is None:
            i = min(range(len(tab)), key=lambda j: sum((c[k] - tab[j][k]) ** 2 for k in range(3)))
            cache[c] = i
        return i

    roh = im.getcolors(1 << 20)
    lut = {c: index(c) for _n, c in roh}
    out = Image.new("P", im.size)
    out.putpalette(pal.getpalette())
    out.putdata([lut[c] for c in (im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())])
    return out


_N_FARBEN = 0


def palette() -> Image.Image:
    p = Image.new("P", (1, 1))
    farben = list(FARBEN.values()) + [c for _n, c in EINGABEN]
    # Zwischentöne für glatte Kanten: jede Farbe mit Weiß gemischt
    misch = [_misch(c, (255, 255, 255), t) for c in farben for t in (0.25, 0.5, 0.75)]
    global _N_FARBEN
    alle = list(dict.fromkeys(farben + misch))[:256]
    _N_FARBEN = len(alle)
    flach = [v for c in alle for v in c]
    p.putpalette(flach + [0] * (768 - len(flach)))
    return p


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    storyboard = Path(argv[argv.index("--storyboard") + 1]) if "--storyboard" in argv else None
    pal = palette()
    bilder, dauer = [], []
    for e in range(len(EINGABEN)):
        for phase, sek in PHASEN:
            n = max(1, round(sek * FPS))
            for i in range(n):
                bilder.append(auf_palette(bild(e, phase, i / max(n - 1, 1)), pal))
                dauer.append(round(1000 / FPS))
    ziel = REPO / "docs" / "bilder" / "ablauf.gif"
    bilder[0].save(ziel, save_all=True, append_images=bilder[1:], duration=dauer, loop=0, optimize=True, disposal=1)
    gesamt = sum(dauer) / 1000
    print(f"{ziel.name}: {len(bilder)} Bilder, {gesamt:.1f} s, {ziel.stat().st_size} Bytes")
    if storyboard is None:
        return
    # Storyboard: fünf Schlüsselbilder untereinander, links beschriftet
    szenen = [
        (0, "warten", 1.0, "1  Datei liegt im Eingang (CSV, XML oder PDF)"),
        (0, "hinein", 0.5, "2  Fakturafalter holt sie ab"),
        (0, "geprueft", 1.0, "3  Rechnung wird erzeugt und lokal geprüft (EN 16931, PDF/A-3)"),
        (0, "hinaus", 0.5, "4  ZUGFeRD-PDF (PDF/A-3 mit eingebetteter XML) wandert in den Ausgang"),
        (0, "ruhe", 1.0, "5  Fertig – Datei liegt im Ausgang, nächste Datei (XML, PDF …)"),
    ]
    rand, kopf = 16, 34
    sb = Image.new("RGB", (B + 2 * rand, len(szenen) * (H + kopf) + rand), (247, 250, 252))
    d = ImageDraw.Draw(sb)
    for i, (e, ph, t, titel) in enumerate(szenen):
        y = rand + i * (H + kopf)
        d.text((rand, y + 6), titel, font=ImageFont.truetype(str(SCHRIFT_FETT), 17), fill=FARBEN["text"])
        sb.paste(bild(e, ph, t), (rand, y + kopf - 4))
        d.rectangle((rand, y + kopf - 4, rand + B - 1, y + kopf - 4 + H - 1), outline=FARBEN["ordner_dunkel"])
    sb.save(storyboard, optimize=True)


if __name__ == "__main__":
    main()
