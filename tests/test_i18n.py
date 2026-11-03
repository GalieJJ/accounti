"""Kern der Zweisprachigkeit: Sprachwahl, Katalog, Formate (Baustein 10b, Paket 2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from markupsafe import Markup

from accounti.i18n import (
    Text,
    aus_accept_language,
    betrag,
    datum,
    euro,
    gettext,
    monat,
    ngettext,
    prozent,
    sprache_aktiv,
    waehle_sprache,
)


def test_accept_language_mit_q_werten():
    assert aus_accept_language("de-DE,de;q=0.9,en;q=0.8") == "de"
    assert aus_accept_language("fr-FR,fr;q=0.9,en-GB;q=0.8,de;q=0.7") == "en"
    assert aus_accept_language("de;q=0.5, en;q=0.9") == "en"
    assert aus_accept_language("en;q=0, de;q=0.1") == "de"
    assert aus_accept_language("fr, it") is None
    assert aus_accept_language("") is None and aus_accept_language(None) is None
    assert aus_accept_language("en;q=kaputt, de") == "de"
    # Leerraum um Trenner und q-Wert
    assert aus_accept_language("  de ; q = 0.5 ,\ten\t;\tq=0.9  ") == "en"


def test_accept_language_ohne_quadratische_laufzeit():
    """Gefunden bei der Suche nach Stellen wie F-B1 (Folgepaket F, Runde 2): Ein Teil
    mit langer Leerraumfolge vor einem Fehler („de“ + 16 000 Leerzeichen + „;q=1 x“)
    brauchte 1,2 s — jede Aufteilung der Folge auf zwei ``\\s*``. Jetzt linear."""
    import time

    for kopf, erwartet in (
        ("de" + " " * 60_000 + ";q=1 x", None),
        ("a" + " " * 60_000 + "x", None),
        ("en" + "\t" * 60_000 + "x", None),
        ("de;q=1" + " " * 60_000 + "x", None),
        ("de; q=" + "1" * 60_000 + "x", None),
        ("fr" + " " * 60_000 + ";q=1 x,en", "en"),
        ("en" + " " * 60_000 + ";q=0.5" + " " * 60_000, "en"),
    ):
        beginn = time.perf_counter()
        ergebnis = aus_accept_language(kopf)
        dauer = time.perf_counter() - beginn
        assert dauer < 0.25, (kopf[:8], dauer)  # vorher 16 s (60 000 Zeichen)
        assert ergebnis == erwartet, kopf[:8]


def test_benutzersprache_gewinnt():
    assert waehle_sprache("de", "en-US,en;q=0.9") == "de"
    assert waehle_sprache("en", "de") == "en"
    assert waehle_sprache(None, "en-US") == "en"


def test_unbekannte_sprache_faellt_auf_standard():
    assert waehle_sprache(None, "fr") == "de"
    assert waehle_sprache("fr", None, standard="en") == "en"
    assert waehle_sprache(None, None, standard="xx") == "de"


def test_fehlender_eintrag_bleibt_deutsch():
    assert gettext("Kein Eintrag im Katalog vorhanden", "en") == (
        "Kein Eintrag im Katalog vorhanden"
    )
    assert gettext("Anmelden", "en") == "Sign in"
    assert gettext("Anmelden", "de") == "Anmelden"
    with sprache_aktiv("en"):
        assert gettext("Anmelden") == "Sign in"
    assert gettext("Anmelden") == "Anmelden"


def test_platzhalter_werden_escaped():
    from accounti.api.vorlagen import UMGEBUNG

    vorlage = UMGEBUNG.from_string(
        '{{ _("Gesellschaft: <strong>%(name)s</strong>", name=name) }}'
    )
    html = vorlage.render(name="<script>x</script>", sprache="en")
    assert html == "Company: <strong>&lt;script&gt;x&lt;/script&gt;</strong>"
    t = Text("Ihre Rolle in %(gesellschaft)s erlaubt das nicht", gesellschaft="<b>")
    assert str(t) == "Ihre Rolle in <b> erlaubt das nicht"
    assert t.uebersetzt("en") == "Your role in <b> does not allow this"
    assert not isinstance(t.uebersetzt("en"), Markup)  # escaped beim Rendern


def test_mehrzahl():
    einzahl, mehrzahl = "%(num)s Buchung", "%(num)s Buchungen"
    assert ngettext(einzahl, mehrzahl, 1, "en") == "%(num)s booking"
    assert ngettext(einzahl, mehrzahl, 3, "en") == "%(num)s bookings"
    assert ngettext(einzahl, mehrzahl, 3, "de") == "%(num)s Buchungen"


def test_formate_je_sprache():
    wert = Decimal("1234.5")
    assert (betrag(wert, "de"), betrag(wert, "en")) == ("1.234,50", "1,234.50")
    assert (betrag(Decimal("-0.5"), "de"), betrag(Decimal("-0.5"), "en")) == (
        "-0,50",
        "-0.50",
    )
    assert betrag(None, "en") == "—" and datum(None, "de") == "—"
    tag = date(2026, 10, 21)
    assert (datum(tag, "de"), datum(tag, "en")) == ("21.10.2026", "2026-10-21")
    assert (euro(wert, "de"), euro(wert, "en")) == ("1.234,50 €", "€1,234.50")
    assert euro(Decimal("-5"), "en") == "-€5.00"
    assert (prozent(12.5, "de"), prozent(12.5, "en")) == ("12,5 %", "12.5%")
    assert (monat(3, "de"), monat(3, "en")) == ("März", "March")
