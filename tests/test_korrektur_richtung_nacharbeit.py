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


# --- G8R-4: Lücke eines Belegs, der nur über seinen Erlös Ausgang ist -----------------

MARKT = [
    ("Verkauf", "500.00", "19", "95.00"),
    ("Verkaufsgebühr", "100.00", "19", "19.00"),
]


def _luecken_der_regel(make_session) -> list[Any]:  # noqa: ANN001
    from accounti.konfiguration import Buchhaltung
    from accounti.pruefung.einstellungen import PruefEinstellungen
    from accounti.pruefung.regeln import Kontext, fuehre_regeln_aus

    with make_session() as s:
        k = Kontext(s, PruefEinstellungen(), Buchhaltung(), date(2026, 10, 20))
        return fuehre_regeln_aus(k, ["beleg_ust_ohne_buchung"]).befunde


@pytest.mark.parametrize(
    "gebuehr",
    [("9", "100.00", "19.00"), (None, "119.00", None)],
    ids=["gebuehr_mit_vorsteuer", "gebuehr_brutto"],
)
def test_luecke_zaehlt_keine_gebuehrenposition(make_session, gebuehr):
    """G8R-4 (t6_markt_luecke.py P1/P2): Marktplatzabrechnung (SONSTIGES) mit Verkauf
    und Verkaufsgebühr zu 19 % — nach dem Storno des Erlöses fehlen 95,00 € (die
    Umsatzsteuer des Verkaufs), nicht 114,00 €: Die Gebühr ist eine Eingangsleistung.
    Storno-Warnung und Prüfregel nennen denselben Betrag."""
    schluessel, netto, steuer = gebuehr
    bel = _beleg("S", netto="600.00", steuer="114.00", positionen=MARKT)
    erloes = _buchung(bel, "1200", "8400", 3, "95.00")
    gebuehr_b = _buchung(
        bel, "4970", "1200", int(schluessel) if schluessel else None, steuer, netto
    )
    anlegen(make_session, bel, erloes, gebuehr_b)
    (warnung,) = [w for w in _storniere(make_session, erloes.id) if "§ 14c" in w]
    assert "weist 95,00 € Umsatzsteuer" in warnung and "114,00" not in warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text


def test_korrigierter_erloes_mit_gebuehr_hat_keine_luecke(make_session):
    """G8R-4: Eine Korrektur (Storno und Neubuchung) des Erlöses lässt die Steuer
    gebucht — keine Lücke, auch nicht in Höhe der Gebühr (die Kette zählt einmal);
    erst das Storno der Neubuchung fehlt mit 95,00 €."""
    bel = _beleg("S", netto="600.00", steuer="114.00", positionen=MARKT)
    erloes = _buchung(bel, "1200", "8400", 3, "95.00")
    gebuehr_b = _buchung(bel, "4970", "1200", 9, "19.00", "100.00")
    anlegen(make_session, bel, erloes, gebuehr_b)
    k = _korrigiere(make_session, erloes.id, "1360", "8400")
    assert k.neu is not None and not [w for w in k.warnungen if "§ 14c" in w]
    assert _luecken_der_regel(make_session) == []
    (warnung,) = [w for w in _storniere(make_session, k.neu.id) if "§ 14c" in w]
    assert "weist 95,00 € Umsatzsteuer" in warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text


def test_ausgangsrechnung_zaehlt_weiter_alle_positionen(make_session):
    """Gegenprobe: Eine Ausgangsrechnung weist die Steuer aller ihrer Positionen aus
    (zwei Erlöspositionen, eine gebucht) — unverändert."""
    zwei = [("Ware", "500.00", "19", "95.00"), ("Fracht", "100.00", "19", "19.00")]
    bel = _beleg("AR", netto="600.00", steuer="114.00", positionen=zwei)
    b = _buchung(bel, "10001", "8400", 3, "95.00")
    anlegen(make_session, bel, b)
    (warnung,) = [w for w in _storniere(make_session, b.id) if "§ 14c" in w]
    assert "weist 114,00 € Umsatzsteuer" in warnung


# --- F Runde 2 (gf-richtung GF-1): Erlös in der ganzen Korrekturkette ----------------


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(("art", "geld"), [("Q", "1000"), ("S", "1200")])
@pytest.mark.parametrize("minderung", ["8700", "8736"])
def test_erloesschmaelerung_im_haben_bleibt_ausgewiesen(
    make_session, status, art, geld, minderung
):
    """GF-1a (gf1_erloes_umweg.py A/A2/A9, v1_gf1.py A): „1000 an 8400, Schlüssel 3“
    auf Quittung bzw. SONSTIGES → „1000 an 8700 --steuer 3“ ließ die Umsatzsteuer als
    „Fehlschlüssel“ erscheinen, „ohne Steuer“ mit Grund ging (Kz 81 500 → leer). Eine
    Erlösschmälerung im Haben eines positiven Belegs bucht Kz 81 positiv wie ein Erlös
    — maßgeblich ist die Kennziffer: § 14c, nur Schlüssel 3, wie d36ac77 (R7-3)."""
    bel = _beleg(art)
    b = _buchung(bel, geld, "8400", 3, "95.00", status=status)
    anlegen(make_session, bel, b)
    _korrigiere(make_session, b.id, geld, minderung, steuer=3, grund=None)
    (akt,) = _wirksam(make_session, bel.id)
    assert (akt.haben_konto, akt.steuer_schluessel) == (minderung, 3)
    optionen = steuer_optionen(akt, bel, Kontenplan())
    assert optionen.schluessel == (3,) and not optionen.ohne_steuer, optionen
    hinweis = optionen.hinweis or ""
    assert "§ 14c Abs. 1" in hinweis and "Fehlschlüssel" not in hinweis, hinweis
    with pytest.raises(StornoError):
        _korrigiere(make_session, akt.id, geld, minderung, steuer=9)
    with pytest.raises(StornoError) as fehler:
        _korrigiere(
            make_session, akt.id, geld, minderung, ohne_steuer=True, grund="kein USt"
        )
    assert "§ 14c" in fehler.value.meldung, fehler.value.meldung
    assert _kennziffern(make_session) == {81: D("500.00")}


@pytest.mark.parametrize(("art", "geld"), [("Q", "1000"), ("S", "1200")])
@pytest.mark.parametrize("ziel", ["2700", "8736"])
def test_storno_nach_kontowechsel_meldet_die_luecke(make_session, art, geld, ziel):
    """GF-1b (gf1_erloes_umweg.py B/C, v1_gf1.py B/C): Freigegeben „1000 an 8400,
    Schlüssel 3“ → „1000 an 2700 --steuer 3“ (bzw. 8736), dann Storno: Die ersetzte
    Original-Erlösbuchung zählte für die Obergrenze der Lücke nicht mehr — keine
    Warnung, kein Befund, obwohl die 95 € in der Voranmeldung fehlen. Die Obergrenze
    ist jetzt die höchste Erlös-Umsatzsteuer je Satz über die ganze Korrekturkette."""
    bel = _beleg(art)
    b = _buchung(bel, geld, "8400", 3, "95.00")
    anlegen(make_session, bel, b)
    k = _korrigiere(make_session, b.id, geld, ziel, steuer=3, grund=None)
    assert k.neu is not None
    (warnung,) = [w for w in _storniere(make_session, k.neu.id) if "§ 14c" in w]
    assert "weist 95,00 € Umsatzsteuer" in warnung, warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text
    assert _kennziffern(make_session) == {}


@pytest.mark.parametrize(("art", "geld"), [("Q", "1000"), ("S", "1200")])
def test_ohne_steuer_nach_kontowechsel_meldet_die_luecke(make_session, art, geld):
    """GF-1b (Grenze 5 aus F, gf1_erloes_umweg.py B2): „→ 2700 --steuer 3“, dann
    „--ohne-steuer --grund“ — die Prüfregel meldet die fehlenden 95 € wie d36ac77."""
    bel = _beleg(art)
    b = _buchung(bel, geld, "8400", 3, "95.00")
    anlegen(make_session, bel, b)
    k = _korrigiere(make_session, b.id, geld, "2700", steuer=3, grund=None)
    assert k.neu is not None
    _korrigiere(make_session, k.neu.id, geld, "2700", ohne_steuer=True, grund="kein")
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text


def test_obergrenze_zaehlt_jede_korrekturkette_einmal(make_session):
    """Zwei Verkäufe zu 19 % auf einem Marktplatzbeleg (SONSTIGES), je eine
    Erlösbuchung: Der erste wird über eine Neubuchung auf 2700 umgebucht, der zweite
    storniert — es fehlen 95 € (die Obergrenze summiert die Ketten: 95 + 95), und
    eine zweimal korrigierte Kette zählt nur einmal (keine Lücke über 190 €)."""
    zwei = [
        ("Verkauf A", "500.00", "19", "95.00"),
        ("Verkauf B", "500.00", "19", "95.00"),
    ]
    bel = _beleg("S", netto="1000.00", steuer="190.00", positionen=zwei)
    a = _buchung(bel, "1200", "8400", 3, "95.00")
    b = _buchung(bel, "1200", "8400", 3, "95.00")
    anlegen(make_session, bel, a, b)
    k1 = _korrigiere(make_session, a.id, "1360", "8400")
    assert k1.neu is not None
    k2 = _korrigiere(make_session, k1.neu.id, "1360", "2700", steuer=3, grund=None)
    assert k2.neu is not None
    assert _luecken_der_regel(make_session) == []
    (warnung,) = [w for w in _storniere(make_session, b.id) if "§ 14c" in w]
    assert "weist 190,00 € Umsatzsteuer" in warnung and "nur 95,00 €" in warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text


# --- F Runde 2 (gf-richtung GF-2): Zahlung über das Gegenkonto der Rechnung ----------


def _nebenbuchung_in(make_session, buchung_id, rahmen: str) -> bool:  # noqa: ANN001
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen
    from accounti.konfiguration import Buchhaltung

    bh = Buchhaltung(
        kontenrahmen=rahmen, bank_konto="1800" if rahmen == "SKR04" else "1200"
    )
    with make_session() as s:
        b = st._lade(s, str(buchung_id))
        plan = st.kontenplan(s, bh, None)
        kr = st.mit_eingerichteten_konten(lade_kontenrahmen(rahmen), s)
        return st.richtungsbezug(s, b, plan, kr, bh).nebenbuchung


SKONTO_UEBER_VERRECHNUNG = [
    # Z1: Ausgangsrechnung über den durchlaufenden Posten, Zahlung „1200 an 1590“
    (
        "Z1_ar_1590",
        "SKR03",
        "AR",
        ("1590", "8400", 3),
        ("1200", "1590"),
        ("8736", "1590"),
    ),
    # Z3: Eingangsrechnung über 1590, Zahlung „1590 an 1200“ → erhaltenes Skonto
    (
        "Z3_er_1590",
        "SKR03",
        "ER",
        ("4930", "1590", 9),
        ("1590", "1200"),
        ("1590", "3736"),
    ),
    (
        "Z1_ar_1370",
        "SKR04",
        "AR",
        ("1370", "4400", 3),
        ("1800", "1370"),
        ("4736", "1370"),
    ),
    (
        "Z3_er_1370",
        "SKR04",
        "ER",
        ("6815", "1370", 9),
        ("1370", "1800"),
        ("1370", "5736"),
    ),
]


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("rahmen", "art", "rechnung", "zahlung", "ziel"),
    [f[1:] for f in SKONTO_UEBER_VERRECHNUNG],
    ids=[f[0] for f in SKONTO_UEBER_VERRECHNUNG],
)
def test_skonto_zur_zahlung_ueber_das_gegenkonto_der_rechnung(
    make_session, status, rahmen, art, rechnung, zahlung, ziel
):
    """GF-2 (gf2_neben.py Z1, Z3; aus F c72072c): Steht die Rechnung auf einem
    Verrechnungskonto (1590 bzw. SKR04 1370) statt auf einem Personenkonto, ist die
    Zahlung „1200 an 1590“ dieses Gegenkonto auf der Gegenseite — eine Nebenbuchung,
    ihr Skonto („8736 an 1590, Schlüssel 3“ bzw. „1590 an 3736, Schlüssel 9“) geht
    wieder wie d36ac77 (G8R-3 sperrte es)."""
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen
    from accounti.konfiguration import Buchhaltung

    soll, haben, schluessel = rechnung
    bel = _beleg(art)
    r = _buchung(bel, soll, haben, schluessel, "95.00")
    z = _buchung(bel, *zahlung, netto="595.00", status=status)
    anlegen(make_session, bel, r, z)
    assert _nebenbuchung_in(make_session, z.id, rahmen)
    umgebung: dict[str, Any] = {}
    if rahmen == "SKR04":
        umgebung = {
            "buchhaltung": Buchhaltung(kontenrahmen="SKR04", bank_konto="1800"),
            "kontenrahmen": lade_kontenrahmen("SKR04"),
        }
    _korrigiere(make_session, z.id, *ziel, steuer=schluessel, **umgebung)
    (neu,) = [x for x in _wirksam(make_session, bel.id) if x.id != r.id]
    assert (neu.soll_konto, neu.haben_konto, neu.steuer_schluessel) == (
        *ziel,
        schluessel,
    )


# --- F Runde 3 (gf2-richtung GF2-1, GF2-2): Obergrenze ohne Erlösschmälerungen -------


def _rest_von_b2(make_session, beleg_id, b1_id) -> Any:  # noqa: ANN001
    (rest,) = [x for x in _wirksam(make_session, beleg_id) if x.id != b1_id]
    return rest


def _warnung_14c(warnungen: list[str]) -> str:
    (warnung,) = [w for w in warnungen if "§ 14c" in w]
    return warnung


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(("art", "geld"), [("Q", "1000"), ("S", "1200")])
@pytest.mark.parametrize("weg", ["storno", "2700_ohne"])
def test_berichtigte_erloesschmaelerung_senkt_die_obergrenze_nicht(
    make_session, status, art, geld, weg
):
    """GF2-1 (n1_negkette.py, w1_negkette.py K1): Neben dem Erlös B1 „1000 an 8400,
    Schlüssel 3“ (Quittung bzw. SONSTIGES 500/95) steht eine irrig als
    Erlösschmälerung gebuchte Ausgabe B2 „8700 an 1000, Schlüssel 3“. B2 wird über
    „8400 an 1000 --steuer 3“ zu „4530 an 1000 --steuer 9“ berichtigt (G8R-1), danach
    B1 storniert (bzw. „→ 2700 --steuer 3“ und „ohne Steuer“). Die Kette von B2 zählte
    in der Obergrenze mit ihrem höchsten Stand −95 und hob den Erlös auf: keine
    Warnung, kein Befund, die 95 € fehlten still. Je Kette zählt nur ihr höchster
    positiver Stand — wie ohne B2 (K0)."""
    bel = _beleg(art)
    b1 = _buchung(bel, geld, "8400", 3, "95.00")
    b2 = _buchung(bel, "8700", geld, 3, "95.00", status=status)
    anlegen(make_session, bel, b1, b2)
    _korrigiere(make_session, b2.id, "8400", geld, steuer=3, grund=None)
    zwischen = _rest_von_b2(make_session, bel.id, b1.id)
    _korrigiere(make_session, zwischen.id, "4530", geld, steuer=9, grund=None)
    rest = _rest_von_b2(make_session, bel.id, b1.id)
    assert (rest.soll_konto, rest.steuer_schluessel) == ("4530", 9)
    assert _luecken_der_regel(make_session) == []
    if weg == "storno":
        warnung = _warnung_14c(_storniere(make_session, b1.id))
        assert "weist 95,00 € Umsatzsteuer" in warnung, warnung
    else:
        k = _korrigiere(make_session, b1.id, geld, "2700", steuer=3, grund=None)
        assert k.neu is not None
        _korrigiere(
            make_session, k.neu.id, geld, "2700", ohne_steuer=True, grund="kein USt"
        )
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text
    assert _kennziffern(make_session) == {66: D("95.00")}


@pytest.mark.parametrize(("art", "geld"), [("Q", "1000"), ("S", "1200")])
@pytest.mark.parametrize(
    "fall",
    [
        "K2_erst_minderung",
        "K2r_erst_erloes",
        "K2t_teilminderung",
        "K3_minderung_bleibt",
    ],
)
def test_stornierte_erloesschmaelerung_senkt_die_obergrenze_nicht(
    make_session, art, geld, fall
):
    """GF2-2 (n1_negkette.py K2/K3, w1_k2_cli.py K2/K2r/K2t): B1 „1000 an 8400,
    Schlüssel 3“ und B2 „8700 an 1000, Schlüssel 3“ (95 € bzw. Teilminderung 100/19),
    beide freigegeben; B2 wird storniert (der Weg aus dem Plan), dann B1 — oder
    umgekehrt, oder B2 bleibt. Die stornierte bzw. wirksame Minderung zählte in der
    Obergrenze mit −95 (−19) und hob den Erlös auf: keine Warnung, kein Befund (bzw.
    76 statt 95 €). Wie d36ac77 fehlen 95 €: Eine Minderung mindert die ausgewiesene
    Steuer nicht, sie mindert nach § 17 UStG."""
    bel = _beleg(art)
    b1 = _buchung(bel, geld, "8400", 3, "95.00")
    if fall.startswith("K2t"):
        b2 = _buchung(bel, "8700", geld, 3, "19.00", netto="100.00")
    else:
        b2 = _buchung(bel, "8700", geld, 3, "95.00")
    anlegen(make_session, bel, b1, b2)
    if fall.startswith("K2r"):
        warnung = _warnung_14c(_storniere(make_session, b1.id))
        assert "weist 95,00 € Umsatzsteuer" in warnung, warnung
        warnung = _warnung_14c(_storniere(make_session, b2.id))
        assert "weist 95,00 € Umsatzsteuer" in warnung, warnung
    elif fall.startswith("K3"):
        warnung = _warnung_14c(_storniere(make_session, b1.id))
        assert "weist 95,00 € Umsatzsteuer" in warnung, warnung
        assert _kennziffern(make_session) == {81: D("-500.00")}
    else:
        assert not [w for w in _storniere(make_session, b2.id) if "§ 14c" in w]
        warnung = _warnung_14c(_storniere(make_session, b1.id))
        assert "weist 95,00 € Umsatzsteuer" in warnung, warnung
        assert "76,00" not in warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text


@pytest.mark.parametrize("weg", ["M2_storno", "V1_berichtigt"])
def test_minderung_auf_dem_marktplatzbeleg_senkt_die_obergrenze_nicht(
    make_session, weg
):
    """GF2-1/GF2-2 im Marktplatzfall (w2_markt_cli.py M2, n2_varianten.py V1):
    SONSTIGES mit Verkauf 500/95 und Verkaufsgebühr 100/19; die Gebühr irrig als
    „8700 an 1361, Schlüssel 3“ gebucht, dann storniert bzw. über 8400 zu „4930 an
    1361 --steuer 9“ berichtigt. Das Storno des Verkaufs meldete 76 statt 95 €."""
    bel = _beleg("S", netto="600.00", steuer="114.00", positionen=MARKT)
    b1 = _buchung(bel, "1361", "8400", 3, "95.00")
    b2 = _buchung(bel, "8700", "1361", 3, "19.00", netto="100.00")
    anlegen(make_session, bel, b1, b2)
    if weg.startswith("M2"):
        assert not [w for w in _storniere(make_session, b2.id) if "§ 14c" in w]
    else:
        _korrigiere(make_session, b2.id, "8400", "1361", steuer=3, grund=None)
        zwischen = _rest_von_b2(make_session, bel.id, b1.id)
        _korrigiere(make_session, zwischen.id, "4930", "1361", steuer=9, grund=None)
    warnung = _warnung_14c(_storniere(make_session, b1.id))
    assert "weist 95,00 € Umsatzsteuer" in warnung and "76,00" not in warnung, warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("95.00"), befund.text


RUECKSENDUNG = [
    ("Verkauf", "500.00", "19", "95.00"),
    ("Rücksendung", "-100.00", "19", "-19.00"),
]


@pytest.mark.parametrize("zuerst", ["ruecksendung", "verkauf"])
def test_ruecksendung_des_belegs_mindert_die_obergrenze_schon(make_session, zuerst):
    """Gegenprobe zu GF2-1/GF2-2: Weist der Marktplatzbeleg die Minderung selbst aus
    (Position Rücksendung −100/−19), mindert sie schon die ausgewiesene Steuer
    (``_ausgewiesen``: 76 €). Ihre Buchung „8700 an 1361, Schlüssel 3“ storniert —
    keine Lücke (95 € gebucht); beide storniert — es fehlen die 76 € des Belegs, nicht
    mehr."""
    bel = _beleg("S", netto="400.00", steuer="76.00", positionen=RUECKSENDUNG)
    b1 = _buchung(bel, "1361", "8400", 3, "95.00")
    b2 = _buchung(bel, "8700", "1361", 3, "19.00", netto="100.00")
    anlegen(make_session, bel, b1, b2)
    assert _luecken_der_regel(make_session) == []
    if zuerst == "ruecksendung":
        assert not [w for w in _storniere(make_session, b2.id) if "§ 14c" in w]
        assert _luecken_der_regel(make_session) == []
        warnung = _warnung_14c(_storniere(make_session, b1.id))
    else:
        warnung = _warnung_14c(_storniere(make_session, b1.id))
        assert "weist 76,00 € Umsatzsteuer" in warnung, warnung
        warnung = _warnung_14c(_storniere(make_session, b2.id))
    assert "weist 76,00 € Umsatzsteuer" in warnung, warnung
    (befund,) = _luecken_der_regel(make_session)
    assert befund.betrag == D("76.00"), befund.text


def test_storno_einer_minderung_auf_negativem_beleg_fehlt_nie(make_session):
    """Gegenprobe: Ein negativer Beleg (Rückgabe auf dem eigenen Kassenbon −500/−95)
    mit „8700 an 1000, Schlüssel 3“ — sein Storno erhöht die Steuer, es fehlt nichts
    (keine Warnung, kein Befund), auch nicht mit der neuen Untergrenze 0."""
    bel = _beleg("Q", netto="-500.00", steuer="-95.00")
    b = _buchung(bel, "8700", "1000", 3, "95.00")
    anlegen(make_session, bel, b)
    assert not [w for w in _storniere(make_session, b.id) if "§ 14c" in w]
    assert _luecken_der_regel(make_session) == []


@pytest.mark.parametrize("fall", ["K1_Q", "K1_S", "M2"])
def test_obergrenze_ohne_minderung_ueber_die_cli(
    make_session, tmp_path, monkeypatch, fall
):
    """GF2-1/GF2-2 über die echte CLI (n3_cli_kette.py, w2_markt_cli.py):
    ``accounti korrigiere`` (B2 → 8400 → 4530 Schlüssel 9) bzw. ``buchung storniere``
    der Gebühr, dann ``buchung storniere`` des Erlöses — die Ausgabe warnt mit 95,00 €,
    ``accounti pruefen --regel beleg_ust_ohne_buchung`` meldet 95,00 €."""
    from typer.testing import CliRunner

    from accounti.cli import app
    from tests.pruefung_hilfe import db_url, kurz

    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    url = db_url(tmp_path)
    runner = CliRunner()

    def cli(*argumente: str) -> str:
        r = runner.invoke(app, [*argumente, "--db", url], env={"COLUMNS": "250"})
        assert r.exit_code == 0, r.output
        return " ".join(r.output.split())

    if fall == "M2":
        bel = _beleg("S", netto="600.00", steuer="114.00", positionen=MARKT)
        geld = "1361"
        b1 = _buchung(bel, geld, "8400", 3, "95.00")
        b2 = _buchung(bel, "8700", geld, 3, "19.00", netto="100.00")
    else:
        bel = _beleg(fall[-1])
        geld = {"Q": "1000", "S": "1200"}[fall[-1]]
        b1 = _buchung(bel, geld, "8400", 3, "95.00")
        b2 = _buchung(bel, "8700", geld, 3, "95.00")
    anlegen(make_session, bel, b1, b2)
    if fall == "M2":
        text = cli("buchung", "storniere", kurz(b2.id), "--grund", "Gebühr falsch")
        assert "weist" not in text, text
    else:
        cli("korrigiere", kurz(b2.id), "--soll", "8400", "--haben", geld,
            "--steuer", "3")  # fmt: skip
        zwischen = _rest_von_b2(make_session, bel.id, b1.id)
        cli("korrigiere", kurz(zwischen.id), "--soll", "4530", "--haben", geld,
            "--steuer", "9")  # fmt: skip
    text = cli("buchung", "storniere", kurz(b1.id), "--grund", "doppelt erfasst")
    assert "weist 95,00 € Umsatzsteuer" in text, text
    text = cli("pruefen", "--regel", "beleg_ust_ohne_buchung")
    assert "1 Befunde" in text and "│ 95,00 │" in text, text
