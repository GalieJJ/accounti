"""belege freigeben — Nachprüfung Paket C (M1, N1–N3)."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.freigabe import FreigabeError, gib_frei
from accounti.db.repository import aktualisiere_beleg, lade_beleg, speichere_beleg
from accounti.models import BelegStatus
from accounti.pruefung.journal import lade_journal
from tests.pruefung_hilfe import beleg, make_session_fixture  # noqa: F401

# Prüfgrund der Erkennung (belege/erkennung.py) bei negiertem Korrekturbeleg
GEDREHT = (
    "Vorzeichen gedreht: Korrekturbeleg mit positiven Beträgen als Minderung "
    "übernommen; ist es keine Korrektur: belege freigeben … --vorzeichen umkehren"
)


def _zur_pruefung(make_session, grund=GEDREHT, **kw):
    b = beleg(
        netto=kw.pop("netto", "-100.00"),
        steuer=kw.pop("steuer", "-19.00"),
        brutto=kw.pop("brutto", "-119.00"),
        status=BelegStatus.ZUR_PRUEFUNG,
        pruef_grund=grund,
        **kw,
    )
    with make_session() as s:
        speichere_beleg(s, b)
        s.commit()
    return str(b.id)[:8], b


def test_vorzeichen_umkehren(make_session):
    """M1: Der Weg zurück, wenn die Erkennung eine Rechnung als Minderung negiert hat
    — vorher übernahm die Freigabe das Minus, ein erneuter Import war eine Dublette."""
    kurz, b = _zur_pruefung(make_session)
    with make_session() as s:
        neu = gib_frei(
            s, kurz, vorzeichen="umkehren", grund="Rechnung, keine Korrektur"
        )
        s.commit()
    with make_session() as s:
        gespeichert = lade_beleg(s, b.id)
    for x in (neu, gespeichert):
        assert x is not None
        assert (x.netto, x.steuer, x.brutto) == (
            Decimal("100.00"),
            Decimal("19.00"),
            Decimal("119.00"),
        )
        (p,) = x.positionen
        assert (p.netto, p.steuer_betrag) == (Decimal("100.00"), Decimal("19.00"))
        assert x.status is BelegStatus.ERFASST


def test_vorzeichen_nur_mit_grund_und_bekanntem_wert(make_session):
    kurz, _ = _zur_pruefung(make_session)
    with make_session() as s:
        with pytest.raises(FreigabeError, match="--grund"):
            gib_frei(s, kurz, vorzeichen="umkehren")
        with pytest.raises(FreigabeError, match="umkehren"):
            gib_frei(s, kurz, vorzeichen="plus", grund="x")


@pytest.mark.parametrize(
    "pruef_grund",
    [
        "Dublettenverdacht zu Beleg 1a2b3c4d: gleicher Betrag und Datum",
        "Rechenprobe stimmt nicht (Netto + Steuer ≠ Brutto oder Vorzeichen "
        "uneinheitlich)",
        GEDREHT,
        "Titel mehrdeutig: vor dem Titel „Gutschrift“ steht eine Zeile wie ein "
        "Rechnungstitel",
    ],
)
def test_freigabe_bei_ernstem_pruefgrund_nur_mit_grund(make_session, pruef_grund):
    """N2: Dublettenverdacht, Rechenprobe und gedrehtes Vorzeichen gab die Freigabe
    ohne Begründung frei (GoBD Rz. 58: Änderungen nachvollziehbar). Ein mehrdeutiger
    Titel (Runde 4, Mittel 1) ist dieselbe Entscheidung über das Vorzeichen."""
    kurz, _ = _zur_pruefung(make_session, pruef_grund)
    with make_session() as s:
        with pytest.raises(FreigabeError, match="--grund"):
            gib_frei(s, kurz)
        assert gib_frei(s, kurz, grund="Original geprüft").status is BelegStatus.ERFASST


def test_fehlendes_feld_braucht_keinen_grund(make_session):
    kurz, _ = _zur_pruefung(make_session, "fehlt: Steuerausweis")
    with make_session() as s:
        assert gib_frei(s, kurz).status is BelegStatus.ERFASST


def test_belegnummer_nachtragen(make_session):
    """N2: Fehlt die Belegnummer, trägt die Freigabe sie nach — nie in Konkurrenz zu
    einem anderen Beleg desselben Lieferanten."""
    kurz, b = _zur_pruefung(make_session, "fehlt: Belegnummer", nummer=None)
    _zur_pruefung(make_session, "x", nummer="G-17", datei_hash="b" * 64)
    with make_session() as s:
        with pytest.raises(FreigabeError, match="G-17"):
            gib_frei(s, kurz, belegnummer="G-17")
        neu = gib_frei(s, kurz, belegnummer="G-18")
        s.commit()
    assert neu.belegnummer == "G-18"


def test_steuerfall_ohne_ausweis_nicht_bei_steuer_in_der_summe(make_session):
    """N1: Netto 200, Brutto 238 — die Rechnung weist Steuer aus; § 13b, ig. Erwerb
    oder steuerfrei passen dazu nicht (das Kennzeichen buchte 94 auf das Brutto)."""
    kurz, _ = _zur_pruefung(
        make_session,
        "fehlt: Steuerausweis",
        netto="200.00",
        steuer=None,
        brutto="238.00",
        positionen=[("Gesamtbetrag", "238.00", None, None)],
    )
    with make_session() as s:
        with pytest.raises(FreigabeError, match="Netto"):
            gib_frei(s, kurz, steuer="13b")
        assert gib_frei(s, kurz).steuerkennzeichen is None


def test_journal_freigabe_nur_aus_belege_freigeben(make_session):
    """N3: Jeder Wechsel „zur Prüfung“ → „erfasst“ stand als beleg_freigegeben im
    Journal — auch der von belege erkennen, ohne dass ein Mensch freigab."""
    kurz, b = _zur_pruefung(make_session, "fehlt: Steuerausweis")
    zweiter, b2 = _zur_pruefung(
        make_session, "fehlt: Steuerausweis", nummer="RE-2", datei_hash="c" * 64
    )
    with make_session() as s:
        # wie belege erkennen: neu gelesen, jetzt vollständig
        aktualisiere_beleg(
            s, b.model_copy(update={"status": BelegStatus.ERFASST, "pruef_grund": None})
        )
        s.flush()
        gib_frei(s, zweiter, grund="Original geprüft")
        s.commit()
        vorgaenge = {
            e.objekt_id: e.vorgang
            for e in lade_journal(s)
            if e.vorgang.startswith("beleg_") and e.vorgang != "beleg_importiert"
        }
    assert vorgaenge == {str(b.id): "beleg_geaendert", str(b2.id): "beleg_freigegeben"}


def test_freigeben_zeigt_den_alten_pruefgrund(tmp_path):
    """N2: Wer freigibt, sieht, warum der Beleg in der Prüfung lag."""
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.db import init_db, session_factory
    from tests.pruefung_hilfe import db_url

    engine, make_session = session_factory(db_url(tmp_path))
    init_db(engine)
    kurz, _ = _zur_pruefung(make_session, "fehlt: Steuerausweis")
    engine.dispose()
    r = CliRunner().invoke(
        app,
        [
            "belege",
            "freigeben",
            kurz,
            "--db",
            db_url(tmp_path),
            "--config",
            str(tmp_path / "keine.yaml"),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "fehlt: Steuerausweis" in r.output


def test_belege_freigeben_vorzeichen_ueber_die_cli(tmp_path):
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.db import init_db, session_factory
    from tests.pruefung_hilfe import db_url

    engine, make_session = session_factory(db_url(tmp_path))
    init_db(engine)
    kurz, b = _zur_pruefung(make_session, tag=date(2026, 8, 10))
    args = ["--db", db_url(tmp_path), "--config", str(tmp_path / "keine.yaml")]
    ohne = CliRunner().invoke(
        app, ["belege", "freigeben", kurz, "--vorzeichen", "umkehren", *args]
    )
    assert ohne.exit_code == 1 and "--grund" in ohne.output
    r = CliRunner().invoke(
        app,
        [
            "belege",
            "freigeben",
            kurz,
            "--vorzeichen",
            "umkehren",
            "--grund",
            "Rechnung, keine Korrektur",
            *args,
        ],
    )
    assert r.exit_code == 0, r.output
    with make_session() as s:
        gespeichert = lade_beleg(s, b.id)
    engine.dispose()
    assert gespeichert is not None and gespeichert.brutto == Decimal("119.00")


def test_grund_auch_aus_dem_journal_kontext(make_session):
    """Web und API setzen den Grund über den Journal-Kontext."""
    from accounti.pruefung.person import journal_kontext

    kurz, _ = _zur_pruefung(make_session)
    with make_session() as s, journal_kontext(grund="Original geprüft"):
        assert gib_frei(s, kurz).status is BelegStatus.ERFASST
