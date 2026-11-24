# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Lokale Prüfung nach Erstellung: gültig -> Ausgang, ungültig -> Fehlerordner mit deutscher Begründung."""

from pathlib import Path

import pikepdf
import pytest

from fakturafalter import pipeline, validierung
from fakturafalter.gui import daten

braucht_werkzeuge = pytest.mark.skipif(
    not all(validierung.verfuegbar().values()),
    reason="Prüfwerkzeuge (Java, Mustang, KoSIT) nicht gefunden",
)


def test_ohne_werkzeuge_nicht_geprueft(konfig, eingang):
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    ok = [e for e in lauf.ergebnisse if e.status == "ok"]
    assert ok and all(e.pruefung == "nicht geprüft" for e in ok)
    assert all(Path(d).parent == konfig.ausgang for e in ok for d in e.dateien)
    assert {e.pruefung for e in daten.protokoll(konfig, 100)} == {"nicht geprüft"}


def test_pruefung_aus(konfig, eingang, monkeypatch):
    monkeypatch.setattr(validierung, "bereit", lambda: True)
    monkeypatch.setattr(validierung, "pruefen", lambda d: pytest.fail("darf nicht laufen"))
    konfig.nachpruefen = False
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    assert all(e.pruefung == "" for e in lauf.ergebnisse)


def test_option_aus_konfiguration(tmp_path):
    import shutil

    import yaml

    from fakturafalter.konfig import lade_konfig

    b = Path(shutil.copytree(Path(__file__).resolve().parent.parent / "beispiele", tmp_path / "b"))
    assert lade_konfig(b / "konfiguration.yaml").nachpruefen is True
    d = yaml.safe_load((b / "konfiguration.yaml").read_text(encoding="utf-8"))
    d["optionen"]["nach_erstellung_pruefen"] = False
    (b / "konfiguration.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    assert lade_konfig(b / "konfiguration.yaml").nachpruefen is False


def test_technischer_fehler_bleibt_im_ausgang(konfig, eingang, monkeypatch):
    monkeypatch.setattr(validierung, "bereit", lambda: True)
    monkeypatch.setattr(
        validierung,
        "pruefen",
        lambda ds: [
            validierung.Pruefergebnis(
                str(d), "Mustang", False, ["OutOfMemoryError"], technisch=True
            )
            for d in ds
        ],
    )
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    ok = [e for e in lauf.ergebnisse if e.dateien]
    assert ok and all(e.status == "ok" and e.pruefung == "nicht geprüft" for e in ok)


def test_gruende_deutsch():
    e = validierung.Pruefergebnis(
        "x.pdf",
        "KoSIT",
        False,
        ["BR-CO-15 [BR-CO-15]-Invoice total amount with VAT ...", "BR-DE-1 Zahlung fehlt"],
        info="[EN16931] (eingebettete XML)",
    )
    g = validierung.gruende(e)
    assert g[0].startswith("Prüfung der Rechnungsdaten nach EN 16931 (KoSIT) nicht bestanden")
    assert "Rechenregel EN 16931 BR-CO-15: Bruttobetrag" in g[1]
    assert "XRechnung-Regel BR-DE-1" in g[2]
    m = validierung.gruende(
        validierung.Pruefergebnis(
            "x.pdf", "Mustang", False, ["1 x"], info="[PDF/A 3B konform=false, XML-Profil ]"
        )
    )
    assert m[0].startswith("PDF/A-Prüfung (veraPDF) nicht bestanden")
    assert "nicht PDF/A-3-konform" in m[0]


# ------------------------------------------------------------------ echte Werkzeuge (eine JVM je Stapel)
@pytest.mark.validierung
@braucht_werkzeuge
def test_gueltiger_stapel(konfig, eingang):
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    ok = [e for e in lauf.ergebnisse if e.dateien]
    assert ok and all(e.status == "ok" and e.pruefung == "gültig" for e in ok), [
        (e.nummer, e.hinweise) for e in lauf.ergebnisse
    ]
    assert all(Path(d).parent == konfig.ausgang for e in ok for d in e.dateien)
    assert {e.pruefung for e in daten.protokoll(konfig, 100) if e.status == "ok"} == {"gültig"}


@pytest.mark.validierung
@braucht_werkzeuge
def test_ungueltige_ausgabe_in_fehlerordner(konfig, eingang, monkeypatch):
    """Absichtlich kaputte Ausgabe: Gesamtbetrag in der eingebetteten XML verfälscht."""
    echt = pipeline.entwurf_erzeugen  # ab 0.9.6: erzeugt im System-Temp, geprüft vor dem Ausgang

    def kaputt(r, k, ziel=None, bei_pdfa=None):
        ent = echt(r, k, ziel, bei_pdfa)
        for d in ent.dateien:
            if d.suffix == ".pdf":
                with pikepdf.open(d, allow_overwriting_input=True) as pdf:
                    name, fs = next(iter(pdf.attachments.items()))
                    xml = fs.get_file().read_bytes()
                    xml = xml.replace(b"<ram:DuePayableAmount>", b"<ram:DuePayableAmount>9", 1)
                    del pdf.attachments[name]
                    pdf.attachments[name] = pikepdf.AttachedFileSpec(
                        pdf, xml, mime_type="text/xml", relationship=pikepdf.Name.Alternative
                    )
                    pdf.save(d)
        return ent

    monkeypatch.setattr(pipeline, "entwurf_erzeugen", kaputt)
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    schlecht = [e for e in lauf.ergebnisse if e.pruefung == "ungültig"]
    assert schlecht and all(e.status == "fehler" for e in schlecht)
    assert not list(konfig.ausgang.glob("*.pdf"))
    assert list(konfig.fehler.glob("*.pdf"))
    bericht = "\n".join(p.read_text(encoding="utf-8") for p in konfig.fehler.glob("*_fehler.txt"))
    assert "lokale Prüfung nicht bestanden" in bericht
    assert "EN 16931" in bericht


def test_mustang_meldung_und_doppelte():
    roh = "4 [BR-CO-16]-Amount due for payment (BT-115) = ... [ID BR-CO-16] from /xslt/ZF_250/FACTUR-X_EN16931.xslt)"
    assert validierung._regel(roh).startswith("Rechenregel EN 16931 BR-CO-16: Zahlbetrag (BT-115)")
    schon: set[str] = set()
    k = validierung.Pruefergebnis("x.pdf", "KoSIT", False, ["BR-CO-16 [BR-CO-16]-Amount due"])
    m = validierung.Pruefergebnis(
        "x.pdf", "Mustang", False, [roh], info="[PDF/A 3B konform=true, XML-Profil x]"
    )
    assert len(validierung.gruende(k, schon=schon)) == 2
    assert validierung.gruende(m, schon=schon) == []


# ------------------------------------------------------------------ veraPDF isCompliant (strengere PDF/A-Prüfung)
def _bericht(pdf_zeile: str | None, status: str = "valid", fehler: str = "") -> str:
    pdf = f'<pdf>{pdf_zeile}<summary status="{status}"/></pdf>' if pdf_zeile is not None else ""
    return (
        f'<validation filename="x.pdf">{pdf}<xml><info><profile>urn:cen.eu:en16931:2017</profile></info>'
        f'<summary status="valid"/></xml>{fehler}<summary status="{status}"/></validation>'
    )


VERSTOSS = (
    "TestAssertion [ruleId=RuleId [specification=ISO 19005-3:2012, clause=6.2.4.3, testNumber=4], "
    "status=failed, message=DeviceGray shall only be used if ..., location=Location [level=CosDocument, "
    "context=root/document[0]/pages[0](7 0 obj PDPage)], locationContext=null, "
    "errorMessage=DeviceGray colour space is used without output intent profile]"
)


def test_mustang_konform_true_gueltig():
    e = validierung._mustang_bericht(
        Path("x.pdf"),
        _bericht(
            "ValidationResult [flavour=3b, totalAssertions=2713, assertions=[], isCompliant=true]"
        ),
    )
    assert e.gueltig and not e.technisch and not e.fehler
    assert "konform=true" in e.info


def test_mustang_konform_false_ungueltig_mit_regel():
    """Mustang meldet „valid“ ohne Fehler, veraPDF aber isCompliant=false -> ungültig (bisher „gültig“)."""
    e = validierung._mustang_bericht(
        Path("x.pdf"),
        _bericht(
            f"ValidationResult [flavour=3b, totalAssertions=2679, assertions=[{VERSTOSS}, {VERSTOSS}], "
            "isCompliant=false]"
        ),
    )
    assert not e.gueltig and not e.technisch
    assert e.fehler == [
        "veraPDF 6.2.4.3-4 DeviceGray colour space is used without output intent profile"
    ]
    g = validierung.gruende(e)
    assert g[0] == "PDF/A-Prüfung (veraPDF) nicht bestanden – das PDF ist nicht PDF/A-3-konform:"
    assert (
        g[1]
        == "  – PDF/A-Regel ISO 19005-3 6.2.4.3-4: DeviceGray colour space is used without output intent profile"
    )
    assert not any("ohne Einzelmeldung" in z for z in g)


def test_mustang_konform_false_ohne_regeltext():
    e = validierung._mustang_bericht(
        Path("x.pdf"),
        _bericht(
            "ValidationResult [flavour=3b, totalAssertions=1, assertions=[], isCompliant=false]"
        ),
    )
    assert not e.gueltig and not e.technisch
    assert validierung.gruende(e)[0].startswith("PDF/A-Prüfung (veraPDF) nicht bestanden")


def test_mustang_ohne_iscompliant_nicht_geprueft():
    """PDF ohne PDF/A-Angabe im Bericht: kein stilles „gültig“, sondern „nicht geprüft“ (technisch)."""
    for pdf_zeile in (None, "ValidationResult [flavour=3b, totalAssertions=0]"):
        e = validierung._mustang_bericht(Path("x.pdf"), _bericht(pdf_zeile))
        assert not e.gueltig and e.technisch, pdf_zeile
        assert validierung.gruende(e) == [
            "PDF/A-Prüfung (veraPDF) ohne Ergebnis – PDF/A-Konformität nicht geprüft"
        ]


def test_mustang_ohne_iscompliant_mit_xml_fehler_bleibt_ungueltig():
    e = validierung._mustang_bericht(
        Path("x.pdf"),
        _bericht(
            None,
            status="invalid",
            fehler='<error type="4">[BR-CO-16]-Amount due [ID BR-CO-16]</error>',
        ),
    )
    assert not e.gueltig and not e.technisch and e.fehler


def test_gruende_englisch():
    from fakturafalter.gui import texte

    e = validierung.Pruefergebnis(
        "x.pdf",
        "Mustang",
        False,
        ["veraPDF 6.2.4.3-4 DeviceGray without intent"],
        info="[PDF/A 3b konform=false, XML-Profil x]",
    )
    texte.sprache_setzen("en")
    try:
        g = validierung.gruende(e)
    finally:
        texte.sprache_setzen("de")
    assert g == [
        "PDF/A check (veraPDF) failed – the PDF is not PDF/A-3 compliant:",
        "  – PDF/A rule ISO 19005-3 6.2.4.3-4: DeviceGray without intent",
    ]


def test_konform_false_landet_im_fehlerordner(konfig, eingang, monkeypatch):
    """Ablauf: Mustang-Urteil isCompliant=false -> Status „fehler“, Datei im Fehlerordner, Begründung im Bericht."""
    monkeypatch.setattr(validierung, "bereit", lambda: True)
    monkeypatch.setattr(
        validierung,
        "pruefen",
        lambda ds: [
            validierung._mustang_bericht(
                Path(d),
                _bericht(
                    f"ValidationResult [flavour=3b, totalAssertions=9, assertions=[{VERSTOSS}], isCompliant=false]"
                ),
            )
            for d in ds
            if Path(d).suffix == ".pdf"
        ],
    )
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    schlecht = [e for e in lauf.ergebnisse if e.pruefung == "ungültig"]
    assert schlecht and all(e.status == "fehler" for e in schlecht)
    assert not list(konfig.ausgang.glob("*.pdf")) and list(konfig.fehler.glob("*.pdf"))
    bericht = "\n".join(p.read_text(encoding="utf-8") for p in konfig.fehler.glob("*_fehler.txt"))
    assert "PDF/A-Prüfung (veraPDF) nicht bestanden" in bericht
    assert "ISO 19005-3 6.2.4.3-4" in bericht


def test_ohne_iscompliant_bleibt_im_ausgang(konfig, eingang, monkeypatch):
    monkeypatch.setattr(validierung, "bereit", lambda: True)
    monkeypatch.setattr(
        validierung,
        "pruefen",
        lambda ds: [
            validierung._mustang_bericht(Path(d), _bericht(None))
            for d in ds
            if Path(d).suffix == ".pdf"
        ],
    )
    eingang("variante-a_positionen_utf8.csv")
    lauf = pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    ok = [e for e in lauf.ergebnisse if e.dateien]
    assert ok and all(e.status == "ok" and e.pruefung == "nicht geprüft" for e in ok)
    assert all(any("PDF/A-Konformität nicht geprüft" in h for h in e.hinweise) for e in ok)
    assert all(Path(d).parent == konfig.ausgang for e in ok for d in e.dateien)


@pytest.mark.validierung
@braucht_werkzeuge
def test_echt_nicht_pdfa_konform(konfig, eingang, tmp_path):
    """Echte Werkzeuge: OutputIntent entfernt -> veraPDF isCompliant=false -> ungültig."""
    eingang("variante-a_positionen_utf8.csv")
    konfig.nachpruefen = False
    pipeline.verarbeiten(sorted(konfig.eingang.iterdir()), konfig)
    pdf = sorted(konfig.ausgang.glob("*.pdf"))[0]
    kaputt = tmp_path / "ohne_outputintent.pdf"
    with pikepdf.open(pdf) as p:
        del p.Root.OutputIntents
        p.save(kaputt)
    (gut,) = validierung.mustang_stapel([pdf])
    assert gut.gueltig and "konform=true" in gut.info
    (e,) = validierung.mustang_stapel([kaputt])
    assert not e.gueltig and not e.technisch and "konform=false" in e.info
    assert any(f.startswith("veraPDF 6.2.4.3") for f in e.fehler), e.fehler
