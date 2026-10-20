"""CLI ``accounti ustva`` — Kennziffern, Plausibilisierung (Akzeptanz 1, 2, 7)."""

import json
from datetime import date, datetime
from decimal import Decimal

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_buchung, speichere_kontakt
from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from tests.elster_hilfe import als_eric
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


# --- Freigabe und Übermittlung (Akzeptanz 3 und 4) ----------------------------------


def mit_attrappe(konfig):
    """Probelauf-Konfiguration: Attrappe statt ERiC, eigene Hersteller-ID."""
    with open(konfig, "a", encoding="utf-8") as datei:
        datei.write("  uebermittler: attrappe\n  hersteller_id: '12345'\n")


def befehl(url, konfig, tmp_path, *argumente):
    archiv = (
        ["--archiv", str(tmp_path / "archiv")] if "uebermitteln" in argumente else []
    )
    return runner.invoke(
        app,
        ["ustva", *argumente, "--period", "2026-08", "--db", url, "--config", konfig]
        + archiv,
    )


def protokoll(url, tmp_path, *extra):
    return runner.invoke(
        app,
        [
            "elster",
            "protokoll",
            "--db",
            url,
            "--archiv",
            str(tmp_path / "archiv"),
            *extra,
        ],
    )


def test_akzeptanz_3_testmodus_per_cli(tmp_path):
    url, konfig = umgebung(tmp_path)
    datei = tmp_path / "ustva.xml"
    r = befehl(url, konfig, tmp_path, "uebermitteln", "--test", "--ausgabe", str(datei))
    assert r.exit_code == 0, r.output
    assert "nichts abgegeben" in text(r)
    assert "ERiC nicht eingerichtet" in text(r)
    xml = datei.read_text(encoding="utf-8")
    assert "<Testmerker>700000004</Testmerker>" in xml
    assert "<Kz83>2145.18</Kz83>" in xml
    p = protokoll(url, tmp_path)
    assert p.exit_code == 0, p.output
    assert "pruefung" in p.output and "vollständig und unverändert" in text(p)


def test_echte_abgabe_braucht_freigabe(tmp_path, monkeypatch):
    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    als_eric(monkeypatch)
    assert befehl(url, konfig, tmp_path, "uebermitteln", "--test").exit_code == 0
    r = befehl(url, konfig, tmp_path, "uebermitteln")
    assert r.exit_code == 1
    assert "nicht freigegeben" in text(r)


def test_attrappe_gibt_per_cli_nicht_echt_ab(tmp_path):
    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    assert befehl(url, konfig, tmp_path, "freigeben", "--von", "Erika").exit_code == 0
    assert befehl(url, konfig, tmp_path, "uebermitteln", "--test").exit_code == 0
    r = befehl(url, konfig, tmp_path, "uebermitteln")
    assert r.exit_code == 1
    assert "Attrappe gibt nichts ab" in text(r)


def test_erster_lauf_ist_der_testmodus(tmp_path, monkeypatch):
    """Spec 5: „Testmodus — Default beim ersten Lauf“."""
    from accounti.db.repository import lade_posten

    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    eric = als_eric(monkeypatch)
    assert befehl(url, konfig, tmp_path, "freigeben", "--von", "Erika").exit_code == 0
    erster = befehl(url, konfig, tmp_path, "uebermitteln")
    assert erster.exit_code == 0, erster.output
    assert "Erster Lauf" in text(erster) and "nichts abgegeben" in text(erster)
    assert eric.gesendet == [] and len(eric.geprueft) == 1
    zweiter = befehl(url, konfig, tmp_path, "uebermitteln")
    assert zweiter.exit_code == 0, zweiter.output
    assert "Erster Lauf" not in text(zweiter)
    assert "Modus echt" in text(zweiter) and len(eric.gesendet) == 1
    engine, make_session = session_factory(url)
    with make_session() as s:
        assert len(lade_posten(s)) == 1
    engine.dispose()


def test_ein_jahr_wird_nicht_uebermittelt(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(
        app,
        ["ustva", "uebermitteln", "--period", "2026", "--test", "--db", url]
        + ["--config", konfig, "--archiv", str(tmp_path / "archiv")],
    )
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert "kein Voranmeldungszeitraum" in text(r)


def test_freigabe_gesperrt_per_cli(tmp_path):
    url, konfig = umgebung(tmp_path, AUGUST + [buchung("10001", "8200", "99.00")])
    r = befehl(url, konfig, tmp_path, "freigeben", "--von", "Erika Muster")
    assert r.exit_code == 1
    assert "Freigabe gesperrt" in text(r) and "8200" in text(r)


def test_akzeptanz_4_freigeben_und_uebermitteln_per_cli(tmp_path, monkeypatch):
    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    als_eric(monkeypatch)
    f = befehl(url, konfig, tmp_path, "freigeben", "--von", "Erika Muster")
    assert f.exit_code == 0, f.output
    assert "Freigegeben von Erika Muster" in text(f)
    assert "2.145,18" in text(f)
    assert befehl(url, konfig, tmp_path, "uebermitteln", "--test").exit_code == 0
    u = befehl(url, konfig, tmp_path, "uebermitteln")
    assert u.exit_code == 0, u.output
    ausgabe = text(u)
    assert "ERiC-Doppel im Test" in ausgabe
    assert "Ticket attrappe-0001" in ausgabe
    assert "Protokoll Nr. 2" in ausgabe
    p = protokoll(url, tmp_path, "--csv", str(tmp_path / "protokoll.csv"))
    assert p.exit_code == 0, p.output
    assert "echt" in p.output and "vollständig und unverändert" in text(p)
    tabelle = (tmp_path / "protokoll.csv").read_text(encoding="utf-8")
    assert tabelle.count("\n") == 3  # Kopf + Testlauf + Abgabe
    assert "attrappe-0001" in tabelle and "Erika Muster" in tabelle


def test_akzeptanz_5_zahllast_per_cli_als_offener_posten(tmp_path, monkeypatch):
    from accounti.db.repository import lade_kontakte, lade_posten

    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    als_eric(monkeypatch)
    assert befehl(url, konfig, tmp_path, "freigeben", "--von", "Erika").exit_code == 0
    assert befehl(url, konfig, tmp_path, "uebermitteln", "--test").exit_code == 0
    u = befehl(url, konfig, tmp_path, "uebermitteln")
    assert u.exit_code == 0, u.output
    assert "Zahllast 2.145,18 € als offener Posten bei Finanzamt München" in text(u)
    assert "fällig 10.09.2026" in text(u)
    engine, make_session = session_factory(url)
    with make_session() as s:
        (posten,) = lade_posten(s)
        kontakt = next(k for k in lade_kontakte(s) if k.id == posten.kontakt_id)
    engine.dispose()
    assert (kontakt.name, posten.betrag) == ("Finanzamt München", D("2145.18"))
    liste = runner.invoke(app, ["opos", "liste", "--db", url])
    assert liste.exit_code == 0, liste.output
    assert "Finanzamt" in text(liste)  # die Spalte bricht den Namen um
    assert "1 Posten · Rest 2.145,18 €" in text(liste)


def test_gescheiterte_zahllast_wird_nachgeholt(tmp_path, monkeypatch):
    import accounti.elster.zahllast as zahllast
    from accounti.db.repository import lade_posten

    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    als_eric(monkeypatch)
    assert befehl(url, konfig, tmp_path, "freigeben", "--von", "Erika").exit_code == 0
    assert befehl(url, konfig, tmp_path, "uebermitteln", "--test").exit_code == 0

    def kaputt(*args, **kwargs):
        raise ValueError("Personenkontenkreis 70000–99999 ist voll")

    monkeypatch.setattr(zahllast, "buche_zahllast", kaputt)
    u = befehl(url, konfig, tmp_path, "uebermitteln")
    assert u.exit_code == 1 and isinstance(u.exception, SystemExit)
    assert "Ticket attrappe-0001" in text(u)  # die Abgabe wird trotzdem gezeigt
    assert "Zahllast nicht gebucht" in text(u) and "elster zahllast" in text(u)
    monkeypatch.undo()
    nach = runner.invoke(app, ["elster", "zahllast", "--db", url, "--config", konfig])
    assert nach.exit_code == 0, nach.output
    assert "Zahllast 2.145,18 € als offener Posten" in text(nach)
    leer = runner.invoke(app, ["elster", "zahllast", "--db", url, "--config", konfig])
    assert leer.exit_code == 0 and "nichts nachzubuchen" in text(leer)
    engine, make_session = session_factory(url)
    with make_session() as s:
        assert len(lade_posten(s)) == 1
    engine.dispose()


def test_protokoll_nennt_die_kennziffer_der_meldeart(tmp_path):
    from accounti.elster.protokoll import neuer_eintrag, protokolliere
    from accounti.models.elster import Meldeart, Modus

    url, _ = umgebung(tmp_path)
    engine, make_session = session_factory(url)
    with make_session() as s:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.DAUERFRIST, zeitraum="2026", modus=Modus.PRUEFUNG,
                weg="intern", datensatz="<x/>", erfolgreich=True, ergebnis="geprüft",
                pruefbericht="{}", betrag=D("4000.00"),
            ),
        )  # fmt: skip
        s.commit()
    engine.dispose()
    r = runner.invoke(
        app,
        ["elster", "protokoll", "--db", url, "--archiv", "fehlt"],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code == 0, r.output
    assert "Kz 38 4.000,00" in text(r) and "Kz 83" not in text(r)
