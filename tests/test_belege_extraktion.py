import signal
import time
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.belege import extraktion
from accounti.belege.extraktion import Steuerzeile, extrahiere

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"


def _lies(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_rechnung_mit_zwei_steuersaetzen():
    e = extrahiere(_lies("rechnung_zwei_steuersaetze.txt"))
    assert e.belegnummer == "RE-2026-0042"
    assert e.belegdatum == date(2026, 3, 5)
    assert e.leistungsdatum == date(2026, 3, 3)
    assert e.lieferant_name == "Bürobedarf Müller GmbH"
    assert e.lieferant_ust_id == "DE123456789"
    assert e.iban == "DE89370400440532013000"
    assert e.zahlungsziel == date(2026, 3, 19)
    assert e.skonto_prozent == Decimal("2")
    assert e.skonto_tage == 7
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("100.00"), Decimal("19.00")),
        Steuerzeile(Decimal("7"), Decimal("50.00"), Decimal("3.50")),
    ]
    assert e.netto == Decimal("150.00")
    assert e.steuer == Decimal("22.50")
    assert e.brutto == Decimal("172.50")
    assert e.rechenprobe is True


def test_quittung_mit_inklusive_steuer():
    e = extrahiere(_lies("quittung_tankstelle.txt"))
    assert e.lieferant_name == "Tankstelle Nord GmbH & Co. KG"
    assert e.belegdatum == date(2026, 3, 12)
    assert e.belegnummer == "4711"
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("63.72"), Decimal("12.11"))
    ]
    assert e.brutto == Decimal("75.83")
    assert e.rechenprobe is True


def test_steuerzeile_mit_nur_einem_betrag():
    e = extrahiere(_lies("ausgangsrechnung.txt"))
    assert e.belegnummer == "2026-117"
    assert e.belegdatum == date(2026, 3, 10)
    assert e.zahlungsziel == date(2026, 3, 24)
    assert e.lieferant_ust_id == "DE999999999"
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("1000.00"), Decimal("190.00"))
    ]
    assert e.brutto == Decimal("1190.00")
    assert e.rechenprobe is True


def test_rechenprobe_schlaegt_fehl():
    text = """Firma Test GmbH
Rechnung Nr. 1
Datum: 01.03.2026
Nettobetrag 100,00
zzgl. 19 % MwSt. 19,00
Gesamtbetrag 120,00"""
    e = extrahiere(text)
    assert e.rechenprobe is False


def test_unvollstaendige_rechnung():
    e = extrahiere(_lies("rechnung_unvollstaendig.txt"))
    assert e.belegnummer is None
    assert e.belegdatum is None
    assert e.lieferant_name == "Hans Beispiel"
    assert e.brutto == Decimal("450.00")
    assert e.steuerzeilen == []
    assert e.rechenprobe is None


def test_ungueltige_iban_wird_ignoriert():
    e = extrahiere("Firma\nIBAN DE00 3704 0044 0532 0130 00")
    assert e.iban is None


def test_kundennummer_ist_keine_rechnungsnummer():
    e = extrahiere("Firma GmbH\nKundennummer: 100234\nRechnung\n")
    assert e.belegnummer is None


def test_label_nimmt_den_ersten_betrag_dahinter():
    e = extrahiere("Firma GmbH\nNetto 63,72   MwSt 12,11   Brutto 75,83\n")
    assert e.netto == Decimal("63.72")
    assert e.brutto == Decimal("75.83")


def test_brutto_inklusive_steuer_und_nicht_aus_nettosumme():
    e = extrahiere(
        "Firma GmbH\nSumme netto 150,00\nGesamtbetrag inkl. 19 % MwSt 178,50\n"
    )
    assert e.brutto == Decimal("178.50")
    assert e.netto == Decimal("150.00")


# --- Gesamttest Paket C: 0 %, Hinweistexte, Vorzeichen, „ohne Abzug“ -------------

REVERSE_CHARGE = """Galerietechnik Salzburg GmbH
Getreidegasse 9 · 5020 Salzburg · Österreich
UID: ATU12345678

Galerie Muster GmbH
USt-IdNr.: DE999999999

Rechnung

Rechnungsnummer: GS-2026-044
Rechnungsdatum: 02.04.2026

Summe netto                                        600,00 €
USt 0 %                                              0,00 €
Rechnungsbetrag                                    600,00 €

Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge).
Zahlbar innerhalb von 14 Tagen ohne Abzug.
"""


def test_nullsatz_mit_hinweis_auf_13b_ist_steuerangabe():
    """B06: Die 0-%-Zeile wird nicht verworfen, der Hinweis ist das Kennzeichen."""
    e = extrahiere(REVERSE_CHARGE)
    assert e.steuerzeilen == [Steuerzeile(Decimal("0"), Decimal("600.00"), Decimal(0))]
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("600.00"),
        Decimal("0.00"),
        Decimal("600.00"),
    )
    assert e.steuerkennzeichen == "AE"
    assert e.lieferant_ust_id == "ATU12345678"
    assert e.rechenprobe is True


@pytest.mark.parametrize(
    "zeile",
    ["Umsatzsteuer (0 %) 0,00 €", "USt 0 % auf 600,00 € 0,00 €", "MwSt. 0 % 0,00"],
)
def test_nullsatz_in_verschiedenen_schreibweisen(zeile):
    e = extrahiere(
        f"Firma GmbH\nRechnung\nNettobetrag 600,00\n{zeile}\nGesamt 600,00\n"
    )
    assert e.steuerzeilen == [Steuerzeile(Decimal("0"), Decimal("600.00"), Decimal(0))]
    assert e.steuer == Decimal("0.00")


@pytest.mark.parametrize(
    ("hinweis", "kennzeichen"),
    [
        ("Gemäß § 19 Abs. 1 UStG wird keine Umsatzsteuer berechnet.", "E"),
        ("Steuerfrei nach § 4 Nr. 14 UStG.", "E"),
        ("Steuerfreie innergemeinschaftliche Lieferung.", "K"),
        ("Reverse Charge — VAT to be accounted for by the recipient", "AE"),
    ],
)
def test_hinweis_ohne_nullzeile_wird_nullsatz(hinweis, kennzeichen):
    e = extrahiere(f"Atelier Klein\nRechnung Nr. 7\nGesamtbetrag 250,00 €\n{hinweis}\n")
    assert e.steuerkennzeichen == kennzeichen
    assert e.steuerzeilen == [Steuerzeile(Decimal("0"), Decimal("250.00"), Decimal(0))]
    assert e.steuer == Decimal("0.00")


def test_hinweis_bei_besteuerter_summe_wird_kein_nullsatz():
    """Netto ≠ Brutto: eine besteuerte Rechnung, deren Steuerzeile fehlt — kein 0 %."""
    e = extrahiere(
        "Firma GmbH\nNettobetrag 100,00\nGesamtbetrag 119,00\n"
        "Hinweis: bei Lieferungen ins Ausland Reverse Charge.\n"
    )
    assert e.steuerzeilen == [] and e.steuer is None


GUTSCHRIFT = """Rahmenwerk Nord GmbH
USt-IdNr.: DE811907980

Gutschrift (Rechnungskorrektur)

Rechnungsnummer: RW-G-0012
Rechnungsdatum: 20.10.2026

Pos. Bezeichnung                 Menge  Einzelpreis   Gesamt
1    Rücknahme Bilderrahmen Eiche    -4        50,00   -200,00

Summe netto                                       -200,00 €
zzgl. 19 % USt                                     -38,00 €
Gutschriftbetrag                                  -238,00 €
"""


def test_gutschrift_behaelt_das_vorzeichen():
    """B12: Steuer −38 (nicht +38), Brutto −238 aus „Gutschriftbetrag“."""
    e = extrahiere(GUTSCHRIFT)
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("-200.00"), Decimal("-38.00"))
    ]
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("-200.00"),
        Decimal("-38.00"),
        Decimal("-238.00"),
    )
    assert e.rechenprobe is True
    assert e.korrektur == "korrektur" and not e.vorzeichen_gedreht


def test_rechnungskorrektur_mit_positiven_betraegen_wird_negiert():
    positiv = GUTSCHRIFT.replace("-4 ", "4 ").replace("-2", "2").replace("-3", "3")
    e = extrahiere(positiv)
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("-200.00"),
        Decimal("-38.00"),
        Decimal("-238.00"),
    )
    assert e.vorzeichen_gedreht and e.korrektur == "korrektur"


def test_gemischte_vorzeichen_bestehen_die_rechenprobe_nicht():
    e = extrahiere("Firma GmbH\nSumme netto -200,00\nzzgl. 19 % USt 38,00\n")
    assert e.brutto == Decimal("-162.00")
    assert e.rechenprobe is False


def test_gutschrift_als_posten_einer_rechnung_ist_kein_korrekturbeleg():
    e = extrahiere(
        "Firma GmbH\nRechnung\nGutschrift vom 01.10.2026 -50,00\n"
        "Summe netto 100,00\nzzgl. 19 % USt 19,00\nGesamtbetrag 119,00\n"
    )
    assert e.korrektur is None and e.brutto == Decimal("119.00")


RECHNUNG_MIT_FUSSZEILE = """Rahmenwerk Nord GmbH
USt-IdNr.: DE811907980
{titel}
Rechnungsnummer: RW-5
Rechnungsdatum: 20.10.2026

Summe netto                                        300,00 €
zzgl. 19 % USt                                      57,00 €
Rechnungsbetrag                                    357,00 €

{fusszeile}
"""


@pytest.mark.parametrize("titel", ["Rechnung", ""])
@pytest.mark.parametrize(
    "fusszeile",
    [
        "Rechnungskorrektur nur schriftlich innerhalb von 8 Tagen",
        "Gutschrift erfolgt nur bei Rücksendung der Ware in Originalverpackung",
        "Credit notes are issued within 14 days",
        "Stornorechnung wird bei Rücktritt gesondert erstellt",
    ],
)
def test_korrekturwort_im_satz_ist_kein_belegtitel(titel, fusszeile):
    """M1 (Nachprüfung C): Ein Satz, der mit „Rechnungskorrektur“ oder „Gutschrift“
    beginnt, macht aus einer Rechnung keinen Korrekturbeleg — vorher wurde sie negiert
    (−357) und bei geprüftem Kreditor automatisch gebucht. Titel ist nur eine Zeile aus
    dem Schlüsselwort (höchstens mit Nummer oder Datum), und nie nach dem Titel
    „Rechnung“."""
    e = extrahiere(RECHNUNG_MIT_FUSSZEILE.format(titel=titel, fusszeile=fusszeile))
    assert e.korrektur is None and not e.vorzeichen_gedreht
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("300.00"),
        Decimal("57.00"),
        Decimal("357.00"),
    )


@pytest.mark.parametrize(
    ("titel", "art"),
    [
        ("Gutschrift", "gutschrift"),
        ("Gutschrift Nr. G-17", "gutschrift"),
        ("Gutschrift-Nr.: G-17 vom 20.10.2026", "gutschrift"),
        ("Gutschrift (Rechnungskorrektur)", "korrektur"),
        ("Rechnungskorrektur zur Rechnung Nr. RE-2026-0042", "korrektur"),
        ("Rechnungskorrektur", "korrektur"),
        ("Stornorechnung", "korrektur"),
        ("Credit Note No. CN-5", "korrektur"),
        ("GUTSCHRIFT / CREDIT NOTE", "korrektur"),
        ("Gutschrift Nr. G-17 zur Rechnung RE-5 vom 20.10.2026", "gutschrift"),
    ],
)
def test_korrekturtitel_mit_nummer_oder_datum(titel, art):
    e = extrahiere(RECHNUNG_MIT_FUSSZEILE.format(titel=titel, fusszeile=""))
    assert e.korrektur == art
    assert e.vorzeichen_gedreht and e.brutto == Decimal("-357.00")


def test_titel_rechnung_vor_dem_korrekturwort_bleibt_rechnung():
    """Steht vorher der Titel „Rechnung“, ist eine spätere Zeile „Gutschrift“ eine
    Zwischenüberschrift (z. B. verrechnete Gutschrift), kein Belegtitel."""
    e = extrahiere(
        RECHNUNG_MIT_FUSSZEILE.format(titel="Rechnung", fusszeile="Gutschrift")
    )
    assert e.korrektur is None and e.brutto == Decimal("357.00")


@pytest.mark.parametrize(
    "zeile",
    [
        "Gutschrift-Nr.: G-2026-17",
        "Gutschriftsnummer: G-2026-17",
        "Credit note no. G-2026-17",
    ],
)
def test_gutschriftnummer_ist_belegnummer(zeile):
    """N2 (Nachprüfung C): typische Gutschriften gingen mit „fehlt: Belegnummer“ zur
    Prüfung und wurden ohne Nummer gebucht."""
    e = extrahiere(f"Rahmenwerk Nord GmbH\nGutschrift\n{zeile}\nDatum: 20.10.2026\n")
    assert e.belegnummer == "G-2026-17"


def test_ohne_abzug_heisst_ausdruecklich_kein_skonto():
    """B09: „ohne Abzug“ ist 0 % — nicht „unbekannt“ (sonst Kontakt-Skonto)."""
    e = extrahiere(REVERSE_CHARGE)
    assert (e.skonto_prozent, e.skonto_tage) == (Decimal("0"), 0)
    mit = extrahiere(
        "Firma GmbH\nRechnungsdatum: 01.10.2026\n"
        "Zahlbar innerhalb von 30 Tagen ohne Abzug.\n"
        "Bei Zahlung innerhalb von 10 Tagen 2 % Skonto.\n"
    )
    assert (mit.skonto_prozent, mit.skonto_tage) == (Decimal("2"), 10)
    assert mit.zahlungsziel == date(2026, 10, 31)


@pytest.mark.parametrize(
    "zeile",
    [
        "Zahlbar innerhalb 30 Tagen ohne Abzug oder innerhalb 10 Tagen mit 2 % Skonto.",
        "Innerhalb 10 Tagen 2 % Skonto, innerhalb 30 Tagen netto.",
        "Zahlbar innerhalb von 30 Tagen netto; innerhalb von 10 Tagen 2 % Skonto.",
    ],
)
def test_skontofrist_aus_dem_teilsatz_mit_skonto(zeile):
    """N5 (Nachprüfung C): Stehen Zahlungsziel und Skonto in einer Zeile, kam die
    Skontofrist aus der ersten Tagesangabe (30 statt 10 Tage), das Ziel fehlte."""
    e = extrahiere(f"Firma GmbH\nRechnungsdatum: 01.10.2026\n{zeile}\n")
    assert (e.skonto_prozent, e.skonto_tage) == (Decimal("2"), 10)
    assert e.zahlungsziel == date(2026, 10, 31)


def test_skonto_ohne_frist_im_teilsatz_nimmt_die_frist_der_zeile():
    e = extrahiere(
        "Firma GmbH\nRechnungsdatum: 01.10.2026\nSkonto: 2 %, innerhalb 10 Tagen\n"
    )
    assert (e.skonto_prozent, e.skonto_tage) == (Decimal("2"), 10)
    assert e.zahlungsziel is None


# --- Nachprüfung C, Runde 3 ---------------------------------------------------------


@contextmanager
def _zeitschranke(sekunden):
    """Bricht nach ``sekunden`` hart ab (SIGALRM unterbricht auch einen laufenden
    Regex) — eine exponentielle Laufzeit soll den Testlauf nicht aufhalten."""
    beginn = time.perf_counter()
    if not hasattr(signal, "setitimer"):  # pragma: no cover - nur Windows
        yield
        assert time.perf_counter() - beginn < sekunden
        return

    def abbruch(*_):
        raise TimeoutError(f"länger als {sekunden} s")

    alt = signal.signal(signal.SIGALRM, abbruch)
    signal.setitimer(signal.ITIMER_REAL, sekunden)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, alt)


def _spalten(woerter, abstand):
    return (" " * abstand).join(woerter)


SPALTEN_GUTSCHRIFT = [
    "GUTSCHRIFT",
    "Nr. GS-12",
    "vom 01.10.2026",
    "zur Rechnung Nr. RE-5",
    "vom 15.09.2026",
]
PATHOLOGISCHE_ZEILEN = {  # Zeile, erkannter Titel
    "zur Rechnung ×12": ("Rechnungskorrektur" + " zur Rechnung" * 12 + " x", None),
    "vom ×22": ("Gutschrift" + " vom 01.01.2026" * 22 + " x", None),
    "Spalten 12": (_spalten([*SPALTEN_GUTSCHRIFT, "Seite 1"], 12), "gutschrift"),
    "Spalten 25": (_spalten([*SPALTEN_GUTSCHRIFT, "Seite 1"], 25), "gutschrift"),
    "Spalten 25, Kunde": (_spalten([*SPALTEN_GUTSCHRIFT, "Kunden-Nr. 4711"], 25), None),
    "Rechnung Spalten 10": (
        _spalten(
            ["RECHNUNG", "Nr. 4711", "vom 01.10.2026", "zur Rechnung Nr. RE-5"]
            + ["Datum 15.09.2026", "Kunde 1"],
            10,
        ),
        None,
    ),
    "lang": ("Gutschrift" + " zur Rechnung Nr. RE-5 vom 01.01.2026" * 300, None),
}


@pytest.mark.parametrize(
    ("zeile", "titel"), PATHOLOGISCHE_ZEILEN.values(), ids=PATHOLOGISCHE_ZEILEN.keys()
)
def test_titelerkennung_haengt_nicht(zeile, titel):
    """H/M-1 (Nachprüfung C, Runde 3): Zwischen den Wiederholungen der Titelangaben
    standen mehrdeutige ``\\s*`` — scheiterte der Treffer am Zeilenende, probierte das
    Muster jede Aufteilung der Leerzeichen durch (Spaltenlayout mit 12 Leerzeichen:
    15 s, mit 25: `belege import` hing). Jeder, der ein PDF an Postfach oder Webhook
    schickt, konnte so den Eingang lahmlegen. Eine Zeile über 120 Zeichen ist kein
    Titel („lang“)."""
    with _zeitschranke(2):
        e = extrahiere(f"Rahmenwerk Nord GmbH\n{zeile}\nSumme netto 100,00 €\n")
    assert e.korrektur == titel


@pytest.mark.parametrize("muster", ["_KORREKTUR_TITEL", "_RECHNUNG_TITEL"])
@pytest.mark.parametrize(
    "wiederholung", [" zur Rechnung", " vom 01.01.2026", " Nr. 12"]
)
def test_titelmuster_linear_auch_ohne_laengengrenze(muster, wiederholung):
    """Die Längengrenze für Titelzeilen ist nur die zweite Sicherung — das Muster
    selbst darf auch auf einer langen Zeile nicht zurückverfolgen."""
    wort = "Rechnung" if muster == "_RECHNUNG_TITEL" else "Gutschrift"
    zeile = wort + wiederholung * 2000 + " x"
    with _zeitschranke(2):
        assert getattr(extraktion, muster).match(zeile) is None
        assert getattr(extraktion, muster).match(wort + wiederholung * 2000)


def test_titel_im_spaltenlayout_wird_erkannt():
    """Mehrere Leerzeichen zwischen den Angaben (Spaltenlayout aus pypdf) zählen wie
    eines; die Seitenzahl gehört im Spaltenlayout oft in die Titelzeile."""
    titel = _spalten([*SPALTEN_GUTSCHRIFT, "Seite 1/2"], 25)
    with _zeitschranke(2):
        e = extrahiere(RECHNUNG_MIT_FUSSZEILE.format(titel=titel, fusszeile=""))
    assert e.korrektur == "gutschrift" and e.brutto == Decimal("-357.00")


@pytest.mark.parametrize(
    ("titel", "art"),
    [
        ("Gutschrift GS-2026-12", "gutschrift"),
        ("Credit Note CN-77", "korrektur"),
        ("Rechnungskorrektur zu RE-2026-5", "korrektur"),
        ("Gutschrift 4711", "gutschrift"),
    ],
)
def test_korrekturtitel_mit_blosser_nummer(titel, art):
    """N-1 (Nachprüfung C, Runde 3): Der Plan sagt „höchstens mit Nummer“, der Code
    verlangte „Nr.“, „No.“ oder „#“ davor — „Gutschrift GS-2026-12“ blieb positiv und
    wurde wie eine Rechnung gebucht."""
    e = extrahiere(RECHNUNG_MIT_FUSSZEILE.format(titel=titel, fusszeile=""))
    assert e.korrektur == art
    assert e.vorzeichen_gedreht and e.brutto == Decimal("-357.00")


@pytest.mark.parametrize(
    "zeile", ["Gutschrift 50,00", "Gutschrift zu 50,00 €", "Gutschrift 2 Stück"]
)
def test_betrag_nach_dem_korrekturwort_ist_keine_nummer(zeile):
    e = extrahiere(RECHNUNG_MIT_FUSSZEILE.format(titel="", fusszeile=zeile))
    assert e.korrektur is None and e.brutto == Decimal("357.00")


_LANG = 50_000
LANGER_LEERRAUM = {
    "Nr. und Leerzeichen": "Rechnungsnr." + " " * _LANG + "x",
    "Datum und Leerzeichen": "Rechnungsdatum" + " " * _LANG + "x",
    "Datum und Leerzeilen": "Rechnungsdatum" + "\n" * _LANG + "x",
    "Datum und Seitenvorschub": "Rechnungsdatum" + "\x0c" * _LANG + "x",
    "USt-IdNr.": "USt-IdNr." + " " * _LANG + "DE" + " " * _LANG + "x",
    "Skonto": "Skonto 2 % innerhalb" + " " * _LANG + "x",
}


@pytest.mark.parametrize("zeile", LANGER_LEERRAUM.values(), ids=LANGER_LEERRAUM.keys())
def test_lange_leerraeume_bremsen_die_erkennung_nicht(zeile):
    """H/M-1, gleiche Ursache in anderen Mustern: benachbarte ``\\s*`` wurden an einer
    langen Folge von Leerzeichen oder Leerzeilen quadratisch (20 000 Zeichen: 4 s bis
    über 10 s, 50 000 ein Vielfaches). Fremddaten kommen mit begrenztem Leerraum in die
    Muster."""
    with _zeitschranke(2):
        e = extrahiere(f"Rahmenwerk Nord GmbH\n{zeile}\nSumme netto 100,00 €\n")
    assert e.netto == Decimal("100.00")


def test_begrenzter_leerraum_behaelt_zeilen_und_spalten():
    text = "a" + " " * 30 + "b\r\nc\x0cd\n\n\n\n" + " " * 40 + "\ne  f\n"
    assert extraktion.begrenze_leerraum(text) == "a" + " " * 20 + "b\nc\nd\n\ne  f\n"
