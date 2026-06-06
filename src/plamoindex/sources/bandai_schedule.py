"""Bandai schedule/product collector for Japanese, English, and Chinese locales.

Handles:
- Japanese schedule parsing (bandai-hobby.net/schedule/).
- English schedule parsing (global.bandai-hobby.net/en-others/schedule/).
- Chinese schedule parsing (bandaihobbysite.cn/schedule).
- Product detail page parsing (taxonomy, prices, releases).
- ja/en merge by shared 01_xxxx product id.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup, Tag

from plamoindex.collector import BaseCollector, CollectionResult, CollectorCache
from plamoindex.fetch import FetchClient

logger = logging.getLogger(__name__)

# Japanese schedule
_JA_SCHEDULE_URL = "https://bandai-hobby.net/schedule/index.php?saledate={year_month}"
_JA_PRODUCT_URL = "https://bandai-hobby.net/item/{product_id}/"

# English schedule
_EN_SCHEDULE_URL = "https://global.bandai-hobby.net/en-others/schedule/index.php?saledate={year_month}"
_EN_PRODUCT_URL = "https://global.bandai-hobby.net/en-others/item/{product_id}/"

# Chinese schedule
_ZH_SCHEDULE_URL = "https://bandaihobbysite.cn/schedule"
_ZH_PRODUCT_URL = "https://bandaihobbysite.cn/index/index/detail/id/{cn_id}"

# Default month window for collection
_DEFAULT_PAST_MONTHS = 3
_DEFAULT_FUTURE_MONTHS = 6


class BandaiScheduleCollector(BaseCollector):
    """Collector for Bandai schedule/product pages across all locales."""

    @property
    def source_id(self) -> str:
        return "bandai"

    def __init__(
        self,
        fetch_client: FetchClient,
        cache: CollectorCache,
        *,
        past_months: int = _DEFAULT_PAST_MONTHS,
        future_months: int = _DEFAULT_FUTURE_MONTHS,
    ) -> None:
        super().__init__(fetch_client, cache)
        self.past_months = past_months
        self.future_months = future_months

    def collect_all(self) -> CollectionResult:
        """Full collection pass across all three locales."""
        result = CollectionResult()

        # Collect from all locales
        ja = self._collect_locale("ja", self._collect_ja_schedule)
        en = self._collect_locale("en", self._collect_en_schedule)
        zh = self._collect_locale("zh-Hans", self._collect_zh_schedule)

        result = result + ja + en + zh

        # Save to cache
        if result.product_sources:
            self.cache.save_records(result.product_sources, "product_sources.json")
        if result.manuals:
            self.cache.save_records(result.manuals, "manuals.json")
        if result.relationships:
            self.cache.save_records(result.relationships, "relationships.json")

        return result

    def _collect_locale(
        self,
        locale: str,
        collect_fn: Any,
    ) -> CollectionResult:
        """Collect for a single locale with error handling."""
        try:
            return collect_fn()
        except Exception as exc:
            logger.warning("Failed to collect Bandai %s schedule: %s", locale, exc)
            return CollectionResult()

    def _collect_ja_schedule(self) -> CollectionResult:
        """Collect Japanese schedule across month window."""
        product_sources: list[dict[str, Any]] = []
        months = self._get_month_window()

        for year_month in months:
            try:
                entries = self._fetch_ja_month(year_month)
                for entry in entries:
                    detail = self._fetch_product_detail(
                        entry["product_id"],
                        _JA_PRODUCT_URL,
                        "ja",
                    )
                    if detail:
                        entry.update(detail)
                    product_sources.append(entry)
            except Exception as exc:
                logger.warning(
                    "Failed to collect JA schedule for %s: %s", year_month, exc,
                )

        return CollectionResult(product_sources=product_sources)

    def _collect_en_schedule(self) -> CollectionResult:
        """Collect English schedule across month window."""
        product_sources: list[dict[str, Any]] = []
        months = self._get_month_window()

        for year_month in months:
            try:
                entries = self._fetch_en_month(year_month)
                for entry in entries:
                    detail = self._fetch_product_detail(
                        entry["product_id"],
                        _EN_PRODUCT_URL,
                        "en",
                    )
                    if detail:
                        entry.update(detail)
                    product_sources.append(entry)
            except Exception as exc:
                logger.warning(
                    "Failed to collect EN schedule for %s: %s", year_month, exc,
                )

        return CollectionResult(product_sources=product_sources)

    def _collect_zh_schedule(self) -> CollectionResult:
        """Collect Chinese schedule."""
        product_sources: list[dict[str, Any]] = []

        try:
            entries = self._fetch_zh_schedule()
            for entry in entries:
                cn_id = entry["cn_id"]
                detail = self._fetch_zh_product_detail(cn_id)
                if detail:
                    entry.update(detail)
                product_sources.append(entry)
        except Exception as exc:
            logger.warning("Failed to collect ZH schedule: %s", exc)

        return CollectionResult(product_sources=product_sources)

    def _fetch_ja_month(self, year_month: str) -> list[dict[str, Any]]:
        """Fetch and parse a Japanese schedule month page.

        Uses browser-like headers as required by the research.
        """
        url = _JA_SCHEDULE_URL.format(year_month=year_month)
        page_id = f"ja-schedule-{year_month}"

        result = self.fetch_with_cache(
            url,
            page_id,
            headers={
                "Accept-Language": "ja,en;q=0.9",
                "Referer": "https://bandai-hobby.net/",
            },
            force=True,  # Always fetch schedule pages
        )

        if result is None:
            return self.cache.load_records(f"ja-{year_month}.json")

        entries = _parse_ja_schedule_page(result.text, year_month)
        self.cache.save_records(entries, f"ja-{year_month}.json")
        return entries

    def _fetch_en_month(self, year_month: str) -> list[dict[str, Any]]:
        """Fetch and parse an English schedule month page."""
        url = _EN_SCHEDULE_URL.format(year_month=year_month)
        page_id = f"en-schedule-{year_month}"

        result = self.fetch_with_cache(
            url,
            page_id,
            force=True,
        )

        if result is None:
            return self.cache.load_records(f"en-{year_month}.json")

        entries = _parse_en_schedule_page(result.text, year_month)
        self.cache.save_records(entries, f"en-{year_month}.json")
        return entries

    def _fetch_zh_schedule(self) -> list[dict[str, Any]]:
        """Fetch and parse the Chinese schedule page."""
        url = _ZH_SCHEDULE_URL
        page_id = "zh-schedule"

        result = self.fetch_with_cache(
            url,
            page_id,
            headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            force=True,
        )

        if result is None:
            return self.cache.load_records("zh-schedule.json")

        entries = _parse_zh_schedule_page(result.text)
        self.cache.save_records(entries, "zh-schedule.json")
        return entries

    def _fetch_product_detail(
        self,
        product_id: str,
        url_tpl: str,
        locale: str,
    ) -> dict[str, Any] | None:
        """Fetch and parse a product detail page.

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but detail data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        url = url_tpl.format(product_id=product_id)
        page_id = f"product-detail-{locale}-{product_id}"

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            return _parse_product_detail(result.text, url, locale, product_id)
        except Exception as exc:
            logger.warning(
                "Failed to fetch product detail %s: %s", url, exc,
            )
            return None

    def _fetch_zh_product_detail(self, cn_id: str) -> dict[str, Any] | None:
        """Fetch and parse a Chinese product detail page.

        Always fetches and re-parses on each run (the HTTP request is always
        made regardless of cache state). Cache hash is updated for change
        detection, but detail data is always re-parsed to avoid data loss on
        incremental collection runs.
        """
        url = _ZH_PRODUCT_URL.format(cn_id=cn_id)
        page_id = f"zh-product-detail-{cn_id}"

        try:
            result = self.fetch.fetch(url)
            self.cache.put_page(page_id, result.content_hash)
            return _parse_zh_product_detail(result.text, url, cn_id)
        except Exception as exc:
            logger.warning(
                "Failed to fetch ZH product detail %s: %s", url, exc,
            )
            return None

    def _get_month_window(self) -> list[str]:
        """Generate a list of YYYYMM strings for the collection month window."""
        from datetime import date

        today = date.today()
        months: list[str] = []

        # Past months
        for i in range(self.past_months, 0, -1):
            y, m = _add_months(today.year, today.month, -i)
            months.append(f"{y}{m:02d}")

        # Current month
        months.append(f"{today.year}{today.month:02d}")

        # Future months
        for i in range(1, self.future_months + 1):
            y, m = _add_months(today.year, today.month, i)
            months.append(f"{y}{m:02d}")

        return months


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add or subtract months from a year/month pair."""
    total_months = (year * 12 + month - 1) + delta
    return (total_months // 12, total_months % 12 + 1)


# ---- Japanese Schedule Parsing ----

def _parse_ja_schedule_page(html: str, year_month: str) -> list[dict[str, Any]]:
    """Parse a Japanese schedule page.

    Expected structure (from research):
    - Schedule cards with: title_ja, product URL/id, image, price, release month.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[dict[str, Any]] = []

    items = soup.select(".card, .schedule-card, [class*='card'], .product-item")
    for item in items:
        entry = _parse_ja_card(item, year_month)
        if entry:
            entries.append(entry)

    return entries


def _parse_ja_card(item: Tag, year_month: str) -> dict[str, Any] | None:
    """Parse a single Japanese schedule card."""
    link = item.find("a", href=re.compile(r"/item/\d"))
    if not link:
        link = item.find("a", href=re.compile(r"item"))
    if not link:
        return None

    href = link.get("href", "")
    pid_match = re.search(r"/item/([\w_]+)", href)
    if not pid_match:
        return None
    product_id = pid_match.group(1)

    title_ja = link.get_text(strip=True) or ""

    # Price parsing
    price_text = None
    price_elem = item.find(["span", "p", "div"], class_=re.compile(r"price|value", re.I))
    if price_elem:
        price_text = price_elem.get_text(strip=True)

    # Image
    img = item.find("img")
    image_url = img.get("src") if img and img.get("src") else None
    if image_url and isinstance(image_url, str) and image_url.startswith("/"):
        image_url = f"https://bandai-hobby.net{image_url}"

    amount, tax_included = _parse_jp_price(price_text) if price_text else (None, True)

    entry: dict[str, Any] = {
        "product_source_id": product_id,
        "product_id": product_id,
        "locale": "ja",
        "title_ja": title_ja,
        "title": title_ja,
        "image_url": image_url,
        "product_url": _JA_PRODUCT_URL.format(product_id=product_id),
        "release_month": year_month[:4] + "-" + year_month[4:],
        "release_date_precision": "month",
        "price_amount": amount,
        "price_currency": "JPY",
        "price_tax_included": tax_included,
        "price_raw": price_text,
        "source": "bandai_schedule_ja",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    return entry


def _parse_jp_price(text: str) -> tuple[float | None, bool]:
    """Parse a Japanese price string like '2,530円(税10%込)' or '4,180円(税込)'."""
    tax_included = True
    clean = text.replace(",", "").replace(" ", "")

    if "税" in clean or "込" in clean:
        tax_included = True
    if "税別" in clean or "税抜" in clean:
        tax_included = False

    amount_match = re.search(r"(\d+\.?\d*)", clean)
    if not amount_match:
        return None, tax_included

    return float(amount_match.group(1)), tax_included


# ---- English Schedule Parsing ----

def _parse_en_schedule_page(html: str, year_month: str) -> list[dict[str, Any]]:
    """Parse an English schedule page.

    Expected structure (from research):
    - Schedule cards with: title_en, product URL/id, image, price, release month.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[dict[str, Any]] = []

    items = soup.select(".card, .schedule-card, [class*='card'], .product-item")
    for item in items:
        entry = _parse_en_card(item, year_month)
        if entry:
            entries.append(entry)

    return entries


def _parse_en_card(item: Tag, year_month: str) -> dict[str, Any] | None:
    """Parse a single English schedule card."""
    link = item.find("a", href=re.compile(r"/item/\d"))
    if not link:
        link = item.find("a", href=re.compile(r"item"))
    if not link:
        return None

    href = link.get("href", "")
    pid_match = re.search(r"/item/([\w_]+)", href)
    if not pid_match:
        return None
    product_id = pid_match.group(1)

    title_en = link.get_text(strip=True) or ""

    # Price
    price_text = None
    price_elem = item.find(["span", "p", "div"], class_=re.compile(r"price|value", re.I))
    if price_elem:
        price_text = price_elem.get_text(strip=True)

    # Image
    img = item.find("img")
    image_url = img.get("src") if img and img.get("src") else None
    if image_url and isinstance(image_url, str) and image_url.startswith("/"):
        image_url = f"https://global.bandai-hobby.net{image_url}"

    # Parse release month from card (may differ from request month)
    release_raw = item.get_text()
    release_month_parsed = _parse_en_release_month(release_raw) or (
        year_month[:4] + "-" + year_month[4:]
    )

    amount = None
    if price_text:
        clean = price_text.replace(",", "").replace(" ", "")
        amt_match = re.search(r"(\d+\.?\d*)", clean)
        if amt_match:
            amount = float(amt_match.group(1))

    entry: dict[str, Any] = {
        "product_source_id": product_id,
        "product_id": product_id,
        "locale": "en",
        "title_en": title_en,
        "title": title_en,
        "image_url": image_url,
        "product_url": _EN_PRODUCT_URL.format(product_id=product_id),
        "release_month": release_month_parsed,
        "release_date_precision": "month",
        "release_raw": None,
        "price_amount": amount,
        "price_currency": "JPY",
        "price_tax_included": False,
        "price_raw": price_text,
        "source": "bandai_schedule_en",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    return entry


def _parse_en_release_month(text: str) -> str | None:
    """Parse an English release month like 'Jun, 2026' into '2026-06'."""
    months_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[,.\s]+(\d{4})", text, re.I)
    if match:
        month_str = months_map.get(match.group(1).lower()[:3])
        if month_str:
            return f"{match.group(2)}-{month_str}"
    return None


# ---- Chinese Schedule Parsing ----

def _parse_zh_schedule_page(html: str) -> list[dict[str, Any]]:
    """Parse the Chinese schedule page.

    Expected structure (from research):
    - Cards with: title_zh, detail URL with cn_id, image, price, release month.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[dict[str, Any]] = []

    items = soup.select(".card, [class*='card'], .product-item, li")
    for item in items:
        entry = _parse_zh_card(item)
        if entry:
            entries.append(entry)

    return entries


def _parse_zh_card(item: Tag) -> dict[str, Any] | None:
    """Parse a single Chinese schedule card."""
    link = item.find("a", href=re.compile(r"/index/index/detail/id/\d+"))
    if not link:
        link = item.find("a", href=re.compile(r"detail"))
    if not link:
        return None

    href = link.get("href", "")
    cn_id_match = re.search(r"/id/(\d+)", href)
    if not cn_id_match:
        cn_id_match = re.search(r"id=(\d+)", href)
    if not cn_id_match:
        return None
    cn_id = cn_id_match.group(1)

    title_zh = link.get_text(strip=True) or link.get("title", "")

    # Image
    img = item.find("img")
    image_url = img.get("src") if img and img.get("src") else None
    if image_url and isinstance(image_url, str) and image_url.startswith("/"):
        image_url = f"https://bandaihobbysite.cn{image_url}"

    # Price parsing (Chinese prices are tax-included)
    price_text = None
    price_elem = item.find(["span", "p", "div"], class_=re.compile(r"price|value", re.I))
    if price_elem:
        price_text = price_elem.get_text(strip=True)

    amount = None
    if price_text:
        clean = price_text.replace(",", "").replace(" ", "")
        amt_match = re.search(r"(\d+\.?\d*)", clean)
        if amt_match:
            amount = float(amt_match.group(1))

    # Release month parsing
    release_raw = item.get_text()
    release_month = _parse_zh_release_month(release_raw)

    entry: dict[str, Any] = {
        "cn_id": cn_id,
        "product_source_id": cn_id,
        "locale": "zh-Hans",
        "title_zh": title_zh,
        "title": title_zh,
        "image_url": image_url,
        "product_url": _ZH_PRODUCT_URL.format(cn_id=cn_id),
        "release_month": release_month,
        "release_date_precision": "month" if release_month else "unknown",
        "price_amount": amount,
        "price_currency": "JPY",
        "price_tax_included": True,
        "price_raw": price_text,
        "source": "bandai_schedule_zh",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    return entry


def _parse_zh_release_month(text: str) -> str | None:
    """Parse a Chinese release month like '2026年06月发售' into '2026-06'."""
    match = re.search(r"(\d{4})年\s*(\d{1,2})月", text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}"
    return None


# ---- Product Detail Parsing (ja/en) ----

def _parse_product_detail(html: str, url: str, locale: str, product_id: str) -> dict[str, Any]:
    """Parse a Bandai product detail page for taxonomy, prices, and release.

    Expected structure (from research):
    - Product line via /brand/{slug}/
    - Series via /series/{slug}/
    - Breadcrumb: p-breadcrumb
    - Flat taxonomy cards: c-card__flat p-card__flat
    """
    soup = BeautifulSoup(html, "lxml")
    detail: dict[str, Any] = {}

    # Taxonomy from flat cards (priority 1)
    taxonomy = _parse_taxonomy_from_cards(soup)
    if taxonomy:
        detail["taxonomy"] = taxonomy

    # Taxonomy from breadcrumb (priority 2)
    if not taxonomy:
        breadcrumb_tax = _parse_taxonomy_from_breadcrumb(soup)
        if breadcrumb_tax:
            detail["taxonomy"] = breadcrumb_tax

    # Price from detail page
    price_elem = soup.find(["span", "p", "div"], string=re.compile(r"[0-9,]+円|Yen|¥", re.I))
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        clean = price_text.replace(",", "").replace(" ", "")
        amt_match = re.search(r"(\d+\.?\d*)", clean)
        if amt_match:
            detail["price_amount"] = float(amt_match.group(1))
            detail["price_raw"] = price_text
            detail["price_tax_included"] = "込" in price_text or "tax" not in price_text.lower()

    # Release month from detail
    release_elem = soup.find(["span", "p", "div"], string=re.compile(r"発売|release", re.I))
    if release_elem:
        parent = release_elem.parent
        if parent:
            release_text = parent.get_text(strip=True)
            detail["release_raw"] = release_text
            parsed = _parse_release_detail(release_text)
            if parsed:
                detail.update(parsed)

    return detail


def _parse_taxonomy_from_cards(soup: BeautifulSoup) -> list[dict[str, Any]] | None:
    """Parse taxonomy from flat cards (c-card__flat p-card__flat)."""
    cards = soup.select(".c-card__flat, .p-card__flat, [class*='flat-card'], .card")
    if not cards:
        return None

    taxonomy_entries = []
    for card in cards:
        link = card.find("a")
        if not link:
            continue

        href = link.get("href", "")
        label = link.get_text(strip=True) or card.get_text(strip=True)

        entry = {"label": label, "url": href}

        # Determine kind from URL pattern
        if "/brand/" in href:
            entry["kind"] = "brand"
            slug_match = re.search(r"/brand/([\w-]+)", href)
            if slug_match:
                entry["slug"] = slug_match.group(1)
        elif "/series/" in href:
            entry["kind"] = "series"
            slug_match = re.search(r"/series/([\w-]+)", href)
            if slug_match:
                entry["slug"] = slug_match.group(1)
        elif "/category/" in href or "cate" in href:
            entry["kind"] = "category"

        taxonomy_entries.append(entry)

    return taxonomy_entries if taxonomy_entries else None


def _parse_taxonomy_from_breadcrumb(soup: BeautifulSoup) -> list[dict[str, Any]] | None:
    """Parse taxonomy from breadcrumb elements (p-breadcrumb)."""
    breadcrumb = soup.select_one(".p-breadcrumb, .breadcrumb, [class*='breadcrumb']")
    if not breadcrumb:
        return None

    items = breadcrumb.find_all("a")
    taxonomy_entries = []
    for item in items:
        href = item.get("href", "")
        label = item.get_text(strip=True)
        if not label or label in ("TOP", "Home", "ホーム"):
            continue

        entry: dict[str, Any] = {"label": label, "url": href}
        if "/brand/" in href:
            entry["kind"] = "brand"
        elif "/series/" in href:
            entry["kind"] = "series"
        elif "/category/" in href or "cate" in href:
            entry["kind"] = "category"

        taxonomy_entries.append(entry)

    return taxonomy_entries if taxonomy_entries else None


def _parse_release_detail(text: str) -> dict[str, str | None] | None:
    """Parse release detail text for structured fields."""
    if not text:
        return None

    result: dict[str, str | None] = {
        "release_month": None,
        "release_date_precision": None,
    }

    # YYYY-MM
    iso_month = re.search(r"(\d{4})-(\d{2})", text)
    if iso_month:
        result["release_month"] = iso_month.group(0)
        result["release_date_precision"] = "month"
        return result

    # Japanese month
    jp_month = re.search(r"(\d{4})年\s*(\d{1,2})月", text)
    if jp_month:
        result["release_month"] = f"{jp_month.group(1)}-{jp_month.group(2).zfill(2)}"
        result["release_date_precision"] = "month"
        return result

    # English month
    en_month = _parse_en_release_month(text)
    if en_month:
        result["release_month"] = en_month
        result["release_date_precision"] = "month"
        return result

    return None


# ---- Chinese Product Detail Parsing ----

def _parse_zh_product_detail(html: str, url: str, cn_id: str) -> dict[str, Any]:
    """Parse a Chinese product detail page.

    Expected structure (from research):
    - Category
    - Brand line via /index/index/brand/cate/{id}
    - Series via /index/index/series/cate/{id}
    """
    soup = BeautifulSoup(html, "lxml")
    detail: dict[str, Any] = {}

    # Taxonomy from links
    taxonomy_entries: list[dict[str, Any]] = []

    brand_link = soup.find("a", href=re.compile(r"/index/index/brand/cate/\d+"))
    if brand_link:
        href = brand_link.get("href", "")
        label = brand_link.get_text(strip=True)
        cate_match = re.search(r"/cate/(\d+)", href)
        taxonomy_entries.append({
            "kind": "brand",
            "id": cate_match.group(1) if cate_match else None,
            "label": label,
            "url": href if href.startswith("http") else f"https://bandaihobbysite.cn{href}",
        })

    series_link = soup.find("a", href=re.compile(r"/index/index/series/cate/\d+"))
    if series_link:
        href = series_link.get("href", "")
        label = series_link.get_text(strip=True)
        cate_match = re.search(r"/cate/(\d+)", href)
        taxonomy_entries.append({
            "kind": "series",
            "id": cate_match.group(1) if cate_match else None,
            "label": label,
            "url": href if href.startswith("http") else f"https://bandaihobbysite.cn{href}",
        })

    # Category text
    for cat_text in ["gunpla", "characterplastic", "30ML"]:
        cat_link = soup.find("a", href=re.compile(cat_text, re.I))
        if cat_link:
            taxonomy_entries.append({
                "kind": "category",
                "label": cat_link.get_text(strip=True) or cat_text,
                "url": cat_link.get("href", ""),
            })

    if taxonomy_entries:
        detail["taxonomy"] = taxonomy_entries

    return detail
