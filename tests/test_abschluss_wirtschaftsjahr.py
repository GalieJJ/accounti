"""Abweichendes Wirtschaftsjahr im Jahresabschluss (Gesamttest Betrieb B5).

Der Abschluss rechnete fest 01.01.–31.12.; ``datev.wirtschaftsjahr_beginn`` der
Gesellschaft wurde nicht gelesen. Konvention: ``--jahr`` ist das Kalenderjahr des
Wirtschaftsjahresendes (§ 4a Abs. 2 Nr. 2 EStG).
"""

from datetime import date
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.abschluss.abgrenzung import (
    bestaetige_abgrenzung,
    schlage_abgrenzungen_vor,
)
from accounti.abschluss.euer import erstelle_euer, verteilung_4a
from accounti.abschluss.konfiguration import (
    lade_abschluss,
    wirtschaftsjahr,
    wirtschaftsjahr_zum,
)
from accounti.abschluss.pruefungen import kontext, pruefe_abschluss
from accounti.abschluss.salden import summen_und_salden
from accounti.abschluss.vortrag import AbschlussError, erfasse_eroeffnung, trage_vor
from accounti.anlagen.rechtsstand import lade_rechtsstand
from accounti.cli import app
from accounti.db.repository import lade_buchungen
from accounti.konfiguration import KonfigurationError
from accounti.models import BuchungStatus
from tests.abschluss_hilfe import anlegen, buche, datenbank

D = Decimal
JULI = date(2025, 7, 1)


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


def _config(tmp_path, gewinnermittlung="euer", beginn='"2025-07-01"'):
    datei = tmp_path / "accounti.yaml"
    datei.write_text(
        f"datev:\n  wirtschaftsjahr_beginn: {beginn}\n"
        f"abschluss:\n  gewinnermittlung: {gewinnermittlung}\n",
        encoding="utf-8",
    )
    return datei


# --- der Helfer ----------------------------------------------------------------------


def test_wirtschaftsjahr_heisst_nach_dem_jahr_seines_endes():
    kj = wirtschaftsjahr(2026)
    assert (kj.von, kj.bis, kj.bezeichnung, kj.abweichend) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
        "2026",
        False,
    )
    assert kj.kalenderjahre == [(2026, 12)]
    wj = wirtschaftsjahr(2026, JULI)
    assert (wj.von, wj.bis, wj.bezeichnung, wj.abweichend) == (
        date(2025, 7, 1),
        date(2026, 6, 30),
        "2025/2026",
        True,
    )
    assert wj.kalenderjahre == [(2025, 12), (2026, 6)]
    assert wj.enthaelt(date(2025, 7, 1)) and not wj.enthaelt(date(2026, 7, 1))
    # nur Tag und Monat zählen; ein Februar-Beginn bleibt im Februar
    assert wirtschaftsjahr(2026, date(2019, 7, 1)) == wj
    assert wirtschaftsjahr(2026, date(2020, 2, 29)).von == date(2025, 2, 28)
    assert wirtschaftsjahr_zum(date(2025, 8, 1), JULI) == wj
    assert wirtschaftsjahr_zum(date(2026, 6, 30), JULI) == wj
    assert wirtschaftsjahr_zum(date(2026, 7, 1), JULI).jahr == 2027


@pytest.mark.parametrize("beginn", ['"2025-07-01"', "2024-07-01"])
def test_beginn_aus_datev_abschnitt(tmp_path, beginn):
    einst = lade_abschluss(_config(tmp_path, beginn=beginn))
    assert einst.abweichendes_wirtschaftsjahr
    assert einst.wirtschaftsjahr(2026).von == JULI
    ohne = lade_abschluss(tmp_path / "fehlt.yaml")
    assert not ohne.abweichendes_wirtschaftsjahr
    assert ohne.wirtschaftsjahr(2026).von == date(2026, 1, 1)


def test_falsches_format(tmp_path):
    with pytest.raises(KonfigurationError, match="JJJJ-MM-TT"):
        lade_abschluss(_config(tmp_path, beginn='"1. Juli"'))


# --- Saldenliste, Prüfungen, EÜR ------------------------------------------------------


def _drei_buchungen(make_session):
    buche(make_session, date(2025, 6, 30), "4930", "1200", "1")  # WJ 2024/2025
    buche(make_session, date(2025, 8, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 3, 1), "4930", "1200", "200")
    buche(make_session, date(2026, 7, 1), "4930", "1200", "50")  # WJ 2026/2027


def test_saldenliste_ueber_das_wirtschaftsjahr(make_session, tmp_path):
    """Befund B5: ``susa --jahr 2025`` zeigte bei WJ 01.07.–30.06. nur Juli bis
    Dezember 2025."""
    einst = lade_abschluss(_config(tmp_path))
    _drei_buchungen(make_session)
    with make_session() as s:
        susa = summen_und_salden(
            s,
            2026,
            einst.lade_kontenrahmen(),
            "euer",
            wj=einst.wirtschaftsjahr(2026),
        )
    assert (susa.von, susa.bis) == (JULI, date(2026, 6, 30))
    assert susa.saldo("4930") == D("200") and susa.saldo("8400") == D("-1000")
    assert susa.ergebnis == D("800")


def test_pruefungen_zum_ende_des_wirtschaftsjahres(make_session, tmp_path):
    config = _config(tmp_path)
    buche(make_session, date(2025, 9, 1), "4930", "1200", "10", status="pruefung")
    buche(make_session, date(2026, 9, 1), "4930", "1200", "10", status="pruefung")
    with make_session() as s:
        k = kontext(s, 2026, config)
        assert k.stichtag == date(2026, 6, 30)
        (b,) = pruefe_abschluss(k, ["unfreigegeben"])
    assert "1 Buchung im Jahr 2025/2026" in b.text


def test_euer_mit_verteilung_nach_paragraf_4a(make_session, tmp_path):
    """L+F mit EÜR: Gewinn zeitanteilig auf zwei Kalenderjahre (§ 4a Abs. 2 Nr. 1
    EStG) — accounti nennt die Verteilung, trägt sie aber nicht ein."""
    einst = lade_abschluss(_config(tmp_path))
    _drei_buchungen(make_session)
    kr = einst.lade_kontenrahmen()
    with make_session() as s:
        susa = summen_und_salden(s, 2026, kr, "euer", wj=einst.wirtschaftsjahr(2026))
    e = erstelle_euer(susa, kr)
    assert e.gewinn == D("800") and e.vordruck_jahr <= 2026
    (hinweis,) = [h for h in e.hinweise if "§ 4a" in h]
    assert "2025/2026 (01.07.2025–30.06.2026)" in hinweis
    assert "2025: 400,00 € (6 Monate), 2026: 400,00 € (6 Monate)" in hinweis
    assert "Nr. 2" in hinweis
    # Beginn nicht am Monatsersten: nach Tagen
    wj = wirtschaftsjahr(2026, date(2025, 7, 15))
    (j1, a1, z1), (j2, a2, z2) = verteilung_4a(D("365"), wj)
    assert (j1, a1, z1, j2, a2, z2) == (
        2025,
        D("170"),
        "170 Tage",
        2026,
        D("195"),
        "195 Tage",
    )


# --- Abgrenzung, Eröffnung, Vortrag ---------------------------------------------------


def test_abgrenzung_zum_ende_des_wirtschaftsjahres(make_session, tmp_path):
    einst = lade_abschluss(_config(tmp_path, gewinnermittlung="bilanz"))
    buche(
        make_session,
        date(2026, 6, 1),
        "4360",
        "1200",
        "1200",
        text="Versicherung 01.06.2026 – 31.05.2027",
    )
    with make_session() as s:
        lauf = schlage_abgrenzungen_vor(s, 2026, einst, lade_rechtsstand())
        (a,) = lauf.vorschlaege
        assert a.betrag == D("1100.00")  # 11 von 12 Monaten nach dem 30.06.2026
        assert "30.06.2026" in a.rechenweg
        bestaetige_abgrenzung(s, str(a.nr), "chef", einst.wirtschaftsjahr_beginn)
        s.commit()
        rap = sorted(
            (b.datum, b.soll_konto, b.haben_konto, b.betrag_netto)
            for b in lade_buchungen(s)
            if (b.beleg_nummer or "").startswith("RAP-")
        )
    assert rap == [
        (date(2026, 6, 30), "0980", "4360", D("1100.00")),
        (date(2026, 7, 1), "4360", "0980", D("1100.00")),
    ]


def test_eroeffnung_am_wirtschaftsjahresbeginn_und_kein_vortrag(make_session, tmp_path):
    config = _config(tmp_path, gewinnermittlung="bilanz")
    einst = lade_abschluss(config)
    with make_session() as s:
        b = erfasse_eroeffnung(s, 2026, "1200", D("5000"), "chef", einst)
        erfasse_eroeffnung(s, 2026, "0880", D("-5000"), "chef", einst)
        s.commit()
    assert (b.datum, b.beleg_nummer) == (JULI, "EB-2025")
    with make_session() as s:
        k = kontext(s, 2026, config)
        assert k.susa.zeile("1200").eb == D("5000")
        assert pruefe_abschluss(k, ["vortragskonten"]) == []
        # Saldovortrag und Jahressperre: nur im Kalenderjahr — abgelehnt statt falsch
        with pytest.raises(AbschlussError, match="Abweichendes Wirtschaftsjahr"):
            trage_vor(s, k, "chef")


# --- Anlagen: AfA-Lauf über zwei Kalenderjahre ----------------------------------------


def test_abschluss_buchen_und_pruefen_mit_anlage(make_session, tmp_path):
    config = _config(tmp_path, gewinnermittlung="bilanz")
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    buche(make_session, date(2025, 9, 1), "0420", "1200", "36000")
    anlegen(make_session, "36000", date(2025, 9, 1), nd=3, konto="0420")
    runner = CliRunner()

    def run(*args):
        r = runner.invoke(
            app,
            ["abschluss", *args, "--db", url, "--config", str(config)],
            env={"COLUMNS": "200"},
        )
        return r, " ".join(r.output.split())

    r, text = run("pruefen", "--jahr", "2026")
    assert "AfA 2025 nicht vollständig" in text
    assert "--jahr 2026 --bis-monat 6" in text
    r, text = run("buchen", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    # Sep–Dez 2025 und Jan–Jun 2026: 4 + 6 Monate × 1.000 €
    assert "AfA 2025 ab 07 (zur Prüfung)" in text and "4.000,00" in text
    assert "AfA 2026 bis 06 (zur Prüfung)" in text and "6.000,00" in text
    with make_session() as s:
        for b in lade_buchungen(s, status={BuchungStatus.ZUR_PRUEFUNG}):
            from accounti.db.repository import setze_status

            setze_status(s, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von="chef")
        s.commit()
        befunde = pruefe_abschluss(kontext(s, 2026, config), ["anlagen"])
    assert befunde == []  # 0420: 36.000 − 10.000 = Restbuchwert zum 30.06.2026
    r, text = run("susa", "--jahr", "2026")
    assert "Summen- und Saldenliste 2025/2026 (01.07.2025 bis 30.06.2026)" in text
    r, text = run("vortrag", "--jahr", "2026", "--von", "chef")
    assert r.exit_code == 1 and "Abweichendes Wirtschaftsjahr" in text


def test_warnung_fuer_afa_je_wirtschaftsjahr(make_session, tmp_path):
    """Degressive AfA, Sammelposten und E-Fahrzeug-Staffel gelten je
    Wirtschaftsjahr — der Plan rechnet im Kalenderjahr: Warnung statt Stille."""
    from accounti.abschluss.pruefungen import Schwere
    from accounti.models.anlagen import AfaArt

    config = _config(tmp_path, gewinnermittlung="bilanz")
    anlegen(make_session, "30000", date(2025, 9, 1), nd=10, konto="0420")
    anlegen(
        make_session, "30000", date(2025, 9, 1), art=AfaArt.DEGRESSIV, nd=10,
        konto="0420",
    )  # fmt: skip
    with make_session() as s:
        warnungen = [
            b.text
            for b in pruefe_abschluss(kontext(s, 2026, config), ["anlagen"])
            if b.schwere is Schwere.WARNUNG
        ]
    assert (
        len(warnungen) == 1 and "Anlagegut Nr. 2 mit dem Steuerberater" in warnungen[0]
    )


# --- Nachprüfung F: AfA je Abschnitt des Kalenderjahres -------------------------------


def _alles_freigeben(make_session):
    from accounti.db.repository import setze_status

    with make_session() as s:
        for b in lade_buchungen(s, status={BuchungStatus.ZUR_PRUEFUNG}):
            setze_status(s, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von="chef")
        s.commit()


def test_afa_im_ersten_wirtschaftsjahr_mit_altbestand(make_session, tmp_path):
    """Nachprüfung F, N1: Im ersten abweichenden WJ rechnete ``afa_lauf(2025, 12)``
    Januar bis Dezember 2025 — Januar bis Juni gehören zum Vor-WJ, dessen AfA im
    Eröffnungssaldo steckt; vorgeschlagen wurden 18 Monate (§ 7 Abs. 1 EStG: AfA je
    Wirtschaftsjahr). Maschine 01.01.2020, 12.000 €, 10 Jahre: 100 €/Monat,
    Restbuchwert 30.06.2025 = 5.400 €."""
    config = _config(tmp_path, gewinnermittlung="bilanz")
    einst = lade_abschluss(config)
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    anlegen(make_session, "12000", date(2020, 1, 1), nd=10, konto="0420")
    with make_session() as s:
        erfasse_eroeffnung(s, 2026, "0420", D("5400"), "chef", einst)
        erfasse_eroeffnung(s, 2026, "0880", D("-5400"), "chef", einst)
        s.commit()
    runner = CliRunner()

    def run(*args):
        r = runner.invoke(
            app,
            [*args, "--db", url, "--config", str(config)],
            env={"COLUMNS": "200"},
        )
        assert r.exit_code == 0, r.output
        return " ".join(r.output.split())

    text = run("abschluss", "buchen", "--jahr", "2026")
    assert "AfA 2025 ab 07 (zur Prüfung)" in text and "AfA 2026 bis 06" in text
    assert "1.200,00" not in text and text.count("600,00") >= 2
    _alles_freigeben(make_session)

    def anlagenbefunde(jahr):
        with make_session() as s:
            return [
                b.text for b in pruefe_abschluss(kontext(s, jahr, config), ["anlagen"])
            ]

    assert anlagenbefunde(2026) == []  # 0420: 5.400 − 1.200 = 4.200 zum 30.06.2026
    # der AfA-Lauf von Hand kennt den Abschnitt ebenso — nichts nachzubuchen
    assert "nichts zu buchen" in run("anlagen", "afa", "--jahr", "2025")
    assert "nichts zu buchen" in run(
        "anlagen", "afa", "--jahr", "2026", "--bis-monat", "6"
    )
    # das Folge-WJ bucht Juli–Dezember 2026; das WJ 2026 bleibt dabei stimmig
    text = run("abschluss", "buchen", "--jahr", "2027")
    assert "AfA 2026 ab 07 (zur Prüfung)" in text and "AfA 2027 bis 06" in text
    assert "1.200,00" not in text and "Korrektur" not in text
    _alles_freigeben(make_session)
    assert anlagenbefunde(2026) == []
    assert not [t for t in anlagenbefunde(2027) if "AfA" in t]
    # erneut gebucht: idempotent in beiden Wirtschaftsjahren
    assert "nichts zu buchen" in run("abschluss", "buchen", "--jahr", "2026")
    with make_session() as s:
        assert not lade_buchungen(s, status={BuchungStatus.ZUR_PRUEFUNG})


def test_abgang_im_ersten_wirtschaftsjahr_ohne_vorjahres_afa(make_session, tmp_path):
    """N1 auch beim Abgang: AfA nur ab Beginn des Wirtschaftsjahres (Juli–September
    statt Januar–September 2025)."""
    from accounti.anlagen.abgang import buche_abgang
    from accounti.anlagen.konfiguration import lade_anlagen

    config = _config(tmp_path, gewinnermittlung="bilanz")
    g = anlegen(make_session, "12000", date(2020, 1, 1), nd=10, konto="0420")
    anlagen = lade_anlagen(config)
    with make_session() as s:
        e = buche_abgang(s, str(g.nr), date(2025, 9, 30), anlagen)
        s.commit()
    assert e.afa.summe == D("300")
    assert e.restbuchwert == D("5100")


def test_aenderung_rechnet_jeden_abschnitt_neu(make_session, tmp_path):
    """N1 bei ``anlagen aendern``: Je Kalenderjahr gibt es bei abweichendem WJ zwei
    Abschnitte — beide werden neu gerechnet, nicht nur der mit dem spätesten Monat."""
    from accounti.anlagen.aenderung import aendere_anlage
    from accounti.anlagen.konfiguration import lade_anlagen
    from accounti.anlagen.lauf import afa_lauf

    config = _config(tmp_path, gewinnermittlung="bilanz")
    anlagen = lade_anlagen(config)
    g = anlegen(make_session, "12000", date(2020, 1, 1), nd=10, konto="0420")
    with make_session() as s:
        for jahr, monat in [(2025, 12), (2026, 6), (2026, 12), (2027, 6)]:
            assert afa_lauf(s, jahr, anlagen, monat).summe == D("600")
        s.commit()
    _alles_freigeben(make_session)
    with make_session() as s:
        a = aendere_anlage(
            s, str(g.nr), anlagen, kosten=D("13200"), grund="Tippfehler AK"
        )
        s.commit()
    # 110 statt 100 €/Monat: je Abschnitt 6 × 10 € AfA nachzubuchen
    assert sorted(
        (lauf.jahr, lauf.ab_monat, lauf.bis_monat, lauf.summe)
        for lauf in a.neuberechnung.afa
    ) == [
        (2025, 7, 12, D("60")),
        (2026, 1, 6, D("60")),
        (2026, 7, 12, D("60")),
        (2027, 1, 6, D("60")),
    ]
