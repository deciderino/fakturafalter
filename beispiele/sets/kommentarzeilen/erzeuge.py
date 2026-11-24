#!/usr/bin/env python3
"""Testdaten-Set „Kommentarzeilen“: zwei erfundene Rechnungen eines fiktiven Absenders im Mandanten-Layout.

Zweck (Fix in der Erkennung vor dem nächsten Release):
- Kommentarzeilen ohne Menge, Preis und Betrag unter einer normalen Position. Der Text beginnt links in der
  Einheitenspalte und läuft quer bis in die Bezeichnungsspalte. Soll: Der Kommentar wird als weitere Zeile an
  ``description[]`` der Position darüber angehängt; er erzeugt keine eigene Position und hat keine Einheit.
- Die Rechnungsnummer steht außerhalb des Kopfblocks, oben links unter dem Briefkopf („Rechnung Nr. …“).
  Datum, Kundennummer, Bestellnummer usw. stehen rechts im Block.
- Beleg 1 dient zum Anlernen, Beleg 2 (gleiches Layout, andere Nummer, andere Kommentare) zum Nachlesen.

Baut auf ``beispiele/sets/fiktiva/erzeuge.py`` auf (Geometrie, Hilfen, Zeichnen-Grundlagen werden importiert,
fiktiva selbst bleibt unverändert). Alle Namen, Anschriften, Nummern und Beträge sind erfunden.

Aufruf (aus der Repo-Wurzel):

    .venv/bin/python beispiele/sets/kommentarzeilen/erzeuge.py

Deterministisch: fester Seed (``SEED``), reportlab mit ``invariant=1``.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

HIER = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fiktiva_erzeuge", HIER.parent / "fiktiva" / "erzeuge.py")
F = importlib.util.module_from_spec(_spec)
sys.dont_write_bytecode = True                                # kein __pycache__ in fiktiva/
sys.modules[_spec.name] = F                                   # nötig für @dataclass im Modul
_spec.loader.exec_module(F)                                   # nur Definitionen, main() läuft nicht

SEED = 26_4712
R, B = F.R, F.B
BREITE, HOEHE, LINKS, RECHTS = F.BREITE, F.HOEHE, F.LINKS, F.RECHTS
AKZENT, GRAU, DUNKEL, HELL, HELLER, WEISS = F.AKZENT, F.GRAU, F.DUNKEL, F.HELL, F.HELLER, F.WEISS
cent, betrag, menge, de, Blatt = F.cent, F.betrag, F.menge, F.de, F.Blatt

# Spalten: Menge (rechts) | Einheit (links) | Bezeichnung (links) | Einzelpreis „X € /N“ (rechts) | Gesamt (rechts)
X_MENGE, X_EINHEIT, X_BEZ, X_PREIS, X_GES = F.X_MENGE, F.X_ME, F.X_BEZ, 468.00, F.X_GES
ZEILE0, TAKT = F.ZEILE0, F.TAKT
LETZTE = F.S1_LETZTE                                         # einseitig: Rechnungsbetrag höchstens Index 19
NR_TOP = 116.50                                              # „Rechnung Nr. …“ oben links unter dem Briefkopf


# ------------------------------------------------------------------ Prüfziffern
def ust_id(basis8: str) -> str:
    """DE + 8 Ziffern + Prüfziffer nach ISO 7064 MOD 11,10."""
    produkt = 10
    for z in basis8:
        summe = (int(z) + produkt) % 10 or 10
        produkt = (2 * summe) % 11
    pz = 11 - produkt
    return f"DE{basis8}{0 if pz == 10 else pz}"


def iban(konto10: str) -> str:
    """Deutsche IBAN mit erfundener BLZ 00000000, Prüfziffer nach ISO 13616 (mod 97)."""
    bban = "00000000" + konto10
    pz = 98 - int(bban + "131400") % 97
    i = f"DE{pz:02d}{bban}"
    return " ".join(i[k:k + 4] for k in range(0, len(i), 4))


VERKAEUFER = {
    "name": "Testoria Zerspanungstechnik GmbH",
    "street": "Beispielallee 5",
    "postal_code": "34117",
    "city": "Kassel",
    "ust_id": ust_id("27182818"),
    "iban": iban("0002604711"),
    "bic": "TESTDEX1XXX",
    "bank": "Musterbank Kassel",
    "email": "buchhaltung@testoria.example",
    "register": "Amtsgericht Kassel, HRB 000000",
    "ceo": "Max Beispiel",
}
TELEFON = "Tel. 0561 000000-0"
MARKE, MARKE_ZUSATZ, KUERZEL = "TESTORIA", "Zerspanungstechnik GmbH", "TZ"


# ------------------------------------------------------------------ Belege (Struktur fest, Preise aus dem Seed)
@dataclass
class Pos:
    qty: int
    unit: str
    bezeichnung: str
    spanne: tuple[float, float]
    pe: int = 1
    kommentar: str | None = None          # Kommentarzeile unter der Position (Einheit-x bis in die Bezeichnung)
    preis: Decimal | None = None

    @property
    def gesamt(self) -> Decimal:
        return cent(self.qty * self.preis / self.pe)

    @property
    def description(self) -> list[str]:
        return [self.bezeichnung] + ([self.kommentar] if self.kommentar else [])


@dataclass
class Spez:
    nummer: str
    rolle: str                            # anlernen | nachlesen
    datum: date
    kunde: dict
    bestellung: str
    versand: str
    skonto: int | None
    pos: list[Pos] = field(default_factory=list)


SPEZ = [
    Spez("2026-04711", "anlernen", date(2026, 10, 14),
         {"name_lines": ["Hagedorn Fördersysteme GmbH", "Abteilung Einkauf"], "street": "Kanalstraße 18",
          "postal_code": "30165", "city": "Hannover", "customer_number": "20318"},
         "4500817263", "Spedition", 2,
         [Pos(10, "Stk.", "Lagerbock LB-40 Stahl verzinkt 31-2208", (18, 65)),
          Pos(40, "Stk.", "Antriebswelle Ø 25 nach Zeichnung 26-0731", (60, 140),
              kommentar="davon mit Härtung 12 Stück"),
          Pos(500, "Stk.", "Zylinderschraube ISO 4762 M6x20 8.8 verzinkt", (4, 14), pe=100),
          Pos(25, "Stk.", "Zahnriemenscheibe T10 Z=32 44-1907", (24, 90),
              kommentar="davon Restmenge folgt"),
          Pos(6, "Std.", "Montagearbeit vor Ort", (58, 78))]),
    Spez("2026-04738", "nachlesen", date(2026, 10, 21),
         {"name_lines": ["Krummbach Verpackungsmaschinen KG"], "street": "Am Gleisdreieck 4",
          "postal_code": "59065", "city": "Hamm", "customer_number": "20457"},
         "BE-26-588", "DHL", None,
         [Pos(30, "Stk.", "Kettenrad 1/2\" Z=19 18-6604", (14, 39),
              kommentar="davon 8 Stück brüniert"),
          Pos(1000, "Stk.", "Sechskantmutter ISO 4032 M8 verzinkt", (2.5, 8), pe=100),
          Pos(12, "Stk.", "Spannsatz SP-30 Ø 30 mm 52-0175", (19, 48)),
          Pos(4, "Stk.", "Getriebeflansch GF-80 63-3390", (55, 210),
              kommentar="Restmenge 2 Stück folgt in KW 46"),
          Pos(250, "Stk.", "Passfeder DIN 6885 A 8x7x40", (18, 55), pe=100)]),
]


# ------------------------------------------------------------------ Zeichnen
def kopf_fuss(b: Blatt, d: dict):
    v = VERKAEUFER
    c = b.c
    c.setFillColor(AKZENT)
    c.roundRect(LINKS, HOEHE - 85.04, 36.85, 36.85, 2.5, stroke=0, fill=1)
    b.text(72.28, 64.12, KUERZEL, B, 12.5, WEISS, mitte=True)
    b.text(102.05, 48.04, MARKE, B, 16, AKZENT)
    b.text(102.61, 69.40, MARKE_ZUSATZ, R, 9, GRAU)
    b.text(RECHTS, 57.44, f"{v['street']} · {v['postal_code']} {v['city']}", R, 8, GRAU, rechts=True)
    b.text(552.75, 73.50, f"{TELEFON}  ·  {v['email']}", R, 7.4, GRAU, rechts=True)
    b.linie(LINKS, 103.46, RECHTS, 0.85, AKZENT)
    # Rechnungsnummer bewusst außerhalb des Kopfblocks: oben links unter dem Briefkopf
    b.text(LINKS, NR_TOP, f"Rechnung Nr. {d['invoice']['number']}", B, 10.5, AKZENT)
    b.text(LINKS, 144.76, f"{v['name']} · {v['street']} · {v['postal_code']} {v['city']}", R, 6.9, GRAU)
    k = d["buyer"]
    plz_top = 298.12
    str_top = plz_top - 11.34 * 2
    b.text(LINKS, plz_top, f"{k['postal_code']} {k['city']}", R, 9.4, DUNKEL)
    b.text(LINKS, str_top, k["street"], R, 9.4, DUNKEL)
    for j, n in enumerate(reversed(k["name_lines"])):
        b.text(LINKS, str_top - 11.34 * (j + 1), n, R, 9.4, DUNKEL)
    # Kopfblock rechts (ohne Rechnungsnummer)
    inv = d["invoice"]
    b.text(337.32, 147.93, "RECHNUNG", B, 15.5, AKZENT)
    felder = [("RE-Datum:", inv["date"]), ("Leistungsdatum:", inv["service_date"]),
              ("Kundennummer:", k["customer_number"]), ("Bestellnummer:", inv["order_number"]),
              ("Versandart:", inv["shipping"])]
    for j, (lab, wert) in enumerate(felder):
        top = 190.58 + 15.307 * j
        b.text(337.32, top, lab, R, 8.1, GRAU)
        if wert:
            b.text(445.04, top - 0.28, wert, R, 8.5, DUNKEL)
    # Tabellenkopf
    b.text(LINKS, 378.03, "Rechnungspositionen", B, 10.2, AKZENT)
    b.linie(LINKS, 401.39, RECHTS, 0.8, AKZENT)
    for x, t, rechts in [(X_MENGE, "Menge", True), (X_EINHEIT, "Einheit", False), (X_BEZ, "Bezeichnung", False),
                         (X_PREIS, "Einzelpreis", True), (X_GES, "Gesamt", True)]:
        b.text(x, 413.22, t, B, 8, AKZENT, rechts=rechts)
    b.linie(LINKS, 428.03, RECHTS, 0.45, HELL)
    # Zahlungsblock (Seite 1, fest)
    b.linie(LINKS, 688.82, RECHTS, 0.45, HELLER)
    b.text(LINKS, 699.29, "Zahlungsbedingungen", B, 9, AKZENT)
    for j, t in enumerate(d["payment_terms_text"]):
        b.text(LINKS, 715.89 + 11.91 * j, t, R, 8.4, DUNKEL)
    # Fuß
    b.linie(LINKS, 763.09, RECHTS, 0.65, AKZENT)
    b.text(LINKS, 773.74, v["name"], B, 7.7, AKZENT)
    b.text(LINKS, 785.24, f"GF: {v['ceo']} · AG Kassel, HRB 000000", R, 7.1, GRAU)
    b.text(LINKS, 796.29, f"USt-IdNr.: {v['ust_id']}", R, 7.1, GRAU)
    b.text(314.65, 773.74, v["bank"], B, 7.7, AKZENT)
    b.text(314.65, 785.24, f"IBAN: {v['iban']}", R, 7.1, GRAU)
    b.text(314.65, 796.29, f"BIC: {v['bic']}", R, 7.1, GRAU)
    b.text(LINKS, 820.93, "FIKTIVE MUSTERRECHNUNG · TESTDATEN · KEINE ZAHLUNG", B, 6.8, GRAU)
    b.text(552.75, 820.75, "Seite 1 von 1", R, 7.0, GRAU, rechts=True)


def einzelpreis(p: Pos) -> str:
    return f"{betrag(p.preis)} /{p.pe}"                  # z. B. „3,40 € /1“, „12,50 € /100“


def zeichnen(pfad: Path, d: dict, ps: list[Pos]):
    c = canvas.Canvas(str(pfad), pagesize=(BREITE, HOEHE), invariant=1, pageCompression=1)
    c.setTitle(f"Rechnung {d['invoice']['number']}")
    c.setAuthor(f"{VERKAEUFER['name']} – fiktiver Rechnungssteller")
    c.setSubject("Fiktive Testrechnung für Fakturafalter; keine echte Forderung")
    c.setCreator("beispiele/sets/kommentarzeilen/erzeuge.py")
    b = Blatt(c)
    t = d["totals"]
    kopf_fuss(b, d)
    z = 0
    gl = lambda: ZEILE0 + TAKT * z                         # noqa: E731
    for p in ps:
        b.zeile(X_MENGE, gl(), menge(p.qty), groesse=9.0, rechts=True)
        b.zeile(X_EINHEIT, gl(), p.unit)
        b.zeile(X_BEZ, gl(), p.bezeichnung)
        b.zeile(X_PREIS, gl(), einzelpreis(p), rechts=True)
        b.zeile(X_GES, gl(), betrag(p.gesamt), rechts=True)
        z += 1
        if p.kommentar:                                    # ohne Menge, Preis, Betrag; beginnt auf x der Einheit
            b.zeile(X_EINHEIT, gl(), p.kommentar)
            z += 1
    b.zeile(X_BEZ, gl(), "Netto", groesse=8.9)
    b.zeile(X_GES, gl(), betrag(Decimal(t["net"])), groesse=8.9, rechts=True)
    z += 1
    b.zeile(X_BEZ, gl(), "MwSt. 19 %", groesse=8.9)
    b.zeile(X_GES, gl(), betrag(Decimal(t["vat"])), groesse=8.9, rechts=True)
    z += 1
    b.zeile(X_BEZ, gl(), "Rechnungsbetrag", schrift=B, groesse=9.0, farbe=AKZENT)
    txt = betrag(Decimal(t["gross"]))
    b.zeile(X_GES, gl(), txt, schrift=B, groesse=9.3, farbe=AKZENT, rechts=True)
    x0 = X_GES - pdfmetrics.stringWidth(txt, B, 9.3)
    for off in (1.99, 4.09):
        b.linie(x0, gl() + off, X_GES, 0.55, AKZENT)
    c.showPage()
    c.save()


# ------------------------------------------------------------------ Soll
def beleg(n: int, s: Spez, rng: random.Random) -> dict:
    for p in s.pos:
        p.preis = F.preis_zufall(rng, p.spanne)
    netto = sum(p.gesamt for p in s.pos)
    ust = cent(netto * Decimal("0.19"))
    brutto = netto + ust
    faellig = s.datum + timedelta(days=30)
    if s.skonto:
        sk_datum = s.datum + timedelta(days=10)
        sk_betrag = cent(brutto * s.skonto / 100)
        text = [f"zahlbar bis {de(sk_datum, True)} bei {s.skonto} % Skonto ({betrag(sk_betrag)})",
                f"bis {de(faellig)} ohne Abzug"]
    else:
        sk_datum, sk_betrag = None, None
        text = [f"zahlbar bis {de(faellig)} ohne Abzug"]
    zeilen = sum(len(p.description) for p in s.pos)
    return {
        "datei": f"Rechnung_{n:03d}_{s.nummer}.pdf",
        "format": "PDF 1.4 (reportlab, Schriften eingebettet)",
        "rolle": s.rolle,
        "holdout": False,
        "seller": dict(VERKAEUFER),
        "buyer": dict(s.kunde),
        "invoice": {"number": s.nummer, "date": de(s.datum), "service_date": de(s.datum),
                    "order_number": s.bestellung, "shipping": s.versand},
        "positions": [{"qty": p.qty, "unit": p.unit, "description": p.description,
                       "unit_price": f"{p.preis:.2f}", "kind": "regular", "price_unit": f"/{p.pe}",
                       "price_unit_qty": p.pe, "min_order": False, "total": f"{p.gesamt:.2f}",
                       "comment_lines": [p.kommentar] if p.kommentar else []} for p in s.pos],
        "vat_rate": "19.00",
        "discount_percent": f"{s.skonto:.2f}" if s.skonto else None,
        "discount_days": 10 if s.skonto else None,
        "payment_days": 30,
        "totals": {"net": f"{netto:.2f}", "vat": f"{ust:.2f}", "gross": f"{brutto:.2f}"},
        "payment": {"discount_date": de(sk_datum) if sk_datum else None, "due_date": de(faellig),
                    "discount_amount": f"{sk_betrag:.2f}" if sk_betrag is not None else None,
                    "discount_base": "gross" if s.skonto else None},
        "payment_terms_text": text,
        "page_count": 1,
        "pages": [{"page": 1, "position_indices": list(range(1, len(s.pos) + 1)), "line_count": zeilen,
                   "transfer": None, "carry_forward": None, "summary_present": True,
                   "payment_block_present": True}],
        "test_flags": {
            "address_name_lines": len(s.kunde["name_lines"]),
            "address_blank_lines": 1,
            "missing_order_number": not s.bestellung,
            "discount_applied": bool(s.skonto),
            "price_unit_100_count": sum(p.pe == 100 for p in s.pos),
            "comment_line_count": sum(bool(p.kommentar) for p in s.pos),
            "comment_line_positions": [i + 1 for i, p in enumerate(s.pos) if p.kommentar],
            "comment_starts_at_unit_column": True,
            "invoice_number_outside_header_block": True,
            "invoice_number_label": f"Rechnung Nr. {s.nummer}",
            "last_table_row_index": zeilen + 2,
            "note": f"Kommentarzeilen + Rechnungsnummer oben links; Rolle: {s.rolle}",
        },
    }


def selbstcheck(d: dict, s: Spez):
    nr = d["invoice"]["number"]
    netto, ust, brutto = (Decimal(d["totals"][k]) for k in ("net", "vat", "gross"))
    for p in s.pos:
        assert p.preis > 0 and p.qty > 0 and p.gesamt == cent(p.qty * p.preis / p.pe), nr
    assert sum(Decimal(p["total"]) for p in d["positions"]) == netto, f"{nr}: Σ Positionen ≠ Netto"
    assert cent(netto * Decimal("0.19")) == ust and netto + ust == brutto, f"{nr}: Netto + USt ≠ Brutto"
    if s.skonto:
        assert Decimal(d["payment"]["discount_amount"]) == cent(brutto * s.skonto / 100), f"{nr}: Skonto"
    assert d["test_flags"]["last_table_row_index"] <= LETZTE, f"{nr}: Tabelle zu lang"
    assert d["test_flags"]["comment_line_count"] == 2, nr
    for p in s.pos:                                        # Kommentar muss quer bis in die Bezeichnung laufen
        if p.kommentar:
            assert X_EINHEIT + pdfmetrics.stringWidth(p.kommentar, R, 8.8) > X_BEZ + 20, (nr, p.kommentar)
            assert X_EINHEIT + pdfmetrics.stringWidth(p.kommentar, R, 8.8) < X_PREIS - 100, (nr, p.kommentar)
    sys.path.insert(0, str(HIER.parents[2] / "src"))
    from fakturafalter import pflichtpruefung                # Prüfziffern mit der App-Funktion kontrollieren
    assert pflichtpruefung.ust_id_de_gueltig(VERKAEUFER["ust_id"]), VERKAEUFER["ust_id"]
    assert pflichtpruefung.iban_gueltig(VERKAEUFER["iban"]), VERKAEUFER["iban"]


def zurueckgelesen(pdf: Path, d: dict, s: Spez):
    """PDF mit pdfplumber zurücklesen: Texte, Nummer oben links, Wortboxen der Kommentarzeilen."""
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        assert len(doc.pages) == 1
        seite = doc.pages[0]
        text = seite.extract_text() or ""
        woerter = seite.extract_words()
    for t in d["payment_terms_text"]:
        assert t in text, (pdf.name, t)
    assert betrag(Decimal(d["totals"]["gross"])) in text and "MwSt. 19 %" in text
    nr = [w for w in woerter if w["text"] == d["invoice"]["number"]]
    assert len(nr) == 1 and nr[0]["x0"] < 300 and 103.46 < nr[0]["top"] < 144, nr
    zeilen = {}
    for w in woerter:
        zeilen.setdefault(round(w["top"], 1), []).append(w)
    boxen = []
    for p in s.pos:
        if not p.kommentar:
            continue
        erstes = p.kommentar.split()[0]
        kandidaten = [ws for ws in zeilen.values()
                      if " ".join(x["text"] for x in sorted(ws, key=lambda x: x["x0"])) == p.kommentar]
        assert len(kandidaten) == 1, (pdf.name, p.kommentar)
        ws = sorted(kandidaten[0], key=lambda x: x["x0"])
        assert ws[0]["text"] == erstes and abs(ws[0]["x0"] - X_EINHEIT) < 0.05, ws[0]
        assert ws[-1]["x1"] > X_BEZ, ws[-1]
        boxen.append({"text": p.kommentar, "x0": round(ws[0]["x0"], 2), "x1": round(ws[-1]["x1"], 2),
                      "top": round(ws[0]["top"], 2)})
    return boxen


def main():
    rng = random.Random(SEED)
    rech, ref = HIER / "Rechnungen", HIER / "Referenzdaten"
    for o in (rech, ref):
        if o.exists():
            shutil.rmtree(o)
        o.mkdir()
    for n, s in enumerate(SPEZ, start=1):
        d = beleg(n, s, rng)
        selbstcheck(d, s)
        pdf = rech / d["datei"]
        zeichnen(pdf, d, s.pos)
        boxen = zurueckgelesen(pdf, d, s)
        d["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        (ref / (pdf.stem + ".json")).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{d['datei']}  {s.rolle:9s}  Brutto {d['totals']['gross']}")
        for bx in boxen:
            print(f"    Kommentar x {bx['x0']}–{bx['x1']} top {bx['top']}: {bx['text']}")
    print(f"2 Belege. Einheit x={X_EINHEIT}, Bezeichnung x={X_BEZ}. Selbstcheck ok.")


if __name__ == "__main__":
    main()
