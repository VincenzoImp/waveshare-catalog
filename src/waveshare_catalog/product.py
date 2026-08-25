"""Parse a product page: description, specs, wiki link and purchasable variants."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from waveshare_catalog.store import Detail, Variant

# The variant blob is Waveshare's own, not Magento's `spConfig`, and its SKU key
# carries a trailing space: {"sku ": "30733", "attributes": [...], ...}.
_SKU_BLOB = re.compile(r"waveshare_sku_attributes\s*=\s*(\[.*?\])\s*;", re.S)


def parse(url: str, html: str) -> Detail:
    """Everything the product page adds on top of the listing row."""
    soup = BeautifulSoup(html, "lxml")
    return Detail(
        url=url,
        description=_description(soup),
        specs=_specs(soup),
        wiki_url=_wiki_url(soup),
        images=_images(soup),
        variants=_variants(html),
    )


def option_axes(html: str) -> dict[str, tuple[str, ...]]:
    """The option groups shown on the page, such as `Version Options`.

    Kept separate from the variants because the axes are what a human filters on,
    while the variants are what actually has a SKU.
    """
    soup = BeautifulSoup(html, "lxml")
    axes: dict[str, tuple[str, ...]] = {}
    for line in soup.select("div.goods-detail-line"):
        label = line.select_one("div.line-left")
        values = [a.get_text(strip=True) for a in line.select("div.line-right a.tag-text")]
        if label is None or not values:
            continue
        name = label.get_text(strip=True)
        if name:
            axes[name] = tuple(values)
    return axes


def _variants(html: str) -> tuple[Variant, ...]:
    match = _SKU_BLOB.search(html)
    if match is None:
        return ()
    try:
        entries = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ()
    variants: list[Variant] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sku = _sku_of(entry)
        attributes = tuple(str(a) for a in entry.get("attributes", []))
        if sku is None:
            continue
        variants.append(
            Variant(
                sku=sku,
                label=" / ".join(attributes),
                attributes=attributes,
                unsaleable=bool(entry.get("unsaleable", False)),
            )
        )
    return tuple(variants)


def _sku_of(entry: dict[str, object]) -> str | None:
    """Read the SKU whether or not the trailing space in the key is still there."""
    for key in ("sku ", "sku"):
        value = entry.get(key)
        if isinstance(value, str | int):
            return str(value)
    return None


def _description(soup: BeautifulSoup) -> str:
    node = soup.select_one("div.product-description, div.std, div.short-description")
    return node.get_text(" ", strip=True) if node is not None else ""


def _specs(soup: BeautifulSoup) -> dict[str, str]:
    """Two-column spec tables, flattened into name to value."""
    specs: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) != 2:
            continue
        key = cells[0].get_text(" ", strip=True)
        value = cells[1].get_text(" ", strip=True)
        if key and value and key not in specs:
            specs[key] = value
    return specs


def _wiki_url(soup: BeautifulSoup) -> str | None:
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if isinstance(href, str) and "/wiki/" in href:
            return href
    return None


def _images(soup: BeautifulSoup) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for image in soup.select("img[src]"):
        src = image.get("src")
        if isinstance(src, str) and "/media/catalog/product/" in src:
            seen[src] = None
    return tuple(seen)
