"""Ликвидация (Senior Marketer) табло.

Жаңа студенттер базасының қала парақтарынан оплаталарды санайды, PNG табло жасайды,
топқа азартты пуштар жібереді (жаңа оплата, кестемен жарыс, баға баспалдағы).
Кесте тек оқылады. Деректер: МОП, ФИО, Дата покупки, Договоренная сумма, Внесла, Остаток."""
import io
import json
import logging
import math
import re
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS = {
    'enabled': False,
    'spreadsheet_id': None,
    'sheet_names': ['Алматы', 'Астана', 'Шымкент', 'Ақтау'],
    'max_rows': 400,
    'plan': 261,
    'start_date': '2026-11-17',
    'end_date': '2026-11-30',
    'tiers': [
        {'price': 179000, 'from': '2026-11-17', 'to': '2026-11-21'},
        {'price': 239000, 'from': '2026-11-22', 'to': '2026-11-25'},
        {'price': 299000, 'from': '2026-11-26', 'to': '2026-11-30'},
    ],
    'push_at': ['13:00', '17:00', '20:00'],
    'celebrate': True,
    'poll_seconds': 90,
    'count_mode': 'paid',          # paid: ақша түскен әр студент; full: толық төленгені ғана
    'targets': {},                 # {'Арман': 40} жеке жоспар; болмаса жоспар/команда
    'days': [0, 1, 2, 3, 4, 5, 6],
    'title': 'ЛИКВИДАЦИЯ',
    'subtitle': 'Senior Marketer',
}

_TR = str.maketrans({'ұ': 'у', 'ү': 'у', 'қ': 'к', 'ғ': 'г', 'ң': 'н', 'ө': 'о', 'ә': 'а', 'і': 'и', 'һ': 'х', 'ё': 'е', 'й': 'и'})
FIELDS = {'моп': 'mop', 'фио': 'fio', 'телефон': 'phone', 'город': 'city', 'дата покупки': 'date',
          'договоренная сумма': 'agreed', 'внесла': 'paid', 'остаток': 'rest'}
FALLBACK = {'mop': 1, 'fio': 2, 'phone': 3, 'city': 9, 'date': 6, 'agreed': 12, 'paid': 13, 'rest': 14, 'kind': 15}


def cfg(config):
    d = dict(DEFAULTS)
    d.update(config.get('liquidation') or {})
    return d


def enabled(config):
    c = cfg(config)
    return bool(c['enabled'] and c.get('spreadsheet_id'))


# ---------------------------------------------------------------- парсинг
def _s(v):
    return '' if v is None else ' '.join(str(v).split())


def _norm(v):
    return _s(v).casefold().translate(_TR)


def _num(v):
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r'[^\d,.\-]', '', _s(v).replace('\u00a0', ''))
    if not t or t in '-.,':
        return 0.0
    if ',' in t and '.' in t:
        t = t.replace(',', '')
    else:
        t = t.replace(',', '.')
    try:
        return float(t)
    except ValueError:
        return 0.0


def _date(v, today):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 90000:
        return date(1899, 12, 30) + timedelta(days=int(v))
    t = _s(v)
    m = re.fullmatch(r'(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?', t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        y = today.year if not y else (int(y) + 2000 if len(y) == 2 else int(y))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _headers(row):
    m = {}
    for i, c in enumerate(row):
        h = _norm(c)
        if h == 'вид оплаты' and 'kind' not in m:
            m['kind'] = i
            continue
        for k, key in FIELDS.items():
            if h.startswith(k) and key not in m:
                m[key] = i
    return m


def _mgr(raw, names):
    r = _norm(raw)
    if not r:
        return None
    for n in names:
        nn = _norm(n)
        if r == nn or r.startswith(nn) or (len(r) >= 3 and nn.startswith(r)):
            return n
    return 'Басқа'


def parse(value_ranges, names, today, c):
    """value_ranges: Sheets API valueRanges (FORMATTED_VALUE). Қайтарады: жиынтық dict (JSON-ға жарамды)."""
    names = list(names)
    full_only = c.get('count_mode') == 'full'
    blank = lambda: {'paid_n': 0, 'full_n': 0, 'pre_n': 0, 'cash': 0, 'agreed': 0, 'balance': 0, 'today': 0}
    out = {'team': blank(), 'by_mgr': {n: blank() for n in names}, 'by_city': {}, 'by_day': {}, 'reserved': 0, 'rows': 0, 'tabs': []}
    for vr in value_ranges:
        tab = vr.get('range', '').split('!')[0].strip("'").replace("''", "'")
        vals = vr.get('values', []) or []
        hi, hm = None, {}
        for i, row in enumerate(vals[:6]):
            m = _headers(row)
            if len(m) >= 4:
                hi, hm = i, m
                break
        if hi is None:
            hm = dict(FALLBACK)
            hi = 0
        for k, v in FALLBACK.items():
            hm.setdefault(k, v)
        out['tabs'].append(tab)
        city = out['by_city'].setdefault(tab, blank())
        for row in vals[hi + 1:]:
            row = list(row) + [''] * (26 - len(row))
            fio, phone = _s(row[hm['fio']]), _s(row[hm['phone']])
            if not fio and not phone:
                continue
            out['rows'] += 1
            paid = _num(row[hm['paid']])
            agreed, rest = _num(row[hm['agreed']]), _num(row[hm['rest']])
            kind = _norm(row[hm['kind']])
            mgr = _mgr(row[hm['mop']], names)
            if paid <= 0:
                out['reserved'] += 1
                continue
            is_full = (rest <= 0 and agreed > 0) or kind == 'оплата'
            counted = is_full if full_only else True
            day = _date(row[hm['date']], today)
            bucket = [out['team'], city]
            if mgr:
                bucket.append(out['by_mgr'].setdefault(mgr, blank()))
            for b in bucket:
                b['cash'] += paid
                b['agreed'] += agreed
                b['balance'] += max(rest, 0)
                if counted:
                    b['paid_n'] += 1
                if is_full:
                    b['full_n'] += 1
                else:
                    b['pre_n'] += 1
                if counted and day == today:
                    b['today'] += 1
            if counted and day:
                iso = day.isoformat()
                out['by_day'][iso] = out['by_day'].get(iso, 0) + 1
    out['by_mgr'] = {k: v for k, v in out['by_mgr'].items() if k in names or v['paid_n'] or v['cash']}
    return out


# ---------------------------------------------------------------- есеп
def _d(s):
    return date.fromisoformat(s)


def tier_info(c, today):
    tiers = sorted(c['tiers'], key=lambda t: t['from'])
    cur, nxt = None, None
    for i, t in enumerate(tiers):
        if _d(t['from']) <= today <= _d(t['to']):
            cur, nxt = t, (tiers[i + 1] if i + 1 < len(tiers) else None)
            break
    if cur is None:
        cur = tiers[0] if today < _d(tiers[0]['from']) else tiers[-1]
        nxt = None
    left = (_d(cur['to']) - today).days + 1
    return {'price': cur['price'], 'until': _d(cur['to']), 'left': max(left, 0), 'next_price': (nxt or {}).get('price'),
            'next_from': _d(nxt['from']) if nxt else None, 'tiers': tiers, 'index': tiers.index(cur)}


def stats(data, c, now):
    today = now.date()
    start, end = _d(c['start_date']), _d(c['end_date'])
    total_days = (end - start).days + 1
    idx = 0 if today < start else total_days if today > end else (today - start).days + 1
    days_left = total_days if today < start else 0 if today > end else (end - today).days + 1
    plan = int(c['plan'])
    paid = data['team']['paid_n']
    need = max(plan - paid, 0)
    exp_end = plan * idx / total_days
    exp_start = plan * max(idx - 1, 0) / total_days
    if paid >= exp_end:
        state = 'ahead'
    elif paid >= exp_start:
        state = 'ok'
    elif paid >= 0.8 * exp_start:
        state = 'behind'
    else:
        state = 'critical'
    names = [n for n in data['by_mgr'] if n != 'Басқа'] or ['—']
    per_day = math.ceil(need / days_left) if days_left else need
    ranking = sorted(data['by_mgr'].items(), key=lambda kv: (-kv[1]['paid_n'], -kv[1]['cash'], kv[0]))
    yesterday = data['by_day'].get((today - timedelta(days=1)).isoformat(), 0)
    return {'plan': plan, 'paid': paid, 'need': need, 'pct': round(100 * paid / plan) if plan else 0, 'idx': idx,
            'total_days': total_days, 'days_left': days_left, 'per_day': per_day, 'per_mgr': math.ceil(per_day / max(len(names), 1)),
            'exp_end': exp_end, 'exp_start': exp_start, 'state': state, 'ranking': ranking, 'today': data['team']['today'],
            'yesterday': yesterday, 'tier': tier_info(c, today), 'target_each': math.ceil(plan / max(len(names), 1)),
            'start': start, 'end': end}


STATE_TXT = {'ahead': 'ЖОСПАРДАН АЛДА', 'ok': 'ЖОСПАР БОЙЫНША', 'behind': 'АРТТА ҚАЛДЫҚ', 'critical': 'ҚЫЗЫЛ АЙМАҚ'}
STATE_EMO = {'ahead': '🔥', 'ok': '✅', 'behind': '⚠️', 'critical': '🚨'}


def money(v):
    return f'{int(round(v)):,}'.replace(',', ' ')


def tier_note(st):
    t = st['tier']
    if t['next_price'] and t['left'] <= 1:
        return f'⚠️ Бүгін соңғы күн! Ертең {money(t["next_price"])} ₸'
    if t['next_price']:
        return f'{t["until"]:%d.%m}-ге дейін, одан кейін {money(t["next_price"])} ₸'
    return f'{t["until"]:%d.%m}-ге дейін'


def _target(c, name, st):
    return int((c.get('targets') or {}).get(name) or st['target_each'])


def caption(kind, data, st, c):
    lead = st['ranking'][0] if st['ranking'] and st['ranking'][0][1]['paid_n'] else None
    head = f'{STATE_EMO[st["state"]]} {c["title"]} · {min(max(st["idx"], 1), st["total_days"])}-күн/{st["total_days"]}'
    base = f'{head}\n{st["paid"]}/{st["plan"]} оплата ({st["pct"]}%) · қалды {st["need"]}'
    price = f'💰 Қазір баға: {money(st["tier"]["price"])} ₸ ({tier_note(st)})'
    if kind == 'kick':
        txt = f'{base}\n🎯 Бүгінгі мақсат: +{st["per_day"]} (әр МОП ~{st["per_mgr"]})\n{price}\n{STATE_TXT[st["state"]]}'
        if st['yesterday']:
            txt += f'\nКеше: +{st["yesterday"]}'
    elif kind == 'mid':
        left = max(st['per_day'] - st['today'], 0)
        txt = f'⏱ Күн ортасы · бүгін +{st["today"]} (мақсат +{st["per_day"]}, қалды +{left})\n{base}\n{price}'
        if lead:
            txt += f'\n👑 Лидер: {lead[0]} ({lead[1]["paid_n"]})'
    elif kind == 'eve':
        hero = max(data['by_mgr'].items(), key=lambda kv: kv[1]['today']) if data['by_mgr'] else None
        txt = f'🌙 Күн қорытындысы: бүгін +{st["today"]} (мақсат +{st["per_day"]})\n{base}'
        if hero and hero[1]['today']:
            txt += f'\n⭐ Күн ұтқыны: {hero[0]} (+{hero[1]["today"]})'
        nxt = st['tier']
        if nxt['next_price'] and nxt['left'] <= 1:
            txt += f'\n🚀 Ертең баға {money(nxt["next_price"])} ₸ болады: бүгін соңғы мүмкіндік!'
        elif st['days_left'] > 1:
            txt += f'\nЕртең мақсат: +{math.ceil(st["need"] / (st["days_left"] - 1)) if st["days_left"] > 1 else st["need"]}'
    else:
        txt = f'{base}\n{price}\n{STATE_TXT[st["state"]]}'
        if lead:
            txt += f'\n👑 Лидер: {lead[0]} ({lead[1]["paid_n"]})'
    return txt[:1000]


# ---------------------------------------------------------------- сурет
FONT_R = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
          '/System/Library/Fonts/Supplemental/Arial.ttf', '/Library/Fonts/Arial.ttf', 'C:/Windows/Fonts/arial.ttf']
FONT_B = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
          '/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/Library/Fonts/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf']
_FC = {}
BG1, BG2, CARD, EDGE, TRACK = '#0A0F24', '#1C1247', '#141B3A', '#27316A', '#222A57'
TXT, MUT, GOLD, ORANGE, GREEN, RED, BLUE, SILVER, BRONZE = '#FFFFFF', '#8D98C4', '#FFC53D', '#FF7A3D', '#2EE6A6', '#FF4D6D', '#4DA3FF', '#C9D2EE', '#D9915A'
STATE_COL = {'ahead': GREEN, 'ok': GOLD, 'behind': ORANGE, 'critical': RED}


def _font(bold, px):
    from PIL import ImageFont
    key = (bold, px)
    if key not in _FC:
        f = None
        for p in (FONT_B if bold else FONT_R):
            try:
                f = ImageFont.truetype(p, px)
                break
            except Exception:
                continue
        if f is None:
            log.warning('liquidation: TTF қаріп табылмады (fonts-dejavu-core орнату керек)')
            try:
                f = ImageFont.load_default(px)
            except TypeError:
                f = ImageFont.load_default()
        _FC[key] = f
    return _FC[key]


class _C:
    def __init__(self, w, h, k=2):
        from PIL import Image, ImageDraw
        self.k, self.w, self.h = k, w, h
        top, bot = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (BG1, BG2)]
        img = Image.new('RGB', (w * k, h * k))
        d = ImageDraw.Draw(img)
        for y in range(h * k):
            t = y / (h * k)
            d.line((0, y, w * k, y), fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
        self.img, self.d = img, d

    def _x(self, xy):
        return [v * self.k for v in xy]

    def rr(self, xy, r, fill=None, outline=None, width=1):
        self.d.rounded_rectangle(self._x(xy), r * self.k, fill=fill, outline=outline, width=int(width * self.k) if outline else 0)

    def el(self, xy, fill=None, outline=None, width=1):
        self.d.ellipse(self._x(xy), fill=fill, outline=outline, width=int(width * self.k) if outline else 0)

    def arc(self, xy, a0, a1, fill, width):
        self.d.arc(self._x(xy), a0, a1, fill=fill, width=int(width * self.k))

    def poly(self, pts, fill):
        self.d.polygon([(x * self.k, y * self.k) for x, y in pts], fill=fill)

    def tx(self, x, y, t, px, fill=TXT, bold=False, anchor='l'):
        f = _font(bold, px * self.k)
        wd = self.d.textlength(t, font=f) / self.k
        if anchor == 'r':
            x -= wd
        elif anchor == 'm':
            x -= wd / 2
        self.d.text((x * self.k, y * self.k), t, font=f, fill=fill)
        return wd

    def width(self, t, px, bold=False):
        return self.d.textlength(t, font=_font(bold, px * self.k)) / self.k

    def png(self):
        from PIL import Image
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        b = io.BytesIO()
        out.save(b, 'PNG', optimize=True)
        return b.getvalue()


def _fit(c, t, px, maxw, bold=True):
    while c.width(t, px, bold) > maxw and len(t) > 3:
        t = t[:-2] + '…' if not t.endswith('…') else t[:-2] + '…'
    return t


def render(data, st, c, now):
    names = [n for n, _ in st['ranking']]
    rows = len(names)
    dy = 240
    H = 1034 + dy + rows * 112
    cv = _C(1080, H)
    col = STATE_COL[st['state']]
    # тақырып
    cv.tx(54, 42, c['title'], 62, GOLD, True)
    cv.tx(58, 118, f'{c["subtitle"]} · {st["start"]:%d.%m}–{st["end"]:%d.%m}', 28, MUT)
    chip = f'{min(max(st["idx"], 1), st["total_days"])}-КҮН / {st["total_days"]}'
    w = cv.width(chip, 30, True) + 48
    cv.rr((1026 - w, 52, 1026, 110), 29, fill=CARD, outline=EDGE, width=2)
    cv.tx(1026 - w / 2, 66, chip, 30, TXT, True, 'm')
    # hero карточка
    cv.rr((40, 170, 1040, 560), 36, fill=CARD, outline=EDGE, width=2)
    cx, cy, r = 250, 365, 148
    cv.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, TRACK, 38)
    pct = min(st['paid'] / st['plan'], 1) if st['plan'] else 0
    if pct > 0:
        cv.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * pct, col, 38)
        ang = math.radians(-90 + 360 * pct)
        for a in (math.radians(-90), ang):
            px, py = cx + (r - 19) * math.cos(a), cy + (r - 19) * math.sin(a)
            cv.el((px - 19, py - 19, px + 19, py + 19), fill=col)
    big = 88 if len(str(st['paid'])) <= 2 else 66
    cv.tx(cx, cy - 66 + (88 - big) * 0.4, str(st['paid']), big, TXT, True, 'm')
    cv.tx(cx, cy + 22, f'/ {st["plan"]}', 30, MUT, False, 'm')
    cv.tx(cx, cy + 62, f'{st["pct"]}%', 30, col, True, 'm')
    tx0 = 470
    cv.tx(tx0, 200, 'ҚАЛДЫ', 24, MUT, True)
    cv.tx(tx0, 228, str(st['need']), 78, TXT, True)
    cv.tx(tx0 + cv.width(str(st['need']), 78, True) + 18, 262, f'күніне +{st["per_day"]}', 30, GOLD, True)
    cv.rr((tx0, 340, 1010, 342), 1, fill=EDGE)
    t = st['tier']
    cv.tx(tx0, 360, 'ҚАЗІРГІ БАҒА', 24, MUT, True)
    cv.tx(tx0, 388, f'{money(t["price"])} ₸', 52, ORANGE if t['next_price'] and t['left'] <= 1 else TXT, True)
    cv.tx(tx0, 452, tier_note(st).replace('⚠️ ', ''), 26, RED if t['next_price'] and t['left'] <= 1 else MUT, t['left'] <= 1)
    lab = f'БҮГІН +{st["today"]}'
    ww = cv.width(lab, 28, True) + 44
    cv.rr((tx0, 492, tx0 + ww, 538), 23, fill=col)
    cv.tx(tx0 + ww / 2, 500, lab, 28, '#0A0F24', True, 'm')
    cv.tx(tx0 + ww + 22, 502, STATE_TXT[st['state']], 26, col, True)
    # лидер баннері + «Ожидается / Факт / Остаток»
    lead = st['ranking'][0] if st['ranking'] and st['ranking'][0][1]['paid_n'] else None
    cv.rr((40, 580, 1040, 636), 22, fill=GOLD)
    if lead:
        second = st['ranking'][1][1]['paid_n'] if len(st['ranking']) > 1 else 0
        cv.tx(64, 590, _fit(cv, f'★ ЛИДЕР: {lead[0]} · {lead[1]["paid_n"]} оплата', 32, 690), 32, '#0A0F24', True)
        cv.tx(1016, 596, f'2-орыннан +{lead[1]["paid_n"] - second}', 26, '#0A0F24', True, 'r')
    else:
        cv.tx(64, 590, '★ ЛИДЕР ӘЛІ ЖОҚ: бірінші оплата сенікі!', 32, '#0A0F24', True)
    cv.rr((40, 636, 1040, 684), 0, fill=CARD)
    shart = (c.get('prize') or f'Жоспарға тағы {st["need"]} оплата керек · күніне +{st["per_day"]}')
    cv.tx(64, 646, _fit(cv, shart, 26, 940, False), 26, TXT)
    tm = data['team']
    tiles = [('ОЖИДАЕТСЯ', tm['agreed'], TXT), ('ФАКТ · КІРГЕН АҚША', tm['cash'], GREEN), ('ОСТАТОК · ДОПЛАТА', tm['balance'], ORANGE)]
    tw = (1000 - 2 * 14) / 3
    for i, (lab, val, colr) in enumerate(tiles):
        tx0 = 40 + i * (tw + 14)
        cv.rr((tx0, 706, tx0 + tw, 806), 22, fill=CARD, outline=EDGE, width=2)
        cv.tx(tx0 + tw / 2, 718, lab, 20, MUT, True, 'm')
        cv.tx(tx0 + tw / 2, 748, _fit(cv, f'{money(val)} ₸', 36, tw - 24), 36, colr, True, 'm')
    # ұпай жолағы: нақты vs жоспар сызығы
    cv.tx(54, 588 + dy, 'ЖОСПАР ЖОЛЫ', 22, MUT, True)
    x0, x1, y0 = 54, 1026, 624 + dy
    cv.rr((x0, y0, x1, y0 + 30), 15, fill=TRACK)
    if pct > 0:
        cv.rr((x0, y0, x0 + max((x1 - x0) * pct, 30), y0 + 30), 15, fill=col)
    mx = x0 + (x1 - x0) * min(st['exp_end'] / st['plan'], 1) if st['plan'] else x0
    cv.rr((mx - 3, y0 - 10, mx + 3, y0 + 40), 3, fill=TXT)
    cv.tx(min(mx, x1 - 150), y0 + 44, f'бүгін керек: {math.ceil(st["exp_end"])}', 22, MUT)
    # баға баспалдағы
    cv.tx(54, 722 + dy, 'БАҒА БАСПАЛДАҒЫ · әр қадамда қымбаттайды', 22, MUT, True)
    n = len(t['tiers'])
    bw = (972 - 16 * (n - 1)) / n
    for i, tr in enumerate(t['tiers']):
        bx = 54 + i * (bw + 16)
        cur = i == t['index']
        past = i < t['index']
        cv.rr((bx, 756 + dy, bx + bw, 850 + dy), 22, fill=(GOLD if cur else CARD), outline=(None if cur else EDGE), width=2)
        fg = '#0A0F24' if cur else (MUT if past else TXT)
        cv.tx(bx + bw / 2, 768 + dy, f'{money(tr["price"])} ₸', 34, fg, True, 'm')
        cv.tx(bx + bw / 2, 812 + dy, f'{_d(tr["from"]):%d.%m}–{_d(tr["to"]):%d.%m}', 22, fg, False, 'm')
    # жарыс
    y = 890 + dy
    cv.tx(54, y, 'ЖАРЫС · МЕНЕДЖЕРЛЕР', 26, TXT, True)
    cv.tx(1026, y + 4, f'әрқайсысына ~{st["target_each"]}', 22, MUT, False, 'r')
    y += 52
    medal = [GOLD, SILVER, BRONZE]
    top_n = st['ranking'][0][1]['paid_n'] if st['ranking'] else 0
    for i, (name, v) in enumerate(st['ranking']):
        ry = y + i * 112
        cv.rr((40, ry, 1040, ry + 100), 26, fill=CARD, outline=(GOLD if i == 0 and v['paid_n'] else EDGE), width=2)
        mc = medal[i] if i < 3 and v['paid_n'] else TRACK
        cv.el((62, ry + 24, 114, ry + 76), fill=mc)
        cv.tx(88, ry + 33, str(i + 1), 30, '#0A0F24' if mc != TRACK else MUT, True, 'm')
        cv.tx(134, ry + 14, _fit(cv, name, 34, 250), 34, TXT, True)
        tgt = _target(c, name, st)
        bx0, bx1 = 134, 700
        cv.rr((bx0, ry + 62, bx1, ry + 82), 10, fill=TRACK)
        fr = min(v['paid_n'] / tgt, 1) if tgt else 0
        if fr > 0:
            cv.rr((bx0, ry + 62, bx0 + max((bx1 - bx0) * fr, 20), ry + 82), 10, fill=medal[i] if i < 3 else BLUE)
        cv.tx(724, ry + 18, str(v['paid_n']), 52, TXT, True)
        cv.tx(724 + cv.width(str(v['paid_n']), 52, True) + 8, ry + 44, f'/{tgt}', 24, MUT)
        sub = f'{money(v["cash"])} ₸'
        cv.tx(1016, ry + 22, sub, 24, MUT, False, 'r')
        if v['today']:
            cv.tx(1016, ry + 58, f'+{v["today"]} бүгін', 26, GREEN, True, 'r')
        elif i > 0 and top_n > v['paid_n']:
            cv.tx(1016, ry + 58, f'лидерге −{top_n - v["paid_n"]}', 22, MUT, False, 'r')
    fy = y + rows * 112 + 22
    cv.tx(54, fy, f'Жаңартылды {now:%d.%m %H:%M}', 22, MUT)
    cv.tx(1026, fy, f'Жоспар {st["plan"]} · {st["end"]:%d.%m}-ге дейін', 22, MUT, False, 'r')
    return cv.png()


# ---------------------------------------------------------------- деректер
def fetch(bot, now, force=False):
    c = cfg(bot.config)
    cached = bot.store.get('lq:data')
    try:
        if cached and not force and (now - datetime.fromisoformat(cached['at'])).total_seconds() < c['poll_seconds']:
            return cached['data']
        ranges = ["'%s'!A1:Y%d" % (n.replace("'", "''"), c['max_rows']) for n in c['sheet_names']]
        vrs = bot.sheets.formatted_values(c['spreadsheet_id'], ranges)
        data = parse(vrs, [p['name'] for p in bot.config.get('team', [])], now.date(), c)
        bot.store.set('lq:data', {'at': now.isoformat(), 'data': data})
        bot.store.set('lq:err', '')
        return data
    except Exception as exc:
        log.warning('liquidation sheet read failed: %s', type(exc).__name__)
        try:
            bot.store.set('lq:err', type(exc).__name__ + ': ' + str(exc)[:160])
        except Exception:
            pass
        if cached and (now - datetime.fromisoformat(cached['at'])).total_seconds() < 6 * 3600:
            return cached['data']
        return None


def _ctx():
    try:
        from . import dashboard
        return dashboard._ctx()
    except Exception:
        return None


def send_photo(token, chat_id, png, caption=''):
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in (('chat_id', str(chat_id)), ('caption', caption))]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="tablo.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + png + b'\r\n')
    parts.append(f'--{b}--\r\n'.encode())
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendPhoto', b''.join(parts), {'Content-Type': 'multipart/form-data; boundary=' + b})
    with urllib.request.urlopen(req, timeout=40, context=_ctx()) as r:
        return json.loads(r.read().decode())


def _post(bot, chat, png, cap):
    return send_photo(bot.config['token'], chat, png, cap)


def _mention(bot, name):
    try:
        return bot.mention(name)
    except Exception:
        return escape(name)


WIN = ['🔥 {m} · +{k} оплата!', '💥 {m} тағы +{k} жапты!', '🚀 {m} · +{k} оплата, тоқтамаймыз!', '⚡ {m} +{k} қосты!', '💰 {m} · +{k} оплата кассаға!']


def _celebrate(bot, now, c, data, st, chat):
    cur = {'paid_n': st['paid'], 'mgr': {n: v['paid_n'] for n, v in data['by_mgr'].items()}}
    base = bot.store.get('lq:base')
    bot.store.set('lq:base', cur)
    if base is None or not c['celebrate'] or not chat:
        return
    wins = [(n, k) for n, v in cur['mgr'].items() if (k := v - (base.get('mgr') or {}).get(n, 0)) > 0]
    if not wins:
        return
    n_all = bot.store.get('lq:wins_n') or 0
    lines = []
    for i, (n, k) in enumerate(wins):
        lines.append(WIN[(n_all + i) % len(WIN)].format(m=_mention(bot, n), k=k))
    bot.store.set('lq:wins_n', n_all + len(wins))
    lead = st['ranking'][0] if st['ranking'] else None
    tail = f'Команда: <b>{st["paid"]}/{st["plan"]}</b> ({st["pct"]}%) · қалды {st["need"]}'
    if st['days_left']:
        tail += f' · {st["days_left"]} күн'
    if lead and lead[1]['paid_n']:
        tail += f'\n👑 Лидер: {escape(lead[0])} ({lead[1]["paid_n"]})'
    bot.enqueue(f'lq:win:{now:%Y%m%d%H%M%S}', '\n'.join(lines) + '\n' + tail, now, chat=chat, expires=now + timedelta(minutes=30))
    ms = [m for m in sorted({round(st['plan'] * f) for f in (0.25, 0.5, 0.75, 1)} | {50, 100, 150, 200})
          if base['paid_n'] < m <= cur['paid_n'] and m <= st['plan']]
    for m in ms[-1:]:
        key = f'lq:ms:{m}'
        if bot.store.get(key):
            continue
        try:
            _post(bot, chat, render(data, st, c, now), f'🏁 {m} оплата! ' + caption('misc', data, st, c))
            bot.store.set(key, True)
        except Exception as exc:
            log.warning('liquidation milestone failed: %s', type(exc).__name__)


def due(bot, now):
    c = cfg(bot.config)
    if not enabled(bot.config) or now.weekday() not in c['days']:
        return
    start, end = _d(c['start_date']), _d(c['end_date'])
    if now.date() < start - timedelta(days=1) or now.date() > end:
        return
    data = fetch(bot, now)
    if not data:
        return
    st = stats(data, c, now)
    chat = bot.config.get('chat_id')
    try:
        _celebrate(bot, now, c, data, st, chat)
    except Exception:
        log.exception('liquidation celebrate failed')
    zk = f'lq:zp:{now.date().isoformat()}'
    if now.hour >= 21 and not bot.store.get(zk) and bot.config.get('owner_id'):
        try:
            bot.enqueue(zk, salary_text(bot, data, c, now), now, chat=bot.config['owner_id'], expires=now + timedelta(hours=3))
            bot.store.set(zk, True)
        except Exception:
            log.exception('liquidation zp push failed')
    slots = sorted(c['push_at'])
    for i, hhmm in enumerate(slots):
        h, m = map(int, hhmm.split(':'))
        since = now.hour * 60 + now.minute - (h * 60 + m)
        key = f'lq:{now.date().isoformat()}:{hhmm}'
        if not 0 <= since < 120 or bot.store.get(key) or not chat:
            continue
        tries, last = bot.store.get(key + ':n') or 0, bot.store.get(key + ':t')
        if tries >= 4 or (last and (now - datetime.fromisoformat(last)).total_seconds() < 300):
            continue
        bot.store.set(key + ':n', tries + 1)
        bot.store.set(key + ':t', now.isoformat())
        kind = 'kick' if i == 0 else 'eve' if i == len(slots) - 1 else 'mid'
        try:
            _post(bot, chat, render(data, st, c, now), caption(kind, data, st, c))
            bot.store.set(key, True)
            log.info('liquidation tablo sent: %s', hhmm)
        except Exception as exc:
            log.warning('liquidation tablo failed (%s/4): %s', tries + 1, type(exc).__name__)


# ---------------------------------------------------------------- ЗП есебі
def _rates(config):
    c = cfg(config)
    b = config.get('bonus') or {}
    r = {'full': b.get('pay', 10000), 'pre': b.get('prepay', 5000), 'percent': 0}
    r.update(c.get('salary') or {})
    return r


def _fines(bot, start):
    out = {}
    try:
        from . import fines
        from datetime import date as _date
        for iso in bot.store.get('fines:days') or []:
            if _date.fromisoformat(iso) < start:
                continue
            for name, rec in fines._data(bot, _date.fromisoformat(iso)).items():
                out[name] = out.get(name, 0) + fines._fsum(rec)
    except Exception:
        pass
    return out


def salary_rows(bot, data, c):
    r = _rates(bot.config)
    fn = _fines(bot, _d(c['start_date']))
    rows = []
    for name, v in sorted(data['by_mgr'].items(), key=lambda kv: (-kv[1]['paid_n'], kv[0])):
        if name == 'Басқа':
            continue
        bonus = v['full_n'] * r['full'] + v['pre_n'] * r['pre'] + v['cash'] * r['percent'] / 100
        fine = fn.get(name, 0)
        rows.append({'name': name, 'paid_n': v['paid_n'], 'full': v['full_n'], 'pre': v['pre_n'], 'cash': v['cash'],
                     'bonus': int(bonus), 'fine': int(fine), 'net': int(bonus - fine)})
    return rows, r


def salary_text(bot, data, c, now):
    rows, r = salary_rows(bot, data, c)
    L = [f'<b>ЗП есебі · {escape(c["title"])}</b> ({_d(c["start_date"]):%d.%m}–{now:%d.%m})']
    for x in rows:
        if not (x['paid_n'] or x['fine']):
            continue
        L.append(f'<b>{escape(x["name"])}</b>: {x["paid_n"]} оплата ({x["full"]} толық, {x["pre"]} пред.) · касса {money(x["cash"])} ₸\n'
                 f'   бонус {money(x["bonus"])}' + (f' − штраф {money(x["fine"])}' if x['fine'] else '') + f' = <b>{money(x["net"])} ₸</b>')
    tot = sum(x['net'] for x in rows)
    L.append(f'\n<b>Жиыны: {money(tot)} ₸</b> · бонус {money(sum(x["bonus"] for x in rows))} · штраф {money(sum(x["fine"] for x in rows))}')
    rule = f'толық оплата × {money(r["full"])} + предоплата × {money(r["pre"])}' + (f' + кассадан {r["percent"]}%' if r['percent'] else '')
    L.append(f'<i>Есеп: {rule}, штраф алынады. Баға болжам: нақты формула басқа болса, config.json → liquidation.salary.</i>')
    return '\n'.join(L)


def prices_text(config, now):
    c = cfg(config)
    st = tier_info(c, now.date())
    lines = ['<b>Ликвидация · Senior Marketer</b> (онлайн курс + офлайн практикум)']
    for i, tr in enumerate(st['tiers']):
        mark = '👉 ' if i == st['index'] else ''
        lines.append(f'{mark}{money(tr["price"])} ₸ · {_d(tr["from"]):%d.%m}–{_d(tr["to"]):%d.%m}')
    lines.append(f'Қазір: <b>{money(st["price"])} ₸</b>, {tier_note({"tier": st})}.')
    lines.append(f'Сатылым {_d(c["end_date"]):%d.%m} күні жабылады.')
    return '\n'.join(lines)


def command(bot, now, chat, key, which='/tablo', private_owner=True):
    """/tablo: қазіргі табло, /zp: ЗП есебі (тек Саятқа жеке чатта)."""
    c = cfg(bot.config)
    if not enabled(bot.config):
        return bot._reply(key, 'Табло әлі қосылмаған: config.json ішіндегі liquidation бөлімін толтыру керек.', now, chat)
    data = fetch(bot, now, force=True)
    if not data:
        err = escape((bot.store.get('lq:err') or 'белгісіз қате')[:160])
        return bot._reply(key, f'Табло шықпады: кестені оқи алмадым ({err}). Кестеге service account email-ін Viewer ретінде қосыңыз.', now, chat)
    if which == '/zp':
        if not private_owner:
            return bot._reply(key, 'ЗП есебі тек Саяттың ботпен жеке чатында ашылады.', now, chat)
        return bot._reply(key, salary_text(bot, data, c, now), now, chat)
    st = stats(data, c, now)
    try:
        _post(bot, chat, render(data, st, c, now), caption('misc', data, st, c))
    except Exception as exc:
        bot._reply(key, 'Сурет жіберілмеді: ' + escape(type(exc).__name__) + '\n' + escape(caption('misc', data, st, c)), now, chat)
