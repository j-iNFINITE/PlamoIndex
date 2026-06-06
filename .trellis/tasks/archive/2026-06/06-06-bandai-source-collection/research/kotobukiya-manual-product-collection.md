# Kotobukiya Manual and Product Collection Research

Date: 2026-06-06

## Summary

Kotobukiya instruction pages already contain enough metadata to create useful
manual records. Product detail pages provide valuable supplemental product
metadata and, unlike Bandai Chinese schedule pages, the manual-to-product
relationship is explicit through an official `View Product Details` link.

For v0.1, Kotobukiya does not need a separate schedule crawler if the goal is a
manual index. The recommended flow is:

```text
instructions list
  -> instruction detail
  -> product detail if linked
```

Product metadata should be stored in product records, not forced into
`ManualRecord`.

## Official Sources Observed

### Instruction List

- `https://www.kotobukiya.co.jp/en/instructions/`
- Pagination shape: `https://www.kotobukiya.co.jp/en/instructions/?page=N`
- Detail URL shape:
  `https://www.kotobukiya.co.jp/en/instructions/detail/{instruction_id}/`

Observed list fields:

- Instruction detail id.
- Product/title text.
- Product code.
- Manual language label, such as `Instructions (JPN)`, `Instructions (ENG)`,
  or `Instructions (JPN/ENG)`.
- Thumbnail/image.

The list currently has a small page count compared with Bandai manual pages, so
full list discovery on each run is reasonable.

### Instruction Detail

Example:

- `https://www.kotobukiya.co.jp/en/instructions/detail/538/`

Observed fields:

- Manual title: `Instruction Manuals｜ASRA ARCHER Modelers Edition`.
- Product code: `PV256`.
- PDF download links:
  - `/en/instructions/dl-ja/{hash}/`
  - `/en/instructions/dl-en/{hash}/`
- Manual preview images under `/files/inst/...`.
- Product detail link:
  `https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/`

Manual identity should remain:

```text
manual_source_key = "kotobukiya:{instruction_id}"
```

Example:

```text
manual_source_key = kotobukiya:538
manual_source_id = 538
manufacturer_item_code = PV256
```

The primary `pdf_url` can prefer Japanese if available, then English. Preserve
all language-specific PDF URLs in `raw` or a structured `pdf_urls` field.

### Product Detail

Example:

- `https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/`

Observed product detail fields:

- Product detail source id: `p4934054063482`.
- Title: `ASRA ARCHER Modelers Edition`.
- Category badge/breadcrumb: `Figures`.
- Release month: `2024.12`.
- Price:
  - `JPY 19,800 incl. tax`.
  - `JPY 18,000 excl. tax`.
- Series/title: `MEGAMI DEVICE`.
- Product series: `Unpainted Figures`.
- Scale: `2/1`.
- Size: `360mm tall`.
- Specifications: `Unpainted Figure / Kit`.
- Product material: `PVC (Phthalate-free)・ABS・Iron・Acrylic・Polyester`.
- Age rating: `Ages 15 and up`.
- Sculptor(s): `BRAIN, KOTOBUKIYA`.
- Product code: `PV256`.
- Product description.
- Product images.
- Related products.
- Link back to the instruction detail if available.

Product identity should be:

```text
product_key = "kotobukiya-product:{product_source_id}"
```

Example:

```text
product_key = kotobukiya-product:p4934054063482
```

The numeric portion of the product URL looks like a JAN/EAN-like official product
identifier, but until the schema explicitly defines JAN semantics, store it as
`product_source_id` and optionally `raw.product_url_code`.

## Relationship Strength

Kotobukiya manual-to-product mapping can be confirmed when the instruction
detail page links directly to a product detail page.

Example relationship:

```json
{
  "from_key": "kotobukiya:538",
  "to_key": "kotobukiya-product:p4934054063482",
  "relationship": "manual_for_product",
  "status": "confirmed",
  "method": "official_instruction_detail_product_link",
  "confidence": 1.0
}
```

This is much stronger than Bandai Chinese schedule matching, which currently
lacks a shared product id and requires candidate scoring.

## Proposed Kotobukiya Manual Record Additions

```json
{
  "manual_source_key": "kotobukiya:538",
  "source": "kotobukiya",
  "manual_source_id": "538",
  "title": "ASRA ARCHER Modelers Edition",
  "brand": "KOTOBUKIYA",
  "manufacturer_item_code": "PV256",
  "source_url": "https://www.kotobukiya.co.jp/en/instructions/detail/538/",
  "pdf_url": "https://www.kotobukiya.co.jp/en/instructions/dl-ja/...",
  "languages": ["ja", "en"],
  "related_products": [
    {
      "product_key": "kotobukiya-product:p4934054063482",
      "relationship": "manual_for_product",
      "status": "confirmed",
      "method": "official_instruction_detail_product_link",
      "confidence": 1.0
    }
  ],
  "raw": {
    "pdf_urls": {
      "ja": "https://www.kotobukiya.co.jp/en/instructions/dl-ja/...",
      "en": "https://www.kotobukiya.co.jp/en/instructions/dl-en/..."
    },
    "manual_preview_images": [
      "https://www.kotobukiya.co.jp/files/inst/..."
    ],
    "product_url": "https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/"
  }
}
```

## Proposed Kotobukiya Product Record

```json
{
  "product_key": "kotobukiya-product:p4934054063482",
  "source": "kotobukiya_product",
  "locale": "en",
  "market": "jp-shop",
  "manufacturer": "KOTOBUKIYA",
  "product_source_id": "p4934054063482",
  "product_url": "https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/",
  "title": "ASRA ARCHER Modelers Edition",
  "manufacturer_item_code": "PV256",
  "category": {
    "label": "Figures",
    "url": "https://www.kotobukiya.co.jp/en/product/figures/"
  },
  "series": {
    "label": "MEGAMI DEVICE",
    "url": "https://www.kotobukiya.co.jp/en/title/megamidevice/"
  },
  "product_series": {
    "label": "Unpainted Figures",
    "url": "https://www.kotobukiya.co.jp/en/series/unpainted-figures/"
  },
  "releases": [
    {
      "source": "kotobukiya_product",
      "locale": "en",
      "market": "jp-shop",
      "release_month": "2024-12",
      "release_date_precision": "month",
      "raw": "2024.12"
    }
  ],
  "prices": [
    {
      "source": "kotobukiya_product",
      "locale": "en",
      "market": "jp-shop",
      "amount": 19800,
      "currency": "JPY",
      "tax_included": true,
      "raw": "JPY 19,800 incl. tax"
    },
    {
      "source": "kotobukiya_product",
      "locale": "en",
      "market": "jp-shop",
      "amount": 18000,
      "currency": "JPY",
      "tax_included": false,
      "raw": "JPY 18,000 excl. tax"
    }
  ],
  "specs": {
    "scale": "2/1",
    "size": "360mm tall",
    "specifications": ["Unpainted Figure / Kit"],
    "material": "PVC (Phthalate-free)・ABS・Iron・Acrylic・Polyester",
    "age_rating": "Ages 15 and up",
    "sculptors": ["BRAIN", "KOTOBUKIYA"]
  },
  "related_manuals": [
    {
      "manual_source_key": "kotobukiya:538",
      "relationship": "manual_for_product",
      "status": "confirmed"
    }
  ],
  "raw": {}
}
```

## Incremental Collection

Recommended v0.1 incremental strategy:

```text
1. Crawl all instruction list pages.
2. Extract instruction detail candidates and list hashes.
3. Fetch instruction detail when:
   - new id
   - list hash changed
   - detail revalidation window expires
4. Extract PDF URLs, preview images, product code, and product detail URL.
5. Fetch product detail when:
   - product URL is new
   - instruction detail product URL changed
   - product detail revalidation window expires
6. Store normalized product detail hash.
7. Reuse previous records when unchanged.
```

Because the instruction set is small, full list discovery on every run is
acceptable. Product detail fetches can still be hash/revalidation-gated to reduce
load.

## Output Recommendation

Kotobukiya manual records should remain in:

```text
dist/manuals.kotobukiya.v1.json
```

Supplemental product records should go into:

```text
dist/products.kotobukiya.v1.json
```

The full product dataset can combine all manufacturers:

```text
dist/products.latest.json
dist/products.compact.v1.json
```

Manual records can include `related_products`, but product prices, release
months, category, series, and product specs belong in product outputs.

