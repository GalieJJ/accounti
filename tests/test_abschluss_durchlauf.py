"""Durchlauf über ein synthetisches Geschäftsjahr (Spec 6).

Eröffnung → Bank, Kasse, Belege → Anlage und AfA → Abgrenzung (bei Bilanz) →
Prüfungen → Summen- und Saldenliste → EÜR (bei EÜR) → Saldovortrag → die
Eröffnungssalden des Folgejahres sind exakt die Schlusssalden, und das Folgejahr
rechnet darauf weiter (Kasse, Bank, Anlagenspiegel).
"""

from datetime import date
from decimal import Decimal

import pytest

from accounti.abschluss.abgrenzung import (
    bestaetige_abgrenzung,
    schlage_abgrenzungen_vor,
)
from accounti.abschluss.euer import erstelle_euer
from accounti.abschluss.kassenbuch import anfangsbestand, bestand, buche_kasse
from accounti.abschluss.pruefungen import (
    Schwere,
    erfasse_kontoauszugssaldo,
    kontext,
    pruefe_abschluss,
)
from accounti.abschluss.vortrag import (
    erfasse_eroeffnung,
    eroeffnungssalden,
    schlusssalden,
    trage_vor,
)
from accounti.anlagen.dienst import lege_an
from accounti.anlagen.lauf import afa_lauf, freigeben
from accounti.anlagen.spiegel import anlagenspiegel
from accounti.db.repo_abschluss import ist_gesperrt
from accounti.db.repo_anlagen import lade_anlagen as lade_anlagegueter
from accounti.db.repo_kasse import lade_kassenbuch
from accounti.db.repository import speichere_bankkonto, speichere_beleg
from accounti.models import Bankkonto, Beleg, Belegposition
from accounti.models.anlagen import AfaArt
from tests.abschluss_hilfe import buche, datenbank

D = Decimal
J = 2026
IBAN = "DE02120300000000202051"


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


def _beleg(nummer: str, datum: date, netto: str, position: str) -> Beleg:
    b = Beleg(
        belegnummer=nummer,
        belegdatum=datum,
        netto=D(netto),
        datei_hash=nummer.encode().hex().ljust(64, "0")[:64],
        dateiname=f"{nummer}.pdf",
        kanal="upload",
        herkunft="test",
        aufbewahren_bis=date(2036, 12, 31),
    )
    b.positionen = [Belegposition(beleg_id=b.id, bezeichnung=position, netto=D(netto))]
    return b


def _geschaeftsjahr(make_session, config) -> None:
    """Eröffnung und laufendes Jahr 2026 — alles freigegeben, Bank abgestimmt."""
    versicherung = _beleg(
        "VS-2026-12",
        date(J, 12, 15),
        "1200",
        "Betriebshaftpflicht 01.01.2027-31.12.2027",
    )
    regal = _beleg("RE-2026-77", date(J, 9, 10), "3000", "Lagerregal")
    with make_session() as s:
        k = kontext(s, J, config)
        speichere_bankkonto(s, Bankkonto(iban=IBAN, bezeichnung="Giro"))
        erfasse_eroeffnung(s, J, "1200", D("20000"), "test", k.einstellungen)
        erfasse_eroeffnung(s, J, "1000", D("500"), "test", k.einstellungen)
        erfasse_eroeffnung(s, J, "0880", D("-20500"), "test", k.einstellungen)
        anfangsbestand(s, D("500"), date(J, 1, 1), k.kasse)
        speichere_beleg(s, versicherung)
        speichere_beleg(s, regal)
        s.commit()

    # Bank
    buche(
        make_session,
        date(J, 2, 15),
        "1200",
        "8400",
        "10000",
        "Erlös",
        steuer_schluessel=3,
        steuer_betrag=D("1900"),
    )
    buche(make_session, date(J, 3, 1), "4210", "1200", "1000", "Miete März")
    buche(
        make_session,
        date(J, 9, 10),
        "0420",
        "1200",
        "3000",
        "Lagerregal",
        steuer_schluessel=9,
        steuer_betrag=D("570"),
        beleg_id=regal.id,
    )
    buche(
        make_session,
        date(J, 12, 15),
        "4360",
        "1200",
        "1200",
        "Versicherung",
        beleg_id=versicherung.id,
    )
    buche(make_session, date(J, 6, 30), "1800", "1200", "2000", "Entnahme")
    buche(make_session, date(J, 10, 10), "1780", "1200", "500", "USt-VZ")

    with make_session() as s:
        k = kontext(s, J, config)
        # Kasse: Ausgabe und Bareinnahme, beide sofort kontiert
        buche_kasse(s, D("-24.90"), "Porto", k.kasse, date(J, 4, 2), None, "4910")
        buche_kasse(
            s, D("119"), "Barverkauf", k.kasse, date(J, 5, 3), None, "8400", D("19")
        )
        # Anlage aus dem Beleg, AfA-Lauf zum Jahresende, Freigabe
        lege_an(
            s,
            k.anlagen,
            beleg="RE-2026-77",
            konto="0420",
            nutzungsdauer=3,
            art=AfaArt.LINEAR,
        )
        afa = afa_lauf(s, J, k.anlagen)
        assert afa.summe == D("333.33")  # 3.000 × 4/36 (September: vier Monate)
        freigeben(s, J, "test")
        erfasse_kontoauszugssaldo(s, IBAN, date(J, 12, 31), D("23630"))
        s.commit()


def _config(tmp_path, gewinnermittlung):
    datei = tmp_path / f"{gewinnermittlung}.yaml"
    datei.write_text(
        f"abschluss:\n  gewinnermittlung: {gewinnermittlung}\n", encoding="utf-8"
    )
    return datei


ERWARTET = {
    "euer": {
        "ergebnis": D("8390.77"),
        "schluss": {
            "1200": D("23630"),
            "1000": D("594.10"),
            "0420": D("2666.67"),
            "0880": D("-26890.77"),
        },
    },
    "bilanz": {
        "ergebnis": D("8741.77"),
        "schluss": {
            "1200": D("23630"),
            "1000": D("594.10"),
            "0420": D("2666.67"),
            "0980": D("1200"),
            "1576": D("570"),
            "1776": D("-1919"),
            "1780": D("500"),
            "0880": D("-27241.77"),
        },
    },
}


@pytest.mark.parametrize("gewinnermittlung", ["euer", "bilanz"])
def test_durchlauf_geschaeftsjahr(make_session, tmp_path, gewinnermittlung):
    config = _config(tmp_path, gewinnermittlung)
    erwartet = ERWARTET[gewinnermittlung]
    _geschaeftsjahr(make_session, config)

    # Abschlussbuchungen: Abgrenzung nur bei Bilanz — vorgeschlagen, dann bestätigt
    with make_session() as s:
        k = kontext(s, J, config)
        lauf = schlage_abgrenzungen_vor(s, J, k.einstellungen, k.anlagen.rechtsstand())
        if gewinnermittlung == "bilanz":
            (v,) = lauf.vorschlaege
            assert (v.konto, v.rap_konto, v.betrag) == ("4360", "0980", D("1200"))
            assert pruefe_abschluss(k, nur=["abgrenzungen"])  # offen → Fehler
            bestaetige_abgrenzung(s, str(v.nr), "test")
        else:
            assert lauf.vorschlaege == []
        s.commit()

    with make_session() as s:
        k = kontext(s, J, config)
        befunde = pruefe_abschluss(k)
        assert [b for b in befunde if b.schwere is Schwere.FEHLER] == []
        susa = k.susa
        assert susa.summe_soll == susa.summe_haben
        assert susa.ergebnis == erwartet["ergebnis"]
        if gewinnermittlung == "euer":
            euer = erstelle_euer(susa, k.kontenrahmen)
            assert euer.gewinn - euer.summe_nicht_abziehbar == susa.ergebnis
            assert euer.zeile("130").betrag == D("333.33")  # AfA bewegliche WG
            assert euer.zeile("112").betrag == D("10100")
            assert euer.zeile("185").betrag == D("570")
            assert euer.entnahmen == D("2000")
        schluss = schlusssalden(s, J, k.einstellungen, k.kontenrahmen)
        assert schluss == erwartet["schluss"]
        vortrag = trage_vor(s, k, "E. Muster")
        s.commit()
    assert vortrag.ergebnis == erwartet["ergebnis"]

    with make_session() as s:
        k27 = kontext(s, J + 1, config)
        eb = eroeffnungssalden(s, J + 1, k27.kontenrahmen)
        assert eb == schluss  # exakt die Schlusssalden
        assert ist_gesperrt(s, J) and not ist_gesperrt(s, J + 1)
        # das Folgejahr rechnet auf den Eröffnungswerten weiter
        assert bestand(lade_kassenbuch(s), date(J + 1, 1, 1)) == eb["1000"]
        spiegel = anlagenspiegel(lade_anlagegueter(s), J + 1, k27.anlagen.rechtsstand())
        assert sum(g.rbw_beginn for g in spiegel.gruppen) == eb["0420"]
        assert afa_lauf(s, J + 1, k27.anlagen).summe == D("1000")
        freigeben(s, J + 1, "test")
        erfasse_kontoauszugssaldo(s, IBAN, date(J + 1, 12, 31), D("23630"))
        s.commit()
    with make_session() as s:
        k27 = kontext(s, J + 1, config)
        fehler = [b for b in pruefe_abschluss(k27) if b.schwere is Schwere.FEHLER]
        assert fehler == []  # Bank, Kasse, Anlagen, Vortragskonten stimmen 2027
