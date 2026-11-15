"""Carrega criterios.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import RAIZ


@dataclass(frozen=True)
class Criterios:
    preco_max: float
    ram_min_gb: int
    armazenamento_min_gb: int
    tipo_armazenamento: str
    tela_pol_min: float
    tela_pol_max: float
    sistemas_aceitos: list[str]
    exigir_cs2: bool
    excluir_termos: list[str]
    componentes: dict[str, dict[str, list[str]]]  # ex.: {"gpu": {"boa": [...], "excluir": [...]}}
    oportunidade_ativa: bool
    oportunidade_preco_max: float
    oportunidade_desconto_min_pct: float
    nota_minima: float
    nota_minima_usado: float
    dedup_horas: float
    queda_minima_reais: float
    notificar_ate_horas: float
    notificar_ate_horas_marketplace: float
    bruto: dict[str, Any]  # yaml inteiro, pra montar o prompt da avaliação

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Criterios":
        dados = yaml.safe_load((caminho or RAIZ / "criterios.yaml").read_text(encoding="utf-8"))
        r = dados["regras_duras"]
        op = dados.get("oportunidade") or {}
        return cls(
            preco_max=float(r["preco_max"]),
            ram_min_gb=int(r["ram_min_gb"]),
            armazenamento_min_gb=int(r["armazenamento_min_gb"]),
            tipo_armazenamento=str(r["tipo_armazenamento"]),
            tela_pol_min=float(r["tela_pol_min"]),
            tela_pol_max=float(r["tela_pol_max"]),
            sistemas_aceitos=list(r["sistemas_aceitos"]),
            exigir_cs2=bool(r.get("exigir_cs2", True)),
            excluir_termos=list(r.get("excluir_termos") or []),
            componentes={comp: {nivel: list(termos or []) for nivel, termos in (niveis or {}).items()}
                         for comp, niveis in (dados.get("componentes") or {}).items()},
            oportunidade_ativa=bool(op.get("ativo", False)),
            oportunidade_preco_max=float(op.get("preco_max_absoluto", 0)),
            oportunidade_desconto_min_pct=float(op.get("desconto_min_pct", 100)),
            nota_minima=float(dados["notificacao"]["nota_minima"]),
            nota_minima_usado=float(dados["condicao"]["nota_minima_usado"]),
            dedup_horas=float(dados["notificacao"].get("dedup_horas", 72)),
            queda_minima_reais=float(dados["notificacao"].get("queda_minima_reais", 50)),
            notificar_ate_horas=float(dados["notificacao"].get("notificar_ate_horas", 6)),
            notificar_ate_horas_marketplace=float(dados["notificacao"].get("notificar_ate_horas_marketplace", 168)),
            bruto=dados,
        )
