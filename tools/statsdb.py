"""The Kirka stats database (SQLite, stdlib only so it runs anywhere incl. the cloud). One file: kirka-api/kirka.db.
It records, every day, the raw state of players, clans, leaderboards and online counts, so all the detailed history
(daily/weekly/monthly/all-time scores, clan join/leave timelines, churn, averages) can be derived from it later.

Design: store lifetime totals per player per day (deltas = that day's gains); store clan membership per player per
day (diffs = joins/leaves/role changes); keep every leaderboard day and every online sample. Never deletes.
"""
import pathlib
import sqlite3
import time

DB = pathlib.Path(__file__).resolve().parent.parent / 'kirka-api' / 'kirka.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY, short_id TEXT, name TEXT,
  account_created TEXT, first_seen TEXT, last_seen TEXT,
  level INTEGER, total_xp INTEGER
);
CREATE TABLE IF NOT EXISTS player_daily (
  player_id TEXT, date TEXT,
  score INTEGER, kills INTEGER, deaths INTEGER, wins INTEGER, games INTEGER, headshots INTEGER,
  level INTEGER, total_xp INTEGER,
  klo REAL, klo_ranked REAL, klo_sad REAL, klo_1v1 REAL, klo_2v2 REAL,
  coins INTEGER, diamonds INTEGER, clan TEXT, captured_at TEXT,
  PRIMARY KEY (player_id, date)
);
CREATE TABLE IF NOT EXISTS clans (
  id TEXT PRIMARY KEY, name TEXT, created TEXT, discord TEXT,
  first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS clan_daily (
  clan_id TEXT, date TEXT, name TEXT,
  all_scores INTEGER, month_scores INTEGER, war_position INTEGER, member_count INTEGER, captured_at TEXT,
  PRIMARY KEY (clan_id, date)
);
CREATE TABLE IF NOT EXISTS memberships (
  player_id TEXT, clan_id TEXT, date TEXT, role TEXT,
  all_scores INTEGER, month_scores INTEGER, joined TEXT,
  PRIMARY KEY (player_id, date)
);
CREATE TABLE IF NOT EXISTS leaderboard (
  date TEXT, board TEXT, rank INTEGER, ref_id TEXT, name TEXT, score INTEGER, extra INTEGER,
  PRIMARY KEY (date, board, rank)
);
CREATE TABLE IF NOT EXISTS online (
  ts TEXT PRIMARY KEY, eu INTEGER, na INTEGER, sa INTEGER, asia INTEGER, oce INTEGER, india INTEGER
);
CREATE TABLE IF NOT EXISTS trader_daily (
  date TEXT, tag TEXT, short_id TEXT, name TEXT,
  trades INTEGER, volume INTEGER, profit INTEGER, net_worth INTEGER, items INTEGER,
  level INTEGER, clan TEXT, captured_at TEXT,
  PRIMARY KEY (date, tag)
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT, player_id TEXT, name TEXT, type TEXT, clan_id TEXT, clan_name TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_pd_date ON player_daily(date);
CREATE INDEX IF NOT EXISTS ix_mem_clan ON memberships(clan_id, date);
CREATE INDEX IF NOT EXISTS ix_ev_player ON events(player_id);
CREATE INDEX IF NOT EXISTS ix_ev_clan ON events(clan_id);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB, timeout=60)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    con.execute('PRAGMA journal_mode=WAL')
    return con


def today():
    return time.strftime('%Y-%m-%d', time.gmtime())


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())


# ---- upserts -------------------------------------------------------------
def see_player(con, pid, short_id=None, name=None, account_created=None, level=None, total_xp=None):
    """register a player (or update their identity); set first_seen once, keep last_seen current"""
    con.execute("""INSERT INTO players (id, short_id, name, account_created, first_seen, last_seen, level, total_xp)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          short_id=COALESCE(excluded.short_id, short_id),
          name=COALESCE(excluded.name, name),
          account_created=COALESCE(excluded.account_created, account_created),
          last_seen=excluded.last_seen,
          level=COALESCE(excluded.level, level),
          total_xp=COALESCE(excluded.total_xp, total_xp)""",
        (pid, short_id, name, account_created, now(), now(), level, total_xp))


def player_snapshot(con, pid, date, stats):
    con.execute("""INSERT OR REPLACE INTO player_daily
        (player_id,date,score,kills,deaths,wins,games,headshots,level,total_xp,klo,klo_ranked,klo_sad,klo_1v1,klo_2v2,coins,diamonds,clan,captured_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, date, stats.get('score'), stats.get('kills'), stats.get('deaths'), stats.get('wins'),
         stats.get('games'), stats.get('headshots'), stats.get('level'), stats.get('total_xp'),
         stats.get('klo'), stats.get('klo_ranked'), stats.get('klo_sad'), stats.get('klo_1v1'), stats.get('klo_2v2'),
         stats.get('coins'), stats.get('diamonds'), stats.get('clan'), now()))


def see_clan(con, cid, name=None, created=None, discord=None):
    con.execute("""INSERT INTO clans (id,name,created,discord,first_seen,last_seen) VALUES (?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET name=COALESCE(excluded.name,name),
          created=COALESCE(excluded.created,created), discord=COALESCE(excluded.discord,discord),
          last_seen=excluded.last_seen""",
        (cid, name, created, discord, now(), now()))


def clan_snapshot(con, cid, date, name, all_scores, month_scores, war_position, member_count):
    con.execute("""INSERT OR REPLACE INTO clan_daily
        (clan_id,date,name,all_scores,month_scores,war_position,member_count,captured_at) VALUES (?,?,?,?,?,?,?,?)""",
        (cid, date, name, all_scores, month_scores, war_position, member_count, now()))


def membership(con, pid, cid, date, role, all_scores, month_scores, joined):
    con.execute("""INSERT OR REPLACE INTO memberships
        (player_id,clan_id,date,role,all_scores,month_scores,joined) VALUES (?,?,?,?,?,?,?)""",
        (pid, cid, date, role, all_scores, month_scores, joined))


def leaderboard_row(con, date, board, rank, ref_id, name, score, extra=None):
    con.execute("""INSERT OR REPLACE INTO leaderboard (date,board,rank,ref_id,name,score,extra)
        VALUES (?,?,?,?,?,?,?)""", (date, board, rank, ref_id, name, score, extra))


def online_point(con, ts, r):
    con.execute("""INSERT OR IGNORE INTO online (ts,eu,na,sa,asia,oce,india) VALUES (?,?,?,?,?,?,?)""",
        (ts, r.get('eu'), r.get('na'), r.get('sa'), r.get('asia'), r.get('oce'), r.get('india')))


def event(con, date, pid, name, type_, cid=None, clan_name=None, detail=None):
    con.execute("""INSERT INTO events (date,player_id,name,type,clan_id,clan_name,detail) VALUES (?,?,?,?,?,?,?)""",
        (date, pid, name, type_, cid, clan_name, detail))


def trader_daily(con, date, tag, short_id, name, trades, volume, profit, net_worth, items, level, clan):
    con.execute("""INSERT OR REPLACE INTO trader_daily
        (date,tag,short_id,name,trades,volume,profit,net_worth,items,level,clan,captured_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (date, tag, short_id, name, trades, volume, profit, net_worth, items, level, clan, now()))


def meta_get(con, k, default=None):
    row = con.execute('SELECT v FROM meta WHERE k=?', (k,)).fetchone()
    return row['v'] if row else default


def meta_set(con, k, v):
    con.execute('INSERT OR REPLACE INTO meta (k,v) VALUES (?,?)', (k, str(v)))
