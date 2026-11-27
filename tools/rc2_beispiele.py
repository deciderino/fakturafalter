# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Beispieldateien für 1.0.0-rc2 erzeugen (alle Daten fiktiv) nach beispiele/rc2/.

- rechnungen-export-fiktiv.xlsx: Excel-Mappe, Blatt „Export“ mit zwei Titelzeilen, Blatt „Notizen“;
  Spalte „Bestellnummer (BT-13)“ (BT-Nummer im Spaltennamen) und „Bauleiter“ (keinem Feld zugeordnet,
  im Layout als Platzhalter {Bauleiter} nutzbar)
- rechnungen-export-fiktiv.ods: dieselbe Tabelle, von LibreOffice Calc (soffice --headless) gespeichert
- profil-rc2-excel.yaml / profil-rc2-ods.yaml: Profile wie aus dem Assistenten
- layout-platzhalter-fiktiv.yaml: Layoutformat 2 mit Textfeld „Bestellung {BT-13} · Bauleiter {Bauleiter}“
- layout-alt-format1-fiktiv.yaml: altes Layout (Layoutformat 1, Stand 1.0.0-rc1) für den Ablehnungstest

Aufruf: PYTHONPATH=src python tools/rc2_beispiele.py  (braucht openpyxl und für die ODS LibreOffice)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import yaml

from fakturafalter import csv_einrichtung as ce
from fakturafalter import layout

ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "beispiele" / "rc2"

KOPF = ["Rechnungsnummer", "Rechnungsdatum", "Lieferdatum", "Kunde", "Straße", "PLZ", "Ort",
        "Bestellnummer (BT-13)", "Bauleiter", "Artikel", "Menge", "Einheit", "Einzelpreis", "USt"]
ZEILEN = [
    ["RE-2026-9101", date(2026, 11, 3), date(2026, 10, 30), "Beispiel Handel GmbH", "Beispielweg 5", "12345",
     "Musterstadt", "PO-77801", "Hans Beispiel", "Schraube M8 verzinkt", 500, "Stück", 0.12, 0.19],
    ["RE-2026-9101", date(2026, 11, 3), date(2026, 10, 30), "Beispiel Handel GmbH", "Beispielweg 5", "12345",
     "Musterstadt", "PO-77801", "Hans Beispiel", "Montage vor Ort", 2.5, "Stunde", 65.0, 0.19],
    ["RE-2026-9102", date(2026, 11, 4), date(2026, 11, 2), "Muster Bau KG", "Musterstraße 7", "01067",
     "Dresden", "", "", "Fachbuch Montage", 1, "Stück", 39.9, 0.07],
]


def xlsx(ziel: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(["Rechnungsexport November 2026 – Muster GmbH (fiktiv)"])
    ws.append([])
    ws.append(KOPF)
    for z in ZEILEN:
        ws.append(z)
        r = ws.max_row
        for sp in (2, 3):
            ws.cell(r, sp).number_format = "DD.MM.YYYY"
        ws.cell(r, 13).number_format = "#,##0.00 €"
        ws.cell(r, 14).number_format = "0%"
    wb.create_sheet("Notizen").append(["Nur Notizen, kein Export"])
    wb.active = 0
    wb.properties.creator = "Fakturafalter-Mitwirkende"
    wb.properties.created = wb.properties.modified = datetime(2026, 11, 27)
    wb.save(ziel)


def ods(quelle: Path, ziel: Path) -> None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise SystemExit("LibreOffice (soffice) fehlt – die ODS wird von LibreOffice gespeichert")
    with tempfile.TemporaryDirectory() as t:
        subprocess.run([soffice, f"-env:UserInstallation=file://{t}/profil", "--headless", "--convert-to", "ods",
                        "--outdir", t, str(quelle)], check=True, capture_output=True, timeout=180)
        shutil.move(Path(t) / (quelle.stem + ".ods"), ziel)


def profil(datei: Path, name: str) -> dict:
    fmt = ce.format_erkennen(datei)
    z = ce.spalten_vorschlagen(fmt.kopf, fmt.zeilen)
    assert z.get("BT-13") == "Bestellnummer (BT-13)", z
    assert "Bauleiter" not in z.values(), z
    p = ce.profil_bauen(name, datei, fmt, z, ce.steuer_vorschlag(ce.spalte(fmt, z["steuer"])),
                        ce.einheiten_vorschlag(ce.spalte(fmt, z["BT-130"])))
    p["beschreibung"] = f"Beispiel 1.0.0-rc2 (fiktiv): {p['beschreibung']}"
    return p


def platzhalter_layout() -> dict:
    v = layout.standard()
    v.seite1.felder.append(layout.Element("text", 20, 86, 100, 10, schrift=9, ebene=3, kennung="text1",
                                          text="Bestellung {BT-13} · Bauleiter {Bauleiter}"))
    assert not layout.pruefen(v)
    return v.als_dict()


def main() -> int:
    ZIEL.mkdir(parents=True, exist_ok=True)
    x = ZIEL / "rechnungen-export-fiktiv.xlsx"
    xlsx(x)
    ods(x, ZIEL / "rechnungen-export-fiktiv.ods")
    kopf = "# Fakturafalter 1.0.0-rc2 – Beispielprofil, alle Daten fiktiv (erzeugt mit tools/rc2_beispiele.py).\n"
    for n, d, name in (("profil-rc2-excel.yaml", x, "Beispiel Excel (rc2)"),
                       ("profil-rc2-ods.yaml", ZIEL / "rechnungen-export-fiktiv.ods", "Beispiel ODS (rc2)")):
        (ZIEL / n).write_text(kopf + yaml.safe_dump(profil(d, name), allow_unicode=True, sort_keys=False),
                              encoding="utf-8")
    (ZIEL / "layout-platzhalter-fiktiv.yaml").write_text(
        "# Layoutformat 2 (ab 1.0.0-rc2), fiktiv: Textfeld mit Platzhaltern {BT-13} und {Bauleiter}.\n"
        "# Einsetzen als Block „layout:“ in konfiguration.yaml.\n"
        + yaml.safe_dump({"layout": platzhalter_layout()}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    alt = subprocess.run(["git", "-C", str(ROOT), "show", "v1.0.0-rc1:beispiele/layout/layout-beispiel.yaml"],
                         check=True, capture_output=True, text=True).stdout
    (ZIEL / "layout-alt-format1-fiktiv.yaml").write_text(
        "# Altes Layout (Layoutformat 1, Stand 1.0.0-rc1), fiktiv – ab 1.0.0-rc2 wird es abgelehnt.\n"
        + "".join(z + "\n" for z in alt.splitlines() if not z.startswith("#")), encoding="utf-8")
    print("geschrieben:", *sorted(p.name for p in ZIEL.iterdir()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
