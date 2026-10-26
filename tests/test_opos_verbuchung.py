from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    lade_kontakte,
    lade_posten,
    speichere_ausgangsrechnung,
    speichere_beleg,
    speichere_kontakt,
)
from accounti.erechnung.ausstellung import stelle_aus
from accounti.klassifikation.engine import Regel, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Beleg,
    Belegart,
    Belegposition,
    Belegrichtung,
    BelegStatus,
    BuchungStatus,
    Kontakt,
    KontaktStatus,
    PostenRichtung,
)
from accounti.opos.verbuchung import verbuche_belege
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos
from tests.test_ustid_protokoll import bestaetige

EINSTELLUNGEN = Buchhaltung()


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def eingangsrechnung(**kw):
    b = Beleg(
        datei_hash="a" * 64,
        dateiname="re.pdf",
        kanal="ordner",
        herkunft="x",
        aufbewahren_bis=date(2036, 12, 31),
        belegart=Belegart.EINGANGSRECHNUNG,
        status=BelegStatus.ERFASST,
        belegnummer="RE-2026-0042",
        belegdatum=date(2026, 3, 5),
        lieferant_name="Bürobedarf Müller GmbH",
        lieferant_ust_id="DE123456789",
        iban="DE89370400440532013000",
        netto=Decimal("150.00"),
        steuer=Decimal("22.50"),
        brutto=Decimal("172.50"),
        zahlungsziel=date(2026, 3, 19),
        skonto_prozent=Decimal("2"),
        skonto_tage=7,
    )
    b.positionen = [
        Belegposition(
            beleg_id=b.id,
            bezeichnung="Papier",
            netto=Decimal("100.00"),
            steuersatz=Decimal("19"),
            steuer_betrag=Decimal("19.00"),
        ),
        Belegposition(
            beleg_id=b.id,
            bezeichnung="Fachbuch",
            netto=Decimal("50.00"),
            steuersatz=Decimal("7"),
            steuer_betrag=Decimal("3.50"),
        ),
    ]
    return b.model_copy(update=kw)


def _verbuche(make_session, archiv=None, regelwerk=None):
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN, archiv=archiv, regelwerk=regelwerk)
        s.commit()
    assert lauf.fehler == []
    return lauf.verbucht


def test_eingangsrechnung_bucht_gegen_kreditor_und_erzeugt_posten(umgebung):
    """Akzeptanz 1."""
    make_session, _ = umgebung
    beleg = eingangsrechnung()
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    (v,) = _verbuche(make_session)
    assert v.kontakt_neu
    with make_session() as s:
        (kontakt,) = lade_kontakte(s)
        buchungen = sorted(lade_buchungen(s), key=lambda b: -b.betrag_netto)
        (posten,) = lade_posten(s)
    assert kontakt.kreditor_konto == "70000"
    assert kontakt.status is KontaktStatus.ZUR_PRUEFUNG
    assert (kontakt.iban, kontakt.ust_id) == ("DE89370400440532013000", "DE123456789")
    assert [
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
        )
        for b in buchungen
    ] == [
        ("4900", "70000", Decimal("100.00"), 9, Decimal("19.00")),
        ("4900", "70000", Decimal("50.00"), 8, Decimal("3.50")),
    ]
    assert all(b.beleg_id == beleg.id and b.transaktion_id is None for b in buchungen)
    assert all(b.beleg_nummer == "RE-2026-0042" for b in buchungen)
    # unbekanntes Sachkonto → zur Prüfung
    assert all(b.status is BuchungStatus.ZUR_PRUEFUNG for b in buchungen)
    assert posten.richtung is PostenRichtung.VERBINDLICHKEIT
    assert posten.kontakt_id == kontakt.id
    assert (posten.betrag, posten.restbetrag) == (Decimal("172.50"), Decimal("172.50"))
    assert posten.faellig_am == date(2026, 3, 19)
    assert posten.skonto_bis == date(2026, 3, 12)
    assert posten.skonto_betrag == Decimal("3.45")


def test_bekannter_kontakt_mit_sachkonto_und_zahlungsbedingungen(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_kontakt(
            s,
            Kontakt(
                name="Bürobedarf Müller",
                kreditor_konto="70001",
                sachkonto="4930",
                zahlungsziel_tage=30,
                skonto_prozent=Decimal("3"),
                skonto_tage=10,
            ),
        )
        speichere_beleg(
            s,
            eingangsrechnung(
                zahlungsziel=None,
                skonto_prozent=None,
                skonto_tage=None,
                lieferant_name="BUEROBEDARF MÜLLER G.m.b.H.",
                lieferant_ust_id=None,
                iban=None,
            ),
        )
        s.commit()
    (v,) = _verbuche(make_session)
    assert not v.kontakt_neu and v.merkmal == "Name"
    with make_session() as s:
        assert len(lade_kontakte(s)) == 1
        buchungen = lade_buchungen(s)
        (posten,) = lade_posten(s)
    assert {(b.soll_konto, b.haben_konto) for b in buchungen} == {("4930", "70001")}
    assert all(b.status is BuchungStatus.AUTO_GEBUCHT for b in buchungen)
    assert posten.faellig_am == date(2026, 4, 4)
    assert (posten.skonto_bis, posten.skonto_betrag) == (
        date(2026, 3, 15),
        Decimal("5.18"),
    )


def test_regelwerk_liefert_das_sachkonto(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung())
        s.commit()
    regelwerk = RegelwerkEngine(
        [
            Regel(
                "buero",
                r"b(ü|ue)robedarf",
                "4930",
                "1200",
                9,
                "Bürobedarf",
                feld="beide",
            )
        ]
    )
    _verbuche(make_session, regelwerk=regelwerk)
    with make_session() as s:
        buchungen = lade_buchungen(s)
    assert {b.soll_konto for b in buchungen} == {"4930"}


def test_schreibvarianten_ergeben_einen_kontakt_und_nichts_doppelt(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung())
        speichere_beleg(
            s,
            eingangsrechnung(
                datei_hash="b" * 64,
                belegnummer="RE-2026-0051",
                lieferant_name="Buerobedarf Mueller",
                lieferant_ust_id=None,
            ),
        )
        speichere_beleg(
            s,
            eingangsrechnung(
                datei_hash="c" * 64,
                belegnummer="RE-2026-0060",
                lieferant_name="Bürobedarf Müller GmbH & Co. KG",
                iban=None,
            ),
        )
        s.commit()
    ergebnis = _verbuche(make_session)
    assert [v.kontakt_neu for v in ergebnis] == [True, False, False]
    assert _verbuche(make_session) == []  # zweiter Lauf: nichts doppelt
    with make_session() as s:
        assert len(lade_kontakte(s)) == 1
        assert len(lade_posten(s)) == 3
        assert len(lade_buchungen(s)) == 6


def test_nur_erfasste_rechnungen_werden_verbucht(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung(status=BelegStatus.ZUR_PRUEFUNG))
        speichere_beleg(
            s, eingangsrechnung(datei_hash="q" * 64, belegart=Belegart.QUITTUNG)
        )
        s.commit()
    assert _verbuche(make_session) == []


def test_gutschrift_dreht_soll_und_haben(umgebung):
    make_session, _ = umgebung
    beleg = eingangsrechnung(
        brutto=Decimal("-119.00"), netto=Decimal("-100.00"), steuer=Decimal("-19.00")
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Gutschrift",
            netto=Decimal("-100.00"),
            steuersatz=Decimal("19"),
            steuer_betrag=Decimal("-19.00"),
        )
    ]
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        (b,) = lade_buchungen(s)
        (p,) = lade_posten(s)
    assert (b.soll_konto, b.haben_konto, b.betrag_netto, b.steuer_betrag) == (
        "70000",
        "4900",
        Decimal("100.00"),
        Decimal("19.00"),
    )
    assert p.betrag == Decimal("-119.00")


def _ausgangsrechnung(make_session, archiv, e):
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2026, 3, 10))
        s.commit()


def test_ausgangsrechnung_bucht_debitor_an_erloes(umgebung):
    make_session, archiv = umgebung
    _ausgangsrechnung(
        make_session,
        archiv,
        entwurf(
            kunde(),
            pos("Bilderrahmen", "250", "4"),
            pos("Katalog", "25", ermaessigt=True),
        ),
    )
    (v,) = _verbuche(make_session, archiv=archiv)
    with make_session() as s:
        (kontakt,) = lade_kontakte(s)
        buchungen = sorted(lade_buchungen(s), key=lambda b: -b.betrag_netto)
        (posten,) = lade_posten(s)
    assert (kontakt.name, kontakt.debitor_konto, kontakt.status) == (
        "Atelier Kundin GmbH",
        "10000",
        KontaktStatus.GEPRUEFT,
    )
    assert kontakt.ust_id == "DE888888888"
    assert [
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
            b.status,
        )
        for b in buchungen
    ] == [
        (
            "10000",
            "8400",
            Decimal("1000.00"),
            3,
            Decimal("190.00"),
            BuchungStatus.AUTO_GEBUCHT,
        ),
        (
            "10000",
            "8300",
            Decimal("25.00"),
            2,
            Decimal("1.75"),
            BuchungStatus.AUTO_GEBUCHT,
        ),
    ]
    assert posten.richtung is PostenRichtung.FORDERUNG
    assert (posten.betrag, posten.faellig_am) == (Decimal("1216.75"), date(2026, 3, 24))
    assert v.beleg.richtung is Belegrichtung.AUSGANG


VORTAG = datetime(2026, 3, 9, 10, 0)


@pytest.mark.parametrize(
    ("k", "position", "erloes"),
    [
        (
            kunde(land="AT", ust_id="ATU12345678"),
            pos("Hängung", "90", "8", sonstige_leistung=True),
            "8336",  # SKR03: EU-Leistung, Empfänger schuldet (8338 = Drittland)
        ),
        (kunde(land="FR", ust_id="FR12345678901"), pos("Rahmen", "100"), "8125"),
        (kunde(land="CH", ust_id=None), pos("Rahmen", "100"), "8120"),
    ],
    ids=["reverse_charge", "ig_lieferung", "ausfuhr"],
)
def test_steuerfreie_erloese(umgebung, k, position, erloes):
    make_session, archiv = umgebung
    if k.ust_id:
        with make_session() as s:
            bestaetige(s, k.ust_id, jetzt=VORTAG)
            s.commit()
    _ausgangsrechnung(make_session, archiv, entwurf(k, position))
    _verbuche(make_session, archiv=archiv)
    with make_session() as s:
        (b,) = lade_buchungen(s)
    assert (b.soll_konto, b.haben_konto, b.steuer_schluessel) == ("10000", erloes, None)
    assert b.status is BuchungStatus.AUTO_GEBUCHT


def test_ungueltig_gewordene_ust_id_geht_zur_pruefung(umgebung):
    """Akzeptanz 7: keine automatische Buchung als steuerfreie ig. Lieferung."""
    make_session, archiv = umgebung
    with make_session() as s:
        bestaetige(s, "FR12345678901", jetzt=VORTAG)
        s.commit()
    _ausgangsrechnung(
        make_session,
        archiv,
        entwurf(kunde(land="FR", ust_id="FR12345678901"), pos("Rahmen", "100")),
    )
    with make_session() as s:  # nach dem Ausstellen, vor dem Verbuchen
        bestaetige(s, "FR12345678901", "evatr-2006", datetime(2026, 3, 11, 9, 0))
        s.commit()
    (v,) = _verbuche(make_session, archiv=archiv)
    (b,) = v.buchungen
    assert (b.haben_konto, b.status) == ("8125", BuchungStatus.ZUR_PRUEFUNG)
    (hinweis,) = v.hinweise
    assert "FR12345678901" in hinweis and "nicht gültig" in hinweis
    assert "pruefe-ustid" in hinweis


def test_fehlerhafter_beleg_haelt_den_lauf_nicht_auf(umgebung):
    make_session, _ = umgebung
    ohne_lieferant = eingangsrechnung(datei_hash="z" * 64, lieferant_name=None)
    with make_session() as s:
        speichere_beleg(s, ohne_lieferant)
        speichere_beleg(s, eingangsrechnung())
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN)
        s.commit()
        assert len(lauf.verbucht) == 1
        ((beleg, grund),) = lauf.fehler
        assert beleg.id == ohne_lieferant.id
        assert "kein Lieferant" in grund
        assert len(lade_posten(s)) == 1


def test_belegbuchung_im_datev_export(umgebung, tmp_path):
    """Kreditor als Gegenkonto, BU-Schlüssel, Bruttobetrag und Belegfeld 1."""
    import csv

    from accounti.export.datev import DATEVConfig, DATEVExporter

    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung())
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        buchungen = lade_buchungen(s)
    datei = DATEVExporter(
        DATEVConfig(berater_nummer="1", mandanten_nummer="2")
    ).exportiere(buchungen, tmp_path)
    zeilen = list(
        csv.reader(datei.read_text(encoding="cp1252").splitlines()[1:], delimiter=";")
    )
    kopf, daten = zeilen[0], zeilen[1:]
    spalte = {name: i for i, name in enumerate(kopf)}
    werte = sorted(
        (
            z[spalte["Umsatz (ohne Soll/Haben-Kz)"]],
            z[spalte["Konto"]],
            z[spalte["Gegenkonto (ohne BU-Schlüssel)"]],
            z[spalte["BU-Schlüssel"]],
            z[spalte["Belegfeld 1"]],
        )
        for z in daten
    )
    assert werte == [
        ("119,00", "4900", "70000", "9", "RE-2026-0042"),
        ("53,50", "4900", "70000", "8", "RE-2026-0042"),
    ]


def test_eigene_firma_wird_nicht_zum_kreditor(umgebung):
    from accounti.kontakte.dienst import Partnerdaten

    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(
            s,
            eingangsrechnung(
                lieferant_name="Galerie Muster GmbH",
                lieferant_ust_id="DE999999999",
                iban=None,
            ),
        )
        s.commit()
    eigene = Partnerdaten(name="Galerie Muster GmbH", ust_id="DE999999999")
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN, eigene_firma=eigene)
        s.commit()
        assert lauf.verbucht == []
        ((_, grund),) = lauf.fehler
        assert "eigene Firma" in grund
        assert lade_kontakte(s) == []


def test_eigene_kennungen_aus_der_konfiguration(tmp_path):
    from accounti.konfiguration import lade_eigene_firma

    pfad = tmp_path / "accounti.yaml"
    assert lade_eigene_firma(pfad) is None
    pfad.write_text(
        'mandant:\n  name: "Galerie Muster GmbH"\n  ust_id: DE999999999\n',
        encoding="utf-8",
    )
    eigene = lade_eigene_firma(pfad)
    assert (eigene.name, eigene.ust_id) == ("Galerie Muster GmbH", "DE999999999")


# --- Gesamttest Paket C: Steuerfall, Vorzeichen, kein Schlüssel, Land, Skonto -----


def _aus_pdf(text, **kw):
    """Beleg, wie ihn die Erkennung aus einem PDF mit diesem Text macht."""
    from accounti.belege.erkennung import BelegErkenner
    from accounti.belege.kanaele import RohBeleg
    from tests.pdf_hilfe import pdf_mit_text

    roh = RohBeleg(
        dateiname="r.pdf", inhalt=pdf_mit_text(text), kanal="upload", herkunft="r.pdf"
    )
    leer = Beleg(
        datei_hash=kw.pop("datei_hash", "d" * 64),
        dateiname="r.pdf",
        kanal="upload",
        herkunft="r.pdf",
        aufbewahren_bis=date(2036, 12, 31),
        eingegangen_am=kw.pop("eingegangen_am", datetime(2026, 4, 3, 9, 0)),
    )
    return BelegErkenner()(roh, leer).model_copy(update=kw)


def _zeilen(buchungen):
    return sorted(
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
            b.status,
        )
        for b in buchungen
    )


def test_reverse_charge_rechnung_bucht_13b_und_meldet_kz_46_47(umgebung):
    """B06/Steuer B4: 0 % mit § 13b-Hinweis → Schlüssel 94 zur Prüfung, Kreditor-Land
    aus der USt-IdNr. (AT) → Kz 46/47/67 statt nichts."""
    from accounti.db.repository import setze_status
    from accounti.steuer.kennziffern import Kontenplan, ermittle
    from accounti.steuer.zeitraum import Zeitraum
    from tests.test_belege_extraktion import REVERSE_CHARGE

    make_session, _ = umgebung
    beleg = _aus_pdf(REVERSE_CHARGE)
    assert beleg.status is BelegStatus.ERFASST, beleg.pruef_grund
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    (v,) = _verbuche(make_session)
    assert v.treffer.kontakt.land == "AT"
    assert any("§ 13b" in h and "46/47" in h for h in v.hinweise)
    assert not any("nicht bestätigt" in h for h in v.hinweise)
    with make_session() as s:
        (b,) = lade_buchungen(s)
        (posten,) = lade_posten(s)
        assert _zeilen([b]) == [
            (
                "4900",
                "70000",
                Decimal("600.00"),
                94,
                Decimal("114.00"),
                BuchungStatus.ZUR_PRUEFUNG,
            )
        ]
        assert posten.betrag == Decimal("600.00")  # die Steuer zahlt man ans FA
        setze_status(s, str(b.id), BuchungStatus.GEPRUEFT)
        s.commit()
        e = ermittle(
            lade_buchungen(s),
            Zeitraum.lies("2026-04"),
            Kontenplan(),
            lade_kontakte(s),
            {p.beleg_id: p.kontakt_id for p in lade_posten(s)},
        )
    assert e.voranmeldung.werte == {
        46: Decimal("600.00"),
        47: Decimal("114.00"),
        67: Decimal("114.00"),
    }


def test_e_rechnung_ae_im_eingang_bekommt_94_ohne_ustid_hinweis(umgebung):
    """Steuer B4: Kategorie AE im Eingang → Schlüssel 94 zur Prüfung; der Hinweis auf
    eine unbestätigte USt-IdNr. gilt nur eigenen Rechnungen (er nannte unsere)."""
    from accounti.db.repository import aktualisiere_beleg, lade_belege

    make_session, archiv = umgebung
    k = kunde(land="AT", ust_id="ATU12345678")
    with make_session() as s:
        bestaetige(s, k.ust_id, jetzt=VORTAG)
        s.commit()
    _ausgangsrechnung(
        make_session,
        archiv,
        entwurf(k, pos("Hängung", "90", "8", sonstige_leistung=True)),
    )
    with make_session() as s:  # dieselbe Datei als empfangene Rechnung
        (b,) = lade_belege(s)
        aktualisiere_beleg(
            s,
            b.model_copy(
                update={
                    "belegart": Belegart.EINGANGSRECHNUNG,
                    "richtung": Belegrichtung.EINGANG,
                }
            ),
        )
        s.commit()
    (v,) = _verbuche(make_session, archiv=archiv)
    (b,) = v.buchungen
    assert (b.steuer_schluessel, b.betrag_netto, b.steuer_betrag, b.status) == (
        94,
        Decimal("720.00"),
        Decimal("136.80"),
        BuchungStatus.ZUR_PRUEFUNG,
    )
    assert not any("USt-IdNr." in h for h in v.hinweise)


def test_steuer_ohne_satz_wird_brutto_gebucht_und_ist_korrigierbar(umgebung):
    """B05: ZUGFeRD MINIMUM — Sammelposition mit Steuer, aber ohne Satz. Nie netto
    gegen einen Brutto-Posten; `korrigiere --steuer 9` ist dann erlaubt."""
    from accounti.pruefung.storno import StornoError, korrigiere

    make_session, _ = umgebung
    beleg = eingangsrechnung(
        netto=Decimal("1000.00"), steuer=Decimal("190.00"), brutto=Decimal("1190.00")
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Gesamtbetrag",
            netto=Decimal("1000.00"),
            steuer_betrag=Decimal("190.00"),
        )
    ]
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        (b,) = lade_buchungen(s)
        (posten,) = lade_posten(s)
        assert _zeilen([b]) == [
            (
                "4900",
                "70000",
                Decimal("1190.00"),
                None,
                None,
                BuchungStatus.ZUR_PRUEFUNG,
            )
        ]
        assert posten.betrag == Decimal("1190.00")
        with pytest.raises(StornoError, match="Grund"):
            korrigiere(s, str(b.id), "4900", "70000", steuer=9)
        k = korrigiere(
            s, str(b.id), "4900", "70000", steuer=9, grund="PDF-Ansicht: 19 % USt"
        )
        s.commit()
    assert (k.neu.betrag_netto, k.neu.steuer_betrag) == (
        Decimal("1000.00"),
        Decimal("190.00"),
    )


def test_lieferantengutschrift_mindert_aufwand_und_vorsteuer(umgebung):
    """B12: Gutschrift −200/−38 → Kreditor an Aufwand mit VSt 38 (Minderung), Posten
    −238 — nicht Aufwand mit +38 Vorsteuer und Posten −162."""
    from tests.test_belege_extraktion import GUTSCHRIFT

    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, _aus_pdf(GUTSCHRIFT))
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        (b,) = lade_buchungen(s)
        (posten,) = lade_posten(s)
    assert (b.soll_konto, b.haben_konto, b.betrag_netto, b.steuer_betrag) == (
        "70000",
        "4900",
        Decimal("200.00"),
        Decimal("38.00"),
    )
    assert posten.betrag == Decimal("-238.00")


def test_ohne_abzug_schlaegt_das_skonto_des_kontakts(umgebung):
    """B09: Die Rechnung sagt „ohne Abzug“ (0 %) — der Posten bekommt kein Skonto."""
    make_session, _ = umgebung
    with make_session() as s:
        speichere_kontakt(
            s,
            Kontakt(
                name="Bürobedarf Müller GmbH",
                kreditor_konto="70000",
                iban="DE89370400440532013000",
                skonto_prozent=Decimal("2"),
                skonto_tage=10,
            ),
        )
        speichere_beleg(s, eingangsrechnung(skonto_prozent=Decimal("0"), skonto_tage=0))
        speichere_beleg(
            s,
            eingangsrechnung(
                datei_hash="b" * 64,
                belegnummer="RE-2026-0043",
                skonto_prozent=None,
                skonto_tage=None,
            ),
        )
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        posten = {p.belegnummer: p for p in lade_posten(s)}
    assert posten["RE-2026-0042"].skonto_betrag is None
    assert posten["RE-2026-0043"].skonto_prozent == Decimal("2")  # Kontakt-Skonto


def test_land_des_kreditors_aus_der_ust_idnr(umgebung):
    """B06/Beobachtung: kein „DE“ mehr für jeden Kreditor aus einem PDF; ein Kontakt,
    dessen „DE“ nur die Vorgabe war, bekommt das Land aus dem Beleg."""
    make_session, _ = umgebung
    with make_session() as s:
        speichere_kontakt(s, Kontakt(name="Galerie Athen", kreditor_konto="70005"))
        speichere_beleg(
            s,
            eingangsrechnung(
                lieferant_name="Rahmen Wien GmbH",
                lieferant_ust_id="ATU12345678",
                iban="AT611904300234573201",
            ),
        )
        speichere_beleg(
            s,
            eingangsrechnung(
                datei_hash="b" * 64,
                belegnummer="GA-1",
                lieferant_name="Galerie Athen",
                lieferant_ust_id="EL123456789",
                iban=None,
            ),
        )
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        laender = {k.name: k.land for k in lade_kontakte(s)}
    assert laender == {"Rahmen Wien GmbH": "AT", "Galerie Athen": "GR"}


def test_13b_nachtraeglich_auf_belegbuchung_setzen(umgebung):
    """Steuer B4: Eine Belegbuchung ohne Schlüssel (0 %, Steuerfall unklar) nimmt
    `--steuer 94` an — die Steuer steht nie auf dem Beleg (§ 14a Abs. 5 UStG)."""
    from accounti.pruefung.storno import StornoError, korrigiere

    make_session, _ = umgebung
    beleg = eingangsrechnung(
        netto=Decimal("500.00"), steuer=Decimal("0.00"), brutto=Decimal("500.00")
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Netto 0 %",
            netto=Decimal("500.00"),
            steuersatz=Decimal("0"),
            steuer_betrag=Decimal("0.00"),
        )
    ]
    mit_satz = eingangsrechnung(datei_hash="b" * 64, belegnummer="RE-2026-0043")
    with make_session() as s:
        speichere_beleg(s, beleg)
        speichere_beleg(s, mit_satz)
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        ohne = next(b for b in lade_buchungen(s) if b.beleg_id == beleg.id)
        assert ohne.steuer_schluessel is None
        k = korrigiere(
            s, str(ohne.id), "4900", "70000", steuer=94, grund="Reverse Charge"
        )
        assert (k.neu.betrag_netto, k.neu.steuer_betrag) == (
            Decimal("500.00"),
            Decimal("95.00"),
        )
        sieben = next(
            b
            for b in lade_buchungen(s)
            if b.beleg_id == mit_satz.id and b.steuer_schluessel == 9
        )
        with pytest.raises(StornoError, match="hat einen Beleg"):
            korrigiere(s, str(sieben.id), "4900", "70000", steuer=8, grund="x")
