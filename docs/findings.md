# Findings - Kirka data sources, access, and bugs

Everything we discovered about Kirka's APIs and data. Deep route-by-route detail is in
`captures/kirkahub-online-analysis.md`; the full internal spec is `kirka-api/api2/docs-json-20261114.json`.

## Data sources

### Kirka Hub - `kirkahub.online/api` (our main source)
A community proxy of the official `api.kirka.io`, adds the API key server-side. **CORS open (`*`), no login.**
Browser-callable directly. Gives:
- `POST /api/user/getProfile` `{id, isShortId}` - profile: name, bio, role, KLO (all modes), level, totalXp, coins,
  diamonds, createdAt (account age), clan, active skins, and `stats` {games, wins, kills, deaths, headshots, scores}.
- `POST /api/inventory/user` `{id, isShortId}` - every item owned (type, rarity, salePrice, totalOwned, amount,
  market-listed, createdAt).
- `GET /api/inventory/items` - the full catalogue (~2,277 items) with **creator names**, totalOwned, renders.
- `POST /api/quests` `{type?}` - global active quests (hourly/daily/event).
- `GET /api/leaderboard/{solo|clan|ranked1V1|ranked2V2|rankedSAD}` - daily/ranked boards + remainingTime + rewards.
- `GET /api/clan/{name}` - description, Discord, allScores, monthScores, war position, and **members** with role,
  contribution, and **clan-join date** (`createdAt` per member, retroactive).
- `GET /api/prices`, `/data/hub_prices.json`, `/api/changelog` (value moves), `/api/bot-stats`.
- `GET /trade-api/trades.json` (open offers), `/trade-api/playerCount.json` (per-region online).

### api2.kirka.io - the internal API
336 routes, obfuscated paths + field names. **`GET /api/docs-json` is PUBLIC** = full Swagger with real operation
names (used to decode anything after a game update). Mostly **no CORS** (needs our server-side fetch or a proxy).
- Public, no login: match history (`/WwMWm/wWwWmMN`), ranked profile, skin textures/renders/3D
  (`/skin-render/{name}`, versioned), `/skin-art`, shop (`/WwMWnwNm/*`), crafting effects (`/wMNn/wnMN`), videos
  (`/wNwWmMn`), news (`/WnwmNw/WwnNmwW`), map images, leaderboards, twitch streams.
- Login (any account): quests, your inventory/notifications/daily-reward/battlepass, **community maps browse**
  (`/user-WwMWmw/wNnmM` - 48 player maps with thumbnail/author/plays/likes/join-date), community custom skins
  (per-creator), profile modes, trophies.
- KAT (staff only, 403 for us): create/edit quests, anti-cheat cases, game config, logs, play stats, API tokens.

### Live games - `https://<region>.kirka.io/matchmake/`
`GET`, **CORS open, no login**. Colyseus. Every open match per region (eu/na/sa/asia/oceania/india). Fields
obfuscated (decoded in `src/lib/games.ts`). Decoded room metadata (`WnWwwMm`), all read-only from the listing:
`wMNmWwW`=mode, `wWwWmMnN`=map, `wWnMNwWm`/`wWMwWmNn`=custom map name, `wWnWMm`=custom map id (links to its
community-map page/author), `wWMnw`=players, `wWnMNmwW`=max, `wWnWMw`=score/kill/round cap, `wWmW`=time limit (min),
`inRound___METADATA`=round in progress, `roundCreatedAt___METADATA`=round start epoch ms (-> live match timer),
`loggedOnly___METADATA`=login-only, `needLevel___METADATA`=min level, `wWMnWm`=team slots. Ranked = login+level
gated. Join link `kirka.io/games/<REGION>~<id>`.

**The live player roster is NOT in the listing** - only the count. The roster (names/scores) lives in the Colyseus
room **state** (MessagePack frames, per the network capture). Colyseus has no spectator API: reading it means
`POST /matchmake/joinById/<id>` + consuming the seat over the room websocket, which **joins the match** (our account
briefly appears in real players' games). Intrusive, dev-authorised (xip) but gated; not built. Non-intrusive
alternative for "who played": the match-history endpoint (`/WwMWm/wWwWmMN`, readable by shortId) gives *finished*-
match rosters.

> **OLD (2026-11-13/14):** the paragraph above: roster in "MessagePack frames", "Colyseus has no spectator API",
> reading it means `joinById` which joins the match as a player.
> **NEW (2026-11-15):** three corrections, all tested:
> 1. Kirka HAS a spectator mode (`SPECTATE`/`Watch` in the room browser). A spectator takes no player slot and can't
>    affect the match, so the roster can be read non-intrusively.
> 2. The roster is in the Colyseus **schema** state (`@colyseus/schema` v2, binary), not MessagePack. MessagePack is only
>    the op-13 message channel. `tools/colyseus.py` decodes both (see kirka-everything.md §4.3).
> 3. HTTP `joinById` is disabled (`{code:4210,"invalid method joinById"}`); seats come only from the authed lobby
>    websocket. Headless every-match sweep is PARKED by xip (2026-11-15). Full write-up: kirka-everything.md §4.8.
> **NEW (2026-11-15, later):** NOT parked — xip meant leave KAT (staff API, last priority), not the spectator sweep.

### Luke / KirkaTrades - `kirka.lukeskywalk.com`
Public, **no CORS** (fetch server-side). Prices, open trades, **completed-trade archive since 2023 (929 day-files,
`tradehistory/`)** - this is how we backfill trader history retroactively. Also skinVotes, playerCount, custom maps.

### Chat - `wss://chat.kirka.io`
Global chat, trade offers (type 13), the Pwnstar bot. Plain JSON. Used by the Live page.

### Auth - Xsolla OAuth
Kirka logs in via Xsolla. Token refresh: `POST https://login.xsolla.com/api/oauth2/token`, form body
`grant_type=refresh_token&client_id=303&redirect_uri=https://kirka.io&refresh_token=...` -> new access + refresh
token. `tools/auth.py` uses this to keep our stored login valid without a browser (token lasts ~24h, auto-refreshes).

## Field decoding (obfuscated -> readable)
Kirka obfuscates paths, field names, and enum values (`WwMWmn`=name, `WnWwwNmM`=id, etc.). We decode by matching live
responses + the `docs-json` spec. Maps live in the tool that uses them:
- Quests: task/reward/rarity/weapon codes - `tools/quests.py` (see also the `kirka-quests-api` memory).
- Shop: set/bundle/currency/card codes - `tools/shop.py`.
- Live games: room fields - `src/lib/games.ts`.
- Community maps: `tools/maps.py`. News: `tools/feeds.py`.
A game update can rename these; re-read `docs-json` to re-map.

## Bugs / issues found (to report to xip)
1. **Quest data bug** - non-weapon quests serialize their weapon field as the literal string `"undefined"` instead of
   null (5 quests at time of finding). A JS `undefined` leaking into the JSON from quest generation.
2. **Access control** - match history and ranked profile are readable with **no login and no API key**, by short id
   (returned full data unauthenticated). May be unintended.
3. **Info disclosure** - the internal API's full Swagger (`api2.kirka.io/api/docs-json`) is world-readable, exposing
   all 336 routes incl. the admin (KAT) route paths and schemas.

## Access we don't have
- **Past daily/ranked history** - the API only returns today's board; nobody public archives it, so old data isn't
  recoverable (our archive only grows forward). Past ranked seasons need a KAT role (403).
- **Enumerate all players** - no "list all users" endpoint; we reach players via leaderboards + clan rosters (which
  snowballs to cover the active/competitive population, not every dead account).
