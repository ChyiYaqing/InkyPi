# GitHub Trending Plugin

Display the trending repositories from [github.com/trending](https://github.com/trending?since=weekly)
on your InkyPi display.

## Features

- Trending repositories for **daily**, **weekly**, or **monthly** time ranges
- Optional filter by programming language (e.g. `python`, `rust`, `go`)
- Ranked list with repository name, description, language, total stars, and
  stars gained in the selected period
- Offline fallback: shows the last saved list when the network is unavailable
- High-contrast black & white design optimized for e-ink displays

## Configuration

### Available Settings

1. **Time Range**
   - `Daily` (today), `Weekly` (this week), `Monthly` (this month)
   - Default: Weekly

2. **Programming Language (optional)**
   - Filter trending to a single language, e.g. `python`
   - Uses the GitHub trending language path (`/trending/<language>`)
   - Leave blank for all languages

3. **Repositories to show**
   - Number of repositories to display (1–25, default 8)

4. **Repository Description**
   - Show or hide each repository's description (default: Enabled)

5. **Refresh Time**
   - Show or hide the last refresh timestamp (default: Enabled)

## Data Source

GitHub does not provide an official Trending API, so this plugin fetches the
public HTML page `https://github.com/trending?since=<range>` (optionally
`/trending/<language>`) and parses the repository entries from it. No API key
or authentication is required.

> Because this relies on scraping the page markup, a future change to GitHub's
> HTML structure could require updating the parser in `parse_trending`.

## Caching & Offline Behavior

Each successful fetch is cached to `static/cache/github_trending/` (keyed by
time range and language). If a later refresh fails, the plugin falls back to the
cached list and shows an "Offline" banner with the time of the last successful
update. If no cache exists yet, an "Offline - trending unavailable" message is
shown.

## Troubleshooting

If repositories are not displaying:

1. Check your internet connection
2. Verify `https://github.com/trending` is reachable from your network
3. Check the InkyPi logs for error messages

## Icon

The plugin includes a trending-themed icon (`icon.png`).
