# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""0.6.0: Rechnung mit allen EN-16931-Gruppen, die Fakturafalter übernimmt (fiktive Daten)."""
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from fakturafalter import pipeline, rechnen
from fakturafalter.modell import (
    Anhang,
    Anschrift,
    Klassifizierung,
    Lieferung,
    Merkmal,
    Rechnungsbezug,
    Referenzen,
    Steuer,
    Steuervertreter,
    Zahlungsempfaenger,
    ZuAbschlag,
)

BEISPIELE = Path(__file__).resolve().parent.parent / "beispiele"


def volle_rechnung(konfig, art: str = "380", lastschrift: bool = False):
    _, rs = pipeline.einlesen(BEISPIELE / "variante-a_positionen_utf8.csv", konfig)
    r = rs[0]
    r.art = art
    p0, p1 = r.positionen[0], r.positionen[1]
    p0.bruttopreis, p0.preisrabatt, p0.einzelpreis = p0.einzelpreis + D("2.00"), D("2.00"), None
    p0.zu_abschlaege = [ZuAbschlag(prozent=D("10"), grund="Mengenrabatt", grund_code="95")]
    p0.notiz, p0.beschreibung = "Lieferung in zwei Kartons", "Ausführliche Beschreibung der Position"
    p0.leistung_von, p0.leistung_bis = date(2026, 10, 1), date(2026, 10, 15)
    p0.merkmale = [Merkmal("Farbe", "Blau"), Merkmal("Länge", "2 m")]
    p0.klassifizierungen = [Klassifizierung("43211503", "TST", "19.0501")]
    p0.kaeufer_artikelnummer, p0.standard_id, p0.standard_schema = "KA-1", "4000000000006", "0160"
    p0.ursprungsland, p0.bestellposition, p0.objektkennung, p0.buchungsreferenz = "DE", "3", "OBJ-9", "4711"
    p1.zu_abschlaege = [ZuAbschlag(zuschlag=True, betrag=D("5.00"), grund="Expresszuschlag")]
    r.zu_abschlaege = [ZuAbschlag(prozent=D("2"), grund="Treuerabatt", grund_code="95"),
                       ZuAbschlag(zuschlag=True, betrag=D("12.50"), grund="Fracht", grund_code="FC",
                                  steuer=Steuer("S", D("19")))]
    r.vorausbezahlt = D("50.00")
    if art in ("381", "384"):
        r.bezuege = [Rechnungsbezug("RE-2026-0815", date(2026, 9, 30))]
    r.referenzen = Referenzen(auftrag="AB-77", wareneingang="WE-5", projekt="PRJ-12", projekt_name="Neubau Halle 3",
                              vertrag="V-2026-01", lieferschein="LS-4711", ausschreibung="LOS-3", objekt="ZAEHLER-1",
                              objekt_schema="AAG", buchung="8400")
    r.lieferung = Lieferung(name="Baustelle Halle 3", ort_id="LO-1",
                            anschrift=Anschrift("Werkstraße 9", "12345", "Musterstadt", "DE", "Tor 2"))
    r.zahlungsempfaenger = Zahlungsempfaenger("Factoring Beispiel AG", "ZE-1", "HRB 999")
    r.steuervertreter = Steuervertreter("Steuerkanzlei Beispiel", "DE123456788",
                                        Anschrift("Kanzleiweg 3", "54321", "Beispielhausen", "DE"))
    r.anhaenge = [Anhang("Stundenzettel", "Stundenzettel Oktober", uri="https://example.com/sz.pdf"),
                  Anhang("Aufmass", "Aufmaß", daten=b"Aufmass Halle 3\n", mime="text/csv", dateiname="aufmass.csv")]
    if lastschrift:
        z = r.zahlung
        z.art, z.mandat, z.glaeubiger_id, z.lastschrift_iban = "59", "MANDAT-0042", "DE98ZZZ09999999999", \
            "DE75512108001245126199"
    rechnen.berechnen(r)
    return r
