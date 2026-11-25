# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Anlern-Assistent (Nur PDF) nach Skizze 11–13: links die PDF, rechts die Schritte
Bereiche → Absender → Rechnungsdaten → Positionen. Die ganze Logik steckt in ``anlernen.Sitzung``; hier nur Anzeige,
Klicks in die PDF (Wort wählen, Rahmen ziehen) und Knöpfe."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import anlernen
from ..absender import Absender, aus_csv
from .bausteine import (
    Balken,
    Schritte,
    ToastStapel,
    Zustand,
    fadenkreuz,
    fussleiste,
    karte,
    knopf,
    kopfleiste,
    lbl,
    rahmen_symbol,
    rollen,
    trenner,
)
from .texte import _

log = logging.getLogger("fakturafalter")

SCHRITTE = ("Bereiche", "Absender", "Rechnungsdaten", "Positionen")
S_BEREICHE, S_ABSENDER, S_DATEN, S_POSITIONEN = range(4)
GILT_AUF = {"alle": "allen Seiten", "erste": "erster Seite", "letzte": "letzter Seite"}
# Absender: Feld -> (Bezeichnung, Pflicht?)
ABSENDER = {
    "name": ("Firmenname", True),
    "strasse": ("Straße und Hausnummer", True),
    "zusatz": ("Adresszusatz (freiwillig)", False),
    "plz": ("PLZ", True),
    "ort": ("Ort", True),
    "ust_id": ("USt-IdNr.", False),
    "steuernummer": ("Steuernummer", False),
    "iban": ("IBAN", True),
    "bic": ("BIC (freiwillig)", False),
    "register": ("Handelsregister (freiwillig)", False),
    "telefon": ("Telefon (freiwillig)", False),
    "email": ("E-Mail (freiwillig)", False),
}
# Spaltenrahmen: Bedeutungen in dieser Reihenfolge, je eine feste Farbe (bleibt beim Verschieben gleich)
SPALTEN_RAHMEN = (
    "BT-129",
    "BT-130",
    "BT-153",
    "BT-146",
    "BT-149",
    "gesamt",
    "steuer",  # ab 0.9.7: Steuersatz/-kennzeichen je Position (Steuerfall je Position)
    "BT-155",
    "ignorieren",
)
# Steuerfall der Vorlage (Positionen): "" = Vorschlag aus dem Hinweistext im Druck
STEUERFALL_WAHL = (
    ("", "automatisch (aus dem Steuerhinweis im Druck)"),
    ("S", "Regelbesteuerung (Steuersatz aus dem Druck)"),
    ("AE", "Reverse Charge (§ 13b UStG)"),
    ("K", "Innergemeinschaftliche Lieferung"),
    ("G", "Ausfuhrlieferung (Drittland)"),
    ("O", "Nicht im Inland steuerbar"),
    ("KU", "Kleinunternehmer (§ 19 UStG)"),
)
# Wert der Steuerspalte -> Bedeutung
STEUERWERT_WAHL = (
    ("S:19", "19 %"),
    ("S:7", "7 %"),
    ("AE", "Reverse Charge (§ 13b UStG)"),
    ("K", "Innergemeinschaftliche Lieferung"),
    ("G", "Ausfuhrlieferung (Drittland)"),
    ("O", "Nicht im Inland steuerbar"),
    ("KU", "Kleinunternehmer (§ 19 UStG)"),
)
SPALTEN_FARBE = {
    "BT-129": "#1565c0",
    "BT-130": "#00838f",
    "BT-153": "#6a1b9a",
    "BT-146": "#c43e00",
    "BT-149": "#795548",
    "gesamt": "#2e7d32",
    "BT-155": "#ad1457",
    "steuer": "#455a64",
    "BT-126": "#5d4037",
    "ignorieren": "#757575",
}


class Auswahl(QComboBox):
    """Auswahlfeld, das beim Scrollen der Seite nicht mitdreht: das Mausrad ändert den Wert nur, wenn das Feld
    angeklickt (fokussiert) ist, sonst scrollt die Seite weiter. Sonst stellte z. B. „Preis gilt für“ beim
    Überscrollen still auf „1000 Einheiten“ um und die Rechnung ging beim Speichern nicht mehr auf."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e) -> None:  # noqa: N802 – Qt
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


PREISEINHEIT = (
    ("1", "1 Einheit"),
    ("100", "100 Einheiten"),
    ("1000", "1000 Einheiten"),
    ("spalte", "aus Spalte lesen"),
)


def _feldname(feld: str) -> str:
    return _(anlernen.FELDER[feld][0])


# ======================================================================================== PDF-Ansicht
class PdfSeite(QWidget):
    """Eine gerenderte Seite mit Markierungen. Modus „wort“: Klick wählt einen Abschnitt; „rahmen“: Ziehen."""

    wort_geklickt = Signal(str, list)
    rahmen_gezogen = Signal(float, float, float, float)
    grenze_gezogen = Signal(int, float)  # Spaltenlinie i auf x (PDF-Punkte) verschoben
    spalte_geaendert = Signal(
        int, float, float
    )  # Spaltenrahmen i verschoben/in der Breite geändert
    einpassen_gewuenscht = Signal()  # Doppelklick auf eine leere Stelle
    rad_zoom = Signal(float, QPointF)  # Strg+Mausrad: Faktor, Mausposition (global)

    def __init__(self, c: dict):
        super().__init__()
        self.c = c
        self.s: anlernen.Sitzung | None = None
        self.dok = None
        self.seite = 0
        self.zoom = 1.0
        self.modus = ""  # "" | "wort" | "rahmen" | "spalte" | "block"
        self.marken: list[tuple[list, str, str]] = []  # (Wörter, Art, Etikett)
        self.rahmen_zeigen = False
        # „Bereiche festlegen“: (Etikett, (x0, top, x1, bottom), aktiv?) – nur gezeichnet, fangen nie die Maus ab
        self.zonen: list[
            tuple[str, tuple, bool, list[int]]
        ] = []  # … und die Seiten, auf denen er gilt
        self._bild: QImage | None = None
        self._bild_schl = None
        self._zug: tuple[QPointF, QPointF] | None = None
        self._hover = None
        self._grenze: tuple[int, float] | None = (
            None  # (Index, x in Punkten) während eine Spaltenlinie gezogen wird
        )
        # Spaltenrahmen wird gezogen: (Index, "links"|"rechts"|"mitte", Start-x, x0, x1) und die neue Lage
        self._sp_zug: tuple[int, str, float, float, float] | None = None
        self._sp_neu: tuple[int, float, float] | None = None
        self._bereiche_schl = None
        self._bereiche: dict[int, tuple[float, float]] = {}
        self._wortflaechen: tuple[int, list[QRectF]] | None = None
        self.setMouseTracking(True)

    def laden(self, s: anlernen.Sitzung) -> None:
        import pypdfium2

        if self.dok is not None:
            self.dok.close()
        self.s = s
        # Aus dem Speicher statt über den Pfad: pdfium hält eine geöffnete Datei sonst bis zum close() fest, und
        # Windows verweigert dann das Verschieben nach „Erledigt“ (PermissionError, WinError 32).
        self.dok = pypdfium2.PdfDocument(s.pfad.read_bytes())
        self.seite = 0
        self._bild_schl = None
        self.marken = []
        self.groesse_setzen()

    def seiten(self) -> int:
        return len(self.dok) if self.dok is not None else 0

    def pt(self) -> tuple[float, float]:
        if self.dok is None:
            return 595.0, 842.0
        return self.dok[self.seite].get_size()

    def zoom_setzen(self, z: float) -> None:
        """Neuer Zoom. Ein Rahmen, der gerade gezogen wird, behält seine Lage auf der Seite (er ist in
        Bildschirmpunkten gespeichert); Spaltenlinien und Markierungen rechnen ohnehin in PDF-Punkten."""
        alt, self.zoom = self.zoom, z
        if self._zug and alt != z:
            f = z / alt
            self._zug = tuple(QPointF((p.x() - 1) * f + 1, (p.y() - 1) * f + 1) for p in self._zug)
        self.groesse_setzen()

    def zug_nachfuehren(self) -> None:
        """Nach Zoom/Scrollen während des Ziehens: das Rahmenende folgt wieder dem Mauszeiger."""
        if self._zug:
            self._zug = (self._zug[0], QPointF(self.mapFromGlobal(QCursor.pos())))
            self.update()

    def wheelEvent(self, e):  # noqa: N802 – Qt
        """Strg+Mausrad zoomt (PdfBereich), das Rad allein geht an die Scrollfläche weiter."""
        d = e.angleDelta().y() or e.angleDelta().x()
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and d:
            self.rad_zoom.emit(1.2 ** (d / 120), QPointF(self.mapToGlobal(e.position().toPoint())))
            e.accept()
        else:
            e.ignore()

    def mouseDoubleClickEvent(self, e):  # noqa: N802 – Qt
        """Doppelklick auf eine leere Stelle (kein Wort, keine Spaltenlinie): Seite einpassen."""
        if e.button() != Qt.MouseButton.LeftButton:
            return
        x, y = self._in_pt(e.position())
        leer = self.s is None or (
            not self.s.wort_an(self.seite, x, y)
            and self._grenze_an(e.position()) is None
            and self._spaltenrahmen_an(e.position()) is None
        )
        if leer and not self._zug:
            self.einpassen_gewuenscht.emit()
        else:
            self.mousePressEvent(e)

    def groesse_setzen(self) -> None:
        b, h = self.pt()
        self.setFixedSize(int(b * self.zoom) + 2, int(h * self.zoom) + 2)
        self.update()

    def _bild_holen(self) -> QImage | None:
        if self.dok is None:
            return None
        dpr = self.devicePixelRatioF()
        schl = (self.seite, round(self.zoom * dpr, 3))
        if schl != self._bild_schl:
            pil = self.dok[self.seite].render(scale=self.zoom * dpr * 1.5).to_pil().convert("RGB")
            self._bild = QImage(
                pil.tobytes(), pil.width, pil.height, pil.width * 3, QImage.Format.Format_RGB888
            ).copy()
            self._bild_schl = schl
        return self._bild

    def schliessen(self) -> None:
        if self.dok is not None:
            self.dok.close()
            self.dok = None

    # -- Maus ---------------------------------------------------------------------------------------
    def _in_pt(self, pos) -> tuple[float, float]:
        return (pos.x() - 1) / self.zoom, (pos.y() - 1) / self.zoom

    def _grenze_an(self, pos) -> int | None:
        """Index der Spaltenlinie unter dem Mauszeiger (±6 px), sonst None."""
        t = self.s.tabelle if self.s is not None else None
        if (
            self.modus != "rahmen"
            or not self.rahmen_zeigen
            or t is None
            or t.leer()
            or t.seite != self.seite
            or t.spaltenrahmen
        ):
            return None
        x, y = self._in_pt(pos)
        if not t.top - 2 <= y <= t.bottom + 2:
            return None
        nah = [(abs(gx - x) * self.zoom, i) for i, gx in enumerate(t.grenzen) if i > 0]
        nah = [n for n in nah if n[0] <= 6]
        return min(nah)[1] if nah else None

    def _spaltenrahmen_an(self, pos) -> tuple[int, str] | None:
        """Spaltenrahmen unter dem Mauszeiger: Kante (±6 px) zum Verbreitern, Etikett über der Tabelle (beim
        Spalten-Ziehen) zum Verschieben. Die Fläche selbst bleibt frei, damit neue Spaltenrahmen darüber gehen."""
        t = self.s.tabelle if self.s is not None else None
        if (
            self.modus not in ("rahmen", "spalte")
            or not self.rahmen_zeigen
            or t is None
            or not t.spaltenrahmen
            or t.seite != self.seite
        ):
            return None
        x, y = self._in_pt(pos)
        if self.modus == "spalte" and t.top - 14 / self.zoom <= y < t.top + 2 / self.zoom:
            for i, (_c, a, b) in enumerate(t.spaltenrahmen):
                if a <= x <= b:
                    return i, "mitte"
        if not t.top - 2 <= y <= t.bottom + 2:
            return None
        kanten = []
        for i, (_c, a, b) in enumerate(t.spaltenrahmen):
            kanten += [(abs(x - a) * self.zoom, i, "links"), (abs(x - b) * self.zoom, i, "rechts")]
        d, i, art = min(kanten)
        return (i, art) if d <= 6 else None

    def zieht(self) -> bool:
        """Ein neuer Rahmen wird gerade aufgezogen (nicht: Kante/Linie verschieben)."""
        return bool(self._zug) and not self._sp_zug and not self._grenze

    def tabellen_bereich(self, seite: int | None = None) -> tuple[float, float] | None:
        """(top, bottom) der Tabelle auf dieser Seite – auf Folgeseiten aus den dort gelesenen Positionen."""
        if self.s is None or self.s.tabelle.leer():
            return None
        t = self.s.tabelle
        schl = (id(self.s), repr(t))
        if schl != self._bereiche_schl:
            try:
                self._bereiche = self.s.tabellen_bereiche()
            except Exception:  # Anzeige darf nie am Lesen scheitern
                self._bereiche = {t.seite: (t.top, t.bottom)}
            self._bereiche_schl = schl
        return self._bereiche.get(self.seite if seite is None else seite)

    def _woerter_flaechen(self) -> list[QRectF]:
        """Wortflächen der Seite in Pixeln – Etiketten weichen ihnen aus, damit sie keinen Text verdecken."""
        if self._wortflaechen is None or self._wortflaechen[0] != (
            self.seite,
            self.zoom,
            id(self.s),
        ):
            z = self.zoom
            fl = [
                QRectF(
                    w.x0 * z,
                    (w.top + (w.bottom - w.top) * 0.2) * z,
                    (w.x1 - w.x0) * z,
                    (w.bottom - w.top) * 0.65 * z,
                )
                for w in self.s.woerter(self.seite)
            ]  # Schrift ohne Luft
            self._wortflaechen = ((self.seite, self.zoom, id(self.s)), fl)
        return self._wortflaechen[1]

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.s is None:
            return
        zeichnen = self.modus in ("rahmen", "spalte", "block")
        sp = self._spaltenrahmen_an(e.position())
        if sp is not None:
            _c, a, b = self.s.tabelle.spaltenrahmen[sp[0]]
            self._sp_zug = (sp[0], sp[1], self._in_pt(e.position())[0], a, b)
            self._sp_neu = (sp[0], a, b)
            if (
                zeichnen and sp[1] != "mitte"
            ):  # senkrecht weitergezogen = neuer Rahmen (Kante fängt nicht ab)
                self._zug = (e.position(), e.position())
            return
        i = self._grenze_an(e.position())
        if i is not None:
            self._grenze = (i, self.s.tabelle.grenzen[i])
            if zeichnen:  # ebenso an einer Spaltenlinie
                self._zug = (e.position(), e.position())
            return
        if self.modus in ("rahmen", "block"):
            self._zug = (e.position(), e.position())
            self.update()
        elif self.modus == "wort":
            x, y = self._in_pt(e.position())
            treffer = self.s.wort_an(self.seite, x, y)
            if treffer:
                self.wort_geklickt.emit(treffer[0], treffer[1])

    def mouseMoveEvent(self, e):
        if self._sp_zug and self._zug:
            self._zug = (self._zug[0], e.position())
            if abs(e.position().y() - self._zug[0].y()) > 10:  # Rechteck statt Kante: neuer Rahmen
                self._sp_zug = self._sp_neu = None
                self.update()
                return
        if self._sp_zug:
            i, art, x_start, a, b = self._sp_zug
            dx = self._in_pt(e.position())[0] - x_start
            if art == "links":
                a = min(a + dx, b - 4)
            elif art == "rechts":
                b = max(b + dx, a + 4)
            else:
                a, b = a + dx, b + dx
            self._sp_neu = (i, a, b)
            self.update()
            return
        if self._grenze and self._zug:
            self._zug = (self._zug[0], e.position())
            if abs(e.position().y() - self._zug[0].y()) > 10:  # Rechteck statt Linie: neuer Rahmen
                self._grenze = None
                self.update()
                return
        if self._grenze:
            self._grenze = (self._grenze[0], self._in_pt(e.position())[0])
            self.update()
            return
        if self.modus in ("rahmen", "spalte") and not self._zug:
            sp = self._spaltenrahmen_an(e.position())
            self.setCursor(
                Qt.CursorShape.SizeAllCursor
                if sp and sp[1] == "mitte"
                else Qt.CursorShape.SplitHCursor
                if sp or self._grenze_an(e.position()) is not None
                else Qt.CursorShape.CrossCursor
            )
        if self._zug:
            self._zug = (self._zug[0], e.position())
            self.update()
        elif self.modus in ("wort", "block") and self.s is not None:
            x, y = self._in_pt(e.position())
            t = self.s.wort_an(self.seite, x, y)
            neu = t[1] if t else None
            if neu != self._hover:
                self._hover = neu
                self.setCursor(
                    Qt.CursorShape.PointingHandCursor
                    if neu
                    else Qt.CursorShape.CrossCursor
                    if self.modus == "block"
                    else Qt.CursorShape.ArrowCursor
                )
                self.update()

    def mouseReleaseEvent(self, e):
        if self._sp_zug:
            i, a, b = self._sp_neu
            alt = self._sp_zug
            self._sp_zug = self._sp_neu = self._zug = None
            if (a, b) != (alt[3], alt[4]):
                self.spalte_geaendert.emit(i, a, b)
            self.update()
            return
        if self._grenze:
            i, x = self._grenze
            self._grenze = self._zug = None
            self.grenze_gezogen.emit(i, x)
            self.update()
            return
        if not self._zug:
            return
        a, b = self._zug
        self._zug = None
        x0, y0 = self._in_pt(a)
        x1, y1 = self._in_pt(b)
        if abs(x1 - x0) > 20 and abs(y1 - y0) > 10:
            self.rahmen_gezogen.emit(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        elif self.modus == "block":  # Klick (Strg+Klick) ohne Ziehen: eine Zeile dazu/weg
            treffer = self.s.wort_an(self.seite, x1, y1)
            if treffer:
                self.wort_geklickt.emit(treffer[0], treffer[1])
        self.update()

    def modus_setzen(self, m: str) -> None:
        self.modus = m
        self._hover = None
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if m in ("rahmen", "spalte", "block")
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    # -- Zeichnen -----------------------------------------------------------------------------------
    def paintEvent(self, _e):
        z, c = self.zoom, self.c
        b, h = self.pt()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(QRectF(1, 1, b * z, h * z), QColor("#ffffff"))
        bild = self._bild_holen()
        if bild is not None:
            p.drawImage(QRectF(1, 1, b * z, h * z), bild)
        p.setPen(QPen(QColor(c["card_b"]), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(0.5, 0.5, b * z + 1, h * z + 1))
        if self.s is None:
            p.end()
            return
        if self.modus in ("wort", "block"):  # anklickbare Wörter ganz dezent
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(21, 101, 192, 18))
            for w in self.s.woerter(self.seite):
                p.drawRect(QRectF(w.x0 * z, w.top * z, (w.x1 - w.x0) * z, (w.bottom - w.top) * z))
        farbe = {"erkannt": c["ok"], "pruefen": c["busy"], "warten": c["acc"], "kandidat": c["acc"]}
        f = QFont("Liberation Sans")
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        marken = list(self.marken)
        if self._hover:
            marken.append((self._hover, "kandidat", ""))
        # Beim Aufziehen eines neuen Rahmens treten vorhandene Rahmen und Etiketten zurück (blass); Mausereignisse
        # fangen sie dabei ohnehin nicht ab – Kanten und Linien geben einen senkrechten Zug an den neuen Rahmen ab.
        zieht = self.zieht()
        blass = 0.22 if zieht else 0.6 if self.modus in ("rahmen", "spalte", "block") else 1.0
        woerter = self._woerter_flaechen()
        belegt = []
        for ws, art, et in marken:  # erst alle Rahmen merken, damit Etiketten keine Werte verdecken
            ws_ = [w for w in ws if getattr(w, "seite", self.seite) == self.seite]
            if ws_:
                belegt.append(
                    QRectF(
                        min(w.x0 for w in ws_) * z - 3,
                        min(w.top for w in ws_) * z - 2,
                        (max(w.x1 for w in ws_) - min(w.x0 for w in ws_)) * z + 6,
                        (max(w.bottom for w in ws_) - min(w.top for w in ws_)) * z + 4,
                    )
                )
        klein_et = QFont(f)
        klein_et.setPixelSize(10)
        for ws, art, et in marken:
            ws = [w for w in ws if getattr(w, "seite", self.seite) == self.seite]
            if not ws:
                continue
            p.setOpacity(1.0 if art == "kandidat" else blass)
            q = QColor(farbe.get(art, c["acc"]))
            x0, y0 = min(w.x0 for w in ws), min(w.top for w in ws)
            x1, y1 = max(w.x1 for w in ws), max(w.bottom for w in ws)
            r = QRectF(x0 * z - 3, y0 * z - 2, (x1 - x0) * z + 6, (y1 - y0) * z + 4)
            fuell = QColor(q)
            fuell.setAlpha(45 if art != "kandidat" else 30)
            p.setBrush(fuell)
            p.setPen(QPen(q, 2 if art in ("warten", "kandidat") else 1.5))
            p.drawRoundedRect(r, 3, 3)
            if et:
                p.setFont(klein_et)
                tag = self._etikett_platz(
                    r, p.fontMetrics().horizontalAdvance(et) + 8, belegt, woerter
                )
                p.setFont(f)
                if tag is None:  # kein Platz: Etikett weglassen, die Farbe zeigt den Zustand
                    continue
                belegt.append(tag)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(q)
                p.drawRoundedRect(tag, 3, 3)
                p.setFont(klein_et)
                p.setPen(QColor("#3e2723") if art == "pruefen" else QColor("#ffffff"))
                p.drawText(tag, Qt.AlignmentFlag.AlignCenter, et)
                p.setFont(f)
        p.setOpacity(1.0)
        for et, (x0, y0, x1, y1), aktiv, seiten in self.zonen:
            if self.seite not in seiten:
                continue
            p.setOpacity(0.25 if zieht else 1.0)
            q = QColor(c["acc"] if aktiv else c["ok"])
            p.setBrush(QColor(q.red(), q.green(), q.blue(), 16))
            p.setPen(QPen(q, 2, Qt.PenStyle.DashLine))
            r = QRectF(x0 * z, y0 * z, (x1 - x0) * z, (y1 - y0) * z)
            p.drawRect(r)
            p.setFont(klein_et)
            tag = QRectF(r.x(), max(0.0, r.y() - 15), p.fontMetrics().horizontalAdvance(et) + 8, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(q)
            p.drawRoundedRect(tag, 3, 3)
            p.setPen(QColor("#ffffff"))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, et)
            p.setFont(f)
        p.setOpacity(1.0)
        t = self.s.tabelle
        ber = self.tabellen_bereich() if self.rahmen_zeigen else None
        if ber is not None:
            top, bot = ber
            folge = t.seite != self.seite  # Folgeseite: gleicher Rahmen, nur zur Ansicht
            p.setOpacity(
                0.22
                if zieht and self.modus != "spalte"
                else 0.4
                if zieht
                else 0.6
                if folge
                else 1.0
            )
            q = QColor(c["acc"])
            p.setBrush(QColor(q.red(), q.green(), q.blue(), 14))
            p.setPen(QPen(q, 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(t.x0 * z, top * z, (t.x1 - t.x0) * z, (bot - top) * z))
            if t.spaltenrahmen:
                self._spaltenrahmen_malen(p, f, top, bot)
            else:
                p.setPen(QPen(q, 1.5))
                for i, sx in enumerate(t.grenzen):
                    if i == 0:
                        continue
                    if (
                        self._grenze and self._grenze[0] == i and not folge
                    ):  # gezogene Linie kräftiger
                        p.setPen(QPen(q, 3))
                        sx = self._grenze[1]
                    p.drawLine(QPointF(sx * z, top * z), QPointF(sx * z, bot * z))
                    p.setPen(QPen(q, 1.5))
                klein = QFont(f)
                klein.setPixelSize(10)
                p.setFont(klein)
                g = list(t.grenzen) + [t.x1]
                for i, n in enumerate(t.spalten):
                    if i + 1 >= len(g):
                        break
                    tag = QRectF(
                        g[i] * z + 2, top * z - 13, max(8.0, (g[i + 1] - g[i]) * z - 4), 14
                    )
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(c["off"]) if n == "ignorieren" else q)
                    p.drawRoundedRect(tag, 3, 3)
                    p.setPen(QColor("#ffffff"))
                    name = _(anlernen.SPALTEN[n]).split(" (")[0]
                    p.drawText(
                        tag,
                        Qt.AlignmentFlag.AlignCenter,
                        p.fontMetrics().elidedText(
                            name, Qt.TextElideMode.ElideRight, int(tag.width()) - 4
                        ),
                    )
            p.setOpacity(1.0)
        if zieht:
            a, b_ = self._zug
            p.setBrush(QColor(21, 101, 192, 30))
            p.setPen(QPen(QColor(c["acc"]), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(a, b_).normalized())
        p.end()

    @staticmethod
    def _etikett_platz(
        r: QRectF, bt: float, belegt: list[QRectF], woerter: list[QRectF]
    ) -> QRectF | None:
        """Platz für ein Etikett am Rahmen: zuerst auf dem Rahmenrand (halb drüber), dann knapp außen – jeweils
        nur, wo es weder Text noch andere Rahmen/Etiketten verdeckt. Auf dem Rand reicht es, wenn kein Text
        darunter liegt; ein Etikett mitten auf einem Wert gibt es nicht mehr."""
        h = 12.0
        kand = [
            QRectF(r.right() - bt - 4, r.top() - h + 3, bt, h),
            QRectF(r.left() + 4, r.top() - h + 3, bt, h),
            QRectF(r.right() - bt - 4, r.bottom() - 3, bt, h),
            QRectF(r.left() + 4, r.bottom() - 3, bt, h),
            QRectF(r.left(), r.top() - h - 1, bt, h),
            QRectF(r.left(), r.bottom() + 1, bt, h),
            QRectF(r.left() - bt - 2, r.top(), bt, h),
            QRectF(r.right() + 2, r.top(), bt, h),
        ]
        for k in kand:
            if k.top() < 0 or k.left() < 0:
                continue
            if any(k.intersects(w) for w in woerter):
                continue
            if any(k.intersects(x) for x in belegt if x != r):
                continue
            return k
        return None

    def _spaltenrahmen_malen(self, p: QPainter, f: QFont, top: float, bot: float) -> None:
        """Jede Spalte als eigener, farbiger Rahmen; Etikett als Reiter auf der oberen Kante (verdeckt kaum Text)."""
        z, t = self.zoom, self.s.tabelle
        klein = QFont(f)
        klein.setPixelSize(10)
        p.setFont(klein)
        for i, (code, a, b) in enumerate(t.spaltenrahmen):
            if self._sp_neu and self._sp_neu[0] == i and t.seite == self.seite:
                a, b = self._sp_neu[1], self._sp_neu[2]
            q = QColor(SPALTEN_FARBE.get(code, "#757575"))
            fuell = QColor(q)
            fuell.setAlpha(34)
            p.setBrush(fuell)
            p.setPen(QPen(q, 3 if self._sp_neu and self._sp_neu[0] == i else 2))
            r = QRectF(a * z, top * z + 1, (b - a) * z, (bot - top) * z - 2)
            p.drawRect(r)
            tag = QRectF(r.left(), top * z - 13, max(10.0, r.width()), 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(q)
            p.drawRoundedRect(tag, 3, 3)
            p.setPen(QColor("#ffffff"))
            name = _(anlernen.SPALTEN.get(code, code)).split(" (")[0]
            p.drawText(
                tag,
                Qt.AlignmentFlag.AlignCenter,
                p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(tag.width()) - 4),
            )


class PdfBereich(QWidget):
    """Linke Spalte: Dateiname, Seite, Zoom, Banner „Klicke in der PDF auf …“, PDF in Scrollfläche."""

    def __init__(self, c: dict):
        super().__init__()
        self.c = c
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 8, 12)
        v.setSpacing(8)
        h = QHBoxLayout()
        h.setSpacing(6)
        self.l_kopf = lbl("", "sub")
        h.addWidget(self.l_kopf, 1)
        self.b_zurueck = knopf("<", tip=_("Vorige Seite"), klick=lambda: self.blaettern(-1))
        self.b_vor = knopf(">", tip=_("Nächste Seite"), klick=lambda: self.blaettern(1))
        self.b_klein = knopf(
            "−", tip=_("Verkleinern (Strg+Mausrad)"), klick=lambda: self.zoomen(1 / 1.2)
        )
        self.b_ganz = knopf(
            _("Ganze Seite"),
            tip=_("Seite einpassen (auch: Doppelklick auf eine leere Stelle)"),
            klick=self.einpassen,
        )
        self.b_gross = knopf(
            "+", tip=_("Vergrößern (Strg+Mausrad)"), klick=lambda: self.zoomen(1.2)
        )
        for b in (self.b_zurueck, self.b_vor, self.b_klein, self.b_ganz, self.b_gross):
            if len(b.text()) == 1:
                b.setFixedWidth(48)
            h.addWidget(b)
        v.addLayout(h)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setStyleSheet(
            f"QFrame#banner {{ background:{c['sel']}; border:1px solid {c['acc']}; border-radius:6px; }}"
        )
        bh = QHBoxLayout(self.banner)
        bh.setContentsMargins(12, 4, 6, 4)
        self.l_banner = lbl("", umbruch=True)
        bh.addWidget(self.l_banner, 1)
        self._abbrechen = None
        self._uebernehmen = None
        self.b_banner_ok = knopf(
            _("Übernehmen"), primary=True, klick=lambda: self._uebernehmen and self._uebernehmen()
        )
        self.b_banner_ok.setVisible(False)
        bh.addWidget(self.b_banner_ok)
        self.b_banner = knopf(_("Abbrechen"), klick=lambda: self._abbrechen and self._abbrechen())
        bh.addWidget(self.b_banner)
        self.banner.setVisible(False)
        v.addWidget(self.banner)
        self.seite = PdfSeite(c)
        hinter = QWidget()
        hinter.setStyleSheet(f"background:{c['bar']};")
        hl = QVBoxLayout(hinter)
        hl.setContentsMargins(12, 12, 12, 12)
        hl.addWidget(self.seite, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidget(hinter)
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(56)  # bei 250 % braucht das umgebrochene Banner den Platz
        self.scroll.setStyleSheet(f"QScrollArea {{ border:1px solid {c['card_b']}; }}")
        v.addWidget(self.scroll, 1)
        self._eingepasst = True
        # Strg+Mausrad zoomt zur Mausposition, das Mausrad allein scrollt; Doppelklick ins Leere passt ein
        self.scroll.viewport().installEventFilter(self)
        self.seite.einpassen_gewuenscht.connect(self.einpassen)
        self.seite.rad_zoom.connect(
            lambda f, g: self.zoomen(f, QPointF(self.scroll.viewport().mapFromGlobal(g.toPoint())))
        )

    def laden(self, s: anlernen.Sitzung) -> None:
        self.seite.laden(s)
        self._eingepasst = True
        self.einpassen()

    def kopf(self) -> None:
        s = self.seite.s
        n = self.seite.seiten()
        name = s.pfad.name if s else ""
        self.l_kopf.setText(
            _("{datei}  ·  Seite {i} von {n}").format(datei=name, i=self.seite.seite + 1, n=n)
        )
        self.b_zurueck.setVisible(n > 1)
        self.b_vor.setVisible(n > 1)
        self.b_zurueck.setEnabled(self.seite.seite > 0)
        self.b_vor.setEnabled(self.seite.seite < n - 1)

    def blaettern(self, d: int) -> None:
        self.zeige_seite(self.seite.seite + d)

    def zeige_seite(self, i: int) -> None:
        i = max(0, min(self.seite.seiten() - 1, i))
        if i != self.seite.seite:
            self.seite.seite = i
            self.seite._bild_schl = None
            self.seite.groesse_setzen()
        self.kopf()

    def zoomen(self, f: float, anker: QPointF | None = None) -> None:
        """Zoom um Faktor ``f``. ``anker`` (Punkt im sichtbaren Ausschnitt, Standard: Mitte) bleibt dabei an
        derselben Stelle der Seite unter dem Mauszeiger."""
        vp = self.scroll.viewport()
        if anker is None:
            anker = QPointF(vp.width() / 2, vp.height() / 2)
        alt = self.seite.zoom
        neu = max(0.4, min(3.0, alt * f))
        if abs(neu - alt) < 1e-6:
            return
        self._eingepasst = False
        x, y = self.seite._in_pt(QPointF(self.seite.mapFrom(vp, anker.toPoint())))
        self.seite.zoom_setzen(neu)
        self._layout_jetzt()
        ziel = self.seite.mapTo(vp, QPointF(x * neu + 1, y * neu + 1).toPoint())
        h, v = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
        h.setValue(h.value() + round(ziel.x() - anker.x()))
        v.setValue(v.value() + round(ziel.y() - anker.y()))
        self.seite.zug_nachfuehren()

    def _layout_jetzt(self) -> None:
        """Neue Seitengröße sofort in Scrollfläche und Bildlaufleisten übernehmen (nicht erst beim nächsten
        Ereignis), damit die Position für den Zoom-Anker stimmt."""
        hinter = self.scroll.widget()
        hinter.layout().activate()
        QApplication.sendPostedEvents(hinter, QEvent.Type.LayoutRequest)
        QApplication.sendPostedEvents(self.scroll, QEvent.Type.LayoutRequest)
        hinter.resize(
            max(self.scroll.viewport().width(), hinter.sizeHint().width()),
            max(self.scroll.viewport().height(), hinter.sizeHint().height()),
        )

    def eventFilter(self, obj, ev):  # noqa: N802 – Qt
        if obj is self.scroll.viewport():
            if (
                ev.type() == QEvent.Type.Wheel
                and ev.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                d = ev.angleDelta().y() or ev.angleDelta().x()
                if d:
                    self.zoomen(1.2 ** (d / 120), ev.position())
                return True
            if (
                ev.type() == QEvent.Type.MouseButtonDblClick
                and ev.button() == Qt.MouseButton.LeftButton
            ):
                self.einpassen()  # Doppelklick auf den grauen Rand
                return True
        return False

    def einpassen(self) -> None:
        self._eingepasst = True
        b, _h = self.seite.pt()
        breite = max(200, self.scroll.viewport().width() - 44)
        self.seite.zoom_setzen(max(0.4, min(2.0, breite / b)))
        self.seite.zug_nachfuehren()
        self.kopf()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._eingepasst:
            self.einpassen()
        QTimer.singleShot(0, self._banner_hoehe)

    def _banner_hoehe(self) -> None:
        """Umgebrochenen Bannertext nie abschneiden (bei 250 % passt er sonst nicht neben die Knöpfe)."""
        if self.banner.isVisible() and self.l_banner.width() > 0:
            self.l_banner.setMinimumHeight(self.l_banner.heightForWidth(self.l_banner.width()))

    def zeige_woerter(self, ws: list) -> None:
        """Zur Fundstelle blättern und scrollen."""
        if not ws:
            return
        self.zeige_seite(ws[0].seite)
        y = int(ws[0].top * self.seite.zoom)
        sb = self.scroll.verticalScrollBar()
        if not (sb.value() + 40 < y < sb.value() + self.scroll.viewport().height() - 40):
            sb.setValue(max(0, y - self.scroll.viewport().height() // 3))

    def banner_zeigen(self, html: str | None, abbrechen=None, uebernehmen=None) -> None:
        self.banner.setVisible(bool(html))
        self.l_banner.setText(html or "")
        self._abbrechen = abbrechen
        self._uebernehmen = uebernehmen
        self.b_banner_ok.setVisible(uebernehmen is not None)
        self.b_banner_ok.setEnabled(False)
        self.l_banner.setMinimumHeight(0)
        QTimer.singleShot(0, self._banner_hoehe)


# ======================================================================================== Feldzeile
class Feldzeile(QFrame):
    """Bezeichnung über dem Feld, Zustandssymbol links, „Passt“ und Ziel-Knopf rechts, Hinweis darunter."""

    def __init__(self, c: dict, name: str, bei_ziel, bei_text, bei_passt=None, bei_bereich=None):
        super().__init__()
        self.c = c
        self.setObjectName("zeile")
        g = QGridLayout(self)
        g.setContentsMargins(8, 6, 8, 6)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(4)
        self.sym = Zustand(c, "fehlt")
        g.addWidget(self.sym, 1, 0, Qt.AlignmentFlag.AlignVCenter)
        self.l_name = lbl(name, umbruch=True)
        g.addWidget(self.l_name, 0, 1, 1, 4)
        self.e = QLineEdit()
        self.e.setPlaceholderText(_("In der PDF anklicken oder eintippen"))
        self.e.setAccessibleName(name)
        self.e.editingFinished.connect(lambda: bei_text(self.e.text()))
        g.addWidget(self.e, 1, 1)
        self.b_passt = knopf(_("Passt"), klick=lambda: bei_passt and bei_passt())
        self.b_passt.setVisible(False)
        g.addWidget(self.b_passt, 1, 2)
        self.b_ziel = knopf("", tip=_("Wert in der PDF anklicken"), klick=bei_ziel)
        self.b_ziel.setFixedWidth(48)
        g.addWidget(self.b_ziel, 1, 3)
        self.b_bereich = knopf(
            "",
            tip=_(
                "Bereich ziehen: Rahmen um den Wert in der PDF ziehen (mehrere Wörter oder Zeilen)"
            ),
            klick=lambda: bei_bereich and bei_bereich(),
        )
        self.b_bereich.setFixedWidth(48)
        self.b_bereich.setAccessibleName(_("Bereich ziehen"))
        self.b_bereich.setVisible(bei_bereich is not None)
        g.addWidget(self.b_bereich, 1, 4)
        self.l_hilfe = lbl("", "hinweis", umbruch=True)
        self.l_hilfe.setVisible(False)
        g.addWidget(self.l_hilfe, 2, 1, 1, 4)
        g.setColumnStretch(1, 1)
        self.aktiv(False)

    def setzen(self, wert: str, zustand: str, hilfe: str = "", passt: bool = False) -> None:
        if self.e.text() != wert:
            self.e.setText(wert)
            self.e.setCursorPosition(0)
        self.sym.setzen(zustand)
        self.b_passt.setVisible(passt)
        self.l_hilfe.setText(hilfe)
        self.l_hilfe.setObjectName("warn" if zustand == "pruefen" else "hinweis")
        self.l_hilfe.setStyleSheet("")  # Objektname neu anwenden
        self.l_hilfe.setVisible(bool(hilfe))

    def aktiv(self, an: bool, bereich: bool = False) -> None:
        c = self.c
        self.setStyleSheet(
            f"QFrame#zeile {{ background:{c['sel']}; border:2px solid {c['acc']}; border-radius:6px; }}"
            if an
            else "QFrame#zeile { border:2px solid transparent; }"
        )
        for b, ein, symbol in (
            (self.b_ziel, an and not bereich, fadenkreuz),
            (self.b_bereich, an and bereich, rahmen_symbol),
        ):
            b.setIcon(symbol("#ffffff" if ein else c["sub"]))
            b.setProperty("primary", ein)
            b.style().unpolish(b)
            b.style().polish(b)


def _legende(c: dict) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setSpacing(6)
    for z, t in (("erkannt", _("erkannt")), ("pruefen", _("bitte prüfen")), ("fehlt", _("fehlt"))):
        h.addWidget(Zustand(c, z, 20))
        h.addWidget(lbl(t, "sub"))
        h.addSpacing(10)
    h.addStretch(1)
    return h


def _nebeneinander(*ws, stretch=None) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    for i, x in enumerate(ws):
        h.addWidget(x, (stretch or [1] * len(ws))[i])
    return w


class _Umbruch(QWidget):
    """Widgets nebeneinander; wird es zu eng (große Schrift, schmales Fenster), untereinander statt
    abgeschnitten."""

    def __init__(self, *ws, stretch=None):
        super().__init__()
        self._ws = ws
        self._l = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._l.setContentsMargins(0, 0, 0, 0)
        self._l.setSpacing(4)
        for i, x in enumerate(ws):
            self._l.addWidget(x, (stretch or [1] * len(ws))[i])

    def _breit(self) -> int:
        return sum(w.sizeHint().width() for w in self._ws if not w.isHidden()) + 4 * (
            len(self._ws) - 1
        )

    def minimumSizeHint(self):  # noqa: N802 – Qt
        m = super().minimumSizeHint()
        m.setWidth(
            max((w.minimumSizeHint().width() for w in self._ws if not w.isHidden()), default=0)
        )
        return m

    def resizeEvent(self, ev):  # noqa: N802 – Qt
        r = (
            QBoxLayout.Direction.LeftToRight
            if ev.size().width() >= self._breit()
            else QBoxLayout.Direction.TopToBottom
        )
        if self._l.direction() != r:
            self._l.setDirection(r)
        super().resizeEvent(ev)


# ======================================================================================== Assistent
class AnlernAssistent(QDialog):
    """Arbeitet die PDFs nacheinander ab. ``pdfs`` liegen schon im Anlern-Ordner (werden nach „Erledigt“
    verschoben, sobald sie gespeichert sind)."""

    def __init__(
        self, parent, k, konfig_pfad: Path, pdfs: list[Path], c: dict, bereiche_zuerst: bool = False
    ):
        super().__init__(parent)
        self.k, self.konfig_pfad, self.c = k, Path(konfig_pfad), c
        self.bereiche_zuerst = bereiche_zuerst  # über „Bereiche bearbeiten“ geöffnet
        self.pdfs = list(pdfs)
        self.i = 0
        self.gespeichert = 0
        self.s: anlernen.Sitzung | None = None
        self.schritt = 0
        self.ziel: tuple[str, str] | None = (
            None  # ("abs"|"feld"|"bereich"|"block", Schlüssel), wartet auf die PDF
        )
        self._block_ws: list[list] = []  # „Anschrift als Block“: per Klick gewählte Zeilen
        self.setObjectName("wurzel")
        self.setWindowTitle(_("Vorlage anlernen"))
        self.resize(1280, 900)
        self.toasts = ToastStapel(self, abstand_unten=90)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        kopf, kv, self.l_titel = kopfleiste("")
        self.stepper = Schritte(c, [_(s) for s in SCHRITTE])
        kv.addWidget(self.stepper)
        v.addWidget(kopf)

        mitte = QWidget()
        m = QHBoxLayout(mitte)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(0)
        self.pdf = PdfBereich(c)
        self.pdf.seite.wort_geklickt.connect(self._wort_geklickt)
        self.pdf.seite.rahmen_gezogen.connect(self._rahmen_gezogen)
        self.pdf.seite.grenze_gezogen.connect(self._grenze_gezogen)
        self.pdf.seite.spalte_geaendert.connect(self._spalte_geaendert)
        m.addWidget(self.pdf, 11)
        self.stapel = QStackedWidget()
        m.addWidget(self.stapel, 10)
        v.addWidget(mitte, 1)

        fuss, links, self.l_fuss, rechts = fussleiste(c)
        self.b_abbrechen = knopf(_("Abbrechen"), klick=self.reject)
        self.b_zurueck = knopf(_("Zurück"), klick=lambda: self.schritt_setzen(self.schritt - 1))
        links.addWidget(self.b_abbrechen)
        links.addWidget(self.b_zurueck)
        self.b_weiter = knopf("", primary=True, klick=self._weiter)
        self.b_speichern = knopf(_("Speichern && nächste PDF"), klick=self.speichern)
        rechts.addWidget(self.b_weiter)
        rechts.addWidget(self.b_speichern)
        v.addWidget(fuss)
        self._laden()

    # -- PDF laden ----------------------------------------------------------------------------------
    def _laden(self) -> bool:
        while self.i < len(self.pdfs):
            p = self.pdfs[self.i]
            if p.exists():
                try:
                    self.s = anlernen.Sitzung(p, self.k)
                    break
                except Exception as e:  # noqa: BLE001 – kaputte PDF: überspringen, Details ins Log
                    log.warning("Anlernen: %s nicht lesbar: %s", p.name, e)
                    self.toast("fehler", _("PDF nicht lesbar"), p.name)
            self.i += 1
        else:
            self.s = None
            return False
        s = self.s
        prof, abw = getattr(self, "_kontrolle", (None, {}))
        if (
            abw
            and prof is not None
            and s.profil is not None
            and anlernen.pdferkennung.profil_name(s.profil)
            == anlernen.pdferkennung.profil_name(prof)
        ):
            s.kontrolle_markieren(abw)  # Selbstkontrolle der letzten PDF: Felder hier markieren
        name = (s.profil or {}).get("name") or s.absender.name or _("neuer Absender")
        self.l_titel.setText(
            _("Vorlage anlernen: {name}  ·  PDF {i} von {n}").format(
                name=name, i=self.i + 1, n=len(self.pdfs)
            )
        )
        self.pdf.laden(s)
        while self.stapel.count():
            w = self.stapel.widget(0)
            self.stapel.removeWidget(w)
            w.deleteLater()
        self.stapel.addWidget(self._seite_bereiche())
        self.stapel.addWidget(self._seite_absender())
        self.stapel.addWidget(self._seite_daten())
        self.stapel.addWidget(self._seite_positionen())
        self.schritt = -1
        # Bereiche zuerst: neue Vorlage (noch keine Bereiche) oder „Bereiche bearbeiten“
        if self.bereiche_zuerst or not s.zonen:
            self.schritt_setzen(S_BEREICHE)
        else:
            self.schritt_setzen(S_DATEN if self._absender_bekannt() else S_ABSENDER)
        return True

    def _absender_bekannt(self) -> bool:
        return self.s is not None and self.s.profil is not None and not self.s.absender.fehlt()

    def _weiter(self) -> None:
        if self.schritt == S_BEREICHE and self._absender_bekannt():
            self.schritt_setzen(S_DATEN)  # Absender ist bekannt: gleich zu den Rechnungsdaten
        else:
            self.schritt_setzen(self.schritt + 1)

    # -- Schritt 1: Bereiche festlegen --------------------------------------------------------------
    def _seite_bereiche(self) -> QWidget:
        inhalt = QWidget()
        v = QVBoxLayout(inhalt)
        v.setContentsMargins(12, 12, 20, 12)
        v.setSpacing(6)
        v.addWidget(lbl(_("Bereiche festlegen"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Bereich anklicken, dann in der PDF einen Rahmen darum ziehen. Diese Angaben werden "
                    "danach nur noch innerhalb deiner Rahmen gelesen. Freiwillig – „Weiter“ geht immer."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addWidget(
            lbl(
                _(
                    "„Vorschlag übernehmen“ setzt den Rahmen der automatischen Erkennung; ist er zu klein, "
                    "zieh ihn einfach größer neu."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self.zonen_ui: dict[str, dict] = {}
        for name in anlernen.ZONEN:
            kt, kv = karte()
            kopf = QHBoxLayout()
            voll = _(anlernen.pdferkennung.BEREICH_NAMEN[name])
            kurz, _k, zusatz = voll.partition(
                " ("
            )  # Klammerzusatz unter den Knopf: Knopf bleibt schmal
            b = knopf(
                kurz,
                klick=lambda _c=False, n=name: self._zone_ziel(n),
                tip=voll + " – " + _("Rahmen in der PDF ziehen"),
            )
            b.setIcon(rahmen_symbol(self.c["sub"]))
            b.setObjectName(f"zone_{name}")
            st = lbl("")
            st.setMinimumWidth(32)
            kopf.addWidget(b, 1)
            kopf.addWidget(st)
            kv.addLayout(kopf)
            if zusatz:
                kv.addWidget(lbl("(" + zusatz, "hinweis", umbruch=True))
            vorschlag = knopf(
                _("Vorschlag übernehmen"), klick=lambda _c=False, n=name: self._zone_vorschlag(n)
            )
            weg = knopf(_("Entfernen"), klick=lambda _c=False, n=name: self._zone_entfernen(n))
            kv.addWidget(_Umbruch(vorschlag, weg))
            gilt = Auswahl()
            gilt.setMinimumHeight(48)
            gilt.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            gilt.setMinimumContentsLength(8)
            for code, text in GILT_AUF.items():
                gilt.addItem(_(text), code)
            gilt.currentIndexChanged.connect(lambda _i, n=name: self._zone_gilt(n))
            l_gilt = lbl(_("Gilt auf:"))
            zeile = _Umbruch(l_gilt, gilt, stretch=[0, 1])
            if name == "tabelle":  # die Tabelle läuft ohnehin über alle Seiten
                l_gilt.setVisible(False)
                gilt.setVisible(False)
                zeile.setVisible(False)
            kv.addWidget(zeile)
            info = lbl("", "hinweis", umbruch=True)
            kv.addWidget(info)
            v.addWidget(kt)
            self.zonen_ui[name] = {
                "knopf": b,
                "status": st,
                "vorschlag": vorschlag,
                "weg": weg,
                "gilt": gilt,
                "info": info,
            }
        v.addStretch(1)
        self._zonen_anzeigen()
        return rollen(inhalt)

    def _zonen_anzeigen(self) -> None:
        s = self.s
        for name, ui in self.zonen_ui.items():
            da = name in s.zonen
            aktiv = self.ziel == ("zone", name)
            ui["status"].setText("✔" if da else "○")
            ui["status"].setStyleSheet(
                f"font-size:20px; font-weight:bold; color:{self.c['ok'] if da else self.c['sub']};"
            )
            ui["status"].setToolTip(
                _("Rahmen gesetzt") if da else _("Kein Rahmen – automatische Erkennung")
            )
            ui["knopf"].setProperty("primary", aktiv)
            ui["knopf"].setIcon(rahmen_symbol("#ffffff" if aktiv else self.c["sub"]))
            ui["knopf"].style().unpolish(ui["knopf"])
            ui["knopf"].style().polish(ui["knopf"])
            ui["weg"].setEnabled(da)
            ui["vorschlag"].setEnabled(s.zone_vorschlag(name) is not None)
            g = ui["gilt"]
            g.blockSignals(True)
            g.setCurrentIndex(max(0, g.findData(s.zonen.get(name, {}).get("seiten", "alle"))))
            g.blockSignals(False)
            g.setEnabled(da)
            if aktiv:
                ui["info"].setText(_("Wartet auf deinen Rahmen in der PDF."))
            elif da:
                seiten = s.zone_seiten(name)
                ui["info"].setText(
                    _("Seite {s}").format(s=", ".join(str(i + 1) for i in seiten))
                    if len(seiten) < 6
                    else _("alle {n} Seiten").format(n=len(seiten))
                )
            else:
                ui["info"].setText("")

    def _zone_ziel(self, name: str) -> None:
        self._ziel_setzen("zone", name)

    def _zone_name(self, name: str) -> str:
        return _(anlernen.pdferkennung.BEREICH_NAMEN[name]).split(" (")[0]

    def _zone_fertig(self, name: str, geaendert: list[str], titel: str) -> None:
        if name == "tabelle":
            detail = _("{n} Positionen gelesen.").format(n=len(self.s.positionen()))
        elif geaendert:
            detail = _("Neu gelesen: {felder}.").format(
                felder=", ".join(_feldname(f).split(" (")[0] for f in geaendert)
            )
        else:
            detail = _("Werte unverändert.")
        if self.s.vorlage is not None and name in self.s.zonen_geaendert():
            detail += " " + _(
                "Zählt beim Speichern als Korrektur: Bereich „{name}“ geändert, der Zähler beginnt "
                "wieder bei 0."
            ).format(name=self._zone_name(name))
        log.info("Anlernen %s: %s – %s", self.s.pfad.name, titel, detail)
        self.toast("ok", titel, detail)
        self._zonen_anzeigen()
        self._markieren()
        self._fuss()

    def _zone_vorschlag(self, name: str) -> None:
        vs = self.s.zone_vorschlag(name)
        if vs is None:
            self.toast(
                "info",
                _("Kein Vorschlag"),
                _(
                    "Die automatische Erkennung hat hier nichts gefunden. Bitte "
                    "einen Rahmen ziehen."
                ),
            )
            return
        self._ziel_setzen(None)
        seite, rahmen = vs
        geaendert = self.s.zone_setzen(name, seite, rahmen, neu_lesen=name != "tabelle")
        self.pdf.zeige_seite(seite)
        self._zone_fertig(
            name, geaendert, _("Vorschlag übernommen: {name}").format(name=self._zone_name(name))
        )

    def _zone_entfernen(self, name: str) -> None:
        self._ziel_setzen(None)
        geaendert = self.s.zone_entfernen(name)
        self._zone_fertig(
            name, geaendert, _("Bereich entfernt: {name}").format(name=self._zone_name(name))
        )

    def _zone_gilt(self, name: str) -> None:
        code = self.zonen_ui[name]["gilt"].currentData()
        if name not in self.s.zonen or self.s.zonen[name].get("seiten") == code:
            return
        geaendert = self.s.zone_seiten_setzen(name, code)
        self._zone_fertig(
            name,
            geaendert,
            _("{name}: gilt auf {wo}").format(name=self._zone_name(name), wo=_(GILT_AUF[code])),
        )

    def toast(self, art, titel, detail="", aktion=None, bei_aktion=None):
        return self.toasts.zeigen(self.c, art, titel, detail, aktion, bei_aktion)

    # -- Schritt 2: Absender ------------------------------------------------------------------------
    def _seite_absender(self) -> QWidget:
        inhalt = QWidget()
        v = QVBoxLayout(inhalt)
        v.setContentsMargins(12, 12, 20, 12)
        v.setSpacing(6)
        v.addWidget(lbl(_("Wer stellt die Rechnung aus?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Diese Angaben stehen meist schon auf der PDF. Bitte kurz prüfen – sie werden nur einmal "
                    "gespeichert."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        # bekannter Absender, neues Layout: Profil wählen statt alles neu einzugeben
        h = QHBoxLayout()
        h.addWidget(lbl(_("Bekannter Absender:"), "hinweis", umbruch=True), 1)
        self.cb_profil = Auswahl()
        self.cb_profil.setMinimumHeight(48)
        self.cb_profil.setAccessibleName(_("Bekannter Absender"))
        self.cb_profil.addItem(_("Neuer Absender (aus der PDF)"), None)
        for i, prof in enumerate(self.k.pdf_profile):
            self.cb_profil.addItem(
                str(prof.get("name") or prof.get("profil") or Path(prof["_datei"]).stem), i
            )
        if self.s.profil is not None and self.s.profil in self.k.pdf_profile:
            self.cb_profil.setCurrentIndex(self.k.pdf_profile.index(self.s.profil) + 1)
        self.cb_profil.setEnabled(bool(self.k.pdf_profile))
        self.cb_profil.setToolTip(
            _("Neues Rechnungslayout eines Absenders, den die App schon kennt?")
            if self.k.pdf_profile
            else _("Noch kein Absender gespeichert.")
        )
        self.cb_profil.activated.connect(self._profil_gewaehlt)
        h.addWidget(self.cb_profil, 2)
        v.addLayout(h)
        h = QHBoxLayout()
        h.addWidget(lbl(_("Oder aus einer Datei übernehmen:"), "hinweis", umbruch=True), 1)
        h.addWidget(knopf(_("Aus Datei importieren…"), klick=self._absender_import))
        v.addLayout(h)
        v.addWidget(trenner())
        self.abs_zeilen: dict[str, Feldzeile] = {}
        for schl, (name, _p) in ABSENDER.items():
            self.abs_zeilen[schl] = Feldzeile(
                self.c,
                _(name),
                lambda _c=False, s_=schl: self._ziel_setzen("abs", s_),
                lambda t, s_=schl: self._abs_text(s_, t),
            )
        z = self.abs_zeilen
        v.addWidget(z["name"])
        v.addWidget(z["strasse"])
        for schl in ("zusatz", "plz", "ort", "ust_id", "steuernummer"):
            v.addWidget(z[schl])
        v.addWidget(
            lbl(_("USt-IdNr. oder Steuernummer – eins von beiden reicht."), "hinweis", umbruch=True)
        )
        for schl in ("iban", "bic", "register", "telefon", "email"):
            v.addWidget(z[schl])
        v.addStretch(1)
        self._abs_anzeigen()
        return rollen(inhalt)

    def _profil_gewaehlt(self, idx: int) -> None:
        i = self.cb_profil.itemData(idx)
        prof = self.k.pdf_profile[i] if i is not None else None
        self.s.profil_waehlen(prof)
        for f in getattr(self, "zeilen", {}):
            self._feld_anzeigen(f)
        self._abs_anzeigen()
        self._markieren()
        self._fuss()
        if prof is not None:
            self.toast("ok", _("Absender übernommen"), self.cb_profil.currentText())

    def _abs_anzeigen(self) -> None:
        a = self.s.absender
        fehlt = set(a.fehlt())
        for schl, zeile in self.abs_zeilen.items():
            wert = getattr(a, schl)
            if wert:
                zust = "erkannt"
            elif schl in fehlt or (schl == "steuernummer" and "ust_id" in fehlt):
                zust = "fehlt"
            else:
                zust = "aus"
            hilfe = ""
            if schl == "iban" and wert and "iban" in self._abs_ungueltig():
                zust, hilfe = "pruefen", _("Die IBAN ist ungültig (Prüfziffer).")
            zeile.setzen(wert, zust, hilfe)

    def _abs_ungueltig(self) -> set[str]:
        from ..pflichtpruefung import iban_gueltig

        a = self.s.absender
        return {"iban"} if a.iban and not iban_gueltig(a.iban.replace(" ", "")) else set()

    def _abs_text(self, schl: str, text: str) -> None:
        text = " ".join(text.split())
        if schl in ("iban", "bic", "ust_id"):
            text = text.upper()
        if getattr(self.s.absender, schl) != text:
            setattr(self.s.absender, schl, text)
            if schl in ("name", "strasse", "plz", "ort"):
                self._kaeufer_aktualisieren()
        self._abs_anzeigen()
        self._fuss()

    def _kaeufer_aktualisieren(self) -> None:
        """Absender geändert: Käufer-Vorschlag (Anschriftfeld) neu ermitteln; Bestätigtes bleibt."""
        neu = self.s.kaeufer_neu_vorschlagen()
        for f in neu:
            if f in getattr(self, "zeilen", {}):
                self._feld_anzeigen(f)
        if neu:
            log.info("Anlernen: Käufer-Vorschlag neu ermittelt (%s)", ", ".join(neu))

    def _absender_import(self) -> None:
        datei, _f = QFileDialog.getOpenFileName(
            self, _("Absender importieren"), str(Path.home()), _("CSV-Dateien (*.csv *.txt)")
        )
        if datei:
            self.absender_importieren(Path(datei))

    def absender_importieren(self, datei: Path) -> bool:
        try:
            a = aus_csv(datei.read_bytes())
        except (OSError, ValueError) as e:
            log.warning("Absender-Import %s: %s", datei, e)
            self.toast(
                "fehler",
                _("Datei nicht lesbar"),
                _("Erwartet: CSV mit Kopfzeile Name;Strasse;PLZ;Ort;…"),
            )
            return False
        self.s.absender = a
        self._kaeufer_aktualisieren()
        self._abs_anzeigen()
        self._fuss()
        self.toast("ok", _("Absender übernommen"), a.name)
        return True

    # -- Schritt 3: Rechnungsdaten ------------------------------------------------------------------
    def _seite_daten(self) -> QWidget:
        rs = QWidget()
        rv = QVBoxLayout(rs)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        oben = QWidget()
        v = QVBoxLayout(oben)
        v.setContentsMargins(12, 12, 20, 8)
        v.setSpacing(6)
        kopf = QHBoxLayout()
        kopf.addWidget(lbl(_("Pflichtangaben"), "titel"), 1)
        self.l_fort = lbl("")
        self.l_fort.setStyleSheet("font-weight:bold;")
        kopf.addWidget(self.l_fort)
        v.addLayout(kopf)
        self.balken = Balken(self.c)
        v.addWidget(self.balken)
        v.addLayout(_legende(self.c))
        v.addWidget(
            lbl(
                _(
                    "Feld anklicken, dann den Wert in der PDF anklicken. Oder einfach eintippen – "
                    "die App sucht ihn dann selbst."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addWidget(trenner())
        rv.addWidget(oben)
        inhalt = QWidget()
        v = QVBoxLayout(inhalt)
        v.setContentsMargins(12, 4, 20, 12)
        v.setSpacing(6)
        self.zeilen: dict[str, Feldzeile] = {}
        for feld, (name, _t, pflicht) in anlernen.FELDER.items():
            self.zeilen[feld] = Feldzeile(
                self.c,
                _(name),
                lambda _c=False, f=feld: self._ziel_setzen("feld", f),
                lambda t, f=feld: self._feld_text(f, t),
                lambda f=feld: self._passt(f),
                lambda f=feld: self._ziel_setzen("bereich", f),
            )
            self.zeilen[feld].e.installEventFilter(self)
        z = self.zeilen
        # eine Angabe je Zeile: bleibt auch bei 250 % Skalierung lesbar
        for titel, felder in (
            (None, ("BT-1", "BT-2", "leistung")),
            (_("Käufer"), ("BT-44", "BT-51", "BT-163", "BT-56", "BT-50", "BT-53", "BT-52")),
            (_("Beträge"), ("BT-109", "BT-119", "BT-110", "BT-112")),
            (_("Gutschrift"), ("BT-3", "BT-25")),
            (_("Weitere Angaben (freiwillig)"), ("BT-20", "BT-13", "kundennummer")),
            (_("Steuerhinweis & Kennungen (freiwillig)"), anlernen.STEUERFELDER),
        ):
            if titel:
                v.addSpacing(6)
                v.addWidget(lbl(titel, "sektion"))
            if felder[0] == "BT-44":
                h = QHBoxLayout()
                h.addWidget(
                    lbl(
                        _(
                            "Ganze Anschrift auf einmal: Rahmen ziehen oder Zeilen mit Strg+Klick wählen."
                        ),
                        "hinweis",
                        umbruch=True,
                    ),
                    1,
                )
                self.b_anschrift = knopf(
                    _("Anschrift als Block"), klick=lambda: self._ziel_setzen("block", "kaeufer")
                )
                self.b_anschrift.setIcon(rahmen_symbol(self.c["sub"]))
                self.b_anschrift.setToolTip(
                    _("Name, Adresszusatz, Straße, PLZ und Ort aus einem Rahmen übernehmen")
                )
                h.addWidget(self.b_anschrift)
                v.addLayout(h)
            for f in felder:
                v.addWidget(z[f])
        v.addStretch(1)
        self.daten_scroll = rollen(inhalt)
        rv.addWidget(self.daten_scroll, 1)
        for f in self.zeilen:
            self._feld_anzeigen(f)
        return rs

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "vorschau", None) and ev.type() == QEvent.Type.Resize:
            if self._vorschau_breiten and not self._vorschau_nutzer:
                QTimer.singleShot(0, self._vorschau_einpassen)
            return False
        if (
            ev.type() == QEvent.Type.MouseButtonPress
            and hasattr(self, "vorschau")
            and obj is self.vorschau.horizontalHeader().viewport()
        ):
            self._vorschau_nutzer = True
            return False
        if ev.type() == QEvent.Type.FocusIn and self.schritt == S_DATEN:
            for f, z in self.zeilen.items():
                if z.e is obj and (self.ziel != ("feld", f)):
                    self._ziel_setzen("feld", f, fokus=False)
        return False

    def _feld_anzeigen(self, f: str, *, _kette: bool = False) -> None:
        vs = self.s.werte[f]
        pflicht = anlernen.FELDER[f][2] and not (f == "BT-119" and self.s.steuerfall_wirksam() != "S")
        zust = vs.status if vs.status != "fehlt" or pflicht else "aus"
        zusatz = ""
        if f == "BT-20":
            zusatz = self.s.zahlung_hinweis()
            if zust == "aus" and zusatz:
                zust = "fehlt"  # empfohlen: die Rechnung nennt eine Zahlungsbedingung
        elif f == "BT-3":
            zusatz = self.s.belegart_hinweis()
        elif f == "BT-25":
            if self.s.belegart() == "381" and not vs.wert:
                zusatz = anlernen.BEZUG_FEHLT
                if zust == "aus":
                    zust = "fehlt"
        if self.ziel in (("feld", f), ("bereich", f)):
            zust = "warten"
        hilfe = _(vs.hinweis) if vs.hinweis else ""
        if zusatz:
            ztxt = _(zusatz)
            if ztxt and ztxt not in hilfe:
                hilfe = f"{hilfe} {ztxt}".strip() if hilfe else ztxt
        if not hilfe and zust == "warten":
            hilfe = (
                _("Wartet auf deinen Rahmen in der PDF.")
                if self.ziel[0] == "bereich"
                else _("Wartet auf deinen Klick in der PDF.")
            )
        self.zeilen[f].setzen(vs.wert, zust, hilfe, passt=vs.status == "pruefen" and bool(vs.wert))
        if (
            not _kette
            and f in ("BT-3", "BT-25")
            and "BT-3" in self.zeilen
            and "BT-25" in self.zeilen
        ):
            self._feld_anzeigen("BT-25" if f == "BT-3" else "BT-3", _kette=True)

    def _feld_text(self, f: str, text: str) -> None:
        vs = self.s.werte[f]
        if " ".join(text.split()) == vs.wert and vs.status != "fehlt":
            return
        vs = self.s.setzen(f, text, None)
        if text and not vs.woerter:
            vs.woerter = self.s.fundstelle(text, f)
        self._feld_anzeigen(f)
        self._markieren()
        self._fuss()

    def _passt(self, f: str) -> None:
        self.s.bestaetigen(f)
        self._feld_anzeigen(f)
        self._markieren()
        self._fuss()

    # -- Klicks in die PDF --------------------------------------------------------------------------
    def _ziel_setzen(self, art: str | None, schl: str | None = None, fokus: bool = True) -> None:
        alt = self.ziel
        self.ziel = (art, schl) if art else None
        if alt and alt[0] in ("feld", "bereich"):
            self.zeilen[alt[1]].aktiv(False)
            self._feld_anzeigen(alt[1])
        elif alt and alt[0] == "abs":
            self.abs_zeilen[alt[1]].aktiv(False)
        elif alt and alt[0] == "zone":
            self._zonen_anzeigen()
        elif alt and alt[0] == "block":
            self._block_ws = []
            self.b_anschrift.setProperty("primary", False)
            self.b_anschrift.setIcon(rahmen_symbol(self.c["sub"]))
            self.b_anschrift.style().unpolish(self.b_anschrift)
            self.b_anschrift.style().polish(self.b_anschrift)
            self._markieren()
        if self.ziel and art == "block":
            self._block_ws = []
            self.b_anschrift.setProperty("primary", True)
            self.b_anschrift.setIcon(rahmen_symbol("#ffffff"))
            self.b_anschrift.style().unpolish(self.b_anschrift)
            self.b_anschrift.style().polish(self.b_anschrift)
            self.pdf.banner_zeigen(
                _(
                    "Ziehe einen Rahmen um die <b>ganze Käuferanschrift</b> – oder wähle die Zeilen "
                    "mit Strg+Klick und dann „Übernehmen“."
                ),
                lambda: self._ziel_setzen(None),
                self._block_uebernehmen,
            )
            self.pdf.seite.modus_setzen("block")
        elif self.ziel and art == "zone":
            self._zonen_anzeigen()
            self.pdf.banner_zeigen(
                _("Ziehe in der PDF einen Rahmen um: <b>{was}</b>").format(
                    was=_(anlernen.pdferkennung.BEREICH_NAMEN[schl])
                ),
                lambda: self._ziel_setzen(None),
            )
            self.pdf.seite.modus_setzen("rahmen")
            self._markieren()
        elif self.ziel:
            feld = art in ("feld", "bereich")
            zeile = self.zeilen[schl] if feld else self.abs_zeilen[schl]
            zeile.aktiv(True, bereich=art == "bereich") if feld else zeile.aktiv(True)
            if feld:
                self._feld_anzeigen(schl)
            name = _feldname(schl) if feld else _(ABSENDER[schl][0])
            if art == "bereich":
                self.pdf.banner_zeigen(
                    _("Ziehe in der PDF einen Rahmen um: <b>{was}</b>").format(was=name),
                    lambda: self._ziel_setzen(None),
                )
                self.pdf.seite.modus_setzen("rahmen")
            else:
                self.pdf.banner_zeigen(
                    _("Klicke in der PDF auf: <b>{was}</b>").format(was=name),
                    lambda: self._ziel_setzen(None),
                )
                self.pdf.seite.modus_setzen("wort")
        else:
            self.pdf.banner_zeigen(None)
            self.pdf.seite.modus_setzen(
                self._modus_positionen() if self.schritt == S_POSITIONEN else ""
            )
            if alt and alt[0] == "zone":
                self._markieren()

    def _wort_geklickt(self, text: str, woerter: list) -> None:
        if not self.ziel:
            return
        art, schl = self.ziel
        if art == "abs":
            self._abs_text(schl, text)
            self._ziel_setzen(None)
            return
        if art == "block":  # Zeile zur Anschrift dazu – oder wieder weg
            ids = {id(w) for w in woerter}
            vorher = len(self._block_ws)
            self._block_ws = [ws for ws in self._block_ws if not ids & {id(w) for w in ws}]
            if len(self._block_ws) == vorher:
                self._block_ws.append(list(woerter))
            self.pdf.b_banner_ok.setEnabled(bool(self._block_ws))
            self._markieren()
            return
        self.s.setzen(schl, text, woerter)
        self._ziel_setzen(None)
        self._feld_anzeigen(schl)
        # nächstes offenes Pflichtfeld gleich bereitstellen (spart Klicks)
        offen = self.s.fehlende()
        if offen and self.s.werte[offen[0]].status == "fehlt":
            self._ziel_setzen("feld", offen[0])
        self._markieren()
        self._fuss()

    def _block_uebernehmen(self) -> None:
        ws = [w for z in self._block_ws for w in z]
        if ws:
            self._anschrift_fertig(self.s.anschrift_setzen(ws[0].seite, woerter=ws))

    def _anschrift_fertig(self, teile: dict) -> None:
        self._ziel_setzen(None)
        for f in (*anlernen.KAEUFER_FELDER_ANLERNEN, *anlernen.KAEUFER_NEBENFELDER):
            self._feld_anzeigen(f)
        self._markieren()
        self._fuss()
        if teile:
            self.toast(
                "ok",
                _("Anschrift übernommen"),
                ", ".join(
                    teile[f]
                    for f in ("BT-44", "BT-51", "BT-163", "BT-56", "BT-50", "BT-53", "BT-52")
                    if f in teile
                ),
            )
        else:
            self.toast("fehler", _("Im Rahmen steht kein Text."), "")

    def _rahmen_gezogen(self, x0: float, top: float, x1: float, bottom: float) -> None:
        if self.ziel and self.ziel[0] == "zone":
            name = self.ziel[1]
            self._ziel_setzen(None)
            geaendert = self.s.zone_setzen(name, self.pdf.seite.seite, (x0, top, x1, bottom))
            self._zone_fertig(
                name, geaendert, _("Bereich gesetzt: {name}").format(name=self._zone_name(name))
            )
            return
        if self.ziel and self.ziel[0] == "block":
            self._anschrift_fertig(
                self.s.anschrift_setzen(self.pdf.seite.seite, (x0, top, x1, bottom))
            )
            return
        if self.ziel and self.ziel[0] == "bereich":
            f = self.ziel[1]
            vs = self.s.bereich_setzen(f, self.pdf.seite.seite, x0, top, x1, bottom)
            self._ziel_setzen(None)
            self._feld_anzeigen(f)
            self._markieren()
            self._fuss()
            if vs.bereich:
                self.toast("ok", _("Bereich übernommen"), vs.wert)
            return
        if self.pdf.seite.modus == "spalte":
            i = self.s.spalte_hinzufuegen(self.pdf.seite.seite, x0, top, x1, bottom)
            self._tabelle_anzeigen()
            code = self.s.tabelle.spaltenrahmen[i][0]
            name = _(anlernen.SPALTEN.get(code, code)).split(" (")[0]
            n = dict(self.s.spalten_zustand()).get(code, 0)
            self.toast(
                "ok",
                _("Spalte „{name}“ hinzugefügt").format(name=name),
                _("{n} Werte erkannt. Bedeutung rechts in der Liste ändern.").format(n=n),
            )
            return
        self.s.rahmen_setzen(self.pdf.seite.seite, x0, top, x1, bottom)
        self._tabelle_anzeigen()
        n = len(self.s.positionen())
        if n:
            self.toast(
                "ok",
                _("Tabelle erkannt"),
                _("{n} Positionen, {s} Spalten").format(n=n, s=len(self.s.tabelle.codes())),
            )
        if self.s.tabelle.spaltenrahmen:
            self._modus_waehlen("spalte")

    def _grenze_gezogen(self, i: int, x: float) -> None:
        self.s.grenze_setzen(i, x)
        self._tabelle_anzeigen()

    # Spalten als eigene Rahmen
    def _modus_positionen(self) -> str:
        return getattr(self, "_pos_modus", "rahmen")

    def _modus_waehlen(self, m: str) -> None:
        self._pos_modus = m
        if self.schritt == S_POSITIONEN:
            self.pdf.seite.modus_setzen(m)
        self._modus_anzeigen()

    def _modus_anzeigen(self) -> None:
        if not hasattr(self, "l_modus"):
            return
        m = self._modus_positionen()
        self.l_modus.setText(
            _("Jetzt: Rahmen um eine Spalte ziehen (Kopfzeile bis letzte Position).")
            if m == "spalte"
            else _("Jetzt: Rahmen um die ganze Tabelle ziehen.")
        )
        self.b_spalte_neu.setProperty("primary", m != "spalte")
        self.b_tabelle_neu.setProperty("primary", False)
        for b in (self.b_spalte_neu, self.b_tabelle_neu):
            b.style().unpolish(b)
            b.style().polish(b)

    def _spalte_neu(self) -> None:
        if self.s.tabelle.spaltenrahmen or not self.s.tabelle.leer():
            self.s.spalten_aus_linien()  # bisherige Zuordnung bleibt als Rahmen erhalten
        self._modus_waehlen("spalte")
        self._tabelle_anzeigen()
        self.toast(
            "info",
            _("Spalte hinzufügen"),
            _(
                "Zieh in der PDF einen Rahmen über eine Spalte – von der Überschrift bis zur letzten Position."
            ),
        )

    def _tabelle_neu(self) -> None:
        self._modus_waehlen("rahmen")
        self.toast(
            "info",
            _("Tabellenrahmen neu ziehen"),
            _("Zieh in der PDF einen Rahmen um die ganze Tabelle. Gezogene Spalten darin bleiben."),
        )

    def _spalte_geaendert(self, i: int, x0: float, x1: float) -> None:
        self.s.spalte_verschieben(i, x0, x1)
        self._tabelle_anzeigen()

    def _spaltenrahmen_bedeutung(self, i: int, code: str) -> None:
        self.s.spalte_bedeutung(i, code)
        self._tabelle_anzeigen()

    def _spaltenrahmen_entfernen(self, i: int) -> None:
        rs = self.s.tabelle.spaltenrahmen
        if 0 <= i < len(rs):
            name = _(anlernen.SPALTEN.get(rs[i][0], rs[i][0])).split(" (")[0]
            self.s.spalte_entfernen(i)
            self._tabelle_anzeigen()
            self.toast("ok", _("Spalte „{name}“ entfernt").format(name=name), "")

    def _diagnose_kopieren(self) -> None:
        text = self.s.tabellen_diagnose() + "\n\n" + self.s.bereiche_diagnose()
        QApplication.clipboard().setText(text)
        log.info("Diagnose (ohne Rechnungstext) in die Zwischenablage kopiert:\n%s", text)
        self.toast(
            "ok",
            _("Diagnose kopiert"),
            _(
                "Enthält nur Lage und Form der Wörter (z. B. „Aaaa 99,99“), keinen Rechnungstext. "
                "Füge sie in deine Nachricht an den Support ein."
            ),
        )

    def _markieren(self) -> None:
        marken = []
        zonen = []
        if self.schritt == S_BEREICHE:
            for name, b in self.s.zonen.items():
                zonen.append(
                    (
                        self._zone_name(name),
                        tuple(b["rahmen"]),
                        self.ziel == ("zone", name),
                        self.s.zone_seiten(name),
                    )
                )
        elif self.schritt == S_ABSENDER:
            for schl in ("name", "strasse", "ust_id", "steuernummer", "iban", "register"):
                wert = getattr(self.s.absender, schl)
                if wert:
                    ws = self.s.fundstelle(wert)
                    if ws:
                        marken.append((ws, "erkannt", _(ABSENDER[schl][0]).split(" (")[0]))
        elif self.schritt == S_DATEN:
            for f, vs in self.s.werte.items():
                if vs.woerter and vs.status != "fehlt":
                    et = _feldname(f).split(" (")[0].replace(_("Käufer: "), "")
                    marken.append((vs.woerter, vs.status, et))
            for ws in getattr(self, "_block_ws", []):
                marken.append((ws, "warten", ""))
        self.pdf.seite.marken = marken
        self.pdf.seite.zonen = zonen
        self.pdf.seite.rahmen_zeigen = self.schritt == S_POSITIONEN
        self.pdf.seite.update()

    # -- Schritt 4: Positionen ----------------------------------------------------------------------
    def _seite_positionen(self) -> QWidget:
        inhalt = QWidget()
        v = QVBoxLayout(inhalt)
        v.setContentsMargins(12, 12, 20, 12)
        v.setSpacing(8)
        v.addWidget(lbl(_("Positionen"), "titel"))
        self.l_kontrolle_pos = lbl("", "warn", umbruch=True)
        self.l_kontrolle_pos.setObjectName("kontrolle_positionen")
        self.l_kontrolle_pos.setVisible(False)
        v.addWidget(self.l_kontrolle_pos)
        self._kontrolle_positionen_anzeigen()
        v.addWidget(
            lbl(
                _(
                    "Zieh in der PDF einen Rahmen um die Tabelle (mit Kopfzeile). Dann sag pro Spalte, "
                    "was drinsteht."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addWidget(
            lbl(
                _(
                    "Sitzt eine Spaltenlinie falsch, zieh sie in der PDF mit der Maus an die richtige Stelle."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addWidget(
            lbl(
                _(
                    "Klappt das nicht, zieh die Spalten einzeln: „Spalte hinzufügen“, dann einen Rahmen über "
                    "die Spalte ziehen und die Bedeutung wählen."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self.b_spalte_neu = knopf(
            _("Spalte hinzufügen"),
            primary=True,
            klick=self._spalte_neu,
            tip=_("Einen Rahmen über eine einzelne Spalte ziehen"),
        )
        self.b_tabelle_neu = knopf(
            _("Tabellenrahmen neu ziehen"),
            klick=self._tabelle_neu,
            tip=_("Den Rahmen um die ganze Tabelle neu ziehen"),
        )
        v.addWidget(_nebeneinander(self.b_spalte_neu, self.b_tabelle_neu))
        self.l_modus = lbl("", "hinweis", umbruch=True)
        self.l_modus.setStyleSheet("font-weight:bold;")
        v.addWidget(self.l_modus)
        k, kv = karte()
        kv.addWidget(lbl(_("Spalten zuordnen"), "sektion"))
        self.spalten_gitter = QGridLayout()
        self.spalten_gitter.setHorizontalSpacing(12)
        self.spalten_gitter.setVerticalSpacing(6)
        kv.addLayout(self.spalten_gitter)
        self.l_spalten_leer = lbl(
            _("Noch kein Rahmen. Zieh mit der Maus einen Rahmen um die Tabelle."),
            "hinweis",
            umbruch=True,
        )
        kv.addWidget(self.l_spalten_leer)
        kv.addWidget(lbl(_("Preis gilt für"), "hinweis"))
        self.pe = Auswahl()
        for code, name in PREISEINHEIT:
            self.pe.addItem(_(name), code)
        self.pe.activated.connect(self._pe_gewaehlt)
        kv.addWidget(self.pe)
        self.einh_box = QVBoxLayout()
        self.einh_box.setSpacing(6)
        kv.addLayout(self.einh_box)
        # ab 0.9.7: Steuerfall der Vorlage und Bedeutung der Werte in der Steuerspalte
        kv.addWidget(lbl(_("Steuerfall"), "hinweis"))
        self.steuerfall = Auswahl()
        self.steuerfall.setObjectName("steuerfall")
        for code, name in STEUERFALL_WAHL:
            self.steuerfall.addItem(_(name), code)
        self.steuerfall.activated.connect(self._steuerfall_gewaehlt)
        kv.addWidget(self.steuerfall)
        self.l_steuerfall = lbl("", "hinweis", umbruch=True)
        kv.addWidget(self.l_steuerfall)
        self.steuer_box = QVBoxLayout()
        self.steuer_box.setSpacing(6)
        kv.addLayout(self.steuer_box)
        v.addWidget(k)

        k2, kv2 = karte()
        kv2.addWidget(lbl(_("Vorschau: so liest die App die Tabelle"), "sektion"))
        self.vorschau = QTableWidget(0, 5)
        self.vorschau.setHorizontalHeaderLabels(
            [_("Bezeichnung"), _("Menge"), _("Einheit"), _("Einzelpreis"), _("Gesamt")]
        )
        self.vorschau.verticalHeader().setVisible(False)
        self.vorschau.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        c = self.c
        self.vorschau.setStyleSheet(
            f"QTableWidget {{ background:{c['base']}; border:1px solid {c['card_b']}; gridline-color:{c['card_b']}; }}"
            f"QHeaderView::section {{ background:{c['bar']}; border:none; border-bottom:1px solid {c['card_b']};"
            f" padding:6px; font-weight:bold; font-size:13px; }}"
        )
        hh = self.vorschau.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  # Breiten mit der Maus änderbar
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(48)
        self._vorschau_breiten = False
        self._vorschau_nutzer = False  # hat der Nutzer schon selbst Spaltenbreiten gezogen?
        self.vorschau.installEventFilter(self)
        hh.viewport().installEventFilter(self)
        self.vorschau.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        kv2.addWidget(self.vorschau)
        self.summe = QFrame()
        self.summe.setObjectName("summe")
        sh = QHBoxLayout(self.summe)
        sh.setContentsMargins(12, 10, 12, 10)
        self.summe_sym = Zustand(c, "erkannt", 22)
        sh.addWidget(self.summe_sym)
        self.l_summe = lbl("", umbruch=True)
        self.l_summe.setStyleSheet("font-weight:bold;")
        sh.addWidget(self.l_summe, 1)
        kv2.addWidget(self.summe)
        self.l_tab_hinweis = lbl("", "hinweis", umbruch=True)
        kv2.addWidget(self.l_tab_hinweis)
        self.b_diagnose = knopf(
            _("Diagnose kopieren"),
            klick=self._diagnose_kopieren,
            enabled=False,
            tip=_("Lage und Form der Wörter ohne Rechnungstext in die Zwischenablage kopieren"),
        )
        kv2.addWidget(self.b_diagnose)
        v.addWidget(k2)
        v.addStretch(1)
        self._spalten_combos: list[QComboBox] = []
        self._tabelle_anzeigen()
        return rollen(inhalt)

    def _tabelle_anzeigen(self) -> None:
        s, t = self.s, self.s.tabelle
        while self.spalten_gitter.count():
            it = self.spalten_gitter.takeAt(0)
            if it.widget():
                it.widget().hide()  # bis zum Löschen nicht über der Karte liegen lassen
                it.widget().deleteLater()
            elif it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.hide()
                        w.deleteLater()
        self._spalten_combos = []
        self._spalten_zeilen: list[tuple] = []
        titel = s.spalten_titel()
        zustand = dict(s.spalten_zustand()) if t.spaltenrahmen else {}
        for i, (code, _a, _b) in enumerate(t.spaltenrahmen):
            h = QHBoxLayout()
            h.setSpacing(8)
            chip = QFrame()
            chip.setFixedSize(14, 44)
            chip.setStyleSheet(
                f"background:{SPALTEN_FARBE.get(code, '#757575')}; border-radius:3px;"
            )
            h.addWidget(chip)
            cb = Auswahl()
            for c_ in SPALTEN_RAHMEN + tuple(x for x in (code,) if x not in SPALTEN_RAHMEN):
                cb.addItem(_(anlernen.SPALTEN[c_]), c_)
            cb.setCurrentIndex(max(0, cb.findData(code)))
            cb.setAccessibleName(_("Bedeutung der Spalte {n}").format(n=i + 1))
            cb.activated.connect(
                lambda _i, n=i, box_=cb: self._spaltenrahmen_bedeutung(n, box_.currentData())
            )
            h.addWidget(cb, 1)
            n = zustand.get(code, 0)
            sym = Zustand(
                self.c, "aus" if code == "ignorieren" else "erkannt" if n else "pruefen", 22
            )
            h.addWidget(sym)
            st = lbl(
                "—" if code == "ignorieren" else _("{n} Werte").format(n=n) if n else _("leer"),
                "hinweis",
            )
            st.setMinimumWidth(64)
            h.addWidget(st)
            weg = knopf(
                _("Entfernen"),
                tip=_("Spalte {n} entfernen").format(n=i + 1),
                klick=lambda _c=False, n=i: self._spaltenrahmen_entfernen(n),
            )
            h.addWidget(weg)
            self.spalten_gitter.addLayout(h, i, 0, 1, 2)
            self._spalten_combos.append(cb)
            self._spalten_zeilen.append((cb, sym, st, weg))
        for i, sp in enumerate([] if t.spaltenrahmen else t.spalten):
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(
                lbl(
                    _("Spalte „{name}“").format(name=titel[i] if i < len(titel) else i + 1),
                    "hinweis",
                )
            )
            cb = Auswahl()
            for code, name in anlernen.SPALTEN.items():
                cb.addItem(_(name), code)
            cb.setCurrentIndex(max(0, cb.findData(sp)))
            cb.activated.connect(
                lambda _i, n=i, box_=cb: self._spalte_gewaehlt(n, box_.currentData())
            )
            box.addWidget(cb)
            self._spalten_combos.append(cb)
            z, sp_ = divmod(i, 2)
            self.spalten_gitter.addLayout(box, z, sp_)
        self.l_spalten_leer.setVisible(t.leer() or not t.codes())
        self.pe.setCurrentIndex(max(0, self.pe.findData(t.preiseinheit)))
        self.pe.model().item(3).setEnabled("BT-149" in t.codes())
        # Einheiten: unbekannte zuordnen lassen, bekannte nur nennen
        while self.einh_box.count():
            w = self.einh_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        pos = s.positionen()
        einh = s.einheiten_offen()
        offen = [e for e, code in einh.items() if not code]
        if not t.leer() and "BT-130" not in t.codes():
            self.einh_box.addWidget(lbl(_("Einheit für alle Positionen"), "hinweis"))
            self.einh_box.addWidget(self._einheit_combo("*", t.einheiten.get("*") or "H87"))
        for e in offen:
            self.einh_box.addWidget(
                lbl(
                    _("Positionen ohne Einheit sind:")
                    if e == anlernen.pdferkennung.OHNE_EINHEIT
                    else _("Unbekannte Einheit „{e}“ ist:").format(e=e),
                    "warn",
                )
            )
            self.einh_box.addWidget(self._einheit_combo(e, ""))
        self._steuer_anzeigen()
        # Vorschau
        abw = {a[0]: a for a in s.betrag_abweichungen()}
        self.vorschau.setRowCount(len(pos))
        for r, p in enumerate(pos):
            a = abw.get(p.nr or str(r + 1))
            einheit = p.einheit_text or anlernen.EINHEIT_NAMEN.get(
                t.einheiten.get("*") or "H87", ""
            )
            werte = (
                p.bezeichnung,
                anlernen._de(p.menge, 2).rstrip("0").rstrip(",") if p.menge is not None else "",
                einheit,
                anlernen._de(p.einzelpreis) if p.einzelpreis is not None else "",
                anlernen._de(p.gesamt) if p.gesamt is not None else "",
            )
            for c_, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c_ in (1, 3, 4):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if a and c_ == 4:
                    it.setForeground(QColor(self.c["err"]))
                    it.setToolTip(
                        _("Menge × Preis ÷ Preiseinheit {pe} = {b}").format(
                            pe=anlernen._de(a[3], 0), b=anlernen._de(a[4])
                        )
                    )
                self.vorschau.setItem(r, c_, it)
            self.vorschau.setRowHeight(r, 36)
        if (
            pos and not self._vorschau_breiten
        ):  # einmal an den Inhalt anpassen, danach bestimmt der Nutzer
            self.vorschau.resizeColumnsToContents()
            QTimer.singleShot(
                0, self._vorschau_einpassen
            )  # erst nach dem Layout ist die Breite bekannt
            self._vorschau_breiten = True
        # Höhe aus Kopfzeile, Rahmen und (bei schmalem Fenster) waagrechter Bildlaufleiste – nicht geschätzt,
        # sonst verdeckt die Leiste die letzten Zeilen
        self.vorschau.setFixedHeight(
            36 * min(len(pos), 12)
            + self.vorschau.horizontalHeader().sizeHint().height()
            + 2 * self.vorschau.frameWidth()
            + self.vorschau.horizontalScrollBar().sizeHint().height()
        )
        self.vorschau.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if len(pos) > 12
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        summe, netto, ok = s.summenpruefung()
        c = self.c
        if pos:
            self.summe.setVisible(True)
            farbe_bg, farbe, farbe_t = (
                (c["ok_bg"], c["ok"], c["ok_t"]) if ok else (c["er_bg"], c["err"], c["er_t"])
            )
            self.summe.setStyleSheet(
                f"QFrame#summe {{ background:{farbe_bg}; border:1px solid {farbe}; border-radius:6px; }}"
                f"QFrame#summe QLabel {{ color:{farbe_t}; }}"
            )
            self.summe_sym.setzen("erkannt" if ok else "pruefen")
            if ok:
                self.l_summe.setText(
                    _("Summe Positionen {s} = Netto {n}").format(
                        s=anlernen._de(summe), n=anlernen._de(netto)
                    )
                )
            elif netto is None:
                self.l_summe.setText(
                    _("Summe Positionen {s} – Nettobetrag fehlt noch (Schritt 3)").format(
                        s=anlernen._de(summe)
                    )
                )
            else:
                self.l_summe.setText(
                    _("Summe Positionen {s} ≠ Netto {n} – Rahmen oder Spalten prüfen").format(
                        s=anlernen._de(summe), n=anlernen._de(netto)
                    )
                )
        else:
            self.summe.setVisible(False)
        bekannt = sorted(
            {
                f"{e} → {_(anlernen.EINHEIT_NAMEN.get(code, code))}"
                for e, code in einh.items()
                if code
            }
        )
        hinweis = [_(x) for x in s.tabelle_fehlt()]
        if bekannt:
            hinweis.append(_("Einheiten erkannt: {liste}.").format(liste=", ".join(bekannt)))
        self.l_tab_hinweis.setText("\n".join(hinweis))
        self.b_diagnose.setEnabled(not t.leer() or bool(self.s.zonen))
        if not t.leer() and not pos:
            self.l_tab_hinweis.setText(
                self.l_tab_hinweis.text()
                + "\n"
                + _(
                    "Tipp: „Diagnose kopieren“ erstellt eine Beschreibung ohne Rechnungstext für den Support."
                )
            )
        self._modus_anzeigen()
        self._markieren()
        self._fuss()

    def _einheit_combo(self, text: str, code: str) -> QComboBox:
        cb = Auswahl()
        if not code:
            cb.addItem(_("bitte wählen"), "")
        for c_, name in anlernen.EINHEIT_NAMEN.items():
            cb.addItem(_(name), c_)
        cb.setCurrentIndex(max(0, cb.findData(code)))
        cb.activated.connect(lambda _i: self._einheit_gewaehlt(text, cb.currentData()))
        return cb

    def _steuer_anzeigen(self) -> None:
        """Steuerfall (Vorschlag aus dem Hinweistext) und je Wert der Steuerspalte die Bedeutung."""
        s = self.s
        self.steuerfall.setCurrentIndex(max(0, self.steuerfall.findData(s.steuerfall)))
        vorschlag = s.steuerfall_vorschlag()
        name = _(dict(STEUERFALL_WAHL).get(vorschlag, ""))
        if s.steuerfall:
            self.l_steuerfall.setText("")
        elif vorschlag == "S":
            self.l_steuerfall.setText(_("Kein Steuerhinweis im Druck – Regelbesteuerung."))
        else:
            self.l_steuerfall.setText(_("Vorschlag aus dem Steuerhinweis: {f}").format(f=name))
        while self.steuer_box.count():
            w = self.steuer_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        for text, wahl in s.steuerwerte_offen().items():
            self.steuer_box.addWidget(
                lbl(_("Steuerwert „{t}“ ist:").format(t=text), "hinweis" if wahl else "warn")
            )
            self.steuer_box.addWidget(self._steuerwert_combo(text, wahl))

    def _steuerwert_combo(self, text: str, wahl: str) -> QComboBox:
        cb = Auswahl()
        cb.setObjectName("steuerwert")
        if not wahl:
            cb.addItem(_("bitte wählen"), "")
        for code, name in STEUERWERT_WAHL:
            cb.addItem(_(name), code)
        if wahl and cb.findData(wahl) < 0:  # z. B. „S:16“ aus einer Steuerzeile
            cb.addItem(wahl.replace("S:", "") + " %", wahl)
        cb.setCurrentIndex(max(0, cb.findData(wahl)))
        cb.activated.connect(lambda _i: self._steuerwert_gewaehlt(text, cb.currentData()))
        return cb

    def _steuerwert_gewaehlt(self, text: str, wahl: str) -> None:
        if wahl:
            self.s.tabelle.steuerwerte[text] = wahl
            self._tabelle_anzeigen()

    def _steuerfall_gewaehlt(self, _i: int = 0) -> None:
        self.s.steuerfall_setzen(self.steuerfall.currentData() or "")
        self._tabelle_anzeigen()
        if hasattr(self, "zeilen") and "BT-119" in self.zeilen:
            self._feld_anzeigen("BT-119")
        self._fuss()

    def _einheit_gewaehlt(self, text: str, code: str) -> None:
        if code:
            self.s.tabelle.einheiten[text] = code
            self._tabelle_anzeigen()

    def _spalte_gewaehlt(self, i: int, code: str) -> None:
        t = self.s.tabelle
        if 0 <= i < len(t.spalten):
            if (
                code != "ignorieren" and code in t.spalten
            ):  # jede Spalte nur einmal: alte Zuordnung tauschen
                t.spalten[t.spalten.index(code)] = (
                    t.spalten[i] if t.spalten[i] != code else "ignorieren"
                )
            t.spalten[i] = code
            if code == "BT-149":
                t.preiseinheit = "spalte"
            elif t.preiseinheit == "spalte" and "BT-149" not in t.spalten:
                t.preiseinheit = "1"
            self._tabelle_anzeigen()

    def _pe_gewaehlt(self, _i: int) -> None:
        self.s.tabelle.preiseinheit = self.pe.currentData()
        self._tabelle_anzeigen()

    # -- Ablauf -------------------------------------------------------------------------------------
    def _vorschau_einpassen(self) -> None:
        """Bezeichnung kürzen, damit alle Spalten ohne Bildlauf nebeneinander passen."""
        hh = self.vorschau.horizontalHeader()
        rest = sum(hh.sectionSize(i) for i in range(1, 5))
        platz = self.vorschau.viewport().width()
        if platz > 200 and hh.sectionSize(0) + rest > platz:
            hh.resizeSection(0, max(160, platz - rest))

    def _kontrolle_positionen_anzeigen(self) -> None:
        w = getattr(self, "l_kontrolle_pos", None)
        if w is None:
            return
        an = self.s is not None and "positionen" in (self.s.kontrolle_offen or [])
        w.setText(
            _(
                "Selbstkontrolle: Nach dem letzten Speichern hat die Vorlage die Positionen anders gelesen – bitte prüfen."
            )
            if an
            else ""
        )
        w.setVisible(an)

    def schritt_setzen(self, n: int) -> None:
        if self.s is None:
            return
        n = max(S_BEREICHE, min(S_POSITIONEN, n))
        self._ziel_setzen(None)
        self.schritt = n
        self.stapel.setCurrentIndex(n)
        self.stepper.setzen(n)
        self.b_zurueck.setEnabled(n > 0)
        self.b_weiter.setVisible(n < S_POSITIONEN)
        self.b_weiter.setText(
            _("Weiter ▶")
            if n == S_BEREICHE
            else _("Weiter: Rechnungsdaten")
            if n == S_ABSENDER
            else _("Weiter: Positionen")
        )
        if n == S_BEREICHE:
            self._zonen_anzeigen()
        if n == S_POSITIONEN:
            self._tabelle_anzeigen()
            self._kontrolle_positionen_anzeigen()
            t = self.s.tabelle
            if not t.leer():
                self.pdf.zeige_seite(t.seite)
            self._pos_modus = "spalte" if self.s.tabelle.spaltenrahmen else "rahmen"
        elif n == S_DATEN:
            for f in self.zeilen:  # Bereiche können Vorschläge geändert haben
                self._feld_anzeigen(f)
        self.pdf.seite.modus_setzen(self._modus_positionen() if n == S_POSITIONEN else "")
        self._modus_anzeigen()
        self._markieren()
        self._fuss()

    def _fuss(self) -> None:
        if self.s is None:
            return
        s = self.s
        a_fehlt = s.absender.fehlt() or self._abs_ungueltig()
        offen = s.fehlende()
        if hasattr(self, "l_fort"):
            n_p = len(anlernen.PFLICHT)
            self.l_fort.setText(_("{x} von {n} erledigt").format(x=n_p - len(offen), n=n_p))
            self.balken.setzen((n_p - len(offen)) / n_p)
        if self.schritt == S_BEREICHE:
            n_z = len(s.zonen)
            text = _("{n} von {m} Bereichen gesetzt").format(n=n_z, m=len(anlernen.ZONEN))
        elif self.schritt == S_ABSENDER:
            text = (
                _("Pflichtangaben vollständig")
                if not a_fehlt
                else _("Noch {n} Angaben offen").format(n=len(a_fehlt))
            )
        elif self.schritt == S_DATEN:
            text = (
                _("Noch {n} Felder offen").format(n=len(offen))
                if offen
                else _("Pflichtangaben vollständig")
            )
        else:
            tf = s.tabelle_fehlt()
            if a_fehlt:
                text = _("Absender unvollständig (Schritt 2)")
            elif offen:
                text = _("Noch {n} Felder offen (Schritt 3)").format(n=len(offen))
            elif tf:
                text = _(tf[0])
            elif not s.summenpruefung()[2]:
                text = _("Summe passt nicht zum Nettobetrag")
            else:
                text = _("Alles vollständig")
        self.l_fuss.setText(text)
        fertig = s.fertig() and not self._abs_ungueltig()
        letzte = self.i >= len(self.pdfs) - 1
        self.b_speichern.setText(
            _("Speichern && fertig") if letzte else _("Speichern && nächste PDF")
        )
        self.b_speichern.setEnabled(fertig)
        prim = self.schritt == S_POSITIONEN or fertig
        if self.b_speichern.property("primary") != prim:
            self.b_speichern.setProperty("primary", prim)
            self.b_speichern.style().unpolish(self.b_speichern)
            self.b_speichern.style().polish(self.b_speichern)

    def speichern(self) -> None:
        s = self.s
        if s is None or not s.fertig():
            return
        try:
            erg, v = s.speichern(self.konfig_pfad)
        except anlernen.dateien.DateiNichtSchreibbar as e:
            log.exception("Anlernen %s fehlgeschlagen: %s", s.pfad.name, e.details())
            self.toast("fehler", _("Konnte nicht speichern"), str(e) + " – " + _("Details im Log"))
            return
        except Exception as e:  # noqa: BLE001 – Details ins Log, kurz im Toast
            log.exception("Anlernen %s fehlgeschlagen", s.pfad.name)
            self.toast("fehler", _("Nicht gespeichert"), f"{type(e).__name__}: {e}"[:160])
            return
        if erg.status != "ok" or v is None:
            for hw in erg.hinweise:
                log.log(
                    logging.INFO if hw.startswith("INFO") else logging.WARNING,
                    "Anlernen %s nicht gespeichert: %s",
                    s.pfad.name,
                    hw,
                )
            self.toast(
                "fehler",
                _("Nicht gespeichert"),
                anlernen.erste_meldung(erg.hinweise) or _("Details im Log"),
            )
            return
        self.gespeichert += 1
        n, ab = s.fortschritt()
        detail = _("Vorlage: {n} von {ab} Rechnungen ohne Korrektur.").format(n=n, ab=ab)
        art = "ok"
        self._kontrolle = (s.profil, dict(s.selbstkontrolle))
        if s.selbstkontrolle:  # mit der neuen Vorlage anders gelesen: zeigen, nicht verschweigen
            art = "info"
            namen = ", ".join(
                _(anlernen.FELDER[f][0]) if f in anlernen.FELDER else _("Positionen")
                for f in s.selbstkontrolle
            )
            detail = (
                _(
                    "Selbstkontrolle: Mit der neuen Vorlage anders gelesen: {felder}. Die Felder sind bei der "
                    "nächsten PDF markiert – Details im Log."
                ).format(felder=namen)
                + " "
                + detail
            )
        if s.zaehler_grund:
            detail = (
                _("Zähler zurückgesetzt: {grund}.").format(grund=s.zaehler_grund) + " " + detail
            )
        sicher = n >= ab
        if sicher and not anlernen.pdferkennung.einstellungen(s.profil)["nur_pdf"]:
            detail = _(
                "Die Vorlage ist sicher. „Automatisch, ohne Nachfrage“ kannst du in den Einstellungen "
                "einschalten."
            )
        if s.nicht_verschoben is not None:
            detail += " " + _("Die PDF blieb im Anlern-Ordner ({grund}).").format(
                grund=s.nicht_verschoben
            )
        self._neue_aus_warteschlange()
        self.i += 1
        titel = _("Gespeichert: {nr}").format(nr=erg.nummer)
        if self.i < len(self.pdfs) and self._laden():
            self.toast(
                art,
                titel,
                detail
                + " "
                + _("Weiter mit der nächsten PDF ({i} von {n}).").format(
                    i=self.i + 1, n=len(self.pdfs)
                ),
            )
            return
        if not sicher:
            detail += " " + _(
                "Keine weitere PDF wartet: Lege die nächste Rechnung dieses Absenders in den "
                "Eingang (oder wähle sie unter „Anlernen“)."
            )
        p = self.parent()
        if p is not None and hasattr(p, "toast"):
            p.toast(art, titel, detail)
        self.accept()

    def _neue_aus_warteschlange(self) -> None:
        """PDFs, die inzwischen im Anlern-Ordner gelandet sind, hinten anhängen – der Assistent macht dann mit
        ihnen weiter, statt nach der letzten gewählten PDF aufzuhören."""
        try:
            bekannt = {p.resolve() for p in self.pdfs}
            for p in anlernen.warteschlange(self.k):
                if p.resolve() not in bekannt and p.resolve() != self.s.pfad.resolve():
                    self.pdfs.append(p)
        except OSError as e:
            log.warning("Anlern-Warteschlange nicht lesbar: %s", e)

    def done(self, r):
        self.pdf.seite.schliessen()
        super().done(r)


def absender_fuer_import(datei: Path) -> Absender:
    return aus_csv(Path(datei).read_bytes())
