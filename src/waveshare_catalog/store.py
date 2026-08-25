"""The local catalogue: schema, upserts and the few queries the CLI needs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PARSER_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    url TEXT PRIMARY KEY, name TEXT, parent_url TEXT, depth INTEGER);

CREATE TABLE IF NOT EXISTS products (
    url TEXT PRIMARY KEY, slug TEXT, name TEXT, part_no TEXT,
    price_min REAL, price_max REAL, currency TEXT DEFAULT 'USD',
    image TEXT, has_options INTEGER DEFAULT 0, listed_at TEXT);

CREATE TABLE IF NOT EXISTS product_categories (
    product_url TEXT, category_url TEXT,
    PRIMARY KEY (product_url, category_url));

CREATE TABLE IF NOT EXISTS details (
    product_url TEXT PRIMARY KEY, description TEXT, specs_json TEXT,
    wiki_url TEXT, images_json TEXT, fetched_at TEXT, parser_version INTEGER);

CREATE TABLE IF NOT EXISTS variants (
    product_url TEXT, sku TEXT, label TEXT, attributes_json TEXT,
    unsaleable INTEGER, PRIMARY KEY (product_url, sku));

CREATE INDEX IF NOT EXISTS idx_variants_product ON variants(product_url);
CREATE INDEX IF NOT EXISTS idx_prodcat_category ON product_categories(category_url);
"""


@dataclass(frozen=True, slots=True)
class Product:
    """One row of a category listing."""

    url: str
    name: str
    part_no: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    image: str | None = None
    has_options: bool = False

    @property
    def slug(self) -> str:
        return self.url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".htm")


@dataclass(frozen=True, slots=True)
class Variant:
    """One purchasable combination of a product's options."""

    sku: str
    label: str
    attributes: tuple[str, ...]
    unsaleable: bool


@dataclass(frozen=True, slots=True)
class Detail:
    """What a product page adds on top of its listing row."""

    url: str
    description: str
    specs: dict[str, str]
    wiki_url: str | None
    images: tuple[str, ...]
    variants: tuple[Variant, ...]


@contextmanager
def open_db(path: Path) -> Iterator[sqlite3.Connection]:
    """Open `path`, creating the schema when needed, and commit on success."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        yield connection
        connection.commit()
    finally:
        connection.close()


def save_categories(
    connection: sqlite3.Connection, categories: Iterable[tuple[str, str, str | None, int]]
) -> int:
    rows = list(categories)
    connection.executemany(
        "INSERT INTO categories (url, name, parent_url, depth) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(url) DO UPDATE SET name=excluded.name, parent_url=excluded.parent_url, "
        "depth=excluded.depth",
        rows,
    )
    return len(rows)


def save_products(
    connection: sqlite3.Connection, products: Iterable[Product], category_url: str | None = None
) -> int:
    rows = list(products)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    connection.executemany(
        "INSERT INTO products (url, slug, name, part_no, price_min, price_max, image, "
        "has_options, listed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(url) DO UPDATE SET name=excluded.name, part_no=excluded.part_no, "
        "price_min=excluded.price_min, price_max=excluded.price_max, image=excluded.image, "
        "has_options=excluded.has_options, listed_at=excluded.listed_at",
        [
            (
                p.url,
                p.slug,
                p.name,
                p.part_no,
                p.price_min,
                p.price_max,
                p.image,
                int(p.has_options),
                now,
            )
            for p in rows
        ],
    )
    if category_url is not None:
        connection.executemany(
            "INSERT OR IGNORE INTO product_categories (product_url, category_url) VALUES (?, ?)",
            [(p.url, category_url) for p in rows],
        )
    return len(rows)


def save_detail(connection: sqlite3.Connection, detail: Detail) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    connection.execute(
        "INSERT INTO details (product_url, description, specs_json, wiki_url, images_json, "
        "fetched_at, parser_version) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(product_url) DO UPDATE SET description=excluded.description, "
        "specs_json=excluded.specs_json, wiki_url=excluded.wiki_url, "
        "images_json=excluded.images_json, fetched_at=excluded.fetched_at, "
        "parser_version=excluded.parser_version",
        (
            detail.url,
            detail.description,
            json.dumps(detail.specs, ensure_ascii=False),
            detail.wiki_url,
            json.dumps(list(detail.images), ensure_ascii=False),
            now,
            PARSER_VERSION,
        ),
    )
    connection.executemany(
        "INSERT INTO variants (product_url, sku, label, attributes_json, unsaleable) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(product_url, sku) DO UPDATE SET label=excluded.label, "
        "attributes_json=excluded.attributes_json, unsaleable=excluded.unsaleable",
        [
            (
                detail.url,
                v.sku,
                v.label,
                json.dumps(list(v.attributes), ensure_ascii=False),
                int(v.unsaleable),
            )
            for v in detail.variants
        ],
    )


def known_product_urls(connection: sqlite3.Connection) -> set[str]:
    return {row["url"] for row in connection.execute("SELECT url FROM products")}


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Row counts per table, for `stats`."""
    tables = ("categories", "products", "product_categories", "details", "variants")
    return {
        table: int(connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"])
        for table in tables
    }
