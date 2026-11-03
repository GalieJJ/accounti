"""Token und Grundstile aus ``statisch/accounti.css`` (Spec 10c A89–A91, A100, A103;
Plan P1 Schritt 1 und L1–L3).

Die Farben stehen in zwei Tokenblöcken (hell, dunkel) und ein zweites Mal unter
``prefers-color-scheme: dark`` für ``data-theme="auto"``; die Werte sind die der
freigegebenen Design-Leinwand. Die Kontraste rechnet der Test aus der Datei nach.
"""

from __future__ import annotations

import re

import pytest

from tests.design_hilfe import (
    AUTO,
    CSS,
    DUNKEL,
    HELL,
    PRUEFEN_CSS,
    css,
    kontrast,
    leinwand_token,
    medienregeln,
    mische,
    selektoren,
    stilregeln,
    token,
)

T = token()
MODI = {"hell": T.hell, "dunkel": T.dunkel}

# Leinwand → accounti.css: die Kennfarben heißen in der Leinwand nach den Beispielen
UMBENANNT = {"--marke-gd": "--marke-1", "--marke-ku": "--marke-3"}
# Token der Leinwand, die P1 nicht übernimmt (mit Grund)
NICHT_UEBERNOMMEN = {
    "--papier": "Vorschaubild eines paperless-Dokuments; nur in den noch nicht "
    "freigegebenen Zeichenflächen Belege-paperless und Handy-Belege (Nachtrag P8 ff.)",
}
# Token von P1, die die Leinwand nicht kennt (mit Grund)
NICHT_IN_DER_LEINWAND = {
    "--schleier": "Hover über Knöpfen und Einträgen (L1, L7 Nr. 22)",
    "--marke-6": "sechste Kennfarbe (A5), Oliv aus Fassung 3",
    "--beleg-hintergrund": "Rahmen der Belegvorschau, weiß in beiden Modi",
}

FARBEN = [
    "--grund",
    "--flaeche",
    "--flaeche-2",
    "--text",
    "--text-2",
    "--linie",
    "--linie-stark",
    "--akzent",
    "--akzent-text",
    "--akzent-flaeche",
    "--fokus",
    "--ok",
    "--ok-flaeche",
    "--warn",
    "--warn-flaeche",
    "--fehler",
    "--fehler-flaeche",
    "--fehler-text",
    "--info",
    "--info-flaeche",
    "--schatten",
    "--schleier",
    "--beleg-hintergrund",
] + [f"--marke-{n}" for n in range(1, 7)]

FLAECHEN = ("--grund", "--flaeche", "--flaeche-2")
STATUS = ("ok", "warn", "fehler", "info")


def _farbe(modus: dict[str, str], ausdruck: str) -> str:
    """``--token`` oder ``schleier:--token`` (der Hover-Schleier über der Fläche)."""
    if ausdruck.startswith("schleier:"):
        return mische(modus["--schleier"], modus[ausdruck.removeprefix("schleier:")])
    return modus[ausdruck]


def paare() -> list[tuple[str, str, float]]:
    """(Vordergrund, Hintergrund, Mindestkontrast) nach A89, AK3 und L1."""
    liste: list[tuple[str, str, float]] = []
    for text in ("--text", "--text-2"):
        for flaeche in (*FLAECHEN, "--akzent-flaeche"):
            liste.append((text, flaeche, 4.5))
        for art in STATUS:
            liste.append((text, f"--{art}-flaeche", 4.5))
    for flaeche in (*FLAECHEN, "--akzent-flaeche"):
        liste.append(("--akzent", flaeche, 4.5))  # Links, aktiver Eintrag
    liste.append(("--akzent-text", "--akzent", 4.5))
    for art in STATUS:
        liste.append((f"--{art}", f"--{art}-flaeche", 4.5))
        liste.append((f"--{art}", "--flaeche", 4.5))
    for nicht_text in (
        "--linie-stark",
        "--fokus",
        *(f"--marke-{n}" for n in range(1, 7)),
    ):
        for flaeche in FLAECHEN:
            liste.append((nicht_text, flaeche, 3.0))
    # Fassung 4: Gefahr-Knopf, Kürzel auf der Kennfarbe, gewählte Zeile, Hover
    liste.append(("--fehler-text", "--fehler", 4.5))
    liste += [("--fehler", "--flaeche", 3.0), ("--fehler", "--grund", 3.0)]
    liste += [("--flaeche", f"--marke-{n}", 4.5) for n in range(1, 7)]
    liste += [(f"--{a}", "--akzent-flaeche", 4.5) for a in ("ok", "warn", "fehler")]
    liste += [
        ("--akzent-text", "schleier:--akzent", 4.5),  # primärer Knopf
        ("--fehler-text", "schleier:--fehler", 4.5),  # gefährlicher Knopf
        ("--text", "schleier:--flaeche", 4.5),  # sekundärer Knopf
        ("--akzent", "schleier:--flaeche", 4.5),  # stiller Knopf auf der Fläche
        ("--akzent", "schleier:--grund", 4.5),  # Navigationseintrag
        ("--akzent", "schleier:--akzent-flaeche", 4.5),  # aktiver Eintrag
    ]
    return liste


# Werte aus L1 (hell, dunkel), auf zwei Stellen — sie halten die Rechnung des Plans fest
ERWARTET = {
    ("--text", "--flaeche"): (16.56, 14.03),
    ("--text-2", "--flaeche"): (6.68, 7.55),
    ("--text-2", "--akzent-flaeche"): (5.65, 6.16),
    ("--linie-stark", "--flaeche-2"): (3.41, 3.36),
    ("--akzent", "--flaeche"): (7.63, 8.62),
    ("--akzent-text", "--akzent"): (7.63, 9.02),
    ("--fokus", "--flaeche"): (4.72, 9.58),
    ("--fokus", "--grund"): (4.29, 10.45),
    ("--fehler-text", "--fehler"): (7.15, 8.86),
    ("--flaeche", "--marke-1"): (6.86, 7.40),
    ("--flaeche", "--marke-3"): (4.99, 9.36),
    ("--marke-3", "--flaeche-2"): (4.27, 8.42),
    ("--ok", "--akzent-flaeche"): (5.53, 7.56),
    ("--akzent-text", "schleier:--akzent"): (8.45, 9.57),
    ("--fehler-text", "schleier:--fehler"): (7.99, 9.38),
    ("--text", "schleier:--flaeche"): (13.89, 11.16),
    ("--akzent", "schleier:--flaeche"): (6.40, 6.85),
    ("--akzent", "schleier:--grund"): (5.78, 7.63),
    ("--akzent", "schleier:--akzent-flaeche"): (5.41, 5.49),
}


def _pruefe_kontraste(modus: str) -> None:
    werte = MODI[modus]
    zu_wenig = []
    for vorne, hinten, minimum in paare():
        wert = kontrast(_farbe(werte, vorne), _farbe(werte, hinten))
        if wert < minimum:
            zu_wenig.append((vorne, hinten, round(wert, 2)))
    assert zu_wenig == []
    index = 0 if modus == "hell" else 1
    for (vorne, hinten), erwartet in ERWARTET.items():
        wert = kontrast(_farbe(werte, vorne), _farbe(werte, hinten))
        assert wert == pytest.approx(erwartet[index], abs=0.01), (vorne, hinten)


def test_kontrast_hell():
    _pruefe_kontraste("hell")


def test_kontrast_dunkel():
    _pruefe_kontraste("dunkel")


def _gleich(a: str, b: str) -> bool:
    return re.sub(r"\s+", "", a.lower()) == re.sub(r"\s+", "", b.lower())


def test_token_wie_leinwand():
    leinwand = leinwand_token()
    for dunkel, werte in leinwand.items():
        eigene = T.dunkel if dunkel else T.hell
        for name, wert in werte.items():
            if name in NICHT_UEBERNOMMEN:
                continue
            ziel = UMBENANNT.get(name, name)
            assert ziel in eigene, ziel
            assert _gleich(eigene[ziel], wert), (dunkel, name, eigene[ziel], wert)
        aus_der_leinwand = {UMBENANNT.get(n, n) for n in werte}
        assert set(eigene) - aus_der_leinwand == set(NICHT_IN_DER_LEINWAND)


def test_themenklassen_in_den_tokenbloecken():
    assert T.color_scheme[HELL] == "light"
    assert T.color_scheme[DUNKEL] == "dark"
    assert T.dunkel_auto  # der Block unter @media steht ohne Themenklasse
    koepfe = [" ".join(s.regel.kopf.split()) for s in stilregeln(css())]
    assert koepfe.count(HELL) == 1 and koepfe.count(DUNKEL) == 1
    # sonst nur die Grundregel der Themenrahmen (Hintergrund und Text, /muster)
    andere = {k for k in koepfe if ".thema-" in k} - {HELL, DUNKEL}
    assert andere <= {".thema-hell, .thema-dunkel"}


def test_jedes_token_in_beiden_modi():
    assert sorted(T.hell) == sorted(FARBEN)
    assert set(T.hell) == set(T.dunkel)
    assert all(T.hell[n] and T.dunkel[n] for n in FARBEN)


def test_dunkel_zweimal_gleich():
    assert T.dunkel_auto == T.dunkel


def test_color_scheme_je_wahl():
    assert T.color_scheme == {HELL: "light", DUNKEL: "dark", AUTO: "light dark"}


SKALA = {
    "--gr-1": "0.75rem",
    "--gr-2": "0.8125rem",
    "--gr-3": "0.875rem",
    "--gr-4": "1rem",
    "--gr-5": "1.125rem",
    "--gr-6": "1.25rem",
    "--gr-7": "1.375rem",
    "--gr-8": "1.75rem",
    "--gr-9": "2.5rem",
}


def _alle_deklarationen(datei=CSS):  # noqa: ANN001, ANN202
    for stelle in stilregeln(css(datei)):
        for name, wert in stelle.regel.deklarationen:
            yield stelle, name, wert


def test_schriftgroessen_nur_aus_der_skala():
    assert {n: w for n, w in T.masse.items() if n.startswith("--gr-")} == SKALA
    for datei in (CSS, PRUEFEN_CSS):
        for stelle, name, wert in _alle_deklarationen(datei):
            if name == "font-size":
                assert re.fullmatch(r"var\(--gr-[1-9]\)|inherit|1em", wert), (
                    stelle.regel.kopf,
                    wert,
                )


ABSTAND = re.compile(r"padding|margin|gap|row-gap|column-gap|inset|border-radius")
ERLAUBT = re.compile(
    r"var\(--a-\d+\)|var\(--fein-\d\)|var\(--radius(-[a-z]+)?\)|0|auto|-?1px"
    r"|env\(safe-area-inset-(top|right|bottom|left)\)"
)


def _atome(wert: str) -> list[str]:
    """Teile eines Werts; ``calc(…)`` in seine Glieder zerlegt."""
    atome = []
    for teil in re.findall(r"calc\((?:[^()]|\([^()]*\))*\)|\S+", wert):
        if teil.startswith("calc("):
            innen = teil[len("calc(") : -1]
            atome += [a for a in re.split(r"\s+[-+*/]\s+", innen.strip()) if a]
        else:
            atome.append(teil)
    return atome


def test_abstaende_und_radien_aus_token():
    for stelle, name, wert in _alle_deklarationen():
        if stelle.ebene not in ("layout", "komponenten", "seiten"):
            continue
        if not re.fullmatch(rf"({ABSTAND.pattern})(-[a-z-]+)?", name):
            continue
        for atom in _atome(wert.replace("!important", "")):
            assert ERLAUBT.fullmatch(atom), (stelle.regel.kopf, name, wert)
            if atom.startswith("var(--fein-"):
                assert stelle.ebene == "komponenten", (stelle.regel.kopf, name)


FARBLITERAL = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(|"
    r"\b(white|black|red|green|blue|gray|grey|yellow|orange|purple|silver)\b"
)


def test_farben_nur_ueber_token():
    for datei in (CSS, PRUEFEN_CSS):
        for stelle, name, wert in _alle_deklarationen(datei):
            if stelle.ebene == "token" or "@media print" in stelle.medien:
                continue
            assert not FARBLITERAL.search(wert), (datei.name, stelle.regel.kopf, name)


def _regeln_mit(selektor: str, ebene: str | None = None):  # noqa: ANN202
    return [
        s
        for s in stilregeln(css())
        if selektor in selektoren(s.regel.kopf) and (ebene is None or s.ebene == ebene)
    ]


def test_formularelemente_aus_token():
    """AK4 statisch: Felder und Knöpfe nehmen Hintergrund, Text und Rand aus Token
    (auch dunkel nicht weiß); ``kbd`` ohne Deckkraft."""
    for element in ("input", "select", "textarea", "button"):
        (regel,) = (
            s.regel
            for s in _regeln_mit(element, "basis")
            if s.regel.wert("background-color") and not s.medien
        )
        assert regel.wert("background-color") == "var(--flaeche)", element
        assert regel.wert("color") == "var(--text)", element
        assert "var(--linie-stark)" in (regel.wert("border") or ""), element
        assert regel.wert("font") == "inherit", element
    haken = _regeln_mit('input[type="checkbox"]', "basis")
    assert any(s.regel.wert("accent-color") == "var(--akzent)" for s in haken)
    kbd = _regeln_mit("kbd")
    assert kbd and all(s.regel.wert("opacity") is None for s in kbd)
    assert any(s.regel.wert("color") == "var(--text-2)" for s in kbd)


def test_nur_gewichte_400_und_600():
    for datei in (CSS, PRUEFEN_CSS):
        for stelle, name, wert in _alle_deklarationen(datei):
            if name == "font-weight":
                assert wert in ("400", "600"), (stelle.regel.kopf, wert)
    for element in ("strong", "b", "th", "h1", "summary", "legend"):
        assert any(
            s.regel.wert("font-weight") == "600" for s in _regeln_mit(element, "basis")
        ), element


FARBE_UND_DECKKRAFT = {
    "color",
    "background-color",
    "border-color",
    "outline-color",
    "opacity",
}


def test_uebergaenge_kurz_nur_farbe_und_deckkraft():
    gesehen = False
    for stelle, name, wert in _alle_deklarationen():
        if name == "transition":
            gesehen = True
            for teil in wert.split(","):
                eigenschaft, dauer = teil.split()[:2]
                assert eigenschaft in FARBE_UND_DECKKRAFT, (stelle.regel.kopf, teil)
                assert re.fullmatch(r"\d+ms", dauer) and int(dauer[:-2]) <= 150, teil
        assert name not in ("transition-property", "animation", "animation-name")
    assert gesehen


def test_reduzierte_bewegung_ohne_uebergang():
    regeln = [
        s.regel
        for s in stilregeln(css())
        if "@media (prefers-reduced-motion: reduce)" in s.medien
    ]
    assert any(
        r.wert("transition-duration") == "0s !important"
        and r.wert("animation-duration") == "0s !important"
        for r in regeln
    )


def test_fokusring_3px_mit_2px_abstand():
    (regel,) = (s.regel for s in _regeln_mit(":focus-visible", "basis"))
    assert regel.wert("outline") == "3px solid var(--fokus)"
    assert regel.wert("outline-offset") == "2px"
    for stelle, name, wert in _alle_deklarationen():
        if name == "outline" and wert not in ("0", "none"):
            assert wert.startswith("3px solid var(--fokus)"), stelle.regel.kopf


def test_nur_drei_breakpoints():
    """Breiten nur 40, 64 und 90rem — schmaler als X als ``not all and (min-width:
    X)``, damit sich beide Seiten nie überschneiden (1024 px ist ein iPad quer); dazu
    ``max-height: 30rem`` für wenig Höhe."""
    erlaubt = re.compile(
        r"@media (not all and )?\(min-width: (40|64|90)rem\)"
        r"|@media \(max-height: 30rem\)"
        r"|@media \(prefers-(color-scheme: dark|reduced-motion: reduce)\)"
        r"|@media \(pointer: coarse\)|@media print"
    )
    for datei in (CSS, PRUEFEN_CSS):
        for kopf in medienregeln(css(datei)):
            assert erlaubt.fullmatch(kopf), (datei.name, kopf)


def test_hidden_versteckt_immer():
    (regel,) = (s.regel for s in _regeln_mit("[hidden]", "basis"))
    assert regel.wert("display") == "none !important"


def test_css_budget():
    """AK50: 40 KB für alle Stile — bis Schritt 12 zählt ``pruefen.css`` mit."""
    groesse = CSS.stat().st_size + PRUEFEN_CSS.stat().st_size
    assert groesse <= 40_960, groesse


EBENEN = "token, basis, layout, bestand, komponenten, seiten, hilfen, druck"


def test_ebenenfolge_wie_entschieden():
    oben = css()
    assert oben[0].anweisung and oben[0].kopf == f"@layer {EBENEN}"


def test_jede_regel_in_einer_ebene():
    for regel in css():
        assert regel.kopf.startswith("@layer "), regel.kopf
    (bestand,) = css(PRUEFEN_CSS)
    assert bestand.kopf == "@layer bestand" and not bestand.anweisung


def test_jeder_tokenverweis_definiert():
    hell = set(T.hell) | set(T.masse)
    dunkel = set(T.dunkel) | set(T.masse)
    for datei in (CSS, PRUEFEN_CSS):
        text = datei.read_text(encoding="utf-8")
        for name in set(re.findall(r"var\((--[\w-]+)", text)):
            assert name in hell and name in dunkel, (datei.name, name)
