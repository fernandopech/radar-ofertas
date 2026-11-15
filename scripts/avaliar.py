"""Etapa 5: aplica os critérios nas amostras e mostra a tabela pra calibrar o criterios.yaml.

Uso: python -m scripts.avaliar                      (regras + ficha do site + IA)
     python -m scripts.avaliar --margem-preco 1000  (também avalia quem só estourou o preço
                                                     em até R$ 1.000, pra ver o que está perdendo)
     python -m scripts.avaliar --sem-ia --sem-site  (só regras duras, grátis e offline)

Ofertas repetidas (mesmo modelo e preço) são avaliadas uma vez só.
Saída: amostras/avaliadas_<fonte>.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter

from app.avaliacao import Criterios, Resultado, avaliar
from app.config import RAIZ
from app.extracao import extrair
from app.extracao.modelos import Specs
from scripts.extrair import carregar

PASTA = RAIZ / "amostras"


def brl(v: float | None) -> str:
    return f"R$ {v:,.0f}".replace(",", ".") if v is not None else "?"


def icone(r: Resultado) -> str:
    if r.aprovado and r.oportunidade:
        return "🔥"
    if r.aprovado:
        return "✅"
    if r.avaliacao is not None:
        return "🟡" if r.na_margem else "🟠"
    if r.regras.passou or r.na_margem or (r.oportunidade and r.avaliacao is None):
        return "⚪"
    return "❌"


def detalhes(specs: Specs, r: Resultado) -> None:
    a, f = r.avaliacao, r.ficha
    print(f"\n{icone(r)} {specs.modelo} · {brl(specs.preco)}" + (" · ACIMA DO TETO" if r.na_margem else ""))
    if f and f.loja:
        print(f"   loja: {f.loja}")
    if f and f.campos:
        ram = f"RAM: soldada={f.ram_soldada_gb or 0} GB, slots={f.ram_slots or '?'}, " \
              f"dual-channel={f.ram_dual_channel}, expansível={f.ram_expansivel}"
        extras = [f.campos.get(k) for k in ("brilho", "bateria", "peso", "painel") if f.campos.get(k)]
        print(f"   ficha do site: {ram}")
        print(f"                  {' · '.join(extras)}")
    elif f is not None:
        print("   ficha do site: não encontrada")
    cl = r.regras.classes
    if cl:
        tela = ", ".join(f"{n}: {', '.join(t)}" for n, t in cl.get("tela", {}).items()) or "fora das listas"
        print(f"   listas: GPU {cl.get('gpu')} · CPU {cl.get('cpu')} · tela {tela}")
    if f and f.preco_justo_min:
        sinal = "abaixo" if (r.desconto_pct or 0) >= 0 else "acima"
        print(f"   preço justo: {brl(f.preco_justo_min)}–{brl(f.preco_justo_max)} "
              f"(oferta {abs(r.desconto_pct or 0):.0f}% {sinal} do mínimo)")
    if r.regras.ausentes:
        print(f"   dados ausentes: {', '.join(r.regras.ausentes)}")
    if a:
        print(f"   nota {a.nota:g}/10 · CS2: {a.roda_cs2} · {r.motivo}")
        for p in a.pontos_fortes:
            print(f"   ✅ {p}")
        for p in a.pontos_fracos + a.incertezas:
            print(f"   ⚠️ {p}")
        print(f"   → {a.resumo}")
    else:
        print(f"   {r.motivo}")


def main(margem: float, usar_ia: bool, usar_site: bool) -> None:
    c = Criterios.carregar()
    arquivos = sorted(p for p in PASTA.glob("*.jsonl")
                      if not p.name.startswith(("extraidas_", "avaliadas_")))
    for arquivo in arquivos:
        ofertas = carregar(arquivo)
        print(f"\n### {arquivo.name}: teto R$ {c.preco_max:,.0f}".replace(",", ".")
              + (f" (+ margem de teste R$ {margem:,.0f})".replace(",", ".") if margem else ""))
        print(f"\n{'':2} {'MODELO':<36} {'PREÇO':>9}  MOTIVO")
        ja_vistos: dict[tuple, Resultado] = {}
        fora_das_listas: dict[str, set[str]] = {"GPU": set(), "CPU": set()}
        para_detalhar: list[tuple[Specs, Resultado]] = []
        contagem: Counter[str] = Counter()
        saida = PASTA / f"avaliadas_{arquivo.name}"
        with saida.open("w", encoding="utf-8") as fout:
            for o in ofertas:
                e = extrair(o, usar_ia=usar_ia)
                if not e.specs or not e.specs.eh_oferta_notebook:
                    continue
                s = e.specs
                chave = (s.modelo, s.preco)
                repetida = chave in ja_vistos
                r = ja_vistos.get(chave) or avaliar(o, s, c, usar_ia=usar_ia, usar_site=usar_site,
                                                    margem_preco=margem)
                ja_vistos[chave] = r
                contagem[icone(r)] += 1
                chegou_na_ia = r.regras.passou or r.na_margem or r.oportunidade
                for nome, valor in (("GPU", s.gpu), ("CPU", s.cpu)):
                    classe = r.regras.classes.get(nome.lower())
                    tem_niveis = set(c.componentes.get(nome.lower(), {})) - {"excluir"}
                    if chegou_na_ia and tem_niveis and valor and classe and classe.nivel is None:
                        fora_das_listas[nome].add(valor)
                if not repetida and (r.avaliacao or r.regras.passou or r.na_margem or r.oportunidade):
                    para_detalhar.append((s, r))
                print(f"{icone(r)} {s.modelo[:36]:<36} {brl(s.preco):>9}  {r.motivo}"
                      + ("  (repetida)" if repetida else ""))
                fout.write(json.dumps({
                    "id_externo": o.id_externo, "modelo": s.modelo, "preco": s.preco,
                    "passou_regras": r.regras.passou, "motivos": r.regras.motivos,
                    "ausentes": r.regras.ausentes, "na_margem": r.na_margem,
                    "aprovado": r.aprovado, "oportunidade": r.oportunidade,
                    "desconto_pct": r.desconto_pct,
                    "avaliacao": r.avaliacao.model_dump() if r.avaliacao else None,
                    "loja": r.ficha.loja if r.ficha else None,
                    "ficha": r.ficha.campos if r.ficha else None,
                }, ensure_ascii=False) + "\n")

        print("\nLegenda: ✅ aprovada (notificaria) · 🔥 oportunidade: fora do teto, mas bem abaixo do "
              "preço justo (notificaria) · 🟠 passou nas regras, nota baixa · 🟡 só estourou o preço "
              "(margem de teste) · ⚪ passou, sem IA · ❌ reprovada")
        print("Totais: " + " · ".join(f"{k} {v}" for k, v in contagem.most_common()))
        for nome, valores in fora_das_listas.items():
            if valores:
                print(f"{nome} fora das listas do criterios.yaml (a IA julgou sozinha): "
                      + ", ".join(sorted(valores)))
        if para_detalhar:
            print("\n=== Detalhes das que passaram (ou ficaram na margem) ===")
            for s, r in para_detalhar:
                detalhes(s, r)
        print(f"\nSalvo em {saida.relative_to(RAIZ)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--margem-preco", type=float, default=0, metavar="R$")
    ap.add_argument("--sem-ia", action="store_true")
    ap.add_argument("--sem-site", action="store_true")
    a = ap.parse_args()
    main(a.margem_preco, not a.sem_ia, not a.sem_site)
