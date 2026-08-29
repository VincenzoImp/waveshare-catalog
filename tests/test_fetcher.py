"""Tests for fetching: cache, crawl delay and robots enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from fakes import FakeClient, FakeClock
from waveshare_catalog.fetcher import Cache, Fetcher, FetchError

ROBOTS = "https://www.waveshare.com/robots.txt"
PAGE = "https://www.waveshare.com/x.htm"
POLITE = "User-agent: *\nCrawl-delay: 60\nDisallow: /catalogsearch/\n"


def build(
    tmp_path: Path, pages: dict[str, tuple[int, str]], delay: float | None = None
) -> tuple[Fetcher, FakeClient, FakeClock]:
    client = FakeClient(pages)
    clock = FakeClock()
    fetcher = Fetcher(
        client, Cache(tmp_path / "cache"), delay=delay, sleep=clock.sleep, clock=clock.time
    )
    return fetcher, client, clock


def test_fetches_a_page_and_caches_it(tmp_path: Path) -> None:
    fetcher, client, _ = build(tmp_path, {ROBOTS: (200, POLITE), PAGE: (200, "<html>hi</html>")})

    first = fetcher.get(PAGE)
    second = fetcher.get(PAGE)

    assert first.text == "<html>hi</html>"
    assert not first.from_cache
    assert second.from_cache
    assert client.requested.count(PAGE) == 1


def test_waits_out_the_crawl_delay_between_requests(tmp_path: Path) -> None:
    pages = {ROBOTS: (200, POLITE), PAGE: (200, "a"), PAGE + "?p=2": (200, "b")}
    fetcher, _, clock = build(tmp_path, pages)

    fetcher.get(PAGE)
    fetcher.get(PAGE + "?p=2")

    assert clock.slept == [60.0]


def test_an_explicit_delay_overrides_robots(tmp_path: Path) -> None:
    pages = {ROBOTS: (200, POLITE), PAGE: (200, "a"), PAGE + "?p=2": (200, "b")}
    fetcher, _, clock = build(tmp_path, pages, delay=0.5)

    fetcher.get(PAGE)
    fetcher.get(PAGE + "?p=2")

    assert clock.slept == [0.5]
    assert fetcher.delay == 0.5


def test_does_not_sleep_when_the_delay_has_already_passed(tmp_path: Path) -> None:
    pages = {ROBOTS: (200, POLITE), PAGE: (200, "a"), PAGE + "?p=2": (200, "b")}
    fetcher, _, clock = build(tmp_path, pages, delay=1.0)

    fetcher.get(PAGE)
    clock.now += 5.0
    fetcher.get(PAGE + "?p=2")

    assert clock.slept == []


def test_refuses_a_path_robots_disallows(tmp_path: Path) -> None:
    fetcher, _, _ = build(tmp_path, {ROBOTS: (200, POLITE)})

    with pytest.raises(FetchError, match="disallows"):
        fetcher.get("https://www.waveshare.com/catalogsearch/result/index")


def test_a_missing_robots_file_leaves_the_default_delay(tmp_path: Path) -> None:
    fetcher, _, _ = build(tmp_path, {ROBOTS: (404, ""), PAGE: (200, "a")})

    fetcher.get(PAGE)

    assert fetcher.delay == 60.0


def test_robots_is_read_once(tmp_path: Path) -> None:
    pages = {ROBOTS: (200, POLITE), PAGE: (200, "a"), PAGE + "?p=2": (200, "b")}
    fetcher, client, _ = build(tmp_path, pages)

    fetcher.get(PAGE)
    fetcher.get(PAGE + "?p=2")

    assert client.requested.count(ROBOTS) == 1


def test_the_delay_is_unknown_until_robots_is_read(tmp_path: Path) -> None:
    fetcher, _, _ = build(tmp_path, {ROBOTS: (200, POLITE), PAGE: (200, "a")})

    assert fetcher.delay is None
    fetcher.get(PAGE)
    assert fetcher.delay == 60.0


def test_cache_keys_are_per_url(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")

    cache.write(PAGE, "one")

    assert cache.read(PAGE) == "one"
    assert cache.read(PAGE + "?p=2") is None
    assert cache.path_for(PAGE) != cache.path_for(PAGE + "?p=2")


def test_the_real_client_returns_status_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """HttpxClient is thin, but it is the one place that talks to the network."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"].startswith("waveshare-catalog")
        return httpx.Response(200, text="body")

    from waveshare_catalog.fetcher import USER_AGENT, HttpxClient

    client = HttpxClient()
    monkeypatch.setattr(client, "_client", httpx.Client(transport=httpx.MockTransport(handler)))

    assert client.get(PAGE, {"User-Agent": USER_AGENT}) == (200, "body")
    client.close()


def test_retries_a_transient_server_error(tmp_path: Path) -> None:
    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
            if url.endswith("robots.txt"):
                return 200, POLITE
            self.calls += 1
            return (503, "") if self.calls == 1 else (200, "recovered")

    client = Flaky()
    clock = FakeClock()
    fetcher = Fetcher(client, Cache(tmp_path / "c"), delay=1, sleep=clock.sleep, clock=clock.time)

    assert fetcher.get(PAGE).text == "recovered"
    assert client.calls == 2


def test_retries_a_dropped_connection(tmp_path: Path) -> None:
    class Dropping:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
            if url.endswith("robots.txt"):
                return 200, POLITE
            self.calls += 1
            if self.calls == 1:
                raise FetchError("connection reset")
            return 200, "recovered"

    client = Dropping()
    fetcher = Fetcher(client, Cache(tmp_path / "c"), delay=0)

    assert fetcher.get(PAGE).text == "recovered"


def test_gives_up_after_the_configured_attempts(tmp_path: Path) -> None:
    fetcher, client, _ = build(tmp_path, {ROBOTS: (200, POLITE), PAGE: (503, "")}, delay=0)

    with pytest.raises(FetchError, match="failed after 3 attempts: HTTP 503"):
        fetcher.get(PAGE)

    assert client.requested.count(PAGE) == 3


def test_does_not_retry_a_permanent_error(tmp_path: Path) -> None:
    fetcher, client, _ = build(tmp_path, {ROBOTS: (200, POLITE), PAGE: (404, "")}, delay=0)

    with pytest.raises(FetchError, match="HTTP 404"):
        fetcher.get(PAGE)

    assert client.requested.count(PAGE) == 1


def test_the_real_client_turns_transport_failures_into_fetch_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    from waveshare_catalog.fetcher import USER_AGENT, HttpxClient

    client = HttpxClient()
    monkeypatch.setattr(client, "_client", httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(FetchError, match="refused"):
        client.get(PAGE, {"User-Agent": USER_AGENT})


def test_the_cache_accepts_a_plain_string_path(tmp_path: Path) -> None:
    cache = Cache(str(tmp_path / "cache"))

    cache.write(PAGE, "one")

    assert cache.read(PAGE) == "one"


def test_closing_releases_the_client(tmp_path: Path) -> None:
    """The real client holds a connection pool, so a long crawl must not leak it."""

    class Closable(FakeClient):
        closed = False

        def close(self) -> None:
            self.closed = True

    client = Closable({ROBOTS: (200, POLITE)})
    with Fetcher(client, Cache(tmp_path / "c")) as fetcher:
        assert fetcher.delay is None

    assert client.closed


def test_closing_a_client_without_close_is_harmless(tmp_path: Path) -> None:
    fetcher, _, _ = build(tmp_path, {ROBOTS: (200, POLITE)})

    fetcher.close()
