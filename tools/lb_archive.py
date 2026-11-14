"""Archive Kirka's leaderboards so we build our OWN history (daily top players / top clans). Kirka's API only ever
returns TODAY's board with a countdown to the next reset; nobody public stores past days, so the only way to get
"old top player" data is to start snapshotting now. Run this daily (or on a schedule).

  python tools/lb_archive.py

Appends one dated snapshot per board per day to skin-library/public/lb-history.json:
  { "solo": [ { date, remainingTime, top: [{rank, name, score, userId}] } , ... ], "clan": [ ... ] }
Source: Kirka Hub (kirkahub.online, public, no login). Keeps the top 20 of each board.
"""
import json
import pathlib
import time
import urllib.request

WEB = pathlib.Path(__file__).resolve().parent.parent / 'skin-library' / 'public' / 'lb-history.json'
TOP = 20


def get(path):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        'https://kirkahub.online' + path, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read())


def snapshot(board, clan):
    d = get(f'/api/leaderboard/{board}')
    rows = d.get('results', [])[:TOP]
    top = [{'rank': i + 1,
            'name': r.get('name'),
            'score': r.get('scores'),
            **({'clanId': r.get('clanId'), 'members': r.get('membersCount')} if clan else {'userId': r.get('userId')})}
           for i, r in enumerate(rows)]
    return {'date': time.strftime('%Y-%m-%d'), 'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'remainingTime': d.get('remainingTime'), 'top': top}


def main():
    hist = json.loads(WEB.read_text(encoding='utf-8')) if WEB.exists() else {}
    for board, clan in [('solo', False), ('clan', True)]:
        snap = snapshot(board, clan)
        days = hist.setdefault(board, [])
        days[:] = [d for d in days if d.get('date') != snap['date']]   # one snapshot per day (latest wins)
        days.append(snap)
        days.sort(key=lambda d: d['date'])
        tops = ', '.join('{} ({})'.format(t['name'], t['score']) for t in snap['top'][:3])
        print('  {:5s} {}  top: {}'.format(board, snap['date'], tops))
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps(hist, ensure_ascii=False), encoding='utf-8')
    print(f'lb-history.json: solo {len(hist.get("solo", []))} days, clan {len(hist.get("clan", []))} days')


if __name__ == '__main__':
    main()
