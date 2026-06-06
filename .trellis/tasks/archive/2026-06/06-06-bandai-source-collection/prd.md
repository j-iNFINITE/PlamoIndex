# Source Collection and Schema Design

## Goal

Design and implement the metadata schema and source collection model for
`plamoindex`, covering manual records, supplemental product records, taxonomy,
prices, releases, and manual-product relationships across Bandai and Kotobukiya.

The project must keep manual identity separate from product/catalog identity,
while still allowing official or high-confidence relationships between manual
records and product records.

## What I Already Know

- `plamoindex` is a Python CLI project that generates static JSON metadata
  datasets for official plastic model manual sources.
- Manual PDFs must not be downloaded, mirrored, or redistributed; store metadata
  and official links only.
- Bandai manual pages expose manual metadata and list entries include both
  Japanese and English titles.
- Bandai product metadata requires additional schedule/product sources:
  Japanese, English, and Chinese Bandai Hobby pages.
- Bandai Japanese and English product pages often share an official `01_xxxx`
  product id, making ja/en product merging strong.
- Bandai Chinese product pages use separate numeric ids and translated names;
  no shared `01_xxxx`, JAN, Japanese title, or English title was observed in
  sampled Chinese HTML.
- Bandai Chinese records therefore need candidate matching and/or curated
  mappings.
- Bandai release month can differ across markets, so release month cannot be a
  hard cross-market identity condition.
- Kotobukiya instruction pages already provide strong manual metadata:
  instruction id, title, product code, PDF links, languages, preview images, and
  an official product detail link.
- Kotobukiya instruction-to-product relationships can be confirmed when the
  instruction detail links directly to product detail.
- Product metadata belongs in product records, not inside `ManualRecord`.

## Research References

- [`research/bandai-manual-schedule-collection.md`](research/bandai-manual-schedule-collection.md)
  — Bandai manual, schedule, taxonomy, multilingual matching, and incremental
  collection research.
- [`research/kotobukiya-manual-product-collection.md`](research/kotobukiya-manual-product-collection.md)
  — Kotobukiya instruction/product detail research and confirmed relationship
  strategy.
- [`info.md`](info.md)
  — Cross-source schema design draft for manuals, products, relationships,
  releases, prices, and taxonomy.
- [`plamoindex-development-plan.md`](../../../plamoindex-development-plan.md)
  — Original project plan and v0.1 scope.

## Requirements

- Preserve the original manual-first dataset goal.
- Include product schema and product outputs in v0.1.
- Keep manual source identity separate from product/catalog identity.
- Add schema support for supplemental product metadata without making it required
  for every manual record.
- Support `ManualRecord` fields for localized titles, language-specific PDFs,
  release date/month precision, manual preview images, and related products.
- Add product-side schema families:
  - `ProductSourceRecord`
  - `ProductRecord`
  - `RelationshipRecord`
  - `TaxonomyRef`
  - `ReleaseInfo`
  - `PriceInfo`
- Support source-local product identities:
  - `bandai-schedule:ja:{id}`
  - `bandai-schedule:en:{id}`
  - `bandai-schedule:zh-Hans:{id}`
  - `kotobukiya-product:en:{id}`
- Support merged product identities:
  - `bandai-product:{id}`
  - `kotobukiya-product:{id}`
- Support relationship status values:
  - `confirmed`
  - `matched`
  - `candidate`
  - `rejected`
  - `unmapped`
- Support market/source-specific releases and prices as lists, not single
  product-global values.
- Output supplemental product datasets alongside manual datasets.
- Parse taxonomy such as category, product line, series, and product series from
  source detail pages.
- Treat Bandai ja/en shared `01_xxxx` ids as strong product merge keys.
- Treat Bandai manual Japanese/English title pair as strong manual-product
  association evidence.
- Treat Bandai Chinese product records as candidates unless a curated mapping or
  future official bridge field confirms the relationship.
- Treat Kotobukiya instruction detail product links as confirmed manual-product
  relationships.
- Preserve raw source metadata needed for auditability and future parser
  improvements.

## Acceptance Criteria

- [ ] Schema can represent a Bandai manual record with Japanese and English
      titles.
- [ ] Schema can represent a Bandai product merged from ja/en product source
      records sharing the same `01_xxxx` id.
- [ ] Schema can represent a Bandai Chinese product source record that is only a
      candidate for a merged product.
- [ ] Schema can represent cross-market release month differences without
      validation failure.
- [ ] Schema can represent tax-included and tax-excluded prices as separate
      entries.
- [ ] Schema can represent taxonomy refs for Bandai `brand/hg`,
      `series/endlesswaltz`, and Chinese numeric taxonomy ids.
- [ ] Schema can represent a Kotobukiya manual record linked to product detail
      via a confirmed relationship.
- [ ] Schema can represent Kotobukiya product fields: category, series,
      product_series, release month, price, scale, size, material, age, sculptor,
      and product code.
- [ ] Validation rejects duplicate manual, product source, and product keys.
- [ ] Validation requires method/confidence/matched fields for automatic
      `matched` relationships.
- [ ] Validation requires official link or curated reason for `confirmed`
      relationships.
- [ ] Existing manual-only downstream consumers can still use compact manual
      data without product outputs.
- [ ] Product outputs are generated for Bandai and Kotobukiya product metadata.
- [ ] Bandai Chinese product relationships can be emitted as candidates and
      promoted to confirmed through curated mappings.

## Out of Scope

- Downloading or mirroring PDFs.
- Downloading or mirroring product images.
- Full product catalog crawling unrelated to manuals, except Bandai schedule
  pages required for product metadata.
- Confirming Bandai Chinese product mappings without evidence or curated
  mappings.
- User accounts, backend management UI, or public API.
- External pip-installed source plugins.
- Cloudflare Worker API.

## Technical Approach

Start from schema and validation before implementing source collectors.

Recommended schema direction:

- Keep `ManualRecord` close to the original plan but add optional relationship
  and language-specific PDF/title fields.
- Add product outputs as supplemental datasets:
  - `products.latest.json`
  - `products.compact.v1.json`
  - `products.bandai.v1.json`
  - `products.kotobukiya.v1.json`
  - `product-sources.bandai.v1.json`
  - `product-sources.kotobukiya.v1.json`
  - `relationships.v1.json`
- Use Pydantic models for schema validation.
- Keep mapping logic explicit and auditable via relationship records.
- Use curated YAML mappings to promote high-confidence candidates to confirmed
  relationships when official source data is insufficient.

## Decision (ADR-lite)

**Context**: Bandai and Kotobukiya both provide manual metadata, but product
metadata and product identity behave differently by source. Bandai requires
schedule/product pages and candidate matching for Chinese records. Kotobukiya has
direct instruction-to-product links.

**Decision**: Use separate manual, product source, merged product, and
relationship schemas. Keep product release/price/taxonomy out of manual records,
but allow manuals to reference related products.

**Consequences**:

- The schema is more complex than a manual-only dataset.
- Downstream consumers can still use manual-only outputs.
- Product-aware consumers get official metadata without overloading
  `ManualRecord`.
- Bandai Chinese mappings remain honest candidates unless curated or confirmed by
  future official bridge fields.

## Decision: v0.1 Product Scope

Product schema and product outputs are included in v0.1.

Scope:

- Implement manual schema and manual outputs.
- Implement product source schema, merged product schema, and relationship schema.
- Emit product datasets alongside manual datasets.
- Support Bandai product metadata from schedule/product sources.
- Support Kotobukiya product metadata from instruction-linked product detail pages.
- Keep Bandai Chinese product records as candidate matches unless a curated
  mapping or future official source bridge confirms them.

Out of scope for v0.1:

- Forcing automatic confirmed matches for Bandai Chinese records.
- Building a manual review UI for candidate matches.
- Crawling full product catalogs unrelated to manuals/schedule scope.

## Definition of Done

- Research files are persisted under the task.
- PRD and schema design are updated with confirmed requirements.
- Pydantic schema models are implemented.
- Validation covers manual/product identity uniqueness and relationship status
  rules.
- Focused tests cover Bandai-style, Kotobukiya-style, and curated relationship
  scenarios.
- Lint, type-check, and tests pass.
- Documentation notes explain manual/product separation.
