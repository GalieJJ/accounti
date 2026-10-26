"""Gutschrift (381) und Rechnungskorrektur (384) mit Bezug auf die Rechnung (BT-25).

Gesamttest Ausgang B3: Eine Minderung des Entgelts (§ 17 Abs. 1 UStG) bezieht sich
eindeutig auf die ursprüngliche Rechnung — in der E-Rechnung Typ 381/384 mit BT-25/26.
Beim Verbuchen wird die Gutschrift mit der noch offenen Rechnung verrechnet.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    lade_posten,
    speichere_ausgangsrechnung,
)
from accounti.erechnung import lies
from accounti.erechnung.abbildung import zu_beleg
from accounti.erechnung.ausstellung import AusstellungError, stelle_aus
from accounti.erechnung.erzeuger.aufbau import baue_rechnung
from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.kosit import KositPruefer
from accounti.erechnung.mustang import MustangPruefer
from accounti.models import Beleg, PostenStatus
from tests.test_cli_rechnung import FIRMA_YAML
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos

D = Decimal
URSPRUNG = date(2026, 3, 2)
runner = CliRunner()


def _korrektur(typ="381", *positionen, **kw):
    return entwurf(
        kunde(),
        *(positionen or [pos("Minderung wegen Mangel", "100")]),
        rechnungstyp=typ,
        korrektur_zu="2026-0001",
        **kw,
    )


def _bau(e, nummer="2026-0002"):
    return baue_rechnung(e, FIRMA, nummer, date(2026, 3, 5), vorgaenger_datum=URSPRUNG)


def _beleg(r):
    return zu_beleg(
        r,
        [],
        Beleg(
            datei_hash="0" * 64,
            dateiname="x.xml",
            kanal="rechnung",
            herkunft="test",
            aufbewahren_bis=date(2036, 12, 31),
        ),
    )


def test_gutschrift_381_traegt_den_bezug_auf_die_rechnung():
    r = _bau(_korrektur())
    assert (r.typ, r.vorgaenger_nummer, r.vorgaenger_datum) == (
        "381",
        "2026-0001",
        URSPRUNG,
    )
    assert (r.summen.netto, r.summen.brutto) == (D("100.00"), D("119.00"))
    xml = schreibe_cii(r)
    assert b"<ram:TypeCode>381</ram:TypeCode>" in xml
    assert b"<ram:InvoiceReferencedDocument>" in xml
    assert b"<ram:IssuerAssignedID>2026-0001</ram:IssuerAssignedID>" in xml
    gelesen = lies(xml)
    assert (gelesen.vorgaenger_nummer, gelesen.vorgaenger_datum) == (
        "2026-0001",
        URSPRUNG,
    )
    assert _beleg(gelesen).brutto == D("-119.00")


def test_gutschrift_mit_negativer_menge_wird_positiv_ausgewiesen():
    r = _bau(_korrektur("381", pos("Minderung", "100", menge="-1")))
    (z,) = r.zeilen
    assert (z.menge, z.einzelpreis, z.netto) == (D("1"), D("100"), D("100.00"))
    assert r.summen.brutto == D("119.00")


def test_rechnungskorrektur_384_weist_die_differenz_aus():
    r = _bau(_korrektur("384", pos("Minderung", "-100")))
    (z,) = r.zeilen
    # BR-27: Einzelpreis nie negativ — die Minderung steckt in der Menge
    assert (z.menge, z.einzelpreis, z.netto) == (D("-1"), D("100"), D("-100.00"))
    assert (r.typ, r.summen.brutto) == ("384", D("-119.00"))
    assert _beleg(lies(schreibe_cii(r))).brutto == D("-119.00")


def test_korrektur_ohne_bezug_oder_bezug_ohne_korrektur_ist_unzulaessig():
    with pytest.raises(ValueError, match="korrektur_zu"):
        entwurf(kunde(), pos("x", "1"), rechnungstyp="381")
    with pytest.raises(ValueError, match="rechnungstyp"):
        entwurf(kunde(), pos("x", "1"), korrektur_zu="2026-0001")


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def _ausgestellt(make_session, archiv, e, datum, **kw):
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        s.commit()
    with make_session() as s:
        ergebnis = stelle_aus(s, archiv, str(e.id)[:8], FIRMA, datum, **kw)
        s.commit()
    return ergebnis


def test_ausstellen_verlangt_die_ausgestellte_ursprungsrechnung(umgebung):
    make_session, archiv = umgebung
    with pytest.raises(AusstellungError, match="2026-0001"):
        _ausgestellt(make_session, archiv, _korrektur(), date(2026, 3, 5))
    _ausgestellt(make_session, archiv, entwurf(kunde(), pos("Ware", "500")), URSPRUNG)
    with pytest.raises(AusstellungError, match="vor der Rechnung"):
        _ausgestellt(make_session, archiv, _korrektur(), date(2026, 3, 1))
    ergebnis = _ausgestellt(make_session, archiv, _korrektur(), date(2026, 3, 5))
    assert lies(ergebnis.xml).vorgaenger_datum == URSPRUNG


@pytest.mark.skipif(
    not (KositPruefer().verfuegbar() and MustangPruefer().verfuegbar()),
    reason="KoSIT/Mustang nicht installiert (ACCOUNTI_PRUEFWERKZEUGE)",
)
@pytest.mark.parametrize(
    ("typ", "position"),
    [
        ("381", pos("Minderung wegen Mangel", "100")),
        ("381", pos("Minderung", "100", menge="-1")),
        ("384", pos("Minderung wegen Mangel", "100", menge="-1")),
        ("384", pos("Nachberechnung Fracht", "20")),
    ],
)
def test_kosit_und_mustang_akzeptieren_gutschrift_und_korrektur(
    umgebung, typ, position
):
    make_session, archiv = umgebung
    _ausgestellt(make_session, archiv, entwurf(kunde(), pos("Ware", "500")), URSPRUNG)
    ergebnis = _ausgestellt(
        make_session,
        archiv,
        _korrektur(typ, position),
        date(2026, 3, 5),
        kosit=KositPruefer(),
        pdf_pruefer=MustangPruefer(),
    )
    assert ergebnis.kosit is not None and ergebnis.kosit.akzeptiert
    assert ergebnis.mustang is not None and ergebnis.mustang.gueltig


# --- CLI Ende zu Ende (Proben des Testers: Gutschrift, Erstattung) -----------------


def _url(tmp_path):
    return f"sqlite:///{(tmp_path / 'a.db').as_posix()}"


def _cli(*args):
    r = runner.invoke(app, list(args))
    return r


def _ausstellen_cli(tmp_path, rid, datum):
    argumente = [
        "rechnung",
        "ausstellen",
        rid,
        "--db",
        _url(tmp_path),
        "--config",
        str(tmp_path / "accounti.yaml"),
        "--archiv",
        str(tmp_path / "archiv"),
        "--ausgabe",
        str(tmp_path / "out"),
        "--datum",
        datum,
    ]
    if not (KositPruefer().verfuegbar() and MustangPruefer().verfuegbar()):
        argumente.append("--ohne-formale-pruefung")
    r = _cli(*argumente)
    assert r.exit_code == 0, r.output
    return r


def _rechnung_und_gutschrift(tmp_path):
    (tmp_path / "accounti.yaml").write_text(FIRMA_YAML, encoding="utf-8")
    url = _url(tmp_path)
    r = _cli(
        "rechnung", "neu", "--db", url, "--name", "Kunde AG", "--strasse", "Weg 1",
        "--plz", "20457", "--ort", "Hamburg", "--email", "ap@kunde.example",
        "--ust-id", "DE129273398",
    )  # fmt: skip
    rid = r.output.split("Entwurf ")[1].split()[0]
    _cli("rechnung", "position", rid, "--db", url, "--text", "Ware", "--preis", "500")
    _ausstellen_cli(tmp_path, rid, "2026-03-02")
    r = _cli("rechnung", "neu", "--db", url, "--korrektur-zu", "2026-0001")
    assert r.exit_code == 0, r.output
    assert "Kunde AG" in r.output
    gid = r.output.split("Entwurf ")[1].split()[0]
    r = _cli(
        "rechnung", "position", gid, "--db", url, "--text", "Minderung wegen Mangel",
        "--preis", "100",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    return url, gid


def _verbuchen(tmp_path, url):
    r = _cli(
        "opos", "verbuchen", "--db", url, "--archiv", str(tmp_path / "archiv"),
        "--config", str(tmp_path / "accounti.yaml"),
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    return " ".join(r.output.split())


def _bank(tmp_path, url, zeile):
    datei = tmp_path / "bank.csv"
    datei.write_text(
        "Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;"
        "Begünstigter/Zahlungspflichtiger;Kontonummer;BLZ;Betrag;Währung;Info\n"
        + zeile
        + "\n",
        encoding="utf-8",
    )
    r = _cli("import", "bank", str(datei), "--db", url, "--format", "sparkasse")
    assert r.exit_code == 0, r.output
    r = _cli(
        "opos", "zuordnen", "--db", url, "--config", str(tmp_path / "accounti.yaml")
    )
    assert r.exit_code == 0, r.output
    return " ".join(r.output.split())


def test_gutschrift_wird_verrechnet_und_die_saldozahlung_gleicht_alles_aus(tmp_path):
    url, gid = _rechnung_und_gutschrift(tmp_path)
    _ausstellen_cli(tmp_path, gid, "2026-03-05")
    xml = (tmp_path / "out" / "2026-0002.xml").read_bytes()
    assert b"<ram:TypeCode>381</ram:TypeCode>" in xml
    assert b"<ram:IssuerAssignedID>2026-0001</ram:IssuerAssignedID>" in xml
    ausgabe = _verbuchen(tmp_path, url)
    assert "verrechnet" in ausgabe and "2026-0001" in ausgabe
    zuordnung = _bank(
        tmp_path,
        url,
        "DE89370400440532013000;20.03.26;20.03.26;GUTSCHRIFT;RE 2026-0001 ABZGL "
        "KORREKTUR 2026-0002;Kunde AG;DE44700500000000999999;BYLADEMMXXX;476,00;EUR;"
        "Umsatz gebucht",
    )
    assert "1 ausgeglichen" in zuordnung, zuordnung
    assert "Keine offenen Posten" in _cli("opos", "liste", "--db", url).output
    mahnlauf = _cli(
        "mahnwesen", "lauf", "--stichtag", "2026-04-30", "--db", url, "--config",
        str(tmp_path / "accounti.yaml"),
    )  # fmt: skip
    assert mahnlauf.exit_code == 0, mahnlauf.output
    assert "Mahnung 1" not in mahnlauf.output and "119,00" not in mahnlauf.output
    engine, make_session = session_factory(url)
    with make_session() as s:
        erloes = [b for b in lade_buchungen(s) if b.soll_konto == "8400"]
    engine.dispose()
    assert [(b.haben_konto, b.betrag_netto, b.steuer_betrag) for b in erloes] == [
        ("10000", D("100.00"), D("19.00"))
    ]


def test_erstattung_der_gutschrift_nach_bezahlter_rechnung(tmp_path):
    url, gid = _rechnung_und_gutschrift(tmp_path)
    _verbuchen(tmp_path, url)
    bezahlt = _bank(
        tmp_path,
        url,
        "DE89370400440532013000;10.03.26;10.03.26;GUTSCHRIFT;RE 2026-0001;Kunde AG;"
        "DE44700500000000999999;BYLADEMMXXX;595,00;EUR;Umsatz gebucht",
    )
    assert "1 ausgeglichen" in bezahlt
    _ausstellen_cli(tmp_path, gid, "2026-03-15")
    ausgabe = _verbuchen(tmp_path, url)
    assert "verrechnet" not in ausgabe
    erstattung = _bank(
        tmp_path,
        url,
        "DE89370400440532013000;20.03.26;20.03.26;UEBERWEISUNG;ERSTATTUNG GUTSCHRIFT "
        "2026-0002;Kunde AG;DE44700500000000999999;BYLADEMMXXX;-119,00;EUR;"
        "Umsatz gebucht",
    )
    assert "1 ausgeglichen" in erstattung, erstattung
    engine, make_session = session_factory(url)
    with make_session() as s:
        assert {p.status for p in lade_posten(s)} == {PostenStatus.AUSGEGLICHEN}
    engine.dispose()


def test_korrektur_zu_einer_unbekannten_rechnung(tmp_path):
    r = _cli("rechnung", "neu", "--db", _url(tmp_path), "--korrektur-zu", "2026-0099")
    assert r.exit_code == 1 and "2026-0099" in r.output
    r = _cli("rechnung", "neu", "--db", _url(tmp_path))
    assert r.exit_code == 1 and "--name" in r.output


# --- Gegenprüfung: Altrechnung ohne Straße (Regression aus N5) ----------------------


def _rechnung_ohne_strasse(tmp_path):
    """Ausgestellte Rechnung 2026-0001 über 595 €, deren Kunde keine Straße hat — so
    stellte accounti vor N5 aus (es verlangte nur PLZ und Ort)."""
    (tmp_path / "accounti.yaml").write_text(FIRMA_YAML, encoding="utf-8")
    url = _url(tmp_path)
    r = _cli(
        "rechnung", "neu", "--db", url, "--name", "Kunde AG", "--strasse", "Weg 1",
        "--plz", "20457", "--ort", "Hamburg", "--email", "ap@kunde.example",
        "--ust-id", "DE129273398",
    )  # fmt: skip
    rid = r.output.split("Entwurf ")[1].split()[0]
    _cli("rechnung", "position", rid, "--db", url, "--text", "Ware", "--preis", "500")
    _ausstellen_cli(tmp_path, rid, "2026-03-02")
    engine, _ = session_factory(url)
    with engine.begin() as c:
        c.execute(text("UPDATE ausgangsrechnungen SET kunde_strasse = NULL"))
    engine.dispose()
    return url


def _zeigen(tmp_path, url, schluessel):
    return _cli(
        "rechnung", "zeigen", schluessel, "--db", url, "--config",
        str(tmp_path / "accounti.yaml"),
    )  # fmt: skip


def test_ausgestellte_rechnung_ohne_strasse_laesst_sich_weiter_zeigen(tmp_path):
    # Gegenprüfung: die Anschriftprüfung (§ 14 Abs. 4 Satz 1 Nr. 1 UStG) gilt beim
    # Ausstellen — die Anzeige einer schon ausgestellten Rechnung bricht nicht ab
    url = _rechnung_ohne_strasse(tmp_path)
    r = _zeigen(tmp_path, url, "2026-0001")
    ausgabe = " ".join(r.output.split())
    assert r.exit_code == 0, r.output
    assert "Brutto 595.00" in ausgabe and "(ausgestellt)" in ausgabe
    assert "Straße oder Postfach" in ausgabe  # als Hinweis, nicht als Abbruch


def test_entwurf_ueber_250_euro_ohne_strasse_zeigt_die_vorschau_mit_warnung(tmp_path):
    (tmp_path / "accounti.yaml").write_text(FIRMA_YAML, encoding="utf-8")
    url = _url(tmp_path)
    r = _cli(
        "rechnung", "neu", "--db", url, "--name", "Kunde AG", "--plz", "20457",
        "--ort", "Hamburg", "--email", "ap@kunde.example",
    )  # fmt: skip
    rid = r.output.split("Entwurf ")[1].split()[0]
    _cli("rechnung", "position", rid, "--db", url, "--text", "Ware", "--preis", "500")
    r = _zeigen(tmp_path, url, rid)
    ausgabe = " ".join(r.output.split())
    assert r.exit_code == 0, r.output
    assert "Brutto 595.00" in ausgabe
    assert "Straße oder Postfach" in ausgabe and "ausstellen" in ausgabe
    # das Ausstellen lehnt weiter ab — die Nummer bleibt frei
    argumente = [
        "rechnung", "ausstellen", rid, "--db", url, "--config",
        str(tmp_path / "accounti.yaml"), "--archiv", str(tmp_path / "archiv"),
        "--ausgabe", str(tmp_path / "out"), "--datum", "2026-03-02",
        "--ohne-formale-pruefung",
    ]  # fmt: skip
    r = _cli(*argumente)
    assert r.exit_code == 1 and "Straße oder Postfach" in " ".join(r.output.split())


def test_korrektur_zu_altrechnung_ergaenzt_die_anschrift(tmp_path):
    # Gegenprüfung: ohne --name übernimmt die Korrektur den Kunden der Rechnung —
    # --strasse (wie --plz, --ort, --email …) ergänzt oder ändert einzelne Angaben,
    # sonst ließe sich zu einer Altrechnung über 250 € keine Korrektur ausstellen
    url = _rechnung_ohne_strasse(tmp_path)
    r = _cli(
        "rechnung", "neu", "--db", url, "--korrektur-zu", "2026-0001",
        "--korrektur-art", "korrektur", "--strasse", "Hafenweg 2",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    kid = r.output.split("Entwurf ")[1].split()[0]
    r = _cli(
        "rechnung", "position", kid, "--db", url, "--text", "Nachberechnung",
        "--preis", "300",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    _ausstellen_cli(tmp_path, kid, "2026-03-05")
    engine, make_session = session_factory(url)
    with make_session() as s:
        from accounti.db.repository import lade_ausgangsrechnung

        k = lade_ausgangsrechnung(s, "2026-0002")
    engine.dispose()
    assert (k.kunde.name, k.kunde.strasse, k.kunde.plz, k.kunde.ort) == (
        "Kunde AG",
        "Hafenweg 2",
        "20457",
        "Hamburg",
    )
    assert (k.rechnungstyp, k.korrektur_zu) == ("384", "2026-0001")
