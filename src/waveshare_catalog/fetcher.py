"""Fetch pages politely, and never fetch the same page twice."""

from __future__ import annotations

import gzip
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from waveshare_catalog import robots

USER_AGENT = "waveshare-catalog (+https://github.com/VincenzoImp/waveshare-catalog)"

# Statuses worth another go: rate limiting and the transient server-side failures.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(Exception):
    """A page could not be retrieved."""


class Client(Protocol):
    """The slice of an HTTP client this package needs."""

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        """Return the status code and decoded body for `url`."""
        ...


@dataclass(frozen=True, slots=True)
class Page:
    """A page body plus where it came from."""

    url: str
    text: str
    from_cache: bool


class Cache:
    """Gzipped page bodies on disk, keyed by URL.

    Detail parsing has already had to change once (Waveshare replaced the Magento
    variant blob), so keeping the raw HTML means a parser fix costs no network.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()
        return self.root / digest[:2] / f"{digest}.html.gz"

    def read(self, url: str) -> str | None:
        path = self.path_for(url)
        if not path.exists():
            return None
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()

    def write(self, url: str, text: str) -> None:
        path = self.path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)


class Fetcher:
    """Serial fetching that honours robots.txt unless told otherwise.

    The crawl delay is deliberately not something you can forget about: it comes
    from the site's own robots.txt, and overriding it takes an explicit `delay`.
    """

    def __init__(
        self,
        client: Client,
        cache: Cache,
        *,
        delay: float | None = None,
        attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._cache = cache
        self._override = delay
        self._attempts = attempts
        self._sleep = sleep
        self._clock = clock
        self._rules: robots.Rules | None = None
        self._last_request: float | None = None

    def rules_for(self, url: str) -> robots.Rules:
        """Load and remember robots.txt for the site serving `url`."""
        if self._rules is None:
            parts = urlsplit(url)
            robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
            status, body = self._client.get(robots_url, {"User-Agent": USER_AGENT})
            text = body if status == 200 else ""
            self._rules = robots.parse(text, USER_AGENT)
        return self._rules

    @property
    def delay(self) -> float | None:
        """The delay in force, or None until robots.txt has been read."""
        if self._override is not None:
            return self._override
        return None if self._rules is None else self._rules.crawl_delay

    def get(self, url: str) -> Page:
        """Return `url`, from cache when possible, waiting out the crawl delay otherwise.

        Retries the failures that tend to be temporary. A full crawl runs for hours,
        so one refused connection must not end it.
        """
        cached = self._cache.read(url)
        if cached is not None:
            return Page(url=url, text=cached, from_cache=True)

        rules = self.rules_for(url)
        if not rules.allows(urlsplit(url).path):
            raise FetchError(f"robots.txt disallows {url}")

        reason = ""
        for _ in range(self._attempts):
            self._wait()
            try:
                status, body = self._client.get(url, {"User-Agent": USER_AGENT})
            except FetchError as error:
                self._last_request = self._clock()
                reason = str(error)
                continue
            self._last_request = self._clock()
            if status == 200:
                self._cache.write(url, body)
                return Page(url=url, text=body, from_cache=False)
            if status not in RETRYABLE_STATUS:
                raise FetchError(f"{url} returned HTTP {status}")
            reason = f"HTTP {status}"
        raise FetchError(f"{url} failed after {self._attempts} attempts: {reason}")

    def _wait(self) -> None:
        delay = self._override if self._override is not None else self._require_rules().crawl_delay
        if self._last_request is None:
            return
        remaining = delay - (self._clock() - self._last_request)
        if remaining > 0:
            self._sleep(remaining)

    def _require_rules(self) -> robots.Rules:
        assert self._rules is not None  # get() always loads them first
        return self._rules


class HttpxClient:
    """The real client, kept thin so the rest of the package stays testable."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        """Transport failures become FetchError so callers only handle one exception."""
        try:
            response = self._client.get(url, headers=headers)
        except httpx.HTTPError as error:
            raise FetchError(f"{url}: {error}") from error
        return response.status_code, response.text

    def close(self) -> None:
        self._client.close()
