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

## Setup (una tantum, ~10 minuti)

### 1. Crea il repository su GitHub

1. Vai su github.com, crea un nuovo repository (es. `market-watch`), **pubblico** — GitHub
   Pages gratuito richiede repo pubblico (su repo privati serve un piano GitHub a pagamento).
2. Carica tutti i file di questa cartella nel repository (via web upload, GitHub Desktop o
   `git push` — scegli quello che preferisci).

### 2. Crea il bot Telegram (per le notifiche)

1. Apri Telegram, cerca **@BotFather** e avvia una chat.
2. Manda `/newbot`, scegli un nome e uno username per il bot (deve finire in `bot`, es.
   `filippo_market_watch_bot`).
3. BotFather ti restituisce un **token** tipo `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` —
   copialo, ti serve al passo 4.
4. Cerca il tuo bot su Telegram (con lo username scelto) e mandagli un messaggio qualsiasi
   (es. "ciao") per attivare la chat.
5. Apri nel browser (sostituendo `<TOKEN>` con il tuo token):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Nel JSON restituito cerca `"chat":{"id": 123456789, ...}` — quel numero è il tuo
   **chat_id**.

### 3. Aggiungi i secrets al repository

Nel repository GitHub: **Settings → Secrets and variables → Actions → New repository secret**

- `TELEGRAM_BOT_TOKEN` = il token di BotFather
- `TELEGRAM_CHAT_ID` = il chat_id ottenuto sopra

### 4. Attiva GitHub Pages

**Settings → Pages → Build and deployment → Source: "Deploy from a branch"**,
branch `main`, cartella `/docs` → Save.

Dopo qualche minuto la pagina sarà visibile su:
`https://<tuo-username>.github.io/<nome-repo>/`

### 5. Primo run manuale

Vai sulla tab **Actions** del repository, seleziona il workflow "Market Watch",
clicca **Run workflow** per testarlo subito invece di aspettare la prossima ora.
Controlla i log per verificare che non ci siano errori, poi guarda la pagina Pages
e (se scatta una soglia) il messaggio Telegram.

## Personalizzazioni

Tutto si modifica in cima a `scripts/market_watch.py`:

- `WATCHLIST` — aggiungi/rimuovi titoli (serve il ticker Yahoo Finance, es. `ENI.MI` per
  Eni su Borsa Italiana).
- `INDICES` — altri indici, es. `FTSEMIB.MI` per il FTSE MIB.
- `STOCK_FLAG_THRESHOLD` / `INDEX_FLAG_THRESHOLD` — soglie di variazione % per far scattare
  una notifica.
- In `.github/workflows/market-watch.yml`, l'espressione cron `5 * * * *` è in **UTC**:
  cambiala se vuoi una frequenza diversa (es. `5 6-22 * * 1-5` per ogni ora, solo nei giorni
  feriali, dalle 8 alle 24 ora italiana in inverno).

## Limiti da conoscere

- Dati da fonti pubbliche gratuite (Yahoo Finance, Google News): non è un feed professionale
  in tempo reale, possono esserci ritardi di qualche minuto o dati mancanti in singole run.
- GitHub Actions gratuito ha un limite di minuti di esecuzione mensile (ampiamente sufficiente
  per uno script che gira in pochi secondi ogni ora).
- Nessuna esecuzione di ordini/trading: solo monitoraggio e notifica.
