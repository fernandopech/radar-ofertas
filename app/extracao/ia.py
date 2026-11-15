"""Extração por IA (Claude Haiku) para ofertas que o leitor em código não entende.

Pede o JSON no próprio prompt e valida com Pydantic do nosso lado. (A saída
estruturada da API recusou o schema por complexidade e demorava pra compilar.)
"""
from __future__ import annotations

import logging
import os
import re
import time

import anthropic
from pydantic import ValidationError

from app.extracao.modelos import Specs
from app.ia_comum import TIMEOUT_S
from app.ia_comum import get_cliente as _get_cliente
from app.ia_comum import json_da_resposta as _json_da_resposta
from app.oferta import Oferta

log = logging.getLogger(__name__)

MODELO = os.getenv("MODELO_EXTRACAO", "claude-haiku-5-5")

MODELO_JSON = """{
  "eh_oferta_notebook": true,
  "modelo": "", "marca": "",
  "cpu": "", "gpu": "", "gpu_inferida": false,
  "ram_gb": null, "ram_expansivel": null, "ram_dual_channel": null,
  "armazenamento_gb": null, "tipo_armazenamento": "",
  "tela_pol": null, "tela_tipo": "",
  "sistema": "",
  "preco": null, "preco_parcelado": "", "cupom": "",
  "condicao": "desconhecido",
  "garantia_meses": null,
  "vendedor_tipo": "desconhecido",
  "loja": "", "link": ""
}"""

SISTEMA = f"""Você extrai dados de ofertas de notebook postadas em canais brasileiros de promoção.

Responda APENAS com um objeto JSON, sem texto antes ou depois, exatamente com estas chaves:
{MODELO_JSON}

Regras:
- Texto que a oferta não informa: "". Número ou sim/não que a oferta não informa: null. Nunca invente.
- modelo: o nome completo como aparece na oferta, incluindo a marca e, no fim, o código do produto
  se a oferta trouxer (ex.: "Lenovo IdeaPad Slim 3 15ARP10 83TYS00500", "VAIO FE16 VJFE69F11X-B1711H").
- Observações do post como "RAM soldada", "sem expansão", "2x8GB", "dual" valem para ram_expansivel
  e ram_dual_channel.
- cpu e gpu: como aparecem na oferta, sem "(Série 2)" ou "(13ª ger.)" (ex.: "Core 7-240H", "Ryzen 5 7535HS").
- eh_oferta_notebook = false para acessórios, monitores, consoles, avisos, vídeos, cupons genéricos.
- preco: o menor valor à vista em reais, como número (ex.: 3289.0). Se o preço anunciado é com cupom, use esse.
- ram_gb, armazenamento_gb, garantia_meses: inteiros. 1 TB = 1024 GB. 1 ano = 12 meses.
- armazenamento_gb é só o SSD principal. NÃO some HD ou segundo disco (ex.: "SSD 120 GB + HD 1 TB"
  → armazenamento_gb = 120, tipo_armazenamento = "SSD").
- tipo_armazenamento: "SSD", "HD", "eMMC" ou "eUFS" (eUFS anunciado como SSD continua sendo "eUFS").
- gpu: se a oferta não disser a GPU mas der um processador com gráfico integrado conhecido, pode deduzir
  (ex.: Ryzen 7 7840HS -> Radeon 780M; Ryzen 5 7535HS -> Radeon 660M) e marcar gpu_inferida = true.
  Se não tiver certeza, deixe "".
- sistema: "Windows", "Linux", "sem sistema", "macOS" ou "ChromeOS".
- condicao: "recondicionado" (recondicionado/renovado/vitrine/open box), "usado" (usado/seminovo),
  "novo" ou "desconhecido". Post de canal de promoção divulgando loja (preço à vista, parcelamento,
  cupom, garantia de fábrica) que não fala em usado/recondicionado é "novo".
- vendedor_tipo: "loja", "pessoa_fisica" ou "desconhecido".
- Anúncio de marketplace (OLX, Facebook) de particular: condicao "usado" (a não ser que diga
  novo/lacrado/na caixa com nota fiscal) e vendedor_tipo "pessoa_fisica". garantia_meses só se
  o anúncio disser que ainda tem garantia. Leia a descrição: specs costumam estar lá.
- cupom: o código do cupom, ou "sim" se exige cupom sem dizer o código.
- link: o link para comprar (prefira o da loja ao de sites de review)."""

def extrair_com_ia(oferta: Oferta) -> Specs | None:
    """Devolve None se a chamada falhar ou a resposta vier inválida (loga e segue)."""
    conteudo = oferta.texto
    if oferta.link:
        conteudo += f"\n\n[link principal: {oferta.link}]"
    inicio = time.monotonic()
    try:
        resposta = _get_cliente().messages.create(
            model=MODELO,
            max_tokens=4000,
            system=SISTEMA,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": conteudo}],
        )
    except anthropic.APITimeoutError:
        log.error("IA não respondeu em %.0fs para %s", TIMEOUT_S, oferta.id_externo)
        return None
    except anthropic.APIError as e:
        log.error("Falha na IA para %s: %s", oferta.id_externo, e)
        return None
    except Exception:  # sem chave configurada, rede etc.
        log.exception("Erro chamando a IA para %s", oferta.id_externo)
        return None

    uso = resposta.usage
    log.info("IA respondeu em %.1fs (%d tokens de entrada, %d de saída)",
             time.monotonic() - inicio, uso.input_tokens, uso.output_tokens)

    if resposta.stop_reason == "refusal":
        log.error("IA recusou %s", oferta.id_externo)
        return None
    texto = "".join(b.text for b in resposta.content if b.type == "text")
    try:
        return Specs.model_validate(_json_da_resposta(texto))
    except (ValueError, ValidationError) as e:  # JSONDecodeError é ValueError
        log.error("JSON inválido da IA para %s: %s | resposta: %s",
                  oferta.id_externo, e, re.sub(r"\s+", " ", texto)[:300])
        return None
