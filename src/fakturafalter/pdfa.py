# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""PDF/A-3b herstellen und die XML-Rechnung einbetten (ZUGFeRD/Factur-X).

Nur lizenzfreundliche Bausteine: pikepdf (MPL-2.0, auf qpdf Apache-2.0), fontTools (MIT),
Liberation-Schriften (SIL OFL 1.1), sRGB-Profil aus LittleCMS (MIT, über Pillow erzeugt).
Kein Ghostscript, kein PyMuPDF.

Vorgehen für ein Eingangs-PDF (Druck):
  1. Seiten der jeweiligen Rechnung herauslösen.
  2. Prüfen, was PDF/A-3 verbietet (Verschlüsselung, JavaScript, Aktionen, Multimedia ...).
  3. Nicht eingebettete Standardschriften (Helvetica/Courier/Times + Varianten) durch
     metrikgleiche Liberation-Schriften ersetzen und eingebettet (Teilmenge) ablegen.
     Andere nicht eingebettete Schriften -> NichtReparierbar (dann Sichtteil neu aufbauen).
  4. sRGB-OutputIntent, XMP (pdfaid 3/B + Factur-X-Erweiterungsschema), passendes Info-Dictionary.
  5. factur-x.xml als Associated File (/AF, AFRelationship) einbetten.
"""

from __future__ import annotations

import hashlib
import io
import logging
import random
import string
from datetime import datetime, timezone
from importlib import resources
from xml.sax.saxutils import escape

import pikepdf
from fontTools import subset as ft_subset
from fontTools.ttLib import TTFont
from pikepdf import Array, Dictionary, Name, Pdf, Stream, String

from . import __version__

logging.getLogger("fontTools").setLevel(logging.ERROR)


class NichtReparierbar(Exception):
    """Das Eingangs-PDF lässt sich nicht verlustfrei nach PDF/A-3 bringen."""


RES = resources.files("fakturafalter") / "ressourcen"
STANDARD14 = {
    "Helvetica": "LiberationSans-Regular",
    "Helvetica-Bold": "LiberationSans-Bold",
    "Helvetica-Oblique": "LiberationSans-Italic",
    "Helvetica-BoldOblique": "LiberationSans-BoldItalic",
    "Arial": "LiberationSans-Regular",
    "Arial,Bold": "LiberationSans-Bold",
    "ArialMT": "LiberationSans-Regular",
    "Courier": "LiberationMono-Regular",
    "Courier-Bold": "LiberationMono-Bold",
    "Courier-Oblique": "LiberationMono-Italic",
    "Courier-BoldOblique": "LiberationMono-BoldItalic",
    "CourierNew": "LiberationMono-Regular",
    "CourierNewPSMT": "LiberationMono-Regular",
    "Times-Roman": "LiberationSerif-Regular",
    "Times-Bold": "LiberationSerif-Bold",
    "Times-Italic": "LiberationSerif-Italic",
    "Times-BoldItalic": "LiberationSerif-BoldItalic",
    "TimesNewRoman": "LiberationSerif-Regular",
    "TimesNewRomanPSMT": "LiberationSerif-Regular",
}
VERBOTENE_ANNOTS = {"/Sound", "/Movie", "/Screen", "/3D", "/RichMedia", "/FileAttachment"}


# ---------------------------------------------------------------- Schriften
def _tag(seed: str) -> str:
    rnd = random.Random(seed)
    return "".join(rnd.choice(string.ascii_uppercase) for _ in range(6))


_font_cache: dict[str, tuple] = {}


def _liberation(name: str):
    """-> (FontFile2-Bytes, Widths[32..255], Descriptor-Werte, PostScript-Name, Codes ohne Glyphe)."""
    if name in _font_cache:
        return _font_cache[name]
    pfad = RES / "schriften" / f"{name}.ttf"
    tt = TTFont(str(pfad))
    upm = tt["head"].unitsPerEm
    cmap = tt.getBestCmap()
    hmtx = tt["hmtx"]
    skala = 1000 / upm
    codes = range(32, 256)
    unis = {}
    for c in codes:
        try:
            u = ord(bytes([c]).decode("cp1252"))
        except UnicodeDecodeError:
            continue
        if c == 0xA0:
            u = 0x20 if 0xA0 not in cmap else 0xA0
        unis[c] = u
    widths = []
    for c in codes:
        g = cmap.get(unis.get(c, -1), ".notdef")
        widths.append(round(hmtx[g][0] * skala))
    os2, head, post = tt["OS/2"], tt["head"], tt["post"]
    desc = {
        "Ascent": round(os2.sTypoAscender * skala),
        "Descent": round(os2.sTypoDescender * skala),
        "CapHeight": round(getattr(os2, "sCapHeight", os2.sTypoAscender) * skala),
        "FontBBox": [round(v * skala) for v in (head.xMin, head.yMin, head.xMax, head.yMax)],
        "ItalicAngle": float(post.italicAngle),
        "StemV": 80,
        "Flags": 32
        | (1 if post.isFixedPitch else 0)
        | (2 if "Serif" in name else 0)
        | (64 if "Italic" in name else 0),
    }
    psname = tt["name"].getDebugName(6) or name.replace("-Regular", "")
    # Codes ohne Glyphe (Steuerzeichen 0–31, in Windows-1252 nicht belegt, nicht in der Schrift): PDF/A-3
    # verbietet Verweise auf .notdef (ISO 19005-3, 6.2.11.8) -> werden aus den Inhaltsströmen entfernt.
    fehlend = frozenset(c for c in range(256) if c < 32 or c not in unis or unis[c] not in cmap)
    # Teilmenge: alle Zeichen aus Windows-1252 (WinAnsiEncoding)
    opts = ft_subset.Options()
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = True
    opts.hinting = False
    opts.layout_features = []
    sub = ft_subset.Subsetter(opts)
    sub.populate(unicodes=set(unis.values()))
    sub.subset(tt)
    buf = io.BytesIO()
    tt.save(buf)
    _font_cache[name] = (buf.getvalue(), widths, desc, psname, fehlend)
    return _font_cache[name]


def _schrift_ersetzen(pdf: Pdf, font: Dictionary) -> frozenset[int]:
    """Standardschrift -> eingebettete Liberation-Teilmenge. -> Zeichencodes, für die es keine Glyphe gibt."""
    base = str(font.get("/BaseFont", "")).lstrip("/")
    ziel = STANDARD14.get(base) or STANDARD14.get(base.split("+")[-1])
    enc = font.get("/Encoding")
    if not ziel:
        raise NichtReparierbar(
            f"Schrift „{base}“ ist nicht eingebettet und hat keinen freien Ersatz"
        )
    if enc is not None and not (isinstance(enc, Name) and enc == Name.WinAnsiEncoding):
        raise NichtReparierbar(f"Schrift „{base}“: Kodierung {enc!r} wird (noch) nicht unterstützt")
    data, widths, desc, psname, fehlend = _liberation(ziel)
    fname = Name("/" + _tag(ziel) + "+" + psname)
    ff = Stream(pdf, data)
    ff["/Length1"] = len(data)
    fd = pdf.make_indirect(
        Dictionary(
            Type=Name.FontDescriptor,
            FontName=fname,
            Flags=desc["Flags"],
            FontBBox=Array(desc["FontBBox"]),
            ItalicAngle=desc["ItalicAngle"],
            Ascent=desc["Ascent"],
            Descent=desc["Descent"],
            CapHeight=desc["CapHeight"],
            StemV=desc["StemV"],
            FontFile2=pdf.make_indirect(ff),
        )
    )
    for k in list(font.keys()):
        if k not in ("/Type", "/Name"):
            del font[k]
    font.Subtype = Name.TrueType
    font.BaseFont = fname
    font.FirstChar = 32
    font.LastChar = 255
    font.Widths = Array(widths)
    font.Encoding = Name.WinAnsiEncoding
    font.FontDescriptor = fd
    return fehlend


def _ist_eingebettet(font: Dictionary) -> bool:
    st = font.get("/Subtype")
    if st == Name.Type0:
        desc = font.DescendantFonts[0].get("/FontDescriptor")
    elif st == Name.Type3:
        return True
    else:
        desc = font.get("/FontDescriptor")
    return desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def _ressourcen_durchlaufen(
    pdf: Pdf, res: Dictionary, gesehen: set, ersetzt: dict[str, frozenset[int]]
) -> None:
    if res is None:
        return
    for _, f in (res.get("/Font") or {}).items():
        if f.objgen in gesehen and f.objgen != (0, 0):
            continue
        gesehen.add(f.objgen)
        if not _ist_eingebettet(f):
            ersetzt[str(f.BaseFont)] = _schrift_ersetzen(pdf, f)
    for _, x in (res.get("/XObject") or {}).items():
        if x.get("/Subtype") == Name.Form and x.objgen not in gesehen:
            gesehen.add(x.objgen)
            _ressourcen_durchlaufen(pdf, x.get("/Resources"), gesehen, ersetzt)


_TEXT_OPS = {"Tj", "TJ", "'", '"'}


def _ohne_notdef(
    ops: list, res: Dictionary | None, ersetzt: dict[str, frozenset[int]], formen: set
) -> list | None:
    """Zeichen ohne Glyphe aus Textoperatoren in ersetzten Schriften entfernen (z. B. ``\\012`` am Zeilenende,
    wie manche Warenwirtschaften drucken). Die Standardschrift hatte dafür ebenfalls keine Glyphe und Breite 0,
    das Schriftbild bleibt gleich. -> geänderte Operatorliste oder None (nichts geändert)."""
    fonts = (res or {}).get("/Font") or {}
    fehlend: frozenset[int] = frozenset()
    geaendert = False

    def saeubern(x):
        nonlocal geaendert
        if isinstance(x, String):
            b = bytes(x)
            neu = bytes(c for c in b if c not in fehlend)
            if neu != b:
                geaendert = True
                return String(neu)
        return x

    aus = []
    for operanden, op in ops:
        o = str(op)
        if o == "Tf" and operanden:
            f = fonts.get(str(operanden[0]))
            fehlend = (
                ersetzt.get(str(f.get("/BaseFont", ""))) or frozenset()
                if f is not None
                else frozenset()
            )
        elif o in _TEXT_OPS and fehlend:
            operanden = [
                Array([saeubern(e) for e in x]) if isinstance(x, Array) else saeubern(x)
                for x in operanden
            ]
        elif o == "Do" and operanden:  # Formular-XObjects mit eigenen Inhalten
            x = ((res or {}).get("/XObject") or {}).get(str(operanden[0]))
            if x is not None and x.get("/Subtype") == Name.Form and x.objgen not in formen:
                formen.add(x.objgen)
                neu = _ohne_notdef(
                    pikepdf.parse_content_stream(x), x.get("/Resources") or res, ersetzt, formen
                )
                if neu is not None:
                    x.write(pikepdf.unparse_content_stream(neu))
        aus.append((operanden, op))
    return aus if geaendert else None


def schriften_einbetten(pdf: Pdf) -> None:
    gesehen: set = set()
    ersetzt: dict[str, frozenset[int]] = {}
    for page in pdf.pages:
        _ressourcen_durchlaufen(pdf, page.obj.get("/Resources"), gesehen, ersetzt)
    if not any(ersetzt.values()):
        return
    formen: set = set()
    for page in pdf.pages:
        neu = _ohne_notdef(
            pikepdf.parse_content_stream(page), page.obj.get("/Resources"), ersetzt, formen
        )
        if neu is not None:
            page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(neu))


# ---------------------------------------------------------------- Prüfen / Bereinigen
def bereinigen(pdf: Pdf) -> None:
    if pdf.is_encrypted:
        raise NichtReparierbar("PDF ist verschlüsselt")
    root = pdf.Root
    for k in (
        "/OpenAction",
        "/AA",
        "/AcroForm",
        "/OCProperties",
        "/Names",
        "/AF",
        "/Metadata",
        "/Perms",
        "/Collection",
    ):
        if k == "/AcroForm" and k in root:
            raise NichtReparierbar("PDF enthält Formularfelder")
        if k in root:
            del root[k]
    for page in pdf.pages:
        p = page.obj
        for k in ("/AA",):
            if k in p:
                del p[k]
        if "/Group" in p and p.Group.get("/S") == Name.Transparency and "/CS" not in p.Group:
            p.Group.CS = Name.DeviceRGB
        for a in list(p.get("/Annots") or []):
            if (
                a.get("/Subtype") in VERBOTENE_ANNOTS
                or "/A" in a
                and a.A.get("/S") in (Name.JavaScript, Name.Launch)
            ):
                raise NichtReparierbar(f"Annotation {a.get('/Subtype')} nicht erlaubt")
            a.F = 4  # Print
        # Rasterbilder mit Alternativen / Interpolation
        for _, x in (p.get("/Resources", {}).get("/XObject") or {}).items():
            if x.get("/Subtype") == Name.Image:
                for k in ("/Alternates", "/OPI"):
                    if k in x:
                        del x[k]
                if x.get("/Interpolate"):
                    x.Interpolate = False


# ---------------------------------------------------------------- Metadaten
def _pdf_datum(dt: datetime) -> str:
    off = dt.utcoffset()
    m = int(off.total_seconds() // 60) if off else 0
    sign = "+" if m >= 0 else "-"
    return dt.strftime("D:%Y%m%d%H%M%S") + f"{sign}{abs(m) // 60:02d}'{abs(m) % 60:02d}'"


def _xmp(
    titel: str, autor: str, beschreibung: str, jetzt: datetime, dateiname: str, stufe: str
) -> bytes:
    iso = jetzt.isoformat(timespec="seconds")
    e = escape
    return f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>3</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:format>application/pdf</dc:format>
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{e(titel)}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{e(autor)}</rdf:li></rdf:Seq></dc:creator>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{e(beschreibung)}</rdf:li></rdf:Alt></dc:description>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdf:Producer>fakturafalter {__version__}</pdf:Producer>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:CreatorTool>fakturafalter {__version__}</xmp:CreatorTool>
   <xmp:CreateDate>{iso}</xmp:CreateDate>
   <xmp:ModifyDate>{iso}</xmp:ModifyDate>
   <xmp:MetadataDate>{iso}</xmp:MetadataDate>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/" xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#" xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
   <pdfaExtension:schemas>
    <rdf:Bag>
     <rdf:li rdf:parseType="Resource">
      <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
      <pdfaSchema:namespaceURI>urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#</pdfaSchema:namespaceURI>
      <pdfaSchema:prefix>fx</pdfaSchema:prefix>
      <pdfaSchema:property>
       <rdf:Seq>
        <rdf:li rdf:parseType="Resource"><pdfaProperty:name>DocumentFileName</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The name of the embedded XML document</pdfaProperty:description></rdf:li>
        <rdf:li rdf:parseType="Resource"><pdfaProperty:name>DocumentType</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The type of the hybrid document in capital letters, e.g. INVOICE or ORDER</pdfaProperty:description></rdf:li>
        <rdf:li rdf:parseType="Resource"><pdfaProperty:name>Version</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The actual version of the standard applying to the embedded XML document</pdfaProperty:description></rdf:li>
        <rdf:li rdf:parseType="Resource"><pdfaProperty:name>ConformanceLevel</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The conformance level of the embedded XML document</pdfaProperty:description></rdf:li>
       </rdf:Seq>
      </pdfaSchema:property>
     </rdf:li>
    </rdf:Bag>
   </pdfaExtension:schemas>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">
   <fx:DocumentType>INVOICE</fx:DocumentType>
   <fx:DocumentFileName>{e(dateiname)}</fx:DocumentFileName>
   <fx:Version>1.0</fx:Version>
   <fx:ConformanceLevel>{e(stufe)}</fx:ConformanceLevel>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>""".encode("utf-8")


def _output_intent(pdf: Pdf) -> None:
    icc = (RES / "sRGB.icc").read_bytes()
    prof = Stream(pdf, icc)
    prof["/N"] = 3
    oi = Dictionary(
        Type=Name.OutputIntent,
        S=Name.GTS_PDFA1,
        OutputConditionIdentifier=String("sRGB IEC61966-2.1"),
        Info=String("sRGB IEC61966-2.1"),
        RegistryName=String("http://www.color.org"),
        DestOutputProfile=pdf.make_indirect(prof),
    )
    pdf.Root.OutputIntents = Array([pdf.make_indirect(oi)])


def _anhang(pdf: Pdf, xml: bytes, dateiname: str, beziehung: str, jetzt: datetime) -> None:
    ef = Stream(pdf, xml)
    ef.Type = Name.EmbeddedFile
    ef.Subtype = Name("/text/xml")
    ef.Params = Dictionary(
        ModDate=String(_pdf_datum(jetzt)),
        CreationDate=String(_pdf_datum(jetzt)),
        Size=len(xml),
        CheckSum=String(hashlib.md5(xml).digest()),
    )
    ef_ref = pdf.make_indirect(ef)
    fs = pdf.make_indirect(
        Dictionary(
            Type=Name.Filespec,
            F=String(dateiname),
            UF=String(dateiname),
            Desc=String("Factur-X/ZUGFeRD Rechnung"),
            AFRelationship=Name("/" + beziehung),
            EF=Dictionary(F=ef_ref, UF=ef_ref),
        )
    )
    pdf.Root.Names = Dictionary(EmbeddedFiles=Dictionary(Names=Array([String(dateiname), fs])))
    pdf.Root.AF = Array([fs])


def zugferd_pdf(
    sicht: bytes | Pdf,
    xml: bytes,
    *,
    titel: str,
    autor: str,
    beschreibung: str = "",
    seiten: list[int] | None = None,
    dateiname: str = "factur-x.xml",
    stufe: str = "EN 16931",
    beziehung: str = "Alternative",
    jetzt: datetime | None = None,
) -> bytes:
    """Sicht-PDF (+ Seitenauswahl) + XML -> PDF/A-3b-Bytes mit eingebetteter Rechnung."""
    jetzt = (jetzt or datetime.now(timezone.utc).astimezone()).replace(microsecond=0)
    quelle = sicht if isinstance(sicht, Pdf) else Pdf.open(io.BytesIO(sicht))
    if seiten is not None:
        pdf = Pdf.new()
        for i in seiten:
            pdf.pages.append(quelle.pages[i])
    else:
        pdf = quelle
    bereinigen(pdf)
    schriften_einbetten(pdf)
    _output_intent(pdf)
    pdf.Root.Metadata = pdf.make_indirect(
        Stream(pdf, _xmp(titel, autor, beschreibung, jetzt, dateiname, stufe))
    )
    pdf.Root.Metadata.Type = Name.Metadata
    pdf.Root.Metadata.Subtype = Name.XML
    d = _pdf_datum(jetzt)
    pdf.trailer.Info = pdf.make_indirect(
        Dictionary(
            Title=String(titel),
            Author=String(autor),
            Subject=String(beschreibung),
            Producer=String(f"fakturafalter {__version__}"),
            Creator=String(f"fakturafalter {__version__}"),
            CreationDate=String(d),
            ModDate=String(d),
        )
    )
    _anhang(pdf, xml, dateiname, beziehung, jetzt)
    if "/MarkInfo" not in pdf.Root:
        pass
    out = io.BytesIO()
    pdf.save(
        out,
        min_version="1.7",
        fix_metadata_version=False,
        compress_streams=True,
        object_stream_mode=pikepdf.ObjectStreamMode.preserve,
        deterministic_id=True,
    )
    return out.getvalue()
