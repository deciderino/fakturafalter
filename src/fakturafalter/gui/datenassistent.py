# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Assistenten für „PDF + CSV“ (Datei → Format → Vorschau → Probe → Fertig) und „PDF + XML“ (Format → Probe →
Fertig) im Stil der Ersteinrichtung. Ergebnis CSV: ein normales CSV-Profil im Profilordner."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import adapter_xml
from .. import csv_einrichtung as ce
from . import aktionen
from .bausteine import (
    Schritte,
    ToastStapel,
    Zustand,
    fussleiste,
    karte,
    knopf,
    kopfleiste,
    lbl,
    rollen,
)
from .blockassistent import AnfangsBox, BlockTabelle, Legende, SpaltenJeBlock
from .texte import _

TRENNZEICHEN = (
    (";", "Semikolon ;"),
    (",", "Komma ,"),
    ("\t", "Tabulator"),
    ("|", "Senkrechter Strich |"),
)
KODIERUNGEN = (
    ("utf-8", "UTF-8"),
    ("utf-8-sig", "UTF-8 mit BOM"),
    ("cp1252", "Windows-1252 (ANSI)"),
    ("iso-8859-15", "ISO-8859-15"),
)
DEZIMAL = ((",", "Komma (1.234,56)"), (".", "Punkt (1,234.56)"))
DATUM = (
    ("%d.%m.%Y", "TT.MM.JJJJ"),
    ("%Y-%m-%d", "JJJJ-MM-TT"),
    ("%d.%m.%y", "TT.MM.JJ"),
    ("%d/%m/%Y", "TT/MM/JJJJ"),
    ("%Y%m%d", "JJJJMMTT"),
)
VORSCHAU_ZEILEN = 8
NICHT = "– nicht verwenden –"


def _seite() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(32, 24, 32, 24)
    v.setSpacing(10)
    return w, v


def _auswahl(werte, jetzt=None, name: str = "") -> QComboBox:
    b = QComboBox()
    b.setMinimumHeight(48)
    if name:
        b.setObjectName(name)
        b.setAccessibleName(name)
    for code, text in werte:
        b.addItem(_(text), code)
    if jetzt is not None and b.findData(jetzt) >= 0:
        b.setCurrentIndex(b.findData(jetzt))
    return b


class _Assistent(QDialog):
    """Gerüst: Kopf mit Schritten, Seitenstapel, Fuß mit Zurück/Weiter (wie die Ersteinrichtung)."""

    SCHRITTE: tuple[str, ...] = ()

    def __init__(self, haupt, eltern, titel: str, unter: str):
        super().__init__(eltern or haupt)
        self.haupt, self.c = haupt, haupt.c
        self.setWindowTitle(titel)
        self.setObjectName("wurzel")
        self.resize(1000, 800)
        self.toasts = ToastStapel(self, abstand_unten=90)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        kopf, kv, _t = kopfleiste(titel, unter)
        self.schritte = Schritte(self.c, [_(s) for s in self.SCHRITTE])
        kv.addWidget(self.schritte)
        v.addWidget(kopf)
        self.stapel = QStackedWidget()
        v.addWidget(self.stapel, 1)
        fuss, links, self.l_fuss, rechts = fussleiste(self.c)
        links.addWidget(knopf(_("Abbrechen"), klick=self.reject))
        self.b_zurueck = knopf(_("Zurück"), klick=lambda: self.gehe(self.i - 1))
        links.addWidget(self.b_zurueck)
        self.b_weiter = knopf(_("Weiter"), primary=True, klick=self._weiter)
        self.b_weiter.setDefault(True)
        rechts.addWidget(self.b_weiter)
        v.addWidget(fuss)
        self.i = 0

    def toast(self, art, titel, detail=""):
        return self.toasts.zeigen(self.c, art, titel, detail)

    def gehe(self, i: int) -> None:
        n = len(self.SCHRITTE)
        self.i = max(0, min(n - 1, i))
        self.stapel.setCurrentIndex(self.i)
        self.schritte.setzen(self.i)
        self.b_zurueck.setEnabled(0 < self.i < n - 1)
        self.b_weiter.setText(_("Fertig") if self.i == n - 1 else _("Weiter"))
        self.l_fuss.setText(_("Schritt {n} von {m}").format(n=self.i + 1, m=n))
        self.betreten(self.i)

    def betreten(self, i: int) -> None:
        pass

    def _weiter(self) -> None:
        raise NotImplementedError

    def _probe_tabelle(self) -> QTableWidget:
        t = QTableWidget(0, 4)
        t.setObjectName("probe")
        t.setHorizontalHeaderLabels([_("Rechnung"), _("Kunde"), _("Brutto"), _("Ergebnis")])
        h = t.horizontalHeader()
        for j in range(3):
            h.setSectionResizeMode(j, QHeaderView.ResizeMode.ResizeToContents)
        h.setStretchLastSection(True)  # „Ergebnis“ füllt die Breite, lange Hinweise brechen um
        t.setWordWrap(True)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(40)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setMinimumHeight(220)
        h.sectionResized.connect(
            lambda *_a: _Assistent._zeilenhoehen(t)
        )  # neue Breite → neu umbrechen
        return t

    @staticmethod
    def _zeilenhoehen(t: QTableWidget) -> None:
        """Zeilen so hoch wie der umbrochene Text, mindestens 40 px."""
        t.resizeRowsToContents()
        for i in range(t.rowCount()):
            t.setRowHeight(i, max(40, t.rowHeight(i)))

    def _probe_zeigen(self, t: QTableWidget, l_sum, ergebnisse: list[ce.Probe]) -> None:
        from . import daten

        t.setRowCount(len(ergebnisse))
        for i, e in enumerate(ergebnisse):
            if e.status == "ok":  # Warnungen (z. B. nicht übernommene XML-Elemente) sichtbar machen
                text = (
                    _("bereit, mit Hinweisen: {g}").format(g=e.hinweise[0])
                    if e.hinweise
                    else _("bereit")
                )
            else:
                text = (
                    _("braucht Prüfung: {g}").format(g=e.hinweise[0])
                    if e.hinweise
                    else _("braucht Prüfung")
                )
            if e.status == "fehler":
                text = _("Fehler: {g}").format(g=e.hinweise[0] if e.hinweise else "")
            for j, w in enumerate((e.nummer, e.kunde, daten.betrag(e.brutto), text)):
                it = QTableWidgetItem(w)
                it.setToolTip("\n".join(e.hinweise) if j == 3 else w)
                t.setItem(i, j, it)
        _Assistent._zeilenhoehen(t)
        ok = sum(e.status == "ok" for e in ergebnisse)
        hinweise = sum(e.status == "ok" and bool(e.hinweise) for e in ergebnisse)
        text = _(
            "{ok} von {n} Rechnungen bereit. Was „braucht Prüfung“ zeigt, landet im Lauf in „Zu prüfen“ "
            "– du kannst es dort freigeben oder hier die Zuordnung ändern."
        ).format(ok=ok, n=len(ergebnisse))
        if hinweise:
            text += " " + _(
                "{h} davon mit Hinweisen – Einzelheiten in der Spalte „Ergebnis“ und im Protokoll."
            ).format(h=hinweise)
        l_sum.setText(text)
        l_sum.setObjectName("gut" if ok == len(ergebnisse) and not hinweise else "warn")
        l_sum.style().unpolish(l_sum)
        l_sum.style().polish(l_sum)


class CsvAssistent(_Assistent):
    SCHRITTE = ("Datei", "Format", "Vorschau", "Probe", "Fertig")

    def __init__(self, haupt, eltern=None, profil: dict | None = None, start: str | None = None):
        super().__init__(
            haupt,
            eltern,
            _("CSV einrichten"),
            _(
                "Eine Beispiel-CSV aus deiner Warenwirtschaft genügt. Danach liest Fakturafalter jede "
                "CSV dieser Art von selbst."
            ),
        )
        self.alt = profil  # „Ändern…“: vorhandenes Profil
        self.datei: Path | None = None
        self.fmt: ce.Format | None = None
        self.gespeichert: Path | None = None
        self.spalten: list[QComboBox] = []
        self.steuer_wahl: dict[str, QComboBox] = {}
        self.art = "zeile_je_position"
        self.bloecke: list[dict] = []
        self.zuordnung_je: dict[str, dict[str, str]] = {}
        self.block_typ: dict[int, QComboBox] = {}
        self.f_art = None
        self._start = start
        self.block_felder: dict[int, set[str]] = {}
        self.block_marker: dict[int, str] = {}
        self.block_wiederholend: dict[int, bool] = {}
        self._bloecke_init = False
        self.satzart_spalte = None
        for s in (
            self._seite_datei(),
            self._seite_format(),
            self._seite_vorschau(),
            self._seite_textzeilen(),
            self._seite_darstellung(),
            self._seite_probe(),
            self._seite_fertig(),
            self._seite_bloecke(),
            self._seite_spalten_je_block(),
        ):
            self.stapel.addWidget(rollen(s))
        self._schritte_anpassen()
        ziel = 0
        if (
            start == "darstellung"
            and (profil or {}).get("aufbau", {}).get("art", "zeile_je_position")
            == "zeile_je_position"
        ):
            folge = self._folge()
            for i, (st, _n) in enumerate(folge):
                if st == 4:
                    ziel = i
                    break
        self.gehe(ziel)

    # ------------------------------------------------------------------ 1 Datei
    def _seite_datei(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Welche CSV legt deine Warenwirtschaft ab?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _("Wähle eine echte Export-Datei. Sie wird nur gelesen, nicht verändert."),
                "sub",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addWidget(knopf(_("CSV-Datei auswählen…"), primary=True, klick=self._waehlen))
        h.addStretch(1)
        v.addLayout(h)
        self.l_datei = lbl("", umbruch=True)
        v.addWidget(self.l_datei)
        v.addWidget(lbl(_("Name für diese Zuordnung")))
        self.name = QLineEdit(str((self.alt or {}).get("profil") or ""))
        self.name.setObjectName("csv_name")
        self.name.setAccessibleName(_("Name für diese Zuordnung"))
        self.name.setPlaceholderText(_("z. B. Warenwirtschaft"))
        self.name.setMinimumHeight(48)
        v.addWidget(self.name)
        v.addStretch(1)
        return w

    def _waehlen(self) -> None:
        d, _f = QFileDialog.getOpenFileName(
            self, _("CSV-Datei auswählen…"), str(Path.home()), _("CSV-Dateien (*.csv *.txt *.tsv)")
        )
        if d:
            self.datei_setzen(Path(d))

    def datei_setzen(self, datei: Path) -> None:
        try:
            fmt = ce.format_erkennen(datei)
        except (OSError, ValueError, UnicodeError) as e:
            self.toast("fehler", _("Datei lässt sich nicht lesen"), str(e))
            self.gehe(self.i)
            return
        self.datei = datei
        if self.alt:  # beim Ändern: gespeichertes Format vorbelegen
            d, z = self.alt.get("datei") or {}, self.alt.get("zahlen") or {}
            fmt.kodierung = d.get("kodierung", fmt.kodierung)
            fmt.trennzeichen = d.get("trennzeichen", fmt.trennzeichen)
            fmt.dezimal = z.get("dezimal", fmt.dezimal)
            fmt.datum = (self.alt.get("datum") or {}).get("format", fmt.datum)
            try:
                fmt = self._neu_lesen(fmt)
            except (ValueError, UnicodeError):
                fmt = ce.format_erkennen(datei)
        self.fmt = fmt
        if not self.name.text().strip():
            self.name.setText(datei.stem.replace("_", " ").strip()[:40])
        self.l_datei.setText(
            _("{datei}: {n} Zeilen, {s} Spalten").format(
                datei=datei.name, n=len(fmt.zeilen), s=len(fmt.kopf)
            )
        )
        for box, wert in (
            (self.f_trenn, fmt.trennzeichen),
            (self.f_kod, fmt.kodierung),
            (self.f_dez, fmt.dezimal),
            (self.f_datum, fmt.datum),
        ):
            box.blockSignals(True)
            if box.findData(wert) < 0:
                box.addItem(str(wert), wert)
            box.setCurrentIndex(box.findData(wert))
            box.blockSignals(False)
        self._format_zeigen()
        self._vorschau_bauen()
        self.gehe(self.i)

    # ------------------------------------------------------------------ 2 Format
    def _seite_format(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Stimmt das Format?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _("Fakturafalter hat es erkannt. Passt die Vorschau nicht, stelle es hier um."),
                "sub",
                umbruch=True,
            )
        )
        g = QGridLayout()
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(6)
        self.f_trenn = _auswahl(TRENNZEICHEN, name=_("Trennzeichen"))
        self.f_kod = _auswahl(KODIERUNGEN, name=_("Zeichensatz"))
        self.f_dez = _auswahl(DEZIMAL, name=_("Dezimalzeichen"))
        self.f_datum = _auswahl(DATUM, name=_("Datumsformat"))
        for i, (t, b) in enumerate(
            (
                (_("Trennzeichen"), self.f_trenn),
                (_("Zeichensatz"), self.f_kod),
                (_("Dezimalzeichen"), self.f_dez),
                (_("Datumsformat"), self.f_datum),
            )
        ):
            g.addWidget(lbl(t), (i // 2) * 2, i % 2)
            g.addWidget(b, (i // 2) * 2 + 1, i % 2)
            b.currentIndexChanged.connect(self._format_geaendert)
        v.addLayout(g)
        v.addWidget(lbl(_("Aufbau der Datei"), umbruch=True))
        self.f_art = _auswahl(
            (
                ("auto", "Automatisch erkennen"),
                ("zeile_je_position", "Eine Zeile je Position (Standard)"),
                ("bloecke", "Blöcke mit eigener Kopfzeile"),
                ("satzart", "Satzart (Kennwort in einer Spalte)"),
            ),
            name=_("Aufbau der Datei"),
        )
        self.f_art.currentIndexChanged.connect(self._art_geaendert)
        v.addWidget(self.f_art)
        self.l_satzart = lbl("", "hinweis", umbruch=True)
        v.addWidget(self.l_satzart)
        self.box_satzarten = QWidget()
        sv = QVBoxLayout(self.box_satzarten)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(lbl(_("Satzart-Kennwerte (neben K und P auch S, R oder eigene Wörter)")))
        self.t_satzarten = QTableWidget(3, 2)
        self.t_satzarten.setHorizontalHeaderLabels([_("Wert"), _("Bedeutung")])
        self.t_satzarten.verticalHeader().setVisible(False)
        self.t_satzarten.setMaximumHeight(140)
        for i, (wert, art) in enumerate((("S", "kopf"), ("R", "rabatt"), ("Z", "zuschlag"))):
            # defaults empty so K/P remain the standard; user fills extras
            self.t_satzarten.setItem(i, 0, QTableWidgetItem("" if i else ""))
            b = _auswahl(
                (("kopf", "Kopf"), ("position", "Position"), ("rabatt", "Rabatt"), ("zuschlag", "Zuschlag")),
                art,
            )
            self.t_satzarten.setCellWidget(i, 1, b)
        sv.addWidget(self.t_satzarten)
        self.box_satzarten.setVisible(False)
        v.addWidget(self.box_satzarten)
        self.t_format = QTableWidget()
        self.t_format.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.t_format.setMinimumHeight(260)
        v.addWidget(self.t_format, 1)
        return w

    def _neu_lesen(self, fmt: ce.Format) -> ce.Format:
        neu = ce.format_erkennen(self.datei, fmt.kodierung, fmt.trennzeichen)
        neu.dezimal, neu.datum = fmt.dezimal, fmt.datum
        neu.tausender = "." if fmt.dezimal == "," else ""
        return neu

    def _format_geaendert(self, *_a) -> None:
        if not self.datei:
            return
        f = ce.Format(
            self.f_kod.currentData(),
            self.f_trenn.currentData(),
            self.f_dez.currentData(),
            "",
            self.f_datum.currentData(),
        )
        try:
            self.fmt = self._neu_lesen(f)
        except (ValueError, UnicodeError) as e:
            self.toast("fehler", _("Mit dieser Einstellung nicht lesbar"), str(e))
            return
        self._format_zeigen()
        self._vorschau_bauen()

    def _format_zeigen(self) -> None:
        fmt = self.fmt
        if fmt:
            self._art_vorschlagen()
            self._schritte_anpassen()
        if not fmt:
            return
        t = self.t_format
        t.clear()
        from .. import csv_bloecke

        rows = [list(fmt.kopf)] + [list(z) for z in fmt.zeilen]
        if csv_bloecke.sieht_nach_marker_heuristik(fmt.kopf):
            # Erste Zeile ist ein Marker, keine Datei-Kopfzeile: alle Spalten zeigen.
            breit = max((len(r) for r in rows), default=1)
            t.setColumnCount(breit)
            t.setHorizontalHeaderLabels([str(j + 1) for j in range(breit)])
            t.setRowCount(min(VORSCHAU_ZEILEN, len(rows)))
            for i, z in enumerate(rows[:VORSCHAU_ZEILEN]):
                for j, w in enumerate(z[:breit]):
                    t.setItem(i, j, QTableWidgetItem(w))
        else:
            t.setColumnCount(len(fmt.kopf))
            t.setHorizontalHeaderLabels(fmt.kopf)
            t.setRowCount(min(VORSCHAU_ZEILEN, len(fmt.zeilen)))
            for i, z in enumerate(fmt.zeilen[:VORSCHAU_ZEILEN]):
                for j, w in enumerate(z[: len(fmt.kopf)]):
                    t.setItem(i, j, QTableWidgetItem(w))
        t.resizeColumnsToContents()

    def _art_erkannt(self) -> str:
        if not self.fmt:
            return "zeile_je_position"
        if ce.bloecke_erkannt(self.fmt):
            return "bloecke"
        if ce.satzart(self.fmt):
            return "satzart"
        return "zeile_je_position"

    def _art_vorschlagen(self) -> None:
        erkannt = self._art_erkannt()
        if self.f_art is not None and self.f_art.currentData() == "auto":
            self.art = erkannt
        elif self.f_art is not None:
            self.art = self.f_art.currentData() or erkannt
            if self.art == "auto":
                self.art = erkannt
        else:
            self.art = erkannt
        texte = {
            "bloecke": _("Diese Datei sieht nach mehreren Blöcken aus."),
            "satzart": _(
                "Kennwort-Spalte (Satzart) erkannt. Kopf- und Positionszeilen werden getrennt gelesen."
            ),
            "zeile_je_position": "",
        }
        self.l_satzart.setText(
            texte.get(
                self.art if self.f_art is None or self.f_art.currentData() == "auto" else erkannt,
                "",
            )
        )
        self.l_satzart.setVisible(bool(self.l_satzart.text()))
        if getattr(self, "box_satzarten", None):
            self.box_satzarten.setVisible(self.art == "satzart")

    def _art_geaendert(self, *_a) -> None:
        if not self.fmt:
            return
        self._bloecke_init = False
        self._art_vorschlagen()
        self._schritte_anpassen()
        self._vorschau_bauen()

    def _textzeile(self) -> dict:
        if not getattr(self, "f_textziel", None):
            return {}
        return {
            "ziel": self.f_textziel.currentData(),
            "platzhalter": self.f_platz.text(),
            "leerzeile_modus": self.f_leer_modus.currentData(),
            "verwaist": self.f_verwaist.currentData(),
            "zwischen": self.f_zwischen.currentData()
            if getattr(self, "f_zwischen", None)
            else "vorher",
            "trenner": "\n",
            "leer": self._leer_felder(),
            "text_spalte": (self.zuordnung() or {}).get("BT-153"),
            "preis_ohne_menge": self.f_preis_ohne.currentData()
            if getattr(self, "f_preis_ohne", None)
            else "pruefen",
        }

    def _block_wechseln(self, *_a) -> None:
        if getattr(self, "_block_wechsel_sperre", False):
            return
        self._vorschau_bauen_block()

    # ------------------------------------------------------------------ 3 Vorschau mit Zuordnung
    def _seite_vorschau(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Was steht in welcher Spalte?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Über jeder Spalte steht, wofür Fakturafalter sie nimmt. Stimmt etwas nicht, wähle es im "
                    "Feld darüber um."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.box_bloecke = QWidget()
        bv = QVBoxLayout(self.box_bloecke)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.addWidget(
            lbl(_("Erkannte Blöcke – typisiere sie, falls nötig."), "hinweis", umbruch=True)
        )
        self.t_bloecke = QTableWidget(0, 3)
        self.t_bloecke.setHorizontalHeaderLabels([_("Zeile"), _("Typ"), _("Kopfzeile")])
        self.t_bloecke.verticalHeader().setVisible(False)
        self.t_bloecke.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.t_bloecke.setMaximumHeight(160)
        bv.addWidget(self.t_bloecke)
        hb = QHBoxLayout()
        hb.addWidget(lbl(_("Spalten zuordnen für")))
        self.f_block = QComboBox()
        self.f_block.setMinimumHeight(48)
        self.f_block.currentIndexChanged.connect(self._block_wechseln)
        hb.addWidget(self.f_block, 1)
        bv.addLayout(hb)
        v.addWidget(self.box_bloecke)
        self.t_map = QTableWidget()
        self.t_map.setObjectName("zuordnung")
        self.t_map.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.t_map.setMinimumHeight(300)
        self.t_map.verticalHeader().setVisible(False)
        v.addWidget(self.t_map, 1)
        self.l_fehlt = lbl("", "warn", umbruch=True)
        v.addWidget(self.l_fehlt)
        self.k_steuer, kv = karte()
        kv.addWidget(lbl(_("Steuer"), "titel"))
        self.l_steuer = lbl("", "hinweis", umbruch=True)
        kv.addWidget(self.l_steuer)
        self.g_steuer = QGridLayout()
        self.g_steuer.setHorizontalSpacing(16)
        kv.addLayout(self.g_steuer)
        v.addWidget(self.k_steuer)
        self.l_einheit = lbl("", "hinweis", umbruch=True)
        v.addWidget(self.l_einheit)
        self.box_text = QWidget()
        tv = QVBoxLayout(self.box_text)
        tv.setContentsMargins(0, 8, 0, 0)
        tv.addWidget(lbl(_("Textzeilen und Leerzeilen"), "titel", umbruch=True))
        self.f_textziel = _auswahl(
            (("BT-154", "Beschreibung (BT-154)"), ("BT-153", "Bezeichnung (BT-153)")),
            "BT-154",
            _("Textziel"),
        )
        tv.addWidget(lbl(_("Text ohne Menge/Preis kommt nach")))
        tv.addWidget(self.f_textziel)
        self.f_platz = QLineEdit("#LEER")
        self.f_platz.setPlaceholderText(_("leer = kein Platzhalter"))
        self.f_platz.setMinimumHeight(48)
        tv.addWidget(lbl(_("Platzhalter für eine gewollte Leerzeile auf der Sichtseite")))
        tv.addWidget(self.f_platz)
        self.f_leer_modus = _auswahl(
            (
                ("beides", "Platzhalter oder Zeile nur mit Kopffeldern"),
                ("platzhalter", "Nur Platzhalter"),
                ("kopffeldzeile", "Nur Zeile mit Kopffeldern (ohne Menge/Preis/Text)"),
            ),
            "beides",
            _("Leerzeile erkennen"),
        )
        tv.addWidget(self.f_leer_modus)
        self.f_verwaist = _auswahl(
            (
                ("BT-22", "Als Hinweis zur Rechnung (BT-22)"),
                ("naechste", "Zur folgenden Position (BT-154)"),
                ("pruefen", "Rechnung nach „Zu prüfen“"),
            ),
            "BT-22",
            _("Textzeile vor der ersten Position"),
        )
        tv.addWidget(lbl(_("Textzeile vor der ersten Position")))
        tv.addWidget(self.f_verwaist)
        self.f_zwischen = _auswahl(
            (
                ("vorher", "Zur vorherigen Position (Beschreibung)"),
                ("nachher", "Zur folgenden Position (darüber auf der Sichtseite)"),
            ),
            "vorher",
            _("Text zwischen zwei Positionen"),
        )
        tv.addWidget(lbl(_("Text zwischen zwei Positionen")))
        tv.addWidget(self.f_zwischen)
        v.addWidget(self.box_text)
        return w

    def _vorschau_bauen(self) -> None:
        fmt = self.fmt
        if not fmt:
            return
        bloecke = self.art == "bloecke"
        if getattr(self, "box_bloecke", None):
            self.box_bloecke.setVisible(False)
        # box_text liegt auf der Textzeilen-Seite und darf hier nicht versteckt werden.
        if bloecke:
            kopf = ce.einzigartige_spalten(fmt) or list(fmt.kopf)
            vorschlag = ce.spalten_vorschlagen(kopf, fmt.zeilen)
            if self.alt:
                alt = {f: s for f, s in ce.profil_zuordnung(self.alt).items() if s in kopf}
                if alt:
                    vorschlag = alt
            je_spalte = {s: f for f, s in vorschlag.items()}
            zeilen = self._vorschauwerte_fuer(kopf)
            self._map_tabelle(kopf, zeilen, je_spalte)
            if getattr(self, "l_fehlt", None):
                self.l_fehlt.setText(
                    _(
                        "Ob die Rechnung vollständig ist, prüft Fakturafalter am Ende, "
                        "wenn alle Blöcke zusammengeführt sind."
                    )
                )
                self.l_fehlt.setVisible(True)
                self.l_fehlt.setObjectName("hinweis")
                self.l_fehlt.setStyleSheet("")
                self.l_fehlt.style().unpolish(self.l_fehlt)
                self.l_fehlt.style().polish(self.l_fehlt)
            return
        vorschlag = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
        if self.alt:
            alt = {f: s for f, s in ce.profil_zuordnung(self.alt).items() if s in fmt.kopf}
            if alt:
                vorschlag = alt
        je_spalte = {s: f for f, s in vorschlag.items()}
        self._map_tabelle(fmt.kopf, fmt.zeilen, je_spalte)

    def _bloecke_tabelle(self) -> None:
        self.bloecke = ce.bloecke_schneiden_fmt(self.fmt)
        self.block_typ = {}
        t = self.t_bloecke
        t.setRowCount(len(self.bloecke))
        self._block_wechsel_sperre = True
        self.f_block.blockSignals(True)
        self.f_block.clear()
        typen = (
            ("positionen", _("Positionen")),
            ("kopf", _("Kopf")),
            ("zahlung", _("Zahlung / Skonto")),
            ("summen", _("Summen / Steuer")),
            ("lieferung", _("Lieferanschrift")),
            ("rabatt", _("Rabatte")),
            ("notiz", _("Notizen")),
        )
        for i, b in enumerate(self.bloecke):
            typ = ce.typ_vorschlag(b.get("kopf") or [])
            if typ and typ not in self.zuordnung_je:
                daten = [w for _n, w in b.get("daten") or []]
                self.zuordnung_je[typ] = ce.spalten_vorschlagen(b.get("kopf") or [], daten)
            t.setItem(i, 0, QTableWidgetItem(str(b.get("start") or "")))
            cb = QComboBox()
            for code, text in typen:
                cb.addItem(text, code)
            j = cb.findData(typ)
            cb.setCurrentIndex(j if j >= 0 else 0)
            cb.currentIndexChanged.connect(lambda *_a, n=i: self._block_typ_geaendert(n))
            t.setCellWidget(i, 1, cb)
            self.block_typ[i] = cb
            t.setItem(i, 2, QTableWidgetItem(", ".join(b.get("kopf") or [])))
            self.f_block.addItem(
                _("{t} (Zeile {n})").format(t=cb.currentText(), n=b.get("start")), i
            )
        self.f_block.blockSignals(False)
        self._block_wechsel_sperre = False
        t.resizeColumnsToContents()

    def _block_typ_geaendert(self, i: int) -> None:
        if i < self.f_block.count():
            b = self.bloecke[i]
            self.f_block.setItemText(
                i, _("{t} (Zeile {n})").format(t=self.block_typ[i].currentText(), n=b.get("start"))
            )
        self._vorschau_bauen_block()

    def _aktueller_block(self) -> dict | None:
        i = self.f_block.currentData()
        if i is None or i >= len(self.bloecke):
            return None
        b = dict(self.bloecke[i])
        if i in self.block_typ:
            b["typ"] = self.block_typ[i].currentData()
        return b

    def _vorschau_bauen_block(self) -> None:
        b = self._aktueller_block()
        if not b:
            return
        kopf = list(b.get("kopf") or [])
        daten = [w for _n, w in b.get("daten") or []]
        typ = b.get("typ") or ""
        gespeichert = self.zuordnung_je.get(typ)
        vorschlag = gespeichert or ce.spalten_vorschlagen(kopf, daten)
        je_spalte = {s: f for f, s in vorschlag.items()}
        self._map_tabelle(kopf, daten, je_spalte)

    def _map_tabelle(
        self, kopf: list[str], zeilen: list[list[str]], je_spalte: dict[str, str]
    ) -> None:
        t = self.t_map
        t.clear()
        t.setColumnCount(len(kopf))
        t.setHorizontalHeaderLabels(kopf)
        n = min(VORSCHAU_ZEILEN, len(zeilen))
        t.setRowCount(n + 1)
        t.setRowHeight(0, 52)
        self.spalten = []
        self._map_kopf = list(kopf)
        for j, sp in enumerate(kopf):
            b = QComboBox()
            b.setMinimumHeight(48)
            b.setAccessibleName(_("Spalte {s}").format(s=sp))
            b.addItem(_(NICHT), "")
            for f, anz, *_r in ce.FELDER:
                b.addItem(_(anz), f)
            b.setCurrentIndex(max(0, b.findData(je_spalte.get(sp, ""))))
            b.currentIndexChanged.connect(lambda _i, s=j: self._zuordnung_geaendert(s))
            t.setCellWidget(0, j, b)
            self.spalten.append(b)
        for i, z in enumerate(zeilen[:n]):
            for j, w in enumerate(z[: len(kopf)]):
                t.setItem(i + 1, j, QTableWidgetItem(w))
        t.resizeColumnsToContents()
        for j in range(len(kopf)):
            t.setColumnWidth(j, max(t.columnWidth(j), 200))
        self._zuordnung_geaendert(None)

    def zuordnung(self) -> dict[str, str]:
        kopf = getattr(self, "_map_kopf", None) or (self.fmt.kopf if self.fmt else [])
        return {
            b.currentData(): kopf[j]
            for j, b in enumerate(self.spalten)
            if b.currentData() and j < len(kopf)
        }

    def _alle_zuordnungen(self) -> dict[str, str]:
        """Bei Blöcken Pflichtfelder über alle typisierten Blöcke prüfen, nicht nur den sichtbaren."""
        return self.zuordnung()

    def _zuordnung_geaendert(self, spalte: int | None) -> None:
        if spalte is not None:  # jedes Feld nur einmal: gleiches Feld an anderer Spalte lösen
            f = self.spalten[spalte].currentData()
            for j, b in enumerate(self.spalten):
                if j != spalte and f and b.currentData() == f:
                    b.blockSignals(True)
                    b.setCurrentIndex(0)
                    b.blockSignals(False)
        z = self.zuordnung()
        fehlt = ce.fehlende_pflicht(self._alle_zuordnungen())
        if self.art == "bloecke":
            self.l_fehlt.setText(
                _(
                    "Ob die Rechnung vollständig ist, prüft Fakturafalter am Ende, "
                    "wenn alle Blöcke zusammengeführt sind."
                )
                + (
                    (
                        " "
                        + _("Noch nicht zugeordnet, aber empfohlen: {was}.").format(
                            was=", ".join(_(x) for x in fehlt)
                        )
                    )
                    if fehlt
                    else ""
                )
            )
            self.l_fehlt.setVisible(True)
            self.l_fehlt.setObjectName("hinweis")
            self.l_fehlt.setStyleSheet("")
            self.l_fehlt.style().unpolish(self.l_fehlt)
            self.l_fehlt.style().polish(self.l_fehlt)
        else:
            self.l_fehlt.setText(
                _("Noch zuordnen: {was}").format(was=", ".join(_(x) for x in fehlt))
                if fehlt
                else ""
            )
            self.l_fehlt.setVisible(bool(fehlt))
        self._steuer_bauen(z.get("steuer"))
        einheit_werte = (
            ce.spalte_in_datei(self.fmt, z["BT-130"]) if z.get("BT-130") and self.fmt else []
        )
        eh = ce.einheiten_vorschlag(einheit_werte) if einheit_werte else {}
        unbekannt = [w for w, c in eh.items() if not c]
        self.l_einheit.setText(
            _("Einheiten ohne Zuordnung (kommen zur Prüfung): {e}").format(e=", ".join(unbekannt))
            if unbekannt
            else ""
        )
        self.l_einheit.setVisible(bool(unbekannt))
        if self.i == 2:
            self.gehe(self.i)

    def _steuer_bauen(self, spalte: str | None) -> None:
        while self.g_steuer.count():
            w = self.g_steuer.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.steuer_wahl = {}
        werte = ce.spalte_in_datei(self.fmt, spalte) if spalte and self.fmt else []
        self.k_steuer.setVisible(bool(spalte))
        if not spalte:
            return
        if ce.steuer_ist_satz(werte):
            self.l_steuer.setText(
                _("In der Spalte steht der Steuersatz – er wird direkt übernommen.")
            )
            return
        self.l_steuer.setText(
            _(
                "Was bedeutet welcher Wert? Unklares bleibt auf „prüfen“ – solche Rechnungen kommen "
                "zur Prüfung, nichts wird geraten."
            )
        )
        alt = ((self.alt or {}).get("mappings") or {}).get("steuer") or {}
        for i, (w, vor) in enumerate(ce.steuer_vorschlag(werte).items()):
            b = QComboBox()
            b.setMinimumHeight(48)
            b.setAccessibleName(_("Steuerwert {w}").format(w=w))
            for anz in ce.STEUER_WAHL:
                b.addItem(_(anz), anz)
            gesp = next(
                (
                    a
                    for a, d in ce.STEUER_WAHL.items()
                    if d
                    and isinstance(alt.get(w), dict)
                    and alt[w].get("BT-151") == d["BT-151"]
                    and float(alt[w].get("BT-152", -1)) == float(d["BT-152"])
                ),
                None,
            )
            b.setCurrentIndex(b.findData(gesp or vor))
            self.g_steuer.addWidget(lbl(f"„{w}“"), i, 0)
            self.g_steuer.addWidget(b, i, 1)
            self.steuer_wahl[w] = b

    def _vorschauwerte_fuer(self, kopf: list[str]) -> list[list[str]]:
        """Beispielwerte zu den einzigartigen Spaltennamen, über alle Blöcke."""
        aus: list[list[str]] = []
        for sp in kopf:
            werte = ce.spalte_in_datei(self.fmt, sp) if self.fmt else []
            for i, w in enumerate(werte[:8]):
                while len(aus) <= i:
                    aus.append([""] * len(kopf))
                aus[i][kopf.index(sp)] = w
        return aus

    def _seite_bloecke(self) -> QWidget:

        from .bausteine import lbl

        w, v = _seite()
        v.addWidget(lbl(_("Blöcke festlegen"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Jede Farbe ist ein Block. Der Block läuft bis zum nächsten Anfang. "
                    "Grenzen mit der Maus ziehen oder Zeilen markieren und zuweisen."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.legende = Legende()
        self.legende.typ_gewählt.connect(self._block_zuweisen)
        v.addWidget(self.legende)
        self.t_block = BlockTabelle()
        self.t_block.block_gesetzt.connect(self._bloecke_geaendert)
        self.t_block.cursor_block.connect(self._block_anzeigen)
        v.addWidget(self.t_block, 1)
        self.box_anfang = AnfangsBox()
        self.box_anfang.regel_gesetzt.connect(self._bloecke_geaendert)
        v.addWidget(self.box_anfang)
        # alte Tabelle bleibt als unsichtbare Kompatibilität für vorhandene Tests
        self.t_bloecke_neu = self.t_block
        return w

    def _seite_spalten_je_block(self) -> QWidget:
        w, v = _seite()
        self.spalten_seite = SpaltenJeBlock()
        self.spalten_seite.geaendert.connect(lambda: None)
        v.addWidget(self.spalten_seite, 1)
        return w

    def _csv_zeilen(self) -> list[list[str]]:
        if not self.fmt:
            return []
        return [list(self.fmt.kopf or [])] + [list(z) for z in (self.fmt.zeilen or [])]

    def _bloecke_laden(self) -> None:
        if self._bloecke_init and self.t_block.bloecke:
            self.t_block.setzen(self._csv_zeilen(), self.t_block.bloecke)
            self.box_anfang.satzart_spalte = self.satzart_spalte
            self._block_anzeigen(self.t_block.aktueller_block_index())
            self._bloecke_weiter()
            return
        bloecke, sa = ce.bloecke_vorschlagen(self.fmt)
        self.satzart_spalte = sa
        if self.alt and (self.alt.get("aufbau") or {}).get("art") == "bloecke":
            # gespeicherte Typen/Anfangsregeln, wo die Starts zusammenpassen, bevorzugen
            alt_b = list(self.alt.get("bloecke") or [])
            if len(alt_b) == len(bloecke):
                for i, b in enumerate(bloecke):
                    if alt_b[i].get("typ"):
                        b["typ"] = alt_b[i]["typ"]
                    if alt_b[i].get("anfang"):
                        b["anfang"] = list(alt_b[i]["anfang"])
                        b["ohne_anfang"] = False
                    if alt_b[i].get("marker"):
                        b["marker"] = alt_b[i]["marker"]
                    if "wiederholend" in alt_b[i]:
                        b["wiederholend"] = bool(alt_b[i]["wiederholend"])
            if (self.alt.get("aufbau") or {}).get("satzart_spalte"):
                self.satzart_spalte = self.alt["aufbau"]["satzart_spalte"]
        self.t_block.setzen(self._csv_zeilen(), bloecke)
        self.box_anfang.satzart_spalte = self.satzart_spalte
        self._bloecke_init = True
        if bloecke:
            self.t_block.selectRow(max(0, int(bloecke[0].get("start") or 1) - 1))
        self._block_anzeigen(0)
        self._bloecke_weiter()

    def _block_zuweisen(self, typ: str) -> None:
        self.t_block.zuweisen(typ)
        self._bloecke_geaendert()

    def _block_anzeigen(self, i: int) -> None:
        if i < 0 or i >= len(self.t_block.bloecke):
            self.box_anfang.zeigen(None, self.satzart_spalte)
            return
        self.box_anfang.zeigen(self.t_block.bloecke[i], self.satzart_spalte)

    def _bloecke_geaendert(self) -> None:
        self.t_block.setzen(self._csv_zeilen(), self.t_block.bloecke)
        self._block_anzeigen(self.t_block.aktueller_block_index())
        self._bloecke_weiter()

    def _bloecke_ohne_anfang(self) -> list[dict]:
        aus = []
        for b in self.t_block.bloecke:
            if not (b.get("anfang") or []) or b.get("ohne_anfang"):
                aus.append(b)
        return aus

    def _bloecke_weiter(self) -> None:
        ok = bool(self.t_block.bloecke) and not self._bloecke_ohne_anfang()
        n_w = sum(1 for b in self.t_block.bloecke if b.get("wiederholend") or b.get("typ") == "positionen")
        ok = ok and n_w == 1
        if getattr(self, "b_weiter", None) and self.stapel.currentIndex() == 7:
            self.b_weiter.setEnabled(ok)

    def _spalten_je_block_laden(self) -> None:
        bloecke = self.t_block.bloecke
        zeilen = self._csv_zeilen()
        if not getattr(self.spalten_seite, "felder", None) or not self.spalten_seite.felder:
            felder: dict[int, dict[int, str]] = {}
            for i, b in enumerate(bloecke):
                kopf = list(b.get("kopf") or [])
                daten = [r for _n, r in (b.get("daten") or [])]
                if kopf:
                    zu = ce.spalten_vorschlagen(kopf, daten)
                    # im Positionsblock Positionsfelder bevorzugen, im Kopf Kopffelder
                    pf = ce.positionsfelder()
                    if b.get("typ") == "positionen" or b.get("wiederholend"):
                        zu = {f: s for f, s in zu.items() if f in pf or f in ("steuer",)}
                    else:
                        zu = {f: s for f, s in zu.items() if f not in pf}
                    sp_zu: dict[int, str] = {}
                    for f, s in zu.items():
                        if s in kopf:
                            sp_zu[kopf.index(s)] = f
                    felder[i] = sp_zu
            self.spalten_seite.setzen(zeilen, bloecke, felder)
        else:
            self.spalten_seite.setzen(zeilen, bloecke)
        self.b_weiter.setEnabled(True)

    def _bloecke_seite_bauen(self) -> None:
        if not self.fmt:
            return
        zu = self.zuordnung()
        alt = self.alt if (self.alt or {}).get("aufbau", {}).get("art") == "bloecke" else None
        if alt:
            self.bloecke = ce.bloecke_schneiden_zuordnung(self.fmt, zu, alt)
        else:
            self.bloecke = ce.bloecke_schneiden_zuordnung(self.fmt, zu)
        typen_fest = [
            ("kopf", _("Kopf")),
            ("positionen", _("Positionen")),
            ("summen", _("Summen")),
            ("lieferung", _("Lieferung")),
            ("zahlung", _("Zahlung")),
        ]
        self.block_typ = {}
        self.block_marker_edit: dict[int, QLineEdit] = {}
        t = self.t_bloecke_neu
        t.blockSignals(True)
        t.setRowCount(len(self.bloecke))
        alt_bloecke = list((alt or {}).get("bloecke") or [])
        for i, b in enumerate(self.bloecke):
            typ = b.get("typ") or ce.typ_vorschlag(b.get("kopf") or [])
            if not typ and i < len(alt_bloecke):
                typ = str(alt_bloecke[i].get("typ") or typ)
            if not typ:
                typ = "kopf"
            b["typ"] = typ
            if i not in self.block_wiederholend:
                if i < len(alt_bloecke) and "wiederholend" in alt_bloecke[i]:
                    self.block_wiederholend[i] = bool(alt_bloecke[i]["wiederholend"])
                else:
                    self.block_wiederholend[i] = typ == "positionen"
            if i not in self.block_marker:
                if i < len(alt_bloecke) and alt_bloecke[i].get("marker"):
                    self.block_marker[i] = str(alt_bloecke[i]["marker"])
                elif b.get("marker_wort"):
                    self.block_marker[i] = str(b.get("marker_wort") or "")
                else:
                    treffer = next(
                        (x for x in alt_bloecke if x.get("typ") == typ and x.get("marker")), None
                    )
                    self.block_marker[i] = str((treffer or {}).get("marker") or "")
            t.setItem(i, 0, QTableWidgetItem(str(b.get("start") or "")))
            cb = QComboBox()
            cb.setEditable(True)
            for code, text in typen_fest:
                cb.addItem(text, code)
            j = cb.findData(typ)
            if j >= 0:
                cb.setCurrentIndex(j)
            else:
                cb.addItem(typ, typ)
                cb.setCurrentIndex(cb.findData(typ))
            cb.currentIndexChanged.connect(lambda *_a, n=i: self._block_typ_seite_geaendert(n))
            cb.editTextChanged.connect(lambda *_a, n=i: self._block_typ_seite_geaendert(n))
            t.setCellWidget(i, 1, cb)
            self.block_typ[i] = cb
            ed = QLineEdit(self.block_marker.get(i) or "")
            ed.setPlaceholderText(_("z. B. #Kopf"))
            ed.setMinimumHeight(40)
            ed.textChanged.connect(lambda txt, n=i: self._block_marker_geaendert(n, txt))
            t.setCellWidget(i, 2, ed)
            self.block_marker_edit[i] = ed
            t.setItem(i, 3, QTableWidgetItem(", ".join(c for c in (b.get("kopf") or []) if c)))
            # default fields: assigned columns that appear in this header
            if i not in self.block_felder:
                namen = {ce._norm(c) for c in (b.get("kopf") or [])}
                felder = {f for f, s in zu.items() if ce._norm(s) in namen}
                if alt:
                    for ab in alt_bloecke:
                        if ab.get("typ") == typ:
                            felder |= {
                                f
                                for f, d in (ab.get("felder") or {}).items()
                                if isinstance(d, dict) and d.get("spalte")
                            }
                self.block_felder[i] = felder
        t.blockSignals(False)
        t.resizeColumnsToContents()
        if self.bloecke and t.currentRow() < 0:
            t.selectRow(0)
        self._block_auswahl_geaendert()
        self._block_pruefen()

    def _block_typ_seite_geaendert(self, i: int) -> None:
        cb = self.block_typ.get(i)
        if not cb or i >= len(self.bloecke):
            return
        typ = cb.currentData() or cb.currentText().strip()
        self.bloecke[i]["typ"] = typ
        if typ == "positionen" and i not in self.block_wiederholend:
            self.block_wiederholend[i] = True
        self._block_pruefen()

    def _block_marker_geaendert(self, i: int, txt: str) -> None:
        self.block_marker[i] = txt
        self._block_pruefen()

    def _block_wiederholend_geaendert(self, an: bool) -> None:
        i = self.t_bloecke_neu.currentRow()
        if i < 0:
            return
        self.block_wiederholend[i] = an
        self._block_pruefen()

    def _block_auswahl_geaendert(self) -> None:
        i = self.t_bloecke_neu.currentRow()
        while self.lay_block_felder.count():
            item = self.lay_block_felder.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._block_feld_boxen: dict[str, QCheckBox] = {}
        if i < 0 or i >= len(self.bloecke):
            return
        self.c_wiederholend.blockSignals(True)
        self.c_wiederholend.setChecked(bool(self.block_wiederholend.get(i)))
        self.c_wiederholend.blockSignals(False)
        zu = self.zuordnung()
        belegt = self.block_felder.get(i) or set()
        for f, anz, *_r in ce.FELDER:
            if f not in zu and f not in belegt:
                continue
            box = QCheckBox(_(anz) + (f" ({zu[f]})" if f in zu else ""))
            box.setChecked(f in belegt)
            box.toggled.connect(lambda an, feld=f: self._block_feld_toggeln(feld, an))
            self.lay_block_felder.addWidget(box)
            self._block_feld_boxen[f] = box

    def _block_feld_toggeln(self, feld: str, an: bool) -> None:
        i = self.t_bloecke_neu.currentRow()
        if i < 0:
            return
        s = self.block_felder.setdefault(i, set())
        if an:
            s.add(feld)
        else:
            s.discard(feld)
        self._block_pruefen()

    def _block_pruefen(self) -> tuple[bool, str]:
        texte: list[str] = []
        n_w = sum(1 for i in range(len(self.bloecke)) if self.block_wiederholend.get(i))
        if n_w != 1:
            texte.append(_("Es muss genau einen wiederholenden Block (Positionen) geben."))
        pf = {f for f in ce.positionsfelder() if not str(f).endswith("_kontrolle")}
        for i in range(len(self.bloecke)):
            if self.block_wiederholend.get(i):
                continue
            falsch = (self.block_felder.get(i) or set()) & pf
            if falsch:
                texte.append(
                    _("Positionsfelder dürfen nur im wiederholenden Block liegen ({t}).").format(
                        t=", ".join(sorted(falsch))
                    )
                )
        platz = (self._textzeile() or {}).get("platzhalter") or "#LEER"
        zu_namen = {ce._norm(s) for s in self.zuordnung().values() if s}
        for i, m in self.block_marker.items():
            m = (m or "").strip()
            if not m:
                continue
            from .. import csv_bloecke

            if csv_bloecke.name_norm(m) == csv_bloecke.name_norm(platz):
                texte.append(
                    _(
                        "„{p}“ bleibt für gewollte Leerzeilen reserviert und kann kein Marker sein."
                    ).format(p=platz)
                )
            elif csv_bloecke.name_norm(m) in zu_namen:
                texte.append(_("Hinweis: Der Marker „{m}“ gleicht einem Spaltennamen.").format(m=m))
        in_bloecken: dict[str, int] = {}
        for i in range(len(self.bloecke)):
            for f in self.block_felder.get(i) or set():
                if f in ce.FELD and ce.FELD[f][2] == "kopf":
                    in_bloecken[f] = in_bloecken.get(f, 0) + 1
        mehr = [ce.FELD[f][1] for f, n in in_bloecken.items() if n > 1]
        if mehr:
            texte.append(
                _(
                    "Hinweis: Kopffeld in mehreren Blöcken wird verglichen, Abweichung → Zu prüfen ({t})."
                ).format(t=", ".join(mehr))
            )
        # warnings vs errors: name clash and comparison hint are warnings (still allowed)
        fehler = [x for x in texte if not x.startswith("Hinweis:")]
        self.l_block_fehler.setText(" ".join(texte))
        self.l_block_fehler.setVisible(bool(texte))
        self.l_block_fehler.setObjectName("warn" if fehler else "hinweis")
        self.l_block_fehler.setStyleSheet("")
        self.l_block_fehler.style().unpolish(self.l_block_fehler)
        self.l_block_fehler.style().polish(self.l_block_fehler)
        ok = not fehler and bool(self.bloecke)
        if getattr(self, "b_weiter", None) and self.stapel.currentIndex() == 7:
            self.b_weiter.setEnabled(ok)
        return ok, " ".join(fehler)

    def _bloecke_fuer_profil(self) -> list[dict]:
        aus = []
        for i, roh in enumerate(self.bloecke):
            typ = (
                (self.block_typ[i].currentData() or self.block_typ[i].currentText().strip())
                if i in self.block_typ
                else roh.get("typ") or ce.typ_vorschlag(roh.get("kopf") or [])
            )
            aus.append(
                {
                    **roh,
                    "typ": typ,
                    "wiederholend": bool(self.block_wiederholend.get(i, typ == "positionen")),
                    "marker": (self.block_marker.get(i) or "").strip(),
                    "kopf": list(roh.get("kopf") or []),
                    "felder_wahl": set(self.block_felder.get(i) or []),
                }
            )
        return aus

    def _folge(self) -> list[tuple[int, str]]:
        """Seitenindex und Schrittname. Bei Blöcken: Blöcke festlegen, dann Spalten je Block."""
        if self.art == "bloecke":
            return [
                (0, "Datei"),
                (1, "Format"),
                (7, "Blöcke festlegen"),
                (8, "Spalten je Block"),
                (3, "Textzeilen"),
                (4, "Darstellung"),
                (5, "Probe"),
                (6, "Fertig"),
            ]
        return [
            (0, "Datei"),
            (1, "Format"),
            (2, "Vorschau"),
            (3, "Textzeilen"),
            (4, "Darstellung auf der Rechnung"),
            (5, "Probe"),
            (6, "Fertig"),
        ]

    def _schritte_anpassen(self) -> None:
        namen = [_(n) for _st, n in self._folge()]
        alt = self.schritte
        eltern = alt.parent()
        lay = eltern.layout() if eltern is not None else None
        neu = Schritte(self.c, namen)
        if lay is not None:
            i = lay.indexOf(alt)
            lay.insertWidget(max(0, i), neu)
            alt.setParent(None)
            alt.deleteLater()
        self.schritte = neu

    def gehe(self, i: int) -> None:
        folge = self._folge()
        n = len(folge)
        self.i = max(0, min(n - 1, i))
        stapel_i, _name = folge[self.i]
        self.stapel.setCurrentIndex(stapel_i)
        if getattr(self, "schritte", None):
            self.schritte.setzen(self.i)
        self.b_zurueck.setEnabled(0 < self.i < n - 1)
        self.b_weiter.setText(_("Fertig") if self.i == n - 1 else _("Weiter"))
        self.l_fuss.setText(_("Schritt {n} von {m}").format(n=self.i + 1, m=n))
        self.betreten(stapel_i)

    def _leer_felder(self) -> list[str]:
        aus = ["BT-129", "BT-146"]
        if getattr(self, "c_leer_text", None) and self.c_leer_text.isChecked():
            aus.append("text")
        elif not getattr(self, "c_leerzeilen", None):
            aus.append("text")
        return aus

    def _seite_textzeilen(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Kommentar- und Leerzeilen"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Kommt in der CSV Text oder eine gewollte Leerzeile ohne Menge und Preis vor? "
                    "Dann legen wir fest, woran Fakturafalter das erkennt. 0 und 0,00 gelten als leer."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.c_kommentare = QCheckBox(_("Kommentarzeilen sind zu erwarten"))
        self.c_kommentare.setChecked(True)
        self.c_leerzeilen = QCheckBox(_("Gewollte Leerzeilen sind zu erwarten"))
        self.c_leerzeilen.setChecked(True)
        v.addWidget(self.c_kommentare)
        v.addWidget(self.c_leerzeilen)
        v.addWidget(lbl(_("Damit eine Zeile als Kommentar oder Leerzeile gilt, müssen leer sein:")))
        self.c_leer_menge = QCheckBox(_("Menge"))
        self.c_leer_menge.setChecked(True)
        self.c_leer_menge.setEnabled(False)
        self.c_leer_preis = QCheckBox(_("Preis"))
        self.c_leer_preis.setChecked(True)
        self.c_leer_preis.setEnabled(False)
        self.c_leer_text = QCheckBox(_("Text / Bezeichnung (für eine Leerzeile)"))
        self.c_leer_text.setChecked(True)
        v.addWidget(self.c_leer_menge)
        v.addWidget(self.c_leer_preis)
        v.addWidget(self.c_leer_text)
        self.l_platz_zjp = lbl(_("Platzhalter für eine gewollte Leerzeile (optional)"))
        v.addWidget(self.l_platz_zjp)
        self.f_platz_zjp = QLineEdit("#LEER")
        self.f_platz_zjp.setMinimumHeight(48)
        v.addWidget(self.f_platz_zjp)
        self.f_preis_ohne = _auswahl(
            (
                ("pruefen", "Zu prüfen (Standard)"),
                ("eins", "Menge 1 setzen"),
                ("kommentar", "Als Kommentarzeile (nur Text, nicht in der Summe)"),
            ),
            "pruefen",
            _("Preis vorhanden, Menge leer oder 0"),
        )
        v.addWidget(lbl(_("Wenn ein Preis steht, die Menge aber leer oder 0 ist")))
        v.addWidget(self.f_preis_ohne)
        v.addWidget(
            lbl(_("Vorschau: so werden die Zeilen der Datei erkannt"), "titel", umbruch=True)
        )
        self.t_tz_vorschau = QTableWidget(0, 3)
        self.t_tz_vorschau.setHorizontalHeaderLabels([_("Zeile"), _("Erkennung"), _("Inhalt")])
        self.t_tz_vorschau.verticalHeader().setVisible(False)
        self.t_tz_vorschau.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.t_tz_vorschau.setMinimumHeight(180)
        v.addWidget(self.t_tz_vorschau, 1)
        for wdg in (
            self.c_kommentare,
            self.c_leerzeilen,
            self.c_leer_text,
            self.f_platz_zjp,
            self.f_preis_ohne,
        ):
            if isinstance(wdg, QCheckBox):
                wdg.toggled.connect(self._textzeilen_vorschau_fuellen)
            elif isinstance(wdg, QLineEdit):
                wdg.textChanged.connect(lambda *_a: self._textzeilen_vorschau_fuellen())
            else:
                wdg.currentIndexChanged.connect(lambda *_a: self._textzeilen_vorschau_fuellen())
        # Werte aus vorhandenem Profil
        alt_tz = ((self.alt or {}).get("aufbau") or {}).get("textzeile") or {}
        if alt_tz.get("platzhalter") is not None:
            self.f_platz_zjp.setText(str(alt_tz.get("platzhalter")))
        if (
            alt_tz.get("preis_ohne_menge")
            and self.f_preis_ohne.findData(alt_tz["preis_ohne_menge"]) >= 0
        ):
            self.f_preis_ohne.setCurrentIndex(
                self.f_preis_ohne.findData(alt_tz["preis_ohne_menge"])
            )
        if getattr(self, "box_text", None):
            self.box_text.setParent(w)
            # nach der Einleitung, vor den weiteren Optionen
            v.insertWidget(2, self.box_text)
            self.box_text.setVisible(True)
            # Platzhalter steht bereits in box_text – nicht zweimal anbieten.
            self.l_platz_zjp.setVisible(False)
            self.f_platz_zjp.setVisible(False)
            self.f_platz.textChanged.connect(self.f_platz_zjp.setText)
        return w

    def _textzeilen_vorschau_fuellen(self) -> None:
        from .. import csv_bloecke, csv_zeilen

        t = self.t_tz_vorschau
        if not self.fmt or not getattr(t, "setRowCount", None):
            return
        z = self.zuordnung()
        p = self.profil() if z.get("BT-1") else None
        if not p:
            t.setRowCount(0)
            return
        tz = csv_bloecke.textzeile_konfig(p)
        # Platzhalter aus diesem Schritt, falls der Vorschau-Schritt den anderen noch führt
        if getattr(self, "f_platz_zjp", None):
            tz["platzhalter"] = self.f_platz_zjp.text()
        pos, kopf = (
            (p.get("felder") or {}).get("position") or {},
            (p.get("felder") or {}).get("kopf") or {},
        )
        namen = {
            "position": _("Position"),
            "text": _("Kommentarzeile"),
            "leer": _("Leerzeile"),
            "skip": _("wird ignoriert"),
            "preis_ohne_menge": _("Preis ohne Menge"),
            "marker": _("Marker"),
            "kopfzeile": _("Kopfzeile"),
        }
        if self.art == "bloecke":
            try:
                bloecke = csv_bloecke.schneiden_profil(
                    [self.fmt.kopf] + list(self.fmt.zeilen or []), 1, p
                )
            except Exception:
                bloecke = []
            wieder = csv_bloecke.wiederholender_typ(p)
            zeilen_info: list[tuple[int, dict, str]] = []
            for bl in bloecke:
                typ = str(bl.get("typ") or csv_bloecke.typ_fuer(bl["kopf"], p) or "")
                if typ != wieder and typ != "positionen":
                    continue
                for nr, werte in bl.get("daten") or []:
                    row = dict(zip(bl.get("kopf") or [], werte))
                    zeilen_info.append((nr, row, typ))
            t.setRowCount(min(len(zeilen_info), 40))
            for i, (nr, row, typ) in enumerate(zeilen_info[:40]):
                art = csv_zeilen.erkennen(
                    row, pos if pos else (p.get("bloecke") or [{}])[0].get("felder") or {}, kopf, tz
                )
                # use positions fields from profile
                if not pos:
                    bdef = next(
                        (
                            b
                            for b in (p.get("bloecke") or [])
                            if b.get("typ") in (wieder, "positionen")
                        ),
                        {},
                    )
                    pos = bdef.get("felder") or {}
                    art = csv_zeilen.erkennen(row, pos, kopf, tz)
                if art is None:
                    kind, inhalt = "position", row.get(z.get("BT-153") or "", "") or ""
                else:
                    kind, inhalt = art[0], art[1]
                t.setItem(i, 0, QTableWidgetItem(str(nr)))
                t.setItem(i, 1, QTableWidgetItem(namen.get(kind, kind)))
                t.setItem(
                    i, 2, QTableWidgetItem(str(inhalt or row.get(z.get("BT-153") or "", "") or ""))
                )
        else:
            daten = list(self.fmt.zeilen)
            t.setRowCount(min(len(daten), 40))
            for i, werte in enumerate(daten[:40]):
                row = dict(zip(self.fmt.kopf, werte))
                art = csv_zeilen.erkennen(row, pos, kopf, tz)
                if art is None:
                    kind, inhalt = "position", row.get(z.get("BT-153") or "", "") or ""
                else:
                    kind, inhalt = art[0], art[1]
                t.setItem(i, 0, QTableWidgetItem(str(i + 2)))
                t.setItem(i, 1, QTableWidgetItem(namen.get(kind, kind)))
                t.setItem(
                    i, 2, QTableWidgetItem(str(inhalt or row.get(z.get("BT-153") or "", "") or ""))
                )
        t.resizeColumnsToContents()

    def _seite_darstellung(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Darstellung auf der Rechnung"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Hier bestimmst du, wie die Sichtseite aussieht. Die XML (ZUGFeRD/XRechnung) bleibt "
                    "unverändert. Mit Weiter werden die Vorschläge übernommen."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.c_posnr = QCheckBox(_("Positionsnummer auf der Sichtseite zeigen"))
        self.c_posnr.setChecked(True)
        v.addWidget(self.c_posnr)
        self.c_menge_exakt = QCheckBox(_("Menge exakt aus der CSV zeigen (z. B. 40,00)"))
        self.c_menge_exakt.setChecked(True)
        v.addWidget(self.c_menge_exakt)
        self.f_einheit_sicht = _auswahl(
            (("kurz", "Kurzform (Stk., Std., …)"), ("csv", "Einheit wie in der CSV anzeigen")),
            "kurz",
            _("Einheit auf der Sichtseite"),
        )
        v.addWidget(lbl(_("Einheit auf der Sichtseite")))
        v.addWidget(self.f_einheit_sicht)
        self.c_einheit_fehlt_stueck = QCheckBox(_("Fehlende Einheit = Stück verwenden"))
        self.c_einheit_fehlt_stueck.setChecked(False)
        v.addWidget(self.c_einheit_fehlt_stueck)
        v.addWidget(
            lbl(
                _(
                    "Positionen mit Menge und Preis, aber ohne Einheit, erhalten Stück (H87). "
                    "Im Protokoll erscheint der Hinweis „Einheit fehlte, Stück angenommen“ – kein Prüffall."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self.c_kommentar_ohne = QCheckBox(_("Bezeichnungen bei Kommentarzeilen ausblenden"))
        self.c_kommentar_ohne.setChecked(False)
        v.addWidget(self.c_kommentar_ohne)
        v.addWidget(
            lbl(
                _(
                    "PDF-Bezeichnung je Spalte (Pflichtfelder können nur umbenannt, nicht ausgeblendet werden)"
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self.t_darstellung = QTableWidget(0, 3)
        self.t_darstellung.setHorizontalHeaderLabels(
            [_("Feld"), _("Bezeichnung auf der PDF"), _("Auf PDF zeigen")]
        )
        self.t_darstellung.verticalHeader().setVisible(False)
        self.t_darstellung.setMinimumHeight(160)
        v.addWidget(self.t_darstellung, 1)
        v.addWidget(lbl(_("Vorschau der Positionszeile"), "titel"))
        self.l_darst_vorschau = lbl("", "hinweis", umbruch=True)
        v.addWidget(self.l_darst_vorschau)
        v.addWidget(knopf(_("Sichtseite ansehen…"), klick=self._sichtseite))
        for wdg in (
            self.c_posnr,
            self.c_menge_exakt,
            self.c_einheit_fehlt_stueck,
            self.c_kommentar_ohne,
            self.f_einheit_sicht,
        ):
            if isinstance(wdg, QCheckBox):
                wdg.toggled.connect(self._darstellung_aktualisieren)
            else:
                wdg.currentIndexChanged.connect(lambda *_a: self._darstellung_aktualisieren())
        alt_s = (self.alt or {}).get("sicht") or {}
        if "positionsnummer" in alt_s:
            self.c_posnr.setChecked(bool(alt_s["positionsnummer"]))
        if "menge_exakt" in alt_s:
            self.c_menge_exakt.setChecked(bool(alt_s["menge_exakt"]))
        if alt_s.get("einheit") and self.f_einheit_sicht.findData(alt_s["einheit"]) >= 0:
            self.f_einheit_sicht.setCurrentIndex(self.f_einheit_sicht.findData(alt_s["einheit"]))
        if "kommentar_ohne_bezeichnungen" in alt_s:
            self.c_kommentar_ohne.setChecked(bool(alt_s["kommentar_ohne_bezeichnungen"]))
        alt_a = (self.alt or {}).get("aufbau") or {}
        self.c_einheit_fehlt_stueck.setChecked(bool(alt_a.get("einheit_fehlt_stueck")))
        return w

    PFLICHT_SICHT = ("BT-153", "BT-129", "BT-146", "steuer", "BT-130")
    FELD_TITEL = {
        "BT-126": "Pos",
        "BT-153": "Bezeichnung",
        "BT-129": "Menge",
        "BT-130": "Einh.",
        "BT-146": "Einzelpreis",
        "steuer": "USt",
        "gesamt": "Gesamt",
        "BT-155": "Art.-Nr.",
        "BT-154": "Beschreibung",
    }

    def _darstellung_tabelle_bauen(self) -> None:
        z = self.zuordnung()
        keys = [
            k
            for k in (
                "BT-126",
                "BT-153",
                "BT-155",
                "BT-154",
                "BT-129",
                "BT-130",
                "BT-146",
                "steuer",
            )
            if z.get(k) or k in ("BT-153", "BT-129", "BT-146", "steuer", "BT-130")
        ]
        # nur zugeordnete, Pflicht immer
        keys = [k for k in keys if z.get(k) or k in self.PFLICHT_SICHT]
        alt = ((self.alt or {}).get("sicht") or {}).get("felder") or {}
        self.t_darstellung.setRowCount(len(keys))
        self._darst_felder = keys
        for i, k in enumerate(keys):
            self.t_darstellung.setItem(i, 0, QTableWidgetItem(_(self.FELD_TITEL.get(k, k))))
            titel = QLineEdit((alt.get(k) or {}).get("titel") or self.FELD_TITEL.get(k, k))
            titel.setMinimumHeight(36)
            titel.textChanged.connect(lambda *_a: self._darstellung_aktualisieren())
            self.t_darstellung.setCellWidget(i, 1, titel)
            box = QCheckBox()
            sichtbar = (alt.get(k) or {}).get("sichtbar", True)
            if k == "BT-126":
                sichtbar = bool(self.c_posnr.isChecked())
            box.setChecked(bool(sichtbar))
            box.setEnabled(k not in self.PFLICHT_SICHT)
            box.toggled.connect(lambda *_a: self._darstellung_aktualisieren())
            self.t_darstellung.setCellWidget(i, 2, box)
        self.t_darstellung.resizeColumnsToContents()

    def _sicht_aus_seite(self) -> dict:
        felder = {}
        for i, k in enumerate(getattr(self, "_darst_felder", []) or []):
            titel = self.t_darstellung.cellWidget(i, 1)
            box = self.t_darstellung.cellWidget(i, 2)
            d = {}
            if titel and titel.text().strip() and titel.text().strip() != self.FELD_TITEL.get(k, k):
                d["titel"] = titel.text().strip()
            if box is not None and k not in self.PFLICHT_SICHT:
                d["sichtbar"] = box.isChecked()
            if d:
                felder[k] = d
        return {
            "positionsnummer": self.c_posnr.isChecked() if getattr(self, "c_posnr", None) else True,
            "einheit": self.f_einheit_sicht.currentData()
            if getattr(self, "f_einheit_sicht", None)
            else "kurz",
            "menge_exakt": self.c_menge_exakt.isChecked()
            if getattr(self, "c_menge_exakt", None)
            else True,
            "kommentar_ohne_bezeichnungen": self.c_kommentar_ohne.isChecked()
            if getattr(self, "c_kommentar_ohne", None)
            else False,
            "felder": felder,
        }

    def _darstellung_aktualisieren(self) -> None:
        if not getattr(self, "l_darst_vorschau", None):
            return
        sicht = self._sicht_aus_seite()
        teile = []
        teile.append(
            _("Pos {n}").format(n="1")
            if sicht.get("positionsnummer", True)
            else _("ohne Positionsnummer")
        )
        teile.append(_("Menge {m}").format(m="40,00" if sicht.get("menge_exakt", True) else "40"))
        teile.append(
            _("Einheit {e}").format(e="Stück" if sicht.get("einheit") == "csv" else "Stk.")
        )
        if (
            getattr(self, "c_einheit_fehlt_stueck", None)
            and self.c_einheit_fehlt_stueck.isChecked()
        ):
            teile.append(_("fehlende Einheit = Stück"))
        self.l_darst_vorschau.setText(" · ".join(teile))

    # ------------------------------------------------------------------ 4 Probe

    def _seite_probe(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Probe mit deiner Datei"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "So würde Fakturafalter die Rechnungen lesen. Es wird nichts erzeugt oder verschoben."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.t_probe = self._probe_tabelle()
        v.addWidget(self.t_probe, 1)
        self.l_probe = lbl("", "hinweis", umbruch=True)
        v.addWidget(self.l_probe)
        v.addWidget(knopf(_("Sichtseite ansehen…"), klick=self._sichtseite))
        return w

    def _satzarten_map(self) -> dict[str, str]:
        """Zusätzliche Satzart-Kennwerte aus dem Format-Schritt (außer K/P)."""
        aus: dict[str, str] = {}
        tab = getattr(self, "t_satzarten", None)
        if tab is None:
            return aus
        for i in range(tab.rowCount()):
            w = tab.item(i, 0)
            b = tab.cellWidget(i, 1)
            wert = (w.text() if w else "").strip()
            art = b.currentData() if b is not None else ""
            if wert and art:
                aus[wert] = art
        return aus

    def profil(self) -> dict:
        z = self.zuordnung()
        steuer = {w: b.currentData() for w, b in self.steuer_wahl.items()}
        if not steuer and z.get("steuer"):
            try:
                steuer = {w: "prüfen" for w in set(ce.spalte_in_datei(self.fmt, z["steuer"])) if w}
            except ValueError:
                steuer = {}
        try:
            eh = (
                ce.einheiten_vorschlag(ce.spalte_in_datei(self.fmt, z["BT-130"]))
                if z.get("BT-130") and self.fmt
                else {}
            )
        except ValueError:
            eh = {}
        if self.art == "bloecke":
            bloecke = list(getattr(self, "t_block", None).bloecke if getattr(self, "t_block", None) else [])
            if not bloecke and self.bloecke:
                bloecke = self._bloecke_fuer_profil()
            zu_je: dict[str, dict[str, str]] = {}
            if getattr(self, "spalten_seite", None):
                zu_je = self.spalten_seite.zuordnung_je()
            p = ce.profil_bauen_bloecke(
                self.name.text().strip() or "csv",
                self.datei,
                self.fmt,
                bloecke,
                zu_je,
                steuer,
                eh,
                self._textzeile(),
                ce.kundenstamm_vorschlag(self.haupt.k) if z.get("kundennummer") else None,
                self.satzart_spalte,
            )
        else:
            p = ce.profil_bauen(
                self.name.text().strip() or "csv",
                self.datei,
                self.fmt,
                z,
                steuer,
                eh,
                ce.kundenstamm_vorschlag(self.haupt.k) if z.get("kundennummer") else None,
                self._textzeile(),
            )
            if self.art == "satzart":
                spalte = next(
                    (
                        s
                        for s in (self.fmt.kopf or [])
                        if ce._norm(s) in ("satzart", "satztyp", "zeilentyp", "recordtype")
                    ),
                    "Satzart",
                )
                p["aufbau"]["art"] = "satzart"
                p["aufbau"]["satzart_spalte"] = spalte
                werte = {w.strip() for w in ce.spalte(self.fmt, spalte) if w.strip()}
                if "K" in werte:
                    p["aufbau"]["kopf"] = "K"
                if "P" in werte:
                    p["aufbau"]["position"] = "P"
                kenn = self._satzarten_map()
                if kenn:
                    p["aufbau"]["satzarten"] = kenn
        if self.art == "zeile_je_position" and getattr(self, "c_posnr", None):
            p["sicht"] = self._sicht_aus_seite()
            if getattr(self, "f_platz_zjp", None):
                p.setdefault("aufbau", {}).setdefault("textzeile", {})
                p["aufbau"]["textzeile"]["platzhalter"] = self.f_platz_zjp.text()
        if self.alt:  # Handprofil: eigene Zusätze (Ausgabe, Erkennung …) behalten
            p = {**{k: v for k, v in self.alt.items() if not k.startswith("_")}, **p}
            if (self.alt.get("datei") or {}).get("muster"):
                p["datei"]["muster"] = self.alt["datei"]["muster"]
            if self.art == "zeile_je_position" and getattr(self, "c_posnr", None):
                p["sicht"] = self._sicht_aus_seite()
        if getattr(self, "c_einheit_fehlt_stueck", None):
            auf = p.setdefault("aufbau", {})
            if self.c_einheit_fehlt_stueck.isChecked():
                auf["einheit_fehlt_stueck"] = True
            else:
                auf.pop("einheit_fehlt_stueck", None)
        return p

    def _probe(self) -> None:
        try:
            erg = ce.probe_csv(self.datei, self.profil(), self.haupt.k)
        except Exception as e:  # noqa: BLE001 – Probe darf nie den Assistenten abbrechen
            self.t_probe.setRowCount(0)
            self.l_probe.setText(_("Probe fehlgeschlagen: {f}").format(f=e))
            self.l_probe.setObjectName("warn")
            return
        self._probe_zeigen(self.t_probe, self.l_probe, erg)
        from .. import adapter_csv

        anderes = adapter_csv.eingang_anderes_profil(
            Path(self.datei), self.profil(), self.haupt.k.csv_profile
        )
        if anderes:
            extra = _(
                "Im Eingang würde derzeit das Profil „{n}“ greifen, nicht dieses. "
                "Es steht weiter oben und passt ebenfalls. Reihenfolge in den Einstellungen prüfen."
            ).format(n=anderes)
            self.l_probe.setText((self.l_probe.text() + " " + extra).strip())
            self.l_probe.setObjectName("warn")
            self.l_probe.setStyleSheet("")
            self.l_probe.style().unpolish(self.l_probe)
            self.l_probe.style().polish(self.l_probe)

    def _sichtseite(self) -> None:
        """Probe-Rechnung als Sichtseite öffnen (temporäres PDF, nur lesen)."""
        import tempfile

        from .. import adapter_csv, rechnen, sicht

        try:
            rs = adapter_csv.lesen(Path(self.datei), self.profil(), self.haupt.k)
            if not rs:
                self.toast("fehler", _("Keine Rechnung lesbar."))
                return
            r = rs[0]
            rechnen.berechnen(r)
            pdf = sicht.erzeugen(r)
            z = Path(tempfile.mkdtemp(prefix="fakturafalter-probe-")) / "sichtseite.pdf"
            z.write_bytes(pdf)
            aktionen.oeffnen(z)
        except Exception as e:  # noqa: BLE001
            self.toast("fehler", _("Sichtseite nicht erzeugbar"), str(e))

    # ------------------------------------------------------------------ 5 Fertig
    def _seite_fertig(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Fertig – die CSV ist eingerichtet."), "titel", umbruch=True))
        kt, kv = karte()
        z = QHBoxLayout()
        z.addWidget(Zustand(self.c, "erkannt", 28), 0, Qt.AlignmentFlag.AlignTop)
        self.l_fertig = lbl("", umbruch=True)
        z.addWidget(self.l_fertig, 1)
        kv.addLayout(z)
        v.addWidget(kt)
        v.addWidget(
            lbl(
                _(
                    "Lege ab jetzt die CSV in den Eingang. Wenn du zusätzlich das Original-PDF als Sichtseite "
                    "nutzen willst, hake das unter Einstellungen → Eingang & Vorlagen an."
                ),
                "sub",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addWidget(
            knopf(_("Profilordner öffnen"), klick=lambda: aktionen.oeffnen(self.haupt.k.basis))
        )
        h.addStretch(1)
        v.addLayout(h)
        v.addStretch(1)
        return w

    def speichern(self) -> Path | None:
        k = self.haupt.k
        p = self.profil()
        if self.alt and self.alt.get("_datei"):
            ziel = Path(self.alt["_datei"])
            if ziel.suffix.lower() == ".json":
                ziel.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                ce.speichern(p, ziel)
        else:
            erst = ziel = ce.dateiname(p["profil"], Path(k.basis))
            n = 2
            while ziel.exists():
                ziel, n = erst.with_name(f"{erst.stem}-{n}.yaml"), n + 1
            ce.speichern(p, ziel)
        r = copy.deepcopy(k.roh)
        liste = list(r.get("csv_profile") or [])
        try:
            eintrag = str(ziel.resolve().relative_to(Path(k.basis).resolve()))
        except ValueError:
            eintrag = str(ziel)
        from ..konfig import csv_eintrag_datei

        def _pfad(x):
            try:
                return Path(k.pfad(csv_eintrag_datei(x))).resolve()
            except (OSError, ValueError):
                return None

        if not any(_pfad(x) == ziel.resolve() for x in liste):
            liste.append({"datei": eintrag, "aktiv": True})
        r["csv_profile"] = liste
        r["modus"] = "csv"
        if not self.haupt.einstellungen_uebernehmen(r):
            return None
        self.gespeichert = ziel
        return ziel

    # ------------------------------------------------------------------ Ablauf
    def betreten(self, i: int) -> None:
        # i ist der Seitenindex im Stapel, nicht der Schritt in der Leiste
        if i == 0:
            self.b_weiter.setEnabled(self.datei is not None)
        elif i == 1:
            self.b_weiter.setEnabled(bool(self.fmt))
        elif i == 2:
            self.b_weiter.setEnabled(not ce.fehlende_pflicht(self._alle_zuordnungen()))
        elif i == 7:
            self._bloecke_laden()
        elif i == 8:
            self._spalten_je_block_laden()
        elif i == 3:
            self.b_weiter.setEnabled(True)
            if getattr(self, "box_text", None):
                self.box_text.setVisible(True)
            self._textzeilen_vorschau_fuellen()
        elif i == 4:
            self.b_weiter.setEnabled(True)
            self._darstellung_tabelle_bauen()
            self._darstellung_aktualisieren()
        elif i == 5:
            self.b_weiter.setEnabled(True)
            self.b_weiter.setText(_("Speichern"))
            self._probe()
        else:
            self.b_weiter.setEnabled(True)
            self.l_fertig.setText(
                _("Zuordnung „{n}“ gespeichert: {p}").format(
                    n=self.name.text().strip(), p=self.gespeichert.name if self.gespeichert else ""
                )
            )

    def _weiter(self) -> None:
        folge = self._folge()
        stapel_i = folge[self.i][0] if folge else self.i
        if stapel_i == 0 and not self.name.text().strip():
            self.toast("fehler", _("Bitte einen Namen angeben."))
            return
        if stapel_i == 5 and not self.speichern():
            return
        if self.i == len(folge) - 1:
            self.accept()
            return
        self.gehe(self.i + 1)


class XmlAssistent(_Assistent):
    SCHRITTE = ("Format", "Probe", "Fertig")

    def __init__(self, haupt, eltern=None):
        super().__init__(
            haupt,
            eltern,
            _("XML einrichten"),
            _(
                "ZUGFeRD/Factur-X- und XRechnung-Dateien (CII oder UBL) liest Fakturafalter fest – "
                "eine Zuordnung ist nicht nötig."
            ),
        )
        self.datei: Path | None = None
        for s in (self._seite_format(), self._seite_probe(), self._seite_fertig()):
            self.stapel.addWidget(rollen(s))
        self.gehe(0)

    def _seite_format(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Welche XML legt deine Software ab?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Wähle eine Beispiel-XML. Erkannt werden ZUGFeRD/Factur-X und XRechnung, jeweils als CII "
                    "oder UBL."
                ),
                "sub",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addWidget(knopf(_("XML-Datei auswählen…"), primary=True, klick=self._waehlen))
        h.addStretch(1)
        v.addLayout(h)
        kt, kv = karte()
        z = QHBoxLayout()
        self.z_format = Zustand(self.c, "fehlt", 28)
        z.addWidget(self.z_format, 0, Qt.AlignmentFlag.AlignTop)
        self.l_format = lbl(_("Noch keine Datei gewählt."), umbruch=True)
        z.addWidget(self.l_format, 1)
        kv.addLayout(z)
        v.addWidget(kt)
        v.addWidget(
            lbl(
                _(
                    "Andere XML-Formate (z. B. DATEV, Lexware) werden nicht gelesen – die Datei kommt dann mit "
                    "Begründung in den Fehlerordner."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addStretch(1)
        return w

    def _waehlen(self) -> None:
        d, _f = QFileDialog.getOpenFileName(
            self, _("XML-Datei auswählen…"), str(Path.home()), _("XML-Dateien (*.xml)")
        )
        if d:
            self.datei_setzen(Path(d))

    def datei_setzen(self, datei: Path) -> None:
        self.datei = None
        try:
            _art, name = adapter_xml.erkennen(datei.read_bytes())
            adapter_xml.lesen(datei, self.haupt.k)
        except (OSError, ValueError) as e:
            self.z_format.setzen("pruefen")
            self.l_format.setText(
                _("{datei}: nicht lesbar – {grund}").format(datei=datei.name, grund=e)
            )
            self.gehe(self.i)
            return
        self.datei = datei
        self.z_format.setzen("erkannt")
        self.l_format.setText(_("{datei}: {format}").format(datei=datei.name, format=name))
        self.gehe(self.i)

    def _seite_probe(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Probe mit deiner Datei"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "So würde Fakturafalter die Rechnungen lesen. Es wird nichts erzeugt oder verschoben."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.t_probe = self._probe_tabelle()
        v.addWidget(self.t_probe, 1)
        self.l_probe = lbl("", "hinweis", umbruch=True)
        v.addWidget(self.l_probe)
        return w

    def _seite_fertig(self) -> QWidget:
        w, v = _seite()
        v.addWidget(lbl(_("Fertig – XML-Eingang ist eingeschaltet."), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Lege ab jetzt die XML in den Eingang. Fakturafalter erzeugt daraus eine ZUGFeRD-PDF und "
                    "prüft das Ergebnis. Das Original-PDF als Sichtseite hake unter Einstellungen → "
                    "Eingang & Vorlagen an."
                ),
                "sub",
                umbruch=True,
            )
        )
        v.addStretch(1)
        return w

    def betreten(self, i: int) -> None:
        self.b_weiter.setEnabled(i != 0 or self.datei is not None)
        if i == 1:
            self.b_weiter.setText(_("Einschalten"))
            self._probe_zeigen(
                self.t_probe,
                self.l_probe,
                ce.probe(adapter_xml.lesen(self.datei, self.haupt.k), self.haupt.k),
            )

    def _weiter(self) -> None:
        if self.i == 1:
            r = copy.deepcopy(self.haupt.k.roh)
            r["modus"] = "xml"
            if not self.haupt.einstellungen_uebernehmen(r):
                return
        if self.i == len(self.SCHRITTE) - 1:
            self.accept()
            return
        self.gehe(self.i + 1)
