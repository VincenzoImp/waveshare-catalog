"""The local catalogue: schema, upserts and the few queries the CLI needs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

PARSER_VERSION = 2

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
    product_url TEXT PRIMARY KEY, description TEXT, axes_json TEXT,
    wiki_url TEXT, images_json TEXT, fetched_at TEXT, parser_version INTEGER,
    wiki_fetched_at TEXT);

CREATE TABLE IF NOT EXISTS variants (
    product_url TEXT, sku TEXT, label TEXT, attributes_json TEXT,
    unsaleable INTEGER, PRIMARY KEY (product_url, sku));

-- One row per fact the page states about the product, key kept verbatim. The catalogue
-- has no fixed vocabulary: 2,570 distinct keys across the whole of it, of which the 40
-- commonest cover under a third, so columns would silently drop the tail. `value` is part
-- of the key because a page may legitimately state one key twice.
CREATE TABLE IF NOT EXISTS specs (
    product_url TEXT, key TEXT, key_norm TEXT, value TEXT, source TEXT,
    PRIMARY KEY (product_url, key, value, source));

-- Which sibling models a page's comparison matrix lists. This is the only cross-reference
-- between products in the catalogue, since categories do not link siblings, so it is what
-- makes "what else is like this?" answerable.
CREATE TABLE IF NOT EXISTS family_members (
    product_url TEXT, model TEXT,
    PRIMARY KEY (product_url, model));

-- What those matrices say about each model, deduplicated across pages. The same matrix is
-- reprinted on every page of a family, so keeping it per page cost 545,688 rows to state
-- fewer than 10,000 facts, and grew the file eightfold. Pages disagree about a model 327
-- times, mostly over punctuation or how a page groups its columns, and `value` is part of
-- the key so every reading survives rather than the last one winning.
CREATE TABLE IF NOT EXISTS family_specs (
    model TEXT, key TEXT, value TEXT,
    PRIMARY KEY (model, key, value));

-- Files the product's wiki page links: CAD geometry, schematics, component datasheets and
-- demo code. The shop page links none of these, so the wiki is their only source.
CREATE TABLE IF NOT EXISTS resources (
    product_url TEXT, kind TEXT, url TEXT, title TEXT,
    PRIMARY KEY (product_url, url));

CREATE INDEX IF NOT EXISTS idx_resources_kind ON resources(kind);
CREATE INDEX IF NOT EXISTS idx_variants_product ON variants(product_url);
CREATE INDEX IF NOT EXISTS idx_prodcat_category ON product_categories(category_url);
CREATE INDEX IF NOT EXISTS idx_specs_keynorm ON specs(key_norm);
CREATE INDEX IF NOT EXISTS idx_family_members_model ON family_members(model);
"""

# Columns introduced after a release. `CREATE TABLE IF NOT EXISTS` leaves an existing
# table alone, so without this an upgrade would fail on a database built by an older
# version. SQLite can add a column but not drop one, which is all this needs.
ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "products": {"has_options": "INTEGER DEFAULT 0"},
    "details": {"axes_json": "TEXT", "wiki_fetched_at": "TEXT"},
}


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
class Spec:
    """One key/value the page states about this product, as written."""

    key: str
    value: str
    source: str = "product_page"

    @property
    def key_norm(self) -> str:
        return " ".join(self.key.lower().split())


@dataclass(frozen=True, slots=True)
class FamilyRow:
    """One cell of the comparison matrix a page prints for its product family."""

    model: str
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class Resource:
    """A file the product's wiki page offers for download."""

    kind: str
    url: str
    title: str


@dataclass(frozen=True, slots=True)
class Detail:
    """What a product page adds on top of its listing row."""

    url: str
    description: str
    wiki_url: str | None
    images: tuple[str, ...]
    variants: tuple[Variant, ...]
    axes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    specs: tuple[Spec, ...] = ()
    family: tuple[FamilyRow, ...] = ()
    price_min: float | None = None
    price_max: float | None = None
    name: str | None = None
    part_no: str | None = None
    image: str | None = None


@contextmanager
def open_db(path: Path) -> Iterator[sqlite3.Connection]:
    """Open `path`, creating the schema when needed, and commit on success."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        _add_missing_columns(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def _add_missing_columns(connection: sqlite3.Connection) -> None:
    """Bring a database created by an older version up to the current schema."""
    for table, columns in ADDED_COLUMNS.items():
        present = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in present:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


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


def register_products(connection: sqlite3.Connection, urls: Iterable[str]) -> int:
    """Record product URLs the sitemap knows about, without touching what is already there.

    Roughly a fifth of the catalogue appears in no category at all, so the sitemap is the
    only place those products are ever named. They land here with a URL and a slug and no
    name, which is what marks them as never listed.
    """
    rows = [(url, Product(url=url, name="").slug) for url in urls]
    connection.executemany("INSERT OR IGNORE INTO products (url, slug) VALUES (?, ?)", rows)
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
        "INSERT INTO details (product_url, description, axes_json, wiki_url, images_json, "
        "fetched_at, parser_version) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(product_url) DO UPDATE SET description=excluded.description, "
        "axes_json=excluded.axes_json, wiki_url=excluded.wiki_url, "
        "images_json=excluded.images_json, fetched_at=excluded.fetched_at, "
        "parser_version=excluded.parser_version",
        (
            detail.url,
            detail.description,
            json.dumps({k: list(v) for k, v in detail.axes.items()}, ensure_ascii=False),
            detail.wiki_url,
            json.dumps(list(detail.images), ensure_ascii=False),
            now,
            PARSER_VERSION,
        ),
    )
    if detail.price_min is not None:
        # The listing shows one price even for multi-option products; the product page
        # carries the real range, so it wins where the two disagree.
        connection.execute(
            "UPDATE products SET price_min = ?, price_max = ? WHERE url = ?",
            (detail.price_min, detail.price_max, detail.url),
        )
    # A fifth of the catalogue is in no listing, so for those products the page is the
    # only source of a name, a Part No and an image. Fill gaps, never overwrite.
    connection.execute(
        "UPDATE products SET name = COALESCE(NULLIF(name, ''), ?), "
        "part_no = COALESCE(NULLIF(part_no, ''), ?), image = COALESCE(image, ?) WHERE url = ?",
        (detail.name, detail.part_no, detail.image, detail.url),
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
    # Replaced rather than merged: a parser fix that stops emitting a wrong row must not
    # leave that row behind after `reparse`.
    connection.execute(
        "DELETE FROM specs WHERE product_url = ? AND source = 'product_page'", (detail.url,)
    )
    connection.executemany(
        "INSERT OR REPLACE INTO specs (product_url, key, key_norm, value, source) "
        "VALUES (?, ?, ?, ?, ?)",
        [(detail.url, s.key, s.key_norm, s.value, s.source) for s in detail.specs],
    )
    connection.execute("DELETE FROM family_members WHERE product_url = ?", (detail.url,))
    connection.executemany(
        "INSERT OR IGNORE INTO family_members (product_url, model) VALUES (?, ?)",
        [(detail.url, model) for model in dict.fromkeys(f.model for f in detail.family)],
    )
    # Not scoped to this page, because the matrix describes the family rather than the page
    # that happens to print it. `reparse` rebuilds the table from scratch, which is where a
    # row left behind by a corrected parser gets cleared.
    connection.executemany(
        "INSERT OR IGNORE INTO family_specs (model, key, value) VALUES (?, ?, ?)",
        [(f.model, f.key, f.value) for f in detail.family],
    )


def save_resources(
    connection: sqlite3.Connection, product_url: str, resources: Iterable[Resource]
) -> int:
    """Record what a product's wiki offers, and that its wiki has now been read.

    The timestamp is written even when the page links nothing, so that `--all` does not
    keep returning to a wiki that simply has no downloads.
    """
    rows = list(resources)
    connection.execute("DELETE FROM resources WHERE product_url = ?", (product_url,))
    connection.executemany(
        "INSERT OR REPLACE INTO resources (product_url, kind, url, title) VALUES (?, ?, ?, ?)",
        [(product_url, r.kind, r.url, r.title) for r in rows],
    )
    connection.execute(
        "UPDATE details SET wiki_fetched_at = ? WHERE product_url = ?",
        (datetime.now(UTC).isoformat(timespec="seconds"), product_url),
    )
    return len(rows)


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Row counts per table, for `stats`."""
    tables = (
        "categories",
        "products",
        "product_categories",
        "details",
        "variants",
        "specs",
        "family_members",
        "family_specs",
        "resources",
    )
    counted = {
        table: int(connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"])
        for table in tables
    }
    # Products known by URL only, because no category lists them.
    counted["products_unlisted"] = int(
        connection.execute(
            "SELECT count(*) AS n FROM products WHERE name IS NULL OR name = ''"
        ).fetchone()["n"]
    )
    # Details written by an older parser: `reparse` refreshes these from the cache.
    counted["details_outdated"] = int(
        connection.execute(
            "SELECT count(*) AS n FROM details WHERE parser_version < ?", (PARSER_VERSION,)
        ).fetchone()["n"]
    )
    # Products with a wiki that has not been read yet, which is what `wiki --all` collects.
    counted["wikis_pending"] = int(
        connection.execute(
            "SELECT count(*) AS n FROM details WHERE wiki_url IS NOT NULL AND wiki_url != '' "
            "AND wiki_fetched_at IS NULL"
        ).fetchone()["n"]
    )
    return counted
