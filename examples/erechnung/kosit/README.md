# Offizielle XRechnung-Beispiele (KoSIT)

Auswahl aus der **XRechnung-Testsuite 3.0.2**, Release `v2026-08-31`
(<https://github.com/itplr-kosit/xrechnung-testsuite>), © Koordinierungsstelle für
IT-Standards (KoSIT), lizenziert unter der Apache License 2.0. Die Dateien sind
unverändert übernommen.

Sie dienen als Regressionstest: Jede dieser gültigen Rechnungen muss sich ohne Fehler-Befund
lesen lassen (`tests/test_erechnung_kosit.py`).

| Datei | Warum ausgewählt |
|-------|------------------|
| `01.01a-INVOICE_ubl.xml`, `01.01a-INVOICE_uncefact.xml` | Standardfall in beiden Syntaxen |
| `01.04a-INVOICE_*.xml` | Kategorie O (nicht steuerbar) ohne Steuersatz, Steuernummer statt USt-IdNr. |
| `02.01a-INVOICE_*.xml` | Steuerbefreiung nur mit Befreiungscode (BT-121) |
| `05.01a-INVOICE_ubl.xml` | Extension-Profil mit Drittzahlungen (Zahlbetrag ≠ EN-16931-Formel) |
