"""Benutzer, zweiter Faktor, Anmeldung, Sperre und Sitzungen (Spec 4.1, Akzeptanz 4)."""

from datetime import datetime, timedelta

import pytest

from accounti.auth.dienst import (
    aendere_passwort,
    beende_sitzung,
    entsperre,
    fuege_rolle_hinzu,
    gesellschaften_von,
    lege_benutzer_an,
    neue_wiederherstellungscodes,
    oeffne_sitzung,
    pruefe_anmeldung,
    pruefe_sitzung,
    pruefe_zweiten_faktor,
    rechte_in,
)
from accounti.auth.fehler import AnmeldungError, AuthError
from accounti.auth.passwort import PasswortRegelError
from accounti.auth.totp import code
from accounti.bank.tresor import TresorError, neuer_schluessel
from accounti.db.repo_auth import lade_benutzer, lade_ereignisse
from accounti.models.auth import Recht, Rolle
from tests.auth_hilfe import (
    JETZT,
    PASSWORT,
    SCHLUESSEL,
    billige_hashes,
    einstellungen,
    lege_person_an,
    systemdatenbank,
)

E = einstellungen()


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def system(tmp_path):
    with systemdatenbank(tmp_path) as s:
        yield s


def anmelden(s, name, pw, einmalcode, jetzt=JETZT, e=E):
    return pruefe_anmeldung(s, name, pw, einmalcode, SCHLUESSEL, e, jetzt=jetzt)


def test_benutzer_anlegen_speichert_nur_den_hash(system):
    b = lege_benutzer_an(
        system, "jan", PASSWORT, [("standard", Rolle.BUCHHALTER)], E, jetzt=JETZT
    )
    system.commit()
    gespeichert = lade_benutzer(system, "jan")
    assert gespeichert.passwort_hash.startswith("scrypt$")
    assert PASSWORT not in gespeichert.passwort_hash
    assert not gespeichert.totp_aktiv
    assert rechte_in(system, b.id, "standard") == {
        Recht.LESEN,
        Recht.BUCHEN,
        Recht.BELEGE_EINLIEFERN,
        Recht.LAEUFE_STARTEN,
        Recht.BUCHUNG_FREIGEBEN,
    }
    assert rechte_in(system, b.id, "andere") == set()
    assert [e.art for e in lade_ereignisse(system)] == ["benutzer_angelegt"]


def test_passwortregeln_beim_anlegen(system):
    with pytest.raises(PasswortRegelError):
        lege_benutzer_an(system, "jan", "kurz", [], E, jetzt=JETZT)


def test_2fa_braucht_einen_gueltigen_code(system):
    from accounti.auth.dienst import bestaetige_2fa
    from accounti.auth.totp import neues_geheimnis

    b = lege_benutzer_an(system, "jan", PASSWORT, [], E, jetzt=JETZT)
    geheimnis = neues_geheimnis()
    with pytest.raises(AuthError, match="passt nicht"):
        bestaetige_2fa(system, b, geheimnis, "000000", SCHLUESSEL, E, jetzt=JETZT)
    codes = bestaetige_2fa(
        system,
        b,
        geheimnis,
        code(geheimnis, JETZT.timestamp()),
        SCHLUESSEL,
        E,
        jetzt=JETZT,
    )
    assert len(codes) == 10
    assert len(set(codes)) == 10
    gespeichert = lade_benutzer(system, "jan")
    assert gespeichert.totp_aktiv
    # Geheimnis nur verschlüsselt
    from accounti.auth.totp import base32

    assert base32(geheimnis) not in gespeichert.totp_chiffrat
    # ohne Schlüssel keine Einrichtung
    with pytest.raises(TresorError):
        bestaetige_2fa(system, b, geheimnis, "123456", "", E, jetzt=JETZT)


def test_akzeptanz_4_anmeldung_ohne_zweiten_faktor_scheitert(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    # richtiges Passwort, aber kein Code
    with pytest.raises(AnmeldungError) as fehler:
        anmelden(system, "jan", PASSWORT, "")
    assert str(fehler.value) == "Anmeldung fehlgeschlagen"
    # richtiges Passwort, falscher Code
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, "000000")
    # Benutzer ohne eingerichteten zweiten Faktor kommt gar nicht hinein
    lege_person_an(system, "eva", Rolle.BUCHHALTER, mit_2fa=False)
    with pytest.raises(AnmeldungError):
        anmelden(system, "eva", PASSWORT, "123456")
    # mit beidem gelingt es
    assert anmelden(system, "jan", PASSWORT, jan.code(JETZT)).name == "jan"
    arten = [(e.art, e.ok) for e in lade_ereignisse(system)]
    assert ("ohne_zweiten_faktor", False) in arten
    assert ("anmeldung", True) in arten


def test_falsches_passwort_mit_richtigem_code_scheitert(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsches Passwort!", jan.code(JETZT))


def test_unbekannter_benutzer_gleiche_meldung_ohne_namen_im_protokoll(system):
    with pytest.raises(AnmeldungError) as fehler:
        anmelden(system, "niemand", PASSWORT, "123456")
    assert str(fehler.value) == "Anmeldung fehlgeschlagen"
    ereignis = lade_ereignisse(system)[-1]
    assert ereignis.benutzer is None
    assert "niemand" not in (ereignis.hinweis or "")


def test_totp_code_nur_einmal(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    c = jan.code(JETZT)
    anmelden(system, "jan", PASSWORT, c)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, c, jetzt=JETZT + timedelta(seconds=5))
    # auch ein älterer Code aus dem Toleranzfenster zählt nicht mehr
    alt = code(jan.geheimnis, JETZT.timestamp() - 30)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, alt, jetzt=JETZT + timedelta(seconds=5))
    spaeter = JETZT + timedelta(seconds=30)
    anmelden(system, "jan", PASSWORT, jan.code(spaeter), jetzt=spaeter)


def test_wiederherstellungscode_genau_einmal(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    wc = jan.codes[3]
    assert anmelden(system, "jan", PASSWORT, wc.lower().replace("-", " ")).name == "jan"
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, wc)
    assert any(e.art == "wiederherstellungscode" for e in lade_ereignisse(system))
    # neue Codes machen alle alten ungültig
    neu = neue_wiederherstellungscodes(
        system, lade_benutzer(system, "jan"), E, JETZT, schluessel=SCHLUESSEL
    )
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, jan.codes[0])
    anmelden(system, "jan", PASSWORT, neu[0])


def test_sperre_nach_fehlversuchen(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    e = einstellungen(sperre_nach_fehlversuchen=3, sperre_minuten=15)
    for _ in range(3):
        with pytest.raises(AnmeldungError):
            anmelden(system, "jan", "falsch falsch falsch", "000000", e=e)
    # gesperrt: auch richtige Angaben helfen nicht
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, jan.code(JETZT), e=e)
    assert lade_benutzer(system, "jan").gesperrt(JETZT)
    assert any(x.art == "gesperrt" for x in lade_ereignisse(system))
    # nach Ablauf der Sperre geht es wieder; Erfolg setzt den Zähler zurück
    spaeter = JETZT + timedelta(minutes=16)
    anmelden(system, "jan", PASSWORT, jan.code(spaeter), jetzt=spaeter, e=e)
    assert lade_benutzer(system, "jan").fehlversuche == 0


def test_fehlversuche_bleiben_trotz_ausnahme_gespeichert(system):
    lege_person_an(system, "jan", Rolle.BUCHHALTER)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsch falsch falsch", "000000")
    system.rollback()  # der Aufrufer rollt zurück — der Fehlversuch zählt trotzdem
    assert lade_benutzer(system, "jan").fehlversuche == 1


def test_entsperren(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    e = einstellungen(sperre_nach_fehlversuchen=1)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsch falsch falsch", "000000", e=e)
    entsperre(system, lade_benutzer(system, "jan"), JETZT, durch="chef")
    anmelden(system, "jan", PASSWORT, jan.code(JETZT), e=e)


def test_deaktivierter_benutzer(system):
    from accounti.auth.dienst import setze_aktiv

    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    setze_aktiv(system, lade_benutzer(system, "jan"), False, JETZT, durch="chef")
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, jan.code(JETZT))


def test_veralteter_hash_wird_bei_anmeldung_erneuert(system, monkeypatch):
    from accounti.auth import passwort

    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    alt = lade_benutzer(system, "jan").passwort_hash
    monkeypatch.setattr(passwort, "KOSTEN", passwort.Kosten(log_n=11, r=8, p=1))
    anmelden(system, "jan", PASSWORT, jan.code(JETZT))
    neu = lade_benutzer(system, "jan").passwort_hash
    assert neu != alt
    assert neu.startswith("scrypt$11$")


def test_zweiter_faktor_allein(system):
    jan = lege_person_an(system, "jan", Rolle.FREIGEBER)
    b = lade_benutzer(system, "jan")
    assert pruefe_zweiten_faktor(
        system, b, jan.code(JETZT), SCHLUESSEL, E, JETZT, quelle="cli"
    ) == ("totp")
    with pytest.raises(AnmeldungError):
        pruefe_zweiten_faktor(
            system, b, jan.code(JETZT), SCHLUESSEL, E, JETZT, quelle="cli"
        )
    falscher = neuer_schluessel()
    spaeter = JETZT + timedelta(seconds=30)
    with pytest.raises(TresorError):
        pruefe_zweiten_faktor(
            system, b, jan.code(spaeter), falscher, E, spaeter, quelle="cli"
        )


def test_sitzung_leerlauf_und_hoechstdauer(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    e = einstellungen(sitzung_leerlauf_minuten=30, sitzung_hoechstdauer_stunden=8)
    token, sitzung = oeffne_sitzung(system, jan.benutzer, "standard", e, JETZT)
    assert len(token) >= 43  # 256 Bit
    assert token not in sitzung.token_hash
    gefunden = pruefe_sitzung(system, token, e, JETZT + timedelta(minutes=29))
    assert gefunden is not None
    assert gefunden[1].name == "jan"
    # Leerlauf zählt ab der letzten Aktivität
    assert pruefe_sitzung(system, token, e, JETZT + timedelta(minutes=58)) is not None
    assert pruefe_sitzung(system, token, e, JETZT + timedelta(minutes=89)) is None
    # beendet bleibt beendet
    assert pruefe_sitzung(system, token, e, JETZT + timedelta(minutes=90)) is None
    # absolute Dauer
    token2, _ = oeffne_sitzung(system, jan.benutzer, "standard", e, JETZT)
    t = JETZT
    for _ in range(17):
        t += timedelta(minutes=29)
        if t >= JETZT + timedelta(hours=8):
            break
        assert pruefe_sitzung(system, token2, e, t) is not None
    assert (
        pruefe_sitzung(system, token2, e, JETZT + timedelta(hours=8, minutes=1)) is None
    )
    assert pruefe_sitzung(system, "gibtsnicht", e, JETZT) is None


def test_abmelden_beendet_serverseitig(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    beende_sitzung(system, token, JETZT)
    assert pruefe_sitzung(system, token, E, JETZT) is None


def test_passwortwechsel_und_rollenaenderung_beenden_sitzungen(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    aendere_passwort(
        system, lade_benutzer(system, "jan"), "ein neuer langer Satz", E, JETZT, "jan"
    )
    assert pruefe_sitzung(system, token, E, JETZT) is None
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, jan.code(JETZT))
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    fuege_rolle_hinzu(system, jan.benutzer, "standard", Rolle.FREIGEBER, JETZT, "chef")
    assert pruefe_sitzung(system, token, E, JETZT) is None


def test_gesperrter_benutzer_verliert_sitzung(system):
    """Gesperrt von einem Verwalter (``benutzer sperren``): die Sitzung endet. Eine
    Sperre nach Fehlversuchen beendet sie nicht — die kann jeder auslösen, der den
    Namen kennt (Befund A-M4, ``tests/test_auth_befunde.py``)."""
    from accounti.auth.dienst import setze_aktiv, sperre

    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    e = einstellungen(sperre_nach_fehlversuchen=1)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsch falsch falsch", "000000", e=e)
    assert pruefe_sitzung(system, token, e, JETZT) is not None
    setze_aktiv(system, lade_benutzer(system, "jan"), False, JETZT, durch="chef")
    assert pruefe_sitzung(system, token, e, JETZT) is None
    setze_aktiv(system, lade_benutzer(system, "jan"), True, JETZT, durch="chef")
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    assert pruefe_sitzung(system, token, e, JETZT) is not None
    sperre(system, lade_benutzer(system, "jan"), JETZT + timedelta(hours=1), JETZT, "c")
    assert pruefe_sitzung(system, token, e, JETZT) is None


def test_gesellschaften_von(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER, gesellschaft="a")
    fuege_rolle_hinzu(system, jan.benutzer, "b", Rolle.BETRACHTER, JETZT, "chef")
    assert gesellschaften_von(system, jan.benutzer.id) == ["a", "b"]
    assert rechte_in(system, jan.benutzer.id, "b") == {Recht.LESEN}


def test_zeitpunkte_in_der_zukunft_sind_kein_problem(system):
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    t = datetime(2030, 1, 1, 12, 0)
    assert anmelden(system, "jan", PASSWORT, jan.code(t), jetzt=t).name == "jan"
