"""Abschnittsleser der Einstellungen (Baustein 10c, Paket P4) — ohne Importe aus
Fachmodulen.

``lies_abschnitt(pfad, name)`` liefert den wirksamen Abschnitt als Zuordnung; die Lader
prüfen ihn wie bisher mit ihrem Modell. Vorrang (Spec E2, Plan D7):

1. Betriebsabschnitt (``server``, ``auth``, ``gesellschaften``, ``einstellungen``,
   ``database``) → Datei.
2. ``einstellungen.quelle: datei`` bzw. der Abschnitt in ``einstellungen.festgelegt`` →
   Datei.
3. Version im Schnappschuss (bzw. ``ueberlagert``) → ihre Daten. Betriebsfelder und
   Blätter mit ``${`` der Version entfallen; darüber kommen Betriebsfelder und
   Platzhalterblätter der Datei (Umgebung schlägt alles, feldweise). Listen von
   Zuordnungen werden über ``name`` zugeordnet.
4. Abschnitt der Datei — eine fehlende Datei ist ``{}`` (D25).
5. ``{}``: der Lader nimmt seine Standards.

Ein ``nur_db``-Abschnitt (``einrichtung``) liest nie die Datei.

**Stand** (``ContextVar``): Je CLI-Befehl bzw. Web-Anfrage einer (A54). Er heftet jede
Datei beim ersten Lesen an und hält einen Schnappschuss der Datenbank, genommen beim
Binden in einer kurzen Lesetransaktion (D3, D4, N10). Ohne Stand (Unit-Tests, Werkzeuge)
gilt nur die Datei. Im Web liest ein ungebundener Stand keinen Datenbank-Abschnitt
(``EinstellungsquelleFehlt``, D5), ebenso nicht aus einer anderen Konfiguration als der
der gebundenen Gesellschaft; in der CLI gilt die Datenbank des Befehls auch für eine
andere ``--config`` (E5), nur nicht für die Konfiguration einer anderen Gesellschaft der
Registry. Ist die Datenbank nicht lesbar, scheitert das erste Lesen eines
Datenbank-Abschnitts mit ``EinstellungenNichtLesbar`` statt still die Datei zu nehmen.

**Caches** je Prozess: geparste Dateien je Inhalts-Hash (M7), Versionen je
(Datenbank, Abschnitt, Zeilen-Hash) (G-N7) — beide unter einer Sperre (Threadpool).
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Literal, Protocol

import yaml

from accounti.einstellungen.inventar import ABSCHNITTE, BETRIEBSFELDER, info

if TYPE_CHECKING:
    from sqlalchemy import Connection, Engine


class KonfigurationError(ValueError):
    """Die Konfiguration fehlt oder ist unvollständig."""


class EinstellungsquelleFehlt(RuntimeError):  # noqa: N818 — Name wie im Plan (D5)
    """Ein Datenbank-Abschnitt ohne passend gebundenen Stand gelesen (fail-closed)."""


class EinstellungenNichtLesbar(RuntimeError):  # noqa: N818 — Name wie im Plan
    """Die Datenbank der Einstellungen ließ sich nicht lesen (fail-closed)."""


# ---------------------------------------------------------------------------
# Normalform (D9)
# ---------------------------------------------------------------------------


def normalform(wert: Any) -> Any:
    """``wert`` in JSON-Typen: Datum als ISO-Text, ``Decimal`` als Text, Schlüssel als
    Text, Tupel als Listen. In dieser Form werden Versionen gespeichert, gehasht,
    verglichen und ins Journal geschrieben; ein Typ ohne Normalform ist ein
    ``TypeError``."""
    if isinstance(wert, enum.Enum):  # vor str: (str, Enum) als sein Wert
        return normalform(wert.value)
    if isinstance(wert, Mapping):
        return {str(k): normalform(v) for k, v in wert.items()}
    if isinstance(wert, list | tuple):
        return [normalform(v) for v in wert]
    if wert is None or isinstance(wert, bool | int | str):
        return wert
    if isinstance(wert, float):
        if not math.isfinite(wert):
            msg = f"Zahl {wert!r} hat keine Normalform"
            raise TypeError(msg)
        return wert
    if isinstance(wert, datetime | date):
        return wert.isoformat()
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, PurePath):
        return str(wert)
    if isinstance(wert, set | frozenset):
        return sorted(normalform(v) for v in wert)
    msg = f"{type(wert).__name__} hat keine Normalform"
    raise TypeError(msg)


def _json(wert: Any) -> str:
    return json.dumps(wert, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def abschnitt_hash(daten: Mapping[str, Any] | None) -> str | None:
    """Hash eines Abschnitts in Normalform (``datei_hash``, D9) — ``None`` ohne ihn."""
    if daten is None:
        return None
    return hashlib.sha256(_json(normalform(daten)).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Text und Datei
# ---------------------------------------------------------------------------


def parse_text(text: str, *, grenze: int = 64 * 1024) -> Any:
    """YAML aus einer Eingabe (``--datei``, später die Experten-Ansicht): höchstens
    ``grenze`` Bytes, ohne Anker und Aliase (keine Vervielfachung beim Speichern als
    JSON); ein Fehler nennt Zeile und Spalte."""
    groesse = len(text.encode("utf-8"))
    if groesse > grenze:
        msg = f"zu groß ({groesse} Bytes, höchstens {grenze})"
        raise KonfigurationError(msg)
    try:
        for token in yaml.scan(text, Loader=yaml.SafeLoader):
            if isinstance(token, yaml.AnchorToken | yaml.AliasToken):
                stelle = token.start_mark
                msg = (
                    f"Zeile {stelle.line + 1}, Spalte {stelle.column + 1}: Anker und "
                    "Aliase (&, *) sind nicht erlaubt"
                )
                raise KonfigurationError(msg)
        return yaml.safe_load(text)
    except yaml.YAMLError as fehler:
        stelle = getattr(fehler, "problem_mark", None)
        wo = f"Zeile {stelle.line + 1}, Spalte {stelle.column + 1}: " if stelle else ""
        grund = getattr(fehler, "problem", None) or fehler
        msg = f"{wo}kein gültiges YAML ({grund})"
        raise KonfigurationError(msg) from fehler


_GEPARST: OrderedDict[str, dict[str, Any]] = OrderedDict()
_GEPARST_GRENZE = 64  # Dateiinhalte je Prozess
_SPERRE = threading.Lock()


def _pfadschluessel(pfad: str | Path) -> str:
    return str(Path(pfad).expanduser().resolve())


def _lies_datei(pfad: Path) -> tuple[str | None, dict[str, Any]]:
    """(Inhalts-Hash, geparste Datei) — fehlt die Datei: ``(None, {})`` (D25). Die
    Datei wird jedes Mal gelesen (klein); gecacht ist nur das Parsen, Schlüssel ist der
    SHA-256 des Inhalts (M7)."""
    try:
        inhalt = pfad.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None, {}
    except OSError as fehler:
        msg = f"{pfad}: nicht lesbar ({fehler.strerror or fehler})"
        raise KonfigurationError(msg) from fehler
    schluessel = hashlib.sha256(inhalt).hexdigest()
    with _SPERRE:
        if schluessel in _GEPARST:
            _GEPARST.move_to_end(schluessel)
            return schluessel, _GEPARST[schluessel]
    try:
        text = inhalt.decode("utf-8")
    except UnicodeDecodeError as fehler:
        raise KonfigurationError(f"{pfad}: keine UTF-8-Datei ({fehler})") from fehler
    try:
        daten: Any = yaml.safe_load(text) or {}
    except yaml.YAMLError as fehler:
        raise KonfigurationError(f"{pfad}: kein gültiges YAML ({fehler})") from fehler
    geparst: dict[str, Any] = daten if isinstance(daten, dict) else {}
    with _SPERRE:
        _GEPARST[schluessel] = geparst
        while len(_GEPARST) > _GEPARST_GRENZE:
            _GEPARST.popitem(last=False)
    return schluessel, geparst


def _angeheftet(stand: Stand | None, pfad: Path) -> tuple[str | None, dict[str, Any]]:
    """(Inhalts-Hash, Datei), wie der Stand sie sieht (beim ersten Lesen angeheftet)."""
    if stand is None:
        return _lies_datei(pfad)
    schluessel = _pfadschluessel(pfad)
    if schluessel not in stand.dateien:
        stand.dateien[schluessel] = _lies_datei(pfad)
    return stand.dateien[schluessel]


def _datei(stand: Stand | None, pfad: Path) -> dict[str, Any]:
    """Die Datei, wie der Stand sie sieht. Nur lesen — nach außen geht immer eine
    Kopie."""
    return _angeheftet(stand, pfad)[1]


def lies_datei(pfad: str | Path) -> dict[str, Any]:
    """Die ganze Datei (Registry, Export) — eine Kopie; fehlt sie: ``{}``."""
    return copy.deepcopy(_datei(_STAND.get(), Path(pfad)))


def datei_vorhanden(pfad: str | Path) -> bool:
    """Gibt es die Datei (wie der Stand sie sieht)? Nur für den Wortlaut der Meldung
    ohne Quelle („fehlt — Vorlage kopieren“ statt „Abschnitt fehlt“, D25) — die Lader
    fragen nicht selbst nach der Datei."""
    return _angeheftet(_STAND.get(), Path(pfad))[0] is not None


def _abschnitt_der_datei(
    datei: Mapping[str, Any], pfad: Path, name: str
) -> dict[str, Any] | None:
    wert = datei.get(name)
    if wert is None:
        return None
    if not isinstance(wert, dict):
        msg = f"{pfad}: Abschnitt '{name}' muss eine Zuordnung sein"
        raise KonfigurationError(msg)
    return wert


def _festlegung(datei: Mapping[str, Any], pfad: Path) -> tuple[bool, frozenset[str]]:
    """(``einstellungen.quelle: datei``?, ``einstellungen.festgelegt``) der Datei."""
    abschnitt = _abschnitt_der_datei(datei, pfad, "einstellungen") or {}
    quelle = abschnitt.get("quelle", "datenbank")
    if quelle not in ("datenbank", "datei"):
        msg = f"{pfad}: einstellungen.quelle {quelle!r}: datenbank oder datei"
        raise KonfigurationError(msg)
    festgelegt = abschnitt.get("festgelegt") or []
    if not isinstance(festgelegt, list):
        msg = f"{pfad}: einstellungen.festgelegt: Liste von Abschnitten erwartet"
        raise KonfigurationError(msg)
    erlaubt = {n for n, i in ABSCHNITTE.items() if i.ziel == "db"}
    unbekannt = sorted(str(n) for n in festgelegt if n not in erlaubt)
    if unbekannt:
        msg = (
            f"{pfad}: einstellungen.festgelegt: unbekannter Abschnitt "
            f"{', '.join(unbekannt)} (möglich: {', '.join(sorted(erlaubt))})"
        )
        raise KonfigurationError(msg)
    return quelle == "datei", frozenset(str(n) for n in festgelegt)


# ---------------------------------------------------------------------------
# Datenbank: Quelle und Schnappschuss
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Zeile:
    """Die wirksame Version eines Abschnitts im Schnappschuss."""

    abschnitt: str
    version: int
    hash: str
    daten: dict[str, Any]
    erstellt_am: datetime | None
    person: str
    datei_hash: str | None


@dataclass(frozen=True)
class Schnappschuss:
    versionen: Mapping[str, Zeile] = field(default_factory=dict)
    chiffrate: Mapping[str, str] = field(default_factory=dict)
    fehler: str | None = None  # die Datenbank ließ sich nicht lesen


LEER = Schnappschuss()


class Quelle(Protocol):
    @property
    def schluessel(self) -> str: ...

    def schnappschuss(self, stichtag: datetime | None = None) -> Schnappschuss: ...


# Versionen je (Datenbank, Abschnitt, Zeilen-Hash) — eine unter derselben URL neu
# angelegte Datenbank hat andere Hashes (G-N7)
_ZEILEN: OrderedDict[tuple[str, str, str], Zeile] = OrderedDict()
_ZEILEN_GRENZE = 4096

_NEUESTE = (
    "SELECT e.abschnitt, e.version, e.hash FROM einstellungen e WHERE e.version = "
    "(SELECT max(v.version) FROM einstellungen v WHERE v.abschnitt = e.abschnitt{bis})"
)
_ZEILE = (
    "SELECT abschnitt, version, hash, daten, erstellt_am, person, datei_hash "
    "FROM einstellungen WHERE hash = :hash"
)


def _sqlite_datei(url: str) -> Path | None:
    """Die Datei einer SQLite-URL (``None`` für andere Datenbanken, ``:memory:`` und
    eine ungültige URL)."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    try:
        adresse = make_url(url)
    except ArgumentError:
        return None
    if adresse.get_backend_name() != "sqlite":
        return None
    datenbank = adresse.database or ""
    if datenbank in ("", ":memory:") or datenbank.startswith("file:"):
        return None
    return Path(datenbank)


def _url_schluessel(url: str) -> str:
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    datei = _sqlite_datei(url)
    if datei is not None:
        return f"sqlite:{_pfadschluessel(datei)}"
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:  # der Schnappschuss meldet den Fehler
        return "ungueltig:" + hashlib.sha256(url.encode()).hexdigest()


def _fehlertext(fehler: BaseException) -> str:
    ursache = getattr(fehler, "orig", None) or fehler
    zeile = (str(ursache).strip().splitlines() or [""])[0]
    return f"{type(ursache).__name__}: {zeile}"[:300]


class DatenbankQuelle:
    """Einstellungen aus einer Datenbank — über eine URL (eigene Engine je
    Schnappschuss, ohne Pool) oder eine vorhandene Engine (Web, ``Dienste``). Legt keine
    SQLite-Datei an; ohne Tabelle ``einstellungen`` (Schema vor P4) ist sie leer."""

    def __init__(self, url: str | None = None, *, engine: Engine | None = None) -> None:
        if (url is None) == (engine is None):
            msg = "DatenbankQuelle braucht genau eines: url oder engine"
            raise ValueError(msg)
        self._url = url
        self._engine = engine
        if engine is not None:
            url = engine.url.render_as_string(hide_password=False)
        assert url is not None
        self._schluessel = _url_schluessel(url)

    @property
    def schluessel(self) -> str:
        return self._schluessel

    def __repr__(self) -> str:
        return f"DatenbankQuelle({self._schluessel})"

    def schnappschuss(self, stichtag: datetime | None = None) -> Schnappschuss:
        from sqlalchemy.exc import SQLAlchemyError

        try:
            if self._engine is not None:
                with self._engine.connect() as verbindung:
                    return self._lies(verbindung, stichtag)
            assert self._url is not None
            datei = _sqlite_datei(self._url)
            if datei is not None and not datei.exists():
                return LEER  # keine neue Datei anlegen
            engine = self._neue_engine(self._url)
            try:
                with engine.connect() as verbindung:
                    return self._lies(verbindung, stichtag)
            finally:
                engine.dispose()
        except (SQLAlchemyError, ImportError, OSError) as fehler:
            return Schnappschuss(fehler=_fehlertext(fehler))

    @staticmethod
    def _neue_engine(url: str) -> Engine:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        zusatz = {"connect_args": {"timeout": 30}} if url.startswith("sqlite") else {}
        return create_engine(url, poolclass=NullPool, hide_parameters=True, **zusatz)

    def _lies(self, verbindung: Connection, stichtag: datetime | None) -> Schnappschuss:
        """Eine kurze Lesetransaktion: neueste Version je Abschnitt (bis ``stichtag``),
        Zeilen nur, wo der Prozess-Cache den Hash nicht kennt, dazu die Chiffrate."""
        from sqlalchemy import DateTime, bindparam, inspect, text

        pruefer = inspect(verbindung)
        versionen: dict[str, Zeile] = {}
        if pruefer.has_table("einstellungen"):
            if stichtag is None:
                abfrage = text(_NEUESTE.format(bis=""))
            else:
                abfrage = text(
                    _NEUESTE.format(bis=" AND v.erstellt_am <= :bis")
                ).bindparams(bindparam("bis", stichtag, type_=DateTime))
            for abschnitt, _, zeilen_hash in verbindung.execute(abfrage):
                schluessel = (self._schluessel, abschnitt, zeilen_hash)
                with _SPERRE:
                    zeile = _ZEILEN.get(schluessel)
                if zeile is None:
                    roh = (
                        verbindung.execute(
                            text(_ZEILE).columns(erstellt_am=DateTime),
                            {"hash": zeilen_hash},
                        )
                        .mappings()
                        .one()
                    )
                    zeile = Zeile(
                        abschnitt=roh["abschnitt"],
                        version=int(roh["version"]),
                        hash=roh["hash"],
                        daten=json.loads(roh["daten"]),
                        erstellt_am=roh["erstellt_am"],
                        person=roh["person"],
                        datei_hash=roh["datei_hash"],
                    )
                    with _SPERRE:
                        _ZEILEN[schluessel] = zeile
                        while len(_ZEILEN) > _ZEILEN_GRENZE:
                            _ZEILEN.popitem(last=False)
                versionen[abschnitt] = zeile
        chiffrate: dict[str, str] = {}
        if pruefer.has_table("geheimnisse"):
            for name, chiffrat in verbindung.execute(
                text("SELECT name, chiffrat FROM geheimnisse")
            ):
                chiffrate[name] = chiffrat
        return Schnappschuss(versionen=versionen, chiffrate=chiffrate)


# ---------------------------------------------------------------------------
# Stand
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class Stand:
    """Was ein CLI-Befehl bzw. eine Web-Anfrage liest — veränderlich, damit eine
    Bindung im Threadpool (kopierter Kontext) auch den Endpunkt erreicht (D4).

    ``ersatz``: Quelle für einen Befehl, der bis zum ersten Lesen nicht gebunden ist
    (CLI: Standarddatenbank, D3). ``fremde_pfade``: Konfigurationen anderer
    Gesellschaften der Registry (CLI, D5)."""

    web: bool = False
    stichtag: datetime | None = None
    ersatz: Callable[[], Quelle] | None = None
    fremde_pfade: frozenset[str] = frozenset()
    quelle: Quelle | None = None
    konfiguration: str | None = None  # aufgelöster Pfad der gebundenen Gesellschaft
    streng: bool = False
    kuerzel: str | None = None
    dateien: dict[str, tuple[str | None, dict[str, Any]]] = field(default_factory=dict)
    ueberlagerung: dict[str, dict[str, Any]] = field(default_factory=dict)
    _schnappschuss: Schnappschuss | None = None
    _basis: Stand | None = None

    @property
    def gebunden(self) -> bool:
        return self._wurzel().quelle is not None

    def _wurzel(self) -> Stand:
        return self._basis._wurzel() if self._basis is not None else self

    def binde(
        self,
        quelle: Quelle,
        konfiguration: str | Path | None = None,
        *,
        streng: bool = False,
        kuerzel: str | None = None,
    ) -> None:
        """An ``quelle`` binden und **sofort** den Schnappschuss nehmen (D3, D4) — vor
        dem Rumpf des Befehls bzw. dem Endpunkt; dieselbe Quelle noch einmal ändert
        nichts (ein Stand je Befehl)."""
        ziel = self._wurzel()
        pfad = _pfadschluessel(konfiguration) if konfiguration is not None else None
        if (
            ziel.quelle is not None
            and ziel.quelle.schluessel == quelle.schluessel
            and (pfad is None or pfad == ziel.konfiguration)
        ):
            return
        ziel.quelle = quelle
        ziel.konfiguration = pfad
        ziel.streng = streng
        ziel.kuerzel = kuerzel
        ziel._schnappschuss = quelle.schnappschuss(ziel.stichtag)

    def schnappschuss(self) -> Schnappschuss:
        ziel = self._wurzel()
        if ziel._schnappschuss is None:
            if ziel.ersatz is not None:
                ziel.binde(ziel.ersatz(), kuerzel=ziel.kuerzel)
            elif ziel.web:
                msg = "Die Anfrage ist an keine Gesellschaft gebunden"
                raise EinstellungsquelleFehlt(msg)
            else:
                return LEER  # Werkzeug ohne Quelle: nur die Datei
        assert ziel._schnappschuss is not None
        if ziel._schnappschuss.fehler is not None:
            msg = (
                "Die Einstellungen in der Datenbank ließen sich nicht lesen "
                f"({ziel._schnappschuss.fehler}) — es gilt nicht still die Datei"
            )
            raise EinstellungenNichtLesbar(msg)
        return ziel._schnappschuss

    def pruefe_pfad(self, pfad: Path, name: str) -> None:
        """Gehört ``pfad`` zum gebundenen Stand? Sonst ``EinstellungsquelleFehlt``."""
        ziel = self._wurzel()
        schluessel = _pfadschluessel(pfad)
        if ziel.konfiguration is not None and schluessel == ziel.konfiguration:
            return
        if ziel.streng:
            msg = (
                f"Einstellungen '{name}' aus einer Konfiguration, die nicht zur "
                "gebundenen Gesellschaft gehört"
            )
            raise EinstellungsquelleFehlt(msg)
        if schluessel in ziel.fremde_pfade:
            msg = (
                f"Einstellungen '{name}' aus der Konfiguration einer anderen "
                "Gesellschaft — je Gesellschaft unter mit_quelle lesen"
            )
            raise EinstellungsquelleFehlt(msg)

    def abgeleitet(self, ueberlagerung: dict[str, dict[str, Any]]) -> Stand:
        """Derselbe Stand mit Abschnitten, die als Versionen wirken (ueberlagert)."""
        return replace(
            self, ueberlagerung={**self.ueberlagerung, **ueberlagerung}, _basis=self
        )


_STAND: ContextVar[Stand | None] = ContextVar(
    "accounti_einstellungsstand", default=None
)
_PRUEFMODUS: ContextVar[bool] = ContextVar("accounti_pruefmodus", default=False)


def aktueller_stand() -> Stand | None:
    return _STAND.get()


def setze_stand(stand: Stand | None) -> Any:
    """Für Middleware und Callback: Token zum Zurücksetzen (``ruecksetzen``)."""
    return _STAND.set(stand)


def ruecksetzen(token: Any) -> None:
    _STAND.reset(token)


@contextmanager
def neuer_stand(
    *,
    web: bool = False,
    ersatz: Callable[[], Quelle] | None = None,
    fremde_pfade: frozenset[str] = frozenset(),
) -> Iterator[Stand]:
    """Ein neuer, ungebundener Stand für den Block (CLI-Befehl, Web-Anfrage)."""
    stand = Stand(web=web, ersatz=ersatz, fremde_pfade=fremde_pfade)
    token = _STAND.set(stand)
    try:
        yield stand
    finally:
        _STAND.reset(token)


@contextmanager
def mit_quelle(
    quelle: Quelle | None,
    konfiguration: str | Path | None = None,
    stichtag: datetime | None = None,
) -> Iterator[Stand]:
    """Ein eigener Stand für den Block, an ``quelle`` gebunden (``None``: nur die
    Datei) — für Lesen über Gesellschaften hinweg und zum Stichtag. Mit
    ``konfiguration`` gilt er nur für diese Datei (streng)."""
    stand = Stand(stichtag=stichtag)
    if quelle is not None:
        stand.binde(quelle, konfiguration, streng=konfiguration is not None)
    token = _STAND.set(stand)
    try:
        yield stand
    finally:
        _STAND.reset(token)


@contextmanager
def ueberlagert(abschnitte: Mapping[str, Mapping[str, Any]]) -> Iterator[None]:
    """Im Block wirken ``abschnitte`` wie Versionen (mit Betriebs- und
    Platzhalterfeldern der Datei darüber) — für die Validierung über die Lader."""
    basis = _STAND.get() or Stand()
    neu = basis.abgeleitet({k: copy.deepcopy(dict(v)) for k, v in abschnitte.items()})
    token = _STAND.set(neu)
    try:
        yield
    finally:
        _STAND.reset(token)


@contextmanager
def pruefmodus() -> Iterator[None]:
    """Im Block bleibt ein fehlender ``${VAR}`` als Text stehen (D16)."""
    token = _PRUEFMODUS.set(True)
    try:
        yield
    finally:
        _PRUEFMODUS.reset(token)


def im_pruefmodus() -> bool:
    return _PRUEFMODUS.get()


class _HatQuelle(Protocol):
    def quelle(self, kuerzel: str) -> Quelle: ...


class _Gesellschaft(Protocol):
    @property
    def kuerzel(self) -> str: ...

    @property
    def konfiguration(self) -> str: ...


def binde_gesellschaft(stand: Stand, dienste: _HatQuelle, g: _Gesellschaft) -> None:
    """Web: den Stand der Anfrage an die Gesellschaft binden (streng, D4, D5)."""
    stand.binde(
        dienste.quelle(g.kuerzel), g.konfiguration, streng=True, kuerzel=g.kuerzel
    )


# ---------------------------------------------------------------------------
# Wirksamer Abschnitt
# ---------------------------------------------------------------------------

Segment = str | tuple[str, str]  # Schlüssel bzw. ("name", Wert) in einer Liste
Pfad = tuple[Segment, ...]


def _benannt(liste: list[Any]) -> bool:
    return bool(liste) and all(
        isinstance(e, dict) and isinstance(e.get("name"), str) for e in liste
    )


def _hat_platzhalter(wert: Any) -> bool:
    if isinstance(wert, str):
        return "${" in wert
    if isinstance(wert, dict):
        return any(_hat_platzhalter(k) or _hat_platzhalter(v) for k, v in wert.items())
    if isinstance(wert, list):
        return any(_hat_platzhalter(v) for v in wert)
    return False


def _platzhalterblaetter(knoten: Any, pfad: Pfad = ()) -> Iterator[tuple[Pfad, Any]]:
    """Blätter mit ``${`` (auch ein Schlüssel mit ``${`` samt Wert); Listen von
    Zuordnungen über ``name``, andere Listen als ein Blatt."""
    if isinstance(knoten, dict):
        for schluessel, wert in knoten.items():
            if _hat_platzhalter(schluessel):
                yield (*pfad, str(schluessel)), wert
            else:
                yield from _platzhalterblaetter(wert, (*pfad, str(schluessel)))
    elif isinstance(knoten, list) and _benannt(knoten):
        for element in knoten:
            yield from _platzhalterblaetter(element, (*pfad, ("name", element["name"])))
    elif _hat_platzhalter(knoten):
        yield pfad, knoten


def _ohne_platzhalter(knoten: Any) -> Any:
    """``knoten`` ohne jedes Blatt mit ``${`` (D7: nie aus der Datenbank)."""
    if isinstance(knoten, list) and _benannt(knoten):
        return [_ohne_platzhalter(e) for e in knoten]
    if not isinstance(knoten, dict):
        return knoten
    neu: dict[str, Any] = {}
    for schluessel, wert in knoten.items():
        if _hat_platzhalter(schluessel):
            continue
        if isinstance(wert, dict) or (isinstance(wert, list) and _benannt(wert)):
            neu[schluessel] = _ohne_platzhalter(wert)
        elif not _hat_platzhalter(wert):
            neu[schluessel] = wert
    return neu


def _muster(abschnitt: str) -> list[tuple[str, ...]]:
    """Betriebsfelder des Abschnitts als Segmente (``[]`` für Listenelemente)."""
    muster = []
    for eintrag in sorted(BETRIEBSFELDER):
        kopf, _, rest = eintrag.partition(".")
        if kopf != abschnitt:
            continue
        segmente: list[str] = []
        for teil in rest.split("."):
            if teil.endswith("[]"):
                segmente += [teil[:-2], "[]"]
            else:
                segmente.append(teil)
        muster.append(tuple(segmente))
    return muster


def _betriebsblaetter(
    knoten: Any, muster: tuple[str, ...], pfad: Pfad = ()
) -> Iterator[tuple[Pfad, Any]]:
    """Konkrete Pfade und Werte zu einem Betriebsfeld-Muster in ``knoten``."""
    if not muster:
        yield pfad, knoten
        return
    kopf, rest = muster[0], muster[1:]
    if kopf == "[]":
        if isinstance(knoten, list):
            for element in knoten:
                if isinstance(element, dict) and isinstance(element.get("name"), str):
                    weiter = (*pfad, ("name", element["name"]))
                    yield from _betriebsblaetter(element, rest, weiter)
        return
    if isinstance(knoten, dict) and kopf in knoten:
        yield from _betriebsblaetter(knoten[kopf], rest, (*pfad, kopf))


def _ohne_betrieb(knoten: Any, muster: tuple[str, ...]) -> None:
    """Das Betriebsfeld-Muster aus ``knoten`` entfernen (an Ort und Stelle)."""
    kopf, rest = muster[0], muster[1:]
    if kopf == "[]":
        if isinstance(knoten, list):
            for element in knoten:
                if isinstance(element, dict) and rest:
                    _ohne_betrieb(element, rest)
        return
    if not isinstance(knoten, dict) or kopf not in knoten:
        return
    if not rest:
        del knoten[kopf]
    else:
        _ohne_betrieb(knoten[kopf], rest)


def _setze(knoten: dict[str, Any], pfad: Pfad, wert: Any) -> None:
    """``wert`` an ``pfad`` setzen; Zwischenstufen entstehen als Zuordnung, ein
    Listenelement nur, wenn es den ``name`` schon gibt."""
    aktuell: Any = knoten
    for i, segment in enumerate(pfad):
        letztes = i == len(pfad) - 1
        if isinstance(segment, tuple):
            if not isinstance(aktuell, list):
                return
            treffer = [
                e
                for e in aktuell
                if isinstance(e, dict) and e.get("name") == segment[1]
            ]
            if not treffer:
                return
            if letztes:  # pragma: no cover — ein Blatt ist nie ein ganzes Element
                return
            aktuell = treffer[0]
            continue
        if not isinstance(aktuell, dict):
            return
        if letztes:
            aktuell[segment] = copy.deepcopy(wert)
            return
        naechster = pfad[i + 1]
        if segment not in aktuell or not isinstance(
            aktuell[segment], list if isinstance(naechster, tuple) else dict
        ):
            if isinstance(naechster, tuple):
                return
            aktuell[segment] = {}
        aktuell = aktuell[segment]


def _mit_datei(
    version: Mapping[str, Any], datei: Mapping[str, Any], abschnitt: str
) -> dict[str, Any]:
    """Die Daten einer Version mit den Werten, die immer aus der Datei kommen (D7):
    ohne ``${`` und ohne Betriebsfelder der Version, darüber Betriebsfelder und
    Platzhalterblätter der Datei."""
    daten: dict[str, Any] = _ohne_platzhalter(copy.deepcopy(dict(version)))
    muster = _muster(abschnitt)
    for m in muster:
        _ohne_betrieb(daten, m)
    for m in muster:
        for pfad, wert in _betriebsblaetter(datei, m):
            _setze(daten, pfad, wert)
    for pfad, wert in _platzhalterblaetter(datei):
        _setze(daten, pfad, wert)
    return daten


Art = Literal["datenbank", "datei", "standard", "festgelegt", "betrieb"]


@dataclass(frozen=True)
class HerkunftRoh:
    """Woher ein Abschnitt kommt (D23; ``abweichend`` bestimmt ``pruefung.herkunft``).

    ``datei_hash``: Hash des Datei-Abschnitts jetzt; ``version_datei_hash``: der beim
    Schreiben der Version (beides ``None`` ohne Abschnitt in der Datei)."""

    art: Art
    version: int | None = None
    erstellt_am: datetime | None = None
    person: str | None = None
    datei_hash: str | None = None
    version_datei_hash: str | None = None


def _ueberlagerte_zeile(stand: Stand, name: str) -> Zeile | None:
    daten = stand.ueberlagerung.get(name)
    if daten is None:
        return None
    return Zeile(name, 0, "", daten, None, "", None)


def _wirksam(
    pfad: str | Path, name: str
) -> tuple[dict[str, Any], Art, Zeile | None, dict[str, Any] | None]:
    """(wirksame Daten — nur lesen, Art, Version, Abschnitt der Datei)."""
    pfad = Path(pfad)
    stand = _STAND.get()
    abschnitt = info(name)
    datei = _datei(stand, pfad)
    eigen = _abschnitt_der_datei(datei, pfad, name)
    if abschnitt.ziel == "datei":
        return eigen or {}, "betrieb", None, eigen
    if stand is not None:
        stand.pruefe_pfad(pfad, name)
        if not stand.gebunden and stand.web and name not in stand.ueberlagerung:
            stand.schnappschuss()  # ungebunden im Web: EinstellungsquelleFehlt
    if abschnitt.ziel == "db":
        nur_datei, festgelegt = _festlegung(datei, pfad)
        if nur_datei or name in festgelegt:
            return eigen or {}, "festgelegt", None, eigen
    zeile = None
    if stand is not None:
        zeile = _ueberlagerte_zeile(stand, name) or stand.schnappschuss().versionen.get(
            name
        )
    if zeile is not None:
        return _mit_datei(zeile.daten, eigen or {}, name), "datenbank", zeile, eigen
    if abschnitt.ziel == "nur_db" or eigen is None:
        return {}, "standard", None, eigen
    return eigen, "datei", None, eigen


def lies_abschnitt(pfad: str | Path, name: str) -> dict[str, Any]:
    """Der wirksame Abschnitt (eine Kopie): ohne Geheimnisse der Datenbank, ohne
    ``${…}`` aus der Datenbank; eine fehlende Datei ist ``{}`` (D25)."""
    return copy.deepcopy(_wirksam(pfad, name)[0])


def quelle_vorhanden(pfad: str | Path, name: str) -> bool:
    """Gibt es den Abschnitt in der Datei oder als Version bzw. Überlagerung? Sonst
    melden Lader wie bisher „Vorlage kopieren“ (D25)."""
    _, art, _, eigen = _wirksam(pfad, name)
    return art == "datenbank" or eigen is not None


def herkunft_roh(pfad: str | Path, name: str) -> HerkunftRoh:
    _, art, zeile, eigen = _wirksam(pfad, name)
    datei_hash = abschnitt_hash(eigen)
    if zeile is None:
        return HerkunftRoh(art, datei_hash=datei_hash)
    return HerkunftRoh(
        art,
        version=zeile.version,
        erstellt_am=zeile.erstellt_am,
        person=zeile.person,
        datei_hash=datei_hash,
        version_datei_hash=zeile.datei_hash,
    )
