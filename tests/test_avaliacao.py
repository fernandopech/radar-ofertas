"""Regras duras, leitura da ficha do site e avaliação da IA (simulada)."""
from types import SimpleNamespace as N

import pytest

from app.avaliacao import ia as ia_aval
from app.avaliacao.criterios import Criterios
from app.avaliacao.regras import aplicar_regras, bate_com
from app.enriquecimento.ficha import Ficha, _desembrulhar, analisar_ram, ler_ficha_qnc
from app.extracao.modelos import Specs

C = Criterios.carregar()


def specs(**kw) -> Specs:
    base = dict(eh_oferta_notebook=True, modelo="X", cpu="Ryzen 7 8840HS", gpu="Radeon 780M",
                ram_gb=16, armazenamento_gb=512, tipo_armazenamento="SSD", tela_pol=15.6,
                sistema="Windows", preco=4000.0, condicao="novo")
    base.update(kw)
    return Specs(**base)


@pytest.mark.parametrize("nome,termo,esperado", [
    ("Radeon RX Vega 8", "Radeon Vega", True),
    ("UHD Graphics", "Intel UHD", True),
    ("Iris Xe Graphics G7 (96 EUs)", "Iris Xe", True),
    ("Core 3-304", "Core 3", True),
    ("Intel Core 3 100U", "Core 3", True),
    ("Core 5-320", "Core 3", False),
    ("Ryzen 7 3700U", "Ryzen 3", False),
    ("Core i3-1305U", "Core i3", True),
    ("Core Ultra 7-255H", "Core 3", False),
    ("Radeon 780M", "Radeon 610M", False),
])
def test_bate_com(nome, termo, esperado):
    assert bate_com(nome, termo) is esperado


def test_oferta_boa_passa():
    r = aplicar_regras(specs(), "", C)
    assert r.passou and not r.motivos


def test_reprovacoes():
    r = aplicar_regras(specs(ram_gb=8, tipo_armazenamento="eUFS", tela_pol=13.3,
                             cpu="Core 3-304", gpu="Graphics 1 Xe3 iGPU", sistema="ChromeOS"), "", C)
    texto = " | ".join(r.motivos)
    for trecho in ["RAM 8 GB", "eUFS", "13.3", "ChromeOS", "Core 3"]:
        assert trecho in texto


def test_dado_ausente_nao_reprova():
    r = aplicar_regras(specs(gpu="", tela_pol=None, preco=None), "", C)
    assert r.passou and {"GPU", "tamanho da tela", "preço"} <= set(r.ausentes)


def test_so_preco():
    r = aplicar_regras(specs(preco=4900.0), "", C)
    assert not r.passou and r.so_preco
    assert not aplicar_regras(specs(preco=4900.0, ram_gb=8), "", C).so_preco


HTML = """
<li class="spec_ram_installed_capacity_and_type">16 GB DDR5</li>
<li class="spec_ram_max_capacity">Máximo de 32 GB</li>
<ul><li class="spec_ram_onboard not-available">RAM soldada: <em>Não possui</em></li></ul>
<ul><li class="spec_ram_slot_1">Slot 1: <b>8 GB</b></li><li class="spec_ram_slot_2">Slot 2: <b>8 GB</b></li></ul>
<li class="spec_m2_slot_2">M.2 slot 2: <b>vazio</b> <i class="x" data-content="<p>NVMe</p>"></i></li>
<p class="spec_display_luminance small">Brilho: 300 nits</p>
<p class="spec_battery_mah_and_wh">Bateria de <b>60 Wh</b></p>
<p class="spec_dimensions_weight"><small>Peso:</small> <b>1,47</b> kg</p>
"""


def test_le_ficha_qnc():
    campos = ler_ficha_qnc(HTML)
    assert campos["RAM soldada"] == "RAM soldada: Não possui"
    assert campos["slot M.2 2"] == "M.2 slot 2: vazio"
    assert campos["peso"] == "Peso: 1,47 kg"
    f = Ficha(campos=campos)
    analisar_ram(f)
    assert f.ram_dual_channel is True and f.ram_expansivel is True  # 2x8, máx 32


@pytest.mark.parametrize("soldada,slots,dual,expansivel", [
    ("RAM soldada: 16 GB", ["Slot 1: vazio", "Slot 2: Não possui"], None, True),
    ("RAM soldada: Não possui", ["Slot 1: 16 GB", "Slot 2: vazio"], False, True),
    ("RAM soldada: 8 GB", ["Slot 1: 8 GB"], True, False),
])
def test_analisar_ram(soldada, slots, dual, expansivel):
    campos = {"RAM soldada": soldada, "RAM instalada": "16 GB", "RAM máxima": "Máximo de 16 GB"}
    campos.update({f"slot de RAM {i}": s for i, s in enumerate(slots, 1)})
    f = Ficha(campos=campos)
    analisar_ram(f)
    assert (f.ram_dual_channel, f.ram_expansivel) == (dual, expansivel)


def test_desembrulha_afiliado():
    url = ("https://click.linksynergy.com/deeplink?id=x&mid=1&murl="
           "https%3A%2F%2Fbr.store.asus.com%2Fnotebook.html")
    assert _desembrulhar(url) == "https://br.store.asus.com/notebook.html"


def test_avaliacao_ia_simulada(monkeypatch):
    texto = ('{"nota": 8, "aprovado": true, "roda_cs2": "Não", "pontos_fortes": ["RTX 3050"], '
             '"pontos_fracos": [], "incertezas": ["brilho"], "resumo": "Boa."}')
    resp = N(content=[N(type="text", text=texto)], usage=N(input_tokens=1, output_tokens=1),
             stop_reason="end_turn")
    monkeypatch.setattr(ia_aval, "_get_cliente", lambda: N(messages=N(create=lambda **kw: resp)))
    a = ia_aval.avaliar_com_ia(specs(), None, [], C)
    assert a.nota == 8 and a.roda_cs2 == "nao"


def test_prompt_tem_criterios():
    s = ia_aval.montar_sistema(C)
    assert "Counter-Strike 2" in s and "dual-channel" in s


# --- Listas por nível e oportunidade -------------------------------------------------
from datetime import datetime, timezone  # noqa: E402

import app.avaliacao as aval  # noqa: E402
from app.avaliacao.componentes import classificar_nome, classificar_tela  # noqa: E402
from app.enriquecimento.ficha import ler_preco_justo  # noqa: E402
from app.oferta import Oferta  # noqa: E402

GPU = C.componentes["gpu"]


@pytest.mark.parametrize("gpu,nivel", [
    ("GeForce RTX 4060", "excelente"),
    ("GeForce 🎮 RTX 3050", "boa"),
    ("Arc Graphics 140T", "boa"),
    ("Arc Graphics 130T", "ok"),
    ("Intel Arc Graphics", "ok"),
    ("Radeon 660M", "fraca"),
    ("Graphics 2 Xe3 iGPU", "excluir"),
    ("Graphics 80 EUs", "excluir"),
    ("Iris Xe Graphics G7 (80 EUs)", "excluir"),
    ("Radeon 999X", None),
])
def test_niveis_gpu(gpu, nivel):
    assert classificar_nome(gpu, GPU).nivel == nivel


def test_tela_varias_qualidades():
    t = classificar_tela("Full HD IPS 144 Hz", C.componentes["tela"])
    assert t == {"boa": ["IPS", "144 Hz"]}
    assert "ruim" in classificar_tela("HD TN (1366 x 768)", C.componentes["tela"])


def test_gpu_excluida_reprova():
    r = aplicar_regras(specs(gpu="Graphics 2 Xe3 iGPU"), "", C)
    assert not r.passou and "Graphics 2 Xe3" in r.motivos[0]


def test_preco_justo():
    pagina = ('<p class="ideal-prices-calcs">O preço justo fica entre <b>R$ 6.308</b> e '
              '<b>R$ 6.834</b></p><p class="ideal-prices-alert">É uma ótima oportunidade!</p>')
    assert ler_preco_justo(pagina) == (6308.0, 6834.0, "É uma ótima oportunidade!")


def _oferta():
    return Oferta(fonte="t", id_externo="1", texto="", recebida_em=datetime.now(timezone.utc))


@pytest.mark.parametrize("preco,justo,oportunidade", [
    (5100.0, 6000.0, True),    # 15% abaixo, abaixo do teto absoluto
    (5400.0, 5800.0, False),   # só 6,9% abaixo
    (5600.0, 7000.0, False),   # acima do teto absoluto (5500)
])
def test_oportunidade(monkeypatch, preco, justo, oportunidade):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha(preco_justo_min=justo, preco_justo_max=justo + 500))
    nota8 = ia_aval.Avaliacao(nota=8, roda_cs2="sim")
    monkeypatch.setattr(aval, "avaliar_com_ia", lambda *a, **k: nota8)
    r = aval.avaliar(_oferta(), specs(preco=preco), C)
    assert r.oportunidade is oportunidade
    assert r.aprovado is oportunidade


def test_dentro_do_teto_nao_e_oportunidade(monkeypatch):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha(preco_justo_min=6000.0, preco_justo_max=6500.0))
    monkeypatch.setattr(aval, "avaliar_com_ia", lambda *a, **k: ia_aval.Avaliacao(nota=7, roda_cs2="sim"))
    r = aval.avaliar(_oferta(), specs(preco=4000.0), C)
    assert r.aprovado and not r.oportunidade
    assert any("33% abaixo" in linha for linha in r.contexto)  # IA recebe o preço justo


def test_veredito_normalizado(monkeypatch):
    texto = '{"nota": 8, "roda_cs2": "sim", "veredito": "Comprar agora", "por_que": "barato"}'
    resp = N(content=[N(type="text", text=texto)], usage=N(input_tokens=1, output_tokens=1),
             stop_reason="end_turn")
    monkeypatch.setattr(ia_aval, "_get_cliente", lambda: N(messages=N(create=lambda **kw: resp)))
    assert ia_aval.avaliar_com_ia(specs(), None, [], C).veredito == "comprar_agora"


@pytest.mark.parametrize("veredito,aprovado", [
    ("comprar_agora", True), ("esperar", True), ("", True), ("nao_compensa", False),
])
def test_nao_compensa_nao_notifica(monkeypatch, veredito, aprovado):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha())
    monkeypatch.setattr(aval, "avaliar_com_ia",
                        lambda *a, **k: ia_aval.Avaliacao(nota=8, roda_cs2="sim", veredito=veredito))
    assert aval.avaliar(_oferta(), specs(), C).aprovado is aprovado


def test_busca_pagina_qnc_pelo_codigo(monkeypatch):
    from app.enriquecimento import ficha as ficha_mod
    resultado = ('<a href="https://quenotebookcomprar.com.br/vaio-fe16-vjfe69f11x-b1711h/">VAIO</a>'
                 '<a href="https://quenotebookcomprar.com.br/outro-modelo/">x</a>')
    monkeypatch.setattr(ficha_mod, "_baixar", lambda url: resultado if "?s=" in url else None)
    assert ficha_mod.buscar_pagina_qnc("VJFE69F11X-B1711H") == \
        "https://quenotebookcomprar.com.br/vaio-fe16-vjfe69f11x-b1711h/"
    assert ficha_mod.buscar_pagina_qnc("83TYS00500") is None


def test_agregador_nao_vira_loja():
    from app.enriquecimento.ficha import resolver_loja
    assert resolver_loja("https://boletando.com/oferta/271944/") == (None, None)


def test_usado_barato_demais_fica_suspeito(monkeypatch):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha(preco_justo_min=6000.0, preco_justo_max=6500.0))
    monkeypatch.setattr(aval, "avaliar_com_ia", lambda *a, **k: ia_aval.Avaliacao(nota=8, roda_cs2="sim"))
    r = aval.avaliar(_oferta(), specs(preco=2000.0, condicao="usado", vendedor_tipo="pessoa_fisica"), C)
    assert r.suspeito and "33%" in r.suspeito
    ok = aval.avaliar(_oferta(), specs(preco=3500.0, condicao="usado", vendedor_tipo="pessoa_fisica"), C)
    assert ok.suspeito is None


def test_alerta_da_ia_vira_suspeito(monkeypatch):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha())
    monkeypatch.setattr(aval, "avaliar_com_ia", lambda *a, **k: ia_aval.Avaliacao(
        nota=8, roda_cs2="sim", alerta_golpe="pede PIX antes de mostrar"))
    assert aval.avaliar(_oferta(), specs(), C).suspeito == "pede PIX antes de mostrar"


@pytest.mark.parametrize("sistema,modelo,cs2,aprovado", [
    ("Windows", "Lenovo LOQ", "sim", True),
    ("Windows", "ASUS S14", "provavelmente", False),   # precisa ter certeza
    ("Linux", "VAIO", "nao", False),
    ("macOS", "MacBook Air M2", "nao", True),          # Mac: CS2 não é exigido
])
def test_cs2_obrigatorio_fora_do_mac(monkeypatch, sistema, modelo, cs2, aprovado):
    monkeypatch.setattr(aval, "enriquecer", lambda *a: Ficha())
    monkeypatch.setattr(aval, "avaliar_com_ia", lambda *a, **k: ia_aval.Avaliacao(nota=8, roda_cs2=cs2))
    r = aval.avaliar(_oferta(), specs(sistema=sistema, modelo=modelo), C)
    assert r.aprovado is aprovado
    if not aprovado:
        assert "CS2" in r.motivo


def test_mac_passa_nas_regras_duras():
    assert aplicar_regras(specs(sistema="macOS", cpu="Apple M2", gpu="Apple M2 GPU 10 núcleos"), "", C).passou


def test_prompt_explica_mac():
    s = ia_aval.montar_sistema(C)
    assert "MacBook" in s and "não cite CS2" in s


@pytest.mark.parametrize("gpu", ["GeForce GTX 1650", "GTX 1660 Ti", "NVIDIA GTX 1060 6GB"])
def test_gtx_usadas_no_nivel_ok(gpu):
    assert classificar_nome(gpu, GPU).nivel == "ok"
