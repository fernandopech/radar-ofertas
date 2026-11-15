"""Envia mensagens pelo BOT (Bot API). Sua conta pessoal nunca envia nada."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from app.config import ConfigFaltando

log = logging.getLogger(__name__)


class ErroBot(RuntimeError):
    pass


class Bot:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.getenv("BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.getenv("BOT_CHAT_ID", "").strip()
        if not self.token:
            raise ConfigFaltando("BOT_TOKEN vazio. Crie o bot no @BotFather e cole o token no .env.")

    def _chamar(self, metodo: str, dados: dict[str, Any] | None = None) -> Any:
        url = f"https://api.telegram.org/bot{self.token}/{metodo}"
        corpo = json.dumps(dados or {}).encode()
        req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                resposta = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            resposta = json.loads(e.read().decode() or "{}")
        except urllib.error.URLError as e:
            raise ErroBot(f"sem conexão com o Telegram: {e.reason}") from None
        if not resposta.get("ok"):
            # nunca loga a URL: ela contém o token
            raise ErroBot(f"{metodo}: {resposta.get('description', 'erro desconhecido')}")
        return resposta["result"]

    def quem_sou(self) -> dict:
        return self._chamar("getMe")

    def chats_recentes(self) -> list[dict]:
        """Chats que mandaram mensagem pro bot (ex.: seu /start)."""
        chats = {}
        for u in self._chamar("getUpdates"):
            msg = u.get("message") or u.get("edited_message") or {}
            chat = msg.get("chat")
            if chat:
                chats[chat["id"]] = chat
        return list(chats.values())

    def enviar(self, texto: str, botoes: list[tuple[str, str]] | None = None) -> int:
        """`botoes`: lista de (rótulo, url) mostrados lado a lado embaixo da mensagem."""
        if not self.chat_id:
            raise ConfigFaltando("BOT_CHAT_ID vazio. Rode: python -m scripts.configurar_bot")
        dados: dict[str, Any] = {
            "chat_id": self.chat_id, "text": texto, "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        validos = [(r, u) for r, u in (botoes or []) if u and u.startswith(("http://", "https://"))]
        if validos:
            dados["reply_markup"] = {"inline_keyboard": [[{"text": r, "url": u} for r, u in validos]]}
        return self._chamar("sendMessage", dados)["message_id"]
