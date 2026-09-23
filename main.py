import os
import time
import math
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# PREOPEN GEMS OFFICIAL
# BOSS + BUYER PRIORITY + QUALITY + RISK PENALTY
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
NSE_HOME = "https://www.nseindia.com/"

IST = ZoneInfo("Asia/Kolkata")

SCAN_INTERVAL = 30

# ============================================================
# 🔒 BOSS FILTER — LOCKED
# ============================================================

BOSS_MIN_CHANGE = 2.0
BOSS_MIN_RATIO = 3.0
BOSS_MIN_BUY_QTY = 50000
BOSS_SERIES = "EQ"

# ============================================================
# OUTPUT
# ============================================================

MIN_GEMS = 1
MAX_GEMS = 10

# ============================================================
# QUALITY / RISK SETTINGS
# ============================================================

MIN_MARKET_CAP_PREFERRED = 500       # ₹ Cr
MIN_MARKET_CAP_STRONG = 1000         # ₹ Cr

LOW_PRICE = 50
VERY_LOW_PRICE = 20

MIN_BUY_QTY = 50000

# ============================================================
# SESSION
# ============================================================

nse_session = requests.Session()

nse_headers = {
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

# ============================================================
# CACHE
# ============================================================

fundamental_cache = {}
price_cache = {}


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:

        r = requests.post(
            url,
            data=payload,
            timeout=15
        )

        if r.status_code == 200:
            return True

        print("Telegram error:", r.status_code, r.text[:500])
        return False

    except Exception as e:
        print("Telegram exception:", e)
        return False


# ============================================================
# NUMBER HELPERS
# ============================================================

def num(value, default=0):

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


def clean(value):

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

def get_nse_data():

    try:

        try:
            nse_session.get(
                NSE_HOME,
                headers=nse_headers,
                timeout=10
            )
        except Exception:
            pass

        r = nse_session.get(
            NSE_URL,
            headers=nse_headers,
            timeout=15
        )

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
        "pledge": None,
        "price": None,
    }

    try:

        ticker = yf.Ticker(symbol + ".NS")

        info = ticker.info

        # ----------------------------------------------------
        # Market Cap
        # ----------------------------------------------------

        market_cap = clean(
            info.get("marketCap")
        )

        if market_cap is not None:
            result["market_cap"] = market_cap / 10000000

        # ----------------------------------------------------
        # Current Price
        # ----------------------------------------------------

        price = clean(
            info.get("currentPrice")
        )

        if price is None:
            price = clean(
                info.get("regularMarketPrice")
            )

        result["price"] = price

        # ----------------------------------------------------
        # ROE
        # ----------------------------------------------------

        roe = clean(
            info.get("returnOnEquity")
        )

        if roe is not None:
            result["roe"] = roe * 100

        # ----------------------------------------------------
        # ROCE
        # ----------------------------------------------------

        roce = clean(
            info.get("returnOnCapitalEmployed")
        )

        if roce is not None:

            if roce < 1:
                roce *= 100

            result["roce"] = roce

        # ----------------------------------------------------
        # D/E
        # ----------------------------------------------------

        de = clean(
            info.get("debtToEquity")
        )

        if de is not None:

            # Yahoo can sometimes return 45.35
            # instead of 0.4535
            if de > 20:
                de = de / 100

            result["de"] = de

        # ----------------------------------------------------
        # Sales Growth
        # ----------------------------------------------------

        sales = clean(
            info.get("revenueGrowth")
        )

        if sales is not None:
            result["sales_growth"] = sales * 100

        # ----------------------------------------------------
        # Profit Growth
        # ----------------------------------------------------

        profit = clean(
            info.get("earningsGrowth")
        )

        if profit is not None:
            result["profit_growth"] = profit * 100

        # ----------------------------------------------------
        # Pledge
        # ----------------------------------------------------

        pledge = clean(
            info.get("pledgeRatio")
        )

        if pledge is not None:
            result["pledge"] = pledge * 100

    except Exception as e:

        print(f"Fundamental error {symbol}: {e}")

    fundamental_cache[symbol] = result

    return result


# ============================================================
# BOSS FILTER
# ============================================================

def boss_filter(record):

    try:

        metadata = record.get(
            "metadata",
            {}
        )

        detail = record.get(
            "detail",
            {}
        )

        symbol = metadata.get("symbol")
        series = metadata.get("series")

        change = num(
            metadata.get("pChange")
        )

        iep = num(
            metadata.get("iep")
        )

        preopen = detail.get(
            "preOpenMarket",
            {}
        )

        buy_qty = num(
            preopen.get(
                "totalBuyQuantity"
            )
        )

        sell_qty = num(
            preopen.get(
                "totalSellQuantity"
            )
        )

        if not symbol:
            return None

        # ====================================================
        # 🔒 BOSS — EXACTLY SAME
        # ====================================================

        if series != BOSS_SERIES:
            return None

        if change < BOSS_MIN_CHANGE:
            return None

        if buy_qty < BOSS_MIN_BUY_QTY:
            return None

        if sell_qty <= 0:
            return None

        ratio = buy_qty / sell_qty

        if ratio < BOSS_MIN_RATIO:
            return None

        return {
            "symbol": symbol,
            "series": series,
            "change": change,
            "iep": iep,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "ratio": ratio,
        }

    except Exception:
        return None


# ============================================================
# BUYER SCORE
# ============================================================

def buyer_score(item):

    ratio = item["ratio"]
    buy_qty = item["buy_qty"]
    change = item["change"]

    # --------------------------------------------------------
    # Ratio
    # --------------------------------------------------------

    if ratio <= 3:
        ratio_score = 25

    elif ratio >= 25:
        ratio_score = 100

    else:

        ratio_score = (
            25
            + ((ratio - 3) / 22) * 75
        )

    # --------------------------------------------------------
    # Buy Quantity
    # --------------------------------------------------------

    if buy_qty <= 50000:

        qty_score = 20

    else:

        qty_score = min(
            100,
            20 + (
                math.log10(
                    buy_qty / 50000
                ) * 45
            )
        )

    # --------------------------------------------------------
    # Change
    # --------------------------------------------------------

    change_score = min(
        100,
        max(
            0,
            change * 4
        )
    )

    # Buyer priority
    score = (
        ratio_score * 0.50
        + qty_score * 0.30
        + change_score * 0.20
    )

    return round(score, 2)


# ============================================================
# QUALITY SCORE
# ============================================================

def quality_score(f):

    score = 0
    reasons = []

    # Market cap
    if f["market_cap"] is not None:

        if f["market_cap"] >= 1000:

            score += 2
            reasons.append("Strong Market Cap")

        elif f["market_cap"] >= 500:

            score += 1
            reasons.append("Market Cap")

    # Sales growth
    if f["sales_growth"] is not None:

        if f["sales_growth"] >= 10:

            score += 1
            reasons.append("Sales Growth")

        elif f["sales_growth"] > 0:

            score += 0.5

    # Profit growth
    if f["profit_growth"] is not None:

        if f["profit_growth"] >= 10:

            score += 1
            reasons.append("Profit Growth")

        elif f["profit_growth"] > 0:

            score += 0.5

    # ROE
    if f["roe"] is not None:

        if f["roe"] >= 12:

            score += 1
            reasons.append("ROE")

    # ROCE
    if f["roce"] is not None:

        if f["roce"] >= 15:

            score += 1
            reasons.append("ROCE")

    # D/E
    if f["de"] is not None:

        if f["de"] <= 0.50:

            score += 1
            reasons.append("Low D/E")

        elif f["de"] <= 1.0:

            score += 0.5

    # Pledge
    if f["pledge"] is not None:

        if f["pledge"] <= 5:

            score += 1
            reasons.append("Low Pledge")

    return round(score, 1), reasons


# ============================================================
# RISK PENALTY
# ============================================================

def risk_penalty(f):

    penalty = 0
    reasons = []

    market_cap = f["market_cap"]
    price = f["price"]

    # --------------------------------------------------------
    # Very small market cap
    # --------------------------------------------------------

    if market_cap is not None:

        if market_cap < 100:

            penalty += 25
            reasons.append("Very Small Cap")

        elif market_cap < 250:

            penalty += 15
            reasons.append("Small Cap")

        elif market_cap < 500:

            penalty += 7
            reasons.append("Lower Market Cap")

    # --------------------------------------------------------
    # Very low price
    # --------------------------------------------------------

    if price is not None:

        if price < VERY_LOW_PRICE:

            penalty += 20
            reasons.append("Very Low Price")

        elif price < LOW_PRICE:

            penalty += 8
            reasons.append("Low Price")

    # --------------------------------------------------------
    # High debt
    # --------------------------------------------------------

    if f["de"] is not None:

        if f["de"] > 3:

            penalty += 15
            reasons.append("High D/E")

        elif f["de"] > 1:

            penalty += 6
            reasons.append("D/E > 1")

    return penalty, reasons


# ============================================================
# FINAL SCORE
# ============================================================

def final_score(item):

    bscore = buyer_score(item)

    f = item["fundamentals"]

    qscore, qreasons = quality_score(f)

    penalty, preasons = risk_penalty(f)

    # --------------------------------------------------------
    # Buyer = 60%
    # Quality = 30%
    # Risk = 10%
    # --------------------------------------------------------

    quality_normalized = min(
        100,
        (qscore / 7) * 100
    )

    final = (
        bscore * 0.60
        + quality_normalized * 0.30
        - penalty * 0.10
    )

    return {
        "buyer_score": round(bscore, 2),
        "quality_score": qscore,
        "quality_reasons": qreasons,
        "risk_penalty": penalty,
        "risk_reasons": preasons,
        "final_score": round(final, 2),
    }


# ============================================================
# PROCESS
# ============================================================

def process_records(records):

    candidates = []

    for record in records:

        item = boss_filter(record)

        if not item:
            continue

        f = get_fundamentals(
            item["symbol"]
        )

        item["fundamentals"] = f

        scores = final_score(item)

        item.update(scores)

        candidates.append(item)

    return candidates


# ============================================================
# SELECT TOP GEMS
# ============================================================

def select_gems(candidates):

    if not candidates:
        return []

    # --------------------------------------------------------
    # Sort by FINAL SCORE
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: (
            x["final_score"],
            x["buyer_score"],
            x["quality_score"],
            x["ratio"]
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # Do not force 10 stocks
    # Select stocks with reasonable score.
    #
    # Threshold is deliberately moderate to avoid ZERO.
    # --------------------------------------------------------

    good = [
        x for x in candidates
        if x["final_score"] >= 35
    ]

    # If less than 1 passes,
    # take strongest BOSS candidate.
    if not good:

        return candidates[:1]

    return good[:MAX_GEMS]


# ============================================================
# FORMAT
# ============================================================

def fmt_cr(value):

    if value is None:
        return "N/A"

    return f"₹{value:,.0f} Cr"


def fmt_pct(value):

    if value is None:
        return "N/A"

    return f"{value:.1f}%"


def fmt_qty(value):

    return f"{int(value):,}"


# ============================================================
# GEM MESSAGE
# ============================================================

def send_gem(item, rank):

    f = item["fundamentals"]

    risk = ", ".join(
        item["risk_reasons"]
    )

    if not risk:
        risk = "Low Risk Penalty"

    message = f"""
💎 PREOPEN GEM #{rank}

📌 {item['symbol']}

━━━━━━━━━━━━━━━━━━
👥 BUYER STRENGTH
━━━━━━━━━━━━━━━━━━

📈 IEP Change : +{item['change']:.2f}%
⚖️ B/S Ratio  : {item['ratio']:.2f}x
🟢 Buy Qty    : {fmt_qty(item['buy_qty'])}
🔴 Sell Qty   : {fmt_qty(item['sell_qty'])}

⭐ Buyer Score : {item['buyer_score']}/100

━━━━━━━━━━━━━━━━━━
🏦 FUNDAMENTALS
━━━━━━━━━━━━━━━━━━

💰 Market Cap : {fmt_cr(f['market_cap'])}

ROE           : {fmt_pct(f['roe'])}
ROCE          : {fmt_pct(f['roce'])}

D/E           : {
    f"{f['de']:.2f}"
    if f['de'] is not None
    else "N/A"
}

Sales Growth  : {fmt_pct(f['sales_growth'])}
Profit Growth : {fmt_pct(f['profit_growth'])}
Pledge        : {fmt_pct(f['pledge'])}

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

    telegram_send(message)


# ============================================================
# STARTUP
# ============================================================

def startup_message():

    telegram_send(
"""
🔥 PREOPEN GEMS OFFICIAL

📡 PRE-OPEN BUYING SCANNER

✅ Bot is online
✅ Telegram connected
✅ NSE scanner ready

🔒 BOSS FILTER LOCKED
👥 Buyer Priority ACTIVE
🏦 Quality Ranking ACTIVE
🛡️ Risk Protection ACTIVE

⏰ Scanner: 09:00–09:08 AM IST
🔄 Every 30 seconds

📊 Output: 1–10 stocks

💻 Made by Prakash Kanki
"""
    )


# ============================================================
# MAIN
# ============================================================

def main():

    startup_message()

    # --------------------------------------------------------
    # Wait until 09:00
    # --------------------------------------------------------

    while True:

        now = datetime.now(IST)

        if (
            now.hour > 9
            or (
                now.hour == 9
                and now.minute >= 0
            )
        ):
            break

        time.sleep(5)

    telegram_send(
"""
📡 PRE-OPEN SCANNING STARTED

⏰ 09:00–09:08 AM IST
🔄 Every 30 seconds

🔒 BOSS FILTER LOCKED
👥 BUYER PRIORITY ACTIVE
🏦 QUALITY RANKING ACTIVE
🛡️ RISK PROTECTION ACTIVE
"""
    )

    sent_symbols = set()

    latest_candidates = []

    # --------------------------------------------------------
    # SCAN LOOP
    # --------------------------------------------------------

    while True:

        now = datetime.now(IST)

        if (
            now.hour > 9
            or (
                now.hour == 9
                and now.minute > 8
            )
        ):
            break

        records = get_nse_data()

        print(
            f"{now.strftime('%H:%M:%S')} "
            f"NSE Records: {len(records)}"
        )

        candidates = process_records(
            records
        )

        print(
            "BOSS Matches:",
            len(candidates)
        )

        selected = select_gems(
            candidates
        )

        latest_candidates = selected

        # ----------------------------------------------------
        # Send only new symbols
        # ----------------------------------------------------

        for item in selected:

            symbol = item["symbol"]

            if symbol not in sent_symbols:

                rank = len(sent_symbols) + 1

                if rank <= MAX_GEMS:

                    send_gem(
                        item,
                        rank
                    )

                    sent_symbols.add(
                        symbol
                    )

        time.sleep(
            SCAN_INTERVAL
        )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    final_records = get_nse_data()

    final_candidates = process_records(
        final_records
    )

    final_selected = select_gems(
        final_candidates
    )

    message = f"""
🏁 PREOPEN GEMS OFFICIAL

📊 FINAL PRE-OPEN REPORT

⏰ {datetime.now(IST).strftime('%H:%M:%S')} IST

📊 NSE Records   : {len(final_records)}
🔒 BOSS Matches  : {len(final_candidates)}
💎 Selected Gems : {len(final_selected)}

━━━━━━━━━━━━━━━━━━

👥 Buyer Priority : HIGH
🏦 Quality Score   : ACTIVE
🛡️ Risk Protection: ACTIVE

🎯 Maximum Output : {MAX_GEMS}

"""

    if final_selected:

        message += "\n🏆 FINAL SELECTED:\n\n"

        for i, item in enumerate(
            final_selected,
            1
        ):

            message += (
                f"{i}. {item['symbol']} "
                f"• B/S {item['ratio']:.2f}x "
                f"• Buy {int(item['buy_qty']):,} "
                f"• Q {item['quality_score']}/7 "
                f"• Score {item['final_score']:.1f}\n"
            )

    else:

        message += (
            "\n⚠️ No BOSS candidate found.\n"
        )

    message += """
    
━━━━━━━━━━━━━━━━━━

🔒 BOSS FILTER WAS NOT CHANGED.
👥 Strong buyers remain the priority.
🏦 Quality is supportive, not 7/7 mandatory.
🛡️ Penny/low-quality stocks receive penalties.

💻 Made by Prakash Kanki
"""

    telegram_send(message)

    print("PREOPEN SCAN FINISHED")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
