"""Etapa 1 do pipeline: transformar o texto da oferta em specs estruturadas.

Ordem: pré-filtro (grátis) → leitor em código (grátis) → IA (só se precisar).
"""
from app.extracao.modelos import Specs
from app.extracao.pipeline import Extracao, extrair

__all__ = ["Specs", "Extracao", "extrair"]
