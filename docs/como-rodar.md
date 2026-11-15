# Como rodar no GitHub Codespaces (sem instalar nada no seu computador)

1. No GitHub, abra o repositório → botão verde **Code** → aba **Codespaces** →
   **Create codespace on main**. Espere abrir o VS Code no navegador. As
   dependências instalam sozinhas e um `.env` é criado a partir do `.env.example`.
2. Abra o `.env` e preencha `TELEGRAM_API_ID` e `TELEGRAM_API_HASH`
   (gerados em https://my.telegram.org → API development tools).
3. No terminal (menu ☰ → Terminal → New Terminal):
   ```bash
   python -m scripts.login_telegram
   ```
   Digite seu número com +55 e o código que chega no app do Telegram.
   A sessão é gravada no `.env`.
4. Liste os canais e copie o identificador dos que interessam:
   ```bash
   python -m scripts.listar_canais
   ```
   Coloque em `TELEGRAM_CANAIS` no `.env`, separados por vírgula.
5. Escute as ofertas chegando:
   ```bash
   python -m scripts.escutar
   ```

6. Sem esperar promoção nova: baixe as últimas mensagens dos canais
   (salva em `amostras/`, que pode ir pro Git para o Claude ler):
   ```bash
   python -m scripts.backfill
   ```

7. Extraia as specs das amostras e revise a tabela
   (`--testar-ia 5` também compara 5 ofertas com a IA, pra validar a chave):
   ```bash
   python -m scripts.extrair --testar-ia 5
   ```

8. Aplique os critérios e veja a tabela de calibração
   (`--margem-preco 1000` também mostra quem só estourou o teto em até R$ 1.000):
   ```bash
   python -m scripts.avaliar --margem-preco 1000
   ```

9. Grave as amostras no Supabase (as que já estão no banco são puladas):
   ```bash
   python -m scripts.gravar
   ```

10. Bot de notificação: crie no @BotFather, cole o token em `BOT_TOKEN` no `.env`,
    mande /start pro bot e rode:
    ```bash
    python -m scripts.configurar_bot
    python -m scripts.testar_notificacao
    ```

11. Monitor completo (escuta → processa → grava → notifica). Ctrl+C pra parar:
    ```bash
    python -m app.main
    ```

**Desligue o codespace quando terminar** (☰ → Codespaces → Stop Current
Codespace). Ele consome as horas incluídas no GitHub Pro enquanto está ligado.

## Guardar os segredos para não perder

Um codespace parado por 30 dias é apagado, e o `.env` vai junto. Copie os
valores do `.env` para **github.com → Settings → Codespaces → Secrets**,
liberando só este repositório. Assim eles viram variáveis de ambiente em
qualquer codespace novo. Se a mesma variável estiver preenchida no `.env` e como secret,
vale a do `.env` (assim editar o `.env` sempre tem efeito).

## Segurança

- `.env` e `*.session` estão no `.gitignore`. Nunca commite segredos.
- `TELEGRAM_SESSION` dá acesso total à sua conta do Telegram: trate como senha.
- A conta pessoal só **lê**. Notificações saem por um bot separado.
