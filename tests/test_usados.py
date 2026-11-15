"""Usados de marketplace: reparos, referência de preço, defeito grave, IQR e resumo semanal."""
from datetime import datetime, timezone

import app.avaliacao as aval
from app.avaliacao import ia as ia_aval
from app.avaliacao.criterios import Criterios
from app.avaliacao.usados import ConfigUsados, calcular
from app.enriquecimento.ficha import Ficha
from app.extracao.modelos import Specs
from app.notificacao.resumo import formatar_resumo, proximo_envio
from app.oferta import Oferta

C = Criterios.carregar()
CFG = ConfigUsados.carregar(C.bruto)
PARECIDOS = [3900, 3700, 4100, 3800, 4200, 3600, 3950]
BATERIA = {"descricao": "bateria dura 1h", "nivel": "moderado", "tipo": "bateria viciada ou fraca"}


def test_reparo_soma_no_preco_e_referencia_prefere_mercado():
    c = calcular(3300, [BATERIA, {"descricao": "riscos", "nivel": "leve"}], 2022, 6500, True,
                 PARECIDOS, CFG, hoje=datetime(2026, 11, 15))
    assert c.custo_reparo == 350 and c.preco_efetivo == 3650
    assert c.ref_comparaveis == 3900 and c.referencia == 3900      # mercado real tem prioridade
    assert c.ref_depreciacao == 3250                                # 4 anos × 50%
    assert round(c.desconto_pct) == 6 and c.leves == ["riscos"]


def test_sem_parecidos_usa_depreciacao():
    c = calcular(3300, [], 2024, 6000, True, [3500], CFG, hoje=datetime(2026, 11, 15))
    assert c.ref_comparaveis is None and c.referencia == 4200      # 2 anos × 70%


def test_tipo_de_defeito_desconhecido_usa_custo_padrao():
    c = calcular(3000, [{"descricao": "webcam ruim", "nivel": "moderado", "tipo": "webcam"}], None, None,
                 True, [], CFG)
    assert c.custo_reparo == 200


def test_iqr_marca_preco_fora_da_curva():
    assert calcular(1500, [], None, None, True, PARECIDOS, CFG).suspeito_iqr
    assert calcular(3500, [], None, None, True, PARECIDOS, CFG).suspeito_iqr is None


def _specs(**kw):
    base = dict(eh_oferta_notebook=True, modelo="Lenovo Legion 5", cpu="Ryzen 7 5800H", gpu="RTX 3050",
                ram_gb=16, armazenamento_gb=512, tipo_armazenamento="SSD", tela_pol=15.6,
                sistema="Windows", preco=3300.0, condicao="usado", vendedor_tipo="pessoa_fisica")
    base.update(kw)
    return Specs(**base)


def _olx():
    return Oferta(fonte="olx:grande-poa", id_externo="1@3300", texto="Anúncio da OLX: Legion 5",
                  recebida_em=datetime.now(timezone.utc), categoria_confirmada=True)


def _avaliar(monkeypatch, defeitos, nota=7.0, preco=3300.0):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha())
    vistos = {}

    def ia_falsa(*a, **k):
        vistos["contexto"] = a[4]
        return ia_aval.Avaliacao(nota=nota, roda_cs2="sim", defeitos=defeitos)

    monkeypatch.setattr(aval, "avaliar_com_ia", ia_falsa)
    r = aval.avaliar(_olx(), _specs(preco=preco), C, comparaveis=lambda gpu, ram: PARECIDOS)
    return r, vistos


def test_usado_nota_7_e_aprovado(monkeypatch):
    r, vistos = _avaliar(monkeypatch, [BATERIA])
    assert r.aprovado and r.usado.preco_efetivo == 3650
    assert any("mediana" in linha for linha in vistos["contexto"])  # IA recebe a referência


def test_defeito_grave_reprova(monkeypatch):
    r, _ = _avaliar(monkeypatch, [{"descricao": "tela com listras", "nivel": "grave"}], nota=8)
    assert not r.aprovado and "defeito grave" in r.motivo


def test_preco_fora_da_curva_nao_notifica(monkeypatch):
    r, _ = _avaliar(monkeypatch, [], nota=8, preco=1500.0)
    assert not r.aprovado and r.suspeito and "golpe" in r.motivo


def test_prompt_de_usado_tem_tabela_de_defeitos():
    s = ia_aval.instrucoes_usado(C)
    assert "bateria viciada ou fraca" in s and "NÃO trate" in s and "tela quebrada" in s


def test_proximo_domingo_19h():
    # sábado 14/11 22h UTC (19h BRT) → domingo 15/11 19h BRT
    alvo = proximo_envio(datetime(2026, 11, 14, 22, tzinfo=timezone.utc), "domingo", 19)
    assert (alvo.day, alvo.hour, alvo.weekday()) == (15, 19, 6)
    # domingo 15/11 22h UTC (19h BRT em ponto) → já passou, vai pro próximo domingo
    assert proximo_envio(datetime(2026, 11, 15, 22, 0, 1, tzinfo=timezone.utc), "domingo", 19).day == 22


def test_resumo_semanal_formata_lista_e_vazio():
    t = formatar_resumo([{"modelo": "Avell A60", "preco": 2990, "nota": 6.5, "local": "Centro, Canoas",
                          "link": "https://olx/x", "avaliacao_json": {"por_que": "1660 Ti ok"}}])
    assert "1. Avell A60" in t and "R$ 2.990" in t and "6,5/10" in t and "ver anúncio" in t
    assert "Nenhum usado" in formatar_resumo([])
