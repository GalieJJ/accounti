"""Einnahmenüberschussrechnung nach dem Schema der Anlage EÜR.

Jedes erfolgswirksame Konto der Summen- und Saldenliste (bei EÜR auch Vorsteuer,
Umsatzsteuer und USt-Vorauszahlungen) geht über seine Kennzahl in eine Zeile des
Vordrucks des jeweiligen Jahres. Konten ohne Zeile erscheinen als „nicht zugeordnet“
und zählen trotzdem mit. Nicht abziehbare Betriebsausgaben (Kz 162, 164, 165, 168 — dort
auch die Gewerbesteuer, § 4 Abs. 5b EStG) stehen in eigener Spalte und mindern die
Summe der Betriebsausgaben nicht. Konten mit der Kennzahl „-“ (Steuern vom Einkommen,
Spenden, kalkulatorische Kosten, Bestandsveränderungen) gehören gar nicht in die EÜR.
Die Überleitung zum Ergebnis der SuSa ist ausgewiesen:
Ergebnis = Gewinn − nicht abziehbare Betriebsausgaben − Konten außerhalb der EÜR.

Die Zeilen ab „Ermittlung des Gewinns“ (Hinzurechnungen, Kürzungen, § 7g, § 4 Abs. 4a)
berechnet accounti nicht.

Abweichendes Wirtschaftsjahr (``datev.wirtschaftsjahr_beginn``): Die EÜR umfasst das
Wirtschaftsjahr, Vordruck des Kalenderjahres seines **Beginns** — die Anlage EÜR 2025
gilt für das Kalenderjahr 2025 bzw. das Wirtschaftsjahr 2025/2026 (Kz 131
„abweichender Beginn TTMM 2025“, BMF 29.08.2025). Land- und Forstwirte — auch
mit EÜR (§ 4a Abs. 1 Satz 2 Nr. 1 EStG) — verteilen den Gewinn zeitanteilig auf die
beiden Kalenderjahre (§ 4a Abs. 2 Nr. 1 EStG, ohne Veräußerungsgewinne); accounti
rechnet die Verteilung nach Monaten als Hinweis aus, trägt sie aber in keinen Vordruck
ein (Anlage L/ESt mit dem Steuerberater).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import cache
from importlib import resources
from typing import Any

import yaml

from accounti.abschluss.konfiguration import Wirtschaftsjahr
from accounti.abschluss.kontenrahmen import NICHT_IN_EUER, Kontenart, Kontenrahmen
from accounti.abschluss.salden import Susa
from accounti.anlagen.afa import runde
from accounti.anzeige import betrag_de

NULL = Decimal("0")
AUSSERHALB_TEXT = "Nicht in der EÜR (keine Betriebseinnahme/-ausgabe)"


class EuerError(ValueError):
    """Die EÜR lässt sich so nicht erstellen."""


@dataclass
class EuerZeile:
    kz: str | None
    zeile: int | None
    text: str
    konten: dict[str, Decimal] = field(default_factory=dict)

    @property
    def betrag(self) -> Decimal:
        return sum(self.konten.values(), NULL)


@dataclass
class Euer:
    jahr: int
    vordruck_jahr: int
    quelle: str
    einnahmen: list[EuerZeile] = field(default_factory=list)
    ausgaben: list[EuerZeile] = field(default_factory=list)
    nicht_abziehbar: list[EuerZeile] = field(default_factory=list)
    nicht_zugeordnet: list[EuerZeile] = field(default_factory=list)
    ausserhalb: list[EuerZeile] = field(default_factory=list)  # Saldo Soll − Haben
    entnahmen: Decimal = NULL
    einlagen: Decimal = NULL
    summe_einnahmen_zeile: int = 0
    summe_ausgaben_zeile: int = 0
    gewinn_zeilen: tuple[int, int] = (0, 0)
    entnahmen_zeile: int = 0
    einlagen_zeile: int = 0
    hinweise: list[str] = field(default_factory=list)

    def zeile(self, kz: str) -> EuerZeile | None:
        return next((z for z in [*self.einnahmen, *self.ausgaben] if z.kz == kz), None)

    def _nicht_zugeordnet(self, einnahme: bool) -> Decimal:
        return sum(
            (
                z.betrag
                for z in self.nicht_zugeordnet
                if (z.text == "Einnahmen") == einnahme
            ),
            NULL,
        )

    @property
    def summe_einnahmen(self) -> Decimal:
        return sum((z.betrag for z in self.einnahmen), NULL) + self._nicht_zugeordnet(
            True
        )

    @property
    def summe_ausgaben(self) -> Decimal:
        return sum((z.betrag for z in self.ausgaben), NULL) + self._nicht_zugeordnet(
            False
        )

    @property
    def summe_nicht_abziehbar(self) -> Decimal:
        return sum((z.betrag for z in self.nicht_abziehbar), NULL)

    @property
    def summe_ausserhalb(self) -> Decimal:
        return sum((z.betrag for z in self.ausserhalb), NULL)

    @property
    def gewinn(self) -> Decimal:
        """Summe Betriebseinnahmen − Summe Betriebsausgaben (vor Hinzurechnungen)."""
        return self.summe_einnahmen - self.summe_ausgaben


@cache
def lade_vordrucke() -> dict[int, dict[str, Any]]:
    text = (
        resources.files("accounti.abschluss")
        .joinpath("euer_vordrucke.yaml")
        .read_text(encoding="utf-8")
    )
    daten: dict[str, dict[str, Any]] = yaml.safe_load(text)
    return {int(jahr): vordruck for jahr, vordruck in daten.items()}


def _vordruck(jahr: int) -> tuple[int, dict[str, Any]]:
    vordrucke = lade_vordrucke()
    passend = [j for j in vordrucke if j <= jahr]
    if not passend:
        raise EuerError(f"Kein Vordruck der Anlage EÜR für {jahr} hinterlegt")
    gewaehlt = max(passend)
    return gewaehlt, vordrucke[gewaehlt]


def erstelle_euer(susa: Susa, kr: Kontenrahmen) -> Euer:
    if susa.gewinnermittlung != "euer":
        msg = f"Gewinnermittlung ist {susa.gewinnermittlung} — keine EÜR"
        raise EuerError(msg)
    # das Jahr des WJ-Beginns bestimmt den Vordruck (beim Kalenderjahr dasselbe)
    gesucht = susa.wirtschaftsjahr.von.year
    vordruck_jahr, v = _vordruck(gesucht)
    euer = Euer(
        susa.jahr,
        vordruck_jahr,
        v["quelle"],
        summe_einnahmen_zeile=v["summe_einnahmen"][0],
        summe_ausgaben_zeile=v["summe_ausgaben"][0],
        gewinn_zeilen=(v["gewinn"][0], v["gewinn"][1]),
        entnahmen_zeile=v["entnahmen"][0],
        einlagen_zeile=v["einlagen"][0],
    )
    if vordruck_jahr != gesucht:
        euer.hinweise.append(
            f"Für {gesucht} ist kein Vordruck hinterlegt — Zeilen nach dem "
            f"Vordruck {vordruck_jahr}"
        )
    zeilen: dict[tuple[str, str], EuerZeile] = {}

    def buche(gruppe: str, kz: str | None, konto: str, betrag: Decimal) -> None:
        if betrag == 0:
            return
        if gruppe == "ausserhalb":
            z = zeilen.setdefault(
                ("ausserhalb", NICHT_IN_EUER), EuerZeile(None, None, AUSSERHALB_TEXT)
            )
        elif kz is not None and kz in v.get(gruppe, {}):
            nr, text = v[gruppe][kz]
            z = zeilen.setdefault((gruppe, kz), EuerZeile(kz, nr, text))
        else:
            seite = "Einnahmen" if gruppe == "einnahmen" else "Ausgaben"
            z = zeilen.setdefault(
                ("nicht_zugeordnet", seite), EuerZeile(None, None, seite)
            )
        z.konten[konto] = z.konten.get(konto, NULL) + betrag

    entnahmen_einlagen: dict[str, Decimal] = defaultdict(lambda: NULL)
    for z in susa.zeilen:
        if z.art is Kontenart.PRIVAT:
            entnahmen_einlagen["entnahmen" if z.saldo > 0 else "einlagen"] += abs(
                z.saldo
            )
            continue
        if z.art is not Kontenart.ERFOLG or (z.saldo == 0 and z.soll == 0):
            continue
        soll = z.soll + max(z.eb, NULL)
        haben = z.haben + max(-z.eb, NULL)
        kz_soll = kr.euer_kz(z.konto, Decimal(1))
        kz_haben = kr.euer_kz(z.konto, Decimal(-1))
        if kz_soll != kz_haben:
            # Konten mit Richtung (USt-Vorauszahlungen): Soll- und Habenverkehr getrennt
            buche(_gruppe(v, kz_soll, ausgabe=True), kz_soll, z.konto, soll)
            gruppe = _gruppe(v, kz_haben, ausgabe=False)
            buche(gruppe, kz_haben, z.konto, haben if gruppe == "einnahmen" else -haben)
            continue
        kz = kz_soll
        gruppe = _gruppe(v, kz, ausgabe=z.saldo > 0)
        betrag = -z.saldo if gruppe == "einnahmen" else z.saldo
        buche(gruppe, kz, z.konto, betrag)

    for (gruppe, _), zeile in sorted(
        zeilen.items(), key=lambda e: (e[1].zeile or 999, e[1].kz or "")
    ):
        getattr(euer, gruppe).append(zeile)
    euer.entnahmen = entnahmen_einlagen["entnahmen"]
    euer.einlagen = entnahmen_einlagen["einlagen"]
    euer.hinweise += _konten_hinweise(euer, kr)
    wj = susa.wirtschaftsjahr
    if wj.abweichend:
        euer.hinweise.append(_paragraf_4a(euer.gewinn, wj))
    return euer


def verteilung_4a(
    gewinn: Decimal, wj: Wirtschaftsjahr
) -> list[tuple[int, Decimal, str]]:
    """Zeitanteilige Verteilung des Gewinns eines abweichenden Wirtschaftsjahres auf
    die beiden Kalenderjahre (§ 4a Abs. 2 Nr. 1 EStG): (Kalenderjahr, Anteil,
    Zeitanteil) — nach Monaten, bei einem Beginn nicht am Monatsersten nach Tagen."""
    if not wj.abweichend:
        return [(wj.jahr, gewinn, "12 Monate")]
    if wj.von.day == 1:
        erst, gesamt, einheit = 12 - wj.von.month + 1, 12, "Monate"
    else:
        erst = (date(wj.von.year, 12, 31) - wj.von).days + 1
        gesamt, einheit = (wj.bis - wj.von).days + 1, "Tage"
    anteil = runde(gewinn * erst / gesamt)
    return [
        (wj.von.year, anteil, f"{erst} {einheit}"),
        (wj.bis.year, gewinn - anteil, f"{gesamt - erst} {einheit}"),
    ]


def _paragraf_4a(gewinn: Decimal, wj: Wirtschaftsjahr) -> str:
    teile = ", ".join(
        f"{jahr}: {betrag_de(anteil)} € ({zeit})"
        for jahr, anteil, zeit in verteilung_4a(gewinn, wj)
    )
    return (
        f"Abweichendes Wirtschaftsjahr {wj.bezeichnung} ({wj.zeitraum}): Land- und "
        "Forstwirte verteilen den Gewinn zeitanteilig auf die Kalenderjahre (§ 4a "
        f"Abs. 2 Nr. 1 EStG, ohne Veräußerungsgewinne) — {teile}; bei im "
        "Handelsregister eingetragenen Gewerbetreibenden gilt er im Kalenderjahr "
        f"{wj.bis.year} als bezogen (Nr. 2). accounti trägt die Verteilung in keinen "
        "Vordruck ein — mit dem Steuerberater abstimmen"
    )


def _kontenliste(konten: list[str]) -> str:
    """„Konto 4870“ bzw. „Konten 4870, 4875“."""
    return ("Konto " if len(konten) == 1 else "Konten ") + ", ".join(konten)


def _konten_hinweise(euer: Euer, kr: Kontenrahmen) -> list[str]:
    """Konten ohne Zeile — mit dem Hinweis ihrer Regel, sonst „Zuordnung prüfen“ —
    und Konten mit Zeile oder außerhalb der EÜR, deren Regel einen Hinweis trägt."""
    ohne_zeile = {k for z in euer.nicht_zugeordnet for k in z.konten}
    mit_zeile = [*euer.einnahmen, *euer.ausgaben, *euer.nicht_abziehbar]
    gebucht = ohne_zeile | {k for z in mit_zeile + euer.ausserhalb for k in z.konten}
    gruppen: dict[tuple[bool, str | None], list[str]] = defaultdict(list)
    for konto in sorted(gebucht):
        hinweis = kr.euer_hinweis(konto)
        if konto in ohne_zeile or hinweis:
            gruppen[(konto not in ohne_zeile, hinweis)].append(konto)
    texte = []
    for (hat_zeile, hinweis), konten in sorted(
        gruppen.items(), key=lambda g: (g[0][0], g[0][1] is not None, g[1])
    ):
        if hat_zeile:
            texte.append(f"{_kontenliste(konten)}: {hinweis}")
        elif hinweis:
            texte.append(
                f"Konten ohne Zeile der Anlage EÜR: {', '.join(konten)} — in den "
                f"Summen enthalten. {hinweis}"
            )
        else:
            texte.append(
                f"Konten ohne Zeile der Anlage EÜR: {', '.join(konten)} — in den "
                "Summen enthalten, Zuordnung prüfen"
            )
    return texte


def _gruppe(v: dict[str, Any], kz: str | None, ausgabe: bool) -> str:
    """Einnahme-, Ausgabe-, nicht-abziehbar- oder Außerhalb-Gruppe der Kennzahl."""
    if kz == NICHT_IN_EUER:
        return "ausserhalb"
    for gruppe in ("einnahmen", "ausgaben", "nicht_abziehbar"):
        if kz is not None and kz in v.get(gruppe, {}):
            return gruppe
    return "ausgaben" if ausgabe else "einnahmen"


def euer_csv(euer: Euer) -> str:
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\n")
    w.writerow(["Zeile", "Kennzahl", "Bezeichnung", "Betrag", "Konten"])

    def zahl(wert: Decimal) -> str:
        return betrag_de(wert).replace(".", "")

    def zeile(z: EuerZeile, text: str | None = None) -> None:
        konten = ", ".join(f"{k} {zahl(b)}" for k, b in sorted(z.konten.items()))
        w.writerow([z.zeile or "", z.kz or "", text or z.text, zahl(z.betrag), konten])

    for z in euer.einnahmen:
        zeile(z)
    for z in euer.nicht_zugeordnet:
        if z.text == "Einnahmen":
            zeile(z, "Nicht zugeordnete Einnahmen")
    w.writerow(
        [
            euer.summe_einnahmen_zeile,
            "159",
            "Summe Betriebseinnahmen",
            zahl(euer.summe_einnahmen),
            "",
        ]
    )
    for z in euer.ausgaben:
        zeile(z)
    for z in euer.nicht_zugeordnet:
        if z.text == "Ausgaben":
            zeile(z, "Nicht zugeordnete Ausgaben")
    for z in euer.nicht_abziehbar:
        zeile(z)
    w.writerow(
        [
            euer.summe_ausgaben_zeile,
            "199",
            "Summe Betriebsausgaben",
            zahl(euer.summe_ausgaben),
            "",
        ]
    )
    w.writerow(
        [
            "/".join(str(n) for n in euer.gewinn_zeilen),
            "",
            "Gewinn (Betriebseinnahmen − Betriebsausgaben)",
            zahl(euer.gewinn),
            "",
        ]
    )
    for z in euer.ausserhalb:
        zeile(z)
    w.writerow([euer.entnahmen_zeile, "122", "Entnahmen", zahl(euer.entnahmen), ""])
    w.writerow([euer.einlagen_zeile, "123", "Einlagen", zahl(euer.einlagen), ""])
    return puffer.getvalue()
