"""accounti.integrationen — Marktplatz-Abrechnungen buchen und mit der Bank abgleichen.

Die Formate lesen die Importer in ``accounti.importers`` (amazon, ebay, paypal,
shopify); hier passiert die Buchhaltung: Summenprobe, Buchung gegen das
Verrechnungskonto, Steuer je Bestimmungsland über ``accounti.steuer``,
Auszahlungsabgleich und die OSS-Quartalsmeldung.
"""
