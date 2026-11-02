"""OSS-Fernverkäufe je Kontenrahmen (Gesamttest 10b-1, Runde 3, gegen:regeln:0).

Eine eigene Rechnung an eine Privatkundin im übrigen Gemeinschaftsgebiet (Satz des
Bestimmungslands, § 3c UStG) bucht OPOS auf das OSS-Erlöskonto des Landes. Im SKR04
gab es dafür nur das Sammelkonto 4320 — die OSS-Meldung (§ 18j UStG) kannte nur die
SKR03-Konten 8320–8327 und zeigte „0,00“, auch nachdem 4320 in der Voranmeldung Kz 45
bekommen hatte. Jetzt: Länderkonten 4320–4327 (wie 8320–8327), Meldung, Schwelle,
Kz 45 und Prüfregel lesen die Konten des Kontenrahmens. Ein Land ohne eigenes Konto
geht nicht mehr auf das Konto eines anderen Landes (8320/4320 = FR), sondern auf
„Erlöse“ zur Prüfung, mit Hinweis.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db.repository import lade_buchungen, speichere_ausgangsrechnung
from accounti.erechnung.ausstellung import stelle_aus
from accounti.integrationen.oss import oss_meldung
from accounti.konfiguration import Buchhaltung
from accounti.models import Buchungssatz, BuchungStatus, Rechnungsempfaenger
from accounti.opos.verbuchung import verbuche_belege
from accounti.steuer.kennziffern import KENNZIFFERN_KONTEN
from accounti.steuer.oss import OSSEngine
from tests.pruefung_hilfe import make_session_fixture  # noqa: F401
from tests.test_erechnung_aufbau import FIRMA, entwurf, pos

D = Decimal
SKR03 = Buchhaltung()
SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800", standard_aufwand="6300")
FIRMA_OSS = FIRMA.model_copy(update={"oss": True})


def kundin(land: str) -> Rechnungsempfaenger:
    return Rechnungsempfaenger(
        name=f"Claire Martin {land}",
        strasse="1 rue de Rivoli",
        plz="75001",
        ort="Paris",
        land=land,
        ust_id=None,
        email="claire@example.fr",
        privat=True,
    )


def verbuche(make_session, tmp_path, bh: Buchhaltung, land: str):  # noqa: ANN001, ANN201
    archiv = BelegArchiv(tmp_path / "archiv")
    e = entwurf(kundin(land), pos("Rahmen", "400"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA_OSS, date(2026, 3, 10))
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, bh, archiv=archiv)
        s.commit()
    return lauf


@pytest.mark.parametrize(
    ("bh", "erloes"), [(SKR03, "8320"), (SKR04, "4320")], ids=["SKR03", "SKR04"]
)
def test_oss_fernverkauf_steht_in_der_oss_meldung(make_session, tmp_path, bh, erloes):
    verbuche(make_session, tmp_path, bh, "FR")
    with make_session() as s:
        erloese = [b for b in lade_buchungen(s) if b.haben_konto == erloes]
        assert [(b.betrag_netto, b.status) for b in erloese] == [
            (D("400.00"), BuchungStatus.ZUR_PRUEFUNG)
        ]
        meldung = oss_meldung(s, 2026, 1, kontenrahmen=bh.kontenrahmen)
    zeilen = [
        (x.land_code, x.bemessungsgrundlage_normal, x.steuer_normal, x.anzahl_normal)
        for x in meldung.laender
    ]
    assert zeilen == [("FR", D("400.00"), D("80.00"), 1)]
    assert KENNZIFFERN_KONTEN[bh.kontenrahmen][erloes] == 45


def test_skr04_laenderkonten_wie_im_skr03(make_session, tmp_path):
    """Italien auf 4321 (wie 8321) — gemeldet mit dem Satz Italiens."""
    archiv = BelegArchiv(tmp_path / "archiv")
    e = entwurf(kundin("IT"), pos("Rahmen", "100"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA_OSS, date(2026, 3, 10))
        s.commit()
    with make_session() as s:
        verbuche_belege(s, SKR04, archiv=archiv)
        s.commit()
    with make_session() as s:
        assert any(b.haben_konto == "4321" for b in lade_buchungen(s))
        meldung = oss_meldung(s, 2026, 1, kontenrahmen="SKR04")
    assert [(x.land_code, x.steuer_normal) for x in meldung.laender] == [
        ("IT", D("22.00"))
    ]


@pytest.mark.parametrize("bh", [SKR03, SKR04], ids=["SKR03", "SKR04"])
def test_land_ohne_oss_konto_nicht_als_frankreich_gemeldet(make_session, tmp_path, bh):
    lauf = verbuche(make_session, tmp_path, bh, "DK")
    unbekannt = "8200" if bh.kontenrahmen == "SKR03" else "4200"
    with make_session() as s:
        erloese = [b for b in lade_buchungen(s) if b.haben_konto == unbekannt]
        assert [(b.betrag_netto, b.status) for b in erloese] == [
            (D("400.00"), BuchungStatus.ZUR_PRUEFUNG)
        ]
        meldung = oss_meldung(s, 2026, 1, kontenrahmen=bh.kontenrahmen)
    assert meldung.laender == []  # nicht als FR (Konto 8320/4320) gemeldet
    hinweise = " ".join(h for v in lauf.verbucht for h in v.hinweise)
    assert "kein OSS-Erlöskonto für DK" in hinweise
    assert "selbst melden" in hinweise


def _buchung(haben: str, netto: str = "500.00") -> Buchungssatz:
    return Buchungssatz(
        datum=date(2026, 5, 4),
        soll_konto="1400",
        haben_konto=haben,
        betrag_netto=D(netto),
        buchungstext="Fernverkauf",
        beleg_nummer="RE-1",
    )


def test_skr04_meldung_und_schwelle_lesen_auch_die_marktplatzkonten():
    """Im SKR04 bucht die Marktplatz-Abrechnung weiter auf 8320–8327 (Klasse 8 frei)
    — Meldung und Schwelle zählen beide; im SKR03 ist 4320 die Gewerbesteuer."""
    buchungen = [_buchung("4320"), _buchung("8320"), _buchung("4326", "200.00")]
    meldung = OSSEngine().erstelle_meldung(buchungen, 2026, 2, kontenrahmen="SKR04")
    assert sorted(
        (x.land_code, x.bemessungsgrundlage_normal) for x in meldung.laender
    ) == [("AT", D("200.00")), ("FR", D("1000.00"))]
    _, summe = OSSEngine().pruefe_schwelle(buchungen, 2026, kontenrahmen="SKR04")
    assert summe == D("1200.00")
    skr03 = OSSEngine().erstelle_meldung(buchungen, 2026, 2)
    assert [(x.land_code, x.bemessungsgrundlage_normal) for x in skr03.laender] == [
        ("FR", D("500.00"))
    ]
    assert KENNZIFFERN_KONTEN["SKR04"]["8320"] == 45
    assert "4320" not in KENNZIFFERN_KONTEN["SKR03"]
