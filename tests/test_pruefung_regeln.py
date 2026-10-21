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
    """config/skr03.yaml des Projekts, relativ zum Arbeitsverzeichnis wie in der CLI."""
    (tmp_path / "config").mkdir(exist_ok=True)
    quelle = Path(__file__).resolve().parents[1] / "config" / "skr03.yaml"
    (tmp_path / "config" / "skr03.yaml").write_bytes(quelle.read_bytes())
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
