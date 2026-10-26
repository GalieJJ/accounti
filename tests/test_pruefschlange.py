"""Prüfschlange: Reihenfolge, Ansichten, Herkunft, Stand unter der Schreibsperre,
Aktionen über Baustein 7 (Baustein 10b, Paket 1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from accounti.aufgaben import aufgaben_zu, melde_aufgabe
from accounti.belege.zuordnung import beleg_zur_buchung
from accounti.buchung.pruefschlange import (
    Aenderung,
    Ansicht,
    LernWunsch,
    NichtInPruefungError,
    PruefschlangeError,
    RegelBestaetigenError,
    SchonZurueckgestelltError,
    StandVeraltetError,
    freigeben,
    herkunft,
    korrigieren,
    lade_eintrag,
    lade_pruefschlange,
    naechster,
    position,
    stand,
    zurueckstellen,
)
from accounti.db.repo_kontierung import (
    lade_kontierungsregeln,
    speichere_kontierungsgrund,
)
from accounti.db.repo_pruefung import lade_korrekturen
from accounti.db.repository import (
    finde_buchung,
    lade_buchungen,
    speichere_abgleich,
    speichere_posten,
    speichere_zuordnung,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Belegabgleich,
    BuchungStatus,
    OffenerPosten,
    PostenRichtung,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.models.aufgaben import AufgabenStatus, Objekt
from accounti.pruefung.journal import lade_journal
from accounti.pruefung.storno import (
    Korrekturumgebung,
    StornoError,
    lade_korrekturumgebung,
)
from tests.pg_hilfe import mit_postgresql
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    kontakt,
    make_session_fixture,
    umsatz,
)

BH = Buchhaltung()


def umgebung(tmp_path=None, text_: str = "") -> Korrekturumgebung:  # noqa: ANN001
    if tmp_path is None:
        from accounti.abschluss.kontenrahmen import lade_kontenrahmen
        from accounti.pruefung.einstellungen import PruefEinstellungen

        return Korrekturumgebung(lade_kontenrahmen(), BH, PruefEinstellungen())
    pfad = tmp_path / "gesellschaft.yaml"
    pfad.write_text(text_, encoding="utf-8")
    return lade_korrekturumgebung(pfad)


def _drei(make_session):  # noqa: ANN001, ANN202
    a = buchung(tag=date(2026, 8, 3))
    b = buchung(tag=date(2026, 8, 1))
    c = buchung(tag=date(2026, 8, 3))
    fertig = buchung(tag=date(2026, 8, 2), status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, a, b, c, fertig)
    return sorted([a, c], key=lambda x: str(x.id)), b


def test_reihenfolge_stabil(make_session):
    (a, c), b = _drei(make_session)
    with make_session() as s:
        seite = lade_pruefschlange(s)
        ids = [e.buchung.id for e in seite.eintraege]
        assert ids == [b.id, a.id, c.id]
        assert [e.buchung.id for e in lade_pruefschlange(s).eintraege] == ids
        p = position(s, a.id)
        assert (p.nr, p.gesamt, p.vorher, p.nachher) == (2, 3, b.id, c.id)
        assert naechster(s, finde_buchung(s, str(c.id))) == b.id  # wieder vorn
        assert naechster(s, finde_buchung(s, str(b.id))) == a.id


def test_liste_seitenweise(make_session, monkeypatch):
    from accounti.buchung import pruefschlange

    monkeypatch.setattr(pruefschlange, "JE_SEITE", 2)
    (a, c), b = _drei(make_session)
    with make_session() as s:
        eins, zwei = lade_pruefschlange(s, seite=1), lade_pruefschlange(s, seite=2)
        zu_weit = lade_pruefschlange(s, seite=9)
    assert (eins.seiten, eins.gesamt) == (2, 3)
    assert [e.buchung.id for e in zwei.eintraege] == [c.id]
    assert zu_weit.seite == 2


def test_ansichten_offen_und_zurueckgestellt(make_session):
    (a, c), b = _drei(make_session)
    with make_session() as s:
        zurueckstellen(s, a.id, "Wofür war das?", "jan")
        s.commit()
    with make_session() as s:
        offen = lade_pruefschlange(s)
        zurueck = lade_pruefschlange(s, Ansicht.ZURUECKGESTELLT)
    assert [e.buchung.id for e in offen.eintraege] == [b.id, c.id]
    assert [e.buchung.id for e in zurueck.eintraege] == [a.id]
    assert zurueck.eintraege[0].zurueckgestellt
    assert (offen.offen, offen.zurueckgestellt) == (2, 1)


def test_beleg_zur_buchung_direkt_abgleich_posten_keiner(make_session):
    k = kontakt()
    direkt_beleg = beleg(datei_hash="1" * 64, nummer="RE-1")
    abgleich_beleg = beleg(datei_hash="2" * 64, nummer="RE-2")
    posten_beleg = beleg(datei_hash="3" * 64, nummer="RE-3")
    tx_abgleich, tx_posten, tx_ohne = umsatz(), umsatz(), umsatz()
    direkt = buchung(beleg_id=direkt_beleg.id)
    ueber_abgleich = buchung(tx_abgleich)
    ueber_posten = buchung(tx_posten)
    ohne = buchung(tx_ohne)
    anlegen(
        make_session,
        k,
        direkt_beleg,
        abgleich_beleg,
        posten_beleg,
        tx_abgleich,
        tx_posten,
        tx_ohne,
        direkt,
        ueber_abgleich,
        ueber_posten,
        ohne,
    )
    with make_session() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx_abgleich.id,
                beleg_id=abgleich_beleg.id,
                stufe="referenz",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Nummer im Zweck",
            ),
        )
        p = OffenerPosten(
            kontakt_id=k.id,
            beleg_id=posten_beleg.id,
            richtung=PostenRichtung.VERBINDLICHKEIT,
            belegnummer="RE-3",
            belegdatum=date(2026, 8, 1),
            betrag=Decimal("119.00"),
            restbetrag=Decimal("0"),
            faellig_am=date(2026, 8, 15),
        )
        speichere_posten(s, p)
        s.flush()
        speichere_zuordnung(
            s,
            Zahlungszuordnung(
                transaktion_id=tx_posten.id,
                posten_id=p.id,
                betrag=Decimal("119.00"),
                stufe="referenz",
                status=ZuordnungStatus.GEBUCHT,
                confidence=1.0,
                begruendung="RE-3",
            ),
        )
        s.commit()
        assert beleg_zur_buchung(s, direkt).id == direkt_beleg.id  # type: ignore[union-attr]
        assert beleg_zur_buchung(s, ueber_abgleich).id == abgleich_beleg.id  # type: ignore[union-attr]
        assert beleg_zur_buchung(s, ueber_posten).id == posten_beleg.id  # type: ignore[union-attr]
        assert beleg_zur_buchung(s, ohne) is None


QUELLEN = ["regelwerk", "llm", "beleg", "kontakt", "standard", "opos"]
QUELLEN += ["kreditkarte", "anlagen", "marktplatz"]


@pytest.mark.parametrize("quelle", QUELLEN)
def test_herkunft_fuer_jede_gespeicherte_quelle(make_session, quelle):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        speichere_kontierungsgrund(
            s, b.id, quelle=quelle, regel="r1", modell="m", begruendung="weil"
        )
        s.commit()
        h = herkunft(s, b)
    assert (h.quelle, h.text, h.regel, h.gespeichert) == (quelle, "weil", "r1", True)


def test_herkunft_ohne_zeile_abgeleitet(make_session, tmp_path):
    """Altbuchungen, AfA über ``AfaVorgang``, Neubuchung und Storno über
    ``buchungskorrekturen``, bestätigter Abgleich, Belegprüfgrund."""
    from accounti.db.repo_anlagen import speichere_afa_vorgang
    from accounti.models.anlagen import AfaVorgang
    from accounti.pruefung.storno import korrigiere

    alt = buchung()
    afa = buchung(soll="4830", haben="0420", schluessel=None, steuer=None)
    frei = buchung(status=BuchungStatus.GEPRUEFT, soll="4900")
    tx = umsatz()
    abgeglichen = buchung(tx)
    b_pruef = beleg(datei_hash="7" * 64, pruef_grund="Steuernummer fehlt")
    mit_beleg = buchung(beleg_id=b_pruef.id)
    anlegen(make_session, alt, afa, frei, tx, abgeglichen, b_pruef, mit_beleg)
    with make_session() as s:
        speichere_afa_vorgang(
            s,
            AfaVorgang(
                objekt="1",
                jahr=2026,
                bis_monat=12,
                betrag=Decimal("100"),
                buchung_id=afa.id,
                begruendung="Gut 3600: linear 3 Jahre",
            ),
        )
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=b_pruef.id,
                stufe="exakt",
                status=AbgleichStatus.BESTAETIGT,
                confidence=0.9,
                begruendung="Betrag und Datum passen",
            ),
        )
        k = korrigiere(
            s, str(frei.id), "4930", "1200", steuer=9, von="jan", grund="Bürobedarf"
        )
        s.commit()
        assert herkunft(s, alt).quelle is None and not herkunft(s, alt).bekannt
        assert herkunft(s, afa).text == "Gut 3600: linear 3 Jahre"
        assert herkunft(s, abgeglichen).text == "Betrag und Datum passen"
        assert herkunft(s, mit_beleg).text == "Steuernummer fehlt"
        assert k.neu is not None and k.storno is not None
        neu, storno = herkunft(s, k.neu), herkunft(s, k.storno)
    assert (neu.quelle, neu.text) == ("korrektur", "jan: Bürobedarf")
    assert storno.quelle == "storno"


def test_regelangebot_nur_fuer_kontierungsvorschlaege(make_session):
    faelle = {}
    for quelle in QUELLEN:
        tx = umsatz()
        b = buchung(tx)
        anlegen(make_session, tx, b)
        with make_session() as s:
            speichere_kontierungsgrund(s, b.id, quelle=quelle, begruendung="x")
            s.commit()
            faelle[quelle] = lade_eintrag(s, b.id).regel_moeglich
    assert {q for q, ja in faelle.items() if ja} == {"regelwerk", "llm", "standard"}
    ohne_umsatz = buchung()
    anlegen(make_session, ohne_umsatz)
    with make_session() as s:
        speichere_kontierungsgrund(s, ohne_umsatz.id, quelle="llm", begruendung="x")
        s.commit()
        assert not lade_eintrag(s, ohne_umsatz.id).regel_moeglich


@pytest.mark.parametrize(
    ("spalte", "wert"),
    [
        ("beleg_id", "'b-1'"),
        ("datum", "'2026-08-13'"),
        ("buchungstext", "'anders'"),
        ("storniert_durch", "'s-1'"),
        ("soll_konto", "'4930'"),
        ("confidence", "0.7"),
        ("steuer_betrag", "18.99"),
    ],
)
def test_stand_aendert_sich_mit_jeder_spalte(make_session, spalte, wert):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        vorher = stand(s, b.id)
        s.execute(text(f"UPDATE buchungssaetze SET {spalte} = {wert}"))
        s.commit()
        assert stand(s, b.id) != vorher
        assert len(vorher) == 16


def test_stand_unter_der_schreibsperre(make_session):
    """Zweite Sitzung ändert zwischen Laden und Freigeben → 409, nichts geändert."""
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        gesehen = lade_eintrag(s, b.id).stand
    with make_session() as zweite:  # jemand anderes ändert den Vorschlag
        zweite.execute(text("UPDATE buchungssaetze SET soll_konto = '4980'"))
        zweite.commit()
    with make_session() as s:
        with pytest.raises(StandVeraltetError) as info:
            freigeben(s, b.id, "jan", gesehen)
        s.rollback()
        assert info.value.stand == stand(s, b.id) != gesehen
        b_jetzt = finde_buchung(s, str(b.id))
        assert (
            b_jetzt.status is BuchungStatus.ZUR_PRUEFUNG
            and b_jetzt.geprueft_von is None
        )


def test_freigeben_mit_veraltetem_stand_scheitert(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        with pytest.raises(StandVeraltetError):
            freigeben(s, b.id, "jan", "0" * 16)
        s.rollback()
        neu, geaendert = freigeben(s, b.id, "jan", stand(s, b.id))
        s.commit()
    assert (
        geaendert and neu.status is BuchungStatus.GEPRUEFT and neu.geprueft_von == "jan"
    )


def test_korrektur_mit_veraltetem_stand_storniert_nicht(make_session):
    """Ein inzwischen freigegebener Vorschlag und ein Doppelklick „Korrigieren“:
    kein Storno."""
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        gesehen = stand(s, b.id)
        freigeben(s, b.id, "eva", gesehen)
        s.commit()
    with make_session() as s:
        for nur in (True, False):
            with pytest.raises((StandVeraltetError, NichtInPruefungError)):
                korrigieren(
                    s,
                    b.id,
                    Aenderung("4930", "1200", steuer=9),
                    "jan",
                    gesehen,
                    umgebung(),
                    nur_vorschlaege=nur,
                )
            s.rollback()
        assert len(lade_buchungen(s)) == 1
        assert lade_korrekturen(s) == []


def test_nur_vorschlaege(make_session):
    """Freigegebene oder ``auto``-Buchung über die Queue-Wege → 409, kein Storno."""
    for status in (BuchungStatus.GEPRUEFT, BuchungStatus.AUTO_GEBUCHT):
        b = buchung(status=status)
        anlegen(make_session, b)
        with make_session() as s:
            aktuell = stand(s, b.id)
            with pytest.raises(NichtInPruefungError):
                freigeben(s, b.id, "jan", aktuell)
            with pytest.raises(NichtInPruefungError):
                korrigieren(
                    s,
                    b.id,
                    Aenderung("4930", "1200", steuer=9),
                    "jan",
                    aktuell,
                    umgebung(),
                )
            with pytest.raises(NichtInPruefungError):
                zurueckstellen(s, b.id, "?", "jan")
            s.rollback()
            assert len(lade_buchungen(s)) == 1 + (status is BuchungStatus.AUTO_GEBUCHT)


def test_entscheidung_schliesst_rueckfrage_und_kontierung_pruefen(make_session):
    erste, zweite = buchung(), buchung()
    anlegen(make_session, erste, zweite)
    with make_session() as s:
        for b in (erste, zweite):
            melde_aufgabe(
                s,
                "kontierung_pruefen",
                Objekt("buchung", b.id),
                "Kontierung prüfen",
                erzeugt_von="aufgaben",
            )
        zurueckstellen(s, erste.id, "Wofür?", "jan")
        s.commit()
    with make_session() as s:
        freigeben(s, erste.id, "jan", stand(s, erste.id))
        korrigieren(
            s,
            zweite.id,
            Aenderung("4900", "1200"),
            "jan",
            stand(s, zweite.id),
            umgebung(),
        )
        s.commit()
        for b in (erste, zweite):
            aufgaben = aufgaben_zu(s, Objekt("buchung", b.id))
            assert aufgaben and all(
                a.status is AufgabenStatus.HINFAELLIG for a in aufgaben
            ), [(a.art, a.status) for a in aufgaben]
            assert all("jan" in (a.abschluss_grund or "") for a in aufgaben)


def test_zurueckstellen_legt_rueckfrage_als_aufgabe_an(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        stand_vorher = stand(s, b.id)
        r = zurueckstellen(s, b.id, "  Wofür war das?  ", "jan", an="eva")
        s.commit()
        e = lade_eintrag(s, b.id)
    assert r.aufgabe is not None and r.aufgabe.zustaendig == "eva"
    assert e.zurueckgestellt and e.stand == stand_vorher  # Stand bleibt
    assert [k.text for k in e.rueckfragen] == ["Wofür war das?"]
    assert e.buchung.status is BuchungStatus.ZUR_PRUEFUNG
    with make_session() as s, pytest.raises(PruefschlangeError) as info:
        zurueckstellen(s, b.id, " ", "jan")
    assert info.value.feld == "text"


def test_zurueckstellen_zweimal_fehler(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        zurueckstellen(s, b.id, "Wofür?", "jan")
        s.commit()
        with pytest.raises(SchonZurueckgestelltError):
            zurueckstellen(s, b.id, "Noch einmal", "eva")


def test_person_ist_der_uebergebene_benutzer(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "mallory")
    monkeypatch.setattr("getpass.getuser", lambda: "mallory")
    tx = umsatz()
    vorschlag = buchung(tx)
    frei = buchung(status=BuchungStatus.GEPRUEFT)
    dritte, vierte = buchung(), buchung()
    anlegen(make_session, tx, vorschlag, frei, dritte, vierte)
    with make_session() as s:
        vorher = s.execute(text("SELECT max(nr) FROM journal")).scalar()
        speichere_kontierungsgrund(s, vorschlag.id, quelle="llm", begruendung="x")
        freigeben(s, dritte.id, "jan", stand(s, dritte.id))
        ergebnis = korrigieren(
            s,
            vorschlag.id,
            Aenderung("4930", "1200", steuer=9),
            "jan",
            stand(s, vorschlag.id),
            umgebung(),
            lernen=LernWunsch(),
        )
        korrigieren(
            s,
            frei.id,
            Aenderung("4930", "1200", steuer=9),
            "jan",
            stand(s, frei.id),
            umgebung(),
            nur_vorschlaege=False,
        )
        r = zurueckstellen(s, vierte.id, "Wofür?", "jan")
        s.commit()
        personen = set(
            s.execute(
                text("SELECT person FROM journal WHERE nr > :n"), {"n": vorher}
            ).scalars()
        )
        geprueft = set(
            s.execute(text("SELECT geprueft_von FROM buchungssaetze")).scalars()
        )
        (korrektur,) = lade_korrekturen(s)
    assert ergebnis.regel is not None and ergebnis.regel.angelegt_von == "jan"
    assert personen == {"jan"}
    assert geprueft - {None} == {"jan"}
    assert korrektur.person == "jan"
    assert r.kommentar.autor == "jan" and r.aufgabe is not None
    assert r.aufgabe.erzeugt_von == "jan"


def test_umgebung_der_gesellschaft(make_session, tmp_path):
    """SKR04 mit Bank 1800 und eigener Kontenrahmen-Datei: Umkehrbarkeit, Steuerkonto
    und Automatikprüfung kommen aus der Gesellschaft, nicht aus den SKR03-Vorgaben."""
    datei = tmp_path / "konten.yaml"
    datei.write_text(
        "konten:\n  '6815':\n    name: Bürobedarf\n    typ: aufwand\n"
        "    steuer: {schluessel: 9, automatik: true}\n",
        encoding="utf-8",
    )
    u = umgebung(
        tmp_path,
        "buchhaltung:\n  kontenrahmen: SKR04\n  bank_konto: '1800'\n"
        f"pruefung:\n  kontenrahmen_datei: '{datei}'\n",
    )
    frei = buchung(status=BuchungStatus.GEPRUEFT, soll="6800", haben="1800")
    vorschlag = buchung(soll="6800", haben="1800", schluessel=None, steuer=None)
    anlegen(make_session, frei, vorschlag)
    with make_session() as s:
        with pytest.raises(StornoError, match="dieselbe Natur"):  # SKR03: 1800 privat
            korrigieren(
                s,
                frei.id,
                Aenderung("6805", "1800", steuer=9),
                "jan",
                None,
                umgebung(),
                nur_vorschlaege=False,
            )
        s.rollback()
        e = korrigieren(
            s,
            frei.id,
            Aenderung("6805", "1800", steuer=9),
            "jan",
            None,
            u,
            nur_vorschlaege=False,
        )
        assert e.korrektur.storno is not None
        with pytest.raises(StornoError, match="Automatikkonto"):
            korrigieren(s, vorschlag.id, Aenderung("6815", "1800"), "jan", None, u)
        s.rollback()


def test_sperre_im_eintrag(make_session):
    b = buchung(tag=date(2025, 12, 30))
    anlegen(make_session, b)
    with make_session() as s:
        s.execute(
            text(
                "INSERT INTO abschluesse VALUES "
                "(2025, 1, 'euer', 0, '2026-03-01 10:00:00.000000', 'chef')"
            )
        )
        s.commit()
        e = lade_eintrag(s, b.id)
    assert e.sperre is not None and (e.sperre.art, e.sperre.zeitraum) == (
        "jahr",
        "2025",
    )


def test_belegnachforderung_und_belegfrei_im_eintrag(make_session):
    from accounti.pruefung.einstellungen import PruefEinstellungen

    gebuehr = umsatz("-4.90", zweck="Kontoführung 09/2026", name="Sparkasse")
    strom = umsatz("-119.00")
    b_gebuehr, b_strom = buchung(gebuehr), buchung(strom)
    anlegen(make_session, gebuehr, strom, b_gebuehr, b_strom)
    einst = PruefEinstellungen.model_validate(
        {
            "belegfrei": [
                {
                    "name": "kontofuehrung",
                    "muster": "kontoführung",
                    "feld": "verwendungszweck",
                    "begruendung": "Bankentgelt — der Auszug ist Beleg",
                }
            ]
        }
    )
    with make_session() as s:
        melde_aufgabe(
            s,
            "beleg_fehlt",
            Objekt("transaktion", strom.id),
            "Beleg fehlt",
            erzeugt_von="pruefung",
            zustaendig="eva",
            faellig_am=date(2026, 9, 1),
        )
        s.commit()
        frei = lade_eintrag(s, b_gebuehr.id, pruefung=einst)
        fehlt = lade_eintrag(s, b_strom.id, pruefung=einst)
    assert frei.belegfrei is not None and frei.belegfrei.name == "kontofuehrung"
    assert frei.nachforderung == []
    assert fehlt.belegfrei is None
    (a,) = fehlt.nachforderung
    assert a.zustaendig == "eva" and a.faellig_am == date(2026, 9, 1)


def test_kontonummer_geprueft(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        for soll, haben, feld in (("49x0", "1200", "soll"), ("4930", "12", "haben")):
            with pytest.raises(PruefschlangeError) as info:
                korrigieren(s, b.id, Aenderung(soll, haben), "jan", None, umgebung())
            assert info.value.feld == feld and info.value.status == 422


def test_regel_aus_der_queue_nur_mit_angebot(make_session):
    tx = umsatz()
    b = buchung(tx)
    anlegen(make_session, tx, b)
    with make_session() as s:
        speichere_kontierungsgrund(s, b.id, quelle="kreditkarte", begruendung="x")
        s.commit()
        with pytest.raises(PruefschlangeError, match="keine Regel"):
            korrigieren(
                s,
                b.id,
                Aenderung("4930", "1200", steuer=9),
                "jan",
                None,
                umgebung(),
                lernen=LernWunsch(),
            )


def test_korrektur_behaelt_das_finanzkonto(make_session):
    """Nachbesserung M1: Eine Buchung zu einem Bankumsatz behält dessen Finanzkonto
    auf der Seite seiner Zahlungsrichtung — sonst stimmt der Bankbestand der Bücher
    nicht mehr mit dem Kontoauszug (und eine Regel lernte das falsche Geldkonto)."""
    tx = umsatz()  # Ausgabe auf 1200
    b = buchung(tx)
    karte = umsatz(sachkonto="1210")
    kb = buchung(karte, haben="1210")
    anlegen(make_session, tx, b, karte, kb)
    with make_session() as s:
        for soll, haben in (("4930", "4980"), ("4930", "1000"), ("4930", "1210")):
            with pytest.raises(PruefschlangeError, match="Finanzkonto 1200") as info:
                korrigieren(
                    s, b.id, Aenderung(soll, haben, steuer=9), "jan", None, umgebung()
                )
            assert info.value.feld == "haben" and info.value.status == 422
            s.rollback()
        with pytest.raises(PruefschlangeError, match="Finanzkonto 1210"):
            korrigieren(
                s, kb.id, Aenderung("4930", "1200", steuer=9), "jan", None, umgebung()
            )
        s.rollback()
        assert finde_buchung(s, str(b.id)).status is BuchungStatus.ZUR_PRUEFUNG
        k = korrigieren(
            s, b.id, Aenderung("4930", "1200", steuer=9), "jan", None, umgebung()
        )
        s.commit()
    assert k.korrektur.neu is not None and k.korrektur.neu.haben_konto == "1200"


def test_erstattung_auf_der_falschen_seite_laesst_sich_richtigstellen(make_session):
    """Eine Gutschrift, die eine Altregel ohne Richtung als Abgang gebucht hat
    (4920 an 1200), wird zu 1200 an 4920 korrigiert — die falsche Seite behalten
    geht nicht."""
    tx = umsatz("25.00", zweck="Gutschrift Telekom", name="Deutsche Telekom AG")
    b = buchung(tx, soll="4920", haben="1200")
    anlegen(make_session, tx, b)
    with make_session() as s:
        with pytest.raises(PruefschlangeError, match="im Soll") as info:
            korrigieren(
                s, b.id, Aenderung("4920", "1200", steuer=9), "jan", None, umgebung()
            )
        assert info.value.feld == "soll"
        s.rollback()
        k = korrigieren(s, b.id, Aenderung("1200", "4920"), "jan", None, umgebung())
        s.commit()
    assert k.korrektur.neu is not None and k.korrektur.neu.soll_konto == "1200"


def test_lernen_nur_aus_kontierungsvorschlaegen_auch_ausserhalb_der_queue(
    make_session,
):
    """Nachbesserung M6: Auch der CLI-Weg (``nur_vorschlaege=False``) lernt nicht aus
    Kreditkarte, Anlagen, Marktplatz oder OPOS; Altbuchungen ohne gespeicherte
    Herkunft nur mit ``unbekannte_herkunft_lernbar`` (CLI)."""
    for quelle in ("kreditkarte", "anlagen", "marktplatz", "opos"):
        tx = umsatz(name="VISA Sammelbelastung")
        b = buchung(tx, status=BuchungStatus.GEPRUEFT)
        anlegen(make_session, tx, b)
        with make_session() as s:
            speichere_kontierungsgrund(s, b.id, quelle=quelle, begruendung="x")
            s.commit()
            with pytest.raises(PruefschlangeError, match="keine Regel"):
                korrigieren(
                    s, b.id, Aenderung("4930", "1200", steuer=9), "jan", None,
                    umgebung(), lernen=LernWunsch(), nur_vorschlaege=False,
                    unbekannte_herkunft_lernbar=True,
                )  # fmt: skip
            s.rollback()
            assert lade_kontierungsregeln(s) == []
    alt_tx = umsatz(name="Stadtwerke Hamburg")
    alt = buchung(alt_tx, status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, alt_tx, alt)
    with make_session() as s:
        with pytest.raises(PruefschlangeError, match="keine Regel"):
            korrigieren(
                s, alt.id, Aenderung("4930", "1200", steuer=9), "jan", None,
                umgebung(), lernen=LernWunsch(), nur_vorschlaege=False,
            )  # fmt: skip
        s.rollback()
        e = korrigieren(
            s, alt.id, Aenderung("4930", "1200", steuer=9), "jan", None, umgebung(),
            lernen=LernWunsch(), nur_vorschlaege=False,
            unbekannte_herkunft_lernbar=True,
        )  # fmt: skip
        s.commit()
    assert e.regel is not None and e.regel.muster == "Stadtwerke Hamburg"


def test_regel_auf_fremde_gegenparteien_nur_mit_bestaetigung(make_session):
    """Nachbesserung H1: Trifft das Muster andere Gegenparteien, wird die Regel nicht
    still gespeichert — weder Korrektur noch Regel, bis die Warnung bestätigt ist."""
    tx = umsatz("-39.95", zweck="Mobilfunk 10/2026", name="Deutsche Telekom AG")
    bahn = umsatz("-80.00", zweck="Fahrkarte", name="Deutsche Bahn AG")
    b = buchung(tx, soll="4980")
    anlegen(make_session, tx, bahn, b)
    aenderung = Aenderung("4920", "1200", steuer=9)
    with make_session() as s:
        speichere_kontierungsgrund(s, b.id, quelle="llm", begruendung="x")
        s.commit()
        with pytest.raises(RegelBestaetigenError) as info:
            korrigieren(
                s, b.id, aenderung, "jan", None, umgebung(),
                lernen=LernWunsch(muster="Deutsche"),
            )  # fmt: skip
        assert info.value.feld == "muster" and info.value.status == 422
        assert info.value.vorschau.fremde == ["Deutsche Bahn AG"]
        assert "andere Gegenparteien" in info.value.meldung
        s.rollback()
        assert lade_kontierungsregeln(s) == []
        assert finde_buchung(s, str(b.id)).soll_konto == "4980"
        e = korrigieren(
            s, b.id, aenderung, "jan", None, umgebung(),
            lernen=LernWunsch(muster="Deutsche", bestaetigt=True),
        )  # fmt: skip
        s.commit()
    assert e.regel is not None and e.regel.muster == "Deutsche"


def test_journal_nach_queue_aktionen_in_ordnung(make_session):
    from accounti.pruefung.journal import pruefe_journal

    tx = umsatz(name="Bürobedarf Müller GmbH")
    b = buchung(tx, soll="4980")
    anlegen(make_session, tx, b)
    with make_session() as s:
        speichere_kontierungsgrund(s, b.id, quelle="llm", begruendung="x")
        korrigieren(
            s,
            b.id,
            Aenderung("4930", "1200", steuer=9),
            "jan",
            stand(s, b.id),
            umgebung(),
            lernen=LernWunsch(muster="Müller"),
        )
        s.commit()
        assert pruefe_journal(s).in_ordnung
        vorgaenge = [e.vorgang for e in lade_journal(s)]
    assert "regel_gelernt" in vorgaenge and "buchung_korrigiert" in vorgaenge


def _unbenutzt() -> None:  # pragma: no cover
    uuid4, datetime  # noqa: B018


@mit_postgresql
def test_stand_und_aktionen_unter_postgresql(pg_datenbank):
    """Schreibsperre (Advisory-Lock) vor dem Vergleich, Freigabe, Korrektur mit Regel
    und Rückfrage — unter PostgreSQL."""
    from accounti.db import init_db, session_factory

    engine, fabrik = session_factory(pg_datenbank())
    init_db(engine)
    tx = umsatz(name="Bürobedarf Müller GmbH")
    erste, zweite, dritte = buchung(tx), buchung(), buchung()
    anlegen(fabrik, tx, erste, zweite, dritte)
    with fabrik() as s:
        speichere_kontierungsgrund(s, erste.id, quelle="llm", begruendung="x")
        gesehen = stand(s, zweite.id)
        s.commit()
    with fabrik() as anderer:  # ein anderer Schreiber ändert den Vorschlag (ORM)
        from accounti.db.repository import aktualisiere_buchung

        aktualisiere_buchung(
            anderer, str(zweite.id), zweite.model_copy(update={"buchungstext": "neu"})
        )
        anderer.commit()
    with fabrik() as s:
        with pytest.raises(StandVeraltetError):
            freigeben(s, zweite.id, "jan", gesehen)
        s.rollback()
        freigeben(s, zweite.id, "jan", stand(s, zweite.id))
        e = korrigieren(
            s,
            erste.id,
            Aenderung("4930", "1200", steuer=9),
            "jan",
            stand(s, erste.id),
            umgebung(),
            lernen=LernWunsch(muster="Müller"),
        )
        zurueckstellen(s, dritte.id, "Wofür?", "jan")
        s.commit()
    assert e.regel is not None and e.regel.richtung is not None
    with fabrik() as s:
        from accounti.pruefung.journal import pruefe_journal

        assert pruefe_journal(s).in_ordnung
        assert [x.buchung.id for x in lade_pruefschlange(s).eintraege] == []
    engine.dispose()
