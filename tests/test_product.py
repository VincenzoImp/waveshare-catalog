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


def test_the_description_no_longer_carries_the_family_matrix(product_html: str) -> None:
    """The page tabulates 87 sibling models inside the description; only prose should remain.

    Left in, a text search for "with case" answered about whichever sibling had one.
    """
    detail = product.parse(URL, product_html)

    assert "√" not in detail.description
    assert "ESP32-S3-Touch-AMOLED-2.41" not in detail.description
    assert detail.description.startswith("ESP32-S3 3.5inch Capacitive Touch Display")


def test_the_specifications_reach_the_detail(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert {s.key_norm: s.value for s in detail.specs}["driver ic"] == "ST7796"


def test_the_family_matrix_reaches_the_detail(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert len({row.model for row in detail.family}) == 87


def test_reads_the_wiki_link_and_images(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert detail.wiki_url is not None and "/wiki/" in detail.wiki_url
    assert detail.images
    assert all("/media/catalog/product/" in image for image in detail.images)


def test_a_product_without_variants_yields_none() -> None:
    detail = product.parse(URL, "<html><body>nothing here</body></html>")

    assert detail.variants == ()
    assert detail.description == ""
    assert detail.wiki_url is None
    assert detail.images == ()
    assert detail.price_min is None


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


def test_reads_the_price_range_of_a_real_product(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert (detail.price_min, detail.price_max) == (25.99, 32.99)


def test_a_single_price_gives_an_equal_range() -> None:
    html = '<span class="waveshare_price-box"><span class="price">$9.99</span></span>'

    detail = product.parse(URL, html)

    assert (detail.price_min, detail.price_max) == (9.99, 9.99)


def test_the_zero_placeholder_is_not_a_price() -> None:
    html = '<span class="waveshare_price-box"><span class="price">$0.00</span></span>'

    assert product.parse(URL, html).price_min is None


def test_an_unreadable_price_is_left_unset() -> None:
    html = '<span class="waveshare_price-box"><span class="price">on request</span></span>'

    assert product.parse(URL, html).price_min is None


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


def test_the_parsed_detail_carries_the_axes(product_html: str) -> None:
    detail = product.parse(URL, product_html)

    assert detail.axes["Version Options"] == ("with case and OV5640 camera", "without case")


def test_images_are_limited_to_the_product_itself(product_html: str) -> None:
    """A page shows ~57 catalogue thumbnails; all but a handful belong to related items."""
    detail = product.parse(URL, product_html)

    assert len(detail.images) == 8
    assert all("esp32-s3-touch-lcd-3.5" in image for image in detail.images)


def test_reads_the_identifying_fields_from_the_page(product_html: str) -> None:
    """For the fifth of the catalogue in no listing, the page is the only source of these."""
    detail = product.parse(URL, product_html)

    assert detail.name is not None and detail.name.startswith("ESP32-S3 3.5inch")
    assert detail.image is not None and detail.image.endswith(".jpg")


def test_reads_a_part_number_when_the_page_carries_one() -> None:
    html = (
        '<span class="product-info-title">Part No.</span>'
        '<span style="opacity: 0;">:</span><span>1.02inch e-Paper</span>'
    )

    assert product.parse(URL, html).part_no == "1.02inch e-Paper"


def test_a_page_without_those_fields_leaves_them_unset() -> None:
    detail = product.parse(URL, '<span class="product-info-title">Weight</span><span>10g</span>')

    assert detail.name is None
    assert detail.part_no is None
    assert detail.image is None


def test_an_empty_product_name_is_not_taken() -> None:
    assert product.parse(URL, '<div class="product-name">  </div>').name is None


def test_keeps_looking_when_a_part_number_label_has_no_value() -> None:
    html = (
        '<div><span class="product-info-title">Part No.</span><span>:</span></div>'
        '<div><span class="product-info-title">Part No.</span><span>X-2</span></div>'
    )

    assert product.parse(URL, html).part_no == "X-2"
