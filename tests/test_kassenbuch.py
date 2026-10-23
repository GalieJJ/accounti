"""Kassenbuch: laufende Nummer, Bestand, Ablehnung negativer Bestände (Akzeptanz 4)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import update

from accounti.abschluss.kassenbuch import (
    KassenbuchError,
    KasseNegativError,
    anfangsbestand,
    bestand,
    buche_kasse,
    storniere,
    tagessalden,
    verlauf,
)
from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.db.repo_kasse import lade_kassenbuch
from accounti.db.repository import lade_buchungen, lade_transaktionen
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_kasse import KassenvorgangRow
from accounti.models import BuchungStatus
from tests.abschluss_hilfe import datenbank

D = Decimal
KASSE = KassenEinstellungen(konto="1000")


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


def _buche(make_session, betrag, tag, text="Vorgang", **kw):
    with make_session() as s:
        v = buche_kasse(s, D(betrag), text, KASSE, datum=tag, **kw)
        s.commit()
    return v


def _start(make_session, betrag="100", tag=date(2026, 3, 1)):
    with make_session() as s:
        anfangsbestand(s, D(betrag), tag, KASSE)
        s.commit()


def _bestand(make_session, bis=None):
    with make_session() as s:
        return bestand(lade_kassenbuch(s), bis)


def test_akzeptanz_4_negativer_bestand_wird_abgelehnt(make_session):
    _start(make_session)
    _buche(make_session, "-24.90", date(2026, 3, 2), "Porto")
    assert _bestand(make_session) == D("75.10")
    with pytest.raises(KasseNegativError, match="−4,90"):
        _buche(make_session, "-80.00", date(2026, 3, 3), "Druckerpatronen")
    # nichts gespeichert: kein Eintrag, keine Transaktion
    assert _bestand(make_session) == D("75.10")
    with make_session() as s:
        assert len(lade_kassenbuch(s)) == 2
        assert len(lade_transaktionen(s)) == 1


def test_rueckdatierte_ausgabe_die_spaeter_ins_minus_fuehrt(make_session):
    _start(make_session)
    _buche(make_session, "-90", date(2026, 3, 10))
    # am 05.03. wären noch 50 € da, aber am 10.03. −40 €
    with pytest.raises(KasseNegativError, match="10.03.2026"):
        _buche(make_session, "-50", date(2026, 3, 5))
    _buche(make_session, "30", date(2026, 3, 5), "Bareinnahme")
    _buche(make_session, "-40", date(2026, 3, 5))
    assert _bestand(make_session) == 0


def test_ohne_anfangsbestand_ist_jede_ausgabe_zu_viel(make_session):
    with pytest.raises(KasseNegativError):
        _buche(make_session, "-1", date(2026, 1, 2))
    with pytest.raises(KassenbuchError, match="0"):
        _buche(make_session, "0", date(2026, 1, 2))


def test_laufende_nummer_verlauf_und_tagessalden(make_session):
    _start(make_session)
    _buche(make_session, "50", date(2026, 3, 2), "Einnahme")
    _buche(make_session, "-20", date(2026, 3, 2), "Ausgabe")
    _buche(make_session, "-5", date(2026, 3, 1), "Nachtrag")  # rückdatiert, Nr. 4
    with make_session() as s:
        buch = lade_kassenbuch(s)
    assert [v.nr for v in buch] == [1, 2, 3, 4]
    assert [(v.nr, b) for v, b in verlauf(buch)] == [
        (1, D("100")),
        (4, D("95")),
        (2, D("145")),
        (3, D("125")),
    ]
    assert _bestand(make_session, date(2026, 3, 1)) == D("95")
    tage = tagessalden(buch, date(2026, 3, 1), date(2026, 3, 31))
    assert [(t.datum, t.einnahmen, t.ausgaben, t.bestand) for t in tage] == [
        (date(2026, 3, 1), D("100"), D("5"), D("95")),
        (date(2026, 3, 2), D("50"), D("20"), D("125")),
    ]


def test_transaktion_und_buchung_mit_steuer(make_session):
    _start(make_session, "500")
    aus = _buche(
        make_session,
        "-119",
        date(2026, 3, 2),
        "Bürobedarf",
        gegenkonto="4930",
        steuersatz=D("19"),
        belegnummer="Q-1",
    )
    ein = _buche(
        make_session,
        "119",
        date(2026, 3, 3),
        "Barverkauf",
        gegenkonto="8400",
        steuersatz=D("19"),
    )
    ohne = _buche(make_session, "-10", date(2026, 3, 4), "Trinkgeld")
    with make_session() as s:
        txs = {t.id: t for t in lade_transaktionen(s)}
        buchungen = {b.transaktion_id: b for b in lade_buchungen(s)}
    t = txs[aus.transaktion_id]
    assert (t.betrag, t.sachkonto, t.verwendungszweck) == (
        D("-119"),
        "1000",
        "Bürobedarf",
    )
    b = buchungen[aus.transaktion_id]
    assert (b.soll_konto, b.haben_konto, b.betrag_netto, b.steuer_schluessel) == (
        "4930",
        "1000",
        D("100.00"),
        9,
    )
    assert b.steuer_betrag == D("19.00") and b.status is BuchungStatus.GEPRUEFT
    assert b.beleg_nummer == "Q-1"
    e = buchungen[ein.transaktion_id]
    assert (e.soll_konto, e.haben_konto, e.betrag_netto, e.steuer_schluessel) == (
        "1000",
        "8400",
        D("100.00"),
        3,
    )
    # ohne Gegenkonto: nur die Transaktion — die Kontierung macht 'classify'
    assert ohne.transaktion_id in txs and ohne.transaktion_id not in buchungen


def test_unveraenderbar(make_session):
    _start(make_session)
    with make_session() as s:
        row = s.get(KassenvorgangRow, str(lade_kassenbuch(s)[0].id))
        row.betrag = D("1000")
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with make_session() as s:
        s.delete(s.get(KassenvorgangRow, str(lade_kassenbuch(s)[0].id)))
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with make_session() as s, pytest.raises(Exception, match="unveränderbar"):
        s.execute(update(KassenvorgangRow).values(text="geändert"))


def test_storno(make_session):
    _start(make_session)
    einnahme = _buche(make_session, "50", date(2026, 3, 2), "Einnahme")
    ausgabe = _buche(
        make_session, "-120", date(2026, 3, 3), "Ausgabe", gegenkonto="4930"
    )
    # Storno der Einnahme ließe den Bestand am 03.03. ins Minus fallen
    with make_session() as s, pytest.raises(KasseNegativError):
        storniere(s, einnahme.nr, "falsch erfasst", KASSE)
    with make_session() as s:
        st = storniere(s, ausgabe.nr, "doppelt erfasst", KASSE, datum=date(2026, 3, 4))
        s.commit()
    assert (st.betrag, st.storno_von) == (D("120"), ausgabe.nr)
    assert _bestand(make_session) == D("150")
    with make_session() as s:
        gegen = [b for b in lade_buchungen(s) if b.transaktion_id == st.transaktion_id]
    assert [(b.soll_konto, b.haben_konto, b.betrag_netto) for b in gegen] == [
        ("1000", "4930", D("120"))
    ]
    with make_session() as s, pytest.raises(KassenbuchError, match="schon storniert"):
        storniere(s, ausgabe.nr, "nochmal", KASSE)


def test_anfangsbestand_nur_einmal(make_session):
    _start(make_session)
    with make_session() as s, pytest.raises(KassenbuchError, match="Anfangsbestand"):
        anfangsbestand(s, D("10"), date(2026, 4, 1), KASSE)


def test_lange_freitexte_passen_in_die_spalten(make_session):
    """Postgres prüft die Spaltenlänge — gekürzt wird vorher, nicht abgelehnt."""
    _start(make_session)
    _buche(
        make_session,
        "-10",
        date(2026, 3, 2),
        text="T" * 300,
        belegnummer="B" * 80,
        von="V" * 80,
    )
    with make_session() as s:
        v = lade_kassenbuch(s)[-1]
    assert (len(v.text), v.belegnummer, v.erfasst_von) == (200, "B" * 60, "V" * 50)


# --- Kassen-Storno und Storno statt Änderung (Baustein 7, Befund B-M1) --------------


def _kassenbuchung(make_session):
    _start(make_session, "500")
    aus = _buche(
        make_session,
        "-119",
        date(2026, 3, 2),
        "Bürobedarf",
        gegenkonto="4930",
        steuersatz=D("19"),
    )
    return aus


def test_kassen_storno_nach_korrektur_kehrt_die_neubuchung_um(make_session):
    from accounti.db.repository import finde_buchung
    from accounti.pruefung.journal import pruefe_journal
    from accounti.pruefung.storno import korrigiere

    aus = _kassenbuchung(make_session)
    with make_session() as s:
        k = korrigiere(s, str(aus.buchung_id), "4940", "1000", steuer=9, von="erika")
        s.commit()
    with make_session() as s:
        st = storniere(s, aus.nr, "falsch erfasst", KASSE, datum=date(2026, 3, 4))
        s.commit()
        gegen = finde_buchung(s, str(st.buchung_id))
        neu = finde_buchung(s, str(k.neu.id))
        assert (gegen.soll_konto, gegen.haben_konto) == ("1000", "4940")
        assert gegen.storno_von == neu.id and neu.storniert_durch == gegen.id
        assert gegen.storniert_durch is None
        assert pruefe_journal(s).in_ordnung


def test_kassen_storno_ist_ein_storno_der_buchung(make_session):
    from accounti.db.repository import finde_buchung
    from accounti.pruefung.storno import StornoError, korrigiere

    aus = _kassenbuchung(make_session)
    with make_session() as s:
        st = storniere(s, aus.nr, "doppelt erfasst", KASSE, datum=date(2026, 3, 4))
        s.commit()
        assert finde_buchung(s, str(aus.buchung_id)).storniert_durch == st.buchung_id
        with pytest.raises(StornoError, match="schon storniert"):
            korrigiere(s, str(aus.buchung_id), "4940", "1000", steuer=9)


def test_kassen_storno_ohne_gueltige_buchung_abgelehnt(make_session):
    from accounti.pruefung.storno import storniere as storniere_buchung

    aus = _kassenbuchung(make_session)
    with make_session() as s:
        storniere_buchung(s, str(aus.buchung_id), grund="falsch", von="erika")
        s.commit()
    with make_session() as s, pytest.raises(KassenbuchError, match="ohne Neubuchung"):
        storniere(s, aus.nr, "falsch erfasst", KASSE)


# --- Gesamttest Abschluss B5/B9: Storno nach classify, nie vor dem Original ---------


def _classify_bucht(make_session, v, soll, haben, status=BuchungStatus.AUTO_GEBUCHT):
    """Wie classify: eine Buchung am Umsatz des Kassenvorgangs, ohne dass das (nur
    anfügbare) Kassenbuch davon erfährt."""
    from accounti.db.repository import speichere_buchung
    from accounti.models import Buchungssatz

    b = Buchungssatz(
        transaktion_id=v.transaktion_id,
        datum=v.datum,
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=abs(v.betrag),
        buchungstext=v.text,
        status=status,
    )
    with make_session() as s:
        speichere_buchung(s, b)
        s.commit()
    return b


def test_kassen_storno_nach_classify_kehrt_die_buchung_um(make_session):
    """Befund B5: ohne --konto kontiert classify den Umsatz; das Storno fand die
    Buchung nicht (nur ``kassenbuch.buchung_id``) und kehrte nichts um."""
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen
    from accounti.abschluss.salden import summen_und_salden
    from accounti.db.repo_pruefung import korrektur_zu
    from accounti.db.repository import finde_buchung, gebuchte_transaktion_ids
    from accounti.pruefung.journal import pruefe_journal

    _start(make_session, "100", date(2026, 1, 1))
    aus = _buche(make_session, "-50", date(2026, 2, 1), "Bareinzahlung auf Bank")
    assert aus.buchung_id is None
    gebucht = _classify_bucht(make_session, aus, "1360", "1000")
    with make_session() as s:
        st = storniere(s, aus.nr, "falsch", KASSE, datum=date(2026, 2, 3))
        s.commit()
    assert st.buchung_id is not None
    with make_session() as s:
        gegen = finde_buchung(s, str(st.buchung_id))
        original = finde_buchung(s, str(gebucht.id))
        assert (gegen.soll_konto, gegen.haben_konto, gegen.betrag_netto) == (
            "1000",
            "1360",
            D("50"),
        )
        assert gegen.storno_von == original.id
        assert original.storniert_durch == gegen.id
        assert korrektur_zu(s, original.id).storno_id == gegen.id
        # beide Umsätze gebucht, Kassenkonto = Kassenbuch, 1360 ausgeglichen
        assert {aus.transaktion_id, st.transaktion_id} <= gebuchte_transaktion_ids(s)
        susa = summen_und_salden(s, 2026, lade_kontenrahmen("SKR03"), "bilanz")
        assert susa.saldo("1000") == D("0") and susa.saldo("1360") == 0
        assert pruefe_journal(s).in_ordnung


def test_kassen_storno_nach_classify_und_korrektur(make_session):
    from accounti.db.repository import finde_buchung
    from accounti.pruefung.storno import korrigiere

    _start(make_session)
    aus = _buche(make_session, "-30", date(2026, 3, 2), "Porto")
    gebucht = _classify_bucht(make_session, aus, "4930", "1000")
    with make_session() as s:
        k = korrigiere(s, str(gebucht.id), "4910", "1000", von="erika")
        s.commit()
    with make_session() as s:
        st = storniere(s, aus.nr, "doppelt", KASSE, datum=date(2026, 3, 5))
        s.commit()
        gegen = finde_buchung(s, str(st.buchung_id))
    assert (gegen.soll_konto, gegen.haben_konto) == ("1000", "4910")
    assert gegen.storno_von == k.neu.id


def test_kassen_storno_nach_classify_mit_splitbuchung(make_session):
    _start(make_session)
    aus = _buche(make_session, "-30", date(2026, 3, 2), "Bürobedarf und Porto")
    for konto, betrag in (("4930", "20"), ("4910", "10")):
        _classify_bucht(
            make_session, aus.model_copy(update={"betrag": D(betrag)}), konto, "1000"
        )
    with make_session() as s:
        st = storniere(s, aus.nr, "falsch", KASSE, datum=date(2026, 3, 4))
        s.commit()
        gegen = sorted(
            (b.soll_konto, b.haben_konto, b.betrag_netto)
            for b in lade_buchungen(s)
            if b.transaktion_id == st.transaktion_id
        )
    assert gegen == [("1000", "4910", D("10")), ("1000", "4930", D("20"))]


def test_kassen_storno_eines_vorschlags_abgelehnt(make_session):
    _start(make_session)
    aus = _buche(make_session, "-30", date(2026, 3, 2), "Porto")
    _classify_bucht(make_session, aus, "4930", "1000", BuchungStatus.ZUR_PRUEFUNG)
    with make_session() as s, pytest.raises(KassenbuchError, match="Vorschlag"):
        storniere(s, aus.nr, "falsch", KASSE, datum=date(2026, 3, 4))


def test_kassen_storno_ungebucht_bleibt_ohne_buchung(make_session):
    _start(make_session)
    aus = _buche(make_session, "-30", date(2026, 3, 2), "Porto")
    with make_session() as s:
        st = storniere(s, aus.nr, "falsch", KASSE, datum=date(2026, 3, 4))
        s.commit()
    assert st.buchung_id is None and _bestand(make_session) == D("100")


def test_kassen_storno_nie_vor_dem_original(make_session):
    """Befund B9: ein rückdatiertes Storno machte den Bestand zwischen Storno und
    Original falsch und berichtigte die Umsatzsteuer vor dem Umsatz."""
    _start(make_session, "300", date(2026, 1, 1))
    ein = _buche(
        make_session,
        "119",
        date(2026, 3, 15),
        "Barverkauf",
        gegenkonto="8400",
        steuersatz=D("19"),
    )
    with make_session() as s, pytest.raises(KassenbuchError, match="vor Nr. 2"):
        storniere(s, ein.nr, "Irrtum", KASSE, datum=date(2026, 2, 1))
    with make_session() as s:
        assert len(lade_kassenbuch(s)) == 2
        st = storniere(s, ein.nr, "Irrtum", KASSE, datum=date(2026, 3, 15))
        s.commit()
    assert st.datum == date(2026, 3, 15)


def test_kassen_storno_ohne_datum_fruehestens_am_tag_des_originals(make_session):
    morgen = date.today().replace(year=date.today().year + 1, month=1, day=2)
    _start(make_session, "300", date.today())
    ein = _buche(make_session, "50", morgen, "Vorausgezahlt", gegenkonto="8400")
    with make_session() as s:
        st = storniere(s, ein.nr, "Irrtum", KASSE)
        s.commit()
    assert st.datum == morgen


def test_cli_kassen_storno_nach_classify(tmp_path, monkeypatch):
    """Befund B5 wie im Gesamttest: kasse buchen ohne --konto, classify, kasse storno
    — danach meldet abschluss pruefen weder ungebuchte Umsätze noch eine Kasse ≠
    Kassenbuch."""
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.db import init_db, session_factory

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        '- {name: einzahlung, muster: "^Bareinzahlung auf Bank", soll_konto: "1360",'
        ' haben_konto: "1200", buchungstext: "Bareinzahlung Geldtransit"}\n',
        encoding="utf-8",
    )
    url = f"sqlite:///{(tmp_path / 'k.db').as_posix()}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    engine.dispose()
    konfig = str(tmp_path / "accounti.yaml")
    runner = CliRunner()

    def run(*args):
        r = runner.invoke(
            app, [*args, "--db", url, "--config", konfig], env={"COLUMNS": "250"}
        )
        return r, " ".join(r.output.split())

    for konto, saldo in (("1000", "100"), ("0880", "-100")):
        r, _ = run(
            "abschluss",
            "eroeffnung",
            "--jahr",
            "2026",
            "--konto",
            konto,
            "--saldo",
            saldo,
            "--von",
            "t",
        )
        assert r.exit_code == 0, r.output
    run("kasse", "anfangsbestand", "--betrag", "100", "--datum", "2026-01-01")
    r, _ = run(
        "kasse",
        "buchen",
        "--betrag",
        "-50",
        "--text",
        "Bareinzahlung auf Bank",
        "--datum",
        "2026-02-01",
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["classify", "--no-llm", "--db", url, "--config", konfig])
    assert r.exit_code == 0, r.output
    r, text = run("kasse", "storno", "2", "--grund", "falsch", "--datum", "2026-02-01")
    assert r.exit_code == 0, r.output
    assert "noch nicht kontiert" not in text
    r, text = run("kasse", "storno", "1", "--grund", "x")
    assert r.exit_code == 1 and "kann nicht storniert" in text
    r, text = run("abschluss", "pruefen", "--jahr", "2026")
    assert "kasse:" not in text and "ungebucht:" not in text, text
    with fabrik() as s:
        paare = sorted(
            (b.soll_konto, b.haben_konto, b.storno_von is not None)
            for b in lade_buchungen(s)
            if not (b.beleg_nummer or "").startswith("EB-")
        )
    assert paare == [("1000", "1360", True), ("1360", "1000", False)]
