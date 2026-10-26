"""Lernschleife in der Datenbank: Richtung, Vorrang, Schalter, Vorschau, Journal
(Baustein 10b, Paket 1)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db.repo_kontierung import (
    lade_kontierungsgrund,
    lade_kontierungsregeln,
)
from accounti.db.repository import (
    lade_buchungen,
    lade_kontakt,
    speichere_buchung,
    speichere_posten,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine, Regel, RegelwerkEngine
from accounti.klassifikation.lernen import (
    RegelError,
    deaktiviere,
    entwurf_aus_korrektur,
    entwurf_fuer,
    lade_regelwerk,
    lerne,
    lerne_regex,
    lerne_sachkonto,
    pruefe_entwurf,
    uebernehme_aus_datei,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus, OffenerPosten, PostenRichtung, Transaktion
from accounti.models.kontierung import RegelHerkunft, Richtung
from accounti.pruefung.journal import lade_journal, pruefe_journal
from accounti.pruefung.person import journal_kontext
from accounti.pruefung.storno import korrigiere
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    kontakt,
    make_session_fixture,
    umsatz,
)

BH = Buchhaltung()
HEUTE = date(2026, 10, 21)


def mueller(betrag: str = "-59.50", tag: date = date(2026, 10, 1), **kw) -> Transaktion:  # noqa: ANN003
    werte = {"zweck": "RE 4711 Büromaterial", "name": "Bürobedarf Müller GmbH"}
    werte.update(kw)
    return umsatz(betrag, tag, werte.pop("zweck"), werte.pop("name"), **werte)


def lerne_mueller(s, **kw):  # noqa: ANN001, ANN003, ANN201
    tx = mueller()
    entwurf = entwurf_fuer(tx, "4930", "1200", 9, BH, **kw)
    return lerne(s, entwurf, "jan")


# --- Journal --------------------------------------------------------------------------


def test_lernen_im_journal_mit_person(make_session):
    with make_session() as s, journal_kontext(person="jan", geprueft=True):
        r = lerne_mueller(s)
        s.commit()
    with make_session() as s:
        eintraege = lade_journal(s, objekt_id=str(r.id))
    assert [e.vorgang for e in eintraege] == ["regel_gelernt"]
    assert (
        eintraege[0].person == "jan" and eintraege[0].objekt_typ == "kontierungsregel"
    )
    nachher = json.loads(eintraege[0].nachher or "{}")
    assert nachher["muster"] == "Bürobedarf Müller" and nachher["richtung"] == "ausgabe"


def test_an_accounti_vorbei_geaenderte_regel_meldet_journal_pruefen(make_session):
    with make_session() as s:
        r = lerne_mueller(s)
        s.commit()
    with make_session() as s:
        assert pruefe_journal(s).in_ordnung
        s.rollback()
        s.execute(text("UPDATE kontierungsregeln SET soll_konto = '4980'"))
        s.commit()
    with make_session() as s:
        p = pruefe_journal(s)
    assert not p.in_ordnung
    assert any(
        b.art == "abweichung" and b.objekt == str(r.id) and "soll_konto" in b.text
        for b in p.befunde
    )


def test_verlauf_einer_regel(make_session):
    with make_session() as s:
        r = lerne_mueller(s)
        s.commit()
    with make_session() as s, journal_kontext(person="eva", geprueft=True):
        deaktiviere(s, r.id, "eva", "trifft auch Privatkäufe")
        s.commit()
    with make_session() as s:
        eintraege = lade_journal(s, objekt_id=str(r.id))
        assert pruefe_journal(s).in_ordnung
    assert [(e.vorgang, e.person) for e in eintraege] == [
        ("regel_gelernt", "jan"),
        ("regel_deaktiviert", "eva"),
    ]
    assert eintraege[1].grund == "trifft auch Privatkäufe"


# --- Richtung -------------------------------------------------------------------------


def test_gelernte_regel_nur_in_ihrer_richtung(make_session):
    """Eine aus einer Ausgabe gelernte Regel bucht die Erstattung derselben
    Gegenpartei nicht als Geldabgang (Befund 13)."""
    with make_session() as s:
        lerne_mueller(s)
        s.commit()
        werk = lade_regelwerk(s, None, "automatisch")
    e = werk.klassifiziere(mueller("-12.00"))
    assert e is not None and e.regel == "gelernt_bürobedarf_müller"
    assert werk.klassifiziere(mueller("12.00", zweck="Gutschrift")) is None


def test_yaml_regel_ohne_richtung_wie_bisher(tmp_path):
    from accounti.klassifikation.regeln_loader import lade_regeln

    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: telekom\n  muster: telekom\n  feld: beide\n  soll_konto: '4920'\n"
        "  haben_konto: '1200'\n- name: erstattung\n  muster: rueck\n"
        "  richtung: einnahme\n  soll_konto: '1200'\n  haben_konto: '4920'\n",
        encoding="utf-8",
    )
    ohne, mit = lade_regeln(datei)
    assert ohne.richtung is None and mit.richtung == "einnahme"
    assert ohne.passt(mueller("-10.00", zweck="Telekom")) and ohne.passt(
        mueller("10.00", zweck="Telekom")
    )
    assert mit.passt(mueller("10.00", zweck="rueck")) and not mit.passt(
        mueller("-10.00", zweck="rueck")
    )


def test_belegdaten_passen_zu_ausgaberegel(make_session):
    """Belegdaten laufen als Pseudo-Ausgabe (negativer Betrag) durchs Regelwerk."""
    from accounti.buchung.mit_beleg import sachkonto_fuer_beleg

    with make_session() as s:
        lerne(
            s,
            entwurf_fuer(mueller(), "4930", "1200", 9, BH, muster="Stadtwerke"),
            "jan",
        )
        s.commit()
        werk = lade_regelwerk(s, None, "automatisch")
    sk = sachkonto_fuer_beleg(beleg(), None, BH, werk)
    assert sk.konto == "4930" and sk.regel == "gelernt_stadtwerke"


# --- Vorrang und Schalter -------------------------------------------------------------


def _eigene(tmp_path: Path) -> Path:
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "# eigene Regeln — Kommentar bleibt\n"
        "- name: buero_falsch\n  muster: 'b(ü|ue)ro'\n  feld: beide\n"
        "  soll_konto: '4980'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n",
        encoding="utf-8",
    )
    return datei


def test_reihenfolge_gelernt_eigene_standard(make_session, tmp_path):
    with make_session() as s:
        lerne_mueller(s)
        s.commit()
        werk = lade_regelwerk(s, _eigene(tmp_path), "automatisch")
    namen = [r.name for r in werk.regeln]
    assert namen[0] == "gelernt_bürobedarf_müller" and namen[1] == "buero_falsch"
    assert namen[2:] == [r.name for r in RegelwerkEngine().regeln]


def test_gelernte_regel_schlaegt_falsch_treffende_eigene_regel(make_session, tmp_path):
    """Regression zu Befund 5: angehängt ans Dateiende griff die gelernte Regel nie."""
    eigene = _eigene(tmp_path)
    with make_session() as s:
        werk = lade_regelwerk(s, eigene, "automatisch")
        assert werk.klassifiziere(mueller()).soll_konto == "4980"  # type: ignore[union-attr]
        lerne_mueller(s)
        s.commit()
        werk = lade_regelwerk(s, eigene, "automatisch")
    e = werk.klassifiziere(mueller(tag=date(2026, 10, 15)))
    assert e is not None and e.soll_konto == "4930" and e.confidence == 1.0
    assert e.regel == "gelernt_bürobedarf_müller"


def test_deaktivierte_regel_greift_nicht(make_session):
    with make_session() as s:
        r = lerne_mueller(s)
        deaktiviere(s, r.id, "jan", "falsch")
        s.commit()
        werk = lade_regelwerk(s, None, "automatisch")
    e = werk.klassifiziere(mueller())
    assert e is None or not (e.regel or "").startswith("gelernt_")


def test_schalter_pruefen_legt_vor(make_session):
    with make_session() as s:
        lerne_mueller(s)
        tx = mueller(tag=date(2026, 10, 15))
        speichere_transaktion(s, tx)
        s.commit()
    with make_session() as s:
        engine = KlassifikationsEngine(regelwerk=lade_regelwerk(s, None, "pruefen"))
        kontiere_umsaetze(s, engine, BH)
        s.commit()
        (b,) = lade_buchungen(s)
        grund = lade_kontierungsgrund(s, b.id)
    assert b.status is BuchungStatus.ZUR_PRUEFUNG and b.confidence == 0.9
    assert grund is not None and "Einstellung: prüfen" in grund.begruendung


def test_schalter_pruefen_gilt_auch_fuer_belegbuchungen(make_session):
    """Nachbesserung M2 (Probe p7): Mit ``gelernte_regeln: pruefen`` legt eine
    gelernte Regel auch eine Belegbuchung (Umsatz mit Beleg, OPOS) nur vor — das
    Sachkonto kommt aus der Regel, gebucht wird zur Prüfung."""
    from accounti.buchung.mit_beleg import kontiere_beleg, sachkonto_fuer_beleg

    with make_session() as s:
        lerne(
            s,
            entwurf_fuer(mueller(), "4930", "1200", 9, BH, muster="Stadtwerke"),
            "jan",
        )
        s.commit()
        pruefen = lade_regelwerk(s, None, "pruefen")
        automatisch = lade_regelwerk(s, None, "automatisch")
    sk = sachkonto_fuer_beleg(beleg(), None, BH, pruefen)
    assert sk.konto == "4930" and sk.pruefen and "Einstellung: prüfen" in sk.quelle
    assert not sachkonto_fuer_beleg(beleg(), None, BH, automatisch).pruefen
    tx = umsatz("-119.00", date(2026, 8, 12), "RE-2026-0815", "Stadtwerke Hamburg")
    k = kontiere_beleg(tx, beleg(), BH, pruefen)
    assert {(b.soll_konto, b.status) for b in k.buchungen} == {
        ("4930", BuchungStatus.ZUR_PRUEFUNG)
    }
    assert k.regel == "gelernt_stadtwerke" and "Einstellung: prüfen" in k.begruendung
    frei = kontiere_beleg(tx, beleg(), BH, automatisch)
    assert {b.status for b in frei.buchungen} == {BuchungStatus.AUTO_GEBUCHT}


def test_schalter_aus_laedt_keine_gelernten(make_session):
    with make_session() as s:
        lerne_mueller(s)
        s.commit()
        werk = lade_regelwerk(s, None, "aus")
    assert not any(r.name.startswith("gelernt_") for r in werk.regeln)


# --- Entwurf --------------------------------------------------------------------------


def test_entwurf_ganzer_name_sonst_erstes_wort_des_zwecks():
    """(umgestellt, Nachbesserung H1) Vorschlag ist der ganze Name der Gegenpartei
    ohne Rechtsform — das erste Wort („Deutsche“) träfe fremde Gegenparteien. Ohne
    Namen bleibt es beim ersten Wort des Verwendungszwecks."""
    assert entwurf_fuer(mueller(), "4930", "1200", 9, BH).muster == "Bürobedarf Müller"
    kurz = mueller(name="AB Spedition KG")
    assert entwurf_fuer(kurz, "4930", "1200", 9, BH).muster == "AB Spedition"
    ohne_namen = mueller(name=None, zweck="Telekom. Rechnung 10/2026")
    assert entwurf_fuer(ohne_namen, "4920", "1200", 9, BH).muster == "Telekom"


@pytest.mark.parametrize(
    ("name", "muster"),
    [
        ("Deutsche Telekom AG", "Deutsche Telekom"),
        ("Bürobedarf Müller GmbH & Co. KG", "Bürobedarf Müller"),
        ("PayPal Europe S.a.r.l. et Cie S.C.A", "PayPal Europe"),
        ("Amazon EU S.à r.l.", "Amazon EU"),
        ("Müller e. K.", "Müller"),
        ("Deutsche Rentenversicherung", "Deutsche Rentenversicherung"),
        ("Muster UG (haftungsbeschränkt)", "Muster"),
    ],
)
def test_mustervorschlag_ohne_rechtsform(name, muster):
    from accounti.klassifikation.lernen import vorschlag_muster

    assert vorschlag_muster(mueller(name=name)) == muster


def test_mustervorschlag_hoechstens_100_zeichen():
    from accounti.klassifikation.lernen import pruefe_text, vorschlag_muster

    lang = " ".join(["Wort"] * 40) + " GmbH"
    muster = vorschlag_muster(mueller(name=lang))
    assert len(muster) <= 100 and pruefe_text(muster) == muster


def test_text_muster_mit_mehrfachem_leerraum():
    r = Regel.aus_text("t", "Deutsche Telekom", "4920", "1200", feld="beide")
    assert r.passt(mueller(name="DEUTSCHE  TELEKOM AG"))
    assert not r.passt(mueller(name="Deutsche Telekomik"))


def test_entwurf_behaelt_das_finanzkonto_auf_seiner_seite():
    """Nachbesserung M1: Die Regel bucht künftige Umsätze über ihr Finanzkonto —
    eine Ausgabe im Haben, eine Einnahme im Soll."""
    for soll, haben, feld in (("4930", "4980", "haben"), ("1200", "4930", "haben")):
        with pytest.raises(RegelError, match="Finanzkonto 1200") as info:
            entwurf_fuer(mueller(), soll, haben, 9, BH)
        assert info.value.feld == feld
    rein = mueller("100.00", zweck="Zahlung Kunde")
    with pytest.raises(RegelError) as info:
        entwurf_fuer(rein, "8400", "1200", 3, BH)
    assert info.value.feld == "soll"
    assert entwurf_fuer(rein, "1200", "8400", 3, BH).soll_konto == "1200"


def test_text_muster_ist_kein_regex():
    for muster in (".*", "(a+)+$"):
        r = Regel.aus_text("t", muster, "4930", "1200")
        assert not r.passt(mueller(name="irgendwer", zweck="aaaaaaaaaaaaaaaaaaaaaaaa!"))
        assert r.passt(mueller(name="x", zweck=f"zahlung {muster} danke"))


def test_text_muster_nur_ganze_woerter():
    r = Regel.aus_text("t", "Müller", "4930", "1200", feld="beide")
    assert r.passt(mueller(name="Müller GmbH"))
    assert r.passt(mueller(name="Bürobedarf MÜLLER"))
    assert not r.passt(mueller(name="Müllerstraße 5", zweck="Miete"))
    punkt = Regel.aus_text("t", "Müller GmbH.", "4930", "1200")
    assert punkt.passt(mueller(name="x", zweck="an Müller GmbH. Danke"))


def test_finanzkonto_wird_standard_bankkonto():
    karte = mueller(sachkonto="1361")
    e = entwurf_fuer(karte, "4930", "1361", 9, BH)
    assert (e.soll_konto, e.haben_konto) == ("4930", "1200")


def test_richtung_aus_dem_umsatz():
    assert entwurf_fuer(mueller(), "4930", "1200", 9, BH).richtung is Richtung.AUSGABE
    rein = mueller("100.00", zweck="Zahlung Kunde")
    assert entwurf_fuer(rein, "1200", "8400", 3, BH).richtung is Richtung.EINNAHME


def test_schluessel_der_neubuchung(make_session):
    """Sachkonto bleibt → bisheriger Schlüssel; neues Sachkonto → ausdrücklich
    angegebener (wie korrigiere --lernen in Baustein 7)."""
    tx = mueller()
    gleich = buchung(tx, soll="4930", haben="1200", schluessel=9)
    anders = buchung(tx, soll="4980", haben="1200", schluessel=9)
    anlegen(make_session, tx, gleich, anders)
    with make_session() as s:
        k1 = korrigiere(s, str(gleich.id), "4930", "1200", von="jan")
        k2 = korrigiere(s, str(anders.id), "4930", "1200", steuer=8, von="jan")
        s.commit()
    assert entwurf_aus_korrektur(k1, tx, BH).steuer_schluessel == 9
    assert entwurf_aus_korrektur(k2, tx, BH).steuer_schluessel == 8


# --- Vorschau -------------------------------------------------------------------------


def _bestand(make_session, *umsaetze: Transaktion, gebucht=()):  # noqa: ANN001, ANN002, ANN202
    anlegen(make_session, *umsaetze, *gebucht)


def test_vorschau_treffer_beispiele_verdraengte_regel(make_session, tmp_path):
    tx = mueller()
    frueher = mueller(tag=date(2026, 8, 3))
    fremd = umsatz("-20.00", date(2026, 9, 1), "Tankstelle", "Aral")
    falsch = buchung(frueher, soll="4980", haben="1200", schluessel=9)
    anlegen(make_session, tx, frueher, fremd, falsch)
    with make_session() as s:
        werk = lade_regelwerk(s, _eigene(tmp_path), "automatisch")
        v = pruefe_entwurf(
            s, entwurf_fuer(tx, "4930", "1200", 9, BH), tx, werk, heute=HEUTE
        )
    assert v.treffer == 2 and v.gegenrichtung == 0
    assert v.greift_fuer_umsatz and v.verdraengt == "buero_falsch"
    assert v.anders_kontiert == 1
    assert [b.datum for b in v.beispiele] == [date(2026, 10, 1), date(2026, 8, 3)]
    assert v.beispiele[1].kontierung == "4980 an 1200"
    assert v.beispiele[0].kontierung is None


def test_vorschau_zaehlt_gegenrichtung_getrennt(make_session):
    tx = mueller()
    erstattung = mueller("15.00", tag=date(2026, 9, 2), zweck="Gutschrift")
    anlegen(make_session, tx, erstattung)
    with make_session() as s:
        v = pruefe_entwurf(
            s,
            entwurf_fuer(tx, "4930", "1200", 9, BH),
            tx,
            lade_regelwerk(s, None, "automatisch"),
            heute=HEUTE,
        )
    assert v.treffer == 1 and v.gegenrichtung == 1


def test_vorschau_nur_24_monate(make_session):
    tx = mueller()
    alt = mueller(tag=HEUTE - timedelta(days=800))
    anlegen(make_session, tx, alt)
    with make_session() as s:
        v = pruefe_entwurf(
            s,
            entwurf_fuer(tx, "4930", "1200", 9, BH),
            tx,
            lade_regelwerk(s, None, "automatisch"),
            heute=HEUTE,
        )
    assert v.treffer == 1


def test_vorschau_warnt_zu_kurz_zu_breit_doppelt(make_session):
    """(angepasst, Nachbesserung H1: der Vorschlag ist jetzt der ganze Name — das
    breite Muster „GmbH“ wird ausdrücklich angegeben)"""
    tx = mueller(name="GmbH Bürobedarf Müller")
    andere = [
        umsatz("-5.00", date(2026, 9, i + 1), f"Rechnung {i}", f"Lieferant {i} GmbH")
        for i in range(12)
    ]
    anlegen(make_session, tx, *andere)
    with make_session() as s:
        werk = lade_regelwerk(s, None, "automatisch")
        breit = pruefe_entwurf(
            s,
            entwurf_fuer(tx, "4930", "1200", 9, BH, muster="GmbH"),
            tx,
            werk,
            heute=HEUTE,
        )
        assert any("breit" in w for w in breit.warnungen)
        kurz = pruefe_entwurf(
            s,
            entwurf_fuer(tx, "4930", "1200", 9, BH, muster="Gm"),
            tx,
            werk,
            heute=HEUTE,
        )
        assert any("kurz" in w for w in kurz.warnungen)
        lerne(s, entwurf_fuer(tx, "4930", "1200", 9, BH, muster="Müller"), "jan")
        doppelt = pruefe_entwurf(
            s,
            entwurf_fuer(tx, "4930", "1200", 9, BH, muster="müller"),
            tx,
            lade_regelwerk(s, None, "aus"),
            heute=HEUTE,
            einstellung="aus",
        )
    assert any("schon gelernt" in w for w in doppelt.warnungen)
    assert any("gelernte_regeln" in w for w in doppelt.warnungen)


def _telekom_welt(make_session):  # noqa: ANN001, ANN202
    tx = umsatz("-39.95", date(2026, 10, 1), "Rechnung 10/2026", "Deutsche Telekom AG")
    frueher = umsatz(
        "-39.95", date(2026, 9, 1), "Rechnung 09/2026", "DEUTSCHE TELEKOM AG"
    )
    bahn = umsatz("-80.00", date(2026, 9, 3), "Fahrkarte 4711", "Deutsche Bahn AG")
    drv = umsatz("-450.00", date(2026, 9, 6), "Beitrag", "Deutsche Rentenversicherung")
    anlegen(make_session, tx, frueher, bahn, drv)
    return tx


def test_vorschau_warnt_vor_fremden_gegenparteien(make_session):
    """Nachbesserung H1: „Deutsche“ träfe Bahn und Rentenversicherung — die Vorschau
    nennt sie und verlangt eine Bestätigung; der Standardvorschlag trifft nur die
    Telekom (auch in anderer Schreibweise)."""
    tx = _telekom_welt(make_session)
    with make_session() as s:
        breit = pruefe_entwurf(
            s, entwurf_fuer(tx, "4920", "1200", 9, BH, muster="Deutsche"), tx, None,
            heute=HEUTE,
        )  # fmt: skip
        genau = pruefe_entwurf(
            s, entwurf_fuer(tx, "4920", "1200", 9, BH), tx, None, heute=HEUTE
        )
    assert breit.bestaetigung_noetig and breit.fremde_anzahl == 2
    assert set(breit.fremde) == {"Deutsche Bahn AG", "Deutsche Rentenversicherung"}
    assert any("andere Gegenparteien" in w for w in breit.warnungen)
    assert genau.entwurf.muster == "Deutsche Telekom" and genau.treffer == 2
    assert not genau.bestaetigung_noetig and genau.fremde == []


def test_vorschau_warnt_vor_zahlungsdienst(make_session):
    """Ein Muster auf „PayPal“ träfe jeden Kauf über PayPal — nur mit Bestätigung;
    der Händler aus dem Verwendungszweck nicht."""
    tx = umsatz(
        "-19.99",
        date(2026, 10, 7),
        "PP.1234.PP . Spotify AB, Ihr Einkauf bei Spotify AB",
        "PayPal Europe S.a.r.l. et Cie S.C.A",
    )
    anlegen(make_session, tx)
    with make_session() as s:
        dienst = pruefe_entwurf(
            s, entwurf_fuer(tx, "4940", "1200", 9, BH), tx, None, heute=HEUTE
        )
        haendler = pruefe_entwurf(
            s, entwurf_fuer(tx, "4940", "1200", 9, BH, muster="Spotify"), tx, None,
            heute=HEUTE,
        )  # fmt: skip
    assert dienst.zahlungsdienst == "PayPal" and dienst.bestaetigung_noetig
    assert any("Zahlungsdienst PayPal" in w for w in dienst.warnungen)
    assert haendler.zahlungsdienst is None and not haendler.bestaetigung_noetig


def test_vorschau_warnt_vor_anders_gebuchten_treffern(make_session):
    tx = mueller()
    frueher = mueller(tag=date(2026, 8, 3))
    anlegen(make_session, tx, frueher, buchung(frueher, soll="4980", haben="1200"))
    with make_session() as s:
        v = pruefe_entwurf(
            s, entwurf_fuer(tx, "4930", "1200", 9, BH), tx, None, heute=HEUTE
        )
    assert any("1 weitere Treffer sind heute anders gebucht" in w for w in v.warnungen)
    assert not v.bestaetigung_noetig  # dieselbe Gegenpartei: nur ein Hinweis


def test_regel_nur_in_der_eigenen_datenbank(tmp_path):
    from accounti.db import init_db, session_factory

    fabriken = {}
    for k in ("a", "b"):
        engine, fabrik = session_factory(f"sqlite:///{tmp_path / k}.db")
        init_db(engine)
        fabriken[k] = fabrik
    with fabriken["a"]() as s:
        lerne_mueller(s)
        s.commit()
    with fabriken["b"]() as s:
        assert lade_kontierungsregeln(s) == []
        werk = lade_regelwerk(s, None, "automatisch")
    assert not any(r.name.startswith("gelernt_") for r in werk.regeln)


def test_lerne_sachkonto_am_kontakt_mit_journal(make_session):
    k = kontakt()
    b = beleg()
    bu = buchung(beleg_id=b.id, soll="4900", haben="70001")
    anlegen(make_session, k, b, bu)
    with make_session() as s:
        speichere_posten(
            s,
            OffenerPosten(
                kontakt_id=k.id,
                beleg_id=b.id,
                richtung=PostenRichtung.VERBINDLICHKEIT,
                belegnummer="RE-2026-0815",
                belegdatum=date(2026, 8, 10),
                betrag=Decimal("119.00"),
                restbetrag=Decimal("119.00"),
                faellig_am=date(2026, 8, 24),
            ),
        )
        s.commit()
    with make_session() as s:
        text_ = lerne_sachkonto(s, bu, "4240", "70001", "jan")
        s.commit()
        assert lade_kontakt(s, str(k.id)).sachkonto == "4240"
        (e,) = lade_journal(s, vorgang="sachkonto_gelernt")
    assert text_ is not None and "4240" in text_
    assert e.person == "jan" and e.objekt_typ == "kontakt"
    assert json.loads(e.nachher or "{}") == {"sachkonto": "4240", "bisher": None}


def test_lerne_regex_wird_geprueft(make_session):
    with make_session() as s:
        with pytest.raises(RegelError, match="Ausdruck"):
            lerne_regex(s, "kaputt", "(offen", "4930", "1200", None, "jan")
        with pytest.raises(RegelError, match="200"):
            lerne_regex(s, "lang", "x" * 201, "4930", "1200", None, "jan")
        r = lerne_regex(s, "telekom", r"telekom|t-mobile", "4920", "1200", 9, "jan")
        with pytest.raises(RegelError, match="vergeben"):
            lerne_regex(s, "telekom", "x", "4920", "1200", 9, "jan")
        s.commit()
    assert r.herkunft is RegelHerkunft.LERNE and not r.ist_text


def test_deaktivieren_zweimal_fehler(make_session):
    with make_session() as s:
        r = lerne_mueller(s)
        deaktiviere(s, r.id, "jan", "falsch")
        with pytest.raises(RegelError, match="schon deaktiviert"):
            deaktiviere(s, r.id, "jan", "nochmal")
        with pytest.raises(RegelError, match="Grund"):
            deaktiviere(
                s, lerne_regex(s, "x1", "x", "4930", "1200", None, "j").id, "j", " "
            )


def test_uebernahme_gelernter_eintraege_aus_datei(make_session, tmp_path):
    datei = tmp_path / "regeln.yaml"
    inhalt = (
        "# eigene Regeln\n"
        "- name: miete\n  muster: miete\n  soll_konto: '4210'\n  haben_konto: '1200'\n"
        "- name: gelernt_müller\n  muster: Müller\n  feld: beide\n"
        "  soll_konto: '4930'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n"
        "- name: gelernt_aral\n  muster: Aral\n  feld: beide\n"
        "  soll_konto: '4530'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n"
    )
    datei.write_text(inhalt, encoding="utf-8")
    with make_session() as s:
        probe = uebernehme_aus_datei(s, datei, "jan", probe=True)
        assert probe.uebernommen == ["gelernt_müller", "gelernt_aral"]
        assert lade_kontierungsregeln(s) == []
        lerne_regex(s, "gelernt_aral", "Aral", "4530", "1200", 9, "jan")
        echt = uebernehme_aus_datei(s, datei, "jan")
        s.commit()
        regeln = {r.name: r for r in lade_kontierungsregeln(s)}
        eintraege = lade_journal(s, vorgang="regel_uebernommen")
    assert echt.uebernommen == ["gelernt_müller"] and echt.uebersprungen == [
        "gelernt_aral"
    ]
    neu = regeln["gelernt_müller"]
    assert neu.herkunft is RegelHerkunft.UEBERNAHME and not neu.ist_text
    # (angepasst, Nachbesserung M3: Richtung aus der Bankseite statt ohne Richtung)
    assert neu.richtung is Richtung.AUSGABE and neu.steuer_schluessel == 9
    assert len(eintraege) == 1
    assert datei.read_text(encoding="utf-8") == inhalt  # Datei unverändert


def test_uebernahme_leitet_die_richtung_aus_der_bankseite_ab(make_session, tmp_path):
    """Nachbesserung M3 (Probe L2): Eine übernommene Regel hat Vorrang vor der
    Regeldatei — ohne Richtung buchte sie die Gutschrift der Telekom als Geldabgang
    (4920 an 1200, Vorsteuer, automatisch). Bank im Haben → Ausgabe, im Soll →
    Einnahme, Geldkonto des Kontenrahmens (Kreditkarte 1361) ebenso; ohne Bankseite
    bleibt sie ohne Richtung und wird gemeldet."""
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen

    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: gelernt_telekom\n  muster: Telekom\n  feld: beide\n"
        "  soll_konto: '4920'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n"
        "- name: gelernt_kunde\n  muster: Kunde\n  feld: beide\n"
        "  soll_konto: '1200'\n  haben_konto: '8400'\n  steuer_schluessel: 3\n"
        "- name: gelernt_karte\n  muster: Tanke\n  feld: beide\n"
        "  soll_konto: '4530'\n  haben_konto: '1361'\n"
        "- name: gelernt_umbuchung\n  muster: Umbuchung\n  feld: beide\n"
        "  soll_konto: '4930'\n  haben_konto: '4980'\n"
        "- name: gelernt_fest\n  muster: Fest\n  richtung: einnahme\n"
        "  soll_konto: '1200'\n  haben_konto: '4930'\n",
        encoding="utf-8",
    )
    with make_session() as s:
        e = uebernehme_aus_datei(s, datei, "jan", kontenrahmen=lade_kontenrahmen())
        s.commit()
        regeln = {r.name: r.richtung for r in lade_kontierungsregeln(s)}
        werk = lade_regelwerk(s, None, "automatisch")
    assert regeln == {
        "gelernt_telekom": Richtung.AUSGABE,
        "gelernt_kunde": Richtung.EINNAHME,
        "gelernt_karte": Richtung.AUSGABE,
        "gelernt_umbuchung": None,
        "gelernt_fest": Richtung.EINNAHME,
    }
    assert e.ohne_richtung == ["gelernt_umbuchung"]
    gutschrift = mueller("25.00", zweck="Gutschrift Telekom", name="Deutsche Telekom")
    treffer = werk.klassifiziere(gutschrift)
    assert treffer is None or treffer.regel != "gelernt_telekom"


def test_uebernahme_behaelt_die_reihenfolge_der_datei(make_session, tmp_path):
    """Nachbesserung Fach N7 (Mutation N10): In der Datei gewann der erste passende
    Eintrag — nach der Übernahme ebenso."""
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: gelernt_erst\n  muster: Müller\n  feld: beide\n"
        "  soll_konto: '4930'\n  haben_konto: '1200'\n"
        "- name: gelernt_dann\n  muster: Müller\n  feld: beide\n"
        "  soll_konto: '4980'\n  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    with make_session() as s:
        uebernehme_aus_datei(s, datei, "jan")
        s.commit()
        werk = lade_regelwerk(s, None, "automatisch")
    e = werk.klassifiziere(mueller())
    assert e is not None and e.regel == "gelernt_erst" and e.soll_konto == "4930"


def test_text_regel_aus_der_datenbank_bleibt_woertlich(make_session):
    """Nachbesserung Fach N7 (Mutation N19): Eine im Browser gelernte Text-Regel
    wird beim Laden aus der Datenbank wieder wörtlich und nur als ganzes Wort
    angewandt — kein regulärer Ausdruck."""
    with make_session() as s:
        for muster in ("Müller (alt)", "a.c Handel"):
            lerne(
                s, entwurf_fuer(mueller(), "4930", "1200", 9, BH, muster=muster), "jan"
            )
        s.commit()
        werk = lade_regelwerk(s, None, "automatisch")
    assert werk.klassifiziere(mueller(name="Müller (alt) GmbH")) is not None
    for name in ("Müller alt GmbH", "abc Handel", "Müller (alt)straße"):
        e = werk.klassifiziere(mueller(name=name, zweck="RE 1"))
        assert e is None or not (e.regel or "").startswith("gelernt_"), name


def test_gelernte_regel_mit_kaputtem_ausdruck_wird_uebersprungen(make_session):
    """Ein an accounti vorbei gespeicherter ungültiger Ausdruck bricht keinen Lauf ab
    (``journal pruefen`` meldet die Änderung)."""
    with make_session() as s:
        r = lerne_regex(s, "ok", "telekom", "4920", "1200", 9, "jan")
        s.commit()
        s.execute(text("UPDATE kontierungsregeln SET muster = '(kaputt'"))
        s.commit()
        werk = lade_regelwerk(s, None, "automatisch")
    assert r.name not in [x.name for x in werk.regeln]


def test_gelernte_regel_in_derselben_sitzung_buchbar(make_session):
    """Kontierungslauf mit gelernter Regel: Buchung und Grund mit Regelname."""
    with make_session() as s:
        lerne_mueller(s)
        tx = mueller(tag=date(2026, 10, 20))
        speichere_transaktion(s, tx)
        s.commit()
    with make_session() as s:
        engine = KlassifikationsEngine(regelwerk=lade_regelwerk(s, None, "automatisch"))
        kontiere_umsaetze(s, engine, BH)
        s.commit()
        (b,) = lade_buchungen(s)
        g = lade_kontierungsgrund(s, b.id)
    assert b.soll_konto == "4930" and b.status is BuchungStatus.AUTO_GEBUCHT
    assert (
        g is not None
        and g.quelle == "regelwerk"
        and g.regel == "gelernt_bürobedarf_müller"
    )


def _unbenutzt() -> None:  # pragma: no cover — hält Importe für Hilfen stabil
    speichere_buchung  # noqa: B018
