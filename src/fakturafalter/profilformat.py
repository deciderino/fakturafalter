# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Profilformat 2: Prüfung und Ablehnung älterer CSV-Profile (keine Migration)."""

from __future__ import annotations

from pathlib import Path

PROFILFORMAT = 2
ALTE_SCHLUESSEL = frozenset({"gesamt_kontrolle", "kaeufer_name_2", "kaeufer_name_3"})


class ProfilVeraltet(ValueError):
    """Altes oder unpassendes Profil – nicht einlesen, Datei unverändert lassen."""

    def __init__(
        self,
        profilname: str = "",
        gefunden: str | int | None = None,
        schluessel: str | None = None,
    ) -> None:
        self.profilname = (profilname or "").strip()
        self.gefunden = gefunden
        self.schluessel = schluessel
        super().__init__(self.meldung())

    def titel(self) -> str:
        return "Dieses Profil passt nicht mehr zu Fakturafalter 1.0"

    def meldung(self) -> str:
        name = f"„{self.profilname}“" if self.profilname else ""
        wer = f"Die Zuordnung {name} ".replace("  ", " ") if name else "Die Zuordnung "
        gefunden = self.gefunden
        if gefunden is None or gefunden == "":
            gefunden_txt = "ohne Profilformat"
        else:
            gefunden_txt = f"Profilformat {gefunden}"
        if self.schluessel:
            grund = (
                f"{wer}verwendet eine Bezeichnung, die Fakturafalter 1.0 nicht mehr kennt "
                f"({self.schluessel}); dieses Fakturafalter erwartet Profilformat {PROFILFORMAT}."
            )
        else:
            grund = (
                f"{wer}wurde mit einer älteren Version eingerichtet "
                f"({gefunden_txt}, dieses Fakturafalter erwartet Profilformat {PROFILFORMAT})."
            )
        return (
            f"{grund}\n\n"
            "Fakturafalter liest die Datei deshalb nicht weiter – damit keine Felder falsch "
            "zugeordnet werden.\n\n"
            "Was du tun kannst:\n\n"
            "• Die Zuordnung im Assistenten neu einrichten. Eine Beispiel-CSV aus deiner "
            "Warenwirtschaft (ERP) reicht.\n\n"
            "• Oder bei der Version 0.9.11 bleiben; dort funktionieren die bisherigen "
            "Profile weiter.\n\n"
            "Die alte Profildatei bleibt unverändert liegen."
        )


def _version_von(profil: dict) -> int | None:
    roh = profil.get("version")
    if roh is None or roh == "":
        return None
    try:
        return int(roh)
    except (TypeError, ValueError):
        return None


def _feld_schluessel(profil: dict) -> set[str]:
    aus: set[str] = set()
    felder = profil.get("felder") or {}
    if isinstance(felder, dict):
        for gruppe in felder.values():
            if isinstance(gruppe, dict):
                aus.update(str(k) for k in gruppe)
            elif isinstance(gruppe, str):
                aus.add(gruppe)
    for b in profil.get("bloecke") or []:
        if not isinstance(b, dict):
            continue
        bf = b.get("felder") or {}
        if isinstance(bf, dict):
            aus.update(str(k) for k in bf)
    # flache Zuordnung {feld: spalte}
    zu = profil.get("zuordnung") or {}
    if isinstance(zu, dict):
        aus.update(str(k) for k in zu)
    return aus


def pruefen(profil: dict, *, datei: Path | str | None = None) -> None:
    """Wirft ProfilVeraltet, wenn das Profil nicht Format 2 ist oder alte Schlüssel enthält.

    PDF-Vorlagen und andere Nicht-CSV-Definitionen ohne Feldzuordnung bleiben unberührt,
    solange sie keine alten Feldschlüssel tragen und nicht als CSV-Profil auftreten.
    """
    name = str(profil.get("profil") or profil.get("name") or "").strip()
    if not name and datei:
        name = Path(datei).stem
    schluessel = _feld_schluessel(profil)
    alt = sorted(schluessel & ALTE_SCHLUESSEL)
    if alt:
        raise ProfilVeraltet(name, _version_von(profil), alt[0])
    # CSV-Profile (Feldzuordnung oder Blockprofil) brauchen Format 2.
    ist_csv = bool(
        profil.get("felder")
        or profil.get("bloecke")
        or (profil.get("aufbau") or {}).get("art")
        or profil.get("datei")
    )
    if not ist_csv:
        return
    ver = _version_von(profil)
    if ver is None or ver < PROFILFORMAT:
        raise ProfilVeraltet(name, ver if ver is not None else "")
