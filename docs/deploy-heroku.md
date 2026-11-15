# Deploy no Heroku

## Jeito rápido (recomendado): um comando no Codespace

```bash
bash scripts/deploy_heroku.sh
```

Antes, coloque no `.env` a `HEROKU_API_KEY` (Heroku → Account Settings → API Key → Reveal).
O `heroku login` pelo navegador não funciona no Codespaces ("IP address mismatch").

O script instala a ferramenta do Heroku, cria o app, copia as variáveis do `.env` sem
exibi-las, sobe o código e liga o worker. Rodar de novo só atualiza.

## Jeito manual, pelo painel

O monitor (`app/main.py`) roda como **worker** (não tem site), 24h por dia.
Arquivos usados pelo Heroku: `Procfile`, `.python-version`, `requirements.txt`.

## 1. Criar o app (uma vez)

No painel do Heroku: **New → Create new app** → nome, por exemplo `projeto-automacao-ofertas`
→ região **United States** (mesma região do Supabase).

## 2. Ligar ao GitHub

Aba **Deploy** → Deployment method: **GitHub** → conectar `<seu-usuario>/radar-ofertas`
→ **Enable Automatic Deploys** do branch `main` (cada push sobe sozinho).

## 3. Variáveis (Settings → Config Vars → Reveal Config Vars)

Copie do seu `.env` do Codespace, uma por uma:

| Variável | Observação |
|---|---|
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | do my.telegram.org |
| `TELEGRAM_SESSION` | a sessão longa gerada no login (é a sua conta: trate como senha) |
| `TELEGRAM_CANAIS` | ex.: `qualnotebook` |
| `ANTHROPIC_API_KEY` | |
| `SUPABASE_URL`, `SUPABASE_KEY` | chave secreta `sb_secret_...` |
| `BOT_TOKEN`, `BOT_CHAT_ID` | |

## 4. Ligar o worker

Faça o primeiro deploy (Deploy → **Deploy Branch**). Depois, aba **Resources**:
desligue `web` se aparecer, ligue **worker** (`python -m app.main`), plano **Basic**.

## 5. Conferir

**More → View logs**: deve aparecer `Monitor iniciado` e `Escutando 1 canal(is): qualnotebook`.

## Importante

- **Desligue o monitor no Codespace** quando o Heroku estiver rodando: duas cópias com a
  mesma sessão do Telegram podem derrubar uma à outra.
- Mudou o `criterios.yaml`? Commit + push: o deploy automático reinicia com os critérios novos.
- O Heroku reinicia o worker 1x por dia; ao subir, o monitor recupera as últimas 30
  mensagens e pula as que já estão no banco.

## Dia a dia (no Codespace)

```bash
bash scripts/monitor.sh status      # está rodando?
bash scripts/monitor.sh logs        # o que ele fez por último
bash scripts/monitor.sh ao-vivo     # acompanhar em tempo real (Ctrl+C sai)
bash scripts/monitor.sh parar       # desligar
bash scripts/monitor.sh ligar       # ligar
bash scripts/monitor.sh reiniciar   # reiniciar
```

Mudou código, `criterios.yaml` ou a lista de canais no `.env`? `git pull` e
`bash scripts/deploy_heroku.sh` de novo.
