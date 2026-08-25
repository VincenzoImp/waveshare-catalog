"""Tests for category listing parsing, against a real category page."""

from __future__ import annotations

from waveshare_catalog import listing


def test_reads_every_product_on_a_full_page(category_html: str) -> None:
    products = listing.parse(category_html)

    assert len(products) == listing.PAGE_SIZE
    assert all(p.part_no for p in products)
    assert all(p.price_min is not None for p in products)


def test_reads_the_fields_of_a_known_row(category_html: str) -> None:
    by_part_no = {p.part_no: p for p in listing.parse(category_html)}

    product = by_part_no["10.1HP-CAPQLED-B"]

    assert product.url == "https://www.waveshare.com/10.1hp-capqled-b.htm"
    assert product.slug == "10.1hp-capqled-b"
    assert product.price_min == 116.99
    assert product.has_options
    assert product.name.startswith("10.1inch QLED Quantum Dot Display Type B")
    assert product.image is not None and product.image.endswith(".jpg")


def test_marks_single_option_products(category_html: str) -> None:
    products = listing.parse(category_html)

    assert sum(p.has_options for p in products) == 48


def test_page_url_asks_for_a_full_page() -> None:
    url = listing.page_url("https://www.waveshare.com/product/displays.htm", 2)

    assert url == "https://www.waveshare.com/product/displays.htm?limit=80&p=2"


def test_skips_items_without_a_usable_link() -> None:
    html = """
    <ul class="product-list">
      <li><div class="product-shop"><h2 class="product-name"><span>no link</span></h2></div></li>
      <li><div class="product-shop"><h2 class="product-name"><a>no href</a></h2></div></li>
      <li><div class="product-shop"><h2 class="product-name"><a href="/x.htm"></a></h2></div></li>
    </ul>
    """

    assert listing.parse(html) == []


def test_falls_back_to_link_text_when_the_title_is_missing() -> None:
    html = """
    <ul class="product-list"><li><div class="product-shop">
      <h2 class="product-name"><a href="https://www.waveshare.com/x.htm">Plain name</a></h2>
    </div></li></ul>
    """

    product = listing.parse(html)[0]

    assert product.name == "Plain name"
    assert product.part_no is None
    assert product.price_min is None
    assert product.image is None


def test_ignores_attribute_rows_that_are_not_the_part_number() -> None:
    html = """
    <ul class="product-list"><li><div class="product-shop">
      <h2 class="product-name"><a href="/x.htm" title="X">X</a></h2>
      <div class="product-attr"><p><span>Weight:</span>10g</p><p>loose text</p></div>
      <span class="regular-price"><span class="price">not a number</span></span>
    </div></li></ul>
    """

    product = listing.parse(html)[0]

    assert product.part_no is None
    assert product.price_min is None


def test_detects_the_pager(category_html: str) -> None:
    # The real page is full, so it offers a next one: categories exceed 80 products.
    assert listing.has_next_page(category_html)
    assert not listing.has_next_page('<div class="pages"><span>1</span></div>')


def test_keeps_looking_when_a_part_number_row_is_empty() -> None:
    html = """
    <ul class="product-list"><li><div class="product-shop">
      <h2 class="product-name"><a href="/x.htm" title="X">X</a></h2>
      <div class="product-attr"><p><span>Part No.:</span></p><p><span>Part No.:</span>X-9</p></div>
    </div></li></ul>
    """

    assert listing.parse(html)[0].part_no == "X-9"
