"""Tests for the MCP server, which offers agents a schema and read-only SQL."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from waveshare_catalog import mcp_server, store

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "waveshare.db"
    with store.open_db(path) as connection:
        store.save_products(connection, [store.Product(url="https://x/a.htm", name="A display")])
    monkeypatch.setenv("WAVESHARE_CATALOG_DB", str(path))
    return path


def test_the_guide_and_the_repository_document_cannot_drift() -> None:
    """`SCHEMA.md` is for people browsing the repository; the guide travels with the package."""
    assert mcp_server.GUIDE.strip() in (REPOSITORY / "SCHEMA.md").read_text(encoding="utf-8")


def test_the_schema_tool_reports_what_this_database_holds(catalogue: Path) -> None:
    described = mcp_server.schema()

    assert "family_members" in described, "the guide is included"
    assert "products: 1 rows" in described, "and so is the live count"


def test_the_schema_tool_says_where_it_looked_when_there_is_no_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAVESHARE_CATALOG_DB", str(tmp_path / "absent.db"))

    assert "No database at" in mcp_server.schema()


def test_the_query_tool_returns_rows_as_json(catalogue: Path) -> None:
    answer = json.loads(mcp_server.query("SELECT name FROM products"))

    assert answer == {"rows": [{"name": "A display"}], "count": 1, "truncated": False}


def test_the_query_tool_refuses_to_write(catalogue: Path) -> None:
    answer = json.loads(mcp_server.query("DELETE FROM products"))

    assert "readonly database" in answer["error"]


def test_the_query_tool_reports_a_broken_statement(catalogue: Path) -> None:
    assert "error" in json.loads(mcp_server.query("SELECT nope FROM products"))


def test_the_query_tool_says_when_there_is_no_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAVESHARE_CATALOG_DB", str(tmp_path / "absent.db"))

    assert "no database at" in json.loads(mcp_server.query("SELECT 1"))["error"]


def test_a_large_answer_is_truncated_and_says_so(catalogue: Path) -> None:
    """A careless SELECT over 2,350 products would not fit in a model's context."""
    monkeypatch_rows = mcp_server.MAX_ROWS
    try:
        mcp_server.MAX_ROWS = 1
        answer = json.loads(mcp_server.query("SELECT 1 UNION ALL SELECT 2"))
    finally:
        mcp_server.MAX_ROWS = monkeypatch_rows

    assert answer["truncated"] is True
    assert answer["count"] == 1


def test_the_database_defaults_to_the_working_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAVESHARE_CATALOG_DB", raising=False)

    assert mcp_server.database_path() == Path("waveshare.db")


def test_main_starts_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []
    monkeypatch.setattr(mcp_server.server, "run", lambda: started.append(True))

    mcp_server.main()

    assert started == [True]


def test_a_plain_install_is_told_which_extra_it_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    """The entry point is declared unconditionally, so it must explain itself, not traceback."""
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)

    with pytest.raises(SystemExit) as failure:
        importlib.reload(mcp_server)

    assert "waveshare-catalog[mcp]" in str(failure.value)
    monkeypatch.undo()
    importlib.reload(mcp_server)  # leave the module usable for every other test
