"""Katalog ``i18n/en.yaml``: vollständig, ohne Waisen, gleiche Platzhalter, Fachbegriffe
bleiben deutsch (Baustein 10b, Spec 4.5). Neue Texte ohne Eintrag lassen ihn
scheitern."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from accounti.i18n import MONATE, katalog, katalogtexte, platzhalter

QUELLEN = Path(__file__).resolve().parents[1] / "src" / "accounti"
VORLAGEN = QUELLEN / "api" / "vorlagen"
AUFRUFE = {"_", "N_", "Text", "gettext", "ngettext"}
# Begriffe ohne tragfähige Entsprechung — bleiben in der englischen Oberfläche deutsch
FACHBEGRIFFE = (
    "Buchungssatz",
    "BWA",
    "Steuerschlüssel",
    "GoBD",
    "Festschreibung",
    "USt-IdNr.",
    "USt-VA",
    "SKR03",
    "SKR04",
    "DATEV",
    "ELSTER",
    "ZUGFeRD",
    "XRechnung",
)


def texte_aus_vorlagen() -> set[str]:
    from accounti.api.vorlagen import UMGEBUNG

    gefunden: set[str] = set()
    for datei in sorted(VORLAGEN.rglob("*.html")):
        quelle = datei.read_text(encoding="utf-8")
        for _zeile, _funktion, text in UMGEBUNG.extract_translations(quelle):
            teile = text if isinstance(text, tuple) else (text,)
            if teile and isinstance(teile[0], str):
                gefunden.add(teile[0])
    return gefunden


def texte_aus_python() -> set[str]:
    gefunden: set[str] = set()
    for datei in sorted((QUELLEN / "api").rglob("*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call) or not knoten.args:
                continue
            name = getattr(knoten.func, "id", getattr(knoten.func, "attr", None))
            erstes = knoten.args[0]
            if (
                name in AUFRUFE
                and isinstance(erstes, ast.Constant)
                and isinstance(erstes.value, str)
            ):
                gefunden.add(erstes.value)
    return gefunden


def alle_texte() -> set[str]:
    # RECHT_TEXT: die Namen der Rechte stehen auf der 403-Seite (Plan P1, Schritt 11)
    from accounti.models.auth import RECHT_TEXT

    return (
        texte_aus_vorlagen()
        | texte_aus_python()
        | set(MONATE)
        | set(RECHT_TEXT.values())
    )


def test_jeder_text_hat_eine_uebersetzung():
    fehlend = sorted(t for t in alle_texte() if t not in katalog("en"))
    assert fehlend == [], "\n".join(fehlend)


def test_keine_verwaisten_eintraege():
    texte = alle_texte()
    waisen = sorted(t for t in katalog("en") if t not in texte)
    assert waisen == [], "\n".join(waisen)


def test_platzhalter_gleich():
    for msgid, eintrag in katalog("en").items():
        for form, uebersetzung in katalogtexte(eintrag).items():
            assert platzhalter(uebersetzung) == platzhalter(msgid), (msgid, form)


def test_katalogwert_nur_mit_den_tags_seiner_msgid():
    """Nachbesserung 10b-1 Technik N6: ``_()`` behandelt Katalogwerte als Markup
    (Jinja-Newstyle) — eine Übersetzung darf keine Tags mitbringen, die ihre msgid
    nicht hat (sonst käme Markup ungeprüft aus dem Katalog in die Seite)."""
    import re

    tag = re.compile(r"</?\s*([a-zA-Z][\w-]*)[^>]*>")
    for msgid, eintrag in katalog("en").items():
        erlaubt = sorted(tag.findall(msgid))
        for form, uebersetzung in katalogtexte(eintrag).items():
            assert sorted(tag.findall(uebersetzung)) == erlaubt, (msgid, form)
            assert "<script" not in uebersetzung.lower(), msgid


def test_fachbegriffe_bleiben_deutsch():
    for msgid, eintrag in katalog("en").items():
        for begriff in FACHBEGRIFFE:
            if begriff in msgid:
                for uebersetzung in katalogtexte(eintrag).values():
                    assert begriff in uebersetzung, (begriff, msgid, uebersetzung)


@pytest.mark.parametrize(
    ("deutsch", "englisch"),
    [
        ("Soll", "Debit"),
        ("Haben", "Credit"),
        ("Storno", "Reversal"),
        ("Beleg", "Document"),
        ("Einmalcode", "One-time code"),
        ("Offene Posten", "Open items"),
    ],
)
def test_glossar(deutsch, englisch):
    assert katalog("en").get(deutsch) == englisch
