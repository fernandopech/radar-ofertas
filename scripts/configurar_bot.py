"""Etapa 7: confere o token do bot e descobre o seu chat (grava BOT_CHAT_ID no .env).

Antes: crie o bot no @BotFather, cole o token em BOT_TOKEN no .env
e mande /start para o bot pelo Telegram.
Uso: python -m scripts.configurar_bot
"""
from __future__ import annotations

from app.config import gravar_variavel
from app.notificacao import Bot


def main() -> None:
    bot = Bot()
    eu = bot.quem_sou()
    print(f"Token OK: bot @{eu['username']} ({eu['first_name']})")
    privados = [c for c in bot.chats_recentes() if c.get("type") == "private"]
    if not privados:
        print(f"\nNenhuma conversa encontrada. Abra https://t.me/{eu['username']} no Telegram,")
        print("aperte INICIAR (ou mande /start) e rode este comando de novo.")
        return
    chat = privados[-1]
    nome = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
    gravar_variavel("BOT_CHAT_ID", str(chat["id"]))
    print(f"Chat encontrado: {nome} (@{chat.get('username', '-')}). BOT_CHAT_ID gravado no .env.")
    bot.chat_id = str(chat["id"])
    bot.enviar("✅ Pronto! A partir de agora eu te aviso quando aparecer um notebook que vale a pena.")
    print("Mandei uma mensagem de confirmação. Confira no Telegram.")


if __name__ == "__main__":
    main()
