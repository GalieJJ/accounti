#!/usr/bin/env bash
# Installiert das KoSIT-Prüftool (Validator + XRechnung-Konfiguration) mit fester Version.
#
#   scripts/kosit_installieren.sh            → nach ./.kosit
#   ACCOUNTI_KOSIT_DIR=/opt/kosit scripts/kosit_installieren.sh
#
# Die Prüfsummen sind fest hinterlegt: Ein geändertes Release wird nicht installiert.
set -euo pipefail

VALIDATOR_VERSION="1.6.3"
VALIDATOR_SHA256="799e64befca97d4080e03608c80b85dd5a5ecc5f4ae4f35d1116ec2855b9a7c9"
KONFIG_RELEASE="v2026-08-31"
KONFIG_DATEI="xrechnung-3.0.2-validator-configuration-2026-08-31.zip"
KONFIG_SHA256="2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8"

ZIEL="${ACCOUNTI_KOSIT_DIR:-.kosit}"
JAR="validator-${VALIDATOR_VERSION}-standalone.jar"

if [[ -f "$ZIEL/$JAR" && -f "$ZIEL/xrechnung/scenarios.xml" ]]; then
  echo "KoSIT-Prüftool bereits installiert: $ZIEL"
  exit 0
fi

mkdir -p "$ZIEL"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL -o "$TMP/$JAR" \
  "https://github.com/itplr-kosit/validator/releases/download/v${VALIDATOR_VERSION}/${JAR}"
curl -fsSL -o "$TMP/$KONFIG_DATEI" \
  "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/${KONFIG_RELEASE}/${KONFIG_DATEI}"

echo "${VALIDATOR_SHA256}  $TMP/$JAR" | sha256sum -c -
echo "${KONFIG_SHA256}  $TMP/$KONFIG_DATEI" | sha256sum -c -

rm -rf "$ZIEL/xrechnung"
mkdir -p "$ZIEL/xrechnung"
python3 -m zipfile -e "$TMP/$KONFIG_DATEI" "$ZIEL/xrechnung"
mv "$TMP/$JAR" "$ZIEL/$JAR"
echo "KoSIT-Prüftool installiert: $ZIEL (Validator $VALIDATOR_VERSION, Konfiguration $KONFIG_RELEASE)"
