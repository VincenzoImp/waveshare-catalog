# waveshare-catalog

[![CI](https://github.com/VincenzoImp/waveshare-catalog/actions/workflows/ci.yml/badge.svg)](https://github.com/VincenzoImp/waveshare-catalog/actions/workflows/ci.yml)

The [Waveshare](https://www.waveshare.com) catalogue as a SQLite file you can query, plus the
crawler that builds it.

Waveshare sells around 2,350 products and its own search cannot answer the questions people
actually have about them. You pick a board and only later find the identical one with a
different microcontroller for four dollars less, or never learn that the thing you needed
existed at all. This turns the catalogue into a table, so that "a touch display under $40
that ships with a case and can take a battery" is a query rather than forty browser tabs.

Waveshare prints, on each product page, a comparison matrix of that product's whole family.
Nothing else in the catalogue links related products — categories certainly do not — so this
is the query the project exists for:

```console
$ waveshare-catalog sql "
    SELECT DISTINCT m.model, pr.price_min
    FROM family_members m JOIN products pr ON lower(pr.part_no) = lower(m.model)
    WHERE m.product_url = 'https://www.waveshare.com/esp32-s3-touch-lcd-2.htm'
    ORDER BY pr.price_min LIMIT 6"
model              price_min
-----------------  ---------
ESP32-C3-LCD-1.47  9.99
ESP32-C6-GEEK      9.99
ESP32-C6-LCD-1.3   9.99
ESP32-S3-GEEK      9.99
ESP32-C3-LCD-0.71  11.99
ESP32-C5-LCD-1.47  11.99
```

## Get the data

The [latest release](https://github.com/VincenzoImp/waveshare-catalog/releases/latest) carries
a ready database. Most people never need to run the crawler.

```bash
curl -LO https://github.com/VincenzoImp/waveshare-catalog/releases/latest/download/waveshare-catalog.db.gz
gunzip waveshare-catalog.db.gz && mv waveshare-catalog.db waveshare.db
sqlite3 waveshare.db "SELECT count(*) FROM specs"
```

It holds every product with its page fetched: prices, specifications, purchasable variants,
category membership, the family comparison matrices, and the files each product's wiki
publishes. It is a snapshot, so prices drift; re-run the crawler for current data. The
product text in it belongs to Waveshare and is bundled so you can query the catalogue, not
as content to republish.

**[`SCHEMA.md`](SCHEMA.md) is the thing to read next.** It says what each table means, where
its facts come from, and the three things that will mislead you if you do not know them.

## Query it

The database is the interface. There is no API to learn:

```bash
waveshare-catalog sql "SELECT part_no, price_min FROM products ORDER BY price_min LIMIT 5"
waveshare-catalog sql "SELECT * FROM specs LIMIT 5" --format csv > specs.csv
```

`query` and `export` are a friendlier front door for the common filters — name, Part No,
category, price, options — and `stats` shows how much has been collected.

For an AI agent with a shell, that is all there is: hand it `SCHEMA.md` and let it write SQL.
For one without a shell, there is an MCP server offering exactly the same two things:

```bash
uv tool install "waveshare-catalog[mcp]"
WAVESHARE_CATALOG_DB=$PWD/waveshare.db waveshare-catalog-mcp
```

It exposes `schema()` and `query(sql)`, and nothing else. Themed tools like
`search_displays(size_max, has_case)` were deliberately not built: they would freeze one
guess about what people want to ask, which is the mistake this project already made once.

## Install the crawler

Run it without installing anything:

```bash
uvx --from git+https://github.com/VincenzoImp/waveshare-catalog waveshare-catalog --help
```

Or keep it around:

```bash
uv tool install git+https://github.com/VincenzoImp/waveshare-catalog
```

`pipx install` works the same way if you prefer it. To work on it, clone the repository and
run `uv sync`.

## Build the data yourself

```bash
# 1. register the whole catalogue and read the root listing
waveshare-catalog sync --with-categories

# 2. fetch product pages: specifications, variants, family matrices
waveshare-catalog detail --all

# 3. fetch each product's wiki for the files it links
waveshare-catalog wiki --all

# 4. see where you are
waveshare-catalog stats
```

Every step resumes where the last one stopped and commits as it goes, so an interrupted run
loses nothing. `reparse` re-runs the parsers over pages already on disk, which costs no
network and is how you pick up a parser fix.

## How this catalogue is actually shaped

Four things measured against the live site, each of which decides how the tool works.

**A fifth of the catalogue is in no category at all.** 465 of the 2,350 products are listed in
`sitemap.xml`, have a live page and can be bought, yet appear under no category.
`1.02inch-e-paper.htm` is one of them: a real 1.02inch e-Paper module at $5.99, absent from
`/product/displays/e-paper.htm` and from every `epaper-N` subcategory. So `sync` registers
every URL the sitemap names. Without that, no amount of crawling would find them — and they
are exactly where the products nobody knows about live.

**Crawling the category tree is close to pointless for discovery:**

| route | requests | coverage |
|---|---|---|
| root listing, paginated | 24 | 80% |
| the 13 top-level categories | 49 | 78.7%, i.e. *less* |
| all 225 leaf categories | ~265 | still ~80%, orphans still missing |

`--with-categories` is worth its 49 requests to know which category a product belongs to, but
it will not find you a single extra product.

**Each page states its facts in a table, and buries a second one.** The product page carries
its own specification table — size, resolution, driver IC, touch IC, the active area in
millimetres — and also a comparison matrix of the entire product family, up to 92 rows wide.
Both are parsed into `specs` and `family_specs`. Before that they were flattened into the
description, where searching for "with case" returned 306 products when only 88 have one: the
rest of the hits belonged to a sibling.

**The wiki is the only source of downloads.** A product page links no files at all. The wiki
links the CAD geometry you need to design an enclosure, the schematic, and every component
datasheet.

## What a full crawl costs

Waveshare's `robots.txt` asks for `Crawl-delay: 60` and `Request-rate: 1/60`, one request per
minute. This tool reads that file and obeys it by default, single threaded. `--delay`
overrides it: going faster than a site asks is your call, not the tool's default.

Pages are around 300 KB. The last column is measured wall clock, not arithmetic: with
`--delay 1` a page takes about 2.1 s, because the site's own response time dominates the
delay rather than adding to it.

| goal | requests | at 60 s | at `--delay 1` |
|---|---|---|---|
| every URL, plus metadata for 80% | 25 | ~26 min | ~1 min |
| the same, with category membership | ~75 | ~75 min | ~3 min |
| every product page | 2,350 | ~40 h | ~1.5 h |
| every wiki as well | +1,662 | ~28 h | ~1 h |

Nothing is lost to an interruption: every response is cached gzipped under `cache/`, keyed by
URL, and progress is committed as it goes.

## What the parsers cannot give you

**Per-variant prices.** A product page shows a range, `$25.99 - $32.99`, and lists the
purchasable combinations, but the price of one exact combination is computed in JavaScript
when you click it. `variants` therefore has SKUs and labels but no prices.

**A tidy specification vocabulary.** 2,570 distinct keys appear across the catalogue and the
40 commonest cover under a third of them. Keys are stored exactly as written, with a
lowercased `key_norm` to filter on. Mapping them onto a fixed set of columns would drop the
tail silently, so it is not done.

**A clean list of siblings.** `family_members.model` is whatever the vendor typed into a
comparison matrix. Roughly half of those strings resolve to a catalogue product; join to
`products` when you need certainty.

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
