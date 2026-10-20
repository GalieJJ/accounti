"""Test-Doppel für die echte Abgabe.

Die Attrappe aus ``elster.uebermittlung`` gibt nie etwas ab und darf deshalb auch
keinen Lauf im Modus „echt“ erzeugen. Für Tests des Abgabewegs (Freigabe, Protokoll,
Zahllast, Berichtigung) meldet sich dieses Doppel als ERiC — es spricht trotzdem kein
Netz an (Spec 6: „Übermittlung ausschließlich gemockt“).
"""

from accounti.elster.uebermittlung import AttrappenUebermittler


class EricDoppel(AttrappenUebermittler):
    weg = "eric"


def als_eric(monkeypatch, doppel=None):
    """Die CLI wählt statt der konfigurierten Attrappe das ERiC-Doppel."""
    import accounti.elster.uebermittlung as uebermittlung

    doppel = doppel or EricDoppel()
    monkeypatch.setattr(
        uebermittlung,
        "waehle_uebermittler",
        lambda einstellungen, umgebung=None: (doppel, "ERiC-Doppel im Test"),
    )
    return doppel
