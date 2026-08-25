# waveshare-catalog

[![CI](https://github.com/VincenzoImp/waveshare-catalog/actions/workflows/ci.yml/badge.svg)](https://github.com/VincenzoImp/waveshare-catalog/actions/workflows/ci.yml)

Collect the [Waveshare](https://www.waveshare.com) product catalogue into a local SQLite
database, then filter it offline as many times as you like.

Waveshare sells roughly 2,350 products and its own site search is not much help when you
are shopping by property rather than by name, for example "a touch display under $40 that
ships with a case and can take a battery". This tool pulls the catalogue down once and lets
you answer that kind of question with a query instead of forty browser tabs.

## Install

```bash
uv sync
```

## Use

```bash
# 1. index the catalogue: sitemap, then every category listing
uv run waveshare-catalog sync

# 2. filter locally, as often as you want, with no further requests
uv run waveshare-catalog query --name touch --price-max 40 --with-options

# 3. pull full pages only for what survived the filter
uv run waveshare-catalog detail --name "touch lcd" --limit 20

# ...or take the whole catalogue, resuming wherever the last run stopped
uv run waveshare-catalog detail --all

# 4. take it elsewhere
uv run waveshare-catalog export --format csv --price-max 60 > shortlist.csv
```

`stats` shows how much has been collected, including how many product pages were parsed by
an older version of the code. `reparse` re-runs the parsers over pages already on disk,
which costs no network at all and is how you pick those up after an upgrade.

## About the crawl delay

Waveshare's `robots.txt` asks for `Crawl-delay: 60` and `Request-rate: 1/60`, so one request
per minute. This tool reads that file and obeys it by default, single threaded.

That shapes how it works. A full `sync` is about 80 requests, so roughly an hour and a half,
and it is the only slow step: it collects name, Part No, price, image and a multi-option flag
for every product in the catalogue. Full product pages, with specs and per-SKU variants, are
fetched only for the products you ask for, so a shortlist of thirty costs thirty requests
rather than 2,350.

`--delay` overrides the interval. It is deliberately explicit, and going faster than a site
asks for is your call, not the tool's default.

### How long a full crawl takes

Product pages are around 300 KB and the site answers in about 2.1 s, measured. For all 2,349
products:

| delay | full detail crawl |
|---|---|
| 60 s (what robots.txt asks) | ~40 h |
| 5 s | ~4.6 h |
| 2 s | ~2.7 h |
| 1 s | ~2 h |

`detail --all` only picks products whose page is missing, so a run can be interrupted and
resumed, and an interrupted crawl loses nothing: pages already fetched stay in the cache.

Every response is cached gzipped under `cache/`, keyed by URL, so re-running is free and a
parser fix can be replayed with `reparse` without touching the network again.

## What gets stored

`waveshare.db` holds categories, products, the category memberships, and for products you
fetched in full: description, wiki link, images, the option axes (`Version Options: with
case, without case`) and one row per purchasable variant with its SKU.

Two notes on what you get, because both are easy to get wrong:

**Prices.** A category listing prints a single figure even when a product has options, so
after `sync` you only know the entry price. The product page carries the real range, for
example `$25.99 - $32.99`, and `detail` writes it back over the listing figure. So
`price_max` is populated exactly for the products whose page you fetched.

**Specifications are not a structured field.** Waveshare does not publish a spec table on
product pages; the details live in the prose. The full description is stored, typically a
few thousand words including resolution, interfaces and dimensions, but there is no
`specs` dictionary to query. A parser that mined the prose would be guesswork that breaks
on the first page written differently, so the field is deliberately absent rather than
present and empty.

Waveshare's variants are not standard Magento. The page carries its own blob:

```js
var waveshare_sku_attributes = [{"sku ":"30733","attributes":["without case"], ...}];
```

Note the trailing space in the `sku ` key. The parser accepts it with or without, because
this format has already changed once and will probably change again. When it does, the fix
is a parser change plus `reparse`, with no re-crawling.

## Development

```bash
uv run pytest --cov     # 100% branch coverage is enforced
uv run ruff check .
uv run mypy
```

Parser tests run against real pages captured from the site and frozen under
`tests/fixtures/`, so they catch a change in the site's markup rather than agreeing with a
mock. Nothing in the suite touches the network.

## Licence

MIT.
