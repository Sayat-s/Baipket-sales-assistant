"""Ликвидация табло мен геолокация түзетулерінің тесттері (Telegram/Google-сыз)."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from baipket_bot import checkin, liquidation as lq
from baipket_bot.store import Store

TZ = ZoneInfo('Asia/Almaty')
HEAD = ['№', 'МОП ', 'ФИО', 'Телефон нөмірі', 'Эл.почта', 'Теллеграм номер / НИК или аккаунт ', 'Дата покупки ',
        'Вид оплаты (голд, рассрочка)  ', 'Возраст', 'Город', 'Статус (собственник, маркетолог, смм, фриланс)', 'Откуда клиент:',
        'Договоренная сумма ', 'Внесла', 'Остаток', 'Вид оплаты', 'Дали доступ?']


def row(n, mop, fio, phone, date, agreed, paid, rest, kind):
    r = [''] * 25
    r[0], r[1], r[2], r[3], r[6], r[12], r[13], r[14], r[15] = n, mop, fio, phone, date, agreed, paid, rest, kind
    return r


def vr(tab, rows):
    return {'range': f"'{tab}'!A1:Y400", 'values': [HEAD] + rows}


FIXTURE = [
    vr('Алматы', [row(1, 'Арман', 'A A', '8701', '17.11', '179 000,00', '179 000,00', '0,00', 'оплата'),
                  row(2, 'Нурай', 'B B', '8702', '18.11', '179 000,00', '179 000,00', '0,00', 'оплата'),
                  row(3, 'Арман', 'C C', '8703', '18.11', '179 000,00', '0,00', '179 000,00', '')]),
    vr('Астана', [row(1, 'Еңлік', 'D D', '8704', '17.11', '179 000,00', '179 000,00', '0,00', 'оплата'),
                  row(2, 'Еңлік', 'E E', '8705', '18.11', '179 000,00', '50 000,00', '129 000,00', 'предоплата')]),
    vr('Шымкент', [row(1, 'Алия', 'F F', '8706', '16.11', '179 000,00', '170 000,00', '9 000,00', 'предоплата')]),
    vr('Ақтау', []),
]
TEAM = ['Ленара', 'Олжас', 'Ерасыл', 'Арман', 'Нұрай', 'Алия', 'Еңлік']


class FakeSheets:
    def formatted_values(self, sid, ranges):
        self.last = (sid, ranges)
        return FIXTURE


class FakeBot:
    def __init__(self, tmp, extra=None):
        self.store = Store(Path(tmp) / 'bot.db')
        self.config = {'timezone': 'Asia/Almaty', 'token': '1:T', 'chat_id': -5, 'owner_id': 77, 'owner_name': 'Саят',
                       'team': [{'name': n, 'role': 'manager'} for n in TEAM],
                       'liquidation': {'enabled': True, 'spreadsheet_id': 'SID', 'count_mode': 'paid'}}
        self.config.update(extra or {})
        self.sheets = FakeSheets()
        self.sent, self.replies = [], []

    def enqueue(self, key, text, now, **kw):
        self.sent.append((key, text, kw))

    def mention(self, name):
        return f'<a>{name}</a>'

    def _reply(self, key, text, now, chat=None):
        self.replies.append((key, text, chat))


class LiquidationTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.now = datetime(2026, 11, 18, 14, 0, tzinfo=TZ)
        self.c = lq.cfg({'liquidation': {'enabled': True, 'spreadsheet_id': 'SID'}})

    def tearDown(self):
        self._t.cleanup()

    def test_parse_counts_paid_rows_headers_and_aliases(self):
        d = lq.parse(FIXTURE, TEAM, self.now.date(), self.c)
        self.assertEqual(d['team']['paid_n'], 5)           # ақша түскен 5 студент
        self.assertEqual(d['reserved'], 1)                  # төлемсіз бронь
        self.assertEqual(d['team']['full_n'], 3)
        self.assertEqual(d['team']['pre_n'], 2)
        self.assertEqual(d['team']['cash'], 179000 * 3 + 50000 + 170000)
        self.assertEqual(d['by_mgr']['Нұрай']['paid_n'], 1)  # «Нурай» транслит
        self.assertEqual(d['by_mgr']['Еңлік']['today'], 1)
        self.assertEqual(d['team']['today'], 2)
        self.assertEqual(d['by_day']['2026-11-17'], 2)

    def test_full_mode_counts_only_fully_paid(self):
        d = lq.parse(FIXTURE, TEAM, self.now.date(), dict(self.c, count_mode='full'))
        self.assertEqual(d['team']['paid_n'], 3)

    def test_numbers_and_dates(self):
        self.assertEqual(lq._num('179 000,00'), 179000)
        self.assertEqual(lq._num('1,234.50'), 1234.5)
        self.assertEqual(lq._num('—'), 0)
        self.assertEqual(lq._date('17.11', self.now.date()).isoformat(), '2026-11-17')
        self.assertEqual(lq._date('17.11.26', self.now.date()).isoformat(), '2026-11-17')
        self.assertEqual(lq._date(46343, self.now.date()).year, 2026)

    def test_stats_and_tiers(self):
        d = lq.parse(FIXTURE, TEAM, self.now.date(), self.c)
        st = lq.stats(d, self.c, self.now)
        self.assertEqual((st['paid'], st['need'], st['idx'], st['days_left']), (5, 256, 2, 13))
        self.assertEqual(st['per_day'], 20)
        self.assertEqual(st['state'], 'critical')
        self.assertEqual(st['tier']['price'], 179000)
        t21 = lq.tier_info(self.c, datetime(2026, 11, 21).date())
        self.assertEqual((t21['left'], t21['next_price']), (1, 239000))
        t28 = lq.tier_info(self.c, datetime(2026, 11, 28).date())
        self.assertIsNone(t28['next_price'])
        self.assertIn('соңғы күн', lq.tier_note(dict(st, tier=t21)))

    def test_render_png(self):
        from PIL import Image
        import io
        d = lq.parse(FIXTURE, TEAM, self.now.date(), self.c)
        png = lq.render(d, lq.stats(d, self.c, self.now), self.c, self.now)
        im = Image.open(io.BytesIO(png))
        self.assertEqual(im.size[0], 1080)
        self.assertGreater(im.size[1], 1500)

    def test_celebrate_baseline_then_win_and_slot_once(self):
        bot = FakeBot(self.tmp)
        photos = []
        lq._post = lambda b, chat, png, cap: photos.append((chat, cap))
        lq.due(bot, datetime(2026, 11, 18, 9, 0, tzinfo=TZ))
        self.assertEqual(bot.sent, [])                       # бірінші рет: baseline, спам жоқ
        FIXTURE[3]['values'].append(row(1, 'Алия', 'G G', '8707', '18.11', '179 000,00', '179 000,00', '0,00', 'оплата'))
        try:
            bot.store.set('lq:data', None)
            lq.due(bot, datetime(2026, 11, 18, 13, 5, tzinfo=TZ))
            self.assertEqual(len(bot.sent), 1)
            self.assertIn('+1', bot.sent[0][1])
            self.assertIn('Алия', bot.sent[0][1])
            self.assertEqual(len(photos), 1)                  # 13:00 слоты
            bot.store.set('lq:data', None)
            lq.due(bot, datetime(2026, 11, 18, 13, 20, tzinfo=TZ))
            self.assertEqual(len(photos), 1)                  # қайталанбайды
            self.assertEqual(len(bot.sent), 1)
        finally:
            FIXTURE[3]['values'].pop()


    def test_salary_report_and_banner_render(self):
        bot = FakeBot(self.tmp, {'bonus': {'pay': 10000, 'prepay': 5000}})
        d = lq.parse(FIXTURE, TEAM, self.now.date(), self.c)
        rows, rates = lq.salary_rows(bot, d, self.c)
        by = {r['name']: r for r in rows}
        self.assertEqual((by['Арман']['full'], by['Арман']['pre'], by['Арман']['bonus']), (1, 0, 10000))
        self.assertEqual((by['Еңлік']['full'], by['Еңлік']['pre'], by['Еңлік']['bonus']), (1, 1, 15000))
        txt = lq.salary_text(bot, d, self.c, self.now)
        self.assertIn('Жиыны', txt)
        self.assertIn('Еңлік', txt)
        png = lq.render(d, lq.stats(d, self.c, self.now), self.c, self.now)
        self.assertGreater(len(png), 20000)

    def test_zp_is_owner_private_only(self):
        bot = FakeBot(self.tmp)
        lq.command(bot, self.now, -5, 'k', '/zp', False)
        self.assertIn('жеке чатында', bot.replies[-1][1])
        lq.command(bot, self.now, 77, 'k2', '/zp', True)
        self.assertIn('ЗП есебі', bot.replies[-1][1])

    def test_zp_daily_push_to_owner_once(self):
        bot = FakeBot(self.tmp)
        lq._post = lambda *a: None
        n = datetime(2026, 11, 18, 21, 10, tzinfo=TZ)
        lq.due(bot, n)
        lq.due(bot, n)
        z = [m for m in bot.sent if m[0].startswith('lq:zp:')]
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0][2]['chat'], 77)

    def test_disabled_does_nothing(self):
        bot = FakeBot(self.tmp)
        bot.config['liquidation']['enabled'] = False
        lq.due(bot, self.now)
        self.assertEqual((bot.sent, bot.replies), ([], []))


class GeoTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.bot = FakeBot(self._t.name, {'checkin': {'enabled': True, 'start': '12:00', 'grace_minutes': 15, 'days': [0, 1, 2, 3, 4, 5]}})
        self.now = datetime(2026, 11, 18, 15, 0, tzinfo=TZ)   # сәрсенбі
        self._today = dict(getattr(checkin, 'TODAY', {}) or {})
        checkin.TODAY = {}                                     # басқа тесттердің жұмыс кестесі әсер етпесін

    def tearDown(self):
        checkin.TODAY = self._today
        self._t.cleanup()

    def msg(self, at, **kw):
        m = {'location': {'latitude': 43.2, 'longitude': 76.9}, 'date': int(at.timestamp())}
        m.update(kw)
        return m

    def test_uses_message_time_not_processing_time(self):
        sent_at = datetime(2026, 11, 18, 12, 5, tzinfo=TZ)     # уақытында жіберген, бот 3 сағат кейін өңдеді
        checkin.on_location(self.bot, self.msg(sent_at), 1, 'Арман', False, -5, 10, self.now)
        _, state = checkin._state(self.bot.store, self.now)
        self.assertEqual(state['in']['Арман']['late_min'], 5)
        self.assertEqual(self.bot.replies, [])                  # ескі хабарға жауап жазылмайды

    def test_forward_ignored_and_weekend_message(self):
        checkin.on_location(self.bot, self.msg(self.now, forward_origin={'type': 'user'}), 1, 'Арман', False, -5, 10, self.now)
        _, state = checkin._state(self.bot.store, self.now)
        self.assertNotIn('Арман', state['in'])
        sunday = datetime(2026, 11, 22, 13, 0, tzinfo=TZ)
        checkin.on_location(self.bot, self.msg(sunday), 2, 'Арман', False, -5, 10, sunday)
        self.assertIn('демалыс', self.bot.replies[-1][1])

    def test_owner_private_location_sets_office_and_far_is_rejected(self):
        checkin.on_location(self.bot, self.msg(self.now), 3, 'Саят', True, 77, 77, self.now)
        self.assertEqual(self.bot.store.get('office')['lat'], 43.2)
        self.assertGreaterEqual(self.bot.store.get('office')['radius_m'], 400)
        far = self.msg(self.now)
        far['location'] = {'latitude': 51.1, 'longitude': 71.4}
        checkin.on_location(self.bot, far, 4, 'Арман', False, -5, 10, self.now)
        _, state = checkin._state(self.bot.store, self.now)
        self.assertNotIn('Арман', state['in'])


if __name__ == '__main__':
    unittest.main()
