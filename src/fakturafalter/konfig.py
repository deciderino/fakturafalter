# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Konfiguration (Absender, Ordner, Profile) laden."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import zahlungsziel
from .modell import Anschrift, Partei, Zahlung
from .werte import bloecke_bereinigen

log = logging.getLogger("fakturafalter")


def lade_datei(pfad: Path) -> dict:
    text = Path(pfad).read_text(encoding="utf-8")
    if Path(pfad).suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text) or {}


ZAHLUNGSBEDINGUNG = "Zahlbar innerhalb {zahlungsziel_tage} Tagen ohne Abzug."


def partei_aus(a: dict, basis: Partei | None = None) -> Partei:
    """Block ``absender`` (Konfiguration) bzw. ``verkaeufer`` (Profil) -> Partei.

    Mit ``basis`` gilt: Nur die im Block genannten Schlüssel überschreiben ``basis``; alles andere bleibt."""
    b = basis or Partei()
    adr = a.get("anschrift") or {}
    kon = a.get("kontakt") or {}

    def w(d: dict, schl: str, alt: str) -> str:
        return str(d[schl]) if d.get(schl) is not None else alt

    return Partei(
        name=w(a, "name", b.name),
        anschrift=Anschrift(
            w(adr, "strasse", b.anschrift.strasse),
            w(adr, "plz", b.anschrift.plz),
            w(adr, "ort", b.anschrift.ort),
            w(adr, "land", b.anschrift.land or "DE"),
            w(adr, "zusatz", b.anschrift.zusatz),
        ),
        ust_id=w(a, "ust_id", b.ust_id),
        steuernummer=w(a, "steuernummer", b.steuernummer),
        elektronische_adresse=w(a, "elektronische_adresse", b.elektronische_adresse),
        kontakt_name=w(kon, "name", b.kontakt_name),
        kontakt_telefon=w(kon, "telefon", b.kontakt_telefon),
        kontakt_email=w(kon, "email", b.kontakt_email),
        register=w(a, "register", b.register),
        kennung=b.kennung,
        # ab 0.9.7: Kleinunternehmer (§ 19 UStG) – Schalter beim Absender
        kleinunternehmer=bool(a["kleinunternehmer"])
        if a.get("kleinunternehmer") is not None
        else b.kleinunternehmer,
        kleinunternehmer_text=w(a, "kleinunternehmer_text", b.kleinunternehmer_text),
    )


def zahlung_aus(z: dict, basis: Zahlung | None = None, kontoinhaber: str = "") -> Zahlung:
    """Block ``zahlung`` (Konfiguration oder Profil) -> Zahlung; mit ``basis`` nur genannte Schlüssel überschreiben."""
    b = basis or Zahlung(
        art="58", kontoinhaber=kontoinhaber, bedingungen=ZAHLUNGSBEDINGUNG, ziel_tage=14
    )
    skonto = _skonto_aus_zahlung(z, b)
    return Zahlung(
        art=str(z.get("art", b.art)),
        iban=str(z.get("iban", b.iban) or "").replace(" ", ""),
        bic=str(z.get("bic", b.bic) or ""),
        kontoinhaber=str(z.get("kontoinhaber", b.kontoinhaber) or ""),
        bedingungen=str(z.get("bedingungen", b.bedingungen) or ""),
        ziel_tage=z.get("ziel_tage", b.ziel_tage),
        skonto=skonto,
        glaeubiger_id=str(z.get("glaeubiger_id", b.glaeubiger_id) or "")
        .replace(" ", "")
        .upper(),  # BT-90
    )


def _skonto_aus_zahlung(z: dict, basis: Zahlung) -> list:
    """Optionale Profil-Standard-Skontostufen (Satz und Tage je Stufe)."""
    profil = list(basis.skonto or [])
    schluessel = (
        "skonto_satz",
        "skonto_tage",
        "skonto_basisbetrag",
        "skonto_satz_2",
        "skonto_tage_2",
        "skonto_basisbetrag_2",
    )
    if not any(z.get(k) not in (None, "") for k in schluessel):
        return profil
    stufen = []
    paare = (
        ("skonto_satz", "skonto_tage", "skonto_basisbetrag", 0),
        ("skonto_satz_2", "skonto_tage_2", "skonto_basisbetrag_2", 1),
    )
    for satz_k, tage_k, basis_k, i in paare:
        satz = (
            z[satz_k]
            if z.get(satz_k) not in (None, "")
            else (profil[i].satz if i < len(profil) else None)
        )
        tage = (
            z[tage_k]
            if z.get(tage_k) not in (None, "")
            else (profil[i].tage if i < len(profil) else None)
        )
        betrag = (
            z[basis_k]
            if z.get(basis_k) not in (None, "")
            else (profil[i].basisbetrag if i < len(profil) else None)
        )
        stufe = zahlungsziel.stufe_aus_werten(tage, satz, betrag)
        if stufe:
            stufen.append(stufe)
    return stufen


def bemerkungen_aus(liste: list) -> list[tuple[str, str]]:
    return [(b["text"], b.get("code", "")) for b in liste]



@dataclass
class XRechnungEintrag:
    """Ein Eintrag der einfachen XRechnung-Liste (Name und/oder Nummer, optionale Leitweg-ID)."""

    name: str = ""
    nummer: str = ""
    leitweg_id: str = ""

    def leer(self) -> bool:
        return not (self.name.strip() or self.nummer.strip() or self.leitweg_id.strip())


def _norm_vgl(s: str) -> str:
    return " ".join((s or "").strip().casefold().split())


def xrechnung_liste_aus(opt: dict) -> list[XRechnungEintrag]:
    aus: list[XRechnungEintrag] = []
    for roh in opt.get("xrechnung_liste") or []:
        if not isinstance(roh, dict):
            continue
        e = XRechnungEintrag(
            name=str(roh.get("name") or roh.get("kundenname") or "").strip(),
            nummer=str(roh.get("nummer") or roh.get("kundennummer") or "").strip(),
            leitweg_id=str(roh.get("leitweg_id") or roh.get("leitweg_id_bt10") or "").strip(),
        )
        if not e.leer():
            aus.append(e)
    return aus


def kunden_namen(r) -> list[str]:
    """Namen eines Käufers für den Listenvergleich: ganzer Name und erste Namenszeile."""
    k = getattr(r, "kaeufer", None)
    if k is None:
        return []
    return [k.name] + list(getattr(k, "name_zeilen", None) or [])[:1]


def xrechnung_treffer(
    k: "Konfig", *, name: str | list[str] = "", nummer: str = ""
) -> XRechnungEintrag | None:
    """Erster Listen-Treffer über Kundenname oder Kundennummer (Groß/Klein und Leerzeichen egal).

    ``name`` darf eine Liste sein: der ganze Name (BT-44 mit Zeile 2/3) und die erste Namenszeile –
    so trifft „Muster GmbH“ auch, wenn in der CSV zusätzlich „Einkauf“ als Zeile 2 steht."""
    if not getattr(k, "xrechnung_zusatz", False):
        return None
    namen = [name] if isinstance(name, str) else list(name or [])
    ns = {_norm_vgl(x) for x in namen if x and _norm_vgl(x)}
    nr = _norm_vgl(nummer)
    for e in k.xrechnung_liste or []:
        en, enr = _norm_vgl(e.name), _norm_vgl(e.nummer)
        if en and en in ns:
            return e
        if enr and nr and enr == nr:
            return e
    return None


@dataclass
class Konfig:

    basis: Path
    absender: Partei
    zahlung: Zahlung
    bemerkungen: list[tuple[str, str]]
    eingang: Path
    ausgang: Path
    erledigt: Path
    fehler: Path
    pruefen: Path
    csv_profile: list[dict] = field(default_factory=list)
    pdf_profile: list[dict] = field(
        default_factory=list
    )  # „Nur PDF“: Absender ohne CSV, Vorlage per Assistent
    arbeitsordner: Path | None = (
        None  # gemeinsamer Ordner mit den Standard-Unterordnern (sonst einzeln)
    )
    pdf_vorlagen: list[dict] = field(default_factory=list)
    sichtteil: str = "original"  # original | neu
    xrechnung_zusatz: bool = False  # zusätzlich XRechnung-CII, wenn die Liste trifft
    xrechnung_liste: list = field(default_factory=list)  # list[XRechnungEintrag]
    abgelehnte_profile: list = field(default_factory=list)  # [(Pfad, Meldung), ...]
    konfig_hinweise: list = field(default_factory=list)  # klare Hinweise zu geänderten Einstellungen
    stabil_sekunden: float = 2.0
    paarung_sekunden: float = 5.0
    gegenstueck_minuten: float = (
        10.0  # PDF + CSV/XML: so lange auf die Datei mit gleichem Namen warten (0 = nie)
    )
    schwelle: float = 0.9
    logs_anonym: bool = False  # Log-Ausgabe ohne Namen, Anschriften, IBAN, USt-IdNr., Beträge
    nachpruefen: bool = True  # nach Erstellung lokal prüfen (Mustang + KoSIT, im Paket enthalten)
    modus: str = "csv"  # nur_pdf | csv | xml (alt: pdf_csv / pdf_xml)
    pdf_verwenden: bool = True  # CSV/XML: Original-PDF als Sichtteil
    # ab 0.9.5: je Belegart Prüfmuster, Lückenwarnung, Dateinamen-Muster (nummernkreis.Kreis); leer = wie bisher
    nummernkreise: dict = field(default_factory=dict)
    # ab 0.9.6: eigener Ordner für protokoll.tsv (None = „Protokoll“ neben Eingang, also im Arbeitsordner)
    protokoll_ordner: Path | None = None
    xrechnung_ablage: str = "ausgang"  # ausgang (neben der PDF) | unterordner (Ausgang/XRechnung)
    updatepruefung: bool = True  # beim Start nach neuer Version fragen (einziger Netzzugriff)
    updates_vorab: bool = False  # Pre-Releases einbeziehen
    roh: dict = field(default_factory=dict)

    def pfad(self, p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (self.basis / p).resolve()

    @property
    def profile(self) -> list[dict]:
        """Alle Profile: PDF + CSV und Nur PDF."""
        return self.csv_profile + self.pdf_profile

    @property
    def anlernen(self) -> Path:
        """PDFs, die der Anlern-Assistent noch zeigen soll (Unterordner von „Pruefen“)."""
        return self.pruefen / "Anlernen"

    @property
    def protokoll(self) -> Path:
        """Ordner für protokoll.tsv (ab 0.9.6 nicht mehr im Ausgang): eingestellt oder „Protokoll“ im
        Arbeitsordner (bei einzeln gewählten Ordnern neben dem Eingang)."""
        return self.protokoll_ordner or self.eingang.parent / PROTOKOLL_ORDNER

    @property
    def xrechnung_ordner(self) -> Path:
        """Ziel der XRechnung-Zusatzdatei (neben der PDF oder im Unterordner „XRechnung“ des Ausgangs)."""
        return (
            self.ausgang / XRECHNUNG_ORDNER
            if self.xrechnung_ablage == "unterordner"
            else self.ausgang
        )

    def ordner_anlegen(self) -> None:
        for p in (
            self.eingang,
            self.ausgang,
            self.pruefen,
            self.fehler,
            self.erledigt,
            self.protokoll,
        ):
            p.mkdir(parents=True, exist_ok=True)

    def ist_csv(self) -> bool:
        return self.modus in ("csv", "pdf_csv")

    def ist_xml(self) -> bool:
        return self.modus in ("xml", "pdf_xml")

    def ist_daten(self) -> bool:
        """Eingang ist CSV oder XML (mit oder ohne optionales Gegenstück-PDF)."""
        return self.ist_csv() or self.ist_xml()

    def pdf_als_gegenstueck(self) -> bool:
        """True: CSV/XML plus Original-PDF als Sichtteil (früher Modus PDF+CSV / PDF+XML)."""
        if self.modus in ("pdf_csv", "pdf_xml"):
            return True
        return self.ist_daten() and bool(self.pdf_verwenden)


PROTOKOLL_ORDNER = "Protokoll"
XRECHNUNG_ORDNER = "XRechnung"
XRECHNUNG_ABLAGEN = ("ausgang", "unterordner", "keine")

# Ein Arbeitsordner, darin automatisch diese Unterordner (Schlüssel in der Konfiguration -> Ordnername)
UNTERORDNER = (
    ("eingang", "Eingang"),
    ("ausgang", "Ausgang"),
    ("pruefen", "Pruefen"),
    ("fehler", "Fehler"),
    ("erledigt", "Erledigt"),
)


def _abs(basis: Path, p: str | Path) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else (basis / p).resolve()


def ordner_aufloesen(d: dict, basis: Path) -> dict[str, Path]:
    """``arbeitsordner`` + Standard-Unterordner; einzelne Einträge unter ``ordner`` gehen vor (alte Dateien)."""
    arb = d.get("arbeitsordner")
    o = d.get("ordner") or {}
    out = {}
    for schl, name in UNTERORDNER:
        if o.get(schl):
            out[schl] = _abs(basis, o[schl])
        elif arb:
            out[schl] = _abs(basis, arb) / name
        else:
            out[schl] = _abs(basis, schl)
    return out


def gemeinsamer_ordner(ordner: dict[str, Path]) -> Path | None:
    """Liegen alle fünf Ordner als Standard-Unterordner in EINEM Ordner? -> dieser Ordner, sonst None."""
    eltern = {Path(ordner[s]).parent for s, _ in UNTERORDNER if s in ordner}
    if len(eltern) != 1 or len(ordner) < len(UNTERORDNER):
        return None
    if all(Path(ordner[s]).name == n for s, n in UNTERORDNER):
        return eltern.pop()
    return None


def _altlasten_bereinigen(datei: Path, roh: dict, schluessel) -> None:
    """Alte „(CID:10)“-/Steuerzeichen-Reste (Assistent bis 0.4.1) beim Laden entfernen und zurückschreiben."""
    geaendert = bloecke_bereinigen(roh, schluessel)
    if not geaendert:
        return
    log = logging.getLogger("fakturafalter")
    log.info("%s: Steuerzeichen-Reste entfernt (%s)", datei.name, ", ".join(geaendert))
    try:
        from .anlernen import _yaml_schreiben

        ab = lade_datei(datei)  # frisch lesen: nur die bereinigten Blöcke ersetzen
        for s in schluessel:
            if s in roh:
                ab[s] = roh[s]
        _yaml_schreiben(datei, ab)
    except Exception as e:  # schreibgeschützt o. Ä.: bereinigt nur im Speicher
        log.warning("%s: bereinigte Werte nicht gespeichert: %s", datei.name, e)


def csv_eintrag_datei(eintrag) -> str:
    """Pfad aus einem csv_profile-Eintrag (Zeichenkette oder {datei, aktiv})."""
    if isinstance(eintrag, dict):
        return str(eintrag.get("datei") or "")
    return str(eintrag or "")


def _profil_laden(k: "Konfig", d: dict, p) -> dict:
    rel = csv_eintrag_datei(p)
    prof = lade_datei(k.pfad(rel))
    _altlasten_bereinigen(k.pfad(rel), prof, ("verkaeufer", "zahlung"))
    prof["_basis"] = k.pfad(rel).parent
    prof["_datei"] = str(k.pfad(rel))
    if isinstance(p, dict) and "aktiv" in p:
        prof["aktiv"] = bool(p["aktiv"])
    name = str(prof.get("profil") or prof.get("name") or k.pfad(rel).stem)
    ueber = (d.get("pdf_erkennung") or {}).get(name)  # Schalter aus den Einstellungen gehen vor
    if ueber:
        prof["pdf_erkennung"] = {**(prof.get("pdf_erkennung") or {}), **ueber}
    return prof


# Alte Konfigurationswerte bleiben lesbar: pdf_csv / pdf_xml -> csv / xml plus Haken.
_MODUS_ALT = {"pdf_csv": ("csv", True), "pdf_xml": ("xml", True)}
_MODUS_NEU = frozenset({"nur_pdf", "csv", "xml"})


def modus_und_pdf(d: dict, opt: dict | None = None) -> tuple[str, bool]:
    """-> (modus, pdf_verwenden). Übersetzt pdf_csv/pdf_xml.

    Fehlender modus in einer schon vorhandenen Datei bleibt wie bisher
    pdf_csv (csv plus Haken): so lief die Verarbeitung bisher, und eine
    bestehende Installation ändert sich nicht still. Neue Setups tragen
    modus und pdf_verwenden in der Startkonfiguration ein (csv, Haken aus).
    """
    opt = opt if opt is not None else (d.get("optionen") or {})
    raw = d.get("modus")
    if raw in _MODUS_ALT:
        modus, standard = _MODUS_ALT[raw]
    elif raw in _MODUS_NEU:
        modus, standard = raw, False
    else:
        modus, standard = "csv", True
    if modus == "nur_pdf":
        return modus, False
    if "pdf_verwenden" in opt:
        return modus, bool(opt["pdf_verwenden"])
    return modus, standard


def _profile_laden(k: "Konfig", d: dict, liste, *, art: str) -> tuple[list[dict], list]:
    """Profile laden. Fehlende oder unlesbare Dateien werden weggelassen, nicht als Fehler geworfen.

    So bleibt ein gelöschtes (oder nicht mehr vorhandenes) Profil weg, und das Speichern der
    restlichen Einstellungen bzw. eines anderen Profils bricht nicht mit „No such file or directory“ ab.
    """
    geladen, behalten = [], []
    for p in liste or []:
        rel = csv_eintrag_datei(p)
        try:
            if not rel:
                raise ValueError("kein Dateiname")
            prof = _profil_laden(k, d, p)
            if art == "csv":
                from .profilformat import pruefen

                pruefen(prof, datei=rel)
        except Exception as e:
            from .profilformat import ProfilVeraltet

            if isinstance(e, ProfilVeraltet):
                log.warning("Profil %s „%s“ abgelehnt: %s", art, rel or p, e.titel())
                k.abgelehnte_profile.append((str(rel or p), e.meldung(), e.titel()))
                behalten.append(p)  # Eintrag in der Konfiguration behalten, Datei unangetastet
                continue
            if isinstance(e, (OSError, ValueError, TypeError, KeyError, yaml.YAMLError)):
                log.warning(
                    "Profil %s „%s“ nicht geladen (%s) – Eintrag wird ignoriert",
                    art,
                    rel or p,
                    e,
                )
                continue
            raise
        geladen.append(prof)
        behalten.append(p)
    return geladen, behalten


def lade_konfig(pfad: str | Path) -> Konfig:
    pfad = Path(pfad).resolve()
    d = lade_datei(pfad)
    _altlasten_bereinigen(pfad, d, ("absender", "zahlung"))
    basis = pfad.parent
    absender = partei_aus(d.get("absender") or {})
    zahlung = zahlung_aus(d.get("zahlung") or {}, kontoinhaber=absender.name)
    bem = bemerkungen_aus(d.get("bemerkungen") or [])
    o = ordner_aufloesen(d, basis)
    k = Konfig(basis=basis, absender=absender, zahlung=zahlung, bemerkungen=bem, roh=d, **o)
    k.arbeitsordner = gemeinsamer_ordner(o)
    prot = d.get("protokoll_ordner") or (d.get("ordner") or {}).get("protokoll")
    if prot:
        k.protokoll_ordner = _abs(basis, prot)
    csv_profs, csv_ein = _profile_laden(k, d, d.get("csv_profile"), art="csv")
    from . import csv_standard

    k.csv_profile = csv_standard.anhaengen(csv_profs, d)
    if list(d.get("csv_profile") or []) != csv_ein:
        d["csv_profile"] = csv_ein
    pdf_profs, pdf_ein = _profile_laden(k, d, d.get("pdf_profile"), art="pdf")
    for prof in pdf_profs:
        prof.setdefault("quelle", "pdf")
    k.pdf_profile = pdf_profs
    if list(d.get("pdf_profile") or []) != pdf_ein:
        d["pdf_profile"] = pdf_ein
    vorlagen, vorlagen_ein = [], []
    for p in d.get("pdf_vorlagen") or []:
        try:
            v = lade_datei(k.pfad(p))
        except (OSError, ValueError, TypeError, yaml.YAMLError) as e:
            log.warning(
                "PDF-Vorlage „%s“ nicht geladen (%s) – Eintrag wird ignoriert",
                p,
                e,
            )
            continue
        v["_basis"] = k.pfad(p).parent
        v["_datei"] = str(k.pfad(p))
        vorlagen.append(v)
        vorlagen_ein.append(p)
    k.pdf_vorlagen = vorlagen
    if list(d.get("pdf_vorlagen") or []) != vorlagen_ein:
        d["pdf_vorlagen"] = vorlagen_ein
    opt = d.get("optionen", {})
    k.sichtteil = opt.get("sichtteil", k.sichtteil)
    k.xrechnung_liste = xrechnung_liste_aus(opt)
    if "xrechnung_zusatz" in opt:
        k.xrechnung_zusatz = bool(opt.get("xrechnung_zusatz"))
    else:
        k.xrechnung_zusatz = bool(k.xrechnung_liste)
    ablage = str(opt.get("xrechnung_ablage") or "ausgang")
    if ablage == "keine":
        k.xrechnung_zusatz = False
    k.xrechnung_ablage = ablage if ablage in ("ausgang", "unterordner") else "ausgang"
    # Früher: XRechnung, wenn der Kundenstamm es verlangte. Jetzt gilt die Liste.
    if opt.get("xrechnung_zusatz") and not k.xrechnung_liste and ablage != "keine":
        k.konfig_hinweise.append(
            "Es gibt keinen Kundenstamm mehr. Trage in der XRechnung-Liste ein, für welche Kunden "
            "zusätzlich eine XRechnung erzeugt werden soll. Bisherige Profile werden nicht "
            "automatisch übernommen."
        )
    k.updatepruefung = bool(opt.get("updatepruefung", k.updatepruefung))
    k.updates_vorab = bool(opt.get("updates_vorab", k.updates_vorab))
    k.stabil_sekunden = float(opt.get("stabil_sekunden", k.stabil_sekunden))
    k.paarung_sekunden = float(opt.get("paarung_sekunden", k.paarung_sekunden))
    k.gegenstueck_minuten = float(opt.get("gegenstueck_minuten", k.gegenstueck_minuten))
    k.schwelle = float(opt.get("schwelle", k.schwelle))
    k.nachpruefen = bool(opt.get("nach_erstellung_pruefen", k.nachpruefen))
    k.logs_anonym = bool(opt.get("logs_anonymisieren", k.logs_anonym))
    k.modus, k.pdf_verwenden = modus_und_pdf(d, opt)
    from .nummernkreis import aus_optionen

    k.nummernkreise = aus_optionen(opt)
    return k
