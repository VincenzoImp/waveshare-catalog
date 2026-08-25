"""Tests for product page parsing, against a real product page."""

from __future__ import annotations

from waveshare_catalog import product

URL = "https://www.waveshare.com/esp32-s3-touch-lcd-3.5.htm"


def test_reads_the_variants_of_a_real_product(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert {v.sku: v.label for v in detail.variants} == {
        "30733": "without case",
        "30934": "with case and OV5640 camera",
    }
    assert not any(v.unsaleable for v in detail.variants)


def test_reads_the_option_axes(product_html: str) -> None:
    axes = product.option_axes(product_html)

    assert axes["Version Options"] == ("with case and OV5640 camera", "without case")


def test_reads_the_wiki_link_and_images(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert detail.wiki_url is not None and "/wiki/" in detail.wiki_url
    assert detail.images
    assert all("/media/catalog/product/" in image for image in detail.images)


def test_a_product_without_variants_yields_none() -> None:
    detail = product.parse(URL, "<html><body>nothing here</body></html>")

    assert detail.variants == ()
    assert detail.description == ""
    assert detail.specs == {}
    assert detail.wiki_url is None
    assert detail.images == ()


def test_survives_a_malformed_variant_blob() -> None:
    html = "<script>var waveshare_sku_attributes = [not json];</script>"

    assert product.parse(URL, html).variants == ()


def test_accepts_the_sku_key_with_or_without_its_trailing_space() -> None:
    html = (
        "<script>var waveshare_sku_attributes = ["
        '{"sku ":"1","attributes":["a"],"unsaleable":true},'
        '{"sku":"2","attributes":["b"]},'
        '{"attributes":["c"]},'
        '"not a dict"'
        "];</script>"
    )

    variants = product.parse(URL, html).variants

    assert [(v.sku, v.unsaleable) for v in variants] == [("1", True), ("2", False)]


def test_reads_two_column_spec_tables() -> None:
    html = """
    <table>
      <tr><th>Resolution</th><td>320x480</td></tr>
      <tr><td>Resolution</td><td>ignored duplicate</td></tr>
      <tr><td>Touch</td><td>capacitive</td></tr>
      <tr><td>only one cell</td></tr>
      <tr><td></td><td>no name</td></tr>
    </table>
    """

    specs = product.parse(URL, html).specs

    assert specs == {"Resolution": "320x480", "Touch": "capacitive"}


def test_reads_the_description_block() -> None:
    html = '<div class="product-description">  A small display.  </div>'

    assert product.parse(URL, html).description == "A small display."


def test_option_axes_ignores_incomplete_groups() -> None:
    html = """
    <div class="goods-detail-line"><div class="line-right"><a class="tag-text">v</a></div></div>
    <div class="goods-detail-line"><div class="line-left">Named</div></div>
    <div class="goods-detail-line"><div class="line-left"> </div>
      <div class="line-right"><a class="tag-text">v</a></div></div>
    """

    assert product.option_axes(html) == {}
