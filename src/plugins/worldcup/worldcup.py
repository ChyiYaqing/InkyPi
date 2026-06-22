from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path
import requests
import logging
from datetime import datetime
import pytz
import json
import os
import re

logger = logging.getLogger(__name__)

# TheSportsDB free API (test key "3", no registration required)
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

# FIFA World Cup league id in TheSportsDB
WORLD_CUP_LEAGUE_ID = "4429"
DEFAULT_SEASON = "2026"

# Rounds to pull per season. 1-3 are the group-stage matchdays; the higher codes
# are TheSportsDB's knockout rounds (R32, R16, QF, SF, Final). Unscheduled rounds
# simply return no events, so listing them is harmless and keeps the plugin
# working once the tournament reaches the knockout stage.
WORLD_CUP_ROUNDS = ["1", "2", "3", "180", "170", "160", "150", "125"]

# Human-friendly stage names for each TheSportsDB round code. Group-stage rounds
# are shown as matchdays; the knockout codes get their proper round names.
ROUND_LABELS = {
    "1": "Matchday 1",
    "2": "Matchday 2",
    "3": "Matchday 3",
    "180": "Round of 32",
    "170": "Round of 16",
    "160": "Quarter-Final",
    "150": "Semi-Final",
    "125": "Final",
}

# Statuses that mean the match has been played
FINISHED_STATUSES = {"FT", "AET", "PEN", "MATCH FINISHED"}

# Statuses that mean the match is currently being played
LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P", "PEN LIVE", "LIVE", "INPLAY", "IN PLAY"}

# A match without an explicit live status is treated as live if kickoff was
# within this many seconds in the past (covers 90' + stoppage + half time).
LIVE_WINDOW_SECONDS = 150 * 60

DISPLAY_MODES = {
    'both': 'Results & Fixtures',
    'results': 'Recent Results only',
    'upcoming': 'Upcoming Fixtures only',
}

class WorldCup(BasePlugin):
    CACHE_DIR = resolve_path(os.path.join("static", "cache", "worldcup"))

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['display_modes'] = DISPLAY_MODES
        return template_params

    def generate_image(self, settings, device_config):
        try:
            display_mode = settings.get('displayMode', 'both')
            if display_mode not in DISPLAY_MODES:
                display_mode = 'both'

            match_count = self.parse_match_count(settings.get('matchCount', '6'))
            favorite_team = (settings.get('favoriteTeam') or '').strip()
            refresh_time = settings.get('displayRefreshTime', 'true') == 'true'

            # Timezone used for both match kickoff times and the refresh timestamp
            timezone_name = device_config.get_config("timezone", default="America/New_York")
            tz = pytz.timezone(timezone_name)
            current_time = datetime.now(tz)

            fetch_result = self.fetch_matches(DEFAULT_SEASON, tz)
            matches = self.apply_favorite(fetch_result['data'], favorite_team)

            # Relative labels (Today / Live / etc.) depend on the current time,
            # so they are computed at render time rather than cached.
            for match in matches:
                self.annotate_match(match, current_time)

            ordered = self.prioritize_matches(matches, display_mode)[:match_count]

            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]

            template_params = {
                'matches': ordered,
                'favorite_team': favorite_team,
                'display_refresh_time': refresh_time,
                'last_refresh_time': current_time.strftime("%b %d, %I:%M %p"),
                'timezone_label': current_time.strftime("%Z") or timezone_name,
                'data_status': fetch_result['status'],
                'status_message': fetch_result['message'],
                'data_updated_at': fetch_result.get('updated_at'),
                'plugin_settings': settings
            }

            return self.render_image(
                dimensions,
                'worldcup.html',
                'worldcup.css',
                template_params
            )

        except Exception as e:
            logger.error(f"World Cup image generation failed: {str(e)}")
            raise

    def parse_match_count(self, value):
        try:
            count = int(value)
        except (TypeError, ValueError):
            return 6
        return max(1, min(count, 12))

    def annotate_match(self, match, now):
        """Attach render-time labels (state, relative day/time, live minute)."""
        kickoff = None
        iso = match.get('kickoff_iso')
        if iso:
            try:
                kickoff = datetime.fromisoformat(iso)
            except ValueError:
                kickoff = None

        match['sort_dt'] = kickoff or now
        match['is_today'] = bool(kickoff) and kickoff.date() == now.date()

        status_upper = (match.get('status') or '').strip().upper()
        has_scores = match['home_score'] is not None and match['away_score'] is not None

        # Resolve state authoritatively here: a live match already has a score,
        # so "has scores" alone cannot mean finished. Prefer explicit statuses,
        # then fall back to the kickoff time.
        is_live = False
        is_finished = False
        live_minute = ''
        if status_upper in LIVE_STATUSES:
            is_live = True
        elif status_upper and status_upper.rstrip("'+").isdigit():
            is_live = True
            live_minute = status_upper if status_upper.endswith("'") else f"{status_upper}'"
        elif status_upper in FINISHED_STATUSES:
            is_finished = True
        elif kickoff:
            elapsed = (now - kickoff).total_seconds()
            if elapsed < 0:
                pass  # upcoming
            elif elapsed <= LIVE_WINDOW_SECONDS:
                is_live = True
            else:
                is_finished = True
        elif has_scores:
            is_finished = True

        if is_live and not live_minute:
            if status_upper == 'HT':
                live_minute = 'HT'
            elif kickoff:
                # No exact minute from the feed; estimate from kickoff but only
                # show it while it stays realistic, otherwise just say "Live".
                elapsed_min = int((now - kickoff).total_seconds() // 60)
                if 0 < elapsed_min <= 105:
                    live_minute = f"{elapsed_min}'"

        if is_live:
            match['state'] = 'live'
        elif is_finished:
            match['state'] = 'finished'
        else:
            match['state'] = 'upcoming'
        match['finished'] = is_finished

        match['live_minute'] = live_minute
        match['day_label'] = self.relative_day(kickoff, now)
        match['time_label'] = kickoff.strftime("%-I:%M %p") if kickoff else 'TBD'

        rnd = (match.get('round') or '').strip()
        stage = ROUND_LABELS.get(rnd) or (f"Round {rnd}" if rnd else '')
        match['round_label'] = f"World Cup · {stage}" if stage else "World Cup"

    def relative_day(self, kickoff, now):
        if not kickoff:
            return 'TBD'
        delta = (kickoff.date() - now.date()).days
        if delta == 0:
            return 'Today'
        if delta == 1:
            return 'Tomorrow'
        if delta == -1:
            return 'Yesterday'
        return kickoff.strftime("%b %-d")

    def prioritize_matches(self, matches, display_mode):
        """Order matches so the most relevant ones surface first.

        Live games come first, then everything else happening today, then the
        soonest upcoming fixtures, and finally the most recent past results.
        """
        live = [m for m in matches if m['state'] == 'live']
        today = [m for m in matches if m['state'] != 'live' and m['is_today']]
        upcoming = [m for m in matches if m['state'] == 'upcoming' and not m['is_today']]
        past = [m for m in matches if m['state'] == 'finished' and not m['is_today']]

        live.sort(key=lambda m: m['sort_dt'])
        today.sort(key=lambda m: m['sort_dt'])
        upcoming.sort(key=lambda m: m['sort_dt'])
        past.sort(key=lambda m: m['sort_dt'], reverse=True)

        if display_mode == 'results':
            return live + [m for m in today if m['state'] == 'finished'] + past
        if display_mode == 'upcoming':
            return live + [m for m in today if m['state'] != 'finished'] + upcoming
        return live + today + upcoming + past

    def apply_favorite(self, matches, favorite_team):
        if not favorite_team:
            return matches

        needle = favorite_team.lower()
        filtered = []
        for match in matches:
            is_favorite = needle in match['home'].lower() or needle in match['away'].lower()
            if is_favorite:
                match = {**match, 'is_favorite': True}
                filtered.append(match)
        return filtered

    def fetch_matches(self, season, tz):
        """Fetch the World Cup schedule from TheSportsDB, falling back to cached data."""
        try:
            events = self.fetch_worldcup_data(season)
            matches = self.parse_matches(events, tz)
            result = {
                'data': matches,
                'status': 'live',
                'message': '',
                'updated_at': datetime.now(tz).strftime("%b %d, %I:%M %p")
            }
            self.write_cached_matches(season, result)
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch World Cup data: {str(e)}")
            cached_result = self.read_cached_matches(season)
            if cached_result:
                cached_result['status'] = 'cached'
                cached_result['message'] = 'Offline - showing last saved schedule'
                return cached_result

            return {
                'data': [],
                'status': 'offline',
                'message': 'Offline - schedule unavailable',
                'updated_at': None
            }
        except Exception as e:
            logger.error(f"Error processing World Cup data: {str(e)}")
            raise RuntimeError(f"Error processing World Cup data: {str(e)}")

    def fetch_worldcup_data(self, season):
        """Merge several TheSportsDB feeds so live and upcoming games are included.

        On the free key every endpoint only returns a small, truncated slice, so
        no single feed has the whole schedule. The per-round feeds give the bulk
        of the fixtures (including future rounds), while the past/next feeds add
        the currently-live game and the next kickoff. Feeds are merged and
        de-duplicated by event id; the round feeds come first and the fresher
        past/next feeds come last so their live status wins on any conflict.
        """
        sources = [
            (f"{SPORTSDB_BASE}/eventsround.php",
             {'id': WORLD_CUP_LEAGUE_ID, 'r': rnd, 's': season})
            for rnd in WORLD_CUP_ROUNDS
        ]
        sources += [
            (f"{SPORTSDB_BASE}/eventspastleague.php", {'id': WORLD_CUP_LEAGUE_ID}),
            (f"{SPORTSDB_BASE}/eventsnextleague.php", {'id': WORLD_CUP_LEAGUE_ID}),
        ]

        merged = {}
        succeeded = False
        last_error = None
        for url, params in sources:
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                events = response.json().get('events') or []
                succeeded = True
            except requests.exceptions.RequestException as e:
                last_error = e
                continue
            for event in events:
                key = event.get('idEvent') or \
                    f"{event.get('strTimestamp')}-{event.get('strHomeTeam')}"
                merged[key] = event

        if not succeeded and last_error is not None:
            raise last_error
        return list(merged.values())

    def parse_matches(self, events, tz):
        matches = []
        for event in events:
            timestamp = event.get('strTimestamp')
            kickoff = self.parse_kickoff(timestamp, event.get('dateEvent'), event.get('strTime'), tz)

            home_score = self.parse_score(event.get('intHomeScore'))
            away_score = self.parse_score(event.get('intAwayScore'))
            status = (event.get('strStatus') or '').strip()
            finished = (home_score is not None and away_score is not None) or \
                status.upper() in FINISHED_STATUSES

            matches.append({
                'home': event.get('strHomeTeam', 'TBD'),
                'away': event.get('strAwayTeam', 'TBD'),
                'home_score': home_score,
                'away_score': away_score,
                'status': status,
                'finished': finished,
                'kickoff_display': kickoff.strftime("%b %d, %I:%M %p") if kickoff else 'TBD',
                'kickoff_iso': kickoff.isoformat() if kickoff else None,
                'sort_key': timestamp or '',
                'round': str(event.get('intRound') or '').strip(),
                'venue': (event.get('strVenue') or '').strip(),
                'is_favorite': False,
            })

        matches.sort(key=lambda m: m['sort_key'])
        return matches

    def parse_kickoff(self, timestamp, date_event, time_event, tz):
        """TheSportsDB timestamps are UTC; convert to the device timezone for display."""
        raw = None
        if timestamp:
            raw = timestamp
        elif date_event:
            raw = f"{date_event}T{time_event or '00:00:00'}"

        if not raw:
            return None

        raw = raw.replace('Z', '')
        try:
            naive = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                naive = datetime.strptime(raw, "%Y-%m-%d")
            except ValueError:
                return None

        return pytz.utc.localize(naive).astimezone(tz)

    def parse_score(self, value):
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def cache_file_path(self, season):
        safe_season = re.sub(r'[^a-z0-9_-]+', '_', str(season).lower())
        return os.path.join(self.CACHE_DIR, f"worldcup_{safe_season}.json")

    def write_cached_matches(self, season, result):
        try:
            os.makedirs(self.CACHE_DIR, exist_ok=True)
            with open(self.cache_file_path(season), 'w') as cache_file:
                json.dump(result, cache_file)
        except OSError as e:
            logger.warning(f"Failed to write World Cup cache: {str(e)}")

    def read_cached_matches(self, season):
        try:
            with open(self.cache_file_path(season)) as cache_file:
                return json.load(cache_file)
        except (OSError, json.JSONDecodeError) as e:
            logger.info(f"No usable World Cup cache found: {str(e)}")
            return None
