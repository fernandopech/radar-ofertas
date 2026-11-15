"""Lista canais e grupos da sua conta pra você escolher o TELEGRAM_CANAIS.

Uso: python -m scripts.listar_canais [filtro]
     ex.: python -m scripts.listar_canais promo
"""
from __future__ import annotations

import asyncio
import sys

from app.config import ConfigFaltando, ConfigTelegram
from app.fontes.telegram import criar_cliente


async def main(filtro: str) -> None:
    cfg = ConfigTelegram.carregar()
    if not cfg.session:
        raise ConfigFaltando("Rode antes: python -m scripts.login_telegram")
    cliente = criar_cliente(cfg)
    await cliente.connect()
    if not await cliente.is_user_authorized():
        raise ConfigFaltando("Sessão inválida. Rode de novo: python -m scripts.login_telegram")

    print(f"{'TIPO':<7} {'USE EM TELEGRAM_CANAIS':<28} NOME")
    async for d in cliente.iter_dialogs():
        if not (d.is_channel or d.is_group):
            continue
        if filtro and filtro.lower() not in (d.name or "").lower():
            continue
        tipo = "canal" if d.is_channel and not d.is_group else "grupo"
        username = getattr(d.entity, "username", None)
        ident = username or str(d.id)
        print(f"{tipo:<7} {ident:<28} {d.name}")
    await cliente.disconnect()


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:])))
