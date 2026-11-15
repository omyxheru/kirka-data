"""Collect everything into the stats database (statsdb). Run daily (tools/daily.py runs it). Public sources only
(Kirka Hub), so it needs no login and works in the cloud.

Each run:
  1. Leaderboards (solo + clan) -> store the day's board, register the players/clans on them.
  2. Every tracked clan -> fetch its members: store clan state + each member's clan context (role, contribution,
     join date), register the members as players.
  3. A budget of player profiles (leaderboard players first, then whoever was snapshotted longest ago) -> store
     their lifetime totals for today (deltas give daily/weekly/monthly), and discover their clan.
  4. Online counts per region.
  5. Derive membership events: who joined / left a clan or changed role since their last record.

Registries (players, clans) grow over time, so coverage widens every day. Be polite: throttled, retried, budgeted.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import statsdb as db  # noqa: E402

HUB = 'https://kirkahub.online'
PROFILE_BUDGET = 250        # profiles fetched per run (round-robins over days to cover the whole registry)
CLAN_BUDGET = 120           # clans fetched per run
SLEEP = 0.15                # polite pause between calls


def get(path, body=None, tries=3):
    for a in range(tries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(HUB + path, data=data, method='POST' if body is not None else 'GET',
                                         headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            if a == tries - 1:
                return None
            time.sleep(1.5 * (a + 1))
    return None


def num(v):
    try:
        return int(v)
    except Exception:  # noqa: BLE001
        return None


def collect_leaderboards(con, date):
    solo = get('/api/leaderboard/solo')
    if solo and solo.get('results'):
        for i, r in enumerate(solo['results']):
            db.see_player(con, r['userId'], name=r.get('name'))
            db.leaderboard_row(con, date, 'solo', i + 1, r['userId'], r.get('name'), num(r.get('scores')))
    clan = get('/api/leaderboard/clan')
    seen_clans = []
    if clan and clan.get('results'):
        for i, r in enumerate(clan['results']):
            db.see_clan(con, r['clanId'], name=r.get('name'))
            db.leaderboard_row(con, date, 'clan', i + 1, r['clanId'], r.get('name'), num(r.get('scores')), num(r.get('membersCount')))
            seen_clans.append(r.get('name'))
    for board in ('ranked1V1', 'ranked2V2', 'rankedSAD'):
        rk = get('/api/leaderboard/' + board)
        if rk and rk.get('results'):
            for i, r in enumerate(rk['results']):
                db.leaderboard_row(con, date, board, i + 1, r.get('userId'), r.get('name'), num(r.get('scores') or r.get('rating')))
    return len(solo['results']) if solo and solo.get('results') else 0, seen_clans


def clan_list(con, extra_names):
    """every clan name to fetch: the ones on the leaderboard + any discovered from players, least-recently-seen first"""
    names = {n for n in extra_names if n}
    for row in con.execute('SELECT name FROM clans WHERE name IS NOT NULL ORDER BY last_seen ASC').fetchall():
        names.add(row['name'])
    return list(names)[:CLAN_BUDGET]


def collect_clans(con, date, names):
    members_seen = 0
    for name in names:
        c = get('/api/clan/' + urllib.parse.quote(str(name)))
        time.sleep(SLEEP)
        if not isinstance(c, dict) or 'members' not in c:
            continue
        cid = c.get('id') or name
        db.see_clan(con, cid, name=c.get('name'), created=c.get('createdAt'), discord=c.get('discordLink'))
        mems = c.get('members') or []
        db.clan_snapshot(con, cid, date, c.get('name'), num(c.get('allScores')), num(c.get('monthScores')),
                         num(c.get('currentClanWarPosition')), len(mems))
        for m in mems:
            u = m.get('user') or {}
            if not u.get('id'):
                continue
            db.see_player(con, u['id'], short_id=u.get('shortId'), name=u.get('name'), level=u.get('level'))
            db.membership(con, u['id'], cid, date, m.get('role'), num(m.get('allScores')), num(m.get('monthScores')), m.get('createdAt'))
            members_seen += 1
    return members_seen


def profile_queue(con, date):
    """players needing a profile snapshot today: leaderboard players first, then longest-since-snapshot"""
    done = {r['player_id'] for r in con.execute('SELECT player_id FROM player_daily WHERE date=?', (date,)).fetchall()}
    order = []
    # leaderboard players today (most important)
    for r in con.execute('SELECT ref_id FROM leaderboard WHERE date=? AND board="solo" ORDER BY rank', (date,)).fetchall():
        if r['ref_id'] and r['ref_id'] not in done:
            order.append(r['ref_id'])
    # then everyone else, least-recently-snapshotted first
    for r in con.execute("""SELECT p.id FROM players p
        LEFT JOIN (SELECT player_id, MAX(date) md FROM player_daily GROUP BY player_id) d ON d.player_id=p.id
        ORDER BY COALESCE(d.md,'') ASC""").fetchall():
        if r['id'] not in done and r['id'] not in order:
            order.append(r['id'])
    return order[:PROFILE_BUDGET]


def collect_profiles(con, date, ids):
    n = 0
    for pid in ids:
        pr = get('/api/user/getProfile', {'id': pid, 'isShortId': False})
        time.sleep(SLEEP)
        if not isinstance(pr, dict) or not pr.get('id'):
            continue
        s = pr.get('stats') or {}
        db.see_player(con, pr['id'], short_id=pr.get('shortId'), name=pr.get('name'),
                      account_created=pr.get('createdAt'), level=pr.get('level'), total_xp=pr.get('totalXp'))
        db.player_snapshot(con, pr['id'], date, {
            'score': s.get('scores'), 'kills': s.get('kills'), 'deaths': s.get('deaths'), 'wins': s.get('wins'),
            'games': s.get('games'), 'headshots': s.get('headshots'), 'level': pr.get('level'), 'total_xp': pr.get('totalXp'),
            'klo': pr.get('klo'), 'klo_ranked': pr.get('kloRanked'), 'klo_sad': pr.get('kloSAD'),
            'klo_1v1': pr.get('klo1V1'), 'klo_2v2': pr.get('kloPOINT2V2'),
            'coins': pr.get('coins'), 'diamonds': pr.get('diamonds'), 'clan': pr.get('clan')})
        if pr.get('clan'):                       # discover the player's clan so it gets tracked next run
            con.execute('INSERT OR IGNORE INTO clans (id,name,first_seen,last_seen) VALUES (?,?,?,?)',
                        ('name:' + pr['clan'], pr['clan'], db.now(), db.now()))
        n += 1
    return n


def derive_membership_events(con, date):
    """compare each player's clan on `date` with their previous record -> join / leave / switch / role change"""
    rows = con.execute('SELECT player_id, clan_id, role FROM memberships WHERE date=?', (date,)).fetchall()
    today_clan = {r['player_id']: (r['clan_id'], r['role']) for r in rows}
    made = 0
    for pid, (cid, role) in today_clan.items():
        prev = con.execute('SELECT clan_id, role, date FROM memberships WHERE player_id=? AND date<? ORDER BY date DESC LIMIT 1',
                           (pid, date)).fetchone()
        name = (con.execute('SELECT name FROM players WHERE id=?', (pid,)).fetchone() or {'name': None})['name']
        cname = (con.execute('SELECT name FROM clans WHERE id=?', (cid,)).fetchone() or {'name': None})['name']
        if prev is None:
            db.event(con, date, pid, name, 'join_clan', cid, cname, 'first seen in clan')
            made += 1
        elif prev['clan_id'] != cid:
            pcn = (con.execute('SELECT name FROM clans WHERE id=?', (prev['clan_id'],)).fetchone() or {'name': None})['name']
            db.event(con, date, pid, name, 'leave_clan', prev['clan_id'], pcn, f'left for {cname}')
            db.event(con, date, pid, name, 'join_clan', cid, cname, f'from {pcn}')
            made += 2
        elif prev['role'] != role:
            db.event(con, date, pid, name, 'role_change', cid, cname, f"{prev['role']} -> {role}")
            made += 1
    # players who were in a clan before but are in none today (left, no new clan) -> detect via profiles later;
    # membership-list absence is handled next run when they reappear or via profile clan=null.
    return made


def collect_online(con):
    pts = get('/trade-api/playerCount.json')
    if isinstance(pts, list):
        for p in pts[-50:]:
            if p.get('timestamp'):
                db.online_point(con, p['timestamp'], p)


def main():
    con = db.connect()
    date = db.today()
    force = '--force' in sys.argv
    if not force and db.meta_get(con, 'last_collect_date') == date:
        print(f'collect {date}: already collected today (use --force to redo)')
        con.close()
        return
    t0 = time.time()
    nsolo, lb_clans = collect_leaderboards(con)  if False else collect_leaderboards(con, date)
    con.commit()
    names = clan_list(con, lb_clans)
    nmem = collect_clans(con, date, names)
    con.commit()
    ids = profile_queue(con, date)
    nprof = collect_profiles(con, date, ids)
    con.commit()
    collect_online(con)
    nev = derive_membership_events(con, date)
    db.meta_set(con, 'last_run', db.now())
    db.meta_set(con, 'last_collect_date', date)
    con.commit()
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')   # fold the WAL into the .db file so a single file is complete
    tot_players = con.execute('SELECT COUNT(*) c FROM players').fetchone()['c']
    tot_clans = con.execute('SELECT COUNT(*) c FROM clans').fetchone()['c']
    snaps = con.execute('SELECT COUNT(*) c FROM player_daily WHERE date=?', (date,)).fetchone()['c']
    con.close()
    print(f'collect {date}: registry {tot_players} players / {tot_clans} clans | today: {nsolo} on board, '
          f'{len(names)} clans fetched ({nmem} memberships), {nprof} profiles snapshotted, {nev} events. ({time.time()-t0:.0f}s)')


if __name__ == '__main__':
    main()
