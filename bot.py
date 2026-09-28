"""
PREOPEN GEMS + INTRADAY MID/SMALLCAP SURGE  -  ALL-IN-ONE BOT
Start command:  python bot.py

Railway variables:
  TELEGRAM_BOT_TOKEN = <bot token>
  TELEGRAM_CHAT_ID   = 7418177111,1391074551
requirements.txt:  requests, yfinance
"""
import os
import time
import math
import threading
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# PART 1: PRE-OPEN (9:00-9:10)
# ============================================================

# ============================================================
# PREOPEN GEMS OFFICIAL  (v3)
# BOSS + BUYER PRIORITY + QUALITY + RISK + CIRCUIT/PENNY SAFETY
# Multi chat-id support
# ============================================================

pre_TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Comma separated: 7418177111,1391074551
pre__raw_ids = os.getenv("TELEGRAM_CHAT_ID", "7418177111,1391074551")
pre_TELEGRAM_CHAT_IDS = [x.strip() for x in pre__raw_ids.replace(";", ",").split(",") if x.strip()]

pre_NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
pre_NSE_HOME = "https://www.nseindia.com/"
pre_NSE_QUOTE = "https://www.nseindia.com/api/quote-equity?symbol="

pre_IST = ZoneInfo("Asia/Kolkata")
pre_SCAN_INTERVAL = 30

# ---------------- BOSS FILTER (LOCKED) ----------------
pre_BOSS_MIN_CHANGE = 2.0
pre_BOSS_MIN_RATIO = 3.0
pre_BOSS_MIN_BUY_QTY = 50000
pre_BOSS_SERIES = "EQ"

# ---------------- OUTPUT ----------------
pre_MIN_GEMS = 1
pre_MAX_GEMS = 10
pre_MIN_FINAL_SCORE = 35

# ---------------- SAFETY (naya) ----------------
pre_HARD_MIN_PRICE = 50          # isse niche = penny, final list se hata denge
pre_CIRCUIT_BUFFER = 0.8         # band ka 80% se upar = circuit ke paas
FINAL_SEND_HOUR, FINAL_SEND_MIN = 9, 10   # final list 9:10 par

# ---------------- QUALITY / RISK ----------------
pre_LOW_PRICE = 50
pre_VERY_LOW_PRICE = 20

pre_nse_session = requests.Session()
pre_nse_headers = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": pre_NSE_HOME,
    "Connection": "keep-alive",
}

pre_fundamental_cache = {}
pre_band_cache = {}


# ============================================================
# TELEGRAM  (sabhi chat IDs par bhejta hai)
# ============================================================
def pre_telegram_send(message):
    if not pre_TELEGRAM_BOT_TOKEN or not pre_TELEGRAM_CHAT_IDS:
        print("Telegram credentials missing")
        return False

    url = f"https://api.telegram.org/bot{pre_TELEGRAM_BOT_TOKEN}/sendMessage"
    ok_any = False

    for chat_id in pre_TELEGRAM_CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "text": message,
                      "disable_web_page_preview": True},
                timeout=15,
            )
            if r.status_code == 200:
                ok_any = True
            else:
                print(f"Telegram error [{chat_id}]:", r.status_code, r.text[:300])
        except Exception as e:
            print(f"Telegram exception [{chat_id}]:", e)
        time.sleep(0.3)

    return ok_any


# ============================================================
# HELPERS
# ============================================================
def pre_num(value, default=0):
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


def pre_clean(value):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


# ============================================================
# NSE
# ============================================================
def pre_get_nse_data():
    try:
        try:
            pre_nse_session.get(pre_NSE_HOME, headers=pre_nse_headers, timeout=10)
        except Exception:
            pass
        r = pre_nse_session.get(pre_NSE_URL, headers=pre_nse_headers, timeout=15)
        if r.status_code != 200:
            print("NSE HTTP:", r.status_code)
            return []
        data = r.json()
        if isinstance(data, dict):
            return data.get("data", [])
        return data
    except Exception as e:
        print("NSE error:", e)
        return []


def pre_get_price_band(symbol):
    """Price band % (None = no band / unknown)."""
    if symbol in pre_band_cache:
        return pre_band_cache[symbol]
    band = None
    try:
        r = pre_nse_session.get(pre_NSE_QUOTE + symbol, headers=pre_nse_headers, timeout=12)
        b = str(r.json().get("priceInfo", {}).get("pPriceBand", "")).strip()
        if b.replace(".", "").isdigit():
            band = float(b)
    except Exception:
        pass
    pre_band_cache[symbol] = band
    time.sleep(0.3)
    return band


# ============================================================
# FUNDAMENTALS
# ============================================================
def pre_get_fundamentals(symbol):
    if symbol in pre_fundamental_cache:
        return pre_fundamental_cache[symbol]

    result = {"market_cap": None, "roe": None, "roce": None, "de": None,
              "sales_growth": None, "profit_growth": None,
              "pledge": None, "price": None}
    try:
        info = yf.Ticker(symbol + ".NS").info

        mc = pre_clean(info.get("marketCap"))
        if mc is not None:
            result["market_cap"] = mc / 10000000

        price = pre_clean(info.get("currentPrice"))
        if price is None:
            price = pre_clean(info.get("regularMarketPrice"))
        result["price"] = price

        roe = pre_clean(info.get("returnOnEquity"))
        if roe is not None:
            result["roe"] = roe * 100

        roce = pre_clean(info.get("returnOnCapitalEmployed"))
        if roce is not None:
            result["roce"] = roce * 100 if roce < 1 else roce

        de = pre_clean(info.get("debtToEquity"))
        if de is not None:
            result["de"] = de / 100 if de > 20 else de

        sales = pre_clean(info.get("revenueGrowth"))
        if sales is not None:
            result["sales_growth"] = sales * 100

        profit = pre_clean(info.get("earningsGrowth"))
        if profit is not None:
            result["profit_growth"] = profit * 100

        pledge = pre_clean(info.get("pledgeRatio"))
        if pledge is not None:
            result["pledge"] = pledge * 100
    except Exception as e:
        print(f"Fundamental error {symbol}: {e}")

    pre_fundamental_cache[symbol] = result
    return result


# ============================================================
# BOSS FILTER
# ============================================================
def pre_boss_filter(record):
    try:
        metadata = record.get("metadata", {})
        detail = record.get("detail", {})
        symbol = metadata.get("symbol")
        series = metadata.get("series")
        change = pre_num(metadata.get("pChange"))
        iep = pre_num(metadata.get("iep"))
        pre = detail.get("preOpenMarket", {})
        buy_qty = pre_num(pre.get("totalBuyQuantity"))
        sell_qty = pre_num(pre.get("totalSellQuantity"))

        if not symbol:
            return None
        if series != pre_BOSS_SERIES:
            return None
        if change < pre_BOSS_MIN_CHANGE:
            return None
        if buy_qty < pre_BOSS_MIN_BUY_QTY:
            return None
        if sell_qty <= 0:
            return None
        ratio = buy_qty / sell_qty
        if ratio < pre_BOSS_MIN_RATIO:
            return None

        return {"symbol": symbol, "series": series, "change": change,
                "iep": iep, "buy_qty": buy_qty, "sell_qty": sell_qty,
                "ratio": ratio}
    except Exception:
        return None


# ============================================================
# SCORES
# ============================================================
def pre_buyer_score(item):
    ratio, buy_qty, change = item["ratio"], item["buy_qty"], item["change"]

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


def pre_quality_score(f):
    score, reasons = 0, []

    if f["market_cap"] is not None:
        if f["market_cap"] >= 1000:
            score += 2; reasons.append("Strong Market Cap")
        elif f["market_cap"] >= 500:
            score += 1; reasons.append("Market Cap")

    if f["sales_growth"] is not None:
        if f["sales_growth"] >= 10:
            score += 1; reasons.append("Sales Growth")
        elif f["sales_growth"] > 0:
            score += 0.5

    if f["profit_growth"] is not None:
        if f["profit_growth"] >= 10:
            score += 1; reasons.append("Profit Growth")
        elif f["profit_growth"] > 0:
            score += 0.5

    if f["roe"] is not None and f["roe"] >= 12:
        score += 1; reasons.append("ROE")

    if f["roce"] is not None and f["roce"] >= 15:
        score += 1; reasons.append("ROCE")

    if f["de"] is not None:
        if f["de"] <= 0.50:
            score += 1; reasons.append("Low D/E")
        elif f["de"] <= 1.0:
            score += 0.5

    if f["pledge"] is not None and f["pledge"] <= 5:
        score += 1; reasons.append("Low Pledge")

    return round(score, 1), reasons


def pre_risk_penalty(f, iep=None):
    penalty, reasons = 0, []
    mc = f["market_cap"]
    price = f["price"] if f["price"] is not None else iep

    if mc is not None:
        if mc < 100:
            penalty += 25; reasons.append("Very Small Cap")
        elif mc < 250:
            penalty += 15; reasons.append("Small Cap")
        elif mc < 500:
            penalty += 7; reasons.append("Lower Market Cap")

    if price is not None:
        if price < pre_VERY_LOW_PRICE:
            penalty += 20; reasons.append("Very Low Price")
        elif price < pre_LOW_PRICE:
            penalty += 8; reasons.append("Low Price")

    if f["de"] is not None:
        if f["de"] > 3:
            penalty += 15; reasons.append("High D/E")
        elif f["de"] > 1:
            penalty += 6; reasons.append("D/E > 1")

    return penalty, reasons


def pre_final_score(item):
    bscore = pre_buyer_score(item)
    f = item["fundamentals"]
    qscore, qreasons = pre_quality_score(f)
    penalty, preasons = pre_risk_penalty(f, item["iep"])
    quality_norm = min(100, (qscore / 7) * 100)
    final = bscore * 0.60 + quality_norm * 0.30 - penalty * 0.10
    return {"buyer_score": round(bscore, 2), "quality_score": qscore,
            "quality_reasons": qreasons, "risk_penalty": penalty,
            "risk_reasons": preasons, "final_score": round(final, 2)}


# ============================================================
# PROCESS + SELECT
# ============================================================
def pre_process_records(records):
    candidates = []
    for record in records:
        item = pre_boss_filter(record)
        if not item:
            continue
        item["fundamentals"] = pre_get_fundamentals(item["symbol"])
        item.update(pre_final_score(item))
        candidates.append(item)
    return candidates


def pre_near_circuit(item):
    band = pre_get_price_band(item["symbol"])
    item["band"] = band
    return bool(band) and item["change"] >= band * pre_CIRCUIT_BUFFER


def pre_is_penny(item):
    price = item["fundamentals"]["price"] or item["iep"]
    return bool(price) and price < pre_HARD_MIN_PRICE


def pre_select_gems(candidates):
    """Min 1, Max pre_MAX_GEMS. Circuit/penny hatate hain, par 0 kabhi nahi."""
    if not candidates:
        return []

    candidates = sorted(
        candidates,
        key=lambda x: (x["final_score"], x["buyer_score"],
                       x["quality_score"], x["ratio"]),
        reverse=True,
    )

    # Circuit check sirf top 25 par (API calls bachane ke liye)
    top = candidates[:25]
    for c in top:
        c["near_circuit"] = pre_near_circuit(c)
        c["penny"] = pre_is_penny(c)

    # Level 1: circuit nahi + penny nahi + score ok
    picks = [c for c in top if not c["near_circuit"] and not c["penny"]
             and c["final_score"] >= pre_MIN_FINAL_SCORE]

    # Level 2: score threshold hata do
    if len(picks) < pre_MIN_GEMS:
        picks = [c for c in top if not c["near_circuit"] and not c["penny"]]

    # Level 3: penny allow (circuit abhi bhi nahi)
    if len(picks) < pre_MIN_GEMS:
        picks = [c for c in top if not c["near_circuit"]]

    # Level 4: last fallback - best candidate (warning ke saath)
    if len(picks) < pre_MIN_GEMS:
        picks = top[:1]

    return picks[:pre_MAX_GEMS]


# ============================================================
# FORMAT + SEND
# ============================================================
def pre_fmt_cr(v):
    return "N/A" if v is None else f"₹{v:,.0f} Cr"


def pre_fmt_pct(v):
    return "N/A" if v is None else f"{v:.1f}%"


def pre_fmt_qty(v):
    return f"{int(v):,}"


def pre_send_gem(item, rank):
    f = item["fundamentals"]
    risk_list = list(item["risk_reasons"])
    if item.get("near_circuit"):
        risk_list.append("⚠️ Circuit ke paas")
    if item.get("penny"):
        risk_list.append("⚠️ Penny price")
    risk = ", ".join(risk_list) if risk_list else "Low Risk Penalty"

    de_txt = f"{f['de']:.2f}" if f["de"] is not None else "N/A"
    band_txt = f"{item['band']:.0f}%" if item.get("band") else "N/A"

    message = f"""
💎 PREOPEN GEM #{rank}

📌 {item['symbol']}  (₹{item['iep']:.2f})

━━━━━━━━━━━━━━━━━━
👥 BUYER STRENGTH
━━━━━━━━━━━━━━━━━━

📈 IEP Change : +{item['change']:.2f}%
🚧 Price Band : {band_txt}
⚖️ B/S Ratio  : {item['ratio']:.2f}x
🟢 Buy Qty    : {pre_fmt_qty(item['buy_qty'])}
🔴 Sell Qty   : {pre_fmt_qty(item['sell_qty'])}

⭐ Buyer Score : {item['buyer_score']}/100

━━━━━━━━━━━━━━━━━━
🏦 FUNDAMENTALS
━━━━━━━━━━━━━━━━━━

💰 Market Cap : {pre_fmt_cr(f['market_cap'])}

ROE           : {pre_fmt_pct(f['roe'])}
ROCE          : {pre_fmt_pct(f['roce'])}
D/E           : {de_txt}
Sales Growth  : {pre_fmt_pct(f['sales_growth'])}
Profit Growth : {pre_fmt_pct(f['profit_growth'])}
Pledge        : {pre_fmt_pct(f['pledge'])}

⭐ Quality     : {item['quality_score']}/7

━━━━━━━━━━━━━━━━━━
🛡️ RISK CHECK
━━━━━━━━━━━━━━━━━━

{risk}

🏆 FINAL SCORE : {item['final_score']}/100

🔒 BOSS FILTER : PASSED
👥 BUYER PRIORITY : HIGH

💻 Made by Prakash Kanki
"""
    pre_telegram_send(message)
    time.sleep(0.5)


def pre_send_summary(gems):
    lines = [f"📋 PREOPEN GEMS SUMMARY ({len(gems)} stocks)\n"]
    for i, g in enumerate(gems, 1):
        lines.append(f"{i}. {g['symbol']}  +{g['change']:.1f}%  "
                     f"{g['ratio']:.1f}x  Score {g['final_score']}")
    lines.append("\n⚠️ Sirf screening hai, advice nahi. Stoploss zaroor rakhein.")
    pre_telegram_send("\n".join(lines))


def pre_startup_message():
    pre_telegram_send(
        "🔥 PREOPEN GEMS OFFICIAL\n\n"
        "✅ Bot is online\n✅ Telegram connected\n✅ NSE scanner ready\n\n"
        "🔒 BOSS FILTER LOCKED\n👥 Buyer Priority ACTIVE\n"
        "🏦 Quality Ranking ACTIVE\n🛡️ Risk + Circuit + Penny Protection ACTIVE\n\n"
        "⏰ Scan: 09:00–09:08 AM pre_IST\n📨 Final list: 09:10 AM pre_IST\n"
        "📊 Output: 1–10 stocks\n\n💻 Made by Prakash Kanki"
    )


# ============================================================
# DAILY RUN
# ============================================================
def pre_wait_until(hour, minute):
    while True:
        now = datetime.now(pre_IST)
        if (now.hour, now.minute) >= (hour, minute):
            return
        time.sleep(5)


def pre_run_today():
    pre_wait_until(9, 0)
    pre_telegram_send("📡 PRE-OPEN SCANNING STARTED\n⏰ 09:00–09:08 AM pre_IST\n🔄 Every 30 seconds")

    latest = []
    got_any_data = False

    # 09:00 - 09:08 : scan, sirf latest candidates yaad rakho (spam nahi)
    while True:
        now = datetime.now(pre_IST)
        if (now.hour, now.minute) > (9, 8):
            break
        records = pre_get_nse_data()
        print(f"{now:%H:%M:%S} NSE Records: {len(records)}")
        if records:
            got_any_data = True
            candidates = pre_process_records(records)
            print("BOSS Matches:", len(candidates))
            if candidates:
                latest = candidates
        time.sleep(pre_SCAN_INTERVAL)

    if not got_any_data:
        pre_telegram_send("⚠️ NSE se pre-open data nahi mila (holiday ya NSE block ho sakta hai).")
        return

    # 09:10 : final data lo aur list bhejo
    pre_wait_until(FINAL_SEND_HOUR, FINAL_SEND_MIN)
    records = pre_get_nse_data()
    final_candidates = pre_process_records(records) if records else latest
    if not final_candidates:
        final_candidates = latest

    gems = pre_select_gems(final_candidates)

    if not gems:
        pre_telegram_send("📭 Aaj BOSS filter (2%+, 3x buyers, 50k qty) me koi stock match nahi hua.")
        return

    for i, g in enumerate(gems, 1):
        pre_send_gem(g, i)
    pre_send_summary(gems)


def pre_main():
    pre_startup_message()
    last_run_date = None

    while True:
        now = datetime.now(pre_IST)
        today = now.date()

        # Weekday (Mon-Fri) aur aaj abhi tak run nahi hua
        if now.weekday() < 5 and last_run_date != today and (now.hour, now.minute) <= (9, 8):
            last_run_date = today
            try:
                pre_run_today()
            except Exception as e:
                pre_telegram_send(f"⚠️ Bot error: {e}")
                print("Run error:", e)
            pre_fundamental_cache.clear()
            pre_band_cache.clear()

        time.sleep(30)




# ============================================================
# PART 2: INTRADAY SURGE (9:15-3:30)
# ============================================================

# ============================================================
# INTRADAY MID+SMALLCAP VOLUME/BUYER SURGE SCANNER
# Market hours: 09:15 - 15:30 intra_IST
# Universe: NIFTY MIDCAP 150 + NIFTY SMALLCAP 250
# Alerts: sudden volume surge + sudden buyer surge, max 10/day
# ============================================================

intra_TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
intra__raw_ids = os.getenv("TELEGRAM_CHAT_ID", "7418177111,1391074551")
intra_TELEGRAM_CHAT_IDS = [x.strip() for x in intra__raw_ids.replace(";", ",").split(",") if x.strip()]

intra_IST = ZoneInfo("Asia/Kolkata")

intra_NSE_HOME = "https://www.nseindia.com/"
intra_NSE_INDEX_URL = "https://www.nseindia.com/api/equity-stockIndices?index={idx}"
intra_NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={sym}"

intra_INDEXES = ["NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]

# ---------------- TIMING ----------------
intra_MARKET_START = (9, 15)
intra_WARMUP_UNTIL = (9, 30)      # pehle 15 min sirf data collect, alert nahi (volume abhi settle nahi hua)
intra_MARKET_END = (15, 30)
intra_POLL_INTERVAL_SEC = 180      # har 3 min data lo
intra_BASELINE_MIN_SAMPLES = 3     # kam se kam itne poll ke baad hi surge check

# ---------------- SURGE THRESHOLDS ----------------
intra_VOLUME_SURGE_RATIO = 3.0     # is interval ka volume >= 3x average interval volume
intra_PRICE_MIN_MOVE = 0.5         # kam se kam 0.5% up move (surge)
intra_BUYER_MIN_RAT
