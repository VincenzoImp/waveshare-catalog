"""Read the tables a product page prints, instead of flattening them into prose.

A page carries up to three kinds, told apart by shape:

* the product's own spec table, two or four columns of key/value pairs;
* a pinout, the same shape but keyed by pin names;
* a comparison matrix of the whole product family, six columns or more.

The last one is why the flattened description could never be trusted for anything: it
states *other* products' facts, so a text search for "with case" answers about a sibling.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from bs4.element import Tag

# Shapes measured over 120 sampled pages: key/value tables are 2 or 4 columns wide,
# family matrices 6 or more and always several rows deep.
MAX_PAIRED_WIDTH = 4
MAX_PAIRED_ROWS = 40
MIN_FAMILY_WIDTH = 6
MIN_FAMILY_ROWS = 5

# A pinout has the same shape as a spec table, so it is told apart by what its keys say.
_PIN_NAME = re.compile(
    r"^(GND|VCC|VDD|VIN|VBAT|3V3|5V|SDA|SCL|CS|RST|RES|DC|BL|BLK|MOSI|MISO|SCK|SCLK|CLK|"
    r"TX|RX|TXD|RXD|EN|BOOT|NC|D\d{1,2}|IO\d{1,2}|GPIO\d{1,2}|A\d)$",
    re.I,
)
_MIN_PIN_HITS = 3

# A cell spanning an absurd width is broken markup, not a wide table.
_MAX_SPAN = 40

# Shape alone is not enough to recognise a family matrix: a wide specification table looks
# the same, and its first column holds labels like "Sensitivity" or "1D" rather than model
# names. What separates them is what the first column is titled. Sampled over 260 pages,
# this vocabulary covers 63 of the 72 wide tables, and the nine it turns away are package
# contents, chip lists and kit inventories — none of them a product family.
_MODEL_HEADERS = frozenset(
    {
        "part number",
        "partnumber",
        "part no",
        "part no.",
        "partno",
        "model",
        "models",
        "product",
        "product model",
        "product name",
        "name",
    }
)


def read(
    soup: BeautifulSoup,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str, str], ...]]:
    """Every fact the page's tables state: `(key, value)` pairs and family `(model, key, value)`.

    Anything whose shape is not recognised is skipped rather than guessed at, because a
    wrong row in `specs` is worse than a missing one: it looks like a fact.
    """
    pairs: list[tuple[str, str]] = []
    family: list[tuple[str, str, str]] = []
    for table in soup.find_all("table"):
        head, body = _split(table)
        rows = head + body
        if not rows:
            continue
        width = max(len(row) for row in rows)
        if width >= MIN_FAMILY_WIDTH and len(rows) >= MIN_FAMILY_ROWS:
            family.extend(_family(head, body))
        elif 2 <= width <= MAX_PAIRED_WIDTH and len(rows) <= MAX_PAIRED_ROWS:
            pairs.extend(_pairs(rows))
    return tuple(pairs), tuple(family)


def _names_models(header: list[str]) -> bool:
    """Whether the first column is titled as holding product identities."""
    return bool(header) and " ".join(header[0].lower().split()) in _MODEL_HEADERS


def _split(table: Tag) -> tuple[list[list[str]], list[list[str]]]:
    """The table as two rectangles, header and body, with spans expanded."""
    thead = table.find("thead")
    if isinstance(thead, Tag):
        head_rows = thead.find_all("tr")
        body_rows = [tr for tr in table.find_all("tr") if tr not in head_rows]
        return _expand(head_rows), _expand(body_rows)
    return [], _expand(table.find_all("tr"))


def _expand(rows: list[Tag]) -> list[list[str]]:
    """Flatten `colspan` and `rowspan` so every row has one entry per column.

    The family matrix needs this: its "Model" and "Peripheral interfaces" headers carry
    `rowspan=2` while the columns between them are grouped with `colspan`, so the leaf
    header only lines up with the data once both are expanded.
    """
    grid: list[list[str]] = []
    carried: dict[int, tuple[str, int]] = {}
    for row in rows:
        cells = row.find_all(["td", "th"], recursive=False)
        line: list[str] = []
        column = index = 0
        while index < len(cells) or column in carried:
            if column in carried:
                text, left = carried.pop(column)
                line.append(text)
                if left > 1:
                    carried[column] = (text, left - 1)
                column += 1
                continue
            cell = cells[index]
            index += 1
            text = cell.get_text(" ", strip=True)
            down = _span(cell, "rowspan")
            for _ in range(_span(cell, "colspan")):
                line.append(text)
                if down > 1:
                    carried[column] = (text, down - 1)
                column += 1
        grid.append(line)
    return grid


def _span(cell: Tag, name: str) -> int:
    try:
        value = int(str(cell.get(name)))
    except (TypeError, ValueError):
        return 1
    return value if 1 <= value <= _MAX_SPAN else 1


def _pairs(rows: list[list[str]]) -> list[tuple[str, str]]:
    """Key/value pairs read across each row: `key | value | key | value`."""
    found = [
        (row[i].strip(), row[i + 1].strip())
        for row in rows
        for i in range(0, len(row) - 1, 2)
        if row[i].strip() and row[i + 1].strip() and row[i].strip() != row[i + 1].strip()
    ]
    prefix = "pin:" if _looks_like_a_pinout(found) else ""
    return [(prefix + key, value) for key, value in found]


def _looks_like_a_pinout(pairs: list[tuple[str, str]]) -> bool:
    return sum(1 for key, _ in pairs if _PIN_NAME.match(key)) >= _MIN_PIN_HITS


def _family(head: list[list[str]], body: list[list[str]]) -> list[tuple[str, str, str]]:
    """One entry per cell of the comparison matrix, keyed by the model each row names."""
    header = head[-1] if head else (body[0] if body else [])
    if not _names_models(header):
        return []
    rows = body if head else body[1:]
    first = header[0].strip() if header else ""
    out: list[tuple[str, str, str]] = []
    for row in rows:
        model = row[0].strip() if row else ""
        # A row of one repeated value is a section banner such as "AMOLED display",
        # spanning the full width; it names no model.
        if not model or len(set(row)) <= 1 or model == first:
            continue
        for index in range(1, len(row)):
            key = header[index].strip() if index < len(header) else f"column {index}"
            value = row[index].strip()
            if key and value and key != model:
                out.append((model, key, value))
    return out
