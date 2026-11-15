#!/usr/bin/env bash
# Controle do monitor no Heroku, a partir do Codespace.
#   bash scripts/monitor.sh status     → está rodando?
#   bash scripts/monitor.sh logs       → últimas 60 linhas do que ele fez
#   bash scripts/monitor.sh ao-vivo    → acompanha em tempo real (Ctrl+C sai; o monitor continua)
#   bash scripts/monitor.sh parar      → desliga o monitor
#   bash scripts/monitor.sh ligar      → liga o monitor
#   bash scripts/monitor.sh reiniciar  → reinicia
set -euo pipefail
APP="projeto-automacao-ofertas"
cd "$(dirname "$0")/.."
linha="$(grep -E "^HEROKU_API_KEY=" .env 2>/dev/null | tail -n1 || true)"
export HEROKU_API_KEY="${HEROKU_API_KEY:-${linha#*=}}"
[ -n "$HEROKU_API_KEY" ] || { echo "Falta HEROKU_API_KEY no .env"; exit 1; }
command -v heroku >/dev/null || { echo "Instalando a ferramenta do Heroku..."; curl -fsSL https://cli-assets.heroku.com/install.sh | sh; }

case "${1:-status}" in
  status)    heroku ps -a "$APP" 2>/dev/null ;;
  logs)      heroku logs -n 60 -a "$APP" 2>/dev/null ;;
  ao-vivo)   heroku logs --tail -a "$APP" 2>/dev/null ;;
  parar)     heroku ps:scale worker=0 -a "$APP" 2>/dev/null && echo "Monitor DESLIGADO." ;;
  ligar)     heroku ps:scale worker=1 -a "$APP" 2>/dev/null && echo "Monitor LIGADO." ;;
  reiniciar) heroku ps:restart -a "$APP" 2>/dev/null && echo "Monitor reiniciado." ;;
  *) sed -n '2,8p' "$0" ;;
esac
