#!/usr/bin/env bash
# Demonstração da Av3 — Redes de Computadores.
#
#   ./demo.sh              # abre servidor + 3 clientes em janelas tmux
#   ./demo.sh --porta 9990 # porta alternativa (padrão: 9990)
#
# Sem tmux instalado, o script só imprime os comandos para abrir em terminais separados.

set -euo pipefail
cd "$(dirname "$0")"

PORTA=9990
if [[ "${1:-}" == "--porta" ]]; then PORTA="${2:?informe a porta}"; fi
SESSAO="chat-av3"

if ! command -v tmux >/dev/null 2>&1; then
  cat <<EOF
tmux não encontrado. Abra 4 terminais neste diretório e rode:

  python3 servidor.py --porta $PORTA
  python3 cliente.py --nick ana   --porta-servidor $PORTA
  python3 cliente.py --nick bruno --porta-servidor $PORTA
  python3 cliente.py --nick carla --porta-servidor $PORTA
EOF
  exit 0
fi

tmux kill-session -t "$SESSAO" 2>/dev/null || true
tmux new-session  -d -s "$SESSAO" -n servidor "python3 servidor.py --porta $PORTA"
tmux new-window   -t "$SESSAO" -n ana       "sleep 1; python3 cliente.py --nick ana   --porta-servidor $PORTA"
tmux new-window   -t "$SESSAO" -n bruno     "sleep 1.5; python3 cliente.py --nick bruno --porta-servidor $PORTA"
tmux new-window   -t "$SESSAO" -n carla     "sleep 2; python3 cliente.py --nick carla --porta-servidor $PORTA"
tmux select-window -t "$SESSAO:servidor"
tmux attach -t "$SESSAO"
