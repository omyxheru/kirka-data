"""Load the live-room history (reports/live/<date>.ndjson, written by `liveall.py --cloud`) into kirka.db match_roster.

Idempotent (PRIMARY KEY captured_at+room+name, INSERT OR REPLACE), so it can re-read the recent days every run.
  python tools/live_import.py            # last 3 days
  python tools/live_import.py --all      # every file
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import statsdb
from specd import MATCH_ROSTER

HIST = pathlib.Path(__file__).resolve().parent.parent / 'reports' / 'live'


def main():
    files = sorted(HIST.glob('*.ndjson'))
    if '--all' not in sys.argv:
        files = files[-3:]
    con = statsdb.connect(); con.executescript(MATCH_ROSTER)
    rows = snaps = 0
    for f in files:
        for ln in f.read_text(encoding='utf-8').splitlines():
            try:
                s = json.loads(ln)
            except ValueError:
                continue   # a half-written last line
            snaps += 1
            cols = s['cols']; region = s['room'].split('~')[0].lower()
            for rank, vals in enumerate(s['p'], 1):
                p = dict(zip(cols, vals))
                con.execute("""INSERT OR REPLACE INTO match_roster
                    (captured_at,room,region,mode,map,short_id,name,rank,kills,deaths,score,side,is_bot)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (s['t'], s['room'], region, s.get('mode'), s.get('map'), p['shortId'], p['name'], rank,
                     p['kills'], p['deaths'], p['score'], p['team'] or 'all', p['bot']))
                rows += 1
    con.commit()
    total = con.execute('SELECT COUNT(*), COUNT(DISTINCT room), COUNT(DISTINCT short_id) FROM match_roster').fetchone()
    con.close()
    print(f'live_import: {snaps} room snapshots / {rows} rows from {len(files)} file(s); '
          f'match_roster now {total[0]} rows, {total[1]} rooms, {total[2]} players')


if __name__ == '__main__':
    main()
