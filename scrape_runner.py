#!/usr/bin/env python3
"""
Metrica scrape runner — designed to run in GitHub Actions.

Fetches Yad2 search pages for every configured city, extracts listing
data from the embedded __NEXT_DATA__ JSON, and writes everything to
data/listings.json.  The dashboard imports from that file.

Usage:
    python scrape_runner.py              # scrape all cities
    python scrape_runner.py --city 5000  # scrape a single city code
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("scrape_runner")

DATA_DIR = Path(__file__).parent / "data"
LISTINGS_FILE = DATA_DIR / "listings.json"

DELAY_BETWEEN_CITIES = float(os.getenv("SCRAPE_DELAY", "4"))
DELAY_BETWEEN_PAGES = float(os.getenv("PAGE_DELAY", "3"))
MAX_RETRIES = int(os.getenv("SCRAPE_RETRIES", "2"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "20"))

# ── City definitions (mirrors app/config.py) ─────────────────────────

CITIES = {
    "beer_sheva":     {"code": "9000",  "he": "באר שבע",       "en": "Beer Sheva",      "region": "south"},
    "ashkelon":       {"code": "2000",  "he": "אשקלון",        "en": "Ashkelon",        "region": "south"},
    "ashdod":         {"code": "70",    "he": "אשדוד",         "en": "Ashdod",          "region": "south"},
    "kiryat_gat":     {"code": "1260",  "he": "קריית גת",      "en": "Kiryat Gat",      "region": "south"},
    "tel_aviv":       {"code": "5000",  "he": "תל אביב",       "en": "Tel Aviv",        "region": "center"},
    "rishon_lezion":  {"code": "8300",  "he": "ראשון לציון",    "en": "Rishon LeZion",   "region": "center"},
    "rehovot":        {"code": "8600",  "he": "רחובות",         "en": "Rehovot",         "region": "center"},
    "petah_tikva":    {"code": "7900",  "he": "פתח תקווה",      "en": "Petah Tikva",     "region": "center"},
    "jerusalem":      {"code": "3000",  "he": "ירושלים",        "en": "Jerusalem",       "region": "center"},
    "haifa":          {"code": "4000",  "he": "חיפה",           "en": "Haifa",           "region": "north"},
    "nazareth":       {"code": "8700",  "he": "נצרת",           "en": "Nazareth",        "region": "north"},
    "akko":           {"code": "4",     "he": "עכו",            "en": "Akko",            "region": "north"},
    "kiryat_ata":     {"code": "6800",  "he": "קריית אתא",      "en": "Kiryat Ata",      "region": "north"},
    "kiryat_bialik":  {"code": "6900",  "he": "קריית ביאליק",   "en": "Kiryat Bialik",   "region": "north"},
    "kiryat_motzkin": {"code": "3600",  "he": "קריית מוצקין",   "en": "Kiryat Motzkin",  "region": "north"},
    "kiryat_yam":     {"code": "2800",  "he": "קריית ים",       "en": "Kiryat Yam",      "region": "north"},
    "hadera":         {"code": "6400",  "he": "חדרה",           "en": "Hadera",          "region": "north"},
}

YAD2_URL = "https://www.yad2.co.il/realestate/forsale?city={code}"
YAD2_ITEM_URL = "https://www.yad2.co.il/item/{token}"

# ── Parsing helpers ──────────────────────────────────────────────────

def _safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v):
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _extract_detail(details: dict, key: str):
    """Extract a value from Yad2's additionalDetails map."""
    val = details.get(key)
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("value") or val.get("text")
    return val


def _parse_address(address_obj):
    """Extract city, neighborhood, street from the address block."""
    if not address_obj or not isinstance(address_obj, dict):
        return {}, "", ""

    city_obj = address_obj.get("city") or {}
    hood_obj = address_obj.get("neighborhood") or {}
    street_obj = address_obj.get("street") or {}

    city_name = ""
    if isinstance(city_obj, dict):
        city_name = city_obj.get("text") or city_obj.get("name") or ""
    elif isinstance(city_obj, str):
        city_name = city_obj

    hood_name = ""
    if isinstance(hood_obj, dict):
        hood_name = hood_obj.get("text") or hood_obj.get("name") or ""
    elif isinstance(hood_obj, str):
        hood_name = hood_obj

    street_name = ""
    if isinstance(street_obj, dict):
        street_name = street_obj.get("text") or street_obj.get("name") or ""
    elif isinstance(street_obj, str):
        street_name = street_obj

    return city_name, hood_name, street_name


def parse_yad2_item(raw: dict, city_code: str, city_info: dict) -> dict | None:
    """Convert a single Yad2 feed item into our normalised listing dict."""
    token = raw.get("token")
    if not token:
        return None

    price = raw.get("price")
    if isinstance(price, str):
        price = _safe_int(re.sub(r"[^\d]", "", price))
    elif isinstance(price, (int, float)):
        price = int(price)
    else:
        price = None

    address = raw.get("address") or {}
    city_name, neighborhood, street = _parse_address(address)
    if not city_name:
        city_name = city_info.get("he", "")

    details = raw.get("additionalDetails") or {}
    if isinstance(details, list):
        details = {d.get("key", ""): d.get("value") for d in details if isinstance(d, dict)}

    rooms = _safe_float(_extract_detail(details, "roomsCount") or _extract_detail(details, "rooms"))
    sqm = _safe_float(_extract_detail(details, "squareMeter"))
    floor_val = _extract_detail(details, "floor")
    floor = _safe_int(floor_val)
    prop_type = _extract_detail(details, "property") or raw.get("subcategoryName") or ""

    parking = _extract_detail(details, "parking")
    has_parking = None
    if parking is not None:
        if isinstance(parking, bool):
            has_parking = parking
        elif isinstance(parking, str):
            has_parking = parking.strip().lower() not in ("", "0", "false", "no", "אין", "ללא")
        elif isinstance(parking, (int, float)):
            has_parking = parking > 0

    elevator = _extract_detail(details, "elevator")
    has_elevator = None
    if elevator is not None:
        if isinstance(elevator, bool):
            has_elevator = elevator
        elif isinstance(elevator, str):
            has_elevator = elevator.strip().lower() not in ("", "0", "false", "no", "אין", "ללא")

    # Image — try multiple locations
    image_url = None
    cover = raw.get("coverImage")
    if isinstance(cover, str) and cover:
        image_url = cover
    elif isinstance(cover, dict):
        image_url = cover.get("src") or cover.get("url")
    if not image_url:
        images = raw.get("images") or raw.get("media") or []
        if images and isinstance(images, list):
            first = images[0]
            image_url = first if isinstance(first, str) else (first.get("src") or first.get("url") if isinstance(first, dict) else None)
    metadata = raw.get("metaData") or {}
    if not image_url and isinstance(metadata, dict):
        image_url = metadata.get("coverImage") or metadata.get("imageUrl")

    return {
        "external_id": f"yad2_{token}",
        "source": "yad2",
        "url": YAD2_ITEM_URL.format(token=token),
        "title": raw.get("title") or "",
        "price": price,
        "city": city_name,
        "city_code": city_code,
        "neighborhood": neighborhood,
        "address": street,
        "size_sqm": sqm,
        "rooms": rooms,
        "floor": floor,
        "total_floors": None,
        "has_parking": has_parking,
        "has_elevator": has_elevator,
        "image_url": image_url,
        "property_type": prop_type,
    }


# ── Scraper (Playwright) ────────────────────────────────────────────

def scrape_yad2_playwright(cities_to_scrape: dict) -> list[dict]:
    """Use Playwright + stealth to fetch Yad2 pages and extract listings."""
    if not HAS_PLAYWRIGHT:
        log.error("Playwright not installed. Run: pip install playwright playwright-stealth && python -m playwright install firefox")
        return []

    all_listings: list[dict] = []
    stealth = Stealth()

    with stealth.use_sync(sync_playwright()) as p:
        browser = p.firefox.launch(headless=True)
        ctx = browser.new_context(
            locale="he-IL",
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
        )
        page = ctx.new_page()

        for slug, city in cities_to_scrape.items():
            code = city["code"]
            log.info("Scraping %s (%s)…", city["en"], code)

            items = _fetch_city_all_pages(page, code, city)
            all_listings.extend(items)
            log.info("  → %d total listings for %s", len(items), city["en"])

            time.sleep(DELAY_BETWEEN_CITIES)

        browser.close()

    return all_listings


FEED_CATEGORIES = ["private", "agency", "yad1", "platinum", "kingOfTheHar", "trio", "booster", "leadingBroker"]


def _fetch_city_all_pages(page, code: str, city: dict) -> list[dict]:
    """Paginate through all Yad2 search pages for a city."""
    all_items: list[dict] = []
    seen_tokens: set[str] = set()

    for page_num in range(1, MAX_PAGES + 1):
        url = f"{YAD2_URL.format(code=code)}&page={page_num}"
        items, total_pages = _fetch_single_page(page, url, code, city, page_num)

        new_on_page = 0
        for item in items:
            eid = item["external_id"]
            if eid not in seen_tokens:
                seen_tokens.add(eid)
                all_items.append(item)
                new_on_page += 1

        log.info("  page %d/%s — %d items (%d new)", page_num, total_pages or "?", len(items), new_on_page)

        if not items or new_on_page == 0:
            break
        if total_pages and page_num >= total_pages:
            break

        time.sleep(DELAY_BETWEEN_PAGES)

    return all_items


def _fetch_single_page(page, url: str, code: str, city: dict, page_num: int) -> tuple[list[dict], int | None]:
    """Fetch one page of Yad2 results. Returns (items, total_pages)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000 + (attempt * 2000))

            title = page.title()
            if "captcha" in title.lower() or "shieldsquare" in title.lower():
                log.warning("  Captcha on attempt %d for %s page %d", attempt, city["en"], page_num)
                if attempt < MAX_RETRIES:
                    page.wait_for_timeout(10000)
                continue

            nd = page.query_selector("script#__NEXT_DATA__")
            if not nd:
                log.warning("  No __NEXT_DATA__ on attempt %d for %s page %d", attempt, city["en"], page_num)
                continue

            raw = nd.inner_text()
            data = json.loads(raw)
            feed = data.get("props", {}).get("pageProps", {}).get("feed", {})

            items: list[dict] = []
            for category in FEED_CATEGORIES:
                for raw_item in feed.get(category, []):
                    if not isinstance(raw_item, dict):
                        continue
                    parsed = parse_yad2_item(raw_item, code, city)
                    if parsed:
                        items.append(parsed)

            pagination = feed.get("pagination") or {}
            total_pages = pagination.get("last_page") or pagination.get("totalPages") or pagination.get("pages")
            if isinstance(total_pages, str):
                total_pages = _safe_int(total_pages)

            return items, total_pages

        except Exception as exc:
            log.warning("  Error on attempt %d for %s page %d: %s", attempt, city["en"], page_num, exc)
            if attempt < MAX_RETRIES:
                time.sleep(5)

    return [], None


# ── Merge + write ────────────────────────────────────────────────────

def merge_and_save(new_listings: list[dict]):
    """Merge new listings into the existing data file."""
    DATA_DIR.mkdir(exist_ok=True)

    existing: list[dict] = []
    if LISTINGS_FILE.exists():
        try:
            existing = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []

    existing_map = {item["external_id"]: item for item in existing}

    now = datetime.now(timezone.utc).isoformat()
    new_count = 0

    for item in new_listings:
        eid = item["external_id"]
        if eid in existing_map:
            existing_map[eid]["last_seen"] = now
            existing_map[eid]["price"] = item.get("price") or existing_map[eid].get("price")
            if item.get("image_url"):
                existing_map[eid]["image_url"] = item["image_url"]
        else:
            item["first_seen"] = now
            item["last_seen"] = now
            existing_map[eid] = item
            new_count += 1

    all_listings = list(existing_map.values())
    LISTINGS_FILE.write_text(
        json.dumps(all_listings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log.info("Saved %d total listings (%d new) to %s", len(all_listings), new_count, LISTINGS_FILE)
    return len(all_listings), new_count


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Metrica Yad2 scraper")
    parser.add_argument("--city", help="Scrape only this city code")
    args = parser.parse_args()

    if args.city:
        cities = {k: v for k, v in CITIES.items() if v["code"] == args.city}
        if not cities:
            log.error("Unknown city code: %s", args.city)
            sys.exit(1)
    else:
        cities = CITIES

    log.info("Starting scrape for %d cities", len(cities))
    listings = scrape_yad2_playwright(cities)
    total, new = merge_and_save(listings)

    print(f"::notice::Scrape complete — {total} total listings, {new} new")


if __name__ == "__main__":
    main()
