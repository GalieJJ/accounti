"""Nachprüfung 6 E: fremde Umsätze und der Marktplatz-Abgleich.

Mb: opos-Zahlungsvorschlag und ``marktplatz zuordnen``; Mc: „schon gebucht“ nur mit
Stichwort oder Nummer, die Kasse ist keine Bank; Md: Umsätze eines anderen
Marktplatzes, mit der Nummer eines anderen oder einer Rechnung sind keine
Kandidaten; der festgeschriebene Monat; dazu die Niedrig-Befunde N-a bis N-i.
"""

import shlex
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repo_integrationen import lade_abrechnungen
from accounti.db.repository import (
    buchungen_zur_transaktion,
    lade_buchungen,
    lade_zuordnungen,
    speichere_buchung,
    speichere_kontakt,
    speichere_posten,
    speichere_zuordnung,
)
from accounti.integrationen.auszahlung import (
    ZuordnungError,
    gleiche_auszahlungen_ab,
    ordne_zu,
)
from accounti.integrationen.einstellungen import lade_integrationen
from accounti.integrationen.lauf import Kontext
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    Transaktion,
    TransaktionQuelle,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.models.integrationen import Schweregrad
from accounti.opos.zahlungslauf import ZahlungslaufError, bestaetige
from tests.test_integrationen_lauf import (
    FIXTURES,
    _als_erloes_gebucht,
    _amazon_ende_august,
    _bank_lauf_mit_regel,
    _ustva_warnungen,
    amazon,
    bank,
    saldo,
)

EBAY = "EBAY MANAGED PAYMENTS"


@pytest.fixture
def umgebung(tmp_path):
    """Wie in ``test_integrationen_lauf``: leere Datenbank, Archiv, Standardkontext."""
    engine, make = session_factory(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    kontext = Kontext(
        einstellungen=lade_integrationen(tmp_path / "keine.yaml"),
        buchhaltung=Buchhaltung(),
        oss_registriert=True,
    )
    with make() as s:
        yield s, BelegArchiv(tmp_path / "archiv"), kontext


def _amazon_september(s, archiv, kontext):
    """Amazon 11223344556 (16.–31.08.), Auszahlung 209,85 € am 02.09."""
    roh = _amazon_ende_august((FIXTURES / "amazon_abrechnung_v2.txt").read_bytes())
    (ergebnis,) = amazon(s, archiv, kontext, roh)
    return ergebnis


def _forderung(s, belegnummer, betrag, kunde="Galerie Nord GmbH", tag=None):
    """Offene Ausgangsrechnung eines Kunden (opos)."""
    k = Kontakt(name=kunde, debitor_konto="10001")
    speichere_kontakt(s, k)
    p = OffenerPosten(
        kontakt_id=k.id,
        beleg_id=uuid4(),
        richtung=PostenRichtung.FORDERUNG,
        belegnummer=belegnummer,
        belegdatum=tag or date(2026, 8, 1),
        betrag=Decimal(betrag),
        faellig_am=tag or date(2026, 8, 15),
    )
    speichere_posten(s, p)
    s.flush()
    return p


def _vorschlag(s, tx, posten):
    """Ein Zahlungsvorschlag von opos (wie ``zuordne_zahlungen``, Stufe unscharf)."""
    speichere_zuordnung(
        s,
        Zahlungszuordnung(
            transaktion_id=tx.id,
            posten_id=posten.id,
            betrag=tx.betrag,
            stufe="unscharf",
            status=ZuordnungStatus.VORGESCHLAGEN,
            confidence=0.6,
            begruendung="Kontakt unbekannt, aber genau ein offener Posten",
        ),
    )
    s.flush()


def _befunde(s, nummer, *, hinweise=False):
    (a,) = [x for x in lade_abrechnungen(s) if x.nummer == nummer]
    return [
        b
        for b in a.offene_befunde
        if b.code.startswith(("auszahlung", "zuordnung"))
        and (hinweise or b.schweregrad is not Schweregrad.HINWEIS)
    ]


# --- Mb: opos-Zahlungsvorschlag ---------------------------------------------------


def test_zuordnen_lehnt_umsatz_mit_zahlungsvorschlag_ab(umgebung):
    """Mb (a): opos hat den Umsatz einer fremden Forderung vorgeschlagen; der
    automatische Abgleich lässt ihn deshalb liegen (``offen_ids``), ``marktplatz
    zuordnen`` nahm ihn trotzdem — nach dem Bestätigen war er doppelt gebucht. Die
    Meldung nennt den Befehl, der den Vorschlag verwirft."""
    s, archiv, kontext = umgebung
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999")
    _vorschlag(s, tx, _forderung(s, "RE-2026-77", "209.85"))
    gleiche_auszahlungen_ab(s, kontext)
    ident = str(tx.id)[:8]
    with pytest.raises(ZuordnungError, match=f"accounti opos ablehnen {ident}"):
        ordne_zu(s, kontext, "11223344556", ident, von="erika")
    assert not buchungen_zur_transaktion(s, tx.id)


def test_bestaetige_lehnt_inzwischen_gebuchten_umsatz_ab(umgebung):
    """Mb (b): Steht der Umsatz inzwischen anderweitig gebucht (hier: als
    Geldbewegung auf dem Amazon-Verrechnungskonto), bucht ``opos bestaetige`` ihn
    nicht ein zweites Mal gegen die Forderung."""
    s, archiv, kontext = umgebung
    posten = _forderung(s, "RE-2026-77", "209.85")
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE")
    _vorschlag(s, tx, posten)
    speichere_buchung(
        s,
        Buchungssatz(
            transaktion_id=tx.id,
            datum=tx.datum,
            soll_konto="1200",
            haben_konto="1361",
            betrag_netto=Decimal("209.85"),
            buchungstext="Amazon Auszahlung",
            status=BuchungStatus.AUTO_GEBUCHT,
        ),
    )
    s.flush()
    with pytest.raises(ZahlungslaufError, match="schon gebucht"):
        bestaetige(s, str(tx.id)[:8], kontext.buchhaltung, von="erika")
    assert len(buchungen_zur_transaktion(s, tx.id)) == 1
    assert saldo(lade_buchungen(s), "10001") == 0


def test_bestaetige_lehnt_einer_auszahlung_zugeordneten_umsatz_ab(umgebung):
    """Mb (b): auch, wenn der Umsatz einer Marktplatz-Auszahlung zugeordnet ist."""
    s, archiv, kontext = umgebung
    posten = _forderung(s, "RE-2026-77", "209.85")
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE 11223344556")
    _vorschlag(s, tx, posten)
    # wie vor der Behebung (a): zugeordnet trotz Vorschlag
    from accounti.integrationen import auszahlung

    lauf = auszahlung._neuer_lauf(s, kontext, lade_abrechnungen(s))
    (a,) = lade_abrechnungen(s)
    (p,) = [x for x in a.posten if x.art.value == "auszahlung"]
    auszahlung._zuordnen(lauf, a, p, tx, Decimal("209.85"), von_hand=True)
    with pytest.raises(ZahlungslaufError, match="schon gebucht"):
        bestaetige(s, str(tx.id)[:8], kontext.buchhaltung, von="erika")


def test_bank_lauf_schlaegt_zurueckgehaltene_auszahlung_keiner_forderung_vor(umgebung):
    """Mb (c), Fall s14: Regel 4 hält die Amazon-Auszahlung zurück (Warnung mit dem
    zuordnen-Befehl), im selben ``bank lauf`` schlug opos sie einer fremden Forderung
    gleichen Betrags vor („Kontakt unbekannt, aber genau ein offener Posten“). Der
    Abgleich weiß, dass sie eine Auszahlung ist — opos lässt sie liegen."""
    s, archiv, kontext = umgebung
    _forderung(s, "RE-2026-77", "209.85", tag=date(2026, 8, 20))
    _amazon_september(s, archiv, kontext)
    tx = bank(
        s,
        date(2026, 9, 3),
        "209.85",
        "AMAZON PAYMENTS EUROPE EREF 11223399999",
        "Amazon Payments Europe S.C.A.",
    )
    lauf = _bank_lauf_mit_regel(s, kontext, r"AMAZON")
    (m,) = lauf.marktplatz
    assert m.befund is not None and m.befund.code == "auszahlung_andere_nummer"
    assert not lauf.zuordnung.vorgeschlagen and not lauf.zuordnung.gebucht
    assert not lade_zuordnungen(s)
    # der Befehl aus der Warnung geht jetzt ohne Umweg
    ordne_zu(s, kontext, "11223344556", str(tx.id)[:8], von="erika")
    assert saldo(lade_buchungen(s), "1200") == Decimal("209.85")
    assert saldo(lade_buchungen(s), "10001") == 0
