"""Richtung einer Belegbuchung: Altbestand, Zahlungen zum Beleg und Erlöse auf Belegen
ohne eindeutige Belegart (Gesamttest 10b-1, Runde 8: g7w R7-1, R7-2, R7-3).

R7-1: Wurde eine falsch herum gebuchte Belegbuchung früher (main bzw. Runde ≤ 4, ohne
Richtungsprüfung) umgedreht, maß die Kettenprüfung jede weitere Korrektur auch am
Fehlstand davor — selbst ein anderer Debitor war gesperrt. Jetzt zählen die Stände,
mit deren Richtung kein späterer Stand bricht.

R7-2: Der Rückfall auf die Seite der Rechnung (``_belegseite``) galt auch für Zahlung,
Erstattung, Verrechnung und Skonto mit derselben ``beleg_id``; „1200 an 70001 → 1200
an 4930“ (Erstattung als Preisnachlass) und „1590 an 10001 → 8730 an 10001“ (Skonto)
waren gesperrt. Skonto und Erlösschmälerung sind negative Umsätze — die neue negative
Kennziffer (Runde 7, N2) sperrt sie dort nicht.

R7-3: Erlösbuchungen mit Umsatzsteuer auf einer Quittung, einer Marktplatzabrechnung
(SONSTIGES) oder einem unbekannten Beleg galten als Eingangsbeleg: Hinweis
„Fehlschlüssel“, Schlüssel 9 und „ohne Steuer“ in der Auswahl, ``--ohne-steuer
--grund`` strich die Umsatzsteuer eines Erlöses, das Storno warnte nicht (§ 14c).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.db.repository import aktualisiere_buchung, lade_buchungen
from accounti.konfiguration import Buchhaltung
from accounti.models import Belegart, Belegrichtung, BuchungStatus
from accounti.pruefung import storno as st
from accounti.pruefung.person import journal_kontext
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
SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800")
ART = {
    "AR": (Belegart.AUSGANGSRECHNUNG, Belegrichtung.AUSGANG),
    "ER": (Belegart.EINGANGSRECHNUNG, Belegrichtung.EINGANG),
    "Q": (Belegart.QUITTUNG, Belegrichtung.EINGANG),
    "S": (Belegart.SONSTIGES, Belegrichtung.EINGANG),
    "U": (Belegart.UNBEKANNT, Belegrichtung.EINGANG),
}


def _beleg(art: str, netto: str = "500.00", steuer: str | None = "95.00", satz="19"):  # noqa: ANN001, ANN202
    belegart, richtung = ART[art]
    positionen = [] if satz is None else [("Leistung", netto, satz, steuer)]
    return beleg(
        belegart=belegart,
        richtung=richtung,
        nummer=f"B-{uuid4().hex[:6]}",
        tag=TAG,
        netto=netto if satz is not None else None,
        steuer=steuer if satz is not None else None,
        brutto=str(D(netto) + D(steuer or "0")),
        lieferant="Partner GmbH",
        positionen=positionen,
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


def _wirksam(make_session, beleg_id) -> list[Any]:  # noqa: ANN001
    with make_session() as s:
        return [
            b
            for b in lade_buchungen(s)
            if b.beleg_id == beleg_id
            and b.storno_von is None
            and b.storniert_durch is None
        ]


def _korrigiere(make_session, buchung_id, soll, haben, **optionen):  # noqa: ANN001, ANN003, ANN202
    optionen.setdefault("grund", "Test")
    with make_session() as s:
        k = korrigiere(s, str(buchung_id), soll, haben, von="erika", **optionen)
        s.commit()
    return k


def _kennziffern(make_session, skr04: bool = False) -> dict[int, Decimal]:  # noqa: ANN001
    with make_session() as s:
        plan = st.kontenplan(s, SKR04 if skr04 else None, None)
        alle = lade_buchungen(s)
        summe: dict[int, Decimal] = {}
        for b in alle:
            eigene = [x for x in alle if x.beleg_id == b.beleg_id]
            for kz, v in kennziffern_der_buchung(b, plan, eigene).items():
                summe[kz] = summe.get(kz, D(0)) + v
    return {k: v for k, v in summe.items() if v}


# --- R7-1: Altfall-Kette -------------------------------------------------------------


def _wie_main(make_session, b, soll: str, haben: str, kr) -> None:  # noqa: ANN001
    """Wie main (2305d47) ``korrigiere`` ohne Richtungsprüfung: eine freigegebene
    Buchung per Storno und Neubuchung (``buchungskorrekturen``), ein Vorschlag direkt
    überschrieben (Journal) und danach freigegeben."""
    aenderung = {
        "soll_konto": soll,
        "haben_konto": haben,
        "status": BuchungStatus.KORRIGIERT,
        "confidence": 1.0,
    }
    with make_session() as s:
        if st.ist_freigegeben(b):
            neu = b.model_copy(
                update={**aenderung, "id": uuid4(), "storniert_durch": None}
            )
            st._storno(s, b, "alt", "Altfall main", None, kr, neu)
        else:
            with journal_kontext(person="alt", grund="Altfall main"):
                aktualisiere_buchung(s, str(b.id), b.model_copy(update=aenderung))
                s.flush()
            s.commit()
            st.freigeben(s, str(b.id), von="alt")
        s.commit()


# (id, SKR04?, Belegart, Start (Soll, Haben, Schlüssel, Steuer), Altkorrektur, Schritte)
ALTFAELLE: list[tuple[str, bool, str, tuple, tuple, list]] = [
    ("A1_ausgang", False, "AR", ("8400", "10001", 3, "95.00"), ("10001", "8400"),
     [("10002", "8400", {}), ("10001", "8400", {"steuer": 3})]),
    ("A2_eingang", False, "ER", ("70001", "4930", 9, "95.00"), ("4930", "70001"),
     [("4930", "70002", {}), ("0420", "70001", {"steuer": 9})]),
    ("A3_ig_lieferung", False, "AR", ("8125", "10001", None, None), ("10001", "8125"),
     [("10001", "8120", {}), ("10002", "8120", {})]),
    ("G1_skr04", True, "AR", ("4400", "10001", 3, "95.00"), ("10001", "4400"),
     [("10002", "4400", {})]),
]  # fmt: skip


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("skr04", "art", "start", "alt", "schritte"),
    [f[1:] for f in ALTFAELLE],
    ids=[f[0] for f in ALTFAELLE],
)
def test_altfall_kette_misst_am_berichtigten_stand(
    make_session, status, skr04, art, start, alt, schritte
):
    """R7-1 (altfall_main.py, falsch.py A1–A3, G1): Nach der Berichtigung auf main
    gehen Korrekturen derselben Seite wieder (Runde 6: ja, Runde 7: gesperrt)."""
    soll, haben, schluessel, steuer = start
    satz = "19" if steuer else "0"
    bel = _beleg(art, steuer=steuer or "0.00", satz=satz)
    b = _buchung(bel, soll, haben, schluessel, steuer, status=status)
    anlegen(make_session, bel, b)
    umgebung: dict[str, Any] = {}
    if skr04:
        umgebung = {"buchhaltung": SKR04, "kontenrahmen": lade_kontenrahmen("SKR04")}
    _wie_main(make_session, b, *alt, umgebung.get("kontenrahmen", lade_kontenrahmen()))
    for s_, h_, optionen in schritte:
        (akt,) = _wirksam(make_session, bel.id)
        k = _korrigiere(make_session, akt.id, s_, h_, **optionen, **umgebung)
        assert k.neu is not None and (k.neu.soll_konto, k.neu.haben_konto) == (s_, h_)


def test_altfall_bleibt_auf_der_berichtigten_seite(make_session):
    """Zurück zum Fehlstand geht es nicht: der berichtigte Stand bestimmt die Richtung,
    wie jeder Stand, mit dem kein späterer bricht — auch über einen Zwischenschritt mit
    unbestimmter Seite (U01 nach dem Altfall)."""
    bel = _beleg("AR", steuer="0.00", satz="0")
    b = _buchung(bel, "8125", "10001")
    anlegen(make_session, bel, b)
    _wie_main(make_session, b, "10001", "8125", lade_kontenrahmen())
    (akt,) = _wirksam(make_session, bel.id)
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, akt.id, "8125", "10001")
    assert "Konto 8125 aus dem Haben ins Soll" in fehler.value.meldung
    k = _korrigiere(make_session, akt.id, "10001", "1590")
    assert k.neu is not None
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, k.neu.id, "8125", "1200")
    assert "„10001 an 8125“" in fehler.value.meldung


def test_altfall_ueber_unbestimmten_zwischenstand(make_session):
    """Auch ein Altfall, der die Seite über einen unbestimmten Stand gewechselt hat
    („8400 an 10001 → 10001 an 1590 → 10001 an 8400“, alles ohne Sperre): es zählt der
    berichtigte Stand."""
    bel = _beleg("AR")
    b = _buchung(bel, "8400", "10001", 3, "95.00")
    anlegen(make_session, bel, b)
    kr = lade_kontenrahmen()
    _wie_main(make_session, b, "10001", "1590", kr)
    (akt,) = _wirksam(make_session, bel.id)
    _wie_main(make_session, akt, "10001", "8400", kr)
    (akt,) = _wirksam(make_session, bel.id)
    k = _korrigiere(make_session, akt.id, "10002", "8400")
    assert k.neu is not None and k.neu.soll_konto == "10002"


# --- R7-2: Zahlung, Erstattung, Verrechnung und Skonto zum Beleg ---------------------


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("art", "rechnung", "neben", "ziel", "optionen", "kennziffer"),
    [
        # C2: Erstattung als Preisnachlass direkt auf den Aufwand
        ("ER", ("4930", "70001", 9, "95.00"), ("1200", "70001", "100.00"),
         ("1200", "4930"), {}, None),
        # N2_1: auf 1590 geparktes Skonto, ohne und mit Umsatzsteuerkorrektur
        ("AR", ("10001", "8400", 3, "95.00"), ("1590", "10001", "11.90"),
         ("8730", "10001"), {}, None),
        ("AR", ("10001", "8400", 3, "95.00"), ("1590", "10001", "11.90"),
         ("8736", "10001"), {"steuer": 3}, (81, "-10.00")),
        # N2_2: Skonto ohne Schlüssel → gewährtes Skonto 19 %
        ("AR", ("10001", "8400", 3, "95.00"), ("8730", "10001", "11.90"),
         ("8736", "10001"), {"steuer": 3}, (81, "-10.00")),
        # N2_3, N2_4: erhaltenes Skonto bzw. Bonus mindert die Vorsteuer
        ("ER", ("4930", "70001", 9, "95.00"), ("70001", "1590", "11.90"),
         ("70001", "3736"), {"steuer": 9}, (66, "-1.90")),
        ("ER", ("4930", "70001", 9, "95.00"), ("1200", "70001", "59.50"),
         ("1200", "3736"), {"steuer": 9}, (66, "-9.50")),
        # N2_5: Rabatt als Erlösschmälerung
        ("AR", ("10001", "8400", 3, "95.00"), ("1590", "10001", "59.50"),
         ("8720", "10001"), {"steuer": 3}, (81, "-50.00")),
    ],
    ids=["C2_erstattung", "N2_1_8730", "N2_1_8736", "N2_2", "N2_3", "N2_4", "N2_5"],
)  # fmt: skip
def test_zahlung_zum_beleg_wird_minderung(
    make_session, status, art, rechnung, neben, ziel, optionen, kennziffer
):
    """R7-2 (falsch.py C2, n2.py): Die Seite der Rechnung gilt nicht für Zahlungen und
    Verrechnungen desselben Belegs, und ein Skonto bzw. eine Erlösschmälerung darf die
    Kennziffer negativ buchen."""
    bel = _beleg(art)
    r = _buchung(bel, *rechnung)
    z = _buchung(bel, neben[0], neben[1], netto=neben[2], status=status)
    anlegen(make_session, bel, r, z)
    vorher = _kennziffern(make_session)
    k = _korrigiere(make_session, z.id, *ziel, **optionen)
    assert k.neu is not None and (k.neu.soll_konto, k.neu.haben_konto) == ziel
    nachher = _kennziffern(make_session)
    if kennziffer is not None:
        kz, betrag = kennziffer
        assert nachher[kz] - vorher.get(kz, D(0)) == D(betrag), nachher


def test_skr04_skonto_aus_verrechnung(make_session):
    """N2_9: im SKR04 „1370 an 10001 → 4736 an 10001, Schlüssel 3“."""
    bel = _beleg("AR")
    r = _buchung(bel, "10001", "4400", 3, "95.00")
    z = _buchung(bel, "1370", "10001", netto="11.90")
    anlegen(make_session, bel, r, z)
    k = _korrigiere(
        make_session, z.id, "4736", "10001", steuer=3,
        buchhaltung=SKR04, kontenrahmen=lade_kontenrahmen("SKR04"),
    )  # fmt: skip
    assert k.neu is not None and k.neu.soll_konto == "4736"


def test_geparkte_rechnung_misst_weiter_am_beleg(make_session):
    """Ohne eigene Rechnungsbuchung kann die Buchung auf zwei Gegenkonten die Rechnung
    selbst sein („10001 an 1590“ als erster Vorschlag): Der Rückfall auf die Seite der
    Ausgangsrechnung bleibt, aus dem Erlös wird keine Erlösschmälerung."""
    bel = _beleg("AR")
    b = _buchung(bel, "10001", "1590", status=P, netto="595.00")
    anlegen(make_session, bel, b)
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, b.id, "8736", "1200", steuer=3)
    assert "die Ausgangsrechnung bucht ihr Erfolgskonto" in fehler.value.meldung
    k = _korrigiere(make_session, b.id, "10001", "8400", steuer=3)
    assert k.neu is not None and k.neu.haben_konto == "8400"


def test_zahlung_wird_kein_erloes_mit_negativer_kennziffer(make_session):
    """Aus einer Zahlung wird kein negativer Erlös auf einem Erlöskonto, das keine
    Erlösschmälerung ist („1590 an 10001 → 8125 an 10001“: Kz 41 −) — N2 bleibt."""
    bel = _beleg("AR", steuer="0.00", satz="0")
    r = _buchung(bel, "10001", "8125")
    z = _buchung(bel, "1590", "10001", netto="50.00")
    anlegen(make_session, bel, r, z)
    with pytest.raises(StornoError) as fehler:
        _korrigiere(make_session, z.id, "8125", "10001")
    assert "Kz 41 mit -50,00 €" in fehler.value.meldung


# --- R7-3: Erlös auf Quittung, Marktplatzabrechnung, unbekanntem Beleg ---------------

ERLOESE: list[tuple[str, str, tuple, str | None]] = [
    ("Q2_eigener_kassenbon", "Q", ("1000", "8400"), "19"),
    ("S1_marktplatz_ohne_satz", "S", ("1590", "8400"), None),
    ("S3_sonstiges_19", "S", ("1590", "8400"), "19"),
    ("S4_unbekannt", "U", ("10001", "8400"), "19"),
    ("X3_quittung_8200", "Q", ("1000", "8200"), "19"),
]


@pytest.mark.parametrize(
    ("art", "konten", "satz"), [f[1:] for f in ERLOESE], ids=[f[0] for f in ERLOESE]
)
def test_erloes_ohne_eindeutige_belegart_ist_ausgewiesene_steuer(
    make_session, art, konten, satz
):
    """R7-3 (n5.py, n5b.py): kein Hinweis „Fehlschlüssel“, kein Schlüssel 9, kein „ohne
    Steuer“ — die Buchung bucht einen Erlös, § 14c gilt wie beim Ausgangsbeleg."""
    bel = _beleg(art, satz=satz)
    b = _buchung(bel, *konten, 3, "95.00", status=P)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel, Kontenplan())
    assert optionen.schluessel == (3,), optionen
    assert not optionen.ohne_steuer and optionen.laut_beleg in (None, 3)
    assert "§ 14c" in (optionen.hinweis or "")
    assert "Fehlschlüssel" not in (optionen.hinweis or "")
    for weg in ({"steuer": 9}, {"ohne_steuer": True}):
        with pytest.raises(StornoError) as fehler:
            _korrigiere(make_session, b.id, *konten, **weg)
        assert fehler.value.feld == "steuer", fehler.value.meldung
    assert _wirksam(make_session, bel.id)[0].steuer_schluessel == 3


@pytest.mark.parametrize("art", ["Q", "U"])
def test_storno_eines_erloeses_ohne_eindeutige_belegart_warnt(make_session, art):
    """Q2/S4: Das Storno warnt wieder nach § 14c (Runde 6: ja, Runde 7: nein)."""
    bel = _beleg(art)
    b = _buchung(bel, "1000" if art == "Q" else "10001", "8400", 3, "95.00")
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = st.storniere(s, str(b.id), grund="doppelt", von="erika")
        s.commit()
    assert any("95,00 € Umsatzsteuer" in w and "§ 14c" in w for w in k.warnungen)


def test_aufwand_auf_quittung_bleibt_fehlschluessel(make_session):
    """Q1: „4930 an 1000, Schlüssel 3“ auf einer Quittung bucht Aufwand — Schlüssel 3
    bleibt ein Fehlschlüssel, laut Beleg 9 (ohne Grund)."""
    bel = _beleg("Q")
    b = _buchung(bel, "4930", "1000", 3, "95.00", status=P)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel, Kontenplan())
    assert optionen.laut_beleg == 9 and "Fehlschlüssel" in (optionen.hinweis or "")
    k = _korrigiere(make_session, b.id, "4930", "1000", steuer=9, grund=None)
    assert k.neu is not None and k.neu.steuer_schluessel == 9
