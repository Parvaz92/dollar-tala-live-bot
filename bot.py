"""
ربات پست اتوماتیک قیمت دلار، طلا، سکه و تتر در کانال تلگرام
Dollar / Gold price auto-poster for a Telegram channel.

- هر POST_INTERVAL_MINUTES دقیقه یک پست منظم، اگر قیمتی عوض شده باشد (به جز ساعات سکوت شب)
- پست فوری وقتی قیمتی بیشتر از ALERT_PERCENT درصد نسبت به آخرین پست تغییر کند
"""

import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------- تنظیمات ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "@dollar_tala_live").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "@dollar_tala_live_bot").strip()
# وقتی بخش هشدار شخصی ساخته شد، این را 1 کنید تا لینک ربات زیر پست‌ها بیاید
SHOW_BOT_LINK = os.getenv("SHOW_BOT_LINK", "0").strip() == "1"

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
# هر چند دقیقه یک پست منظم (فقط اگر قیمتی عوض شده باشد)
POST_INTERVAL_MINUTES = int(os.getenv("POST_INTERVAL_MINUTES", "15"))
ALERT_PERCENT = float(os.getenv("ALERT_PERCENT", "1.0"))
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))
QUIET_START_HOUR = int(os.getenv("QUIET_START_HOUR", "0"))
QUIET_END_HOUR = int(os.getenv("QUIET_END_HOUR", "8"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tehran"))

# نماد هر قیمت در api.priceto.day : عنوان فارسی
# لیست همه‌ی نمادها: https://api.priceto.day/v1/symbols
ITEMS = {
    os.getenv("KEY_USD", "usd"): "💵 دلار",
    os.getenv("KEY_EUR", "euro"): "💶 یورو",
    os.getenv("KEY_USDT", "tether"): "🪙 تتر",
    os.getenv("KEY_GOLD18", "gold-18k"): "🟡 طلای ۱۸ عیار (گرم)",
    os.getenv("KEY_SEKKEH", "coin-emami"): "🏅 سکه امامی",
}

# منبع قیمت: رایگان، بدون نیاز به کلید، از خارج ایران هم در دسترس است
# قیمت‌ها به ریال برگردانده می‌شوند و ربات به تومان تبدیل می‌کند
API_BASE = os.getenv("API_BASE", "https://api.priceto.day/v1/latest/irr").rstrip("/")
HEADERS = {"User-Agent": "dollar-tala-live-bot", "Accept": "application/json"}

# قیمت لحظه‌ای تتر از صرافی والکس (به تومان)
WALLEX_URL = "https://api.wallex.ir/v1/markets"
WALLEX_SYMBOL = os.getenv("WALLEX_SYMBOL", "USDTTMN")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("nerkh")

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# ---------------- ابزارها ----------------
def fa(text) -> str:
    """تبدیل اعداد انگلیسی به فارسی"""
    return str(text).translate(FA_DIGITS)


def fmt_price(value: float) -> str:
    return fa(f"{int(round(value)):,}").replace(",", "٬")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning("state.json خراب بود، از نو ساخته می‌شود")
    return {"last_prices": {}, "last_post_ts": 0, "last_alert_ts": 0}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_quiet_hour(now: datetime) -> bool:
    if QUIET_START_HOUR == QUIET_END_HOUR:
        return False
    if QUIET_START_HOUR < QUIET_END_HOUR:
        return QUIET_START_HOUR <= now.hour < QUIET_END_HOUR
    return now.hour >= QUIET_START_HOUR or now.hour < QUIET_END_HOUR


# ---------------- دریافت قیمت ----------------
def fetch_one(symbol: str) -> float | None:
    """قیمت یک نماد را به تومان برمی‌گرداند"""
    try:
        resp = requests.get(f"{API_BASE}/{symbol}", headers=HEADERS, timeout=20)
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("دریافت %s ناموفق: %s", symbol, e)
        return None
    if resp.status_code != 200 or not data.get("success") or not data.get("price"):
        log.warning("پاسخ نامعتبر برای %s: HTTP %s %s", symbol, resp.status_code, str(data)[:200])
        return None
    return float(data["price"]) / 10  # ریال به تومان


def fetch_tether_live() -> float | None:
    """قیمت لحظه‌ای تتر از والکس (تومان)"""
    try:
        resp = requests.get(WALLEX_URL, headers=HEADERS, timeout=20)
        stats = resp.json()["result"]["symbols"][WALLEX_SYMBOL]["stats"]
        value = float(stats["lastPrice"])
        return value if value > 0 else None
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        log.warning("دریافت تتر از والکس ناموفق، از منبع دوم استفاده می‌شود: %s", e)
        return None


def fetch_prices() -> dict:
    prices = {}
    tether_key = os.getenv("KEY_USDT", "tether")
    for key in ITEMS:
        value = fetch_tether_live() if key == tether_key else None
        if not value:
            value = fetch_one(key)
        if value:
            prices[key] = value
    return prices


# ---------------- ساخت پیام ----------------
def change_text(new: float, old: float | None) -> str:
    if not old:
        return ""
    pct = (new - old) / old * 100
    if abs(pct) < 0.01:
        return "  ⚪️"
    arrow = "🟢▲" if pct > 0 else "🔴▼"
    return f"  {arrow} {fa(f'{abs(pct):.2f}')}٪"


def build_message(prices: dict, last: dict, urgent: bool, movers: list[str]) -> str:
    now = datetime.now(TIMEZONE)
    lines = []
    if urgent:
        names = "، ".join(ITEMS[k].split(" ", 1)[1] for k in movers)
        lines.append(f"⚡️ <b>هشدار نوسان: {names}</b>")
    else:
        lines.append("📊 <b>قیمت لحظه‌ای بازار</b>")
    lines.append(f"🕐 {fa(now.strftime('%H:%M'))}")
    lines.append("")
    for key, title in ITEMS.items():
        if key not in prices:
            continue
        lines.append(
            f"{title}: <b>{fmt_price(prices[key])}</b> تومان"
            f"{change_text(prices[key], last.get(key))}"
        )
    lines.append("")
    if SHOW_BOT_LINK:
        lines.append(f"🔔 هشدار قیمت شخصی: {BOT_USERNAME}")
    lines.append(f"📢 {CHANNEL_ID}")
    return "\n".join(lines)


def send_message(text: str) -> bool:
    try:
        resp = requests.post(
            TELEGRAM_URL,
            json={
                "chat_id": CHANNEL_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        data = resp.json()
        if not data.get("ok"):
            log.error("خطای تلگرام: %s", data)
            return False
        return True
    except requests.RequestException as e:
        log.error("ارسال پیام ناموفق: %s", e)
        return False


# ---------------- منطق اصلی ----------------
def tick(state: dict) -> None:
    now = datetime.now(TIMEZONE)
    prices = fetch_prices()
    if not prices:
        log.warning("هیچ قیمتی دریافت نشد")
        return

    last = state.get("last_prices", {})

    # تشخیص نوسان مهم
    movers = []
    for key, value in prices.items():
        old = last.get(key)
        if old and abs(value - old) / old * 100 >= ALERT_PERCENT:
            movers.append(key)

    now_ts = time.time()
    cooldown_ok = now_ts - state.get("last_alert_ts", 0) >= ALERT_COOLDOWN_MINUTES * 60
    # یک دقیقه تلورانس برای تأخیر زمان‌بندی گیت‌هاب
    interval_ok = now_ts - state.get("last_post_ts", 0) >= (POST_INTERVAL_MINUTES - 1) * 60
    changed = any(round(prices[k]) != round(last.get(k, 0)) for k in prices)
    regular_due = interval_ok and changed and not is_quiet_hour(now)

    if movers and cooldown_ok:
        if send_message(build_message(prices, last, urgent=True, movers=movers)):
            log.info("پست فوری ارسال شد: %s", movers)
            state["last_alert_ts"] = now_ts
            state["last_post_ts"] = now_ts
            state["last_prices"] = prices
    elif regular_due:
        if send_message(build_message(prices, last, urgent=False, movers=[])):
            log.info("پست منظم ارسال شد")
            state["last_post_ts"] = now_ts
            state["last_prices"] = prices
    else:
        log.info("چیزی برای ارسال نیست (قیمت ثابت یا هنوز وقت پست نشده)")

    # اولین اجرا: قیمت‌ها را به عنوان مبنا ذخیره کن
    if not state.get("last_prices"):
        state["last_prices"] = prices

    save_state(state)


def check_config() -> None:
    missing = [n for n, v in [("BOT_TOKEN", BOT_TOKEN)] if not v]
    if missing:
        raise SystemExit(f"این مقادیر خالی است (فایل .env یا Secrets گیت‌هاب): {', '.join(missing)}")


def main() -> None:
    import sys

    check_config()

    if "--keys" in sys.argv:
        for k, title in ITEMS.items():
            print(k, "=>", title, fetch_one(k))
        return

    if "--once" in sys.argv:
        # برای GitHub Actions: یک بار چک کن و خارج شو
        state = load_state()
        tick(state)
        return

    if "--test" in sys.argv:
        prices = fetch_prices()
        ok = send_message(build_message(prices, {}, urgent=False, movers=[]))
        print("ارسال شد ✅" if ok else "ارسال نشد ❌ (لاگ بالا را ببینید)")
        return

    log.info("ربات شروع به کار کرد. کانال: %s", CHANNEL_ID)
    state = load_state()
    while True:
        try:
            tick(state)
        except requests.RequestException as e:
            log.error("خطای شبکه: %s", e)
        except Exception as e:  # noqa: BLE001
            log.exception("خطای غیرمنتظره: %s", e)
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
