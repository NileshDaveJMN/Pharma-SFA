"""
trikal_bot.py — Pharma-SFA Render project mein add karo
Ye file Telegram bot + daily horoscope sender hai.

Render par "Background Worker" ke roop mein chalega.

Environment Variables (Render Dashboard par set karo):
    TELEGRAM_BOT_TOKEN  = aapka bot token
    GEMINI_API_KEYS1    = Gemini key 1
    GEMINI_API_KEYS2    = Gemini key 2
    GEMINI_API_KEYS3    = Gemini key 3
    GEMINI_API_KEYS4    = Gemini key 4
    BOT_API_SECRET      = trikal-secret-2026
    TRIKAL_API_BASE     = https://trikaldarshan.pythonanywhere.com
"""

import os, time, json, random, re, requests, datetime
import swisseph as swe
import pytz

# ── Config ───────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_SECRET   = os.getenv("BOT_API_SECRET", "trikal-secret-2026")
TRIKAL_BASE  = os.getenv("TRIKAL_API_BASE", "https://trikaldarshan.pythonanywhere.com")
GEMINI_MODEL = "gemini-3-flash-preview"

GEMINI_KEYS = []
for i in range(1, 10):
    k = os.getenv(f"GEMINI_API_KEYS{i}", "").strip()
    if k: GEMINI_KEYS.append(k)

TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
HEADERS = {"X-Bot-Secret": BOT_SECRET}

# ── Vedic Constants ──────────────────────────────────────────
RASHI_NAMES = ["मेष","वृषभ","मिथुन","कर्क","सिंह","कन्या","तुला","वृश्चिक","धनु","मकर","कुंभ","मीन"]
NAKSHATRA_NAMES = ["अश्विनी","भरणी","कृत्तिका","रोहिणी","मृगशिरा","आर्द्रा","पुनर्वसु","पुष्य","आश्लेषा","मघा","पूर्वाफाल्गुनी","उत्तराफाल्गुनी","हस्त","चित्रा","स्वाती","विशाखा","अनुराधा","ज्येष्ठा","मूल","पूर्वाषाढ़ा","उत्तराषाढ़ा","श्रवण","धनिष्ठा","शतभिषा","पूर्वाभाद्रपद","उत्तराभाद्रपद","रेवती"]
SWE_IDS = {"सूर्य":swe.SUN,"चंद्र":swe.MOON,"मंगल":swe.MARS,"बुध":swe.MERCURY,"गुरु":swe.JUPITER,"शुक्र":swe.VENUS,"शनि":swe.SATURN,"राहु":swe.TRUE_NODE}

# ── Telegram Functions ───────────────────────────────────────
def tg_send(chat_id, text):
    try:
        requests.post(f"{TG_BASE}/sendMessage",
            json={"chat_id":chat_id,"text":text,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"TG send error: {e}")

def tg_get_updates(offset):
    try:
        r = requests.get(f"{TG_BASE}/getUpdates",
            params={"offset":offset,"timeout":20},timeout=30)
        return r.json()
    except:
        return {"ok":False,"result":[]}

# ── PythonAnywhere API Functions ─────────────────────────────
def pa_save_chat_id(username, chat_id):
    try:
        r = requests.post(f"{TRIKAL_BASE}/api/bot/save-chat-id/",
            json={"username":username,"chat_id":chat_id},
            headers=HEADERS, timeout=15)
        return r.json()
    except Exception as e:
        print(f"PA save_chat_id error: {e}")
        return {"ok":False}

def pa_get_pending():
    try:
        r = requests.get(f"{TRIKAL_BASE}/api/bot/pending-horoscope/",
            headers=HEADERS, timeout=30)
        return r.json().get("users", [])
    except Exception as e:
        print(f"PA pending error: {e}")
        return []

def pa_save_horoscope(username, text):
    try:
        requests.post(f"{TRIKAL_BASE}/api/bot/save-horoscope/",
            json={"username":username,"horoscope_text":text},
            headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"PA save_horoscope error: {e}")

# ── SwissEph Transit ─────────────────────────────────────────
def get_transit():
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz)
    jd = swe.julday(now.year,now.month,now.day,now.hour+now.minute/60.0)
    ayan = swe.get_ayanamsa_ut(jd)
    pos = {}
    for naam, pid in SWE_IDS.items():
        res, _ = swe.calc_ut(jd, pid, swe.FLG_SWIEPH|swe.FLG_SPEED)
        lon = (res[0] - ayan) % 360
        retro = res[3] < 0
        r_idx = int(lon/30)
        nak_idx = int(lon/(360/27))
        pos[naam] = {
            "rashi": RASHI_NAMES[r_idx],
            "degree": round(lon%30,1),
            "nakshatra": NAKSHATRA_NAMES[nak_idx],
            "vakri": retro
        }
    # Ketu
    rahu_lon = (SWE_IDS["राहु"] and pos["राहु"]["degree"] + pos["राहु"]["rashi"].index(pos["राहु"]["rashi"]) * 30)
    return pos

# ── Gemini API ───────────────────────────────────────────────
def call_gemini(prompt):
    if not GEMINI_KEYS:
        print("❌ No Gemini keys!")
        return None
    keys = GEMINI_KEYS.copy()
    random.shuffle(keys)
    for key in keys:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
            r = requests.post(url, json={
                "contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"temperature":0.75,"maxOutputTokens":512}
            }, timeout=30)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = re.sub(r'\*+','',text)
                text = re.sub(r'#+\s*','',text)
                return text.strip()
            elif r.status_code == 429:
                print(f"Rate limit, trying next key...")
                time.sleep(2)
        except Exception as e:
            print(f"Gemini error: {e}")
        time.sleep(1)
    return None

# ── Rashifal Generator ───────────────────────────────────────
def generate_rashifal(user, transit):
    today = datetime.date.today().strftime("%d %B %Y")
    transit_text = "\n".join([
        f"  {g}: {d['rashi']} {d['degree']}° | {d['nakshatra']}" + (" (वक्री)" if d['vakri'] else "")
        for g, d in transit.items()
    ])
    k = user.get("kundali", {})
    profile_text = ""
    for label, field in [("पेशा", "profession"), ("मुख्य लक्ष्य", "primary_focus"),
                          ("चुनौती", "current_challenge"), ("रिश्ते", "relationship_status"),
                          ("आर्थिक लक्ष्य", "finance_focus")]:
        if user.get(field):
            profile_text += f"  • {label}: {user[field]}\n"

    prompt = f"""
आज: {today}
आप एक अनुभवी वैदिक ज्योतिषी हैं।

जातक: {user['display_name']} जी
जन्म: {k.get('day')}/{k.get('month')}/{k.get('year')} {k.get('hour')}:{k.get('minute'):02d}
{profile_text}
आज का गोचर:
{transit_text}

नियम:
1. 5-6 लाइन, सरल हिंदी
2. '{user['display_name']} जी,' से शुरू करें
3. अंत में एक छोटा वैदिक उपाय बताएं
4. कोई ** या ## नहीं
"""
    return call_gemini(prompt)

# ── Daily Horoscope Sender ───────────────────────────────────
def send_daily_horoscopes():
    print(f"\n🔮 Daily Horoscope — {datetime.date.today()}")
    users = pa_get_pending()
    print(f"📋 Pending users: {len(users)}")
    if not users:
        return

    transit = get_transit()
    sent = 0
    for user in users:
        try:
            rashifal = generate_rashifal(user, transit)
            if not rashifal:
                print(f"  ❌ {user['username']} — Gemini failed")
                continue
            tg_send(user["chat_id"], f"🔮 *त्रिकाल दर्शन — आज का राशिफल*\n\n{rashifal}")
            pa_save_horoscope(user["username"], rashifal)
            sent += 1
            print(f"  ✅ {user['username']} — Sent!")
            time.sleep(1)
        except Exception as e:
            print(f"  ❌ {user['username']} error: {e}")

    print(f"✅ Sent: {sent}/{len(users)}")

# ── Telegram Bot Polling ─────────────────────────────────────
def handle_start(chat_id, text, first_name):
    parts = text.split(maxsplit=1)
    if len(parts) > 1:
        username = parts[1].strip()
        result = pa_save_chat_id(username, chat_id)
        if result.get("ok"):
            name = result.get("display_name", username)
            tg_send(chat_id,
                f"🎉 *बधाई हो {name} जी!*\n\n"
                f"आपका त्रिकाल दर्शन अकाउंट Telegram से जुड़ गया! ✨\n\n"
                f"🌅 अब रोज़ सुबह यहाँ आपका AI राशिफल मिलेगा। 🙏"
            )
        else:
            tg_send(chat_id, "⚠️ अकाउंट नहीं मिला। वेबसाइट से दोबारा जुड़ें।")
    else:
        tg_send(chat_id,
            "🔮 *त्रिकाल दर्शन बॉट में स्वागत है!*\n\n"
            "वेबसाइट पर जाकर 'Telegram Bot से जुड़ें' बटन दबाएं।\n\n"
            "🌐 trikaldarshan.pythonanywhere.com"
        )

def run_bot():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN nahi mila!")
        return

    print("🤖 Trikal Darshan Bot starting...")
    offset = 0
    last_horoscope_check = datetime.datetime.now() - datetime.timedelta(hours=25)

    while True:
        # Daily horoscope — subah 7 baje check karo
        now = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
        if now.hour == 7 and (now - last_horoscope_check).total_seconds() > 3600:
            send_daily_horoscopes()
            last_horoscope_check = now

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
                    tg_send(chat_id, "🔮 त्रिकाल दर्शन बॉट सक्रिय है! 🙏")
                elif text == "/rashifal":
                    tg_send(chat_id, "⏳ राशिफल सुबह 7 बजे मिलेगा। 🌅")

        time.sleep(1)

if __name__ == "__main__":
    run_bot()
