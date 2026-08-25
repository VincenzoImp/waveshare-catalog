"""Tests for CSV and JSONL output."""

from __future__ import annotations

import io
import json
import sqlite3

import pytest

from waveshare_catalog.export import to_csv, to_jsonl
from waveshare_catalog.store import Product, save_products

PRODUCT = Product(
    url="https://www.waveshare.com/a.htm", name="3.5inch, Touch", part_no="A-1", price_min=25.99
)


@pytest.fixture
def rows(db: sqlite3.Connection) -> list[sqlite3.Row]:
    save_products(db, [PRODUCT])
    return list(db.execute("SELECT * FROM products"))


def test_csv_has_a_header_and_one_row_per_product(rows: list[sqlite3.Row]) -> None:
    stream = io.StringIO()

    written = to_csv(rows, stream)
    lines = stream.getvalue().splitlines()

    assert written == 1
    assert lines[0].startswith("url,slug,name,part_no")
    assert '"3.5inch, Touch"' in lines[1]


def test_jsonl_writes_one_object_per_line(rows: list[sqlite3.Row]) -> None:
    stream = io.StringIO()

    written = to_jsonl(rows, stream)
    record = json.loads(stream.getvalue().splitlines()[0])

    assert written == 1
    assert record["part_no"] == "A-1"
    assert record["price_min"] == 25.99


def test_empty_results_still_produce_a_csv_header() -> None:
    stream = io.StringIO()

    assert to_csv([], stream) == 0
    assert stream.getvalue().strip().startswith("url,")


def test_empty_results_produce_no_jsonl() -> None:
    stream = io.StringIO()

    assert to_jsonl([], stream) == 0
    assert stream.getvalue() == ""
