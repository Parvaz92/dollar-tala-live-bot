"""
ربات پست اتوماتیک قیمت دلار، طلا، سکه و تتر در کانال تلگرام
Dollar / Gold price auto-poster for a Telegram channel.

- هر ساعت یک پست منظم (به جز ساعات سکوت شب)
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
API_KEY = os.getenv("BRSAPI_KEY", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "@dollar_tala_live_bot").strip()

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
ALERT_PERCENT = float(os.getenv("ALERT_PERCENT", "1.0"))
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))
QUIET_START_HOUR = int(os.getenv("QUIET_START_HOUR", "0"))
QUIET_END_HOUR = int(os.getenv("QUIET_END_HOUR", "8"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tehran"))

# نماد هر قیمت در BrsApi : عنوان فارسی
# اگر نمادی کار نکرد، با دستور  python bot.py --keys  نمادهای موجود را ببینید
ITEMS = {
    os.getenv("KEY_USD", "USD"): "💵 دلار",
    os.getenv("KEY_EUR", "EUR"): "💶 یورو",
    os.getenv("KEY_USDT", "USDT"): "🪙 تتر",
    os.getenv("KEY_GOLD18", "IR_GOLD_18K"): "🟡 طلای ۱۸ عیار (گرم)",
    os.getenv("KEY_SEKKEH", "IR_COIN_EMAMI"): "🏅 سکه امامی",
}

API_URL = "https://Api.BrsApi.ir/Market/Gold_Currency.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (dollar-tala-live-bot)", "Accept": "application/json"}
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
    return {"last_prices": {}, "last_hourly": "", "last_alert_ts": 0}


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
def fetch_raw() -> dict:
    """همه‌ی نمادها را به شکل {symbol: item} برمی‌گرداند"""
    resp = requests.get(API_URL, params={"key": API_KEY}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = {}

    def walk(node):
        if isinstance(node, dict):
            if "symbol" in node and "price" in node:
                items[str(node["symbol"])] = node
            else:
                for v in node.values():
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return items


def to_toman(item: dict) -> float:
    value = float(str(item["price"]).replace(",", ""))
    if "ریال" in str(item.get("unit", "")):
        value /= 10
    return value


def fetch_prices() -> dict:
    raw = fetch_raw()
    prices = {}
    for key in ITEMS:
        item = raw.get(key)
        if not item:
            log.warning("نماد %s در پاسخ API نبود. نمادهای موجود: %s", key, ", ".join(raw))
            continue
        try:
            prices[key] = to_toman(item)
        except (KeyError, ValueError, TypeError):
            log.warning("مقدار نماد %s قابل خواندن نبود: %s", key, item)
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

    cooldown_ok = time.time() - state.get("last_alert_ts", 0) >= ALERT_COOLDOWN_MINUTES * 60
    hour_key = now.strftime("%Y-%m-%d %H")
    hourly_due = state.get("last_hourly") != hour_key and not is_quiet_hour(now)

    if movers and cooldown_ok:
        if send_message(build_message(prices, last, urgent=True, movers=movers)):
            log.info("پست فوری ارسال شد: %s", movers)
            state["last_alert_ts"] = time.time()
            state["last_prices"] = prices
            state["last_hourly"] = hour_key
    elif hourly_due:
        if send_message(build_message(prices, last, urgent=False, movers=[])):
            log.info("پست ساعتی ارسال شد")
            state["last_prices"] = prices
            state["last_hourly"] = hour_key
    else:
        log.info("چیزی برای ارسال نیست")

    # اولین اجرا: قیمت‌ها را به عنوان مبنا ذخیره کن
    if not state.get("last_prices"):
        state["last_prices"] = prices

    save_state(state)


def check_config() -> None:
    missing = [n for n, v in [("BOT_TOKEN", BOT_TOKEN), ("BRSAPI_KEY", API_KEY)] if not v]
    if missing:
        raise SystemExit(f"این مقادیر خالی است (فایل .env یا Secrets گیت‌هاب): {', '.join(missing)}")


def main() -> None:
    import sys

    check_config()

    if "--keys" in sys.argv:
        raw = fetch_raw()
        for k, v in raw.items():
            print(k, "=>", v.get("name"), v.get("price"), v.get("unit"))
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
