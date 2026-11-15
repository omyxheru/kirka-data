"""Capture the trader data the website's Trader viewer reads: top traders with their full trade log, profit, partners,
and account (level, clan, join date, inventory net worth). Public sources only (Luke's trade archive + Kirka Hub),
no login. Writes skin-library/public/traders.json.

  python tools/traders.py [days] [topN]      default 60 days, top 60 traders

Profit is in community value-list terms (a trade's offerer receives the 'wanted' side, gives 'offered'). Net worth
prices the player's inventory off the Hub value list. Values are estimates.
"""
import collections
import json
import pathlib
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import statsdb as sdb  # noqa: E402

HIST = 'https://kirka.lukeskywalk.com/tradehistory/'
HUB = 'https://kirkahub.online'
WEB = pathlib.Path(__file__).resolve().parent.parent / 'skin-library' / 'public' / 'traders.json'
LOG_CAP = 60        # trades kept in each trader's visible log
SLEEP = 0.15


def get(url, body=None, tries=3):
    for a in range(tries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, method='POST' if body is not None else 'GET',
                                         headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            if a == tries - 1:
                return None
            time.sleep(1.2 * (a + 1))
    return None


def items(side):
    return [{'name': i.get('name'), 'rarity': i.get('rarity'), 'qty': i.get('quantity'), 'value': i.get('value')}
            for i in (side.get('items') or [])]


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    topn = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    force = '--force' in sys.argv
    con = sdb.connect()
    date = sdb.today()
    if not force and sdb.meta_get(con, 'last_traders_date') == date:
        print(f'traders {date}: already captured today (use --force to redo)')
        con.close()
        return
    files = get(HIST + 'snapshots.json')
    files = files[-days:] if files else []
    agg = {}   # tag -> dict
    seen = set()

    def tr(tag):
        return agg.setdefault(tag, {'tag': tag, 'trades': 0, 'volume': 0, 'profit': 0, 'best': None, 'worst': None,
                                    'partners': collections.Counter(), 'log': []})

    for f in files:
        rows = get(HIST + f)
        if not isinstance(rows, list):
            continue
        for t in rows:
            tid = t.get('tradeId')
            if tid in seen:
                continue
            seen.add(tid)
            trd = t.get('trade') or {}
            off, wnt = (trd.get('offered') or {}), (trd.get('wanted') or {})
            ot, wt = off.get('total', 0) or 0, wnt.get('total', 0) or 0
            when = (t.get('updatedAt') or '')[:19]
            o, a = t.get('offerer'), t.get('accepter')
            for tag, partner, gave, got, gtot, rtot in (
                    (o, a, items(off), items(wnt), ot, wt),
                    (a, o, items(wnt), items(off), wt, ot)):
                if not tag:
                    continue
                d = tr(tag)
                profit = rtot - gtot
                d['trades'] += 1; d['volume'] += gtot + rtot; d['profit'] += profit
                entry = {'date': when, 'partner': partner, 'profit': profit, 'gaveTotal': gtot, 'gotTotal': rtot,
                         'gave': gave, 'got': got}
                d['log'].append(entry)
                if partner:
                    d['partners'][partner] += 1
                if d['best'] is None or profit > d['best']['profit']:
                    d['best'] = entry
                if d['worst'] is None or profit < d['worst']['profit']:
                    d['worst'] = entry

    top = sorted(agg.values(), key=lambda x: x['volume'], reverse=True)[:topn]

    # enrich the top traders with their account + inventory net worth
    prices = {p['Skin Name']: p for p in (get(HUB + '/data/hub_prices.json') or [])}

    def price(name):
        p = prices.get(name) or {}
        v = p.get('Hub Value') or p.get('Base Value') or '0'
        try:
            return int(str(v).replace(',', ''))
        except Exception:  # noqa: BLE001
            return 0

    for d in top:
        short = d['tag'].rsplit('#', 1)[-1] if '#' in d['tag'] else None
        d['name'] = d['tag'].rsplit('#', 1)[0]
        d['shortId'] = short
        d['topPartners'] = [[k, v] for k, v in d['partners'].most_common(5)]
        del d['partners']
        d['log'] = sorted(d['log'], key=lambda e: e['date'], reverse=True)[:LOG_CAP]
        if short:
            pr = get(HUB + '/api/user/getProfile', {'id': short, 'isShortId': True})
            time.sleep(SLEEP)
            if isinstance(pr, dict) and pr.get('id'):
                d['account'] = {'id': pr['id'], 'name': pr.get('name'), 'level': pr.get('level'),
                                'clan': pr.get('clan'), 'joined': (pr.get('createdAt') or '')[:10]}
                inv = get(HUB + '/api/inventory/user', {'id': short, 'isShortId': True})
                time.sleep(SLEEP)
                if isinstance(inv, list):
                    d['netWorth'] = sum(price((i.get('item') or {}).get('name')) * (i.get('amount') or 1) for i in inv)
                    d['items'] = len(inv)

    out = {'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%S'), 'windowDays': len(files),
           'totalTrades': len(seen), 'totalTraders': len(agg), 'traders': top}
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    # archive a daily row per top trader into the stats DB, so net-worth / profit over time can be charted later
    for d in top:
        acc = d.get('account') or {}
        sdb.trader_daily(con, date, d['tag'], d.get('shortId'), d.get('name'),
                         d['trades'], d['volume'], d['profit'], d.get('netWorth'), d.get('items'),
                         acc.get('level'), acc.get('clan'))
    sdb.meta_set(con, 'last_traders_date', date)
    con.commit()
    try:
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')   # fold WAL into the .db (non-fatal if a reader holds it)
    except Exception:  # noqa: BLE001
        pass
    con.close()
    kb = WEB.stat().st_size // 1024
    print(f'traders.json: top {len(top)} of {len(agg)} traders, {len(seen)} trades over {len(files)} days ({kb} KB); '
          f'{len(top)} archived to kirka.db for {date}')
    for i, d in enumerate(top[:10], 1):
        acc = d.get('account') or {}
        print(f"  {i:2} {d['tag'][:22]:22} {d['trades']:>4} trades  net {d['profit']/1e6:+.0f}M  "
              f"worth {(d.get('netWorth') or 0)/1e6:.0f}M  lvl {acc.get('level','?')} clan {acc.get('clan') or '-'}")


if __name__ == '__main__':
    main()
