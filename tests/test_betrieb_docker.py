"""Betriebsdateien statisch geprüft: keine Geheimnisse im Abbild, Ports nur lokal.

``docker compose up`` selbst ist im Plan als ausgeführte Probe dokumentiert
(Akzeptanz 6); hier wird geprüft, dass die Dateien zusichern, was ``docs/betrieb.md``
sagt.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

WURZEL = Path(__file__).resolve().parents[1]


def compose():
    return yaml.safe_load((WURZEL / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_mit_anwendung_datenbank_und_lauf():
    dienste = compose()["services"]
    assert set(dienste) == {"db", "app", "lauf"}
    assert dienste["db"]["image"].startswith("postgres:16")
    assert "ports" not in dienste["db"]  # Datenbank nicht von außen erreichbar
    assert dienste["app"]["command"][0] == "serve"
    assert dienste["lauf"]["command"][:2] == ["betrieb", "lauf"]
    assert dienste["app"]["depends_on"]["db"]["condition"] == "service_healthy"
    for port in dienste["app"]["ports"]:
        assert port.startswith("127.0.0.1:"), port


def test_speichergrenze_fuer_app_und_lauf():
    """Befund A-M2: scrypt braucht 128 MiB je Prüfung — der Container hat eine
    Obergrenze (die Anwendung begrenzt zusätzlich die gleichzeitigen Anmeldungen)."""
    dienste = compose()["services"]
    for name in ("app", "lauf"):
        assert dienste[name].get("mem_limit"), name


def test_geheimnisse_nur_aus_der_umgebung():
    text = (WURZEL / "docker-compose.yml").read_text(encoding="utf-8")
    for zeile in text.splitlines():
        if re.search(
            r"(PASSWORD|SCHLUESSEL|PASSWORT)\s*[:=]", zeile
        ) and not zeile.strip().startswith("#"):
            assert "${" in zeile, zeile
    umgebung = compose()["x-accounti"]["environment"]
    assert umgebung["ACCOUNTI_SCHLUESSEL"].startswith("${ACCOUNTI_SCHLUESSEL:?")


def test_abbild_ohne_geheimnisse_und_nicht_als_root():
    datei = (WURZEL / "Dockerfile").read_text(encoding="utf-8")
    assert "USER accounti" in datei
    assert "HEALTHCHECK" in datei and "/gesund" in datei
    assert not re.search(r"ENV\s+[^\n]*(SCHLUESSEL|PASSWORT|PASSWORD|TOKEN)", datei)
    assert "COPY . " not in datei  # nur ausgewählte Dateien
    ignoriert = (WURZEL / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for muster in (".env", "config/accounti.yaml", "*.db", "archiv/", ".git"):
        assert muster in ignoriert, muster


def test_alembic_liest_accounti_db(tmp_path):
    """alembic upgrade head gegen die Datenbank aus ACCOUNTI_DB (wie im Container)."""
    db = tmp_path / "migriert.db"
    umgebung = {
        **os.environ,
        "ACCOUNTI_DB": f"sqlite:///{db}",
        "PYTHONPATH": str(WURZEL / "src"),
    }
    ergebnis = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(WURZEL / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=tmp_path,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert db.exists()
    assert not (tmp_path / "accounti.db").exists()
