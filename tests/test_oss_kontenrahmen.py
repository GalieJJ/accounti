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
    """Im SKR04 buchte die Marktplatz-Abrechnung bis Paket E auf 8320–8327 (Klasse 8
    frei; seitdem Vorgabe 4320–4327) — Meldung und Schwelle zählen beide; im SKR03 ist
    4320 die Gewerbesteuer."""
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


# --- OSS-Umsatzsteuer: Steuerkonto des Kontenrahmens (Merge Paket E, NACHARBEITEN) ---
# Im SKR04 buchte OPOS die OSS-Steuer auf 177720/1779 (seit Paket C, SKR03-Konvention),
# nach dem Merge mit Paket E auf 1767 — beides liegt im SKR04 im Bank- und
# Zahlungsmittelbereich 1700–1889: `abschluss pruefen` meldete „Bankkonto … nicht
# eingerichtet“ (Abschluss gesperrt), und die Zahlung an das BZSt ließ sich nicht als
# Regel lernen („beide Geldkonten“). DATEV SKR04 3817 „Umsatzsteuer aus im anderen
# EU-Land steuerpflichtigen Lieferungen“ ist das Gegenstück zu SKR03 1767 (gleich
# bezeichnet im DATEV-Kontenrahmen § 4 Abs. 3 EStG 2026, Paritätstabelle in
# test_abschluss_kontenrahmen) und liegt in den Steuerkonten 3800–3849.

OSS_UST = {"SKR03": "1767", "SKR04": "3817"}


def _steuerbuchung(make_session):  # noqa: ANN001, ANN202
    with make_session() as s:
        (b,) = [x for x in lade_buchungen(s) if x.betrag_netto == D("80.00")]
    return b


@pytest.mark.parametrize("bh", [SKR03, SKR04], ids=["SKR03", "SKR04"])
def test_oss_steuer_auf_dem_steuerkonto_des_kontenrahmens(make_session, tmp_path, bh):
    from accounti.abschluss.kontenrahmen import Kontenart, lade_kontenrahmen

    verbuche(make_session, tmp_path, bh, "FR")
    ust = OSS_UST[bh.kontenrahmen]
    b = _steuerbuchung(make_session)
    assert (b.soll_konto, b.haben_konto) == ("10000", ust)
    kr = lade_kontenrahmen(bh.kontenrahmen)
    assert not kr.ist_bankkonto(ust) and not kr.ist_zahlungsmittel(ust)
    assert not kr.ist_geldkonto(ust)
    # wie jedes Umsatzsteuerkonto: in der EÜR Zeile 140, in der Bilanz Bestand
    assert kr.art(ust, "euer") is Kontenart.ERFOLG
    assert kr.euer_kz(ust, D("-80.00")) == "140"
    assert kr.art(ust, "bilanz") is Kontenart.BESTAND
    assert kr.bezeichnung(ust).startswith("Umsatzsteuer aus im anderen EU-Land")


def test_skr04_abschluss_ohne_bankbefund_fuer_die_oss_steuer(make_session, tmp_path):
    from accounti.abschluss.pruefungen import kontext, pruefe_abschluss
    from accounti.db.repository import setze_status

    config = tmp_path / "accounti.yaml"
    config.write_text(
        "buchhaltung:\n  kontenrahmen: SKR04\n  bank_konto: '1800'\n"
        "  standard_aufwand: '6300'\n",
        encoding="utf-8",
    )
    verbuche(make_session, tmp_path, SKR04, "FR")
    with make_session() as s:
        for b in lade_buchungen(s):
            setze_status(s, str(b.id), BuchungStatus.GEPRUEFT)
        s.commit()
    with make_session() as s:
        befunde = pruefe_abschluss(kontext(s, 2026, config), nur=["bank"])
    assert [b.text for b in befunde if "nicht eingerichtet" in b.text] == []


@pytest.mark.parametrize("bh", [SKR03, SKR04], ids=["SKR03", "SKR04"])
def test_oss_zahlung_an_das_bzst_als_regel_lernbar(make_session, tmp_path, bh):
    from accounti.klassifikation.lernen import entwurf_fuer
    from accounti.models import Transaktion, TransaktionQuelle

    verbuche(make_session, tmp_path, bh, "FR")
    ust = _steuerbuchung(make_session).haben_konto
    zahlung = Transaktion(
        datum=date(2026, 4, 20),
        betrag=D("-80.00"),
        verwendungszweck="OSS-Zahlung Q1/2026 Bundeszentralamt fuer Steuern",
        gegenkonto_name="Bundeskasse",
        quelle=TransaktionQuelle.BANK,
        rohtext="OSS-Zahlung Q1/2026",
    )
    e = entwurf_fuer(zahlung, ust, bh.bank_konto, None, bh)
    assert (e.soll_konto, e.haben_konto) == (ust, bh.bank_konto)


@pytest.mark.parametrize("bh", [SKR03, SKR04], ids=["SKR03", "SKR04"])
def test_oss_steuerabgleich_ohne_differenz(make_session, tmp_path, bh):
    """Die OSS-Meldung gleicht die gemeldete Steuer gegen die gebuchte auf dem
    OSS-Steuerkonto der Einstellungen ab (``integrationen.oss_ust_konto``, Vorgabe je
    Kontenrahmen) — OPOS bucht auf dasselbe Konto."""
    from accounti.integrationen.einstellungen import lade_integrationen
    from accounti.integrationen.oss import steuerabgleich

    config = tmp_path / "accounti.yaml"
    config.write_text(
        f"buchhaltung:\n  kontenrahmen: {bh.kontenrahmen}\n"
        f"  bank_konto: '{bh.bank_konto}'\n",
        encoding="utf-8",
    )
    einstellungen = lade_integrationen(config)
    assert einstellungen.oss_ust_konto == OSS_UST[bh.kontenrahmen]
    verbuche(make_session, tmp_path, bh, "FR")
    with make_session() as s:
        meldung = oss_meldung(
            s, 2026, 1, einstellungen=einstellungen, kontenrahmen=bh.kontenrahmen
        )
        assert steuerabgleich(s, meldung, "DE", einstellungen) == []
        # ohne Einstellungen: das Steuerkonto des Kontenrahmens
        assert steuerabgleich(s, meldung, "DE", kontenrahmen=bh.kontenrahmen) == []
