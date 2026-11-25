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

    def __init__(self, haupt, eltern=None, profil: dict | None = None):
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
        for s in (
            self._seite_datei(),
            self._seite_format(),
            self._seite_vorschau(),
            self._seite_probe(),
            self._seite_fertig(),
        ):
            self.stapel.addWidget(rollen(s))
        self.gehe(0)

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
        if not fmt:
            return
        t = self.t_format
        t.clear()
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
            "bloecke": _("Mehrere Blöcke mit eigener Kopfzeile erkannt."),
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

    def _art_geaendert(self, *_a) -> None:
        if not self.fmt:
            return
        self._art_vorschlagen()
        self._vorschau_bauen()

    def _textzeile(self) -> dict:
        if not getattr(self, "f_textziel", None):
            return {}
        return {
            "ziel": self.f_textziel.currentData(),
            "platzhalter": self.f_platz.text(),
            "leerzeile_modus": self.f_leer_modus.currentData(),
            "verwaist": self.f_verwaist.currentData(),
            "trenner": "\n",
            "leer": ["BT-129", "BT-146", "text"],
            "text_spalte": (self.zuordnung() or {}).get("BT-153"),
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
        tv.addWidget(lbl(_("Textzeilen und Leerzeilen im Positionsblock"), "titel", umbruch=True))
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
                ("pruefen", "Rechnung nach „Zu prüfen“"),
            ),
            "BT-22",
            _("Textzeile vor der ersten Position"),
        )
        tv.addWidget(lbl(_("Textzeile vor der ersten Position")))
        tv.addWidget(self.f_verwaist)
        v.addWidget(self.box_text)
        return w

    def _vorschau_bauen(self) -> None:
        fmt = self.fmt
        if not fmt:
            return
        bloecke = self.art == "bloecke"
        if getattr(self, "box_bloecke", None):
            self.box_bloecke.setVisible(bloecke)
            self.box_text.setVisible(bloecke)
        if bloecke:
            self._bloecke_tabelle()
            self._vorschau_bauen_block()
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
        if self.art != "bloecke":
            return self.zuordnung()
        alle: dict[str, str] = {}
        for z in self.zuordnung_je.values():
            alle.update(z)
        alle.update(self.zuordnung())
        return alle

    def _zuordnung_geaendert(self, spalte: int | None) -> None:
        if spalte is not None:  # jedes Feld nur einmal: gleiches Feld an anderer Spalte lösen
            f = self.spalten[spalte].currentData()
            for j, b in enumerate(self.spalten):
                if j != spalte and f and b.currentData() == f:
                    b.blockSignals(True)
                    b.setCurrentIndex(0)
                    b.blockSignals(False)
        z = self.zuordnung()
        if self.art == "bloecke":
            b = self._aktueller_block()
            if b and b.get("typ"):
                self.zuordnung_je[b["typ"]] = dict(z)
        fehlt = ce.fehlende_pflicht(self._alle_zuordnungen())
        self.l_fehlt.setText(
            _("Noch zuordnen: {was}").format(was=", ".join(_(x) for x in fehlt)) if fehlt else ""
        )
        self.l_fehlt.setVisible(bool(fehlt))
        self._steuer_bauen(z.get("steuer"))
        eh = ce.einheiten_vorschlag(ce.spalte(self.fmt, z["BT-130"])) if z.get("BT-130") else {}
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
        werte = ce.spalte(self.fmt, spalte) if spalte else []
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

    def profil(self) -> dict:
        z = self.zuordnung()
        steuer = {w: b.currentData() for w, b in self.steuer_wahl.items()}
        if not steuer and z.get("steuer"):
            try:
                steuer = {w: "prüfen" for w in set(ce.spalte(self.fmt, z["steuer"])) if w}
            except ValueError:
                steuer = {}
        try:
            eh = ce.einheiten_vorschlag(ce.spalte(self.fmt, z["BT-130"])) if z.get("BT-130") else {}
        except ValueError:
            eh = {}
        if self.art == "bloecke":
            bloecke = []
            zu_je: dict[str, dict[str, str]] = {}
            # aktuelle Zuordnung dem sichtbaren Block zuordnen; andere Blöcke über Vorschlag
            for i, roh in enumerate(self.bloecke):
                typ = (
                    self.block_typ[i].currentData()
                    if i in self.block_typ
                    else ce.typ_vorschlag(roh.get("kopf") or [])
                )
                b = {**roh, "typ": typ}
                bloecke.append(b)
                if typ in self.zuordnung_je:
                    zu_je[typ] = dict(self.zuordnung_je[typ])
                else:
                    zu_je[typ] = ce.spalten_vorschlagen(
                        roh.get("kopf") or [], [w for _n, w in roh.get("daten") or []]
                    )
            if z:
                sichtbar = self._aktueller_block()
                if sichtbar and sichtbar.get("typ"):
                    zu_je[sichtbar["typ"]] = dict(z)
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
        if self.alt:  # Handprofil: eigene Zusätze (Ausgabe, Erkennung …) behalten
            p = {**{k: v for k, v in self.alt.items() if not k.startswith("_")}, **p}
            if (self.alt.get("datei") or {}).get("muster"):
                p["datei"]["muster"] = self.alt["datei"]["muster"]
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
        if i == 0:
            self.b_weiter.setEnabled(self.datei is not None)
        elif i == 1:
            self.b_weiter.setEnabled(bool(self.fmt))
        elif i == 2:
            self.b_weiter.setEnabled(not ce.fehlende_pflicht(self._alle_zuordnungen()))
        elif i == 3:
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
        if self.i == 0 and not self.name.text().strip():
            self.toast("fehler", _("Bitte einen Namen angeben."))
            return
        if self.i == 3 and not self.speichern():
            return
        if self.i == len(self.SCHRITTE) - 1:
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
