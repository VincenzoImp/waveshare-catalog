"""Tests for the command line, from argv to exit code, over a fake network."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from fakes import FakeClient, FakeClock
from waveshare_catalog import cli
from waveshare_catalog.fetcher import Cache, Fetcher
from waveshare_catalog.store import Product, open_db, save_products

ROBOTS = "https://www.waveshare.com/robots.txt"
SITEMAP = "https://www.waveshare.com/sitemap.xml"
CATEGORY = "https://www.waveshare.com/product/displays.htm"
PRODUCT_URL = "https://www.waveshare.com/a.htm"
# A product the listing never mentions, like the fifth of the real catalogue that
# belongs to no category and is reachable only through the sitemap.
ORPHAN_URL = "https://www.waveshare.com/orphan.htm"
ROOT = "https://www.waveshare.com/product.htm"

SITEMAP_XML = (
    f"<urlset><url><loc>{ROOT}</loc></url><url><loc>{CATEGORY}</loc></url>"
    f"<url><loc>{PRODUCT_URL}</loc></url><url><loc>{ORPHAN_URL}</loc></url></urlset>"
)

LISTING_HTML = """
<ul class="product-list"><li><div class="product-shop">
  <h2 class="product-name"><a href="https://www.waveshare.com/a.htm" title="A display">A</a></h2>
  <div class="product-attr"><p><span>Part No.:</span>A-1</p></div>
  <span class="regular-price"><span class="price">$25.99</span></span>
</div></li></ul>
"""

# Real pages print a comparison matrix of the whole product family, which is the only
# cross-reference between products in the catalogue.
FAMILY_TABLE = (
    "<table><tr><td>Model</td><td>CPU</td><td>a</td><td>b</td><td>c</td><td>d</td></tr>"
    + "".join(
        f"<tr><td>Sibling-{n}</td><td>ESP32</td><td>a</td><td>b</td><td>c</td><td>d</td></tr>"
        for n in range(4)
    )
    + "</table>"
)

WIKI_URL = "https://www.waveshare.com/wiki/A"
WIKI_HTML = (
    '<a href="https://files.waveshare.com/wiki/A/A-2Dand3D.zip">A 2D &amp; 3D diagram</a>'
    '<a href="/wiki/Elsewhere">not a file</a>'
)

WIKI_URL_2 = "https://www.waveshare.com/wiki/Orphan"

PRODUCT_HTML = (
    "<script>var waveshare_sku_attributes = "
    '[{"sku ":"1","attributes":["with case"],"unsaleable":false}];</script>'
    f'<a href="{WIKI_URL}">wiki</a>' + FAMILY_TABLE
)

ORPHAN_HTML = PRODUCT_HTML.replace(WIKI_URL, WIKI_URL_2)

PAGES = {
    ROBOTS: (200, "User-agent: *\nCrawl-delay: 60\n"),
    SITEMAP: (200, SITEMAP_XML),
    f"{ROOT}?limit=80&p=1": (200, LISTING_HTML),
    f"{CATEGORY}?limit=80&p=1": (200, LISTING_HTML),
    PRODUCT_URL: (200, PRODUCT_HTML),
    ORPHAN_URL: (200, ORPHAN_HTML),
    WIKI_URL: (200, WIKI_HTML),
    WIKI_URL_2: (200, WIKI_HTML),
}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the CLI at a scratch database and a fake network."""
    clock = FakeClock()

    def fake_fetcher(args: object, delay: float | None) -> Fetcher:
        return Fetcher(
            FakeClient(PAGES),
            Cache(tmp_path / "cache"),
            delay=delay,
            sleep=clock.sleep,
            clock=clock.time,
        )

    monkeypatch.setattr(cli, "_fetcher", fake_fetcher)
    return tmp_path


def run(workspace: Path, *args: str) -> int:
    return cli.main(
        ["--db", str(workspace / "db.sqlite"), "--cache", str(workspace / "cache"), *args]
    )


def rows(workspace: Path, sql: str) -> list[sqlite3.Row]:
    with open_db(workspace / "db.sqlite") as connection:
        return list(connection.execute(sql))


def test_sync_indexes_the_sitemap_and_reads_categories(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(workspace, "sync") == 0

    out = capsys.readouterr().out
    assert "2 products, 2 categories" in out
    listed = rows(workspace, "SELECT * FROM products WHERE name IS NOT NULL")
    assert listed[0]["part_no"] == "A-1"
    assert {r["name"] for r in rows(workspace, "SELECT * FROM categories")} == {
        "product",
        "displays",
    }


def test_sync_can_stop_early(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "sync", "--limit-categories", "0") == 0

    assert "listed 0 product rows" in capsys.readouterr().out


def test_sync_reports_a_category_it_could_not_read(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = {k: v for k, v in PAGES.items() if not k.startswith(ROOT + "?")}
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda args, delay: Fetcher(FakeClient(pages), Cache(workspace / "c2"), delay=0),
    )

    assert run(workspace, "sync") == 0
    assert "skipped" in capsys.readouterr().out


def test_detail_fetches_one_product(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "detail", "--url", PRODUCT_URL) == 0

    assert "1 variants" in capsys.readouterr().out
    assert rows(workspace, "SELECT * FROM variants")[0]["sku"] == "1"


def test_detail_can_select_products_by_name(workspace: Path) -> None:
    run(workspace, "sync")

    assert run(workspace, "detail", "--name", "display") == 0
    assert len(rows(workspace, "SELECT * FROM details")) == 1


def test_detail_needs_something_to_fetch(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(workspace, "detail") == 1

    assert "nothing to fetch" in capsys.readouterr().out


def test_detail_reports_a_failure(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "detail", "--url", "https://www.waveshare.com/missing.htm") == 1

    assert "HTTP 404" in capsys.readouterr().out


def test_query_prints_matches(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(workspace, "sync")

    assert run(workspace, "query", "--name", "display") == 0

    out = capsys.readouterr().out
    assert "$25.99" in out
    assert "1 products" in out


def test_query_shows_a_dash_when_the_price_is_unknown(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with open_db(workspace / "db.sqlite") as connection:
        save_products(connection, [Product(url=PRODUCT_URL, name="No price")])

    run(workspace, "query")

    assert "-" in capsys.readouterr().out


def test_export_writes_csv_and_jsonl(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(workspace, "sync")
    capsys.readouterr()  # drop the sync progress output

    assert run(workspace, "export", "--format", "csv") == 0
    assert capsys.readouterr().out.startswith("url,slug,name")

    assert run(workspace, "export", "--format", "jsonl") == 0
    assert '"part_no": "A-1"' in capsys.readouterr().out


def test_reparse_replays_the_cache_without_network(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace, "detail", "--url", PRODUCT_URL)

    assert run(workspace, "reparse") == 0
    assert "reparsed 1 products" in capsys.readouterr().out


def test_wiki_records_the_files_a_product_page_never_links(workspace: Path) -> None:
    run(workspace, "detail", "--url", PRODUCT_URL)

    assert run(workspace, "wiki", "--all") == 0

    found = rows(workspace, "SELECT kind, title FROM resources")
    assert [(r["kind"], r["title"]) for r in found] == [("cad", "A 2D & 3D diagram")]


def test_wiki_all_does_not_return_to_a_page_it_has_read(workspace: Path) -> None:
    """The timestamp is written even for a wiki with no downloads, or `--all` would loop."""
    run(workspace, "detail", "--url", PRODUCT_URL)
    run(workspace, "wiki", "--all")

    assert run(workspace, "wiki", "--all") == 1, "nothing left to fetch"


def test_wiki_selects_by_name_and_by_url(workspace: Path) -> None:
    run(workspace, "sync")
    run(workspace, "detail", "--all")

    assert run(workspace, "wiki", "--name", "display", "--limit", "1") == 0
    assert run(workspace, "wiki", "--url", PRODUCT_URL) == 0


def test_wiki_reports_a_page_it_could_not_fetch(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace, "detail", "--url", PRODUCT_URL)
    PAGES[WIKI_URL] = (404, "gone")
    try:
        assert run(workspace, "wiki", "--all") == 1
    finally:
        PAGES[WIKI_URL] = (200, WIKI_HTML)
    assert "returned HTTP 404" in capsys.readouterr().out


def test_sql_answers_a_query_in_each_format(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace, "sync")

    for style, expected in (("table", "part_no"), ("csv", "part_no"), ("jsonl", '"part_no"')):
        assert run(workspace, "sql", "SELECT part_no FROM products", "--format", style) == 0
        assert expected in capsys.readouterr().out


def test_sql_refuses_to_write(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Read-only is a property of how the file is opened, not a pattern match on the text."""
    run(workspace, "sync")

    assert run(workspace, "sql", "DELETE FROM products") == 1
    assert "readonly database" in capsys.readouterr().out


def test_sql_reports_a_broken_query(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(workspace, "sync")

    assert run(workspace, "sql", "SELECT nope FROM products") == 1
    assert "sql: " in capsys.readouterr().out


def test_sql_says_so_when_there_is_no_database(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(workspace, "sql", "SELECT 1") == 1
    assert "no database at" in capsys.readouterr().out


def test_sql_prints_nothing_found_rather_than_an_empty_table(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace, "sync")

    assert run(workspace, "sql", "SELECT * FROM products WHERE url = 'nowhere'") == 0
    assert "no rows" in capsys.readouterr().out


def test_reparse_clears_family_facts_a_corrected_parser_no_longer_states(
    workspace: Path,
) -> None:
    """`family_specs` is keyed by model, so no per-page write can retract a stale row."""
    run(workspace, "detail", "--url", PRODUCT_URL)
    with open_db(workspace / "db.sqlite") as connection:
        connection.execute(
            "INSERT INTO family_specs (model, key, value) VALUES ('Ghost', 'Wrong', '1')"
        )

    assert run(workspace, "reparse") == 0

    models = {row["model"] for row in rows(workspace, "SELECT model FROM family_specs")}
    assert "Ghost" not in models
    assert "Sibling-0" in models, "the matrix the page really prints survives the rebuild"


def test_reparse_skips_products_missing_from_the_cache(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace, "detail", "--url", PRODUCT_URL)
    for path in (workspace / "cache").rglob("*.html.gz"):
        path.unlink()

    assert run(workspace, "reparse") == 0
    assert "reparsed 0 products" in capsys.readouterr().out


def test_stats_counts_the_tables(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(workspace, "sync")

    assert run(workspace, "stats") == 0

    out = capsys.readouterr().out
    assert "products             2" in out
    assert "products_unlisted    1" in out


def test_version_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip()


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2


def test_sync_follows_the_pager_across_pages(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = LISTING_HTML + '<div class="pages"><a class="next" href="?p=2">Next</a></div>'
    second = LISTING_HTML.replace("a.htm", "b.htm").replace("A-1", "B-2")
    pages = {
        **PAGES,
        f"{ROOT}?limit=80&p=1": (200, first),
        f"{ROOT}?limit=80&p=2": (200, second),
    }
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda args, delay: Fetcher(FakeClient(pages), Cache(workspace / "c3"), delay=0),
    )

    assert run(workspace, "sync") == 0

    assert "listed 2 product rows" in capsys.readouterr().out
    named = rows(workspace, "SELECT * FROM products WHERE name IS NOT NULL")
    assert len(named) == 2


def test_the_default_fetcher_is_wired_to_the_real_client(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(["--cache", str(tmp_path), "sync"])

    fetcher = cli._fetcher(args, delay=1.0)

    assert fetcher.delay == 1.0


def test_a_closed_pipe_is_not_an_error(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`waveshare-catalog export | head` must exit quietly, like any other tool."""
    redirected: list[int] = []

    def explode(args: object) -> int:
        raise BrokenPipeError

    monkeypatch.setattr(cli, "_dispatch", explode)
    # Let the handler run without actually closing the descriptor pytest is capturing.
    monkeypatch.setattr(os, "open", lambda path, flags: 99)
    monkeypatch.setattr(os, "dup2", lambda source, target: redirected.append(source))

    assert run(workspace, "export") == 0
    assert redirected == [99]


def test_detail_all_takes_every_product_without_a_page(workspace: Path) -> None:
    run(workspace, "sync")

    assert run(workspace, "detail", "--all") == 0
    assert len(rows(workspace, "SELECT * FROM details")) == 2

    # Second run has nothing left to do, which is what makes a long crawl resumable.
    assert run(workspace, "detail", "--all") == 1


def test_sync_stops_at_the_page_guard(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    endless = LISTING_HTML + '<div class="pages"><a class="next" href="#">Next</a></div>'

    class Endless(FakeClient):
        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
            self.requested.append(url)
            if url.endswith("robots.txt"):
                return 200, "User-agent: *\nCrawl-delay: 60\n"
            if url.endswith("sitemap.xml"):
                return 200, SITEMAP_XML
            return 200, endless

    client = Endless()
    monkeypatch.setattr(cli, "MAX_PAGES", 3)
    monkeypatch.setattr(
        cli, "_fetcher", lambda args, delay: Fetcher(client, Cache(workspace / "c4"), delay=0)
    )

    assert run(workspace, "sync") == 0
    assert sum("limit=80" in url for url in client.requested) == 3


def test_the_eta_is_shown_while_fetching_details(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda args, delay: Fetcher(
            FakeClient(PAGES),
            Cache(workspace / "c5"),
            delay=3600,
            sleep=clock.sleep,
            clock=clock.time,
        ),
    )

    run(workspace, "detail", "--url", PRODUCT_URL, "--url", "https://www.waveshare.com/b.htm")

    assert "1h00m left" in capsys.readouterr().out


def test_sync_reaches_products_that_no_category_lists(workspace: Path) -> None:
    """The point of registering the sitemap: an orphan must become fetchable."""
    run(workspace, "sync")

    urls = {r["url"] for r in rows(workspace, "SELECT url FROM products")}
    assert ORPHAN_URL in urls

    assert run(workspace, "detail", "--all") == 0
    fetched = {r["product_url"] for r in rows(workspace, "SELECT product_url FROM details")}
    assert ORPHAN_URL in fetched


def test_query_can_isolate_the_unlisted_products(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace, "sync")
    capsys.readouterr()

    assert run(workspace, "query", "--unlisted") == 0

    out = capsys.readouterr().out
    assert "1 products" in out


def test_sync_only_reads_the_root_unless_asked_for_categories(workspace: Path) -> None:
    run(workspace, "sync")
    without = {
        r["category_url"] for r in rows(workspace, "SELECT category_url FROM product_categories")
    }

    assert without == {ROOT}


def test_with_categories_adds_the_top_level_listings(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(workspace, "sync", "--with-categories") == 0

    used = {
        r["category_url"] for r in rows(workspace, "SELECT category_url FROM product_categories")
    }
    assert used == {ROOT, CATEGORY}


def test_a_long_detail_run_commits_as_it_goes(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two hours of crawling must not vanish on a Ctrl-C, so progress is committed."""
    seen_by_another_connection: list[int] = []

    class Watching(FakeClient):
        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
            if url == ORPHAN_URL:  # the second product: look at what the first one left
                other = sqlite3.connect(workspace / "db.sqlite")
                try:
                    seen_by_another_connection.append(
                        other.execute("SELECT count(*) FROM details").fetchone()[0]
                    )
                finally:
                    other.close()
            return super().get(url, headers)

    monkeypatch.setattr(cli, "COMMIT_EVERY", 1)
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda args, delay: Fetcher(Watching(PAGES), Cache(workspace / "c6"), delay=0),
    )

    run(workspace, "detail", "--url", PRODUCT_URL, "--url", ORPHAN_URL)

    assert seen_by_another_connection == [1]


def test_a_long_wiki_run_commits_as_it_goes(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1,662 wikis is over an hour of fetching, so the same guarantee has to hold here."""
    seen_by_another_connection: list[int] = []

    class Watching(FakeClient):
        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
            if url == WIKI_URL_2:  # the second wiki: look at what the first one left behind
                other = sqlite3.connect(workspace / "db.sqlite")
                try:
                    seen_by_another_connection.append(
                        other.execute("SELECT count(*) FROM resources").fetchone()[0]
                    )
                finally:
                    other.close()
            return super().get(url, headers)

    run(workspace, "sync")
    run(workspace, "detail", "--all")
    monkeypatch.setattr(cli, "COMMIT_EVERY", 1)
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda args, delay: Fetcher(Watching(PAGES), Cache(workspace / "c7"), delay=0),
    )

    run(workspace, "wiki", "--all")

    assert seen_by_another_connection == [1], "the first wiki was durable before the second ran"


def test_paths_are_accepted_after_the_subcommand(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Almost every CLI takes its global options either side of the command name."""
    assert cli.main(["stats", "--db", str(workspace / "after.db")]) == 0

    assert "products" in capsys.readouterr().out
    assert (workspace / "after.db").exists()


def test_a_path_given_before_the_subcommand_still_wins(workspace: Path) -> None:
    """Regression: a default on the subparser would silently overwrite this one."""
    chosen = workspace / "before.db"

    assert cli.main(["--db", str(chosen), "stats"]) == 0
    assert chosen.exists()

    parsed = cli.build_parser().parse_args(["--db", str(chosen), "stats"])
    assert parsed.db == chosen


def test_the_cache_path_works_in_both_positions(workspace: Path) -> None:
    args = cli.build_parser().parse_args(["--cache", "x", "sync"])
    assert args.cache == Path("x")

    args = cli.build_parser().parse_args(["sync", "--cache", "y"])
    assert args.cache == Path("y")

    assert cli.build_parser().parse_args(["sync"]).cache == cli.DEFAULT_CACHE


def test_reparse_also_reclassifies_wiki_downloads(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wiki pages sit in the same cache, so a fix to their parser must cost no network either."""
    run(workspace, "detail", "--url", PRODUCT_URL)
    run(workspace, "wiki", "--all")
    with open_db(workspace / "db.sqlite") as connection:
        connection.execute("UPDATE resources SET kind = 'wrong'")
    capsys.readouterr()

    assert run(workspace, "reparse") == 0

    assert "reparsed 1 wikis" in capsys.readouterr().out
    assert [r["kind"] for r in rows(workspace, "SELECT kind FROM resources")] == ["cad"]


def test_reparse_skips_a_wiki_missing_from_the_cache(workspace: Path) -> None:
    run(workspace, "detail", "--url", PRODUCT_URL)
    run(workspace, "wiki", "--all")
    for path in (workspace / "cache").rglob("*.html.gz"):
        path.unlink()

    assert run(workspace, "reparse") == 0


def test_wiki_url_naming_a_product_without_one_finds_nothing(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not every product has a wiki; asking for one should say so, not raise."""
    with open_db(workspace / "db.sqlite") as connection:
        connection.execute(
            "INSERT INTO details (product_url, wiki_url) VALUES (?, NULL)", (PRODUCT_URL,)
        )

    assert run(workspace, "wiki", "--url", PRODUCT_URL) == 1
    assert "no wikis to fetch" in capsys.readouterr().out
