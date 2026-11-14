"""Who made every skin. Pulls the official item catalogue (Kirka Hub proxy of api.kirka.io) and writes
public/data/creators.json: { "<skin name>": { "by": ["Creator", ...], "ids": ["SHORTID", ...], "owners": n } }
keyed by skin name, matched to the Library's character skins and the weapon skins. No login.

  python scripts/build_creators.py
"""
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'public' / 'data'
HUB = 'https://kirkahub.online/api/inventory/items'


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read())


def main():
    catalog = get(HUB)
    # name -> creators, for the item types the site shows (characters = body skins, weapon skins)
    out = {}
    for i in catalog:
        if i['type'] not in ('BODY_SKIN', 'WEAPON_SKIN'):
            continue
        creators = i.get('creators') or []
        name = i['name']
        rec = out.get(name)
        # if a name repeats, keep the one that actually has creators / more owners
        if rec and not creators and rec.get('by'):
            continue
        out[name] = {
            'by': [c['name'] for c in creators],
            'ids': [c.get('shortId') for c in creators if c.get('shortId')],
            'owners': i.get('totalOwned'),
        }

    # how many of the site's own skins we could attribute
    def covered(path, key='n'):
        try:
            data = json.loads((DATA / path).read_text(encoding='utf-8'))
        except FileNotFoundError:
            return (0, 0)
        items = data if isinstance(data, list) else [x for v in data.values() for x in v]
        hit = sum(1 for s in items if out.get(s[key], {}).get('by'))
        return (hit, len(items))

    (DATA / 'creators.json').write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    ch, ct = covered('skins.json')
    wh, wt = covered('weapon-skins.json')
    print(f'creators.json: {len(out)} named skins')
    print(f'  character skins attributed: {ch}/{ct}')
    print(f'  weapon skins attributed:    {wh}/{wt}')
    # the most prolific creators, for a credits view
    import collections
    tally = collections.Counter()
    for i in catalog:
        for c in (i.get('creators') or []):
            tally[c['name']] += 1
    print('  top creators:', ', '.join(f'{n} ({c})' for n, c in tally.most_common(8)))


if __name__ == '__main__':
    main()
