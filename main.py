import os
import time
import requests
import yfinance as yf
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

# ============================================================
# PREOPEN GEMS OFFICIAL
# DIAGNOSTIC VERSION
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
# 💎 QUALITY SCORE
# ============================================================

MIN_MARKET_CAP = 500_00_00_000
MIN_GEM_SCORE = 4
MIN_STRONG_SCORE = 5

fundamental_cache = {}
alerted_stocks = set()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return False

    try:

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=15
        )

        if response.status_code == 200:
            return True

        print("Telegram error:", response.text)
        return False

    except Exception as e:

        print("Telegram error:", e)
        return False


# ============================================================
# NSE DATA
# ============================================================

def get_nse_data():

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36",

        "Accept":
            "application/json,text/plain,*/*",

        "Referer":
            "https://www.nseindia.com/"
    }

    try:

        session = requests.Session()

        session.get(
            "https://www.nseindia.com/",
            headers=headers,
            timeout=10
        )

        response = session.get(
            NSE_URL,
            headers=headers,
            timeout=15
        )

        print(
            "NSE HTTP:",
            response.status_code
        )

        if response.status_code != 200:
            return []

        return response.json().get(
            "data",
            []
        )

    except Exception as e:

        print(
            "NSE ERROR:",
            e
        )

        return []


# ============================================================
# BOSS FILTER
# ============================================================

def scan_boss_stocks(data):

    boss = []

    for item in data:

        try:

            metadata = item.get(
                "metadata",
                {}
            )

            detail = item.get(
                "detail",
                {}
            )

            symbol = metadata.get(
                "symbol",
                ""
            )

            series = metadata.get(
                "series",
                ""
            )

            pchange = float(
                metadata.get(
                    "pChange"
                ) or 0
            )

            iep = float(
                metadata.get(
                    "iep"
                ) or 0
            )

            preopen = detail.get(
                "preOpenMarket",
                {}
            )

            buy_qty = float(
                preopen.get(
                    "totalBuyQuantity"
                ) or 0
            )

            sell_qty = float(
                preopen.get(
                    "totalSellQuantity"
                ) or 0
            )

            # ------------------------------------------------
            # 🔒 BOSS CONDITIONS — DO NOT CHANGE
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

        ticker = yf.Ticker(
            symbol + ".NS"
        )

        info = ticker.info

        result["market_cap"] = info.get(
            "marketCap"
        )

        result["roe"] = info.get(
            "returnOnEquity"
        )

        result["roce"] = info.get(
            "returnOnCapitalEmployed"
        )

        result["de"] = info.get(
            "debtToEquity"
        )

        result["sales_growth"] = info.get(
            "revenueGrowth"
        )

        result["profit_growth"] = info.get(
            "earningsGrowth"
        )

        result["pledge"] = info.get(
            "pledgeRatio"
        )

    except Exception as e:

        print(
            f"Yahoo error {symbol}: {e}"
        )

    fundamental_cache[symbol] = result

    return result


# ============================================================
# QUALITY SCORE + REASONS
# ============================================================

def calculate_quality(f):

    score = 0
    passed = []
    missing = []
    failed = []

    market_cap = f["market_cap"]
    roe = f["roe"]
    roce = f["roce"]
    de = f["de"]
    sales_growth = f["sales_growth"]
    profit_growth = f["profit_growth"]
    pledge = f["pledge"]

    # --------------------------------------------------------
    # MARKET CAP
    # --------------------------------------------------------

    if market_cap is None:

        missing.append("Market Cap")

        return {
            "score": 0,
            "passed": passed,
            "missing": missing,
            "failed": failed,
            "market_cap_ok": False
        }

    if market_cap >= MIN_MARKET_CAP:

        score += 1
        passed.append("Market Cap")

        market_cap_ok = True

    else:

        failed.append("Market Cap < ₹500 Cr")

        market_cap_ok = False

    # --------------------------------------------------------
    # ROE
    # --------------------------------------------------------

    if roe is None:

        missing.append("ROE")

    elif roe >= 0.12:

        score += 1
        passed.append("ROE")

    else:

        failed.append("ROE < 12%")

    # --------------------------------------------------------
    # ROCE
    # --------------------------------------------------------

    if roce is None:

        missing.append("ROCE")

    elif roce >= 0.15:

        score += 1
        passed.append("ROCE")

    else:

        failed.append("ROCE < 15%")

    # --------------------------------------------------------
    # D/E
    # --------------------------------------------------------

    if de is None:

        missing.append("D/E")

    elif de <= 0.50:

        score += 1
        passed.append("D/E")

    else:

        failed.append("D/E > 0.50")

    # --------------------------------------------------------
    # SALES GROWTH
    # --------------------------------------------------------

    if sales_growth is None:

        missing.append("Sales Growth")

    elif sales_growth >= 0.10:

        score += 1
        passed.append("Sales Growth")

    else:

        failed.append("Sales Growth < 10%")

    # --------------------------------------------------------
    # PROFIT GROWTH
    # --------------------------------------------------------

    if profit_growth is None:

        missing.append("Profit Growth")

    elif profit_growth >= 0.10:

        score += 1
        passed.append("Profit Growth")

    else:

        failed.append("Profit Growth < 10%")

    # --------------------------------------------------------
    # PLEDGE
    # --------------------------------------------------------

    if pledge is None:

        missing.append("Pledge")

    elif pledge <= 0.05:

        score += 1
        passed.append("Pledge")

    else:

        failed.append("Pledge > 5%")

    return {
        "score": score,
        "passed": passed,
        "missing": missing,
        "failed": failed,
        "market_cap_ok": market_cap_ok
    }


# ============================================================
# FORMAT
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

        return (
            f"₹{value / 1e7:,.0f} Cr"
        )

    except:

        return "N/A"


# ============================================================
# DIAGNOSTIC STOCK REPORT
# ============================================================

def create_diagnostic_message(
    stock,
    fundamentals,
    quality
):

    symbol = stock["symbol"]

    score = quality["score"]

    if score >= 5:

        status = "🔥 STRONG GEM"

    elif score >= 4:

        status = "💎 GEM"

    else:

        status = "❌ NOT GEM"

    missing_text = (
        ", ".join(quality["missing"])
        if quality["missing"]
        else "None"
    )

    failed_text = (
        ", ".join(quality["failed"])
        if quality["failed"]
        else "None"
    )

    return f"""
🔍 DIAGNOSTIC STOCK

📌 {symbol}

📈 IEP Change : +{stock["pchange"]:.2f}%
⚖️ B/S Ratio  : {stock["bs_ratio"]:.2f}x
🟢 Buy Qty    : {int(stock["buy_qty"]):,}
🔴 Sell Qty   : {int(stock["sell_qty"]):,}

━━━━━━━━━━━━━━━━━━

💰 Market Cap : {fmt_market_cap(fundamentals["market_cap"])}
ROE           : {fmt_percent(fundamentals["roe"])}
ROCE          : {fmt_percent(fundamentals["roce"])}
D/E           : {fundamentals["de"] if fundamentals["de"] is not None else "N/A"}
Sales Growth  : {fmt_percent(fundamentals["sales_growth"])}
Profit Growth : {fmt_percent(fundamentals["profit_growth"])}
Pledge        : {fmt_percent(fundamentals["pledge"])}

━━━━━━━━━━━━━━━━━━

⭐ QUALITY SCORE: {score}/7

{status}

✅ Passed:
{", ".join(quality["passed"]) if quality["passed"] else "None"}

⚠️ Missing:
{missing_text}

❌ Failed:
{failed_text}
""".strip()


# ============================================================
# PROCESS ONE SCAN
# ============================================================

def diagnostic_scan():

    data = get_nse_data()

    print(
        f"📊 NSE Records: {len(data)}"
    )

    boss = scan_boss_stocks(data)

    print(
        f"🔒 BOSS Matches: {len(boss)}"
    )

    if not boss:

        return {
            "nse": len(data),
            "boss": 0,
            "market_cap": 0,
            "gems": 0,
            "strong": 0
        }

    market_cap_pass = 0
    gem_count = 0
    strong_count = 0

    # --------------------------------------------------------
    # SEND DIAGNOSTIC SUMMARY
    # --------------------------------------------------------

    send_telegram(
        f"""
🔍 PREOPEN GEMS DIAGNOSTIC

⏰ {datetime.now(IST).strftime("%H:%M:%S")} AM IST

📊 NSE Records: {len(data)}
🔒 BOSS Matches: {len(boss)}

💎 Checking fundamentals...
""".strip()
    )

    # --------------------------------------------------------
    # CHECK STOCKS
    # --------------------------------------------------------

    for stock in boss:

        symbol = stock["symbol"]

        print(
            f"Checking fundamentals: {symbol}"
        )

        fundamentals = get_fundamentals(
            symbol
        )

        quality = calculate_quality(
            fundamentals
        )

        score = quality["score"]

        if quality["market_cap_ok"]:
            market_cap_pass += 1

        if score >= MIN_GEM_SCORE:
            gem_count += 1

        if score >= MIN_STRONG_SCORE:
            strong_count += 1

        # ----------------------------------------------------
        # Send every BOSS stock diagnostic
        # ----------------------------------------------------

        message = create_diagnostic_message(
            stock,
            fundamentals,
            quality
        )

        send_telegram(message)

    return {
        "nse": len(data),
        "boss": len(boss),
        "market_cap": market_cap_pass,
        "gems": gem_count,
        "strong": strong_count
    }


# ============================================================
# MAIN
# ============================================================

def run_scanner():

    start_time = dt_time(9, 0, 0)
    end_time = dt_time(9, 8, 0)

    now = datetime.now(IST)

    # --------------------------------------------------------
    # WAIT FOR 9 AM
    # --------------------------------------------------------

    while now.time() < start_time:

        print(
            "Waiting for 09:00 AM IST..."
        )

        time.sleep(20)

        now = datetime.now(IST)

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    send_telegram(
        """
🔥 PREOPEN GEMS OFFICIAL

📡 PRE-OPEN DIAGNOSTIC SCANNING STARTED

⏰ 09:00–09:08 AM IST
🔄 Every 30 seconds

🔒 BOSS FILTER LOCKED
🧪 DIAGNOSTIC MODE ACTIVE
""".strip()
    )

    total_gems = set()

    # --------------------------------------------------------
    # 30 SECOND SCAN
    # --------------------------------------------------------

    while True:

        now = datetime.now(IST)

        if now.time() >= end_time:
            break

        try:

            result = diagnostic_scan()

            print()
            print(
                "📊 CURRENT SUMMARY"
            )

            print(
                f"NSE: {result['nse']}"
            )

            print(
                f"BOSS: {result['boss']}"
            )

            print(
                f"Market Cap: {result['market_cap']}"
            )

            print(
                f"GEM: {result['gems']}"
            )

            print(
                f"STRONG: {result['strong']}"
            )

        except Exception as e:

            print(
                "Scanner error:",
                e
            )

        time.sleep(30)

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    finish = datetime.now(IST)

    send_telegram(
        f"""
🏁 PREOPEN GEMS OFFICIAL

🧪 DIAGNOSTIC SCAN FINISHED

⏰ {finish.strftime("%H:%M:%S")} AM IST

The diagnostic report has been
sent above for all BOSS matches.

🔒 BOSS FILTER WAS NOT CHANGED.

💻 Made by Prakash Kanki
""".strip()
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print(
        "===================================="
    )

    print(
        "🤖 PREOPEN GEMS OFFICIAL"
    )

    print(
        "🧪 DIAGNOSTIC MODE"
    )

    print(
        "===================================="
    )

    run_scanner()
