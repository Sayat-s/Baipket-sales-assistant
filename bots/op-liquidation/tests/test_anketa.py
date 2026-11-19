"""Анкета -> кесте тесттері (Telegram/Google-сыз, нақты кесте құрылымын қайталайтын жалған сессия)."""
import copy
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from baipket_bot import anketa as aq, liquidation as lq
from baipket_bot.store import Store

TZ = ZoneInfo('Asia/Almaty')
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=TZ)
TEAM = ['Ленара', 'Олжас', 'Ерасыл', 'Арман', 'Нұрай', 'Алия', 'Еңлік']
HEAD = ['№', 'МОП ', 'ФИО', 'Телефон нөмірі', 'Эл.почта', 'Теллеграм номер / НИК или аккаунт ', 'Дата покупки ',
        'Вид оплаты (голд, рассрочка)  ', 'Возраст', 'Город', 'Статус (собственник, маркетолог, смм, фриланс)', 'Откуда клиент:',
        'Договоренная сумма ', 'Внесла', 'Остаток', 'Вид оплаты', 'Дали доступ?', 'Курсқа қатысудағы негізгі запросы',
        'Договормен танысты ма?', 'Ережелермен танысты ма?', 'Қабылдау қағазын алды ма?', 'Группаға кірді ме?',
        'Телеграм чатқа қосылды', 'ДОПЛАТА КҮНІ:', 'КОММЕНТАРИЙ']


def mkrow(**kw):
    r = [''] * 25
    for k, v in kw.items():
        r[int(k[1:])] = v
    return r


def sheet():
    first = mkrow(c0=1, c1='Арман', c2='Торгаев А', c3='87066881039', c6='17.11', c9='Алматы', c12='179 000,00', c13='179 000,00',
                  c14='=M2-N2', c15='оплата')
    blank = [''] * 16 + [False, '', False, False, False, False, False, '', '']      # алдын ала қойылған чекбокстар, 25 баған
    return {t: [list(HEAD)] + ([first] if t == 'Алматы' else []) + [list(blank) for _ in range(30)] for t in ('Алматы', 'Астана', 'Шымкент', 'Ақтау')}


class Resp:
    def __init__(self, body=None, code=200):
        self.body, self.code = body or {}, code

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.code >= 400:
            raise OSError(f'HTTP {self.code}')


class Sess:
    def __init__(self, data):
        self.data, self.writes, self.fail = data, [], None

    def get(self, url, params=None, timeout=0):
        tabs = [v.split('!')[0].strip("'") for k, v in params if k == 'ranges']
        return Resp({'valueRanges': [{'values': self.data[t]} for t in tabs]})

    def post(self, url, json=None, timeout=0):
        if self.fail:
            return Resp(code=self.fail)
        self.opt = json.get('valueInputOption')
        for item in json['data']:
            rng = item['range']
            tab = rng.split('!')[0].strip("'")
            cell = rng.split('!')[1]
            col = 0
            for ch in cell.rstrip('0123456789'):
                col = col * 26 + ord(ch) - 64
            row = int(cell.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')) - 1
            self.data[tab][row][col - 1] = item['values'][0][0]
            self.writes.append((tab, row, col - 1, item['values'][0][0]))
        return Resp({})


class TG:
    def __init__(self):
        self.calls = []

    def call(self, m, d=None, **k):
        self.calls.append((m, d))
        return True


class Bot:
    def __init__(self, tmp):
        self.store = Store(Path(tmp) / 'b.db')
        self.config = {'owner_id': 77, 'chat_id': -5, 'owner_name': 'Саят', 'token': 'x', 'team': [{'name': n} for n in TEAM],
                       'liquidation': {'enabled': True, 'spreadsheet_id': 'SID'}}
        self.sent, self.telegram = [], TG()

    def enqueue(self, key, text, now, **kw):
        self.sent.append((key, text, kw))


ANKETA = """Анкета
ФИО: Сейтқали Ерназар Нұрланұлы
Телефон: +7 (777) 123-45-67
Email: ernazar@gmail.com
Telegram: @ernazar_s
Возраст: 24
Город: Астана
Статус: смм
Запрос: жеке бренд және жоғары чек
"""



REAL = """1. Аты-жөніңіз: Айдана Серікқызы
2. Жасыңыз: 22
3. Телефон нөміріңіз: 8 705 111 22 33
4. Электронды поштаңыз: aidana@mail.ru
5. Telegram аккаунтыңыз: @aidana_s
6. Қазіргі салаңыз / мамандығыңыз: SMM маманы
7. Қай қаладансыз: Қарағанды
8. Бағдарламадан күтетін нәтижеңіз (запрос): Өз брендімді дамыту
9. Бағдарламаға қатысу үшін қай қалаға келе аласыз: Астана
"""


class AnketaTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.bot = Bot(self._t.name)
        self.data = sheet()
        self.sess = Sess(self.data)
        aq._sess = lambda: self.sess
        self.bot.config['liquidation']['anketa'] = {'auto_write': False}

    def tearDown(self):
        self._t.cleanup()

    def send(self, text, **msgkw):
        msg = dict({'text': text, 'chat': {'id': 77}}, **msgkw)
        return aq.handle(self.bot, msg, text, 77, True, 77, NOW, 'k')

    def press(self, did, act, n=1):
        cb = {'id': f'cb{n}', 'data': f'aq:{did}:{act}', 'from': {'id': 77}, 'message': {'chat': {'id': 77}}}
        return aq.callback(self.bot, cb, NOW)

    def draft(self):
        return self.bot.store.get('aq:draft:77')

    def test_parse_labels_phone_tab(self):
        f = aq.parse(ANKETA, TEAM, 179000)
        self.assertEqual(f['fio'], 'Сейтқали Ерназар Нұрланұлы')
        self.assertEqual(f['phone'], '87771234567')
        self.assertEqual((f['email'], f['tg'], f['age'], f['city']), ('ernazar@gmail.com', '@ernazar_s', '24', 'Астана'))
        self.assertEqual(f['agreed'], 179000)
        self.assertEqual(aq.norm_tab('г. Түркістан', ['Алматы', 'Астана', 'Шымкент', 'Ақтау'], aq.DEFAULT_CITY_TABS), 'Шымкент')

    def test_free_text_without_labels_and_forwarded_nick(self):
        f = aq.parse('Айдана Серікқызы\n87051112233\nаidana@mail.ru\nАлматы', TEAM, None, 'aidana_tg')
        self.assertEqual((f['fio'], f['phone'], f['tg']), ('Айдана Серікқызы', '87051112233', '@aidana_tg'))

    def test_not_anketa_ignored(self):
        self.assertFalse(self.send('Командада не болып жатыр?'))
        self.assertFalse(self.send('Задача Нұрай: оффер жібер. Дедлайн ертең 18:00'))
        self.assertEqual(self.bot.sent, [])

    def test_group_or_non_owner_ignored(self):
        self.assertFalse(aq.handle(self.bot, {'chat': {'id': -5}}, ANKETA, 103, False, -5, NOW, 'k'))

    def test_preview_asks_missing_then_merges_followup_and_writes_first_empty_row(self):
        self.assertTrue(self.send(ANKETA))
        txt = self.bot.sent[-1][1]
        self.assertIn('Жетіспейді', txt)
        self.assertIn('МОП', txt)
        self.assertEqual(self.draft()['tab'], 'Астана')
        self.assertEqual(self.sess.writes, [])                       # растаусыз жазылмайды
        self.assertTrue(self.send('МОП: Еңлік\nВнесла: 179000'))
        self.assertNotIn('Жетіспейді', self.bot.sent[-1][1])
        kb = self.bot.sent[-1][2]['keyboard']['inline_keyboard']
        self.assertIn('✅', kb[0][0]['text'])
        did = self.draft()['id']
        self.assertTrue(self.press(did, 'ok'))
        wrote = {(c): v for (t, r, c, v) in self.sess.writes}
        row = self.data['Астана'][1]                                 # Астанада бірінші жол бос болған
        self.assertEqual((row[1], row[2], row[3]), ('Еңлік', 'Сейтқали Ерназар Нұрланұлы', '87771234567'))
        self.assertEqual((row[4], row[5], row[8], row[9], row[10]), ('ernazar@gmail.com', '@ernazar_s', 24, 'Астана', 'смм'))
        self.assertEqual((row[12], row[13], row[14], row[15]), (179000, 179000, 0, 'оплата'))
        self.assertEqual(row[0], 1)
        self.assertEqual(row[6], '18.11')
        self.assertEqual(row[16], False)                             # чекбокстарға тимеді
        self.assertEqual(row[24], 'Практикум Астана: 1–6 ақпан')
        self.assertTrue(any('✅' in m[1] and 'Астана' in m[1] for m in self.bot.sent))
        self.assertTrue(self.press(did, 'ok', 2))                    # қайта басу екінші жол жазбайды
        self.assertEqual(len([w for w in self.sess.writes if w[2] == 2]), 1)

    def test_next_row_number_and_formula_cell_untouched_in_almaty(self):
        a = ANKETA.replace('Астана', 'Алматы') + 'МОП: Арман\nВнесла: 170000\nВид оплаты: рассрочка\n'
        self.send(a)
        self.press(self.draft()['id'], 'ok')
        row = self.data['Алматы'][2]                                 # 1-жол тақырып, 2-жол толы, жаңа жол 3-інші
        self.assertEqual((row[0], row[1], row[7], row[12], row[13], row[14], row[15]), (2, 'Арман', 'рассрочка', 179000, 170000, 9000, 'предоплата'))
        self.assertEqual(self.data['Алматы'][1][14], '=M2-N2')       # бар формула сақталды


    def test_real_template_kazakh_labels_tab_from_question_9_and_amount_line(self):
        f = aq.parse(REAL + "179000 рассрочка", TEAM, 179000)
        self.assertEqual((f['fio'], f['age'], f['phone'], f['email'], f['tg']), ('Айдана Серікқызы', '22', '87051112233', 'aidana@mail.ru', '@aidana_s'))
        self.assertEqual((f['status'], f['city'], f['attend']), ('SMM маманы', 'Қарағанды', 'Астана'))
        self.assertEqual(f['request'], 'Өз брендімді дамыту')
        self.assertEqual((f['paid'], f['plan']), (179000, 'рассрочка'))
        self.send(REAL + "170000 голд")
        self.assertEqual(self.draft()['tab'], 'Астана')                       # 7-қала емес, 9-практикум қаласы
        self.assertIn('Практикум Астана', self.bot.sent[-1][1])
        kb = self.bot.sent[-1][2]['keyboard']['inline_keyboard']
        self.assertTrue(any(b['text'] == 'Арман' for r in kb for b in r))     # МОП батырмалары
        self.press(self.draft()['id'], 'm3')                                  # Арман
        self.assertEqual(self.draft()['f']['mop'], 'Арман')
        self.press(self.draft()['id'], 'ok')
        row = self.data['Астана'][1]
        self.assertEqual((row[1], row[2], row[7], row[9], row[12], row[13], row[14], row[15]),
                         ('Арман', 'Айдана Серікқызы', 'голд', 'Қарағанды', 179000, 170000, 9000, 'предоплата'))
        self.assertEqual(row[24], 'Практикум Астана: 1–6 ақпан')

    def test_amount_and_plan_in_separate_followup(self):
        self.send(REAL)
        self.assertIn('Внесла', self.bot.sent[-1][1])
        self.send('179000 рассрочка')
        self.assertEqual((self.draft()['f']['paid'], self.draft()['f']['plan']), (179000, 'рассрочка'))


    def test_numbered_answers_without_labels_and_invisible_chars(self):
        W = '\u2060'
        txt = (f"1.{W} Кулжабекова Назгуль\n2.{W} {W}29\n3.{W} {W}87067367797\n4.{W} {W}nazekagabba@gmail.com\n5.{W} {W}Nazeken_07\n"
               f"6.{W} {W}смм\n7.{W} {W}Астана\n8.{W} {W}маркетинг саласын білу, чек көтеру\n9.{W} {W}Астана\n179000 рассрочка")
        f = aq.parse(txt, TEAM, 179000)
        self.assertEqual((f['fio'], f['age'], f['phone'], f['email'], f['tg']), ('Кулжабекова Назгуль', '29', '87067367797', 'nazekagabba@gmail.com', '@Nazeken_07'))
        self.assertEqual((f['status'], f['city'], f['attend'], f['request']), ('смм', 'Астана', 'Астана', 'маркетинг саласын білу, чек көтеру'))
        self.assertEqual((f['paid'], f['plan']), (179000, 'рассрочка'))
        self.assertTrue(self.send(txt))
        self.assertEqual(self.draft()['tab'], 'Астана')
        self.press(self.draft()['id'], 'm1')
        self.press(self.draft()['id'], 'ok')
        row = self.data['Астана'][1]
        self.assertEqual((row[1], row[2], row[3], row[8], row[9], row[10], row[13]), ('Олжас', 'Кулжабекова Назгуль', '87067367797', 29, 'Астана', 'смм', 179000))


    def test_nearest_practicum_city_for_smaller_towns(self):
        tabs = ['Алматы', 'Астана', 'Шымкент', 'Ақтау']
        m = aq.DEFAULT_CITY_TABS
        got = {c: aq.norm_tab(c, tabs, m) for c in ['Қарағанды', 'Түркістан', 'Ақтөбе', 'Тараз-Алматы', 'Талдықорған', 'Қызылорда', 'Павлодар',
                                                    'Атырау', 'г. Тараз', 'Алматы', 'Шымкент']}
        self.assertEqual(got, {'Қарағанды': 'Астана', 'Түркістан': 'Шымкент', 'Ақтөбе': 'Ақтау', 'Тараз-Алматы': 'Алматы', 'Талдықорған': 'Алматы',
                               'Қызылорда': 'Шымкент', 'Павлодар': 'Астана', 'Атырау': 'Ақтау', 'г. Тараз': 'Шымкент', 'Алматы': 'Алматы',
                               'Шымкент': 'Шымкент'})
        self.assertIsNone(aq.norm_tab('Мәскеу', tabs, m))
        self.send(REAL.replace('Астана', 'Қарағанды') + '179000')           # 9-сұрақ шағын қала
        self.assertEqual(self.draft()['tab'], 'Астана')
        self.assertIn('ең жақын', self.bot.sent[-1][1])


    def test_nearest_hub_by_map_distance(self):
        tabs = ['Алматы', 'Астана', 'Шымкент', 'Ақтау']
        self.assertEqual(aq.nearest_hub('Сәтбаев', tabs)[0], 'Астана')
        self.assertEqual(aq.nearest_hub('Ақтөбе', tabs)[0], 'Ақтау')
        self.assertEqual(aq.nearest_hub('Қызылорда', tabs)[0], 'Шымкент')
        self.assertEqual(aq.nearest_hub('Текелі', tabs)[0], 'Алматы')
        tab, km = aq.nearest_hub('Қарағанды', tabs)
        self.assertEqual(tab, 'Астана')
        self.assertTrue(180 <= km <= 240, km)                       # нақты ~ 210 км
        self.assertIsNone(aq.nearest_hub('Мәскеу', tabs))
        self.send(REAL.replace('Астана', 'Сәтбаев') + '179000')
        self.assertIn('картадағы ең жақын', self.bot.sent[-1][1])
        self.assertIn('км', self.bot.sent[-1][1])


    def test_unnumbered_lines_and_other_separators_still_fill_everything(self):
        order = "Жүсіпбек Аяулым\n22\n8 705 580 26 91\nayaulymzhusipbek3@gmail.com\nswayau\nSMM маманы\nТүркістан\nМаркетингті үйреніп, өз брендімді дамытқым келеді\nАстана\n"
        f = aq.parse(order + "МОП: Олжас\nВнесла 179,000 тг\nРассрочка", TEAM, 179000)
        self.assertEqual((f['fio'], f['age'], f['phone'], f['email'], f['tg']), ('Жүсіпбек Аяулым', '22', '87055802691', 'ayaulymzhusipbek3@gmail.com', '@swayau'))
        self.assertEqual((f['status'], f['city'], f['attend']), ('SMM маманы', 'Түркістан', 'Астана'))
        self.assertEqual(f['request'], 'Маркетингті үйреніп, өз брендімді дамытқым келеді')
        self.assertEqual((f['paid'], f['plan'], f['mop']), (179000, 'рассрочка', 'Олжас'))
        g = aq.parse("1 - Назгуль Кулжан\n2) 29\n№3: 87067367797\n4 – a@b.kz\n5. @nz_07\n6: смм\n7. Астана\n8. чек көтеру\n9. Астана", TEAM)
        self.assertEqual((g['fio'], g['age'], g['phone'], g['email'], g['tg'], g['status'], g['request'], g['attend']),
                         ('Назгуль Кулжан', '29', '87067367797', 'a@b.kz', '@nz_07', 'смм', 'чек көтеру', 'Астана'))

    def test_duplicate_warning(self):
        self.send(ANKETA.replace('+7 (777) 123-45-67', '8 706 688 10 39'))
        self.assertIn('бұрыннан бар', self.bot.sent[-1][1])

    def test_unknown_city_needs_tab_choice_and_tab_button(self):
        self.send(ANKETA.replace('Астана', 'Мәскеу') + 'МОП: Алия\nВнесла: 50000')
        self.assertIn('қала/парақ', self.bot.sent[-1][1])
        self.assertTrue(self.press(self.draft()['id'], 't2'))
        self.assertEqual(self.draft()['tab'], 'Шымкент')
        self.assertNotIn('Жетіспейді', self.bot.sent[-1][1])
        self.press(self.draft()['id'], 'ok')
        self.assertEqual(self.data['Шымкент'][1][1], 'Алия')
        self.assertEqual(self.data['Шымкент'][1][15], 'предоплата')

    def test_cancel_and_forbidden_hint(self):
        self.send(ANKETA + 'МОП: Арман\nВнесла: 179000')
        did = self.draft()['id']
        self.sess.fail = 403
        self.press(did, 'ok')
        self.assertTrue(any('Editor' in m[1] for m in self.bot.sent))
        self.sess.fail = None
        self.assertEqual(self.draft()['done'], None)                 # қайта әрекет етуге болады
        self.press(did, 'no', 3)
        self.assertEqual(self.draft()['done'], 'cancel')

    def test_other_user_cannot_press(self):
        self.send(ANKETA)
        cb = {'id': 'x', 'data': 'aq:' + self.draft()['id'] + ':ok', 'from': {'id': 103}, 'message': {'chat': {'id': -5}}}
        self.assertTrue(aq.callback(self.bot, cb, NOW))
        self.assertEqual(self.sess.writes, [])

    def test_tier_price_by_date_used_as_agreed(self):
        late = datetime(2026, 11, 23, 12, 0, tzinfo=TZ)
        msg = {'text': ANKETA, 'chat': {'id': 77}}
        aq.handle(self.bot, msg, ANKETA, 77, True, 77, late, 'k')
        self.assertEqual(self.draft()['f']['agreed'], 239000)


class TG2(TG):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def send(self, payload):
        self.msgs.append(('send', payload))
        return {'message_id': len(self.msgs)}

    def call(self, m, d=None, **k):
        if m == 'editMessageText':
            self.msgs.append(('edit', d))
        return super().call(m, d, **k)


class AutoTests(unittest.TestCase):
    """Толық анкета бірден жазылады, бір хабарлама өзгертіледі, қайтару бар."""
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.bot = Bot(self._t.name)
        self.bot.telegram = TG2()
        self.data = sheet()
        self.sess = Sess(self.data)
        aq._sess = lambda: self.sess

    def tearDown(self):
        self._t.cleanup()

    def send(self, text):
        return aq.handle(self.bot, {'text': text, 'chat': {'id': 77}}, text, 77, True, 77, NOW, 'k')

    def press(self, act, n=1):
        d = self.bot.store.get('aq:draft:77')
        cb = {'id': f'c{n}', 'data': f'aq:{d["id"]}:{act}', 'from': {'id': 77}, 'message': {'chat': {'id': 77}}}
        return aq.callback(self.bot, cb, NOW)

    def test_users_real_flow_amount_in_separate_message_one_edited_message(self):
        body = REAL.replace('Астана', 'Астана').replace('Қарағанды', 'Астана')
        self.send(body)
        sends = [m for m in self.bot.telegram.msgs if m[0] == 'send']
        self.assertEqual(len(sends), 1)
        self.assertIn('Жетіспейді', sends[0][1]['text'])
        self.assertEqual(self.sess.writes, [])
        self.send('МОП: Олжас\nВнесла 179,000 тг\nРассрочка')
        row = self.data['Астана'][1]
        self.assertEqual((row[1], row[2], row[7], row[12], row[13], row[14], row[15]), ('Олжас', 'Айдана Серікқызы', 'рассрочка', 179000, 179000, 0, 'оплата'))
        msgs = self.bot.telegram.msgs
        self.assertEqual(len([m for m in msgs if m[0] == 'send']), 1)                # жаңа хабарлама жоқ
        edits = [m for m in msgs if m[0] == 'edit']
        self.assertTrue(edits and edits[-1][1]['message_id'] == 1)
        self.assertIn('✅', edits[-1][1]['text'])
        self.assertIn('undo', str(edits[-1][1]['reply_markup']))
        self.assertEqual(self.sess.opt, 'RAW')

    def test_full_message_writes_immediately(self):
        self.send(REAL + 'МОП: Арман\n179 000 голд')
        self.assertEqual(self.data['Астана'][1][1], 'Арман')
        self.assertEqual(self.data['Астана'][1][7], 'голд')
        self.assertEqual(len([m for m in self.bot.telegram.msgs if m[0] == 'send']), 1)


    def test_missing_extras_still_autowrite_and_followup_fills(self):
        short = "1. Аты-жөніңіз: Жүсіпбек Аяулым\n3. Телефон нөміріңіз: 87055802691\n4. Электронды поштаңыз: a@b.kz\n5. Telegram аккаунтыңыз: @swayau\n9. Бағдарламаға қатысу үшін қай қалаға келе аласыз: Астана\nМОП: Олжас\n179000 рассрочка"
        self.send(short)
        self.assertEqual(self.data['Астана'][1][2], 'Жүсіпбек Аяулым')        # бірден жазылды
        txt = self.bot.telegram.msgs[-1][1]['text']
        self.assertIn('Бос қалды', txt)
        self.assertIn('запрос', txt)
        self.send('Запрос: маркетингті үйрену\nЖасы: 22\nСтатус: смм')
        self.assertEqual(self.data['Астана'][1][17], 'маркетингті үйрену')
        self.assertEqual(self.data['Астана'][1][8], 22)

    def test_duplicate_needs_confirmation(self):
        self.send(REAL.replace('8 705 111 22 33', '8 706 688 10 39') + 'МОП: Арман\n179000')
        self.assertEqual(self.sess.writes, [])
        self.assertIn('бұрыннан бар', self.bot.telegram.msgs[-1][1]['text'])
        self.assertIn('Қосу', str(self.bot.telegram.msgs[-1][1]['reply_markup']))

    def test_undo_clears_written_cells_only(self):
        self.send(REAL + 'МОП: Арман\n179000')
        self.assertEqual(self.data['Астана'][1][2], 'Айдана Серікқызы')
        self.data['Астана'][1][21] = 'қолмен жазылған'                                   # адам кейін қосқан ұяшық
        self.press('undo')
        row = self.data['Астана'][1]
        self.assertEqual((row[1], row[2], row[3], row[13]), ('', '', '', ''))
        self.assertEqual(row[21], 'қолмен жазылған')
        self.assertIn('Қайтарылды', self.bot.telegram.msgs[-1][1]['text'])
        n = len(self.sess.writes)
        self.press('undo', 2)
        self.assertEqual(len(self.sess.writes), n)

    def test_formula_injection_is_written_as_text(self):
        evil = REAL.replace('Айдана Серікқызы', '=HYPERLINK("http://x","a")')
        self.send(evil + 'МОП: Арман\n179000')
        self.assertEqual(self.sess.opt, 'RAW')
        self.assertEqual(self.data['Астана'][1][2], '=HYPERLINK("http://x","a")')


if __name__ == '__main__':
    unittest.main()
