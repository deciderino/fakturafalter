# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Gemeinsamer Schritt aller Adapter: Rohfelder -> Rechnung (EN-16931-Modell) + Stammdaten."""

from __future__ import annotations

import calendar
import copy
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from . import sicht, steuerfaelle, zahlungsziel
from .konfig import Konfig, bemerkungen_aus, kundenstamm_fuer, partei_aus, zahlung_aus
from .modell import (
    Anhang,
    Herkunft,
    Klassifizierung,
    Merkmal,
    Partei,
    Position,
    Rechnung,
    Rechnungsbezug,
    Steuer,
    Zahlungsempfaenger,
    ZuAbschlag,
)

# Rohfeld: (wert, Herkunft) – wert bereits typisiert (str/Decimal/date)
Roh = dict[str, tuple[object, Herkunft]]

# Käuferfelder, die ein Profil direkt aus der Quelle liefern darf (Vorrang vor dem Kundenstamm).
# Schlüssel = Feldname im Profil, Wert = Attributpfad in Partei.
KAEUFER_FELDER = {
    "BT-44": "name",
    "BT-50": "anschrift.strasse",
    "BT-51": "anschrift.zusatz",
    "BT-163": "anschrift.zeile3",
    "BT-53": "anschrift.plz",
    "BT-52": "anschrift.ort",
    "BT-55": "anschrift.land",
    "BT-48": "ust_id",
    "BT-47": "register",  # ab 0.9.7: Registerkennung des Käufers (Reverse Charge ohne USt-IdNr.)
    "BT-49": "elektronische_adresse",
    "BT-56": "kontakt_name",
    "BT-57": "kontakt_telefon",
    "BT-58": "kontakt_email",
}
AUSGABEFORMATE = ("ZUGFERD_EN16931", "XRECHNUNG_CII", "XRECHNUNG_UBL")

# Belegart in der Quelle -> BT-3 (UNTDID 1001). Ein Profil kann unter ``mappings.belegart`` ergänzen.
BELEGART = {
    "re": "380",
    "rg": "380",
    "rechnung": "380",
    "invoice": "380",
    "380": "380",
    "gs": "381",
    "gutschrift": "381",
    "creditnote": "381",
    "credit note": "381",
    "381": "381",
    "ko": "384",
    "korrektur": "384",
    "rechnungskorrektur": "384",
    "korrekturrechnung": "384",
    "384": "384",
    "ar": "386",
    "anzahlung": "386",
    "anzahlungsrechnung": "386",
    "386": "386",
    "tr": "326",
    "teilrechnung": "326",
    "326": "326",
    "schlussrechnung": "380",
}
# Zahlungsart in der Quelle -> BT-81 (UNTDID 4461)
ZAHLUNGSART = {
    "ue": "58",
    "überweisung": "58",
    "ueberweisung": "58",
    "sepa-überweisung": "58",
    "58": "58",
    "30": "30",
    "ls": "59",
    "lastschrift": "59",
    "sepa-lastschrift": "59",
    "sepa lastschrift": "59",
    "einzug": "59",
    "bankeinzug": "59",
    "59": "59",
    "49": "49",
    "bar": "10",
    "barzahlung": "10",
    "10": "10",
    "karte": "48",
    "kartenzahlung": "48",
    "ec": "48",
    "48": "48",
    "kreditkarte": "54",
    "54": "54",
    "paypal": "68",
    "68": "68",
    "verrechnung": "97",
    "97": "97",
}
# Zeilenart einer Position: Rabatt-/Zuschlagszeilen werden zu Nachlässen/Zuschlägen auf Belegebene (BG-20/21)
ZEILENART = {
    "rabatt": "rabatt",
    "nachlass": "rabatt",
    "abschlag": "rabatt",
    "r": "rabatt",
    "discount": "rabatt",
    "zuschlag": "zuschlag",
    "z": "zuschlag",
    "fracht": "zuschlag",
    "versand": "zuschlag",
    "porto": "zuschlag",
    "verpackung": "zuschlag",
    "charge": "zuschlag",
    "p": "",
    "position": "",
    "artikel": "",
    "": "",
}
FRACHT = ("fracht", "versand", "porto", "lieferung")


def _code(
    mapping: dict | None, eingebaut: dict[str, str], wert, was: str, r: Rechnung, feld: str
) -> str | None:
    """Text aus der Quelle -> Code (Profil-Mapping vor eingebauter Liste); unbekannt -> „prüfen“, None."""
    t = str(wert).strip()
    for k, v in (mapping or {}).items():
        if str(k).strip().lower() == t.lower():
            return str(v)
    if t.lower() in eingebaut:
        return eingebaut[t.lower()]
    r.hinweis("pruefen", f"{was} „{t}“ ist nicht zugeordnet", feld)
    return None


def _dez(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v).replace("%", "").replace(",", ".").strip())
    except ArithmeticError:
        return None


def _setzen(p: Partei, pfad: str, wert: str) -> None:
    ziel, _, attr = pfad.rpartition(".")
    setattr(getattr(p, ziel) if ziel else p, attr, wert)


def stammdaten_aus_definition(
    definition: dict, konfig: Konfig
) -> tuple[Partei, object, list[tuple[str, str]], bool]:
    """Verkäufer, Zahlung, Bemerkungen: Konfiguration, überschrieben durch die Blöcke ``verkaeufer``,
    ``zahlung`` und ``bemerkungen`` im Profil bzw. in der Vorlage (falls vorhanden).
    -> (verkaeufer, zahlung, bemerkungen, aus_profil)"""
    vk = definition.get("verkaeufer")
    zb = definition.get("zahlung")
    verkaeufer = partei_aus(vk, konfig.absender) if vk else copy.deepcopy(konfig.absender)
    basis = copy.deepcopy(konfig.zahlung)
    if vk and not (zb or {}).get("kontoinhaber"):
        basis.kontoinhaber = ""  # anderer Verkäufer -> Kontoinhaber = dessen Name (siehe unten)
    zahlung = zahlung_aus(zb, basis) if zb else basis
    bem = (
        bemerkungen_aus(definition["bemerkungen"])
        if definition.get("bemerkungen") is not None
        else list(konfig.bemerkungen)
    )
    return verkaeufer, zahlung, bem, bool(vk or zb)


def _map(mapping: dict, wert: str, was: str, r: Rechnung, feld: str):
    m = mapping or {}
    if wert in m:
        return m[wert], True
    # tolerant: ohne Punkt / Groß-Klein
    for k, v in m.items():
        if str(k).rstrip(".").lower() == str(wert).rstrip(".").lower():
            return v, True
    aktion = m.get("unbekannt", "pruefen")
    if aktion == "allgemein":  # Einheit: allgemeine Liste („Stk.“ -> H87), sonst prüfen
        from .pdferkennung import einheit_code

        if code := einheit_code(str(wert)):
            return code, True
        aktion = "pruefen"
    if aktion == "satz":  # Steuer: Spalte enthält den Satz („19“, „7,00 %“) -> Kategorie S
        try:
            n = Decimal(str(wert).replace("%", "").replace(",", ".").strip())
        except ArithmeticError:
            n = Decimal(0)
        if n > 0:
            return {"BT-151": "S", "BT-152": n.normalize()}, True
        aktion = "pruefen"
    if aktion in ("pruefen", "fehler"):
        r.hinweis(
            "pruefen" if aktion == "pruefen" else "fehler",
            f"{was} „{wert}“ ist nicht zugeordnet",
            feld,
        )
        return None, False
    return aktion, True  # fester Ersatzwert, z.B. C62


def _monat(v) -> tuple[date, date] | None:
    """Leistungsmonat (§ 31 Abs. 4 UStDV) -> (erster, letzter Tag). Akzeptiert date/datetime (beliebiger Tag
    im Monat) oder Text „2026-10“, „10/2026“, „10.2026“, „102026“."""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        j, m = v.year, v.month
    else:
        t = str(v).strip()
        a = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
        b = re.fullmatch(r"(\d{1,2})[./]?(\d{4})", t)
        if a:
            j, m = int(a[1]), int(a[2])
        elif b:
            j, m = int(b[2]), int(b[1])
        else:
            return None
        if not 1 <= m <= 12:
            return None
    return date(j, m, 1), date(j, m, calendar.monthrange(j, m)[1])


def rechnung_bauen(
    kopf: Roh, positionen: list[Roh], definition: dict, konfig: Konfig, quelle: str
) -> Rechnung:
    r = Rechnung(quelle=quelle)
    mappings = definition.get("mappings", {})
    stamm = stammdaten_aus_definition(definition, konfig)
    ku = stamm[0].kleinunternehmer  # § 19 UStG: alle Positionen E/0 mit Hinweistext

    def wert(feld, default=None):
        v = kopf.get(feld)
        if v is None or v[0] in (None, ""):
            return default
        r.herkunft[feld] = v[1]
        return v[0]

    r.nummer = str(wert("BT-1", ""))
    r.datum = wert("BT-2")
    r.art = str(wert("BT-3", "380"))
    r.waehrung = waehrung_code(wert("BT-5", "EUR"))
    r.steuerhinweis = " ".join(str(wert("steuerhinweis", "") or "").split())
    _kurs_setzen(r, wert)
    r.leistungsdatum = wert("BT-72")
    r.leistung_von = wert("BT-73")  # BG-14 Rechnungszeitraum
    r.leistung_bis = wert("BT-74")
    lm = wert("leistungsmonat")  # § 31 Abs. 4 UStDV: Kalendermonat genügt
    if lm is not None:
        monat = _monat(lm)
        if monat:
            r.leistung_von = r.leistung_von or monat[0]
            r.leistung_bis = r.leistung_bis or monat[1]
        else:
            r.hinweis(
                "pruefen", f"Leistungsmonat „{lm}“ nicht lesbar (erwartet z. B. 10/2026)", "BG-14"
            )
    r.bestellnummer = str(wert("BT-13", "") or "")
    r.kundennummer = str(wert("kundennummer", "") or "")
    if wert("belegart") is not None:  # „GS“/„Gutschrift“ -> 381 usw.
        r.art = (
            _code(mappings.get("belegart"), BELEGART, wert("belegart"), "Belegart", r, "BT-3")
            or r.art
        )
    if wert("BT-25") is not None:  # BG-3 Rechnungsbezug (Gutschrift/Korrektur)
        r.bezuege.append(Rechnungsbezug(str(wert("BT-25")).strip(), wert("BT-26")))
    ref = r.referenzen
    for k, attr in (
        ("BT-11", "projekt"),
        ("BT-12", "vertrag"),
        ("BT-14", "auftrag"),
        ("BT-15", "wareneingang"),
        ("BT-16", "lieferschein"),
        ("BT-17", "ausschreibung"),
        ("BT-18", "objekt"),
        ("BT-19", "buchung"),
    ):
        if wert(k) is not None:
            setattr(ref, attr, str(wert(k)).strip())
    lf = r.lieferung
    for k, attr in (("BT-70", "name"), ("BT-71", "ort_id")):
        if wert(k) is not None:
            setattr(lf, attr, str(wert(k)).strip())
    for k, attr in (
        ("BT-75", "strasse"),
        ("BT-76", "zusatz"),
        ("BT-78", "plz"),
        ("BT-77", "ort"),
        ("BT-80", "land"),
    ):
        if wert(k) is not None:
            setattr(lf.anschrift, attr, str(wert(k)).strip())
    if lf.anschrift and not lf.anschrift.land:
        lf.anschrift.land = "DE"
    r_bemerkung = str(wert("BT-22", "") or "").strip()
    if wert("BT-124") is not None:  # BG-24: Link auf eine Unterlage
        r.anhaenge.append(
            Anhang(kennung="Anlage", beschreibung="Unterlage", uri=str(wert("BT-124")).strip())
        )
    if wert("BT-113") is not None:
        r.vorausbezahlt = abs(Decimal(str(wert("BT-113"))))
    for zu, k_proz, k_betrag, k_grund in (
        (False, "BT-94", "BT-92", "BT-97"),
        (True, "BT-101", "BT-99", "BT-104"),
    ):
        proz, betrag = _dez(wert(k_proz)), _dez(wert(k_betrag))
        if proz or betrag:
            grund = str(wert(k_grund, "") or "") or ("Zuschlag" if zu else "Rabatt")
            r.zu_abschlaege.append(
                ZuAbschlag(
                    zuschlag=zu,
                    betrag=abs(betrag) if betrag else None,
                    prozent=abs(proz) if proz and not betrag else None,
                    grund=grund,
                    grund_code="" if zu else "95",
                )
            )
    for k in ("BT-109", "BT-110", "BT-112"):
        if k in kopf and kopf[k][0] not in (None, ""):
            r.kontrolle[k] = kopf[k][0]

    for nr, p in enumerate(positionen, 1):
        pos = Position()
        g = lambda f, d=None: p.get(f, (d,))[0] if p.get(f, (None,))[0] not in (None, "") else d  # noqa: E731
        za_art = ZEILENART.get(str(g("zeilenart", "") or "").strip().lower())
        if za_art is None:
            za_art = (
                _code(mappings.get("zeilenart"), {}, g("zeilenart"), "Zeilenart", r, f"Pos {nr}")
                or ""
            )
        if za_art:  # Rabatt-/Zuschlagszeile -> BG-20/BG-21
            _zeile_als_zu_abschlag(r, g, za_art, mappings, nr)
            continue
        pos.nr = str(g("BT-126", nr)).strip()
        pos.artikelnummer = str(g("BT-155", "") or "")
        pos.bezeichnung = str(g("BT-153", "") or "")
        pos.menge = g("BT-129")  # None = fehlt -> Pflichtprüfung (keine stille 0)
        pos.einzelpreis = g("BT-146")
        pe = g("BT-149")  # Preiseinheit (optional, Standard 1)
        if pe is not None:
            try:
                pos.preiseinheit = Decimal(str(pe))
            except ArithmeticError:
                r.hinweis("pruefen", f"Preiseinheit „{pe}“ ist keine Zahl", f"Pos {pos.nr} BT-149")
        pos.kontrolle_gesamt = g("gesamt_kontrolle")
        eh = g("BT-130", "")
        if eh:
            code, ok = _map(
                mappings.get("einheiten", {}), str(eh), "Einheit", r, f"Pos {pos.nr} BT-130"
            )
            pos.einheit = code or ""  # nicht zugeordnet -> bereits als Prüffall markiert
        st = g("steuer", "")
        if ku:
            pos.steuer = _ku_steuer(r, stamm[0], st, mappings, pos.nr)
        else:
            code, ok = _map(
                mappings.get("steuer", {}), str(st), "Steuerschlüssel", r, f"Pos {pos.nr} BT-151"
            )
            neu = steuer_aus_code(code, r.steuerhinweis)
            if neu is not None:
                pos.steuer = neu
            elif isinstance(code, dict):
                r.hinweis("pruefen", "Steuerfall nicht bestimmbar: kein Steuerhinweis im Druck und kein Steuersatz",
                          f"Pos {pos.nr} BT-151")
        _position_ergaenzen(pos, g)
        if not pos.bezeichnung:
            r.hinweis("pruefen", "Bezeichnung fehlt", f"Pos {pos.nr} BT-153")
        r.positionen.append(pos)
    _vorzeichen(r)

    # --- Stammdaten -----------------------------------------------------------
    r.verkaeufer, r.zahlung, r.bemerkungen, aus_profil = stamm
    r.herkunft["verkaeufer"] = Herkunft("profil" if aus_profil else "konfig", 1.0)
    basis = Path(definition.get("_basis", konfig.basis))
    ks = kundenstamm_fuer(definition.get("kundenstamm"), basis)
    eintrag = ks.get(r.kundennummer)
    if eintrag:
        r.kaeufer = ks.partei(r.kundennummer)
        r.herkunft["kaeufer"] = Herkunft(f"kundenstamm:{r.kundennummer}", 1.0)
        r.leitweg_id = eintrag.get("leitweg_id_bt10", "")
        if eintrag.get("zahlungsziel_tage"):
            r.zahlung.ziel_tage = int(eintrag["zahlungsziel_tage"])
        if eintrag.get("format"):
            r.ausgabeformat = eintrag["format"]
    # Käuferdaten direkt aus der Quelle (z. B. CSV-Spalten) haben Vorrang vor dem Kundenstamm
    aus_quelle = [f for f in KAEUFER_FELDER if wert(f) is not None]
    for f in aus_quelle:
        _setzen(r.kaeufer, KAEUFER_FELDER[f], str(wert(f)).strip())
    _namenszeilen(r, wert)
    for a in (r.kaeufer.anschrift, r.lieferung.anschrift):  # „Österreich“ -> AT
        if a.land and not re.fullmatch(r"[A-Z]{2}", a.land):
            a.land = steuerfaelle.land_code(a.land) or a.land
    la = r.lieferung.anschrift
    if la.land and not (r.lieferung.name or la.strasse or la.plz or la.ort or la.zusatz):
        # nur „Lieferland“ (BT-80) ohne Anschrift: gleiches Land wie der Käufer -> Käuferanschrift gilt (die
        # E-Rechnung übernimmt sie bei innergemeinschaftlicher Lieferung als Lieferanschrift)
        if la.land == (r.kaeufer.anschrift.land or "DE"):
            la.land = ""
        else:
            r.hinweis("pruefen", (f"Lieferland {la.land} weicht vom Land des Kunden ab – bitte die vollständige "
                                  "Lieferanschrift (Name, Straße, PLZ, Ort) angeben."), "BT-80")
    if aus_quelle and not r.kaeufer.kennung:
        r.kaeufer.kennung = r.kundennummer  # BT-46
    if wert("BT-10") is not None:
        r.leitweg_id = str(wert("BT-10")).strip()
    faellig_druck = None
    if "BT-20" in kopf:  # Zahlungsbedingung aus der Quelle/dem Druck: gilt statt des Profils
        zz = zahlungsziel.lesen(str(kopf["BT-20"][0] or ""))
        r.herkunft["BT-20"] = kopf["BT-20"][1]
        r.zahlung.bedingungen = (
            zz.text
        )  # "" = im Druck erwartet, aber nicht gelesen: kein Profiltext
        r.zahlung.ziel_tage = zz.tage  # kein Zahlungsziel aus dem Profil, wenn der Druck eins trägt
        faellig_druck = zz.faellig
    else:
        r.herkunft["BT-20"] = Herkunft("profil", 1.0)  # Standardtext des Profils
    if wert("zahlungsziel_tage") is not None:
        r.zahlung.ziel_tage = int(Decimal(str(wert("zahlungsziel_tage"))))
    bt44_offen = any(h.feld == "BT-44" for h in r.hinweise)  # z. B. Kundenbezeichnung 1 fehlt
    if bt44_offen:
        pass
    elif not eintrag and not r.kaeufer.name:
        r.hinweis(
            definition.get("kundenstamm", {}).get("fehlt", "pruefen")
            if definition.get("kundenstamm")
            else "pruefen",
            f"Kunde „{r.kundennummer}“ nicht im Kundenstamm",
            "BT-44",
        )
    elif not r.kaeufer.name:
        r.hinweis("pruefen", "Name des Käufers fehlt", "BT-44")
    # Ausgabeformat fest im Profil? (sonst aus dem Kundenstamm, Standard ZUGFERD_EN16931)
    fmt = str((definition.get("ausgabe") or {}).get("format") or "aus_kundenstamm")
    if fmt in AUSGABEFORMATE:
        r.ausgabeformat = fmt
    elif fmt != "aus_kundenstamm":
        r.hinweis("pruefen", f"Ausgabeformat „{fmt}“ im Profil unbekannt", "ausgabe.format")

    if faellig_druck:
        r.zahlung.faellig = faellig_druck
    elif r.datum and r.zahlung.ziel_tage is not None:
        r.zahlung.faellig = r.datum + timedelta(days=int(r.zahlung.ziel_tage))
    if "{zahlungsziel_tage}" in r.zahlung.bedingungen:
        # ohne Zahlungsziel keine halbe Textvorlage („zahlbar innerhalb  Tagen“) – dann fehlt BT-20 sichtbar
        r.zahlung.bedingungen = (
            ""
            if r.zahlung.ziel_tage is None
            else r.zahlung.bedingungen.replace("{zahlungsziel_tage}", str(r.zahlung.ziel_tage))
        )
    if not r.zahlung.kontoinhaber:
        r.zahlung.kontoinhaber = r.verkaeufer.name
    if r_bemerkung:
        r.bemerkungen = [*r.bemerkungen, (r_bemerkung, "")]
    _zahlung_aus_quelle(r, wert, mappings, eintrag or {})

    # --- Pflichtfelder / Sicherheit -------------------------------------------
    pflicht = {"BT-1": r.nummer, "BT-2": r.datum}
    for f, v in pflicht.items():
        if not v:
            r.hinweis("pruefen", "Pflichtfeld fehlt", f)
    # Leistungsdatum, Anschriften, Steuer, Zahlung usw.: siehe pflichtpruefung.py (läuft nach dem Rechnen)
    if not r.positionen:
        r.hinweis("pruefen", "keine Positionen gefunden", "BG-25")
    schwelle = konfig.schwelle
    for f, h in r.herkunft.items():
        if h.sicherheit < schwelle:
            r.hinweis(
                "pruefen", f"unsicher erkannt ({h.sicherheit:.2f} < {schwelle}) aus {h.quelle}", f
            )
    sicht.gutschrift_zahlung_setzen(r)
    return r


def waehrung_code(v) -> str:
    """„EUR“, „usd“, „$“, „US$“ -> ISO-4217-Code; Unbekanntes bleibt (Pflichtprüfung meldet es)."""
    t = " ".join(str(v or "").split())
    if re.fullmatch(r"[A-Za-z]{3}", t):
        return t.upper()
    gef = steuerfaelle.waehrungen_im_text(t)
    return gef[0] if len(gef) == 1 else (t or "EUR")


def _kurs_setzen(r: Rechnung, wert) -> None:
    """Fremdwährung (ab 0.9.7): Kurs „1 EUR = x BT-5“ (Zahl oder Kurszeile), Kursdatum, USt in EUR (BT-111)."""
    k = wert("kurs")
    if k is not None:
        if isinstance(k, Decimal):
            r.kurs = k
        else:
            kurs, fw = steuerfaelle.kurs_lesen(str(k), r.waehrung)
            if kurs is None:
                kurs = steuerfaelle.dezimal(str(k))
            r.kurs = kurs
            if fw and fw != r.waehrung and r.waehrung == "EUR":
                r.waehrung = fw  # Kurszeile nennt die Rechnungswährung, die Quelle hatte keine
            if kurs is None:
                r.hinweis("pruefen", f"Umrechnungskurs „{k}“ nicht lesbar (erwartet z. B. 1,0850)", "kurs")
    kd = wert("kursdatum")
    if kd is not None:
        r.kursdatum = kd if isinstance(kd, date) else None
    u = wert("BT-111")
    if u is not None:
        r.ust_eur_quelle = u if isinstance(u, Decimal) else steuerfaelle.dezimal(str(u))


def steuer_aus_code(code, hinweis: str = "") -> Steuer | None:
    """Steuer-Mapping eines Profils -> Steuer. Werte: {BT-151, BT-152, BT-120, BT-121}, ein Steuerfall („AE“,
    „K“, „G“, „O“, „KU“) oder {fall: AE, BT-120: Text}. Mit ``fall: hinweis`` entscheidet der Hinweistext der
    Rechnung (Druck), sonst gilt das Mapping selbst (Regelbesteuerung)."""
    if isinstance(code, str) and code in steuerfaelle.FAELLE:
        return steuerfaelle.steuer(code, hinweis if steuerfaelle.erkennen(hinweis) == code else "")
    if not isinstance(code, dict):
        return None
    fall = str(code.get("fall") or "")
    if fall == "hinweis":
        erkannt = steuerfaelle.erkennen(hinweis)
        if erkannt:
            return steuerfaelle.steuer(erkannt, hinweis)
        if "BT-152" not in code:
            return None  # kein Hinweis im Druck und kein Satz: nicht raten
    elif fall in steuerfaelle.FAELLE:
        passt = hinweis if steuerfaelle.erkennen(hinweis) == fall else ""
        return steuerfaelle.steuer(fall, str(code.get("BT-120") or "") or passt)
    return Steuer(
        str(code.get("BT-151", "S")),
        Decimal(str(code.get("BT-152", 0))),
        str(code.get("BT-120", "") or ""),
        str(code.get("BT-121", "") or ""),
    )


def _ku_steuer(r: Rechnung, vk, st, mappings: dict, nr: str) -> Steuer:
    """Kleinunternehmer: jede Position E/0 mit Hinweistext. Liefert die Quelle trotzdem einen Satz > 0, hält die
    Rechnung an (nicht still überschreiben)."""
    if st not in (None, ""):
        code = (mappings.get("steuer") or {}).get(str(st))
        if code is None and str(st).replace(",", ".").replace("%", "").strip() not in ("0", "0.0", "0.00"):
            try:
                satz = Decimal(str(st).replace("%", "").replace(",", ".").strip())
            except ArithmeticError:
                satz = None
            if satz:
                code = {"BT-151": "S", "BT-152": satz}
        alt = steuer_aus_code(code, r.steuerhinweis) if code is not None else None
        if alt is not None and alt.kategorie == "S" and alt.satz > 0:
            r.hinweis("pruefen", (f"Absender ist Kleinunternehmer (§ 19 UStG), die Quelle nennt für Position {nr} "
                                  f"aber {alt.satz:g} % Umsatzsteuer – Einstellung oder Quelle prüfen."),
                      f"Pos {nr} BT-152")
    return steuerfaelle.steuer("KU", vk.kleinunternehmer_text or "")


def _zelle(v) -> str:
    """Zelle für eine Namenszeile: Rand-Leerraum weg, innere Leerräume und Umbrüche -> ein Leerzeichen."""
    return " ".join(str(v or "").split())


def _namenszeilen(r: Rechnung, wert) -> None:
    """Kundenbezeichnung 1–3 (ab 0.9.5): BT-44 ist Zeile 1 (auch die bisherige Einzelspalte „Kunde“),
    ``kaeufer_name_2``/``_3`` sind optional. In der XML steht in BT-44 alles mit je einem Leerzeichen verbunden,
    die Sichtseite zeigt jede belegte Zeile einzeln. Ohne Zeile 2/3 bleibt alles wie bisher.
    Zeile 2/3 ohne Zeile 1 rückt nicht nach oben: Hinweis „prüfen“ (BT-44)."""
    z2, z3 = _zelle(wert("kaeufer_name_2")), _zelle(wert("kaeufer_name_3"))
    if not (z2 or z3):
        return
    z1 = _zelle(wert("BT-44"))
    if not z1:
        r.hinweis(
            "pruefen",
            "Kundenbezeichnung 1 fehlt, obwohl Kundenbezeichnung 2 oder 3 belegt ist "
            "(Zeile 1 ist Pflicht; Zeile 2/3 rückt nicht nach oben)",
            "BT-44",
        )
        r.kaeufer.name, r.kaeufer.name_zeilen = "", []
        return
    zeilen = [z for z in (z1, z2, z3) if z]
    r.kaeufer.name_zeilen = zeilen
    r.kaeufer.name = " ".join(zeilen)


# Artikelmerkmale (BG-32) mit fester Bedeutung aus eigenen CSV-Spalten (ab 0.9.5)
MERKMAL_ZEICHNUNG = "Zeichnungsnummer"
MERKMAL_INDEX = "Index"


def _position_ergaenzen(pos: Position, g) -> None:
    """Freiwillige Positionsfelder (BT-127 … BT-161, BG-27/28) aus der Quelle."""
    pos.notiz = str(g("BT-127", "") or "")
    pos.beschreibung = str(g("BT-154", "") or "")
    pos.kaeufer_artikelnummer = str(g("BT-156", "") or "")
    if g("BT-157"):
        pos.standard_id, pos.standard_schema = (
            str(g("BT-157")).strip(),
            str(g("BT-157-1", "0160")),
        )  # 0160 = GTIN
    pos.ursprungsland = str(g("BT-159", "") or "").strip().upper()
    pos.bestellposition = str(g("BT-132", "") or "")
    pos.objektkennung = str(g("BT-128", "") or "")
    pos.buchungsreferenz = str(g("BT-133", "") or "")
    pos.leistung_von, pos.leistung_bis = g("BT-134"), g("BT-135")
    if g("BT-158"):
        pos.klassifizierungen.append(
            Klassifizierung(str(g("BT-158")).strip(), str(g("BT-158-1", "ZZZ")))
        )
    if g("BT-161"):
        pos.merkmale.append(Merkmal(str(g("BT-160", "Merkmal")), str(g("BT-161"))))
    for feld, name in (("zeichnungsnummer", MERKMAL_ZEICHNUNG), ("index", MERKMAL_INDEX)):
        w = " ".join(str(g(feld, "") or "").split())
        if w:  # optional: leer = kein Merkmal, keine Zeile
            pos.merkmale.append(Merkmal(name, w))
    if g("BT-148") is not None:
        pos.bruttopreis = Decimal(str(g("BT-148")))
    if g("BT-147") is not None:
        pos.preisrabatt = abs(Decimal(str(g("BT-147"))))
    proz, betrag = _dez(g("BT-138")), _dez(g("BT-136"))
    if proz or betrag:
        pos.zu_abschlaege.append(
            ZuAbschlag(
                betrag=abs(betrag) if betrag else None,
                prozent=abs(proz) if proz and not betrag else None,
                grund=str(g("BT-139", "") or "Rabatt"),
                grund_code="95",
            )
        )
    zb, zp = _dez(g("BT-141")), _dez(g("BT-143"))
    if zb or zp:
        pos.zu_abschlaege.append(
            ZuAbschlag(
                zuschlag=True,
                betrag=abs(zb) if zb else None,
                prozent=abs(zp) if zp and not zb else None,
                grund=str(g("BT-144", "") or "Zuschlag"),
            )
        )


def _zeile_als_zu_abschlag(r: Rechnung, g, art: str, mappings: dict, nr: int) -> None:
    """Rabatt- oder Zuschlagszeile (eigene Satzart/Zeilenart) -> Nachlass/Zuschlag auf Belegebene.
    Betrag: Positionsbetrag, sonst Menge × Preis, sonst Preis; das Vorzeichen in der Quelle zählt nicht."""
    text = str(g("BT-153", "") or "")
    betrag = _dez(g("gesamt_kontrolle"))
    if betrag is None and _dez(g("BT-146")) is not None:
        betrag = _dez(g("BT-146")) * (_dez(g("BT-129")) or Decimal(1))
    proz = _dez(g("BT-138")) if betrag is None else None
    steuer = None
    st = g("steuer", "")
    if st:
        code, _ok = _map(
            mappings.get("steuer", {}), str(st), "Steuerschlüssel", r, f"Pos {nr} BT-151"
        )
        if isinstance(code, dict):
            steuer = Steuer(
                str(code.get("BT-151", "S")),
                Decimal(str(code.get("BT-152", 0))),
                str(code.get("BT-120", "") or ""),
                str(code.get("BT-121", "") or ""),
            )
    if betrag is None and proz is None:
        r.hinweis(
            "pruefen",
            f"{'Zuschlag' if art == 'zuschlag' else 'Rabatt'}szeile ohne Betrag",
            f"Pos {nr}",
        )
        return
    zu = art == "zuschlag"
    code = ("FC" if any(w in text.lower() for w in FRACHT) else "ABL") if zu else "95"
    r.zu_abschlaege.append(
        ZuAbschlag(
            zuschlag=zu,
            betrag=abs(betrag) if betrag is not None else None,
            prozent=abs(proz) if proz is not None else None,
            grund=text or ("Zuschlag" if zu else "Rabatt"),
            grund_code=code,
            steuer=steuer,
        )
    )


def _vorzeichen(r: Rechnung) -> None:
    """EN 16931: Preise (BT-146/148) sind nie negativ (BR-27/BR-28), Gutschriften (381) tragen positive Beträge –
    das Vorzeichen steckt in der Belegart. Negative Preise -> negative Menge; Gutschrift mit negativen Beträgen ->
    alle Beträge positiv. Summe und Steuer ändern sich dadurch nicht (bei 381 nur das Vorzeichen)."""

    def betrag(p: Position) -> Decimal:
        try:
            return Decimal(str(p.menge or 0)) * Decimal(str(p.einzelpreis or 0))
        except ArithmeticError:
            return Decimal(0)

    if r.art == "381" and sum((betrag(p) for p in r.positionen), Decimal(0)) < 0:
        for p in r.positionen:
            if p.menge is not None:
                p.menge = -Decimal(str(p.menge))
            if p.kontrolle_gesamt is not None:
                p.kontrolle_gesamt = -Decimal(str(p.kontrolle_gesamt))
        for k in ("BT-109", "BT-110", "BT-112"):
            if k in r.kontrolle:
                r.kontrolle[k] = abs(Decimal(str(r.kontrolle[k])))
        r.hinweis(
            "info",
            "Gutschrift mit negativen Beträgen: als positive Beträge übernommen (Belegart 381)",
            "BT-3",
        )
    for p in r.positionen:
        if p.einzelpreis is not None and Decimal(str(p.einzelpreis)) < 0:
            p.einzelpreis = -Decimal(str(p.einzelpreis))
            if p.menge is not None:
                p.menge = -Decimal(str(p.menge))
            r.hinweis(
                "info",
                "negativer Preis als negative Menge übernommen (BR-27)",
                f"Pos {p.nr} BT-146",
            )


def _zahlung_aus_quelle(r: Rechnung, wert, mappings: dict, eintrag: dict) -> None:
    """Zahlungsart, SEPA-Lastschrift (Mandat BT-89, Gläubiger-ID BT-90, IBAN des Zahlers BT-91), Verwendungszweck.
    Kundenstamm: Spalten ``mandat_bt89`` und ``iban_bt91``. Gläubiger-ID sonst aus dem Absenderprofil."""
    z = r.zahlung
    if wert("zahlungsart") is not None:
        z.art = (
            _code(
                mappings.get("zahlungsart"),
                ZAHLUNGSART,
                wert("zahlungsart"),
                "Zahlungsart",
                r,
                "BT-81",
            )
            or z.art
        )
    mandat = str(wert("BT-89", "") or eintrag.get("mandat_bt89") or "").strip()
    if mandat:
        z.mandat = mandat
        if wert("zahlungsart") is None and not z.lastschrift:
            z.art = "59"
            r.hinweis(
                "info", "Mandatsreferenz angegeben: Zahlungsart SEPA-Lastschrift (59)", "BT-81"
            )
    iban = str(wert("BT-91", "") or eintrag.get("iban_bt91") or "").replace(" ", "").upper()
    if iban:
        z.lastschrift_iban = iban
    if wert("BT-90") is not None:
        z.glaeubiger_id = str(wert("BT-90")).replace(" ", "").upper()
    if wert("BT-83") is not None:
        z.verwendungszweck = str(wert("BT-83")).strip()
    if wert("BT-59") is not None:
        r.zahlungsempfaenger = Zahlungsempfaenger(name=str(wert("BT-59")).strip())
