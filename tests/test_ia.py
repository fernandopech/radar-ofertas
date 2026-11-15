"""Testa a leitura da resposta da IA com respostas simuladas (sem chamar a API)."""
from datetime import datetime, timezone
from types import SimpleNamespace as N

import pytest

from app.extracao import ia
from app.oferta import Oferta

OFERTA = Oferta(fonte="t", id_externo="1", texto="Notebook X Ryzen 5 16GB por R$ 3.000",
                recebida_em=datetime.now(timezone.utc))


def responder(texto: str, stop_reason: str = "end_turn"):
    resp = N(content=[N(type="thinking", thinking=""), N(type="text", text=texto)],
             usage=N(input_tokens=900, output_tokens=200), stop_reason=stop_reason)
    return N(messages=N(create=lambda **kw: resp))


@pytest.mark.parametrize("texto", [
    '{"eh_oferta_notebook": true, "cpu": "Ryzen 5 7535HS", "ram_gb": 16, "preco": 3000, "modelo": null}',
    'Aqui está:\n```json\n{"eh_oferta_notebook": true, "cpu": "Ryzen 5 7535HS", "ram_gb": 16, "preco": 3000}\n```',
])
def test_resposta_valida(monkeypatch, texto):
    monkeypatch.setattr(ia, "_get_cliente", lambda: responder(texto))
    s = ia.extrair_com_ia(OFERTA)
    assert s.cpu == "Ryzen 5 7535HS" and s.ram_gb == 16 and s.preco == 3000.0
    assert s.modelo == ""  # null em campo de texto vira ""


@pytest.mark.parametrize("texto,stop", [
    ("não sei", "end_turn"),
    ('{"eh_oferta_notebook": true, "ram_gb": "muita"}', "end_turn"),
    ('{"eh_oferta_notebook": true, "condicao": "seminovo"}', "end_turn"),
    ("", "refusal"),
])
def test_resposta_invalida_nao_derruba(monkeypatch, texto, stop):
    monkeypatch.setattr(ia, "_get_cliente", lambda: responder(texto, stop))
    assert ia.extrair_com_ia(OFERTA) is None
