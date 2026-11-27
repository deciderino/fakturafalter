# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Durchsuchbare, gruppierte Feldauswahl für den CSV-Assistenten."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from .. import csv_einrichtung as ce
from .texte import _


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
        self.suche = QLineEdit()
        self.suche.setPlaceholderText(_("Feld suchen …"))
        self.suche.setClearButtonEnabled(True)
        self.suche.setMinimumHeight(48)
        self.suche.setAccessibleName(_("Feld suchen"))
        self.suche.textChanged.connect(self._fuellen)
        self.suche.returnPressed.connect(self._enter)
        v.addWidget(self.suche)
        self.liste = QListWidget()
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
            if it and it.flags() & Qt.ItemFlag.ItemIsSelectable and it.data(Qt.ItemDataRole.UserRole) is not None:
                self.liste.setCurrentItem(it)
                self._wahl(it, None)
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
            tip = ce.FELD_TOOLTIP.get(fid)
            if tip:
                it.setToolTip(_(tip))
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
        if fid and fid in ce.FELD_TOOLTIP:
            self.l_tip.setText(_(ce.FELD_TOOLTIP[fid]))
        elif fid and fid in ce.FELD:
            self.l_tip.setText(ce.FELD[fid][1])
        else:
            self.l_tip.setText("")
