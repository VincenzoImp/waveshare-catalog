"""Tests for the SQLite store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from waveshare_catalog.store import (
    Detail,
    Product,
    Variant,
    counts,
    open_db,
    register_products,
    save_categories,
    save_detail,
    save_products,
)

URL = "https://www.waveshare.com/x.htm"

PRODUCT = Product(url=URL, name="A display", part_no="X-1", price_min=9.99, has_options=True)

DETAIL = Detail(
    url=URL,
    description="A display.",
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
        "products_unlisted": 0,
        "details_outdated": 0,
    }


def test_the_product_page_price_range_overrides_the_listing(db: sqlite3.Connection) -> None:
    """A listing shows one figure even for multi-option products; the page shows the range."""
    save_products(db, [PRODUCT])

    save_detail(db, replace(DETAIL, price_min=25.99, price_max=32.99))

    row = db.execute("SELECT price_min, price_max FROM products").fetchone()
    assert (row["price_min"], row["price_max"]) == (25.99, 32.99)


def test_a_detail_without_a_price_leaves_the_listing_alone(db: sqlite3.Connection) -> None:
    save_products(db, [PRODUCT])

    save_detail(db, DETAIL)

    assert db.execute("SELECT price_min FROM products").fetchone()["price_min"] == 9.99


def test_details_written_by_an_older_parser_are_counted(db: sqlite3.Connection) -> None:
    save_detail(db, DETAIL)
    db.execute("UPDATE details SET parser_version = 0")

    assert counts(db)["details_outdated"] == 1


def test_saves_the_option_axes(db: sqlite3.Connection) -> None:
    save_detail(db, replace(DETAIL, axes={"Version Options": ("with case", "without case")}))

    row = db.execute("SELECT axes_json FROM details").fetchone()

    assert json.loads(row["axes_json"]) == {"Version Options": ["with case", "without case"]}


def test_opens_a_database_created_by_an_older_version(tmp_path: Path) -> None:
    """An upgrade must not strand a database that predates the newer columns."""
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE products (url TEXT PRIMARY KEY, slug TEXT, name TEXT, part_no TEXT,"
        " price_min REAL, price_max REAL, currency TEXT, image TEXT, listed_at TEXT);"
        "CREATE TABLE details (product_url TEXT PRIMARY KEY, description TEXT, wiki_url TEXT,"
        " images_json TEXT, fetched_at TEXT, parser_version INTEGER);"
    )
    old.commit()
    old.close()

    with open_db(path) as connection:
        save_products(connection, [PRODUCT])
        save_detail(connection, replace(DETAIL, axes={"Version Options": ("with case",)}))

        assert connection.execute("SELECT has_options FROM products").fetchone()[0] == 1
        assert connection.execute("SELECT axes_json FROM details").fetchone()[0]


def test_registering_a_url_creates_a_bare_product(db: sqlite3.Connection) -> None:
    """Products no category lists exist only in the sitemap, so this is their only way in."""
    registered = register_products(db, ["https://www.waveshare.com/1.02inch-e-paper.htm"])

    row = db.execute("SELECT slug, name FROM products").fetchone()

    assert registered == 1
    assert row["slug"] == "1.02inch-e-paper"
    assert row["name"] is None
    assert counts(db)["products_unlisted"] == 1


def test_registering_never_overwrites_listing_metadata(db: sqlite3.Connection) -> None:
    save_products(db, [PRODUCT])

    register_products(db, [URL])

    row = db.execute("SELECT name, price_min FROM products").fetchone()
    assert (row["name"], row["price_min"]) == ("A display", 9.99)
    assert counts(db)["products_unlisted"] == 0


def test_a_detail_fills_identifying_gaps_without_overwriting(db: sqlite3.Connection) -> None:
    """Listing data wins where it exists; the page only fills what is missing."""
    register_products(db, [URL])

    save_detail(db, replace(DETAIL, name="From the page", part_no="P-9", image="img.jpg"))

    row = db.execute("SELECT name, part_no, image FROM products").fetchone()
    assert (row["name"], row["part_no"], row["image"]) == ("From the page", "P-9", "img.jpg")

    save_products(db, [PRODUCT])
    save_detail(db, replace(DETAIL, name="From the page", part_no="P-9"))

    row = db.execute("SELECT name, part_no FROM products").fetchone()
    assert (row["name"], row["part_no"]) == ("A display", "X-1")
