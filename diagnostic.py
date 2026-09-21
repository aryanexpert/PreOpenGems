import os
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"

MIN_IEP_CHANGE = 2.0
MIN_BS_RATIO = 3.0
MIN_BUY_QTY = 50000

MIN_MARKET_CAP = 500_00_00_000
MIN_GEM_SCORE = 4

fundamental_cache = {}


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

        print("NSE HTTP:", response.status_code)

        if response.status_code != 200:
            return []

        return response.json().get("data", [])

    except Exception as e:

        print("NSE ERROR:", e)
        return []


# ============================================================
# BOSS FILTER
# ============================================================

def get_boss_stocks(data):

    boss = []

    for item in data:

        try:

            metadata = item.get("metadata", {})
            detail = item.get("detail", {})

            symbol = metadata.get("symbol", "")
            series = metadata.get("series", "")

            pchange = float(
                metadata.get("pChange") or 0
            )

            iep = float(
                metadata.get("iep") or 0
            )

            preopen = detail.get(
                "preOpenMarket", {}
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
# QUALITY SCORE
# ============================================================

def quality_score(f):

    score = 0

    market_cap = f["market_cap"]
    roe = f["roe"]
    roce = f["roce"]
    de = f["de"]
    sales_growth = f["sales_growth"]
    profit_growth = f["profit_growth"]
    pledge = f["pledge"]

    # Market Cap
    if market_cap is None:
        return 0

    if market_cap < MIN_MARKET_CAP:
        return 0

    score += 1

    # ROE
    if roe is not None and roe >= 0.12:
        score += 1

    # ROCE
    if roce is not None and roce >= 0.15:
        score += 1

    # D/E
    if de is not None and de <= 0.50:
        score += 1

    # Sales Growth
    if sales_growth is not None and sales_growth >= 0.10:
        score += 1

    # Profit Growth
    if profit_growth is not None and profit_growth >= 0.10:
        score += 1

    # Pledge
    if pledge is not None and pledge <= 0.05:
        score += 1

    return score


# ============================================================
# DISPLAY
# ============================================================

def pct(value):

    if value is None:
        return "N/A"

    return f"{value * 100:.1f}%"


def market_cap(value):

    if value is None:
        return "N/A"

    return f"₹{value / 1e7:,.0f} Cr"


def show_stock(stock, f, score):

    print()
    print("=" * 60)

    print(
        f"📌 {stock['symbol']}"
    )

    print(
        f"IEP Change : +{stock['pchange']:.2f}%"
    )

    print(
        f"IEP        : ₹{stock['iep']:.2f}"
    )

    print(
        f"Buy Qty    : {int(stock['buy_qty']):,}"
    )

    print(
        f"Sell Qty   : {int(stock['sell_qty']):,}"
    )

    print(
        f"B/S Ratio  : {stock['bs_ratio']:.2f}x"
    )

    print("-" * 60)

    print(
        f"Market Cap : {market_cap(f['market_cap'])}"
    )

    print(
        f"ROE        : {pct(f['roe'])}"
    )

    print(
        f"ROCE       : {pct(f['roce'])}"
    )

    print(
        f"D/E        : "
        f"{f['de'] if f['de'] is not None else 'N/A'}"
    )

    print(
        f"Sales Gr.  : {pct(f['sales_growth'])}"
    )

    print(
        f"Profit Gr. : {pct(f['profit_growth'])}"
    )

    print(
        f"Pledge     : {pct(f['pledge'])}"
    )

    print(
        f"⭐ SCORE    : {score}/7"
    )

    if score >= 5:
        print("🔥 STRONG GEM")

    elif score >= 4:
        print("💎 GEM")

    else:
        print("❌ NOT GEM")

    print("=" * 60)


# ============================================================
# MAIN DIAGNOSTIC
# ============================================================

def main():

    now = datetime.now(IST)

    print()
    print("=" * 60)
    print("🔍 PREOPEN GEMS OFFICIAL")
    print("🧪 DIAGNOSTIC MODE")
    print("=" * 60)

    print(
        "⏰ Test Time:",
        now.strftime("%d-%b-%Y %H:%M:%S"),
        "IST"
    )

    print()
    print("📡 Fetching NSE data...")

    data = get_nse_data()

    print(
        f"📊 NSE Records: {len(data)}"
    )

    if not data:

        print(
            "❌ NSE data unavailable."
        )

        return

    # --------------------------------------------------------
    # BOSS
    # --------------------------------------------------------

    boss = get_boss_stocks(data)

    print()
    print(
        f"🔒 BOSS Matches: {len(boss)}"
    )

    if not boss:

        print()
        print(
            "⚠️ BOSS filter returned ZERO stocks."
        )

        print(
            "Quality Score was not the reason."
        )

        return

    # --------------------------------------------------------
    # FUNDAMENTAL
    # --------------------------------------------------------

    print()
    print(
        "💎 Checking fundamentals..."
    )

    market_cap_pass = 0
    gem_count = 0
    strong_count = 0

    for stock in boss:

        symbol = stock["symbol"]

        print()
        print(
            f"Checking {symbol}..."
        )

        f = get_fundamentals(symbol)

        score = quality_score(f)

        if (
            f["market_cap"] is not None
            and f["market_cap"] >= MIN_MARKET_CAP
        ):
            market_cap_pass += 1

        if score >= 4:
            gem_count += 1

        if score >= 5:
            strong_count += 1

        show_stock(
            stock,
            f,
            score
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("🏁 DIAGNOSTIC SUMMARY")
    print("=" * 60)

    print(
        f"📊 NSE Records       : {len(data)}"
    )

    print(
        f"🔒 BOSS Matches      : {len(boss)}"
    )

    print(
        f"💰 Market Cap Passed : {market_cap_pass}"
    )

    print(
        f"💎 GEM 4/7+          : {gem_count}"
    )

    print(
        f"🔥 STRONG 5/7+       : {strong_count}"
    )

    print("=" * 60)

    print()
    print(
        "🔒 BOSS FILTER WAS NOT CHANGED."
    )

    print(
        "🧪 Diagnostic test completed."
    )


if __name__ == "__main__":
    main()
