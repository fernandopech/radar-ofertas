"""Identifica o mesmo notebook entre ofertas e decide se vale notificar de novo."""
from __future__ import annotations

import re
from dataclasses import dataclass


def codigo_modelo(modelo: str | None) -> str | None:
    """Código do modelo (part number), se houver: 'Lenovo LOQ 83KH000SBR' -> '83KH000SBR'."""
    if not modelo:
        return None
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-./]*", modelo)
    codigos = [t for t in tokens
               if len(t) >= 6 and re.search(r"\d", t) and re.search(r"[A-Za-z]", t)]
    return codigos[-1].upper().strip("-./") if codigos else None


def _gpu_curta(gpu: str | None) -> str:
    if not gpu:
        return "?"
    gpu = re.sub(r"\b(graphics|geforce|nvidia|amd|intel)\b", " ", gpu, flags=re.I)
    m = re.search(r"\b(RTX|GTX|MX|RX)\s*\d{3,4}\w*|\b\d{3,4}M\b|\bArc\s*\w+|Iris\s*Xe|UHD|Vega", gpu, re.I)
    return re.sub(r"\s+", "", (m.group(0) if m else gpu)).upper()


def chave_modelo(modelo: str | None, gpu: str | None = None, ram_gb: int | None = None,
                 armazenamento_gb: int | None = None) -> str | None:
    """Identidade do notebook para dedup: código (ou nome) + GPU + RAM + SSD.

    O código sozinho às vezes é só a linha ("LOQ 15IRX9"), que tem várias configurações;
    juntar GPU/RAM/SSD evita tratar configs diferentes como a mesma oferta.
    """
    if not modelo:
        return None
    base = codigo_modelo(modelo) or re.sub(r"\s+", " ", modelo).strip().lower()
    return f"{base}|{_gpu_curta(gpu)}|{ram_gb or '?'}|{armazenamento_gb or '?'}"


@dataclass
class Decisao:
    notificar: bool
    queda_de: float | None = None  # preço da última notificação, se caiu
    motivo: str = ""


def decidir(preco: float | None, ultima_notificada: float | None, queda_minima: float) -> Decisao:
    """`ultima_notificada`: preço da última vez que avisamos desse modelo dentro da janela."""
    if ultima_notificada is None:
        return Decisao(True, motivo="novidade")
    if preco is not None and preco <= ultima_notificada - queda_minima:
        return Decisao(True, queda_de=ultima_notificada, motivo="preço caiu")
    return Decisao(False, motivo=f"já avisado por R$ {ultima_notificada:,.0f}".replace(",", "."))
