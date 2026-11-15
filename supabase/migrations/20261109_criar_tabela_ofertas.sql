-- Aplicada no projeto Supabase "projeto-automacao-ofertas" em 09/11/2026.
create table public.ofertas (
  id bigint generated always as identity primary key,
  fonte text not null,
  id_externo text not null,
  recebida_em timestamptz not null,
  gravada_em timestamptz not null default now(),
  texto_original text not null,
  link text,
  link_origem text,
  tem_imagem boolean not null default false,
  metodo_extracao text not null,            -- prefiltro | parser | ia | falhou
  eh_oferta_notebook boolean,
  modelo text, marca text, cpu text, gpu text, gpu_inferida boolean,
  ram_gb integer, ram_expansivel boolean, ram_dual_channel boolean,
  armazenamento_gb integer, tipo_armazenamento text,
  tela_pol numeric(4,1), tela_tipo text, sistema text,
  preco numeric(10,2), preco_parcelado text, cupom text,
  condicao text, garantia_meses integer, vendedor_tipo text, loja text,
  passou_regras_duras boolean,
  motivo_reprovacao text,
  dados_ausentes text[],
  classes jsonb,
  ficha jsonb,
  preco_justo_min numeric(10,2),
  preco_justo_max numeric(10,2),
  desconto_pct numeric(6,2),
  nota numeric(4,1),
  aprovado boolean not null default false,
  oportunidade boolean not null default false,
  avaliacao_json jsonb,
  notificado_em timestamptz,
  constraint ofertas_fonte_id_externo_key unique (fonte, id_externo)
);
create index ofertas_modelo_recebida_idx on public.ofertas (modelo, recebida_em desc) where modelo is not null;
create index ofertas_notificadas_idx on public.ofertas (notificado_em desc) where notificado_em is not null;
-- Só o backend (chave secreta, que ignora RLS) lê e grava. Nenhum acesso público.
alter table public.ofertas enable row level security;

create view public.historico_precos with (security_invoker = true) as
select modelo, count(*) as vezes_visto, min(preco) as menor_preco, round(avg(preco), 2) as preco_medio,
       max(preco) as maior_preco, min(recebida_em) as primeira_vez, max(recebida_em) as ultima_vez
from public.ofertas
where eh_oferta_notebook and modelo is not null and preco is not null
group by modelo;
