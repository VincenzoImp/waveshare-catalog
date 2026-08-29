"""Tests for reading a wiki page's downloads."""

from __future__ import annotations

from waveshare_catalog import wiki


def link(href: str, text: str) -> str:
    return f'<a href="{href}">{text}</a>'


def test_classifies_downloads_by_what_the_link_calls_them() -> None:
    """Anchor text describes these better than the file name: both of these are PDFs."""
    html = "".join(
        (
            link("https://files.waveshare.com/x/X-2Dand3D.zip", "X 2D & 3D diagram"),
            link("https://files.waveshare.com/x/X-Schematic.pdf", "X Schematic diagram"),
            link("https://files.waveshare.com/c/Esp32-s3_datasheet_en.pdf", "ESP32-S3 Datasheet"),
            link("https://files.waveshare.com/c/ES8311.user.Guide.pdf", "ES8311 User Guide"),
            link("https://files.waveshare.com/x/X-Demo.zip", "X Demo"),
            link("https://files.waveshare.com/c/flash_download_tool.zip", "Flash_download_tool"),
            link("https://files.waveshare.com/c/mystery.rar", "Unlabelled"),
        )
    )

    found = {resource.title: resource.kind for resource in wiki.parse(html)}

    assert found == {
        "X 2D & 3D diagram": "cad",
        "X Schematic diagram": "schematic",
        "ESP32-S3 Datasheet": "datasheet",
        "ES8311 User Guide": "datasheet",
        "X Demo": "demo",
        "Flash_download_tool": "software",
        "Unlabelled": "other",
    }


def test_ignores_links_that_are_not_files() -> None:
    html = link("/wiki/Another_Page", "Another page") + link("https://example.com", "Elsewhere")

    assert wiki.parse(html) == ()


def test_a_file_linked_twice_is_recorded_once() -> None:
    html = link("https://files.waveshare.com/x/X.pdf", "First") * 2

    assert len(wiki.parse(html)) == 1


def test_an_upload_path_counts_as_a_file() -> None:
    """MediaWiki serves some attachments from `/w/upload/` with no extension in the link."""
    html = link("https://www.waveshare.com/w/upload/9/9a/X", "Drawing")

    assert wiki.parse(html)[0].kind == "cad"


def test_the_stored_link_is_upgraded_to_tls() -> None:
    assert wiki.url_of("http://www.waveshare.com/wiki/X") == "https://www.waveshare.com/wiki/X"
    assert wiki.url_of(" https://www.waveshare.com/wiki/X ") == "https://www.waveshare.com/wiki/X"


def test_a_relative_wiki_link_is_resolved_against_the_site() -> None:
    """A handful of product pages write the link relative, which used to fail the fetch."""
    assert wiki.url_of("/wiki/PI4-CASE-NANOSOUND-ONE") == (
        "https://www.waveshare.com/wiki/PI4-CASE-NANOSOUND-ONE"
    )
    assert wiki.url_of("/wiki/index.php?title=MISC_CAPE") == (
        "https://www.waveshare.com/wiki/index.php?title=MISC_CAPE"
    )


def test_classifies_the_less_obvious_names_too() -> None:
    """Each of these was landing in `other` until the real catalogue showed how common it is."""
    html = "".join(
        (
            link("https://files.waveshare.com/x/asm.zip", "Assembly diagram"),
            link("https://files.waveshare.com/x/rp2-pico-v1.15.uf2", "Pico firmware"),
            link("https://files.waveshare.com/x/cp2102.zip", "CP2102 Driver"),
            link("https://files.waveshare.com/x/pinout.pdf", "Pico2 Pinout definition"),
        )
    )

    assert {r.title: r.kind for r in wiki.parse(html)} == {
        "Assembly diagram": "cad",
        "Pico firmware": "demo",
        "CP2102 Driver": "software",
        "Pico2 Pinout definition": "datasheet",
    }
