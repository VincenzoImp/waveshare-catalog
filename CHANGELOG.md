# Changelog

## 0.1.1

Everything here came out of running the tool over the whole catalogue rather than reading
the code.

- Products in no category now get their name, Part No and image from their own page. Before
  this they came only from listings, so 465 products, a fifth of the catalogue, sat in the
  database with no name at all.
- A long crawl commits as it goes. Previously nothing was written until the command ended,
  so an interruption after two hours left the database empty, even though the pages were
  safely cached.
- The HTTP client is closed when a command finishes, instead of leaving its connection pool
  to the garbage collector.
- Only a product's own images are stored. A page shows around 57 catalogue thumbnails and
  all but a handful belong to related items, which was 18 MB of useless URLs across the
  catalogue.
- `--db` and `--cache` are accepted either before or after the subcommand.

## 0.1.0

First release.

- `sync` registers every product URL from `sitemap.xml`, then reads the root listing for
  name, Part No, price, image and a multi-option flag. 25 requests cover the whole
  catalogue by URL and 80% of it with metadata. Category membership is opt-in behind
  `--with-categories`, because walking the category tree costs ten times as much and finds
  no additional products.
- `detail` fetches product pages, one at a time, for a shortlist or for everything still
  missing (`--all`). It records the description, price range, wiki link, images, option
  axes and one row per purchasable variant with its SKU.
- `query` and `export` filter the local database by name, Part No, category, price, whether
  a product has options and whether any category lists it. Output as text, CSV or JSONL.
- `reparse` re-runs the parsers over the on-disk page cache, so a parser fix costs no
  network.
- Fetching reads `robots.txt` and honours its crawl delay by default, single threaded.
  `--delay` overrides it explicitly. Transient failures are retried, transport errors are
  converted, and every response is cached gzipped by URL.
- Databases created by an earlier version are migrated on open.
