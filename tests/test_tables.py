"""Tests for reading a product page's tables, against a real page and small shapes."""

from __future__ import annotations

from bs4 import BeautifulSoup

from waveshare_catalog import tables


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def test_reads_the_spec_table_of_a_real_product(product_html: str) -> None:
    pairs, _ = tables.read(soup_of(product_html))

    assert dict(pairs) == {
        "Display Panel": "IPS",
        "Display Size": "3.5 inch",
        "Resolution": "320 × 480 pixels",
        "Display Colors": "262K",
        "Brightness": "220cd/㎡",
        "Contrast Ratio": "1100:1",
        "Communication Interface": "SPI",
        "Driver IC": "ST7796",
        "Touch Type": "Capacitive",
        "Touch IC": "FT6336",
    }


def test_reads_the_family_matrix_of_a_real_product(product_html: str) -> None:
    _, family = tables.read(soup_of(product_html))

    models = {model for model, _, _ in family}
    assert len(models) == 87
    assert "ESP32-S3-Touch-AMOLED-2.41" in models
    # The header only lines up with the data once rowspan and colspan are expanded.
    assert ("ESP32-S3-Touch-AMOLED-2.41", "PSRAM", "8MB") in family
    assert ("ESP32-S3-Touch-AMOLED-2.41", "pixels", "600 × 450") in family


def test_a_section_banner_names_no_model(product_html: str) -> None:
    """Rows like "AMOLED display" span the full width and separate groups."""
    _, family = tables.read(soup_of(product_html))

    assert "AMOLED display" not in {model for model, _, _ in family}


def test_expands_rowspan_and_colspan() -> None:
    """The real matrix groups its middle columns and spans the outer two down two rows."""
    body = "".join(
        f"<tr><td>Board-{n}</td><td>{n}</td><td>b</td><td>c</td><td>d</td><td>note</td></tr>"
        for n in range(4)
    )
    html = f"""<table>
      <thead>
        <tr><th rowspan="2">Model</th><th colspan="4">Group</th><th rowspan="2">Notes</th></tr>
        <tr><th>Left</th><th>Mid</th><th>Other</th><th>Right</th></tr>
      </thead>
      <tbody>{body}</tbody>
    </table>"""

    _, family = tables.read(soup_of(html))

    assert ("Board-2", "Left", "2") in family, "the grouped columns line up after expansion"
    assert ("Board-2", "Notes", "note") in family, "the rowspan header reaches the last column"


def test_a_cell_spanning_more_than_two_rows_is_carried_down_all_of_them() -> None:
    html = """<table>
      <tr><td>Model</td><td>A</td><td>B</td><td>C</td><td>D</td><td>E</td></tr>
      <tr><td rowspan="3">Board-X</td><td>1</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
      <tr><td>2</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
      <tr><td>3</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
      <tr><td>Board-Y</td><td>4</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
    </table>"""

    _, family = tables.read(soup_of(html))

    assert ("Board-X", "A", "1") in family
    assert ("Board-X", "A", "3") in family, "the third row still knows which model it describes"


def test_an_empty_cell_states_nothing() -> None:
    html = """<table>
      <tr><td>Model</td><td>A</td><td>B</td><td>C</td><td>D</td><td>E</td></tr>
      <tr><td>Board-X</td><td></td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
      <tr><td>Board-Y</td><td>1</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
      <tr><td>Board-Z</td><td>2</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
      <tr><td>Board-W</td><td>3</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>
    </table>"""

    _, family = tables.read(soup_of(html))

    assert ("Board-X", "A") not in {(model, key) for model, key, _ in family}
    assert ("Board-Y", "A", "1") in family


def test_a_matrix_without_a_thead_takes_its_first_row_as_the_header() -> None:
    rows = "".join(
        f"<tr><td>Board-{n}</td><td>{n}</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>"
        for n in range(5)
    )
    header = "<tr><td>Model</td><td>CPU</td><td>c</td><td>d</td><td>e</td><td>f</td></tr>"
    html = f"<table>{header}{rows}</table>"

    _, family = tables.read(soup_of(html))

    assert ("Board-3", "CPU", "3") in family


def test_a_pinout_is_kept_apart_from_the_specifications() -> None:
    html = """<table>
      <tr><th>GND</th><td>Ground</td></tr>
      <tr><th>VCC</th><td>Power</td></tr>
      <tr><th>SDA</th><td>Data</td></tr>
      <tr><th>Colour</th><td>Black</td></tr>
    </table>"""

    pairs, _ = tables.read(soup_of(html))

    assert ("pin:GND", "Ground") in pairs
    assert ("pin:Colour", "Black") in pairs, "a pinout's rows all carry the prefix"


def test_a_wide_specification_table_is_not_mistaken_for_a_family() -> None:
    """Shape alone cannot tell them apart; a family matrix titles its first column.

    Without this, labels like "Sensitivity" and "1D" were recorded as sibling models, and
    half of what the catalogue called a product family was not one.
    """
    rows = "".join(
        f"<tr><td>Label-{n}</td><td>1</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>"
        for n in range(5)
    )
    header = "<tr><td>Package Contents</td><td>A</td><td>B</td><td>C</td><td>D</td><td>E</td></tr>"

    _, family = tables.read(soup_of(f"<table>{header}{rows}</table>"))

    assert family == ()


def test_the_first_column_may_be_titled_in_any_of_the_usual_ways() -> None:
    rows = "".join(
        f"<tr><td>Pico-LCD-{n}</td><td>1</td><td>b</td><td>c</td><td>d</td><td>e</td></tr>"
        for n in range(5)
    )
    for title in ("Part Number", "PARTNUMBER", "Model", "product"):
        header = f"<tr><td>{title}</td><td>A</td><td>B</td><td>C</td><td>D</td><td>E</td></tr>"

        _, family = tables.read(soup_of(f"<table>{header}{rows}</table>"))

        assert ("Pico-LCD-0", "A", "1") in family, f"{title} should name models"


def test_a_table_of_an_unrecognised_shape_is_skipped() -> None:
    """Five columns is neither a key/value table nor a family matrix, so nothing is guessed."""
    html = "<table><tr><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td></tr></table>"

    assert tables.read(soup_of(html)) == ((), ())


def test_an_empty_table_is_skipped() -> None:
    assert tables.read(soup_of("<table></table>")) == ((), ())


def test_a_cell_repeating_its_key_is_not_a_pair() -> None:
    html = "<table><tr><th>Same</th><td>Same</td></tr><tr><th>Key</th><td>Value</td></tr></table>"

    pairs, _ = tables.read(soup_of(html))

    assert pairs == (("Key", "Value"),)


def test_survives_broken_span_attributes() -> None:
    html = """<table>
      <tr><th colspan="huge">Key</th><td rowspan="">Value</td></tr>
      <tr><th colspan="9999">Other</th><td>Second</td></tr>
    </table>"""

    pairs, _ = tables.read(soup_of(html))

    assert pairs == (("Key", "Value"), ("Other", "Second"))
