"""Deduplicação: mesmo modelo repostado só notifica de novo se o preço caiu."""
import pytest

from app.dedup import chave_modelo, codigo_modelo, decidir


@pytest.mark.parametrize("modelo,codigo", [
    ("Lenovo LOQ 83KH000SBR", "83KH000SBR"),
    ("Notebook Lenovo LOQ 15IRX9 i5-14500HX 83KH000SBR", "83KH000SBR"),  # outro canal, mesmo modelo
    ("ASUS VivoBook 15 X1504MA-BQ244W", "X1504MA-BQ244W"),
    ("HP 200 G2i E30QDAT", "E30QDAT"),
    ("Dell Inspiron 15", None),
    ("", None),
])
def test_codigo_modelo(modelo, codigo):
    assert codigo_modelo(modelo) == codigo


def test_chave_junta_config():
    a = chave_modelo("Lenovo LOQ 83KH000SBR", "GeForce RTX 3050", 16, 1024)
    b = chave_modelo("Notebook Lenovo LOQ 15IRX9 83KH000SBR", "RTX 3050 6GB", 16, 1024)
    assert a == b == "83KH000SBR|RTX3050|16|1024"
    # Mesma linha ("15IRX9"), configurações diferentes: não são a mesma oferta
    i5 = chave_modelo("Lenovo LOQ 15IRX9", "RTX 3050", 16, 512)
    i7 = chave_modelo("Lenovo LOQ 15IRX9", "RTX 4050", 16, 512)
    assert i5 != i7
    assert chave_modelo("Dell Inspiron 15", "Iris Xe Graphics", 8, 256) == "dell inspiron 15|IRISXE|8|256"
    assert chave_modelo("") is None
    assert chave_modelo("X", "Arc Graphics 140T", 16, 512) != chave_modelo("X", "Arc Graphics 130T", 16, 512)


def test_decidir():
    assert decidir(5124, None, 50).notificar                      # novidade
    d = decidir(5000, 5124, 50)
    assert d.notificar and d.queda_de == 5124                      # caiu R$ 124
    assert not decidir(5100, 5124, 50).notificar                   # caiu só R$ 24
    assert not decidir(5124, 5124, 50).notificar                   # repost igual
    assert "já avisado por R$ 5.124" in decidir(5359, 5124, 50).motivo
