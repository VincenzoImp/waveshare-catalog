"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from waveshare_catalog import __version__, export, listing, product, query, sitemap, store, wiki
from waveshare_catalog.fetcher import Cache, Fetcher, FetchError, HttpxClient

DEFAULT_DB = Path("waveshare.db")
DEFAULT_CACHE = Path("cache")

# A category should never need this many pages; the guard stops a broken pager
# from looping forever during an unattended crawl.
MAX_PAGES = 200

# A full crawl runs for hours. Without an occasional commit, everything since the start
# would be lost the moment it is interrupted, even though the pages are safe in the cache.
COMMIT_EVERY = 25


def _shared_arguments() -> argparse.ArgumentParser:
    """The options every command takes, so they work before or after the command name.

    The defaults live on the top-level parser alone: with a default here too, argparse
    would write it over a value the user already gave before the subcommand.
    """
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--db", type=Path, default=argparse.SUPPRESS, help="SQLite file to use")
    shared.add_argument(
        "--cache", type=Path, default=argparse.SUPPRESS, help="page cache directory"
    )
    return shared


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_arguments()
    parser = argparse.ArgumentParser(
        prog="waveshare-catalog",
        description="Collect the Waveshare catalogue locally, then query it offline.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file to use")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="page cache directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser(
        "sync", parents=[shared], help="register every product and read the root listing"
    )
    sync.add_argument("--delay", type=float, help="seconds between requests, overriding robots.txt")
    sync.add_argument(
        "--with-categories",
        action="store_true",
        help="also walk the top-level categories, to record which products belong where",
    )
    sync.add_argument("--limit-categories", type=int, help="stop after this many categories")

    detail = sub.add_parser("detail", parents=[shared], help="fetch full product pages")
    detail.add_argument("--url", action="append", default=[], help="product URL, repeatable")
    detail.add_argument("--name", help="instead of --url, take every product matching this name")
    detail.add_argument(
        "--all", action="store_true", help="every product whose page has not been fetched yet"
    )
    detail.add_argument("--limit", type=int, help="cap how many products are fetched")
    detail.add_argument("--delay", type=float, help="seconds between requests")

    pages = sub.add_parser(
        "wiki", parents=[shared], help="fetch product wikis for the files they link"
    )
    pages.add_argument("--url", action="append", default=[], help="product URL, repeatable")
    pages.add_argument("--name", help="instead of --url, take every product matching this name")
    pages.add_argument(
        "--all", action="store_true", help="every product whose wiki has not been read yet"
    )
    pages.add_argument("--limit", type=int, help="cap how many wikis are fetched")
    pages.add_argument("--delay", type=float, help="seconds between requests")

    find = sub.add_parser("query", parents=[shared], help="filter the local catalogue")
    _add_filter_arguments(find)

    out = sub.add_parser("export", parents=[shared], help="write query results to stdout")
    out.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    _add_filter_arguments(out)

    ask = sub.add_parser(
        "sql", parents=[shared], help="run a read-only query against the catalogue"
    )
    ask.add_argument("statement", help="any SELECT; the database is opened read-only")
    ask.add_argument("--format", choices=("table", "csv", "jsonl"), default="table")

    sub.add_parser(
        "reparse",
        parents=[shared],
        help="re-run the parsers over cached pages, without network",
    )
    sub.add_parser("stats", parents=[shared], help="show how much of the catalogue is collected")
    return parser


def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="substring of the product name")
    parser.add_argument("--part-no", help="substring of the Part No")
    parser.add_argument("--category", help="substring of a category URL")
    parser.add_argument("--price-min", type=float)
    parser.add_argument("--price-max", type=float)
    parser.add_argument("--with-options", action="store_true", help="only multi-option products")
    parser.add_argument("--unlisted", action="store_true", help="only products no category lists")
    parser.add_argument("--limit", type=int)


def _filter_from(args: argparse.Namespace) -> query.Filter:
    return query.Filter(
        name=args.name,
        part_no=args.part_no,
        category=args.category,
        price_min=args.price_min,
        price_max=args.price_max,
        has_options=True if args.with_options else None,
        listed=False if args.unlisted else None,
        limit=args.limit,
    )


def _fetcher(args: argparse.Namespace, delay: float | None) -> Fetcher:
    return Fetcher(HttpxClient(), Cache(args.cache), delay=delay)


def run_sync(
    fetcher: Fetcher,
    connection: sqlite3.Connection,
    limit: int | None,
    out: TextIO,
    *,
    with_categories: bool = False,
) -> int:
    """Register every product the sitemap names, then read the root listing for metadata.

    The root listing is the whole shortcut: it returns 80 products per request and covers
    about 80% of the catalogue in two dozen requests. Walking the category tree instead
    costs ten times as much and finds no more products, so it is opt-in.
    """
    index = sitemap.parse(fetcher.get(sitemap.SITEMAP_URL).text)
    known = set(index.categories)
    store.save_categories(
        connection,
        [
            (url, _category_name(url), sitemap.parent_of(url, known), sitemap.category_depth(url))
            for url in index.categories
        ],
    )
    registered = store.register_products(connection, index.products)
    print(f"sitemap: {registered} products, {len(index.categories)} categories", file=out)

    categories = [sitemap.ROOT_CATEGORY]
    if with_categories:
        # Depth 1 is the best of the category routes: the leaves cost far more and,
        # measured against the sitemap, turn up nothing the root listing missed.
        categories += [url for url in index.categories if sitemap.category_depth(url) == 1]
    if limit is not None:
        categories = categories[:limit]

    listed = 0
    for position, category in enumerate(categories, start=1):
        found = _read_category(fetcher, connection, category, out)
        connection.commit()
        listed += found
        print(f"  [{position}/{len(categories)}] {category} -> {found}", file=out)
    print(f"listed {listed} product rows", file=out)
    return 0


def _read_category(
    fetcher: Fetcher, connection: sqlite3.Connection, category: str, out: TextIO
) -> int:
    """Walk a category's pages until the pager stops offering a next one."""
    found = 0
    for page_number in range(1, MAX_PAGES + 1):
        try:
            page = fetcher.get(listing.page_url(category, page_number))
        except FetchError as error:
            print(f"  skipped {category} page {page_number}: {error}", file=out)
            return found
        products = listing.parse(page.text)
        found += store.save_products(connection, products, category_url=category)
        if not products or not listing.has_next_page(page.text):
            break
    return found


def run_detail(
    fetcher: Fetcher,
    connection: sqlite3.Connection,
    urls: Sequence[str],
    out: TextIO,
) -> int:
    """Fetch and store the full page for each product URL."""
    failures = 0
    for position, url in enumerate(urls, start=1):
        progress = f"[{position}/{len(urls)}{_eta(fetcher, len(urls) - position)}]"
        try:
            page = fetcher.get(url)
        except FetchError as error:
            print(f"  {progress} {url}: {error}", file=out)
            failures += 1
            continue
        detail = product.parse(url, page.text)
        store.save_detail(connection, detail)
        if position % COMMIT_EVERY == 0:
            connection.commit()
        print(f"  {progress} {url} -> {len(detail.variants)} variants", file=out)
    return 1 if failures else 0


def run_wiki(
    fetcher: Fetcher,
    connection: sqlite3.Connection,
    targets: Sequence[tuple[str, str]],
    out: TextIO,
) -> int:
    """Read each product's wiki page and record the files it links."""
    failures = 0
    for position, (product_url, wiki_url) in enumerate(targets, start=1):
        progress = f"[{position}/{len(targets)}{_eta(fetcher, len(targets) - position)}]"
        try:
            page = fetcher.get(wiki.url_of(wiki_url))
        except FetchError as error:
            print(f"  {progress} {wiki_url}: {error}", file=out)
            failures += 1
            continue
        found = store.save_resources(connection, product_url, wiki.parse(page.text))
        if position % COMMIT_EVERY == 0:
            connection.commit()
        print(f"  {progress} {wiki_url} -> {found} files", file=out)
    return 1 if failures else 0


def _wiki_targets(
    connection: sqlite3.Connection, args: argparse.Namespace
) -> list[tuple[str, str]]:
    """The (product, wiki) pairs a run should visit, in catalogue order."""
    # Every branch requires a wiki to exist: naming a product that has none is not an error
    # worth a traceback, it simply leaves nothing to fetch.
    if args.url:
        wanted = ", ".join("?" * len(args.url))
        sql = (
            f"SELECT product_url, wiki_url FROM details WHERE product_url IN ({wanted})"
            " AND wiki_url IS NOT NULL AND wiki_url != ''"
        )
        parameters: list[object] = list(args.url)
    else:
        # Not joined to `products` unless a name is being matched: a page can have been
        # fetched for a URL the listings never named, and its wiki is still worth reading.
        sql = "SELECT d.product_url, d.wiki_url FROM details d"
        parameters = []
        if args.name:
            sql += " JOIN products p ON p.url = d.product_url"
        sql += " WHERE d.wiki_url IS NOT NULL AND d.wiki_url != ''"
        if args.all:
            sql += " AND d.wiki_fetched_at IS NULL"
        if args.name:
            sql += " AND lower(p.name) LIKE ?"
            parameters.append(f"%{args.name.lower()}%")
        sql += " ORDER BY d.product_url"
    if args.limit is not None:
        sql += " LIMIT ?"
        parameters.append(args.limit)
    return [(row["product_url"], row["wiki_url"]) for row in connection.execute(sql, parameters)]


def _eta(fetcher: Fetcher, remaining: int) -> str:
    """Rough time left, which matters when a run is measured in hours."""
    delay = fetcher.delay
    if delay is None or remaining <= 0:
        return ""
    seconds = int(delay * remaining)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f", ~{hours}h{minutes:02d}m left" if hours else f", ~{minutes}m left"


def run_reparse(cache: Cache, connection: sqlite3.Connection, out: TextIO) -> int:
    """Re-run the parsers over every page already on disk, product pages and wikis alike."""
    # `family_specs` is keyed by model rather than by page, so nothing else can clear a row
    # a corrected parser no longer produces. Reparsing covers every cached page, so this is
    # the one place the table can safely be rebuilt from nothing.
    connection.execute("DELETE FROM family_specs")
    reparsed = 0
    for row in connection.execute("SELECT product_url FROM details").fetchall():
        url = row["product_url"]
        text = cache.read(url)
        if text is None:
            continue
        store.save_detail(connection, product.parse(url, text))
        reparsed += 1
    print(f"reparsed {reparsed} products from cache", file=out)

    wikis = 0
    for row in connection.execute(
        "SELECT product_url, wiki_url FROM details"
        " WHERE wiki_url IS NOT NULL AND wiki_url != '' AND wiki_fetched_at IS NOT NULL"
    ).fetchall():
        text = cache.read(wiki.url_of(row["wiki_url"]))
        if text is None:
            continue
        store.save_resources(connection, row["product_url"], wiki.parse(text))
        wikis += 1
    print(f"reparsed {wikis} wikis from cache", file=out)
    return 0


def _category_name(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".htm")


def main(argv: Sequence[str] | None = None) -> int:
    """Run waveshare-catalog and return the process exit code."""
    try:
        return _dispatch(build_parser().parse_args(argv))
    except BrokenPipeError:
        # Downstream closed the pipe, as `| head` does. Exit quietly like other tools,
        # after redirecting stdout so the interpreter's own flush cannot fail too.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


def run_sql(path: Path, statement: str, style: str, out: TextIO) -> int:
    """Answer one query against a read-only connection.

    Read-only is enforced by how the file is opened rather than by inspecting the
    statement, so there is no pattern to slip past. Whatever the caller asks for that
    would write simply fails.
    """
    if not path.exists():
        print(f"no database at {path}", file=out)
        return 1
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(statement).fetchall()
    except sqlite3.Error as error:
        print(f"sql: {error}", file=out)
        return 1
    finally:
        connection.close()
    writer = {
        "csv": export.rows_to_csv,
        "jsonl": export.rows_to_jsonl,
        "table": export.rows_to_table,
    }[style]
    writer(rows, out)
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    out = sys.stdout
    if args.command == "sql":
        # Handled before `open_db`, which would otherwise create and migrate the file.
        return run_sql(args.db, args.statement, args.format, out)
    with store.open_db(args.db) as connection:
        if args.command == "sync":
            with _fetcher(args, args.delay) as fetcher:
                return run_sync(
                    fetcher,
                    connection,
                    args.limit_categories,
                    out,
                    with_categories=args.with_categories,
                )
        if args.command == "detail":
            urls = list(args.url)
            if args.name or args.all:
                criteria = query.Filter(
                    name=args.name, detailed=False if args.all else None, limit=args.limit
                )
                urls += [row["url"] for row in query.search(connection, criteria)]
            if not urls:
                print("nothing to fetch: pass --url, --name or --all", file=out)
                return 1
            with _fetcher(args, args.delay) as fetcher:
                return run_detail(fetcher, connection, urls, out)
        if args.command == "wiki":
            targets = _wiki_targets(connection, args)
            if not targets:
                print("no wikis to fetch: pass --url, --name or --all", file=out)
                return 1
            with _fetcher(args, args.delay) as fetcher:
                return run_wiki(fetcher, connection, targets, out)
        if args.command == "query":
            rows = query.search(connection, _filter_from(args))
            for row in rows:
                price = "-" if row["price_min"] is None else f"${row['price_min']:.2f}"
                print(f"{price:>10}  {row['part_no'] or '-':28}  {row['name']}", file=out)
            print(f"{len(rows)} products", file=out)
            return 0
        if args.command == "export":
            rows = query.search(connection, _filter_from(args))
            writer = export.to_csv if args.format == "csv" else export.to_jsonl
            writer(rows, out)
            return 0
        if args.command == "reparse":
            return run_reparse(Cache(args.cache), connection, out)
        for table, count in store.counts(connection).items():
            print(f"{table:20} {count}", file=out)
        return 0
