# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""adapter_pdf: doppelte, weiße und gedrehte Zeichen filtern; bestehende Beispiel-PDFs unverändert."""

from pathlib import Path

from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from fakturafalter import adapter_pdf

BSP = Path(__file__).resolve().parents[1] / "beispiele"


def _pdf(tmp_path: Path) -> Path:
    p = tmp_path / "zeichen.pdf"
    c = canvas.Canvas(str(p), pagesize=A4)
    c.setFillColor(black)
    c.drawString(100, 700, "Rechnung 1001")
    c.setFillColor(white)  # unsichtbar (weiße Füllung, kein Strich)
    c.drawString(100, 680, "GEHEIM")
    c.setFillColor(Color(0.5, 0.5, 0.5))
    c.drawString(100, 660, "GRAU")
    c.setFillColor(black)
    c.saveState()
    c.translate(80, 400)
    c.rotate(90)
    c.drawString(0, 0, "ROT")
    c.restoreState()
    c.drawString(100, 600, "Hallo")
    c.drawString(100, 600, "Hallo")  # deckungsgleiches Doppel
    c.save()
    return p


def test_weisse_gedrehte_und_doppelte_zeichen_entfallen(tmp_path):
    seiten = adapter_pdf.seiten_lesen(_pdf(tmp_path))
    texte = [w["text"] for w in seiten[0].woerter]
    geklebt = " ".join(texte)
    assert "Rechnung" in geklebt and "1001" in geklebt
    assert "GRAU" in texte
    assert "GEHEIM" not in geklebt
    assert "ROT" not in geklebt and "TOR" not in geklebt
    assert "Hallo" in texte and "HHaalllloo" not in texte


def test_erp_beispiel_bleibt_unveraendert():
    """Sichtbarer Text einer bestehenden Beispiel-PDF (ohne Artefakte) ändert sich nicht."""
    import pdfplumber

    pdf = BSP / "industrie" / "eingang" / "NB-26-1001.pdf"
    if not pdf.exists():
        pdf = next(
            p
            for p in (BSP / "sets").rglob("*.pdf")
            if "erp" in str(p).lower() or p.name.startswith("NB-")
        )
    seiten = adapter_pdf.seiten_lesen(pdf)
    with pdfplumber.open(str(pdf)) as d:
        roh = []
        for p in d.pages:
            roh.extend(
                w["text"]
                for w in p.extract_words(
                    keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5
                )
                if w["text"]
            )
    gelesen = [w["text"] for s in seiten for w in s.woerter]
    assert gelesen == roh
