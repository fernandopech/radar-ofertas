"""Polling do Telegram: pega só as mensagens novas a cada ciclo, sem repetir."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace as N

import pytest

from app.config import ConfigTelegram
from app.fontes import telegram as tg


class Msg:
    def __init__(self, id_, texto):
        self.id, self.raw_text, self.entities, self.reply_markup = id_, texto, [], None
        self.chat_id, self.photo = -100, None
        self.date = datetime(2026, 11, 15, 12, 0, id_ % 60, tzinfo=timezone.utc)

    async def get_chat(self):
        return N(username="canal")


class ClienteFalso:
    def __init__(self, canal):
        self.canal = canal  # lista de Msg, cresce entre ciclos

    def is_connected(self):
        return True

    async def get_messages(self, ent, limit):
        return sorted(self.canal, key=lambda m: -m.id)[:limit]

    async def iter_messages(self, ent, min_id=0, reverse=False, limit=None):
        for m in sorted(self.canal, key=lambda m: m.id):
            if m.id > min_id:
                yield m


def test_polling_pega_so_as_novas(monkeypatch):
    canal = [Msg(1, "antiga"), Msg(2, "antiga 2")]
    fonte = tg.FonteTelegram.__new__(tg.FonteTelegram)
    fonte.cfg = ConfigTelegram(api_id=1, api_hash="x", session="s", canais=["canal"])
    fonte.cliente = ClienteFalso(canal)

    async def conectar():
        return ["ent"]
    fonte._conectar = conectar

    recebidas, ciclos = [], {"n": 0}

    async def sono_falso(_):
        ciclos["n"] += 1
        if ciclos["n"] == 1:
            canal.extend([Msg(3, "nova A"), Msg(4, "nova B")])
        elif ciclos["n"] == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(tg.asyncio, "sleep", sono_falso)

    async def ao_receber(o):
        recebidas.append(o.texto)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(fonte.executar(ao_receber))
    assert recebidas == ["nova A", "nova B"]  # nem as antigas, nem repetidas no 2º ciclo
