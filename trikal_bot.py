"""
================================================================
  त्रिकाल दर्शन — Telegram Bot + Daily Horoscope Sender
  Version 2.0 — Render Background Worker
================================================================

Pharma-SFA ya Trikal Darshan — kisi bhi Render project mein rakhो।
Trikal Darshan ke repo mein rakhna BETTER hai kyunki:
  - Same codebase
  - Same requirements.txt (swisseph already hai)
  - Easy maintenance

Render Dashboard → Environment Variables:
    TELEGRAM_BOT_TOKEN  = bot token
    GEMINI_API_KEYS1..4 = Gemini keys
    BOT_API_SECRET      = trikal-secret-2026
    TRIKAL_API_BASE     = https://trikal-darshan-2-0.onrender.com

Render → New Background Worker:
    Start Command: python trikal_bot.py
================================================================
"""

import os, time, json, random, re, requests, datetime
import swisseph as swe
import pytz

# ── Config ───────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_SECRET   = os.getenv("BOT_API_SECRET", "trikal-secret-2026")
TRIKAL_BASE  = os.getenv("TRIKAL_API_BASE", "https://trikal-darshan-2-0.onrender.com")
GEMINI_MODEL = "gemini-3-flash-preview"

GEMINI_KEYS = []
for _i in range(1, 10):
    _k = os.getenv(f"GEMINI_API_KEYS{_i}", "").strip()
    if _k: GEMINI_KEYS.append(_k)

TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
HEADERS = {"X-Bot-Secret": BOT_SECRET, "Content-Type": "application/json"}

# ── Vedic Constants ──────────────────────────────────────────
RASHI_NAMES = [
    "मेष","वृषभ","मिथुन","कर्क","सिंह","कन्या",
    "तुला","वृश्चिक","धनु","मकर","कुंभ","मीन"
]
NAKSHATRA_NAMES = [
    "अश्विनी","भरणी","कृत्तिका","रोहिणी","मृगशिरा","आर्द्रा",
    "पुनर्वसु","पुष्य","आश्लेषा","मघा","पूर्वाफाल्गुनी","उत्तराफाल्गुनी",
    "हस्त","चित्रा","स्वाती","विशाखा","अनुराधा","ज्येष्ठा",
    "मूल","पूर्वाषाढ़ा","उत्तराषाढ़ा","श्रवण","धनिष्ठा","शतभिषा",
    "पूर्वाभाद्रपद","उत्तराभाद्रपद","रेवती"
]
SWE_IDS = {
    "सूर्य": swe.SUN, "चंद्र": swe.MOON, "मंगल": swe.MARS,
    "बुध": swe.MERCURY, "गुरु": swe.JUPITER, "शुक्र": swe.VENUS,
    "शनि": swe.SATURN, "राहु": swe.TRUE_NODE,
}

# ── Telegram Functions ───────────────────────────────────────
def tg_send(chat_id, text):
    """Telegram par message bhejo"""
    try:
        r = requests.post(
            f"{TG_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
        if r.status_code != 200:
            print(f"  TG error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  TG send error: {e}")


def tg_get_updates(offset):
    """Telegram updates fetch karo"""
    try:
        r = requests.get(
            f"{TG_BASE}/getUpdates",
            params={"offset": offset, "timeout": 20},
            timeout=30
        )
        return r.json()
    except:
        return {"ok": False, "result": []}


# ── Trikal API Functions ──────────────────────────────────────
def api_save_chat_id(username, chat_id):
    """Render/PythonAnywhere API par chat_id save karo"""
    try:
        r = requests.post(
            f"{TRIKAL_BASE}/api/bot/save-chat-id/",
            json={"username": username, "chat_id": chat_id},
            headers=HEADERS, timeout=15
        )
        return r.json()
    except Exception as e:
        print(f"  API save_chat_id error: {e}")
        return {"ok": False}


def api_get_pending():
    """Aaj ke pending horoscope users lo"""
    try:
        r = requests.get(
            f"{TRIKAL_BASE}/api/bot/pending-horoscope/",
            headers=HEADERS, timeout=30
        )
        data = r.json()
        print(f"  API response: {data.get('count', 0)} users pending")
        return data.get("users", [])
    except Exception as e:
        print(f"  API pending error: {e}")
        return []


def api_save_horoscope(username, text):
    """Horoscope DB mein save karo"""
    try:
        requests.post(
            f"{TRIKAL_BASE}/api/bot/save-horoscope/",
            json={"username": username, "horoscope_text": text},
            headers=HEADERS, timeout=15
        )
    except Exception as e:
        print(f"  API save_horoscope error: {e}")


# ── SwissEph Transit ─────────────────────────────────────────
def get_transit():
    """Aaj ke graha positions (Lahiri Ayanamsha)"""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz)
    jd = swe.julday(
        now.year, now.month, now.day,
        now.hour + now.minute / 60.0 + now.second / 3600.0
    )
    ayan = swe.get_ayanamsa_ut(jd)
    pos = {}

    for naam, pid in SWE_IDS.items():
        res, _ = swe.calc_ut(jd, pid, swe.FLG_SWIEPH | swe.FLG_SPEED)
        lon = (res[0] - ayan) % 360
        retro = res[3] < 0
        r_idx = int(lon / 30)
        nak_idx = int(lon / (360 / 27))
        pos[naam] = {
            "rashi":     RASHI_NAMES[r_idx],
            "degree":    round(lon % 30, 1),
            "nakshatra": NAKSHATRA_NAMES[nak_idx],
            "vakri":     retro,
            "full_lon":  round(lon, 3),
        }

    # ✅ Bug Fix: Ketu = Rahu + 180°
    rahu_lon = pos["राहु"]["full_lon"]
    ketu_lon = (rahu_lon + 180) % 360
    k_idx = int(ketu_lon / 30)
    k_nak = int(ketu_lon / (360 / 27))
    pos["केतु"] = {
        "rashi":     RASHI_NAMES[k_idx],
        "degree":    round(ketu_lon % 30, 1),
        "nakshatra": NAKSHATRA_NAMES[k_nak],
        "vakri":     True,
        "full_lon":  round(ketu_lon, 3),
    }
    return pos


# ── Gemini API ───────────────────────────────────────────────
def call_gemini(prompt):
    """Gemini API call — key rotation + retry"""
    if not GEMINI_KEYS:
        print("  ❌ No Gemini keys!")
        return None

    keys = GEMINI_KEYS.copy()
    random.shuffle(keys)

    for key in keys:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{GEMINI_MODEL}:generateContent?key={key}"
            )
            r = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.75,
                    "maxOutputTokens": 1024,  # ✅ Bug Fix: 512 → 1024
                }
            }, timeout=30)

            if r.status_code == 200:
                candidates = r.json().get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    # Markdown cleanup
                    text = re.sub(r'\*+', '', text)
                    text = re.sub(r'#+\s*', '', text)
                    return text.strip()

            elif r.status_code == 429:
                print(f"  Rate limit, next key try kar rahe hain...")
                time.sleep(2)
            else:
                print(f"  Gemini {r.status_code}: {r.text[:80]}")

        except Exception as e:
            print(f"  Gemini error: {e}")

        time.sleep(1)

    return None


# ── Rashifal Generator ───────────────────────────────────────
def generate_rashifal(user, transit):
    """User ki kundali + gochar se rashifal banao"""
    today = datetime.date.today().strftime("%d %B %Y")

    # Transit text
    transit_text = "\n".join([
        f"  {g}: {d['rashi']} {d['degree']}° | {d['nakshatra']}"
        + (" (वक्री 🔄)" if d['vakri'] else "")
        for g, d in transit.items()
    ])

    # Kundali info
    k = user.get("kundali", {})

    # Profile text
    profile_lines = []
    for label, field in [
        ("पेशा",         "profession"),
        ("मुख्य लक्ष्य", "primary_focus"),
        ("चुनौती",       "current_challenge"),
        ("रिश्ते",       "relationship_status"),
        ("आर्थिक लक्ष्य","finance_focus"),
    ]:
        if user.get(field):
            profile_lines.append(f"  • {label}: {user[field]}")
    profile_text = "\n".join(profile_lines) or "  • सामान्य जीवन"

    name = user.get('display_name', 'जातक')

    prompt = f"""
आज की तारीख: {today}

आप एक अनुभवी वैदिक ज्योतिषी हैं जो पाराशरी सिद्धांतों पर आधारित सटीक फलित देते हैं।

जातक: {name} जी
जन्म: {k.get('day')}/{k.get('month')}/{k.get('year')} | {k.get('hour')}:{k.get('minute', 0):02d} | {k.get('city', '')}

यूजर की व्यक्तिगत स्थिति:
{profile_text}

आज का सटीक गोचर (Lahiri Ayanamsha):
{transit_text}

फलित नियम:
1. '{name} जी,' से शुरू करें
2. 5-6 पंक्तियाँ — सरल, उत्साहवर्धक हिंदी
3. गोचर और यूजर की व्यक्तिगत स्थिति दोनों को ध्यान में रखें
4. अंत में एक वैदिक उपाय (रंग/मंत्र/कर्म) जरूर बताएं
5. कोई ** या ## Markdown नहीं
"""
    return call_gemini(prompt)


# ── Daily Horoscope Sender ───────────────────────────────────
def send_daily_horoscopes():
    """Sabhi pending users ko rashifal bhejo"""
    print(f"\n🔮 Daily Horoscope — {datetime.date.today()}")

    users = api_get_pending()
    if not users:
        print("  ℹ️  Koi pending user nahi hai")
        return

    # Transit ek baar nikalo — sab ke liye same
    try:
        transit = get_transit()
        print(f"  🪐 Transit ready: {len(transit)} grahas")
    except Exception as e:
        print(f"  ❌ Transit error: {e}")
        return

    sent, failed = 0, 0
    for user in users:
        try:
            print(f"  👤 {user['username']}...")
            rashifal = generate_rashifal(user, transit)

            if not rashifal:
                print(f"    ❌ Gemini failed")
                failed += 1
                continue

            # Telegram par bhejo
            tg_send(
                user["chat_id"],
                f"🔮 *त्रिकाल दर्शन — आज का राशिफल*\n\n{rashifal}"
            )

            # DB mein save karo
            api_save_horoscope(user["username"], rashifal)
            sent += 1
            print(f"    ✅ Sent!")
            time.sleep(1.5)  # Rate limit avoid karo

        except Exception as e:
            print(f"    ❌ Error: {e}")
            failed += 1

    print(f"\n  📊 Sent: {sent} | Failed: {failed} | Total: {len(users)}")


# ── Telegram Bot Loop ─────────────────────────────────────────
def handle_start(chat_id, text, first_name):
    """/start command handle karo"""
    parts = text.split(maxsplit=1)

    if len(parts) > 1:
        username = parts[1].strip()
        result = api_save_chat_id(username, chat_id)

        if result.get("ok"):
            name = result.get("display_name", username)
            tg_send(chat_id,
                f"🎉 *बधाई हो {name} जी!*\n\n"
                f"आपका त्रिकाल दर्शन अकाउंट Telegram से जुड़ गया! ✨\n\n"
                f"🌅 अब रोज़ सुबह यहाँ आपका व्यक्तिगत AI राशिफल मिलेगा। 🙏"
            )
            print(f"  ✅ Linked: {username} → {chat_id}")
        else:
            tg_send(chat_id,
                "⚠️ आपका अकाउंट नहीं मिला।\n"
                "कृपया वेबसाइट पर जाकर दोबारा 'Telegram Bot से जुड़ें' बटन दबाएं।"
            )
    else:
        tg_send(chat_id,
            "🔮 *त्रिकाल दर्शन बॉट में स्वागत है!*\n\n"
            "अपना अकाउंट जोड़ने के लिए वेबसाइट पर जाएं "
            "और 'Telegram Bot से जुड़ें' बटन दबाएं।\n\n"
            "🌐 trikal-darshan-2-0.onrender.com"
        )


def run_bot():
    """Main bot loop"""
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN nahi mila!")
        return

    print("=" * 50)
    print("🤖 त्रिकाल दर्शन Bot v2.0 Starting...")
    print(f"🌐 API Base: {TRIKAL_BASE}")
    print(f"🔑 Gemini Keys: {len(GEMINI_KEYS)}")
    print("=" * 50)

    offset = 0
    # Last horoscope check — 25 hours pehle set karo taaki first run mein check ho
    last_horoscope_date = None

    while True:
        try:
            now = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
            today = now.date()

            # ✅ Daily horoscope — subah 7:00 baje, sirf ek baar
            if now.hour == 7 and last_horoscope_date != today:
                send_daily_horoscopes()
                last_horoscope_date = today

            # Telegram polling
            data = tg_get_updates(offset)
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    if not msg or "text" not in msg:
                        continue

                    chat_id    = str(msg["chat"]["id"])
                    text       = msg["text"].strip()
                    first_name = msg.get("from", {}).get("first_name", "")
                    print(f"📩 '{text}' from {chat_id}")

                    if text.startswith("/start"):
                        handle_start(chat_id, text, first_name)
                    elif text == "/status":
                        tg_send(chat_id, "✅ त्रिकाल दर्शन बॉट सक्रिय है! 🔮")
                    elif text == "/rashifal":
                        tg_send(chat_id, "🌅 राशिफल रोज़ सुबह 7 बजे मिलेगा।")
                    elif text == "/help":
                        tg_send(chat_id,
                            "📖 *उपलब्ध कमांड:*\n\n"
                            "/status — बॉट की स्थिति\n"
                            "/rashifal — राशिफल समय\n"
                            "/help — सहायता"
                        )

        except Exception as e:
            print(f"❌ Bot loop error: {e}")
            time.sleep(5)

        time.sleep(1)


if __name__ == "__main__":
    run_bot()
