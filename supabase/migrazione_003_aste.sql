-- Aste giudiziarie riconosciute dal testo degli annunci (pagina "Aste" del sito).
-- Da eseguire una volta nel SQL Editor di Supabase. Non cancella nulla: aggiunge solo colonne.
alter table public.annunci add column if not exists tipo_vendita text default 'compravendita';
alter table public.annunci add column if not exists indizi_vendita jsonb default '[]'::jsonb;
alter table public.annunci add column if not exists prezzo_base numeric;
alter table public.annunci add column if not exists offerta_minima numeric;
alter table public.annunci add column if not exists data_asta date;
alter table public.annunci add column if not exists scostamento_minima_pct numeric;
alter table public.annunci add column if not exists valore_mercato numeric;
create index if not exists annunci_tipo_idx on public.annunci (territorio, tipo_vendita);
