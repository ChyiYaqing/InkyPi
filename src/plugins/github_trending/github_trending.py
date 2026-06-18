from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path
import requests
import logging
from datetime import datetime
from urllib.parse import quote
import pytz
import json
import os
import re
import html as htmllib

logger = logging.getLogger(__name__)

# GitHub Trending has no official API, so the public HTML page is scraped.
GITHUB_TRENDING_URL = "https://github.com/trending"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (InkyPi GitHub Trending plugin)"}

# Supported trending time ranges -> human readable period label
TIME_RANGES = {
    'daily': 'today',
    'weekly': 'this week',
    'monthly': 'this month',
}

class GitHubTrending(BasePlugin):
    CACHE_DIR = resolve_path(os.path.join("static", "cache", "github_trending"))

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['time_ranges'] = TIME_RANGES
        return template_params

    def generate_image(self, settings, device_config):
        try:
            since = settings.get('since', 'weekly')
            if since not in TIME_RANGES:
                since = 'weekly'

            language = (settings.get('language') or '').strip()
            repo_count = self.parse_repo_count(settings.get('repoCount', '8'))
            show_description = settings.get('showDescription', 'true') == 'true'
            refresh_time = settings.get('displayRefreshTime', 'true') == 'true'

            fetch_result = self.fetch_trending(since, language)
            repos = fetch_result['data'][:repo_count]

            timezone_name = device_config.get_config("timezone", default="America/New_York")
            tz = pytz.timezone(timezone_name)
            current_time = datetime.now(tz)

            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]

            template_params = {
                'repos': repos,
                'period_label': TIME_RANGES[since],
                'language': language,
                'show_description': show_description,
                'display_refresh_time': refresh_time,
                'last_refresh_time': current_time.strftime("%b %d, %I:%M %p"),
                'data_status': fetch_result['status'],
                'status_message': fetch_result['message'],
                'data_updated_at': fetch_result.get('updated_at'),
                'plugin_settings': settings
            }

            return self.render_image(
                dimensions,
                'github_trending.html',
                'github_trending.css',
                template_params
            )

        except Exception as e:
            logger.error(f"GitHub Trending image generation failed: {str(e)}")
            raise

    def parse_repo_count(self, value):
        try:
            count = int(value)
        except (TypeError, ValueError):
            return 8
        return max(1, min(count, 25))

    def fetch_trending(self, since, language):
        """Fetch trending repositories from GitHub, falling back to cached data."""
        try:
            page = self.fetch_trending_page(since, language)
            repos = self.parse_trending(page)
            result = {
                'data': repos,
                'status': 'live',
                'message': '',
                'updated_at': datetime.now().strftime("%b %d, %I:%M %p")
            }
            self.write_cached_repos(since, language, result)
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch GitHub trending: {str(e)}")
            cached_result = self.read_cached_repos(since, language)
            if cached_result:
                cached_result['status'] = 'cached'
                cached_result['message'] = 'Offline - showing last saved repositories'
                return cached_result

            return {
                'data': [],
                'status': 'offline',
                'message': 'Offline - trending unavailable',
                'updated_at': None
            }
        except Exception as e:
            logger.error(f"Error processing GitHub trending data: {str(e)}")
            raise RuntimeError(f"Error processing GitHub trending data: {str(e)}")

    def fetch_trending_page(self, since, language):
        url = GITHUB_TRENDING_URL
        if language:
            url = f"{GITHUB_TRENDING_URL}/{quote(language.lower())}"

        response = requests.get(url, params={'since': since}, headers=REQUEST_HEADERS, timeout=15)
        response.raise_for_status()
        return response.text

    def parse_trending(self, page):
        repos = []
        articles = page.split('<article class="Box-row">')[1:]
        for article in articles:
            name_match = re.search(r'href="/([^"/]+/[^"/]+)/stargazers"', article)
            if not name_match:
                continue
            full_name = name_match.group(1)
            owner, _, repo = full_name.partition('/')

            description = ''
            desc_match = re.search(r'<p class="col-9[^"]*">(.*?)</p>', article, re.S)
            if desc_match:
                description = self.clean_text(desc_match.group(1))

            language = ''
            lang_match = re.search(r'itemprop="programmingLanguage">([^<]+)<', article)
            if lang_match:
                language = lang_match.group(1).strip()

            total_stars = ''
            stars_match = re.search(r'/stargazers"[^>]*>.*?</svg>\s*([\d,]+)', article, re.S)
            if stars_match:
                total_stars = stars_match.group(1)

            period_stars = ''
            period_match = re.search(r'([\d,]+)\s+stars\s+(today|this week|this month)', article)
            if period_match:
                period_stars = period_match.group(1)

            repos.append({
                'name': full_name,
                'owner': owner,
                'repo': repo,
                'description': description,
                'language': language,
                'total_stars': total_stars,
                'period_stars': period_stars,
            })

        return repos

    def clean_text(self, value):
        no_tags = re.sub(r'<[^>]+>', '', value)
        return re.sub(r'\s+', ' ', htmllib.unescape(no_tags)).strip()

    def cache_file_path(self, since, language):
        lang = language or 'all'
        key = f"{since}_{lang}"
        safe_key = re.sub(r'[^a-z0-9_-]+', '_', key.lower())
        return os.path.join(self.CACHE_DIR, f"{safe_key}.json")

    def write_cached_repos(self, since, language, result):
        try:
            os.makedirs(self.CACHE_DIR, exist_ok=True)
            with open(self.cache_file_path(since, language), 'w') as cache_file:
                json.dump(result, cache_file)
        except OSError as e:
            logger.warning(f"Failed to write GitHub trending cache: {str(e)}")

    def read_cached_repos(self, since, language):
        try:
            with open(self.cache_file_path(since, language)) as cache_file:
                return json.load(cache_file)
        except (OSError, json.JSONDecodeError) as e:
            logger.info(f"No usable GitHub trending cache found: {str(e)}")
            return None
