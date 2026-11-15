"""Formato da notificação e cliente do bot (sem rede)."""
import json

import pytest

from app.notificacao import formatar
from app.notificacao import telegram_bot as tb
from app.notificacao.telegram_bot import Bot, ErroBot

BASE = {"modelo": "Lenovo LOQ <83KH>", "preco": 5124, "loja": "Amazon", "fonte": "telegram:qualnotebook",
        "condicao": "novo", "cpu": "Core i5-14500HX", "gpu": "RTX 3050", "ram_gb": 16,
        "armazenamento_gb": 1024, "tipo_armazenamento": "SSD", "tela_pol": 15.6,
        "link": "https://qual.not.br/x", "link_origem": "https://t.me/qualnotebook/1",
        "avaliacao_json": {"nota": 9, "roda_cs2": "sim", "pontos_fortes": ["a & b"], "pontos_fracos": ["c"],
                           "incertezas": []}}


def test_formato_curto_com_detalhes_recolhidos():
    m = formatar({**BASE, "avaliacao_json": {**BASE["avaliacao_json"], "veredito": "comprar_agora",
                                             "por_que": "Boa & barata"}}, teto=4500)
    visivel, detalhes = m.texto.split("<blockquote expandable>")
    assert visivel.startswith("🟢 <b>COMPRAR AGORA</b>")
    assert "<b>Lenovo LOQ &lt;83KH&gt;</b>" in visivel and "R$ 5.124</b> na Amazon" in visivel
    assert "⭐ 9/10   ·   NOVO" in visivel and "CS2" not in m.texto and "💬 Boa &amp; barata" in visivel
    assert "\n\n" in visivel  # blocos separados por linha em branco
    assert "1 TB SSD" in detalhes and "15,6&quot;" in detalhes and "• a &amp; b" in detalhes
    assert "⚙️ <b>Configuração</b>" in detalhes and "✅ <b>Pontos fortes</b>" in detalhes
    assert detalhes.endswith("</blockquote>")
    assert m.botoes == [("🛒 Ver na loja", "https://qual.not.br/x"),
                        ("📄 Post original", "https://t.me/qualnotebook/1")]


def test_veredito_ausente_usa_nota():
    assert formatar(BASE).texto.startswith("🟢")  # nota 9, avaliação antiga sem veredito
    baixa = {**BASE, "avaliacao_json": {**BASE["avaliacao_json"], "nota": 7}}
    assert formatar(baixa).texto.startswith("🟡 <b>VALE ESPERAR</b>")


def test_oportunidade_e_queda():
    t = formatar({**BASE, "oportunidade": True, "desconto_pct": 13.5,
                  "preco_justo_min": 5925, "preco_justo_max": 6419}, queda_de=5359).texto
    assert "🔥 oportunidade  ·  📉 baixou" in t
    assert "R$ 5.124</b> na Amazon  (era R$ 5.359)" in t and "📉 14% abaixo do preço justo" in t


@pytest.mark.parametrize("extra,esperado", [
    ({"condicao": "usado"}, "USADO · SEM GARANTIA"),
    ({"vendedor_tipo": "pessoa_fisica", "condicao": "desconhecido"}, "SEM GARANTIA"),
    ({"condicao": "recondicionado", "garantia_meses": 6}, "RECONDICIONADO (6 meses de garantia)"),
])
def test_condicoes(extra, esperado):
    assert esperado in formatar({**BASE, **extra}).texto


class _Resp:
    def __init__(self, corpo):
        self.corpo = corpo

    def read(self):
        return json.dumps(self.corpo).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_enviar_e_erro_nao_vaza_token(monkeypatch):
    enviados = []

    def falso(req, timeout):
        enviados.append(json.loads(req.data))
        if "sendMessage" in req.full_url and enviados[-1]["text"] == "falha":
            return _Resp({"ok": False, "description": "Bad Request: chat not found"})
        return _Resp({"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(tb.urllib.request, "urlopen", falso)
    bot = Bot("123:SEGREDO", "999")
    assert bot.enviar("oi") == 7
    assert enviados[0] == {"chat_id": "999", "text": "oi", "parse_mode": "HTML",
                           "link_preview_options": {"is_disabled": True}}
    bot.enviar("com botões", [("🛒 Loja", "https://loja/x"), ("ruim", "/sem-http")])
    assert enviados[1]["reply_markup"] == {"inline_keyboard": [[{"text": "🛒 Loja", "url": "https://loja/x"}]]}
    with pytest.raises(ErroBot) as e:
        bot.enviar("falha")
    assert "SEGREDO" not in str(e.value) and "chat not found" in str(e.value)


def test_marketplace_mostra_local_alerta_e_um_botao():
    m = formatar({**BASE, "fonte": "olx:grande-poa", "loja": None, "condicao": "usado",
                  "vendedor_tipo": "pessoa_fisica", "local": "Centro, Canoas",
                  "alerta_golpe": "preço muito abaixo do normal", "link_origem": "https://olx/x"})
    assert "📍 Centro, Canoas · OLX" in m.texto
    assert "🚨 <b>Atenção, possível golpe:</b> preço muito abaixo do normal" in m.texto
    assert "USADO · SEM GARANTIA" in m.texto
    assert m.botoes == [("🛒 Ver anúncio", "https://qual.not.br/x")]
