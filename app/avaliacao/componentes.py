"""Classifica CPU, GPU e tela pelas listas de níveis do criterios.yaml."""
from __future__ import annotations

from dataclasses import dataclass

from app.avaliacao.criterios import Criterios
from app.avaliacao.regras_nomes import bate_com

# Ordem de prioridade: o primeiro nível que casar vence (excluir sempre primeiro).
ORDEM = ["excluir", "excelente", "boa", "ok", "fraca", "ruim"]


@dataclass
class Classe:
    nivel: str | None   # None = fora de todas as listas
    termo: str | None   # termo da lista que casou

    def __str__(self) -> str:
        return f"{self.nivel} ({self.termo})" if self.nivel else "fora das listas"


def classificar_nome(nome: str, niveis: dict[str, list[str]]) -> Classe:
    if not nome:
        return Classe(None, None)
    for nivel in ORDEM + [n for n in niveis if n not in ORDEM]:
        for termo in niveis.get(nivel, []):
            if bate_com(nome, termo):
                return Classe(nivel, termo)
    return Classe(None, None)


def classificar_tela(texto_tela: str, niveis: dict[str, list[str]]) -> dict[str, list[str]]:
    """Tela pode ter várias qualidades ao mesmo tempo (IPS + 144 Hz): devolve todas."""
    achados: dict[str, list[str]] = {}
    alvo = texto_tela.lower()
    for nivel, termos in niveis.items():
        bate = [t for t in termos if t.lower() in alvo]
        if bate:
            achados[nivel] = bate
    return achados


def classificar(cpu: str, gpu: str, tela: str, c: Criterios) -> dict[str, object]:
    comp = c.componentes
    return {
        "cpu": classificar_nome(cpu, comp.get("cpu", {})),
        "gpu": classificar_nome(gpu, comp.get("gpu", {})),
        "tela": classificar_tela(tela, comp.get("tela", {})),
    }
