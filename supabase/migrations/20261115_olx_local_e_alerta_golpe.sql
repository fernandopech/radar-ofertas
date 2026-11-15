-- Aplicada em 15/11/2026: fonte OLX.
alter table public.ofertas
  add column if not exists local text,          -- bairro/cidade (marketplaces)
  add column if not exists alerta_golpe text;   -- motivo de suspeita de golpe, se houver
