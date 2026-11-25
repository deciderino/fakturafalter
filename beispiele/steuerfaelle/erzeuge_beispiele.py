# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Erzeugt das Test-Setup „Steuerfälle“ (ab 0.9.7): Druck-PDFs dreier erfundener Absender mit
Reverse Charge (AE), innergemeinschaftlicher Lieferung (K), Ausfuhr (G), nicht steuerbarer Leistung (O),
Fremdwährung (USD mit Kurs und USt in EUR) und Kleinunternehmer (§ 19 UStG).

- Lichtbogen Messtechnik GmbH: Positionstabelle MIT Steuerspalte -> Steuerfall je Position (gemischt möglich)
- Estrichbau Wendel GmbH: Steuersatz NUR in den Summen -> ein Steuerfall je Rechnung (aus dem Steuerhinweis)
- Gartenpflege Lindner: Kleinunternehmer, keine Umsatzsteuer

Alle Namen, Anschriften, Kennungen und Bankdaten sind erfunden; USt-IdNr. und IBAN haben gültige Prüfziffern.

Aufruf:  python erzeuge_beispiele.py            PDFs + Absender-CSVs (deterministisch)
         python erzeuge_beispiele.py --anlernen  zusätzlich Profile + angelernte Vorlagen (braucht fakturafalter)
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "pdf-erkennung"))
from erzeuge_beispiele import Blatt, de, iban, iban_gruppiert, menge_de, ust_id  # noqa: E402

EINGANG = HIER / "eingang"
C2 = Decimal("0.01")

RC = "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)"
IGL = "Steuerfreie innergemeinschaftliche Lieferung (§ 4 Nr. 1b UStG)"
AUSFUHR = "Steuerfreie Ausfuhrlieferung (§ 4 Nr. 1a UStG)"
NSTB = "Nicht im Inland steuerbare Leistung (§ 3a Abs. 2 UStG)"
KU = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."


@dataclass
class Firma:
    kurz: str
    name: str
    strasse: str
    plz: str
    ort: str
    ust: str
    stnr: str
    iban: str
    telefon: str
    email: str
    register: str = ""
    kleinunternehmer: bool = False


LICHTBOGEN = Firma("lichtbogen", "Lichtbogen Messtechnik GmbH", "Elbuferweg 7", "01099", "Dresden",
                   ust_id("27182818"), "202/118/04711", iban("0027182818"), "0351 4471100",
                   "rechnung@lichtbogen-messtechnik.invalid", "Amtsgericht Dresden HRB 990071")
WENDEL = Firma("wendel", "Estrichbau Wendel GmbH", "Mörtelgasse 3", "34117", "Kassel",
               ust_id("16180339"), "026/233/50918", iban("0016180339"), "0561 7703300",
               "buero@estrichbau-wendel.invalid", "Amtsgericht Kassel HRB 990215")
LINDNER = Firma("lindner", "Gartenpflege Lindner", "Am Rosenhang 12", "79102", "Freiburg",
                ust_id("57721566"), "06454/90311", iban("0090311064"), "0761 5512290", "post@gartenpflege-lindner.invalid",
                kleinunternehmer=True)


@dataclass
class Pos:
    text: str
    menge: Decimal
    einheit: str
    preis: Decimal
    satz: int  # 19, 7 oder 0

    @property
    def betrag(self) -> Decimal:
        return (self.menge * self.preis).quantize(C2, ROUND_HALF_UP)


@dataclass
class Rechnung:
    firma: Firma
    nr: str
    datum: date
    leistung: date
    kunde: list[str]  # Anschriftzeilen
    pos: list[Pos]
    hinweis: str = ""
    kaeufer_ust: str = ""
    waehrung: str = "EUR"
    kurs: Decimal | None = None
    kursdatum: date | None = None
    fall: str = "S"  # nur zur Dokumentation (README)
    extra: list[str] = field(default_factory=list)

    @property
    def netto(self) -> Decimal:
        return sum((p.betrag for p in self.pos), Decimal(0))

    def ust_je_satz(self) -> dict[int, tuple[Decimal, Decimal]]:
        out: dict[int, Decimal] = {}
        for p in self.pos:
            out[p.satz] = out.get(p.satz, Decimal(0)) + p.betrag
        return {s: (b, (b * s / 100).quantize(C2, ROUND_HALF_UP)) for s, b in sorted(out.items(), reverse=True)}

    @property
    def ust(self) -> Decimal:
        return sum((u for _b, u in self.ust_je_satz().values()), Decimal(0))


def d(t: str) -> Decimal:
    return Decimal(t)


KUNDE_DE = ["Datenwerk Saale GmbH", "Hallorenring 5", "06108 Halle (Saale)"]
KUNDE_BAU = ["Hochbau Kranich GmbH", "Baustellenweg 9", "04109 Leipzig"]
KUNDE_AT = ["Messgeräte Alpenblick GmbH", "Kärntner Straße 40", "9020 Klagenfurt", "Österreich"]
KUNDE_CH = ["Präzision Rheintal AG", "Seestrasse 18", "8800 Thalwil", "Schweiz"]
KUNDE_US = ["Bluewater Instruments Inc.", "200 Harbor Drive", "Boston, MA 02110", "USA"]


def rechnungen() -> list[Rechnung]:
    lb, w, li = LICHTBOGEN, WENDEL, LINDNER
    rs = [
        Rechnung(lb, "LM-26-2001", date(2026, 11, 2), date(2026, 10, 30), KUNDE_DE,
                 [Pos("Datenlogger DL-8 mit Netzteil", d("4"), "Stk", d("389.00"), 19),
                  Pos("Kalibrierschein DAkkS", d("4"), "Stk", d("65.00"), 19)]),
        Rechnung(lb, "LM-26-2002", date(2026, 11, 4), date(2026, 11, 3), KUNDE_BAU,
                 [Pos("Montage Messanlage Tiefgarage (Bauleistung)", d("16"), "Std", d("78.00"), 0),
                  Pos("Kabeltrassen und Sensorhalter montiert", d("1"), "pauschal", d("640.00"), 0)],
                 RC, ust_id("31415926"), fall="AE"),
        Rechnung(lb, "LM-26-2003", date(2026, 11, 6), date(2026, 11, 5), KUNDE_AT,
                 [Pos("Datenlogger DL-8 mit Netzteil", d("10"), "Stk", d("389.00"), 0),
                  Pos("Temperaturfühler PT100, 2 m", d("40"), "Stk", d("24.50"), 0)],
                 IGL, "ATU99999999", fall="K"),
        Rechnung(lb, "LM-26-2004", date(2026, 11, 9), date(2026, 11, 6), KUNDE_CH,
                 [Pos("Messverstärker MV-4", d("6"), "Stk", d("512.00"), 0),
                  Pos("Transportkiste Export", d("2"), "Stk", d("38.00"), 0)],
                 AUSFUHR, fall="G"),
        Rechnung(lb, "LM-26-2005", date(2026, 11, 11), date(2026, 11, 10), KUNDE_US,
                 [Pos("Fernwartung Messsystem (Beratungsleistung)", d("12"), "Std", d("95.00"), 0),
                  Pos("Bereitschaft Fernwartung November", d("1"), "pauschal", d("150.00"), 0)],
                 NSTB, fall="O"),
        Rechnung(lb, "LM-26-2006", date(2026, 11, 13), date(2026, 11, 12), KUNDE_DE,
                 [Pos("Datenlogger DL-8, US-Ausführung", d("4"), "Stk", d("500.00"), 19),
                  Pos("Kalibrierschein DAkkS", d("4"), "Stk", d("70.00"), 19)],
                 waehrung="USD", kurs=d("1.0850"), kursdatum=date(2026, 10, 31), fall="S (USD)"),
        Rechnung(lb, "LM-26-2007", date(2026, 11, 16), date(2026, 11, 13), KUNDE_BAU,
                 [Pos("Montage Sensorik Fassade (Bauleistung)", d("12"), "Std", d("78.00"), 0),
                  Pos("Leihgerät Datenlogger (keine Bauleistung)", d("10"), "Tage", d("9.00"), 19)],
                 RC + " für Position 1", ust_id("31415926"), fall="AE + S"),
        Rechnung(w, "WE-26-0301", date(2026, 11, 3), date(2026, 10, 31), ["Erika Musterfrau", "Lindenweg 2",
                                                                          "34119 Kassel"],
                 [Pos("Zementestrich CT-C25-F4, 50 mm", d("62"), "m²", d("21.50"), 19),
                  Pos("Baustelleneinrichtung", d("1"), "pauschal", d("150.00"), 19)]),
        Rechnung(w, "WE-26-0302", date(2026, 11, 10), date(2026, 11, 7), KUNDE_BAU,
                 [Pos("Fließestrich CA-C30-F5, 45 mm, Bauabschnitt 2", d("310"), "m²", d("18.90"), 0),
                  Pos("Baustelleneinrichtung", d("1"), "pauschal", d("350.00"), 0)],
                 RC, ust_id("31415926"), fall="AE"),
        Rechnung(li, "GL-26-0014", date(2026, 11, 24), date(2026, 11, 20),
                 ["Familie Sommer", "Wiesenweg 4", "79104 Freiburg"],
                 [Pos("Gartenpflege November", d("6"), "Std", d("32.00"), 0),
                  Pos("Grünschnitt-Entsorgung", d("1"), "pauschal", d("25.00"), 0)], KU, fall="KU"),
        Rechnung(li, "GL-26-0015", date(2026, 11, 24), date(2026, 11, 21),
                 ["Hausverwaltung Bächle", "Kaiser-Joseph-Straße 99", "79098 Freiburg"],
                 [Pos("Heckenschnitt Wohnanlage", d("9"), "Std", d("32.00"), 0),
                  Pos("Grünschnitt-Entsorgung", d("2"), "pauschal", d("25.00"), 0)], KU, fall="KU"),
    ]
    return rs


def _kopf(b: Blatt, r: Rechnung) -> None:
    f = r.firma
    b.t(50, 36, f.name, 16, fett=True)
    b.t(545, 40, f"{f.strasse} · {f.plz} {f.ort}", 8, rechts=True)
    b.t(545, 51, f"Tel. {f.telefon} · {f.email}", 8, rechts=True)
    b.linie(50, 100, 545, 0.8)
    b.t(50, 116, f"{f.name} · {f.strasse} · {f.plz} {f.ort}", 6)
    for j, z in enumerate(r.kunde):
        b.t(50, 130 + j * 13, z, 10)
    info = [("Rechnung Nr.:", r.nr), ("Rechnungsdatum:", f"{r.datum:%d.%m.%Y}"),
            ("Leistungsdatum:", f"{r.leistung:%d.%m.%Y}")]
    if r.kaeufer_ust:
        info.append(("Ihre USt-IdNr.:", r.kaeufer_ust))
    for j, (lab, w) in enumerate(info):
        b.t(350, 122 + j * 14, lab, 9)
        b.t(545, 122 + j * 14, w, 9, rechts=True)
    b.t(50, 214, "RECHNUNG", 15, fett=True)


def _fuss(b: Blatt, f: Firma) -> None:
    b.linie(50, 772, 545, 0.4)
    reg = f" · {f.register}" if f.register else ""
    b.t(50, 778, f"{f.name} · {f.strasse} · {f.plz} {f.ort}{reg}", 6.5)
    ids = f"USt-IdNr. {f.ust} · " if f.ust else ""
    b.t(50, 788, f"{ids}St.-Nr. {f.stnr} · IBAN {iban_gruppiert(f.iban)} · Musterbank {f.ort}", 6.5)


def zeichnen(r: Rechnung, pfad: Path) -> None:
    """Layout: Tabelle Pos | Bezeichnung | Menge | ME | Einzelpreis | [USt] | Betrag, Summenblock rechts,
    Steuerhinweis und Kurszeile unter den Summen. Die Steuerspalte gibt es nur bei Lichtbogen."""
    b = Blatt(pfad)
    _kopf(b, r)
    mit_spalte = r.firma is LICHTBOGEN
    top = 240
    b.flaeche(48, top - 4, 499, 17, 0.88)
    kopf = [(52, "Pos", False), (78, "Bezeichnung", False), (360, "Menge", True), (368, "ME", False),
            (450, "Einzelpreis", True), (545, "Betrag", True)]
    if mit_spalte:
        kopf.insert(5, (488, "USt", True))
    for x, t, rechts in kopf:
        b.t(x, top, t, 8, fett=True, rechts=rechts)
    top += 22
    for n, p in enumerate(r.pos, 1):
        werte = [(52, str(n), False), (78, p.text, False), (360, menge_de(p.menge), True),
                 (368, p.einheit, False), (450, de(p.preis), True), (545, de(p.betrag), True)]
        if mit_spalte:
            werte.insert(5, (488, f"{p.satz} %", True))
        for x, t, rechts in werte:
            b.t(x, top, t, 8.5, rechts=rechts)
        top += 16
    b.linie(48, top, 547, 0.5)
    top += 10
    w = r.waehrung
    zeilen = [] if r.firma.kleinunternehmer else [("Nettobetrag", f"{de(r.netto)} {w}", False)]
    if not r.firma.kleinunternehmer:
        for satz, (_basis, ust) in r.ust_je_satz().items():
            if satz:
                zeilen.append((f"zzgl. {satz} % USt", f"{de(ust)} {w}", False))
        if not r.ust:
            zeilen.append(("Umsatzsteuer", f"{de(Decimal(0))} {w}", False))
    zeilen.append(("Rechnungsbetrag", f"{de(r.netto + r.ust)} {w}", True))
    for lab, wert, fett in zeilen:
        b.t(370, top, lab, 9, fett=fett)
        b.t(545, top, wert, 9, fett=fett, rechts=True)
        top += 14
    top += 12
    b.t(50, top, "Zahlbar innerhalb 14 Tagen ohne Abzug.", 9)
    top += 20
    if r.kurs:
        ust_eur = (r.ust / r.kurs).quantize(C2, ROUND_HALF_UP)
        b.t(50, top, f"Umrechnungskurs: 1 EUR = {str(r.kurs).replace('.', ',')} USD (Stand {r.kursdatum:%d.%m.%Y})",
            9)
        top += 13
        b.t(50, top, f"Umsatzsteuer in EUR: {de(ust_eur)} EUR", 9)
        top += 13
    if r.hinweis:
        b.t(50, top, r.hinweis, 9, fett=True)
        top += 13
    _fuss(b, r.firma)
    b.fertig()


def absender_csv(f: Firma, pfad: Path) -> None:
    pfad.write_text("Name;Strasse;PLZ;Ort;USt-IdNr;Steuernummer;IBAN;BIC;Telefon;E-Mail;Register\n"
                    f"{f.name};{f.strasse};{f.plz};{f.ort};{f.ust};{f.stnr};{f.iban};;{f.telefon};{f.email};"
                    f"{f.register}\n", encoding="utf-8")


# ------------------------------------------------------------------ Anlernen (Profile + Vorlagen)
LERNEN = {  # Absender -> Rechnungen, die im Assistenten angelernt werden, und die Steuerfall-Auswahl
    "lichtbogen": (["LM-26-2007", "LM-26-2002", "LM-26-2001", "LM-26-2003"], "auto"),  # Steuerspalte: 19 % -> S, 0 % -> Fall aus Hinweis
    "wendel": (["WE-26-0302", "WE-26-0301"], "auto"),      # nur Summen: Fall je Rechnung aus dem Steuerhinweis
    "lindner": (["GL-26-0014", "GL-26-0015"], "KU"),       # Kleinunternehmer: fest
}


def anlernen() -> None:
    import yaml

    from fakturafalter import absender as absender_mod
    from fakturafalter import anlernen as al
    from fakturafalter import konfig

    firmen = {f.kurz: f for f in (LICHTBOGEN, WENDEL, LINDNER)}
    for alt in HIER.glob("profil-*.yaml"):
        alt.unlink()
    shutil.rmtree(HIER / "angelernt", ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        roh = {"arbeitsordner": str(tmp / "lauf"), "modus": "nur_pdf", "pdf_profile": [],
               "optionen": {"sichtteil": "original", "xrechnung_zusatz": False}}
        pf = tmp / "k.yaml"
        pf.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")
        k = konfig.lade_konfig(pf)
        k.ordner_anlegen()
        k.pfad_datei = pf
        for kurz, (nummern, fall) in LERNEN.items():
            f = firmen[kurz]
            for nr in nummern:
                s = al.Sitzung(Path(shutil.copy(EINGANG / f"{nr}.pdf", k.eingang)), k)
                s.absender = absender_mod.Absender(f.name, f.strasse, "", f.plz, f.ort, f.ust, f.stnr, f.iban, "",
                                                   f.telefon, f.email, f.register, f.kleinunternehmer)
                s.steuerfall_setzen("" if fall == "auto" else fall)
                for feld in s.fehlende():
                    s.bestaetigen(feld)
                erg, v = s.speichern(pf)
                if v is None:
                    raise SystemExit(f"{nr}: nicht gelernt: {erg.hinweise}")
                al.nur_pdf_schalten(s.profil, True)
                print(f"{nr}: Vorlage {v['profil']}-{v['kennung']}, in Folge {v['statistik'].get('folge_treffer', 0)}")
        for p in tmp.glob("profil-*.yaml"):  # Beispiel: nach einer Rechnung in Folge „sicher“
            t = p.read_text(encoding="utf-8").replace("nur_pdf_ab: 5", "nur_pdf_ab: 1  # Beispiel; üblich 5")
            (HIER / p.name).write_text(t, encoding="utf-8")
        shutil.copytree(tmp / "angelernt", HIER / "angelernt")


def main() -> None:
    EINGANG.mkdir(exist_ok=True)
    for r in rechnungen():
        zeichnen(r, EINGANG / f"{r.nr}.pdf")
    for f in (LICHTBOGEN, WENDEL, LINDNER):
        absender_csv(f, HIER / f"absender-{f.kurz}.csv")
    print(f"{len(rechnungen())} Rechnungen in {EINGANG}")
    if "--anlernen" in sys.argv:
        anlernen()


if __name__ == "__main__":
    main()
