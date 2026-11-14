"""Capture the Kirka data feeds that have no browser CORS into the site's public/ folder, so the Players Online,
News and Votes pages can read them. Run it to refresh (or on a schedule). No login.

  python tools/feeds.py

Writes into skin-library/public/:
  online.json  players online per region, last 7 days   (Kirka Hub /trade-api/playerCount.json)
  news.json    current version, announcement, coming soon, patch notes   (api2.kirka.io news route)
  votes.json   community skin votes per weapon          (Luke / kirka.lukeskywalk.com)

Browser-direct feeds (CORS open) are NOT captured here; pages fetch them live: value movers
(kirkahub.online/data/price-changelog.json) and live game counts (<region>.kirka.io/matchmake/).
"""
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / 'skin-library' / 'public'
NEWS = ['version', 'message', 'specialMessage', 'comingSoon', 'patchNotes']


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=40).read())


def online():
    rows = get('https://kirkahub.online/trade-api/playerCount.json')
    # keep ~7 days, thin to at most ~700 points
    return {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'points': rows}


def news():
    d = get('https://api2.kirka.io/api/WnwmNw/WwnNmwW')
    out = {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S')}
    for k in NEWS:
        if k in d:
            v = d[k]
            if k == 'specialMessage' and isinstance(v, str):
                try: v = json.loads(v)
                except Exception: pass
            out[k] = v
    return out


def votes():
    v = get('https://kirka.lukeskywalk.com/skinVotes.json')
    # enrich each voted skin with its real render + rarity from the catalogue (the plain /skin-render/<name>
    # endpoint 404s for most weapon skins; the catalogue carries the exact versioned renderUrl)
    try:
        cat = get('https://kirkahub.online/api/inventory/items')
    except Exception:  # noqa: BLE001
        cat = []
    # index by (weapon name, skin name); weapon skins hang off a parent gun, characters are body skins
    ws, body = {}, {}
    for i in cat:
        if i['type'] == 'WEAPON_SKIN' and i.get('parent'):
            ws[(i['parent']['name'], i['name'])] = i
        elif i['type'] == 'BODY_SKIN':
            body.setdefault(i['name'], i)
    # the vote keys use short gun names; the catalogue uses full ones
    GUN = {'AR-9': 'AR-9', 'MAC-10': 'MAC-10'}  # most match directly; parent names already match otherwise
    weapons = {}
    for wname, skins in v.items():
        full = GUN.get(wname, wname)
        rows = []
        for name, count in sorted(skins.items(), key=lambda x: -x[1]):
            m = body.get(name) if wname == 'Character' else (ws.get((full, name)) or body.get(name))
            rows.append({'name': name, 'votes': count,
                         'render': (m or {}).get('renderUrl'), 'rarity': (m or {}).get('rarity')})
        weapons[wname] = rows
    return {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'weapons': weapons}


def videos():
    # featured community videos (YouTube) - public, no login
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(
        'https://api2.kirka.io/api/wNwWmMn', data=b'{}',
        headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}, method='POST'), timeout=40).read())
    F = {'wnMwWWNm': 'youtubeId', 'wmnWMwW': 'title', 'wMWwmW': 'description'}
    vids = [{F[k]: v for k, v in x.items() if k in F} for x in raw]
    return {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'videos': vids}


def effects():
    # the skin-crafting effect catalogue (Glow, Pulse, Holographic...) with rarity - public, no login
    raw = get('https://api2.kirka.io/api/wMNn/wnMN')
    fx = [{'name': e.get('displayName') or e.get('name'), 'description': e.get('description'),
           'rarity': e.get('rarity'), 'animated': e.get('isAnimated')} for e in raw]
    return {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'effects': fx}


def main():
    WEB.mkdir(parents=True, exist_ok=True)
    for name, fn in [('online', online), ('news', news), ('votes', votes), ('videos', videos), ('effects', effects)]:
        try:
            data = fn()
            (WEB / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            n = len(data.get('points') or data.get('weapons') or data.get('videos') or data.get('effects') or data.keys())
            print(f'  {name}.json  ok  ({n} entries)')
        except Exception as e:  # noqa: BLE001
            print(f'  {name}.json  FAILED  {type(e).__name__}: {e}')


if __name__ == '__main__':
    main()
