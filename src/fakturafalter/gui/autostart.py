# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""„Mit dem System starten“ – nur für den angemeldeten Benutzer, ohne Adminrechte.
Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run  ·  Linux: $XDG_CONFIG_HOME/autostart/*.desktop"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = "Fakturafalter"
RUN_SCHLUESSEL = r"Software\Microsoft\Windows\CurrentVersion\Run"


def befehl(konfig: Path | None = None) -> list[str]:
    if os.environ.get("APPIMAGE"):
        b = [os.environ["APPIMAGE"]]
    elif getattr(sys, "frozen", False):
        b = [sys.executable]
    else:
        b = [sys.executable, "-m", "fakturafalter"]
    b.append("--minimiert")
    if konfig:
        b += ["--config", str(konfig)]
    return b


# ------------------------------------------------------------------------------------- Linux
def desktop_datei() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        / "autostart"
        / "fakturafalter.desktop"
    )


def _desktop_exec(b: list[str]) -> str:
    # Desktop-Entry-Spec: Argumente mit Leer-/Sonderzeichen in "" und \ " ` $ escapen
    def q(a: str) -> str:
        if a and all(ch.isalnum() or ch in "-_./=:" for ch in a):
            return a
        return (
            '"' + "".join("\\" + ch if ch in '"`$\\' else ch for ch in a).replace("%", "%%") + '"'
        )

    return " ".join(q(a) for a in b)


def _linux_setzen(an: bool, b: list[str]) -> None:
    p = desktop_datei()
    if not an:
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "[Desktop Entry]\nType=Application\nName=Fakturafalter\n"
        "Comment=PDF + CSV zu ZUGFeRD/XRechnung (lokal)\n"
        f"Exec={_desktop_exec(b)}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


# ----------------------------------------------------------------------------------- Windows
def _winreg():
    import winreg  # noqa: PLC0415 – nur unter Windows vorhanden

    return winreg


def _win_wert() -> str | None:
    wr = _winreg()
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_SCHLUESSEL, 0, wr.KEY_READ) as s:
            return wr.QueryValueEx(s, NAME)[0]
    except FileNotFoundError:
        return None


def _win_setzen(an: bool, b: list[str]) -> None:
    wr = _winreg()
    with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, RUN_SCHLUESSEL, 0, wr.KEY_SET_VALUE) as s:
        if an:
            wr.SetValueEx(s, NAME, 0, wr.REG_SZ, subprocess.list2cmdline(b))
        else:
            try:
                wr.DeleteValue(s, NAME)
            except FileNotFoundError:
                pass


# ------------------------------------------------------------------------------------- API
def ist_aktiv() -> bool:
    if sys.platform == "win32":
        return _win_wert() is not None
    return desktop_datei().exists()


def setzen(an: bool, konfig: Path | None = None) -> None:
    b = befehl(konfig)
    if sys.platform == "win32":
        _win_setzen(an, b)
    else:
        _linux_setzen(an, b)


def beschreibung() -> str:
    if sys.platform == "win32":
        return "HKCU\\" + RUN_SCHLUESSEL
    return str(desktop_datei())


__all__ = ["befehl", "ist_aktiv", "setzen", "beschreibung", "desktop_datei"]
