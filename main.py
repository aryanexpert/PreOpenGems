import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# 💎 PREOPEN GEMS OFFICIAL
# NSE PRE-OPEN BOSS SCANNER
# ============================================================

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SCAN_INTERVAL = 30

# ============================================================
# 🔒 BOSS FILTER — LOCKED
# ============================================================

MIN_CHANGE = 2.0
MIN_RATIO = 3.0
MIN_BUY_QTY = 50_000

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
TELEGRAM_GET_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

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

IST = ZoneInfo("Asia/Kolkata")

nse_session = requests.Session()
nse_session.headers.update(HEADERS)

alerted_stocks = set()


# ============================================================
# TIME
# ============================================================

def now_ist():
    return datetime.now(IST)


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def send_telegram(message, chat_id=None):

    try:

        target_chat = chat_id if chat_id else CHAT_ID

        response = requests.post(
            TELEGRAM_SEND_URL,
            data={
                "chat_id": target_chat,
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
# /START MESSAGE
# ============================================================

def start_message():

    return (
        "👋 Hello!\n\n"
        "💎 Welcome to PreOpen Gems Official\n"
        "NSE Pre-Open Market Intelligence Bot\n\n"

        "📊 What this bot does:\n"
        "PreOpen Gems Official scans NSE pre-open market "
        "data and identifies stocks showing very strong "
        "buying interest before the normal market opens.\n\n"

        "⏰ Active Time\n"
        "09:00 AM – 09:08 AM IST\n\n"

        "🔄 Scan Frequency\n"
        "Every 30 seconds\n\n"

        "🔒 BOSS FILTER\n"
        "• IEP Change ≥ +2%\n"
        "• Buy/Sell Ratio ≥ 3.0x\n"
        "• Buy Quantity ≥ 50,000\n"
        "• Series = EQ\n\n"

        "🚨 When a new stock matches the BOSS filter, "
        "the bot sends an automatic alert.\n\n"

        "⚠️ Important\n"
        "Pre-open data is indicative and market conditions "
        "can change after the market opens.\n"
        "This bot is for information and educational purposes "
        "only and is not a buy/sell recommendation.\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "💎 PREOPEN GEMS OFFICIAL\n"
        "NSE Pre-Open Intelligence\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "💻 Made by Prakash Kanki"
    )


# ============================================================
# /TEST MESSAGE
# ============================================================

def test_message():

    return (
        "🧪 PREOPEN GEMS OFFICIAL — TEST\n\n"

        "👋 Hello Prakash!\n\n"

        "✅ Telegram connection is working!\n"
        "✅ Bot is online!\n"
        "✅ BOSS filter is loaded!\n\n"

        "🔒 BOSS FILTER\n"
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3.0x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ\n\n"

        "⏰ Production Scanner\n"
        "09:00 AM – 09:08 AM IST\n"
        "Every 30 seconds\n\n"

        "💎 PreOpen Gems Official\n"
        "💻 Made by Prakash Kanki"
    )


# ============================================================
# NSE DATA
# ============================================================

def get_nse_data():

    try:

        response = nse_session.get(
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
# 🔒 BOSS SCANNER
# ============================================================

def scan_stocks(data):

    results = []

    for item in data:

        metadata = item.get("metadata", {})
        market = item.get(
            "detail", {}
        ).get(
            "preOpenMarket", {}
        )

        symbol = metadata.get("symbol")

        series = metadata.get("series")

        iep = metadata.get("iep", 0) or 0

        change = metadata.get(
            "pChange", 0
        ) or 0

        buy_qty = market.get(
            "totalBuyQuantity", 0
        ) or 0

        sell_qty = market.get(
            "totalSellQuantity", 0
        ) or 0

        # ====================================================
        # 🔒 BOSS FILTER — DO NOT CHANGE
        # ====================================================

        if series != "EQ":
            continue

        if iep <= 0:
            continue

        if change < MIN_CHANGE:
            continue

        if buy_qty < MIN_BUY_QTY:
            continue

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

    results.sort(
        key=lambda x: (
            x["change"],
            x["ratio"],
            x["buy"]
        ),
        reverse=True
    )

    return results


# ============================================================
# STOCK ALERT MESSAGE
# ============================================================

def create_stock_message(stocks):

    current = now_ist()

    message = (
        "🚨 PREOPEN GEMS OFFICIAL\n"
        "🔥 PRE-OPEN BOSS SIGNAL\n\n"

        f"📅 {current.strftime('%d-%b-%Y')}\n"
        f"⏰ {current.strftime('%I:%M:%S %p')} IST\n\n"

        "💎 VERY STRONG BUYING\n\n"
    )

    for i, stock in enumerate(stocks[:10], 1):

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
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3.0x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "⚠️ Pre-open data only.\n"
        "Not a buy/sell recommendation.\n\n"

        "💻 Made by Prakash Kanki"
    )

    return message


# ============================================================
# TELEGRAM COMMAND HANDLER
# ============================================================

telegram_offset = 0


def handle_telegram_commands():

    global telegram_offset

    try:

        response = requests.get(
            TELEGRAM_GET_URL,
            params={
                "offset": telegram_offset,
                "timeout": 5
            },
            timeout=10
        )

        if response.status_code != 200:

            print(
                "Telegram getUpdates error:",
                response.status_code
            )

            return

        updates = response.json().get(
            "result",
            []
        )

        for update in updates:

            telegram_offset = (
                update["update_id"] + 1
            )

            message = update.get("message")

            if not message:
                continue

            text = message.get(
                "text",
                ""
            ).strip()

            chat_id = message.get(
                "chat",
                {}
            ).get("id")

            if not chat_id:
                continue

            # ------------------------------------------------
            # /start
            # ------------------------------------------------

            if text.startswith("/start"):

                send_telegram(
                    start_message(),
                    chat_id
                )

                print(
                    "Received /start"
                )

            # ------------------------------------------------
            # /test
            # ------------------------------------------------

            elif text.startswith("/test"):

                send_telegram(
                    test_message(),
                    chat_id
                )

                print(
                    "Received /test"
                )


    except Exception as e:

        print(
            "Telegram polling error:",
            e
        )


# ============================================================
# MAIN SCANNER
# ============================================================

def run_scanner():

    global telegram_offset

    telegram_offset = 0

    print("\n")
    print("==============================================")
    print("      PREOPEN GEMS OFFICIAL")
    print("      NSE PRE-OPEN BOSS BOT")
    print("==============================================")

    print("🔒 BOSS FILTER LOCKED")
    print("----------------------------------------------")

    print(
        "IEP Change : >=",
        MIN_CHANGE,
        "%"
    )

    print(
        "B/S Ratio  : >=",
        MIN_RATIO,
        "x"
    )

    print(
        "Buy Qty    : >=",
        f"{MIN_BUY_QTY:,}"
    )

    print(
        "Series     : EQ"
    )

    print(
        "Scan       :",
        SCAN_INTERVAL,
        "seconds"
    )

    print("==============================================")

    # ========================================================
    # BOT ONLINE MESSAGE
    # ========================================================

    send_telegram(
        "🤖 PREOPEN GEMS OFFICIAL\n\n"
        "✅ Bot is online!\n"
        "✅ Telegram connection established!\n"
        "✅ NSE scanner is ready!\n\n"
        "⏰ Scanner will run:\n"
        "09:00–09:08 AM IST\n\n"
        "💻 Made by Prakash Kanki"
    )

    # ========================================================
    # WAIT FOR 9:00 AM IST
    # ========================================================

    while True:

        handle_telegram_commands()

        current = now_ist()

        current_time = current.strftime(
            "%H:%M:%S"
        )

        if current_time >= "09:00:00":
            break

        print(
            "Waiting for 09:00 AM IST...",
            current_time
        )

        time.sleep(5)

    # ========================================================
    # PRE-OPEN SCANNER
    # ========================================================

    print(
        "\n🔥 PRE-OPEN SCANNING STARTED"
    )

    alerted_stocks.clear()

    while True:

        handle_telegram_commands()

        current = now_ist()

        current_time = current.strftime(
            "%H:%M:%S"
        )

        if current_time >= "09:08:00":
            break

        print(
            "\nScanning NSE...",
            current_time
        )

        data = get_nse_data()

        print(
            "NSE Records:",
            len(data)
        )

        if not data:

            print(
                "No NSE data received."
            )

            time.sleep(
                SCAN_INTERVAL
            )

            continue

        results = scan_stocks(data)

        print(
            "BOSS stocks found:",
            len(results)
        )

        # ====================================================
        # NEW STOCK DETECTION
        # ====================================================

        new_stocks = []

        for stock in results:

            symbol = stock["symbol"]

            if symbol not in alerted_stocks:

                alerted_stocks.add(symbol)

                new_stocks.append(stock)

        # ====================================================
        # TELEGRAM ALERT
        # ====================================================

        if new_stocks:

            print(
                "\n🚨 NEW BOSS STOCKS"
            )

            for stock in new_stocks:

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

            send_telegram(
                create_stock_message(
                    new_stocks
                )
            )

        else:

            print(
                "No NEW BOSS stock in this scan."
            )

        time.sleep(
            SCAN_INTERVAL
        )

    # ========================================================
    # SESSION FINISHED
    # ========================================================

    print("\n")
    print("==============================================")
    print(" NSE PRE-OPEN SESSION FINISHED")
    print("==============================================")

    send_telegram(
        "🏁 PREOPEN GEMS OFFICIAL\n\n"
        "NSE Pre-Open scan finished.\n\n"
        f"⏰ {now_ist().strftime('%I:%M:%S %p')} IST\n"
        f"🔥 BOSS stocks detected: "
        f"{len(alerted_stocks)}\n\n"
        "Scanner stopped for today.\n\n"
        "💻 Made by Prakash Kanki"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if not BOT_TOKEN:

        print(
            "ERROR: TELEGRAM_BOT_TOKEN is missing."
        )

        raise SystemExit(1)

    if not CHAT_ID:

        print(
            "ERROR: TELEGRAM_CHAT_ID is missing."
        )

        raise SystemExit(1)

    run_scanner()
