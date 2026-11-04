"""Umbau der Lader auf den Abschnittsleser (Baustein 10c P4, Schritt 4; A41, A47, D25,
AK76, AK78).

Jeder Lader liest über ``einstellungen.lies_abschnitt`` — gleiche Signatur, gleicher
Modelltyp, gleiche Fehlertexte, ohne ``is_file``-Wächter (D25). ``yaml.safe_load``
steht nur noch in der Positivliste (Daten-Dateien), ``lies_yaml`` gibt es nicht mehr.
``inventar.LADER`` nennt je Lader die gelesenen Abschnitte, auch mittelbar; der
dynamische Test zeichnet sie unter einem echten Stand auf.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from accounti.db import init_db, session_factory
from accounti.db.repo_einstellungen import fuege_version_an
from accounti.einstellungen import leser
from accounti.einstellungen.inventar import ABSCHNITTE, LADER
from accounti.einstellungen.leser import DatenbankQuelle, mit_quelle
from accounti.konfiguration import KonfigurationError
from tests.werkzeuge.golden_lader import feste_umgebung

WURZEL = Path(__file__).resolve().parents[1]
SRC = WURZEL / "src"
VORLAGE = WURZEL / "config" / "accounti.example.yaml"
runner = CliRunner()

# Daten-Dateien, keine Konfiguration — je Eintrag ein Grund
POSITIVLISTE = {
    "accounti/einstellungen/leser.py": "der Abschnittsleser selbst (lies_datei, "
    "parse_text)",
    "accounti/abschluss/kontenrahmen.py": "Kontenzuordnung (mitgelieferte bzw. "
    "eigene Datei des Betreibers, Betriebsfeld)",
    "accounti/abschluss/euer.py": "Zeilen der Anlage EÜR (mitgelieferte Daten)",
    "accounti/anlagen/rechtsstand.py": "AfA-Rechtsstand (Daten, Betriebsfeld)",
    "accounti/pruefung/regeln/richtigkeit.py": "Kontenrahmen-Datei der Prüfregeln "
    "(Daten, Betriebsfeld)",
    "accounti/importers/profil.py": "Bankprofile (config/banken.yaml, Daten)",
    "accounti/klassifikation/regeln_loader.py": "Regeldatei der Kontierung (eigene "
    "Datei, kein Abschnitt)",
    "accounti/klassifikation/lernen.py": "Regeldatei der Kontierung (schreibt die "
    "gelernten Regeln zurück)",
    "accounti/i18n/__init__.py": "Sprachkataloge (mitgelieferte Daten)",
}
LADEFUNKTIONEN = {"safe_load", "load", "full_load", "unsafe_load", "load_all"}
BETRIEBSLADER = {
    "accounti.auth.einstellungen.lade_auth",
    "accounti.api.einstellungen.lade_server",
    "accounti.betrieb.gesellschaften.lade_gesellschaften",
}


def _module() -> Iterator[tuple[str, Path, ast.Module]]:
    for datei in sorted((SRC / "accounti").rglob("*.py")):
        relativ = datei.relative_to(SRC).as_posix()
        modul = relativ.removesuffix(".py").removesuffix("/__init__")
        modul = modul.replace("/", ".")
        yield modul, datei, ast.parse(datei.read_text(encoding="utf-8"))


def _funktionen(baum: ast.Module) -> Iterator[tuple[str, ast.AST]]:
    """(Name bzw. ``Klasse.methode``, Knoten) der Funktionen eines Moduls —
    verschachtelte Funktionen zählen zu ihrer äußeren."""
    for knoten in baum.body:
        if isinstance(knoten, ast.FunctionDef | ast.AsyncFunctionDef):
            yield knoten.name, knoten
        elif isinstance(knoten, ast.ClassDef):
            for unter in knoten.body:
                if isinstance(unter, ast.FunctionDef | ast.AsyncFunctionDef):
                    yield f"{knoten.name}.{unter.name}", unter


def _ruft(knoten: ast.AST, name: str) -> bool:
    for k in ast.walk(knoten):
        if isinstance(k, ast.Call):
            ziel = k.func
            if (isinstance(ziel, ast.Name) and ziel.id == name) or (
                isinstance(ziel, ast.Attribute) and ziel.attr == name
            ):
                return True
    return False


def _definition(punktname: str) -> ast.AST:
    for modul, _, baum in _module():
        for name, knoten in _funktionen(baum):
            if f"{modul}.{name}" == punktname:
                return knoten
    raise AssertionError(f"{punktname} nicht gefunden")


def objekt(punktname: str) -> Any:
    """Punktname auflösen — auch eine Methode (``modul.Klasse.methode``)."""
    teile = punktname.split(".")
    for i in range(len(teile) - 1, 0, -1):
        try:
            ziel: Any = importlib.import_module(".".join(teile[:i]))
        except ModuleNotFoundError:
            continue
        for teil in teile[i:]:
            ziel = getattr(ziel, teil)
        return ziel
    raise AssertionError(punktname)


# --- Statisch ---------------------------------------------------------------------


def test_safe_load_nur_in_der_positivliste():
    """A47: Nur die Positivliste parst YAML — jede Konfiguration geht über den
    Abschnittsleser (Aufrufe ``yaml.safe_load|load|…`` und ``from yaml import …``)."""
    funde = set()
    for _, datei, baum in _module():
        relativ = datei.relative_to(SRC).as_posix()
        for k in ast.walk(baum):
            if (
                isinstance(k, ast.Call)
                and isinstance(k.func, ast.Attribute)
                and k.func.attr in LADEFUNKTIONEN
                and isinstance(k.func.value, ast.Name)
                and k.func.value.id == "yaml"
            ) or (
                isinstance(k, ast.ImportFrom)
                and k.module == "yaml"
                and any(a.name in LADEFUNKTIONEN for a in k.names)
            ):
                funde.add(relativ)
    assert funde <= set(POSITIVLISTE), sorted(funde - set(POSITIVLISTE))
    assert all(grund.strip() for grund in POSITIVLISTE.values())


def test_kein_lies_yaml_mehr():
    funde = []
    for modul, _, baum in _module():
        for k in ast.walk(baum):
            if (isinstance(k, ast.FunctionDef) and k.name == "lies_yaml") or (
                isinstance(k, ast.Name | ast.Attribute)
                and getattr(k, "id", getattr(k, "attr", None)) == "lies_yaml"
            ):
                funde.append(modul)
    assert funde == []


def test_jeder_lader_ist_registriert():
    """Jede Funktion, die ``lies_abschnitt`` aufruft, steht in ``inventar.LADER``."""
    rufer = {
        f"{modul}.{name}"
        for modul, _, baum in _module()
        if modul != "accounti.einstellungen.leser"
        for name, knoten in _funktionen(baum)
        if _ruft(knoten, "lies_abschnitt")
    }
    assert rufer == set(LADER)
    for lader, abschnitte in LADER.items():
        assert callable(objekt(lader)), lader
        assert abschnitte <= set(ABSCHNITTE), lader


def test_kein_is_file_waechter_mehr():
    """D25: Ein Lader eines Datenbank-Abschnitts fragt nicht mehr, ob die Datei da ist
    — sonst gälten ohne Datei die Versionen nicht (Betriebslader ausgenommen)."""
    funde = [
        lader
        for lader in sorted(set(LADER) - BETRIEBSLADER)
        if _ruft(_definition(lader), "is_file") or _ruft(_definition(lader), "exists")
    ]
    assert funde == []


# --- Dynamisch: gelesene Abschnitte -------------------------------------------------


def _doku_abschnitte(pfad: Path) -> Any:
    from accounti.pruefung.verfahrensdoku import _Doku

    d = _Doku(None, pfad, None)  # type: ignore[arg-type]
    return d.abschnitt("mandant"), d.abschnitt("belegkanaele")


# Aufruf je Lader (Signaturen mit mehr als dem Pfad)
AUFRUF: dict[str, Callable[[Path], Any]] = {
    "accounti.export.datev_stammdaten.lade_datev_mandant": lambda p: objekt(
        "accounti.export.datev_stammdaten.lade_datev_mandant"
    )(p, date(2026, 3, 31)),
    "accounti.pruefung.verfahrensdoku._Doku.abschnitt": _doku_abschnitte,
}


@contextmanager
def _aufzeichnung() -> Iterator[set[str]]:
    gelesen: set[str] = set()
    original = leser._wirksam

    def aufzeichnend(pfad: Any, name: str) -> Any:
        gelesen.add(name)
        return original(pfad, name)

    leser._wirksam = aufzeichnend  # type: ignore[assignment]
    try:
        yield gelesen
    finally:
        leser._wirksam = original  # type: ignore[assignment]


@pytest.mark.parametrize("lader", sorted(LADER))
def test_lader_lesen_was_registriert_ist(lader, tmp_path):
    """N1: Was ein Lader liest (auch über andere Lader), steht in ``LADER`` — unter
    einem gebundenen Stand mit der Vorlage."""
    aufruf = AUFRUF.get(lader) or objekt(lader)
    url = _db(tmp_path)
    with (
        feste_umgebung(),
        mit_quelle(DatenbankQuelle(url)),
        _aufzeichnung() as g,
        contextlib.suppress(KonfigurationError),  # gelesen ist trotzdem
    ):
        aufruf(VORLAGE)
    assert g == LADER[lader]


# --- Datenbank-Werte wirken ---------------------------------------------------------


def _db(tmp_path: Path, name: str = "a.db") -> str:
    url = f"sqlite:///{tmp_path / name}"
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    return url


def version(url: str, abschnitt: str, daten: dict[str, Any]) -> None:
    engine, fabrik = session_factory(url)
    try:
        with fabrik() as s:
            fuege_version_an(
                s, abschnitt, daten, person="erika", grund="Probe", quelle="cli"
            )
            s.commit()
    finally:
        engine.dispose()


MANDANT = {
    "name": "Datenbank GmbH",
    "anschrift": {"strasse": "Weg 1", "plz": "20095", "ort": "Hamburg", "land": "AT"},
    "ust_id": "DE123456789",
    "email": "rechnung@datenbank.example",
    "kontakt": {"name": "Erika", "telefon": "040 1", "email": "e@datenbank.example"},
    "bank": {"iban": "DE89370400440532013000"},
    "oss": True,
    "sachkonten_laenge": 6,
    "rechnung": {"zahlungsziel_tage": 21},
}

# Lader → (Abschnitt, Daten der Version, gelesener Wert, erwarteter Wert)
WIRKUNG: dict[str, tuple[str, dict[str, Any], Callable[[Any], Any], Any]] = {
    "accounti.konfiguration.lade_firma": (
        "mandant",
        MANDANT,
        lambda f: (f.name, f.zahlungsziel_tage),
        ("Datenbank GmbH", 21),
    ),
    "accounti.konfiguration.lade_buchhaltung": (
        "buchhaltung",
        {"bank_konto": "1800"},
        lambda b: b.bank_konto,
        "1800",
    ),
    "accounti.konfiguration.lade_ustid_pruefung": (
        "ustid_pruefung",
        {"max_alter_tage": 7},
        lambda u: u.max_alter_tage,
        7,
    ),
    "accounti.konfiguration.lade_eigene_firma": (
        "mandant",
        MANDANT,
        lambda p: p.name,
        "Datenbank GmbH",
    ),
    "accounti.abschluss.konfiguration.lade_wirtschaftsjahr_beginn": (
        "datev",
        {"wirtschaftsjahr_beginn": "2025-07-01"},
        lambda d: (d.month, d.day),
        (7, 1),
    ),
    "accounti.abschluss.konfiguration.lade_abschluss": (
        "abschluss",
        {"rap_verzicht_bis_gwg": True},
        lambda a: a.rap_verzicht_bis_gwg,
        True,
    ),
    "accounti.abschluss.konfiguration.gewinnermittlung_angegeben": (
        "abschluss",
        {"gewinnermittlung": "bilanz"},
        lambda g: g,
        "bilanz",
    ),
    "accounti.abschluss.konfiguration.lade_kasse": (
        "kasse",
        {"konto": "1010"},
        lambda k: k.konto,
        "1010",
    ),
    "accounti.aufgaben.einstellungen.lade_aufgaben_einstellungen": (
        "aufgaben",
        {"ich": "erika"},
        lambda a: a.ich,
        "erika",
    ),
    "accounti.erechnung.versand.lade_versand": (
        "versand",
        {"absender": "DB <r@datenbank.example>", "smtp": {"host": "smtp.db.example"}},
        lambda v: (v.absender, v.smtp.host),
        ("DB <r@datenbank.example>", "smtp.db.example"),
    ),
    "accounti.mahnwesen.konfiguration.lade_mahnwesen": (
        "mahnwesen",
        {"karenztage": 9},
        lambda m: m.karenztage,
        9,
    ),
    "accounti.pruefung.einstellungen.lade_pruefung": (
        "pruefung",
        {"eigene_namen": ["Datenbank"]},
        lambda p: p.eigene_namen,
        ["Datenbank"],
    ),
    "accounti.belege.kanaele.einstellungen.lade_belegkanaele": (
        "belegkanaele",
        {"max_groesse_mb": 3},
        lambda k: k.max_groesse_mb,
        3,
    ),
    "accounti.anlagen.konfiguration.lade_anlagen": (
        "anlagen",
        {"kfz_konten": ["0520"]},
        lambda a: a.kfz_konten,
        ["0520"],
    ),
    "accounti.elster.konfiguration.lade_elster": (
        "elster",
        {"bundesland": "BY", "voranmeldungszeitraum": "quartal"},
        lambda e: e.model_dump(by_alias=True)["voranmeldungszeitraum"],
        "quartal",
    ),
    "accounti.elster.konfiguration.lade_elster_konten": (
        "elster",
        {"konten_ohne_kennziffer": ["1234"]},
        lambda e: "1234" in e.konten_ohne_kennziffer,
        True,
    ),
    "accounti.elster.konfiguration.lade_oss": (
        "mandant",
        MANDANT,
        lambda o: o,
        True,
    ),
    "accounti.elster.konfiguration.lade_mandant": (
        "mandant",
        MANDANT,
        lambda m: m["name"],
        "Datenbank GmbH",
    ),
    "accounti.integrationen.einstellungen.lade_integrationen": (
        "integrationen",
        {"geldtransit_konto": "1361"},
        lambda i: i.geldtransit_konto,
        "1361",
    ),
    "accounti.integrationen.einstellungen.lade_steuerangaben": (
        "mandant",
        MANDANT,
        lambda s: s,
        (True, "AT"),
    ),
    "accounti.bank.einstellungen.lade_bank_einstellungen": (
        "bank",
        {"kreditkarte": {"geldtransit_konto": "1361"}},
        lambda b: b.kreditkarte.geldtransit_konto,
        "1361",
    ),
    "accounti.zahlung.konfiguration.lade_zahlung": (
        "zahlung",
        {"skonto_ziehen": False},
        lambda z: (z.skonto_ziehen, z.auftraggeber.name),
        (False, "Meine Firma GmbH"),
    ),
    "accounti.export.datev_stammdaten.sachkontenlaenge": (
        "mandant",
        MANDANT,
        lambda n: n,
        6,
    ),
    "accounti.export.datev_stammdaten.lade_datev_mandant": (
        "datev",
        {"berater_nummer": "4711", "mandanten_nummer": "42"},
        lambda m: (m.berater, m.mandant, m.sachkontenlaenge),
        (4711, 42, 4),
    ),
    "accounti.befehle.gesellschaft._wirtschaftsjahr": (
        "datev",
        {"wirtschaftsjahr_beginn": "2025-07-01"},
        lambda t: "07-01" in t,
        True,
    ),
    "accounti.pruefung.verfahrensdoku._Doku.abschnitt": (
        "mandant",
        MANDANT,
        lambda a: a[0]["name"],
        "Datenbank GmbH",
    ),
}


def test_wirkung_kennt_jeden_lader():
    assert set(WIRKUNG) | BETRIEBSLADER == set(LADER)


@pytest.mark.parametrize("lader", sorted(WIRKUNG))
def test_datenbankwert_wirkt(lader, tmp_path):
    """A41: Je Lader wirkt eine Version gegen die Vorlage als Datei."""
    abschnitt, daten, wert, erwartet = WIRKUNG[lader]
    aufruf = AUFRUF.get(lader) or objekt(lader)
    url = _db(tmp_path)
    version(url, abschnitt, daten)
    with feste_umgebung(), mit_quelle(DatenbankQuelle(url), VORLAGE):
        assert wert(aufruf(VORLAGE)) == erwartet


@pytest.mark.parametrize("lader", sorted(BETRIEBSLADER))
def test_betriebslader_lesen_nie_die_datenbank(lader, tmp_path):
    abschnitt = {"lade_auth": "auth", "lade_server": "server"}.get(
        lader.rsplit(".", 1)[-1], "gesellschaften"
    )
    url = _db(tmp_path)
    version(url, abschnitt, {"x": 1})
    with feste_umgebung():
        ohne = objekt(lader)(VORLAGE)
        with mit_quelle(DatenbankQuelle(url), VORLAGE):
            assert objekt(lader)(VORLAGE) == ohne


@pytest.mark.parametrize("lader", ["lade_firma", "lade_buchhaltung", "lade_versand"])
def test_ohne_datei_gelten_versionen(lader, tmp_path):
    """H3/D25: Fehlt die Datei, gelten die Versionen; ohne Version die bisherige
    Meldung bzw. die Standards."""
    from accounti.erechnung.versand import lade_versand
    from accounti.konfiguration import Buchhaltung, lade_buchhaltung, lade_firma

    fehlt = tmp_path / "fehlt.yaml"
    url = _db(tmp_path)
    leer = _db(tmp_path, "leer.db")
    if lader == "lade_firma":
        with (
            mit_quelle(DatenbankQuelle(leer)),
            pytest.raises(KonfigurationError, match="fehlt — Vorlage"),
        ):
            lade_firma(fehlt)
        version(url, "mandant", MANDANT)
        with mit_quelle(DatenbankQuelle(url)):
            assert lade_firma(fehlt).name == "Datenbank GmbH"
    elif lader == "lade_buchhaltung":
        with mit_quelle(DatenbankQuelle(leer)):
            assert lade_buchhaltung(fehlt) == Buchhaltung()
        version(url, "buchhaltung", {"kontenrahmen": "SKR04"})
        with mit_quelle(DatenbankQuelle(url)):
            assert lade_buchhaltung(fehlt).kontenrahmen == "SKR04"
    else:
        with (
            mit_quelle(DatenbankQuelle(leer)),
            pytest.raises(KonfigurationError, match="fehlt — Vorlage"),
        ):
            lade_versand(fehlt)
        version(url, "versand", {"absender": "a@b.example", "smtp": {"host": "h"}})
        with mit_quelle(DatenbankQuelle(url)):
            assert lade_versand(fehlt).smtp.host == "h"


def test_umgebung_schlaegt_alles_im_lader(tmp_path, monkeypatch):
    """AK76: ``${VAR}`` der Datei gilt auch, wenn der Abschnitt eine Version hat."""
    from accounti.erechnung.versand import lade_versand

    monkeypatch.setenv("VERSAND_ABSENDER", "Umgebung <u@umgebung.example>")
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        "versand:\n  absender: ${VERSAND_ABSENDER}\n  smtp:\n    host: datei\n",
        encoding="utf-8",
    )
    url = _db(tmp_path)
    version(url, "versand", {"absender": "DB <d@db.example>", "smtp": {"host": "db"}})
    with mit_quelle(DatenbankQuelle(url)):
        versand = lade_versand(pfad)
    assert versand.absender == "Umgebung <u@umgebung.example>"
    assert versand.smtp.host == "db"


def test_platzhalter_der_datenbank_wird_nie_aufgeloest(tmp_path, monkeypatch):
    """H1: Ein ``${…}`` in einer Version (nur über das Repository bzw. rohes SQL
    möglich) wird nie eingesetzt — weder im Betreff noch in Connector-Kopfzeilen."""
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.erechnung.versand import STANDARD_TEXT, lade_versand

    monkeypatch.setenv("GEHEIM", "streng-geheim")
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text("mandant:\n  name: X\n", encoding="utf-8")
    url = _db(tmp_path)
    version(
        url,
        "versand",
        {
            "absender": "a@b.example",
            "betreff": "x ${GEHEIM}",
            "text": "${GEHEIM}",
            "smtp": {"host": "h", "passwort": "${GEHEIM}"},
        },
    )
    version(
        url,
        "belegkanaele",
        {
            "connectoren": [
                {
                    "name": "portal",
                    "typ": "json",
                    "basis_url": "https://portal.example",
                    "kopfzeilen": {"Authorization": "Bearer ${GEHEIM}"},
                    "liste": {"pfad": "/belege"},
                    "datei": {"pfad": "/belege/{id}"},
                }
            ]
        },
    )
    with mit_quelle(DatenbankQuelle(url)):
        versand = lade_versand(pfad)
        kanaele = lade_belegkanaele(pfad)
    assert versand.betreff == "Rechnung {nummer} von {firma}"
    assert versand.text == STANDARD_TEXT
    assert versand.smtp.passwort is None
    assert "streng-geheim" not in json.dumps(versand.model_dump(mode="json"))
    assert "streng-geheim" not in json.dumps(kanaele.model_dump(mode="json"))
    (connector,) = kanaele.connectoren
    assert "Authorization" not in (connector.einstellungen().get("kopfzeilen") or {})


# --- CLI und Gesellschaften ---------------------------------------------------------


@pytest.fixture
def _cli_umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def test_cli_wirkt_mit_datenbankwert(tmp_path, _cli_umgebung):
    """``fristen --jahr 2027`` nimmt den Voranmeldungszeitraum der Version, ``rechnung
    ausstellen`` das Zahlungsziel der Version, ``verfahrensdoku`` den Namen."""
    from accounti.cli import app
    from accounti.db.repository import lade_ausgangsrechnungen

    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(VORLAGE.read_text(encoding="utf-8"), encoding="utf-8")
    url = _db(tmp_path)
    version(url, "elster", {"bundesland": "BY", "voranmeldungszeitraum": "quartal"})
    version(url, "mandant", {**MANDANT, "anschrift": {**MANDANT["anschrift"]}})
    r = runner.invoke(
        app,
        ["fristen", "--jahr", "2027", "--db", url, "--config", str(konfig)],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code == 0, r.output
    assert "2027-Q1" in r.output and "2027-01" not in r.output
    r = runner.invoke(
        app,
        [
            "rechnung", "neu", "--db", url, "--name", "Kunde GmbH", "--strasse",
            "Kehrwieder 1", "--plz", "20457", "--ort", "Hamburg", "--email",
            "ap@kunde.example", "--leistungsdatum", "2026-09-01",
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    rid = r.output.split("Entwurf ")[1].split()[0]
    r = runner.invoke(
        app,
        [
            "rechnung", "position", rid, "--db", url, "--text", "Montage", "--preis",
            "100",
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app,
        [
            "rechnung", "ausstellen", rid, "--db", url, "--archiv",
            str(tmp_path / "archiv"), "--config", str(konfig), "--ausgabe",
            str(tmp_path / "out"), "--datum", "2026-09-03", "--ohne-formale-pruefung",
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    engine, fabrik = session_factory(url)
    try:
        with fabrik() as s:
            (rechnung,) = lade_ausgangsrechnungen(s)
    finally:
        engine.dispose()
    assert rechnung.zahlungsziel == date(2026, 9, 24)  # 21 Tage aus der Version
    doku = tmp_path / "doku.md"
    r = runner.invoke(
        app,
        [
            "verfahrensdoku",
            "--db",
            url,
            "--config",
            str(konfig),
            "--ausgabe",
            str(doku),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "Verfahrensdokumentation — Datenbank GmbH" in doku.read_text("utf-8")


def test_andere_gesellschaft_eigene_werte(tmp_path, _cli_umgebung, monkeypatch):
    """AK78: Jede Gesellschaft sieht die Versionen ihrer eigenen Datenbank."""
    from accounti.cli import app
    from tests.gesellschaft_hilfe import zwei_gesellschaften

    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    for kuerzel in ("a", "b"):
        with u.config[kuerzel].open("a", encoding="utf-8") as datei:
            datei.write("elster:\n  bundesland: BY\n  voranmeldungszeitraum: monat\n")
    quartal = {"bundesland": "BY", "voranmeldungszeitraum": "quartal"}
    version(u.db["b"], "elster", quartal)
    ausgaben = {}
    for kuerzel in ("a", "b"):
        r = runner.invoke(
            app, ["-g", kuerzel, "fristen", "--jahr", "2027"], env={"COLUMNS": "200"}
        )
        assert r.exit_code == 0, r.output
        ausgaben[kuerzel] = r.output
    assert "2027-Q1" in ausgaben["b"] and "2027-01" not in ausgaben["b"]
    assert "2027-01" in ausgaben["a"]
