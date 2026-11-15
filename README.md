# Kirka data capture

Archives public Kirka data every few hours via GitHub Actions (`.github/workflows/kirka-daily.yml`), 24/7, no PC needed.
Each run writes a full daily snapshot to `reports/snapshots/<date>.json` and a readable `reports/<date>.md`.
See the Actions tab for runs. The core data (top players, clans, players online) needs no login.
To also capture quests + community maps, add a repository secret `KIRKA_REFRESH` (your Kirka refresh token).

## The stats database (kirka-api/kirka.db)

The detailed engine. A SQLite DB that records, every day, the full state needed to reconstruct any history:
- **players** + **player_daily**: each tracked player's lifetime totals per day (score, kills, deaths, wins, games,
  headshots, KLO per mode, level, coins, diamonds, clan). Day-to-day differences give daily / weekly / monthly / all-time.
- **clans** + **clan_daily**: each clan's score, monthly score, war rank, member count per day.
- **memberships**: every player's clan, role and monthly contribution per day, with the clan-join date. Diffs give
  who joined / left / was promoted and when.
- **leaderboard**: the top of every board each day (solo, clan, ranked).
- **online**: players per region over time.
- **events**: derived join_clan / leave_clan / role_change records.

Built by `tools/collect.py` (public Kirka Hub data, no login) once a day. The registry of players + clans grows every
run, so coverage widens over time. Query it with any SQLite tool.
