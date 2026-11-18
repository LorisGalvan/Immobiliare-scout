# Scout Immobili

Bot in Python per individuare **immobili sottoprezzo rispetto alla loro microzona**, replicando (e automatizzando) il metodo manuale dei file *Verona_Mappatura.xlsx* e *San Giovanni Lupatoto - mappatura.xlsx*.

Il bot:

1. gestisce le **microzone come poligoni GeoJSON**: le importa dai tuoi Excel (decodifica `vrt` di Immobiliare, `shape` di Idealista e `geopolygon` di Casa.it) oppure le propone in automatico da OpenStreetMap;
2. scarica gli annunci da **Immobiliare.it** e **Subito.it** (Idealista in fase 2, Facebook semi-manuale) con un modulo per sito, a ritmo lento, con retry e gestione dei blocchi;
3. assegna ogni annuncio alla microzona (point-in-polygon, con geocoding dell'indirizzo se mancano le coordinate);
4. pulisce i dati (mq assurdi, nude proprietà...), riconosce dal testo le aste giudiziarie e le tiene a parte, segnala i dati dubbi e unisce i doppioni tra siti e agenzie;
5. calcola la **mediana €/mq per microzona e fascia** (30/50, 50/70, 70/100, 100+) e lo **scostamento %** di ogni annuncio, con correzioni opzionali per piano/ascensore/stato e confronto con le quotazioni OMI;
6. tiene lo **storico su SQLite**: ribassi di prezzo, giorni online, annunci rimossi;
7. produce un **Excel** con un foglio per microzona nello stesso formato dei tuoi file, più i fogli *Occasioni*, *Frazionabili*, *Ribassi*;
8. invia **alert Telegram/email** per le nuove occasioni;
9. genera una **mappa HTML** con le microzone colorate per €/mq e le occasioni evidenziate;
10. valuta il **frazionamento** degli immobili grandi.

## Sito web per il team

I risultati si possono consultare online, con login, da browser e telefono (occasioni, mappa, microzone,
frazionabili, ribassi, storico prezzi, valutazioni e note condivise del team).
Database e login su **Supabase**, sito su **Netlify** (piani gratuiti). Guida passo-passo: **[SITO_WEB.md](SITO_WEB.md)**.

---

## 1. Installazione

### Windows, senza comandi (consigliato)

1. Su GitHub: pulsante verde **Code → Download ZIP**, poi estrai lo ZIP (es. in `Documenti\scout_immobili`).
2. Doppio clic su **`INSTALLA.bat`**: installa Python se manca, le librerie, e apre il Blocco note per
   incollare la chiave *secret* di Supabase.
3. Doppio clic su **`AVVIA.bat`**: raccolta annunci, analisi, Excel, mappa e pubblicazione sul sito.

Per l'esecuzione automatica ogni mattina vedi il paragrafo 9 (`scripts\run_giornaliero.bat`).

### Windows blocca le librerie ("Un criterio di controllo dell'applicazione ha bloccato il file")

È il **Controllo intelligente delle app** di Windows 11, che blocca i file delle librerie scientifiche
(numpy, pandas) perché non hanno la firma digitale. Per disattivarlo:
*Sicurezza di Windows → Controllo app e browser → Impostazioni di Controllo intelligente delle app → Disattivato*.
Poi riavvia `AVVIA.bat`. Sulle versioni attuali di Windows, una volta disattivato, in genere non si può
riattivare senza reinstallare il sistema: Windows Defender (antivirus) resta comunque attivo.
Se il PC è aziendale, il blocco può essere una regola dell'amministratore: in quel caso serve il suo intervento
o un altro PC.

### Da riga di comando

Serve Python 3.10 o superiore.

```bash
git clone https://github.com/LorisGalvan/Immobiliare-scout.git scout_immobili
cd scout_immobili
python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp config.local.example.yaml config.local.yaml   # Windows: copy ...  poi inserisci i tuoi dati
```

Per aggiornare alla versione più recente: `git pull`.

Tutti i comandi si lanciano dalla cartella del progetto con `python -m scout <comando>`.
`python -m scout --help` mostra l'elenco; `python -m scout <comando> --help` mostra le opzioni di un comando.

> **Importante: dove eseguirlo.** Immobiliare e Subito bloccano le richieste dai server cloud (HTTP 403).
> Il bot va eseguito **dal tuo PC** (connessione di casa/ufficio). Il bot si presenta con uno
> user-agent dichiarato e non aggira protezioni anti-bot. Se un sito ti blocca anche da casa, usa
> l'**importazione semi-manuale** (paragrafo 4.2).

---

## 2. Configurazione (`config.yaml`)

Tutto è nel file `config.yaml`, commentato riga per riga. Le sezioni principali:

| Sezione | Cosa regola |
|---|---|
| `territorio` | comune e "slug" usati negli URL dei siti |
| `microzone` | file GeoJSON dei poligoni, tolleranza sul confine |
| `scraping` | pause tra richieste (default 6–14 s), retry, siti attivi, filtri prezzo/mq, modalità `comune` o `microzone` |
| `pulizia` | mq/€/mq accettabili, parole che escludono (nuda proprietà, posto auto...); le aste non vanno qui, le riconosce il bot dal testo o che rendono un annuncio "dubbio" |
| `analisi` | fasce mq, campione minimo, **soglia occasione (default -15%)**, coefficienti di correzione, OMI |
| `frazionamento` | soglia mq, mq per unità, costi (lavori/mq, impianti, oneri, spese tecniche, notaio, provvigioni), margine minimo |
| `alert` | Telegram ed email |

**Uso condiviso (più persone).** `config.yaml` e le microzone (`data/zone/`) sono condivisi nel repository.
Ognuno mette i propri dati personali (token Telegram, email, password, eventuali soglie diverse) in
`config.local.yaml` — copia `config.local.example.yaml` — che **non** viene caricato su GitHub e sovrascrive
solo le voci indicate. Database, log e output restano sul PC di ciascuno.

Per un altro territorio copia il file (es. `config_sgl.yaml`, già pronto per San Giovanni Lupatoto) e
lancia i comandi con `-c config_sgl.yaml`. Ogni territorio ha il suo database e il suo GeoJSON.

---

## 3. Microzone

### 3.1 Importare le tue microzone dagli Excel

```bash
python -m scout zone-importa-excel "Verona_Mappatura.xlsx"
python -m scout -c config_sgl.yaml zone-importa-excel "San_Giovanni_Lupatoto_-_mappatura.xlsx"
```

- Ogni foglio diventa una microzona con il nome del foglio (es. `1 Borgo Trento m1`).
- Il poligono viene preso dal link Immobiliare (`vrt`); se manca, da Idealista (`shape`) o Casa.it (`geopolygon`).
- Le righe annuncio dei fogli (VIA, MQ, PREZZO...) vengono salvate nello storico come dati **non attivi**
  (solo consultazione: non entrano nelle mediane attuali perché sono più vecchie di `includi_storico_giorni`).
- Vengono segnalati i fogli senza poligono e le zone che si sovrappongono.

Già fatto sui tuoi file: `data/zone/verona.geojson` (50 microzone) e `data/zone/san_giovanni_lupatoto.geojson` (4 microzone; il foglio *5SGL* non ha link e va disegnato).

### 3.2 Proposta automatica da OpenStreetMap

```bash
# tutto il comune, tagliato da strade principali/secondarie, ferrovie, fiumi, confini di quartiere
python -m scout zone-auto --livello medio --area-min 150000 --output data/zone/verona_auto.geojson

# solo nelle parti del comune NON coperte dalle tue microzone (le tue restano invariate)
python -m scout zone-auto --solo-scoperto
```

- `--livello base|medio|fine`: quali strade fanno da confine (`fine` include le terziarie → zone più piccole).
- `--area-min`: le zone più piccole di questa area (m²) vengono fuse con la vicina con cui condividono il bordo più lungo.
- I nomi vengono dal quartiere OSM che contiene la zona (`Borgo Venezia m1`, `m2`...).

### 3.3 Modificare le microzone

```bash
python -m scout editor          # crea output/editor_microzone.html
```

Apri il file nel browser: puoi spostare i vertici (matita), eliminare (cestino) o disegnare nuove zone.
Al termine premi **Export**, poi:

```bash
python -m scout zone-importa-geojson microzone_modificate.geojson
python -m scout zone-rinomina "Nuova zona 51" "Golosine m1"
python -m scout zone-elenco      # elenco, superfici e sovrapposizioni
```

In alternativa il GeoJSON si modifica con [geojson.io](https://geojson.io) o QGIS (la proprietà `nome` è il nome della microzona).

---

## 4. Raccolta annunci

### 4.1 Automatica

```bash
python -m scout scrape                       # siti attivi in config
python -m scout scrape --siti immobiliare     # un solo sito
```

- **Modalità `comune`** (default): una ricerca su tutto il comune ordinata per data, poi point-in-polygon. Meno richieste.
- **Modalità `microzone`**: una ricerca a poligono (`vrt`) per ogni microzona, come facevi a mano. Più richieste.
- Pausa casuale tra le richieste, retry con backoff esponenziale, rispetto di `robots.txt`.
- Se un sito risponde con blocchi (403/429/captcha) per `stop_dopo_blocchi` volte, il bot **smette di interrogarlo** per quella esecuzione. In quel caso non segna come "rimossi" gli annunci non visti (l'elenco è incompleto).
- **Fasce di prezzo** (`scraping.fasce_prezzo`): i portali mostrano solo un numero limitato di pagine per ricerca, quindi la ricerca del comune viene spezzata in fasce di prezzo per arrivare a tutti gli annunci. Lista vuota `[]` = una ricerca unica.
- Se manca il campo mq, il bot li cerca nel testo (`pulizia.mq_dal_testo`), ignorando giardini, cantine, terrazzi e box.
- Per Immobiliare scarica la scheda di dettaglio (descrizione completa, data, ascensore) solo per i candidati più interessanti (grandi o con €/mq basso), max `max_dettagli_per_run`.

### 4.2 Semi-manuale (se un sito blocca, e per Idealista)

1. Apri nel browser la ricerca (puoi usare i link in riga 1-3 dei fogli microzona dell'Excel generato).
2. Salva ogni pagina dei risultati con **Ctrl+S** ("**Pagina web completa**") nella cartella **`pagine_salvate`**.
   Usa la vista a **elenco** (es. `https://www.immobiliare.it/vendita-case/verona/`, pagine 2, 3…), non quella a mappa,
   che salvata non contiene gli annunci
   del progetto. Al successivo `AVVIA.bat` vengono importate in automatico e spostate in `pagine_salvate/importate/<data>/`
   (quelle illeggibili in `pagine_salvate/non_riconosciute/`).
3. Oppure, da riga di comando, importa una cartella qualsiasi:

```bash
python -m scout importa-html data/pagine/2026-11-16
```

Il formato (Immobiliare, Idealista, Casa.it, Subito) viene riconosciuto in automatico. Indirizzi per la vista a elenco:
`https://www.immobiliare.it/vendita-case/verona/?criterio=data&ordine=desc`,
`https://www.idealista.it/vendita-case/verona-verona/?ordine=pubblicazione-desc`,
`https://www.casa.it/vendita/residenziale/verona/?sortType=date_desc`.
Aggiungi `--fonte-completa` solo se hai salvato **tutte** le pagine della ricerca (così il bot segna come rimossi gli annunci spariti).

### 4.3 Facebook Marketplace / annunci trovati a mano

Compila un CSV (separatore `,` o `;`) con le colonne:

```
link,prezzo,mq,indirizzo,piano,ascensore,bagni,stato,agenzia,data,descrizione,lat,lon
```

(`agenzia` = `privato` per i privati; colonne vuote ammesse) e importalo:

```bash
python -m scout importa-csv annunci_facebook.csv --fonte facebook
```

---

## 5. Analisi e output

```bash
python -m scout analizza                 # Excel + mappa + alert
python -m scout analizza --prova-alert    # mostra gli alert senza inviarli
```

Nella cartella `output/`:

- **`scouting_<territorio>_<data>.xlsx`**
  - *Riepilogo*: per ogni microzona mediana €/mq e numero annunci per fascia.
  - *Occasioni*: annunci attivi con scostamento ≤ soglia (default -15%), dal più conveniente.
  - *Frazionabili*: candidati al frazionamento ordinati per margine %.
  - *Ribassi*: annunci con prezzo ridotto rispetto alla prima rilevazione.
  - **Un foglio per microzona** con lo stesso layout dei tuoi file: righe 1-3 link di ricerca a poligono
    (Immobiliare / Idealista / Casa), poi un blocco per fascia con
    `VIA | MQ | PREZZO | PREZZO MQ | %SCOSTAMENTO | PIANO | ASCENSORE | BAGNI | RISTRUTTURATO | DATA | AGENZIA/PRIVATO | LINK | NOTE`
    più colonne extra (fonte, giorni online, ribasso, scostamento grezzo, OMI, link dei doppioni) e le righe *Mediana* e *Media*.
    Lo scostamento è colorato con la tua legenda (giallo > 0, verde chiaro 0/-10, verde -10/-20, azzurro oltre -20).
    Gli annunci rimossi restano in grigio barrato.
  - *Fuori zona*: annunci che non cadono in nessuna microzona (utile per capire dove disegnarne di nuove).
- **`mappa_<territorio>_<data>.html`**: microzone colorate per mediana €/mq (clic = dettaglio per fascia),
  occasioni (stella rossa), frazionabili (viola), tutti gli annunci (livello attivabile).

### Come si calcola lo scostamento

- Fasce: 30/50, 50/70, 70/100, 100+ (configurabili).
- Riferimento = **mediana** €/mq degli annunci della stessa microzona e fascia (attivi + rimossi negli ultimi 180 giorni, doppioni esclusi).
- Se la fascia ha meno di `min_campione` annunci si usa la mediana dell'intera microzona (indicato nella colonna NOTE / "Base confronto").
- **Correzioni** (se `correzioni.attive: true`): ogni €/mq viene "normalizzato" dividendo per un coefficiente
  (piano terra 0,93; 3° piano o più senza ascensore 0,92; attico 1,08; stato nuovo 1,12, ottimo 1,05, da ristrutturare 0,80).
  Così un piano terra da ristrutturare non appare come falsa occasione. La colonna *SCOST. GREZZO %* mostra il valore senza correzioni.
- Nota: i tuoi file usavano come riferimento la **media -20%**; il bot usa la **mediana** (meno sensibile agli annunci fuori mercato) e una soglia configurabile.

### Quotazioni OMI

1. Scarica il file delle quotazioni da Agenzia delle Entrate → *Banche dati* → *Quotazioni immobiliari* (CSV "VALORI" del semestre).
2. Copialo in `data/omi/QI_VALORI.csv` e imposta `analisi.omi.attivo: true`.
3. Collega le microzone alle zone OMI: o con un GeoJSON delle zone OMI (`file_zone`) o a mano in `mappa_microzone`
   (es. `"1 Borgo Trento m1": C12`).

Nell'Excel compaiono il valore OMI medio e lo scostamento rispetto a OMI.

### Aste giudiziarie

Ogni annuncio viene letto (titolo, descrizione, tipologia, inserzionista) da `scout/tipo_vendita.py`:

- **asta**: almeno un indizio forte (R.G.E., prezzo base, offerta minima, delegato alla vendita, custode/IVG,
  "all'asta", procedura fallimentare, data dell'asta...) oppure più indizi deboli;
- **possibile asta**: un solo indizio debole (la parola "asta" da sola, pignoramento, agenzia specializzata);
- **compravendita**: tutto il resto. Le frasi che negano ("non è un'asta", "no aste") e parole come "vasta" vengono ignorate.

Aste e possibili aste **non entrano nelle mediane**: finiscono nel foglio Excel **Aste** e nella pagina **Aste** del sito,
confrontate con il mercato libero della loro microzona e fascia, con prezzo base, offerta minima e data letti dal testo.
Sul sito serve una volta `supabase/migrazione_003_aste.sql` (SQL Editor di Supabase); senza, il bot pubblica solo le compravendite.

**Portale delle Vendite Pubbliche (PVP).** Per avere l'elenco completo delle aste, il bot legge anche
[pvp.giustizia.it](https://pvp.giustizia.it), dove per legge va pubblicata ogni vendita giudiziaria
(`scraping.siti.pvp: true`, impostazioni in `aste_pvp`). I lotti del PVP vanno solo nella sezione Aste.
Se lo stesso lotto è anche su Immobiliare o altri portali, resta una riga sola, quella del PVP, con gli altri link
in "Stesso lotto anche su". Per ogni asta il bot legge anche il **diritto** venduto (piena proprietà, quota, nuda
proprietà, usufrutto) e se l'immobile è **libero o occupato**.

Il servizio di ricerca del PVP non è documentato e il bot non è ancora stato provato sul sito vero:
se nel log compare "PVP: il servizio di ricerca non risponde come previsto", apri la ricerca sul PVP nel browser
(Verona, immobili), salvala con Ctrl+S in `pagine_salvate/` e lancia `importa-html` come per Immobiliare.

---

## 6. Frazionamento

Per ogni annuncio attivo ≥ `frazionamento.mq_min` (default 100 mq):

```
mq utili      = mq × (1 - perdita_superficie_pct)
n unità       = floor(mq utili / mq_unita_target)            (minimo 2)
valore post   = mq utili × mediana €/mq della fascia piccola (30/50) nella stessa microzona × (1 - sconto prudenziale)
costi         = lavori/mq × mq + spese tecniche % + (impianti + oneri) × n unità + notaio/imposte % + provvigioni vendita %
margine       = valore post - prezzo - costi           margine % = margine / (prezzo + costi)
```

Il testo dell'annuncio viene analizzato per **indizi** di frazionabilità: doppio ingresso, "frazionabile/divisibile",
più utenze/contatori, due o più bagni, piano terra/indipendente, forma regolare, due cucine. Nel foglio *Frazionabili*
trovi n. unità, valore post, dettaglio costi, margine €/% e indizi, ordinati per margine.
Con i costi di default (650 €/mq di lavori sull'intera superficie) un immobile deve essere molto sotto
mercato per avere margine: adatta i costi alla tua esperienza.

---

## 7. Storico

Il database SQLite (`data/scout.sqlite`) conserva per ogni annuncio prima e ultima rilevazione, tutti i prezzi
(tabella `prezzi`), la data di rimozione e gli alert già inviati. Da qui:
**giorni online**, **ribasso %** dal primo prezzo, annunci **rimossi** (probabilmente venduti: restano nella mediana per 180 giorni).

```bash
python -m scout stato      # riepilogo per fonte e ultime esecuzioni
```

Il database si apre anche con [DB Browser for SQLite](https://sqlitebrowser.org/).

---

## 8. Alert

**Telegram**
1. Su Telegram scrivi a `@BotFather` → `/newbot` → copia il token.
2. Scrivi un messaggio al tuo bot, poi apri `https://api.telegram.org/bot<TOKEN>/getUpdates` e copia `chat.id`.
3. In `config.yaml`: `alert.telegram.attivo: true`, `token`, `chat_id` (oppure variabili d'ambiente `SCOUT_TELEGRAM_TOKEN`, `SCOUT_TELEGRAM_CHAT_ID`).

**Email** (es. Gmail): crea una "password per le app" nell'account Google, poi compila `alert.email`
(password anche in `SCOUT_SMTP_PASSWORD`).

```bash
python -m scout test-alert
```

Ogni occasione/frazionabile viene segnalata **una sola volta**.

---

## 9. Esecuzione giornaliera

```bash
python -m scout run          # scrape + analisi + Excel + mappa + alert
```

**Windows** – Utilità di pianificazione → Crea attività di base → giornaliera (es. 7:30) →
Avvia programma: `scripts\run_giornaliero.bat` (nessun percorso da modificare; il PC deve essere acceso).

**Linux/Mac** – `crontab -e`:

```
30 7 * * * /percorso/scout_immobili/scripts/run_giornaliero.sh
```

I log sono in `data/log/scout.log`.

---

## 10. Struttura del progetto

```
config.yaml / config_sgl.yaml   configurazioni per territorio
scout/
  cli.py              comandi
  pipeline.py         orchestrazione
  geo/polygons.py     decodifica/codifica vrt, shape Idealista, geopolygon Casa.it
  geo/microzones.py   GeoJSON e point-in-polygon
  geo/osm_zoning.py   microzone automatiche da OpenStreetMap (Overpass)
  geo/geocode.py      geocoding Nominatim con cache
  scrapers/base.py    client HTTP lento con retry e gestione blocchi
  scrapers/immobiliare.py, subito.py, idealista.py
  importa.py          import pagine salvate e CSV (Facebook)
  excel_import.py     import dei tuoi Excel
  cleaning.py         validazione e doppioni
  analysis.py         mediane, scostamenti, correzioni, OMI
  frazionamento.py    modulo frazionamento
  storage.py          SQLite
  export_excel.py     Excel di output
  mappa.py            mappe folium ed editor microzone
  alerts.py           Telegram / email
  supabase_sync.py    pubblicazione dei risultati per il sito web
supabase/schema.sql   tabelle e permessi Supabase
web/                  sito web (React + Vite + Tailwind + Leaflet)
tests/                test automatici (python -m pytest)
```

## 11. Stato e limiti

- **Verificato**: decodifica dei poligoni sui tuoi file (50 + 4 microzone), import dello storico Excel, geocoding reale
  con Nominatim e assegnazione alla microzona, analisi/Excel/mappa sui tuoi dati storici, pipeline completa (storico,
  ribassi, rimozioni, doppioni, occasioni, frazionamento, alert) su dati simulati.
- **Da verificare al primo avvio dal tuo PC**: i parser di Immobiliare e Subito leggono il JSON `__NEXT_DATA__` delle pagine;
  sono scritti per resistere a piccoli cambi di struttura, ma non è stato possibile provarli su pagine reali perché i
  siti bloccano i server cloud. Se `scrape` trova 0 annunci, salva una pagina di ricerca (Ctrl+S) e mandamela: si adatta il parser in pochi minuti.
- La proposta automatica di microzone richiede l'accesso a `overpass-api.de` (testata su dati sintetici).
- Lo scraping dei portali è soggetto ai loro termini d'uso: tieni ritmi lenti e uso personale.
