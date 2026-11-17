#!/usr/bin/env bash
# Gera dist/sockets-chat-cliente.zip com o que o colega precisa: cliente.py + protocolo.py.
# Rode de qualquer lugar:  ./scripts/empacotar-cliente.sh
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ=$(pwd)
DESTINO="$RAIZ/dist/sockets-chat-cliente.zip"

mkdir -p dist
rm -f "$DESTINO"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/cliente-av3"
cp cliente.py protocolo.py "$TMP/cliente-av3/"
cp scripts/LEIA-ME-cliente.txt "$TMP/cliente-av3/LEIA-ME.txt"

command -v zip >/dev/null || { echo "precisa do comando zip instalado" >&2; exit 1; }
( cd "$TMP" && zip -qr "$DESTINO" cliente-av3 )

echo "gerado: dist/sockets-chat-cliente.zip"
unzip -l "$DESTINO" | sed 's/^/  /'
