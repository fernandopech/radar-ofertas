#!/usr/bin/env bash
# Deploy completo no Heroku a partir do Codespace, com um comando:
#   bash scripts/deploy_heroku.sh [nome-do-app]
# Cria o app (se não existir), copia as variáveis do .env SEM mostrá-las,
# sobe o código e liga o worker. Rodar de novo só atualiza.
set -euo pipefail
APP="${1:-projeto-automacao-ofertas}"
VARS=(TELEGRAM_API_ID TELEGRAM_API_HASH TELEGRAM_SESSION TELEGRAM_CANAIS
      ANTHROPIC_API_KEY SUPABASE_URL SUPABASE_KEY BOT_TOKEN BOT_CHAT_ID)

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Sem .env aqui. Rode no Codespace, na pasta do projeto."; exit 1; }

if ! command -v heroku >/dev/null; then
  echo "→ Instalando a ferramenta do Heroku (heroku CLI)..."
  curl -fsSL https://cli-assets.heroku.com/install.sh | sh
fi

# Login pela chave de API (o "heroku login" pelo navegador falha no Codespaces com
# "IP address mismatch": o terminal está na nuvem e o navegador no seu computador).
linha_key="$(grep -E "^HEROKU_API_KEY=" .env | tail -n1 || true)"
export HEROKU_API_KEY="${HEROKU_API_KEY:-${linha_key#*=}}"
if [ -z "$HEROKU_API_KEY" ]; then
  cat <<'AJUDA'
✗ Falta HEROKU_API_KEY no .env.
  1. Heroku → Account Settings → seção "API Key" → Reveal (ou Regenerate) e copie.
  2. No .env, adicione a linha:  HEROKU_API_KEY=<a chave>
  3. Rode este script de novo.
  (A chave dá acesso total à sua conta do Heroku: não compartilhe nem commite.)
AJUDA
  exit 1
fi
if ! heroku auth:whoami >/dev/null 2>&1; then
  echo "✗ HEROKU_API_KEY inválida ou expirada. Gere outra em Account Settings → API Key."
  exit 1
fi
echo "→ Conta: $(heroku auth:whoami)"

if heroku apps:info -a "$APP" >/dev/null 2>&1; then
  echo "→ App $APP já existe; atualizando."
else
  echo "→ Criando app $APP (região EUA, perto do Supabase)..."
  heroku apps:create "$APP" --region us
fi

echo "→ Copiando variáveis do .env (valores não são exibidos)..."
args=()
for v in "${VARS[@]}"; do
  linha="$(grep -E "^${v}=" .env | tail -n1 || true)"
  valor="${linha#*=}"
  if [ -z "$valor" ]; then echo "  ✗ $v está vazio no .env"; exit 1; fi
  args+=("${v}=${valor}")
done
# Opcionais: vão pro Heroku só se estiverem preenchidas no .env
for v in RAPIDAPI_KEY; do
  linha="$(grep -E "^${v}=" .env | tail -n1 || true)"
  valor="${linha#*=}"
  [ -n "$valor" ] && args+=("${v}=${valor}")
done
heroku config:set -a "$APP" "${args[@]}" >/dev/null
echo "  ✓ ${#args[@]} variáveis configuradas"

echo "→ Subindo o código (branch main)..."
git push "https://heroku:${HEROKU_API_KEY}@git.heroku.com/${APP}.git" HEAD:main 2>&1 \
  | sed "s/${HEROKU_API_KEY}/***/g"

echo "→ Ligando o monitor (worker, plano Basic)..."
heroku ps:type worker=basic -a "$APP" >/dev/null 2>&1 || true
heroku ps:scale web=0 worker=1 -a "$APP" >/dev/null 2>&1 || heroku ps:scale worker=1 -a "$APP"

cat <<FIM

✓ Pronto. IMPORTANTE: pare o monitor no Codespace (Ctrl+C), se estiver rodando:
  duas cópias com a mesma sessão do Telegram derrubam uma à outra.

Acompanhar os logs (Ctrl+C sai, o monitor continua no Heroku):
  heroku logs --tail -a $APP
FIM
