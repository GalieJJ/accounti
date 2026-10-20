"""CLI ``accounti ustva`` — Kennziffern, Plausibilisierung (Akzeptanz 1, 2, 7)."""

import json
from datetime import date, datetime
from decimal import Decimal

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_buchung, speichere_kontakt
from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from tests.test_ustid_protokoll import bestaetige

D = Decimal

runner = CliRunner()
TAG = date(2026, 8, 14)

KONFIG = """
mandant:
  name: "Galerie Muster GmbH"
  anschrift: {strasse: "Kunstweg 1", plz: "80331", ort: "München"}
  ust_id: "DE123456789"
  steuernummer: "181/815/08155"
  email: "rechnung@galerie.example"
  kontakt: {name: "Erika Muster", telefon: "089 123", email: "buero@galerie.example"}
  bank: {iban: "DE89 3704 0044 0532 0130 00"}
elster:
  bundesland: BY
  finanzamt: {name: "Finanzamt München"}
"""

WIEN = Kontakt(
    name="Rahmen Wien", land="AT", ust_id="ATU12345678", debitor_konto="10002"
)
KONTAKTE = [
    Kontakt(name="Kunde Berlin", debitor_konto="10001"),
    WIEN,
    Kontakt(name="Kunst Zürich", land="CH", debitor_konto="10003"),
    Kontakt(name="Mme Dupont", land="FR", debitor_konto="10004"),
    Kontakt(name="Papier GmbH", kreditor_konto="70001"),
    Kontakt(
        name="Agentur Wien", land="AT", ust_id="ATU87654321", kreditor_konto="70002"
    ),
]


def buchung(soll, haben, netto, schluessel=None, steuer=None, **kw):
    return Buchungssatz(
        datum=kw.pop("datum", TAG),
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=D(netto),
        steuer_schluessel=schluessel,
        steuer_betrag=D(steuer) if steuer is not None else None,
        buchungstext=kw.pop("text", "Test"),
        status=kw.pop("status", BuchungStatus.AUTO_GEBUCHT),
        **kw,
    )


# Ein Monat mit allen Konstellationen der Spec (Teststrategie)
AUGUST = [
    buchung("10001", "8400", "12345.67", 3, "2345.68"),  # Inland 19 %
    buchung("1200", "8300", "1234.56", 2, "86.42"),  # Inland 7 %
    buchung("8400", "10001", "345.00", 3, "65.55"),  # Gutschrift 19 %
    buchung("10002", "8125", "5000.00"),  # ig. Lieferung (AT, bestätigt)
    buchung("4900", "70002", "800.00", 94, "152.00"),  # Reverse Charge, Empfänger
    buchung("10003", "8120", "2500.00"),  # Ausfuhr (CH)
    buchung("10004", "8320", "300.00"),  # OSS Frankreich
    buchung("4930", "70001", "1000.00", 9, "190.00"),  # Vorsteuer 19 %
    buchung("3400", "70001", "500.00", 8, "35.00"),  # Vorsteuer 7 %
    buchung("70001", "3736", "20.00", 9, "3.80"),  # erhaltenes Skonto
    buchung("1200", "10001", "2000.00"),  # Zahlung
]

# Handgerechnete Sollrechnung (Vordruck USt 1 A 2026):
#   Kz 81  12.345,67 − 345,00 = 12.000,67 → 12.000 €  → Steuer 12.000 × 19 % = 2.280,00
#   Kz 86   1.234,56 → 1.234 €                       → Steuer  1.234 ×  7 % =    86,38
#   Kz 41   5.000 € · Kz 43 2.500 € · Kz 45 300 € (OSS, nur netto)
#   Kz 46     800 €, Kz 47 152,00 · Kz 67 152,00 (Reverse Charge neutral)
#   Kz 66   190,00 + 35,00 − 3,80 = 221,20
#   Zeile 37 Umsatzsteuer 2.280,00 + 86,38 + 152,00 = 2.518,38
#   Zeilen 38–44 Vorsteuer 221,20 + 152,00 = 373,20
#   Kz 83   2.518,38 − 373,20 = 2.145,18
SOLL = {
    "41": "5000",
    "43": "2500",
    "45": "300",
    "46": "800",
    "47": "152.00",
    "66": "221.20",
    "67": "152.00",
    "81": "12000",
    "83": "2145.18",
    "86": "1234",
}


def umgebung(tmp_path, buchungen=AUGUST, bestaetigt=True):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(KONFIG, encoding="utf-8")
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine, make_session = session_factory(url)
    init_db(engine)
    with make_session() as s:
        for k in KONTAKTE:
            speichere_kontakt(s, k)
        for b in buchungen:
            speichere_buchung(s, b)
        if bestaetigt:
            bestaetige(s, ust_id=WIEN.ust_id, jetzt=datetime(2026, 8, 3, 9, 0))
        s.commit()
    engine.dispose()
    return url, str(konfig)


def text(ergebnis):
    """Ausgabe ohne die Zeilenumbrüche der Konsole."""
    return " ".join(ergebnis.output.split())


def test_akzeptanz_1_kennziffern_wie_sollrechnung(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(
        app, ["ustva", "--period", "2026-08", "--json", "--db", url, "--config", konfig]
    )
    assert r.exit_code == 0, r.output
    ergebnis = json.loads(r.output)
    assert ergebnis["kennziffern"] == SOLL
    assert ergebnis["umsatzsteuer"] == "2518.38"
    assert ergebnis["vorsteuer"] == "373.20"
    assert ergebnis["freigabe_gesperrt"] is False


def test_anzeige_mit_zeilen_und_befunden(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(
        app, ["ustva", "--period", "2026-08", "--db", url, "--config", konfig]
    )
    assert r.exit_code == 0, r.output
    assert "August 2026" in r.output
    assert "12.000" in r.output and "2.280,00" in r.output
    assert "2.145,18" in r.output
    assert "Freigabe möglich" in r.output


def test_ohne_period_gibt_es_eine_meldung(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(app, ["ustva", "--db", url, "--config", konfig])
    assert r.exit_code != 0
    assert "--period" in r.output


def test_akzeptanz_2_buchung_ohne_steuerschluessel_sperrt(tmp_path):
    url, konfig = umgebung(
        tmp_path, AUGUST + [buchung("10001", "8200", "99.00", text="Erlös ohne BU")]
    )
    r = runner.invoke(
        app,
        ["ustva", "pruefen", "--period", "2026-08", "--db", url, "--config", konfig],
    )
    assert r.exit_code == 1, r.output
    assert "Freigabe gesperrt" in r.output
    assert "Erlöskonto 8200 ohne Steuerschlüssel" in text(r)


def test_akzeptanz_7_ig_lieferung_ohne_bestaetigte_ustid(tmp_path):
    url, konfig = umgebung(tmp_path, bestaetigt=False)
    r = runner.invoke(
        app,
        ["ustva", "pruefen", "--period", "2026-08", "--db", url, "--config", konfig],
    )
    assert r.exit_code == 1, r.output
    assert "USt-IdNr. ATU12345678 nicht bestätigt" in text(r)
    assert "pruefe-ustid 10002" in text(r)


def test_pruefen_ohne_fehler(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(
        app,
        ["ustva", "pruefen", "--period", "2026-08", "--db", url, "--config", konfig],
    )
    assert r.exit_code == 0, r.output
    assert "Freigabe möglich" in r.output


def test_quartal_passt_nicht_zur_konfiguration(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(
        app,
        ["ustva", "pruefen", "--period", "2026-Q3", "--db", url, "--config", konfig],
    )
    assert r.exit_code == 1
    assert "voranmeldungszeitraum" in r.output
