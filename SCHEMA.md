# The catalogue schema

Everything is one SQLite file. There is no API and no ORM: open it and write SQL.

```bash
waveshare-catalog sql "SELECT count(*) FROM products"
sqlite3 waveshare.db "SELECT count(*) FROM products"
```

## The tables

Tables, and where each one's facts come from.

- products(url, slug, name, part_no, price_min, price_max, image, has_options)
  One row per product. `price_max` is only filled for products whose page was fetched.
  About a fifth appear in no category at all and are known only from the sitemap.
- details(product_url, description, axes_json, wiki_url, images_json, ...)
  `description` is the product's own prose. It no longer contains the family comparison
  matrix, which used to make text searches answer about a sibling instead.
- specs(product_url, key, key_norm, value, source)
  Facts as the page's own specification table states them, keys verbatim. `key_norm` is
  the key lowercased with whitespace collapsed, which is what you should filter on. There
  is no fixed vocabulary: 2,570 distinct keys, the commonest 40 covering under a third.
  Pin assignments are prefixed `pin:`.
- variants(product_url, sku, label, attributes_json, unsaleable)
  One row per purchasable combination. Per-variant prices are not available: the site
  renders them in JavaScript on click, so only the product's range is known.
- family_members(product_url, model) and family_specs(model, key, value)
  The comparison matrix a page prints for its whole product family. This is the only
  cross-reference between related products, since categories do not link siblings. Join
  `family_members.model` to `products.part_no` to keep only siblings in the catalogue.
- resources(product_url, kind, url, title)
  Files the product's wiki links: `cad` (2D/3D geometry, for designing an enclosure),
  `schematic`, `datasheet`, `demo`, `software`. The shop page links none of these.
- categories(url, name, parent_url, depth) and product_categories(product_url, category_url)
  Category membership, which is only populated if the catalogue was collected with
  `sync --with-categories`.

## Three things that will mislead you if you do not know them

**Specification keys are a long tail, not a vocabulary.** Filter on `key_norm`, and expect
the same idea to be written several ways: `display size`, `lcd size`, `screen size`. Look
before you assume:

```sql
SELECT key_norm, count(*) n FROM specs GROUP BY 1 ORDER BY n DESC LIMIT 40;
```

**`family_specs` is not a product table.** Its `model` column is whatever the vendor typed
into a comparison matrix. Roughly half of those strings resolve to a catalogue product;
the rest are discontinued items, or labels from a table that only looked like a family.
Join to `products` when you need certainty.

**Prices are per product, not per variant.** `price_min` and `price_max` bracket the whole
range. Which exact configuration costs what is not in the database and cannot be, because
the site computes it in the browser.

## Recipes

Everything a page states about one product:

```sql
SELECT key, value FROM specs
WHERE product_url = 'https://www.waveshare.com/esp32-s3-touch-lcd-3.5.htm';
```

Displays under two inches, from stated facts rather than guessed from the name. Note the
`LIKE '%inch%'`: some pages put the active area in millimetres under the same key, so
without it a 27 mm panel reads as 27 inches.

```sql
SELECT p.part_no, s.value AS size, p.price_min
FROM products p JOIN specs s ON s.product_url = p.url
WHERE s.key_norm = 'display size' AND s.value LIKE '%inch%'
  AND CAST(replace(s.value, 'inch', '') AS REAL) < 2
ORDER BY p.price_min;
```

The cheaper twin: siblings of a board that are themselves in the catalogue.

```sql
SELECT DISTINCT m.model, pr.price_min
FROM family_members m
JOIN products pr ON lower(pr.part_no) = lower(m.model)
WHERE m.product_url = 'https://www.waveshare.com/esp32-s3-touch-lcd-3.5.htm'
ORDER BY pr.price_min;
```

How two siblings differ. Expect a key to carry several values: a model is tabulated by every
page in its family, and not all of them label the columns the same way. Where one page's
header row groups four columns under `display`, all four land under that one key.

```sql
SELECT model, key, value FROM family_specs
WHERE model IN ('ESP32-S3-Touch-LCD-3.5', 'RP2350-Touch-LCD-3.5')
ORDER BY key, model;
```

Boards whose wiki publishes CAD geometry, which is what you need to design an enclosure:

```sql
SELECT p.name, r.url FROM resources r
JOIN products p ON p.url = r.product_url
WHERE r.kind = 'cad' AND p.name != '' ORDER BY p.name;
```

Products no category lists — where the things you never knew existed are:

```sql
SELECT p.name, p.price_min FROM products p
LEFT JOIN product_categories c ON c.product_url = p.url
WHERE c.product_url IS NULL AND p.name != '' AND p.price_min > 2
ORDER BY p.price_min;
```

## For agents

If you have a shell, use it: the file is the interface and `sqlite3` beats anything this
project could wrap around it. If you do not, install the MCP server and point a client at
it; it offers exactly the same two things, this document and read-only SQL.

```bash
uv tool install "waveshare-catalog[mcp]"
WAVESHARE_CATALOG_DB=/path/to/waveshare.db waveshare-catalog-mcp
```
