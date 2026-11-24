# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
import io

import pikepdf
import pytest

from fakturafalter import pdfa, validierung
from fakturafalter.pipeline import verarbeiten


def test_struktur_pdfa3(konfig, eingang):
    verarbeiten(eingang("druckauftrag-wawi.pdf", "variante-a_positionen_utf8.csv"), konfig)
    for nr in ("RE-2026-0101", "RE-2026-0103"):
        with pikepdf.open(konfig.ausgang / f"{nr}_zugferd.pdf") as pdf:
            assert pdf.pdf_version == "1.7"
            xmp = bytes(pdf.Root.Metadata.read_bytes()).decode()
            assert (
                "<pdfaid:part>3</pdfaid:part>" in xmp
                and "<pdfaid:conformance>B</pdfaid:conformance>" in xmp
            )
            assert "<fx:ConformanceLevel>EN 16931</fx:ConformanceLevel>" in xmp
            assert pdf.Root.OutputIntents[0].S == "/GTS_PDFA1"
            assert pdf.Root.AF[0].AFRelationship == "/Alternative"
            for page in pdf.pages:
                for _, f in page.Resources.Font.items():
                    d = f.get("/FontDescriptor") or f.DescendantFonts[0].FontDescriptor
                    assert "/FontFile2" in d or "/FontFile" in d or "/FontFile3" in d, f.BaseFont


def test_unbekannte_schrift_nicht_reparierbar():
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.pages[0].Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(
            F1=pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name("/Frutiger"),
            )
        )
    )
    buf = io.BytesIO()
    pdf.save(buf)
    with pytest.raises(pdfa.NichtReparierbar):
        pdfa.zugferd_pdf(buf.getvalue(), b"<x/>", titel="t", autor="a")


werkzeuge = validierung.verfuegbar()


@pytest.mark.skipif(not all(werkzeuge.values()), reason="Java/KoSIT/Mustang nicht vorhanden")
def test_referenzvalidierung(konfig, eingang):
    verarbeiten(eingang("druckauftrag-wawi.pdf", "variante-b_wawi_cp1252.csv"), konfig)
    erg = validierung.pruefen(
        sorted(konfig.ausgang.glob("*_zugferd.pdf")) + sorted(konfig.ausgang.glob("*.xml"))
    )
    assert erg and all(e.gueltig and not e.fehler and not e.warnungen for e in erg), [
        e.zeile() for e in erg
    ]


def _courier_pdf(inhalt: bytes) -> bytes:
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    seite = pdf.pages[0]
    seite.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(
            F1=pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.Font,
                    Subtype=pikepdf.Name.Type1,
                    BaseFont=pikepdf.Name("/Courier"),
                    Encoding=pikepdf.Name.WinAnsiEncoding,
                )
            )
        )
    )
    seite.Contents = pdf.make_stream(inhalt)
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_steuerzeichen_ohne_glyphe_entfernt():
    """Warenwirtschafts-Druck mit „\\012“ am Zeilenende (Courier, nicht eingebettet): Der Code hat in der
    eingebetteten Liberation-Schrift keine Glyphe -> veraPDF 6.2.11.8 (.notdef). Wird aus dem Text entfernt."""
    roh = _courier_pdf(
        b"BT /F1 10 Tf 1 0 0 1 30 800 Tm [ ( Menge\\012) ] TJ 1 0 0 1 30 780 Tm (Summe\\012) Tj"
        b" (\\201x) ' ET"
    )
    out = pdfa.zugferd_pdf(roh, b"<x/>", titel="t", autor="a")
    with pikepdf.open(io.BytesIO(out)) as pdf:
        texte = [
            bytes(o)
            for ops, _ in pikepdf.parse_content_stream(pdf.pages[0])
            for x in ops
            for o in (x if isinstance(x, pikepdf.Array) else [x])
            if isinstance(o, pikepdf.String)
        ]
    assert texte == [b" Menge", b"Summe", b"x"]


@pytest.mark.skipif(not all(werkzeuge.values()), reason="Java/KoSIT/Mustang nicht vorhanden")
def test_steuerzeichen_pdfa_konform(tmp_path):
    roh = _courier_pdf(b"BT /F1 10 Tf 1 0 0 1 30 800 Tm [ ( Menge\\012) ] TJ ET")
    d = tmp_path / "x.pdf"
    d.write_bytes(pdfa.zugferd_pdf(roh, b"<x/>", titel="t", autor="a"))
    (e,) = validierung.mustang_stapel([d])
    assert "konform=true" in e.info, e.fehler
