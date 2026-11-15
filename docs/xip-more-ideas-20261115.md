# xip: "there's so much more we can do": data we already receive but do not use (2026-11-15)

OFFLINE analysis only: recorded files, no network, game not run. Out of scope, as standing rules say: the lobby
**type 35 bot check / integrity blob** (not decoded) and **KAT / moderation** (last priority).

Sources read:
- `captures/ws-spectate/session.json`: one spectator session, about 9 s. The CDP recording mixes the **lobby**
  frames (type 102 seat, 35, 123/116) with the **game-room** socket.
- `captures/liveall/*.json`: 16 rooms, 14,516 state/patch frames, recorded by `tools/liveall.py`.
- `captures/lobby-reserve/session-065920.json`: lobby socket and chat socket.
- `captures/tdm-end-053114/end.html`: the end-of-match screen DOM.
- `kirka-api/api2/probe-20261115/*` and `docs/api2-routes-20261115.md`.

Decoding used python `msgpack` plus `tools/colyseus.py`. The scratch scripts were not saved in the repo. All
example values below are real values from the captures.

---

## 0. Headline findings

1. **op-13 type 31 is a HIT event, not "spawn/health"**: `{victim sessionId, attacker sessionId, damage,
   headshot flag, killed flag}`. All 13 events in the capture match the state patches that follow 1–5 frames later
   (hp drop = damage, `killed=1` = victim deaths +1 and attacker kills +1). This is the real-time damage and death
   feed xip asked for in §17. **We already receive it.**
2. **`tools/liveall.py` drops every op-13 frame.** The holder JS (line 67) queues only ops 14/15/11/12. That is why
   `captures/liveall/` has 0 op-13 frames. Adding `13` to that filter turns on the kill feed, headshots and damage
   for all ~50 rooms at once.
3. **The state already carries a lot that we decode but do not output.** Per player: the full **loadout with skin
   names** (weapon skins and character), **clan tag**, **account level**, the **weapon in hand**, a
   **recent-attackers list with weapon + headshot flag** (type 8, 4 s window, used for assists), time alive,
   is-alive/is-dead flags and spawn count. Per room: **team scores**, **round number**, the **round banner
   text (`MVP: Name#SHORTID (3 kills, 0 assists)`, `Next round in 3`, `Waiting for players`)**, round start
   clock, and **match end (`state___SYNC` start → end)**.
4. **The roster field we call `weaponSkin` (`wNWWwMmn`) is the weapon the player is holding, not a skin.** It flips
   VITA↔Tomahawk as the player switches weapons. The real skin is in the loadout array (e.g. Bayonet → "Alighted").
5. **The spectator itself is in the players map** (it has a shortId, `team:""`, its spectator flag set), and listing
   `WNMWnwm` counts spectators. The Games page reads `room.WNMWnwm` first, so **our own guest spectators inflate
   the public player counts**. `meta.wWMnw` is the real player count.
6. The game socket sends the **entire voxel map** (op-13 type 1: 24 chunks × 4096 blocks + lighting/fog/sun) when
   you join. With live positions plus kill events, this is enough for **kill/death heatmaps on the real map geometry**.

---

## 1. op-13 messages decoded (`0x0d <type> <msgpack>`)

Note: msgpack ext type 0 with payload `00` = JS `undefined`. Ext type 0 with 8 bytes = a uint64 ms timestamp.

### 1a. Game-room socket, server → us

| type | when | meaning | fields (obfuscated key = meaning) | real example | confidence |
|---|---|---|---|---|---|
| **28** | continuous (266 msgs / 9 s / 12 humans) | **Client movement batch**, relayed per player. Only humans send it; bots move via state | `wwMnmWW` = sessionId; `WmwN` = array of 4–22 sub-ticks at 60 Hz: `WmwwMnWN` x, `WmwwMnW` y, `WmwwMn` z, `WwMwNmn` pitch, `WwMwNmWn` yaw, `WmwNWn` = **client clock ms** (steps of 16.67; same scale as state `wMNmWwnW`), `WmwNWwnM` bool ≈ moving/keys held (true 495× moving vs 85× still), `WmwwMnNW` bool (crouch or fire, unclear), `WmwwMN` 0/1/float = ADS/scope progress | `{"wwMnmWW":"jgV9CYW6Y","WmwN":[{"WmwwMnWN":-38.94,"WmwwMnW":-2,"WmwwMn":-0.585,"WwMwNmn":-0.513,"WwMwNmWn":4.419,"WmwNWn":210033.1,"WmwwMnNW":false,"WmwwMN":0,"WmwNWwnM":true},…]}` | high (pos/rot/clock), low (bools) |
| **31** | per hit | **HIT / KILL event** | `WmwwM` = **victim** sessionId, `WmwwMWN` = **attacker** sessionId, `WmwwMNn` = **damage** (90 head / 50 body in TKO), `WwMwN` = **headshot** 1/0, `WmwwMNWn` = **killed** 1/0 | `{"WmwwM":"qt2_mdNWb","WmwwMWN":"S8A-1lsbg","WmwwMNn":90,"WwMwN":1,"WmwwMNWn":1}` = Vladimir-Lenin headshot-kills Newbie (deaths 2→3, his kills 1→2) | **verified 13/13** |
| **0** | once on join | **Room settings**: the same object as the listing metadata `WnWwwMm` (see §3c) | weapon whitelist with forced skins, mode, map, caps, flags | `{"wMNmWwW":"TKO","wWwWmMnN":"Sk8","wWnWMw":16,"wWmW":30,"wWwWmMn":{"Tomahawk":{…},"Bayonet":{"skin":"Bayonet","isSelected":true,"wear":true}},…}` | high |
| **1** | once on join (102 KB) | **Full map geometry**: voxel chunks plus render settings | `light/blockLight/brightness/skyboxColor/fogColor/fogNear/fogFar/fogAmbientColor/sunX,Y,Z/shadow*/triangles/blockTraits___DATA`, `chunks___DATA` = `{"x,y,z": [4096 block ids]}` | Sk8: 24 chunks, `fogFar 42`, `fogColor #141f1d` | high |
| **3** | once | Spectator camera start `"x,y,z,pitch,yaw"` | string | `"-15.5,-1.99,-14.5,0,3.48"` | high |
| **29** | once | **Our own** loadout (the spectator's), with no sessionId | `wMNmWnWw[]`: `wNWWnwMm` slot (BODY/weapon), `wwMnWW` skin, `wmMNn` equipped, `wWwNWnM`, `wWMnWmNw`, `wWMmnNwW/wWMmnNw/wWMmnNWw` (0), `wWnMNmW` | `[{"wNWWnwMm":"BODY","wwMnWW":"James","wmMNn":true,…},{"wNWWnwMm":"Bayonet","wwMnWW":"Bayonet",…}]` | high |
| **23** | once | Room chat-command list | `[{name, description, args}]` | `[{"name":"roles","description":"List current room owners, admins and moderators"}]` | high |
| **81** | once | Unknown single number | `[23679127]` | could be a server tick or uptime (6.6 h as ms) | low |

Not in any capture, but the end screen proves it exists: **in-room chat and join/leave lines** (`Tomboyloichoi: gg`,
`thy123_ left the game`). Most likely a separate op-13 type, shaped like lobby type 105 `{name, message, role}`.
Record it once the holder forwards op-13.

**Round and match end are NOT op-13 messages.** They come through the state (§2a).

### 1b. Game-room socket, client → server (what the real client sends; for reference, we do not generate any of it)

| type | payload | meaning (guess) |
|---|---|---|
| 69 | `[]` at join; later `{blob, nonce}` | Integrity/proof message. **Same category as the type-35 blob: off-limits, not decoded** |
| 22 | `"refactor"` | client build/feature marker sent on join |
| 67 | `{WmwNWn:1}` | spectator control (camera mode or target) |
| 70 | `{wwMnmN:0}` | spectator target index (next/prev) |
| 24 | `[]` | spectator request (e.g. follow/refresh) |
| 35 | bot-check answer | **skipped** |

Correction to `kirka-everything.md` §4.5: 67 and 70 are **sent by the client**, not server "counter events".

### 1c. Lobby socket (`captures/lobby-reserve`) and the same frames inside session.json

| type | dir | meaning | example |
|---|---|---|---|
| **104** | R | Map catalogue + **mode catalogue** (34 KB). `maps`: 104 maps (`id,name,tag,tagClass,activePlay,optionPlay,activeCreate,optionCreate,enabled,fullPreviewUrl,miniFullPreviewUrl,previewVerticalUrl`). Tags: 61 none, 37 `Experimental`, 4 `Event` (Ghosttown, Moss, Rust, Stratos), 2 `___Experimental___`. Only `Lava` has activePlay=false. `modes`: 12 modes, each `{id,name,tip,tab,weapons[],mapIds[] (= the official map rotation), isRanked,needLevel,needLogged,gameType,state[] (HUD widgets),flags,build,serversList,sort,isDefault,enabled}` | DM rotation = Arid, BootyBay, Castle, Catacomb, Co2 XL, Mefitis, Sandstorm, Shipment, Wade, Windmill. RWP = "LAR ONLY" (Event: BootyBay, Moss). TRAD needLogged=true. PAR has 29 maps |
| 23 | R | party-chat commands | help, start, ready, team, kick, ban, promote, demote |
| 105 | R | party chat line `{name, message, role}` | `{"name":"SERVER","message":"Welcome to the party chat…"}` |
| 101 | S | reserve a seat `{wwMnWWNm: roomId, wWwNWM: spectate, wWwNWnmM}` | (known, §18) |
| **102** | R | seat reservation + **full listing entry for that room** (metadata §3c) | `WNMWnwm 13` vs `wWMnw 12` = 12 players + 1 spectator |
| 112 / 113 | S | presence: `false` / `"online"` | |
| 123 → 116 | S → R | ping → pong (~5 s) | |
| 35 | R/S | bot check | **skipped** |

Lobby **state** (op-14, root type 2: `wMNWWnmw` party members, `state___SYNC`, `wWWwnN`, `wmwNWMWn`, `wWnMNmWw` = own
sessionId / party leader, `wWMwNW`, `wmwNWMW`). Each member has a 7-slot loadout with skins, team, level, `WwMwnW`,
role and held weapon, plus three booleans `wNWWwmn/wNWWwm/wNWWn` (ready / host / leader, guessed).

Chat socket (§6), not yet used: every chat user carries **`id` (uuid; guests are `guest-<uuid>`), shortId, level,
role**. A guest can be level 86 (`China #CHINAA`), so guests are long-lived accounts, not throwaways.

---

## 2. State fields we decode but do NOT output (`tools/colyseus.py` → `liveall.py` live.json / `match_roster`)

Current output: rank, name, shortId, isBot, team, kills, deaths, score, health, shield, role, weaponSkin (really
the held weapon), pos.

### 2a. Room root (type 16 GameState)

| key | meaning | evidence |
|---|---|---|
| `state___SYNC` | match phase: `start` → **`end`** | NA~YIaWPdvim (PAR) flipped to `end` on its last patch, right before the 1000 close |
| **`wWnWMmNw`** | **centre banner text**: `MVP: Pfandwasser#Q9ULUE (3 kills, 0 assists)`, `Next round in 3/2/1`, `Waiting for players` | EU~eJjMtqzX2 (RSAD), EU~9umLh-8rY (1V1) |
| **`wWMwNWmn` / `wWMnwWNm`** | **team scores** (red / blue). In round modes = round wins | TDM ticks 18→22 / 8→12; RSAD 1→2→3 at each MVP |
| `wNWWnMw` | **round number** | RSAD 2→3→4 after each `Next round in 1` |
| `wWwNnMWm` | rounds setting (1 normal, 10 RSAD, 9 1V1) | |
| `wmMNWnW` | score cap (16, 4 RSAD, 10 1V1, 0 TRAD) | |
| `wWnMmW` | room-clock ms when the current round started | RSAD 194923 → 229964 → 248210 |
| `wWWwnN` | room clock ms (elapsed) | TRAD room 7,750,082 = up 2 h 9 min |
| `wMNWWmw` | round live (true) / intermission (false) | false during MVP + countdown |
| `wmwnMNWW` | waiting for players | true in the empty 1V1 |
| `wmwNWnWM` | true only in RSAD (ranked/round-based flag) | |
| `wwMnWWN` / `wMNmWnW` | mode / map | (already from listing) |
| `wwMnNWm` | vec3, non-zero only in PAR = parkour finish/checkpoint position | (50.64, 17.1, 20.63) |
| `wmwnNMW` | HUD widget JSON (timer, kd, score, `{"kind":"killfeed"}`) | |
| `wmMNWWn` | scoreboard config JSON (`teams`, columns, sort) | |

### 2b. Player (type 15; 62 fields)

| key | meaning | example / evidence | confidence |
|---|---|---|---|
| **`wnMmWwNW`** (and the identical `wmwnN`) | **full loadout**: array of type 0 `{wwMnWmW: slot (BODY / weapon), WwMwnWNm: **skin name**, wmwnNMWW: equipped, wWWwNM, wWMwN, wWMnWmN/wWMnWmwN/wWMnWmw (0), wWnWMNw}` | sky_3o3: BODY **Slime**, Tomahawk **Damascus**, Bayonet **Alighted**. Others: MAC-10 Lemon/Sleep/Beet/Toy/Fire/Rub1x, Weatie Neon/Winter/Teflon/Wacky/Fading Waves, Shark Fortunate | high |
| **`wwMnWNW`** | **clan tag** | `ftw/ttv`, `Frost`, `Polaris`, `PINRIDs`, `Saphyr_`, `KirkSports` | high |
| **`wNWWwmMn`** | **account level** (old note: "weapon index") | Newbies 1–3; drku. 99; matches `players.level` in kirka.db for TUF1GY 97, 40O0Q4 95, ZYNOTW 99, JKMXIY 97 | high |
| `wNWWwMmn` | **weapon held now** (was labelled weaponSkin) | flips VITA↔Tomahawk, AR-9↔Bayonet mid-life | high |
| **`wNmWMwnW`** | **recent attackers** (type 8): `{wmwNWWMn: attacker sessionId/bot id, wnMmNw: bool (headshot?), wNWWwMmn: **weapon used**, wWNwMmW: 4000 (ms window), wWWwNnMm: bool, wmwNWWM: 0}` | `{"wmwNWWMn":"8w2pFTtBn","wnMmNw":true,"wNWWwMmn":"SCAR","wWNwMmW":4000,…}` → **kill-by-weapon + assists** | high (weapon/attacker), med (bools) |
| `wWNwMmnW` | **seconds alive since last spawn** (+1/60 per tick, reset on respawn) | STEBAH 17.85 s | high |
| `wMNmWwnW` | client clock ms (same as type-28 `WmwNWn`) ≈ time since the client started | 136176 | med |
| `wWnWMN` | **spawn counter** (+1 or +2 per respawn) | | med |
| `wMNW` / `wWnMNwmW` | is alive / is dead-or-spectating | flips on death; spectator has `wWnMNwmW=true` | high |
| `wmMNWn` | spectator flag (true on our seat) | | med |
| `WwMwnW` | **unknown uint16**: 1 for most new accounts, 1000 for the #HIDDEN ranked player, bots also get values (264–1454), top players 14k–31k | rating or lifetime-stat candidate: verify by shortId → getUserProfile | low |
| `wWMmnNW` | per-player input/tick counter (+~60/s); −1 for bots and spectators | | med |
| `wmMNwWWn` + `wWNwMmn` | chain counter 0,1,2,3 → reset on death, plus a multiplier 1.0/1.15/1.30/1.45/1.5 that moves in step | likely movement-chain (bhop/slide) speed bonus | low |
| `wwMnmWNW/wwMnmWN/wwMnmWWN` | velocity xyz | | med |
| `wWnMNm` | 0→1 ramp = ADS/scope progress | | med |
| `wWMmnN`, `wmMNwWn` | decaying floats (hit shake, recoil/spread) | | low |
| `wnMmN, wWWwNnmM, wmwNWM, wNmWMnw, wWwNWn, wWNwMmWn, wwMnNWmW` | input/state booleans (fire, reload, jump, grounded, crouch…) | toggle many times per second | low |
| `wWNwmnW` | uint8 event-code stream per player: 65/55/50 + a counter; 105 in parkour | `[65,50,1,65,2,65,50,1]` | unknown |
| `disconnected___SYNC` | player dropped | Varad2220 false→true | high |
| `wNWWnMwm` | shield (150 just after spawn = spawn protection?) | Bondman_17 150→100 | med |

Type 1 `ScoreboardPlayer` / type 2 (lobby/scoreboard copy) carry the same name/shortId/level/`WwMwnW`/clan
(`wwMnWNW`)/role/skin set.

---

## 3. More lobby / listing data

### 3a. Modes and maps (type 104)
The **official map rotation per mode** (`modes[].mapIds`), mode rules (`weapons`, `needLevel`, `needLogged`,
`isRanked`, `gameType`), and the map catalogue with tags (Experimental / Event) and preview image URLs. Archive
it daily → a "mode/map rotation history" and "new map added / experimental → stable" changelog.

### 3b. Seat reply / room info (type 102)
Same as the listing, plus a room **createdAt** (`WmwNWnM`, ext timestamp: `0x1a1deb3712c` = 1794737664300 ms,
which equals `roundCreatedAt` to the 50 ms).

### 3c. Room metadata keys (listing `WnWwwMm` = op-13 type 0): new guesses
Only two samples (TKO Sk8 12/20, DM Shipment 8/8), so the generic flags are unconfirmed.

| key | value(s) | guess |
|---|---|---|
| `room.WNMWnwm` | 13 / 9 | **connected clients incl. spectators** (not players) |
| `room.WwMwnWmN` | 25 / 25 | max clients incl. spectator slots |
| `room.WmwNWnM` | ext-ts | room created at (ms) |
| `wWMnw` / `wWnMNmwW` | 12/20, 8/8 | players / max players (already used for max) |
| `wWwWmMn` | per-weapon `{skin, isSelected, wear}` | weapon whitelist with forced skin (TKO = Tomahawk + Bayonet only) |
| `wWWwNm` | DM true / TKO false | guns allowed / loadout choice |
| `wWMnwWm` | 1.5 | respawn delay (s) or a multiplier |
| `wmMNWnWw, wWwNWmMn, wmwnMWW, wWmNWMwn, wWNwMnm, wmMNw, wWMwWmn` | all 1 | custom-room multipliers (gravity / speed / damage / jump / fire rate / health …) |
| `wmwnMW, wmWMnNwW, wmMNWWnw, wMNWWw, wWmnwWMN` | true | feature toggles (bots fill, spectators allowed, kill feed, public, …) |
| `wWwNnW, wWNwMnmW, wWWw, wWMnWNm, wWWwNmMn, wWNwmnWM, wWnWMwmN` | false | feature toggles |
| `wWmNMWw, wWmNWMn, wWmnwN, wWnMNwW` | 0 | numeric settings (min ping / team-balance / …) |
| `wWnWM` | 9007199254740991 | JS MAX_SAFE_INTEGER = "no limit" (max level or max ping) |

To pin these: diff the metadata of custom (`USER MODE`) rooms, which change settings, or match the keys to the
bundle's create-room form (`optionCreate`).

---

## 4. Per-player endpoints we can feed with live shortIds (no login, read-only)
Body `{WnWwwNmM: <shortId>, wMWnwm: true}`, see `kirka-everything.md` §2:
- `POST /api/WwMWm/wmMwWn` getUserProfile → uuid, level, XP, **lifetime stats** (games, wins, kills, deaths,
  headshots, score), clan, equipped skin + character, account created.
- `POST /api/WwMWm/wWNwMn` getRankedProfile and `POST /api/WwMWm/wWwWmMN` getMatchHistory (+ `wMNmWWwn` = ranked
  category) → the full ranked match list (won, K, D, score, map, date).
- `POST /api/wMWnwNmW/get_<rotating id>` getInventoryPublic (by uuid from the profile) → inventory value.
- `POST /api/WwMWm/wNmWnw` getUserTrophy.

Ranked rooms show `#HIDDEN` and guests can't spectate login-only rooms, so ranked players are reached through the
leaderboards and history instead.

---

## 5. Ranked feature list

"Have it?" = do we already receive the data. ✔ = in the socket/files today; ◐ = partly; ✘ = not yet.

| # | feature | data needed | have it? | effort |
|---|---|---|---|---|
| 1 | **Live kill feed + damage feed per room** ("Vladimir-Lenin ⌖ Newbie, headshot, 90") | op-13 type 31 + names from state | ✔ received; **dropped by the holder filter** (liveall.py line 67) | tiny: forward op 13, decode 31 |
| 2 | **Headshot % / damage dealt / damage taken per player per match** | type 31 (`WwMwN`, `WmwwMNn`) | ✔ | small |
| 3 | **Kills by weapon / weapon meta per mode and map** | type-8 `wNmWMwnW.wNWWwMmn` at the moment of a kill (31 killed=1) + held weapon `wNWWwMmn` | ✔ in state | small |
| 4 | **Skin and character usage stats** ("most-equipped skins right now", by rarity; tie-in to market prices + skin-library) | loadout arrays `wnMmWwNW` (skin names) | ✔ in state, not output | small |
| 5 | **Round results, MVPs, match end + final scoreboard** | root `wWnWMmNw` (MVP text), team scores, round no., `state___SYNC=end`, snapshot at end | ✔ | small: new `match_result` table |
| 6 | **Per-player match history built from our rosters** (every match a shortId played, final K/D/score, win/loss, map, mode) | match id = room + `roundCreatedAt`, final roster at `end`, team score winner | ◐ we archive once a minute, without the final snapshot | medium |
| 7 | **Player online tracking by shortId** (last seen in room X, sessions/day, playtime), joined with api2 profile (lifetime stats, account age) | live shortIds (rooms) + chat users (uuid/shortId/level) + getUserProfile | ✔ / ✔ / open endpoint | medium (rate-limit api2) |
| 8 | **Clans online now** / clan-vs-clan in the same room | `wwMnWNW` clan tag | ✔ in state | small |
| 9 | **Assists + assist leaderboards** | type-8 attackers list (4 s window) at each kill | ✔ | small |
| 10 | **Map and mode popularity over time** + official rotation history + new-map watch | listing (have) + type 104 `modes[].mapIds`/tags (lobby) | ✔ (lobby frame already captured by the minter tabs) | small |
| 11 | **Kill/death heatmaps on real map geometry** | position at each type-31 kill (state pos or type 28) + op-13 type 1 voxels | ✔ | medium (renderer) |
| 12 | **Survival time / life length, spawn counts, AFK detection** | `wWNwMmnW`, `wWnWMN`, type-28 gaps (>1 s idle) | ✔ | small |
| 13 | **Level distribution / new-player funnel per region** (levels of everyone playing now; guests vs accounts) | `wNWWwmMn` level, shortId | ✔ | tiny |
| 14 | **Bot share and real headcount** (players vs bots vs spectators per room/region); fix the Games page count | no-shortId = bot, `wmMNWn`/`wWnMNwmW` spectator, `wWMnw` vs `WNMWnwm` | ✔ | tiny (Games page: use `wWMnw`) |
| 15 | **Parkour run times / finishers** | PAR `wwMnNWm` finish pos, code 105 in `wWNwmnW`, positions | ◐ needs a recorded finish to confirm | medium |
| 16 | **Live trade-offer archive** (offers / accepts / cancels with item + rarity) | chat type 13, already parsed in `skin-library/src/lib/chat.ts` | ◐ parsed live, **not archived** | small |
| 17 | **In-room chat + join/leave log** | game-room op-13 (type unknown) | ✘ not captured yet: record after #1 | small |
| 18 | Ranked live rooms (1V1/RSAD/POINT2V2/TRAD) | needs a logged-in seat | ✘ (guest only, by design) | ask xip |
| 19 | Movement/aim analytics (speed-chain, 60 Hz aim from type 28) | type 28, `wmMNwWWn`/`wWNwMmn` | ✔, but **anti-cheat territory**: leave to xip, don't publish per-player | n/a |

**Suggested order:** #1 + #2 + #9 (one change in liveall.py plus a type-31 decoder), then #4 + #8 + #13 (add
loadout/clan/level to live.json + `match_roster`), then #5/#6 (final snapshot at `state___SYNC=end` → match_result
+ per-player history), then #7 (join with api2), then #10/#11.

### Label fixes for the code (when building)
- `colyseus.PLAYER_FIELDS`: rename `wNWWwMmn` weaponSkin → **heldWeapon**. Add `wNWWwmMn` level, `wwMnWNW` clan,
  `wnMmWwNW` loadout, `wNmWMwnW` attackers, `wMNW` alive, `wWNwMmnW` aliveSecs.
- Filter the spectator (our own sessionId, `wmMNWn` true, `team ""`) out of rosters. It currently shows as an extra
  "Newbie" with a real shortId (e.g. our `8FQHP1` in session.json).
- `kirka-everything.md` §4.4: `wNWWwmMn` = level (not weapon index). `wMNmWwnW` = client clock. §4.5: type 31 =
  hit event. 67/70 are client → server.
