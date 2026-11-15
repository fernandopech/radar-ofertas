"""Fonte OLX: anúncios de notebook da Grande Porto Alegre via API omkarcloud (RapidAPI).

A cada `intervalo_min`: 1 busca (RS inteiro, categoria Notebooks, mais recentes, faixa de
preço) → filtra as cidades da região metropolitana no código → busca os detalhes (descrição)
só dos anúncios novos → entrega ao pipeline como Oferta.

Economia de consultas (plano grátis = 1.000/mês): anúncios já gravados no banco não têm
os detalhes buscados de novo; títulos claramente fora do perfil são pulados antes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.fontes.base import AoReceber, Fonte
from app.oferta import Oferta

log = logging.getLogger(__name__)

HOST_PADRAO = "best-olx-brazil-scraper-free-1000-calls.p.rapidapi.com"
# Pula antes de gastar consulta de detalhes: fora do perfil (sem Mac/Chromebook, sucata).
_PULAR_SEMPRE = (r"\bimac\b|ipad|tablet|pe[çc]as|defeito|quebrad|sucata|n[aã]o liga|"
                 r"retirada|carca[çc]a|placa[\s-]m[aã]e|tela\s+(para|de)\s+notebook|bateria\s+(para|de)")
# Sistema fora de sistemas_aceitos → título que já denuncia o sistema é pulado.
_POR_SISTEMA = {"macos": r"macbook", "chromeos": r"chromebook"}


def regex_pular(sistemas_aceitos: list[str]) -> re.Pattern:
    aceitos = {s.lower() for s in sistemas_aceitos}
    extras = [rx for sistema, rx in _POR_SISTEMA.items() if sistema not in aceitos]
    return re.compile("|".join([_PULAR_SEMPRE, *extras]), re.I)


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


@dataclass
class ConfigOlx:
    chave: str
    cidades: list[str]
    intervalo_min: float = 120
    preco_min: float = 1500
    preco_max: float = 5500
    saldo_minimo: int = 60
    host: str = HOST_PADRAO
    sistemas_aceitos: list[str] = field(default_factory=lambda: ["Windows", "Linux", "sem sistema"])
    estado: str = "rs"
    categoria: str = "informatica/notebooks"
    _cidades_norm: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self._cidades_norm = {_sem_acento(c) for c in self.cidades}

    def cidade_ok(self, municipio: str | None) -> bool:
        return bool(municipio) and _sem_acento(municipio) in self._cidades_norm

    @classmethod
    def carregar(cls, bruto: dict[str, Any]) -> "ConfigOlx | None":
        """None se a OLX estiver desligada ou sem chave (aí o monitor roda só com o Telegram)."""
        o = bruto.get("olx") or {}
        chave = os.getenv("RAPIDAPI_KEY", "").strip()
        if not o.get("ativo") or not chave:
            return None
        return cls(chave=chave, cidades=list(o.get("cidades") or []),
                   intervalo_min=float(o.get("intervalo_min", 120)),
                   preco_min=float(o.get("preco_min", 1500)), preco_max=float(o.get("preco_max", 5500)),
                   saldo_minimo=int(o.get("saldo_minimo", 60)),
                   sistemas_aceitos=list((bruto.get("regras_duras") or {}).get("sistemas_aceitos") or []))


class ClienteOlx:
    def __init__(self, cfg: ConfigOlx):
        self.cfg = cfg
        self.saldo: int | None = None  # consultas restantes no mês (cabeçalho do RapidAPI)

    def _get(self, caminho: str, **params: Any) -> dict:
        url = f"https://{self.cfg.host}{caminho}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"X-RapidAPI-Key": self.cfg.chave,
                                                   "X-RapidAPI-Host": self.cfg.host})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                restantes = r.headers.get("x-ratelimit-requests-remaining")
                if restantes and restantes.isdigit():
                    self.saldo = int(restantes)
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OLX API {e.code} em {caminho}: {e.read().decode()[:300]}") from None

    def buscar(self, pagina: int = 1) -> list[dict]:
        params = dict(query="notebook", category=self.cfg.categoria, location=self.cfg.estado,
                      sort="newest", price_min=int(self.cfg.preco_min), price_max=int(self.cfg.preco_max))
        if pagina > 1:
            params["page"] = pagina
        corpo = self._get("/ads/search", **params)
        for chave in ("results", "ads", "data", "items"):
            if isinstance(corpo.get(chave), list):
                return corpo[chave]
        return []

    def detalhes(self, ad_id: str) -> dict:
        return self._get("/ads/details", ad=ad_id)


def _preco(ad: dict) -> float | None:
    p = ad.get("price")
    valor = p.get("amount") if isinstance(p, dict) else p
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _atributos(ad: dict) -> list[str]:
    linhas = []
    for a in ad.get("attributes") or []:
        if isinstance(a, dict):
            rotulo = a.get("label") or a.get("name") or a.get("key")
            valor = a.get("value_label") or a.get("value") or a.get("values")
            if rotulo and valor:
                linhas.append(f"{rotulo}: {valor}")
    return linhas


def _data(ad: dict) -> datetime:
    bruto = ad.get("posted_at") or ""
    try:
        return datetime.fromisoformat(bruto.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def anuncio_para_oferta(ad: dict, det: dict | None) -> Oferta:
    det = det or {}
    loc = det.get("location") or ad.get("location") or {}
    municipio, bairro = loc.get("municipality"), loc.get("neighbourhood")
    preco = _preco(det) or _preco(ad)
    profissional = det.get("is_professional", ad.get("is_professional"))
    vendedor = "loja/profissional" if profissional else "particular (pessoa física)"
    descricao = det.get("description") or det.get("body") or ""
    partes = [
        f"Anúncio da OLX: {ad.get('title') or det.get('title')}",
        f"Preço: R$ {preco:,.0f}".replace(",", ".") if preco else "Preço: não informado",
        f"Local: {', '.join(x for x in (bairro, municipio) if x)}",
        f"Vendedor: {vendedor}",
        *_atributos(det or ad),
    ]
    if descricao:
        partes += ["", "Descrição do vendedor:", descricao.strip()[:2500]]
    preco_id = int(preco) if preco else 0
    return Oferta(
        fonte="olx:grande-poa",
        # id + preço: se o vendedor baixar o preço, vira uma oferta nova (e o dedup avisa a queda)
        id_externo=f"{ad.get('id')}@{preco_id}",
        texto="\n".join(partes),
        recebida_em=_data(ad),
        link=ad.get("link") or det.get("link"),
        link_origem=ad.get("link") or det.get("link"),
        tem_imagem=bool(ad.get("image_count")),
        condicao=None,
        categoria_confirmada=True,
        local=", ".join(x for x in (bairro, municipio) if x) or None,
    )


class FonteOlx(Fonte):
    nome = "olx"

    def __init__(self, cfg: ConfigOlx, ja_existe: Callable[[str, str], bool] | None = None):
        self.cfg = cfg
        self.cliente = ClienteOlx(cfg)
        self.ja_existe = ja_existe or (lambda fonte, id_externo: False)
        self.vistos: set[str] = set()
        self.ultima_busca: list[dict] = []
        self.pular = regex_pular(cfg.sistemas_aceitos)

    def ciclo(self, pagina: int = 1) -> list[Oferta]:
        """Uma rodada síncrona: busca, filtra região, pega detalhes dos novos."""
        if self.cliente.saldo is not None and self.cliente.saldo < self.cfg.saldo_minimo:
            log.warning("OLX: só %d consultas restantes no mês; pausando a OLX", self.cliente.saldo)
            return []
        ads = self.cliente.buscar(pagina)
        self.ultima_busca = ads
        novas: list[Oferta] = []
        na_regiao = 0
        for ad in ads:
            loc = ad.get("location") or {}
            if not self.cfg.cidade_ok(loc.get("municipality")):
                continue
            na_regiao += 1
            preco = _preco(ad)
            id_externo = f"{ad.get('id')}@{int(preco) if preco else 0}"
            if id_externo in self.vistos:
                continue
            self.vistos.add(id_externo)
            if self.pular.search(ad.get("title") or ""):
                continue
            try:
                if self.ja_existe("olx:grande-poa", id_externo):
                    continue
            except Exception:
                log.exception("Banco indisponível no dedup da OLX; seguindo")
            if self.cliente.saldo is not None and self.cliente.saldo < self.cfg.saldo_minimo:
                break
            try:
                det = self.cliente.detalhes(str(ad.get("id")))
            except Exception:
                log.exception("OLX: falha nos detalhes de %s; usando só a busca", ad.get("id"))
                det = None
            novas.append(anuncio_para_oferta(ad, det))
        log.info("OLX: %d anúncios na busca, %d na região, %d novos · saldo %s",
                 len(ads), na_regiao, len(novas), self.cliente.saldo)
        return novas

    async def executar(self, ao_receber: AoReceber, recuperar: int = 0) -> None:
        log.info("OLX: buscando a cada %g min (Grande Porto Alegre, R$ %.0f a %.0f)",
                 self.cfg.intervalo_min, self.cfg.preco_min, self.cfg.preco_max)
        while True:
            try:
                novas = await asyncio.to_thread(self.ciclo)
                for oferta in sorted(novas, key=lambda o: o.recebida_em):
                    await ao_receber(oferta)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("OLX: erro no ciclo; tento de novo no próximo")
            await asyncio.sleep(self.cfg.intervalo_min * 60)
