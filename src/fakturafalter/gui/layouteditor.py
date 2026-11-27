# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Layouteditor für den sichtbaren Teil der erzeugten ZUGFeRD-Rechnung (nach Skizze, abgestimmt 11.11.2026).

Links die Bausteine (Schloss = ganzer Baustein bleibt nötig: Empfänger, Kopf, Positionen, Summen; Absender und
Fußzeile sind ab Layoutformat 2 ausblendbar, je Baustein wählst du die Verkäufer-Angaben) und eigene Felder,
in der Mitte die A4-Seite, rechts die Eigenschaften in mm. Die Seite im Hintergrund ist die echte Ausgabe:
``sicht.erzeugen`` mit fiktiven Beispieldaten, gerendert mit pypdfium2 – Editor und Rechnung laufen damit nicht
auseinander. Neu gezeichnet wird erst nach dem Loslassen bzw. kurz nach einer Eingabe (nichts flackert).
"""

from __future__ import annotations

import copy
import logging
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import beispielrechnung, pdfa, sicht, validierung
from .. import layout as lay
from ..modell import Partei, Zahlung
from .bausteine import ToastStapel, knopf, lbl
from .texte import _

log = logging.getLogger("fakturafalter")
S = 4.0  # Szeneneinheiten je mm
GRIFF = 2.5  # Anfasser-Bereich in mm (Kante/Ecke) – mit dem Zoom wenigstens 12 px


# ---------------------------------------------------------------------------- Hilfen
class FlussLayout(QLayout):
    """Knöpfe nebeneinander, bei schmalem Fenster (z. B. 250 %) in die nächste Zeile."""

    def __init__(self, parent=None, abstand: int = 8):
        super().__init__(parent)
        self._items: list = []
        self._abstand = abstand

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._anordnen(QRect(0, 0, w, 0), nur_messen=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._anordnen(rect, nur_messen=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _anordnen(self, rect, nur_messen):
        m = self.contentsMargins()
        x, y = rect.x() + m.left(), rect.y() + m.top()
        zeile = 0
        rechts = rect.right() - m.right()
        for it in self._items:
            if (
                it.widget() is not None
                and not it.widget().isVisible()
                and not nur_messen
                and it.widget().isHidden()
            ):
                continue
            sh = it.sizeHint()
            if x + sh.width() > rechts and zeile > 0:
                x = rect.x() + m.left()
                y += zeile + self._abstand
                zeile = 0
            if not nur_messen:
                it.setGeometry(QRect(x, y, sh.width(), sh.height()))
            x += sh.width() + self._abstand
            zeile = max(zeile, sh.height())
        return y + zeile - rect.y() + m.bottom()


def schloss_symbol(farbe: str, d: int = 22) -> QIcon:
    """Geschlossenes Schloss (gezeichnet, kein Schrift-Glyph)."""
    pm = QPixmap(d * 2, d * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    pen = QPen(QColor(farbe), 2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(d * 0.3, d * 0.12, d * 0.4, d * 0.5), 0, 180 * 16)
    p.drawLine(QPointF(d * 0.3, d * 0.37), QPointF(d * 0.3, d * 0.45))
    p.drawLine(QPointF(d * 0.7, d * 0.37), QPointF(d * 0.7, d * 0.45))
    p.setBrush(QColor(farbe))
    p.drawRoundedRect(QRectF(d * 0.2, d * 0.45, d * 0.6, d * 0.42), 2, 2)
    p.end()
    return QIcon(pm)


def seite_rendern(pdf: bytes, index: int, breite_px: int) -> QImage:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf)
    try:
        index = min(index, len(doc) - 1)
        seite = doc[index]
        skala = max(0.5, breite_px / seite.get_width())
        bild = seite.render(scale=skala).to_pil().convert("RGB")
    finally:
        doc.close()
    daten = bild.tobytes("raw", "RGB")
    qi = QImage(daten, bild.width, bild.height, bild.width * 3, QImage.Format.Format_RGB888)
    return qi.copy()


# ---------------------------------------------------------------------------- Szene
class Raster(QGraphicsItem):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setZValue(1)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return QRectF(0, 0, lay.SEITE_B * S, lay.SEITE_H * S)

    def paint(self, p, _opt, _w=None):
        r = self.editor.vorlage.raster or 5
        pen = QPen(QColor(90, 140, 200, 45))
        pen.setCosmetic(True)
        p.setPen(pen)
        x = r
        while x < lay.SEITE_B:
            p.drawLine(QPointF(x * S, 0), QPointF(x * S, lay.SEITE_H * S))
            x += r
        y = r
        while y < lay.SEITE_H:
            p.drawLine(QPointF(0, y * S), QPointF(lay.SEITE_B * S, y * S))
            y += r


class BlockItem(QGraphicsRectItem):
    """Rahmen eines Bausteins/Felds: verschieben (Maus, Pfeiltasten), Größe an Kanten und Ecken ändern."""

    def __init__(self, editor, e: lay.Element):
        super().__init__()
        self.editor = editor
        self.e = e
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)
        self._griff: str | None = None
        self._start = None
        self.fehler = False
        self.aus_element()

    def aus_element(self) -> None:
        self.setRect(0, 0, self.e.breite * S, self.e.hoehe * S)
        self.setPos(self.e.x * S, self.e.y * S)

    def name(self) -> str:
        if self.e.art == "text":
            return _("Textfeld") + (
                f": {self.e.text.splitlines()[0][:18]}" if self.e.text.strip() else ""
            )
        return _(lay.NAMEN.get(self.e.art, self.e.art))

    def paint(self, p, _opt, _w=None):
        c = self.editor.c
        sel = self.isSelected()
        farbe = (
            QColor(c["err"])
            if self.fehler
            else QColor(c["acc"] if sel else ("#333333" if self.e.oben else "#7a7a7a"))
        )
        pen = QPen(farbe, 2.5 if sel else 1.4)
        pen.setCosmetic(True)
        if not sel and not self.fehler:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(21, 101, 192, 18) if sel else Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect())
        # Beschriftung oben links (Fähnchen)
        f = QFont(p.font())
        f.setPixelSize(max(8, int(3.2 * S)))
        f.setBold(True)
        p.setFont(f)
        t = self.name()
        w = p.fontMetrics().horizontalAdvance(t) + 2 * S
        h = 4.6 * S
        p.fillRect(QRectF(0, -h, w, h), farbe)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(S, -h, w, h), Qt.AlignmentFlag.AlignVCenter, t)
        if sel:
            p.setBrush(QColor(c["acc"]))
            p.setPen(Qt.PenStyle.NoPen)
            d = 2.2 * S
            for pt in self._punkte().values():
                p.drawRect(QRectF(pt.x() - d / 2, pt.y() - d / 2, d, d))

    def boundingRect(self):
        return self.rect().adjusted(-3 * S, -5 * S, 3 * S, 3 * S)

    def shape(self):
        from PySide6.QtGui import QPainterPath

        pfad = QPainterPath()
        pfad.addRect(
            self.rect().adjusted(-GRIFF * S / 2, -GRIFF * S / 2, GRIFF * S / 2, GRIFF * S / 2)
        )
        return pfad

    def _punkte(self) -> dict[str, QPointF]:
        r = self.rect()
        return {
            "lo": r.topLeft(),
            "ro": r.topRight(),
            "lu": r.bottomLeft(),
            "ru": r.bottomRight(),
            "o": QPointF(r.center().x(), r.top()),
            "u": QPointF(r.center().x(), r.bottom()),
            "l": QPointF(r.left(), r.center().y()),
            "r": QPointF(r.right(), r.center().y()),
        }

    def _griff_bei(self, pos: QPointF) -> str | None:
        if not self.isSelected():
            return None
        zoom = max(0.05, self.editor.ansicht.transform().m11())
        tol = max(GRIFF * S, 14 / zoom)
        for k, pt in self._punkte().items():
            if abs(pt.x() - pos.x()) <= tol and abs(pt.y() - pos.y()) <= tol:
                return k
        return None

    def hoverMoveEvent(self, ev):
        g = self._griff_bei(ev.pos())
        form = {
            "lo": Qt.CursorShape.SizeFDiagCursor,
            "ru": Qt.CursorShape.SizeFDiagCursor,
            "ro": Qt.CursorShape.SizeBDiagCursor,
            "lu": Qt.CursorShape.SizeBDiagCursor,
            "o": Qt.CursorShape.SizeVerCursor,
            "u": Qt.CursorShape.SizeVerCursor,
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
        }.get(g, Qt.CursorShape.SizeAllCursor)
        self.setCursor(form)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        self._griff = self._griff_bei(ev.pos())
        self._start = (ev.scenePos(), (self.e.x, self.e.y, self.e.breite, self.e.hoehe))
        if self._griff:
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if not self._griff:
            return super().mouseMoveEvent(ev)
        p0, (x, y, b, h) = self._start
        dx, dy = (ev.scenePos().x() - p0.x()) / S, (ev.scenePos().y() - p0.y()) / S
        x1, y1, x2, y2 = x, y, x + b, y + h
        if "l" in self._griff:
            x1 = self.editor.einrasten(x + dx)
        if "r" in self._griff:
            x2 = self.editor.einrasten(x + b + dx)
        if "o" in self._griff:
            y1 = self.editor.einrasten(y + dy)
        if "u" in self._griff:
            y2 = self.editor.einrasten(y + h + dy)
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(lay.SEITE_B, x2), min(lay.SEITE_H, y2)
        if x2 - x1 < lay.MIN_MASS:
            x1, x2 = (x2 - lay.MIN_MASS, x2) if "l" in self._griff else (x1, x1 + lay.MIN_MASS)
        if y2 - y1 < lay.MIN_MASS:
            y1, y2 = (y2 - lay.MIN_MASS, y2) if "o" in self._griff else (y1, y1 + lay.MIN_MASS)
        self.prepareGeometryChange()
        self.e.x, self.e.y, self.e.breite, self.e.hoehe = x1, y1, x2 - x1, y2 - y1
        self.aus_element()
        self.editor.werte_zeigen(live=True)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        war = self._start[1] if self._start else None
        self._griff = None
        super().mouseReleaseEvent(ev)
        if war != (self.e.x, self.e.y, self.e.breite, self.e.hoehe):
            self.editor.geaendert()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and not self.editor._laden:
            x = self.editor.einrasten(value.x() / S)
            y = self.editor.einrasten(value.y() / S)
            x = min(max(0.0, x), lay.SEITE_B - self.e.breite)
            y = min(max(0.0, y), lay.SEITE_H - self.e.hoehe)
            return QPointF(x * S, y * S)
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self.editor._laden
        ):
            self.e.x, self.e.y = round(self.pos().x() / S, 2), round(self.pos().y() / S, 2)
            self.editor.werte_zeigen(live=True)
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged
            and not self.editor._laden
        ):
            self.editor.auswahl_geaendert()
        return super().itemChange(change, value)

    def keyPressEvent(self, ev):
        schritt = (
            self.editor.vorlage.raster
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier
            else 1.0
        )
        d = {
            Qt.Key.Key_Left: (-schritt, 0),
            Qt.Key.Key_Right: (schritt, 0),
            Qt.Key.Key_Up: (0, -schritt),
            Qt.Key.Key_Down: (0, schritt),
        }.get(ev.key())
        if d is None:
            return super().keyPressEvent(ev)
        self.e.x = min(max(0.0, self.e.x + d[0]), lay.SEITE_B - self.e.breite)
        self.e.y = min(max(0.0, self.e.y + d[1]), lay.SEITE_H - self.e.hoehe)
        self.editor._laden = True
        self.aus_element()
        self.editor._laden = False
        self.editor.werte_zeigen(live=True)
        self.editor.geaendert()


class Ansicht(QGraphicsView):
    def __init__(self, editor, szene):
        super().__init__(szene)
        self.editor = editor
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(QColor("#d4d4d4"))
        self.setAccessibleName(_("A4-Seite"))
        self._zoom = 1.0

    def einpassen(self):
        self.resetTransform()
        r = QRectF(-6 * S, -8 * S, (lay.SEITE_B + 12) * S, (lay.SEITE_H + 14) * S)
        self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
        if self._zoom != 1.0:
            self.scale(self._zoom, self._zoom)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.einpassen()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom = min(
                4.0, max(1.0, self._zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15))
            )
            self.einpassen()
            e.accept()
            return
        super().wheelEvent(e)


class _Pruefsignal(QObject):
    fertig = Signal(object)


# ---------------------------------------------------------------------------- Editor
class LayoutEditor(QDialog):
    """Ergebnis: :meth:`ergebnis` -> Layout-Block (dict) oder None (= festes Standardlayout)."""

    def __init__(
        self,
        eltern,
        c: dict,
        roh: dict | None,
        basis: Path,
        profil: str = "",
        verkaeufer: Partei | None = None,
        zahlung: Zahlung | None = None,
        spalten: list[str] | None = None,
    ):
        super().__init__(eltern)
        self.c = c
        self.basis = Path(basis)
        self.profil = profil
        self.verkaeufer = verkaeufer
        self.zahlung = zahlung
        self.spalten = list(spalten or [])  # eigene CSV-Spalten für Platzhalter (rc2)
        self.alt_meldung = ""  # Text der Ablehnung eines alten Layouts (Format 1)
        self.setWindowTitle(_("Layouteditor"))
        self.setObjectName("wurzel")
        self.setStyleSheet(
            f"QPushButton:checked {{ background:{c['sel']}; border:2px solid {c['acc']}; "
            "font-weight:bold; }"
        )
        self.resize(1400, 900)
        self.toasts = ToastStapel(self, abstand_unten=70)
        self._laden = False
        self._items: list[BlockItem] = []
        self.seite_name = "seite1"
        self.vorschau = False
        self.eigen = True
        try:
            v = lay.aus_dict(roh, self.basis) if roh else None
        except lay.LayoutAlt as e:
            # Layoutformat 1 (bis rc1): keine Übernahme, Datei bleibt unverändert – Start auf dem Standard
            log.warning("Layout-Vorlage %s abgelehnt: %s", profil, e)
            v = None
            self.alt_meldung = _(lay.ALT_TEXT).format(
                name=profil or "–", format=_(lay.format_text(e.gefunden))
            )
            QTimer.singleShot(0, self._alt_zeigen)
        except (lay.LayoutFehler, TypeError, ValueError) as e:
            log.warning("Layout-Vorlage %s nicht lesbar: %s – Standard geladen", profil, e)
            v = None
            QTimer.singleShot(
                0,
                lambda: self.toast(
                    "fehler",
                    _("Gespeichertes Layout nicht lesbar"),
                    _("Standard geladen. Details stehen im Log."),
                ),
            )
        self.vorlage = v or lay.standard()
        self.vorlage.basis = self.basis
        self._beispiel = {
            n: beispielrechnung.rechnung(
                verkaeufer if verkaeufer and verkaeufer.name else None,
                n,
                zahlung if zahlung and zahlung.iban else None,
            )
            for n in (3, 40)
        }
        self.bericht: list[str] = []
        self._signal = _Pruefsignal()
        self._signal.fertig.connect(self._briefpapier_geprueft)
        self._pruefung_laeuft = False
        self._aufbauen()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.neu_zeichnen)
        self.seite_zeigen("seite1")

    # ------------------------------------------------------------------ Aufbau
    def _aufbauen(self) -> None:
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.setSpacing(0)

        leiste = QFrame()
        leiste.setObjectName("leiste")
        fl = FlussLayout(leiste)
        fl.setContentsMargins(12, 10, 12, 10)
        prof = lbl(_("Vorlage / Profil: {name}").format(name=self.profil or "–"), "titel")
        prof.setMinimumHeight(48)
        fl.addWidget(prof)
        self.b_brief = knopf(_("Briefpapier laden…"), klick=self.briefpapier_knopf)
        self.b_brief_weg = knopf(_("Briefpapier entfernen"), klick=self.briefpapier_entfernen)
        self.b_raster = knopf(_("Raster an"), klick=self._raster_umschalten)
        self.b_raster.setCheckable(True)
        self.b_raster.setChecked(self.vorlage.raster_an)
        self.b_s1 = knopf(_("Seite 1"), klick=lambda: self.seite_zeigen("seite1"))
        self.b_sf = knopf(_("Folgeseite"), klick=lambda: self.seite_zeigen("folgeseite"))
        grp = QButtonGroup(self)
        for b in (self.b_s1, self.b_sf):
            b.setCheckable(True)
            grp.addButton(b)
        self.b_s1.setChecked(True)
        self.b_vorschau = knopf(_("Vorschau mit Beispieldaten"), klick=self._vorschau_umschalten)
        self.b_vorschau.setCheckable(True)
        self.b_standard = knopf(_("Zurücksetzen auf Standard"), klick=self.zuruecksetzen)
        self.b_abbrechen = knopf(_("Abbrechen"), klick=self.reject)
        self.b_speichern = knopf(_("Speichern"), primary=True, klick=self.speichern)
        for b in (
            self.b_brief,
            self.b_brief_weg,
            self.b_raster,
            self.b_s1,
            self.b_sf,
            self.b_vorschau,
            self.b_standard,
            self.b_abbrechen,
            self.b_speichern,
        ):
            fl.addWidget(b)
        aussen.addWidget(leiste)

        teiler = QSplitter(Qt.Orientation.Horizontal)
        teiler.setChildrenCollapsible(False)
        # --- links: Bausteine
        links = QWidget()
        lv = QVBoxLayout(links)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(8)
        lv.addWidget(lbl(_("Bausteine"), "sektion"))
        lv.addWidget(
            lbl(
                _(
                    "Schloss = dieser Baustein bleibt nötig (Empfänger, Kopf, Positionen, Summen). Absender und "
                    "Fußzeile kannst du ausblenden, wenn die Angaben schon im Briefpapier oder in einem anderen "
                    "Baustein stehen. Häkchen = sichtbar."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self.liste = QListWidget()
        self.liste.setObjectName("bausteine")
        self.liste.setAccessibleName(_("Bausteine"))
        self.liste.setWordWrap(True)
        self.liste.setStyleSheet(
            f"QListWidget::item {{ min-height:48px; padding-left:6px; }}"
            f"QListWidget::item:selected {{ background:{self.c['sel']}; color:{self.c['fg']}; }}"
            "QListWidget::indicator { width:24px; height:24px; }"
        )
        self.liste.itemChanged.connect(self._liste_haken)
        self.liste.currentRowChanged.connect(self._liste_gewaehlt)
        lv.addWidget(self.liste, 1)
        self.b_text = knopf(_("Textfeld hinzufügen"), klick=lambda: self.feld_hinzufuegen("text"))
        self.b_bild = knopf(_("Bildfeld hinzufügen…"), klick=lambda: self.feld_hinzufuegen("bild"))
        self.b_loeschen = knopf(_("Feld löschen"), danger=True, klick=self.feld_loeschen)
        self.b_vor = knopf(_("Ebene nach vorn"), klick=lambda: self.ebene(+1))
        self.b_zurueck = knopf(_("Ebene nach hinten"), klick=lambda: self.ebene(-1))
        for b in (self.b_text, self.b_bild, self.b_loeschen, self.b_vor, self.b_zurueck):
            lv.addWidget(b)
        links.setMinimumWidth(250)
        teiler.addWidget(self._rolle(links))

        # --- Mitte: Seite
        self.szene = QGraphicsScene(self)
        self.szene.setSceneRect(
            QRectF(-8 * S, -10 * S, (lay.SEITE_B + 16) * S, (lay.SEITE_H + 18) * S)
        )
        schatten = QGraphicsRectItem(QRectF(1 * S, 1 * S, lay.SEITE_B * S, lay.SEITE_H * S))
        schatten.setBrush(QColor(0, 0, 0, 40))
        schatten.setPen(Qt.PenStyle.NoPen)
        schatten.setZValue(-2)
        self.szene.addItem(schatten)
        self.blatt = QGraphicsPixmapItem()
        self.blatt.setZValue(0)
        self.blatt.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.szene.addItem(self.blatt)
        self.raster_item = Raster(self)
        self.szene.addItem(self.raster_item)
        mitte = QWidget()
        mv = QVBoxLayout(mitte)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        self.seiten_info = lbl("", "sub")
        self.seiten_info.setContentsMargins(12, 6, 12, 6)
        self.seiten_info.setWordWrap(True)
        mv.addWidget(self.seiten_info)
        self.ansicht = Ansicht(self, self.szene)
        self.ansicht.setMinimumWidth(320)
        mv.addWidget(self.ansicht, 1)
        teiler.addWidget(mitte)

        # --- rechts: Eigenschaften
        rechts = QWidget()
        rv = QVBoxLayout(rechts)
        rv.setContentsMargins(12, 12, 12, 12)
        rv.setSpacing(6)
        rv.addWidget(lbl(_("Eigenschaften"), "sektion"))
        self.e_titel = lbl("", "titel", umbruch=True)
        rv.addWidget(self.e_titel)
        self.e_hinweis = lbl("", "hinweis", umbruch=True)
        rv.addWidget(self.e_hinweis)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for schl, name in (
            ("x", "X (mm)"),
            ("y", "Y (mm)"),
            ("breite", "Breite (mm)"),
            ("hoehe", "Höhe (mm)"),
            ("schrift", "Schriftgröße (pt)"),
        ):
            rv.addWidget(lbl(_(name)))
            sp = QDoubleSpinBox()
            sp.setObjectName(f"eig_{schl}")
            sp.setAccessibleName(_(name))
            sp.setDecimals(1)
            sp.setSingleStep(0.5 if schl == "schrift" else 1.0)
            sp.setRange(4, 40) if schl == "schrift" else sp.setRange(0, lay.SEITE_H)
            sp.setMinimumHeight(48)
            sp.setKeyboardTracking(False)
            sp.setButtonSymbols(
                QAbstractSpinBox.ButtonSymbols.NoButtons
            )  # Klickziele: Tippen/Pfeiltasten
            sp.valueChanged.connect(lambda w, s=schl: self._wert(s, w))
            rv.addWidget(sp)
            self.spins[schl] = sp
        self.l_ausr = lbl(_("Ausrichtung"))
        rv.addWidget(self.l_ausr)
        ah = QHBoxLayout()
        ah.setSpacing(6)
        self.ausr_gruppe = QButtonGroup(self)
        self.ausr: dict[str, QPushButton] = {}
        for code, name in (("links", "Links"), ("mitte", "Mitte"), ("rechts", "Rechts")):
            b = knopf(_(name), klick=lambda _c=False, k=code: self._ausrichten(k))
            b.setCheckable(True)
            self.ausr_gruppe.addButton(b)
            ah.addWidget(b)
            self.ausr[code] = b
        rv.addLayout(ah)
        self.sichtbar = QCheckBox(_("Sichtbar"))
        self.sichtbar.setObjectName("eig_sichtbar")
        self.sichtbar.setMinimumHeight(32)
        self.sichtbar.toggled.connect(self._sichtbar)
        rv.addWidget(self.sichtbar)
        # Layoutformat 2: welche Verkäufer-Angaben zeigt der Baustein?
        self.l_angaben = lbl(_("Dieser Baustein zeigt:"), "sektion")
        rv.addWidget(self.l_angaben)
        self.angaben: dict[str, QCheckBox] = {}
        for a in lay.ANGABEN:
            cb = QCheckBox(_(lay.ANGABEN_NAMEN[a]))
            cb.setObjectName(f"angabe_{a}")
            cb.setMinimumHeight(32)
            cb.toggled.connect(lambda an, a=a: self._angabe(a, an))
            rv.addWidget(cb)
            self.angaben[a] = cb
        self.l_angaben_hinweis = lbl("", "hinweis", umbruch=True)
        rv.addWidget(self.l_angaben_hinweis)
        self.l_text = lbl(_("Text"))
        rv.addWidget(self.l_text)
        self.text = QPlainTextEdit()
        self.text.setObjectName("eig_text")
        self.text.setAccessibleName(_("Text"))
        self.text.setMinimumHeight(96)
        self.text.textChanged.connect(self._text)
        rv.addWidget(self.text)
        self.b_platzhalter = knopf(_("Platzhalter einfügen…"), klick=self.platzhalter_menue)
        self.b_platzhalter.setObjectName("platzhalter")
        rv.addWidget(self.b_platzhalter)
        self.l_platzhalter = lbl(
            _(
                "Platzhalter wie {Bestellnummer} oder {BT-13} füllt Fakturafalter beim Erzeugen mit dem Wert aus "
                "der Rechnung bzw. der CSV-Spalte (nur Kopfwerte). Fehlt ein Wert, bleibt die Stelle leer."
            ),
            "hinweis",
            umbruch=True,
        )
        rv.addWidget(self.l_platzhalter)
        self.b_bildwahl = knopf(_("Bild wählen…"), klick=self._bild_waehlen)
        rv.addWidget(self.b_bildwahl)
        self.e_ebene = lbl("", "hinweis", umbruch=True)
        rv.addWidget(self.e_ebene)
        rv.addStretch(1)
        rechts.setMinimumWidth(260)
        teiler.addWidget(self._rolle(rechts))
        teiler.setStretchFactor(0, 0)
        teiler.setStretchFactor(1, 1)
        teiler.setStretchFactor(2, 0)
        teiler.setSizes([290, 800, 310])
        aussen.addWidget(teiler, 1)

        fuss = QFrame()
        fuss.setObjectName("leiste")
        fh = QHBoxLayout(fuss)
        fh.setContentsMargins(12, 6, 12, 6)
        sv = QVBoxLayout()
        sv.setSpacing(4)
        self.status = lbl("", "sub", umbruch=True)
        self.status.setMinimumHeight(40)
        sv.addWidget(self.status)
        # Pflichtangaben (§ 14 Abs. 4 UStG): rot = fehlt (blockiert Speichern), gelb = doppelt (Hinweis)
        self.pruef_fehler = lbl("", "", umbruch=True)
        self.pruef_fehler.setObjectName("pruef_fehler")
        self.pruef_doppelt = lbl("", "", umbruch=True)
        self.pruef_doppelt.setObjectName("pruef_doppelt")
        hb = QHBoxLayout()
        hb.setSpacing(8)
        hb.addWidget(self.pruef_fehler, 1)
        hb.addWidget(self.pruef_doppelt, 1)
        sv.addLayout(hb)
        fh.addLayout(sv, 1)
        self.b_eigen = knopf(_("Eigenes Layout anlegen"), klick=self._eigen_anlegen)
        fh.addWidget(self.b_eigen)
        self.brief_status = lbl("", "sub", umbruch=True)
        fh.addWidget(self.brief_status)
        aussen.addWidget(fuss)

    def _rolle(self, w: QWidget) -> QScrollArea:
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(w)
        s.setFrameShape(QFrame.Shape.NoFrame)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return s

    def toast(self, art, titel, detail=""):
        return self.toasts.zeigen(self.c, art, titel, detail)

    # ------------------------------------------------------------------ Zustand
    @property
    def seite(self) -> lay.Seite:
        return self.vorlage.seite(self.seite_name)

    def einrasten(self, w: float) -> float:
        if not self.vorlage.raster_an:
            return round(w, 1)
        r = self.vorlage.raster or 5
        return round(round(w / r) * r, 2)

    def seite_zeigen(self, name: str) -> None:
        self.seite_name = name
        (self.b_s1 if name == "seite1" else self.b_sf).setChecked(True)
        self._items_neu()
        self.neu_zeichnen()

    def _items_neu(self, waehlen: lay.Element | None = None) -> None:
        self._laden = True
        for it in self._items:
            self.szene.removeItem(it)
        self._items = []
        folge = self.seite.zeichenfolge()
        for z, e in enumerate(folge):
            it = BlockItem(self, e)
            it.setZValue(10 + z)
            it.setVisible(e.sichtbar and self.eigen and not self.vorschau)
            self.szene.addItem(it)
            self._items.append(it)
        self.liste.blockSignals(True)
        self.liste.clear()
        schloss = schloss_symbol(self.c["fg"])
        for e in self._listen_reihenfolge():
            it = QListWidgetItem(self._listen_name(e))
            it.setData(Qt.ItemDataRole.UserRole, id(e))
            it.setSizeHint(QSize(10, 48))
            if e.pflicht:
                it.setIcon(schloss)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it.setToolTip(_("Bleibt nötig (Pflichtangaben nach § 14 Abs. 4 UStG)"))
            else:
                it.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                it.setCheckState(Qt.CheckState.Checked if e.sichtbar else Qt.CheckState.Unchecked)
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        self._laden = False
        self._regeln_markieren()
        if waehlen is not None:
            self.waehlen(waehlen)
        else:
            self.auswahl_geaendert()
        self._infos()

    def _listen_reihenfolge(self) -> list[lay.Element]:
        return [self.seite.bausteine[k] for k in lay.BAUSTEINE if k in self.seite.bausteine] + list(
            self.seite.felder
        )

    def _listen_name(self, e: lay.Element) -> str:
        if e.art == "text":
            return _("Textfeld") + (f": {e.text.splitlines()[0][:24]}" if e.text.strip() else "")
        if e.art == "bild":
            return _("Bildfeld") + (f": {Path(e.datei).name[:24]}" if e.datei else "")
        return _(lay.NAMEN[e.art])

    def element(self) -> lay.Element | None:
        sel = [i for i in self._items if i.isSelected()]
        if sel:
            return sel[0].e
        it = self.liste.currentItem()
        if it is None:
            return None
        k = it.data(Qt.ItemDataRole.UserRole)
        return next((e for e in self.seite.elemente() if id(e) == k), None)

    def waehlen(self, e: lay.Element) -> None:
        self._laden = True
        for it in self._items:
            it.setSelected(it.e is e)
        for i in range(self.liste.count()):
            if self.liste.item(i).data(Qt.ItemDataRole.UserRole) == id(e):
                self.liste.setCurrentRow(i)
        self._laden = False
        self.auswahl_geaendert()

    def auswahl_geaendert(self) -> None:
        e = self.element()
        if e is not None and not self._laden:
            self.liste.blockSignals(True)
            for i in range(self.liste.count()):
                if self.liste.item(i).data(Qt.ItemDataRole.UserRole) == id(e):
                    self.liste.setCurrentRow(i)
            self.liste.blockSignals(False)
        self.werte_zeigen()

    def werte_zeigen(self, live: bool = False) -> None:
        e = self.element()
        self._laden = True
        try:
            alle = (
                list(self.spins.values())
                + list(self.ausr.values())
                + [self.sichtbar, self.text, self.b_bildwahl]
            )
            for w in alle:
                w.setEnabled(e is not None and self.eigen)
            self.b_loeschen.setEnabled(bool(e is not None and e.eigen and self.eigen))
            frei = e is not None and not e.oben and self.eigen
            self.b_vor.setEnabled(frei)
            self.b_zurueck.setEnabled(frei)
            self._angaben_zeigen(e)
            self.b_platzhalter.setVisible(e is not None and e.art == "text")
            self.b_platzhalter.setEnabled(self.eigen)
            self.l_platzhalter.setVisible(e is not None and e.art == "text")
            if e is None:
                self.e_titel.setText(_("Nichts gewählt"))
                self.e_hinweis.setText(_("Baustein links oder auf der Seite anklicken."))
                self.e_ebene.setText("")
                return
            self.e_titel.setText(self._listen_name(e))
            if e.pflicht:
                self.e_hinweis.setText(
                    _(
                        "Pflichtangabe nach § 14 Abs. 4 UStG. Der Baustein bleibt sichtbar und "
                        "liegt immer über allen anderen."
                    )
                )
            elif e.art in ("absender", "fusszeile"):
                self.e_hinweis.setText(
                    _(
                        "Dieser Baustein ist nicht fest vorgeschrieben. Du kannst ihn ausblenden, wenn die "
                        "Angaben schon im Briefpapier oder in einem anderen Baustein stehen."
                    )
                )
            elif e.art == "zahlung":
                self.e_hinweis.setText(
                    _(
                        "Freiwillig. Ausgeblendet stehen vereinbarte Skonti trotzdem im "
                        "Summenblock (§ 14 Abs. 4 Nr. 7 UStG)."
                    )
                )
            elif e.eigen:
                self.e_hinweis.setText(_("Eigenes Feld, nur Gestaltung – geht nicht in die XML."))
            else:
                self.e_hinweis.setText(_("Freiwillig, lässt sich ausblenden."))
            for schl, sp in self.spins.items():
                if not (live and sp.hasFocus()):
                    sp.setValue(getattr(e, schl))
            self.spins["x"].setMaximum(lay.SEITE_B)
            self.spins["breite"].setMaximum(lay.SEITE_B)
            mit_schrift = e.art not in ("logo", "bild")
            self.spins["schrift"].setEnabled(mit_schrift and self.eigen)
            mit_ausr = e.art not in lay.OHNE_AUSRICHTUNG
            for k, b in self.ausr.items():
                b.setEnabled(mit_ausr and self.eigen)
                b.setChecked(k == e.ausrichtung)
            self.sichtbar.setChecked(e.sichtbar)
            self.sichtbar.setEnabled(not e.pflicht and self.eigen)
            self.sichtbar.setText(
                _("Sichtbar") if not e.pflicht else _("Sichtbar (nicht änderbar)")
            )
            ist_text = e.art == "text"
            self.l_text.setVisible(ist_text)
            self.text.setVisible(ist_text)
            if ist_text and self.text.toPlainText() != e.text:
                self.text.setPlainText(e.text)
            self.b_bildwahl.setVisible(e.art in ("logo", "bild"))
            if e.oben:
                self.e_ebene.setText(_("Ebene: oben (fest)"))
            else:
                frei_e = sorted(
                    (x for x in self.seite.elemente() if not x.oben), key=lambda x: x.ebene
                )
                self.e_ebene.setText(
                    _("Ebene {n} von {m} (darüber liegen Absender, Fußzeile und die Pflichtbausteine)").format(
                        n=frei_e.index(e) + 1, m=len(frei_e)
                    )
                )
        finally:
            self._laden = False

    def _infos(self) -> None:
        bp = self.seite.briefpapier
        titel = _("Seite 1") if self.seite_name == "seite1" else _("Folgeseite")
        self.seiten_info.setText(
            _("{seite} · A4 (210 × 297 mm) · Briefpapier: {bp}").format(
                seite=titel, bp=Path(bp).name if bp else _("keins")
            )
        )
        self.b_brief_weg.setEnabled(bool(bp) and self.eigen)
        self.b_brief.setEnabled(self.eigen and not self._pruefung_laeuft)
        for b in (self.b_text, self.b_bild, self.b_raster):
            b.setEnabled(self.eigen)
        self.b_eigen.setVisible(not self.eigen)
        self.b_raster.setText(_("Raster an") if self.vorlage.raster_an else _("Raster aus"))
        self.raster_item.setVisible(self.vorlage.raster_an and self.eigen and not self.vorschau)
        f = self.fehler_liste() if self.eigen else []
        self._pruefung_zeigen()
        if not self.eigen:
            txt = _("Standardlayout (fest, wie bisher). Zum Gestalten „Eigenes Layout anlegen“.")
        elif f:
            txt = _("Bitte korrigieren: {fehler}").format(fehler=f[0]) + (
                f" (+{len(f) - 1})" if len(f) > 1 else ""
            )
        else:
            txt = _(
                "Bereit. Raster {r} mm · {seite} · Profil „{p}“. Details stehen im Log."
            ).format(r=f"{self.vorlage.raster:g}", seite=titel, p=self.profil or "–")
        if self.bericht and self.eigen:
            txt += " · " + _("Hinweis: {t}").format(t=self.bericht[0])
        self.status.setText(txt)
        self.b_brief.setText(_("Briefpapier…") if bp else _("Briefpapier laden…"))

    def _regeln_markieren(self) -> None:
        pfl = [i for i in self._items if lay.traegt_pflicht(i.e)]
        for i in self._items:
            i.fehler = lay.traegt_pflicht(i.e) and any(
                lay.ueberlappen(i.e, j.e) for j in pfl if j is not i
            )
            i.update()

    # ------------------------------------------------------------------ Pflichtangaben (Layoutformat 2)
    def pflichtbefund(self) -> lay.Pflichtbefund:
        return lay.pflicht_pruefen(self.vorlage, self.verkaeufer, self.zahlung, _)

    def fehler_liste(self) -> list[str]:
        """Alles, was Speichern blockiert: feste Regeln und fehlende Pflichtangaben."""
        return lay.pruefen(self.vorlage, _) + self.pflichtbefund().fehler

    def _pruefung_zeigen(self) -> None:
        c = self.c
        if not self.eigen:
            self.pruef_fehler.setVisible(False)
            self.pruef_doppelt.setVisible(False)
            return
        b = self.pflichtbefund()
        rot = b.fehler
        gelb = b.doppelt + b.hinweise
        self.pruef_fehler.setText(
            (_("Fehlt (Speichern nicht möglich):") + "\n• " + "\n• ".join(rot)) if rot else ""
        )
        self.pruef_fehler.setVisible(bool(rot))
        self.pruef_fehler.setStyleSheet(
            f"background:{c['er_bg']}; color:{c['er_t']}; border:1px solid {c['err']}; "
            "border-radius:6px; padding:6px 10px;"
        )
        self.pruef_doppelt.setText(
            (_("Hinweis:") + "\n• " + "\n• ".join(gelb)) if gelb else ""
        )
        self.pruef_doppelt.setVisible(bool(gelb))
        self.pruef_doppelt.setStyleSheet(
            f"background:{c['in_bg']}; color:{c['in_t']}; border:1px solid {c['busy']}; "
            "border-radius:6px; padding:6px 10px;"
        )

    def _angaben_zeigen(self, e: lay.Element | None) -> None:
        erlaubt = lay.ANGABEN_JE.get(e.art, ()) if e is not None else ()
        self.l_angaben.setVisible(bool(erlaubt))
        for a, cb in self.angaben.items():
            cb.setVisible(a in erlaubt)
            cb.setEnabled(self.eigen and e is not None and e.sichtbar)
            cb.setChecked(bool(e is not None and a in (e.angaben or ())))
        hinweis = ""
        if e is not None and e.art == "empfaenger":
            hinweis = _("Rücksendezeile über der Anschrift (für Fensterkuverts). Standard: an.")
        elif e is not None and erlaubt:
            im_bp = [_(lay.ANGABEN_NAMEN[a]) for a in erlaubt if self.seite.im_briefpapier(a)]
            if im_bp:
                hinweis = _("Steht schon im Briefpapier, wird hier nicht gedruckt: {liste}").format(
                    liste=", ".join(im_bp)
                )
        self.l_angaben_hinweis.setText(hinweis)
        self.l_angaben_hinweis.setVisible(bool(hinweis))

    def _angabe(self, a: str, an: bool) -> None:
        e = self.element()
        if self._laden or e is None or a not in lay.ANGABEN_JE.get(e.art, ()):
            return
        neu = set(e.angaben or ())
        neu.add(a) if an else neu.discard(a)
        e.angaben = [x for x in lay.ANGABEN_JE[e.art] if x in neu]
        self.geaendert()

    def _alt_zeigen(self) -> None:
        """Ablehnung eines Layouts im Format 1 – nicht blockierend, die Datei bleibt unverändert."""
        import shiboken6

        if not shiboken6.isValid(self) or not self.alt_meldung:
            return
        self.toast("fehler", _(lay.ALT_TITEL), _("Start auf dem Standard. Mit „Speichern“ entsteht Layoutformat 2."))
        box = QMessageBox(self)
        box.setObjectName("layout_alt")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(_(lay.ALT_TITEL))
        box.setText(_(lay.ALT_TITEL))
        box.setInformativeText(self.alt_meldung)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        self._alt_box = box
        box.open()

    # ------------------------------------------------------------------ Platzhalter (rc2)
    def platzhalter_liste(self) -> list[tuple[str, list[tuple[str, str]]]]:
        """[(Gruppe, [(Anzeige, Platzhalter)])] – Rechnungsangaben (BT) und eigene, nicht zugeordnete Spalten."""
        from .. import csv_einrichtung as ce

        rechnung = []
        for bt in (
            "BT-1", "BT-2", "BT-9", "BT-10", "BT-11", "BT-12", "BT-13", "BT-14", "BT-15", "BT-16",
            "BT-17", "BT-18", "BT-19", "BT-25", "BT-44", "BT-46", "BT-56", "BT-72", "BT-73", "BT-74",
        ):
            label = ce.FELD[bt][1] if bt in ce.FELD else ce.STANDARD_NAME.get(bt, (bt,))[0]
            rechnung.append((f"{_(label)} ({bt})", "{" + bt + "}"))
        eigen = [(sp, "{" + sp + "}") for sp in self.spalten if "{" not in sp and "}" not in sp]
        out = [(_("Rechnungsangaben"), rechnung)]
        if eigen:
            out.append((_("Eigene Spalten aus deinen CSV-Profilen"), eigen))
        return out

    def platzhalter_einfuegen(self, ph: str) -> None:
        e = self.element()
        if e is None or e.art != "text" or not self.eigen:
            return
        self.text.insertPlainText(ph)
        self.text.setFocus()

    def platzhalter_menue(self) -> QMenu:
        m = QMenu(self)
        m.setObjectName("platzhalter_menue")
        for gruppe, eintraege in self.platzhalter_liste():
            m.addSection(gruppe)
            for anzeige, ph in eintraege:
                a = m.addAction(f"{anzeige}  {ph}" if not anzeige.startswith(ph) else anzeige)
                a.setData(ph)
                a.triggered.connect(lambda _c=False, ph=ph: self.platzhalter_einfuegen(ph))
        if not self.spalten:
            a = m.addAction(_("Eigene Spalten: tippe den Spaltennamen in geschweiften Klammern in den Text."))
            a.setEnabled(False)
        self._platzhalter_m = m
        if self.isVisible():
            m.popup(self.b_platzhalter.mapToGlobal(self.b_platzhalter.rect().bottomLeft()))
        return m

    # ------------------------------------------------------------------ Zeichnen
    def geaendert(self) -> None:
        self._regeln_markieren()
        self._infos()
        self._timer.start()

    def pdf(
        self, seite_name: str | None = None, vorlage: lay.Vorlage | None = None
    ) -> tuple[bytes, int]:
        """Beispiel-PDF über den Renderer der Ausgabe -> (PDF, Seitenindex für die gewählte Seite)."""
        seite_name = seite_name or self.seite_name
        r = self._beispiel[3 if seite_name == "seite1" else 40]
        self.bericht = []
        v = (vorlage or self.vorlage) if self.eigen else None
        return sicht.erzeugen(
            r, vorlage=v, bericht=self.bericht
        ), 0 if seite_name == "seite1" else 1

    def neu_zeichnen(self) -> None:
        try:
            daten, idx = self.pdf()
            dpr = self.ansicht.devicePixelRatioF() if self.ansicht.isVisible() else 1.0
            breite = int(max(600, min(2400, self.ansicht.viewport().width() * dpr * 1.5)))
            bild = seite_rendern(daten, idx, breite)
        except Exception as e:  # noqa: BLE001 – Vorschau darf den Editor nicht schließen
            log.exception("Layout-Vorschau fehlgeschlagen")
            self.toast("fehler", _("Vorschau nicht möglich"), f"{type(e).__name__}: {e}")
            return
        pm = QPixmap.fromImage(bild)
        self.blatt.setPixmap(pm)
        self.blatt.setScale(lay.SEITE_B * S / pm.width())
        for b in dict.fromkeys(self.bericht):
            log.info("Layout-Vorschau: %s", b)
        self._infos()

    # ------------------------------------------------------------------ Bedienung
    def _liste_gewaehlt(self, _row: int) -> None:
        if self._laden:
            return
        it = self.liste.currentItem()
        if it is None:
            return
        k = it.data(Qt.ItemDataRole.UserRole)
        e = next((x for x in self.seite.elemente() if id(x) == k), None)
        if e is not None:
            self._laden = True
            for i in self._items:
                i.setSelected(i.e is e)
            self._laden = False
            self.werte_zeigen()

    def _liste_haken(self, it: QListWidgetItem) -> None:
        if self._laden:
            return
        k = it.data(Qt.ItemDataRole.UserRole)
        e = next((x for x in self.seite.elemente() if id(x) == k), None)
        if e is None or e.pflicht:
            return
        an = it.checkState() == Qt.CheckState.Checked
        if an != e.sichtbar:
            self._sichtbar_setzen(e, an)

    def _sichtbar(self, an: bool) -> None:
        e = self.element()
        if self._laden or e is None or e.pflicht:
            return
        self._sichtbar_setzen(e, an)

    def _sichtbar_setzen(self, e: lay.Element, an: bool) -> None:
        e.sichtbar = an
        for i in self._items:
            if i.e is e:
                i.setVisible(an and not self.vorschau)
        self._items_neu(waehlen=e)
        self.geaendert()

    def _wert(self, schl: str, w: float) -> None:
        e = self.element()
        if self._laden or e is None:
            return
        if schl in ("x", "breite"):
            w = min(w, lay.SEITE_B - (e.breite if schl == "x" else e.x))
        if schl in ("y", "hoehe"):
            w = min(w, lay.SEITE_H - (e.hoehe if schl == "y" else e.y))
        if schl in ("breite", "hoehe"):
            w = max(lay.MIN_MASS, w)
        setattr(e, schl, round(w, 2))
        self._laden = True
        for i in self._items:
            if i.e is e:
                i.prepareGeometryChange()
                i.aus_element()
        self._laden = False
        self.geaendert()

    def _ausrichten(self, k: str) -> None:
        e = self.element()
        if e is None or self._laden:
            return
        e.ausrichtung = k
        self.geaendert()

    def _text(self) -> None:
        e = self.element()
        if self._laden or e is None or e.art != "text":
            return
        e.text = self.text.toPlainText()
        it = self.liste.currentItem()
        if it is not None:
            it.setText(self._listen_name(e))
        for i in self._items:
            if i.e is e:
                i.update()
        self.geaendert()

    def _raster_umschalten(self) -> None:
        self.vorlage.raster_an = self.b_raster.isChecked()
        self._infos()

    def _vorschau_umschalten(self) -> None:
        self.vorschau = self.b_vorschau.isChecked()
        for i in self._items:
            i.setVisible(i.e.sichtbar and self.eigen and not self.vorschau)
        self._infos()

    def _eigen_anlegen(self) -> None:
        self.eigen = True
        self.vorlage = lay.standard()
        self.vorlage.basis = self.basis
        self.b_raster.setChecked(self.vorlage.raster_an)
        self.seite_zeigen(self.seite_name)

    def zuruecksetzen(self) -> None:
        """Zurück auf das feste Standardlayout (wie ohne Vorlage); gespeichert wird erst mit „Speichern“."""
        self.eigen = False
        self.vorlage = lay.standard()
        self.vorlage.basis = self.basis
        self.seite_zeigen(self.seite_name)
        self.toast("info", _("Standardlayout eingestellt"), _("Mit „Speichern“ übernehmen."))

    def feld_hinzufuegen(self, art: str) -> None:
        datei = ""
        if art == "bild":
            pfad = self._bild_dialog()
            if pfad is None:
                return
            datei = self._datei_uebernehmen(pfad, "bild")
            if not datei:
                return
        n = 1 + max(
            [
                int(f.kennung[len(art) :])
                for f in self.seite.felder
                if f.art == art and f.kennung[len(art) :].isdigit()
            ]
            or [0]
        )
        ebene = 1 + max([x.ebene for x in self.seite.elemente() if not x.oben] or [0])
        e = lay.Element(
            art,
            20,
            150,
            70 if art == "text" else 40,
            15 if art == "text" else 25,
            schrift=10,
            ebene=ebene,
            text="Vielen Dank für Ihren Auftrag!" if art == "text" else "",
            datei=datei,
            kennung=f"{art}{n}",
        )
        self.seite.felder.append(e)
        self._items_neu(waehlen=e)
        self.geaendert()

    def feld_loeschen(self) -> None:
        e = self.element()
        if e is None or not e.eigen:
            return
        self.seite.felder = [f for f in self.seite.felder if f is not e]
        self._items_neu()
        self.geaendert()
        self.toast("info", _("Feld gelöscht"), self._listen_name(e))

    def ebene(self, richtung: int) -> None:
        """Nicht vorgeschriebene Bausteine und eigene Felder eine Ebene nach vorn (+1) oder hinten (−1).
        Pflichtbausteine bleiben immer darüber."""
        e = self.element()
        if e is None or e.oben:
            return
        frei = sorted((x for x in self.seite.elemente() if not x.oben), key=lambda x: x.ebene)
        i = frei.index(e)
        j = i + richtung
        if not 0 <= j < len(frei):
            self.toast(
                "info",
                _("Schon ganz vorn") if richtung > 0 else _("Schon ganz hinten"),
                _("Absender, Fußzeile und Pflichtbausteine liegen immer oben.") if richtung > 0 else "",
            )
            return
        frei[i], frei[j] = frei[j], frei[i]
        for n, x in enumerate(frei):
            x.ebene = n
        self._items_neu(waehlen=e)
        self.geaendert()

    # ------------------------------------------------------------------ Dateien
    def _bild_dialog(self) -> Path | None:
        d, _f = QFileDialog.getOpenFileName(
            self, _("Bild wählen"), str(Path.home()), _("Bilder (*.png *.jpg *.jpeg)")
        )
        return Path(d) if d else None

    def _datei_uebernehmen(self, pfad: Path, praefix: str) -> str:
        try:
            if praefix != "briefpapier":
                lay.bild_laden(pfad)
            return lay.datei_uebernehmen(pfad, self.basis, praefix)
        except Exception as e:  # noqa: BLE001
            log.warning("Layout: %s nicht übernommen: %s", pfad, e)
            self.toast("fehler", _("Datei nicht lesbar"), Path(pfad).name)
            return ""

    def _bild_waehlen(self) -> None:
        e = self.element()
        if e is None or e.art not in ("logo", "bild"):
            return
        pfad = self._bild_dialog()
        if pfad is not None:
            self.bild_setzen(e, pfad)

    def bild_setzen(self, e: lay.Element, pfad: Path) -> bool:
        datei = self._datei_uebernehmen(pfad, "logo" if e.art == "logo" else "bild")
        if not datei:
            return False
        if e.art == "logo":
            self.vorlage.logo = datei
        else:
            e.datei = datei
        self._items_neu(waehlen=e)
        self.geaendert()
        return True

    def briefpapier_waehlen(self) -> None:
        d, _f = QFileDialog.getOpenFileName(
            self, _("Briefpapier wählen"), str(Path.home()), _("PDF-Dateien (*.pdf)")
        )
        if d:
            self.briefpapier_laden(Path(d))

    def briefpapier_knopf(self) -> None:
        """„Briefpapier laden…“ bzw. „Briefpapier…“: liegt schon eines, öffnet der Dialog mit den Haken."""
        if self.seite.briefpapier:
            self.briefpapier_dialog(self.seite_name)
        else:
            self.briefpapier_waehlen()

    def briefpapier_dialog(self, seite: str | None = None) -> "BriefpapierDialog":
        dlg = BriefpapierDialog(self, seite or self.seite_name)
        self._brief_dlg = dlg
        dlg.open()
        return dlg

    def briefpapier_enthaelt_setzen(self, seite: str, angabe: str, an: bool) -> None:
        s = self.vorlage.seite(seite)
        neu = set(s.briefpapier_enthaelt)
        neu.add(angabe) if an else neu.discard(angabe)
        s.briefpapier_enthaelt = [a for a in lay.BRIEFPAPIER_ANGABEN if a in neu]
        if seite == self.seite_name:
            self.werte_zeigen()
        self.geaendert()

    def briefpapier_entfernen(self, seite: str | None = None) -> None:
        s = self.vorlage.seite(seite or self.seite_name)
        s.briefpapier = ""
        s.briefpapier_enthaelt = []
        self.brief_status.setText("")
        self.werte_zeigen()
        self.geaendert()

    def briefpapier_laden(self, pfad: Path, warten: bool = False) -> None:
        """Briefpapier prüfen: erst statisch (Schriften, Farben, Formulare …), dann – wenn die Prüfwerkzeuge da
        sind – eine Probe-Ausgabe mit veraPDF. Nicht taugliches Briefpapier wird als Bild (sRGB) übernommen;
        geht auch das nicht, wird es abgelehnt. Ergebnis als Toast, Gründe ins Log."""
        seite = self.seite_name
        befund = lay.briefpapier_pruefen(pfad)
        log.info(
            "Briefpapier %s: %s%s",
            pfad.name,
            "statisch tauglich" if befund.ok else "nicht PDF/A-tauglich",
            (" – " + "; ".join(befund.gruende)) if befund.gruende else "",
        )
        if befund.seiten == 0:
            self.toast(
                "fehler",
                _("Briefpapier abgelehnt"),
                _("PDF nicht lesbar oder verschlüsselt. Details stehen im Log."),
            )
            return
        if not befund.format_passt:
            self.toast("info", _("Briefpapier ist nicht A4"), _("Es wird auf A4 eingepasst."))
        if not befund.ok:
            self._als_bild(pfad, seite, befund.gruende)
            return
        datei = self._datei_uebernehmen(pfad, "briefpapier")
        if not datei:
            return
        if not validierung.bereit():
            self._briefpapier_setzen(seite, datei)
            self.toast(
                "info",
                _("Briefpapier übernommen"),
                _(
                    "Geprüft ohne veraPDF (Prüfwerkzeuge fehlen). Jede Rechnung wird nach dem Erstellen geprüft."
                ),
            )
            return
        self._pruefung_laeuft = True
        self.brief_status.setText(_("Briefpapier wird geprüft (veraPDF)…"))
        self._infos()
        probe = copy.deepcopy(self.vorlage)
        probe.seite(seite).briefpapier = datei
        args = (pfad, seite, datei, probe)
        if warten:
            self._signal.fertig.emit((*args, self._probe_pruefen(probe, seite)))
            return
        threading.Thread(
            target=lambda: self._signal.fertig.emit((*args, self._probe_pruefen(probe, seite))),
            daemon=True,
        ).start()

    def _probe_pruefen(self, probe: lay.Vorlage, seite: str) -> tuple[bool, list[str]]:
        """Beispielrechnung mit dem Briefpapier als ZUGFeRD-PDF bauen und mit Mustang/veraPDF prüfen."""
        from .. import cii

        r = self._beispiel[3 if seite == "seite1" else 40]
        try:
            pdf = pdfa.zugferd_pdf(
                sicht.erzeugen(r, vorlage=probe),
                cii.erzeugen(r, "EN16931"),
                titel="Probe",
                autor=r.verkaeufer.name,
            )
        except pdfa.NichtReparierbar as e:
            return False, [str(e)]
        except Exception as e:  # noqa: BLE001
            return False, [f"{type(e).__name__}: {e}"]
        with tempfile.TemporaryDirectory(prefix="fakturafalter-briefpapier-") as d:
            p = Path(d) / "probe.pdf"
            p.write_bytes(pdf)
            try:
                e = validierung.mustang(p)
            except Exception as ex:  # noqa: BLE001
                return True, [f"Prüfung nicht möglich: {ex}"]
            if e.technisch:
                return True, ["Prüfung technisch nicht möglich: " + "; ".join(e.fehler)]
            return e.gueltig, ([] if e.gueltig else (e.fehler or ["veraPDF: nicht konform"]))

    def _briefpapier_geprueft(self, ergebnis) -> None:
        import shiboken6

        if not shiboken6.isValid(self):  # Editor inzwischen geschlossen
            return
        pfad, seite, datei, _probe, (ok, gruende) = ergebnis
        self._pruefung_laeuft = False
        self.brief_status.setText("")
        if ok:
            for g in gruende:
                log.warning("Briefpapier %s: %s", pfad.name, g)
            self._briefpapier_setzen(seite, datei)
            self.brief_status.setText(_("Briefpapier ist PDF/A-tauglich"))
            self.toast("ok", _("Briefpapier ist PDF/A-tauglich"), Path(pfad).name)
        else:
            log.warning("Briefpapier %s: veraPDF/PDF-A: %s", pfad.name, "; ".join(gruende))
            self._als_bild(pfad, seite, gruende)
        self._infos()

    def _als_bild(self, pfad: Path, seite: str, gruende: list[str]) -> None:
        try:
            ziel = Path(tempfile.mkdtemp(prefix="fakturafalter-bp-")) / (pfad.stem + ".jpg")
            lay.briefpapier_als_bild(pfad, ziel)
            datei = lay.datei_uebernehmen(ziel, self.basis, "briefpapier")
            ziel.unlink(missing_ok=True)
            ziel.parent.rmdir()
        except Exception as e:  # noqa: BLE001
            log.warning("Briefpapier %s nicht umwandelbar: %s", pfad.name, e)
            self.toast(
                "fehler",
                _("Briefpapier abgelehnt"),
                _("Nicht PDF/A-tauglich und nicht umwandelbar. Details stehen im Log."),
            )
            return
        log.info(
            "Briefpapier %s als Bild übernommen (%s): %s", pfad.name, datei, "; ".join(gruende)
        )
        self._briefpapier_setzen(seite, datei)
        self.brief_status.setText(_("Briefpapier als Bild übernommen"))
        self.toast(
            "info",
            _("Briefpapier als Bild übernommen"),
            _("Das PDF war nicht PDF/A-tauglich ({grund}). Details stehen im Log.").format(
                grund=gruende[0] if gruende else "?"
            ),
        )

    def _briefpapier_setzen(self, seite: str, datei: str) -> None:
        self.vorlage.seite(seite).briefpapier = datei
        if seite == self.seite_name:
            self.geaendert()
        else:
            self._infos()
        import shiboken6

        if shiboken6.isValid(self) and self.isVisible():
            self.briefpapier_dialog(seite)  # gleich danach: was steht schon auf dem Briefpapier?

    # ------------------------------------------------------------------ Ergebnis
    def speichern(self) -> None:
        if self._pruefung_laeuft:
            self.toast("info", _("Briefpapier wird noch geprüft"), _("Bitte kurz warten."))
            return
        if self.eigen:
            f = self.fehler_liste()
            if f:
                self.toast("fehler", _("Layout so nicht speicherbar"), "\n".join(f[:4]))
                return
        self.accept()

    def ergebnis(self) -> dict | None:
        return self.vorlage.als_dict() if self.eigen else None


class BriefpapierDialog(QDialog):
    """„Briefpapier – Seite 1/Folgeseite“: Haken „Briefpapier enthält …“ (Layoutformat 2). Die Haken ändern die
    Bausteine nicht von allein; was angehakt ist, druckt Fakturafalter auf dieser Seite nicht noch einmal."""

    def __init__(self, editor: LayoutEditor, seite: str):
        super().__init__(editor)
        self.editor = editor
        self.seite_name = seite
        self.setObjectName("wurzel")
        titel = _("Briefpapier – Seite 1") if seite == "seite1" else _("Briefpapier – Folgeseite")
        self.setWindowTitle(titel)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(8)
        v.addWidget(lbl(titel, "titel"))
        s = editor.vorlage.seite(seite)
        self.l_datei = lbl(_("Datei: {name}").format(name=Path(s.briefpapier).name or _("keins")), "sub", umbruch=True)
        v.addWidget(self.l_datei)
        v.addWidget(lbl(_("Briefpapier enthält:"), "sektion"))
        self.haken: dict[str, QCheckBox] = {}
        for a in lay.BRIEFPAPIER_ANGABEN:
            cb = QCheckBox(_(lay.ANGABEN_NAMEN[a]))
            cb.setObjectName(f"brief_{a}")
            cb.setMinimumHeight(32)
            cb.setChecked(a in s.briefpapier_enthaelt)
            cb.toggled.connect(lambda an, a=a: editor.briefpapier_enthaelt_setzen(seite, a, an))
            v.addWidget(cb)
            self.haken[a] = cb
        v.addWidget(
            lbl(
                _(
                    "Was schon auf dem Briefpapier steht, druckt Fakturafalter nicht noch einmal. Die "
                    "Pflichtangaben müssen trotzdem irgendwo auf der Rechnung stehen – hier oder in einem Baustein. "
                    "Prüfe danach die Vorschau: Fakturafalter liest das Briefpapier nicht."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        self.b_anders = knopf(_("Anderes Briefpapier…"), klick=self._anders)
        self.b_weg = knopf(_("Briefpapier entfernen"), danger=True, klick=self._weg)
        self.b_fertig = knopf(_("Fertig"), primary=True, klick=self.accept)
        h.addWidget(self.b_anders)
        h.addWidget(self.b_weg)
        h.addStretch(1)
        h.addWidget(self.b_fertig)
        v.addLayout(h)
        self.resize(460, 520)

    def _anders(self) -> None:
        self.accept()
        self.editor.seite_zeigen(self.seite_name)
        self.editor.briefpapier_waehlen()

    def _weg(self) -> None:
        self.editor.briefpapier_entfernen(self.seite_name)
        self.accept()
