"""Nachforderung (Spec 4.2, Akzeptanz 4): aus dem Befund wird eine Aufgabe, die
verstummt, sobald der Beleg eintrifft."""

from datetime import date, timedelta

import pytest

from accounti.aufgaben import (
    AufgabenEinstellungen,
    AufgabenStatus,
    Objekt,
    aufgaben_zu,
    kommentare_zu,
    stelle_zusammen,
)
from accounti.aufgaben.anbindung import lade_anbindungen
from accounti.aufgaben.prueflaeufe import PRUEFLAEUFE, fuehre_prueflaeufe_aus
from accounti.bank.abgleichslauf import gleiche_belege_ab
from accounti.konfiguration import Buchhaltung
from accounti.models import Belegart
from accounti.pruefung.einstellungen import PruefEinstellungen
from accounti.pruefung.journal import lade_journal
from accounti.pruefung.nachforderung import (
    BelegFehltNachRegel,
    NachforderungError,
    baue_anfrage,
    mit_pruefeinstellungen,
    sende_anfrage,
)
from accounti.pruefung.regeln import Kontext, fuehre_regeln_aus
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    kontakt,
    make_session_fixture,
    umsatz,
)

TAG = date(2026, 8, 12)
STICHTAG = date(2026, 10, 20)


def _nachfordern(make_session, einstellungen=None, stichtag=STICHTAG):
    with (
        make_session() as s,
        mit_pruefeinstellungen(einstellungen or PruefEinstellungen()),
    ):
        (lauf,) = fuehre_prueflaeufe_aus(
            s, AufgabenEinstellungen(), stichtag=stichtag, namen=["beleg_fehlt"]
        )
        s.commit()
    return lauf.abgleich


def _befunde(make_session, einstellungen=None):
    with make_session() as s:
        k = Kontext(s, einstellungen or PruefEinstellungen(), Buchhaltung(), STICHTAG)
        return fuehre_regeln_aus(k, ["umsatz_ohne_beleg"]).befunde


def test_baustein_7_uebernimmt_den_lauf_beleg_fehlt():
    lade_anbindungen()
    assert isinstance(PRUEFLAEUFE["beleg_fehlt"], BelegFehltNachRegel)


def test_akzeptanz_4_aufgabe_verstummt_wenn_der_beleg_eintrifft(make_session):
    tx = umsatz("-59.50", tag=TAG, zweck="KARTENZAHLUNG SHELL", name="Shell Kiel")
    anlegen(make_session, tx)
    (befund,) = _befunde(make_session)
    assert befund.objekt_id == str(tx.id)

    abgleich = _nachfordern(make_session)
    (aufgabe,) = abgleich.neu
    assert aufgabe.objekt == Objekt("transaktion", tx.id)
    assert aufgabe.merkmale["befund"] == "umsatz_ohne_beleg"
    assert aufgabe.merkmale["gegenpartei"] == "Shell Kiel"
    assert "-59,50 €" in aufgabe.titel and "Shell Kiel" in aufgabe.titel
    # Erinnerung: die Aufgabe steht in der Tagesübersicht
    with make_session() as s:
        uebersichten = stelle_zusammen(s, AufgabenEinstellungen(), STICHTAG)
    assert any(aufgabe.nr in u.nummern for u in uebersichten)

    # der Beleg trifft ein und der Abgleich greift
    quittung = beleg(
        belegart=Belegart.QUITTUNG,
        nummer=None,
        tag=TAG,
        lieferant="Shell Kiel",
        netto=None,
        steuer=None,
        brutto="59.50",
        positionen=[],
    )
    anlegen(make_session, quittung)
    with make_session() as s:
        assert len(gleiche_belege_ab(s).automatisch) == 1
        s.commit()
    assert _befunde(make_session) == []
    abgleich = _nachfordern(make_session)
    (geschlossen,) = abgleich.hinfaellig
    assert geschlossen.id == aufgabe.id
    with make_session() as s:
        (zu,) = aufgaben_zu(s, Objekt("transaktion", tx.id))
        assert zu.status is AufgabenStatus.HINFAELLIG
        assert "Beleg zugeordnet" in (zu.abschluss_grund or "")
        # verstummt: keine Erinnerung mehr, auch später nicht
        spaeter = stelle_zusammen(
            s, AufgabenEinstellungen(), STICHTAG + timedelta(days=30)
        )
    assert not any(aufgabe.nr in u.nummern for u in spaeter)


def test_belegfrei_nach_regel_schliesst_mit_grund(make_session):
    gebuehr = umsatz("-5.90", tag=TAG, zweck="Kontoführung 08/2026", name="Bank")
    anlegen(make_session, gebuehr)
    assert len(_nachfordern(make_session).neu) == 1  # ohne Regel wie bisher
    e = PruefEinstellungen.model_validate(
        {
            "belegfrei": [
                {
                    "name": "kontofuehrung",
                    "muster": "kontoführung",
                    "begruendung": "Bankentgelt — der Kontoauszug ist der Beleg",
                }
            ]
        }
    )
    (zu,) = _nachfordern(make_session, e).hinfaellig
    assert "belegfrei nach Regel kontofuehrung" in (zu.abschluss_grund or "")
    assert _befunde(make_session, e) == []


def test_schwellen_der_regel(make_session):
    klein = umsatz("-3.00", tag=TAG)
    jung = umsatz("-80.00", tag=STICHTAG - timedelta(days=2))
    gross = umsatz("-80.00", tag=TAG)
    anlegen(make_session, klein, jung, gross)
    assert len(_nachfordern(make_session).neu) == 3
    e = PruefEinstellungen.model_validate(
        {"regeln": {"umsatz_ohne_beleg": {"ab_betrag": 5, "nach_tagen": 10}}}
    )
    abgleich = _nachfordern(make_session, e)
    # unter der Schwelle: hinfällig; zu jung: bleibt, wie es ist (ausgenommen)
    assert [a.objekt.id for a in abgleich.hinfaellig] == [str(klein.id)]
    with make_session() as s:
        (a,) = aufgaben_zu(s, Objekt("transaktion", jung.id))
    assert a.status is AufgabenStatus.OFFEN


class _Postfach:
    name = "attrappe"

    def __init__(self):
        self.gesendet = []

    def sende(self, nachricht):
        self.gesendet.append(nachricht)


def test_anfrage_entwurf_und_versand_nur_auf_befehl(make_session):
    lieferant = kontakt(
        name="Shell Kiel GmbH",
        iban="DE02120300000000202051",
        email="beleg@shell.example",
    )
    tx = umsatz(
        "-59.50",
        tag=TAG,
        name="Shell Kiel GmbH",
        gegenkonto_iban="DE02120300000000202051",
    )
    anlegen(make_session, lieferant, tx)
    _nachfordern(make_session)
    e = PruefEinstellungen()
    with make_session() as s:
        entwurf = baue_anfrage(
            s, str(tx.id)[:8], e, "Galerie Muster GmbH", "b@g.example"
        )
    assert entwurf.an == "beleg@shell.example"
    assert "12.08.2026" in entwurf.betreff and "59,50" in entwurf.betreff
    assert "Galerie Muster GmbH" in entwurf.text and "b@g.example" in entwurf.text
    postfach = _Postfach()
    with make_session() as s:
        sende_anfrage(s, entwurf, postfach, "Galerie <b@g.example>", "jan")
        s.commit()
        objekt = Objekt("transaktion", tx.id)
        kommentare = kommentare_zu(s, objekt)
        journal = lade_journal(s, vorgang="beleg_angefordert")
    (nachricht,) = postfach.gesendet
    assert nachricht["To"] == "beleg@shell.example"
    assert any("Beleg angefordert" in k.text for k in kommentare)
    assert len(journal) == 1 and journal[0].person == "jan"


def test_anfrage_ohne_empfaenger(make_session):
    tx = umsatz(tag=TAG)
    anlegen(make_session, tx)
    with make_session() as s:
        entwurf = baue_anfrage(s, str(tx.id), PruefEinstellungen(), "Firma")
        # Schlussprüfung N-6: ohne antwort_an kein „… an uns.“
        assert "an uns." not in entwurf.text
        assert "an die Absenderadresse dieser E-Mail" in entwurf.text
        assert entwurf.an is None
        postfach = _Postfach()
        with pytest.raises(NachforderungError, match="Kein Empfänger"):
            sende_anfrage(s, entwurf, postfach, "a@b.example", "jan")
    assert postfach.gesendet == []


def test_falscher_platzhalter_in_der_vorlage(make_session):
    tx = umsatz(tag=TAG)
    anlegen(make_session, tx)
    e = PruefEinstellungen.model_validate({"nachforderung": {"betreff": "{rechnung}"}})
    with make_session() as s, pytest.raises(NachforderungError, match="Platzhalter"):
        baue_anfrage(s, str(tx.id), e, "Firma")


def test_beleg_ueber_die_buchung_zugeordnet(make_session):
    """Schlussprüfung N-4: Ein Umsatz, dessen Buchung den Beleg trägt (z.B. die
    Sammelbelastung einer Kreditkarte gegen die Abrechnung), braucht keine
    Nachforderung — auch ohne Belegabgleich. Eine offene Aufgabe wird hinfällig."""
    from accounti.models import BuchungStatus
    from tests.pruefung_hilfe import buchung

    tx = umsatz("-250.00", tag=TAG, zweck="KREDITKARTE ABRECHNUNG 08", name="Visa")
    anlegen(make_session, tx)
    (aufgabe,) = _nachfordern(make_session).neu
    abrechnung = beleg(tag=TAG, nummer="KK-08", brutto="250.00", positionen=[])
    anlegen(
        make_session,
        abrechnung,
        buchung(
            tx,
            status=BuchungStatus.GEPRUEFT,
            soll="1361",
            steuer=None,
            schluessel=None,
            netto="250.00",
            beleg_id=abrechnung.id,
        ),
    )
    abgleich = _nachfordern(make_session)
    assert abgleich.neu == []
    (zu,) = abgleich.hinfaellig
    assert zu.id == aufgabe.id
    assert "Beleg über die Buchung zugeordnet" in (zu.abschluss_grund or "")
