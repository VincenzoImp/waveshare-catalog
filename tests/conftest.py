"""Shared fixtures: the frozen pages and a scratch database."""

from __future__ import annotations

import gzip
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from waveshare_catalog import store

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    """Read one of the gzipped pages captured from waveshare.com."""
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8", errors="replace") as handle:
        return handle.read()


@pytest.fixture
def category_html() -> str:
    return load("category-lcd-oled-1.html.gz")


@pytest.fixture
def product_html() -> str:
    return load("product-esp32-s3-touch-lcd-3.5.html.gz")


@pytest.fixture
def wiki_html() -> str:
    return load("wiki-esp32-s3-touch-lcd-3.5.html.gz")


@pytest.fixture
def sitemap_xml() -> str:
    return load("sitemap.xml.gz")


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with store.open_db(tmp_path / "test.db") as connection:
        yield connection
