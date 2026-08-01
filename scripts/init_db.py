import sqlite3
import os

os.makedirs("data", exist_ok=True)
conn = sqlite3.connect("data/listings.db")
cursor = conn.cursor()

# Create Listings Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    title TEXT,
    year INTEGER,
    model TEXT,               -- Cayman or Boxster
    trim TEXT,                -- Base, S, Black Edition, R, Spyder
    transmission TEXT,        -- Manual or PDK
    price REAL,
    mileage INTEGER,
    location TEXT,
    seller_type TEXT,        -- Private or Dealer
    url TEXT UNIQUE,
    photo_url TEXT,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- Valuation & Flagging
    kbb_value REAL,
    discount_pct REAL,
    is_flagged INTEGER DEFAULT 0,  -- 1 if >= 15% under market
    
    -- Outreach Draft
    negotiation_draft TEXT,
    status TEXT DEFAULT 'New'       -- New, Contacted, Rejected, Purchased
)
""")

# Create Search Preferences Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS search_configs (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

defaults = [
    ("max_budget", "38000"),
    ("min_year", "2009"),
    ("max_year", "2012"),
    ("flag_threshold_pct", "15"),
    ("models", "Cayman,Boxster"),
    ("exclude_salvage", "1")
]

cursor.executemany("INSERT OR REPLACE INTO search_configs VALUES (?, ?)", defaults)

conn.commit()
conn.close()
print("✅ Database initialized at data/listings.db")
