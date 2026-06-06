# Source Metadata Schema Design

Date: 2026-06-06

## Purpose

This document starts the cross-source schema design for `plamoindex` after
reviewing Bandai and Kotobukiya source behavior.

The key design decision is to keep manuals and products separate:

- Manuals describe official instruction/manual source records.
- Products describe official product/schedule/detail records.
- Relationships connect manuals and products with explicit status, method, and
  confidence.

This avoids forcing prices, market-specific release months, category, product
line, and series into `ManualRecord`.

## Schema Families

Recommended v0.1 schema families:

```text
ManualRecord
ProductRecord
ProductSourceRecord
RelationshipRecord
TaxonomyRef
ReleaseInfo
PriceInfo
Provenance
SourceStatus
```

`ManualRecord` is the original dataset contract for downstream manual search.
`ProductRecord` is a new supplemental dataset contract for official product
metadata.

## Identity Keys

### Manual Identity

```text
manual_source_key = "{source}:{manual_source_id}"
```

Examples:

```text
bandai:5119
kotobukiya:538
wave:mk-001
```

Manual identity is source-local and must not be treated as product identity.

### Product Source Identity

Product source records represent one official source/locale product page or
schedule entry before merging.

```text
product_source_key = "{source-family}:{locale}:{product_source_id}"
```

Examples:

```text
bandai-schedule:ja:01_7017
bandai-schedule:en:01_7017
bandai-schedule:zh-Hans:3236
kotobukiya-product:en:p4934054063482
```

### Merged Product Identity

Merged products represent one inferred or confirmed product across source-local
records.

```text
product_key = "{manufacturer}-product:{stable_id}"
```

Examples:

```text
bandai-product:01_7017
kotobukiya-product:p4934054063482
```

For Bandai ja/en, shared `01_xxxx` product ids are strong merge keys. For Bandai
Chinese records, no shared `01_xxxx` was observed, so matching is candidate
unless curated. For Kotobukiya, the instruction detail page's direct product
detail link confirms the manual-to-product relationship.

### Taxonomy Identity

Taxonomy terms are source- and locale-local by default.

```text
taxonomy_key = "{source-family}:{locale}:{kind}:{slug-or-id}"
```

Examples:

```text
bandai-schedule:en:brand:hg
bandai-schedule:ja:series:endlesswaltz
bandai-schedule:zh-Hans:series:147
kotobukiya-product:en:title:megamidevice
kotobukiya-product:en:series:unpainted-figures
```

Do not assume identical labels imply the same taxonomy. Preserve source URL,
slug/id, and locale.

## ManualRecord

Manual records are the primary manual index output.

```json
{
  "schema_version": 1,
  "manual_source_key": "bandai:5119",
  "source": "bandai",
  "source_type": "automated",
  "manual_source_id": "5119",
  "title": "HG 1/144 メッサーＭ０１型 (ガウマン機)",
  "title_en": "HG 1/144 MESSER TYPE-M01 (GAWMAN USE)",
  "localized_titles": {
    "ja": "HG 1/144 メッサーＭ０１型 (ガウマン機)",
    "en": "HG 1/144 MESSER TYPE-M01 (GAWMAN USE)"
  },
  "normalized_titles": {
    "ja": "HG1/144メッサーM01型ガウマン機",
    "en": "HG1/144MESSERTYPEM01GAWMANUSE"
  },
  "brand": "BANDAI SPIRITS",
  "manufacturer_item_code": null,
  "source_url": "https://manual.bandai-hobby.net/menus/detail/5119",
  "pdf_url": "https://manual.bandai-hobby.net/pdf/5119.pdf",
  "pdf_urls": {
    "ja": "https://manual.bandai-hobby.net/pdf/5119.pdf"
  },
  "image_url": "https://...",
  "manual_preview_images": [],
  "release_date_raw": "2026年5月30日発売",
  "release_date": "2026-05-30",
  "release_month": "2026-05",
  "release_date_precision": "day",
  "languages": ["ja"],
  "manual_type": "assembly",
  "availability": "available",
  "catalog_product_id": null,
  "catalog_mapping_status": "unmapped",
  "related_products": [
    {
      "product_key": "bandai-product:01_7017",
      "relationship": "manual_for_product",
      "status": "matched",
      "method": "official_bilingual_title_with_jp_release_check",
      "confidence": 0.97
    }
  ],
  "aliases": [],
  "search_tokens": [],
  "provenance": {
    "collector": "bandai_manual",
    "collection_method": "scrape",
    "collected_at": "2026-06-06T00:00:00Z",
    "updated_at": "2026-06-06T00:00:00Z"
  },
  "raw": {}
}
```

Notes:

- `brand` remains manufacturer/official brand, not product line.
- Product line such as Bandai `HG` belongs in product/taxonomy metadata unless
  it is part of a manual-side source field.
- `pdf_url` is primary/preferred for backward compatibility.
- `pdf_urls` preserves all language-specific PDFs when available.
- `related_products` is relationship metadata, not a replacement for
  `catalog_product_id`.

## ProductSourceRecord

Product source records preserve source-local product detail before merging.

```json
{
  "schema_version": 1,
  "product_source_key": "bandai-schedule:en:01_7017",
  "source": "bandai_schedule_en",
  "manufacturer": "BANDAI SPIRITS",
  "locale": "en",
  "market": "en-others",
  "product_source_id": "01_7017",
  "product_url": "https://global.bandai-hobby.net/en-others/item/01_7017/",
  "title": "HG 1/144 GUNDAM SANDROCK CUSTOM EW",
  "normalized_title": "HG1/144GUNDAMSANDROCKCUSTOMEW",
  "manufacturer_item_code": null,
  "image_url": "https://...",
  "image_urls": ["https://..."],
  "category": null,
  "brand_line": {
    "taxonomy_key": "bandai-schedule:en:brand:hg",
    "kind": "brand",
    "slug": "hg",
    "line_code": "HG",
    "line_name": "HIGH GRADE",
    "label": "HG [HIGH GRADE]",
    "url": "https://global.bandai-hobby.net/en-others/brand/hg/"
  },
  "series": {
    "taxonomy_key": "bandai-schedule:en:series:endlesswaltz",
    "kind": "series",
    "slug": "endlesswaltz",
    "label": "MOBILE SUIT GUNDAM WING series",
    "url": "https://global.bandai-hobby.net/en-others/series/endlesswaltz/"
  },
  "product_series": null,
  "release": {
    "source": "bandai_schedule_en",
    "locale": "en",
    "market": "en-others",
    "release_month": "2026-06",
    "release_date_precision": "month",
    "raw": "Jun, 2026"
  },
  "prices": [
    {
      "source": "bandai_schedule_en",
      "locale": "en",
      "market": "en-others",
      "amount": 3800,
      "currency": "JPY",
      "tax_included": false,
      "price_region": "JP",
      "raw": "3,800Yen"
    }
  ],
  "description": null,
  "specs": {},
  "provenance": {
    "collector": "bandai_schedule_en",
    "collection_method": "scrape",
    "collected_at": "2026-06-06T00:00:00Z"
  },
  "raw": {}
}
```

## ProductRecord

Product records merge source-local product source records into a product view.

```json
{
  "schema_version": 1,
  "product_key": "bandai-product:01_7017",
  "manufacturer": "BANDAI SPIRITS",
  "source_type": "automated",
  "titles": {
    "ja": "HG 1/144 ...",
    "en": "HG 1/144 GUNDAM SANDROCK CUSTOM EW",
    "zh-Hans": null
  },
  "normalized_titles": {
    "ja": "...",
    "en": "HG1/144GUNDAMSANDROCKCUSTOMEW"
  },
  "manufacturer_item_codes": [],
  "source_ids": {
    "bandai_schedule_ja": "01_7017",
    "bandai_schedule_en": "01_7017"
  },
  "product_urls": {
    "ja": "https://bandai-hobby.net/item/01_7017/",
    "en": "https://global.bandai-hobby.net/en-others/item/01_7017/"
  },
  "taxonomy_by_locale": {
    "ja": {
      "brand_line": {
        "slug": "hg",
        "label": "HG［ハイグレード］"
      },
      "series": {
        "slug": "endlesswaltz",
        "label": "新機動戦記ガンダムWシリーズ"
      }
    },
    "en": {
      "brand_line": {
        "slug": "hg",
        "label": "HG [HIGH GRADE]"
      },
      "series": {
        "slug": "endlesswaltz",
        "label": "MOBILE SUIT GUNDAM WING series"
      }
    }
  },
  "releases": [
    {
      "source": "bandai_schedule_ja",
      "locale": "ja",
      "market": "jp",
      "release_month": "2026-06",
      "release_date_precision": "month",
      "raw": "2026年06月"
    },
    {
      "source": "bandai_schedule_en",
      "locale": "en",
      "market": "en-others",
      "release_month": "2026-07",
      "release_date_precision": "month",
      "raw": "Jul, 2026"
    }
  ],
  "prices": [
    {
      "source": "bandai_schedule_ja",
      "locale": "ja",
      "market": "jp",
      "amount": 4180,
      "currency": "JPY",
      "tax_included": true,
      "raw": "4,180円(税10%込)"
    },
    {
      "source": "bandai_schedule_en",
      "locale": "en",
      "market": "en-others",
      "amount": 3800,
      "currency": "JPY",
      "tax_included": false,
      "raw": "3,800Yen"
    }
  ],
  "related_manuals": [
    {
      "manual_source_key": "bandai:5119",
      "relationship": "manual_for_product",
      "status": "matched",
      "method": "official_bilingual_title_with_jp_release_check",
      "confidence": 0.97
    }
  ],
  "related_product_sources": [
    "bandai-schedule:ja:01_7017",
    "bandai-schedule:en:01_7017"
  ],
  "provenance": {
    "collector": "product_merge",
    "collection_method": "merge",
    "collected_at": "2026-06-06T00:00:00Z"
  },
  "raw": {}
}
```

Rules:

- `releases` is a list because release month can differ by market/source.
- `prices` is a list because price tax treatment and source market differ.
- Chinese Bandai product sources remain candidate merges unless curated or a
  future official bridge field is discovered.
- Kotobukiya instruction-to-product links can produce confirmed relationships.

## RelationshipRecord

Relationships connect manuals, product source records, and merged products.

```json
{
  "schema_version": 1,
  "relationship_key": "rel:manual-product:bandai:5119:bandai-product:01_7017",
  "from_key": "bandai:5119",
  "to_key": "bandai-product:01_7017",
  "relationship": "manual_for_product",
  "status": "matched",
  "method": "official_bilingual_title_with_jp_release_check",
  "confidence": 0.97,
  "matched_fields": [
    "manual.title_ja",
    "manual.title_en",
    "product.title_ja",
    "product.title_en",
    "jp_release_month"
  ],
  "ignored_differences": [
    {
      "field": "en_release_month",
      "reason": "cross-market release dates may differ"
    }
  ],
  "reason": null,
  "provenance": {
    "collector": "product_merge",
    "collection_method": "inference",
    "collected_at": "2026-06-06T00:00:00Z"
  }
}
```

Allowed `status` values:

```text
confirmed
matched
candidate
rejected
unmapped
```

Status meanings:

- `confirmed`: explicit official link or curated confirmed mapping.
- `matched`: high-confidence automatic match.
- `candidate`: plausible but needs review.
- `rejected`: explicitly rejected candidate.
- `unmapped`: no candidate.

## Source-Specific Relationship Rules

### Bandai

Strong signals:

- Japanese and English schedule product pages share `01_xxxx`.
- Manual list exposes Japanese and English title pair.
- Manual release date can be compared to Japanese schedule release month.
- Product detail taxonomy provides product line and series.

Weak/candidate signals:

- Chinese schedule has separate numeric ids and translated titles.
- Chinese release month may differ from Japanese/English market release.
- Chinese mapping should use title tokens, product line, series aliases, price tax
  adjustment, scale, and optional image signals.

### Kotobukiya

Strong signals:

- Instruction detail directly links to product detail.
- Product code appears in both instruction and product detail.
- Product detail id in URL can be used as product source id.

Recommended status:

```text
official instruction detail -> product detail link = confirmed
```

## ReleaseInfo

```json
{
  "source": "bandai_schedule_ja",
  "locale": "ja",
  "market": "jp",
  "release_date": null,
  "release_month": "2026-06",
  "release_date_precision": "month",
  "raw": "2026年06月"
}
```

Allowed `release_date_precision`:

```text
day
month
year
unknown
```

Do not invent a day for month-only sources.

## PriceInfo

```json
{
  "source": "kotobukiya_product",
  "locale": "en",
  "market": "jp-shop",
  "amount": 19800,
  "currency": "JPY",
  "tax_included": true,
  "price_region": "JP",
  "raw": "JPY 19,800 incl. tax"
}
```

Rules:

- Keep tax-included and tax-excluded prices as separate entries.
- Preserve raw text.
- Store market/source semantics separately from price region.

## TaxonomyRef

```json
{
  "taxonomy_key": "bandai-schedule:en:series:endlesswaltz",
  "kind": "series",
  "slug": "endlesswaltz",
  "id": null,
  "line_code": null,
  "line_name": null,
  "label": "MOBILE SUIT GUNDAM WING series",
  "url": "https://global.bandai-hobby.net/en-others/series/endlesswaltz/"
}
```

For product lines:

```json
{
  "kind": "brand",
  "slug": "hg",
  "line_code": "HG",
  "line_name": "HIGH GRADE",
  "label": "HG [HIGH GRADE]",
  "url": "https://global.bandai-hobby.net/en-others/brand/hg/"
}
```

## Output Files

Keep original manual outputs:

```text
dist/index.json
dist/schema.v1.json
dist/manuals.latest.json
dist/manuals.compact.v1.json
dist/manuals.bandai.v1.json
dist/manuals.kotobukiya.v1.json
dist/manuals.curated.v1.json
dist/sources.json
dist/checksums.json
```

Recommended supplemental product outputs:

```text
dist/products.latest.json
dist/products.compact.v1.json
dist/products.bandai.v1.json
dist/products.kotobukiya.v1.json
dist/product-sources.bandai.v1.json
dist/product-sources.kotobukiya.v1.json
dist/relationships.v1.json
```

`manuals.compact.v1.json` should remain usable without products. Product outputs
are supplemental and can be consumed by downstream tools that need enriched
names, prices, release windows, and taxonomy.

## Validation Rules

Required validation:

- Every `manual_source_key` is unique.
- Every `product_source_key` is unique.
- Every `product_key` is unique.
- Relationship targets must exist unless status is `candidate` with explicit
  unresolved target metadata.
- `confirmed` relationships require either:
  - explicit official link;
  - curated mapping with reason;
  - shared official product id.
- `matched` relationships require method, confidence, and matched fields.
- Cross-market release month differences must not fail validation.
- Price entries must include amount, currency, tax status, and raw text.
- Month-only releases must not be converted to fake day-level dates.
- Product details must not be required for curated manual-only records.

## Open Design Questions

- Whether `p4934054063482` should later be promoted to explicit `jan_code`.
- Whether image perceptual hashes are worth adding for Bandai Chinese candidate
  matching.
- How much title normalization should happen before it risks false positives.
- Whether downstream consumers want relationship records embedded in manuals and
  products, stored separately, or both.

## Decisions

- Product schema and product outputs are in v0.1 scope.
- Bandai Chinese product records are emitted as candidates unless a curated
  mapping or future official source bridge confirms them.
