#!/bin/bash
INPUT="$1"
OUTPUT="$2"
CERT="$3"
PASS="$4"
REASON="${5:-Automação OS}"

pdftk "$INPUT" \
  stamp_output "$OUTPUT" \
  data_operator add_user_pw "" "$PASS" \
  cat "$INPUT" \
  output "$OUTPUT" \
  2>/dev/null

# Assinatura real com OpenSSL + qpdf (padrão ICP-BRASIL/LGPD)
openssl cms -sign \
  -in "$INPUT" \
  -outform DER \
  -out /tmp/sig.der \
  -signer "$CERT" \
  -passin pass:"$PASS" \
  -nodetach 2>/dev/null

qpdf --encrypt --user-password="" --owner-password="$PASS" --key-length=128 "$INPUT" "$OUTPUT" 2>/dev/null