import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# 💎 PREOPEN GEMS OFFICIAL
# NSE PRE-OPEN BOSS + FUNDAMENTAL QUALITY SCORE
# ============================================================

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SCAN_INTERVAL = 30

# ============================================================
# 🔒 BOSS FILTER — LOCKED
# DO NOT CHANGE
# ============================================================

MIN_CHANGE = 2.0
MIN_RATIO = 3.0
MIN_BUY_QTY = 50_000

# ============================================================
# 💎 FUNDAMENTAL QUALITY SCORE
# ============================================================

MIN_MARKET_CAP = 500_00_00_000      # ₹500 Cr
MIN_GEM_SCORE = 4
MIN_STRONG_SCORE = 5

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_SEND_URL = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
)

TELEGRAM_GET_URL = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
)

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

# ============================================================
# MEMORY
# ============================================================

alerted_stocks = set()
fundamental_cache = {}

telegram_offset = 0


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

        print(
            "Telegram ERROR:",
            response.status_code
        )

        print(response.text)

    except Exception as e:

        print(
            "Telegram connection error:",
            e
        )

    return False


# ============================================================
# /START
# ============================================================

def start_message():

    return (
        "👋 Hello!\n\n"

        "💎 Welcome to PreOpen Gems Official\n"
        "NSE Pre-Open Market Intelligence Bot\n\n"

        "📊 This bot scans NSE pre-open data "
        "for strong buying interest.\n\n"

        "⏰ Active Time\n"
        "09:00 AM – 09:08 AM IST\n\n"

        "🔄 Scan Frequency\n"
        "Every 30 seconds\n\n"

        "🔒 BOSS FILTER\n"
        "• IEP Change ≥ +2%\n"
        "• Buy/Sell Ratio ≥ 3.0x\n"
        "• Buy Quantity ≥ 50,000\n"
        "• Series = EQ\n\n"

        "💎 FUNDAMENTAL QUALITY SCORE\n"
        "7 parameters\n"
        "Minimum GEM Score = 4/7\n\n"

        "⚠️ Pre-open data is indicative.\n"
        "For information and educational purposes only.\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "💎 PREOPEN GEMS OFFICIAL\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "💻 Made by Prakash Kanki"
    )


# ============================================================
# /TEST
# ============================================================

def test_message():

    return (
        "🧪 PREOPEN GEMS OFFICIAL — TEST\n\n"

        "✅ Telegram connection working\n"
        "✅ NSE scanner loaded\n"
        "✅ BOSS filter loaded\n"
        "✅ Fundamental Score loaded\n\n"

        "🔒 BOSS FILTER\n"
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3.0x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ\n\n"

        "💎 GEM SCORE\n"
        "Minimum Score = 4/7\n"
        "Strong GEM = 5/7+\n\n"

        "⏰ 09:00–09:08 AM IST\n"
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

            print(
                "NSE ERROR:",
                response.status_code
            )

            return []

        data = response.json().get(
            "data",
            []
        )

        return data

    except Exception as e:

        print(
            "NSE connection error:",
            e
        )

        return []


# ============================================================
# 🔒 BOSS FILTER
# EXACTLY SAME
# ============================================================

def scan_boss_stocks(data):

    results = []

    for item in data:

        metadata = item.get(
            "metadata",
            {}
        )

        market = item.get(
            "detail",
            {}
        ).get(
            "preOpenMarket",
            {}
        )

        symbol = metadata.get(
            "symbol"
        )

        series = metadata.get(
            "series"
        )

        iep = metadata.get(
            "iep",
            0
        ) or 0

        change = metadata.get(
            "pChange",
            0
        ) or 0

        buy_qty = market.get(
            "totalBuyQuantity",
            0
        ) or 0

        sell_qty = market.get(
            "totalSellQuantity",
            0
        ) or 0

        # ====================================================
        # 🔒 BOSS FILTER — NEVER CHANGE
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

        ticker = yf.Ticker(
            symbol + ".NS"
        )

        info = ticker.info

        market_cap = info.get(
            "marketCap"
        )

        roe = info.get(
            "returnOnEquity"
        )

        roce = info.get(
            "returnOnCapitalEmployed"
        )

        debt_equity = info.get(
            "debtToEquity"
        )

        sales_growth = info.get(
            "revenueGrowth"
        )

        profit_growth = info.get(
            "earningsGrowth"
        )

        pledge = info.get(
            "pledgedShares"
        )

        # ----------------------------------------------------
        # Convert decimals to %
        # ----------------------------------------------------

        if roe is not None:
            roe = roe * 100

        if roce is not None:
            roce = roce * 100

        if sales_growth is not None:
            sales_growth = sales_growth * 100

        if profit_growth is not None:
            profit_growth = profit_growth * 100

        if pledge is not None:
            pledge = pledge * 100

        # ----------------------------------------------------
        # Debt/Equity
        # Yahoo commonly returns this as percentage
        # ----------------------------------------------------

        if debt_equity is not None:
            debt_equity = debt_equity / 100

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
            "Fundamentals:",
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

        fundamental_cache[symbol] = {}

        return {}


# ============================================================
# 💎 QUALITY SCORE
# ============================================================

def calculate_quality_score(symbol):

    f = get_fundamentals(symbol)

    score = 0

    reasons = []

    # --------------------------------------------------------
    # MARKET CAP
    # --------------------------------------------------------

    market_cap = f.get(
        "market_cap"
    )

    if market_cap is not None:

        if market_cap >= MIN_MARKET_CAP:

            score += 1
            reasons.append(
                "Market Cap ✓"
            )

        else:

            # Too small = reject
            return {
                "score": 0,
                "status": "REJECT",
                "reason": "Market Cap < ₹500 Cr",
                "data": f
            }

    else:

        # Missing market cap = cannot verify size
        return {
            "score": 0,
            "status": "REJECT",
            "reason": "Market Cap unavailable",
            "data": f
        }

    # --------------------------------------------------------
    # ROE
    # --------------------------------------------------------

    roe = f.get(
        "roe"
    )

    if roe is not None:

        if roe >= 12:

            score += 1
            reasons.append(
                "ROE ✓"
            )

    # --------------------------------------------------------
    # ROCE
    # --------------------------------------------------------

    roce = f.get(
        "roce"
    )

    if roce is not None:

        if roce >= 15:

            score += 1
            reasons.append(
                "ROCE ✓"
            )

    # --------------------------------------------------------
    # DEBT/EQUITY
    # --------------------------------------------------------

    debt_equity = f.get(
        "debt_equity"
    )

    if debt_equity is not None:

        if debt_equity <= 0.50:

            score += 1
            reasons.append(
                "Low Debt ✓"
            )

    # --------------------------------------------------------
    # SALES GROWTH
    # --------------------------------------------------------

    sales_growth = f.get(
        "sales_growth"
    )

    if sales_growth is not None:

        if sales_growth >= 10:

            score += 1
            reasons.append(
                "Sales Growth ✓"
            )

    # --------------------------------------------------------
    # PROFIT GROWTH
    # --------------------------------------------------------

    profit_growth = f.get(
        "profit_growth"
    )

    if profit_growth is not None:

        if profit_growth >= 10:

            score += 1
            reasons.append(
                "Profit Growth ✓"
            )

    # --------------------------------------------------------
    # PLEDGE
    # --------------------------------------------------------

    pledge = f.get(
        "pledge"
    )

    if pledge is not None:

        if pledge <= 5:

            score += 1
            reasons.append(
                "Low Pledge ✓"
            )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if score >= MIN_STRONG_SCORE:

        status = "STRONG GEM"

    elif score >= MIN_GEM_SCORE:

        status = "GEM"

    else:

        status = "BOSS ONLY"

    return {
        "score": score,
        "status": status,
        "reason": reasons,
        "data": f
    }


# ============================================================
# APPLY QUALITY SCORE
# ============================================================

def apply_quality_score(boss_stocks):

    gems = []

    for stock in boss_stocks:

        symbol = stock[
            "symbol"
        ]

        print(
            "💎 Quality checking:",
            symbol
        )

        quality = calculate_quality_score(
            symbol
        )

        score = quality[
            "score"
        ]

        status = quality[
            "status"
        ]

        stock[
            "quality_score"
        ] = score

        stock[
            "quality_status"
        ] = status

        stock[
            "quality_reasons"
        ] = quality.get(
            "reason",
            []
        )

        stock[
            "fundamentals"
        ] = quality.get(
            "data",
            {}
        )

        print(
            symbol,
            "Score:",
            score,
            "/7",
            status
        )

        # ----------------------------------------------------
        # Only GEM 4+ goes to Telegram
        # ----------------------------------------------------

        if score >= MIN_GEM_SCORE:

            gems.append(
                stock
            )

    gems.sort(
        key=lambda x: (
            x["quality_score"],
            x["change"],
            x["ratio"],
            x["buy"]
        ),
        reverse=True
    )

    return gems


# ============================================================
# TELEGRAM GEM MESSAGE
# ============================================================

def create_stock_message(stocks):

    current = now_ist()

    message = (
        "💎 PREOPEN GEMS OFFICIAL\n"
        "🔥 FUNDAMENTAL + BOSS GEM\n\n"

        f"📅 "
        f"{current.strftime('%d-%b-%Y')}\n"

        f"⏰ "
        f"{current.strftime('%I:%M:%S %p')} IST\n\n"
    )

    for i, stock in enumerate(
        stocks[:10],
        1
    ):

        f = stock.get(
            "fundamentals",
            {}
        )

        market_cap = f.get(
            "market_cap"
        )

        if market_cap:

            market_cap_cr = (
                market_cap / 10_000_000
            )

            market_text = (
                f"₹{market_cap_cr:,.0f} Cr"
            )

        else:

            market_text = "N/A"

        roe = f.get(
            "roe"
        )

        roce = f.get(
            "roce"
        )

        de = f.get(
            "debt_equity"
        )

        sales = f.get(
            "sales_growth"
        )

        profit = f.get(
            "profit_growth"
        )

        pledge = f.get(
            "pledge"
        )

        score = stock[
            "quality_score"
        ]

        status = stock[
            "quality_status"
        ]

        message += (
            f"{i}️⃣ {stock['symbol']}\n"

            f"Signal     : 💎 {status}\n"

            f"Quality    : "
            f"{score}/7\n"

            f"IEP        : "
            f"₹{stock['iep']:,.2f}\n"

            f"Change     : "
            f"+{stock['change']:.2f}%\n"

            f"Buy Qty    : "
            f"{stock['buy']:,}\n"

            f"Sell Qty   : "
            f"{stock['sell']:,}\n"

            f"B/S Ratio  : "
            f"{stock['ratio']:.2f}x\n"

            f"Market Cap : "
            f"{market_text}\n"

            f"ROE        : "
            f"{roe:.1f}%\n"
            if roe is not None
            else
            "ROE        : N/A\n"
        )

        message += (
            f"ROCE       : "
            f"{roce:.1f}%\n"
            if roce is not None
            else
            "ROCE       : N/A\n"
        )

        message += (
            f"D/E        : "
            f"{de:.2f}\n"
            if de is not None
            else
            "D/E        : N/A\n"
        )

        message += (
            f"Sales Gr.   : "
            f"{sales:.1f}%\n"
            if sales is not None
            else
            "Sales Gr.   : N/A\n"
        )

        message += (
            f"Profit Gr.  : "
            f"{profit:.1f}%\n"
            if profit is not None
            else
            "Profit Gr.  : N/A\n"
        )

        message += (
            f"Pledge      : "
            f"{pledge:.1f}%\n"
            if pledge is not None
            else
            "Pledge      : N/A\n"
        )

        message += "\n"

    message += (
        "━━━━━━━━━━━━━━━━━━\n"

        "🔒 BOSS FILTER\n"
        "IEP Change ≥ +2%\n"
        "B/S Ratio ≥ 3.0x\n"
        "Buy Qty ≥ 50,000\n"
        "Series = EQ\n\n"

        "💎 QUALITY SCORE\n"
        "Market Cap ≥ ₹500 Cr\n"
        "ROE ≥ 12% = +1\n"
        "ROCE ≥ 15% = +1\n"
        "D/E ≤ 0.50 = +1\n"
        "Sales Growth ≥ 10% = +1\n"
        "Profit Growth ≥ 10% = +1\n"
        "Pledge ≤ 5% = +1\n\n"

        "💎 GEM = 4/7+\n"
        "🔥 STRONG GEM = 5/7+\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "⚠️ Pre-open data is indicative.\n"
        "Not a buy/sell recommendation.\n\n"

        "💻 Made by Prakash Kanki"
    )

    return message


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

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
            ).get(
                "id"
            )

            if not chat_id:
                continue

            if text.startswith(
                "/start"
            ):

                send_telegram(
                    start_message(),
                    chat_id
                )

                print(
                    "Received /start"
                )

            elif text.startswith(
                "/test"
            ):

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

    print("\n")
    print(
        "=============================================="
    )

    print(
        "       PREOPEN GEMS OFFICIAL"
    )

    print(
        "       BOSS + QUALITY SCORE BOT"
    )

    print(
        "=============================================="
    )

    print(
        "🔒 BOSS FILTER LOCKED"
    )

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

    print(
        "----------------------------------------------"
    )

    print(
        "💎 GEM SCORE:",
        f"{MIN_GEM_SCORE}/7+"
    )

    print(
        "🔥 STRONG GEM:",
        f"{MIN_STRONG_SCORE}/7+"
    )

    print(
        "Min Market Cap:",
        "₹500 Cr"
    )

    print(
        "=============================================="
    )

    send_telegram(
        "🤖 PREOPEN GEMS OFFICIAL\n\n"
        "✅ Bot is online!\n"
        "✅ Telegram connected!\n"
        "✅ NSE scanner ready!\n"
        "✅ BOSS filter loaded!\n"
        "✅ Quality Score loaded!\n\n"
        "⏰ Scanner:\n"
        "09:00–09:08 AM IST\n"
        "🔄 Every 30 seconds\n\n"
        "💻 Made by Prakash Kanki"
    )

    # ========================================================
    # WAIT FOR 09:00
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
    # START
    # ========================================================

    print(
        "\n🔥 PRE-OPEN SCANNING STARTED"
    )

    alerted_stocks.clear()
    fundamental_cache.clear()

    # ========================================================
    # 09:00 → 09:08
    # ========================================================

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
                "No NSE data."
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

        # ----------------------------------------------------
        # STEP 2 — QUALITY SCORE
        # ----------------------------------------------------

        gems = apply_quality_score(
            boss_stocks
        )

        print(
            "💎 GEM stocks:",
            len(gems)
        )

        # ----------------------------------------------------
        # STEP 3 — NEW GEM
        # ----------------------------------------------------

        new_gems = []

        for stock in gems:

            symbol = stock[
                "symbol"
            ]

            if symbol not in alerted_stocks:

                alerted_stocks.add(
                    symbol
                )

                new_gems.append(
                    stock
                )

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        if new_gems:

            print(
                "\n💎 NEW GEMS"
            )

            for stock in new_gems:

                print(
                    stock["symbol"],
                    "| Score:",
                    stock["quality_score"],
                    "/7",
                    "|",
                    f"{stock['change']:.2f}%",
                    "| B/S:",
                    f"{stock['ratio']:.2f}x"
                )

            send_telegram(
                create_stock_message(
                    new_gems
                )
            )

        else:

            print(
                "No NEW GEM."
            )

        time.sleep(
            SCAN_INTERVAL
        )

    # ========================================================
    # FINISHED
    # ========================================================

    print("\n")
    print(
        "=============================================="
    )

    print(
        " NSE PRE-OPEN SESSION FINISHED"
    )

    print(
        "=============================================="
    )

    send_telegram(
        "🏁 PREOPEN GEMS OFFICIAL\n\n"

        "NSE Pre-Open scan finished.\n\n"

        f"⏰ "
        f"{now_ist().strftime('%I:%M:%S %p')} IST\n"

        f"💎 GEM stocks detected: "
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
            "ERROR: TELEGRAM_BOT_TOKEN missing."
        )

        raise SystemExit(1)

    if not CHAT_ID:

        print(
            "ERROR: TELEGRAM_CHAT_ID missing."
        )

        raise SystemExit(1)

    run_scanner()
