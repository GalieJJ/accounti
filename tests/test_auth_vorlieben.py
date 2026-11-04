"""Anzeige-Vorlieben am Benutzer (Spec 10c A87, A88; Plan P1 Schritt 3).

Sprache, Darstellung, Fachansicht, Beträge verbergen und Tastenkürzel gelten auf jedem
Gerät. ``setze_vorlieben`` ändert nur die gesetzten Felder mit einem gezielten
``UPDATE`` (wie zuvor ``setze_sprache``) und schreibt kein Ereignis (Ausnahme A113);
``speichere_benutzer`` schreibt sie bei bestehenden Benutzern nicht zurück (B18).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from accounti.auth.dienst import UNVERAENDERT, Vorlieben, setze_vorlieben
from accounti.auth.fehler import AuthError
from accounti.db.repo_auth import lade_benutzer, lade_benutzer_id, speichere_benutzer
from accounti.db.tabellen_auth import AuthEreignisRow
from accounti.models.auth import Benutzer, Rolle
from tests.auth_hilfe import JETZT, billige_hashes, lege_person_an, systemdatenbank


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def system(tmp_path):
    with systemdatenbank(tmp_path) as s:
        yield s


@pytest.fixture
def jan(system) -> Benutzer:
    p = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    system.commit()
    return p.benutzer


def _vorlieben(b: Benutzer) -> tuple[object, ...]:
    return (
        b.sprache,
        b.darstellung,
        b.fachansicht,
        b.betraege_verbergen,
        b.tastenkuerzel,
    )


def test_standard_fuer_neue_benutzer(system, jan):
    b = lade_benutzer(system, "jan")
    assert b is not None
    assert _vorlieben(b) == (None, "auto", False, False, True)
    assert _vorlieben(Benutzer(name="neu", passwort_hash="x")) == (
        None,
        "auto",
        False,
        False,
        True,
    )


def test_bestehender_benutzer_liest_standard(system):
    """Eine Zeile ohne Angaben (wie nach der Migration): die Server-Standards gelten."""
    system.execute(
        text(
            "INSERT INTO auth_benutzer (id, name, passwort_hash, totp_aktiv, "
            "fehlversuche, cli_fehlversuche, aktiv, angelegt_am) VALUES "
            "(:id, 'alt', 'h', 0, 0, 0, 1, '2026-10-01 09:00:00')"
        ),
        {"id": str(uuid4())},
    )
    system.commit()
    b = lade_benutzer(system, "alt")
    assert b is not None
    assert _vorlieben(b) == (None, "auto", False, False, True)


def test_speichern_ueberschreibt_vorlieben_nicht(system, jan):
    vorher = lade_benutzer(system, "jan")
    assert vorher is not None
    setze_vorlieben(
        system,
        jan.id,
        Vorlieben(sprache="en", darstellung="dunkel", tastenkuerzel=False),
    )
    system.commit()
    # ein vorher geladener Benutzer wird mit neuer Anmeldezeit gespeichert (Anmeldung)
    speichere_benutzer(
        system, vorher.model_copy(update={"letzte_anmeldung_am": JETZT + timedelta(1)})
    )
    system.commit()
    nachher = lade_benutzer_id(system, jan.id)
    assert nachher is not None
    assert nachher.letzte_anmeldung_am == JETZT + timedelta(1)
    assert _vorlieben(nachher) == ("en", "dunkel", False, False, False)


def test_nur_gesetzte_felder_aendern_sich(system, jan):
    setze_vorlieben(
        system, jan.id, Vorlieben(fachansicht=True, betraege_verbergen=True)
    )
    setze_vorlieben(system, jan.id, Vorlieben(darstellung="hell"))
    system.commit()
    b = lade_benutzer_id(system, jan.id)
    assert b is not None
    assert _vorlieben(b) == (None, "hell", True, True, True)
    setze_vorlieben(system, jan.id, Vorlieben())  # nichts gesetzt: nichts ändert sich
    system.commit()
    b = lade_benutzer_id(system, jan.id)
    assert b is not None and _vorlieben(b) == (None, "hell", True, True, True)
    assert Vorlieben().darstellung is UNVERAENDERT


def test_sprache_none_heisst_automatisch(system, jan):
    setze_vorlieben(system, jan.id, Vorlieben(sprache="en"))
    setze_vorlieben(system, jan.id, Vorlieben(sprache=None))
    system.commit()
    b = lade_benutzer_id(system, jan.id)
    assert b is not None and b.sprache is None


@pytest.mark.parametrize(
    "vorlieben",
    [
        Vorlieben(darstellung="grau"),  # type: ignore[arg-type]
        Vorlieben(sprache="fr"),  # type: ignore[arg-type]
        Vorlieben(tastenkuerzel="ja"),  # type: ignore[arg-type]
        Vorlieben(fachansicht=1),  # type: ignore[arg-type]
    ],
)
def test_ungueltige_darstellung_auth_error(system, jan, vorlieben):
    with pytest.raises(AuthError):
        setze_vorlieben(system, jan.id, vorlieben)
    system.rollback()
    b = lade_benutzer_id(system, jan.id)
    assert b is not None and _vorlieben(b) == (None, "auto", False, False, True)


def test_unbekannter_benutzer_auth_error(system, jan):
    with pytest.raises(AuthError, match="unbekannt"):
        setze_vorlieben(system, uuid4(), Vorlieben(darstellung="dunkel"))
    with pytest.raises(AuthError, match="unbekannt"):
        setze_vorlieben(system, uuid4(), Vorlieben())


def test_kein_auth_ereignis(system, jan):
    def anzahl() -> int:
        return system.scalar(select(func.count()).select_from(AuthEreignisRow)) or 0

    vorher = anzahl()
    setze_vorlieben(
        system,
        jan.id,
        Vorlieben(
            sprache="de",
            darstellung="dunkel",
            fachansicht=True,
            betraege_verbergen=True,
            tastenkuerzel=False,
        ),
    )
    system.commit()
    assert anzahl() == vorher
