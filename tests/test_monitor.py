"""Monitor: grava, notifica, pula repetidas e não cai quando banco/bot falham."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import app.avaliacao as aval
from app.avaliacao import Criterios
from app.avaliacao.ia import Avaliacao
from app.enriquecimento.ficha import Ficha
from app.main import Monitor
from app.oferta import Oferta

C = Criterios.carregar()
BOA = ("💻 Lenovo IdeaPad Slim 5 83NJ0001BR\nRyzen AI 7 350 | Radeon 860M\n"
       "RAM 16 GB | SSD 512 GB | Windows 11 Home\nTela LED 14,0″ pol. | WUXGA IPS\n✅ Por R$ 4.299 à vista")
RUIM = BOA.replace("RAM 16 GB", "RAM 8 GB")


class BancoFalso:
    def __init__(self, existentes=(), falhar=False, ja_avisado=None):
        self.existentes, self.falhar, self.ja_avisado = set(existentes), falhar, ja_avisado or {}
        self.gravados, self.notificados, self.anotacoes = [], [], []

    def ultima_notificacao(self, chave, desde):
        if self.falhar:
            raise RuntimeError("banco fora")
        return self.ja_avisado.get(chave)

    def anotar(self, id_oferta, campos):
        self.anotacoes.append(campos)

    def ja_existe(self, fonte, id_externo):
        if self.falhar:
            raise RuntimeError("banco fora")
        return id_externo in self.existentes

    def gravar(self, reg):
        if self.falhar:
            raise RuntimeError("banco fora")
        self.gravados.append(reg)
        return len(self.gravados)

    def marcar_notificado(self, id_oferta, quando):
        self.notificados.append(id_oferta)


class BotFalso:
    chat_id = "1"

    def __init__(self, falhar=False):
        self.falhar, self.enviados = falhar, []

    def enviar(self, texto, botoes=None):
        if self.falhar:
            raise RuntimeError("telegram fora")
        self.enviados.append(texto)
        return 1


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha())
    monkeypatch.setattr(aval, "avaliar_com_ia", lambda *a, **k: Avaliacao(
        nota=8, roda_cs2="sim", veredito="comprar_agora", por_que="boa"))


def oferta(texto, id_="1", horas_atras=0):
    return Oferta(fonte="telegram:x", id_externo=id_, texto=texto,
                  recebida_em=datetime.now(timezone.utc) - timedelta(hours=horas_atras))


def test_aprovada_grava_notifica_e_marca():
    banco, bot = BancoFalso(), BotFalso()
    asyncio.run(Monitor(banco, bot, C).ao_receber(oferta(BOA)))
    assert len(banco.gravados) == 1 and banco.gravados[0]["aprovado"] is True
    assert len(bot.enviados) == 1 and "COMPRAR AGORA" in bot.enviados[0]
    assert banco.notificados == [1]


def test_reprovada_grava_sem_notificar():
    banco, bot = BancoFalso(), BotFalso()
    Monitor(banco, bot, C).tratar(oferta(RUIM))
    assert len(banco.gravados) == 1 and not bot.enviados


def test_repetida_e_pulada():
    banco, bot = BancoFalso(existentes={"1"}), BotFalso()
    Monitor(banco, bot, C).tratar(oferta(BOA))
    assert not banco.gravados and not bot.enviados


def test_banco_fora_ainda_notifica():
    banco, bot = BancoFalso(falhar=True), BotFalso()
    Monitor(banco, bot, C).tratar(oferta(BOA))
    assert len(bot.enviados) == 1 and not banco.notificados


def test_bot_fora_nao_marca_notificado():
    banco, bot = BancoFalso(), BotFalso(falhar=True)
    Monitor(banco, bot, C).tratar(oferta(BOA))
    assert len(banco.gravados) == 1 and not banco.notificados


def test_repost_mesmo_preco_nao_notifica():
    banco, bot = BancoFalso(ja_avisado={"83NJ0001BR|860M|16|512": 4299.0}), BotFalso()
    Monitor(banco, bot, C).tratar(oferta(BOA))
    assert not bot.enviados and banco.gravados[0]["chave_modelo"] == "83NJ0001BR|860M|16|512"
    assert "já avisado" in banco.anotacoes[0]["motivo_nao_notificado"]


def test_queda_de_preco_notifica_com_destaque():
    banco, bot = BancoFalso(ja_avisado={"83NJ0001BR|860M|16|512": 4599.0}), BotFalso()
    Monitor(banco, bot, C).tratar(oferta(BOA))
    assert len(bot.enviados) == 1 and "📉 baixou" in bot.enviados[0] and "era R$ 4.599" in bot.enviados[0]


def test_oferta_antiga_recuperada_grava_sem_notificar():
    banco, bot = BancoFalso(), BotFalso()
    Monitor(banco, bot, C).tratar(oferta(BOA, horas_atras=72))
    assert len(banco.gravados) == 1 and banco.gravados[0]["aprovado"] is True
    assert not bot.enviados and "oferta antiga" in banco.anotacoes[0]["motivo_nao_notificado"]


def test_sessao_derrubada_avisa_pelo_bot(monkeypatch):
    import app.main as m
    from app.config import SessaoInvalida

    enviados = []

    class FonteQuebrada:
        def __init__(self, cfg):
            pass

        async def executar(self, *a, **k):
            raise SessaoInvalida("x")

    class BotOk:
        chat_id = "1"

        def enviar(self, texto, botoes=None):
            enviados.append(texto)

    async def sem_espera(_):
        return None

    monkeypatch.setattr(m, "FonteTelegram", FonteQuebrada)
    monkeypatch.setattr(m, "ConfigTelegram", type("C", (), {"carregar": staticmethod(lambda: None)}))
    monkeypatch.setattr(m, "Banco", lambda: BancoFalso())
    monkeypatch.setattr(m, "Bot", BotOk)
    monkeypatch.setattr(m.asyncio, "sleep", sem_espera)

    async def sem_resumo(_):
        return None
    monkeypatch.setattr(m, "_resumo_semanal", sem_resumo)  # senão roda em loop com o sleep falso
    asyncio.run(m.rodar())
    assert len(enviados) == 1 and "login_telegram" in enviados[0]


def test_marketplace_tem_janela_maior():
    from dataclasses import replace
    banco, bot = BancoFalso(), BotFalso()
    o = replace(oferta(BOA, horas_atras=72), categoria_confirmada=True)
    Monitor(banco, bot, C).tratar(o)
    assert len(bot.enviados) == 1  # 3 dias: Telegram não notificaria, OLX sim
