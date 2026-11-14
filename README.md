# Kirka data capture

Archives public Kirka data every few hours via GitHub Actions (`.github/workflows/kirka-daily.yml`), 24/7, no PC needed.
Each run writes a full daily snapshot to `reports/snapshots/<date>.json` and a readable `reports/<date>.md`.
See the Actions tab for runs. The core data (top players, clans, players online) needs no login.
To also capture quests + community maps, add a repository secret `KIRKA_REFRESH` (your Kirka refresh token).
