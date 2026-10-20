"""Dauerfristverlängerung und Sondervorauszahlung (§§ 46–48 UStDV, USt 5 E 2026)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_elster import lade_uebermittlungen
from accounti.db.repository import lade_posten
from accounti.elster.datensatz import lies_kennzahlen
from accounti.elster.dauerfrist import (
    DauerfristError,
    berechne_svz,
    gib_dauerfrist_frei,
    uebermittle_dauerfrist,
)
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.elster.protokoll import neuer_eintrag, protokolliere
from accounti.elster.uebermittlung import AttrappenUebermittler, UebermittlungError
from accounti.elster.ustva import bereite_vor
from accounti.konfiguration import Buchhaltung
from accounti.models.elster import Meldeart, Modus
from accounti.steuer.voranmeldung import sondervorauszahlung
from accounti.steuer.zeitraum import Zeitraum
from tests.elster_hilfe import EricDoppel, als_eric
from tests.test_cli_ustva import KONFIG, text
from tests.test_elster_ustva import KONTEXT

D = Decimal
runner = CliRunner()
MONATLICH = ElsterEinstellungen(dauerfristverlaengerung=True)


def test_ein_elftel_wie_im_beispiel_der_anleitung():
    # USt 5 E 2026: 39.000 € Vorauszahlungen + 5.000 € Sondervorauszahlung → 4.000 €
    assert sondervorauszahlung(D("39000"), D("5000")) == D("4000.00")
    assert sondervorauszahlung(D("1000"), D("0")) == D("90.91")
    assert sondervorauszahlung(D("-500"), D("0")) == D("0.00")  # Überschuss → 0


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'd.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def vorjahr(s, monate=range(1, 13), betrag="3250.00", svz=None):
    """Abgegebene Voranmeldungen 2025 im Protokoll (12 × 3.250 € = 39.000 €)."""
    for m in monate:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.USTVA, zeitraum=f"2025-{m:02d}", modus=Modus.ECHT,
                weg="eric", datensatz=f"<x m='{m}'/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=D(betrag),
            ),
        )  # fmt: skip
    if svz is not None:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.DAUERFRIST, zeitraum="2025", modus=Modus.ECHT,
                weg="eric", datensatz="<x/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=D(svz),
            ),
        )  # fmt: skip
    s.commit()


def test_summe_aus_dem_protokoll(make_session):
    with make_session() as s:
        vorjahr(s, svz="5000.00")
        svz = berechne_svz(s, 2026, MONATLICH)
    assert (svz.summe_vorjahr, svz.svz_vorjahr, svz.betrag) == (
        D("39000.00"),
        D("5000.00"),
        D("4000.00"),
    )


def test_fehlende_monate_brauchen_eine_angabe(make_session):
    with make_session() as s:
        vorjahr(s, monate=range(1, 12))
        with pytest.raises(DauerfristError, match="2025-12"):
            berechne_svz(s, 2026, MONATLICH)
        svz = berechne_svz(s, 2026, MONATLICH, summe_vorjahr=D("44000"))
    assert svz.betrag == D("4000.00")


def test_quartalszahler_ohne_sondervorauszahlung(make_session):
    quartal = ElsterEinstellungen(voranmeldungszeitraum="quartal")
    with make_session() as s:
        assert berechne_svz(s, 2026, quartal).betrag is None


def _dfv_lauf(s, svz, archiv, modus=Modus.ECHT, uebermittler=None):
    u = uebermittle_dauerfrist(
        s, svz, modus=modus, kontext=KONTEXT,
        uebermittler=uebermittler or EricDoppel(), archiv=archiv,
        jetzt=datetime(2026, 2, 2, 9, 0),
    )  # fmt: skip
    s.commit()
    return u


def test_freigeben_uebermitteln_und_posten(make_session, tmp_path):
    archiv = BelegArchiv(tmp_path / "archiv")
    einst = MONATLICH.model_copy(update={"bundesland": "BY"})
    with make_session() as s:
        vorjahr(s, svz="5000.00")
        svz = berechne_svz(s, 2026, einst)
        with pytest.raises(UebermittlungError, match="nicht freigegeben"):
            _dfv_lauf(s, svz, archiv)
        gib_dauerfrist_frei(s, svz, "Erika Muster")
        s.commit()
        with pytest.raises(UebermittlungError, match="Attrappe"):
            _dfv_lauf(s, svz, archiv, uebermittler=AttrappenUebermittler())
        with pytest.raises(UebermittlungError, match="Testmodus"):
            _dfv_lauf(s, svz, archiv)
        assert _dfv_lauf(s, svz, archiv, Modus.PRUEFUNG).erfolgreich
        u = _dfv_lauf(s, svz, archiv)
    werte = lies_kennzahlen(u.datensatz)
    assert werte["Kz38"] == "4000.00" and werte["Jahr"] == "2026"
    assert "<Dauerfristverlaengerung>" in u.datensatz
    assert u.art is Meldeart.DAUERFRIST and u.betrag == D("4000.00")


def test_berichtigte_dauerfrist_braucht_eine_eigene_freigabe(make_session, tmp_path):
    """Eine vor der ersten Abgabe doppelt erteilte Freigabe deckt keine berichtigte
    Anmeldung (Kz 10) — der Freigabe-Hash enthält das Berichtigt-Kennzeichen."""
    archiv = BelegArchiv(tmp_path / "archiv")
    with make_session() as s:
        vorjahr(s, svz="5000.00")
        svz = berechne_svz(s, 2026, MONATLICH)
        gib_dauerfrist_frei(s, svz, "Erika Muster")
        gib_dauerfrist_frei(s, svz, "Erika Muster")
        s.commit()
        _dfv_lauf(s, svz, archiv, Modus.PRUEFUNG)
        erste = _dfv_lauf(s, svz, archiv)
        assert erste.erfolgreich and not erste.berichtigt
        with pytest.raises(UebermittlungError, match="freigeben"):
            _dfv_lauf(s, svz, archiv)
        gib_dauerfrist_frei(s, svz, "Erika Muster")
        s.commit()
        zweite = _dfv_lauf(s, svz, archiv)
    assert zweite.erfolgreich and zweite.berichtigt
    assert lies_kennzahlen(zweite.datensatz)["Kz10"] == "1"


def test_kz_39_im_dezember(make_session):
    with make_session() as s:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.DAUERFRIST, zeitraum="2026", modus=Modus.ECHT,
                weg="eric", datensatz="<x/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=D("4000.00"),
            ),
        )  # fmt: skip
        s.commit()
        dezember = bereite_vor(
            s, Zeitraum.lies("2026-12"), buchhaltung=Buchhaltung(),
            einstellungen=MONATLICH,
        )  # fmt: skip
        november = bereite_vor(
            s, Zeitraum.lies("2026-11"), buchhaltung=Buchhaltung(),
            einstellungen=MONATLICH,
        )  # fmt: skip
        ohne_dfv = bereite_vor(
            s, Zeitraum.lies("2026-12"), buchhaltung=Buchhaltung(),
            einstellungen=ElsterEinstellungen(),
        )  # fmt: skip
    assert dezember.voranmeldung.formularwerte()[39] == D("4000.00")
    assert dezember.voranmeldung.kz83 == D("-4000.00")
    assert 39 not in november.voranmeldung.formularwerte()
    assert 39 not in ohne_dfv.voranmeldung.formularwerte()


def test_cli_dauerfrist(tmp_path, monkeypatch):
    als_eric(monkeypatch)
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        KONFIG
        + "  dauerfristverlaengerung: true\n  uebermittler: attrappe\n"
        + "  hersteller_id: '12345'\n",
        encoding="utf-8",
    )
    url = f"sqlite:///{tmp_path / 'c.db'}"
    basis = [
        "ustva",
        "dauerfrist",
        "--jahr",
        "2026",
        "--db",
        url,
        "--config",
        str(konfig),
    ]
    archiv = ["--archiv", str(tmp_path / "archiv")]
    zeige = runner.invoke(
        app, [*basis, "--summe-vorjahr", "39000", "--svz-vorjahr", "5000"]
    )
    assert zeige.exit_code == 0, zeige.output
    assert "4.000,00" in text(zeige) and "10.02.2026" in text(zeige)
    ohne = runner.invoke(app, basis)
    assert ohne.exit_code == 2 and "--summe-vorjahr" in text(ohne)
    werte = ["--summe-vorjahr", "39000", "--svz-vorjahr", "5000"]
    frei = runner.invoke(app, [*basis, *werte, "--freigeben", "--von", "Erika Muster"])
    assert frei.exit_code == 0, frei.output
    erster = runner.invoke(app, [*basis, *werte, "--uebermitteln", *archiv])
    assert erster.exit_code == 0, erster.output
    assert "Erster Lauf" in text(erster)  # Testmodus beim ersten Lauf
    ab = runner.invoke(app, [*basis, *werte, "--uebermitteln", *archiv])
    assert ab.exit_code == 0, ab.output
    assert "Sondervorauszahlung 4.000,00 € als offener Posten" in text(ab)
    engine, make_session = session_factory(url)
    with make_session() as s:
        (posten,) = lade_posten(s)
        (u,) = lade_uebermittlungen(s, modus=Modus.ECHT)
    engine.dispose()
    assert posten.faellig_am == date(2026, 2, 10) and posten.betrag == D("4000.00")
    assert u.art is Meldeart.DAUERFRIST


def _dfv(s, jahr, betrag):
    protokolliere(
        s,
        neuer_eintrag(
            None, art=Meldeart.DAUERFRIST, zeitraum=str(jahr), modus=Modus.ECHT,
            weg="eric", datensatz=f"<x j='{jahr}'/>", erfolgreich=True,
            ergebnis="übermittelt", pruefbericht="{}", betrag=D(betrag),
        ),
    )  # fmt: skip
    s.commit()


def _dezember(s, jahr, einstellungen):
    return bereite_vor(
        s, Zeitraum.lies(f"{jahr}-12"), buchhaltung=Buchhaltung(),
        einstellungen=einstellungen,
    )  # fmt: skip


def test_sondervorauszahlung_je_jahr_aus_einer_quelle(make_session):
    """Die SVZ 2025 steht in der Konfiguration, die SVZ 2026 meldet accounti an:
    Berechnung 2026, Kz 39 im Dezember 2026 und Berechnung 2027 passen zusammen."""
    einst = MONATLICH.model_copy(update={"sondervorauszahlung": {2025: D("5000")}})
    with make_session() as s:
        vorjahr(s)  # 12 × 3.250 € = 39.000 €
        svz = berechne_svz(s, 2026, einst)
        assert (svz.svz_vorjahr, svz.betrag) == (D("5000"), D("4000.00"))
        _dfv(s, 2026, svz.betrag)
        dezember = _dezember(s, 2026, einst)
        assert dezember.voranmeldung.wert(39) == D("4000.00")
        assert "sondervorauszahlung" not in [b.regel for b in dezember.befunde]
        assert _dezember(s, 2025, einst).voranmeldung.wert(39) == D("5000")
        vorjahr(s, betrag="3000.00")  # nur 2025 — 2026 fehlt im Protokoll
        svz_2027 = berechne_svz(s, 2027, einst, summe_vorjahr=D("40000"))
    assert svz_2027.svz_vorjahr == D("4000.00")  # angemeldet, nicht die von 2025
    assert svz_2027.betrag == D("4000.00")  # (40.000 + 4.000) / 11


def test_abweichende_festsetzung_geht_vor_mit_warnung(make_session):
    einst = MONATLICH.model_copy(update={"sondervorauszahlung": {2026: D("4500")}})
    with make_session() as s:
        _dfv(s, 2026, "4000.00")
        dezember = _dezember(s, 2026, einst)
    assert dezember.voranmeldung.wert(39) == D("4500")
    (befund,) = [b for b in dezember.befunde if b.regel == "sondervorauszahlung"]
    assert befund.schweregrad.value == "warnung" and "4.000,00" in befund.text
