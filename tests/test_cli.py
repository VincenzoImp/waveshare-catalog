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

SITEMAP_XML = (
    f"<urlset><url><loc>{CATEGORY}</loc></url><url><loc>{PRODUCT_URL}</loc></url></urlset>"
)

LISTING_HTML = """
<ul class="product-list"><li><div class="product-shop">
  <h2 class="product-name"><a href="https://www.waveshare.com/a.htm" title="A display">A</a></h2>
  <div class="product-attr"><p><span>Part No.:</span>A-1</p></div>
  <span class="regular-price"><span class="price">$25.99</span></span>
</div></li></ul>
"""

PRODUCT_HTML = (
    "<script>var waveshare_sku_attributes = "
    '[{"sku ":"1","attributes":["with case"],"unsaleable":false}];</script>'
)

PAGES = {
    ROBOTS: (200, "User-agent: *\nCrawl-delay: 60\n"),
    SITEMAP: (200, SITEMAP_XML),
    f"{CATEGORY}?limit=80&p=1": (200, LISTING_HTML),
    PRODUCT_URL: (200, PRODUCT_HTML),
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
    assert "1 products, 1 categories" in out
    assert rows(workspace, "SELECT * FROM products")[0]["part_no"] == "A-1"
    assert rows(workspace, "SELECT * FROM categories")[0]["name"] == "displays"


def test_sync_can_stop_early(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "sync", "--limit-categories", "0") == 0

    assert "listed 0 product rows" in capsys.readouterr().out


def test_sync_reports_a_category_it_could_not_read(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = {k: v for k, v in PAGES.items() if not k.startswith(CATEGORY)}
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
    assert "products             1" in capsys.readouterr().out


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
        f"{CATEGORY}?limit=80&p=1": (200, first),
        f"{CATEGORY}?limit=80&p=2": (200, second),
    }
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda args, delay: Fetcher(FakeClient(pages), Cache(workspace / "c3"), delay=0),
    )

    assert run(workspace, "sync") == 0

    assert "listed 2 product rows" in capsys.readouterr().out
    assert len(rows(workspace, "SELECT * FROM products")) == 2


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
    assert len(rows(workspace, "SELECT * FROM details")) == 1

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
