"""Demo: pull all of Kirka's shop and the full item catalogue, readable, no login.

  python tools/shop.py            print a summary, save kirka-api/shop.json + kirka-api/catalog.json
  python tools/shop.py json       print the full JSON instead

Sources (all public, read-only, no ApiKey):
  - Catalogue: Kirka Hub proxy of the official api.kirka.io  (clean fields, creators, renders)
      POST https://kirkahub.online/api/inventory/items  ->  every item: type, rarity, creators, totalOwned, renderUrl
  - Shop:      Kirka's internal api2.kirka.io shop routes (field names obfuscated; decoded below from the live data,
               game 0.44.x, 2026-11-14; re-check after a Kirka update)
      GET /api/WwMWnwNm/WwMWnwN   sets
      GET /api/WwMWnwNm/wnMNmWwW  bundles
      GET /api/WwMWnwNm/wmMwW     currency (coins packs + diamond packs)
      GET /api/WwMWnwNm/wwnmWNMW  character cards

api2 sends no CORS header, so a website calls it through a small proxy (Kirka Hub does the same). The catalogue route
on Kirka Hub already allows any origin.
"""
import json
import pathlib
import sys
import urllib.request
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'kirka-api'
WEB = ROOT / 'skin-library' / 'public' / 'shop.json'
IMG = 'https://kirka.io/img/'
CUR = {'wwMNWmWn': 'coins', 'wMNmW': 'diamonds', 'USD': 'USD'}
API2 = 'https://api2.kirka.io'
HUB = 'https://kirkahub.online'

# obfuscated -> readable, confirmed by matching ids against the official catalogue
ITEM = {'WnWwwNmM': 'id', 'WwMWmwn': 'type', 'wNmMnW': 'rarity', 'WwMWmn': 'name', 'wmnWMwN': 'marketPrice', 'wNmWnwM': 'parent'}
SET = {'WnWwwNmM': 'id', 'WwMWmn': 'name', 'wwMNmnWW': 'slug', 'wmWnMwWN': 'layout', 'wmMwWnWN': 'bg', 'wNwWmnW': 'fg',
       'wMNmWWnw': 'price', 'wmwNnWMW': 'startsAt', 'wNwWmnMW': 'endsAt', 'wMNwWWn': 'active', 'wwnmMW': 'tag', 'wwnmWNMW': 'items'}
BUNDLE = {'WnWwwNmM': 'id', 'WwMWmn': 'name', 'wmwNnWMW': 'startsAt', 'wNwWmnMW': 'endsAt', 'wmnWNMwW': 'items'}
PACK = {'WnWwwNmM': 'id', 'WwMWmn': 'amount', 'wwMNnWm': 'price', 'wWmwN': 'wasPrice', 'wMWwnNW': 'currency',
        'wMNnW': 'value', 'wMwW': 'image', 'wwnmMW': 'tag', 'WnwmwNM': 'order'}
CARD = {**PACK, 'wmMwWnWN': 'color', 'wNwWmnWM': 'color2', 'wnWmMNw': 'render', 'wNnWmMwW': 'bg'}


def get(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method='POST' if body is not None else 'GET', data=data,
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def pick(d, m):
    return {m[k]: v for k, v in d.items() if k in m}


def pack(d):
    """a currency / card pack -> readable, with a resolved currency name and image url"""
    o = pick(d, PACK)
    if 'currency' in o:
        o['currency'] = CUR.get(o['currency'], o['currency'])
    # the pack icon filename (e.g. __coin_1__.webp) is a hashed asset in Kirka's bundle, not reachable by name;
    # keep the raw name, leave image null so the page shows a clean coin/gem icon instead
    o['iconName'] = o.pop('image', None)
    o['image'] = None
    return o


def item(wrapper):
    """a shop item wrapper {item, quantity, [coin price]} -> readable, keeping just the parent gun's name"""
    inner = wrapper.get('WwMWnmN', wrapper)
    o = pick(inner, ITEM)
    if isinstance(o.get('parent'), dict):
        o['parent'] = o['parent'].get('WwMWmn')
    o['qty'] = wrapper.get('wNmMn', 1)
    if 'wwMNnWm' in wrapper:                 # a bundle item carries its own coin price
        o['price'] = wrapper['wwMNnWm']
    return o


def fetch_shop():
    sets = [{**pick(s, SET), 'items': [item(w) for w in s.get('wwnmWNMW', [])]} for s in get(f'{API2}/api/WwMWnwNm/WwMWnwN')]
    bundles = [{**pick(b, BUNDLE), 'items': [item(w) for w in b.get('wmnWNMwW', [])]} for b in get(f'{API2}/api/WwMWnwNm/wnMNmWwW')]
    cur = get(f'{API2}/api/WwMWnwNm/wmMwW')
    currency = {'coins': [pack(c) for c in cur.get('wwMnN', [])],
                'diamonds': [pack(c) for c in cur.get('wMNmWWnw', [])]}
    cc = get(f'{API2}/api/WwMWnwNm/wwnmWNMW')
    # a character card is a pack: `wMWwnWmN` lists the characters in it (name + rarity). Keep those names so the
    # page can show every character (joined to the catalogue for renders in main()).
    def card(c):
        o = pack(c)
        o['characters'] = [x.get('WwMWmn') for x in (c.get('wMWwnWmN') or [])]
        return o
    cards = {'cards': [card(c) for c in cc.get('wwnmWNM', [])],
             'chests': [pack(c) for c in cc.get('wNnWwWm', [])]}
    return {'sets': sets, 'bundles': bundles, 'currency': currency, 'characterCards': cards}


def fetch_catalog():
    return get(f'{HUB}/api/inventory/items')


def main(as_json):
    OUT.mkdir(exist_ok=True)
    shop = fetch_shop()
    catalog = fetch_catalog()
    # join every shop skin to the catalogue by id, for a clean name / type / rarity / render picture
    cat_by = {i['id']: i for i in catalog}
    for group in (shop['sets'], shop['bundles']):
        for s in group:
            for it in s['items']:
                c = cat_by.get(it.get('id'))
                if c:
                    it['name'], it['type'], it['rarity'] = c['name'], c['type'], c['rarity']
                    it['render'] = c.get('renderUrl')
                    it['parent'] = (c.get('parent') or {}).get('name')
    cat_name = {}
    for i in catalog:
        if 'CHARACTER' in i['type'] or i['type'] == 'BODY_SKIN':
            cat_name.setdefault(i['name'], i)                # first wins (character skin)
    for c in shop['characterCards']['cards'] + shop['characterCards']['chests']:
        c['name'] = c.pop('amount', c.get('name'))          # for cards this field is the name, not a quantity
        c.pop('value', None)
        # expand each card's characters to {name, rarity, render} from the catalogue
        chars = []
        for nm in c.pop('characters', []) or []:
            m = cat_name.get(nm)
            chars.append({'name': nm, 'rarity': m['rarity'] if m else None, 'render': m.get('renderUrl') if m else None})
        if chars:
            c['characters'] = chars
    shop['capturedAt'] = __import__('time').strftime('%Y-%m-%dT%H:%M:%S')
    (OUT / 'shop.json').write_text(json.dumps(shop, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps(shop, ensure_ascii=False), encoding='utf-8')          # the site's Shop page reads this
    if as_json:
        print(json.dumps({'shop': shop, 'catalogCount': len(catalog)}, ensure_ascii=False, indent=2))
        return
    print('SHOP')
    for s in shop['sets']:
        print(f"  Set  {s['name']:18s} {s.get('price','?'):>6} coins  {len(s['items'])} items  tag={s.get('tag') or '-'}  ends {str(s.get('endsAt'))[:10]}")
    for b in shop['bundles']:
        total = sum(i.get('price', 0) for i in b['items'])
        print(f"  Bndl {b['name']:18s} {len(b['items'])} items  {total} coins  ends {str(b.get('endsAt'))[:10]}")
    print(f"  Coin packs: {len(shop['currency']['coins'])}  ({', '.join(c['amount'] for c in shop['currency']['coins'])})")
    print(f"  Diamond packs: {len(shop['currency']['diamonds'])}  ({', '.join(str(c['amount']) + ' for $' + str(c['price']) for c in shop['currency']['diamonds'])})")
    print(f"  Character cards: {len(shop['characterCards']['cards'])}   chests: {len(shop['characterCards']['chests'])}")

    import collections
    by_type = collections.Counter(i['type'] for i in catalog)
    by_rar = collections.Counter(i['rarity'] for i in catalog)
    creators = collections.Counter(c['name'] for i in catalog for c in (i.get('creators') or []))
    print(f"\nCATALOGUE  {len(catalog)} items")
    print('  by type:  ', dict(by_type))
    print('  by rarity:', dict(by_rar))
    print('  top creators:', ', '.join(f'{n} ({c})' for n, c in creators.most_common(6)))
    print(f"\nsaved {OUT / 'shop.json'} and {OUT / 'catalog.json'}")


if __name__ == '__main__':
    try:
        main(len(sys.argv) > 1 and sys.argv[1] == 'json')
    except urllib.error.HTTPError as e:
        print(f'HTTP {e.code}: {e.read()[:200]}')
