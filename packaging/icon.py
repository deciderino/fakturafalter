# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Programmsymbol aus dem Logo erzeugen (Variante A „gefächerte Blätter“).

    QT_QPA_PLATFORM=offscreen python packaging/icon.py      (braucht PySide6)

Quelle: src/fakturafalter/ressourcen/fakturafalter.svg, für 16 und 20 px die vereinfachte
fakturafalter-16.svg. Ergebnis: packaging/fakturafalter.png (256 px), packaging/icons/fakturafalter-<n>.png,
packaging/windows/fakturafalter.ico (alle Größen) und ressourcen/fakturafalter.png (Fenstersymbol).
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HIER = Path(__file__).resolve().parent
RES = HIER.parent / "src" / "fakturafalter" / "ressourcen"
SVG, SVG16 = RES / "fakturafalter.svg", RES / "fakturafalter-16.svg"
PNG = HIER / "fakturafalter.png"
ICONS = HIER / "icons"
ICO = HIER / "windows" / "fakturafalter.ico"
GROESSEN = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def zeichnen(n: int) -> QImage:
    img = QImage(n, n, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(SVG16 if n <= 20 else SVG)).render(p, QRectF(0, 0, n, n))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main() -> int:
    QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])
    ICONS.mkdir(exist_ok=True)
    teile = []
    for s in GROESSEN:
        d = png_bytes(zeichnen(s))
        (ICONS / f"fakturafalter-{s}.png").write_bytes(d)
        teile.append((s, d))
    PNG.write_bytes(teile[-1][1])
    (RES / "fakturafalter.png").write_bytes(teile[-1][1])
    aus = struct.pack("<HHH", 0, 1, len(teile))
    ab = 6 + 16 * len(teile)
    for s, d in teile:
        aus += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(d), ab)
        ab += len(d)
    ICO.write_bytes(aus + b"".join(d for _, d in teile))
    print(PNG, ICO, ICONS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
