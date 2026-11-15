"""Testes do pré-filtro e do leitor em código usando as amostras reais.

Rodar: python -m pytest -q
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.extracao import extrair
from app.extracao.prefiltro import parece_notebook
from app.oferta import Oferta

AMOSTRA = Path(__file__).parent.parent / "amostras" / "telegram_qualnotebook.jsonl"


def oferta(texto: str, link: str | None = None) -> Oferta:
    return Oferta(fonte="teste", id_externo="1", texto=texto,
                  recebida_em=datetime.now(timezone.utc), link=link)


FICHA = """🔥 BAIXOU MUITO!
==========
💻 Lenovo IdeaPad Slim 3 83MMS00300
==========
Ryzen 5 7535HS (Série 7000) | Radeon 660M
RAM 8 GB | SSD 📦 1 TB | Linux
Tela LED 15,3″ pol. | WUXGA IPS
Garantia 1 ano Premium Care
de R$ 3399
✅ Por R$ 2.917 à vista c/ CUPOM
Em até 10x de R$ 324
https://quenotebookcomprar.com.br/x
Ver na loja:
▶️ https://qual.not.br/g9vbj9tx
"""


def test_leitor_ficha_completa():
    e = extrair(oferta(FICHA), usar_ia=False)
    assert e.metodo == "parser"
    s = e.specs
    assert s.modelo == "Lenovo IdeaPad Slim 3 83MMS00300"
    assert (s.cpu, s.gpu) == ("Ryzen 5 7535HS", "Radeon 660M")
    assert (s.ram_gb, s.armazenamento_gb, s.tipo_armazenamento) == (8, 1024, "SSD")
    assert (s.tela_pol, s.sistema, s.preco) == (15.3, "Linux", 2917.0)
    assert s.garantia_meses == 12 and s.cupom == "sim"
    assert s.link == "https://qual.not.br/g9vbj9tx"


def test_eufs_nao_conta_como_ssd():
    texto = FICHA.replace("SSD 📦 1 TB", "SSD (eUFS) 128 GB")
    assert extrair(oferta(texto), usar_ia=False).specs.tipo_armazenamento == "eUFS"


@pytest.mark.parametrize("texto", [
    "Mouse sem fio Logitech M170\nPor ✅ R$ 49",
    "Suporte p/ notebook ajustável – Até 17″ pol.\nPor ✅ R$ 16",
    "🔴💻 A LIVE DO QNC ESTÁ ONLINE!",
    "PRÉ-VENDA do PlayStation com GTA VI\nPreço de R$ 4.449",
])
def test_prefiltro_descarta(texto):
    assert not parece_notebook(texto)


def test_prefiltro_aceita_ficha_sem_palavra_notebook():
    assert parece_notebook("Acer Nitro Core i5 RAM 16 GB SSD 512 GB por R$ 4.999")


@pytest.mark.skipif(not AMOSTRA.exists(), reason="sem amostras")
def test_amostras_nenhuma_ficha_falha():
    for linha in AMOSTRA.open(encoding="utf-8"):
        d = json.loads(linha)
        d["recebida_em"] = datetime.fromisoformat(d["recebida_em"])
        d["links_extras"] = tuple(d["links_extras"])
        e = extrair(Oferta(**d), usar_ia=False)
        if "💻" in d["texto"] and "R$" in d["texto"] and "LIVE" not in d["texto"]:
            assert e.metodo == "parser", d["texto"][:120]


@pytest.mark.parametrize("texto", [
    "📱 Galaxy S26 Ultra Snapdragon 8 Elite Gen 5 256 GB 12 GB RAM\nDe R$ 11.999 Por R$ 8.999",
    "🔥📱 Motorola Razr 70 MediaTek Dimensity 7450X 8 GB RAM 256 GB\nPor R$ 5.999",
    "👉 Smartphone Samsung Galaxy S25 5G 256GB, 12GB RAM\nR$ 3.999",
    "➡️ Mochila Lenovo Everyday B510 até 15.6\" para notebook GX40Q75214\n✅ R$ 67",
    "PC Gamer KaBuM! AMD Ryzen 5 3400G, GeForce RTX 3050, 8GB DDR4, SSD 512GB\nPor: R$ 3.674,99",
    "Monitor Gamer LG 27\" 180Hz\nR$ 899",
])
def test_prefiltro_descarta_canais_gerais(texto):
    assert not parece_notebook(texto)


@pytest.mark.parametrize("texto", [
    "👉 Notebook Lenovo IdeaPad Slim 3 15ARP10 – AMD Ryzen 7-8840HS Radeon 780M 8GB RAM\nR$ 3.499",
    "Notebook Gamer Lenovo LOQ Core i5-13450HX, RTX 5050 8GB, 16GB RAM DDR5\n💰 R$ 5.499",
    "Samsung Galaxy Book4 Core 5 120U 16GB RAM 512GB SSD\nPor R$ 3.999",
    "🔥 COMBO Notebook ASUS ExpertBook P1 + mouse\nR$ 4.299 · Core i5 16GB",
])
def test_prefiltro_aceita_notebook_de_canal_geral(texto):
    assert parece_notebook(texto)


def test_prefiltro_motorola_achados():
    assert not parece_notebook("📱 Motorola Edge 70 Fusion Snapdragon 7 Gen 3 256 GB 12 GB RAM\nDe R$ 3.999 Por R$ 1.899")


@pytest.mark.parametrize("texto", [
    "🔥 Smartphone Motorola Moto g35 5G 128GB 4GB RAM\n💵 R$ 899\n👉 t.me/cacadordenotebook",
    "🔥 Kit Upgrade Amd Ryzen 5 5600Gt Placa Mae Msi A520M\n💵 R$ 1.113,00\nhttps://t.me/cacadordenotebook",
    "🌙 Preço à vista R$59,99 Memoria Notebook TGT Shiver 100, 8GB (1x8GB), DDR3",
])
def test_prefiltro_rodape_e_acessorio_antes(texto):
    assert not parece_notebook(texto)


def test_prefiltro_notebook_com_rodape_continua_passando():
    assert parece_notebook("🔥 Notebook ASUS Vivobook 16 Intel Core i7, 8GB, 512GB SSD\n💵 R$ 2.999\nt.me/cacadordenotebook")


@pytest.mark.parametrize("texto", [
    ("🔥 Smartphone Motorola Moto g35 5G - 128GB 4GB RAM\n\n💵 R$ 829,00 em 10x\n\n🔗 Link do produto:\n"
     "https://aoferta.net/x\n\n⚡️SE LIGA NOS OUTROS CANAIS⚡️\n💻SÓ NOTEBOOKS: https://t.me/cacadordenotebook"),
    "🖤 Black Friday Pichau! 🖤\n\nPichau Kit upgrade, AMD Ryzen 5 9600X, A620M DDR5, 16GB\n\n🛒 Oferta a partir de R$3.197,28",
    "🌙 PRUUMO DA MADRUGADA! 🌙\nPreço à vista R$59,99\nMemoria Notebook TGT Shiver 100, 8GB (1x8GB), DDR3",
])
def test_prefiltro_casos_reais_tecnoart_pichau(texto):
    assert not parece_notebook(texto)


def test_prefiltro_pelando_linha_unica_com_link():
    assert parece_notebook("Notebook Acer Nitro V16 Core i5 RTX 5060 16 💰 R$ 6589,00 📍 Mercado Livre ➡️ https://pelando.com.br/d/x")
