"""
================================================================
 STOCK ALERT BOT - ALL IN ONE  (Railway: python bot.py)
================================================================
2 bots ek hi process me chalte hain:

  1) PRE-OPEN GEMS
     09:00-09:08 AM IST  -> NSE pre-open market scan
     09:10 AM IST         -> Telegram par final list (1-10 stocks)

  2) INTRADAY SURGE SCANNER
     09:30 AM - 03:30 PM IST -> Nifty Midcap150 + Smallcap250
     Jab kisi stock ka volume + buyers achanak badhe -> alert
     Max 10 alerts/din, har stock sirf ek baar/din

Env variables (Railway -> Variables):
  TELEGRAM_BOT_TOKEN = <bot father se mila token>
  TELEGRAM_CHAT_ID   = 7418177111,1391074551   (comma se multiple)

requirements.txt:
  requests
  yfinance
================================================================
"""

import os
import time
import math
import threading
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer


# ================================================================
# SHARED CONFIG
# ================================================================

IST = ZoneInfo("Asia/Kolkata")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

_raw_chat_ids = os.getenv("TELEGRAM_CHAT_ID", "7418177111,1391074551")
CHAT_IDS = []
for part in _raw_chat_ids.replace(";", ",").split(","):
    part = part.strip()
    if part:
        CHAT_IDS.append(part)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def telegram_send(text):
    """Sabhi configured chat IDs par message bhejta hai."""
    if not BOT_TOKEN or not CHAT_IDS:
        print("Telegram credentials missing", flush=True)
        return False

    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    ok_any = False

    for chat_id in CHAT_IDS:
        try:
            resp = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                ok_any = True
            else:
                print("Telegram error [" + chat_id + "]: " +
                      str(resp.status_code) + " " + resp.text[:300], flush=True)
        except Exception as err:
            print("Telegram exception [" + chat_id + "]: " + str(err), flush=True)
        time.sleep(0.3)

    return ok_any


def safe_num(value, default=0.0):
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

