import json

import pytest
import requests

from src.plugins.crypto.crypto import Crypto


@pytest.fixture
def crypto_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(Crypto, "CACHE_DIR", str(tmp_path))
    return Crypto({"id": "crypto"})


def test_fetch_crypto_prices_uses_cache_when_request_fails(crypto_plugin):
    cached_result = {
        "data": [
            {
                "id": "bitcoin",
                "symbol": "BTC",
                "name": "Bitcoin",
                "price": "10.00",
                "price_raw": 10,
                "change_24h": 1.23,
                "change_direction": "up",
            }
        ],
        "status": "live",
        "message": "",
        "updated_at": "Jun 02, 10:30 AM",
    }

    cache_path = crypto_plugin.cache_file_path(["bitcoin"], "usd")
    with open(cache_path, "w") as cache_file:
        json.dump(cached_result, cache_file)

    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network unavailable")

    crypto_plugin.fetch_coingecko_data = fail_request

    result = crypto_plugin.fetch_crypto_prices(["bitcoin"], "usd")

    assert result["status"] == "cached"
    assert result["message"] == "Offline - showing last saved prices"
    assert result["data"][0]["price"] == "10.00"


def test_fetch_crypto_prices_returns_offline_data_without_cache(crypto_plugin):
    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network unavailable")

    crypto_plugin.fetch_coingecko_data = fail_request

    result = crypto_plugin.fetch_crypto_prices(["bitcoin", "ethereum"], "usd")

    assert result["status"] == "offline"
    assert result["message"] == "Offline - prices unavailable"
    assert [crypto["price"] for crypto in result["data"]] == ["N/A", "N/A"]
