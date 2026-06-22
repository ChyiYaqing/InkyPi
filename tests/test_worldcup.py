import json
from datetime import datetime, timedelta

import pytest
import pytz
import requests

from src.plugins.worldcup.worldcup import WorldCup


@pytest.fixture
def worldcup_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(WorldCup, "CACHE_DIR", str(tmp_path))
    return WorldCup({"id": "worldcup"})


@pytest.fixture
def tz():
    return pytz.utc


SAMPLE_EVENTS = [
    {
        "strHomeTeam": "Mexico",
        "strAwayTeam": "South Africa",
        "intHomeScore": "2",
        "intAwayScore": "0",
        "strStatus": "FT",
        "strTimestamp": "2026-06-11T19:00:00",
        "intRound": "1",
        "strVenue": "Estadio Azteca",
    },
    {
        "strHomeTeam": "Czech Republic",
        "strAwayTeam": "South Africa",
        "intHomeScore": None,
        "intAwayScore": None,
        "strStatus": "",
        "strTimestamp": "2026-06-18T16:00:00",
        "intRound": "2",
        "strVenue": "Mercedes-Benz Stadium",
    },
]


def test_parse_matches_classifies_and_sorts(worldcup_plugin, tz):
    matches = worldcup_plugin.parse_matches(list(reversed(SAMPLE_EVENTS)), tz)

    # Sorted chronologically regardless of input order
    assert [m["home"] for m in matches] == ["Mexico", "Czech Republic"]

    finished = matches[0]
    assert finished["finished"] is True
    assert finished["home_score"] == 2 and finished["away_score"] == 0

    upcoming = matches[1]
    assert upcoming["finished"] is False
    assert upcoming["home_score"] is None


def test_apply_favorite_filters_and_flags(worldcup_plugin, tz):
    matches = worldcup_plugin.parse_matches(SAMPLE_EVENTS, tz)

    filtered = worldcup_plugin.apply_favorite(matches, "mexico")

    assert len(filtered) == 1
    assert filtered[0]["home"] == "Mexico"
    assert filtered[0]["is_favorite"] is True


def test_fetch_matches_uses_cache_when_request_fails(worldcup_plugin, tz):
    cached_result = {
        "data": [
            {
                "home": "Mexico",
                "away": "South Africa",
                "home_score": 2,
                "away_score": 0,
                "status": "FT",
                "finished": True,
                "kickoff_display": "Jun 11, 07:00 PM",
                "sort_key": "2026-06-11T19:00:00",
                "round": "1",
                "venue": "Estadio Azteca",
                "is_favorite": False,
            }
        ],
        "status": "live",
        "message": "",
        "updated_at": "Jun 11, 09:00 PM",
    }

    cache_path = worldcup_plugin.cache_file_path("2026")
    with open(cache_path, "w") as cache_file:
        json.dump(cached_result, cache_file)

    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network unavailable")

    worldcup_plugin.fetch_worldcup_data = fail_request

    result = worldcup_plugin.fetch_matches("2026", tz)

    assert result["status"] == "cached"
    assert result["message"] == "Offline - showing last saved schedule"
    assert result["data"][0]["home"] == "Mexico"


def test_fetch_matches_returns_offline_data_without_cache(worldcup_plugin, tz):
    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network unavailable")

    worldcup_plugin.fetch_worldcup_data = fail_request

    result = worldcup_plugin.fetch_matches("2026", tz)

    assert result["status"] == "offline"
    assert result["message"] == "Offline - schedule unavailable"
    assert result["data"] == []


def _match(state_kickoff_offset_min, finished, status="", scores=(None, None)):
    """Build a parsed-match dict relative to a fixed 'now' for annotation tests."""
    now = datetime(2026, 6, 18, 18, 0, tzinfo=pytz.utc)
    kickoff = now + timedelta(minutes=state_kickoff_offset_min)
    return {
        "home": "Home",
        "away": "Away",
        "home_score": scores[0],
        "away_score": scores[1],
        "status": status,
        "finished": finished,
        "kickoff_iso": kickoff.isoformat(),
        "round": "2",
        "is_favorite": False,
    }, now


def test_annotate_match_detects_live_by_time_window(worldcup_plugin):
    match, now = _match(-50, finished=False)  # kicked off 50 min ago, still playing
    worldcup_plugin.annotate_match(match, now)
    assert match["state"] == "live"
    assert match["live_minute"] == "50'"
    assert match["is_today"] is True


def test_annotate_match_relative_day_labels(worldcup_plugin):
    upcoming, now = _match(60, finished=False)  # later today
    worldcup_plugin.annotate_match(upcoming, now)
    assert upcoming["state"] == "upcoming"
    assert upcoming["day_label"] == "Today"

    tomorrow, now = _match(60 * 24, finished=False)
    worldcup_plugin.annotate_match(tomorrow, now)
    assert tomorrow["day_label"] == "Tomorrow"

    finished, now = _match(-60 * 30, finished=True, status="FT", scores=(1, 0))
    worldcup_plugin.annotate_match(finished, now)
    assert finished["state"] == "finished"
    assert finished["round_label"] == "World Cup · Matchday 2"


def test_prioritize_matches_orders_live_today_upcoming_past(worldcup_plugin):
    live, now = _match(-30, finished=False)
    today_done, _ = _match(-60 * 3, finished=True, status="FT", scores=(2, 1))
    future, _ = _match(60 * 48, finished=False)
    past, _ = _match(-60 * 50, finished=True, status="FT", scores=(0, 0))

    matches = [past, future, today_done, live]
    for m in matches:
        worldcup_plugin.annotate_match(m, now)

    ordered = worldcup_plugin.prioritize_matches(matches, "both")
    assert [m["state"] for m in ordered] == ["live", "finished", "upcoming", "finished"]
    assert ordered[0] is live
    assert ordered[1] is today_done
    assert ordered[3] is past
