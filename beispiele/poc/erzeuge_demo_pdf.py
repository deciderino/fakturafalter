# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Erzeugt das Demo-Druck-PDF TM-2026-0042.pdf aus TM-2026-0042.csv (ALLE Daten erfunden).

Aufruf (im Repo-Ordner):  .venv/bin/python beispiele/poc/erzeuge_demo_pdf.py
Die Werte werden aus der CSV gelesen, damit PDF und CSV immer exakt zusammenpassen.
Schrift: Helvetica (Standardschrift, Textebene); Fakturafalter bettet beim Erzeugen Liberation Sans ein.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HIER = Path(__file__).resolve().parent
CSV = HIER / "TM-2026-0042.csv"
PDF = HIER / "TM-2026-0042.pdf"
H = A4[1]
STEUER_KZ = {"1": ("A", Decimal("19")), "2": ("B", Decimal("7"))}


def d(s: str) -> Decimal:
    return Decimal(s.replace(".", "").replace(",", "."))


def de(x: Decimal) -> str:
    s = f"{x.quantize(Decimal('0.01'), ROUND_HALF_UP):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def menge(x: Decimal) -> str:
    return f"{x.normalize():f}".replace(".", ",")


def main() -> None:
    zeilen = list(csv.DictReader(CSV.read_text(encoding="utf-8").splitlines(), delimiter=";"))
    k = zeilen[0]
    c = canvas.Canvas(str(PDF), pagesize=A4)
    c.setTitle(f"Rechnung {k['rechnungsnummer']}")
    c.setAuthor("Tischlerei Muster GmbH")

    def t(x, top, text, font="Helvetica", size=9, rechts=False):
        c.setFont(font, size)
        (c.drawRightString if rechts else c.drawString)(x, H - top, text)

    # Kopf
    t(45, 60, "Tischlerei Muster GmbH", "Helvetica-Bold", 18)
    t(45, 76, "Möbel · Innenausbau · Reparaturen", size=10)
    t(45, 135, "Tischlerei Muster GmbH · Hobelweg 7 · 12345 Musterstadt", size=7)
    for i, z in enumerate([k["kunde_name"], k["kunde_strasse"], f"{k['kunde_plz']} {k['kunde_ort']}"]):
        t(45, 155 + i * 14, z, size=10)
    for i, (lab, wert) in enumerate([("Rechnungsnr.:", k["rechnungsnummer"]), ("Datum:", k["rechnungsdatum"]),
                                     ("Kunden-Nr.:", k["kundennummer"]), ("Leistungsdatum:", k["leistungsdatum"]),
                                     ("Ihre Bestellung:", k["bestellnummer"]), ("Seite:", "1 von 1")]):
        t(350, 140 + i * 14, lab)
        t(440, 140 + i * 14, wert)
    t(45, 260, "Rechnung", "Helvetica-Bold", 14)

    # Tabelle
    top = 295
    for x, txt, r in [(48, "Pos", 0), (75, "Art.-Nr.", 0), (150, "Bezeichnung", 0), (390, "Menge", 1),
                      (396, "ME", 0), (475, "Einzelpreis", 1), (535, "Gesamt", 1), (545, "USt", 0)]:
        t(x, top, txt, "Helvetica-Bold", 9, bool(r))
    c.line(45, H - top - 5, 565, H - top - 5)
    netto: dict[str, Decimal] = {}
    for z in zeilen:
        top += 16
        m, ep = d(z["menge"]), d(z["einzelpreis_netto"])
        ges = (m * ep).quantize(Decimal("0.01"), ROUND_HALF_UP)
        kz, _ = STEUER_KZ[z["steuerschluessel"]]
        netto[kz] = netto.get(kz, Decimal("0")) + ges
        t(48, top, z["pos"])
        t(75, top, z["artikelnummer"])
        t(150, top, z["bezeichnung"])
        t(390, top, menge(m), rechts=True)
        t(396, top, z["einheit"])
        t(475, top, de(ep), rechts=True)
        t(535, top, de(ges), rechts=True)
        t(545, top, kz)
    top += 8
    c.line(45, H - top, 565, H - top)

    # Summen
    summe = sum(netto.values(), Decimal("0"))
    top += 16
    t(350, top, "Nettobetrag")
    t(535, top, de(summe), rechts=True)
    ust_ges = Decimal("0")
    for kz, satz in sorted({v for v in STEUER_KZ.values() if v[0] in netto}):
        ust = (netto[kz] * satz / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        ust_ges += ust
        top += 14
        t(350, top, f"zzgl. {satz} % USt ({kz})")
        t(535, top, de(ust), rechts=True)
    top += 18
    t(350, top, "Gesamtbetrag EUR", "Helvetica-Bold")
    t(535, top, de(summe + ust_ges), "Helvetica-Bold", rechts=True)

    faellig = datetime.strptime(k["rechnungsdatum"], "%d.%m.%Y") + timedelta(days=14)
    top += 40
    t(45, top, f"Leistung erbracht am {k['leistungsdatum']}. Steuerkennzeichen: A = 19 % USt, B = 7 % USt.")
    t(45, top + 14, f"Zahlbar innerhalb 14 Tagen ohne Abzug (bis {faellig:%d.%m.%Y}).")
    t(45, top + 28, f"Bitte geben Sie bei der Zahlung die Rechnungsnummer {k['rechnungsnummer']} an.")

    # Fußzeile (unterhalb bereich_bis_top der Vorlage)
    c.line(45, H - 770, 565, H - 770)
    t(45, 782, "Tischlerei Muster GmbH · Hobelweg 7 · 12345 Musterstadt · Geschäftsführung: Max Beispiel", size=7)
    t(45, 792, "Amtsgericht Musterstadt HRB 00000 · USt-IdNr. DE123456788 · buchhaltung@tischlerei-muster.example", size=7)
    t(45, 802, "Bankverbindung: IBAN DE36 0000 0000 0000 0000 00 (Beispiel-IBAN)", size=7)
    c.showPage()
    c.save()
    print(f"{PDF.name}: netto {de(summe)} / USt {de(ust_ges)} / brutto {de(summe + ust_ges)}")


if __name__ == "__main__":
    main()
