import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# 💎 PREOPEN GEMS OFFICIAL
# NSE PRE-OPEN BOSS + FUNDAMENTAL QUALITY BOT
# ============================================================

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SCAN_INTERVAL = 30

# ============================================================
# 🔒 BOSS FILTER — LOCKED / NEVER CHANGE
# ============================================================

MIN_CHANGE = 2.0
MIN_RATIO = 3.0
MIN_BUY_QTY = 50_000

# ============================================================
# 💎 FUNDAMENTAL QUALITY FILTER
# ============================================================

MIN_MARKET_CAP = 2_000_00_00_000      # ₹2,000 Cr
MIN_ROE = 12.0
MIN_ROCE = 15.0
MAX_DEBT_EQUITY = 0.50
MIN_SALES_GROWTH = 10.0
MIN_PROFIT_GROWTH = 10.0
MAX_PLEDGE = 5.0

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

# Fundamental data cache
fundamental_cache = {}


# ============================================================
# TIME
# ============================================================

def now_ist():
    return datetime.now(IST)


# ============================================================
# TELEGRAM SEND
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
# START MESSAGE
# ============================================================

def start_message():
    return (
        "👋 Hello!\n\n"
        "💎 Welcome to PreOpen Gems Official\n"
        "NSE Pre-Open Market Intelligence Bot\n\n"

        "📊 What this bot does:\n"
        "Scans NSE pre-open data and identifies stocks "
        "with strong buying interest plus fundamental quality.\n\n"

        "⏰ Active Time\n"
        "09:00 AM – 09:08 AM IST\n\n"

        "🔄 Scan Frequency\n"
        "Every 30 seconds\n\n"

        "🔒 BOSS FILTER\n"
        "• IEP Change ≥ +2%\n"
        "• Buy/Sell Ratio ≥ 3.0x\n"
        "• Buy Quantity ≥ 50,000\n"
        "• Series = EQ\n\n"

        "💎 FUNDAMENTAL QUALITY\n"
        "• Market Cap ≥ ₹2,000 Cr\n"
        "• ROE ≥ 12%\n"
        "• ROCE ≥ 15%\n"
        "• Debt/Equity ≤ 0.50\n"
        "• Sales Growth ≥ 10%\n"
        "• Profit Growth ≥ 10%\n"
        "• Promoter Pledge ≤ 5%\n\n"

        "⚠️ Informational/educational use only.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💎 PREOPEN GEMS OFFICIAL\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "💻 Made by Prakash Kanki"
    )


# ============================================================
# TEST MESSAGE
# ============================================================

def test_message():
    return (
        "🧪 PREOPEN GEMS OFFICIAL — TEST\n\n"

        "👋 Hello Prakash!\n\n"

        "✅ Telegram connection is working!\n"
        "✅ Bot is online!\n"
        "✅ BOSS filter loaded!\n"
        "✅ Fundamental filter loaded!\n\n"

        "🔒 BOSS FILTER\n"
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3.0x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ\n\n"

        "💎 FUNDAMENTAL FILTER\n"
        "Market Cap ≥ ₹2,000 Cr\n"
        "ROE ≥ 12%\n"
        "ROCE ≥ 15%\n"
        "Debt/Equity ≤ 0.50\n"
        "Sales Growth ≥ 10%\n"
        "Profit Growth ≥ 10%\n"
        "Pledge ≤ 5%\n\n"

        "⏰ 09:00 AM – 09:08 AM IST\n"
        "🔄 Every 30 seconds\n\n"

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
# BOSS FILTER
# 🔒 DO NOT CHANGE
# ============================================================

def scan_boss_stocks(data):

    results = []

    for item in data:

        metadata = item.get("metadata", {})
        market = item.get("detail", {}).get(
            "preOpenMarket", {}
        )

        symbol = metadata.get("symbol")
        series = metadata.get("series")

        iep = metadata.get("iep", 0) or 0
        change = metadata.get("pChange", 0) or 0

        buy_qty = market.get(
            "totalBuyQuantity", 0
        ) or 0

        sell_qty = market.get(
            "totalSellQuantity", 0
        ) or 0

        # ====================================================
        # 🔒 BOSS FILTER — EXACTLY SAME
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
# FUNDAMENTAL DATA
# ============================================================

def get_fundamentals(symbol):

    if symbol in fundamental_cache:
        return fundamental_cache[symbol]

    try:

        import yfinance as yf

        ticker = yf.Ticker(symbol + ".NS")

        info = ticker.info

        market_cap = info.get(
            "marketCap"
        )

        roe = info.get(
            "returnOnEquity"
        )

        debt_equity = info.get(
            "debtToEquity"
        )

        # Yahoo gives ROE as decimal
        if roe is not None:
            roe = roe * 100

        # Yahoo debt/equity is normally in percentage
        if debt_equity is not None:
            debt_equity = debt_equity / 100

        # ----------------------------------------------------
        # ROCE / growth may not always be available in Yahoo.
        # Try additional financial statements.
        # ----------------------------------------------------

        roce = info.get("returnOnCapitalEmployed")

        if roce is not None:
            roce = roce * 100

        sales_growth = info.get(
            "revenueGrowth"
        )

        if sales_growth is not None:
            sales_growth = sales_growth * 100

        profit_growth = info.get(
            "earningsGrowth"
        )

        if profit_growth is not None:
            profit_growth = profit_growth * 100

        pledge = info.get(
            "pledgedShares"
        )

        if pledge is not None:
            pledge = pledge * 100

        fundamentals = {
            "market_cap": market_cap,
            "roe": roe,
            "roce": roce,
            "debt_equity": debt_equity,
            "sales_growth": sales_growth,
            "profit_growth": profit_growth,
            "pledge": pledge
        }

        fundamental_cache[symbol] = fundamentals

        print(
            "Fundamental:",
            symbol,
            fundamentals
        )

        return fundamentals

    except Exception as e:

        print(
            "Fundamental error:",
            symbol,
            e
        )

        fundamental_cache[symbol] = None

        return None


# ============================================================
# FUNDAMENTAL QUALITY CHECK
# ============================================================

def passes_fundamental_filter(symbol):

    fundamentals = get_fundamentals(symbol)

    if not fundamentals:
        return False

    market_cap = fundamentals.get(
        "market_cap"
    )

    roe = fundamentals.get(
        "roe"
    )

    roce = fundamentals.get(
        "roce"
    )

    debt_equity = fundamentals.get(
        "debt_equity"
    )

    sales_growth = fundamentals.get(
        "sales_growth"
    )

    profit_growth = fundamentals.get(
        "profit_growth"
    )

    pledge = fundamentals.get(
        "pledge"
    )

    # --------------------------------------------------------
    # Missing fundamental data = reject
    # --------------------------------------------------------

    required = [
        market_cap,
        roe,
        roce,
        debt_equity,
        sales_growth,
        profit_growth,
        pledge
    ]

    if any(value is None for value in required):
        print(
            symbol,
            "❌ Fundamental data incomplete"
        )
        return False

    # --------------------------------------------------------
    # QUALITY FILTER
    # --------------------------------------------------------

    if market_cap < MIN_MARKET_CAP:
        return False

    if roe < MIN_ROE:
        return False

    if roce < MIN_ROCE:
        return False

    if debt_equity > MAX_DEBT_EQUITY:
        return False

    if sales_growth < MIN_SALES_GROWTH:
        return False

    if profit_growth < MIN_PROFIT_GROWTH:
        return False

    if pledge > MAX_PLEDGE:
        return False

    return True


# ============================================================
# APPLY FUNDAMENTAL FILTER
# ============================================================

def filter_quality_stocks(boss_stocks):

    quality = []

    for stock in boss_stocks:

        symbol = stock["symbol"]

        print(
            "Checking fundamentals:",
            symbol
        )

        if passes_fundamental_filter(symbol):

            fundamentals = fundamental_cache.get(
                symbol
            )

            stock["fundamentals"] = fundamentals

            quality.append(stock)

            print(
                "💎 QUALITY PASS:",
                symbol
            )

        else:

            print(
                "❌ QUALITY FAIL:",
                symbol
            )

    return quality


# ============================================================
# TELEGRAM STOCK MESSAGE
# ============================================================

def create_stock_message(stocks):

    current = now_ist()

    message = (
        "💎 PREOPEN GEMS OFFICIAL\n"
        "🔥 BOSS + FUNDAMENTAL GEM\n\n"

        f"📅 {current.strftime('%d-%b-%Y')}\n"
        f"⏰ {current.strftime('%I:%M:%S %p')} IST\n\n"

        "💎 FUNDAMENTALLY STRONG + "
        "PRE-OPEN BUYING\n\n"
    )

    for i, stock in enumerate(stocks[:10], 1):

        f = stock.get(
            "fundamentals",
            {}
        )

        market_cap = f.get(
            "market_cap", 0
        )

        market_cap_cr = (
            market_cap / 10_000_000
        )

        roe = f.get("roe", 0)
        roce = f.get("roce", 0)
        de = f.get("debt_equity", 0)
        sales = f.get("sales_growth", 0)
        profit = f.get("profit_growth", 0)
        pledge = f.get("pledge", 0)

        message += (
            f"{i}️⃣ {stock['symbol']}\n"

            f"IEP       : "
            f"₹{stock['iep']:,.2f}\n"

            f"Change    : "
            f"+{stock['change']:.2f}%\n"

            f"Buy Qty   : "
            f"{stock['buy']:,}\n"

            f"Sell Qty  : "
            f"{stock['sell']:,}\n"

            f"B/S Ratio : "
            f"{stock['ratio']:.2f}x\n"

            f"Market Cap: "
            f"₹{market_cap_cr:,.0f} Cr\n"

            f"ROE       : "
            f"{roe:.1f}%\n"

            f"ROCE      : "
            f"{roce:.1f}%\n"

            f"D/E       : "
            f"{de:.2f}\n"

            f"Sales Gr.  : "
            f"{sales:.1f}%\n"

            f"Profit Gr. : "
            f"{profit:.1f}%\n"

            f"Pledge     : "
            f"{pledge:.1f}%\n"

            f"Signal    : 💎 GEM\n\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🔒 BOSS FILTER\n"
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3.0x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ\n\n"

        "💎 QUALITY FILTER\n"
        "Market Cap ≥ ₹2,000 Cr\n"
        "ROE ≥ 12%\n"
        "ROCE ≥ 15%\n"
        "D/E ≤ 0.50\n"
        "Sales Growth ≥ 10%\n"
        "Profit Growth ≥ 10%\n"
        "Pledge ≤ 5%\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "⚠️ Pre-open data is indicative.\n"
        "Not a buy/sell recommendation.\n\n"

        "💻 Made by Prakash Kanki"
    )

    return message


# ============================================================
# TELEGRAM COMMANDS
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
            return

        updates = response.json().get(
            "result",
            []
        )

        for update in updates:

            telegram_offset = (
                update["update_id"] + 1
            )

            message = update.get(
                "message"
            )

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

            if text.startswith("/start"):

                send_telegram(
                    start_message(),
                    chat_id
                )

                print(
                    "Received /start"
                )

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
    print("      NSE BOSS + FUNDAMENTAL BOT")
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

    print("----------------------------------------------")
    print("💎 FUNDAMENTAL FILTER")
    print(
        "Market Cap : >=",
        "₹2,000 Cr"
    )
    print(
        "ROE        : >=",
        MIN_ROE,
        "%"
    )
    print(
        "ROCE       : >=",
        MIN_ROCE,
        "%"
    )
    print(
        "Debt/Equity:",
        "<=",
        MAX_DEBT_EQUITY
    )
    print(
        "Sales Growth:",
        ">=",
        MIN_SALES_GROWTH,
        "%"
    )
    print(
        "Profit Growth:",
        ">=",
        MIN_PROFIT_GROWTH,
        "%"
    )
    print(
        "Pledge      : <=",
        MAX_PLEDGE,
        "%"
    )

    print("==============================================")

    send_telegram(
        "🤖 PREOPEN GEMS OFFICIAL\n\n"
        "✅ Bot is online!\n"
        "✅ Telegram connected!\n"
        "✅ NSE scanner ready!\n"
        "✅ BOSS filter loaded!\n"
        "✅ Fundamental filter loaded!\n\n"
        "⏰ Scanner:\n"
        "09:00–09:08 AM IST\n"
        "🔄 Every 30 seconds\n\n"
        "💻 Made by Prakash Kanki"
    )

    # ========================================================
    # WAIT FOR 09:00 IST
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
    # PRE-OPEN START
    # ========================================================

    print("\n🔥 PRE-OPEN SCANNING STARTED")

    alerted_stocks.clear()
    fundamental_cache.clear()

    # ========================================================
    # SCAN UNTIL 09:08
    # ========================================================

    while True:

        handle_telegram_commands()

        current = now_ist()

        current_time = current.strftime(
            "%H:%M:%S"
        )

        if current_time >= "09:08:00":
            break

        print("\nScanning NSE...", current_time)

        # ----------------------------------------------------
        # NSE DATA
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # STEP 1 — BOSS
        # ----------------------------------------------------

        boss_stocks = scan_boss_stocks(
            data
        )

        print(
            "🔒 BOSS stocks:",
            len(boss_stocks)
        )

        if not boss_stocks:

            print(
                "No BOSS stocks."
            )

            time.sleep(
                SCAN_INTERVAL
            )

            continue

        # ----------------------------------------------------
        # STEP 2 — FUNDAMENTAL QUALITY
        # ----------------------------------------------------

        quality_stocks = filter_quality_stocks(
            boss_stocks
        )

        print(
            "💎 Quality stocks:",
            len(quality_stocks)
        )

        # ----------------------------------------------------
        # STEP 3 — NEW GEM ALERT
        # ----------------------------------------------------

        new_stocks = []

        for stock in quality_stocks:

            symbol = stock["symbol"]

            if symbol not in alerted_stocks:

                alerted_stocks.add(
                    symbol
                )

                new_stocks.append(
                    stock
                )

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        if new_stocks:

            print(
                "\n💎 NEW FUNDAMENTAL GEMS"
            )

            for stock in new_stocks:

                print(
                    stock["symbol"],
                    "|",
                    f"{stock['change']:.2f}%",
                    "| Buy:",
                    f"{stock['buy']:,}",
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
                "No NEW Fundamental Gem."
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

        f"⏰ "
        f"{now_ist().strftime('%I:%M:%S %p')} IST\n"

        f"💎 Fundamental Gems: "
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
