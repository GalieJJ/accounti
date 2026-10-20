"""Web-App mit zwei Gesellschaften, Benutzern und steuerbarer Uhr — für API-Tests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from accounti.api.app import erstelle_app
from accounti.api.dienste import Dienste
from accounti.api.einstellungen import ServerEinstellungen
from accounti.auth.dienst import fuege_rolle_hinzu
from accounti.auth.einstellungen import AuthEinstellungen
from accounti.auth.token import lege_api_token_an
from accounti.betrieb.gesellschaften import lade_gesellschaften
from accounti.db import session_factory
from accounti.models.auth import Rolle, TokenRecht
from tests.auth_hilfe import PASSWORT, SCHLUESSEL, Person, lege_person_an
from tests.gesellschaft_hilfe import Umgebung, zwei_gesellschaften

BASIS = "https://accounti.test"


class Uhr:
    """Steuerbare Uhr: TOTP-Codes, Sitzungsdauer und Sperren laufen danach."""

    def __init__(self, jetzt: datetime) -> None:
        self.jetzt = jetzt

    def __call__(self) -> datetime:
        return self.jetzt

    def weiter(self, sekunden: float = 30) -> None:
        self.jetzt += timedelta(seconds=sekunden)


@dataclass
class Webwelt:
    umgebung: Umgebung
    dienste: Dienste
    uhr: Uhr
    personen: dict[str, Person] = field(default_factory=dict)

    def client(self) -> TestClient:
        return TestClient(erstelle_app(self.dienste), base_url=BASIS)

    def system(self):  # noqa: ANN201 - Kontextmanager der Systemdatenbank
        return self.dienste.system()

    def person(
        self, name: str, *rollen: Rolle, gesellschaft: str = "a", mit_2fa: bool = True
    ) -> Person:
        with self.dienste.system() as s:
            p = lege_person_an(
                s,
                name,
                *rollen,
                gesellschaft=gesellschaft,
                mit_2fa=mit_2fa,
                jetzt=self.uhr.jetzt,
            )
        self.personen[name] = p
        return p

    def rolle(self, name: str, gesellschaft: str, rolle: Rolle) -> None:
        with self.dienste.system() as s:
            fuege_rolle_hinzu(
                s,
                self.personen[name].benutzer,
                gesellschaft,
                rolle,
                self.uhr.jetzt,
                "t",
            )
            s.commit()

    def token(self, gesellschaft: str, *rechte: TokenRecht, name: str = "erp") -> str:
        with self.dienste.system() as s:
            klartext = lege_api_token_an(
                s, name, gesellschaft, rechte, "test", jetzt=self.uhr.jetzt
            )
            s.commit()
        return klartext

    def code(self, name: str) -> str:
        return self.personen[name].code(self.uhr.jetzt)

    def anmelden(self, client: TestClient, name: str, code: str | None = None):  # noqa: ANN201
        """Anmelden mit Passwort und aktuellem Code; danach rückt die Uhr 30 s vor."""
        einmalcode = code if code is not None else self.code(name)
        antwort = melde_an(client, name, PASSWORT, einmalcode)
        self.uhr.weiter(30)
        return antwort

    def angemeldet(self, name: str) -> TestClient:
        client = self.client()
        antwort = self.anmelden(client, name)
        assert antwort.status_code == 303, antwort.text
        return client


def formularwert(html: str, name: str) -> str:
    treffer = re.search(rf'name="{name}" value="([^"]*)"', html)
    assert treffer, f"Feld {name} fehlt"
    return treffer.group(1)


def melde_an(
    client: TestClient, benutzer: str, passwort: str, einmalcode: str, weiter: str = "/"
):  # noqa: ANN201
    seite = client.get("/anmelden")
    anmeldung = formularwert(seite.text, "anmeldung")
    return client.post(
        "/anmelden",
        data={
            "anmeldung": anmeldung,
            "weiter": weiter,
            "benutzer": benutzer,
            "passwort": passwort,
            "einmalcode": einmalcode,
        },
        follow_redirects=False,
    )


def csrf(client: TestClient, pfad: str = "/") -> str:
    return formularwert(client.get(pfad).text, "csrf")


def webwelt(tmp_path: Path, uhr: Uhr | None = None, **auth: object) -> Webwelt:
    u = zwei_gesellschaften(tmp_path)
    registry = lade_gesellschaften(u.registry)
    uhr = uhr or Uhr(datetime(2026, 10, 20, 9, 0))
    dienste = Dienste(
        systemdatenbank=u.system,
        gesellschaften={g.kuerzel: g for g in registry.alle()},
        auth=AuthEinstellungen.model_validate(auth),
        server=ServerEinstellungen(),
        schluessel=lambda: SCHLUESSEL,
        uhr=uhr,
    )
    return Webwelt(u, dienste, uhr)


def zaehle(url: str, sql: str) -> int:
    from sqlalchemy import text

    engine, fabrik = session_factory(url)
    with fabrik() as s:
        wert = s.execute(text(sql)).scalar() or 0
    engine.dispose()
    return int(wert)
