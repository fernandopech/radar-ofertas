from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.extracao.modelos import Specs
from app.extracao.parser_ficha import ler_ficha
from app.extracao.prefiltro import parece_notebook
from app.oferta import Oferta

Metodo = Literal["prefiltro", "parser", "ia", "falhou"]


@dataclass
class Extracao:
    specs: Specs | None
    metodo: Metodo  # quem decidiu: descartado no pré-filtro, leitor em código ou IA


def extrair(oferta: Oferta, usar_ia: bool = True) -> Extracao:
    if not oferta.categoria_confirmada and not parece_notebook(oferta.texto):
        return Extracao(None, "prefiltro")
    if specs := ler_ficha(oferta):
        return Extracao(specs, "parser")
    if not usar_ia:
        return Extracao(None, "falhou")
    from app.extracao.ia import extrair_com_ia  # só importa/conecta se precisar

    specs = extrair_com_ia(oferta)
    return Extracao(specs, "ia" if specs else "falhou")
