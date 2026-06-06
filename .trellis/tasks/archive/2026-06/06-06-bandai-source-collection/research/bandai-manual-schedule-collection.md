# Bandai Manual and Schedule Collection Research

Date: 2026-06-06

## Summary

Bandai collection should be modeled as two related but separate source families:

- `bandai_manual`: official manual metadata from `manual.bandai-hobby.net`.
- `bandai_schedule_*`: official product schedule metadata from Japanese, English,
  and Chinese Bandai Hobby schedule/product pages.

Manual records and schedule/product records must not share identity by default.
They can be related through explicit or inferred mappings. The strongest observed
automatic signal is the Bandai manual listing's bilingual Japanese/English title
pair, combined with official Bandai schedule product data.

## Official Sources Observed

### Manual Source

- `https://manual.bandai-hobby.net/`
- Detail URL shape: `https://manual.bandai-hobby.net/menus/detail/{manual_id}`
- PDF URL can be parsed from the detail page viewer data, then normalized to
  `https://manual.bandai-hobby.net/pdf/{manual_id}.pdf`.

Observed manual list item fields:

- Japanese title.
- English title.
- Release date text.
- Manual detail id.

Observed manual detail fields:

- Japanese title.
- Product image.
- `品番` raw value.
- Release date.
- Manual-side brand/product line text, such as `HG`.
- Work/series text, such as a Gundam work title.
- Viewer data source containing `/pdf/{manual_id}.pdf`.

Important implementation note: the English title is visible on the list page, so
Bandai manual collection must preserve list-level fields while fetching details.
Do not normalize from detail pages alone.

### Japanese Schedule Source

- `https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM`
- Example confirmed with browser-like headers:
  `https://bandai-hobby.net/schedule/index.php?saledate=202612`
- Product detail URL shape: `https://bandai-hobby.net/item/{product_id}/`
- Example: `https://bandai-hobby.net/item/01_7017/`

The non-`www` domain is required for the observed schedule pages. Earlier
`www.bandai-hobby.net/schedule/` checks returned a Bandai official 404 page, but
the parameterized non-`www` schedule URL worked with a normal browser user agent
and Japanese `Accept-Language`.

Observed schedule card fields:

- Japanese product title.
- Product URL and product id, such as `01_7185`.
- Product image.
- Japanese yen price, tax included, such as `2,530円(税10%込)`.
- Release month, such as `2026年12月`.

Observed product detail taxonomy fields:

- Product line via `/brand/{slug}/`, for example `/brand/hg/`.
- Series via `/series/{slug}/`, for example `/series/endlesswaltz/`.
- Breadcrumb class: `p-breadcrumb`.
- Flat taxonomy cards: classes including `c-card__flat p-card__flat`.

Example taxonomy:

```text
brand_line:
  url: https://bandai-hobby.net/brand/hg/
  slug: hg
  label: HG［ハイグレード］

series:
  url: https://bandai-hobby.net/series/endlesswaltz/
  slug: endlesswaltz
  label: 新機動戦記ガンダムWシリーズ
```

### English Schedule Source

- `https://global.bandai-hobby.net/en-others/schedule/`
- Month URL shape:
  `https://global.bandai-hobby.net/en-others/schedule/index.php?saledate=YYYYMM`
- Product detail URL shape:
  `https://global.bandai-hobby.net/en-others/item/{product_id}/`
- Example: `https://global.bandai-hobby.net/en-others/item/01_7017/`

Observed schedule card fields:

- English product title.
- Product URL and product id, such as `01_7017`.
- Product image.
- Yen price, tax excluded per product detail notes.
- Release month, such as `Jun, 2026`.

Observed product detail taxonomy:

```text
brand_line:
  url: https://global.bandai-hobby.net/en-others/brand/hg/
  slug: hg
  label: HG [HIGH GRADE]

series:
  url: https://global.bandai-hobby.net/en-others/series/endlesswaltz/
  slug: endlesswaltz
  label: MOBILE SUIT GUNDAM WING series
```

The English site often shares the same `01_xxxx` product id with the Japanese
site. That is the strongest observed ja/en product merge signal.

### Chinese Schedule Source

- `https://bandaihobbysite.cn/schedule`
- Product detail URL shape:
  `https://bandaihobbysite.cn/index/index/detail/id/{cn_id}`
- Examples:
  - `https://bandaihobbysite.cn/index/index/detail/id/3236`
  - `https://bandaihobbysite.cn/index/index/detail/id/3404`
  - `https://bandaihobbysite.cn/index/index/detail/id/3428`

Observed schedule card fields:

- Chinese product title.
- Chinese detail id, such as `3236`, `3404`, `3428`.
- Product image.
- Japanese-region suggested retail price, tax included, such as
  `4,180日元(含税)`.
- Release month, such as `2026年06月发售`.

Observed detail taxonomy fields:

```text
category:
  url: https://bandaihobbysite.cn/characterplastic
  label: 角色模型

brand_line:
  url: https://bandaihobbysite.cn/index/index/brand/cate/43
  id: 43
  label: RG

series:
  url: https://bandaihobbysite.cn/index/index/series/cate/147
  id: 147
  label: 机动警察系列
```

Not every Chinese detail page has a series link. Some pages only expose category
and product line.

Observed limitation: sampled Chinese detail pages did not include the matching
Japanese/English `01_xxxx` product id, JAN, barcode, Japanese title, or English
title in the HTML. Chinese records therefore cannot be reliably merged into the
ja/en product core through a shared official id.

## Product and Manual Identity

Manual identity remains:

```text
manual_source_key = "bandai:{manual_id}"
```

Schedule product source identity should be separate:

```text
schedule_source_key = "bandai-schedule:{locale}:{product_source_id}"
```

Examples:

```text
bandai-schedule:ja:01_7017
bandai-schedule:en:01_7017
bandai-schedule:zh-Hans:3236
```

Merged Bandai product identity should be separate again:

```text
product_key = "bandai-product:{stable_product_id_or_generated_key}"
```

For ja/en pages that share `01_xxxx`, use that id:

```text
product_key = "bandai-product:01_7017"
```

For Chinese-only products without a confirmed ja/en match, keep a locale-local
record and/or generate a candidate product key only after scoring.

## Proposed Schedule Product Record Shape

```json
{
  "schedule_source_key": "bandai-schedule:en:01_7017",
  "source": "bandai_schedule_en",
  "locale": "en",
  "market": "en-others",
  "product_source_id": "01_7017",
  "product_url": "https://global.bandai-hobby.net/en-others/item/01_7017/",
  "title": "HG 1/144 GUNDAM SANDROCK CUSTOM EW",
  "normalized_title": "HG1/144GUNDAMSANDROCKCUSTOMEW",
  "image_url": "https://...",
  "release": {
    "market": "en-others",
    "release_month": "2026-06",
    "release_date_precision": "month",
    "raw": "Jun, 2026"
  },
  "price": {
    "amount": 3800,
    "currency": "JPY",
    "tax_included": false,
    "price_region": "JP",
    "raw": "3,800Yen"
  },
  "category": null,
  "brand_line": {
    "kind": "brand",
    "slug": "hg",
    "line_code": "HG",
    "line_name": "HIGH GRADE",
    "label": "HG [HIGH GRADE]",
    "url": "https://global.bandai-hobby.net/en-others/brand/hg/"
  },
  "series": {
    "kind": "series",
    "slug": "endlesswaltz",
    "label": "MOBILE SUIT GUNDAM WING series",
    "url": "https://global.bandai-hobby.net/en-others/series/endlesswaltz/"
  },
  "raw": {}
}
```

## Merged Product Shape

Release and price are market/source-specific, not product-global single values.
English-market and Japanese-market release months may differ, so release month
must not be a hard cross-market identity condition.

```json
{
  "product_key": "bandai-product:01_7017",
  "source_ids": {
    "ja": "01_7017",
    "en": "01_7017"
  },
  "titles": {
    "ja": "HG 1/144 ...",
    "en": "HG 1/144 GUNDAM SANDROCK CUSTOM EW",
    "zh-Hans": null
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
      "raw": "2026年06月"
    },
    {
      "source": "bandai_schedule_en",
      "locale": "en",
      "market": "en-others",
      "release_month": "2026-07",
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
  "related_schedule_records": [
    "bandai-schedule:ja:01_7017",
    "bandai-schedule:en:01_7017"
  ]
}
```

## Taxonomy Parsing

Parse product taxonomy from detail pages, not only schedule cards.

Priority:

1. Flat taxonomy cards with classes including `c-card__flat p-card__flat`.
2. Breadcrumbs with class `p-breadcrumb`.
3. Ignore top navigation and footer navigation as product taxonomy sources.

URL pattern rules:

```text
/brand/{slug}/
  -> brand_line

/series/{slug}/
  -> series

/index/index/brand/cate/{id}
  -> brand_line

/index/index/series/cate/{id}
  -> series

/gunpla
/characterplastic
/30ML
  -> category
```

Product line label parsing:

```text
HG［ハイグレード］ -> line_code=HG, line_name=ハイグレード
HG [HIGH GRADE] -> line_code=HG, line_name=HIGH GRADE
RG [-REAL GRADE-] -> line_code=RG, line_name=REAL GRADE
HG -> line_code=HG, line_name=null
```

## Manual to Product Association

Use the Bandai manual list's bilingual title pair as the main automatic
association signal.

Recommended priority:

```text
P0: Curated confirmed mapping.
P1: Shared official product id or URL.
P2: Manual ja title + manual en title match schedule/product ja/en titles.
P3: Single-language title match plus compatible taxonomy.
P4: Fuzzy title match plus taxonomy plus price/image/description evidence.
```

Manual release date should only be compared against Japanese schedule release as
an auxiliary signal. Do not require English or Chinese release month to match
the Japanese/manual release month, because different markets may release in
different months.

Example relationship:

```json
{
  "manual_source_key": "bandai:5119",
  "related_products": [
    {
      "product_key": "bandai-product:01_7017",
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
      ]
    }
  ]
}
```

## Chinese Matching Limitation

Chinese schedule records cannot currently be confirmed by shared product id in
the sampled pages. They should be matched as candidates unless a curated mapping
or future official bridge field is available.

Observed missing from sampled Chinese pages:

- Matching `01_xxxx` Japanese/English product id.
- JAN/barcode.
- Japanese title.
- English title.

Candidate matching signals:

- Chinese title tokens.
- Product line, such as `HG`, `RG`, `MG`, `30MM`, `30MS`.
- Series taxonomy or series name in description.
- Scale tokens, such as `1/144`, `1/100`, `1/48`.
- English fragments retained in Chinese title, such as `AV-98Plus`,
  `VF-31E`, `EW`, `RX-78-2`.
- Price compatibility, including tax adjustment:
  `3800 * 1.10 = 4180`.
- Release month as a weak signal only.
- Optional image perceptual hash if future implementation decides this is worth
  the extra request cost.

Suggested score:

```text
+40 shared official product id
    Usually unavailable for Chinese records currently.

+25 strong title token match
+20 brand_line match
+20 series alias match
+15 price compatible, including tax adjustment
+10 release month close, weak only
+10 scale match
+10 image perceptual match, optional
```

Suggested thresholds:

```text
>= 85 and unique best candidate:
  auto matched

70-84:
  candidate, needs review

< 70:
  unmatched
```

Use curated mappings to promote Chinese candidates to confirmed links:

```yaml
mappings:
  - product_key: bandai-product:01_7017
    zh_schedule_key: bandai-schedule:zh-Hans:3236
    status: confirmed
    reason: "Chinese title, EW series alias, HG line, and tax-included price match official ja/en product."
```

## Incremental Collection

### Manual Incremental

- Crawl Bandai manual list pages in newest-first order.
- Preserve list fields, especially English title.
- Follow pagination from page controls rather than incrementing until empty.
  Large out-of-range page requests can return first-page content.
- Fetch detail pages for new records, changed list hashes, and periodic
  revalidation.
- Use normalized detail hashes, not raw HTML hashes, to avoid cache-busting and
  whitespace noise.

### Schedule Incremental

Schedule collection should be month-window based.

For normal incremental runs:

- Current month.
- Future 6-12 months.
- Past 2-3 months.

For periodic full refresh:

- Current year.
- Adjacent historical/future windows as needed.

Fetch product detail pages for:

- New product source ids.
- Changed schedule card hash.
- Current/future month periodic revalidation.
- Explicit full refresh.

Do not use release month equality as a cross-market identity requirement.

## Output Recommendation

Manual dataset should stay focused on manuals.

Add product/schedule outputs for Bandai:

```text
dist/products.bandai.v1.json
dist/products.bandai.compact.v1.json
```

Manual records may include related product candidates, but product title,
release, price, category, product line, and series belong in the product dataset.

