"""Recupera anúncios da OLX dos últimos N dias (páginas 2, 3, ... da busca) e processa.

Roda no Codespace junto com o monitor do Heroku sem conflito (não usa o Telegram).
Anúncios já no banco são pulados; aprovados ainda ativos são notificados pelo bot.
Uso: python -m scripts.olx_recuperar            (7 dias, até 6 páginas)
     python -m scripts.olx_recuperar --dias 3
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from app.avaliacao import Criterios
from app.banco import Banco
from app.fontes.olx import ConfigOlx, FonteOlx, _data
from app.main import Monitor
from app.notificacao import Bot


def main(dias: int, max_paginas: int) -> None:
    c = Criterios.carregar()
    cfg = ConfigOlx.carregar(c.bruto)
    if not cfg:
        raise SystemExit("OLX desligada: falta RAPIDAPI_KEY no .env ou olx.ativo no criterios.yaml")
    banco = Banco()
    monitor = Monitor(banco, Bot(), c)
    fonte = FonteOlx(cfg, ja_existe=banco.ja_existe)
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    total = 0
    for pagina in range(2, max_paginas + 2):
        novas = fonte.ciclo(pagina=pagina)
        for oferta in sorted(novas, key=lambda o: o.recebida_em):
            monitor.tratar(oferta)
        total += len(novas)
        datas = [_data(a) for a in fonte.ultima_busca]
        mais_antiga = min(datas) if datas else None
        print(f"Página {pagina}: {len(novas)} anúncio(s) novo(s) da região processado(s)"
              + (f" · mais antigo da página: {mais_antiga:%d/%m %H:%M}" if mais_antiga else ""))
        if not fonte.ultima_busca or (mais_antiga and mais_antiga < limite):
            break
    print(f"\nPronto: {total} anúncio(s) processado(s). Consultas restantes no mês: {fonte.cliente.saldo}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for ruido in ("httpx2", "httpx", "httpcore2"):
        logging.getLogger(ruido).setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--max-paginas", type=int, default=6)
    a = ap.parse_args()
    main(a.dias, a.max_paginas)
