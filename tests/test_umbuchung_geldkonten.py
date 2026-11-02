"""Umbuchungen zwischen eigenen Geldkonten (Gesamttest 10b-1 nach dem Merge, H-1).

Eine Umbuchung Giro ↔ Tagesgeld steht auf beiden Kontoauszügen. Aus ihr wird keine
Regel (sie buchte künftige Umsätze mit demselben Konto im Soll und im Haben), und eine
Buchung mit Soll = Haben entsteht auf keinem Weg automatisch — weder aus gelernter
Regel, Regeldatei, Standardregel, Gegenrichtung noch LLM: Der Umsatz bleibt offen,
der Lauf nennt ihn. ``accounti pruefen`` meldet Altfälle (Prüfregel
``soll_gleich_haben``).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.buchung.mit_beleg import kontiere_beleg, sachkonto_fuer_beleg
from accounti.cli import app
from accounti.db import session_factory
from accounti.db.repo_kontierung import speichere_regel
from accounti.db.repository import (
    lade_buchungen,
    speichere_abgleich,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine, Regel, RegelwerkEngine
from accounti.klassifikation.lernen import (
    RegelError,
    entwurf_fuer,
    lade_regelwerk,
    lerne_regex,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Belegabgleich,
    BuchungStatus,
    Transaktion,
)
from accounti.models.kontierung import Kontierungsregel, RegelHerkunft, Richtung
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    db_url,
    kontakt,
    kurz,
    make_session_fixture,
    umsatz,
)

BH = Buchhaltung()
SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800", standard_aufwand="6300")
runner = CliRunner()


def uebertrag(betrag: str, tag: date = date(2026, 10, 2), **kw: object) -> Transaktion:
    werte: dict[str, object] = {"zweck": "Übertrag Tagesgeld", "name": "Probe GmbH"}
    werte.update(kw)
    return umsatz(betrag, tag, str(werte.pop("zweck")), str(werte.pop("name")), **werte)


def altregel(soll: str, haben: str, richtung: Richtung | None = Richtung.AUSGABE):  # noqa: ANN201
    """Gelernte Regel, wie sie vor der Korrektur entstand (an ``lerne`` vorbei)."""
    return Kontierungsregel(
        name=f"gelernt_alt_{soll}_{haben}",
        muster="Probe GmbH",
        ist_text=True,
        feld="beide",
        richtung=richtung,
        soll_konto=soll,
        haben_konto=haben,
        herkunft=RegelHerkunft.KORREKTUR,
        angelegt_von="jan",
        angelegt_am=datetime(2026, 9, 1, 12, 0),
    )


def kontiere(make_session, werk=None, llm=None, bh: Buchhaltung = BH):  # noqa: ANN001, ANN201
    with make_session() as s:
        engine = KlassifikationsEngine(
            regelwerk=werk or lade_regelwerk(s, None, "automatisch", buchhaltung=bh),
            llm=llm,
        )
        lauf = kontiere_umsaetze(s, engine, bh)
        s.commit()
        return lauf, lade_buchungen(s)


# --- (a) keine Regel aus einer Umbuchung ----------------------------------------------


@pytest.mark.parametrize(
    ("tx", "soll", "haben"),
    [
        (uebertrag("-300.00", sachkonto="1210"), "1200", "1210"),  # Probe s2 b
        (uebertrag("300.00", sachkonto="1210"), "1210", "1200"),
        (uebertrag("-400.00"), "1210", "1200"),  # auf dem Giro (Variante c)
        (uebertrag("-50.00", sachkonto="1730", zweck="Karte"), "1200", "1730"),
        (uebertrag("-200.00", zweck="Bareinzahlung"), "1000", "1200"),  # Kasse
    ],
)
def test_aus_einer_umbuchung_wird_keine_regel(tx, soll, haben):
    with pytest.raises(RegelError, match="Geldkonten") as info:
        entwurf_fuer(tx, soll, haben, None, BH)
    assert info.value.feld == "regel"
    assert "Umbuchung" in str(info.value)


def test_umbuchung_im_skr04_und_eingerichtete_konten():
    with pytest.raises(RegelError, match="Geldkonten"):
        entwurf_fuer(uebertrag("-10.00"), "1810", "1800", None, SKR04)
    # Konto außerhalb der Bereiche des Kontenrahmens, aber als Bankkonto eingerichtet
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen

    kr = lade_kontenrahmen("SKR03").mit_geldkonten(["1370"])
    entwurf_fuer(uebertrag("-10.00"), "1370", "1200", None, BH)  # sonst kein Geldkonto
    with pytest.raises(RegelError, match="Geldkonten"):
        entwurf_fuer(uebertrag("-10.00"), "1370", "1200", None, BH, kontenrahmen=kr)


@pytest.mark.parametrize(
    ("soll", "haben", "bh"),
    [
        ("4930", "1200", BH),
        ("1600", "1200", BH),  # Verbindlichkeiten (Sammelkonto) ist kein Zahlungsmittel
        ("70001", "1200", BH),  # Kreditor
        ("1400", "1200", BH),  # Forderungen
        ("6815", "1800", SKR04),
        ("3300", "1800", SKR04),  # Verbindlichkeiten SKR04
    ],
)
def test_andere_regeln_bleiben_lernbar(soll, haben, bh):
    e = entwurf_fuer(uebertrag("-10.00"), soll, haben, 9, bh)
    assert (e.soll_konto, e.haben_konto) == (soll, haben)


def test_lerne_regex_lehnt_umbuchung_ab(make_session):
    with make_session() as s:
        with pytest.raises(RegelError, match="Geldkonten") as info:
            lerne_regex(s, "tagesgeld", "tagesgeld", "1210", "1200", None, "jan",
                        buchhaltung=BH)  # fmt: skip
        assert info.value.feld == "regel"
        r = lerne_regex(s, "telekom", "telekom", "4920", "1200", 9, "jan",
                        buchhaltung=BH)  # fmt: skip
    assert r.soll_konto == "4920"


# --- (b) nie Soll = Haben automatisch ----------------------------------------------


def test_regeldatei_umbuchung_auf_dem_zweiten_konto_bleibt_offen(
    make_session, tmp_path
):
    """Probe s2 a: Regel „1210 an 1200“ ohne Richtung auf Umsätzen des Tagesgelds
    ergab „1210 an 1210 auto“. Auf dem Giro bucht sie wie bisher."""
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: tagesgeld\n  muster: 'Übertrag Tagesgeld'\n  feld: verwendungszweck\n"
        "  soll_konto: '1210'\n  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    giro = uebertrag("-500.00", date(2026, 9, 1))
    rein = uebertrag("500.00", date(2026, 9, 1), sachkonto="1210")
    raus = uebertrag("-200.00", date(2026, 9, 15), sachkonto="1210")
    anlegen(make_session, giro, rein, raus)
    with make_session() as s:
        werk = lade_regelwerk(s, datei, "automatisch", buchhaltung=BH)
    lauf, buchungen = kontiere(make_session, werk)
    assert [(b.transaktion_id, b.soll_konto, b.haben_konto) for b in buchungen] == [
        (giro.id, "1210", "1200")
    ]
    assert lauf.offen == 2 and lauf.kontiert == 1
    assert len(lauf.umbuchungen) == 2
    assert all("1210 an 1210" in h and "tagesgeld" in h for h in lauf.umbuchungen)


@pytest.mark.parametrize(
    ("soll", "haben", "offen"),
    [
        # Probe s2 b: aus der Korrektur auf dem Tagesgeld — auch auf dem Giro
        ("1200", "1200", 4),
        # Probe s2 c: auf dem Giro gelernt — auf dem Giro richtig, sonst offen
        ("1210", "1200", 3),
    ],
)
def test_alte_gelernte_umbuchungsregeln_buchen_nie_soll_gleich_haben(
    make_session, soll, haben, offen
):
    """Gelernte Regeln aus Umbuchungen (vor der Korrektur entstanden): auf beiden
    Konten, auch als Gegenbuchung, bleibt der Umsatz offen statt Soll = Haben."""
    with make_session() as s:
        speichere_regel(s, altregel(soll, haben))
        s.commit()
    umsaetze = [
        uebertrag("-300.00", date(2026, 10, 2), sachkonto="1210"),
        uebertrag("-150.00", date(2026, 10, 3), sachkonto="1210"),
        uebertrag("400.00", date(2026, 10, 4), sachkonto="1210"),  # Gegenrichtung
        uebertrag("-300.00", date(2026, 10, 5)),  # Giro
    ]
    anlegen(make_session, *umsaetze)
    lauf, buchungen = kontiere(make_session)
    assert not [b for b in buchungen if b.soll_konto == b.haben_konto]
    assert lauf.offen == offen and len(lauf.umbuchungen) == offen
    assert len(buchungen) == 4 - offen


def test_llm_vorschlag_mit_soll_gleich_haben_bleibt_offen(make_session):
    from tests.pruefen_hilfe import LLMAttrappe

    tx = uebertrag("-80.00", sachkonto="1210", zweck="irgendwas", name="Niemand")
    anlegen(make_session, tx)
    lauf, buchungen = kontiere(
        make_session, RegelwerkEngine([]), llm=LLMAttrappe(soll="1210")
    )
    assert buchungen == [] and lauf.offen == 1
    assert "1210 an 1210" in lauf.umbuchungen[0]


def test_belegbuchung_nimmt_kein_geld_oder_personenkonto_als_sachkonto(make_session):
    """Belegbuchung (Umsatz mit Beleg) und OPOS: Eine Regel „1210 an 1200“ oder
    „70001 an 1200“ liefert kein Aufwandskonto — sonst „1210 an 1210“ bzw. „70001 an
    70001“."""
    for soll in ("1210", "1200", "70001", "1600"):
        werk = RegelwerkEngine(
            [
                Regel.aus_text(
                    "r", "Stadtwerke", soll, "1200", richtung="ausgabe", feld="beide"
                )
            ]
        )
        sk = sachkonto_fuer_beleg(beleg(), None, BH, werk)
        assert (sk.konto, sk.pruefen, sk.regel) == ("4900", True, None), soll
        tx = umsatz("-119.00", sachkonto="1210")
        k = kontiere_beleg(tx, beleg(), BH, werk)
        assert all(b.soll_konto != b.haben_konto for b in k.buchungen)
        assert {b.status for b in k.buchungen} == {BuchungStatus.ZUR_PRUEFUNG}


def test_kontakt_mit_geldkonto_als_sachkonto_wird_uebergangen():
    k = kontakt(sachkonto="1200")
    sk = sachkonto_fuer_beleg(beleg(), k, BH, RegelwerkEngine([]))
    assert sk.konto == "4900" and sk.pruefen


def test_opos_verbuchen_mit_kreditorregel_bucht_nicht_kreditor_an_kreditor(
    make_session,
):
    from accounti.opos.verbuchung import verbuche_beleg

    b = beleg()
    anlegen(make_session, kontakt(), b)
    werk = RegelwerkEngine(
        [
            Regel.aus_text(
                "r", "Stadtwerke", "70001", "1200", richtung="ausgabe", feld="beide"
            )
        ]
    )
    with make_session() as s:
        v = verbuche_beleg(s, b, BH, regelwerk=werk)
        s.commit()
    assert [(x.soll_konto, x.haben_konto) for x in v.buchungen] == [("4900", "70001")]
    assert {x.status for x in v.buchungen} == {BuchungStatus.ZUR_PRUEFUNG}


def test_umsatz_mit_beleg_und_umbuchungsregel_bleibt_ohne_soll_gleich_haben(
    make_session,
):
    """Belegweg im Kontierungslauf: dieselbe Schranke wie für Regel und LLM."""
    tx = umsatz("-119.00", sachkonto="1210")
    b = beleg()
    anlegen(make_session, tx, b)
    with make_session() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=b.id,
                stufe="referenz",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="x",
            ),
        )
        speichere_regel(
            s, altregel("1210", "1200").model_copy(update={"muster": "Stadtwerke"})
        )
        s.commit()
    _, buchungen = kontiere(make_session)
    assert buchungen and all(x.soll_konto != x.haben_konto for x in buchungen)


# --- Läufe: classify, bank lauf, REST ------------------------------------------------


@pytest.fixture
def url(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    u = db_url(tmp_path)
    engine, fabrik = session_factory(u)
    from accounti.db import init_db

    init_db(engine)
    with fabrik() as s:
        speichere_regel(s, altregel("1200", "1200"))
        speichere_transaktion(s, uebertrag("-300.00", sachkonto="1210"))
        s.commit()
    engine.dispose()
    return u


def _buchungen(u: str):  # noqa: ANN202
    engine, fabrik = session_factory(u)
    with fabrik() as s:
        ergebnis = lade_buchungen(s)
    engine.dispose()
    return ergebnis


def test_classify_meldet_die_offene_umbuchung(url):
    r = runner.invoke(
        app, ["classify", "--no-llm", "--db", url], env={"COLUMNS": "250"}
    )
    assert r.exit_code == 0, r.output
    assert "1 offen" in r.output and "Soll = Haben" in r.output
    assert "1210 an 1210" in r.output
    assert _buchungen(url) == []


def test_bank_lauf_bleibt_offen(url):
    from accounti.bank.einstellungen import BankEinstellungen
    from accounti.bank.lauf import bank_lauf

    engine, fabrik = session_factory(url)
    with fabrik() as s:
        werk = lade_regelwerk(s, None, "automatisch", buchhaltung=BH)
        e = bank_lauf(
            s,
            KlassifikationsEngine(regelwerk=werk),
            BH,
            bank_einstellungen=BankEinstellungen(),
        )
        s.commit()
    engine.dispose()
    assert e.kontierung.offen == 1 and len(e.kontierung.umbuchungen) == 1
    assert _buchungen(url) == []


def test_rest_lauf_bleibt_offen_und_meldet_die_umbuchung(tmp_path, monkeypatch):
    from accounti.models.auth import TokenRecht
    from tests.api_hilfe import webwelt
    from tests.auth_hilfe import billige_hashes

    billige_hashes(monkeypatch)
    welt = webwelt(tmp_path)
    u = welt.umgebung.db["a"]
    engine, fabrik = session_factory(u)
    with fabrik() as s:
        speichere_regel(s, altregel("1210", "1200"))
        speichere_transaktion(s, uebertrag("-150.00", sachkonto="1210"))
        s.commit()
    token = welt.token("a", TokenRecht.LAEUFE_STARTEN)
    r = welt.client().post(
        "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    k = r.json()["kontierung"]
    assert (k["kontiert"], k["offen"], k["umbuchung"]) == (0, 1, 1)
    with fabrik() as s:
        assert lade_buchungen(s) == []
    engine.dispose()


# --- CLI: korrigiere --lernen, lerne -------------------------------------------------


def test_cli_korrigiere_lernen_aus_umbuchung_ohne_regel(tmp_path, monkeypatch):
    """Probe s2 b: bisher Exit 0 „Regel gelernt“, gespeichert „1200 an 1200“. Nach
    H-1 verwarf ``--lernen`` auch die Korrektur (gw2-merge B2) — jetzt gilt sie, nur
    ohne Regel, mit Hinweis (Runde 3)."""
    from accounti.db import init_db
    from accounti.db.repo_kontierung import lade_kontierungsregeln

    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    u = db_url(tmp_path)
    engine, fabrik = session_factory(u)
    init_db(engine)
    tx = uebertrag("-300.00", sachkonto="1210", zweck="Übertrag auf Giro")
    b = buchung(tx, soll="4900", haben="1210", schluessel=None, steuer=None)
    anlegen(fabrik, tx, b)
    befehl = ["korrigiere", kurz(b.id), "--soll", "1200", "--haben", "1210"]
    r = runner.invoke(app, [*befehl, "--lernen", "--grund", "Umbuchung", "--db", u],
                      env={"COLUMNS": "250"})  # fmt: skip
    assert r.exit_code == 0 and "Korrigiert" in r.output, r.output
    assert "Keine Regel gelernt" in r.output and "Geldkonten" in r.output
    with fabrik() as s:
        assert lade_kontierungsregeln(s) == []
        (x,) = lade_buchungen(s)
        assert (x.soll_konto, x.haben_konto) == ("1200", "1210")
    engine.dispose()


def test_cli_lerne_umbuchung_exit_1(url):
    r = runner.invoke(
        app,
        ["lerne", "--muster", "tagesgeld", "--soll", "1210", "--haben", "1200",
         "--name", "tagesgeld", "--db", url],
    )  # fmt: skip
    assert r.exit_code == 1 and "Geldkonten" in r.output, r.output


# --- Browser: Queue und Regelvorschau ------------------------------------------------


def test_web_korrektur_mit_regel_aus_umbuchung_ohne_regel(tmp_path, monkeypatch):
    """Die Regelvorschau lehnt ab (422); speichern mit Haken „Regel“ korrigiert ohne
    Regel und sagt es (Runde 3, gw2-merge B2: vorher 422, Korrektur verworfen)."""
    from accounti.db.repo_kontierung import lade_kontierungsregeln
    from tests.api_hilfe import csrf
    from tests.auth_hilfe import billige_hashes
    from tests.pruefen_hilfe import queuewelt, stand_aus

    billige_hashes(monkeypatch)
    qw = queuewelt(tmp_path)
    b = qw.unsicher(betrag="-300.00", zweck="Übertrag auf Giro", name="Probe GmbH",
                    sachkonto="1210")  # fmt: skip
    qw.unsicher(betrag="-20.00", zweck="RE 4721", name="Bürobedarf Müller")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {"csrf": csrf(client), "soll": "1200", "haben": "1210", "steuer": "ohne",
             "muster": "Probe GmbH", "feld": "beide"}  # fmt: skip
    r = client.post(f"/pruefen/{b.id}/regelvorschau", data=daten,
                    headers={"HX-Request": "true"})  # fmt: skip
    assert r.status_code == 422 and "Geldkonten" in r.text
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={**daten, "csrf": csrf(client), "stand": stand_aus(seite), "regel": "1"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200 and "Keine Regel gelernt" in r.text, r.text
    with qw.fabrik()() as s:
        assert lade_kontierungsregeln(s) == []
        x = next(x for x in lade_buchungen(s) if x.id == b.id)
        assert (x.soll_konto, x.haben_konto) == ("1200", "1210")


# --- (c) Prüfregel für Altfälle -----------------------------------------------------


def test_pruefen_meldet_buchungen_mit_soll_gleich_haben(make_session):
    from accounti.models.pruefung import Schwere
    from tests.test_pruefung_regeln import pruefe

    tx = uebertrag("-300.00", sachkonto="1210")
    alt = buchung(tx, soll="1210", haben="1210", schluessel=None, steuer=None,
                  status=BuchungStatus.AUTO_GEBUCHT)  # fmt: skip
    gut = buchung(soll="4930", haben="1200")
    anlegen(make_session, tx, alt, gut)
    (befund,) = pruefe(make_session, "soll_gleich_haben")
    assert befund.objekt_id == str(alt.id) and befund.schwere is Schwere.FEHLER
    assert "1210 an 1210" in befund.text
    assert befund.abhilfe and f"korrigiere {kurz(alt.id)}" in befund.abhilfe


def test_pruefregel_uebergeht_stornierte(make_session):
    from accounti.pruefung.storno import storniere
    from tests.test_pruefung_regeln import pruefe

    tx = uebertrag("-300.00", sachkonto="1210")
    alt = buchung(tx, soll="1210", haben="1210", schluessel=None, steuer=None,
                  status=BuchungStatus.GEPRUEFT)  # fmt: skip
    anlegen(make_session, tx, alt)
    with make_session() as s:
        storniere(s, str(alt.id), grund="Umbuchung", von="jan")
        s.commit()
    assert pruefe(make_session, "soll_gleich_haben") == []


# --- Runde 3: enge Ausnahme der Sachkonten, Geldtransit, alte Zuordnung --------------


@pytest.mark.parametrize(
    ("konto", "bh"),
    [
        ("1348", BH),  # sonstige Wertpapiere (§ 266 Abs. 2 B III HGB)
        ("1290", BH),  # Finanzmittelanlagen
        ("1355", BH),  # Rückdeckungsversicherung
        ("1370", BH),  # Verrechnungskonto
        ("1890", SKR04),  # Finanzmittelanlagen
        ("1510", SKR04),  # Wertpapiere
    ],
)
def test_bestandskonten_bleiben_sachkonto_eines_belegs(konto, bh):
    """gegen:umbuchung:0: Der breite Bereich ``geldkonten`` (SKR03 1000–1399, SKR04
    1600–1899) verwarf legitime Sachkonten — der Wertpapiersparplan mit Abrechnung
    ging jedes Mal als Aufwand zur Prüfung, das gelernte Sachkonto wirkte nie."""
    bank = bh.bank_konto
    regel = Regel.aus_text(
        "depot", "Stadtwerke", konto, bank, richtung="ausgabe", feld="beide"
    )
    werk = RegelwerkEngine([regel])
    sk = sachkonto_fuer_beleg(beleg(), None, bh, werk)
    assert (sk.konto, sk.regel) == (konto, "depot")
    sk = sachkonto_fuer_beleg(beleg(), kontakt(sachkonto=konto), bh, None)
    assert sk.konto == konto


def test_uebergangenes_sachkonto_steht_in_der_begruendung():
    sk = sachkonto_fuer_beleg(beleg(), kontakt(sachkonto="1200"), BH, None)
    assert sk.konto == "4900" and "übergangen: 1200 (Kontakt" in sk.quelle


def test_lerne_sachkonto_lehnt_geldkonto_ab_korrektur_bleibt(make_session):
    """Lernen meldete „Gelernt“, die nächste Belegbuchung überging das Konto — jetzt
    ein Hinweis statt des Lernens; die Korrektur selbst gilt."""
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen
    from accounti.buchung.pruefschlange import Aenderung, LernWunsch, korrigieren
    from accounti.db.repository import lade_kontakte
    from accounti.opos.verbuchung import verbuche_beleg
    from accounti.pruefung.einstellungen import PruefEinstellungen
    from accounti.pruefung.storno import Korrekturumgebung

    b = beleg()
    anlegen(make_session, kontakt(), b)
    with make_session() as s:
        v = verbuche_beleg(s, b, BH, regelwerk=RegelwerkEngine([]))
        s.commit()
    (x,) = v.buchungen
    umgebung = Korrekturumgebung(lade_kontenrahmen("SKR03"), BH, PruefEinstellungen())
    with make_session() as s:
        e = korrigieren(
            s, x.id, Aenderung("1200", "70001", ohne_steuer=True, grund="Test"),
            "jan", None, umgebung, lernen=LernWunsch(),
        )  # fmt: skip
        s.commit()
        (k,) = lade_kontakte(s)
    assert e.gelernt is None and k.sachkonto is None
    assert any("nicht als Vorschlag" in w for w in e.korrektur.warnungen)
    with make_session() as s:
        e = korrigieren(
            s, x.id, Aenderung("1348", "70001", ohne_steuer=True, grund="Depot"),
            "jan", None, umgebung, lernen=LernWunsch(), nur_vorschlaege=False,
        )  # fmt: skip
        s.commit()
        (k,) = lade_kontakte(s)
    assert e.gelernt is not None and k.sachkonto == "1348"


@pytest.mark.parametrize(
    ("betrag", "soll", "haben", "bh"),
    [
        ("-500.00", "1360", "1200", BH),
        ("500.00", "1200", "1360", BH),
        ("-500.00", "1460", "1800", SKR04),
    ],
)
def test_regel_gegen_geldtransit_bleibt_lernbar(betrag, soll, haben, bh):
    """gw2-umbuchung N-2: Geldtransit hat keinen eigenen Kontoauszug — eine Regel
    dagegen bucht auf keinem Konto Soll = Haben."""
    e = entwurf_fuer(uebertrag(betrag), soll, haben, None, bh)
    assert (e.soll_konto, e.haben_konto) == (soll, haben)


def test_alte_kontenzuordnung_ohne_zahlungsmittel_nimmt_die_mitgelieferten(tmp_path):
    """gw2-umbuchung N-1: Eine eigene Zuordnung älterer Fassung (ohne Abschnitt
    ``zahlungsmittel``) machte Kasse, Geldtransit und Karte zu Nicht-Zahlungsmitteln
    — die Regel „1000 an 1200“ wurde gelernt, die Vorschau lehnte sie ab."""
    import yaml

    from accounti.abschluss.kontenrahmen import lade_kontenrahmen

    daten = yaml.safe_load(
        (
            Path(__file__).parents[1] / "src/accounti/abschluss/kontenrahmen_skr03.yaml"
        ).read_text(encoding="utf-8")
    )
    for abschnitt in ("zahlungsmittel", "geldtransit", "lul_konten"):
        daten.pop(abschnitt)
    datei = tmp_path / "zuordnung.yaml"
    datei.write_text(yaml.safe_dump(daten), encoding="utf-8")
    kr = lade_kontenrahmen("SKR03", datei)
    assert kr.zahlungsmittel is None
    assert all(kr.ist_zahlungsmittel(k) for k in ("1000", "1200", "1360", "1730"))
    assert kr.ist_geldtransit("1360") and kr.ist_lul_konto("1400")
    for soll in ("1000", "1730"):
        with pytest.raises(RegelError, match="Geldkonten"):
            entwurf_fuer(uebertrag("-10.00"), soll, "1200", None, BH, kontenrahmen=kr)
