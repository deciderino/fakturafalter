# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Einstellungen nach Skizze 14/15: links Bereiche, rechts eine Seite mit Bezeichnung über dem Feld.

Bei großer Skalierung (schmales Fenster) wird die linke Liste zur Auswahl oben. [Abbrechen] [Speichern] unten."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import (
    __version__,
    anlernen,
    csv_einrichtung,
    nummernkreis,
    pdferkennung,
    updatepruefung,
    validierung,
)
from ..konfig import PROTOKOLL_ORDNER, UNTERORDNER, XRECHNUNG_ORDNER, gemeinsamer_ordner
from . import aktionen, autostart, daten
from .absender_form import AbsenderFormular, aus_roh, in_roh
from .bausteine import Segmente, ToastStapel, fussleiste, karte, knopf, lbl, rollen, trenner
from .texte import SPRACHEN, _

ORDNER = (
    ("eingang", "Eingang"),
    ("ausgang", "Ausgang"),
    ("erledigt", "Erledigt"),
    ("pruefen", "Zu prüfen"),
    ("fehler", "Fehler"),
)
BEREICHE = ("Allgemein", "Absender", "Eingang & Vorlagen", "Ausgabe", "Prüfung", "Ordner")
NEUER_ABSENDER = "+ Neuer Absender"


def bereich(name: str) -> int:
    """Index eines Bereichs nach Namen (Aufrufer hängen nicht an der Reihenfolge)."""
    return BEREICHE.index(name)


# Fehlertexte aus nummernkreis, die übersetzt angezeigt werden (Rest enthält Werte)
_UEBERSETZBAR = ("Prüfmuster ist leer", "Klammern { } passen nicht zusammen")

SCHMAL = 640  # darunter (logische Pixel) wird die Navigation zur Auswahl oben


def _abschnitt(v: QVBoxLayout, titel: str, hilfe: str | None = None, erste: bool = False) -> None:
    if not erste:
        v.addSpacing(8)
        v.addWidget(trenner())
    v.addWidget(lbl(titel, "titel", umbruch=True))
    if hilfe:
        v.addWidget(lbl(hilfe, "hinweis", umbruch=True))


def _seite() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(24, 20, 24, 20)
    v.setSpacing(8)
    return w, v


def _pruefen_text(n: int, ab: int, sicher: bool, an: bool) -> str:
    if sicher and an:
        return _("Sicher erkannt. Neue Rechnungen laufen ohne Nachfrage.")
    if sicher:
        return _("Sicher erkannt. Du kannst „Automatisch, ohne Nachfrage“ einschalten.")
    if n == 0:
        return _("Noch keine Rechnung ohne Korrektur. Jede angelernte Rechnung zählt.")
    return _(
        "Noch {r} Rechnungen ohne Korrektur, dann kannst du „Automatisch, ohne Nachfrage“ einschalten."
    ).format(r=ab - n)


class Einstellungen(QDialog):
    update_ergebnis = Signal(bool, object)  # „Jetzt prüfen“: (erreichbar, Neu | None) aus dem Hintergrund

    def __init__(self, haupt, bereich: int = 0):
        super().__init__(haupt)
        self.haupt = haupt
        self.c = haupt.c
        k = haupt.k
        self.roh = copy.deepcopy(k.roh)
        self.setWindowTitle(_("Einstellungen"))
        self.setObjectName("wurzel")
        self.resize(940, 820)
        self.toasts = ToastStapel(self, abstand_unten=90)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.setSpacing(0)
        self.auswahl = QComboBox()  # schmal: Bereich oben auswählen
        self.auswahl.setAccessibleName(_("Bereich"))
        for b in BEREICHE:
            self.auswahl.addItem(_(b))
        kopf = QFrame()
        kopf.setObjectName("leiste")
        kh = QHBoxLayout(kopf)
        kh.setContentsMargins(20, 10, 20, 10)
        kh.setSpacing(12)
        kh.addWidget(lbl(_("Einstellungen"), "titel"))
        kh.addWidget(self.auswahl, 1)
        aussen.addWidget(kopf)

        mitte = QWidget()
        m = QHBoxLayout(mitte)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(0)
        c = self.c
        self.nav = QListWidget()
        self.nav.setFixedWidth(210)
        self.nav.setWordWrap(True)
        self.nav.setStyleSheet(
            f"QListWidget {{ background:{c['bar']}; border:none; border-right:1px solid {c['bar_b']}; outline:0;"
            f" padding-top:8px; }}"
            f"QListWidget::item {{ min-height:48px; padding-left:16px; border:none; color:{c['fg']}; }}"
            f"QListWidget::item:selected {{ background:{c['sel']}; color:{c['fg']}; border-left:4px solid {c['acc']};"
            f" font-weight:bold; }}"
        )
        for b in BEREICHE:
            self.nav.addItem(QListWidgetItem(_(b)))
        m.addWidget(self.nav)
        self.stapel = QStackedWidget()
        m.addWidget(self.stapel, 1)
        aussen.addWidget(mitte, 1)

        self.stapel.addWidget(rollen(self._seite_allgemein()))
        self.stapel.addWidget(rollen(self._seite_absender()))
        self.vorlagen_rolle = rollen(self._seite_vorlagen())
        self.stapel.addWidget(self.vorlagen_rolle)
        self.stapel.addWidget(rollen(self._seite_ausgabe()))
        self.stapel.addWidget(rollen(self._seite_pruefung()))
        self.stapel.addWidget(rollen(self._seite_ordner()))
        self.nav.currentRowChanged.connect(self.bereich_zeigen)
        self.auswahl.currentIndexChanged.connect(self.bereich_zeigen)

        fuss, _links, self.fehler, rechts = fussleiste(c)
        self.fehler.setObjectName("warn")
        rechts.addWidget(knopf(_("Abbrechen"), klick=self.reject))
        self.b_speichern = knopf(_("Speichern"), primary=True, klick=self._speichern)
        self.b_speichern.setDefault(True)
        rechts.addWidget(self.b_speichern)
        aussen.addWidget(fuss)
        self.bereich_zeigen(bereich)
        self._breite_anpassen()

    def toast(self, art, titel, detail=""):
        return self.toasts.zeigen(self.c, art, titel, detail)

    def bereich_zeigen(self, i: int | str) -> None:
        i = bereich(i) if isinstance(i, str) else i
        i = max(0, min(len(BEREICHE) - 1, i))
        self.stapel.setCurrentIndex(i)
        for w in (self.nav, self.auswahl):
            w.blockSignals(True)
        self.nav.setCurrentRow(i)
        self.auswahl.setCurrentIndex(i)
        for w in (self.nav, self.auswahl):
            w.blockSignals(False)

    def _breite_anpassen(self) -> None:
        schmal = self.width() < SCHMAL
        self.nav.setVisible(not schmal)
        self.auswahl.setVisible(schmal)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._breite_anpassen()

    # ======================================================================== Ordner
    def _seite_ordner(self) -> QWidget:
        k = self.haupt.k
        w, v = _seite()
        einzeln = bool(self.roh.get("ordner"))
        arb = (
            k.arbeitsordner
            or gemeinsamer_ordner({s: getattr(k, s) for s, _n in UNTERORDNER})
            or Path(k.eingang).parent
        )
        _abschnitt(
            v,
            _("Arbeitsordner"),
            _(
                "Darin liegen Eingang, Ausgang, Pruefen, Fehler, Erledigt und Protokoll. "
                "Fakturafalter legt sie selbst an."
            ),
            erste=True,
        )
        h = QHBoxLayout()
        h.setSpacing(8)
        self.arbeitsordner = QLineEdit(str(arb))
        self.arbeitsordner.setObjectName("arbeitsordner")
        self.arbeitsordner.setAccessibleName(_("Arbeitsordner"))
        h.addWidget(self.arbeitsordner, 1)
        h.addWidget(
            knopf(_("Wählen…"), klick=lambda: self._waehlen(self.arbeitsordner, "Arbeitsordner"))
        )
        h.addWidget(
            knopf(
                _("Öffnen"),
                klick=lambda: aktionen.oeffnen(Path(self.arbeitsordner.text()).expanduser()),
            )
        )
        v.addLayout(h)
        v.addSpacing(8)
        v.addWidget(trenner())
        self.einzeln = QCheckBox(_("Ordner einzeln festlegen"))
        self.einzeln.setObjectName("ordner_einzeln")
        self.einzeln.setChecked(einzeln)
        v.addWidget(self.einzeln)
        v.addWidget(
            lbl(
                _("Nur nötig, wenn z. B. der Ausgang auf einem Netzlaufwerk liegen soll."),
                "hinweis",
                umbruch=True,
            )
        )
        self.ordner: dict[str, QLineEdit] = {}
        self._ordner_lbl = []
        self._ordner_knopf = []
        for schl, name in ORDNER:
            l_ = lbl(_(name))
            v.addWidget(l_)
            zeile = QHBoxLayout()
            zeile.setSpacing(8)
            e = QLineEdit(str(getattr(k, schl)))
            e.setObjectName(f"ordner_{schl}")
            e.setAccessibleName(_(name))
            zeile.addWidget(e, 1)
            b = knopf(_("Wählen…"), klick=lambda _c=False, ed=e, n=name: self._waehlen(ed, n))
            zeile.addWidget(b)
            v.addLayout(zeile)
            self.ordner[schl] = e
            self._ordner_lbl.append(l_)
            self._ordner_knopf.append(b)
        self.einzeln.toggled.connect(self._einzeln_umschalten)
        self.arbeitsordner.textChanged.connect(self._unterordner_nachziehen)
        self._einzeln_umschalten(einzeln)

        _abschnitt(
            v,
            _("Protokollordner"),
            _(
                "protokoll.tsv (alle Vorgänge, Grundlage der Doppelprüfung) liegt getrennt vom Ausgang, "
                "damit Archiv oder andere Programme den Ausgang leeren dürfen. Leer = Ordner „Protokoll“ "
                "im Arbeitsordner."
            ),
        )
        h = QHBoxLayout()
        h.setSpacing(8)
        prot = self.roh.get("protokoll_ordner") or (self.roh.get("ordner") or {}).get("protokoll") or ""
        self.protokoll_ordner = QLineEdit(str(prot))
        self.protokoll_ordner.setObjectName("protokoll_ordner")
        self.protokoll_ordner.setAccessibleName(_("Protokollordner"))
        self._protokoll_platzhalter()
        h.addWidget(self.protokoll_ordner, 1)
        h.addWidget(knopf(_("Wählen…"), klick=lambda: self._waehlen(self.protokoll_ordner, "Protokollordner")))
        v.addLayout(h)
        self.arbeitsordner.textChanged.connect(self._protokoll_platzhalter)
        self.einzeln.toggled.connect(self._protokoll_platzhalter)
        self.ordner["eingang"].textChanged.connect(self._protokoll_platzhalter)

        opt = self.roh.get("optionen") or {}
        _abschnitt(v, _("Eingang überwachen"))
        self.polling = QCheckBox(_("Eingang liegt auf Netzlaufwerk (langsamer, aber zuverlässig)"))
        self.polling.setChecked(bool(opt.get("polling")))
        v.addWidget(self.polling)
        v.addStretch(1)
        return w

    def _protokoll_platzhalter(self, *_a) -> None:
        """Platzhalter zeigt den Standardort (Arbeitsordner bzw. neben dem Eingang)."""
        if self.einzeln.isChecked():
            basis = Path(self.ordner["eingang"].text().strip() or ".").expanduser().parent
        else:
            basis = Path(self.arbeitsordner.text().strip() or ".").expanduser()
        self.protokoll_ordner.setPlaceholderText(str(basis / PROTOKOLL_ORDNER))

    def _einzeln_umschalten(self, an: bool) -> None:
        for x in [*self.ordner.values(), *self._ordner_lbl, *self._ordner_knopf]:
            x.setEnabled(an)
        self.arbeitsordner.setEnabled(not an)
        if not an:
            self._unterordner_nachziehen()

    def _unterordner_nachziehen(self) -> None:
        if self.einzeln.isChecked():
            return
        basis = Path(self.arbeitsordner.text().strip()).expanduser()
        for schl, name in UNTERORDNER:
            if schl in self.ordner:
                self.ordner[schl].setText(str(basis / name))

    def _waehlen(self, ed: QLineEdit, name: str) -> None:
        d = QFileDialog.getExistingDirectory(self, _(name), ed.text())
        if d:
            ed.setText(d)

    # ======================================================================== Absender
    def _seite_absender(self) -> QWidget:
        w, v = _seite()
        _abschnitt(
            v,
            _("Absender"),
            _(
                "Steht auf jeder Rechnung als Verkäufer. Vorlagen (Nur PDF) und CSV-Profile "
                "können einen eigenen Absender haben – der geht dann vor."
            ),
            erste=True,
        )
        # Absender-Profile: [0] = aktiver Absender (Blöcke absender/zahlung), dahinter die gemerkten
        self.abs_slots = [
            {
                "absender": copy.deepcopy(self.roh.get("absender") or {}),
                "zahlung": copy.deepcopy(self.roh.get("zahlung") or {}),
            }
        ]
        if self.roh.get("layout"):  # Layouteditor (seit 0.7.0)
            self.abs_slots[0]["layout"] = copy.deepcopy(self.roh["layout"])
        self.abs_slots += [
            copy.deepcopy(x) for x in self.roh.get("absender_profile") or [] if isinstance(x, dict)
        ]
        self.abs_i = 0
        v.addWidget(lbl(_("Absender-Profil")))
        h = QHBoxLayout()
        h.setSpacing(8)
        self.abs_wahl = QComboBox()
        self.abs_wahl.setObjectName("absender_profil")
        self.abs_wahl.setAccessibleName(_("Absender-Profil"))
        self.abs_wahl.setMinimumHeight(48)
        h.addWidget(self.abs_wahl, 1)
        self.b_abs_weg = knopf(_("Entfernen"), danger=True, klick=self._absender_entfernen)
        h.addWidget(self.b_abs_weg)
        v.addLayout(h)
        v.addWidget(
            lbl(
                _(
                    "Das gewählte Profil gilt beim Speichern für alle Rechnungen ohne eigenen Absender."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        lh = QHBoxLayout()
        lh.setSpacing(8)
        self.b_layout = knopf(_("Layout gestalten…"), klick=self._layout_gestalten)
        self.b_layout.setObjectName("layout_gestalten")
        lh.addWidget(self.b_layout)
        self.layout_info = lbl("", "hinweis", umbruch=True)
        lh.addWidget(self.layout_info, 1)
        v.addLayout(lh)
        v.addWidget(trenner())
        self.abs_form = AbsenderFormular(self.roh, self.toast)
        self.abs = self.abs_form.felder
        v.addWidget(self.abs_form)
        v.addStretch(1)
        self._absender_liste()
        self.abs_wahl.activated.connect(self._absender_wechseln)
        return w

    def _absender_liste(self) -> None:
        self.abs_wahl.blockSignals(True)
        self.abs_wahl.clear()
        for i, sl in enumerate(self.abs_slots):
            name = (sl.get("absender") or {}).get("name") or _("(ohne Namen)")
            self.abs_wahl.addItem(name, i)
        self.abs_wahl.addItem(_(NEUER_ABSENDER), -1)
        self.abs_wahl.setCurrentIndex(self.abs_i)
        self.abs_wahl.blockSignals(False)
        self.b_abs_weg.setEnabled(len(self.abs_slots) > 1)
        eigen = bool(self.abs_slots[self.abs_i].get("layout"))
        self.layout_info.setText(
            (_("Eigenes Layout.") if eigen else _("Standardlayout."))
            + " "
            + _("Gilt, wenn der Sichtteil neu erzeugt wird (Ausgabe → Sichtbild).")
        )

    def _layout_gestalten(self) -> None:
        """Layouteditor für das gewählte Absender-Profil; das Ergebnis gilt mit „Speichern“ der Einstellungen."""
        from ..konfig import partei_aus, zahlung_aus
        from .layouteditor import LayoutEditor

        self._absender_merken()
        sl = self.abs_slots[self.abs_i]
        v = partei_aus(sl.get("absender") or {})
        dlg = LayoutEditor(
            self,
            self.c,
            sl.get("layout"),
            self.haupt.k.basis,
            profil=v.name,
            verkaeufer=v,
            zahlung=zahlung_aus(sl.get("zahlung") or {}, kontoinhaber=v.name),
        )
        self._layout_dlg = dlg
        if dlg.exec():
            neu = dlg.ergebnis()
            if neu:
                sl["layout"] = neu
            else:
                sl.pop("layout", None)
            self._absender_liste()
            self.toast("ok", _("Layout übernommen"), _("Mit „Speichern“ unten sichern."))

    def _absender_merken(self) -> None:
        in_roh(self.abs_slots[self.abs_i], self.abs_form.werte())

    def _absender_wechseln(self, idx: int) -> None:
        ziel = self.abs_wahl.itemData(idx)
        self._absender_merken()
        if ziel == -1:
            self.abs_slots.append({"absender": {}, "zahlung": {}})
            ziel = len(self.abs_slots) - 1
        self.abs_i = ziel
        werte = aus_roh(self.abs_slots[ziel])
        for schl, e in self.abs_form.felder.items():
            e.setText(str(werte.get(schl) or ""))
        self.abs_form.ku.setChecked(bool(werte.get("kleinunternehmer")))
        self._absender_liste()

    def _absender_entfernen(self) -> None:
        if len(self.abs_slots) < 2:
            return
        weg = self.abs_slots.pop(self.abs_i)
        self.abs_i = max(0, self.abs_i - 1)
        werte = aus_roh(self.abs_slots[self.abs_i])
        for schl, e in self.abs_form.felder.items():
            e.setText(str(werte.get(schl) or ""))
        self.abs_form.ku.setChecked(bool(werte.get("kleinunternehmer")))
        self._absender_liste()
        self.toast("info", _("Absender entfernt"), (weg.get("absender") or {}).get("name", ""))

    # ======================================================================== Eingang & Vorlagen
    def _seite_vorlagen(self) -> QWidget:
        k = self.haupt.k
        opt = self.roh.get("optionen") or {}
        w, v = _seite()
        _abschnitt(v, _("Eingangsformat"), erste=True)
        self.modus_gruppe = QButtonGroup(self)
        modus = k.modus
        for code, titel, hinweise in (
            (
                "csv",
                _("CSV"),
                (_("Die Rechnungsdaten kommen aus einem CSV-Export der Warenwirtschaft."),),
            ),
            (
                "xml",
                _("XML (ZUGFeRD / XRechnung)"),
                (_(
                    "Die Rechnungsdaten kommen aus einer ZUGFeRD- oder "
                    "XRechnung-XML (CII oder UBL)."
                ),),
            ),
            (
                "nur_pdf",
                _("Nur PDF"),
                (
                    _("nicht empfohlen"),
                    _(
                        "Nur wenn kein CSV- oder XML-Export da ist. Die App liest "
                        "die Angaben aus dem Rechnungsdruck; jedes Layout lernst du "
                        "einmal an. Die Erkennung kann fehlgehen – prüfe die erzeugte "
                        "Rechnung, bevor du sie verschickst."
                    ),
                ),
            ),
        ):
            r = QRadioButton(titel)
            r.setObjectName(f"modus_{code}")
            r.setMinimumHeight(48)
            r.setChecked(modus == code)
            self.modus_gruppe.addButton(r)
            r.setProperty("code", code)
            v.addWidget(r)
            for text in hinweise:
                v.addWidget(lbl(text, "hinweis", umbruch=True))

        self.pdf_verwenden = QCheckBox(_("Zusätzlich das PDF der Rechnung verwenden"))
        self.pdf_verwenden.setObjectName("pdf_verwenden")
        self.pdf_verwenden.setMinimumHeight(48)
        self.pdf_verwenden.setChecked(bool(k.pdf_verwenden) and modus in ("csv", "xml"))
        v.addWidget(self.pdf_verwenden)
        v.addWidget(
            lbl(
                _(
                    "Dann gilt das Original-PDF als Sichtseite, und Fakturafalter wartet auf das "
                    "Gegenstück mit gleichem Namen. Ohne Haken wird die Sichtseite aus den "
                    "Daten neu gebaut (Layout unter Absender → „Layout gestalten…“)."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self.hinweis_pdf_verwenden = v.itemAt(v.count() - 1).widget()

        self.box_warten = QWidget()
        bw = QVBoxLayout(self.box_warten)
        bw.setContentsMargins(0, 8, 0, 0)
        bw.setSpacing(6)
        bw.addWidget(lbl(_("Wartezeit auf das PDF (Minuten)")))
        self.gegenstueck = QSpinBox()
        self.gegenstueck.setObjectName("gegenstueck_minuten")
        self.gegenstueck.setAccessibleName(_("Wartezeit auf das PDF (Minuten)"))
        self.gegenstueck.setRange(0, 240)
        self.gegenstueck.setMinimumHeight(48)
        self.gegenstueck.setValue(int(round(float(opt.get("gegenstueck_minuten", 10) or 0))))
        h = QHBoxLayout()
        h.addWidget(self.gegenstueck)
        h.addStretch(1)
        bw.addLayout(h)
        bw.addWidget(
            lbl(
                _(
                    "Die Verarbeitung startet, sobald PDF und CSV bzw. XML mit gleichem Namen im Eingang "
                    "liegen. Kommt die zweite Datei nicht, geht es nach dieser Zeit über die Rechnungsnummer "
                    "weiter. 0 = nicht warten."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addWidget(self.box_warten)

        self.pdf: dict[str, tuple[QCheckBox | None, QCheckBox | None, QCheckBox]] = {}
        self.box_csv = self._box(v, self._teil_csv)
        self.box_xml = self._box(v, self._teil_xml)
        self.box_pdf = self._box(v, self._teil_nur_pdf)
        v.addSpacing(8)
        h = QHBoxLayout()
        h.addWidget(knopf(_("Profilordner öffnen"), klick=lambda: aktionen.oeffnen(k.basis)))
        h.addStretch(1)
        v.addLayout(h)
        v.addStretch(1)
        self.modus_gruppe.buttonToggled.connect(lambda *_a: self._modus_zeigen())
        self.pdf_verwenden.toggled.connect(lambda *_a: self._modus_zeigen())
        self._modus_zeigen()
        return w

    @staticmethod
    def _box(v: QVBoxLayout, fuellen) -> QWidget:
        b = QWidget()
        bv = QVBoxLayout(b)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(8)
        fuellen(bv)
        v.addWidget(b)
        return b

    def _modus_zeigen(self) -> None:
        m = self.modus()
        daten = m in ("csv", "xml")
        self.box_pdf.setVisible(m == "nur_pdf")
        self.box_csv.setVisible(m == "csv")
        self.box_xml.setVisible(m == "xml")
        self.pdf_verwenden.setVisible(daten)
        self.pdf_verwenden.setEnabled(daten)
        if hasattr(self, "hinweis_pdf_verwenden"):
            self.hinweis_pdf_verwenden.setVisible(daten)
        self.box_warten.setVisible(daten and self.pdf_verwenden.isChecked())

    def _profil_karte(self, v: QVBoxLayout, prof: dict, art: str) -> None:
        name = pdferkennung.profil_name(prof)
        es = pdferkennung.einstellungen(prof)
        vorlagen = pdferkennung.vorlagen_laden(prof)
        sicher = any(pdferkennung.sicher(vl, es) for vl in vorlagen)
        n = max((anlernen.fortschritt(vl, prof)[0] for vl in vorlagen), default=0)
        ab = es["nur_pdf_ab"]
        kt, kv = karte()
        kopf = QHBoxLayout()
        kopf.addWidget(lbl(daten.profilname(prof), "titel", umbruch=True), 1)
        if art == "csv" and csv_einrichtung.bearbeitbar(prof):
            kopf.addWidget(
                knopf(
                    _("Ändern…"),
                    klick=lambda _c=False, p=prof: self._csv_assistent(p),
                    tip=_("Format und Spaltenzuordnung mit einer Beispiel-CSV ändern"),
                )
            )
        kv.addLayout(kopf)
        if art == "csv":
            d = prof.get("datei") or {}
            kv.addWidget(
                lbl(_("Dateien: {m}").format(m=d.get("muster", "*.csv")), "hinweis", umbruch=True)
            )
        z = QHBoxLayout()
        st = lbl(_("{n} von {ab} ohne Korrektur").format(n=min(n, ab), ab=ab))
        st.setStyleSheet("font-weight:bold;" + (f"color:{self.c['ok']};" if sicher else ""))
        z.addWidget(st)
        z.addSpacing(12)
        z.addWidget(Segmente(self.c, min(n, ab), ab), 1)
        kv.addLayout(z)
        gp = an = None
        if art == "csv":
            gp = QCheckBox(_("Gegenprüfung: CSV mit dem Druck vergleichen"))
            gp.setChecked(es["gegenpruefung"])
            an = QCheckBox(_("Anlernen: Layout aus Paaren CSV + PDF lernen"))
            an.setChecked(es["anlernen"])
            kv.addWidget(gp)
            kv.addWidget(an)
        nur = QCheckBox(_("Automatisch, ohne Nachfrage"))
        nur.setObjectName(f"auto_{name}")
        nur.setChecked(es["nur_pdf"] and sicher)
        nur.setEnabled(sicher)
        kv.addWidget(nur)
        kv.addWidget(
            lbl(_pruefen_text(min(n, ab), ab, sicher, es["nur_pdf"]), "hinweis", umbruch=True)
        )
        if art == "pdf":
            unten = QHBoxLayout()
            unten.addStretch(1)
            unten.addWidget(
                knopf(
                    _("Bereiche bearbeiten…"),
                    klick=lambda: self._anlernen_waehlen(bereiche=True),
                    tip=_(
                        "Eine Rechnung dieses Absenders wählen und die Bereiche (Anschrift, "
                        "Rechnungskopf, Summen …) neu ziehen"
                    ),
                )
            )
            unten.addWidget(
                knopf(
                    _("Weiter anlernen") if not sicher else _("Nachbessern"),
                    klick=lambda: self._anlernen_waehlen(),
                )
            )
            kv.addLayout(unten)
        v.addWidget(kt)
        self.pdf[name] = (gp, an, nur)

    def _teil_nur_pdf(self, v: QVBoxLayout) -> None:
        k = self.haupt.k
        _abschnitt(
            v,
            _("Vorlagen & Anlernen"),
            _(
                "Pro Rechnungslayout eine Vorlage. Nach {n} Rechnungen in Folge "
                "ohne Korrektur kannst du „Automatisch, ohne Nachfrage“ "
                "einschalten."
            ).format(n=pdferkennung.einstellungen({})["nur_pdf_ab"]),
        )
        wart = anlernen.warteschlange(k)
        h = QHBoxLayout()
        h.setSpacing(8)
        if wart:
            l_ = lbl(
                _("{n} Rechnungen warten aufs Anlernen").format(n=len(wart))
                if len(wart) != 1
                else _("1 Rechnung wartet aufs Anlernen"),
                "warn",
                umbruch=True,
            )
            h.addWidget(l_, 1)
            h.addWidget(
                knopf(_("Jetzt anlernen"), primary=True, klick=lambda: self._anlernen(None))
            )
            v.addLayout(h)
            h = QHBoxLayout()
        h.addWidget(
            knopf(_("Neue Rechnung anlernen…"), primary=not wart, klick=self._anlernen_waehlen)
        )
        h.addStretch(1)
        v.addLayout(h)
        if not k.pdf_profile:
            v.addWidget(
                lbl(
                    _(
                        "Noch keine Vorlage. Lerne die erste Rechnung an – danach erscheint sie hier."
                    ),
                    "hinweis",
                    umbruch=True,
                )
            )
        for prof in k.pdf_profile:
            self._profil_karte(v, prof, "pdf")

    def _teil_csv(self, v: QVBoxLayout) -> None:
        k = self.haupt.k
        _abschnitt(
            v,
            _("CSV-Zuordnungen"),
            _(
                "Wie Fakturafalter die CSV deiner Warenwirtschaft liest: Format und "
                "welche Spalte was bedeutet. Trennzeichen, Zeichensatz und "
                "Dezimalzeichen erkennt der Assistent selbst."
            ),
        )
        h = QHBoxLayout()
        h.addWidget(
            knopf(
                _("Neue CSV einrichten…"),
                primary=not k.csv_profile,
                klick=lambda: self._csv_assistent(),
            )
        )
        h.addStretch(1)
        v.addLayout(h)
        if not k.csv_profile:
            v.addWidget(lbl(_("Noch keine CSV eingerichtet."), "hinweis", umbruch=True))
        for prof in k.csv_profile:
            self._profil_karte(v, prof, "csv")
        infos = daten.kundenstamm_info(k)
        if infos:
            _abschnitt(v, _("Kundenstamm"))
            for pfad, anzahl, ohne in infos:
                zeile = QHBoxLayout()
                zeile.addWidget(lbl(pfad.name, umbruch=True), 1)
                zeile.addWidget(
                    knopf(_("Öffnen"), klick=lambda _c=False, p=pfad: aktionen.oeffnen(p))
                )
                v.addLayout(zeile)
                text = (
                    _("{n} Kunden geladen").format(n=anzahl)
                    if anzahl
                    else _("Datei fehlt oder ist leer")
                )
                if ohne:
                    text += " · " + _("{n} ohne E-Mail (für XRechnung nötig)").format(n=ohne)
                v.addWidget(lbl(text, "gut" if anzahl and not ohne else "warn", umbruch=True))

    def _teil_xml(self, v: QVBoxLayout) -> None:
        _abschnitt(v, _("XML-Eingang"))
        kt, kv = karte()
        kv.addWidget(
            lbl(_("ZUGFeRD / Factur-X und XRechnung, jeweils CII oder UBL"), "titel", umbruch=True)
        )
        kv.addWidget(
            lbl(
                _(
                    "Feste Zuordnung nach EN 16931 – nichts einzurichten. Fehlt der Verkäufer in der XML, "
                    "gilt der Absender aus den Einstellungen."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(knopf(_("Probe mit einer XML…"), klick=self._xml_assistent))
        kv.addLayout(h)
        v.addWidget(kt)

    def modus(self) -> str:
        b = self.modus_gruppe.checkedButton()
        return b.property("code") if b else "csv"

    def _csv_assistent(self, profil: dict | None = None) -> None:
        self.haupt.datenassistent_oeffnen("csv", eltern=self, profil=profil)
        self._vorlagen_neu(("csv_profile", "modus"))

    def _xml_assistent(self) -> None:
        self.haupt.datenassistent_oeffnen("xml", eltern=self)
        self._vorlagen_neu(("modus",))

    def _anlernen_waehlen(self, bereiche: bool = False) -> None:
        dateien, _f = QFileDialog.getOpenFileNames(
            self, _("Rechnungen zum Anlernen"), str(Path.home()), _("PDF-Dateien (*.pdf)")
        )
        if dateien:
            self._anlernen([Path(d) for d in dateien], bereiche=bereiche)

    def _anlernen(self, dateien: list[Path] | None, bereiche: bool = False) -> None:
        """Assistent über das Hauptfenster; danach Vorlagenliste neu aus der Datei lesen (der Assistent
        trägt neue Vorlagen selbst in die Konfiguration ein). ``bereiche``: mit „Bereiche festlegen“ beginnen."""
        if bereiche:
            self.haupt.anlernen_oeffnen(dateien, eltern=self, bereiche=True)
        else:
            self.haupt.anlernen_oeffnen(dateien, eltern=self)
        self._vorlagen_neu(("pdf_profile", "pdf_erkennung"))

    def _vorlagen_neu(self, schluessel: tuple[str, ...]) -> None:
        frisch = self.haupt.k.roh
        for schl in schluessel:
            if schl in frisch:
                self.roh[schl] = copy.deepcopy(frisch[schl])
        o = self.roh.setdefault("optionen", {})
        o["gegenstueck_minuten"] = self.gegenstueck.value()
        alt = self.vorlagen_rolle
        self.vorlagen_rolle = rollen(self._seite_vorlagen())
        i = self.stapel.indexOf(alt)
        self.stapel.insertWidget(i, self.vorlagen_rolle)
        self.stapel.removeWidget(alt)
        alt.deleteLater()
        self.bereich_zeigen("Eingang & Vorlagen")

    # ======================================================================== Prüfung
    def _seite_pruefung(self) -> QWidget:
        w, v = _seite()
        opt = self.roh.get("optionen") or {}
        da = validierung.bereit()
        _abschnitt(v, _("Prüfung"), erste=True)
        self.nachpruefen = QCheckBox(_("Nach Erstellung prüfen"))
        self.nachpruefen.setObjectName("nach_erstellung_pruefen")
        self.nachpruefen.setChecked(bool(opt.get("nach_erstellung_pruefen", True)) and da)
        self.nachpruefen.setEnabled(da)
        v.addWidget(self.nachpruefen)
        if da:
            v.addWidget(
                lbl(
                    _(
                        "Lokal mit Mustang (PDF/A-3, ZUGFeRD) und KoSIT (EN 16931), ohne Internet. "
                        "Ungültige Rechnungen landen mit Begründung im Fehlerordner."
                    ),
                    "hinweis",
                    umbruch=True,
                )
            )
        else:
            v.addWidget(
                lbl(
                    _("Prüfwerkzeuge nicht gefunden (Ordner „werkzeuge“ neben dem Programm)."),
                    "hinweis",
                    enabled=False,
                    umbruch=True,
                )
            )
        v.addStretch(1)
        return w

    # ======================================================================== Ausgabe
    def _seite_ausgabe(self) -> QWidget:
        opt = self.roh.get("optionen") or {}
        w, v = _seite()
        _abschnitt(
            v,
            _("Ausgabe"),
            _(
                "Fakturafalter erzeugt ZUGFeRD-PDFs (EN 16931, PDF/A-3): die Rechnung zum "
                "Ansehen mit den Daten darin."
            ),
            erste=True,
        )
        v.addWidget(lbl(_("XRechnung (XML) zusätzlich, wenn der Kundenstamm es verlangt"), umbruch=True))
        self.xr = QComboBox()
        self.xr.setObjectName("xrechnung_ablage")
        self.xr.setAccessibleName(_("XRechnung (XML) zusätzlich, wenn der Kundenstamm es verlangt"))
        self.xr.addItem(_("Neben der PDF im Ausgang"), "ausgang")
        self.xr.addItem(_("Im Unterordner „{n}“ des Ausgangs").format(n=XRECHNUNG_ORDNER), "unterordner")
        self.xr.addItem(_("Keine XRechnung-Datei"), "keine")
        ablage = str(opt.get("xrechnung_ablage") or "ausgang")
        if not opt.get("xrechnung_zusatz", True) or ablage == "keine":
            ablage = "keine"
        self.xr.setCurrentIndex(max(0, self.xr.findData(ablage)))
        v.addWidget(self.xr)
        v.addWidget(lbl(_("Sichtbild"), umbruch=True))
        self.sicht = QComboBox()
        self.sicht.addItem(_("Original-Druck verwenden (sonst neu erzeugen)"), "original")
        self.sicht.addItem(_("Immer neu erzeugen"), "neu")
        self.sicht.setCurrentIndex(0 if opt.get("sichtteil", "original") == "original" else 1)
        v.addWidget(self.sicht)
        self._teil_dateiname(v, opt)
        v.addStretch(1)
        return w

    def _teil_dateiname(self, v: QVBoxLayout, opt: dict) -> None:
        """Dateiname und Prüfung der Rechnungsnummer je Belegart (ab 0.9.5). Leere Felder = wie bisher."""
        _abschnitt(
            v,
            _("Dateiname und Rechnungsnummer"),
            _(
                "Die Rechnungsnummer kommt immer aus der CSV bzw. XML (dem ERP). Fakturafalter vergibt "
                "keine Nummern und ändert sie nie, es prüft sie nur. Leere Felder: wie bisher."
            ),
        )
        kreise = nummernkreis.aus_optionen(opt)
        self.kreis_felder: dict[str, dict] = {}
        for kreis, titel in (("rechnung", "Rechnungen"), ("gutschrift", "Gutschriften")):
            k = kreise.get(kreis) or nummernkreis.Kreis()
            box, b = karte()
            b.addWidget(lbl(_(titel), "titel"))
            b.addWidget(lbl(_("Dateiname der ZUGFeRD-PDF"), umbruch=True))
            pdf = QLineEdit(k.dateiname)
            pdf.setObjectName(f"dateiname_{kreis}")
            pdf.setAccessibleName(_("Dateiname der ZUGFeRD-PDF"))
            pdf.setPlaceholderText(
                "{rechnungsnummer}_zugferd.pdf" if kreis == "rechnung" else _("wie bei Rechnungen")
            )
            b.addWidget(pdf)
            b.addWidget(lbl(_("Dateiname der XRechnung-XML (falls erzeugt)"), umbruch=True))
            xml = QLineEdit(k.dateiname_xrechnung)
            xml.setObjectName(f"dateiname_xrechnung_{kreis}")
            xml.setAccessibleName(_("Dateiname der XRechnung-XML (falls erzeugt)"))
            xml.setPlaceholderText(
                "{rechnungsnummer}_xrechnung.xml" if kreis == "rechnung" else _("wie bei Rechnungen")
            )
            b.addWidget(xml)
            b.addWidget(lbl(_("Prüfmuster der Rechnungsnummer (optional)"), umbruch=True))
            muster = QLineEdit(k.pruefmuster)
            muster.setObjectName(f"pruefmuster_{kreis}")
            muster.setAccessibleName(_("Prüfmuster der Rechnungsnummer (optional)"))
            muster.setPlaceholderText(_("z. B. JJJJ###### oder RE-JJJJ-####"))
            b.addWidget(muster)
            luecken = QCheckBox(_("Lücken im Nummernkreis melden (nur Warnung)"))
            luecken.setObjectName(f"luecken_{kreis}")
            luecken.setChecked(k.luecken_warnen)
            b.addWidget(luecken)
            vorschau = lbl("", "hinweis", umbruch=True)
            vorschau.setAccessibleName(_("Vorschau des Dateinamens"))
            b.addWidget(vorschau)
            v.addWidget(box)
            self.kreis_felder[kreis] = {
                "pdf": pdf,
                "xml": xml,
                "muster": muster,
                "luecken": luecken,
                "vorschau": vorschau,
            }
            for ed in (pdf, xml, muster):
                ed.textChanged.connect(lambda _t: self._dateiname_vorschau())
        v.addWidget(
            lbl(
                _(
                    "Platzhalter im Dateinamen: {rechnungsnummer} {jahr} {monat} {tag} {datum} "
                    "{kundennummer} {kunde} {belegart} {belegart_kurz}. Umlaute und Sonderzeichen werden "
                    "für Windows und Linux ersetzt. Gibt es die Datei schon, wird nichts überschrieben: "
                    "die Rechnung geht nach „Zu prüfen“."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        v.addWidget(
            lbl(
                _(
                    "Prüfmuster: JJJJ = Jahr, JJ = Jahr zweistellig, MM = Monat, # = eine Ziffer, "
                    "* = beliebige Zeichen, alles andere wörtlich. Passt eine Nummer nicht, geht die Rechnung "
                    "nach „Zu prüfen“. Lücken (der letzte #-Block zählt) sind erlaubt und werden nur gemeldet. "
                    "Doppelte Nummern hält Fakturafalter immer an."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self._dateiname_vorschau()

    def _kreise_aus_feldern(self) -> dict:
        aus = {}
        for kreis, f in self.kreis_felder.items():
            aus[kreis] = nummernkreis.Kreis(
                f["muster"].text().strip(),
                f["luecken"].isChecked(),
                f["pdf"].text().strip(),
                f["xml"].text().strip(),
            )
        return aus

    def _kreis_fehler(self) -> str:
        """Erster Fehler in den Mustern (leer = alles in Ordnung)."""
        for kreis, k in self._kreise_aus_feldern().items():
            name = _("Rechnungen") if kreis == "rechnung" else _("Gutschriften")
            for text in (
                nummernkreis.dateiname_pruefen(k.dateiname),
                nummernkreis.dateiname_pruefen(k.dateiname_xrechnung),
                nummernkreis.muster_pruefen(k.pruefmuster),
            ):
                if text:
                    return f"{name}: {_(text) if text in _UEBERSETZBAR else text}"
        return ""

    def _dateiname_vorschau(self) -> None:
        kreise = self._kreise_aus_feldern()
        rech = kreise["rechnung"]
        for kreis, f in self.kreis_felder.items():
            k = kreise[kreis]
            m_pdf = k.dateiname or rech.dateiname or nummernkreis.STANDARD_PDF
            m_xml = k.dateiname_xrechnung or rech.dateiname_xrechnung or nummernkreis.STANDARD_XML
            hat_zaehler = bool(k.pruefmuster) and nummernkreis.hat_zaehler(k.pruefmuster)
            f["luecken"].setEnabled(hat_zaehler)
            f["luecken"].setToolTip(
                ""
                if hat_zaehler
                else _("Braucht ein Prüfmuster mit # (Zähler), z. B. JJJJ######.")
            )
            fehler = (
                nummernkreis.muster_pruefen(k.pruefmuster)
                or nummernkreis.dateiname_pruefen(m_pdf)
                or nummernkreis.dateiname_pruefen(m_xml)
            )
            if fehler:
                f["vorschau"].setObjectName("warn")
                f["vorschau"].setText(_(fehler) if fehler in _UEBERSETZBAR else fehler)
            else:
                r = nummernkreis.beispiel(kreis, k.pruefmuster)
                f["vorschau"].setObjectName("hinweis")
                f["vorschau"].setText(
                    _("Vorschau mit Nummer {nr}: {pdf} · {xml}").format(
                        nr=r.nummer,
                        pdf=nummernkreis.dateiname(m_pdf, r, ".pdf"),
                        xml=nummernkreis.dateiname(m_xml, r, ".xml"),
                    )
                )
            f["vorschau"].style().unpolish(f["vorschau"])
            f["vorschau"].style().polish(f["vorschau"])

    # ======================================================================== Allgemein
    def _seite_allgemein(self) -> QWidget:
        ui = self.haupt.ui
        w, v = _seite()
        _abschnitt(v, _("Start und Hintergrund"), erste=True)
        self.autostart = QCheckBox(_("Mit dem System starten"))
        try:
            self._autostart_vorher = autostart.ist_aktiv()
        except OSError:
            self._autostart_vorher = False
        self.autostart.setChecked(self._autostart_vorher)
        self.autostart.setToolTip(autostart.beschreibung())
        v.addWidget(self.autostart)
        tray = QSystemTrayIcon.isSystemTrayAvailable()
        self.minimiert = QCheckBox(_("Minimiert im Infobereich (Tray) starten"))
        self.minimiert.setChecked(bool(ui.get("minimiert_starten")) and tray)
        self.minimiert.setEnabled(tray)
        v.addWidget(self.minimiert)
        self.schliessen = QCheckBox(_("Fenster schließen = im Tray weiterlaufen"))
        self.schliessen.setChecked(bool(ui.get("schliessen_in_tray", True)) and tray)
        self.schliessen.setEnabled(tray)
        v.addWidget(self.schliessen)
        if not tray:
            v.addWidget(
                lbl(
                    _("Kein Infobereich (Tray) auf diesem System gefunden."),
                    "hinweis",
                    enabled=False,
                    umbruch=True,
                )
            )

        _abschnitt(v, _("Darstellung"))
        v.addWidget(lbl(_("Sprache")))
        self.sprache = QComboBox()
        for code, name in SPRACHEN.items():
            self.sprache.addItem(name, code)
        self.sprache.setCurrentIndex(max(0, self.sprache.findData(ui.get("sprache", "de"))))
        v.addWidget(self.sprache)
        v.addWidget(lbl(_("Farbschema")))
        self.thema = QComboBox()
        for code, name in (("system", "Wie System"), ("hell", "Hell"), ("dunkel", "Dunkel")):
            self.thema.addItem(_(name), code)
        self.thema.setCurrentIndex(max(0, self.thema.findData(ui.get("thema", "system"))))
        v.addWidget(self.thema)

        _abschnitt(
            v,
            _("Datenschutz"),
            _(
                "Alle Rechnungsdaten werden ausschließlich lokal verarbeitet: keine Telemetrie, "
                "keine Daten verlassen diesen Rechner. Einziger Netzzugriff ist die optionale "
                "Updateprüfung (unten). Freie Software (Apache-2.0), ohne Gewähr, kein Support."
            ),
        )
        self.anonym = QCheckBox(_("Logs anonymisieren"))
        self.anonym.setObjectName("logs_anonymisieren")
        self.anonym.setChecked(
            bool((self.roh.get("optionen") or {}).get("logs_anonymisieren", False))
        )
        v.addWidget(self.anonym)
        v.addWidget(
            lbl(
                _(
                    "Namen, Anschriften, IBAN, USt-IdNr., E-Mail-Adressen und Beträge erscheinen in der "
                    "Logdatei als Platzhalter (z. B. „[Name]“). Gut, bevor du ein Log "
                    "weitergibst. Gilt ab jetzt, ältere Logzeilen bleiben, wie sie sind."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        self._teil_updates(v)
        v.addStretch(1)
        return w

    def _teil_updates(self, v: QVBoxLayout) -> None:
        """Updateprüfung (ab 0.9.6): einziger Netzzugriff, nur Hinweis mit Link, kein Download."""
        opt = self.roh.get("optionen") or {}
        _abschnitt(
            v,
            _("Updates"),
            _(
                "Fragt nur die aktuelle Versionsnummer bei GitHub ab und sendet keine Daten. "
                "Gibt es eine neuere Version, erscheint ein Hinweis mit Link – heruntergeladen "
                "wird nichts."
            ),
        )
        self.updates = QCheckBox(_("Beim Start nach Updates suchen"))
        self.updates.setObjectName("updatepruefung")
        self.updates.setChecked(bool(opt.get("updatepruefung", True)))
        v.addWidget(self.updates)
        self.updates_vorab = QCheckBox(_("Pre-Releases einbeziehen"))
        self.updates_vorab.setObjectName("updates_vorab")
        self.updates_vorab.setChecked(bool(opt.get("updates_vorab", False)))
        v.addWidget(self.updates_vorab)
        h = QHBoxLayout()
        h.setSpacing(8)
        self.b_update = knopf(_("Jetzt prüfen"), klick=self._update_jetzt)
        self.b_update.setObjectName("update_jetzt")
        h.addWidget(self.b_update)
        self.update_info = lbl("", "hinweis", umbruch=True)
        self.update_info.setObjectName("update_info")
        self.update_info.setOpenExternalLinks(True)
        h.addWidget(self.update_info, 1)
        v.addLayout(h)
        self.update_ergebnis.connect(self._update_fertig)

    def _update_jetzt(self) -> None:
        self.b_update.setEnabled(False)
        self.update_info.setText(_("Prüfe …"))
        updatepruefung.im_hintergrund(self.updates_vorab.isChecked(), self.update_ergebnis.emit)

    def _update_fertig(self, erreichbar: bool, neu) -> None:
        self.b_update.setEnabled(True)
        if neu is not None:
            self.update_info.setText(
                _("Neue Version verfügbar: Fakturafalter {v}").format(v=neu.version)
                + f' – <a href="{neu.url}">{_("Release-Seite öffnen")}</a>'
            )
        elif erreichbar:
            self.update_info.setText(_("Fakturafalter {v} ist aktuell.").format(v=__version__))
        else:
            self.update_info.setText(_("Keine Verbindung – später erneut versuchen."))

    # ======================================================================== Speichern
    def _fehler(self, text: str, wo: str = "Ordner") -> None:
        self.fehler.setText(text)
        self.fehler.setVisible(True)
        self.bereich_zeigen(wo)

    def _speichern(self) -> None:
        if self.einzeln.isChecked():
            leer = [_(n) for s, n in ORDNER if not self.ordner[s].text().strip()]
            if leer:
                return self._fehler(_("Bitte Ordner angeben: {was}").format(was=", ".join(leer)))
            pfade = [Path(self.ordner[s].text().strip()).expanduser() for s, _n in ORDNER]
            if len({str(p) for p in pfade}) < len(pfade):
                return self._fehler(_("Die fünf Ordner müssen verschieden sein."))
        elif not self.arbeitsordner.text().strip():
            return self._fehler(_("Bitte einen Arbeitsordner angeben."))
        fehler = self._kreis_fehler()
        if fehler:
            return self._fehler(fehler, "Ausgabe")
        self.accept()

    def autostart_gewuenscht(self) -> bool | None:
        an = self.autostart.isChecked()
        return an if an != self._autostart_vorher else None

    def ergebnis(self) -> dict:
        r = copy.deepcopy(self.roh)
        basis = self.haupt.k.basis
        if self.einzeln.isChecked():
            ordner = {}
            for schl, _n in ORDNER:
                p = Path(self.ordner[schl].text().strip()).expanduser()
                alt = (r.get("ordner") or {}).get(schl)
                # unverändert -> ursprüngliche (evtl. relative) Schreibweise behalten
                ordner[schl] = alt if alt and (basis / alt).resolve() == p.resolve() else str(p)
            r["ordner"] = ordner
        else:
            p = Path(self.arbeitsordner.text().strip()).expanduser()
            alt = r.get("arbeitsordner")
            r["arbeitsordner"] = alt if alt and (basis / alt).resolve() == p.resolve() else str(p)
            r.pop("ordner", None)
        prot = self.protokoll_ordner.text().strip()
        if prot:
            alt = r.get("protokoll_ordner")
            p = Path(prot).expanduser()
            r["protokoll_ordner"] = alt if alt and (basis / alt).resolve() == p.resolve() else str(p)
        else:
            r.pop("protokoll_ordner", None)
        self._absender_merken()
        slots = [
            sl
            for i, sl in enumerate(self.abs_slots)
            if i == self.abs_i or (sl.get("absender") or {}).get("name")
        ]
        aktiv = self.abs_slots[self.abs_i]
        r["absender"], r["zahlung"] = (
            copy.deepcopy(aktiv["absender"]),
            copy.deepcopy(aktiv["zahlung"]),
        )
        if aktiv.get("layout"):
            r["layout"] = copy.deepcopy(aktiv["layout"])
        else:
            r.pop("layout", None)
        andere = [copy.deepcopy(sl) for sl in slots if sl is not aktiv]
        if andere:
            r["absender_profile"] = andere
        else:
            r.pop("absender_profile", None)
        o = r.setdefault("optionen", {})
        o["pdf_verwenden"] = self.modus() in ("csv", "xml") and self.pdf_verwenden.isChecked()
        if (self.modus() in ("csv", "xml") and self.pdf_verwenden.isChecked()) or "gegenstueck_minuten" in o:
            o["gegenstueck_minuten"] = self.gegenstueck.value()
        ablage = self.xr.currentData()
        o["xrechnung_zusatz"] = ablage != "keine"
        if ablage == "unterordner" or "xrechnung_ablage" in o:
            o["xrechnung_ablage"] = ablage if ablage != "keine" else o.get("xrechnung_ablage", "ausgang")
        if self.updates.isChecked() is not True or "updatepruefung" in o:
            o["updatepruefung"] = self.updates.isChecked()
        if self.updates_vorab.isChecked() or "updates_vorab" in o:
            o["updates_vorab"] = self.updates_vorab.isChecked()
        o["sichtteil"] = self.sicht.currentData()
        kreise = nummernkreis.in_optionen(self._kreise_aus_feldern())
        if kreise:
            o["nummernkreise"] = kreise
        else:
            o.pop("nummernkreise", None)  # nichts eingestellt: Datei bleibt wie bisher
        o["polling"] = self.polling.isChecked()
        o["logs_anonymisieren"] = self.anonym.isChecked()
        if self.nachpruefen.isEnabled():
            o["nach_erstellung_pruefen"] = self.nachpruefen.isChecked()
        r["modus"] = self.modus()
        pe = r.setdefault("pdf_erkennung", {})
        for name, (gp, an, nur) in self.pdf.items():
            e = dict(pe.get(name) or {})
            if gp is not None:
                e["gegenpruefung"] = gp.isChecked()
                e["anlernen"] = an.isChecked()
            e["nur_pdf"] = nur.isChecked() if nur.isEnabled() else e.get("nur_pdf", False)
            pe[name] = e
        u = r.setdefault("oberflaeche", {})
        u["sprache"] = self.sprache.currentData()
        u["thema"] = self.thema.currentData()
        u["minimiert_starten"] = self.minimiert.isChecked()
        u["schliessen_in_tray"] = (
            self.schliessen.isChecked()
            if self.schliessen.isEnabled()
            else u.get("schliessen_in_tray", True)
        )
        return r
