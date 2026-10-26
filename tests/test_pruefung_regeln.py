"""Prüfregeln (Spec 4.1): je Regel ein Fall, der sie auslöst, und einer, der es nicht
darf — Fehlalarme sind so schädlich wie übersehene Befunde (Spec 6). Akzeptanz 1–3."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from accounti.aufgaben import Objekt, erledige, melde_aufgabe
from accounti.belege.archiv import BelegArchiv
from accounti.db.repo_abschluss import speichere_kontoauszugssaldo
from accounti.db.repository import (
    speichere_abgleich,
    speichere_bankkonto,
    speichere_buchung,
    speichere_posten,
    speichere_zuordnung,
)
from accounti.db.tabellen_anlagen import AfaVorgangRow
from accounti.export.kontoauszuege import erstelle_auszuege
from accounti.konfiguration import Buchhaltung, KonfigurationError
from accounti.kontakte.dienst import Partnerdaten
from accounti.models import (
    AbgleichStatus,
    Bankkonto,
    Belegabgleich,
    Belegart,
    Belegrichtung,
    BelegStatus,
    BuchungStatus,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.models.abschluss import Kontoauszugssaldo
from accounti.models.pruefung import Schwere
from accounti.pruefung.einstellungen import PruefEinstellungen
from accounti.pruefung.journal import uebernehme_bestand
from accounti.pruefung.perioden import schliesse
from accounti.pruefung.regeln import (
    PRUEFREGELN,
    Kontext,
    PruefungError,
    fuehre_regeln_aus,
    zeitraum,
)
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    db_url,
    kontakt,
    make_session_fixture,
    umsatz,
)

STICHTAG = date(2026, 10, 20)
FIRMA = Partnerdaten(name="Galerie Muster GmbH", ust_id="DE999999999")
CII = (
    Path(__file__).resolve().parents[1] / "examples" / "erechnung" / "xrechnung_cii.xml"
)


def pruefe(
    make_session,
    regel,
    *,
    period=None,
    stichtag=STICHTAG,
    einstellungen=None,
    archiv=None,
    firma=FIRMA,
    buchhaltung=None,
):
    von, bis = zeitraum(period)
    with make_session() as s:
        k = Kontext(
            s,
            einstellungen or PruefEinstellungen(),
            buchhaltung or Buchhaltung(),
            stichtag,
            von,
            bis,
            firma=firma,
            archiv=archiv,
        )
        return fuehre_regeln_aus(k, [regel]).befunde


def test_alle_regeln_aus_der_spec_sind_registriert():
    fuehre = {
        "umsatz_ohne_beleg",
        "beleg_ohne_zahlung",
        "nummernkreis_luecke",
        "kontoauszug_luecke",
        "pflichtangaben",
        "rechenprobe",
        "steuerschluessel_konto",
        "steuersatz_land",
        "adressat",
        "ig_erwerb_ustid",
        "dublette",
        "beleg_unbearbeitet",
        "buchung_verspaetet",
        "buchung_in_gesperrter_periode",
        "buchung_ohne_beleg",
        "op_alter",
        "periode_nicht_festgeschrieben",
        "bankumsatz_ohne_bankkonto",
    }
    from accounti.pruefung.regeln import _lade_regeln

    _lade_regeln()
    assert fuehre <= set(PRUEFREGELN)


def test_zeitraum():
    assert zeitraum("2026-08") == (date(2026, 8, 1), date(2026, 8, 31))
    assert zeitraum("2026") == (date(2026, 1, 1), date(2026, 12, 31))
    assert zeitraum(None) == (None, None)
    with pytest.raises(PruefungError):
        zeitraum("8/2026")


def test_regeln_aendern_nie_daten(make_session):
    tx = umsatz()
    anlegen(
        make_session,
        tx,
        buchung(tx, status=BuchungStatus.GEPRUEFT, schluessel=3),
        beleg(nummer=None, tag=date(2026, 8, 1)),
    )
    with make_session() as s:
        vorher = list(s.connection().connection.iterdump())
    with make_session() as s:
        k = Kontext(s, PruefEinstellungen(), Buchhaltung(), STICHTAG, firma=FIRMA)
        bericht = fuehre_regeln_aus(k)
        s.commit()
        nachher = list(s.connection().connection.iterdump())
    assert len(bericht.befunde) >= 3
    assert vorher == nachher


# --- Vollständigkeit ------------------------------------------------------------------


def test_akzeptanz_1_zahlung_ohne_beleg_mit_betrag_datum_gegenpartei(make_session):
    tx = umsatz("-119.00", tag=date(2026, 8, 12), name="Stadtwerke Hamburg")
    anlegen(make_session, tx)
    (b,) = pruefe(make_session, "umsatz_ohne_beleg", period="2026-08")
    assert (b.objekt_typ, b.objekt_id) == ("transaktion", str(tx.id))
    assert b.betrag == Decimal("-119.00")
    assert b.datum == date(2026, 8, 12)
    assert b.gegenpartei == "Stadtwerke Hamburg"
    assert b.schwere is Schwere.WARNUNG
    assert "12.08.2026" in b.text and "-119,00 €" in b.text
    assert "Stadtwerke Hamburg" in b.text


def test_umsatz_mit_beleg_ist_kein_befund(make_session):
    abgeglichen, zugeordnet, gebucht = umsatz(), umsatz(), umsatz()
    q = beleg(belegart=Belegart.QUITTUNG)
    anlegen(make_session, abgeglichen, zugeordnet, gebucht, q)
    with make_session() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=abgeglichen.id,
                beleg_id=q.id,
                stufe="exakt",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Test",
            ),
        )
        speichere_zuordnung(
            s,
            Zahlungszuordnung(
                transaktion_id=zugeordnet.id,
                posten_id=uuid4(),
                betrag=Decimal("119"),
                stufe="exakt",
                status=ZuordnungStatus.GEBUCHT,
                confidence=1.0,
                begruendung="Test",
            ),
        )
        speichere_buchung(s, buchung(gebucht, beleg_id=q.id))
        s.commit()
    assert pruefe(make_session, "umsatz_ohne_beleg") == []


def test_umsatz_ohne_beleg_schwellen_belegfrei_und_zeitraum(make_session):
    klein = umsatz("-4.99", zweck="Kontoführung", name="Bank")
    jung = umsatz("-50.00", tag=STICHTAG - timedelta(days=1))
    alt = umsatz("-50.00", tag=date(2026, 7, 1))
    anlegen(make_session, klein, jung, alt)
    e = PruefEinstellungen.model_validate(
        {"regeln": {"umsatz_ohne_beleg": {"ab_betrag": 5, "nach_tagen": 3}}}
    )
    ids = {
        b.objekt_id for b in pruefe(make_session, "umsatz_ohne_beleg", einstellungen=e)
    }
    assert ids == {str(alt.id)}
    belegfrei = PruefEinstellungen.model_validate(
        {
            "belegfrei": [
                {
                    "name": "bank",
                    "muster": "kontoführung",
                    "feld": "verwendungszweck",
                    "begruendung": "Bankentgelt — der Auszug ist der Beleg",
                }
            ]
        }
    )
    ids = {
        b.objekt_id
        for b in pruefe(make_session, "umsatz_ohne_beleg", einstellungen=belegfrei)
    }
    assert str(klein.id) not in ids and str(alt.id) in ids
    assert pruefe(make_session, "umsatz_ohne_beleg", period="2026-09") == []


def test_begruendet_belegfrei_erledigt_ist_kein_befund(make_session):
    tx = umsatz("-12.00", zweck="Zinsen")
    anlegen(make_session, tx)
    with make_session() as s:
        m = melde_aufgabe(s, "beleg_fehlt", Objekt("transaktion", tx.id), titel="x")
        erledige(s, m.aufgabe.nr, von="jan", text="Zinsen: der Auszug ist Beleg")
        s.commit()
    assert pruefe(make_session, "umsatz_ohne_beleg") == []


def _posten(k, **kw):
    werte = {
        "kontakt_id": k.id,
        "beleg_id": uuid4(),
        "richtung": PostenRichtung.VERBINDLICHKEIT,
        "belegnummer": "RE-1",
        "belegdatum": date(2026, 8, 1),
        "betrag": Decimal("119.00"),
        "faellig_am": date(2026, 8, 15),
    }
    werte.update(kw)
    return OffenerPosten.model_validate(werte)


def test_beleg_ohne_zahlung(make_session):
    k = kontakt()
    faellig = _posten(k)
    offen = _posten(k, belegnummer="RE-2", faellig_am=date(2026, 11, 1))
    forderung = _posten(k, belegnummer="A-1", richtung=PostenRichtung.FORDERUNG)
    anlegen(make_session, k)
    with make_session() as s:
        for p in (faellig, offen, forderung):
            speichere_posten(s, p)
        s.commit()
    befunde = {b.objekt_id: b for b in pruefe(make_session, "beleg_ohne_zahlung")}
    assert set(befunde) == {str(faellig.id), str(forderung.id)}
    assert befunde[str(faellig.id)].schwere is Schwere.WARNUNG
    assert befunde[str(forderung.id)].schwere is Schwere.HINWEIS
    assert "seit 66 Tagen fällig" in befunde[str(faellig.id)].text


def test_quittung_ohne_umsatz(make_session):
    alt = beleg(belegart=Belegart.QUITTUNG, tag=date(2026, 8, 1), datei_hash="b" * 64)
    neu = beleg(belegart=Belegart.QUITTUNG, tag=date(2026, 10, 15), datei_hash="c" * 64)
    anlegen(make_session, alt, neu)
    ids = {b.objekt_id for b in pruefe(make_session, "beleg_ohne_zahlung")}
    assert ids == {str(alt.id)}


def _ausgang(nr, tag=date(2026, 8, 1)):
    return beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer=nr,
        tag=tag,
        datei_hash=uuid4().hex * 2,
    )


def test_nummernkreis_luecke_und_doppelt(make_session):
    anlegen(
        make_session,
        _ausgang("2026-0001"),
        _ausgang("2026-0002"),
        _ausgang("2026-0004"),
        _ausgang("2026-0004"),
        _ausgang("A-7"),
    )
    befunde = pruefe(make_session, "nummernkreis_luecke", period="2026")
    texte = [b.text for b in befunde]
    assert any("Nummer 3 fehlt" in t for t in texte)
    doppelt = [b for b in befunde if "2-mal vergeben" in b.text]
    assert len(doppelt) == 1 and doppelt[0].schwere is Schwere.FEHLER


def test_nummernkreis_lueckenlos(make_session):
    anlegen(make_session, _ausgang("RE-2026-001"), _ausgang("RE-2026-002"))
    assert pruefe(make_session, "nummernkreis_luecke") == []


def test_kontoauszug_saldo_luecke(make_session):
    konto = Bankkonto(iban="DE89370400440532013000", bezeichnung="Giro")
    anlegen(
        make_session,
        umsatz("-100.00", tag=date(2026, 8, 5), bankkonto_id=konto.id),
        umsatz("200.00", tag=date(2026, 8, 20), bankkonto_id=konto.id),
    )
    with make_session() as s:
        speichere_bankkonto(s, konto)
        for tag, saldo in ((date(2026, 7, 31), "1000"), (date(2026, 8, 31), "1050")):
            speichere_kontoauszugssaldo(
                s,
                Kontoauszugssaldo(
                    bankkonto_id=konto.id, stichtag=tag, saldo=Decimal(saldo)
                ),
            )
        s.commit()
    (b,) = pruefe(make_session, "kontoauszug_luecke")
    assert b.objekt_typ == "bankkonto" and b.betrag == Decimal("-50")
    assert "es fehlen Umsätze" in b.text


def test_festgeschriebener_kontoauszug_mit_fehlendem_umsatz(make_session):
    august = umsatz("-100.00", tag=date(2026, 8, 5), sachkonto="1200")
    september = umsatz("50.00", tag=date(2026, 9, 5), sachkonto="1200")
    anlegen(make_session, august, september)
    with make_session() as s:
        erstelle_auszuege(
            s,
            "1200",
            date(2026, 9, 30),
            anfangssaldo=Decimal("1000"),
            ab=date(2026, 8, 1),
            heute=STICHTAG,
        )
        s.commit()
    assert pruefe(make_session, "kontoauszug_luecke") == []
    with make_session() as s:  # an accounti vorbei gelöscht
        s.execute(
            text("DELETE FROM transaktionen WHERE id = :id"), {"id": str(august.id)}
        )
        s.commit()
    befunde = pruefe(make_session, "kontoauszug_luecke")
    assert befunde and all(b.schwere is Schwere.FEHLER for b in befunde)
    assert any("nicht mehr vorhanden" in b.text for b in befunde)


def test_kontoauszug_saldo_stimmt_und_monat_ohne_umsatz(make_session):
    konto = Bankkonto(iban="DE89370400440532013000", bezeichnung="Giro")
    anlegen(
        make_session,
        umsatz("-100.00", tag=date(2026, 6, 5), bankkonto_id=konto.id),
        umsatz("200.00", tag=date(2026, 8, 20), bankkonto_id=konto.id),
    )
    with make_session() as s:
        speichere_bankkonto(s, konto)
        for tag, saldo in ((date(2026, 5, 31), "1000"), (date(2026, 8, 31), "1100")):
            speichere_kontoauszugssaldo(
                s,
                Kontoauszugssaldo(
                    bankkonto_id=konto.id, stichtag=tag, saldo=Decimal(saldo)
                ),
            )
        s.commit()
    (b,) = pruefe(make_session, "kontoauszug_luecke")
    assert b.schwere is Schwere.HINWEIS and "2026-07" in b.text


# --- Richtigkeit: § 14 UStG (Akzeptanz 2) --------------------------------------------

RECHNUNGSTEXT = """Bürobedarf Müller GmbH · Hauptstraße 12 · 20095 Hamburg
An: Galerie Muster GmbH, Beispielweg 3, 24103 Kiel
Rechnung Nr. RE-2026-0815
Rechnungsdatum: 10.08.2026   Leistungsdatum: 05.08.2026
Papier A4, 10 Pakete   100,00 EUR
Netto 100,00  USt 19 % 19,00  Brutto 119,00
{zusatz}
"""


def _archiviert(make_session, tmp_path, inhalt, endung=".txt", **kw):
    archiv = BelegArchiv(tmp_path / "archiv")
    datei_hash = archiv.ablegen(inhalt, endung)
    b = beleg(datei_hash=datei_hash, **kw)
    b = b.model_copy(update={"dateiname": f"rechnung{endung}"})
    anlegen(make_session, b)
    return archiv, b


def test_akzeptanz_2_rechnung_ohne_steuernummer_unvollstaendig(make_session, tmp_path):
    archiv, b = _archiviert(
        make_session,
        tmp_path,
        RECHNUNGSTEXT.format(zusatz="").encode(),
        netto="500.00",
        steuer="95.00",
        brutto="595.00",
        positionen=[("Papier", "500.00", "19", "95.00")],
    )
    (befund,) = pruefe(make_session, "pflichtangaben", archiv=archiv)
    assert befund.schwere is Schwere.FEHLER
    assert befund.objekt_id == str(b.id)
    assert "unvollständig nach § 14 Abs. 4 UStG" in befund.text
    assert "Nr. 2 Steuernummer oder USt-IdNr." in befund.text


def test_rechnung_mit_steuernummer_ist_vollstaendig(make_session, tmp_path):
    archiv, _ = _archiviert(
        make_session,
        tmp_path,
        RECHNUNGSTEXT.format(zusatz="Steuernummer: 12/345/67890").encode(),
        netto="500.00",
        steuer="95.00",
        brutto="595.00",
        positionen=[("Papier", "500.00", "19", "95.00")],
    )
    assert pruefe(make_session, "pflichtangaben", archiv=archiv) == []


def test_belegangaben_begrenzen_leerraum_und_laenge(make_session, tmp_path):
    """Mittel 2 (Nachprüfung C, Runde 4): Der Prüflauf liest das Original aus dem
    Archiv — dort war weder der Leerraum begrenzt (20 000 Leerzeichen nach
    „Steuer-Nr.“: 7,5 s, quadratisch) noch die Länge. Anfang und Ende bleiben, der
    Hinweis sagt, dass gekürzt wurde."""
    from accounti.pruefung.belegangaben import lies_angaben
    from tests.test_belege_extraktion import _zeitschranke

    zusatz = (
        "Steuer-Nr."
        + " " * 20_000
        + "x\n"
        + "a" * 300_000
        + "\nSteuernummer: 12/345/67890"
    )
    archiv, b = _archiviert(
        make_session, tmp_path, RECHNUNGSTEXT.format(zusatz=zusatz).encode()
    )
    with _zeitschranke(5):
        a = lies_angaben(b, archiv)
    assert a.steuernummer == "12/345/67890"
    assert a.hinweis is not None and "gekürzt" in a.hinweis
    assert a.text is not None and len(a.text) <= 100_000


def test_kleinbetragsrechnung_braucht_keine_steuernummer(make_session, tmp_path):
    archiv, _ = _archiviert(
        make_session, tmp_path, RECHNUNGSTEXT.format(zusatz="").encode()
    )  # 119,00 € ≤ 250 €
    assert pruefe(make_session, "pflichtangaben", archiv=archiv) == []


def test_ohne_archiv_nur_nicht_erkannt(make_session):
    anlegen(make_session, beleg(brutto="595.00", netto="500.00", steuer="95.00"))
    befunde = pruefe(make_session, "pflichtangaben")
    haupt = next(b for b in befunde if b.objekt_typ == "beleg")
    assert haupt.schwere is Schwere.WARNUNG and "nicht erkannt" in haupt.text
    assert any(b.objekt_typ == "pruefung" for b in befunde)


def test_erechnung_mit_ustid_ist_vollstaendig(make_session, tmp_path):
    archiv, _ = _archiviert(
        make_session, tmp_path, CII.read_bytes(), endung=".xml", brutto="595.00"
    )
    assert pruefe(make_session, "pflichtangaben", archiv=archiv) == []


def test_erechnung_ohne_ustid_und_steuernummer(make_session, tmp_path):
    ohne = re.sub(
        rb"<ram:SpecifiedTaxRegistration>\s*"
        rb"<ram:ID schemeID=\"VA\">DE123456789</ram:ID>"
        rb"\s*</ram:SpecifiedTaxRegistration>",
        b"",
        CII.read_bytes(),
    )
    archiv, _ = _archiviert(
        make_session, tmp_path, ohne, endung=".xml", brutto="595.00"
    )
    (befund,) = pruefe(make_session, "pflichtangaben", archiv=archiv)
    assert befund.schwere is Schwere.FEHLER and "Nr. 2" in befund.text


# --- Richtigkeit: Rechenprobe --------------------------------------------------


def test_rechenprobe(make_session):
    falsch = beleg(netto="100.00", steuer="19.00", brutto="120.00", datei_hash="d" * 64)
    richtig = beleg(datei_hash="e" * 64)
    anlegen(
        make_session,
        falsch,
        richtig,
        buchung(netto="100.00", steuer="17.00", schluessel=9),
        buchung(netto="100.00", steuer="19.00", schluessel=9),
    )
    befunde = pruefe(make_session, "rechenprobe")
    assert {(b.objekt_typ, b.schwere) for b in befunde} == {
        ("beleg", Schwere.FEHLER),
        ("buchung", Schwere.WARNUNG),
    }
    assert next(b for b in befunde if b.objekt_typ == "beleg").objekt_id == str(
        falsch.id
    )


# --- Richtigkeit: Steuerschlüssel ./. Sachkonto (Akzeptanz 3) -------------------------


@pytest.fixture
def skr03(tmp_path, monkeypatch):
    """Die mitgelieferte SKR03-Datei gilt unabhängig vom Arbeitsverzeichnis."""
    monkeypatch.chdir(tmp_path)


def test_akzeptanz_3_steuerschluessel_passt_nicht_zum_sachkonto(make_session, skr03):
    vst_auf_erloes = buchung(soll="1200", haben="8400", schluessel=9)
    ust_auf_aufwand = buchung(soll="4930", haben="1200", schluessel=3, steuer="19.00")
    # DATEV SKR03 2026: 3400 = Wareneingang 19 % Vorsteuer (AV)
    automatik = buchung(soll="3400", haben="1200", schluessel=8, steuer="7.00")
    steuerfrei = buchung(soll="1400", haben="8125", schluessel=3)
    zahlung = buchung(soll="70001", haben="1200", schluessel=9)
    anlegen(
        make_session, vst_auf_erloes, ust_auf_aufwand, automatik, steuerfrei, zahlung
    )
    befunde = {b.objekt_id: b for b in pruefe(make_session, "steuerschluessel_konto")}
    assert set(befunde) == {
        str(x.id)
        for x in (vst_auf_erloes, ust_auf_aufwand, automatik, steuerfrei, zahlung)
    }
    assert all(b.schwere is Schwere.FEHLER for b in befunde.values())
    assert "Vorsteuerschlüssel 9" in befunde[str(vst_auf_erloes.id)].text
    assert "Erlöskonto 8400" in befunde[str(vst_auf_erloes.id)].text
    assert "Aufwandskonto 4930" in befunde[str(ust_auf_aufwand.id)].text
    assert "Automatikkonto" in befunde[str(automatik.id)].text
    assert "feste Steuerfunktion" in befunde[str(steuerfrei.id)].text
    assert "Geld- und Personenkonten" in befunde[str(zahlung.id)].text


def test_passende_steuerschluessel_sind_kein_befund(make_session, skr03):
    anlegen(
        make_session,
        buchung(soll="4930", haben="1200", schluessel=9),
        buchung(soll="1200", haben="8400", schluessel=3),
        buchung(soll="3400", haben="1200", schluessel=9),  # Wareneingang 19 % (AV)
        buchung(soll="3300", haben="1200", schluessel=8, steuer="7.00"),  # 7 % (AV)
        buchung(soll="1400", haben="8125", schluessel=None, steuer=None),
        buchung(soll="70001", haben="1200", schluessel=None, steuer=None),
        buchung(soll="4970", haben="1200", schluessel=None, steuer=None),
    )
    assert pruefe(make_session, "steuerschluessel_konto") == []


@pytest.mark.parametrize(
    ("soll", "haben", "schluessel", "steuer"),
    [
        ("4900", "70001", 8, "7.00"),  # Standardaufwand mit 7 % (Belegverbuchung)
        ("4900", "70001", 9, "19.00"),
        ("4940", "1200", 9, "19.00"),  # Online-Abo 19 %
        ("8700", "1400", 2, "0.70"),  # Erlösschmälerung 7 %
        ("3000", "70001", 8, "7.00"),
        ("4210", "1200", 9, "19.00"),  # Miete mit Option zur Steuerpflicht
        ("4500", "1200", 8, "7.00"),
        ("4920", "1200", 9, "19.00"),
        ("4955", "1200", 9, "19.00"),
    ],
)
def test_keine_automatikkonten_laut_datev(
    make_session, skr03, soll, haben, schluessel, steuer
):
    """DATEV SKR03 2026: diese Konten haben keine AV/AM-Automatik — kein Fehler."""
    anlegen(
        make_session,
        buchung(soll=soll, haben=haben, schluessel=schluessel, steuer=steuer),
    )
    assert pruefe(make_session, "steuerschluessel_konto") == []


@pytest.mark.parametrize("mit_beleg", [False, True])
def test_abhilfe_ist_ein_gueltiger_aufruf(make_session, skr03, tmp_path, mit_beleg):
    """Befund B-Niedrig: die Abhilfe nennt --soll/--haben und läuft so durch."""
    import shlex

    from typer.testing import CliRunner

    from accounti.cli import app

    zahlung = buchung(
        soll="70001",
        haben="1200",
        schluessel=9,
        status=BuchungStatus.ZUR_PRUEFUNG,
        beleg_id=uuid4() if mit_beleg else None,
    )
    anlegen(make_session, zahlung)
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert "--soll 70001 --haben 1200 --ohne-steuer" in befund.abhilfe
    args = shlex.split(befund.abhilfe.replace("…", "Zahlung ohne Steuer"))[1:]
    r = CliRunner().invoke(app, [*args, "--db", db_url(tmp_path)])
    assert r.exit_code == 0, r.output
    assert pruefe(make_session, "steuerschluessel_konto") == []


def test_abhilfe_freigegeben_ohne_storno(make_session, skr03):
    """Freigegeben und beide Seiten Geld-/Personenkonto: ein Storno höbe die Steuer
    nicht auf — die Abhilfe verspricht keinen Aufruf, der scheitert."""
    anlegen(
        make_session,
        buchung(
            soll="70001", haben="1200", schluessel=9, status=BuchungStatus.GEPRUEFT
        ),
    )
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert "korrigiere" not in befund.abhilfe and "Steuerberater" in befund.abhilfe


def test_konto_ohne_vorsteuerfunktion_ist_nur_ein_hinweis(make_session, skr03):
    anlegen(make_session, buchung(soll="4360", haben="1200", schluessel=9))
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert befund.schwere is Schwere.HINWEIS
    assert "4360" in befund.text and "keine Vorsteuer" in befund.text


def test_storniertes_ist_kein_befund(make_session, skr03):
    falsch = buchung(soll="1200", haben="8400", schluessel=9)
    storno = buchung(soll="8400", haben="1200", schluessel=9, storno_von=falsch.id)
    anlegen(
        make_session, falsch.model_copy(update={"storniert_durch": storno.id}), storno
    )
    assert pruefe(make_session, "steuerschluessel_konto") == []


def test_skr04_ohne_automatikdatei(make_session):
    anlegen(make_session, buchung(soll="1800", haben="4400", schluessel=9))
    befunde = pruefe(
        make_session,
        "steuerschluessel_konto",
        buchhaltung=Buchhaltung(kontenrahmen="SKR04", bank_konto="1800"),
    )
    assert len(befunde) == 1 and "Erlöskonto 4400" in befunde[0].text


# --- Richtigkeit: Bankumsatz ohne Bankkonto (Gesamttest Betrieb B3) ----------------

SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800")


def test_bankumsatz_ohne_bankkonto_skr03_regel_in_skr04(make_session):
    """SKR03-Regel (Bank 1200) in einer SKR04-Gesellschaft: 1200 ist dort eine
    Forderung — die Bereichsprüfung sieht nichts, die Bankabstimmung erst im
    Abschluss."""
    miete, versicherung = umsatz("-1200.00"), umsatz("-320.00")
    falsch = buchung(miete, soll="4210", haben="1200", schluessel=None, steuer=None)
    richtig = buchung(
        versicherung, soll="6400", haben="1800", schluessel=None, steuer=None
    )
    anlegen(make_session, miete, versicherung, falsch, richtig)
    (befund,) = pruefe(make_session, "bankumsatz_ohne_bankkonto", buchhaltung=SKR04)
    assert befund.objekt_id == str(falsch.id) and befund.schwere is Schwere.FEHLER
    assert "4210 an 1200" in befund.text and "1800" in befund.text
    assert befund.abhilfe and f"korrigiere {str(falsch.id)[:8]}" in befund.abhilfe


def test_bankumsatz_eigenes_konto_und_mehrere_buchungen_kein_befund(make_session):
    karte = Bankkonto(iban="VISA1234", bezeichnung="Visa", sachkonto="3610")
    with make_session() as s:
        speichere_bankkonto(s, karte)
        s.commit()
    kartenumsatz = umsatz("-23.99", sachkonto="3610", bankkonto_id=karte.id)
    kasse = umsatz("-12.00", sachkonto="1600")
    zahlung = umsatz("-119.00")
    anlegen(
        make_session,
        kartenumsatz,
        kasse,
        zahlung,
        buchung(kartenumsatz, soll="6815", haben="3610"),
        buchung(kasse, soll="6815", haben="1600"),
        # Zahlung mit Skonto: eine Buchung trägt die Bank, die andere nicht
        buchung(zahlung, soll="70001", haben="1800", schluessel=None, steuer=None),
        buchung(zahlung, soll="70001", haben="5736", netto="4.20", steuer="0.80"),
    )
    assert pruefe(make_session, "bankumsatz_ohne_bankkonto", buchhaltung=SKR04) == []


def test_bankumsatz_storno_und_ohne_umsatz_kein_befund(make_session):
    tx = umsatz("-50.00")
    falsch = buchung(tx, soll="4930", haben="1576", status=BuchungStatus.GEPRUEFT)
    storno = buchung(
        tx,
        soll="1576",
        haben="4930",
        status=BuchungStatus.GEPRUEFT,
        storno_von=falsch.id,
    )
    anlegen(
        make_session,
        tx,
        falsch.model_copy(update={"storniert_durch": storno.id}),
        storno,
        buchung(soll="4930", haben="70001"),  # Belegbuchung ohne Umsatz
    )
    assert pruefe(make_session, "bankumsatz_ohne_bankkonto") == []


def test_bankkonto_der_konfiguration_kein_bankkonto_im_kontenrahmen(make_session):
    """SKR04 ohne buchhaltung.bank_konto: der Standard 1200 ist dort eine Forderung."""
    tx = umsatz("-1200.00")
    anlegen(
        make_session,
        tx,
        buchung(tx, soll="6310", haben="1200", schluessel=None, steuer=None),
    )
    befunde = pruefe(
        make_session,
        "bankumsatz_ohne_bankkonto",
        buchhaltung=Buchhaltung(kontenrahmen="SKR04"),
    )
    (befund,) = befunde
    assert befund.objekt_typ == "konto" and befund.objekt_id == "1200"
    assert "buchhaltung.bank_konto" in befund.text and "SKR04" in befund.text


# --- Richtigkeit: Steuersatz, Adressat, ig. Erwerb, Dubletten -------------------------


def test_steuersatz_zum_land(make_session):
    fr = kontakt(name="Papeterie SARL", land="FR", kreditor_konto="70002")
    de16 = beleg(positionen=[("x", "100.00", "16", "16.00")], datei_hash="1" * 64)
    de19 = beleg(datei_hash="2" * 64)
    aus_fr = beleg(
        kontakt_id=fr.id,
        positionen=[("x", "100.00", "20", "20.00")],
        datei_hash="3" * 64,
    )
    vst_aus_fr = buchung(soll="4930", haben="70002", schluessel=9, beleg_id=aus_fr.id)
    anlegen(make_session, fr, de16, de19, aus_fr, vst_aus_fr)
    befunde = {b.objekt_id: b for b in pruefe(make_session, "steuersatz_land")}
    assert set(befunde) == {str(de16.id), str(aus_fr.id), str(vst_aus_fr.id)}
    assert befunde[str(de16.id)].schwere is Schwere.WARNUNG
    assert "16 %" in befunde[str(de16.id)].text
    assert befunde[str(aus_fr.id)].schwere is Schwere.HINWEIS
    assert befunde[str(vst_aus_fr.id)].schwere is Schwere.FEHLER


def test_adressat_erechnung(make_session, tmp_path):
    archiv, b = _archiviert(
        make_session, tmp_path, CII.read_bytes(), endung=".xml", brutto="595.00"
    )
    assert pruefe(make_session, "adressat", archiv=archiv) == []
    anders = Partnerdaten(name="Atelier Anders AG", ust_id="DE111111111")
    (befund,) = pruefe(make_session, "adressat", archiv=archiv, firma=anders)
    assert befund.schwere is Schwere.FEHLER
    assert "Galerie Muster GmbH" in befund.text and befund.objekt_id == str(b.id)


def test_adressat_text_und_kleinbetrag(make_session, tmp_path):
    inhalt = RECHNUNGSTEXT.format(zusatz="").replace("Galerie Muster GmbH", "Jemand")
    archiv, _ = _archiviert(
        make_session, tmp_path, inhalt.encode(), brutto="595.00", netto="500.00"
    )
    (befund,) = pruefe(make_session, "adressat", archiv=archiv)
    assert befund.schwere is Schwere.WARNUNG
    eigene = PruefEinstellungen(eigene_namen=["Jemand"])
    assert pruefe(make_session, "adressat", archiv=archiv, einstellungen=eigene) == []


def test_ig_erwerb_ohne_ustid(make_session):
    ohne = kontakt(name="Fournisseur SA", land="FR", kreditor_konto="70003")
    mit = kontakt(
        name="Lieferant BV", land="NL", kreditor_konto="70004", ust_id="NL123456789B01"
    )
    inland = kontakt(name="Inland GmbH", kreditor_konto="70005", ust_id="DE123456789")
    a = buchung(soll="3425", haben="70003", schluessel=19)
    b = buchung(soll="3425", haben="70004", schluessel=19)
    c = buchung(soll="3425", haben="70005", schluessel=19)
    normal = buchung(soll="3300", haben="70005", schluessel=8, steuer="7.00")
    anlegen(make_session, ohne, mit, inland, a, b, c, normal)
    befunde = {b.objekt_id: b for b in pruefe(make_session, "ig_erwerb_ustid")}
    assert set(befunde) == {str(a.id), str(b.id), str(c.id)}
    assert befunde[str(a.id)].schwere is Schwere.FEHLER
    assert "§ 14a Abs. 3" in befunde[str(a.id)].text
    assert befunde[str(b.id)].schwere is Schwere.HINWEIS  # nicht beim BZSt geprüft
    assert befunde[str(c.id)].schwere is Schwere.FEHLER  # Lieferant im Inland


def test_dubletten(make_session):
    k = kontakt()
    erste = beleg(kontakt_id=k.id, datei_hash="4" * 64, tag=date(2026, 8, 1))
    zweite = beleg(
        kontakt_id=k.id, datei_hash="5" * 64, tag=date(2026, 8, 3), nummer="X"
    )
    spaet = beleg(
        kontakt_id=k.id, datei_hash="6" * 64, tag=date(2026, 9, 30), nummer="Y"
    )
    gleich = beleg(kontakt_id=k.id, datei_hash="7" * 64, tag=date(2026, 9, 30))
    doppelt = [buchung(soll="4930", haben="70001", beleg_id=erste.id) for _ in range(2)]
    anlegen(make_session, k, erste, zweite, spaet, gleich, *doppelt)
    befunde = {b.objekt_id: b for b in pruefe(make_session, "dublette")}
    assert (
        str(zweite.id) in befunde and befunde[str(zweite.id)].schwere is Schwere.WARNUNG
    )
    assert str(gleich.id) in befunde  # am selben Tag wie spaet
    assert str(spaet.id) not in befunde
    gebucht = [b for b in befunde.values() if b.objekt_typ == "buchung"]
    assert len(gebucht) == 1 and gebucht[0].schwere is Schwere.FEHLER


# --- Zeitgerechtheit -----------------------------------------------------------------


def test_beleg_unbearbeitet(make_session):
    liegt = beleg(status=BelegStatus.EINGEGANGEN, datei_hash="8" * 64)
    frisch = beleg(status=BelegStatus.EINGEGANGEN, datei_hash="9" * 64).model_copy(
        update={"eingegangen_am": datetime(2026, 10, 15, 9, 0)}
    )
    erfasst_ungebucht = beleg(datei_hash="f" * 64)
    anlegen(make_session, liegt, frisch, erfasst_ungebucht)
    befunde = {b.objekt_id: b for b in pruefe(make_session, "beleg_unbearbeitet")}
    assert set(befunde) == {str(liegt.id), str(erfasst_ungebucht.id)}
    assert "nicht gebucht" in befunde[str(erfasst_ungebucht.id)].text


def test_buchung_verspaetet(make_session):
    heute = date.today()
    tx_alt, tx_neu = umsatz(tag=heute - timedelta(days=120)), umsatz(tag=heute)
    alt, neu = buchung(tx_alt), buchung(tx_neu)
    anlegen(make_session, tx_alt, tx_neu, alt, neu)
    befunde = pruefe(make_session, "buchung_verspaetet", stichtag=heute)
    assert [b.objekt_id for b in befunde] == [str(alt.id)]
    assert befunde[0].schwere is Schwere.HINWEIS


def test_bestand_von_vor_dem_journal_ist_nicht_verspaetet(make_session):
    """Übernommener Bestand hat keinen bekannten Buchungszeitpunkt — kein Befund,
    weder „verspätet“ noch „nach dem Abschluss angelegt“."""
    tx = umsatz(tag=date(2026, 6, 3))
    b = buchung(tx, status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, tx, b)
    with make_session() as s:
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text("DELETE FROM journal"))
        uebernehme_bestand(s)
        schliesse(s, "2026-06", "erika")
        s.commit()
    assert pruefe(make_session, "buchung_verspaetet") == []
    assert pruefe(make_session, "buchung_in_gesperrter_periode") == []


def test_buchung_in_gesperrter_periode(make_session):
    tx = umsatz(tag=date(2026, 8, 20))
    vorher = buchung(status=BuchungStatus.GEPRUEFT, tag=date(2026, 8, 5))
    anlegen(make_session, tx, vorher)
    with make_session() as s:
        schliesse(s, "2026-08", "erika", trotzdem=True)
        s.commit()
        # an accounti vorbei nachgebucht (rohes SQL umgeht Sperre und Journal)
        s.execute(
            text(
                "INSERT INTO buchungssaetze (id, datum, soll_konto, haben_konto, "
                "betrag_netto, buchungstext, status, confidence) VALUES "
                "(:id, '2026-08-10', '4930', '1200', 5, 'nachgebucht', 'geprueft', 1)"
            ),
            {"id": str(uuid4())},
        )
        s.commit()
    befunde = pruefe(make_session, "buchung_in_gesperrter_periode")
    arten = sorted((b.objekt_typ, b.schwere.value) for b in befunde)
    assert arten == [("buchung", "fehler"), ("transaktion", "warnung")]
    assert (
        "ohne Journaleintrag"
        in next(b for b in befunde if b.objekt_typ == "buchung").text
    )


def test_keine_sperre_kein_befund(make_session):
    anlegen(make_session, buchung(tag=date(2026, 8, 5)))
    assert pruefe(make_session, "buchung_in_gesperrter_periode") == []


# --- Ordnung -------------------------------------------------------------------------


def test_buchung_ohne_beleg(make_session):
    umbuchung = buchung(None, soll="4930", haben="4900", schluessel=None, steuer=None)
    eb = buchung(None, soll="1200", haben="9000", schluessel=None, steuer=None)
    afa = buchung(None, soll="4830", haben="0420", schluessel=None, steuer=None)
    anlegen(make_session, umbuchung, eb, afa)
    with make_session() as s:
        s.add(
            AfaVorgangRow(
                id=str(uuid4()),
                objekt="anlage",
                jahr=2026,
                bis_monat=8,
                betrag=Decimal("100"),
                buchung_id=str(afa.id),
                begruendung="linear",
                erstellt_am=datetime(2026, 9, 1),
            )
        )
        s.commit()
    befunde = pruefe(make_session, "buchung_ohne_beleg")
    assert [b.objekt_id for b in befunde] == [str(umbuchung.id)]


def test_op_alter(make_session):
    k = kontakt()
    alt = _posten(k, belegdatum=date(2025, 6, 1), faellig_am=date(2025, 7, 1))
    jung = _posten(k, belegnummer="RE-9")
    kaputt = _posten(k, belegnummer="RE-8", restbetrag=Decimal("500.00"))
    anlegen(make_session, k)
    with make_session() as s:
        for p in (alt, jung, kaputt):
            speichere_posten(s, p)
        s.commit()
    befunde = {b.objekt_id: b for b in pruefe(make_session, "op_alter")}
    assert set(befunde) == {str(alt.id), str(kaputt.id)}
    assert befunde[str(kaputt.id)].schwere is Schwere.FEHLER


def test_periode_nicht_festgeschrieben(make_session):
    anlegen(
        make_session,
        buchung(status=BuchungStatus.GEPRUEFT, tag=date(2026, 7, 5)),
        buchung(status=BuchungStatus.GEPRUEFT, tag=date(2026, 8, 5)),
        buchung(status=BuchungStatus.GEPRUEFT, tag=date(2026, 9, 5)),
    )
    with make_session() as s:
        schliesse(s, "2026-07", "erika")
        s.commit()
    befunde = pruefe(make_session, "periode_nicht_festgeschrieben")
    assert [b.objekt_id for b in befunde] == ["2026-08"]  # September: Oktober läuft


# --- Konfiguration --------------------------------------------------------------------


def test_schwere_und_abschalten_aus_der_konfiguration(make_session):
    anlegen(make_session, umsatz())
    e = PruefEinstellungen.model_validate({"schwere": {"umsatz_ohne_beleg": "fehler"}})
    (b,) = pruefe(make_session, "umsatz_ohne_beleg", einstellungen=e)
    assert b.schwere is Schwere.FEHLER
    with make_session() as s:
        k = Kontext(
            s,
            PruefEinstellungen(abgeschaltet=["umsatz_ohne_beleg"]),
            Buchhaltung(),
            STICHTAG,
        )
        bericht = fuehre_regeln_aus(k)
    assert "umsatz_ohne_beleg" not in bericht.regeln


def test_falsche_konfiguration(make_session):
    for werte in (
        {"abgeschaltet": ["gibt_es_nicht"]},
        {"regeln": {"umsatz_ohne_beleg": {"ab_betrag": -1}}},
        {"regeln": {"op_alter": {"max_tage": "viele"}}},
    ):
        with make_session() as s, pytest.raises(KonfigurationError):
            fuehre_regeln_aus(
                Kontext(
                    s, PruefEinstellungen.model_validate(werte), Buchhaltung(), STICHTAG
                )
            )
    with make_session() as s, pytest.raises(PruefungError, match="Unbekannte Regel"):
        fuehre_regeln_aus(
            Kontext(s, PruefEinstellungen(), Buchhaltung(), STICHTAG), ["nix"]
        )


# --- Befunde der fachlichen Prüfung: Marktplatz, Land, § 13b/§ 6a --------------------


def test_marktplatz_abrechnung_ist_keine_dublette(make_session):
    """Befund B-M5: zwei Bestellungen zum selben Preis in einer Abrechnung."""
    abr = beleg(
        belegart=Belegart.SONSTIGES,
        nummer="AMZ-2026-08",
        netto="33.60",
        steuer="6.38",
        brutto="39.98",
        lieferant="Amazon",
    )
    bestellungen = [
        buchung(
            soll="1361",
            haben="8400",
            netto="16.80",
            steuer="3.19",
            schluessel=3,
            status=BuchungStatus.AUTO_GEBUCHT,
            beleg_id=abr.id,
            beleg_nummer=nummer,
        )
        for nummer in ("302-111", "302-222")
    ]
    anlegen(make_session, abr, *bestellungen)
    assert pruefe(make_session, "dublette") == []


def test_auslaendischer_lieferant_mit_deutscher_ustid(make_session):
    """Befund B-M6: Amazon EU S.à r.l. (LU) stellt deutsche USt unter ihrer
    DE-USt-IdNr. in Rechnung — die Vorsteuer ist abziehbar."""
    amazon = kontakt(
        name="Amazon EU S.a r.l.",
        land="LU",
        kreditor_konto="70010",
        ust_id="LU20260743",
    )
    rechnung = beleg(
        nummer="DE6ABCD",
        lieferant="Amazon EU S.a r.l.",
        ust_id="DE814584193",
        kontakt_id=amazon.id,
    )
    vst = buchung(
        soll="4930",
        haben="70010",
        status=BuchungStatus.AUTO_GEBUCHT,
        beleg_id=rechnung.id,
    )
    anlegen(make_session, amazon, rechnung, vst)
    assert pruefe(make_session, "steuersatz_land") == []


def _rc_rechnung(brutto: str, **kw):
    return beleg(
        nummer="IE-1",
        lieferant="Google Ireland Ltd",
        netto=brutto,
        steuer="0.00",
        brutto=brutto,
        positionen=[("Ads", brutto, "0", "0.00")],
        **kw,
    )


def test_reverse_charge_ist_keine_kleinbetragsrechnung(make_session):
    """Befund B-M7: § 33 UStDV gilt nicht für § 13b — auch unter 250 € braucht die
    Rechnung die USt-IdNr. des Leistenden (§ 14a Abs. 1 UStG)."""
    rc = _rc_rechnung("50.00")
    b = buchung(
        soll="4610",
        haben="70020",
        netto="50.00",
        steuer=None,
        schluessel=94,
        status=BuchungStatus.AUTO_GEBUCHT,
        beleg_id=rc.id,
    )
    anlegen(make_session, rc, b)
    befund = next(
        x for x in pruefe(make_session, "pflichtangaben") if x.objekt_typ == "beleg"
    )
    assert "§ 33 UStDV" not in befund.text
    assert "§ 14a" in befund.text and "§ 13b" in befund.text


RC_TEXT = """Google Ireland Ltd · Gordon House · Barrow Street · Dublin 4 · Ireland
VAT: IE6388047V
Bill to: Galerie Muster GmbH, Beispielweg 3, 24103 Kiel
Invoice No. IE-1   Invoice date: 10.08.2026
Leistungszeitraum: 01.07.2026 - 31.07.2026
Google Ads, Juli 2026   50,00 EUR
Total 50,00 EUR  VAT 0 %
{zusatz}
"""


@pytest.mark.parametrize("vollstaendig", [False, True])
def test_reverse_charge_pflichtangaben_nach_14a(make_session, tmp_path, vollstaendig):
    """§ 14a Abs. 1 und 5 UStG: USt-IdNr. beider Seiten, Hinweis
    „Steuerschuldnerschaft des Leistungsempfängers“."""
    zusatz = (
        "USt-IdNr. Leistungsempfänger: DE999999999\n"
        "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)"
        if vollstaendig
        else ""
    )
    archiv, rc = _archiviert(
        make_session,
        tmp_path,
        RC_TEXT.format(zusatz=zusatz).encode(),
        nummer="IE-1",
        lieferant="Google Ireland Ltd",
        netto="50.00",
        steuer="0.00",
        brutto="50.00",
        positionen=[("Ads", "50.00", "0", "0.00")],
    )
    b = buchung(
        soll="4610",
        haben="70020",
        netto="50.00",
        steuer=None,
        schluessel=94,
        status=BuchungStatus.AUTO_GEBUCHT,
        beleg_id=rc.id,
    )
    anlegen(make_session, b)
    befunde = pruefe(make_session, "pflichtangaben", archiv=archiv)
    if vollstaendig:
        assert befunde == []
        return
    (befund,) = befunde
    assert befund.schwere is Schwere.WARNUNG
    assert "USt-IdNr. des Leistungsempfängers" in befund.text
    assert "Steuerschuldnerschaft des Leistungsempfängers" in befund.text


def test_ig_lieferung_braucht_ustid_und_hinweis(make_session, tmp_path):
    """§ 14a Abs. 3 UStG: Rechnung über eine ig. Lieferung (beim Erwerber: Schlüssel
    19) mit USt-IdNr. beider Seiten und Hinweis auf die Steuerbefreiung."""
    text = (
        "Papeterie SARL · 12 Rue de Rivoli · 75001 Paris\n"
        "TVA: FR12345678901\nFacture F-7 du 10.08.2026 · Papier 100,00 EUR\n"
        "Total HT 100,00 EUR  TVA 0 %\n"
    )
    archiv, fr = _archiviert(
        make_session,
        tmp_path,
        text.encode(),
        nummer="F-7",
        lieferant="Papeterie SARL",
        netto="100.00",
        steuer="0.00",
        brutto="100.00",
        positionen=[("Papier", "100.00", "0", "0.00")],
    )
    erwerb = buchung(
        soll="3425",
        haben="70002",
        schluessel=19,
        status=BuchungStatus.AUTO_GEBUCHT,
        beleg_id=fr.id,
    )
    anlegen(make_session, erwerb)
    (befund,) = pruefe(make_session, "pflichtangaben", archiv=archiv)
    assert "§ 33 UStDV" not in befund.text
    # Lieferer im Ausland: dessen Recht (Art. 226 MwStSystRL), nicht § 14a UStG
    assert "Art. 226 Nr. 4 MwStSystRL" in befund.text
    assert "§ 14a Abs. 3" not in befund.text
    assert "USt-IdNr. des Leistungsempfängers" in befund.text
    assert "steuerfreie innergemeinschaftliche Lieferung" in befund.text


# --- Automatikkonto ohne Schlüssel (Befund N-M3) ------------------------------------


def test_automatikkonto_ohne_schluessel_ist_eine_warnung(make_session, skr03):
    """DATEV rechnet auf einem AV/AM-Konto ohne Schlüssel selbst Steuer heraus."""
    anlegen(
        make_session, buchung(soll="3400", haben="1200", schluessel=None, steuer=None)
    )
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert befund.schwere is Schwere.WARNUNG
    assert "Automatikkonto" in befund.text and "40" in befund.text
    assert "--ohne-steuer" not in befund.abhilfe


def test_abhilfe_bietet_auf_automatikkonto_kein_ohne_steuer_an(make_session, skr03):
    """3400 (19 % automatisch) mit 7 % aus dem Beleg: das Konto ist falsch (3300),
    nicht die Steuer zu entfernen."""
    rb = beleg(
        steuer="7.00", brutto="107.00", positionen=[("Ware", "100.00", "7", "7.00")]
    )
    falsch = buchung(
        status=BuchungStatus.AUTO_GEBUCHT,
        soll="3400",
        haben="70001",
        steuer="7.00",
        schluessel=8,
        beleg_id=rb.id,
    )
    anlegen(make_session, rb, falsch)
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert "--ohne-steuer" not in befund.abhilfe
    assert "--steuer 8" in befund.abhilfe and "Automatik" in befund.abhilfe


def test_datev_export_hebt_die_automatik_auf(tmp_path, skr03):
    """DATEV 0907049 Kap. 3: Steuerschlüssel nur auf Konten ohne Automatik. Auf einem
    Automatikkonto bleibt das BU-Feld leer, wenn der Schlüssel der Automatik
    entspricht (DATEV rechnet selbst); ohne Steuer steht BU 40 („Aufhebung der
    Automatik“); ein abweichender Schlüssel wird vor dem Export gemeldet."""
    from accounti.export.datev import DATEVConfig, DATEVExporter
    from accounti.pruefung.regeln.richtigkeit import automatikkonten

    automatik = automatikkonten(Buchhaltung())
    assert automatik["3400"] == 9 and automatik["8400"] == 3 and "8125" not in automatik
    buchungen = [
        buchung(soll="3400", haben="1200", schluessel=None, steuer=None),
        buchung(soll="3400", haben="1200", schluessel=9),
        buchung(soll="10000", haben="8400", schluessel=3),
        buchung(soll="4900", haben="1200", schluessel=None, steuer=None),
        buchung(soll="4900", haben="1200", schluessel=9),
        buchung(soll="1400", haben="8125", schluessel=None, steuer=None),
        buchung(soll="3400", haben="70001", schluessel=8, steuer="7.00"),
    ]
    cfg = DATEVConfig(
        berater_nummer="1", mandanten_nummer="1", automatikkonten=automatik
    )
    exporter = DATEVExporter(cfg)
    datei = exporter.exportiere(buchungen, tmp_path / "out")
    zeilen = datei.read_text(encoding="cp1252").splitlines()
    bu = zeilen[1].split(";").index("BU-Schlüssel")
    assert [z.split(";")[bu] for z in zeilen[2:]] == ["40", "", "", "", "9", "", "8"]
    (warnung,) = exporter.warnungen
    assert "3400" in warnung and "Schlüssel 8" in warnung


def test_steuersatz_ohne_exponentenschreibweise(make_session):
    """Befund N-N2: 20 % und 10 % stehen nicht als „2E+1 %“ im Befund."""
    de20 = beleg(positionen=[("x", "100.00", "20", "20.00")], datei_hash="1" * 64)
    anlegen(make_session, de20)
    (befund,) = pruefe(make_session, "steuersatz_land")
    assert "Steuersatz 20 %" in befund.text and "E+" not in befund.text


def test_eigene_ustid_verdeckt_nicht_den_auslaendischen_lieferanten(make_session):
    """Befund N-N3: Hat die Erkennung die eigene USt-IdNr. als die des Lieferanten
    übernommen, zählt das Land des Kontakts."""
    fr = kontakt(name="Papeterie SARL", land="FR", kreditor_konto="70002")
    rechnung = beleg(kontakt_id=fr.id, ust_id="DE999999999", datei_hash="3" * 64)
    vst = buchung(
        soll="4930",
        haben="70002",
        status=BuchungStatus.AUTO_GEBUCHT,
        beleg_id=rechnung.id,
    )
    anlegen(make_session, fr, rechnung, vst)
    befunde = pruefe(make_session, "steuersatz_land")
    assert any(
        b.objekt_id == str(vst.id) and b.schwere is Schwere.FEHLER for b in befunde
    ), [b.text for b in befunde]


def test_reverse_charge_im_inland_zitiert_14a(make_session, tmp_path):
    """Befund N-N4: Inländischer Leistender (§ 13b Abs. 2, z.B. Bauleistung) —
    dann gilt § 14a Abs. 5 UStG."""
    bau = kontakt(name="Bau GmbH", land="DE", kreditor_konto="70005")
    text = (
        "Bau GmbH · Hauptstraße 1 · 20095 Hamburg\nSteuernummer: 12/345/67890\n"
        "Rechnung B-1 vom 10.08.2026 · Leistungsdatum: 05.08.2026\n"
        "Dachreparatur 300,00 EUR\n"
    )
    archiv, rb = _archiviert(
        make_session,
        tmp_path,
        text.encode(),
        nummer="B-1",
        lieferant="Bau GmbH",
        netto="300.00",
        steuer="0.00",
        brutto="300.00",
        positionen=[("Dach", "300.00", "0", "0.00")],
        kontakt_id=bau.id,
    )
    anlegen(
        make_session,
        bau,
        buchung(
            soll="4260",
            haben="70005",
            netto="300.00",
            steuer=None,
            schluessel=94,
            status=BuchungStatus.AUTO_GEBUCHT,
            beleg_id=rb.id,
        ),
    )
    (befund,) = pruefe(make_session, "pflichtangaben", archiv=archiv)
    assert "§ 14a Abs. 5 UStG" in befund.text and "Art. 226" not in befund.text


# --- Runde 3: Automatikkonto, ausführbare Abhilfe ------------------------------------


def test_automatikkonto_mit_steuerbetrag_ohne_schluessel(make_session, skr03):
    """Befund N-13: Steuer ohne Schlüssel — accounti meldet sie in der UStVA nicht,
    DATEV rechnet sie aus dem Bruttobetrag."""
    anlegen(make_session, buchung(soll="3400", haben="1200", schluessel=None))
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert befund.schwere is Schwere.FEHLER and "ohne Schlüssel" in befund.text


@pytest.mark.parametrize("mit_beleg", [False, True])
def test_abhilfe_automatikkonto_ohne_schluessel_ist_ausfuehrbar(
    make_session, skr03, tmp_path, mit_beleg
):
    """Befund N-10: Die Abhilfe lässt sich ausführen — ohne Beleg mit dem Schlüssel
    der Automatik, mit Beleg auf ein Konto ohne Automatik (Platzhalter <Konto>)."""
    import shlex

    from typer.testing import CliRunner

    from accounti.cli import app

    b = buchung(
        soll="3400",
        haben="1200",
        schluessel=None,
        steuer=None,
        status=BuchungStatus.ZUR_PRUEFUNG,
        beleg_id=uuid4() if mit_beleg else None,
    )
    anlegen(make_session, b)
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    aufruf = befund.abhilfe[befund.abhilfe.index("accounti korrigiere") :]
    args = shlex.split(aufruf.replace("<Konto>", "3200"))[1:]
    r = CliRunner().invoke(app, [*args, "--db", db_url(tmp_path)])
    assert r.exit_code == 0, (befund.abhilfe, r.output)
    assert pruefe(make_session, "steuerschluessel_konto") == []


def test_abhilfe_bei_13b_schlaegt_nicht_vorsteuer_entfernen_vor(make_session, skr03):
    """Schlussprüfung M-5: Schlüssel 94 (§ 13b) mit Beleg auf einem Erlöskonto — das
    Sachkonto ist falsch; „Vorsteuer entfernen“ wäre falsch, die Steuerschuld bliebe
    (§ 13b Abs. 5 UStG), der Vorsteuerabzug hängt nicht an der Rechnung."""
    rb = beleg()
    falsch = buchung(
        status=BuchungStatus.AUTO_GEBUCHT,
        soll="8000",
        haben="70001",
        steuer="19.00",
        schluessel=94,
        beleg_id=rb.id,
    )
    anlegen(make_session, rb, falsch)
    (befund,) = pruefe(make_session, "steuerschluessel_konto")
    assert "--ohne-steuer" not in befund.abhilfe
    assert "Vorsteuer entfernen" not in befund.abhilfe
    assert "--steuer 94" in befund.abhilfe


def test_datev_export_warnt_bei_steuer_ohne_schluessel_auf_automatikkonto(tmp_path):
    """Schlussprüfung N-5 (zu N-13): 3400 mit Steuerbetrag, aber ohne Schlüssel —
    das BU-Feld bleibt leer, DATEV rechnet die Steuer aus dem Betrag; accounti
    meldet sie nicht. Das sagt der Export vorab, nicht erst ``pruefen``."""
    from accounti.export.datev import DATEVConfig, DATEVExporter
    from accounti.pruefung.regeln.richtigkeit import automatikkonten

    cfg = DATEVConfig(
        berater_nummer="1",
        mandanten_nummer="1",
        automatikkonten=automatikkonten(Buchhaltung()),
    )
    exporter = DATEVExporter(cfg)
    exporter.exportiere(
        [buchung(soll="3400", haben="1200", schluessel=None, steuer="19.00")],
        tmp_path / "out",
    )
    (warnung,) = exporter.warnungen
    assert "3400" in warnung and "ohne Schlüssel" in warnung and "--steuer 9" in warnung


def test_personenkonto_op(make_session):
    """B05 (Gesamttest): Rechnung netto auf den Kreditor gebucht, Posten brutto —
    Hauptbuch und Offene-Posten-Liste weichen ab. Stimmige Konten und ein Guthaben aus
    einer Überzahlung sind kein Befund."""
    falsch = kontakt(name="Druckerei Beispiel GmbH", kreditor_konto="70002")
    richtig = kontakt(kreditor_konto="70001")
    guthaben = kontakt(name="Überzahlt GmbH", kreditor_konto="70003")
    tag = date(2026, 3, 10)
    belege = {k.kreditor_konto: uuid4() for k in (falsch, richtig, guthaben)}

    def rechnung(konto, netto, steuer):
        return buchung(
            haben=konto,
            netto=netto,
            steuer=steuer,
            schluessel=9 if steuer else None,
            beleg_id=belege[konto],
            tag=tag,
        )

    zahlung = umsatz("-130.00", tag=date(2026, 3, 20), zweck="RE-3")
    anlegen(
        make_session,
        falsch,
        richtig,
        guthaben,
        zahlung,
        rechnung("70002", "1000.00", None),
        rechnung("70001", "100.00", "19.00"),
        rechnung("70003", "100.00", "19.00"),
        buchung(
            zahlung,
            soll="70003",
            haben="1200",
            netto="130.00",
            steuer=None,
            schluessel=None,
            beleg_id=belege["70003"],
        ),
    )
    posten = [
        _posten(falsch, beleg_id=belege["70002"], betrag=Decimal("1190.00")),
        _posten(richtig, beleg_id=belege["70001"], belegnummer="RE-2"),
        _posten(
            guthaben,
            beleg_id=belege["70003"],
            belegnummer="RE-3",
            restbetrag=Decimal("0"),
            status=PostenStatus.AUSGEGLICHEN,
        ),
    ]
    with make_session() as s:
        for p in posten:
            speichere_posten(s, p)
        speichere_zuordnung(
            s,
            Zahlungszuordnung(
                transaktion_id=zahlung.id,
                posten_id=posten[2].id,
                betrag=Decimal("130.00"),
                stufe="referenz",
                status=ZuordnungStatus.GEBUCHT,
                confidence=1.0,
                begruendung="RE-3",
            ),
        )
        s.commit()
    (b,) = pruefe(make_session, "personenkonto_op")
    assert b.objekt_id == str(falsch.id)
    assert b.betrag == Decimal("-190.00")
    assert "70002" in b.text and "1.000,00" in b.text and "1.190,00" in b.text
    # vor der Rechnung (Stichtag) gibt es nichts abzustimmen
    assert pruefe(make_session, "personenkonto_op", period="2026-02") == []
