"""Ablauf freigeben → übermitteln → protokollieren (Akzeptanz 3 und 4)."""

from datetime import date, datetime

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import session_factory
from accounti.db.repo_elster import lade_freigaben, lade_uebermittlungen
from accounti.db.repository import speichere_buchung
from accounti.elster.datensatz import Absender, lies_kennzahlen, pruefe_datensatz
from accounti.elster.freigabe import FreigabeError, gib_frei
from accounti.elster.konfiguration import lade_elster
from accounti.elster.protokoll import pruefe_protokoll
from accounti.elster.uebermittlung import AttrappenUebermittler, UebermittlungError
from accounti.elster.ustva import (
    Kontext,
    bereite_vor,
    hat_testlauf,
    uebermittle,
)
from accounti.konfiguration import Buchhaltung
from accounti.models.elster import Meldeart, Modus
from accounti.steuer.zeitraum import Zeitraum
from tests.elster_hilfe import EricDoppel
from tests.test_cli_ustva import buchung, umgebung

AUGUST = Zeitraum.lies("2026-08")
JETZT = datetime(2026, 9, 7, 10, 30)
KONTEXT = Kontext(
    steuernummer="9181081508155",
    absender=Absender("Galerie Muster GmbH", "Kunstweg 1", "80331", "München"),
    hersteller_id="12345",
    produkt_name="accounti",
    produkt_version="0.1.0",
)


@pytest.fixture
def db(tmp_path):
    url, konfig = umgebung(tmp_path)
    engine, make_session = session_factory(url)
    yield make_session, lade_elster(konfig), BelegArchiv(tmp_path / "archiv")
    engine.dispose()


def vorbereiten(s, einstellungen):
    return bereite_vor(
        s, AUGUST, buchhaltung=Buchhaltung(), einstellungen=einstellungen
    )


def test_akzeptanz_3_testmodus_erzeugt_pruefbaren_datensatz_ohne_abgabe(db):
    make_session, einstellungen, archiv = db
    attrappe = AttrappenUebermittler()
    with make_session() as s:
        v = vorbereiten(s, einstellungen)
        u = uebermittle(
            s, v, modus=Modus.PRUEFUNG, kontext=KONTEXT, uebermittler=attrappe,
            archiv=archiv, jetzt=JETZT,
        )  # fmt: skip
        s.commit()
    assert attrappe.gesendet == []  # nichts abgegeben
    assert attrappe.geprueft == [u.datensatz]  # aber geprüft (mit ERiC: EBV-8)
    assert u.erfolgreich and u.modus is Modus.PRUEFUNG and u.weg == "attrappe"
    assert "<Testmerker>700000004</Testmerker>" in u.datensatz
    assert pruefe_datensatz(u.datensatz, testfall=True) == []
    assert lies_kennzahlen(u.datensatz)["Kz83"] == "2145.18"
    assert archiv.lese(u.datensatz_hash).decode() == u.datensatz
    assert u.freigabe_id is None  # Testmodus braucht keine Freigabe


def test_testmodus_ohne_eric_und_ohne_hersteller_id(db):
    make_session, einstellungen, archiv = db
    kontext = Kontext(**{**KONTEXT.__dict__, "hersteller_id": None})
    with make_session() as s:
        u = uebermittle(
            s, vorbereiten(s, einstellungen), modus=Modus.PRUEFUNG, kontext=kontext,
            uebermittler=None, archiv=archiv, jetzt=JETZT,
        )  # fmt: skip
    assert u.erfolgreich and u.weg == "intern"
    assert "<HerstellerID>74931</HerstellerID>" in u.datensatz
    assert "seit ERiC 39.4" in u.pruefbericht


def test_echt_nur_mit_freigabe(db):
    make_session, einstellungen, archiv = db
    attrappe = EricDoppel()
    with make_session() as s:
        v = vorbereiten(s, einstellungen)
        with pytest.raises(UebermittlungError, match="nicht freigegeben"):
            uebermittle(
                s, v, modus=Modus.ECHT, kontext=KONTEXT, uebermittler=attrappe,
                archiv=archiv,
            )  # fmt: skip
        assert lade_uebermittlungen(s) == []
    assert attrappe.gesendet == []


def test_freigabe_gesperrt_bei_fehlern(db):
    make_session, einstellungen, _ = db
    with make_session() as s:
        speichere_buchung(s, buchung("10001", "8200", "99.00"))
        v = vorbereiten(s, einstellungen)
        with pytest.raises(FreigabeError, match="8200"):
            gib_frei(s, v, "Erika Muster")
        with pytest.raises(FreigabeError, match="Wer"):
            gib_frei(s, vorbereiten(s, einstellungen), " ")
        assert lade_freigaben(s) == []


def _abgeben(s, einstellungen, archiv, attrappe, von="Erika Muster"):
    v = vorbereiten(s, einstellungen)
    gib_frei(s, v, von, jetzt=JETZT)
    s.commit()
    if not hat_testlauf(s, Meldeart.USTVA, attrappe.weg):
        _testlauf(s, einstellungen, archiv, attrappe)
    u = uebermittle(
        s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
        uebermittler=attrappe, archiv=archiv, jetzt=JETZT,
    )  # fmt: skip
    s.commit()
    return u


def test_akzeptanz_4_nach_uebermittlung_liegt_alles_unveraenderbar_vor(db):
    make_session, einstellungen, archiv = db
    attrappe = EricDoppel()
    with make_session() as s:
        u = _abgeben(s, einstellungen, archiv, attrappe)
    assert attrappe.gesendet == [u.datensatz]
    with make_session() as s:
        testlauf, gespeichert = lade_uebermittlungen(s)
        (freigabe,) = lade_freigaben(s)
    assert testlauf.modus is Modus.PRUEFUNG  # Testmodus beim ersten Lauf
    assert gespeichert == u
    assert gespeichert.modus is Modus.ECHT and gespeichert.erfolgreich
    assert gespeichert.ticket == "attrappe-0001"  # Ticket
    assert gespeichert.zeitpunkt == JETZT  # Zeitpunkt
    assert "<Testmerker>" not in gespeichert.datensatz  # Datensatz, Echtfall
    assert '"intern": []' in gespeichert.pruefbericht  # Prüfbericht
    assert "nichts wurde abgegeben" in gespeichert.server_antwort
    assert gespeichert.freigabe_id == freigabe.id
    assert gespeichert.freigegeben_von == "Erika Muster"
    assert str(gespeichert.betrag) == "2145.18"
    assert archiv.lese(gespeichert.protokoll_pdf_hash).startswith(b"%PDF")
    assert pruefe_protokoll([testlauf, gespeichert], archiv) == []


def test_freigabe_passt_nicht_mehr_nach_neuer_buchung(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        gib_frei(s, vorbereiten(s, einstellungen), "Erika Muster")
        speichere_buchung(s, buchung("10001", "8400", "100.00", 3, "19.00"))
        s.commit()
        with pytest.raises(UebermittlungError, match="geändert"):
            uebermittle(
                s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
                uebermittler=EricDoppel(), archiv=archiv,
            )  # fmt: skip


def test_neuer_fehler_nach_der_freigabe_sperrt_die_abgabe(db):
    """Akzeptanz 2 auch nach der Freigabe: Die Werte bleiben gleich (die Buchung ohne
    Steuerschlüssel zählt in keine Kennziffer), die Abgabe ist trotzdem gesperrt."""
    make_session, einstellungen, archiv = db
    attrappe = EricDoppel()
    with make_session() as s:
        gib_frei(s, vorbereiten(s, einstellungen), "Erika Muster")
        speichere_buchung(s, buchung("10001", "8200", "99.00", text="ohne BU"))
        s.commit()
        v = vorbereiten(s, einstellungen)
        assert v.gesperrt
        with pytest.raises(UebermittlungError, match="gesperrt.*8200"):
            uebermittle(
                s, v, modus=Modus.ECHT, kontext=KONTEXT, uebermittler=attrappe,
                archiv=archiv,
            )  # fmt: skip
        assert lade_uebermittlungen(s) == []
    assert attrappe.gesendet == []


def test_berichtigte_anmeldung_tritt_neben_die_alte(db):
    make_session, einstellungen, archiv = db
    attrappe = EricDoppel()
    with make_session() as s:
        erste = _abgeben(s, einstellungen, archiv, attrappe)
        speichere_buchung(s, buchung("10001", "8400", "100.00", 3, "19.00"))
        s.commit()
        v = vorbereiten(s, einstellungen)
        assert v.voranmeldung.berichtigt
        zweite = _abgeben(s, einstellungen, archiv, attrappe)
        alle = lade_uebermittlungen(s)
    assert [(x.nr, x.modus) for x in alle] == [
        (1, Modus.PRUEFUNG),
        (2, Modus.ECHT),
        (3, Modus.ECHT),
    ]
    assert not erste.berichtigt and zweite.berichtigt
    assert lies_kennzahlen(zweite.datensatz)["Kz10"] == "1"
    assert lies_kennzahlen(zweite.datensatz)["Kz83"] == "2164.18"
    assert lies_kennzahlen(erste.datensatz)["Kz83"] == "2145.18"
    assert pruefe_protokoll(alle, archiv) == []


def test_fehlschlag_wird_protokolliert_und_verbraucht_die_freigabe_nicht(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        gib_frei(s, vorbereiten(s, einstellungen), "Erika Muster")
        _testlauf(s, einstellungen, archiv, EricDoppel())
        u = uebermittle(
            s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
            uebermittler=EricDoppel(fehler="Zertifikat abgelaufen"),
            archiv=archiv,
        )  # fmt: skip
        s.commit()
        assert not u.erfolgreich and "Zertifikat abgelaufen" in u.ergebnis
        zweiter = uebermittle(
            s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
            uebermittler=EricDoppel(), archiv=archiv,
        )  # fmt: skip
        assert zweiter.erfolgreich and zweiter.freigabe_id == u.freigabe_id


def test_interne_pruefung_haelt_fehlerhaften_datensatz_zurueck(db):
    make_session, einstellungen, archiv = db
    kaputt = Kontext(**{**KONTEXT.__dict__, "steuernummer": "918108150815"})
    attrappe = AttrappenUebermittler()
    with make_session() as s:
        u = uebermittle(
            s, vorbereiten(s, einstellungen), modus=Modus.PRUEFUNG, kontext=kaputt,
            uebermittler=attrappe, archiv=archiv,
        )  # fmt: skip
    assert not u.erfolgreich and "Steuernummer" in u.ergebnis
    assert attrappe.geprueft == [] and attrappe.gesendet == []


def test_testfall_braucht_eigene_hersteller_id_und_uebermittler(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        v = vorbereiten(s, einstellungen)
        with pytest.raises(UebermittlungError, match="ERiC"):
            uebermittle(
                s, v, modus=Modus.TESTFALL, kontext=KONTEXT, uebermittler=None,
                archiv=archiv,
            )  # fmt: skip
        attrappe = AttrappenUebermittler()
        u = uebermittle(
            s, v, modus=Modus.TESTFALL, kontext=KONTEXT, uebermittler=attrappe,
            archiv=archiv, jetzt=datetime(2026, 9, 7),
        )  # fmt: skip
    assert u.erfolgreich and "<Testmerker>700000004" in attrappe.gesendet[0]
    assert u.aufbewahren_bis == date(2036, 12, 31)


# --- Attrappe nie „echt“, Testmodus beim ersten Lauf (Spec 5) -------------------------


def _testlauf(s, einstellungen, archiv, uebermittler):
    u = uebermittle(
        s, vorbereiten(s, einstellungen), modus=Modus.PRUEFUNG, kontext=KONTEXT,
        uebermittler=uebermittler, archiv=archiv, jetzt=JETZT,
    )  # fmt: skip
    s.commit()
    return u


def test_attrappe_gibt_nie_echt_ab(db):
    """Sonst stünde ein „echter“ Lauf im unveränderbaren Protokoll: Die erste
    wirkliche Abgabe ginge als berichtigte (Kz 10) raus, die Zahllast nur als
    Differenz."""
    make_session, einstellungen, archiv = db
    attrappe = AttrappenUebermittler()
    with make_session() as s:
        gib_frei(s, vorbereiten(s, einstellungen), "Erika Muster")
        _testlauf(s, einstellungen, archiv, attrappe)
        with pytest.raises(UebermittlungError, match="Attrappe"):
            uebermittle(
                s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
                uebermittler=attrappe, archiv=archiv,
            )  # fmt: skip
        assert [u.modus for u in lade_uebermittlungen(s)] == [Modus.PRUEFUNG]
    assert attrappe.gesendet == []


def test_echte_abgabe_erst_nach_einem_testlauf_auf_demselben_weg(db):
    make_session, einstellungen, archiv = db
    eric = EricDoppel()
    with make_session() as s:
        gib_frei(s, vorbereiten(s, einstellungen), "Erika Muster")
        s.commit()

        def echt():
            return uebermittle(
                s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
                uebermittler=eric, archiv=archiv, jetzt=JETZT,
            )  # fmt: skip

        with pytest.raises(UebermittlungError, match="Testmodus"):
            echt()
        _testlauf(s, einstellungen, archiv, None)  # nur intern: zählt nicht
        _testlauf(s, einstellungen, archiv, AttrappenUebermittler())  # anderer Weg
        with pytest.raises(UebermittlungError, match="Testmodus"):
            echt()
        _testlauf(s, einstellungen, archiv, eric)
        u = echt()
    assert u.erfolgreich and u.modus is Modus.ECHT and not u.berichtigt
    assert eric.gesendet == [u.datensatz]


class _Abbruch(EricDoppel):
    """Sendet — und stürzt danach mit einem unerwarteten Fehler ab."""

    def sende(self, xml, datenart_version):
        super().sende(xml, datenart_version)
        raise OSError("Verbindung nach dem Versand abgebrochen")


def test_unerwarteter_fehler_beim_senden_wird_als_ungewiss_protokolliert(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        gib_frei(s, vorbereiten(s, einstellungen), "Erika Muster")
        _testlauf(s, einstellungen, archiv, EricDoppel())
        u = uebermittle(
            s, vorbereiten(s, einstellungen), modus=Modus.ECHT, kontext=KONTEXT,
            uebermittler=_Abbruch(), archiv=archiv, jetzt=JETZT,
        )  # fmt: skip
        s.commit()
        alle = lade_uebermittlungen(s)
    assert not u.erfolgreich and "ungewiss" in u.ergebnis
    assert "Verbindung nach dem Versand abgebrochen" in u.ergebnis
    assert [x.modus for x in alle] == [Modus.PRUEFUNG, Modus.ECHT]


def test_eu_leistung_ueber_die_bank_findet_den_leistenden_am_beleg(db):
    """Werbe- und SaaS-Rechnungen aus dem EU-Ausland, direkt über die Bank bezahlt:
    Der Leistende steht nur am Beleg (Beleg.kontakt_id), nicht im offenen Posten."""
    from decimal import Decimal

    from accounti.db.repository import speichere_beleg, speichere_kontakt
    from accounti.models import Beleg, Kontakt

    make_session, einstellungen, _ = db
    google = Kontakt(name="Google Ireland", land="IE", kreditor_konto="70010")
    beleg = Beleg(
        kontakt_id=google.id, datei_hash="g" * 64, dateiname="google.pdf",
        kanal="ordner", herkunft="Test", aufbewahren_bis=date(2036, 12, 31),
    )  # fmt: skip
    with make_session() as s:
        speichere_kontakt(s, google)
        speichere_beleg(s, beleg)
        speichere_buchung(
            s, buchung("4600", "1200", "1000.00", 94, "190.00", beleg_id=beleg.id)
        )
        s.commit()
        v = vorbereiten(s, einstellungen)
    assert v.voranmeldung.wert(46) == Decimal("1800.00")  # 800 Agentur Wien + 1000
    assert v.voranmeldung.wert(84) == 0
    assert not any("Leistender unbekannt" in b.text for b in v.befunde)
