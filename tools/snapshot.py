"""Write one compact snapshot of EVERYTHING for today, kept forever, so any past day can be looked back at. The
per-feed files in skin-library/public/ only hold the latest state (overwritten each run); this archives a dated
record. Thumbnails and the full 2 MB catalogue are left out - only the facts that are worth a time-series.

  python tools/snapshot.py

Writes reports/snapshots/<date>.json (one per day, latest run of the day wins) with: players online, top players +
clans, every quest, the shop, top community maps, catalogue counts + skins released today, the biggest value moves,
and the game version. Run by tools/daily.py after the feeds are refreshed.
"""
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / 'skin-library' / 'public'
KAPI = ROOT / 'kirka-api'
OUT = ROOT / 'reports' / 'snapshots'
TODAY = time.strftime('%Y-%m-%d')


def jload(p, default=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return default if default is not None else {}


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read())


def online_now():
    pts = jload(WEB / 'online.json', {}).get('points', [])
    if not pts:
        return {}
    reg = ('eu', 'na', 'sa', 'asia', 'oce', 'india')
    tot = lambda p: sum(p.get(r, 0) for r in reg)
    today = [p for p in pts if str(p.get('timestamp', '')).startswith(TODAY)]
    last = pts[-1]
    return {'perRegion': {r: last.get(r, 0) for r in reg}, 'total': tot(last),
            'peakToday': max((tot(p) for p in today), default=tot(last))}


def leaderboards():
    hist = jload(WEB / 'lb-history.json', {})
    out = {}
    for board in ('solo', 'clan'):
        days = hist.get(board, [])
        today = next((d for d in days if d.get('date') == TODAY), days[-1] if days else None)
        if today:
            out[board] = today['top']
    return out


def quests():
    q = jload(WEB / 'quests.json', {}).get('quests', {})
    out = {}
    for kind in ('hourly', 'daily', 'event'):
        items = q.get(kind)
        if isinstance(items, list):
            out[kind] = [{'text': x.get('text'), 'rarity': x.get('rarity'),
                          'rewards': [{'kind': r.get('kind'), 'amount': r.get('amount'),
                                       'item': (r.get('item') or {}).get('name')} for r in x.get('rewards', [])]}
                         for x in items]
    return out


def shop():
    s = jload(WEB / 'shop.json', {})
    if not s:
        return {}
    lite = lambda grp: [{'name': x.get('name'), 'price': x.get('price') or sum(i.get('price', 0) for i in x.get('items', [])),
                         'items': [i.get('name') for i in x.get('items', [])]} for x in s.get(grp, [])]
    cc = s.get('characterCards') or {}
    return {'sets': lite('sets'), 'bundles': lite('bundles'),
            'coins': [{'amount': c.get('amount'), 'price': c.get('price'), 'currency': c.get('currency')} for c in (s.get('currency') or {}).get('coins', [])],
            'gems': [{'amount': c.get('amount'), 'price': c.get('price'), 'currency': c.get('currency')} for c in (s.get('currency') or {}).get('diamonds', [])],
            'cards': [{'name': c.get('name'), 'price': c.get('price'), 'characters': len(c.get('characters') or [])} for c in cc.get('cards', [])]}


def maps_top():
    ms = jload(WEB / 'maps.json', {}).get('maps', [])
    return [{'name': m.get('name'), 'author': m.get('author'), 'plays': m.get('plays'),
             'likes': m.get('likes'), 'favorites': m.get('favorites')} for m in ms[:30]]


def catalogue():
    cat = jload(KAPI / 'catalog.json', [])
    if not cat:
        return {}
    import collections
    by_type = collections.Counter(i.get('type') for i in cat)
    by_rar = collections.Counter(i.get('rarity') for i in cat)
    new = [{'name': i.get('name'), 'type': i.get('type'), 'rarity': i.get('rarity'),
            'by': [c.get('name') for c in (i.get('creators') or [])]}
           for i in cat if str(i.get('createdAt', '')).startswith(TODAY)]
    return {'total': len(cat), 'byType': dict(by_type), 'byRarity': dict(by_rar), 'releasedToday': new}


def value_movers():
    try:
        ch = get('https://kirkahub.online/api/changelog')
        changed = ((ch.get('pending') or {}).get('changed')) or []
        rows = [e for e in changed if isinstance(e, dict) and isinstance(e.get('pct'), (int, float))]
        rows.sort(key=lambda e: e.get('pct', 0))
        pick = lambda e: {'name': e.get('name'), 'type': e.get('type'), 'from': e.get('fromRaw') or e.get('from'),
                          'to': e.get('toRaw') or e.get('to'), 'pct': e.get('pct')}
        return {'gainers': [pick(e) for e in rows[::-1][:10]], 'losers': [pick(e) for e in rows[:10]]}
    except Exception:  # noqa: BLE001
        return {}


def build():
    snap = {'date': TODAY, 'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'online': online_now(), 'leaderboards': leaderboards(), 'quests': quests(),
            'shop': shop(), 'topMaps': maps_top(), 'catalogue': catalogue(),
            'valueMovers': value_movers(), 'game': {k: jload(WEB / 'news.json', {}).get(k) for k in ('version', 'comingSoon')}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{TODAY}.json').write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
    # a small index of every day captured
    idx = sorted(p.stem for p in OUT.glob('*.json') if p.stem != 'index')
    (OUT / 'index.json').write_text(json.dumps({'days': idx}, ensure_ascii=False), encoding='utf-8')
    kb = (OUT / f'{TODAY}.json').stat().st_size // 1024
    newc = len(snap['catalogue'].get('releasedToday', []))
    print(f"snapshot {TODAY}.json ({kb} KB): {len(snap['leaderboards'].get('solo', []))} top players, "
          f"{sum(len(v) for v in snap['quests'].values())} quests, {len(snap['topMaps'])} maps, {newc} new items today. "
          f"{len(idx)} days archived.")


if __name__ == '__main__':
    build()
