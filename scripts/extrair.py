"""Etapa 4: extrai as specs das amostras e mostra uma tabela pra revisão.

Uso: python -m scripts.extrair                  (pré-filtro + leitor em código + IA quando precisar)
     python -m scripts.extrair --testar-ia 5    (também manda 5 ofertas já lidas pelo código
                                                 para a IA e compara: valida a chave e o prompt)

Saída: amostras/extraidas_<fonte>.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import datetime

from app.config import RAIZ
from app.extracao import extrair
from app.extracao.modelos import Specs
from app.oferta import Oferta

PASTA = RAIZ / "amostras"
CAMPOS_COMPARAR = ["modelo", "cpu", "gpu", "ram_gb", "armazenamento_gb", "tipo_armazenamento",
                   "tela_pol", "sistema", "preco", "condicao", "garantia_meses"]


def carregar(arquivo) -> list[Oferta]:
    ofertas = []
    for linha in arquivo.open(encoding="utf-8"):
        d = json.loads(linha)
        d["recebida_em"] = datetime.fromisoformat(d["recebida_em"])
        d["links_extras"] = tuple(d.get("links_extras") or ())
        ofertas.append(Oferta(**d))
    return ofertas


def linha_tabela(s: Specs) -> str:
    gpu = (s.gpu or "?") + (" (inf.)" if s.gpu_inferida else "")
    armaz = f"{s.armazenamento_gb or '?'}{s.tipo_armazenamento or ''}"
    preco = f"R$ {s.preco:,.0f}".replace(",", ".") if s.preco else "?"
    return (f"{(s.modelo or '?')[:30]:<30} {(s.cpu or '?')[:18]:<18} {gpu[:20]:<20} "
            f"{s.ram_gb or '?':>3}GB {armaz:<8} {s.tela_pol or '?':>4}\" {preco:>10}")


def comparar_com_ia(ofertas_parser: list[tuple[Oferta, Specs]], n: int) -> None:
    from app.extracao.ia import extrair_com_ia

    print(f"\n=== Comparando leitor em código x IA em {n} ofertas ===")
    for i, (oferta, specs_parser) in enumerate(ofertas_parser[:n], 1):
        print(f"→ {i}/{n} chamando IA para {specs_parser.modelo}...", flush=True)
        specs_ia = extrair_com_ia(oferta)
        if specs_ia is None:
            print(f"✗ {oferta.id_externo}: IA falhou (veja o log acima)")
            continue
        difs = [f"{c}: código={getattr(specs_parser, c)!r} IA={getattr(specs_ia, c)!r}"
                for c in CAMPOS_COMPARAR if getattr(specs_parser, c) != getattr(specs_ia, c)]
        status = "✓ iguais" if not difs else f"≠ {len(difs)} diferença(s)"
        print(f"{status} · {specs_parser.modelo}")
        for d in difs:
            print(f"    {d}")


def main(testar_ia: int) -> None:
    arquivos = sorted(p for p in PASTA.glob("*.jsonl") if not p.name.startswith("extraidas_"))
    if not arquivos:
        print("Nenhuma amostra. Rode antes: python -m scripts.backfill")
        return
    for arquivo in arquivos:
        ofertas = carregar(arquivo)
        contagem: Counter[str] = Counter()
        lidas_pelo_codigo: list[tuple[Oferta, Specs]] = []
        saida = PASTA / f"extraidas_{arquivo.name}"
        print(f"\n### {arquivo.name} ({len(ofertas)} mensagens)\n")
        with saida.open("w", encoding="utf-8") as f:
            for o in ofertas:
                e = extrair(o)
                contagem[e.metodo] += 1
                if e.specs and not e.specs.eh_oferta_notebook:
                    contagem["ia_nao_notebook"] += 1
                if e.metodo == "parser":
                    lidas_pelo_codigo.append((o, e.specs))
                if e.specs and e.specs.eh_oferta_notebook:
                    print(f"[{e.metodo:<6}] {linha_tabela(e.specs)}")
                f.write(json.dumps({
                    "id_externo": o.id_externo, "metodo": e.metodo,
                    "specs": e.specs.model_dump() if e.specs else None,
                    "texto": o.texto,
                }, ensure_ascii=False) + "\n")
        print(f"\nResumo: {contagem['parser']} lidas pelo código, {contagem['ia']} pela IA "
              f"({contagem['ia_nao_notebook']} a IA disse que não é notebook), "
              f"{contagem['prefiltro']} descartadas no pré-filtro, {contagem['falhou']} falharam.")
        print(f"Salvo em {saida.relative_to(RAIZ)}")
        if testar_ia:
            comparar_com_ia(lidas_pelo_codigo, testar_ia)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("app.extracao.ia").setLevel(logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--testar-ia", type=int, default=0, metavar="N")
    main(ap.parse_args().testar_ia)
