"""Kotobukiya instruction and product collector.

Handles:
- Instruction list page parsing (id, title, product code, language, image).
- Instruction detail page parsing (PDF URLs, preview images, product link).
- Product detail page parsing (category, series, release, price, specs).
- Confirmed manual-product relationships via official product detail links.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from plamoindex.collector import BaseCollector, CollectionResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.kotobukiya.co.jp"
_LIST_URL = f"{_BASE_URL}/en/instructions/"
_DETAIL_URL = f"{_BASE_URL}/en/instructions/detail/{{instruction_id}}/"
_PRODUCT_URL = f"{_BASE_URL}/en/product/detail/{{product_id}}/"


def _get_attr_str(tag: Tag, name: str) -> str:
    """Return a tag attribute only when it is a string."""
    value = tag.get(name)
    return value if isinstance(value, str) else ""


def _clean_text(text: str) -> str:
    """Collapse source HTML whitespace into readable text."""
    return " ".join(text.split())


def _find_text_tag(tag: Tag, tags: list[str], pattern: re.Pattern[str]) -> Tag | None:
    """Find the first descendant tag whose text matches a pattern."""
    for candidate in tag.find_all(name=tags):
        if pattern.search(candidate.get_text(strip=True)):
            return candidate
    return None


def _find_text_tags(tag: Tag, tags: list[str], pattern: re.Pattern[str]) -> list[Tag]:
    """Find descendant tags whose text matches a pattern."""
    return [
        candidate
        for candidate in tag.find_all(name=tags)
        if pattern.search(candidate.get_text(strip=True))
    ]


class KotobukiyaCollector(BaseCollector):
    """Collector for Kotobukiya instruction and product data."""

    @property
    def source_id(self) -> str:
        return "kotobukiya"

    def collect_all(self) -> CollectionResult:
        """Full collection pass: instruction list -> detail -> product detail."""
        manuals: list[dict[str, Any]] = []
        product_sources_by_key: dict[str, dict[str, Any]] = {}
        relationships: list[dict[str, Any]] = []
        relationship_keys: set[tuple[str, str, str]] = set()

        # Step 1: Discover instruction entries from list pages
        list_entries = self._collect_list_pages()
        logger.info("Found %d instruction entries on list pages", len(list_entries))

        # Step 2: Fetch detail pages for each instruction
        for entry in list_entries:
            instruction_id = entry["instruction_id"]
            try:
                detail = self._fetch_detail(instruction_id)
                if detail is not None:
                    entry.update(detail)

                # Step 3: Follow product link if present
                product_link = entry.get("product_link")
                if product_link:
                    product_id_match = re.search(r"/product/detail/([\w]+)", product_link)
                    if product_id_match:
                        product_id = product_id_match.group(1)
                        product_source_key = f"kotobukiya-product:en:{product_id}"
                        product_key = f"kotobukiya-product:{product_id}"

                        if product_source_key not in product_sources_by_key:
                            product_detail = self._fetch_product_detail(product_id)
                            product_source = (
                                self._build_product_source(product_id, product_detail)
                                if product_detail
                                else None
                            )
                            if product_source:
                                actual_key = str(
                                    product_source.get("product_source_key") or product_source_key
                                )
                                product_sources_by_key[actual_key] = product_source
                            else:
                                logger.warning(
                                    "Skipping relationship for instruction %s because "
                                    "product source %s could not be built",
                                    instruction_id,
                                    product_source_key,
                                )

                        # Create confirmed relationship only when the target
                        # product source exists and can be merged into a product.
                        if product_source_key in product_sources_by_key:
                            relationship_identity = (
                                f"kotobukiya:{instruction_id}",
                                product_key,
                                "manual_for_product",
                            )
                            if relationship_identity not in relationship_keys:
                                relationship_keys.add(relationship_identity)
                                relationships.append({
                                    "from_key": relationship_identity[0],
                                    "to_key": relationship_identity[1],
                                    "relationship": "manual_for_product",
                                    "status": "confirmed",
                                    "method": "official_instruction_detail_product_link",
                                    "confidence": 1.0,
                                    "provenance": {
                                        "collector": "kotobukiya",
                                        "collection_method": "scrape",
                                        "collected_at": datetime.now(timezone.utc).isoformat(),
                                    },
                                })

                manuals.append(entry)
            except Exception as exc:
                logger.warning(
                    "Failed to process instruction %s: %s", instruction_id, exc,
                )
                manuals.append(entry)

        # Save to cache
        product_sources = list(product_sources_by_key.values())
        self.cache.save_records(manuals, "manuals.json")
        self.cache.save_records(product_sources, "product_sources.json")
        self.cache.save_records(relationships, "relationships.json")

        return CollectionResult(
            manuals=manuals,
            product_sources=product_sources,
            relationships=relationships,
        )

    def _collect_list_pages(self) -> list[dict[str, Any]]:
        """Collect instruction entries from all list pages.

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but list data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        entries: list[dict[str, Any]] = []
        page = 1

        while True:
            url = f"{_LIST_URL}?page={page}" if page > 1 else _LIST_URL
            page_id = f"instruction-list-{page}"

            try:
                result = self.fetch.fetch(url)
                self.cache.put_page(page_id, result.content_hash)

                page_entries = _parse_instruction_list(result.text, url)
                if not page_entries:
                    break

                entries.extend(page_entries)
                page += 1
            except Exception as exc:
                logger.warning("Failed to fetch list page %d: %s", page, exc)
                break

        return entries

    def _fetch_detail(self, instruction_id: str) -> dict[str, Any] | None:
        """Fetch and parse an instruction detail page.

        Reuses the parsed detail cache when available. List pages are still
        fetched to discover current instruction IDs, but historical detail
        pages do not need to be re-fetched on every workflow run.
        """
        url = _DETAIL_URL.format(instruction_id=instruction_id)
        page_id = f"instruction-detail-{instruction_id}"
        detail_filename = f"{page_id}.json"
        cached_detail = self.cache.load_record(detail_filename)
        if cached_detail is not None:
            return cached_detail

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            detail = _parse_instruction_detail(result.text, url, instruction_id)
            self.cache.save_record(detail, detail_filename)
            return detail
        except Exception as exc:
            logger.warning(
                "Failed to fetch instruction detail %s: %s", instruction_id, exc,
            )
            return None

    def _fetch_product_detail(self, product_id: str) -> dict[str, Any] | None:
        """Fetch and parse a product detail page.

        Reuses the parsed detail cache when available. Product metadata is
        stable enough that historical workflow chunks should not fetch the same
        product detail page repeatedly.
        """
        url = _PRODUCT_URL.format(product_id=product_id)
        page_id = f"product-detail-{product_id}"
        detail_filename = f"{page_id}.json"
        cached_detail = self.cache.load_record(detail_filename)
        if cached_detail is not None:
            return cached_detail

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            detail = _parse_product_detail(result.text, url, product_id)
            self.cache.save_record(detail, detail_filename)
            return detail
        except Exception as exc:
            logger.warning(
                "Failed to fetch product detail %s: %s", product_id, exc,
            )
            return None

    def _build_product_source(
        self,
        product_id: str,
        detail: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build a product source record dict from parsed detail data."""
        if not detail:
            return None

        source: dict[str, Any] = {
            "product_source_id": product_id,
            "product_source_key": f"kotobukiya-product:en:{product_id}",
            "source": "kotobukiya_product",
            "manufacturer": "KOTOBUKIYA",
            "locale": "en",
            "market": "jp-shop",
            "product_id": product_id,
            "product_url": _PRODUCT_URL.format(product_id=product_id),
            "title": detail.get("title", ""),
            "provenance": {
                "collector": "kotobukiya",
                "collection_method": "scrape",
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # Copy detail fields
        for key in (
            "manufacturer_item_code",
            "category", "series", "product_series",
            "release", "prices",
            "description", "specs",
            "scale", "size", "material", "age_rating", "sculptors",
        ):
            if key in detail:
                source[key] = detail[key]

        return source


# ---- Instruction List Parsing ----

def _parse_instruction_list(html: str, source_url: str) -> list[dict[str, Any]]:
    """Parse the Kotobukiya instruction list page.

    Expected structure (from research):
    - Items with: instruction_id, product/title, product code, language label, thumbnail.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[dict[str, Any]] = []

    items = soup.select(".manualList_item")
    if not items:
        items = soup.select(".manualList_card")
    if not items:
        items = soup.select(".instruction-item, [class*='instruction'], .list-item, tr, article")
    if not items:
        items = soup.find_all("a", href=re.compile(r"/en/instructions/detail/\d+"))

    seen_ids: set[str] = set()

    for item in items:
        entry = _parse_single_instruction_item(item)
        if entry and entry["instruction_id"] not in seen_ids:
            seen_ids.add(entry["instruction_id"])
            entries.append(entry)

    return entries


def _parse_single_instruction_item(item: Tag) -> dict[str, Any] | None:
    """Parse a single instruction list item."""
    link = item.select_one(".manualList_manual a[href*='/en/instructions/detail/']")
    if not link:
        link = item.find(name="a", href=re.compile(r"/en/instructions/detail/\d+"))
    if not link:
        if isinstance(item, Tag) and item.name == "a" and "detail" in _get_attr_str(item, "href"):
            link = item
        else:
            return None

    href = _get_attr_str(link, "href")
    id_match = re.search(r"/detail/(\d+)", href)
    if not id_match:
        return None
    instruction_id = id_match.group(1)

    title_elem = item.select_one(".manualList_title")
    title = (
        _clean_text(title_elem.get_text(" ", strip=True))
        if title_elem
        else _clean_text(link.get_text(" ", strip=True))
    )

    # Image
    img = item.find("img")
    image_url = _get_attr_str(img, "src") if img else None
    if image_url:
        image_url = urljoin(_BASE_URL, image_url)

    # Product code
    code_elem = item.select_one(".manualList_proNumber dd")
    if not code_elem:
        code_elem = _find_text_tag(item, ["span", "p", "div", "dd"], re.compile(r"Product Code|PV\d+|[A-Z]{2,}\d+"))
    code_text = _clean_text(code_elem.get_text(" ", strip=True)) if code_elem else ""
    code_match = re.search(r"(PV\d+|[A-Z]{2,}\d+)", code_text)
    product_code = code_match.group(1) if code_match else None

    # Language
    lang_text = link.get_text(" ", strip=True)
    languages = []
    if "JPN" in lang_text or "日本語" in lang_text:
        languages.append("ja")
    if "ENG" in lang_text or "English" in lang_text or "英語" in lang_text:
        languages.append("en")

    product_link = None
    product_link_tag = item.select_one(".manualList_more a[href*='/en/product/detail/']")
    if product_link_tag:
        href = _get_attr_str(product_link_tag, "href")
        product_link = urljoin(_BASE_URL, href) if href else None

    entry: dict[str, Any] = {
        "instruction_id": instruction_id,
        "title": title,
        "image_url": image_url,
        "manufacturer_item_code": product_code,
        "languages": languages if languages else None,
        "product_link": product_link,
        "source_url": _DETAIL_URL.format(instruction_id=instruction_id),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    return entry


# ---- Instruction Detail Parsing ----

def _parse_instruction_detail(html: str, url: str, instruction_id: str) -> dict[str, Any]:
    """Parse an instruction detail page.

    Expected structure (from research):
    - Title: 'Instruction Manuals｜...'
    - Product code: PV256
    - PDF download links: /en/instructions/dl-ja/..., /en/instructions/dl-en/...
    - Preview images: /files/inst/...
    - Product detail link: /en/product/detail/...
    """
    soup = BeautifulSoup(html, "lxml")
    detail: dict[str, Any] = {}

    # Title
    title_elem = soup.find("h1") or soup.find("title")
    if title_elem:
        title_text = title_elem.get_text(strip=True)
        # Clean up "Instruction Manuals｜" prefix
        title_text = re.sub(r"^Instruction\s*Manuals?[｜|]\s*", "", title_text)
        detail["title"] = title_text

    # Product code
    code_elem = soup.find(string=re.compile(r"PV\d+|[A-Z]{2,}\d+"))
    if code_elem:
        code_match = re.search(r"(PV\d+|[A-Z]{2,}\d+)", code_elem)
        if code_match:
            detail["manufacturer_item_code"] = code_match.group(1)

    # PDF URLs
    pdf_urls: dict[str, str] = {}
    pdf_links = soup.find_all("a", href=re.compile(r"/en/instructions/dl-"))
    for pdf_link in pdf_links:
        href = _get_attr_str(pdf_link, "href")
        if not href:
            continue
        full_url = f"{_BASE_URL}{href}" if href.startswith("/") else href
        if "dl-ja" in href:
            pdf_urls["ja"] = full_url
            if "pdf_url" not in detail:
                detail["pdf_url"] = full_url  # Prefer Japanese
        elif "dl-en" in href:
            pdf_urls["en"] = full_url
            if "pdf_url" not in detail:
                detail["pdf_url"] = full_url  # Fallback to English

    if pdf_urls:
        detail["pdf_urls"] = pdf_urls

    # Preview images
    preview_images: list[str] = []
    img_links = soup.find_all("img", src=re.compile(r"/files/inst/"))
    if not img_links:
        img_links = soup.find_all("img", src=re.compile(r"inst"))
    for img in img_links:
        src = _get_attr_str(img, "src")
        if isinstance(src, str) and src:
            full_url = f"{_BASE_URL}{src}" if src.startswith("/") else src
            preview_images.append(full_url)

    if preview_images:
        detail["manual_preview_images"] = preview_images

    # Product detail link
    product_link = None
    for link in soup.find_all(name="a", href=re.compile(r"/en/product/detail/")):
        link_text = _clean_text(link.get_text(" ", strip=True))
        if re.search(r"view\s+product\s+details?", link_text, re.I):
            product_link = link
            break
    if product_link is None:
        product_link = soup.find(name="a", href=re.compile(r"/en/product/detail/"))
    if product_link:
        href = _get_attr_str(product_link, "href")
        if href:
            detail["product_link"] = urljoin(_BASE_URL, href)

    return detail


# ---- Product Detail Parsing ----

def _parse_product_detail(html: str, url: str, product_id: str) -> dict[str, Any]:
    """Parse a Kotobukiya product detail page.

    Expected structure (from research):
    - Title.
    - Category badge/breadcrumb.
    - Release month.
    - Price (incl. and excl. tax).
    - Series/title, Product series.
    - Scale, size, specifications, material, age rating, sculptor(s), product code.
    - Description.
    - Product images.
    """
    soup = BeautifulSoup(html, "lxml")
    detail: dict[str, Any] = {}
    detail["product_source_id"] = product_id

    # Title
    title_elem = soup.find("h1") or soup.find(["h2", "h3"], class_=re.compile(r"title|product", re.I))
    if title_elem:
        detail["title"] = title_elem.get_text(strip=True)

    # Category / breadcrumb
    breadcrumb = soup.select_one(".breadcrumb, [class*='breadcrumb'], .p-breadcrumb, nav")
    if breadcrumb:
        links = breadcrumb.find_all("a")
        for link in links:
            label = link.get_text(strip=True)
            href = _get_attr_str(link, "href")
            if label and label not in ("Home", "TOP"):
                if not detail.get("category") and "product" in href:
                    detail["category"] = {
                        "label": label,
                        "url": href if href.startswith("http") else f"{_BASE_URL}{href}",
                    }

    # Badge / category
    badge = soup.select_one(".badge, [class*='badge'], .category-badge")
    if badge and "category" not in detail:
        detail["category"] = {
            "label": badge.get_text(strip=True),
            "kind": "category",
        }

    # Release month - the product page keeps this in the detail header.
    release_text = ""
    release_elem = soup.select_one(".detailHeader_set-release dd")
    if release_elem:
        release_text = _clean_text(release_elem.get_text(" ", strip=True))
    release_match = re.search(r"(\d{4})\.(\d{1,2})", release_text)
    if release_match:
        release_month = f"{release_match.group(1)}-{release_match.group(2).zfill(2)}"
        detail["release"] = {
            "source": "kotobukiya_product",
            "locale": "en",
            "market": "jp-shop",
            "release_month": release_month,
            "release_date_precision": "month",
            "raw": release_text,
        }

    # Prices - the detail header has separate tax-included and tax-excluded spans.
    prices: list[dict[str, Any]] = []
    price_texts = [
        _clean_text(price.get_text(" ", strip=True))
        for price in soup.select(".detailHeader_set-price .detailHeader_price")
    ]
    if not price_texts:
        price_rows = _find_text_tags(soup, ["tr"], re.compile(r"Price|価格", re.I))
        for row in price_rows:
            row_text = _clean_text(row.get_text(" ", strip=True))
            if row_text and row_text not in price_texts:
                price_texts.append(row_text)

    for text in price_texts:
        price_info = _parse_kotobukiya_price(text)
        if price_info:
            prices.append(price_info)

    if prices:
        detail["prices"] = prices

    # Specs and taxonomy live in the product spec table.
    spec_rows = _parse_spec_table(soup)
    specs: dict[str, Any] = {}

    series_row = spec_rows.get("series")
    if series_row:
        detail["series"] = _taxonomy_from_spec_row(series_row, "series")

    product_series_row = spec_rows.get("product series")
    if product_series_row:
        detail["product_series"] = _taxonomy_from_spec_row(product_series_row, "product_series")

    for key, spec_key in (
        ("scale", "scale"),
        ("size", "size"),
        ("product material", "material"),
        ("age rating", "age_rating"),
    ):
        spec_row = spec_rows.get(key)
        if spec_row and spec_row["text"]:
            specs[spec_key] = spec_row["text"]

    specifications_row = spec_rows.get("specifications")
    if specifications_row and specifications_row["items"]:
        specs["specifications"] = specifications_row["items"]
    elif specifications_row and specifications_row["text"]:
        specs["specifications"] = [specifications_row["text"]]

    sculptors_row = spec_rows.get("sculptor(s)") or spec_rows.get("sculptors")
    if sculptors_row and sculptors_row["text"]:
        specs["sculptors"] = [
            sculptor.strip()
            for sculptor in re.split(r"[,、・]", sculptors_row["text"])
            if sculptor.strip()
        ]

    code_row = spec_rows.get("product code")
    if code_row and code_row["text"]:
        detail["manufacturer_item_code"] = code_row["text"]

    if specs:
        detail["specs"] = specs

    # Description
    desc_elem = soup.find(["p", "div"], class_=re.compile(r"description|desc|overview", re.I))
    if desc_elem:
        detail["description"] = desc_elem.get_text(strip=True)

    return detail


def _parse_spec_table(soup: BeautifulSoup) -> dict[str, dict[str, Any]]:
    """Parse Kotobukiya product spec table rows by lower-case label."""
    rows: dict[str, dict[str, Any]] = {}
    for row in soup.select(".grid-specTable tr"):
        header = row.find("th")
        value = row.find("td")
        if not header or not value:
            continue
        label = _clean_text(header.get_text(" ", strip=True)).lower()
        items = [
            _clean_text(item.get_text(" ", strip=True))
            for item in value.find_all("li")
            if _clean_text(item.get_text(" ", strip=True))
        ]
        first_link = value.find("a", href=True)
        href = _get_attr_str(first_link, "href") if first_link else None
        rows[label] = {
            "text": _clean_text(value.get_text(" ", strip=True)),
            "items": items,
            "url": urljoin(_BASE_URL, href) if href else None,
        }
    return rows


def _taxonomy_from_spec_row(row: dict[str, Any], kind: str) -> dict[str, Any]:
    """Build a taxonomy-like dict from a spec table row."""
    return {
        "label": row["text"],
        "kind": kind,
        "url": row.get("url"),
    }


def _parse_kotobukiya_price(text: str) -> dict[str, Any] | None:
    """Parse a Kotobukiya price string.

    Examples:
    - 'JPY 19,800 incl. tax' -> amount=19800, tax_included=True
    - 'JPY 18,000 excl. tax' -> amount=18000, tax_included=False
    """
    clean = text.replace(",", "").replace(" ", "")

    amount_match = re.search(r"(\d+\.?\d*)", clean)
    if not amount_match:
        return None

    amount = float(amount_match.group(1))
    tax_included = "incl" in text.lower() or "込" in text
    if "excl" in text.lower() or "抜" in text:
        tax_included = False

    # Filter out very low amounts that are likely not prices
    if amount < 100:
        return None

    return {
        "source": "kotobukiya_product",
        "locale": "en",
        "market": "jp-shop",
        "amount": amount,
        "currency": "JPY",
        "tax_included": tax_included,
        "raw": text.strip(),
    }
