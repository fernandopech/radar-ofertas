"""Gravação no Supabase via API REST (PostgREST), com a chave secreta do backend.

A tabela tem RLS ligado e nenhuma política pública: só a chave secreta acessa.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.config import ConfigFaltando

log = logging.getLogger(__name__)


class ErroBanco(RuntimeError):
    pass


class Banco:
    def __init__(self, url: str | None = None, chave: str | None = None):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.chave = chave or os.getenv("SUPABASE_KEY", "")
        faltando = [n for n, v in (("SUPABASE_URL", self.url), ("SUPABASE_KEY", self.chave)) if not v]
        if faltando:
            raise ConfigFaltando(
                f"{' e '.join(faltando)} vazio(s). Preencha no .env (o git pull não atualiza o .env; "
                f"veja o .env.example). A chave é a secreta: sb_secret_...")
        if self.chave.startswith("sb_publishable_"):
            raise ConfigFaltando("SUPABASE_KEY é a chave pública; use a secreta (sb_secret_...).")

    def _req(self, metodo: str, caminho: str, corpo: Any = None, prefer: str | None = None) -> Any:
        headers = {"apikey": self.chave, "Content-Type": "application/json"}
        if self.chave.startswith("eyJ"):  # chave antiga (JWT service_role)
            headers["Authorization"] = f"Bearer {self.chave}"
        if prefer:
            headers["Prefer"] = prefer
        dados = json.dumps(corpo, ensure_ascii=False, default=str).encode() if corpo is not None else None
        req = urllib.request.Request(f"{self.url}/rest/v1/{caminho}", data=dados, method=metodo, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                texto = r.read().decode()
        except urllib.error.HTTPError as e:
            raise ErroBanco(f"{e.code} em {metodo} {caminho}: {e.read().decode()[:500]}") from None
        except urllib.error.URLError as e:
            raise ErroBanco(f"sem conexão com o Supabase: {e.reason}") from None
        return json.loads(texto) if texto else None

    def ja_existe(self, fonte: str, id_externo: str) -> bool:
        q = urllib.parse.urlencode({"select": "id", "fonte": f"eq.{fonte}",
                                    "id_externo": f"eq.{id_externo}", "limit": "1"})
        return bool(self._req("GET", f"ofertas?{q}"))

    def gravar(self, registro: dict[str, Any]) -> int:
        """Insere ou atualiza (mesma fonte + id_externo). Devolve o id."""
        linhas = self._req("POST", "ofertas?on_conflict=fonte,id_externo", registro,
                           prefer="resolution=merge-duplicates,return=representation")
        return linhas[0]["id"]

    def marcar_notificado(self, id_oferta: int, quando: str) -> None:
        self.anotar(id_oferta, {"notificado_em": quando})

    def anotar(self, id_oferta: int, campos: dict[str, Any]) -> None:
        self._req("PATCH", f"ofertas?id=eq.{id_oferta}", campos, prefer="return=minimal")

    def ultima_notificacao(self, chave_modelo: str, desde_iso: str) -> float | None:
        """Preço da notificação mais recente desse modelo desde `desde_iso`, ou None."""
        q = urllib.parse.urlencode({"select": "preco", "chave_modelo": f"eq.{chave_modelo}",
                                    "notificado_em": f"gte.{desde_iso}",
                                    "order": "notificado_em.desc", "limit": "1"})
        linhas = self._req("GET", f"ofertas?{q}") or []
        preco = linhas[0]["preco"] if linhas else None
        return float(preco) if preco is not None else None

    def precos_comparaveis(self, gpu_curta: str, ram_gb: int, dias: int = 30) -> list[float]:
        """Preços de usados de marketplace com a mesma GPU e RAM (pela chave_modelo)."""
        from datetime import datetime, timedelta, timezone
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        q = urllib.parse.urlencode({"select": "preco", "fonte": "like.olx*",
                                    "chave_modelo": f"like.*|{gpu_curta}|{ram_gb}|*",
                                    "recebida_em": f"gte.{desde}", "limit": "500"})
        return [float(l["preco"]) for l in (self._req("GET", f"ofertas?{q}") or []) if l.get("preco")]

    def quase_da_semana(self, nota_min: float, nota_max: float, limite: int, dias: int = 7) -> list[dict]:
        """Usados que passaram nas regras mas não foram notificados (pro resumo semanal)."""
        from datetime import datetime, timedelta, timezone
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        q = urllib.parse.urlencode([
            ("select", "modelo,preco,local,nota,link,alerta_golpe,avaliacao_json,fonte"),
            ("fonte", "like.olx*"), ("passou_regras_duras", "is.true"), ("notificado_em", "is.null"),
            ("alerta_golpe", "is.null"), ("nota", f"gte.{nota_min}"), ("nota", f"lt.{nota_max}"),
            ("gravada_em", f"gte.{desde}"), ("order", "nota.desc,preco.asc"), ("limit", str(limite * 3)),
        ])
        linhas = self._req("GET", f"ofertas?{q}") or []
        # um por modelo/preço (o mesmo anúncio pode ter sido gravado com preços diferentes)
        vistos, saida = set(), []
        for l in linhas:
            chave = (l.get("modelo"), l.get("link"))
            if chave not in vistos:
                vistos.add(chave)
                saida.append(l)
        return saida[:limite]

    def aprovadas(self, limite: int = 5) -> list[dict[str, Any]]:
        q = urllib.parse.urlencode({"select": "*", "aprovado": "eq.true",
                                    "order": "recebida_em.desc", "limit": str(limite)})
        return self._req("GET", f"ofertas?{q}") or []

    def contar(self) -> int:
        linhas = self._req("GET", "ofertas?select=id", prefer="count=exact")
        return len(linhas or [])
