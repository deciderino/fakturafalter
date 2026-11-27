# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Farbige Block-Tabelle und Spalten-je-Block im CSV-Assistenten (ab 0.9.10)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import csv_bloecke
from .. import csv_einrichtung as ce
from . import thema
from .feldsuche import FeldSuche
from .texte import _

# Fallback-Konstanten (hell); laufende Palette kommt aus thema.block_palette().
HINWEIS_RD = "#c05621"
WARN_HG_HELL, WARN_T_HELL = "#fff5f5", "#c53030"
WARN_HG_DUNKEL, WARN_T_DUNKEL = "#3b2a2a", "#fecaca"
LINIE_HELL, LINIE_DUNKEL = "#d0d5dd", "#4a5568"

TYPEN = ("kopf", "positionen", "summen", "zahlung", "lieferung")


def typ_name(typ: str) -> str:
    return {
        "kopf": _("Kopf"),
        "kunde": _("Kunde"),
        "beleg": _("Beleg"),
        "positionen": _("Positionen"),
        "summen": _("Summen"),
        "zahlung": _("Zahlung"),
        "lieferung": _("Lieferung"),
    }.get(typ, typ or _("Block"))


def aktuelle_palette(hell: bool | None = None) -> dict[str, tuple[str, str, str]]:
    if hell is None:
        hell = True
    return thema.block_palette(bool(hell))


def warn_farben(hell: bool) -> tuple[str, str, str]:
    if hell:
        return WARN_HG_HELL, WARN_T_HELL, LINIE_HELL
    return WARN_HG_DUNKEL, WARN_T_DUNKEL, LINIE_DUNKEL


def im_block(typ: str) -> str:
    return {
        "kopf": _("Im Kopf"),
        "positionen": _("In den Positionen"),
        "summen": _("In den Summen"),
        "zahlung": _("In der Zahlung"),
        "lieferung": _("In der Lieferung"),
    }.get(typ, _("Im Block „{t}“").format(t=typ_name(typ)))


def typ_schluessel(typ: str, wiederholend: bool = False) -> str:
    if wiederholend or typ == "positionen":
        return "positionen"
    if typ in ("summen", "zahlung", "lieferung"):
        return typ
    return "kopf"  # kopf, kunde, beleg, freie Namen


def typ_farbe(typ: str, wiederholend: bool = False, palette=None) -> tuple[QColor, QColor, QColor]:
    """Hintergrund, Schrift, Rand."""
    pal = palette or thema.block_palette(True)
    key = typ_schluessel(typ, wiederholend)
    hg, fg, rk = pal.get(key) or pal["kopf"]
    return QColor(hg), QColor(fg), QColor(rk)


class _AuswahlDelegate(QStyledItemDelegate):
    """Auswahl als transparente Auflage, damit Blockfarbe und Schrift bleiben."""

    def __init__(self, tabelle: "BlockTabelle", parent=None):
        super().__init__(parent)
        self._t = tabelle

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, opt, index)
        if option.state & QStyle.StateFlag.State_Selected:
            overlay = QColor(0, 0, 0, 36) if self._t._hell else QColor(255, 255, 255, 40)
            painter.fillRect(option.rect, overlay)


class _Farbkasten(QWidget):
    def __init__(self, farbe: QColor, rahmen: QColor, parent=None):
        super().__init__(parent)
        self._f, self._r = farbe, rahmen
        self.setFixedSize(16, 16)

    def paintEvent(self, ev):
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setPen(QPen(self._r, 1.5))
        q.setBrush(QBrush(self._f))
        q.drawRoundedRect(1, 1, 14, 14, 3, 3)
        q.end()


class BlockTabelle(QTableWidget):
    """CSV als farbige Tabelle: Blöcke, Marker, Kopfzeilen; Markieren und Grenzen ziehen."""

    block_gesetzt = Signal()
    cursor_block = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zeilen: list[list[str]] = []
        self.bloecke: list[dict] = []
        self.satzart_spalte = None
        self._hell = True
        self._ziehen_ursprung: int | None = None
        self._ziehen_vorschau: int | None = None
        self._mark_start: int | None = None
        self._auto_y = 0.0
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(40)
        self._auto_timer.timeout.connect(self._auto_tick)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setShowGrid(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoScroll(True)
        self.itemSelectionChanged.connect(self._sel)
        self.setMouseTracking(True)
        self.setItemDelegate(_AuswahlDelegate(self, self))

    def set_hell(self, hell: bool) -> None:
        self._hell = bool(hell)
        self._stil()

    def _stil(self) -> None:
        if self._hell:
            self.setStyleSheet("")
        else:
            self.setStyleSheet(
                "QTableWidget { background: #1a202c; color: #e2e8f0; gridline-color: #4a5568; }"
                "QHeaderView::section { background: #2d3748; color: #e2e8f0; padding: 4px; "
                "border: 1px solid #4a5568; }"
                "QTableCornerButton::section { background: #2d3748; border: 1px solid #4a5568; }"
            )

    def _palette(self) -> dict[str, tuple[str, str, str]]:
        return thema.block_palette(self._hell)

    def setzen(self, zeilen: list[list[str]], bloecke: list[dict]) -> None:
        bar = self.verticalScrollBar()
        pos = bar.value()
        self.zeilen = list(zeilen)
        self.bloecke = bloecke
        self._zeichnen()
        bar.setValue(pos)

    def _block_fuer(self, nr: int) -> tuple[int, dict | None]:
        for i, b in enumerate(self.bloecke):
            start = int(b.get("start") or 0)
            letzte = start
            for z, _r in b.get("daten") or []:
                letzte = max(letzte, int(z))
            ende = max(letzte, start)
            if "marker" in b or b.get("marker_wort"):
                pass
            if start <= nr <= ende or (nr == start):
                if nr >= start:
                    nxt = None
                    if i + 1 < len(self.bloecke):
                        nxt = int(self.bloecke[i + 1].get("start") or 0) - 1
                    ober = nxt if nxt is not None else max(ende, start)
                    if start <= nr <= ober:
                        return i, b
        return -1, None

    def _grenzen(self) -> list[int]:
        """Erste Zeilennummer jedes Blocks nach dem ersten (Zieh-Punkte)."""
        return [int(b.get("start") or 0) for b in self.bloecke[1:] if b.get("start")]

    def _zeile_art(self, nr: int, row: list[str], bl: dict | None) -> tuple[bool, bool, bool]:
        """(ist_marker, ist_kopf, ist_satzart_daten). Enge Markerform, nicht #Kopf;Daten."""
        ist_marker = bool(
            bl
            and csv_bloecke.sieht_nach_marker_heuristik(row)
            or (
                bl
                and (bl.get("marker_wort") or bl.get("marker"))
                and nr == int(bl.get("start") or 0)
                and csv_bloecke.sieht_nach_marker_heuristik(row)
            )
        )
        ist_kopf = False
        if bl and not ist_marker:
            kopfz = [csv_bloecke.name_norm(x) for x in (bl.get("kopf") or [])]
            zellen = [csv_bloecke.name_norm(c) for c in row]
            if kopfz and zellen[: len(kopfz)] == kopfz[: len(zellen)]:
                ist_kopf = True
            elif csv_bloecke.ist_kopfzeile(row, set(kopfz) or ce.synonym_namen(), 2):
                ist_kopf = True
        ist_sa = False
        if not ist_marker and not ist_kopf:
            erste = next((str(c).strip() for c in row if str(c).strip()), "")
            if erste.startswith("#") and erste.upper() != "#LEER":
                ist_sa = True
        return ist_marker, ist_kopf, ist_sa

    def _farben_fuer(self, typ: str, wiederholend: bool, ist_marker: bool, ist_kopf: bool):
        pal = self._palette()
        if typ or wiederholend:
            hg, fg, rk = typ_farbe(typ, wiederholend, pal)
        else:
            kh, kf, kr = pal.get("kopfzeile") or pal["kopf"]
            hg, fg, rk = QColor(kh), QColor(kf), QColor(kr)
        if ist_marker:
            sh, sf, sr = pal.get("satzart") or pal["kopf"]
            hg, fg, rk = QColor(sh), QColor(sf), QColor(sr)
        elif ist_kopf:
            hg = QColor(hg).darker(108) if self._hell else QColor(hg).lighter(112)
        return hg, fg, rk

    def _zelle_faerben(self, i: int, typ: str, wiederholend: bool, ist_marker: bool, ist_kopf: bool, ist_sa: bool) -> None:
        hg, fg, rk = self._farben_fuer(typ, wiederholend, ist_marker, ist_kopf)
        pal = self._palette()
        n_c = self.columnCount()
        zeile_item = self.item(i, 0)
        if zeile_item is not None:
            zeile_item.setBackground(QBrush(rk if typ or wiederholend else hg))
            # Zeilennummer: kontrastreiche Schrift auf dem Randton
            zn_fg = QColor("#ffffff") if self._hell else QColor("#f7fafc")
            zeile_item.setForeground(QBrush(zn_fg if (typ or wiederholend) else fg))
        for j in range(1, n_c):
            it = self.item(i, j)
            if it is None:
                continue
            z_hg, z_fg = hg, fg
            if ist_sa and j == 1:
                sh, sf, _sr = pal.get("satzart") or pal["kopf"]
                z_hg, z_fg = QColor(sh), QColor(sf)
            it.setBackground(QBrush(z_hg))
            it.setForeground(QBrush(z_fg))
            if ist_marker or ist_kopf or (ist_sa and j == 1):
                fett = QFont(it.font())
                fett.setBold(True)
                it.setFont(fett)

    def _zeichnen(self) -> None:
        n_r = len(self.zeilen)
        n_c = max((len(r) for r in self.zeilen), default=0)
        self.clear()
        self.setRowCount(n_r)
        self.setColumnCount(n_c + 1)
        # Nur Spaltennummern: jeder Block hat eigene Kopfzeilen in den Daten.
        kopf = ["Zeile"] + [str(i) for i in range(1, n_c + 1)]
        self.setHorizontalHeaderLabels(kopf)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        fett = QFont()
        fett.setBold(True)
        for i, row in enumerate(self.zeilen):
            nr = i + 1
            _bi, bl = self._block_fuer(nr)
            typ = (bl or {}).get("typ") or ""
            wdh = bool((bl or {}).get("wiederholend"))
            ist_marker, ist_kopf, ist_sa = self._zeile_art(nr, row, bl)
            hg, fg, rk = self._farben_fuer(typ, wdh, ist_marker, ist_kopf)
            zeile_item = QTableWidgetItem(str(nr))
            zeile_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            zeile_item.setFlags(zeile_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if typ:
                zeile_item.setData(Qt.ItemDataRole.UserRole, typ)
            self.setItem(i, 0, zeile_item)
            for j in range(n_c):
                val = row[j] if j < len(row) else ""
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if ist_marker or ist_kopf:
                    it.setFont(fett)
                self.setItem(i, j + 1, it)
            self._zelle_faerben(i, typ, wdh, ist_marker, ist_kopf, ist_sa)
            self.setRowHeight(i, 26)
        self.setColumnWidth(0, 56)
        self.resizeColumnsToContents()
        for j in range(1, n_c + 1):
            self.setColumnWidth(j, max(self.columnWidth(j), 90))
        self._stil()
        self._zeilen_sichtbar_halten()

    def _zeilen_sichtbar_halten(self) -> None:
        """Minimale Höhe so, dass wenige Zeilen (z. B. die Summenzeile) nicht abgeschnitten werden."""
        kopf_h = self.horizontalHeader().height() or 28
        needed = kopf_h + sum(self.rowHeight(i) for i in range(self.rowCount())) + 6
        self.setMinimumHeight(max(220, min(needed, 420)))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def _umfaerben(self, vorschau_start: int | None = None) -> None:
        """Nur Farben aktualisieren, Tabelle nicht neu aufbauen (Ziehen)."""
        starts = [int(b.get("start") or 0) for b in self.bloecke]
        if vorschau_start and self._ziehen_ursprung:
            for i, s in enumerate(starts):
                if s == self._ziehen_ursprung:
                    starts[i] = vorschau_start
                    break
        for i, row in enumerate(self.zeilen):
            nr = i + 1
            typ, wdh, bl = "", False, None
            for j, start in enumerate(starts):
                ende = (starts[j + 1] - 1) if j + 1 < len(starts) else len(self.zeilen)
                if start <= nr <= ende:
                    bl = self.bloecke[j]
                    typ = bl.get("typ") or ""
                    wdh = bool(bl.get("wiederholend"))
                    break
            ist_marker, ist_kopf, ist_sa = self._zeile_art(nr, row, bl)
            self._zelle_faerben(i, typ, wdh, ist_marker, ist_kopf, ist_sa)

    def _sel(self) -> None:
        if self._ziehen_ursprung is not None:
            return
        rows = self.ausgewaehlte_nr()
        if rows:
            i, _b = self._block_fuer(rows[0])
            self.cursor_block.emit(i)

    def ausgewaehlte_nr(self) -> list[int]:
        return sorted({i.row() + 1 for i in self.selectedIndexes()})

    def aktueller_block_index(self) -> int:
        rows = self.ausgewaehlte_nr()
        if not rows:
            return 0 if self.bloecke else -1
        i, _ = self._block_fuer(rows[0])
        return i

    def zuweisen(self, typ: str, nrs: list[int] | None = None) -> None:
        nrs = nrs or self.ausgewaehlte_nr()
        if not nrs:
            return
        a, b = min(nrs), max(nrs)
        self._bereich_setzen(a, b, typ)
        self._zeichnen()
        self.block_gesetzt.emit()

    def neuer_block(self, typ: str | None = None, nrs: list[int] | None = None) -> None:
        nrs = nrs or self.ausgewaehlte_nr()
        if not nrs:
            # hinter dem letzten Block einen leeren Versuch vermeiden; eine Zeile nehmen, falls Datei da
            if self.zeilen and not self.bloecke:
                nrs = list(range(1, len(self.zeilen) + 1))
            else:
                return
        typ = typ or self._freier_name(_("Block"))
        self.zuweisen(typ, nrs)

    def entfernen(self, index: int | None = None) -> None:
        i = self.aktueller_block_index() if index is None else index
        if i < 0 or i >= len(self.bloecke):
            return
        del self.bloecke[i]
        self._zeichnen()
        self.block_gesetzt.emit()

    def umbenennen(self, name: str, index: int | None = None) -> None:
        i = self.aktueller_block_index() if index is None else index
        if i < 0 or i >= len(self.bloecke) or not (name or "").strip():
            return
        name = name.strip()
        self.bloecke[i]["name"] = name
        self.bloecke[i]["typ"] = name
        if not self.bloecke[i].get("id"):
            self.bloecke[i]["id"] = ce.block_id_von(self.bloecke[i], i)
        self._zeichnen()
        self.block_gesetzt.emit()

    def set_wiederholend(self, an: bool, index: int | None = None) -> None:
        i = self.aktueller_block_index() if index is None else index
        if i < 0 or i >= len(self.bloecke):
            return
        self.bloecke[i]["wiederholend"] = bool(an)
        self._zeichnen()
        self.block_gesetzt.emit()

    def _freier_name(self, basis: str) -> str:
        vergeben = {str(b.get("typ") or "") for b in self.bloecke} | {
            str(b.get("name") or "") for b in self.bloecke
        }
        if basis not in vergeben:
            return basis
        n = 2
        while f"{basis} {n}" in vergeben or f"{basis}_{n}" in vergeben:
            n += 1
        return f"{basis} {n}"

    def _bereich_setzen(self, a: int, b: int, typ: str) -> None:
        """Setzt Zeilen a–b inkl. als Block typ; bestehende Blöcke werden zerschnitten."""
        neu: list[dict] = []
        for bl in self.bloecke:
            start, ende = self._span(bl)
            if ende < a or start > b:
                neu.append(bl)
                continue
            if start < a:
                teil = dict(bl)
                teil["daten"] = [(z, r) for z, r in (bl.get("daten") or []) if z < a]
                if teil["daten"] or int(bl.get("start") or 0) < a:
                    neu.append(teil)
            if ende > b:
                teil = dict(bl)
                teil["start"] = b + 1
                teil["daten"] = [(z, r) for z, r in (bl.get("daten") or []) if z > b]
                neu.append(teil)
        kopf, daten, anfang, ohne = self._zeilen_als_block(a, b)
        block = {
            "typ": typ,
            "name": typ,
            "id": typ,
            "start": a,
            "kopf": kopf,
            "daten": daten,
            "anfang": anfang,
            "wiederholend": typ == "positionen",
            "ohne_anfang": ohne,
        }
        if anfang and anfang[0].get("art") == "marker":
            block["marker"] = anfang[0].get("wert")
            block["marker_wort"] = anfang[0].get("wert")
        neu.append(block)
        neu.sort(key=lambda x: int(x.get("start") or 0))
        gesehen: set[str] = set()
        for i, bl in enumerate(neu):
            bid = ce.block_id_von(bl, i)
            if bid in gesehen:
                bid = f"{bid}_{i + 1}"
            gesehen.add(bid)
            bl["id"] = bid
        self.bloecke[:] = neu

    def _span(self, bl: dict) -> tuple[int, int]:
        start = int(bl.get("start") or 0)
        ende = start
        for z, _r in bl.get("daten") or []:
            ende = max(ende, int(z))
        nxt = None
        idx = self.bloecke.index(bl) if bl in self.bloecke else -1
        if 0 <= idx + 1 < len(self.bloecke):
            nxt = int(self.bloecke[idx + 1].get("start") or 0) - 1
        if nxt is not None:
            ende = max(ende, min(ende if ende else nxt, nxt))
            ende = nxt if nxt >= start else ende
        return start, max(ende, start)

    def _zeilen_als_block(self, a: int, b: int) -> tuple[list, list, list, bool]:
        kopf: list[str] = []
        daten: list[tuple[int, list]] = []
        for nr in range(a, b + 1):
            if nr < 1 or nr > len(self.zeilen):
                continue
            row = self.zeilen[nr - 1]
            if csv_bloecke._leer_zeile(row):
                continue
            if csv_bloecke.sieht_nach_marker_heuristik(row):
                continue
            if not kopf and (
                csv_bloecke.ist_kopfzeile(row, ce.synonym_namen(), 2)
                or any(ce._norm(c) in ("satzart", "satztyp") for c in row)
            ):
                kopf = [c.strip() for c in row]
                continue
            daten.append((nr, row))
        anfang = ce.anfang_ableiten(self.zeilen, a, b, self.satzart_spalte)
        ohne = not bool(anfang)
        return kopf, daten, anfang, ohne

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(ev.position().toPoint())
            if idx.isValid():
                nr = idx.row() + 1
                if nr in self._grenzen():
                    self._ziehen_ursprung = nr
                    self._ziehen_vorschau = nr
                    self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
                    ev.accept()
                    return
                self._mark_start = nr
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._ziehen_ursprung is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self._auto_y = ev.position().y()
            if not self._auto_timer.isActive():
                self._auto_timer.start()
            self._grenze_vorschau(ev.position().toPoint())
            ev.accept()
            return
        idx = self.indexAt(ev.position().toPoint())
        if idx.isValid() and (idx.row() + 1) in self._grenzen():
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._auto_timer.stop()
        if self._ziehen_ursprung is not None:
            neu = self._ziehen_vorschau or self._ziehen_ursprung
            alt = self._ziehen_ursprung
            self._ziehen_ursprung = None
            self._ziehen_vorschau = None
            self.unsetCursor()
            if neu != alt:
                self._grenze_verschieben(alt, neu)
            ev.accept()
            super().mouseReleaseEvent(ev)
            return
        self._ziehen_ursprung = None
        self._ziehen_vorschau = None
        self._mark_start = None
        self.unsetCursor()
        super().mouseReleaseEvent(ev)

    def _auto_tick(self) -> None:
        if self._ziehen_ursprung is None:
            self._auto_timer.stop()
            return
        y = self._auto_y
        bar = self.verticalScrollBar()
        hoehe = self.viewport().height()
        if y < 28:
            bar.setValue(bar.value() - 16)
        elif y > hoehe - 28:
            bar.setValue(bar.value() + 16)

    def _grenze_vorschau(self, pos) -> None:
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        neu = idx.row() + 1
        if neu < 2 or neu == self._ziehen_vorschau:
            return
        # nicht vor den vorherigen Blockanfang
        alt = self._ziehen_ursprung or neu
        for i, bl in enumerate(self.bloecke):
            if int(bl.get("start") or 0) == alt and i > 0:
                if neu <= int(self.bloecke[i - 1].get("start") or 1):
                    return
                break
        self._ziehen_vorschau = neu
        self._umfaerben(neu)

    def _grenze_verschieben(self, alt: int, neu: int) -> None:
        for i, bl in enumerate(self.bloecke):
            if int(bl.get("start") or 0) == alt and i > 0:
                prev = self.bloecke[i - 1]
                if neu <= int(prev.get("start") or 1):
                    return
                bl["start"] = neu
                self._daten_neu_schneiden()
                self._zeichnen()
                self.block_gesetzt.emit()
                return

    def _daten_neu_schneiden(self) -> None:
        starts = [int(b.get("start") or 0) for b in self.bloecke]
        for i, bl in enumerate(self.bloecke):
            a = starts[i]
            b = (starts[i + 1] - 1) if i + 1 < len(starts) else len(self.zeilen)
            kopf, daten, anfang, ohne = self._zeilen_als_block(a, b)
            if not bl.get("anfang"):
                bl["anfang"] = anfang
                bl["ohne_anfang"] = ohne
            elif anfang:
                for r in anfang:
                    if not any(
                        x.get("art") == r.get("art") and x.get("wert") == r.get("wert")
                        for x in bl["anfang"]
                    ):
                        bl["anfang"].append(r)
            bl["kopf"] = kopf or bl.get("kopf") or []
            bl["daten"] = daten
            bl["start"] = a
            bl["ohne_anfang"] = not bool(bl.get("anfang"))


class Legende(QWidget):
    typ_gewählt = Signal(str)

    def __init__(self, parent=None, hell: bool = True):
        super().__init__(parent)
        self._hell = hell
        self._h = QHBoxLayout(self)
        self._h.setContentsMargins(0, 0, 0, 0)
        self._h.setSpacing(14)
        self._bauen()

    def set_hell(self, hell: bool) -> None:
        self._hell = bool(hell)
        self._bauen()

    def _bauen(self) -> None:
        while self._h.count():
            it = self._h.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        pal = thema.block_palette(self._hell)
        for typ, label in (
            ("kopf", _("Kopf / Kunde / Beleg")),
            ("positionen", _("Positionen (wiederholend)")),
            ("summen", _("Summen")),
        ):
            hg, _fg, rk = typ_farbe(typ, typ == "positionen", pal)
            box = QWidget()
            bh = QHBoxLayout(box)
            bh.setContentsMargins(0, 0, 0, 0)
            bh.setSpacing(6)
            bh.addWidget(_Farbkasten(hg, rk))
            bh.addWidget(QLabel(label))
            box.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            typ_s = typ
            box.mousePressEvent = lambda ev, t=typ_s: self.typ_gewählt.emit(t)  # type: ignore[method-assign]
            self._h.addWidget(box)
        for typ, label in (("satzart", _("Satzart-Wert in der Datenzeile")), ("kopfzeile", _("Kopfzeile"))):
            hg, _fg, rk = QColor(pal[typ][0]), QColor(pal[typ][1]), QColor(pal[typ][2])
            box = QWidget()
            bh = QHBoxLayout(box)
            bh.setContentsMargins(0, 0, 0, 0)
            bh.setSpacing(6)
            bh.addWidget(_Farbkasten(hg, rk))
            bh.addWidget(QLabel(label))
            self._h.addWidget(box)
        self._h.addStretch(1)


class BlockKarten(QWidget):
    """Reiter/Karten je Block: Name, Farbe, Kennzeichen wiederholend."""

    gewählt = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hell = True
        self._h = QHBoxLayout(self)
        self._h.setContentsMargins(0, 0, 0, 0)
        self._h.setSpacing(8)

    def set_hell(self, hell: bool) -> None:
        self._hell = bool(hell)

    def setzen(self, bloecke: list[dict], aktiv: int = -1) -> None:
        while self._h.count():
            it = self._h.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        pal = thema.block_palette(self._hell)
        bekannt = ("kopf", "kunde", "beleg", "positionen", "summen", "zahlung", "lieferung")
        for i, bl in enumerate(bloecke):
            typ = str(bl.get("typ") or "")
            name = str(bl.get("name") or typ or typ_name("kopf"))
            wdh = bool(bl.get("wiederholend"))
            hg, fg, rk = typ_farbe(typ or name, wdh, pal)
            lab = typ_name(typ) if typ in bekannt else name
            if wdh:
                lab = _("{n} (wiederholend)").format(n=lab)
            k = QPushButton(lab)
            k.setCheckable(True)
            k.setChecked(i == aktiv)
            k.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            k.setStyleSheet(
                f"QPushButton {{ background: {hg.name()}; color: {fg.name()}; "
                f"border: 2px solid {rk.name()}; border-radius: 8px; padding: 6px 12px; }}"
                f"QPushButton:checked {{ border-width: 3px; font-weight: bold; }}"
            )
            k.clicked.connect(lambda _an=False, idx=i: self.gewählt.emit(idx))
            self._h.addWidget(k)
        self._h.addStretch(1)


class AnfangsBox(QFrame):
    """Anfangsregeln des aktuellen Blocks, oder der rote Hinweis ohne Regel."""

    regel_gesetzt = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.block: dict | None = None
        self.satzart_spalte = None
        self._hell = True
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(16, 12, 16, 12)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._normal()

    def set_hell(self, hell: bool) -> None:
        self._hell = bool(hell)

    def _leeren(self) -> None:
        while self._v.count():
            it = self._v.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _normal(self) -> None:
        self._leeren()
        self.setMinimumHeight(0)
        hg, _fg, ln = ("#ffffff", "#1a202c", LINIE_HELL) if self._hell else ("#1a202c", "#e0e0e0", LINIE_DUNKEL)
        self.setStyleSheet(
            f"QFrame {{ background: {hg}; border: 1px solid {ln}; border-radius: 8px; }}"
        )
        typ = (self.block or {}).get("name") or (self.block or {}).get("typ") or ""
        titel = QLabel(_("Anfangsregel dieses Blocks ({t})").format(t=typ_name(typ)))
        f = QFont()
        f.setBold(True)
        titel.setFont(f)
        self._v.addWidget(titel)
        teile = []
        for r in (self.block or {}).get("anfang") or []:
            art = r.get("art")
            if art == "marker":
                teile.append(_("Marker: {m}").format(m=r.get("wert") or ""))
            elif art == "satzart":
                sp = self.satzart_spalte or _("Spalte 1")
                if not isinstance(sp, str):
                    sp = _("Spalte {n}").format(n=sp)
                else:
                    sp = _("Satzart-Spalte „{s}“").format(s=sp)
                teile.append(
                    _(
                        "{s}, Wert {w}. Die Zeile mit diesem Wert enthält zugleich Daten und wird mitgelesen."
                    ).format(s=sp, w=r.get("wert") or "")
                )
            elif art == "kopfzeile":
                kopf = (self.block or {}).get("kopf") or []
                kurz = ", ".join(kopf[:3]) + ("…" if len(kopf) > 3 else "")
                teile.append(_("Kopfzeile erkannt ({k})").format(k=kurz or _("ja")))
        if teile:
            self._v.addWidget(QLabel("     ·     ".join(teile)))
        else:
            self._v.addWidget(
                QLabel(_("Noch keine Anfangsregel. Zeilennummern werden nicht gespeichert."))
            )
        self._v.addWidget(
            QLabel(
                _(
                    "Die Zeilennummern werden nicht gespeichert. Ohne erkennbare Anfangsregel erscheint unten ein Hinweis."
                )
            )
        )
        # einfache Bearbeitung
        reihe = QHBoxLayout()
        self.f_marker = QLineEdit()
        self.f_marker.setPlaceholderText(_("Marker, z. B. #Kopf"))
        self.f_marker.setText(
            next(
                (str(r.get("wert") or "") for r in (self.block or {}).get("anfang") or [] if r.get("art") == "marker"),
                str((self.block or {}).get("marker") or ""),
            )
        )
        self.f_sa = QLineEdit()
        self.f_sa.setPlaceholderText(_("Satzart-Wert, z. B. #Kopf oder #Beleg"))
        self.f_sa.setText(
            next(
                (str(r.get("wert") or "") for r in (self.block or {}).get("anfang") or [] if r.get("art") == "satzart"),
                "",
            )
        )
        self.b_uebernehmen = QPushButton(_("Regel übernehmen"))
        self.b_uebernehmen.clicked.connect(self._uebernehmen)
        reihe.addWidget(QLabel(_("Marker")))
        reihe.addWidget(self.f_marker, 1)
        reihe.addWidget(QLabel(_("Satzart-Wert")))
        reihe.addWidget(self.f_sa, 1)
        reihe.addWidget(self.b_uebernehmen)
        self._v.addLayout(reihe)

    def _warnung(self) -> None:
        self._leeren()
        self.setMinimumHeight(220)
        wh, wt, _ln = warn_farben(self._hell)
        self.setStyleSheet(
            f"QFrame {{ background: {wh}; border: 1px solid {wt}; border-radius: 8px; }}"
        )
        bl = self.block or {}
        start = int(bl.get("start") or 1)
        ende = start
        for z, _r in bl.get("daten") or []:
            ende = max(ende, int(z))
        typ = typ_name(bl.get("typ") or "kopf")
        titel = QLabel(_("Block ohne erkennbaren Anfang"))
        f = QFont()
        f.setBold(True)
        f.setPointSize(13)
        titel.setFont(f)
        titel.setStyleSheet(f"color: {wt};")
        self._v.addWidget(titel)
        self._v.addWidget(
            QLabel(
                _(
                    "Die Zeilen {a}–{b} ({t}) wurden von dir markiert, aber Fakturafalter sieht keinen Marker, "
                    "keine Kopfzeile und keinen Satzart-Wert, den es schon kennt.\n"
                    "Keine Anfangsregel für Block „{n}“ ableitbar. Du kannst trotzdem weiter; "
                    "beim nächsten Einlesen wird dieser Block vielleicht nicht erkannt. "
                    "Eine Regel kannst du hier wählen:"
                ).format(a=start, b=ende, t=typ, n=typ)
            )
        )
        vorschlaege = self._vorschlaege()
        for text, cb in vorschlaege:
            b = QPushButton(text)
            b.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 8px 12px; "
                f"background: {'#ffffff' if self._hell else '#2d3748'}; "
                f"color: {'#1a202c' if self._hell else '#e0e0e0'}; "
                f"border: 1px solid {LINIE_HELL if self._hell else LINIE_DUNKEL}; border-radius: 4px; }}"
            )
            b.clicked.connect(cb)
            self._v.addWidget(b)

    def _vorschlaege(self) -> list:
        bl = self.block or {}
        typ = bl.get("typ") or "kopf"
        aus = []
        # Satzart aus erster Datenzeile
        sa = self.satzart_spalte
        row0 = (bl.get("daten") or [(0, [])])[0][1] if bl.get("daten") else []
        wert = ""
        if row0:
            if isinstance(sa, int) and 1 <= sa <= len(row0):
                wert = (row0[sa - 1] or "").strip()
            elif sa and not isinstance(sa, int):
                # erste Spalte als Fallback
                wert = (row0[0] or "").strip()
            else:
                wert = (row0[0] or "").strip()
        if wert:
            if isinstance(sa, int):
                sp_txt = _("Spalte {n}").format(n=sa)
            elif sa:
                sp_txt = f"„{sa}“"
            else:
                sp_txt = _("Spalte 1")
            aus.append(
                (
                    _("Satzart-Spalte {s}, Wert {w}  →  Typ {t}  (empfohlen)").format(
                        s=sp_txt, w=wert, t=typ_name(typ)
                    ),
                    lambda w=wert: self._setze_satzart(w),
                )
            )
        marker_bsp = {"kopf": "#Kopf", "positionen": "#Positionen", "summen": "#Summen"}.get(
            typ, "#Block"
        )
        aus.append(
            (
                _("Marker setzen, z. B. {m} (eigene Zeile vor dem Block)").format(m=marker_bsp),
                lambda m=marker_bsp: self._setze_marker(m),
            )
        )
        aus.append(
            (
                _("Kopfzeile in der Warenwirtschaft ergänzen und hier zuweisen"),
                self._setze_kopfzeile,
            )
        )
        return aus

    def _setze_satzart(self, wert: str) -> None:
        if not self.block:
            return
        self.block["anfang"] = [{"art": "satzart", "wert": wert}]
        self.block["ohne_anfang"] = False
        self.block["satzart"] = True
        self.block["satzart_wert"] = wert
        self.regel_gesetzt.emit()

    def _setze_marker(self, wert: str) -> None:
        if not self.block:
            return
        self.block["anfang"] = [{"art": "marker", "wert": wert}]
        self.block["marker"] = wert
        self.block["marker_wort"] = wert
        self.block["ohne_anfang"] = False
        self.regel_gesetzt.emit()

    def _setze_kopfzeile(self) -> None:
        if not self.block:
            return
        self.block["anfang"] = [{"art": "kopfzeile"}]
        self.block["ohne_anfang"] = False
        self.regel_gesetzt.emit()

    def _uebernehmen(self) -> None:
        if not self.block:
            return
        anfang = []
        m = self.f_marker.text().strip()
        if m:
            if csv_bloecke.name_norm(m) == csv_bloecke.name_norm("#LEER"):
                return
            anfang.append({"art": "marker", "wert": m})
            self.block["marker"] = m
        w = self.f_sa.text().strip()
        if w:
            anfang.append({"art": "satzart", "wert": w})
            self.block["satzart"] = True
            self.block["satzart_wert"] = w
        if (self.block.get("kopf") or []) and not any(r.get("art") == "kopfzeile" for r in anfang):
            # Kopfzeile bleibt zusätzliche Regel, wenn vorhanden
            if any(r.get("art") == "kopfzeile" for r in (self.block.get("anfang") or [])):
                anfang.append({"art": "kopfzeile"})
        self.block["anfang"] = anfang
        self.block["ohne_anfang"] = not bool(anfang)
        self.regel_gesetzt.emit()

    def zeigen(self, block: dict | None, satzart_spalte=None) -> None:
        self.block = block
        self.satzart_spalte = satzart_spalte
        if block is None:
            self._leeren()
            self._v.addWidget(QLabel(_("Keinen Block gewählt.")))
            return
        if not (block.get("anfang") or []) or block.get("ohne_anfang"):
            self._warnung()
        else:
            self._normal()


class SpaltenJeBlock(QWidget):
    """Schritt ‚Spalten je Block‘: Reiter, Klick auf Spalte, Beispielwert, Hinweis."""

    geaendert = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bloecke: list[dict] = []
        self.zeilen: list[list[str]] = []
        self.aktiv = 0
        self.spalte_i = 0  # 0-basiert in den Daten
        self.felder: dict[int, dict[int, str]] = {}  # block_i -> {col_i: feld}
        self._hell = True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.l_titel = QLabel(_("Spalten je Block zuordnen"))
        f = QFont()
        f.setBold(True)
        f.setPointSize(16)
        self.l_titel.setFont(f)
        v.addWidget(self.l_titel)
        self.l_sub = QLabel("")
        self.l_sub.setWordWrap(True)
        v.addWidget(self.l_sub)
        self.reit_zeile = QHBoxLayout()
        v.addLayout(self.reit_zeile)
        self.tabelle = QTableWidget()
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.cellClicked.connect(self._zelle)
        self.tabelle.setMinimumHeight(280)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tabelle, 3)
        unten = QHBoxLayout()
        self.box_spalte = QFrame()
        self.box_spalte.setFrameShape(QFrame.Shape.StyledPanel)
        sv = QVBoxLayout(self.box_spalte)
        self.l_spalte = QLabel(_("Spalte"))
        ff = QFont()
        ff.setBold(True)
        self.l_spalte.setFont(ff)
        self.l_beispiel = QLabel("")
        self.l_beispiel.setVisible(False)
        self.b_feld = FeldSuche()
        self.b_feld.geaendert.connect(self._feld_geaendert)
        self.l_andere = QLabel("")
        self.l_andere.setWordWrap(True)
        sv.addWidget(self.l_spalte)
        sv.addWidget(self.b_feld, 1)
        sv.addWidget(self.l_andere)
        self.box_hinweis = QFrame()
        self.box_hinweis.setFrameShape(QFrame.Shape.StyledPanel)
        hv = QVBoxLayout(self.box_hinweis)
        self.l_hinweis_titel = QLabel(_("Hinweis"))
        self.l_hinweis_titel.setFont(ff)
        self.l_hinweis_titel.setStyleSheet(f"color: {HINWEIS_RD};")
        self.l_hinweis = QLabel("")
        self.l_hinweis.setWordWrap(True)
        hv.addWidget(self.l_hinweis_titel)
        hv.addWidget(self.l_hinweis)
        hv.addStretch(1)
        self.box_pflicht = QFrame()
        self.box_pflicht.setFrameShape(QFrame.Shape.StyledPanel)
        pv = QVBoxLayout(self.box_pflicht)
        self.l_pflicht_titel = QLabel(_("Pflichtangaben der Rechnung"))
        self.l_pflicht_titel.setFont(ff)
        self.l_pflicht = QLabel("")
        self.l_pflicht.setWordWrap(True)
        self.l_pflicht_status = QLabel("")
        self.l_pflicht_status.setWordWrap(True)
        pv.addWidget(self.l_pflicht_titel)
        pv.addWidget(self.l_pflicht)
        pv.addWidget(self.l_pflicht_status)
        pv.addStretch(1)
        unten.addWidget(self.box_spalte, 2)
        unten.addWidget(self.box_pflicht, 3)
        unten.addWidget(self.box_hinweis, 2)
        v.addLayout(unten)

    def set_hell(self, hell: bool) -> None:
        self._hell = bool(hell)
        self._tabelle_stil()
        if getattr(self, "l_hinweis", None) is not None:
            self._hinweis_text()

    def _tabelle_stil(self) -> None:
        if self._hell:
            self.tabelle.setStyleSheet(
                "QTableWidget { background: #ffffff; color: #1a202c; gridline-color: #d0d5dd; }"
                "QHeaderView::section { background: #edf2f7; color: #1a202c; padding: 4px; "
                "border: 1px solid #d0d5dd; }"
                "QTableCornerButton::section { background: #edf2f7; border: 1px solid #d0d5dd; }"
            )
        else:
            self.tabelle.setStyleSheet(
                "QTableWidget { background: #1a202c; color: #e2e8f0; gridline-color: #4a5568; }"
                "QHeaderView::section { background: #2d3748; color: #e2e8f0; padding: 4px; "
                "border: 1px solid #4a5568; }"
                "QTableCornerButton::section { background: #2d3748; border: 1px solid #4a5568; }"
            )

    def setzen(self, zeilen: list[list[str]], bloecke: list[dict], felder=None) -> None:
        self.zeilen = zeilen
        self.bloecke = bloecke
        if felder is not None:
            self.felder = felder
        if self.aktiv >= len(bloecke):
            self.aktiv = 0
        self._reiter()
        self._tabelle()
        self._karten()
        self._pflicht_aktualisieren()

    def _reiter(self) -> None:
        while self.reit_zeile.count():
            it = self.reit_zeile.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for i, b in enumerate(self.bloecke):
            typ = b.get("typ") or "kopf"
            name = b.get("name") or typ_name(typ)
            wdh = bool(b.get("wiederholend"))
            hg, fg, rk = typ_farbe(typ, wdh, thema.block_palette(self._hell))
            lab = typ_name(typ) if typ in (
                "kopf", "kunde", "beleg", "positionen", "summen", "zahlung", "lieferung"
            ) else name
            if wdh:
                lab = _("{n} (wiederholend)").format(n=lab)
            btn = QPushButton(lab)
            btn.setCheckable(True)
            btn.setChecked(i == self.aktiv)
            if i == self.aktiv:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {hg.name()}; color: {fg.name()}; "
                    f"border: 2px solid {rk.name()}; border-radius: 6px; padding: 6px 16px; font-weight: bold; }}"
                )
            else:
                rand = LINIE_HELL if self._hell else LINIE_DUNKEL
                hg0 = "#ffffff" if self._hell else "#2d3748"
                fg0 = "#1a202c" if self._hell else "#e0e0e0"
                btn.setStyleSheet(
                    f"QPushButton {{ background: {hg0}; color: {fg0}; border: 1px solid {rand}; "
                    "border-radius: 6px; padding: 6px 16px; }"
                )
            btn.clicked.connect(lambda _=False, j=i: self._aktiv(j))
            self.reit_zeile.addWidget(btn)
        self.reit_zeile.addStretch(1)

    def _aktiv(self, i: int) -> None:
        self.aktiv = i
        self.spalte_i = 0
        self._reiter()
        self._tabelle()
        self._karten()
        self._pflicht_aktualisieren()

    def _span(self, bl: dict) -> tuple[int, int]:
        start = int(bl.get("start") or 1)
        ende = start
        for z, _r in bl.get("daten") or []:
            ende = max(ende, int(z))
        i = self.bloecke.index(bl) if bl in self.bloecke else -1
        if 0 <= i + 1 < len(self.bloecke):
            ende = max(ende, int(self.bloecke[i + 1].get("start") or ende) - 1)
        # Kopfzeile oder Marker unmittelbar vor dem Start gehört zum Block
        unter = 1
        if i > 0:
            vor = self.bloecke[i - 1]
            unter = int(vor.get("start") or 1)
            for z, _r in vor.get("daten") or []:
                unter = max(unter, int(z) + 1)
        kopf = [csv_bloecke.name_norm(x) for x in (bl.get("kopf") or [])]
        while start > unter:
            row = self.zeilen[start - 2]
            if csv_bloecke.sieht_nach_marker_heuristik(row):
                start -= 1
                continue
            zellen = [csv_bloecke.name_norm(c) for c in row]
            if kopf and zellen[: len(kopf)] == kopf[: len(zellen)]:
                start -= 1
                continue
            break
        return start, max(ende, start)

    def _tabelle(self) -> None:
        t = self.tabelle
        if not self.bloecke:
            t.setRowCount(0)
            return
        bl = self.bloecke[self.aktiv]
        typ = bl.get("typ") or ""
        hg, fg, rk = typ_farbe(typ, bool(bl.get("wiederholend")), thema.block_palette(self._hell))
        start, ende = self._span(bl)
        kopf = list(bl.get("kopf") or [])
        n_c = max((len(r) for r in self.zeilen), default=0)
        if kopf and len(kopf) > n_c:
            n_c = len(kopf)
        t.clear()
        t.setColumnCount(n_c + 1)
        labels = ["Zeile"] + [
            f"{i + 1} {kopf[i]}" if i < len(kopf) and kopf[i] else str(i + 1) for i in range(n_c)
        ]
        t.setHorizontalHeaderLabels(labels)
        rows = [i for i in range(start, ende + 1) if 1 <= i <= len(self.zeilen)]
        t.setRowCount(len(rows))
        fett = QFont()
        fett.setBold(True)
        for ri, nr in enumerate(rows):
            row = self.zeilen[nr - 1]
            ze = QTableWidgetItem(str(nr))
            ze.setBackground(QBrush(rk))
            ze.setForeground(QBrush(QColor("#ffffff") if self._hell else QColor("#f7fafc")))
            ze.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(ri, 0, ze)
            ist_marker = csv_bloecke.sieht_nach_marker_heuristik(row)
            ist_kopf = kopf and [csv_bloecke.name_norm(c) for c in row[: len(kopf)]] == [
                csv_bloecke.name_norm(x) for x in kopf
            ]
            for j in range(n_c):
                val = row[j] if j < len(row) else ""
                it = QTableWidgetItem(val)
                if j == self.spalte_i:
                    it.setBackground(QBrush(QColor(hg).lighter(130) if self._hell else QColor(hg).lighter(140)))
                    it.setFont(fett)
                elif ist_marker:
                    pal = thema.block_palette(self._hell)
                    sh, sf, _sr = pal.get("satzart") or pal["kopf"]
                    it.setBackground(QBrush(QColor(sh)))
                    it.setForeground(QBrush(QColor(sf)))
                    it.setFont(fett)
                else:
                    it.setBackground(QBrush(hg))
                    if ist_kopf:
                        it.setFont(fett)
                if not ist_marker:
                    it.setForeground(QBrush(fg))
                t.setItem(ri, j + 1, it)
            t.setRowHeight(ri, 26)
        t.setColumnWidth(0, 56)
        t.resizeColumnsToContents()
        hdr = t.horizontalHeader()
        letzte = t.columnCount() - 1
        for i in range(t.columnCount()):
            hdr.setSectionResizeMode(
                i,
                QHeaderView.ResizeMode.Stretch
                if i == letzte
                else QHeaderView.ResizeMode.Interactive,
            )
        hdr.setStretchLastSection(True)
        self._tabelle_stil()
        typn = typ_name(typ)
        zusatz = _(" (wiederholend)") if bl.get("wiederholend") else ""
        self.l_sub.setText(
            _(
                "Aktiver Block: {t}. Klick auf eine Spalte – dieselbe Position darf in einem anderen Block ein anderes Feld sein."
            ).format(t=typn + zusatz)
        )

    def _zelle(self, row: int, col: int) -> None:
        if col <= 0:
            return
        self.spalte_i = col - 1
        self._tabelle()
        self._karten()

    def _fuelle_combo(self) -> None:
        bl = self.bloecke[self.aktiv] if self.bloecke else {}
        self.b_feld.set_wiederholend(bool(bl.get("wiederholend")))
        schon = (self.felder.get(self.aktiv) or {}).get(self.spalte_i, "")
        self.b_feld.set_feld(schon or "")
        self.b_feld.set_beispiel(self._beispiel())

    def _feld_geaendert(self) -> None:
        if not self.bloecke:
            return
        self.felder.setdefault(self.aktiv, {})
        feld = self.b_feld.feld() if hasattr(self.b_feld, "feld") else (self.b_feld.currentData() or "")
        if feld:
            self.felder[self.aktiv][self.spalte_i] = feld
        else:
            self.felder[self.aktiv].pop(self.spalte_i, None)
        self.geaendert.emit()
        self._karten()
        self._pflicht_aktualisieren()

    def _beispiel(self) -> str:
        if not self.bloecke:
            return ""
        bl = self.bloecke[self.aktiv]
        for _z, row in bl.get("daten") or []:
            if self.spalte_i < len(row) and (row[self.spalte_i] or "").strip():
                return (row[self.spalte_i] or "").strip()
        return ""

    def _karten(self) -> None:
        self._fuelle_combo()
        nr = self.spalte_i + 1
        kopf = (self.bloecke[self.aktiv].get("kopf") if self.bloecke else []) or []
        name = kopf[self.spalte_i] if self.spalte_i < len(kopf) and kopf[self.spalte_i] else ""
        if name:
            self.l_spalte.setText(_("Spalte {n} in diesem Block").format(n=f"{nr} ({name})" if False else nr))
            self.l_spalte.setText(_("Spalte {n} in diesem Block").format(n=nr))
        else:
            self.l_spalte.setText(_("Spalte {n} in diesem Block").format(n=nr))
        bsp = self._beispiel()
        self.l_beispiel.setText(_("Erster Beispielwert: {w}").format(w=bsp) if bsp else _("Kein Beispielwert in den Datenzeilen."))
        # anderer Block, dieselbe Position
        andere = []
        for i, bl in enumerate(self.bloecke):
            if i == self.aktiv:
                continue
            f = (self.felder.get(i) or {}).get(self.spalte_i)
            if not f:
                continue
            anz = ce.FELD[f][1] if f in ce.FELD else f
            kn = (bl.get("kopf") or [])
            nm = kn[self.spalte_i] if self.spalte_i < len(kn) and kn[self.spalte_i] else ""
            andere.append((bl.get("typ") or "", anz, nm, f))
        if andere:
            typ_a, anz, nm, f = andere[0]
            if nm:
                self.l_andere.setText(
                    _("{im} ist Spalte {n} „{nm}“ ({anz}). Das ist zulässig.").format(
                        im=im_block(typ_a), n=nr, nm=nm, anz=anz
                    )
                )
            else:
                self.l_andere.setText(
                    _("{im} ist Spalte {n} als „{anz}“ belegt. Das ist zulässig.").format(
                        im=im_block(typ_a), n=nr, anz=anz
                    )
                )
        else:
            self.l_andere.setText("")
        self._hinweis_text()

    def _hinweis_text(self) -> None:
        # Kopffeld in mehreren Blöcken
        in_bloecken: dict[str, list[str]] = {}
        for i, bl in enumerate(self.bloecke):
            typ = typ_name(bl.get("typ") or "")
            for _col, f in (self.felder.get(i) or {}).items():
                if f in ce.FELD and ce.FELD[f][2] == "kopf":
                    in_bloecken.setdefault(f, []).append(typ)
        mehr = {f: typen for f, typen in in_bloecken.items() if len(set(typen)) > 1 or len(typen) > 1}
        teile = []
        if mehr:
            f, typen = next(iter(mehr.items()))
            anz = ce.FELD[f][1]
            # unique typ names
            ts = []
            for t in typen:
                if t not in ts:
                    ts.append(t)
            if len(ts) >= 2:
                teile.append(
                    _(
                        "„{f}“ steckt in {a} und {b}. Fakturafalter vergleicht die Werte. "
                        "Weichen sie ab, geht die Rechnung nach „Zu prüfen“."
                    ).format(f=anz, a=ts[0], b=ts[1])
                )
            else:
                teile.append(
                    _(
                        "Hinweis: Kopffeld in mehreren Blöcken wird verglichen, Abweichung → Zu prüfen ({t})."
                    ).format(t=anz)
                )
        teile.append(
            _(
                "Absender, Währung und übrige Angaben prüft die Probe. "
                "Die Pflichtangaben dieser Seite stehen rechts."
            )
        )
        self.l_hinweis.setText("\n\n".join(teile))
        if self._hell:
            hh, hf, hl = thema.hinweis_farben(True)
            sh, sl = "#ffffff", LINIE_HELL
            ph, pl = "#f7fafc", LINIE_HELL
        else:
            hh, hf, hl = thema.hinweis_farben(False)
            sh, sl = "#1a202c", LINIE_DUNKEL
            ph, pl = "#1a202c", LINIE_DUNKEL
        self.box_hinweis.setStyleSheet(
            f"QFrame {{ background: {hh}; border: 1px solid {hl}; border-radius: 8px; }}"
            f"QLabel {{ color: {hf}; }}"
        )
        if getattr(self, "l_hinweis_titel", None) is not None:
            self.l_hinweis_titel.setStyleSheet(f"color: {hl};")
        self.l_hinweis.setStyleSheet(f"color: {hf};")
        self.box_spalte.setStyleSheet(
            f"QFrame {{ background: {sh}; border: 1px solid {sl}; border-radius: 8px; }}"
        )
        self.box_pflicht.setStyleSheet(
            f"QFrame {{ background: {ph}; border: 1px solid {pl}; border-radius: 8px; }}"
        )

    def zuordnung_je(self) -> dict[str, dict[str, str]]:
        """id (und typ als Fallback) → {feld: spaltenname} plus feld_pos am Block."""
        aus: dict[str, dict[str, str]] = {}
        for i, bl in enumerate(self.bloecke):
            bid = ce.block_id_von(bl, i)
            typ = str(bl.get("typ") or f"block{i}")
            kopf = list(bl.get("kopf") or [])
            pos: dict[str, int] = {}
            zu: dict[str, str] = {}
            for col, f in (self.felder.get(i) or {}).items():
                name = kopf[col] if col < len(kopf) and kopf[col] else f"Spalte{col + 1}"
                zu[f] = name
                pos[f] = col + 1
            aus[bid] = zu
            if typ not in aus:
                aus[typ] = zu
            aus[str(i)] = zu
            bl["feld_pos"] = pos
            bl["id"] = bid
        return aus

    def zuordnung_flach(self) -> dict[str, str]:
        """Alle Blockzuordnungen in einer Map für fehlende_pflicht."""
        aus: dict[str, str] = {}
        for _k, zu in self.zuordnung_je().items():
            for f, s in (zu or {}).items():
                if s and f not in aus:
                    aus[f] = s
        return aus

    def _pflicht_aktualisieren(self) -> None:
        zu = self.zuordnung_flach()
        wo: dict[str, str] = {}
        for i, bl in enumerate(self.bloecke):
            name = typ_name(str(bl.get("name") or bl.get("typ") or ""))
            kopf = list(bl.get("kopf") or [])
            for col, f in (self.felder.get(i) or {}).items():
                sp = kopf[col] if col < len(kopf) and kopf[col] else _("Spalte {n}").format(n=col + 1)
                wo[f] = _("Block {b}, Spalte {n} {s}").format(b=name, n=col + 1, s=sp)
        sicht = [
            ("BT-153", _("Bezeichnung der Position")),
            ("BT-129", _("Menge")),
            ("BT-146", _("Einzelpreis (netto)")),
            ("steuer", _("Steuersatz oder Steuerschlüssel")),
            ("BT-1", _("Rechnungsnummer")),
            ("BT-2", _("Rechnungsdatum")),
            ("BT-44", _("Kundenname")),
        ]
        zeilen = []
        for f, lab in sicht:
            if zu.get(f):
                zeilen.append("✓  " + lab + " – " + wo.get(f, zu[f]))
            else:
                zeilen.append("○  " + lab + " – " + _("fehlt noch"))
        self.l_pflicht.setText("\n".join(zeilen))
        fehlt = ce.fehlende_pflicht(zu)
        if fehlt:
            self.l_pflicht_status.setText(
                _("Noch nicht zugeordnet: {l}.").format(l=", ".join(_(x) for x in fehlt))
            )
        else:
            self.l_pflicht_status.setText(_("Alle Pflichtangaben der Rechnung sind zugeordnet."))
