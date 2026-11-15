"""Julgamento de usados de marketplace: defeitos, preço efetivo e preços de referência.

- Defeito grave reprova; moderado soma o custo de reparo ao preço (preço efetivo).
- Referência principal: mediana de usados parecidos (mesma GPU e RAM) do nosso histórico,
  que é o mercado real. Sem parecidos suficientes: preço original × fator pela idade.
- Anti-golpe estatístico (ideia do radar-de-achados, MIT): preço abaixo de Q1 − 1,5×IQR.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConfigUsados:
    graves: list[str]
    custos: dict[str, float]          # tipo de defeito moderado → custo de reparo
    leves: list[str]
    depreciacao: dict[int, float]     # anos → fator
    comparaveis_dias: int = 30
    comparaveis_minimo: int = 4
    iqr_minimo: int = 6

    @classmethod
    def carregar(cls, bruto: dict[str, Any]) -> "ConfigUsados":
        u = bruto.get("usados") or {}
        d = u.get("defeitos") or {}
        return cls(
            graves=list(d.get("grave") or []),
            custos={str(k).lower(): float(v) for k, v in (d.get("moderado") or {}).items()},
            leves=list(d.get("leve") or []),
            depreciacao={int(k): float(v) for k, v in (u.get("depreciacao") or {1: 0.7}).items()},
            comparaveis_dias=int(u.get("comparaveis_dias", 30)),
            comparaveis_minimo=int(u.get("comparaveis_minimo", 4)),
            iqr_minimo=int(u.get("iqr_minimo", 6)),
        )

    def custo(self, tipo: str) -> float:
        tipo = (tipo or "").lower().strip()
        if tipo in self.custos:
            return self.custos[tipo]
        # aceita o começo do nome ("bateria" → "bateria viciada ou fraca")
        for chave, valor in self.custos.items():
            if tipo and (chave.startswith(tipo) or tipo.startswith(chave.split()[0])):
                return valor
        return self.custos.get("outro defeito moderado", 200.0)

    def fator(self, idade_anos: int) -> float:
        anos = sorted(self.depreciacao)
        idade = max(1, idade_anos)
        for a in anos:
            if idade <= a:
                return self.depreciacao[a]
        return self.depreciacao[anos[-1]]


@dataclass
class CalculoUsado:
    custo_reparo: float = 0.0
    reparos: list[str] = field(default_factory=list)   # "bateria viciada (+R$ 350)"
    graves: list[str] = field(default_factory=list)
    leves: list[str] = field(default_factory=list)
    preco_efetivo: float | None = None
    ref_depreciacao: float | None = None
    preco_original: float | None = None
    ano: int | None = None
    original_estimado: bool = True
    ref_comparaveis: float | None = None
    n_comparaveis: int = 0
    referencia: float | None = None
    desconto_pct: float | None = None                  # (referência − efetivo) / referência
    suspeito_iqr: str | None = None

    def para_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], 0.0) or k == "custo_reparo"}


def _brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def referencia_comparaveis(precos: list[float], cfg: ConfigUsados) -> tuple[float | None, int]:
    precos = [p for p in precos if p]
    if len(precos) < cfg.comparaveis_minimo:
        return None, len(precos)
    return float(statistics.median(precos)), len(precos)


def suspeito_por_iqr(preco: float, precos: list[float], cfg: ConfigUsados) -> str | None:
    precos = sorted(p for p in precos if p)
    if len(precos) < cfg.iqr_minimo:
        return None
    q1, _, q3 = statistics.quantiles(precos, n=4)
    limite = q1 - 1.5 * (q3 - q1)
    if preco < limite:
        return (f"preço muito abaixo de {len(precos)} anúncios parecidos na região "
                f"(normal a partir de ~{_brl(q1)})")
    return None


def calcular(preco: float | None, defeitos: list[dict], ano: int | None, preco_original: float | None,
             original_estimado: bool, precos_parecidos: list[float], cfg: ConfigUsados,
             hoje: datetime | None = None) -> CalculoUsado:
    c = CalculoUsado(ano=ano, preco_original=preco_original, original_estimado=original_estimado)
    for d in defeitos or []:
        nivel = (d.get("nivel") or "").lower()
        desc = d.get("descricao") or d.get("tipo") or "defeito"
        if nivel == "grave":
            c.graves.append(desc)
        elif nivel == "moderado":
            custo = cfg.custo(d.get("tipo") or desc)
            c.custo_reparo += custo
            c.reparos.append(f"{desc} (+{_brl(custo)})")
        elif nivel == "leve":
            c.leves.append(desc)
    if preco:
        c.preco_efetivo = preco + c.custo_reparo
    if preco_original and ano:
        idade = (hoje or datetime.now()).year - ano
        c.ref_depreciacao = round(preco_original * cfg.fator(idade), -1)
    c.ref_comparaveis, c.n_comparaveis = referencia_comparaveis(precos_parecidos, cfg)
    c.referencia = c.ref_comparaveis or c.ref_depreciacao
    if c.referencia and c.preco_efetivo:
        c.desconto_pct = (c.referencia - c.preco_efetivo) / c.referencia * 100
    if preco:
        c.suspeito_iqr = suspeito_por_iqr(preco, precos_parecidos, cfg)
    return c
