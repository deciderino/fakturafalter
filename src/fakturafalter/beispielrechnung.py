# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Fiktive Beispielrechnung für die Vorschau im Layouteditor (alle Daten erfunden, Beispiel-Domains)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import rechnen
from .modell import Anschrift, Partei, Position, Rechnung, Zahlung

_ARTIKEL = (("ART-1001", "Konferenztisch, Eiche, 180 cm", "H87", "420.00"),
            ("ART-2044", "Schreibtischleuchte LED", "H87", "64.50"),
            ("ART-3102", "Montage und Anlieferung", "LS", "95.00"),
            ("ART-4410", "Bürostuhl ergonomisch, Stoffbezug anthrazit", "H87", "289.00"),
            ("ART-5120", "Rollcontainer mit drei Schubladen", "H87", "149.90"),
            ("ART-6033", "Kabelkanal, 2 m, weiß", "MTR", "12.40"))


def rechnung(verkaeufer: Partei | None = None, positionen: int = 3, zahlung: Zahlung | None = None) -> Rechnung:
    """Beispiel mit ``positionen`` Zeilen (für die Folgeseite z. B. 40). ``verkaeufer``: Stammdaten des
    Absender-Profils, sonst „Musterwerk GmbH“."""
    v = verkaeufer or Partei(name="Musterwerk GmbH", anschrift=Anschrift("Holzgartenstraße 4", "70174", "Stuttgart"),
                             ust_id="DE123456788", steuernummer="", register="Amtsgericht Stuttgart HRB 12345",
                             kontakt_email="rechnung@musterwerk.example")
    pos = []
    for i in range(positionen):
        a, b, e, p = _ARTIKEL[i % len(_ARTIKEL)]
        m = Decimal("1") if e == "LS" else Decimal(1 + (i * 3) % 7)
        pos.append(Position(nr=str(i + 1), artikelnummer=a, bezeichnung=b, menge=m, einheit=e, einzelpreis=Decimal(p)))
    z = zahlung or Zahlung(art="58", iban="DE89370400440532013000", bic="COBADEFFXXX", kontoinhaber=v.name,
                           bedingungen="Zahlbar innerhalb von 14 Tagen ohne Abzug.", ziel_tage=14)
    r = Rechnung(nummer="RE-2026-0042", datum=date(2026, 11, 3), leistungsdatum=date(2026, 10, 31),
                 kundennummer="K-1042", bestellnummer="B-7781", verkaeufer=v,
                 kaeufer=Partei(name="Nordlicht Handel GmbH", anschrift=Anschrift("Hafenstraße 18", "20457", "Hamburg")),
                 positionen=pos, zahlung=z)
    rechnen.berechnen(r)
    return r
