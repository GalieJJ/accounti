"""Kreditkarten: eigenes Konto, PDF-Abrechnung, Abgleich der Sammelbelastung."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.bank.einstellungen import KreditkartenEinstellungen
from accounti.bank.kreditkarte import (
    KreditkartenError,
    bilde_abrechnung,
    gleiche_sammelbelastungen_ab,
    letzter_stichtag,
    loese_zuordnung,
    richte_karte_ein,
    trenne_belastung,
    uebernimm_abrechnung,
)
from accounti.bank.lauf import speichere_neue
from accounti.bank.provider import BANK_PROVIDER
from accounti.belege.erkennung import BelegErkenner
from accounti.belege.kanaele import RohBeleg
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db import init_db, session_factory
from accounti.db.repo_bank import abgerechnete_transaktion_ids, lade_abrechnungen
from accounti.db.repository import (
    lade_bankkonto,
    lade_buchungen,
    lade_transaktionen,
    setze_status,
    speichere_bankkonto,
    speichere_beleg,
    speichere_buchung,
)
from accounti.db.tabellen_bank import KreditkarteRow
from accounti.klassifikation.engine import (
    KlassifikationsEngine,
    Regel,
    RegelwerkEngine,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Bankkonto,
    Beleg,
    Belegart,
    Belegposition,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.bank import AbrechnungStatus

GIRO = "DE02120300000000202051"
BEISPIEL = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "belege"
    / "kreditkarte_12_umsaetze.txt"
)
SKR03 = Buchhaltung()
EINST = KreditkartenEinstellungen()


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'k.db'}")
    init_db(engine)
    with factory() as s:
        speichere_bankkonto(s, Bankkonto(iban=GIRO, bezeichnung="Giro"))
        s.commit()
    yield factory
    engine.dispose()


def _karte(s, kennung="VISA1234", provider="abrechnung", **kw):
    karte, _ = richte_karte_ein(
        s,
        girokonto=GIRO,
        kennung=kennung,
        bezeichnung=f"Karte {kennung}",
        sachkonto=kw.pop("sachkonto", "1730"),
        provider=provider,
        **kw,
    )
    return karte


def _eingerichtet_am(s, karte, wann):
    """Die Karte wurde zu ``wann`` eingerichtet (statt jetzt)."""
    s.get(KreditkarteRow, str(karte.id)).erstellt_am = wann
    s.flush()
    return karte.model_copy(update={"erstellt_am": wann})


def _beispielbeleg(s, text=None):
    """Die Kreditkartenabrechnung aus examples/, durch die echte Belegerkennung."""
    inhalt = (text or BEISPIEL.read_text(encoding="utf-8")).encode()
    roh = RohBeleg(
        dateiname="visa-maerz.txt", inhalt=inhalt, kanal="upload", herkunft="t"
    )
    leer = Beleg(
        datei_hash=str(abs(hash(inhalt))).ljust(64, "0"),
        dateiname=roh.dateiname,
        kanal=roh.kanal,
        herkunft=roh.herkunft,
        aufbewahren_bis=date(2036, 12, 31),
    )
    beleg = BelegErkenner()(roh, leer)
    assert (
        beleg.belegart is Belegart.KONTOAUSZUG and beleg.status is BelegStatus.ERFASST
    )
    speichere_beleg(s, beleg)
    return beleg


def _umsatz(betrag, tag, text, monat=4, **kw):
    return Transaktion(
        datum=date(2026, monat, tag),
        betrag=Decimal(betrag),
        verwendungszweck=text,
        quelle=TransaktionQuelle.BANK,
        rohtext=text,
        **kw,
    )


def _auf_konto(s, iban, *umsaetze):
    konto = lade_bankkonto(s, iban)
    speichere_neue(s, list(umsaetze), konto.iban, konto)


def _belastung(
    s, betrag="-698.65", tag=5, text="KREDITKARTENABRECHNUNG 4111XXXXXXXX1234", monat=4
):
    umsatz = _umsatz(betrag, tag, text, monat=monat, gegenkonto_name="Musterbank AG")
    _auf_konto(s, GIRO, umsatz)


def _buchungen_zu(s, text):
    tx = {t.id: t for t in lade_transaktionen(s)}
    return [
        b
        for b in lade_buchungen(s)
        if b.transaktion_id and text in tx[b.transaktion_id].verwendungszweck
    ]


# --- Einrichtung ---------------------------------------------------------------


def test_karte_ist_ein_eigenes_konto_mit_eigenem_sachkonto(make_session):
    with make_session() as s:
        karte, konto = richte_karte_ein(
            s,
            girokonto=GIRO,
            kennung="visa 1234",
            bezeichnung="Visa Firma",
            sachkonto="1730",
            endziffern="1234",
            abrechnungstag=20,
        )
        s.commit()
        assert (konto.iban, konto.sachkonto, konto.provider) == (
            "VISA1234",
            "1730",
            "abrechnung",
        )
        assert karte.bankkonto_id == konto.id
        assert karte.girokonto_id == lade_bankkonto(s, GIRO).id
        assert (
            BANK_PROVIDER["abrechnung"]().abrufen(konto, {}, None).transaktionen == []
        )


def test_vorhandenes_konto_wird_zur_karte(make_session):
    with make_session() as s:
        speichere_bankkonto(
            s,
            Bankkonto(
                iban="AMEX0001",
                bezeichnung="Amex",
                sachkonto="1731",
                einstellungen={"ordner": "/tmp"},
            ),
        )
        karte, konto = richte_karte_ein(s, girokonto=GIRO, konto="AMEX0001")
        assert konto.provider == "datei" and karte.bankkonto_id == konto.id


@pytest.mark.parametrize(
    ("kw", "grund"),
    [
        ({"girokonto": "DE89370400440532013000"}, "DE89370400440532013000"),
        ({"sachkonto": "1200"}, "eigenes Sachkonto"),
        ({"kennung": GIRO}, "Girokonto"),
        ({"endziffern": "12a4"}, "Endziffern"),
        ({"muster": "(kaputt"}, "Muster"),
        ({"provider": "fints"}, "fints einrichten"),
        ({"provider": "gibtsnicht"}, "gibtsnicht"),
        ({"sachkonto": None}, "Sachkonto"),
    ],
)
def test_einrichtung_prueft(make_session, kw, grund):
    werte = {
        "girokonto": GIRO,
        "kennung": "VISA1234",
        "bezeichnung": "Visa",
        "sachkonto": "1730",
    }
    werte.update(kw)
    with make_session() as s, pytest.raises(KreditkartenError, match=grund):
        richte_karte_ein(s, **werte)


# --- PDF-Abrechnung ------------------------------------------------------------


def test_pdf_abrechnung_wird_zu_umsaetzen_am_kartenkonto(make_session):
    with make_session() as s:
        karte = _karte(s)
        beleg = _beispielbeleg(s)
        ergebnis = uebernimm_abrechnung(s, str(beleg.id)[:8], karte, EINST)
        s.commit()
        a = ergebnis.abrechnung
        assert (ergebnis.neu, ergebnis.doppelt, ergebnis.ausgleich) == (12, 0, 0)
        assert (a.summe, a.anzahl, a.stichtag) == (
            Decimal("-698.65"),
            12,
            date(2026, 3, 31),
        )
        assert (a.von, a.beleg_id, a.status) == (
            date(2026, 3, 2),
            beleg.id,
            AbrechnungStatus.OFFEN,
        )
        konto = lade_bankkonto(s, "VISA1234")
        umsaetze = [t for t in lade_transaktionen(s) if t.bankkonto_id == konto.id]
        assert len(umsaetze) == 12
        assert all(t.sachkonto == "1730" for t in umsaetze)
        gutschrift = next(t for t in umsaetze if "GUTSCHRIFT" in t.verwendungszweck)
        assert gutschrift.betrag == Decimal("23.99")
        with pytest.raises(KreditkartenError, match="schon übernommen"):
            uebernimm_abrechnung(s, str(beleg.id), karte, EINST)


def test_ausgleich_der_vorperiode_ist_kein_einzelumsatz(make_session):
    text = BEISPIEL.read_text(encoding="utf-8").replace(
        "Saldo Vormonat                                                   0,00",
        "01.03.  01.03.  IHRE ZAHLUNG - DANKE                            500,00+",
    )
    with make_session() as s:
        karte = _karte(s)
        beleg = _beispielbeleg(s, text)
        ergebnis = uebernimm_abrechnung(s, str(beleg.id), karte, EINST)
        assert (ergebnis.neu, ergebnis.ausgleich) == (12, 1)
        assert ergebnis.abrechnung.summe == Decimal("-698.65")


def test_nur_kreditkartenabrechnungen(make_session):
    with make_session() as s:
        karte = _karte(s)
        quittung = Beleg(
            belegart=Belegart.QUITTUNG,
            datei_hash="q" * 64,
            dateiname="q.pdf",
            kanal="upload",
            herkunft="t",
            aufbewahren_bis=date(2036, 12, 31),
            status=BelegStatus.ERFASST,
        )
        quittung = quittung.model_copy(
            update={
                "positionen": [
                    Belegposition(beleg_id=quittung.id, bezeichnung="x", netto=1)
                ]
            }
        )
        speichere_beleg(s, quittung)
        with pytest.raises(KreditkartenError, match="keine Kreditkartenabrechnung"):
            uebernimm_abrechnung(s, str(quittung.id), karte, EINST)
        with pytest.raises(KreditkartenError, match="Kein Beleg"):
            uebernimm_abrechnung(s, "ffffffff", karte, EINST)


# --- Sammelbelastung -----------------------------------------------------------


def _uebernommen(s, **kw):
    karte = _karte(s, **kw)
    uebernimm_abrechnung(s, str(_beispielbeleg(s).id), karte, EINST)
    return karte


def test_sammelbelastung_gleich_summe_wird_gebucht(make_session):
    with make_session() as s:
        _uebernommen(s, endziffern="1234")
        _belastung(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        s.commit()
        (a,) = ergebnis.abgeglichen
        assert (a.status, a.differenz, a.befund) == (
            AbrechnungStatus.ABGEGLICHEN,
            Decimal("0"),
            None,
        )
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        assert (b.soll_konto, b.haben_konto, b.betrag_netto) == (
            "1730",
            "1200",
            Decimal("698.65"),
        )
        assert (b.status, b.confidence, b.beleg_id) == (
            BuchungStatus.AUTO_GEBUCHT,
            1.0,
            a.beleg_id,
        )
        assert b.steuer_betrag is None

        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)  # idempotent
        assert zweiter.abgeglichen == zweiter.abweichungen == []
        assert len(_buchungen_zu(s, "KREDITKARTENABRECHNUNG")) == 1


def test_ein_cent_abweichung_ist_ein_befund_kein_rundungsposten(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-698.66")
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        s.commit()
        (a,) = ergebnis.abweichungen
        assert a.status is AbrechnungStatus.ABWEICHUNG
        assert a.differenz == Decimal("-0.01")
        assert "Differenz -0,01 €" in (a.befund or "")
        assert "Rundungsposten" in (a.befund or "")
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        assert (b.betrag_netto, b.status) == (
            Decimal("698.66"),
            BuchungStatus.ZUR_PRUEFUNG,
        )
        assert not any(x.betrag_netto == Decimal("0.01") for x in lade_buchungen(s))
        (gespeichert,) = lade_abrechnungen(s, status={AbrechnungStatus.ABWEICHUNG})
        assert gespeichert.befund == a.befund


def test_ohne_abrechnung_wird_nichts_gebucht(make_session):
    with make_session() as s:
        _karte(s)
        _belastung(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert [t.betrag for t in ergebnis.ohne_abrechnung] == [Decimal("-698.65")]
        assert lade_buchungen(s) == []


def test_alte_schon_gebuchte_belastungen_ohne_abrechnung_bleiben_still(make_session):
    """Wer die Karte nachträglich einrichtet, hat frühere Sammelbelastungen längst
    gebucht — sie sollen nicht bei jedem Lauf als „ohne Abrechnung“ auftauchen."""
    with make_session() as s:
        _karte(s)
        _belastung(s, tag=5, monat=1)
        tx = next(
            t for t in lade_transaktionen(s) if "KREDITKARTEN" in t.verwendungszweck
        )
        speichere_buchung(
            s,
            Buchungssatz(
                transaktion_id=tx.id,
                datum=tx.datum,
                soll_konto="1730",
                haben_konto="1200",
                betrag_netto=Decimal("698.65"),
                buchungstext="früher gebucht",
            ),
        )
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert ergebnis.ohne_abrechnung == [] and ergebnis.mehrdeutig == []


def test_belastung_ausserhalb_des_fensters(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, tag=30, text="KREDITKARTENABRECHNUNG", monat=5)  # 60 Tage
        _belastung(s, tag=30, text="KREDITKARTENABRECHNUNG", monat=3)  # vor Stichtag
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(ergebnis.ohne_abrechnung) == 2
        assert lade_buchungen(s) == []


def test_andere_karte_per_endziffern_und_fremde_lastschriften(make_session):
    with make_session() as s:
        _uebernommen(s, endziffern="9999")
        _belastung(s)  # nennt ...1234
        _auf_konto(s, GIRO, _umsatz("-698.65", 6, "Miete April"))
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert ergebnis.abgeglichen == ergebnis.ohne_abrechnung == []
        assert lade_buchungen(s) == []


def test_zwei_belastungen_eine_abrechnung_ohne_exakten_treffer_ist_mehrdeutig(
    make_session,
):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-698.60", tag=5)
        _belastung(s, "-698.70", tag=6)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(ergebnis.mehrdeutig) == 2
        assert lade_buchungen(s) == []


def test_exakter_treffer_gewinnt_gegen_den_ungefaehren(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-698.60", tag=4)
        _belastung(s, "-698.65", tag=6)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = ergebnis.abgeglichen
        assert a.belastung_betrag == Decimal("-698.65")
        assert [t.betrag for t in ergebnis.ohne_abrechnung] == [Decimal("-698.60")]


def test_schon_anders_gebucht_wird_zum_befund(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s)
        tx = next(
            t for t in lade_transaktionen(s) if "KREDITKARTEN" in t.verwendungszweck
        )
        speichere_buchung(
            s,
            Buchungssatz(
                transaktion_id=tx.id,
                datum=tx.datum,
                soll_konto="4900",
                haben_konto="1200",
                betrag_netto=Decimal("698.65"),
                buchungstext="Regel",
            ),
        )
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = ergebnis.abweichungen
        assert "anders gebucht" in (a.befund or "") and "4900" in (a.befund or "")
        assert len(_buchungen_zu(s, "KREDITKARTENABRECHNUNG")) == 1


def test_pdf_abrechnung_wird_bei_einer_karte_von_selbst_uebernommen(make_session):
    with make_session() as s:
        _karte(s)
        _beispielbeleg(s)
        _belastung(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(ergebnis.uebernommen) == 1
        assert len(ergebnis.abgeglichen) == 1
        # bei zwei PDF-Karten wird nicht geraten
        _karte(s, kennung="MC5678")
        _beispielbeleg(s, BEISPIEL.read_text(encoding="utf-8") + "\n")
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert zweiter.uebernommen == []
        assert any("kreditkarte uebernehmen" in h for h in zweiter.hinweise)


def test_neben_einer_abrufkarte_wird_eine_pdf_abrechnung_nicht_geraten(make_session):
    """Auch die PDF einer Karte mit Abruf landet zur Aufbewahrung in den Belegen —
    sie darf nicht von selbst bei der PDF-Karte landen."""
    with make_session() as s:
        _karte(s)
        _abrufkarte(s)
        _beispielbeleg(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert ergebnis.uebernommen == []
        assert any("kreditkarte uebernehmen" in h for h in ergebnis.hinweise)


def test_einzelumsaetze_kontiert_classify_gegen_das_kartenkonto(make_session):
    regel = Regel(
        name="aws",
        muster="AWS",
        feld="verwendungszweck",
        soll_konto="4964",
        haben_konto="1200",
        buchungstext="AWS",
    )
    engine = KlassifikationsEngine(regelwerk=RegelwerkEngine([regel]))
    with make_session() as s:
        _uebernommen(s)
        _belastung(s)
        gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        lauf = kontiere_umsaetze(s, engine, SKR03)
        (aws,) = _buchungen_zu(s, "AWS")
        assert (aws.soll_konto, aws.haben_konto) == ("4964", "1730")
        assert len(_buchungen_zu(s, "KREDITKARTENABRECHNUNG")) == 1  # nicht doppelt
        assert lauf.kontiert == 1


# --- Karten mit Abruf: Abrechnungstag und Geldtransit -----------------------------


def _abrufkarte(s, abrechnungstag=20):
    speichere_bankkonto(
        s,
        Bankkonto(
            iban="DKBVISA9",
            bezeichnung="Visa DKB",
            sachkonto="1732",
            einstellungen={"ordner": "/tmp"},
        ),
    )
    karte, _ = richte_karte_ein(
        s, girokonto=GIRO, konto="DKBVISA9", abrechnungstag=abrechnungstag
    )
    _auf_konto(
        s,
        "DKBVISA9",
        _umsatz("-100.00", 2, "HOTEL KIEL", monat=3),
        _umsatz("-50.00", 20, "BAHN", monat=3),
        _umsatz("-7.00", 22, "KAFFEE", monat=3),  # nach dem Stichtag 20.03.
        _umsatz("120.00", 25, "ZAHLUNG ERHALTEN - DANKE", monat=2),  # Vorperiode
    )
    return karte


def test_abrechnung_aus_dem_abrechnungstag_und_geldtransit(make_session):
    with make_session() as s:
        _abrufkarte(s)
        _belastung(s, "-150.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        s.commit()
        (a,) = ergebnis.abgeglichen
        assert (a.stichtag, a.summe, a.anzahl) == (
            date(2026, 3, 20),
            Decimal("-150"),
            2,
        )
        (giro,) = _buchungen_zu(s, "VISA DKB")
        assert (giro.soll_konto, giro.haben_konto) == ("1360", "1200")
        (ausgleich,) = _buchungen_zu(s, "ZAHLUNG ERHALTEN")
        assert (
            ausgleich.soll_konto,
            ausgleich.haben_konto,
            ausgleich.betrag_netto,
        ) == (
            "1732",
            "1360",
            Decimal("120.00"),
        )
        assert ergebnis.ausgleich_gebucht == 1
        # der Kaffee nach dem Stichtag gehört zur nächsten Abrechnung
        naechste = bilde_abrechnung(s, lade_karte(s), date(2026, 4, 20), EINST)
        assert (naechste.summe, naechste.anzahl) == (Decimal("-7.00"), 1)


def lade_karte(s):
    from accounti.db.repo_bank import lade_kreditkarte

    return lade_kreditkarte(s, "DKBVISA9")


def test_geldtransit_nach_kontenrahmen(make_session):
    with make_session() as s:
        _abrufkarte(s)
        _belastung(s, "-150.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        gleiche_sammelbelastungen_ab(s, Buchhaltung(kontenrahmen="SKR04"), EINST)
        (giro,) = _buchungen_zu(s, "VISA DKB")
        assert giro.soll_konto == "1460"


def test_abrechnung_von_hand(make_session):
    with make_session() as s:
        karte = _abrufkarte(s, abrechnungstag=None)
        a = bilde_abrechnung(s, karte, date(2026, 3, 21), EINST)
        assert (a.summe, a.anzahl, a.von) == (Decimal("-150.00"), 2, None)
        with pytest.raises(KreditkartenError, match="Stichtag"):
            bilde_abrechnung(s, karte, date(2026, 3, 21), EINST)
        b = bilde_abrechnung(s, karte, date(2026, 3, 22), EINST)
        assert (b.summe, b.von) == (Decimal("-7.00"), date(2026, 3, 22))
        assert bilde_abrechnung(s, karte, date(2026, 3, 30), EINST) is None


@pytest.mark.parametrize(
    ("datum", "tag", "stichtag"),
    [
        (date(2026, 3, 25), 20, date(2026, 3, 20)),
        (date(2026, 3, 20), 20, date(2026, 3, 20)),
        (date(2026, 3, 5), 20, date(2026, 2, 20)),
        (date(2026, 3, 5), 31, date(2026, 2, 28)),
        (date(2026, 1, 5), 20, date(2025, 12, 20)),
    ],
)
def test_letzter_stichtag(datum, tag, stichtag):
    assert letzter_stichtag(datum, tag) == stichtag


# --- Im geplanten Lauf ---------------------------------------------------------

GIRO_APRIL = "\r\n".join(
    [
        ":20:STARTUMSE",
        ":25:12030000/0000202051",
        ":28C:00004/001",
        ":60F:C260401EUR5000,00",
        ":61:2604050405DR698,65NDDTNONREF//2604050000099",
        ":86:105?00LASTSCHRIFT?20KREDITKARTENABRECHNUNG?21 4111XXXXXXXX1234"
        "?32Musterbank AG",
        ":62F:C260405EUR4301,35",
        "-",
    ]
)


def test_bank_lauf_gleicht_karten_vor_dem_kontieren_ab(make_session, tmp_path):
    """Girokonto per Datei-Provider (MT940), Karte per PDF-Abrechnung: der Lauf
    übernimmt die Abrechnung, bucht die Sammelbelastung auf das Kartenkonto und
    kontiert nur noch die Einzelumsätze — eine gierige Regel bekommt die
    Sammelbelastung nicht mehr zu sehen."""
    from accounti.bank.einstellungen import BankEinstellungen
    from accounti.bank.lauf import bank_lauf
    from accounti.db.repository import aktualisiere_bankkonto

    ordner = tmp_path / "giro"
    ordner.mkdir()
    (ordner / "april.sta").write_bytes(GIRO_APRIL.encode("cp1252"))
    with make_session() as s:
        giro = lade_bankkonto(s, GIRO)
        aktualisiere_bankkonto(
            s, giro.model_copy(update={"einstellungen": {"ordner": str(ordner)}})
        )
        _karte(s, endziffern="1234")
        _beispielbeleg(s)
        s.commit()
    alles = Regel(name="alles", muster=".", soll_konto="4900", haben_konto="1200")
    engine = KlassifikationsEngine(regelwerk=RegelwerkEngine([alles]))
    with make_session() as s:
        lauf = bank_lauf(s, engine, SKR03, bank_einstellungen=BankEinstellungen())
        s.commit()
        assert lauf.abrufe[0].neu == 1
        karten = lauf.kreditkarten
        assert (len(karten.uebernommen), len(karten.abgeglichen)) == (1, 1)
        assert lauf.kontierung.kontiert == 12
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        assert (b.soll_konto, b.haben_konto) == ("1730", "1200")
        assert all(
            x.haben_konto == "1730" for x in lade_buchungen(s) if x.soll_konto == "4900"
        )


# --- PDF-Abrechnungen aus der Zeit vor der Karte --------------------------------

ALLES = Regel(name="alles", muster=".", soll_konto="4900", haben_konto="1200")


def test_alte_abrechnung_mit_schon_gebuchter_belastung_wird_nicht_uebernommen(
    make_session,
):
    """Die Belegerfassung hatte die März-Abrechnung schon, die Sammelbelastung ist
    längst per Regel als Aufwand gebucht; danach wird die Karte eingerichtet. Von
    selbst übernommen, buchte classify die zwölf Einzelumsätze ein zweites Mal als
    Aufwand."""
    engine = KlassifikationsEngine(regelwerk=RegelwerkEngine([ALLES]))
    with make_session() as s:
        beleg = _beispielbeleg(s)
        _belastung(s)
        kontiere_umsaetze(s, engine, SKR03)  # damals: als Aufwand gebucht
        karte = _karte(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        kontiere_umsaetze(s, engine, SKR03)
        assert ergebnis.uebernommen == []
        (hinweis,) = [h for h in ergebnis.hinweise if str(beleg.id)[:8] in h]
        assert "schon gebucht" in hinweis and "4900" in hinweis
        assert len([b for b in lade_buchungen(s) if b.soll_konto == "4900"]) == 1
        # von Hand nur ausdrücklich
        with pytest.raises(KreditkartenError, match="schon gebucht"):
            uebernimm_abrechnung(s, str(beleg.id), karte, EINST)
        u = uebernimm_abrechnung(s, str(beleg.id), karte, EINST, trotzdem=True)
        assert any("4900" in w for w in u.warnungen)


def test_alte_abrechnung_ohne_offene_belastung_nur_von_hand(make_session):
    with make_session() as s:
        karte = _karte(s)  # heute eingerichtet, Abrechnung zum 31.03.2026
        beleg = _beispielbeleg(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert ergebnis.uebernommen == []
        assert any("vor der Einrichtung" in h for h in ergebnis.hinweise)
        assert lade_transaktionen(s) == []
        u = uebernimm_abrechnung(s, str(beleg.id), karte, EINST)
        assert any("vor der Einrichtung" in w for w in u.warnungen)
        assert u.neu == 12


def test_abrechnung_nach_der_einrichtung_wird_von_selbst_uebernommen(make_session):
    with make_session() as s:
        _eingerichtet_am(s, _karte(s), datetime(2026, 3, 1, 9, 0))
        _beispielbeleg(s)
        ergebnis = gleiche_sammelbelastungen_ab(s, SKR03, EINST)  # Belastung folgt
        assert len(ergebnis.uebernommen) == 1
        assert ergebnis.uebernommen[0].warnungen == []


# --- Zuordnung über mehrere Läufe -------------------------------------------------


def test_debitkartenzahlung_ist_keine_sammelbelastung(make_session):
    """Visa- und Mastercard-Debitkarten sind auf Girokonten verbreitet — ihr Text
    nennt „Visa“, sie sind aber Einzelzahlungen, keine Kartenabrechnung."""
    with make_session() as s:
        _uebernommen(s)
        _auf_konto(
            s, GIRO, _umsatz("-12.50", 2, "VISA Debitkartenumsatz REWE MARKT KIEL")
        )
        _auf_konto(s, GIRO, _umsatz("-45.00", 3, "VISA Debit SHELL TANKSTELLE KIEL"))
        erster = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert erster.abweichungen == erster.ohne_abrechnung == erster.mehrdeutig == []
        assert lade_buchungen(s) == []
        _belastung(s)
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(zweiter.abgeglichen) == 1


def test_spaeter_exakter_treffer_loest_die_vorlaeufige_zuordnung(make_session):
    """Lauf 1 kennt nur eine ungefähre Belastung (Jahresgebühr), Lauf 2 bringt
    die centgenaue Sammelbelastung: exakt gewinnt — auch über Läufe hinweg."""
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-29.00", tag=2, text="VISA JAHRESGEBUEHR")
        erster = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = erster.abweichungen
        assert a.belastung_betrag == Decimal("-29.00")
        (vorlaeufig,) = _buchungen_zu(s, "JAHRESGEBUEHR")
        assert vorlaeufig.status is BuchungStatus.ZUR_PRUEFUNG

        _belastung(s)  # die echte Sammelbelastung am 05.04.
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = zweiter.abgeglichen
        assert (a.belastung_betrag, a.befund) == (Decimal("-698.65"), None)
        assert [t.betrag for t in zweiter.geloest] == [Decimal("-29.00")]
        assert zweiter.ohne_abrechnung == []
        assert _buchungen_zu(s, "JAHRESGEBUEHR") == []  # vorläufige Buchung gelöst
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        assert (b.status, b.soll_konto) == (BuchungStatus.AUTO_GEBUCHT, "1730")
        dritter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)  # stabil
        assert dritter.abgeglichen == dritter.abweichungen == dritter.geloest == []


def test_zweiter_ungefaehrer_kandidat_in_spaeterem_lauf_macht_mehrdeutig(
    make_session,
):
    """Dasselbe Ergebnis wie mit beiden Belastungen in einem Lauf."""
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-698.60", tag=4)
        assert len(gleiche_sammelbelastungen_ab(s, SKR03, EINST).abweichungen) == 1
        _belastung(s, "-698.70", tag=6)
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(zweiter.mehrdeutig) == 2
        assert lade_buchungen(s) == []
        (a,) = lade_abrechnungen(s)
        assert (a.status, a.belastung_id) == (AbrechnungStatus.OFFEN, None)


def test_bestaetigte_abweichung_bleibt_bestehen(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-698.66")
        gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        setze_status(s, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von="mensch")
        _belastung(s, tag=7)  # centgenau, aber zu spät: die Abweichung ist geprüft
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert zweiter.abgeglichen == [] and zweiter.geloest == []
        (a,) = lade_abrechnungen(s)
        assert a.belastung_betrag == Decimal("-698.66")


def test_zuordnung_von_hand_loesen(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-29.00", tag=2, text="VISA JAHRESGEBUEHR")
        (a,) = gleiche_sammelbelastungen_ab(s, SKR03, EINST).abweichungen
        abrechnung, tx = loese_zuordnung(s, str(a.id)[:8], SKR03, EINST)
        assert (abrechnung.status, abrechnung.belastung_id) == (
            AbrechnungStatus.OFFEN,
            None,
        )
        assert tx.betrag == Decimal("-29.00")
        assert lade_buchungen(s) == []
        # nicht wieder vorgeschlagen, und auch nicht als „ohne Abrechnung“
        wieder = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert wieder.abweichungen == wieder.ohne_abrechnung == []
        _belastung(s)
        assert len(gleiche_sammelbelastungen_ab(s, SKR03, EINST).abgeglichen) == 1
        with pytest.raises(KreditkartenError, match="automatisch"):
            loese_zuordnung(s, str(a.id), SKR03, EINST)  # exakt, freigegeben


def test_geloest_wird_nur_was_noch_nicht_geprueft_ist(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-698.66")
        (a,) = gleiche_sammelbelastungen_ab(s, SKR03, EINST).abweichungen
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        setze_status(s, str(b.id), BuchungStatus.EXPORTIERT)
        with pytest.raises(KreditkartenError, match="exportiert"):
            loese_zuordnung(s, str(a.id), SKR03, EINST)
        with pytest.raises(KreditkartenError, match="Keine Abrechnung"):
            loese_zuordnung(s, "ffffffff", SKR03, EINST)


# --- Karten mit Abruf: spät kommende Umsätze, Ausgleich ----------------------------


def _nur_abrufkarte(s, *umsaetze, abrechnungstag=20):
    speichere_bankkonto(
        s,
        Bankkonto(
            iban="DKBVISA9",
            bezeichnung="Visa DKB",
            sachkonto="1732",
            einstellungen={"ordner": "/tmp"},
        ),
    )
    karte, _ = richte_karte_ein(
        s, girokonto=GIRO, konto="DKBVISA9", abrechnungstag=abrechnungstag
    )
    if umsaetze:
        _auf_konto(s, "DKBVISA9", *umsaetze)
    return karte


def test_spaet_kommende_kartenumsaetze_werden_nachgetragen(make_session):
    """Das Girokonto kommt täglich, die Kartenumsätze monatlich per Datei: Die
    Abrechnung wird gebildet, bevor alle Umsätze bis zum Stichtag da sind."""
    with make_session() as s:
        _nur_abrufkarte(s, _umsatz("-100.00", 2, "HOTEL KIEL", monat=3))
        _belastung(s, "-150.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        erster = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = erster.abweichungen
        assert a.summe == Decimal("-100.00")
        (giro,) = _buchungen_zu(s, "VISA DKB")
        assert giro.status is BuchungStatus.ZUR_PRUEFUNG

        _auf_konto(s, "DKBVISA9", _umsatz("-50.00", 20, "BAHN", monat=3))
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = zweiter.abgeglichen
        assert (a.stichtag, a.summe, a.anzahl, a.befund) == (
            date(2026, 3, 20),
            Decimal("-150.00"),
            2,
            None,
        )
        bahn = next(t for t in lade_transaktionen(s) if t.verwendungszweck == "BAHN")
        assert bahn.id in abgerechnete_transaktion_ids(s)
        (giro,) = _buchungen_zu(s, "VISA DKB")
        assert (giro.status, giro.confidence, giro.soll_konto) == (
            BuchungStatus.AUTO_GEBUCHT,
            1.0,
            "1360",
        )


def test_umsatz_nach_abgeglichener_abrechnung_kommt_in_die_naechste(make_session):
    """Bucht der Herausgeber einen Umsatz erst nach dem Stichtag, steht er in der
    nächsten Abrechnung — er fällt nicht aus jeder heraus."""
    with make_session() as s:
        _nur_abrufkarte(s, _umsatz("-100.00", 2, "HOTEL KIEL", monat=3))
        _belastung(s, "-100.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        assert len(gleiche_sammelbelastungen_ab(s, SKR03, EINST).abgeglichen) == 1
        _auf_konto(
            s,
            "DKBVISA9",
            _umsatz("-50.00", 19, "BAHN", monat=3),  # kam zu spät
            _umsatz("-30.00", 10, "TAXI", monat=4),
        )
        _belastung(s, "-80.00", tag=25, text="VISA DKB ABRECHNUNG", monat=4)
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = zweiter.abgeglichen
        assert (a.stichtag, a.summe, a.anzahl) == (
            date(2026, 4, 20),
            Decimal("-80.00"),
            2,
        )


def test_ausgleich_nur_mit_gleich_hoher_sammelbelastung_automatisch(make_session):
    """Die Ausgleichszeile auf dem Kartenkonto wird nur dann automatisch gegen
    Geldtransit gebucht, wenn dort eine gleich hohe Sammelbelastung dieser Karte
    steht — sonst bliebe Geldtransit offen (anderes Konto, Einlage, Abweichung)."""
    with make_session() as s:
        _nur_abrufkarte(
            s,
            _umsatz("-150.00", 2, "HOTEL KIEL", monat=3),
            _umsatz("150.00", 27, "LASTSCHRIFT AUSGLEICH", monat=3),
            _umsatz("120.00", 25, "ZAHLUNG ERHALTEN - DANKE", monat=2),
        )
        erster = gleiche_sammelbelastungen_ab(s, SKR03, EINST)  # Belastung fehlt
        assert erster.ausgleich_gebucht == 2
        assert {t.betrag for t in erster.ausgleich_ohne_belastung} == {
            Decimal("150.00"),
            Decimal("120.00"),
        }
        assert {b.status for b in lade_buchungen(s)} == {BuchungStatus.ZUR_PRUEFUNG}

        _belastung(s, "-150.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(zweiter.abgeglichen) == 1
        assert zweiter.ausgleich_gebucht == 0 and zweiter.ausgleich_ohne_belastung == []
        (passend,) = _buchungen_zu(s, "LASTSCHRIFT AUSGLEICH")
        assert (
            passend.soll_konto,
            passend.haben_konto,
            passend.status,
            passend.confidence,
        ) == ("1732", "1360", BuchungStatus.AUTO_GEBUCHT, 1.0)
        (vorperiode,) = _buchungen_zu(s, "ZAHLUNG ERHALTEN")
        assert vorperiode.status is BuchungStatus.ZUR_PRUEFUNG


def _saldo_freigegeben(s, konto):
    """Saldo eines Kontos über die freigegebenen Buchungen (nicht zur Prüfung)."""
    saldo = Decimal("0")
    for b in lade_buchungen(s):
        if b.status in {BuchungStatus.ZUR_PRUEFUNG, BuchungStatus.ENTWURF}:
            continue
        saldo += b.betrag_netto if b.soll_konto == konto else Decimal("0")
        saldo -= b.betrag_netto if b.haben_konto == konto else Decimal("0")
    return saldo


def test_ausgleich_gegen_vorlaeufige_belastung_nur_zur_pruefung(make_session):
    """Ist die gleich hohe Sammelbelastung nur vorläufig zugeordnet (Befund), wird
    der Ausgleich nicht freigegeben: Löst ein späterer Lauf die Zuordnung (zweiter
    Kandidat), entfällt die Buchung der Belastung — ein freigegebener Ausgleich
    ließe Geldtransit offen."""
    with make_session() as s:
        _nur_abrufkarte(
            s,
            _umsatz("-100.00", 2, "HOTEL KIEL", monat=3),
            _umsatz("150.00", 27, "LASTSCHRIFT AUSGLEICH", monat=3),
        )
        _belastung(s, "-150.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        erster = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(erster.abweichungen) == 1
        (giro,) = _buchungen_zu(s, "VISA DKB")
        assert giro.status is BuchungStatus.ZUR_PRUEFUNG
        (ausgleich,) = _buchungen_zu(s, "LASTSCHRIFT AUSGLEICH")
        assert (ausgleich.status, ausgleich.confidence) == (
            BuchungStatus.ZUR_PRUEFUNG,
            0.5,
        )
        assert [t.betrag for t in erster.ausgleich_vorlaeufig] == [Decimal("150.00")]
        assert erster.ausgleich_ohne_belastung == []

        _belastung(s, "-20.00", tag=28, text="VISA DKB JAHRESGEBUEHR", monat=3)
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert len(zweiter.mehrdeutig) == 2
        assert _buchungen_zu(s, "VISA DKB") == []  # vorläufige Buchung gelöst
        (ausgleich,) = _buchungen_zu(s, "LASTSCHRIFT AUSGLEICH")
        assert ausgleich.status is BuchungStatus.ZUR_PRUEFUNG
        assert _saldo_freigegeben(s, "1360") == Decimal("0")


def test_ausgleich_wird_mit_der_gepruefen_belastung_bestaetigt(make_session):
    with make_session() as s:
        _nur_abrufkarte(
            s,
            _umsatz("-100.00", 2, "HOTEL KIEL", monat=3),
            _umsatz("150.00", 27, "LASTSCHRIFT AUSGLEICH", monat=3),
        )
        _belastung(s, "-150.00", tag=25, text="VISA DKB ABRECHNUNG", monat=3)
        gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (giro,) = _buchungen_zu(s, "VISA DKB")
        setze_status(s, str(giro.id), BuchungStatus.GEPRUEFT, geprueft_von="mensch")
        zweiter = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert zweiter.ausgleich_vorlaeufig == zweiter.ausgleich_ohne_belastung == []
        (ausgleich,) = _buchungen_zu(s, "LASTSCHRIFT AUSGLEICH")
        assert (ausgleich.status, ausgleich.confidence) == (
            BuchungStatus.AUTO_GEBUCHT,
            1.0,
        )
        assert _saldo_freigegeben(s, "1360") == Decimal("0")


# --- Mehrdeutig: von Hand entscheiden ----------------------------------------------


def test_mehrdeutig_wird_von_hand_entschieden(make_session):
    """Eine Jahresgebühr passt zum Muster und wird vorläufig zugeordnet; dann kommt
    die echte Sammelbelastung mit Abweichung. Beide sind ab da in jedem Lauf
    mehrdeutig — ohne Entscheidung von Hand bliebe die Abrechnung für immer offen."""
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-29.00", tag=2, text="VISA JAHRESGEBUEHR")
        assert len(gleiche_sammelbelastungen_ab(s, SKR03, EINST).abweichungen) == 1
        _belastung(s, "-703.65", tag=5)
        for _ in range(2):  # bleibt so, Lauf für Lauf
            lauf = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
            assert sorted(t.betrag for t in lauf.mehrdeutig) == [
                Decimal("-703.65"),
                Decimal("-29.00"),
            ]
        (a,) = lade_abrechnungen(s)
        assert a.status is AbrechnungStatus.OFFEN
        gebuehr = next(t for t in lauf.mehrdeutig if t.betrag == Decimal("-29.00"))
        assert [x.id for x in lauf.mehrdeutig_bei[gebuehr.id]] == [a.id]

        abrechnung, tx, war_zugeordnet = trenne_belastung(
            s, str(a.id)[:8], str(gebuehr.id)[:8], SKR03, EINST
        )
        assert (abrechnung.id, tx.id, war_zugeordnet) == (a.id, gebuehr.id, False)
        danach = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (a,) = danach.abweichungen
        assert a.belastung_betrag == Decimal("-703.65")
        assert "Differenz -5,00 €" in (a.befund or "")
        assert danach.mehrdeutig == danach.ohne_abrechnung == []
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        assert b.status is BuchungStatus.ZUR_PRUEFUNG
        assert _buchungen_zu(s, "JAHRESGEBUEHR") == []  # kontiert classify
        stabil = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert stabil.abweichungen == stabil.mehrdeutig == stabil.geloest == []


def test_mehrdeutig_zwischen_zwei_karten_wird_von_hand_abgeglichen(make_session):
    with make_session() as s:
        visa = _karte(s)
        mc = _karte(s, kennung="MC5678")
        uebernimm_abrechnung(s, str(_beispielbeleg(s).id), visa, EINST)
        zweite = _beispielbeleg(s, BEISPIEL.read_text(encoding="utf-8") + "\n")
        uebernimm_abrechnung(s, str(zweite.id), mc, EINST)
        _belastung(s)  # centgenau für beide Karten
        erster = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        (tx,) = erster.mehrdeutig
        assert len(erster.mehrdeutig_bei[tx.id]) == 2
        assert lade_buchungen(s) == []
        von_mc = next(a for a in lade_abrechnungen(s) if a.kreditkarte_id == mc.id)
        trenne_belastung(s, str(von_mc.id), str(tx.id), SKR03, EINST)
        (a,) = gleiche_sammelbelastungen_ab(s, SKR03, EINST).abgeglichen
        assert (a.kreditkarte_id, a.belastung_id) == (visa.id, tx.id)
        (b,) = _buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        assert b.status is BuchungStatus.AUTO_GEBUCHT


def test_trennen_einer_vorlaeufigen_zuordnung_loest_sie(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s, "-29.00", tag=2, text="VISA JAHRESGEBUEHR")
        (a,) = gleiche_sammelbelastungen_ab(s, SKR03, EINST).abweichungen
        abrechnung, tx, war_zugeordnet = trenne_belastung(
            s, str(a.id), str(a.belastung_id), SKR03, EINST
        )
        assert war_zugeordnet and tx.betrag == Decimal("-29.00")
        assert (abrechnung.status, abrechnung.belastung_id) == (
            AbrechnungStatus.OFFEN,
            None,
        )
        assert lade_buchungen(s) == []
        wieder = gleiche_sammelbelastungen_ab(s, SKR03, EINST)
        assert wieder.abweichungen == wieder.ohne_abrechnung == []


def test_trennen_prueft_abrechnung_und_umsatz(make_session):
    with make_session() as s:
        _uebernommen(s)
        _belastung(s)
        (a,) = gleiche_sammelbelastungen_ab(s, SKR03, EINST).abgeglichen
        with pytest.raises(KreditkartenError, match="automatisch"):
            trenne_belastung(s, str(a.id), str(a.belastung_id), SKR03, EINST)
        with pytest.raises(KreditkartenError, match="Kein Umsatz"):
            trenne_belastung(s, str(a.id), "ffffffff", SKR03, EINST)
        with pytest.raises(KreditkartenError, match="Keine Abrechnung"):
            trenne_belastung(s, "ffffffff", str(a.belastung_id), SKR03, EINST)
        kartenumsatz = next(
            t for t in lade_transaktionen(s) if t.id in abgerechnete_transaktion_ids(s)
        )
        with pytest.raises(KreditkartenError, match="keine Belastung des Girokontos"):
            trenne_belastung(s, str(a.id), str(kartenumsatz.id), SKR03, EINST)
