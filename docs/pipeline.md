# Pipeline - capture tools, database, automation, deploy

## The tools (`tools/`)
All stdlib Python (urllib + sqlite3), so they run anywhere including the cloud.

| Tool | What it does | Needs login? | Output |
|---|---|---|---|
| `feeds.py` | players-online, news, votes, videos, crafting-effects | no | `public/online/news/votes/videos/effects.json` |
| `shop.py` | sets, bundles, currency, character cards (+ their characters) | no | `public/shop.json`, `kirka-api/shop.json`, `catalog.json` |
| `quests.py` | hourly/daily/event quests | yes (token) | `public/quests.json` |
| `maps.py` | community maps browse | yes (token) | `public/maps.json` |
| `scripts/build_creators.py` | creator names per skin | no | `public/data/creators.json` |
| `lb_archive.py` | top-20 solo + clan per day (history) | no | `public/lb-history.json` |
| `snapshot.py` | one compact snapshot of the whole day | no | `reports/snapshots/<date>.json` |
| `collect.py` + `statsdb.py` | the stats DB: players, clans, memberships, leaderboards, online | no | `kirka-api/kirka.db` |
| `traders.py` | top traders + trade history/profit/net worth; archives daily | no | `public/traders.json` + `kirka.db` |
| `auth.py` | stored login (Xsolla refresh), so token tools work without a browser | - | `kirka-api/auth.json` (gitignored) |
| `daily.py` | orchestrates all of the above + writes `reports/<date>.md` | - | the daily report |
| `cdp.py` | drives the debug Chrome over port 9222 (one-time login capture, etc.) | - | - |
| `room.py` | the live roster of a match room, by **spectating** it (no slot taken) + archives it | spectating client | `public/rooms/<TAG>.json` + `kirka.db` |
| `colyseus.py` | headless Colyseus decoder: msgpack (op-13 telemetry) + schema (full room state) | - | (library) |
| `specd.py` | spectate a room, capture its socket, **headless-decode** the full roster (team/health/score) | spectating client | `public/rooms/<TAG>.json` + `kirka.db` |
| `roomserver.py` | local HTTP bridge (:5191) for the site's **Request info** button: spectate+decode a room on demand | spectating client | JSON to the site |

Login-only tools (`quests`, `maps`) use `auth.py`: the token lives in `kirka-api/auth.json` and auto-refreshes via
Xsolla, so no browser is needed. One-time setup: `python tools/auth.py capture` (with the debug Chrome logged in).

## The stats database (`kirka-api/kirka.db`, SQLite)
Built by `collect.py` / `traders.py` via `statsdb.py`. Records daily state so any history can be derived.

| Table | One row per | Key columns |
|---|---|---|
| `players` | player | id, short_id, name, account_created, first_seen, last_seen, level, total_xp |
| `player_daily` | player per day | score, kills, deaths, wins, games, headshots, level, KLO (all modes), coins, diamonds, clan |
| `clans` | clan | id, name, created, discord, first_seen, last_seen |
| `clan_daily` | clan per day | all_scores, month_scores, war_position, member_count |
| `memberships` | player per day | clan_id, role, all_scores, month_scores, **joined** (clan-join date) |
| `leaderboard` | board/rank per day | date, board, rank, ref_id, name, score |
| `online` | timestamp | eu, na, sa, asia, oce, india |
| `events` | derived event | date, player, type (join_clan/leave_clan/role_change), clan |
| `trader_daily` | trader per day | tag, short_id, trades, volume, profit, net_worth, items, level, clan |
| `match_roster` | player per room capture | captured_at, room, region, map, short_id, name, rank, kills, deaths, score, side, is_bot |
| `meta` | key | last_collect_date, last_traders_date, etc. |

**Deltas give everything:** a player's `player_daily` row today minus yesterday = that day's score/kills/wins; sums
give weekly/monthly/all-time. Membership diffs give join/leave/role events with dates. Registry (players+clans) grows
each run (clan rosters + leaderboards), so coverage widens daily. Profile snapshots are budgeted (~250/run) and
round-robin to stay polite.

## Automation
`daily.py` runs every step, with retries, archives first (the irreplaceable leaderboard data needs no login), writes
the report + snapshot, logs to `reports/run-log.txt` + `last-success.txt`, and flags any missed days.

**On the PC:** Windows Task `KirkaDailyReport` (`tools/install_daily_task.ps1`) - every 3h, StartWhenAvailable
(catches missed runs), WakeToRun (from sleep), restarts 3x. Idempotent (one snapshot per day).

**In the cloud:** GitHub Actions `.github/workflows/kirka-daily.yml` in the `kirka-data` repo - every 6h, 24/7, no PC
needed. Commits `reports/`, `public/*.json`, and `kirka.db` back to the repo. Public data needs no secret; quests +
maps use the optional `KIRKA_REFRESH` repo secret (the refresh token). `auth.json` and `catalog.json` are never
committed.

## Deploy (GitHub)
Cloud repo: `github.com/omyxheru/kirka-data` (local clone `Desktop/kirka-data`). It's a **minimal** repo - just the
capture tools + data + workflow, not the whole project. To update it: edit tools in `Desktop/kirka/tools`, copy the
changed ones into `kirka-data/tools`, `git add -A`, commit, `git pull --no-rebase -X ours --no-edit`, `git push`.
Never commit `auth.json`. See `CLOUD-SETUP.md` for first-time setup.

## Refreshing by hand
`npm run` scripts in `skin-library/`: `creators`, `feeds`, `shop`, `quests`, `maps`, `archive`, `traders`,
`data:live` (creators+feeds+shop). Or `python tools/daily.py` for the full job. `python tools/auth.py status` to
check the login.

## Live all-rooms roster — `tools/liveall.py` (added 2026-11-15)
The "guest army": 6 guest tabs (one per region, `localStorage.region` preset) mint spectator seats; one holder tab
on `kirka.io/ads.txt` holds every room socket; `tools/colyseus.py` decodes state + patches live. Writes
`skin-library/public/rooms/live.json` every 2 s and archives each room to `kirka.db` `match_roster` once a minute.
Local only (needs debug Chrome on 9222). Full build log: kirka-everything.md §16.
