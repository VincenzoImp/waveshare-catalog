"""Read a product's wiki page for the files it links.

Only the files. The prose is an Arduino tutorial and the tables list library versions, so
harvesting them would file `v8.4.0 = "Install Online"` as a specification. What the wiki
has that the shop page does not is downloads: the product page links none at all, while
the wiki carries the CAD geometry, the schematic and every component datasheet.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from waveshare_catalog.store import Resource

# Anchor text describes these better than the file name does: "2D & 3D diagram" is a zip,
# and "ESP32-S3 Series Datasheet" and "ES8311 User Guide" are both PDFs. First match wins,
# so the more specific kinds come first.
KINDS: tuple[tuple[str, str], ...] = (
    ("cad", r"\b2d\b|\b3d\b|dimension|drawing|assembly|\.step$|\.stp$|\.dxf$|\.dwg$"),
    ("schematic", r"schematic|\.sch$|\.brd$"),
    ("datasheet", r"datasheet|manual|user guide|specification|pinout"),
    ("demo", r"\bdemo\b|\bexample|\bsample|\bcodes?\b|firmware|program|\.uf2$"),
    # No word boundary before "tool": the files are named `flash_download_tool.zip`.
    ("software", r"software|tool|conversion|converter|installation|driver|imager|formatter"),
)

# A few product pages link their wiki relative to the site root instead of absolutely.
SITE = "https://www.waveshare.com"

_FILE = re.compile(r"\.(pdf|zip|step|stp|dxf|dwg|7z|rar|sch|brd|exe|msi|uf2)$|/w/upload/", re.I)


def parse(html: str) -> tuple[Resource, ...]:
    """Every downloadable file the page links, classified by what the link calls it."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, Resource] = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not isinstance(href, str) or not _FILE.search(href):
            continue
        title = anchor.get_text(" ", strip=True)
        if href not in found:
            found[href] = Resource(kind=_kind(f"{title} {href}"), url=href, title=title)
    return tuple(found.values())


def _kind(text: str) -> str:
    """What the link calls it, or `other`.

    `other` is mostly the third-party utilities a tutorial tells you to install — PuTTY,
    Win32DiskImager, Thonny — which every wiki page links and which say nothing about the
    product. Naming each of them would be a list to maintain, not a rule.
    """
    for name, pattern in KINDS:
        if re.search(pattern, text, re.I):
            return name
    return "other"


def url_of(wiki_url: str) -> str:
    """The address to fetch.

    Stored links are inconsistent: most are absolute and `http://`, which the site
    redirects to TLS, but a handful are written relative to the site root.
    """
    return urljoin(SITE, re.sub(r"^http://", "https://", wiki_url.strip()))
