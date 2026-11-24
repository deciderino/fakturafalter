# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Lokale Prüfung mit den Referenz-Werkzeugen (im Paket enthalten: Java-Laufzeit, Mustang, KoSIT):

- Mustang (enthält veraPDF) für PDF/A-3 und die ZUGFeRD/Factur-X-Prüfung der eingebetteten XML
- KoSIT-Validator + XRechnung-Konfiguration (Schema + EN16931-Schematron + XRechnung-Regeln) für die XML

Werkzeuge werden gesucht in: Umgebungsvariable FAKTURAFALTER_WERKZEUGE, ``werkzeuge/`` neben dem Programm
bzw. im Arbeitsverzeichnis. Java: FAKTURAFALTER_JAVA, ``werkzeuge/jre*/bin/java``, PATH.

Leistung: je Stapel startet höchstens eine JVM für Mustang (``fakturafalter-pruefdienst.jar`` prüft alle
PDFs nacheinander; ohne den Dienst einzeln über die Mustang-Kommandozeile) und eine für KoSIT.
Keine Online-Dienste.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

log = logging.getLogger("fakturafalter")
ZEITLIMIT = 900  # Sekunden je Werkzeug und Stapel
KEIN_PDFA = "veraPDF lieferte kein PDF/A-Ergebnis (isCompliant fehlt)"
NS = {
    "rep": "http://www.xoev.de/de/validator/varl/1",
    "svrl": "http://purl.oclc.org/dsdl/svrl",
    "s": "http://www.xoev.de/de/validator/framework/1/scenarios",
}


@dataclass
class Pruefergebnis:
    datei: str
    werkzeug: str
    gueltig: bool
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    info: str = ""
    technisch: bool = False  # Werkzeug selbst gescheitert (kein Urteil über die Rechnung)
    bericht: str = ""  # Rohbericht fürs Log

    def zeile(self) -> str:
        s = "OK " if self.gueltig else "FEHLER"
        return (
            f"{s} {self.werkzeug:8} {Path(self.datei).name}: {len(self.fehler)} Fehler, "
            f"{len(self.warnungen)} Warnungen {self.info}"
        ).rstrip()


def _kandidaten() -> list[Path]:
    k = []
    if os.environ.get("FAKTURAFALTER_WERKZEUGE"):
        k.append(Path(os.environ["FAKTURAFALTER_WERKZEUGE"]))
    k += [Path(sys.executable).resolve().parent / "werkzeuge", Path.cwd() / "werkzeuge"]
    return [p for p in k if p.is_dir()]


def _finde(muster: str) -> Path | None:
    for d in _kandidaten():
        treffer = sorted(d.glob(muster))
        if treffer:
            return treffer[-1]
    return None


def java() -> str | None:
    if os.environ.get("FAKTURAFALTER_JAVA"):
        return os.environ["FAKTURAFALTER_JAVA"]
    exe = "java.exe" if os.name == "nt" else "java"
    j = _finde(f"*jre*/bin/{exe}") or _finde(f"*jdk*/bin/{exe}")
    return str(j) if j else shutil.which("java")


def verfuegbar() -> dict[str, str | None]:
    return {
        "java": java(),
        "mustang": str(_finde("Mustang-CLI-*.jar") or "") or None,
        "kosit": str(_finde("validator-*-standalone.jar") or "") or None,
        "kosit_konfig": str(_finde("kosit-xr/scenarios.xml") or "") or None,
    }


def bereit() -> bool:
    """Alle Werkzeuge da? (Der Prüfdienst ist optional, ohne ihn startet Mustang je Datei.)"""
    return all(verfuegbar().values())


def werkzeug_versionen() -> str:
    v = verfuegbar()
    teile = [
        Path(v[n])
        .stem.replace("-standalone", "")
        .replace("validator-", "KoSIT ")
        .replace("Mustang-CLI-", "Mustang ")
        for n in ("mustang", "kosit")
        if v[n]
    ]
    return ", ".join(teile)


def _starten(cmd: list[str], eingabe: str = "") -> subprocess.CompletedProcess:
    """Java ohne Konsolenfenster (Windows) und mit UTF-8-Ausgabe starten.

    Die Standardeingabe ist immer eine (ggf. leere) Pipe: KoSIT fragt ``System.in.available()`` ab und
    bricht mit „Request not supported“ ab, wenn ein GUI-Programm unter Windows/Wine keine gültige
    Standardeingabe vererbt."""
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    return subprocess.run(
        cmd,
        input=eingabe,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=ZEITLIMIT,
        **extra,
    )


def _java_basis(xmx: str) -> list[str]:
    return [
        java() or "java",
        f"-Xmx{xmx}",
        "-Dfile.encoding=UTF-8",
        "-Dstdout.encoding=UTF-8",
        "-Djava.awt.headless=true",
    ]


def kosit(xml_dateien: list[Path]) -> list[Pruefergebnis]:
    """Alle XML-Dateien in einem Aufruf (eine JVM)."""
    v = verfuegbar()
    if not (v["java"] and v["kosit"] and v["kosit_konfig"]):
        raise RuntimeError(
            "KoSIT-Validator nicht gefunden (Java, validator-*-standalone.jar, kosit-xr/)"
        )
    konf = Path(v["kosit_konfig"])
    with tempfile.TemporaryDirectory() as out:
        try:
            p = _starten(
                [
                    *_java_basis("1g"),
                    "-jar",
                    v["kosit"],
                    "-s",
                    str(konf),
                    "-r",
                    str(konf.parent),
                    "-o",
                    out,
                    *map(str, xml_dateien),
                ]
            )
            ausgabe = (p.stderr or "") + (p.stdout or "")
        except (OSError, subprocess.TimeoutExpired) as e:
            ausgabe = f"{type(e).__name__}: {e}"
        ergebnisse = []
        for x in xml_dateien:
            rep = Path(out) / f"{Path(x).stem}-report.xml"
            if not rep.exists():
                ergebnisse.append(
                    Pruefergebnis(
                        str(x),
                        "KoSIT",
                        False,
                        ["kein Prüfbericht erzeugt"],
                        technisch=True,
                        bericht=ausgabe[-2000:],
                    )
                )
                continue
            roh = rep.read_text(encoding="utf-8", errors="replace")
            t = etree.parse(str(rep))
            fehler, warn = [], []
            for m in t.iterfind(".//rep:message", NS):
                txt = f"{m.get('code', '')} {(m.text or '').strip()}".strip()
                (
                    fehler
                    if m.get("level") == "error"
                    else warn
                    if m.get("level") == "warning"
                    else []
                ).append(txt)
            for fa in t.iterfind(".//svrl:failed-assert", NS):
                txt = f"{fa.get('id', '')} {fa.findtext('svrl:text', '', NS).strip()}"
                if fa.get("flag") in ("fatal", "error") and txt not in fehler:
                    fehler.append(txt)
                elif fa.get("flag") == "warning" and txt not in warn:
                    warn.append(txt)
            szen = t.findtext(".//rep:scenarioMatched/s:scenario/s:name", "", NS)
            acc = t.findtext(".//rep:assessment/rep:accept", None, NS) is not None
            ergebnisse.append(
                Pruefergebnis(
                    str(x), "KoSIT", acc and not fehler, fehler, warn, f"[{szen}]", bericht=roh
                )
            )
        return ergebnisse


def _verapdf_verstoesse(pdf_txt: str) -> list[str]:
    """Fehlgeschlagene veraPDF-Regeln aus ``ValidationResult [...]`` -> „veraPDF 6.2.4.3-4 Meldung“ (je Regel
    einmal, veraPDF meldet dieselbe Regel oft für jede Fundstelle)."""
    aus: list[str] = []
    for m in re.finditer(
        r"clause=([\w.]+), testNumber=(\d+)\], status=failed, message=(.*?), location=.*?"
        r"errorMessage=(.*?)\](?:, TestAssertion|\]|$)",
        pdf_txt,
        re.S,
    ):
        txt = f"veraPDF {m.group(1)}-{m.group(2)} {(m.group(4) or m.group(3)).strip()}"
        if txt not in aus:
            aus.append(txt)
    return aus


def _mustang_bericht(pdf: Path, text: str) -> Pruefergebnis:
    """Mustang-Bericht -> Urteil. „gültig“ nur, wenn Mustang ``valid`` meldet, kein Fehler vorliegt **und**
    veraPDF ``isCompliant=true`` meldet (PDF/A-3 ist für ZUGFeRD Pflicht, geprüft werden nur erzeugte Dateien).

    - ``isCompliant=false`` -> ungültig; die fehlgeschlagenen veraPDF-Regeln stehen in ``fehler``.
    - keine ``isCompliant``-Angabe -> kein Urteil über PDF/A möglich: ``technisch`` („nicht geprüft“,
      Warnung, Datei bleibt im Ausgang) statt stillschweigend „gültig“. Mustang prüft nur PDFs; reine XML
      (XRechnung) geht nur an KoSIT und ist davon nicht betroffen."""
    m = re.search(r"<validation.*</validation>", text, re.S)
    if not m:
        return Pruefergebnis(
            str(pdf), "Mustang", False, ["keine Ausgabe"], technisch=True, bericht=text[-2000:]
        )
    try:
        t = etree.fromstring(m.group(0).encode())
    except etree.XMLSyntaxError as e:
        return Pruefergebnis(
            str(pdf),
            "Mustang",
            False,
            [f"Bericht unlesbar: {e}"],
            technisch=True,
            bericht=m.group(0)[-2000:],
        )
    fehler = [f"{e.get('type', '')} {(e.text or '').strip()}".strip() for e in t.iter("error")]
    warn = [f"{e.get('type', '')} {(e.text or '').strip()}".strip() for e in t.iter("warning")]
    pdf_txt = t.findtext("pdf") or ""
    pdfa = re.search(r"flavour=(\w+).*isCompliant=(\w+)", pdf_txt, re.S)
    konform = pdfa.group(2).lower() == "true" if pdfa else None
    status = t.find("summary").get("status") if t.find("summary") is not None else "?"
    info = (
        f"[PDF/A {pdfa.group(1)} konform={pdfa.group(2)}, XML-Profil {t.findtext('xml/info/profile', '')}]"
        if pdfa
        else ""
    )
    intern = any(e.get("type") == "intern" for e in t.iter("error"))
    if konform is False:
        fehler += [v for v in _verapdf_verstoesse(pdf_txt) if v not in fehler]
    gueltig = status == "valid" and not fehler and konform is True
    if status == "valid" and not fehler and konform is None and not intern:
        log.warning(
            "Mustang %s: veraPDF lieferte keine PDF/A-Angabe (isCompliant) – PDF/A nicht geprüft",
            Path(pdf).name,
        )
        return Pruefergebnis(
            str(pdf),
            "Mustang",
            False,
            [KEIN_PDFA],
            warn,
            "[PDF/A nicht geprüft]",
            technisch=True,
            bericht=m.group(0),
        )
    return Pruefergebnis(
        str(pdf), "Mustang", gueltig, fehler, warn, info, technisch=intern, bericht=m.group(0)
    )


def mustang(pdf: Path) -> Pruefergebnis:
    """Eine Datei über die Mustang-Kommandozeile (eine JVM je Aufruf)."""
    v = verfuegbar()
    if not (v["java"] and v["mustang"]):
        raise RuntimeError("Mustang-CLI nicht gefunden (Java, Mustang-CLI-*.jar)")
    try:
        p = _starten(
            [
                *_java_basis("1g"),
                "-jar",
                v["mustang"],
                "--no-notices",
                "--action",
                "validate",
                "--source",
                str(pdf),
            ]
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return Pruefergebnis(
            str(pdf), "Mustang", False, [f"{type(e).__name__}: {e}"], technisch=True
        )
    return _mustang_bericht(pdf, (p.stdout or "") + "\n" + (p.stderr or "")[-300:])


def mustang_stapel(pdfs: list[Path]) -> list[Pruefergebnis]:
    """Alle PDFs in einer JVM über den Prüfdienst; ohne Prüfdienst einzeln."""
    if not pdfs:
        return []
    v = verfuegbar()
    dienst = _finde("fakturafalter-pruefdienst.jar")
    if not (v["java"] and v["mustang"] and dienst):
        return [mustang(p) for p in pdfs]
    try:
        p = _starten(
            [
                *_java_basis("1g"),
                "-cp",
                os.pathsep.join([str(dienst), v["mustang"]]),
                "Pruefdienst",
            ],
            eingabe="".join(f"{Path(x)}\n" for x in pdfs),
        )
        ausgabe, rest = p.stdout or "", (p.stderr or "")[-2000:]
    except (OSError, subprocess.TimeoutExpired) as e:
        ausgabe, rest = "", f"{type(e).__name__}: {e}"
    teile = dict(
        re.findall(
            r"^##FAKTURAFALTER-ANFANG (.*?)\r?\n(.*?)^##FAKTURAFALTER-ENDE", ausgabe, re.S | re.M
        )
    )
    return [
        _mustang_bericht(x, teile[str(Path(x))])
        if str(Path(x)) in teile
        else Pruefergebnis(
            str(x), "Mustang", False, ["kein Prüfbericht erzeugt"], technisch=True, bericht=rest
        )
        for x in pdfs
    ]


def pruefen(dateien: list[Path], bei_werkzeug=None) -> list[Pruefergebnis]:
    """PDF -> Mustang (veraPDF + XML) und KoSIT auf die eingebettete XML; XML -> KoSIT.
    Ergebnisse zur eingebetteten XML tragen den Pfad des PDFs (``info`` nennt „eingebettet“).
    ``bei_werkzeug``: optionaler Rückruf mit „veraPDF“ bzw. „KoSIT“, bevor das Werkzeug startet."""
    import pikepdf

    dateien = [Path(d) for d in dateien]
    pdfs = [d for d in dateien if d.suffix.lower() == ".pdf"]
    if bei_werkzeug is not None and pdfs:
        bei_werkzeug("veraPDF")
    erg: list[Pruefergebnis] = mustang_stapel(pdfs)
    xmls: list[Path] = []
    herkunft: dict[str, Path] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for i, d in enumerate(dateien):
            if d.suffix.lower() == ".pdf":
                with pikepdf.open(d) as pdf:
                    for name, fs in pdf.attachments.items():
                        if name.lower().endswith(".xml"):
                            ziel = Path(tmp) / f"{i:04d}_{d.stem}__{name}"
                            ziel.write_bytes(fs.get_file().read_bytes())
                            xmls.append(ziel)
                            herkunft[str(ziel)] = d
            else:
                xmls.append(d)
        if xmls:
            if bei_werkzeug is not None:
                bei_werkzeug("KoSIT")
            for e in kosit(xmls):
                if e.datei in herkunft:
                    e.datei = str(herkunft[e.datei])
                    e.info = f"{e.info} (eingebettete XML)".strip()
                erg.append(e)
    return erg


# ---------------------------------------------------------------- Klartext für Menschen
_ART = (
    ("BR-DE-", "XRechnung-Regel"),
    ("BR-CO-", "Rechenregel EN 16931"),
    ("BR-", "Geschäftsregel EN 16931"),
    ("CII-SR-", "Syntaxregel CII"),
    ("CII-DT-", "Datentyp-Regel CII"),
    ("FX-", "Factur-X-Regel"),
    ("PEPPOL-", "PEPPOL-Regel"),
)


# Deutsche Kurztexte zu häufigen Regeln (sonst bleibt der Originaltext des Regelwerks stehen)
DEUTSCH = {
    "BR-CO-10": "Summe der Positionsnettobeträge (BT-106) stimmt nicht mit den Positionen überein",
    "BR-CO-11": "Summe der Nachlässe auf Belegebene (BT-107) stimmt nicht",
    "BR-CO-12": "Summe der Zuschläge auf Belegebene (BT-108) stimmt nicht",
    "BR-CO-13": "Nettogesamtbetrag (BT-109) ≠ Positionssumme − Nachlässe + Zuschläge",
    "BR-CO-14": "Umsatzsteuer gesamt (BT-110) ≠ Summe der Steuerbeträge je Steuersatz",
    "BR-CO-15": "Bruttobetrag (BT-112) ≠ Nettobetrag (BT-109) + Umsatzsteuer (BT-110)",
    "BR-CO-16": "Zahlbetrag (BT-115) ≠ Bruttobetrag (BT-112) − Vorauszahlung (BT-113) + Rundung (BT-114)",
    "BR-CO-17": "Steuerbetrag je Steuersatz (BT-117) ≠ Bemessungsgrundlage × Steuersatz (gerundet)",
    "BR-S-08": "Bemessungsgrundlage beim Normalsatz (BT-116) passt nicht zu den Positionen",
    "BR-DE-1": "Zahlungsanweisungen (BG-16) fehlen",
    "BR-DE-15": "Käuferreferenz/Leitweg-ID (BT-10) fehlt",
    "BR-DE-2": "Verkäuferkontakt (BG-6) fehlt",
    "BR-DE-23-a": "Bei Überweisung muss eine IBAN (BT-84) angegeben sein",
}


def _regel(text: str) -> str:
    """Eine Werkzeugmeldung -> „Art Code: Text“ (deutscher Kurztext, wenn bekannt)."""
    text = text.strip()
    v = re.match(r"veraPDF ([\w.]+-\d+) (.*)", text, re.S)  # aus _verapdf_verstoesse
    if v:
        return f"{_t('PDF/A-Regel')} ISO 19005-3 {v.group(1)}: {v.group(2)}"
    m = re.search(r"\[ID ([\w.-]+)\]", text)  # Mustang: „4 [BR-CO-16]-… [ID BR-CO-16] from …)“
    if m:
        code = m.group(1)
        rest = re.sub(r"^\d+\s+", "", text[: m.start()]).strip()
    else:
        code, _, rest = text.partition(" ")
        if code.isdigit() or code in ("intern", ""):
            return re.sub(r"^\d+\s+", "", text)
    rest = re.sub(r"^\[[^\]]+\]-?", "", rest).strip()
    rest = DEUTSCH.get(code, rest)
    for vor, name in _ART:
        if code.startswith(vor):
            return f"{name} {code}: {rest}"
    return f"{code}: {rest}" if rest else code


def _t(text: str) -> str:
    """Text in der Sprache der Oberfläche (Übersetzungen in ``gui/texte.py``; ohne Qt importierbar)."""
    try:
        from .gui.texte import _

        return _(text)
    except Exception:  # noqa: BLE001
        return text


def gruende(e: Pruefergebnis, hoechstens: int = 8, schon: set[str] | None = None) -> list[str]:
    """Kurze Begründung (Deutsch bzw. Sprache der Oberfläche) zu einem nicht bestandenen Ergebnis.
    ``schon``: bereits genannte Gründe (Mustang und KoSIT melden XML-Regeln oft doppelt) – die werden
    übersprungen."""
    if e.gueltig:
        return []
    schon = set() if schon is None else schon
    if e.technisch:
        if e.fehler == [KEIN_PDFA]:
            return [_t("PDF/A-Prüfung (veraPDF) ohne Ergebnis – PDF/A-Konformität nicht geprüft")]
        return [
            _t("{werkzeug}: Prüfung konnte nicht laufen ({fehler})").format(
                werkzeug=e.werkzeug, fehler="; ".join(e.fehler)[:200]
            )
        ]
    pdfa_falsch = "konform=false" in e.info
    if e.werkzeug == "Mustang":
        kopf = (
            _t("PDF/A-Prüfung (veraPDF) nicht bestanden – das PDF ist nicht PDF/A-3-konform")
            if pdfa_falsch
            else _t("PDF/A-3- bzw. ZUGFeRD-Prüfung (Mustang/veraPDF) nicht bestanden")
        )
    else:
        kopf = _t("Prüfung der Rechnungsdaten nach EN 16931 (KoSIT) nicht bestanden")
        if "(eingebettete XML)" in e.info:
            kopf += " – " + _t("eingebettete XML")
    neu = []
    for f in e.fehler:
        r = _regel(f)
        if r not in schon:
            schon.add(r)
            neu.append(r)
    if e.fehler and not neu and not pdfa_falsch:
        return []  # alles schon beim anderen Werkzeug genannt
    z = [kopf + ":"] + [f"  – {r}" for r in neu[:hoechstens]]
    if len(neu) > hoechstens:
        z.append("  … " + _t("und {n} weitere (siehe Logdatei)").format(n=len(neu) - hoechstens))
    if not e.fehler:
        z.append("  – " + _t("ohne Einzelmeldung abgelehnt (siehe Logdatei)"))
    return z
