"""Regras duras: determinísticas, em código. Dado ausente nunca reprova sozinho."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.avaliacao.componentes import classificar
from app.avaliacao.criterios import Criterios
from app.avaliacao.regras_nomes import bate_com  # noqa: F401 (reexport p/ testes)
from app.extracao.modelos import Specs

@dataclass
class ResultadoRegras:
    passou: bool
    motivos: list[str] = field(default_factory=list)   # por que reprovou
    ausentes: list[str] = field(default_factory=list)  # dados que a oferta não trouxe
    so_preco: bool = False  # reprovou apenas pelo preço (margem de teste / oportunidade)
    classes: dict = field(default_factory=dict)  # nível de CPU/GPU/tela nas listas


def aplicar_regras(specs: Specs, texto: str, c: Criterios) -> ResultadoRegras:
    motivos: list[str] = []
    ausentes: list[str] = []
    motivo_preco = None

    if specs.preco is None:
        ausentes.append("preço")
    elif specs.preco > c.preco_max:
        motivo_preco = f"preço R$ {specs.preco:,.0f} > R$ {c.preco_max:,.0f}".replace(",", ".")

    if specs.ram_gb is None:
        ausentes.append("RAM")
    elif specs.ram_gb < c.ram_min_gb:
        motivos.append(f"RAM {specs.ram_gb} GB < {c.ram_min_gb} GB")

    if specs.armazenamento_gb is None:
        ausentes.append("armazenamento")
    elif specs.armazenamento_gb < c.armazenamento_min_gb:
        motivos.append(f"armazenamento {specs.armazenamento_gb} GB < {c.armazenamento_min_gb} GB")

    if not specs.tipo_armazenamento:
        ausentes.append("tipo de armazenamento")
    elif specs.tipo_armazenamento.upper() != c.tipo_armazenamento.upper():
        motivos.append(f"armazenamento {specs.tipo_armazenamento}, não {c.tipo_armazenamento}")

    if specs.tela_pol is None:
        ausentes.append("tamanho da tela")
    elif not (c.tela_pol_min <= specs.tela_pol <= c.tela_pol_max):
        motivos.append(f"tela {specs.tela_pol:g}\" fora de {c.tela_pol_min:g}–{c.tela_pol_max:g}\"")

    if not specs.sistema:
        ausentes.append("sistema")
    elif specs.sistema.lower() not in {s.lower() for s in c.sistemas_aceitos}:
        motivos.append(f"sistema {specs.sistema}")

    classes = classificar(specs.cpu, specs.gpu, specs.tela_tipo, c)
    if not specs.cpu:
        ausentes.append("CPU")
    elif classes["cpu"].nivel == "excluir":
        motivos.append(f"CPU fraca ({classes['cpu'].termo})")

    if not specs.gpu:
        ausentes.append("GPU")
    elif classes["gpu"].nivel == "excluir":
        motivos.append(f"GPU fraca ({classes['gpu'].termo})")

    texto_l = texto.lower()
    if termo := next((t for t in c.excluir_termos if t.lower() in texto_l), None):
        motivos.append(f"termo excluído: {termo}")

    if specs.condicao == "recondicionado" and specs.garantia_meses is not None and specs.garantia_meses < 3:
        motivos.append(f"recondicionado com só {specs.garantia_meses} mês(es) de garantia")

    so_preco = motivo_preco is not None and not motivos
    if motivo_preco:
        motivos.insert(0, motivo_preco)
    return ResultadoRegras(passou=not motivos, motivos=motivos, ausentes=ausentes,
                           so_preco=so_preco, classes=classes)
