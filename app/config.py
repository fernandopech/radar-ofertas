"""Carrega configuração do .env (local/Codespaces) ou das variáveis do Heroku."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_ENV = RAIZ / ".env"



def _carregar_env() -> None:
    """Valores PREENCHIDOS no .env valem mais que variáveis de ambiente (ex.: secrets do
    Codespaces), pra que editar o .env sempre tenha efeito. Valor vazio no .env não apaga
    o que já existe. No Heroku não há .env: valem só as Config Vars."""
    if not ARQUIVO_ENV.exists():
        return
    for nome, valor in dotenv_values(ARQUIVO_ENV).items():
        if valor:
            os.environ[nome] = valor


_carregar_env()


def gravar_variavel(nome: str, valor: str) -> None:
    """Grava/atualiza NOME=valor no .env e no ambiente do processo atual."""
    conteudo = ARQUIVO_ENV.read_text() if ARQUIVO_ENV.exists() else ""
    linha = f"{nome}={valor}"
    padrao = rf"^{re.escape(nome)}=.*$"
    if re.search(padrao, conteudo, flags=re.M):
        conteudo = re.sub(padrao, lambda _: linha, conteudo, flags=re.M)
    else:
        conteudo = conteudo.rstrip("\n") + f"\n{linha}\n"
    ARQUIVO_ENV.write_text(conteudo)
    os.environ[nome] = valor


class ConfigFaltando(RuntimeError):
    pass


class SessaoInvalida(ConfigFaltando):
    """O Telegram derrubou o login da sua conta (ex.: sessão usada em dois lugares)."""


def _obrigatoria(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise ConfigFaltando(
            f"Variável {nome} não está definida. Preencha no .env "
            f"(veja .env.example) ou nas variáveis do Heroku."
        )
    return valor


@dataclass(frozen=True)
class ConfigTelegram:
    api_id: int
    api_hash: str
    session: str          # StringSession; vazio = ainda não logou
    canais: list[str]

    @classmethod
    def carregar(cls) -> "ConfigTelegram":
        api_id = _obrigatoria("TELEGRAM_API_ID")
        if not api_id.isdigit():
            raise ConfigFaltando("TELEGRAM_API_ID deve ser só números.")
        canais_brutos = os.getenv("TELEGRAM_CANAIS", "")
        canais = [c.strip().lstrip("@") for c in canais_brutos.split(",") if c.strip()]
        return cls(
            api_id=int(api_id),
            api_hash=_obrigatoria("TELEGRAM_API_HASH"),
            session=os.getenv("TELEGRAM_SESSION", "").strip(),
            canais=canais,
        )
