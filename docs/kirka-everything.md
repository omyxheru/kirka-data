# Kirka.io — EVERYTHING we found (the full reference)

The complete, no-detail-omitted record of every Kirka data source, API, socket, protocol, field, bug, access level
and tool we discovered. Companion to the focused docs ([findings](findings.md), [pipeline](pipeline.md),
[website](website.md)); this file is the deep dump. Game version **0.44.x** (checked through 2026-11-15). Kirka
obfuscates paths, JSON field names and enum values; a game update can rename them (re-read `api2 /api/docs-json` and
the socket reflection to re-map).

Raw captures referenced here:
- `captures/kirkahub-online-analysis.md` — route-by-route Kirka Hub + api2 analysis.
- `captures/network-20261113/NOTES.md` — passive client network map (REST + lobby socket + chat).
- `captures/ws-spectate/NOTES.md` + `session.json` — a full spectator socket capture (handshake + state + ticks).
- `kirka-api/api2/docs-json-20261114.json` — the internal API's full 336-route Swagger.
- `tools/colyseus.py` — the working headless Colyseus decoder (schema + msgpack).

---

## 0. The map at a glance

| Host | Transport | Auth | What |
|---|---|---|---|
| `kirkahub.online/api` | HTTPS, **CORS \*** | none | community proxy of `api.kirka.io`; profiles, inventory, clans, leaderboards, quests, prices, trades |
| `api2.kirka.io/api` | HTTPS, mostly no CORS | mixed | the internal API (obfuscated); `docs-json` is public |
| `<region>.kirka.io/matchmake/` | HTTPS, **CORS \*** | none | Colyseus room listing (open matches per region) |
| `wss://<region>.kirka.io/<proc>/<room>` | WebSocket | session | **the live game room** (Colyseus): full roster + telemetry |
| `kirka.lukeskywalk.com` | HTTPS, no CORS | none | prices, trades, 2023+ trade archive, maps, votes |
| `wss://chat.kirka.io` | WebSocket | none | global chat + trade offers + Pwnstar bot |
| `login.xsolla.com/api/oauth2/token` | HTTPS | refresh token | token refresh (Kirka logs in via Xsolla) |

Regions: `eu, na, sa, asia, oceania, india` (hosts `<region>.kirka.io`).

---

## 1. Kirka Hub — `kirkahub.online/api` (our main REST source)
Community proxy that injects the API key server-side. **CORS open (`*`), no login**, browser-callable.

- `POST /api/user/getProfile` `{id, isShortId}` → name, bio, role, **KLO per mode**, level, totalXp, coins, diamonds,
  `createdAt` (account age), clan, active skins, `stats` {games, wins, kills, deaths, headshots, scores}.
- `POST /api/inventory/user` `{id, isShortId}` → every item owned (type, rarity, salePrice, totalOwned, amount,
  market-listed, createdAt).
- `GET /api/inventory/items` → full catalogue (~2,277 items) with **creator names**, totalOwned, renders.
- `POST /api/quests` `{type?}` → global active quests (hourly/daily/event). **Bug:** non-weapon quests serialize the
  weapon field as the literal string `"undefined"`.
- `GET /api/leaderboard/{solo|clan|ranked1V1|ranked2V2|rankedSAD}` → daily/ranked boards + remainingTime + rewards.
- `GET /api/clan/{name}` → description, Discord, allScores, monthScores, war position, and **members** with role,
  contribution and **clan-join date** (`createdAt` per member — retroactive history anchor).
- `GET /api/prices`, `/data/hub_prices.json`, `/api/changelog` (value moves), `/api/bot-stats`.
- `GET /trade-api/trades.json` (open offers), `/trade-api/playerCount.json` (per-region online).

## 2. api2.kirka.io — the internal API
336 routes, obfuscated paths AND field names (`WwMWmn`=name, `WnWwwNmM`=id, …). **`GET /api/docs-json` is PUBLIC** =
full Swagger with real operation names (decode anything after an update). Mostly **no CORS** (fetch server-side).
- **Public, no login:** match history (`/WwMWm/wWwWmMN`), ranked profile, skin textures/renders/3D
  (`/skin-render/{name}`), `/skin-art`, shop (`/WwMWnwNm/*`), crafting effects (`/wMNn/wnMN`), videos (`/wNwWmMn`),
  news (`/WnwmNw/WwnNmwW`), map images (`/map-image/<Map>/{full|mini}/v<ver>.webp`), leaderboards, twitch streams.
- **Login (any account):** quests, inventory/notifications/daily-reward/battlepass, **community maps browse**
  (`/user-WwMWmw/wNnmM`), community custom skins, profile modes, trophies.
- **KAT (staff only, 403 for us):** create/edit quests, anti-cheat cases, config, logs, play stats, API tokens.
- Other REST seen on the live client: `/api/WnwmNw/WwnNmwW` (version+news), `/api/WwMWm` (your profile),
  `/api/WwMWm/wmWMwnNW` (pass tiers), `/api/wnMmwNW/wNnmWM` (level reward table), `/api/wnMmwNW` (pending rewards),
  `/api/wNnWmM` (quests of a type), `/api/skin-art`, `/api/layout/state`, `/api/kat-wwMNmn/WnWw` (your role/powers),
  `/api/kat-wwMNmn/wNnWmwWM` (chat roles + SVG badges).

**OPEN (no-auth) per-player endpoints — the big untapped data ("the lot lot more", decoded from docs-json 2026-11-15):**
- `POST /api/WwMWm/wmMwWn` = **getUserProfile** (profile by id — open).
- `POST /api/WwMWm/wWwWmMN` = **getMatchHistory** (a player's recent matches, by shortId — open).
- `POST /api/WwMWm/wWNwMn` = **getRankedProfile** (ranked ELO / rank / category standing — open).
- `GET  /api/WwMWm/wmWMnwNW` = **getProfileModes** (per-mode stat breakdown).
- `POST /api/WwMWm/wNmWnw` = **getUserTrophy** (trophies / achievements).
- `POST /api/wMWnwNmW/WwMWnmN` = **getItemByName**; `GET /api/wMWnwNmW/getAllItems_<uuid|codename>` = item catalogue;
  `POST /api/wMWnwNmW/get_<uuid|codename>` = **getInventoryPublic** (anyone's inventory by id). These inventory/item
  paths **rotate** (codenames like `sheriff`, `irrvlo`, plus UUIDs) as light anti-scrape - re-read docs-json for the
  current variant.
- `GET  /api/wwnmWMW/{name}` = **getParticularClan**; `GET /api/wmWMnN/*` = all leaderboards OPEN (solo, ranked
  categories `wWmNWnwM/wWmNWnM/wWmNWnMw/wWmMwWnN`, active categories `wWMwWnmN`, clan championship `wWMWmnN`).
- Device/anon identity: `POST /api/WwMWm/wWNwMWnm` setTrackToken, `POST /api/WwMWm/wWNwWn` getTrackToken.
- **KAT-only (staff, 403):** `KatController_*` searchUser, getItemsByUserId, add/deleteItems, setUserRole,
  **changeUserCurrency**, getLogs, **getRankedSeasons** (past seasons), inspector reports — the surface xip could grant.

**DIG ROUND 2 (2026-11-15) — xip: "there are still a lot of endpoints we didn't even know about, dig more."**
Full table of all 336 routes + all 103 request-body formats: [api2-routes-20261115.md](api2-routes-20261115.md)
(generator `tools/api2_routes.py`; spec saved `kirka-api/api2/docs-json-20261115.json`). docs-json on 11-15 is
**identical to 11-14** (same 336 routes, no renames). Coverage before this round: only 126/336 ever probed; KAT
(staff, 135 routes) is set aside per xip. Of the 201 non-KAT routes, these were **undocumented until now**:
*(xip's exact priority: staff/KAT is the LAST priority, build everything else first.)*
- **`POST /api/WwnNmwWM/wwnmWWNM` = `createGuest`** (no auth in spec) — the guest-account mint the guest note below
  was missing. Not called yet.
- **Replay system disguised as "layout"** (ReplayController/ReplayAdminController): `GET /api/layout/state` (public
  config), `POST /api/layout/open` (start replay, `StartReplayDto`), `POST /api/layout/{id}/parts/{sequence}` (upload
  chunk, `ReplayChunkDto`), admin `GET /api/layout/sheets/list|{id}|{id}/parts/{seq}` (401). The client records and
  uploads match replays. `POST /api/layout/tiles/{id}` = CaptureController (screen capture upload).
- **Moderation cases** `/api/moderation/cases[/{id}|/{id}/screenshot|/bans|/settings|/replay-settings]` (401, staff)
  and **inspector** `/api/inspector/reports|tagged` (401) — anti-cheat review. Documented only; not ours to touch.
- **Room bans** `/api/WwwmnMW/WwnNwW|WnwmwM|wwnmMWN` (list/ban/unban, auth).
- **Players (login):** `GET /api/user-WwMWmw/wmwNnWWM/{shortId}` maps by creator, `GET /api/user-wwMNWmn/wmwNnWWM/{shortId}`
  custom skins by creator, `GET /api/user-WwMWmw/wMNwWWm/{id}` map comments, `GET /api/user-wwMNWmn/wMWwmn` checkName.
- **Open, never probed:** `getNewRankedCategories` (`/api/wmWMnN/wMWwnm`), `getCharacterCards`
  (`/api/WwMWnwNm/wwnmWNMW`), `getBundles`, `getCurrency`, `getAdGuest` (`GET /api/wnMmwNW/WnWmwwMN`),
  `/api/special-image/{file}`, `/api/mode-thumb/{id}[/{kind}]`, `/api/news-image/v{version}`.
- **Friends** offer/accept/cancel, **Twitch** link/entitlements, **battlepass** claim, **notifications** — account
  actions, documented only.
- Key body formats: `GetMatchHistoryDto {WnWwwNmM:id, wMWnwm:bool(isShortId?), wMNmWWwn:number(page/limit?)}`,
  `UserItemIdDto {WnWwwNmM}`, `OfferFriendshipDto {wnMmwWN}`, `UserIdDto {wNnWmw}`.
Next: probe the open no-auth GETs read-only, results appended below as found.

**Probe results (2026-11-15, plain GET, no auth; raw responses in `kirka-api/api2/probe-20261115/`):**
- `GET /api/WwMWnwNm/wmMwW` **getCurrency** → `{wwMnN:[packs]}`: coin/diamond packs, each `WnWwwNmM` id,
  `WwMWmn` label ("375 000"), `wwMNnWm` price in diamonds (30), `wMNnW` amount (375000), `wMwW` icon file,
  `wMWwnNW` currency code (`wMNmW` = coins). Packs: 375k=30, 1M=80, 2.5M=200, 8.125M=650, …
- `GET /api/WwMWnwNm/wnMNmWwW` **getBundles** → 5 bundles (e.g. "Autumn", start `wmwNnWMW` 2026-11-01, end
  `wNwWmnMW` 2026-11-17), each with `wmnWNMwW` = items: `WwMWnmN` item {id, name, `wNmMnW` rarity code}, `wNmMn`
  qty, `WwMWmwn` type (CHARACTER…), `wwMNnWm` price. → **bundle schedule + prices, archivable daily.**
- `GET /api/WwMWnwNm/wwnmWNMW` **getCharacterCards** → `{wwnmWNM:[cards]}`: name ("Scary"), price 499, card colours
  (`wmMwWnWN` hex, `wNwWmnWM` CSS gradient), `wMWwnWmN` = the **drop pool** (character name + rarity code). →
  **what each card can roll.**
- `GET /api/WwMWm/wmWMnwNW` **getProfileModes** → 3 modes (DM, TDM, POINT): id/name, `wMNmWWwn` order, `wmWnNMwW`
  enabled, `WwwmnWNM` (0/5/10, unknown — min level?), `wmwNnWMW` created date.
- `GET /api/wMNn/wnMN` **getEffects** → 16 crafting effects with **real field names** (not obfuscated): name,
  displayName, description, rarity, **`shaderCode` (GLSL fragment source)**, isAnimated.
- `GET /api/layout/state` → `{"ready":false}` — the replay recorder is **currently switched off** server-side.
- `GET /api/wmWMnN/wMWwnm` getNewRankedCategories → `[]`; `GET /api/wmWMnN/wWMwWnmN` getActiveRankedCategories →
  `[]` — **no ranked category active right now** (between seasons?).
- `GET /api/wnMmwNW/WnWmwwMN` getAdGuest → 200, empty body (no ad reward for guests at the moment).

**Per-player open endpoints — real responses decoded (2026-11-15, test player = solo-leaderboard #1, read-only
POSTs, raw in `kirka-api/api2/probe-20261115/`).** All work with **no login, no key**. The id body is
`{WnWwwNmM: <uuid or shortId>, wMWnwm: <true if shortId>}` (+ `wMNmWWwn` where noted).
- `POST /api/WwMWm/wmMwWn` **getUserProfile** → `WnWwwNmM` uuid, `wnMmwWN` **shortId**, `WwMWmn` name, `WmMnwNw` bio,
  `WwMWmnwN` role code, `WmMnwNwW` ranked rating, `wmWMnNWw`, `wNmMnWwW`/`wNmMnWw`/`wNmMWwnW` (ratings, unknown which),
  `wwMnNWW` level, `wnMwmN` total XP, `wWMwWmN`/`wWMwWm` (XP into level / XP for level?), `wwMnN` coins?,
  `wMNmWWnw` diamonds?, `wmwNnWMW` **account created**, `WwMWmnw` **clan**, `wWMnWNw` equipped weapon skin
  (item + parent weapon), `wWnWNmMw` equipped character, `wwMNnWmW` **lifetime stats** {`wwMnNmW` games,
  `WwMWmwnN` wins, `wwMnNm` kills, `wNmWnM` deaths, `wmwNW` headshots, `wNmWnwMW` score}.
- `POST /api/WwMWm/wWwWmMN` **getMatchHistory** — **`wMNmWWwn` is the RANKED CATEGORY, not a page.** Returns the
  player's **complete** ranked match list for that category (count always equals the ranked-profile games total;
  323 entries seen for one category, back to 2026-09-21). Entry = `WnWwwNmM` match id, `wNmWnwWM` **won (1/0)**,
  `wwMnNm` kills, `wNmWnM` deaths, `wNmWnwMW` score, `WmMnwN` **map**, `WmMnwNwW` 0–1 float (unknown — rating
  change factor / performance?), `wmwNnWMW` date. **No other players in the entry** — it is the player's own line
  only; no non-KAT route fetches a match by id, so the per-match roster is NOT available here.
- `POST /api/WwMWm/wWNwMn` **getRankedProfile** (same body, `wMNmWWwn` = category) → name, shortId, level, rating
  `WmMnwNwW`, and `wwMNnWmW` per-category stats {`wNmWnwW` games, `WmMnwwNW` wins, `WmMnwNwW` losses, `wwMnNm`
  kills, `wNmWnM` deaths, `wNmWnwMW` score, `wmwNW` headshots, `wnMmwNWW` ?, `WnWwwNm` K/D string}.
- Categories seen for the test player: 0 → 150 games, 1 → 175, 2 → 0, 3 → 0, 4 → 23, 5 → 10, 6 → 323 (323 wins,
  0 losses, K/D 18.88 — looks like a vs-bots or event category). Mapping category id → 1v1/2v2/SAD/POINT2V2 not
  pinned yet (the leaderboards name 4 categories: `wWmNWnM` 1V1, `wWmNWnMw` 2V2, `wWmNWnwM` SAD, `wWmMwWnN`
  POINT2V2).
- `POST /api/WwMWm/wNmWnw` **getUserTrophy** → `[]` for this player (no trophies, or trophies not live).
- Leaderboard entries carry the player uuid (`wNnWmw`), so **leaderboard → uuid → profile + full ranked history**
  works end to end with no login: a full ranked-player history crawler is possible (keep it rate-limited).

**Guest / anonymous account (xip's hint: "logged-out we can still get quests"):** the client's **Guest Login**
(`guest-login-btn`, `onGuestLoginClick`) mints a **`guestToken`** with no credentials, sent as header
**`x-guest-wwMNm`**. A guest is a throwaway real account: it reaches the login-only endpoints (quests, maps,
inventory) and almost certainly opens game sockets - so the pipeline can run **anonymously, no real login**, minting
fresh guests at will. Exact mint request is behind obfuscated accessors; capture it once from a logged-out client
(Guest Login with CDP Network recording) to lock the URL + body. Crazygames embeds defer to Crazygames auth instead.

## 3. The matchmake room listing — `GET https://<region>.kirka.io/matchmake/`
`GET`, **CORS open, no login**. Colyseus. Returns an array of open rooms. Fields obfuscated; decoded in
`src/lib/games.ts`. The room metadata object is `room.WnWwwMm`. **Decoded metadata keys (all read-only):**

| key | meaning |
|---|---|
| `room.name` | mode name (`DM`,`TDM`,`TKO`,`POINT`,`PAR`,`PHY`,`RWP`,`ME`,`1V1`,`POINT2V2`,`LobbyRoom`,…) |
| `room.WWMNmww` | room id (used in the join URL `kirka.io/games/<REGION>~<id>`) |
| `room.WmwNWnwM` | process id (server process) |
| `room.WWMNmwwn` | locked/private (boolean) |
| `WnWwwMm.wMNmWwW` | canonical mode (`DM`/`TDM`/`PAR`/`RSAD`=ranked SAD/`PHY`/`POINT`/`TKO`/`RWP`) |
| `WnWwwMm.wWwWmMnN` | map name (`"Custom"` for a community map) |
| `WnWwwMm.wWnMNwWm` / `wWMwWmNn` | custom map display name |
| `WnWwwMm.wWnWMm` | custom map id (links to its community-map page/author) |
| `WnWwwMm.wWMnw` | current players |
| `WnWwwMm.wWnMNmwW` | max players |
| `WnWwwMm.wWnWMw` | score / kill / round cap (16 DM, 4 ranked, custom caps) |
| `WnWwwMm.wWmW` | time limit (minutes; 30 standard, 60 ranked) |
| `WnWwwMm.inRound___METADATA` | a round is in progress (boolean) |
| `WnWwwMm.roundCreatedAt___METADATA` | round start epoch ms → **live match timer** |
| `WnWwwMm.loggedOnly___METADATA` | login-only room |
| `WnWwwMm.needLevel___METADATA` | minimum account level |
| `WnWwwMm.wWMnWm` | team slots in use (`[1,2,3,4]` FFA / `[2,4]` two-team) |
| `WnWwwMm.wWwWmMn` | allowed weapon skins list |
| `WnWwwMm.wmMNwWnW` | per-weapon loadout / headshot limits |

**The listing gives only the player COUNT, never the roster.** The roster is in the socket state (§4).
Other matchmake endpoints: `GET /matchmake/` (the listing), `GET /matchmake/rooms` (returns `[]`),
`POST /matchmake/joinById/<roomId>` (seat reservation; **CORS \*, OPTIONS/POST/GET**), `GET /matchmake/ping`.

> **OLD (2026-11-15, morning):** `joinById` above was read from the bundle/CORS preflight and assumed to work as
> a plain HTTP seat reservation.
> **NEW (2026-11-15, tested):** Kirka has **disabled the HTTP matchmake methods**. `POST /matchmake/joinById/<id>`
> returns `{"code":4210,"error":"invalid method joinById"}`. Seats are reserved only over the logged-in lobby
> websocket. Full details in §4.8.

---

## 4. THE LIVE GAME SOCKET — Colyseus (the big one)
This is where "who's playing" + all live telemetry lives. **No public archive of it exists; we capture it ourselves.**

### 4.1 Connection flow
1. Reserve a seat: `POST https://<region>.kirka.io/matchmake/joinById/<roomId>` (+ a spectator option) → a seat
   reservation `{sessionId, room:{processId, roomId, …}}`.
2. Connect: `wss://<region>.kirka.io/<processId>/<roomId>?WmwNWnMw=<sessionId>`  (the session-key query param is
   `WmwNWnMw`). Example captured: `wss://eu.kirka.io/dlGhJ2B1Y/lPaAAtl17?WmwNWnMw=s80405idJ`.
3. The server streams Colyseus frames. **Spectating takes no player slot and cannot affect the match**
   ("Spectators can't play the match anymore", "Permanent spectator; irreversible").

> **OLD (2026-11-15):** step 1 above (HTTP `joinById` → seat reservation).
> **NEW (2026-11-15, tested):** step 1 does NOT work over HTTP anymore (error 4210). The real flow is in §4.8:
> the seat comes from the authed lobby websocket, and the game-socket roomId can differ from the listed room id.
> Steps 2 and 3 are still correct (captured from the real client).

### 4.8 Headless "every match" sweep — what we tried and where it stopped (2026-11-15)
Goal (xip asked for it for every match): a tool with no browser that spectates every open room per region and
archives the roster. Tool: `tools/specsweep.py` (has the ws connect + decode + reserve scaffold and a `--test` debug
mode). Also `tools/specd.py` and `tools/room.py` (earlier scaffolds).

**What works:**
- `tools/colyseus.py` decodes everything offline (validated against `captures/ws-spectate/session.json`): full roster
  (name, shortId, team, role, skin, health, score, kills/deaths, live position) + every op-13 MessagePack message.
- Game sockets **do connect** headlessly. The websocket itself is not the blocker.

**What blocks it (the anti-bot wall):**
1. HTTP matchmake is off: `POST /matchmake/joinById/<id>` → `{code:4210, "invalid method joinById"}`.
2. Connecting with a random/made-up sessionId → opcode-11 ERROR `"seat reservation expired."` A real seat
   reservation is required.
3. Reservations happen **only over the authed lobby websocket** (`POST /matchmake/create/LobbyRoom` + JWT, then the
   lobby wss). Kirka's matchmaker there is custom and obfuscated. Lobby op-13 **type 102 = room info**. The exact
   reserve request → sessionId reply has NOT been pinned yet.
4. The listed room id can differ from the real game-socket roomId; both + the sessionId come from the lobby exchange.
   Game ws = `wss://<region>.kirka.io/<processId = room.WmwNWnwM>/<realRoomId>?WmwNWnMw=<sessionId>`, then send
   opcode-10 ack to get state.

**What it would take:** a headless lobby client (auth with our token or a guest token, see §guest) that speaks the
lobby reserve protocol. Big reverse-engineering job.
**Alternative considered:** a real headless browser cycling rooms (reuses the DOM scrape; robust but heavy, one PC,
not parallel).
**Rule we kept:** don't sweep/join all rooms continuously even as spectator; keep it on demand.

**STATUS — PARKED (2026-11-15):** xip said leave this for now. Nothing deleted; resume from step 3 above if it
comes back.

> **OLD:** "PARKED — xip said leave this for now" (a misread).
> **NEW:** **CORRECTION (2026-11-15, later, from xip via the user):** xip said leave **KAT** (the staff/admin API) for now — KAT is our LAST priority, build other
> stuff first. The spectator sweep is **NOT parked**; it stays on the list.

### 4.2 Frame format
Each WebSocket binary frame = **1 opcode byte + payload**.

| opcode | name | payload |
|---|---|---|
| `10` | JOIN_ROOM | `[10, len, "schema", <reflection>]` — the serializer id `"schema"` + the **reflection** (full self-describing schema definition) |
| `12` | LEAVE_ROOM | — |
| `13` | ROOM_DATA | `[13, type, <MessagePack>]` — room.send messages (live telemetry; **plain MessagePack**) |
| `14` | ROOM_STATE | `[14, <schema-encoded full state>]` — the full initial state (the roster lives here) |
| `15` | ROOM_STATE_PATCH | incremental schema-encoded state changes |
| client→server | `10` (join ack), `13` messages (e.g. type 35 = a client fingerprint blob) |

### 4.3 The schema wire format (how `tools/colyseus.py` decodes state)
`@colyseus/schema` v2, reflection-driven. **This Kirka build's quirks (verified against the capture):**
- `ReflectionType = {id, fields}` — **no `extendsId` field** (differs from upstream master).
- **Strings**: length is a fixstr marker `0xA0 | len` for len<32, else `0xD9`(uint8)/`0xDA`(uint16 LE)/`0xDB`(uint32 LE),
  then `len` UTF-8 bytes.
- **Numbers**: little-endian, msgpack-style prefixes: `<0x80` fixint; `0xE0–0xFF` negative fixint (`p-256`); `0xCA`
  float32, `0xCB` float64, `0xCC` uint8, `0xCD` uint16, `0xCE` uint32, `0xCF` uint64, `0xD0` int8, `0xD1` int16,
  `0xD2` int32, `0xD3` int64.
- **Fixed-width** primitives (`int8/uint8/…/float32/float64/boolean`) have NO prefix byte (boolean = 1 byte >0).
- **Operations** (constants): `ADD=128`, `REPLACE=0`, `DELETE=64`, `DELETE_AND_ADD=192`, `CLEAR=10`, `REVERSE=15`,
  `MOVE=32`, `DELETE_BY_REFID=33`, `ADD_BY_REFID=129`, `SWITCH_TO_STRUCTURE=255`, `TYPE_ID=213`.
- **Schema field op**: `b = byte; operation=(b>>6)<<6; index = b % (operation||255)`; decode the value per the field's
  type from the reflection; for a child ref/collection the value is a `refId` (a number), and that structure's own
  ops arrive later after `SWITCH_TO_STRUCTURE(255)` + the refId.
- **Map op**: raw op byte, then `index`(number); on ADD, a `key`(string); value per child type.
- **Array op**: raw op byte (`10`=clear, `15`=reverse, `33`=delete-by-refid, `129`=add-by-refid, else `index`(number)),
  then value.
- **Reflection** = a normal state encoding whose root is the fixed `Reflection` schema
  (`Reflection{types:[ReflectionType], rootType:number}`, `ReflectionType{id, fields:[ReflectionField]}`,
  `ReflectionField{name:string, type:string, referencedType:number, childPrimitive:string, quantized:ref?}`).

`tools/colyseus.py` implements all of the above. Usage:
`types, root = colyseus.parse_reflection(join_frame)` → `state = colyseus.Decoder(types, root).decode(state_frame)` →
`colyseus.roster(state)`.

### 4.4 The decoded state schema (17 types; root = type 16 = GameState)
The game's state has **17 Schema types**. Key ones (full dump in the decoder test / `captures/ws-spectate`):

**Root — type 16 `GameState` (28 fields):** `state___SYNC`(string, game state), `wMNmWnW`/`wWnWMmNw`(strings),
`wWMwNWmn`/`wWMnwWNm`(uint16), `wWWwNMmn`(uint8), several booleans, `wWnMmW`(uint32), `wWwNnMWm`(uint8),
`wWWwnN`(uint32), **`wWwNn`**(map→type 11, often empty), `wWwNnMm`/`wmwnNMW`(map of string), `wmMNWWn`(string),
**`wMNWWnmw`(map→type 15 = THE PLAYERS)**, `wwMnWWN`(string), `wwMnNWm`(ref→type 6), `wWnWm`/`wWMnwWN`(ints),
`wWNwmMnW`(map of uint32).

**type 15 `Player` (62 fields)** — the full in-game player entity. **Confirmed field map:**

| key | meaning |
|---|---|
| `wwMnWmW` | **name** |
| `wMNWWm` | **short id** (empty for bots) |
| `wwMnWm` | **team** (`"blue"`/`"red"`; empty = FFA) |
| `wwMnWN` | **role** (`USER`, …) |
| `wNWWwMmn` | equipped **weapon skin** name |
| `WmwNWnMw` | **session id** |
| `WmwNWnw` | **health** (0 = dead) |
| `wNWWnMwm` | **shield/armor** |
| `wNWWnMm` | **score** |
| `wNWWnMmw` | **kills** |
| `wnMWWwN` | **deaths** |
| `WwMwnWN` | **position** `{WnWwwMNm:x, WnWwwM:y, WnWwwMN:z}` |
| `WwMwNmnW` | **rotation** `{x, y}` |
| `fillMoveX/Y___SYNC, fillRotX/Y___SYNC, fillCrouch/Scope___SYNC, fillWName___SYNC, tickFillCount___SYNC` | client input prediction (per-tick movement/aim/crouch/scope, current weapon name, tick counter) |
| `disconnected___SYNC` | disconnect flag |
| `wnMmWwNW`, `wmwnN` | arrays of type 0 (loadout/perk slots) |
| `wWNwmnW` | array of uint8 (ammo/state per slot) |
| `wMNmWwnW` | large float (≈210983) — likely a tick/time or distance accumulator |
| `wWMmnNW` | int (≈191) — unmapped |
| `wNWWwmMn` | uint16 — current weapon index (TKO ladder level in gungame) |
| `WwMwnW` | uint16 — unmapped (ping?) |
| remaining `w*` keys | physics/flags not yet labelled (velocity, fire state, booleans) — present in the decode, label as needed |

**type 1 `ScoreboardPlayer` (13 fields):** a lighter player record — `wwMnWmW`(name), `wMNWWm`(shortId),
`wwMnWN`(role), `wNWWwMmn`(skin), `WmwNWnMw`(sessionId), `wwMnWm`, `wNWWwmMn`/`WwMwnW`(uint16), `wnMmWwNW`(array→type 0),
plus booleans. **type 2** holds `wMNWWnmw`(map→type 1). **type 0 (9 fields):** a loadout/stat slot — `wwMnWmW`,
`WwMwnWNm`, `wWMwN` (strings), `wWMnWmN`/`wWMnWmwN`/`wWMnWmw` (numbers), booleans. Types 3–14 cover maps, weapons,
widgets, vectors, etc.

### 4.5 The op-13 MessagePack telemetry (the "missing a lot of things")
`op 13` messages are plain MessagePack. `raw[1]` = message type; `raw[2:]` = payload. **Decoded types:**

| type | payload | meaning |
|---|---|---|
| `28` (continuous) | `{wwMnmWW: sessionId, WmwN:[{WmwwMnWN:x, WmwwMnW:y, WmwwMn:z, WwMwNmn:rotX, WwMwNmWn:rotY, WmwNWn:?, WmwwMnNW:bool, WmwwMN:int, WmwNWwnM:bool}, …]}` | **live player movement** — positions + look angles per tick (the array is a batch of sub-ticks) |
| `29` | `{wMNmWnWw:[{wNWWnwMm: slot (BODY/Bayonet/SCAR/…), wwMnWW: skin name, wmMNn:bool, wWwNWnM:bool, …}, …]}` | **loadout / equipped skins** per player |
| `31` | `{WmwwM: sessionId, WmwwMWN:?, WmwwMNn: 90 (health?), WwMwN:1 (team?), WmwwMNWn:1}` | spawn / health / kill event |
| `3` | `"-15.5,-1.99,-14.5,0,3.48"` | spawn position string `x,y,z,rotX,rotY` |
| `67` | `{WmwNWn:1}` | counter event |
| `70` | `{wwMnmN:0}` | counter event |
| `22` | `"refactor"` | command/marker |
| `102` | `"wWnWMNwm"` | id/marker |
| `35` (client→server) | JSON string: `{userAgent, platform, language, hardwareConcurrency, screen, …}` | the client **fingerprint / integrity blob** the client posts |
| `0,1,23,24,69,81,116,123` | small ints / ext types | misc events (some use msgpack ext `0xD4` — not fully mapped) |

> **OLD:** type 31 = "spawn / health / kill event" (`WmwwMNn` = health?); 67/70 = counter events.
> **NEW (2026-11-15, verified offline 13/13 against the state patches):** **type 31 = HIT event** `{WmwwM: victim
> sessionId, WmwwMWN: attacker sessionId, WmwwMNn: damage, WwMwN: headshot 1/0, WmwwMNWn: killed 1/0}`, which
> arrives 1–5 frames before the patch. 67/70/24/22/69 are **client → server**. Type 0 = room settings, type 1 = full
> voxel map, 29 = our own loadout, 23 = room command list. Player `wNWWwmMn` = **account level**, `wNWWwMmn` =
> **held weapon** (not a skin), `wwMnWNW` = clan tag, `wnMmWwNW` = loadout with skin names. `tools/liveall.py`
> currently drops all op-13 frames (holder filter). Full write-up + feature list:
> [xip-more-ideas-20261115.md](xip-more-ideas-20261115.md).

### 4.6 The spectator mechanism (how we reach a room read-only)
- In the client: **SERVERS** panel → the server list (`.server` rows with `.map` = `MODE_Map`, `.session-id` =
  `REGION~id`, `.online` = `n/max`, a `.button.join`). Clicking a row (a **trusted** click; synthetic events are
  ignored by the Vue list) shows a `.preview` with a **`.spectate-btn`** ("SPECTATE"). Clicking it enters the
  spectator stream (no player slot). Ranked rows have class `is-ranked`.
- In the spectator stream the scoreboard DOM renders as `.player-list > .player-cont > (.player-left: .key rank,
  .nickname name, .short-id #tag) + (.player-right: three .player-value = kills, deaths, score)`. A player with no
  `.short-id` is a bot. **Ranked rooms hide short-ids** (`#HIDDEN`).
- Spectator camera settings in the client: `SPECTATOR_FLY/NEXT/PREV/TPS___SETTING` (fly, next/prev target, third-person).

### 4.7 Lua map-scripting player API (what the engine exposes to maps — reference, not ours to call)
The bundle's scripting docs expose per-player fields/events, useful for naming state fields:
`IsSpectator, IsTempSpectator, IsBot, IsAlive, IsHidden, IsHost, IsMoving, IsZombie, Team, Name, JoinedAgo`,
damage dealt/received, `SetSpectator(on[, permanent])`, events `p.Spawned/Damaged/Died/Chatted/Jumped/Suicide`,
`Players.OnDamage`, kill/hit application, team scores, widgets (12 per player), spawn points, bot skill tiers
(`CASUAL/AVERAGE/GOOD/SKILLED/EXPERT/PRO/GOD`).

---

## 5. Luke / KirkaTrades — `kirka.lukeskywalk.com`
Public, **no CORS** (fetch server-side). Prices, open trades, **completed-trade archive since 2023 (929+ day files,
`tradehistory/`)** — backfills trader history retroactively. Also `skinVotes`, `playerCount`, custom maps.

## 6. Chat — `wss://chat.kirka.io`
Plain JSON text frames, subprotocol `protocolOne`, works from our own Origin (used by the Live page, `src/lib/chat.ts`).
- First frame `{type:3, messages:[…]}` (recent history). Message `{type, user:{id,shortId,name,role,level,roleTag}|null,
  message, msgId}`. `type 2` = player message; `type 13` = system trade offer (`/trade accept <n>`), cancels, accepts.
- Item tags in text `[name|weapon|ITEM_TYPE|RARITY]` with optional `xN`. Rarities: PARANORMAL, MYTHICAL, LEGENDARY,
  EPIC, RARE, COMMON. The Pwnstar bot (role BOT) posts giveaways/votes/inventory values. Many connections from one IP
  → `ERR_CONNECTION_RESET`; back off.

## 7. Auth — Xsolla OAuth
Kirka logs in via Xsolla. Refresh: `POST https://login.xsolla.com/api/oauth2/token`, form body
`grant_type=refresh_token&client_id=303&redirect_uri=https://kirka.io&refresh_token=…` → new access + refresh token
(access lasts ~24h). `tools/auth.py` keeps our stored login valid without a browser (`kirka-api/auth.json`, gitignored).

---

## 8. Obfuscation / decoding
Kirka minifies paths, JSON field names and enum values and rebuilds them on updates. Decode by matching live
responses against `docs-json` and the socket reflection. Per-area maps live in the tool that uses them:
quests → `tools/quests.py`; shop → `tools/shop.py`; live games listing → `src/lib/games.ts`; maps → `tools/maps.py`;
news → `tools/feeds.py`; **socket schema → the reflection itself (self-describing), decoded by `tools/colyseus.py`**.
The client bundle (`game-src/<date>/app.*.js`) stores readable strings as hex after a `MWNnM-` prefix (decode with
`bytes.fromhex`) — this is how we recovered "Permanent spectator; irreversible", the KAT route list, scoreboard
config JSON, etc.

## 9. Bugs / issues found (for xip)
1. **Quest data bug** — non-weapon quests serialize their weapon field as the literal string `"undefined"` instead of
   null.
2. **Access control** — match history + ranked profile are readable with **no login and no API key**, by short id.
3. **Info disclosure** — `api2.kirka.io/api/docs-json` is world-readable, exposing all 336 routes incl. the admin
   (KAT) paths and schemas.
4. **Spectator data exposure (by design, but total)** — a spectator receives the full authoritative state of every
   player: exact position, rotation, health, shield, score, kills, deaths, team, loadout and per-tick movement. A
   spectator client therefore has complete positional knowledge of every player (relevant to wallhack/radar cheats).
5. **(2026-11-15) Dev addresses left in the production bundle** — `game-src/2026-11-13/app.0312c6a3.js` still contains
   `http://127.0.0.1:4000`, `http://localhost:8080`, `ws://127.0.0.1:2567` (local Colyseus default port) and
   `ws://localhost:443`. Harmless at runtime but leaks the dev setup; worth stripping in the build.
6. **(2026-11-15) Spec exposes the anti-cheat surface** — docs-json names the replay recorder (`/api/layout/*`, framed
   as "layout" to look harmless), screen capture upload (`/api/layout/tiles/{id}`), moderation cases with screenshots
   and the inspector. The disguised path names don't help when the public spec labels them `ReplayController` etc.
7. **(2026-11-15) `createGuest` is unauthenticated** (`POST /api/WwnNmwWM/wwnmWWNM`, no security in spec) — anyone can
   mint guest accounts; worth a rate limit if there isn't one. (Not called by us.)
   > **OLD:** listed as a bug.
   > **NEW (2026-11-15, later):** **NOT a bug — a feature.** xip confirmed guest accounts are intentional
   > (guest play / logged-out quests). Kept here only as history; drop it from the bug report to xip.
Also seen: host `https://client.kirka.io` in the bundle (not yet looked at).

## 10. Access levels
- Normal player (our account): all of §1–§7 except login-gated and KAT routes.
- **KAT** (Kirka Admin Tool) — staff only; gates create/edit quests, anti-cheat, config, logs, play stats, **public
  API tokens**. Our account's `kat/fetchMyAccess` returns `{manageRoles:false, sections:[]}` → `/kat` not reachable.
  Known KAT/chat roles: BUG, TESTER, BOT, MODERATOR, OWNER (+ roleColors also lists SCRIPT, ASSET, VERIFIED, MAP,
  PAYMENT, VIP, ADMIN). The public-API token feature exists but is behind KAT (xip can grant a role/token).

## 11. What we cannot get
- **Past daily/ranked history** — the API returns only today's board; nobody public archives it, so old data isn't
  recoverable. Our archive only grows forward. Past ranked seasons need KAT (403).
- **Enumerate all players** — no "list all users" endpoint; reach players via leaderboards + clan rosters + match
  rosters (snowballs to the active/competitive population, not every dead account).

## 12. Tools built (`tools/`, stdlib only unless noted)
`feeds.py` (online/news/votes/videos/effects), `shop.py`, `quests.py`, `maps.py`, `scripts/build_creators.py`,
`lb_archive.py`, `snapshot.py`, `collect.py`+`statsdb.py` (the DB), `traders.py`, `auth.py` (Xsolla refresh),
`daily.py` (orchestrator, `--cloud`), `cdp.py` (debug-Chrome driver over port 9222), `room.py` (roster via the
client's spectator scoreboard DOM + archive), **`colyseus.py` (the headless Colyseus decoder: msgpack + schema)**,
**`specd.py` (spectate a live room, capture its socket, headless-decode the full roster + archive)**.

## 13. The stats database (`kirka-api/kirka.db`, SQLite)
Tables: `players`, `player_daily`, `clans`, `clan_daily`, `memberships` (w/ join date), `leaderboard`, `online`,
`events` (join/leave/role), `trader_daily`, **`match_roster`** (room captures: captured_at, room, region, mode, map,
short_id, name, rank, kills, deaths, score, side, is_bot), `meta`. Deltas across days give daily/weekly/monthly/
all-time; membership diffs give clan join/leave/role timelines; match_roster links players → matches over time.

## 14. Automation & deploy
PC Windows Task `KirkaDailyReport` (every 3h) runs `daily.py`. Cloud GitHub Actions `kirka-daily.yml` in
`github.com/omyxheru/kirka-data` (every 6h) runs `daily.py --cloud`, commits reports + `public/*.json` + `kirka.db`;
never commits `auth.json`/`catalog.json`. Public data needs no secret; quests+maps use the optional `KIRKA_REFRESH`
repo secret (the refresh token). `room.py`/`specd.py` are **local** (they drive the logged-in client over CDP); the
pure-headless spectator (`joinById` for every room with no client) is the next step and needs permission to open
game-server sockets.

> **OLD (2026-11-15, morning):** "pure-headless spectator via `joinById` is the next step".
> **NEW (2026-11-15):** HTTP `joinById` is disabled (4210); headless needs the lobby reserve protocol (§4.8).
>  PARKED by xip. `room.py`/`specd.py` (local, via the logged-in client) are unchanged.
> **NEW (2026-11-15, later):** not parked after all — xip meant leave KAT (staff), not the spectator work. See §4.8.

## 15. Website pages (what shows the data)
See [website.md](website.md). The Games page room-detail panel shows the live match timer, win/time limits, ranked/
level/login flags, custom-map author, and — when captured — the **roster** (name, short-id, K/D/score, bots flagged,
"captured Xs ago"), fed by `room.py` (DOM) or `specd.py` (headless socket decode).

---

## 16. LIVE ALL-ROOMS PLAYER DATA — build log (started 2026-11-15)
Goal (user, for xip): live player data for **every** open room, all regions. Findings appended as they happen.

**2026-11-15 — live patches verified offline.** `colyseus.Decoder` is stateful: after the op-14 full state, feeding
every op-15 patch into the SAME decoder keeps the state current. Against `captures/ws-spectate/session.json`:
**159/159 patches applied, 0 errors**; over ~9 s kills/deaths/score/positions moved (e.g. sky_3o3 28→30 kills,
1175→1275 score; yusuf.baba.67 6→7 kills). So one open socket per room = a live roster, no re-spectating needed.
Frames the real client SENT on join (recorded): `0x0a` (JOIN ack), `0x0d 0x45` (op-13 type 69, no payload),
`0x0d 0x16 "refactor"` (op-13 type 22). A headless socket must send at least the `0x0a` ack to receive state.

**Plan ("guest army"):** guest browser tabs (incognito contexts in debug Chrome, `tools/guest.py`) only MINT the
spectator seat — a page-level `WebSocket` hook catches the game-room URL
(`wss://<region>.kirka.io/<processId>/<roomId>?WmwNWnMw=<sessionId>`) before the tab connects, and hands it to
Python. Python opens that socket itself and decodes state + patches live. One tab can mint seats for many rooms in
turn; several guest tabs mint in parallel. No 3D game tab has to stay open per room.
Tool: `tools/liveall.py` (in progress).

**2026-11-15 — first mint test (guest tab, hook armed only at SPECTATE).** Sockets the guest page opened, in order:
1. `wss://eu.kirka.io:443/dlGhJ2B1Y/P7O0-IUed?WmwNWnMw=hHNHGtphc` — the **lobby** room (same URL shape as a game room!
   so the hook must stay disarmed until the SPECTATE click), 2. `wss://chat.kirka.io` — global chat,
3. after SPECTATE: `wss://eu.kirka.io:443/dlGhJ2B1Y/lGJT4_grf?WmwNWnMw=BGnCCx9nt` — the **spectator seat**. Notes:
the client puts an explicit **`:443`** in the host (first regex missed it); the processId (`dlGhJ2B1Y`) was the same
for lobby and game room (one EU process); the game roomId here **equalled** the listed room id (`lGJT4_grf`); the page
URL changes to `https://kirka.io/games/EU~lGJT4_grf` when spectating. A guest account can spectate.

**2026-11-15 06:30 — FIRST LIVE ROOM WORKING (`python tools/liveall.py --one`).** Guest tab minted the seat for
`EU~lGJT4_grf`, the holder tab on `https://kirka.io/ads.txt` opened it (real kirka.io origin, no header faking, no
game loaded), Python decoded state + patches live: **9 players, ~20 patches/s (411 in ~25 s)**, every field live —
name, shortId, team, kills/deaths/score, **HP** (drops to 0 on death, back to 100 on respawn), **xyz position**.
Seen live: Navy_seal6864 12→14 kills / 370→425 score; Dream 14→15 deaths with hp 0 then 100. The holder approach
needs nothing from the game tab after the mint (the minting tab got a dummy socket and never loaded the match).
Note: several players named "Newbie" with different shortIds — that is Kirka's default name for new/guest players,
so **shortId is the real identity**, never the name.

**2026-11-15 — scale check.** Public listings right now: EU 17 rooms/57 players, NA 7/19, SA 2/9, ASIA 9/41,
OCEANIA 7/12, INDIA 10/41 = **52 rooms, 179 players**. The in-game SERVERS list shows **one region at a time**
(`.select-region`; a fresh guest landed on ASIA, presumably nearest/ping) and filters by tabs MAIN / PARKOUR /
CUSTOM. So minting every room by clicking the list needs region + tab switching. Testing the direct room URL
`kirka.io/games/<REGION>~<id>` instead (hook blocks any room socket on that page so it can't auto-join as a player).

**2026-11-15 — direct room link test → NOT used.** Opening `kirka.io/games/NA~hSRCpJS98` (hook catching every room
socket) caught `wss://na.kirka.io:443/ySEXKrQIm/uFs4WYiPn?...` — that is the **NA lobby** (roomId ≠ the target), so
the page sat on LOADING. Learned: **the lobby is per region** (opening a NA link connects the NA lobby), and a room
link may auto-join; a caught seat URL doesn't say whether it's a spectator or player seat, so we only ever mint from
the SPECTATE button (seat is guaranteed spectator). Going with region switching in the SERVERS list instead.

**2026-11-15 — region = a localStorage key.** The client stores the chosen region as `localStorage.region`
(`"EU"`, `"NA"`, …) and connects that region's lobby; the SERVERS list then shows that region. A fresh guest picks
one automatically (seen ASIA once, EU once). Also in localStorage: `guestToken` + `token` (guest JWT), `version`
(`0.44.4` = game version), ~300 `SETTINGS___SETTING/...` keys (all client settings, incl. matchmaking
`WARMUP_ONLY`, `MINUTES_LEFT`, `LOGGED_ONLY`, privacy `ANONYMOUS_MODE`, spectator keybinds `SPECTATOR_WALLS`/`FLY`/
`FPS`/`TPS`). → **Guest army design:** one guest tab per region with `localStorage.region` preset before load
(script injected at document start), each minting its own region's rooms in parallel; one shared holder page.

**2026-11-15 06:35 — first guest-army run (EU+NA, 3 min).** Within ~2 min: **14 rooms live, ~70 players** decoded
at once from one holder tab. Problems found (being fixed):
1. live.json write crashed: `Circular reference detected` — some decoded player field is a shared schema object
   that links back; output must be sanitised to plain values.
2. Decoder error `index out of range` on 2 rooms after ~1,400 patches each (EU~udDYg8RjW, NA~hSRCpJS98), then the
   server closed the socket with code 1000 (normal close) — suspect round end / room reset sends an op we decode
   wrong. Need the raw frames to fix → adding a frame recorder (captures/liveall/).
3. "no seat" on some listed rooms although the row was found (EU~eJjMtqzX2, EU~aF4TQuoiG) → need the reason
   (no SPECTATE button? full / ranked / private?).

**2026-11-15 06:45 — decoder bug found (from the recorded frames in `captures/liveall/`).** Second run (EU+NA,
4.5 min) reached **19 rooms / 108 players live**, but 16 rooms hit decode errors (`schema number prefix 0x80/0x84/
0x94…`, `index out of range`). Tracing the failing patch every time: a **map DELETE** on the players map (refId 4,
type 15) — e.g. `0f 8d … ff 04 40 00 …` = switch to ref 4, op `0x40` DELETE, index 0 — i.e. **a player leaving**.
In @colyseus/schema v2 a DELETE carries **no value**, but `colyseus.py` still read an element value after it, so the
rest of the patch was misaligned. Same bug in the array DELETE path. (The offline 9 s capture never had a player
leave, so validation missed it.) Fix: return right after a plain DELETE in `_map_op`/`_array_op`.
Also seen: the patch right after the delete ADDs a new player whose name starts `bot…` (a bot filling the slot).
**Fix verified:** replaying all 16 recorded failing rooms + the original capture through the fixed decoder:
**14,533 state/patch frames, 0 errors** (backup of the old decoder: `tools/colyseus.py.bak-20261115`).

**2026-11-15 06:55 — why some rooms gave "no seat".** Compared the in-game SERVERS list (guest, EU) with the public
listing:
- **Login-only rooms can't be spectated by a guest**: `loggedOnly___METADATA=true` rooms — ranked (`1V1`, `RSAD`,
  `POINT2V2` needLevel 10) and `TRAD` (50-slot). They appear in the list but no seat is minted for a guest. Covering
  them needs a logged-in account (not used: xip said guest accounts).
- **Custom-map rooms** show as `USER MODE` rows with the custom map name (e.g. "Arsenal: Warzone", "anti gravity",
  "Hunger Games") and **no session-id text** → matched by name; the real roomId is then read from the seat URL.
- The in-game list showed **14 of 20** listed EU rooms; the MAIN/PARKOUR/CUSTOM tabs did not change it (those tabs
  belong to another panel). Rooms missing from the guest's list at that moment: a `PAR` parkour room, two `TKO`
  rooms, `POINT Castle`, `TDM Pool` (all 1–4 players). Reason not known yet (maybe list cap / matchmaking settings
  `WARMUP_ONLY`, `MINUTES_LEFT`).
- **Full rooms (`is-locked`, 8/8) CAN be spectated** (EU~AdODAirNs was 8/8 and decoded).
- Rows have no framework data attached (production build), so only visible text can be matched.

**2026-11-15 06:47 — first all-6-regions run.** 59 rooms listed; 4 rooms / 28 players live within 15 s, then the
tool crashed on our side (Windows console couldn't print a room's error text → main loop died → guest contexts
closed → every minter lost its CDP link). The error text was a Colyseus **ERROR frame (op 11)**:
`0b cd 77 10 ad "onAuth failed"` = code **4215** (uint16 LE 0x1077), message `onAuth failed` — from INDIA~6zpx2M1LR:
the room's onAuth rejected the guest seat (cause unknown yet: maybe a room rule, maybe seat timing). Also: the
server list re-renders live, so a click can land on a neighbouring row ("asked EU~i5lLvx-e1, seat is EU~TNcuqiQk5")
— harmless because seats are filed by the roomId in the seat URL.

**2026-11-15 06:53 — ALL 6 REGIONS LIVE (5.5-min run, 6 guest minter tabs + 1 holder tab).** Ramp: 21 rooms/102
players at 1.5 min → 34/155 → 42/201 → **peak 53 rooms / 255 players decoded live at the same time**, every region.
Rooms closing with code **1000** after 1,500–4,300 patches = the match ending normally (re-minted if still listed).
No decode errors after the DELETE fix. "No seat" leftovers: rows that re-rendered mid-click, TKO/PAR rooms not in
the guest's list (`row=None`), some rows found but no seat in 8 s (to investigate). Known display bug: the "listed"
total only grew (ended rooms never removed) → fixed to recount per region each refresh.

**How to run it (2026-11-15):** debug Chrome on port 9222 open, then
`python tools/liveall.py` (all regions, until Ctrl+C) · `--minutes 5` (timed) · `--regions eu,na` · `--one` (one
room test). Output: `skin-library/public/rooms/live.json` (every live room, refreshed every 2 s: tag, region, mode,
map, patches, players[rank, name, shortId, isBot, team, kills, deaths, score, health, shield, role, weaponSkin,
pos xyz]) + per-room `public/rooms/<tag>.json` + **archive** `kirka.db` `match_roster` (each room once a minute).
After today's test runs the archive held **1,389 roster rows, 98 matches, 234 distinct players**. Decode-error
recordings go to `captures/liveall/`. Not covered yet: login-only rooms (ranked, TRAD), rooms missing from the
guest's server list, and the op-13 telemetry (kill feed / loadouts) — the holder only queues state frames for now.

---

## 17. HEADLESS GUEST + REAL-TIME EVENTS (xip, 2026-11-15: "real live data — damage/deaths immediately", "a better way for guest accounts, without opening anything")

**2026-11-15 06:58 — createGuest works with no browser.** `POST https://api2.kirka.io/api/WwnNmwWM/wwnmWWNM` body
`{}` → **201**, ~1.4 KB: `{wwMNm: <guest JWT>, WwMWm: <the new user>, wnMmwWWN: true}`. JWT payload =
`{sub: "guest-<uuid>", iat}` (no expiry claim). New user: id `guest-72eaf80d-…`, shortId `V9WKHV`, name `Newbie`,
level 1, coins 100, default loadout (LAR + character James), `wnMmwWWN: true` (= is guest?). Raw:
`kirka-api/api2/probe-20261115/createGuest.json` (contains a live throwaway token — not pushed).
**Finding for xip (info exposure):** the user object returned to the client carries the **anti-cheat fields
un-obfuscated**: `online, hacker, fullName, picture, banDone, autoaim, wallhack, lastIp, autoaimWall,
autoaimWallShoot, muteReason, kloTrust, kloPOINT2V2Trust, kloSADTrust, klo1V1Trust, klo2V2Trust`. For a guest they
are its own (zeros), but it reveals the server-side cheat model/flags — check whether other user-object responses
(profile, friends, lobby) also carry them for OTHER players.
**Guest token works headless as a Bearer token:** `Authorization: Bearer <guest JWT>` → `GET /api/WwMWm`
(getCurrentUser) **200** and `POST /api/wNnWmM` (getQuests) **201** (7.9 KB). The `x-guest-wwMNm` header ALONE
gives 401 → **OLD** note above ("sent as header x-guest-wwMNm") is incomplete: **NEW** — REST auth for a guest is a
normal Bearer token; x-guest-wwMNm is something else (maybe sent alongside, or for the lobby).

---

## 18. SEAT RESERVATION DECODED + CLOUD PLAN (2026-11-15, "build the headless and put it on the cloud")

**Lobby capture decoded** (`captures/lobby-reserve/session-065920.json`, guest tab, EU, one SPECTATE click). Lobby
socket `wss://eu.kirka.io/<processId>/<lobbyRoomId>?WmwNWnMw=<sessionId>`, Colyseus op-13 msgpack messages
(`0d <type> <msgpack>`). Order seen:
1. R op-10 JOIN (schema) · S `0a` ack · S `0d 23` (type 35, empty) · R op-14 lobby state.
2. S type 112 `false` · R type 104 (`0x68`) = **the full maps list** (34 KB, 104 maps: tag, tagClass, activePlay,
   optionPlay, …) · R type 23 (`0x17`) = party-chat **command list** (`/help` …) · R type 105 = server chat line
   "Welcome to the party chat…".
3. **Bot check, type 35:** R `0d 23 ce 01 05 a5 74` = a number challenge (17147252) → S `{data: <long XOR/base64
   blob>}` → R `true`. **We do NOT generate this blob** (standing rule: no bot-check work). The real client in a
   browser answers it; everything below runs on top of a lobby that the real client has already passed.
4. S type 112 `false`, S type 113 `"online"` (presence).
5. **The SPECTATE click = ONE message, type 101 (`0x65`):**
   `{wwMnWWNm: <roomId>, wWwNWM: true /*spectate*/, wWwNWnmM: false}`
6. **Reply type 102 (`0x66`)** = the seat reservation: `{wWnWMNwm: {mwwnWMNW: {<room listing: name 'DM',
   WmwNWnwM: <processId 'dlGhJ2B1Y'>, WWMNmww: <roomId 'X3HQGZLcW'>, WnWwwMm: <metadata: mode, players 8/8,
   inRound, roundCreatedAt, loggedOnly, needLevel…>}>, WmwNWnMw: <sessionId 'b-mH5Nce6'>}, wWwNWM: true}`.
   → seat URL = `wss://<region>.kirka.io/<processId>/<roomId>?WmwNWnMw=<sessionId>` (matched the hooked URL exactly).
7. Then S type 123 (`0d 7b`, no payload) → R type 116 (`0d 74`).

**What this unlocks:** the minter tab no longer has to click through the SERVERS list. After the page's own lobby
is connected (and the real client passed the check), the tab sends type 101 for ANY room id from the public
`/matchmake/` listing and reads the type-102 reply. No row matching, no list re-render mis-clicks, and rooms that the
guest's list never showed (TKO, PAR, …) can be requested too. Pure-Python (no browser) would need the type-35
answer → not doing it; ask xip for an official way (e.g. a whitelisted spectator token) if a browserless version is
wanted. Cloud plan: headless Chrome (real client, no 3D match loaded) + Python, runnable on a GitHub Actions runner
or any server.

**2026-11-15 — direct seat request WORKS (`tools/lobbyseat.py`).** Guest tab (EU) loads kirka.io normally, the
client connects its lobby and passes the check itself (`0d 23 c3` seen → `__lobbyOk`); the hook then sends type 101
over that same socket. Results: **0.37 s per seat** (old click flow: ~5–10 s), seats for `TKO Pool` (13p),
`PAR Race`, `TDM Gulag` — TKO/PAR were rooms the guest's SERVERS list never showed. The type-102 reply is hidden
from the game (listener registered before the client's onmessage + `stopImmediatePropagation`), so the client never
tries to join; 0 room sockets had to be blocked. Hold test: 4 seats minted → holder opened them → **4/4 rooms decoded
live in 15 s** (16 / 8 / 9 / 6 players, ~17 patches/s each, 0 errors). Next: liveall uses this instead of clicking,
then headless Chrome for the cloud.

**2026-11-15 07:15–07:29 — headless Chrome + liveall on the direct seat request (3 runs).**
- **Headless Chrome works** (`tools/chrome.py`, plain `--headless=new`, throwaway profile, nothing spoofed): the real
  client connects its lobby and passes the check by itself. → runnable on a cloud runner.
- **Lobby rate limit:** a burst of 8 seat requests → inbound **type 101 = refusal string** `"Rate limit, retry in a
  few seconds"`. Other refusals on 101: `"Room doesnt exist"` (match ended), `"Room is locked"`. 1 request per ~3–3.5 s
  per guest lobby = 0 rate limits (12/12 seats in a row on one EU guest, all 12 rooms live at once → no per-guest
  spectate cap seen). liveall now paces 3 s (`PACE`) and backs off 8 s on a rate limit. We stay under it, never
  around it (no extra guests to dodge it).
- **`onAuth failed` (4215) was mostly self-made:** requesting the next seat before the previous one was opened.
  Fix: the minter thread opens each seat in the holder itself (own CDP link to the holder page) right after the
  reply. "seat reservation expired" came from the main loop lagging (CPU) → gone after the next fix.
- **CPU:** 6 guest tabs each rendering the 3D lobby in software saturated Chrome. Fix: once the tab's lobby passed
  the check, the hook swaps `requestAnimationFrame` for a 1 fps timer (lobby networking doesn't need frames).
  Decoder cost is negligible (36k frames/s in Python).
- **Late seat replies leaked to the game** (it tried to join 11 rooms → blocked by the hook → its lobby closed 4002).
  Fix: every inbound 101/102 is hidden from the game (we never click, so they're all ours).
- **Result (run 3, 4 min, all 6 regions, headless):** 10 rooms at 1 min → 30 / 172 → **peak 45 of 57 listed rooms,
  244 players** live at once; 0 expired seats, 0 lobby drops. Still open: ~7 rooms answered `onAuth failed` on the
  first try (5 were TKO 20-slot, 1 a custom "ME dev" room) — cause unknown, retried after 3 min.
