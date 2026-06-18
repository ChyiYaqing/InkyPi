import json

import pytest
import requests

from src.plugins.github_trending.github_trending import GitHubTrending


@pytest.fixture
def trending_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(GitHubTrending, "CACHE_DIR", str(tmp_path))
    return GitHubTrending({"id": "github_trending"})


SAMPLE_PAGE = """
<div data-hpc>
  <article class="Box-row">
    <h2 class="h3 lh-condensed"><a href="/apple/container">apple / container</a></h2>
    <p class="col-9 color-fg-muted my-1 tmp-pr-4">
      A tool for creating &amp; running Linux containers.
    </p>
    <div class="f6 color-fg-muted mt-2">
      <span class="repo-language-color"></span>
      <span itemprop="programmingLanguage">Swift</span>
      <a href="/apple/container/stargazers"><svg></svg> 38,424</a>
      <span class="d-inline-block float-sm-right">9,735 stars this week</span>
    </div>
  </article>
  <article class="Box-row">
    <h2 class="h3 lh-condensed"><a href="/iptv-org/iptv">iptv-org / iptv</a></h2>
    <div class="f6 color-fg-muted mt-2">
      <a href="/iptv-org/iptv/stargazers"><svg></svg> 125,315</a>
      <span class="d-inline-block float-sm-right">1,200 stars this week</span>
    </div>
  </article>
</div>
"""


def test_parse_trending_extracts_fields(trending_plugin):
    repos = trending_plugin.parse_trending(SAMPLE_PAGE)

    assert len(repos) == 2

    first = repos[0]
    assert first["name"] == "apple/container"
    assert first["owner"] == "apple"
    assert first["repo"] == "container"
    assert first["language"] == "Swift"
    assert first["total_stars"] == "38,424"
    assert first["period_stars"] == "9,735"
    assert first["description"] == "A tool for creating & running Linux containers."

    # Second repo has no description or language
    second = repos[1]
    assert second["name"] == "iptv-org/iptv"
    assert second["language"] == ""
    assert second["description"] == ""
    assert second["period_stars"] == "1,200"


def test_parse_repo_count_clamps(trending_plugin):
    assert trending_plugin.parse_repo_count("3") == 3
    assert trending_plugin.parse_repo_count("0") == 1
    assert trending_plugin.parse_repo_count("99") == 25
    assert trending_plugin.parse_repo_count("abc") == 8


def test_fetch_trending_uses_cache_when_request_fails(trending_plugin):
    cached_result = {
        "data": [
            {
                "name": "apple/container",
                "owner": "apple",
                "repo": "container",
                "description": "A tool",
                "language": "Swift",
                "total_stars": "38,424",
                "period_stars": "9,735",
            }
        ],
        "status": "live",
        "message": "",
        "updated_at": "Jun 18, 10:30 AM",
    }

    cache_path = trending_plugin.cache_file_path("weekly", "")
    with open(cache_path, "w") as cache_file:
        json.dump(cached_result, cache_file)

    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network unavailable")

    trending_plugin.fetch_trending_page = fail_request

    result = trending_plugin.fetch_trending("weekly", "")

    assert result["status"] == "cached"
    assert result["message"] == "Offline - showing last saved repositories"
    assert result["data"][0]["name"] == "apple/container"


def test_fetch_trending_returns_offline_data_without_cache(trending_plugin):
    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network unavailable")

    trending_plugin.fetch_trending_page = fail_request

    result = trending_plugin.fetch_trending("weekly", "rust")

    assert result["status"] == "offline"
    assert result["message"] == "Offline - trending unavailable"
    assert result["data"] == []
