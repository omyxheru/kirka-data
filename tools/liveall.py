"""LIVE player data for every open Kirka room - the "guest army" (xip-authorised, 2026-11-15).

How it works (no faked headers, no staff/KAT endpoints):
  1. MINT  - a guest browser tab (incognito context in debug Chrome, tools/guest.py style - never the user's account)
             opens SERVERS, picks a room and clicks SPECTATE. A page-level WebSocket hook catches the game-room
             seat URL  wss://<region>.kirka.io/<processId>/<roomId>?WmwNWnMw=<sessionId>  and gives the game a
             dummy socket, so the 3D match never loads in that tab.
  2. HOLD  - a light "holder" tab on https://kirka.io/ads.txt (a real kirka.io page, plain text, no game) opens
             that seat's socket itself (genuine kirka.io origin), sends the JOIN ack and queues the state frames.
  3. DECODE- Python polls the holder, feeds op-14 state + op-15 patches into tools/colyseus.py (one stateful
             decoder per room) -> live roster per room.
Spectators take no player slot and can't affect the match.

  python tools/liveall.py --one            # mint + hold ONE room, print the live roster for ~25 s (test)
  python tools/liveall.py                  # every room, continuously; writes skin-library/public/rooms/live.json
Output: public/rooms/live.json (all rooms, refreshed ~2 s), per-room public/rooms/<tag>.json + kirka.db
match_roster archive (once a minute per room). Docs: docs/kirka-everything.md section 16.
"""
import base64
import msgpack
import json
import struct
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cdp
import colyseus

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUB = ROOT / 'skin-library' / 'public' / 'rooms'
LOG = ROOT / 'captures' / 'liveall'

# page-level hook, installed before any game script runs. Only fires while armed (set right before SPECTATE), so
# the client's own lobby socket is never touched.
HOOK = r"""(()=>{ if (window.__hooked) return; window.__hooked = true;
  const W = window.WebSocket; window.__seats = []; window.__allws = [];
  // on a /games/<tag> page every room socket is caught (never connects) - so opening a room link can never join as a player
  window.__arm = false;  // only armed right before a SPECTATE click (direct /games/ links tested 2026-11-15: not safe)
  function F(url, protocols){
    const u = String(url); window.__allws.push([Date.now(), window.__arm, u]);
    if (window.__arm && /\.kirka\.io(:\d+)?\/[^\/?]+\/[^\/?]+\?WmwNWnMw=/.test(u)) {
      window.__arm = false; window.__seats.push(u);
      const fake = new EventTarget();
      Object.assign(fake, {url:u, readyState:0, binaryType:'arraybuffer', protocol:'', extensions:'',
                           bufferedAmount:0, onopen:null, onmessage:null, onclose:null, onerror:null,
                           send(){}, close(){ this.readyState = 3; }});
      return fake;
    }
    return protocols === undefined ? new W(url) : new W(url, protocols);
  }
  F.prototype = W.prototype; F.CONNECTING=0; F.OPEN=1; F.CLOSING=2; F.CLOSED=3;
  window.WebSocket = F;
})();"""

# holder page: opens room sockets on the kirka.io origin and queues the frames we need (JOIN / STATE / PATCH / ERROR)
HOLDER = r"""(()=>{ if (window.__H) return true;
  const b64 = (u8) => { let s=''; for (let i=0;i<u8.length;i+=0x8000) s+=String.fromCharCode.apply(null,u8.subarray(i,i+0x8000)); return btoa(s); };
  window.__H = { rooms:{},
    open(tag, url){
      const r = { q:[], closed:false, code:null, opened:false, n:0 }; this.rooms[tag] = r;
      const ws = new WebSocket(url); ws.binaryType = 'arraybuffer'; r.ws = ws;
      ws.onopen = () => { r.opened = true; };
      ws.onmessage = (e) => { if (typeof e.data === 'string') return; const u8 = new Uint8Array(e.data); if (!u8.length) return;
        r.n++; const op = u8[0];
        if (op === 10) { r.q.push(b64(u8)); try { ws.send(new Uint8Array([10])); } catch(_){} }
        else if (op === 14 || op === 15 || op === 11 || op === 12) r.q.push(b64(u8));
        else if (op === 13 && u8[1] === 31) r.q.push(b64(u8)); };   // type 31 = hit/kill event (kill feed)
      ws.onclose = (e) => { r.closed = true; r.code = e.code; };
      return true; },
    poll(){ const out = {}; for (const [t,r] of Object.entries(this.rooms)) { out[t] = {q:r.q, closed:r.closed, code:r.code, opened:r.opened, n:r.n}; r.q = []; if (r.closed) delete this.rooms[t]; } return out; },
    close(tag){ const r = this.rooms[tag]; if (r) { try { r.ws.close(); } catch(_){} } return true; } };
  return true; })()"""


def new_tab(ctx, url):
    tid = cdp._browser_call('Target.createTarget', {'url': 'about:blank', 'browserContextId': ctx})['targetId']
    time.sleep(0.4)
    page = cdp.Page({'targetId': tid, 'url': 'about:blank'})
    page.send('Page.enable')
    if url:
        page.send('Page.navigate', {'url': url})
    return page


def guest_context():
    return cdp._browser_call('Target.createBrowserContext', {}).get('browserContextId')


PICK = r"""([rid,cname])=>{
  const rows=[...document.querySelectorAll('.server')];
  let best=null,bn=-1;
  for(const r of rows){
    const sid=(r.querySelector('.session-id')?.textContent||'').trim();
    if(rid && sid){ if(sid.endsWith('~'+rid)){best=r;break;} continue; }
    if(rid && !sid){ // USER MODE (custom map) rows have no session id: match by the custom map name
      if(cname && r.textContent.includes(cname) && !(window.__tried||[]).includes(r.textContent.trim())){best=r;break;}
      continue; }
    if(/is-ranked/.test(r.className))continue;
    const nn=parseInt((r.querySelector('.online')?.textContent||'').trim())||0;
    if(nn>bn){bn=nn;best=r;}
  }
  if(!best)return null;
  best.scrollIntoView({block:'center'}); window.__t=(best.querySelector('.session-id')?.textContent||'').trim()||('custom:'+best.textContent.trim());
  const q=best.getBoundingClientRect(); return {x:q.x+q.width/2,y:q.y+q.height/2};
}"""


def pick_room(page, want_tag=None, cname=None):
    """Open SERVERS and real-click a room row. Looks in every list tab (MAIN / PARKOUR / CUSTOM).
    Returns the row's tag (REGION~id) or None."""
    page.send('Page.navigate', {'url': 'https://kirka.io/'})
    for _ in range(20):
        page.wait_for_timeout(700)
        if page.evaluate(r"""()=>!![...document.querySelectorAll('.icon-btn')].find(e=>/SERVERS/.test(e.className))"""):
            break
    page.evaluate(r"""()=>{const b=[...document.querySelectorAll('.icon-btn')].find(e=>/SERVERS/.test(e.className));b&&b.click();}""")
    rid = (want_tag or '').split('~')[-1]
    for _ in range(14):
        page.wait_for_timeout(700)
        if page.evaluate("()=>document.querySelectorAll('.server').length>0"):
            break
    ntabs = page.evaluate("()=>[...document.querySelectorAll('.tabs .text-2.tab')].length") or 1
    for ti in range(ntabs):
        if ti:  # switch list tab (PARKOUR, CUSTOM)
            page.evaluate("(i)=>{const t=[...document.querySelectorAll('.tabs .text-2.tab')][i];t&&t.click();}", ti)
            page.wait_for_timeout(1200)
        rect = page.evaluate(PICK, [rid, cname])
        if rect:
            page.mouse.click(rect['x'], rect['y']); page.wait_for_timeout(1500)
            return page.evaluate('()=>window.__t')
        if not rid:
            break
    return None


def list_rooms(region):
    """Public matchmake listing for a region -> [{id, mode, map, cname, players, loggedOnly, needLevel}]."""
    import urllib.request
    try:
        d = json.load(urllib.request.urlopen(f'https://{region}.kirka.io/matchmake/', timeout=8))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in d:
        if not r.get('name') or r.get('name') == 'LobbyRoom' or not r.get('WWMNmww'):
            continue
        m = r.get('WnWwwMm') or {}
        out.append({'id': r['WWMNmww'], 'mode': r.get('name'), 'map': m.get('wWwWmMnN'),
                    'cname': m.get('wWnMNwWm') or m.get('wWMwWmNn'), 'players': m.get('wWMnw') or 0,
                    'loggedOnly': bool(m.get('loggedOnly___METADATA')), 'needLevel': m.get('needLevel___METADATA')})
    return out


class Minter:
    """A guest kirka.io tab that mints spectator seats (catches the room socket URL instead of connecting)."""

    def __init__(self, ctx, region=None):
        self.region = region
        self.page = new_tab(ctx, None)
        self.page.send('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK})
        if region:  # the client reads its region from localStorage.region (found 2026-11-15)
            self.page.send('Page.addScriptToEvaluateOnNewDocument',
                           {'source': f"try{{localStorage.setItem('region','{region.upper()}')}}catch(e){{}}"})
        self.page.send('Page.navigate', {'url': 'https://kirka.io/'})

    def mint(self, want_tag=None, wait_s=8, cname=None):
        """Open SERVERS, click the room (or the busiest public one), arm the hook, click SPECTATE.
        Returns (tag, seat_url) or (tag|None, None)."""
        p = self.page
        tag = pick_room(p, want_tag, cname)
        if not tag:
            return None, None
        if not p.evaluate("()=>!!document.querySelector('.spectate-btn')"):
            why = p.evaluate("()=>[...document.querySelectorAll('button')].filter(b=>b.offsetWidth).map(b=>b.textContent.trim()).filter(Boolean).slice(0,12).join(' | ')")
            print(f'    no SPECTATE button for {tag}; visible buttons: {why}')
            return tag, None
        p.evaluate("()=>{window.__seats=[];window.__arm=true;const b=document.querySelector('.spectate-btn');b&&b.click();}")
        end = time.time() + wait_s
        while time.time() < end:
            seats = p.evaluate('()=>window.__seats') or []
            if seats:
                return tag, seats[0]
            p.wait_for_timeout(250)
        p.evaluate('()=>{window.__arm=false}')
        return tag, None


class Holder:
    """A light kirka.io page (ads.txt) that holds the room sockets."""

    def __init__(self, ctx):
        self.page = new_tab(ctx, 'https://kirka.io/ads.txt')
        self.page.wait_for_timeout(2500)
        self.page.evaluate(HOLDER)

    def open(self, tag, url):
        self.page.evaluate(HOLDER)  # idempotent (survives a reload)
        return self.page.evaluate('([t,u])=>window.__H.open(t,u)', [tag, url])

    def poll(self):
        return self.page.evaluate('()=>window.__H ? window.__H.poll() : {}') or {}


class Room:
    def __init__(self, tag, url):
        self.tag, self.url = tag, url
        self.dec = None; self.state = None; self.err = None
        self.t0 = time.time(); self.updated = None; self.patches = 0; self.closed = False
        self.frames = []; self.dumped = False   # raw frames kept for debugging decode errors
        self.feed_log = []                      # last hits/kills (op-13 type 31), newest last
        self.hits = {}                          # sessionId -> {dmg, hits, hs, kills, hsKills, taken} since we joined

    def dump(self, why):
        if self.dumped:
            return
        self.dumped = True
        LOG.mkdir(parents=True, exist_ok=True)
        f = LOG / f"{self.tag.replace('~', '_')}-{time.strftime('%H%M%S')}.json"
        f.write_text(json.dumps({'tag': self.tag, 'why': why, 'frames': self.frames}), encoding='utf-8')
        print(f'  dumped {len(self.frames)} frames -> {f.name} ({why})')

    def feed(self, b64frame):
        raw = base64.b64decode(b64frame)
        self.frames.append(b64frame)
        if len(self.frames) > 20000:
            del self.frames[2:12000]  # keep JOIN + STATE at the front
        op = raw[0]
        if op == 10 and b'schema' in raw[:12]:
            types, root = colyseus.parse_reflection(raw)
            self.dec = colyseus.Decoder(types, root)
        elif op in (14, 15) and self.dec:
            try:
                self.state = self.dec.decode(raw)
                self.patches += op == 15
                self.updated = time.time()
            except Exception as e:  # noqa: BLE001
                if not self.err:
                    self.err = f'decode: {e}'
                    self.dump(self.err)
        elif op == 13 and len(raw) > 2 and raw[1] == 31:
            self.on_hit(raw)
        elif op == 11:  # Colyseus ERROR: [11, code(number), message(string)]
            try:
                r = colyseus.Reader(raw, 1); code = colyseus.s_number(r); msg = colyseus.s_string(r)
                self.err = f'server error {code}: {msg}'
            except Exception:  # noqa: BLE001
                self.err = 'server error ' + raw[1:].hex()
            self.dump(self.err)

    def on_hit(self, raw):
        """op-13 type 31: {WmwwM victim sid, WmwwMWN attacker sid, WmwwMNn damage, WwMwN headshot, WmwwMNWn killed}
        (decoded by the 2026-11-15 telemetry dig, verified 13/13 against state patches - docs/xip-more-ideas)."""
        try:
            ev = msgpack.unpackb(raw[2:], raw=False)
            vic, att = ev.get('WmwwM'), ev.get('WmwwMWN')
            dmg, hs, kill = ev.get('WmwwMNn') or 0, bool(ev.get('WwMwN')), bool(ev.get('WmwwMNWn'))
        except Exception:  # noqa: BLE001
            return
        a = self.hits.setdefault(att, {'dmg': 0, 'hits': 0, 'hs': 0, 'kills': 0, 'hsKills': 0, 'taken': 0})
        a['dmg'] += dmg; a['hits'] += 1; a['hs'] += hs; a['kills'] += kill; a['hsKills'] += hs and kill
        self.hits.setdefault(vic, {'dmg': 0, 'hits': 0, 'hs': 0, 'kills': 0, 'hsKills': 0, 'taken': 0})['taken'] += dmg
        names = {}
        if self.state:
            for p in colyseus.roster(self.state):
                names[p.get('sessionId')] = (p.get('name'), p.get('shortId'))   # many players are "Newbie": keep shortId
        an, asid = names.get(att, (att, None)); vn, vsid = names.get(vic, (vic, None))
        self.feed_log.append({'t': round(time.time(), 2), 'a': an, 'aId': asid, 'v': vn, 'vId': vsid,
                              'dmg': dmg, 'hs': hs, 'kill': kill})
        del self.feed_log[:-30]

    def players(self):
        if not self.state:
            return []
        rows = [p for p in colyseus.roster(self.state) if p.get('name') and not p.get('isSpectator')]
        rows.sort(key=lambda p: (p.get('score') or 0), reverse=True)
        for p in rows:
            p['hits'] = self.hits.get(p.get('sessionId'))   # damage/headshots seen since we joined (None = none yet)
        return rows


def show(room):
    ps = room.players()
    print(f"\n[{time.strftime('%H:%M:%S')}] {room.tag}  {len(ps)} players  patches={room.patches}"
          + (f"  ERR {room.err}" if room.err else ''))
    for i, p in enumerate(ps, 1):
        who = '(bot)' if p['isBot'] else f"#{p['shortId']}"
        pos = p.get('pos') or {}
        xyz = ','.join(f"{v:.0f}" for v in pos.values()) if isinstance(pos, dict) else ''
        print(f"  {i:2}. {p['name'][:18]:18} {who:9} {p['kills']}/{p['deaths']:<3} sc {p['score']:<5} "
              f"hp {p['health']} [{p['team'] or 'all'}] pos {xyz}")


def test_one(hold_s=25):
    ctx = guest_context()
    try:
        print('guest context up; minting a seat (busiest public room)...')
        m = Minter(ctx); m.page.wait_for_timeout(3000)
        tag, url = m.mint()
        print('room:', tag, '| seat:', url)
        if not url:
            print('no seat caught (spectate did not start, or hook missed it).'); return
        h = Holder(ctx)
        h.open(tag, url)
        room = Room(tag, url)
        end = time.time() + hold_s; last = 0
        while time.time() < end:
            for t, r in h.poll().items():
                for f in r['q']:
                    room.feed(f)
                if r['closed']:
                    room.closed = True; print(f'socket closed code={r["code"]} opened={r["opened"]} frames={r["n"]}')
            if room.err and not room.state:
                print('ERROR:', room.err); break
            if room.state and time.time() - last > 5:
                show(room); last = time.time()
            if room.closed:
                break
            h.page.wait_for_timeout(1000)
        if not room.state:
            print('no state decoded. err=', room.err)
    finally:
        try:
            cdp._browser_call('Target.disposeBrowserContext', {'browserContextId': ctx})
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- every room, all regions
REGIONS = ['eu', 'na', 'sa', 'asia', 'oceania', 'india']
PACE = 3.0                      # seconds between seat requests per guest lobby
CLICK = '--click' in sys.argv   # legacy: mint by clicking SERVERS rows instead of the direct lobby request
CLOUD = '--cloud' in sys.argv   # archive to reports/live/*.ndjson instead of kirka.db (for the GitHub Action)


def run_all(minutes=None, regions=REGIONS):
    import queue
    import threading
    import specd
    seats = queue.Queue()               # (tag, url) from minter threads -> main thread opens them
    lock = threading.Lock()
    held, backoff, listing = {}, {}, {}  # tag -> Room ; tag -> retry-after ts ; tag -> (mode, map, listed players)
    stop = threading.Event()
    ctxs = []

    def minter(region):
        R = region.upper()
        hp = cdp.Page({'targetId': holder.page.target_id, 'url': ''})   # own CDP link to the holder page (thread-safe)
        ctx = guest_context(); ctxs.append(ctx)
        if CLICK:   # old flow: click rows in the SERVERS list
            m = Minter(ctx, region); m.page.wait_for_timeout(4000)
        else:       # direct seat request over the page's own lobby (docs §18) - any listed room, ~0.4 s each
            import lobbyseat
            m = lobbyseat.SeatMinter(ctx, region, new_tab)
            if not m.ready(60):
                print(f'  [{region}] lobby not ready: {m.status()}')
        while not stop.is_set():
            if not CLICK and not m.alive():   # lobby dropped -> reload the tab (the client reconnects + re-checks)
                print(f'  [{region}] lobby down {m.status()} - reloading')
                m.load()
                if not m.ready(60):
                    stop.wait(30); continue
            rooms = list_rooms(region)
            with lock:
                if rooms:  # recount this region (drop rooms that ended)
                    for k in [k for k in listing if k.startswith(R + '~')]:
                        del listing[k]
                for r in rooms:
                    listing[f"{R}~{r['id']}"] = (r['mode'], r['cname'] or r['map'], r['players'])
                todo = [r for r in sorted(rooms, key=lambda r: -r['players'])
                        if not r['loggedOnly']            # guests can't spectate login-only rooms (found 2026-11-15)
                        and f"{R}~{r['id']}" not in held and backoff.get(f"{R}~{r['id']}", 0) < time.time()]
            for r in todo[:1 if CLICK else 8]:   # click flow: one at a time; direct: a batch, then re-list
                tag = f"{R}~{r['id']}"
                try:
                    if CLICK:
                        got, url = m.mint(tag, cname=r['cname'])
                    else:
                        url, why = m.mint(r['id']); got = why if not url else tag
                except Exception as e:  # noqa: BLE001
                    got, url = None, None; print(f'  [{region}] mint error {e}')
                if url:
                    real = f"{R}~{url.split('?')[0].rstrip('/').split('/')[-1]}"  # the seat URL holds the real roomId
                    with lock:
                        dup = real in held
                        if not dup:
                            held[real] = None  # reserved; main thread fills the Room
                    if dup:
                        print(f'  [{region}] seat was for {real}, already held - dropped')
                    else:   # open at once: a new reservation before the last seat is used -> 'onAuth failed'
                        with lock:
                            held[real] = Room(real, url)   # before open, so the main loop never drops the JOIN frame
                        hp.evaluate(HOLDER)
                        hp.evaluate('([t,u])=>window.__H.open(t,u)', [real, url])
                        if real != tag:
                            print(f'  [{region}] asked {tag} ({r["cname"]}), seat is {real}')
                    if not CLICK:
                        stop.wait(PACE)   # lobby rate limit: ~1 request / 3 s per guest is clean (tested 2026-11-15)
                else:
                    rl = isinstance(got, str) and 'Rate limit' in got
                    with lock:
                        backoff[tag] = time.time() + (8 if rl else 180)
                    if rl:
                        stop.wait(6); continue
                    print(f'  [{region}] no seat for {tag} {r["mode"]} {r["cname"] or r["map"]} (row={got}); retry in 3 min')
                    if not CLICK:
                        stop.wait(PACE)
            stop.wait(15 if not todo else 0)

    ctx_h = guest_context(); ctxs.append(ctx_h)
    holder = Holder(ctx_h)
    threads = [threading.Thread(target=minter, args=(r,), daemon=True) for r in regions]
    for t in threads:
        t.start(); time.sleep(2)
    print(f'guest army: {len(regions)} minter tabs + 1 holder tab. Ctrl+C to stop.')
    PUB.mkdir(parents=True, exist_ok=True)
    last_write = last_print = 0; archived = {}
    t_end = time.time() + minutes * 60 if minutes else None
    try:
        while not (t_end and time.time() > t_end):
            try:
                for tag, r in holder.poll().items():
                    room = held.get(tag)
                    if not room:
                        continue
                    for f in r['q']:
                        room.feed(f)
                    if r['closed']:
                        if room.err:
                            room.dump(room.err)
                        print(f'  closed {tag} code={r["code"]} (patches {room.patches}){" ERR " + room.err if room.err else ""}')
                        with lock:
                            held.pop(tag, None)
                            backoff[tag] = time.time() + (30 if room.state else 180)
                now = time.time()
                if now - last_write > 2:
                    write_live(held, listing, lock); last_write = now
                for tag, room in list(held.items()):
                    if room and room.state and now - archived.get(tag, 0) > 60:
                        try:
                            if CLOUD:   # text history (git-friendly); tools/live_import.py loads it into kirka.db
                                archive_line(tag, room, listing)
                            else:
                                specd.write_and_archive(specd.to_panel(tag, room.state))
                            archived[tag] = now
                        except Exception as e:  # noqa: BLE001
                            print('  archive error', tag, e)
                if now - last_print > 15:
                    live = [r for r in held.values() if r and r.state]
                    print(f"[{time.strftime('%H:%M:%S')}] live rooms {len(live)}/{len(listing)} listed | "
                          f"players {sum(len(r.players()) for r in live)} | pending {sum(1 for r in held.values() if r is None)}")
                    last_print = now
                holder.page.wait_for_timeout(1000)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001 - one bad room/step must never stop the army
                print('  [loop error]', type(e).__name__, e); time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        write_live(held, listing, lock)
        for c in ctxs:
            try:
                cdp._browser_call('Target.disposeBrowserContext', {'browserContextId': c})
            except Exception:  # noqa: BLE001
                pass
        print('stopped; guest contexts closed.')


def plain(v, depth=0):
    """Decoded schema values can be shared/linked objects - keep only plain JSON-safe data."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if depth > 3:
        return None
    if isinstance(v, dict):
        return {str(k): plain(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x, depth + 1) for x in v]
    return str(v)


HIST = ROOT / 'reports' / 'live'


def archive_line(tag, room, listing):
    """One room snapshot -> a line in reports/live/<UTC date>.ndjson (compact player rows)."""
    mode, mp, _ = listing.get(tag, (None, None, None))
    ps = []
    for p in room.players():
        h = p.get('hits') or {}
        ps.append([plain(p['shortId']), plain(p['name']), plain(p['team']), plain(p['kills']), plain(p['deaths']),
                   plain(p['score']), 1 if p['isBot'] else 0,
                   h.get('dmg', 0), h.get('hits', 0), h.get('hs', 0), h.get('hsKills', 0), h.get('taken', 0)])
    line = {'t': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'room': tag, 'mode': mode, 'map': mp,
            'cols': ['shortId', 'name', 'team', 'kills', 'deaths', 'score', 'bot',
                     'dmg', 'hits', 'hsHits', 'hsKills', 'dmgTaken'],   # hit counters = since we joined, not whole match
            'p': ps}
    HIST.mkdir(parents=True, exist_ok=True)
    with open(HIST / f"{time.strftime('%Y-%m-%d', time.gmtime())}.ndjson", 'a', encoding='utf-8') as f:
        f.write(json.dumps(line, separators=(',', ':'), ensure_ascii=False) + '\n')


def write_live(held, listing, lock):
    rooms = []
    with lock:
        items = list(held.items())
    for tag, room in items:
        if not room or not room.state:
            continue
        mode, mp, _ = listing.get(tag, (None, None, None))
        ps = []
        for i, p in enumerate(room.players(), 1):
            pos = p.get('pos') if isinstance(p.get('pos'), dict) else {}
            ps.append({'rank': i, 'name': plain(p['name']), 'shortId': plain(p['shortId']), 'isBot': p['isBot'],
                       'team': plain(p['team']), 'kills': plain(p['kills']), 'deaths': plain(p['deaths']),
                       'score': plain(p['score']),
                       'health': plain(p['health']), 'shield': plain(p.get('shield')), 'role': plain(p.get('role')),
                       'weapon': plain(p.get('weaponSkin')),   # the weapon in hand (old name kept below)
                       'weaponSkin': plain(p.get('weaponSkin')), 'hits': p.get('hits'),
                       # positions are tournament/event-only (xip) -> never in the public cloud output
                       'pos': None if CLOUD else [plain(v) for v in pos.values()]})
        rooms.append({'tag': tag, 'region': tag.split('~')[0], 'mode': mode, 'map': mp,
                      'since': room.t0, 'updated': room.updated, 'patches': room.patches, 'players': ps,
                      'feed': room.feed_log[-15:]})
    rooms.sort(key=lambda r: (r['region'], -len(r['players'])))
    out = {'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'rooms': len(rooms),
           'players': sum(len(r['players']) for r in rooms), 'listed': len(listing), 'data': rooms}
    tmp = PUB / 'live.json.tmp'
    tmp.write_text(json.dumps(out), encoding='utf-8'); tmp.replace(PUB / 'live.json')


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # room text can contain any character
    except Exception:  # noqa: BLE001
        pass
    if '--headless' in sys.argv:   # start our own headless Chrome (cloud / no visible browser) - tools/chrome.py
        import chrome
        chrome.start()
    if '--one' in sys.argv:
        test_one()
    else:
        mins = None
        if '--minutes' in sys.argv:
            mins = float(sys.argv[sys.argv.index('--minutes') + 1])
        regs = REGIONS
        if '--regions' in sys.argv:
            regs = sys.argv[sys.argv.index('--regions') + 1].split(',')
        run_all(mins, regs)
