#!/usr/bin/env python3
"""Telegram-тыңдаушы: хабарламаны бірден қабылдап, иесіне жеке чатта растау жібереді.
Тапсырмалар bots/assistant/inbox.jsonl файлына түседі, доскаға ассистент (пуш немесе сессия) көшіреді.
Іске қосу: python3 -I bots/assistant/listener.py"""
import os, sys, json, re, time, html, datetime as dt
import urllib.request, urllib.parse

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
os.makedirs(os.path.join(DIR, "tmp"), exist_ok=True)

env = {}
for line in open(os.path.join(DIR, ".env"), encoding="utf8"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        env[k] = v
TOKEN = os.environ.get("BOT_TOKEN") or env["BOT_TOKEN"]
OWNER = int(os.environ.get("CHAT_ID") or env["CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}/"
INBOX = os.path.join(DIR, "inbox.jsonl")
OFFSET_FILE = os.path.join(DIR, "tmp", "offset")
PID_FILE = os.path.join(DIR, "tmp", "listener.pid")
MENTION = re.compile(r"саят|саяк|@hos_baipket", re.I)


def call(method, params=None, http_timeout=70):
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(API + method, data), timeout=http_timeout) as r:
        return json.load(r)


def say(text):
    try:
        call("sendMessage", {"chat_id": OWNER, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})
    except Exception as e:
        print("send error", e, flush=True)


def save(entry):
    with open(INBOX, "a", encoding="utf8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def prayer_text():
    import prayer
    t = prayer.times(dt.date.today())
    rows = "\n".join(f"• {k}: <b>{v}</b>" for k, v in t.items())
    return f"<b>🕌 Намаз уақыты (Алматы)</b>\n{rows}\n<i>Есептелген уақыт, ДУМК кестесімен салыстырыңыз.</i>"


def handle(u):
    m = u.get("message")
    if not m:
        return
    chat = m.get("chat", {})
    frm = m.get("from", {})
    text = (m.get("text") or m.get("caption") or "").strip()
    is_private = chat.get("type") == "private"
    is_owner = frm.get("id") == OWNER
    place = "жеке чат" if is_private else (chat.get("title") or "топ")
    who = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x) or frm.get("username") or "?"
    base = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "update_id": u["update_id"], "place": place, "from": who, "date": m.get("date")}

    if is_private and is_owner:
        low = text.lower()
        if low.startswith("/namaz"):
            say(prayer_text()); return
        if low.startswith("/help") or low.startswith("/start"):
            say("<b>Мен не істей аламын</b>\n• Тапсырма: жай жазыңыз, мен қабылдап доскаға қосамын\n• <code>/tapsyrma мәтін</code> — тапсырма\n• <code>/aqsha 250000 90000 30000</code> — дүкен кірісі, дүкен шығысы, үй шығысы\n• <code>/namaz</code> — намаз уақыты\n• Дауыстық хабарлама — расшифровка жасап тапсырма етемін\nТоптарда «Саят» аталғанын өзім табамын."); return
        if low.startswith("/aqsha") or (re.search(r"дүкен|үй|магазин", low) and len(re.findall(r"\d[\d\s]*", text)) >= 3):
            nums = [int(re.sub(r"\s", "", n)) for n in re.findall(r"\d[\d\s]*\d|\d", text)][:3]
            if len(nums) == 3:
                save({**base, "kind": "money", "shopIn": nums[0], "shopOut": nums[1], "homeOut": nums[2], "text": text})
                say(f"✅ <b>Қабылдадым.</b>\nДүкен кірісі: {nums[0]:,} ₸\nДүкен шығысы: {nums[1]:,} ₸\nҮй шығысы: {nums[2]:,} ₸\n<i>Доскаға қосамын.</i>".replace(",", " "))
            else:
                say("Үш сан керек: дүкен кірісі, дүкен шығысы, үй шығысы. Мысалы: <code>/aqsha 250000 90000 30000</code>")
            return
        if "voice" in m or "audio" in m or "video_note" in m:
            v = m.get("voice") or m.get("audio") or m.get("video_note")
            save({**base, "kind": "voice", "file_id": v.get("file_id"), "duration": v.get("duration")})
            say("🎙 <b>Дауыстық қабылдадым.</b>\nРасшифровка жасап, тапсырма етіп доскаға қосамын.")
            return
        if text and re.search(r"оқыдым|окыдым|оқып болдым|прочитал", low) and re.search(r"таң|бесін|екінті|шам|ақшам|құфтан|намаз|фаджр|зухр|аср|магриб|иша", low):
            save({**base, "kind": "habit", "habit": "namaz", "text": text})
            say(f"🤲 <b>Қабылдадым:</b> {html.escape(text[:200])}\n<i>Намаз белгіленді, апталық статистикаға қосамын.</i>")
            return
        if text:
            body = re.sub(r"^/tapsyrma(@\w+)?\s*", "", text, flags=re.I)
            save({**base, "kind": "task", "text": body})
            say(f"✅ <b>Қабылдадым:</b> {html.escape(body[:300])}\n<i>Доскаға қосамын.</i>")
        return

    if not is_private and (MENTION.search(text) or MENTION.search(m.get("caption") or "")):
        save({**base, "kind": "task", "text": text, "chat_title": chat.get("title")})
        say(f"✅ <b>Қабылдадым.</b> «{html.escape(place)}» тобында {html.escape(who)} сізге жазды:\n<i>{html.escape(text[:400])}</i>\n<i>Тапсырма ретінде доскаға қосамын.</i>")


def main():
    if os.path.exists(PID_FILE):
        try:
            os.kill(int(open(PID_FILE).read()), 0)
            print("already running"); return
        except Exception:
            pass
    open(PID_FILE, "w").write(str(os.getpid()))
    offset = int(open(OFFSET_FILE).read()) if os.path.exists(OFFSET_FILE) else None
    print("listener started", flush=True)
    while True:
        try:
            params = {"timeout": 50, "allowed_updates": json.dumps(["message"])}
            if offset:
                params["offset"] = offset
            res = call("getUpdates", params, 70)
            for u in res.get("result", []):
                try:
                    handle(u)
                except Exception as e:
                    print("handle error", e, flush=True)
                offset = u["update_id"] + 1
                open(OFFSET_FILE, "w").write(str(offset))
        except Exception as e:
            print("poll error", e, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
