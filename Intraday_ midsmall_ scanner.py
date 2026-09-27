import os
import time
import math
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# INTRADAY MID+SMALLCAP VOLUME/BUYER SURGE SCANNER
# Market hours: 09:15 - 15:30 IST
# Universe: NIFTY MIDCAP 150 + NIFTY SMALLCAP 250
# Alerts: sudden volume surge + sudden buyer surge, max 10/day
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_raw_ids = os.getenv("TELEGRAM_CHAT_ID", "7418177111,1391074551")
TELEGRAM_CHAT_IDS = [x.strip() for x in _raw_ids.replace(";", ",").split(",") if x.strip()]

IST = ZoneInfo("Asia/Kolkata")

NSE_HOME = "https://www.nseindia.com/"
NSE_INDEX_URL = "https://www.nseindia.com/api/equity-stockIndices?index={idx}"
NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={sym}"

INDEXES = ["NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]

# ---------------- TIMING ----------------
MARKET_START = (9, 15)
WARMUP_UNTIL = (9, 30)      # pehle 15 min sirf data collect, alert nahi (volume abhi settle nahi hua)
MARKET_END = (15, 30)
POLL_INTERVAL_SEC = 180      # har 3 min data lo
BASELINE_MIN_SAMPLES = 3     # kam se kam itne poll ke baad hi surge check

# ---------------- SURGE THRESHOLDS ----------------
VOLUME_SURGE_RATIO = 3.0     # is interval ka volume >= 3x average interval volume
PRICE_MIN_MOVE = 0.5         # kam se kam 0.5% up move (surge)
BUYER_MIN_RATIO = 1.5        # order-book buy/sell >= 1.5x (sirf top candidates ke liye check hoga)

# ---------------- SAFETY / QUALITY ----------------
MIN_PRICE = 50
CIRCUIT_BUFFER = 0.8         # band ka 80%+ = circuit ke paas, skip
MAX_ALERTS_PER_DAY = 10
MIN_ALERT_SCORE = 40         # loose ho sakta hai agar din bhar me kam mile

# fundamentals (loose but not junk)
MAX_PE = 100
MIN_ROE = 0.0                # sirf negative ROE reject
MAX_DE = 2.5                 # debt/equity
MIN_MCAP_CR = 500

# ============================================================
# SESSION
# ============================================================
session = requests.Session()
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
    "Connection": "keep-alive",
}

fundamental_cache = {}
band_cache = {}
history = {}          # symbol -> list of (timestamp, cum_volume, price, pchange)
alerted_today = set()
alert_count_today = 0


# ============================================================
# TELEGRAM
# ============================================================
def telegram_send(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            r = session.post(url, data={"chat_id": chat_id, "text": message,
                                        "disable_web_page_preview": True}, timeout=15)
            if r.status_code != 200:
                print(f"Telegram error [{chat_id}]:", r.status_code, r.text[:300])
        except Exception as e:
            print(f"Telegram exception [{chat_id}]:", e)
        time.sleep(0.3)


# ============================================================
# HELPERS
# ============================================================
def num(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v in ("", "-", "N/A", "NA", "None"):
                return default
        return float(v)
    except Exception:
        return default


def refresh_cookies():
    try:
        session.get(NSE_HOME, headers=HEADERS, timeout=10)
    except Exception:
        pass


# ============================================================
# NSE: INDEX LIVE DATA (ek call me poore index ka data)
# ============================================================
def get_index_data(index_name):
    try:
        url = NSE_INDEX_URL.format(idx=requests.utils.quote(index_name))
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print("NSE index HTTP:", index_name, r.status_code)
            return []
        data = r.json().get("data", [])
        # pehli entry index summary hoti hai (symbol == index name), usko hata do
        return [d for d in data if d.get("symbol") and d.get("series") == "EQ"]
    except Exception as e:
        print("NSE index error:", index_name, e)
        return []


def get_universe():
    refresh_cookies()
    combined = {}
    for idx in INDEXES:
        for d in get_index_data(idx):
            combined[d["symbol"]] = d  # dedupe agar dono index me ho
    return combined


# ============================================================
# NSE: PER-SYMBOL QUOTE (buy/sell qty + band) - sirf top candidates ke liye
# ============================================================
def get_quote_detail(symbol):
    try:
        r = session.get(NSE_QUOTE_URL.format(sym=symbol), headers=HEADERS, timeout=12)
        j = r.json()
        depth = j.get("marketDeptOrderBook", {})
        buy_qty = num(depth.get("totalBuyQuantity"))
        sell_qty = num(depth.get("totalSellQuantity"))
        band = j.get("priceInfo", {}).get("pPriceBand", "")
        band = float(band) if str(band).replace(".", "").isdigit() else None
        return buy_qty, sell_qty, band
    except Exception as e:
        print("Quote error:", symbol, e)
        return 0, 0, None


# ============================================================
# FUNDAMENTALS
# ============================================================
def get_fundamentals(symbol):
    if symbol in fundamental_cache:
        return fundamental_cache[symbol]
    result = {"market_cap": None, "pe": None, "roe": None, "de": None}
    try:
        info = yf.Ticker(symbol + ".NS").info
        mc = info.get("marketCap")
        if mc:
            result["market_cap"] = mc / 10000000
        result["pe"] = info.get("trailingPE")
        roe = info.get("returnOnEquity")
        result["roe"] = roe if roe is not None else None
        de = info.get("debtToEquity")
        if de is not None:
            result["de"] = de / 100 if de > 20 else de
    except Exception as e:
        print("Fundamental error", symbol, e)
    fundamental_cache[symbol] = result
    return result


def fundamentals_ok(f):
    if f["market_cap"] is not None and f["market_cap"] < MIN_MCAP_CR:
        return False
    if f["pe"] is not None and (f["pe"] < 0 or f["pe"] > MAX_PE):
        return False
    if f["roe"] is not None and f["roe"] < MIN_ROE:
        return False
    if f["de"] is not None and f["de"] > MAX_DE:
        return False
    return True


# ============================================================
# SURGE DETECTION
# ============================================================
def update_history_and_detect(universe, now):
    """Har poll par history update karo, surge candidates return karo."""
    candidates = []

    for symbol, d in universe.items():
        price = num(d.get("lastPrice"))
        pchange = num(d.get("pChange"))
        cum_vol = num(d.get("totalTradedVolume"))

        if price <= 0:
            continue

        hist = history.setdefault(symbol, [])
        hist.append((now, cum_vol, price, pchange))
        if len(hist) > 30:
            del hist[0]

        if len(hist) < BASELINE_MIN_SAMPLES + 1:
            continue  # abhi baseline banane ke liye kaafi data nahi

        # is interval ka volume
        interval_vol = cum_vol - hist[-2][1]
        if interval_vol <= 0:
            continue

        # baseline = purane intervals ka average (current chhodkar)
        deltas = [hist[i][1] - hist[i - 1][1] for i in range(1, len(hist) - 1)]
        deltas = [x for x in deltas if x > 0]
        if not deltas:
            continue
        baseline = sum(deltas) / len(deltas)
        if baseline <= 0:
            continue

        surge_ratio = interval_vol / baseline

        if surge_ratio >= VOLUME_SURGE_RATIO and pchange >= PRICE_MIN_MOVE:
            candidates.append({
                "symbol": symbol, "price": price, "pchange": pchange,
                "surge_ratio": surge_ratio, "cum_vol": cum_vol,
            })

    return candidates


# ============================================================
# SCORING
# ============================================================
def score_candidate(c, buy_qty, sell_qty, f):
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


# ============================================================
# ALERT
# ============================================================
def send_alert(c, buy_qty, sell_qty, ratio, f, band, score):
    de_txt = f"{f['de']:.2f}" if f["de"] is not None else "N/A"
    roe_txt = f"{f['roe']*100:.1f}%" if f["roe"] is not None else "N/A"
    pe_txt = f"{f['pe']:.1f}" if f["pe"] is not None else "N/A"
    mcap_txt = f"₹{f['market_cap']:,.0f} Cr" if f["market_cap"] is not None else "N/A"

    msg = f"""
🚨 INTRADAY SURGE ALERT

📌 {c['symbol']}   ₹{c['price']:.2f}  ({c['pchange']:+.2f}%)
🕐 {datetime.now(IST).strftime('%H:%M')} IST

━━━━━━━━━━━━━━━━━━
📊 VOLUME + BUYERS
━━━━━━━━━━━━━━━━━━
🔥 Volume Surge : {c['surge_ratio']:.1f}x normal
⚖️ Buy:Sell     : {ratio:.1f}x
🟢 Buy Qty      : {int(buy_qty):,}
🔴 Sell Qty     : {int(sell_qty):,}

━━━━━━━━━━━━━━━━━━
🏦 FUNDAMENTALS
━━━━━━━━━━━━━━━━━━
💰 Market Cap : {mcap_txt}
ROE           : {roe_txt}
D/E           : {de_txt}
PE            : {pe_txt}

🏆 SCORE : {score}/100

⚠️ Sirf screening hai, advice nahi. Apna analysis aur stoploss zaroor rakhein.
"""
    telegram_send(msg)


# ============================================================
# MAIN LOOP (one trading day)
# ============================================================
def in_market_hours(now):
    return (MARKET_START <= (now.hour, now.minute) <= MARKET_END)


def past_warmup(now):
    return (now.hour, now.minute) >= WARMUP_UNTIL


def run_day():
    global alert_count_today
    history.clear()
    alerted_today.clear()
    alert_count_today = 0

    telegram_send("📡 Intraday Mid+Smallcap Scanner shuru\n"
                  "⏰ 09:15 - 15:30 IST | Poll: 3 min\n"
                  "🎯 Universe: Nifty Midcap 150 + Smallcap 250")

    while True:
        now = datetime.now(IST)
        if (now.hour, now.minute) > MARKET_END:
            break
        if (now.hour, now.minute) < MARKET_START:
            time.sleep(10)
            continue

        universe = get_universe()
        if not universe:
            time.sleep(POLL_INTERVAL_SEC)
            continue

        candidates = update_history_and_detect(universe, now)

        if past_warmup(now) and candidates and alert_count_today < MAX_ALERTS_PER_DAY:
            # sabse zyada surge wale pehle
            candidates.sort(key=lambda x: x["surge_ratio"], reverse=True)

            for c in candidates:
                if alert_count_today >= MAX_ALERTS_PER_DAY:
                    break
                if c["symbol"] in alerted_today:
                    continue
                if c["price"] < MIN_PRICE:
                    continue

                buy_qty, sell_qty, band = get_quote_detail(c["symbol"])
                if band and c["pchange"] >= band * CIRCUIT_BUFFER:
                    continue  # circuit ke paas
                if sell_qty <= 0 or (buy_qty / sell_qty) < BUYER_MIN_RATIO:
                    continue

                f = get_fundamentals(c["symbol"])
                if not fundamentals_ok(f):
                    continue

                score, ratio = score_candidate(c, buy_qty, sell_qty, f)
                if score < MIN_ALERT_SCORE:
                    continue

                send_alert(c, buy_qty, sell_qty, ratio, f, band, score)
                alerted_today.add(c["symbol"])
                alert_count_today += 1
                time.sleep(0.5)

        time.sleep(POLL_INTERVAL_SEC)

    if alert_count_today == 0:
        telegram_send("📭 Aaj koi bhi stock volume+buyer surge criteria par match nahi hua.")
    else:
        telegram_send(f"✅ Market band. Aaj total {alert_count_today} alerts bheje gaye.")


# ============================================================
# ENTRY POINT (roz chalega)
# ============================================================
def main():
    last_run_date = None
    while True:
        now = datetime.now(IST)
        today = now.date()

        if now.weekday() < 5 and last_run_date != today and (now.hour, now.minute) <= (9, 20):
            last_run_date = today
            try:
                run_day()
            except Exception as e:
                telegram_send(f"⚠️ Scanner error: {e}")
                print("run_day error:", e)
            fundamental_cache.clear()
            band_cache.clear()

        time.sleep(20)


if __name__ == "__main__":
    main()
