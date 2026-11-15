"""Etapa 2: a IA avalia os critérios subjetivos e dá uma nota de 0 a 10."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Literal

import anthropic
import yaml
from pydantic import BaseModel, Field, ValidationError

from app.avaliacao.criterios import Criterios
from app.enriquecimento import Ficha
from app.extracao.modelos import Specs
from app.ia_comum import TIMEOUT_S
from app.ia_comum import get_cliente as _get_cliente
from app.ia_comum import json_da_resposta as _json_da_resposta

log = logging.getLogger(__name__)

MODELO = os.getenv("MODELO_AVALIACAO", "claude-haiku-5-5")


class Avaliacao(BaseModel):
    nota: float = Field(ge=0, le=10)
    aprovado: bool = False  # opinião da IA; a decisão final é do código (nota mínima)
    roda_cs2: Literal["sim", "provavelmente", "nao"]
    pontos_fortes: list[str] = []
    pontos_fracos: list[str] = []
    incertezas: list[str] = []
    resumo: str = ""
    # comprar_agora | esperar | nao_compensa (vazio em avaliações antigas)
    veredito: Literal["comprar_agora", "esperar", "nao_compensa", ""] = ""
    por_que: str = ""  # uma frase curta justificando o veredito
    alerta_golpe: str = ""  # sinais de golpe/defeito escondido, se houver (usados de marketplace)
    # Só usados de marketplace:
    defeitos: list[dict] = []          # [{"descricao", "nivel": grave|moderado|leve, "tipo"}]
    ano_lancamento: int | None = None  # ano em que o modelo/geração foi lançado
    preco_original: float | None = None  # preço de lançamento estimado, em R$


def montar_sistema(c: Criterios) -> str:
    b = c.bruto
    contexto = {
        "uso_principal": b["criterios_subjetivos"]["uso_principal"],
        "desejavel": b["criterios_subjetivos"]["desejavel"],
        "indiferente": b["criterios_subjetivos"].get("indiferente", []),
        "evitar": b["criterios_subjetivos"]["evitar"],
        "listas_de_componentes": {k: v for k, v in (b.get("componentes") or {}).items()},
        "condicao": b["condicao"],
    }
    return f"""Você avalia ofertas de notebook para UMA pessoa que quer comprar um só notebook.
As regras duras (preço, RAM mínima, SSD, tela, CPU/GPU fracas) já foram checadas em código:
a oferta que chega aqui passou nelas ou faltou dado. Seu trabalho é julgar o resto.

Perfil e preferências (YAML):
{yaml.safe_dump(contexto, allow_unicode=True, sort_keys=False)}
Contexto dos jogos:
{b.get("contexto_jogos", "")}

Como dar a nota (0 a 10):
- 10 = compra excelente pro perfil; 7 = boa e vale a notificação; abaixo de 7 = não vale.
- roda_cs2: avalie com rigor. "sim" só se rodar CS2 em 1080p médio acima de 60 FPS com folga
  (piso: Radeon 780M em dual-channel, Arc 140T/140V, ou dedicada RTX/RX/GTX 1650 ou superior).
  Na dúvida, "provavelmente".
  Fora do Mac, CS2 é exigência e já é checado em código: não cite CS2 nos pontos nem no por_que.
- MacBook/macOS é aceito pela pessoa sabendo que CS2 não roda: para Mac, roda_cs2 = "nao" e isso NÃO
  é ponto fraco nem reduz a nota. Avalie Mac por programação, abas, IA local (memória unificada),
  bateria, tela e preço. Mac com 8 GB é fraco pro perfil.
- Pese: RAM expansível e em dual-channel,
  preço x configuração, tela (IPS, Full HD+, brilho >= 300 nits é bom), bateria e peso (bônus).
- Gráfico integrado com pente único de RAM perde muito desempenho: penalize.
- Listas de componentes da pessoa: "excelente" > "boa" > "ok" > "fraca". GPU "fraca" roda CS2
  abaixo de 60 FPS em 1080p (roda_cs2 = "provavelmente" ou "nao"). "fora das listas": julgue você.
- Custo-benefício: se vier o preço justo de mercado, use. Bem abaixo da faixa = ponto forte;
  acima da faixa = ponto fraco. Sem essa referência, compare com o que a configuração costuma custar.
- Se um dado não foi informado, NÃO invente: liste em "incertezas" e julgue com o que tem.
  Você pode deduzir a GPU integrada pelo processador, mas diga que deduziu.
- Usado de pessoa física: deixe claro que não tem garantia.
- Windows, Linux ou sem sistema são todos aceitos pela pessoa: sistema não é ponto fraco.
- Não comente o teto de preço: ele já foi checado em código. Avalie preço x configuração.

Responda APENAS com um objeto JSON, sem texto antes ou depois:
{{"nota": 0, "aprovado": false, "roda_cs2": "sim | provavelmente | nao",
  "pontos_fortes": [], "pontos_fracos": [], "incertezas": [], "resumo": "",
  "veredito": "comprar_agora | esperar | nao_compensa", "por_que": "", "alerta_golpe": "",
  "defeitos": [], "ano_lancamento": null, "preco_original": null}}
(defeitos, ano_lancamento e preco_original: só preencha para usado de marketplace; senão [] e null.)
Veredito (a pessoa vai ler isso primeiro no celular):
- "comprar_agora": atende bem o perfil E o preço está bom (abaixo ou dentro do preço justo, sem
  sinal de que vá cair logo). Oferta assim costuma acabar rápido.
- "esperar": bom notebook, mas o preço está no limite/acima do justo, ou há dúvida importante
  (ex.: dual-channel não confirmado). Vale acompanhar.
- "nao_compensa": não atende bem o perfil, mesmo passando nas regras.
"alerta_golpe": só para usado de marketplace (OLX/Facebook). Se houver sinal de golpe ou defeito
escondido (preço muito abaixo do normal pra essa configuração, só PIX/pagamento antecipado, pressa,
"sem nota" com preço irreal, descrição genérica copiada, peças/defeito citados de passagem), descreva
em uma frase curta. Senão, "". Não invente alerta.
"por_que": uma frase de até ~15 palavras que justifique o veredito (ex.: "RTX 3050 e 16 GB
dual-channel por 14% abaixo do preço justo").
Listas: no máximo 4 pontos fortes, 3 fracos e 3 incertezas, os que mais pesam pro perfil.
Incerteza é só dado ausente que mudaria a nota (ex.: GPU, RAM soldada, tipo de tela);
não liste parcelamento, cupom, tipo de garantia etc. Itens curtos (até ~8 palavras),
em português. "resumo": uma frase."""


def descrever_ram(f: Ficha) -> str:
    soldada = f"{f.ram_soldada_gb} GB soldados na placa" if f.ram_soldada_gb else "nada soldado"
    pentes = [s for s in f.ram_slots if "vazio" not in s.lower()]
    vazios = sum(1 for s in f.ram_slots if "vazio" in s.lower())
    partes = [soldada]
    if pentes:
        partes.append(f"pente(s) de {', '.join(pentes)}")
    if vazios:
        partes.append(f"{vazios} slot(s) vazio(s) para adicionar pente")
    dual = {True: "roda em dual-channel",
            False: "pente único: roda em single-channel",
            None: "dual-channel provável (memória soldada costuma ser), mas não confirmado"}
    expans = "expansível" if f.ram_expansivel else "não expansível"
    return f"{' + '.join(partes)}; {dual[f.ram_dual_channel]}; {expans}"


def instrucoes_usado(c: Criterios) -> str:
    u = (c.bruto.get("usados") or {})
    d = u.get("defeitos") or {}
    tipos = ", ".join(f'"{t}"' for t in (d.get("moderado") or {}))
    return f"""
ESTE É UM USADO DE MARKETPLACE. Regras extras:
- NÃO trate "usado" ou "sem garantia" como ponto fraco nem tire nota por isso: a pessoa aceita
  usado, e esse risco já é tratado à parte. Compare com OUTROS USADOS, não com novo de loja.
- Classifique cada defeito que o vendedor ESCREVEU (não invente) em "defeitos":
  grave (reprova): {"; ".join(d.get("grave") or [])}
  moderado (o custo de reparo é somado ao preço em código; NÃO desconte nota por ele):
    use "tipo" exatamente um destes: {tipos}
  leve (só informativo): {"; ".join(d.get("leve") or [])}
  Formato: {{"descricao": "bateria dura 1h", "nivel": "moderado", "tipo": "bateria viciada ou fraca"}}
- ano_lancamento: ano de lançamento do modelo/geração (pela geração do processador/GPU), ou null.
- preco_original: preço de lançamento aproximado no Brasil em R$ (número), ou null se não souber.
- Julgue o preço pelo "preço efetivo" (preço + reparos) contra a referência de usados do Contexto."""


def montar_usuario(specs: Specs, ficha: Ficha | None, ausentes: list[str], obs_regras: list[str],
                   texto_anuncio: str | None = None) -> str:
    partes = []
    if texto_anuncio:
        partes += ["Anúncio original (marketplace):", texto_anuncio[:3000], ""]
    partes += ["Oferta (dados extraídos):", json.dumps(specs.model_dump(exclude={"link"}), ensure_ascii=False, indent=1)]
    if ficha and ficha.campos:
        partes += ["", "Ficha técnica completa do modelo (site Qual Notebook Comprar):"]
        # Muitos valores já trazem o rótulo ("Peso: 1,40 kg"); não repete.
        partes += [f"- {v}" if re.match(r"[^\W\d][^:]*:\s", v) else f"- {k}: {v}"
                   for k, v in ficha.campos.items()]
        if ficha.ram_expansivel is not None:
            partes.append(f"- resumo da RAM (deduzido da ficha): {descrever_ram(ficha)}")
    else:
        partes += ["", "Não há ficha técnica completa; avalie só com a oferta."]
    if ficha and ficha.loja:
        partes.append(f"Loja: {ficha.loja}")
    if ausentes:
        partes.append(f"Dados ausentes na oferta: {', '.join(ausentes)}")
    if obs_regras:
        partes += ["", "Contexto:"] + [f"- {linha}" for linha in obs_regras]
    return "\n".join(partes)


def avaliar_com_ia(specs: Specs, ficha: Ficha | None, ausentes: list[str], c: Criterios,
                   obs_regras: list[str] | None = None, texto_anuncio: str | None = None) -> Avaliacao | None:
    inicio = time.monotonic()
    try:
        resposta = _get_cliente().messages.create(
            model=MODELO,
            max_tokens=4000,
            system=montar_sistema(c) + (instrucoes_usado(c) if texto_anuncio else ""),
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": montar_usuario(specs, ficha, ausentes, obs_regras or [], texto_anuncio)}],
        )
    except anthropic.APITimeoutError:
        log.error("Avaliação: IA não respondeu em %.0fs (%s)", TIMEOUT_S, specs.modelo)
        return None
    except anthropic.APIError as e:
        log.error("Avaliação: falha na IA (%s): %s", specs.modelo, e)
        return None
    except Exception:
        log.exception("Avaliação: erro chamando a IA (%s)", specs.modelo)
        return None

    uso = resposta.usage
    log.info("Avaliação em %.1fs (%d tokens de entrada, %d de saída)",
             time.monotonic() - inicio, uso.input_tokens, uso.output_tokens)
    if resposta.stop_reason == "refusal":
        log.error("Avaliação: IA recusou (%s)", specs.modelo)
        return None
    texto = "".join(b.text for b in resposta.content if b.type == "text")
    try:
        dados = _json_da_resposta(texto)
        v = str(dados.get("veredito", "")).strip().lower().replace(" ", "_").replace("ã", "a")
        dados["veredito"] = v if v in {"comprar_agora", "esperar", "nao_compensa"} else ""
        if isinstance(dados.get("roda_cs2"), str):
            dados["roda_cs2"] = dados["roda_cs2"].strip().lower().replace("ã", "a")
        if not isinstance(dados.get("defeitos"), list):
            dados["defeitos"] = []
        dados["defeitos"] = [d for d in dados["defeitos"] if isinstance(d, dict)]
        for campo, tipo in (("ano_lancamento", int), ("preco_original", float)):
            try:
                dados[campo] = tipo(dados[campo]) if dados.get(campo) not in (None, "") else None
            except (TypeError, ValueError):
                dados[campo] = None
        return Avaliacao.model_validate(dados)
    except (ValueError, ValidationError) as e:
        log.error("Avaliação: JSON inválido (%s): %s | %s", specs.modelo, e, re.sub(r"\s+", " ", texto)[:300])
        return None
