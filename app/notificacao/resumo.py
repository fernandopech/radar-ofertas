"""Resumo semanal: os "quase" de marketplace que não viraram notificação."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos: Brasília é UTC−3 (sem horário de verão)
    FUSO = timezone(timedelta(hours=-3))

DIAS = {"segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3, "sexta": 4,
        "sabado": 5, "sábado": 5, "domingo": 6}


def proximo_envio(agora: datetime, dia: str, hora: int) -> datetime:
    """Próxima ocorrência de `dia` às `hora`h no horário de Brasília (sempre no futuro)."""
    local = agora.astimezone(FUSO)
    alvo = local.replace(hour=hora, minute=0, second=0, microsecond=0)
    alvo += timedelta(days=(DIAS[dia.lower()] - local.weekday()) % 7)
    if alvo <= local:
        alvo += timedelta(days=7)
    return alvo


def _brl(v: Any) -> str:
    return f"R$ {float(v):,.0f}".replace(",", ".") if v is not None else "?"


def formatar_resumo(itens: list[dict]) -> str:
    if not itens:
        return ("🗓️ <b>Resumo da semana · OLX</b>\n\n"
                "Nenhum usado chegou perto esta semana. Sigo de olho.")
    blocos = [f"🗓️ <b>Resumo da semana · OLX</b>\n"
              f"<i>{len(itens)} usado(s) que chegaram perto, mas não passaram. Vale bater o olho.</i>"]
    for i, r in enumerate(itens, 1):
        a = r.get("avaliacao_json") or {}
        calc = a.get("calculo_usado") or {}
        linha = [f"<b>{i}. {escape(r.get('modelo') or 'Notebook')}</b>  ·  {_brl(r.get('preco'))}"]
        detalhe = [f"⭐ {float(r['nota']):g}/10".replace(".", ",") if r.get("nota") is not None else None,
                   f"📍 {escape(r['local'])}" if r.get("local") else None]
        linha.append("   ".join(x for x in detalhe if x))
        if calc.get("referencia"):
            linha.append(f"📊 usados parecidos: ~{_brl(calc['referencia'])}")
        if a.get("por_que"):
            linha.append(f"💬 {escape(a['por_que'])}")
        if r.get("link"):
            linha.append(f'<a href="{escape(r["link"])}">ver anúncio</a>')
        blocos.append("\n".join(linha))
    return "\n\n".join(blocos)
