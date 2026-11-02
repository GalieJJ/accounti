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


# --- Runde 4 (g3w-fach N3–N6) ---------------------------------------------------------


@pytest.mark.parametrize(
    "wert",
    ["9223372036854775808", "100000000000000000000", "0", "-9", "99", "4", "'-1'",
     "40"],
)  # fmt: skip
def test_steuerschluessel_nur_bekannte(tmp_path, wert):
    """Ab 2^63 gab der REST-Lauf 500, classify und ``regeln uebernehmen`` einen
    Traceback (OverflowError beim Speichern); 0, −9, 99 nahm der Lader an, erst die
    Voranmeldung sperrte („hat keine Kennziffer“)."""
    datei = _datei(tmp_path, _regel(steuer_schluessel=wert))
    with pytest.raises(KonfigurationError, match="Regel telekom: steuer_schluessel"):
        lade_regeln(datei)


@pytest.mark.parametrize(
    "wert", ["1", "'1'", "2", "3", "8", "9", "18", "19", "91", "94", "'9'"]
)
def test_bekannte_steuerschluessel_bleiben(tmp_path, wert):
    """Auch 1 (DATEV „umsatzsteuerfrei mit Vorsteuerabzug“): Voranmeldung und
    Prüfregel kennen ihn, main buchte ihn — Runde 4 lehnte ihn als unbekannt ab
    (g4w N6)."""
    [regel] = lade_regeln(_datei(tmp_path, _regel(steuer_schluessel=wert)))
    assert regel.steuer_schluessel == int(wert.strip("'"))


@pytest.mark.parametrize(
    ("schluessel", "wert"),
    [("prüfen", "true"), ("steuerschluessel", "9"), ("konto", "'4920'"),
     ("Muster", "x")],
)  # fmt: skip
def test_unbekannter_schluessel_ist_fehler_mit_namen(tmp_path, schluessel, wert):
    """Ein Eintrag mit ``prüfen: true`` (Umlaut) buchte die Miete automatisch, einer
    mit ``steuerschluessel: 9`` ohne Vorsteuer — still."""
    datei = _datei(tmp_path, _regel(**{schluessel: wert}))
    with pytest.raises(
        KonfigurationError, match=f"Regel telekom: unbekannter Schlüssel {schluessel}"
    ):
        lade_regeln(datei)


@pytest.mark.parametrize(
    "wert",
    ["0x1340", "1:20:00", "83:20", "4_920", "0b1001100111000", "+4920", "４９２０",
     "'４９２０'", "'٤٩٢٠'"],
)  # fmt: skip
def test_zahlformen_aendern_das_konto_nicht(tmp_path, wert):
    """YAML 1.1 liest 0x1340 als 4928, 1:20:00 (sexagesimal) als 4800, 4_920 als
    4920 — gebucht wurde automatisch auf ein anderes Konto. Unicode-Ziffern
    („４９２０“) wurden ein Phantomkonto, an dem der DATEV-Export abbrach."""
    datei = _datei(tmp_path, _regel(soll_konto=wert))
    with pytest.raises(KonfigurationError, match="ist keine Kontonummer"):
        lade_regeln(datei)


def test_ganze_zahlen_ohne_anfuehrungszeichen_bleiben_konten(tmp_path):
    datei = _datei(tmp_path, _regel(soll_konto="4920", haben_konto="1200",
                                    steuer_schluessel="9"))  # fmt: skip
    [regel] = lade_regeln(datei)
    assert (regel.soll_konto, regel.haben_konto, regel.steuer_schluessel) == (
        "4920",
        "1200",
        9,
    )


def test_uebernahme_mit_riesigem_schluessel_ungueltig_statt_traceback(
    make_session, tmp_path
):
    """g3w-web N3 (a): Die Probe von ``regeln uebernehmen`` war grün, der echte Lauf
    endete mit OverflowError — jetzt ist der Eintrag schon in der Probe ungültig."""
    datei = _datei(
        tmp_path,
        _regel(name="gelernt_riesig", steuer_schluessel="9223372036854775808")
        + _regel(name="gelernt_tippfehler", steuerschluessel="9"),
    )
    with make_session() as s:
        e = uebernehme_aus_datei(s, datei, "jan", probe=True)
    assert sorted(e.ungueltig) == ["gelernt_riesig", "gelernt_tippfehler"]
    assert e.uebernommen == []
    assert "unbekannter Schlüssel steuerschluessel" in e.gruende["gelernt_tippfehler"]


# --- Runde 4 (g3w-web N3): Probe und Lauf urteilen gleich -----------------------------


def test_namen_gleich_nach_100_zeichen_ungueltig_statt_speicherfehler(
    make_session, tmp_path
):
    """Zwei ``gelernt_``-Namen, die sich erst nach 100 Zeichen unterscheiden: Die
    Probe meldete „2 würde übernehmen“, der Lauf endete nach dem Code mit „Regelname …
    ist schon vergeben“. Jetzt ist der zweite schon in der Probe ungültig."""
    lang = "gelernt_" + "x" * 95
    datei = _datei(
        tmp_path,
        _regel(name=lang + "_eins") + _regel(name=lang + "_zwei", muster="vodafone"),
    )
    for probe in (True, False):
        with make_session() as s:
            e = uebernehme_aus_datei(s, datei, "jan", probe=probe)
            s.rollback()
        assert e.uebernommen == [lang + "_eins"], probe
        assert e.ungueltig == [lang + "_zwei"]
        assert "100 Zeichen" in e.gruende[lang + "_zwei"]


def test_langer_name_zweiter_lauf_uebersprungen(make_session, tmp_path):
    lang = "gelernt_" + "y" * 120
    datei = _datei(tmp_path, _regel(name=lang))
    with make_session() as s:
        assert uebernehme_aus_datei(s, datei, "jan").uebernommen == [lang]
        s.commit()
        e = uebernehme_aus_datei(s, datei, "jan")
    assert (e.uebernommen, e.uebersprungen) == ([], [lang])


def test_langer_name_gleich_einem_frueher_uebernommenen_ist_vergeben(
    make_session, tmp_path
):
    """g4w N4 (Runde 5): Gleicht ein langer Name in den ersten 100 Zeichen einer
    früher übernommenen Regel mit anderem Inhalt, galt er still als „schon
    vorhanden“ — wer den Eintrag dann löschte, verlor die Regel. Jetzt ungültig mit
    „Regelname … ist schon vergeben“ (wie vor Runde 4, aber vor dem Code)."""
    basis = "gelernt_" + "a" * 100
    with make_session() as s:
        erst = _datei(tmp_path, _regel(name=basis + "x", muster="TELEKOM"))
        assert uebernehme_aus_datei(s, erst, "jan").uebernommen == [basis + "x"]
        s.commit()
        zweit = _datei(
            tmp_path,
            _regel(name=basis + "y", muster="STADTWERKE", soll_konto="'4240'")
            + _regel(name=basis + "x", muster="TELEKOM"),
        )
        e = uebernehme_aus_datei(s, zweit, "jan")
        s.rollback()
        regeln = [(r.muster, r.soll_konto) for r in lade_kontierungsregeln(s)]
    assert e.ungueltig == [basis + "y"]
    assert e.gruende[basis + "y"].startswith(
        f"Regelname {basis + 'y'} ist schon vergeben"
    )
    assert "in der Datei umbenennen" in e.gruende[basis + "y"]
    assert e.uebersprungen == [basis + "x"]  # derselbe Eintrag: wie bisher
    assert regeln == [("TELEKOM", "4920")]


def test_zu_langes_muster_ungueltig_buchungstext_gekuerzt(make_session, tmp_path):
    """Spalten muster (200) und buchungstext (60): PostgreSQL lehnte zu lange Werte
    erst beim Speichern ab, nach dem Code."""
    datei = _datei(
        tmp_path,
        _regel(name="gelernt_lang", muster="'" + "a" * 201 + "'")
        + _regel(name="gelernt_text", buchungstext="'" + "T" * 80 + "'"),
    )
    with make_session() as s:
        e = uebernehme_aus_datei(s, datei, "jan")
        s.commit()
        regeln = {r.name: r for r in lade_kontierungsregeln(s)}
    assert e.ungueltig == ["gelernt_lang"]
    assert "200 Zeichen" in e.gruende["gelernt_lang"]
    assert regeln["gelernt_text"].buchungstext == "T" * 60


# --- Runde 6 (g5w NEU-5): gleicher Name, anderer Inhalt -------------------------------
#
# Bisher galt jeder kurze Name, den die Datenbank schon kennt, still als „schon
# vorhanden (übersprungen)“ — auch mit anderem Muster oder Konto; ebenso eine nur in
# der Richtung geänderte Regel und derselbe Name zweimal in einer Datei. Wer der
# Ausgabe folgte und den Eintrag löschte, verlor die Änderung. Jetzt „ungültig … anderer
# Inhalt“ wie beim langen Namen (Runde 5, g4w N4).


@pytest.mark.parametrize(
    "zweit",
    [
        {"muster": "'TELEKOM|T-MOBILE'", "soll_konto": "'4925'"},
        {"soll_konto": "'4925'"},
        {"steuer_schluessel": "8"},
        {"feld": "gegenkonto_name"},
    ],
    ids=["muster_und_konto", "konto", "schluessel", "feld"],
)
def test_kurzer_name_anderer_inhalt_ungueltig(make_session, tmp_path, zweit):
    name = "gelernt_telekom"
    with make_session() as s:
        erst = _datei(tmp_path, _regel(name=name, steuer_schluessel="9"))
        assert uebernehme_aus_datei(s, erst, "jan").uebernommen == [name]
        s.commit()
        zweite = _datei(
            tmp_path, _regel(name=name, **{"steuer_schluessel": "9", **zweit})
        )
        for probe in (True, False):
            e = uebernehme_aus_datei(s, zweite, "jan", probe=probe)
            assert (e.uebersprungen, e.ungueltig) == ([], [name]), probe
            assert "anderem Inhalt" in e.gruende[name]
            assert "in der Datei umbenennen" in e.gruende[name]
        s.rollback()
        regeln = [(r.muster, r.soll_konto) for r in lade_kontierungsregeln(s)]
    assert regeln == [("telekom", "4920")]


def test_kurzer_name_gleicher_inhalt_uebersprungen(make_session, tmp_path):
    datei = _datei(tmp_path, _regel(name="gelernt_telekom"))
    with make_session() as s:
        assert uebernehme_aus_datei(s, datei, "jan").uebernommen == ["gelernt_telekom"]
        s.commit()
        e = uebernehme_aus_datei(s, datei, "jan")
    assert (e.uebersprungen, e.ungueltig) == (["gelernt_telekom"], [])


@pytest.mark.parametrize("lang", [False, True], ids=["kurz", "lang"])
def test_nur_richtung_geaendert_ungueltig(make_session, tmp_path, lang):
    name = "gelernt_" + ("a" * 100 + "x" if lang else "telekom")
    with make_session() as s:
        erst = _datei(tmp_path, _regel(name=name, richtung="ausgabe"))
        assert uebernehme_aus_datei(s, erst, "jan").uebernommen == [name]
        s.commit()
        zweite = _datei(tmp_path, _regel(name=name, richtung="einnahme"))
        e = uebernehme_aus_datei(s, zweite, "jan")
        erst = _datei(tmp_path, _regel(name=name, richtung="ausgabe"))
        gleich = uebernehme_aus_datei(s, erst, "jan")
    assert e.ungueltig == [name] and "anderem Inhalt" in e.gruende[name]
    assert gleich.uebersprungen == [name]


def test_ohne_richtung_in_der_datei_vergleicht_die_richtung_nicht(
    make_session, tmp_path
):
    """Eine Regel aus ``accounti lerne`` (ohne Richtung) und derselbe Eintrag in der
    Datei ohne ``richtung``: übersprungen wie bisher (die Richtung leitet die
    Übernahme sonst aus der Bankseite ab)."""
    from accounti.klassifikation.lernen import lerne_regex

    datei = _datei(tmp_path, _regel(name="gelernt_aral", muster="Aral", feld="beide"))
    with make_session() as s:
        lerne_regex(s, "gelernt_aral", "Aral", "4920", "1200", None, "jan")
        e = uebernehme_aus_datei(s, datei, "jan")
    assert (e.uebersprungen, e.ungueltig) == (["gelernt_aral"], [])


@pytest.mark.parametrize("lang", [False, True], ids=["kurz", "lang"])
def test_name_zweimal_in_einer_datei_anderer_inhalt(make_session, tmp_path, lang):
    name = "gelernt_" + ("a" * 100 + "x" if lang else "x")
    datei = _datei(
        tmp_path,
        _regel(name=name, muster="TELEKOM")
        + _regel(name=name, muster="STADTWERKE", soll_konto="'4240'")
        + _regel(name=name, muster="TELEKOM"),
    )
    for probe in (True, False):
        with make_session() as s:
            e = uebernehme_aus_datei(s, datei, "jan", probe=probe)
            s.rollback()
        assert e.uebernommen == [name], probe
        assert e.ungueltig == [name] and "zweimal" in e.gruende[name]
        assert e.uebersprungen == [name]  # derselbe Eintrag noch einmal
