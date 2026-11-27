# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Durchsuchbare, gruppierte Feldauswahl für den CSV-Assistenten."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from .. import csv_einrichtung as ce
from . import texte
from .texte import _

BT_ROLLE = Qt.ItemDataRole.UserRole + 7  # graue BT-Nummer neben dem Label (rc2)


def _farben_von(widget) -> dict:
    """Theme-Farben des Fensters (``c``), sonst aus der Palette geraten (hell/dunkel)."""
    from . import thema

    w = widget
    while w is not None:
        c = getattr(w, "c", None)
        if isinstance(c, dict) and "sub" in c:
            return c
        w = w.parentWidget() if hasattr(w, "parentWidget") else None
    hell = widget is None or widget.palette().base().color().lightness() >= 128
    return thema.farben(hell)


class BtDelegate(QStyledItemDelegate):
    """Zeichnet die amtliche BT-Nummer grau direkt hinter dem Label; markiert in Schriftfarbe (AA-Kontrast)."""

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        bt = index.data(BT_ROLLE)
        if not bt:
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        c = _farben_von(opt.widget)
        markiert = bool(opt.state & QStyle.StateFlag.State_Selected)
        style = opt.widget.style() if opt.widget is not None else None
        text_rect = (
            style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
            if style is not None
            else opt.rect
        )
        fm = opt.fontMetrics
        breite = fm.horizontalAdvance(opt.text)
        x = text_rect.left() + breite + fm.horizontalAdvance("  ") + 4
        if x >= text_rect.right() - 10:
            return
        painter.save()
        f = QFont(opt.font)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(QColor(c["fg"] if markiert else c["sub"]))
        r = text_rect.adjusted(x - text_rect.left(), 0, 0, 0)
        painter.drawText(r, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), fm.elidedText(bt, Qt.TextElideMode.ElideRight, r.width()))
        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802 (Qt)
        h = super().sizeHint(option, index)
        bt = index.data(BT_ROLLE)
        if bt:
            h.setWidth(h.width() + option.fontMetrics.horizontalAdvance(f"  {bt}") + 8)
        return h


def feld_tooltip(fid: str) -> str:
    """Tooltip im Assistenten: Erklärung (übersetzt) plus „Im Standard: …“ (rc2)."""
    tip = ce.FELD_TOOLTIP.get(fid)
    return ce.tooltip(fid, texte.sprache(), _(tip) if tip else (ce.FELD[fid][1] if fid in ce.FELD else ""))


class _SuchZeile(QLineEdit):
    """Escape leert die Suche (statt den Dialog zu schließen), solange etwas drinsteht."""

    def keyPressEvent(self, ev) -> None:  # noqa: N802 (Qt)
        if ev.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            ev.accept()
            return
        super().keyPressEvent(ev)


class FeldSuche(QWidget):
    """Suchfeld plus gruppierte Liste. Keine freie Eingabe neuer Schlüssel."""

    geaendert = Signal(str)  # Feld-ID oder ""

    def __init__(self, parent=None, wiederholend: bool = False) -> None:
        super().__init__(parent)
        self._wiederholend = wiederholend
        self._sperre = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.l_beispiel = QLabel("")
        self.l_beispiel.setObjectName("hinweis")
        self.l_beispiel.setWordWrap(True)
        v.addWidget(self.l_beispiel)
        self.suche = _SuchZeile()
        self.suche.setPlaceholderText(_("Feld suchen …"))
        self.suche.setClearButtonEnabled(True)
        self.suche.setMinimumHeight(48)
        self.suche.setAccessibleName(_("Feld suchen"))
        self.suche.textChanged.connect(self._fuellen)
        self.suche.returnPressed.connect(self._enter)
        v.addWidget(self.suche)
        self.liste = QListWidget()
        self.liste.setItemDelegate(BtDelegate(self.liste))
        self.liste.setMinimumHeight(180)
        self.liste.currentItemChanged.connect(self._wahl)
        v.addWidget(self.liste, 1)
        self.l_tip = QLabel("")
        self.l_tip.setObjectName("hinweis")
        self.l_tip.setWordWrap(True)
        v.addWidget(self.l_tip)
        self._fuellen()

    def set_wiederholend(self, an: bool) -> None:
        if bool(an) == self._wiederholend:
            return
        self._wiederholend = bool(an)
        self._fuellen()

    def set_beispiel(self, text: str) -> None:
        text = (text or "").strip()
        self.l_beispiel.setText(_("Beispielwert: {w}").format(w=text) if text else "")
        self.l_beispiel.setVisible(bool(text))

    def set_feld(self, fid: str) -> None:
        self._sperre = True
        try:
            self.suche.blockSignals(True)
            # Suche nicht löschen, wenn der Nutzer filtert; beim Setzen von außen leeren
            self.suche.clear()
            self.suche.blockSignals(False)
            self._fuellen()
            self._markieren(fid or "", suche_leeren=True)
        finally:
            self._sperre = False

    def feld(self) -> str:
        it = self.liste.currentItem()
        if it is None or not it.data(Qt.ItemDataRole.UserRole) and it.data(Qt.ItemDataRole.UserRole) != "":
            return ""
        val = it.data(Qt.ItemDataRole.UserRole)
        return "" if val is None else str(val)

    def _enter(self) -> None:
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            if it and it.flags() & Qt.ItemFlag.ItemIsSelectable and it.data(Qt.ItemDataRole.UserRole):
                if self.liste.currentItem() is it:
                    self._wahl(it, None)  # schon markiert: trotzdem bestätigen
                else:
                    self.liste.setCurrentItem(it)  # löst _wahl über das Signal aus
                return

    def _markieren(self, fid: str, *, suche_leeren: bool = False) -> None:
        self.liste.blockSignals(True)
        treffer = None
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == fid:
                treffer = it
                break
        if treffer is None and fid and suche_leeren:
            self.suche.blockSignals(True)
            self.suche.clear()
            self.suche.blockSignals(False)
            self.liste.blockSignals(False)
            self._fuellen()
            self._markieren(fid, suche_leeren=False)
            return
        if treffer is not None:
            self.liste.setCurrentItem(treffer)
        self.liste.blockSignals(False)
        self._tip(fid)

    def _fuellen(self) -> None:
        aktuell = ""
        cur = self.liste.currentItem()
        if cur is not None and cur.data(Qt.ItemDataRole.UserRole) is not None:
            aktuell = str(cur.data(Qt.ItemDataRole.UserRole))
        self.liste.blockSignals(True)
        self.liste.clear()
        leer = QListWidgetItem(_("– nicht verwenden –"))
        leer.setData(Qt.ItemDataRole.UserRole, "")
        self.liste.addItem(leer)
        frage = self.suche.text().strip()
        ids = ce.suche_felder(frage, wiederholend=self._wiederholend)
        gesehen: set[str] = set()
        fett = QFont(self.font())
        fett.setBold(True)
        for fid in ids:
            if fid in gesehen:
                continue
            g = ce.FELD_GRUPPE.get(fid)
            if g and g not in gesehen:
                # Gruppenkopf, wenn mindestens ein Treffer in der Gruppe
                kopf = QListWidgetItem(_(ce.GRUPPE_TITEL.get(g, g)))
                kopf.setFlags(Qt.ItemFlag.NoItemFlags)
                kopf.setFont(fett)
                self.liste.addItem(kopf)
                gesehen.add(g)
            gesehen.add(fid)
            it = QListWidgetItem(ce.anzeige_feld(fid))
            it.setData(Qt.ItemDataRole.UserRole, fid)
            it.setData(BT_ROLLE, ce.bt_kurz(fid))
            it.setData(Qt.ItemDataRole.AccessibleTextRole, ce.anzeige_feld(fid, mit_bt=True))
            it.setToolTip(feld_tooltip(fid))
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        self._markieren(aktuell)

    def _wahl(self, aktuell: QListWidgetItem | None, _alt) -> None:
        if aktuell is None or not (aktuell.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        fid = aktuell.data(Qt.ItemDataRole.UserRole)
        fid = "" if fid is None else str(fid)
        self._tip(fid)
        if not self._sperre:
            self.geaendert.emit(fid)

    def _tip(self, fid: str) -> None:
        if fid and fid in ce.FELD:
            self.l_tip.setText(feld_tooltip(fid))
        else:
            self.l_tip.setText("")
