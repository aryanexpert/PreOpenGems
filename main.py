import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# NSE PRE-OPEN BOSS SCANNER
# ============================================================

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open"
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage"

# ============================================================
# 🔒 BOSS FILTER — DO NOT CHANGE
# ============================================================

MIN_CHANGE = 2.0          # IEP change >= +2%
MIN_RATIO = 3.0           # Buy/Sell ratio >= 3x
MIN_BUY_QTY = 50_000      # Buy quantity >= 50,000
SCAN_INTERVAL = 30        # Scan every 30 seconds

# ============================================================
# TELEGRAM SETTINGS
# Railway Variables:
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("ERROR: Telegram variables are missing.")
    print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Railway.")
    raise SystemExit(1)

TELEGRAM_API = TELEGRAM_URL.format(BOT_TOKEN)

# ============================================================
# NSE HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/"
}

session = requests.Session()
session.headers.update(HEADERS)

# ============================================================
# IST TIME
# ============================================================

IST = ZoneInfo("Asia/Kolkata")


def now_ist():
    return datetime.now(IST)


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    try:
        response = requests.post(
            TELEGRAM_API,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=15
        )

        if response.status_code == 200:
            print("Telegram message sent.")
            return True

        print("Telegram ERROR:", response.status_code)
        print(response.text)

    except Exception as e:
        print("Telegram connection error:", e)

    return False


# ============================================================
# NSE DATA
# ============================================================

def get_nse_data():

    try:
        response = session.get(
            NSE_URL,
            params={"key": "ALL"},
            timeout=20
        )

        if response.status_code != 200:
            print("NSE ERROR:", response.status_code)
            return []

        data = response.json().get("data", [])

        return data

    except Exception as e:
        print("NSE connection error:", e)
        return []


# ============================================================
# BOSS SCANNER
# ============================================================

def scan_stocks(data):

    results = []

    for item in data:

        metadata = item.get("metadata", {})
        market = item.get("detail", {}).get("preOpenMarket", {})

        symbol = metadata.get("symbol")
        series = metadata.get("series")

        iep = metadata.get("iep", 0) or 0
        change = metadata.get("pChange", 0) or 0

        buy_qty = market.get("totalBuyQuantity", 0) or 0
        sell_qty = market.get("totalSellQuantity", 0) or 0

        # ====================================================
        # 🔒 BOSS FILTER
        # ====================================================

        if series != "EQ":
            continue

        if iep <= 0:
            continue

        if change < MIN_CHANGE:
            continue

        if buy_qty < MIN_BUY_QTY:
            continue

        # Sell quantity MUST be greater than zero
        if sell_qty <= 0:
            continue

        ratio = buy_qty / sell_qty

        if ratio < MIN_RATIO:
            continue

        results.append({
            "symbol": symbol,
            "iep": iep,
            "change": change,
            "buy": buy_qty,
            "sell": sell_qty,
            "ratio": ratio
        })

    # Strongest first
    results.sort(
        key=lambda x: (x["change"], x["ratio"], x["buy"]),
        reverse=True
    )

    return results


# ============================================================
# CREATE TELEGRAM MESSAGE
# ============================================================

def create_message(results):

    current = now_ist()

    message = (
        "🚨 NSE PRE-OPEN BOSS ALERT\n"
        f"📅 {current.strftime('%d-%b-%Y')} | "
        f"{current.strftime('%I:%M:%S %p')}\n\n"
    )

    message += "🔥 VERY STRONG BUYING\n\n"

    for i, stock in enumerate(results[:10], 1):

        message += (
            f"{i}️⃣ {stock['symbol']}\n"
            f"IEP       : ₹{stock['iep']:,.2f}\n"
            f"Change    : +{stock['change']:.2f}%\n"
            f"Buy Qty   : {stock['buy']:,}\n"
            f"Sell Qty  : {stock['sell']:,}\n"
            f"B/S Ratio : {stock['ratio']:.2f}x\n"
            f"Signal    : 🔥 VERY STRONG\n\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🔒 BOSS FILTER\n"
        "IEP Change : ≥ +2%\n"
        "B/S Ratio  : ≥ 3.0x\n"
        "Buy Qty    : ≥ 50,000\n"
        "Series     : EQ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ Pre-open data only.\n"
        "Not a buy recommendation."
    )

    return message


# ============================================================
# MAIN SCANNER
# ============================================================

def run_scanner():

    print("\n")
    print("==============================================")
    print(" NSE PRE-OPEN BOSS SCANNER")
    print("==============================================")
    print("🔒 BOSS FILTER LOCKED")
    print("----------------------------------------------")
    print("Change      >=", MIN_CHANGE, "%")
    print("B/S Ratio   >=", MIN_RATIO)
    print("Buy Qty     >=", f"{MIN_BUY_QTY:,}")
    print("Series      = EQ")
    print("Scan every  :", SCAN_INTERVAL, "seconds")
    print("==============================================")

    # Send startup message
    startup_message = (
        "🤖 NSE PRE-OPEN BOSS BOT\n\n"
        "✅ Scanner started successfully.\n"
        "⏰ Waiting for NSE pre-open...\n\n"
        "🔒 BOSS FILTER LOCKED\n"
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ"
    )

    send_telegram(startup_message)

    # ========================================================
    # WAIT UNTIL 9:00 AM IST
    # ========================================================

    while True:

        current = now_ist()
        current_time = current.strftime("%H:%M:%S")

        if current_time >= "09:00:00":
            break

        print("Waiting for 09:00 AM IST...", current_time)

        time.sleep(30)

    print("\n🔥 PRE-OPEN SCANNING STARTED")

    # ========================================================
    # PREVIOUS RESULTS
    # Used to prevent duplicate Telegram alerts
    # ========================================================

    alerted_stocks = set()

    # ========================================================
    # SCAN 9:00 TO 9:08
    # ========================================================

    while True:

        current = now_ist()
        current_time = current.strftime("%H:%M:%S")

        if current_time >= "09:08:00":
            break

        print("\nScanning NSE...", current_time)

        data = get_nse_data()

        print("NSE Records:", len(data))

        if not data:
            print("No NSE data received.")
            time.sleep(SCAN_INTERVAL)
            continue

        results = scan_stocks(data)

        print("BOSS stocks found:", len(results))

        # ====================================================
        # NEW STOCK ALERT
        # ====================================================

        new_results = []

        for stock in results:

            symbol = stock["symbol"]

            if symbol not in alerted_stocks:

                alerted_stocks.add(symbol)
                new_results.append(stock)

        # ====================================================
        # TELEGRAM ALERT
        # ====================================================

        if new_results:

            print("\n🚨 NEW BOSS STOCKS:")

            for stock in new_results:
                print(
                    stock["symbol"],
                    "|",
                    f"{stock['change']:.2f}%",
                    "| Buy:",
                    f"{stock['buy']:,}",
                    "| Sell:",
                    f"{stock['sell']:,}",
                    "| B/S:",
                    f"{stock['ratio']:.2f}x"
                )

            message = create_message(new_results)

            send_telegram(message)

        else:

            print("No NEW BOSS stock in this scan.")

        time.sleep(SCAN_INTERVAL)

    # ========================================================
    # FINISH
    # ========================================================

    print("\n==============================================")
    print(" NSE PRE-OPEN SESSION FINISHED")
    print(" Scanner stopped.")
    print("==============================================")

    send_telegram(
        "🏁 NSE PRE-OPEN SESSION FINISHED\n\n"
        f"⏰ {now_ist().strftime('%I:%M:%S %p')} IST\n"
        f"🔎 New BOSS stocks detected: {len(alerted_stocks)}\n\n"
        "The scanner has stopped for today."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_scanner()
