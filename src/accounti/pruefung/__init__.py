"""Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7).

Die Mechanik hinter den GoBD-Grundsätzen: Prüfregeln liefern Befunde und ändern nie
Daten (``regeln/``), fehlende Belege werden als Aufgabe nachgefordert
(``nachforderung``), jede buchungsrelevante Änderung steht im hash-verketteten
Journal (``journal``, ``ereignisse``), freigegebene Buchungen werden nur per Storno
korrigiert (``storno``), festgeschriebene Monate nehmen keine Buchung mehr an
(``perioden``), und die Verfahrensdokumentation entsteht aus dem Systemzustand
(``verfahrensdoku``).
"""
