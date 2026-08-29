"""Parse a product page: description, price range, wiki link and purchasable variants."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from waveshare_catalog.store import Detail, Variant

# The variant blob is Waveshare's own, not Magento's `spConfig`, and its SKU key
# carries a trailing space: {"sku ": "30733", "attributes": [...], ...}.
_SKU_BLOB = re.compile(r"waveshare_sku_attributes\s*=\s*(\[.*?\])\s*;", re.S)
_PRICE = re.compile(r"([\d,]+(?:\.\d{2})?)")


def parse(url: str, html: str) -> Detail:
    """Everything the product page adds on top of the listing row."""
    soup = BeautifulSoup(html, "lxml")
    low, high = _price_range(soup)
    return Detail(
        url=url,
        description=_description(soup),
        wiki_url=_wiki_url(soup),
        images=_images(soup, url),
        variants=_variants(html),
        axes=option_axes(html),
        price_min=low,
        price_max=high,
    )


def _price_range(soup: BeautifulSoup) -> tuple[float | None, float | None]:
    """Read the `$25.99 - $32.99` box a multi-option product shows.

    Category listings only ever print one figure, so this is the only place the
    upper bound of a product's price is available.
    """
    box = soup.select_one("span.waveshare_price-box")
    if box is None:
        return None, None
    found: list[float] = []
    for node in box.select("span.price"):
        match = _PRICE.search(node.get_text(strip=True))
        if match is not None:
            value = float(match.group(1).replace(",", ""))
            if value > 0:  # the page also carries a $0.00 placeholder
                found.append(value)
    if not found:
        return None, None
    return min(found), max(found)


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


def _wiki_url(soup: BeautifulSoup) -> str | None:
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if isinstance(href, str) and "/wiki/" in href:
            return href
    return None


def _images(soup: BeautifulSoup, url: str) -> tuple[str, ...]:
    """The product's own photos.

    A page shows around 57 catalogue thumbnails but only a handful are this product;
    the rest belong to related items and would be dead weight in every row.
    """
    slug = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".htm").lower()
    seen: dict[str, None] = {}
    for image in soup.select("img[src]"):
        src = image.get("src")
        if isinstance(src, str) and "/media/catalog/product/" in src and slug in src.lower():
            seen[src] = None
    return tuple(seen)
