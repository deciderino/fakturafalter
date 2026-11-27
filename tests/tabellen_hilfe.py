# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Fiktive Excel-/ODS-Dateien für Tests (rc2). Keine echten Daten."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

KOPF = ["Rechnungsnummer", "Rechnungsdatum", "Kunde", "Artikel", "Menge", "Einheit", "Einzelpreis", "USt", "Straße", "PLZ", "Ort", "Lieferdatum"]
ZEILEN = [
    ["RE-2026-9001", date(2026, 11, 3), "Beispiel Handel GmbH", "Schraube M8", 100, "Stück", 0.1 + 0.2, 0.19, "Beispielweg 1", 10115, "Berlin", date(2026, 10, 30)],
    ["RE-2026-9001", date(2026, 11, 3), "Beispiel Handel GmbH", "Montage", 2.5, "Stunde", 19.99, 0.19, "Beispielweg 1", 10115, "Berlin", date(2026, 10, 30)],
    ["RE-2026-9002", date(2026, 11, 4), "Muster Bau KG", "Fachbuch", 1, "Stück", 24.9, 0.07, "Musterstraße 5", "01067", "Dresden", date(2026, 11, 2)],
]


def xlsx_schreiben(ziel: Path, titelzeilen: int = 2, zweites_blatt: bool = True) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    if titelzeilen:
        ws.append(["Rechnungsexport November 2026 (fiktiv)"])
        for _ in range(titelzeilen - 1):
            ws.append([])
    ws.append(KOPF)
    for z in ZEILEN:
        ws.append(z)
        r = ws.max_row
        ws.cell(r, 2).number_format = "DD.MM.YYYY"
        ws.cell(r, 7).number_format = "#,##0.00 €"
        ws.cell(r, 8).number_format = "0%"
        ws.cell(r, 12).number_format = "DD.MM.YYYY"
    if zweites_blatt:
        ws2 = wb.create_sheet("Notizen")
        ws2.append(["nur Text", "kein Export"])
    wb.active = 0
    wb.save(ziel)
    return ziel


def _ods_zelle(v) -> str:
    if v is None:
        return "<table:table-cell/>"
    if isinstance(v, date):
        return (f'<table:table-cell office:value-type="date" office:date-value="{v.isoformat()}">'
                f"<text:p>{v:%d.%m.%Y}</text:p></table:table-cell>")
    if isinstance(v, tuple) and v[0] == "prozent":
        return (f'<table:table-cell office:value-type="percentage" office:value="{v[1]}">'
                f"<text:p>{v[1]}</text:p></table:table-cell>")
    if isinstance(v, tuple) and v[0] == "waehrung":
        return (f'<table:table-cell office:value-type="currency" office:currency="EUR" office:value="{v[1]}">'
                f"<text:p>{v[1]} €</text:p></table:table-cell>")
    if isinstance(v, (int, float)):
        return f'<table:table-cell office:value-type="float" office:value="{v}"><text:p>{v}</text:p></table:table-cell>'
    t = escape(str(v)).replace("  ", '<text:s text:c="2"/>')
    return f'<table:table-cell office:value-type="string"><text:p>{t}</text:p></table:table-cell>'


def ods_schreiben(ziel: Path) -> Path:
    zeilen = [["Rechnungsexport (fiktiv)"], [], KOPF]
    for z in ZEILEN:
        z = list(z)
        z[6] = ("waehrung", "0.3" if z[6] == 0.1 + 0.2 else str(z[6]))
        z[7] = ("prozent", str(z[7]))
        zeilen.append(z)
    xml_zeilen = []
    for z in zeilen:
        if not z:
            xml_zeilen.append('<table:table-row table:number-rows-repeated="1"><table:table-cell table:number-columns-repeated="8"/></table:table-row>')
            continue
        zellen = "".join(_ods_zelle(v) for v in z)
        zellen += '<table:table-cell table:number-columns-repeated="1016"/>'
        xml_zeilen.append(f"<table:table-row>{zellen}</table:table-row>")
    # wie LibreOffice: riesige leere Restzeile
    xml_zeilen.append('<table:table-row table:number-rows-repeated="1048570"><table:table-cell table:number-columns-repeated="1024"/></table:table-row>')
    inhalt = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.3">'
        "<office:body><office:spreadsheet>"
        f'<table:table table:name="Export">{"".join(xml_zeilen)}</table:table>'
        '<table:table table:name="Leer"><table:table-row><table:table-cell/></table:table-row></table:table>'
        "</office:spreadsheet></office:body></office:document-content>"
    )
    with zipfile.ZipFile(ziel, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet", compress_type=zipfile.ZIP_STORED)
        z.writestr("content.xml", inhalt)
        z.writestr("META-INF/manifest.xml", '<?xml version="1.0"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>')
    return ziel
