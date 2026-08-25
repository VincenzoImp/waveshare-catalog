"""Test doubles, so the suite never touches the network."""

from __future__ import annotations


class FakeClient:
    """Serves canned responses and records what was asked for."""

    def __init__(self, pages: dict[str, tuple[int, str]] | None = None) -> None:
        self.pages = pages or {}
        self.requested: list[str] = []

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        self.requested.append(url)
        return self.pages.get(url, (404, ""))


class FakeClock:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
