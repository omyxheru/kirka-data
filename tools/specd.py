"""Headless-decode a live Kirka match: capture the room's Colyseus socket frames and decode the FULL state with
tools/colyseus.py (roster + health + team + positions) - not the scoreboard DOM. Writes the roster for the site's
room panel and archives it to kirka.db.

The join itself is minted by the local Kirka client's SPECTATE (non-intrusive, no player slot); the decode is fully
headless. The pure-headless join (joinById for every room with no client) is the next step - it needs permission to
open game-server sockets. Usage (client logged in, debug Chrome on 9222):

  python tools/specd.py            # spectate a busy public room, decode, write + archive, leave
  python tools/specd.py --stay     # keep spectating (card stays live on the site for a demo)
"""
import base64
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cdp
import colyseus
import statsdb

PUB = pathlib.Path(__file__).resolve().parent.parent / 'skin-library' / 'public' / 'rooms'
MATCH_ROSTER = """
CREATE TABLE IF NOT EXISTS match_roster (
  captured_at TEXT, room TEXT, region TEXT, mode TEXT, map TEXT,
  short_id TEXT, name TEXT, rank INTEGER, kills INTEGER, deaths INTEGER, score INTEGER,
  side TEXT, is_bot INTEGER,
  PRIMARY KEY (captured_at, room, name)
);
CREATE INDEX IF NOT EXISTS ix_roster_sid ON match_roster(short_id);
CREATE INDEX IF NOT EXISTS ix_roster_room ON match_roster(room);
"""


def _select_room(page, want_tag=None):
    """Open SERVERS and real-click a room row (a specific tag, or the busiest public one). Returns its tag or None."""
    page.send('Page.navigate', {'url': 'https://kirka.io/'}); page.wait_for_timeout(4500)
    # wait for the lobby UI (the SERVERS icon) to exist
    for _ in range(12):
        if page.evaluate(r"""()=>!![...document.querySelectorAll('.icon-btn')].find(e=>/SERVERS/.test(e.className))"""):
            break
        page.wait_for_timeout(1000)
    page.evaluate(r"""()=>{const b=[...document.querySelectorAll('.icon-btn')].find(e=>/SERVERS/.test(e.className));b&&b.click();}""")
    # the room id is the part after '~'
    rid = (want_tag or '').split('~')[-1]
    # poll for the server list (and the target row, if a specific tag) to populate
    for _ in range(12):
        page.wait_for_timeout(1000)
        ready = page.evaluate(r"""(rid)=>{const rows=[...document.querySelectorAll('.server')];if(!rows.length)return false;if(!rid)return true;return rows.some(r=>(r.querySelector('.session-id')?.textContent||'').trim().endsWith(rid));}""", rid)
        if ready:
            break
    rect = page.evaluate(r"""(rid)=>{
      const rows=[...document.querySelectorAll('.server')];
      let best=null,bn=-1;
      for(const r of rows){
        const sid=(r.querySelector('.session-id')?.textContent||'').trim();
        if(rid){ if(sid.endsWith(rid)){best=r;break;} continue; }
        if(/is-ranked/.test(r.className))continue;
        const m=(r.querySelector('.map')?.textContent||''); if(/custom/i.test(m))continue;
        const on=(r.querySelector('.online')?.textContent||'').trim(); const nn=parseInt(on)||0;
        if(nn>bn){bn=nn;best=r;}
      }
      if(!best)return null;
      best.scrollIntoView({block:'center'}); window.__t=best.querySelector('.session-id')?.textContent.trim();
      const q=best.getBoundingClientRect(); return {x:q.x+q.width/2,y:q.y+q.height/2};
    }""", rid)
    if not rect:
        return None
    page.mouse.click(rect['x'], rect['y']); page.wait_for_timeout(1800)
    return page.evaluate('()=>window.__t')


def spectate_and_capture(page, collect_s=16, want_tag=None):
    """Drive the client into a room's spectate view while capturing its websocket frames (CDP Network).
    `want_tag` targets a specific room (REGION~id); otherwise the busiest public room. Returns (tag, frames).
    Stops early once both the JOIN (reflection) and a ROOM_STATE frame are captured."""
    tag = _select_room(page, want_tag)
    if not tag:
        return None, []
    if not page.evaluate("()=>!!document.querySelector('.spectate-btn')"):
        return tag, []
    page.send('Network.enable')
    page.evaluate(r"""()=>{const b=document.querySelector('.spectate-btn');b&&b.click();}""")
    frames = []; end = time.time() + collect_s; page.ws.settimeout(0.5)
    have_join = have_state = False
    try:
        while time.time() < end:
            try:
                m = json.loads(page.ws.recv())
            except Exception:  # noqa: BLE001
                continue
            if m.get('method') in ('Network.webSocketFrameReceived', 'Network.webSocketFrameSent'):
                r = m['params']['response']
                op = r.get('opcode'); payload = r.get('payloadData', '')
                frames.append({'op': op, 'data': payload})
                if op == 2 and len(payload) >= 4:
                    b0 = base64.b64decode(payload[:4])[0]  # 4 b64 chars = first 3 bytes; [0] = opcode
                    if b0 == 10:
                        have_join = True
                    elif b0 == 14:
                        have_state = True
                    if have_join and have_state:
                        break  # got the reflection + full state; done
    finally:
        page.ws.settimeout(120)
    return tag, frames


def capture_room(page, want_tag=None, leave=True):
    """Full on-demand capture of one room: spectate -> decode -> clean roster dict. Used by the bridge server."""
    tag, frames = spectate_and_capture(page, want_tag=want_tag)
    if not tag:
        return {'error': 'no_room', 'message': 'Room not found in the server list (it may have ended).'}
    if not frames:
        return {'error': 'no_spectate', 'tag': tag, 'message': 'Could not start spectating that room.'}
    state = decode_state(frames)
    if leave:
        page.send('Page.navigate', {'url': 'https://kirka.io/'})
    if not state:
        return {'error': 'no_state', 'tag': tag, 'message': 'Spectated but no full state frame captured; try again.'}
    return to_panel(tag, state)


def decode_state(frames):
    """From captured frames: parse the JOIN reflection + ROOM_STATE, return the decoded state (dict)."""
    join = state = None
    for f in frames:
        if f['op'] != 2:
            continue
        raw = base64.b64decode(f['data'])
        if not raw:
            continue
        if raw[0] == 10 and join is None and b'schema' in raw[:12]:
            join = raw
        elif raw[0] == 14 and state is None:
            state = raw
    if not join or not state:
        return None
    types, root = colyseus.parse_reflection(join)
    return colyseus.Decoder(types, root).decode(state)


def to_panel(tag, state):
    players = colyseus.roster(state)
    players = [p for p in players if p.get('name')]
    players.sort(key=lambda p: (p.get('score') or 0), reverse=True)
    rows = []
    for i, p in enumerate(players, 1):
        rows.append({
            'rank': i, 'name': p['name'], 'shortId': p['shortId'],
            'kills': p['kills'], 'deaths': p['deaths'], 'score': p['score'],
            'side': p['team'] or 'all', 'isBot': p['isBot'],
            'health': p['health'], 'shield': p.get('shield'), 'role': p.get('role'),
            'weaponSkin': p.get('weaponSkin'),
        })
    return {'room': tag, 'capturedAt': statsdb.now() + 'Z', 'count': len(rows),
            'source': 'socket', 'players': rows}


def write_and_archive(data):
    PUB.mkdir(parents=True, exist_ok=True)
    tag = data['room']
    (PUB / f'{tag}.json').write_text(json.dumps(data, indent=1), encoding='utf-8')
    idx_path = PUB / 'index.json'
    idx = {}
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001
            idx = {}
    idx[tag] = {'capturedAt': data['capturedAt'], 'count': data['count'],
                'humans': sum(1 for p in data['players'] if not p['isBot']), 'source': 'socket'}
    idx = dict(sorted(idx.items(), key=lambda kv: kv[1]['capturedAt'], reverse=True)[:60])
    idx_path.write_text(json.dumps(idx, indent=1), encoding='utf-8')
    # archive
    con = statsdb.connect(); con.executescript(MATCH_ROSTER)
    region = tag.split('~')[0].lower()
    for p in data['players']:
        con.execute("""INSERT OR REPLACE INTO match_roster
            (captured_at,room,region,mode,map,short_id,name,rank,kills,deaths,score,side,is_bot)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data['capturedAt'], tag, region, None, None, p['shortId'], p['name'], p['rank'],
             p['kills'], p['deaths'], p['score'], p['side'], 1 if p['isBot'] else 0))
    con.commit(); con.close()


def main():
    page = cdp.kirka_page()
    tag, frames = spectate_and_capture(page)
    if not tag or not frames:
        print('Could not spectate/capture a room (no busy public room, or spectate did not start). Try again.')
        return
    state = decode_state(frames)
    if not state:
        print(f'{tag}: captured {len(frames)} frames but no JOIN+STATE pair (retry - capture must span the join).')
        return
    data = to_panel(tag, state)
    write_and_archive(data)
    humans = sum(1 for p in data['players'] if not p['isBot'])
    print(f"{tag}: headless-decoded {data['count']} players ({humans} human) -> public/rooms/{tag}.json + kirka.db")
    for p in data['players'][:6]:
        b = ' (bot)' if p['isBot'] else f" #{p['shortId']}"
        print(f"  {p['rank']}. {p['name']}{b}  {p['kills']}/{p['deaths']}  score {p['score']}  hp {p['health']}  [{p['side']}]")
    if '--stay' not in sys.argv:
        page.send('Page.navigate', {'url': 'https://kirka.io/'})


if __name__ == '__main__':
    main()
