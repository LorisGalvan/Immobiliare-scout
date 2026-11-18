# Roadmap Scout Immobili

## Fatto
- Bot: microzone dai tuoi Excel, Subito automatico, Immobiliare/Idealista/Casa.it da pagine salvate,
  analisi per microzona e fascia, storico, Excel, mappa, frazionamento, sito web con login (Supabase + GitHub Pages).
- Aste lette dal testo degli annunci e tenute fuori dalla valutazione (foglio e pagina "Aste");
  ricerca spezzata in fasce di prezzo per superare il limite di pagine dei portali; mq letti dal testo.

## In corso
- **Editor microzone sul sito** (ramo `editor-zone`): modifica dei confini sulla mappa, nuove zone,
  rinomina/elimina, storico versioni con ripristino, assegnazione manuale degli annunci senza zona.
  Prima di unirlo: eseguire `supabase/migrazione_002_editor_zone.sql` nel SQL Editor di Supabase.

## Prossimi passi
1. **Coprire tutta Verona**: proporre microzone automatiche (OSM) per le aree non coperte dalle 50 attuali
   (es. Borgo Roma, Golosine, Quinto) e rifinirle con l'editor.
2. **Estensione browser** che salva in automatico le pagine di risultati che l'utente apre su
   Immobiliare / Idealista / Casa.it (niente navigazione automatica: solo le pagine aperte da una persona).
3. **Affinare i risultati**: annunci Subito senza posizione, motivi di scarto, indicatore di affidabilità
   delle occasioni (campione piccolo), alert Telegram, avvio automatico giornaliero.

## Dopo Verona: comuni limitrofi
Aggiungere i principali comuni della cintura, ciascuno con il proprio file di configurazione
(come `config_sgl.yaml`) e le proprie microzone, selezionabili dal sito:
- San Giovanni Lupatoto (config e 4 microzone già presenti dal tuo Excel)
- Villafranca di Verona
- San Martino Buon Albergo
- altri da definire (es. Bussolengo, Sona, Pescantina, Castel d'Azzano, Zevio, Grezzana, Negrar)

Per ogni comune: microzone (Excel / OSM / editor) → pagine salvate dai portali → AVVIA con `-c config_<comune>.yaml`.
