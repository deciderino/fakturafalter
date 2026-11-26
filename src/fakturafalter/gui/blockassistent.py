# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Farbige Block-Tabelle und Spalten-je-Block im CSV-Assistenten (ab 0.9.10)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import csv_bloecke
from .. import csv_einrichtung as ce
from .texte import _

# Farben analog zur Attrappe (und zur PDF-Blockkennzeichnung)
FARBEN = {
    "kopf": ("#d6e8fb", "#2b6cb0"),
    "positionen": ("#d8f3e0", "#2f855a"),
    "summen": ("#fde8cf", "#c05621"),
    "zahlung": ("#e9d8fd", "#6b46c1"),
    "lieferung": ("#feebc8", "#c05621"),
}
MARKER_RK = "#4a5568"
KOPFZEILE_HG = "#edf2f7"
KOPFZEILE_RK = "#718096"
HINWEIS_RD = "#c05621"
WARN_HG = "#fff5f5"
WARN_T = "#c53030"
LINIE = "#d0d5dd"

TYPEN = ("kopf", "positionen", "summen", "zahlung", "lieferung")


def typ_name(typ: str) -> str:
    return {
        "kopf": _("Kopf"),
        "positionen": _("Positionen"),
        "summen": _("Summen"),
        "zahlung": _("Zahlung"),
        "lieferung": _("Lieferung"),
    }.get(typ, typ or _("Block"))


def im_block(typ: str) -> str:
    return {
        "kopf": _("Im Kopf"),
        "positionen": _("In den Positionen"),
        "summen": _("In den Summen"),
        "zahlung": _("In der Zahlung"),
        "lieferung": _("In der Lieferung"),
    }.get(typ, _("Im Block „{t}“").format(t=typ_name(typ)))


def typ_farbe(typ: str) -> tuple[QColor, QColor]:
    hg, rk = FARBEN.get(typ or "kopf", ("#edf2f7", "#718096"))
    return QColor(hg), QColor(rk)


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
        self._ziehen: tuple[int, int] | None = None  # (block_i, start_grenzen_nr)
        self._mark_start: int | None = None
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setShowGrid(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(160)
        self.itemSelectionChanged.connect(self._sel)
        self.setMouseTracking(True)

    def setzen(self, zeilen: list[list[str]], bloecke: list[dict]) -> None:
        self.zeilen = list(zeilen)
        self.bloecke = bloecke
        self._zeichnen()

    def _block_fuer(self, nr: int) -> tuple[int, dict | None]:
        for i, b in enumerate(self.bloecke):
            start = int(b.get("start") or 0)
            letzte = start
            for z, _r in b.get("daten") or []:
                letzte = max(letzte, int(z))
            # Kopfzeile steht oft in start, Daten danach
            ende = max(letzte, start)
            # Markerzeile ist start, Kopf kann start+1 sein
            if "marker" in b or b.get("marker_wort"):
                pass
            if start <= nr <= ende or (nr == start):
                # also include header row at start even without daten
                if nr >= start:
                    # end: next block start - 1 or ende
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

    def _zeichnen(self) -> None:
        n_r = len(self.zeilen)
        n_c = max((len(r) for r in self.zeilen), default=0)
        self.clear()
        self.setRowCount(n_r)
        self.setColumnCount(n_c + 1)
        kopf = ["Zeile"] + [str(i) for i in range(1, n_c + 1)]
        # Namen aus erstem erkennbaren Kopf
        for b in self.bloecke:
            if b.get("kopf"):
                for i, name in enumerate(b["kopf"]):
                    if name and i + 1 < len(kopf):
                        kopf[i + 1] = f"{i + 1} {name}"
                break
        self.setHorizontalHeaderLabels(kopf)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        fett = QFont()
        fett.setBold(True)
        for i, row in enumerate(self.zeilen):
            nr = i + 1
            bi, bl = self._block_fuer(nr)
            typ = (bl or {}).get("typ") or ""
            hg, rk = typ_farbe(typ) if bl else (QColor("#ffffff"), QColor(LINIE))
            ist_marker = bool(
                bl
                and csv_bloecke.sieht_nach_marker_heuristik(row)
                or (
                    bl
                    and (bl.get("marker_wort") or bl.get("marker"))
                    and nr == int(bl.get("start") or 0)
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
            if ist_marker:
                hg = QColor(rk).lighter(170)
            elif ist_kopf:
                # etwas kräftiger, fett
                hg = QColor(hg).darker(102)
            zeile_item = QTableWidgetItem(str(nr))
            zeile_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            zeile_item.setBackground(QBrush(rk if typ else QColor(KOPFZEILE_HG)))
            zeile_item.setForeground(QBrush(QColor("#ffffff") if typ else QColor("#1a202c")))
            zeile_item.setFlags(zeile_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if typ:
                zeile_item.setData(Qt.ItemDataRole.UserRole, typ)
            self.setItem(i, 0, zeile_item)
            for j in range(n_c):
                val = row[j] if j < len(row) else ""
                it = QTableWidgetItem(val)
                it.setBackground(QBrush(hg))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if ist_marker or ist_kopf:
                    it.setFont(fett)
                self.setItem(i, j + 1, it)
            self.setRowHeight(i, 26)
        self.setColumnWidth(0, 56)
        self.resizeColumnsToContents()
        for j in range(1, n_c + 1):
            self.setColumnWidth(j, max(self.columnWidth(j), 90))

    def _sel(self) -> None:
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
        # entferne überlappende Teile aus bestehenden Blöcken, füge neuen Block ein
        self._bereich_setzen(a, b, typ)
        self._zeichnen()
        self.block_gesetzt.emit()

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
        # genau ein wiederholender
        if typ == "positionen":
            for bl in neu:
                if bl is not block:
                    bl["wiederholend"] = False
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
        anfang: list[dict] = []
        ohne = True
        for nr in range(a, b + 1):
            if nr < 1 or nr > len(self.zeilen):
                continue
            row = self.zeilen[nr - 1]
            if csv_bloecke._leer_zeile(row):
                continue
            if csv_bloecke.sieht_nach_marker_heuristik(row):
                wort = next((str(c).strip() for c in row if str(c).strip()), "")
                anfang.append({"art": "marker", "wert": wort})
                ohne = False
                continue
            if not kopf and (
                csv_bloecke.ist_kopfzeile(row, ce.synonym_namen(), 2)
                or any(ce._norm(c) in ("satzart", "satztyp") for c in row)
            ):
                kopf = [c.strip() for c in row]
                if not any(r.get("art") == "kopfzeile" for r in anfang):
                    anfang.append({"art": "kopfzeile"})
                ohne = False
                continue
            daten.append((nr, row))
        return kopf, daten, anfang, ohne and not anfang

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(ev.position().toPoint())
            if idx.isValid():
                nr = idx.row() + 1
                # Grenze ziehen, wenn die Zeile der Anfang eines Blocks (nicht des ersten) ist
                if nr in self._grenzen():
                    self._ziehen = (nr, ev.position().y())
                    self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
                    ev.accept()
                    return
                self._mark_start = nr
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._ziehen is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            idx = self.indexAt(ev.position().toPoint())
            if idx.isValid():
                neu = idx.row() + 1
                alt = self._ziehen[0]
                if neu != alt and neu >= 2:
                    self._grenze_verschieben(alt, neu)
                    self._ziehen = (neu, ev.position().y())
            ev.accept()
            return
        idx = self.indexAt(ev.position().toPoint())
        if idx.isValid() and (idx.row() + 1) in self._grenzen():
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._ziehen = None
        self._mark_start = None
        self.unsetCursor()
        super().mouseReleaseEvent(ev)

    def _grenze_verschieben(self, alt: int, neu: int) -> None:
        # Finde den Block, der bei alt beginnt, und den vorherigen; passe start/daten an
        for i, bl in enumerate(self.bloecke):
            if int(bl.get("start") or 0) == alt and i > 0:
                prev = self.bloecke[i - 1]
                if neu <= int(prev.get("start") or 1):
                    return
                bl["start"] = neu
                # daten neu verteilen anhand der Rohzeilen
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
            elif anfang and not any(r.get("art") == a.get("art") for a in anfang for r in bl["anfang"]):
                # ergänze erkannte Regeln, überschreibe gesetzte nicht
                for r in anfang:
                    if not any(x.get("art") == r.get("art") and x.get("wert") == r.get("wert") for x in bl["anfang"]):
                        bl["anfang"].append(r)
            bl["kopf"] = kopf or bl.get("kopf") or []
            bl["daten"] = daten
            bl["start"] = a
            bl["ohne_anfang"] = not bool(bl.get("anfang"))


class Legende(QWidget):
    typ_gewählt = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)
        for typ, label in (
            ("kopf", _("Kopf")),
            ("positionen", _("Positionen (wiederholend)")),
            ("summen", _("Summen")),
        ):
            hg, rk = typ_farbe(typ)
            box = QWidget()
            bh = QHBoxLayout(box)
            bh.setContentsMargins(0, 0, 0, 0)
            bh.setSpacing(6)
            bh.addWidget(_Farbkasten(hg, rk))
            lab = QLabel(label)
            bh.addWidget(lab)
            box.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            typ_s = typ
            box.mousePressEvent = lambda ev, t=typ_s: self.typ_gewählt.emit(t)  # type: ignore[method-assign]
            h.addWidget(box)
        # Marker / Kopfzeile nur Legende
        for label, hg, rk in (
            (_("Markerzeile"), QColor(QColor(MARKER_RK).lighter(180)), QColor(MARKER_RK)),
            (_("Kopfzeile"), QColor(KOPFZEILE_HG), QColor(KOPFZEILE_RK)),
        ):
            box = QWidget()
            bh = QHBoxLayout(box)
            bh.setContentsMargins(0, 0, 0, 0)
            bh.setSpacing(6)
            bh.addWidget(_Farbkasten(hg, rk))
            bh.addWidget(QLabel(label))
            h.addWidget(box)
        h.addStretch(1)


class AnfangsBox(QFrame):
    """Anfangsregeln des aktuellen Blocks, oder der rote Hinweis ohne Regel."""

    regel_gesetzt = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.block: dict | None = None
        self.satzart_spalte = None
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(16, 12, 16, 12)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._normal()

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
        self.setStyleSheet(
            f"QFrame {{ background: #ffffff; border: 1px solid {LINIE}; border-radius: 8px; }}"
        )
        typ = (self.block or {}).get("typ") or ""
        titel = QLabel(_("Anfangsregeln dieses Blocks ({t})").format(t=typ_name(typ)))
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
                teile.append(_("{s}, Wert {w}").format(s=sp, w=r.get("wert") or ""))
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
        self.f_sa.setPlaceholderText(_("Satzart-Wert, z. B. K oder P"))
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
        self.setStyleSheet(
            f"QFrame {{ background: {WARN_HG}; border: 1px solid {WARN_T}; border-radius: 8px; }}"
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
        titel.setStyleSheet(f"color: {WARN_T};")
        self._v.addWidget(titel)
        self._v.addWidget(
            QLabel(
                _(
                    "Die Zeilen {a}–{b} ({t}) wurden von dir markiert, aber Fakturafalter sieht keinen Marker, "
                    "keine Kopfzeile und keinen Satzart-Wert, den es schon kennt.\n"
                    "Bitte eine Anfangsregel wählen, sonst geht dieser Block beim nächsten Einlesen verloren "
                    "(Zeilennummern werden nicht gespeichert):"
                ).format(a=start, b=ende, t=typ)
            )
        )
        vorschlaege = self._vorschlaege()
        for text, cb in vorschlaege:
            b = QPushButton(text)
            b.setStyleSheet(
                "QPushButton { text-align: left; padding: 8px 12px; background: #ffffff; "
                f"border: 1px solid {LINIE}; border-radius: 4px; }}"
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
        v.addWidget(self.tabelle, 1)
        unten = QHBoxLayout()
        self.box_spalte = QFrame()
        self.box_spalte.setFrameShape(QFrame.Shape.StyledPanel)
        sv = QVBoxLayout(self.box_spalte)
        self.l_spalte = QLabel(_("Spalte"))
        ff = QFont()
        ff.setBold(True)
        self.l_spalte.setFont(ff)
        self.l_beispiel = QLabel("")
        self.b_feld = QComboBox()
        self.b_feld.setMinimumHeight(40)
        self.b_feld.currentIndexChanged.connect(self._feld_geaendert)
        self.l_andere = QLabel("")
        self.l_andere.setWordWrap(True)
        sv.addWidget(self.l_spalte)
        sv.addWidget(self.l_beispiel)
        sv.addWidget(self.b_feld)
        sv.addWidget(self.l_andere)
        sv.addStretch(1)
        self.box_hinweis = QFrame()
        self.box_hinweis.setFrameShape(QFrame.Shape.StyledPanel)
        hv = QVBoxLayout(self.box_hinweis)
        ht = QLabel(_("Hinweis"))
        ht.setFont(ff)
        ht.setStyleSheet(f"color: {HINWEIS_RD};")
        self.l_hinweis = QLabel("")
        self.l_hinweis.setWordWrap(True)
        hv.addWidget(ht)
        hv.addWidget(self.l_hinweis)
        hv.addStretch(1)
        unten.addWidget(self.box_spalte, 3)
        unten.addWidget(self.box_hinweis, 2)
        v.addLayout(unten)

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

    def _reiter(self) -> None:
        while self.reit_zeile.count():
            it = self.reit_zeile.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for i, b in enumerate(self.bloecke):
            typ = b.get("typ") or "kopf"
            hg, rk = typ_farbe(typ)
            btn = QPushButton(typ_name(typ))
            btn.setCheckable(True)
            btn.setChecked(i == self.aktiv)
            if i == self.aktiv:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {hg.name()}; color: {rk.name()}; "
                    f"border: 2px solid {rk.name()}; border-radius: 6px; padding: 6px 16px; font-weight: bold; }}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #ffffff; border: 1px solid #d0d5dd; "
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
        hg, rk = typ_farbe(typ)
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
            ze.setForeground(QBrush(QColor("#ffffff")))
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
                    it.setBackground(QBrush(QColor(rk).lighter(150)))
                    it.setFont(fett)
                elif ist_marker:
                    it.setBackground(QBrush(QColor(rk).lighter(170)))
                    it.setFont(fett)
                else:
                    it.setBackground(QBrush(hg))
                    if ist_kopf:
                        it.setFont(fett)
                t.setItem(ri, j + 1, it)
            t.setRowHeight(ri, 26)
        t.setColumnWidth(0, 56)
        t.resizeColumnsToContents()
        typn = typ_name(typ)
        self.l_sub.setText(
            _("Aktiver Block: {t}. Klick auf eine Spalte – dieselbe Position darf im Kopf ein anderes Feld sein.").format(
                t=typn + (" (" + _("grün") + ")" if typ == "positionen" else "")
            )
        )

    def _zelle(self, row: int, col: int) -> None:
        if col <= 0:
            return
        self.spalte_i = col - 1
        self._tabelle()
        self._karten()

    def _fuelle_combo(self) -> None:
        self.b_feld.blockSignals(True)
        self.b_feld.clear()
        self.b_feld.addItem(_("– nicht verwenden –"), "")
        bl = self.bloecke[self.aktiv] if self.bloecke else {}
        wieder = bool(bl.get("wiederholend") or bl.get("typ") == "positionen")
        pf = ce.positionsfelder()
        for f, anz, *_r in ce.FELDER:
            if f in pf and not wieder:
                continue
            self.b_feld.addItem(_(anz) + f" ({f})", f)
        schon = (self.felder.get(self.aktiv) or {}).get(self.spalte_i, "")
        self.b_feld.setCurrentIndex(max(0, self.b_feld.findData(schon)))
        self.b_feld.blockSignals(False)

    def _feld_geaendert(self) -> None:
        if not self.bloecke:
            return
        self.felder.setdefault(self.aktiv, {})
        feld = self.b_feld.currentData() or ""
        if feld:
            self.felder[self.aktiv][self.spalte_i] = feld
        else:
            self.felder[self.aktiv].pop(self.spalte_i, None)
        self.geaendert.emit()
        self._karten()

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
            _("Pflichtfelder prüft Fakturafalter erst an der ganzen Rechnung, nicht in jedem Block.")
        )
        self.l_hinweis.setText("\n\n".join(teile))
        self.box_hinweis.setStyleSheet(
            f"QFrame {{ background: #fffaf0; border: 1px solid {HINWEIS_RD}; border-radius: 8px; }}"
        )
        self.box_spalte.setStyleSheet(
            f"QFrame {{ background: #ffffff; border: 1px solid {LINIE}; border-radius: 8px; }}"
        )

    def zuordnung_je(self) -> dict[str, dict[str, str]]:
        """typ → {feld: spaltenname oder ''} plus feld_pos am Block."""
        aus: dict[str, dict[str, str]] = {}
        for i, bl in enumerate(self.bloecke):
            typ = str(bl.get("typ") or f"block{i}")
            kopf = list(bl.get("kopf") or [])
            pos: dict[str, int] = {}
            zu: dict[str, str] = {}
            for col, f in (self.felder.get(i) or {}).items():
                name = kopf[col] if col < len(kopf) and kopf[col] else f"Spalte{col + 1}"
                zu[f] = name
                pos[f] = col + 1
            aus[typ] = zu
            bl["feld_pos"] = pos
        return aus
