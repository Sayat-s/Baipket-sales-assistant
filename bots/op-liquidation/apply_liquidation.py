#!/usr/bin/env python3
"""Baipket ОП ботын «Ликвидация» өніміне жаңарту.

Қолдану (серверде):  cd /opt/op-bot && python3 apply_liquidation.py --sheet-id <ID>
Не істейді:
  1. baipket_bot/liquidation.py + llm.py қосады (табло, пуштар, Grok/OpenAI-үйлесімді API);
  2. app.py / checkin.py түзетеді: /tablo, геолокация уақыты (хабарлама уақыты), forward-ты елемеу, /setoffice (read-only config-та істейді);
  3. Dockerfile-ға қаріптер қосады (дашборд жазуы көрінбейтін себебі);
  4. config.json: liquidation бөлімі, КЭВ/созвонға байланған пуштар өшіріледі.
Қайталап іске қосуға болады (екінші рет ештеңе бұзбайды). Алдымен backup жасалады."""
import argparse
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/Sayat-s/Baipket-sales-assistant/claude/adoring-noether-eiml2n/bots/op-liquidation/'
NEW_FILES = ['liquidation.py', 'anketa.py', 'llm.py']

APP_TICK_OLD = """        try:
            from . import dashboard as _db
            _db.due(self,now)
        except Exception:
            pass
        self.check_tasks(now)
"""
APP_TICK_NEW = """        try:
            from . import dashboard as _db
            _db.due(self,now)
        except Exception:
            pass
        try:
            from . import liquidation as _lq
            _lq.due(self,now)
        except Exception:
            pass
        self.check_tasks(now)
"""
APP_CMD_OLD = """        if command=='/reports':
            if not is_owner:
                return
"""
APP_CMD_NEW = """        from . import liquidation as _lq0
        if command=='/tablo' or (command in ('/dashboard','/report') and _lq0.enabled(self.config)):
            _lq0.command(self,now,chat,key);return
        if command=='/reports':
            if not is_owner:
                return
"""
APP_DAILY_OLD = """        for dkey,dtext,dexp in _dl.due(self.store,self.config,self.calendar if self.fresh('calendar',now) else None,now,lambda n:bool(self.user_id(n))):
"""
APP_DAILY_NEW = """        from . import liquidation as _lqd
        for dkey,dtext,dexp in ([] if _lqd.enabled(self.config) else _dl.due(self.store,self.config,self.calendar if self.fresh('calendar',now) else None,now,lambda n:bool(self.user_id(n)))):
"""
APP_PRICES_OLD = """        if command=='/prices':self._reply(key,price_text(self.config,now),now,chat);return
"""
APP_PRICES_NEW = """        if command=='/prices':
            from . import liquidation as _lqp
            self._reply(key,_lqp.prices_text(self.config,now) if _lqp.enabled(self.config) else price_text(self.config,now),now,chat);return
"""
APP_MSG_OLD = """        if not text:return
        chat=msg['chat']['id'];head,*tail=text.split(maxsplit=1)
"""
APP_MSG_NEW = """        if not text:return
        chat=msg['chat']['id'];head,*tail=text.split(maxsplit=1)
        from . import anketa as _aq
        if _aq.handle(self,msg,text,uid,is_owner,chat,now,key):return
"""
APP_CB_OLD = """        parts=callback.get('data','').split(':')
        if len(parts)!=2 or not parts[1].isdigit(): return
"""
APP_CB_NEW = """        from . import anketa as _aqc
        if _aqc.callback(self,callback,now): return
        parts=callback.get('data','').split(':')
        if len(parts)!=2 or not parts[1].isdigit(): return
"""
APP_LOC_OLD = """            answer=_ck.handle_location(self.store,self.config,name,loc['latitude'],loc['longitude'],now)
            if answer: self._reply(uid_key,answer,now,chat=chat_id)
"""
APP_LOC_NEW = """            _ck.on_location(self,msg,uid_key,name,is_owner,chat_id,user_id,now)
"""
APP_OFFICE_OLD = """                import json as _j
                _p='config.json'
                _c=_j.load(open(_p,encoding='utf-8'))
                _r=int((_c.get('checkin',{}).get('office') or {}).get('radius_m') or 400)
                _r=max(_r,400)
                _c.setdefault('checkin',{})['office']={'lat':_lat,'lon':_lon,'radius_m':_r}
                _j.dump(_c,open(_p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
                self.config.setdefault('checkin',{})['office']={'lat':_lat,'lon':_lon,'radius_m':_r}
"""
APP_OFFICE_NEW = """                _r=int((self.config.get('checkin',{}).get('office') or {}).get('radius_m') or 400)
                _r=max(_r,400)
                self.store.set('office',{'lat':_lat,'lon':_lon,'radius_m':_r})
                self.config.setdefault('checkin',{})['office']={'lat':_lat,'lon':_lon,'radius_m':_r}
"""
CK_OLD = """    if not c['enabled'] or not name or name in c['remote']:
        return None
    key, state = _state(store, now)
    if name in state['in']:
        return escape(rop.ALREADY.format(n=name))
    o = c['office']
"""
CK_NEW = """    if not c['enabled'] or not name or name in c['remote']:
        return None
    if now.weekday() not in c['days']:
        return escape('Бүгін демалыс күні, келу белгісі жазылмайды 🙂')
    if now.hour * 60 + now.minute < 6 * 60:
        return None
    key, state = _state(store, now)
    if name in state['in']:
        return escape(rop.ALREADY.format(n=name))
    o = store.get('office') or c['office']
"""
CK_APPEND = '''

def on_location(bot, msg, key, name, is_owner, chat_id, user_id, now):
    """Геолокация хабарламасы: уақыт = хабарламаның нақты уақыты (бот қайта қосылса да штраф қате болмайды)."""
    from datetime import datetime
    loc = msg['location']
    if is_owner and chat_id == user_id:
        r = max(int(((_cfg(bot.config).get('office') or {}).get('radius_m')) or 300), 400)
        o = {'lat': loc['latitude'], 'lon': loc['longitude'], 'radius_m': r}
        bot.store.set('office', o)
        bot.config.setdefault('checkin', {})['office'] = o
        bot._reply(key, escape(f'Офис нүктесі сақталды ✅ {o["lat"]:.5f}, {o["lon"]:.5f}, радиус {r} м. '
                               'Енді одан алыс жерден жіберілген геолокация келу болып есептелмейді.'), now, chat=chat_id)
        return
    if msg.get('forward_origin') or msg.get('forward_date') or msg.get('forward_from'):
        return
    when = now
    if msg.get('date'):
        try:
            when = datetime.fromtimestamp(msg['date'], now.tzinfo)
        except Exception:
            when = now
    if when > now:
        when = now
    answer = handle_location(bot.store, bot.config, name, loc['latitude'], loc['longitude'], when)
    if answer and (now - when).total_seconds() <= 1800:
        bot._reply(key, answer, now, chat=chat_id)
'''
LLM = """import os


def endpoint():
    return (os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1').rstrip('/') + '/responses'


def adapt(payload):
    \"\"\"OpenAI емес провайдер (мысалы Grok/xAI) үшін developer рөлін system-ке аударады.\"\"\"
    if 'api.openai.com' in endpoint():
        return payload
    p = dict(payload)
    p['input'] = [dict(m, role='system') if m.get('role') == 'developer' else m for m in p.get('input', [])]
    return p
"""
CHAT_OLD = """    request = Request('https://api.openai.com/v1/responses',
        data=json.dumps(payload, ensure_ascii=False).encode(), method='POST',"""
CHAT_NEW = """    from . import llm
    request = Request(llm.endpoint(),
        data=json.dumps(llm.adapt(payload), ensure_ascii=False).encode(), method='POST',"""
GAI_OLD = "    req = Request('https://api.openai.com/v1/responses', data=json.dumps(payload, ensure_ascii=False).encode(), method='POST',"
GAI_NEW = "    from . import llm\n    req = Request(llm.endpoint(), data=json.dumps(llm.adapt(payload), ensure_ascii=False).encode(), method='POST',"
NLP_OLD = '    request = Request(_ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST", headers={'
NLP_NEW = '    from . import llm\n    request = Request(llm.endpoint(), data=json.dumps(llm.adapt(payload), ensure_ascii=False).encode("utf-8"), method="POST", headers={'


def edit(path, old, new, marker):
    s = path.read_text(encoding='utf-8')
    if marker in s:
        print(f'  = {path.name}: бұрын қолданылған ({marker[:30].strip()}…)')
        return
    if s.count(old) != 1:
        sys.exit(f'ҚАТЕ: {path.name} ішінде күтілген үзінді {s.count(old)} рет кездесті (1 болу керек). Код нұсқасы басқа, тоқтадым, ештеңе бұзылған жоқ.')
    path.write_text(s.replace(old, new), encoding='utf-8')
    print(f'  + {path.name}')


def get_new_file(name, pkg, here, base):
    src = here / name
    dst = pkg / name
    if name == 'llm.py':
        dst.write_text(LLM, encoding='utf-8')
    elif src.exists():
        shutil.copy(src, dst)
    else:
        with urllib.request.urlopen(base + name, timeout=60) as r:
            dst.write_bytes(r.read())
    print(f'  + {name}')


def patch_config(path, sheet_id):
    c = json.loads(path.read_text(encoding='utf-8'))
    old = c.get('liquidation') or {}
    c['liquidation'] = {
        'sheet_names': ['Алматы', 'Астана', 'Шымкент', 'Ақтау'], 'plan': 261,
        'start_date': '2026-11-17', 'end_date': '2026-11-30',
        'tiers': [{'price': 179000, 'from': '2026-11-17', 'to': '2026-11-21'},
                  {'price': 239000, 'from': '2026-11-22', 'to': '2026-11-25'},
                  {'price': 299000, 'from': '2026-11-26', 'to': '2026-11-30'}],
        'push_at': ['13:00', '17:00', '20:00'], 'celebrate': True, 'count_mode': 'paid', 'targets': {},
        'title': 'ЛИКВИДАЦИЯ', 'subtitle': 'Senior Marketer',
    }
    c['liquidation'].update({k: v for k, v in old.items() if k != 'enabled' and v not in (None, '')})
    c['liquidation']['enabled'] = True
    if sheet_id:
        c['liquidation']['spreadsheet_id'] = sheet_id
    for k in ('recognition', 'kev', 'reports', 'wins', 'dashboard', 'calendar_hourly'):
        c.setdefault(k, {})['enabled'] = False
    if isinstance(c.get('owner_report'), dict):
        c['owner_report']['report_times'] = []
    camp = c.get('campaigns')
    if isinstance(camp, dict):
        camp['prices'] = [{'name': 'Senior Marketer ликвидация (онлайн + офлайн практикум)', 'presales': 179000,
                           'regular': 299000, 'available': True}]
    for p in c.get('team', []):
        p['daily_calls'] = None
    path.write_text(json.dumps(c, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('  + config.json: liquidation қосылды, КЭВ/созвон пуштары өшірілді')


def patch_dockerfile(path):
    if not path.exists():
        print('  ! Dockerfile табылмады, қаріптерді қолмен қосыңыз')
        return
    s = path.read_text(encoding='utf-8')
    if 'fonts-dejavu-core' in s:
        print('  = Dockerfile: қаріптер бұрын қосылған')
        return
    n = re.sub(r'(\n\s*)tzdata(\s*\\?)', r'\1tzdata fonts-dejavu-core fonts-liberation\2', s, count=1)
    if n == s:
        sys.exit('ҚАТЕ: Dockerfile ішінен tzdata жолын таппадым. Қолмен: apt-get install -y fonts-dejavu-core')
    path.write_text(n, encoding='utf-8')
    print('  + Dockerfile: fonts-dejavu-core, fonts-liberation')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='.')
    ap.add_argument('--sheet-id', default='')
    ap.add_argument('--base', default=BASE)
    a = ap.parse_args()
    root = Path(a.dir).resolve()
    pkg = root / 'baipket_bot'
    if not (pkg / 'app.py').exists():
        sys.exit(f'ҚАТЕ: {root} ішінде baipket_bot/app.py жоқ. Бот папкасында іске қосыңыз (/opt/op-bot).')
    bk = root.parent / (root.name + '-backup-' + time.strftime('%Y%m%d-%H%M%S'))
    bk.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pkg, bk / "baipket_bot", dirs_exist_ok=True)
    for f in ('config.json', 'Dockerfile'):
        if (root / f).exists():
            shutil.copy(root / f, bk / f)
    print('Backup:', bk)
    here = Path(__file__).resolve().parent
    for f in NEW_FILES:
        get_new_file(f, pkg, here, a.base)
    edit(pkg / 'app.py', APP_TICK_OLD, APP_TICK_NEW, '_lq.due(self,now)')
    edit(pkg / 'app.py', APP_CMD_OLD, APP_CMD_NEW, '_lq0.command')
    edit(pkg / 'app.py', APP_DAILY_OLD, APP_DAILY_NEW, '_lqd.enabled')
    edit(pkg / 'app.py', APP_PRICES_OLD, APP_PRICES_NEW, 'prices_text')
    edit(pkg / 'app.py', APP_MSG_OLD, APP_MSG_NEW, '_aq.handle')
    edit(pkg / 'app.py', APP_CB_OLD, APP_CB_NEW, '_aqc.callback')
    edit(pkg / 'app.py', APP_LOC_OLD, APP_LOC_NEW, '_ck.on_location')
    edit(pkg / 'app.py', APP_OFFICE_OLD, APP_OFFICE_NEW, "self.store.set('office'")
    edit(pkg / 'checkin.py', CK_OLD, CK_NEW, "o = store.get('office')")
    ck = pkg / 'checkin.py'
    if 'def on_location' not in ck.read_text(encoding='utf-8'):
        ck.write_text(ck.read_text(encoding='utf-8') + CK_APPEND, encoding='utf-8')
        print('  + checkin.py: on_location')
    edit(pkg / 'chat.py', CHAT_OLD, CHAT_NEW, 'llm.endpoint()')
    edit(pkg / 'group_ai.py', GAI_OLD, GAI_NEW, 'llm.endpoint()')
    edit(pkg / 'nlp.py', NLP_OLD, NLP_NEW, 'llm.endpoint()')
    patch_dockerfile(root / 'Dockerfile')
    patch_config(root / 'config.json', a.sheet_id)
    print('\nДайын. Енді: docker compose build && docker compose up -d')


if __name__ == '__main__':
    main()
