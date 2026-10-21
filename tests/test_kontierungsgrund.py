"""Herkunft und Begründung je Buchung — von jeder Quelle der Queue geschrieben
(Baustein 10b, Paket 1; Architekturprinzip 2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db.repo_kontierung import lade_kontierungsgruende, lade_kontierungsgrund
from accounti.db.repository import (
    lade_buchungen,
    speichere_abgleich,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Belegabgleich,
    BuchungStatus,
    Klassifikationsergebnis,
    Transaktion,
)
from accounti.pruefung.journal import pruefe_journal, uebernehme_bestand
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    make_session_fixture,
    umsatz,
)

BH = Buchhaltung()
D = Decimal


class LLMAttrappe:
    """Antwortet wie die LLM-Stufe — ohne Netz."""

    model = "attrappe/kontierer-1"

    def __init__(self) -> None:
        self.gefragt: list[str] = []

    def klassifiziere(self, tx: Transaktion) -> Klassifikationsergebnis:
        self.gefragt.append(tx.verwendungszweck)
        return Klassifikationsergebnis(
            transaktion_id=tx.id,
            soll_konto="4980",
            haben_konto="1200",
            steuer_schluessel=9,
            buchungstext=tx.verwendungszweck[:60],
            confidence=0.62,
            begruendung="Bürobedarf laut Gegenpartei, Betrag typisch",
            quelle="llm",
            modell=self.model,
        )


def _lauf(make_session, llm=None):  # noqa: ANN001, ANN202
    with make_session() as s:
        kontiere_umsaetze(s, KlassifikationsEngine(llm=llm), BH)  # type: ignore[arg-type]
        s.commit()
        buchungen = lade_buchungen(s)
        gruende = lade_kontierungsgruende(s, [b.id for b in buchungen])
    return buchungen, gruende


def test_regelwerk_grund_mit_regelname(make_session):
    anlegen(make_session, umsatz("-800.00", zweck="Miete Oktober Büro", name="Haus"))
    (b,), gruende = _lauf(make_session)
    g = gruende[b.id]
    assert (g.quelle, g.regel, g.modell) == ("regelwerk", "miete", None)
    assert "Regel 'miete'" in g.begruendung


def test_llm_begruendung_quelle_und_modell(make_session):
    anlegen(make_session, umsatz("-59.50", zweck="RE 4711", name="Müller GmbH"))
    attrappe = LLMAttrappe()
    (b,), gruende = _lauf(make_session, attrappe)
    g = gruende[b.id]
    assert (g.quelle, g.modell) == ("llm", "attrappe/kontierer-1")
    assert g.begruendung == "Bürobedarf laut Gegenpartei, Betrag typisch"
    assert b.status is BuchungStatus.ZUR_PRUEFUNG and b.confidence == 0.62


def _mit_beleg(make_session, betrag: str = "-119.00"):  # noqa: ANN202
    tx = umsatz(betrag, zweck="RE-2026-0815", name="Stadtwerke Hamburg")
    b = beleg()
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
                begruendung="Rechnungsnummer im Verwendungszweck",
            ),
        )
        s.commit()
    return _lauf(make_session)


def test_belegbuchung_sachkonto_quelle(make_session):
    (b,), gruende = _mit_beleg(make_session)
    g = gruende[b.id]
    assert g.quelle == "standard" and b.soll_konto == "4900"
    assert "Aus Beleg RE-2026-0815" in g.begruendung
    assert "Sachkonto 4900 — Standard" in g.begruendung


def test_abweichung_vom_beleg_im_grund(make_session):
    (b,), gruende = _mit_beleg(make_session, "-121.50")
    assert "weicht um 2,50 € vom Beleg ab" in gruende[b.id].begruendung
    assert b.status is BuchungStatus.ZUR_PRUEFUNG


def test_opos_verbuchung_speichert_grund_und_hinweise(make_session):
    from accounti.opos.verbuchung import verbuche_beleg
    from accounti.pruefung.perioden import schliesse

    rechnung = beleg(tag=date(2026, 8, 10))  # eingegangen 11.08.2026
    anlegen(make_session, rechnung)
    with make_session() as s:
        schliesse(s, "2026-08", "erika")
        s.commit()
    with make_session() as s:
        v = verbuche_beleg(s, rechnung, BH, buchungsdatum="offen")
        s.commit()
        (b,) = v.buchungen
        g = lade_kontierungsgrund(s, b.id)
    assert g is not None and g.quelle == "opos"
    assert "Stadtwerke Hamburg GmbH" in g.begruendung
    assert "Sachkonto 4900 — Standard" in g.begruendung
    assert "§ 15 Abs. 1 Nr. 1 UStG" in g.begruendung  # Hinweis zum Buchungsdatum


def test_kreditkarte_abweichung_als_grund(tmp_path):
    from accounti.bank.kreditkarte import gleiche_sammelbelastungen_ab
    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_bankkonto
    from accounti.models import Bankkonto
    from tests import test_bank_kreditkarte as kk

    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 'k.db'}")
    init_db(engine)
    with fabrik() as s:
        speichere_bankkonto(s, Bankkonto(iban=kk.GIRO, bezeichnung="Giro"))
        kk._uebernommen(s)
        kk._belastung(s, "-698.66")
        gleiche_sammelbelastungen_ab(s, kk.SKR03, kk.EINST)
        s.commit()
        (b,) = kk._buchungen_zu(s, "KREDITKARTENABRECHNUNG")
        g = lade_kontierungsgrund(s, b.id)
    engine.dispose()
    assert g is not None and g.quelle == "kreditkarte"
    assert "Differenz -0,01 €" in g.begruendung and "Rundungsposten" in g.begruendung


def test_afa_vorschlag_mit_rechenweg(tmp_path):
    from accounti.anlagen.konfiguration import lade_anlagen
    from accounti.anlagen.lauf import afa_lauf
    from tests.abschluss_hilfe import anlegen as anlage_anlegen
    from tests.abschluss_hilfe import datenbank

    fabrik = next(datenbank(tmp_path))
    anlage_anlegen(fabrik, 3600, date(2026, 9, 15), nd=3)
    with fabrik() as s:
        (b,) = afa_lauf(s, 2026, lade_anlagen(tmp_path / "x.yaml")).buchungen
        s.commit()
        g = lade_kontierungsgrund(s, b.id)
    assert g is not None and g.quelle == "anlagen"
    assert g.begruendung.startswith("AfA: ") and "linear" in g.begruendung


def test_anlagenzugang_umbuchung_mit_grund(tmp_path):
    from accounti.anlagen.dienst import lege_an
    from accounti.anlagen.konfiguration import lade_anlagen
    from tests import test_anlagen_dienst as ad
    from tests.abschluss_hilfe import datenbank

    fabrik = next(datenbank(tmp_path))
    ad._beleg(fabrik, konto="4980")
    with fabrik() as s:
        e = lege_an(
            s,
            lade_anlagen(tmp_path / "x.yaml"),
            beleg="RE-4711",
            typ="bueromoebel",
            umbuchen=True,
        )
        s.commit()
        assert e.umbuchung is not None
        g = lade_kontierungsgrund(s, e.umbuchung.id)
    assert g is not None and g.quelle == "anlagen"
    assert "4980" in g.begruendung and "Umbuchung Anlagezugang" in g.begruendung


def test_marktplatz_auszahlung_und_abrechnung_mit_grund(tmp_path):
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.integrationen.einstellungen import lade_integrationen
    from accounti.integrationen.lauf import Kontext
    from tests import test_integrationen_lauf as il

    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    kontext = Kontext(
        einstellungen=lade_integrationen(tmp_path / "keine.yaml"),
        buchhaltung=Buchhaltung(),
        oss_registriert=True,
    )
    with fabrik() as s:
        eingang = il.bank(
            s, date(2026, 8, 18), "209.85", "AMAZON PAYMENTS EUROPE S.C.A. 11223344556"
        )
        il.amazon(s, BelegArchiv(tmp_path / "archiv"), kontext)
        s.commit()
        buchungen = lade_buchungen(s)
        gruende = lade_kontierungsgruende(s, [b.id for b in buchungen])
    engine.dispose()
    assert set(gruende) == {b.id for b in buchungen}
    assert {g.quelle for g in gruende.values()} == {"marktplatz"}
    (auszahlung,) = [b for b in buchungen if b.transaktion_id == eingang.id]
    assert "Auszahlung" in gruende[auszahlung.id].begruendung
    assert any("Amazon-Abrechnung" in g.begruendung for g in gruende.values())


def test_grund_in_derselben_transaktion(make_session):
    """Ein Rollback nimmt Buchung und Grund zurück."""
    anlegen(make_session, umsatz("-800.00", zweck="Miete Oktober", name="Haus"))
    with make_session() as s:
        kontiere_umsaetze(s, KlassifikationsEngine(), BH)
        s.flush()
        (b,) = lade_buchungen(s)
        assert lade_kontierungsgrund(s, b.id) is not None
        s.rollback()
    with make_session() as s:
        assert lade_buchungen(s) == []
        assert lade_kontierungsgrund(s, b.id) is None


def test_journal_bleibt_in_ordnung(make_session):
    """(Schutz) Bestand mit Journal aus Baustein 7, Kontierungslauf mit Gründen —
    der Journalabgleich bleibt in Ordnung (Gründe stehen nicht im Journal)."""
    alt = buchung(status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, alt)
    with make_session() as s:
        uebernehme_bestand(s)
        s.commit()
    anlegen(
        make_session,
        umsatz("-800.00", zweck="Miete Oktober", name="Haus"),
        umsatz("-59.50", zweck="RE 4711", name="Müller GmbH"),
    )
    _lauf(make_session, LLMAttrappe())
    with make_session() as s:
        p = pruefe_journal(s)
    assert p.in_ordnung, [b.text for b in p.befunde]


@pytest.mark.parametrize("quelle", ["unbekannt", ""])
def test_unbekannte_quelle_abgelehnt(make_session, quelle):
    from pydantic import ValidationError

    from accounti.db.repo_kontierung import speichere_kontierungsgrund

    with make_session() as s, pytest.raises(ValidationError):
        speichere_kontierungsgrund(
            s,
            buchung().id,
            quelle=quelle,
            begruendung="x",  # type: ignore[arg-type]
        )


def _unbenutzt() -> None:  # pragma: no cover
    speichere_transaktion  # noqa: B018
    D  # noqa: B018
