"""Your Kirka login, stored on this PC, so the data tools work without the browser open.

  python tools/auth.py capture   one-time: copy your login from the logged-in debug Chrome into kirka-api/auth.json
  python tools/auth.py token     print a valid access token (refreshes it if it has expired)
  python tools/auth.py status    show whose login it is and when it expires

How it stays valid: Kirka logs in through Xsolla. The stored refresh token is exchanged at
https://login.xsolla.com/api/oauth2/token for a new access token whenever the old one is near expiry; the rotated
pair is written back to auth.json. The file holds your token and refresh token in plain JSON - keep it on your PC.
If the debug Chrome is open, a refresh also syncs it so its session stays valid too.
"""
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUTH = ROOT / 'kirka-api' / 'auth.json'
XSOLLA = 'https://login.xsolla.com/api/oauth2/token'
CLIENT_ID = '303'                 # Kirka's Xsolla client id (from the game bundle)


def _payload(tok):
    try:
        return json.loads(base64.urlsafe_b64decode(tok.split('.')[1] + '=='))
    except Exception:  # noqa: BLE001
        return {}


def _refresh(refresh_token):
    body = urllib.parse.urlencode({'grant_type': 'refresh_token', 'client_id': CLIENT_ID,
                                   'redirect_uri': 'https://kirka.io', 'refresh_token': refresh_token}).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        XSOLLA, data=body, headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Mozilla/5.0'}), timeout=20)
    res = json.loads(r.read())
    return res['access_token'], res.get('refresh_token', refresh_token)


def _save(token, refresh_token):
    AUTH.parent.mkdir(exist_ok=True)
    AUTH.write_text(json.dumps({'token': token, 'refresh_token': refresh_token}), encoding='utf-8')
    _sync_chrome(token, refresh_token)


def _sync_chrome(token, refresh_token):
    """keep the debug Chrome (if open) on the same token so its session doesn't go stale"""
    try:
        sys.path.insert(0, str(ROOT / 'tools'))
        from cdp import kirka_page
        p = kirka_page()
        p.evaluate(f"(() => {{ localStorage.setItem('token', {json.dumps(token)}); localStorage.setItem('refresh_token', {json.dumps(refresh_token)}); return 1 }})()")
        p.close()
    except Exception:  # noqa: BLE001
        pass


def get_token():
    """a valid access token from the stored login, refreshing if it is within 5 minutes of expiry.
    Returns None if there's no stored login yet (run `python tools/auth.py capture`).
    In the cloud (no file) it reads the refresh token from the KIRKA_REFRESH env var / GitHub secret."""
    import os
    if not AUTH.exists():
        env_rt = os.environ.get('KIRKA_REFRESH')
        if env_rt:
            try:
                token, _ = _refresh(env_rt)
                return token
            except Exception:  # noqa: BLE001
                return None
        return None
    a = json.loads(AUTH.read_text(encoding='utf-8'))
    exp = _payload(a['token']).get('exp', 0)
    if exp - time.time() > 300:
        return a['token']
    try:
        token, refresh_token = _refresh(a['refresh_token'])
        _save(token, refresh_token)
        return token
    except Exception as e:  # noqa: BLE001
        print('token refresh failed:', e, file=sys.stderr)
        return a['token']        # stale, but let the caller try it


def capture():
    """one-time: read the login out of the logged-in debug Chrome"""
    sys.path.insert(0, str(ROOT / 'tools'))
    from cdp import kirka_page
    p = kirka_page()
    tok = p.evaluate("localStorage.getItem('token')")
    rt = p.evaluate("localStorage.getItem('refresh_token')")
    p.close()
    if not tok or not rt:
        print('no login found in the debug Chrome - log in to Kirka there first')
        return
    AUTH.parent.mkdir(exist_ok=True)
    AUTH.write_text(json.dumps({'token': tok, 'refresh_token': rt}), encoding='utf-8')
    print('saved', AUTH)
    status()


def status():
    if not AUTH.exists():
        print('no stored login. Run: python tools/auth.py capture (with the debug Chrome logged in)')
        return
    p = _payload(json.loads(AUTH.read_text(encoding='utf-8'))['token'])
    left = int(p.get('exp', 0) - time.time())
    print(f"login: {p.get('email', '?')}  expires in {left // 60} min" + (' (will auto-refresh)' if left < 3600 else ''))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'capture':
        capture()
    elif cmd == 'token':
        print(get_token() or '')
    else:
        status()
