# Kirka data project - documentation

Everything we've built and found for the Kirka stats project. Kept current as we go.

## What this is
A full Kirka.io data capture + analytics system:
- **A website** (`skin-library/`, a React/Vite app) with pages for skins, players, clans, leaderboards, traders,
  shop, quests, games, maps, and more - fed by live Kirka data.
- **A capture pipeline** (`tools/`) that pulls Kirka data every day, with **no login needed for the public parts**.
- **A stats database** (`kirka-api/kirka.db`, SQLite) that records daily history of players, clans, memberships,
  leaderboards and traders - so we own the history nobody else keeps.
- **Daily automation** on the PC (Windows Task) and in the cloud (GitHub Actions, `github.com/omyxheru/kirka-data`),
  so it captures 24/7 and persists offsite.

The goal: our own Kirka stats API/product, built on accumulated history.

## The docs
| File | What it covers |
|---|---|
| [findings.md](findings.md) | Every Kirka API / data source we found, how it works, access notes, and bugs found |
| [pipeline.md](pipeline.md) | The capture tools, the database schema, the daily automation and cloud deploy |
| [website.md](website.md) | Every page on the site and what it shows |
| [kirka-everything.md](kirka-everything.md) | **The full deep reference** - every API, the live game socket protocol, the Colyseus schema format, every decoded field/message, bugs, access, tools. Nothing left out. |

## Other reference (detailed)
- `skin-library/DATA.md` - which source feeds which page; refresh commands.
- `CLOUD-SETUP.md` - the GitHub Actions cloud setup.
- `captures/kirkahub-online-analysis.md` - the deep route-by-route analysis of Kirka Hub + api2.
- `kirka-api/api2/docs-json-20261114.json` - the internal API's full 336-route spec (real operation names).

## Standing rules (how we work on this)
1. **Capture AND archive daily** - every data feature keeps a dated history, never just the latest.
2. **Store in our own DB/API** - `kirka.db` + `reports/snapshots/`, not just a proxy of someone else's live data.
3. **Deploy to GitHub** - push to the `kirka-data` cloud repo so it runs always and persists.
4. **Document everything** - add to these docs the same turn we build or find something.
