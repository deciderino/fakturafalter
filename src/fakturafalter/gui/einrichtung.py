# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Ersteinrichtung nach Skizze 13: Ordner → Absender → Rechnungen anlernen → Fertig.

Jeder Schritt speichert sofort (Abbrechen verliert nichts). Alles lässt sich später in den Einstellungen ändern."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..konfig import UNTERORDNER
from . import aktionen
from .absender_form import AbsenderFormular, in_roh, pflicht_fehlt
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

SCHRITTE = ("Ordner", "Absender", "Rechnungen anlernen", "Fertig")
ORDNER_TEXT = {
    "Eingang": "hier legst du Rechnungen ab (PDF, CSV oder XML, je nach Eingangsformat)",
    "Ausgang": "fertige E-Rechnungen",
    "Pruefen": "braucht deinen Blick, z. B. neues Layout",
    "Fehler": "konnte nicht erstellt werden, mit Begründung",
    "Erledigt": "verarbeitete Originale",
}


class Einrichtung(QDialog):
    def __init__(self, haupt):
        super().__init__(haupt)
        self.haupt = haupt
        self.c = haupt.c
        self.pdfs: list[Path] = []
        self.angelernt = 0
        self.setWindowTitle(_("Fakturafalter einrichten"))
        self.setObjectName("wurzel")
        self.resize(960, 800)
        self.toasts = ToastStapel(self, abstand_unten=90)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        kopf, kv, _t = kopfleiste(
            _("Fakturafalter einrichten"), _("Vier kurze Schritte, danach läuft alles von selbst.")
        )
        self.schritte = Schritte(self.c, [_(s) for s in SCHRITTE])
        kv.addWidget(self.schritte)
        v.addWidget(kopf)
        self.stapel = QStackedWidget()
        for seite in (
            self._seite_ordner(),
            self._seite_absender(),
            self._seite_anlernen(),
            self._seite_fertig(),
        ):
            self.stapel.addWidget(rollen(seite))
        v.addWidget(self.stapel, 1)

        fuss, links, self.l_fuss, rechts = fussleiste(self.c)
        self.b_spaeter = knopf(_("Später einrichten"), klick=self._spaeter)
        self.b_zurueck = knopf(_("Zurück"), klick=lambda: self.gehe(self.i - 1))
        links.addWidget(self.b_spaeter)
        links.addWidget(self.b_zurueck)
        self.b_weiter = knopf(_("Weiter"), primary=True, klick=self._weiter)
        self.b_weiter.setDefault(True)
        rechts.addWidget(self.b_weiter)
        v.addWidget(fuss)
        self.i = 0
        self.gehe(0)

    def toast(self, art, titel, detail=""):
        return self.toasts.zeigen(self.c, art, titel, detail)

    # ======================================================================== Schritt 1: Ordner
    def _seite_ordner(self) -> QWidget:
        k = self.haupt.k
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 24, 32, 24)
        v.setSpacing(10)
        v.addWidget(lbl(_("Wo sollen deine Rechnungen liegen?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _("Wähle einen Ordner. Fakturafalter legt darin alles Nötige selbst an."),
                "sub",
                umbruch=True,
            )
        )
        v.addWidget(lbl(_("Arbeitsordner")))
        h = QHBoxLayout()
        h.setSpacing(8)
        arb = k.arbeitsordner or Path(k.eingang).parent
        self.arbeitsordner = QLineEdit(str(arb))
        self.arbeitsordner.setObjectName("arbeitsordner")
        self.arbeitsordner.setAccessibleName(_("Arbeitsordner"))
        h.addWidget(self.arbeitsordner, 1)
        h.addWidget(knopf(_("Ändern…"), klick=self._ordner_waehlen))
        v.addLayout(h)
        kt, kv = karte()
        kv.addWidget(lbl(_("Darin entstehen automatisch:"), "sub"))
        for _s, name in UNTERORDNER:
            z = QHBoxLayout()
            z.setSpacing(10)
            n = lbl(name)
            n.setStyleSheet("font-weight:bold;")
            n.setMinimumWidth(110)
            z.addWidget(n)
            z.addWidget(lbl(_(ORDNER_TEXT[name]), "hinweis", umbruch=True), 1)
            kv.addLayout(z)
        v.addWidget(kt)
        self.einzeln = QCheckBox(_("Ordner einzeln festlegen (für Fortgeschrittene)"))
        self.einzeln.setChecked(bool(self.haupt.k.roh.get("ordner")))
        self.einzeln.toggled.connect(lambda an: self.l_einzeln.setVisible(an))
        v.addWidget(self.einzeln)
        self.l_einzeln = lbl(
            _(
                "Die einzelnen Ordner trägst du nach der Einrichtung unter Einstellungen → Ordner ein."
            ),
            "hinweis",
            umbruch=True,
        )
        self.l_einzeln.setVisible(self.einzeln.isChecked())
        v.addWidget(self.l_einzeln)
        v.addStretch(1)
        return w

    def _ordner_waehlen(self) -> None:
        d = QFileDialog.getExistingDirectory(self, _("Arbeitsordner"), self.arbeitsordner.text())
        if d:
            self.arbeitsordner.setText(d)

    # ======================================================================== Schritt 2: Absender
    def _seite_absender(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 24, 32, 24)
        v.setSpacing(10)
        v.addWidget(lbl(_("Wer stellt die Rechnungen aus?"), "titel", umbruch=True))
        v.addWidget(
            lbl(
                _(
                    "Dein Unternehmen als Absender. Am schnellsten: aus einer deiner Rechnungen übernehmen. "
                    "Bei „Nur PDF“ kann jede Vorlage später einen eigenen Absender haben."
                ),
                "sub",
                umbruch=True,
            )
        )
        self.abs_form = AbsenderFormular(self.haupt.k.roh, self.toast, kurz=True)
        v.addWidget(self.abs_form)
        v.addStretch(1)
        return w

    # ======================================================================== Schritt 3: Anlernen
    def _seite_anlernen(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 24, 32, 24)
        v.setSpacing(10)
        v.addWidget(lbl(_("Woher kommen deine Rechnungsdaten?"), "titel", umbruch=True))
        self.modus = QButtonGroup(self)
        jetzt = self.haupt.k.roh.get("modus")
        jetzt = self.haupt.k.modus if jetzt else "csv"
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
            kt, kv = karte()
            r = QRadioButton(titel)
            r.setObjectName(f"modus_{code}")
            r.setProperty("code", code)
            r.setMinimumHeight(48)
            r.setChecked(code == jetzt)
            r.toggled.connect(self._modus_geaendert)
            self.modus.addButton(r)
            kv.addWidget(r)
            for text in hinweise:
                kv.addWidget(lbl(text, "hinweis", umbruch=True))
            v.addWidget(kt)

        self.box_pdf = QFrame()
        self.box_pdf.setStyleSheet(
            f"QFrame#box {{ border:2px dashed {self.c['card_b']}; border-radius:8px; }}"
        )
        self.box_pdf.setObjectName("box")
        bv = QVBoxLayout(self.box_pdf)
        bv.setContentsMargins(20, 16, 20, 16)
        bv.setSpacing(8)
        bv.addWidget(lbl(_("Beispiel-PDFs"), "titel"))
        bv.addWidget(
            lbl(
                _(
                    "Wähle eine oder mehrere echte Rechnungen aus – am besten verschiedene Layouts. "
                    "Pro Rechnung klickst du die Angaben einmal an."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addWidget(knopf(_("PDFs auswählen…"), klick=self._pdfs_waehlen))
        h.addStretch(1)
        bv.addLayout(h)
        self.l_pdfs = lbl("", umbruch=True)
        bv.addWidget(self.l_pdfs)
        v.addWidget(self.box_pdf)
        self.l_csv = QWidget()
        cv = QVBoxLayout(self.l_csv)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.addWidget(
            lbl(
                _(
                    "Wähle eine Beispiel-CSV: Der Assistent erkennt das Format und schlägt vor, welche Spalte "
                    "was bedeutet."
                ),
                "hinweis",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addWidget(knopf(_("CSV einrichten…"), primary=True, klick=lambda: self._assistent("csv")))
        h.addStretch(1)
        cv.addLayout(h)
        v.addWidget(self.l_csv)
        self.l_xml = QWidget()
        xv = QVBoxLayout(self.l_xml)
        xv.setContentsMargins(0, 0, 0, 0)
        xv.addWidget(
            lbl(_("Optional: Probe mit einer XML deiner Software."), "hinweis", umbruch=True)
        )
        h = QHBoxLayout()
        h.addWidget(knopf(_("XML einrichten…"), klick=lambda: self._assistent("xml")))
        h.addStretch(1)
        xv.addLayout(h)
        v.addWidget(self.l_xml)
        v.addStretch(1)
        self._modus_geaendert()
        return w

    def modus_code(self) -> str:
        b = self.modus.checkedButton()
        return b.property("code") if b else "csv"

    def _modus_geaendert(self, *_a) -> None:
        if not hasattr(self, "box_pdf"):
            return
        m = self.modus_code()
        self.box_pdf.setVisible(m == "nur_pdf")
        self.l_csv.setVisible(m == "csv")
        self.l_xml.setVisible(m == "xml")
        if hasattr(self, "b_weiter"):
            self.gehe(self.i)

    def _assistent(self, art: str) -> None:
        if self._sichern():  # Ordner und Absender zuerst, damit die Probe sie kennt
            self.haupt.datenassistent_oeffnen(art, eltern=self)

    def _pdfs_waehlen(self) -> None:
        d, _f = QFileDialog.getOpenFileNames(
            self, _("Beispiel-PDFs"), str(Path.home()), _("PDF-Dateien (*.pdf)")
        )
        if d:
            self.pdfs_setzen([Path(x) for x in d])

    def pdfs_setzen(self, pdfs: list[Path]) -> None:
        self.pdfs = list(pdfs)
        self.l_pdfs.setText(
            "\n".join(p.name for p in self.pdfs[:8])
            + (
                ("\n" + _("… und {n} weitere").format(n=len(self.pdfs) - 8))
                if len(self.pdfs) > 8
                else ""
            )
        )
        self.gehe(self.i)

    # ======================================================================== Schritt 4: Fertig
    def _seite_fertig(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 24, 32, 24)
        v.setSpacing(12)
        v.addWidget(lbl(_("Fertig – Fakturafalter ist bereit."), "titel", umbruch=True))
        self.fertig_zeilen: list[tuple[Zustand, object]] = []
        kt, kv = karte()
        for _n in range(3):
            z = QHBoxLayout()
            z.setSpacing(10)
            sym = Zustand(self.c, "erkannt", 28)
            t = lbl("", umbruch=True)
            z.addWidget(sym, 0, Qt.AlignmentFlag.AlignTop)
            z.addWidget(t, 1)
            kv.addLayout(z)
            self.fertig_zeilen.append((sym, t))
        v.addWidget(kt)
        v.addWidget(
            lbl(
                _(
                    "So geht es weiter: Rechnungen in den Eingang legen. Neue Layouts landen in "
                    "„Zu tun“ zum Anlernen. Alles lässt sich unter Einstellungen ändern."
                ),
                "sub",
                umbruch=True,
            )
        )
        h = QHBoxLayout()
        h.addWidget(
            knopf(_("Eingang öffnen"), klick=lambda: aktionen.oeffnen(self.haupt.k.eingang))
        )
        h.addStretch(1)
        v.addLayout(h)
        v.addStretch(1)
        return w

    def _fertig_fuellen(self) -> None:
        k = self.haupt.k
        e = self.abs_form.werte()
        nur = k.modus == "nur_pdf"
        zeilen = [
            ("erkannt", _("Arbeitsordner: {p}").format(p=k.arbeitsordner or Path(k.eingang).parent))
        ]
        offen = pflicht_fehlt(e)
        if e["name"] and not offen:
            zeilen.append(("erkannt", _("Absender: {n}").format(n=e["name"])))
        else:
            zeilen.append(
                (
                    "pruefen" if not nur else "aus",
                    _("Absender unvollständig – bitte in den Einstellungen ergänzen.")
                    if not nur
                    else _("Kein gemeinsamer Absender – jede Vorlage bringt ihren eigenen mit."),
                )
            )
        if nur:
            n = len(k.pdf_profile)
            zeilen.append(
                (
                    "erkannt" if n else "aus",
                    _("{n} Vorlagen angelernt").format(n=n) if n != 1 else _("1 Vorlage angelernt"),
                )
            )
        elif k.ist_xml():
            zeilen.append(("erkannt", _("XML (ZUGFeRD / XRechnung)")))
        else:
            zeilen.append(
                (
                    "erkannt" if k.csv_profile else "pruefen",
                    _("CSV: {n} CSV-Profile").format(n=len(k.csv_profile)),
                )
            )
        for (sym, t), (z, text) in zip(self.fertig_zeilen, zeilen):
            sym.setzen(z)
            t.setText(text)

    # ======================================================================== Ablauf
    def gehe(self, i: int) -> None:
        self.i = max(0, min(3, i))
        self.stapel.setCurrentIndex(self.i)
        self.schritte.setzen(self.i)
        self.b_zurueck.setEnabled(0 < self.i < 3)
        self.b_spaeter.setVisible(self.i < 3)
        self.l_fuss.setText(_("Schritt {n} von 4").format(n=self.i + 1))
        if self.i == 2 and self.modus_code() == "nur_pdf" and self.pdfs:
            self.b_weiter.setText(_("Anlernen starten"))
        elif self.i == 2 and self.modus_code() == "nur_pdf":
            self.b_weiter.setText(_("Ohne Anlernen weiter"))
        elif self.i == 3:
            self.b_weiter.setText(_("Fertig"))
        else:
            self.b_weiter.setText(_("Weiter"))
        if self.i == 3:
            self._fertig_fuellen()

    def _roh(self) -> dict:
        r = copy.deepcopy(self.haupt.k.roh)
        if not self.einzeln.isChecked():
            r["arbeitsordner"] = str(Path(self.arbeitsordner.text().strip()).expanduser())
            r.pop("ordner", None)
        in_roh(r, self.abs_form.werte())
        r["modus"] = self.modus_code()
        return r

    def _sichern(self, fertig: bool = False) -> bool:
        r = self._roh()
        if fertig:
            r["oberflaeche"] = {**(r.get("oberflaeche") or {}), "eingerichtet": True}
        return self.haupt.einstellungen_uebernehmen(r)

    def _weiter(self) -> None:
        if self.i == 0 and not self.arbeitsordner.text().strip():
            self.toast("fehler", _("Bitte einen Arbeitsordner angeben."))
            return
        if self.i == 1 and pflicht_fehlt(self.abs_form.werte()) and self.modus_code() != "nur_pdf":
            self.toast(
                "info",
                _("Absender unvollständig"),
                _("Du kannst ihn später in den Einstellungen ergänzen."),
            )
        if self.i == 3:
            self._sichern(fertig=True)
            self.accept()
            return
        if not self._sichern():
            return
        if self.i == 2 and self.modus_code() == "nur_pdf" and self.pdfs:
            self.haupt.anlernen_oeffnen(self.pdfs, eltern=self)
        self.gehe(self.i + 1)

    def _spaeter(self) -> None:
        """Merkt sich nur, dass der Assistent nicht von selbst wieder aufgeht; „Einrichten“ bleibt in „Zu tun“."""
        self._sichern(fertig=True)
        self.reject()
