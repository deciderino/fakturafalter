# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""PDF-Erkennung: Gegenprüfung CSV ↔ Druck, Anlernen von Vorlagen und „nur PDF“ an den Beispielen
in beispiele/pdf-erkennung/ (sechs erfundene Verkäufer mit verschiedenen Druck-Layouts)."""

import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fakturafalter import adapter_csv, adapter_pdf, pdferkennung, pipeline, rechnen, validierung
from fakturafalter.konfig import lade_konfig
from fakturafalter.pflichtpruefung import iban_gueltig, ust_id_de_gueltig

BSP = Path(__file__).resolve().parent.parent / "beispiele" / "pdf-erkennung"
VERKAEUFER = ["baeckerei", "elektro", "gartenbau", "musikschule", "pixelwerk", "metallbau"]
WERKZEUGE = all(validierung.verfuegbar().values())


@pytest.fixture
def k(tmp_path):
    k = lade_konfig(BSP / "konfiguration.yaml")
    for n in ("eingang", "ausgang", "erledigt", "fehler", "pruefen"):
        setattr(k, n, tmp_path / n)
        (tmp_path / n).mkdir()
    return k


def paare(kurz: str) -> list[tuple[Path, Path]]:
    out = []
    for c in sorted((BSP / "eingang").glob(f"{kurz}_*.csv")):
        out.append((c, BSP / "eingang" / f"{c.stem.split('_', 1)[1]}.pdf"))
    return out


def lauf(k, *dateien: Path) -> pipeline.Lauf:
    for d in dateien:
        shutil.copy(d, k.eingang)
    return pipeline.verarbeiten(sorted(k.eingang.iterdir()), k)


def profil(k, kurz: str) -> dict:
    return next(p for p in k.csv_profile if p["profil"] == kurz)


def vorlage(k, kurz: str) -> dict:
    (v,) = pdferkennung.vorlagen_laden(profil(k, kurz))
    return v


def zeilen(pdf: Path):
    return pdferkennung.zeilen_aus(adapter_pdf.seiten_lesen(pdf))


# ------------------------------------------------------------------ Einzelteile
def test_zahlen_und_daten_lesen():
    assert pdferkennung.betraege("1.234,56")[0][0] == Decimal("1234.56")
    assert pdferkennung.betraege("1,234.56")[0][0] == Decimal("1234.56")
    assert pdferkennung.daten("3. Oktober 2026") == [date(2026, 10, 3)]
    assert pdferkennung.daten("03.10.26") == [date(2026, 10, 3)]
    assert pdferkennung.zeitraum("01.10.2026 – 31.10.2026") == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    assert pdferkennung.zeitraum("Oktober 2026") == (date(2026, 10, 1), date(2026, 10, 31))


def test_beispiele_haben_gueltige_pruefziffern(k):
    for kurz in VERKAEUFER:
        p = profil(k, kurz)
        if p["verkaeufer"].get("ust_id"):
            assert ust_id_de_gueltig(p["verkaeufer"]["ust_id"]), kurz
        assert iban_gueltig(p["zahlung"]["iban"]), kurz


def test_voreinstellungen():
    es = pdferkennung.einstellungen({})
    assert es["gegenpruefung"] and es["anlernen"] and not es["nur_pdf"]
    assert es["nur_pdf_ab"] == 5 and es["toleranz"] == Decimal("0.01")


# ------------------------------------------------------------------ Anlernen und „nur PDF“ je Layout
@pytest.mark.parametrize("kurz", VERKAEUFER)
def test_anlernen_dann_nur_pdf(k, kurz):
    ps = paare(kurz)
    assert len(ps) == 8
    for csv, pdf in ps[:7]:  # sieben Paare: Gegenprüfung ohne Abweichung, Vorlage lernt
        l = lauf(k, csv, pdf)
        (e,) = l.ergebnisse
        assert e.status == "ok", e.hinweise
        assert any("ohne Abweichung" in h for h in e.hinweise)
    v = vorlage(k, kurz)
    assert v["statistik"]["rechnungen"] == 7
    assert pdferkennung.sicher(v, pdferkennung.einstellungen(profil(k, kurz)))

    csv8, pdf8 = ps[7]
    l = lauf(k, pdf8)  # ausgeschaltet (Voreinstellung): abgelehnt
    assert not l.ergebnisse and "ausgeschaltet" in next(iter(l.datei_fehler.values()))
    for d in k.eingang.iterdir():
        d.unlink()

    profil(k, kurz)["pdf_erkennung"] = {"nur_pdf": True}
    l = lauf(k, pdf8)
    (e,) = l.ergebnisse
    assert e.status == "ok", e.hinweise
    assert any(h.startswith("INFO: Automatisch (Nur PDF)") for h in e.hinweise)

    # Das Ergebnis aus dem Druck allein entspricht der CSV
    (soll,) = adapter_csv.lesen(csv8, profil(k, kurz), k)
    soll.summen = rechnen.berechnen(soll)
    ist, grund = pdferkennung.nur_pdf(pdf8, zeilen(pdf8), k.csv_profile, k)
    assert ist is not None, grund
    ist.summen = rechnen.berechnen(ist)
    for a in ("nummer", "datum", "leistungsdatum", "leistung_von", "leistung_bis", "kundennummer"):
        assert getattr(ist, a) == getattr(soll, a), a
    assert ist.kaeufer.anschrift == soll.kaeufer.anschrift
    assert ist.kaeufer.name == soll.kaeufer.name
    assert len(ist.positionen) == len(soll.positionen)
    for a, b in zip(ist.positionen, soll.positionen):
        assert (
            a.bezeichnung,
            a.menge,
            a.einheit,
            a.einzelpreis,
            a.steuer.kategorie,
            a.steuer.satz,
        ) == (b.bezeichnung, b.menge, b.einheit, b.einzelpreis, b.steuer.kategorie, b.steuer.satz)
        assert a.artikelnummer == b.artikelnummer
    assert (ist.summen.netto, ist.summen.ust, ist.summen.brutto) == (
        soll.summen.netto,
        soll.summen.ust,
        soll.summen.brutto,
    )

    if WERKZEUGE:  # alle erzeugten Rechnungen lokal prüfen
        pdfs = sorted(k.erledigt.parent.joinpath("ausgang").rglob("*.pdf"))
        assert len(pdfs) == 8
        erg = validierung.pruefen(pdfs)
        assert erg and all(x.gueltig and not x.fehler for x in erg), [
            x.zeile() for x in erg if x.fehler
        ]


def test_nur_pdf_noch_nicht_sicher(k):
    profil(k, "metallbau")["pdf_erkennung"] = {"nur_pdf": True}
    for csv, pdf in paare("metallbau")[:3]:
        lauf(k, csv, pdf)
    l = lauf(k, paare("metallbau")[7][1])
    assert not l.ergebnisse
    assert "noch nicht sicher" in next(iter(l.datei_fehler.values()))


def test_nur_pdf_ohne_vorlage(k):
    l = lauf(k, paare("pixelwerk")[0][1])
    assert "keine angelernte Vorlage" in next(iter(l.datei_fehler.values()))


def test_abweichung_verhindert_anlernen(k):
    csv, pdf = paare("baeckerei")[0]
    lauf(k, csv, pdf)
    vorher = vorlage(k, "baeckerei")["statistik"]["rechnungen"]
    lauf(
        k,
        BSP / "fehlerfaelle" / "baeckerei_SK-2026-0499.csv",
        BSP / "fehlerfaelle" / "SK-2026-0499.pdf",
    )
    assert vorlage(k, "baeckerei")["statistik"]["rechnungen"] == vorher


# ------------------------------------------------------------------ Gegenprüfung: kaputte Fälle
FEHLERFAELLE = {
    "baeckerei_SK-2026-0499.csv": (
        "SK-2026-0499.pdf",
        "[BT-109] CSV und Druck weichen ab: Nettosumme 399.58 ≠ 399.08",
    ),
    "pixelwerk_PW-INV-2026-0199.csv": (
        "PW-INV-2026-0199.pdf",
        "[BT-2] CSV und Druck weichen ab: Rechnungsdatum 01.04.2026 ≠ 02.04.2026",
    ),
    "gartenbau_GL-2026-199.csv": (
        "gartenbau_GL-2026-199.pdf",
        "[BT-1] CSV und Druck weichen ab: Rechnungsnummer GL-2026-199 ≠ GL-2026-919",
    ),
    "elektro_EF-1099.csv": (
        "EF-1099.pdf",
        "[BT-84] CSV und Druck weichen ab: IBAN DE44000000000002718281 ≠ DE48000000000009999999",
    ),
    "musikschule_KR-2026-099.csv": (
        "KR-2026-099.pdf",
        "[BT-72] Leistungsdatum (BT-72) bzw. Leistungszeitraum",
    ),
}


@pytest.mark.parametrize("csv", sorted(FEHLERFAELLE))
def test_fehlerfaelle_landen_in_pruefen(k, csv):
    pdf, erwartet = FEHLERFAELLE[csv]
    l = lauf(k, BSP / "fehlerfaelle" / csv, BSP / "fehlerfaelle" / pdf)
    (e,) = l.ergebnisse
    assert e.status == "pruefen"
    assert any(erwartet in h for h in e.hinweise), e.hinweise
    assert list(k.pruefen.glob("*.json"))


def test_gegenpruefung_abschaltbar_und_felder_waehlbar(k):
    csv, pdf = (
        BSP / "fehlerfaelle" / "baeckerei_SK-2026-0499.csv",
        BSP / "fehlerfaelle" / "SK-2026-0499.pdf",
    )
    profil(k, "baeckerei")["pdf_erkennung"] = {"felder": ["BT-1", "BT-2"]}
    (e,) = lauf(k, csv, pdf).ergebnisse
    assert not any("weichen ab" in h for h in e.hinweise)
    for d in k.eingang.iterdir():
        d.unlink()
    profil(k, "baeckerei")["pdf_erkennung"] = {"gegenpruefung": False}
    (e,) = lauf(k, csv, pdf).ergebnisse
    assert not any("weichen ab" in h or "Gegenprüfung" in h for h in e.hinweise)


def test_toleranz(k):
    csv, pdf = paare("gartenbau")[0]
    (r,) = adapter_csv.lesen(csv, profil(k, "gartenbau"), k)
    r.summen = rechnen.berechnen(r)
    es = pdferkennung.einstellungen(profil(k, "gartenbau"))
    z = zeilen(pdf)
    r.summen.netto += Decimal("0.01")
    assert not [a for a in pdferkennung.gegenpruefen(r, z, None, es)[0] if a.feld == "BT-109"]
    r.summen.netto += Decimal("0.01")
    assert [a for a in pdferkennung.gegenpruefen(r, z, None, es)[0] if a.feld == "BT-109"]


def test_schalter_aus_der_konfiguration_gehen_vor(tmp_path):
    import yaml

    for p in BSP.glob("*.yaml"):
        shutil.copy(p, tmp_path)
    d = yaml.safe_load((tmp_path / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["pdf_erkennung"] = {"elektro": {"gegenpruefung": False, "nur_pdf": True}}
    (tmp_path / "konfiguration.yaml").write_text(
        yaml.safe_dump(d, allow_unicode=True), encoding="utf-8"
    )
    k = lade_konfig(tmp_path / "konfiguration.yaml")
    es = pdferkennung.einstellungen(profil(k, "elektro"))
    assert not es["gegenpruefung"] and es["nur_pdf"] and es["anlernen"]
    assert pdferkennung.einstellungen(profil(k, "baeckerei"))["gegenpruefung"]


def _zeile_aus(*abschnitte: str, top: float = 100) -> pdferkennung.Zeile:
    """Eine Druckzeile aus Abschnitten (fiktive Werte); Abschnitte weit auseinander."""
    ws, segs, x = [], [], 50.0
    for a in abschnitte:
        seg = []
        for t in a.split():
            w = pdferkennung.Wort(t, x, x + 6 * len(t), top, 0, top + 10)
            seg.append(w)
            x = w.x1 + 3
        segs.append(seg)
        ws += seg
        x += 60
    return pdferkennung.Zeile(0, top, ws, segs)


def test_rechnungsdatum_ohne_beschriftung():
    """BT-2 ohne „Datum“: Briefdatum „Ort, den …“ und „Rechnung Nr. … vom …“ – nicht „Bestellung vom …“."""
    such = lambda *z: pdferkennung._druckwert_suchen("BT-2", list(z), None)  # noqa: E731
    assert such(_zeile_aus("Honorarrechnung Nr. 2026-0417", "Göttingen, den 8. Oktober 2026")) == (
        "08.10.2026"
    )
    assert such(_zeile_aus("Handelsrechnung Nr. 2026-48001 vom 07.10.2026")) == "07.10.2026"
    assert (
        such(_zeile_aus("Rechnung gemäß Bestellung vom 28.09.2026")) == pdferkennung.NICHT_GEFUNDEN
    )
    # eine Beschriftung „Datum“ geht vor
    assert (
        such(
            _zeile_aus("Rechnung Nr. 1 vom 01.10.2026", top=100),
            _zeile_aus("Rechnungsdatum:", "02.10.2026", top=120),
        )
        == "02.10.2026"
    )


def test_einheit_in_klammern_wird_geprueft():
    """„Stück“ (H87) bei „Regalberatung (Stunden)“: prüfen, nicht still; „(rot)“ ist keine Einheit."""
    from fakturafalter.modell import Position, Rechnung

    def r_mit(bez):
        r = Rechnung(nummer="X", datum=date(2026, 10, 1))
        r.positionen = [Position(nr="1", bezeichnung=bez, menge=Decimal("1"), einheit="H87")]
        return r

    r = r_mit("Regalberatung (Stunden): Sortimentsplanung")
    pdferkennung.einheit_in_klammern_pruefen(r)
    assert [h.feld for h in r.hinweise if h.stufe == "pruefen"] == ["BT-130"]
    r = r_mit("Lenkerband (rot)")
    pdferkennung.einheit_in_klammern_pruefen(r)
    assert not r.hinweise


def test_summenzeilen_beschriftung():
    """„Gesamt EUR inkl. MwSt.“ ist BT-112, „Gesamt EUR ohne MwSt.“ BT-109; ein Doppelpunkt als eigener
    Abschnitt („Bruttosumme | : | 649,09“) trennt Beschriftung und Betrag nicht."""
    such = lambda f, *z: pdferkennung._druckwert_suchen(f, list(z), None)  # noqa: E731
    zeilen = [
        _zeile_aus("Gesamt EUR ohne MwSt.", "539,00", top=100),
        _zeile_aus("19 % MwSt.", "102,41", top=112),
        _zeile_aus("Gesamt EUR inkl. MwSt.", "641,41", top=124),
    ]
    assert such("BT-109", *zeilen) == "539.00"
    assert such("BT-112", *zeilen) == "641.41"
    assert such("BT-112", _zeile_aus("Bruttosumme", ":", "649,09")) == "649.09"
    assert such("BT-112", _zeile_aus("Zahlbetrag", ":", "649,09")) == "649.09"


def test_endsumme_ist_brutto():
    """„Endsumme“ ist die Bruttosumme (BT-112), nicht die Nettosumme."""
    zeilen = [
        _zeile_aus("Summe Netto", "€ 860,02", top=100),
        _zeile_aus("19,00% USt. auf 860,02 €", "€ 163,40", top=112),
        _zeile_aus("Endsumme", "€ 1.023,42", top=124),
    ]
    assert pdferkennung._druckwert_suchen("BT-112", zeilen, None) == "1023.42"
    assert pdferkennung._druckwert_suchen("BT-109", zeilen, None) == "860.02"


def test_debitorennummer_ist_kundennummer():
    """„Debitorennr.“ ist die Kundennummer (Assistent und Druckwert-Suche)."""
    from fakturafalter import anlernen

    assert anlernen.ist_beschriftung("kundennummer", "Debitorennr.")
    z = _zeile_aus("Debitorennr.", "30252", "Lieferdatum", "10.10.2026")
    assert pdferkennung._druckwert_suchen("kundennummer", [z], None) == "30252"


@pytest.mark.parametrize(
    "alt, fort, soll",
    [
        ("Montage-", "material verzinkt", "Montagematerial verzinkt"),
        ("Edelstahl-", "Schraube M8", "Edelstahl-Schraube M8"),
        ("Front-", "und Rücklicht", "Front- und Rücklicht"),
        ("Kabel 3x1,5 -", "lfm", "Kabel 3x1,5 - lfm"),
        ("Wartung", "Heizung", "Wartung Heizung"),
    ],
)
def test_bezeichnung_trennstrich_am_zeilenende(alt, fort, soll):
    assert pdferkennung.bezeichnung_fortsetzen(alt, fort) == soll
