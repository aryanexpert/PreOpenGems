import os
import time
import math
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# PREOPEN GEMS OFFICIAL
# BOSS FILTER = LOCKED
# Buyer Priority + Fundamental Quality Ranking
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

NSE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
NSE_HOME = "https://www.nseindia.com/"

IST = ZoneInfo("Asia/Kolkata")

SCAN_START = (9, 0)
SCAN_END = (9, 8)

SCAN_INTERVAL = 30

# ============================================================
# 🔒 BOSS FILTER - DO NOT CHANGE
# ============================================================

BOSS_MIN_CHANGE = 2.0
BOSS_MIN_RATIO = 3.0
BOSS_MIN_BUY_QTY = 50000
BOSS_SERIES = "EQ"

# ============================================================
# OUTPUT LIMIT
# ============================================================

MIN_GEMS = 1
MAX_GEMS = 10

# ============================================================
# FUNDAMENTAL BASE FILTER
# ============================================================

MIN_MARKET_CAP = 500       # ₹ Crore
MIN_SALES_GROWTH = 0
MIN_PROFIT_GROWTH = 0

# ============================================================
# GLOBAL CACHE
# ============================================================

fundamental_cache = {}

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
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return False

    # Railway variable can contain multiple Chat IDs:
    # 1391074551,7418177111

    chat_ids = [
        x.strip()
        for x in TELEGRAM_CHAT_ID.split(",")
        if x.strip()
    ]

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    success = False

    for chat_id in chat_ids:

        payload = {
            "chat_id": chat_id,
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

                print(
                    f"Telegram sent successfully → {chat_id}"
                )

                success = True

            else:

                print(
                    f"Telegram error → {chat_id}:",
                    r.status_code,
                    r.text[:500]
                )

        except Exception as e:

            print(
                f"Telegram exception → {chat_id}:",
                e
            )

    return success


# ============================================================
# TIME
# ============================================================

def now_ist():

    return datetime.now(IST)


def in_preopen():

    now = now_ist()

    current = (
        now.hour,
        now.minute
    )

    start = SCAN_START
    end = SCAN_END

    return start <= current <= end


# ============================================================
# NSE DATA
# ============================================================

def get_nse_data():

    try:

        # Establish NSE session

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

            print(
                "NSE HTTP:",
                r.status_code
            )

            return []

        data = r.json()

        if isinstance(data, dict):

            records = data.get(
                "data",
                []
            )

        else:

            records = data

        return records

    except Exception as e:

        print(
            "NSE error:",
            e
        )

        return []


# ============================================================
# SAFE NUMBER
# ============================================================

def num(value, default=0):

    try:

        if value is None:
            return default

        if isinstance(value, str):

            value = value.replace(
                ",",
                ""
            ).strip()

            if value in (
                "",
                "-",
                "N/A",
                "NA",
                "None"
            ):

                return default

        return float(value)

    except Exception:

        return default


def clean_value(value):

    try:

        if value is None:
            return None

        if isinstance(value, float):

            if (
                math.isnan(value)
                or math.isinf(value)
            ):

                return None

        return float(value)

    except Exception:

        return None


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
    }

    try:

        ticker = yf.Ticker(
            symbol + ".NS"
        )

        info = ticker.info

        # Market cap

        market_cap = info.get(
            "marketCap"
        )

        if market_cap is not None:

            result["market_cap"] = (
                market_cap / 10000000
            )

        # ROE

        result["roe"] = clean_value(
            info.get(
                "returnOnEquity"
            )
        )

        if result["roe"] is not None:

            result["roe"] *= 100

        # ROCE

        roce = info.get(
            "returnOnCapitalEmployed"
        )

        if roce is not None:

            result["roce"] = clean_value(
                roce
            )

            if (
                result["roce"] is not None
                and result["roce"] < 1
            ):

                result["roce"] *= 100

        # Debt / Equity

        de = info.get(
            "debtToEquity"
        )

        if de is not None:

            result["de"] = clean_value(
                de
            )

            # yfinance sometimes gives
            # percentage-style D/E
            # e.g. 45.35 means 0.4535

            if (
                result["de"] is not None
                and result["de"] > 20
            ):

                result["de"] = (
                    result["de"] / 100
                )

        # Sales growth

        sales_growth = info.get(
            "revenueGrowth"
        )

        if sales_growth is not None:

            result["sales_growth"] = (
                clean_value(
                    sales_growth * 100
                )
            )

        # Profit growth

        profit_growth = info.get(
            "earningsGrowth"
        )

        if profit_growth is not None:

            result["profit_growth"] = (
                clean_value(
                    profit_growth * 100
                )
            )

        # Pledge

        pledge = info.get(
            "pledgeRatio"
        )

        if pledge is not None:

            result["pledge"] = (
                clean_value(
                    pledge * 100
                )
            )

    except Exception as e:

        print(
            f"Fundamental error {symbol}:",
            e
        )

    fundamental_cache[symbol] = result

    return result


# ============================================================
# FUNDAMENTAL QUALITY SCORE
# ============================================================

def quality_score(f):

    score = 0
    passed = []
    weak = []

    # Market Cap

    if f["market_cap"] is not None:

        if f["market_cap"] >= 500:

            score += 1
            passed.append(
                "Market Cap"
            )

    # Sales growth

    if f["sales_growth"] is not None:

        if f["sales_growth"] > 0:

            score += 1
            passed.append(
                "Sales Growth"
            )

    # Profit growth

    if f["profit_growth"] is not None:

        if f["profit_growth"] > 0:

            score += 1
            passed.append(
                "Profit Growth"
            )

    # D/E

    if f["de"] is not None:

        if f["de"] <= 1.0:

            score += 1
            passed.append(
                "D/E"
            )

        else:

            weak.append(
                "D/E high"
            )

    # ROE

    if f["roe"] is not None:

        if f["roe"] >= 12:

            score += 1
            passed.append(
                "ROE"
            )

    # ROCE

    if f["roce"] is not None:

        if f["roce"] >= 15:

            score += 1
            passed.append(
                "ROCE"
            )

    # Pledge

    if f["pledge"] is not None:

        if f["pledge"] <= 5:

            score += 1
            passed.append(
                "Pledge"
            )

    return score, passed, weak


# ============================================================
# BUYER STRENGTH
# ============================================================

def buyer_strength(
    change,
    ratio,
    buy_qty
):

    # --------------------------------------------------------
    # Ratio component
    # Higher buyer/seller imbalance = higher score
    # --------------------------------------------------------

    if ratio <= 3:

        ratio_score = 25

    elif ratio >= 20:

        ratio_score = 100

    else:

        ratio_score = 25 + (
            (ratio - 3) / 17
        ) * 75

    # --------------------------------------------------------
    # Buy quantity component
    # Log scale prevents huge quantity from dominating
    # --------------------------------------------------------

    if buy_qty <= 50000:

        qty_score = 20

    else:

        qty_score = min(
            100,
            20 + (
                math.log10(
                    buy_qty / 50000
                ) * 40
            )
        )

    # --------------------------------------------------------
    # IEP Change
    # --------------------------------------------------------

    change_score = min(
        100,
        max(
            0,
            change * 4
        )
    )

    # --------------------------------------------------------
    # BUYER PRIORITY
    # 70% buyer strength
    # --------------------------------------------------------

    score = (
        ratio_score * 0.50
        + qty_score * 0.30
        + change_score * 0.20
    )

    return round(
        score,
        2
    )


# ============================================================
# FINAL COMBINED SCORE
# ============================================================

def final_score(
    buyer_score,
    quality
):

    # Buyer is the main priority
    # Fundamental quality is secondary

    quality_score_value = (
        quality / 7
    ) * 100

    final = (
        buyer_score * 0.70
        + quality_score_value * 0.30
    )

    return round(
        final,
        2
    )


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

        symbol = metadata.get(
            "symbol"
        )

        series = metadata.get(
            "series"
        )

        iep = num(
            metadata.get(
                "iep"
            )
        )

        change = num(
            metadata.get(
                "pChange"
            )
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

        # 🔒 BOSS FILTER LOCKED

        if series != BOSS_SERIES:

            return None

        if change < BOSS_MIN_CHANGE:

            return None

        if sell_qty <= 0:

            return None

        ratio = (
            buy_qty / sell_qty
        )

        if ratio < BOSS_MIN_RATIO:

            return None

        if buy_qty < BOSS_MIN_BUY_QTY:

            return None

        return {
            "symbol": symbol,
            "series": series,
            "iep": iep,
            "change": change,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "ratio": ratio,
        }

    except Exception:

        return None


# ============================================================
# FORMAT
# ============================================================

def fmt_money(value):

    if value is None:

        return "N/A"

    if value >= 1000:

        return f"₹{value:,.0f} Cr"

    return f"₹{value:,.0f} Cr"


def fmt_pct(value):

    if value is None:

        return "N/A"

    return f"{value:.1f}%"


def fmt_number(value):

    return f"{int(value):,}"


# ============================================================
# SCAN
# ============================================================

def scan_once():

    records = get_nse_data()

    print(
        "NSE records:",
        len(records)
    )

    boss_matches = []

    for record in records:

        item = boss_filter(
            record
        )

        if item:

            boss_matches.append(
                item
            )

    print(
        "BOSS matches:",
        len(boss_matches)
    )

    candidates = []

    for item in boss_matches:

        symbol = item["symbol"]

        f = get_fundamentals(
            symbol
        )

        qscore, passed, weak = (
            quality_score(f)
        )

        bscore = buyer_strength(
            item["change"],
            item["ratio"],
            item["buy_qty"]
        )

        fscore = final_score(
            bscore,
            qscore
        )

        # Basic quality preference

        quality_ok = False

        if (
            f["market_cap"] is not None
            and f["market_cap"]
            >= MIN_MARKET_CAP
        ):

            quality_ok = True

        if (
            f["sales_growth"] is not None
            and f["sales_growth"]
            > MIN_SALES_GROWTH
        ):

            quality_ok = True

        if (
            f["profit_growth"] is not None
            and f["profit_growth"]
            > MIN_PROFIT_GROWTH
        ):

            quality_ok = True

        item.update({

            "fundamentals": f,

            "quality": qscore,

            "buyer_score": bscore,

            "final_score": fscore,

            "passed": passed,

            "weak": weak,

            "quality_ok": quality_ok,

        })

        candidates.append(
            item
        )

    # --------------------------------------------------------
    # First preference:
    # Fundamental-supported candidates
    # --------------------------------------------------------

    preferred = [
        x for x in candidates
        if x["quality_ok"]
    ]

    # --------------------------------------------------------
    # Sort:
    # Buyer strength first
    # Final score second
    # --------------------------------------------------------

    preferred.sort(
        key=lambda x: (
            x["buyer_score"],
            x["final_score"],
            x["quality"]
        ),
        reverse=True
    )

    selected = preferred[
        :MAX_GEMS
    ]

    # --------------------------------------------------------
    # FALLBACK
    # If no quality-supported stock exists,
    # take strongest BOSS stock.
    # --------------------------------------------------------

    fallback = False

    if (
        len(selected) == 0
        and candidates
    ):

        candidates.sort(
            key=lambda x: (
                x["buyer_score"],
                x["final_score"]
            ),
            reverse=True
        )

        selected = candidates[
            :1
        ]

        fallback = True

    return {

        "records": len(records),

        "boss": boss_matches,

        "candidates": candidates,

        "selected": selected,

        "fallback": fallback,

    }


# ============================================================
# TELEGRAM GEM MESSAGE
# ============================================================

def send_gem_message(
    item,
    fallback=False
):

    f = item[
        "fundamentals"
    ]

    label = "💎 GEM"

    if fallback:

        label = (
            "⚠️ BOSS FALLBACK GEM"
        )

    message = f"""
{label}

📌 {item['symbol']}

🔥 BUYER PRIORITY

📈 IEP Change : +{item['change']:.2f}%
⚖️ B/S Ratio  : {item['ratio']:.2f}x
🟢 Buy Qty    : {fmt_number(item['buy_qty'])}
🔴 Sell Qty   : {fmt_number(item['sell_qty'])}

━━━━━━━━━━━━━━━━━━

⭐ BUYER SCORE : {item['buyer_score']:.1f}/100
⭐ QUALITY     : {item['quality']}/7
🏆 FINAL SCORE: {item['final_score']}/100

━━━━━━━━━━━━━━━━━━

💰 Market Cap : {fmt_money(f['market_cap'])}
ROE           : {fmt_pct(f['roe'])}
ROCE          : {fmt_pct(f['roce'])}
D/E           : {fmt_pct(f['de']) if f['de'] is not None else 'N/A'}
Sales Growth  : {fmt_pct(f['sales_growth'])}
Profit Growth : {fmt_pct(f['profit_growth'])}
Pledge        : {fmt_pct(f['pledge'])}

━━━━━━━━━━━━━━━━━━

🔒 BOSS FILTER: PASSED
👥 BUYERS ARE PRIORITY

💻 Made by Prakash Kanki
"""

    telegram_send(
        message
    )


# ============================================================
# STARTUP
# ============================================================

def send_startup():

    message = """
🔥 PREOPEN GEMS OFFICIAL

📡 PRE-OPEN BUYING SCANNER

✅ Bot is online
✅ Telegram connected
✅ NSE scanner ready
🔒 BOSS filter loaded
⭐ Buyer Priority loaded
💎 Quality Ranking loaded

⏰ Scanner: 09:00–09:08 AM IST
🔄 Every 30 seconds

👥 Buyer Priority: 70%
🏦 Fundamental Quality: 30%

📊 Output: Minimum 1 / Maximum 10

💻 Made by Prakash Kanki
"""

    telegram_send(
        message
    )


# ============================================================
# MAIN
# ============================================================

def main():

    send_startup()

    print(
        "PREOPEN GEMS STARTED"
    )

    sent_symbols = set()

    # Wait until 9:00

    while True:

        now = now_ist()

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
"""
    )

    while True:

        now = now_ist()

        # Stop after 09:08

        if (
            now.hour > 9
            or (
                now.hour == 9
                and now.minute > 8
            )
        ):

            break

        result = scan_once()

        selected = result[
            "selected"
        ]

        for item in selected:

            symbol = item[
                "symbol"
            ]

            # Send each symbol only once

            if symbol not in sent_symbols:

                send_gem_message(
                    item,
                    result["fallback"]
                )

                sent_symbols.add(
                    symbol
                )

        time.sleep(
            SCAN_INTERVAL
        )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    result = scan_once()

    selected = result[
        "selected"
    ]

    final_message = f"""
🏁 PREOPEN GEMS OFFICIAL

📊 FINAL PRE-OPEN REPORT

⏰ {now_ist().strftime('%H:%M:%S')} AM IST

📊 NSE Records      : {result['records']}
🔒 BOSS Matches     : {len(result['boss'])}
💎 Selected Gems    : {len(selected)}

👥 Buyer Priority   : 70%
🏦 Quality Priority : 30%

🎯 Maximum Output   : {MAX_GEMS}

"""

    if selected:

        final_message += (
            "\n🏆 SELECTED STOCKS:\n\n"
        )

        for i, item in enumerate(
            selected,
            1
        ):

            final_message += (
                f"{i}. {item['symbol']} "
                f"• B/S {item['ratio']:.2f}x "
                f"• Buy {item['buy_qty']:,.0f} "
                f"• Quality {item['quality']}/7\n"
            )

    else:

        final_message += (
            "\n⚠️ No suitable GEM found today.\n"
        )

    final_message += (
        "\n🔒 BOSS FILTER WAS NOT CHANGED.\n"
        "👥 Buyer strength was given highest priority.\n"
        "\n💻 Made by Prakash Kanki"
    )

    telegram_send(
        final_message
    )

    print(
        "SCAN FINISHED"
    )


if __name__ == "__main__":

    main()
