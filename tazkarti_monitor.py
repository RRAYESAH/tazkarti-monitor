#!/usr/bin/env python3
"""
Tazkarti monitor -> Telegram

بيراقب قايمة الماتشات في تذكرتي، وأول ما ماتش جديد يتضاف يبعتلك رسالة على تليجرام.

التشغيل:
    pip install requests
    export TELEGRAM_BOT_TOKEN="123456:ABC..."
    export TELEGRAM_CHAT_ID="123456789"
    python tazkarti_monitor.py

متغيرات اختيارية:
    TAZKARTI_API_URL   رابط الـ JSON اللي الموقع بيجيب منه الماتشات (شوف الملاحظة تحت)
    CHECK_INTERVAL     كل كام ثانية يفحص (الافتراضي 60)
    NOTIFY_ON_CHANGE   لو "1" يبعتلك كمان لما بيانات ماتش موجود تتغير (مثلاً فتح الحجز)

ملاحظة مهمة:
    موقع تذكرتي Single Page App، يعني الـ HTML نفسه فاضي والماتشات بتتحمل من API.
    لو الرابط الافتراضي تحت مشتغلش، افتح الموقع في كروم -> F12 -> Network -> Fetch/XHR
    -> اعمل Refresh لصفحة الماتشات -> دوّر على الطلب اللي راجع بقايمة الماتشات
    -> Copy link address -> حطه في TAZKARTI_API_URL.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
API_URL = os.environ.get(
    "TAZKARTI_API_URL", "https://tazkarti.com/data/matches-list-json.json"
)
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
NOTIFY_ON_CHANGE = os.environ.get("NOTIFY_ON_CHANGE", "0") == "1"
STATE_FILE = Path(os.environ.get("STATE_FILE", "tazkarti_state.json"))
SITE_URL = "https://www.tazkarti.com/#/matches"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ar,en;q=0.9",
    "Referer": "https://www.tazkarti.com/",
}


def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()


def fetch_matches():
    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    # الـ JSON ممكن يكون list مباشرة أو object جواه list
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    raise ValueError("مقدرتش ألاقي قايمة ماتشات في الرد، راجع TAZKARTI_API_URL")


def match_id(item):
    for key in ("matchId", "MatchId", "matchID", "id", "Id", "ID"):
        if key in item and item[key] not in (None, ""):
            return str(item[key])
    return hashlib.md5(
        json.dumps(item, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def fingerprint(item):
    return hashlib.md5(
        json.dumps(item, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def pick(item, *keys):
    for k in keys:
        if item.get(k) not in (None, ""):
            return item[k]
    return None


def describe(item):
    home = pick(item, "teamName1", "homeTeamName", "homeTeam", "team1", "teamNameAr1")
    away = pick(item, "teamName2", "awayTeamName", "awayTeam", "team2", "teamNameAr2")
    date = pick(item, "matchDate", "date", "matchDateTime", "startDate")
    stadium = pick(item, "stadiumName", "stadium", "venue")
    league = pick(item, "tournamentName", "championshipName", "league", "competition")

    if home and away:
        title = f"{home} × {away}"
    else:
        title = pick(item, "matchName", "name", "title") or "ماتش جديد"

    lines = [f"🎟 {title}"]
    if league:
        lines.append(f"🏆 {league}")
    if date:
        lines.append(f"📅 {date}")
    if stadium:
        lines.append(f"🏟 {stadium}")
    return "\n".join(lines)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def check_once(state):
    matches = fetch_matches()
    current = {match_id(m): fingerprint(m) for m in matches}
    by_id = {match_id(m): m for m in matches}

    # أول تشغيل: نسجل الوضع الحالي من غير ما نبعت حاجة
    if state is None:
        log(f"أول تشغيل: تم تسجيل {len(current)} ماتش كنقطة بداية.")
        return current

    new_ids = [i for i in current if i not in state]
    for i in new_ids:
        send_telegram("🆕 ماتش جديد على تذكرتي\n\n" + describe(by_id[i]) + f"\n\n{SITE_URL}")
        log(f"اتبعت إشعار لماتش جديد: {i}")

    if NOTIFY_ON_CHANGE:
        for i, fp in current.items():
            if i in state and state[i] != fp:
                send_telegram(
                    "🔄 تحديث على ماتش موجود\n\n" + describe(by_id[i]) + f"\n\n{SITE_URL}"
                )
                log(f"اتبعت إشعار تحديث: {i}")

    return current


def main():
    if not BOT_TOKEN or not CHAT_ID:
        sys.exit("لازم تحدد TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID")

    state = load_state()

    # وضع التشغيل مرة واحدة (بيستخدمه GitHub Actions): يفحص مرة ويقفل
    if os.environ.get("RUN_ONCE") == "1":
        state = check_once(state)
        save_state(state)
        return

    send_telegram("✅ المراقب اشتغل، هبعتلك أول ما ماتش جديد يتضاف على تذكرتي.")
    log(f"بدأت المراقبة كل {INTERVAL} ثانية")

    while True:
        try:
            state = check_once(state)
            save_state(state)
        except Exception as e:  # نكمل حتى لو حصل خطأ مؤقت
            log(f"خطأ: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
