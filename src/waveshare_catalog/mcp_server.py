"""Expose the catalogue to an AI agent over MCP, as SQL rather than as fixed filters.

For an agent with a shell there is nothing here worth having: the database is a file and
`sqlite3` is already the best interface to it. This exists for the agents that cannot run
one — a desktop client, a hosted connector — and it deliberately offers the same thing a
shell would, a schema to read and arbitrary read-only SQL, instead of a menu of canned
searches. Filters chosen in advance are what made the CLI useless for the questions people
actually bring to this catalogue.

Install with the extra and point a client at it:

    uv tool install "waveshare-catalog[mcp]"
    waveshare-catalog-mcp            # speaks MCP over stdio
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from mcp.server.mcpserver import MCPServer

# Any single answer has to fit in a model's context, and a careless `SELECT *` over 2,350
# products would not. Callers that want more can page with LIMIT and OFFSET.
MAX_ROWS = 500

# Kept here rather than read from `SCHEMA.md`, which does not travel with an installed
# package. `tests/test_mcp_server.py` asserts the repository's copy still contains this,
# so the two cannot drift.
GUIDE = """\
Tables, and where each one's facts come from.

- products(url, slug, name, part_no, price_min, price_max, image, has_options)
  One row per product. `price_max` is only filled for products whose page was fetched.
  About a fifth appear in no category at all and are known only from the sitemap.
- details(product_url, description, axes_json, wiki_url, images_json, ...)
  `description` is the product's own prose. It no longer contains the family comparison
  matrix, which used to make text searches answer about a sibling instead.
- specs(product_url, key, key_norm, value, source)
  Facts as the page's own specification table states them, keys verbatim. `key_norm` is
  the key lowercased with whitespace collapsed, which is what you should filter on. There
  is no fixed vocabulary: 2,570 distinct keys, the commonest 40 covering under a third.
  Pin assignments are prefixed `pin:`.
- variants(product_url, sku, label, attributes_json, unsaleable)
  One row per purchasable combination. Per-variant prices are not available: the site
  renders them in JavaScript on click, so only the product's range is known.
- family_members(product_url, model) and family_specs(model, key, value)
  The comparison matrix a page prints for its whole product family. This is the only
  cross-reference between related products, since categories do not link siblings. Join
  `family_members.model` to `products.part_no` to keep only siblings in the catalogue.
- resources(product_url, kind, url, title)
  Files the product's wiki links: `cad` (2D/3D geometry, for designing an enclosure),
  `schematic`, `datasheet`, `demo`, `software`. The shop page links none of these.
- categories(url, name, parent_url, depth) and product_categories(product_url, category_url)
  Category membership, which is only populated if the catalogue was collected with
  `sync --with-categories`.
"""

server = MCPServer("waveshare-catalog")


def database_path() -> Path:
    """The catalogue to read, overridable so a client can point at its own copy."""
    return Path(os.environ.get("WAVESHARE_CATALOG_DB", "waveshare.db"))


def describe() -> str:
    """The guide above, followed by what this particular database actually holds."""
    path = database_path()
    if not path.exists():
        return f"{GUIDE}\nNo database at {path}. Set WAVESHARE_CATALOG_DB to point at one."
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        counted = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        lines = [
            f"- {name}: {connection.execute(f'SELECT count(*) FROM {name}').fetchone()[0]:,} rows"
            for (name,) in counted
        ]
    finally:
        connection.close()
    return f"{GUIDE}\nIn {path}:\n" + "\n".join(lines)


def run_query(sql: str) -> str:
    """Run one read-only statement and return its rows as JSON."""
    path = database_path()
    if not path.exists():
        return json.dumps({"error": f"no database at {path}"})
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(sql).fetchmany(MAX_ROWS)
    except sqlite3.Error as error:
        return json.dumps({"error": str(error)})
    finally:
        connection.close()
    return json.dumps(
        {
            "rows": [dict(row) for row in rows],
            "count": len(rows),
            "truncated": len(rows) == MAX_ROWS,
        },
        ensure_ascii=False,
        default=str,
    )


@server.tool()
def schema() -> str:
    """How the catalogue is laid out, what each table means and where its facts come from."""
    return describe()


@server.tool()
def query(sql: str) -> str:
    """Run a read-only SQL SELECT against the catalogue and return the rows as JSON."""
    return run_query(sql)


def main() -> None:
    server.run()
