"""Storno statt Änderung (Spec 4.4, Akzeptanz 6) und der behobene Fehler in
``korrigiere``: Betrag und Beleg der Buchung bleiben — bei Beleg-, Ausgleichs-,
Skonto- und Splitbuchungen."""

import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.abschluss.salden import summen_und_salden
from accounti.buchung.mit_beleg import kontiere_mit_beleg
from accounti.db.repo_pruefung import korrektur_zu, lade_korrekturen
from accounti.db.repository import (
    finde_buchung,
    lade_buchungen,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.db.tabellen import BuchungssatzRow
from accounti.db.tabellen_abschluss import JahrGesperrtError
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.zuordnung import Anteil
from accounti.pruefung.ereignisse import BuchungFestgeschriebenError
from accounti.pruefung.journal import lade_journal, pruefe_journal
from accounti.pruefung.storno import (
    StornoError,
    freigeben,
    korrigiere,
    markiere_exportiert,
    storniere,
)
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    buchung,
    kurz,
    make_session_fixture,
    umsatz,
)
from tests.test_buchung_mit_beleg import REGELN, mit_positionen
from tests.zahlung_hilfe import beleg_zu, kreditor, posten, speichere

KR = lade_kontenrahmen()


def _salden(make_session, jahr=2026):
    with make_session() as s:
        susa = summen_und_salden(s, jahr, KR, "bilanz")
    return {z.konto: z.saldo for z in susa.zeilen if z.saldo}


# --- Vorschlag: direkt ---------------------------------------------------------------


def test_vorschlag_wird_direkt_korrigiert(make_session):
    tx = umsatz()
    b = buchung(tx)
    anlegen(make_session, tx, b)
    with make_session() as s:
        k = korrigiere(s, kurz(b.id), "4930", "1200", steuer=9, von="erika")
        s.commit()
    assert k.direkt and k.storno is None
    with make_session() as s:
        neu = finde_buchung(s, kurz(b.id))
        assert (neu.soll_konto, neu.status, neu.geprueft_von) == (
            "4930",
            BuchungStatus.KORRIGIERT,
            "erika",
        )
        assert neu.betrag_netto == Decimal("100.00")
        assert neu.steuer_schluessel == 9  # ausdrücklich bestätigt (Sachkonto neu)
        vorgaenge = [e.vorgang for e in lade_journal(s)]
    assert vorgaenge[-2:] == ["buchung_korrigiert", "buchung_freigegeben"]


# --- Freigegeben: Storno + Neubuchung (Akzeptanz 6) ----------------------------------


def test_freigegebene_buchung_nur_per_storno_beide_sichtbar(make_session):
    tx = umsatz()
    b = buchung(tx, status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, tx, b)
    vorher = _salden(make_session)
    # direkte Änderung über das ORM wird abgelehnt
    with make_session() as s:
        s.get(BuchungssatzRow, str(b.id)).soll_konto = "4930"
        with pytest.raises(BuchungFestgeschriebenError, match="nur per Storno"):
            s.flush()
    with make_session() as s:
        k = korrigiere(
            s, kurz(b.id), "4930", "1200", steuer=9, von="jan", grund="falsches Konto"
        )
        s.commit()
    assert not k.direkt
    with make_session() as s:
        alle = {x.id: x for x in lade_buchungen(s)}
        original, storno, neu = alle[b.id], alle[k.storno.id], alle[k.neu.id]
        # gegenseitig referenziert, alle drei sichtbar
        assert original.storniert_durch == storno.id
        assert storno.storno_von == original.id
        assert (original.status, original.soll_konto) == (
            BuchungStatus.GEPRUEFT,
            "4900",
        )
        # Gegenbuchung: Seiten getauscht, Beträge und Schlüssel gleich
        assert (storno.soll_konto, storno.haben_konto) == ("1200", "4900")
        assert (
            storno.betrag_netto,
            storno.steuer_betrag,
            storno.steuer_schluessel,
        ) == (
            Decimal("100.00"),
            Decimal("19.00"),
            9,
        )
        assert storno.transaktion_id == tx.id
        assert (neu.soll_konto, neu.status, neu.betrag_netto) == (
            "4930",
            BuchungStatus.KORRIGIERT,
            Decimal("100.00"),
        )
        korrektur = korrektur_zu(s, neu.id)
        assert korrektur is not None and korrektur.grund == "falsches Konto"
        assert pruefe_journal(s).in_ordnung
        vorgaenge = [e.vorgang for e in lade_journal(s)][-3:]
    assert vorgaenge == ["storno_gebucht", "buchung_storniert", "buchung_angelegt"]
    # Salden: 4900 ist aufgehoben, 4930 trägt die Buchung — Vorsteuer bleibt
    nachher = _salden(make_session)
    assert "4900" not in nachher and nachher["4930"] == Decimal("100.00")
    assert nachher["1576"] == vorher["1576"] and nachher["1200"] == vorher["1200"]


def test_storno_ohne_neubuchung_und_kein_zweites_storno(make_session):
    b = buchung(umsatz(), status=BuchungStatus.AUTO_GEBUCHT)
    anlegen(make_session, b)
    with make_session() as s:
        with pytest.raises(StornoError, match="Grund"):
            storniere(s, kurz(b.id), grund=" ")
        k = storniere(s, kurz(b.id), grund="doppelt erfasst", von="jan")
        s.commit()
    assert k.neu is None and k.storno is not None
    with make_session() as s:
        with pytest.raises(StornoError, match="schon storniert"):
            storniere(s, kurz(b.id), grund="nochmal")
        with pytest.raises(StornoError, match="selbst ein Storno"):
            korrigiere(s, kurz(k.storno.id), "4930", "1200")
        # auch am ORM vorbei an der Funktion: der Vermerk lässt sich nicht überschreiben
        s.get(BuchungssatzRow, str(b.id)).storniert_durch = str(uuid4())
        with pytest.raises(BuchungFestgeschriebenError, match="schon storniert"):
            s.flush()
    assert len(lade_korrekturen(make_session())) == 1


def test_vorschlag_wird_nicht_storniert(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s, pytest.raises(StornoError, match="Vorschlag"):
        storniere(s, kurz(b.id), grund="x")


def test_freigegebene_buchung_nicht_loeschbar(make_session):
    b = buchung(status=BuchungStatus.KORRIGIERT)
    anlegen(make_session, b)
    with make_session() as s:
        s.delete(s.get(BuchungssatzRow, str(b.id)))
        with pytest.raises(BuchungFestgeschriebenError):
            s.flush()


def test_erlaubte_statuswege(make_session):
    auto = buchung(status=BuchungStatus.AUTO_GEBUCHT)
    exp = buchung(status=BuchungStatus.EXPORTIERT)
    anlegen(make_session, auto, exp)
    with make_session() as s:
        _, geaendert = freigeben(s, kurz(auto.id), von="jan")
        s.commit()
        assert geaendert
        assert finde_buchung(s, kurz(auto.id)).status is BuchungStatus.GEPRUEFT
        _, geaendert = freigeben(s, kurz(exp.id))
        assert not geaendert
        s.get(BuchungssatzRow, str(exp.id)).status = "geprueft"
        with pytest.raises(BuchungFestgeschriebenError, match="nicht erlaubt"):
            s.flush()


def test_korrektur_ohne_wirkung_wird_abgelehnt(make_session):
    b = buchung(status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, b)
    with make_session() as s, pytest.raises(StornoError, match="ändert"):
        korrigiere(s, kurz(b.id), "4900", "1200")


def test_steuer_aus_dem_brutto_der_buchung(make_session):
    """--steuer rechnet aus dem Brutto der Buchung, nicht aus dem Umsatz."""
    tx = umsatz("-500.00")  # Umsatz größer als die Buchung (z.B. Teil einer Zahlung)
    b = buchung(tx, netto="119.00", steuer=None, schluessel=None)
    anlegen(make_session, tx, b)
    with make_session() as s:
        korrigiere(s, kurz(b.id), "4930", "1200", steuer=9)
        s.commit()
        neu = finde_buchung(s, kurz(b.id))
    assert (neu.betrag_netto, neu.steuer_betrag) == (
        Decimal("100.00"),
        Decimal("19.00"),
    )
    with make_session() as s:  # jetzt freigegeben (korrigiert): Storno + Neubuchung
        k = korrigiere(s, kurz(b.id), "4930", "1200", ohne_steuer=True)
        s.commit()
        neu = finde_buchung(s, kurz(k.neu.id))
    assert (neu.betrag_netto, neu.steuer_betrag, neu.steuer_schluessel) == (
        Decimal("119.00"),
        None,
        None,
    )


def test_storno_im_gesperrten_zeitraum_braucht_ein_offenes_datum(make_session):
    from accounti.db.repo_abschluss import setze_jahresabschluss
    from accounti.models.abschluss import Jahresabschluss

    b = buchung(status=BuchungStatus.GEPRUEFT, tag=date(2025, 12, 30))
    anlegen(make_session, b)
    with make_session() as s:
        setze_jahresabschluss(
            s,
            Jahresabschluss(
                jahr=2025,
                gesperrt=True,
                gewinnermittlung="euer",
                ergebnis=Decimal("0"),
                abgeschlossen_am=date(2026, 3, 1),
                von="jan",
            ),
        )
        s.commit()
    with make_session() as s:
        with pytest.raises(StornoError, match="--datum"):
            korrigiere(s, kurz(b.id), "4930", "1200", steuer=9)
        with pytest.raises(StornoError, match="abgeschlossenen"):
            korrigiere(
                s, kurz(b.id), "4930", "1200", steuer=9, datum=date(2025, 12, 31)
            )
        k = korrigiere(s, kurz(b.id), "4930", "1200", steuer=9, datum=date(2026, 1, 5))
        s.commit()
        assert k.storno.datum == k.neu.datum == date(2026, 1, 5)
        # das Original im gesperrten Jahr trägt den Stornovermerk, sonst nichts
        original = finde_buchung(s, kurz(b.id))
        assert original.storniert_durch == k.storno.id
        s.get(BuchungssatzRow, str(b.id)).buchungstext = "geändert"
        with pytest.raises(JahrGesperrtError):
            s.flush()


def test_gegenbuchung_nicht_eindeutig_umkehrbar(make_session):
    b = buchung(status=BuchungStatus.GEPRUEFT, soll="4900", haben="4930")
    anlegen(make_session, b)
    with make_session() as s, pytest.raises(StornoError, match="dieselbe Natur"):
        storniere(s, kurz(b.id), grund="x")


# --- Der behobene Fehler: je Buchungsart -------------------------------------------


def _korrigiert_freigegeben(make_session, b, soll, haben):
    with make_session() as s:
        k = korrigiere(
            s, kurz(b.id), soll, haben, steuer=b.steuer_schluessel, von="jan"
        )
        s.commit()
    with make_session() as s:
        return finde_buchung(s, kurz(k.neu.id)), finde_buchung(s, kurz(k.storno.id))


def test_belegbuchung_behaelt_beleg_und_betrag(make_session):
    m = kreditor()
    p = posten(m, betrag="1190.00")
    speichere(make_session, [m], [p])
    rechnung = buchung(
        None,
        status=BuchungStatus.GEPRUEFT,
        soll="4930",
        haben="70001",
        netto="1000.00",
        steuer="190.00",
        beleg_id=p.beleg_id,
        beleg_nummer="RE-2026-0042",
    )
    anlegen(make_session, rechnung)
    with make_session() as s, pytest.raises(StornoError, match="Beleg"):
        korrigiere(s, kurz(rechnung.id), "4900", "70001", steuer=8)
    neu, storno = _korrigiert_freigegeben(make_session, rechnung, "4900", "70001")
    for x in (neu, storno):
        assert x.beleg_id == p.beleg_id and x.transaktion_id is None
        assert (x.betrag_netto, x.steuer_betrag) == (
            Decimal("1000.00"),
            Decimal("190.00"),
        )
        assert x.beleg_nummer == "RE-2026-0042"
    with make_session() as s:
        from accounti.db.repository import lade_belegbuchungen

        (wirksam,) = lade_belegbuchungen(s, p.beleg_id)
    assert wirksam.id == neu.id


def _ausgleich(make_session, skonto="0"):
    m = kreditor()
    p = posten(m, betrag="1190.00", skonto_prozent="2" if skonto != "0" else None)
    beleg = beleg_zu(p)
    speichere(make_session, [m], [p], [beleg])
    anlegen(
        make_session,
        buchung(
            None,
            status=BuchungStatus.GEPRUEFT,
            soll="4930",
            haben="70001",
            netto="1000.00",
            steuer="190.00",
            beleg_id=p.beleg_id,
        ),
    )
    # Sammelzahlung: der Umsatz ist größer als dieser Anteil
    tx = umsatz("-2000.00", tag=date(2026, 10, 20))
    with make_session() as s:
        speichere_transaktion(s, tx)
        buchungen = gleiche_aus(
            s,
            tx,
            [Anteil(p, Decimal("1190.00") - Decimal(skonto), Decimal(skonto))],
            Buchhaltung(),
        )
        s.commit()
    return tx, p, buchungen


def test_ausgleichsbuchung_behaelt_anteil_und_beleg(make_session):
    tx, p, (zahlung,) = _ausgleich(make_session)
    assert zahlung.status is BuchungStatus.AUTO_GEBUCHT
    neu, storno = _korrigiert_freigegeben(make_session, zahlung, "70001", "1210")
    for x in (neu, storno):
        assert x.betrag_netto == Decimal("1190.00")  # nicht die 2.000 des Umsatzes
        assert (x.transaktion_id, x.beleg_id) == (tx.id, p.beleg_id)
    assert (storno.soll_konto, storno.haben_konto) == ("1200", "70001")


def test_skontobuchung_behaelt_betrag_steuer_und_beleg(make_session):
    tx, p, buchungen = _ausgleich(make_session, skonto="23.80")
    skonto = next(b for b in buchungen if b.steuer_schluessel)
    assert (skonto.betrag_netto, skonto.steuer_betrag) == (
        Decimal("20.00"),
        Decimal("3.80"),
    )
    neu, storno = _korrigiert_freigegeben(
        make_session, skonto, skonto.soll_konto, "3730"
    )
    for x in (neu, storno):
        assert (x.betrag_netto, x.steuer_betrag, x.steuer_schluessel) == (
            Decimal("20.00"),
            Decimal("3.80"),
            skonto.steuer_schluessel,
        )
        assert (x.transaktion_id, x.beleg_id) == (tx.id, p.beleg_id)


def test_splitbuchung_behaelt_ihren_anteil(make_session):
    b = mit_positionen(
        ("Super E10", "50.00", "19", "9.50"),
        ("Snack", "10.00", "7", "0.70"),
        belegnummer="Q-0042-77",
        brutto="70.20",
    )
    tx = umsatz("-70.20")
    teile = kontiere_mit_beleg(tx, b, Buchhaltung(), REGELN)
    with make_session() as s:
        speichere_transaktion(s, tx)
        for t in teile:
            speichere_buchung(s, t)
        s.commit()
    erster = teile[0]
    assert erster.status is BuchungStatus.AUTO_GEBUCHT
    neu, storno = _korrigiert_freigegeben(make_session, erster, "4500", "1200")
    for x in (neu, storno):
        assert (x.betrag_netto, x.steuer_betrag, x.steuer_schluessel) == (
            Decimal("50.00"),
            Decimal("9.50"),
            9,
        )
        assert (x.transaktion_id, x.beleg_id) == (tx.id, b.id)
        assert x.beleg_nummer == "Q-0042-77"


def test_split_vorschlag_direkt_behaelt_anteil(make_session):
    """Auch die direkte Korrektur eines Vorschlags rechnet nicht aus dem Umsatz."""
    b = mit_positionen(("Diverses", "50.00", None, "0"), brutto="61.00")
    tx = umsatz("-61.00")
    teile = kontiere_mit_beleg(tx, b, Buchhaltung(), REGELN)
    with make_session() as s:
        speichere_transaktion(s, tx)
        for t in teile:
            speichere_buchung(s, t)
        s.commit()
    (teil,) = teile
    assert teil.status is BuchungStatus.ZUR_PRUEFUNG
    with make_session() as s:
        korrigiere(s, kurz(teil.id), "4930", "1200", steuer=teil.steuer_schluessel)
        s.commit()
        neu = finde_buchung(s, kurz(teil.id))
    assert (neu.betrag_netto, neu.beleg_id, neu.transaktion_id) == (
        teil.betrag_netto,
        b.id,
        tx.id,
    )


# --- Export --------------------------------------------------------------------------


def test_export_setzt_exportiert_und_steht_im_journal(make_session, tmp_path):
    a = buchung(status=BuchungStatus.AUTO_GEBUCHT)
    v = buchung(status=BuchungStatus.ZUR_PRUEFUNG)
    anlegen(make_session, a, v)
    datei = tmp_path / "EXTF.csv"
    datei.write_bytes(b"x")
    with make_session() as s:
        alle = lade_buchungen(s)
        assert markiere_exportiert(s, alle, datei, "datev") == (1, 0)
        s.commit()
        assert finde_buchung(s, kurz(a.id)).status is BuchungStatus.EXPORTIERT
        assert finde_buchung(s, kurz(v.id)).status is BuchungStatus.ZUR_PRUEFUNG
        export = lade_journal(s, vorgang="export")[-1]
        assert lade_journal(s, vorgang="buchung_exportiert")[-1].objekt_id == str(a.id)
    daten = json.loads(export.nachher)
    assert daten["markiert"] == [str(a.id)] and daten["anzahl"] == 2
    assert len(daten["sha256"]) == 64


# --- reines Storno: der Umsatz ist wieder offen (Befund A7 / B-M3) ------------------


def test_reines_storno_macht_den_umsatz_wieder_offen(make_session):
    from accounti.db.repository import gebuchte_transaktion_ids
    from accounti.opos.zahlungslauf import offene_transaktionen

    tx = umsatz()
    b = buchung(tx, status=BuchungStatus.AUTO_GEBUCHT, soll="4240")
    anlegen(make_session, tx, b)
    with make_session() as s:
        assert tx.id in gebuchte_transaktion_ids(s)
        storniere(s, str(b.id), grund="falsches Konto, neu kontieren", von="erika")
        s.commit()
        assert tx.id not in gebuchte_transaktion_ids(s)
        assert [t.id for t in offene_transaktionen(s)] == [tx.id]


def test_storno_mit_neubuchung_laesst_den_umsatz_gebucht(make_session):
    from accounti.db.repository import gebuchte_transaktion_ids

    tx = umsatz()
    b = buchung(tx, status=BuchungStatus.AUTO_GEBUCHT)
    anlegen(make_session, tx, b)
    with make_session() as s:
        korrigiere(s, str(b.id), "4930", "1200", steuer=9, von="erika")
        s.commit()
        assert tx.id in gebuchte_transaktion_ids(s)


def test_gegenbuchung_auf_anderem_umsatz_laesst_beide_gebucht(make_session):
    """Kassen-Storno: die Gegenbuchung hängt am Storno-Umsatz, nicht am Original."""
    from accounti.db.repository import gebuchte_transaktion_ids

    tx, gegen = umsatz(), umsatz("119.00", zweck="Storno")
    b = buchung(tx, status=BuchungStatus.GEPRUEFT)
    s_b = buchung(
        gegen, status=BuchungStatus.GEPRUEFT, soll="1200", haben="4900", storno_von=b.id
    )
    anlegen(make_session, tx, gegen, b.model_copy(update={"storniert_durch": s_b.id}))
    anlegen(make_session, s_b)
    with make_session() as s:
        assert {tx.id, gegen.id} <= gebuchte_transaktion_ids(s)


# --- korrigiere: Steuerschlüssel bei geändertem Sachkonto (Befund B-H1, B-M2) -------


def _ustva(make_session) -> dict[int, Decimal]:
    from accounti.steuer.kennziffern import Kontenplan, ermittle
    from accounti.steuer.zeitraum import Zeitraum

    with make_session() as s:
        e = ermittle(lade_buchungen(s), Zeitraum(2026, monat=8), Kontenplan())
    return {kz: e.voranmeldung.wert(kz) for kz in (66, 81)}


def _neubuchung(make_session, k):
    with make_session() as s:
        return finde_buchung(s, str(k.neu.id))


def test_versicherung_umgebucht_verlangt_ausdrueckliche_steuer(make_session):
    tx = umsatz("-320.00", zweck="HAFTPFLICHT BEITRAG Q3", name="Allianz")
    b = buchung(tx, status=BuchungStatus.AUTO_GEBUCHT, netto="268.91", steuer="51.09")
    anlegen(make_session, tx, b)
    with make_session() as s:
        with pytest.raises(StornoError, match="--steuer .*--ohne-steuer"):
            korrigiere(s, str(b.id), "4360", "1200", von="erika")
        s.rollback()
        k = korrigiere(s, str(b.id), "4360", "1200", ohne_steuer=True, von="erika")
        s.commit()
    neu = _neubuchung(make_session, k)
    assert (neu.steuer_schluessel, neu.betrag_netto, neu.steuer_betrag) == (
        None,
        Decimal("320.00"),
        None,
    )
    assert _ustva(make_session)[66] == 0


@pytest.mark.parametrize(
    ("tx_betrag", "vorher", "nachher", "schluessel"),
    [
        ("-119.00", ("4930", "1200"), ("1800", "1200"), 9),  # Privatentnahme
        ("1190.00", ("1200", "8400"), ("1200", "1361"), 3),  # Amazon-Auszahlung
    ],
)
def test_steuer_auf_reiner_geldbewegung_wird_abgelehnt(
    make_session, tx_betrag, vorher, nachher, schluessel
):
    tx = umsatz(tx_betrag, zweck="Auszahlung 4711", name="AMAZON PAYMENTS EUROPE")
    netto = (abs(Decimal(tx_betrag)) / Decimal("1.19")).quantize(Decimal("0.01"))
    b = buchung(
        tx,
        status=BuchungStatus.AUTO_GEBUCHT,
        soll=vorher[0],
        haben=vorher[1],
        netto=str(netto),
        steuer=str(abs(Decimal(tx_betrag)) - netto),
        schluessel=schluessel,
    )
    anlegen(make_session, tx, b)
    soll, haben = nachher
    with make_session() as s:
        with pytest.raises(StornoError, match="--ohne-steuer"):
            korrigiere(s, str(b.id), soll, haben, von="erika")
        s.rollback()
        with pytest.raises(StornoError, match="Geld- und Personenkonten"):
            korrigiere(s, str(b.id), soll, haben, steuer=schluessel, von="erika")
        s.rollback()
        k = korrigiere(s, str(b.id), soll, haben, ohne_steuer=True, von="erika")
        s.commit()
    assert _neubuchung(make_session, k).steuer_schluessel is None
    assert _ustva(make_session) == {66: 0, 81: 0}


def test_nur_das_geldkonto_getauscht_behaelt_den_schluessel(make_session):
    tx = umsatz()
    b = buchung(tx, status=BuchungStatus.AUTO_GEBUCHT)
    anlegen(make_session, tx, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "4900", "1210", von="erika")
        s.commit()
    assert _neubuchung(make_session, k).steuer_schluessel == 9


def test_vorsteuer_aus_belegbuchung_entfernen_nur_mit_grund(make_session):
    beleg_id = uuid4()
    b = buchung(
        status=BuchungStatus.AUTO_GEBUCHT, soll="4930", haben="70001", beleg_id=beleg_id
    )
    anlegen(make_session, b)
    with make_session() as s:
        with pytest.raises(StornoError, match="--grund"):
            korrigiere(s, str(b.id), "4930", "70001", ohne_steuer=True, von="erika")
        s.rollback()
        with pytest.raises(StornoError, match="Beleg"):
            korrigiere(s, str(b.id), "4930", "70001", steuer=8, von="erika")
        s.rollback()
        k = korrigiere(
            s,
            str(b.id),
            "4930",
            "70001",
            ohne_steuer=True,
            grund="Rechnung ohne Steuernummer — kein Vorsteuerabzug",
            von="erika",
        )
        s.commit()
        eintrag = [e for e in lade_journal(s) if e.vorgang == "storno_gebucht"][-1]
    neu = _neubuchung(make_session, k)
    assert (neu.steuer_schluessel, neu.betrag_netto, neu.beleg_id) == (
        None,
        Decimal("119.00"),
        beleg_id,
    )
    assert eintrag.grund == "Rechnung ohne Steuernummer — kein Vorsteuerabzug"


def test_storno_mit_datum_in_anderem_voranmeldungszeitraum_warnt(make_session):
    """Befund B-Niedrig: die USt-Wirkung wandert mit dem Storno-Datum — gewarnt wird,
    weil der Originalzeitraum eigentlich berichtigt werden müsste."""
    b = buchung(status=BuchungStatus.GEPRUEFT, tag=date(2026, 8, 12))
    gleich = buchung(status=BuchungStatus.GEPRUEFT, tag=date(2026, 8, 13))
    anlegen(make_session, b, gleich)
    with make_session() as s:
        k = storniere(s, kurz(b.id), grund="x", von="erika", datum=date(2026, 9, 2))
        k2 = storniere(
            s, kurz(gleich.id), grund="x", von="erika", datum=date(2026, 8, 20)
        )
        s.commit()
    (warnung,) = k.warnungen
    assert "08/2026" in warnung and "berichtigte Voranmeldung" in warnung
    assert k2.warnungen == []


@pytest.mark.parametrize("haben", ["8125", "8400"])
def test_ausgewiesene_umsatzsteuer_nicht_per_ohne_steuer_entfernen(make_session, haben):
    """Befund N-M2: Eine Ausgangsrechnung mit ausgewiesener USt — die Steuer wird
    geschuldet, bis die Rechnung berichtigt ist (§ 14c Abs. 1 UStG)."""
    b = buchung(
        status=BuchungStatus.AUTO_GEBUCHT,
        soll="10002",
        haben="8400",
        netto="5000.00",
        steuer="950.00",
        schluessel=3,
        beleg_id=uuid4(),
    )
    anlegen(make_session, b)
    with make_session() as s, pytest.raises(StornoError, match="§ 14c"):
        korrigiere(
            s,
            str(b.id),
            "10002",
            haben,
            ohne_steuer=True,
            grund="doch ig. Lieferung",
            von="erika",
        )


def test_korrektur_auf_automatikkonto_ohne_schluessel_abgelehnt(
    make_session, tmp_path, monkeypatch
):
    """Befund N-M3: 3400 ohne Schlüssel — DATEV rechnete trotzdem 19 % heraus."""
    monkeypatch.chdir(tmp_path)  # die SKR03-Datei kommt aus dem Paket
    tx = umsatz()
    b = buchung(
        tx, status=BuchungStatus.AUTO_GEBUCHT, soll="4360", schluessel=None, steuer=None
    )
    anlegen(make_session, tx, b)
    with make_session() as s, pytest.raises(StornoError, match="Automatikkonto"):
        korrigiere(s, str(b.id), "3400", "1200", von="erika")


def test_ohne_steuer_bei_paragraph_13b_eingangsrechnung(make_session):
    """Befund N-9: ein falsch erkannter § 13b-Fall (Schlüssel 94 auf einer
    Eingangsrechnung) lässt sich mit Grund korrigieren — § 14c betrifft ihn nicht."""
    b = buchung(
        status=BuchungStatus.AUTO_GEBUCHT,
        soll="4610",
        haben="70020",
        netto="50.00",
        steuer=None,
        schluessel=94,
        beleg_id=uuid4(),
    )
    anlegen(make_session, b)
    with make_session() as s:
        k = korrigiere(
            s,
            str(b.id),
            "4610",
            "70020",
            ohne_steuer=True,
            grund="kein § 13b: Leistender im Inland",
            von="erika",
        )
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel is None


@pytest.mark.parametrize("schluessel", [94, 19])
def test_ohne_steuer_bei_13b_und_ig_erwerb_eigener_hinweis(make_session, schluessel):
    """Schlussprüfung M-5: Bei § 13b (94) und ig. Erwerb (19) entfernt --ohne-steuer
    Steuerschuld **und** Vorsteuer — richtig nur, wenn gar kein § 13b-Fall bzw. kein
    ig. Erwerb vorliegt. Die Meldung schlägt deshalb nicht „kein Vorsteuerabzug,
    Rechnung unvollständig“ vor (dann bliebe die Steuer geschuldet), die Korrektur
    warnt, und das Brutto enthält die selbst berechnete Steuer nicht (sie steckt
    nicht im Zahlbetrag): aus 100 € wird keine Verbindlichkeit über 119 €."""
    b = buchung(
        status=BuchungStatus.AUTO_GEBUCHT,
        soll="4900",
        haben="70001",
        netto="100.00",
        steuer="19.00",
        schluessel=schluessel,
        beleg_id=uuid4(),
    )
    anlegen(make_session, b)
    with make_session() as s:
        with pytest.raises(StornoError) as fehler:
            korrigiere(s, str(b.id), "4900", "70001", ohne_steuer=True, von="erika")
        text = str(fehler.value)
        assert "Rechnung unvollständig" not in text
        assert "nur, wenn" in text and "kein" in text
        k = korrigiere(
            s,
            str(b.id),
            "4900",
            "70001",
            ohne_steuer=True,
            grund="Leistender im Inland, kein § 13b",
            von="erika",
        )
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel is None
    assert k.neu.betrag_netto == Decimal("100.00")  # nicht 119
    assert any("§ 13b Abs. 5" in w and "§ 15 Abs. 1" in w for w in k.warnungen)


def test_gleichzeitiges_storno_meldet_klar(make_session, monkeypatch):
    """Schlussprüfung T-N4: Zwei Prozesse stornieren dieselbe Buchung; der zweite
    hatte sie vor dem Commit des ersten gelesen. Die Unique-Indizes verhindern das
    zweite Storno — gemeldet als StornoError, nicht als IntegrityError-Traceback."""
    import accounti.pruefung.storno as storno_modul

    b = buchung(status=BuchungStatus.GEPRUEFT, steuer=None, schluessel=None)
    anlegen(make_session, b)
    with make_session() as s:
        alt = storno_modul._lade(s, str(b.id))  # noqa: SLF001 — Stand vor dem Storno
    with make_session() as s:
        storniere(s, str(b.id), grund="doppelt", von="erika")
        s.commit()
    monkeypatch.setattr(storno_modul, "_lade", lambda _s, _id: alt)
    with make_session() as s, pytest.raises(StornoError, match="inzwischen"):
        storniere(s, str(b.id), grund="doppelt", von="jan")
