# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Fortschritt der Verarbeitung im Hauptfenster: eigener Bereich über der Statusleiste, nur während eines Laufs.

Textzeile („Rechnung 3 von 12 · Prüfen (KoSIT) · Datei“), ruhiger Balken (Rechnungen × 6 Schritte, ohne
Animation) und sechs Schritte mit Symbol und Kurztext. Die Beschriftung hängt von der Eingabe ab
(nur PDF, PDF + CSV, PDF + XML, ohne PDF). Nichts blinkt; Details stehen im Log."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from .bausteine import Balken, Zustand
from .texte import _, sprache

SCHRITTE = 6


def _pruefen() -> str:
    """„Prüfen“ heißt als Schritt „Validate“ (der Knopf „Prüfen“ = „Review“ bleibt, wie er ist)."""
    return "Validate" if sprache() == "en" else "Prüfen"


def schritt_namen(eingabe: str) -> list[tuple[str, str]]:
    """-> sechs (Kurztext, Langtext) je Eingabeart: pdf | pdf_csv | pdf_xml | csv | xml (ohne PDF)."""
    daten = "xml" if eingabe.endswith("xml") else "csv" if eingabe.endswith("csv") else ""
    ohne_pdf = eingabe in ("csv", "xml")
    zwei = (
        (_("Einlesen"), _("Einlesen (CSV)") if daten == "csv" else _("Einlesen (XML)"))
        if daten
        else (_("Erkennen"), _("Erkennen"))
    )
    drei = (_("XML"), _("XML übernehmen") if daten == "xml" else _("XML erzeugen"))
    vier = (_("Sichtseite"), _("Sichtseite (PDF/A)")) if ohne_pdf else (_("PDF/A"), _("PDF/A"))
    return [
        (_("Lesen"), _("Lesen")),
        zwei,
        drei,
        vier,
        (_pruefen(), _pruefen()),
        (_("Ablegen"), _("Ablegen")),
    ]


def text_zeile(stand) -> str:
    """Gesamtstand · aktueller Schritt · Datei. Bei einer einzelnen Datei/Rechnung entfällt „1 von 1“."""
    lang = schritt_namen(stand.eingabe)[stand.schritt][1]
    if stand.schritt == 4 and stand.werkzeug:
        lang = _("Prüfen ({werkzeug})").format(werkzeug=stand.werkzeug)
    teile = []
    if stand.gesamt > 1:
        if stand.nr and stand.zaehlt == "datei":
            teile.append(_("Datei {nr} von {n}").format(nr=stand.nr, n=stand.gesamt))
        elif stand.nr:
            teile.append(_("Rechnung {nr} von {n}").format(nr=stand.nr, n=stand.gesamt))
        else:
            teile.append(_("{n} Rechnungen").format(n=stand.gesamt))
    teile.append(lang)
    if stand.datei:
        teile.append(stand.datei)
    return " · ".join(teile)


class FortschrittsBereich(QFrame):
    """Bereich über der Statusleiste. ``setzen(stand)`` zeigt ihn, ``zuruecksetzen()`` blendet ihn aus."""

    def __init__(self, c: dict, parent=None):
        super().__init__(parent)
        self.c = c
        self.setObjectName("fortschritt")
        self.setStyleSheet(
            f"QFrame#fortschritt {{ background:{c['card']}; border-top:1px solid {c['bar_b']}; }}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 8, 16, 8)
        v.setSpacing(6)
        self.l_fehler = QLabel("")
        self.l_fehler.setWordWrap(True)
        self.l_fehler.setStyleSheet(
            f"color:{c['er_t']}; background:{c['er_bg']}; border:1px solid {c['err']};"
            " border-radius:4px; padding:4px 8px; font-size:13px;"
        )
        self.l_fehler.hide()
        v.addWidget(self.l_fehler)
        kopf = QHBoxLayout()
        self.l_text = QLabel("")
        self.l_text.setWordWrap(True)
        self.l_text.setStyleSheet("font-size:14px; font-weight:bold;")
        self.l_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.l_prozent = QLabel("")
        self.l_prozent.setStyleSheet("font-size:14px; font-weight:bold;")
        kopf.addWidget(self.l_text, 1)
        kopf.addWidget(self.l_prozent)
        v.addLayout(kopf)
        self.balken = Balken(c)
        v.addWidget(self.balken)
        reihe = QHBoxLayout()
        reihe.setSpacing(6)
        self.kreise: list[Zustand] = []
        self.texte: list[QLabel] = []
        self.linien: list[QFrame] = []
        for i in range(SCHRITTE):
            if i:
                linie = QFrame()
                linie.setFixedHeight(2)
                linie.setMinimumWidth(8)
                reihe.addWidget(linie, 1)
                self.linien.append(linie)
            k = Zustand(c, "aus", 22, str(i + 1))
            t = QLabel("")
            t.setWordWrap(True)
            reihe.addWidget(k)
            reihe.addWidget(t)
            self.kreise.append(k)
            self.texte.append(t)
        v.addLayout(reihe)
        self.stand = None
        self.hide()

    def setzen(self, stand) -> None:
        self.stand = stand
        self.l_text.setText(text_zeile(stand))
        self.l_prozent.setText(f"{round(stand.anteil * 100)} %")
        self.balken.setzen(stand.anteil)
        for i, ((kurz, _lang), k, t) in enumerate(
            zip(schritt_namen(stand.eingabe), self.kreise, self.texte)
        ):
            if i < stand.schritt:
                k.setzen("erkannt", "")
                t.setStyleSheet(f"color:{self.c['fg']}; font-size:13px;")
            elif i == stand.schritt:
                k.setzen("aktiv", str(i + 1))
                t.setStyleSheet("font-weight:bold; font-size:13px;")
            else:
                k.setzen("aus", str(i + 1))
                t.setStyleSheet(f"color:{self.c['sub']}; font-size:13px;")
            t.setText(kurz)
        for i, linie in enumerate(self.linien):
            linie.setStyleSheet(
                f"background:{self.c['ok'] if i < stand.schritt else self.c['card_b']};"
            )
        if stand.fehler:
            self.l_fehler.setText(
                _("{datei}: Fehler – liegt im Ordner Fehler. Verarbeitung läuft weiter.").format(
                    datei=stand.fehler
                )
            )
            self.l_fehler.show()
        self.show()

    def zuruecksetzen(self) -> None:
        self.stand = None
        self.l_fehler.hide()
        self.l_fehler.setText("")
        self.hide()
