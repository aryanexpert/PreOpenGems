PREOPEN GEMS + INTRADAY SURGE BOT  (v4 - self-scheduling)

Run:      python bot.py
Needs:    pip install requests yfinance
Env vars: TELEGRAM_BOT_TOKEN = <bot token>
          TELEGRAM_CHAT_ID   = 7418177111,1391074551

Koi cron / Railway / hosting service nahi chahiye.
Script khud IST clock dekhkar 09:00 pre-open aur 09:15-15:30 intraday chalati hai.
Wall-clock based hai: laptop/phone sleep se wake ho ya bot restart ho, wapas sync ho jata hai.
"""
import os
import sys
import time
import math
import json
import logging
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================
IST = ZoneInfo("Asia/Kolkata")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_IDS = [x.strip() for x in
            os.getenv("TELEGRAM_CHAT_ID", "7418177111,1391074551").replace(";", ",").split(",")
            if x.strip()]
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.json")

# ---- Pre-open ----
SCAN_INTERVAL = 30
BOSS_MIN_CHANGE = 2.0
BOSS_MIN_RATIO = 3.0
BOSS_MIN_BUY_QTY = 50000
BOSS_SERIES = "EQ"
MIN_GEMS, MAX_GEMS, MIN_FINAL_SCORE = 1, 10, 35
HARD_MIN_PRICE = 50
CIRCUIT_BUFFER = 0.8
LOW_PRICE, VERY_LOW_PRICE = 50, 20

# ---- Intraday ----
INDEXES = ["NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]
POLL_SEC = 180
WARMUP_UNTIL = (9, 30)
MARKET_END = (15, 30)
MIN_SAMPLES = 3                # itne intervals ke baad hi surge check
VOL_RATIO = 3.0                # interval volume >= 3x recent average
PRICE_MIN_MOVE = 0.5           # day change >= +0.5%
BUYER_MIN_RATIO = 1.5          # buy qty / sell qty
MIN_INTERVAL_VALUE = 2_000_000  # interval turnover >= 20 lakh (noise filter)
MAX_ALERTS = 10

NSE_HOME = "https://www.nseindia.com/"
PRE_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol="
INDEX_URL = "https://www.nseindia.com/api/equity-stockIndices?index="

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    datefmt="%H:%M:%S", stream=sys.stdout)
log = logging.info


# ============================================================
# TIME + STATE
# ============================================================
def now():
    return datetime.now(IST)


def hm():
    n = now()
    return (n.hour, n.minute)


def wait_until(h, m):
    while hm() < (h, m):
        time.sleep(2)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log(f"state save error: {e}")


# ============================================================
# TELEGRAM (retry + rate-limit safe)
# ============================================================
def tg(text):
    if not TOKEN or not CHAT_IDS:
        log("Telegram credentials missing")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    ok = False
    for i in range(0, len(text), 4000):
        chunk = text[i:i + 4000]
        for cid in CHAT_IDS:
            for _ in range(3):
                try:
                    r = requests.post(url, data={"chat_id": cid, "text": chunk,
                                                 "disable_web_page_preview": True}, timeout=15)
                    if r.status_code == 200:
                        ok = True
                        break
                    if r.status_code == 429:
                        wait = r.json().get("parameters", {}).get("retry_after", 3)
                        time.sleep(wait + 1)
                        continue
                    log(f"Telegram [{cid}] {r.status_code} {r.text[:200]}")
                    break
                except Exception as e:
                    log(f"Telegram [{cid}] exception: {e}")
                    time.sleep(2)
            time.sleep(0.3)
    return ok


_last_err = 0


def notify_error(e):
    global _last_err
    log(f"ERROR: {e!r}")
    if time.time() - _last_err > 600:      # max 1 error msg / 10 min
        _last_err = time.time()
        tg(f"⚠️ Bot error (auto-recovering): {e}")


# ============================================================
# NSE CLIENT (cookie refresh + retry)
# ============================================================
class NSE:
    HEADERS = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_HOME,
        "Connection": "keep-alive",
    }

    def __init__(self):
        self.s = requests.Session()
        self.warm_at = 0

    def warm(self):
        try:
            self.s.get(NSE_HOME, headers=self.HEADERS, timeout=10)
        except Exception as e:
            log(f"NSE warm error: {e}")
        self.warm_at = time.time()

    def get(self, url, tries=3):
        if time.time() - self.warm_at > 240:
            self.warm()
        for i in range(tries):
            try:
                r = self.s.get(url, headers=self.HEADERS, timeout=15)
                if r.status_code == 200:
                    return r.json()
                log(f"NSE HTTP {r.status_code}")
                if r.status_code in (401, 403):
                    self.s.cookies.clear()
                    self.warm()
            except Exception as e:
                log(f"NSE error: {e}")
            time.sleep(2 * (i + 1))
        return None


nse = NSE()


# ============================================================
# HELPERS
# ============================================================
def num(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v in ("", "-", "N/A", "NA", "None"):
                return default
        return float(v)
    except Exception:
        return default


def clean(v):
    try:
        if v is None:
            return None
        v = float(v)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return None


# ============================================================
# PART 1: PRE-OPEN
# ============================================================
fund_cache, band_cache = {}, {}


def get_fundamentals(sym):
    if sym in fund_cache:
        return fund_cache[sym]
    res = {"market_cap": None, "roe": None, "roce": None, "de": None,
           "sales_growth": None, "profit_growth": None, "pledge": None, "price": None}
    try:
        info = yf.Ticker(sym + ".NS").info
        mc = clean(info.get("marketCap"))
        if mc is not None:
            res["market_cap"] = mc / 1e7
        p = clean(info.get("currentPrice"))
        res["price"] = p if p is not None else clean(info.get("regularMarketPrice"))
        roe = clean(info.get("returnOnEquity"))
        if roe is not None:
            res["roe"] = roe * 100
        roce = clean(info.get("returnOnCapitalEmployed"))
        if roce is not None:
            res["roce"] = roce * 100 if roce < 1 else roce
        de = clean(info.get("debtToEquity"))
        if de is not None:
            res["de"] = de / 100 if de > 20 else de
        sg = clean(info.get("revenueGrowth"))
        if sg is not None:
            res["sales_growth"] = sg * 100
        pg = clean(info.get("earningsGrowth"))
        if pg is not None:
            res["profit_growth"] = pg * 100
        pl = clean(info.get("pledgeRatio"))
        if pl is not None:
            res["pledge"] = pl * 100
    except Exception as e:
        log(f"Fundamental error {sym}: {e}")
    fund_cache[sym] = res
    return res


def price_band(sym):
    if sym in band_cache:
        return band_cache[sym]
    band = None
    d = nse.get(QUOTE_URL + sym, tries=1)
    try:
        b = str(d["priceInfo"]["pPriceBand"]).strip()
        if b.replace(".", "").isdigit():
            band = float(b)
    except Exception:
        pass
    band_cache[sym] = band
    time.sleep(0.3)
    return band


def preopen_records():
    d = nse.get(PRE_URL)
    if not d:
        return []
    return d.get("data", []) if isinstance(d, dict) else d


def boss_filter(rec):
    try:
        meta, detail = rec.get("metadata", {}), rec.get("detail", {})
        sym, series = meta.get("symbol"), meta.get("series")
        change, iep = num(meta.get("pChange")), num(meta.get("iep"))
        pre = detail.get("preOpenMarket", {})
        buy, sell = num(pre.get("totalBuyQuantity")), num(pre.get("totalSellQuantity"))
        if not sym or series != BOSS_SERIES:
            return None
        if change < BOSS_MIN_CHANGE or buy < BOSS_MIN_BUY_QTY or sell <= 0:
            return None
        ratio = buy / sell
        if ratio < BOSS_MIN_RATIO:
            return None
        return {"symbol": sym, "change": change, "iep": iep,
                "buy_qty": buy, "sell_qty": sell, "ratio": ratio}
    except Exception:
        return None


def boss_matches(records):
    out = [x for x in (boss_filter(r) for r in records) if x]
    for x in out:
        x["buyer_score"] = buyer_score(x)
    return out


def buyer_score(it):
    ratio, buy, change = it["ratio"], it["buy_qty"], it["change"]
    if ratio <= 3:
        rs = 25
    elif ratio >= 25:
        rs = 100
    else:
        rs = 25 + ((ratio - 3) / 22) * 75
    qs = 20 if buy <= 50000 else min(100, 20 + math.log10(buy / 50000) * 45)
    cs = min(100, max(0, change * 4))
    return round(rs * 0.50 + qs * 0.30 + cs * 0.20, 2)


def quality_score(f):
    s = 0
    if f["market_cap"] is not None:
        s += 2 if f["market_cap"] >= 1000 else (1 if f["market_cap"] >= 500 else 0)
    for k in ("sales_growth", "profit_growth"):
        if f[k] is not None:
            s += 1 if f[k] >= 10 else (0.5 if f[k] > 0 else 0)
    if f["roe"] is not None and f["roe"] >= 12:
        s += 1
    if f["roce"] is not None and f["roce"] >= 15:
        s += 1
    if f["de"] is not None:
        s += 1 if f["de"] <= 0.5 else (0.5 if f["de"] <= 1 else 0)
    if f["pledge"] is not None and f["pledge"] <= 5:
        s += 1
    return round(s, 1)


def risk_penalty(f, iep):
    p, reasons = 0, []
    mc = f["market_cap"]
    price = f["price"] if f["price"] is not None else iep
    if mc is not None:
        if mc < 100:
            p += 25; reasons.append("Very Small Cap")
        elif mc < 250:
            p += 15; reasons.append("Small Cap")
        elif mc < 500:
            p += 7; reasons.append("Lower Market Cap")
    if price is not None:
        if price < VERY_LOW_PRICE:
            p += 20; reasons.append("Very Low Price")
        elif price < LOW_PRICE:
            p += 8; reasons.append("Low Price")
    if f["de"] is not None:
        if f["de"] > 3:
            p += 15; reasons.append("High D/E")
        elif f["de"] > 1:
            p += 6; reasons.append("D/E > 1")
    return p, reasons


def score_item(it):
    f = it["fundamentals"]
    q = quality_score(f)
    pen, reasons = risk_penalty(f, it["iep"])
    final = it["buyer_score"] * 0.60 + min(100, q / 7 * 100) * 0.30 - pen * 0.10
    it.update({"quality_score": q, "risk_reasons": reasons, "final_score": round(final, 2)})


def near_circuit(it):
    it["band"] = price_band(it["symbol"])
    return bool(it["band"]) and it["change"] >= it["band"] * CIRCUIT_BUFFER


def is_penny(it):
    price = it["fundamentals"]["price"] or it["iep"]
    return bool(price) and price < HARD_MIN_PRICE


def select_gems(cands):
    """Min 1, Max 10. Circuit/penny hatate hain, par 0 kabhi nahi."""
    if not cands:
        return []
    # Slow calls (yfinance + band) sirf top 25 buyer-score par
    top = sorted(cands, key=lambda x: (x["buyer_score"], x["ratio"]), reverse=True)[:25]
    for c in top:
        c["fundamentals"] = get_fundamentals(c["symbol"])
        score_item(c)
        c["near_circuit"] = near_circuit(c)
        c["penny"] = is_penny(c)
    top.sort(key=lambda x: (x["final_score"], x["buyer_score"], x["quality_score"], x["ratio"]),
             reverse=True)

    picks = [c for c in top if not c["near_circuit"] and not c["penny"]
             and c["final_score"] >= MIN_FINAL_SCORE]
    if len(picks) < MIN_GEMS:
        picks = [c for c in top if not c["near_circuit"] and not c["penny"]]
    if len(picks) < MIN_GEMS:
        picks = [c for c in top if not c["near_circuit"]]
    if len(picks) < MIN_GEMS:
        picks = top[:1]
    return picks[:MAX_GEMS]


def fmt_cr(v):
    return "N/A" if v is None else f"₹{v:,.0f} Cr"


def fmt_pct(v):
    return "N/A" if v is None else f"{v:.1f}%"


def send_gem(it, rank):
    f = it["fundamentals"]
    risk = list(it["risk_reasons"])
    if it.get("near_circuit"):
        risk.append("⚠️ Circuit ke paas")
    if it.get("penny"):
        risk.append("⚠️ Penny price")
    risk_txt = ", ".join(risk) if risk else "Low Risk Penalty"
    de = f"{f['de']:.2f}" if f["de"] is not None else "N/A"
    band = f"{it['band']:.0f}%" if it.get("band") else "N/A"
    tg(f"""
💎 PREOPEN GEM #{rank}

📌 {it['symbol']}  (₹{it['iep']:.2f})

━━━━━━━━━━━━━━━━━━
👥 BUYER STRENGTH
━━━━━━━━━━━━━━━━━━

📈 IEP Change : +{it['change']:.2f}%
🚧 Price Band : {band}
⚖️ B/S Ratio  : {it['ratio']:.2f}x
🟢 Buy Qty    : {int(it['buy_qty']):,}
🔴 Sell Qty   : {int(it['sell_qty']):,}

⭐ Buyer Score : {it['buyer_score']}/100

━━━━━━━━━━━━━━━━━━
🏦 FUNDAMENTALS
━━━━━━━━━━━━━━━━━━

💰 Market Cap : {fmt_cr(f['market_cap'])}

ROE           : {fmt_pct(f['roe'])}
ROCE          : {fmt_pct(f['roce'])}
D/E           : {de}
Sales Growth  : {fmt_pct(f['sales_growth'])}
Profit Growth : {fmt_pct(f['profit_growth'])}
Pledge        : {fmt_pct(f['pledge'])}

⭐ Quality     : {it['quality_score']}/7

━━━━━━━━━━━━━━━━━━
🛡️ RISK CHECK
━━━━━━━━━━━━━━━━━━

{risk_txt}

🏆 FINAL SCORE : {it['final_score']}/100

🔒 BOSS FILTER : PASSED
👥 BUYER PRIORITY : HIGH

💻 Made by Prakash Kanki
""")
    time.sleep(0.5)


def send_summary(gems):
    lines = [f"📋 PREOPEN GEMS SUMMARY ({len(gems)} stocks)\n"]
    for i, g in enumerate(gems, 1):
        lines.append(f"{i}. {g['symbol']}  +{g['change']:.1f}%  {g['ratio']:.1f}x  "
                     f"Score {g['final_score']}")
    lines.append("\n⚠️ Sirf screening hai, advice nahi. Stoploss zaroor rakhein.")
    tg("\n".join(lines))


def run_preopen(state):
    tg("📡 PRE-OPEN SCANNING STARTED\n⏰ 09:00–09:08 AM IST\n🔄 Every 30 seconds")
    latest, got_data = [], False

    # 09:00-09:08: sirf latest BOSS matches yaad rakho (cheap, spam nahi)
    while hm() <= (9, 8):
        recs = preopen_records()
        log(f"NSE pre-open records: {len(recs)}")
        if recs:
            got_data = True
            c = boss_matches(recs)
            if c:
                latest = c
        time.sleep(SCAN_INTERVAL)

    # 09:10: final list
    wait_until(9, 10)
    recs = preopen_records()
    if recs:
        got_data = True
    final = (boss_matches(recs) if recs else []) or latest

    if not got_data:
        tg("⚠️ NSE se pre-open data nahi mila (holiday ya NSE ne block kiya).")
        state["pre_done"] = str(now().date()); save_state(state)
        return
    state["pre_done"] = str(now().date()); save_state(state)   # double-send se bachne ke liye

    if not final:
        tg("📭 Aaj BOSS filter (2%+, 3x buyers, 50k qty) me koi stock match nahi hua.")
        return
    gems = select_gems(final)
    for i, g in enumerate(gems, 1):
        send_gem(g, i)
    send_summary(gems)
    fund_cache.clear(); band_cache.clear()


# ============================================================
# PART 2: INTRADAY SURGE (09:15 - 15:30)
# ============================================================
def fetch_universe():
    rows = {}
    for idx in INDEXES:
        d = nse.get(INDEX_URL + quote(idx), tries=2)
        for r in (d or {}).get("data", []):
            sym = r.get("symbol") or ""
            if sym and "NIFTY" not in sym.upper():
                rows[sym] = r
    return list(rows.values())


def scan_once(rows, hist, alerted, sent):
    warm = hm() < WARMUP_UNTIL
    surges = []
    for r in rows:
        sym = r.get("symbol")
        vol, px, chg = num(r.get("totalTradedVolume")), num(r.get("lastPrice")), num(r.get("pChange"))
        if not sym or px <= 0:
            continue
        h = hist.setdefault(sym, {"vol": None, "px": None, "ints": []})
        if h["vol"] is not None and vol >= h["vol"]:
            iv = vol - h["vol"]
            recent = h["ints"][-10:]
            if not warm and sym not in alerted and len(recent) >= MIN_SAMPLES:
                avg = sum(recent) / len(recent)
                if (avg > 0 and iv >= VOL_RATIO * avg and iv * px >= MIN_INTERVAL_VALUE
                        and chg >= PRICE_MIN_MOVE and px >= h["px"]):
                    surges.append({"symbol": sym, "px": px, "chg": chg, "iv": iv, "vr": iv / avg})
            h["ints"].append(iv)
        h["vol"], h["px"] = vol, px

    new = 0
    surges.sort(key=lambda s: s["vr"], reverse=True)
    for s in surges[:8]:
        if sent + new >= MAX_ALERTS:
            break
        d = nse.get(QUOTE_URL + s["symbol"], tries=1) or {}
        ob = d.get("marketDeptOrderBook", {}) if isinstance(d, dict) else {}
        buy, sell = num(ob.get("totalBuyQuantity")), num(ob.get("totalSellQuantity"))
        ratio = buy / sell if sell > 0 else 0
        if ratio >= BUYER_MIN_RATIO:
            new += 1
            alerted.add(s["symbol"])
            tg(f"""🚀 SURGE ALERT #{sent + new}

📌 {s['symbol']}  (₹{s['px']:.2f})
📈 Day Change : +{s['chg']:.2f}%
🔊 Volume Surge : {s['vr']:.1f}x  ({int(s['iv']):,} shares in last {POLL_SEC // 60} min)
🟢 Buy Qty  : {int(buy):,}
🔴 Sell Qty : {int(sell):,}
⚖️ Buy/Sell : {ratio:.2f}x

⚠️ Sirf screening hai, advice nahi. Stoploss zaroor rakhein.
💻 Made by Prakash Kanki""")
        time.sleep(0.4)
    return new


def run_intraday(state):
    hist, alerted, sent, fails = {}, set(), 0, 0
    tg("📊 INTRADAY SURGE SCANNER ON\n⏰ 09:15–15:30 IST | har 3 min\n"
       "🕘 Alerts 09:30 ke baad (pehle data collect)")
    while hm() < MARKET_END:
        t0 = time.time()
        try:
            rows = fetch_universe()
            if not rows:
                fails += 1
                if fails >= 5 and not hist:
                    log("Intraday data nahi (holiday/blocked) - aaj skip")
                    break
            else:
                fails = 0
                sent += scan_once(rows, hist, alerted, sent)
        except Exception as e:
            notify_error(e)
        time.sleep(max(5, POLL_SEC - (time.time() - t0)))
    state["intra_done"] = str(now().date()); save_state(state)
    if hist:
        tg(f"📴 Intraday scanner band. Aaj ke alerts: {sent}")


# ============================================================
# MAIN LOOP  (koi cron nahi - khud schedule karta hai)
# ============================================================
def main():
    state = load_state()
    log("Bot started")
    while True:
        try:
            n = now()
            today = str(n.date())

            if state.get("hello") != today:
                state["hello"] = today; save_state(state)
                tg("🔥 PREOPEN GEMS + INTRADAY BOT ONLINE\n\n"
                   "⏰ Pre-open: 09:00–09:08 scan, 09:10 final list\n"
                   "📊 Intraday: 09:15–15:30 surge alerts (max 10)\n"
                   "🗓 Mon–Fri auto | koi cron nahi\n\n💻 Made by Prakash Kanki")

            if n.weekday() < 5:
                if state.get("pre_done") != today and (9, 0) <= hm() < (9, 14):
                    run_preopen(state)
                if state.get("intra_done")
