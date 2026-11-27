# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Adapter CSV / Festbreite: Datei + Profil -> Rechnungen."""

from __future__ import annotations

import fnmatch
import logging
import re
from collections import OrderedDict
from pathlib import Path

from .aufbau import Roh, rechnung_bauen
from .konfig import Konfig
from .modell import Herkunft, Hinweis, Rechnung
from .tabellen import TabellenFehler, als_csv_text, ist_tabelle
from .werte import WertFehler, csv_lesen, datum, dekodieren, trennzeichen_erkennen, zahl

log = logging.getLogger("fakturafalter")


class ProfilFehler(Exception):
    pass


def datei_text(pfad: Path, profil: dict) -> tuple[str, str]:
    """Inhalt als Text -> (Text, Kodierung). Excel/ODS (ab rc2): das Blatt des Profils ab seiner Startzeile,
    Zahlen mit dem Dezimalzeichen des Profils, Datumszellen im Datumsformat des Profils, Trennzeichen „;“."""
    dat = profil.get("datei", {}) or {}
    if ist_tabelle(pfad):
        text = als_csv_text(
            Path(pfad),
            dat.get("blatt") or None,
            int(dat.get("startzeile") or 1),
            (profil.get("zahlen") or {}).get("dezimal", ","),
            (profil.get("datum") or {}).get("format", "%d.%m.%Y"),
        )
        return text, Path(pfad).suffix.lower().lstrip(".")
    return dekodieren(Path(pfad).read_bytes(), dat.get("kodierung", "auto"))


class Zweifel(WertFehler):
    """Wert lesbar, aber nicht eindeutig (z. B. „2.5“ in einem Profil mit Dezimalkomma) -> „prüfen“."""


class Pruefen(str):
    """Hinweistext der Stufe „prüfen“ (statt „fehler“) in der Fehlerliste einer Rechnung."""


def _trennzeichen_zweifel(roh: str, dezimal: str, tausender: str) -> bool:
    """Steht das „andere“ Trennzeichen im Wert, ohne dass es eine gültige Tausendergruppe bildet?
    Beispiel Profil „,“/„.“: „1.234,50“ ist eindeutig, „2.5“ nicht (2,5 oder 25?)."""
    if dezimal not in (",", "."):
        return False
    andere = "." if dezimal == "," else ","
    if andere not in roh:
        return False
    if andere != tausender:
        return True
    t, d = re.escape(tausender), re.escape(dezimal)
    return not re.fullmatch(rf"[+-]?\d{{1,3}}(?:{t}\d{{3}})+(?:{d}\d+)?-?", roh.replace(" ", ""))


def _typisieren(roh: str, d: dict, profil: dict):
    typ = d.get("typ", "text")
    zs = profil.get("zahlen", {})
    if d.get("trim", True):
        roh = roh.strip()
    if roh == "":
        return None
    if typ == "prozent":  # „10“, „10 %“, „10,5%“
        roh, typ = roh.replace("%", "").strip(), "zahl"
        if roh == "":
            return None
    if typ == "zahl":
        dez, tau = zs.get("dezimal", ","), zs.get("tausender", ".")
        implizit = int(d.get("implizite_nachkommastellen", 0))
        if not implizit and _trennzeichen_zweifel(roh, dez, tau):
            raise Zweifel(
                f"„{roh}“ passt nicht zum Dezimalzeichen „{dez}“ des Profils – Wert nicht übernommen, "
                "bitte prüfen"
            )
        return zahl(roh, dez, tau, implizit)
    if typ == "ganzzahl":
        try:
            return str(int(roh))
        except ValueError:
            raise WertFehler(f"„{roh}“ ist keine ganze Zahl") from None
    if typ == "tage":  # „10 Tage“, „10“, „10 Tagen“
        m = re.search(r"(\d{1,3})", roh)
        if not m:
            raise WertFehler(f"„{roh}“ ist keine Tagesangabe")
        return int(m.group(1))
    if typ == "datum":
        return datum(roh, d.get("format") or profil.get("datum", {}).get("format", "%d.%m.%Y"))
    return roh


def profil_passt(pfad: Path, profil: dict) -> bool:
    muster = profil.get("datei", {}).get("muster", "*.csv")
    if not fnmatch.fnmatch(pfad.name.lower(), muster.lower()):
        return False
    art = profil.get("aufbau", {}).get("art")
    if art == "feste_breite":
        return _feste_breite_passt(pfad, profil)
    if art == "bloecke":
        ok, _g = profil_passt_grund(pfad, profil)
        return ok
    # Kopfzeile muss alle benötigten Spalten enthalten
    try:
        text, _ = datei_text(pfad, profil)
    except (UnicodeDecodeError, TabellenFehler):
        return False
    trenn = profil.get("datei", {}).get("trennzeichen", "auto")
    trenn = trennzeichen_erkennen(text) if trenn in (None, "auto") else trenn
    kopf = [c.strip() for c in (csv_lesen(text.splitlines()[0] if text else "", trenn) or [[]])[0]]
    noetig = {
        d["spalte"]
        for teil in ("kopf", "position")
        for d in profil.get("felder", {}).get(teil, {}).values()
        if "spalte" in d and not d.get("optional")
    }
    return noetig.issubset(kopf)


def _feste_breite_passt(pfad: Path, profil: dict) -> bool:
    """Das Dateimuster allein (z. B. „*.txt“) passt auch auf Textdrucke. Deshalb muss die erste belegte Zeile
    ein Kopfsatz des Profils sein und jede belegte Zeile eine bekannte Satzart tragen."""
    try:
        text, _ = datei_text(pfad, profil)
    except (OSError, UnicodeDecodeError, TabellenFehler):
        return False
    aufbau = profil.get("aufbau", {})
    sa_def = aufbau.get("satzart", {"von": 1, "bis": 1})
    saetze = profil.get("saetze", {})
    zeilen = [z for z in text.replace("\f", "\n").splitlines() if z.strip()]
    if not zeilen:
        return False
    arten = [z[sa_def["von"] - 1 : sa_def["bis"]] for z in zeilen]
    return arten[0] == aufbau.get("kopf", "K") and all(a in saetze for a in arten)


def _dateikopf(pfad: Path, profil: dict) -> list[str]:
    """Erste Kopfzeile der CSV, für Hinweise zu unbekannten Spalten."""
    dat = profil.get("datei", {})
    try:
        text, _ = datei_text(pfad, profil)
    except (OSError, UnicodeDecodeError, TabellenFehler):
        return []
    trenn = dat.get("trennzeichen", "auto")
    trenn = trennzeichen_erkennen(text) if trenn in (None, "auto") else trenn
    zeilen = csv_lesen(text, trenn, dat.get("textbegrenzer", '"'))
    if not zeilen:
        return []
    return [c.strip() for c in zeilen[0]]


def lesen(pfad: Path, profil: dict, konfig: Konfig) -> list[Rechnung]:
    text, kod = datei_text(pfad, profil)
    art = profil.get("aufbau", {}).get("art", "zeile_je_position")
    if art == "feste_breite":
        gruppen = _feste_breite(text, profil, pfad)
    elif art == "bloecke":
        gruppen = _bloecke(text, profil, pfad)
    else:
        gruppen = _csv(text, profil, pfad)
    rechnungen = []
    spalten = getattr(gruppen, "spalten", None) or {}
    pos_spalten = _positionsspalten(profil)
    for nr, (kopf, pos, fehler) in gruppen.items():
        r = rechnung_bauen(kopf, pos, profil, konfig, quelle=str(pfad))
        r.spalten = {  # Platzhalter im Layout (rc2): nur Kopfwerte, keine Positionsspalten
            k: v for k, v in (spalten.get(nr) or {}).items() if k not in pos_spalten
        }
        for f in fehler:
            r.hinweis("pruefen" if isinstance(f, Pruefen) else "fehler", f)
        r.herkunft.setdefault("_kodierung", Herkunft(f"erkannt: {kod}", 1.0))
        r.profil = str(
            profil.get("profil") or profil.get("name") or Path(profil.get("_datei", "profil")).stem
        )
        rechnungen.append(r)
    from . import csv_standard

    if csv_standard.ist_standard(profil) and rechnungen:
        for r in rechnungen:
            csv_standard.hinweise_unbekannt(r, _dateikopf(pfad, profil), profil)
    return rechnungen


def _positionsspalten(profil: dict) -> set[str]:
    """Spalten, die Positionsfeldern zugeordnet sind (nicht zugleich einem Kopffeld) – keine Kopfwerte."""
    def namen(defs) -> set[str]:
        return {str(d.get("spalte")).strip() for d in (defs or {}).values() if isinstance(d, dict) and d.get("spalte")}

    felder = profil.get("felder") or {}
    pos, kopf = namen(felder.get("position")), namen(felder.get("kopf"))
    for b in profil.get("bloecke") or []:
        if not isinstance(b, dict):
            continue
        from .csv_bloecke import block_wiederholend

        if block_wiederholend(b):
            pos |= namen(b.get("felder"))
        else:
            kopf |= namen(b.get("felder"))
    return pos - kopf


def _hat_spalte_fehlt(rechnungen: list) -> bool:
    for r in rechnungen:
        for h in r.hinweise:
            t = str(h.text if hasattr(h, "text") else h)
            if "Spalte" in t and "fehlt" in t:
                return True
    return False


def _praefix_spalte_fehlt(rechnungen: list, name: str) -> None:
    for r in rechnungen:
        ersatz = []
        for h in r.hinweise:
            txt = str(h.text if hasattr(h, "text") else h)
            if "Spalte" in txt and "fehlt" in txt and f"Profil „{name}“" not in txt:
                stufe = getattr(h, "stufe", "fehler") or "fehler"
                feld = getattr(h, "feld", None)
                ersatz.append(Hinweis(stufe, f"Profil „{name}“: {txt}", feld))
            else:
                ersatz.append(h)
        r.hinweise[:] = ersatz


def lesen_mit_auswahl(pfad: Path, profile: list, konfig: Konfig) -> tuple[dict | None, list]:
    """Gleiche Erkennung und denselben Lesepfad wie der Eingang; bei „Spalte fehlt“ nächstes Profil."""
    kandidaten = passende_profile(pfad, profile)
    if not kandidaten:
        return None, []
    letzter: tuple[dict, list] | None = None
    for prof, _g, _s in kandidaten:
        rs = lesen(pfad, prof, konfig)
        letzter = (prof, rs)
        if not _hat_spalte_fehlt(rs):
            if prof is not kandidaten[0][0]:
                log.info(
                    "%s: Profil „%s“ wegen fehlender Spalten übersprungen, „%s“ verwendet",
                    pfad.name,
                    profil_name(kandidaten[0][0]),
                    profil_name(prof),
                )
            else:
                weitere = [profil_name(p) for p, _g, _s in kandidaten[1:]]
                name = profil_name(prof)
                if weitere:
                    log.info(
                        "%s: CSV-Profil „%s“ (%s); weitere passende: %s",
                        pfad.name,
                        name,
                        kandidaten[0][1],
                        ", ".join(weitere),
                    )
                else:
                    log.info("%s: CSV-Profil „%s“", pfad.name, name)
            return prof, rs
    assert letzter is not None
    prof, rs = letzter
    _praefix_spalte_fehlt(rs, profil_name(prof))
    return prof, rs


def _csv(text: str, profil: dict, pfad: Path):
    dat = profil.get("datei", {})
    trenn = dat.get("trennzeichen", "auto")
    trenn = trennzeichen_erkennen(text) if trenn in (None, "auto") else trenn
    zeilen = csv_lesen(text, trenn, dat.get("textbegrenzer", '"'))
    zeilen = zeilen[int(dat.get("zeilen_ueberspringen", 0)) :]
    if not zeilen:
        raise ProfilFehler("Datei ist leer")
    kopfzeile = [c.strip() for c in zeilen[0]]
    daten = zeilen[1:] if dat.get("kopfzeile", True) else zeilen
    start = 2 if dat.get("kopfzeile", True) else 1
    aufbau = profil.get("aufbau", {})
    felder = profil.get("felder", {})
    schl = aufbau.get("rechnung_schluessel")
    gruppen: OrderedDict = OrderedDict()
    spalten: dict[str, dict[str, str]] = {}  # Rohwerte der Kopfzeile je Rechnung (Platzhalter, rc2)

    def feldsatz(row: dict, defs: dict, zeile: int, fehler: list) -> Roh:
        roh: Roh = {}
        for feld, d in defs.items():
            h = Herkunft(f"csv:{pfad.name} Zeile {zeile} Spalte {d.get('spalte', 'fest')}", 1.0)
            if "fest" in d:
                roh[feld] = (str(d["fest"]), Herkunft("profil:fest", 1.0))
                continue
            if d.get("spalte") not in row:
                if not d.get("optional"):
                    fehler.append(f"Spalte „{d.get('spalte')}“ fehlt")
                continue
            try:
                roh[feld] = (_typisieren(row[d["spalte"]], d, profil), h)
            except Zweifel as e:
                fehler.append(Pruefen(f"Zeile {zeile}, {feld}: {e}"))
            except WertFehler as e:
                fehler.append(f"Zeile {zeile}, {feld}: {e}")
        return roh

    from . import csv_bloecke

    tz = csv_bloecke.textzeile_konfig(profil)

    for i, werte in enumerate(daten):
        zeile = start + i
        if csv_bloecke.zeile_ohne_inhalt(werte):
            continue
        row = dict(zip(kopfzeile, werte))
        key = (row.get(schl) or "").strip()
        g = gruppen.setdefault(key, [None, [], []])
        sp = spalten.setdefault(key, {})
        if aufbau.get("art") == "satzart":
            sa = (row.get(aufbau.get("satzart_spalte", "Satzart")) or "").strip()
            kenn = {
                str(k): str(v)
                for k, v in (aufbau.get("satzarten") or aufbau.get("kennwerte") or {}).items()
            }
            art_sa = kenn.get(sa)
            if art_sa is None:
                if sa == aufbau.get("kopf", "K"):
                    art_sa = "kopf"
                elif sa == aufbau.get("position", "P"):
                    art_sa = "position"
                elif sa == aufbau.get("rabatt", "R"):
                    art_sa = "rabatt"
                elif sa == aufbau.get("zuschlag", "Z"):
                    art_sa = "zuschlag"
            if art_sa == "kopf":
                _spalten_merken(sp, row)
                g[0] = feldsatz(row, felder.get("kopf", {}), zeile, g[2])
            elif art_sa == "position":
                g[1].append(feldsatz(row, felder.get("position", {}), zeile, g[2]))
            elif art_sa in ("rabatt", "zuschlag"):
                roh = feldsatz(
                    row,
                    {**felder.get("position", {}), **felder.get("zu_abschlag", {})},
                    zeile,
                    g[2],
                )
                roh["zeilenart"] = (
                    art_sa,
                    Herkunft(f"csv:{pfad.name} Zeile {zeile} Satzart {sa}", 1.0),
                )
                g[1].append(roh)
            elif art_sa in ("skip", "ignorieren", "leer"):
                pass
            else:
                g[2].append(f"Zeile {zeile}: unbekannte Satzart „{sa}“")
        else:  # zeile_je_position
            _spalten_merken(sp, row)
            k = feldsatz(row, felder.get("kopf", {}), zeile, g[2])
            if g[0] is None:
                g[0] = k
            else:
                for f in aufbau.get("kopf_muss_gleich_sein", []):
                    if row.get(f) != g[0].get("_roh_" + f, (row.get(f),))[0]:
                        g[2].append(
                            Pruefen(
                                f"Zeile {zeile}: Kopfwert „{f}“ weicht innerhalb der Rechnung ab"
                            )
                        )
            for f in aufbau.get("kopf_muss_gleich_sein", []):
                g[0].setdefault("_roh_" + f, (row.get(f), None))
            _zeile_je_position(g, feldsatz, row, felder, zeile, pfad, tz)
    from .csv_bloecke import Gruppen

    out = Gruppen()
    out.spalten = spalten
    for key, (kopf, pos, fehler) in gruppen.items():
        if kopf is None:
            kopf = {}
            fehler.append("Kopfsatz fehlt")
        davor = kopf.pop("_zeilen_davor", None) if kopf else None
        if davor and not pos:
            _verwaist_in_kopf(kopf, davor, tz, 0)
        elif davor and "_zeilen_davor" not in pos[0]:
            pos[0]["_zeilen_davor"] = list(davor)
            _verwaist_in_kopf(kopf, davor, tz, 0)
        elif davor:
            # Rest nach der letzten Position (zwischen=nachher) an diese anhängen
            from . import csv_zeilen

            for txt in davor:
                csv_zeilen.kommentar_an(pos[-1], txt, txt == "", tz, 0, pfad)
        kopf = {k: v for k, v in kopf.items() if not k.startswith("_roh_")}
        out[key] = (kopf, pos, fehler)
    return out


def _spalten_merken(sp: dict, row: dict) -> None:
    """Erster nicht leerer Wert je Spalte (Kopfwerte einer Rechnung) – für Platzhalter wie {Bestellnummer}."""
    for k, v in row.items():
        if k and v is not None and str(v).strip():
            sp.setdefault(str(k).strip(), str(v).strip())


def _zeile_je_position(g, feldsatz, row, felder, zeile, pfad, tz) -> None:
    """Standardaufbau: Position, Textzeile, gewollte Leerzeile oder überspringen."""
    from . import csv_bloecke, csv_zeilen

    pos_defs = felder.get("position", {}) if felder else {}
    kopf_defs = felder.get("kopf", {}) if felder else {}
    art = csv_zeilen.erkennen(row, pos_defs, kopf_defs, tz)
    if art and art[0] == "preis_ohne_menge":
        modus = str(tz.get("preis_ohne_menge") or "pruefen")
        if modus == "kommentar":
            art = ("text", art[1])
        else:
            art = None  # Position; „eins“ setzt die Menge später im Aufbau
            if modus == "eins":
                row = dict(row)
    if art is None:
        pos = feldsatz(row, pos_defs, zeile, g[2])
        pos["_menge_roh"] = (csv_bloecke._feld_wert(row, pos_defs, "BT-129") or "").strip()
        pos["_einheit_roh"] = (csv_bloecke._feld_wert(row, pos_defs, "BT-130") or "").strip()
        if str(tz.get("preis_ohne_menge") or "pruefen") == "eins":
            pos["_menge_eins"] = True
        davor = g[0].pop("_zeilen_davor", None) if g[0] is not None else None
        if davor:
            pos["_zeilen_davor"] = list(davor)
            _verwaist_in_kopf(g[0], davor, tz, zeile)
            if str(tz.get("verwaist") or "BT-22") == "naechste":
                for txt in davor:
                    csv_bloecke.text_an_roh(pos, txt, txt == "", tz, zeile, pfad)
        g[1].append(pos)
        return
    kind, text = art
    if kind == "skip":
        return
    leer = kind == "leer"
    zwischen = str(tz.get("zwischen") or "vorher")
    if g[1] and zwischen != "nachher":
        csv_zeilen.kommentar_an(g[1][-1], text, leer, tz, zeile, pfad)
        return
    if g[0] is None:
        g[0] = {}
    wartend = g[0].setdefault("_zeilen_davor", [])
    wartend.append("" if leer else text)
    if not g[1] and str(tz.get("verwaist") or "BT-22") == "pruefen":
        g[2].append(Pruefen(f"Textzeile vor der ersten Position (Zeile {zeile})"))


def _verwaist_in_kopf(kopf: dict, davor: list, tz: dict, zeile: int) -> None:
    """Text vor der ersten Position in die XML (Standard: BT-22). Sichtseite bleibt Vorspann."""
    from . import csv_bloecke

    if not kopf:
        return
    verw = str(tz.get("verwaist") or "BT-22")
    texte = [t for t in davor if (t or "").strip()]
    if not texte or verw != "BT-22":
        return
    alt = str((kopf.get("BT-22") or ("",))[0] or "")
    trenner = tz.get("trenner")
    trenner = "\n" if trenner is None else str(trenner)
    neu = "\n".join(texte)
    kopf["BT-22"] = (
        csv_bloecke._anhaengen(alt, neu, trenner),
        Herkunft(f"csv Textzeile vor erster Position (Zeile {zeile})", 1.0),
    )


def _feste_breite(text: str, profil: dict, pfad: Path):
    aufbau = profil["aufbau"]
    sa_def = aufbau.get("satzart", {"von": 1, "bis": 1})
    saetze = profil.get("saetze", {})
    fest = profil.get("fest", {})
    gruppen: OrderedDict = OrderedDict()
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        sa = line[sa_def["von"] - 1 : sa_def["bis"]]
        defs = saetze.get(sa)
        if defs is None:
            continue
        roh: Roh = {}
        fehler = []
        for feld, d in defs.items():
            stueck = line[d["von"] - 1 : d["bis"]]
            h = Herkunft(f"fest:{pfad.name} Zeile {i} Spalten {d['von']}-{d['bis']}", 1.0)
            try:
                v = _typisieren(stueck, d, profil)
            except Zweifel as e:
                fehler.append(Pruefen(f"Zeile {i}, {feld}: {e}"))
                continue
            except WertFehler as e:
                if not d.get("optional"):
                    fehler.append(f"Zeile {i}, {feld}: {e}")
                continue
            roh[feld] = (v, h)
        key = str(roh.get("BT-1", ("",))[0])
        g = gruppen.setdefault(key, [None, [], []])
        g[2].extend(fehler)
        if sa == aufbau.get("kopf", "K"):
            for f, v in fest.items():
                roh[f] = (str(v), Herkunft("profil:fest", 1.0))
            g[0] = roh
        else:
            if sa in (
                aufbau.get("rabatt"),
                aufbau.get("zuschlag"),
            ):  # Rabatt-/Zuschlagssatz (BG-20/21)
                roh["zeilenart"] = (
                    "rabatt" if sa == aufbau.get("rabatt") else "zuschlag",
                    Herkunft(f"fest:{pfad.name} Zeile {i} Satzart {sa}", 1.0),
                )
            g[1].append(roh)
    return OrderedDict(
        (k, (v[0] or {}, v[1], v[2] + ([] if v[0] else ["Kopfsatz fehlt"])))
        for k, v in gruppen.items()
    )


def _bloecke(text: str, profil: dict, pfad: Path):
    from . import csv_bloecke

    dat = profil.get("datei", {})
    trenn = dat.get("trennzeichen", "auto")
    trenn = trennzeichen_erkennen(text) if trenn in (None, "auto") else trenn
    zeilen = csv_lesen(text, trenn, dat.get("textbegrenzer", '"'))
    zeilen = zeilen[int(dat.get("zeilen_ueberspringen", 0)) :]
    if not zeilen:
        raise ProfilFehler("Datei ist leer")
    # Im Block-Modus ist die erste Zeile typischerweise schon eine Block-Kopfzeile
    start = 1 + int(dat.get("zeilen_ueberspringen", 0))
    return csv_bloecke.lesen(zeilen, profil, pfad, start)


def profil_passt_grund(pfad: Path, profil: dict) -> tuple[bool, str]:
    """Wie ``profil_passt``, dazu die Begründung (für „Profil testen“)."""
    muster = profil.get("datei", {}).get("muster", "*.csv")
    if not fnmatch.fnmatch(pfad.name.lower(), muster.lower()):
        return False, f"Dateiname passt nicht zum Muster „{muster}“"
    art = profil.get("aufbau", {}).get("art") or "zeile_je_position"
    if art == "bloecke":
        try:
            text, _ = datei_text(pfad, profil)
        except (OSError, UnicodeDecodeError, TabellenFehler) as e:
            return False, f"Datei nicht lesbar ({e})"
        dat = profil.get("datei", {})
        trenn = dat.get("trennzeichen", "auto")
        trenn = trennzeichen_erkennen(text) if trenn in (None, "auto") else trenn
        zeilen = csv_lesen(text, trenn, dat.get("textbegrenzer", '"'))
        zeilen = zeilen[int(dat.get("zeilen_ueberspringen", 0)) :]
        from . import csv_bloecke

        return csv_bloecke.passt(zeilen, profil)
    ok = profil_passt(pfad, profil)
    if ok:
        return True, f"Aufbau „{art}“, Pflichtspalten vorhanden"
    return False, f"Aufbau „{art}“, Pflichtspalten fehlen oder Datei passt nicht"


def profil_aktiv(profil: dict) -> bool:
    """Fehlendes „aktiv“ gilt als an (rückwärtskompatibel)."""
    if "aktiv" not in profil:
        return True
    return bool(profil.get("aktiv"))


def profil_name(profil: dict) -> str:
    return str(
        profil.get("profil") or profil.get("name") or Path(profil.get("_datei", "profil")).stem
    )


def _zeilen_fuer_profil(pfad: Path, profil: dict) -> list[list[str]]:
    dat = profil.get("datei", {})
    try:
        text, _ = datei_text(pfad, profil)
    except (OSError, UnicodeDecodeError, TabellenFehler):
        return []
    trenn = dat.get("trennzeichen", "auto")
    trenn = trennzeichen_erkennen(text) if trenn in (None, "auto") else trenn
    zeilen = csv_lesen(text, trenn, dat.get("textbegrenzer", '"'))
    return zeilen[int(dat.get("zeilen_ueberspringen", 0)) :]


def _spezifitaet(pfad: Path, profil: dict) -> int:
    if (profil.get("aufbau") or {}).get("art") != "bloecke":
        return 0
    from . import csv_bloecke

    zeilen = _zeilen_fuer_profil(pfad, profil)
    if not zeilen:
        return 0
    return csv_bloecke.spezifitaet(profil, zeilen)


def passende_profile(pfad: Path, profile: list) -> list[tuple[dict, str, int]]:
    """Aktive passende Profile, spezifischste zuerst; bei Gleichstand die frühere Listenposition."""
    roh: list[tuple[int, dict, str, int]] = []
    for i, prof in enumerate(profile):
        if not profil_aktiv(prof):
            continue
        ok, grund = profil_passt_grund(pfad, prof)
        if not ok:
            continue
        roh.append((i, prof, grund, _spezifitaet(pfad, prof)))
    roh.sort(key=lambda x: (-x[3], x[0]))
    return [(p, g, s) for _i, p, g, s in roh]


def profil_fuer_datei(pfad: Path, profile: list) -> tuple[dict | None, str]:
    """Passendes Profil für den Eingang. Bei mehreren gewinnt das spezifischste, sonst das weiter vorne.

    Das Standardprofil gehört ans Ende der Liste. Weitere Treffer stehen in der Begründung.
    """
    treffer_l = passende_profile(pfad, profile)
    if not treffer_l:
        return None, "Kein passendes CSV-Profil gefunden"
    treffer, grund_t, _s = treffer_l[0]
    weitere = [profil_name(p) for p, _g, _s in treffer_l[1:]]
    name = profil_name(treffer)
    if weitere:
        log.info(
            "%s: CSV-Profil „%s“ (%s); weitere passende: %s",
            pfad.name,
            name,
            grund_t,
            ", ".join(weitere),
        )
        grund_t = f"{grund_t}; weitere passende Profile: {', '.join(weitere)}"
    else:
        log.info("%s: CSV-Profil „%s“", pfad.name, name)
    return treffer, grund_t


def _profil_ist(a: dict, b: dict) -> bool:
    if a is b:
        return True
    na, nb = a.get("profil") or a.get("name"), b.get("profil") or b.get("name")
    if na and nb:
        return na == nb
    da, db = a.get("_datei"), b.get("_datei")
    return bool(da) and bool(db) and str(da) == str(db)


def eingang_anderes_profil(datei: Path, dieses: dict, profile: list) -> str | None:
    """Name des Profils, das der Eingang wählen würde, falls es nicht ``dieses`` ist."""
    liste = list(profile)
    if not any(_profil_ist(p, dieses) for p in liste):
        liste = liste + [dieses]
    gewinner, _grund = profil_fuer_datei(datei, liste)
    if gewinner is None or _profil_ist(gewinner, dieses):
        return None
    return profil_name(gewinner)
