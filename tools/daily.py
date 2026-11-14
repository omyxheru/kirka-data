"""Daily Kirka job: refresh every data feed, archive the leaderboards, and write a dated report. Meant to run once a
day from Windows Task Scheduler (tools/install_daily_task.ps1), but you can run it by hand any time:

  python tools/daily.py

Each step is independent: if one source is down (or the debug Chrome isn't open for the login-only ones) it's noted
and the rest still run. The report lands in kirka/reports/<date>.md and kirka/reports/latest.md.
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
WEB = ROOT / 'skin-library' / 'public'
REPORTS = ROOT / 'reports'
PY = sys.executable
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROFILE = ROOT / '.browser-profile'


def chrome_token_ready():
    """is the debug Chrome up on port 9222 with a logged-in kirka.io tab?"""
    try:
        tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=3).read())
        return any('kirka.io' in t.get('url', '') for t in tabs if t.get('type') == 'page')
    except Exception:  # noqa: BLE001
        return False


def ensure_chrome():
    """launch the debug Chrome if it isn't running, so the login-only steps (quests, maps) work unattended.
    It restores its saved login from .browser-profile. Returns True if we started it (so we can close it after)."""
    if chrome_token_ready():
        return False
    if not pathlib.Path(CHROME).exists():
        print('  (debug Chrome not found; quests + maps will skip)')
        return False
    subprocess.Popen([CHROME, '--remote-debugging-port=9222', f'--user-data-dir={PROFILE}',
                      '--no-first-run', '--no-default-browser-check', '--start-minimized', 'https://kirka.io'],
                     creationflags=0x00000008)  # DETACHED_PROCESS
    for _ in range(40):            # wait up to ~40s for the lobby + login to restore
        time.sleep(2)
        if chrome_token_ready():
            time.sleep(6)          # let the token land in localStorage
            print('  (launched the debug Chrome for the login-only steps)')
            return True
    print('  (debug Chrome did not log in; quests + maps may skip)')
    return True


def run(name, script, tries=1):
    """run one refresher script, with retries; capture whether it worked"""
    for attempt in range(1, tries + 1):
        t = time.time()
        try:
            r = subprocess.run([PY, str(TOOLS / script)], capture_output=True, text=True, timeout=300)
            ok = r.returncode == 0 and 'FAILED' not in r.stdout and 'not logged in' not in (r.stdout + r.stderr)
            tail = (r.stdout.strip().splitlines() or [''])[-1][:80]
            if ok or attempt == tries:
                mark = 'ok' if ok else 'SKIP'
                print(f'  {name:10s} {mark}  {tail}  ({time.time()-t:.1f}s)' + (f' [try {attempt}]' if attempt > 1 else ''))
                return ok
        except Exception as e:  # noqa: BLE001
            if attempt == tries:
                print(f'  {name:10s} FAIL  {e}')
                return False
        time.sleep(5 * attempt)   # back off before retrying
    return False


def jload(name, default=None):
    f = WEB / name
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return default if default is not None else {}


def fmt(n):
    try:
        return f'{int(n):,}'
    except Exception:  # noqa: BLE001
        return str(n)


def report(status):
    today = time.strftime('%Y-%m-%d')
    L = [f'# Kirka daily report - {today}', '', f'_Generated {time.strftime("%H:%M")}. Sources refreshed: ' +
         ', '.join(k for k, v in status.items() if v) + ('. Skipped: ' + ', '.join(k for k, v in status.items() if not v) if any(not v for v in status.values()) else '') + '._', '']

    # players online
    online = jload('online.json', {}).get('points', [])
    if online:
        last = online[-1]
        total = lambda p: sum(p.get(r, 0) for r in ('eu', 'na', 'sa', 'asia', 'oce', 'india'))
        day = [p for p in online if str(p.get('timestamp', '')).startswith(today)]
        peak = max((total(p) for p in day), default=total(last))
        busiest = max(('eu', 'na', 'sa', 'asia', 'oce', 'india'), key=lambda r: last.get(r, 0))
        L += ['## Players online', f'- Now: **{total(last)}** in game. Peak today: **{peak}**.',
              f'- Busiest region: **{busiest.upper()}** ({last.get(busiest, 0)}).', '']

    # top players / clans (from our archive)
    hist = jload('lb-history.json', {})
    for board, label in [('solo', 'Top players today'), ('clan', 'Top clans today')]:
        days = hist.get(board, [])
        if days:
            top = days[-1]['top'][:5]
            L += [f'## {label}'] + [f'{t["rank"]}. **{t["name"]}** - {fmt(t["score"])}' for t in top] + ['']

    # quests
    q = jload('quests.json', {}).get('quests', {})
    if q:
        L += ['## Quests']
        for kind in ('hourly', 'daily', 'event'):
            items = q.get(kind) or []
            if isinstance(items, list) and items:
                L += [f'**{kind.title()}**'] + [f'- {x.get("text","?")} -> ' +
                      ', '.join((r.get('item') or {}).get('name') or f'{fmt(r.get("amount"))} {r.get("kind")}' for r in x.get('rewards', [])) for x in items]
        L += ['']

    # shop
    shop = jload('shop.json', {})
    if shop.get('sets') is not None:
        sets = ', '.join(f'{s["name"]} ({fmt(s.get("price"))})' for s in shop.get('sets', []))
        L += ['## Shop', f'- Sets: {sets or "none"}', f'- Bundles: {len(shop.get("bundles", []))}, character cards: {len((shop.get("characterCards") or {}).get("cards", []))}', '']

    # top community maps
    maps = jload('maps.json', {}).get('maps', [])
    if maps:
        L += ['## Top community maps'] + [f'{i+1}. **{m["name"]}** by {m.get("author","?")} - {fmt(m.get("plays"))} plays' for i, m in enumerate(maps[:5])] + ['']

    # news
    news = jload('news.json', {})
    if news.get('version'):
        coming = ', '.join(s.lstrip('- ') for s in (news.get('comingSoon') or []))
        L += ['## Game', f'- Version **{news["version"]}**.' + (f' Coming soon: {coming}.' if coming else ''), '']

    REPORTS.mkdir(exist_ok=True)
    text = '\n'.join(L)
    (REPORTS / f'{today}.md').write_text(text, encoding='utf-8')
    (REPORTS / 'latest.md').write_text(text, encoding='utf-8')
    return REPORTS / f'{today}.md'


def log_run(status):
    """append a line to the run log and record the last success, so there's a trail the job is running"""
    REPORTS.mkdir(exist_ok=True)
    line = time.strftime('%Y-%m-%d %H:%M') + '  ' + '  '.join(f'{k}={"ok" if v else "skip"}' for k, v in status.items())
    with (REPORTS / 'run-log.txt').open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    if status.get('archive'):
        (REPORTS / 'last-success.txt').write_text(time.strftime('%Y-%m-%d %H:%M:%S'), encoding='utf-8')


def find_gaps():
    """days with no leaderboard snapshot between the first record and today (data we can't recover)"""
    try:
        hist = json.loads((WEB / 'lb-history.json').read_text(encoding='utf-8'))
        dates = sorted({d['date'] for d in hist.get('solo', [])})
    except Exception:  # noqa: BLE001
        return []
    if not dates:
        return []
    import datetime
    start = datetime.date.fromisoformat(dates[0])
    today = datetime.date.today()
    have = set(dates)
    gaps, d = [], start
    while d < today:
        if d.isoformat() not in have:
            gaps.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return gaps


def main():
    cloud = '--cloud' in sys.argv      # cloud mode: public sources only, no browser (quests/maps need a login token)
    print('Kirka daily refresh', time.strftime('%Y-%m-%d %H:%M'), '(cloud)' if cloud else '')
    if not cloud and not (ROOT / 'kirka-api' / 'auth.json').exists():
        ensure_chrome()      # no stored login yet: fall back to opening the debug Chrome for quests + maps
    # archive the leaderboards FIRST and with the most retries: it's the irreplaceable daily data (top players /
    # clans) and needs no login, so it must never miss a day.
    status = {
        'archive': run('archive', 'lb_archive.py', tries=4),
        'creators': run('creators', '../skin-library/scripts/build_creators.py', tries=2),
        'feeds': run('feeds', 'feeds.py', tries=3),
        'shop': run('shop', 'shop.py', tries=3),
    }
    # quests + maps need a login. On a PC that's the stored token; in the cloud only if a KIRKA_REFRESH secret is set.
    import os
    if not cloud or os.environ.get('KIRKA_REFRESH'):
        status['quests'] = run('quests', 'quests.py', tries=2)
        status['maps'] = run('maps', 'maps.py', tries=2)
    # archive one compact snapshot of EVERYTHING for today (kept forever), so any past day can be looked back at
    status['snapshot'] = run('snapshot', 'snapshot.py', tries=2)
    path = report(status)
    print(f'report: {path}')
    log_run(status)
    gaps = find_gaps()
    if gaps:
        print(f'NOTE: no leaderboard snapshot on {len(gaps)} earlier day(s) (PC was off): {", ".join(gaps[-5:])}')


if __name__ == '__main__':
    main()
