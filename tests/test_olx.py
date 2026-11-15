"""Fonte OLX: filtro de região, conversão do anúncio e economia de consultas (sem rede)."""
from datetime import datetime, timezone

from app.avaliacao import Criterios
from app.extracao import extrair
from app.fontes.olx import ConfigOlx, FonteOlx, anuncio_para_oferta

C = Criterios.carregar()
CFG = ConfigOlx(chave="x", cidades=C.bruto["olx"]["cidades"])


def ad(id_, cidade, titulo="Notebook Lenovo Ideapad", preco=3000.0):
    return {"id": id_, "title": titulo, "price": {"amount": preco}, "link": f"https://rs.olx.com.br/{id_}",
            "location": {"municipality": cidade, "neighbourhood": "Centro", "state": "RS"},
            "posted_at": "2026-11-15T19:00:00Z", "is_professional": False, "image_count": 3}


def test_cidades_da_regiao_metropolitana():
    assert CFG.cidade_ok("Porto Alegre") and CFG.cidade_ok("São Leopoldo") and CFG.cidade_ok("sao leopoldo")
    assert CFG.cidade_ok("Viamão") and not CFG.cidade_ok("Caxias do Sul") and not CFG.cidade_ok(None)


def test_anuncio_vira_oferta_com_descricao_e_sem_prefiltro():
    det = {"description": "Ryzen 7 5800H, RTX 3050, 16GB RAM, SSD 512. Bateria boa.",
           "attributes": [{"label": "Marca", "value": "Lenovo"}]}
    o = anuncio_para_oferta(ad(1, "Canoas"), det)
    assert o.fonte == "olx:grande-poa" and o.id_externo == "1@3000"
    assert o.categoria_confirmada and o.local == "Centro, Canoas"
    assert "Vendedor: particular" in o.texto and "Ryzen 7 5800H" in o.texto and "Marca: Lenovo" in o.texto
    assert o.recebida_em == datetime(2026, 11, 15, 19, tzinfo=timezone.utc)
    # título curto sem specs não é barrado pelo pré-filtro (a categoria já garante que é notebook)
    assert extrair(o, usar_ia=False).metodo != "prefiltro"


class ClienteFalso:
    def __init__(self, ads):
        self.ads, self.detalhes_pedidos, self.saldo = ads, [], 900

    def buscar(self, pagina=1):
        self.paginas = getattr(self, "paginas", []) + [pagina]
        return self.ads

    def detalhes(self, ad_id):
        self.detalhes_pedidos.append(ad_id)
        return {"description": "x"}


def test_ciclo_filtra_regiao_pula_ja_gravados_e_titulos_fora_do_perfil():
    ads = [ad(1, "Porto Alegre"), ad(2, "Caxias do Sul"), ad(3, "Canoas"),
           ad(4, "Gravataí", titulo="Chromebook Samsung"), ad(5, "Esteio", titulo="Notebook com defeito, peças")]
    f = FonteOlx(CFG, ja_existe=lambda fonte, i: i == "3@3000")
    f.cliente = ClienteFalso(ads)
    novas = f.ciclo()
    assert [o.id_externo for o in novas] == ["1@3000"]
    assert f.cliente.detalhes_pedidos == ["1"]          # só gastou consulta com o que importa
    assert f.ciclo() == [] and f.cliente.detalhes_pedidos == ["1"]  # 2º ciclo não repete


def test_preco_baixou_vira_oferta_nova():
    f = FonteOlx(CFG)
    f.cliente = ClienteFalso([ad(1, "Porto Alegre", preco=3000.0)])
    f.ciclo()
    f.cliente.ads = [ad(1, "Porto Alegre", preco=2700.0)]
    assert [o.id_externo for o in f.ciclo()] == ["1@2700"]


def test_pausa_quando_saldo_acaba():
    f = FonteOlx(CFG)
    f.cliente = ClienteFalso([ad(1, "Porto Alegre")])
    f.cliente.saldo = 10
    assert f.ciclo() == [] and f.cliente.detalhes_pedidos == []


def test_config_sem_chave_desliga_olx(monkeypatch):
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    assert ConfigOlx.carregar(C.bruto) is None
    monkeypatch.setenv("RAPIDAPI_KEY", "k")
    cfg = ConfigOlx.carregar(C.bruto)
    assert cfg.intervalo_min == 120 and "macOS" in cfg.sistemas_aceitos


def test_macbook_segue_os_sistemas_aceitos():
    from app.fontes.olx import regex_pular
    assert not regex_pular(["Windows", "macOS"]).search("MacBook Air M2 16GB")
    assert regex_pular(["Windows"]).search("MacBook Air M2 16GB")
    assert regex_pular(["Windows", "macOS"]).search("Chromebook Samsung")
    assert CFG.sistemas_aceitos  # carregado do criterios.yaml no teste de config abaixo


def test_pagina_extra_e_repassada():
    f = FonteOlx(CFG)
    f.cliente = ClienteFalso([ad(9, "Canoas")])
    f.ciclo(pagina=3)
    assert f.cliente.paginas == [3] and f.ultima_busca[0]["id"] == 9
