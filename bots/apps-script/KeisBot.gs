// Бот Кейс («Кейстер») на Google Apps Script: тегін, 24/7. Python-нұсқасының (bot.py) еркін іздеуі, ИИ-сыз.
// Script Properties: TOKEN_CASE (бот токені), CASES_FILE_ID (cases.csv файлының Drive ID), ADMIN_IDS (міндетті емес, үтірмен).
// Webhook: doPost (Code.gs) ?bot=keis параметрімен осыған бағыттайды. Бір рет keisSetWebhook() іске қосыңыз.

const KEIS_WC = 'a-z0-9_а-яёәіңғүұқөһ';
const KEIS_CONCEPTS = [
  [['товар', 'ритейл', 'розниц', 'оптом', 'магазин', 'дүкен', 'маркетплейс', 'сауда', 'продаж'], ['товар', 'ритей', 'оптом', 'магаз', 'дүкен', 'парфю', 'киім', 'одежд', 'автоз', 'автот', 'мебел', 'ұсақ']],
  [['общепит', 'ресторан', 'кафе', 'кухн', 'тамақ', 'ас', 'суши', 'фастфуд', 'horeca', 'еда', 'пицц', 'кофейн'], ['общеп', 'ресто', 'кафе', 'кухня', 'тамақ', 'fast', 'суши', 'horec']],
  [['медицин', 'клиник', 'дәрігер', 'врач', 'стомат', 'здоров', 'реабилит', 'оздоров'], ['медиц', 'клини', 'дәріг', 'врач', 'стома', 'здоро', 'реаби', 'оздор', 'biosl']],
  [['инфобизнес', 'инфопродукт', 'онлайн', 'білім', 'образован', 'школ', 'мектеп', 'обучен', 'оқыту', 'академ', 'эксперт', 'коуч', 'тренинг'], ['білім', 'образ', 'школ', 'мекте', 'акаде', 'онлай', 'экспе', 'обуче', 'эксперт']],
  [['туризм', 'тур', 'саяхат', 'путешеств', 'travel'], ['туриз', 'trave', 'саяха', 'путеш', 'safar']],
  [['недвижим', 'жылжымайтын', 'ремонт', 'құрылыс', 'строител', 'застройщик', 'квартир'], ['недви', 'жылжы', 'ремон', 'құрыл', 'строи', 'застр']],
  [['агентств', 'агенттік', 'smm', 'таргет', 'сммщик'], ['агент', 'smm', 'тарге']],
  [['бренд', 'блогер', 'личный', 'жеке'], ['бренд', 'блоге', 'личны', 'жеке']],
  [['b2b', 'b2g', 'корпоратив', 'тендер', 'мемлекет'], ['b2b', 'b2g', 'корпо', 'тенде', 'мемле']],
  [['логистик', 'доставк', 'тасымал', 'перевозк', 'пошта'], ['логис', 'доста', 'тасым', 'перев', 'пошта']],
  [['руковод', 'басшы', 'директор', 'ceo', 'партнер', 'серіктес'], ['руков', 'басшы', 'дирек', 'ceo', 'партн']],
  [['мебель', 'мебел'], ['мебел']],
  [['косметик', 'косметолог', 'красот', 'сұлулық', 'салон', 'барбер', 'парфюм', 'парфюмер', 'аромат', 'beauty', 'уход', 'массаж', 'эстетик'], ['косме', 'красо', 'сұлул', 'салон', 'барбе', 'парфю', 'арома', 'массаж', 'beaut']],
  [['видео', 'продакшн', 'фото', 'фотограф', 'съемк', 'монтаж', 'дизайн', 'креатив', 'контент', 'видеограф'], ['видео', 'продак', 'фото', 'дизай', 'креат', 'конте', 'фотог', 'фотос', 'монта']],
  [['производств', 'өндіріс', 'завод', 'цех', 'терезе', 'окна', 'пластик', 'потолок', 'натяжн'], ['өндір', 'произ', 'завод', 'цех', 'терез', 'пласт', 'натяж', 'потол']],
  [['реклам', 'неон', 'наружн', 'баннер'], ['рекла', 'неон', 'наруж']],
  [['грант', 'субсиди', 'финанс', 'қаржы', 'инвест', 'кредит'], ['грант', 'субси', 'қаржы', 'финан', 'инвес', 'креди']],
  [['ai', 'ии', 'жасанды', 'интеллект', 'нейросет', 'искусственн', 'нейро'], ['ai', 'жасан', 'интел', 'нейро', 'искус']],
  [['спорт', 'фитнес', 'тренажер', 'зал'], ['спорт', 'фитне', 'invic']],
  [['e-commerce', 'ecommerce', 'интернет-магазин', 'онлайн-магазин', 'маркетплейс', 'wildberries', 'kaspi'], ['e-com', 'ecomm', 'марке', 'kaspi', 'wildb']],
  [['діни', 'дін', 'религ', 'мұсылман', 'мечеть'], ['діни', 'религ', 'мұсыл', 'қмдб']],
  [['красот', 'салон', 'косметик', 'сұлулық', 'барбер'], ['красо', 'салон', 'косме', 'сұлул', 'барбе']],
  [['авто', 'машин', 'запчаст', 'автотовар'], ['авто', 'машин', 'запча', 'mercedes', 'range']],
  [['алматы', 'алмат'], ['алмат']],
  [['астана', 'нур-султан'], ['астан']],
  [['шымкент', 'чимкент'], ['шымке']],
  [['костанай', 'қостанай'], ['костан', 'қоста']],
  [['туркестан', 'түркістан'], ['турке', 'түрік']],
  [['атырау'], ['атыра']],
  [['тараз'], ['тараз']]
];
const KEIS_ROLES = [
  [['видеограф', 'видеомейкер', 'оператор', 'монтажер', 'монтажёр'], ['видео', 'опера', 'монта']],
  [['таргетолог'], ['тарге']],
  [['маркетолог'], ['марке']],
  [['smm', 'сммщик', 'смм'], ['smm', 'смм']],
  [['контент-мейкер', 'контентмейкер', 'контент-продюсер', 'продюсер', 'сценарист', 'копирайтер'], ['конте', 'проду', 'сцена', 'копир']],
  [['дизайнер'], ['дизай']],
  [['фотограф'], ['фото']],
  [['трафик-менеджер', 'трафик менеджер'], ['трафи']],
  [['роп', 'rop', 'руководитель отдела продаж'], ['роп', 'rop', 'руков', 'прода']],
  [['аналитик'], ['анали']],
  [['кәсіпкер', 'предприниматель', 'бизнесмен', 'владелец', 'иесі'], ['кәсіп', 'предп', 'бизне', 'агент']],
  [['руководитель', 'басшы', 'директор', 'ceo'], ['руков', 'басшы', 'дирек', 'ceo']]
];
const KEIS_INTENT_WORDS = ['оборот', 'чек', 'доход', 'табыс', 'выручк', 'рост', 'өсті', 'вырос', 'результат', 'цифр', 'нәтиже', 'өскен', 'өсіп', 'өсу', 'рос', 'айналым', 'прибыл', 'заработ', 'миллион', 'млн', 'деньги', 'ақша', 'тапты', 'өсім', 'увелич'];
const KEIS_STOP_WORDS = ['нужен', 'нужно', 'мне', 'кейс', 'кейсы', 'кейстер', 'кейсті', 'керек', 'бойынша', 'про', 'для', 'есть', 'дай', 'бер', 'покажи', 'студент', 'сфере', 'бизнес', 'бизнесі', 'бизнесе', 'туралы', 'маған', 'найди', 'ищу', 'где', 'бар', 'барма', 'бармы', 'бар ма', 'және', 'мен', 'пен', 'сала', 'саласы', 'саласынан', 'іздеп', 'тап', 'мынау', 'бұл', 'емес', 'емеско', 'это', 'эт', 'көрсет', 'ұсын', 'посоветуй', 'подскажи', 'сфера', 'направление', 'бағыт', 'нише', 'ниша', 'жеке', 'личный', 'личная', 'жоқ', 'жок', 'нет', 'сфера', 'сферасы', 'сферасынан', 'салада', 'саласында', 'қандай', 'какой', 'какие', 'кейсі', 'кейсы'];
const KEIS_NOTHING_HINT = 'Нақты кейс табылмады / Точных кейсов не нашёл. Мына бағыттарды көріңіз / Попробуйте: товарка, общепит, медицина, туризм, білім беру/онлайн, недвижимость/құрылыс, агенттік/SMM, жеке бренд, логистика, B2B, мебель. Немесе студенттің аты.';

function keisStem_(w) { return w.slice(0, 5); }
function keisTokens_(t) { return (String(t).toLowerCase().replace(/ё/g, 'е').match(/[a-zа-яәіңғүұқөһ0-9]+/g)) || []; }
function keisWordSet_(t) { const s = new Set(); keisTokens_(t).forEach(function (w) { if (w.length >= 3) s.add(keisStem_(w)); }); return s; }
function keisEsc_(s) { return String(s).replace(/[.*+?^${}()|[\]\\\-]/g, '\\$&'); }
function keisHtml_(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
const KEIS_STEMS = KEIS_CONCEPTS.map(function (c) { return [c[0].map(keisStem_), c[1]]; });
const KEIS_INTENT = new Set(KEIS_INTENT_WORDS.map(keisStem_));
const KEIS_STOP = new Set(KEIS_STOP_WORDS.map(keisStem_).concat(KEIS_STOP_WORDS));
const KEIS_STREAM_RE = new RegExp('(?:(\\d{1,2})\\s*[-–]?\\s*(?:поток|лек|ағын)[' + KEIS_WC + ']*|(?:поток|лек|ағын)[' + KEIS_WC + ']*\\s*(\\d{1,2}))', 'gi');

function keisHit_(exp, ws) {
  for (const e of exp) {
    if (ws.has(e)) return true;
    if (e.length < 5) { for (const w of ws) { if (w.indexOf(e) === 0) return true; } }
  }
  return false;
}

// ---------- Деректер: Drive-тағы cases.csv ----------
function keisLoadCases_() {
  const id = PropertiesService.getScriptProperties().getProperty('CASES_FILE_ID');
  if (!id) return [];
  const show = true;
  let text = DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8').replace(/^﻿/, '');
  const rows = Utilities.parseCsv(text);
  if (!rows.length) return [];
  const head = rows[0].map(function (h) { return String(h).trim(); });
  const col = function (r, name, def) { const i = head.indexOf(name); const v = i >= 0 ? String(r[i] || '').trim() : ''; return v || (def || ''); };
  const cases = [];
  rows.slice(1).forEach(function (r, idx) {
    const name = col(r, 'Аты-жөні');
    if (!name) return;
    cases.push({
      id: idx + 1,
      name: name.replace(/\s*[—–-]\s*видео\s*$/i, ''),
      stream: col(r, 'Лек/поток'), role: col(r, 'Рөлі (А→Б)'), niche: col(r, 'Ниша / компания'), tags: col(r, 'Тег'),
      result: col(r, 'Нәтиже (цифр)'), before: col(r, 'Курсқа дейін'), after: col(r, 'Курстан кейін (не істеді)'), link: col(r, 'Сілтеме'),
      phone: show ? col(r, 'Телефон') : '', tg: col(r, 'Telegram'), ig: col(r, 'Instagram'), cur: col(r, 'Қазіргі жұмыс'),
      inc: col(r, 'Табыс (кастдев)'), resp: col(r, 'Жауапкершілік'), hard: col(r, 'Қиындық'), help: col(r, 'Көмек керек'),
      src: col(r, 'Дерек (кейс/кастдев)', 'кейс')
    });
  });
  return cases;
}

// ---------- Іздеу ----------
function keisFreeSearch_(CASES, query, offset) {
  const ql = String(query).toLowerCase().replace(/ё/g, 'е');
  const nums = new Set();
  let m;
  const sre = new RegExp(KEIS_STREAM_RE.source, 'gi');
  while ((m = sre.exec(ql)) !== null) { nums.add(m[1] || m[2]); }
  const belt = ['белбеу', 'пояс', 'belt'].some(function (w) { return ql.indexOf(w) >= 0; });
  let qlClean = ql.replace(new RegExp(KEIS_STREAM_RE.source, 'gi'), ' ');
  const roleGroups = [];
  const exactRoleWords = [];
  KEIS_ROLES.forEach(function (r) {
    const trigs = r[0], stems = r[1];
    const mk = function (t) { return new RegExp('(?<![' + KEIS_WC + '])' + keisEsc_(t) + '[' + KEIS_WC + ']*', 'i'); };
    if (trigs.some(function (t) { return mk(t).test(qlClean); })) {
      roleGroups.push(new Set(stems));
      trigs.forEach(function (t) { if (t.length >= 5 && ql.indexOf(t) >= 0) exactRoleWords.push(t); });
      trigs.forEach(function (t) { qlClean = qlClean.replace(new RegExp(mk(t).source, 'gi'), ' '); });
    }
  });
  let toks = keisTokens_(qlClean).filter(function (w) { return w.length >= 3 && !KEIS_STOP.has(w) && !KEIS_STOP.has(keisStem_(w)); });
  if (belt) toks = toks.filter(function (w) { return !['белб', 'пояс', 'поя', 'қара', 'черн', 'чёрн', 'bel'].some(function (p) { return w.indexOf(p) === 0; }); });
  const old = ql.indexOf('ескі') >= 0 && (ql.indexOf('поток') >= 0 || ql.indexOf('ағын') >= 0);
  if (old) toks = toks.filter(function (w) { return !['ескі', 'поток', 'ағын'].some(function (p) { return w.indexOf(p) === 0; }); });
  const wantNum = toks.some(function (w) { return KEIS_INTENT.has(keisStem_(w)); });
  toks = toks.filter(function (w) { return !KEIS_INTENT.has(keisStem_(w)); });
  let pool = CASES.slice();
  const flt = [];
  if (nums.size) {
    pool = pool.filter(function (c) { const p = c.stream.split(/\s+/).filter(Boolean); return p.length && nums.has(p[0].replace(/^\(|\)$/g, '')); });
    flt.push('поток ' + Array.from(nums).sort().join('/'));
  }
  if (old) { pool = pool.filter(function (c) { return c.stream.toLowerCase().indexOf('ескі') === 0; }); flt.push('ескі поток'); }
  if (belt) { pool = pool.filter(function (c) { return c.stream.toLowerCase().indexOf('белбеу') >= 0; }); flt.push('қара белбеу'); }
  const fltNote = flt.length ? ' [' + flt.join(', ') + ']' : '';
  const dash = ['', '—', '-'];
  if (!toks.length && !roleGroups.length) {
    if (flt.length || wantNum) {
      let has = pool.filter(function (c) { return dash.indexOf(c.result) < 0; });
      if (!has.length) has = pool;
      return [has.slice(offset, offset + 3), has.length, has.length ? 'Табылды / Найдено: ' + has.length + fltNote : ''];
    }
    return [[], 0, ''];
  }
  const qstems = toks.map(keisStem_);
  const inConcepts = new Set();
  KEIS_STEMS.forEach(function (c) { c[0].forEach(function (s) { inConcepts.add(s); }); });
  const nameHits = [];
  (roleGroups.length ? [] : pool).forEach(function (c) {
    const nm = keisWordSet_(c.name);
    if (qstems.some(function (st) { return nm.has(st) && !inConcepts.has(st) && st.length >= 4; })) nameHits.push(c);
  });
  if (nameHits.length) return [nameHits.slice(offset, offset + 3), nameHits.length, 'Студент табылды / Найден студент: ' + nameHits.length];
  const expansions = qstems.map(function (st) {
    const exp = new Set([st]);
    KEIS_STEMS.forEach(function (c) { if (c[0].indexOf(st) >= 0) c[1].forEach(function (x) { exp.add(x); }); });
    return exp;
  });
  const scored = [];
  pool.forEach(function (c) {
    const niche = keisWordSet_(c.niche);
    const head = new Set(Array.from(niche).concat(Array.from(keisWordSet_(c.tags))));
    const body = keisWordSet_([c.role, c.before, c.after, c.result, c.cur, c.inc, c.resp, c.hard, c.help].join(' '));
    let mixed = 0;
    KEIS_CONCEPTS.forEach(function (cc) { if (keisHit_(new Set(cc[1]), niche)) mixed += 1; });
    let sc = 0, matched = 0;
    const roleW = keisWordSet_(c.role);
    roleGroups.forEach(function (rg) {
      if (keisHit_(rg, roleW)) { sc += 8; matched += 1; }
      else if (keisHit_(rg, niche)) { sc += 5; matched += 1; }
      else if (keisHit_(rg, body)) { sc += 1; matched += 1; }
    });
    const rn = (c.role + ' ' + c.niche).toLowerCase();
    if (roleGroups.length && exactRoleWords.some(function (w) { return rn.indexOf(w) >= 0; })) sc += 4;
    qstems.forEach(function (st, i) {
      const exp = expansions[i];
      if (niche.has(st) && mixed <= 1) sc += 2;
      if (keisHit_(exp, niche)) { sc += 7 - 1.5 * Math.max(mixed - 1, 0); matched += 1; }
      else if (keisHit_(exp, head)) { sc += 4; matched += 1; }
      else if (keisHit_(exp, body)) { sc += 1; matched += 1; }
    });
    if (sc) {
      if (dash.indexOf(c.result) < 0) sc += 1.5 + (wantNum ? 3 : 0);
      if (c.src.indexOf('кейс') >= 0) sc += 1.5;
      sc += matched;
      scored.push([sc, c]);
    }
  });
  scored.sort(function (a, b) { return b[0] - a[0]; });
  let exact = scored.filter(function (x) { return x[0] >= 4; });
  if (roleGroups.length) exact = scored.filter(function (x) { return x[0] >= 5; });
  let found, note;
  if (exact.length) { found = exact.map(function (x) { return x[1]; }); note = 'Табылды / Найдено кейстер: %d'; }
  else { found = scored.map(function (x) { return x[1]; }); note = 'Дәл сәйкестік жоқ, жақын кейстер / Точного нет, близкие: %d'; }
  const seen = {}, uniq = [];
  found.forEach(function (c) {
    const key = c.name.replace(/\(.*?\)|[—–].*/g, '').trim().toLowerCase();
    if (seen[key] && key.indexOf('@') !== 0) return;
    seen[key] = true; uniq.push(c);
  });
  found = uniq;
  const total = found.length;
  return [found.slice(offset, offset + 3), total, found.length ? note.replace('%d', total) + fltNote : ''];
}

function keisCard_(c) {
  const e = keisHtml_, dash = ['', '—', '-'];
  const isCase = c.src.indexOf('кейс') >= 0;
  const lines = ['👤 <b>' + e(c.name) + '</b>' + (c.stream ? ' · поток ' + e(c.stream) : '')];
  if (isCase) {
    const hasAB = dash.indexOf(c.role) < 0;
    if (hasAB) lines.push('🔀 Точка А → Б: ' + e(c.role));
    if (dash.indexOf(c.niche) < 0) lines.push('🏷 Ниша: ' + e(c.niche));
    if (dash.indexOf(c.result) < 0) lines.push('📈 Результат: ' + e(c.result));
    if (hasAB && dash.indexOf(c.before) < 0) lines.push('⬅️ До: ' + e(c.before));
    if (hasAB && dash.indexOf(c.after) < 0) lines.push('➡️ После: ' + e(c.after));
    if (c.cur && c.cur !== c.role) lines.push('💼 Қазір: ' + e(c.cur));
    if (c.inc && c.inc !== c.result) lines.push('💰 Табыс: ' + e(c.inc));
    if (c.hard) lines.push('⚠️ Қиындық: ' + e(c.hard.slice(0, 200)));
  } else {
    if (c.cur) lines.push('💼 Қазір: ' + e(c.cur));
    if (c.inc) lines.push('💰 Табыс: ' + e(c.inc));
    if (c.resp) lines.push('🎯 Жауапкершілік: ' + e(c.resp.slice(0, 200)));
    if (c.hard) lines.push('⚠️ Қиындық: ' + e(c.hard.slice(0, 200)));
  }
  const contact = [];
  if (c.phone) contact.push('📞 ' + e(c.phone));
  if (c.tg) contact.push('✈️ ' + e(c.tg));
  if (c.ig) { const h = c.ig.replace(/\/+$/, '').split('/').pop().replace(/^@/, ''); contact.push('📷 Instagram: @' + e(h) + ' https://instagram.com/' + e(h)); }
  if (c.link) contact.push('🔗 Кейс-пост: ' + c.link);
  lines.push(contact.length ? contact.join('\n') : 'Контакт: уточните у куратора');
  return lines.join('\n');
}

// ---------- Telegram ----------
function keisTg_(method, payload) {
  const token = PropertiesService.getScriptProperties().getProperty('TOKEN_CASE');
  return UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/' + method, { method: 'post', payload: payload, muteHttpExceptions: true });
}
function keisLog_(obj) { try { log_('keis', JSON.stringify(obj)); } catch (e) {} }
function keisSend_(chatId, text, html) {
  const r = keisTg_('sendMessage', { chat_id: chatId, text: text, parse_mode: html ? 'HTML' : undefined, disable_web_page_preview: true });
  let out = {};
  try { out = JSON.parse(r.getContentText()); } catch (e) { out = { ok: false, description: 'bad json' }; }
  if (out.ok === false && html) {
    const r2 = keisTg_('sendMessage', { chat_id: chatId, text: text.replace(/<[^>]+>/g, '') });
    try { out = JSON.parse(r2.getContentText()); } catch (e) { out = { ok: false, description: 'bad json' }; }
  }
  if (out.ok === false) keisLog_({ send_error: out.description, chat: chatId });
}
function keisMe_() {
  const cache = CacheService.getScriptCache();
  let me = cache.get('keis_me');
  if (!me) {
    me = keisTg_('getMe', {}).getContentText();
    cache.put('keis_me', me, 21600);
  }
  return JSON.parse(me).result;
}

function keisHandle_(u) {
  try {
    const t0 = Date.now();
    keisHandleInner_(u);
    keisLog_({ ok: true, ms: Date.now() - t0, text: String((u.message && u.message.text) || '').slice(0, 30) });
  } catch (err) { keisLog_({ err: String(err) }); }
}
function keisHandleInner_(u) {
  const m = u.message;
  if (!m || !m.text) return;
  const chat = m.chat, cache = CacheService.getScriptCache();
  const me = keisMe_();
  const lastKey = 'keis_last_' + chat.id;
  const getLast = function () { const v = cache.get(lastKey); return v ? JSON.parse(v) : null; };
  let text = m.text;
  const cmd = text.charAt(0) === '/' ? text.split(/[\s@]/)[0].toLowerCase() : '';
  if (cmd === '/start') {
    return keisSend_(chat.id, 'Сәлем! Мен кейстерді іздеймін. Мысалы: «@' + me.username + ' товарка бойынша кейс керек».\nПривет! Я ищу кейсы студентов. Пример: «@' + me.username + ' нужен кейс по общепиту».\n/stats — сколько кейсов в базе');
  }
  if (cmd === '/stats') return keisSend_(chat.id, 'В базе кейсов: ' + keisLoadCases_().length);
  if (cmd === '/reload') {
    const admins = String(PropertiesService.getScriptProperties().getProperty('ADMIN_IDS') || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    if (admins.length && admins.indexOf(String(m.from.id)) < 0) return;
    return keisSend_(chat.id, 'Перезагружено: ' + keisLoadCases_().length + ' кейсов');
  }
  if (cmd) return;
  if (chat.type !== 'private') {
    const low = text.toLowerCase();
    const mentioned = low.indexOf('@' + me.username.toLowerCase()) >= 0;
    const replied = m.reply_to_message && m.reply_to_message.from && m.reply_to_message.from.id === me.id;
    const norm = text.trim().toLowerCase().replace(/ё/g, 'е');
    const bareMore = ['еще', 'тағы', 'more', 'еще кейс', 'тағы кейс'].indexOf(norm) >= 0 && getLast();
    if (!(mentioned || replied || bareMore)) return;
    text = text.replace(new RegExp('@' + keisEsc_(me.username), 'ig'), '').trim();
  }
  if (!text) return;
  keisAnswer_(chat.id, text, getLast, function (v) { cache.put(lastKey, JSON.stringify(v), 21600); });
}

function keisAnswer_(chatId, query, getLast, setLast) {
  const ql = query.trim().toLowerCase().replace(/ё/g, 'е');
  const neg = ['емес', 'не то', 'неверно', 'неправильно', 'ошибк', 'қате', 'дұрыс емес'].some(function (w) { return ql.indexOf(w) >= 0; });
  const more = ['еще', 'тағы', 'еще кейс', 'more'].indexOf(ql) >= 0 || neg;
  let offset = 0;
  if (more) {
    const last = getLast();
    if (!last) return keisSend_(chatId, 'Алдымен сұрау жазыңыз / Сначала напишите запрос, например: «товарка».');
    query = last.q; offset = last.offset + 3;
    if (neg) keisSend_(chatId, 'Түсіндім, келесі нұсқалар / Понял, вот другие варианты:');
  }
  const CASES = keisLoadCases_();
  const res = keisFreeSearch_(CASES, query, offset);
  const found = res[0], total = res[1], note = res[2];
  if (!found.length) {
    if (more && !neg) return keisSend_(chatId, 'Бұдан артық кейс жоқ / Больше кейсов по этому запросу нет. Жаңа сұрау жазыңыз / Напишите новый запрос.');
    if (neg) return keisSend_(chatId, 'Басқа нұсқа жоқ / Других вариантов нет. Нақтырақ жазып көріңіз / Попробуйте уточнить запрос.');
    return keisSend_(chatId, KEIS_NOTHING_HINT);
  }
  setLast({ q: query, offset: offset });
  if (note) keisSend_(chatId, note);
  found.forEach(function (c) { keisSend_(chatId, keisCard_(c), true); });
  if (total > offset + 3) keisSend_(chatId, 'Тағы ' + (total - offset - 3) + ' кейс бар. «ещё» деп жазыңыз / напишите «ещё».');
}

// ---------- Бір реттік қызметтік функциялар (редакторда қолмен іске қосасыз) ----------
// 1) Деректер дұрыс оқылғанын тексереді және Telegram-ға есеп жібереді.
function keisCheck() {
  const cases = keisLoadCases_();
  const sample = cases.length ? cases[0] : null;
  let msg = '<b>Бот Кейс: тексеру</b>\nКейс саны: <b>' + cases.length + '</b>';
  if (!PropertiesService.getScriptProperties().getProperty('CASES_FILE_ID')) msg += '\n🔴 CASES_FILE_ID свойствосы жоқ';
  if (sample) {
    const empty = ['stream', 'niche', 'result', 'role'].filter(function (k) { return !sample[k]; });
    msg += '\nБірінші жазба: ' + keisHtml_(sample.name) + (empty.length ? '\n⚠️ Бос өрістер: ' + empty.join(', ') : '');
  } else msg += '\n🔴 Жазба табылмады: файл ID немесе бағандар аты («Аты-жөні») сәйкес емес.';
  say_(msg);
}
// 2) Telegram-ды осы скриптке қосады (webhook). Алдымен Mac-тағы ескі ботты тоқтатыңыз.
// Ескерту: редактордан іске қосқанда ScriptApp.getService().getUrl() "/dev" мекенжайын қайтарады, ол жұмыс істемейді.
// Сондықтан тұрақты "/exec" мекенжайы қолданылады (WEBAPP_URL свойствосы болса, соны алады).
const KEIS_EXEC_URL = 'https://script.google.com/macros/s/AKfycbyIP-sAIHtAnQ2PlvS2Irs31ubBodosqpYOckIBwsODYTmksEWH-H-CveX41GiYE1y9/exec';
function keisSetWebhook() {
  const p = PropertiesService.getScriptProperties();
  const base = p.getProperty('WEBAPP_URL') || KEIS_EXEC_URL;
  if (!/\/exec$/.test(base)) { say_('🔴 Webhook орнатылмады: мекенжай /exec-пен аяқталуы керек.'); return; }
  const url = base + '?k=' + p.getProperty('SECRET') + '&bot=keis';
  const r = keisTg_('setWebhook', { url: url, allowed_updates: JSON.stringify(['message']) });
  say_('Бот Кейс webhook: ' + keisHtml_(JSON.parse(r.getContentText()).description || 'ok'));
}
// 2б) Webhook қайда бағытталғанын көрсетеді (токенсіз): /exec болуы керек.
function keisWebhookInfo() {
  const w = JSON.parse(keisTg_('getWebhookInfo', {}).getContentText()).result || {};
  const m = String(w.url || '').match(/^https?:\/\/([^\/?#]+)(\/[^?#]*)?/);
  const host = m ? m[1] : 'жоқ';
  const last = m && m[2] ? m[2].split('/').pop() : '';
  const viaWorker = /workers\.dev$/.test(host) && last === 'keis';
  const direct = host === 'script.google.com' && last === 'exec' && String(w.url || '').indexOf('bot=keis') >= 0;
  const state = viaWorker ? '✅ Worker → Бот Кейс' : (direct ? '✅ тікелей Apps Script' : '🔴 дұрыс емес мекенжай');
  say_('<b>Бот Кейс: webhook</b>\nДомен: ' + keisHtml_(host) + '\nСоңы: ' + keisHtml_(last) + '\nЖағдай: ' + state +
    '\nКезекте: ' + (w.pending_update_count || 0) +
    (w.last_error_message ? '\nСоңғы қате: ' + keisHtml_(w.last_error_message) : ''));
}
// 2в) Іздеу жұмысын тексереді (контактсыз, тек сандар).
function keisSelfTest() {
  const cases = keisLoadCases_();
  const q = ['товарка', 'общепит', 'медицина', 'видеограф'];
  const rows = q.map(function (x) { const r = keisFreeSearch_(cases, x, 0); return keisHtml_(x) + ': ' + r[1]; });
  say_('<b>Бот Кейс: сынақ</b>\nКейс саны: <b>' + cases.length + '</b>\n' + rows.join('\n'));
}
// 2г) Webhook-ты Cloudflare Worker арқылы қосады (жылдам, 302-сіз). Алдымен Worker дайын болуы керек.
// Мекенжай: WORKER_URL свойствосы немесе төмендегі тұрақты.
const KEIS_WORKER_URL = 'https://tg-relay.yk2cmjp7vm.workers.dev';
function keisSetWebhookViaWorker() {
  const p = PropertiesService.getScriptProperties();
  const base = p.getProperty('WORKER_URL') || KEIS_WORKER_URL;
  const url = base.replace(/\/+$/, '') + '/' + p.getProperty('SECRET') + '/keis';
  const r = keisTg_('setWebhook', { url: url, allowed_updates: JSON.stringify(['message']) });
  say_('Бот Кейс webhook (Worker): ' + keisHtml_(JSON.parse(r.getContentText()).description || 'ok'));
}

// 3) Қайтару жолы: webhook-ты өшіреді (Mac-та ескі боттың polling режимін қайта қосу керек болса).
function keisDeleteWebhook() {
  const r = keisTg_('deleteWebhook', { drop_pending_updates: false });
  say_('Бот Кейс webhook өшірілді: ' + keisHtml_(JSON.parse(r.getContentText()).description || 'ok'));
}

// 4) Диагностика отправки: кімнің токені екенін және минимал хабарлама жететінін көрсетеді (токенсіз).
function keisSendTest() {
  const chat = PropertiesService.getScriptProperties().getProperty('CHAT_ID');
  const short = function (r) { const t = r.getContentText(); return t.length > 160 ? t.slice(0, 160) + '…' : t; };
  const me = JSON.parse(keisTg_('getMe', {}).getContentText());
  const a = keisTg_('sendMessage', { chat_id: chat, text: 'Тест A (Бот Кейс): минимал хабарлама' });
  const b = keisTg_('sendMessage', { chat_id: Number(chat), text: 'Тест B (Бот Кейс): chat_id сан түрінде', parse_mode: 'HTML' });
  const c = keisTg_('getChat', { chat_id: chat });
  say_('<b>Бот Кейс: жіберу сынағы</b>\nБот: @' + keisHtml_((me.result && me.result.username) || '?') + ' (id ' + keisHtml_(String(me.result && me.result.id)) + ')\nCHAT_ID: ' + keisHtml_(String(chat)) +
    '\nA: ' + keisHtml_(short(a)) + '\nB: ' + keisHtml_(short(b)) + '\ngetChat: ' + keisHtml_(short(c)));
}
