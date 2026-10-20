#!/usr/bin/env bash
# Installiert die Prüfwerkzeuge für E-Rechnungen mit fester Version und Prüfsumme:
#   - KoSIT-Validator + XRechnung-Konfiguration (formale Prüfung der XRechnung)
#   - Mustang-CLI (ZUGFeRD: PDF/A-3 über veraPDF und das eingebettete XML)
#
#   scripts/pruefwerkzeuge_installieren.sh              → nach ./.pruefwerkzeuge
#   ACCOUNTI_PRUEFWERKZEUGE=/opt/pruef scripts/pruefwerkzeuge_installieren.sh
#
# Die Prüfsummen sind fest hinterlegt: Ein geändertes Release wird nicht installiert.
# Benötigt Java 21.
set -euo pipefail

KOSIT_VERSION="1.6.3"
KOSIT_SHA256="799e64befca97d4080e03608c80b85dd5a5ecc5f4ae4f35d1116ec2855b9a7c9"
KONFIG_RELEASE="v2026-08-31"
KONFIG_DATEI="xrechnung-3.0.2-validator-configuration-2026-08-31.zip"
KONFIG_SHA256="2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8"
MUSTANG_VERSION="2.26.0"
MUSTANG_SHA256="42d7868cb68264874a7b8cab4c3587b03b23ccc7cd72373da917f66758bb9736"

ZIEL="${ACCOUNTI_PRUEFWERKZEUGE:-.pruefwerkzeuge}"
KOSIT_JAR="validator-${KOSIT_VERSION}-standalone.jar"
MUSTANG_JAR="Mustang-CLI-${MUSTANG_VERSION}.jar"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

lade() {  # lade <url> <datei> <sha256>
  curl -fsSL -o "$TMP/$2" "$1"
  echo "$3  $TMP/$2" | sha256sum -c -
}

if [[ -f "$ZIEL/kosit/$KOSIT_JAR" && -f "$ZIEL/kosit/xrechnung/scenarios.xml" ]]; then
  echo "KoSIT-Prüftool bereits installiert: $ZIEL/kosit"
else
  lade "https://github.com/itplr-kosit/validator/releases/download/v${KOSIT_VERSION}/${KOSIT_JAR}" \
    "$KOSIT_JAR" "$KOSIT_SHA256"
  lade "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/${KONFIG_RELEASE}/${KONFIG_DATEI}" \
    "$KONFIG_DATEI" "$KONFIG_SHA256"
  rm -rf "$ZIEL/kosit"
  mkdir -p "$ZIEL/kosit/xrechnung"
  python3 -m zipfile -e "$TMP/$KONFIG_DATEI" "$ZIEL/kosit/xrechnung"
  mv "$TMP/$KOSIT_JAR" "$ZIEL/kosit/$KOSIT_JAR"
  echo "KoSIT-Prüftool installiert: $ZIEL/kosit (Validator $KOSIT_VERSION, Konfiguration $KONFIG_RELEASE)"
fi

if [[ -f "$ZIEL/mustang/$MUSTANG_JAR" ]]; then
  echo "Mustang bereits installiert: $ZIEL/mustang"
else
  lade "https://github.com/ZUGFeRD/mustangproject/releases/download/core-${MUSTANG_VERSION}/${MUSTANG_JAR}" \
    "$MUSTANG_JAR" "$MUSTANG_SHA256"
  rm -rf "$ZIEL/mustang"
  mkdir -p "$ZIEL/mustang"
  mv "$TMP/$MUSTANG_JAR" "$ZIEL/mustang/$MUSTANG_JAR"
  echo "Mustang installiert: $ZIEL/mustang (Mustang-CLI $MUSTANG_VERSION)"
fi
