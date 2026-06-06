# Implement plamoindex v0.1

## Goal

Complete, verify, and harden `plamoindex` v0.1 as a Python CLI/static dataset
generator for official plastic model manual and supplemental product metadata.

The implementation must preserve the original manual-first dataset contract
while adding product/source/relationship outputs for Bandai and Kotobukiya, based
on the already completed source research. The project must store metadata and
official links only; it must not download, mirror, or redistribute manual PDFs or
product images.

## Current Implementation Baseline

The repository already contains a substantial v0.1 skeleton from the prior
implementation commit:

- Python project metadata and CLI entry point in `pyproject.toml`.
- Configuration loader in `src/plamoindex/config.py`.
- Manual/product/source/relationship Pydantic models under
  `src/plamoindex/models/`.
- Source plugin base and built-in registry under `src/plamoindex/sources/`.
- Dataset merge/build/output pipeline in `src/plamoindex/merge.py`,
  `src/plamoindex/dataset.py`, and `src/plamoindex/output/`.
- Curated YAML loader/validator under `src/plamoindex/curated/`.
- Focused unit tests under `tests/`.
- Existing generated `dist/` sample output.

Known gaps to close during this task:

- `BandaiSource` and `KotobukiyaSource` are still collector stubs.
- CLI `collect` does not persist raw/normalized collection data or support the
  original `--raw` behavior.
- No shared HTTP/fetch/cache layer exists yet.
- Product key generation currently needs to align with the accepted schema
  (`bandai-product:{id}`, `kotobukiya-product:{id}`), not manufacturer-name
  fallbacks such as `bandai_spirits-product:{id}`.
- `write_dataset()` writes product files, but `index.json`, `sources.json`, and
  `plamoindex validate` still need to fully include product outputs and real
  source statuses.
- Product merging and relationship generation are still shallow.
- Curated product/manual mappings, especially for Bandai Chinese schedule
  candidates, are not implemented yet.
- Runtime dependencies for real HTML collection/parsing are not complete.
- README and GitHub Actions workflows are not present.

## Requirements

### Manual/Product Identity

- Keep manual source identity separate from product identity.
- Manual keys must use `manual_source_key = "{source}:{manual_source_id}"`.
- Product source keys must use source-local locale-aware identities such as:
  - `bandai-schedule:ja:{product_id}`
  - `bandai-schedule:en:{product_id}`
  - `bandai-schedule:zh-Hans:{cn_id}`
  - `kotobukiya-product:en:{product_id}`
- Merged product keys must use:
  - `bandai-product:{stable_id}`
  - `kotobukiya-product:{stable_id}`
- `ManualRecord.catalog_product_id` must not be populated from source-local
  manual ids. Product links must use `related_products` and standalone
  `RelationshipRecord` entries.

### Bandai Collection

- Collect manual metadata from `manual.bandai-hobby.net`.
- Preserve list-level fields, especially the Japanese and English title pair,
  while fetching detail pages for images, release details, product line/work
  text, and PDF links.
- Collect product/schedule metadata from all three Bandai schedule sources:
  - Japanese: `https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM`
  - English:
    `https://global.bandai-hobby.net/en-others/schedule/index.php?saledate=YYYYMM`
  - Chinese: `https://bandaihobbysite.cn/schedule`
- Request the Japanese schedule endpoint with normal browser-like headers,
  including an appropriate user agent and Japanese-friendly accept language.
- Fetch product detail pages from schedule cards to parse taxonomy and richer
  metadata.
- Parse product line and series from detail taxonomy links and breadcrumbs,
  including `p-breadcrumb`, `/brand/{slug}/`, `/series/{slug}/`, Chinese
  `/index/index/brand/cate/{id}`, and Chinese `/index/index/series/cate/{id}`.
- Preserve release month/date precision without inventing fake day-level dates.
- Preserve tax-included and tax-excluded prices as separate `PriceInfo` entries.
- Merge Japanese and English Bandai products by shared official `01_xxxx` ids.
- Treat Japanese/English release month differences as valid market-specific
  differences, not merge failures.
- Use the manual list Japanese/English title pair as the primary automatic
  manual-to-product matching signal.
- Treat Chinese schedule records as candidates unless a curated mapping or future
  official bridge field confirms the relationship. Do not auto-confirm Chinese
  records merely from translated title similarity.

### Kotobukiya Collection

- Collect instruction metadata from
  `https://www.kotobukiya.co.jp/en/instructions/` and paginated list pages.
- Fetch instruction detail pages for PDF URLs, preview images, product code,
  languages, and official product detail links.
- Prefer Japanese PDF as `pdf_url` when available, then English, while
  preserving all language-specific PDFs in `pdf_urls`.
- Follow the official `View Product Details` link from instruction detail pages
  to product detail pages when present.
- Extract product metadata from product detail pages:
  category, series/title, product series, release month, tax-included and
  tax-excluded prices, scale, size, specifications, material, age rating,
  sculptor(s), product code, description, and images.
- Create confirmed manual-product relationships when an instruction detail page
  links directly to a product detail page.
- Do not add a separate Kotobukiya schedule crawler for v0.1 unless it becomes
  necessary to satisfy the instruction/manual index.

### Incremental Collection

- Add a raw/cache path for collection runs, defaulting to `data/raw/` or a config
  value, and support it from the CLI.
- Store non-published source snapshots or normalized raw records plus a manifest
  with stable source ids, normalized content hashes, collection timestamps, and
  relevant response metadata.
- Do not publish raw HTML/cache artifacts in `dist/`.
- For Bandai manual incremental collection:
  - Discover manual list pages newest-first.
  - Follow pagination controls rather than probing arbitrary page numbers.
  - Fetch detail pages for new ids, changed list hashes, explicit refreshes, and
    periodic revalidation.
  - Use normalized detail hashes instead of raw HTML hashes where practical.
- For Bandai schedule incremental collection:
  - Collect a month window for normal runs: current month, future 6-12 months,
    and past 2-3 months.
  - Support a wider/full refresh mode for current-year and historical windows.
  - Fetch product detail pages for new product ids, changed schedule card hashes,
    current/future month revalidation, and explicit refreshes.
- For Kotobukiya incremental collection:
  - Crawl all instruction list pages on normal runs because the instruction set
    is small.
  - Fetch instruction detail pages for new ids, changed list hashes, explicit
    refreshes, and revalidation expiry.
  - Fetch product details when the product URL is new, changes, or reaches a
    revalidation window.
- Reuse previously normalized records when pages are unchanged.

### Polite Crawling and Anti-Abuse Guardrails

- Implement basic polite crawling controls for all live source collection.
- Use configured per-source delays with random jitter, rather than fixed
  sleep-only timing. The effective delay should be bounded and auditable, for
  example `delay_seconds +/- jitter_seconds` or explicit min/max delay settings.
- Limit live collection concurrency per source/domain. v0.1 should default to
  sequential requests unless a source-specific reason justifies low concurrency.
- Use source-appropriate browser-like request headers where research shows they
  are required for normal public access, especially Bandai Japanese schedule
  pages.
- Honor cache/revalidation decisions so unchanged pages are not fetched
  repeatedly.
- Apply exponential backoff or longer cool-down delays for transient errors,
  especially HTTP 429, 403, 408, 5xx, and connection timeouts.
- Record rate-limit/backoff events in source status or collection logs so failed
  runs are diagnosable.
- Do not implement anti-access-control behavior in v0.1: no CAPTCHA bypass,
  login/session abuse, proxy rotation, IP rotation, or attempts to access
  non-public resources.

### Curated Data

- Keep curated manual records and overrides first-class.
- Add curated mapping support for manual-product and product-source/product
  relationships.
- Curated mappings must include status and reason/evidence.
- Curated mappings may promote Bandai Chinese candidate relationships to
  confirmed, but unmapped Chinese schedule records must remain candidates or
  standalone product source records.
- Duplicate curated records must fail validation unless represented as explicit
  overrides or mappings.

### Dataset Output

- Keep original manual outputs:
  - `dist/index.json`
  - `dist/schema.v1.json`
  - `dist/manuals.latest.json`
  - `dist/manuals.compact.v1.json`
  - `dist/manuals.bandai.v1.json`
  - `dist/manuals.kotobukiya.v1.json`
  - `dist/manuals.curated.v1.json`
  - `dist/sources.json`
  - `dist/checksums.json`
- Add and validate product outputs:
  - `dist/products.latest.json`
  - `dist/products.compact.v1.json`
  - `dist/products.bandai.v1.json`
  - `dist/products.kotobukiya.v1.json`
  - `dist/product-sources.bandai.v1.json`
  - `dist/product-sources.kotobukiya.v1.json`
  - `dist/relationships.v1.json`
- `index.json` must include file references and counts for manual, product,
  product-source, and relationship outputs.
- `sources.json` and `index.json.sources` must preserve real per-source statuses,
  including failed sources, rather than fabricating successful statuses in the
  writer.
- `checksums.json` must include every published output file.
- `manuals.compact.v1.json` must remain usable by manual-only downstream
  consumers without requiring product files.

### CLI

- Preserve and complete these v0.1 commands:
  - `plamoindex sources list`
  - `plamoindex collect --source <id|all> --raw data/raw`
  - `plamoindex curated validate curated/`
  - `plamoindex build --raw data/raw --curated curated/ --dist dist`
  - `plamoindex sync --source <id|all> --curated curated/ --dist dist`
  - `plamoindex validate --dist dist`
- `collect` should persist collection artifacts and report manual, product
  source, product, and relationship counts.
- `build` should be able to build from persisted raw/normalized collection data
  and curated files.
- `sync` should run collection plus build.
- `validate` must check all required manual and product outputs, index
  structure, source statuses, checksums, and schema-valid record files.

### Failure Handling

- A single automated source failure must not discard all usable data.
- If at least one source or curated data source succeeds, the build may produce
  output with failed source statuses recorded.
- Schema errors, duplicate keys, invalid curated overrides, invalid curated
  mappings, and invalid confirmed/matched relationships must fail the build.
- If every automated source fails and there are no curated records to publish,
  the command must fail.
- Tests must not require live network access. Live website checks, if added, must
  be opt-in integration checks.

### Documentation and CI

- Add README usage examples covering install, source listing, collect, sync,
  build, validate, and output file meanings.
- Add GitHub Actions workflows for lint/type-check/tests and scheduled/manual
  dataset build, matching the v0.1 project plan.
- Ensure `pyproject.toml` runtime dependencies cover the implemented HTTP and
  HTML parsing approach.

## Acceptance Criteria

- [ ] `plamoindex sources list` shows Bandai and Kotobukiya built-in sources.
- [ ] `plamoindex curated validate curated/` validates the sample curated data.
- [ ] `plamoindex collect --source bandai --raw data/raw` persists Bandai manual
      and schedule/product collection artifacts without downloading PDFs.
- [ ] `plamoindex collect --source kotobukiya --raw data/raw` persists
      Kotobukiya instruction and product collection artifacts without
      downloading PDFs.
- [ ] Bandai manual records preserve Japanese and English titles from the manual
      list when available.
- [ ] Bandai Japanese schedule collection works for parameterized month URLs
      such as `saledate=202612` using browser-like headers.
- [ ] Bandai product detail parsing captures product line and series taxonomy
      from taxonomy links or `p-breadcrumb`.
- [ ] Bandai ja/en product source records sharing `01_xxxx` merge into
      `bandai-product:01_xxxx`.
- [ ] Bandai English-market and Japanese-market release month differences are
      preserved as separate release entries.
- [ ] Bandai Chinese product source records use
      `bandai-schedule:zh-Hans:{id}` and remain candidate/unconfirmed unless
      curated mapping evidence promotes them.
- [ ] Kotobukiya instruction details produce manual records with product code,
      language-specific PDF URLs, preview images, and official source URLs.
- [ ] Kotobukiya product detail links produce confirmed
      `manual_for_product` relationships.
- [ ] Kotobukiya product records include category, series, product series,
      release month, prices, scale, size, material, age rating, sculptor(s), and
      product code when present.
- [ ] Product keys use `bandai-product:{id}` and
      `kotobukiya-product:{id}` consistently.
- [ ] `plamoindex sync --source all --curated curated/ --dist dist` produces all
      required manual, product, source, relationship, schema, index, and checksum
      files.
- [ ] `plamoindex validate --dist dist` validates every required output file,
      including product and relationship files.
- [ ] Duplicate `manual_source_key`, `product_source_key`, `product_key`, and
      `relationship_key` values fail validation.
- [ ] `matched` relationships require method, confidence, and matched fields.
- [ ] `confirmed` relationships require official-link evidence or curated
      reason/evidence.
- [ ] A failed source is reflected in `sources.json`/`index.json.sources` without
      erasing successful source or curated data.
- [ ] Live collection uses bounded randomized request delays, per-source/domain
      sequential or low-concurrency fetching, cache reuse, and backoff for
      transient/rate-limit errors.
- [ ] The implementation does not include CAPTCHA bypass, proxy/IP rotation, or
      access-control circumvention.
- [ ] Unit and fixture tests cover schemas, merge rules, curated data,
      output writer, CLI validation, Bandai parsing, Kotobukiya parsing, and
      incremental cache reuse.
- [ ] Test suite, Ruff, and mypy pass without live network access.
- [ ] README and GitHub Actions workflows exist and match the implemented CLI.

## Technical Approach

Implement this as a stabilization and completion pass over the existing code,
not a rewrite.

1. Audit and align the existing schema, merge, writer, CLI, and tests against
   the accepted source research.
2. Add a small shared HTTP/fetch/cache layer with configured headers, timeout,
   retries, delay, and normalized content hashing.
3. Complete Bandai collection with separate manual and schedule/product paths.
4. Complete Kotobukiya collection with instruction-to-product traversal.
5. Implement product source merging, manual-product relationships, and curated
   mappings.
6. Update outputs, index metadata, checksums, and validation to cover product
   files and real source statuses.
7. Add fixtures and parser-level tests first; keep live network checks out of
   default tests.
8. Add README and CI workflows after CLI behavior is stable.

## Decision (ADR-lite)

**Context**: The original project plan was manual-first. Research showed Bandai
and Kotobukiya both need supplemental product metadata, but product identity and
release/price semantics are source- and market-specific. Bandai Chinese product
pages lack a shared ja/en product id in sampled HTML, while Kotobukiya has
explicit instruction-to-product links.

**Decision**: v0.1 includes product source records, merged product records, and
relationship records alongside manual outputs. Manual identity remains separate.
Bandai ja/en products merge by shared `01_xxxx`; Bandai Chinese records remain
candidates unless curated; Kotobukiya instruction product links are confirmed.

**Consequences**: The schema and pipeline are more complex than a manual-only
MVP, but downstream manual-only consumers can still use compact manual output,
while product-aware consumers get official release, price, taxonomy, and
relationship metadata without overloading `ManualRecord`.

## Out of Scope

- Downloading, mirroring, or redistributing manual PDFs.
- Downloading, mirroring, or publishing product images beyond official image
  URLs.
- Web UI, backend management UI, or user accounts.
- Cloudflare Worker API or public hosted API.
- External pip-installed source plugins.
- Full product catalog crawling unrelated to manual/schedule scope.
- Manual review UI for Bandai Chinese candidate matches.
- Automatic confirmed Bandai Chinese mapping without official or curated
  evidence.
- Image perceptual hashing unless needed later as an opt-in enhancement.

## Research References

- `../archive/2026-06/06-06-bandai-source-collection/research/bandai-manual-schedule-collection.md`
  - Bandai manual, schedule, taxonomy, multilingual matching, and incremental
    collection research.
- `../archive/2026-06/06-06-bandai-source-collection/research/kotobukiya-manual-product-collection.md`
  - Kotobukiya instruction/product metadata and confirmed relationship research.
- `../archive/2026-06/06-06-bandai-source-collection/info.md`
  - Cross-source schema design for manuals, products, relationships, releases,
    prices, and taxonomy.
- `../../../plamoindex-development-plan.md`
  - Original v0.1 project plan, CLI expectations, output contract, and
    publishing strategy.

## Definition of Done

- PRD is accepted by the user.
- Task context is configured for implementation/check phases.
- Current implementation is audited and aligned with this PRD.
- Source collectors, incremental collection, curated mappings, merge rules,
  outputs, validation, README, and CI are implemented.
- Default quality gate passes:
  - `ruff check .`
  - `mypy src`
  - `pytest`
- `plamoindex sync --source all --curated curated/ --dist dist` and
  `plamoindex validate --dist dist` work from a clean checkout with fixture or
  cached data as appropriate.
