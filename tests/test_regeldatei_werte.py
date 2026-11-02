"""Werte der Regeldatei und ``regeln uebernehmen`` (Gesamttest 10b-1, Runde 3).

* gegen:regeln:3 — der Lader prüfte die Werte nicht: ein leeres Konto wurde „None“,
  ``soll_konto: 0420`` (YAML 1.1: Oktalzahl) wurde 272, ``muster: ''`` traf jeden
  Umsatz; gebucht wurde automatisch auf Konten, die es nicht gibt.
* gw2-regeln N-1 / gw2-web B3 — eine Datei, die nicht UTF-8 ist, ein Verzeichnis,
  ``steuer_schluessel: neun`` gaben Traceback bzw. 500.
* gw2-merge B1 — ``feld: gegenkonto_iban`` war vor N-2 wirksam und wurde abgelehnt.
* gegen:regeln:1 — ein zweiter Lauf von ``regeln uebernehmen`` (``--name``, wie die
  Ausgabe empfiehlt) stellte seinen Eintrag vor die früher übernommenen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from accounti.db.repo_kontierung import lade_kontierungsregeln
from accounti.klassifikation.lernen import lade_regelwerk, uebernehme_aus_datei
from accounti.klassifikation.regeln_loader import lade_regeln
from accounti.konfiguration import KonfigurationError
from tests.pruefung_hilfe import make_session_fixture, umsatz  # noqa: F401


def _datei(tmp_path: Path, text: str) -> Path:
    datei = tmp_path / "regeln.yaml"
    datei.write_text(text, encoding="utf-8")
    return datei


def _regel(**werte: str) -> str:
    felder = {
        "name": "telekom",
        "muster": "telekom",
        "soll_konto": "'4920'",
        "haben_konto": "'1200'",
    }
    felder.update(werte)
    zeilen = [f"  {k}: {v}" if v is not None else f"  {k}:" for k, v in felder.items()]
    return "-" + "\n".join(zeilen)[1:] + "\n"


@pytest.mark.parametrize(
    ("werte", "erwartet"),
    [
        ({"soll_konto": None}, r"Regel telekom: soll_konto: \(leer\) ist keine"),
        ({"soll_konto": "272"}, "272 ist keine Kontonummer .*Anführungszeichen"),
        ({"haben_konto": "'12x0'"}, "Regel telekom: haben_konto: 12x0 ist keine"),
        ({"muster": "''"}, "Regel telekom: muster '' — ein nicht leerer Text"),
        ({"muster": "4711"}, "Regel telekom: muster 4711 — ein nicht leerer Text"),
        ({"steuer_schluessel": "neun"}, "Regel telekom: steuer_schluessel 'neun'"),
        ({"confidence": "hoch"}, "Regel telekom: confidence 'hoch'"),
    ],
    ids=["konto_leer", "konto_272", "konto_text", "muster_leer", "muster_zahl",
         "schluessel_text", "confidence_text"],
)  # fmt: skip
def test_ungueltige_werte_sind_konfigurationsfehler_mit_regelname(
    tmp_path, werte, erwartet
):
    datei = _datei(tmp_path, _regel(**werte))
    with pytest.raises(KonfigurationError, match=erwartet) as info:
        lade_regeln(datei)
    assert str(datei) in str(info.value)


def test_fuehrende_null_bleibt_kontonummer(tmp_path):
    """``0420`` ohne Anführungszeichen liest YAML 1.1 als Oktalzahl 272 — der Lader
    behält den Text (Konto 0420), Zahlen ohne führende Null bleiben Konten."""
    datei = _datei(
        tmp_path,
        _regel(soll_konto="0420", haben_konto="1200", steuer_schluessel="'9'"),
    )
    [regel] = lade_regeln(datei)
    assert (regel.soll_konto, regel.haben_konto) == ("0420", "1200")
    assert regel.steuer_schluessel == 9


def test_regeldatei_nicht_utf8_oder_verzeichnis(tmp_path):
    datei = tmp_path / "regeln.yaml"
    datei.write_bytes(_regel(muster="Bürobedarf").encode("latin-1"))
    with pytest.raises(KonfigurationError, match="keine UTF-8-Datei"):
        lade_regeln(datei)
    datei.unlink()
    datei.mkdir()
    with pytest.raises(KonfigurationError, match="nicht lesbar"):
        lade_regeln(datei)


def test_feld_gegenkonto_iban_bleibt_wirksam(tmp_path):
    """gw2-merge B1: Abgleich über die IBAN der Gegenpartei (vor N-2 wirksam)."""
    datei = _datei(
        tmp_path,
        _regel(
            name="vermieter_iban",
            muster="DE02120300000000202051",
            feld="gegenkonto_iban",
            soll_konto="'4210'",
        ),
    )
    [regel] = lade_regeln(datei)
    miete = umsatz(
        "-1000.00", zweck="Miete Oktober", name="Hausverwaltung",
        gegenkonto_iban="DE02120300000000202051",
    )  # fmt: skip
    assert regel.passt(miete)
    assert not regel.passt(umsatz("-1000.00", zweck="Miete", name="Hausverwaltung"))


def test_uebernahme_prueft_die_werte_wie_der_lader(make_session, tmp_path):
    datei = _datei(
        tmp_path,
        _regel(name="gelernt_leer", soll_konto=None)
        + _regel(name="gelernt_alles", muster="''")
        + _regel(name="gelernt_anlage", soll_konto="0420", muster="maschine")
        + _regel(name="gelernt_iban", muster="DE0212", feld="gegenkonto_iban"),
    )
    with make_session() as s:
        e = uebernehme_aus_datei(s, datei, "jan")
        s.commit()
        regeln = {r.name: r for r in lade_kontierungsregeln(s)}
    assert sorted(e.ungueltig) == ["gelernt_alles", "gelernt_leer"]
    assert "soll_konto: (leer) ist keine Kontonummer" in e.gruende["gelernt_leer"]
    assert str(datei) not in e.gruende["gelernt_leer"]
    assert sorted(regeln) == ["gelernt_anlage", "gelernt_iban"]
    assert regeln["gelernt_anlage"].soll_konto == "0420"
    assert regeln["gelernt_iban"].feld == "gegenkonto_iban"


@pytest.mark.parametrize(
    "inhalt",
    [b"- name: gelernt_x\n  haben: [1200\n", "- muster: B\xfcro\n".encode("latin-1")],
    ids=["yaml", "latin1"],
)
def test_uebernahme_mit_kaputter_datei_meldet_konfigurationsfehler(
    make_session, tmp_path, inhalt
):
    datei = tmp_path / "regeln.yaml"
    datei.write_bytes(inhalt)
    with make_session() as s, pytest.raises(KonfigurationError):
        uebernehme_aus_datei(s, datei, "jan", probe=True)


# --- Vorrang über mehrere Läufe -------------------------------------------------------

_TELEKOM = (
    "- name: gelernt_telekom\n  muster: telekom\n  feld: beide\n"
    "  soll_konto: '4920'\n  haben_konto: '1200'\n"
)
_ALT = (
    "- name: telekom_alt\n  muster: telekom\n  feld: beide\n"
    "  soll_konto: '4900'\n  haben_konto: '1200'\n"
)


@pytest.mark.parametrize(
    ("inhalt", "sieger"),
    [(_TELEKOM + _ALT, "gelernt_telekom"), (_ALT + _TELEKOM, "telekom_alt")],
    ids=["gelernt_zuerst", "eigene_zuerst"],
)
def test_zweiter_lauf_behaelt_die_reihenfolge_der_datei(
    make_session, tmp_path, inhalt, sieger
):
    """Lauf 1 übernimmt ``gelernt_telekom`` und empfiehlt für ``telekom_alt``
    „mit --name übernehmen“; Lauf 2 tut das. Danach gewinnt wie in der Datei (und wie
    bei einem einzigen Lauf) der erste passende Eintrag."""
    datei = _datei(tmp_path, inhalt)
    telekom = umsatz("-39.99", date(2026, 10, 1), "Rechnung 10/2026", "Telekom")
    jetzt = datetime(2026, 10, 1, 9, 0)
    with make_session() as s:
        uebernehme_aus_datei(s, datei, "jan", jetzt=jetzt)
        s.commit()
        e2 = uebernehme_aus_datei(
            s, datei, "jan", jetzt=jetzt + timedelta(days=3), namen=["telekom_alt"]
        )
        s.commit()
        assert e2.uebernommen == ["telekom_alt"]
        werk = lade_regelwerk(s, None, "automatisch")
        reihenfolge = [r.name for r in lade_kontierungsregeln(s)]
    e = werk.klassifiziere(telekom)
    assert e is not None and e.regel == sieger
    assert reihenfolge[0] == sieger
