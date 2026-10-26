"""Einzelbefunde Ausgang/Debitoren aus dem Gesamttest (B7–B11, B13–B16)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_ausgangsrechnung,
    speichere_ausgangsrechnung,
)
from accounti.erechnung import lies
from accounti.erechnung.ausstellung import stelle_aus
from accounti.erechnung.erzeuger.aufbau import (
    EN16931,
    XRECHNUNG_3,
    NichtUnterstuetztError,
    baue_rechnung,
)
from accounti.erechnung.kosit import KositPruefer
from accounti.erechnung.mustang import MustangPruefer
from accounti.konfiguration import Firma
from accounti.steuer.umsatzsteuer import Geschaeftsvorfall, UStBerechner
from tests.pruefung_hilfe import (
    make_session_fixture,  # noqa: F401 - Fixture
)
from tests.test_cli_rechnung import FIRMA_YAML
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos

D = Decimal
runner = CliRunner()
WERKZEUGE = KositPruefer().verfuegbar() and MustangPruefer().verfuegbar()


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def _aus(make_session, archiv, e, datum, firma=FIRMA, **kw):
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        ergebnis = stelle_aus(s, archiv, str(e.id)[:8], firma, datum, **kw)
        s.commit()
    return ergebnis


def _text(r):
    return " ".join(r.output.split())


# --- B7: Nummernformat ohne {jahr} --------------------------------------------------

OHNE_JAHR = FIRMA.model_copy(
    update={
        "rechnung": FIRMA.rechnung.model_copy(
            update={"nummernformat": "RE{nummer:05d}"}
        )
    }
)


def test_nummernformat_ohne_jahr_zaehlt_ueber_den_jahreswechsel(umgebung):
    make_session, archiv = umgebung
    nummern = [
        _aus(
            make_session,
            archiv,
            entwurf(kunde(), pos("Ware", "100")),
            tag,
            OHNE_JAHR,
            erstellt_am=datetime(2027, 1, 5, 9).astimezone(),
        ).rechnung.nummer
        for tag in (date(2026, 12, 30), date(2027, 1, 4))
    ]
    assert nummern == ["RE00001", "RE00002"]


def test_umstieg_auf_ein_format_ohne_jahr_setzt_den_kreis_fort(umgebung):
    make_session, archiv = umgebung
    for _ in range(2):
        _aus(make_session, archiv, entwurf(kunde(), pos("Ware", "1")), date(2026, 3, 1))
    r = _aus(
        make_session,
        archiv,
        entwurf(kunde(), pos("x", "1")),
        date(2026, 3, 2),
        OHNE_JAHR,
    )
    assert r.rechnung.nummer == "RE00003"


def test_vergebene_nummer_wird_uebersprungen(umgebung):
    make_session, archiv = umgebung
    vorhanden = entwurf(kunde(), pos("Altbestand", "1")).model_copy(
        update={"nummer": "RE00001"}
    )
    with make_session() as s:
        speichere_ausgangsrechnung(s, vorhanden)
        s.commit()
    r = _aus(
        make_session,
        archiv,
        entwurf(kunde(), pos("x", "1")),
        date(2026, 3, 2),
        OHNE_JAHR,
    )
    assert r.rechnung.nummer == "RE00002"


@pytest.mark.parametrize(
    ("format_", "meldung"),
    [
        ("RE-{jahr}", "nummer"),
        ("{jahr}-{lfd:04d}", "lfd"),
        ("RE-{nummer:04q}", "Format"),
    ],
)
def test_nummernformat_wird_beim_laden_geprueft(format_, meldung):
    daten = FIRMA.model_dump()
    daten["rechnung"]["nummernformat"] = format_
    with pytest.raises(ValidationError, match=meldung):
        Firma.model_validate(daten)


def test_doppelte_nummer_bricht_ohne_traceback_ab(tmp_path, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    import accounti.erechnung.ausstellung as ausstellung

    def doppelt(*_a, **_k):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(ausstellung, "stelle_aus", doppelt)
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(FIRMA_YAML, encoding="utf-8")
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(
        app,
        ["rechnung", "ausstellen", "abc", "--db", url, "--config", str(konfig),
         "--ohne-formale-pruefung"],
    )  # fmt: skip
    assert r.exit_code == 1 and "Nicht ausgestellt" in _text(r)
    assert not isinstance(r.exception, IntegrityError)


# --- B9: Leistungsort B2C-Dienstleistung ---------------------------------------------

OSS = FIRMA.model_copy(update={"oss": True})


@pytest.mark.parametrize(
    ("land", "leistung", "elektronisch", "erwartet"),
    [
        ("AT", True, False, Geschaeftsvorfall.INLAND),  # § 3a Abs. 1 / Abs. 3 Nr. 3c
        ("AT", False, False, Geschaeftsvorfall.EU_B2C_OSS),  # Fernverkauf § 3c
        ("AT", True, True, Geschaeftsvorfall.EU_B2C_OSS),  # § 3a Abs. 5
        ("CH", True, False, Geschaeftsvorfall.INLAND),  # § 3a Abs. 1
        ("CH", True, True, Geschaeftsvorfall.NICHT_STEUERBAR),  # § 3a Abs. 4 Nr. 11
        ("CH", False, False, Geschaeftsvorfall.DRITTLAND_AUSFUHR),
    ],
)
def test_leistungsort_privatkunde(land, leistung, elektronisch, erwartet):
    b = UStBerechner(oss_registriert=True, oss_schwelle_ueberschritten=True)
    assert (
        b.bestimme_vorfall(
            land,
            ist_b2b=False,
            ist_sonstige_leistung=leistung,
            ist_elektronisch=elektronisch,
        )
        is erwartet
    )


def test_rahmung_fuer_wiener_privatkundin_mit_oss_ist_deutsche_steuer():
    r = baue_rechnung(
        entwurf(
            kunde(land="AT", ust_id=None, privat=True),
            pos("Rahmung eines mitgebrachten Bildes", "100", sonstige_leistung=True),
            pos("Kunstdruck (Versand nach Wien)", "100"),
            pos("E-Book Katalog (Download)", "10", elektronisch=True),
        ),
        OSS,
        "2026-0001",
        date(2026, 3, 10),
    )
    assert [(z.steuerkategorie, z.steuersatz) for z in r.zeilen] == [
        ("S", D("19")),
        ("S", D("20")),
        ("S", D("20")),
    ]


def test_rahmung_fuer_zuercher_privatkunden_ist_deutsche_steuer():
    r = baue_rechnung(
        entwurf(
            kunde(land="CH", ust_id=None, privat=True),
            pos("Rahmung eines mitgebrachten Bildes", "100", sonstige_leistung=True),
        ),
        FIRMA,
        "2026-0001",
        date(2026, 3, 10),
    )
    assert [(s.kategorie, s.satz) for s in r.steuern] == [("S", D("19"))]
    with pytest.raises(NichtUnterstuetztError, match="§ 3a Abs. 4"):
        baue_rechnung(
            entwurf(
                kunde(land="CH", ust_id=None, privat=True),
                pos("Download", "10", elektronisch=True),
            ),
            FIRMA,
            "2026-0001",
            date(2026, 3, 10),
        )


def test_position_elektronisch_ueber_die_cli(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(
        app, ["rechnung", "neu", "--db", url, "--name", "Anna", "--privat"]
    )
    rid = r.output.split("Entwurf ")[1].split()[0]
    r = runner.invoke(
        app,
        ["rechnung", "position", rid, "--db", url, "--text", "E-Book", "--preis", "10",
         "--elektronisch"],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    engine, make_session = session_factory(url)
    with make_session() as s:
        (p,) = lade_ausgangsrechnung(s, rid).positionen
    engine.dispose()
    assert (p.elektronisch, p.sonstige_leistung) == (True, True)


# --- B10: Hinweis nach § 286 Abs. 3 BGB --------------------------------------------


def test_verbraucherrechnung_traegt_den_verzugshinweis(umgebung):
    make_session, archiv = umgebung
    privat = _aus(
        make_session,
        archiv,
        entwurf(kunde(ust_id=None, privat=True), pos("Radierung", "1000")),
        date(2026, 6, 1),
        hinweis_30_tage=True,
    )
    firma = _aus(
        make_session,
        archiv,
        entwurf(kunde(), pos("Radierung", "1000")),
        date(2026, 6, 1),
        hinweis_30_tage=True,
    )
    assert any("§ 286 Abs. 3 BGB" in n for n in lies(privat.xml).notizen)
    assert not any("§ 286" in n for n in lies(firma.xml).notizen)


def test_cli_liest_hinweis_30_tage_aus_der_konfiguration(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(FIRMA_YAML + "mahnwesen:\n  hinweis_30_tage: true\n", "utf-8")
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(
        app,
        ["rechnung", "neu", "--db", url, "--name", "Max Sammler", "--strasse",
         "Bergweg 4", "--plz", "81541", "--ort", "München", "--email",
         "max@sammler.example", "--privat"],
    )  # fmt: skip
    rid = r.output.split("Entwurf ")[1].split()[0]
    runner.invoke(
        app, ["rechnung", "position", rid, "--db", url, "--text", "x", "--preis", "10"]
    )
    r = runner.invoke(
        app,
        ["rechnung", "ausstellen", rid, "--db", url, "--config", str(konfig),
         "--archiv", str(tmp_path / "archiv"), "--ausgabe", str(tmp_path / "out"),
         "--datum", "2026-06-01", "--ohne-formale-pruefung"],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert b"286" in (tmp_path / "out" / "2026-0001.xml").read_bytes()


# --- B13: Skonto-Eingaben ------------------------------------------------------------


@pytest.mark.parametrize(
    "optionen",
    [
        ["--skonto-prozent", "2"],
        ["--skonto-tage", "10"],
        ["--skonto-prozent", "150", "--skonto-tage", "10"],
        ["--skonto-prozent", "0", "--skonto-tage", "10"],
    ],
)
def test_skonto_eingaben_werden_geprueft(tmp_path, optionen):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(
        app, ["rechnung", "neu", "--db", url, "--name", "Kunde", *optionen]
    )
    assert r.exit_code == 1 and "Skonto" in r.output


def test_skonto_ohne_tage_im_entwurf_wird_nicht_ausgestellt():
    e = entwurf(kunde(), pos("x", "100"), skonto_prozent=D("2"))
    with pytest.raises(ValueError, match="Skonto"):
        baue_rechnung(e, FIRMA, "2026-0001", date(2026, 3, 10))


# --- B14: senden --eml mit einem Entwurf ---------------------------------------------


def test_senden_eml_mit_entwurf_verlangt_erst_ausstellen(tmp_path, monkeypatch):
    from tests.test_cli_rechnung import VERSAND_YAML

    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(FIRMA_YAML + VERSAND_YAML, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTI_SMTP_PASSWORT", "geheim")
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(app, ["rechnung", "neu", "--db", url, "--name", "Kunde"])
    rid = r.output.split("Entwurf ")[1].split()[0]
    r = runner.invoke(
        app,
        ["rechnung", "senden", rid, "--eml", str(tmp_path / "x.eml"), "--db", url,
         "--config", str(konfig), "--archiv", str(tmp_path / "archiv")],
    )  # fmt: skip
    assert r.exit_code == 1
    assert "ausstellen" in r.output and "None" not in r.output


# --- B15: Steuersatz in der Vorschau -------------------------------------------------


def test_vorschau_zeigt_20_prozent_nicht_in_exponentialschreibweise(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(FIRMA_YAML.replace("bank:", "oss: true\n  bank:"), "utf-8")
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(
        app,
        ["rechnung", "neu", "--db", url, "--name", "Anna", "--plz", "1010", "--ort",
         "Wien", "--land", "AT", "--email", "a@b.example", "--privat"],
    )  # fmt: skip
    rid = r.output.split("Entwurf ")[1].split()[0]
    runner.invoke(
        app,
        ["rechnung", "position", rid, "--db", url, "--text", "Druck", "--preis", "100"],
    )
    r = runner.invoke(
        app, ["rechnung", "zeigen", rid, "--db", url, "--config", str(konfig)]
    )
    assert r.exit_code == 0, r.output
    assert "S 20 %" in r.output and "E+" not in r.output


# --- B16: Privatkunden ohne E-Mail, Kleinbetrag ohne Empfängerangaben ---------------


def test_kleinbetrag_an_laufkundschaft_ohne_anschrift():
    e = entwurf(
        kunde(ust_id=None, privat=True).model_copy(
            update={"name": "Barverkauf", "strasse": None, "plz": None, "ort": None,
                    "email": None}
        ),
        pos("Postkarte", "2.10", menge="5", ermaessigt=True),
    )  # fmt: skip
    r = baue_rechnung(e, FIRMA, "2026-0001", date(2026, 3, 10))
    assert r.spezifikation == EN16931 and r.summen.brutto == D("11.24")


def test_privatkunde_ohne_email_ueber_250_euro_braucht_die_anschrift():
    ohne_mail = kunde(ust_id=None, privat=True).model_copy(update={"email": None})
    r = baue_rechnung(
        entwurf(ohne_mail, pos("Radierung", "500")), FIRMA, "1", date(2026, 5, 2)
    )
    assert r.spezifikation == EN16931
    ohne_plz = ohne_mail.model_copy(update={"plz": None})
    with pytest.raises(ValueError, match="PLZ"):
        baue_rechnung(
            entwurf(ohne_plz, pos("Radierung", "500")), FIRMA, "1", date(2026, 5, 2)
        )


def test_privatkunde_mit_allen_angaben_bleibt_xrechnung_und_firmen_brauchen_email():
    r = baue_rechnung(
        entwurf(kunde(ust_id=None, privat=True), pos("x", "500")),
        FIRMA,
        "1",
        date(2026, 5, 2),
    )
    assert r.spezifikation == XRECHNUNG_3
    with pytest.raises(ValueError, match="E-Mail"):
        baue_rechnung(
            entwurf(kunde().model_copy(update={"email": None}), pos("x", "5")),
            FIRMA,
            "1",
            date(2026, 5, 2),
        )


@pytest.mark.skipif(not WERKZEUGE, reason="KoSIT/Mustang nicht installiert")
def test_en16931_rechnung_besteht_mustang(umgebung):
    make_session, archiv = umgebung
    ohne_mail = kunde(ust_id=None, privat=True).model_copy(update={"email": None})
    ergebnis = _aus(
        make_session,
        archiv,
        entwurf(ohne_mail, pos("Radierung", "500")),
        date(2026, 5, 2),
        kosit=KositPruefer(),
        pdf_pruefer=MustangPruefer(),
    )
    assert ergebnis.kosit is None  # KoSIT prüft nur XRechnung
    assert ergebnis.mustang is not None and ergebnis.mustang.gueltig
    assert lies(ergebnis.xml).spezifikation == EN16931
    assert b"factur-x.xml" in ergebnis.pdf
