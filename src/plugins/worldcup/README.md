# FIFA World Cup 2026 Plugin

Display recent results and upcoming fixtures for the FIFA World Cup 2026 on your InkyPi display.

## Features

- Live match schedule and results from TheSportsDB (free, no API key required)
- Two side-by-side sections: **Recent Results** and **Upcoming Fixtures**
- Kickoff times converted to your device timezone
- Optional favorite-team filter to show only matches involving one team
- Offline fallback: shows the last saved schedule when the network is unavailable
- High-contrast black & white design optimized for e-ink displays

## Configuration

### Available Settings

1. **Display Mode**
   - `Results & Fixtures` — show both sections (default)
   - `Recent Results only`
   - `Upcoming Fixtures only`

2. **Matches per section**
   - How many matches to show in each section (1–12, default 6)

3. **Favorite Team (optional)**
   - Enter a team name (e.g. `Brazil`) to show only that team's matches
   - Matching is case-insensitive and partial; leave blank to show all matches
   - Matched matches are emphasized with a double border

4. **Refresh Time**
   - Show or hide the last refresh timestamp (default: Enabled)

## API Information

This plugin uses the [TheSportsDB](https://www.thesportsdb.com/) free API:

- **Endpoint**: `eventsseason.php` for the FIFA World Cup league (`id=4429`, season `2026`)
- **Authentication**: None (uses the public test key `3`)
- **Data**: Full-season fixture list with scores and match status

A match is treated as finished when it has both scores or a finished status
(`FT`, `AET`, `PEN`). Everything else is shown as an upcoming fixture.

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
