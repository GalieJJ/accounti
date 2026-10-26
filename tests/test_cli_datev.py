"""CLI ``accounti datev``: stammdaten, belege, kontoauszuege."""

import zipfile
from datetime import date
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_export import lade_kontoauszuege
from accounti.db.repository import (
    speichere_bankkonto,
    speichere_kontakt,
    speichere_transaktion,
)
from accounti.models import (
    Bankkonto,
    Belegart,
    Kontakt,
    Transaktion,
    TransaktionQuelle,
)
from tests.test_datev_belege import PDF, _beleg, _buchung

runner = CliRunner()


def _text(r):
    return " ".join(r.output.split())


@pytest.fixture
def umgebung(tmp_path):
    url = f"sqlite:///{tmp_path / 'd.db'}"
    engine, make = session_factory(url)
    init_db(engine)
    archiv = tmp_path / "archiv"
    with make() as s:
        speichere_kontakt(s, Kontakt(name="Kunde A GmbH", debitor_konto="10001"))
        speichere_kontakt(s, Kontakt(name="Lieferant B KG", kreditor_konto="70001"))
        speichere_kontakt(s, Kontakt(name="Lieferant C AG", kreditor_konto="70002"))
        beleg = _beleg(
            s, BelegArchiv(archiv), "r.pdf", PDF, Belegart.EINGANGSRECHNUNG, "R-1"
        )
        _buchung(s, "R-1", beleg_id=beleg.id)  # 4930 an 70001 im August
        s.commit()
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "datev:\n  berater_nummer: '29098'\n  mandanten_nummer: '00042'\n"
        "  wirtschaftsjahr_beginn: '2026-01-01'\n",
        encoding="utf-8",
    )
    return tmp_path, ["--db", url, "--config", str(konfig)], archiv


def test_stammdaten(umgebung):
    tmp_path, basis, _ = umgebung
    r = runner.invoke(
        app, ["datev", "stammdaten", "--ausgabe", str(tmp_path / "aus"), *basis]
    )
    assert r.exit_code == 0, r.output
    assert "3 Personenkonten" in _text(r)
    (datei,) = (tmp_path / "aus").glob("EXTF_DebKred_Stamm_*.csv")
    kopf = datei.read_bytes().decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[10:12] == ["29098", "42"]  # aus der Konfiguration


def test_stammdaten_nur_konten_mit_buchungen_im_zeitraum(umgebung):
    tmp_path, basis, _ = umgebung
    r = runner.invoke(
        app,
        [
            "datev",
            "stammdaten",
            "--period",
            "2026-08",
            "--ausgabe",
            str(tmp_path / "aus"),
            *basis,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "1 Personenkonten" in _text(r)


def test_stammdaten_ohne_beraternummer(tmp_path):
    r = runner.invoke(
        app,
        [
            "datev",
            "stammdaten",
            "--db",
            f"sqlite:///{tmp_path / 'x.db'}",
            "--config",
            str(tmp_path / "fehlt.yaml"),
        ],
    )
    assert r.exit_code == 1
    assert "Beraternummer" in _text(r)


def test_belege(umgebung):
    tmp_path, basis, archiv = umgebung
    ziel = tmp_path / "aus" / "belege-08.zip"
    r = runner.invoke(
        app,
        [
            "datev",
            "belege",
            "--period",
            "2026-08",
            "--ausgabe",
            str(ziel),
            "--archiv",
            str(archiv),
            "--berater",
            "1234",
            "--mandant",
            "7",
            *basis,
        ],
    )
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "1 Belege" in text and "1 von 1 Buchungen verknüpft" in text
    with zipfile.ZipFile(ziel) as z:
        assert "document.xml" in z.namelist()
        assert b"<consultantNumber>1234</consultantNumber>" in z.read("document.xml")
    assert (
        tmp_path / "aus" / "EXTF_Buchungsstapel_20260801_20260831_Beleglink.csv"
    ).exists()


def test_belege_falscher_zeitraum(umgebung):
    tmp_path, basis, archiv = umgebung
    r = runner.invoke(
        app,
        [
            "datev",
            "belege",
            "--period",
            "08/2026",
            "--ausgabe",
            str(tmp_path / "z.zip"),
            *basis,
        ],
    )
    assert r.exit_code == 1
    assert "JJJJ-MM" in _text(r)


# ---------------------------------------------------------------------------
# kontoauszuege
# ---------------------------------------------------------------------------


@pytest.fixture
def bank(tmp_path):
    url = f"sqlite:///{tmp_path / 'k.db'}"
    engine, make = session_factory(url)
    init_db(engine)
    with make() as s:
        speichere_bankkonto(
            s, Bankkonto(iban="DE89370400440532013000", bezeichnung="Giro")
        )
        for tag, betrag, konto in [
            (date(2025, 7, 3), "1190.00", "1200"),
            (date(2025, 7, 15), "-59.50", "1200"),
            (date(2025, 8, 5), "250.00", "1200"),
            (date(2025, 7, 9), "49.90", "1210"),
        ]:
            speichere_transaktion(
                s,
                Transaktion(
                    datum=tag,
                    betrag=Decimal(betrag),
                    verwendungszweck="Umsatz",
                    quelle=TransaktionQuelle.BANK,
                    rohtext="",
                    sachkonto=konto,
                ),
            )
        s.commit()
    aus = tmp_path / "aus"
    return make, aus, ["--db", url, "--config", str(tmp_path / "fehlt.yaml")]


def _auszug(basis, aus, *args):
    return runner.invoke(
        app, ["datev", "kontoauszuege", "--ausgabe", str(aus), *args, *basis]
    )


def test_kontoauszuege(bank):
    make, aus, basis = bank
    r = _auszug(basis, aus, "--period", "2025-07", "--anfangssaldo", "1.000,00")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "Auszug 1/2025" in text and "2.130,50" in text
    mt = (aus / "MT940_1200_202507.sta").read_bytes().decode("ascii")
    assert ":25:37040044/532013000" in mt and ":28C:1/1" in mt
    r = _auszug(basis, aus, "--period", "2025-09", "--kontrollsaldo", "2380,50")
    assert r.exit_code == 0, r.output
    mt = (aus / "MT940_1200_202508-202509.sta").read_bytes().decode("ascii")
    assert ":28C:2/1" in mt and ":28C:3/1" in mt
    csv = (aus / "Saldenverlauf_1200_2025.csv").read_bytes().decode("cp1252")
    assert len(csv.strip().split("\r\n")) == 4  # Kopf + Juli, August, September
    assert "keine Befunde" in _text(r)
    with make() as s:
        assert [a.nummer for a in lade_kontoauszuege(s, "1200")] == [1, 2, 3]


def test_kontoauszuege_paypal(bank):
    _, aus, basis = bank
    r = _auszug(
        basis, aus, "--konto", "1210", "--period", "2025-07", "--anfangssaldo", "0"
    )
    assert r.exit_code == 0, r.output
    mt = (aus / "MT940_1210_202507.sta").read_bytes().decode("ascii")
    assert ":25:PPLXLULL/PAYPAL" in mt and "1190,00" not in mt  # nur PayPal
    assert ":61:2507090709C49,90NMSCNONREF" in mt
    assert ":62F:C250731EUR49,90" in mt


def test_kontoauszuege_ohne_anfangssaldo(bank):
    make, aus, basis = bank
    r = _auszug(basis, aus, "--period", "2025-07")
    assert r.exit_code == 1
    assert "--anfangssaldo" in _text(r)


def test_kontoauszuege_kontrollsaldo_falsch(bank):
    make, aus, basis = bank
    r = _auszug(
        basis,
        aus,
        "--period",
        "2025-07",
        "--anfangssaldo",
        "1000",
        "--kontrollsaldo",
        "2000",
    )
    assert r.exit_code == 1
    assert "Nichts festgeschrieben" in _text(r)
    with make() as s:
        assert lade_kontoauszuege(s) == []


def test_kontoauszuege_bei_kaputter_kette_keine_dateien(bank):
    """Hat die Prüfung der Auszugskette Befunde, wird kein MT940 geschrieben."""
    from sqlalchemy import update

    from accounti.db.tabellen import TransaktionRow

    make, aus, basis = bank
    r = _auszug(basis, aus, "--period", "2025-07", "--anfangssaldo", "1000")
    assert r.exit_code == 0, r.output
    mt = aus / "MT940_1200_202507.sta"
    mt.unlink()
    with make() as s:
        s.execute(
            update(TransaktionRow)
            .where(TransaktionRow.betrag == Decimal("-59.50"))
            .values(betrag=Decimal("-60.00"))
        )
        s.commit()
    r = _auszug(basis, aus, "--period", "2025-07")
    assert r.exit_code == 1
    text = _text(r)
    assert "Prüfung der Auszugskette" in text and "keine Dateien" in text
    assert not mt.exists()


def test_kontoauszuege_ohne_bankkonto(bank):
    _, aus, basis = bank
    r = _auszug(
        basis, aus, "--konto", "1230", "--period", "2025-07", "--anfangssaldo", "0"
    )
    assert r.exit_code == 1
    assert "--kontobezeichnung" in _text(r)
    r = _auszug(
        basis,
        aus,
        "--konto",
        "1230",
        "--period",
        "2025-07",
        "--anfangssaldo",
        "0",
        "--kontobezeichnung",
        "DE02120300000000202051",
    )
    assert r.exit_code == 0, r.output


def _bu_spalte(datei):
    """(Konto, Gegenkonto) → BU-Schlüssel aus einem Buchungsstapel."""
    import csv

    zeilen = list(
        csv.reader(datei.read_text(encoding="cp1252").splitlines(), delimiter=";")
    )
    kopf = zeilen[1]
    konto, gegen = kopf.index("Konto"), kopf.index("Gegenkonto (ohne BU-Schlüssel)")
    bu = kopf.index("BU-Schlüssel")
    return {(z[konto], z[gegen]): z[bu] for z in zeilen[2:]}


def test_export_und_belege_mit_automatikkonten(umgebung, monkeypatch):
    """Befund M-4/N-8 (Runde 3): beide Exporte, aus einem fremden Arbeitsverzeichnis —
    passender Schlüssel auf Automatikkonto leer (DATEV 0907049 Kap. 3), ohne Steuer
    BU 40 (Aufhebung der Automatik)."""
    from datetime import date as tag

    from accounti.db.repository import speichere_buchung
    from accounti.models import Buchungssatz, BuchungStatus

    tmp_path, basis, archiv = umgebung
    _, make = session_factory(basis[1])
    with make() as s:
        for soll, haben, schluessel, steuer in (
            ("10001", "8400", 3, Decimal("19.00")),
            ("3400", "70001", None, None),
        ):
            speichere_buchung(
                s,
                Buchungssatz(
                    datum=tag(2026, 8, 20),
                    soll_konto=soll,
                    haben_konto=haben,
                    betrag_netto=Decimal("100.00"),
                    steuer_schluessel=schluessel,
                    steuer_betrag=steuer,
                    buchungstext="Automatik",
                    status=BuchungStatus.GEPRUEFT,
                ),
            )
        s.commit()
    fremd = tmp_path / "anderswo"
    fremd.mkdir()
    monkeypatch.chdir(fremd)
    ausgabe = tmp_path / "ex"
    r = runner.invoke(
        app,
        ["export", "datev", "--berater", "1001", "--mandant", "2"]
        + ["--output", str(ausgabe), *basis],
    )
    assert r.exit_code == 0, r.output
    (datei,) = ausgabe.glob("EXTF_*.csv")
    bu = _bu_spalte(datei)
    assert (bu[("10001", "8400")], bu[("3400", "70001")]) == ("", "40")
    ziel = tmp_path / "aus" / "belege-08.zip"
    r = runner.invoke(
        app,
        ["datev", "belege", "--period", "2026-08", "--ausgabe", str(ziel)]
        + ["--archiv", str(archiv), *basis],
    )
    assert r.exit_code == 0, r.output
    bu = _bu_spalte(
        tmp_path / "aus" / "EXTF_Buchungsstapel_20260801_20260831_Beleglink.csv"
    )
    assert (bu[("10001", "8400")], bu[("3400", "70001")]) == ("", "40")


def test_export_mit_kaputter_kontenrahmen_datei(umgebung):
    """Befund N-8: klare Meldung statt Traceback, nichts als exportiert vermerkt."""
    from accounti.db.repository import lade_buchungen
    from accounti.models import BuchungStatus

    tmp_path, basis, _ = umgebung
    kaputt = tmp_path / "skr.yaml"
    kaputt.write_text("konten: [unvollständig\n", encoding="utf-8")
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        konfig.read_text(encoding="utf-8")
        + f"pruefung:\n  kontenrahmen_datei: {kaputt}\n",
        encoding="utf-8",
    )
    r = runner.invoke(
        app,
        ["export", "datev", "--berater", "1", "--mandant", "2"]
        + ["--output", str(tmp_path / "ex"), *basis],
    )
    assert r.exit_code == 1 and "Kontenrahmen-Datei" in r.output
    assert "Traceback" not in r.output
    _, make = session_factory(basis[1])
    with make() as s:
        assert all(b.status is not BuchungStatus.EXPORTIERT for b in lade_buchungen(s))


# --- Gesamttest Abschluss B1, Betrieb B6, Eingang B11: export datev --period ---------


def _export(basis, ausgabe, *extra):
    return runner.invoke(
        app, ["export", "datev", "--output", str(ausgabe), *extra, *basis]
    )


def _kopf(datei):
    return datei.read_bytes().decode("cp1252").split("\r\n")[0].split(";")


def test_export_datev_period_wie_im_readme(umgebung):
    """README: ``export datev --period 2026-04 --berater … --mandant …``."""
    tmp_path, basis, _ = umgebung
    _, make = session_factory(basis[1])
    with make() as s:
        _buchung(s, "R-4", tag=15, monat=4)
        _buchung(s, "R-9", tag=1, monat=9)
        s.commit()
    r = _export(basis, tmp_path / "ex", "--period", "2026-04", "--berater", "23426")
    assert r.exit_code == 0, r.output
    (datei,) = (tmp_path / "ex").glob("EXTF_*.csv")
    assert datei.name == "EXTF_Buchungsstapel_20260401_20260430.csv"
    kopf = _kopf(datei)
    assert kopf[10:16] == ["23426", "42", "20260101", "4", "20260401", "20260430"]
    inhalt = datei.read_bytes().decode("cp1252")
    assert "R-4" in inhalt and "R-9" not in inhalt and "R-1" not in inhalt
    assert "1 Buchungen" in _text(r)


def test_export_datev_nur_einmal_ausser_mit_erneut(umgebung):
    """Betrieb B6: ein zweiter Export liefert dieselben Buchungen nicht noch einmal."""
    tmp_path, basis, _ = umgebung
    assert _export(basis, tmp_path / "a").exit_code == 0
    r = _export(basis, tmp_path / "b")
    assert r.exit_code == 0, r.output
    assert "Keine Buchungen zu exportieren" in _text(r) and "--erneut" in _text(r)
    assert not (tmp_path / "b").exists()
    r = _export(basis, tmp_path / "c", "--erneut")
    assert r.exit_code == 0, r.output
    assert "1 Buchungen" in _text(r)


def test_export_datev_ueber_den_jahreswechsel_abgelehnt(umgebung):
    """Abschluss B1: ohne Zeitraum 2026 und 2027 in einem Stapel — Abbruch, nichts
    als exportiert vermerkt; je Monat geht es."""
    from accounti.db.repository import lade_buchungen
    from accounti.models import BuchungStatus

    tmp_path, basis, _ = umgebung
    _, make = session_factory(basis[1])
    with make() as s:
        _buchung(s, "R-27", tag=2, monat=2, datum=date(2027, 2, 2))
        s.commit()
    r = _export(basis, tmp_path / "ex")
    assert r.exit_code == 1 and "Wirtschaftsjahr" in _text(r), r.output
    assert "--period" in _text(r)
    with make() as s:
        assert all(b.status is not BuchungStatus.EXPORTIERT for b in lade_buchungen(s))
    r = _export(basis, tmp_path / "ex", "--period", "2027-02")
    assert r.exit_code == 0, r.output
    (datei,) = (tmp_path / "ex").glob("EXTF_*20270201_20270228.csv")
    assert _kopf(datei)[12] == "20270101"


def test_export_datev_abweichendes_wirtschaftsjahr_aus_der_konfiguration(umgebung):
    """Betrieb B6: datev.wirtschaftsjahr_beginn bestimmt Feld 13 des Kopfs."""
    tmp_path, basis, _ = umgebung
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        konfig.read_text(encoding="utf-8").replace("2026-01-01", "2025-07-01"),
        encoding="utf-8",
    )
    r = _export(basis, tmp_path / "ex", "--period", "2026-08")
    assert r.exit_code == 0, r.output
    (datei,) = (tmp_path / "ex").glob("EXTF_*.csv")
    assert _kopf(datei)[12] == "20260701"


def test_export_datev_im_festgeschriebenen_monat_nur_einmal(umgebung):
    """Im festgeschriebenen Monat nimmt die Buchung den Status ``exportiert`` nicht
    mehr an — der Journalvermerk des ersten Exports zählt trotzdem."""
    tmp_path, basis, _ = umgebung
    r = runner.invoke(app, ["periode", "schliessen", "2026-08", "--von", "t", *basis])
    assert r.exit_code == 0, r.output
    r = _export(basis, tmp_path / "a")
    assert r.exit_code == 0 and "1 Buchungen" in _text(r), r.output
    r = _export(basis, tmp_path / "b")
    assert "Keine Buchungen zu exportieren" in _text(r), r.output


# --- Gesamttest Abschluss B3: Automatikkonten in pruefung/skr03.yaml ------------------


def test_automatikkonten_aus_anlagen_und_skonto_vollstaendig():
    """Konten, die accounti selbst mit Steuerschlüssel bebucht, sind in DATEV
    Automatikkonten (SKR03 2026: AM 8801/8820, S/AM 8731/8736, S/AV 3731/3736) —
    dort bleibt das BU-Feld leer."""
    from accounti.anlagen.konfiguration import STANDARDS
    from accounti.konfiguration import Buchhaltung
    from accounti.pruefung.regeln.richtigkeit import automatikkonten

    automatik = automatikkonten(Buchhaltung())
    konten = STANDARDS["SKR03"]["konten"]
    for name in ("erloes_buchverlust", "erloes_buchgewinn"):
        assert automatik.get(konten[name]) == 3, name
    b = Buchhaltung()
    erwartet = {"19": 9, "7": 8}
    for satz, konto in b.skonto_erhalten.items():
        if satz != "0":
            assert automatik.get(konto) == erwartet[satz], konto
    erwartet = {"19": 3, "7": 2}
    for satz, konto in b.skonto_gewaehrt.items():
        if satz != "0":
            assert automatik.get(konto) == erwartet[satz], konto


def test_export_ohne_bu_auf_anlagenverkauf_und_skonto(umgebung):
    from accounti.db.repository import speichere_buchung
    from accounti.models import Buchungssatz, BuchungStatus

    tmp_path, basis, archiv = umgebung
    _, make = session_factory(basis[1])
    with make() as s:
        for soll, haben, schluessel, steuer in (
            ("1360", "8820", 3, "285.00"),
            ("70001", "3736", 9, "0.38"),
            ("70001", "3731", 8, "0.07"),
        ):
            speichere_buchung(
                s,
                Buchungssatz(
                    datum=date(2026, 8, 20),
                    soll_konto=soll,
                    haben_konto=haben,
                    betrag_netto=Decimal("10.00"),
                    steuer_schluessel=schluessel,
                    steuer_betrag=Decimal(steuer),
                    buchungstext="Automatik",
                    status=BuchungStatus.GEPRUEFT,
                ),
            )
        s.commit()
    r = _export(basis, tmp_path / "ex")
    assert r.exit_code == 0, r.output
    (datei,) = (tmp_path / "ex").glob("EXTF_*.csv")
    bu = _bu_spalte(datei)
    assert [
        bu[k] for k in (("1360", "8820"), ("70001", "3736"), ("70001", "3731"))
    ] == [
        "",
        "",
        "",
    ]
    ziel = tmp_path / "aus" / "b.zip"
    r = runner.invoke(
        app,
        ["datev", "belege", "--period", "2026-08", "--ausgabe", str(ziel)]
        + ["--archiv", str(archiv), *basis],
    )
    assert r.exit_code == 0, r.output
    bu = _bu_spalte(
        tmp_path / "aus" / "EXTF_Buchungsstapel_20260801_20260831_Beleglink.csv"
    )
    assert bu[("1360", "8820")] == "" and bu[("70001", "3736")] == ""


# --- Nachprüfung Paket E: N1 (Stapel nie überschreiben), N3 (--alle nicht doppelt) ---


def test_export_datev_zweiter_stapel_ueberschreibt_den_ersten_nicht(umgebung):
    """N1: Der zweite Export desselben Monats bringt nur die neue Buchung — früher
    unter demselben Dateinamen, der erste Stapel war weg und der SHA-256 im Journal
    verwies ins Leere. Jetzt eine eigene Datei; jeder Journaleintrag passt zu seiner."""
    import hashlib
    import json

    from accounti.pruefung.journal import lade_journal

    tmp_path, basis, _ = umgebung
    ex = tmp_path / "ex"
    assert _export(basis, ex, "--period", "2026-08").exit_code == 0
    (erste,) = ex.glob("EXTF_*.csv")
    vorher = erste.read_bytes()
    _, make = session_factory(basis[1])
    with make() as s:
        _buchung(s, "R-2", tag=20)
        s.commit()
    r = _export(basis, ex, "--period", "2026-08")
    assert r.exit_code == 0 and "1 Buchungen" in _text(r), r.output
    assert erste.read_bytes() == vorher
    (zweite,) = [d for d in ex.glob("EXTF_*.csv") if d != erste]
    assert zweite.name == "EXTF_Buchungsstapel_20260801_20260831_2.csv"
    assert "R-2" in zweite.read_bytes().decode("cp1252")
    assert "R-1" not in zweite.read_bytes().decode("cp1252")
    with make() as s:
        exporte = [json.loads(e.nachher) for e in lade_journal(s, vorgang="export")]
    assert [e["datei"] for e in exporte] == [erste.name, zweite.name]
    for e in exporte:
        inhalt = (ex / e["datei"]).read_bytes()
        assert hashlib.sha256(inhalt).hexdigest() == e["sha256"]


def test_export_datev_nummer_zaehlt_die_namen_im_journal(umgebung):
    """Nachprüfung 2 E, L2: Den ersten Stapel nach dem Hochladen aus dem Ordner
    geschoben — der nächste Export hieß wieder ``…_20260831.csv``. Zwei
    Journaleinträge mit demselben Namen und verschiedenem SHA-256; im selben
    Archivordner überschriebe die neue Datei die erste. Die laufende Nummer
    überspringt jetzt auch die Namen, die das Journal schon kennt."""
    import json

    from accounti.pruefung.journal import lade_journal

    tmp_path, basis, _ = umgebung
    ex = tmp_path / "ex"
    assert _export(basis, ex, "--period", "2026-08").exit_code == 0
    (erste,) = ex.glob("EXTF_*.csv")
    erste.rename(tmp_path / erste.name)  # hochgeladen und weggeräumt
    _, make = session_factory(basis[1])
    with make() as s:
        _buchung(s, "R-2", tag=20)
        s.commit()
    r = _export(basis, ex, "--period", "2026-08")
    assert r.exit_code == 0 and "1 Buchungen" in _text(r), r.output
    (zweite,) = ex.glob("EXTF_*.csv")
    assert zweite.name == "EXTF_Buchungsstapel_20260801_20260831_2.csv"
    with make() as s:
        namen = [
            json.loads(e.nachher)["datei"] for e in lade_journal(s, vorgang="export")
        ]
    assert namen == [erste.name, zweite.name]


def test_export_datev_alle_ungepruefte_nach_der_freigabe_nicht_noch_einmal(umgebung):
    """N3: ``--alle`` nimmt ungeprüfte Buchungen in den Stapel. Sie wechseln den
    Status nicht (exportiert hieße freigegeben), standen aber auch nicht im Journal —
    nach der Freigabe kamen sie ein zweites Mal nach DATEV."""
    import json

    from accounti.models import BuchungStatus
    from accounti.pruefung.journal import lade_journal
    from accounti.pruefung.storno import freigeben

    tmp_path, basis, _ = umgebung
    _, make = session_factory(basis[1])
    with make() as s:
        offen = _buchung(s, "R-7", tag=7, status=BuchungStatus.ZUR_PRUEFUNG)
        s.commit()
    r = _export(basis, tmp_path / "a", "--alle")
    assert r.exit_code == 0 and "2 Buchungen" in _text(r), r.output
    assert "ungeprüft" in _text(r)
    with make() as s:
        (eintrag,) = lade_journal(s, vorgang="export")
        assert json.loads(eintrag.nachher)["ungeprueft"] == [str(offen.id)]
        assert freigeben(s, str(offen.id), von="Erika")[1]
        s.commit()
    r = _export(basis, tmp_path / "b")
    assert r.exit_code == 0, r.output
    assert "Keine Buchungen zu exportieren" in _text(r)
    assert not (tmp_path / "b").exists()


def test_korrigiere_warnt_wenn_der_vorschlag_schon_bei_datev_ist(umgebung):
    """Nachprüfung 2 E, L3: Ein Vorschlag aus ``export datev --alle`` gilt als
    übergeben. Wird er danach direkt korrigiert (ohne Storno), kommt er nie mehr nach
    DATEV — dort steht das alte Konto, ohne Hinweis beim Korrigieren. Jetzt warnt
    ``korrigiere`` und nennt den Weg (``--erneut``); ein nicht übergebener
    Vorschlag bleibt ohne Warnung."""
    from accounti.models import BuchungStatus
    from accounti.pruefung.storno import korrigiere

    tmp_path, basis, _ = umgebung
    _, make = session_factory(basis[1])
    with make() as s:
        offen = _buchung(s, "R-7", tag=7, status=BuchungStatus.ZUR_PRUEFUNG)
        s.commit()
    assert _export(basis, tmp_path / "a", "--alle").exit_code == 0
    r = runner.invoke(
        app,
        [
            "korrigiere",
            str(offen.id)[:8],
            "--soll",
            "4940",
            "--haben",
            "70001",
            "--steuer",
            "9",
            "--von",
            "Erika",
            *basis,
        ],
    )
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "schon an DATEV" in text and "4930 an 70001" in text, r.output
    assert "export datev --period 2026-08 --erneut" in text, r.output
    with make() as s:
        neu = _buchung(s, "R-9", tag=9, status=BuchungStatus.ZUR_PRUEFUNG)
        k = korrigiere(s, str(neu.id), "4940", "70001", steuer=9, von="Erika")
        assert not [w for w in k.warnungen if "DATEV" in w]
