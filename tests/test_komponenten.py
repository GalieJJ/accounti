"""Komponenten der Oberfläche als Jinja-Makros (Spec 10c A92–A95, A108–A111; Plan P1
Schritt 4, Aussehen nach L4). Jedes Makro wird über eine kleine Vorlage gerendert."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from jinja2 import TemplateError

from accounti.api.vorlagen import UMGEBUNG


def render(quelle: str, **werte: object) -> str:
    vorlage = UMGEBUNG.from_string(
        '{% import "_komponenten.html" as k with context %}' + quelle
    )
    return vorlage.render(sprache=werte.pop("sprache", "de"), **werte)


def nur(html: str, tag: str) -> list[str]:
    """Alle öffnenden Tags ``<tag …>`` eines Ausschnitts."""
    return re.findall(rf"<{tag}\b[^>]*>", html)


# --- Knopf, Linkknopf, Attribute ----------------------------------------------------


def test_knopf_arten_groessen_zustaende():
    html = render('{{ k.knopf("Freigeben") }}')
    assert html.startswith('<button type="submit" class="knopf knopf-primaer">')
    assert html.endswith(">Freigeben</button>")
    for art in ("primaer", "sekundaer", "still", "gefaehrlich"):
        assert f"knopf-{art}" in render(f'{{{{ k.knopf("x", art="{art}") }}}}')
    assert 'class="knopf knopf-sekundaer knopf-klein knopf-breit"' in render(
        '{{ k.knopf("x", art="sekundaer", groesse="klein", breit=true) }}'
    )
    assert "knopf-gross" in render('{{ k.knopf("x", groesse="gross") }}')
    aus = render('{{ k.knopf("x", deaktiviert=true) }}')
    assert " disabled" in aus and "aria-disabled" not in aus
    laedt = render('{{ k.knopf("Speichert …", laedt=true) }}')
    assert 'aria-busy="true"' in laedt and "#loader-circle" in laedt
    assert "Speichert …</button>" in laedt
    mit = render(
        '{{ k.knopf("Weiter", symbol="arrow-right", taste="f", typ="button") }}'
    )
    assert 'type="button"' in mit and "#arrow-right" in mit and "<kbd>f</kbd>" in mit
    link = render('{{ k.linkknopf("Durcharbeiten", "/pruefen?a=1&b=2", taste="j") }}')
    assert link.startswith(
        '<a class="knopf knopf-sekundaer" href="/pruefen?a=1&amp;b=2">'
    )
    for falsch in ('art="bunt"', 'groesse="riesig"', 'typ="image"'):
        with pytest.raises(TemplateError):
            render(f'{{{{ k.knopf("x", {falsch}) }}}}')


def test_attribute_nur_aus_positivliste():
    html = render(
        '{{ k.knopf("x", attribute={"hx-post": "/a?b=1&c=\\"2\\"", "data-taste": "f",'
        ' "aria-controls": "liste", "formnovalidate": true, "hx-vals": none}) }}'
    )
    assert 'hx-post="/a?b=1&amp;c=&#34;2&#34;"' in html
    assert 'data-taste="f"' in html and 'aria-controls="liste"' in html
    assert " formnovalidate" in html and "hx-vals" not in html
    # Prüfungen des Browsers wie im Bestand (Schritt 12): dieselben Felder
    feld = render(
        '{{ k.feld("soll", "Soll", attribute={"required": true,'
        ' "pattern": "[0-9]{4,9}", "maxlength": 9, "minlength": 4}) }}'
    )
    assert ' required pattern="[0-9]{4,9}" maxlength="9" minlength="4">' in feld
    code = render('{{ k.codefeld(attribute={"required": true}) }}')
    assert 'inputmode="numeric" required>' in code
    for name in ("onclick", "style", "href", "class", "hx-on:click", "data-x y", "a>b"):
        with pytest.raises((ValueError, TemplateError)):
            render("{{ k.knopf('x', attribute={name: 'y'}) }}", name=name)
        with pytest.raises((ValueError, TemplateError)):
            render("{{ k.linkknopf('x', '/', attribute={name: 'y'}) }}", name=name)


def test_name_direkt_vor_value():
    html = render('{{ k.knopf("Speichern", name="aktion", wert="weiter") }}')
    assert 'name="aktion" value="weiter"' in html
    assert 'name="leer" value=""' in render('{{ k.knopf("x", name="leer") }}')


# --- Status und Sicherheit ----------------------------------------------------------


def test_status_und_sicherheit_wort_und_symbol():
    zeichen = {
        "ok": "check",
        "info": "info",
        "warn": "triangle-alert",
        "fehler": "triangle-alert",
    }
    for art, symbol in zeichen.items():
        html = render(f'{{{{ k.status("{art}", "Wort") }}}}')
        assert html.startswith(f'<span class="status status-{art}">'), art
        assert f"#{symbol}" in html and "symbol-14 symbol-kraeftig" in html
        assert html.endswith("Wort</span>")
    with pytest.raises(TemplateError):
        render('{{ k.status("bunt", "x") }}')
    for stufe in ("niedrig", "mittel", "hoch"):
        html = render(f'{{{{ k.sicherheit("{stufe}") }}}}')
        assert f"sicherheit-{stufe}" in html
        assert f"Sicherheit: {stufe}" in html
        kaestchen = re.search(r'<span class="sicherheit-kaestchen"[^>]*>', html)
        assert kaestchen and 'aria-hidden="true"' in kaestchen.group(0)
        assert html.count("<span></span>") == 3
    assert "Sicherheit: mittel · KI" in render('{{ k.sicherheit("mittel", "KI") }}')
    assert "sicherheit-klein" in render('{{ k.sicherheit("hoch", klein=true) }}')
    assert "Confidence: high" in render('{{ k.sicherheit("hoch") }}', sprache="en")


def test_zaehler_betont_und_beschriftung():
    html = render('{{ k.zaehler(12, "offen") }}')
    assert (
        html == '<span class="zaehler">12<span class="unsichtbar"> offen</span></span>'
    )
    assert 'class="zaehler zaehler-betont"' in render(
        '{{ k.zaehler(3, "x", betont=true) }}'
    )


def test_marke_monogramm_ohne_aria_label_auf_span():
    from accounti.api.geruest import Marke

    m = Marke(kuerzel="muster", name="Galerie Demo GmbH", farbe=3, monogramm="GD")
    html = render("{{ k.marke(m) }}", m=m)
    assert html.startswith('<span class="marke marke-3" data-gesellschaft="muster">')
    assert '<span class="marke-monogramm" aria-hidden="true">GD</span>' in html
    assert '<span class="unsichtbar">Galerie Demo GmbH</span>' in html
    assert "aria-label" not in html
    link = render('{{ k.marke(m, klein=true, href="/gesellschaft") }}', m=m)
    assert link.startswith('<a class="marke marke-3 marke-klein" href="/gesellschaft"')
    assert link.endswith("</a>")
    for farbe in (0, 7):
        with pytest.raises(TemplateError):
            render("{{ k.marke(m) }}", m=Marke("x", "X", farbe, "XX"))
    assert render('{{ k.avatar("JH") }}') == (
        '<span class="avatar" aria-hidden="true">JH</span>'
    )


def test_hinweis_rolle_nur_wenn_neu():
    dauerhaft = render(
        '{% call k.hinweis("warn") %}Letzte Sicherung vor 9 Tagen.{% endcall %}'
    )
    assert "role=" not in dauerhaft
    neu = render(
        '{% call k.hinweis("ok", neu=true) %}6 Buchungen freigegeben.{% endcall %}'
    )
    assert 'role="status"' in neu
    fehler = render('{% call k.hinweis("fehler", neu=true) %}Code falsch.{% endcall %}')
    assert 'role="alert"' in fehler


def test_hinweis_mit_symbol_und_wort():
    erwartet = {
        "info": ("info", "Hinweis:"),
        "ok": ("check", "Erledigt:"),
        "warn": ("triangle-alert", "Achtung:"),
        "fehler": ("circle-x", "Fehler:"),
    }
    for art, (symbol, wort) in erwartet.items():
        html = render(f'{{% call k.hinweis("{art}") %}}Text{{% endcall %}}')
        assert html.startswith(f'<div class="hinweis hinweis-{art}">'), art
        assert f"#{symbol}" in html
        assert f'<strong class="hinweis-wort">{wort}</strong> Text' in html
    eigen = render('{% call k.hinweis("info", titel="Gesperrt:") %}x{% endcall %}')
    assert ">Gesperrt:</strong>" in eigen
    assert ">Note:</strong>" in render(
        '{% call k.hinweis("info") %}x{% endcall %}', sprache="en"
    )


def test_leer_mit_satz_nebensatz_und_link_ohne_rolle():
    html = render(
        '{{ k.leer("Nichts zu prüfen.", "Nächster Bankabruf: heute 14:00.",'
        ' "So entsteht ein Zahlungslauf", "/hilfe/freigaben#zahlungslauf") }}'
    )
    assert html.startswith('<div class="leer">') and "role=" not in html
    assert "#check" in html and "symbol-28" in html
    assert '<p class="leer-satz">Nichts zu prüfen.</p>' in html
    assert '<p class="leer-neben">Nächster Bankabruf: heute 14:00.</p>' in html
    assert (
        '<a class="leer-aktion" href="/hilfe/freigaben#zahlungslauf">'
        "So entsteht ein Zahlungslauf</a>"
    ) in html
    beleg = render('{{ k.leer("Kein Beleg.", symbol="file-text") }}')
    assert 'class="leer leer-beleg"' in beleg and "#file-text" in beleg
    assert "symbol-40" in beleg and "<a " not in beleg


def test_karte_titel_anzahl_status_hauptaktion_kennzahl():
    html = render(
        '{% call k.karte("Prüfen", anzahl=12, status=("warn", "3 unsicher"),'
        ' hauptaktion=("Durcharbeiten", "/pruefen", "primaer")) %}'
        '<ul class="karte-liste"><li>Telekom</li></ul>{% endcall %}'
    )
    assert html.startswith('<section class="karte">')
    assert (
        '<h2 class="karte-titel">Prüfen <span class="karte-anzahl">12</span></h2>'
        in html
    )
    assert 'class="status status-warn"' in html and "3 unsicher" in html
    assert (
        html.index("karte-titel")
        < html.index("status-warn")
        < html.index("karte-liste")
    )
    assert 'class="karte-fuss"><a class="knopf knopf-primaer" href="/pruefen">' in html
    link = render(
        '{% call k.karte("Belege", hauptaktion=("Alle", "/belege", "link"), ebene=3) %}'
        "{% endcall %}"
    )
    assert '<h3 class="karte-titel">Belege</h3>' in link
    assert '<a class="karte-aktion" href="/belege">Alle</a>' in link
    kennzahl = render(
        '{% call k.karte("Offene Posten", kennzahl=("4", "Rechnungen offen")) %}'
        "{% endcall %}"
    )
    assert '<p class="kennzahl"><span class="kennzahl-wert">4</span>' in kennzahl
    with pytest.raises(TemplateError):
        render('{% call k.karte("x", ebene=1) %}{% endcall %}')


def test_aufklapper_details_summary():
    zu = render('{% call k.aufklapper("Zahlungen ansehen (4)") %}Liste{% endcall %}')
    assert zu.startswith('<details class="aufklapper aufklapper-linie"><summary>')
    assert "Zahlungen ansehen (4)</summary>" in zu and "Liste" in zu
    karte = render(
        '{% call k.aufklapper("Kennzahlen Oktober", art="karte", offen=true) %}'
        "x{% endcall %}"
    )
    assert '<details class="aufklapper aufklapper-karte" open>' in karte
    zustand = re.search(r'<span class="aufklapper-zustand"[^>]*>', karte)
    assert zustand and 'aria-hidden="true"' in zustand.group(0)
    assert "aufklappen" in karte and "zuklappen" in karte and "#chevron-down" in karte
    with pytest.raises(TemplateError):
        render('{% call k.aufklapper("x", art="kasten") %}{% endcall %}')


TABELLE = (
    '{% call k.tabelle("Konten", [Spalte("Konto"), Spalte("Betrag", zahl=true)],'
    ' summe=["Summe", "652,31 €"]) %}'
    '{% call k.zeile() %}{% call k.zelle("Konto") %}Telefon (4920){% endcall %}'
    '{% call k.zelle("Betrag", zahl=true) %}239,94 €{% endcall %}{% endcall %}'
    "{% call k.zeile(gewaehlt=true) %}"
    '{% call k.zelle("Konto") %}Bürobedarf{% endcall %}'
    '{% call k.zelle("Betrag", zahl=true) %}412,37 €{% endcall %}{% endcall %}'
    "{% endcall %}"
)


def test_tabelle_caption_pflicht_und_rollen():
    html = render(TABELLE)
    assert "<caption>Konten</caption>" in html
    assert '<table class="tabelle" role="table">' in html
    assert '<thead role="rowgroup">' in html and '<tbody role="rowgroup">' in html
    assert html.count('role="row"') == 4  # Kopf, zwei Zeilen, Summe
    assert '<th role="columnheader" scope="col">Konto</th>' in html
    assert '<th role="columnheader" scope="col" class="zahl">Betrag</th>' in html
    assert '<td role="cell" data-label="Konto">Telefon (4920)</td>' in html
    assert '<td role="cell" data-label="Betrag" class="zahl">239,94 €</td>' in html
    assert '<tfoot role="rowgroup"><tr role="row" class="summenzeile">' in html
    assert '<td role="cell" class="zahl" data-label="Betrag">652,31 €</td>' in html
    versteckt = render(
        '{% call k.tabelle("Konten", [Spalte("Konto")], sichtbar=false) %}{% endcall %}'
    )
    assert '<caption class="unsichtbar">Konten</caption>' in versteckt
    breit = render(
        '{% call k.tabelle("Monate", [Spalte("Monat")], kompakt=true) %}{% endcall %}'
    )
    rahmen = nur(breit, "div")[0]
    assert 'tabindex="0"' in rahmen and 'role="region"' in rahmen
    assert 'aria-label="Monate"' in rahmen and "tabelle-kompakt" in breit
    with pytest.raises(TemplateError):  # caption ist Pflicht
        render("{% call k.tabelle(spalten=[]) %}{% endcall %}")


def test_tabellenrahmen_scrollt_statt_abzuschneiden():
    """P1 Runde 2 (D-H1, A93/A107): jeder Tabellenrahmen scrollt waagrecht, wenn die
    Tabelle breiter ist als ihr Platz (wie in der Leinwand: ``overflow-x: auto``), und ist
    dann per Tastatur erreichbar und benannt — kein ``overflow: hidden/clip`` mehr, das
    breite Tabellen ab 64rem abschnitt."""
    from tests.design_hilfe import css, selektoren, stilregeln

    html = render('{% call k.tabelle("Journal", [Spalte("Nr.")]) %}{% endcall %}')
    rahmen = nur(html, "div")[0]
    assert 'class="tabelle-rahmen"' in rahmen
    assert 'tabindex="0"' in rahmen and 'role="region"' in rahmen
    assert 'aria-label="Journal"' in rahmen
    regeln = [
        s.regel
        for s in stilregeln(css())
        if any(".tabelle-rahmen" in x for x in selektoren(s.regel.kopf))
    ]
    (grund,) = (r for r in regeln if r.kopf == ".tabelle-rahmen")
    assert grund.wert("overflow-x") == "auto"
    for r in regeln:
        for name, wert in r.deklarationen:
            if name.startswith("overflow"):
                assert wert not in ("hidden", "clip"), (r.kopf, name, wert)


def test_sortieren_auch_in_der_kartenform():
    """P1 Runde 2 (gp1-design B6): Unter 64rem ist der Tabellenkopf versteckt — die
    Sortierlinks waren dort unsichtbar fokussierbar, Sortieren ging nicht. Eine Tabelle
    mit sortierbaren Spalten (``tabelle-sortierbar``) zeigt in der Kartenform eine
    Zeile mit den Sortierlinks; Spalten ohne Sortierung bleiben nur für Screenreader."""
    from tests.design_hilfe import css, selektoren, stilregeln

    html = render(
        '{% call k.tabelle("Umsätze", [Spalte("Datum", sortierung="absteigend", '
        'href="/x?s=datum"), Spalte("Text")]) %}{% endcall %}'
    )
    assert '<table class="tabelle tabelle-sortierbar" role="table">' in html
    assert "tabelle-sortierbar" not in render(
        '{% call k.tabelle("Umsätze", [Spalte("Text")]) %}{% endcall %}'
    )
    schmal = {}
    for s in stilregeln(css()):
        if any("not all and (min-width: 64rem)" in m for m in s.medien):
            for sel in selektoren(s.regel.kopf):
                schmal.setdefault(sel, {}).update(dict(s.regel.deklarationen))
    kopf = schmal[".tabelle-sortierbar:not(.tabelle-kompakt) thead"]
    assert kopf["position"] == "static" and kopf["clip-path"] == "none"
    zeile = schmal[".tabelle-sortierbar:not(.tabelle-kompakt) thead tr"]
    assert zeile["display"] == "flex"
    ohne = schmal[".tabelle-sortierbar:not(.tabelle-kompakt) th:not([aria-sort])"]
    assert ohne["clip-path"] == "inset(50%)"


def test_spaltenkopf_aria_sort():
    for sortierung, aria, symbol in (
        ("aufsteigend", "ascending", "arrow-up"),
        ("absteigend", "descending", "arrow-down"),
        ("keine", "none", "arrow-up-down"),
    ):
        html = render(
            "{{ k.spaltenkopf(Spalte('Datum', sortierung=s, href='/x?sort=datum')) }}",
            s=sortierung,
        )
        assert f'aria-sort="{aria}"' in html and f"#{symbol}" in html
        assert '<a class="spalte-sortieren" href="/x?sort=datum">Datum' in html
    assert "aria-sort" not in render("{{ k.spaltenkopf(Spalte('Datum')) }}")


def test_tabelle_in_karte_und_gewaehlte_zeile():
    html = render(
        '{% call k.tabelle("Jahre", [Spalte("Jahr")], in_karte=true) %}'
        '{% call k.zeile(gewaehlt=true) %}{% call k.zelle("Jahr") %}2026{% endcall %}'
        "{% endcall %}{% endcall %}"
    )
    assert 'class="tabelle-rahmen tabelle-in-karte"' in html
    assert '<tr role="row" class="zeile-gewaehlt">' in html
    assert "aria-selected" not in html


def test_angaben_als_dl():
    html = render(
        '{% call k.angaben() %}{% call k.angabe("Verwendungszweck") %}RE 4711'
        "{% endcall %}{% endcall %}"
    )
    assert html == (
        '<dl class="angaben"><div class="angabe"><dt>Verwendungszweck</dt>'
        "<dd>RE 4711</dd></div></dl>"
    )
    assert 'class="angaben angaben-klein"' in render(
        "{% call k.angaben(klein=true) %}{% endcall %}"
    )


def test_betrag_vorzeichen_und_richtung_als_text():
    ein = render("{{ k.betrag(w, 'einnahme') }}", w=Decimal("780.25"))
    assert '<span class="betrag-wert">+ 780,25 €</span>' in ein
    assert '<span class="betrag-richtung">Einnahme</span>' in ein
    aus = render("{{ k.betrag(w, 'ausgabe') }}", w=Decimal("-1204.90"))
    assert "− 1.204,90 €" in aus and "Ausgabe" in aus
    summe = render("{{ k.betrag(w) }}", w=Decimal("11111.11"))
    assert '<span class="betrag-wert">11.111,11 €</span>' in summe
    assert "betrag-richtung" not in summe and summe.startswith('<span class="betrag">')
    assert 'class="betrag betrag-gross"' in render(
        "{{ k.betrag(w, groesse='gross') }}", w=Decimal("1")
    )
    en = render("{{ k.betrag(w, 'ausgabe') }}", w=Decimal("-5"), sprache="en")
    assert "− €5.00" in en and "Payment out" in en
    with pytest.raises((ValueError, TemplateError)):
        render("{{ k.betrag(w, 'ueberweisung') }}", w=Decimal("1"))


def test_feld_label_hilfe_fehler_aria():
    html = render(
        '{{ k.feld("grund", "Grund", wert="x\\"y", hilfe="Wofür?",'
        ' fehler="Bitte einen Grund angeben.", pflicht=true, id="grund-k",'
        ' autocomplete="off", breite="breit") }}'
    )
    assert (
        '<label for="grund-k">Grund <span class="feld-pflicht">(Pflicht)</span>' in html
    )
    eingabe = nur(html, "input")[0]
    assert 'id="grund-k"' in eingabe and 'name="grund" value="x&#34;y"' in eingabe
    assert 'aria-invalid="true"' in eingabe and 'aria-required="true"' in eingabe
    assert 'aria-describedby="grund-k-hilfe grund-k-fehler"' in eingabe
    assert 'class="eingabe breite-breit"' in eingabe and 'autocomplete="off"' in eingabe
    assert '<p class="feld-hilfe" id="grund-k-hilfe">Wofür?</p>' in html
    assert 'id="grund-k-fehler"' in html and "#circle-x" in html
    assert "<strong>Fehler:</strong> Bitte einen Grund angeben." in html
    assert html.startswith('<div class="feld feld-fehler">')
    ohne = render('{{ k.feld("iban", "IBAN") }}')
    assert "aria-describedby" not in ohne and "aria-invalid" not in ohne
    assert 'id="iban"' in ohne and '<label for="iban">IBAN</label>' in ohne
    auswahl = render(
        '{{ k.auswahl("art", "Rechtsform", [("gmbh", "GmbH"), ("ug", "UG")],'
        ' gewaehlt="ug", fehler="x", id="art-1") }}'
    )
    # umgestellt (Plan P1, Schritt 12): id zuerst — die Bestandstests suchen
    # ``<select id="…"`` bzw. ``<input id="…"``
    assert '<select id="art-1" class="eingabe" name="art"' in auswahl
    assert '<option value="ug" selected>UG</option>' in auswahl
    assert 'aria-describedby="art-1-fehler"' in auswahl
    text = render('{{ k.textfeld("notiz", "Notiz", wert="<b>", hilfe="kurz") }}')
    assert "&lt;b&gt;</textarea>" in text and 'aria-describedby="notiz-hilfe"' in text
    with pytest.raises(TemplateError):
        render('{{ k.feld("x", "X", typ="file") }}')


def test_feld_warnung_ohne_aria_invalid_und_bestaetigt():
    html = render(
        '{{ k.feld("ustid", "USt-IdNr.", warnung="Prüfen Sie die Ländervorsilbe.",'
        ' bestaetigt="Format passt") }}'
    )
    assert html.startswith('<div class="feld feld-warnung">')
    eingabe = nur(html, "input")[0]
    assert "aria-invalid" not in eingabe
    assert 'aria-describedby="ustid-warnung ustid-bestaetigt"' in eingabe
    assert "#triangle-alert" in html and "<strong>Achtung:</strong>" in html
    assert 'id="ustid-bestaetigt">' in html and "#check" in html


def test_optionen_als_fieldset_mit_legend():
    html = render(
        '{% call k.feldgruppe("Anzeige") %}{{ k.optionen("darstellung", "Darstellung",'
        ' [("auto", "automatisch"), ("hell", "hell")], gewaehlt="hell",'
        ' fehler="Bitte wählen.", id="d-1") }}{% endcall %}'
    )
    assert (
        '<fieldset class="feldgruppe"><legend class="etikett">Anzeige</legend>' in html
    )
    assert (
        '<fieldset class="optionen feld-fehler" aria-describedby="d-1-fehler">' in html
    )
    assert "<legend>Darstellung</legend>" in html
    assert (
        '<label class="haken haken-ziel" for="d-1-hell"><input type="radio" '
        'id="d-1-hell" name="darstellung" value="hell" checked>hell</label>'
    ) in html
    assert 'value="auto">automatisch' in html
    haken = render(
        '{{ k.haken("regel", "Künftig immer so", gewaehlt=true, id="r-1") }}'
    )
    assert haken == (
        '<label class="haken haken-ziel" for="r-1"><input type="checkbox" id="r-1"'
        ' name="regel" value="1" checked>Künftig immer so</label>'
    )


def test_optionskarte_und_segment_ohne_skript():
    karte = render(
        '{{ k.optionskarte("konto", "4930", "Bürobedarf", nebentext="4930 · 19 %",'
        ' gewaehlt=true, taste="1") }}'
    )
    assert karte.startswith('<label class="optionskarte" for="konto-4930">')
    assert (
        '<input type="radio" id="konto-4930" name="konto" value="4930" checked>'
        in karte
    )
    assert "<kbd>1</kbd>" in karte and "4930 · 19 %" in karte
    gesperrt = render('{{ k.optionskarte("k", "1", "X", grund="nur mit Beleg") }}')
    assert " disabled" in gesperrt and "nur mit Beleg" in gesperrt
    segment = render(
        '{{ k.segment("ust", "Umsatzsteuer", [("monat", "monatlich"),'
        ' ("quartal", "vierteljährlich")], gewaehlt="quartal") }}'
    )
    assert (
        '<fieldset class="segment"><legend class="etikett">Umsatzsteuer</legend>'
        in segment
    )
    assert 'name="ust" value="quartal" checked>vierteljährlich' in segment
    for html in (karte, gesperrt, segment):
        assert re.search(r"\son[a-z]+=|style=|<script", html) is None


def test_codefeld_ein_feld_numerisch_und_variante():
    html = render(
        "{{ k.codefeld(wechsel_href="
        '"/anmelden?weiter=%2Fpruefen&code=wiederherstellung",'
        ' id="einmalcode-lauf-3") }}'
    )
    assert len(nur(html, "input")) == 1
    eingabe = nur(html, "input")[0]
    assert 'id="einmalcode-lauf-3"' in eingabe and 'name="einmalcode"' in eingabe
    assert (
        'inputmode="numeric"' in eingabe and 'autocomplete="one-time-code"' in eingabe
    )
    assert "pattern" not in eingabe and "maxlength" not in eingabe
    label = html.index(
        '<label for="einmalcode-lauf-3">Code aus Ihrer Authenticator-App'
    )
    link = html.index(
        '<a class="codefeld-wechsel" href="/anmelden?weiter=%2Fpruefen&amp;code='
        'wiederherstellung">Wiederherstellungscode verwenden</a>'
    )
    assert label < link < html.index("<input")
    text = render(
        '{{ k.codefeld("wiederherstellung", wechsel_href="/anmelden",'
        ' fehler="falsch") }}'
    )
    eingabe = nur(text, "input")[0]
    assert 'inputmode="text"' in eingabe and 'autocapitalize="off"' in eingabe
    assert 'spellcheck="false"' in eingabe and 'id="einmalcode"' in eingabe
    assert 'aria-invalid="true" aria-describedby="einmalcode-fehler"' in eingabe
    assert '<label for="einmalcode">Wiederherstellungscode</label>' in text
    assert "Code aus der App verwenden</a>" in text
    with pytest.raises(TemplateError):
        render('{{ k.codefeld("sms") }}')


def test_fehlerliste_alert_mit_links():
    html = render(
        "{{ k.fehlerliste([('grund', 'Bitte einen Grund angeben.'),"
        " ('steuer', 'Steuer fehlt.'), (none, 'Allgemein')],"
        " ids={'grund': 'grund-k'}) }}"
    )
    rahmen = nur(html, "div")[0]
    assert (
        'role="alert"' in rahmen
        and "data-fokus" in rahmen
        and 'tabindex="-1"' in rahmen
    )
    assert "hinweis-fehler" in rahmen and "Bitte prüfen" in html
    assert '<a href="#grund-k">Bitte einen Grund angeben.</a>' in html
    assert '<a href="#steuer">Steuer fehlt.</a>' in html
    assert "<li>Allgemein</li>" in html


def test_reiter_als_nav_mit_aria_current():
    html = render(
        '{{ k.reiter("Ansicht", [("offen", "Offen", "/pruefen", 12),'
        ' ("zurueck", "Zurückgestellt", "/pruefen?ansicht=zurueckgestellt", 2),'
        ' ("regeln", "Gelernte Regeln", "/pruefen/regeln")], "offen") }}'
    )
    assert html.startswith('<nav class="reiter" aria-label="Ansicht">')
    assert (
        '<a href="/pruefen" aria-current="page">Offen '
        '<span class="reiter-anzahl">12</span>' in (html)
    )
    assert html.count("aria-current") == 1 and "role=" not in html
    assert '<a href="/pruefen/regeln">Gelernte Regeln</a>' in html
    assert 'class="reiter reiter-geteilt"' in render(
        '{{ k.reiter("x", [("a", "A", "/a")], "a", geteilt=true) }}'
    )


def test_schritte_mit_progress_und_aria_current_step():
    html = render('{{ k.schritte(["Firma", "Konten", "Steuern", "Bank"], 3) }}')
    assert "Schritt 3 von 4" in html
    assert '<progress class="fortschritt" value="3" max="4" aria-hidden="true">' in html
    assert html.count('aria-current="step"') == 1
    assert '<li class="schritt schritt-aktuell" aria-current="step">' in html
    assert html.count("schritt-erledigt") == 2 and html.count("schritt-offen") == 1
    assert "(erledigt)" in html
    assert "Step 1 of 2" in render('{{ k.schritte(["a", "b"], 1) }}', sprache="en")


def test_bestaetigung_und_ladeanzeige():
    html = render(
        '{% call k.bestaetigung("Wirklich stornieren?", "Stornieren", "/buchungen/1",'
        ' art="gefaehrlich") %}<p>Die Buchung wird gegengebucht.</p>{% endcall %}'
    )
    assert 'role="group" aria-label="Wirklich stornieren?"' in html
    assert (
        '<button type="submit" class="knopf knopf-gefaehrlich">Stornieren</button>'
        in html
    )
    assert '<a class="knopf knopf-still" href="/buchungen/1">Abbrechen</a>' in html
    lade = render("{{ k.ladeanzeige() }}")
    assert lade.startswith('<p class="ladeanzeige">') and "#loader-circle" in lade
    assert "Wird geladen …" in lade and "role=" not in lade


def test_brotkrumen_und_seitenblaettern():
    html = render('{{ k.brotkrumen([("Prüfen", "/pruefen"), ("Telekom", none)]) }}')
    assert html.startswith('<nav class="brotkrumen" aria-label="Brotkrumen"><ol>')
    assert '<a href="/pruefen">Prüfen</a>' in html
    assert '<span aria-current="page">Telekom</span>' in html
    assert '<span class="brotkrumen-trenner" aria-hidden="true">›</span>' in html
    assert 'aria-label="Breadcrumbs"' in render(
        '{{ k.brotkrumen([("a", none)]) }}', sprache="en"
    )
    blaettern = render('{{ k.seitenblaettern(5, 12, "/pruefen?seite=") }}')
    assert 'aria-label="Seiten"' in blaettern
    assert 'href="/pruefen?seite=5" aria-current="page">5</a>' in blaettern
    assert (
        'href="/pruefen?seite=4"' in blaettern
        and 'href="/pruefen?seite=12"' in blaettern
    )
    assert 'href="/pruefen?seite=9"' not in blaettern and "…" in blaettern
    assert blaettern.count('aria-current="page"') == 1
    assert render('{{ k.seitenblaettern(1, 1, "/x?seite=") }}') == ""


def beispielgeruest():  # noqa: ANN201
    from accounti.api.geruest import Geruest, NavEintrag

    return Geruest(
        bereiche=(
            NavEintrag("Übersicht", "/", "house"),
            NavEintrag(
                "Prüfen",
                "/pruefen",
                "square-check-big",
                zaehler=12,
                betont=True,
                aktiv=True,
            ),
            NavEintrag("Freigaben", "/freigaben", "shield-check", zaehler=2),
        ),
        einstellungen=NavEintrag("Einstellungen", "/einstellungen", "settings"),
        unten=(
            NavEintrag("Übersicht", "/", "house"),
            NavEintrag(
                "Prüfen", "/pruefen", "square-check-big", zaehler=12, aktiv=True
            ),
            NavEintrag(
                "Freigaben", "/freigaben", "shield-check", kurztitel="Frei", zaehler=2
            ),
            NavEintrag("Mehr", "/menue", "menu"),
        ),
    )


def test_navigationsmakros_mit_beispielgeruest():
    g = beispielgeruest()
    seite = render("{{ k.seitenleiste(g) }}", g=g)
    assert seite.startswith('<nav class="seitenleiste" aria-label="Bereiche">')
    assert seite.count('class="nav-eintrag"') == 4  # drei Bereiche und Einstellungen
    assert seite.count('aria-current="page"') == 1
    assert '<a class="nav-eintrag" href="/pruefen" aria-current="page">' in seite
    assert (
        '<span class="zaehler zaehler-betont">12<span class="unsichtbar"> offen'
        in seite
    )
    assert '<span class="zaehler">2<span class="unsichtbar"> offen' in seite
    assert '<hr class="nav-trenner">' in seite and "#settings" in seite
    unten = render("{{ k.untere_leiste(g) }}", g=g)
    assert unten.count('class="leisten-ziel"') == 4 and "symbol-22" in unten
    assert 'Prüfen <span class="leisten-zahl">12</span>' in unten
    assert "Frei <span" in unten and ">Freigaben<" not in unten
    assert unten.count('aria-current="page"') == 1 and unten.index(
        "/menue"
    ) > unten.index("/freigaben")
    englisch = render("{{ k.seitenleiste(g) }}", g=g, sprache="en")
    assert ">Overview<" in englisch and ">Review<" in englisch


def test_sammelleiste_und_aktionsleiste():
    sammel = render(
        "{% call k.sammelleiste() %}<strong>2 ausgewählt</strong>{% endcall %}"
    )
    assert sammel == (
        '<div class="sammelleiste" role="region" aria-label="Auswahl">'
        "<strong>2 ausgewählt</strong></div>"
    )
    aktion = render(
        '{% call k.aktionsleiste("Aktionen der Prüfung") %}'
        '{{ k.knopf("Passt – freigeben", breit=true, groesse="gross") }}{% endcall %}'
    )
    assert aktion.startswith(
        '<div class="aktionsleiste" role="region" aria-label="Aktionen der Prüfung">'
    )
    assert "knopf-gross knopf-breit" in aktion


def test_aktionsleiste_bricht_schmal_um():
    """P1 Runde 2 (gp1-design B7): Bei 320 px passten die beiden unteren Knöpfe der
    Aktionsleiste nicht nebeneinander („Später klären“ und das ``kbd`` von „Passt –
    freigeben“ abgeschnitten, mit Textabständen waagrechtes Scrollen). Die Spalten sind
    jetzt mindestens 8rem breit und rücken sonst untereinander."""
    from tests.design_hilfe import css, stilregeln

    (regel,) = (s.regel for s in stilregeln(css()) if s.regel.kopf == ".aktionsleiste")
    spalten = regel.wert("grid-template-columns")
    assert spalten == "repeat(auto-fit, minmax(min(8rem, 100%), 1fr))", spalten


def test_optionskarten_ohne_rahmen_des_browsers():
    """P1 Runde 2 (/muster bei 320 px mit Textabständen waagrechtes Scrollen): Das
    ``fieldset`` der Optionskarten behielt die Vorgaben des Browsers — ``min-width:
    min-content`` (mit den Textabständen aus WCAG 1.4.12 breiter als 320 px) und einen
    Rahmen. Es wird wie Feldgruppe, Optionen und Segment zurückgesetzt."""
    from tests.design_hilfe import css, selektoren, stilregeln

    werte: dict[str, str] = {}
    for s in stilregeln(css()):
        if ".optionskarten" in selektoren(s.regel.kopf):
            werte.update(dict(s.regel.deklarationen))
    assert werte.get("min-width") == "0" and werte.get("border") == "0", werte
    assert werte.get("padding") == "0" and werte.get("margin") == "0", werte
