"""Etapa 2: escuta os canais e imprime cada oferta nova no terminal.

Uso: python -m scripts.escutar   (Ctrl+C pra parar)
"""
from __future__ import annotations

import asyncio
import logging

from app.config import ConfigTelegram
from app.fontes.telegram import FonteTelegram
from app.oferta import Oferta


async def imprimir(oferta: Oferta) -> None:
    print("=" * 70)
    print(f"{oferta.fonte} · {oferta.id_externo} · {oferta.recebida_em:%d/%m %H:%M}")
    print(f"imagem: {'sim' if oferta.tem_imagem else 'não'} · link: {oferta.link}")
    if oferta.link_origem:
        print(f"post: {oferta.link_origem}")
    print("-" * 70)
    print(oferta.texto)


async def main() -> None:
    fonte = FonteTelegram(ConfigTelegram.carregar())
    await fonte.executar(imprimir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nParado.")
