"""Nur anfügen auch gegen rohes SQL — Trigger je Dialekt (Baustein 10c P4, D10).

``nur_anfuegen_sql(tabelle, text, dialekt)`` liefert die Anweisungen, mit denen eine
Tabelle Änderungen und Löschungen ablehnt — für ``after_create`` (der Weg über
``init_db``) und die Migration gleich, wiederholbar:

* **SQLite:** ``BEFORE UPDATE``/``BEFORE DELETE`` mit ``RAISE(ABORT, …)``
  (``CREATE TRIGGER IF NOT EXISTS``), wie bisher ``journal`` und
  ``kontierungsgruende``.
* **PostgreSQL:** die allgemeine Funktion ``accounti_nur_anfuegen()`` (plpgsql,
  ``CREATE OR REPLACE``) mit ``BEFORE UPDATE OR DELETE … FOR EACH ROW`` und
  ``BEFORE TRUNCATE … FOR EACH STATEMENT`` (``DROP TRIGGER IF EXISTS`` vorher). Der
  Text kommt als Trigger-Argument mit; die Meldung lautet „<text> ist unveränderbar“.

Bisher schützt PostgreSQL Journal und Korrekturen nur über ORM-Sperre und Hash-Kette;
sie hier nachzurüsten ist ein eigener Schritt (Plan, Grenzen).
"""

from __future__ import annotations

FUNKTION = "accounti_nur_anfuegen"

PG_FUNKTION = (
    f"CREATE OR REPLACE FUNCTION {FUNKTION}() RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN RAISE EXCEPTION '% ist unveränderbar', TG_ARGV[0]; END $$"
)


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def nur_anfuegen_sql(tabelle: str, text: str, dialekt: str) -> list[str]:
    """Anweisungen für „nur anfügen“ an ``tabelle`` (andere Dialekte: keine)."""
    if dialekt == "sqlite":
        meldung = _literal(f"{text} ist unveränderbar")
        return [
            f"CREATE TRIGGER IF NOT EXISTS {tabelle}_kein_{aktion.lower()} BEFORE "
            f"{aktion} ON {tabelle} BEGIN SELECT RAISE(ABORT, {meldung}); END"
            for aktion in ("UPDATE", "DELETE")
        ]
    if dialekt == "postgresql":
        argument = _literal(text)
        return [
            PG_FUNKTION,
            f"DROP TRIGGER IF EXISTS {tabelle}_nur_anfuegen ON {tabelle}",
            f"CREATE TRIGGER {tabelle}_nur_anfuegen BEFORE UPDATE OR DELETE ON "
            f"{tabelle} FOR EACH ROW EXECUTE FUNCTION {FUNKTION}({argument})",
            f"DROP TRIGGER IF EXISTS {tabelle}_nicht_leeren ON {tabelle}",
            f"CREATE TRIGGER {tabelle}_nicht_leeren BEFORE TRUNCATE ON {tabelle} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {FUNKTION}({argument})",
        ]
    return []


def entferne_sql(tabelle: str, dialekt: str) -> list[str]:
    """Die Trigger von ``nur_anfuegen_sql`` wieder entfernen (Downgrade). Die
    PostgreSQL-Funktion bleibt, solange sie ein anderer Trigger nutzt."""
    if dialekt == "sqlite":
        return [
            f"DROP TRIGGER IF EXISTS {tabelle}_kein_{aktion}"
            for aktion in ("update", "delete")
        ]
    if dialekt == "postgresql":
        return [
            f"DROP TRIGGER IF EXISTS {tabelle}_nur_anfuegen ON {tabelle}",
            f"DROP TRIGGER IF EXISTS {tabelle}_nicht_leeren ON {tabelle}",
        ]
    return []
