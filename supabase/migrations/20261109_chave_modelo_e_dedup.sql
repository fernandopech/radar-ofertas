-- Aplicada em 09/11/2026: dedup por código do modelo.
alter table public.ofertas
  add column chave_modelo text,          -- código do modelo (part number), igual entre lojas/canais
  add column motivo_nao_notificado text; -- ex.: "já avisado por R$ 5.124"
create index ofertas_chave_notificado_idx on public.ofertas (chave_modelo, notificado_em desc)
  where notificado_em is not null;
drop view public.historico_precos;
create view public.historico_precos with (security_invoker = true) as
select chave_modelo, max(modelo) as modelo, count(*) as vezes_visto, min(preco) as menor_preco,
       round(avg(preco), 2) as preco_medio, max(preco) as maior_preco,
       min(recebida_em) as primeira_vez, max(recebida_em) as ultima_vez
from public.ofertas
where eh_oferta_notebook and chave_modelo is not null and preco is not null
group by chave_modelo;
-- Preenchimento das ofertas antigas (código = última palavra do modelo):
-- update public.ofertas set chave_modelo = upper(regexp_replace(modelo, '^.*\s', '')) where ...;
