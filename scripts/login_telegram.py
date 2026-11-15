"""Login interativo na SUA conta do Telegram (rodar uma vez, no Codespaces).

Pede seu número e o código que chega no app do Telegram (e a senha de
verificação em duas etapas, se você tiver). Depois grava a sessão em
TELEGRAM_SESSION no .env.

Uso: python -m scripts.login_telegram
"""
from __future__ import annotations

import asyncio
import getpass

from app.config import ConfigTelegram, gravar_variavel
from app.fontes.telegram import criar_cliente


async def main() -> None:
    cfg = ConfigTelegram.carregar()
    cliente = criar_cliente(cfg)
    await cliente.start(
        phone=lambda: input("Seu número com DDI (ex.: +5551999999999): ").strip(),
        code_callback=lambda: input("Código que chegou no Telegram: ").strip(),
        password=lambda: getpass.getpass("Senha da verificação em duas etapas: "),
    )
    eu = await cliente.get_me()
    sessao = cliente.session.save()
    await cliente.disconnect()
    gravar_variavel("TELEGRAM_SESSION", sessao)
    print(f"\nLogado como {eu.first_name} (@{eu.username or 'sem username'}).")
    print("Sessão gravada em TELEGRAM_SESSION no .env.")
    print("ATENÇÃO: essa sessão dá acesso total à sua conta. Não compartilhe nem commite.")


if __name__ == "__main__":
    asyncio.run(main())
