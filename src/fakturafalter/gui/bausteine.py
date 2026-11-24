# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Kleine Bausteine: Statuspunkt, Karte, Knöpfe, Toasts (ohne Animation), Programmsymbol."""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .texte import _


class Punkt(QLabel):
    """Statuspunkt – ändert nur die Farbe, blinkt nie."""

    def __init__(self, farbe: str, d: int = 14, parent=None):
        super().__init__(parent)
        self.d = d
        self.setFixedSize(d, d)
        self.farbe(farbe)

    def farbe(self, f: str) -> None:
        self._farbe = f
        self.setStyleSheet(f"background:{f}; border-radius:{self.d // 2}px;")


def lbl(
    text: str = "", name: str | None = None, enabled: bool = True, umbruch: bool = False
) -> QLabel:
    l_ = QLabel(text)
    if name:
        l_.setObjectName(name)
    l_.setEnabled(enabled)
    l_.setWordWrap(umbruch)
    return l_


def knopf(
    text: str,
    icon: bool = False,
    primary: bool = False,
    danger: bool = False,
    enabled: bool = True,
    tip: str | None = None,
    klick=None,
) -> QPushButton:
    b = QPushButton(text)
    if icon:
        b.setObjectName("icon")
    if primary:
        b.setProperty("primary", True)
    if danger:
        b.setProperty("danger", True)
    b.setEnabled(enabled)
    if tip:
        b.setToolTip(tip)
        b.setAccessibleName(tip)
    if klick:
        b.clicked.connect(klick)
    b.setMinimumHeight(48)
    return b


def karte() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("karte")
    v = QVBoxLayout(f)
    v.setContentsMargins(14, 12, 14, 12)
    v.setSpacing(8)
    return f, v


def trenner() -> QFrame:
    t = QFrame()
    t.setObjectName("trenner")
    return t


# ------------------------------------------------------------------------------------- Toasts
class Toast(QFrame):
    """Hinweis unten rechts. Kein Symbol-Glyph (fehlt in manchen Schriften) – ein farbiger Punkt zeigt die Art."""

    def __init__(
        self,
        parent: QWidget,
        c: dict,
        art: str,
        titel: str,
        detail: str = "",
        aktion: str | None = None,
        bei_aktion=None,
        dauer_ms: int = 7000,
        schluessel: str | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("toast")
        self.art = art
        self.schluessel = schluessel
        self._dauer = dauer_ms if not aktion else max(dauer_ms, 10000)
        bg, b, fg = {
            "ok": (c["ok_bg"], c["ok"], c["ok_t"]),
            "info": (c["in_bg"], c["busy"], c["in_t"]),
            "fehler": (c["er_bg"], c["err"], c["er_t"]),
        }[art]
        self.setStyleSheet(
            f"QFrame#toast {{ background:{bg}; border:1px solid {b}; border-radius:8px; }}"
            f"QFrame#toast QLabel {{ border:none; background:transparent; color:{fg}; }}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        kopf = QHBoxLayout()
        kopf.setSpacing(10)
        self.punkt = Punkt(b, 12)
        kopf.addWidget(self.punkt, 0, Qt.AlignmentFlag.AlignVCenter)
        self.titel = QLabel(titel)
        self.titel.setStyleSheet("font-weight:bold; font-size:14px;")
        self.titel.setWordWrap(True)
        kopf.addWidget(self.titel, 1)
        zu = QPushButton("×")
        zu.setToolTip(_("Hinweis schließen"))
        zu.setAccessibleName(_("Hinweis schließen"))
        zu.setFixedSize(48, 48)
        zu.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; color:{fg}; font-size:20px;"
            " min-width:48px; min-height:48px; padding:0; }"
        )
        zu.clicked.connect(self.schliessen)
        kopf.addWidget(zu, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(kopf)
        self.detail = QLabel(detail)
        self.detail.setStyleSheet(f"font-size:13px; color:{c['sub']};")
        self.detail.setWordWrap(True)
        self.detail.setVisible(bool(detail))
        v.addWidget(self.detail)
        self.knopf = None
        if aktion:
            self.knopf = QPushButton(aktion)
            self.knopf.setMinimumSize(120, 48)
            self.knopf.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{fg}; border:2px solid {b};"
                f" border-radius:6px; min-height:44px; padding:0 14px; }}"
            )
            self.knopf.clicked.connect(lambda: (bei_aktion and bei_aktion(), self.schliessen()))
            h = QHBoxLayout()
            h.addStretch()
            h.addWidget(self.knopf)
            v.addLayout(h)
        self.setFixedWidth(420)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.schliessen)
        if dauer_ms:
            self.timer.start(self._dauer)

    def setzen(self, titel: str, detail: str = "") -> None:
        """Inhalt ersetzen statt einen weiteren Toast zu stapeln; Anzeigedauer beginnt neu."""
        self.titel.setText(titel)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        if self._dauer and not self.underMouse():
            self.timer.start(self._dauer)

    def schliessen(self) -> None:
        self.timer.stop()
        self.hide()
        self.deleteLater()

    def enterEvent(self, e):  # Maus drüber -> stehen lassen (zum Lesen/Klicken)
        self.timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self.isHidden():
            self.timer.start(4000)
        super().leaveEvent(e)


class ToastStapel(QObject):
    """Toasts unten rechts im Fenster, höchstens 3 sichtbar, ohne Animation.

    Mit `schluessel` wird ein noch sichtbarer Toast gleicher Art/Schlüssel aktualisiert statt neu gestapelt."""

    def __init__(self, fenster: QWidget, abstand_unten: int = 16):
        super().__init__(fenster)
        self.fenster = fenster
        self.abstand_unten = abstand_unten
        self.toasts: list[Toast] = []
        fenster.installEventFilter(self)

    def zeigen(
        self,
        c: dict,
        art: str,
        titel: str,
        detail: str = "",
        aktion=None,
        bei_aktion=None,
        dauer_ms: int = 7000,
        schluessel: str | None = None,
    ) -> Toast:
        if schluessel:
            for alt in self.sichtbare():
                if alt.schluessel == schluessel and alt.art == art:
                    alt.setzen(titel, detail)
                    self.ordnen()
                    return alt
                if (
                    alt.schluessel == schluessel
                ):  # Art hat sich geändert (z.B. jetzt auch Fehler) -> ersetzen
                    alt.schliessen()
        t = Toast(self.fenster, c, art, titel, detail, aktion, bei_aktion, dauer_ms, schluessel)
        t.destroyed.connect(lambda *_: self._weg(t))
        self.toasts.append(t)
        while len(self.toasts) > 3:
            self.toasts[0].schliessen()
            self.toasts.pop(0)
        t.adjustSize()
        t.show()
        self.ordnen()
        return t

    def _weg(self, t) -> None:
        if t in self.toasts:
            self.toasts.remove(t)
        if shiboken6.isValid(self.fenster):  # beim Schließen des Fensters schon weg
            self.ordnen()

    def sichtbare(self) -> list[Toast]:
        aus = []
        for t in self.toasts:
            try:
                if not t.isHidden():
                    aus.append(t)
            except RuntimeError:  # bereits gelöscht
                continue
        return aus

    def ordnen(self) -> None:
        y = self.fenster.height() - self.abstand_unten
        for t in reversed(self.sichtbare()):
            t.adjustSize()
            y -= t.height()
            t.move(self.fenster.width() - t.width() - 16, y)
            t.raise_()
            y -= 8

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize:
            self.ordnen()
        return False


# -------------------------------------------------------------------------------- Programmsymbol
def symbol(farbe: str | None = None, groesse: int = 64, zahl: int = 0) -> QIcon:
    """Programmlogo (gefächerte Blätter, ressourcen/fakturafalter.svg) mit Statuspunkt; farbe=None -> ohne Punkt.

    zahl > 0: Anzahl offener Aufgaben als Ziffer im Punkt (Tray-Badge, statisch – blinkt nie)."""
    from importlib import resources

    from PySide6.QtSvg import QSvgRenderer

    pm = QPixmap(groesse, groesse)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = groesse / 64
    datei = "fakturafalter-16.svg" if groesse <= 20 else "fakturafalter.svg"
    QSvgRenderer(str(resources.files("fakturafalter") / "ressourcen" / datei)).render(
        p, QRectF(0, 0, groesse, groesse)
    )
    if farbe:
        p.setPen(QPen(QColor("#ffffff"), 3 * s))
        p.setBrush(QColor(farbe))
        p.drawEllipse(QRectF(36 * s, 38 * s, 26 * s, 26 * s))
        if zahl > 0:
            f = QFont()
            f.setBold(True)
            f.setPixelSize(max(6, int((15 if zahl < 10 else 11) * s)))
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(
                QRectF(36 * s, 38 * s, 26 * s, 26 * s),
                Qt.AlignmentFlag.AlignCenter,
                str(zahl) if zahl < 10 else "9+",
            )
    p.end()
    return QIcon(pm)


# -------------------------------------------------------------------------------- Assistenten-Bausteine
def fadenkreuz(farbe: str, d: int = 22) -> QIcon:
    """Ziel-Symbol für „Wert in der PDF anklicken“ (gezeichnet, kein Schrift-Glyph)."""
    pm = QPixmap(d * 2, d * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(farbe), 3))
    m = d
    p.drawEllipse(QRectF(m - d * 0.55, m - d * 0.55, d * 1.1, d * 1.1))
    for a, b in (
        ((m, 2), (m, m - 6)),
        ((m, m + 6), (m, 2 * d - 2)),
        ((2, m), (m - 6, m)),
        ((m + 6, m), (2 * d - 2, m)),
    ):
        p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def rahmen_symbol(farbe: str, d: int = 22) -> QIcon:
    """Symbol für „Bereich ziehen“: gestricheltes Rechteck mit Ecke (gezeichnet, kein Schrift-Glyph)."""
    pm = QPixmap(d * 2, d * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(farbe), 3, Qt.PenStyle.DashLine))
    p.drawRect(QRectF(5, 9, d * 2 - 10, d * 2 - 18))
    p.setPen(QPen(QColor(farbe), 4))
    p.drawLine(d * 2 - 5, d * 2 - 9, d * 2 - 13, d * 2 - 9)
    p.drawLine(d * 2 - 5, d * 2 - 9, d * 2 - 5, d * 2 - 17)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


class Zustand(QWidget):
    """Kreis mit Haken (erkannt), Ausrufezeichen (bitte prüfen), Strich (fehlt) oder Ziffer – gezeichnet."""

    def __init__(self, c: dict, zustand: str = "fehlt", d: int = 26, zahl: str = ""):
        super().__init__()
        self.c, self.d, self.zahl = c, d, zahl
        self.zustand = zustand
        self.setFixedSize(d, d)

    def setzen(self, zustand: str, zahl: str | None = None) -> None:
        self.zustand = zustand
        if zahl is not None:
            self.zahl = zahl
        self.update()

    def paintEvent(self, _e):
        c, d = self.c, self.d
        farbe = {
            "erkannt": c["ok"],
            "pruefen": c["busy"],
            "fehlt": c["off"],
            "aktiv": c["prim"],
            "warten": c["acc"],
            "aus": c["off"],
        }.get(self.zustand, c["off"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1.5, 1.5, d - 3, d - 3)
        hohl = self.zustand in ("fehlt", "aus")
        p.setPen(QPen(QColor(farbe), 2) if hohl else Qt.PenStyle.NoPen)
        p.setBrush(Qt.BrushStyle.NoBrush if hohl else QColor(farbe))
        p.drawEllipse(r)
        stift = QPen(QColor(farbe if hohl else "#ffffff"), max(2.0, d / 11))
        stift.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(stift)
        if self.zahl:
            f = QFont()
            f.setBold(True)
            f.setPixelSize(int(d * 0.5))
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.zahl)
        elif self.zustand == "erkannt":
            pfad = QPainterPath()
            pfad.moveTo(d * 0.28, d * 0.52)
            pfad.lineTo(d * 0.44, d * 0.68)
            pfad.lineTo(d * 0.73, d * 0.34)
            p.drawPath(pfad)
        elif self.zustand == "pruefen":
            p.drawLine(int(d / 2), int(d * 0.27), int(d / 2), int(d * 0.56))
            p.drawPoint(int(d / 2), int(d * 0.73))
        elif self.zustand == "warten":
            p.drawLine(int(d * 0.3), int(d / 2), int(d * 0.7), int(d / 2))
            p.drawLine(int(d * 0.55), int(d * 0.35), int(d * 0.7), int(d / 2))
            p.drawLine(int(d * 0.55), int(d * 0.65), int(d * 0.7), int(d / 2))
        else:
            p.drawLine(int(d * 0.32), int(d / 2), int(d * 0.68), int(d / 2))
        p.end()


class Schritte(QWidget):
    """Waagrechte Schrittleiste: erledigt = grüner Haken, aktiv = blau, offen = grau. Text bricht um."""

    def __init__(self, c: dict, namen: list[str]):
        super().__init__()
        self.c = c
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.kreise: list[Zustand] = []
        self.texte: list[QLabel] = []
        self.linien: list[QFrame] = []
        for i, n in enumerate(namen):
            if i:
                linie = QFrame()
                linie.setFixedHeight(2)
                linie.setMinimumWidth(16)
                h.addWidget(linie, 1)
                self.linien.append(linie)
            k = Zustand(c, "aus", 32, str(i + 1))
            t = QLabel(n)
            t.setWordWrap(True)
            box = QHBoxLayout()
            box.setSpacing(8)
            box.addWidget(k)
            box.addWidget(t)
            h.addLayout(box, 0)
            self.kreise.append(k)
            self.texte.append(t)
        self.setzen(0)

    def setzen(self, aktiv: int, erledigt: set[int] | None = None) -> None:
        c = self.c
        erledigt = set(range(aktiv)) if erledigt is None else erledigt
        self.aktiv = aktiv
        for i, (k, t) in enumerate(zip(self.kreise, self.texte)):
            if i in erledigt and i != aktiv:
                k.setzen("erkannt", "")
            else:
                k.setzen("aktiv" if i == aktiv else "aus", str(i + 1))
            t.setStyleSheet(
                ("font-weight:bold;" if i == aktiv else f"color:{c['sub']};") + "font-size:14px;"
            )
        for i, linie in enumerate(self.linien):
            linie.setStyleSheet(f"background:{c['ok'] if i < aktiv else c['card_b']};")


def kopfleiste(titel: str, unter: str | None = None) -> tuple[QFrame, QVBoxLayout, QLabel]:
    f = QFrame()
    f.setObjectName("leiste")
    v = QVBoxLayout(f)
    v.setContentsMargins(20, 14, 20, 14)
    v.setSpacing(10)
    t = lbl(titel, "titel", umbruch=True)
    v.addWidget(t)
    if unter:
        v.addWidget(lbl(unter, "sub", umbruch=True))
    return f, v, t


def fussleiste(c: dict) -> tuple[QFrame, QHBoxLayout, QLabel, QHBoxLayout]:
    """-> (Rahmen, Knöpfe links, Hinweistext, Knöpfe rechts)."""
    f = QFrame()
    f.setObjectName("fuss")
    f.setStyleSheet(
        f"QFrame#fuss {{ border-top: 1px solid {c['bar_b']}; background: {c['win']}; }}"
    )
    h = QHBoxLayout(f)
    h.setContentsMargins(20, 12, 20, 12)
    h.setSpacing(10)
    links = QHBoxLayout()
    links.setSpacing(10)
    rechts = QHBoxLayout()
    rechts.setSpacing(10)
    h.addLayout(links)
    hinweis = lbl("", "hinweis", umbruch=True)
    hinweis.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    h.addWidget(hinweis, 1)
    h.addLayout(rechts)
    return f, links, hinweis, rechts


def rollen(inhalt: QWidget):
    """Scrollfläche nur senkrecht (Text bricht um statt seitlich zu scrollen)."""
    from PySide6.QtWidgets import QScrollArea

    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.Shape.NoFrame)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inhalt.setObjectName("wurzel")
    s.setWidget(inhalt)
    return s


class Schalter(QAbstractButton):
    """Ein/Aus-Schalter mit Beschriftung, 48 px hoch, ohne Animation. ``an``/``aus``: Texte der beiden Zustände."""

    def __init__(self, c: dict, an: str, aus: str, klick=None):
        super().__init__()
        self.c, self.t_an, self.t_aus = c, an, aus
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(48)
        self.toggled.connect(lambda _a: (self._text(), self.update()))
        if klick:
            self.clicked.connect(klick)
        self._text()

    def _text(self) -> None:
        self.setText(self.t_an if self.isChecked() else self.t_aus)
        self.setAccessibleName(self.text())
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        breit = max(fm.horizontalAdvance(self.t_an), fm.horizontalAdvance(self.t_aus))
        return QSize(16 + 44 + 10 + breit + 16, max(48, fm.height() + 16))

    minimumSizeHint = sizeHint

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        an, ok = self.isChecked(), self.isEnabled()
        if self.hasFocus():
            p.setPen(QPen(QColor(self.c["acc"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(1, 1, self.width() - 2, h - 2), 6, 6)
        spur = QRectF(16, (h - 24) / 2, 44, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.c["dis_b"] if not ok else self.c["ok"] if an else self.c["off"]))
        p.drawRoundedRect(spur, 12, 12)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(spur.x() + (23 if an else 3), spur.y() + 3, 18, 18))
        p.setPen(QColor(self.c["fg"] if ok else self.c["dis_fg"]))
        f = self.font()
        f.setBold(True)
        p.setFont(f)
        p.drawText(
            QRectF(70, 0, self.width() - 70, h), int(Qt.AlignmentFlag.AlignVCenter), self.text()
        )
        p.end()


class Segmente(QWidget):
    """Fortschritt in n Kästchen (z. B. 3 von 5 Rechnungen ohne Korrektur). Statisch, ohne Animation."""

    def __init__(self, c: dict, n: int, von: int):
        super().__init__()
        self.c, self.n, self.von = c, n, max(1, von)
        self.setFixedHeight(12)
        self.setMinimumWidth(self.von * 22)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        b = min(40.0, (self.width() - 4 * (self.von - 1)) / self.von)
        for i in range(self.von):
            p.setBrush(QColor(self.c["ok"] if i < self.n else self.c["card_b"]))
            p.drawRoundedRect(QRectF(i * (b + 4), 1, b, 10), 3, 3)
        p.end()


class Balken(QWidget):
    """Waagrechter Fortschrittsbalken (Anteil 0…1), statisch."""

    def __init__(self, c: dict):
        super().__init__()
        self.c, self.anteil = c, 0.0
        self.setFixedHeight(8)

    def setzen(self, anteil: float) -> None:
        self.anteil = max(0.0, min(1.0, anteil))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.c["card_b"]))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 8), 4, 4)
        if self.anteil:
            p.setBrush(QColor(self.c["ok"]))
            p.drawRoundedRect(QRectF(0, 0, self.width() * self.anteil, 8), 4, 4)
        p.end()
