"""Mint spectator seats through the page's OWN lobby socket - no SERVERS list clicking (2026-11-15, docs §18).

A guest kirka.io tab loads normally; the real client connects its region lobby and answers the lobby's bot check
itself (type 35 - we never touch or generate that). This hook only keeps a handle on that lobby socket. Then
window.__reserve(roomId) sends the same message the SPECTATE button sends:
    0x0d 0x65  msgpack {wwMnWWNm: roomId, wWwNWM: true (spectate), wWwNWnmM: false}
and the type-102 reply (0x0d 0x66) - the seat reservation - is caught BEFORE the game sees it (so the client never
tries to join; any room socket it might still open is replaced by a dummy, so it can never join as a player).
Python decodes the reply -> seat URL  wss://<region>.kirka.io/<processId>/<roomId>?WmwNWnMw=<sessionId>

  python tools/lobbyseat.py [region] [n]     # test: mint n seats for the busiest rooms and print them
"""
import base64
import json
import pathlib
import sys
import time

import msgpack

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cdp

ROOM_RE = r"/\.kirka\.io(:\d+)?\/[^\/?]+\/[^\/?]+\?WmwNWnMw=/"

HOOK = r"""(()=>{ if (window.__hooked2) return; window.__hooked2 = true;
  const W = window.WebSocket; const RE = %RE%;
  const b64 = (u8) => { let s=''; for (let i=0;i<u8.length;i+=0x8000) s+=String.fromCharCode.apply(null,u8.subarray(i,i+0x8000)); return btoa(s); };
  Object.assign(window, { __lobby:null, __lobbyUrl:null, __lobbyOk:false, __lobbyClosed:null, __pending:0,
                          __replies:[], __other:[], __blocked:[] });
  function dummy(u){ const f = new EventTarget();
    Object.assign(f, {url:u, readyState:0, binaryType:'arraybuffer', protocol:'', extensions:'', bufferedAmount:0,
      onopen:null, onmessage:null, onclose:null, onerror:null, send(){}, close(){ this.readyState = 3; }}); return f; }
  function F(url, protocols){
    const u = String(url);
    if (RE.test(u)) {
      if (window.__lobby) { window.__blocked.push(u); return dummy(u); }   // never a 2nd room socket (= no game join)
      const ws = protocols === undefined ? new W(url) : new W(url, protocols);
      window.__lobby = ws; window.__lobbyUrl = u;
      // registered before the client sets ws.onmessage -> runs first, can hide our seat replies from the game
      ws.addEventListener('message', (e) => {
        if (typeof e.data === 'string' || !e.data.byteLength) return;
        const u8 = new Uint8Array(e.data);
        if (u8[0] !== 13) return;
        if (u8[1] === 35 && u8.length === 3 && u8[2] === 0xc3) { window.__lobbyOk = true;   // the client passed the check
          // this tab only needs its lobby socket now: draw the 3D lobby at 1 fps (saves most of the CPU)
          const raf = (cb) => setTimeout(() => cb(performance.now()), 1000);
          window.requestAnimationFrame = raf; }
        // 102 = seat; 101 inbound = an error string for our request ("Rate limit, retry in a few seconds",
        // "Room doesnt exist") - hidden from the game too so it doesn't pop an error toast
        // always hidden (we never click, so every seat/refusal is ours - a late one must not make the game join)
        if (u8[1] === 102 || u8[1] === 101) {
          window.__pending = Math.max(0, window.__pending - 1); window.__replies.push([Date.now(), u8[1], b64(u8.subarray(2))]);
          e.stopImmediatePropagation(); return; }
        if (window.__pending > 0 && window.__other.length < 50) window.__other.push([Date.now(), u8[1], b64(u8.subarray(2, 200))]);
      });
      ws.addEventListener('close', (e) => { window.__lobbyClosed = e.code; });
      return ws;
    }
    return protocols === undefined ? new W(url) : new W(url, protocols);
  }
  F.prototype = W.prototype; F.CONNECTING=0; F.OPEN=1; F.CLOSING=2; F.CLOSED=3;
  window.WebSocket = F;
  const fs = (s) => { const b = new TextEncoder().encode(s); return [0xa0 | b.length, ...b]; };   // msgpack fixstr (<32 B)
  window.__reserve = (roomId) => {
    const ws = window.__lobby; if (!ws || ws.readyState !== 1 || !window.__lobbyOk) return false;
    const msg = [0x0d, 0x65, 0x83, ...fs('wwMnWWNm'), ...fs(roomId), ...fs('wWwNWM'), 0xc3, ...fs('wWwNWnmM'), 0xc2];
    window.__pending++; ws.send(new Uint8Array(msg)); return true; };
})();""".replace('%RE%', ROOM_RE)


def seat_from_reply(b64payload, region):
    """type-102 msgpack -> (roomId, seat_url, listing) or (None, None, raw) if it isn't a seat."""
    v = msgpack.unpackb(base64.b64decode(b64payload), raw=False, strict_map_key=False)
    try:
        res = v['wWnWMNwm']; room = res['mwwnWMNW']
        pid, rid, sid = room['WmwNWnwM'], room['WWMNmww'], res['WmwNWnMw']
    except (KeyError, TypeError):
        return None, None, v
    return rid, f"wss://{region.lower()}.kirka.io/{pid}/{rid}?WmwNWnMw={sid}", room


class SeatMinter:
    """One guest tab = one region lobby. mint(roomId) -> seat URL (or None + reason)."""

    def __init__(self, ctx, region, new_tab):
        self.region = region.lower()
        self.page = new_tab(ctx, None)
        self.page.send('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK})
        self.page.send('Page.addScriptToEvaluateOnNewDocument',
                       {'source': f"try{{localStorage.setItem('region','{region.upper()}')}}catch(e){{}}"})
        self.load()

    def load(self):
        self.page.send('Page.navigate', {'url': 'https://kirka.io/'})
        self.t_load = time.time()

    def status(self):
        return self.page.evaluate("()=>({ok:window.__lobbyOk, url:window.__lobbyUrl, closed:window.__lobbyClosed,"
                                  " state:window.__lobby&&window.__lobby.readyState, blocked:window.__blocked})") or {}

    def ready(self, timeout=40):
        end = time.time() + timeout
        while time.time() < end:
            s = self.status()
            if s.get('ok') and s.get('state') == 1:
                return True
            self.page.wait_for_timeout(500)
        return False

    def alive(self):
        s = self.status()
        return bool(s.get('ok')) and s.get('state') == 1

    def mint(self, room_id, wait_s=6):
        if not self.page.evaluate('(r)=>window.__reserve(r)', room_id):
            return None, 'lobby not ready'
        end = time.time() + wait_s
        while time.time() < end:
            reps = self.page.evaluate('()=>window.__replies.splice(0)') or []
            for _t, typ, pl in reps:
                if typ == 101:   # lobby refused: a msgpack string
                    try:
                        msg = msgpack.unpackb(base64.b64decode(pl), raw=False)
                    except Exception:  # noqa: BLE001
                        msg = base64.b64decode(pl)[:60]
                    return None, f'refused: {msg}'
                rid, url, info = seat_from_reply(pl, self.region)
                if url and rid == room_id:
                    return url, info
                if url:   # a late reply for an earlier request - still a valid seat, but not this one
                    return url, info
                return None, f'type {typ}: {json.dumps(info, default=str)[:200]}'
            self.page.wait_for_timeout(150)
        self.page.evaluate('()=>{window.__pending=Math.max(0,window.__pending-1)}')
        other = self.page.evaluate('()=>window.__other.splice(0)') or []
        return None, f'no reply in {wait_s}s; other msgs: {[(t, base64.b64decode(p)[:40]) for _, t, p in other][:5]}'


def _test(region='eu', n=3):
    import liveall
    ctx = liveall.guest_context()
    try:
        m = SeatMinter(ctx, region, liveall.new_tab)
        print('waiting for the client to connect its lobby...')
        if not m.ready():
            print('lobby not ready:', m.status()); return
        print('lobby ok:', m.status())
        rooms = [r for r in liveall.list_rooms(region) if not r['loggedOnly']]
        rooms.sort(key=lambda r: -r['players'])
        for r in rooms[:n]:
            t0 = time.time()
            url, info = m.mint(r['id'])
            print(f"  {r['id']} {r['mode']:6} {str(r['cname'] or r['map'])[:20]:20} {r['players']}p -> "
                  f"{'%.2fs' % (time.time() - t0)} {url or info}")
        print('blocked room sockets (should be []):', m.status().get('blocked'))
    finally:
        cdp._browser_call('Target.disposeBrowserContext', {'browserContextId': ctx})


if __name__ == '__main__':
    _test(*(sys.argv[1:2] or ['eu']), *(int(x) for x in sys.argv[2:3]))
