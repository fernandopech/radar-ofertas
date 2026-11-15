"""Teste da API da OLX (omkarcloud no RapidAPI): descobre parâmetros e mede o que volta.

Precisa de RAPIDAPI_KEY no .env. Gasta ~8 das 1.000 consultas grátis do mês.
Uso: python -m scripts.testar_olx
A saída não mostra a chave; pode colar no chat.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import app.config  # noqa: F401  (carrega o .env)

HOST = "best-olx-brazil-scraper-free-1000-calls.p.rapidapi.com"
CHAVE = os.getenv("RAPIDAPI_KEY", "").strip()
gastas = 0


def chamar(caminho: str, **params) -> tuple[int, object]:
    global gastas
    gastas += 1
    url = f"https://{HOST}{caminho}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-RapidAPI-Key": CHAVE, "X-RapidAPI-Host": HOST})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            restantes = r.headers.get("x-ratelimit-requests-remaining")
            corpo = json.loads(r.read().decode() or "null")
            if restantes:
                print(f"   (consultas restantes no mês: {restantes})")
            return r.status, corpo
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def resumo(obj, n=700) -> str:
    return json.dumps(obj, ensure_ascii=False)[:n]


def anuncios(corpo) -> list:
    if isinstance(corpo, list):
        return corpo
    if isinstance(corpo, dict):
        for k in ("ads", "results", "data", "items"):
            if isinstance(corpo.get(k), list):
                return corpo[k]
    return []


def mostrar_busca(nome: str, corpo) -> None:
    ads = anuncios(corpo)
    print(f"   → {len(ads)} anúncios" + ("" if ads else f" | resposta: {resumo(corpo, 300)}"))
    for a in ads[:6]:
        loc = a.get("location") or {}
        preco = (a.get("price") or {}).get("amount")
        print(f"     · {str(a.get('title'))[:60]:<60} R$ {preco} · {loc.get('municipality')}/{loc.get('state')}"
              f" · {a.get('posted_at') or a.get('date')}")
    if ads:
        estados = {(a.get('location') or {}).get('state') for a in ads}
        precos = [(a.get('price') or {}).get('amount') for a in ads if (a.get('price') or {}).get('amount')]
        print(f"     estados: {estados} · preços de {min(precos, default='?')} a {max(precos, default='?')}")
        print(f"     campos de um anúncio: {sorted(ads[0].keys())}")


def main() -> None:
    if not CHAVE:
        sys.exit("Falta RAPIDAPI_KEY no .env (rapidapi.com → a API → campo X-RapidAPI-Key).")

    print("1) Locais do RS com 'Porto Alegre':")
    candidatos = []
    for termo in ("Porto Alegre", "Grande Porto Alegre"):
        st, corpo = chamar("/locations/search", query=termo)
        for r in (corpo or {}).get("results", []) if isinstance(corpo, dict) else []:
            if r.get("state") == "RS":
                print(f"   · id={r.get('id')} · {r.get('name')} · {r.get('description')} · path={r.get('path')}")
                for valor in (r.get("id"), r.get("path")):
                    if valor and valor not in candidatos:
                        candidatos.append(valor)
    candidatos = candidatos[:3] + ["rs"]

    print("\n2) Testando cada local (notebooks, mais recentes, R$ 1.500 a 5.500):")
    for loc in candidatos:
        st, corpo = chamar("/ads/search", query="notebook", category="informatica/notebooks", sort="newest",
                           location=loc, price_min=1500, price_max=5500)
        ads = anuncios(corpo)
        cidades = {}
        for a in ads:
            l = a.get("location") or {}
            chave = f"{l.get('municipality')}/{l.get('state')}"
            cidades[chave] = cidades.get(chave, 0) + 1
        total = corpo.get("count") if isinstance(corpo, dict) else "?"
        datas = sorted(a.get("posted_at") or "" for a in ads)
        janela = f"{datas[0][:16]} → {datas[-1][:16]}" if datas else "-"
        print(f"   location={loc!r}: HTTP {st} · total na busca: {total} · {len(ads)} na página · {janela}")
        print(f"     cidades: {dict(sorted(cidades.items(), key=lambda x: -x[1])[:10])}")
        if st != 200:
            print(f"     erro: {str(corpo)[:300]}")

    print(f"\nConsultas gastas neste teste: {gastas}")


if __name__ == "__main__":
    main()
