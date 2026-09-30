import os
import time
import math
import requests
import yfinance as yf
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

# ============================================================
# PREOPEN GEMS OFFICIAL
# 9:00-9:10 PRE-OPEN BUYING SCANNER
# Buyer Strength + Volume Potential + Tradability + Fundamentals
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

NSE_HOME = "https://www.nseindia.com/"
NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"

IST = ZoneInfo("Asia/Kolkata")

# Scan every 30 seconds during the order-entry period.
SCAN_START = dtime(9, 0, 0)
SCAN_END = dtime(9, 10, 0)
SCAN_INTERVAL = 30

# ============================================================
# USER'S CORE REQUIREMENT
# ============================================================

# Buy quantity must be at least 3x sell quantity.
MIN_BUY_SELL_RATIO = 3.0

# Avoid very tiny order books.
MIN_BUY_QTY = 50_000

# Do not force a fixed number if the quality is poor.
MIN_OUTPUT = 1
MAX_OUTPUT = 10

# ============================================================
# TRADABILITY / PENNY PROTECTION
# These are scoring/protection layers, not the old 7/7 filter.
# ============================================================

# Hard floor: very small companies are excluded.
HARD_MIN_MARKET_CAP_CR = 100

# Preferred market-cap level.
PREFERRED_MARKET_CAP_CR = 500

# Price protection. Price alone is NOT used as the only penny test.
HARD_MIN_PRICE = 20
PREFERRED_PRICE = 50

# Near-circuit protection. For normal 5%/10%/20% bands we avoid
# stocks whose indicative change is very close to the common band.
# The exact band is not always exposed by the public pre-open API,
# so this is deliberately a soft penalty rather than a hard rule.
NEAR_5_PCT = 4.6
NEAR_10_PCT = 9.2
NEAR_20_PCT = 18.5

# ============================================================
# FUNDAMENTAL SETTINGS — DELIBERATELY NOT STRICT
# ============================================================

# We give points for useful data; missing ROE/ROCE/pledge does not
# automatically reject a stock.

nse_session = requests.Session()

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
    "Connection": "keep-alive",
}

fundamental_cache = {}


def now_ist():
    return datetime.now(IST)


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in ("", "-", "N/A", "NA", "None"):
                return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def fmt_num(value):
    return f"{int(value):,}" if value is not None else "N/A"


def fmt_cr(value):
    return f"₹{value:,.0f} Cr" if value is not None else "N/A"


def fmt_pct(value):
    return f"{value:.1f}%" if value is not None else "N/A"


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            return True
        print("Telegram error:", r.status_code, r.text[:500])
    except Exception as e:
        print("Telegram exception:", e)
    return False


# ============================================================
# NSE DATA
# ============================================================

def get_nse_data():
    try:
        # Refresh cookies/header relationship.
        try:
            nse_session.get(NSE_HOME, headers=NSE_HEADERS, timeout=10)
        except Exception:
            pass

        r = nse_session.get(NSE_URL, headers=NSE_HEADERS, timeout=20)
        if r.status_code != 200:
            print("NSE HTTP:", r.status_code)
            return []

        data = r.json()
        if isinstance(data, dict):
            return data.get("data", [])
        return data if isinstance(data, list) else []
    except Exception as e:
        print("NSE error:", e)
        return []


# ============================================================
# EXTRACT PRE-OPEN DATA
# ============================================================

def extract_preopen(record):
    metadata = record.get("metadata", {}) or {}
    detail = record.get("detail", {}) or {}
    pre = detail.get("preOpenMarket", {}) or {}

    symbol = metadata.get("symbol")
    series = metadata.get("series")

    change = safe_float(metadata.get("pChange"), 0)
    iep = safe_float(metadata.get("iep"))

    buy_qty = safe_float(pre.get("totalBuyQuantity"), 0)
    sell_qty = safe_float(pre.get("totalSellQuantity"), 0)

    # Different NSE responses/versions may expose one of these names.
    # We use them as indicative-volume/tradable-quantity proxies only.
    volume = None
    for key in (
        "totalTradedVolume",
        "tradedQuantity",
        "totalTradedQuantity",
        "finalQuantity",
        "quantityTraded",
    ):
        if pre.get(key) is not None:
            volume = safe_float(pre.get(key))
            if volume is not None:
                break

    previous_close = safe_float(metadata.get("previousClose"))
    final_price = safe_float(metadata.get("finalPrice"))

    return {
        "symbol": symbol,
        "series": series,
        "change": change,
        "iep": iep,
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "ratio": (buy_qty / sell_qty) if sell_qty > 0 else 999.0,
        "volume": volume,
        "previous_close": previous_close,
        "final_price": final_price,
        "raw_metadata": metadata,
    }


# ============================================================
# FUNDAMENTALS
# ============================================================

def get_fundamentals(symbol):
    if symbol in fundamental_cache:
        return fundamental_cache[symbol]

    result = {
        "market_cap": None,
        "price": None,
        "roe": None,
        "roce": None,
        "de": None,
        "sales_growth": None,
        "profit_growth": None,
        "pledge": None,
    }

    try:
        ticker = yf.Ticker(symbol + ".NS")
        info = ticker.info or {}

        market_cap = safe_float(info.get("marketCap"))
        if market_cap is not None:
            result["market_cap"] = market_cap / 10_000_000

        price = safe_float(info.get("currentPrice"))
        if price is None:
            price = safe_float(info.get("regularMarketPrice"))
        result["price"] = price

        roe = safe_float(info.get("returnOnEquity"))
        if roe is not None:
            result["roe"] = roe * 100

        roce = safe_float(info.get("returnOnCapitalEmployed"))
        if roce is not None:
            result["roce"] = roce * 100 if roce < 1 else roce

        de = safe_float(info.get("debtToEquity"))
        if de is not None:
            # Yahoo sometimes returns 45.35 for 45.35%.
            if de > 20:
                de /= 100
            result["de"] = de

        sales = safe_float(info.get("revenueGrowth"))
        if sales is not None:
            result["sales_growth"] = sales * 100

        profit = safe_float(info.get("earningsGrowth"))
        if profit is not None:
            result["profit_growth"] = profit * 100

        pledge = safe_float(info.get("pledgeRatio"))
        if pledge is not None:
            result["pledge"] = pledge * 100

    except Exception as e:
        print(f"Fundamental error {symbol}: {e}")

    fundamental_cache[symbol] = result
    return result


# ============================================================
# B/S BUYER STRENGTH
# ============================================================

def buyer_score(item):
    ratio = item["ratio"]
    buy_qty = item["buy_qty"]
    change = item["change"]

    # Ratio = main buyer-strength signal.
    if ratio >= 25:
        ratio_score = 100
    else:
        ratio_score = 25 + ((max(ratio, 3) - 3) / 22) * 75

    # Quantity = second buyer-strength signal.
    if buy_qty <= 50_000:
        qty_score = 20
    else:
        qty_score = min(100, 20 + math.log10(buy_qty / 50_000) * 45)

    # Change is useful, but very high change can indicate a circuit risk.
    change_score = min(100, max(0, change * 4))

    return round(
        ratio_score * 0.50
        + qty_score * 0.30
        + change_score * 0.20,
        2,
    )


# ============================================================
# VOLUME POTENTIAL
# ============================================================

def volume_potential_score(item):
    """Volume potential" is estimated from the pre-open order book because
    actual continuous-market volume does not exist before 9:15.

    We therefore use:
      - buy quantity
      - sell quantity
      - total order quantity
      - indicative price change

    This is a probability/strength proxy, NOT guaranteed future volume.
    """
    buy_qty = item["buy_qty"]
    sell_qty = item["sell_qty"]
    total_orders = buy_qty + sell_qty
    ratio = item["ratio"]

    # Order-book depth.
    if total_orders >= 5_000_000:
        depth = 100
    elif total_orders >= 1_000_000:
        depth = 85
    elif total_orders >= 500_000:
        depth = 70
    elif total_orders >= 100_000:
        depth = 50
    else:
        depth = 25

    # Strong imbalance helps the chance of high attention/participation.
    imbalance = min(100, 20 + ratio * 4)

    # Change attracts attention, but is capped.
    momentum = min(100, max(0, item["change"] * 5))

    return round(
        depth * 0.50
        + imbalance * 0.30
        + momentum * 0.20,
        2,
    )


# ============================================================
# FUNDAMENTAL SCORE — LOOSE
# ============================================================

def fundamental_score(f):
    score = 0
    reasons = []

    mc = f["market_cap"]
    if mc is not None:
        if mc >= 1000:
            score += 25
            reasons.append("Strong Market Cap")
        elif mc >= 500:
            score += 20
            reasons.append("Good Market Cap")
        elif mc >= 250:
            score += 12
            reasons.append("Mid Market Cap")
        elif mc >= 100:
            score += 5

    sales = f["sales_growth"]
    if sales is not None:
        if sales >= 10:
            score += 20
            reasons.append("Sales Growth")
        elif sales > 0:
            score += 10

    profit = f["profit_growth"]
    if profit is not None:
        if profit >= 10:
            score += 20
            reasons.append("Profit Growth")
        elif profit > 0:
            score += 10

    roe = f["roe"]
    if roe is not None and roe >= 12:
        score += 15
        reasons.append("ROE")
    elif roe is not None and roe > 0:
        score += 5

    roce = f["roce"]
    if roce is not None and roce >= 15:
        score += 15
        reasons.append("ROCE")
    elif roce is not None and roce > 0:
        score += 5

    de = f["de"]
    if de is not None:
        if de <= 0.5:
            score += 15
            reasons.append("Low D/E")
        elif de <= 1.0:
            score += 10
        elif de <= 2.0:
            score += 4

    pledge = f["pledge"]
    if pledge is not None and pledge <= 5:
        score += 10
        reasons.append("Low Pledge")

    return min(100, score), reasons


# ============================================================
# RISK / PENALTIES
# ============================================================

def risk_penalty(item, f):
    penalty = 0
    reasons = []

    mc = f["market_cap"]
    price = f["price"]
    change = item["change"]

    # --------------------------------------------------------
    # Very small market cap = strong penalty / hard reject below 100 Cr.
    # --------------------------------------------------------
    if mc is not None:
        if mc < HARD_MIN_MARKET_CAP_CR:
            return 100, ["Very Small Cap"]
        elif mc < 250:
            penalty += 30
            reasons.append("Small Cap")
        elif mc < PREFERRED_MARKET_CAP_CR:
            penalty += 12
            reasons.append("Lower Market Cap")

    # If market cap is unavailable, do NOT hard reject — fundamentals
    # are often incomplete on Yahoo. Apply only a small uncertainty penalty.
    else:
        penalty += 8
        reasons.append("Market Cap N/A")

    # --------------------------------------------------------
    # Penny-price protection.
    # --------------------------------------------------------
    if price is not None:
        if price < HARD_MIN_PRICE:
            return 100, ["Very Low Price"]
        elif price < PREFERRED_PRICE:
            penalty += 15
            reasons.append("Low Price")

    # --------------------------------------------------------
    # Circuit-near penalty.
    # Public pre-open data does not always expose the exact price band.
    # Therefore use common 5/10/20% proximity as a soft penalty.
    # --------------------------------------------------------
    abs_change = abs(change)

    if abs_change >= NEAR_20_PCT:
        penalty += 40
        reasons.append("Near 20% Band")
    elif abs_change >= NEAR_10_PCT:
        penalty += 35
        reasons.append("Near 10% Band")
    elif abs_change >= NEAR_5_PCT:
        penalty += 30
        reasons.append("Near 5% Band")
    elif abs_change >= 8:
        penalty += 10

    # High D/E is penalized, not automatically rejected.
    de = f["de"]
    if de is not None:
        if de > 3:
            penalty += 15
            reasons.append("High D/E")
        elif de > 1:
            penalty += 6
            reasons.append("D/E > 1")

    return min(100, penalty), reasons


# ============================================================
# FINAL SCORE
# ============================================================

def score_candidate(item):
    f = get_fundamentals(item["symbol"])

    b = buyer_score(item)
    v = volume_potential_score(item)
    q, q_reasons = fundamental_score(f)
    penalty, risk_reasons = risk_penalty(item, f)

    # User's priority:
    # BUYERS = highest
    # VOLUME POTENTIAL = second
    # FUNDAMENTALS = supportive, not strict
    # RISK = penalty
    final = (
        b * 0.45
        + v * 0.25
        + q * 0.30
        - penalty * 0.30
    )

    item["fundamentals"] = f
    item["buyer_score"] = round(b, 2)
    item["volume_score"] = round(v, 2)
    item["fundamental_score"] = round(q, 2)
    item["risk_penalty"] = round(penalty, 2)
    item["quality_reasons"] = q_reasons
    item["risk_reasons"] = risk_reasons
    item["final_score"] = round(final, 2)

    return item


# ============================================================
# CANDIDATE FILTER
# ============================================================

def make_candidates(records):
    candidates = []

    for record in records:
        item = extract_preopen(record)

        if not item["symbol"]:
            continue

        # EQ only.
        if item["series"] != "EQ":
            continue

        # User's core buyer requirement.
        if item["ratio"] < MIN_BUY_SELL_RATIO:
            continue

        if item["buy_qty"] < MIN_BUY_QTY:
            continue

        if item["sell_qty"] <= 0:
            continue

        item = score_candidate(item)

        # Absolute hard protection only for obvious penny/microcap.
        f = item["fundamentals"]

        if f["market_cap"] is not None and f["market_cap"] < HARD_MIN_MARKET_CAP_CR:
            continue

        if f["price"] is not None and f["price"] < HARD_MIN_PRICE:
            continue

        candidates.append(item)

    candidates.sort(
        key=lambda x: (
            x["final_score"],
            x["buyer_score"],
            x["volume_score"],
            x["ratio"],
        ),
        reverse=True,
    )

    return candidates


# ============================================================
# TELEGRAM OUTPUT
# ============================================================

def send_gem(item, rank):
    f = item["fundamentals"]

    risk = ", ".join(item["risk_reasons"]) if item["risk_reasons"] else "No major risk flag"
    quality = ", ".join(item["quality_reasons"]) if item["quality_reasons"] else "Limited fundamental data"

    message = f"""
💎 PREOPEN GEM #{rank}

📌 {item['symbol']}

━━━━━━━━━━━━━━━━━━
👥 BUYER STRENGTH
━━━━━━━━━━━━━━━━━━

📈 IEP Change : +{item['change']:.2f}%
⚖️ B/S Ratio  : {item['ratio']:.2f}x
🟢 Buy Qty    : {fmt_num(item['buy_qty'])}
🔴 Sell Qty   : {fmt_num(item['sell_qty'])}

⭐ Buyer Score : {item['buyer_score']}/100
📊 Volume Potential : {item['volume_score']}/100

━━━━━━━━━━━━━━━━━━
🏦 FUNDAMENTALS
━━━━━━━━━━━━━━━━━━

💰 Market Cap : {fmt_cr(f['market_cap'])}
💵 Price      : {fmt_pct(f['price']) if False else (f"₹{f['price']:.2f}" if f['price'] is not None else 'N/A')}
ROE           : {fmt_pct(f['roe'])}
ROCE          : {fmt_pct(f['roce'])}
D/E           : {f"{f['de']:.2f}" if f['de'] is not None else 'N/A'}
Sales Growth  : {fmt_pct(f['sales_growth'])}
Profit Growth : {fmt_pct(f['profit_growth'])}
Pledge        : {fmt_pct(f['pledge'])}

⭐ Fundamental Score : {item['fundamental_score']}/100

━━━━━━━━━━━━━━━━━━
🛡️ RISK CHECK
━━━━━━━━━━━━━━━━━━

{risk}

🏆 FINAL SCORE : {item['final_score']}/100

✅ BUY/SELL ≥ 3x
✅ Penny-stock protection
✅ Circuit-near penalty
✅ Fundamentals NOT overly strict

💻 Made by Prakash Kanki
"""

    telegram_send(message)


def send_final_report(candidates, records_count):
    selected = candidates[:MAX_OUTPUT]

    message = f"""
🏁 PREOPEN GEMS OFFICIAL

📡 9:00–9:10 PRE-OPEN FINAL SCAN

⏰ {now_ist().strftime('%H:%M:%S')} AM IST
📊 NSE Records : {records_count}
🔎 Candidates  : {len(candidates)}
💎 Selected    : {len(selected)}

━━━━━━━━━━━━━━━━━━
🎯 SELECTION LOGIC
━━━━━━━━━━━━━━━━━━

👥 Buyers / Sellers ≥ 3x
🟢 Buy Qty ≥ 50,000
📊 Volume potential considered
🛡️ Penny stocks filtered
⚠️ Circuit-near stocks penalized
🏦 Fundamentals supportive, not strict

━━━━━━━━━━━━━━━━━━
🏆 TOP STOCKS
━━━━━━━━━━━━━━━━━━
"""

    if not selected:
        message += "\n⚠️ No acceptable stock found today.\n"
    else:
        for i, x in enumerate(selected, 1):
            message += (
                f"\n{i}. {x['symbol']}"
                f" | B/S {x['ratio']:.2f}x"
                f" | Buy {fmt_num(x['buy_qty'])}"
                f" | Vol {x['volume_score']:.0f}"
                f" | Fund {x['fundamental_score']:.0f}"
                f" | Score {x['final_score']:.1f}"
            )

    message += "\n\n💻 Made by Prakash Kanki"
    telegram_send(message)


# ============================================================
# STARTUP
# ============================================================

def send_startup():
    telegram_send("""
🔥 PREOPEN GEMS OFFICIAL

📡 PRE-OPEN BUYING SCANNER

✅ Bot is online
✅ Telegram connected
✅ NSE scanner ready

👥 Buyers / Sellers ≥ 3x
📊 Volume Potential ACTIVE
🛡️ Penny Protection ACTIVE
⚠️ Circuit Protection ACTIVE
🏦 Loose Fundamental Filter ACTIVE

⏰ Scan: 09:00–09:10 AM IST
🔄 Every 30 seconds

🎯 Final list: 1–10 stocks

💻 Made by Prakash Kanki
""")


# ============================================================
# MAIN
# ============================================================

def main():
    send_startup()

    # Wait for 09:00.
    while now_ist().time() < SCAN_START:
        time.sleep(5)

    telegram_send("""
📡 PRE-OPEN SCANNING STARTED

⏰ 09:00–09:10 AM IST
🔄 Every 30 seconds

👥 BUYER PRIORITY ACTIVE
📊 VOLUME POTENTIAL ACTIVE
🛡️ PENNY PROTECTION ACTIVE
⚠️ CIRCUIT PROTECTION ACTIVE
🏦 FUNDAMENTALS ACTIVE
""")

    latest_candidates = []
    latest_records = 0

    while now_ist().time() < SCAN_END:
        records = get_nse_data()
        latest_records = len(records)

        candidates = make_candidates(records)
        latest_candidates = candidates

        print(
            now_ist().strftime("%H:%M:%S"),
            "NSE:", len(records),
            "Candidates:", len(candidates)
        )

        time.sleep(SCAN_INTERVAL)

    # Final collection at approximately 09:10.
    records = get_nse_data()
    latest_records = len(records)
    latest_candidates = make_candidates(records)

    # Only ONE final Telegram list at 09:10.
    send_final_report(latest_candidates, latest_records)

    print("FINAL PREOPEN SCAN FINISHED")


if __name__ == "__main__":
    main()
