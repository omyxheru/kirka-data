"""Capture Kirka's community maps (the in-game User Maps browser) to the site's public/maps.json. Same list for
every player, but Kirka gates the browse route behind any login, so this reads it through the logged-in debug Chrome
tab (tools/open-kirka.ps1), like tools/quests.py. The token never leaves the browser.

  python tools/maps.py

Writes skin-library/public/maps.json: [{ id, name, description, author, authorTag, likes, plays, favorites,
created, thumb }]. The field names are obfuscated (game 0.44.x, decoded 2026-11-14); re-check after a Kirka update.
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import kirka_page  # noqa: E402

WEB = pathlib.Path(__file__).resolve().parent.parent / 'skin-library' / 'public' / 'maps.json'

# obfuscated -> readable (matched to the live data)
F = {'WnWwwNmM': 'id', 'WwMWmn': 'name', 'wmWMnNw': 'description', 'wWwWnm': 'likes', 'wwMNWmnW': 'plays',
     'wMWwmnW': 'favorites', 'wmwNnWMW': 'created', 'wmWMwW': 'author', 'wnMmwWN': 'authorTag', 'wwMn': 'thumb'}


def _fetch_http(token):
    import urllib.request
    import urllib.error
    req = urllib.request.Request('https://api2.kirka.io/api/user-WwMWmw/wNnmM',
                                 headers={'authorization': 'Bearer ' + token, 'csrf': 'token', 'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return {'list': json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {'error': 'status ' + str(e.code)}


def main():
    # prefer the stored login (no browser); fall back to the logged-in debug Chrome tab
    try:
        import auth
        token = auth.get_token()
    except Exception:  # noqa: BLE001
        token = None
    if token:
        res = _fetch_http(token)
    else:
        page = kirka_page()
        try:
            res = page.evaluate("""(async () => {
              const t = localStorage.getItem('token')
              if (!t) return { error: 'not logged in: log in to Kirka in the debug Chrome window first' }
              const r = await fetch('https://api2.kirka.io/api/user-WwMWmw/wNnmM',
                { headers: { authorization: 'Bearer ' + t, csrf: 'token', accept: 'application/json' } })
              if (!r.ok) return { error: 'status ' + r.status }
              return { list: await r.json() }
            })()""")
        finally:
            page.close()
    if 'error' in res:
        print('failed:', res['error'])
        return
    maps = [{F[k]: v for k, v in m.items() if k in F} for m in res['list']]
    maps.sort(key=lambda m: m.get('plays', 0), reverse=True)
    out = {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'maps': maps}
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    kb = WEB.stat().st_size // 1024
    print(f'maps.json: {len(maps)} community maps ({kb} KB)')
    for m in maps[:8]:
        print(f"  {m['name'][:30]:30s} by {m.get('author','?'):14s} {m.get('plays',0):>6} plays  {m.get('likes',0)} likes")


if __name__ == '__main__':
    main()
