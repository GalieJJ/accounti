"""OP-Liste zum Stichtag, Prüfregeln (Gesamttest Ausgang B8, B11, Nebenbefund B12)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    speichere_ausgangsrechnung,
    speichere_posten,
    speichere_transaktion,
    speichere_zuordnung,
)
from accounti.erechnung.ausstellung import stelle_aus
from accounti.models import (
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.models.pruefung import Schwere
from tests.pruefung_hilfe import (
    anlegen,
    kontakt,
    make_session_fixture,  # noqa: F401 - Fixture
)
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos
from tests.test_pruefung_regeln import pruefe

D = Decimal
runner = CliRunner()


# --- B8: Offene Posten zum Stichtag --------------------------------------------------


def test_offene_posten_zum_stichtag(tmp_path):
    from tests.zahlung_hilfe import debitor, posten, speichere

    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    k = debitor(name="Kunde GmbH", konto="10000")
    alt = posten(
        k, "2026-0001", "1190.00", belegdatum=date(2026, 12, 10),
        faellig=date(2026, 12, 24), richtung=PostenRichtung.FORDERUNG, rest="0.00",
    )  # fmt: skip
    neu = posten(
        k, "2027-0001", "1190.00", belegdatum=date(2027, 1, 5),
        faellig=date(2027, 1, 19), richtung=PostenRichtung.FORDERUNG,
    )  # fmt: skip
    speichere(fabrik, [k], [alt, neu])
    t = Transaktion(
        datum=date(2027, 1, 12), betrag=D("1190.00"), verwendungszweck="RE 2026-0001",
        quelle=TransaktionQuelle.BANK, rohtext="x",
    )  # fmt: skip
    with fabrik() as s:
        speichere_transaktion(s, t)
        speichere_zuordnung(
            s,
            Zahlungszuordnung(
                transaktion_id=t.id, posten_id=alt.id, betrag=D("1190.00"),
                stufe="referenz", status=ZuordnungStatus.GEBUCHT, confidence=1.0,
                begruendung="x",
            ),
        )  # fmt: skip
        s.commit()
    engine.dispose()
    r = runner.invoke(app, ["opos", "liste", "--stichtag", "2026-12-31", "--db", url])
    assert "2026-0001" in r.output and "2027-0001" not in r.output
    assert "1.190,00" in r.output
    spaeter = runner.invoke(
        app, ["opos", "liste", "--stichtag", "2027-02-01", "--db", url]
    )
    assert "2027-0001" in spaeter.output and "2026-0001" not in spaeter.output
    staffel = runner.invoke(
        app, ["opos", "staffel", "--stichtag", "2026-12-31", "--db", url]
    )
    assert "1.190,00" in staffel.output


# --- B11: Prüfregel beleg_ohne_zahlung ----------------------------------------------


def test_beleg_ohne_zahlung_nennt_mahnlauf_und_teilzahlung(make_session):
    k = kontakt()
    p = OffenerPosten(
        kontakt_id=k.id, beleg_id=uuid4(), richtung=PostenRichtung.FORDERUNG,
        belegnummer="2026-0001", belegdatum=date(2026, 7, 13), betrag=D("5950.00"),
        restbetrag=D("3950.00"), faellig_am=date(2026, 7, 27),
        status=PostenStatus.TEILBEZAHLT,
    )  # fmt: skip
    anlegen(make_session, k)
    with make_session() as s:
        speichere_posten(s, p)
        s.commit()
    (b,) = pruefe(make_session, "beleg_ohne_zahlung", stichtag=date(2026, 8, 31))
    assert "accounti mahnwesen lauf" in b.abhilfe
    assert "Teilzahlung" in b.text and "3.950,00" in b.text
    assert b.schwere is Schwere.HINWEIS


# --- Nebenbefund B12: unbearbeitete Ausgangsrechnung nennt den Kunden --------------


def test_unbearbeitete_ausgangsrechnung_nennt_den_kunden(make_session, tmp_path):
    archiv = BelegArchiv(tmp_path / "archiv")
    with make_session() as s:
        e = entwurf(kunde(), pos("Ware", "100"))
        speichere_ausgangsrechnung(s, e)
        stelle_aus(
            s,
            archiv,
            str(e.id)[:8],
            FIRMA,
            date(2026, 3, 10),
            erstellt_am=datetime(2026, 3, 10, 9).astimezone(),
        )
        s.commit()
    (b,) = pruefe(make_session, "beleg_unbearbeitet")
    assert b.gegenpartei == "Atelier Kundin GmbH"
    assert "Galerie Muster" not in b.text
