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


# --- G8R-2: dieselben Konten in Auswahl, Korrektur, Storno und Prüfregel -------------


def test_pruefregel_kennt_die_elster_konten(make_session, tmp_path):
    """G8R-2 (t2b_regel.py): Mit ``elster.steuerrelevante_konten`` ['2700-2759',
    '8000-8959'] ist „1000 an 2700, Schlüssel 3“ auf einer Quittung ein Erlös — das
    Storno warnt nach § 14c, und ``accounti pruefen --regel beleg_ust_ohne_buchung``
    mit derselben Konfiguration meldet denselben Betrag (vorher: keine Befunde)."""
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.elster.konfiguration import ElsterEinstellungen
    from tests.pruefung_hilfe import db_url

    bereiche = ["2700-2759", "8000-8959"]
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "buchhaltung:\n  kontenrahmen: SKR03\n"
        f"elster:\n  steuerrelevante_konten: {bereiche}\n",
        encoding="utf-8",
    )
    bel = _beleg("Q")
    b = _buchung(bel, "1000", "2700", 3, "95.00")
    anlegen(make_session, bel, b)
    warnungen = _storniere(
        make_session, b.id, elster=ElsterEinstellungen(steuerrelevante_konten=bereiche)
    )
    assert any("95,00 € Umsatzsteuer" in w for w in warnungen), warnungen
    r = CliRunner().invoke(
        app,
        ["pruefen", "--db", db_url(tmp_path), "--config", str(konfig),
         "--regel", "beleg_ust_ohne_buchung"],
    )  # fmt: skip
    text = " ".join(r.output.split())
    assert "1 Befunde" in text and "│ 95,00 │" in text, text


# --- G8R-3: Nebenbuchung nur für Zahlung, Erstattung, Verrechnung --------------------

# Ausgangsrechnung 1000 €: 500 € zu 19 %, 500 € Auslage ohne Umsatzsteuer
ZWEI_TEILE = [("Ware", "500.00", "19", "95.00"), ("Auslage", "500.00", None, None)]


def _nebenbuchung(make_session, buchung_id) -> bool:  # noqa: ANN001
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen
    from accounti.konfiguration import Buchhaltung

    with make_session() as s:
        b = st._lade(s, str(buchung_id))
        plan = st.kontenplan(s, Buchhaltung(), None)
        kr = st.mit_eingerichteten_konten(lade_kontenrahmen(), s)
        return st.richtungsbezug(s, b, plan, kr, Buchhaltung()).nebenbuchung


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("rechnung", "teil", "ziel"),
    [
        # N1: zweiter Teil der Rechnung auf dem durchlaufenden Posten
        (("10001", "8400"), ("10001", "1590"), ("8736", "1590")),
        (("10001", "8400"), ("10001", "1590"), ("8200", "1590")),
        # N3: Barverkauf, zweiter Teil auf 1590
        (("1000", "8400"), ("1000", "1590"), ("8736", "1590")),
    ],
    ids=["N1_8736", "N1_8200", "N3_barverkauf"],
)
def test_rechnungsteil_auf_zwei_gegenkonten_ist_keine_nebenbuchung(
    make_session, status, rechnung, teil, ziel
):
    """G8R-3 (t3_neben.py N1, N3): Ein Teil der Rechnung bucht Debitor bzw. Kasse auf
    derselben Seite wie die Rechnungsbuchung — keine Zahlung. Aus ihm wird keine
    Erlösschmälerung mit Umsatzsteuer: Die Seite der Ausgangsrechnung gilt (wie
    Runde 7), Kz 81 bleibt."""
    bel = _beleg("AR", netto="1000.00", positionen=ZWEI_TEILE)
    r = _buchung(bel, *rechnung, 3, "95.00")
    z = _buchung(bel, *teil, status=status)
    anlegen(make_session, bel, r, z)
    assert not _nebenbuchung(make_session, z.id)
    optionen = {"steuer": 3} if ziel[0] == "8736" else {}
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, z.id, *ziel, **optionen)
    assert "die Ausgangsrechnung bucht ihr Erfolgskonto" in fehler.value.meldung
    assert _kennziffern(make_session).get(81) == D("500.00")


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize("ziel", [("10001", "8400"), ("1200", "8400")])
def test_auszahlung_einer_gutschrift_wird_kein_erloes(make_session, status, ziel):
    """G8R-3 (t3_neben.py N5): Die Auszahlung einer Gutschrift ist eine Nebenbuchung —
    aber eine Korrektur, die ihr ein Erlöskonto mit Steuer gibt, das kein
    Minderungskonto ist, misst weiter an der Gutschrift (Erlös im Soll)."""
    bel = _beleg(
        "AR", netto="-500.00", steuer="-95.00",
        positionen=[("Gutschrift", "-500.00", "19", "-95.00")],
    )  # fmt: skip
    r = _buchung(bel, "8400", "10001", 3, "95.00")
    z = _buchung(bel, "10001", "1200", netto="595.00", status=status)
    anlegen(make_session, bel, r, z)
    assert _nebenbuchung(make_session, z.id)
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, z.id, *ziel, steuer=3)
    assert "Gutschrift" in fehler.value.meldung
    assert _kennziffern(make_session) == {81: D("-500.00")}


def test_zahlung_zur_eingangsrechnung_wird_erhaltenes_skonto(make_session):
    """Gegenprobe (t3_neben.py N6, R7-2): „70001 an 1200 → 70001 an 3736, Schlüssel 9“
    bleibt erlaubt — eine Zahlung steht auf der Gegenseite der Rechnung."""
    bel = _beleg("ER")
    r = _buchung(bel, "4930", "70001", 9, "95.00")
    z = _buchung(bel, "70001", "1200", netto="595.00")
    anlegen(make_session, bel, r, z)
    assert _nebenbuchung(make_session, z.id)
    k = _korrigiere(make_session, z.id, "70001", "3736", steuer=9)
    assert k.neu is not None and k.neu.haben_konto == "3736"
