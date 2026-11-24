# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Eingangsdateien -> Rechnungen -> ZUGFeRD-PDF (+ XRechnung-CII) im Ausgangsordner.

Paarung PDF <-> CSV: über die Rechnungsnummer (BT-1); Rückfall über gleichen Dateinamen-Stamm.
Vorrang: CSV-Daten (strukturiert) vor PDF-Text; das PDF liefert dann den Sichtteil und wird gegengeprüft.
PDFs ohne Hand-Vorlage werden über die Rechnungsnummer im Text gepaart; ohne CSV nur mit einer sicher
angelernten Vorlage (siehe pdferkennung.py).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from . import (
    adapter_csv,
    adapter_pdf,
    adapter_xml,
    cii,
    dateien,
    layout,
    logdatei,
    nummernkreis,
    pdfa,
    pdferkennung,
    pflichtpruefung,
    protokoll,
    rechnen,
    sicht,
    validierung,
    zahlungsziel,
)
from . import dateien as dateien_mod
from .konfig import XRECHNUNG_ORDNER, Konfig
from .logdatei import NUR_DATEI
from .modell import Rechnung

log = logging.getLogger("fakturafalter")
CSV_ENDUNGEN = {".csv", ".txt", ".tsv"}
SCHON_ERZEUGT = (
    "schon erzeugt – der Druck kam nach seinen Daten (CSV/XML), Rechnung {nr} wurde ohne ihn erstellt; "
    "PDF liegt in „Erledigt“"
)


@dataclass
class Entwurf:
    """Erzeugte, noch nicht abgelegte Ausgaben im System-Temp-Ordner (ab 0.9.6): erst nach der Prüfung kommen
    sie – XML vor PDF, je atomar – in den Ausgang; der Ausgang sieht nie Halbes oder Ungeprüftes."""

    ordner: Path
    teile: list[tuple[Path, Path]] = field(default_factory=list)  # (Temp-Datei, Ziel); PDF zuerst

    @property
    def dateien(self) -> list[Path]:
        return [t for t, _z in self.teile]

    def verwerfen(self) -> None:
        shutil.rmtree(self.ordner, ignore_errors=True)


@dataclass
class Ergebnis:
    nummer: str
    status: str  # ok | pruefen | fehler
    dateien: list[Path] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    quellen: list[str] = field(default_factory=list)
    kunde: str = ""
    brutto: str = ""  # Dezimalzahl als Text, z.B. "175.55"
    pruefung: str = ""  # gültig | ungültig | nicht geprüft | "" (Prüfung aus / nichts erzeugt)
    entwurf: Entwurf | None = field(default=None, repr=False)  # erzeugt, noch nicht im Ausgang (ab 0.9.6)


@dataclass
class Lauf:
    ergebnisse: list[Ergebnis] = field(default_factory=list)
    datei_fehler: dict[str, str] = field(default_factory=dict)  # Eingangsdatei -> Grund
    anlernen: dict[str, str] = field(
        default_factory=dict
    )  # PDF für den Anlern-Assistenten -> Grund
    schon_erzeugt: dict[str, str] = field(
        default_factory=dict
    )  # Druck kam nach seinen Daten -> Rechnungsnummer

    @property
    def ok(self) -> bool:
        return not self.datei_fehler and all(e.status == "ok" for e in self.ergebnisse)

    # ab 0.9.6: allgemeine Hinweise zum Lauf (z. B. Protokoll fehlt) als (Vorlage, Werte) – Oberfläche + Log
    meldungen: list[tuple[str, dict]] = field(default_factory=list)


# ---------------------------------------------------------------- Fortschritt
SCHRITTE = 6  # Lesen, Erkennen/Einlesen, XML, PDF/A, Prüfen, Ablegen


@dataclass(frozen=True)
class Stand:
    """Fortschritt eines Laufs für die Oberfläche. Gesamt = Rechnungen × 6 Schritte; ``anteil`` 0…1.

    ``nr``/``gesamt``: aktuelle Rechnung und Anzahl (beim Lesen: Datei und Anzahl Dateien, ``zaehlt="datei"``).
    ``nr == 0``: Schritt läuft für alle Rechnungen zugleich (Prüfung in einer JVM).
    ``eingabe``: pdf | pdf_csv | pdf_xml | csv | xml (ohne PDF) – bestimmt die Beschriftung der Schritte.
    ``fehler``: Datei, die gerade gescheitert ist (der Lauf geht weiter)."""

    schritt: int
    nr: int
    gesamt: int
    datei: str = ""
    eingabe: str = "pdf"
    anteil: float = 0.0
    werkzeug: str = ""
    zaehlt: str = "rechnung"
    fehler: str = ""


def eingabe_art(quellen: list[str]) -> str:
    endungen = {Path(q).suffix.lower() for q in quellen}
    daten = "xml" if ".xml" in endungen else "csv" if endungen & CSV_ENDUNGEN else ""
    if ".pdf" in endungen:
        return f"pdf_{daten}" if daten else "pdf"
    return daten or "pdf"


class _Melder:
    """Rechnet Schritte in Anteile um und ruft den Rückruf; ein Fehler im Rückruf stört den Lauf nie."""

    def __init__(self, rueckruf):
        self.rueckruf = rueckruf
        self.eingabe = "pdf"

    def __call__(
        self, schritt: int, nr: int, gesamt: int, teil: float, basis: int | None = None, **kw
    ) -> None:
        """``teil``: erledigter Anteil ab Schritt ``basis`` (Standard: ``schritt``), gemessen in Schritten.
        XML und PDF/A laufen je Rechnung abwechselnd und zählen deshalb gemeinsam ab Schritt 2 (0…2)."""
        if self.rueckruf is None:
            return
        gesamt_n = max(gesamt, 1)
        b = schritt if basis is None else basis
        anteil = (b + min(max(teil, 0.0), float(SCHRITTE - b))) / SCHRITTE
        kw.setdefault("eingabe", self.eingabe)
        try:
            self.rueckruf(
                Stand(schritt, nr, gesamt_n if nr or gesamt else 0, anteil=round(anteil, 4), **kw)
            )
        except Exception:  # noqa: BLE001 – Anzeige darf die Verarbeitung nie abbrechen
            log.debug("Fortschritt-Rückruf fehlgeschlagen", exc_info=True)


def sicherer_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "ohne_nummer"


def _json_default(o):
    if isinstance(o, (Decimal, Path)):
        return str(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def ausgabe_namen(nr: str, r: Rechnung | None = None, k: Konfig | None = None) -> tuple[str, str]:
    """Dateinamen im Ausgang -> (ZUGFeRD-PDF, XRechnung-XML). Ohne Dateinamen-Muster in den Einstellungen
    (``optionen.nummernkreise``) wie bisher ``<Nummer>_zugferd.pdf`` / ``<Nummer>_xrechnung.xml``.
    Ein ungültiges Muster wirft ``nummernkreis.MusterFehler``."""
    n = sicherer_name(nr)
    pdf, xml = f"{n}_zugferd.pdf", f"{n}_xrechnung.xml"
    kreise = getattr(k, "nummernkreise", None) or {}
    if r is None or not kreise:
        return pdf, xml
    eigen = kreise.get(nummernkreis.kreis_von(r.art))
    rech = kreise.get("rechnung")
    m_pdf = (eigen and eigen.dateiname) or (rech and rech.dateiname) or ""
    m_xml = (eigen and eigen.dateiname_xrechnung) or (rech and rech.dateiname_xrechnung) or ""
    if m_pdf:
        pdf = nummernkreis.dateiname(m_pdf, r, ".pdf")
    if m_xml:
        xml = nummernkreis.dateiname(m_xml, r, ".xml")
    return pdf, xml


def ausgabe_namen_oder_hinweis(r: Rechnung, k: Konfig) -> tuple[str, str] | None:
    """Wie ``ausgabe_namen``; bei ungültigem Muster Hinweis „prüfen“ an der Rechnung und None."""
    try:
        return ausgabe_namen(r.nummer, r, k)
    except nummernkreis.MusterFehler as e:
        r.hinweis("pruefen", f"Dateinamen-Muster ungültig ({e}) – Einstellungen → Ausgabe", "Dateiname")
        return None


# ---------------------------------------------------------------- Einlesen
def einlesen(datei: Path, k: Konfig) -> tuple[str, list[Rechnung]]:
    """-> (art 'csv'|'xml'|'pdf'|'pdf_frei', Rechnungen). Wirft ValueError mit Klartext bei unbekanntem Format.
    'pdf_frei' = PDF ohne Hand-Vorlage: eine leere Rechnung als Platzhalter, gepaart wird in ``paaren``."""
    suf = datei.suffix.lower()
    if suf == ".pdf":
        seiten = adapter_pdf.seiten_lesen(datei)
        if not any(s.text.strip() for s in seiten):
            raise ValueError(
                "PDF hat keine Textebene (Scan?) – wird in Version 1 nicht unterstützt"
            )
        v = adapter_pdf.vorlage_finden(seiten, k.pdf_vorlagen)
        if not v:
            return "pdf_frei", [
                Rechnung(quelle=str(datei), sicht_pdf=(str(datei), [s.nr for s in seiten]))
            ]
        log.debug(
            "%s: PDF-Vorlage „%s“ (%d Seite(n))",
            datei.name,
            v.get("vorlage") or Path(v.get("_datei", "?")).stem,
            len(seiten),
        )
        return "pdf", adapter_pdf.lesen(datei, v, k, seiten)
    if suf in CSV_ENDUNGEN:
        for prof in k.csv_profile:
            if adapter_csv.profil_passt(datei, prof):
                log.debug(
                    "%s: CSV-Profil „%s“",
                    datei.name,
                    prof.get("profil") or prof.get("name") or Path(prof.get("_datei", "?")).stem,
                )
                try:
                    return "csv", adapter_csv.lesen(datei, prof, k)
                except adapter_csv.ProfilFehler:
                    raise
                except (ValueError, IndexError, KeyError) as e:
                    name = prof.get("profil") or prof.get("name") or "?"
                    raise ValueError(
                        f"Datei ähnelt dem Profil „{name}“, ist damit aber nicht lesbar "
                        f"({type(e).__name__}: {e})"
                    ) from e
        raise ValueError("Kein passendes CSV-Profil gefunden")
    if suf == ".xml":
        return "xml", adapter_xml.lesen(datei, k)
    raise ValueError(f"Dateityp {suf or '(ohne Endung)'} wird nicht verarbeitet")


def _gegenpruefen(daten: Rechnung, druck: Rechnung, nur_tabelle: bool = False) -> None:
    """CSV-Daten mit dem per Hand-Vorlage gelesenen Druck vergleichen (Abweichung -> pruefen).
    ``nur_tabelle``: Summen und Datum prüft schon pdferkennung, hier nur Positionsanzahl und Kundennummer."""
    vergleiche = [
        ("Positionsanzahl", len(daten.positionen), len(druck.positionen)),
        ("Kundennummer", daten.kundennummer, druck.kundennummer),
    ]
    if not nur_tabelle:
        vergleiche = [
            ("Bruttosumme", daten.summen.brutto, druck.summen.brutto),
            ("Nettosumme", daten.summen.netto, druck.summen.netto),
            ("Rechnungsdatum", daten.datum, druck.datum),
        ] + vergleiche
    for was, a, b in vergleiche:
        if a != b:
            daten.hinweis("pruefen", f"CSV und Druck weichen ab: {was} {a} ≠ {b}", was)
    if not nur_tabelle and all(a == b for _, a, b in vergleiche):
        daten.hinweis("info", f"Gegenprüfung mit Druck {Path(druck.quelle).name} ohne Abweichung")


def _profil(r: Rechnung, k: Konfig) -> dict | None:
    return next(
        (p for p in k.profile if r.profil and pdferkennung.profil_name(p) == r.profil), None
    )


def _nummer_im_text(nr: str, zeilen: list) -> bool:
    rx = re.compile(rf"(?<![\w/-]){re.escape(nr)}(?![\w/-])")
    return any(rx.search(z.text) for z in zeilen)


def _zum_anlernen(zeilen: list, k: Konfig) -> bool:
    """PDF ohne CSV in den Anlern-Assistenten? Ja bei einem Nur-PDF-Profil (Vorlage oder Absender passt)
    oder bei einem noch unbekannten Absender, wenn „Nur PDF“ eingerichtet ist."""
    prof, _ = pdferkennung.vorlage_suchen(zeilen, k.profile)
    if prof is not None:
        return prof.get("quelle") == "pdf"
    return bool(k.pdf_profile) or k.modus == "nur_pdf"


def _schon_erzeugt(zeilen: list, k: Konfig) -> str:
    """Rechnungsnummer, falls der Druck genau eine schon erzeugte Rechnung (protokoll.tsv) trägt, sonst ""."""
    treffer = [
        nr
        for nr in protokoll.bekannte_nummern(k)
        if _nummer_im_text(nr, zeilen)
    ]
    return treffer[0] if len(treffer) == 1 else ""


def paaren(
    eingelesen: list[tuple[Path, str, list[Rechnung]]],
    k: Konfig,
    datei_fehler: dict[str, str] | None = None,
    anlernen: dict[str, str] | None = None,
    schon_erzeugt: dict[str, str] | None = None,
) -> list[tuple[Rechnung, list[str]]]:
    """-> Liste (Rechnung mit Daten + Sichtteil, Quelldateien). Nicht zuordenbare PDFs ohne sichere
    Vorlage landen mit Grund in ``datei_fehler`` – bei „Nur PDF“ stattdessen in ``anlernen``."""
    csv_r: dict[str, Rechnung] = {}
    pdf_r: dict[str, Rechnung] = {}
    frei: list[Rechnung] = []
    doppelt: list[tuple[Rechnung, list[str]]] = []
    for datei, art, liste in eingelesen:
        if art == "pdf_frei":
            frei.extend(liste)
            continue
        ziel = csv_r if art in ("csv", "xml") else pdf_r
        for r in liste:
            rechnen.berechnen(r)
            if r.nummer in ziel:
                r.hinweis(
                    "fehler",
                    f"Rechnungsnummer {r.nummer} kommt im Eingang mehrfach vor "
                    f"({Path(ziel[r.nummer].quelle).name} und {datei.name})",
                    "BT-1",
                )
                doppelt.append((r, [str(datei)]))
                continue
            ziel[r.nummer] = r
    # Rückfall: PDF ohne erkannte Nummer, CSV mit gleichem Dateistamm und genau einer Rechnung
    for nr in [n for n in pdf_r if not n]:
        stamm = Path(pdf_r[nr].quelle).stem
        kand = [r for r in csv_r.values() if Path(r.quelle).stem == stamm]
        if len(kand) == 1:
            pdf_r[kand[0].nummer] = pdf_r.pop(nr)
            kand[0].hinweis("info", "Druck über gleichen Dateinamen zugeordnet")

    seiten: dict[str, list] = {}

    def zeilen_von(druck: Rechnung) -> list:
        pfad, idx = druck.sicht_pdf
        if pfad not in seiten:
            seiten[pfad] = adapter_pdf.seiten_lesen(Path(pfad))
        return pdferkennung.zeilen_aus(seiten[pfad], idx)

    # PDFs ohne Hand-Vorlage: Rechnungsnummer der CSV im Text suchen, sonst gleicher Dateistamm
    frei_zu: dict[str, Rechnung] = {}
    uebrig: list[Rechnung] = []
    for f in frei:
        offen = [nr for nr in csv_r if nr and nr not in pdf_r and nr not in frei_zu]
        kand = [nr for nr in offen if _nummer_im_text(nr, zeilen_von(f))]
        if len(kand) != 1:
            kand = [nr for nr in offen if Path(csv_r[nr].quelle).stem == Path(f.quelle).stem]
            if len(kand) == 1:
                csv_r[kand[0]].hinweis("info", "Druck über gleichen Dateinamen zugeordnet")
        if len(kand) == 1:
            frei_zu[kand[0]] = f
        else:
            uebrig.append(f)

    paare = []
    for nr in list(csv_r) + [n for n in pdf_r if n not in csv_r]:
        daten = csv_r.get(nr) or pdf_r[nr]
        druck = pdf_r.get(nr) or frei_zu.get(nr)
        quellen = [daten.quelle]
        if druck is not None and druck is not daten:
            quellen.append(druck.quelle)
            daten.sicht_pdf = druck.sicht_pdf
            prof = _profil(daten, k)
            if nr in pdf_r:
                _gegenpruefen(daten, druck, nur_tabelle=prof is not None)
            if prof is not None:
                pdferkennung.pruefen_und_lernen(
                    daten, zeilen_von(druck), prof, Path(druck.quelle).name
                )
            zahlungsziel.profiltext_sperren(daten, " ".join(z.text for z in zeilen_von(druck)))
        paare.append((daten, quellen))
    # PDF allein: nur mit sicher angelernter Vorlage („Automatisch, ohne Nachfrage“), immer mit Summenprüfung
    for f in uebrig:
        r, grund = pdferkennung.nur_pdf(Path(f.quelle), zeilen_von(f), k.profile, k)
        if r is None:
            if (
                schon_erzeugt is not None
                and k.modus != "nur_pdf"
                and (nr := _schon_erzeugt(zeilen_von(f), k))
            ):
                schon_erzeugt[f.quelle] = (
                    nr  # Druck kam nach seinen Daten: kein Fehler, nur ein Hinweis
                )
            elif anlernen is not None and _zum_anlernen(zeilen_von(f), k):
                anlernen[f.quelle] = grund
            elif datei_fehler is not None:
                datei_fehler[f.quelle] = grund
            continue
        rechnen.berechnen(r)
        pdferkennung.summen_pruefen(r)
        paare.append((r, [f.quelle]))
    return paare + doppelt


# ---------------------------------------------------------------- Erzeugen
def erzeugen(r: Rechnung, k: Konfig, ausgang: Path, bei_pdfa=None) -> list[Path]:
    """Erzeugen und sofort (ungeprüft) in ``ausgang`` ablegen. -> [PDF, ggf. XRechnung]."""
    return ablegen(entwurf_erzeugen(r, k, ausgang, bei_pdfa), k)


def entwurf_erzeugen(r: Rechnung, k: Konfig, ausgang: Path | None = None, bei_pdfa=None) -> Entwurf:
    """ZUGFeRD-PDF (+ XRechnung) erzeugen – in einen eigenen Ordner im System-Temp, nicht in den Ausgang.
    ``bei_pdfa``: optionaler Rückruf, sobald die XML steht und PDF/A beginnt (Fortschrittsanzeige)."""
    ausgang = Path(ausgang) if ausgang is not None else k.ausgang
    xml = cii.erzeugen(r, "EN16931")
    if bei_pdfa is not None:
        bei_pdfa()
    titel = f"{sicht.titel(r)} {r.nummer}"
    beschr = f"{sicht.titel(r)} {r.nummer} von {r.verkaeufer.name} an {r.kaeufer.name}"
    pdf_bytes = None
    if r.sicht_pdf and k.sichtteil == "original":
        pfad, seiten = r.sicht_pdf
        try:
            pdf_bytes = pdfa.zugferd_pdf(
                Path(pfad).read_bytes(),
                xml,
                titel=titel,
                autor=r.verkaeufer.name,
                beschreibung=beschr,
                seiten=seiten,
            )
        except pdfa.NichtReparierbar as e:
            r.hinweis("info", f"Druckseiten nicht PDF/A-tauglich ({e}) – Sichtteil neu aufgebaut")
    if pdf_bytes is None:
        pdf_bytes = _sichtteil_neu(r, k, xml, titel, beschr)
    n_pdf, n_xr = ausgabe_namen(r.nummer, r, k)
    ent = Entwurf(Path(tempfile.mkdtemp(prefix="fakturafalter-")))
    try:
        (ent.ordner / n_pdf).write_bytes(pdf_bytes)
        ent.teile.append((ent.ordner / n_pdf, ausgang / n_pdf))
        xr = _xrechnung(r, k)
        if xr is not None:
            xr_ordner = ausgang / XRECHNUNG_ORDNER if k.xrechnung_ablage == "unterordner" else ausgang
            (ent.ordner / n_xr).write_bytes(xr)
            ent.teile.append((ent.ordner / n_xr, xr_ordner / n_xr))
    except BaseException:
        ent.verwerfen()
        raise
    return ent


def _xrechnung(r: Rechnung, k: Konfig) -> bytes | None:
    if k.xrechnung_zusatz and r.ausgabeformat.startswith("XRECHNUNG"):
        if r.ausgabeformat == "XRECHNUNG_UBL":
            r.hinweis(
                "info", "XRechnung UBL ist noch nicht umgesetzt – XRechnung im CII-Format erzeugt"
            )
        if not r.leitweg_id:
            r.hinweis(
                "info",
                f"Keine Leitweg-ID im Kundenstamm – Käuferreferenz (BT-10) = Kundennummer {r.kundennummer}",
            )
        return cii.erzeugen(r, "XRECHNUNG")
    return None


def ablegen(ent: Entwurf, k: Konfig) -> list[Path]:
    """Geprüfte Ausgaben atomar in den Ausgang: XML vor PDF (wer auf die PDF wartet, findet die XML schon
    vor). Scheitert eine Datei, werden schon abgelegte wieder entfernt. Der Temp-Ordner wird immer gelöscht.
    -> Zielpfade in der Reihenfolge des Entwurfs (PDF zuerst)."""
    abgelegt: list[Path] = []
    zwischen = (k.protokoll,)
    try:
        for tmp, ziel in sorted(ent.teile, key=lambda t: t[1].suffix.lower() == ".pdf"):
            dateien.ablegen(tmp, ziel, zwischen)
            abgelegt.append(ziel)
    except BaseException:
        for z in abgelegt:
            Path(z).unlink(missing_ok=True)
        raise
    finally:
        ent.verwerfen()
    return [z for _t, z in ent.teile]


def vorlage_fuer(r: Rechnung, k: Konfig):
    """Layout-Vorlage des Absender-Profils (Layouteditor) oder None (festes Standardlayout).
    Eine ungültige Vorlage (z. B. von Hand geändert) gilt nicht: Standardlayout + Hinweis, Details ins Log."""
    roh = layout.roh_fuer(k.roh, r.verkaeufer.name)
    if not roh:
        return None
    try:
        return layout.laden(roh, k.basis)
    except (layout.LayoutFehler, TypeError, ValueError) as e:
        log.warning(
            "%s: Layout-Vorlage nicht verwendbar (%s) – Standardlayout",
            r.nummer,
            e,
            extra=NUR_DATEI,
        )
        r.hinweis(
            "info", "Layout-Vorlage nicht verwendbar – Standardlayout verwendet (Details im Log)"
        )
        return None


def _sichtteil_neu(r: Rechnung, k: Konfig, xml: bytes, titel: str, beschr: str) -> bytes:
    """Sichtteil neu aufbauen – mit der Layout-Vorlage des Absenders, sonst im Standardlayout. Lässt sich das
    Briefpapier nicht nach PDF/A-3 bringen, entsteht die Rechnung ohne Briefpapier (nie eine nicht konforme)."""
    vorlage = vorlage_fuer(r, k)
    bericht: list[str] = []
    try:
        return pdfa.zugferd_pdf(
            sicht.erzeugen(r, vorlage=vorlage, bericht=bericht),
            xml,
            titel=titel,
            autor=r.verkaeufer.name,
            beschreibung=beschr,
        )
    except pdfa.NichtReparierbar as e:
        if vorlage is None or not (vorlage.seite1.briefpapier or vorlage.folgeseite.briefpapier):
            raise
        log.warning(
            "%s: Briefpapier nicht PDF/A-tauglich (%s) – ohne Briefpapier erzeugt",
            r.nummer,
            e,
            extra=NUR_DATEI,
        )
        r.hinweis(
            "info",
            "Briefpapier nicht PDF/A-tauglich – Rechnung ohne Briefpapier erzeugt (Details im Log)",
        )
        vorlage.seite1.briefpapier = vorlage.folgeseite.briefpapier = ""
        return pdfa.zugferd_pdf(
            sicht.erzeugen(r, vorlage=vorlage),
            xml,
            titel=titel,
            autor=r.verkaeufer.name,
            beschreibung=beschr,
        )
    finally:
        for b in dict.fromkeys(bericht):
            log.info("%s: Layout – %s", r.nummer, b, extra=NUR_DATEI)


def _schreiben(ziel: Path, daten: bytes) -> None:
    dateien.schreiben(ziel, daten)


def _verschieben(datei: Path, ordner: Path) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / datei.name
    if ziel.exists():
        ziel = ordner / f"{datei.stem}_{datetime.now():%Y%m%d-%H%M%S}{datei.suffix}"
    return dateien.verschieben(datei, ziel)


def pflicht_kontext(k: Konfig, lauf_nummern=()) -> pflichtpruefung.Kontext:
    """Kontext der Pflichtprüfung: heute + alle bisher erzeugten Rechnungsnummern (protokoll.tsv), dazu die
    Einstellungen zum Nummernkreis und die Nummern des laufenden Stapels (für die Lückenwarnung)."""
    return pflichtpruefung.Kontext(
        bekannte_nummern=protokoll.bekannte_nummern(k),
        nummernkreise=dict(getattr(k, "nummernkreise", None) or {}),
        lauf_nummern=frozenset(n for n in lauf_nummern if n),
    )


def _hinweise(r: Rechnung) -> list[str]:
    return [str(h) for h in r.hinweise]


def nachpruefen(ergebnisse: list[Ergebnis], k: Konfig, bei_werkzeug=None) -> list[Ergebnis]:
    """Erzeugte Dateien lokal prüfen (Mustang + KoSIT, je eine JVM für alle). Ungültige Ausgaben wandern
    in den Fehlerordner, das Ergebnis wird „fehler“ mit deutscher Begründung. -> die ungültigen Ergebnisse.

    Fehlen die Werkzeuge oder scheitert ein Werkzeug technisch, bleibt die Ausgabe liegen („nicht geprüft“)."""
    if not ergebnisse:
        return []
    if not validierung.bereit():
        log.warning(
            "Prüfung nach Erstellung: Prüfwerkzeuge nicht gefunden – %d Rechnung(en) nicht geprüft",
            len(ergebnisse),
            extra=NUR_DATEI,
        )
        for e in ergebnisse:
            e.pruefung = "nicht geprüft"
            e.hinweise.append("INFO: Nicht lokal geprüft – Prüfwerkzeuge nicht gefunden")
        return []
    dateien = [d for e in ergebnisse for d in e.dateien]
    try:
        alle = (
            validierung.pruefen(dateien)
            if bei_werkzeug is None
            else validierung.pruefen(dateien, bei_werkzeug=bei_werkzeug)
        )
    except Exception as ex:  # noqa: BLE001 – Prüfung darf die Erzeugung nie verhindern
        log.exception("Prüfung nach Erstellung fehlgeschlagen")
        for e in ergebnisse:
            e.pruefung = "nicht geprüft"
            e.hinweise.append(
                f"WARNUNG: Nicht lokal geprüft – Prüfung fehlgeschlagen ({type(ex).__name__})"
            )
        return []
    je_datei: dict[str, list[validierung.Pruefergebnis]] = {}
    for p in alle:
        je_datei.setdefault(str(Path(p.datei)), []).append(p)
    ungueltig = []
    for e in ergebnisse:
        erg = [p for d in e.dateien for p in je_datei.get(str(Path(d)), [])]
        for p in erg:  # technischer Bericht nur ins Log
            log.info("Prüfung %s: %s", e.nummer, p.zeile(), extra=NUR_DATEI)
            for t in p.fehler + p.warnungen:
                log.info("    %s", t, extra=NUR_DATEI)
            if not p.gueltig and p.bericht:
                log.debug("    Bericht %s:\n%s", p.werkzeug, p.bericht[:20000], extra=NUR_DATEI)
        technisch = [p for p in erg if p.technisch]
        schlecht = [p for p in erg if not p.gueltig and not p.technisch]
        if schlecht:
            e.pruefung = "ungültig"
            e.status = "fehler"
            e.hinweise.append(
                "FEHLER: Die erzeugte E-Rechnung hat die lokale Prüfung nicht bestanden und wurde "
                "nicht in den Ausgang gelegt."
            )
            genannt: set[str] = set()
            for p in sorted(
                schlecht, key=lambda p: p.werkzeug != "KoSIT"
            ):  # KoSIT zuerst (Regelwerk-Texte)
                e.hinweise += validierung.gruende(p, schon=genannt)
            e.hinweise.append(
                "Was tun: Angaben in der Quelle (CSV/Druck) bzw. in Profil und Einstellungen "
                "korrigieren und die Datei erneut in den Eingang legen. Technische Details: Logdatei."
            )
            e.dateien = [_verschieben(d, k.fehler) for d in e.dateien if Path(d).exists()]
            ungueltig.append(e)
        elif technisch or not erg:
            e.pruefung = "nicht geprüft"
            e.hinweise.append(
                "WARNUNG: Lokale Prüfung konnte nicht laufen – "
                + (
                    "; ".join(g for p in technisch for g in validierung.gruende(p))
                    or "kein Ergebnis"
                )
            )
        else:
            e.pruefung = "gültig"
            e.hinweise.append(f"INFO: Lokal geprüft: gültig ({validierung.werkzeug_versionen()})")
    return ungueltig


def _pdfs_ohne_haken(
    paare: list[tuple[Rechnung, list[str]]], pdfs: list[Path], datei_fehler: dict[str, str]
) -> None:
    """PDF neben CSV/XML, Haken aus: nicht als Sichtteil, nicht als eigene Nur-PDF-Rechnung.
    Gleicher Dateiname wie eine Datendatei → Quelle der Rechnung (mit nach Erledigt);
    sonst klarer Fehler, Datei nach Fehler."""
    belegt: set[Path] = set()
    for _r, quellen in paare:
        staemme = {Path(q).stem.lower() for q in quellen}
        for pdf in pdfs:
            if pdf in belegt:
                continue
            if pdf.stem.lower() in staemme:
                quellen.append(str(pdf))
                belegt.add(pdf)
    for pdf in pdfs:
        if pdf not in belegt:
            datei_fehler[str(pdf)] = (
                "PDF wird im aktuellen Eingangsformat nicht verwendet "
                "(„Zusätzlich das PDF der Rechnung verwenden“ ist ausgeschaltet)."
            )


def verarbeiten(
    dateien: list[Path], k: Konfig, *, verschieben: bool = True, fortschritt=None
) -> Lauf:
    """``fortschritt``: optionaler Rückruf mit einem ``Stand`` je Schritt (aus dem Arbeitsthread).

    Ab 0.9.6 entstehen die Ausgaben im System-Temp, werden dort geprüft und erst danach einzeln und atomar in
    den Ausgang gelegt; jede abgelegte Rechnung kommt sofort ins Protokoll."""
    lauf = Lauf()
    lauf.meldungen += protokoll.vorbereiten(k)
    try:
        return _verarbeiten(lauf, dateien, k, verschieben=verschieben, fortschritt=fortschritt)
    finally:
        for e in lauf.ergebnisse:
            if e.entwurf is not None:
                e.entwurf.verwerfen()
                e.entwurf = None


def _verarbeiten(lauf: Lauf, dateien: list[Path], k: Konfig, *, verschieben: bool, fortschritt) -> Lauf:
    eingelesen = []
    melden = _Melder(fortschritt)
    sortiert = sorted(dateien)
    n_dat = len(sortiert)
    if fortschritt is not None:
        art_quellen = [str(d) for d in sortiert]
        if k.ist_daten() and not k.pdf_als_gegenstueck():
            art_quellen = [q for q in art_quellen if Path(q).suffix.lower() != ".pdf"]
        melden.eingabe = eingabe_art(art_quellen)
    ungenutzt_pdfs: list[Path] = []
    for i, d in enumerate(sortiert):
        melden(0, i + 1, n_dat, i / max(n_dat, 1), datei=d.name, zaehlt="datei")
        if d.suffix.lower() == ".pdf" and k.ist_daten() and not k.pdf_als_gegenstueck():
            ungenutzt_pdfs.append(d)
            continue
        try:
            art, liste = einlesen(d, k)
            if not liste:
                raise ValueError("Keine Rechnung in der Datei gefunden")
            eingelesen.append((d, art, liste))
        except Exception as e:  # noqa: BLE001 – jede Datei soll einzeln scheitern dürfen
            if isinstance(e, (ValueError, adapter_csv.ProfilFehler)):
                lauf.datei_fehler[str(d)] = str(e)
            else:
                log.exception("Einlesen fehlgeschlagen: %s", d)
                lauf.datei_fehler[str(d)] = f"{type(e).__name__}: {e}"
            melden(
                0,
                i + 1,
                n_dat,
                (i + 1) / max(n_dat, 1),
                datei=d.name,
                zaehlt="datei",
                fehler=d.name if str(d) in lauf.datei_fehler else "",
            )

    melden(1, 0, 0, 0.0)
    bad_files: set[str] = set(lauf.datei_fehler)
    pruef_files: set[str] = set()
    zu_pruefen: list[Rechnung] = []
    paare = paaren(eingelesen, k, lauf.datei_fehler, lauf.anlernen, lauf.schon_erzeugt)
    ctx = pflicht_kontext(k, [r.nummer for r, _q in paare])
    _pdfs_ohne_haken(paare, ungenutzt_pdfs, lauf.datei_fehler)
    bad_files.update(lauf.datei_fehler)
    n_r = len(paare)
    vergeben: set[str] = set()  # Ausgabenamen dieses Laufs (Ausgaben liegen bis nach der Prüfung im Temp)
    for r, _q in paare:  # „Logs anonymisieren“: diese Angaben auch wörtlich maskieren
        logdatei.ANONYM.merken(
            r.kaeufer.name,
            r.kaeufer.anschrift.strasse,
            r.kaeufer.anschrift.ort,
            r.kaeufer.anschrift.zusatz,
            r.verkaeufer.name,
            r.verkaeufer.anschrift.strasse,
        )
    if fortschritt is not None and paare:
        melden.eingabe = eingabe_art([q for _r, qs in paare for q in qs])
    melden(1, 0, n_r, 1.0)
    for j, (r, quellen) in enumerate(paare):
        art = eingabe_art(quellen)
        name = Path(quellen[-1]).name if quellen else r.nummer
        melden(2, j + 1, n_r, 2 * j / max(n_r, 1), basis=2, datei=name, eingabe=art)
        pflichtpruefung.pruefen(
            r, ctx
        )  # Pflichtangaben § 14 Abs. 4 UStG / Plausibilität -> „Zu prüfen“
        erg = Ergebnis(
            nummer=r.nummer,
            status=r.status,
            quellen=quellen,
            kunde=r.kaeufer.name,
            brutto=str(r.summen.brutto) if r.summen.brutto else "",
        )
        namen = ausgabe_namen_oder_hinweis(r, k) if erg.status == "ok" else None
        if namen is None:
            erg.status = r.status
        elif (k.ausgang / namen[0]).exists() or namen[0] in vergeben:  # auch im selben Lauf vergeben
            r.hinweis(
                "pruefen",
                f"Ausgabe {namen[0]} existiert bereits – Rechnung wurde schon erzeugt?",
                "BT-1",
            )
            erg.status = r.status
        if erg.status == "ok":
            vergeben.add(namen[0])
            try:
                if fortschritt is None:
                    erg.entwurf = entwurf_erzeugen(r, k)
                else:
                    erg.entwurf = entwurf_erzeugen(
                        r,
                        k,
                        bei_pdfa=lambda j=j, name=name, art=art: melden(
                            3,
                            j + 1,
                            n_r,
                            (2 * j + 1) / max(n_r, 1),
                            basis=2,
                            datei=name,
                            eingabe=art,
                        ),
                    )
                erg.dateien = erg.entwurf.dateien
            except Exception as e:  # noqa: BLE001
                log.exception("Erzeugen fehlgeschlagen: %s", r.nummer)
                r.hinweis("fehler", f"Erzeugen fehlgeschlagen: {type(e).__name__}: {e}")
                erg.status = "fehler"
        erg.hinweise = _hinweise(r)
        if erg.status == "pruefen":
            pruef_files.update(quellen)
            zu_pruefen.append(r)
            erg.dateien = [k.pruefen / f"{sicherer_name(r.nummer)}.json"]
        if erg.status == "fehler":
            bad_files.update(quellen)
        lauf.ergebnisse.append(erg)
        melden(
            3,
            j + 1,
            n_r,
            2 * (j + 1) / max(n_r, 1),
            basis=2,
            datei=name,
            eingabe=art,
            fehler=name if erg.status == "fehler" else "",
        )

    if k.nachpruefen:  # lokale Prüfung aller neuen Ausgaben in einem Stapel
        fertig = [e for e in lauf.ergebnisse if e.status == "ok" and e.dateien]
        einzeln = len(fertig) == 1 and n_r == 1
        nr_p = 1 if einzeln else 0
        datei_p = fertig[0].dateien[0].name if einzeln and fertig[0].dateien else ""

        def pruef_melden(werkzeug: str) -> None:
            melden(
                4,
                nr_p,
                n_r,
                0.0 if werkzeug == "veraPDF" else 0.5,
                datei=datei_p,
                werkzeug=werkzeug,
            )

        for e in nachpruefen(
            fertig, k, bei_werkzeug=pruef_melden if fortschritt is not None else None
        ):
            bad_files.update(e.quellen)
            melden(
                4, nr_p, n_r, 1.0, datei=datei_p, werkzeug="KoSIT", fehler=Path(e.quellen[0]).name
            )

    # Geprüfte (bzw. ungeprüfte, wenn Prüfung aus/Werkzeuge fehlen) Ausgaben in den Ausgang, je sofort ins Protokoll
    protokolliert: set[int] = set()
    for e in lauf.ergebnisse:
        if e.entwurf is None:
            continue
        if e.status == "ok":
            try:
                e.dateien = ablegen(e.entwurf, k)
            except Exception as ex:  # noqa: BLE001 – eine Rechnung darf einzeln scheitern
                log.exception("Ablegen im Ausgang fehlgeschlagen: %s", e.nummer)
                e.status = "fehler"
                e.dateien = []
                grund = ex.kurz() if isinstance(ex, dateien_mod.DateiNichtSchreibbar) else ex
                e.hinweise.append(f"FEHLER: Ablegen im Ausgang fehlgeschlagen: {grund}")
                bad_files.update(e.quellen)
            else:
                _protokoll(Lauf(ergebnisse=[e]), k, lauf)
                protokolliert.add(id(e))
        e.entwurf.verwerfen()
        e.entwurf = None

    # Fehlerberichte + Eingangsdateien wegräumen
    for e in lauf.ergebnisse:
        if e.status == "fehler":
            k.fehler.mkdir(parents=True, exist_ok=True)
            (k.fehler / f"{sicherer_name(e.nummer)}_fehler.txt").write_text(
                f"Rechnung {e.nummer}\nQuellen: {', '.join(e.quellen)}\n\n"
                + "\n".join(e.hinweise)
                + "\n",
                encoding="utf-8",
            )
    for d, grund in lauf.datei_fehler.items():
        k.fehler.mkdir(parents=True, exist_ok=True)
        (k.fehler / f"{Path(d).name}_fehler.txt").write_text(
            f"{Path(d).name}\n{grund}\n", encoding="utf-8"
        )
    verschoben: dict[str, str] = {}
    melden(5, 0, n_r, 0.0)
    if verschieben:
        for i, d in enumerate(dateien):
            melden(5, 0, n_r, i / max(len(dateien), 1), datei=d.name)
            if d.exists():
                ordner = (
                    k.fehler
                    if str(d) in bad_files
                    else k.pruefen
                    if str(d) in pruef_files
                    else k.anlernen
                    if str(d) in lauf.anlernen
                    else k.erledigt
                )  # schon erzeugt: Erledigt
                verschoben[str(d)] = str(_verschieben(d, ordner))
    # Prüffälle als JSON (für die Prüfansicht in Phase 2); Pfade zeigen auf den neuen Ort
    for r in zu_pruefen:
        k.pruefen.mkdir(parents=True, exist_ok=True)
        if r.sicht_pdf:
            r.sicht_pdf = (verschoben.get(r.sicht_pdf[0], r.sicht_pdf[0]), r.sicht_pdf[1])
        r.quelle = verschoben.get(r.quelle, r.quelle)
        d = dataclasses.asdict(r)
        d["status"] = r.status
        (k.pruefen / f"{sicherer_name(r.nummer)}.json").write_text(
            json.dumps(d, default=_json_default, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    rest = Lauf(
        ergebnisse=[e for e in lauf.ergebnisse if id(e) not in protokolliert],
        datei_fehler=lauf.datei_fehler,
        schon_erzeugt=lauf.schon_erzeugt,
    )
    _protokoll(rest, k, lauf)
    _log_details(lauf, verschoben)
    melden(5, 0, n_r, 1.0)
    return lauf


def _log_details(lauf: Lauf, verschoben: dict[str, str]) -> None:
    """Alles Technische ausführlich ins Log (Oberfläche zeigt nur Zähler und Aufgaben)."""
    for e in lauf.ergebnisse:
        log.info(
            "Rechnung %s: %s · Quellen: %s%s",
            e.nummer,
            e.status,
            ", ".join(Path(q).name for q in e.quellen),
            f" · Kunde: {e.kunde}" if e.kunde else "",
            extra=NUR_DATEI,
        )
        for h in e.hinweise:
            (log.debug if h.startswith("INFO") else log.info)("  %s", h, extra=NUR_DATEI)
        for d in e.dateien:
            log.info("  Ausgabe: %s", d, extra=NUR_DATEI)
    for d, nr in lauf.schon_erzeugt.items():
        log.info("Druck %s: %s", Path(d).name, SCHON_ERZEUGT.format(nr=nr), extra=NUR_DATEI)
    for d, grund in lauf.anlernen.items():
        log.info("Zum Anlernen: %s (%s)", Path(d).name, grund, extra=NUR_DATEI)
    for d, grund in lauf.datei_fehler.items():
        log.warning("Datei %s nicht verarbeitet: %s", Path(d).name, grund, extra=NUR_DATEI)
    for von, nach in verschoben.items():
        log.info("Verschoben: %s -> %s", von, nach, extra=NUR_DATEI)


def _tsv(s: str) -> str:
    return str(s).replace("\t", " ").replace("\n", " ")


def _protokoll(lauf: Lauf, k: Konfig, ziel_lauf: Lauf | None = None) -> None:
    """protokoll.tsv (ab 0.9.6 im Ordner „Protokoll“): Zeit, Status, Nummer, Dateien, Hinweise, Kunde,
    Brutto (ab v0.2), Prüfung (ab v0.4). Meldungen eines Ersatzwegs gehen an ``ziel_lauf`` (sonst ``lauf``)."""
    zeilen = []
    jetzt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for e in lauf.ergebnisse:
        hinw = " | ".join(h for h in e.hinweise if not h.startswith("INFO"))
        zeilen.append(
            "\t".join(
                _tsv(x)
                for x in (
                    jetzt,
                    e.status,
                    e.nummer,
                    ", ".join(p.name for p in e.dateien),
                    hinw,
                    e.kunde,
                    e.brutto,
                    e.pruefung,
                )
            )
        )
    for d, nr in lauf.schon_erzeugt.items():
        zeilen.append(
            "\t".join(
                _tsv(x)
                for x in (
                    jetzt,
                    "erledigt",
                    nr,
                    Path(d).name,
                    SCHON_ERZEUGT.format(nr=nr),
                    "",
                    "",
                    "",
                )
            )
        )
    for d, grund in lauf.datei_fehler.items():
        zeilen.append(
            "\t".join(_tsv(x) for x in (jetzt, "fehler", Path(d).name, "", grund, "", "", ""))
        )
    meldung = protokoll.schreiben(k, zeilen)
    if meldung is not None:
        ziel = ziel_lauf if ziel_lauf is not None else lauf
        if meldung not in ziel.meldungen:
            ziel.meldungen.append(meldung)


# ---------------------------------------------------------------- Prüffälle (Oberfläche)
def _prueffall_quellen(d: dict) -> list[Path]:
    q = [Path(d["quelle"])] if d.get("quelle") else []
    if d.get("sicht_pdf"):
        q.append(Path(d["sicht_pdf"][0]))
    return list(dict.fromkeys(q))


def _von_anderen_genutzt(datei: Path, json_pfad: Path, k: Konfig) -> bool:
    for andere in k.pruefen.glob("*.json"):
        if andere == json_pfad:
            continue
        try:
            if datei in _prueffall_quellen(json.loads(andere.read_text(encoding="utf-8"))):
                return True
        except (OSError, ValueError):
            continue
    return False


def prueffall_freigeben(json_pfad: Path, k: Konfig) -> Ergebnis:
    """„Neues Sichtbild + erstellen“: Die Datenquelle (CSV) gilt, der Druck wird ignoriert und das Sichtbild
    neu gesetzt. Ergebnis.status != "ok" -> nichts erzeugt, Prüffall bleibt liegen (Hinweise erklären warum)."""
    d = json.loads(Path(json_pfad).read_text(encoding="utf-8"))
    nr, quelle = d.get("nummer", ""), Path(d.get("quelle", ""))
    erg = Ergebnis(nummer=nr, status="fehler", quellen=[str(p) for p in _prueffall_quellen(d)])
    try:
        _, liste = einlesen(quelle, k)
    except (OSError, ValueError, adapter_csv.ProfilFehler) as e:
        erg.hinweise = [f"FEHLER: Quelle {quelle.name} nicht lesbar: {e}"]
        return erg
    r = next((x for x in liste if x.nummer == nr), None)
    if r is None:
        erg.hinweise = [f"FEHLER: Rechnung {nr} nicht mehr in {quelle.name} gefunden"]
        return erg
    rechnen.berechnen(r)
    pflichtpruefung.pruefen(r, pflicht_kontext(k))
    r.sicht_pdf = None
    r.hinweis("info", "Freigegeben in der Prüfansicht: Daten aus der Quelle, Sichtbild neu gesetzt")
    erg.kunde, erg.brutto = r.kaeufer.name, str(r.summen.brutto)
    namen = ausgabe_namen_oder_hinweis(r, k)
    if namen and (k.ausgang / namen[0]).exists():
        r.hinweis("pruefen", f"Ausgabe {namen[0]} existiert bereits", "BT-1")
    erg.status = r.status
    if erg.status == "ok":
        ent = entwurf_erzeugen(r, k)
        erg.dateien = ent.dateien
        erg.hinweise = _hinweise(r)
        try:
            ungueltig = k.nachpruefen and nachpruefen([erg], k)
            if not ungueltig:
                erg.dateien = ablegen(ent, k)
        finally:
            ent.verwerfen()
        if ungueltig:  # ungültig: Prüffall bleibt, Bericht im Fehlerordner
            k.fehler.mkdir(parents=True, exist_ok=True)
            (k.fehler / f"{sicherer_name(nr)}_fehler.txt").write_text(
                f"Rechnung {nr}\nQuellen: {', '.join(erg.quellen)}\n\n"
                + "\n".join(erg.hinweise)
                + "\n",
                encoding="utf-8",
            )
            return erg
        for q in _prueffall_quellen(d):
            if q.exists() and not _von_anderen_genutzt(q, Path(json_pfad), k):
                _verschieben(q, k.erledigt)
        Path(json_pfad).unlink(missing_ok=True)
    pruef_hinweise = [h for h in erg.hinweise if h not in _hinweise(r)]
    erg.hinweise = _hinweise(r) + pruef_hinweise
    if erg.status == "ok":
        _protokoll(Lauf(ergebnisse=[erg]), k)
    return erg


def prueffall_verwerfen(json_pfad: Path, k: Konfig) -> list[tuple[Path, Path]]:
    """Prüffall samt (nicht anderweitig benötigter) Quelldateien nach „Fehler“. -> Liste (von, nach) für Rückgängig."""
    json_pfad = Path(json_pfad)
    d = json.loads(json_pfad.read_text(encoding="utf-8"))
    wege = []
    for q in _prueffall_quellen(d):
        if q.exists() and not _von_anderen_genutzt(q, json_pfad, k):
            wege.append((q, _verschieben(q, k.fehler)))
    wege.append((json_pfad, _verschieben(json_pfad, k.fehler)))
    bericht = k.fehler / f"{sicherer_name(d.get('nummer', json_pfad.stem))}_fehler.txt"
    if not bericht.exists():
        bericht.write_text(
            f"Rechnung {d.get('nummer', '')} – in der Prüfansicht verworfen\n"
            f"Quellen: {', '.join(str(n) for _, n in wege)}\n",
            encoding="utf-8",
        )
        wege.append((None, bericht))
    return wege


def rueckgaengig(wege: list[tuple[Path | None, Path]]) -> None:
    for von, nach in reversed(wege):
        if von is None:  # vom Verwerfen angelegter Bericht
            Path(nach).unlink(missing_ok=True)
        elif Path(nach).exists() and not Path(von).exists():
            Path(von).parent.mkdir(parents=True, exist_ok=True)
            dateien.verschieben(Path(nach), Path(von))
