# 📈 ربات نرخ لایو | دلار، طلا، سکه

ربات پست اتوماتیک قیمت در کانال [@dollar_tala_live](https://t.me/dollar_tala_live)

- هر ساعت یک پست منظم قیمت
- پست فوری وقتی قیمتی بیشتر از ۱٪ تغییر کند
- ساعت ۱۲ شب تا ۸ صبح فقط پست فوری
- همه چیز از فایل `.env` قابل تنظیم است

---

## ✅ پیش‌نیازها
1. توکن ربات از BotFather
2. ربات در کانال **ادمین** باشد (با دسترسی ارسال پست)
3. کلید API از [navasan.tech](https://www.navasan.tech)
4. (فقط برای روش دوم) یک سرور لینوکس خارج از ایران

## 🆓 اجرای رایگان با GitHub Actions (بدون سرور)

ربات می‌تواند **رایگان** روی سرورهای خود گیت‌هاب اجرا شود و هر ۳۰ دقیقه یک بار قیمت را چک کند.

0. **یک بار:** در صفحه‌ی ریپو بزنید **Add file → Create new file**، اسم فایل را دقیقاً `.github/workflows/post.yml` بنویسید، محتوای فایل [`setup/post.yml`](setup/post.yml) را کپی و پیست کنید و **Commit changes** را بزنید.
1. در صفحه‌ی ریپو بروید به **Settings → Secrets and variables → Actions**
2. روی **New repository secret** بزنید و این دو را بسازید:
   - اسم: `BOT_TOKEN` ، مقدار: توکن BotFather
   - اسم: `NAVASAN_API_KEY` ، مقدار: کلید نوسان
3. بروید به تب **Actions** ، روی **Post prices** و بعد **Run workflow** بزنید تا اولین پست ارسال شود.

از این به بعد خودکار هر ۳۰ دقیقه اجرا می‌شود (هر ساعت یک پست + پست فوری در نوسان). مصرف: حدود ۱۴۴۰ دقیقه در ماه، زیر سقف ۲۰۰۰ دقیقه‌ی رایگان.

> زمان‌بندی گیت‌هاب گاهی چند دقیقه تأخیر دارد، طبیعی است.

---

## 🖥 روش دوم: نصب روی سرور شخصی

با SSH وارد سرور شوید و این دستورها را به ترتیب بزنید:

```bash
apt update && apt install -y git python3 python3-venv
cd /root
git clone https://github.com/Parvaz92/dollar-tala-live-bot.git
cd dollar-tala-live-bot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

در `nano` جلوی `BOT_TOKEN=` و `NAVASAN_API_KEY=` مقدارها را بنویسید، بعد `Ctrl+O` ، `Enter` ، `Ctrl+X`.

> ⚠️ چون ریپو خصوصی است، موقع `git clone` گیت‌هاب نام کاربری و یک **Personal Access Token** می‌خواهد (نه رمز عبور).

### تست
```bash
venv/bin/python bot.py --test
```
اگر یک پست در کانال آمد، همه چیز درست است ✅

اگر قیمتی نیامد، کلیدهای API را ببینید:
```bash
venv/bin/python bot.py --keys
```
و کلید درست را در `.env` بگذارید (مثلاً `KEY_USD=usd_sell`).

### اجرای دائمی (حتی بعد از ریستارت سرور)
```bash
cp dollar-tala-live-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dollar-tala-live-bot
```

دیدن لاگ: `journalctl -u dollar-tala-live-bot -f`  
ریستارت بعد از تغییر تنظیمات: `systemctl restart dollar-tala-live-bot`

## ⚙️ تنظیمات `.env`
| متغیر | توضیح | پیش‌فرض |
|---|---|---|
| `CHECK_INTERVAL_MINUTES` | هر چند دقیقه قیمت چک شود | 15 |
| `ALERT_PERCENT` | درصد تغییر برای پست فوری | 1.0 |
| `ALERT_COOLDOWN_MINUTES` | فاصله‌ی حداقل بین پست‌های فوری | 30 |
| `QUIET_START_HOUR` / `QUIET_END_HOUR` | ساعات سکوت شب | 0 / 8 |

> 💡 پلن رایگان نوسان سقف درخواست ماهانه دارد. هر ۱۵ دقیقه ≈ ۲۹۰۰ درخواست در ماه. اگر سقف پلن کمتر است، `CHECK_INTERVAL_MINUTES` را بیشتر کنید.

## 🔒 امنیت
فایل `.env` هیچ‌وقت در گیت‌هاب آپلود نمی‌شود (در `.gitignore` است). توکن را به کسی ندهید.
