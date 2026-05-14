import os

DATABASE_URL = os.getenv("METRICA_DB_URL", "sqlite:///metrica.db")
SCRAPE_INTERVAL_DAYS = int(os.getenv("METRICA_SCRAPE_INTERVAL", "7"))
SCRAPE_DELAY_SECONDS = float(os.getenv("METRICA_SCRAPE_DELAY", "2.5"))
MAX_PAGES_PER_SEARCH = int(os.getenv("METRICA_MAX_PAGES", "10"))

# ---------------------------------------------------------------------------
# City definitions – each maps a slug to Yad2 city code + display names.
# Yad2 city codes may shift over time; verify at yad2.co.il if results
# come back empty and update the code values here.
# ---------------------------------------------------------------------------

CITIES = {
    # South
    "beer_sheva":     {"code": "9000",  "he": "באר שבע",       "en": "Beer Sheva",      "region": "south"},
    "ashkelon":       {"code": "2000",  "he": "אשקלון",        "en": "Ashkelon",        "region": "south"},
    "ashdod":         {"code": "70",    "he": "אשדוד",         "en": "Ashdod",          "region": "south"},
    "kiryat_gat":     {"code": "1260",  "he": "קריית גת",      "en": "Kiryat Gat",      "region": "south"},
    # Center
    "tel_aviv":       {"code": "5000",  "he": "תל אביב",       "en": "Tel Aviv",        "region": "center"},
    "rishon_lezion":  {"code": "8300",  "he": "ראשון לציון",    "en": "Rishon LeZion",   "region": "center"},
    "rehovot":        {"code": "8600",  "he": "רחובות",         "en": "Rehovot",         "region": "center"},
    "petah_tikva":    {"code": "7900",  "he": "פתח תקווה",      "en": "Petah Tikva",     "region": "center"},
    "jerusalem":      {"code": "3000",  "he": "ירושלים",        "en": "Jerusalem",       "region": "center"},
    # North
    "haifa":          {"code": "4000",  "he": "חיפה",           "en": "Haifa",           "region": "north"},
    "nazareth":       {"code": "8700",  "he": "נצרת",           "en": "Nazareth",        "region": "north"},
    "akko":           {"code": "4",     "he": "עכו",            "en": "Akko",            "region": "north"},
    "kiryat_ata":     {"code": "6800",  "he": "קריית אתא",      "en": "Kiryat Ata",      "region": "north"},
    "kiryat_bialik":  {"code": "6900",  "he": "קריית ביאליק",   "en": "Kiryat Bialik",   "region": "north"},
    "kiryat_motzkin": {"code": "3600",  "he": "קריית מוצקין",   "en": "Kiryat Motzkin",  "region": "north"},
    "kiryat_yam":     {"code": "2800",  "he": "קריית ים",       "en": "Kiryat Yam",      "region": "north"},
    "hadera":         {"code": "6400",  "he": "חדרה",           "en": "Hadera",          "region": "north"},
}

ALL_CITY_CODES = [c["code"] for c in CITIES.values()]

# ---------------------------------------------------------------------------
# Dashboard sections – each section defines a filter applied against the DB.
# `cities` = None means "all tracked cities".
# ---------------------------------------------------------------------------

SECTIONS = [
    {
        "id": "entry_level",
        "title": "Under 1.4M",
        "subtitle": "Entry Level",
        "price_min": 0,
        "price_max": 1_400_000,
        "cities": None,
        "neighborhoods": None,
        "property_types": None,
    },
    {
        "id": "mid_range",
        "title": "1.4M \u2013 2.6M",
        "subtitle": "Mid Range",
        "price_min": 1_400_000,
        "price_max": 2_600_000,
        "cities": None,
        "neighborhoods": None,
        "property_types": None,
    },
    {
        "id": "armon_hanatziv",
        "title": "Armon HaNatziv",
        "subtitle": "\u05d0\u05e8\u05de\u05d5\u05df \u05d4\u05e0\u05e6\u05d9\u05d1 \u2014 Apartments",
        "price_min": None,
        "price_max": None,
        "cities": ["3000"],
        "neighborhoods": ["\u05d0\u05e8\u05de\u05d5\u05df \u05d4\u05e0\u05e6\u05d9\u05d1"],
        "property_types": ["apartment"],
    },
    {
        "id": "givat_olga",
        "title": "Givat Olga",
        "subtitle": "\u05d2\u05d1\u05e2\u05ea \u05d0\u05d5\u05dc\u05d2\u05d4",
        "price_min": None,
        "price_max": None,
        "cities": ["6400"],
        "neighborhoods": ["\u05d2\u05d1\u05e2\u05ea \u05d0\u05d5\u05dc\u05d2\u05d4"],
        "property_types": None,
    },
]

SECTION_MAP = {s["id"]: s for s in SECTIONS}
