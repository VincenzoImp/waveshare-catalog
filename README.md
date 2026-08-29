# waveshare-catalog

[![CI](https://github.com/VincenzoImp/waveshare-catalog/actions/workflows/ci.yml/badge.svg)](https://github.com/VincenzoImp/waveshare-catalog/actions/workflows/ci.yml)

Collect the [Waveshare](https://www.waveshare.com) product catalogue into a local SQLite
database, then filter it offline as many times as you like.

Waveshare sells around 2,350 products and its own search is not much help when you shop by
property rather than by name, for example "a touch display under $40 that ships with a case
and can take a battery". This pulls the catalogue down once so you can answer that with a
query instead of forty browser tabs.

```console
$ waveshare-catalog query --name touch --price-max 40 --with-options
     $8.99  PI5-CASE-TD2              Protective Case For Raspberry Pi 7inch Touch Display 2...
    $14.99  ESP32-C6-Touch-LCD-1.47   ESP32-C6 1.47inch Touch Display Development Board...
    $14.99  RP2350-Touch-LCD-2        RP2350 2inch Capacitive Touch Display, Onboard Camera...
    $16.99  ESP32-S3-Touch-LCD-2      ESP32-S3 2inch Capacitive Touch Display, IPS Panel...
8 products
```

## Install

Run it without installing anything:

```bash
uvx --from git+https://github.com/VincenzoImp/waveshare-catalog waveshare-catalog --help
```

Or keep it around:

```bash
pipx install git+https://github.com/VincenzoImp/waveshare-catalog
```

To work on it, clone the repository and run `uv sync`.

## Use

```bash
# 1. register the whole catalogue and collect what the listings give away cheaply
waveshare-catalog sync

# 2. filter locally, as often as you want, with no further requests
waveshare-catalog query --name touch --price-max 40 --with-options

# 3. pull full pages for what survived the filter
waveshare-catalog detail --name "touch lcd" --limit 20

# ...or the whole catalogue, resuming wherever the last run stopped
waveshare-catalog detail --all

# 4. take it elsewhere
waveshare-catalog export --format csv --price-max 60 > shortlist.csv
```

`stats` shows how much has been collected. `reparse` re-runs the parsers over pages already
on disk, which costs no network and is how you pick up a parser fix after an upgrade.

## Skip the crawl

The [latest release](https://github.com/VincenzoImp/waveshare-catalog/releases/latest) carries
a ready database, 2.9 MB compressed:

```bash
curl -LO https://github.com/VincenzoImp/waveshare-catalog/releases/latest/download/waveshare-catalog-2026-08-29.db.gz
gunzip waveshare-catalog-2026-08-29.db.gz && mv waveshare-catalog-*.db waveshare.db
waveshare-catalog query --name touch --price-max 40
```

It holds all 2,350 products with their pages fetched: prices, 2,543 variants across 613
products, wiki links and descriptions. Two caveats. It is a snapshot taken on 2026-08-29, so
prices and availability drift; re-run `sync` and `detail --all` for current data. And the
product text in it belongs to Waveshare: it is bundled so you can query the catalogue, not
as content to republish.

## How this catalogue is actually shaped

Both of these were measured against the live site, and both decide how the tool works.

**A fifth of the catalogue is in no category at all.** 465 of the 2,349 products are listed in
`sitemap.xml`, have a live page and can be bought, yet appear under no category.
`1.02inch-e-paper.htm` is one of them: a real 1.02inch e-Paper module at $5.99, absent from
`/product/displays/e-paper.htm` and from every `epaper-N` subcategory. So `sync` registers
every URL the sitemap names, and `detail` can reach them all. Without that, no amount of
crawling would ever find them.

**Crawling the category tree is close to pointless:**

| route | requests | coverage |
|---|---|---|
| root listing, paginated | 24 | 80% |
| the 13 top-level categories | 49 | 78.7%, i.e. *less* |
| all 225 leaf categories | ~265 | still ~80%, orphans still missing |

That is why the root listing is the default and `--with-categories` is opt-in: you turn it on
when you want to know which category a product belongs to, not to find more products.

## What a full crawl costs

Waveshare's `robots.txt` asks for `Crawl-delay: 60` and `Request-rate: 1/60`, one request per
minute. This tool reads that file and obeys it by default, single threaded. `--delay`
overrides it: going faster than a site asks is your call, not the tool's default.

Product pages are around 300 KB and the site answers in about 2.1 s, so:

| goal | requests | at 60 s | at 1 s |
|---|---|---|---|
| every URL, plus metadata for 80% | 25 | ~26 min | ~1 min |
| metadata for everything | ~525 | ~8.5 h | ~27 min |
| everything including details | 2,350 | ~40 h | ~2 h |

`detail --all` only picks products whose page is missing, so a long run can be interrupted
and resumed. Nothing is lost either way: every response is cached gzipped under `cache/`,
keyed by URL, and progress is committed as it goes.

## What gets stored

`waveshare.db` holds categories, products and their category memberships. For products whose
page you fetched, it also holds the description, wiki link, images, the option axes
(`Version Options: with case, without case`) and one row per purchasable variant with its SKU.

**Prices.** A listing prints one figure even when a product has options, so after `sync` you
only know the entry price. The product page carries the real range, `$25.99 - $32.99`, and
`detail` writes it back over the listing figure. `price_max` is therefore populated exactly
for the products you fetched in full.

**Specifications are not a structured field.** Waveshare publishes no spec table; the details
live in the prose. The full description is stored, usually a few thousand words covering
resolution, interfaces and dimensions, but there is no `specs` dictionary to query. Mining
the prose would be guesswork that breaks on the first differently written page, so the field
is deliberately absent rather than present and empty.

**Variants are not standard Magento.** The page carries Waveshare's own blob:

```js
var waveshare_sku_attributes = [{"sku ":"30733","attributes":["without case"], ...}];
```

Note the trailing space in `sku `. The parser accepts it with or without, because this format
has already changed once and will change again. When it does, fix the parser and run
`reparse`: no re-crawling.

## Development

```bash
uv run pytest --cov     # 100% branch coverage is enforced
uv run ruff check .
uv run mypy
```

Parser tests run against real pages captured from the site and frozen under
`tests/fixtures/`, so they catch a change in the site's markup instead of agreeing with a
mock. Nothing in the suite touches the network.

## Status

Working and complete for what it sets out to do, maintained casually. The snapshot is
refreshed now and then rather than on a schedule, and the parsers read Waveshare's HTML, so
they will break when the site changes: it has happened once already, when Waveshare replaced
the Magento variant format with its own. When it happens, fixing the parser and running
`reparse` costs minutes and no network, because every page is cached. Issues get read when
there is time.

## Licence

MIT.
