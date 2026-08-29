# Changelog

## 0.2.0

The catalogue was used to answer a real question for the first time — which display has a
case, a battery and a camera — and the answer took a day of writing regular expressions
against a wall of text. The page had published every one of those facts in a table, and the
parser had been flattening them into prose. This release stops doing that, and turns the
project from a crawler that produces a file into a dataset with a crawler attached.

### The pages state facts; now the database does too

The parser used to flatten each page into one text blob, discarding the structure Waveshare
publishes. Everything in this section follows from reading the tables instead, and none of it
needed the network: `reparse` rebuilt the whole catalogue from the existing cache, product
pages and wikis alike, in under ten minutes.

- Specifications are stored as facts. `specs` holds 17,525 key/value rows read from the
  page's own table — display size, resolution, driver IC, touch IC, and the active area in
  millimetres. Keys are kept verbatim next to a normalised form, because the catalogue has
  no fixed vocabulary: 2,572 distinct keys, of which the 40 commonest cover under a third,
  so columns would have dropped the tail.
- The family comparison matrix is a table again, in `family_members` and `family_specs`.
  This is the only cross-reference between products in the catalogue, since categories do
  not link siblings, and it makes "what else is like this, and is it cheaper" a single
  query. It is stored once rather than once per page: every page of a family reprints the
  whole matrix, so keeping it per page cost 545,688 rows to state 9,726 facts and grew the
  database to 143 MB.
- A wide table is only read as a family when its first column is titled `Part Number`,
  `Model` or `Product`. Shape alone had been treating wide specification tables as
  families, filing labels such as `Sensitivity` and `1D` as sibling models; that noise fell
  from 48% of models to 25%.
- `description` no longer carries other products' specifications. 373 of 561 display
  descriptions embedded the family matrix, so searching the text for `with case` returned
  306 products where only 88 have one — the rest belonged to a sibling.

### The wiki, for the files a product page never links

- New `wiki` command, selecting products the same way `detail` does and honouring the same
  crawl delay. It records what each product's wiki offers for download in `resources`,
  classified as `cad`, `schematic`, `datasheet`, `demo` or `software`. The CAD entry is the
  2D and 3D geometry, which is what you need to design an enclosure; a shop page links no
  files at all, so the wiki is the only source. Reading all 1,662 of them found 10,966
  files, among them CAD geometry for 520 products and a schematic for 802.
- A handful of product pages write their wiki link relative to the site root rather than
  absolutely. Those three fetches used to fail; they are now resolved. Four more wikis stay
  unreachable because the page links one the site does not have.
- Only the links are taken. The wiki's prose is an Arduino tutorial and its tables list
  library versions, so harvesting them would have filed `v8.4.0 = "Install Online"` as a
  specification.

### SQL instead of flags

- New `sql` command, taking any statement and opening the database read-only, so a write is
  refused by how the file is opened rather than by a pattern match on the text. Output as an
  aligned table, CSV or JSONL.
- New `SCHEMA.md`: what each table means, where its facts come from, the three things that
  will mislead you, and query recipes that were run against the real catalogue rather than
  imagined.
- New optional MCP server, `waveshare-catalog[mcp]`, offering an agent the schema and
  read-only SQL and nothing else. Themed tools such as `search_displays(size_max, has_case)`
  were deliberately not built: they would freeze one guess about what people want to ask.
- `query` and `export` are unchanged. They remain the friendly front door for the common
  filters.

### Also

- `stats` reports the new tables and how many wikis are still to read.
- The README leads with the dataset rather than the crawler, since the crawler is run once
  and the data is used many times.

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
