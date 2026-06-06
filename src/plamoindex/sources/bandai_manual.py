"""Bandai manual collector: parsing logic for manual.bandai-hobby.net.

Handles:
- Manual list page parsing (Japanese title, English title, release date, manual id).
- Manual detail page parsing (PDF URL, product image, release details, brand line).
- Pagination via page controls.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup, Tag

from plamoindex.collector import BaseCollector, CollectionResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://manual.bandai-hobby.net"
_LIST_URL = f"{_BASE_URL}/menus"
_DETAIL_URL = f"{_BASE_URL}/menus/detail/{{manual_id}}"
_PDF_URL_TPL = f"{_BASE_URL}/pdf/{{manual_id}}.pdf"


class BandaiManualCollector(BaseCollector):
    """Collector for Bandai manual pages from manual.bandai-hobby.net."""

    @property
    def source_id(self) -> str:
        return "bandai"

    def collect_all(self) -> CollectionResult:
        """Full collection pass: list pages + detail pages."""
        manuals: list[dict[str, Any]] = []

        # Step 1: Discover manual entries from list pages
        list_entries = self._collect_list_pages()
        logger.info("Found %d manual entries on list pages", len(list_entries))

        # Step 2: Fetch detail pages for each entry
        for entry in list_entries:
            manual_id = entry["manual_id"]
            try:
                detail = self._fetch_detail(manual_id)
                if detail is not None:
                    entry.update(detail)
                manuals.append(entry)
            except Exception as exc:
                logger.warning("Failed to fetch detail for manual %s: %s", manual_id, exc)
                manuals.append(entry)

        # Save to cache
        self.cache.save_records(manuals, "manuals.json")

        return CollectionResult(
            manuals=manuals,
        )

    def _collect_list_pages(self) -> list[dict[str, Any]]:
        """Collect manual entries from list pages using pagination.

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but list data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        entries: list[dict[str, Any]] = []
        page = 1

        while True:
            url = f"{_LIST_URL}?page={page}"
            page_id = f"list-page-{page}"

            try:
                result = self.fetch.fetch(url)
                self.cache.put_page(page_id, result.content_hash)

                page_entries = _parse_list_page(result.text, url)
                if not page_entries:
                    break  # No more entries

                entries.extend(page_entries)
                page += 1
            except Exception as exc:
                logger.warning("Failed to fetch list page %d: %s", page, exc)
                break

        return entries

    def _fetch_detail(self, manual_id: str) -> dict[str, Any] | None:
        """Fetch and parse a manual detail page.

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but detail data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        url = _DETAIL_URL.format(manual_id=manual_id)
        page_id = f"detail-{manual_id}"

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            return _parse_detail_page(result.text, url, manual_id)
        except Exception as exc:
            logger.warning("Failed to fetch detail %s: %s", manual_id, exc)
            return None


def _parse_list_page(html: str, source_url: str) -> list[dict[str, Any]]:
    """Parse a Bandai manual list page.

    Expected structure (from research):
    - Each manual item has: `title_ja`, `title_en`, `release_date_raw`, `manual_id`.
    - English title is visible on the list page.

    Args:
        html: Raw HTML of the list page.
        source_url: URL of the list page (for reference).

    Returns:
        List of manual entry dicts with parsed fields.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[dict[str, Any]] = []

    manual_items = soup.select(".menu-item, .manual-item, [class*='menu-item'], [class*='manual-item'], tr")
    if not manual_items:
        manual_items = soup.select("a[href*='/menus/detail/']")

    seen_ids: set[str] = set()

    for item in manual_items:
        entry = _parse_single_list_item(item)
        if entry and entry["manual_id"] not in seen_ids:
            seen_ids.add(entry["manual_id"])
            entries.append(entry)

    return entries


def _parse_single_list_item(item: Tag) -> dict[str, Any] | None:
    """Parse a single manual item from the list page."""
    detail_link = item.find("a", href=re.compile(r"/menus/detail/\d+"))
    if not detail_link:
        detail_link = item.find("a", href=re.compile(r"detail"))
    if not detail_link:
        return None

    href = detail_link.get("href", "")
    manual_id_match = re.search(r"/menus/detail/(\d+)", href)
    if not manual_id_match:
        return None
    manual_id = manual_id_match.group(1)

    title_text = detail_link.get_text(strip=True) or ""

    # Try to extract Japanese and English titles
    title_ja = title_text
    title_en = None

    # Find image for thumbnail
    img = item.find("img")
    image_url = img.get("src") if img and img.get("src") else None
    if image_url and not image_url.startswith("http"):
        image_url = f"{_BASE_URL}{image_url}" if image_url.startswith("/") else image_url

    # Find release date text
    release_text = None
    date_elem = item.find(["span", "p", "div"], class_=re.compile(r"date|release", re.I))
    if date_elem:
        release_text = date_elem.get_text(strip=True)

    # Check for English title (often in a separate element)
    en_title_elem = item.find(["span", "p", "div"], class_=re.compile(r"en|english|title-en", re.I))
    if en_title_elem:
        title_en = en_title_elem.get_text(strip=True)

    entry: dict[str, Any] = {
        "manual_id": manual_id,
        "title_ja": title_ja,
        "title_en": title_en,
        "image_url": image_url,
        "release_date_raw": release_text,
        "source_url": f"{_BASE_URL}/menus/detail/{manual_id}",
        "pdf_url": _PDF_URL_TPL.format(manual_id=manual_id),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    return entry


def _parse_detail_page(html: str, url: str, manual_id: str) -> dict[str, Any]:
    """Parse a Bandai manual detail page.

    Expected structure (from research):
    - Product image.
    - `品番` raw value.
    - Release date.
    - Brand/product line text (e.g., HG).
    - Work/series text.
    - Viewer data with PDF URL.

    Args:
        html: Raw HTML of the detail page.
        url: Source URL.
        manual_id: Manual ID.

    Returns:
        Dict with parsed detail fields.
    """
    soup = BeautifulSoup(html, "lxml")
    detail: dict[str, Any] = {}

    # Product image
    img = soup.select_one(".product-image img, [class*='product-image'] img, .main-image img")
    if not img:
        img = soup.find("img", class_=re.compile(r"product|main|detail", re.I))
    if img and img.get("src"):
        src = img["src"]
        if isinstance(src, str):
            detail["image_url"] = src if src.startswith("http") else f"{_BASE_URL}{src}"

    # Parse product number (品番)
    product_no = _find_text_after_label(soup, ["品番", "product no", "item no"])
    if product_no:
        detail["product_code"] = product_no

    # Release date
    release_text = _find_text_after_label(soup, ["発売日", "release date", "release"])
    if release_text:
        detail["release_date_raw"] = release_text
        parsed = _parse_release_date(release_text)
        if parsed:
            detail.update(parsed)

    # Brand / product line
    line_text = _find_text_after_label(soup, ["ブランド", "brand", "grade", "line"])
    if line_text:
        detail["product_line"] = line_text

    # Work / series
    series_text = _find_text_after_label(soup, ["作品", "series", "work"])
    if series_text:
        detail["series_text"] = series_text

    # PDF URL from viewer data
    viewer_script = soup.find("script", string=re.compile(r"pdf|viewer", re.I))
    if viewer_script:
        script_text = str(viewer_script.string) if viewer_script.string else ""
        pdf_match = re.search(r'/pdf/\d+\.pdf', script_text)
        if pdf_match:
            detail["pdf_url"] = f"{_BASE_URL}{pdf_match.group(0)}"

    return detail


def _find_text_after_label(soup: BeautifulSoup, labels: list[str]) -> str | None:
    """Find text content following a label element.

    Looks for elements containing the label text, then returns the next
    sibling or parent sibling's text content.
    """
    for label in labels:
        label_elem = soup.find(["th", "dt", "span", "p", "div"], string=re.compile(re.escape(label), re.I))
        if label_elem:
            next_elem = label_elem.find_next(["td", "dd", "span", "p", "div"])
            if next_elem:
                return next_elem.get_text(strip=True)
            # Try parent's next sibling
            parent = label_elem.parent
            if parent:
                next_sibling = parent.find_next_sibling(["td", "dd", "div"])
                if next_sibling:
                    return next_sibling.get_text(strip=True)
    return None


def _parse_release_date(text: str) -> dict[str, str | None] | None:
    """Parse a Japanese release date text into structured fields.

    Examples:
    - 2026年5月30日発売 -> release_date=2026-05-30, precision=day
    - 2026年06月 -> release_month=2026-06, precision=month
    - 2026年 -> release_month=None, precision=year

    Args:
        text: Raw release date text.

    Returns:
        Dict with release_date, release_month, release_date_precision, or None.
    """
    if not text:
        return None

    result: dict[str, str | None] = {
        "release_date": None,
        "release_month": None,
        "release_date_precision": None,
    }

    # Try full date: 2026年5月30日
    full_match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if full_match:
        year, month, day = full_match.group(1), full_match.group(2).zfill(2), full_match.group(3).zfill(2)
        result["release_date"] = f"{year}-{month}-{day}"
        result["release_month"] = f"{year}-{month}"
        result["release_date_precision"] = "day"
        return result

    # Try month only: 2026年06月
    month_match = re.search(r"(\d{4})年\s*(\d{1,2})月", text)
    if month_match:
        year, month = month_match.group(1), month_match.group(2).zfill(2)
        result["release_month"] = f"{year}-{month}"
        result["release_date_precision"] = "month"
        return result

    # Try year only
    year_match = re.search(r"(\d{4})年", text)
    if year_match:
        result["release_date_precision"] = "year"
        return result

    # Try YYYY-MM-DD format
    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match:
        result["release_date"] = iso_match.group(0)
        result["release_month"] = f"{iso_match.group(1)}-{iso_match.group(2)}"
        result["release_date_precision"] = "day"
        return result

    return None
