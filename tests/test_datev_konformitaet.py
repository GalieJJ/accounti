from datetime import date
from decimal import Decimal

from accounti.export.datev import DATEVConfig, DATEVExporter
from accounti.models import Buchungssatz


def _buchung() -> Buchungssatz:
    return Buchungssatz(
        transaktion_id="00000000-0000-0000-0000-000000000000",
        datum=date(2026, 4, 15),
        soll_konto="4930",
        haben_konto="1200",
        betrag_netto=Decimal("100.00"),
        steuer_schluessel=9,
        steuer_betrag=Decimal("19.00"),
        buchungstext="Büromaterial",
    )


def _datenzeile(tmp_path) -> str:
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    datei = DATEVExporter(cfg).exportiere([_buchung()], tmp_path)
    return datei.read_text(encoding="cp1252").splitlines()[2]


def test_betrag_nicht_gequotet(tmp_path):
    zeile = _datenzeile(tmp_path)
    assert zeile.startswith("119,00;")  # nicht "\"119,00\""


def test_konten_nicht_gequotet(tmp_path):
    felder = _datenzeile(tmp_path).split(";")
    assert felder[6] == "4930"  # Konto, ohne Quotes
    assert felder[7] == "1200"  # Gegenkonto, ohne Quotes


def test_text_gequotet(tmp_path):
    assert '"Büromaterial"' in _datenzeile(tmp_path)


def test_wkz_umsatz_leer(tmp_path):
    felder = _datenzeile(tmp_path).split(";")
    # WKZ Umsatz leer — als Textfeld wie in DATEVs Musterdatei in Anführungszeichen
    assert felder[2] == '""'


# --- Gesamttest Abschluss B1/B2, Steuer B7: Format aus datev_format ------------------


def _zeilen(datei):
    import csv

    return list(
        csv.reader(
            datei.read_bytes().decode("cp1252").split("\r\n")[:-1], delimiter=";"
        )
    )


def test_kopf_wie_datev_belege_31_felder_herkunft_re_buchungstyp_1(tmp_path):
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    datei = DATEVExporter(cfg).exportiere([_buchung()], tmp_path)
    kopf = datei.read_bytes().decode("cp1252").split("\r\n")[0].split(";")
    assert len(kopf) == 31
    assert kopf[7] == '"RE"' and kopf[18] == "1" and kopf[30] == '"accounti"'
    # Zeitraum und Wirtschaftsjahr aus der Buchung, nicht fest 2026
    assert kopf[12:16] == ["20260101", "4", "20260415", "20260415"]


def test_sonderzeichen_maskiert_belegfeld_1_im_zeichenvorrat(tmp_path):
    """Abschluss B2: " und ; im Text verschieben keine Felder mehr."""
    b = _buchung().model_copy(
        update={"buchungstext": 'Porto "Express"; Eilbrief', "beleg_nummer": "K 1;2"}
    )
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    exporter = DATEVExporter(cfg)
    zeilen = _zeilen(exporter.exportiere([b], tmp_path))
    kopf, satz = zeilen[1], zeilen[2]
    assert len(satz) == len(kopf) == 125
    assert satz[kopf.index("Buchungstext")] == 'Porto "Express"; Eilbrief'
    assert satz[kopf.index("Belegfeld 1")] == "K12"
    assert any("Belegfeld 1" in w for w in exporter.warnungen)


def test_kostenstelle_in_kost1_feld_37(tmp_path):
    b = _buchung().model_copy(update={"kostenstelle": "100"})
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    zeilen = _zeilen(DATEVExporter(cfg).exportiere([b], tmp_path))
    assert zeilen[1][36] == "KOST1 - Kostenstelle" and zeilen[2][36] == "100"
    assert zeilen[2][22] == ""  # Beleginfo – Art 2 bleibt leer


def test_stapel_ueber_die_grenze_des_wirtschaftsjahrs_abgelehnt(tmp_path):
    """Abschluss B1: 2026 und 2027 in einem Stapel — DATEV läse 0202 als 2026."""
    import pytest

    from accounti.export.datev_format import DatevFormatError

    b26 = _buchung()
    b27 = _buchung().model_copy(update={"datum": date(2027, 2, 2)})
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    with pytest.raises(DatevFormatError, match="Wirtschaftsjahr"):
        DATEVExporter(cfg).exportiere([b26, b27], tmp_path)
    assert not list(tmp_path.glob("EXTF_*"))
    datei = DATEVExporter(cfg).exportiere([b27], tmp_path)
    kopf = datei.read_bytes().decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[12] == "20270101" and kopf[14:16] == ["20270202", "20270202"]


def test_abweichendes_wirtschaftsjahr(tmp_path):
    """WJ ab 01.07.: Juli 2025 bis Juni 2026 ist ein Stapel, Juli 2026 nicht mehr."""
    import pytest

    from accounti.export.datev_format import DatevFormatError

    cfg = DATEVConfig(
        berater_nummer="23426",
        mandanten_nummer="40005",
        wirtschaftsjahr_beginn=date(2020, 7, 1),
    )
    juli = _buchung().model_copy(update={"datum": date(2025, 7, 3)})
    juni = _buchung().model_copy(update={"datum": date(2026, 6, 30)})
    datei = DATEVExporter(cfg).exportiere([juli, juni], tmp_path)
    kopf = datei.read_bytes().decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[12] == "20250701"
    naechstes = _buchung().model_copy(update={"datum": date(2026, 7, 1)})
    with pytest.raises(DatevFormatError, match="30.06.2026"):
        DATEVExporter(cfg).exportiere([juli, naechstes], tmp_path / "x")


def test_buchung_ausserhalb_des_zeitraums_abgelehnt(tmp_path):
    import pytest

    from accounti.export.datev_format import DatevFormatError

    cfg = DATEVConfig(
        berater_nummer="23426",
        mandanten_nummer="40005",
        datum_von=date(2026, 5, 1),
        datum_bis=date(2026, 5, 31),
    )
    with pytest.raises(DatevFormatError, match="außerhalb"):
        DATEVExporter(cfg).exportiere([_buchung()], tmp_path)


def test_konto_passt_nicht_zur_sachkontenlaenge(tmp_path):
    """Steuer B7: 177721 bei Sachkontenlänge 4 ist weder Sach- noch Personenkonto."""
    b = _buchung().model_copy(
        update={
            "soll_konto": "1363",
            "haben_konto": "177721",
            "steuer_schluessel": None,
        }
    )
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    exporter = DATEVExporter(cfg)
    exporter.exportiere([b], tmp_path)
    (warnung,) = [w for w in exporter.warnungen if "177721" in w]
    assert "Sachkontenlänge 4" in warnung
