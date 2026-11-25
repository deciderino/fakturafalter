# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Absender-Formular (Einstellungen und Ersteinrichtung): Bezeichnung über dem Feld, Import aus CSV
oder aus einer Rechnungs-PDF. Schreibt in die Blöcke ``absender``/``zahlung`` der Konfiguration."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from .. import adapter_pdf, pdferkennung
from ..absender import Absender, aus_csv, erkennen_aus_zeilen
from .bausteine import knopf, lbl
from .texte import _

log = logging.getLogger("fakturafalter")

# Schlüssel -> (Bezeichnung, Pflicht)
FELDER = (
    ("name", "Firmenname", True),
    ("strasse", "Straße und Hausnummer", True),
    ("zusatz", "Adresszusatz (freiwillig)", False),
    ("plz", "PLZ", True),
    ("ort", "Ort", True),
    ("ust_id", "USt-IdNr.", False),
    ("steuernummer", "Steuernummer", False),
    ("iban", "IBAN", True),
    ("bic", "BIC (freiwillig)", False),
    ("glaeubiger_id", "Gläubiger-ID (freiwillig, nur für Lastschrift)", False),
    ("register", "Handelsregister (freiwillig)", False),
    ("elektronische_adresse", "E-Mail für Rechnungen (freiwillig)", False),
    ("kontakt_name", "Ansprechpartner (freiwillig)", False),
    ("kontakt_telefon", "Telefon (freiwillig)", False),
    ("kontakt_email", "E-Mail Kontakt (freiwillig)", False),
)
# Absender-Feld -> Formular-Schlüssel
AUS_ABSENDER = {
    "name": "name",
    "strasse": "strasse",
    "zusatz": "zusatz",
    "plz": "plz",
    "ort": "ort",
    "ust_id": "ust_id",
    "steuernummer": "steuernummer",
    "iban": "iban",
    "bic": "bic",
    "register": "register",
    "kleinunternehmer": "kleinunternehmer",
    "telefon": "kontakt_telefon",
    "email": "kontakt_email",
}


def aus_roh(roh: dict) -> dict[str, str]:
    a = roh.get("absender") or {}
    adr = a.get("anschrift") or {}
    kon = a.get("kontakt") or {}
    z = roh.get("zahlung") or {}
    return {
        "name": a.get("name", ""),
        "strasse": adr.get("strasse", ""),
        "zusatz": adr.get("zusatz", ""),
        "plz": str(adr.get("plz", "") or ""),
        "ort": adr.get("ort", ""),
        "ust_id": a.get("ust_id", ""),
        "steuernummer": a.get("steuernummer", ""),
        "iban": z.get("iban", ""),
        "bic": z.get("bic", ""),
        "glaeubiger_id": z.get("glaeubiger_id", ""),
        "register": a.get("register", ""),
        "elektronische_adresse": a.get("elektronische_adresse", ""),
        "kontakt_name": kon.get("name", ""),
        "kontakt_telefon": kon.get("telefon", ""),
        "kontakt_email": kon.get("email", ""),
        "kleinunternehmer": "1" if a.get("kleinunternehmer") else "",
    }


def in_roh(r: dict, e: dict[str, str]) -> None:
    a = r.setdefault("absender", {}) or {}
    r["absender"] = a
    a["name"] = e["name"]
    a["anschrift"] = {
        **(a.get("anschrift") or {}),
        "strasse": e["strasse"],
        "plz": e["plz"],
        "ort": e["ort"],
    }
    a["anschrift"].setdefault("land", "DE")
    if e.get("zusatz"):
        a["anschrift"]["zusatz"] = e["zusatz"]
    else:
        a["anschrift"].pop("zusatz", None)
    a["ust_id"] = e["ust_id"].replace(" ", "")
    a["steuernummer"] = e["steuernummer"]
    a["elektronische_adresse"] = e["elektronische_adresse"]
    a["kontakt"] = {
        "name": e["kontakt_name"],
        "telefon": e["kontakt_telefon"],
        "email": e["kontakt_email"],
    }
    a["register"] = e["register"]
    if e.get("kleinunternehmer"):
        a["kleinunternehmer"] = True  # ab 0.9.7: § 19 UStG
    else:
        a.pop("kleinunternehmer", None)
    z = r.setdefault("zahlung", {}) or {}
    r["zahlung"] = z
    z["iban"] = e["iban"].replace(" ", "").upper()
    z["bic"] = e["bic"].upper()
    if e.get("glaeubiger_id", "").strip():
        z["glaeubiger_id"] = e["glaeubiger_id"].replace(" ", "").upper()
    else:
        z.pop("glaeubiger_id", None)
    if not z.get("kontoinhaber") and e["name"]:
        z["kontoinhaber"] = e["name"]


def pflicht_fehlt(e: dict[str, str]) -> list[str]:
    """Deutsche Feldnamen (für die Anzeige übersetzen)."""
    f = [name for schl, name, p in FELDER if p and not e.get(schl, "").strip()]
    if e.get("kleinunternehmer"):  # BR-CO-26: auch die Registernummer (BT-30) reicht
        if not any(e.get(k, "").strip() for k in ("ust_id", "steuernummer", "register")):
            f.append("USt-IdNr., Steuernummer oder Handelsregister")
    elif not (e.get("ust_id", "").strip() or e.get("steuernummer", "").strip()):
        f.append("USt-IdNr. oder Steuernummer")
    return f


def aus_pdf(datei: Path) -> Absender:
    zeilen = pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(Path(datei)))
    return erkennen_aus_zeilen(zeilen)


class AbsenderFormular(QWidget):
    def __init__(self, roh: dict, toast, kurz: bool = False):
        """``toast(art, titel, detail)`` meldet Import-Ergebnisse; ``kurz``: nur Pflichtfelder + BIC/Register."""
        super().__init__()
        self.toast = toast
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        h = QHBoxLayout()
        h.setSpacing(8)
        self.b_csv = knopf(_("Aus Datei importieren…"), klick=self._csv_waehlen)
        self.b_pdf = knopf(_("Aus einer Rechnung (PDF) übernehmen…"), klick=self._pdf_waehlen)
        h.addWidget(self.b_csv)
        h.addWidget(self.b_pdf)
        h.addStretch(1)
        v.addLayout(h)
        werte = aus_roh(roh)
        self.felder: dict[str, QLineEdit] = {}
        for schl, name, _p in FELDER:
            e = QLineEdit(str(werte.get(schl) or ""))
            e.setObjectName(f"abs_{schl}")
            e.setAccessibleName(_(name))
            if kurz and schl in (
                "glaeubiger_id",
                "elektronische_adresse",
                "kontakt_name",
                "kontakt_telefon",
                "kontakt_email",
            ):
                self.felder[schl] = (
                    e  # Wert bleibt erhalten, Feld nur in den Einstellungen sichtbar
                )
                continue
            v.addWidget(lbl(_(name), umbruch=True))
            v.addWidget(e)
            if schl == "steuernummer":
                v.addWidget(
                    lbl(
                        _("USt-IdNr. oder Steuernummer – eins von beiden reicht."),
                        "hinweis",
                        umbruch=True,
                    )
                )
            self.felder[schl] = e
        # ab 0.9.7: Kleinunternehmer – alle Rechnungen ohne Umsatzsteuer, Hinweis nach § 19 UStG
        self.ku = QCheckBox(_("Kleinunternehmer (§ 19 UStG) – Rechnungen ohne Umsatzsteuer"))
        self.ku.setObjectName("abs_kleinunternehmer")
        self.ku.setChecked(bool(werte.get("kleinunternehmer")))
        v.addWidget(self.ku)
        v.addWidget(
            lbl(
                _(
                    "Dann steht auf jeder Rechnung „Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.“ "
                    "Liefert eine Quelle trotzdem einen Steuersatz, wird die Rechnung angehalten."
                ),
                "hinweis",
                umbruch=True,
            )
        )

    def werte(self) -> dict[str, str]:
        w = {s: " ".join(e.text().split()) for s, e in self.felder.items()}
        w["kleinunternehmer"] = "1" if self.ku.isChecked() else ""
        return w

    def uebernehmen(self, a: Absender) -> int:
        n = 0
        for feld, schl in AUS_ABSENDER.items():
            w = getattr(a, feld)
            if feld == "kleinunternehmer":
                if w:
                    self.ku.setChecked(True)
                    n += 1
            elif w:
                self.felder[schl].setText(w)
                n += 1
        return n

    def _csv_waehlen(self) -> None:
        datei, _f = QFileDialog.getOpenFileName(
            self, _("Absender importieren"), str(Path.home()), _("CSV-Dateien (*.csv *.txt)")
        )
        if datei:
            self.csv_importieren(Path(datei))

    def csv_importieren(self, datei: Path) -> bool:
        try:
            a = aus_csv(Path(datei).read_bytes())
        except (OSError, ValueError) as e:
            log.warning("Absender-Import %s: %s", datei, e)
            self.toast(
                "fehler",
                _("Datei nicht lesbar"),
                _("Erwartet: CSV mit Kopfzeile Name;Strasse;PLZ;Ort;…"),
            )
            return False
        self.uebernehmen(a)
        self.toast("ok", _("Absender übernommen"), a.name)
        return True

    def _pdf_waehlen(self) -> None:
        datei, _f = QFileDialog.getOpenFileName(
            self, _("Rechnung auswählen"), str(Path.home()), _("PDF-Dateien (*.pdf)")
        )
        if datei:
            self.pdf_uebernehmen(Path(datei))

    def pdf_uebernehmen(self, datei: Path) -> bool:
        try:
            a = aus_pdf(datei)
        except Exception as e:  # noqa: BLE001 – kaputte/verschlüsselte PDF: kurz melden, Details ins Log
            log.warning("Absender aus PDF %s: %s", datei, e)
            self.toast("fehler", _("PDF nicht lesbar"), Path(datei).name)
            return False
        if not a.gefunden():
            self.toast("fehler", _("Kein Absender gefunden"), _("Bitte die Angaben eintippen."))
            return False
        self.uebernehmen(a)
        offen = a.fehlt()
        self.toast(
            "ok" if not offen else "info",
            _("Absender übernommen"),
            _("Bitte prüfen und Fehlendes ergänzen.") if offen else _("Bitte kurz prüfen."),
        )
        return True
