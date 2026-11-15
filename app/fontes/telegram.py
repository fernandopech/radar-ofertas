"""Fonte Telegram: lê canais de terceiros pela SUA conta (MTProto/Telethon).

SÓ LEITURA. Este módulo nunca envia mensagem pela sua conta; as notificações
saem por um bot separado.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom.message import Message
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

from app.config import ConfigFaltando, ConfigTelegram, SessaoInvalida
from app.fontes.base import AoReceber, Fonte
from app.oferta import Oferta

log = logging.getLogger(__name__)

_RE_URL = re.compile(r"https?://\S+")
INTERVALO_S = int(os.getenv("TELEGRAM_INTERVALO_S", "180"))  # de quanto em quanto tempo buscar


def criar_cliente(cfg: ConfigTelegram) -> TelegramClient:
    return TelegramClient(StringSession(cfg.session or None), cfg.api_id, cfg.api_hash)


def _canal_converter(canal: str) -> str | int:
    """Aceita username ou id numérico (ex.: -1001234567890)."""
    return int(canal) if canal.lstrip("-").isdigit() else canal


def _fatia_utf16(texto: str, inicio: int, tamanho: int) -> str:
    """O Telegram conta posições em unidades UTF-16; emoji ocupa 2. Python conta 1."""
    b = texto.encode("utf-16-le")
    return b[inicio * 2 : (inicio + tamanho) * 2].decode("utf-16-le", errors="ignore")


def extrair_links(msg: Message) -> list[str]:
    """Links do texto, de entidades (texto com hyperlink) e de botões inline."""
    links: list[str] = []
    texto = msg.raw_text or ""
    for ent in msg.entities or []:
        if isinstance(ent, MessageEntityTextUrl):
            links.append(ent.url)
        elif isinstance(ent, MessageEntityUrl):
            links.append(_fatia_utf16(texto, ent.offset, ent.length))
    links.extend(_RE_URL.findall(texto))
    markup = getattr(msg, "reply_markup", None)
    # Botões inline com link. Checagem pelo atributo `url` em vez do tipo,
    # porque o nome da classe muda entre versões da API do Telegram.
    for linha in getattr(markup, "rows", None) or []:
        for botao in getattr(linha, "buttons", None) or []:
            url = getattr(botao, "url", None)
            if isinstance(url, str) and url.startswith("http"):
                links.append(url)
    vistos: dict[str, None] = {}
    for link in links:
        vistos.setdefault(link.rstrip(").,;"), None)
    return list(vistos)


async def mensagem_para_oferta(msg: Message) -> Oferta | None:
    texto = msg.raw_text or ""
    if not texto.strip():
        return None  # só imagem, sem legenda: fora da v1
    chat = await msg.get_chat()
    username = getattr(chat, "username", None)
    nome_fonte = username or str(msg.chat_id)
    link_origem = f"https://t.me/{username}/{msg.id}" if username else None
    links = extrair_links(msg)
    return Oferta(
        fonte=f"telegram:{nome_fonte}",
        id_externo=f"{msg.chat_id}:{msg.id}",
        texto=texto,
        recebida_em=msg.date,
        link=links[0] if links else None,
        link_origem=link_origem,
        tem_imagem=msg.photo is not None,
        links_extras=tuple(links[1:]),
    )


class FonteTelegram(Fonte):
    nome = "telegram"

    def __init__(self, cfg: ConfigTelegram):
        if not cfg.session:
            raise ConfigFaltando(
                "TELEGRAM_SESSION vazio. Rode antes: python -m scripts.login_telegram"
            )
        if not cfg.canais:
            raise ConfigFaltando(
                "TELEGRAM_CANAIS vazio. Descubra os canais com: python -m scripts.listar_canais"
            )
        self.cfg = cfg
        self.cliente = criar_cliente(cfg)

    async def _conectar(self) -> list:
        """Conecta, valida a sessão e resolve os canais (falha cedo se algum estiver errado)."""
        if not self.cliente.is_connected():
            await self.cliente.connect()
        if not await self.cliente.is_user_authorized():
            raise SessaoInvalida(
                "Sessão do Telegram inválida ou expirada. Rode de novo: python -m scripts.login_telegram"
            )
        return [await self.cliente.get_input_entity(_canal_converter(c)) for c in self.cfg.canais]

    async def executar(self, ao_receber: AoReceber, recuperar: int = 0) -> None:
        """Busca mensagens novas a cada INTERVALO_S segundos (polling).

        Não depende do Telegram "empurrar" atualizações: em canais grandes ele não
        avisa contas que não estão abertas num app, e o monitor ficava surdo.
        """
        entidades = await self._conectar()
        # Ponto de partida: a mensagem mais recente de cada canal agora.
        ultimo: list[int] = []
        for ent in entidades:
            msgs = await self.cliente.get_messages(ent, limit=1)
            ultimo.append(msgs[0].id if msgs else 0)

        if recuperar:
            # Da mais antiga pra mais nova, pra ordem do histórico de preços ficar certa.
            recentes = [o async for o in self.backfill(recuperar)]
            log.info("Recuperando %d mensagem(ns) recente(s)", len(recentes))
            for oferta in sorted(recentes, key=lambda o: o.recebida_em):
                await ao_receber(oferta)

        log.info("Monitorando %d canal(is) a cada %ds: %s",
                 len(entidades), INTERVALO_S, ", ".join(self.cfg.canais))
        ciclos = 0
        while True:
            await asyncio.sleep(INTERVALO_S)
            ciclos += 1
            try:
                if not self.cliente.is_connected():
                    await self.cliente.connect()
                novas: list[Oferta] = []
                for i, ent in enumerate(entidades):
                    async for msg in self.cliente.iter_messages(ent, min_id=ultimo[i], reverse=True, limit=200):
                        ultimo[i] = max(ultimo[i], msg.id)
                        try:
                            oferta = await mensagem_para_oferta(msg)
                        except Exception:
                            log.exception("Erro convertendo mensagem %s", msg.id)
                            continue
                        if oferta:
                            novas.append(oferta)
                for oferta in sorted(novas, key=lambda o: o.recebida_em):
                    await ao_receber(oferta)
                if novas or ciclos % 20 == 0:  # sinal de vida ~1x por hora
                    log.info("Ciclo %d: %d mensagem(ns) nova(s)", ciclos, len(novas))
            except asyncio.CancelledError:
                raise
            except Exception:  # rede, Telegram fora etc.: tenta de novo no próximo ciclo
                log.exception("Erro no ciclo %d; tentando de novo em %ds", ciclos, INTERVALO_S)

    async def backfill(self, limite: int = 100) -> AsyncIterator[Oferta]:
        """Últimas `limite` mensagens de cada canal, da mais nova pra mais antiga."""
        entidades = await self._conectar()
        for entidade in entidades:
            async for msg in self.cliente.iter_messages(entidade, limit=limite):
                try:
                    oferta = await mensagem_para_oferta(msg)
                except Exception:
                    log.exception("Erro convertendo mensagem %s", msg.id)
                    continue
                if oferta:
                    yield oferta

    async def fechar(self) -> None:
        await self.cliente.disconnect()
