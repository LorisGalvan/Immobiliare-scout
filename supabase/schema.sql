-- =====================================================================
--  Scout Immobili - schema Supabase
--  Da eseguire una volta: Supabase -> SQL Editor -> incolla -> Run.
--  Rieseguibile: crea solo ciò che manca.
-- =====================================================================

-- Microzone (poligoni GeoJSON)
create table if not exists public.zone (
  territorio  text not null,
  nome        text not null,
  geojson     jsonb not null,          -- Feature geometry (lon/lat)
  props       jsonb default '{}'::jsonb,
  ordine      int,
  aggiornato  timestamptz default now(),
  primary key (territorio, nome)
);

-- Annunci analizzati (un record per immobile, doppioni già uniti)
create table if not exists public.annunci (
  uid                   text primary key,
  territorio            text not null,
  source                text,
  url                   text,
  titolo                text,
  descrizione           text,
  prezzo                numeric,
  mq                    numeric,
  prezzo_mq             numeric,
  piano                 text,
  ascensore             boolean,
  bagni                 int,
  locali                int,
  stato                 text,
  agenzia               text,
  privato               boolean,
  data_pubblicazione    date,
  indirizzo             text,
  lat                   double precision,
  lon                   double precision,
  microzona             text,
  fascia                text,
  riferimento_mq        numeric,
  scostamento_pct       numeric,
  scostamento_grezzo_pct numeric,
  base_confronto        text,
  coeff                 numeric,
  occasione             boolean default false,
  giorni_online         int,
  ribasso_pct           numeric,
  prezzo_iniziale       numeric,
  first_seen            date,
  last_seen             date,
  attivo                boolean default true,
  removed_at            date,
  flags                 jsonb default '[]'::jsonb,
  doppioni              jsonb default '[]'::jsonb,
  zona_omi              text,
  omi_min               numeric,
  omi_max               numeric,
  run_id                text,
  aggiornato            timestamptz default now()
);
-- aste (vedi migrazione_003_aste.sql per i database già creati)
alter table public.annunci add column if not exists tipo_vendita text default 'compravendita';
alter table public.annunci add column if not exists indizi_vendita jsonb default '[]'::jsonb;
alter table public.annunci add column if not exists prezzo_base numeric;
alter table public.annunci add column if not exists offerta_minima numeric;
alter table public.annunci add column if not exists data_asta date;
alter table public.annunci add column if not exists scostamento_minima_pct numeric;
alter table public.annunci add column if not exists valore_mercato numeric;
alter table public.annunci add column if not exists diritto text;
alter table public.annunci add column if not exists occupazione text;
create index if not exists annunci_terr_idx on public.annunci (territorio, attivo);
create index if not exists annunci_zona_idx on public.annunci (territorio, microzona);

-- Storico prezzi
create table if not exists public.prezzi (
  uid    text not null,
  data   date not null,
  prezzo numeric,
  primary key (uid, data)
);

-- Mediane per microzona e fascia
create table if not exists public.mediane (
  territorio   text not null,
  microzona    text not null,
  fascia       text not null,
  n            int,
  mediana_mq   numeric,
  media_mq     numeric,
  mediana_zona numeric,
  n_zona       int,
  run_id       text,
  primary key (territorio, microzona, fascia)
);

-- Candidati frazionamento
create table if not exists public.frazionabili (
  uid                  text primary key,
  territorio           text not null,
  n_unita              int,
  mq_unita             numeric,
  mediana_piccole_mq   numeric,
  n_campione_piccole   int,
  valore_post          numeric,
  costo_lavori         numeric,
  costo_impianti_oneri numeric,
  costi_transazione    numeric,
  costi_totali         numeric,
  margine              numeric,
  margine_pct          numeric,
  indizi               text,
  punteggio_indizi     int,
  run_id               text
);

-- Esecuzioni del bot
create table if not exists public.esecuzioni (
  id          bigserial primary key,
  territorio  text,
  run_id      text,
  ts          timestamptz default now(),
  annunci     int,
  occasioni   int,
  frazionabili int,
  report_xlsx text,      -- percorso nello storage "report"
  note        text
);

-- Lavoro di squadra: stato e note per annuncio (scritti dagli utenti del sito)
create table if not exists public.valutazioni (
  uid        text not null,
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  user_email text default (auth.jwt() ->> 'email'),
  stato      text check (stato in ('da_vedere','interessante','visitato','in_trattativa','scartato')),
  nota       text,
  aggiornato timestamptz default now(),
  primary key (uid, user_id)
);

-- ---------------------------------------------------------------------
--  Sicurezza: solo utenti autenticati (invitati) leggono.
--  Il bot scrive con la chiave service_role, che ignora le policy.
-- ---------------------------------------------------------------------
alter table public.zone         enable row level security;
alter table public.annunci      enable row level security;
alter table public.prezzi       enable row level security;
alter table public.mediane      enable row level security;
alter table public.frazionabili enable row level security;
alter table public.esecuzioni   enable row level security;
alter table public.valutazioni  enable row level security;

do $$
declare t text;
begin
  foreach t in array array['zone','annunci','prezzi','mediane','frazionabili','esecuzioni','valutazioni'] loop
    if not exists (select 1 from pg_policies where tablename = t and policyname = t || '_lettura') then
      execute format('create policy %I on public.%I for select to authenticated using (true)', t || '_lettura', t);
    end if;
  end loop;
end $$;

drop policy if exists valutazioni_scrittura on public.valutazioni;
create policy valutazioni_scrittura on public.valutazioni
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Storage privato per i report Excel e le mappe HTML
insert into storage.buckets (id, name, public) values ('report', 'report', false)
  on conflict (id) do nothing;
drop policy if exists report_lettura on storage.objects;
create policy report_lettura on storage.objects
  for select to authenticated using (bucket_id = 'report');
