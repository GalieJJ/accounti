"""ZUGFeRD-PDF: lesbare Rechnung als PDF/A-3b mit der XRechnung als Anhang.

Profil XRECHNUNG: Das eingebettete ``xrechnung.xml`` ist byte-genau die XRechnung, die
auch das KoSIT-Prüftool geprüft hat. Die PDF-Ansicht ist nur die menschenlesbare
Darstellung; maßgeblich sind die strukturierten Daten.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from fpdf import FPDF

from accounti.erechnung.modell import Partei, Rechnung

ANHANG = "xrechnung.xml"
SCHRIFTEN = Path(__file__).resolve().parent.parent / "schriften"
GUTSCHRIFT_TYPEN = {"381", "261", "396", "532"}

_EINHEITEN = {
    "C62": "Stk",
    "H87": "Stk",
    "HUR": "Std",
    "DAY": "Tag",
    "MON": "Monat",
    "KGM": "kg",
    "MTR": "m",
    "MTK": "m²",
    "LTR": "l",
    "LS": "pauschal",
    "SET": "Satz",
}


def betrag_de(wert: Decimal | None) -> str:
    if wert is None:
        return "—"
    text = f"{wert.quantize(Decimal('0.01')):,.2f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def _zahl(wert: Decimal | None) -> str:
    if wert is None:
        return ""
    return f"{wert.normalize():f}".replace(".", ",")


def _datum(wert: date | None) -> str:
    return f"{wert:%d.%m.%Y}" if wert else "—"


def _iban(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _adresszeilen(p: Partei, *, mit_land: bool) -> list[str]:
    a = p.anschrift
    zeilen = [p.name or "", a.strasse or "", " ".join(filter(None, [a.plz, a.ort]))]
    if mit_land and a.land and a.land != "DE":
        zeilen.append(a.land)
    return [z for z in zeilen if z]


def _xmp(r: Rechnung, zeit: str) -> str:
    titel = escape(f"Rechnung {r.nummer}")
    autor = escape(r.verkaeufer.name or "")
    eigenschaften = [
        ("DocumentFileName", "The name of the embedded XML document"),
        ("DocumentType", "The type of the hybrid document in capital letters"),
        ("Version", "The actual version of the standard applying to the embedded XML"),
        ("ConformanceLevel", "The conformance level of the embedded XML document"),
    ]
    eigenschafts_xml = "\n".join(
        '          <rdf:li rdf:parseType="Resource">'
        f"<pdfaProperty:name>{name}</pdfaProperty:name>"
        "<pdfaProperty:valueType>Text</pdfaProperty:valueType>"
        "<pdfaProperty:category>external</pdfaProperty:category>"
        f"<pdfaProperty:description>{text}</pdfaProperty:description></rdf:li>"
        for name, text in eigenschaften
    )
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
      <pdfaid:part>3</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
    </rdf:Description>
    <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{titel}</rdf:li></rdf:Alt></dc:title>
      <dc:creator><rdf:Seq><rdf:li>{autor}</rdf:li></rdf:Seq></dc:creator>
    </rdf:Description>
    <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
      <pdf:Producer>accounti</pdf:Producer>
    </rdf:Description>
    <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <xmp:CreatorTool>accounti</xmp:CreatorTool>
      <xmp:CreateDate>{zeit}</xmp:CreateDate>
      <xmp:ModifyDate>{zeit}</xmp:ModifyDate>
      <xmp:MetadataDate>{zeit}</xmp:MetadataDate>
    </rdf:Description>
    <rdf:Description rdf:about=""
        xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
        xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"
        xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
      <pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">
        <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
        <pdfaSchema:namespaceURI>urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#</pdfaSchema:namespaceURI>
        <pdfaSchema:prefix>fx</pdfaSchema:prefix>
        <pdfaSchema:property><rdf:Seq>
{eigenschafts_xml}
        </rdf:Seq></pdfaSchema:property>
      </rdf:li></rdf:Bag></pdfaExtension:schemas>
    </rdf:Description>
    <rdf:Description rdf:about=""
        xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">
      <fx:DocumentType>INVOICE</fx:DocumentType>
      <fx:DocumentFileName>{ANHANG}</fx:DocumentFileName>
      <fx:Version>1.0</fx:Version>
      <fx:ConformanceLevel>XRECHNUNG</fx:ConformanceLevel>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""  # noqa: E501


class _RechnungsPdf(FPDF):
    def __init__(self, r: Rechnung) -> None:
        super().__init__(format="A4", unit="mm", enforce_compliance="PDF/A-3B")
        self.r = r
        self.add_font("Sans", "", str(SCHRIFTEN / "LiberationSans-Regular.ttf"))
        self.add_font("Sans", "B", str(SCHRIFTEN / "LiberationSans-Bold.ttf"))
        self.set_margins(left=20, top=15, right=15)
        self.set_auto_page_break(auto=True, margin=32)

    def footer(self) -> None:
        v = self.r.verkaeufer
        a = v.anschrift
        teile = [
            v.name,
            ", ".join(
                filter(None, [a.strasse, f"{a.plz or ''} {a.ort or ''}".strip()])
            ),
            f"USt-IdNr. {v.ust_id}" if v.ust_id else None,
            f"Steuernummer {v.steuernummer}" if v.steuernummer else None,
            f"IBAN {_iban(self.r.iban)}" if self.r.iban else None,
            v.email,
        ]
        self.set_y(-25)
        self.set_draw_color(160)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_font("Sans", "", 7)
        self.set_text_color(90)
        self.multi_cell(0, 3.5, " · ".join(t for t in teile if t), align="C")
        self.cell(0, 4, f"Seite {self.page_no()} von {{nb}}", align="R")
        self.set_text_color(0)


def _kopf(pdf: _RechnungsPdf) -> None:
    r = pdf.r
    v = r.verkaeufer
    pdf.set_font("Sans", "B", 15)
    pdf.cell(0, 7, v.name or "", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Sans", "", 8)
    pdf.set_text_color(90)
    pdf.cell(
        0,
        4,
        " · ".join(_adresszeilen(v, mit_land=False)[1:]),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0)

    # Anschriftfeld (DIN 5008 Form B)
    pdf.set_xy(20, 45)
    pdf.set_font("Sans", "", 7)
    pdf.set_text_color(90)
    pdf.cell(
        85,
        4,
        " · ".join(_adresszeilen(v, mit_land=False)),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0)
    pdf.set_font("Sans", "", 10)
    for zeile in _adresszeilen(r.kaeufer, mit_land=True):
        pdf.cell(85, 5, zeile, new_x="LMARGIN", new_y="NEXT")
    if r.kaeufer.ust_id:
        pdf.set_font("Sans", "", 8)
        pdf.cell(85, 5, f"USt-IdNr. {r.kaeufer.ust_id}", new_x="LMARGIN", new_y="NEXT")

    # Kopfdaten rechts
    angaben: list[tuple[str, str]] = [
        ("Rechnungsnummer", r.nummer or "—"),
        ("Rechnungsdatum", _datum(r.datum)),
        ("Leistungsdatum", _datum(r.leistungsdatum)),
    ]
    if r.leistungszeitraum_von or r.leistungszeitraum_bis:
        angaben.append(
            (
                "Leistungszeitraum",
                f"{_datum(r.leistungszeitraum_von)} – "
                f"{_datum(r.leistungszeitraum_bis)}",
            )
        )
    if r.bestellnummer:
        angaben.append(("Ihre Bestellung", r.bestellnummer))
    if r.kaeufer_referenz and r.kaeufer_referenz not in ("n/a", r.bestellnummer):
        angaben.append(("Ihre Referenz", r.kaeufer_referenz))
    angaben.append(("Fällig am", _datum(r.faellig)))
    if v.kontakt_name:
        angaben.append(("Ansprechpartner", v.kontakt_name))
    if v.kontakt_telefon:
        angaben.append(("Telefon", v.kontakt_telefon))
    if v.kontakt_email:
        angaben.append(("E-Mail", v.kontakt_email))
    pdf.set_xy(112, 45)
    for label, wert in angaben:
        pdf.set_x(112)
        pdf.set_font("Sans", "", 8)
        pdf.cell(29, 4.5, label)
        pdf.set_font("Sans", "B" if label == "Rechnungsnummer" else "", 8)
        pdf.multi_cell(0, 4.5, wert, new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(max(pdf.get_y(), 92) + 6)
    titel = "Gutschrift" if r.typ in GUTSCHRIFT_TYPEN else "Rechnung"
    pdf.set_font("Sans", "B", 14)
    pdf.cell(0, 8, f"{titel} {r.nummer}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def _positionen(pdf: _RechnungsPdf) -> None:
    r = pdf.r
    pdf.set_font("Sans", "", 9)
    rechts = "RIGHT"
    with pdf.table(
        col_widths=(9, 70, 22, 22, 16, 26),
        text_align=("LEFT", "LEFT", rechts, rechts, rechts, rechts),
        borders_layout="HORIZONTAL_LINES",
        align="LEFT",
        width=pdf.epw,
        line_height=5,
        padding=1,
        headings_style=_fett(pdf),
        repeat_headings=1,
    ) as tabelle:
        kopf = tabelle.row()
        for spalte in ("Pos.", "Bezeichnung", "Menge", "Einzelpreis", "USt", "Netto"):
            kopf.cell(spalte)
        for z in r.zeilen:
            zeile = tabelle.row()
            zeile.cell(z.id or "")
            zeile.cell(z.bezeichnung or "")
            einheit = _EINHEITEN.get(z.einheit or "", z.einheit or "")
            zeile.cell(f"{_zahl(z.menge)} {einheit}".strip())
            zeile.cell(betrag_de(z.einzelpreis))
            zeile.cell(f"{_zahl(z.steuersatz)} %" if z.steuersatz is not None else "—")
            zeile.cell(betrag_de(z.netto))
        for za in r.zu_abschlaege:
            zeile = tabelle.row()
            zeile.cell("")
            art = "Zuschlag" if za.zuschlag else "Nachlass"
            zeile.cell(f"{art}: {za.grund or ''}")
            zeile.cell("")
            zeile.cell("")
            satz = za.steuersatz
            zeile.cell(f"{_zahl(satz)} %" if satz is not None else "—")
            betrag = za.betrag or Decimal("0")
            zeile.cell(betrag_de(betrag if za.zuschlag else -betrag))


def _fett(pdf: _RechnungsPdf) -> Any:
    from fpdf.fonts import FontFace

    return FontFace(family="Sans", emphasis="BOLD", size_pt=9)


def _summen(pdf: _RechnungsPdf) -> None:
    r = pdf.r
    s = r.summen
    pdf.ln(3)

    def zeile(label: str, wert: str, *, fett: bool = False) -> None:
        pdf.set_x(105)
        pdf.set_font("Sans", "B" if fett else "", 10 if fett else 9)
        pdf.cell(60, 5.5, label)
        pdf.cell(0, 5.5, wert, align="R", new_x="LMARGIN", new_y="NEXT")

    zeile("Summe netto", f"{betrag_de(s.netto)} €")
    for st in r.steuern:
        satz = f"{_zahl(st.satz)} %" if st.satz is not None else ""
        bezeichnung = "USt" if st.kategorie == "S" else f"USt ({st.kategorie})"
        zeile(
            f"{bezeichnung} {satz} auf {betrag_de(st.basis)} €",
            f"{betrag_de(st.betrag)} €",
        )
    pdf.set_draw_color(0)
    pdf.line(105, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    zeile("Rechnungsbetrag", f"{betrag_de(s.brutto)} €", fett=True)
    if s.zahlbetrag is not None and s.zahlbetrag != s.brutto:
        zeile("Zu zahlen", f"{betrag_de(s.zahlbetrag)} €", fett=True)


def _hinweise(pdf: _RechnungsPdf) -> None:
    r = pdf.r
    pdf.ln(4)
    pdf.set_font("Sans", "", 9)
    texte = list(r.notizen)
    for st in r.steuern:
        if st.befreiungsgrund and not any(st.befreiungsgrund in t for t in texte):
            texte.append(st.befreiungsgrund)
    bedingungen = re.sub(r"#SKONTO#[^\n]*#\n?", "", r.zahlungsbedingungen or "").strip()
    if bedingungen:
        texte.append(bedingungen)
    if r.skonto:
        prozent, tage = r.skonto
        texte.append(
            f"Bei Zahlung innerhalb von {tage} Tagen gewähren wir "
            f"{betrag_de(prozent)} % Skonto."
        )
    if r.iban:
        texte.append(
            f"Bitte überweisen Sie den Betrag unter Angabe der Rechnungsnummer "
            f"{r.nummer} auf das Konto IBAN {_iban(r.iban)}."
        )
    for text in texte:
        pdf.multi_cell(0, 4.5, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)


def schreibe_zugferd(r: Rechnung, xml: bytes, erstellt_am: datetime) -> bytes:
    """Erzeugt das ZUGFeRD-PDF (PDF/A-3b) mit ``xml`` als eingebetteter XRechnung."""
    pdf = _RechnungsPdf(r)
    pdf.set_creation_date(erstellt_am)
    pdf.set_title(f"Rechnung {r.nummer}")
    pdf.set_author(r.verkaeufer.name or "")
    pdf.set_creator("accounti")
    pdf.set_producer("accounti")
    pdf.add_page()
    _kopf(pdf)
    _positionen(pdf)
    _summen(pdf)
    _hinweise(pdf)
    pdf.embed_file(
        bytes=xml,
        basename=ANHANG,
        desc="XRechnung (ZUGFeRD-Profil XRECHNUNG)",
        mime_type="text/xml",
        modification_date=erstellt_am,
        associated_file_relationship="Alternative",
    )
    pdf.set_xmp_metadata(_xmp(r, erstellt_am.isoformat(timespec="seconds")))
    return bytes(pdf.output())
