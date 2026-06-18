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
SPORTSDB_SEASON_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsseason.php"

# FIFA World Cup league id in TheSportsDB
WORLD_CUP_LEAGUE_ID = "4429"
DEFAULT_SEASON = "2026"

# Statuses that mean the match has been played
FINISHED_STATUSES = {"FT", "AET", "PEN", "MATCH FINISHED"}

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

            results = [m for m in matches if m['finished']]
            upcoming = [m for m in matches if not m['finished']]

            # Most recent results first, soonest fixtures first
            results = list(reversed(results))[:match_count]
            upcoming = upcoming[:match_count]

            show_results = display_mode in ('both', 'results')
            show_upcoming = display_mode in ('both', 'upcoming')

            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]

            template_params = {
                'results': results if show_results else [],
                'upcoming': upcoming if show_upcoming else [],
                'show_results': show_results,
                'show_upcoming': show_upcoming,
                'favorite_team': favorite_team,
                'display_refresh_time': refresh_time,
                'last_refresh_time': current_time.strftime("%b %d, %I:%M %p"),
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
        params = {'id': WORLD_CUP_LEAGUE_ID, 's': season}
        response = requests.get(SPORTSDB_SEASON_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('events') or []

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
