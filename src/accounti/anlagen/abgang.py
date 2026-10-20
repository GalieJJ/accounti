"""Anlagenabgang — Verkauf, Entnahme oder Verschrottung.

Bis einschließlich des Abgangsmonats läuft die AfA weiter (R 7.4 Abs. 8 EStR,
monatsweise); der Restbuchwert geht auf „Anlagenabgänge Sachanlagen“ — bei Buchgewinn
auf das eine, bei Buchverlust auf das andere Konto (DATEV SKR03 2026: 2315/2310). Ein
Erlös wird mit Gegenkonto als Vorschlag gebucht, die Umsatzsteuer kommt aus
``accounti.steuer``. Ein Gut im Sammelposten mindert diesen nicht (§ 6 Abs. 2a Satz 3
EStG) — außer es scheidet noch im Anschaffungsjahr aus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.anlagen.afa import plane, sammelposten_mitglieder
from accounti.anlagen.konfiguration import AnlagenEinstellungen
from accounti.anlagen.lauf import AfaLaufErgebnis, afa_lauf
from accounti.anlagen.rechtsstand import Rechtsstand
from accounti.anzeige import betrag_de
from accounti.db.repo_anlagen import aktualisiere_anlage, lade_anlage
from accounti.db.repository import speichere_buchung
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.anlagen import AbgangArt, AfaArt, Anlagegut
from accounti.steuer.umsatzsteuer import UStBerechner

NULL = Decimal("0")


class AbgangError(ValueError):
    """Der Abgang ist so nicht möglich."""


@dataclass
class Abgangsergebnis:
    anlage: Anlagegut
    afa: AfaLaufErgebnis
    restbuchwert: Decimal
    erloes: Decimal
    buchungen: list[Buchungssatz] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def ergebnis(self) -> Decimal:
        """Erlös minus Restbuchwert: positiv Buchgewinn, negativ Buchverlust."""
        return self.erloes - self.restbuchwert


def buche_abgang(
    session: Session,
    schluessel: str,
    datum: date,
    einstellungen: AnlagenEinstellungen,
    art: AbgangArt = AbgangArt.VERKAUF,
    erloes: Decimal | None = None,
    gegenkonto: str | None = None,
    mit_ust: bool = True,
    rechtsstand: Rechtsstand | None = None,
) -> Abgangsergebnis:
    rs = rechtsstand or einstellungen.rechtsstand()
    anlage = lade_anlage(session, schluessel)
    if anlage.abgang_datum is not None:
        msg = f"Anlagegut {anlage.nr}: Abgang schon am {anlage.abgang_datum:%d.%m.%Y}"
        raise AbgangError(msg)
    if datum < anlage.anschaffungsdatum:
        raise AbgangError(f"Abgang am {datum:%d.%m.%Y} liegt vor der Anschaffung")
    if erloes is not None and erloes > 0 and not gegenkonto:
        raise AbgangError("Für den Erlös fehlt das Gegenkonto (z.B. 1200 oder 1400)")

    anlage = anlage.model_copy(
        update={"abgang_datum": datum, "abgang_art": art, "abgang_erloes": erloes}
    )
    aktualisiere_anlage(session, anlage)
    # AfA bis einschließlich Abgangsmonat (bucht nach oder korrigiert)
    afa = afa_lauf(session, datum.year, einstellungen, datum.month, {anlage.id}, rs)

    im_sammelposten = anlage.afa_art is AfaArt.SAMMELPOSTEN and bool(
        sammelposten_mitglieder(anlage.konto, anlage.anschaffungsdatum.year, [anlage])
    )
    rbw = (
        NULL
        if im_sammelposten
        else plane(anlage, rs).restbuchwert(datum.year, datum.month)
    )
    ergebnis = Abgangsergebnis(anlage, afa, rbw, erloes or NULL)
    text = f"Abgang {anlage.bezeichnung} (Nr. {anlage.nr})"
    if im_sammelposten:
        ergebnis.hinweise.append(
            "Gut im Sammelposten: der Sammelposten wird nicht gemindert "
            "(§ 6 Abs. 2a Satz 3 EStG), der Erlös ist voll Ertrag"
        )
    konten = einstellungen.konten
    gewinn = ergebnis.ergebnis >= 0
    if rbw > 0:
        rbw_buchung = Buchungssatz(
            datum=datum,
            soll_konto=konten.abgang_buchgewinn
            if gewinn
            else konten.abgang_buchverlust,
            haben_konto=anlage.konto,
            betrag_netto=rbw,
            buchungstext=f"RBW {text}"[:60],
            beleg_nummer=f"ANL-{anlage.nr}",
            status=BuchungStatus.ZUR_PRUEFUNG,
            confidence=1.0,
        )
        speichere_buchung(session, rbw_buchung)
        ergebnis.buchungen.append(rbw_buchung)
    if erloes is not None and erloes > 0 and gegenkonto:
        if mit_ust:
            # Inland, Regelsteuersatz — Steuerlogik aus accounti.steuer
            position = UStBerechner().berechne_ust(erloes)
            konto = konten.erloes_buchgewinn if gewinn else konten.erloes_buchverlust
            schluessel_bu, steuer = position.datev_schluessel, position.steuerbetrag
        else:
            konto = (
                konten.erloes_buchgewinn_ohne_ust
                if gewinn
                else konten.erloes_buchverlust_ohne_ust
            )
            schluessel_bu, steuer = None, None
        erloes_buchung = Buchungssatz(
            datum=datum,
            soll_konto=gegenkonto,
            haben_konto=konto,
            betrag_netto=erloes,
            steuer_schluessel=schluessel_bu,
            steuer_betrag=steuer,
            buchungstext=f"Erlös {text}"[:60],
            beleg_nummer=f"ANL-{anlage.nr}",
            status=BuchungStatus.ZUR_PRUEFUNG,
            confidence=1.0,
        )
        speichere_buchung(session, erloes_buchung)
        ergebnis.buchungen.append(erloes_buchung)
    ergebnis.hinweise.append(
        f"Restbuchwert {betrag_de(rbw)}, Erlös {betrag_de(ergebnis.erloes)}, "
        f"{'Buchgewinn' if gewinn else 'Buchverlust'} "
        f"{betrag_de(abs(ergebnis.ergebnis))}"
    )
    session.flush()
    return ergebnis
