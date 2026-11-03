"""Zwei Formen neuer Seiten: ganze Seite oder nur der Block ``inhalt`` (Spec 10c A115,
AK58; Plan P1 Schritt 4, Befund B19).

Ein Block allein läuft ohne den Code auf oberster Ebene seiner Vorlage — Importe und
``{% set %}`` dort fehlten, ``super()`` fände keinen Elternblock. ``seite(…, teil=…)``
prüft deshalb jede solche Vorlage einmal: oben nur ``extends`` und Blöcke, im Block kein
``super()``; sonst ``RuntimeError`` — auch beim Rendern der ganzen Seite.
"""

from __future__ import annotations

import pytest
from jinja2 import ChoiceLoader, DictLoader, Environment

from accounti.api.vorlagen import UMGEBUNG, pruefe_teilvorlage, rendere_teil

KOPF = '{% extends "basis.html" %}\n'
IMPORT = '{% import "_komponenten.html" as k with context %}'


def umgebung(**vorlagen: str) -> Environment:
    return UMGEBUNG.overlay(
        loader=ChoiceLoader([DictLoader(vorlagen), UMGEBUNG.loader])
    )


@pytest.mark.parametrize(
    "quelle",
    [
        KOPF + IMPORT + "\n{% block inhalt %}{{ k.status('ok', 'x') }}{% endblock %}",
        KOPF + "{% set y = 1 %}\n{% block inhalt %}{{ y }}{% endblock %}",
        KOPF + "Text oben\n{% block inhalt %}x{% endblock %}",
        KOPF + "{% block inhalt %}{{ super() }}x{% endblock %}",
        KOPF + "{% block titel %}x{% endblock %}",  # Block inhalt fehlt
    ],
    ids=["import_oben", "set_oben", "text_oben", "super_im_block", "ohne_block"],
)
def test_teil_verlangt_nur_bloecke_auf_oberster_ebene(quelle):
    env = umgebung(**{"seite.html": quelle})
    with pytest.raises(RuntimeError, match="seite.html"):
        pruefe_teilvorlage(env, "seite.html", "inhalt")


def test_import_im_block_rendert_das_fragment():
    env = umgebung(
        **{
            "seite.html": KOPF
            + "{% block titel %}T{% endblock %}\n{% block inhalt %}\n"
            + IMPORT
            + '{% set y = "Wort" %}{{ k.status("ok", y) }}{% endblock %}\n'
        }
    )
    pruefe_teilvorlage(env, "seite.html", "inhalt")
    html = rendere_teil(env, "seite.html", "inhalt", {"sprache": "de"})
    assert '<span class="status status-ok">' in html and "Wort</span>" in html
    assert "<html" not in html


def test_pruefung_einmal_je_vorlage(monkeypatch):
    env = umgebung(**{"seite.html": KOPF + "{% block inhalt %}x{% endblock %}"})
    pruefe_teilvorlage(env, "seite.html", "inhalt")
    aufrufe = []
    monkeypatch.setattr(env, "parse", lambda *a, **k: aufrufe.append(a))
    pruefe_teilvorlage(env, "seite.html", "inhalt")
    assert aufrufe == []
