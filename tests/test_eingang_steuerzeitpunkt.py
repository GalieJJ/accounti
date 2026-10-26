"""Eingangsrechnung nach § 13b und ig. Erwerb: Buchungstag = Entstehung der Steuer
(Nachprüfung Merge N-4).

Die Steuer, die der Leistungsempfänger schuldet, entsteht

* bei einer sonstigen Leistung eines im übrigen Gemeinschaftsgebiet ansässigen
  Unternehmers (§ 13b Abs. 1 UStG) mit Ablauf des Voranmeldungszeitraums der Leistung,
* in den Fällen des § 13b Abs. 2 UStG (Werklieferungen und sonstige Leistungen anderer
  ausländischer Unternehmer, Bauleistungen, Gebäudereinigung …) mit Ausstellung der
  Rechnung, spätestens mit Ablauf des Folgemonats der Leistung,
* beim ig. Erwerb mit Ausstellung der Rechnung, spätestens mit Ablauf des Folgemonats
  des Erwerbs (§ 13 Abs. 1 Nr. 6 UStG);

die Vorsteuer im selben Zeitraum (§ 15 Abs. 1 S. 1 Nr. 3, 4 UStG). Vorher buchte
accounti alles zum Rechnungsdatum.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    lade_kontakte,
    lade_posten,
    setze_status,
    speichere_beleg,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Beleg,
    Belegart,
    Belegposition,
    BelegStatus,
    BuchungStatus,
)
from accounti.opos.verbuchung import verbuche_belege
from accounti.pruefung.perioden import schliesse
from accounti.steuer.kennziffern import Kontenplan, ermittle
from accounti.steuer.zeitraum import Zeitraum

D = Decimal
WIEN = {
    "lieferant_name": "Consult Wien GmbH",
    "lieferant_ust_id": "ATU12345678",
    "iban": "AT611904300234573201",
}
HUBER = {
    "lieferant_name": "Bau Huber GmbH",
    "lieferant_ust_id": "DE123456789",
    "iban": "DE89370400440532013000",
}
PARIS = {
    "lieferant_name": "Fournisseur SARL",
    "lieferant_ust_id": "FR12345678901",
    "iban": "FR7630006000011234567890189",
}


@pytest.fixture
def make_session():
    engine, fabrik = session_factory("sqlite:///:memory:")
    init_db(engine)
    yield fabrik
    engine.dispose()


def _beleg(positionen=(("Beratung", "1000.00", "0", "0.00"),), kennzeichen="AE", **kw):
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
        eingegangen_am=datetime(2026, 3, 6, 9, 0),
        **{**WIEN, **kw},
    )
    b.positionen = [
        Belegposition(
            beleg_id=b.id,
            bezeichnung=text,
            netto=D(netto),
            steuersatz=D(satz),
            steuer_betrag=D(steuer),
        )
        for text, netto, satz, steuer in positionen
    ]
    netto = sum((p.netto for p in b.positionen), D("0"))
    steuer = sum((p.steuer_betrag or D("0") for p in b.positionen), D("0"))
    return b.model_copy(
        update={
            "netto": netto,
            "steuer": steuer,
            "brutto": netto + steuer,
            "steuerkennzeichen": kennzeichen,
        }
    )


def _verbuche(make_session, beleg, sperren=()):
    with make_session() as s:
        speichere_beleg(s, beleg)
        for monat in sperren:
            schliesse(s, monat, "erika", trotzdem=True)
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, Buchhaltung(), gewinnermittlung="bilanz")
        s.commit()
    assert lauf.fehler == []
    (v,) = lauf.verbucht
    return v


def _va(make_session, zeitraum):
    with make_session() as s:
        for b in lade_buchungen(s):
            setze_status(s, str(b.id), BuchungStatus.GEPRUEFT)
        s.commit()
        e = ermittle(
            lade_buchungen(s),
            Zeitraum.lies(zeitraum),
            Kontenplan(),
            lade_kontakte(s),
            {p.beleg_id: p.kontakt_id for p in lade_posten(s)},
        )
    return {kz: str(b) for kz, b in e.voranmeldung.werte.items()}


def _tage(v):
    return sorted((b.datum, b.steuer_schluessel) for b in v.buchungen)


def test_13b_abs_1_zum_leistungsmonat(make_session):
    """AT-Berater, Leistung am 20.02., Rechnung vom 05.03.: Kz 46/47/67 gehören in
    02/2026 (§ 13b Abs. 1 UStG), vorher standen sie in 03/2026."""
    v = _verbuche(make_session, _beleg(leistungsdatum=date(2026, 2, 20)))
    assert _tage(v) == [(date(2026, 2, 20), 94)]
    assert v.posten.belegdatum == date(2026, 3, 5)  # Fälligkeit, Skonto: Belegdatum
    (h,) = [h for h in v.hinweise if "§ 13b Abs. 1" in h]
    assert "20.02.2026" in h and "Voranmeldungszeitraums der Leistung" in h, h
    assert _va(make_session, "2026-02") == {46: "1000.00", 47: "190.00", 67: "190.00"}
    assert _va(make_session, "2026-03") == {}


def test_13b_abs_2_mit_der_rechnung_im_folgemonat(make_session):
    """Bauleistung eines inländischen Unternehmers (§ 13b Abs. 2 Nr. 4), Leistung im
    Februar, Rechnung im März: die Steuer entsteht mit Ausstellung der Rechnung."""
    beleg = _beleg(leistungsdatum=date(2026, 2, 20), **HUBER)
    v = _verbuche(make_session, beleg)
    assert _tage(v) == [(date(2026, 3, 5), 94)]
    assert not any("§ 13b Abs. 2" in h for h in v.hinweise), v.hinweise
    assert _va(make_session, "2026-03") == {84: "1000.00", 85: "190.00", 67: "190.00"}


def test_13b_abs_2_spaetestens_mit_ablauf_des_folgemonats(make_session):
    """Leistung im Januar, Rechnung erst im März: Steuer mit Ablauf Februar."""
    beleg = _beleg(leistungsdatum=date(2026, 1, 10), **HUBER)
    v = _verbuche(make_session, beleg)
    assert _tage(v) == [(date(2026, 2, 28), 94)]
    (h,) = [h for h in v.hinweise if "§ 13b Abs. 2" in h]
    assert "28.02.2026" in h and "spätestens" in h, h
    assert _va(make_session, "2026-02") == {84: "1000.00", 85: "190.00", 67: "190.00"}


def test_ig_erwerb_spaetestens_mit_ablauf_des_folgemonats(make_session):
    """§ 13 Abs. 1 Nr. 6 UStG: Lieferung im Januar, Rechnung im März → Februar."""
    beleg = _beleg(
        (("Ware", "1000.00", "0", "0.00"),),
        kennzeichen="K",
        leistungsdatum=date(2026, 1, 10),
        **PARIS,
    )
    v = _verbuche(make_session, beleg)
    assert _tage(v) == [(date(2026, 2, 28), 19)]
    (h,) = [h for h in v.hinweise if "§ 13 Abs. 1 Nr. 6" in h]
    assert "28.02.2026" in h, h
    assert _va(make_session, "2026-02") == {89: "1000.00", 61: "190.00"}


def test_13b_abs_1_ohne_leistungsdatum_bleibt_beim_rechnungsdatum(make_session):
    v = _verbuche(make_session, _beleg())
    assert _tage(v) == [(date(2026, 3, 5), 94)]
    (h,) = [h for h in v.hinweise if "§ 13b Abs. 1" in h]
    assert "kein Leistungsdatum" in h and "umdatieren" in h, h


def test_13b_abs_1_leistungsmonat_festgeschrieben(make_session):
    """Ist der Leistungsmonat festgeschrieben, bleibt die Buchung beim Rechnungsdatum
    — zur Prüfung, der Hinweis nennt den Monat, dessen Voranmeldung zu berichtigen
    ist."""
    beleg = _beleg(leistungsdatum=date(2026, 2, 20))
    v = _verbuche(make_session, beleg, sperren=["2026-02"])
    assert _tage(v) == [(date(2026, 3, 5), 94)]
    assert {b.status for b in v.buchungen} == {BuchungStatus.ZUR_PRUEFUNG}
    (h,) = [h for h in v.hinweise if "festgeschrieben" in h]
    assert "02/2026" in h and "berichtigen" in h and "§ 13b Abs. 1" in h, h


def test_gemischte_rechnung_teilt_den_buchungstag(make_session):
    """§ 13b-Teil zum Ende des Folgemonats, Vorsteuer aus der Rechnung (19 %) zum
    Rechnungsdatum (§ 15 Abs. 1 S. 1 Nr. 1 UStG)."""
    beleg = _beleg(
        (("Montage", "600.00", "0", "0.00"), ("Material", "100.00", "19", "19.00")),
        leistungsdatum=date(2026, 1, 10),
        **HUBER,
    )
    v = _verbuche(make_session, beleg)
    assert _tage(v) == [(date(2026, 2, 28), 94), (date(2026, 3, 5), 9)]


def test_13b_gutschrift_bleibt_im_zeitraum_der_aenderung(make_session):
    """Eine Gutschrift mindert im Zeitraum der Änderung (§ 17 Abs. 1 S. 5, 8 UStG),
    nicht im Leistungsmonat."""
    beleg = _beleg(
        (("Gutschrift Beratung", "-200.00", "0", "0.00"),),
        leistungsdatum=date(2026, 2, 20),
    )
    v = _verbuche(make_session, beleg)
    assert _tage(v) == [(date(2026, 3, 5), 94)]
    assert not any("§ 13b Abs. 1" in h and "gebucht zum" in h for h in v.hinweise)


@pytest.mark.parametrize(
    ("fall", "eu", "leistung", "tag", "teil"),
    [
        # Vorausrechnung: die Steuer entsteht nicht vor der Leistung, bei Zahlung
        # vorher mit der Zahlung (§ 13b Abs. 4 S. 2) — beim Rechnungsdatum, Hinweis
        ("AE", True, date(2026, 4, 10), date(2026, 3, 5), "§ 13b Abs. 4 Satz 2"),
        ("AE", False, date(2026, 4, 10), date(2026, 3, 5), "§ 13b Abs. 4 Satz 2"),
        # gleicher Monat: Rechnungsdatum ohne Hinweis
        ("AE", True, date(2026, 3, 1), date(2026, 3, 5), None),
        # ig. Erwerb: Rechnung vor der Lieferung — mit Ausstellung der Rechnung
        ("K", True, date(2026, 4, 10), date(2026, 3, 5), None),
        # § 13b Abs. 2 Rechnung im Folgemonat: Rechnungsdatum ohne Hinweis
        ("AE", False, date(2026, 2, 27), date(2026, 3, 5), None),
    ],
)
def test_steuertag_empfaenger(fall, eu, leistung, tag, teil):
    from accounti.steuer.leistungszeitpunkt import steuertag_empfaenger

    ergebnis, hinweis = steuertag_empfaenger(date(2026, 3, 5), leistung, fall, eu)
    assert ergebnis == tag
    assert (hinweis is None) if teil is None else (teil in (hinweis or "")), hinweis
