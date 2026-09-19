import os
import time
import requests
import yfinance as yf
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

# ============================================================
# PREOPEN GEMS OFFICIAL
# BOSS FILTER + QUALITY SCORE
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

IST = ZoneInfo("Asia/Kolkata")

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"

# ============================================================
# 🔒 BOSS FILTER — LOCKED
# ============================================================

MIN_IEP_CHANGE = 2.0
MIN_BS_RATIO = 3.0
MIN_BUY_QTY = 50000

# ============================================================
# 💎 QUALITY SCORE — SAME CONDITIONS
# ============================================================

MIN_MARKET_CAP = 500_00_00_000       # ₹500 Cr
MIN_GEM_SCORE = 4
MIN_STRONG_SCORE = 5

# Cache fundamentals so we don't repeatedly hit Yahoo
fundamental_cache = {}

# Prevent duplicate Telegram alerts
alerted_stocks = set()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        r = requests.post(url, data=payload, timeout=15)

        if r.status_code == 200:
            return True

        print("Telegram error:", r.text)
        return False

    except Exception as e:
        print("Telegram exception:", e)
        return False


# ============================================================
# NSE SESSION
# ============================================================

def get_nse_data():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.nseindia.com/"
    }

    try:

        session = requests.Session()

        session.get(
            "https://www.nseindia.com/",
            headers=headers,
            timeout=10
        )

        r = session.get(
            NSE_URL,
            headers=headers,
            timeout=15
        )

        if r.status_code != 200:
            print("NSE HTTP:", r.status_code)
            return []

        data = r.json()

        return data.get("data", [])

    except Exception as e:

        print("NSE error:", e)
        return []


# ============================================================
# BOSS FILTER
# ============================================================

def scan_boss_stocks():

    data = get_nse_data()

    boss = []

    for item in data:

        try:

            metadata = item.get("metadata", {})
            detail = item.get("detail", {})

            symbol = metadata.get("symbol", "")
            series = metadata.get("series", "")

            iep = float(metadata.get("iep") or 0)
            pchange = float(metadata.get("pChange") or 0)

            preopen = detail.get("preOpenMarket", {})

            buy_qty = float(
                preopen.get("totalBuyQuantity") or 0
            )

            sell_qty = float(
                preopen.get("totalSellQuantity") or 0
            )

            # ------------------------------------------------
            # 🔒 EXACT BOSS CONDITIONS
            # ------------------------------------------------

            if series != "EQ":
                continue

            if pchange < MIN_IEP_CHANGE:
                continue

            if sell_qty <= 0:
                continue

            bs_ratio = buy_qty / sell_qty

            if bs_ratio < MIN_BS_RATIO:
                continue

            if buy_qty < MIN_BUY_QTY:
                continue

            boss.append({
                "symbol": symbol,
                "series": series,
                "iep": iep,
                "pchange": pchange,
                "buy_qty": buy_qty,
                "sell_qty": sell_qty,
                "bs_ratio": bs_ratio
            })

        except Exception:
            continue

    return boss


# ============================================================
# FUNDAMENTALS
# ============================================================

def get_fundamentals(symbol):

    if symbol in fundamental_cache:
        return fundamental_cache[symbol]

    result = {
        "market_cap": None,
        "roe": None,
        "roce": None,
        "de": None,
        "sales_growth": None,
        "profit_growth": None,
        "pledge": None
    }

    try:

        ticker = yf.Ticker(symbol + ".NS")
        info = ticker.info

        # Market Cap
        result["market_cap"] = info.get("marketCap")

        # ROE
        result["roe"] = info.get("returnOnEquity")

        # ROCE
        result["roce"] = info.get("returnOnCapitalEmployed")

        # Debt / Equity
        result["de"] = info.get("debtToEquity")

        # Growth
        result["sales_growth"] = info.get(
            "revenueGrowth"
        )

        result["profit_growth"] = info.get(
            "earningsGrowth"
        )

        # Pledge
        result["pledge"] = info.get(
            "pledgeRatio"
        )

    except Exception as e:

        print(f"Fundamental error {symbol}:", e)

    fundamental_cache[symbol] = result

    return result


# ============================================================
# QUALITY SCORE
# ============================================================

def calculate_quality_score(f):

    score = 0

    market_cap = f.get("market_cap")
    roe = f.get("roe")
    roce = f.get("roce")
    de = f.get("de")
    sales_growth = f.get("sales_growth")
    profit_growth = f.get("profit_growth")
    pledge = f.get("pledge")

    # --------------------------------------------------------
    # Market Cap
    # --------------------------------------------------------

    if market_cap is not None:

        if market_cap >= MIN_MARKET_CAP:
            score += 1

        else:
            # Below ₹500 Cr = reject
            return 0

    else:

        # Market cap unavailable = reject
        return 0

    # --------------------------------------------------------
    # ROE
    # --------------------------------------------------------

    if roe is not None:

        if roe >= 0.12:
            score += 1

    # --------------------------------------------------------
    # ROCE
    # --------------------------------------------------------

    if roce is not None:

        if roce >= 0.15:
            score += 1

    # --------------------------------------------------------
    # Debt / Equity
    # --------------------------------------------------------

    if de is not None:

        if de <= 0.50:
            score += 1

    # --------------------------------------------------------
    # Sales Growth
    # --------------------------------------------------------

    if sales_growth is not None:

        if sales_growth >= 0.10:
            score += 1

    # --------------------------------------------------------
    # Profit Growth
    # --------------------------------------------------------

    if profit_growth is not None:

        if profit_growth >= 0.10:
            score += 1

    # --------------------------------------------------------
    # Pledge
    # --------------------------------------------------------

    if pledge is not None:

        if pledge <= 0.05:
            score += 1

    return score


# ============================================================
# FORMAT FUNDAMENTAL VALUES
# ============================================================

def fmt_percent(value):

    if value is None:
        return "N/A"

    try:
        return f"{value * 100:.1f}%"
    except:
        return "N/A"


def fmt_market_cap(value):

    if value is None:
        return "N/A"

    try:

        crore = value / 1e7

        return f"₹{crore:,.0f} Cr"

    except:
        return "N/A"


def fmt_number(value):

    try:
        return f"{int(value):,}"
    except:
        return "N/A"


# ============================================================
# CREATE STOCK MESSAGE
# ============================================================

def create_stock_message(stock, fundamentals, score):

    symbol = stock["symbol"]

    market_cap = fundamentals.get("market_cap")
    roe = fundamentals.get("roe")
    roce = fundamentals.get("roce")
    de = fundamentals.get("de")
    sales_growth = fundamentals.get("sales_growth")
    profit_growth = fundamentals.get("profit_growth")
    pledge = fundamentals.get("pledge")

    if score >= MIN_STRONG_SCORE:
        title = "🔥 STRONG FUNDAMENTAL + BOSS GEM"
    else:
        title = "💎 FUNDAMENTAL + BOSS GEM"

    message = f"""
{title}

📌 STOCK: {symbol}

📅 {datetime.now(IST).strftime("%d-%b-%Y")}
⏰ {datetime.now(IST).strftime("%H:%M:%S")} AM IST

━━━━━━━━━━━━━━━━━━
📊 PRE-OPEN DATA
━━━━━━━━━━━━━━━━━━

📈 IEP Change : +{stock["pchange"]:.2f}%
💰 IEP        : ₹{stock["iep"]:.2f}

🟢 Buy Qty    : {fmt_number(stock["buy_qty"])}
🔴 Sell Qty   : {fmt_number(stock["sell_qty"])}

⚖️ B/S Ratio  : {stock["bs_ratio"]:.2f}x

━━━━━━━━━━━━━━━━━━
💎 FUNDAMENTALS
━━━━━━━━━━━━━━━━━━

💰 Market Cap : {fmt_market_cap(market_cap)}
ROE           : {fmt_percent(roe)}
ROCE          : {fmt_percent(roce)}
D/E           : {de if de is not None else "N/A"}
Sales Gr.     : {fmt_percent(sales_growth)}
Profit Gr.    : {fmt_percent(profit_growth)}
Pledge        : {fmt_percent(pledge)}

━━━━━━━━━━━━━━━━━━
🔒 BOSS FILTER
━━━━━━━━━━━━━━━━━━

IEP Change ≥ +2%
B/S Ratio ≥ 3.0x
Buy Qty ≥ 50,000
Sell Qty > 0
Series = EQ

━━━━━━━━━━━━━━━━━━
💎 QUALITY SCORE
━━━━━━━━━━━━━━━━━━

Market Cap ≥ ₹500 Cr
ROE ≥ 12% = +1
ROCE ≥ 15% = +1
D/E ≤ 0.50 = +1
Sales Growth ≥ 10% = +1
Profit Growth ≥ 10% = +1
Pledge ≤ 5% = +1

💎 GEM = 4/7+
🔥 STRONG GEM = 5/7+

⭐ QUALITY SCORE: {score}/7

━━━━━━━━━━━━━━━━━━

⚠️ Pre-open data is indicative.
Not a buy/sell recommendation.

💻 Made by Prakash Kanki
"""

    return message.strip()


# ============================================================
# PROCESS BOSS STOCKS
# ============================================================

def process_stocks():

    boss_stocks = scan_boss_stocks()

    print(
        f"{datetime.now(IST).strftime('%H:%M:%S')} "
        f"BOSS stocks found: {len(boss_stocks)}"
    )

    gem_count = 0

    for stock in boss_stocks:

        symbol = stock["symbol"]

        # Don't repeatedly process same stock
        if symbol in alerted_stocks:
            continue

        print(
            f"Checking {symbol} | "
            f"IEP +{stock['pchange']:.2f}% | "
            f"B/S {stock['bs_ratio']:.2f}x"
        )

        fundamentals = get_fundamentals(symbol)

        score = calculate_quality_score(
            fundamentals
        )

        print(
            f"{symbol} Quality Score: {score}/7"
        )

        # GEM
        if score >= MIN_GEM_SCORE:

            message = create_stock_message(
                stock,
                fundamentals,
                score
            )

            if send_telegram(message):

                alerted_stocks.add(symbol)
                gem_count += 1

                print(
                    f"💎 GEM SENT: {symbol} "
                    f"{score}/7"
                )

    return gem_count


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

def send_start_message():

    message = """
🤖 PREOPEN GEMS OFFICIAL

✅ Bot is online!
✅ Telegram connected!
✅ NSE scanner ready!
✅ BOSS filter loaded!
✅ Quality Score loaded!

⏰ Scanner:
09:00–09:08 AM IST
🔄 Every 30 seconds

💻 Made by Prakash Kanki
"""

    send_telegram(message)


# ============================================================
# MAIN SCANNER
# ============================================================

def run_scanner():

    global alerted_stocks

    now = datetime.now(IST)

    start_time = dt_time(9, 0, 0)
    end_time = dt_time(9, 8, 0)

    # --------------------------------------------------------
    # WAIT FOR 9:00 AM
    # --------------------------------------------------------

    while now.time() < start_time:

        remaining = (
            datetime.combine(
                now.date(),
                start_time
            ).replace(
                tzinfo=IST
            ) - now
        )

        print(
            f"Waiting for 09:00 AM IST... "
            f"{remaining}"
        )

        time.sleep(20)

        now = datetime.now(IST)

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    print(
        "\n🔥 PRE-OPEN SCANNING STARTED"
    )

    send_telegram(
        """
🔥 PREOPEN GEMS OFFICIAL

📡 PRE-OPEN SCANNING STARTED

⏰ 09:00–09:08 AM IST
🔄 Scanning every 30 seconds

🔒 BOSS filter ACTIVE
💎 Quality Score ACTIVE
"""
    )

    total_gems = 0

    # --------------------------------------------------------
    # SCAN UNTIL 9:08
    # --------------------------------------------------------

    while True:

        now = datetime.now(IST)

        if now.time() >= end_time:
            break

        try:

            gems = process_stocks()

            total_gems += gems

        except Exception as e:

            print(
                "Scanner error:",
                e
            )

        # Every 30 seconds
        time.sleep(30)

    # --------------------------------------------------------
    # FINISH
    # --------------------------------------------------------

    finish_time = datetime.now(IST)

    finish_message = f"""
🏁 PREOPEN GEMS OFFICIAL

NSE Pre-Open scan finished.

⏰ {finish_time.strftime("%H:%M:%S")} AM IST

💎 GEM stocks detected: {len(alerted_stocks)}

Scanner stopped for today.

💻 Made by Prakash Kanki
"""

    send_telegram(finish_message)

    print(
        "🏁 Scanner finished."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print(
        "\n================================"
    )

    print(
        "🤖 PREOPEN GEMS OFFICIAL"
    )

    print(
        "================================"
    )

    send_start_message()

    run_scanner()
