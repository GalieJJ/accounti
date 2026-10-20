"""Benutzer, zweiter Faktor, Anmeldung, Sperre, Sitzungen und Rollen.

Alle Funktionen arbeiten in einer Sitzung der **Systemdatenbank**. Sie schreiben
mit ``flush()``; nur Fehlversuche und Sperren werden sofort festgeschrieben
(``commit``), damit eine Ausnahme beim Aufrufer sie nicht zurückrollt — sonst ließe
sich die Sperre durch Fehler umgehen.

Anmeldung = Passwort **und** zweiter Faktor (TOTP oder Wiederherstellungscode).
Wer noch keinen zweiten Faktor eingerichtet hat, kommt nicht hinein (Akzeptanz 4).
Die Ausnahme sagt nie, was falsch war.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.auth import passwort as pw
from accounti.auth import totp, wiederherstellung
from accounti.auth.einstellungen import AuthEinstellungen
from accounti.auth.fehler import AnmeldungError, AuthError
from accounti.bank.tresor import TresorError, entschluessele, verschluessele
from accounti.db import repo_auth as repo
from accounti.models.auth import (
    AuthEreignis,
    Benutzer,
    Recht,
    Rolle,
    Rollenzuordnung,
    Sitzung,
    pruefe_gesellschaft,
    pruefe_name,
    rechte_der_rollen,
)

_AKTIV_SPEICHERN_AB = timedelta(seconds=60)
_dummy_hash: dict[pw.Kosten, str] = {}


def _jetzt(jetzt: datetime | None) -> datetime:
    return jetzt or datetime.now()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ereignis(
    s: Session,
    art: str,
    jetzt: datetime,
    benutzer: str | None = None,
    *,
    ok: bool = True,
    quelle: str = "cli",
    gesellschaft: str | None = None,
    hinweis: str | None = None,
) -> None:
    repo.protokolliere_ereignis(
        s,
        AuthEreignis(
            zeitpunkt=jetzt,
            art=art,
            benutzer=benutzer,
            gesellschaft=gesellschaft,
            quelle=quelle,
            ok=ok,
            hinweis=hinweis,
        ),
    )


# ---------------------------------------------------------------------------
# Benutzer
# ---------------------------------------------------------------------------


def lege_benutzer_an(
    s: Session,
    name: str,
    passwort: str,
    rollen: Iterable[tuple[str, Rolle]],
    einstellungen: AuthEinstellungen,
    *,
    anzeigename: str | None = None,
    durch: str | None = None,
    jetzt: datetime | None = None,
) -> Benutzer:
    jetzt = _jetzt(jetzt)
    pruefe_name(name)
    pw.pruefe_regeln(passwort, name, einstellungen.passwort_mindestlaenge)
    b = Benutzer(
        name=name,
        anzeigename=anzeigename,
        passwort_hash=pw.hash_passwort(passwort),
        angelegt_am=jetzt,
        passwort_geaendert_am=jetzt,
    )
    repo.speichere_benutzer(s, b)
    for gesellschaft, rolle in rollen:
        repo.fuege_rolle_hinzu(
            s, Rollenzuordnung(b.id, pruefe_gesellschaft(gesellschaft), rolle)
        )
    ereignis(
        s,
        "benutzer_angelegt",
        jetzt,
        name,
        hinweis=f"durch {durch}" if durch else None,
    )
    return b


def aendere_passwort(
    s: Session,
    b: Benutzer,
    neu: str,
    einstellungen: AuthEinstellungen,
    jetzt: datetime | None,
    durch: str,
) -> Benutzer:
    """Neues Passwort; alle Sitzungen des Benutzers enden."""
    jetzt = _jetzt(jetzt)
    pw.pruefe_regeln(neu, b.name, einstellungen.passwort_mindestlaenge)
    b = b.model_copy(
        update={"passwort_hash": pw.hash_passwort(neu), "passwort_geaendert_am": jetzt}
    )
    repo.speichere_benutzer(s, b)
    repo.beende_sitzungen_von(s, b.id, jetzt)
    ereignis(s, "passwort_geaendert", jetzt, b.name, hinweis=f"durch {durch}")
    return b


def setze_aktiv(
    s: Session, b: Benutzer, aktiv: bool, jetzt: datetime | None, durch: str
) -> Benutzer:
    jetzt = _jetzt(jetzt)
    b = b.model_copy(update={"aktiv": aktiv})
    repo.speichere_benutzer(s, b)
    if not aktiv:
        repo.beende_sitzungen_von(s, b.id, jetzt)
    art = "benutzer_aktiviert" if aktiv else "benutzer_deaktiviert"
    ereignis(s, art, jetzt, b.name, hinweis=f"durch {durch}")
    return b


def sperre(
    s: Session, b: Benutzer, bis: datetime, jetzt: datetime | None, durch: str
) -> Benutzer:
    jetzt = _jetzt(jetzt)
    b = b.model_copy(update={"gesperrt_bis": bis})
    repo.speichere_benutzer(s, b)
    repo.beende_sitzungen_von(s, b.id, jetzt)
    ereignis(s, "gesperrt", jetzt, b.name, hinweis=f"durch {durch}")
    return b


def entsperre(s: Session, b: Benutzer, jetzt: datetime | None, durch: str) -> Benutzer:
    jetzt = _jetzt(jetzt)
    b = b.model_copy(update={"gesperrt_bis": None, "fehlversuche": 0})
    repo.speichere_benutzer(s, b)
    ereignis(s, "entsperrt", jetzt, b.name, hinweis=f"durch {durch}")
    return b


# ---------------------------------------------------------------------------
# Rollen und Rechte
# ---------------------------------------------------------------------------


def fuege_rolle_hinzu(
    s: Session,
    b: Benutzer,
    gesellschaft: str,
    rolle: Rolle,
    jetzt: datetime | None,
    durch: str,
) -> bool:
    """Neue Rolle — offene Sitzungen enden (neue Sitzungs-ID nach Rechteänderung)."""
    jetzt = _jetzt(jetzt)
    neu = repo.fuege_rolle_hinzu(
        s, Rollenzuordnung(b.id, pruefe_gesellschaft(gesellschaft), rolle)
    )
    if neu:
        repo.beende_sitzungen_von(s, b.id, jetzt)
        ereignis(
            s,
            "rolle_hinzugefuegt",
            jetzt,
            b.name,
            gesellschaft=gesellschaft,
            hinweis=f"{rolle.value} durch {durch}",
        )
    return neu


def entferne_rolle(
    s: Session,
    b: Benutzer,
    gesellschaft: str,
    rolle: Rolle,
    jetzt: datetime | None,
    durch: str,
) -> bool:
    jetzt = _jetzt(jetzt)
    weg = repo.entferne_rolle(s, b.id, gesellschaft, rolle)
    if weg:
        repo.beende_sitzungen_von(s, b.id, jetzt)
        ereignis(
            s,
            "rolle_entfernt",
            jetzt,
            b.name,
            gesellschaft=gesellschaft,
            hinweis=f"{rolle.value} durch {durch}",
        )
    return weg


def rollen_in(s: Session, benutzer_id: UUID, gesellschaft: str) -> list[Rolle]:
    return [z.rolle for z in repo.rollen_von(s, benutzer_id, gesellschaft)]


def rechte_in(s: Session, benutzer_id: UUID, gesellschaft: str) -> set[Recht]:
    return rechte_der_rollen(rollen_in(s, benutzer_id, gesellschaft))


def gesellschaften_von(s: Session, benutzer_id: UUID) -> list[str]:
    return sorted({z.gesellschaft for z in repo.rollen_von(s, benutzer_id)})


# ---------------------------------------------------------------------------
# Zweiter Faktor
# ---------------------------------------------------------------------------


def _bezug(b: Benutzer) -> str:
    return f"totp:{b.id}"


def bestaetige_2fa(
    s: Session,
    b: Benutzer,
    geheimnis: bytes,
    einmalcode: str,
    schluessel: str,
    einstellungen: AuthEinstellungen,
    jetzt: datetime | None = None,
) -> list[str]:
    """Aktiviert TOTP mit diesem Geheimnis, wenn der Code dazu passt.

    Gibt neue Wiederherstellungscodes zurück — im Klartext nur dieses eine Mal.
    Ein schon eingerichteter zweiter Faktor wird ersetzt.
    """
    jetzt = _jetzt(jetzt)
    chiffrat = verschluessele(
        {"geheimnis": totp.base32(geheimnis)}, schluessel, _bezug(b)
    )
    schritt = totp.finde_schritt(
        geheimnis, einmalcode, jetzt.timestamp(), einstellungen.totp_toleranz_schritte
    )
    if schritt is None:
        raise AuthError(
            "Der Code passt nicht — Uhrzeit der App prüfen und neu eingeben"
        )
    b = b.model_copy(
        update={
            "totp_chiffrat": chiffrat,
            "totp_aktiv": True,
            "totp_letzter_schritt": schritt,
        }
    )
    repo.speichere_benutzer(s, b)
    codes = neue_wiederherstellungscodes(s, b, einstellungen, jetzt, protokoll=False)
    ereignis(s, "zweiter_faktor_eingerichtet", jetzt, b.name)
    return codes


def neue_wiederherstellungscodes(
    s: Session,
    b: Benutzer,
    einstellungen: AuthEinstellungen,
    jetzt: datetime | None = None,
    *,
    protokoll: bool = True,
) -> list[str]:
    jetzt = _jetzt(jetzt)
    codes = wiederherstellung.neue_codes()
    repo.ersetze_wiederherstellungscodes(
        s, b.id, [wiederherstellung.hash_code(c) for c in codes], jetzt
    )
    if protokoll:
        ereignis(s, "wiederherstellungscodes_neu", jetzt, b.name)
    return codes


def _geheimnis(b: Benutzer, schluessel: str) -> bytes:
    if not b.totp_chiffrat:
        raise AuthError("Kein zweiter Faktor eingerichtet")
    daten = entschluessele(b.totp_chiffrat, schluessel, _bezug(b))
    return totp.geheimnis_aus_base32(daten["geheimnis"])


def _pruefe_faktor(
    s: Session,
    b: Benutzer,
    einmalcode: str,
    schluessel: str,
    einstellungen: AuthEinstellungen,
    jetzt: datetime,
) -> str | None:
    """``"totp"``, ``"wiederherstellungscode"`` oder ``None``."""
    rein = "".join(einmalcode.split())
    if len(rein) == totp.STELLEN and rein.isascii() and rein.isdigit():
        schritt = totp.finde_schritt(
            _geheimnis(b, schluessel),
            rein,
            jetzt.timestamp(),
            einstellungen.totp_toleranz_schritte,
        )
        if schritt is not None and repo.merke_totp_schritt(s, b.id, schritt):
            return "totp"
        return None
    if wiederherstellung.normalisiere(einmalcode) is None:
        return None
    for code in repo.offene_wiederherstellungscodes(s, b.id):
        if wiederherstellung.passt(
            einmalcode, code.code_hash
        ) and repo.verbrauche_wiederherstellungscode(s, code.id, jetzt):
            return "wiederherstellungscode"
    return None


def _fehlversuch(
    s: Session,
    b: Benutzer,
    einstellungen: AuthEinstellungen,
    jetzt: datetime,
    grund: str,
    quelle: str,
) -> AnmeldungError:
    aktuell = repo.lade_benutzer_id(s, b.id) or b
    zaehler = aktuell.fehlversuche + 1
    aenderung: dict[str, object] = {"fehlversuche": zaehler}
    gesperrt = zaehler >= einstellungen.sperre_nach_fehlversuchen
    if gesperrt:
        aenderung["gesperrt_bis"] = jetzt + timedelta(
            minutes=einstellungen.sperre_minuten
        )
        aenderung["fehlversuche"] = 0
    repo.speichere_benutzer(s, aktuell.model_copy(update=aenderung))
    ereignis(s, grund, jetzt, b.name, ok=False, quelle=quelle)
    if gesperrt:
        repo.beende_sitzungen_von(s, b.id, jetzt)
        ereignis(
            s,
            "gesperrt",
            jetzt,
            b.name,
            ok=False,
            quelle=quelle,
            hinweis=f"{zaehler} Fehlversuche, {einstellungen.sperre_minuten} min",
        )
    s.commit()  # Fehlversuch und Sperre überstehen die Ausnahme beim Aufrufer
    return AnmeldungError(grund)


def pruefe_zweiten_faktor(
    s: Session,
    b: Benutzer,
    einmalcode: str,
    schluessel: str,
    einstellungen: AuthEinstellungen,
    jetzt: datetime | None = None,
    quelle: str = "cli",
) -> str:
    """Nur der zweite Faktor — für Freigaben in der CLI. Zählt Fehlversuche."""
    jetzt = _jetzt(jetzt)
    if b.gesperrt(jetzt) or not b.aktiv:
        ereignis(s, "einmalcode_gesperrt", jetzt, b.name, ok=False, quelle=quelle)
        s.commit()
        raise AnmeldungError("gesperrt")
    if not b.totp_aktiv:
        msg = f"{b.name} hat keinen zweiten Faktor — accounti benutzer 2fa {b.name}"
        raise AuthError(msg)
    art = _pruefe_faktor(s, b, einmalcode, schluessel, einstellungen, jetzt)
    if art is None:
        raise _fehlversuch(s, b, einstellungen, jetzt, "einmalcode_falsch", quelle)
    repo.speichere_benutzer(
        s, (repo.lade_benutzer_id(s, b.id) or b).model_copy(update={"fehlversuche": 0})
    )
    if art == "wiederherstellungscode":
        ereignis(s, "wiederherstellungscode", jetzt, b.name, quelle=quelle)
    return art


def _gleiche_zeit(passwort: str) -> None:
    """Rechnet einen Hash, damit unbekannte Namen nicht schneller abgewiesen werden."""
    kosten = pw.KOSTEN
    if kosten not in _dummy_hash:
        _dummy_hash[kosten] = pw.hash_passwort(secrets.token_hex(16), kosten)
    pw.pruefe_passwort(passwort, _dummy_hash[kosten])


def pruefe_anmeldung(
    s: Session,
    name: str,
    passwort: str,
    einmalcode: str,
    schluessel: str,
    einstellungen: AuthEinstellungen,
    *,
    jetzt: datetime | None = None,
    quelle: str = "web",
) -> Benutzer:
    """Passwort und zweiter Faktor — sonst ``AnmeldungError``."""
    jetzt = _jetzt(jetzt)
    name = name.strip().lower()
    b = repo.lade_benutzer(s, name) if name else None
    if b is None:
        _gleiche_zeit(passwort)
        # der eingegebene Name kann ein vertipptes Passwort sein: nicht speichern
        ereignis(
            s,
            "anmeldung",
            jetzt,
            None,
            ok=False,
            quelle=quelle,
            hinweis="unbekannter Benutzer",
        )
        s.commit()
        raise AnmeldungError("unbekannt")
    if not b.aktiv or b.gesperrt(jetzt):
        _gleiche_zeit(passwort)
        grund = "deaktiviert" if not b.aktiv else "gesperrt"
        ereignis(s, "anmeldung", jetzt, b.name, ok=False, quelle=quelle, hinweis=grund)
        s.commit()
        raise AnmeldungError(grund)
    if not pw.pruefe_passwort(passwort, b.passwort_hash):
        raise _fehlversuch(s, b, einstellungen, jetzt, "passwort_falsch", quelle)
    if not b.totp_aktiv:
        ereignis(s, "ohne_zweiten_faktor", jetzt, b.name, ok=False, quelle=quelle)
        s.commit()
        raise AnmeldungError("ohne_zweiten_faktor")
    try:
        art = _pruefe_faktor(s, b, einmalcode, schluessel, einstellungen, jetzt)
    except TresorError:
        ereignis(
            s,
            "anmeldung",
            jetzt,
            b.name,
            ok=False,
            quelle=quelle,
            hinweis="Tresor-Schlüssel fehlt oder falsch",
        )
        s.commit()
        raise
    if art is None:
        raise _fehlversuch(s, b, einstellungen, jetzt, "einmalcode_falsch", quelle)
    aktuell = repo.lade_benutzer_id(s, b.id) or b
    aenderung: dict[str, object] = {"fehlversuche": 0, "letzte_anmeldung_am": jetzt}
    if pw.veraltet(aktuell.passwort_hash):
        aenderung["passwort_hash"] = pw.hash_passwort(passwort)
    b = aktuell.model_copy(update=aenderung)
    repo.speichere_benutzer(s, b)
    if art == "wiederherstellungscode":
        ereignis(s, "wiederherstellungscode", jetzt, b.name, quelle=quelle)
    ereignis(s, "anmeldung", jetzt, b.name, quelle=quelle)
    return b


# ---------------------------------------------------------------------------
# Sitzungen
# ---------------------------------------------------------------------------


def oeffne_sitzung(
    s: Session,
    b: Benutzer,
    gesellschaft: str,
    einstellungen: AuthEinstellungen,
    jetzt: datetime | None = None,
) -> tuple[str, Sitzung]:
    """Neue Sitzung mit 256-Bit-Token; gespeichert wird nur sein SHA-256."""
    jetzt = _jetzt(jetzt)
    token = secrets.token_urlsafe(32)
    sitzung = Sitzung(
        token_hash=token_hash(token),
        benutzer_id=b.id,
        gesellschaft=gesellschaft,
        angelegt_am=jetzt,
        zuletzt_aktiv_am=jetzt,
        laeuft_ab_am=jetzt
        + timedelta(hours=einstellungen.sitzung_hoechstdauer_stunden),
    )
    repo.speichere_sitzung(s, sitzung)
    return token, sitzung


def pruefe_sitzung(
    s: Session,
    token: str,
    einstellungen: AuthEinstellungen,
    jetzt: datetime | None = None,
) -> tuple[Sitzung, Benutzer] | None:
    """Gültige Sitzung und ihr Benutzer — sonst ``None`` (und die Sitzung endet)."""
    jetzt = _jetzt(jetzt)
    if not token or len(token) > 200:
        return None
    sitzung = repo.lade_sitzung_nach_hash(s, token_hash(token))
    if sitzung is None or sitzung.beendet_am is not None:
        return None
    leerlauf = timedelta(minutes=einstellungen.sitzung_leerlauf_minuten)
    b = repo.lade_benutzer_id(s, sitzung.benutzer_id)
    if (
        jetzt >= sitzung.laeuft_ab_am
        or jetzt - sitzung.zuletzt_aktiv_am > leerlauf
        or b is None
        or not b.aktiv
        or b.gesperrt(jetzt)
    ):
        repo.beende_sitzung(s, sitzung.id, jetzt)
        return None
    if jetzt - sitzung.zuletzt_aktiv_am >= _AKTIV_SPEICHERN_AB:
        repo.markiere_sitzung_aktiv(s, sitzung.id, jetzt)
        sitzung = sitzung.model_copy(update={"zuletzt_aktiv_am": jetzt})
    return sitzung, b


def wechsle_gesellschaft(
    s: Session, sitzung: Sitzung, gesellschaft: str, jetzt: datetime | None = None
) -> Sitzung:
    jetzt = _jetzt(jetzt)
    repo.markiere_sitzung_aktiv(s, sitzung.id, jetzt, gesellschaft)
    return sitzung.model_copy(
        update={"gesellschaft": gesellschaft, "zuletzt_aktiv_am": jetzt}
    )


def beende_sitzung(s: Session, token: str, jetzt: datetime | None = None) -> None:
    jetzt = _jetzt(jetzt)
    sitzung = repo.lade_sitzung_nach_hash(s, token_hash(token))
    if sitzung is not None and sitzung.beendet_am is None:
        repo.beende_sitzung(s, sitzung.id, jetzt)
        b = repo.lade_benutzer_id(s, sitzung.benutzer_id)
        ereignis(s, "abmeldung", jetzt, b.name if b else None, quelle="web")
