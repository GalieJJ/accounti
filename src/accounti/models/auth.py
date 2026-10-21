"""Datenmodell für Anmeldung, Rollen, Sitzungen und API-Token (Baustein 10).

Rollen sind grobe Vorgaben und wirken je Gesellschaft; ein Benutzer kann mehrere
haben, seine Rechte sind die Vereinigung. Die Rollen sind bewusst nicht
hierarchisch: Wer bucht, gibt nicht automatisch Zahlungen frei — nur so kann das
Vier-Augen-Prinzip aus Baustein 6 greifen.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

NAME_MUSTER = re.compile(r"^[a-z0-9][a-z0-9._-]{1,49}$")
GESELLSCHAFT_MUSTER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,29}$")
STANDARD_GESELLSCHAFT = "standard"


class Rolle(str, enum.Enum):
    BETRACHTER = "betrachter"
    BUCHHALTER = "buchhalter"
    FREIGEBER = "freigeber"
    VERWALTER = "verwalter"


class Recht(str, enum.Enum):
    LESEN = "lesen"
    BUCHEN = "buchen"  # erfassen, prüfen, korrigieren
    BELEGE_EINLIEFERN = "belege_einliefern"
    LAEUFE_STARTEN = "laeufe_starten"
    BUCHUNG_FREIGEBEN = "buchung_freigeben"
    ZAHLUNG_FREIGEBEN = "zahlung_freigeben"
    STEUER_FREIGEBEN = "steuer_freigeben"
    VERWALTEN = "verwalten"  # Benutzer, Token, Einstellungen


RECHT_TEXT: dict[Recht, str] = {
    Recht.LESEN: "lesen",
    Recht.BUCHEN: "buchen und korrigieren",
    Recht.BELEGE_EINLIEFERN: "Belege einliefern",
    Recht.LAEUFE_STARTEN: "Läufe starten",
    Recht.BUCHUNG_FREIGEBEN: "Buchungen freigeben",
    Recht.ZAHLUNG_FREIGEBEN: "Zahlungsläufe freigeben",
    Recht.STEUER_FREIGEBEN: "Steuermeldungen freigeben",
    Recht.VERWALTEN: "Benutzer und Einstellungen verwalten",
}

ROLLEN_RECHTE: dict[Rolle, frozenset[Recht]] = {
    Rolle.BETRACHTER: frozenset({Recht.LESEN}),
    Rolle.BUCHHALTER: frozenset(
        {
            Recht.LESEN,
            Recht.BUCHEN,
            Recht.BELEGE_EINLIEFERN,
            Recht.LAEUFE_STARTEN,
            Recht.BUCHUNG_FREIGEBEN,
        }
    ),
    Rolle.FREIGEBER: frozenset(
        {
            Recht.LESEN,
            Recht.BUCHUNG_FREIGEBEN,
            Recht.ZAHLUNG_FREIGEBEN,
            Recht.STEUER_FREIGEBEN,
        }
    ),
    Rolle.VERWALTER: frozenset({Recht.LESEN, Recht.VERWALTEN}),
}


# Befehle der CLI je Recht — mit eingerichteten Benutzern nur mit Rolle und Einmalcode
# (Verfahrensdokumentation, docs/betrieb.md). Nicht gebunden sind Lesebefehle und
# maschinelle Läufe (classify, opos verbuchen, opos zuordnen, bank abgleich, import,
# bank lauf, aufgaben lauf, verfahrensdoku) — ihre Person ist im Journal „(ungeprüft)“.
FREIGABEWEGE: dict[Recht, tuple[str, ...]] = {
    Recht.BUCHEN: (
        "korrigiere",
        "buchung storniere",
        "kasse buchen|anfangsbestand|storno",
        "abschluss eroeffnung",
        "bank bestaetigen|ablehnen",
        "nachfordern anfrage --senden",
        "zahlung anlegen|entfernen|sperre|iban-klaeren|abgleichen",
    ),
    Recht.BUCHUNG_FREIGEBEN: (
        "bestaetige",
        "opos bestaetigen|ablehnen",
        "abschluss bestaetigen|ablehnen",
        "anlagen freigeben",
        "periode schliessen",
        "abschluss vortrag",
        "export datev",
        "datev belege",
    ),
    Recht.ZAHLUNG_FREIGEBEN: ("zahlung freigeben|stornieren|sepa",),
    Recht.STEUER_FREIGEBEN: (
        "ustva freigeben",
        "ustva dauerfrist --freigeben",
        "periode oeffnen",
        "abschluss oeffnen",
    ),
    Recht.VERWALTEN: ("benutzer …", "token …", "journal uebernehmen"),
}


def rechte_der_rollen(rollen: Iterable[Rolle]) -> set[Recht]:
    """Vereinigung der Rechte aller Rollen."""
    rechte: set[Recht] = set()
    for rolle in rollen:
        rechte |= ROLLEN_RECHTE[rolle]
    return rechte


class TokenRecht(str, enum.Enum):
    """Berechtigungen eines API-Tokens. Freigeben kann ein Token nie."""

    OPOS_LESEN = "opos:lesen"
    BUCHUNGEN_LESEN = "buchungen:lesen"
    BELEGE_SCHREIBEN = "belege:schreiben"
    LAEUFE_STARTEN = "laeufe:starten"


def pruefe_name(name: str) -> str:
    if not NAME_MUSTER.match(name):
        msg = (
            f"Ungültiger Benutzername {name!r} — 2 bis 50 Zeichen, klein: "
            "a–z, 0–9, Punkt, Unterstrich, Bindestrich"
        )
        raise ValueError(msg)
    return name


def pruefe_gesellschaft(kuerzel: str) -> str:
    if not GESELLSCHAFT_MUSTER.match(kuerzel):
        msg = (
            f"Ungültiges Kürzel {kuerzel!r} — bis 30 Zeichen, klein: a–z, 0–9, "
            "Unterstrich, Bindestrich"
        )
        raise ValueError(msg)
    return kuerzel


class Benutzer(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    anzeigename: str | None = None
    passwort_hash: str
    totp_chiffrat: str | None = Field(
        default=None, description="TOTP-Geheimnis, mit dem Tresor verschlüsselt"
    )
    totp_aktiv: bool = False
    totp_letzter_schritt: int | None = Field(
        default=None, description="zuletzt angenommener Zeitschritt (RFC 6238 5.2)"
    )
    fehlversuche: int = Field(default=0, description="Fehlversuche in Folge (Browser)")
    gesperrt_bis: datetime | None = None
    # die Server-Shell zählt getrennt: eine Flut aus dem Netz sperrt sie nie
    cli_fehlversuche: int = Field(default=0, description="Fehlversuche in Folge (CLI)")
    cli_gesperrt_bis: datetime | None = None
    aktiv: bool = True
    angelegt_am: datetime = Field(default_factory=datetime.now)
    passwort_geaendert_am: datetime | None = None
    letzte_anmeldung_am: datetime | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, wert: str) -> str:
        return pruefe_name(wert)

    def gesperrt(self, jetzt: datetime) -> bool:
        """Anmeldung im Browser gesperrt (Fehlversuche aus dem Netz)."""
        return self.gesperrt_bis is not None and self.gesperrt_bis > jetzt

    def cli_gesperrt(self, jetzt: datetime) -> bool:
        """Einmalcode in der CLI gesperrt (Fehlversuche auf der Server-Shell)."""
        return self.cli_gesperrt_bis is not None and self.cli_gesperrt_bis > jetzt


@dataclass(frozen=True)
class Rollenzuordnung:
    benutzer_id: UUID
    gesellschaft: str
    rolle: Rolle


class Wiederherstellungscode(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    benutzer_id: UUID
    code_hash: str
    angelegt_am: datetime
    verbraucht_am: datetime | None = None


class Sitzung(BaseModel):
    """Angemeldete Browser-Sitzung; das Token selbst kennt nur der Browser."""

    id: UUID = Field(default_factory=uuid4)
    token_hash: str = Field(description="SHA-256 des Sitzungstokens")
    benutzer_id: UUID
    gesellschaft: str
    angelegt_am: datetime
    zuletzt_aktiv_am: datetime
    laeuft_ab_am: datetime = Field(description="absolutes Ende")
    beendet_am: datetime | None = None


class ApiToken(BaseModel):
    """Zugang eines Fremdsystems zur REST-API — gespeichert wird nur der Hash."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    token_hash: str
    gesellschaft: str
    rechte: list[TokenRecht]
    angelegt_von: str
    angelegt_am: datetime
    gueltig_bis: date | None = Field(default=None, description="letzter gültiger Tag")
    widerrufen_am: datetime | None = None
    zuletzt_genutzt_am: datetime | None = None

    def gilt(self, jetzt: datetime) -> bool:
        if self.widerrufen_am is not None:
            return False
        return self.gueltig_bis is None or jetzt.date() <= self.gueltig_bis


class AuthEreignis(BaseModel):
    """Anmeldungen, Fehlversuche, Sperren, Rollen- und Tokenänderungen — nur
    anfügen. Keine Passwörter, Codes oder Token, keine IP-Adressen."""

    id: UUID = Field(default_factory=uuid4)
    zeitpunkt: datetime
    art: str
    benutzer: str | None = None
    gesellschaft: str | None = None
    quelle: str = Field(description="web, cli oder api")
    ok: bool = True
    hinweis: str | None = None
