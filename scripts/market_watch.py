#!/usr/bin/env python3
"""
Market Watch — screener + notifiche Telegram + pagina statica (GitHub Pages).

Gira su GitHub Actions (cron ogni 15 minuti). Non richiede API a pagamento:
- Prezzi/volumi: Yahoo Finance chart API pubblica (nessuna key necessaria)
- Notizie: Google News RSS (nessuna key necessaria)
- Notifiche: Telegram Bot API (token + chat id da variabili d'ambiente)

Variabili d'ambiente richieste (impostale come GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

Questo script NON dà consigli di acquisto/vendita. Descrive solo la reazione
osservabile del mercato (variazione di prezzo, volumi scambiati rispetto alla
media) quando trova un annuncio/notizia nuova su un titolo della watchlist.
"""

import os
import json
import html
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500"},
    {"symbol": "^IXIC", "name": "Nasdaq Composite"},
    {"symbol": "^DJI", "name": "Dow Jones"},
]

WATCHLIST = [
    {"symbol": "AAPL", "name": "Apple", "query": "Apple AAPL stock"},
    {"symbol": "MSFT", "name": "Microsoft", "query": "Microsoft MSFT stock"},
    {"symbol": "NVDA", "name": "Nvidia", "query": "Nvidia NVDA stock"},
    {"symbol": "TSLA", "name": "Tesla", "query": "Tesla TSLA stock"},
    {"symbol": "AMZN", "name": "Amazon", "query": "Amazon AMZN stock"},
    {"symbol": "GOOGL", "name": "Alphabet", "query": "Alphabet GOOGL stock"},
    {"symbol": "META", "name": "Meta", "query": "Meta META stock"},
]

STOCK_FLAG_THRESHOLD = 3.0     # % variazione giornaliera per segnalare un titolo
INDEX_FLAG_THRESHOLD = 1.5     # % variazione giornaliera per segnalare un indice
VOLUME_RATIO_NOTABLE = 1.5     # volumi >= 1.5x la media = attività di trading elevata
NEWS_PER_TICKER = 3
MAX_SEEN_LINKS_PER_SYMBOL = 40
GENERAL_NEWS_QUERY = "stock market news today"
GENERAL_NEWS_COUNT = 5

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketWatchBot/1.0)"}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUTPUT_HTML = os.path.join(DOCS_DIR, "index.html")
STATE_DIR = os.path.join(BASE_DIR, "state")
STATE_PATH = os.path.join(STATE_DIR, "seen_news.json")


# ---------------------------------------------------------------------------
# Stato (per non notificare due volte la stessa notizia)
# ---------------------------------------------------------------------------

def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen_links": {}}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Raccolta dati
# ---------------------------------------------------------------------------

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_volume_ratio(result):
    """Volume di oggi rispetto alla media dei giorni precedenti nella stessa risposta."""
    try:
        quote = result["indicators"]["quote"][0]
        volumes = [v for v in (quote.get("volume") or []) if v is not None]
        if len(volumes) < 2:
            return None
        today = volumes[-1]
        prior = volumes[:-1]
        avg_prior = sum(prior) / len(prior)
        if not avg_prior:
            return None
        return today / avg_prior
    except Exception:
        return None


def fetch_quote(symbol):
    """Ritorna dict con prezzo corrente, variazione % e rapporto sui volumi."""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval=1d&range=6d"
    )
    try:
        data = fetch_json(url)
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None or prev_close in (None, 0):
            return None
        change_pct = (price - prev_close) / prev_close * 100
        return {
            "symbol": symbol,
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "currency": meta.get("currency", "USD"),
            "volume_ratio": compute_volume_ratio(result),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] quote fallita per {symbol}: {exc}")
        return None


def fetch_news(query, limit=3):
    """Notizie recenti da Google News RSS per una query testuale."""
    url = (
        "https://news.google.com/rss/search?q="
        f"{urllib.parse.quote(query)}&hl=it-IT&gl=IT&ceid=IT:it"
    )
    items = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        for item in root.findall("./channel/item")[:limit]:
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            source_el = item.find("source")
            source = source_el.text if source_el is not None else ""
            items.append({"title": title, "link": link, "source": source})
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] news fallite per '{query}': {exc}")
    return items


# ---------------------------------------------------------------------------
# Raccolta + individuazione novità
# ---------------------------------------------------------------------------

def collect(state):
    now = datetime.datetime.now(datetime.timezone.utc)
    seen_links = state.setdefault("seen_links", {})

    index_rows = []
    for idx in INDICES:
        q = fetch_quote(idx["symbol"])
        if q:
            q["name"] = idx["name"]
            q["flag"] = abs(q["change_pct"]) >= INDEX_FLAG_THRESHOLD
            index_rows.append(q)

    watch_rows = []
    for w in WATCHLIST:
        q = fetch_quote(w["symbol"])
        if not q:
            continue
        q["name"] = w["name"]
        q["flag"] = abs(q["change_pct"]) >= STOCK_FLAG_THRESHOLD

        news = fetch_news(w["query"], NEWS_PER_TICKER)
        already_seen = set(seen_links.get(w["symbol"], []))
        for n in news:
            n["is_new"] = n["link"] not in already_seen
        q["news"] = news

        updated = list(dict.fromkeys(list(already_seen) + [n["link"] for n in news]))
        seen_links[w["symbol"]] = updated[-MAX_SEEN_LINKS_PER_SYMBOL:]

        watch_rows.append(q)

    general_news = fetch_news(GENERAL_NEWS_QUERY, GENERAL_NEWS_COUNT)

    return {
        "generated_at": now.isoformat(),
        "indices": index_rows,
        "watchlist": watch_rows,
        "general_news": general_news,
    }


# ---------------------------------------------------------------------------
# Notifica Telegram
# ---------------------------------------------------------------------------

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[info] Telegram non configurato, salto notifica.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("[info] notifica Telegram inviata.")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] invio Telegram fallito: {exc}")


def describe_reaction(r):
    """Descrizione neutra della reazione del mercato — mai un consiglio."""
    parts = [f"{r['change_pct']:+.2f}% da inizio giornata"]
    vr = r.get("volume_ratio")
    if vr is not None:
        if vr >= VOLUME_RATIO_NOTABLE:
            parts.append(f"volumi ~{vr:.1f}x la media (attività di trading elevata)")
        else:
            parts.append(f"volumi ~{vr:.1f}x la media")
    return ", ".join(parts)


def build_notification(data, is_market_hours):
    lines = []

    news_lines = []
    for r in data["watchlist"]:
        new_items = [n for n in r["news"] if n["is_new"]]
        if not new_items:
            continue
        news_lines.append(f"📰 *{r['name']}* ({r['symbol']})")
        news_lines.append(f"   {new_items[0]['title']}")
        news_lines.append(f"   Reazione: {describe_reaction(r)}")
        news_lines.append(f"   {new_items[0]['link']}")

    if news_lines:
        lines.append("*Nuovi annunci rilevati*")
        lines.extend(news_lines)
        lines.append("")

    move_lines = []
    for r in data["indices"]:
        if r["flag"]:
            arrow = "🔺" if r["change_pct"] >= 0 else "🔻"
            move_lines.append(f"{arrow} *{r['name']}*: {r['price']:.2f} ({r['change_pct']:+.2f}%)")
    for r in data["watchlist"]:
        if r["flag"]:
            arrow = "🔺" if r["change_pct"] >= 0 else "🔻"
            move_lines.append(f"{arrow} *{r['name']}* ({r['symbol']}): {describe_reaction(r)}")

    if move_lines:
        lines.append("*Movimenti di prezzo rilevanti*")
        lines.extend(move_lines)
        lines.append("")

    if not lines:
        return None

    if not is_market_hours:
        lines.insert(0, "_Mercato USA chiuso — dati riferiti all'ultima sessione._\n")

    lines.append("_Informazione descrittiva, non un consiglio di acquisto/vendita. Verifica sempre la fonte primaria._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generazione pagina HTML
# ---------------------------------------------------------------------------

def render_html(data):
    generated_at = datetime.datetime.fromisoformat(data["generated_at"])
    generated_at_str = generated_at.strftime("%d/%m/%Y %H:%M UTC")

    def index_card(r):
        cls = "up" if r["change_pct"] >= 0 else "down"
        arrow = "▲" if r["change_pct"] >= 0 else "▼"
        return f"""
        <div class="card">
          <div class="name">{html.escape(r['name'])}</div>
          <div class="value">{r['price']:.2f}</div>
          <div class="change {cls}">{arrow} {r['change_pct']:+.2f}%</div>
        </div>"""

    def watch_row(r):
        cls = "up" if r["change_pct"] >= 0 else "down"
        arrow = "▲" if r["change_pct"] >= 0 else "▼"
        flags = []
        if r["flag"]:
            flags.append('<span class="flag warn">Movimento rilevante</span>')
        if any(n["is_new"] for n in r["news"]):
            flags.append('<span class="flag new">Nuovo annuncio</span>')
        flag_html = "".join(flags) or "—"
        vr = r.get("volume_ratio")
        vol_html = f'<div class="mini-news">Volumi: {vr:.1f}x media</div>' if vr is not None else ""
        news_html = ""
        if r["news"]:
            n = r["news"][0]
            badge = ' <span class="tag">nuovo</span>' if n["is_new"] else ""
            news_html = f'<div class="mini-news"><a href="{html.escape(n["link"])}" target="_blank" rel="noopener">{html.escape(n["title"])}</a>{badge}</div>'
        return f"""
        <tr>
          <td>{html.escape(r['name'])} ({r['symbol']})</td>
          <td>{r['price']:.2f} {html.escape(r['currency'])}</td>
          <td class="{cls}">{arrow} {r['change_pct']:+.2f}%</td>
          <td>{flag_html}{vol_html}{news_html}</td>
        </tr>"""

    def news_item(n):
        source = f' <span class="tag">{html.escape(n["source"])}</span>' if n.get("source") else ""
        return f"""
        <div class="news-item">
          <a href="{html.escape(n['link'])}" target="_blank" rel="noopener">{html.escape(n['title'])}</a>{source}
        </div>"""

    indices_html = "".join(index_card(r) for r in data["indices"]) or "<p>Dati indici non disponibili in questa run.</p>"
    watch_html = "".join(watch_row(r) for r in data["watchlist"]) or "<tr><td colspan='4'>Dati non disponibili in questa run.</td></tr>"
    news_html = "".join(news_item(n) for n in data["general_news"]) or "<p>Nessuna notizia recuperata in questa run.</p>"

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="300">
<title>Market Watch Dashboard</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f7f7f5;
    color: #1a1a1a;
    padding: 24px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
  .header h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .header .sub {{ color: #666; font-size: 13px; }}
  .badge {{ background: #fff3e0; color: #995c00; border: 1px solid #f0c98a; border-radius: 6px; padding: 6px 10px; font-size: 12px; max-width: 320px; }}
  .section-title {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; color: #666; margin: 28px 0 10px 0; }}
  .indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
  .card {{ background: #fff; border: 1px solid #e5e5e3; border-radius: 10px; padding: 14px 16px; }}
  .card .name {{ font-size: 13px; color: #666; margin-bottom: 4px; }}
  .card .value {{ font-size: 20px; font-weight: 600; }}
  .change {{ font-size: 13px; font-weight: 600; margin-top: 2px; }}
  .up {{ color: #0a7d32; }}
  .down {{ color: #c22626; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e5e5e3; border-radius: 10px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 10px 14px; font-size: 13px; border-bottom: 1px solid #eeeeec; vertical-align: top; }}
  th {{ background: #fafaf9; color: #666; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.03em; }}
  tr:last-child td {{ border-bottom: none; }}
  .flag {{ display: inline-block; font-size: 11px; padding: 2px 7px; border-radius: 10px; font-weight: 600; margin-right: 4px; }}
  .flag.warn {{ background: #fdecea; color: #c22626; }}
  .flag.new {{ background: #e8f0fe; color: #1a56db; }}
  .mini-news {{ margin-top: 4px; font-size: 12px; }}
  .mini-news a {{ color: #555; }}
  .news-list {{ display: flex; flex-direction: column; gap: 10px; }}
  .news-item {{ background: #fff; border: 1px solid #e5e5e3; border-radius: 10px; padding: 12px 16px; font-size: 13.5px; line-height: 1.5; }}
  .news-item a {{ color: #1a1a1a; text-decoration: none; }}
  .news-item a:hover {{ text-decoration: underline; }}
  .tag {{ display: inline-block; font-size: 10.5px; font-weight: 600; color: #995c00; background: #fff3e0; border-radius: 5px; padding: 1px 6px; margin-left: 6px; }}
  .disclaimer {{ margin-top: 32px; padding: 14px 16px; background: #f0f0ee; border-radius: 10px; font-size: 12px; color: #555; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Market Watch — Indici &amp; Big Cap USA</h1>
      <div class="sub">Ultimo aggiornamento: {generated_at_str} · rigenerata ogni 15 minuti via GitHub Actions</div>
    </div>
    <div class="badge">Dati da ricerca pubblica, non un feed in tempo reale. Non è consulenza finanziaria.</div>
  </div>

  <div class="section-title">Indici principali</div>
  <div class="indices">{indices_html}</div>

  <div class="section-title">Watchlist big cap</div>
  <table>
    <thead><tr><th>Titolo</th><th>Prezzo</th><th>Var. giornaliera</th><th>Segnali</th></tr></thead>
    <tbody>{watch_html}</tbody>
  </table>

  <div class="section-title">Notizie di mercato</div>
  <div class="news-list">{news_html}</div>

  <div class="disclaimer">
    <strong>Nota:</strong> pagina generata automaticamente da uno script che interroga fonti pubbliche gratuite (Yahoo Finance, Google News). Le "segnalazioni" descrivono variazioni di prezzo superiori a {STOCK_FLAG_THRESHOLD:.1f}% (titoli) / {INDEX_FLAG_THRESHOLD:.1f}% (indici) e nuovi annunci/notizie rilevati, insieme alla reazione osservabile del mercato (prezzo, volumi). Sono informazioni descrittive per la tua ricerca personale, non raccomandazioni di acquisto/vendita né consulenza finanziaria. Verifica sempre su una fonte primaria prima di decidere ed esegui sempre tu stesso qualsiasi operazione.
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def is_us_market_hours(now_utc):
    if now_utc.weekday() >= 5:
        return False
    return 13 <= now_utc.hour < 21


def main():
    state = load_state()
    data = collect(state)

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    print(f"[info] pagina scritta in {OUTPUT_HTML}")

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    notification = build_notification(data, is_us_market_hours(now_utc))
    if notification:
        send_telegram(notification)
    else:
        print("[info] nessuna segnalazione in questa run, nessuna notifica inviata.")

    save_state(state)


if __name__ == "__main__":
    main()
