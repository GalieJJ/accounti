"""Gerüst: Befehlsgruppen und Tabellenmodule werden automatisch eingebunden."""

import sys
import textwrap

from sqlalchemy import inspect
from typer.testing import CliRunner

import accounti.befehle
import accounti.db
from accounti.db import init_db, registriere_tabellen, session_factory


def test_befehlsgruppe_wird_eingehaengt(tmp_path, monkeypatch):
    paket = tmp_path / "befehle_probe"
    paket.mkdir()
    (paket / "probe.py").write_text(
        textwrap.dedent(
            """
            import typer

            NAME = "probe"
            befehl = typer.Typer(help="Probe")


            @befehl.command("hallo")
            def hallo() -> None:
                print("hallo aus der Probe")
            """
        ),
        encoding="utf-8",
    )
    (paket / "_privat.py").write_text("NAME = 'privat'\n", encoding="utf-8")
    (paket / "ohne_befehl.py").write_text("NAME = 'nichts'\n", encoding="utf-8")
    monkeypatch.setattr(accounti.befehle, "__path__", [str(paket)])
    monkeypatch.setattr(accounti.befehle, "__name__", "befehle_probe")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = accounti.befehle.befehlsmodule()
    assert [m.NAME for m in module] == ["probe"]

    import typer

    app = typer.Typer()
    from accounti.cli import haenge_befehle_ein

    haenge_befehle_ein(app, module)
    r = CliRunner().invoke(app, ["probe", "hallo"])
    assert r.exit_code == 0, r.output
    assert "hallo aus der Probe" in r.output
    sys.modules.pop("befehle_probe.probe", None)


def test_tabellenmodule_werden_registriert(tmp_path, monkeypatch):
    paket = tmp_path / "accounti_db_probe"
    paket.mkdir()
    (paket / "tabellen_probe.py").write_text(
        textwrap.dedent(
            """
            from sqlalchemy import String
            from sqlalchemy.orm import Mapped, mapped_column

            from accounti.db import Base


            class ProbeRow(Base):
                __tablename__ = "probe_erweiterung"
                id: Mapped[str] = mapped_column(String(36), primary_key=True)
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registriere_tabellen(paket_name="accounti_db_probe", pfade=[str(paket)])
    engine, _ = session_factory(f"sqlite:///{tmp_path / 'p.db'}")
    init_db(engine)
    assert "probe_erweiterung" in inspect(engine).get_table_names()
    assert "transaktionen" in inspect(engine).get_table_names()
    engine.dispose()
    accounti.db.Base.metadata.remove(
        accounti.db.Base.metadata.tables["probe_erweiterung"]
    )
    sys.modules.pop("accounti_db_probe.tabellen_probe", None)
