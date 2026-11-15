"""Leitor em código para ofertas no formato "ficha técnica" (ex.: canal QNC).

Formato esperado (a ordem das linhas pode variar um pouco):
    💻 Lenovo IdeaPad Slim 3 83MMS00300
    Ryzen 5 7535HS (Série 7000) | Radeon 660M
    RAM 8 GB | SSD 512 GB | Linux
    Tela LED 15,3″ pol. | WUXGA IPS
    Garantia 1 ano
    ✅ Por R$ 2.917 à vista

Devolve None se faltar algum campo essencial; aí quem decide é a IA.
"""
from __future__ import annotations

import re

from app.extracao.modelos import Specs
from app.oferta import Oferta

# Emojis e símbolos decorativos que os canais enfiam no meio das specs.
_DECORACAO = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍Ⓐ-⓿]"
)
_CPU = re.compile(
    r"\b(Core\s*(Ultra\s*)?\d|Core\s*i\d|Ryzen|Celeron|Pentium|Athlon|Snapdragon|MediaTek|Intel\s*N\d)", re.I
)
_PARENTESES = re.compile(r"\s*\((Série|\d+ª ger)[^)]*\)", re.I)
_RAM = re.compile(r"\bRAM\s*(\d{1,3})\s*GB", re.I)
_ARMAZ = re.compile(r"\b(SSD|HDD?|eMMC|eUFS)\b\s*(?:\(([^)]+)\))?\s*(\d+(?:[.,]\d+)?)\s*(GB|TB)", re.I)
_TELA = re.compile(r"Tela\b[^|\n]*?(\d{2}(?:[.,]\d)?)\s*[″\"”']", re.I)
_PRECO_POR = re.compile(r"Por\s*(?:✅\s*)?R\$\s*([\d.]+(?:,\d{1,2})?)", re.I)
_PARCELADO = re.compile(r"((?:em\s*)?at[ée]\s*\d+\s*x\s*de\s*R\$\s*[\d.,]+(?:\s*sem\s*juros)?)", re.I)
_GARANTIA = re.compile(r"Garantia\s*(?:de\s*)?(\d+)\s*(ano|anos|m[eê]s|meses)", re.I)
_CUPOM_CODIGO = re.compile(r"cupom[:\s]+([A-Z0-9]{4,})\b")
_COND_RECOND = re.compile(r"recondicionad|renovad|refurb|vitrine|open\s*box", re.I)
_COND_USADO = re.compile(r"\busad[oa]\b|semi-?nov[oa]", re.I)
_URL = re.compile(r"https?://\S+")


def _limpar(s: str) -> str:
    s = _DECORACAO.sub("", s)
    s = _PARENTESES.sub("", s)
    return re.sub(r"\s+", " ", s).strip(" -|/")


def _numero(s: str) -> float:
    """'2.917' -> 2917 ; '2.917,90' -> 2917.9 ; '15,6' -> 15.6"""
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


def _sistema(linha: str) -> str | None:
    l = linha.lower()
    if "windows" in l:
        return "Windows"
    if "linux" in l or "ubuntu" in l:
        return "Linux"
    if "sem sistema" in l or "free dos" in l or "freedos" in l:
        return "sem sistema"
    if "macos" in l:
        return "macOS"
    if "chrome" in l:
        return "ChromeOS"
    return None


def ler_ficha(oferta: Oferta) -> Specs | None:
    originais = [l.strip() for l in oferta.texto.splitlines() if l.strip()]
    modelo = next((_limpar(l) for l in originais if l.startswith("💻") and len(_limpar(l)) > 3), None)

    # Daqui pra baixo, sem emojis: "SSD 📦 512 GB" vira "SSD 512 GB".
    texto = re.sub(r"[ \t]+", " ", _DECORACAO.sub("", oferta.texto))
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    cpu = gpu = None
    for l in linhas:
        if "|" in l and _CPU.search(l) and not _RAM.search(l):
            partes = [_limpar(p) for p in l.split("|")]
            cpu = partes[0] or None
            gpu = partes[1] if len(partes) > 1 and partes[1] else None
            break

    ram = int(m.group(1)) if (m := _RAM.search(texto)) else None

    armaz_gb = tipo_armaz = None
    if m := _ARMAZ.search(texto):
        tipo_armaz = m.group(1).upper().replace("HDD", "HD")
        if m.group(2) and m.group(2).lower() == "eufs":
            tipo_armaz = "eUFS"  # anunciado como "SSD (eUFS)", mas não é SSD de verdade
        tipo_armaz = {"EMMC": "eMMC", "EUFS": "eUFS"}.get(tipo_armaz, tipo_armaz)
        valor = _numero(m.group(3))
        armaz_gb = int(valor * 1024 if m.group(4).upper() == "TB" else valor)

    linha_ram = next((l for l in linhas if _RAM.search(l)), "")
    sistema = _sistema(linha_ram)

    tela_pol = tela_tipo = None
    linha_tela = next((l for l in linhas if l.lower().startswith("tela") and _TELA.search(l)), None)
    if linha_tela:
        if m := _TELA.search(linha_tela):
            tela_pol = _numero(m.group(1))
        partes = linha_tela.split("|")
        painel = _limpar(partes[1]) if len(partes) > 1 else ""
        oled = re.search(r"Super AMOLED|AMOLED|OLED", partes[0], re.I)
        tela_tipo = " ".join(x for x in [oled.group(0) if oled else None, painel] if x) or None

    precos = [_numero(p) for p in _PRECO_POR.findall(texto)]
    preco = min(precos) if precos else None
    parcelado = _limpar(m.group(1)) if (m := _PARCELADO.search(texto)) else None

    garantia = None
    if m := _GARANTIA.search(texto):
        n = int(m.group(1))
        garantia = n * 12 if m.group(2).lower().startswith("ano") else n

    cupom = None
    if m := _CUPOM_CODIGO.search(texto):
        cupom = m.group(1)
    elif re.search(r"c/\s*cupom|com\s*cupom|cupom", texto, re.I):
        cupom = "sim"

    if _COND_RECOND.search(texto):
        condicao = "recondicionado"
    elif _COND_USADO.search(texto):
        condicao = "usado"
    else:
        # Formato ficha técnica é de canal que divulga loja, produto novo.
        condicao = "novo"

    urls = [u.rstrip(").,;") for u in _URL.findall(texto)]
    # "Ver na loja" vem depois do link do site de review; prefere o da loja.
    link = next((u for u in urls if "qual.not.br" in u), None) or oferta.link

    essenciais = [modelo, cpu, ram, armaz_gb, preco]
    if any(v is None for v in essenciais):
        return None

    return Specs(
        eh_oferta_notebook=True,
        modelo=modelo,
        marca=modelo.split()[0] if modelo else None,
        cpu=cpu,
        gpu=gpu,
        gpu_inferida=False,
        ram_gb=ram,
        armazenamento_gb=armaz_gb,
        tipo_armazenamento=tipo_armaz,
        tela_pol=tela_pol,
        tela_tipo=tela_tipo,
        sistema=sistema,
        preco=preco,
        preco_parcelado=parcelado,
        cupom=cupom,
        condicao=condicao,
        garantia_meses=garantia,
        vendedor_tipo="loja",
        loja=None,  # link encurtado não diz a loja
        link=link,
    )
