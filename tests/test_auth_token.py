"""API-Token: Klartext einmal, gespeichert nur der Hash, Rechte, Ablauf, Widerruf."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from accounti.auth.token import PRAEFIX, lege_api_token_an, pruefe_api_token
from accounti.db.repo_auth import lade_api_tokens, lade_ereignisse, widerrufe_api_token
from accounti.models.auth import TokenRecht
from tests.auth_hilfe import JETZT, systemdatenbank


@pytest.fixture
def system(tmp_path):
    with systemdatenbank(tmp_path) as s:
        yield s


def test_anlegen_und_pruefen(system):
    klartext = lege_api_token_an(
        system,
        "erp",
        "standard",
        [TokenRecht.OPOS_LESEN],
        "jan",
        jetzt=JETZT,
    )
    system.commit()
    assert klartext.startswith(PRAEFIX)
    assert len(klartext) > len(PRAEFIX) + 40
    # in der Datenbank steht der Klartext nirgends
    zeilen = system.execute(text("SELECT * FROM api_tokens")).all()
    assert all(klartext not in str(z) for z in zeilen)
    token = pruefe_api_token(system, klartext, JETZT)
    assert token is not None
    assert token.rechte == [TokenRecht.OPOS_LESEN]
    assert token.gesellschaft == "standard"
    assert lade_api_tokens(system)[0].zuletzt_genutzt_am == JETZT
    assert [e.art for e in lade_ereignisse(system)] == ["token_angelegt"]


def test_falsch_abgelaufen_widerrufen(system):
    klartext = lege_api_token_an(
        system,
        "erp",
        "standard",
        [TokenRecht.OPOS_LESEN],
        "jan",
        gueltig_bis=date(2026, 10, 31),
        jetzt=JETZT,
    )
    assert pruefe_api_token(system, klartext + "x", JETZT) is None
    assert pruefe_api_token(system, "", JETZT) is None
    assert pruefe_api_token(system, "x" * 500, JETZT) is None
    assert (
        pruefe_api_token(system, klartext, datetime(2026, 10, 31, 23, 59)) is not None
    )
    assert pruefe_api_token(system, klartext, datetime(2026, 11, 1)) is None
    widerrufe_api_token(system, "erp", JETZT)
    assert pruefe_api_token(system, klartext, JETZT) is None


def test_eingaben_werden_geprueft(system):
    with pytest.raises(ValueError, match="Rechte"):
        lege_api_token_an(system, "erp", "standard", [], "jan", jetzt=JETZT)
    with pytest.raises(ValueError, match="Name"):
        lege_api_token_an(
            system, "mit leerzeichen", "standard", [TokenRecht.OPOS_LESEN], "jan"
        )
    with pytest.raises(ValueError, match="Vergangenheit"):
        lege_api_token_an(
            system,
            "erp",
            "standard",
            [TokenRecht.OPOS_LESEN],
            "jan",
            gueltig_bis=JETZT.date() - timedelta(days=1),
            jetzt=JETZT,
        )
