"""Pré-filtro barato: descarta o que claramente não é oferta de notebook.

Erra pro lado de deixar passar: na dúvida, segue pro próximo passo.
Nos canais gerais (Pelando, Boletando...), a maior parte é celular, acessório,
peça de PC etc.; cortar isso aqui evita gastar IA à toa.
"""
from __future__ import annotations

import re

_PRECO = re.compile(r"R\$\s*\d", re.I)
_NOTEBOOK = re.compile(r"💻|\bnotebooks?\b|\blaptops?\b|\bultrabooks?\b|\bchromebooks?\b|\bmacbook", re.I)
_SPEC_RAM = re.compile(r"\b\d{1,2}\s*GB\b.*\b(RAM|DDR\d?)\b|\b(RAM|DDR\d?)\b.*\b\d{1,2}\s*GB\b", re.I | re.S)
_GB = re.compile(r"\b\d{1,4}\s*(GB|TB)\b", re.I)
_CPU = re.compile(r"\b(Core\s*(i\d|Ultra|\d)|Ryzen|Celeron|Pentium|Athlon|Snapdragon|MediaTek|Apple\s*M\d)\b", re.I)

# Produto principal claramente não é notebook (procurado só no título da oferta).
_OUTRO_PRODUTO = re.compile(
    r"📱|\b(smartphones?|celular(es)?|iphone|ipad|tablet|galaxy\s+(s|a|z|m|tab)\s?\d*|redmi|poco\s|xiaomi|"
    r"motorola|moto\s+(g|e|edge)|razr|realme|oneplus|honor\s|pixel\s\d|smartwatch|rel[oó]gio|smart\s*tv|televis[aã]o|monitor|"
    r"placa[\s-]m[aã]e|placa\s+de\s+v[ií]deo|processador|pc\s+gamer|computador\s+(gamer|desktop)|desktop|"
    r"console|playstation|ps5|xbox|nintendo|kindle|kit\s+(upgrade|gamer|pc)|a[2-6]\d0m|b[4-8]\d0m?|"
    r"gabinete|water\s*cooler)\b", re.I)
# "Mochila para notebook", "Suporte p/ notebook", "Mouse ... para notebook"
_ACESSORIO = re.compile(
    r"\b(mochilas?|capas?|case|suportes?|mouse|teclados?|cooler|base|carregador(es)?|fontes?|pel[ií]culas?|"
    r"bolsas?|hub|adaptador(es)?|dock|headset|fones?|mem[oó]ria|ssd|hd\s+externo|maleta|trava)\b", re.I)
_PARA_NOTEBOOK = re.compile(r"\b(para|p/|pra|de)\s+notebooks?\b", re.I)


def _titulo(texto: str) -> str:
    """Primeiras linhas com letras: é onde o canal diz qual é o produto."""
    linhas = [l for l in texto.splitlines() if re.search(r"[A-Za-zÀ-ú]{3}", l)]
    return " ".join(linhas[:3])[:250]


_URL = re.compile(r"(https?://|t\.me/|@)\S+", re.I)
# Acessório/peça escrito ANTES da palavra notebook no título: "Memória Notebook 8GB", "Mochila Notebook".
_ACESSORIO_ANTES = re.compile(
    r"\b(mochilas?|capas?|case|suportes?|mouse|teclados?|cooler|base|carregador(es)?|fontes?|pel[ií]culas?|"
    r"bolsas?|hub|adaptador(es)?|dock|mem[oó]rias?|ssd|hd|maleta|trava|bateria|tela\s+para|cabo)\b"
    r"[^\n]{0,40}?\bnotebooks?\b", re.I)


def parece_notebook(texto: str) -> bool:
    if not _PRECO.search(texto):
        return False
    # Rodapés do tipo "💻 SÓ NOTEBOOKS: https://t.me/..." (linha curta com link) saem inteiros;
    # nas outras linhas, só o link sai. Assim um celular com rodapé não vira notebook.
    linhas = []
    for linha in texto.splitlines():
        if _URL.search(linha):
            resto = _URL.sub(" ", linha)
            if len(re.sub(r"[\W_]+", "", resto)) < 30:
                continue
            linha = resto
        linhas.append(linha)
    texto = "\n".join(linhas)
    titulo = _titulo(texto)
    if _ACESSORIO_ANTES.search(titulo) and not _CPU.search(texto):
        return False
    tem_palavra_notebook = bool(_NOTEBOOK.search(texto))

    if _OUTRO_PRODUTO.search(titulo) and not _NOTEBOOK.search(titulo):
        return False

    if tem_palavra_notebook:
        # Acessório "para notebook" sem processador = não é notebook.
        if _PARA_NOTEBOOK.search(texto) and _ACESSORIO.search(titulo) and not _CPU.search(texto):
            return False
        # Oferta de notebook sempre traz processador ou GB.
        return bool(_CPU.search(texto) or _GB.search(texto))

    # Sem a palavra "notebook": celular, monitor, PC gamer... fora.
    if _OUTRO_PRODUTO.search(titulo):
        return False
    # Aceita se tiver cara de ficha técnica (CPU + RAM).
    return bool(_CPU.search(texto) and _SPEC_RAM.search(texto))
