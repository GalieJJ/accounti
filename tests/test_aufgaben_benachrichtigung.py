"""Tagesübersicht statt Einzelmails (Akzeptanz 5) — über lokale Gegenstellen.

E-Mails gehen per echtem ``smtplib`` an einen SMTP-Testserver auf 127.0.0.1, der
Webhook an einen lokalen HTTP-Server. Nichts verlässt den Rechner.
"""

import socketserver
import threading
from datetime import date, datetime, timedelta

import pytest

from accounti.aufgaben import melde_aufgabe
from accounti.aufgaben.benachrichtigung import (
    KANAELE,
    EmailKanal,
    KanalError,
    Tagesuebersicht,
    WebhookKanal,
    baue_kanaele,
    stelle_zusammen,
    versende_tagesuebersichten,
)
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.db import init_db, session_factory
from accounti.db.repo_aufgaben import (
    aktualisiere_aufgabe,
    lade_aufgabe,
    lade_benachrichtigungen,
    lade_kommentare,
)
from accounti.erechnung.versand import SmtpVersand, VersandKonfiguration
from accounti.models.aufgaben import AufgabenStatus, Objekt, Prioritaet
from tests.aufgaben_hilfe import SmtpTestserver, WebhookTestserver

TAG = date(2026, 10, 20)
UHR = datetime(2026, 10, 20, 7, 0)


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


@pytest.fixture
def smtp():
    server = SmtpTestserver().starte()
    yield server
    server.stoppe()


@pytest.fixture
def webhook():
    server = WebhookTestserver().starte()
    yield server
    server.stoppe()


def _einstellungen(**benachrichtigung):
    werte = {
        "empfaenger": {
            "jan": "jan@firma.example",
            "gemeinsam": "buchhaltung@firma.example",
            "@leitung": "chefin@firma.example",
        },
        "absender": "accounti <accounti@firma.example>",
    }
    werte.update(benachrichtigung)
    return AufgabenEinstellungen.model_validate({"benachrichtigung": werte})


def _email(smtp, einstellungen):
    konfig = VersandKonfiguration.model_validate(
        {
            "absender": "Firma <rechnung@firma.example>",
            "smtp": {
                "host": "127.0.0.1",
                "port": smtp.port,
                "verschluesselung": "keine",
            },
        }
    )
    return EmailKanal(
        einstellungen.benachrichtigung.empfaenger,
        einstellungen.benachrichtigung.absender or konfig.absender,
        SmtpVersand(konfig),
    )


def _aufgabe(s, nr, faellig, **kw):
    werte = {"titel": f"Aufgabe {nr}", "faellig_am": faellig, "jetzt": UHR}
    werte.update(kw)
    return melde_aufgabe(s, "beleg_fehlt", Objekt("transaktion", f"tx{nr}"), **werte)


def _versende(make_session, einstellungen, kanaele, stichtag=TAG):
    with make_session() as s:
        lauf = versende_tagesuebersichten(
            s,
            einstellungen,
            kanaele,
            stichtag=stichtag,
            jetzt=datetime.combine(stichtag, UHR.time()),
        )
        s.commit()
    return lauf


@pytest.fixture
def fuenf_aufgaben(make_session):
    with make_session() as s:
        _aufgabe(s, 1, TAG, zustaendig="jan")  # heute fällig
        _aufgabe(s, 2, TAG - timedelta(days=2), zustaendig="jan")  # überfällig
        _aufgabe(s, 3, TAG)  # gemeinsame Liste
        nicht_faellig = _aufgabe(s, 4, TAG + timedelta(days=30), zustaendig="jan")
        aktualisiere_aufgabe(
            s, nicht_faellig.aufgabe.model_copy(update={"gemeldet_am": TAG})
        )
        _aufgabe(s, 5, TAG, zustaendig="erika")  # erika hat keine Adresse
        s.commit()


def test_faellige_aufgaben_kommen_gebuendelt(make_session, smtp, fuenf_aufgaben):
    """Akzeptanz 5: vier fällige Aufgaben → zwei Tagesübersichten, keine Einzelmails."""
    e = _einstellungen()
    lauf = _versende(make_session, e, {"email": _email(smtp, e)})
    assert len(smtp.nachrichten) == 2
    post = {an[0]: n for _, an, n in smtp.nachrichten}
    jan = post["jan@firma.example"]
    text = jan.get_body(("plain",)).get_content()
    assert "#1" in text and "#2" in text and "#4" not in text and "#3" not in text
    assert "fällig heute" in text and "2 Tage überfällig" in text
    assert jan["Subject"] == "accounti: 2 fällig — Aufgaben am 20.10.2026"
    assert jan["Auto-Submitted"] == "auto-generated"  # RFC 3834
    assert jan["From"] == "accounti <accounti@firma.example>"
    gemeinsam = post["buchhaltung@firma.example"].get_body(("plain",)).get_content()
    assert "#3" in gemeinsam and "#5" in gemeinsam and "zuständig: erika" in gemeinsam
    assert "accounti aufgaben liste --unzugewiesen" in gemeinsam
    assert [z.erfolgreich for z in lauf.zustellungen] == [True, True]
    with make_session() as s:
        protokoll = lade_benachrichtigungen(s, tag=TAG)
        assert {(p.empfaenger, p.adresse, tuple(p.aufgaben)) for p in protokoll} == {
            ("jan", "jan@firma.example", (1, 2)),
            ("gemeinsam", "buchhaltung@firma.example", (3, 5)),
        }
        eins = lade_aufgabe(s, "1")
    assert eins.erinnerungsstufe == 1 and eins.gemeldet_am == TAG


def test_hoechstens_eine_uebersicht_am_tag(make_session, smtp, fuenf_aufgaben):
    e = _einstellungen()
    kanaele = {"email": _email(smtp, e)}
    _versende(make_session, e, kanaele)
    with make_session() as s:  # neue Aufgabe am selben Tag
        _aufgabe(s, 6, TAG, zustaendig="jan")
        s.commit()
    zweiter = _versende(make_session, e, kanaele)
    assert len(smtp.nachrichten) == 2
    assert [z.uebersprungen for z in zweiter.zustellungen] == [True]
    # am nächsten Tag kommt die neue, die alten haben keine neue Stufe
    _versende(make_session, e, kanaele, stichtag=TAG + timedelta(days=1))
    assert len(smtp.nachrichten) == 3
    text = smtp.nachrichten[-1][2].get_body(("plain",)).get_content()
    assert "#6" in text and "#1" not in text
    # drei Tage nach Fälligkeit: 1. Erinnerung für #1, #3, #5 (und #2 schon früher)
    _versende(make_session, e, kanaele, stichtag=TAG + timedelta(days=3))
    an = sorted(a[0] for _, a, _ in smtp.nachrichten[3:])
    assert an == ["buchhaltung@firma.example", "jan@firma.example"]


def test_neue_aufgaben_vor_faelligkeit(make_session, smtp):
    e = _einstellungen()
    with make_session() as s:
        _aufgabe(s, 1, TAG + timedelta(days=10), zustaendig="jan")
        s.commit()
    _versende(make_session, e, {"email": _email(smtp, e)})
    ((_, _, n),) = smtp.nachrichten
    assert "Neu (1)" in n.get_body(("plain",)).get_content()
    assert n["Subject"] == "accounti: 1 neu — Aufgaben am 20.10.2026"
    ohne_neue = _einstellungen(neue_melden=False)
    with make_session() as s:
        _aufgabe(s, 2, TAG + timedelta(days=10), zustaendig="jan")
        s.commit()
    _versende(make_session, ohne_neue, {"email": _email(smtp, e)}, TAG + timedelta(1))
    assert len(smtp.nachrichten) == 1


def test_leere_uebersicht_wird_nicht_versendet(make_session, smtp):
    e = _einstellungen()
    lauf = _versende(make_session, e, {"email": _email(smtp, e)})
    assert lauf.zustellungen == [] and smtp.nachrichten == []


def test_fehlschlag_wird_protokolliert_und_nachgeholt(
    make_session, smtp, fuenf_aufgaben
):
    e = _einstellungen()
    kanaele = {"email": _email(smtp, e)}
    smtp.ablehnen = True
    lauf = _versende(make_session, e, kanaele)
    assert not any(z.erfolgreich for z in lauf.zustellungen)
    assert "Postfach unbekannt" in (lauf.zustellungen[0].fehler or "")
    with make_session() as s:
        assert not any(p.erfolgreich for p in lade_benachrichtigungen(s))
        assert lade_aufgabe(s, "1").erinnerungsstufe == 0  # nicht als gemeldet
    smtp.ablehnen = False
    nochmal = _versende(make_session, e, kanaele)
    assert all(z.erfolgreich for z in nochmal.zustellungen)
    assert len(smtp.nachrichten) == 2


def test_eskalation_mit_kopie_an_das_ziel(make_session, smtp):
    e = AufgabenEinstellungen.model_validate(
        {
            "erinnerung": {"stufen": [0, 3, 7], "eskalation_an": "@leitung"},
            "benachrichtigung": _einstellungen().benachrichtigung.model_dump(),
        }
    )
    with make_session() as s:
        _aufgabe(s, 1, TAG - timedelta(days=7), zustaendig="jan")
        s.commit()
    _versende(make_session, e, {"email": _email(smtp, e)})
    post = {
        an[0]: n.get_body(("plain",)).get_content() for _, an, n in smtp.nachrichten
    }
    assert "eskaliert an @leitung" in post["jan@firma.example"]
    assert "Eskaliert (1)" in post["chefin@firma.example"]
    assert "zuständig: jan" in post["chefin@firma.example"]
    with make_session() as s:
        a = lade_aufgabe(s, "1")
        verlauf = [k.text for k in lade_kommentare(s, aufgabe_id=a.id)]
    assert a.prioritaet is Prioritaet.HOCH and a.erinnerungsstufe == 3
    assert any("eskaliert an @leitung" in t for t in verlauf)


def test_webhook(make_session, webhook, fuenf_aufgaben):
    e = _einstellungen(kanaele=["webhook"], webhook={"url": webhook.url})
    kanal = WebhookKanal(webhook.url, timeout=5)
    lauf = _versende(make_session, e, {"webhook": kanal})
    assert len(webhook.anfragen) == 2
    assert all(a["typ"] == "application/json" for a in webhook.anfragen)
    jan = next(a["body"] for a in webhook.anfragen if a["body"]["empfaenger"] == "jan")
    assert "#1" in jan["text"]  # Slack/Mattermost zeigen „text“
    assert [x["nr"] for x in jan["aufgaben"]] == [1, 2]
    assert jan["aufgaben"][0]["abschnitt"] == "faellig" and jan["tag"] == "2026-10-20"
    # das Protokoll kennt den Webhook, aber nicht sein Geheimnis im Pfad
    assert all(
        z.adresse == f"{webhook.url.rsplit('/', 2)[0]}/…" for z in lauf.zustellungen
    )


def test_teilausfall_eines_kanals(make_session, smtp, webhook):
    e = _einstellungen(kanaele=["email", "webhook"], webhook={"url": webhook.url})
    kanaele = {"email": _email(smtp, e), "webhook": WebhookKanal(webhook.url, 5)}
    with make_session() as s:
        _aufgabe(s, 1, TAG, zustaendig="jan")
        s.commit()
    webhook.status = 500
    lauf = _versende(make_session, e, kanaele)
    assert {z.kanal: z.erfolgreich for z in lauf.zustellungen} == {
        "email": True,
        "webhook": False,
    }
    with make_session() as s:
        assert lade_aufgabe(s, "1").erinnerungsstufe == 0  # erst, wenn alle zugestellt
    webhook.status = 200
    nochmal = _versende(make_session, e, kanaele)
    assert {z.kanal: z.uebersprungen for z in nochmal.zustellungen} == {
        "email": True,
        "webhook": False,
    }
    assert len(smtp.nachrichten) == 1 and len(webhook.anfragen) == 2
    with make_session() as s:
        assert lade_aufgabe(s, "1").erinnerungsstufe == 1


def test_ohne_adresse_fuer_die_gemeinsame_liste(make_session, smtp):
    e = AufgabenEinstellungen()
    with make_session() as s:
        _aufgabe(s, 1, TAG)
        s.commit()
    lauf = _versende(make_session, e, {"email": _email(smtp, e)})
    (z,) = lauf.zustellungen
    assert not z.erfolgreich and "empfaenger.gemeinsam" in (z.fehler or "")


def test_vorschau_aendert_nichts(make_session, fuenf_aufgaben):
    e = _einstellungen()
    with make_session() as s:
        uebersichten = stelle_zusammen(s, e, TAG)
        assert [u.empfaenger for u in uebersichten] == ["gemeinsam", "jan"]
        assert lade_aufgabe(s, "1").erinnerungsstufe == 0
    jan = uebersichten[1]
    assert jan.offen == 3 and jan.ueberfaellig == 1
    assert "Offen insgesamt: 3, davon überfällig: 1." in jan.text()


def test_erledigte_aufgaben_fehlen(make_session, smtp, fuenf_aufgaben):
    from accounti.aufgaben import erledige

    e = _einstellungen()
    with make_session() as s:
        erledige(s, "3", von="jan", text="belegfrei")
        erledige(s, "5", von="jan", text="belegfrei")
        s.commit()
    _versende(make_session, e, {"email": _email(smtp, e)})
    assert [an for _, an, _ in smtp.nachrichten] == [["jan@firma.example"]]
    with make_session() as s:
        assert lade_aufgabe(s, "3").status is AufgabenStatus.ERLEDIGT


def test_kanaele_aus_der_konfiguration(tmp_path, smtp):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        f"""
versand:
  absender: "Firma <rechnung@firma.example>"
  smtp: {{host: 127.0.0.1, port: {smtp.port}, verschluesselung: keine}}
aufgaben:
  benachrichtigung:
    kanaele: [email, webhook]
    webhook: {{url: "http://127.0.0.1:9/hook"}}
""",
        encoding="utf-8",
    )
    from accounti.aufgaben.einstellungen import lade_aufgaben_einstellungen

    kanaele, fehler = baue_kanaele(lade_aufgaben_einstellungen(pfad), pfad)
    assert set(kanaele) == {"email", "webhook"} and fehler == {}
    assert kanaele["email"].absender == "Firma <rechnung@firma.example>"
    ohne_versand = tmp_path / "ohne.yaml"
    ohne_versand.write_text("aufgaben: {}\n", encoding="utf-8")
    kanaele, fehler = baue_kanaele(AufgabenEinstellungen(), ohne_versand)
    assert kanaele == {} and "versand" in fehler["email"]


# ---------------------------------------------------------------------------
# Teilausfälle, unerwartete Fehler, Abbruch
# ---------------------------------------------------------------------------


class Attrappe:
    """Kanal ohne Netz: merkt sich, was er zustellt; scheitert für ausgewählte
    Empfänger (oder alle) mit dem angegebenen Fehler."""

    def __init__(self, name="email", scheitert_bei=(), fehler=None, immer=False):
        self.name = name
        self.post = []
        self.scheitert_bei = set(scheitert_bei)
        self.immer = immer
        self.fehler = fehler or KanalError("550 Postfach voll")

    def adresse(self, uebersicht):
        return f"{uebersicht.empfaenger}@firma.example"

    def sende(self, uebersicht):
        if self.immer or uebersicht.empfaenger in self.scheitert_bei:
            raise self.fehler
        self.post.append(
            (
                uebersicht.tag,
                uebersicht.empfaenger,
                [e.abschnitt for e in uebersicht.eintraege],
            )
        )


def _eskalierend():
    return AufgabenEinstellungen.model_validate(
        {
            "erinnerung": {"stufen": [0, 3, 7], "eskalation_an": "@leitung"},
            "benachrichtigung": _einstellungen().benachrichtigung.model_dump(),
        }
    )


def _verlauf(make_session, nr):
    with make_session() as s:
        a = lade_aufgabe(s, str(nr))
        return a, [k.text for k in lade_kommentare(s, aufgabe_id=a.id)]


def test_eskalation_erst_vermerkt_wenn_auch_die_kopie_ankam(make_session):
    """Fällt nur der Kanal des Eskalationsziels aus, gilt die Eskalation nicht als
    gemeldet — der nächste Lauf eskaliert erneut, statt sie zu verlieren."""
    e = _eskalierend()
    with make_session() as s:
        _aufgabe(s, 1, TAG - timedelta(days=7), zustaendig="jan")
        s.commit()
    kanal = Attrappe(scheitert_bei={"@leitung"})
    _versende(make_session, e, {"email": kanal})
    assert [p[1] for p in kanal.post] == ["jan"]
    a, verlauf = _verlauf(make_session, 1)
    assert a.erinnerungsstufe == 2 and a.prioritaet is Prioritaet.NORMAL
    assert not any("eskaliert" in t for t in verlauf)

    kanal.scheitert_bei.clear()
    _versende(make_session, e, {"email": kanal}, stichtag=TAG + timedelta(days=1))
    assert [(p[1], p[2]) for p in kanal.post[1:]] == [
        ("@leitung", ["eskaliert"]),
        ("jan", ["faellig"]),
    ]
    a, verlauf = _verlauf(make_session, 1)
    assert a.erinnerungsstufe == 3 and a.prioritaet is Prioritaet.HOCH
    assert sum("eskaliert an @leitung" in t for t in verlauf) == 1
    # danach ist Ruhe
    _versende(make_session, e, {"email": kanal}, stichtag=TAG + timedelta(days=2))
    assert len(kanal.post) == 3


def test_eskalation_wenn_das_ziel_heute_schon_post_hatte(make_session):
    """Hatte die Leitung heute schon ihre Übersicht, entfällt die Kopie — dann ist
    auch die Eskalation nicht gemeldet und kommt am nächsten Tag."""
    e = _eskalierend()
    kanal = Attrappe()
    with make_session() as s:
        _aufgabe(s, 1, TAG, rolle="leitung")
        s.commit()
    _versende(make_session, e, {"email": kanal})
    with make_session() as s:
        _aufgabe(s, 2, TAG - timedelta(days=7), zustaendig="jan")
        s.commit()
    lauf = _versende(make_session, e, {"email": kanal})
    assert {z.empfaenger: z.uebersprungen for z in lauf.zustellungen} == {
        "@leitung": True,
        "jan": False,
    }
    a, verlauf = _verlauf(make_session, 2)
    assert a.erinnerungsstufe == 2 and not any("eskaliert" in t for t in verlauf)
    _versende(make_session, e, {"email": kanal}, stichtag=TAG + timedelta(days=1))
    assert ("@leitung", ["eskaliert"]) in [(p[1], p[2]) for p in kanal.post]
    assert _verlauf(make_session, 2)[0].erinnerungsstufe == 3


def test_unerwarteter_kanalfehler_bricht_den_lauf_nicht_ab(
    make_session, fuenf_aufgaben
):
    """Ein Fehler außerhalb der erwarteten Arten (z.B. ValueError) ist ein
    Fehlschlag dieser Zustellung — die übrigen gehen hinaus und stehen im
    Protokoll, ein zweiter Lauf verschickt nichts doppelt."""
    e = _einstellungen(
        kanaele=["email", "webhook"], webhook={"url": "https://x.example/h"}
    )
    email = Attrappe()
    kaputt = Attrappe("webhook", fehler=ValueError("kaputt"), immer=True)
    lauf = _versende(make_session, e, {"email": email, "webhook": kaputt})
    assert {(z.empfaenger, z.kanal): z.erfolgreich for z in lauf.zustellungen} == {
        ("gemeinsam", "email"): True,
        ("gemeinsam", "webhook"): False,
        ("jan", "email"): True,
        ("jan", "webhook"): False,
    }
    assert "ValueError" in (lauf.zustellungen[1].fehler or "")
    with make_session() as s:
        assert len(lade_benachrichtigungen(s, tag=TAG)) == 4
    _versende(make_session, e, {"email": email, "webhook": kaputt})
    assert len(email.post) == 2


def test_protokoll_bleibt_auch_bei_abbruch(make_session, fuenf_aufgaben):
    """Mit ``sichern`` (die CLI übergibt ``commit``) steht jede Zustellung sofort
    fest — bricht der Lauf danach ab, verschickt der nächste nichts doppelt."""

    class Abbruch(BaseException):
        pass

    e = _einstellungen()
    kanal = Attrappe(scheitert_bei={"jan"}, fehler=Abbruch())
    with make_session() as s, pytest.raises(Abbruch):
        versende_tagesuebersichten(
            s, e, {"email": kanal}, stichtag=TAG, jetzt=UHR, sichern=s.commit
        )
    with make_session() as s:
        protokoll = lade_benachrichtigungen(s, tag=TAG)
    assert [(p.empfaenger, p.erfolgreich) for p in protokoll] == [("gemeinsam", True)]
    kanal.scheitert_bei.clear()
    _versende(make_session, e, {"email": kanal})
    assert [p[1] for p in kanal.post] == ["gemeinsam", "jan"]
    with make_session() as s:
        assert lade_aufgabe(s, "3").erinnerungsstufe == 1  # aus der ersten Zustellung


class _KeinHttp(socketserver.StreamRequestHandler):
    def handle(self):
        self.rfile.readline()
        self.wfile.write(b"kein http\r\n")


@pytest.mark.parametrize("art", ["ohne_schema", "kein_http", "verweigert"])
def test_webhook_fehler_sind_kanalfehler_ohne_geheimnis(art):
    server = None
    if art == "ohne_schema":
        url = "hooks.example.com/services/T0/B0/geheim"
    elif art == "kein_http":
        server = socketserver.TCPServer(("127.0.0.1", 0), _KeinHttp)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/geheim"
    else:
        frei = socketserver.TCPServer(("127.0.0.1", 0), _KeinHttp)
        port = frei.server_address[1]
        frei.server_close()
        url = f"http://127.0.0.1:{port}/geheim"
    try:
        with pytest.raises(KanalError) as fehler:
            WebhookKanal(url, timeout=5).sende(Tagesuebersicht("jan", TAG))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    assert "geheim" not in str(fehler.value)


def test_webhook_text_ohne_fremdes_markup(make_session, webhook):
    """Titel enthalten Fremddaten (Kontaktname, Dateiname, Buchungstext). Im Feld
    ``text`` dürfen sie weder alle benachrichtigen noch Links unterschieben."""
    boese = (
        "<!channel> <https://evil.example/login|Zahlung freigeben> "
        "[hier](https://evil.example) @all & Co"
    )
    with make_session() as s:
        _aufgabe(s, 1, TAG, titel=f"Kontakt prüfen: {boese}", zustaendig="jan")
        s.commit()
    e = _einstellungen(kanaele=["webhook"], webhook={"url": webhook.url})
    _versende(make_session, e, {"webhook": WebhookKanal(webhook.url, 5)})
    (anfrage,) = webhook.anfragen
    text = anfrage["body"]["text"]
    assert "<" not in text and ">" not in text and "](" not in text
    assert "@all" not in text and "@channel" not in text
    assert "&lt;!channel&gt;" in text and "&amp; Co" in text
    # die strukturierten Felder bleiben roh — wer sie anzeigt, maskiert selbst
    assert anfrage["body"]["aufgaben"][0]["titel"].endswith("@all & Co")


def test_eigener_kanal_aus_der_registry(tmp_path, monkeypatch):
    attrappe = Attrappe("teams")
    monkeypatch.setitem(KANAELE, "teams", lambda einstellungen, pfad: attrappe)
    e = AufgabenEinstellungen.model_validate(
        {"benachrichtigung": {"kanaele": ["teams", "brieftaube"]}}
    )
    kanaele, fehler = baue_kanaele(e, tmp_path / "fehlt.yaml")
    assert kanaele == {"teams": attrappe}
    assert "unbekannter Kanal brieftaube" in fehler["brieftaube"]
    assert "teams" in fehler["brieftaube"]  # nennt, was es gibt
