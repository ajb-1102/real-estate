"""
Metrica — Israeli real-estate intelligence dashboard.

FastAPI application: serves the dashboard, proxies images, exposes a
REST API for fetching / filtering listings, and imports scraped data
from data/listings.json (produced by scrape_runner.py in GitHub Actions).
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import CITIES, SECTIONS, SECTION_MAP
from app.database import get_db, init_db, SessionLocal
from app.models import Listing, ScrapeLog

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(name)-24s  %(levelname)-7s  %(message)s")
log = logging.getLogger("metrica")

DATA_DIR = Path(__file__).parent.parent / "data"
LISTINGS_FILE = DATA_DIR / "listings.json"


# ── JSON import ──────────────────────────────────────────────────────

def import_from_json():
    """Read data/listings.json and upsert every listing into SQLite."""
    if not LISTINGS_FILE.exists():
        log.info("No listings file at %s — nothing to import.", LISTINGS_FILE)
        return 0, 0

    try:
        raw = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read %s: %s", LISTINGS_FILE, exc)
        return 0, 0

    db = SessionLocal()
    try:
        found, new = _upsert_listings(db, raw)
        scrape_log = ScrapeLog(
            source="json_import",
            status="success",
            listings_found=found,
            listings_new=new,
            finished_at=datetime.now(timezone.utc),
        )
        db.add(scrape_log)
        db.commit()
        log.info("Imported %d listings (%d new) from JSON.", found, new)
        return found, new
    finally:
        db.close()


def _upsert_listings(db: Session, items: list[dict]) -> tuple[int, int]:
    found = 0
    new = 0
    now = datetime.now(timezone.utc)
    for data in items:
        ext_id = data.get("external_id")
        if not ext_id:
            continue
        found += 1
        existing = db.query(Listing).filter_by(external_id=ext_id).first()
        if existing:
            existing.last_seen = now
            existing.price = data.get("price") or existing.price
            existing.image_url = data.get("image_url") or existing.image_url
        else:
            first_seen = data.get("first_seen")
            if isinstance(first_seen, str):
                try:
                    first_seen = datetime.fromisoformat(first_seen)
                except ValueError:
                    first_seen = now
            else:
                first_seen = now

            listing = Listing(
                external_id=ext_id,
                source=data.get("source", ""),
                url=data.get("url", ""),
                title=data.get("title", ""),
                price=data.get("price"),
                city=data.get("city", ""),
                city_code=data.get("city_code", ""),
                neighborhood=data.get("neighborhood", ""),
                address=data.get("address", ""),
                size_sqm=data.get("size_sqm"),
                rooms=data.get("rooms"),
                floor=data.get("floor"),
                total_floors=data.get("total_floors"),
                has_parking=data.get("has_parking"),
                has_elevator=data.get("has_elevator"),
                image_url=data.get("image_url"),
                property_type=data.get("property_type", ""),
                first_seen=first_seen,
                last_seen=now,
            )
            db.add(listing)
            new += 1
    db.commit()
    return found, new


# ── App lifecycle ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    found, new = import_from_json()
    if found:
        log.info("Auto-imported %d listings (%d new) on startup.", found, new)
    yield


app = FastAPI(title="Metrica", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ── Pages ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request, "dashboard.html", {"sections": SECTIONS}
    )


# ── API: sections & listings ────────────────────────────────────────

@app.get("/api/sections")
def api_sections(db: Session = Depends(get_db)):
    out = []
    for sec in SECTIONS:
        q = _build_query(db, sec)
        count = q.count()
        out.append({"id": sec["id"], "title": sec["title"], "subtitle": sec["subtitle"], "count": count})
    return out


@app.get("/api/listings/{section_id}")
def api_listings(
    section_id: str,
    status_filter: str = Query("active", pattern="^(active|saved|not_interested|all)$"),
    db: Session = Depends(get_db),
):
    sec = SECTION_MAP.get(section_id)
    if not sec:
        return JSONResponse({"error": "unknown section"}, status_code=404)

    q = _build_query(db, sec)
    if status_filter == "active":
        q = q.filter(Listing.status.in_(["new", "saved"]))
    elif status_filter != "all":
        q = q.filter(Listing.status == status_filter)

    q = q.order_by(Listing.price.asc())
    rows = q.all()

    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"city": "", "city_he": "", "count": 0, "listings": []})
    for r in rows:
        city_key = r.city or "Unknown"
        g = groups[city_key]
        g["city"] = city_key
        city_info = _city_info_by_name(city_key)
        g["city_he"] = city_info["he"] if city_info else city_key
        g["count"] += 1
        g["listings"].append(_listing_dict(r))

    sorted_groups = sorted(groups.values(), key=lambda g: g["count"], reverse=True)
    return {"section": sec, "total": len(rows), "cities": sorted_groups}


def _build_query(db: Session, sec: dict):
    q = db.query(Listing)
    if sec.get("price_min") is not None:
        q = q.filter(Listing.price >= sec["price_min"])
    if sec.get("price_max") is not None:
        q = q.filter(Listing.price <= sec["price_max"])

    if sec.get("cities"):
        q = q.filter(Listing.city_code.in_(sec["cities"]))
    if sec.get("neighborhoods"):
        q = q.filter(Listing.neighborhood.in_(sec["neighborhoods"]))
    if sec.get("property_types"):
        pt = sec["property_types"]
        if "apartment" in pt:
            q = q.filter(Listing.property_type.in_(["apartment", "דירה", "1", ""]))
    return q


def _listing_dict(r: Listing) -> dict:
    return {
        "id": r.id,
        "external_id": r.external_id,
        "source": r.source,
        "url": r.url,
        "title": r.title,
        "price": r.price,
        "city": r.city,
        "neighborhood": r.neighborhood,
        "address": r.address,
        "size_sqm": r.size_sqm,
        "rooms": r.rooms,
        "floor": r.floor,
        "total_floors": r.total_floors,
        "has_parking": r.has_parking,
        "has_elevator": r.has_elevator,
        "image_url": f"/api/proxy-image?url={urllib.parse.quote_plus(r.image_url)}" if r.image_url else None,
        "property_type": r.property_type,
        "first_seen": r.first_seen.isoformat() if r.first_seen else None,
        "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        "status": r.status,
        "is_new": _is_new(r),
    }


def _is_new(r: Listing) -> bool:
    if not r.first_seen:
        return False
    delta = datetime.now(timezone.utc) - r.first_seen.replace(tzinfo=timezone.utc)
    return delta.days <= 7


def _city_info_by_name(city_name: str) -> dict | None:
    for c in CITIES.values():
        if c["he"] == city_name or c["en"].lower() == city_name.lower():
            return c
    return None


# ── API: listing actions ─────────────────────────────────────────────

@app.post("/api/listings/{listing_id}/status")
def api_set_status(listing_id: int, status: str = Query(..., pattern="^(new|saved|not_interested)$"), db: Session = Depends(get_db)):
    row = db.query(Listing).filter_by(id=listing_id).first()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    row.status = status
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": listing_id, "status": status}


# ── API: refresh (re-import from JSON) ───────────────────────────────

@app.post("/api/refresh")
def api_refresh():
    found, new = import_from_json()
    return {"status": "done", "listings_found": found, "listings_new": new}


@app.get("/api/refresh/status")
def api_refresh_status(db: Session = Depends(get_db)):
    last = db.query(ScrapeLog).order_by(ScrapeLog.id.desc()).first()
    return {
        "running": False,
        "last_scrape": {
            "started_at": last.started_at.isoformat() if last else None,
            "finished_at": last.finished_at.isoformat() if last and last.finished_at else None,
            "status": last.status if last else None,
            "listings_found": last.listings_found if last else 0,
            "listings_new": last.listings_new if last else 0,
        } if last else None,
    }


# ── API: stats ───────────────────────────────────────────────────────

@app.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    total = db.query(Listing).count()
    saved = db.query(Listing).filter_by(status="saved").count()
    return {"total": total, "saved": saved}


# ── Image proxy ──────────────────────────────────────────────────────

@app.get("/api/proxy-image")
async def proxy_image(url: str = Query(...)):
    if not url:
        return Response(status_code=400)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.yad2.co.il/"})
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=ct, headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        return Response(status_code=502)
