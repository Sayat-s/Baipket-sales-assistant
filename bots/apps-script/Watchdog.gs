// Сторож: проверяет ваших Telegram-ботов и пишет в Telegram, если что-то сломалось.
// Использует say_() из Code.gs (тот же проект). Токены ботов лежат в Script Properties.
// Проверка каждые 30 минут + короткий отчёт каждое утро в 09:00 (Алматы).
const WATCH = [
  { name: 'Саят · Ассистент (@assistsayatbot)', prop: 'BOT_TOKEN' },
  { name: 'ОТЧЕТ БОТ (@baipketsalesbot)', prop: 'TOKEN_SALES' },
  { name: 'ОКК бот (@OKKbaipketbot)', prop: 'TOKEN_OKK' },
  { name: 'AI BOT (@baipketbot)', prop: 'TOKEN_AI' },
  { name: 'Бот Кейс (@casebaipbot)', prop: 'TOKEN_CASE' },
  { name: 'Baipket РОП · Ассистент (@sayatassistantbot)', prop: 'TOKEN_ROP' },
  { name: 'Salestodaybot (@salesrememberbot)', prop: 'TOKEN_REMIND' }
];
const PENDING_LIMIT = 50;       // сколько необработанных сообщений считаем проблемой
const ERROR_FRESH_SEC = 3600;   // ошибка webhook за последний час

function wdCall_(token, method) {
  try {
    const r = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/' + method, { muteHttpExceptions: true });
    return JSON.parse(r.getContentText());
  } catch (e) { return { ok: false, description: String(e) }; }
}

// Apps Script отвечает Telegram редиректом 302: это не поломка, сообщение обрабатывается.
function wdIs302_(w) {
  return String(w.last_error_message || '').indexOf('302') >= 0 && String(w.url || '').indexOf('script.google.com') >= 0;
}

function wdCheck_() {
  const props = PropertiesService.getScriptProperties();
  const res = [];
  WATCH.forEach(function (b) {
    const token = props.getProperty(b.prop);
    if (!token) return; // токен не задан, бот не проверяем
    const issues = [];
    const me = wdCall_(token, 'getMe');
    if (!me.ok) {
      issues.push('не отвечает или токен недействителен (' + (me.description || 'нет ответа') + ')');
    } else {
      const wh = wdCall_(token, 'getWebhookInfo');
      if (wh.ok && wh.result) {
        const w = wh.result, now = Math.floor(Date.now() / 1000);
        if (w.last_error_date && now - w.last_error_date < ERROR_FRESH_SEC && !wdIs302_(w)) {
          issues.push('ошибка доставки: ' + (w.last_error_message || '?'));
        }
        if ((w.pending_update_count || 0) > PENDING_LIMIT) {
          issues.push('накопилось необработанных сообщений: ' + w.pending_update_count);
        }
      }
    }
    res.push({ prop: b.prop, name: b.name, username: me.ok ? me.result.username : '', issues: issues });
  });
  return res;
}

// Каждые 30 минут: пишет только когда состояние изменилось (сломалось или починилось).
function checkBots() {
  const props = PropertiesService.getScriptProperties();
  const old = JSON.parse(props.getProperty('WD_STATE') || '{}');
  const next = {};
  const lines = [];
  wdCheck_().forEach(function (r) {
    const key = r.issues.join('|');
    next[r.prop] = key;
    const before = old[r.prop] || '';
    if (key && key !== before) lines.push('🔴 <b>' + esc_(r.name) + '</b>\n' + r.issues.map(function (i) { return '• ' + esc_(i); }).join('\n'));
    if (!key && before) lines.push('🟢 <b>' + esc_(r.name) + '</b> снова работает');
  });
  props.setProperty('WD_STATE', JSON.stringify(next));
  if (lines.length) say_('<b>Сторож ботов</b>\n\n' + lines.join('\n\n'));
}

// Каждое утро в 09:00: короткая сводка.
function dailyReport() {
  const r = wdCheck_();
  if (!r.length) return say_('<b>Сторож ботов</b>\nТокены ботов не добавлены в свойства скрипта.');
  const bad = r.filter(function (x) { return x.issues.length; });
  const ok = r.length - bad.length;
  let text = '<b>Сторож ботов · утро</b>\nРаботают: <b>' + ok + ' из ' + r.length + '</b>';
  if (bad.length) text += '\n\n' + bad.map(function (x) { return '🔴 ' + esc_(x.name) + ': ' + esc_(x.issues.join('; ')); }).join('\n');
  say_(text);
}

// Один раз запустите вручную: создаёт расписание.
function setupTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    const f = t.getHandlerFunction();
    if (f === 'checkBots' || f === 'dailyReport') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('checkBots').timeBased().everyMinutes(30).create();
  ScriptApp.newTrigger('dailyReport').timeBased().everyDays(1).atHour(9).inTimezone('Asia/Almaty').create();
  say_('✅ Сторож ботов включён: проверка каждые 30 минут и сводка в 09:00.');
}

// Разово: покажет, ГДЕ работает каждый бот (по адресу webhook) и нет ли ошибок.
// Токены не показываются; от адреса остаётся только домен.
function reportHosting() {
  const props = PropertiesService.getScriptProperties();
  const rows = [];
  WATCH.forEach(function (b) {
    const token = props.getProperty(b.prop);
    if (!token) return;
    const me = wdCall_(token, 'getMe');
    if (!me.ok) { rows.push('🔴 <b>' + esc_(b.name) + '</b>\nтокен недействителен или бот удалён'); return; }
    const w = (wdCall_(token, 'getWebhookInfo').result) || {};
    let where;
    if (w.url) {
      const m = String(w.url).match(/^https?:\/\/([^\/?#]+)/);
      where = 'webhook: ' + (m ? m[1] : '?');
    } else {
      where = 'webhook нет (бот сам опрашивает Telegram, значит где-то запущен процесс)';
    }
    rows.push('<b>' + esc_(b.name) + '</b> (@' + esc_(me.result.username) + ')\n' + esc_(where) +
      '\nнеобработанных: ' + (w.pending_update_count || 0) +
      (w.last_error_message ? '\nпоследняя ошибка: ' + esc_(w.last_error_message) : ''));
  });
  say_(rows.length ? '<b>Где работают боты</b>\n\n' + rows.join('\n\n') : 'Токены ботов не добавлены.');
}
