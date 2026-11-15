"""Etapa 6: processa as amostras e grava tudo no Supabase.

Ofertas que já estão no banco são puladas (não gasta IA de novo).
Uso: python -m scripts.gravar
     python -m scripts.gravar --refazer   (reprocessa e sobrescreve as que já existem)
"""
from __future__ import annotations

import argparse
import logging
from collections import Counter

from app.avaliacao import Criterios
from app.banco import Banco
from app.config import RAIZ
from app.processamento import processar, registro
from scripts.extrair import carregar

PASTA = RAIZ / "amostras"


def main(refazer: bool) -> None:
    banco = Banco()
    c = Criterios.carregar()
    arquivos = sorted(p for p in PASTA.glob("*.jsonl")
                      if not p.name.startswith(("extraidas_", "avaliadas_")))
    total: Counter[str] = Counter()
    for arquivo in arquivos:
        for o in carregar(arquivo):
            if not refazer and banco.ja_existe(o.fonte, o.id_externo):
                total["já estava"] += 1
                continue
            p = processar(o, c)
            banco.gravar(registro(p))
            if p.resultado is None:
                total["não é notebook"] += 1
            elif p.resultado.aprovado:
                total["aprovada"] += 1
                print(f"{'🔥' if p.resultado.oportunidade else '✅'} {p.extracao.specs.modelo}")
            else:
                total["reprovada"] += 1
    print("Gravadas: " + " · ".join(f"{k} {v}" for k, v in total.items()))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--refazer", action="store_true")
    main(ap.parse_args().refazer)
