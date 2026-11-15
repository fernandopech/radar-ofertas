"""Monta a notificação a partir do registro da oferta (dict do banco).

Formato: veredito e o essencial visíveis; o resto numa citação recolhível
(toque pra abrir) e botões para a loja e o post original.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Any

VEREDITOS = {
    "comprar_agora": "🟢 <b>COMPRAR AGORA</b>",
    "esperar": "🟡 <b>VALE ESPERAR</b>",
    "nao_compensa": "🔴 <b>NÃO COMPENSA</b>",
}


@dataclass
class Mensagem:
    texto: str
    botoes: list[tuple[str, str]] = field(default_factory=list)  # (rótulo, url)


def _brl(v: Any) -> str:
    return f"R$ {float(v):,.0f}".replace(",", ".") if v is not None else "preço ?"


def _armaz(gb: int) -> str:
    return f"{gb // 1024} TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb} GB"


def _condicao(r: dict[str, Any]) -> str:
    cond, vendedor, garantia = r.get("condicao"), r.get("vendedor_tipo"), r.get("garantia_meses")
    if cond == "usado" or vendedor == "pessoa_fisica":
        return "⚠️ USADO · SEM GARANTIA"
    if cond == "recondicionado":
        return f"RECONDICIONADO ({garantia} meses de garantia)" if garantia else "RECONDICIONADO"
    if cond == "novo":
        return "NOVO"
    return "condição ?"


def _veredito(r: dict[str, Any], a: dict[str, Any]) -> str:
    v = a.get("veredito")
    if not v:  # avaliações antigas, sem veredito
        v = "comprar_agora" if float(a.get("nota", r.get("nota") or 0)) >= 8 else "esperar"
    return VEREDITOS.get(v, VEREDITOS["esperar"])


def _eh_marketplace(r: dict[str, Any]) -> bool:
    return (r.get("fonte") or "").split(":", 1)[0] in {"olx", "facebook"}


def formatar(r: dict[str, Any], *, queda_de: float | None = None, teto: float | None = None,
             teste: bool = False) -> Mensagem:
    """`queda_de` = preço anterior quando o preço caiu; `teto` = preço máximo dos critérios.

    Layout com respiro: blocos separados por linha em branco; o essencial fica visível e o
    resto numa citação recolhível.
    """
    a = r.get("avaliacao_json") or {}
    desconto = float(r["desconto_pct"]) if r.get("desconto_pct") is not None else None
    marketplace = _eh_marketplace(r)
    blocos: list[list[str]] = []

    # 1. Veredito
    topo = _veredito(r, a)
    if r.get("oportunidade"):
        topo += "  ·  🔥 oportunidade"
    if queda_de:
        topo += "  ·  📉 baixou"
    blocos.append((["🧪 <i>teste</i>"] if teste else []) + [topo])

    # 2. O quê, quanto, onde
    produto = [f"💻 <b>{escape(r.get('modelo') or 'Notebook')}</b>"]
    preco = f"💰 <b>{_brl(r.get('preco'))}</b>"
    if r.get("loja") and not marketplace:
        preco += f" na {escape(r['loja'])}"
    if queda_de:
        preco += f"  (era {_brl(queda_de)})"
    produto.append(preco)
    if r.get("local"):
        nome_fonte = "OLX" if (r.get("fonte") or "").startswith("olx") else "Marketplace"
        produto.append(f"📍 {escape(r['local'])} · {nome_fonte}")
    calc = a.get("calculo_usado") or {}
    if marketplace and calc:
        if calc.get("custo_reparo"):
            produto.append(f"🔧 Reparos: +{_brl(calc['custo_reparo'])}  →  <b>{_brl(calc.get('preco_efetivo'))}</b> efetivo")
        if calc.get("referencia"):
            if calc.get("ref_comparaveis"):
                ref = f"📊 Usados parecidos na região: ~{_brl(calc['ref_comparaveis'])} ({calc.get('n_comparaveis')} anúncios)"
            else:
                orig = f"original ~{_brl(calc['preco_original'])}" if calc.get("preco_original") else "pela idade"
                ref = f"📊 Vale ~{_brl(calc['ref_depreciacao'])} como usado ({orig}, {calc.get('ano')}, estimativa)"
            produto.append(ref)
            d = calc.get("desconto_pct")
            if d is not None and abs(d) >= 1:
                produto.append(f"{'📉' if d > 0 else '📈'} {abs(d):.0f}% {'abaixo' if d > 0 else 'acima'} da referência")
    elif desconto is not None and abs(desconto) >= 1:
        produto.append(f"📉 {abs(desconto):.0f}% {'abaixo' if desconto > 0 else 'acima'} do preço justo")
    blocos.append(produto)

    # 3. Nota e condição (CS2 é checado por dentro, não aparece)
    nota = a.get("nota", r.get("nota"))
    resumo = [f"⭐ {float(nota):g}/10".replace(".", ",") if nota is not None else None, _condicao(r)]
    blocos.append(["   ·   ".join(escape(x) for x in resumo if x)])

    # 4. Alerta de golpe (destaque, fora do recolhido)
    if r.get("alerta_golpe"):
        blocos.append([f"🚨 <b>Atenção, possível golpe:</b> {escape(r['alerta_golpe'])}",
                       "<i>Não pague antes de ver e testar pessoalmente.</i>"])
    elif marketplace and _condicao(r).startswith("⚠️"):
        blocos.append(["<i>Combine de ver e testar pessoalmente antes de pagar.</i>"])

    # 5. Por quê
    frase = a.get("por_que") or a.get("resumo")
    if frase:
        blocos.append([f"💬 {escape(frase)}"])

    # 6. Detalhes (recolhido), em seções
    secoes: list[str] = []
    spec = " · ".join(x for x in (
        r.get("cpu"), r.get("gpu"),
        f"{r['ram_gb']} GB RAM" if r.get("ram_gb") else None,
        f"{_armaz(r['armazenamento_gb'])} {r.get('tipo_armazenamento') or ''}".strip()
        if r.get("armazenamento_gb") else None,
        f"{float(r['tela_pol']):g}\"".replace(".", ",") if r.get("tela_pol") else None,
    ) if x)
    if spec:
        secoes.append("⚙️ <b>Configuração</b>\n" + escape(spec))
    fortes = a.get("pontos_fortes", [])[:4]
    if fortes:
        secoes.append("✅ <b>Pontos fortes</b>\n" + "\n".join(f"• {escape(p)}" for p in fortes))
    if marketplace and (calc.get("reparos") or calc.get("leves")):
        estado = [f"• {escape(x)}" for x in calc.get("reparos", []) + calc.get("leves", [])]
        secoes.append("🩹 <b>Estado (pelo anúncio)</b>\n" + "\n".join(estado))
    atencao = (a.get("pontos_fracos", []) + a.get("incertezas", []))[:4]
    if atencao:
        secoes.append("⚠️ <b>Atenção</b>\n" + "\n".join(f"• {escape(p)}" for p in atencao))
    extras = []
    if r.get("preco_justo_min"):
        justo = f"💲 Preço justo{' do novo' if marketplace else ''}: {_brl(r['preco_justo_min'])} – {_brl(r.get('preco_justo_max'))}"
        if teto:
            justo += f"  ·  teu teto: {_brl(teto)}"
        extras.append(justo)
    if r.get("preco_parcelado"):
        extras.append(f"💳 {escape(r['preco_parcelado'])}")
    if r.get("cupom"):
        extras.append("🎟️ " + ("precisa de cupom (veja no post)" if r["cupom"] == "sim" else f"cupom {escape(r['cupom'])}"))
    fonte = (r.get("fonte") or "").split(":", 1)[-1]
    if fonte:
        extras.append(f"📡 {escape(fonte)}")
    if extras:
        secoes.append("\n".join(extras))
    if secoes:
        blocos.append(["<blockquote expandable>📋 <b>Detalhes</b>\n\n" + "\n\n".join(secoes) + "</blockquote>"])

    texto = "\n\n".join("\n".join(b) for b in blocos)
    rotulo_link = "🛒 Ver anúncio" if marketplace else "🛒 Ver na loja"
    botoes = [(rotulo_link, r.get("link") or "")]
    if not marketplace:
        botoes.append(("📄 Post original", r.get("link_origem") or ""))
    return Mensagem(texto, [b for b in botoes if b[1]])
