"""OSS-Quartalsmeldung aus den gebuchten Marktplatz-Erlösen, gerechnet von steuer.oss.

Die Marktplatz-Buchung legt EU-Fernverkäufe an Privatkunden je Bestimmungsland auf die
OSS-Erlöskonten aus ``steuer.umsatzsteuer.OSS_ERLOES_KONTEN_SKR03``; die Meldung bildet
``steuer.oss.OSSEngine`` aus diesen Buchungen. Hier wird nur zusammengestellt.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from accounti.db.repository import lade_buchungen
from accounti.models import Buchungssatz, BuchungStatus
from accounti.steuer.oss import OSSEngine, OSSMeldung
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03


def oss_buchungen(session: Session, jahr: int, quartal: int) -> list[Buchungssatz]:
    """Buchungen eines Quartals auf OSS-Erlöskonten (Erlöse und Erstattungen)."""
    konten = set(OSS_ERLOES_KONTEN_SKR03.values())
    monate = range((quartal - 1) * 3 + 1, quartal * 3 + 1)
    return [
        b
        for b in lade_buchungen(session)
        if b.datum.year == jahr
        and b.datum.month in monate
        and (b.haben_konto in konten or b.soll_konto in konten)
    ]


def oss_meldung(
    session: Session, jahr: int, quartal: int, firmen_land: str = "DE"
) -> OSSMeldung:
    if quartal not in (1, 2, 3, 4):
        raise ValueError(f"Quartal {quartal} gibt es nicht")
    return OSSEngine(firmen_land).erstelle_meldung(
        oss_buchungen(session, jahr, quartal), jahr, quartal
    )


def ungepruefte(buchungen: list[Buchungssatz]) -> int:
    """Wie viele der Buchungen noch zur Prüfung liegen (Meldung dann vorläufig)."""
    return sum(1 for b in buchungen if b.status is BuchungStatus.ZUR_PRUEFUNG)
