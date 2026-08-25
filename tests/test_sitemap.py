"""Tests for sitemap parsing, against the real sitemap.xml."""

from __future__ import annotations

import pytest

from waveshare_catalog import sitemap


def test_splits_the_real_sitemap_into_products_and_categories(sitemap_xml: str) -> None:
    index = sitemap.parse(sitemap_xml)

    assert len(index.products) == 2349
    assert len(index.categories) == 299
    assert "https://www.waveshare.com/esp32-s3-touch-lcd-3.5.htm" in index.products
    assert "https://www.waveshare.com/product/displays.htm" in index.categories


def test_products_are_deduplicated_by_canonical_url() -> None:
    xml = (
        "<urlset>"
        "<url><loc>https://www.waveshare.com/product/displays/lcd-oled/x.htm</loc></url>"
        "<url><loc>https://www.waveshare.com/x.htm</loc></url>"
        "</urlset>"
    )

    index = sitemap.parse(xml)

    assert index.products == ("https://www.waveshare.com/x.htm",)
    assert index.categories == ("https://www.waveshare.com/product/displays/lcd-oled/x.htm",)


def test_ignores_entries_that_are_not_pages() -> None:
    xml = "<urlset><url><loc>https://www.waveshare.com/media/logo.png</loc></url></urlset>"

    index = sitemap.parse(xml)

    assert index.products == ()
    assert index.categories == ()


@pytest.mark.parametrize(
    ("url", "depth"),
    [
        ("https://www.waveshare.com/product.htm", 0),
        ("https://www.waveshare.com/product/displays.htm", 1),
        ("https://www.waveshare.com/product/displays/lcd-oled.htm", 2),
        ("https://www.waveshare.com/product/displays/lcd-oled/lcd-oled-1.htm", 3),
    ],
)
def test_category_depth(url: str, depth: int) -> None:
    assert sitemap.category_depth(url) == depth


def test_parent_is_the_closest_category_that_exists() -> None:
    known = {
        "https://www.waveshare.com/product/displays.htm",
        "https://www.waveshare.com/product/displays/lcd-oled/lcd-oled-1.htm",
    }

    parent = sitemap.parent_of(
        "https://www.waveshare.com/product/displays/lcd-oled/lcd-oled-1.htm", known
    )

    assert parent == "https://www.waveshare.com/product/displays.htm"


def test_a_top_level_category_has_no_parent() -> None:
    assert sitemap.parent_of("https://www.waveshare.com/product.htm", set()) is None
