# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Start der Oberfläche:  fakturafalter [--config DATEI] [--minimiert]"""

from __future__ import annotations

import argparse
import logging
import sys
from importlib import resources
from pathlib import Path


def anwendung(argv: list[str] | None = None):
    from PySide6.QtGui import QFont, QFontDatabase, QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    app.setApplicationName("Fakturafalter")
    app.setOrganizationName("Fakturafalter")
    app.setDesktopFileName("fakturafalter")
    app.setQuitOnLastWindowClosed(False)  # Tray hält das Programm am Leben
    schriften = resources.files("fakturafalter") / "ressourcen" / "schriften"
    for ttf in schriften.iterdir():
        if ttf.name.endswith(".ttf"):
            QFontDatabase.addApplicationFont(str(ttf))
    app.setFont(QFont("Liberation Sans", 11))
    app.setWindowIcon(
        QIcon(str(resources.files("fakturafalter") / "ressourcen" / "fakturafalter.png"))
    )
    return app


def _orte_loggen(pfad: Path, w) -> None:
    """Wohin geschrieben wird (für Rückfragen bei „PermissionError“): Ordner, beschreibbar?, Admin-Rechte?"""
    import sys

    log = logging.getLogger("fakturafalter")
    admin = None
    if sys.platform == "win32":
        try:
            import ctypes

            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            pass
    log.info(
        "Programm %s, Arbeitsverzeichnis %s, Admin %s",
        Path(sys.executable).resolve().parent,
        Path.cwd(),
        admin,
    )
    k = getattr(w, "k", None)
    orte_ = {"Konfiguration": pfad.parent}
    if k is not None:
        orte_.update(
            {
                n: getattr(k, n)
                for n in ("eingang", "ausgang", "erledigt", "anlernen", "pruefen", "fehler")
                if getattr(k, n, None) is not None
            }
        )
    for name, o in orte_.items():
        log.info("Ordner %-13s %s (%s)", name, o, _ort_befund(Path(o)))


def _ort_befund(o: Path) -> str:
    """„beschreibbar“ nur für vorhandene Ordner prüfen. Ein noch nicht angelegter Ordner (z. B. „Pruefen\\Anlernen“
    vor der ersten Anlern-Rechnung) ist kein Fehler – er entsteht bei Bedarf, wenn der nächste vorhandene
    Ordner darüber beschreibbar ist (früher stand hier irreführend „NICHT beschreibbar“)."""
    import os

    if o.is_dir():
        return "beschreibbar" if os.access(o, os.W_OK) else "NICHT beschreibbar"
    oben = o.parent
    while not oben.exists() and oben != oben.parent:
        oben = oben.parent
    ok = os.access(oben, os.W_OK)
    return (
        "noch nicht angelegt – wird bei Bedarf erstellt"
        if ok
        else f"noch nicht angelegt, Ordner darüber ({oben}) NICHT beschreibbar"
    )


def starten(konfig: Path | None = None, minimiert: bool = False) -> int:
    from PySide6.QtWidgets import QSystemTrayIcon

    from .. import logdatei
    from . import orte
    from .einzel import Einzelinstanz
    from .hauptfenster import Hauptfenster

    app = anwendung()
    pfad = Path(konfig) if konfig else orte.standard_konfig()
    einzel = Einzelinstanz(pfad, app)
    if einzel.andere_wecken(zeigen=not minimiert):
        logging.getLogger("fakturafalter").info(
            "Fakturafalter läuft bereits – vorhandenes Fenster wird gezeigt"
        )
        return 0
    einzel.lauschen()
    datei = logdatei.einrichten(pfad.parent / "logs")
    logging.getLogger("fakturafalter").info(
        "Fakturafalter-Oberfläche gestartet (Konfiguration %s, Log %s)", pfad, datei
    )
    w = Hauptfenster(pfad)
    _orte_loggen(pfad, w)
    einzel.geweckt.connect(lambda zeigen: w.anzeigen() if zeigen else None)
    if minimiert or w.ui.get("minimiert_starten"):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            w.showMinimized()
    else:
        w.show()
        if not w.ui.get("eingerichtet") and w.einrichtung_fehlt():
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, w.einrichtung_oeffnen)
    try:
        return app.exec()
    finally:
        einzel.schliessen()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fakturafalter-gui")
    ap.add_argument("--config", "-c", type=Path)
    ap.add_argument("--minimiert", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    return starten(a.config, a.minimiert)


if __name__ == "__main__":
    sys.exit(main())
