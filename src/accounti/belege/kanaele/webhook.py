"""Webhook-Kanal — Dateien, die ein Fremdsystem per HTTP schickt.

Der Kanal holt nichts ab, er empfängt: Der HTTP-Endpunkt (``accounti.belege.webhook``,
gestartet mit ``accounti kanaele webhook starten``) prüft Token, Größe und Typ und
reicht die Dateien über diesen Kanal an die Pipeline — wie jeder andere Kanal nur
Rohdatei plus Herkunft.
"""

from __future__ import annotations

from collections.abc import Iterator

from accounti.belege.kanaele import BelegKanal, RohBeleg, registriere

KANAL = "webhook"


@registriere
class WebhookKanal(BelegKanal):
    name = KANAL
    beschreibung = (
        "HTTP-Endpunkt für Fremdsysteme und Messenger, tokengeschützt "
        "(accounti kanaele webhook starten)"
    )

    def __init__(self, dateien: list[tuple[str, bytes]], herkunft: str) -> None:
        self.dateien = dateien
        self.herkunft = herkunft[:500]

    def abholen(self) -> Iterator[RohBeleg]:
        for dateiname, inhalt in self.dateien:
            yield RohBeleg(
                dateiname=dateiname, inhalt=inhalt, kanal=KANAL, herkunft=self.herkunft
            )
