"""Etapa de avaliação: regras duras → ficha completa → IA → decisão.

Caminhos para notificar:
  - normal: passou nas regras duras e a nota da IA ≥ nota mínima;
  - oportunidade: só estourou o teto, está abaixo do teto absoluto, pelo menos
    X% abaixo do preço justo de mercado, e a nota da IA ≥ nota mínima.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.avaliacao.componentes import classificar_tela
from app.avaliacao.criterios import Criterios
from app.avaliacao.ia import Avaliacao, avaliar_com_ia
from app.avaliacao.regras import ResultadoRegras, aplicar_regras
from app.avaliacao.usados import CalculoUsado, ConfigUsados, calcular
from app.dedup import _gpu_curta
from app.enriquecimento import Ficha, enriquecer
from app.extracao.modelos import Specs
from app.oferta import Oferta

__all__ = ["Criterios", "Resultado", "avaliar"]

LIMITE_SUSPEITO = 0.45  # usado abaixo de 45% do preço justo do novo = suspeito


@dataclass
class Resultado:
    regras: ResultadoRegras
    ficha: Ficha | None = None
    avaliacao: Avaliacao | None = None
    aprovado: bool = False
    oportunidade: bool = False     # fora do teto, mas bem abaixo do preço justo
    desconto_pct: float | None = None  # % abaixo (+) ou acima (-) do preço justo mínimo
    na_margem: bool = False        # só calibração: estourou o preço, dentro da margem de teste
    motivo: str = ""               # frase curta pra tabela
    contexto: list[str] = field(default_factory=list)  # linhas extras enviadas à IA
    suspeito: str | None = None    # alerta de possível golpe (regra de preço ou IA)
    usado: CalculoUsado | None = None  # marketplace: reparos, preço efetivo e referências


def nota_minima(specs: Specs, c: Criterios) -> float:
    if specs.condicao == "usado" or specs.vendedor_tipo == "pessoa_fisica":
        return max(c.nota_minima, c.nota_minima_usado)
    return c.nota_minima


def _brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


# (gpu curta, ram) → preços de usados parecidos na região (vem do banco, via Monitor)
Comparaveis = Callable[[str, int], list[float]]


def avaliar(oferta: Oferta, specs: Specs, c: Criterios, *, usar_ia: bool = True,
            usar_site: bool = True, margem_preco: float = 0,
            comparaveis: Comparaveis | None = None) -> Resultado:
    regras = aplicar_regras(specs, oferta.texto, c)
    preco = specs.preco
    na_margem = regras.so_preco and preco is not None and preco <= c.preco_max + margem_preco
    candidata_oportunidade = (c.oportunidade_ativa and regras.so_preco and preco is not None
                              and preco <= c.oportunidade_preco_max)
    if not regras.passou and not (na_margem or candidata_oportunidade):
        return Resultado(regras, motivo="; ".join(regras.motivos))

    r = Resultado(regras, na_margem=na_margem)

    if usar_site:
        r.ficha = enriquecer(oferta, specs.link, specs.modelo)
        # Ficha do site completa os dados que a mensagem não traz.
        if r.ficha.ram_expansivel is not None and specs.ram_expansivel is None:
            specs = specs.model_copy(update={"ram_expansivel": r.ficha.ram_expansivel,
                                             "ram_dual_channel": r.ficha.ram_dual_channel})
        if r.ficha.loja and not specs.loja:
            specs = specs.model_copy(update={"loja": r.ficha.loja})
        # Tela: junta o que a oferta diz com o painel/frequência da ficha.
        tela = " ".join([specs.tela_tipo] + [r.ficha.campos.get(k, "") for k in
                                             ("painel", "resolução", "taxa de atualização")])
        regras.classes["tela"] = classificar_tela(tela, c.componentes.get("tela", {}))

    # Preço de mercado
    if r.ficha and r.ficha.preco_justo_min and preco:
        r.desconto_pct = (r.ficha.preco_justo_min - preco) / r.ficha.preco_justo_min * 100
        abaixo = "abaixo" if r.desconto_pct >= 0 else "acima"
        r.contexto.append(
            f"Preço justo deste modelo (histórico do site Qual Notebook Comprar): "
            f"{_brl(r.ficha.preco_justo_min)} a {_brl(r.ficha.preco_justo_max)}. "
            f"Esta oferta está {abs(r.desconto_pct):.0f}% {abaixo} do mínimo da faixa.")
    # Anti-golpe (ideia do radar-de-achados): usado de particular muito abaixo do preço do novo.
    usado_particular = specs.condicao == "usado" or specs.vendedor_tipo == "pessoa_fisica"
    if usado_particular and r.ficha and r.ficha.preco_justo_min and preco and \
            preco < r.ficha.preco_justo_min * LIMITE_SUSPEITO:
        r.suspeito = (f"custa {preco / r.ficha.preco_justo_min:.0%} do preço do novo "
                      f"({_brl(r.ficha.preco_justo_min)}): barato demais pra um usado")
    r.oportunidade = bool(candidata_oportunidade and r.desconto_pct is not None
                          and r.desconto_pct >= c.oportunidade_desconto_min_pct)

    if not regras.passou and not (r.oportunidade or na_margem):
        if r.desconto_pct is None:
            ref = "sem preço de mercado pra comparar"
        elif r.desconto_pct >= 0:
            ref = f"só {r.desconto_pct:.1f}% abaixo do preço justo (mín. {c.oportunidade_desconto_min_pct:g}%)"
        else:
            ref = f"{-r.desconto_pct:.1f}% ACIMA do preço justo"
        r.motivo = f"{regras.motivos[0]}; {ref}"
        return r

    cl = regras.classes
    tela_txt = ", ".join(f"{n}: {', '.join(t)}" for n, t in cl.get("tela", {}).items()) or "fora das listas"
    r.contexto.insert(0, f"Classificação pelas listas da pessoa: GPU = {cl.get('gpu')}; "
                         f"CPU = {cl.get('cpu')}; tela = {tela_txt}.")

    if not usar_ia:
        r.motivo = "oportunidade (IA desligada)" if r.oportunidade else "passou nas regras (IA desligada)"
        return r

    marketplace = oferta.categoria_confirmada
    cfg_usados = ConfigUsados.carregar(c.bruto)
    precos_parecidos: list[float] = []
    if marketplace and comparaveis and specs.gpu and specs.ram_gb:
        try:
            precos_parecidos = [p for p in comparaveis(_gpu_curta(specs.gpu), specs.ram_gb) if p]
        except Exception:
            precos_parecidos = []
        if len(precos_parecidos) >= cfg_usados.comparaveis_minimo:
            import statistics
            med = statistics.median(precos_parecidos)
            r.contexto.append(
                f"Referência de usados: mediana de {_brl(med)} em {len(precos_parecidos)} anúncios "
                f"parecidos (mesma GPU e RAM) na região nos últimos {cfg_usados.comparaveis_dias} dias.")
        elif marketplace:
            r.contexto.append("Poucos usados parecidos no histórico: estime o valor de usado pela "
                              "idade do modelo (fatores: " + ", ".join(
                                  f"{a} ano(s) = {f:.0%}" for a, f in sorted(cfg_usados.depreciacao.items()))
                              + " do preço de lançamento).")

    texto = oferta.texto if marketplace else None  # marketplace: IA lê a descrição
    r.avaliacao = avaliar_com_ia(specs, r.ficha, regras.ausentes, c, r.contexto, texto)
    if r.avaliacao is None:
        r.motivo = "IA falhou"
        return r
    if r.avaliacao.alerta_golpe and not r.suspeito:
        r.suspeito = r.avaliacao.alerta_golpe
    defeito_grave = None
    if marketplace:
        r.usado = calcular(preco, r.avaliacao.defeitos, r.avaliacao.ano_lancamento,
                           r.avaliacao.preco_original, True, precos_parecidos, cfg_usados)
        if r.usado.suspeito_iqr and not r.suspeito:
            r.suspeito = r.usado.suspeito_iqr
        if r.usado.graves:
            defeito_grave = r.usado.graves[0]
    minima = nota_minima(specs, c)
    nota_ok = r.avaliacao.nota >= minima
    # A curadoria é o ponto: se a IA diz que não compensa, não notifica, mesmo com nota alta.
    nao_compensa = r.avaliacao.veredito == "nao_compensa"
    # CS2 é exigência interna (não aparece na mensagem): fora do Mac, só "sim" passa.
    eh_mac = "mac" in (specs.sistema or "").lower() or "macbook" in (specs.modelo or "").lower()
    sem_cs2 = c.exigir_cs2 and not eh_mac and r.avaliacao.roda_cs2 != "sim"
    r.aprovado = (nota_ok and not nao_compensa and not sem_cs2 and not defeito_grave
                  and not (marketplace and r.suspeito) and (regras.passou or r.oportunidade))
    r.motivo = f"nota {r.avaliacao.nota:g} {'≥' if nota_ok else '<'} {minima:g}"
    if nao_compensa:
        r.motivo += " · IA: não compensa"
    if sem_cs2:
        r.motivo += f" · CS2: {r.avaliacao.roda_cs2} (precisa ser sim)"
    if defeito_grave:
        r.motivo += f" · defeito grave: {defeito_grave}"
    if marketplace and r.suspeito:
        r.motivo += " · suspeita de golpe"
    if r.oportunidade:
        r.motivo += f" · OPORTUNIDADE: {r.desconto_pct:.0f}% abaixo do preço justo"
    return r
