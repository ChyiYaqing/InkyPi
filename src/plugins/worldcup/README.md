# FIFA World Cup 2026 Plugin

Display recent results and upcoming fixtures for the FIFA World Cup 2026 on your InkyPi display.

## Features

- Live match schedule and results from TheSportsDB (free, no API key required)
- Space-aware priority feed: **live matches first**, then today's scores, then the
  soonest upcoming fixtures, and finally recent results
- Per-match status shown as `Live 75'`, `FT Today`, `Today 6:00 PM`, `Tomorrow 10:00 AM`
- Kickoff times converted to your device timezone
- Optional favorite-team filter to show only matches involving one team
- Offline fallback: shows the last saved schedule when the network is unavailable
- High-contrast black & white design optimized for e-ink displays

## Configuration

### Available Settings

1. **Display Mode**
   - `Results & Fixtures` — prioritized feed of live, today, upcoming and recent matches (default)
   - `Recent Results only` — live and finished matches
   - `Upcoming Fixtures only` — live and scheduled matches

2. **Matches shown**
   - How many matches to show in total (1–12, default 6)

3. **Favorite Team (optional)**
   - Enter a team name (e.g. `Brazil`) to show only that team's matches
   - Matching is case-insensitive and partial; leave blank to show all matches
   - Matched matches are emphasized with a double border

4. **Refresh Time**
   - Show or hide the last refresh timestamp (default: Enabled)

## API Information

This plugin uses the [TheSportsDB](https://www.thesportsdb.com/) free API for the
FIFA World Cup league (`id=4429`, season `2026`), with the public test key `3`
(no authentication required). Several feeds are merged and de-duplicated by event id:

- `eventsround.php` — per-round fixtures, including future rounds. Group-stage
  matchdays are rounds `1`–`3`; the knockout rounds use the higher round codes.
  This is the bulk of the schedule, and where upcoming fixtures come from.
- `eventspastleague.php` — most recent and currently-live matches
- `eventsnextleague.php` — the next upcoming kickoff

Multiple feeds are needed because every free-key endpoint only returns a small,
truncated slice, so no single feed has the whole schedule. The round feeds supply
upcoming fixtures, while the fresher past/next feeds add the live game and override
any stale status on matches they share.

Match state is resolved at render time from the match status (`1H`/`2H`/`HT`/minute
for live, `FT`/`AET`/`PEN` for finished) and kickoff time, so a live match — which
already has a score — is never mistaken for a finished one.

## Caching & Offline Behavior

Each successful fetch is cached to `static/cache/worldcup/`. If a later refresh
fails (e.g. no internet), the plugin falls back to the cached schedule and shows
an "Offline" banner with the time of the last successful update. If no cache
exists yet, an "Offline - schedule unavailable" message is shown.

## Troubleshooting

If matches are not displaying:

1. Check your internet connection
2. Verify `https://www.thesportsdb.com` is reachable from your network
3. Check the InkyPi logs for error messages

## Icon

The plugin includes a soccer-ball themed icon (`icon.png`).
