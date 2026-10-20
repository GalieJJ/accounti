"""Kreditkarten: eigenes Konto, PDF-Abrechnung, Abgleich der Sammelbelastung."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.bank.einstellungen import KreditkartenEinstellungen
from accounti.bank.kreditkarte import (
    KreditkartenError,
    bilde_abrechnung,
    gleiche_sammelbelastungen_ab,
    letzter_stichtag,
    richte_karte_ein,
    uebernimm_abrechnung,
)
from accounti.bank.lauf import speichere_neue
from accounti.bank.provider import BANK_PROVIDER
from accounti.belege.erkennung import BelegErkenner
from accounti.belege.kanaele import RohBeleg
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db import init_db, session_factory
from accounti.db.repo_bank import lade_abrechnungen
from accounti.db.repository import (
    lade_bankkonto,
    lade_buchungen,
    lade_transaktionen,
    speichere_bankkonto,
    speichere_beleg,
    speichere_buchung,
)
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
