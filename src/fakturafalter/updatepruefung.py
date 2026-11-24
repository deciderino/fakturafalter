# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Updateprüfung – der einzige Netzzugriff von Fakturafalter (ab 0.9.6).

Ein einzelner GET auf die öffentliche GitHub-Releases-API von deciderino/fakturafalter. Gesendet wird nichts
außer der Anfrage selbst mit dem nötigen User-Agent „Fakturafalter/<Version>“: keine Rechnungsdaten, keine
Kennung, keine Konfiguration, keine Cookies.  Kurzer Timeout, immer im Hintergrund-Thread; ohne Netz still
(nur ein Debug-Eintrag im Log).  Es wird nie etwas heruntergeladen oder installiert – bei einer neueren Version
gibt es nur einen Hinweis mit Link zur Release-Seite.  Abschaltbar in den Einstellungen (``optionen.updatepruefung``).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import urllib.request
from dataclasses import dataclass

from . import __version__

log = logging.getLogger("fakturafalter")

REPO = "deciderino/fakturafalter"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES = f"https://github.com/{REPO}/releases"
TIMEOUT = 4.0  # Sekunden


@dataclass
class Neu:
    version: str
    url: str
    vorab: bool = False


def version_tupel(v: str) -> tuple:
    """„v0.9.6“ -> (0, 9, 6, 1, 0); Vorversionen wie „0.9.6rc1“/„0.9.6-beta.2“ zählen vor 0.9.6."""
    m = re.match(
        r"^\s*v?(\d+(?:\.\d+)*)(?:[-.]?(a|alpha|b|beta|rc|pre)\.?(\d*))?", str(v or ""), re.I
    )
    if not m:
        return ()
    zahlen = [int(x) for x in m.group(1).split(".")]
    zahlen += [0] * (4 - len(zahlen))
    if m.group(2):
        rang = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "pre": 2, "rc": 2}[m.group(2).lower()]
        return (*zahlen, 0, rang, int(m.group(3) or 0))
    return (*zahlen, 1, 0, 0)


def _abrufen(url: str = API, timeout: float = TIMEOUT) -> list:
    """Die eine Anfrage. Nur GET, nur öffentlich, ohne Daten und ohne Kennung."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Fakturafalter/{__version__}",
            "Accept": "application/vnd.github+json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – feste https-URL
        return json.loads(r.read(2_000_000).decode("utf-8"))


def _sichere_url(url: str) -> str:
    """Nur Links auf die Release-Seiten dieses Repositorys weitergeben, sonst die Übersicht."""
    url = str(url or "")
    return url if url.startswith(RELEASES + "/") else RELEASES


def auswerten(releases: list, vorab: bool = False, aktuell: str = __version__) -> Neu | None:
    """Neueste passende Version aus der API-Antwort; nur wenn sie neuer als ``aktuell`` ist."""
    beste: Neu | None = None
    beste_t: tuple = version_tupel(aktuell)
    for rel in releases if isinstance(releases, list) else []:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        if rel.get("prerelease") and not vorab:
            continue
        tag = str(rel.get("tag_name") or "")
        t = version_tupel(tag)
        if t and t > beste_t:
            beste_t = t
            beste = Neu(
                tag.lstrip("vV"), _sichere_url(rel.get("html_url")), bool(rel.get("prerelease"))
            )
    return beste


def jetzt(vorab: bool = False) -> tuple[bool, Neu | None]:
    """Einmal prüfen. -> (erreichbar, neuere Version oder None). Ohne Netz, bei Zeitüberschreitung oder
    unerwarteter Antwort: (False, None) – nur ein Debug-Eintrag im Log, nie eine Ausnahme."""
    try:
        neu = auswerten(_abrufen(), vorab)
    except Exception as e:  # noqa: BLE001 – darf nie stören
        log.debug("Updateprüfung nicht möglich: %s: %s", type(e).__name__, e)
        return False, None
    if neu is None:
        log.debug("Updateprüfung: Fakturafalter %s ist aktuell", __version__)
    else:
        log.info("Neue Version verfügbar: Fakturafalter %s – %s", neu.version, neu.url)
    return True, neu


def pruefen(vorab: bool = False) -> Neu | None:
    return jetzt(vorab)[1]


def im_hintergrund(vorab: bool = False, rueckruf=None) -> threading.Thread:
    """Prüfung im Daemon-Thread; ``rueckruf(erreichbar, neu_oder_None)`` aus diesem Thread (Oberfläche: per
    Signal weiterreichen). Blockiert nie den Aufrufer."""

    def los():
        erreichbar, neu = jetzt(vorab)
        if rueckruf is not None:
            try:
                rueckruf(erreichbar, neu)
            except Exception:  # noqa: BLE001
                log.debug("Updateprüfung: Rückruf fehlgeschlagen", exc_info=True)

    t = threading.Thread(target=los, name="fakturafalter-updatepruefung", daemon=True)
    t.start()
    return t
