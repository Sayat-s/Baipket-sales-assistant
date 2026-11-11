#!/usr/bin/env bash
# Отправка в Telegram-группу.
# Использование:
#   send.sh text  "<b>Привет</b>"        # текст (HTML)
#   send.sh voice "Текст для озвучки"    # голосовое (edge-tts, русский)
#   send.sh photo /path/img.png ["подпись"]
#   send.sh doc   /path/file.pdf ["подпись"]
#   send.sh chatid                        # найти chat_id группы через getUpdates
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$DIR/.env" ] && set -a && . "$DIR/.env" && set +a
: "${BOT_TOKEN:?BOT_TOKEN не задан (переменная окружения или bots/assistant/.env)}"
API="https://api.telegram.org/bot${BOT_TOKEN}"
VOICE="${TTS_VOICE:-ru-RU-SvetlanaNeural}"

save_chat_id() { echo "CHAT_ID=$1" >> "$DIR/.env"; }

cmd="${1:-}"; shift || true
if [ "$cmd" = "chatid" ]; then
  curl -sS "$API/getUpdates" | python3 -I -c '
import sys, json
d = json.load(sys.stdin)
seen = {}
for u in d.get("result", []):
    m = u.get("message") or u.get("channel_post") or u.get("my_chat_member", {})
    c = m.get("chat") if m else None
    if c: seen[c["id"]] = c.get("title") or c.get("username") or c.get("first_name")
for k, v in seen.items(): print(k, v)
if not seen: print("Пусто: напишите любое сообщение в группу и повторите", file=sys.stderr)'
  exit 0
fi
: "${CHAT_ID:?CHAT_ID не задан. Запустите: send.sh chatid и добавьте CHAT_ID=... в bots/assistant/.env}"

case "$cmd" in
  text)
    curl -sS "$API/sendMessage" -d chat_id="$CHAT_ID" -d parse_mode=HTML \
      -d disable_web_page_preview=true --data-urlencode text="${1:?нужен текст}" ;;
  voice)
    mkdir -p "$DIR/tmp"; mp3="$DIR/tmp/v$$.mp3"; ogg="$DIR/tmp/v$$.ogg"
    VOICE="$VOICE" TEXT="${1:?нужен текст}" OUT="$mp3" python3 -I -c '
import os, asyncio, ssl, edge_tts
kw = {}
if os.environ.get("HTTPS_PROXY"): kw["proxy"] = os.environ["HTTPS_PROXY"]
asyncio.run(edge_tts.Communicate(os.environ["TEXT"], os.environ["VOICE"], **kw).save(os.environ["OUT"]))' 
    ffmpeg -loglevel error -y -i "$mp3" -c:a libopus "$ogg"
    curl -sS "$API/sendVoice" -F chat_id="$CHAT_ID" -F voice=@"$ogg"
    rm -f "$mp3" "$ogg" ;;
  photo)
    curl -sS "$API/sendPhoto" -F chat_id="$CHAT_ID" -F photo=@"${1:?нужен файл}" \
      --form-string parse_mode=HTML --form-string caption="${2:-}" ;;
  doc)
    curl -sS "$API/sendDocument" -F chat_id="$CHAT_ID" -F document=@"${1:?нужен файл}" \
      --form-string parse_mode=HTML --form-string caption="${2:-}" ;;
  *) echo "Команды: text | voice | photo | doc | chatid" >&2; exit 2 ;;
esac
echo
