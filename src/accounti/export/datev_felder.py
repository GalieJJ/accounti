"""Feldlisten des DATEV-Formats (EXTF) — wörtlich aus DATEVs eigenen Unterlagen.

Spaltenüberschriften: Zeile 2 der DATEV-Musterdateien (``EXTF_DebKred_Stamm.csv`` vom
27.03.2024, ``EXTF_Buchungsstapel.csv`` vom 18.06.2025; DATEV Developer Portal,
„DATEV-Format“, Musterdaten). Feldtyp, Länge und Nachkommastellen: Formatbeschreibung
des DATEV-Format-Prüfprogramms 2.2.3.0 (``Format_Debitoren_Kreditoren.xml`` Version 5,
``Format_Buchungsstapel.xml`` Version 13, Stand 21.10.2025). Abgerufen am 20.10.2026.

Typen: ``T`` Text (in Anführungszeichen), ``Z`` Zahl, ``B`` Betrag, ``D`` Datum,
``K`` Konto. DATEV liest die Felder nach ihrer Position.
"""

from __future__ import annotations

from typing import NamedTuple


class Feld(NamedTuple):
    name: str  # Spaltenüberschrift
    typ: str  # T, Z, B, D, K
    laenge: int  # Höchstlänge (Text) bzw. Stellen vor dem Komma
    nachkomma: int = 0


# Debitoren/Kreditoren, Formatkategorie 16, Formatversion 5 — 254 Felder
DEBITOREN_KREDITOREN: tuple[Feld, ...] = (
    Feld("Konto", "K", 9, 0),  # 1
    Feld("Name (Adressattyp Unternehmen)", "T", 50, 0),  # 2
    Feld("Unternehmensgegenstand", "T", 50, 0),  # 3
    Feld("Name (Adressattyp natürl. Person)", "T", 30, 0),  # 4
    Feld("Vorname (Adressattyp natürl. Person)", "T", 30, 0),  # 5
    Feld("Name (Adressattyp keine Angabe)", "T", 50, 0),  # 6
    Feld("Adressattyp", "T", 1, 0),  # 7
    Feld("Kurzbezeichnung", "T", 15, 0),  # 8
    Feld("EU-Land", "T", 2, 0),  # 9
    Feld("EU-UStID", "T", 13, 0),  # 10
    Feld("Anrede", "T", 30, 0),  # 11
    Feld("Titel/Akad. Grad", "T", 25, 0),  # 12
    Feld("Adelstitel", "T", 15, 0),  # 13
    Feld("Namensvorsatz", "T", 14, 0),  # 14
    Feld("Adressart", "T", 3, 0),  # 15
    Feld("Straße", "T", 36, 0),  # 16
    Feld("Postfach", "T", 10, 0),  # 17
    Feld("Postleitzahl", "T", 10, 0),  # 18
    Feld("Ort", "T", 30, 0),  # 19
    Feld("Land", "T", 2, 0),  # 20
    Feld("Versandzusatz", "T", 50, 0),  # 21
    Feld("Adresszusatz", "T", 36, 0),  # 22
    Feld("Abweichende Anrede", "T", 30, 0),  # 23
    Feld("Abw. Zustellbezeichnung 1", "T", 50, 0),  # 24
    Feld("Abw. Zustellbezeichnung 2", "T", 36, 0),  # 25
    Feld("Kennz. Korrespondenzadresse", "Z", 1, 0),  # 26
    Feld("Adresse Gültig von", "D", 8, 0),  # 27
    Feld("Adresse Gültig bis", "D", 8, 0),  # 28
    Feld("Telefon", "T", 60, 0),  # 29
    Feld("Bemerkung (Telefon)", "T", 40, 0),  # 30
    Feld("Telefon GL", "T", 60, 0),  # 31
    Feld("Bemerkung (Telefon GL)", "T", 40, 0),  # 32
    Feld("E-Mail", "T", 60, 0),  # 33
    Feld("Bemerkung (E-Mail)", "T", 40, 0),  # 34
    Feld("Internet", "T", 60, 0),  # 35
    Feld("Bemerkung (Internet)", "T", 40, 0),  # 36
    Feld("Fax", "T", 60, 0),  # 37
    Feld("Bemerkung (Fax)", "T", 40, 0),  # 38
    Feld("Sonstige", "T", 60, 0),  # 39
    Feld("Bemerkung (Sonstige)", "T", 40, 0),  # 40
    Feld("Bankleitzahl 1", "T", 8, 0),  # 41
    Feld("Bankbezeichnung 1", "T", 30, 0),  # 42
    Feld("Bank-Kontonummer 1", "T", 10, 0),  # 43
    Feld("Länderkennzeichen 1", "T", 2, 0),  # 44
    Feld("IBAN-Nr. 1", "T", 34, 0),  # 45
    Feld("Leerfeld", "T", 1, 0),  # 46
    Feld("SWIFT-Code 1", "T", 11, 0),  # 47
    Feld("Abw. Kontoinhaber 1", "T", 70, 0),  # 48
    Feld("Kennz. Hauptbankverb. 1", "T", 1, 0),  # 49
    Feld("Bankverb 1 Gültig von", "D", 8, 0),  # 50
    Feld("Bankverb 1 Gültig bis", "D", 8, 0),  # 51
    Feld("Bankleitzahl 2", "T", 8, 0),  # 52
    Feld("Bankbezeichnung 2", "T", 30, 0),  # 53
    Feld("Bank-Kontonummer 2", "T", 10, 0),  # 54
    Feld("Länderkennzeichen 2", "T", 2, 0),  # 55
    Feld("IBAN-Nr. 2", "T", 34, 0),  # 56
    Feld("Leerfeld", "T", 1, 0),  # 57
    Feld("SWIFT-Code 2", "T", 11, 0),  # 58
    Feld("Abw. Kontoinhaber 2", "T", 70, 0),  # 59
    Feld("Kennz. Hauptbankverb. 2", "T", 1, 0),  # 60
    Feld("Bankverb 2 Gültig von", "D", 8, 0),  # 61
    Feld("Bankverb 2 Gültig bis", "D", 8, 0),  # 62
    Feld("Bankleitzahl 3", "T", 8, 0),  # 63
    Feld("Bankbezeichnung 3", "T", 30, 0),  # 64
    Feld("Bank-Kontonummer 3", "T", 10, 0),  # 65
    Feld("Länderkennzeichen 3", "T", 2, 0),  # 66
    Feld("IBAN-Nr. 3", "T", 34, 0),  # 67
    Feld("Leerfeld", "T", 1, 0),  # 68
    Feld("SWIFT-Code 3", "T", 11, 0),  # 69
    Feld("Abw. Kontoinhaber 3", "T", 70, 0),  # 70
    Feld("Kennz. Hauptbankverb. 3", "T", 1, 0),  # 71
    Feld("Bankverb 3 Gültig von", "D", 8, 0),  # 72
    Feld("Bankverb 3 Gültig bis", "D", 8, 0),  # 73
    Feld("Bankleitzahl 4", "T", 8, 0),  # 74
    Feld("Bankbezeichnung 4", "T", 30, 0),  # 75
    Feld("Bank-Kontonummer 4", "T", 10, 0),  # 76
    Feld("Länderkennzeichen 4", "T", 2, 0),  # 77
    Feld("IBAN-Nr. 4", "T", 34, 0),  # 78
    Feld("Leerfeld", "T", 1, 0),  # 79
    Feld("SWIFT-Code 4", "T", 11, 0),  # 80
    Feld("Abw. Kontoinhaber 4", "T", 70, 0),  # 81
    Feld("Kennz. Hauptbankverb. 4", "T", 1, 0),  # 82
    Feld("Bankverb 4 Gültig von", "D", 8, 0),  # 83
    Feld("Bankverb 4 Gültig bis", "D", 8, 0),  # 84
    Feld("Bankleitzahl 5", "T", 8, 0),  # 85
    Feld("Bankbezeichnung 5", "T", 30, 0),  # 86
    Feld("Bank-Kontonummer 5", "T", 10, 0),  # 87
    Feld("Länderkennzeichen 5", "T", 2, 0),  # 88
    Feld("IBAN-Nr. 5", "T", 34, 0),  # 89
    Feld("Leerfeld", "T", 1, 0),  # 90
    Feld("SWIFT-Code 5", "T", 11, 0),  # 91
    Feld("Abw. Kontoinhaber 5", "T", 70, 0),  # 92
    Feld("Kennz. Hauptbankverb. 5", "T", 1, 0),  # 93
    Feld("Bankverb 5 Gültig von", "D", 8, 0),  # 94
    Feld("Bankverb 5 Gültig bis", "D", 8, 0),  # 95
    Feld("Leerfeld", "T", 1, 0),  # 96
    Feld("Briefanrede", "T", 100, 0),  # 97
    Feld("Grußformel", "T", 50, 0),  # 98
    Feld("Kunden-/Lief.-Nr.", "T", 15, 0),  # 99
    Feld("Steuernummer", "T", 20, 0),  # 100
    Feld("Sprache", "Z", 2, 0),  # 101
    Feld("Ansprechpartner", "T", 40, 0),  # 102
    Feld("Vertreter", "T", 40, 0),  # 103
    Feld("Sachbearbeiter", "T", 40, 0),  # 104
    Feld("Diverse-Konto", "Z", 1, 0),  # 105
    Feld("Ausgabeziel", "Z", 1, 0),  # 106
    Feld("Währungssteuerung", "T", 1, 0),  # 107
    Feld("Kreditlimit (Debitor)", "B", 10, 0),  # 108
    Feld("Zahlungsbedingung", "Z", 3, 0),  # 109
    Feld("Fälligkeit in Tagen (Debitor)", "Z", 3, 0),  # 110
    Feld("Skonto in Prozent (Debitor)", "Z", 2, 2),  # 111
    Feld("Kreditoren-Ziel 1 Tg.", "Z", 2, 0),  # 112
    Feld("Kreditoren-Skonto 1 %", "Z", 2, 2),  # 113
    Feld("Kreditoren-Ziel 2 Tg.", "Z", 2, 0),  # 114
    Feld("Kreditoren-Skonto 2 %", "Z", 2, 2),  # 115
    Feld("Kreditoren-Ziel 3 Brutto Tg.", "Z", 3, 0),  # 116
    Feld("Kreditoren-Ziel 4 Tg.", "Z", 2, 0),  # 117
    Feld("Kreditoren-Skonto 4 %", "Z", 2, 2),  # 118
    Feld("Kreditoren-Ziel 5 Tg.", "Z", 2, 0),  # 119
    Feld("Kreditoren-Skonto 5 %", "Z", 2, 2),  # 120
    Feld("Mahnung", "Z", 1, 0),  # 121
    Feld("Kontoauszug", "Z", 1, 0),  # 122
    Feld("Mahntext 1", "Z", 1, 0),  # 123
    Feld("Mahntext 2", "Z", 1, 0),  # 124
    Feld("Mahntext 3", "Z", 1, 0),  # 125
    Feld("Kontoauszugstext", "Z", 1, 0),  # 126
    Feld("Mahnlimit Betrag", "B", 5, 2),  # 127
    Feld("Mahnlimit %", "Z", 2, 2),  # 128
    Feld("Zinsberechnung", "Z", 1, 0),  # 129
    Feld("Mahnzinssatz 1", "Z", 2, 2),  # 130
    Feld("Mahnzinssatz 2", "Z", 2, 2),  # 131
    Feld("Mahnzinssatz 3", "Z", 2, 2),  # 132
    Feld("Lastschrift", "T", 1, 0),  # 133
    Feld("Leerfeld", "T", 1, 0),  # 134
    Feld("Mandantenbank", "Z", 4, 0),  # 135
    Feld("Zahlungsträger", "T", 1, 0),  # 136
    Feld("Indiv. Feld 1", "T", 40, 0),  # 137
    Feld("Indiv. Feld 2", "T", 40, 0),  # 138
    Feld("Indiv. Feld 3", "T", 40, 0),  # 139
    Feld("Indiv. Feld 4", "T", 40, 0),  # 140
    Feld("Indiv. Feld 5", "T", 40, 0),  # 141
    Feld("Indiv. Feld 6", "T", 40, 0),  # 142
    Feld("Indiv. Feld 7", "T", 40, 0),  # 143
    Feld("Indiv. Feld 8", "T", 40, 0),  # 144
    Feld("Indiv. Feld 9", "T", 40, 0),  # 145
    Feld("Indiv. Feld 10", "T", 40, 0),  # 146
    Feld("Indiv. Feld 11", "T", 40, 0),  # 147
    Feld("Indiv. Feld 12", "T", 40, 0),  # 148
    Feld("Indiv. Feld 13", "T", 40, 0),  # 149
    Feld("Indiv. Feld 14", "T", 40, 0),  # 150
    Feld("Indiv. Feld 15", "T", 40, 0),  # 151
    Feld("Abweichende Anrede (Rechnungsadresse)", "T", 30, 0),  # 152
    Feld("Adressart (Rechnungsadresse)", "T", 3, 0),  # 153
    Feld("Straße (Rechnungsadresse)", "T", 36, 0),  # 154
    Feld("Postfach (Rechnungsadresse)", "T", 10, 0),  # 155
    Feld("Postleitzahl (Rechnungsadresse)", "T", 10, 0),  # 156
    Feld("Ort (Rechnungsadresse)", "T", 30, 0),  # 157
    Feld("Land (Rechnungsadresse)", "T", 2, 0),  # 158
    Feld("Versandzusatz (Rechnungsadresse)", "T", 50, 0),  # 159
    Feld("Adresszusatz (Rechnungsadresse)", "T", 36, 0),  # 160
    Feld("Abw. Zustellbezeichnung 1 (Rechnungsadresse)", "T", 50, 0),  # 161
    Feld("Abw. Zustellbezeichnung 2 (Rechnungsadresse)", "T", 36, 0),  # 162
    Feld("Adresse Gültig von (Rechnungsadresse)", "D", 8, 0),  # 163
    Feld("Adresse Gültig bis (Rechnungsadresse)", "D", 8, 0),  # 164
    Feld("Bankleitzahl 6", "T", 8, 0),  # 165
    Feld("Bankbezeichnung 6", "T", 30, 0),  # 166
    Feld("Bank-Kontonummer 6", "T", 10, 0),  # 167
    Feld("Länderkennzeichen 6", "T", 2, 0),  # 168
    Feld("IBAN-Nr. 6", "T", 34, 0),  # 169
    Feld("Leerfeld", "T", 1, 0),  # 170
    Feld("SWIFT-Code 6", "T", 11, 0),  # 171
    Feld("Abw. Kontoinhaber 6", "T", 70, 0),  # 172
    Feld("Kennz. Hauptbankverb. 6", "T", 1, 0),  # 173
    Feld("Bankverb 6 Gültig von", "D", 8, 0),  # 174
    Feld("Bankverb 6 Gültig bis", "D", 8, 0),  # 175
    Feld("Bankleitzahl 7", "T", 8, 0),  # 176
    Feld("Bankbezeichnung 7", "T", 30, 0),  # 177
    Feld("Bank-Kontonummer 7", "T", 10, 0),  # 178
    Feld("Länderkennzeichen 7", "T", 2, 0),  # 179
    Feld("IBAN-Nr. 7", "T", 34, 0),  # 180
    Feld("Leerfeld", "T", 1, 0),  # 181
    Feld("SWIFT-Code 7", "T", 11, 0),  # 182
    Feld("Abw. Kontoinhaber 7", "T", 70, 0),  # 183
    Feld("Kennz. Hauptbankverb. 7", "T", 1, 0),  # 184
    Feld("Bankverb 7 Gültig von", "D", 8, 0),  # 185
    Feld("Bankverb 7 Gültig bis", "D", 8, 0),  # 186
    Feld("Bankleitzahl 8", "T", 8, 0),  # 187
    Feld("Bankbezeichnung 8", "T", 30, 0),  # 188
    Feld("Bank-Kontonummer 8", "T", 10, 0),  # 189
    Feld("Länderkennzeichen 8", "T", 2, 0),  # 190
    Feld("IBAN-Nr. 8", "T", 34, 0),  # 191
    Feld("Leerfeld", "T", 1, 0),  # 192
    Feld("SWIFT-Code 8", "T", 11, 0),  # 193
    Feld("Abw. Kontoinhaber 8", "T", 70, 0),  # 194
    Feld("Kennz. Hauptbankverb. 8", "T", 1, 0),  # 195
    Feld("Bankverb 8 Gültig von", "D", 8, 0),  # 196
    Feld("Bankverb 8 Gültig bis", "D", 8, 0),  # 197
    Feld("Bankleitzahl 9", "T", 8, 0),  # 198
    Feld("Bankbezeichnung 9", "T", 30, 0),  # 199
    Feld("Bank-Kontonummer 9", "T", 10, 0),  # 200
    Feld("Länderkennzeichen 9", "T", 2, 0),  # 201
    Feld("IBAN-Nr. 9", "T", 34, 0),  # 202
    Feld("Leerfeld", "T", 1, 0),  # 203
    Feld("SWIFT-Code 9", "T", 11, 0),  # 204
    Feld("Abw. Kontoinhaber 9", "T", 70, 0),  # 205
    Feld("Kennz. Hauptbankverb. 9", "T", 1, 0),  # 206
    Feld("Bankverb 9 Gültig von", "D", 8, 0),  # 207
    Feld("Bankverb 9 Gültig bis", "D", 8, 0),  # 208
    Feld("Bankleitzahl 10", "T", 8, 0),  # 209
    Feld("Bankbezeichnung 10", "T", 30, 0),  # 210
    Feld("Bank-Kontonummer 10", "T", 10, 0),  # 211
    Feld("Länderkennzeichen 10", "T", 2, 0),  # 212
    Feld("IBAN-Nr. 10", "T", 34, 0),  # 213
    Feld("Leerfeld", "T", 1, 0),  # 214
    Feld("SWIFT-Code 10", "T", 11, 0),  # 215
    Feld("Abw. Kontoinhaber 10", "T", 70, 0),  # 216
    Feld("Kennz. Hauptbankverb. 10", "T", 1, 0),  # 217
    Feld("Bankverb 10 Gültig von", "D", 8, 0),  # 218
    Feld("Bankverb 10 Gültig bis", "D", 8, 0),  # 219
    Feld("Nummer Fremdsystem", "T", 15, 0),  # 220
    Feld("Insolvent", "Z", 1, 0),  # 221
    Feld("SEPA-Mandatsreferenz 1", "T", 35, 0),  # 222
    Feld("SEPA-Mandatsreferenz 2", "T", 35, 0),  # 223
    Feld("SEPA-Mandatsreferenz 3", "T", 35, 0),  # 224
    Feld("SEPA-Mandatsreferenz 4", "T", 35, 0),  # 225
    Feld("SEPA-Mandatsreferenz 5", "T", 35, 0),  # 226
    Feld("SEPA-Mandatsreferenz 6", "T", 35, 0),  # 227
    Feld("SEPA-Mandatsreferenz 7", "T", 35, 0),  # 228
    Feld("SEPA-Mandatsreferenz 8", "T", 35, 0),  # 229
    Feld("SEPA-Mandatsreferenz 9", "T", 35, 0),  # 230
    Feld("SEPA-Mandatsreferenz 10", "T", 35, 0),  # 231
    Feld("Verknüpftes OPOS-Konto", "K", 9, 0),  # 232
    Feld("Mahnsperre bis", "D", 8, 0),  # 233
    Feld("Lastschriftsperre bis", "D", 8, 0),  # 234
    Feld("Zahlungssperre bis", "D", 8, 0),  # 235
    Feld("Gebührenberechnung", "Z", 1, 0),  # 236
    Feld("Mahngebühr 1", "Z", 2, 2),  # 237
    Feld("Mahngebühr 2", "Z", 2, 2),  # 238
    Feld("Mahngebühr 3", "Z", 2, 2),  # 239
    Feld("Pauschalenberechnung", "Z", 1, 0),  # 240
    Feld("Verzugspauschale 1", "Z", 3, 2),  # 241
    Feld("Verzugspauschale 2", "Z", 3, 2),  # 242
    Feld("Verzugspauschale 3", "Z", 3, 2),  # 243
    Feld("Alternativer Suchname", "T", 50, 0),  # 244
    Feld("Status", "Z", 1, 0),  # 245
    Feld("Anschrift manuell geändert (Korrespondenzadresse)", "Z", 1, 0),  # 246
    Feld("Anschrift individuell (Korrespondenzadresse)", "T", 306, 0),  # 247
    Feld("Anschrift manuell geändert (Rechnungsadresse)", "Z", 1, 0),  # 248
    Feld("Anschrift individuell (Rechnungsadresse)", "T", 306, 0),  # 249
    Feld("Fristberechnung bei Debitor", "Z", 1, 0),  # 250
    Feld("Mahnfrist 1", "Z", 3, 0),  # 251
    Feld("Mahnfrist 2", "Z", 3, 0),  # 252
    Feld("Mahnfrist 3", "Z", 3, 0),  # 253
    Feld("Letzte Frist", "Z", 3, 0),  # 254
)

# Buchungsstapel, Formatkategorie 21, Formatversion 13 — 125 Felder
BUCHUNGSSTAPEL: tuple[Feld, ...] = (
    Feld("Umsatz (ohne Soll/Haben-Kz)", "B", 10, 2),  # 1
    Feld("Soll/Haben-Kennzeichen", "T", 1, 0),  # 2
    Feld("WKZ Umsatz", "T", 3, 0),  # 3
    Feld("Kurs", "Z", 5, 6),  # 4
    Feld("Basis-Umsatz", "B", 10, 2),  # 5
    Feld("WKZ Basis-Umsatz", "T", 3, 0),  # 6
    Feld("Konto", "K", 9, 0),  # 7
    Feld("Gegenkonto (ohne BU-Schlüssel)", "K", 9, 0),  # 8
    Feld("BU-Schlüssel", "T", 4, 0),  # 9
    Feld("Belegdatum", "D", 8, 0),  # 10
    Feld("Belegfeld 1", "T", 36, 0),  # 11
    Feld("Belegfeld 2", "T", 12, 0),  # 12
    Feld("Skonto", "B", 8, 2),  # 13
    Feld("Buchungstext", "T", 60, 0),  # 14
    Feld("Postensperre", "Z", 1, 0),  # 15
    Feld("Diverse Adressnummer", "T", 9, 0),  # 16
    Feld("Geschäftspartnerbank", "Z", 3, 0),  # 17
    Feld("Sachverhalt", "Z", 2, 0),  # 18
    Feld("Zinssperre", "Z", 1, 0),  # 19
    Feld("Beleglink", "T", 210, 0),  # 20
    Feld("Beleginfo - Art 1", "T", 20, 0),  # 21
    Feld("Beleginfo - Inhalt 1", "T", 210, 0),  # 22
    Feld("Beleginfo - Art 2", "T", 20, 0),  # 23
    Feld("Beleginfo - Inhalt 2", "T", 210, 0),  # 24
    Feld("Beleginfo - Art 3", "T", 20, 0),  # 25
    Feld("Beleginfo - Inhalt 3", "T", 210, 0),  # 26
    Feld("Beleginfo - Art 4", "T", 20, 0),  # 27
    Feld("Beleginfo - Inhalt 4", "T", 210, 0),  # 28
    Feld("Beleginfo - Art 5", "T", 20, 0),  # 29
    Feld("Beleginfo - Inhalt 5", "T", 210, 0),  # 30
    Feld("Beleginfo - Art 6", "T", 20, 0),  # 31
    Feld("Beleginfo - Inhalt 6", "T", 210, 0),  # 32
    Feld("Beleginfo - Art 7", "T", 20, 0),  # 33
    Feld("Beleginfo - Inhalt 7", "T", 210, 0),  # 34
    Feld("Beleginfo - Art 8", "T", 20, 0),  # 35
    Feld("Beleginfo - Inhalt 8", "T", 210, 0),  # 36
    Feld("KOST1 - Kostenstelle", "T", 36, 0),  # 37
    Feld("KOST2 - Kostenstelle", "T", 36, 0),  # 38
    Feld("Kost-Menge", "Z", 12, 4),  # 39
    Feld("EU-Land u. UStID (Bestimmung)", "T", 15, 0),  # 40
    Feld("EU-Steuersatz (Bestimmung)", "Z", 2, 2),  # 41
    Feld("Abw. Versteuerungsart", "T", 1, 0),  # 42
    Feld("Sachverhalt L+L", "Z", 3, 0),  # 43
    Feld("Funktionsergänzung L+L", "Z", 3, 0),  # 44
    Feld("BU 49 Hauptfunktionstyp", "Z", 1, 0),  # 45
    Feld("BU 49 Hauptfunktionsnummer", "Z", 2, 0),  # 46
    Feld("BU 49 Funktionsergänzung", "Z", 3, 0),  # 47
    Feld("Zusatzinformation - Art 1", "T", 20, 0),  # 48
    Feld("Zusatzinformation- Inhalt 1", "T", 210, 0),  # 49
    Feld("Zusatzinformation - Art 2", "T", 20, 0),  # 50
    Feld("Zusatzinformation- Inhalt 2", "T", 210, 0),  # 51
    Feld("Zusatzinformation - Art 3", "T", 20, 0),  # 52
    Feld("Zusatzinformation- Inhalt 3", "T", 210, 0),  # 53
    Feld("Zusatzinformation - Art 4", "T", 20, 0),  # 54
    Feld("Zusatzinformation- Inhalt 4", "T", 210, 0),  # 55
    Feld("Zusatzinformation - Art 5", "T", 20, 0),  # 56
    Feld("Zusatzinformation- Inhalt 5", "T", 210, 0),  # 57
    Feld("Zusatzinformation - Art 6", "T", 20, 0),  # 58
    Feld("Zusatzinformation- Inhalt 6", "T", 210, 0),  # 59
    Feld("Zusatzinformation - Art 7", "T", 20, 0),  # 60
    Feld("Zusatzinformation- Inhalt 7", "T", 210, 0),  # 61
    Feld("Zusatzinformation - Art 8", "T", 20, 0),  # 62
    Feld("Zusatzinformation- Inhalt 8", "T", 210, 0),  # 63
    Feld("Zusatzinformation - Art 9", "T", 20, 0),  # 64
    Feld("Zusatzinformation- Inhalt 9", "T", 210, 0),  # 65
    Feld("Zusatzinformation - Art 10", "T", 20, 0),  # 66
    Feld("Zusatzinformation- Inhalt 10", "T", 210, 0),  # 67
    Feld("Zusatzinformation - Art 11", "T", 20, 0),  # 68
    Feld("Zusatzinformation- Inhalt 11", "T", 210, 0),  # 69
    Feld("Zusatzinformation - Art 12", "T", 20, 0),  # 70
    Feld("Zusatzinformation- Inhalt 12", "T", 210, 0),  # 71
    Feld("Zusatzinformation - Art 13", "T", 20, 0),  # 72
    Feld("Zusatzinformation- Inhalt 13", "T", 210, 0),  # 73
    Feld("Zusatzinformation - Art 14", "T", 20, 0),  # 74
    Feld("Zusatzinformation- Inhalt 14", "T", 210, 0),  # 75
    Feld("Zusatzinformation - Art 15", "T", 20, 0),  # 76
    Feld("Zusatzinformation- Inhalt 15", "T", 210, 0),  # 77
    Feld("Zusatzinformation - Art 16", "T", 20, 0),  # 78
    Feld("Zusatzinformation- Inhalt 16", "T", 210, 0),  # 79
    Feld("Zusatzinformation - Art 17", "T", 20, 0),  # 80
    Feld("Zusatzinformation- Inhalt 17", "T", 210, 0),  # 81
    Feld("Zusatzinformation - Art 18", "T", 20, 0),  # 82
    Feld("Zusatzinformation- Inhalt 18", "T", 210, 0),  # 83
    Feld("Zusatzinformation - Art 19", "T", 20, 0),  # 84
    Feld("Zusatzinformation- Inhalt 19", "T", 210, 0),  # 85
    Feld("Zusatzinformation - Art 20", "T", 20, 0),  # 86
    Feld("Zusatzinformation- Inhalt 20", "T", 210, 0),  # 87
    Feld("Stück", "Z", 8, 0),  # 88
    Feld("Gewicht", "Z", 8, 2),  # 89
    Feld("Zahlweise", "Z", 2, 0),  # 90
    Feld("Forderungsart", "T", 10, 0),  # 91
    Feld("Veranlagungsjahr", "Z", 4, 0),  # 92
    Feld("Zugeordnete Fälligkeit", "D", 8, 0),  # 93
    Feld("Skontotyp", "Z", 1, 0),  # 94
    Feld("Auftragsnummer", "T", 30, 0),  # 95
    Feld("Buchungstyp", "T", 2, 0),  # 96
    Feld("USt-Schlüssel (Anzahlungen)", "Z", 2, 0),  # 97
    Feld("EU-Land (Anzahlungen)", "T", 2, 0),  # 98
    Feld("Sachverhalt L+L (Anzahlungen)", "Z", 3, 0),  # 99
    Feld("EU-Steuersatz (Anzahlungen)", "Z", 2, 2),  # 100
    Feld("Erlöskonto (Anzahlungen)", "K", 9, 0),  # 101
    Feld("Herkunft-Kz", "T", 2, 0),  # 102
    Feld("Buchungs GUID", "T", 36, 0),  # 103
    Feld("KOST-Datum", "D", 8, 0),  # 104
    Feld("SEPA-Mandatsreferenz", "T", 35, 0),  # 105
    Feld("Skontosperre", "Z", 1, 0),  # 106
    Feld("Gesellschaftername", "T", 76, 0),  # 107
    Feld("Beteiligtennummer", "Z", 4, 0),  # 108
    Feld("Identifikationsnummer", "T", 11, 0),  # 109
    Feld("Zeichnernummer", "T", 20, 0),  # 110
    Feld("Postensperre bis", "D", 8, 0),  # 111
    Feld("Bezeichnung SoBil-Sachverhalt", "T", 30, 0),  # 112
    Feld("Kennzeichen SoBil-Buchung", "Z", 2, 0),  # 113
    Feld("Festschreibung", "Z", 1, 0),  # 114
    Feld("Leistungsdatum", "D", 8, 0),  # 115
    Feld("Datum Zuord. Steuerperiode", "D", 8, 0),  # 116
    Feld("Fälligkeit", "D", 8, 0),  # 117
    Feld("Generalumkehr (GU)", "T", 1, 0),  # 118
    Feld("Steuersatz", "Z", 2, 2),  # 119
    Feld("Land", "T", 2, 0),  # 120
    Feld("Abrechnungsreferenz", "T", 50, 0),  # 121
    Feld("BVV-Position", "Z", 1, 0),  # 122
    Feld("EU-Land u. UStID (Ursprung)", "T", 15, 0),  # 123
    Feld("EU-Steuersatz (Ursprung)", "Z", 2, 2),  # 124
    Feld("Abw. Skontokonto", "K", 8, 0),  # 125
)
