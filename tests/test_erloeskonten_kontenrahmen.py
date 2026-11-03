"""Erlöskonten je Kontenrahmen für Ausgangsbelege (Gesamttest 10b-1 nach dem Merge,
M-3; besteht auf main).

Ein Zahlungseingang mit bestätigtem Ausgangsbeleg (Belegbuchung) und eine
Ausgangsrechnung über OPOS bucht im SKR04 auf die Erlöskonten des SKR04 (4400 bei
19 %, 4300 bei 7 %, 4200 ohne erkennbaren Satz, steuerfrei 4125/4120/4100/4336) —
bisher auf die SKR03-Konten 8400/8300/8200, die im SKR04 „zur freien Verfügung“
stehen: Die Anlage EÜR zeigte die Einnahme als „nicht zugeordnet“ (8400).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.abschluss.euer import erstelle_euer
from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.abschluss.salden import summen_und_salden
from accounti.buchung.konten import erloeskonten
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.buchung.mit_beleg import kontiere_mit_beleg
from accounti.db.repository import lade_buchungen, speichere_abgleich
from accounti.klassifikation.engine import KlassifikationsEngine, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Belegabgleich,
    Belegart,
    Belegrichtung,
    BuchungStatus,
)
from accounti.steuer.kennziffern import KENNZIFFERN_KONTEN
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    make_session_fixture,
    umsatz,
)

SKR03 = Buchhaltung()
SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800", standard_aufwand="6300")


def ausgang(*positionen: tuple[str, str, str | None, str | None], brutto: str):  # noqa: ANN201
    return beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer="RE-2026-0042",
        lieferant="Probe GmbH",
        netto=None,
        steuer=None,
        brutto=brutto,
        datei_hash=uuid4().hex * 2,
        positionen=list(positionen),
    )


@pytest.mark.parametrize(
    ("bh", "bank", "e19", "e7", "unbekannt"),
    [(SKR03, "1200", "8400", "8300", "8200"), (SKR04, "1800", "4400", "4300", "4200")],
    ids=["SKR03", "SKR04"],
)
def test_belegbuchung_bucht_auf_die_erloese_des_kontenrahmens(
    bh, bank, e19, e7, unbekannt
):
    b = ausgang(
        ("Rahmen", "100.00", "19", "19.00"),
        ("Katalog", "20.00", "7", "1.40"),
        ("Sonderposten", "10.00", "16", "1.60"),
        brutto="152.00",
    )
    buchungen = kontiere_mit_beleg(umsatz("152.00"), b, bh, RegelwerkEngine([]))
    zeilen = {(x.soll_konto, x.haben_konto, x.steuer_schluessel) for x in buchungen}
    assert zeilen == {(bank, e19, 3), (bank, e7, 2), (bank, unbekannt, None)}
    status = {x.haben_konto: x.status for x in buchungen}
    assert status[e19] is BuchungStatus.AUTO_GEBUCHT
    assert status[unbekannt] is BuchungStatus.ZUR_PRUEFUNG


def test_skr04_klassifizierung_und_euer_ohne_nicht_zugeordnete_einnahme(make_session):
    """Probe s6: classify bucht im SKR04 1800 an 4400; die EÜR ordnet die Einnahme
    der Zeile der umsatzsteuerpflichtigen Betriebseinnahmen (Kz 112) zu."""
    tx = umsatz("119.00", date(2026, 10, 5), "RE-2026-0042", "Kunde Schmidt KG")
    b = ausgang(("Rahmen", "100.00", "19", "19.00"), brutto="119.00")
    anlegen(make_session, tx, b)
    with make_session() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=b.id,
                stufe="referenz",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="x",
            ),
        )
        kontiere_umsaetze(s, KlassifikationsEngine(RegelwerkEngine([])), SKR04)
        s.commit()
        (x,) = lade_buchungen(s)
        kr = lade_kontenrahmen("SKR04")
        euer = erstelle_euer(summen_und_salden(s, 2026, kr, "euer"), kr)
    assert (x.soll_konto, x.haben_konto, x.status) == (
        "1800",
        "4400",
        BuchungStatus.AUTO_GEBUCHT,
    )
    assert euer.nicht_zugeordnet == []
    zeile = euer.zeile("112")
    assert zeile is not None and zeile.konten == {"4400": Decimal("100.00")}


def test_steuerfreie_erloese_passen_zu_den_kennziffern():
    """Die steuerfreien Erlöskonten stammen aus ``KENNZIFFERN_KONTEN`` — so landen
    sie in der Voranmeldung in derselben Kennziffer wie im SKR03."""
    for name, kz in (("K", 41), ("G", 43), ("E", 48), ("AE", 21)):
        for rahmen in ("SKR03", "SKR04"):
            konto = erloeskonten(rahmen).steuerfrei[name]
            assert KENNZIFFERN_KONTEN[rahmen][konto] == kz, (rahmen, name)
    assert erloeskonten("SKR04").steuerfrei == {
        "K": "4125",
        "G": "4120",
        "E": "4100",
        "AE": "4336",
    }
