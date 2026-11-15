# Website - the pages

The React/Vite app in `skin-library/` (dev on port 5180). Dark theme, GSAP motion. Sidebar grouped Browse / Trade /
Create / More. Routing in `src/lib/router.ts`, pages wired in `src/App.tsx`, sidebar in `src/components/Side.tsx`.

## Pages

### Browse
- **Library** (`/library`) - the character-skin catalogue: cards with 3D heads, a pixel-world theme, hover shows the
  live 3D model, pagination, filters. Performance-tuned (baked head shading, paginated grid, GPU animations).
- **Weapons** (`/weapons`) - weapon skins per gun, 3D gun previews.
- **Items** (`/items`) - the full item catalogue; opens a detail with market/origin + **"Made by" creator names**.

### Trade
- **Market** (`/market`) - price list, history sparklines, value movers (Luke's data).
- **Deal Radar** (`/deals`) - deal finder.
- **Live** (`/live`) - live global chat + trade offers (`wss://chat.kirka.io`).
- **Players** (`/player`) - look up a player's profile + inventory value (Kirka Hub).
- **Clans** (`/clans`) - clan lookup: roster, scores, war position.
- **Leaderboards** (`/leaderboard`) - solo + clan + ranked boards (live).
- **Traders** (`/traders`) - top traders by volume/trades/profit/net worth; click any for their full trade log,
  profit, best/worst trades, partners, account + inventory net worth. Built from Luke's 2023+ trade archive; archived
  daily into `kirka.db` (`trader_daily`) for net-worth/profit-over-time.
- **Quests** (`/quests`) - hourly/daily/event quests with rewards (global, same for everyone).
- **Shop** (`/shop`) - the in-game shop: sets, bundles, coin/gem packs, character cards expanded to their characters.
- **Games** (`/games`) - live matches per region with map preview, mode, players, join link.

### More
- **Players Online** (`/online`) - live per-region counts + 7-day trend chart + per-region sparklines.
- **Votes** (`/votes`) - Pwnstar's community favourite-skin votes per weapon, with renders.
- **Maps** (`/maps`) - community player-made maps: thumbnail, author, plays/likes, "playing now" badge.
- **Videos** (`/videos`) - featured community YouTube videos + the skin-crafting effects reference.
- **News** (`/news`) - current version, update message, coming soon, 133 patch notes.

### Create
- **Studio** (`/studio`) - the skin editor.

## Creator attribution
Every skin shows **"Made by"** its real creator (official catalogue), merged in `src/lib/meta.ts`, shown in
`ItemFacts.tsx`. Built by `scripts/build_creators.py` -> `public/data/creators.json` (681/1099 characters, 713/1123
weapon skins named).

## Data each page reads
Most pages read a captured `public/*.json` (so a published build works offline) or call Kirka Hub / matchmake live
where CORS allows. See `skin-library/DATA.md` for the exact source per page and the refresh commands.

## Not yet built (next up)
- **Player profile page** with history (rank over time, clan timeline, daily/weekly/monthly/all-time) from `kirka.db`.
- **Clan page** with roster history + join/leave + transfer/poaching graph.
- **Period leaderboards** (week/month/most-improved).
- **The HTTP API** over `kirka.db` (`/player/<id>`, `/clan/<name>`, `/top?period=...`).
- A **homepage/overview** dashboard and a **global player/clan/trader search** (with track-on-search).
