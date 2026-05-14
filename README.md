# Metrica — Israeli Real Estate Intelligence Dashboard

Personal dashboard that aggregates property listings from **Yad2**, refreshed weekly via GitHub Actions. Browse, filter, save, and track the Israeli real estate market across multiple price brackets, regions, and specific neighborhoods.

## How It Works

```
GitHub Actions (weekly)          Local Machine
┌─────────────────────┐         ┌────────────────────────┐
│  scrape_runner.py    │         │  python run.py         │
│  Playwright+Stealth  │──git──→│  FastAPI dashboard     │
│  → data/listings.json│  push  │  imports JSON → SQLite │
└─────────────────────┘         │  serves UI at :8000    │
                                └────────────────────────┘
```

1. **GitHub Actions** runs `scrape_runner.py` weekly (Sunday 06:00 UTC)
2. Playwright (Firefox + stealth) navigates to Yad2 search pages for each city
3. Extracts listing data from the embedded `__NEXT_DATA__` JSON
4. Saves to `data/listings.json` and commits back to the repo
5. You `git pull` and the dashboard auto-imports on startup

## Sections

| Section | Filter |
|---------|--------|
| Under 1.4M | All tracked cities, 0–1.4M ₪ |
| 1.4M – 2.6M | All tracked cities, 1.4M–2.6M ₪ |
| Armon HaNatziv | Jerusalem — apartments only, any price |
| Givat Olga | Hadera area — all listings, any price |

Cities tracked: Beer Sheva, Ashkelon, Ashdod, Kiryat Gat, Tel Aviv, Rishon LeZion, Rehovot, Petah Tikva, Jerusalem, Haifa, Nazareth, Akko, Krayot, Hadera.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch the dashboard
python run.py

# 3. Open in browser
open http://127.0.0.1:8000
```

On startup the dashboard auto-imports any listings from `data/listings.json` into SQLite. Click **Refresh** in the header to re-import after pulling new data.

## Running the Scraper Manually

```bash
# Install Playwright browser (one time)
python -m playwright install firefox

# Scrape all cities
python scrape_runner.py

# Scrape a single city
python scrape_runner.py --city 5000
```

> **Note:** Yad2 has anti-bot protection (ShieldSquare/PerimeterX). The scraper uses Playwright + stealth mode to bypass it. From GitHub Actions cloud IPs it works reliably. Locally it may intermittently hit captchas — this is normal.

## GitHub Actions Setup

1. Push this repo to GitHub
2. The workflow at `.github/workflows/scrape.yml` runs weekly
3. It scrapes all cities, commits `data/listings.json`, and pushes
4. Pull the repo to get fresh data, then start the dashboard

To trigger a manual scrape: go to **Actions → Weekly Scrape → Run workflow**.

## Configuration

City codes and sections are defined in `app/config.py`. Yad2 city codes may change — verify at yad2.co.il if a city returns no results.

| Env Variable | Default | Description |
|---|---|---|
| `SCRAPE_DELAY` | `4` | Seconds between city scrapes |
| `SCRAPE_RETRIES` | `2` | Retry attempts per city on captcha |
| `METRICA_DB_URL` | `sqlite:///metrica.db` | Database connection string |

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard |
| `GET` | `/api/sections` | Section list with counts |
| `GET` | `/api/listings/{id}` | Listings grouped by city |
| `POST` | `/api/listings/{id}/status?status=saved` | Save / hide a listing |
| `POST` | `/api/refresh` | Re-import from JSON |
| `GET` | `/api/stats` | Total / saved counts |
| `GET` | `/api/proxy-image?url=...` | Image proxy |
