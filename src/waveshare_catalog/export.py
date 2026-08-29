"""Write query results out, for a spreadsheet or for feeding to something else."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable, Sequence
from typing import TextIO

COLUMNS: Sequence[str] = (
    "url",
    "slug",
    "name",
    "part_no",
    "price_min",
    "price_max",
    "image",
    "has_options",
)


def to_csv(rows: Iterable[sqlite3.Row], stream: TextIO) -> int:
    writer = csv.DictWriter(stream, fieldnames=list(COLUMNS), extrasaction="ignore")
    writer.writeheader()
    written = 0
    for row in rows:
        writer.writerow({column: row[column] for column in COLUMNS})
        written += 1
    return written


def to_jsonl(rows: Iterable[sqlite3.Row], stream: TextIO) -> int:
    written = 0
    for row in rows:
        record = {column: row[column] for column in COLUMNS}
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        written += 1
    return written


# `export` promises the fixed set of columns above. An arbitrary query has whatever shape
# it asked for, so these take their columns from the rows themselves.


def rows_to_csv(rows: Sequence[sqlite3.Row], stream: TextIO) -> int:
    if not rows:
        return 0
    writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows([dict(row) for row in rows])
    return len(rows)


def rows_to_jsonl(rows: Sequence[sqlite3.Row], stream: TextIO) -> int:
    for row in rows:
        stream.write(json.dumps(dict(row), ensure_ascii=False, default=str) + "\n")
    return len(rows)


def rows_to_table(rows: Sequence[sqlite3.Row], stream: TextIO) -> int:
    """Columns padded to line up, for reading in a terminal."""
    if not rows:
        stream.write("no rows\n")
        return 0
    columns = list(rows[0].keys())
    text = [["" if row[c] is None else str(row[c]) for c in columns] for row in rows]
    widths = [max(len(c), *(len(line[i]) for line in text)) for i, c in enumerate(columns)]
    stream.write(
        "  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)).rstrip() + "\n"
    )
    stream.write("  ".join("-" * w for w in widths) + "\n")
    for line in text:
        stream.write(
            "  ".join(v.ljust(w) for v, w in zip(line, widths, strict=True)).rstrip() + "\n"
        )
    return len(rows)
