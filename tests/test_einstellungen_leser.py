"""Abschnittsleser (Baustein 10c P4, Schritt 2; AK76, A41, A42, A54, D7, D25).

Vorrang nach E2: Umgebung (``${VAR}`` der Datei) › Festlegung › Datenbank › Datei ›
Standard. Ein Stand je Befehl bzw. Anfrage: Datei beim ersten Lesen angeheftet,
Datenbank als Schnappschuss beim Binden; Caches über Inhalts- bzw. Zeilen-Hash.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repo_einstellungen import fuege_version_an
from accounti.einstellungen.leser import (
    DatenbankQuelle,
    EinstellungenNichtLesbar,
    EinstellungsquelleFehlt,
    KonfigurationError,
    herkunft_roh,
    im_pruefmodus,
    lies_abschnitt,
    lies_datei,
    mit_quelle,
    neuer_stand,
    parse_text,
    pruefmodus,
    quelle_vorhanden,
    ueberlagert,
)
from accounti.konfiguration import Buchhaltung, lade_buchhaltung
from tests.pg_hilfe import mit_postgresql

JETZT = datetime(2026, 11, 4, 10, 0, 0)


@pytest.fixture
def db(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    return url


def version(url: str, abschnitt: str, daten: dict, jetzt: datetime = JETZT) -> None:
    engine, fabrik = session_factory(url)
    try:
        with fabrik() as s:
            fuege_version_an(
                s,
                abschnitt,
                daten,
                person="erika",
                grund="Probe",
                quelle="cli",
                jetzt=jetzt,
            )
            s.commit()
    finally:
        engine.dispose()


def konfig(tmp_path: Path, text: str, name: str = "accounti.yaml") -> Path:
    pfad = tmp_path / name
    pfad.write_text(text, encoding="utf-8")
    return pfad


def test_ohne_stand_nur_datei(tmp_path, db):
    """Außerhalb von CLI und Web gibt es keinen Stand — dann gilt nur die Datei (E5)."""
    pfad = konfig(tmp_path, "buchhaltung:\n  bank_konto: '1210'\n")
    version(db, "buchhaltung", {"bank_konto": "1800"})
    assert lies_abschnitt(pfad, "buchhaltung") == {"bank_konto": "1210"}
    assert lade_buchhaltung(pfad).bank_konto == "1210"


def test_datenbank_schlaegt_datei(tmp_path, db):
    pfad = konfig(tmp_path, "buchhaltung:\n  bank_konto: '1210'\n")
    version(db, "buchhaltung", {"bank_konto": "1800", "kontenrahmen": "SKR04"})
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "buchhaltung") == {
            "bank_konto": "1800",
            "kontenrahmen": "SKR04",
        }
        herkunft = herkunft_roh(pfad, "buchhaltung")
    assert herkunft.art == "datenbank" and herkunft.version == 1
    assert herkunft.person == "erika" and herkunft.erstellt_am == JETZT


def test_ohne_beides_gilt_der_standard(tmp_path, db):
    pfad = konfig(tmp_path, "mandant:\n  name: X\n")
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "buchhaltung") == {}
        assert lade_buchhaltung(pfad) == Buchhaltung()
        assert herkunft_roh(pfad, "buchhaltung").art == "standard"
        assert not quelle_vorhanden(pfad, "buchhaltung")
        assert quelle_vorhanden(pfad, "mandant")


def test_festgelegter_abschnitt_nimmt_die_datei_trotz_version(tmp_path, db):
    pfad = konfig(
        tmp_path,
        "einstellungen:\n  festgelegt: [buchhaltung]\n"
        "buchhaltung:\n  bank_konto: '1210'\nkasse:\n  konto: '1000'\n",
    )
    version(db, "buchhaltung", {"bank_konto": "1800"})
    version(db, "kasse", {"konto": "1600"})
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "buchhaltung") == {"bank_konto": "1210"}
        assert herkunft_roh(pfad, "buchhaltung").art == "festgelegt"
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}


def test_festlegung_mit_unbekanntem_abschnitt_ist_ein_fehler(tmp_path):
    pfad = konfig(tmp_path, "einstellungen:\n  festgelegt: [buchhaltng]\n")
    with pytest.raises(
        KonfigurationError, match="einstellungen.festgelegt.*buchhaltng"
    ):
        lies_abschnitt(pfad, "buchhaltung")
    pfad = konfig(tmp_path, "einstellungen:\n  quelle: beides\n")
    with pytest.raises(KonfigurationError, match="einstellungen.quelle"):
        lies_abschnitt(pfad, "buchhaltung")


def test_quelle_datei_fuer_alle(tmp_path, db):
    pfad = konfig(
        tmp_path,
        "einstellungen:\n  quelle: datei\nbuchhaltung:\n  bank_konto: '1210'\n",
    )
    version(db, "buchhaltung", {"bank_konto": "1800"})
    version(db, "kasse", {"konto": "1600"})
    version(db, "einrichtung", {"ausgeblendet": ["bank"]})
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "buchhaltung") == {"bank_konto": "1210"}
        assert lies_abschnitt(pfad, "kasse") == {}
        # ein reiner Datenbank-Abschnitt hat keinen Datei-Stand
        assert lies_abschnitt(pfad, "einrichtung") == {"ausgeblendet": ["bank"]}


def test_umgebung_schlaegt_alles(tmp_path, db):
    """AK76: ``${VAR}`` der Datei bleibt auch bei Datenbank-Version — feldweise; den
    aufgelösten Wert über ``lade_versand`` prüft Schritt 4."""
    pfad = konfig(
        tmp_path,
        "versand:\n  absender: '${VERSAND_ABSENDER}'\n  smtp:\n    host: smtp.a\n",
    )
    version(
        db,
        "versand",
        {"absender": "x@b.example", "betreff": "Rechnung", "smtp": {"host": "smtp.b"}},
    )
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "versand") == {
            "absender": "${VERSAND_ABSENDER}",
            "betreff": "Rechnung",
            "smtp": {"host": "smtp.b"},
        }


def test_platzhalter_aus_der_datenbank_wird_nicht_weitergegeben(tmp_path, db):
    """H1: ein ``${…}`` aus der Datenbank wird nie aufgelöst — ersetzt durch das
    Platzhalterblatt der Datei an demselben Pfad, sonst entfällt es."""
    pfad = konfig(
        tmp_path,
        "versand:\n  smtp:\n    host: smtp.a\n    passwort: '${SMTP_PASS}'\n"
        "belegkanaele:\n  connectoren:\n    - name: portal\n      typ: json\n",
    )
    version(
        db,
        "versand",
        {
            "betreff": "x ${HOME}",
            "smtp": {"host": "smtp.b", "passwort": "${SMTP_PASS}"},
            "bcc": "${ACCOUNTI_SCHLUESSEL}",
        },
    )
    version(
        db,
        "belegkanaele",
        {
            "connectoren": [
                {
                    "name": "portal",
                    "typ": "json",
                    "basis_url": "https://p.example",
                    "kopfzeilen": {"X-Key": "${ACCOUNTI_SCHLUESSEL}", "A": "b"},
                    "parameter": ["${HOME}"],
                }
            ]
        },
    )
    with mit_quelle(DatenbankQuelle(db)):
        versand = lies_abschnitt(pfad, "versand")
        kanaele = lies_abschnitt(pfad, "belegkanaele")
    assert versand == {"smtp": {"host": "smtp.b", "passwort": "${SMTP_PASS}"}}
    assert kanaele == {
        "connectoren": [
            {
                "name": "portal",
                "typ": "json",
                "basis_url": "https://p.example",
                "kopfzeilen": {"A": "b"},
            }
        ]
    }


def test_fehlende_datei_ist_leer_versionen_gelten(tmp_path, db):
    """D25: Eine fehlende Datei ist ein leerer Startwert — Versionen gelten."""
    pfad = tmp_path / "gibt-es-nicht.yaml"
    assert lies_abschnitt(pfad, "buchhaltung") == {}
    assert lies_datei(pfad) == {}
    version(db, "buchhaltung", {"kontenrahmen": "SKR04"})
    with mit_quelle(DatenbankQuelle(db)):
        assert lade_buchhaltung(pfad).kontenrahmen == "SKR04"
        assert quelle_vorhanden(pfad, "buchhaltung")
        assert not quelle_vorhanden(pfad, "mandant")
    assert not pfad.exists()


def test_pilot_lader_lesen_ueber_den_leser(tmp_path, db):
    from accounti.elster.konfiguration import lade_elster

    pfad = konfig(
        tmp_path,
        "buchhaltung:\n  kontenrahmen: SKR03\n"
        "elster:\n  voranmeldungszeitraum: monat\n",
    )
    version(db, "buchhaltung", {"kontenrahmen": "SKR04", "bank_konto": "1800"})
    version(db, "elster", {"voranmeldungszeitraum": "quartal", "bundesland": "HH"})
    with mit_quelle(DatenbankQuelle(db)):
        b = lade_buchhaltung(pfad)
        e = lade_elster(pfad)
    assert (b.kontenrahmen, b.bank_konto) == ("SKR04", "1800")
    assert (e.voranmeldungszeitraum_fuer(2026), e.bundesland) == ("quartal", "HH")
    # OSS-Umsatzsteuerkonto aus integrationen nach dem Kontenrahmen der Version
    assert "3817" in e.konten_ohne_kennziffer and "1767" not in e.konten_ohne_kennziffer
    # ohne Stand: Datei
    assert lade_elster(pfad).voranmeldungszeitraum_fuer(2026) == "monat"


def test_pilot_lader_fallback_mandant_kontenrahmen(tmp_path, db):
    """Paket A: ``mandant.kontenrahmen`` gilt, wenn ``buchhaltung`` ihn nicht nennt —
    auch aus einer Version von ``mandant``; ein Widerspruch bleibt ein Fehler."""
    pfad = konfig(tmp_path, "mandant:\n  kontenrahmen: skr04\n")
    assert lade_buchhaltung(pfad).kontenrahmen == "SKR04"
    version(db, "buchhaltung", {"kontenrahmen": "SKR03"})
    with (
        mit_quelle(DatenbankQuelle(db)),
        pytest.raises(KonfigurationError, match="widersprechen"),
    ):
        lade_buchhaltung(pfad)


def test_pruefmodus_fehlende_variable_bleibt_text(tmp_path, monkeypatch):
    from accounti.belege.kanaele.einstellungen import loese_auf
    from accounti.erechnung.versand import lade_versand

    monkeypatch.delenv("P4A_FEHLT", raising=False)
    pfad = konfig(
        tmp_path,
        "versand:\n  absender: a@b.example\n  smtp:\n    host: smtp.a\n"
        "    passwort: '${P4A_FEHLT}'\n",
    )
    with pytest.raises(KonfigurationError, match="P4A_FEHLT"):
        lade_versand(pfad)
    with pytest.raises(KonfigurationError, match="P4A_FEHLT"):
        loese_auf("${P4A_FEHLT}")
    assert not im_pruefmodus()
    with pruefmodus():
        assert im_pruefmodus()
        assert lade_versand(pfad).smtp.passwort == "${P4A_FEHLT}"
        assert loese_auf("x ${P4A_FEHLT}") == "x ${P4A_FEHLT}"
    assert not im_pruefmodus()


def test_betriebsfeld_kommt_aus_der_datei(tmp_path, db):
    pfad = konfig(
        tmp_path,
        "elster:\n  eric:\n    bibliothek: /opt/eric/lib/libericapi.so\n"
        "pruefung:\n  archiv: archiv/a\n"
        "belegkanaele:\n  email:\n"
        "    - {name: a, host: imap.a, benutzer: u, ca_datei: /etc/a.pem}\n"
        "    - {name: b, host: imap.b, benutzer: u}\n",
    )
    version(
        db,
        "elster",
        {"bundesland": "BY", "eric": {"bibliothek": "/tmp/boese.so", "log": "/tmp"}},
    )
    version(db, "pruefung", {"archiv": "/etc", "kleinbetrag_grenze": 200})
    version(
        db,
        "belegkanaele",
        {
            "email": [
                {"name": "a", "host": "imap.neu", "benutzer": "u", "ca_datei": "/x"},
                {"name": "b", "host": "imap.b", "benutzer": "u", "ca_datei": "/y"},
            ]
        },
    )
    with mit_quelle(DatenbankQuelle(db)):
        elster = lies_abschnitt(pfad, "elster")
        pruefung = lies_abschnitt(pfad, "pruefung")
        kanaele = lies_abschnitt(pfad, "belegkanaele")
    assert elster == {
        "bundesland": "BY",
        "eric": {"bibliothek": "/opt/eric/lib/libericapi.so"},
    }
    assert pruefung == {"archiv": "archiv/a", "kleinbetrag_grenze": 200}
    assert kanaele["email"] == [
        {"name": "a", "host": "imap.neu", "benutzer": "u", "ca_datei": "/etc/a.pem"},
        {"name": "b", "host": "imap.b", "benutzer": "u"},
    ]


def test_betriebsfeld_der_version_gilt_nie(tmp_path, db):
    """G-N3, A42: Fehlt das Betriebsfeld in der Datei, gilt der Standard, nicht die
    Version."""
    from accounti.pruefung.einstellungen import lade_pruefung

    pfad = konfig(tmp_path, "pruefung:\n  kleinbetrag_grenze: 250\n")
    version(db, "pruefung", {"archiv": "/etc", "kontenrahmen_datei": "/etc/passwd"})
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "pruefung") == {}
        standard = lade_pruefung(tmp_path / "leer.yaml")
        assert lade_pruefung(pfad).archiv == standard.archiv


def test_betriebsabschnitt_nie_aus_der_datenbank(tmp_path, db):
    pfad = konfig(tmp_path, "server:\n  port: 8400\n")
    version(db, "server", {"port": 9999})
    version(db, "auth", {"passwort_mindestlaenge": 4})
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "server") == {"port": 8400}
        assert lies_abschnitt(pfad, "auth") == {}
        assert herkunft_roh(pfad, "server").art == "betrieb"


def test_nur_db_abschnitt_ignoriert_die_datei(tmp_path, db):
    pfad = konfig(tmp_path, "einrichtung:\n  ausgeblendet: [bank]\n")
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "einrichtung") == {}
    version(db, "einrichtung", {"ausgeblendet": ["vier_augen"]})
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "einrichtung") == {"ausgeblendet": ["vier_augen"]}


def test_schnappschuss_bleibt_in_der_anfrage(tmp_path, db):
    pfad = konfig(tmp_path, "")
    version(db, "kasse", {"konto": "1000"})
    with neuer_stand() as stand:
        stand.binde(DatenbankQuelle(db))
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
        version(db, "kasse", {"konto": "1600"})
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}


def test_datei_aenderung_im_stand_unsichtbar(tmp_path):
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\n")
    with mit_quelle(None):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
        konfig(tmp_path, "kasse:\n  konto: '1600'\n")
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
        assert lies_datei(pfad) == {"kasse": {"konto": "1000"}}
    with mit_quelle(None):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}


def test_cache_liest_neu_nach_gleich_langer_aenderung(tmp_path):
    """M7: gleiche Länge, gleicher Zeitstempel — der Inhalts-Hash erkennt es."""
    pfad = konfig(tmp_path, "buchhaltung:\n  kontenrahmen: SKR03\n")
    alt = pfad.stat()
    with mit_quelle(None):
        assert lade_buchhaltung(pfad).kontenrahmen == "SKR03"
    konfig(tmp_path, "buchhaltung:\n  kontenrahmen: SKR04\n")
    os.utime(pfad, ns=(alt.st_atime_ns, alt.st_mtime_ns))
    assert pfad.stat().st_size == alt.st_size
    with mit_quelle(None):
        assert lade_buchhaltung(pfad).kontenrahmen == "SKR04"


def test_datei_hash_nur_ueber_den_abschnitt(tmp_path):
    """G-N2: Kommentar oder anderer Abschnitt geändert → ``datei_hash`` gleich."""
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\nzahlung:\n  vorlauf_tage: 3\n")
    vorher = herkunft_roh(pfad, "kasse").datei_hash
    assert vorher is not None
    konfig(
        tmp_path,
        "# Kommentar\nkasse:\n  konto: '1000'   # Kasse\nzahlung:\n  vorlauf_tage: 5\n",
    )
    assert herkunft_roh(pfad, "kasse").datei_hash == vorher
    konfig(tmp_path, "kasse:\n  konto: '1600'\n")
    assert herkunft_roh(pfad, "kasse").datei_hash != vorher
    assert herkunft_roh(pfad, "zahlung").datei_hash is None


def test_cache_erkennt_neu_angelegte_datenbank(tmp_path):
    """G-N7: dieselbe URL, neu angelegte Datenbank, wieder Version 1 → neuer Inhalt."""
    pfad = konfig(tmp_path, "")
    url = f"sqlite:///{tmp_path / 'neu.db'}"
    for konto in ("1000", "1600"):
        engine, _ = session_factory(url)
        init_db(engine)
        engine.dispose()
        version(url, "kasse", {"konto": konto}, jetzt=JETZT + timedelta(seconds=1))
        with mit_quelle(DatenbankQuelle(url)):
            assert lies_abschnitt(pfad, "kasse") == {"konto": konto}
        (tmp_path / "neu.db").unlink()


def test_rueckgabe_ist_eine_kopie(tmp_path, db):
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\n")
    version(db, "elster", {"finanzamt": {"name": "FA"}})
    erste = lies_abschnitt(pfad, "kasse")
    erste["konto"] = "x"
    assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
    ganz = lies_datei(pfad)
    ganz["kasse"]["konto"] = "y"
    assert lies_datei(pfad) == {"kasse": {"konto": "1000"}}
    with mit_quelle(DatenbankQuelle(db)):
        e = lies_abschnitt(pfad, "elster")
        e["finanzamt"]["name"] = "anders"
        assert lies_abschnitt(pfad, "elster") == {"finanzamt": {"name": "FA"}}


def test_schnappschuss_haelt_keine_verbindung(tmp_path, db):
    """N10: Nach ``binde`` ist die Lesetransaktion zu — eine zweite Sitzung holt
    ``BEGIN EXCLUSIVE`` und committet ohne Warten (URL wie Engine)."""
    version(db, "kasse", {"konto": "1000"})
    datei = tmp_path / "a.db"
    engine, _ = session_factory(db)
    try:
        for quelle in (DatenbankQuelle(db), DatenbankQuelle(engine=engine)):
            with neuer_stand() as stand:
                stand.binde(quelle)
                v = sqlite3.connect(datei, timeout=0)
                try:
                    v.execute("BEGIN EXCLUSIVE")
                    v.execute("UPDATE buchungssaetze SET id = id WHERE 0")
                    v.commit()
                finally:
                    v.close()
    finally:
        engine.dispose()


def test_prozess_cache_unter_threads(tmp_path, db):
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\n")
    version(db, "elster", {"bundesland": "HH"})
    ergebnisse: list[object] = []
    start = threading.Barrier(8)

    def lesen() -> None:
        start.wait()
        with mit_quelle(DatenbankQuelle(db)):
            ergebnisse.append(
                (lies_abschnitt(pfad, "kasse"), lies_abschnitt(pfad, "elster"))
            )

    faeden = [threading.Thread(target=lesen) for _ in range(8)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    assert ergebnisse == [({"konto": "1000"}, {"bundesland": "HH"})] * 8


def test_stichtag_nimmt_die_damals_gueltige_version(tmp_path, db):
    pfad = konfig(tmp_path, "")
    version(db, "kasse", {"konto": "1000"}, jetzt=JETZT)
    version(db, "kasse", {"konto": "1600"}, jetzt=JETZT + timedelta(days=30))
    with mit_quelle(DatenbankQuelle(db), stichtag=JETZT + timedelta(days=1)):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
    with mit_quelle(DatenbankQuelle(db), stichtag=JETZT - timedelta(days=1)):
        assert lies_abschnitt(pfad, "kasse") == {}
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}


def test_ueberlagert_wirkt_nur_im_block(tmp_path, db):
    pfad = konfig(tmp_path, "pruefung:\n  archiv: archiv/a\n")
    version(db, "kasse", {"konto": "1000"})
    with mit_quelle(DatenbankQuelle(db)):
        with ueberlagert({"kasse": {"konto": "1600"}, "pruefung": {"archiv": "/etc"}}):
            assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}
            # wie eine Version: das Betriebsfeld kommt aus der Datei
            assert lies_abschnitt(pfad, "pruefung") == {"archiv": "archiv/a"}
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
    with ueberlagert({"kasse": {"konto": "1610"}}):  # auch ohne Stand
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1610"}
    assert lies_abschnitt(pfad, "kasse") == {}


def test_keine_neue_sqlite_datei(tmp_path):
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\n")
    datei = tmp_path / "tippfehler.db"
    with mit_quelle(DatenbankQuelle(f"sqlite:///{datei}")):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
    assert not datei.exists()


def test_ohne_tabelle_wie_datei(tmp_path):
    """Eine Datenbank vor P4 (ohne ``einstellungen``) ist leer — es gilt die Datei."""
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\n")
    datei = tmp_path / "alt.db"
    with sqlite3.connect(datei) as v:
        v.execute("CREATE TABLE buchungssaetze (id VARCHAR(36) PRIMARY KEY)")
    with mit_quelle(DatenbankQuelle(f"sqlite:///{datei}")):
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
        assert herkunft_roh(pfad, "kasse").art == "datei"


def test_nicht_erreichbar_fail_closed(tmp_path):
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\nserver:\n  port: 8400\n")
    kaputt = tmp_path / "kaputt.db"
    kaputt.write_bytes(b"das ist keine Datenbank" * 100)
    with mit_quelle(DatenbankQuelle(f"sqlite:///{kaputt}")):
        with pytest.raises(EinstellungenNichtLesbar, match="nicht lesen"):
            lies_abschnitt(pfad, "kasse")
        assert lies_abschnitt(pfad, "server") == {"port": 8400}  # Betrieb geht
    nicht_da = DatenbankQuelle("postgresql+psycopg://u:geheim@127.0.0.1:1/x")
    with mit_quelle(nicht_da), pytest.raises(EinstellungenNichtLesbar) as fehler:
        lies_abschnitt(pfad, "kasse")
    assert "geheim" not in str(fehler.value)


def test_web_ungebunden_und_fremder_pfad_fail_closed(tmp_path, db):
    """D5: Im Web liest ein ungebundener Stand keinen Datenbank-Abschnitt, ein
    gebundener keinen aus einer anderen Konfiguration — Betrieb geht immer."""
    from accounti.einstellungen.leser import binde_gesellschaft

    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\nauth: {}\n")
    andere = konfig(tmp_path, "kasse:\n  konto: '1600'\n", "b.yaml")

    class Dienste:
        def quelle(self, kuerzel: str) -> DatenbankQuelle:
            return DatenbankQuelle(db)

    class G:
        kuerzel = "a"
        konfiguration = str(pfad)

    with neuer_stand(web=True) as stand:
        assert lies_abschnitt(pfad, "auth") == {}
        with pytest.raises(EinstellungsquelleFehlt):
            lies_abschnitt(pfad, "kasse")
        binde_gesellschaft(stand, Dienste(), G())
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1000"}
        with pytest.raises(EinstellungsquelleFehlt):
            lies_abschnitt(andere, "kasse")
        assert stand.kuerzel == "a" and stand.streng


def test_cli_fremder_registry_pfad_fail_closed(tmp_path, db):
    """D5, Ausnahme in der CLI: eine andere ``--config`` geht (E5), die Konfiguration
    einer anderen Gesellschaft der Registry nicht."""
    eigene = konfig(tmp_path, "kasse:\n  konto: '1000'\n", "a.yaml")
    fremde = konfig(tmp_path, "kasse:\n  konto: '1600'\n", "b.yaml")
    sonst = konfig(tmp_path, "kasse:\n  konto: '1610'\n", "c.yaml")
    with neuer_stand(fremde_pfade=frozenset({str(fremde.resolve())})) as stand:
        stand.binde(DatenbankQuelle(db))
        assert lies_abschnitt(eigene, "kasse") == {"konto": "1000"}
        assert lies_abschnitt(sonst, "kasse") == {"konto": "1610"}
        with pytest.raises(EinstellungsquelleFehlt):
            lies_abschnitt(fremde, "kasse")
        with mit_quelle(DatenbankQuelle(db), fremde):
            assert lies_abschnitt(fremde, "kasse") == {"konto": "1600"}


def test_ersatzquelle_beim_ersten_lesen(tmp_path, db):
    """D3: Ein CLI-Stand ohne Bindung nimmt beim ersten Lesen seine Ersatzquelle."""
    pfad = konfig(tmp_path, "")
    version(db, "kasse", {"konto": "1600"})
    aufrufe: list[int] = []

    def ersatz() -> DatenbankQuelle:
        aufrufe.append(1)
        return DatenbankQuelle(db)

    with neuer_stand(ersatz=ersatz) as stand:
        assert not stand.gebunden
        assert lies_abschnitt(pfad, "server") == {}  # Betrieb bindet nicht
        assert aufrufe == []
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}
    assert aufrufe == [1]


def test_kaputtes_yaml_und_fremde_kodierung_sind_konfigurationsfehler(tmp_path):
    from accounti.konfiguration import KonfigurationError as AusKonfiguration

    assert AusKonfiguration is KonfigurationError
    pfad = konfig(tmp_path, "kasse: [\n")
    with pytest.raises(KonfigurationError, match="kein gültiges YAML"):
        lies_abschnitt(pfad, "kasse")
    pfad.write_bytes("kasse:\n  konto: 'Ä'\n".encode("latin-1"))
    with pytest.raises(KonfigurationError, match="keine UTF-8-Datei"):
        lade_buchhaltung(pfad)
    pfad = konfig(tmp_path, "kasse: 5\n")
    with pytest.raises(
        KonfigurationError, match="Abschnitt 'kasse' muss eine Zuordnung"
    ):
        lies_abschnitt(pfad, "kasse")


def test_parse_text_grenze_anker_zeile_spalte():
    assert parse_text("a: 1\nb: [x, y]\n") == {"a": 1, "b": ["x", "y"]}
    with pytest.raises(KonfigurationError, match="zu groß"):
        parse_text("a: " + "x" * 70_000)
    assert parse_text("a: " + "x" * 100, grenze=200) == {"a": "x" * 100}
    with pytest.raises(KonfigurationError, match=r"Zeile 1, Spalte 4: Anker"):
        parse_text("a: &x [1, 2]\nb: *x\n")
    with pytest.raises(KonfigurationError, match=r"Zeile 2, Spalte 4"):
        parse_text("a: 1\nb: *y\n")
    with pytest.raises(KonfigurationError, match=r"Zeile 2, Spalte 4: kein gültiges"):
        parse_text("a: 1\nb: ]\n")


def test_datei_cache_ohne_wiederholtes_parsen(tmp_path, monkeypatch):
    """Dieselbe Datei in vielen Ständen wird einmal geparst (Inhalts-Hash)."""
    import yaml

    pfad = konfig(tmp_path, f"kasse:\n  konto: '{time.time_ns()}'\n")
    zaehler: list[int] = []
    echt = yaml.safe_load
    monkeypatch.setattr(yaml, "safe_load", lambda t: zaehler.append(1) or echt(t))
    for _ in range(5):
        with mit_quelle(None):
            lies_abschnitt(pfad, "kasse")
    assert zaehler == [1]


def test_betriebsfeld_unter_dem_feldnamen_nie_aus_der_version(tmp_path, db):
    """Prüfung sicher-2: ``anlagen.rechtsstand`` ist im Modell das Feld
    ``rechtsstand_datei`` (Alias, ``populate_by_name``) — auch unter dem Feldnamen
    kommt der Pfad nie aus einer Version; es gilt der Standard. Die Datei darf beide
    Schreibweisen nutzen."""
    from accounti.anlagen.konfiguration import lade_anlagen

    fremd = konfig(tmp_path, "gwg:\n  grenze: 1\n", "fremder_rechtsstand.yaml")
    version(db, "anlagen", {"rechtsstand_datei": str(fremd), "kfz_konten": ["0520"]})
    leer = konfig(tmp_path, "")
    with mit_quelle(DatenbankQuelle(db)):
        assert lies_abschnitt(leer, "anlagen") == {"kfz_konten": ["0520"]}
        assert lade_anlagen(leer).rechtsstand_datei is None
    eigen = tmp_path / "eigener_rechtsstand.yaml"
    for schluessel in ("rechtsstand", "rechtsstand_datei"):
        text = f"anlagen:\n  {schluessel}: {eigen}\n"
        pfad = konfig(tmp_path, text, f"{schluessel}.yaml")
        with mit_quelle(DatenbankQuelle(db)):
            assert lade_anlagen(pfad).rechtsstand_datei == str(eigen), schluessel


def test_ungueltiger_port_ist_nicht_lesbar_statt_traceback(tmp_path):
    """Prüfung sicher-5: Bei einem ungültigen Port wirft ``make_url`` einen
    ``ValueError`` (kein ``ArgumentError``) — die Quelle entsteht trotzdem, der
    Schnappschuss merkt sich den Fehler (fail-closed beim Lesen, ohne Passwort)."""
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\nserver:\n  port: 8400\n")
    for url in ("postgresql://u:geheim@h:abc/db", "sqlite://h:abc/x.db"):
        quelle = DatenbankQuelle(url)
        assert quelle.schluessel.startswith("ungueltig:"), url
        assert "ValueError" in (quelle.schnappschuss().fehler or ""), url
        with mit_quelle(quelle):
            assert lies_abschnitt(pfad, "server") == {"port": 8400}  # Betrieb geht
            with pytest.raises(EinstellungenNichtLesbar, match="nicht lesen") as f:
                lies_abschnitt(pfad, "kasse")
        assert "geheim" not in str(f.value)


def test_kaputtes_yaml_ohne_ausschnitt_der_zeile(tmp_path):
    """Prüfung verhalten-5: Die Meldung nennt Datei, Zeile, Spalte und das Problem,
    aber keinen Ausschnitt der Zeile — dort kann ein Passwort stehen (wie
    ``parse_text``)."""
    for text in (
        'versand:\n  smtp:\n    passwort: "Geheim123\n',  # nicht geschlossen
        "versand:\n  smtp:\n    passwort: Geheim123: x\n",  # mapping values
        "versand:\n  smtp: [Geheim123\n",
        "versand:\n  smtp:\n    passwort: !Geheim123\n",  # Tag im problem
        "versand:\n  smtp:\n    passwort: *Geheim123\n",  # Alias im problem
    ):
        pfad = konfig(tmp_path, text)
        with pytest.raises(KonfigurationError, match="kein gültiges YAML") as fehler:
            lies_abschnitt(pfad, "versand")
        meldung = str(fehler.value)
        assert "Geheim123" not in meldung, meldung
        assert meldung.startswith(f"{pfad}: kein gültiges YAML (Zeile "), meldung
        assert "\n" not in meldung, meldung


def test_fehlendes_verzeichnis_ist_nicht_lesbar(tmp_path):
    """Nachprüfung zu sicher-3: Fehlt nur die SQLite-Datei, gibt es noch keine
    Versionen (leer, nichts angelegt). Fehlt ihr Verzeichnis (Volume nicht
    eingehängt), ist die Datenbank nicht erreichbar — fail-closed statt still die
    Datei."""
    neu = tmp_path / "neu.db"
    assert DatenbankQuelle(f"sqlite:///{neu.as_posix()}").schnappschuss().fehler is None
    assert not neu.exists()
    weg = tmp_path / "volume" / "a.db"
    fehler = DatenbankQuelle(f"sqlite:///{weg.as_posix()}").schnappschuss().fehler
    assert fehler and "volume" in fehler, fehler
    assert not weg.parent.exists()


def test_sqlite_wartet_hoechstens_die_wartezeit(tmp_path):
    """Web (``QUELLE_WARTEN``): Auf eine gesperrte SQLite-Datei wartet der Schnappschuss
    höchstens ``wartezeit``, nicht die 30 s der Engine."""
    pfad = tmp_path / "a.db"
    sperre = sqlite3.connect(pfad, isolation_level=None)
    sperre.execute("CREATE TABLE x (y)")
    sperre.execute("BEGIN EXCLUSIVE")
    try:
        quelle = DatenbankQuelle(
            f"sqlite:///{pfad.as_posix()}", wartezeit=0.2, behalten=True
        )
        anfang = time.monotonic()
        ergebnis = quelle.schnappschuss()
        assert time.monotonic() - anfang < 5
        assert ergebnis.fehler and "locked" in ergebnis.fehler, ergebnis.fehler
        quelle.schliesse()
    finally:
        sperre.rollback()
        sperre.close()


def test_bindung_ohne_sofort_liest_beim_ersten_abschnitt(tmp_path, db):
    """Web (Prüfung sicher-3): ``binde(sofort=False)`` öffnet die Datenbank nicht —
    der Schnappschuss entsteht beim ersten Lesen eines Datenbank-Abschnitts, einmal je
    Stand; ein Betriebsabschnitt liest sie nie."""
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\nserver:\n  port: 8400\n")
    version(db, "kasse", {"konto": "1600"})
    gelesen: list[int] = []

    class Zaehlend(DatenbankQuelle):
        def schnappschuss(self, stichtag: datetime | None = None):  # noqa: ANN201
            gelesen.append(1)
            return super().schnappschuss(stichtag)

    with neuer_stand(web=True) as stand:
        stand.binde(Zaehlend(db), pfad, streng=True, sofort=False)
        assert stand.gebunden and gelesen == []
        assert lies_abschnitt(pfad, "server") == {"port": 8400}
        assert gelesen == []
        version(db, "kasse", {"konto": "1610"})  # vor dem ersten Lesen: gilt schon
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1610"}
        version(db, "kasse", {"konto": "1620"})
        assert lies_abschnitt(pfad, "kasse") == {"konto": "1610"}  # ein Stand
    assert gelesen == [1]


def test_behaltene_quelle_wartet_hoechstens_die_wartezeit():
    """Web (``Dienste.quelle``, Prüfung sicher-3): Unter PostgreSQL begrenzt
    ``wartezeit`` den Verbindungsaufbau (``connect_timeout``) — ein Server, der die
    Verbindung annimmt, aber nie antwortet, hält das Lesen der Einstellungen nicht auf;
    der Fehler steht im Schnappschuss, ohne Passwort."""
    import socket

    stumm = socket.create_server(("127.0.0.1", 0))  # nimmt an, antwortet nie
    port = stumm.getsockname()[1]
    quelle = DatenbankQuelle(
        f"postgresql+psycopg://u:geheim@127.0.0.1:{port}/x", wartezeit=1, behalten=True
    )
    ergebnis: list = []
    faden = threading.Thread(
        target=lambda: ergebnis.append(quelle.schnappschuss()), daemon=True
    )
    try:
        anfang = time.monotonic()
        faden.start()
        faden.join(timeout=10)
        assert not faden.is_alive(), "Verbindungsaufbau ohne Frist"
        assert time.monotonic() - anfang < 8
        assert ergebnis[0].fehler and "geheim" not in ergebnis[0].fehler
    finally:
        stumm.close()
        quelle.schliesse()


@mit_postgresql
def test_behaltene_quelle_unter_postgresql(tmp_path, pg_datenbank):
    """Web unter PostgreSQL: eine Engine (mit Pool) für alle Schnappschüsse der
    Gesellschaft, jeder Schnappschuss sieht den neuesten Stand, ``schliesse`` gibt die
    Engine frei (Prüfung sicher-3; bisher nur unter SQLite geprüft)."""
    url = pg_datenbank()
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    version(url, "kasse", {"konto": "1600"})
    pfad = konfig(tmp_path, "kasse:\n  konto: '1000'\n")
    quelle = DatenbankQuelle(url, wartezeit=3, behalten=True)
    try:
        with mit_quelle(quelle, pfad):
            assert lies_abschnitt(pfad, "kasse") == {"konto": "1600"}
        eigene = quelle._eigene
        assert eigene is not None and eigene.pool.__class__.__name__ != "NullPool"
        version(url, "kasse", {"konto": "1610"})
        with mit_quelle(quelle, pfad):
            assert lies_abschnitt(pfad, "kasse") == {"konto": "1610"}
        assert quelle._eigene is eigene  # dieselbe Engine
    finally:
        quelle.schliesse()
    assert quelle._eigene is None
