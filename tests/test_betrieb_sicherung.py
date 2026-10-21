"""Verschlüsselte Sicherung von Datenbank und Belegarchiv (Spec 4.6, Akzeptanz 7)."""

import secrets
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select, text

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import nimm_auf
from accounti.betrieb.sicherung import (
    AUSGELASSEN,
    SicherungError,
    dekodiere,
    erstelle,
    kodiere,
    pruefe,
    stelle_wieder_her,
)
from accounti.betrieb.verschluesselung import (
    ManipuliertError,
    SicherungsschluesselError,
)
from accounti.db import Base, init_db, session_factory
from accounti.db.repository import lade_ustid_pruefungen, speichere_buchung
from accounti.kontakte.ustid import pruefe_protokoll
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.auth import Rolle, TokenRecht
from tests.auth_hilfe import billige_hashes, lege_person_an
from tests.pdf_hilfe import pdf_mit_text
from tests.test_ustid_protokoll import bestaetige
from tests.zahlung_hilfe import kreditor, posten, speichere

SCHLUESSEL = secrets.token_bytes(32)


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


def url(pfad: Path) -> str:
    return f"sqlite:///{pfad.as_posix()}"


def befuelle(tmp_path: Path) -> tuple[str, Path]:
    """Gesellschaft mit Belegen im Archiv, Buchungen, Posten, Protokollen, Benutzern."""
    db = url(tmp_path / "quelle.db")
    archiv = tmp_path / "archiv-quelle"
    engine, fabrik = session_factory(db)
    init_db(engine)
    m = kreditor()
    speichere(fabrik, [m], [posten(m, "RE-1", "1190.00")])
    with fabrik() as s:
        belegarchiv = BelegArchiv(archiv)
        for i in range(3):
            nimm_auf(
                s,
                belegarchiv,
                RohBeleg(
                    dateiname=f"rechnung-{i}.pdf",
                    inhalt=pdf_mit_text(f"Rechnung {i} über 119,00 EUR"),
                    kanal="ordner",
                    herkunft="test",
                ),
            )
        for netto in ("100.00", "0.01", "12345678.99"):
            speichere_buchung(
                s,
                Buchungssatz(
                    datum=date(2026, 9, 30),
                    soll_konto="4930",
                    haben_konto="1200",
                    betrag_netto=Decimal(netto),
                    steuer_schluessel=9,
                    steuer_betrag=Decimal("19.00"),
                    buchungstext="Bürobedarf äöü ß",
                    status=BuchungStatus.GEPRUEFT,
                    confidence=0.875,
                ),
            )
        bestaetige(s, jetzt=datetime(2026, 8, 3, 9, 0))
        bestaetige(s, jetzt=datetime(2026, 8, 4, 9, 0))
        s.commit()
        person = lege_person_an(s, "chef", Rolle.FREIGEBER)
        from accounti.auth.dienst import oeffne_sitzung
        from accounti.auth.einstellungen import AuthEinstellungen
        from accounti.auth.token import lege_api_token_an

        oeffne_sitzung(s, person.benutzer, "standard", AuthEinstellungen())
        lege_api_token_an(s, "erp", "standard", [TokenRecht.OPOS_LESEN], "chef")
        s.commit()
    engine.dispose()
    return db, archiv


def tabelleninhalt(db: str) -> dict[str, list[tuple]]:
    engine, _ = session_factory(db)
    inhalt = {}
    with engine.connect() as v:
        vorhanden = set(inspect(v).get_table_names())
        for t in Base.metadata.sorted_tables:
            if t.name in vorhanden:
                spalten = list(t.primary_key.columns) or list(t.columns)
                inhalt[t.name] = [
                    tuple(z) for z in v.execute(select(t).order_by(*spalten))
                ]
    engine.dispose()
    return inhalt


def dateien(archiv: Path) -> dict[str, bytes]:
    return {
        p.relative_to(archiv).as_posix(): p.read_bytes()
        for p in archiv.rglob("*")
        if p.is_file()
    }


def test_akzeptanz_7_wiederherstellung_in_leere_umgebung(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "sicherung" / "2026-10-20.accounti"
    e = erstelle(db, archiv, ziel, SCHLUESSEL, gesellschaft="standard")
    assert e.tabellen["buchungssaetze"] == 3 and e.tabellen["belege"] == 4
    assert e.dateien == 3  # drei Belege mit Datei, einer aus den Posten ohne
    assert ziel.stat().st_mode & 0o777 == 0o600
    roh = ziel.read_bytes()
    assert "Bürobedarf".encode() not in roh and b"%PDF" not in roh  # verschlüsselt

    neu_db, neu_archiv = url(tmp_path / "neu.db"), tmp_path / "neu" / "archiv"
    w = stelle_wieder_her(ziel, neu_db, neu_archiv, SCHLUESSEL)
    assert w.tabellen == e.tabellen

    vorher, nachher = tabelleninhalt(db), tabelleninhalt(neu_db)
    for name in vorher:
        if name in AUSGELASSEN:
            assert nachher[name] == []
        else:
            assert nachher[name] == vorher[name], name
    assert len(vorher["auth_sitzungen"]) == 1  # gesichert wurde sie nicht
    # Buchungen und Belege vollständig — samt Archivdateien, bytegleich
    assert len(nachher["buchungssaetze"]) == 3 and len(nachher["belege"]) == 4
    assert dateien(neu_archiv) == dateien(archiv)
    beleg_hashes = {
        z.datei_hash
        for z in nachher_zeilen(neu_db, "belege")
        if z.dateiname.startswith("rechnung-")
    }
    assert len(beleg_hashes) == 3
    assert all(BelegArchiv(neu_archiv).enthaelt(h) for h in beleg_hashes)
    # Hash-Kette des USt-IdNr.-Protokolls bleibt gültig
    engine, fabrik = session_factory(neu_db)
    with fabrik() as s:
        assert pruefe_protokoll(lade_ustid_pruefungen(s)) == []
        # Decimal und Umlaute unverändert
        werte = (
            s.execute(text("SELECT buchungstext FROM buchungssaetze")).scalars().all()
        )
        assert set(werte) == {"Bürobedarf äöü ß"}
    engine.dispose()


def nachher_zeilen(db, tabelle):
    engine, _ = session_factory(db)
    with engine.connect() as v:
        zeilen = list(v.execute(text(f"SELECT * FROM {tabelle}")))
    engine.dispose()
    return zeilen


def test_pruefen_ohne_zu_schreiben(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "s.accounti"
    erstelle(db, archiv, ziel, SCHLUESSEL)
    e = pruefe(ziel, SCHLUESSEL)
    assert e.tabellen["buchungssaetze"] == 3 and e.dateien == 3
    assert e.manifest["datenbank"] == "sqlite"


def test_nur_in_leere_umgebung(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "s.accounti"
    erstelle(db, archiv, ziel, SCHLUESSEL)
    with pytest.raises(SicherungError, match="Datenbank ist nicht leer"):
        stelle_wieder_her(ziel, db, tmp_path / "leer", SCHLUESSEL)
    with pytest.raises(SicherungError, match="Belegarchiv .* nicht leer"):
        stelle_wieder_her(ziel, url(tmp_path / "neu.db"), archiv, SCHLUESSEL)
    assert not (tmp_path / "leer").exists()


def test_sicherung_wird_nie_ueberschrieben(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "s.accounti"
    erstelle(db, archiv, ziel, SCHLUESSEL)
    with pytest.raises(SicherungError, match="gibt es schon"):
        erstelle(db, archiv, ziel, SCHLUESSEL)


def test_falscher_schluessel_laesst_alles_leer(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "s.accounti"
    erstelle(db, archiv, ziel, SCHLUESSEL)
    neu_db, neu_archiv = url(tmp_path / "neu.db"), tmp_path / "neu-archiv"
    with pytest.raises(SicherungsschluesselError):
        stelle_wieder_her(ziel, neu_db, neu_archiv, secrets.token_bytes(32))
    assert all(z == [] for z in tabelleninhalt(neu_db).values())
    assert not neu_archiv.exists()
    assert not list(tmp_path.glob(".neu-archiv-*"))


def test_veraenderte_sicherung_wird_zurueckgerollt(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "s.accounti"
    erstelle(db, archiv, ziel, SCHLUESSEL)
    roh = bytearray(ziel.read_bytes())
    roh[-100] ^= 0x01  # im letzten Stück (Archiv, Manifest)
    kaputt = tmp_path / "kaputt.accounti"
    kaputt.write_bytes(bytes(roh))
    neu_db, neu_archiv = url(tmp_path / "neu.db"), tmp_path / "neu-archiv"
    with pytest.raises((ManipuliertError, SicherungsschluesselError)):
        stelle_wieder_her(kaputt, neu_db, neu_archiv, SCHLUESSEL)
    assert all(z == [] for z in tabelleninhalt(neu_db).values())
    assert not neu_archiv.exists()
    abgeschnitten = tmp_path / "halb.accounti"
    abgeschnitten.write_bytes(ziel.read_bytes()[: len(roh) // 2])
    with pytest.raises((ManipuliertError, SicherungsschluesselError)):
        pruefe(abgeschnitten, SCHLUESSEL)


def test_ohne_archiv(tmp_path):
    db, archiv = befuelle(tmp_path)
    ziel = tmp_path / "s.accounti"
    e = erstelle(db, None, ziel, SCHLUESSEL)
    assert e.dateien == 0 and not e.manifest["mit_archiv"]
    with pytest.raises(SicherungError, match="kein Belegarchiv"):
        stelle_wieder_her(ziel, url(tmp_path / "x.db"), tmp_path / "x", SCHLUESSEL)
    w = stelle_wieder_her(ziel, url(tmp_path / "y.db"), None, SCHLUESSEL)
    assert w.tabellen["belege"] == 4


def test_fremde_datei_im_archiv(tmp_path):
    db, archiv = befuelle(tmp_path)
    (archiv / "notiz.txt").write_text("privat", encoding="utf-8")
    with pytest.raises(SicherungError, match="Fremde Datei"):
        erstelle(db, archiv, tmp_path / "s.accounti", SCHLUESSEL)
    assert not (tmp_path / "s.accounti").exists()
    assert not list(tmp_path.glob(".s.accounti.*"))


def baue_sicherung(ziel, eintraege: dict[str, bytes]) -> None:
    """Eine von Hand gebaute, gültig verschlüsselte Sicherung (für Fehlerfälle)."""
    import hashlib
    import io
    import json
    import tarfile

    from accounti.betrieb.verschluesselung import VerschluesselnderSchreiber

    tabellen = {
        name.removeprefix("datenbank/").removesuffix(".jsonl"): {
            "zeilen": inhalt.count(b"\n"),
            "sha256": hashlib.sha256(inhalt).hexdigest(),
        }
        for name, inhalt in eintraege.items()
        if name.startswith("datenbank/")
    }
    manifest = {"format": 1, "tabellen": tabellen, "dateien": {}, "mit_archiv": False}
    eintraege = {**eintraege, "manifest.json": json.dumps(manifest).encode()}
    with open(ziel, "wb") as datei:
        w = VerschluesselnderSchreiber(datei, SCHLUESSEL)
        with tarfile.open(fileobj=w, mode="w|") as tar:
            for name, inhalt in eintraege.items():
                info = tarfile.TarInfo(name)
                info.size = len(inhalt)
                tar.addfile(info, io.BytesIO(inhalt))
        w.close()


def test_unpassende_zeilen_werden_abgelehnt(tmp_path):
    ziel = tmp_path / "hand.sicherung"
    baue_sicherung(ziel, {"datenbank/kontakte.jsonl": b'{"id": "x", "unbekannt": 1}\n'})
    neu = url(tmp_path / "neu.db")
    with pytest.raises(SicherungError, match="lehnt die Sicherung ab"):
        stelle_wieder_her(ziel, neu, None, SCHLUESSEL)
    assert all(z == [] for z in tabelleninhalt(neu).values())


@pytest.mark.parametrize(
    "name",
    [
        "archiv/../../etc/passwd",
        "archiv/ab/cd/../../x",
        "datenbank/../x.jsonl",
        "fremd.txt",
    ],
)
def test_fremde_eintraege_werden_abgelehnt(tmp_path, name):
    ziel = tmp_path / "hand.sicherung"
    baue_sicherung(ziel, {name: b"inhalt"})
    with pytest.raises((ManipuliertError, SicherungError)):
        stelle_wieder_her(
            ziel, url(tmp_path / "neu.db"), tmp_path / "archiv", SCHLUESSEL
        )
    assert not (tmp_path / "archiv").exists()
    assert not (tmp_path.parent / "etc").exists()


@pytest.mark.parametrize(
    "wert",
    [
        None,
        True,
        7,
        0.875,
        "äöü",
        Decimal("12345678.99"),
        date(2026, 10, 20),
        datetime(2026, 10, 20, 9, 30, 1, 123),
        time(23, 59),
        b"\x00\xff",
        uuid4(),
        {"a": [1, {"$": "kein Typ"}]},
        ["opos:lesen"],
    ],
)
def test_typgetreu(wert):
    assert dekodiere(kodiere(wert)) == wert
