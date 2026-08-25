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
