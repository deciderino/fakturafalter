# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Beispiel-Dateien für den Layouteditor erzeugen (alles fiktiv): beispiele/layout/

    PYTHONPATH=src python tools/layout_beispiel.py

- logo.png: Fantasie-Logo „Musterwerk“ (RGBA, Liberation Sans)
- briefpapier-seite1.pdf / briefpapier-folgeseite.pdf: PDF/A-taugliches Briefpapier (sRGB, Schriften eingebettet)
- layout-beispiel.yaml: Block ``layout`` mit Logo, Briefpapier, eigenem Text- und Bildfeld
"""
from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from fakturafalter import layout

ZIEL = Path(__file__).resolve().parents[1] / "beispiele" / "layout"
SCHRIFTEN = resources.files("fakturafalter") / "ressourcen" / "schriften"
PETROL = (14, 94, 107)


def logo(p: Path) -> None:
    im = Image.new("RGBA", (600, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 30, 190, 210), 28, fill=PETROL + (255,))
    d.polygon([(130, 30), (190, 30), (190, 90)], fill=(242, 163, 58, 255))
    f = ImageFont.truetype(str(SCHRIFTEN / "LiberationSans-Bold.ttf"), 120)
    d.text((40, 52), "M", font=f, fill=(255, 255, 255, 255))
    f2 = ImageFont.truetype(str(SCHRIFTEN / "LiberationSans-Bold.ttf"), 64)
    d.text((215, 70), "Musterwerk", font=f2, fill=PETROL + (255,))
    im.save(p, optimize=True)


def briefpapier(p: Path, folge: bool) -> None:
    pdfmetrics.registerFont(TTFont("BP-Sans", str(SCHRIFTEN / "LiberationSans-Regular.ttf")))
    W, H = A4
    c = canvas.Canvas(str(p), pagesize=A4, invariant=1)
    petrol = Color(PETROL[0] / 255, PETROL[1] / 255, PETROL[2] / 255)
    c.setFillColorRGB(0.91, 0.95, 0.96)
    c.rect(0, H - (8 if folge else 10) * mm, W, (8 if folge else 10) * mm, stroke=0, fill=1)
    c.setFillColor(petrol)
    c.rect(0, H - (8 if folge else 10) * mm, 6 * mm, (8 if folge else 10) * mm, stroke=0, fill=1)
    c.setStrokeColor(petrol)
    c.setLineWidth(0.6)
    c.line(20 * mm, 23 * mm, W - 20 * mm, 23 * mm)
    c.setFont("BP-Sans", 7)
    c.setFillColorRGB(0.35, 0.45, 0.47)
    c.drawRightString(W - 20 * mm, H - 6 * mm, "Musterwerk GmbH · Möbel und Objekteinrichtung · www.musterwerk.example")
    if not folge:
        c.setStrokeColorRGB(0.85, 0.9, 0.91)
        for i in range(5):                                   # dezente Bögen unten rechts
            c.circle(W, 0, (14 + i * 6) * mm, stroke=1, fill=0)
    c.showPage()
    c.save()


def vorlage() -> dict:
    v = layout.standard()
    v.logo = "layout/logo.png"
    v.seite1.briefpapier = "layout/briefpapier-seite1.pdf"
    v.folgeseite.briefpapier = "layout/briefpapier-folgeseite.pdf"
    s1 = v.seite1.bausteine
    s1["logo"].x, s1["logo"].y, s1["logo"].breite, s1["logo"].hoehe = 140, 14, 50, 20
    s1["logo"].ausrichtung = "rechts"
    s1["absender"].breite = 115
    s1["empfaenger"].x, s1["kopf"].x = 115, 20                 # Empfänger rechts, Kopf links
    s1["kopf"].breite, s1["empfaenger"].breite = 80, 75
    s1["summen"].x, s1["zahlung"].x = 20, 115                   # Zahlung neben den Summen
    s1["summen"].breite, s1["zahlung"].breite = 85, 75
    v.seite1.felder.append(layout.Element("text", 20, 244, 85, 12, schrift=9, ebene=3, kennung="text1",
                                          text="Vielen Dank für Ihren Auftrag!\nIhr Team der Musterwerk GmbH"))
    v.seite1.felder.append(layout.Element("bild", 160, 240, 30, 16, ebene=4, kennung="bild1", datei="layout/logo.png",
                                          ausrichtung="rechts"))
    f = v.folgeseite.bausteine
    f["logo"].x, f["logo"].y, f["logo"].breite, f["logo"].hoehe = 150, 12, 40, 16
    f["logo"].ausrichtung = "rechts"
    f["kopf"].x, f["kopf"].y = 20, 36
    f["absender"].breite = 120
    f["positionen"].y, f["positionen"].hoehe = 66, 154
    f["summen"].x, f["zahlung"].x = 20, 115
    f["summen"].breite, f["zahlung"].breite = 85, 75
    fehler = layout.pruefen(v)
    assert not fehler, fehler
    return v.als_dict()


def main() -> int:
    ZIEL.mkdir(parents=True, exist_ok=True)
    logo(ZIEL / "logo.png")
    briefpapier(ZIEL / "briefpapier-seite1.pdf", folge=False)
    briefpapier(ZIEL / "briefpapier-folgeseite.pdf", folge=True)
    kopf = ("# Layout-Vorlage (Layouteditor, Fakturafalter 0.7.0) – alle Daten fiktiv.\n"
            "# Einsetzen als Block „layout:“ in konfiguration.yaml; Pfade relativ zur Konfiguration.\n")
    (ZIEL / "layout-beispiel.yaml").write_text(kopf + yaml.safe_dump({"layout": vorlage()}, allow_unicode=True,
                                                                     sort_keys=False), encoding="utf-8")
    print("geschrieben:", *sorted(x.name for x in ZIEL.iterdir()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
