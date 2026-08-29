"""Read sitemap.xml, which lists the whole catalogue in one request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

SITEMAP_URL = "https://www.waveshare.com/sitemap.xml"
# The root listing, which pages through most of the catalogue on its own.
ROOT_CATEGORY = "https://www.waveshare.com/product.htm"

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def canonical_product_url(url: str) -> str:
    """Reduce a product URL to the form the sitemap uses.

    Category listings link products through their category path, for example
    `/product/displays/lcd-oled/lcd-oled-1/10.1inch-raspberry-pi-touch-display-2.htm`,
    while the sitemap only ever carries `/10.1inch-raspberry-pi-touch-display-2.htm`.
    Normalising to the short form is what lets the two sources agree.
    """
    parts = urlsplit(url)
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    return urlunsplit((parts.scheme, parts.netloc, f"/{slug}", "", ""))


def is_category(url: str) -> bool:
    return urlsplit(url).path.startswith("/product/") or urlsplit(url).path == "/product.htm"


@dataclass(frozen=True, slots=True)
class Index:
    """Every URL the sitemap knows about, split by kind."""

    products: tuple[str, ...]
    categories: tuple[str, ...]


def parse(xml: str) -> Index:
    """Split the sitemap into canonical product URLs and category URLs."""
    products: dict[str, None] = {}
    categories: dict[str, None] = {}
    for url in _LOC.findall(xml):
        if not url.endswith(".htm"):
            continue
        if is_category(url):
            categories[url] = None
        else:
            products[canonical_product_url(url)] = None
    return Index(products=tuple(products), categories=tuple(categories))


def category_depth(url: str) -> int:
    """How deep a category sits, with `/product.htm` as the root at depth 0."""
    path = urlsplit(url).path
    if path == "/product.htm":
        return 0
    return path.removeprefix("/product/").count("/") + 1


def parent_of(url: str, known: set[str]) -> str | None:
    """The closest enclosing category that actually exists in `known`."""
    parts = urlsplit(url)
    segments = parts.path.removesuffix(".htm").strip("/").split("/")
    while len(segments) > 1:
        segments = segments[:-1]
        candidate = urlunsplit(
            (parts.scheme, parts.netloc, "/" + "/".join(segments) + ".htm", "", "")
        )
        if candidate in known:
            return candidate
    return None
