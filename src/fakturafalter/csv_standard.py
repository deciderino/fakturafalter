# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Eingebautes CSV-Standardprofil und Vorlagen (ab 0.9.9, nur DE-Format, fiktive Beispieldaten)."""

from __future__ import annotations

from pathlib import Path

from . import steuerfaelle

PROFIL_ID = "fakturafalter-standard"
PROFIL_DATEI = "profil-fakturafalter-standard.yaml"

# Die Pflichtnamen der Vorlage: genau so muss die Kopfzeile sie tragen, damit das Profil greift.
PFLICHTNAMEN = (
    "Rechnungsnummer",
    "Rechnungsdatum",
    "Leistungsdatum",
    "Kundenname",
    "Bezeichnung",
    "Menge",
    "Einheit",
    "Einzelpreis",
    "Steuersatz",
)

# Wiederholte Kopffelder der Pflicht- und Beleggruppe: Abweichung in der Rechnung -> Zu prüfen.
KOPF_GLEICH = (
    "Rechnungsnummer",
    "Rechnungsdatum",
    "Leistungsdatum",
    "Kundennummer",
    "Kundenname",
    "Belegart",
    "Währung",
    "Leistung von",
    "Leistung bis",
    "Bestellnummer",
    "Leitweg-ID",
    "Summe netto",
    "Summe USt",
    "Summe brutto",
)

# (Feld, exakter Spaltenname, typ oder None, Pflichtspalte)
_SPALTEN: list[tuple[str, str, str | None, bool]] = [
    ("BT-1", "Rechnungsnummer", None, True),
    ("BT-2", "Rechnungsdatum", "datum", True),
    ("BT-72", "Leistungsdatum", "datum", True),
    ("kundennummer", "Kundennummer", None, False),
    ("BT-153", "Bezeichnung", None, True),
    ("BT-129", "Menge", "zahl", True),
    ("BT-130", "Einheit", None, True),
    ("BT-146", "Einzelpreis", "zahl", True),
    ("steuer", "Steuersatz", None, True),
    ("belegart", "Belegart", None, False),
    ("BT-5", "Währung", None, False),
    ("BT-73", "Leistung von", "datum", False),
    ("BT-74", "Leistung bis", "datum", False),
    ("BT-13", "Bestellnummer", None, False),
    ("BT-10", "Leitweg-ID", None, False),
    ("BT-109", "Summe netto", "zahl", False),
    ("BT-110", "Summe USt", "zahl", False),
    ("BT-112", "Summe brutto", "zahl", False),
    ("BT-44", "Kundenname", None, True),
    ("kunden_name_2", "Kundenbezeichnung 2", None, False),
    ("kunden_name_3", "Kundenbezeichnung 3", None, False),
    ("BT-50", "Straße", None, False),
    ("BT-51", "Adresszusatz", None, False),
    ("BT-53", "PLZ", None, False),
    ("BT-52", "Ort", None, False),
    ("BT-55", "Land", None, False),
    ("BT-48", "Kunde-USt-IdNr.", None, False),
    ("BT-49", "E-Rechnungsadresse", None, False),
    ("BT-47", "Handelsregister", None, False),
    ("BT-70", "Liefername", None, False),
    ("BT-75", "Lieferstraße", None, False),
    ("BT-78", "Liefer-PLZ", None, False),
    ("BT-77", "Lieferort", None, False),
    ("BT-80", "Lieferland", None, False),
    ("BT-126", "Positionsnummer", None, False),
    ("BT-155", "Artikelnummer", None, False),
    ("BT-149", "Preiseinheit", "zahl", False),
    ("gesamtpreis_position", "Positionsbetrag", "zahl", False),
    ("BT-127", "Positionstext", None, False),
    ("BT-154", "Artikelbeschreibung", None, False),
    ("BT-156", "Kundenartikelnummer", None, False),
    ("BT-157", "GTIN", None, False),
    ("zeichnungsnummer", "Zeichnungsnummer", None, False),
    ("index", "Index", None, False),
    ("BT-132", "Bestellposition", None, False),
    ("BT-159", "Ursprungsland", None, False),
    ("BT-158", "Warengruppe", None, False),
    ("BT-128", "Objektkennung Position", None, False),
    ("BT-133", "Buchungsreferenz Position", None, False),
    ("BT-134", "Leistung von Position", "datum", False),
    ("BT-135", "Leistung bis Position", "datum", False),
    ("BT-160", "Merkmal", None, False),
    ("BT-161", "Merkmalwert", None, False),
    ("BT-138", "Rabatt Prozent", "prozent", False),
    ("BT-136", "Rabatt Betrag", "zahl", False),
    ("BT-139", "Rabattgrund", None, False),
    ("BT-143", "Zuschlag Prozent", "prozent", False),
    ("BT-141", "Zuschlag Betrag", "zahl", False),
    ("BT-144", "Zuschlaggrund Position", None, False),
    ("BT-148", "Bruttopreis", "zahl", False),
    ("BT-147", "Preisnachlass", "zahl", False),
    ("zahlungsziel_tage", "Zahlungsziel", "tage", False),
    ("skonto_satz", "Skonto", "prozent", False),
    ("skonto_tage", "Zahlungsziel mit Skonto", "tage", False),
    ("skonto_basisbetrag", "Skonto-Basisbetrag", "zahl", False),
    ("skonto_satz_2", "Skonto 2", "prozent", False),
    ("skonto_tage_2", "Zahlungsziel mit Skonto 2", "tage", False),
    ("skonto_basisbetrag_2", "Skonto-Basisbetrag 2", "zahl", False),
    ("zahlungsart", "Zahlungsart", None, False),
    ("BT-83", "Verwendungszweck", None, False),
    ("BT-89", "Mandatsreferenz", None, False),
    ("BT-90", "Gläubiger-ID", None, False),
    ("BT-91", "Kunden-IBAN", None, False),
    ("BT-59", "Zahlungsempfänger", None, False),
    ("BT-94", "Belegrabatt Prozent", "prozent", False),
    ("BT-92", "Belegrabatt Betrag", "zahl", False),
    ("BT-97", "Belegrabattgrund", None, False),
    ("BT-99", "Fracht", "zahl", False),
    ("BT-101", "Zuschlag Prozent Beleg", "prozent", False),
    ("BT-104", "Zuschlaggrund", None, False),
    ("BT-113", "Anzahlung", "zahl", False),
    ("BT-14", "Auftragsnummer", None, False),
    ("BT-11", "Projektnummer", None, False),
    ("BT-12", "Vertragsnummer", None, False),
    ("BT-16", "Lieferscheinnummer", None, False),
    ("BT-15", "Wareneingang", None, False),
    ("BT-17", "Vergabenummer", None, False),
    ("BT-18", "Objektkennung", None, False),
    ("BT-19", "Kostenstelle", None, False),
    ("BT-22", "Bemerkung", None, False),
    ("steuerhinweis", "Steuerhinweis", None, False),
    ("kurs", "Kurs", "zahl", False),
    ("kursdatum", "Kursdatum", "datum", False),
    ("BT-111", "USt EUR", "zahl", False),
    ("BT-124", "Link auf Unterlage", None, False),
    ("zeilenart", "Zeilenart", None, False),
    ("BT-25", "Bezugsrechnung", None, False),
    ("BT-26", "Bezugsdatum", "datum", False),
]

# Die Vollvorlage nutzt in der Kopfzeile „Zuschlag Prozent“ für den Belegzuschlag (nach Fracht).
# Im Profil bleibt der eindeutige interne Name; die Datei-Spalte heißt wie in der Spezifikation.
_SPALTEN = [
    (f, "Zuschlag Prozent" if s == "Zuschlag Prozent Beleg" else s, t, p) for f, s, t, p in _SPALTEN
]

EINHEITEN = {
    "Stück": "H87",
    "Stk": "H87",
    "Stk.": "H87",
    "Stck": "H87",
    "St.": "H87",
    "Stunde": "HUR",
    "Stunden": "HUR",
    "Std": "HUR",
    "Std.": "HUR",
    "h": "HUR",
    "m": "MTR",
    "Meter": "MTR",
    "lfm": "MTR",
    "m²": "MTK",
    "m2": "MTK",
    "qm": "MTK",
    "m³": "MTQ",
    "m3": "MTQ",
    "cbm": "MTQ",
    "kg": "KGM",
    "g": "GRM",
    "t": "TNE",
    "l": "LTR",
    "Ltr": "LTR",
    "pauschal": "LS",
    "pausch": "LS",
    "Pauschale": "LS",
    "psch": "LS",
    "Tag": "DAY",
    "Tage": "DAY",
    "Woche": "WEE",
    "Wochen": "WEE",
    "Monat": "MON",
    "Paar": "PR",
    "Set": "SET",
    "Satz": "SET",
    "Rolle": "XRO",
    "Karton": "XCT",
    "Paket": "XPK",
    "Pkt": "XPK",
    "Pak": "XPK",
    "unbekannt": "pruefen",
}

STEUER = {
    "19 %": {"BT-151": "S", "BT-152": 19},
    "19": {"BT-151": "S", "BT-152": 19},
    "7 %": {"BT-151": "S", "BT-152": 7},
    "7": {"BT-151": "S", "BT-152": 7},
    "0 %": {"BT-151": "E", "BT-152": 0, "BT-120": "Steuerfrei", "BT-121": ""},
    "steuerfrei": {"BT-151": "E", "BT-152": 0, "BT-120": "Steuerfrei", "BT-121": ""},
    "Reverse Charge": steuerfaelle.mapping("AE"),
    "RC": steuerfaelle.mapping("AE"),
    "igL": steuerfaelle.mapping("K"),
    "EX": steuerfaelle.mapping("G"),
    "§19": steuerfaelle.mapping("KU"),
    "unbekannt": "satz",
}


def ist_standard(profil: dict | None) -> bool:
    return bool(profil) and (profil.get("profil") == PROFIL_ID or profil.get("_eingebaut") is True)


def bekannte_spalten(profil: dict | None = None) -> set[str]:
    if profil:
        namen = set()
        for teil in (profil.get("felder") or {}).values():
            for d in (teil or {}).values():
                if isinstance(d, dict) and d.get("spalte"):
                    namen.add(d["spalte"])
        return namen
    return {s for _f, s, _t, _p in _SPALTEN}


def unbekannte_spalten(kopf: list[str], profil: dict | None = None) -> list[str]:
    bekannt = bekannte_spalten(profil)
    return [c for c in kopf if c and c not in bekannt]


def hinweise_unbekannt(r, kopf: list[str], profil: dict | None = None) -> None:
    for name in unbekannte_spalten(kopf, profil):
        r.hinweis(
            "info",
            f"Spalte „{name}“ ist nicht im Standardprofil und wird nicht gelesen.",
            "csv",
        )


def profil() -> dict:
    """Eingebautes Standardprofil (exakte Namen, letzte Priorität, DE-Format)."""
    from .csv_einrichtung import FELDER

    typ_von = {f: typ for f, _n, _teil, typ, _p in FELDER}
    kopf, pos = {}, {}
    for feld, spalte, typ, pflicht in _SPALTEN:
        d: dict = {"spalte": spalte}
        t = typ or typ_von.get(feld)
        if t and t != "text":
            d["typ"] = t
        if feld == "BT-130":
            d["mapping"] = "einheiten"
        if feld == "steuer":
            d["mapping"] = "steuer"
        if feld == "belegart":
            d["mapping"] = "belegart"
        if feld == "zahlungsart":
            d["mapping"] = "zahlungsart"
        if not pflicht:
            d["optional"] = True
        teil = next((x[2] for x in FELDER if x[0] == feld), "kopf")
        if feld in ("BT-51", "BT-101"):
            teil = "kopf"
        (kopf if teil == "kopf" else pos)[feld] = d
    return {
        "profil": PROFIL_ID,
        "version": 2,
        "beschreibung": (
            "Eingebautes Standardformat (DE: UTF-8 mit BOM, Semikolon, Dezimalkomma, "
            "TT.MM.JJJJ). Greift nur, wenn die Kopfzeile die Pflichtnamen trägt und "
            "kein früheres aktives Profil passt."
        ),
        "datei": {
            "muster": "*.csv",
            "kodierung": "utf-8-sig",
            "trennzeichen": ";",
            "textbegrenzer": '"',
            "kopfzeile": True,
        },
        "zahlen": {"dezimal": ",", "tausender": "."},
        "datum": {"format": "%d.%m.%Y"},
        "aufbau": {
            "art": "zeile_je_position",
            "rechnung_schluessel": "Rechnungsnummer",
            "kopf_muss_gleich_sein": list(KOPF_GLEICH),
            "textzeile": {
                "ziel": "BT-154",
                "platzhalter": "#LEER",
                "leerzeile_modus": "beides",
                "verwaist": "BT-22",
                "zwischen": "vorher",
                "preis_ohne_menge": "pruefen",
                "trenner": "\n",
                "leer": ["BT-129", "BT-146", "text"],
            },
        },
        "felder": {"kopf": kopf, "position": pos},
        "mappings": {"einheiten": dict(EINHEITEN), "steuer": dict(STEUER)},
        "_eingebaut": True,
        "_datei": str(Path(__file__).resolve().parent / "ressourcen" / PROFIL_DATEI),
    }


def anhaengen(profile: list[dict], roh: dict | None = None) -> list[dict]:
    """Standardprofil ans Ende hängen, wenn es noch nicht in der Liste steht. Nicht überschreiben.

    Im Modus nur_pdf bleibt die Liste unverändert.
    """
    if (roh or {}).get("modus") == "nur_pdf":
        return profile
    if any(ist_standard(p) or p.get("profil") == PROFIL_ID for p in profile):
        return profile
    p = profil()
    opt = (roh or {}).get("optionen") or {}
    if "standardprofil_aktiv" in opt:
        p["aktiv"] = bool(opt["standardprofil_aktiv"])
    profile.append(p)
    return profile


def aktiv_setzen(roh: dict, an: bool) -> None:
    roh.setdefault("optionen", {})["standardprofil_aktiv"] = bool(an)


def _csv_zeile(zellen: list[str]) -> str:
    out = []
    for z in zellen:
        if any(c in z for c in ';"\n'):
            out.append('"' + z.replace('"', '""') + '"')
        else:
            out.append(z)
    return ";".join(out)


def vorlage_minimal() -> bytes:
    """UTF-8 mit BOM, die Pflichtspalten plus Anschrift (Straße, PLZ, Ort – § 14 UStG), zwei fiktive Rechnungen."""
    kopf = list(PFLICHTNAMEN) + ["Straße", "PLZ", "Ort"]
    zeilen = [
        kopf,
        [
            "RE-2026-1001",
            "02.11.2026",
            "31.10.2026",
            "Beispiel Handel GmbH",
            "Bürostuhl Modell Münster",
            "2",
            "Stück",
            "149,00",
            "19 %",
        ],
        [
            "RE-2026-1001",
            "02.11.2026",
            "31.10.2026",
            "Beispiel Handel GmbH",
            "Lieferung frei Haus",
            "",
            "",
            "",
            "",
        ],
        [
            "RE-2026-1001",
            "02.11.2026",
            "31.10.2026",
            "Beispiel Handel GmbH",
            "Montage vor Ort",
            "1",
            "Stunde",
            "65,00",
            "19 %",
        ],
        [
            "RE-2026-1002",
            "03.11.2026",
            "03.11.2026",
            "Beispiel Handel GmbH",
            "Beratung Einrichtung",
            "3",
            "Stunde",
            "90,00",
            "19 %",
        ],
    ]
    anschrift = ["Beispielweg 5", "12345", "Musterstadt"]
    zeilen = [zeilen[0]] + [z + anschrift for z in zeilen[1:]]
    text = "\n".join(_csv_zeile(z) for z in zeilen) + "\n"
    return text.encode("utf-8-sig")


def vorlage_voll() -> bytes:
    """UTF-8 mit BOM, alle Standardspalten inklusive Skonto-Stufe 2 (fiktiv)."""
    kopf = [s for _f, s, _t, _p in _SPALTEN]

    # Zeile 1 von RE-2026-1001: Position 1 mit Skonto 2/10 und Stufe 2: 1/20
    def z(**kw):
        d = {s: "" for s in kopf}
        d.update(kw)
        return [d[s] for s in kopf]

    gemein = dict(
        Rechnungsnummer="RE-2026-1001",
        Rechnungsdatum="02.11.2026",
        Leistungsdatum="31.10.2026",
        Kundennummer="K-1001",
        Kundenname="Beispiel Handel GmbH",
        Straße="Beispielweg 5",
        PLZ="12345",
        Ort="Musterstadt",
        Land="DE",
        **{"E-Rechnungsadresse": "rechnung@beispiel-handel.example"},
        Belegart="Rechnung",
        **{"Summe netto": "363,00", "Summe USt": "68,97", "Summe brutto": "431,97"},
        Währung="EUR",
        Bestellnummer="AB-44019",
        Zahlungsziel="30",
        Skonto="2",
        **{"Zahlungsziel mit Skonto": "10", "Skonto 2": "1", "Zahlungsziel mit Skonto 2": "20"},
        Zahlungsart="Überweisung",
        Bemerkung="Lieferung nach Vereinbarung.",
    )
    zeilen = [
        kopf,
        z(
            **gemein,
            Bezeichnung="Bürostuhl Modell Münster",
            Menge="2",
            Einheit="Stück",
            Einzelpreis="149,00",
            Steuersatz="19 %",
            Positionsnummer="1",
            Artikelnummer="ART-1040",
            Positionsbetrag="298,00",
            Zeilenart="Position",
        ),
        z(**gemein, Bezeichnung="Lieferung frei Haus"),
        z(
            **gemein,
            Bezeichnung="Montage vor Ort",
            Menge="1",
            Einheit="Stunde",
            Einzelpreis="65,00",
            Steuersatz="19 %",
            Positionsnummer="2",
            Artikelnummer="ART-2001",
            Positionsbetrag="65,00",
            Zeilenart="Position",
        ),
        z(
            Rechnungsnummer="RE-2026-1002",
            Rechnungsdatum="03.11.2026",
            Leistungsdatum="03.11.2026",
            Kundennummer="K-1001",
            Bezeichnung="Beratung Einrichtung",
            Menge="3",
            Einheit="Stunde",
            Einzelpreis="90,00",
            Steuersatz="19 %",
            Kundenname="Beispiel Handel GmbH",
            Straße="Beispielweg 5",
            PLZ="12345",
            Ort="Musterstadt",
            Land="DE",
            **{"Kunde-USt-IdNr.": "DE000000003", "E-Rechnungsadresse": "rechnung@beispiel-handel.example"},
            Positionsnummer="1",
        ),
    ]
    text = "\n".join(_csv_zeile(z) for z in zeilen) + "\n"
    return text.encode("utf-8-sig")


def vorlage_schreiben(ziel: Path, welche: str) -> list[Path]:
    """``welche``: minimal, voll oder beide. ``ziel`` ist ein Ordner oder eine Datei (nur eine Variante)."""
    ziel = Path(ziel)
    ordner = ziel if ziel.is_dir() or welche == "beide" else ziel.parent
    if welche == "beide" and not ziel.is_dir():
        ordner = ziel if ziel.suffix == "" else ziel.parent
        ordner.mkdir(parents=True, exist_ok=True)
    aus: list[Path] = []
    if welche in ("minimal", "beide"):
        p = (
            (ordner / "fakturafalter-standard-minimal.csv")
            if welche == "beide" or ziel.is_dir()
            else ziel
        )
        p.write_bytes(vorlage_minimal())
        aus.append(p)
    if welche in ("voll", "beide"):
        p = (
            (ordner / "fakturafalter-standard-voll.csv")
            if welche == "beide" or ziel.is_dir()
            else ziel
        )
        p.write_bytes(vorlage_voll())
        aus.append(p)
    return aus
