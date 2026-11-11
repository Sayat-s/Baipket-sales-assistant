// Саят · Ассистент: Telegram-бот Google Apps Script-те (тегін, 24/7, сервер керек емес).
// Script Properties: BOT_TOKEN, CHAT_ID, SECRET. Хабарламалар осы кестедегі "Inbox" парағына түседі.
const MENTION = /саят|саяк|@hos_baipket/i;
const P = () => PropertiesService.getScriptProperties();
const ok_ = () => ContentService.createTextOutput('ok');

function doGet() { return ContentService.createTextOutput('assistant ok'); }

function doPost(e) {
  if (((e && e.parameter) || {}).k !== P().getProperty('SECRET')) return ok_();
  try {
    const u = JSON.parse(e.postData.contents);
    const cache = CacheService.getScriptCache();
    if (cache.get('u' + u.update_id)) return ok_();
    cache.put('u' + u.update_id, '1', 21600);
    handle_(u);
  } catch (err) { log_('error', String(err)); }
  return ok_();
}

function tg_(method, payload) {
  return UrlFetchApp.fetch('https://api.telegram.org/bot' + P().getProperty('BOT_TOKEN') + '/' + method,
    { method: 'post', payload: payload, muteHttpExceptions: true });
}
function say_(text) {
  tg_('sendMessage', { chat_id: P().getProperty('CHAT_ID'), text: text, parse_mode: 'HTML', disable_web_page_preview: true });
}
function esc_(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName('Inbox') || ss.insertSheet('Inbox');
}
function save_(kind, u, place, who, text, extra) {
  sheet_().appendRow([new Date(), u.update_id, kind, place, who, text || '', extra ? JSON.stringify(extra) : '', '']);
}
function log_(kind, text) { sheet_().appendRow([new Date(), '', kind, '', '', text, '', '']); }

function handle_(u) {
  const m = u.message;
  if (!m) return;
  const owner = Number(P().getProperty('CHAT_ID'));
  const chat = m.chat || {}, from = m.from || {};
  const text = (m.text || m.caption || '').trim();
  const low = text.toLowerCase();
  const isPrivate = chat.type === 'private';
  const place = isPrivate ? 'жеке чат' : (chat.title || 'топ');
  const who = [from.first_name, from.last_name].filter(Boolean).join(' ') || from.username || '?';

  if (isPrivate && from.id === owner) {
    if (low.indexOf('/namaz') === 0) return say_(prayerText_());
    if (low.indexOf('/help') === 0 || low.indexOf('/start') === 0) {
      return say_('<b>Мен не істей аламын</b>\n• Тапсырма: жай жазыңыз, мен қабылдап доскаға қосамын\n• <code>/tapsyrma мәтін</code> — тапсырма\n• <code>/aqsha 250000 90000 30000</code> — дүкен кірісі, дүкен шығысы, үй шығысы\n• <code>/namaz</code> — намаз уақыты\n• Дауыстық хабарлама — расшифровка жасап тапсырма етемін\nТоптарда «Саят» аталғанын өзім табамын.');
    }
    const nums = (text.match(/\d[\d ]*\d|\d/g) || []).map(function (n) { return parseInt(n.replace(/\s/g, ''), 10); });
    if (low.indexOf('/aqsha') === 0 || (/дүкен|үй|магазин/.test(low) && nums.length >= 3)) {
      if (nums.length >= 3) {
        save_('money', u, place, who, text, { shopIn: nums[0], shopOut: nums[1], homeOut: nums[2] });
        return say_('✅ <b>Қабылдадым.</b>\nДүкен кірісі: ' + fmt_(nums[0]) + ' ₸\nДүкен шығысы: ' + fmt_(nums[1]) + ' ₸\nҮй шығысы: ' + fmt_(nums[2]) + ' ₸\n<i>Доскаға қосамын.</i>');
      }
      return say_('Үш сан керек: дүкен кірісі, дүкен шығысы, үй шығысы. Мысалы: <code>/aqsha 250000 90000 30000</code>');
    }
    const media = m.voice || m.audio || m.video_note;
    if (media) {
      save_('voice', u, place, who, '', { file_id: media.file_id, duration: media.duration });
      return say_('🎙 <b>Дауыстық қабылдадым.</b>\nРасшифровка жасап, тапсырма етіп доскаға қосамын.');
    }
    if (text && /оқыдым|окыдым|оқып болдым|прочитал/.test(low) && /таң|бесін|екінті|шам|ақшам|құфтан|намаз|фаджр|зухр|аср|магриб|иша/.test(low)) {
      save_('habit', u, place, who, text, { habit: 'namaz' });
      return say_('🤲 <b>Қабылдадым:</b> ' + esc_(text.slice(0, 200)) + '\n<i>Намаз белгіленді.</i>');
    }
    if (text) {
      const body = text.replace(/^\/tapsyrma(@\w+)?\s*/i, '');
      save_('task', u, place, who, body);
      return say_('✅ <b>Қабылдадым:</b> ' + esc_(body.slice(0, 300)) + '\n<i>Доскаға қосамын.</i>');
    }
    return;
  }
  if (!isPrivate && MENTION.test(text)) {
    save_('task', u, place, who, text, { chat_title: chat.title });
    say_('✅ <b>Қабылдадым.</b> «' + esc_(place) + '» тобында ' + esc_(who) + ' сізге жазды:\n<i>' + esc_(text.slice(0, 400)) + '</i>\n<i>Тапсырма ретінде доскаға қосамын.</i>');
  }
}
function fmt_(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }

// ---- Намаз уақыты (Алматы): Таң 18°, Құфтан 17°, Екінті Ханафи. ДУМК-пен салыстырыңыз.
function prayerText_() {
  const today = Utilities.formatDate(new Date(), 'Asia/Almaty', 'yyyy-MM-dd').split('-').map(Number);
  const t = prayer_(today[0], today[1], today[2]);
  return '<b>🕌 Намаз уақыты (Алматы)</b>\n' + Object.keys(t).map(function (k) { return '• ' + k + ': <b>' + t[k] + '</b>'; }).join('\n') +
    '\n<i>Есептелген уақыт, ДУМК кестесімен салыстырыңыз.</i>';
}
function prayer_(y, mo, d) {
  const LAT = 43.2389, LON = 76.8897, TZ = 5, FAJR = 18, ISHA = 17, ASRF = 2, R = Math.PI / 180, D = 180 / Math.PI;
  const a = Math.floor((14 - mo) / 12), yy = y + 4800 - a, mm = mo + 12 * a - 3;
  const jdn = d + Math.floor((153 * mm + 2) / 5) + 365 * yy + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400) - 32045;
  const jd = jdn - 0.5 + 0.5 - TZ / 24;
  const dd = jd - 2451545.0;
  const g = (357.529 + 0.98560028 * dd) % 360, q = (280.459 + 0.98564736 * dd) % 360;
  const L = (q + 1.915 * Math.sin(g * R) + 0.020 * Math.sin(2 * g * R)) % 360;
  const e = 23.439 - 0.00000036 * dd;
  const ra = ((Math.atan2(Math.cos(e * R) * Math.sin(L * R), Math.cos(L * R)) * D) / 15 % 24 + 24) % 24;
  const decl = Math.asin(Math.sin(e * R) * Math.sin(L * R)) * D;
  let eqt = q / 15 - ra; eqt = ((eqt + 12) % 24 + 24) % 24 - 12;
  const noon = 12 + TZ - LON / 15 - eqt;
  function ha(angle) {
    const x = (-Math.sin(angle * R) - Math.sin(LAT * R) * Math.sin(decl * R)) / (Math.cos(LAT * R) * Math.cos(decl * R));
    return Math.acos(Math.max(-1, Math.min(1, x))) * D / 15;
  }
  const asrAngle = -Math.atan(1 / (ASRF + Math.tan(Math.abs(LAT - decl) * R))) * D;
  function hm(v) { const mins = Math.round(v * 60); return ('0' + Math.floor(mins / 60)).slice(-2) + ':' + ('0' + (mins % 60)).slice(-2); }
  return {
    'Таң (Фаджр)': hm(noon - ha(FAJR)), 'Күн шығуы': hm(noon - ha(0.833)), 'Бесін (Зухр)': hm(noon + 2 / 60),
    'Екінті (Аср)': hm(noon + ha(asrAngle)), 'Ақшам (Магриб)': hm(noon + ha(0.833)), 'Құфтан (Иша)': hm(noon + ha(ISHA))
  };
}
