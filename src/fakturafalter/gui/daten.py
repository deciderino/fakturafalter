# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Lesen, was die Pipeline hinterlässt (Protokoll, Prüffälle, Fehlerberichte) – ohne Qt, damit testbar."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .. import protokoll as protokoll_mod
from ..konfig import Konfig, kundenstamm_fuer, partei_aus
from ..pipeline import ausgabe_namen
from ..ueberwachung import relevant


@dataclass
class Eintrag:
    zeit: datetime | None
    status: str
    nummer: str
    dateien: list[str]
    hinweise: list[str]
    kunde: str = ""
    brutto: str = ""
    pruefung: str = ""  # gültig | ungültig | nicht geprüft | "" (ab v0.4)


@dataclass
class Prueffall:
    pfad: Path
    nummer: str
    kunde: str
    brutto: str
    zeit: datetime
    abweichungen: list[tuple[str, str, str]] = field(default_factory=list)  # (Feld, CSV, Druck)
    sonstige: list[str] = field(default_factory=list)
    quellen: list[Path] = field(default_factory=list)
    profil: str = ""
    kennung: str = ""
    kontrolle_offen: list[str] = field(default_factory=list)


@dataclass
class Fehlerbericht:
    pfad: Path
    titel: str
    text: str
    zeit: datetime


def protokoll(k: Konfig, anzahl: int | None = None) -> list[Eintrag]:
    """Neueste zuerst."""
    aus = []
    for z in protokoll_mod.zeilen(k):  # ab 0.9.6: Ordner „Protokoll“ (+ Nachträge)
        t = z.split("\t")
        if len(t) < 3:
            continue
        t += [""] * (8 - len(t))
        try:
            zeit = datetime.strptime(t[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            zeit = None
        aus.append(
            Eintrag(
                zeit,
                t[1],
                t[2],
                [x for x in t[3].split(", ") if x],
                [x for x in t[4].split(" | ") if x],
                t[5],
                t[6],
                t[7],
            )
        )
    aus.sort(key=lambda e: e.zeit or datetime.min)  # Nachträge an die richtige Stelle
    aus.reverse()
    return aus[:anzahl] if anzahl else aus


def heute_erstellt(k: Konfig, heute: date | None = None) -> int:
    heute = heute or date.today()
    return sum(1 for e in protokoll(k) if e.status == "ok" and e.zeit and e.zeit.date() == heute)


_ABW = re.compile(r"CSV und Druck weichen ab: (?P<feld>.+?) (?P<a>\S+) ≠ (?P<b>\S+)$")


_VORLAGE_QUELLE = re.compile(r"pdf-angelernt:(.+)-([0-9a-f]{8})(?:\s|$)")
_VORLAGE_TEXT = re.compile(r"Vorlage (.+)-([0-9a-f]{8})\b")


def vorlage_aus_prueffall(d: dict, k: Konfig) -> tuple[str, str, list[str]]:
    """Profilname, Kennung und aktuell offene Selbstkontrolle der verwendeten Vorlage."""
    from .. import pdferkennung

    name = str(d.get("profil") or "")
    kennung = ""
    herkunft = d.get("herkunft") or {}
    if isinstance(herkunft, dict):
        for h in herkunft.values():
            q = (h or {}).get("quelle") if isinstance(h, dict) else ""
            m = _VORLAGE_QUELLE.search(q or "")
            if m:
                name, kennung = m.group(1), m.group(2)
                break
    if not kennung:
        for h in d.get("hinweise") or []:
            txt = h.get("text") if isinstance(h, dict) else str(h)
            m = _VORLAGE_TEXT.search(txt or "")
            if m:
                name, kennung = m.group(1), m.group(2)
                break
    if not name or not kennung:
        return name, kennung, []
    prof = next((p for p in k.profile if pdferkennung.profil_name(p) == name), None)
    if not prof:
        return name, kennung, []
    for v in pdferkennung.vorlagen_laden(prof):
        if v.get("kennung") == kennung:
            return name, kennung, list(pdferkennung.kontrolle_offen(v))
    return name, kennung, []


def prueffaelle(k: Konfig) -> list[Prueffall]:
    if not k.pruefen.exists():
        return []
    aus = []
    for j in sorted(k.pruefen.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        f = Prueffall(
            pfad=j,
            nummer=d.get("nummer", j.stem),
            kunde=(d.get("kaeufer") or {}).get("name", ""),
            brutto=str((d.get("summen") or {}).get("brutto", "")),
            zeit=datetime.fromtimestamp(j.stat().st_mtime),
        )
        for h in d.get("hinweise", []):
            if h.get("stufe") not in ("pruefen", "fehler", "warnung"):
                continue
            m = _ABW.match(h.get("text", ""))
            if m:
                f.abweichungen.append((m["feld"], m["a"], m["b"]))
            else:
                f.sonstige.append(h.get("text", ""))
        if d.get("quelle"):
            f.quellen.append(Path(d["quelle"]))
        if d.get("sicht_pdf"):
            f.quellen.append(Path(d["sicht_pdf"][0]))
        f.quellen = list(dict.fromkeys(f.quellen))
        f.profil, f.kennung, f.kontrolle_offen = vorlage_aus_prueffall(d, k)
        aus.append(f)
    return aus


def fehlerberichte(k: Konfig) -> list[Fehlerbericht]:
    if not k.fehler.exists():
        return []
    aus = []
    for p in sorted(k.fehler.glob("*_fehler.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        text = p.read_text(encoding="utf-8", errors="replace")
        aus.append(
            Fehlerbericht(
                p,
                (text.splitlines() or [p.stem])[0],
                text,
                datetime.fromtimestamp(p.stat().st_mtime),
            )
        )
    return aus


def wartend(k: Konfig) -> int:
    return sum(1 for p in k.eingang.iterdir() if relevant(p)) if k.eingang.exists() else 0


def ausgabe_pdf(k: Konfig, nummer: str) -> Path | None:
    """Erzeugte PDF zu einer Nummer: laut Protokoll (eigenes Dateinamen-Muster), sonst der Standardname."""
    for e in protokoll(k):
        if e.status == "ok" and e.nummer == nummer:
            for d in e.dateien:
                if d.lower().endswith(".pdf") and (k.ausgang / d).exists():
                    return k.ausgang / d
    p = k.ausgang / ausgabe_namen(nummer)[0]
    return p if p.exists() else None


def kundenstamm_info(k: Konfig) -> list[tuple[Path, int, int]]:
    """-> [(Datei, Kunden, davon ohne elektronische Adresse BT-49)] je Kundenstamm aus Profilen/Vorlagen."""
    gesehen: dict[Path, tuple[Path, int, int]] = {}
    for prof in [*k.csv_profile, *k.pdf_vorlagen]:
        dfn = prof.get("kundenstamm")
        if not dfn or not dfn.get("datei"):
            continue
        p = Path(dfn["datei"])
        p = (p if p.is_absolute() else Path(prof["_basis"]) / p).resolve()
        if p in gesehen:
            continue
        ks = kundenstamm_fuer(dfn, Path(prof["_basis"]))
        ohne = sum(1 for r in ks.daten.values() if not r.get("elektr_adresse_bt49"))
        gesehen[p] = (p, len(ks.daten), ohne)
    return list(gesehen.values())


def profilname(prof: dict) -> str:
    name = (
        prof.get("profil")
        or prof.get("vorlage")
        or prof.get("name")
        or Path(prof.get("_datei", "?")).stem
    )
    return f"{name} – {prof['beschreibung']}" if prof.get("beschreibung") else str(name)


def betrag(text: str, sprache: str = "de", waehrung: str = "€") -> str:
    try:
        d = Decimal(str(text).replace(",", "."))
    except (InvalidOperation, ValueError):
        return str(text or "")
    s = f"{d:,.2f}"
    if sprache == "de":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {waehrung}"
    return f"{waehrung}{s}" if waehrung == "€" else f"{s} {waehrung}"


def absender_fehlt(k: Konfig) -> list[str]:
    """Pflichtangaben des Absenders, die noch leer sind (Feldnamen deutsch, Übersetzung in der UI).

    Bringen alle CSV-Profile einen eigenen Block ``verkaeufer`` mit, gilt der (mit der Konfiguration
    gemischte) Verkäufer des Profils – dann darf ``absender`` in der Konfiguration leer sein.
    „Nur PDF“: jede Vorlage bringt ihren Absender mit (Assistent, Schritt 1) – nichts Pflicht.
    „XML“: der Verkäufer steht in der XML (Absender nur Rückfall) – nichts Pflicht."""
    if k.modus == "nur_pdf" or k.ist_xml():
        return []
    if k.csv_profile and all(prof.get("verkaeufer") for prof in k.csv_profile):
        for prof in k.csv_profile:
            fehlt = _partei_fehlt(partei_aus(prof["verkaeufer"], k.absender))
            if fehlt:
                return fehlt
        return []
    return _partei_fehlt(k.absender)


def _partei_fehlt(a) -> list[str]:
    fehlt = []
    if not a.name:
        fehlt.append("Firma")
    if not (a.anschrift.strasse and a.anschrift.plz and a.anschrift.ort):
        fehlt.append("Anschrift")
    if not (a.ust_id or a.steuernummer):
        fehlt.append("USt-IdNr.")
    return fehlt
