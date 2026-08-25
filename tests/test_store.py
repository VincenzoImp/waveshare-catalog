"""Tests for the SQLite store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

from waveshare_catalog.store import (
    Detail,
    Product,
    Variant,
    counts,
    known_product_urls,
    save_categories,
    save_detail,
    save_products,
)

URL = "https://www.waveshare.com/x.htm"

PRODUCT = Product(url=URL, name="A display", part_no="X-1", price_min=9.99, has_options=True)

DETAIL = Detail(
    url=URL,
    description="A display.",
    specs={"Resolution": "320x480"},
    wiki_url="https://www.waveshare.com/wiki/X",
    images=("https://www.waveshare.com/media/catalog/product/x.jpg",),
    variants=(Variant(sku="1", label="with case", attributes=("with case",), unsaleable=False),),
)


def test_saves_and_reads_back_a_product(db: sqlite3.Connection) -> None:
    save_products(db, [PRODUCT])

    row = db.execute("SELECT * FROM products").fetchone()

    assert row["slug"] == "x"
    assert row["part_no"] == "X-1"
    assert row["price_min"] == 9.99
    assert row["has_options"] == 1
    assert known_product_urls(db) == {URL}


def test_saving_the_same_product_twice_updates_it(db: sqlite3.Connection) -> None:
    save_products(db, [PRODUCT])
    save_products(db, [Product(url=URL, name="Renamed", price_min=1.0)])

    row = db.execute("SELECT name, price_min, has_options FROM products").fetchone()

    assert (row["name"], row["price_min"], row["has_options"]) == ("Renamed", 1.0, 0)
    assert counts(db)["products"] == 1


def test_links_products_to_a_category(db: sqlite3.Connection) -> None:
    category = "https://www.waveshare.com/product/displays.htm"

    save_products(db, [PRODUCT], category_url=category)
    save_products(db, [PRODUCT], category_url=category)

    assert counts(db)["product_categories"] == 1


def test_saves_categories_and_updates_them(db: sqlite3.Connection) -> None:
    save_categories(db, [("https://www.waveshare.com/product/displays.htm", "displays", None, 1)])
    save_categories(
        db, [("https://www.waveshare.com/product/displays.htm", "renamed", "parent", 2)]
    )

    row = db.execute("SELECT * FROM categories").fetchone()

    assert (row["name"], row["parent_url"], row["depth"]) == ("renamed", "parent", 2)


def test_saves_a_detail_with_its_variants(db: sqlite3.Connection) -> None:
    save_detail(db, DETAIL)

    detail = db.execute("SELECT * FROM details").fetchone()
    variant = db.execute("SELECT * FROM variants").fetchone()

    assert json.loads(detail["specs_json"]) == {"Resolution": "320x480"}
    assert detail["wiki_url"] == "https://www.waveshare.com/wiki/X"
    assert variant["sku"] == "1"
    assert json.loads(variant["attributes_json"]) == ["with case"]
    assert variant["unsaleable"] == 0


def test_saving_a_detail_twice_updates_it(db: sqlite3.Connection) -> None:
    save_detail(db, DETAIL)
    changed = Variant(sku="1", label="without case", attributes=("without case",), unsaleable=True)

    save_detail(db, replace(DETAIL, variants=(changed,)))

    variant = db.execute("SELECT label, unsaleable FROM variants").fetchone()

    assert (variant["label"], variant["unsaleable"]) == ("without case", 1)
    assert counts(db)["variants"] == 1


def test_counts_every_table(db: sqlite3.Connection) -> None:
    assert counts(db) == {
        "categories": 0,
        "products": 0,
        "product_categories": 0,
        "details": 0,
        "variants": 0,
    }
