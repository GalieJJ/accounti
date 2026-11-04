"""Buchungsansicht und Storno mit Einmalcode (Spec 4.4/4.2; Baustein 10b, Paket 3)."""

from __future__ import annotations

from datetime import date

import pytest

from accounti.models import BuchungStatus
from tests.api_hilfe import csrf, formularwert
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import queuewelt


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def qw(tmp_path):
    return queuewelt(tmp_path)


def buchungen(qw, kuerzel="a"):  # noqa: ANN001, ANN201
    return qw.sql(
        "SELECT id, status, soll_konto, storniert_durch, storno_von FROM "
        "buchungssaetze ORDER BY soll_konto, status",
        kuerzel,
    )


def senden(qw, client, b, was, *, code=True, **felder):  # noqa: ANN001, ANN003, ANN201
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {"csrf": csrf(client), "stand": formularwert(seite, "stand")}
    if code:
        daten["einmalcode"] = qw.web.personen["jan"].codes.pop()
    daten.update({k: str(v) for k, v in felder.items()})
    return client.post(f"/buchungen/{b.id}/{was}", data=daten)


def test_storno_kette_korrektur_und_journal_sichtbar(qw):
    from accounti.pruefung.storno import korrigiere

    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    with qw.fabrik()() as s:
        k = korrigiere(
            s, str(b.id), "4930", "1200", steuer=9, von="eva", grund="Bürobedarf"
        )
        s.commit()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    assert "Storniert durch" in seite and str(k.storno.id) in seite
    assert str(k.neu.id) in seite and "eva" in seite and "Bürobedarf" in seite
    for vorgang in ("buchung_angelegt", "buchung_storniert"):
        assert f"<code>{vorgang}</code>" in seite
    neu = client.get(f"/buchungen/{k.neu.id}").text
    assert "Original" in neu and "Neubuchung" in neu
    # kein Formular an Original und Storno (schon storniert bzw. selbst ein Storno)
    assert f"/buchungen/{b.id}/stornieren" not in seite
    assert (
        f"/buchungen/{k.storno.id}/stornieren"
        not in client.get(f"/buchungen/{k.storno.id}").text
    )


def test_freigegebene_buchung_korrigieren_ist_storno_und_neubuchung(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    r = senden(qw, client, b, "korrigieren", soll="4930", haben="1200", steuer="9")
    assert r.status_code == 200, r.text
    assert "Storniert durch Storno" in r.text
    zeilen = buchungen(qw)
    assert len(zeilen) == 3
    original = next(z for z in zeilen if z[0] == str(b.id))
    assert original[1] == "geprueft" and original[2] == "4980" and original[3]
    (person,) = qw.sql("SELECT person FROM buchungskorrekturen")[0]
    assert person == "jan"


def test_exportierte_buchung_nur_per_storno(qw):
    b = qw.buchung(status=BuchungStatus.EXPORTIERT)
    client = qw.web.angemeldet("jan")
    r = senden(qw, client, b, "korrigieren", soll="4930", haben="1200", steuer="9")
    assert r.status_code == 200
    original = next(z for z in buchungen(qw) if z[0] == str(b.id))
    assert original[1] == "exportiert" and original[3] is not None


def test_korrigieren_und_stornieren_verlangen_einmalcode(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    for was, felder in (
        ("korrigieren", {"soll": "4930", "haben": "1200", "steuer": "9"}),
        ("stornieren", {"grund": "doppelt"}),
    ):
        ohne = senden(qw, client, b, was, code=False, **felder)
        falsch = senden(qw, client, b, was, code=False, einmalcode="000000", **felder)
        assert ohne.status_code == falsch.status_code == 403, was
        assert "Einmalcode" in falsch.text
    assert len(buchungen(qw)) == 1
    code = qw.web.personen["jan"].codes.pop()
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "einmalcode": code,
        "grund": "doppelt",
    }
    assert client.post(f"/buchungen/{b.id}/stornieren", data=daten).status_code == 200
    # derselbe Code ein zweites Mal: verbraucht
    b2 = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 2))
    seite = client.get(f"/buchungen/{b2.id}").text
    daten["stand"] = formularwert(seite, "stand")
    assert client.post(f"/buchungen/{b2.id}/stornieren", data=daten).status_code == 403


def test_fachlich_abgelehnte_aktion_verbraucht_keinen_einmalcode(qw):
    """Nachbesserung Technik M3 (Probe c): Scheitert die Aktion erst in der
    Fachlogik (Konto ungültig, Sachkontowechsel ohne Steuerangabe), bleibt der
    Einmalcode — auch ein Wiederherstellungscode — gültig; erst die erfolgreiche
    Aktion verbraucht ihn."""
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    code = qw.web.personen["jan"].codes.pop()
    for felder in (
        {"soll": "12", "haben": "1200", "steuer": "9"},
        {"soll": "4360", "haben": "1200"},  # neues Sachkonto ohne Steuerangabe
    ):
        seite = client.get(f"/buchungen/{b.id}").text
        daten = {"csrf": csrf(client), "stand": formularwert(seite, "stand")}
        r = client.post(
            f"/buchungen/{b.id}/korrigieren",
            data={**daten, "einmalcode": code, **felder},
        )
        assert r.status_code == 422, (felder, r.status_code)
        assert len(buchungen(qw)) == 1
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {"csrf": csrf(client), "stand": formularwert(seite, "stand")}
    gut = {"soll": "4930", "haben": "1200", "steuer": "9", "einmalcode": code}
    r = client.post(f"/buchungen/{b.id}/korrigieren", data={**daten, **gut})
    assert r.status_code == 200, r.text
    assert len(buchungen(qw)) == 3  # Original, Storno, Neubuchung
    b2 = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 2))
    seite = client.get(f"/buchungen/{b2.id}").text
    daten = {"csrf": csrf(client), "stand": formularwert(seite, "stand")}
    r = client.post(f"/buchungen/{b2.id}/stornieren", data={**daten, "grund": "x",
                    "einmalcode": code})  # fmt: skip
    assert r.status_code == 403  # nach dem Erfolg verbraucht


def test_ohne_einmalcode_bestaetigung_kein_code(tmp_path):
    qw = queuewelt(tmp_path, einmalcode_bestaetigung=False)
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    assert 'name="einmalcode"' not in client.get(f"/buchungen/{b.id}").text
    r = senden(qw, client, b, "stornieren", code=False, grund="doppelt")
    assert r.status_code == 200 and len(buchungen(qw)) == 2


def test_gesperrter_zeitraum_verlangt_datum_ohne_vorbelegung(qw):
    from accounti.pruefung.perioden import schliesse

    b = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 8, 12))
    with qw.fabrik()() as s:
        schliesse(s, "2026-08", "erika")
        s.commit()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    # umgestellt (Plan P1, Schritt 12): Felder als Komponente — beide Datumsfelder leer
    # und Pflicht
    import re

    for ident in ("datum-k", "datum-s"):
        feld = re.search(rf'<input id="{ident}"[^>]*>', seite)
        assert feld and 'type="date"' in feld.group(0), ident
        assert 'value=""' in feld.group(0) and " required" in feld.group(0), ident
    r = senden(qw, client, b, "stornieren", grund="doppelt")
    assert r.status_code == 422 and "--datum" not in r.text
    assert "offenen Zeitraum" in r.text
    r = senden(qw, client, b, "stornieren", grund="doppelt", datum="2026-09-02")
    assert r.status_code == 200, r.text


def test_warnung_anderer_voranmeldungszeitraum(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 8, 12))
    r = senden(
        qw,
        qw.web.angemeldet("jan"),
        b,
        "stornieren",
        grund="doppelt",
        datum="2026-09-02",
    )
    assert r.status_code == 200 and "anderen Voranmeldungszeitraum" in r.text


def test_stornieren_verlangt_grund(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    vorher = len(qw.web.personen["jan"].codes)
    r = senden(qw, client, b, "stornieren", code=False, grund="  ")
    assert r.status_code == 422 and len(buchungen(qw)) == 1
    assert len(qw.web.personen["jan"].codes) == vorher


def test_veralteter_stand_409_kein_storno(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    alt = formularwert(seite, "stand")
    qw.sql("UPDATE buchungssaetze SET status = 'exportiert'")
    code = qw.web.personen["jan"].codes[-1]
    r = client.post(
        f"/buchungen/{b.id}/stornieren",
        data={"csrf": csrf(client), "stand": alt, "einmalcode": code, "grund": "x"},
    )
    assert r.status_code == 409 and len(buchungen(qw)) == 1
    # der Code wurde nicht verbraucht
    r = senden(qw, client, b, "stornieren", grund="doppelt")
    assert r.status_code == 200


def test_reines_storno_hinweis_umsatz_wieder_offen(qw):
    tx = qw.umsatz()
    b = qw.buchung(status=BuchungStatus.GEPRUEFT, transaktion_id=tx.id)
    r = senden(qw, qw.web.angemeldet("jan"), b, "stornieren", grund="falsch kontiert")
    assert r.status_code == 200
    assert (
        "Der Umsatz ist wieder offen und wird beim nächsten Lauf neu kontiert" in r.text
    )


def test_storno_hinweis_nur_wenn_der_umsatz_wirklich_offen_ist(qw):
    """Nachbesserung Fach N4 (Probe p4): Bleibt ein weiterer Buchungssatz am selben
    Umsatz (zwei Steuersätze), ist der Umsatz nach einem Storno nicht wieder offen —
    kein Hinweis „wird beim nächsten Lauf neu kontiert“."""
    from decimal import Decimal

    tx = qw.umsatz()
    b = qw.buchung(status=BuchungStatus.GEPRUEFT, transaktion_id=tx.id)
    qw.buchung(
        status=BuchungStatus.GEPRUEFT,
        transaktion_id=tx.id,
        soll="4930",
        steuer_schluessel=8,
        betrag_netto=Decimal("10.00"),
        steuer_betrag=Decimal("0.70"),
    )
    r = senden(qw, qw.web.angemeldet("jan"), b, "stornieren", grund="falsch")
    assert r.status_code == 200 and "Storniert durch Storno" in r.text
    assert "Der Umsatz ist wieder offen" not in r.text


def test_storno_eines_stornos_abgelehnt(qw):
    from accounti.pruefung.storno import storniere

    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    with qw.fabrik()() as s:
        k = storniere(s, str(b.id), grund="doppelt", von="eva")
        s.commit()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{k.storno.id}").text
    assert f"/buchungen/{k.storno.id}/stornieren" not in seite
    from accounti.buchung.pruefschlange import stand

    with qw.fabrik()() as s:
        aktuell = stand(s, k.storno.id)
    daten = {
        "csrf": csrf(client),
        "stand": aktuell,
        "einmalcode": qw.web.personen["jan"].codes.pop(),
        "grund": "zurück",
    }
    r = client.post(f"/buchungen/{k.storno.id}/stornieren", data=daten)
    assert r.status_code == 409 and "selbst ein Storno" in r.text
    assert len(buchungen(qw)) == 2


def test_stornieren_braucht_buchen(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    for wer in ("fritz", "leo", "vera"):
        client = qw.web.angemeldet(wer)
        assert (
            f"/buchungen/{b.id}/stornieren" not in client.get(f"/buchungen/{b.id}").text
        )
        r = client.post(
            f"/buchungen/{b.id}/stornieren", data={"csrf": csrf(client), "grund": "x"}
        )
        assert r.status_code == 403, wer


def test_buchung_im_design(qw):
    """Plan P1, Schritt 12: Journal als Tabelle mit caption; zwei Codefelder mit eigenem
    Label; „Stornieren“ als gefährlicher Knopf; die Fehlerliste eines Stornos verlinkt
    #grund-s; ?code=wiederherstellung schaltet beide Codefelder um."""
    import re

    b = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 1))
    client = qw.web.angemeldet("jan")
    html = client.get(f"/buchungen/{b.id}").text
    assert '<caption class="unsichtbar">Journal</caption>' in html
    assert '<table class="tabelle" role="table">' in html
    for ident in ("einmalcode-k", "einmalcode-s"):
        assert f'<label for="{ident}">Code aus Ihrer Authenticator-App</label>' in html
        assert re.search(rf'<input id="{ident}"[^>]*inputmode="numeric"', html)
    assert 'class="knopf knopf-gefaehrlich">Stornieren</button>' in html
    assert 'class="knopf knopf-primaer">Korrigieren</button>' in html
    assert '<dl class="angaben">' in html
    variante = client.get(f"/buchungen/{b.id}?code=wiederherstellung").text
    assert variante.count('<label for="einmalcode-') == 2
    assert variante.count(">Wiederherstellungscode</label>") == 2
    seite = client.get(f"/buchungen/{b.id}").text
    r = client.post(
        f"/buchungen/{b.id}/stornieren",
        data={
            "csrf": csrf(client),
            "stand": formularwert(seite, "stand"),
            "einmalcode": qw.web.personen["jan"].codes[-1],
            "grund": " ",
        },
    )
    assert r.status_code == 422
    assert '<a href="#grund-s">' in r.text and 'role="alert"' in r.text
