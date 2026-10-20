"""Mahnschreiben als Text und als PDF (fpdf2, Liberation Sans wie die E-Rechnung).

Die Brieftexte je Stufe sind Konfiguration (``mahnwesen.stufen[].text``); ohne eigenen
Text gibt es einen Standard für die Zahlungserinnerung, für Mahnungen mit Verzug und
für die letzte Stufe. Die Beträge stehen immer darunter, aufgeschlüsselt.
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from accounti.anzeige import betrag_de, datum_de
from accounti.konfiguration import Firma
from accounti.mahnwesen.konfiguration import MahnEinstellungen
from accounti.mahnwesen.zinsen import AUFSCHLAG_UNTERNEHMER, AUFSCHLAG_VERBRAUCHER
from accounti.models import Kontakt
from accounti.models.mahnwesen import Mahnung, Zinsabschnitt
from accounti.zahlung.iban import lesbar

SCHRIFTEN = Path(__file__).resolve().parent.parent / "erechnung" / "schriften"

TEXT_ERINNERUNG = (
    "sicher ist es Ihrer Aufmerksamkeit entgangen: Unsere Rechnung {nummer} vom "
    "{datum} war am {faellig} fällig, der Betrag von {betrag} € ist bei uns noch "
    "nicht eingegangen. Bitte überweisen Sie ihn bis zum {frist}."
)
TEXT_MAHNUNG = (
    "unsere Rechnung {nummer} vom {datum} ist trotz Fälligkeit am {faellig} noch "
    "offen. Sie befinden sich mit der Zahlung in Verzug. Bitte überweisen Sie den "
    "Gesamtbetrag von {summe} € einschließlich der unten berechneten Verzugszinsen "
    "und Kosten bis zum {frist}."
)
TEXT_OHNE_VERZUG = (
    "unsere Rechnung {nummer} vom {datum} ist trotz Fälligkeit am {faellig} noch "
    "offen. Bitte überweisen Sie den Gesamtbetrag von {summe} € bis zum {frist}."
)
TEXT_LETZTE = (
    "trotz unserer bisherigen Mahnungen ist unsere Rechnung {nummer} vom {datum} "
    "noch offen; Sie befinden sich mit der Zahlung in Verzug. Dies ist unsere letzte "
    "Mahnung: Geht der Gesamtbetrag von {summe} € nicht bis zum {frist} bei uns ein, "
    "behalten wir uns vor, ohne weitere Ankündigung ein gerichtliches Mahnverfahren "
    "einzuleiten."
)


def _prozent(wert: Decimal) -> str:
    return f"{wert:.2f}".replace(".", ",")


def im_verzug(m: Mahnung) -> bool:
    return m.verzug_ab is not None and m.verzug_ab <= m.datum


def brieftext(m: Mahnung, kontakt: Kontakt, firma: Firma, e: MahnEinstellungen) -> str:
    stufe = e.stufen[m.stufe - 1]
    if stufe.text:
        vorlage = stufe.text
    elif not stufe.verzugszinsen:
        # verlangt die Stufe eine Gebühr, nennt der Text den Gesamtbetrag
        vorlage = TEXT_ERINNERUNG if m.summe == m.restbetrag else TEXT_OHNE_VERZUG
    elif not im_verzug(m):
        vorlage = TEXT_OHNE_VERZUG  # nichts behaupten, was (noch) nicht gilt
    elif m.stufe == len(e.stufen):
        vorlage = TEXT_LETZTE
    else:
        vorlage = TEXT_MAHNUNG
    return vorlage.format(
        kunde=kontakt.name,
        nummer=m.belegnummer or "—",
        datum=datum_de(m.belegdatum),
        faellig=datum_de(m.faellig_am),
        betrag=betrag_de(m.restbetrag),
        summe=betrag_de(m.summe),
        frist=datum_de(m.zahlungsfrist),
        firma=firma.name,
        stufe=m.stufe_name,
    )


def _zinszeilen(a: Zinsabschnitt, unternehmer: bool) -> tuple[str, str]:
    aufschlag = AUFSCHLAG_UNTERNEHMER if unternehmer else AUFSCHLAG_VERBRAUCHER
    absatz = "2" if unternehmer else "1"
    tage = "1 Tag" if a.tage == 1 else f"{a.tage} Tage"
    return (
        f"Verzugszinsen {_prozent(a.satz)} % vom {datum_de(a.von)} bis "
        f"{datum_de(a.bis)} ({tage}) auf {betrag_de(a.kapital)} €",
        f"(Basiszinssatz {_prozent(a.basiszins)} % + {aufschlag} Prozentpunkte, "
        f"§ 288 Abs. {absatz} BGB)",
    )


def aufstellung(m: Mahnung) -> list[tuple[str, str | None]]:
    """Zeilen der Forderungsaufstellung: (Text, Betrag oder None für Hinweise)."""
    zeilen: list[tuple[str, str | None]] = [
        (
            f"Rechnung {m.belegnummer or '—'} vom {datum_de(m.belegdatum)}, fällig am "
            f"{datum_de(m.faellig_am)}",
            f"{betrag_de(m.rechnungsbetrag)} €",
        )
    ]
    if m.restbetrag != m.rechnungsbetrag:
        zeilen.append(
            (
                "abzüglich bereits gezahlt",
                f"{betrag_de(m.restbetrag - m.rechnungsbetrag)} €",
            )
        )
    zeilen.append(("Offener Rechnungsbetrag", f"{betrag_de(m.restbetrag)} €"))
    if im_verzug(m) and m.verzug_ab is not None and m.verzug_grund:
        zeilen.append(
            (f"In Verzug seit {datum_de(m.verzug_ab)}: {m.verzug_grund}", None)
        )
    for a in m.zinsabschnitte:
        text, hinweis = _zinszeilen(a, m.unternehmer)
        zeilen += [(text, f"{betrag_de(a.zinsen)} €"), (hinweis, None)]
    if m.pauschale:
        zeilen.append(
            ("Pauschale nach § 288 Abs. 5 BGB", f"{betrag_de(m.pauschale)} €")
        )
    if m.gebuehren or m.gebuehren_kumuliert:
        zeilen.append(("Mahngebühren", f"{betrag_de(m.gebuehren)} €"))
    angerechnet = m.gebuehren_kumuliert - m.gebuehren
    if angerechnet > 0:
        zeilen.append(
            (
                f"(Mahngebühren von {betrag_de(angerechnet)} € sind auf die Pauschale "
                "angerechnet, § 288 Abs. 5 Satz 3 BGB)",
                None,
            )
        )
    zeilen.append(("Gesamtbetrag", f"{betrag_de(m.summe)} €"))
    return zeilen


def _absenderzeile(firma: Firma) -> str:
    a = firma.anschrift
    return f"{firma.name} · {a.strasse} · {a.plz} {a.ort}"


def _empfaenger(kontakt: Kontakt) -> list[str]:
    zeilen = [kontakt.name, kontakt.strasse or ""]
    zeilen.append(" ".join(filter(None, [kontakt.plz, kontakt.ort])))
    if kontakt.land and kontakt.land != "DE":
        zeilen.append(kontakt.land)
    return [z for z in zeilen if z]


def _zahlungshinweis(m: Mahnung, firma: Firma) -> tuple[str, str]:
    """(Bitte, Bankverbindung) — die IBAN bleibt in einer eigenen Zeile zusammen."""
    bic = f" (BIC {firma.bank.bic})" if firma.bank.bic else ""
    return (
        f"Bitte überweisen Sie den Gesamtbetrag bis zum {datum_de(m.zahlungsfrist)} "
        f"unter Angabe der Rechnungsnummer {m.belegnummer or '—'} auf unser Konto:",
        f"IBAN {lesbar(firma.iban)}{bic}",
    )


SCHLUSS = (
    "Haben Sie inzwischen gezahlt, betrachten Sie dieses Schreiben bitte als "
    "gegenstandslos."
)


def betreff(m: Mahnung) -> str:
    return (
        f"{m.stufe_name} — Rechnung {m.belegnummer or '—'} vom {datum_de(m.belegdatum)}"
    )


def mahntext(m: Mahnung, kontakt: Kontakt, firma: Firma, e: MahnEinstellungen) -> str:
    """Das Mahnschreiben als reiner Text (Absätze auf 80 Zeichen umbrochen)."""

    def absatz(text: str) -> str:
        return textwrap.fill(text, width=80, break_on_hyphens=False)

    teile = [_absenderzeile(firma), "", *_empfaenger(kontakt), ""]
    teile += [f"{firma.anschrift.ort}, {datum_de(m.datum)}", "", betreff(m), ""]
    teile += ["Sehr geehrte Damen und Herren,", ""]
    teile += [absatz(brieftext(m, kontakt, firma, e)), ""]
    for text, betrag in aufstellung(m):
        if betrag is None:
            teile.append(f"  {text}")
        else:
            teile.append(f"{text:<64} {betrag:>15}")
    bitte, konto = _zahlungshinweis(m, firma)
    teile += ["", absatz(bitte), f"  {konto}", "", absatz(SCHLUSS), ""]
    teile += ["Mit freundlichen Grüßen", firma.name, ""]
    return "\n".join(teile)


class _MahnPdf(FPDF):
    def __init__(self, firma: Firma) -> None:
        super().__init__(format="A4", unit="mm")
        self.firma = firma
        self.add_font("Sans", "", str(SCHRIFTEN / "LiberationSans-Regular.ttf"))
        self.add_font("Sans", "B", str(SCHRIFTEN / "LiberationSans-Bold.ttf"))
        self.set_margins(left=20, top=15, right=15)
        self.set_auto_page_break(auto=True, margin=28)

    def footer(self) -> None:
        f = self.firma
        teile = [
            _absenderzeile(f),
            f"USt-IdNr. {f.ust_id}" if f.ust_id else None,
            f"Steuernummer {f.steuernummer}" if f.steuernummer else None,
            f"IBAN {lesbar(f.iban)}",
            f.email,
        ]
        self.set_y(-22)
        self.set_font("Sans", "", 7)
        self.set_text_color(90)
        self.multi_cell(0, 3.5, " · ".join(t for t in teile if t), align="C")
        self.set_text_color(0)


def mahn_pdf(
    m: Mahnung,
    kontakt: Kontakt,
    firma: Firma,
    e: MahnEinstellungen,
    erstellt_am: datetime,
) -> bytes:
    """Das Mahnschreiben als PDF (Anschriftfeld nach DIN 5008 Form B)."""
    pdf = _MahnPdf(firma)
    pdf.set_creation_date(erstellt_am)
    pdf.set_title(betreff(m))
    pdf.set_author(firma.name)
    pdf.set_creator("accounti")
    pdf.set_producer("accounti")
    pdf.add_page()
    pdf.set_font("Sans", "B", 15)
    pdf.cell(0, 7, firma.name, new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(20, 45)
    pdf.set_font("Sans", "", 7)
    pdf.set_text_color(90)
    pdf.cell(85, 4, _absenderzeile(firma), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.set_font("Sans", "", 10)
    for zeile in _empfaenger(kontakt):
        pdf.cell(85, 5, zeile, new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(130, 45)
    pdf.cell(0, 5, f"{firma.anschrift.ort}, {datum_de(m.datum)}", align="R")
    pdf.set_y(95)
    pdf.set_font("Sans", "B", 12)
    pdf.multi_cell(0, 6, betreff(m), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Sans", "", 10)
    pdf.multi_cell(
        0, 5, "Sehr geehrte Damen und Herren,", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(2)
    pdf.multi_cell(0, 5, brieftext(m, kontakt, firma, e), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for text, betrag in aufstellung(m):
        gesamt = text == "Gesamtbetrag"
        if gesamt:
            pdf.ln(1)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(0.5)
        if betrag is None:
            pdf.set_font("Sans", "", 7.5)
            pdf.set_text_color(90)
            pdf.multi_cell(140, 4, text, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0)
            continue
        pdf.set_font("Sans", "B" if gesamt else "", 10 if gesamt else 9)
        y = pdf.get_y()
        pdf.set_xy(160, y)
        pdf.cell(0, 5, betrag, align="R")
        pdf.set_xy(pdf.l_margin, y)
        pdf.multi_cell(135, 5, text, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    pdf.set_font("Sans", "", 10)
    bitte, konto = _zahlungshinweis(m, firma)
    for absatz in (f"{bitte}\n{konto}", SCHLUSS):
        pdf.multi_cell(0, 5, absatz, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.ln(4)
    pdf.multi_cell(
        0, 5, f"Mit freundlichen Grüßen\n{firma.name}", new_x="LMARGIN", new_y="NEXT"
    )
    return bytes(pdf.output())
