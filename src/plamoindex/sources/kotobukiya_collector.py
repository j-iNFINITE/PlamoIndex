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

from bs4 import BeautifulSoup, Tag

from plamoindex.collector import BaseCollector, CollectionResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.kotobukiya.co.jp"
_LIST_URL = f"{_BASE_URL}/en/instructions/"
_DETAIL_URL = f"{_BASE_URL}/en/instructions/detail/{{instruction_id}}/"
_PRODUCT_URL = f"{_BASE_URL}/en/product/detail/{{product_id}}/"


class KotobukiyaCollector(BaseCollector):
    """Collector for Kotobukiya instruction and product data."""

    @property
    def source_id(self) -> str:
        return "kotobukiya"

    def collect_all(self) -> CollectionResult:
        """Full collection pass: instruction list -> detail -> product detail."""
        manuals: list[dict[str, Any]] = []
        product_sources: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

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
                        product_detail = self._fetch_product_detail(product_id)
                        if product_detail:
                            product_source = self._build_product_source(
                                product_id, product_detail,
                            )
                            if product_source:
                                product_sources.append(product_source)

                            # Create confirmed relationship
                            relationships.append({
                                "from_key": f"kotobukiya:{instruction_id}",
                                "to_key": f"kotobukiya-product:{product_id}",
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

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but detail data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        url = _DETAIL_URL.format(instruction_id=instruction_id)
        page_id = f"instruction-detail-{instruction_id}"

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            return _parse_instruction_detail(result.text, url, instruction_id)
        except Exception as exc:
            logger.warning(
                "Failed to fetch instruction detail %s: %s", instruction_id, exc,
            )
            return None

    def _fetch_product_detail(self, product_id: str) -> dict[str, Any] | None:
        """Fetch and parse a product detail page.

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but detail data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        url = _PRODUCT_URL.format(product_id=product_id)
        page_id = f"product-detail-{product_id}"

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            return _parse_product_detail(result.text, url, product_id)
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
    link = item.find("a", href=re.compile(r"/en/instructions/detail/\d+"))
    if not link:
        if isinstance(item, Tag) and item.name == "a" and "detail" in item.get("href", ""):
            link = item
        else:
            return None

    href = link.get("href", "")
    id_match = re.search(r"/detail/(\d+)", href)
    if not id_match:
        return None
    instruction_id = id_match.group(1)

    title = link.get_text(strip=True) or ""

    # Image
    img = item.find("img")
    image_url = img.get("src") if img and img.get("src") else None
    if image_url and isinstance(image_url, str):
        if image_url.startswith("/"):
            image_url = f"{_BASE_URL}{image_url}"

    # Product code
    code_elem = item.find(["span", "p", "div"], string=re.compile(r"PV\d+|[A-Z]{2,}\d+"))
    product_code = code_elem.get_text(strip=True) if code_elem else None

    # Language
    lang_text = item.get_text()
    languages = []
    if "JPN" in lang_text or "日本語" in lang_text:
        languages.append("ja")
    if "ENG" in lang_text or "English" in lang_text or "英語" in lang_text:
        languages.append("en")

    entry: dict[str, Any] = {
        "instruction_id": instruction_id,
        "title": title,
        "image_url": image_url,
        "manufacturer_item_code": product_code,
        "languages": languages if languages else None,
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
        href = pdf_link.get("href", "")
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
        src = img.get("src", "")
        if isinstance(src, str) and src:
            full_url = f"{_BASE_URL}{src}" if src.startswith("/") else src
            preview_images.append(full_url)

    if preview_images:
        detail["manual_preview_images"] = preview_images

    # Product detail link
    product_link = soup.find("a", href=re.compile(r"/en/product/detail/"))
    if product_link:
        href = product_link.get("href", "")
        if href:
            detail["product_link"] = f"{_BASE_URL}{href}" if href.startswith("/") else href

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
            href = link.get("href", "")
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

    # Release month - look for patterns like "2024.12"
    page_text = soup.get_text()
    release_match = re.search(r"(\d{4})\.(\d{1,2})", page_text)
    if release_match:
        release_month = f"{release_match.group(1)}-{release_match.group(2).zfill(2)}"
        detail["release"] = {
            "source": "kotobukiya_product",
            "locale": "en",
            "market": "jp-shop",
            "release_month": release_month,
            "release_date_precision": "month",
            "raw": f"{release_match.group(1)}.{release_match.group(2)}",
        }

    # Prices - look for "JPY X,XXX incl. tax" and "JPY X,XXX excl. tax"
    prices: list[dict[str, Any]] = []
    price_texts = []

    price_blocks = soup.find_all(string=re.compile(r"JPY|¥|Yen|円"))
    for price_block in price_blocks:
        text = price_block.strip()
        if text and len(text) > 5:
            price_texts.append(text)

    # Also look in table rows
    price_rows = soup.find_all(["tr", "div", "p"], string=re.compile(r"Price|価格", re.I))
    for row in price_rows:
        row_text = row.get_text(strip=True)
        if row_text and row_text not in price_texts:
            price_texts.append(row_text)

    for text in price_texts:
        price_info = _parse_kotobukiya_price(text)
        if price_info:
            prices.append(price_info)

    if prices:
        detail["prices"] = prices

    # Series and Product Series
    series_labels = soup.find_all(string=re.compile(r"MEGAMI DEVICE|series|title", re.I))
    for s in series_labels:
        parent_text = s.strip()
        if "MEGAMI DEVICE" in parent_text or "MEGAMI" in parent_text:
            detail["series"] = {"label": "MEGAMI DEVICE", "kind": "series"}

    product_series_labels = soup.find_all(string=re.compile(r"Unpainted|Product Series|シリーズ", re.I))
    for s in product_series_labels:
        label = s.strip()
        if label and not detail.get("product_series"):
            detail["product_series"] = {"label": label, "kind": "product_series"}

    # Specs
    specs: dict[str, Any] = {}

    # Scale
    scale_match = re.search(r"(\d+/\d+)", page_text)
    if scale_match:
        specs["scale"] = scale_match.group(1)

    # Size
    size_match = re.search(r"(\d+mm\s*(tall|long|wide|height))", page_text, re.I)
    if size_match:
        specs["size"] = size_match.group(1)

    # Specifications
    spec_keywords = ["Unpainted", "Kit", "Painted", "PVC", "ABS", "Iron", "Acrylic", "Polyester"]
    spec_items = [kw for kw in spec_keywords if kw.lower() in page_text.lower()]
    if spec_items:
        specs["specifications"] = spec_items

    # Material
    material_match = re.search(r"PVC[^。.]+", page_text)
    if material_match:
        specs["material"] = material_match.group(0).strip()

    # Age rating
    age_match = re.search(r"Ages?\s*\d+\s*(?:and|&)\s*up", page_text, re.I)
    if age_match:
        specs["age_rating"] = age_match.group(0)

    # Sculptors
    sculptor_match = re.search(r"Sculptor[s]?[：:]\s*([^。.]+)", page_text)
    if sculptor_match:
        sculptors_raw = sculptor_match.group(1)
        specs["sculptors"] = [s.strip() for s in sculptors_raw.split("・") if s.strip()]

    if specs:
        detail["specs"] = specs

    # Product code
    code_match = re.search(r"(PV\d+)", page_text)
    if code_match:
        detail["manufacturer_item_code"] = code_match.group(1)

    # Description
    desc_elem = soup.find(["p", "div"], class_=re.compile(r"description|desc|overview", re.I))
    if desc_elem:
        detail["description"] = desc_elem.get_text(strip=True)

    return detail


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
