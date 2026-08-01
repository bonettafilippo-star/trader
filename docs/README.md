# Market Watch — webapp personale con notifiche Telegram

Screener automatico di indici USA (S&P 500, Nasdaq, Dow Jones) e di una watchlist di big cap
(Apple, Microsoft, Nvidia, Tesla, Amazon, Alphabet, Meta). Ogni ora uno script pubblico su
GitHub Actions raccoglie prezzi e notizie da fonti gratuite, rigenera una pagina web statica
(pubblicata gratis con GitHub Pages) e ti manda una notifica Telegram **solo se** c'è un
movimento superiore alla soglia impostata (±3% sui titoli, ±1,5% sugli indici).

Non è consulenza finanziaria: è uno strumento di monitoraggio/ricerca personale. Le notifiche
segnalano movimenti degni di nota, non indicazioni di acquisto/vendita. Nessuna operazione
viene mai eseguita automaticamente.

## Come funziona

- `scripts/market_watch.py` — legge prezzi da Yahoo Finance (API pubblica, nessuna chiave
  richiesta) e notizie da Google News RSS, genera `docs/index.html`, invia una notifica
  Telegram se qualcosa supera la soglia.
- `.github/workflows/market-watch.yml` — esegue lo script ogni ora su GitHub Actions
  (gratuito per repository pubblici) e pubblica la pagina aggiornata.
- `docs/index.html` — la pagina della tua webapp, servita da GitHub Pages.

## Personalizzazioni

Tutto si modifica in cima a `scripts/market_watch.py`:

- `WATCHLIST` — aggiungi/rimuovi titoli (serve il ticker Yahoo Finance, es. `ENI.MI` per
  Eni su Borsa Italiana).
- `INDICES` — altri indici, es. `FTSEMIB.MI` per il FTSE MIB.
- `STOCK_FLAG_THRESHOLD` / `INDEX_FLAG_THRESHOLD` — soglie di variazione % per far scattare
  una notifica.
- In `.github/workflows/market-watch.yml`, l'espressione cron `5 * * * *` è in **UTC**:
  cambiala se vuoi una frequenza diversa.

## Limiti da conoscere

- Dati da fonti pubbliche gratuite (Yahoo Finance, Google News): non è un feed professionale
  in tempo reale, possono esserci ritardi di qualche minuto o dati mancanti in singole run.
- GitHub Actions gratuito ha un limite di minuti di esecuzione mensile (ampiamente sufficiente
  per uno script che gira in pochi secondi ogni ora).
- Nessuna esecuzione di ordini/trading: solo monitoraggio e notifica.
