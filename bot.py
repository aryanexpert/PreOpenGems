"""
================================================================
 STOCK ALERT BOT - ALL IN ONE  (Railway: python bot.py)
================================================================
2 bots ek hi process me chalte hain:

  1) PRE-OPEN GEMS
     09:00-09:08 AM IST  -> NSE pre-open market scan
     09:10 AM IST         -> Telegram par final list (1-10 stocks)

  2) INTRADAY SURGE SCANNER
     09:30 AM - 03:30 PM IST -> Nifty Midcap150 + Smallcap250
     Jab kisi stock ka volume + buyers achanak badhe -> alert
     Max 10 alerts/din, har stock sirf ek baar/din

Env variables (Railway -> Variables):
  TELEGRAM_BOT_TOKEN = <bot father se mila token>
  TELEGRAM_CHAT_ID   = 7418177111,1391074551   (comma se multiple)

requirements.txt:
  requests
  yfinance
================================================================
"""

import os
import time
import math
import threading
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer


# ================================================================
# SHARED CONFIG
# ================================================================

IST = ZoneInfo("Asia/Kolkata")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

_raw_chat_ids = os.getenv("TELEGRAM_CHAT_ID", "7418177111,1391074551")
CHAT_IDS = []
for part in _raw_chat_ids.replace(";", ",").split(","):
    part = part.strip()
    if part:
        CHAT_IDS.append(part)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def telegram_send(text):
    """Sabhi configured chat IDs par message bhejta hai."""
    if not BOT_TOKEN or not CHAT_IDS:
        print("Telegram credentials missing", flush=True)
        return False

    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    ok_any = False

    for chat_id in CHAT_IDS:
        try:
            resp = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                ok_any = True
            else:
                print("Telegram error [" + chat_id + "]: " +
                      str(resp.status_code) + " " + resp.text[:300], flush=True)
        except Exception as err:
            print("Telegram exception [" + chat_id + "]: " + str(err), flush=True)
        time.sleep(0.3)

    return ok_any


def safe_num(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in ("", "-", "N/A", "NA", "None"):
                return default
        return float(value)
    except Exception:
        return default


def wait_until(hour, minute):
    while True:
        now = datetime.now(IST)
        if (now.hour, now.minute) >= (hour, minute):
            return
        time.sleep(5)


# ================================================================
# KEEP-ALIVE WEB SERVER
# Railway trial plan background worker ko traffic na hone par
# sula deta hai. Ye server ek URL deta hai jisko bahar se
# (cron-job.org / UptimeRobot) har 5 min ping karke jagaye rakhte hain.
# ================================================================

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def log_message(self, fmt, *args):
        pass


def start_keepalive_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    print("Keep-alive server listening on port " + str(port), flush=True)
    server.serve_forever()


# ================================================================
# ================================================================
#   PART 1 : PRE-OPEN GEMS  (09:00 - 09:10 AM)
# ================================================================
# ================================================================

PO_BOSS_MIN_CHANGE = 2.0
PO_BOSS_MIN_RATIO = 3.0
PO_BOSS_MIN_BUY_QTY = 50000
PO_BOSS_SERIES = "EQ"

PO_MIN_GEMS = 1
PO_MAX_GEMS = 10
PO_MIN_FINAL_SCORE = 35

PO_HARD_MIN_PRICE = 50
PO_CIRCUIT_BUFFER = 0.8

PO_LOW_PRICE = 50
PO_VERY_LOW_PRICE = 20

PO_NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
PO_NSE_QUOTE = "https://www.nseindia.com/api/quote-equity?symbol="

po_session = requests.Session()
po_fundamental_cache = {}
po_band_cache = {}


def po_clean(value):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


def po_get_nse_data():
    try:
        try:
            po_session.get("https://www.nseindia.com/", headers=HTTP_HEADERS, timeout=10)
        except Exception:
            pass
        resp = po_session.get(PO_NSE_URL, headers=HTTP_HEADERS, timeout=15)
        if resp.status_code != 200:
            print("PO NSE HTTP: " + str(resp.status_code), flush=True)
            return []
        data = resp.json()
        if isinstance(data, dict):
            return data.get("data", [])
        return data
    except Exception as err:
        print("PO NSE error: " + str(err), flush=True)
        return []


def po_get_price_band(symbol):
    if symbol in po_band_cache:
        return po_band_cache[symbol]
    band = None
    try:
        resp = po_session.get(PO_NSE_QUOTE + symbol, headers=HTTP_HEADERS, timeout=12)
        raw = str(resp.json().get("priceInfo", {}).get("pPriceBand", "")).strip()
        if raw.replace(".", "").isdigit():
            band = float(raw)
    except Exception:
        pass
    po_band_cache[symbol] = band
    time.sleep(0.3)
    return band


def po_get_nse_mcap_price(symbol):
    """Yahoo fail ho to NSE se hi market cap + price nikalo (issuedSize * lastPrice)."""
    try:
        resp = po_session.get(PO_NSE_QUOTE + symbol, headers=HTTP_HEADERS, timeout=12)
        data = resp.json()
        issued_size = po_clean(data.get("securityInfo", {}).get("issuedSize"))
        last_price = po_clean(data.get("priceInfo", {}).get("lastPrice"))
        mcap_cr = None
        if issued_size and last_price:
            mcap_cr = (issued_size * last_price) / 10000000
        return mcap_cr, last_price
    except Exception as err:
        print("PO NSE mcap error " + symbol + ": " + str(err), flush=True)
        return None, None


def po_get_fundamentals(symbol):
    if symbol in po_fundamental_cache:
        return po_fundamental_cache[symbol]

    result = {
        "market_cap": None, "roe": None, "roce": None, "de": None,
        "sales_growth": None, "profit_growth": None,
        "pledge": None, "price": None,
    }
    try:
        info = yf.Ticker(symbol + ".NS").info

        mc = po_clean(info.get("marketCap"))
        if mc is not None:
            result["market_cap"] = mc / 10000000

        price = po_clean(info.get("currentPrice"))
        if price is None:
            price = po_clean(info.get("regularMarketPrice"))
        result["price"] = price

        roe = po_clean(info.get("returnOnEquity"))
        if roe is not None:
            result["roe"] = roe * 100

        roce = po_clean(info.get("returnOnCapitalEmployed"))
        if roce is not None:
            result["roce"] = roce * 100 if roce < 1 else roce

        de = po_clean(info.get("debtToEquity"))
        if de is not None:
            result["de"] = de / 100 if de > 20 else de

        sales = po_clean(info.get("revenueGrowth"))
        if sales is not None:
            result["sales_growth"] = sales * 100

        profit = po_clean(info.get("earningsGrowth"))
        if profit is not None:
            result["profit_growth"] = profit * 100

        pledge = po_clean(info.get("pledgeRatio"))
        if pledge is not None:
            result["pledge"] = pledge * 100
    except Exception as err:
        print("PO fundamentals error " + symbol + ": " + str(err), flush=True)

    # Yahoo fail/empty ho to NSE se market cap + price fallback le lo
    if result["market_cap"] is None or result["price"] is None:
        nse_mcap, nse_price = po_get_nse_mcap_price(symbol)
        if result["market_cap"] is None and nse_mcap is not None:
            result["market_cap"] = nse_mcap
        if result["price"] is None and nse_price is not None:
            result["price"] = nse_price

    po_fundamental_cache[symbol] = result
    return result


def po_boss_filter(record):
    try:
        metadata = record.get("metadata", {})
        detail = record.get("detail", {})
        symbol = metadata.get("symbol")
        series = metadata.get("series")
        change = safe_num(metadata.get("pChange"))
        iep = safe_num(metadata.get("iep"))

        pre = detail.get("preOpenMarket", {})
        buy_qty = safe_num(pre.get("totalBuyQuantity"))
        sell_qty = safe_num(pre.get("totalSellQuantity"))

        if not symbol:
            return None
        if series != PO_BOSS_SERIES:
            return None
        if change < PO_BOSS_MIN_CHANGE:
            return None
        if buy_qty < PO_BOSS_MIN_BUY_QTY:
            return None
        if sell_qty <= 0:
            return None

        ratio = buy_qty / sell_qty
        if ratio < PO_BOSS_MIN_RATIO:
            return None

        return {
            "symbol": symbol, "series": series, "change": change,
            "iep": iep, "buy_qty": buy_qty, "sell_qty": sell_qty,
            "ratio": ratio,
        }
    except Exception:
        return None


def po_buyer_score(item):
    ratio = item["ratio"]
    buy_qty = item["buy_qty"]
    change = item["change"]

    if ratio <= 3:
        ratio_score = 25
    elif ratio >= 25:
        ratio_score = 100
    else:
        ratio_score = 25 + ((ratio - 3) / 22) * 75

    if buy_qty <= 50000:
        qty_score = 20
    else:
        qty_score = min(100, 20 + math.log10(buy_qty / 50000) * 45)

    change_score = min(100, max(0, change * 4))

    return round(ratio_score * 0.50 + qty_score * 0.30 + change_score * 0.20, 2)


def po_quality_score(f):
    score = 0
    reasons = []

    if f["market_cap"] is not None:
        if f["market_cap"] >= 1000:
            score += 2
            reasons.append("Strong Market Cap")
        elif f["market_cap"] >= 500:
            score += 1
            reasons.append("Market Cap")

    if f["sales_growth"] is not None:
        if f["sales_growth"] >= 10:
            score += 1
            reasons.append("Sales Growth")
        elif f["sales_growth"] > 0:
            score += 0.5

    if f["profit_growth"] is not None:
        if f["profit_growth"] >= 10:
            score += 1
            reasons.append("Profit Growth")
        elif f["profit_growth"] > 0:
            score += 0.5

    if f["roe"] is not None and f["roe"] >= 12:
        score += 1
        reasons.append("ROE")

    if f["roce"] is not None and f["roce"] >= 15:
        score += 1
        reasons.append("ROCE")

    if f["de"] is not None:
        if f["de"] <= 0.50:
            score += 1
            reasons.append("Low D/E")
        elif f["de"] <= 1.0:
            score += 0.5

    if f["pledge"] is not None and f["pledge"] <= 5:
        score += 1
        reasons.append("Low Pledge")

    return round(score, 1), reasons


def po_risk_penalty(f, iep=None):
    penalty = 0
    reasons = []

    mc = f["market_cap"]
    price = f["price"] if f["price"] is not None else iep

    if mc is not None:
        if mc < 100:
            penalty += 25
            reasons.append("Very Small Cap")
        elif mc < 250:
            penalty += 15
            reasons.append("Small Cap")
        elif mc < 500:
            penalty += 7
            reasons.append("Lower Market Cap")

    if price is not None:
        if price < PO_VERY_LOW_PRICE:
            penalty += 20
            reasons.append("Very Low Price")
        elif price < PO_LOW_PRICE:
            penalty += 8
            reasons.append("Low Price")

    if f["de"] is not None:
        if f["de"] > 3:
            penalty += 15
            reasons.append("High D/E")
        elif f["de"] > 1:
            penalty += 6
            reasons.append("D/E > 1")

    return penalty, reasons


def po_final_score(item):
    bscore = po_buyer_score(item)
    f = item["fundamentals"]
    qscore, qreasons = po_quality_score(f)
    penalty, preasons = po_risk_penalty(f, item["iep"])

    quality_norm = min(100, (qscore / 7) * 100)
    final = bscore * 0.60 + quality_norm * 0.30 - penalty * 0.10

    return {
        "buyer_score": round(bscore, 2),
        "quality_score": qscore,
        "quality_reasons": qreasons,
        "risk_penalty": penalty,
        "risk_reasons": preasons,
        "final_score": round(final, 2),
    }


def po_process_records(records):
    candidates = []
    for record in records:
        item = po_boss_filter(record)
        if not item:
            continue
        item["fundamentals"] = po_get_fundamentals(item["symbol"])
        item.update(po_final_score(item))
        candidates.append(item)
    return candidates


def po_near_circuit(item):
    band = po_get_price_band(item["symbol"])
    item["band"] = band
    return bool(band) and item["change"] >= band * PO_CIRCUIT_BUFFER


def po_is_penny(item):
    price = item["fundamentals"]["price"] or item["iep"]
    return bool(price) and price < PO_HARD_MIN_PRICE


def po_select_gems(candidates):
    if not candidates:
        return []

    candidates = sorted(
        candidates,
        key=lambda x: (x["final_score"], x["buyer_score"], x["quality_score"], x["ratio"]),
        reverse=True,
    )

    top = candidates[:25]
    for c in top:
        c["near_circuit"] = po_near_circuit(c)
        c["penny"] = po_is_penny(c)

    picks = [c for c in top if not c["near_circuit"] and not c["penny"]
             and c["final_score"] >= PO_MIN_FINAL_SCORE]

    if len(picks) < PO_MIN_GEMS:
        picks = [c for c in top if not c["near_circuit"] and not c["penny"]]

    if len(picks) < PO_MIN_GEMS:
        picks = [c for c in top if not c["near_circuit"]]

    if len(picks) < PO_MIN_GEMS:
        picks = top[:1]

    return picks[:PO_MAX_GEMS]


def po_fmt_cr(v):
    return "N/A" if v is None else "Rs " + format(v, ",.0f") + " Cr"


def po_fmt_pct(v):
    return "N/A" if v is None else format(v, ".1f") + "%"


def po_fmt_qty(v):
    return format(int(v), ",")


def po_send_gem(item, rank):
    f = item["fundamentals"]
    risk_list = list(item["risk_reasons"])
    if item.get("near_circuit"):
        risk_list.append("Circuit ke paas")
    if item.get("penny"):
        risk_list.append("Penny price")
    risk = ", ".join(risk_list) if risk_list else "Low Risk"

    de_txt = format(f["de"], ".2f") if f["de"] is not None else "N/A"
    band_txt = format(item["band"], ".0f") + "%" if item.get("band") else "N/A"

    msg = (
        "GEM #" + str(rank) + "\n\n"
        + item["symbol"] + "  (Rs " + format(item["iep"], ".2f") + ")\n\n"
        + "--- BUYER STRENGTH ---\n"
        + "IEP Change : +" + format(item["change"], ".2f") + "%\n"
        + "Price Band : " + band_txt + "\n"
        + "B/S Ratio  : " + format(item["ratio"], ".2f") + "x\n"
        + "Buy Qty    : " + po_fmt_qty(item["buy_qty"]) + "\n"
        + "Sell Qty   : " + po_fmt_qty(item["sell_qty"]) + "\n"
        + "Buyer Score: " + str(item["buyer_score"]) + "/100\n\n"
        + "--- FUNDAMENTALS ---\n"
        + "Market Cap : " + po_fmt_cr(f["market_cap"]) + "\n"
        + "ROE        : " + po_fmt_pct(f["roe"]) + "\n"
        + "ROCE       : " + po_fmt_pct(f["roce"]) + "\n"
        + "D/E        : " + de_txt + "\n"
        + "Sales Gr   : " + po_fmt_pct(f["sales_growth"]) + "\n"
        + "Profit Gr  : " + po_fmt_pct(f["profit_growth"]) + "\n"
        + "Pledge     : " + po_fmt_pct(f["pledge"]) + "\n"
        + "Quality    : " + str(item["quality_score"]) + "/7\n\n"
        + "--- RISK CHECK ---\n"
        + risk + "\n\n"
        + "FINAL SCORE : " + str(item["final_score"]) + "/100\n\n"
        + "Sirf screening, advice nahi."
    )
    telegram_send(msg)
    time.sleep(0.4)


def po_send_summary(gems):
    lines = ["PRE-OPEN GEMS SUMMARY (" + str(len(gems)) + " stocks)\n"]
    for i, g in enumerate(gems, 1):
        lines.append(
            str(i) + ". " + g["symbol"]
            + "  +" + format(g["change"], ".1f") + "%"
            + "  " + format(g["ratio"], ".1f") + "x"
            + "  Score " + str(g["final_score"])
        )
    lines.append("\nStoploss zaroor rakhein.")
    telegram_send("\n".join(lines))


def po_run_today():
    telegram_send(
        "PRE-OPEN SCANNING STARTED\n"
        "09:00 - 09:08 AM IST, final list 09:10 AM"
    )

    latest = []
    got_data = False

    while True:
        now = datetime.now(IST)
        if (now.hour, now.minute) > (9, 8):
            break
        records = po_get_nse_data()
        print(datetime.now(IST).strftime("%H:%M:%S") + " PO records: " + str(len(records)), flush=True)
        if records:
            got_data = True
            candidates = po_process_records(records)
            if candidates:
                latest = candidates
        time.sleep(20)

    if not got_data:
        telegram_send("NSE se pre-open data nahi mila aaj (holiday ya block ho sakta hai).")
        return

    wait_until(9, 10)
    records = po_get_nse_data()
    final_candidates = po_process_records(records) if records else latest
    if not final_candidates:
        final_candidates = latest

    gems = po_select_gems(final_candidates)

    if not gems:
        telegram_send("Aaj BOSS filter me koi stock match nahi hua.")
        return

    for i, g in enumerate(gems, 1):
        po_send_gem(g, i)
    po_send_summary(gems)


def po_main_loop():
    last_run = None
    while True:
        now = datetime.now(IST)
        today = now.date()

        if now.weekday() < 5 and last_run != today and (now.hour, now.minute) <= (9, 8):
            last_run = today
            try:
                po_run_today()
            except Exception as err:
                telegram_send("Pre-open bot error: " + str(err))
                print("po_run_today error: " + str(err), flush=True)
            po_fundamental_cache.clear()
            po_band_cache.clear()

        time.sleep(20)


# ================================================================
# ================================================================
#   PART 2 : INTRADAY MID/SMALLCAP SURGE SCANNER (09:15 - 15:30)
# ================================================================
# ================================================================

ID_INDEXES = ["NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]

ID_MARKET_START = (9, 15)
ID_WARMUP_UNTIL = (9, 30)
ID_MARKET_END = (15, 30)
ID_POLL_INTERVAL_SEC = 180
ID_BASELINE_MIN_SAMPLES = 3

ID_VOLUME_SURGE_RATIO = 2.2
ID_PRICE_MIN_MOVE = 0.3
ID_BUYER_MIN_RATIO = 1.5

ID_MIN_PRICE = 50
ID_CIRCUIT_BUFFER = 0.8
ID_MAX_ALERTS_PER_DAY = 10
ID_MIN_ALERT_SCORE = 40

ID_MAX_PE = 100
ID_MIN_ROE = 0.0
ID_MAX_DE = 2.5
ID_MIN_MCAP_CR = 500

ID_NSE_INDEX_URL = "https://www.nseindia.com/api/equity-stockIndices?index={idx}"
ID_NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={sym}"

id_session = requests.Session()
id_fundamental_cache = {}
id_history = {}
id_alerted_today = set()
id_alert_count_today = 0


def id_refresh_cookies():
    try:
        id_session.get("https://www.nseindia.com/", headers=HTTP_HEADERS, timeout=10)
    except Exception:
        pass


def id_get_index_data(index_name):
    try:
        url = ID_NSE_INDEX_URL.format(idx=requests.utils.quote(index_name))
        resp = id_session.get(url, headers=HTTP_HEADERS, timeout=15)
        if resp.status_code != 200:
            print("ID NSE index HTTP " + index_name + ": " + str(resp.status_code), flush=True)
            return []
        data = resp.json().get("data", [])
        return [d for d in data if d.get("symbol") and d.get("series") == "EQ"]
    except Exception as err:
        print("ID NSE index error " + index_name + ": " + str(err), flush=True)
        return []


def id_get_universe():
    id_refresh_cookies()
    combined = {}
    for idx in ID_INDEXES:
        for d in id_get_index_data(idx):
            combined[d["symbol"]] = d
    return combined


def id_get_quote_detail(symbol):
    try:
        url = ID_NSE_QUOTE_URL.format(sym=symbol)
        resp = id_session.get(url, headers=HTTP_HEADERS, timeout=12)
        data = resp.json()
        depth = data.get("marketDeptOrderBook", {})
        buy_qty = safe_num(depth.get("totalBuyQuantity"))
        sell_qty = safe_num(depth.get("totalSellQuantity"))
        band_raw = data.get("priceInfo", {}).get("pPriceBand", "")
        band = float(band_raw) if str(band_raw).replace(".", "").isdigit() else None
        return buy_qty, sell_qty, band
    except Exception as err:
        print("ID quote error " + symbol + ": " + str(err), flush=True)
        return 0, 0, None


def id_get_nse_mcap(symbol):
    """Yahoo fail ho to NSE se hi market cap nikalo (issuedSize * lastPrice)."""
    try:
        url = ID_NSE_QUOTE_URL.format(sym=symbol)
        resp = id_session.get(url, headers=HTTP_HEADERS, timeout=12)
        data = resp.json()
        issued_size = safe_num(data.get("securityInfo", {}).get("issuedSize"), None)
        last_price = safe_num(data.get("priceInfo", {}).get("lastPrice"), None)
        if issued_size and last_price:
            return (issued_size * last_price) / 10000000
        return None
    except Exception as err:
        print("ID NSE mcap error " + symbol + ": " + str(err), flush=True)
        return None


def id_get_fundamentals(symbol):
    if symbol in id_fundamental_cache:
        return id_fundamental_cache[symbol]

    result = {"market_cap": None, "pe": None, "roe": None, "de": None}
    try:
        info = yf.Ticker(symbol + ".NS").info
        mc = info.get("marketCap")
        if mc:
            result["market_cap"] = mc / 10000000
        result["pe"] = info.get("trailingPE")
        result["roe"] = info.get("returnOnEquity")
        de = info.get("debtToEquity")
        if de is not None:
            result["de"] = de / 100 if de > 20 else de
    except Exception as err:
        print("ID fundamentals error " + symbol + ": " + str(err), flush=True)

    if result["market_cap"] is None:
        nse_mcap = id_get_nse_mcap(symbol)
        if nse_mcap is not None:
            result["market_cap"] = nse_mcap

    id_fundamental_cache[symbol] = result
    return result


def id_fundamentals_ok(f):
    if f["market_cap"] is not None and f["market_cap"] < ID_MIN_MCAP_CR:
        return False
    if f["pe"] is not None and (f["pe"] < 0 or f["pe"] > ID_MAX_PE):
        return False
    if f["roe"] is not None and f["roe"] < ID_MIN_ROE:
        return False
    if f["de"] is not None and f["de"] > ID_MAX_DE:
        return False
    return True


def id_update_history_and_detect(universe, now):
    candidates = []

    for symbol, d in universe.items():
        price = safe_num(d.get("lastPrice"))
        pchange = safe_num(d.get("pChange"))
        cum_vol = safe_num(d.get("totalTradedVolume"))

        if price <= 0:
            continue

        hist = id_history.setdefault(symbol, [])
        hist.append((now, cum_vol, price, pchange))
        if len(hist) > 30:
            del hist[0]

        if len(hist) < ID_BASELINE_MIN_SAMPLES + 1:
            continue

        interval_vol = cum_vol - hist[-2][1]
        if interval_vol <= 0:
            continue

        deltas = []
        for i in range(1, len(hist) - 1):
            d_vol = hist[i][1] - hist[i - 1][1]
            if d_vol > 0:
                deltas.append(d_vol)

        if not deltas:
            continue

        baseline = sum(deltas) / len(deltas)
        if baseline <= 0:
            continue

        surge_ratio = interval_vol / baseline

        if surge_ratio >= ID_VOLUME_SURGE_RATIO and pchange >= ID_PRICE_MIN_MOVE:
            candidates.append({
                "symbol": symbol, "price": price, "pchange": pchange,
                "surge_ratio": surge_ratio, "cum_vol": cum_vol,
            })

    return candidates


def id_score_candidate(c, buy_qty, sell_qty, f):
    ratio = (buy_qty / sell_qty) if sell_qty > 0 else 0
    ratio_score = min(100, (ratio / 3.5) * 100) if ratio else 0
    vol_score = min(100, (c["surge_ratio"] / 8) * 100)
    price_score = min(100, c["pchange"] * 8)

    quality = 0
    if f["market_cap"] and f["market_cap"] >= 2000:
        quality += 30
    elif f["market_cap"] and f["market_cap"] >= 1000:
        quality += 20
    elif f["market_cap"] and f["market_cap"] >= 500:
        quality += 10
    if f["roe"] is not None and f["roe"] >= 0.12:
        quality += 20
    if f["de"] is not None and f["de"] <= 0.7:
        quality += 15
    if f["pe"] is not None and 0 < f["pe"] <= 40:
        quality += 15
    quality = min(100, quality)

    final = ratio_score * 0.35 + vol_score * 0.30 + price_score * 0.10 + quality * 0.25
    return round(final, 2), round(ratio, 2)


def id_send_alert(c, buy_qty, sell_qty, ratio, f, score):
    de_txt = format(f["de"], ".2f") if f["de"] is not None else "N/A"
    roe_txt = format(f["roe"] * 100, ".1f") + "%" if f["roe"] is not None else "N/A"
    pe_txt = format(f["pe"], ".1f") if f["pe"] is not None else "N/A"
    mcap_txt = "Rs " + format(f["market_cap"], ",.0f") + " Cr" if f["market_cap"] is not None else "N/A"

    msg = (
        "INTRADAY SURGE ALERT\n\n"
        + c["symbol"] + "   Rs " + format(c["price"], ".2f")
        + "  (" + format(c["pchange"], "+.2f") + "%)\n"
        + datetime.now(IST).strftime("%H:%M") + " IST\n\n"
        + "--- VOLUME + BUYERS ---\n"
        + "Volume Surge : " + format(c["surge_ratio"], ".1f") + "x normal\n"
        + "Buy:Sell     : " + format(ratio, ".1f") + "x\n"
        + "Buy Qty      : " + format(int(buy_qty), ",") + "\n"
        + "Sell Qty     : " + format(int(sell_qty), ",") + "\n\n"
        + "--- FUNDAMENTALS ---\n"
        + "Market Cap : " + mcap_txt + "\n"
        + "ROE        : " + roe_txt + "\n"
        + "D/E        : " + de_txt + "\n"
        + "PE         : " + pe_txt + "\n\n"
        + "SCORE : " + str(score) + "/100\n\n"
        + "Sirf screening, advice nahi. Stoploss zaroor rakhein."
    )
    telegram_send(msg)


def id_in_market_hours(now):
    return ID_MARKET_START <= (now.hour, now.minute) <= ID_MARKET_END


def id_past_warmup(now):
    return (now.hour, now.minute) >= ID_WARMUP_UNTIL


def id_run_day():
    global id_alert_count_today
    id_history.clear()
    id_alerted_today.clear()
    id_alert_count_today = 0

    telegram_send(
        "INTRADAY SCANNER STARTED\n"
        "09:15 - 15:30 IST, poll every 3 min\n"
        "Universe: Nifty Midcap 150 + Smallcap 250"
    )

    while True:
        now = datetime.now(IST)
        if (now.hour, now.minute) > ID_MARKET_END:
            break
        if (now.hour, now.minute) < ID_MARKET_START:
            time.sleep(10)
            continue

        universe = id_get_universe()
        print(
            now.strftime("%H:%M:%S") + " ID universe size: " + str(len(universe)),
            flush=True,
        )
        if not universe:
            time.sleep(ID_POLL_INTERVAL_SEC)
            continue

        candidates = id_update_history_and_detect(universe, now)
        print(
            now.strftime("%H:%M:%S") + " ID surge candidates: " + str(len(candidates)),
            flush=True,
        )

        if id_past_warmup(now) and candidates and id_alert_count_today < ID_MAX_ALERTS_PER_DAY:
            candidates.sort(key=lambda x: x["surge_ratio"], reverse=True)

            for c in candidates:
                if id_alert_count_today >= ID_MAX_ALERTS_PER_DAY:
                    break
                if c["symbol"] in id_alerted_today:
                    continue
                if c["price"] < ID_MIN_PRICE:
                    continue

                buy_qty, sell_qty, band = id_get_quote_detail(c["symbol"])
                if band and c["pchange"] >= band * ID_CIRCUIT_BUFFER:
                    continue
                if sell_qty <= 0 or (buy_qty / sell_qty) < ID_BUYER_MIN_RATIO:
                    continue

                f = id_get_fundamentals(c["symbol"])
                if not id_fundamentals_ok(f):
                    continue

                score, ratio = id_score_candidate(c, buy_qty, sell_qty, f)
                if score < ID_MIN_ALERT_SCORE:
                    continue

                id_send_alert(c, buy_qty, sell_qty, ratio, f, score)
                id_alerted_today.add(c["symbol"])
                id_alert_count_today += 1
                time.sleep(0.5)

        time.sleep(ID_POLL_INTERVAL_SEC)

    if id_alert_count_today == 0:
        telegram_send("Aaj koi stock volume+buyer surge criteria par match nahi hua.")
    else:
        telegram_send("Market band. Aaj total " + str(id_alert_count_today) + " alerts bheje gaye.")


def id_main_loop():
    last_run = None
    while True:
        now = datetime.now(IST)
        today = now.date()

        if now.weekday() < 5 and last_run != today and (now.hour, now.minute) <= ID_MARKET_END:
            last_run = today
            try:
                id_run_day()
            except Exception as err:
                telegram_send("Intraday bot error: " + str(err))
                print("id_run_day error: " + str(err), flush=True)
            id_fundamental_cache.clear()

        time.sleep(20)


# ================================================================
# ENTRY POINT
# ================================================================

def run_forever(name, fn):
    while True:
        try:
            fn()
        except Exception as err:
            print("[" + name + "] crashed: " + str(err) + " - restart in 15s", flush=True)
            time.sleep(15)


def main():
    telegram_send("Bot online (Railway). Pre-open 9:00-9:10, Intraday 9:15-15:30.")

    t0 = threading.Thread(target=start_keepalive_server, daemon=True)
    t1 = threading.Thread(target=run_forever, args=("PREOPEN", po_main_loop), daemon=True)
    t2 = threading.Thread(target=run_forever, args=("INTRADAY", id_main_loop), daemon=True)

    t0.start()
    t1.start()
    t2.start()

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
