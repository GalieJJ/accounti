"""Ablauf freigeben → übermitteln → protokollieren (Akzeptanz 3 und 4)."""

from datetime import date, datetime

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import session_factory
from accounti.db.repo_elster import lade_freigaben, lade_uebermittlungen
from accounti.db.repository import lade_buchungen, speichere_buchung
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


# --- Gesamttest Steuer B5, B10, Eingang B13 ------------------------------------------


def test_korrektur_nach_abgabe_abgegeben_abweichend(db):
    """Steuer B5: nach der Abgabe ändert ein Storno den Monat — ``ustva`` sagt, dass
    die abgegebene Anmeldung nicht mehr passt (§ 153 Abs. 1 AO)."""
    from accounti.pruefung.storno import storniere

    make_session, einstellungen, archiv = db
    with make_session() as s:
        _abgeben(s, einstellungen, archiv, EricDoppel())
        v = vorbereiten(s, einstellungen)
        assert not [b for b in v.befunde if b.regel == "abgegeben_abweichend"]
        ziel = next(
            b
            for b in lade_buchungen(s)
            if b.haben_konto == "8400" and b.storniert_durch is None
        )
        k = storniere(s, str(ziel.id)[:8], grund="Fehlbuchung", von="Erika")
        s.commit()
        (warnung,) = [w for w in k.warnungen if "schon abgegeben" in w]
        assert "08/2026" in warnung or "August 2026" in warnung
        v = vorbereiten(s, einstellungen)
    (befund,) = [b for b in v.befunde if b.regel == "abgegeben_abweichend"]
    assert befund.schweregrad.value == "warnung"
    assert "Kz 83 2.145,18 €" in befund.text and "83" in befund.text
    # das Storno eines Erlöses senkt die Zahllast — keine Pflicht (Nachprüfung 6 E,
    # merge: der Text berief sich trotzdem auf die Pflicht nach § 153 Abs. 1 AO)
    assert "keine Pflicht nach § 153 Abs. 1 AO" in befund.text, befund.text


def test_abgegeben_abweichend_pflicht_nur_wenn_die_zahllast_steigt(db):
    """Nachprüfung 6 E (merge): eine nach der Abgabe gebuchte Ausgangsrechnung
    erhöht die Zahllast — dann ist die berichtigte Voranmeldung Pflicht (§ 153 Abs. 1
    AO: die Erklärung führt zu einer Verkürzung)."""
    make_session, einstellungen, archiv = db
    with make_session() as s:
        _abgeben(s, einstellungen, archiv, EricDoppel())
        speichere_buchung(s, buchung("10001", "8400", "100.00", 3, "19.00"))
        s.commit()
        v = vorbereiten(s, einstellungen)
    (befund,) = [b for b in v.befunde if b.regel == "abgegeben_abweichend"]
    assert "Pflicht nach § 153 Abs. 1 AO" in befund.text, befund.text
    assert "keine Pflicht" not in befund.text


def test_storno_in_anderem_monat_verlangt_keine_berichtigung_des_originals(db):
    """Nachprüfung N4: Storno am 02.10. zu einer Buchung aus dem abgegebenen August.
    accounti zählt das Storno im Oktober, ``ustva 2026-08`` bleibt unverändert — die
    Warnung „berichtigte Voranmeldung 08 abgeben“ widersprach dem § 17-Hinweis
    daneben. Es bleibt der Hinweis, der beide Fälle unterscheidet."""
    from datetime import date

    from accounti.pruefung.storno import storniere

    make_session, einstellungen, archiv = db
    with make_session() as s:
        _abgeben(s, einstellungen, archiv, EricDoppel())
        ziel = next(
            b
            for b in lade_buchungen(s)
            if b.haben_konto == "8400" and b.storniert_durch is None
        )
        k = storniere(
            s, str(ziel.id)[:8], grund="Rabatt", von="Erika", datum=date(2026, 10, 2)
        )
        s.commit()
        assert not [w for w in k.warnungen if "schon abgegeben" in w], k.warnungen
        (hinweis,) = k.warnungen
        assert "§ 17 Abs. 1 S. 7 UStG" in hinweis and "10/2026" in hinweis
        assert "periode oeffnen 2026-08" in hinweis
        v = vorbereiten(s, einstellungen)
    assert not [b for b in v.befunde if b.regel == "abgegeben_abweichend"]


def test_ohne_abgabe_kein_befund_und_kein_veralteter_hinweis(db):
    """Eingang B13 / Ausgang: der Hinweis „Baustein 7 nicht angeschlossen“ ist weg."""
    make_session, einstellungen, _ = db
    with make_session() as s:
        v = vorbereiten(s, einstellungen)
    texte = " ".join(b.text for b in v.befunde)
    assert "nicht angeschlossen" not in texte
    assert not [b for b in v.befunde if b.regel == "abgegeben_abweichend"]


def test_pruefregeln_laufen_mit(db, tmp_path):
    """Mit der Konfiguration laufen die Prüfregeln (Baustein 7) über den Zeitraum."""
    make_session, einstellungen, _ = db
    konfig = tmp_path / "leer.yaml"
    konfig.write_text("", encoding="utf-8")
    with make_session() as s:
        speichere_buchung(
            s, buchung("4900", "1200", "100.00", 9, "19.00", text="ohne Beleg")
        )
        s.commit()
        v = bereite_vor(
            s,
            AUGUST,
            buchhaltung=Buchhaltung(),
            einstellungen=einstellungen,
            konfiguration=konfig,
        )
    pruefung = [b for b in v.befunde if b.regel == "pruefung"]
    assert pruefung and all(b.schweregrad.value != "fehler" for b in pruefung)
    assert any("accounti pruefen --period 2026-08" in b.text for b in pruefung)


def test_laufender_zeitraum_fehler_im_test_warnung(db):
    """Steuer B10: § 18 Abs. 1 UStG — abgegeben wird nach Ablauf des Zeitraums."""
    make_session, einstellungen, _ = db
    with make_session() as s:
        v = bereite_vor(
            s,
            AUGUST,
            buchhaltung=Buchhaltung(),
            einstellungen=einstellungen,
            heute=date(2026, 8, 31),
        )
        (b,) = [x for x in v.befunde if x.regel == "zeitraum_laufend"]
        assert b.schweregrad.value == "fehler" and v.gesperrt
        assert "31.08.2026" in b.text
        with pytest.raises(FreigabeError, match="nicht abgelaufen"):
            gib_frei(s, v, "Erika")
        test = bereite_vor(
            s,
            AUGUST,
            buchhaltung=Buchhaltung(),
            einstellungen=einstellungen,
            heute=date(2026, 8, 31),
            test=True,
        )
        (b,) = [x for x in test.befunde if x.regel == "zeitraum_laufend"]
        assert b.schweregrad.value == "warnung"
        abgelaufen = bereite_vor(
            s,
            AUGUST,
            buchhaltung=Buchhaltung(),
            einstellungen=einstellungen,
            heute=date(2026, 9, 1),
        )
        assert not [x for x in abgelaufen.befunde if x.regel == "zeitraum_laufend"]


def test_saldenvortrag_ist_kein_umsatz(db):
    """Eingang B13: EB-Buchung 1576 an 9000 — keine Warnung „Steuerkonto ohne
    Kennziffer“, keine Kennziffer."""
    make_session, einstellungen, _ = db
    with make_session() as s:
        vorher = vorbereiten(s, einstellungen).voranmeldung.formularwerte()
        speichere_buchung(
            s,
            buchung(
                "1576", "9000", "250.00", text="EB Vorsteuer", datum=date(2026, 8, 1)
            ),
        )
        s.commit()
        v = vorbereiten(s, einstellungen)
    assert not [b for b in v.befunde if "1576" in b.text]
    assert v.voranmeldung.formularwerte() == vorher


def test_dezember_2026_monat_trotz_quartal_2027():
    """AK31 (dritter Punkt): ``voranmeldungszeitraum: {2026: monat, 2027: quartal}`` —
    die Voranmeldung Dezember 2026 ist monatlich und bleibt es, 2027 vierteljährlich;
    die Sondervorauszahlung gehört zum Dezember 2026, solange 2026 Dauerfrist gilt."""
    from accounti.elster.konfiguration import ElsterEinstellungen
    from accounti.elster.ustva import _zeitraum_befunde

    einst = ElsterEinstellungen(
        voranmeldungszeitraum={2026: "monat", 2027: "quartal"},
        dauerfristverlaengerung={2026: True, 2027: False},
    )
    heute = date(2028, 1, 1)

    def fehler(text: str) -> list[str]:
        return [b.text for b in _zeitraum_befunde(Zeitraum.lies(text), einst, heute)]

    assert fehler("2026-12") == []
    assert fehler("2027-Q1") == []
    assert any("kein Voranmeldungszeitraum" in t for t in fehler("2027-01"))
    assert any("kein Voranmeldungszeitraum" in t for t in fehler("2026-Q4"))
    assert einst.dauerfrist_fuer(2026) and not einst.dauerfrist_fuer(2027)


AK31_EINST = {
    "voranmeldungszeitraum": {2026: "monat", 2027: "quartal"},
    "dauerfristverlaengerung": {2026: True, 2027: False},
}


def _ak31_uebermittlung(art, zeitraum):
    from accounti.models.elster import Uebermittlung

    return Uebermittlung(
        art=art, zeitraum=zeitraum, modus=Modus.ECHT, weg="eric", datensatz="<x/>",
        datensatz_hash="h", erfolgreich=True, ergebnis="", pruefbericht="{}",
        aufbewahren_bis=date(2037, 12, 31),
    )  # fmt: skip


def test_dezember_2026_kz39_und_faelligkeit_trotz_quartal_2027(tmp_path):
    """AK31 bei den Verbrauchern: Die Voranmeldung Dezember 2026 (erstellt im Januar
    2027) rechnet die angemeldete Sondervorauszahlung 2026 an (Kz 39), ihre Zahllast
    ist mit der Dauerfrist 2026 am 10.02.2027 fällig; 2027-Q1 ohne Dauerfrist am
    10.04.2027 (ein Samstag, also Montag, 12.04.2027 — § 108 Abs. 3 AO); für 2027
    (Quartal) gibt es keine Sondervorauszahlung."""
    from decimal import Decimal

    from accounti.db import init_db
    from accounti.elster.dauerfrist import berechne_svz
    from accounti.elster.konfiguration import ElsterEinstellungen
    from accounti.elster.protokoll import neuer_eintrag, protokolliere
    from accounti.elster.zahllast import _faellig

    einst = ElsterEinstellungen(**AK31_EINST)
    engine, make_session = session_factory(f"sqlite:///{tmp_path / 'ak31.db'}")
    init_db(engine)
    with make_session() as s:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.DAUERFRIST, zeitraum="2026", modus=Modus.ECHT,
                weg="eric", datensatz="<x/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=Decimal("4000.00"),
            ),
        )  # fmt: skip
        s.commit()
        dezember = bereite_vor(
            s, Zeitraum.lies("2026-12"), buchhaltung=Buchhaltung(), einstellungen=einst
        )
        svz_2027 = berechne_svz(
            s, 2027, einst, summe_vorjahr=Decimal("12000"), svz_vorjahr=Decimal("0")
        )
    engine.dispose()
    assert dezember.voranmeldung.formularwerte()[39] == Decimal("4000.00")
    assert dezember.voranmeldung.kz83 == Decimal("-4000.00")
    assert "sondervorauszahlung" not in [b.regel for b in dezember.befunde]
    assert svz_2027.betrag is None
    ustva = Meldeart.USTVA
    assert _faellig(_ak31_uebermittlung(ustva, "2026-12"), einst) == date(2027, 2, 10)
    assert _faellig(_ak31_uebermittlung(ustva, "2027-Q1"), einst) == date(2027, 4, 12)
