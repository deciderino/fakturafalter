# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Erzeugt das Test-Setup „Industrie“: ein erfundener Schrauben- und Normteile-Großhandel mit eigener
Lohnzerspanung, acht Rechnungen (Druck-PDF + schlanker CSV-Export) und eine Absender-CSV zum Importieren.

Besonderheiten: 19 % Inland, Stückpreise teils „pro 100 Stk“ (Preiseinheit 100) gemischt mit Preisen pro
Stück, Zerspanung nach Stunden. Alle Namen, Anschriften, Kennungen und Bankdaten sind erfunden;
USt-IdNr. und IBAN haben gültige Prüfziffern. Aufruf:  python erzeuge_beispiele.py  (deterministisch)."""
from __future__ import annotations

import csv
import io
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "pdf-erkennung"))
from erzeuge_beispiele import Blatt, de, iban, iban_gruppiert, menge_de, ust_id  # noqa: E402

EINGANG = HIER / "eingang"
C2 = Decimal("0.01")

NAME = "Normteile Brückner GmbH"
STRASSE, PLZ, ORT = "Gewerbering 14", "42897", "Remscheid"
UST = ust_id("29031966")
IBAN = iban("0071100842")
STNR = "126/5743/0815"
REGISTER = "Amtsgericht Wuppertal HRB 990042"
TELEFON = "02191 990420"
EMAIL = "rechnung@normteile-brueckner.invalid"

ARTIKEL = [  # Artikelnr, Bezeichnung, Einheit, Preis, Preiseinheit
    ("100-0830", "Sechskantschraube DIN 933 M8x30 8.8 verzinkt", "Stk", "4.80", 100),
    ("100-1040", "Sechskantschraube DIN 933 M10x40 8.8 verzinkt", "Stk", "9.25", 100),
    ("110-0008", "Sechskantmutter DIN 934 M8 Kl. 8 verzinkt", "Stk", "1.90", 100),
    ("120-0620", "Zylinderschraube ISO 4762 M6x20 12.9", "Stk", "9.60", 100),
    ("130-0010", "Scheibe DIN 125 A 10,5 verzinkt", "Stk", "1.35", 100),
    ("140-1210", "Gewindestange DIN 976 M12x1000 4.6", "Stk", "2.35", 1),
    ("150-0805", "Passfeder DIN 6885 A 8x7x50", "Stk", "0.85", 1),
    ("900-0001", "Drehteil Welle Ø 25 nach Zeichnung 4711-B", "Stk", "14.50", 1),
    ("900-0002", "Frästeil Halter AlMgSi nach Zeichnung 0815-C", "Stk", "27.40", 1),
]
LOHN = [("990-0100", "Zerspanung Lohnarbeit CNC-Drehen", "Std", "68.00"),
        ("990-0200", "Rüstzeit CNC-Fräsen", "Std", "72.00")]
KUNDEN = [
    {"name": "Maschinenbau Halder KG", "strasse": "Talsperrenweg 3", "plz": "58511", "ort": "Lüdenscheid"},
    {"name": "Fördertechnik Ostwind GmbH", "strasse": "Hafenstraße 88", "plz": "47119", "ort": "Duisburg"},
    {"name": "Pumpenwerk Kaltenbach AG", "strasse": "Brunnenallee 1", "plz": "57072", "ort": "Siegen"},
    {"name": "Anlagenbau Riedel GmbH & Co. KG", "strasse": "Am Walzwerk 21", "plz": "44147", "ort": "Dortmund"},
]
SPALTEN = ["Rechnungsnr", "Datum", "Lieferdatum", "Kunde", "Strasse", "PLZ", "Ort",
           "Artikel", "Menge", "Einheit", "Einzelpreis", "Preiseinheit", "USt-Satz"]


@dataclass
class Pos:
    artnr: str
    text: str
    menge: Decimal
    einheit: str
    preis: Decimal
    pe: int = 1

    @property
    def betrag(self) -> Decimal:
        return (self.menge * self.preis / self.pe).quantize(C2, ROUND_HALF_UP)


@dataclass
class Rechnung:
    nr: str
    datum: date
    lieferung: date
    kunde: dict
    bestellung: str
    pos: list[Pos]

    @property
    def netto(self) -> Decimal:
        return sum((p.betrag for p in self.pos), Decimal(0))

    @property
    def ust(self) -> Decimal:
        return (self.netto * 19 / 100).quantize(C2, ROUND_HALF_UP)


def rechnungen() -> list[Rechnung]:
    zz = random.Random("industrie")
    out = []
    for i in range(8):
        d = date(2026, 10, 5) + timedelta(days=3 * i)
        art = zz.sample(ARTIKEL[:5], zz.randint(2, 3)) + zz.sample(ARTIKEL[5:], zz.randint(1, 2))
        pos = []
        for a, t, e, p, pe in art:
            m = zz.choice([500, 1000, 2000, 2500, 5000]) if pe == 100 else zz.choice([4, 10, 12, 25, 40])
            pos.append(Pos(a, t, Decimal(m), e, Decimal(p), pe))
        if i % 2 == 0:                                          # jede zweite mit Zerspanung nach Stunden
            a, t, e, p = LOHN[i // 2 % 2]
            pos.append(Pos(a, t, Decimal(zz.choice(["1.5", "2", "3.25", "6"])), e, Decimal(p)))
        out.append(Rechnung(f"NB-26-{1001 + i}", d, d - timedelta(days=1), KUNDEN[i % 4],
                            f"B-{4500 + 17 * i}", pos))
    return out


def zeichnen(r: Rechnung, pfad: Path) -> None:
    """Layout: Logo-Schriftzug, Absenderzeile über dem Fenster, Infoblock rechts mit Doppelpunkt-Etiketten,
    Tabelle Pos | Art.-Nr. | Bezeichnung | Menge | ME | Preis € | PE | Betrag €, Summenblock rechts."""
    b = Blatt(pfad)
    b.t(50, 36, "BRÜCKNER", 22, fett=True)
    b.t(50, 62, "Normteile · Verbindungselemente · Lohnzerspanung", 8)
    b.t(545, 40, NAME, 9, fett=True, rechts=True)
    for j, z in enumerate([STRASSE, f"{PLZ} {ORT}", f"Tel. {TELEFON}", EMAIL]):
        b.t(545, 52 + j * 11, z, 8, rechts=True)
    b.linie(50, 112, 545, 0.8)
    b.t(50, 128, f"{NAME} · {STRASSE} · {PLZ} {ORT}", 6)
    k = r.kunde
    for j, z in enumerate([k["name"], k["strasse"], f"{k['plz']} {k['ort']}"]):
        b.t(50, 142 + j * 13, z, 10)
    info = [("Rechnung Nr.:", r.nr), ("Rechnungsdatum:", f"{r.datum:%d.%m.%Y}"),
            ("Lieferdatum:", f"{r.lieferung:%d.%m.%Y}"), ("Ihre Bestellung:", r.bestellung)]
    for j, (lab, w) in enumerate(info):
        b.t(350, 132 + j * 14, lab, 9)
        b.t(545, 132 + j * 14, w, 9, rechts=True)
    b.t(50, 222, "RECHNUNG", 15, fett=True)
    b.t(50, 244, "Wir liefern Ihnen zu unseren Verkaufs- und Lieferbedingungen:", 8)
    top = 266
    b.flaeche(48, top - 4, 499, 17, 0.88)
    kopf = [(52, "Pos", False), (78, "Art.-Nr.", False), (130, "Bezeichnung", False), (378, "Menge", True),
            (386, "ME", False), (465, "Preis €", True), (492, "PE", True), (545, "Betrag €", True)]
    for x, t, rechts in kopf:
        b.t(x, top, t, 8, fett=True, rechts=rechts)
    top += 22
    for n, p in enumerate(r.pos, 1):
        werte = [(52, str(n * 10), False), (78, p.artnr, False), (130, p.text, False),
                 (378, menge_de(p.menge), True), (386, p.einheit, False), (465, de(p.preis), True),
                 (492, str(p.pe), True), (545, de(p.betrag), True)]
        for x, t, rechts in werte:
            b.t(x, top, t, 8.5, rechts=rechts)
        top += 16
    b.linie(48, top, 547, 0.5)
    top += 10
    brutto = r.netto + r.ust
    for lab, w, fett in [("Warenwert netto", de(r.netto), False), ("zzgl. 19 % USt", de(r.ust), False),
                         ("Rechnungsbetrag EUR", de(brutto), True)]:
        b.t(380, top, lab, 9, fett=fett)
        b.t(545, top, w, 9, fett=fett, rechts=True)
        top += 14
    b.t(50, top + 20, "PE = Preiseinheit: Preis gilt je 1 bzw. je 100 Stück.", 7.5)
    b.t(50, top + 34, "Zahlbar innerhalb 30 Tagen ohne Abzug.", 9)
    b.linie(50, 772, 545, 0.4)
    b.t(50, 778, f"{NAME} · {STRASSE} · {PLZ} {ORT} · {REGISTER} · Geschäftsführer: Erik Brückner", 6.5)
    b.t(50, 788, f"USt-IdNr. {UST} · St.-Nr. {STNR} · IBAN {iban_gruppiert(IBAN)} · Musterbank Remscheid", 6.5)
    b.fertig()


def csv_schreiben(r: Rechnung, pfad: Path) -> None:
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow(SPALTEN)
    k = r.kunde
    for p in r.pos:
        w.writerow([r.nr, f"{r.datum:%d.%m.%Y}", f"{r.lieferung:%d.%m.%Y}", k["name"], k["strasse"], k["plz"],
                    k["ort"], p.text, menge_de(p.menge), p.einheit, de(p.preis).replace(".", ""), str(p.pe), "19"])
    pfad.write_bytes(puffer.getvalue().encode("utf-8"))


def absender_csv(pfad: Path) -> None:
    pfad.write_text("Name;Strasse;PLZ;Ort;USt-IdNr;Steuernummer;IBAN;BIC;Telefon;E-Mail;Register\n"
                    f"{NAME};{STRASSE};{PLZ};{ORT};{UST};{STNR};{IBAN};;{TELEFON};{EMAIL};{REGISTER}\n",
                    encoding="utf-8")


def main() -> None:
    EINGANG.mkdir(exist_ok=True)
    for r in rechnungen():
        zeichnen(r, EINGANG / f"{r.nr}.pdf")
        csv_schreiben(r, EINGANG / f"normteile_{r.nr}.csv")
    absender_csv(HIER / "absender-normteile.csv")
    print(f"{len(rechnungen())} Rechnungen in {EINGANG}  (USt-IdNr. {UST}, IBAN {IBAN})")


if __name__ == "__main__":
    main()
