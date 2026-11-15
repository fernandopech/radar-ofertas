"""Registro do banco e cliente REST (sem rede: urlopen simulado)."""
import json
from datetime import datetime, timezone

import pytest

from app import banco as banco_mod
from app.avaliacao import Criterios
from app.banco import Banco
from app.config import ConfigFaltando
from app.oferta import Oferta
from app.processamento import processar, registro

C = Criterios.carregar()


def oferta(texto, link=None):
    return Oferta(fonte="telegram:x", id_externo="1:2", texto=texto,
                  recebida_em=datetime(2026, 11, 9, tzinfo=timezone.utc), link=link)


def test_registro_prefiltro_tem_campos_obrigatorios():
    r = registro(processar(oferta("Live no ar! https://youtu.be/x", link="/youtu.be/x\n👆"), C, usar_ia=False))
    assert r["metodo_extracao"] == "prefiltro" and r["eh_oferta_notebook"] is False
    assert r["aprovado"] is False and r["oportunidade"] is False
    assert r["link"] == "https://youtu.be/x"  # link quebrado das amostras antigas é corrigido


def test_registro_notebook_reprovado():
    texto = ("💻 Lenovo IdeaPad Slim 3 83MMS00300\nRyzen 5 7535HS | Radeon 660M\n"
             "RAM 8 GB | SSD 512 GB | Linux\nTela LED 15,3″ pol. | WUXGA IPS\n✅ Por R$ 2.917 à vista")
    r = registro(processar(oferta(texto), C, usar_ia=False, usar_site=False))
    assert r["modelo"] == "Lenovo IdeaPad Slim 3 83MMS00300" and r["preco"] == 2917.0
    assert r["passou_regras_duras"] is False and "RAM 8 GB" in r["motivo_reprovacao"]
    assert r["cupom"] is None  # texto vazio vira NULL
    json.dumps(r, default=str)  # serializável


def test_recusa_chave_publica():
    with pytest.raises(ConfigFaltando):
        Banco("https://x.supabase.co", "sb_publishable_abc")


class _Resp:
    def __init__(self, corpo):
        self.corpo = corpo

    def read(self):
        return json.dumps(self.corpo).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("chave,tem_bearer", [("sb_secret_abc", False), ("eyJhbGciOi.x.y", True)])
def test_gravar_upsert(monkeypatch, chave, tem_bearer):
    pedidos = []

    def falso_urlopen(req, timeout):
        pedidos.append(req)
        return _Resp([{"id": 42}])

    monkeypatch.setattr(banco_mod.urllib.request, "urlopen", falso_urlopen)
    b = Banco("https://x.supabase.co", chave)
    assert b.gravar({"fonte": "f", "id_externo": "1"}) == 42
    req = pedidos[0]
    assert req.full_url == "https://x.supabase.co/rest/v1/ofertas?on_conflict=fonte,id_externo"
    assert req.get_method() == "POST"
    assert req.headers["Apikey"] == chave
    assert ("Authorization" in req.headers) is tem_bearer
    assert "merge-duplicates" in req.headers["Prefer"]
