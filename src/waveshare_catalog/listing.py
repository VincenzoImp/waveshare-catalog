"""Parse a category page, which carries 80 products per request."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from waveshare_catalog.sitemap import canonical_product_url
from waveshare_catalog.store import Product

PAGE_SIZE = 80

_PRICE = re.compile(r"([\d,]+(?:\.\d{2})?)")


def page_url(category_url: str, page: int) -> str:
    """The category URL asking for a full page of results."""
    return f"{category_url}?limit={PAGE_SIZE}&p={page}"


def parse(html: str) -> list[Product]:
    """Every product listed on one category page."""
    soup = BeautifulSoup(html, "lxml")
    products: list[Product] = []
    for item in soup.select("ul.product-list > li"):
        product = _product_from(item)
        if product is not None:
            products.append(product)
    return products


def has_next_page(html: str) -> bool:
    """Whether the pager offers a page after the current one."""
    soup = BeautifulSoup(html, "lxml")
    return soup.select_one("div.pages a.next, li.next a") is not None


def _product_from(item: Tag) -> Product | None:
    link = item.select_one("h2.product-name a")
    if link is None:
        return None
    href = link.get("href")
    title = link.get("title")
    name = title if isinstance(title, str) and title else link.get_text(strip=True)
    if not isinstance(href, str) or not name:
        return None
    return Product(
        url=canonical_product_url(href),
        name=name.strip(),
        part_no=_part_no(item),
        price_min=_price(item),
        image=_image(item),
        has_options=item.select_one(".multi-options") is not None,
    )


def _part_no(item: Tag) -> str | None:
    """Read `<p><span>Part No.:</span>10.1HP-CAPQLED-B</p>` from the attribute block."""
    for paragraph in item.select("div.product-attr p"):
        label = paragraph.select_one("span")
        if label is None or "part no" not in label.get_text(strip=True).lower():
            continue
        value = paragraph.get_text(" ", strip=True)
        _, _, tail = value.partition(":")
        candidate = tail.strip()
        if candidate:
            return candidate
    return None


def _price(item: Tag) -> float | None:
    node = item.select_one("span.regular-price .price, span.price-box .price")
    if node is None:
        return None
    match = _PRICE.search(node.get_text(strip=True))
    if match is None:
        return None
    return float(match.group(1).replace(",", ""))


def _image(item: Tag) -> str | None:
    node = item.select_one("img.primary-image, img")
    if node is None:
        return None
    src = node.get("src")
    return src if isinstance(src, str) else None
