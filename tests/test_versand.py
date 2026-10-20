import smtplib
from datetime import date
from email import message_from_bytes
from email.policy import default as standard_policy

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_versandprotokolle, speichere_ausgangsrechnung
from accounti.erechnung.ausstellung import stelle_aus
from accounti.erechnung.versand import (
    SmtpVersand,
    VersandError,
    VersandKonfiguration,
    baue_nachricht,
    lade_versand,
    versende,
)
from accounti.konfiguration import KonfigurationError
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos

KONFIG = VersandKonfiguration.model_validate(
    {
        "absender": "Galerie Muster GmbH <rechnung@galerie-muster.example>",
        "bcc": "archiv@galerie-muster.example",
        "smtp": {"host": "smtp.example", "port": 587, "benutzer": "rechnung"},
    }
)


class FalscherSmtp:
    """Ersetzt smtplib.SMTP — merkt sich, was gesendet worden wäre."""

    gesendet: list = []
    fehler: Exception | None = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.schritte = ["verbinden"]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.schritte.append("starttls")

    def login(self, benutzer, passwort):
        self.schritte.append(f"login {benutzer}")

    def send_message(self, nachricht):
        if FalscherSmtp.fehler:
            raise FalscherSmtp.fehler
        FalscherSmtp.gesendet.append((self, nachricht))


@pytest.fixture(autouse=True)
def _zuruecksetzen():
    FalscherSmtp.gesendet = []
    FalscherSmtp.fehler = None


@pytest.fixture
def ausgestellt(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    archiv = BelegArchiv(tmp_path / "archiv")
    e = entwurf(kunde(), pos("Bilderrahmen Eiche", "250", "4"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2026, 3, 10))
        s.commit()
    return make_session, archiv


def _weg():
    return SmtpVersand(KONFIG, passwort="geheim", smtp_klasse=FalscherSmtp)


def test_konfiguration_mit_umgebungsvariable(tmp_path, monkeypatch):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        """
versand:
  absender: "Galerie <rechnung@galerie.example>"
  smtp:
    host: smtp.galerie.example
    benutzer: rechnung
    passwort: "${ACCOUNTI_SMTP_PASSWORT}"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACCOUNTI_SMTP_PASSWORT", "s3cr3t")
    k = lade_versand(pfad)
    assert k.smtp.passwort == "s3cr3t"
    assert k.smtp.port == 587
    assert k.smtp.verschluesselung == "starttls"
    monkeypatch.delenv("ACCOUNTI_SMTP_PASSWORT")
    with pytest.raises(KonfigurationError, match="ACCOUNTI_SMTP_PASSWORT"):
        lade_versand(pfad)


def test_fehlender_abschnitt(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text("mandant: {}\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="versand"):
        lade_versand(pfad)


def test_nachricht(ausgestellt):
    make_session, archiv = ausgestellt
    from accounti.db.repository import lade_ausgangsrechnung

    with make_session() as s:
        r = lade_ausgangsrechnung(s, "2026-0001")
    pdf = archiv.lese(r.pdf_hash)
    n = baue_nachricht(r, FIRMA, KONFIG, archiv, "zugferd", "kunde@example.org")
    assert n["To"] == "kunde@example.org"
    assert n["From"] == "Galerie Muster GmbH <rechnung@galerie-muster.example>"
    assert n["Bcc"] == "archiv@galerie-muster.example"
    assert n["Subject"] == "Rechnung 2026-0001 von Galerie Muster GmbH"
    assert n["Message-ID"].endswith("@galerie-muster.example>")
    text = n.get_body(("plain",)).get_content()
    assert "2026-0001" in text and "1.190,00" in text and "24.03.2026" in text
    (anhang,) = list(n.iter_attachments())
    assert anhang.get_filename() == "2026-0001.pdf"
    assert anhang.get_content_type() == "application/pdf"
    assert anhang.get_content() == pdf


def test_versand_erfolgreich_mit_protokoll(ausgestellt):
    make_session, archiv = ausgestellt
    with make_session() as s:
        p = versende(s, archiv, "2026-0001", FIRMA, KONFIG, _weg())
        s.commit()
        (gespeichert,) = lade_versandprotokolle(s, "2026-0001")
    assert p.erfolgreich and gespeichert.erfolgreich
    assert gespeichert.empfaenger == "rechnung@atelier-kundin.example"
    assert gespeichert.format == "zugferd"
    assert gespeichert.message_id
    ((verbindung, nachricht),) = FalscherSmtp.gesendet
    assert verbindung.host == "smtp.example"
    assert verbindung.schritte == ["verbinden", "starttls", "login rechnung"]
    geparst = message_from_bytes(nachricht.as_bytes(), policy=standard_policy)
    (anhang,) = list(geparst.iter_attachments())
    assert anhang.get_filename() == "2026-0001.pdf"


def test_xrechnung_als_xml_und_anderer_empfaenger(ausgestellt):
    make_session, archiv = ausgestellt
    with make_session() as s:
        p = versende(
            s,
            archiv,
            "2026-0001",
            FIRMA,
            KONFIG,
            _weg(),
            format="xrechnung",
            an="einkauf@example.org",
        )
        s.commit()
    ((_, nachricht),) = FalscherSmtp.gesendet
    (anhang,) = list(nachricht.iter_attachments())
    assert anhang.get_filename() == "2026-0001.xml"
    assert anhang.get_content_type() == "application/xml"
    assert p.empfaenger == "einkauf@example.org"


def test_fehlschlag_wird_protokolliert(ausgestellt):
    make_session, archiv = ausgestellt
    FalscherSmtp.fehler = smtplib.SMTPRecipientsRefused({"x": (550, b"unbekannt")})
    with make_session() as s:
        p = versende(s, archiv, "2026-0001", FIRMA, KONFIG, _weg())
        s.commit()
        (gespeichert,) = lade_versandprotokolle(s, "2026-0001")
    assert not p.erfolgreich
    assert not gespeichert.erfolgreich
    assert "unbekannt" in gespeichert.fehler


def test_entwurf_kann_nicht_versendet_werden(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    e = entwurf(kunde(), pos("Rahmen", "100"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        with pytest.raises(VersandError, match="ausgestellt"):
            versende(s, BelegArchiv(tmp_path), str(e.id)[:8], FIRMA, KONFIG, _weg())


def test_ohne_empfaenger(ausgestellt, monkeypatch):
    make_session, archiv = ausgestellt
    with make_session() as s:
        from accounti.db.tabellen import AusgangsrechnungRow

        s.query(AusgangsrechnungRow).update({"kunde_email": None})
        with pytest.raises(VersandError, match="Empfänger"):
            versende(s, archiv, "2026-0001", FIRMA, KONFIG, _weg())
