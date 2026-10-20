import datetime as dt
import email.policy
import imaplib
import quopri
from email.message import EmailMessage
from email.utils import format_datetime

import pytest

from accounti.belege.kanaele import BELEG_KANAELE
from accounti.belege.kanaele.abholung import KanalError
from accounti.belege.kanaele.einstellungen import EmailPostfach
from accounti.belege.kanaele.email import EmailKanal, lies_nachricht
from accounti.belege.kanaele.gedaechtnis import DbGedaechtnis
from accounti.belege.kanaele.pruefung import Dateipruefung
from accounti.db import init_db, session_factory
from accounti.db.repo_kanaele import lade_nachrichten
from tests.imap_attrappe import ImapAttrappe, Postfach, zertifikate
from tests.pdf_hilfe import pdf_mit_text

PDF = pdf_mit_text("Rechnung RE-1\nGesamtbetrag 119,00 EUR")
PNG_LOGO = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def mail(
    *anhaenge,
    absender="Bürobedarf Müller GmbH <rechnung@mueller.example>",
    betreff="Ihre Rechnung RE-1",
    message_id="<re-1@mueller.example>",
    text="Guten Tag, anbei die Rechnung.",
    html=None,
):
    m = EmailMessage()
    m["From"] = absender
    m["To"] = "belege@firma.example"
    m["Subject"] = betreff
    m["Date"] = format_datetime(dt.datetime(2026, 10, 1, 9, 30, tzinfo=dt.UTC))
    if message_id:
        m["Message-ID"] = message_id
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    for name, inhalt, typ in anhaenge:
        haupt, _, unter = typ.partition("/")
        m.add_attachment(inhalt, maintype=haupt, subtype=unter, filename=name)
    return m.as_bytes(policy=email.policy.SMTP)


# ---------------------------------------------------------------------------
# Anhänge aus einer Nachricht
# ---------------------------------------------------------------------------


def test_registry_kennt_email():
    assert BELEG_KANAELE["email"] is EmailKanal
    assert "IMAP" in EmailKanal.beschreibung


def test_pdf_anhang_byte_genau_und_absender():
    n = lies_nachricht(mail(("Rechnung.pdf", PDF, "application/pdf")), Dateipruefung())
    assert [(d.dateiname, d.inhalt) for d in n.dateien] == [("Rechnung.pdf", PDF)]
    assert n.absender == "rechnung@mueller.example"
    assert n.absender_name == "Bürobedarf Müller GmbH"
    assert n.betreff == "Ihre Rechnung RE-1"
    assert n.message_id == "<re-1@mueller.example>"
    assert n.gesendet_am == dt.datetime(2026, 10, 1, 9, 30, tzinfo=dt.UTC).astimezone(
        None
    ).replace(tzinfo=None)
    assert n.hinweise == []


def test_quoted_printable_xml_anhang():
    xml = (
        b'<?xml version="1.0"?>\n<Invoice xmlns="urn:oasis:names:specification:'
        b'ubl:schema:xsd:Invoice-2"><Note>M\xc3\xbcller =</Note></Invoice>\n'
    )
    roh = (
        b"From: a@b.example\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="g"\r\n\r\n'
        b"--g\r\nContent-Type: text/plain\r\n\r\nx\r\n"
        b"--g\r\nContent-Type: application/xml\r\n"
        b'Content-Disposition: attachment; filename="r.xml"\r\n'
        b"Content-Transfer-Encoding: quoted-printable\r\n\r\n"
        + quopri.encodestring(xml).replace(b"\n", b"\r\n")
        + b"\r\n--g--\r\n"
    )
    n = lies_nachricht(roh, Dateipruefung())
    # Zeilenumbrüche sind in Quoted-Printable kanonisch CRLF (RFC 2045 6.7)
    assert [d.inhalt for d in n.dateien] == [xml.replace(b"\n", b"\r\n")]


def test_mehrere_anhaenge_und_weitergeleitete_nachricht():
    innen = mail(("innen.pdf", PDF + b"innen", "application/pdf"))
    aussen = EmailMessage()
    aussen["From"] = "Kollegin <kollegin@firma.example>"
    aussen["Subject"] = "WG: Ihre Rechnung"
    aussen.set_content("Bitte buchen.")
    aussen.add_attachment(
        PDF + b"aussen", maintype="application", subtype="pdf", filename="aussen.pdf"
    )
    aussen.add_attachment(email.message_from_bytes(innen, policy=email.policy.default))
    n = lies_nachricht(aussen.as_bytes(), Dateipruefung())
    assert [d.dateiname for d in n.dateien] == ["aussen.pdf", "innen.pdf"]
    assert n.absender == "kollegin@firma.example"


def test_textkoerper_und_eingebettetes_logo_werden_uebersprungen():
    m = EmailMessage()
    m["From"] = "a@b.example"
    m.set_content("Text")
    m.add_alternative('<p>Text <img src="cid:logo"></p>', subtype="html")
    html = m.get_payload()[1]
    html.add_related(
        PNG_LOGO, maintype="image", subtype="png", cid="<logo>", filename="logo.png"
    )
    m.add_attachment(PDF, maintype="application", subtype="pdf", filename="r.pdf")
    n = lies_nachricht(m.as_bytes(), Dateipruefung())
    assert [d.dateiname for d in n.dateien] == ["r.pdf"]
    assert n.hinweise == []


def test_unerlaubter_typ_und_zu_gross_als_hinweis():
    roh = mail(
        ("vertrag.docx", b"PK\x03\x04 docx", "application/octet-stream"),
        ("gross.pdf", PDF + b"x" * 2000, "application/pdf"),
        ("ok.png", PNG_LOGO, "image/png"),
    )
    n = lies_nachricht(roh, Dateipruefung(max_bytes=1500))
    assert [d.dateiname for d in n.dateien] == ["ok.png"]
    assert len(n.hinweise) == 2
    assert "vertrag.docx" in n.hinweise[0]
    assert "ZIP" in n.hinweise[0]
    assert "gross.pdf" in n.hinweise[1]
    assert "höchstens" in n.hinweise[1]


def test_rfc2231_dateiname_und_fehlender_dateiname():
    m = EmailMessage()
    m["From"] = "a@b.example"
    m.set_content("x")
    m.add_attachment(
        PDF,
        maintype="application",
        subtype="pdf",
        filename=("utf-8", "", "Rechnung März.pdf"),
    )
    m.add_attachment(PDF + b"2", maintype="application", subtype="pdf")
    n = lies_nachricht(m.as_bytes(), Dateipruefung())
    assert [d.dateiname for d in n.dateien] == ["Rechnung März.pdf", "anhang-2.pdf"]


def test_kaputte_kopfzeilen_brechen_nicht_ab():
    roh = (
        b"From: kein gueltiger <absender\r\nSubject: =?utf-8?q?kaputt\r\n"
        b"Date: gestern\r\nMIME-Version: 1.0\r\nContent-Type: text/plain\r\n\r\nx\r\n"
    )
    n = lies_nachricht(roh, Dateipruefung())
    assert n.dateien == []
    assert n.gesendet_am is None


# ---------------------------------------------------------------------------
# Gegen den IMAP-Server
# ---------------------------------------------------------------------------


@pytest.fixture
def make_session(tmp_path):
    engine, make = session_factory(f"sqlite:///{(tmp_path / 'k.db').as_posix()}")
    init_db(engine)
    return make


def _postfach(port, **werte):
    basis = {
        "name": "rechnungen",
        "host": "127.0.0.1",
        "port": port,
        "verschluesselung": "keine",
        "benutzer": "belege@firma.example",
    }
    return EmailPostfach(**{**basis, **werte})


def _kanal(port, make_session, passwort="geheim", **werte):
    return EmailKanal(_postfach(port, **werte), passwort, DbGedaechtnis(make_session))


def _alles(kanal, bestaetigen=True):
    geholt = []
    for roh in kanal.abholen():
        geholt.append(roh)
        if bestaetigen:
            kanal.bestaetige(roh)
    return geholt


def test_holt_anhaenge_merkt_nachrichten_und_laesst_postfach_unberuehrt(
    make_session,
):
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    pf.lege_ab(mail(message_id="<ohne@x>", betreff="Nur Text"))
    with ImapAttrappe(pf) as server:
        kanal = _kanal(server.port, make_session)
        (roh,) = _alles(kanal)
        assert roh.kanal == "email"
        assert roh.dateiname == "Rechnung.pdf"
        assert roh.inhalt == PDF
        assert "rechnung@mueller.example" in roh.herkunft
        assert "Ihre Rechnung RE-1" in roh.herkunft
        assert any("keine Belegdatei" in h for h in kanal.hinweise)
        # zweiter Lauf: nichts Neues, nichts erneut geladen
        assert _alles(_kanal(server.port, make_session)) == []
    assert not any(b.startswith("UID STORE") for b in pf.befehle)
    assert any(b.startswith("EXAMINE") for b in pf.befehle)
    assert sum("BODY.PEEK[]" in b for b in pf.befehle) == 2
    assert all(n.flags == set() for n in pf.ordner["INBOX"])
    with make_session() as s:
        nachrichten = lade_nachrichten(s, kanal="email")
    assert len(nachrichten) == 2
    mit = next(n for n in nachrichten if n.datei_hashes)
    assert mit.absender == "rechnung@mueller.example"
    assert mit.schluessel == "INBOX:1:1"
    assert mit.message_id == "<re-1@mueller.example>"


def test_neue_uidvalidity_gleiche_message_id_holt_nichts_doppelt(make_session):
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    with ImapAttrappe(pf) as server:
        assert len(_alles(_kanal(server.port, make_session))) == 1
        pf.neu_angelegt()
        kanal = _kanal(server.port, make_session)
        assert _alles(kanal) == []
        assert any("Message-ID" in h for h in kanal.hinweise)
        assert _alles(_kanal(server.port, make_session)) == []


def test_ohne_bestaetigung_wird_nicht_gemerkt(make_session):
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    with ImapAttrappe(pf) as server:
        assert len(_alles(_kanal(server.port, make_session), bestaetigen=False)) == 1
        # Abbruch mitten im Lauf
        gen = _kanal(server.port, make_session).abholen()
        next(gen)
        gen.close()
        assert len(_alles(_kanal(server.port, make_session))) == 1
    assert pf.befehle[-1].startswith("LOGOUT")


def test_gelesen_setzt_seen(make_session):
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    with ImapAttrappe(pf) as server:
        _alles(_kanal(server.port, make_session, nach_abholen="gelesen"))
    assert pf.ordner["INBOX"][0].flags == {"\\Seen"}
    assert any(b.startswith("SELECT") for b in pf.befehle)


def test_verschieben_mit_move(make_session):
    pf = Postfach()
    pf.ordner["Belege abgeholt"] = []
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    with ImapAttrappe(pf) as server:
        _alles(
            _kanal(
                server.port,
                make_session,
                nach_abholen="verschieben",
                ziel_ordner="Belege abgeholt",
            )
        )
    assert pf.ordner["INBOX"] == []
    assert len(pf.ordner["Belege abgeholt"]) == 1


def test_verschieben_ohne_move_faehigkeit_bricht_vorher_ab(make_session):
    pf = Postfach(faehigkeiten=("IMAP4rev1",))
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    with ImapAttrappe(pf) as server:
        kanal = _kanal(
            server.port, make_session, nach_abholen="verschieben", ziel_ordner="X"
        )
        with pytest.raises(KanalError, match="MOVE"):
            _alles(kanal)
    assert not any("BODY.PEEK" in b for b in pf.befehle)


def test_falsches_passwort_meldet_ohne_passwort(make_session):
    with ImapAttrappe(Postfach()) as server:
        kanal = _kanal(server.port, make_session, passwort="falsch-Xy9")
        with pytest.raises(KanalError) as fehler:
            _alles(kanal)
    assert "Anmeldung" in str(fehler.value)
    assert "falsch-Xy9" not in str(fehler.value)


def test_passwort_wird_erst_beim_abholen_ermittelt(make_session):
    aufrufe = []

    def passwort():
        aufrufe.append(1)
        return "geheim"

    with ImapAttrappe(Postfach()) as server:
        kanal = _kanal(server.port, make_session, passwort=passwort)
        assert aufrufe == []
        _alles(kanal)
    assert aufrufe == [1]


def test_zu_grosse_nachricht_wird_gemerkt_aber_nicht_geladen(make_session):
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", PDF + b"x" * 3 * 1024 * 1024, "application/pdf")))
    with ImapAttrappe(pf) as server:
        kanal = _kanal(server.port, make_session, max_nachricht_mb=1)
        assert _alles(kanal) == []
        assert any("zu groß" in h for h in kanal.hinweise)
        assert _alles(_kanal(server.port, make_session, max_nachricht_mb=1)) == []
    assert not any("BODY.PEEK" in b for b in pf.befehle)


def test_ab_datum_sucht_mit_since(make_session):
    pf = Postfach()
    pf.lege_ab(
        mail(("alt.pdf", PDF + b"a", "application/pdf")), datum=dt.date(2025, 12, 31)
    )
    pf.lege_ab(
        mail(("neu.pdf", PDF + b"n", "application/pdf"), message_id="<n@x>"),
        datum=dt.date(2026, 1, 1),
    )
    with ImapAttrappe(pf) as server:
        geholt = _alles(_kanal(server.port, make_session, ab=dt.date(2026, 1, 1)))
    assert [r.dateiname for r in geholt] == ["neu.pdf"]
    assert any(b == "UID SEARCH SINCE 01-Jan-2026" for b in pf.befehle)


def test_fehlender_ordner_und_keine_verbindung(make_session):
    with ImapAttrappe(Postfach()) as server:
        with pytest.raises(KanalError, match="Ordner"):
            _alles(_kanal(server.port, make_session, ordner="Gibtsnicht"))
        port = server.port
    with pytest.raises(KanalError, match="Verbindung"):
        _alles(_kanal(port, make_session))


# ---------------------------------------------------------------------------
# TLS mit eigener CA
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tls(tmp_path_factory):
    return zertifikate(tmp_path_factory.mktemp("tls"))


@pytest.mark.parametrize("modus", ["ssl", "starttls"])
def test_tls_mit_eigener_ca(make_session, tls, modus):
    ca_datei, kontext = tls
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", PDF, "application/pdf")))
    with ImapAttrappe(pf, modus=modus, kontext=kontext) as server:
        kanal = _kanal(
            server.port,
            make_session,
            host="localhost",
            verschluesselung=modus,
            ca_datei=str(ca_datei),
        )
        assert len(_alles(kanal)) == 1
    if modus == "starttls":
        assert pf.befehle.index("STARTTLS ") < pf.befehle.index("LOGIN ***")


def test_tls_ohne_passende_ca_oder_mit_falschem_namen_scheitert(make_session, tls):
    ca_datei, kontext = tls
    with ImapAttrappe(Postfach(), modus="ssl", kontext=kontext) as server:
        ohne_ca = _kanal(
            server.port, make_session, host="localhost", verschluesselung="ssl"
        )
        with pytest.raises(KanalError, match="Verbindung"):
            _alles(ohne_ca)
        falscher_name = EmailKanal(
            EmailPostfach(
                name="p",
                host="127.0.0.1",
                port=server.port,
                verschluesselung="ssl",
                benutzer="belege@firma.example",
                ca_datei=str(ca_datei),
            ),
            "geheim",
            DbGedaechtnis(make_session),
        )
        with pytest.raises(KanalError, match="Verbindung"):
            _alles(falscher_name)


def test_ssl_nutzt_pruefenden_kontext(monkeypatch, make_session):
    gesehen = {}

    def falsch_ssl(host, port, ssl_context=None, timeout=None):
        gesehen.update(host=host, port=port, kontext=ssl_context, timeout=timeout)
        raise imaplib.IMAP4.abort("Testabbruch")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", falsch_ssl)
    kanal = EmailKanal(
        EmailPostfach(name="p", host="imap.firma.example", benutzer="b"),
        "pw",
        DbGedaechtnis(make_session),
    )
    with pytest.raises(KanalError):
        _alles(kanal)
    assert gesehen["port"] == 993
    assert gesehen["kontext"].verify_mode.name == "CERT_REQUIRED"
    assert gesehen["kontext"].check_hostname is True
    assert gesehen["timeout"] == 60
