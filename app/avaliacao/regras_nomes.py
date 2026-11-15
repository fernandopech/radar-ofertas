"""Comparação de nomes de componentes por palavras."""
from __future__ import annotations

import re

_RUIDO = {"intel", "amd", "graphics", "gráficos", "integrada", "processador"}


def _tokens(nome: str) -> list[str]:
    """'Intel Core 7-240H (Série 2)' -> ['core', '7', '240h']"""
    nome = re.sub(r"\([^)]*\)", " ", nome.lower())
    return [t for t in re.split(r"[\s\-_/,]+", nome) if t and t not in _RUIDO]


def bate_com(nome: str, termo: str) -> bool:
    """Todas as palavras do termo aparecem no nome, na mesma ordem.

    'Radeon Vega' bate com 'Radeon RX Vega 8'; 'Core 3' bate com 'Core 3-304';
    'Core 3' NÃO bate com 'Core 5-320' nem com 'Ryzen 3' com 'Ryzen 7 3700U'.
    """
    alvo, procura = _tokens(nome), _tokens(termo)
    if not procura:
        return False
    i = 0
    for t in alvo:
        if t == procura[i]:
            i += 1
            if i == len(procura):
                return True
    return False
