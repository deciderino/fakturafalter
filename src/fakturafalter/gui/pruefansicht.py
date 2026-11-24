# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Reiter „Zu prüfen“ / „Fehler“ / „Protokoll“ nach Skizze 04."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import pipeline, validierung
from . import aktionen, daten
from .bausteine import Punkt, ToastStapel, karte, knopf, lbl
from .kuerzel import KurzLabel
from .texte import _, hinweis_text, sprache

FELDNAMEN = {
    "Bruttosumme": "Brutto",
    "Nettosumme": "Netto",
    "Umsatzsteuer": "USt",
    "Positionsanzahl": "Positionen",
    "Kundennummer": "Kundennummer",
    "Rechnungsdatum": "Rechnungsdatum",
    "Rechnungsnummer": "Rechnungsnummer",
    "Leistungsdatum": "Leistungsdatum",
    "Leistungszeitraum": "Leistungszeitraum",
    "USt-IdNr.": "USt-IdNr.",
    "Steuernummer": "Steuernummer",
    "IBAN": "IBAN",
    "Steuersatz": "Steuersatz",
}
BETRAGSFELDER = ("Bruttosumme", "Nettosumme", "Umsatzsteuer")
PRUEFZEICHEN = {"gültig": "✓", "ungültig": "✗", "nicht geprüft": "–"}


def _zeit(z) -> str:
    if z is None:
        return ""
    if z.date() == date.today():
        return _("heute {uhr}").format(uhr=z.strftime("%H:%M"))
    return z.strftime("%d.%m.%Y %H:%M" if sprache() == "de" else "%Y-%m-%d %H:%M")


def _wert(feld: str, w: str) -> str:
    if feld in BETRAGSFELDER and w != "fehlt":
        return daten.betrag(w, sprache())
    return w


class Pruefansicht(QWidget):
    def __init__(self, haupt):
        super().__init__(haupt, Qt.WindowType.Window)
        self.haupt = haupt
        self.setObjectName("wurzel")
        self.setWindowTitle(_("Fakturafalter – Prüfen und Protokoll"))
        self.setWindowIcon(haupt.windowIcon())
        self.resize(940, 640)
        self.setMinimumSize(720, 480)
        self.verworfen: dict[str, list] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        self.reiter = QTabWidget()
        self.reiter.setDocumentMode(True)
        v.addWidget(self.reiter)
        self.s_pruef, self.l_pruef = self._scrollseite()
        self.s_fehler, self.l_fehler = self._scrollseite()
        self.protokoll = QPlainTextEdit()
        self.protokoll.setReadOnly(True)
        self.protokoll.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
        )  # lange Hinweise umbrechen
        p = QWidget()
        pv = QVBoxLayout(p)
        pv.setContentsMargins(0, 8, 0, 0)
        self.l_pruefstatus = lbl("", "hinweis", umbruch=True)
        self.l_pruefstatus.setObjectName("pruefstatus")
        pv.addWidget(self.l_pruefstatus)
        pv.addWidget(self.protokoll, 1)
        ph = QHBoxLayout()
        ph.addWidget(
            lbl(
                _("Quelle: protokoll.tsv im Ausgang · Technische Details in der Logdatei"),
                "hinweis",
                umbruch=True,
            ),
            1,
        )
        ph.addWidget(
            knopf(
                _("Logdatei öffnen"),
                enabled=bool(getattr(self.haupt, "log_datei", None)),
                klick=lambda: aktionen.oeffnen(self.haupt.log_datei),
            )
        )
        ph.addWidget(
            knopf(_("Ausgang öffnen"), klick=lambda: aktionen.oeffnen(self.haupt.k.ausgang))
        )
        pv.addLayout(ph)
        self.reiter.addTab(self.s_pruef, "")
        self.reiter.addTab(self.s_fehler, "")
        self.reiter.addTab(p, _("Protokoll"))
        self.toasts = ToastStapel(self)

    def _scrollseite(self):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        innen = QWidget()
        innen.setObjectName("wurzel")
        lay = QVBoxLayout(innen)
        lay.setContentsMargins(0, 8, 4, 8)
        lay.setSpacing(10)
        sa.setWidget(innen)
        return sa, lay

    @staticmethod
    def _leeren(lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def toast(self, *a, **kw):
        return self.toasts.zeigen(self.haupt.c, *a, **kw)

    # ------------------------------------------------------------------------------------------
    def aktualisieren(self) -> None:
        k, c = self.haupt.k, self.haupt.c
        faelle = daten.prueffaelle(k)
        berichte = daten.fehlerberichte(k)
        self.reiter.setTabText(0, _("Zu prüfen ({n})").format(n=len(faelle)))
        self.reiter.setTabText(1, _("Fehler ({n})").format(n=len(berichte)))

        self._leeren(self.l_pruef)
        if not faelle:
            self.l_pruef.addWidget(lbl(_("Nichts zu prüfen."), "sub"))
        for f in faelle:
            self.l_pruef.addWidget(self._fall_karte(f, c))
        if faelle:
            self.l_pruef.addWidget(
                lbl(
                    _(
                        "„Neues Sichtbild + erstellen“: Die CSV-Daten gelten, das PDF wird neu gesetzt. "
                        "„Verwerfen“: Dateien gehen nach „Fehler“ (mit Rückgängig im Hinweis)."
                    ),
                    "hinweis",
                    umbruch=True,
                )
            )
        self.l_pruef.addStretch()

        self._leeren(self.l_fehler)
        if not berichte:
            self.l_fehler.addWidget(lbl(_("Keine Fehler."), "sub"))
        for b in berichte:
            kk, kv = karte()
            z = QHBoxLayout()
            z.setSpacing(10)
            z.addWidget(Punkt(c["err"]))
            z.addWidget(lbl(b.titel, "titel"))
            z.addStretch()
            z.addWidget(lbl(_zeit(b.zeit), "sub"))
            kv.addLayout(z)
            rest = "\n".join(b.text.splitlines()[1:]).strip()
            kv.addWidget(lbl(rest, "sub", umbruch=True))
            h = QHBoxLayout()
            h.addStretch()
            h.addWidget(
                knopf(_("Bericht öffnen"), klick=lambda _c=False, p=b.pfad: aktionen.oeffnen(p))
            )
            h.addWidget(knopf(_("Fehlerordner öffnen"), klick=lambda: aktionen.oeffnen(k.fehler)))
            kv.addLayout(h)
            self.l_fehler.addWidget(kk)
        if berichte:
            self.l_fehler.addWidget(
                lbl(
                    _(
                        "Dateien korrigieren und wieder in den Eingang legen. "
                        "Erledigte Berichte können gelöscht werden."
                    ),
                    "hinweis",
                    umbruch=True,
                )
            )
        self.l_fehler.addStretch()

        self.l_pruefstatus.setText(self._pruefstatus())
        self.l_pruefstatus.setEnabled(k.nachpruefen and validierung.bereit())
        zeilen = []
        for e in daten.protokoll(k, 500):
            z = e.zeit.strftime("%Y-%m-%d %H:%M:%S") if e.zeit else "?"
            betr = daten.betrag(e.brutto, sprache()) if e.brutto else ""
            zeilen.append(
                f"{z}  {e.status:8} {PRUEFZEICHEN.get(e.pruefung, ' '):1} {e.nummer:16} {e.kunde[:28]:28} "
                f"{betr:>14}  " + " | ".join(e.hinweise)
            )
        self.protokoll.setPlainText("\n".join(zeilen) if zeilen else _("Noch keine Einträge."))

    def _pruefstatus(self) -> str:
        if not self.haupt.k.nachpruefen:
            return _("Prüfung nach Erstellung: aus (Einstellungen → Prüfung)")
        if not validierung.bereit():
            return _("Prüfung nach Erstellung: Prüfwerkzeuge nicht gefunden")
        return _(
            "Prüfung nach Erstellung: an ({werkzeuge}) · ✓ gültig  ✗ ungültig  – nicht geprüft"
        ).format(werkzeuge=validierung.werkzeug_versionen())

    def _fall_karte(self, f: daten.Prueffall, c: dict):
        kk, kv = karte()
        z = QHBoxLayout()
        z.setSpacing(10)
        z.addWidget(Punkt(c["busy"]))
        z.addWidget(lbl(f"{f.nummer} · {f.kunde}" if f.kunde else f.nummer, "titel"))
        z.addStretch()
        z.addWidget(lbl(_zeit(f.zeit), "sub"))
        kv.addLayout(z)
        if f.abweichungen:
            kv.addWidget(lbl(_("Abweichung zwischen CSV und Druck-PDF:"), "sub"))
            g = QGridLayout()
            g.setHorizontalSpacing(20)
            g.setVerticalSpacing(2)
            for j, h in enumerate((_("Feld"), _("CSV (gilt)"), _("Druck-PDF"))):
                g.addWidget(lbl(h, "sub"), 0, j)
            for i, (feld, a, b) in enumerate(f.abweichungen, start=1):
                g.addWidget(lbl(_(FELDNAMEN.get(feld, feld))), i, 0)
                g.addWidget(lbl(_wert(feld, a)), i, 1)
                x = lbl(_wert(feld, b))
                x.setStyleSheet(f"color:{c['warn_t']};")
                g.addWidget(x, i, 2)
            g.setColumnStretch(3, 1)
            kv.addLayout(g)
        for t in f.sonstige:
            if not t.startswith("CSV und Druck weichen ab"):
                kv.addWidget(lbl("• " + hinweis_text(t), "warn", umbruch=True))
        dl = KurzLabel(
            _("Dateien: {liste} (im Ordner „Zu prüfen“)").format(
                liste=", ".join(q.name for q in f.quellen)
            )
        )
        kv.addWidget(dl)
        pdf = next((q for q in f.quellen if q.suffix.lower() == ".pdf"), None)
        csv = next((q for q in f.quellen if q.suffix.lower() != ".pdf"), None)
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addWidget(
            knopf(
                _("Druck-PDF ansehen"),
                enabled=bool(pdf and pdf.exists()),
                klick=lambda: aktionen.oeffnen(pdf),
            )
        )
        h.addWidget(
            knopf(
                _("CSV ansehen"),
                enabled=bool(csv and csv.exists()),
                klick=lambda: aktionen.oeffnen(csv),
            )
        )
        if f.kontrolle_offen and f.kennung:
            b_ok = knopf(
                _("Felder bestätigen"),
                primary=not (csv and csv.exists()),
                klick=lambda *_a, fall=f: self.kontrolle_bestaetigen(fall),
            )
            b_ok.setObjectName("kontrolle_bestaetigen")
            h.addWidget(b_ok)
        h.addStretch()
        b_neu = knopf(
            _("Neues Sichtbild + erstellen"),
            primary=True,
            enabled=bool(csv and csv.exists()),
            klick=lambda: self.freigeben(f),
        )
        b_neu.setObjectName("freigeben")
        h.addWidget(b_neu)
        b_weg = knopf(_("Verwerfen"), danger=True, klick=lambda: self.verwerfen(f))
        b_weg.setObjectName("verwerfen")
        h.addWidget(b_weg)
        kv.addLayout(h)
        return kk

    def kontrolle_bestaetigen(self, f: daten.Prueffall) -> None:
        from .. import pdferkennung

        prof = next(
            (p for p in self.haupt.k.profile if pdferkennung.profil_name(p) == f.profil),
            None,
        )
        if not prof or not f.kennung:
            self.toast(
                "fehler", _("Felder nicht bestätigt"), _("Die Vorlage wurde nicht gefunden.")
            )
            return
        pdferkennung.kontrolle_bestaetigen(prof, f.kennung)
        self.toast(
            "ok",
            _("Felder bestätigt"),
            _("Die offene Selbstkontrolle der Vorlage {vorlage} ist erledigt.").format(
                vorlage=f"{f.profil}-{f.kennung}"
            ),
        )
        self.aktualisieren()
        self.haupt.aktualisieren()

    # ------------------------------------------------------------------------------------------
    def freigeben(self, f: daten.Prueffall) -> None:
        k = self.haupt.k
        erg = pipeline.prueffall_freigeben(f.pfad, k)
        if erg.status != "ok":  # Erfolg: kein Toast – die Karte verschwindet, „Heute“ zählt hoch
            grund = next(
                (h.split(": ", 1)[-1] for h in erg.hinweise if h.startswith(("PRUEFEN", "FEHLER"))),
                "",
            )
            self.toast("fehler", _("{nr}: nicht erstellt").format(nr=f.nummer), grund)
        self.aktualisieren()
        self.haupt.aktualisieren()

    def verwerfen(self, f: daten.Prueffall) -> None:
        wege = pipeline.prueffall_verwerfen(f.pfad, self.haupt.k)
        self.verworfen[f.nummer] = wege
        self.toast(
            "info",
            _("{nr} verworfen").format(nr=f.nummer),
            _("Die Dateien liegen jetzt im Ordner „Fehler“."),
            _("Rückgängig"),
            lambda: self.rueckgaengig(f.nummer),
        )
        self.aktualisieren()
        self.haupt.aktualisieren()

    def rueckgaengig(self, nummer: str) -> None:
        wege = self.verworfen.pop(nummer, None)
        if wege:
            pipeline.rueckgaengig(wege)
        self.aktualisieren()
        self.haupt.aktualisieren()
