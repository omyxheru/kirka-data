"""Start our own headless Chrome for the live-room tools (cloud runner or a PC without the debug browser open).

Plain headless Chrome with a throwaway profile - the real Kirka client runs in it as-is. Nothing is spoofed or
hidden (no stealth patches, no faked user agent): if Kirka ever refuses headless Chrome, we stop and ask xip.

  import chrome; chrome.start()          # sets cdp.PORT to the new browser
  KIRKA_CDP_PORT=9333                    # port (default 9333 so it never clashes with the user's debug Chrome 9222)
  CHROME_BIN=/path/to/chrome             # override the binary
"""
import atexit
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

import cdp

CANDIDATES = [
    'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
]


def find():
    if os.environ.get('CHROME_BIN'):
        return os.environ['CHROME_BIN']
    for c in CANDIDATES:
        p = shutil.which(c) or (c if os.path.isfile(c) else None)
        if p:
            return p
    raise SystemExit('Chrome not found - set CHROME_BIN')


def start(port=None):
    port = int(port or os.environ.get('KIRKA_CDP_PORT', 9333))
    prof = tempfile.mkdtemp(prefix='kirka-chrome-')
    args = [find(), '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={prof}',
            '--no-first-run', '--no-default-browser-check', '--mute-audio', '--disable-gpu',
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows', '--window-size=1280,800', 'about:blank']
    if os.name != 'nt' and hasattr(os, 'geteuid') and os.geteuid() == 0:
        args.insert(1, '--no-sandbox')   # root in a container
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _stop():
        try:
            proc.terminate(); proc.wait(5)
        except Exception:  # noqa: BLE001
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)
    atexit.register(_stop)
    for _ in range(60):
        try:
            v = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2))
            cdp.PORT = port
            print(f'headless Chrome up on :{port} ({v.get("Browser")})')
            return proc
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise SystemExit('headless Chrome did not start')
