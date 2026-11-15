# Roadmap

## v1: Telegram

- [x] 1. Setup: estrutura com fontes plugáveis, `.env.example`, `requirements.txt`, `.gitignore`
- [x] 2. Listener: login com Telethon, listar canais, imprimir mensagens novas
- [x] 3. Backfill de teste (`scripts/backfill.py`)
- [x] 4. Extração: pré-filtro, leitor em código e IA (`scripts/extrair.py`)
- [x] 5. Regras + avaliação: listas por nível, ficha do site, preço justo, oportunidade (`scripts/avaliar.py`)
- [x] 6. Supabase: tabela `ofertas` e view `historico_precos` (`scripts/gravar.py`)
- [x] 7. Bot de notificação: veredito, detalhes recolhíveis, botões; monitor `app/main.py`
- [x] 8. Dedup e queda de preço (código do modelo; janela e queda mínima no `criterios.yaml`)
- [x] 9. Deploy 24h no Heroku (`bash scripts/deploy_heroku.sh`; worker Basic)

## v2: expansão

- [ ] 10. Mais canais do Telegram. Levantamento de 09/11/2026 (últimas ~100 mensagens de cada
      canal público, contando ofertas de notebook com o nosso pré-filtro):

      | Canal | Inscritos | Posts/dia | Notebooks/dia | Veredito |
      |---|---|---|---|---|
      | `qualnotebook` (atual) | 55,6 mil | ~10–14 | ~4–6 | já usamos |
      | `boletando_notebooks` | – | ~8 | **~7,7** (96% notebook) | ✅ entrar |
      | `boletando_notebooksgamer` | – | ~3 | **~3,3** (98% notebook) | ✅ entrar |
      | `boletando` (geral) | 14,4 mil | ~51 | ~8,6 | trocar pelos dois acima |
      | `BenchPromos` | 116 mil | ~34 | **~5,7** | entrar |
      | `pelandobr` | 54,4 mil | ~116 | ~2,3 | entrar (ruído é filtrado de graça) |
      | `promotop` | 111 mil | ~57 | ~1,1 | opcional |
      | `TudoPromo` | 10,5 mil | ~8 | ~0,7 | opcional (posts com comentário) |
      | `gpcrpromo` | 45,1 mil | ~35 | ~0,7 | opcional |
      | `cupons_desconto` (Promobit) | 32,3 mil | ~22 | ~0,2 | não vale |
      | `achadosdotb` (Achados do TB) | 17,2 mil | ~4 | ~0,1 | não vale |
      | `ofertaskabum` | 51 mil | ~17 | ~0,3 | não vale (mais PC/peças) |
      | `nerdofertas` | 130 mil | ~580 | 0 | não vale |

      Ajustes feitos para os canais novos:
      - [x] Dedup por código + GPU + RAM + SSD (a linha "LOQ 15IRX9" tem várias configs).
      - [x] Ficha/preço justo: sem link do QNC no post, busca a página no QNC pelo código.
      - [x] Pré-filtro descarta celular, tablet, monitor, PC gamer e acessório "para notebook".
      - [ ] Loja real dos links boletando.com/oferta/... (hoje a loja vem do texto, quando houver).

      Levantamento 2 (14/11/2026, já com o pré-filtro corrigido para rodapés e kits):

      | Canal | Posts/dia | Notebooks/dia | Veredito |
      |---|---|---|---|
      | `cacadordenotebook` (Caçador de Notebooks, do TecnoArt) | ~31 | **~28** (90%) | ✅ entrar |
      | `boletando_notebooks` | ~28 | ~28 (99%) | já entramos (volume subiu na Black Friday) |
      | `BenchPromos` | ~36 | ~7 | já entramos |
      | `tecnoarthardware` (geral) | ~142 | ~6 (repete o Caçador) | ❌ |
      | `pichauofertas` | ~33 | 0 (só peças) | ❌ |
      | `pelandobr` | ~127 | ~1 | já entramos; avaliar se vale o ruído |

      Fora do Telegram (testado em 14/11):
      - Mercado Livre: API pública de busca dá 403 e a página de lista cai em verificação anti-robô.
        Caminho: app oficial no DevCenter do ML (gratuito) com token, ou Actor pago do Apify.
      - Lojas de recondicionado/usado com garantia: Forcetech é Shopify (`/products.json` aberto, fácil
        de consultar); John Notebook, Notebooks Usados, 4M&C, Portal One e Dell Outlet bloqueiam ou não
        têm catálogo aberto.
      - Ofertas de outros canais vão para a extração por IA (~US$ 0,0005 cada; ~20/dia ≈ US$ 0,30/mês).
- [ ] 11. **Avaliador sob demanda pelo bot**: você manda pro bot um link, texto ou post
      encaminhado, e ele responde com veredito, nota e porquê (mesma avaliação das notificações).
      - Bot passa a ler mensagens (long polling no mesmo processo), aceitando só o seu `BOT_CHAT_ID`.
      - Reusa extração por IA, regras, ficha do site e avaliação; mostra também por que
        reprovaria nas regras duras, em vez de ficar calado.
      - Links de Amazon/Mercado Livre bloqueiam leitura automática: a IA avalia pelo texto
        e marca o que não deu pra confirmar como incerteza.
- [ ] 12. Mercado Livre (testar a API primeiro)
- [ ] 13. Facebook Marketplace (AI Marketplace Monitor como serviço separado)
- [x] 14a. OLX (Grande Porto Alegre) via API omkarcloud no RapidAPI (plano grátis, 1.000 consultas/mês):
      busca no RS a cada 2 h, filtra as 34 cidades da RMPA, detalhes só dos novos, anti-golpe
      (usado < 45% do preço do novo, ou alerta da IA). Se valer a pena: proxy residencial + versão
      open source sem limite. Ideias de anti-golpe adaptadas do radar-de-achados (MIT).
- [ ] 14b. Facebook Marketplace via Apify (sem login).
- [x] 14c. Usados: tabela de defeitos (grave reprova, moderado soma reparo ao preço), referência
      de preço (mediana de usados parecidos; sem eles, depreciação pela idade), anti-golpe por IQR,
      nota mínima 7 sem penalizar "usado", resumo semanal dos "quase" (domingo 19h).
- [ ] Enjoei e lojas de recondicionado, se ainda fizer sentido
- [ ] Imagens: ler preço em promo que só tem imagem (medir com `tem_imagem` antes)
