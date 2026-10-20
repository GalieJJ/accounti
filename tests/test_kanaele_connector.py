import base64
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from accounti.belege.kanaele import BELEG_KANAELE
from accounti.belege.kanaele.abholung import KanalError
from accounti.belege.kanaele.connector import (
    BELEG_CONNECTOREN,
    BelegConnector,
    ConnectorKanal,
    PortalDokument,
    baue_connector,
    registriere_connector,
)
from accounti.belege.kanaele.einstellungen import ConnectorEintrag
from accounti.belege.kanaele.gedaechtnis import DbGedaechtnis
from accounti.belege.kanaele.json_http import JsonConnector
from accounti.belege.kanaele.pruefung import Dateipruefung
from accounti.db import init_db, session_factory
from accounti.db.repo_kanaele import lade_nachrichten
from accounti.konfiguration import KonfigurationError
from tests.http_attrappe import (
    HttpAttrappe,
    RohAttrappe,
    datei_antwort,
    json_antwort,
)
from tests.pdf_hilfe import pdf_mit_text

PDF_A = pdf_mit_text("Rechnung A")
PDF_B = pdf_mit_text("Rechnung B")
PDF_C = pdf_mit_text("Rechnung C")


@pytest.fixture
def make_session(tmp_path):
    engine, make = session_factory(f"sqlite:///{(tmp_path / 'c.db').as_posix()}")
    init_db(engine)
    return make


def _alles(kanal, bestaetigen=True):
    geholt = []
    for roh in kanal.abholen():
        geholt.append(roh)
        if bestaetigen:
            kanal.bestaetige(roh)
    return geholt


def _kanal(eintrag, make_session, geheimnis=None, pruefung=None):
    connector = baue_connector(ConnectorEintrag(**eintrag), lambda: geheimnis)
    return ConnectorKanal(connector, DbGedaechtnis(make_session), pruefung)


# ---------------------------------------------------------------------------
# Basisklasse und Registry
# ---------------------------------------------------------------------------


class _ProbeEinstellungen(BaseModel):
    dokumente: dict[str, str]


class ProbeConnector(BelegConnector):
    typ = "probe"
    beschreibung = "Probe"
    Einstellungen = _ProbeEinstellungen

    def dokumente(self) -> Iterator[PortalDokument]:
        for nr in self.einstellungen.dokumente:
            yield PortalDokument(id=nr, dateiname=f"{nr}.pdf", absender="Portal AG")

    def lade(self, dokument: PortalDokument) -> bytes:
        inhalt = self.einstellungen.dokumente[dokument.id]
        if inhalt == "fehler":
            raise KanalError("HTTP 503")
        return inhalt.encode("latin-1")


@pytest.fixture
def probe():
    registriere_connector(ProbeConnector)
    yield
    BELEG_CONNECTOREN.pop("probe")


def test_registry_kennt_json_und_connector_kanal():
    assert BELEG_CONNECTOREN["json"] is JsonConnector
    assert BELEG_KANAELE["connector"] is ConnectorKanal
    assert all(k.beschreibung for k in BELEG_CONNECTOREN.values())


def test_eigener_connector_ueber_registry_und_gedaechtnis(make_session, probe):
    eintrag = {
        "name": "p",
        "typ": "probe",
        "dokumente": {
            "1": PDF_A.decode("latin-1"),
            "2": "fehler",
            "3": "kein Beleg",
        },
    }
    kanal = _kanal(eintrag, make_session)
    (roh,) = _alles(kanal)
    assert (roh.kanal, roh.dateiname, roh.inhalt) == ("connector", "1.pdf", PDF_A)
    assert roh.herkunft == "Connector p: Dokument 1 von Portal AG"
    assert any("2" in h and "HTTP 503" in h for h in kanal.hinweise)
    assert any("3.pdf" in h and "nicht erlaubt" in h for h in kanal.hinweise)
    # 1 und 3 sind gemerkt, 2 (Download-Fehler) wird erneut versucht
    zweiter = _kanal(eintrag, make_session)
    assert _alles(zweiter) == []
    assert any("HTTP 503" in h for h in zweiter.hinweise)
    with make_session() as s:
        gemerkt = {n.schluessel: n for n in lade_nachrichten(s, kanal="connector")}
    assert set(gemerkt) == {"1", "3"}
    assert gemerkt["1"].absender == "Portal AG"
    assert gemerkt["1"].datei_hashes


def test_ohne_bestaetigung_nicht_gemerkt(make_session, probe):
    eintrag = {"name": "p", "typ": "probe", "dokumente": {"1": PDF_A.decode("latin-1")}}
    assert len(_alles(_kanal(eintrag, make_session), bestaetigen=False)) == 1
    assert len(_alles(_kanal(eintrag, make_session))) == 1


def test_unbekannter_typ_und_falsche_einstellungen():
    with pytest.raises(KonfigurationError, match="Connector-Typ 'gibtsnicht'"):
        baue_connector(ConnectorEintrag(name="x", typ="gibtsnicht"), lambda: None)
    with pytest.raises(KonfigurationError, match=r"connectoren\[x\].*basis_url"):
        baue_connector(ConnectorEintrag(name="x", typ="json"), lambda: None)


# ---------------------------------------------------------------------------
# Generischer JSON/HTTP-Connector
# ---------------------------------------------------------------------------


def _json_eintrag(server, **werte):
    basis = {
        "name": "portal",
        "typ": "json",
        "basis_url": f"{server.url}/api/v1",
        "kopfzeilen": {"X-API-KEY": "${ACCOUNTI_TEST_PORTAL}"},
        "liste": {
            "pfad": "/dokumente",
            "parameter": {"proSeite": "2"},
            "eintraege": "daten.eintraege",
            "seite_parameter": "seite",
        },
        "felder": {"id": "uid", "dateiname": "datei.name", "absender": "firma"},
        "datei": {"pfad": "/dokumente/{id}/datei"},
    }
    return {**basis, **werte}


def _seiten(eintraege, pro_seite=2):
    def route(anfrage):
        seite = int(anfrage.parameter.get("seite", "1"))
        teil = eintraege[(seite - 1) * pro_seite : seite * pro_seite]
        return json_antwort({"daten": {"eintraege": teil}})

    return route


def test_liste_seitenweise_und_binaerer_download(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "schluessel-123")
    eintraege = [
        {"uid": 1, "datei": {"name": "a.pdf"}, "firma": "A GmbH"},
        {"uid": "b/2", "datei": {"name": "b.pdf"}, "firma": "B AG"},
        {"uid": 3, "datei": {"name": "c.pdf"}},
    ]
    dateien = {"1": PDF_A, "b%2F2": PDF_B, "3": PDF_C}
    with HttpAttrappe({"/api/v1/dokumente": _seiten(eintraege)}) as server:
        for schluessel, inhalt in dateien.items():
            server.routen[f"/api/v1/dokumente/{schluessel}/datei"] = (
                lambda _a, i=inhalt: datei_antwort(i)
            )
        geholt = _alles(_kanal(_json_eintrag(server), make_session))
        assert [r.dateiname for r in geholt] == ["a.pdf", "b.pdf", "c.pdf"]
        assert [r.inhalt for r in geholt] == [PDF_A, PDF_B, PDF_C]
        assert geholt[1].herkunft == "Connector portal: Dokument b/2 von B AG"
        seiten = [a.parameter for a in server.anfragen if a.pfad.endswith("dokumente")]
        assert seiten == [
            {"proSeite": "2", "seite": "1"},
            {"proSeite": "2", "seite": "2"},
            {"proSeite": "2", "seite": "3"},
        ]
        assert all(
            a.kopfzeilen["x-api-key"] == "schluessel-123" for a in server.anfragen
        )
        anzahl = len(server.anfragen)
        assert _alles(_kanal(_json_eintrag(server), make_session)) == []
        neue = server.anfragen[anzahl:]
        assert not any(a.pfad.endswith("/datei") for a in neue)


def test_naechste_url_und_base64_im_json(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    routen = {
        "/api/v1/dokumente": lambda a: json_antwort(
            {
                "records": [{"documentUid": 7, "filename": "r7.pdf"}],
                "next": "/api/v1/weiter?ab=8",
            }  # fmt: skip
        ),
        "/api/v1/weiter": lambda a: json_antwort(
            {"records": [{"documentUid": 8, "filename": "r8.pdf"}], "next": None}
        ),
        "/api/v1/documents/7": lambda a: json_antwort(
            {"fileContent": base64.b64encode(PDF_A).decode()}
        ),
        "/api/v1/documents/8": lambda a: json_antwort(
            {"fileContent": base64.b64encode(PDF_B).decode()}
        ),
    }
    with HttpAttrappe(routen) as server:
        eintrag = _json_eintrag(
            server,
            liste={"pfad": "/dokumente", "eintraege": "records", "naechste": "next"},
            felder={"id": "documentUid", "dateiname": "filename"},
            datei={
                "pfad": "/documents/{id}",
                "parameter": {"includeDocument": "true"},
                "inhalt": "fileContent",
            },
        )
        geholt = _alles(_kanal(eintrag, make_session))
        assert [r.inhalt for r in geholt] == [PDF_A, PDF_B]
        assert any(a.parameter == {"ab": "8"} for a in server.anfragen)
        assert any(a.parameter == {"includeDocument": "true"} for a in server.anfragen)


def test_download_url_eigener_und_fremder_host(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "geheim-k")
    with HttpAttrappe() as fremd, HttpAttrappe() as portal:
        fremd.routen["/s3/a.pdf"] = lambda a: datei_antwort(PDF_A)
        fremd.routen["/s3/b.pdf"] = lambda a: datei_antwort(PDF_B)
        portal.routen["/api/v1/dokumente"] = lambda a: json_antwort(
            [
                {"uid": 1, "url": f"http://localhost:{fremd.port}/s3/a.pdf"},
                {"uid": 2, "url": "/api/v1/eigen/b.pdf"},
                {"uid": 3, "url": f"http://localhost:{fremd.port}/s3/b.pdf"},
            ]
        )
        portal.routen["/api/v1/eigen/b.pdf"] = lambda a: datei_antwort(PDF_B)
        eintrag = _json_eintrag(
            portal,
            liste={"pfad": "/dokumente"},
            felder={"id": "uid", "url": "url"},
            datei={},
        )
        ohne_erlaubnis = _kanal(eintrag, make_session)
        assert [r.inhalt for r in _alles(ohne_erlaubnis)] == [PDF_B]
        assert any(
            "localhost" in h and "erlaubte_hosts" in h for h in ohne_erlaubnis.hinweise
        )
        assert fremd.anfragen == []
        mit = _kanal({**eintrag, "erlaubte_hosts": ["localhost"]}, make_session)
        assert sorted(r.inhalt for r in _alles(mit)) == sorted([PDF_A, PDF_B])
        assert fremd.anfragen
        assert all("x-api-key" not in a.kopfzeilen for a in fremd.anfragen)
        assert all(a.kopfzeilen["x-api-key"] == "geheim-k" for a in portal.anfragen)


def test_portaldatum_steht_im_gedaechtnis(make_session, monkeypatch):
    """felder.datum wird gelesen und wie der Date-Kopf einer Mail gespeichert."""
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    with HttpAttrappe() as server:
        server.routen["/api/v1/dokumente"] = lambda a: json_antwort(
            [
                {"uid": 1, "am": "2026-09-15T08:00:00+02:00"},
                {"uid": 2, "am": "2026-09-16"},
                {"uid": 3, "am": "15.09.2026"},
            ]
        )
        for nr, inhalt in ((1, PDF_A), (2, PDF_B), (3, PDF_C)):
            server.routen[f"/api/v1/dokumente/{nr}/datei"] = lambda _a, i=inhalt: (
                datei_antwort(i)
            )
        eintrag = _json_eintrag(
            server, liste={"pfad": "/dokumente"}, felder={"id": "uid", "datum": "am"}
        )
        assert len(_alles(_kanal(eintrag, make_session))) == 3
    with make_session() as s:
        datum = {
            n.schluessel: n.gesendet_am for n in lade_nachrichten(s, kanal="connector")
        }
    erwartet = datetime(2026, 9, 15, 8, 0, tzinfo=timezone(timedelta(hours=2)))
    assert datum["1"] == erwartet.astimezone(None).replace(tzinfo=None)
    assert datum["2"] == datetime(2026, 9, 16)
    assert datum["3"] is None  # nicht ISO 8601


def test_zugang_aus_dem_tresor(make_session):
    with HttpAttrappe() as server:
        server.routen["/api/v1/dokumente"] = lambda a: json_antwort([])
        eintrag = _json_eintrag(
            server,
            kopfzeilen={"Authorization": "Bearer {zugang}"},
            liste={"pfad": "/dokumente"},
        )
        _alles(_kanal(eintrag, make_session, geheimnis="tresor-token"))
        assert server.anfragen[0].kopfzeilen["authorization"] == "Bearer tresor-token"
        with pytest.raises(KanalError, match="kanaele zugang connector portal"):
            _alles(_kanal(eintrag, make_session, geheimnis=None))


def test_http_fehler_und_zu_grosse_antwort(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "geheim-k")
    with HttpAttrappe() as server:
        server.routen["/api/v1/dokumente"] = lambda a: json_antwort(
            {"fehler": "nicht angemeldet"}, status=401
        )
        eintrag = _json_eintrag(server, liste={"pfad": "/dokumente"})
        with pytest.raises(KanalError) as fehler:
            _alles(_kanal(eintrag, make_session))
        assert "401" in str(fehler.value)
        assert "geheim-k" not in str(fehler.value)
        server.routen["/api/v1/dokumente"] = lambda a: json_antwort(["x" * 2000])
        klein = {**eintrag, "max_antwort_mb": 0.001}
        with pytest.raises(KanalError, match="größer"):
            _alles(_kanal(klein, make_session))
        server.routen["/api/v1/dokumente"] = lambda a: (200, {}, b"kein json")
        with pytest.raises(KanalError, match="JSON"):
            _alles(_kanal(eintrag, make_session))
        server.routen["/api/v1/dokumente"] = lambda a: json_antwort({"x": 1})
        with pytest.raises(KanalError, match="keine Liste"):
            _alles(_kanal(eintrag, make_session))


def test_zu_grosse_datei_wird_gemerkt(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    with HttpAttrappe() as server:
        server.routen["/api/v1/dokumente"] = lambda a: json_antwort([{"uid": 1}])
        server.routen["/api/v1/dokumente/1/datei"] = lambda a: datei_antwort(
            PDF_A + b"x" * 5000
        )
        eintrag = _json_eintrag(server, liste={"pfad": "/dokumente"})
        kanal = _kanal(eintrag, make_session, pruefung=Dateipruefung(max_bytes=2000))
        assert _alles(kanal) == []
        assert any("höchstens" in h for h in kanal.hinweise)
        assert _alles(_kanal(eintrag, make_session)) == []


def test_weiterleitung_auf_fremden_host_wird_abgelehnt(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "geheim-k")
    with HttpAttrappe() as fremd, HttpAttrappe() as portal:
        fremd.routen["/fang"] = lambda a: json_antwort([])
        portal.routen["/api/v1/dokumente"] = lambda a: (
            302,
            {"Location": f"http://localhost:{fremd.port}/fang"},
            b"",
        )
        eintrag = _json_eintrag(portal, liste={"pfad": "/dokumente"})
        with pytest.raises(KanalError, match="Weiterleitung"):
            _alles(_kanal(eintrag, make_session))
    assert fremd.anfragen == []


def _seiten_mit_dateien(server, anzahl, pro_seite=2):
    eintraege = [{"uid": nr} for nr in range(1, anzahl + 1)]
    server.routen["/api/v1/dokumente"] = _seiten(eintraege, pro_seite)
    for nr in range(1, anzahl + 1):
        server.routen[f"/api/v1/dokumente/{nr}/datei"] = lambda _a, n=nr: datei_antwort(
            PDF_A + str(n).encode()
        )


def test_mehr_seiten_als_max_seiten_ist_ein_fehler_kein_beruhigender_hinweis(
    make_session, monkeypatch
):
    """Jeder Lauf beginnt bei Seite 1 — was hinter max_seiten liegt, darf nicht
    still liegen bleiben: Der Lauf scheitert mit wahrer Meldung (Exit 1)."""
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    with HttpAttrappe() as server:
        _seiten_mit_dateien(server, 6)
        eintrag = _json_eintrag(server)
        eintrag["liste"] = {**eintrag["liste"], "max_seiten": 2}
        for _lauf in range(2):
            kanal = _kanal(eintrag, make_session)
            geholt = []
            with pytest.raises(KanalError, match="mehr als 2 Seiten") as fehler:
                for roh in kanal.abholen():
                    geholt.append(roh)
                    kanal.bestaetige(roh)
            assert "max_seiten" in str(fehler.value)
            assert not any("nächste Lauf macht weiter" in h for h in kanal.hinweise)
        # Lauf 1 hat die ersten vier aufgenommen, Lauf 2 nichts Neues gefunden
        with make_session() as s:
            assert len(lade_nachrichten(s, kanal="connector")) == 4
        # mit genug Seiten kommt der Rest im nächsten Lauf
        eintrag["liste"] = {**eintrag["liste"], "max_seiten": 3}
        rest = _alles(_kanal(eintrag, make_session))
        assert [r.inhalt for r in rest] == [PDF_A + b"5", PDF_A + b"6"]


def test_genau_max_seiten_volle_seiten_sind_kein_fehler(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    with HttpAttrappe() as server:
        _seiten_mit_dateien(server, 4)
        eintrag = _json_eintrag(server)
        eintrag["liste"] = {**eintrag["liste"], "max_seiten": 2}
        kanal = _kanal(eintrag, make_session)
        assert len(_alles(kanal)) == 4
        assert kanal.hinweise == []


def test_next_url_ueber_max_seiten_ist_ein_fehler(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")

    def seite(anfrage):
        nr = int(anfrage.parameter.get("s", "1"))
        return json_antwort({"records": [{"uid": nr}], "next": f"?s={nr + 1}"})

    with HttpAttrappe({"/api/v1/dokumente": seite}) as server:
        for nr in range(1, 5):
            server.routen[f"/api/v1/dokumente/{nr}/datei"] = lambda _a, n=nr: (
                datei_antwort(PDF_A + str(n).encode())
            )
        eintrag = _json_eintrag(
            server,
            liste={
                "pfad": "/dokumente",
                "eintraege": "records",
                "naechste": "next",
                "max_seiten": 3,
            },
        )
        with pytest.raises(KanalError, match="mehr als 3 Seiten"):
            _alles(_kanal(eintrag, make_session))


def test_unvollstaendiger_download_wird_nicht_als_original_gemerkt(
    make_session, monkeypatch
):
    """Content-Length 100000, aber nur 20 Bytes und Verbindungsende: Das ist kein
    Original — nicht aufnehmen, nicht merken, nächster Lauf versucht es erneut."""
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    kurz = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
        b"Content-Length: 100000\r\nConnection: close\r\n\r\n" + PDF_A[:20]
    )
    with RohAttrappe(kurz) as dateien, HttpAttrappe() as portal:
        portal.routen["/api/v1/dokumente"] = lambda a: json_antwort(
            [{"uid": 1, "datei": {"name": "p-1.pdf"}, "url": f"{dateien.url}/p-1.pdf"}]
        )
        eintrag = _json_eintrag(
            portal,
            liste={"pfad": "/dokumente"},
            felder={"id": "uid", "dateiname": "datei.name", "url": "url"},
            erlaubte_hosts=["127.0.0.1"],
        )
        kanal = _kanal(eintrag, make_session)
        assert _alles(kanal) == []
        assert any("unvollständig" in h and "erneut" in h for h in kanal.hinweise)
        dateien.antwort = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
            b"Content-Length: %d\r\nConnection: close\r\n\r\n" % len(PDF_A) + PDF_A
        )
        (roh,) = _alles(_kanal(eintrag, make_session))
        assert roh.inhalt == PDF_A


def test_abgebrochenes_chunked_und_kaputte_url_brechen_den_lauf_nicht_ab(
    make_session, monkeypatch
):
    monkeypatch.setenv("ACCOUNTI_TEST_PORTAL", "k")
    chunked = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
        b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        b"400\r\n" + PDF_A[:20]
    )
    with RohAttrappe(chunked) as dateien, HttpAttrappe() as portal:
        portal.routen["/api/v1/dokumente"] = lambda a: json_antwort(
            [
                {"uid": 1, "url": f"{dateien.url}/c.pdf"},
                {"uid": 2, "url": "/api/v1/a/Rechnung 2.pdf"},
                {"uid": 3, "url": "http://[::1/kaputt.pdf"},
                {"uid": 4, "url": "/api/v1/a/vier.pdf"},
            ]
        )
        portal.routen["/api/v1/a/Rechnung%202.pdf"] = lambda a: datei_antwort(PDF_B)
        portal.routen["/api/v1/a/vier.pdf"] = lambda a: datei_antwort(PDF_C)
        eintrag = _json_eintrag(
            portal,
            liste={"pfad": "/dokumente"},
            felder={"id": "uid", "url": "url"},
            datei={},
            erlaubte_hosts=["127.0.0.1"],
        )
        kanal = _kanal(eintrag, make_session)
        assert [r.inhalt for r in _alles(kanal)] == [PDF_B, PDF_C]
        assert any("Dokument 1 nicht geladen" in h for h in kanal.hinweise)
        assert any("Dokument 3 nicht geladen" in h for h in kanal.hinweise)
        with make_session() as s:
            gemerkt = {n.schluessel for n in lade_nachrichten(s, kanal="connector")}
        assert gemerkt == {"2", "4"}


def test_fremder_download_host_nur_mit_https():
    class _S:
        url = "https://portal.example"

    eintrag = _json_eintrag(
        _S(),
        liste={"pfad": "/dokumente"},
        felder={"id": "uid", "url": "url"},
        datei={},
        erlaubte_hosts=["dateien.example"],
    )
    connector = baue_connector(ConnectorEintrag(**eintrag), lambda: None)
    with pytest.raises(KanalError, match="https"):
        connector.lade(PortalDokument(id="1", url="http://dateien.example/x.pdf"))
    with pytest.raises(KanalError, match="erlaubte_hosts"):
        connector.lade(PortalDokument(id="1", url="ftp://dateien.example/x.pdf"))


@pytest.mark.parametrize(
    ("aenderung", "meldung"),
    [
        ({"basis_url": "http://portal.example/api"}, "https"),
        ({"kopfzeilen": {"X-API-KEY": "klartext-123"}}, "Klartext"),
        ({"kopfzeilen": {"Authorization": "Bearer abc"}}, "Klartext"),
        ({"liste": {"pfad": "/d", "parameter": {"api_token": "abc"}}}, "Klartext"),
        ({"datei": {}}, "datei.pfad"),
        ({"unbekannt": 1}, "unbekannt"),
        ({"liste": {"pfad": "/d?apiKey=klartext-123"}}, "Klartext"),
        ({"datei": {"pfad": "/d/{id}?token=klartext-123"}}, "Klartext"),
        ({"kopfzeilen": {"Authorization": "Bearer klartext-123${X}"}}, "Klartext"),
        ({"kopfzeilen": {"X-Auth": "klartext-123"}}, "Klartext"),
        (
            {"liste": {"pfad": "/d", "seite_parameter": "s", "naechste": "n"}},
            "seite_parameter oder naechste",
        ),
    ],
)
def test_einstellungen_werden_geprueft(aenderung, meldung):
    class _S:
        url = "https://portal.example"

    eintrag = {**_json_eintrag(_S()), **aenderung}
    with pytest.raises(KonfigurationError, match=meldung) as fehler:
        baue_connector(ConnectorEintrag(**eintrag), lambda: None)
    assert "klartext-123" not in str(fehler.value)


@pytest.mark.parametrize(
    "kopfzeilen",
    [
        {"Authorization": "Bearer {zugang}"},
        {"Authorization": "Basic ${ACCOUNTI_TEST_B64}"},
        {"X-API-KEY": "${ACCOUNTI_TEST_PORTAL}"},
        {"Cookie": "sid=${ACCOUNTI_TEST_SID}"},
        {"X-Author": "Max Muster", "Accept-Language": "de"},
    ],
)
def test_platzhalter_mit_festem_praefix_sind_erlaubt(kopfzeilen):
    class _S:
        url = "https://portal.example"

    eintrag = {**_json_eintrag(_S()), "kopfzeilen": kopfzeilen}
    baue_connector(ConnectorEintrag(**eintrag), lambda: None)
