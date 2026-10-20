from datetime import date

import pytest

from accounti.belege.kanaele.einstellungen import (
    KanalEinstellungen,
    lade_belegkanaele,
    loese_auf,
)
from accounti.konfiguration import KonfigurationError


def _konfig(tmp_path, text):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


def test_ohne_datei_und_ohne_abschnitt_gelten_standards(tmp_path):
    for e in (
        lade_belegkanaele(tmp_path / "gibtsnicht.yaml"),
        lade_belegkanaele(_konfig(tmp_path, "mandant:\n  name: X\n")),
    ):
        assert e.email == []
        assert e.connectoren == []
        assert e.webhook.host == "127.0.0.1"
        assert e.webhook.port == 8410
        assert e.max_groesse_mb == 25
        assert e.pruefung().max_bytes == 25 * 1024 * 1024
        assert e.pruefung().typen == {"pdf", "xml", "jpeg", "png", "tiff"}


def test_postfach_webhook_und_connector_werden_gelesen(tmp_path):
    pfad = _konfig(
        tmp_path,
        """
belegkanaele:
  max_groesse_mb: 10
  dateitypen: [pdf, xml]
  email:
    - name: rechnungen
      host: imap.firma.example
      benutzer: rechnungen@firma.example
      passwort: "${ACCOUNTI_IMAP_PASSWORT}"
      ab: 2026-01-01
      nach_abholen: verschieben
      ziel_ordner: Belege/abgeholt
  webhook:
    port: 9000
    max_dateien: 3
  connectoren:
    - name: portal
      typ: json
      basis_url: https://portal.example/api
""",
    )
    e = lade_belegkanaele(pfad)
    (p,) = e.email
    assert p.name == "rechnungen"
    assert p.verschluesselung == "ssl"
    assert p.port_oder_standard == 993
    assert p.ordner == "INBOX"
    assert p.ab == date(2026, 1, 1)
    assert p.passwort == "${ACCOUNTI_IMAP_PASSWORT}"  # erst beim Bau aufgelöst
    assert e.webhook.port == 9000
    assert e.webhook.max_dateien == 3
    (c,) = e.connectoren
    assert (c.name, c.typ) == ("portal", "json")
    assert c.einstellungen() == {"basis_url": "https://portal.example/api"}
    assert e.pruefung().typen == {"pdf", "xml"}
    assert e.pruefung().max_bytes == 10 * 1024 * 1024
    assert e.postfach("rechnungen") is p
    assert e.connector("portal") is c


@pytest.mark.parametrize(
    "zeile",
    ['passwort: "geheim123"', 'passwort: "x${VAR}"', "passwort: ${VAR} und mehr"],
)
def test_passwort_im_klartext_ist_ein_fehler(tmp_path, zeile):
    pfad = _konfig(
        tmp_path,
        f"""
belegkanaele:
  email:
    - name: p
      host: imap.firma.example
      benutzer: b
      {zeile}
""",
    )
    with pytest.raises(KonfigurationError) as fehler:
        lade_belegkanaele(pfad)
    text = str(fehler.value)
    assert "Klartext" in text
    assert "geheim123" not in text
    assert "kanaele zugang email p" in text


def test_variable_wird_erst_beim_aufloesen_gebraucht(monkeypatch):
    monkeypatch.setenv("ACCOUNTI_TEST_PW", "s3cr3t")
    assert loese_auf("${ACCOUNTI_TEST_PW}") == "s3cr3t"
    assert loese_auf("Bearer ${ACCOUNTI_TEST_PW}") == "Bearer s3cr3t"
    monkeypatch.delenv("ACCOUNTI_TEST_PW")
    with pytest.raises(KonfigurationError, match="ACCOUNTI_TEST_PW"):
        loese_auf("${ACCOUNTI_TEST_PW}")


def test_unverschluesselt_nur_fuer_localhost():
    basis = {"name": "p", "benutzer": "b", "verschluesselung": "keine"}
    ok = KanalEinstellungen.model_validate({"email": [{**basis, "host": "127.0.0.1"}]})
    assert ok.email[0].port_oder_standard == 143
    with pytest.raises(ValueError, match="nur für localhost"):
        KanalEinstellungen.model_validate({"email": [{**basis, "host": "mail.x.de"}]})


def test_verschieben_braucht_ziel_ordner():
    with pytest.raises(ValueError, match="ziel_ordner"):
        KanalEinstellungen.model_validate(
            {
                "email": [
                    {
                        "name": "p",
                        "host": "h.example",
                        "benutzer": "b",
                        "nach_abholen": "verschieben",
                    }
                ]
            }
        )


def test_doppelte_namen_und_unbekannte_dateitypen(tmp_path):
    zwei = [{"name": "p", "host": "h.example", "benutzer": "b"}] * 2
    with pytest.raises(ValueError, match="doppelt"):
        KanalEinstellungen.model_validate({"email": zwei})
    with pytest.raises(ValueError, match="doppelt"):
        KanalEinstellungen.model_validate(
            {"connectoren": [{"name": "c", "typ": "json"}] * 2}
        )
    with pytest.raises(ValueError, match="docx"):
        KanalEinstellungen.model_validate({"dateitypen": ["pdf", "docx"]})


def test_fehler_im_abschnitt_nennt_den_pfad(tmp_path):
    pfad = _konfig(
        tmp_path,
        "belegkanaele:\n  email:\n    - name: p\n      host: h.example\n",
    )
    with pytest.raises(KonfigurationError, match=r"belegkanaele.*email.0.benutzer"):
        lade_belegkanaele(pfad)
