"""Анкета -> «ЛИКВИДАЦИЯ БАЗА СТУДЕНТОВ» кестесі.

Саят ботқа (жеке чатқа) сатып алған студенттің анкетасын жібереді (қарапайым мәтін немесе forward).
Бот өрістерді таниды, алдын ала көрсетеді, «✅ Қосу» батырмасын бассаң, сәйкес қала парағының
бірінші бос жолына жазады. Қолмен толтырылған жолдарға тиіспейді, формула бар ұяшықтарды жазбайды."""
import logging
import re
import uuid
from datetime import datetime, timedelta
from html import escape

from . import liquidation as lq

log = logging.getLogger(__name__)
SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets/'
DRAFT_TTL = timedelta(minutes=30)

DEFAULT_CITY_TABS = {'алматы': 'Алматы', 'алмата': 'Алматы', 'almaty': 'Алматы', 'астана': 'Астана', 'нурсултан': 'Астана',
                     'нур-султан': 'Астана', 'astana': 'Астана', 'шымкент': 'Шымкент', 'shymkent': 'Шымкент',
                     'туркистан': 'Шымкент', 'туркестан': 'Шымкент', 'ақтау': 'Ақтау', 'актау': 'Ақтау', 'aktau': 'Ақтау'}

# (өріс, [кілт сөздер]) тәртібі маңызды: нақтырақтары алдымен
LABELS = [
    ('attend', ['қай қалаға', 'қалаға келе', 'келе аласыз', 'қатыса аласыз', 'практикумға', 'офлайн']),
    ('tg', ['телеграм', 'telegram', 'тг', 'ник', 'username', 'инста']),
    ('email', ['почта', 'пошта', 'электронды', 'email', 'e-mail', 'mail', 'эл.п']),
    ('plan', ['вид оплаты', 'тип оплаты', 'рассрочка', 'голд', 'төлем түрі']),
    ('rest', ['остаток', 'қалдық', 'қалды']),
    ('agreed', ['договор', 'сумма', 'стоимость', 'цена', 'баға', 'құны', 'тариф']),
    ('paid', ['внесл', 'внес', 'оплачен', 'төленді', 'предоплат', 'аванс', 'оплата', 'төлем']),
    ('mop', ['моп', 'менеджер']),
    ('age', ['возраст', 'жас']),
    ('city', ['город', 'қала', 'каласы', 'проживан', 'откуда вы']),
    ('status', ['статус', 'кәсіп', 'профессия', 'чем занима', 'деятельност', 'сфера', 'қызмет', 'сала', 'маман', 'кім боласыз', 'занятост']),
    ('request', ['запрос', 'мақсат', 'цель', 'ожидан', 'не күтес', 'қатысудағы', 'чего хотите']),
    ('source', ['откуда клиент', 'источник', 'қайдан білд', 'откуда узнал']),
    ('date', ['дата']),
    ('phone', ['телефон', 'номер', 'нөмір', 'тел', 'whatsapp', 'ватсап', 'контакт']),
    ('fio', ['фио', 'ф.и.о', 'аты', 'имя', 'фамилия', 'толық ат', 'тегі', 'ісім', 'name']),
]
LINE = re.compile(r'^\s*(?:[-*•▪️✅📌☑️]|\d{1,2}[.)])?\s*([^:：\n]{2,70}?)\s*[:：]\s*(.+?)\s*$')
PHONE = re.compile(r'(?<!\d)(?:\+?7|8)?[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
TGNICK = re.compile(r'(?<![\w@])@[A-Za-z0-9_]{4,32}')
HEADER = {'№': 'num', 'моп': 'mop', 'фио': 'fio', 'телефон': 'phone', 'эл.почта': 'email', 'теллеграм': 'tg', 'дата покупки': 'date',
          'возраст': 'age', 'город': 'city', 'статус': 'status', 'откуда клиент': 'source', 'договоренная сумма': 'agreed',
          'внесла': 'paid', 'остаток': 'rest', 'курсқа қатысудағы': 'request', 'комментарий': 'comment'}


def _n(v):
    return lq._norm(v)


def _field(label):
    t = _n(label)
    for f, keys in LABELS:
        if any(_n(k) in t for k in keys):
            return f
    return None


def norm_phone(v):
    d = re.sub(r'\D', '', str(v or ''))
    if len(d) == 10:
        d = '8' + d
    if len(d) == 11 and d[0] == '7':
        d = '8' + d[1:]
    return d if len(d) == 11 else ''


def pick_tab(f, tabs, mapping):
    return norm_tab(f.get('attend', ''), tabs, mapping) or norm_tab(f.get('city', ''), tabs, mapping)


def norm_tab(city, tabs, mapping):
    t = _n(city).replace('г.', '').strip(' .,')
    for k, tab in mapping.items():
        if _n(k) in t and tab in tabs:
            return tab
    return None


def parse(text, team, tier_price=None, forwarded_nick=None):
    """Мәтіннен өрістерді алады. Қайтарады: dict (тек табылғандары)."""
    out = {}
    free = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = LINE.match(raw)
        f = _field(m.group(1)) if m else None
        if f and f not in out:
            out[f] = m.group(2).strip()
        elif not m:
            free.append(raw.strip())
    flat = ' '.join(text.split())
    if 'phone' not in out:
        mm = PHONE.search(flat)
        if mm:
            out['phone'] = mm.group()
    if 'phone' in out:
        p = norm_phone(out['phone'])
        mm = PHONE.search(out['phone'])
        out['phone'] = p or (norm_phone(mm.group()) if mm else '') or out['phone']
    if 'email' not in out:
        mm = EMAIL.search(flat)
        if mm:
            out['email'] = mm.group()
    if 'tg' not in out:
        mm = TGNICK.search(flat)
        if mm:
            out['tg'] = mm.group()
        elif forwarded_nick:
            out['tg'] = '@' + forwarded_nick.lstrip('@')
    if 'fio' not in out:
        for line in free:
            w = line.split()
            if 2 <= len(w) <= 4 and not re.search(r'\d|@|:', line) and not EMAIL.search(line) and not any(_n(x) == _n(n) for n in team for x in w[:1]):
                out['fio'] = line
                break
    if 'paid' not in out:
        for line in free:
            if PHONE.search(line) or EMAIL.search(line):
                continue
            mm = re.search(r'(?<![\d@])(\d{1,3}(?:[\s.,]\d{3})+|\d{4,7})(?![\d@])', line)
            if mm:
                v = lq._num(mm.group(1).replace(' ', ''))
                if 1000 <= v <= 3000000:
                    out['paid'] = v
                    break
    for k in ('agreed', 'paid', 'rest'):
        if k in out:
            n = lq._num(out[k])
            out[k] = n if n or re.search(r'\d', str(out[k])) else None
            if out[k] is None:
                out.pop(k)
    if 'mop' in out:
        out['mop'] = _match_team(out['mop'], team) or out['mop']
    else:
        for w in re.findall(r'[^\W\d_]+', text):
            t = _match_team(w, team)
            if t and re.search(r'(?i)моп|менеджер', text):
                out['mop'] = t
                break
    if 'plan' in out:
        pl = _n(out['plan'])
        out['plan'] = 'рассрочка' if 'рассроч' in pl else 'голд' if 'голд' in pl else ('оплата' if 'оплат' in pl else out['plan'])
        if out['plan'] == 'оплата':
            out.pop('plan')
    else:
        pl = _n(text)
        if re.search(r'(?<!\w)рассрочка', pl):
            out['plan'] = 'рассрочка'
        elif re.search(r'(?<!\w)голд', pl):
            out['plan'] = 'голд'
    if tier_price and 'agreed' not in out:
        out['agreed'] = tier_price
    return out


def _match_team(word, team):
    w = _n(word).strip()
    for n in team:
        nn = _n(n)
        if w and (w == nn or w.startswith(nn) or (len(w) >= 3 and nn.startswith(w))):
            return n
    return None


def score(fields):
    return sum(1 for k in ('fio', 'phone', 'email', 'tg', 'age', 'city', 'status', 'request', 'agreed', 'paid', 'mop') if fields.get(k) not in (None, ''))


def looks_like_anketa(text, fields):
    t = text.strip().casefold()
    if t.startswith(('анкета', '#анкета', '/anketa', '/анкета')):
        return True
    return bool(fields.get('phone')) and score(fields) >= 3


def missing(f, tab):
    need = []
    if not f.get('fio'):
        need.append('ФИО')
    if not f.get('phone'):
        need.append('телефон')
    if not f.get('mop'):
        need.append('МОП')
    if not tab:
        need.append('қала/парақ')
    if f.get('paid') is None:
        need.append('Внесла (қанша төледі)')
    return need


# ---------------------------------------------------------------- кесте
def _read(sess, sid, tabs, maxrows):
    ranges = ["'%s'!A1:Y%d" % (t.replace("'", "''"), maxrows) for t in tabs]
    r = sess.get(f'{SHEETS}{sid}/values:batchGet', params=[('ranges', x) for x in ranges] + [('valueRenderOption', 'FORMULA')], timeout=30)
    r.raise_for_status()
    got = {}
    for tab, vr in zip(tabs, r.json().get('valueRanges', [])):
        got[tab] = vr.get('values', []) or []
    return got


def _cols(rows):
    """Тақырып жолынан баған индекстері."""
    for i, row in enumerate(rows[:6]):
        m = {}
        for j, c in enumerate(row):
            h = _n(c)
            if h.startswith('вид оплаты'):
                m['plan' if '(' in h else 'kind'] = j
                continue
            for key, field in HEADER.items():
                if h.startswith(_n(key)) and field not in m:
                    m[field] = j
        if len(m) >= 6:
            return i, m
    return None, {}


def _val(row, j):
    return row[j] if j is not None and j < len(row) else ''


def find_row(rows, cols, hi):
    """Бірінші бос жол (ФИО мен телефон бос) және келесі №."""
    last_num, first_empty = 0, None
    for i in range(hi + 1, len(rows) + 60):
        row = rows[i] if i < len(rows) else []
        filled = bool(_s(_val(row, cols.get('fio'))) or _s(_val(row, cols.get('phone'))))
        if filled:
            n = lq._num(_val(row, cols.get('num')))
            last_num = max(last_num, int(n) if n else 0)
            first_empty = None
        elif first_empty is None:
            first_empty = i
        if i > hi + 400:
            break
    return (first_empty if first_empty is not None else len(rows)), last_num + 1


def _s(v):
    return '' if v is None else str(v).strip()


def duplicates(data, phone, fio):
    d = norm_phone(phone)
    hits = []
    for tab, rows in data.items():
        hi, cols = _cols(rows)
        if hi is None:
            continue
        for i in range(hi + 1, len(rows)):
            r = rows[i]
            p = norm_phone(_val(r, cols.get('phone')))
            if (d and p and p == d) or (not d and fio and _n(_val(r, cols.get('fio'))) == _n(fio)):
                hits.append((tab, i + 1))
    return hits


def build_cells(f, rows, cols, row_i, num, today, comment=None):
    """Жазылатын ұяшықтар: (баған индексі, мән). Формула бар ұяшық пен толтырылған ұяшыққа тимейді."""
    paid, agreed = f.get('paid'), f.get('agreed')
    rest = f.get('rest')
    if rest is None and paid is not None and agreed is not None:
        rest = max(agreed - paid, 0)
    kind = 'оплата' if rest is not None and rest <= 0 else 'предоплата'
    values = {'num': num, 'mop': f.get('mop'), 'fio': f.get('fio'), 'phone': f.get('phone'), 'email': f.get('email'),
              'tg': f.get('tg'), 'date': f.get('date') or f'{today:%d.%m}', 'plan': f.get('plan'), 'age': f.get('age'),
              'city': f.get('city'), 'status': f.get('status'), 'source': f.get('source'), 'agreed': agreed, 'paid': paid,
              'rest': rest, 'kind': kind if paid is not None else None, 'request': f.get('request'), 'comment': comment}
    row = rows[row_i] if row_i < len(rows) else []
    cells = []
    for key, v in values.items():
        j = cols.get(key)
        if j is None or v in (None, ''):
            continue
        cur = _val(row, j)
        if _s(cur):
            continue                      # бар мәнге/формулаға тимейміз
        if isinstance(v, float) and v == int(v):
            v = int(v)
        cells.append((j, v))
    return cells


def _a1(j):
    s, j = '', j
    while True:
        j, r = divmod(j, 26)
        s = chr(65 + r) + s
        if j == 0:
            return s
        j -= 1


def write(sess, sid, tab, row_i, cells):
    data = [{'range': "'%s'!%s%d" % (tab.replace("'", "''"), _a1(j), row_i + 1), 'values': [[v]]} for j, v in cells]
    r = sess.post(f'{SHEETS}{sid}/values:batchUpdate', json={'valueInputOption': 'USER_ENTERED', 'data': data}, timeout=30)
    r.raise_for_status()


# ---------------------------------------------------------------- Telegram ағыны
def _cfg(config):
    c = lq.cfg(config)
    a = dict({'enabled': True, 'city_tabs': {}}, **(c.get('anketa') or {}))
    return c, a


def _sess():
    from . import fines
    return fines._sess()


def _fwd_nick(msg):
    o = msg.get('forward_origin') or {}
    u = o.get('sender_user') or msg.get('forward_from') or {}
    return u.get('username')


def preview(f, tab, dup, tabs, practicum=None):
    L = ['<b>Анкета</b> (кестеге жазылмаған, тексеріңіз)']
    rows = [('ФИО', f.get('fio')), ('Телефон', f.get('phone')), ('Email', f.get('email')), ('Telegram', f.get('tg')),
            ('Жасы', f.get('age')), ('Қала', f.get('city')), ('Практикумға келеді', f.get('attend')), ('Статус', f.get('status')), ('Запрос', f.get('request')),
            ('МОП', f.get('mop')), ('Келісілген', lq.money(f['agreed']) + ' ₸' if f.get('agreed') is not None else None),
            ('Внесла', lq.money(f['paid']) + ' ₸' if f.get('paid') is not None else None), ('Вид', f.get('plan'))]
    for k, v in rows:
        if v not in (None, ''):
            L.append(f'{k}: {escape(str(v))}')
    L.append(f'Парақ: <b>{escape(tab)}</b>' if tab else 'Парақ: ❓ таңдаңыз')
    if tab and practicum:
        L.append(escape(practicum))
    if dup:
        L.append('⚠️ Мұндай телефон/ФИО бұрыннан бар: ' + ', '.join(f'{escape(t)} {r}-жол' for t, r in dup))
    return '\n'.join(L)


def keyboard(did, tab, tabs, ready, team=None):
    rows = []
    if ready:
        rows.append([{'text': f'✅ Қосу → {tab}', 'callback_data': f'aq:{did}:ok'}, {'text': '❌ Болдырмау', 'callback_data': f'aq:{did}:no'}])
    else:
        rows.append([{'text': '❌ Болдырмау', 'callback_data': f'aq:{did}:no'}])
    rows.append([{'text': ('• ' if t == tab else '') + t, 'callback_data': f'aq:{did}:t{i}'} for i, t in enumerate(tabs)])
    if team:
        btn = [{'text': n, 'callback_data': f'aq:{did}:m{i}'} for i, n in enumerate(team)]
        rows += [btn[i:i + 4] for i in range(0, len(btn), 4)]
    return {'inline_keyboard': rows}


def _active_draft(bot, chat, now):
    d = bot.store.get('aq:draft:' + str(chat))
    if not d or d.get('done'):
        return None
    try:
        if now - datetime.fromisoformat(d['at']) > DRAFT_TTL:
            return None
    except Exception:
        return None
    return d


def handle(bot, msg, text, uid, is_owner, chat, now, key):
    c, a = _cfg(bot.config)
    if not (lq.enabled(bot.config) and a.get('enabled', True)) or not is_owner or chat != uid:
        return False
    if text.startswith('/') and not text.lower().startswith(('/anketa', '/анкета')):
        return False
    team = [p['name'] for p in bot.config.get('team', [])]
    try:
        price = lq.tier_info(c, now.date())['price']
    except Exception:
        price = None
    fields = parse(text, team, price, _fwd_nick(msg))
    explicit = _explicit(text)
    draft = _active_draft(bot, chat, now)
    if draft:
        add = {k: v for k, v in fields.items() if k in explicit}
        word = text.strip()
        if 'mop' not in add and len(word.split()) == 1 and _match_team(word, team):
            add['mop'] = _match_team(word, team)
        if 'paid' not in add and re.fullmatch(r'\d[\d\s]{2,9}', word):
            add['paid'] = float(re.sub(r'\s', '', word))
        for k in ('paid', 'plan'):
            if k in fields and k not in add and not fields.get('phone'):
                add[k] = fields[k]
        new_person = fields.get('phone') and draft['f'].get('phone') and fields['phone'] != draft['f']['phone']
        if add and not new_person:
            draft['f'].update(add)
            if 'city' in add:
                draft['tab'] = None
            _show_with_hits(bot, draft, now, chat)
            return True
    if not looks_like_anketa(text, fields):
        return False
    draft = {'id': uuid.uuid4().hex[:8], 'f': fields, 'tab': None, 'dup_hits': []}
    try:
        data = _read(_sess(), c['spreadsheet_id'], c['sheet_names'], 400)
        draft['dup_hits'] = duplicates(data, fields.get('phone'), fields.get('fio'))
    except Exception as exc:
        log.warning('anketa duplicate check failed: %s', type(exc).__name__)
    _show_with_hits(bot, draft, now, chat)
    return True


def _explicit(text):
    return {f for raw in text.splitlines() for m in [LINE.match(raw)] if m for f in [_field(m.group(1))] if f}


def _show_with_hits(bot, draft, now, chat):
    c, a = _cfg(bot.config)
    tabs = c['sheet_names']
    f = draft['f']
    mapping = dict(DEFAULT_CITY_TABS, **a.get('city_tabs', {}))
    tab = draft.get('tab') or pick_tab(f, tabs, mapping)
    draft['tab'] = tab
    miss = missing(f, tab)
    text = preview(f, tab, draft.get('dup_hits') or [], tabs, lq.practicum_text(c, tab) if tab else None)
    if miss:
        text += '\n\n❗ Жетіспейді: <b>' + escape(', '.join(miss)) + '</b>. Мына түрде жазыңыз:\n<code>МОП: Арман\nВнесла: 179000</code>'
    bot.store.set('aq:draft:' + str(chat), dict(draft, at=now.isoformat()))
    bot.enqueue(f'aq:show:{draft["id"]}:{now:%H%M%S%f}', text, now, chat=chat, keyboard=keyboard(draft['id'], tab, tabs, not miss, [p['name'] for p in bot.config.get('team', [])] if not f.get('mop') else None),
                expires=now + timedelta(hours=2))




def callback(bot, cb, now):
    data = cb.get('data', '')
    if not data.startswith('aq:'):
        return False
    c, a = _cfg(bot.config)
    uid = (cb.get('from') or {}).get('id')
    chat = (cb.get('message') or {}).get('chat', {}).get('id')

    def ack(text=''):
        try:
            bot.telegram.call('answerCallbackQuery', {'callback_query_id': cb['id'], 'text': text[:150]}, timeout=10)
        except Exception:
            pass

    if uid != bot.config['owner_id'] or chat != uid:
        ack('Бұл батырма тек Саятқа арналған')
        return True
    try:
        _, did, act = data.split(':')
    except ValueError:
        ack()
        return True
    d = bot.store.get('aq:draft:' + str(chat))
    if not d or d.get('id') != did:
        ack('Бұл анкета ескірген, қайта жіберіңіз')
        return True
    if d.get('done'):
        ack('Бұл анкета бұрын өңделген')
        return True
    if act == 'no':
        d['done'] = 'cancel'
        bot.store.set('aq:draft:' + str(chat), d)
        ack('Болдырылмады')
        bot.enqueue(f'aq:no:{did}', 'Анкета жойылды, кестеге жазылған жоқ.', now, chat=chat)
        return True
    if act.startswith('t') and act[1:].isdigit() and int(act[1:]) < len(c['sheet_names']):
        d['tab'] = c['sheet_names'][int(act[1:])]
        ack(d['tab'])
        _show_with_hits(bot, d, now, chat)
        return True
    team = [p['name'] for p in bot.config.get('team', [])]
    if act.startswith('m') and act[1:].isdigit() and int(act[1:]) < len(team):
        d['f']['mop'] = team[int(act[1:])]
        ack('МОП: ' + d['f']['mop'])
        _show_with_hits(bot, d, now, chat)
        return True
    if act != 'ok':
        ack()
        return True
    tab = d.get('tab')
    miss = missing(d['f'], tab)
    if miss:
        ack('Жетіспейді: ' + ', '.join(miss))
        return True
    d['done'] = 'saving'
    bot.store.set('aq:draft:' + str(chat), d)
    try:
        sess = _sess()
        data_ = _read(sess, c['spreadsheet_id'], c['sheet_names'], 400)
        rows = data_[tab]
        hi, cols = _cols(rows)
        if hi is None:
            raise ValueError('Тақырып жолы табылмады')
        row_i, num = find_row(rows, cols, hi)
        cells = build_cells(d['f'], rows, cols, row_i, num, now.date(), lq.practicum_text(c, tab))
        if not cells:
            raise ValueError('Жазатын ұяшық жоқ')
        write(sess, c['spreadsheet_id'], tab, row_i, cells)
        back = _read(sess, c['spreadsheet_id'], [tab], 400)[tab]
        ok = norm_phone(_val(back[row_i] if row_i < len(back) else [], cols.get('phone'))) == norm_phone(d['f'].get('phone')) or \
            _n(_val(back[row_i] if row_i < len(back) else [], cols.get('fio'))) == _n(d['f'].get('fio'))
        d['done'] = 'saved'
        bot.store.set('aq:draft:' + str(chat), d)
        ack('Жазылды ✅')
        if ok:
            bot.enqueue(f'aq:ok:{did}', f'✅ Жазылды: <b>{escape(tab)}</b>, {row_i + 1}-жол · {escape(str(d["f"].get("fio")))} · МОП {escape(str(d["f"].get("mop")))}.',
                        now, chat=chat)
        else:
            bot.enqueue(f'aq:chk:{did}', f'⚠️ Жазу жіберілді, бірақ {tab} парағының {row_i + 1}-жолын тексере алмадым. Кестені көзбен қараңыз.', now, chat=chat)
        try:
            bot.store.set('dash:sheet', None)
            bot.store.set('lq:data', None)
        except Exception:
            pass
    except Exception as exc:
        d['done'] = None
        bot.store.set('aq:draft:' + str(chat), d)
        code = type(exc).__name__ + ': ' + str(exc)[:120]
        hint = ''
        if '403' in str(exc):
            try:
                from . import fines
                hint = f'\nКестеге <code>{escape(fines.sa_email())}</code> email-ін <b>Editor</b> ретінде қосыңыз.'
            except Exception:
                hint = '\nService account-қа кестеде Editor рұқсатын беріңіз.'
        ack('Жазылмады')
        bot.enqueue(f'aq:err:{did}:{now:%H%M%S}', f'❌ Кестеге жазылмады ({escape(code)}).{hint}', now, chat=chat)
    return True
