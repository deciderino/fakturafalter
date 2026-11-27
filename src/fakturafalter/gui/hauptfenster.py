# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Schlankes Hauptfenster: Läuft es? Muss ich etwas tun? Wie viele heute? – plus Tray mit Aufgaben-Zahl."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QScrollArea,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, anlernen, logdatei, updatepruefung
from ..konfig import lade_konfig
from . import aktionen, daten, orte, thema
from .arbeiter import Arbeiter
from .bausteine import Punkt, Schalter, ToastStapel, karte, knopf, lbl, symbol
from .fortschritt import FortschrittsBereich
from .texte import _, sprache_setzen

log = logging.getLogger("fakturafalter")


class Hauptfenster(QMainWindow):
    update_ergebnis = Signal(
        bool, object
    )  # (erreichbar, updatepruefung.Neu | None) aus dem Hintergrund

    def __init__(self, konfig_pfad: Path, tray_erlaubt: bool = True, auto_start: bool = True):
        super().__init__()
        self.konfig_pfad = Path(konfig_pfad)
        self.k = lade_konfig(self.konfig_pfad)
        self.ui = orte.ui_optionen(self.k.roh)
        logdatei.anonym_setzen(self.k.logs_anonym, self.k)
        sprache_setzen(self.ui["sprache"])
        self.c = thema.anwenden(QApplication.instance(), self.ui["thema"])
        self.zust = "pausiert"
        self._einst_offen = False
        self._wirklich_beenden = False
        self.pruef_fenster = None
        self._starthinweis_zu = False  # „Schließen“: bis zum nächsten Start ausgeblendet
        self._laeuft = False  # Lauf mit Fortschrittsanzeige (Überwachung oder „Jetzt einlesen“)

        self.arbeiter = Arbeiter(
            self.k, polling=bool(self.k.roh.get("optionen", {}).get("polling")), parent=self
        )
        self.arbeiter.lauf_fertig.connect(self._bei_lauf)
        self.arbeiter.zustand.connect(self._zustand)
        self.arbeiter.fortschritt.connect(self._bei_fortschritt)
        self.arbeiter.problem.connect(lambda t: self.toast("fehler", _("Überwachung gestoppt"), t))
        self.arbeiter.umwandeln_problem.connect(
            lambda t: self.toast("fehler", _("Umwandeln fehlgeschlagen"), t)
        )
        self._manuell = False  # laufender Lauf kommt aus „Umwandeln …“ / Ziehen ins Fenster (rc2)
        self.log_datei = logdatei.aktuell()
        self._tray_sig = None

        self.setWindowIcon(symbol())
        self.setMinimumSize(640, 420)  # passt auch bei 250 % auf 1920×1080
        self.resize(900, 900)
        self.toasts = ToastStapel(self, abstand_unten=48)
        self.tray = None
        self._aufbauen()
        QTimer.singleShot(0, self._profilhinweise)

        if tray_erlaubt and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(symbol(self.c["off"]), self)
            self.tray.activated.connect(self._tray_klick)
            self._tray_menue()
            self.tray.show()

        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.protokoll_umschalten)
        QShortcut(QKeySequence("F5"), self, activated=self.jetzt_einlesen)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.einstellungen_oeffnen)

        self.timer = QTimer(self)  # Ordner-Zähler auffrischen (kein Blinken: nur Text ändert sich)
        self.timer.timeout.connect(self.aktualisieren)
        self.timer.start(3000)
        if auto_start and not self.einrichtung_fehlt():
            self.arbeiter.starten()
        else:
            self._zustand("einrichten" if self.einrichtung_fehlt() else "pausiert")
        self.aktualisieren()
        self.update_ergebnis.connect(self._bei_update)
        self._update_still = True  # Start-Prüfung: nur melden, wenn es etwas Neues gibt
        if self.k.updatepruefung:
            QTimer.singleShot(3000, self.update_pruefen)

    # ======================================================================== Updateprüfung
    def update_pruefen(self, still: bool = True) -> None:
        """Im Hintergrund nach einer neueren Version fragen (einziger Netzzugriff, blockiert nie)."""
        self._update_still = still
        updatepruefung.im_hintergrund(self.k.updates_vorab, self.update_ergebnis.emit)

    def _bei_update(self, erreichbar: bool, neu) -> None:
        if neu is None:
            return
        self.toast(
            "info",
            _("Neue Version verfügbar: Fakturafalter {v}").format(v=neu.version),
            _("Download auf der Release-Seite (kein automatischer Download)."),
            _("Release-Seite öffnen"),
            lambda: aktionen.link_oeffnen(neu.url),
            schluessel="update",
        )

    # ======================================================================== Aufbau
    def einrichtung_fehlt(self) -> list[str]:
        fehlt = [_(f) for f in daten.absender_fehlt(self.k)]
        if not (
            self.k.csv_profile
            or self.k.pdf_vorlagen
            or self.k.pdf_profile
            or self.k.modus == "nur_pdf"
            or self.k.ist_xml()
        ):
            fehlt.append(_("CSV-Profil oder PDF-Vorlage"))
        return fehlt

    def _aufbauen(self) -> None:
        """Drei Fragen, sonst nichts: Läuft es? Muss ich etwas tun? Wie viele heute?

        Ordner, Profile, Vorlagen und Absender stehen in den Einstellungen; Technisches in der Logdatei."""
        self.setWindowTitle("Fakturafalter")
        root = QWidget()
        root.setObjectName("wurzel")
        m = QVBoxLayout(root)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(0)

        leiste = QFrame()
        leiste.setObjectName("leiste")
        tl = QHBoxLayout(leiste)
        tl.setContentsMargins(12, 8, 12, 8)
        tl.setSpacing(8)
        self.b_pause = Schalter(
            self.c, _("Überwachung an"), _("Überwachung aus"), klick=self.pause_umschalten
        )
        self.b_pause.setObjectName("ueberwachung")
        self.b_pause.setToolTip(_("Eingang überwachen an/aus"))
        self.b_jetzt = knopf(
            _("Jetzt einlesen"), klick=self.jetzt_einlesen, tip=_("Eingang sofort verarbeiten (F5)")
        )
        # rc2: Umwandeln von Hand – Dateien oder Ordner wählen (auch bei „Überwachung aus“)
        self.b_umwandeln = knopf(
            _("Umwandeln …"),
            tip=_(
                "Dateien oder einen Ordner von Hand umwandeln – mit dem eingestellten Profil, auch bei "
                "ausgeschalteter Überwachung. Du kannst Dateien auch ins Fenster ziehen."
            ),
        )
        self.b_umwandeln.setObjectName("umwandeln")
        self.m_umwandeln = QMenu(self.b_umwandeln)
        self.a_dateien = self.m_umwandeln.addAction(_("Dateien wählen …"), self.umwandeln_dateien)
        self.a_ordner = self.m_umwandeln.addAction(_("Ordner wählen …"), self.umwandeln_ordner)
        self.b_umwandeln.setMenu(self.m_umwandeln)
        self.b_eingang = knopf(_("Eingang öffnen"), klick=lambda: aktionen.oeffnen(self.k.eingang))
        self.b_einst = knopf(
            _("Einstellungen"), tip=_("Einstellungen (Strg+,)"), klick=self.einstellungen_oeffnen
        )
        for b in (self.b_pause, self.b_jetzt, self.b_umwandeln, self.b_eingang):
            tl.addWidget(b)
        tl.addStretch()
        tl.addWidget(self.b_einst)
        m.addWidget(leiste)

        body = QWidget()
        body.setObjectName("wurzel")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 8)
        bl.setSpacing(10)
        rollen = QScrollArea()  # kleine Fenster: scrollen statt Zeilen zu quetschen
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.Shape.NoFrame)
        rollen.setWidget(body)
        m.addWidget(rollen, 1)
        self.fortschritt = FortschrittsBereich(self.c)  # nur während der Verarbeitung sichtbar
        m.addWidget(self.fortschritt)

        # 0) Starthinweis: keine Gewährleistung, kein Support (Apache-2.0 §7/§8), bis „Nicht mehr anzeigen“
        self.starthinweis = None
        if not self.ui.get("starthinweis_aus") and not self._starthinweis_zu:
            self.starthinweis = self._starthinweis_bauen()
            bl.addWidget(self.starthinweis)

        # 1) Läuft es?
        k, v = karte()
        z = QHBoxLayout()
        z.setSpacing(10)
        self.punkt = Punkt(self.c["off"])
        self.l_titel = lbl("", "titel")
        z.addWidget(self.punkt)
        z.addWidget(self.l_titel)
        z.addStretch()
        v.addLayout(z)
        self.l_status = lbl("", "sub", umbruch=True)
        v.addWidget(self.l_status)
        bl.addWidget(k)

        # 2) Muss ich etwas tun?
        k, v = karte()
        v.addWidget(lbl(_("Zu tun"), "titel"))
        self.einricht_zeile, self.l_einricht, _b = self._aufgabe(
            "warn", _("Einrichten"), self.einrichtung_oeffnen, primary=True
        )
        self.anlern_zeile, self.l_anlern, self.b_anlernen = self._aufgabe(
            "warn", _("Anlernen"), lambda: self.anlernen_oeffnen(), primary=True
        )
        self.pruef_zeile, self.l_pruef, self.b_pruefen = self._aufgabe(
            "warn", _("Prüfen"), lambda: self.pruefansicht_oeffnen(0), primary=True
        )
        self.fehler_zeile, self.l_fehler, self.b_fehler = self._aufgabe(
            "warn", _("Ansehen"), lambda: self.pruefansicht_oeffnen(1)
        )
        for zeile in (self.einricht_zeile, self.anlern_zeile, self.pruef_zeile, self.fehler_zeile):
            v.addWidget(zeile)
        self.l_warten = lbl("", "sub", umbruch=True)  # PDF + CSV/XML: zweite Datei fehlt noch
        self.l_warten.hide()
        v.addWidget(self.l_warten)
        self.nichts_zeile = QWidget()
        nz = QHBoxLayout(self.nichts_zeile)
        nz.setContentsMargins(0, 0, 0, 0)
        self.l_nichts = lbl(_("Nichts zu tun."), "gut")
        nz.addWidget(self.l_nichts, 1)
        self.b_protokoll = knopf(
            _("Protokoll"),
            tip=_("Alle Vorgänge (Strg+L)"),
            klick=lambda: self.pruefansicht_oeffnen(2),
        )
        nz.addWidget(self.b_protokoll)
        v.addWidget(self.nichts_zeile)
        bl.addWidget(k)

        # 3) Wie viele heute?
        k, v = karte()
        z = QHBoxLayout()
        z.setSpacing(10)
        self.l_heute = lbl("", "gross")
        z.addWidget(self.l_heute, 1)
        self.b_ausgang = knopf(_("Ausgang öffnen"), klick=lambda: aktionen.oeffnen(self.k.ausgang))
        z.addWidget(self.b_ausgang)
        v.addLayout(z)
        self.l_zuletzt = lbl("", "sub")
        v.addWidget(self.l_zuletzt)
        bl.addWidget(k)
        bl.addStretch()
        self.setCentralWidget(root)
        self.setAcceptDrops(True)
        self.ablage = self._ablage_bauen(root)

        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.l_bereit = lbl("" if self._laeuft else _("Bereit"))
        sb.addWidget(self.l_bereit, 1)
        self.l_pruefmodul = lbl("")
        sb.addPermanentWidget(self.l_pruefmodul)
        sb.addPermanentWidget(lbl(f"v{__version__}"))
        self.setStatusBar(sb)
        self._zustand(self.zust)
        self.toasts.ordnen()

    def _ablage_bauen(self, eltern: QWidget) -> QFrame:
        """Fläche „Loslassen zum Umwandeln“, nur sichtbar, solange Dateien über das Fenster gezogen werden."""
        c = self.c
        w = QFrame(eltern)
        w.setObjectName("ablage")
        w.setStyleSheet(
            f"QFrame#ablage {{ border: 2px dashed {c['acc']}; border-radius: 8px; background: {c['card']}; }}"
            " QFrame#ablage QLabel { border: none; background: transparent; }"
        )
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 24, 24, 24)
        v.addStretch()
        self.l_ablage = lbl("", "titel", umbruch=True)
        self.l_ablage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.l_ablage)
        unter = lbl(
            _(
                "Gleiches Profil und gleiche Prüfungen wie im Eingang. Ergebnisse in den Ausgang, die "
                "Originale bleiben, wo sie sind. Eine gleichnamige PDF neben der CSV/XML wird wie gewohnt "
                "als Sichtteil genommen."
            ),
            "sub",
            umbruch=True,
        )
        unter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(unter)
        v.addStretch()
        w.hide()
        return w

    # ======================================================================== Umwandeln von Hand (rc2)
    def _umwandeln_moeglich(self, melden: bool = True) -> bool:
        fehlt = self.einrichtung_fehlt()
        if fehlt:
            if melden:
                self.toast(
                    "info",
                    _("Erst die Einrichtung abschließen"),
                    _("Noch einzurichten: {was}").format(was=", ".join(fehlt)),
                )
            return False
        if self._beschaeftigt() or self._einst_offen:
            if melden:
                self.toast(
                    "info",
                    _("Gerade läuft eine Verarbeitung"),
                    _("Versuch es gleich noch einmal, wenn sie fertig ist."),
                )
            return False
        return True

    def umwandeln_dateien(self) -> bool:
        if not self._umwandeln_moeglich():
            return False
        gew, _f = QFileDialog.getOpenFileNames(
            self,
            _("Dateien umwandeln"),
            str(Path.home()),
            _("Rechnungsdateien (*.csv *.txt *.tsv *.xml *.pdf *.xlsx *.ods);;Alle Dateien (*)"),
        )
        return self.umwandeln([Path(g) for g in gew]) if gew else False

    def umwandeln_ordner(self) -> bool:
        if not self._umwandeln_moeglich():
            return False
        d = QFileDialog.getExistingDirectory(self, _("Ordner umwandeln"), str(Path.home()))
        return self.umwandeln([Path(d)]) if d else False

    def umwandeln(self, pfade: list[Path]) -> bool:
        """Gewählte oder ins Fenster gezogene Dateien/Ordner umwandeln (gleiche Strecke wie der Eingang)."""
        from ..ueberwachung import NICHT_UNTERSTUETZT, manuell_sammeln

        if not self._umwandeln_moeglich():
            return False
        auswahl = manuell_sammeln(pfade, self.k)
        for p, grund in auswahl.uebersprungen:
            log.info("Umwandeln von Hand: %s übersprungen (%s)", p.name, grund)
        if auswahl.uebersprungen:
            namen = ", ".join(p.name for p, _g in auswahl.uebersprungen[:3])
            if len(auswahl.uebersprungen) > 3:
                namen += " …"
            self.toast(
                "info",
                _("{n} Datei(en) übersprungen").format(n=len(auswahl.uebersprungen)),
                _("{namen} – passt nicht zum eingestellten Eingang oder wird nicht unterstützt (z. B. Word). Details in der Logdatei.").format(
                    namen=namen
                )
                + (
                    "\n"
                    + _("Word/ODT: als PDF speichern und unter „Nur PDF“ anlernen, oder als CSV exportieren. .xls: als .xlsx speichern.")
                    if any(p.suffix.lower() in NICHT_UNTERSTUETZT for p, _g in auswahl.uebersprungen)
                    else ""
                ),
            )
        if not auswahl.dateien:
            self.toast(
                "info",
                _("Nichts zum Umwandeln"),
                _("In der Auswahl ist keine passende CSV-, XML-, Excel/ODS- oder PDF-Datei."),
            )
            return False
        if not self.arbeiter.umwandeln(auswahl.dateien):
            return False
        self._manuell = True
        self.b_jetzt.setEnabled(False)
        self.b_umwandeln.setEnabled(False)
        self.l_status.setText(_("Umwandeln läuft: {n} Datei(en)").format(n=len(auswahl.dateien)))
        return True

    @staticmethod
    def _lokale_pfade(ev) -> list[Path]:
        md = ev.mimeData()
        if md is None or not md.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in md.urls() if u.isLocalFile() and u.toLocalFile()]

    def dragEnterEvent(self, ev) -> None:  # noqa: N802 (Qt)
        pfade = self._lokale_pfade(ev)
        if not pfade:
            ev.ignore()
            return
        ev.acceptProposedAction()
        if len(pfade) == 1:
            t = _("Loslassen zum Umwandeln: {name}").format(name=pfade[0].name)
        else:
            t = _("Loslassen zum Umwandeln: {n} Dateien/Ordner").format(n=len(pfade))
        if not self._umwandeln_moeglich(melden=False):
            t = (
                _("Erst die Einrichtung abschließen")
                if self.einrichtung_fehlt()
                else _("Gerade läuft eine Verarbeitung")
            )
        self.l_ablage.setText(t)
        self._ablage_zeigen(True)

    def dragMoveEvent(self, ev) -> None:  # noqa: N802 (Qt)
        if self._lokale_pfade(ev):
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev) -> None:  # noqa: N802 (Qt)
        self._ablage_zeigen(False)
        super().dragLeaveEvent(ev)

    def dropEvent(self, ev) -> None:  # noqa: N802 (Qt)
        self._ablage_zeigen(False)
        pfade = self._lokale_pfade(ev)
        if not pfade:
            ev.ignore()
            return
        ev.acceptProposedAction()
        QTimer.singleShot(0, lambda: self.umwandeln(pfade))  # Drag-Quelle nicht blockieren

    def _ablage_zeigen(self, an: bool) -> None:
        if an:
            cw = self.centralWidget()
            self.ablage.setGeometry(cw.rect().adjusted(16, 72, -16, -16))
            self.ablage.raise_()
            self.ablage.show()
        else:
            self.ablage.hide()

    def _starthinweis_bauen(self) -> QFrame:
        """Karte oben im Hauptfenster (kein Popup, blinkt nicht). Farben wie ein Hinweis-Toast."""
        c = self.c
        w = QFrame()
        w.setObjectName("starthinweis")
        w.setStyleSheet(
            f"QFrame#starthinweis {{ background:{c['in_bg']}; border:1px solid {c['busy']};"
            f" border-radius:6px; }} QFrame#starthinweis QLabel {{ color:{c['in_t']}; border:none;"
            " background:transparent; }"
        )
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 6, 6, 12)
        v.setSpacing(4)
        kopf = QHBoxLayout()
        kopf.setSpacing(10)
        kopf.addWidget(Punkt(c["busy"], 12))
        titel = lbl(_("Ohne Gewährleistung und ohne Support"), umbruch=True)
        titel.setStyleSheet("font-weight:bold; font-size:15px;")
        kopf.addWidget(titel, 1)
        zu = knopf(
            "×", tip=_("Hinweis schließen"), klick=lambda: self._starthinweis_schliessen(False)
        )
        zu.setFixedSize(48, 48)
        zu.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; color:{c['in_t']}; font-size:20px;"
            " min-width:48px; min-height:48px; padding:0; }"
        )
        kopf.addWidget(zu)
        v.addLayout(kopf)
        text = lbl(
            _(
                "Fakturafalter ist freie Software unter der Apache-Lizenz 2.0. Sie wird ohne Gewährleistung "
                "bereitgestellt (Abschnitt 7) und ohne Haftung für Schäden (Abschnitt 8). Es gibt keinen "
                "Support. Prüfe erzeugte Rechnungen, bevor du sie verschickst."
            ),
            umbruch=True,
        )
        text.setStyleSheet("font-size:13px;")
        text.setContentsMargins(22, 0, 8, 4)
        v.addWidget(text)
        knoepfe = QHBoxLayout()
        knoepfe.setContentsMargins(0, 0, 8, 0)
        knoepfe.addStretch()
        stil = (
            f"QPushButton {{ background:transparent; color:{c['in_t']}; border:2px solid {c['busy']};"
            " border-radius:6px; min-height:44px; padding:0 14px; }"
        )
        self.b_nie = knopf(
            _("Nicht mehr anzeigen"), klick=lambda: self._starthinweis_schliessen(True)
        )
        self.b_hinweis_zu = knopf(
            _("Schließen"), klick=lambda: self._starthinweis_schliessen(False)
        )
        for b in (self.b_nie, self.b_hinweis_zu):
            b.setStyleSheet(stil)
            knoepfe.addWidget(b)
        v.addLayout(knoepfe)
        log.info(
            "Hinweis beim Start: freie Software (Apache-2.0), ohne Gewährleistung (§7) und Haftung (§8), "
            "kein Support",
            extra=logdatei.NUR_DATEI,
        )
        return w

    def _starthinweis_schliessen(self, fuer_immer: bool) -> None:
        self._starthinweis_zu = True
        if self.starthinweis is not None:
            self.starthinweis.hide()
            self.starthinweis.deleteLater()
            self.starthinweis = None
        if not fuer_immer:
            return
        self.ui["starthinweis_aus"] = True
        roh = dict(self.k.roh)
        roh["oberflaeche"] = {**(roh.get("oberflaeche") or {}), "starthinweis_aus": True}
        try:
            orte.speichern(self.konfig_pfad, roh)
            self.k.roh = roh
            log.info("Starthinweis: „Nicht mehr anzeigen“ gespeichert", extra=logdatei.NUR_DATEI)
        except OSError as e:
            self.toast("fehler", _("Einstellung nicht gespeichert"), str(e))

    def _aufgabe(self, art: str, knopf_text: str, klick, primary: bool = False):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        l_ = lbl("", art, umbruch=True)
        h.addWidget(l_, 1)
        b = knopf(knopf_text, primary=primary, klick=klick)
        b.setMinimumWidth(130)
        h.addWidget(b)
        return w, l_, b

    def _tray_menue(self) -> None:
        if not self.tray:
            return
        menue = QMenu(self)
        self.a_zeigen = QAction(_("Anzeigen"), menue, triggered=self.anzeigen)
        self.a_pause = QAction("", menue, triggered=self.pause_umschalten)
        self.a_eingang = QAction(
            _("Eingang öffnen"), menue, triggered=lambda: aktionen.oeffnen(self.k.eingang)
        )
        self.a_ende = QAction(_("Beenden"), menue, triggered=self.beenden)
        menue.addAction(self.a_zeigen)
        menue.addAction(self.a_pause)
        menue.addAction(self.a_eingang)
        menue.addSeparator()
        menue.addAction(self.a_ende)
        old = self.tray.contextMenu()
        self.tray.setContextMenu(menue)
        if old:
            old.deleteLater()
        self._tray_auffrischen()

    # ======================================================================== Zustand
    def _zustand(self, z: str) -> None:
        self.zust = z
        aktiv = z == "aktiv"
        farbe = {"aktiv": self.c["ok"], "fehler": self.c["err"], "einrichten": self.c["busy"]}.get(
            z, self.c["off"]
        )
        self.punkt.farbe(farbe)
        self.l_titel.setText(
            {
                "aktiv": _("Überwachung aktiv"),
                "fehler": _("Überwachung gestoppt (Fehler)"),
                "einrichten": _("Einrichtung unvollständig"),
            }.get(z, _("Überwachung pausiert"))
        )
        self.b_pause.blockSignals(True)
        self.b_pause.setChecked(aktiv)
        self.b_pause.blockSignals(False)
        self.b_pause._text()
        self.b_pause.update()
        self.b_pause.setEnabled(z != "einrichten" and not self._einst_offen)
        self.b_jetzt.setEnabled(aktiv and not self._beschaeftigt())
        self.b_umwandeln.setEnabled(
            z != "einrichten" and not self._einst_offen and not self._beschaeftigt()
        )
        fehlt = self.einrichtung_fehlt()
        self.l_einricht.setText(_("Noch einzurichten: {was}").format(was=", ".join(fehlt)))
        self._pruefmodul_text()
        self._status_text()
        self.aktualisieren()

    def _pruefmodul_text(self) -> None:
        """Statusleiste: Prüfung nach Erstellung an/aus/Werkzeuge fehlen (ausgegraut, wenn nicht aktiv)."""
        from .. import validierung

        da = validierung.bereit()
        an = da and self.k.nachpruefen
        self.l_pruefmodul.setText(
            _("Prüfung: an") if an else _("Prüfung: aus") if da else _("Prüfung: Werkzeuge fehlen")
        )
        self.l_pruefmodul.setToolTip(
            validierung.werkzeug_versionen()
            if da
            else _("Ordner „werkzeuge“ neben dem Programm nicht gefunden")
        )
        self.l_pruefmodul.setEnabled(an)

    def _status_text(self, wart: int | None = None) -> None:
        z = self.zust
        if z == "aktiv":
            wart = daten.wartend(self.k) if wart is None else wart
            t = (
                _("Verarbeitung läuft")
                if self._beschaeftigt()
                else _("Bereit – wartet auf Dateien im Eingang.")
                if not wart
                else _("{n} Datei(en) im Eingang – warte, bis sie fertig geschrieben sind.").format(
                    n=wart
                )
            )
        elif z == "einrichten":
            t = _("Startet, sobald die Einstellungen vollständig sind.")
        elif z == "fehler":
            t = _("Details in der Logdatei. Mit dem Schalter „Überwachung“ neu starten.")
        elif self._einst_offen:
            t = _("Ruht, solange die Einstellungen offen sind.")
        else:
            t = _("Neue Dateien im Eingang bleiben liegen, bis du die Überwachung einschaltest.")
        self.l_status.setText(t)

    def _offen(self) -> tuple[int, int]:
        return len(daten.prueffaelle(self.k)), len(daten.fehlerberichte(self.k))

    def _tray_farbe(self, n_pr: int | None = None, n_fe: int | None = None) -> str:
        if n_pr is None or n_fe is None:
            n_pr, n_fe = self._offen()
        if self.zust == "fehler" or n_fe:
            return self.c["err"]
        if n_pr:
            return self.c["busy"]
        return self.c["ok"] if self.zust == "aktiv" else self.c["off"]

    def _tray_auffrischen(self, n_pr: int | None = None, n_fe: int | None = None) -> None:
        if not self.tray:
            return
        if n_pr is None or n_fe is None:
            n_pr, n_fe = self._offen()
        sig = (self._tray_farbe(n_pr, n_fe), n_pr + n_fe)
        if sig != self._tray_sig:  # Symbol nur bei Änderung neu setzen (kein Flackern)
            self._tray_sig = sig
            self.tray.setIcon(symbol(sig[0], zahl=sig[1]))
        tip = f"Fakturafalter – {self.l_titel.text()}"
        if n_pr or n_fe:
            tip += " · " + self._aufgaben_text(n_pr, n_fe)
        self.tray.setToolTip(tip)
        if hasattr(self, "a_pause"):
            self.a_pause.setText(_("Pausieren") if self.zust == "aktiv" else _("Fortsetzen"))
            self.a_pause.setEnabled(self.zust != "einrichten")

    @staticmethod
    def _pruef_text(n: int) -> str:
        return (
            _("1 Rechnung braucht deine Prüfung")
            if n == 1
            else _("{n} Rechnungen brauchen deine Prüfung").format(n=n)
        )

    @staticmethod
    def _fehler_text(n: int) -> str:
        return (
            _("1 Datei mit Fehler – nicht erstellt")
            if n == 1
            else _("{n} Dateien mit Fehler – nicht erstellt").format(n=n)
        )

    def _aufgaben_text(self, n_pr: int, n_fe: int) -> str:
        if n_pr and n_fe:
            return _("{pr} zu prüfen, {fe} mit Fehler").format(pr=n_pr, fe=n_fe)
        return self._pruef_text(n_pr) if n_pr else self._fehler_text(n_fe)

    # ======================================================================== Anzeige auffrischen
    def aktualisieren(self) -> None:
        k = self.k
        n_heute = daten.heute_erstellt(k)
        n_pr, n_fe = self._offen()
        fehlt = bool(self.einrichtung_fehlt())
        self.einricht_zeile.setVisible(fehlt)
        self.pruef_zeile.setVisible(bool(n_pr))
        self.fehler_zeile.setVisible(bool(n_fe))
        n_an = len(anlernen.warteschlange(k))
        self.anlern_zeile.setVisible(bool(n_an))
        self.l_anlern.setText(
            _("1 Rechnung wartet aufs Anlernen")
            if n_an == 1
            else _("{n} Rechnungen warten aufs Anlernen").format(n=n_an)
        )
        warten = self._warten_text()
        self.l_warten.setText(warten)
        self.l_warten.setVisible(bool(warten))
        self.nichts_zeile.setVisible(not (fehlt or n_pr or n_fe or n_an))
        self.l_nichts.setVisible(not warten)
        self.l_pruef.setText(self._pruef_text(n_pr))
        self.l_fehler.setText(self._fehler_text(n_fe))
        self.l_heute.setText(_("Heute: {n} erstellt").format(n=n_heute))
        letzte = next((e for e in daten.protokoll(k, 20) if e.status == "ok"), None)
        self.l_zuletzt.setText(
            _("Zuletzt: {nr}, {zeit}").format(
                nr=letzte.nummer, zeit=letzte.zeit.strftime("%H:%M") if letzte.zeit else ""
            )
            if letzte and letzte.zeit and letzte.zeit.date() == date.today()
            else _("Noch nichts erstellt heute.")
        )
        self._tray_auffrischen(n_pr, n_fe)
        if self.zust == "aktiv":
            self._status_text()
            self.b_jetzt.setEnabled(not self._beschaeftigt())

    # ======================================================================== Aktionen
    def pause_umschalten(self) -> None:
        # Kein Toast: Statuskarte und Schalter zeigen den neuen Zustand, sobald der Wächter ihn meldet
        if self.zust == "aktiv":
            self.arbeiter.pausieren()
        elif not self.einrichtung_fehlt():
            self.arbeiter.starten()
        self.b_pause.blockSignals(True)
        self.b_pause.setChecked(self.zust == "aktiv")  # bis zur Rückmeldung den alten Stand zeigen
        self.b_pause.blockSignals(False)
        self.b_pause._text()

    def jetzt_einlesen(self) -> None:
        if self.zust != "aktiv" or not self.arbeiter.jetzt_einlesen():
            return
        self.b_jetzt.setEnabled(False)
        self.l_status.setText(_("Verarbeitung läuft"))

    def protokoll_umschalten(self) -> None:
        """Strg+L: Protokoll (alle Vorgänge) öffnen."""
        self.pruefansicht_oeffnen(2)

    def toast(
        self, art: str, titel: str, detail: str = "", aktion=None, bei_aktion=None, schluessel=None
    ):
        return self.toasts.zeigen(
            self.c, art, titel, detail, aktion, bei_aktion, schluessel=schluessel
        )

    def _beschaeftigt(self) -> bool:
        return self._laeuft or self.arbeiter.beschaeftigt

    def _warten_text(self) -> str:
        """Karte „Zu tun“: Datei wartet bei PDF + CSV/XML noch auf ihr Gegenstück (Überwachung)."""
        if not self.k.pdf_als_gegenstueck():
            return ""
        wartend = self.arbeiter.wartend
        if not wartend:
            return ""
        daten_art = "CSV" if self.k.ist_csv() else "XML"
        pdfs = [p for p in wartend if p.suffix.lower() == ".pdf"]
        if len(wartend) == 1:
            return (
                _("{datei} wartet auf die passende {art}")
                if pdfs
                else _("{datei} wartet auf das passende PDF")
            ).format(datei=wartend[0].name, art=daten_art)
        return _("{n} Dateien warten auf die passende CSV/XML bzw. das PDF").format(n=len(wartend))

    def _bei_fortschritt(self, stand) -> None:
        """Stand aus dem Arbeitsthread (queued): Bereich zeigen, „Jetzt einlesen“ ausgrauen. Kein Toast.
        ``None``: Lauf abgebrochen (Ausnahme, Details im Log) – Bereich ausblenden."""
        if stand is None:
            self._lauf_ende()
            self.b_jetzt.setEnabled(self.zust == "aktiv")
            self.b_umwandeln.setEnabled(self.zust != "einrichten" and not self._einst_offen)
            return
        if not self._laeuft:
            self._laeuft = True
            self.l_bereit.setText("")
            self.b_jetzt.setEnabled(False)
            self.b_umwandeln.setEnabled(False)
            if self.zust == "aktiv":
                self.l_status.setText(_("Verarbeitung läuft"))
        self.fortschritt.setzen(stand)
        self._toast_abstand()

    def _lauf_ende(self) -> None:
        self._laeuft = False
        self.fortschritt.zuruecksetzen()
        self.l_bereit.setText(_("Bereit"))
        self._toast_abstand()

    def _toast_abstand(self) -> None:
        """Toasts sitzen über dem Fortschrittsbereich, damit der Balken sichtbar bleibt."""
        extra = self.fortschritt.sizeHint().height() if self.fortschritt.isVisible() else 0
        self.toasts.abstand_unten = 48 + extra
        self.toasts.ordnen()

    def _bei_lauf(self, lauf) -> None:
        """Erfolg: kein Toast (nur der Zähler steigt). Prüfen: Toast „N verarbeitet, M prüfen“ mit „Prüfen“.
        Fehler: EIN zusammengefasster Toast."""
        self._lauf_ende()
        manuell, self._manuell = self._manuell, False
        self.b_jetzt.setEnabled(self.zust == "aktiv")
        self.b_umwandeln.setEnabled(self.zust != "einrichten" and not self._einst_offen)
        if lauf is None:
            self.aktualisieren()
            if manuell:
                self._status_text()
                return
            self.l_status.setText(
                _("Eingang ist leer – keine lesbaren CSV-, XML- oder PDF-Dateien.")
            )
            return
        if manuell:
            self._status_text()
        for vorlage, werte in getattr(lauf, "meldungen", []):  # z. B. Protokoll fehlt (kein Halt)
            self.toast(
                "info",
                _("Hinweis zum Protokoll"),
                _(vorlage).format(**werte),
                schluessel="protokoll",
            )
        neu_pr = any(e.status == "pruefen" for e in lauf.ergebnisse)
        neu_fe = bool(lauf.datei_fehler) or any(e.status == "fehler" for e in lauf.ergebnisse)
        self.aktualisieren()
        if neu_pr and not neu_fe and not self._offen()[1]:
            self.fertig_toast(lauf)
        elif neu_pr or neu_fe:
            self.hinweis_toast()
        elif manuell:
            n = sum(e.status == "ok" for e in lauf.ergebnisse)
            self.toast(
                "ok",
                _("{n} Rechnung(en) umgewandelt").format(n=n),
                _("Die Dateien liegen im Ausgang. Die Originale sind unverändert."),
                _("Ausgang öffnen"),
                lambda: aktionen.oeffnen(self.k.ausgang),
            )
        if self.pruef_fenster is not None and self.pruef_fenster.isVisible():
            self.pruef_fenster.aktualisieren()

    def fertig_toast(self, lauf):
        """Ende eines Laufs mit Prüffällen: „12 verarbeitet, 1 prüfen“, Knopf „Prüfen“ (48 px)."""
        n = len(lauf.ergebnisse)
        m = sum(e.status == "pruefen" for e in lauf.ergebnisse)
        titel = _("{n} verarbeitet, {m} prüfen").format(n=n, m=m)
        detail = (
            _("Eine Rechnung wartet auf deine Prüfung.")
            if m == 1
            else _("{m} Rechnungen warten auf deine Prüfung.").format(m=m)
        )
        return self.toast(
            "info",
            titel,
            detail,
            _("Prüfen"),
            lambda: self.pruefansicht_oeffnen(0),
            schluessel="aufgaben",
        )

    def hinweis_toast(self):
        """Ein Toast für alles Offene; ein noch sichtbarer wird aktualisiert statt gestapelt."""
        n_pr, n_fe = self._offen()
        if not (n_pr or n_fe):
            return None
        titel = self._aufgaben_text(n_pr, n_fe)
        detail = (
            _("Alle anderen Rechnungen wurden erstellt.")
            if n_pr and not n_fe
            else _("Details stehen im Fehlerbericht.")
            if n_fe and not n_pr
            else ""
        )
        return self.toast(
            "fehler" if n_fe else "info",
            titel,
            detail,
            _("Ansehen"),
            lambda: self.pruefansicht_oeffnen(0 if n_pr else 1),
            schluessel="aufgaben",
        )

    def pruefansicht_oeffnen(self, reiter: int = 0) -> None:
        from .pruefansicht import Pruefansicht

        if self.pruef_fenster is None:
            self.pruef_fenster = Pruefansicht(self)
        self.pruef_fenster.aktualisieren()
        self.pruef_fenster.reiter.setCurrentIndex(reiter)
        self.pruef_fenster.show()
        self.pruef_fenster.raise_()
        self.pruef_fenster.activateWindow()

    def einrichtung_oeffnen(self) -> None:
        """Erststart-Assistent (Ordner → Absender → Rechnungen anlernen → Fertig)."""
        from .einrichtung import Einrichtung

        Einrichtung(self).exec()
        self.aktualisieren()

    def anlernen_oeffnen(
        self, dateien: list[Path] | None = None, eltern=None, bereiche: bool = False
    ) -> bool:
        """Anlern-Assistent: gewählte PDFs, sonst die Warteschlange, sonst Dateiauswahl."""
        from .anlernen import AnlernAssistent

        if dateien:
            pdfs = anlernen.in_warteschlange(self.k, [Path(d) for d in dateien])
        else:
            pdfs = anlernen.warteschlange(self.k)
        if not pdfs:
            gew, _f = QFileDialog.getOpenFileNames(
                eltern or self,
                _("Rechnungen zum Anlernen"),
                str(Path.home()),
                _("PDF-Dateien (*.pdf)"),
            )
            if not gew:
                return False
            pdfs = anlernen.in_warteschlange(self.k, [Path(d) for d in gew])
        dlg = AnlernAssistent(
            eltern or self, self.k, self.konfig_pfad, pdfs, self.c, bereiche_zuerst=bereiche
        )
        ok = bool(dlg.exec())
        self.einstellungen_uebernehmen(orte.lesen(self.konfig_pfad))
        return ok


    def _profilhinweise(self) -> None:
        """Alte Profile und geänderte Einstellungen klar anzeigen, Dateien unangetastet lassen."""
        import os

        from PySide6.QtWidgets import QMessageBox

        # Automatisierte Tests dürfen nicht an modalen Dialogen hängen bleiben.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return

        for hinweis in getattr(self.k, "konfig_hinweise", None) or []:
            QMessageBox.information(self, _("Hinweis zu den Einstellungen"), hinweis)
        from . import profilablehnung

        gesehen = set()
        for _pfad, meldung, *rest in getattr(self.k, "abgelehnte_profile", None) or []:
            titel = rest[0] if rest else None
            if meldung in gesehen:
                continue
            gesehen.add(meldung)
            if profilablehnung.zeigen(self, meldung, titel):
                self.datenassistent_oeffnen("csv")
                break

    def einstellungen_oeffnen(self, bereich: int | str = 0) -> None:
        """Während die Einstellungen offen sind, ruht die Überwachung (keine halb geänderte Konfiguration im
        Lauf); danach läuft sie nur weiter, wenn sie vorher an war und nichts mehr fehlt."""
        from .einstellungen import Einstellungen

        war_aktiv = self.zust in (
            "aktiv",
            "einrichten",
        )  # „einrichten“: nach dem Vervollständigen starten
        if self.zust == "aktiv":
            self.arbeiter.pausieren()
        self._einst_offen = True
        self.b_pause.setEnabled(False)
        try:
            dlg = Einstellungen(self, bereich)
            if dlg.exec():
                self.einstellungen_uebernehmen(dlg.ergebnis(), dlg.autostart_gewuenscht())
        finally:
            self._einst_offen = False
            if war_aktiv and not self.einrichtung_fehlt():
                self.arbeiter.starten()
            else:
                self._zustand(self.zust)

    def datenassistent_oeffnen(
        self, art: str, eltern=None, profil: dict | None = None, start: str | None = None
    ) -> bool:
        """CSV- oder XML-Assistent; speichert selbst über :meth:`einstellungen_uebernehmen`."""
        from .datenassistent import CsvAssistent, XmlAssistent

        dlg = (
            CsvAssistent(self, eltern or self, profil, start=start)
            if art == "csv"
            else XmlAssistent(self, eltern or self)
        )
        return bool(dlg.exec())

    def einstellungen_uebernehmen(self, roh: dict, autostart_an: bool | None = None) -> bool:
        from ..konfig import lade_konfig as _lade

        alt_roh = self.k.roh
        orte.speichern(self.konfig_pfad, roh)
        try:
            k = _lade(self.konfig_pfad)
        except Exception as e:  # noqa: BLE001 – unlesbare Konfiguration
            orte.speichern(self.konfig_pfad, alt_roh)
            self.toast("fehler", _("Einstellungen nicht übernommen"), f"{type(e).__name__}: {e}")
            return False
        # Fehlende Profildateien wurden beim Laden weggelassen – Liste dauerhaft bereinigen.
        if any(
            (k.roh.get(s) or []) != (roh.get(s) or [])
            for s in ("csv_profile", "pdf_profile", "pdf_vorlagen")
        ):
            orte.speichern(self.konfig_pfad, k.roh)
        if autostart_an is not None:
            from . import autostart

            try:
                if autostart_an != autostart.ist_aktiv():
                    autostart.setzen(autostart_an, self.konfig_pfad)
            except OSError as e:
                self.toast("fehler", _("Autostart nicht geändert"), str(e))
        alt_sprache, alt_thema = self.ui["sprache"], self.ui["thema"]
        self.k, self.ui = k, orte.ui_optionen(k.roh)
        logdatei.anonym_setzen(k.logs_anonym, k)
        sprache_setzen(self.ui["sprache"])
        self.c = thema.anwenden(QApplication.instance(), self.ui["thema"])
        war_aktiv = self.zust == "aktiv"
        self.arbeiter.neu_konfigurieren(k, bool(k.roh.get("optionen", {}).get("polling")))
        if alt_sprache != self.ui["sprache"] or alt_thema != self.ui["thema"]:
            self._tray_sig = None
            self._aufbauen()
            self._tray_menue()
            if self.pruef_fenster is not None:
                self.pruef_fenster.close()
                self.pruef_fenster.deleteLater()
                self.pruef_fenster = None
        if self.einrichtung_fehlt():
            if war_aktiv:
                self.arbeiter.pausieren()
            self._zustand("einrichten")
        elif self.zust == "einrichten":
            if self._einst_offen:
                self._zustand("pausiert")
            else:
                self.arbeiter.starten()
        else:
            self._zustand(self.zust)
        self.aktualisieren()
        log.info("Einstellungen gespeichert: %s", self.konfig_pfad)
        return True

    # ======================================================================== Fenster / Tray
    def anzeigen(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_klick(self, grund) -> None:
        if grund in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.hide() if self.isVisible() and not self.isMinimized() else self.anzeigen()

    def closeEvent(self, ev) -> None:
        if not self._wirklich_beenden and self.tray and self.ui.get("schliessen_in_tray", True):
            ev.ignore()
            self.hide()
            if not self.ui.get("tray_hinweis_gezeigt"):
                self.tray.showMessage(
                    "Fakturafalter",
                    _("Läuft im Infobereich weiter. Beenden über das Tray-Menü."),
                    symbol(self._tray_farbe()),
                    6000,
                )
                self.ui["tray_hinweis_gezeigt"] = True
                roh = dict(self.k.roh)
                roh["oberflaeche"] = {
                    **(roh.get("oberflaeche") or {}),
                    "tray_hinweis_gezeigt": True,
                }
                try:
                    orte.speichern(self.konfig_pfad, roh)
                    self.k.roh = roh
                except OSError:
                    pass
            return
        self._aufraeumen()
        ev.accept()
        QApplication.instance().quit()

    def beenden(self) -> None:
        self._wirklich_beenden = True
        self.close()

    def _aufraeumen(self) -> None:
        self.timer.stop()
        self.arbeiter.beenden()
        if self.pruef_fenster is not None:
            self.pruef_fenster.close()
        if self.tray:
            self.tray.hide()
