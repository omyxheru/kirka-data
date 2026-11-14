"""Your Kirka quests (daily + event), readable, from the logged-in Kirka window (Chrome on port 9222).

  python tools/quests.py              capture the active quests from the game, print them, save kirka-api/quests.json
  python tools/quests.py json         the same, printing the JSON
  python tools/quests.py serve [port] a local API on http://127.0.0.1:5190 (CORS open):
                                        /quests          all types
                                        /quests/hourly   /quests/daily   /quests/event

Only the active quests (what to do, the reward, when it ends): no personal progress. The list changes only when the
dailies reset (~05:12 UTC) or an event ends, so the API serves the saved capture and needs the game only once that
capture has run out: then it re-captures from the Kirka window if it's open, or keeps serving the old one with
"stale": true.

How: it asks the game's own quest endpoint from inside the kirka.io tab with the tab's own login, the same read-only
call the client makes when the quest panel loads (POST api2.kirka.io/api/<quests>). Nothing is claimed or changed.
The game obfuscates paths, field names and enum values; the maps below were read from the client (version 0.44.4,
2026-11-13) and may change when Kirka updates: if a field comes back raw, re-map it (captures/network-20261113).
The login token never leaves the browser and is never printed or saved.
"""
import json
import pathlib
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import kirka_page  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'kirka-api' / 'quests.json'
WEB = ROOT / 'skin-library' / 'public' / 'quests.json'

API = 'https://api2.kirka.io/api'
QUESTS = '/wNnWmM'                                  # POST {type}: the quests of one type, with your progress
TYPES = {'hourly': 'wNnWwmW', 'daily': 'wwMNmWnW', 'event': 'wwMNW'}   # weekly: "Weekly quests are coming soon." (client text)

# ---- obfuscated field names -> readable (from the recorded answers)
QUEST_F = {'WnWwwNmM': 'id', 'WwMWmwn': 'type', 'WwMWmn': 'task', 'wNnWmwM': 'with', 'wNmMn': 'goal',
           'wnMNWmwW': 'endsAt', 'wNmMnW': 'difficulty', 'wnMmwNW': 'rewards', 'wMNmWWw': 'progress'}
REWARD_F = {'WnWwwNmM': 'id', 'WwMWmwn': 'kind', 'wNmMn': 'amount', 'WwMWnmN': 'item'}
ITEM_F = {'WnWwwNmM': 'id', 'WwMWmn': 'name', 'WwMWmwn': 'itemType', 'wNmMnW': 'rarity'}

# ---- obfuscated enum values -> words. Filled from the in-game quest panel; anything missing stays as its code.
TYPE_V = {v: k for k, v in TYPES.items()}
# checked against the quest menu: "Win 12 games" pays 3000 XP (WnWwwN) and 1500 coins (wwMNWmWn)
REWARD_V = {'WnWwwN': 'xp', 'wwMNWmWn': 'coins', 'wMNmW': 'diamonds', 'WwMWnmNw': 'item'}
# read off the quest panel on 2026-11-14 (e.g. "Earn 6,081 score with AR9", "Get 216 headshots")
TASK_V = {'wWnWNmM': 'kills', 'wWnWNmwM': 'score', 'wMWnwmN': 'headshots', 'wWMmnwNW': 'headshots',
          'WwMWnNm': 'wins', 'wnMmw': 'killstreak'}
WITH_V = {'WmMnwwW': 'AR9', 'wnMmwN': 'Bayonet', 'WmMnwwN': 'LAR', 'wwMNWWn': 'MAC-10', 'WwMWnm': 'VITA'}   # other weapons: not seen yet
# the quest's rarity: the menu's Rarity filter (Common, Rare, Epic, Legendary) and the colour bar on each quest
DIFF_V = {'wNwWm': 'common', 'WwwmnN': 'rare', 'WwwmnWMN': 'epic', 'wMWwWmnN': 'legendary'}
RARITY_V = {'wMNmnWwW': 'rarity?'}


def _ask_http(token, kind):
    """one quest type, called directly with the stored login (no browser needed)"""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(API + QUESTS, method='POST', data=json.dumps({'WwMWmwn': TYPES[kind]}).encode(),
                                 headers={'authorization': 'Bearer ' + token, 'csrf': 'token',
                                          'content-type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {'status': r.status, 'body': json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {'status': e.code, 'error': e.read()[:200].decode('utf-8', 'replace')}


def _ask(page, kind):
    """one quest type, from inside the kirka.io tab with its own login (the token stays in the page)"""
    js = """async ([api, path, type]) => {
      const t = localStorage.getItem('token')
      if (!t) return { error: 'not logged in: log in to Kirka in the debug Chrome window first' }
      const r = await fetch(api + path, { method: 'POST', credentials: 'include',
        headers: { 'authorization': 'Bearer ' + t, 'csrf': 'token', 'content-type': 'application/json',
                   'accept': 'application/json, text/plain, */*' },
        body: JSON.stringify({ WwMWmwn: type }) })
      const text = await r.text()
      try { return { status: r.status, body: JSON.parse(text) } } catch { return { status: r.status, error: text.slice(0, 300) } }
    }"""
    return page.evaluate(js, [API, QUESTS, TYPES[kind]])


def _map(d, fields):
    return {fields.get(k, k): v for k, v in (d or {}).items()}


def readable(raw_quest):
    q = _map(raw_quest, QUEST_F)
    q['type'] = TYPE_V.get(q.get('type'), q.get('type'))
    q['task'] = TASK_V.get(q.get('task'), q.get('task'))
    w = q.get('with')
    q['with'] = None if w in (None, 'undefined') else WITH_V.get(w, w)
    q['rarity'] = DIFF_V.get(q.pop('difficulty', None), None)
    # the sentence the game shows, e.g. "Get 483 kills with Bayonet", "Win 12 games", "Get a 24 killstreak"
    n, t = q.get('goal', 0), q['task']
    q['text'] = ({'score': f'Earn {n:,} score', 'wins': f'Win {n:,} games', 'killstreak': f'Get a {n:,} killstreak'}
                 .get(t, f'Get {n:,} {t}')) + (f" with {q['with']}" if q['with'] else '')
    q.pop('progress', None)                          # just the quest, not anyone's progress on it
    rw = []
    for r in q.get('rewards') or []:
        r = _map(r, REWARD_F)
        r['kind'] = REWARD_V.get(r.get('kind'), r.get('kind'))
        if r.get('item'):
            it = _map(r['item'], ITEM_F)
            r['item'] = {'name': it.get('name'), 'id': it.get('id')}
        rw.append(r)
    q['rewards'] = rw
    return q


def fetch(kinds=None, raw=False):
    # prefer the stored login (no browser needed); fall back to the logged-in debug Chrome tab
    try:
        import auth
        token = auth.get_token()
    except Exception:  # noqa: BLE001
        token = None
    page = None if token else kirka_page()
    try:
        out = {}
        for kind in kinds or TYPES:
            r = _ask_http(token, kind) if token else _ask(page, kind)
            if 'error' in r:
                out[kind] = {'error': r['error'], 'status': r.get('status')}
            elif raw:
                out[kind] = r['body']
            else:
                out[kind] = [readable(q) for q in r['body']]
        return {'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'quests': out}
    finally:
        if page:
            page.close()


def show(data):
    for kind, qs in data['quests'].items():
        print(f'== {kind.upper()}')
        if isinstance(qs, dict):
            print('  ', qs.get('error'))
            continue
        if not qs:
            print('   no quests')
        for q in qs:
            what = q['text']
            rew = ', '.join((r['item']['name'] if r.get('item') else f"{r['amount']} {r['kind']}") for r in q['rewards'])
            print(f"   {what:36s} {q['rarity'] or '?':10s} ends {q['endsAt'][:16].replace('T', ' ')}  -> {rew}")


def capture():
    """quests from the game, saved to kirka-api/quests.json"""
    data = fetch()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    # the skin library's Quests page reads this copy when the local API isn't running (and it ships with the site)
    if not any(isinstance(v, dict) for v in data['quests'].values()):
        WEB.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data


def expired(data):
    """True once any saved quest has ended (the dailies reset, an event finished), or nothing is saved"""
    now = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
    qs = [q for v in (data or {}).get('quests', {}).values() if isinstance(v, list) for q in v]
    return not qs or any((q.get('endsAt') or '')[:19] <= now for q in qs)


def serve(port=5190):
    state = {'data': json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else None, 'tried': 0.0}

    def current():
        if expired(state['data']) and time.time() - state['tried'] > 60:       # at most one try a minute
            state['tried'] = time.time()
            try:
                d = capture()
                if not any(isinstance(v, dict) for v in d['quests'].values()):   # every type came back fine
                    state['data'] = d
            except (SystemExit, Exception):  # noqa: BLE001  game not open: keep the old capture
                pass
        d = dict(state['data'] or {'quests': {}})
        d['stale'] = expired(state['data'])
        return d

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0].rstrip('/')
            kind = path.split('/')[-1] if path.startswith('/quests/') else None
            if path != '/quests' and kind not in TYPES:
                return self._send(404, {'error': 'try /quests, /quests/hourly, /quests/daily or /quests/event'})
            d = current()
            if kind:
                d = {**d, 'quests': {kind: d['quests'].get(kind, [])}}
            self._send(200, d)

        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False, indent=2).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    print(f'quest API on http://127.0.0.1:{port}/quests  (Ctrl+C stops)')
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == 'serve':
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else 5190)
    else:
        data = capture()
        if arg == 'json':
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            show(data)
            print(f'\nsaved {OUT}')
