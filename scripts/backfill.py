"""Etapa 3: baixa as últimas mensagens dos canais para calibrar sem esperar promoção.

Salva em amostras/telegram_<canal>.jsonl (uma oferta por linha). Essas são
mensagens públicas dos canais, sem segredo, então podem ir pro Git; assim o
Claude consegue ler as amostras para montar os prompts das próximas etapas.

Uso: python -m scripts.backfill                 (canais do TELEGRAM_CANAIS, 100 cada)
     python -m scripts.backfill --limite 200
     python -m scripts.backfill qualnotebook outrocanal
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import replace

from app.config import RAIZ, ConfigTelegram
from app.fontes.telegram import FonteTelegram
from app.oferta import Oferta

PASTA = RAIZ / "amostras"


async def main(canais: list[str], limite: int) -> None:
    cfg = ConfigTelegram.carregar()
    if canais:
        cfg = replace(cfg, canais=canais)
    fonte = FonteTelegram(cfg)
    por_fonte: dict[str, list[Oferta]] = defaultdict(list)
    try:
        async for oferta in fonte.backfill(limite):
            por_fonte[oferta.fonte].append(oferta)
    finally:
        await fonte.fechar()

    PASTA.mkdir(exist_ok=True)
    for nome, ofertas in por_fonte.items():
        arquivo = PASTA / f"{nome.replace(':', '_')}.jsonl"
        with arquivo.open("w", encoding="utf-8") as f:
            for o in ofertas:
                f.write(json.dumps(o.para_dict(), ensure_ascii=False) + "\n")
        com_link = sum(1 for o in ofertas if o.link)
        com_imagem = sum(1 for o in ofertas if o.tem_imagem)
        print(f"{nome}: {len(ofertas)} mensagens com texto "
              f"({com_link} com link, {com_imagem} com imagem) → {arquivo.relative_to(RAIZ)}")

    todas = [o for lista in por_fonte.values() for o in lista]
    if todas:
        exemplo = todas[0]
        print("\nExemplo (mais recente):")
        print("-" * 70)
        print(exemplo.texto[:800])
        print("-" * 70)
        print(f"link: {exemplo.link}")
    else:
        print("Nenhuma mensagem com texto encontrada.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("canais", nargs="*", help="sobrescreve TELEGRAM_CANAIS")
    ap.add_argument("--limite", type=int, default=100)
    args = ap.parse_args()
    asyncio.run(main(args.canais, args.limite))
