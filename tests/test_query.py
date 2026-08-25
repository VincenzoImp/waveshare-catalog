"""Tests for filtering the local catalogue."""

from __future__ import annotations

import sqlite3

import pytest

from waveshare_catalog.query import Filter, search
from waveshare_catalog.store import Detail, Product, save_detail, save_products

CATALOGUE = [
    Product(
        url="https://www.waveshare.com/a.htm",
        name="3.5inch Touch LCD",
        part_no="A-1",
        price_min=25.99,
        has_options=True,
    ),
    Product(
        url="https://www.waveshare.com/b.htm",
        name="4.3inch HDMI LCD",
        part_no="B-2",
        price_min=49.99,
    ),
    Product(url="https://www.waveshare.com/c.htm", name="Touch Monitor", part_no="C-3"),
]


@pytest.fixture
def catalogue(db: sqlite3.Connection) -> sqlite3.Connection:
    save_products(db, CATALOGUE, category_url="https://www.waveshare.com/product/displays.htm")
    return db


def urls(rows: list[sqlite3.Row]) -> list[str]:
    return [row["url"].rsplit("/", 1)[-1] for row in rows]


def test_no_filter_returns_everything_cheapest_first(catalogue: sqlite3.Connection) -> None:
    assert urls(search(catalogue, Filter())) == ["a.htm", "b.htm", "c.htm"]


@pytest.mark.parametrize(
    ("criteria", "expected"),
    [
        (Filter(name="touch"), ["a.htm", "c.htm"]),
        (Filter(part_no="B-"), ["b.htm"]),
        (Filter(price_max=30), ["a.htm"]),
        (Filter(price_min=30), ["b.htm"]),
        (Filter(has_options=True), ["a.htm"]),
        (Filter(has_options=False), ["b.htm", "c.htm"]),
        (Filter(category="displays"), ["a.htm", "b.htm", "c.htm"]),
        (Filter(category="sensors"), []),
        (Filter(limit=2), ["a.htm", "b.htm"]),
        (Filter(name="touch", price_max=30), ["a.htm"]),
    ],
)
def test_filters(catalogue: sqlite3.Connection, criteria: Filter, expected: list[str]) -> None:
    assert urls(search(catalogue, criteria)) == expected


def test_can_select_by_whether_the_detail_page_was_fetched(
    catalogue: sqlite3.Connection,
) -> None:
    save_detail(
        catalogue,
        Detail(
            url="https://www.waveshare.com/a.htm",
            description="",
            specs={},
            wiki_url=None,
            images=(),
            variants=(),
        ),
    )

    assert urls(search(catalogue, Filter(detailed=True))) == ["a.htm"]
    assert urls(search(catalogue, Filter(detailed=False))) == ["b.htm", "c.htm"]
