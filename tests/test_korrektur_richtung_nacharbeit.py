"""Richtung und Steuer einer Belegbuchung — Nacharbeit nach Runde 8 (Gesamttest 10b-1,
Folgepaket F: g8w G8R-1 bis G8R-4).

G8R-1: Ein Erlöskonto machte einen Beleg ohne eindeutige Belegart (Quittung,
Marktplatzabrechnung als ``SONSTIGES``, unbekannt) zum Ausgangsbeleg, egal auf welcher
Seite es stand. Eine fälschlich als Erlös im Soll gebuchte Ausgabe („8400 an 1000,
Schlüssel 3“ statt „4530 an 1000, Schlüssel 9“) ließ sich nicht mehr auf Aufwand mit
Vorsteuer berichtigen (§ 14c-Sperre), und das Storno warnte vor geschuldeter
Umsatzsteuer. Ein Erlös zählt jetzt nur auf der Seite einer Rechnung (Erlös im Haben,
Erlösschmälerung im Soll; ein negativer Beleg spiegelt).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from accounti.db.repository import lade_buchungen
from accounti.models import Belegart, Belegrichtung, BuchungStatus
from accounti.pruefung import storno as st
from accounti.pruefung.storno import StornoError, korrigiere, steuer_optionen
from accounti.steuer.kennziffern import Kontenplan, kennziffern_der_buchung
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    make_session_fixture,
)

D = Decimal
G, P = BuchungStatus.GEPRUEFT, BuchungStatus.ZUR_PRUEFUNG
TAG = date(2026, 10, 1)
ART = {
    "AR": (Belegart.AUSGANGSRECHNUNG, Belegrichtung.AUSGANG),
    "ER": (Belegart.EINGANGSRECHNUNG, Belegrichtung.EINGANG),
    "Q": (Belegart.QUITTUNG, Belegrichtung.EINGANG),
    "S": (Belegart.SONSTIGES, Belegrichtung.EINGANG),
    "U": (Belegart.UNBEKANNT, Belegrichtung.EINGANG),
}


def _beleg(  # noqa: ANN202
    art: str,
    netto: str = "500.00",
    steuer: str = "95.00",
    positionen: list[tuple[str, str, str | None, str | None]] | None = None,
):
    belegart, richtung = ART[art]
    return beleg(
        belegart=belegart,
        richtung=richtung,
        nummer=f"B-{uuid4().hex[:6]}",
        tag=TAG,
        netto=netto,
        steuer=steuer,
        brutto=str(D(netto) + D(steuer)),
        lieferant="Partner GmbH",
        positionen=positionen or [("Leistung", netto, "19", steuer)],
    )


def _buchung(bel, soll, haben, schluessel=None, steuer=None, netto="500.00", status=G):  # noqa: ANN001, ANN202
    return buchung(
        status=status,
        soll=soll,
        haben=haben,
        netto=netto,
        steuer=steuer,
        schluessel=schluessel,
        tag=TAG,
        beleg_id=bel.id,
    )


def _korrigiere(make_session, buchung_id, soll, haben, **optionen):  # noqa: ANN001, ANN003, ANN202
    optionen.setdefault("grund", "Test")
    with make_session() as s:
        k = korrigiere(s, str(buchung_id), soll, haben, von="erika", **optionen)
        s.commit()
    return k


def _storniere(make_session, buchung_id, **optionen) -> list[str]:  # noqa: ANN001, ANN003
    with make_session() as s:
        k = st.storniere(s, str(buchung_id), grund="doppelt", von="erika", **optionen)
        s.commit()
    return k.warnungen


def _kennziffern(make_session) -> dict[int, Decimal]:  # noqa: ANN001
    with make_session() as s:
        plan = st.kontenplan(s, None, None)
        alle = lade_buchungen(s)
        summe: dict[int, Decimal] = {}
        for b in alle:
            eigene = [x for x in alle if x.beleg_id == b.beleg_id]
            for kz, v in kennziffern_der_buchung(b, plan, eigene).items():
                summe[kz] = summe.get(kz, D(0)) + v
    return {k: v for k, v in summe.items() if v}


def _wirksam(make_session, beleg_id) -> list[Any]:  # noqa: ANN001
    with make_session() as s:
        return [
            b
            for b in lade_buchungen(s)
            if b.beleg_id == beleg_id
            and b.storno_von is None
            and b.storniert_durch is None
        ]


# --- G8R-1: Erlös im Soll auf Quittung/SONSTIGES ------------------------------------

AUSGABEN_ALS_ERLOES = [
    # Tankquittung auf 8400 statt 4530 (bar bzw. über die Bank)
    ("T1a_quittung_bar", "Q", ("8400", "1000"), ("4530", "1000"), G),
    ("T1b_quittung_bar", "Q", ("8400", "1000"), ("4530", "1000"), P),
    ("T1c_quittung_bank", "Q", ("8400", "1200"), ("4530", "1200"), P),
    # Marktplatzgebühr als „Erstattung“ (Geldtransit 1360, Verrechnungskonto 1361)
    ("T1d_markt_1360", "S", ("8400", "1360"), ("4970", "1360"), P),
    ("t1d_amazon_1361", "S", ("8400", "1361"), ("4970", "1361"), P),
    ("t1d_amazon_1361", "S", ("8400", "1361"), ("4970", "1361"), G),
]


@pytest.mark.parametrize(
    ("art", "vorher", "nachher", "status"),
    [f[1:] for f in AUSGABEN_ALS_ERLOES],
    ids=[f"{f[0]}_{f[4].value}" for f in AUSGABEN_ALS_ERLOES],
)
def test_ausgabe_als_erloes_im_soll_wird_aufwand_mit_vorsteuer(
    make_session, art, vorher, nachher, status
):
    """G8R-1 (t1_quittung_erloes.py, t1d_amazon.py): Ein Erlöskonto im Soll eines
    positiven Belegs ist keine Rechnung des Unternehmers — Schlüssel 3 ist dort ein
    Fehlschlüssel, laut Beleg Schlüssel 9, ohne § 14c-Sperre (wie Runde 7)."""
    bel = _beleg(art)
    b = _buchung(bel, *vorher, 3, "95.00", status=status)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel, Kontenplan())
    assert optionen.laut_beleg == 9 and 9 in optionen.schluessel, optionen
    assert optionen.ohne_steuer and "Fehlschlüssel" in (optionen.hinweis or "")
    k = _korrigiere(make_session, b.id, *nachher, steuer=9, grund=None)
    assert k.neu is not None and k.neu.steuer_schluessel == 9
    assert _kennziffern(make_session) == {66: D("95.00")}


def test_storno_einer_ausgabe_als_erloes_im_soll_warnt_nicht(make_session):
    """G8R-1: Das Storno von „8400 an 1000, Schlüssel 3“ auf einer Quittung behauptet
    keine geschuldete Umsatzsteuer — die Quittung weist keine Steuer des Unternehmers
    aus; die Prüfregel ``beleg_ust_ohne_buchung`` meldet ebenso nichts."""
    bel = _beleg("Q")
    b = _buchung(bel, "8400", "1000", 3, "95.00")
    anlegen(make_session, bel, b)
    assert not [w for w in _storniere(make_session, b.id) if "§ 14c" in w]


@pytest.mark.parametrize(
    ("art", "konten"),
    [("Q", ("1000", "8400")), ("S", ("1590", "8400")), ("S", ("8700", "1590"))],
    ids=["Q2_erloes_im_haben", "S3_erloes_im_haben", "X2_erloesschmaelerung_im_soll"],
)
def test_erloes_auf_der_rechnungsseite_bleibt_ausgewiesen(make_session, art, konten):
    """R7-3 bleibt: Ein Erlös im Haben bzw. eine Erlösschmälerung im Soll (die eigene
    Minderung des Unternehmers) weist Umsatzsteuer aus — nur Schlüssel 3, kein „ohne
    Steuer“, § 14c."""
    bel = _beleg(art)
    b = _buchung(bel, *konten, 3, "95.00", status=P)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel, Kontenplan())
    assert optionen.schluessel == (3,) and not optionen.ohne_steuer, optionen
    assert "§ 14c" in (optionen.hinweis or "")
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, b.id, *konten, ohne_steuer=True, grund="kein USt")
    assert "§ 14c" in fehler.value.meldung


def test_erloes_im_soll_eines_negativen_belegs_ist_ausgewiesen(make_session):
    """Gespiegelt: Auf einem negativen Beleg (Rückgabe auf dem eigenen Kassenbon) steht
    der Erlös im Soll auf der Seite der Gutschrift — die Umsatzsteuer bleibt
    ausgewiesen (§ 14c), „ohne Steuer“ gesperrt."""
    bel = _beleg("Q", netto="-500.00", steuer="-95.00")
    b = _buchung(bel, "8400", "1000", 3, "95.00", status=P)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel, Kontenplan())
    assert optionen.schluessel == (3,) and not optionen.ohne_steuer, optionen
    with pytest.raises(StornoError):
        _korrigiere(make_session, b.id, "8400", "1000", ohne_steuer=True, grund="x")
    assert _wirksam(make_session, bel.id)[0].steuer_schluessel == 3
