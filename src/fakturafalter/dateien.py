# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Dateien robust schreiben, ersetzen und verschieben (vor allem für Windows).

Unter Windows scheitern ``os.replace``/``os.rename``/``unlink`` mit ``PermissionError`` (WinError 5 „Zugriff
verweigert“, 32/33 „Datei wird von einem anderen Prozess verwendet“), solange ein anderes Programm die Datei
offen hält: Virenscanner, OneDrive-Abgleich, die Explorer-Vorschau oder ein PDF-Betrachter.  Das ist meist nach
Sekundenbruchteilen vorbei – darum hier mehrere Versuche mit kurzer, wachsender Pause.  Bleibt es dabei, kommt
:class:`DateiNichtSchreibbar` mit kurzer Meldung (für den Toast); Pfad, errno und WinError stehen im Log."""
from __future__ import annotations

import errno as _errno
import logging
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

log = logging.getLogger("fakturafalter")
T = TypeVar("T")

PAUSEN = (0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.0)     # zusammen ≈ 3,5 s; Tests setzen das auf ()
BELEGT = {32, 33}                                  # ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION
VERWEIGERT = {5}                                   # ERROR_ACCESS_DENIED (auch: schreibgeschützt, Scanner)


class DateiNichtSchreibbar(PermissionError):
    """Kurz: „Datei ist gerade in Benutzung (name)“ bzw. „Kein Schreibzugriff (name)“."""

    def __init__(self, pfad: Path, ursache: OSError | None = None, aktion: str = "schreiben"):
        self.pfad = Path(pfad)
        self.ursache = ursache
        self.aktion = aktion
        self.winerror = getattr(ursache, "winerror", None)
        super().__init__(getattr(ursache, "errno", None) or _errno.EACCES, self.kurz(), str(pfad))

    @property
    def belegt(self) -> bool:
        return self.winerror in BELEGT or getattr(self.ursache, "errno", None) == _errno.EBUSY

    def kurz(self) -> str:
        if self.belegt:
            return f"Datei ist gerade in Benutzung ({self.pfad.name})"
        return f"Kein Schreibzugriff ({self.pfad.name})"

    def __str__(self) -> str:
        return self.kurz()

    def details(self) -> str:
        u = self.ursache
        return (f"{self.aktion} {self.pfad}: {type(u).__name__ if u else '–'} errno={getattr(u, 'errno', None)} "
                f"winerror={self.winerror} {getattr(u, 'strerror', '') or ''} {beschreiben(self.pfad)}").rstrip()


def beschreiben(p: Path) -> str:
    """Kurzbefund für das Log: gibt es die Datei, ist sie schreibgeschützt, ist der Ordner beschreibbar?"""
    p = Path(p)
    teile = []
    try:
        if p.exists():
            st = p.stat()
            teile.append("vorhanden" + (", schreibgeschützt" if not st.st_mode & stat.S_IWRITE else ""))
        else:
            teile.append("nicht vorhanden")
        teile.append("Ordner beschreibbar" if os.access(p.parent, os.W_OK) else "Ordner NICHT beschreibbar")
    except OSError as e:
        teile.append(f"stat: {e}")
    return "(" + ", ".join(teile) + ")"


def _wiederholbar(e: OSError) -> bool:
    if not isinstance(e, PermissionError):
        return False
    w = getattr(e, "winerror", None)
    return w is None or w in BELEGT | VERWEIGERT


def _schreibschutz_weg(p: Path) -> bool:
    """Schreibschutz-Attribut einer eigenen Datei entfernen (z. B. mitkopiert von einer schreibgeschützten
    Vorlage). -> True, wenn etwas geändert wurde."""
    try:
        if p.exists() and not p.stat().st_mode & stat.S_IWRITE:
            os.chmod(p, p.stat().st_mode | stat.S_IWRITE)
            log.info("Schreibschutz entfernt: %s", p)
            return True
    except OSError:
        pass
    return False


def wiederholen(tun: Callable[[], T], pfad: Path, aktion: str, auch: tuple[Path, ...] = ()) -> T:
    """``tun()`` ausführen; bei PermissionError (WinError 5/32/33) mit Pausen aus :data:`PAUSEN` erneut.
    Am Ende :class:`DateiNichtSchreibbar` (Details ins Log)."""
    letzt: OSError | None = None
    for i in range(len(PAUSEN) + 1):
        try:
            return tun()
        except OSError as e:
            if not _wiederholbar(e):
                raise
            letzt = e
            if i == 0:
                log.info("%s %s: %s – versuche erneut", aktion, pfad, e)
                if getattr(e, "winerror", None) in VERWEIGERT or os.name != "nt":
                    for p in (Path(pfad), *auch):
                        _schreibschutz_weg(p)
            if i < len(PAUSEN):
                time.sleep(PAUSEN[i])
    fehler = DateiNichtSchreibbar(Path(pfad), letzt, aktion)
    log.error("Konnte nicht %s: %s", aktion, fehler.details())
    raise fehler from letzt


def ersetzen(tmp: Path, ziel: Path) -> None:
    """``os.replace(tmp, ziel)`` mit Wiederholung; scheitert es endgültig, wird ``tmp`` aufgeräumt."""
    try:
        wiederholen(lambda: os.replace(tmp, ziel), Path(ziel), "ersetzen")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def schreiben(ziel: Path, daten: bytes | str, encoding: str = "utf-8") -> Path:
    """Atomar schreiben: eindeutige Temp-Datei im Zielordner, dann ersetzen (ein Abbruch hinterlässt nie eine
    halbe Datei; eine liegengebliebene, gesperrte ``.tmp`` von früher stört nicht)."""
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    roh = daten.encode(encoding) if isinstance(daten, str) else daten

    def anlegen() -> str:
        fd, name = tempfile.mkstemp(dir=ziel.parent, prefix=f".{ziel.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(roh)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
        return name

    tmp = wiederholen(anlegen, ziel, "schreiben")
    ersetzen(Path(tmp), ziel)
    return ziel


def anhaengen(ziel: Path, text: str, encoding: str = "utf-8") -> None:
    """Text anhängen (protokoll.tsv – ist sie z. B. in Excel geöffnet, gibt es nach den Versuchen eine klare
    Meldung)."""
    def tun() -> None:
        with open(ziel, "a", encoding=encoding) as f:
            f.write(text)
    wiederholen(tun, Path(ziel), "anhängen an")


def beschreibbar_pruefen(ordner: Path, datei: Path | None = None) -> None:
    """Vorab prüfen, ob in ``ordner`` geschrieben (und ``datei`` angehängt) werden kann – bevor irgendetwas
    erzeugt wird.  -> DateiNichtSchreibbar sonst."""
    ordner = Path(ordner)
    try:
        ordner.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        f = DateiNichtSchreibbar(ordner, e, "Ordner anlegen")
        log.error("Konnte nicht %s", f.details())
        raise f from e

    def probe() -> None:
        fd, name = tempfile.mkstemp(dir=ordner, prefix=".schreibtest.", suffix=".tmp")
        os.close(fd)
        os.unlink(name)
    wiederholen(probe, ordner / ".schreibtest", "probeweise schreiben in")
    if datei is not None and Path(datei).exists():
        def offen() -> None:
            with open(datei, "ab"):
                pass
        wiederholen(offen, Path(datei), "öffnen zum Anhängen")


def verschieben(datei: Path, ziel: Path) -> Path:
    """``datei`` nach ``ziel`` (Ziel darf nicht existieren).  Gleiches Laufwerk: umbenennen mit Wiederholung.
    Anderes Laufwerk: kopieren, dann Quelle löschen – lässt sich die Quelle nicht löschen, wird die Kopie
    wieder entfernt (keine Doppelten) und :class:`DateiNichtSchreibbar` gemeldet."""
    datei, ziel = Path(datei), Path(ziel)

    def umbenennen() -> None:
        os.rename(datei, ziel)
    try:
        wiederholen(umbenennen, datei, "verschieben", auch=(ziel,))
        return ziel
    except OSError as e:
        if isinstance(e, PermissionError) or e.errno != _errno.EXDEV:
            raise
    shutil.copy2(datei, ziel)
    try:
        wiederholen(lambda: datei.unlink(), datei, "verschieben (Quelle löschen)")
    except BaseException:
        ziel.unlink(missing_ok=True)
        raise
    return ziel


def _anderes_laufwerk(e: OSError) -> bool:
    """os.replace/os.rename über Laufwerks- bzw. Dateisystemgrenzen (EXDEV, WinError 17)."""
    return getattr(e, "errno", None) == _errno.EXDEV or getattr(e, "winerror", None) == 17


def _verstecken(p: Path) -> None:
    """Windows: Datei als versteckt markieren (Zwischenstand im Zielordner, nur im Notfall)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x2)  # FILE_ATTRIBUTE_HIDDEN
    except Exception:  # noqa: BLE001 – rein kosmetisch
        pass


def ablegen(quelle: Path, ziel: Path, zwischen: tuple[Path, ...] = ()) -> Path:
    """Fertige Datei ``quelle`` (z. B. im System-Temp-Ordner) atomar als ``ziel`` ablegen – ohne Temp-Datei im
    Zielordner, wo immer es geht (ab 0.9.6: der Ausgang enthält nur fertige Dateien).

    1. gleiches Laufwerk: ``os.replace`` direkt;
    2. sonst Kopie in einen der ``zwischen``-Ordner auf dem Ziellaufwerk (z. B. „Protokoll“), dann ``os.replace``;
    3. nur im Notfall (Ausgang auf eigenem Laufwerk/Netzlaufwerk): Kopie als versteckte ``.<name>.part`` im
       Zielordner, dann ``os.replace`` – sie existiert nur Sekundenbruchteile.
    Die Quelle wird danach gelöscht. ``ziel`` wird ersetzt, falls vorhanden (die Kollisionsprüfung liegt davor)."""
    quelle, ziel = Path(quelle), Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    try:
        wiederholen(lambda: os.replace(quelle, ziel), ziel, "ablegen")
        return ziel
    except OSError as e:
        if isinstance(e, PermissionError) or not _anderes_laufwerk(e):
            raise
    orte = [Path(z) for z in zwischen if z and Path(z).resolve() != ziel.parent.resolve()] + [ziel.parent]
    for ordner in orte:
        notfall = ordner == ziel.parent
        try:
            ordner.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(
                dir=ordner, prefix=f".{ziel.name}." if notfall else f"~{ziel.name}.", suffix=".part"
            )
        except OSError:
            if notfall:
                raise
            continue
        tmp = Path(name)
        try:
            with os.fdopen(fd, "wb") as f, open(quelle, "rb") as q:
                shutil.copyfileobj(q, f)
                f.flush()
                os.fsync(f.fileno())
            if notfall:
                _verstecken(tmp)
                log.info("Ablegen %s: Zwischenstand im Zielordner (anderes Laufwerk)", ziel.name)
            ersetzen(tmp, ziel)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            if not notfall and _anderes_laufwerk(e):
                continue
            raise
        Path(quelle).unlink(missing_ok=True)
        return ziel
    raise OSError(_errno.EXDEV, "Ablegen nicht möglich", str(ziel))  # pragma: no cover – Notfall wirft vorher
