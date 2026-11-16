# Sito web Scout Immobili — messa online

Il sito permette a tutto il team di consultare occasioni, microzone, mappa, frazionabili e ribassi
da browser o telefono, con login, e di segnare lo stato di ogni annuncio (da vedere, interessante,
visitato, in trattativa, scartato) con note condivise.

```
PC del bot (Python)  ──scrive──▶  Supabase (database + login + report Excel)  ◀──legge──  Sito (Netlify)
   python -m scout run              chiave service_role (segreta)                chiave anon (pubblica) + login
```

- Il **bot** gira su un solo PC (connessione di casa/ufficio: i portali bloccano i server cloud) e a ogni
  esecuzione pubblica i risultati su Supabase.
- Il **sito** è statico (nessun server da gestire) e legge da Supabase solo dopo il login.
- Solo le persone **invitate** possono entrare: la registrazione libera è disattivata.

Costo: piani gratuiti di Supabase e Netlify sono sufficienti.

---

## 1. Supabase (10 minuti)

1. Vai su [supabase.com](https://supabase.com) → *New project*. Regione consigliata: **Central EU (Frankfurt)**.
   Annota la password del database (non serve al bot, ma tienila).
2. **SQL Editor** → *New query* → incolla tutto il contenuto di [`supabase/schema.sql`](supabase/schema.sql) → **Run**.
   Crea tabelle, permessi (solo utenti autenticati) e lo spazio "report" per gli Excel.
3. **Authentication → Sign In / Providers**: lascia attivo *Email*, e **disattiva "Allow new users to sign up"**.
4. **Project Settings → API**: copia
   - *Project URL* (es. `https://abcd1234.supabase.co`)
   - chiave **anon / publishable** → per il sito (è pubblica, protetta dal login)
   - chiave **service_role / secret** → solo per il PC del bot. **Non metterla mai nel sito né su GitHub.**

## 2. Bot: pubblicare i dati

Sul PC che esegue il bot, nel file `config.local.yaml` (non viene caricato su GitHub):

```yaml
supabase:
  attivo: true
  url: "https://abcd1234.supabase.co"
  service_key: "eyJ...service_role..."
```

Poi:

```bash
python -m scout analizza      # oppure: python -m scout run
```

Il messaggio "Risultati pubblicati sul sito (Supabase)" conferma l'invio. Ogni esecuzione aggiorna zone,
annunci, storico prezzi, mediane, frazionabili e carica l'Excel del giorno (scaricabile dalla Panoramica).
Per più territori basta eseguire il bot con ciascun config (`-c config_sgl.yaml`): nel sito compare il selettore.

## 3. Netlify: mettere online il sito

1. [app.netlify.com](https://app.netlify.com) → *Add new site* → *Import an existing project* → GitHub →
   scegli `Immobiliare-scout`. Le impostazioni di build sono già nel file `netlify.toml`.
2. *Site configuration → Environment variables* → aggiungi:
   - `VITE_SUPABASE_URL` = Project URL
   - `VITE_SUPABASE_ANON_KEY` = chiave anon
3. *Deploys → Trigger deploy*. Otterrai un indirizzo tipo `https://scout-immobili.netlify.app`
   (rinominabile, o collegabile a un tuo dominio).
4. Torna su Supabase → **Authentication → URL Configuration**: imposta *Site URL* con l'indirizzo Netlify
   e aggiungilo anche in *Redirect URLs*. Serve perché i link degli inviti portino al sito.

A ogni `git push` sul ramo `main` Netlify ripubblica il sito da solo.

> In alternativa a Netlify va bene anche Vercel o Cloudflare Pages: cartella `web`, comando
> `npm run build`, cartella di output `dist`, stesse due variabili.

## 4. Invitare il team

Supabase → **Authentication → Users → Add user → Send invitation**, una email per persona.
Chi riceve l'invito clicca il link, arriva sul sito e sceglie la password. Da quel momento entra con email e password.
Per togliere l'accesso: elimina l'utente dalla stessa pagina.

## 5. Provare il sito sul proprio PC

```bash
cd web
npm install
npm run dev            # http://localhost:5173
```

Senza `web/.env.local` il sito parte in **modalità DEMO** con annunci simulati nelle microzone reali
(`web/public/demo.json`, rigenerabile con `python scripts/genera_demo.py`). Per usare i dati veri copia
`web/.env.example` in `web/.env.local` e inserisci URL e chiave anon.

Il file demo contiene i poligoni delle tue microzone: quando il sito è collegato a Supabase **non** viene
pubblicato (la build lo esclude automaticamente).

## Sicurezza in breve

| Cosa | Dove sta | Chi la vede |
|---|---|---|
| chiave `service_role` | solo `config.local.yaml` sul PC del bot | nessun altro |
| chiave `anon` | variabili Netlify / dentro il sito | chiunque, ma senza login non legge nulla (policy RLS) |
| dati annunci, zone, mediane | Supabase | solo utenti invitati e loggati |
| valutazioni e note | Supabase | tutti gli utenti del team; ognuno modifica solo le proprie |
