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

# CoinGecko API endpoints (free, no API key required)
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_COIN_DATA_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"

# Supported cryptocurrencies
SUPPORTED_CRYPTOS = {
    'bitcoin': {'symbol': 'BTC', 'name': 'Bitcoin'},
    'ethereum': {'symbol': 'ETH', 'name': 'Ethereum'},
    'solana': {'symbol': 'SOL', 'name': 'Solana'},
    'dogecoin': {'symbol': 'DOGE', 'name': 'Dogecoin'},
}

# Supported fiat currencies
SUPPORTED_CURRENCIES = {
    'usd': {'symbol': '$', 'name': 'US Dollar'},
    'eur': {'symbol': '€', 'name': 'Euro'},
    'gbp': {'symbol': '£', 'name': 'British Pound'},
    'jpy': {'symbol': '¥', 'name': 'Japanese Yen'},
    'cny': {'symbol': '¥', 'name': 'Chinese Yuan'},
}

class Crypto(BasePlugin):
    CACHE_DIR = resolve_path(os.path.join("static", "cache", "crypto"))

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['currencies'] = SUPPORTED_CURRENCIES
        template_params['cryptos'] = SUPPORTED_CRYPTOS
        return template_params

    def generate_image(self, settings, device_config):
        try:
            # Get settings
            currency = settings.get('currency', 'usd').lower()
            selected_cryptos = self.normalize_crypto_ids(
                settings.get('selectedCryptos', ['bitcoin', 'ethereum', 'solana', 'dogecoin'])
            )
            display_change = settings.get('displayChange', 'true') == 'true'
            refresh_time = settings.get('displayRefreshTime', 'true') == 'true'

            if currency not in SUPPORTED_CURRENCIES:
                currency = 'usd'

            # Fetch crypto data
            crypto_result = self.fetch_crypto_prices(selected_cryptos, currency, display_change)

            # Get timezone for last refresh time
            timezone_name = device_config.get_config("timezone", default="America/New_York")
            tz = pytz.timezone(timezone_name)
            current_time = datetime.now(tz)

            # Prepare template parameters
            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]

            template_params = {
                'crypto_data': crypto_result['data'],
                'currency_symbol': SUPPORTED_CURRENCIES[currency]['symbol'],
                'currency': currency.upper(),
                'display_change': display_change,
                'display_refresh_time': refresh_time,
                'last_refresh_time': current_time.strftime("%b %d, %I:%M %p"),
                'data_status': crypto_result['status'],
                'status_message': crypto_result['message'],
                'data_updated_at': crypto_result.get('updated_at'),
                'plugin_settings': settings
            }

            # Render the image
            return self.render_image(
                dimensions,
                'crypto.html',
                'crypto.css',
                template_params
            )

        except Exception as e:
            logger.error(f"Crypto image generation failed: {str(e)}")
            raise

    def normalize_crypto_ids(self, crypto_ids):
        if isinstance(crypto_ids, str):
            crypto_ids = [crypto_ids]

        normalized = [crypto_id for crypto_id in crypto_ids if crypto_id in SUPPORTED_CRYPTOS]
        return normalized or ['bitcoin', 'ethereum', 'solana', 'dogecoin']

    def fetch_crypto_prices(self, crypto_ids, currency, include_change=True):
        """Fetch cryptocurrency prices from CoinGecko API, falling back to cached data."""
        try:
            data = self.fetch_coingecko_data(crypto_ids, currency, include_change)
            crypto_list = self.parse_crypto_data(data, crypto_ids, currency)
            result = {
                'data': crypto_list,
                'status': 'live',
                'message': '',
                'updated_at': datetime.now().strftime("%b %d, %I:%M %p")
            }
            self.write_cached_prices(crypto_ids, currency, result)
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch crypto prices: {str(e)}")
            cached_result = self.read_cached_prices(crypto_ids, currency)
            if cached_result:
                cached_result['status'] = 'cached'
                cached_result['message'] = 'Offline - showing last saved prices'
                return cached_result

            return {
                'data': self.build_unavailable_crypto_data(crypto_ids),
                'status': 'offline',
                'message': 'Offline - prices unavailable',
                'updated_at': None
            }
        except Exception as e:
            logger.error(f"Error processing crypto data: {str(e)}")
            raise RuntimeError(f"Error processing cryptocurrency data: {str(e)}")

    def fetch_coingecko_data(self, crypto_ids, currency, include_change):
        ids = ','.join(crypto_ids)
        params = {
            'ids': ids,
            'vs_currencies': currency,
        }

        if include_change:
            params['include_24hr_change'] = 'true'
            params['include_24hr_vol'] = 'true'

        response = requests.get(COINGECKO_API_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse_crypto_data(self, data, crypto_ids, currency):
        crypto_list = []
        for crypto_id in crypto_ids:
            if crypto_id in data:
                crypto_info = SUPPORTED_CRYPTOS.get(crypto_id, {})
                price_data = data[crypto_id]

                price = price_data.get(currency, 0)
                change_24h = price_data.get(f'{currency}_24h_change', 0)

                crypto_list.append({
                    'id': crypto_id,
                    'symbol': crypto_info.get('symbol', crypto_id.upper()),
                    'name': crypto_info.get('name', crypto_id.capitalize()),
                    'price': self.format_price(price),
                    'price_raw': price,
                    'change_24h': round(change_24h, 2) if change_24h else 0,
                    'change_direction': 'up' if change_24h > 0 else 'down' if change_24h < 0 else 'neutral'
                })

        return crypto_list

    def build_unavailable_crypto_data(self, crypto_ids):
        crypto_list = []
        for crypto_id in crypto_ids:
            crypto_info = SUPPORTED_CRYPTOS.get(crypto_id, {})
            crypto_list.append({
                'id': crypto_id,
                'symbol': crypto_info.get('symbol', crypto_id.upper()),
                'name': crypto_info.get('name', crypto_id.capitalize()),
                'price': 'N/A',
                'price_raw': None,
                'change_24h': 0,
                'change_direction': 'neutral'
            })

        return crypto_list

    def cache_file_path(self, crypto_ids, currency):
        ids = '_'.join(crypto_ids)
        safe_ids = re.sub(r'[^a-z0-9_-]+', '_', ids.lower())
        safe_currency = re.sub(r'[^a-z0-9_-]+', '_', currency.lower())
        return os.path.join(self.CACHE_DIR, f"{safe_ids}_{safe_currency}.json")

    def write_cached_prices(self, crypto_ids, currency, result):
        try:
            os.makedirs(self.CACHE_DIR, exist_ok=True)
            with open(self.cache_file_path(crypto_ids, currency), 'w') as cache_file:
                json.dump(result, cache_file)
        except OSError as e:
            logger.warning(f"Failed to write crypto price cache: {str(e)}")

    def read_cached_prices(self, crypto_ids, currency):
        try:
            with open(self.cache_file_path(crypto_ids, currency)) as cache_file:
                return json.load(cache_file)
        except (OSError, json.JSONDecodeError) as e:
            logger.info(f"No usable crypto price cache found: {str(e)}")
            return None

    def format_price(self, price):
        """Format price with appropriate decimal places"""
        if price >= 1000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.2f}"
        elif price >= 0.01:
            return f"{price:.4f}"
        else:
            return f"{price:.8f}"
