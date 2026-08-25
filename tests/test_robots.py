"""Tests for robots.txt parsing."""

from __future__ import annotations

import pytest

from waveshare_catalog import robots

WAVESHARE = """
User-agent: ChatGPT-User
Disallow: /

User-agent: *
Request-rate: 1/60
Crawl-delay: 60
Disallow: /catalogsearch/result/
Disallow: /catalog/category/view/id/
"""


def test_reads_the_wildcard_group_for_an_unknown_agent() -> None:
    rules = robots.parse(WAVESHARE, "waveshare-catalog")

    assert rules.crawl_delay == 60
    assert rules.allows("/esp32-s3-touch-lcd-3.5.htm")
    assert not rules.allows("/catalogsearch/result/index")


def test_prefers_a_group_naming_the_agent() -> None:
    rules = robots.parse(WAVESHARE, "ChatGPT-User")

    assert not rules.allows("/anything")


@pytest.mark.parametrize(
    ("directives", "expected"),
    [
        ("Crawl-delay: 90", 90.0),
        ("Crawl-delay: 5", 60.0),  # never go below the built-in floor
        ("Request-rate: 1/120", 120.0),
        ("Request-rate: 2/60", 60.0),
        ("Crawl-delay: soon", 60.0),
        ("Request-rate: often", 60.0),
        ("Request-rate: 0/60", 60.0),
        ("Request-rate: 1/x", 60.0),
    ],
)
def test_delay_directives(directives: str, expected: float) -> None:
    rules = robots.parse(f"User-agent: *\n{directives}", "bot")

    assert rules.crawl_delay == expected


def test_ignores_comments_blank_lines_and_stray_text() -> None:
    text = "# comment\n\nnonsense\nUser-agent: *\nDisallow: /private/ # trailing\n"

    rules = robots.parse(text, "bot")

    assert not rules.allows("/private/x")
    assert rules.allows("/public")


def test_an_empty_disallow_blocks_nothing() -> None:
    rules = robots.parse("User-agent: *\nDisallow:", "bot")

    assert rules.allows("/anything")


def test_consecutive_agents_share_one_group() -> None:
    text = "User-agent: a\nUser-agent: b\nDisallow: /x/\n"

    for agent in ("a", "b"):
        assert not robots.parse(text, agent).allows("/x/y")


def test_missing_file_falls_back_to_the_floor() -> None:
    rules = robots.parse("", "bot")

    assert rules.crawl_delay == robots.DEFAULT_CRAWL_DELAY
    assert rules.allows("/")


def test_unrelated_directives_are_ignored() -> None:
    rules = robots.parse("User-agent: *\nSitemap: /sitemap.xml\nCrawl-delay: 70", "bot")

    assert rules.crawl_delay == 70.0
