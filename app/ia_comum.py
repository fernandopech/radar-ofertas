"""Cliente da Anthropic e leitura de JSON compartilhados pelas etapas de IA."""
from __future__ import annotations

import json
import os

import anthropic

TIMEOUT_S = float(os.getenv("IA_TIMEOUT_S", "60"))
_cliente: anthropic.Anthropic | None = None


def get_cliente() -> anthropic.Anthropic:
    global _cliente
    if _cliente is None:
        # lê ANTHROPIC_API_KEY do ambiente; 1 nova tentativa em erro temporário
        _cliente = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=1)
    return _cliente


def json_da_resposta(texto: str) -> dict:
    """Aceita JSON puro ou dentro de ```json ... ```; pega do primeiro { ao último }."""
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise ValueError("resposta sem objeto JSON")
    return json.loads(texto[inicio : fim + 1])
