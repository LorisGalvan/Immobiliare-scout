-- =====================================================================
--  Migrazione 002 - Editor delle microzone dal sito
--  Supabase -> SQL Editor -> incolla -> Run (una volta; rieseguibile).
-- =====================================================================

-- Chi ha modificato una zona e quando
alter table public.zone add column if not exists modificato_da text;

-- Storico: ogni salvataggio dall'editor conserva la versione completa,
-- così si può sempre tornare indietro.
create table if not exists public.zone_versioni (
  id          bigserial primary key,
  territorio  text not null,
  salvato_da  text,
  ts          timestamptz default now(),
  nota        text,
  zone        jsonb not null           -- [{nome, geojson, props, ordine}, ...]
);
alter table public.zone_versioni enable row level security;
drop policy if exists zone_versioni_lettura on public.zone_versioni;
create policy zone_versioni_lettura on public.zone_versioni for select to authenticated using (true);

-- Microzona assegnata a mano a un annuncio (vince sul calcolo automatico)
create table if not exists public.zona_manuale (
  uid        text primary key,
  territorio text not null,
  microzona  text not null,
  user_email text default (auth.jwt() ->> 'email'),
  aggiornato timestamptz default now()
);
alter table public.zona_manuale enable row level security;
drop policy if exists zona_manuale_lettura on public.zona_manuale;
create policy zona_manuale_lettura on public.zona_manuale for select to authenticated using (true);
drop policy if exists zona_manuale_scrittura on public.zona_manuale;
create policy zona_manuale_scrittura on public.zona_manuale for all to authenticated using (true) with check (true);

-- Salvataggio atomico di tutte le zone di un territorio dall'editor:
-- sostituisce l'elenco, conserva la versione precedente e quella nuova.
create or replace function public.salva_zone(p_territorio text, p_zone jsonb, p_nota text default null)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  n int;
  chi text := auth.jwt() ->> 'email';
begin
  if auth.uid() is null then
    raise exception 'accesso richiesto';
  end if;
  if jsonb_typeof(p_zone) <> 'array' or jsonb_array_length(p_zone) = 0 then
    raise exception 'elenco zone vuoto';
  end if;
  if (select count(distinct z->>'nome') from jsonb_array_elements(p_zone) z) <> jsonb_array_length(p_zone) then
    raise exception 'nomi di zona duplicati';
  end if;

  -- versione precedente (solo al primo salvataggio dall'editor, se non c'è storico)
  if not exists (select 1 from zone_versioni where territorio = p_territorio) then
    insert into zone_versioni (territorio, salvato_da, nota, zone)
    select p_territorio, 'bot', 'versione iniziale',
           coalesce(jsonb_agg(jsonb_build_object('nome', nome, 'geojson', geojson, 'props', props, 'ordine', ordine)
                              order by ordine), '[]'::jsonb)
    from zone where territorio = p_territorio;
  end if;

  delete from zone where territorio = p_territorio;
  insert into zone (territorio, nome, geojson, props, ordine, aggiornato, modificato_da)
  select p_territorio, z->>'nome', z->'geojson', coalesce(z->'props', '{}'::jsonb),
         coalesce((z->>'ordine')::int, ord::int), now(), chi
  from jsonb_array_elements(p_zone) with ordinality as t(z, ord);
  get diagnostics n = row_count;

  insert into zone_versioni (territorio, salvato_da, nota, zone) values (p_territorio, chi, p_nota, p_zone);

  -- le assegnazioni manuali a zone non più esistenti vengono rimosse
  delete from zona_manuale m
   where m.territorio = p_territorio
     and not exists (select 1 from zone z where z.territorio = p_territorio and z.nome = m.microzona);
  return n;
end $$;

revoke all on function public.salva_zone(text, jsonb, text) from public, anon;
grant execute on function public.salva_zone(text, jsonb, text) to authenticated;
