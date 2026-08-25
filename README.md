# waveshare-catalog

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

# 4. take it elsewhere
uv run waveshare-catalog export --format csv --price-max 60 > shortlist.csv
```

`stats` shows how much has been collected. `reparse` re-runs the parsers over pages already
on disk, which costs no network at all.

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

Every response is cached gzipped under `cache/`, keyed by URL, so re-running is free and a
parser fix can be replayed with `reparse` without touching the network again.

## What gets stored

`waveshare.db` holds categories, products, the category memberships, and for products you
fetched in full: description, spec table, wiki link, images and one row per purchasable
variant with its SKU.

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
