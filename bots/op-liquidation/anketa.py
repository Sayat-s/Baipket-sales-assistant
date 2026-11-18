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

DEFAULT_CITY_TABS = {
    # 4 практикум қаласы бірінші тұрады ("Тараз-Алматы" -> Алматы)
    'алматы': 'Алматы', 'алмата': 'Алматы', 'almaty': 'Алматы', 'астана': 'Астана', 'нурсултан': 'Астана',
    'нур-султан': 'Астана', 'astana': 'Астана', 'шымкент': 'Шымкент', 'shymkent': 'Шымкент', 'ақтау': 'Ақтау',
    'актау': 'Ақтау', 'aktau': 'Ақтау',
    # ең жақын практикум қаласы
    'талдыкорган': 'Алматы', 'конаев': 'Алматы', 'капшагай': 'Алматы', 'есик': 'Алматы', 'текели': 'Алматы', 'уштобе': 'Алматы',
    'жаркент': 'Алматы', 'кульджа': 'Алматы', 'каскелен': 'Алматы', 'алатау': 'Алматы',
    'караганд': 'Астана', 'теміртау': 'Астана', 'темиртау': 'Астана', 'кокшетау': 'Астана', 'павлодар': 'Астана',
    'экибастуз': 'Астана', 'екибастуз': 'Астана', 'петропавл': 'Астана', 'костанай': 'Астана', 'рудный': 'Астана', 'семей': 'Астана',
    'семипалатинск': 'Астана', 'оскемен': 'Астана', 'усть-каменогорск': 'Астана', 'жезказган': 'Астана', 'балхаш': 'Астана',
    'степногорск': 'Астана', 'аркалык': 'Астана', 'акколь': 'Астана', 'щучинск': 'Астана',
    'туркистан': 'Шымкент', 'туркестан': 'Шымкент', 'тараз': 'Шымкент', 'жамбыл': 'Шымкент', 'кызылорд': 'Шымкент',
    'кентау': 'Шымкент', 'арыс': 'Шымкент', 'сарыагаш': 'Шымкент', 'казыгурт': 'Шымкент', 'шу': 'Шымкент',
    'актобе': 'Ақтау', 'атырау': 'Ақтау', 'уральск': 'Ақтау', 'оral': 'Ақтау', 'орал': 'Ақтау', 'жанаозен': 'Ақтау',
    'бейнеу': 'Ақтау', 'кульсары': 'Ақтау', 'эмба': 'Ақтау', 'мангистау': 'Ақтау', 'мангыстау': 'Ақтау',
}

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


# Картадағы нақты орналасу (ендік, бойлық): ең жақын практикум қаласын км бойынша есептеу үшін
HUBS = {'Астана': (51.18, 71.45), 'Алматы': (43.24, 76.89), 'Шымкент': (42.32, 69.59), 'Ақтау': (43.65, 51.15)}
CITY_COORDS = {
    'караганд': (49.80, 73.10), 'саран': (49.80, 72.84), 'темиртау': (50.05, 72.96), 'кокшет': (53.28, 69.38),
    'павлодар': (52.29, 76.97), 'аксу': (52.04, 76.92), 'екибастуз': (51.73, 75.32), 'экибастуз': (51.73, 75.32),
    'петропавл': (54.87, 69.15), 'костанай': (53.21, 63.63), 'рудный': (52.97, 63.12), 'лисаковск': (52.54, 62.50),
    'житикара': (52.19, 61.20), 'семей': (50.41, 80.26), 'семипалатинск': (50.41, 80.26), 'оскемен': (49.95, 82.61),
    'усть-каменогорск': (49.95, 82.61), 'жезказган': (47.78, 67.77), 'сатпаев': (47.90, 67.53), 'сатбаев': (47.90, 67.53), 'балхаш': (46.84, 74.98),
    'степногорск': (52.35, 71.88), 'аркалык': (50.25, 66.91), 'атбасар': (51.80, 68.35), 'ерейментау': (51.62, 73.10),
    'акколь': (51.98, 70.95), 'щучинск': (52.93, 70.20), 'боровое': (53.08, 70.30), 'байконыр': (45.62, 63.31),
    'конаев': (43.88, 77.08), 'капшагай': (43.88, 77.08), 'талдыкорган': (45.02, 78.37), 'текели': (44.85, 78.78),
    'есик': (43.35, 77.45), 'уштобе': (45.25, 77.98), 'жаркент': (44.17, 79.99), 'каскелен': (43.20, 76.60),
    'кордай': (43.05, 74.70), 'тараз': (42.90, 71.37), 'туркистан': (43.30, 68.25), 'туркестан': (43.30, 68.25),
    'кызылорд': (44.85, 65.51), 'кентау': (43.52, 68.51), 'арыс': (42.43, 68.80), 'сарыагаш': (41.45, 69.17),
    'актобе': (50.28, 57.21), 'хромтау': (50.25, 58.44), 'шалкар': (47.83, 59.60), 'атырау': (47.12, 51.88),
    'уральск': (51.23, 51.37), 'орал': (51.23, 51.37), 'жанаозен': (43.35, 52.86), 'бейнеу': (45.32, 55.20),
    'кулсары': (46.97, 54.02), 'аксай': (51.16, 53.00), 'шу': (43.60, 73.76), 'мангистау': (43.65, 51.15),
}


def _km(a, b):
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 12742 * asin(sqrt(h))


def nearest_hub(text, tabs):
    """Қала атынан координат тауып, ең жақын практикум қаласын (парақ, км) қайтарады."""
    t = _n(text)
    words = set(re.findall(r'[^\W\d_]+(?:-[^\W\d_]+)*', t))
    for key, pt in CITY_COORDS.items():
        nk = _n(key)
        if (nk in t) if len(nk) > 3 else (nk in words):
            best = min(((tab, _km(pt, xy)) for tab, xy in HUBS.items() if tab in tabs), key=lambda z: z[1], default=None)
            return (best[0], int(round(best[1]))) if best else None
    return None


def tab_info(src, tabs, mapping):
    """(парақ, км). Алдымен 4 қаланың өз аты, содан кейін карта бойынша ең жақыны, соңында қолмен тізім."""
    t = _n(src).replace('г.', '').strip(' .,')
    if not t:
        return None, None
    for tab in tabs:
        if _n(tab) in t:
            return tab, 0
    near = nearest_hub(src, tabs)
    if near:
        return near
    for k, tab in mapping.items():
        if tab in tabs and _n(k) in t:
            return tab, None
    return None, None



def pick_tab(f, tabs, mapping):
    return tab_info(f.get('attend', ''), tabs, mapping)[0] or tab_info(f.get('city', ''), tabs, mapping)[0]


def norm_tab(city, tabs, mapping):
    return tab_info(city, tabs, mapping)[0]


INVISIBLE = re.compile('[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]')
POS = re.compile(r'^\s*(?:№\s*)?(\d{1,2})\s*(?:[.):]|\s[-–—]|[-–—]\s)\s*(.+?)\s*$')
TIMELIKE = re.compile(r'^\s*\d{1,2}:\d{2}(?!\d)')
POSMAP = {1: 'fio', 2: 'age', 3: 'phone', 4: 'email', 5: 'tg', 6: 'status', 7: 'city', 8: 'request', 9: 'attend'}


def clean(text):
    return INVISIBLE.sub('', text or '').replace('\u00a0', ' ')


STATUS_WORDS = ('смм', 'smm', 'маркетолог', 'студент', 'мұғалім', 'мугалим', 'учител', 'предпринимат', 'кәсіпкер', 'фриланс', 'дизайнер',
                'менеджер', 'бизнес', 'оқушы', 'школьник', 'жұмыссыз', 'врач', 'дәрігер', 'инженер', 'продаж', 'сату', 'контент', 'фото',
                'видео', 'таргет', 'копирайт', 'директор', 'собственник', 'иесі', 'самозанят', 'декрет', 'тренер', 'блогер', 'бухгалтер')


def _service_line(line, team, contacts=True):
    if contacts and (PHONE.search(line) or EMAIL.search(line)):
        return True
    n = _n(line)
    if re.search(r'(?<!\w)(рассрочка|голд|моп|менеджер)(?!\w)', n) and len(line) <= 40:
        return True
    if not PHONE.search(line) and not EMAIL.search(line) and re.search(r'(\d{1,3}(?:[\s.,]\d{3})+|\d{4,7})\s*(тг|₸|тенге)?', line) and len(re.sub(r'[\d\s.,]|тг|₸|тенге', '', n)) <= 14:
        return True
    if len(line.split()) == 1 and _match_team(line, team):
        return True
    return len(line) > 160 and ('қош келдіңіз' in n or 'анкет' in n)


def _fill_missing(out, free, team):
    """Белгісіз жолдардан жасын, қаласын, статусын, запросын болжап толтырады (тек бос өрістерге)."""
    ordered = [ln for ln in free if not _service_line(ln, team, contacts=False)]
    if len(ordered) >= 8:                             # 9 жол стандартты тәртіппен келсе
        for i, ln in enumerate(ordered[:9]):
            out.setdefault(POSMAP[i + 1], ln)
    taken = set(out.values()) | {'@' + str(v) for v in out.values()}
    cand = [ln for ln in free if not _service_line(ln, team) and ln not in taken]
    used = set()
    for ln in cand:
        if 'age' not in out and re.fullmatch(r'\D{0,12}(\d{2})\D{0,12}', ln) and 14 <= int(re.search(r'\d{2}', ln).group()) <= 70:
            out['age'] = re.search(r'\d{2}', ln).group()
            used.add(ln)
    for ln in cand:
        if ln in used or len(ln) > 30:
            continue
        if tab_info(ln, list(HUBS), DEFAULT_CITY_TABS)[0] and not re.search(r'\d', ln):
            if 'city' not in out:
                out['city'] = ln
                used.add(ln)
            elif 'attend' not in out:
                out['attend'] = ln
                used.add(ln)
    for ln in cand:
        if ln not in used and 'status' not in out and len(ln) <= 50 and any(w in _n(ln) for w in STATUS_WORDS):
            out['status'] = ln
            used.add(ln)
    rest = [ln for ln in cand if ln not in used and len(ln) >= 12 and not _is_fio_like(ln, out)]
    if 'request' not in out and rest:
        out['request'] = max(rest, key=len)


def _is_fio_like(ln, out):
    return ln == out.get('fio') or (len(ln.split()) in (2, 3) and not re.search(r'\d|@', ln) and ln == out.get('fio'))


def parse(text, team, tier_price=None, forwarded_nick=None):
    """Мәтіннен өрістерді алады. Қайтарады: dict (тек табылғандары)."""
    text = clean(text)
    out = {}
    free = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = LINE.match(raw)
        f = _field(m.group(1)) if m else None
        pm = None if TIMELIKE.match(raw) else POS.match(raw)
        if pm and not (m and f and len(m.group(1)) <= 70):
            field = POSMAP.get(int(pm.group(1)))
            if field:
                if field not in out:
                    out[field] = pm.group(2).strip()
                continue
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
        else:
            for line in free:
                if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{3,31}', line.strip()):
                    out['tg'] = '@' + line.strip()
                    break
    if out.get('tg') and not out['tg'].startswith('@') and re.fullmatch(r'[A-Za-z0-9_.]{4,32}', out['tg'].strip()):
        out['tg'] = '@' + out['tg'].strip()
    if 'fio' not in out:
        for line in free:
            w = line.split()
            if 2 <= len(w) <= 4 and not re.search(r'\d|@|:', line) and not EMAIL.search(line) and not any(_n(x) == _n(n) for n in team for x in w[:1]):
                out['fio'] = line
                break
    _fill_missing(out, free, team)
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


def empty_optional(f):
    out = []
    if not f.get('age'):
        out.append('жасы')
    if not (f.get('city') or f.get('attend')):
        out.append('қала')
    if not f.get('status'):
        out.append('статус')
    if not f.get('request'):
        out.append('запрос')
    if not f.get('email'):
        out.append('email')
    if not f.get('tg'):
        out.append('Telegram')
    return out


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
        if key in ('age', 'num') and re.fullmatch(r'\d{1,3}', str(v).strip()):
            v = int(str(v).strip())
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
    r = sess.post(f'{SHEETS}{sid}/values:batchUpdate', json={'valueInputOption': 'RAW', 'data': data}, timeout=30)
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
    src = f.get('attend') or f.get('city') or ''
    if tab and src and _n(tab) not in _n(src):
        km = tab_info(src, tabs, dict(DEFAULT_CITY_TABS))[1]
        L.append(f'📍 «{escape(src)}» үшін картадағы ең жақын практикум қаласы: {escape(tab)}' + (f' (~{km} км)' if km else '') + '. Қате болса, батырмамен ауыстырыңыз.')
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
    text = clean(text)
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
        if 'age' not in add and not draft['f'].get('age') and re.fullmatch(r'\d{2}', text.strip()) and 14 <= int(text.strip()) <= 70:
            add['age'] = text.strip()
        new_person = fields.get('phone') and draft['f'].get('phone') and fields['phone'] != draft['f']['phone']
        if add and not new_person:
            draft['f'].update(add)
            if 'city' in add:
                draft['tab'] = None
            _present(bot, draft, now, chat)
            return True
    if not looks_like_anketa(text, fields):
        return False
    draft = {'id': uuid.uuid4().hex[:8], 'f': fields, 'tab': None, 'dup_hits': []}
    try:
        data = _read(_sess(), c['spreadsheet_id'], c['sheet_names'], 400)
        draft['dup_hits'] = duplicates(data, fields.get('phone'), fields.get('fio'))
    except Exception as exc:
        log.warning('anketa duplicate check failed: %s', type(exc).__name__)
    _present(bot, draft, now, chat)
    return True


def _explicit(text):
    return {f for raw in text.splitlines() for m in [LINE.match(raw)] if m for f in [_field(m.group(1))] if f}


def _say(bot, chat, text, kb, now, key, edit_id=None):
    """Тікелей жібереді (кезексіз, жылдам). Мүмкін болса, ескі хабарламаны өзгертеді. Сәтсіз болса, кезекке түседі."""
    payload = {'chat_id': chat, 'text': text, 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}}
    if kb:
        payload['reply_markup'] = kb
    tg = getattr(bot, 'telegram', None)
    try:
        if edit_id:
            tg.call('editMessageText', dict(payload, message_id=edit_id))
            return edit_id
        r = tg.send(payload)
        return r.get('message_id') if isinstance(r, dict) else None
    except Exception as exc:
        log.info('anketa direct send failed (%s), queued', type(exc).__name__)
    try:
        bot.enqueue(key, text, now, chat=chat, keyboard=kb, expires=now + timedelta(hours=2))
    except Exception:
        pass
    return None


def _present(bot, d, now, chat):
    """Толық болса, бірден жазады; болмаса, бір ғана хабарламаны жаңартып көрсетеді."""
    c, a = _cfg(bot.config)
    tabs = c['sheet_names']
    f = d['f']
    mapping = dict(DEFAULT_CITY_TABS, **a.get('city_tabs', {}))
    tab = d.get('tab') or pick_tab(f, tabs, mapping)
    d['tab'] = tab
    miss = missing(f, tab)
    empty = empty_optional(f)
    if not miss and not empty and not d.get('dup_hits') and a.get('auto_write', True) and not d.get('done'):
        return _save(bot, d, c, now, chat)
    text = preview(f, tab, d.get('dup_hits') or [], tabs, lq.practicum_text(c, tab) if tab else None)
    if miss:
        text += '\n\n❗ Жетіспейді: <b>' + escape(', '.join(miss)) + '</b>. Төмендегі батырманы басыңыз немесе жазыңыз, мысалы: <code>Внесла 179000 рассрочка</code>'
    if empty and not miss:
        text += '\n\n⚠️ Бос қалады: <b>' + escape(', '.join(empty)) + '</b>. Жазыңыз (мысалы <code>Запрос: ...</code>, <code>Жасы: 22</code>) немесе «✅ Қосу» басыңыз.'
    kb = keyboard(d['id'], tab, tabs, not miss, [p['name'] for p in bot.config.get('team', [])] if not f.get('mop') else None)
    if not (d.get('mid') and d.get('last') == text):
        mid = _say(bot, chat, text, kb, now, f'aq:show:{d["id"]}:{now:%H%M%S%f}', d.get('mid'))
        d['mid'] = mid or d.get('mid')
        d['last'] = text
    bot.store.set('aq:draft:' + str(chat), dict(d, at=now.isoformat()))


def _save(bot, d, c, now, chat, ack=None):
    tab = d.get('tab')
    did = d['id']
    d['done'] = 'saving'
    bot.store.set('aq:draft:' + str(chat), dict(d, at=now.isoformat()))
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
        r = back[row_i] if row_i < len(back) else []
        ok = norm_phone(_val(r, cols.get('phone'))) == norm_phone(d['f'].get('phone')) or _n(_val(r, cols.get('fio'))) == _n(d['f'].get('fio'))
        d['done'] = 'saved'
        d['written'] = {'tab': tab, 'row': row_i, 'cells': [[j, v] for j, v in cells]}
        bot.store.set('aq:draft:' + str(chat), dict(d, at=now.isoformat()))
        if ack:
            ack('Жазылды ✅')
        paid = d['f'].get('paid')
        txt = (f'✅ <b>{escape(tab)}</b>, {row_i + 1}-жол: {escape(str(d["f"].get("fio")))} · МОП {escape(str(d["f"].get("mop")))}'
               + (f' · {lq.money(paid)} ₸' if paid is not None else '') + (f' · {escape(str(d["f"].get("plan")))}' if d['f'].get('plan') else ''))
        if not ok:
            txt = f'⚠️ Жазу жіберілді, бірақ {escape(tab)} парағының {row_i + 1}-жолын тексере алмадым. Кестені көзбен қараңыз.'
        _say(bot, chat, txt, {'inline_keyboard': [[{'text': '↩ Қайтару (жолды тазалау)', 'callback_data': f'aq:{did}:undo'}]]}, now, f'aq:ok:{did}', d.get('mid'))
        try:
            bot.store.set('dash:sheet', None)
            bot.store.set('lq:data', None)
        except Exception:
            pass
    except Exception as exc:
        d['done'] = None
        bot.store.set('aq:draft:' + str(chat), dict(d, at=now.isoformat()))
        code = type(exc).__name__ + ': ' + str(exc)[:120]
        hint = ''
        if '403' in str(exc):
            try:
                from . import fines
                hint = f'\nКестеге <code>{escape(fines.sa_email())}</code> email-ін <b>Editor</b> ретінде қосыңыз.'
            except Exception:
                hint = '\nService account-қа кестеде Editor рұқсатын беріңіз.'
        if ack:
            ack('Жазылмады')
        _say(bot, chat, f'❌ Кестеге жазылмады ({escape(code)}).{hint}', None, now, f'aq:err:{did}:{now:%H%M%S}')


def _undo(bot, d, c, now, chat, ack):
    w = d.get('written') or {}
    if d.get('done') != 'saved' or not w:
        ack('Қайтаратын жазба жоқ')
        return
    try:
        sess = _sess()
        rows = _read(sess, c['spreadsheet_id'], [w['tab']], 400)[w['tab']]
        row = rows[w['row']] if w['row'] < len(rows) else []
        clear = [(j, '') for j, v in w['cells'] if _s(_val(row, j)) == _s(v)]
        if clear:
            write(sess, c['spreadsheet_id'], w['tab'], w['row'], clear)
        d['done'] = 'undone'
        bot.store.set('aq:draft:' + str(chat), dict(d, at=now.isoformat()))
        ack('Қайтарылды')
        _say(bot, chat, f'↩ Қайтарылды: {escape(w["tab"])} парағының {w["row"] + 1}-жолы тазаланды ({len(clear)} ұяшық).', None, now, f'aq:undo:{d["id"]}', d.get('mid'))
        bot.store.set('lq:data', None)
    except Exception as exc:
        ack('Қайтару сәтсіз')
        _say(bot, chat, f'❌ Қайтару мүмкін болмады ({escape(type(exc).__name__)}). Жолды кестеде қолмен тазалаңыз.', None, now, f'aq:uerr:{d["id"]}')


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
    if act == 'undo':
        _undo(bot, d, c, now, chat, ack)
        return True
    if d.get('done'):
        ack('Бұл анкета бұрын өңделген')
        return True
    if act == 'no':
        d['done'] = 'cancel'
        bot.store.set('aq:draft:' + str(chat), d)
        ack('Болдырылмады')
        _say(bot, chat, 'Анкета жойылды, кестеге жазылған жоқ.', None, now, f'aq:no:{did}', d.get('mid'))
        return True
    if act.startswith('t') and act[1:].isdigit() and int(act[1:]) < len(c['sheet_names']):
        d['tab'] = c['sheet_names'][int(act[1:])]
        ack(d['tab'])
        _present(bot, d, now, chat)
        return True
    team = [p['name'] for p in bot.config.get('team', [])]
    if act.startswith('m') and act[1:].isdigit() and int(act[1:]) < len(team):
        d['f']['mop'] = team[int(act[1:])]
        ack('МОП: ' + d['f']['mop'])
        _present(bot, d, now, chat)
        return True
    if act != 'ok':
        ack()
        return True
    miss = missing(d['f'], d.get('tab'))
    if miss:
        ack('Жетіспейді: ' + ', '.join(miss))
        return True
    _save(bot, d, c, now, chat, ack)
    return True
