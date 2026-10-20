"""Prüfstufe: blockiert, mit Begründung — nie nur eine Warnung."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from accounti.db.repo_zahlung import lade_lauf, lade_protokoll
from accounti.db.repository import (
    aktualisiere_kontakt,
    aktualisiere_posten,
    lade_kontakt,
)
from accounti.models import KontaktStatus, PostenStatus
from accounti.models.zahlung import LaufStatus
from accounti.zahlung.freigabe import (
    LaufError,
    LaufGesperrtError,
    freigeben,
    iban_klaeren,
    lege_an,
    setze_sperre,
)
from accounti.zahlung.iban import lesbar
from accounti.zahlung.konfiguration import Auftraggeber, ZahlungEinstellungen
from accounti.zahlung.pruefung import pruefe_lauf
from accounti.zahlung.vorschlag import lade_vorschlag
from tests.zahlung_hilfe import (
    IBAN_BETRUG,
    IBAN_EIGEN,
    IBAN_MUELLER,
    STICHTAG,
    beleg_zu,
    kreditor,
    neue_db,
    posten,
    speichere,
    zahlung_vorschlagen,
)

E = ZahlungEinstellungen(
    auftraggeber=Auftraggeber(name="Galerie Muster GmbH", iban=IBAN_EIGEN)
)


def _lauf(kontakt=None, beleg_iban=IBAN_MUELLER, e=E, waehrung="EUR", **kw):
    """Datenbank mit einem Posten und einem Lauf (Nr. 1) im Entwurf."""
    fabrik = neue_db()
    k = kontakt or kreditor()
    p = posten(k, faellig=date(2026, 10, 19), **kw)
    speichere(fabrik, [k], [p], [beleg_zu(p, beleg_iban, waehrung)])
    with fabrik() as s:
        lauf = lege_an(s, lade_vorschlag(s, STICHTAG, e), e, "erika")
        s.commit()
    return fabrik, lauf, k, p


def _befunde(fabrik, e=E, heute=STICHTAG):
    with fabrik() as s:
        return pruefe_lauf(s, lade_lauf(s, 1), e, heute)


def test_sauberer_lauf_hat_keine_befunde():
    fabrik, *_ = _lauf()
    ergebnis = _befunde(fabrik)
    assert ergebnis.ok and ergebnis.befunde == []


def test_abweichende_iban_auf_der_rechnung_blockiert_mit_klarer_meldung():
    """Akzeptanz 4: genau so funktionieren gefälschte Rechnungen."""
    fabrik, lauf, *_ = _lauf(beleg_iban=IBAN_BETRUG)
    ergebnis = _befunde(fabrik)
    assert not ergebnis.ok
    (befund,) = ergebnis.befunde
    assert befund.nr == 1
    assert befund.text == (
        "IBAN-Abweichung: Rechnung RE-2026-0042 von Bürobedarf Müller GmbH nennt "
        "DE75 5121 0800 1245 1261 99, im Stammsatz steht DE89 3704 0044 0532 0130 00. "
        "Nicht zahlen, bevor die Bankverbindung beim Lieferanten auf bekanntem Weg "
        "bestätigt ist (bekannte Telefonnummer, nicht die aus Rechnung oder E-Mail) — "
        "dann Stammsatz ändern (accounti kontakte bearbeiten 70001 --iban …) oder die "
        "Abweichung klären (accounti zahlung iban-klaeren 1 1 --grund …)."
    )
    # der ganze Lauf steht: keine Freigabe
    with fabrik() as s:
        with pytest.raises(LaufGesperrtError) as fehler:
            freigeben(s, 1, "erika", E, heute=STICHTAG)
        assert "Lauf 1 ist gesperrt" in str(fehler.value)
        assert "IBAN-Abweichung" in str(fehler.value)
    with fabrik() as s:
        assert lade_lauf(s, 1).status is LaufStatus.ENTWURF


def test_iban_klaerung_zahlt_an_den_stammsatz():
    fabrik, lauf, _, p = _lauf(beleg_iban=IBAN_BETRUG)
    with fabrik() as s:
        with pytest.raises(LaufError, match="Grund"):
            iban_klaeren(s, 1, 1, "erika", "")
        k = iban_klaeren(
            s, 1, 1, "erika", "Rückruf bei Müller (Tel. aus Stammsatz): IBAN alt gilt"
        )
        s.commit()
    assert (k.posten_id, k.rechnungs_iban, k.stammsatz_iban) == (
        p.id,
        IBAN_BETRUG,
        IBAN_MUELLER,
    )
    assert _befunde(fabrik).ok
    with fabrik() as s:
        frei = freigeben(s, 1, "erika", E, heute=STICHTAG)
        s.commit()
        assert frei.zahlungen[0].iban == IBAN_MUELLER
        assert "IBAN-Abweichung geklärt" in lade_protokoll(s, frei.id)[1].text


def test_stammsatz_nach_anlage_geaendert_blockiert():
    fabrik, *_ = _lauf()
    with fabrik() as s:
        k = lade_kontakt(s, "70001")
        aktualisiere_kontakt(s, k.model_copy(update={"iban": IBAN_BETRUG}))
        s.commit()
    texte = [b.text for b in _befunde(fabrik).befunde]
    assert (
        "IBAN der Zahlung DE89 3704 0044 0532 0130 00 weicht vom Stammsatz "
        "DE75 5121 0800 1245 1261 99 ab — Zahlung entfernen oder Lauf stornieren und "
        "neu anlegen" in texte
    )


@pytest.mark.parametrize(
    ("iban", "erwartet"),
    [
        (None, "Bürobedarf Müller GmbH hat keine IBAN im Stammsatz"),
        (
            "DE00370400440532013000",
            "IBAN DE00 3704 0044 0532 0130 00 im Stammsatz ist ungültig (Prüfziffer)",
        ),
        (
            "TR330006100519786457841326",
            "IBAN TR33 0006 1005 1978 6457 8413 26 liegt nicht im SEPA-Raum (TR)",
        ),
    ],
)
def test_iban_im_stammsatz_fehlt_ungueltig_oder_ausserhalb_sepa(iban, erwartet):
    fabrik, *_ = _lauf(kreditor(iban=iban), beleg_iban=None)
    assert erwartet in [b.text for b in _befunde(fabrik).befunde]


def test_gesperrter_oder_unbestaetigter_kontakt_blockiert():
    fabrik, *_ = _lauf(kreditor(status=KontaktStatus.ZUR_PRUEFUNG))
    with fabrik() as s:
        setze_sperre(s, "70001", "Ware mangelhaft", "jan")
        s.commit()
    assert [b.text for b in _befunde(fabrik).befunde] == [
        "Bürobedarf Müller GmbH ist noch zur Prüfung (automatisch angelegt) — "
        "erst prüfen und mit 'accounti kontakte bestaetigen 70001' freigeben",
        "Zahlungssperre für Bürobedarf Müller GmbH: Ware mangelhaft (jan)",
    ]


def test_posten_geaendert_oder_bezahlt_blockiert():
    fabrik, lauf, _, p = _lauf()
    with fabrik() as s:
        aktualisiere_posten(s, p.id, Decimal("190.00"), PostenStatus.TEILBEZAHLT)
        s.commit()
    assert [b.text for b in _befunde(fabrik).befunde] == [
        "Posten RE-2026-0042 hat sich seit der Anlage geändert (Rest jetzt 190,00 € "
        "statt 1.190,00 €) — Zahlung entfernen oder Lauf neu anlegen"
    ]
    with fabrik() as s:
        aktualisiere_posten(s, p.id, Decimal("0.00"), PostenStatus.AUSGEGLICHEN)
        s.commit()
    assert "Posten RE-2026-0042 ist bereits ausgeglichen" in [
        b.text for b in _befunde(fabrik).befunde
    ]


def test_skontofrist_vor_der_ausfuehrung_abgelaufen():
    fabrik = neue_db()
    k = kreditor()
    p = posten(
        k,
        faellig=date(2026, 11, 15),
        skonto_bis=date(2026, 10, 21),
        skonto_prozent="2",
    )
    speichere(fabrik, [k], [p])
    with fabrik() as s:
        lege_an(
            s,
            lade_vorschlag(s, STICHTAG, E),
            E,
            "erika",
            ausfuehrung=date(2026, 10, 23),
        )
        s.commit()
    assert [b.text for b in _befunde(fabrik).befunde] == [
        "Skonto 23,80 € nur bis 21.10.2026, Ausführung erst am 23.10.2026 — "
        "Ausführungstag vorziehen oder ohne Skonto neu anlegen"
    ]


def test_betrag_grenzen_waehrung_und_datum():
    e = E.model_copy(update={"hoechstbetrag_zahlung": Decimal("1000")})
    fabrik, *_ = _lauf(e=e, waehrung="USD")
    texte = [b.text for b in _befunde(fabrik, e, heute=date(2026, 10, 21)).befunde]
    assert texte == [
        "Ausführungstag 20.10.2026 liegt in der Vergangenheit — Lauf stornieren und "
        "neu anlegen",
        "Betrag 1.190,00 € über der Grenze je Zahlung von 1.000,00 € "
        "(zahlung.hoechstbetrag_zahlung)",
        "Rechnung RE-2026-0042 lautet auf USD — SEPA-Überweisungen nur in EUR",
    ]


def test_auftraggeber_ohne_gueltige_iban():
    fabrik, *_ = _lauf()
    with fabrik() as s:
        s.execute(text("UPDATE zahlungslaeufe SET auftraggeber_iban = 'DE00'"))
        s.commit()
    assert _befunde(fabrik).befunde[0].text == (
        "Auftraggeber-IBAN DE00 ist ungültig — zahlung.auftraggeber oder mandant.bank "
        "in der Konfiguration prüfen"
    )


def test_doppelter_posten_wird_auch_an_der_sperre_vorbei_erkannt():
    fabrik, lauf, k, p = _lauf()
    lauf2 = uuid4()
    with fabrik() as s:
        # zweiter Lauf mit demselben Posten, der Index umgangen (sperre = NULL)
        s.execute(
            text(
                "INSERT INTO zahlungslaeufe (id, nr, status, stichtag, ausfuehrung,"
                " auftraggeber_name, auftraggeber_iban, erstellt_am, erstellt_von)"
                " VALUES (:l, 2, 'freigegeben', '2026-10-20', '2026-10-20', 'X',"
                " :iban, '2026-10-20 10:00:00', 'x')"
            ),
            {"iban": IBAN_EIGEN, "l": str(lauf2)},
        )
        s.execute(
            text(
                "INSERT INTO zahlungen (id, lauf_id, nr, posten_id, sperre, kontakt_id,"
                " empfaenger, iban, betrag, skonto, restbetrag_vorher,"
                " verwendungszweck, end_to_end_id, grund) VALUES (:z, :l, 1, :p,"
                " NULL, :k, 'X', :iban, 1190, 0, 1190, 'x', 'x', 'x')"
            ),
            {
                "z": str(uuid4()),
                "l": str(lauf2),
                "p": str(p.id),
                "k": str(k.id),
                "iban": IBAN_MUELLER,
            },
        )
        s.commit()
    assert [b.text for b in _befunde(fabrik).befunde] == [
        "Posten RE-2026-0042 steht schon in Zahlungslauf 2 (freigegeben) — "
        "nie zweimal überweisen"
    ]


def test_vorgeschlagene_zahlung_blockiert_freigabe_und_datei():
    """Zwischen Anlage und Freigabe taucht ein Bankumsatz zum Posten auf."""
    fabrik, lauf, _, p = _lauf()
    zahlung_vorschlagen(fabrik, p)
    assert [b.text for b in _befunde(fabrik).befunde] == [
        "Bankumsatz über 1.190,00 € ist Posten RE-2026-0042 als Zahlung "
        "vorgeschlagen — vielleicht schon bezahlt; erst 'accounti opos bestaetigen' "
        "oder 'accounti opos ablehnen'"
    ]
    with fabrik() as s, pytest.raises(LaufGesperrtError):
        freigeben(s, 1, "erika", E, heute=STICHTAG)


@pytest.mark.parametrize(
    "iban",
    ["CH9300762011623852957", "GB29NWBK60161331926819", "SM86U0322509800000000270100"],
)
def test_iban_ausserhalb_des_ewr_blockiert(iban):
    """CH, GB, SM …: SEPA ja, aber nur mit BIC (und Auftraggeberanschrift)."""
    fabrik, *_ = _lauf(kreditor(iban=iban), beleg_iban=None)
    land = iban[:2]
    assert [b.text for b in _befunde(fabrik).befunde] == [
        f"IBAN {lesbar(iban)} liegt außerhalb des EWR ({land}) — dorthin verlangt "
        "SEPA zusätzlich den BIC der Empfängerbank und die Anschrift des "
        "Auftraggebers, die accounti nicht schreibt; Zahlung entfernen und im "
        "Onlinebanking einzeln überweisen"
    ]


@pytest.mark.parametrize("name", ["Фирма ООД", "Ελληνική Εταιρεία"])
def test_empfaengername_ohne_lateinische_zeichen_blockiert(name):
    """Bereinigt bliebe ein leeres <Nm/> — die Bank wiese die ganze Datei ab."""
    fabrik, *_ = _lauf(kreditor(name=name))
    assert [b.text for b in _befunde(fabrik).befunde] == [
        f"Empfängername „{name}“ enthält keine Zeichen aus dem SEPA-Zeichensatz — "
        "Namen im Stammsatz in lateinischer Schrift pflegen (accounti kontakte "
        "bearbeiten 70001 --name …), dann Zahlung entfernen und neu anlegen"
    ]


def test_auftraggebername_ohne_lateinische_zeichen_blockiert():
    fabrik, *_ = _lauf()
    with fabrik() as s:
        s.execute(text("UPDATE zahlungslaeufe SET auftraggeber_name = '€€€'"))
        s.commit()
    assert [b.text for b in _befunde(fabrik).befunde] == [
        "Name des Auftraggebers fehlt oder enthält keine Zeichen aus dem "
        "SEPA-Zeichensatz (zahlung.auftraggeber.name)"
    ]
