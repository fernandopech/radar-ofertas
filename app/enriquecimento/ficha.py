"""Busca a ficha técnica completa de uma oferta (só para quem passou nas regras duras).

Hoje entende o site Qual Notebook Comprar (link "Mais detalhes no site" dos posts
do canal QNC) e resolve os links encurtados qual.not.br para descobrir a loja.
Acessos são poucos e espaçados; qualquer falha devolve o que deu pra obter.
"""
from __future__ import annotations

import html
import logging
import re
import time
import urllib.request
from dataclasses import dataclass, field
import urllib.parse
from urllib.parse import parse_qs, urlparse

from app.dedup import codigo_modelo
from app.oferta import Oferta

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) projeto-automacao-ofertas (uso pessoal)"
INTERVALO_S = 2.0  # entre acessos ao mesmo site
_ultimo_acesso = 0.0
_cache: dict[str, str | None] = {}

# Campos da ficha do QNC que interessam pra avaliação (classe CSS -> rótulo).
CAMPOS_QNC = {
    "spec_cpu_model": "CPU",
    "spec_cpu_cores_and_threads": "núcleos",
    "spec_gpu_type": "tipo de GPU",
    "spec_gpu_family": "família da GPU",
    "spec_gpu_model": "modelo da GPU",
    "spec_gpu_memory": "memória da GPU",
    "spec_ram_installed_capacity_and_type": "RAM instalada",
    "spec_ram_speed": "velocidade da RAM",
    "spec_ram_max_capacity": "RAM máxima",
    "spec_ram_onboard": "RAM soldada",
    "spec_ram_slot_1": "slot de RAM 1",
    "spec_ram_slot_2": "slot de RAM 2",
    "spec_ssd_installed_capacity": "SSD",
    "spec_ssd_installed_type": "tipo do SSD",
    "spec_m2_slot_1": "slot M.2 1",
    "spec_m2_slot_2": "slot M.2 2",
    "spec_display_backlight_and_size": "tela",
    "spec_display_resolution": "resolução",
    "spec_display_panel_type": "painel",
    "spec_display_refresh_rate": "taxa de atualização",
    "spec_display_luminance": "brilho",
    "spec_display_srgb": "sRGB",
    "spec_keyboard_has_illumination": "teclado iluminado",
    "spec_battery_mah_and_wh": "bateria",
    "spec_ac_adapter_watts": "carregador",
    "spec_dimensions_weight": "peso",
    "spec_laptop_operating_system": "sistema",
}

# Sites de promoção: divulgam a oferta, mas não são a loja.
AGREGADORES = {"boletando", "pelando", "promobit", "benchpromos", "gatry", "quenotebookcomprar"}

LOJAS = {
    "magazinevoce": "Magazine Luiza", "mercadolivre": "Mercado Livre", "mercadolibre": "Mercado Livre", "amazon": "Amazon",
    "kabum": "KaBuM!", "magazineluiza": "Magazine Luiza", "magalu": "Magazine Luiza",
    "casasbahia": "Casas Bahia", "pontofrio": "Ponto", "extra": "Extra", "americanas": "Americanas",
    "fastshop": "Fast Shop", "carrefour": "Carrefour", "terabyteshop": "Terabyte", "pichau": "Pichau",
    "girafa": "Girafa", "lenovo": "Lenovo", "dell": "Dell", "samsung": "Samsung", "acer": "Acer",
    "asus": "ASUS", "avell": "Avell", "vaio": "VAIO", "hp": "HP", "shopee": "Shopee",
    "aliexpress": "AliExpress", "positivotecnologia": "Positivo",
}


@dataclass
class Ficha:
    campos: dict[str, str] = field(default_factory=dict)  # rótulo -> texto da ficha
    fonte_url: str | None = None
    loja: str | None = None
    link_loja: str | None = None
    ram_soldada_gb: int | None = None
    ram_slots: list[str] = field(default_factory=list)    # ex.: ["8 GB", "vazio"]
    ram_expansivel: bool | None = None
    ram_dual_channel: bool | None = None
    preco_justo_min: float | None = None   # faixa de "preço justo" do modelo segundo o site
    preco_justo_max: float | None = None
    veredito_site: str | None = None       # ex.: "É uma ótima oportunidade de compra!"


def _baixar(url: str) -> str | None:
    global _ultimo_acesso
    if url in _cache:
        return _cache[url]
    espera = INTERVALO_S - (time.monotonic() - _ultimo_acesso)
    if espera > 0:
        time.sleep(espera)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            conteudo = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.warning("Não consegui abrir %s: %s", url, e)
        conteudo = None
    _ultimo_acesso = time.monotonic()
    _cache[url] = conteudo
    return conteudo


def _texto(fragmento: str) -> str:
    fragmento = re.sub(r"<i\b.*?</i>", " ", fragmento, flags=re.S)  # tooltips
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def ler_ficha_qnc(pagina: str) -> dict[str, str]:
    campos: dict[str, str] = {}
    # Tooltips guardam HTML dentro de atributos (data-content="<ul><li>..."), o que
    # confunde a busca por </li>. Remove antes.
    pagina = re.sub(r'\sdata-content="[^"]*"', "", pagina)
    for m in re.finditer(r'<(li|p|span|div)\b[^>]*class="(spec_[a-z0-9_]+)[^"]*"[^>]*>(.*?)</\1>', pagina, re.S):
        rotulo = CAMPOS_QNC.get(m.group(2))
        valor = re.sub(r"\s*⚠️?\s*\+ info$", "", _texto(m.group(3)))
        if rotulo and valor and rotulo not in campos:
            campos[rotulo] = valor
    return campos


def _reais(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def ler_preco_justo(pagina: str) -> tuple[float | None, float | None, str | None]:
    m = re.search(r'class="ideal-prices-calcs"[^>]*>(.*?)</p>', pagina, re.S)
    valores = re.findall(r"R\$\s*([\d.]+(?:,\d{2})?)", _texto(m.group(1))) if m else []
    v = re.search(r'class="ideal-prices-alert"[^>]*>(.*?)</p>', pagina, re.S)
    veredito = _texto(v.group(1)) if v else None
    if len(valores) >= 2:
        return _reais(valores[0]), _reais(valores[1]), veredito
    return None, None, veredito


def _gb(texto: str) -> int | None:
    m = re.search(r"(\d+)\s*GB", texto or "")
    return int(m.group(1)) if m else None


def analisar_ram(f: Ficha) -> None:
    """Deduz soldada / slots / expansível / dual-channel a partir da ficha."""
    soldada = f.campos.get("RAM soldada", "")
    f.ram_soldada_gb = None if not soldada else (_gb(soldada) or 0)
    slots = [v.split(":", 1)[-1].strip() for k, v in f.campos.items() if k.startswith("slot de RAM")]
    f.ram_slots = [s for s in slots if "não possui" not in s.lower()]  # slot que não existe
    if not soldada and not f.ram_slots:
        return
    pentes = sum(1 for s in f.ram_slots if _gb(s))
    if f.ram_soldada_gb and pentes == 0:
        # Só memória soldada: costuma ser dual-channel, mas a ficha não garante.
        f.ram_dual_channel = None
    else:
        f.ram_dual_channel = (1 if f.ram_soldada_gb else 0) + pentes >= 2
    tem_slot_vazio = any("vazio" in s.lower() for s in f.ram_slots)
    instalada, maxima = _gb(f.campos.get("RAM instalada", "")), _gb(f.campos.get("RAM máxima", ""))
    f.ram_expansivel = tem_slot_vazio or bool(instalada and maxima and maxima > instalada)


def _desembrulhar(url: str) -> str:
    """Links de afiliado (ex.: click.linksynergy.com/deeplink?murl=...) escondem a loja num parâmetro."""
    for _ in range(3):
        params = parse_qs(urlparse(url).query)
        interno = next((v[0] for k, v in params.items()
                        if k.lower() in {"murl", "url", "u", "ued", "redirect", "dest"} and v[0].startswith("http")), None)
        if not interno:
            break
        url = interno
    return url


def resolver_loja(link: str) -> tuple[str | None, str | None]:
    """Segue o encurtador qual.not.br (redireciona via JavaScript) e diz a loja."""
    destino = link
    if "qual.not.br" in link:
        pagina = _baixar(link)
        if pagina and (m := re.search(r'window\.location\s*=\s*"([^"]+)"', pagina)):
            destino = m.group(1)
        else:
            return None, None
    destino = _desembrulhar(destino)
    host = urlparse(destino).hostname or ""
    partes = host.removeprefix("www.").split(".")
    if any(p in AGREGADORES for p in partes):
        return None, None  # site que divulga a oferta, não a loja que vende
    for p in partes:
        if p in LOJAS:
            return LOJAS[p], destino
    return (partes[0] if partes and partes[0] else None), destino


def buscar_pagina_qnc(codigo: str) -> str | None:
    """Acha a página do modelo no QNC pela busca do site (posts de outros canais não têm o link)."""
    pagina = _baixar(f"https://quenotebookcomprar.com.br/?s={urllib.parse.quote(codigo)}")
    if not pagina:
        return None
    alvo = re.escape(codigo.lower())
    m = re.search(rf'href="(https://quenotebookcomprar\.com\.br/[a-z0-9-]*{alvo}[a-z0-9-]*/?)"', pagina)
    return m.group(1) if m else None


def enriquecer(oferta: Oferta, link_compra: str | None, modelo: str | None = None) -> Ficha:
    f = Ficha()
    # Links do texto também: amostras antigas têm o campo link cortado (bug já corrigido).
    links = [l for l in (oferta.link, *oferta.links_extras) if l]
    links += [u.rstrip(").,;") for u in re.findall(r"https?://\S+", oferta.texto)]
    url_qnc = next((l for l in links if l.startswith("http") and "quenotebookcomprar.com.br" in l), None)
    if not url_qnc and (codigo := codigo_modelo(modelo)):
        url_qnc = buscar_pagina_qnc(codigo)
    if url_qnc and (pagina := _baixar(url_qnc)):
        f.campos = ler_ficha_qnc(pagina)
        f.fonte_url = url_qnc
        f.preco_justo_min, f.preco_justo_max, f.veredito_site = ler_preco_justo(pagina)
        analisar_ram(f)
    if link_compra:
        f.loja, f.link_loja = resolver_loja(link_compra)
    return f
