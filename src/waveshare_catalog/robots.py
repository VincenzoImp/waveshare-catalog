"""Parse robots.txt well enough to obey it."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CRAWL_DELAY = 60.0


@dataclass(frozen=True, slots=True)
class Rules:
    """The directives that apply to one user agent."""

    crawl_delay: float
    disallowed: tuple[str, ...] = field(default=())

    def allows(self, path: str) -> bool:
        """Whether `path` may be fetched. An empty Disallow means "nothing is blocked"."""
        return not any(path.startswith(prefix) for prefix in self.disallowed if prefix)


def parse(text: str, user_agent: str) -> Rules:
    """Read `text` and return the rules for `user_agent`, falling back to the `*` group.

    A group is a run of User-agent lines followed by directives. Only the most
    specific matching group applies, which for our purposes means: prefer a group
    naming our agent, otherwise use the wildcard.
    """
    groups: dict[str, list[tuple[str, str]]] = {}
    current: list[str] = []
    previous_was_agent = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        key = field_name.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if not previous_was_agent:
                current = []
            current.append(value.lower())
            groups.setdefault(value.lower(), [])
            previous_was_agent = True
            continue
        previous_was_agent = False
        for agent in current:
            groups.setdefault(agent, []).append((key, value))

    wanted = user_agent.lower()
    directives = groups.get(wanted)
    if directives is None:
        directives = groups.get("*", [])
    return _rules_from(directives)


def _rules_from(directives: list[tuple[str, str]]) -> Rules:
    delay = DEFAULT_CRAWL_DELAY
    disallowed: list[str] = []
    for key, value in directives:
        if key == "crawl-delay":
            delay = max(delay, _as_float(value, delay))
        elif key == "request-rate":
            delay = max(delay, _rate_to_delay(value, delay))
        elif key == "disallow":
            disallowed.append(value)
    return Rules(crawl_delay=delay, disallowed=tuple(disallowed))


def _as_float(value: str, fallback: float) -> float:
    try:
        return float(value)
    except ValueError:
        return fallback


def _rate_to_delay(value: str, fallback: float) -> float:
    """Turn a `documents/seconds` rate such as `1/60` into seconds per request."""
    requests, _, seconds = value.partition("/")
    try:
        count, window = float(requests), float(seconds)
    except ValueError:
        return fallback
    if count <= 0 or window <= 0:
        return fallback
    return window / count
