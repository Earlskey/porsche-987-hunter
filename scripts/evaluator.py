import sqlite3
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def get_kbb_baseline(year, model, trim, mileage):
    base_price = 28000 if "Base" in trim or "Standard" in trim else 36000
    if "S" in trim: base_price = 37000
    if "R" in trim or "Spyder" in trim: base_price = 60000

    mileage_diff = mileage - 50000
    estimated_val = base_price - (mileage_diff * 0.12)
    return round(max(estimated_val, 15000), 2)

def evaluate_and_draft():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/listings.db")
    cursor = conn.cursor()
    
    # Check if table exists before querying
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listings'")
    if not cursor.fetchone():
        print("⚠️ Table 'listings' not found. Run scripts/init_db.py first.")
        conn.close()
        return

    cursor.execute("SELECT id, title, year, model, trim, price, mileage, url, seller_type FROM listings WHERE is_flagged = 0")
    rows = cursor.fetchall()

    for row in rows:
        lid, title, year, model, trim, price, mileage, url, seller_type = row
        kbb = get_kbb_baseline(year, model, trim, mileage)
        discount_pct = ((kbb - price) / kbb) * 100
        is_flagged = 1 if discount_pct >= 15 else 0
        
        draft = ""
        if is_flagged:
            draft = (
                f"Hi! I saw your {year} {model} {trim} listed on {seller_type}. "
                f"Is it still available? Has it had recent 987.2 maintenance done "
                f"(AOS, water pump, shift cables, or PDK service)? I am a serious buyer."
            )

        cursor.execute("""
            UPDATE listings 
            SET kbb_value = ?, discount_pct = ?, is_flagged = ?, negotiation_draft = ?
            WHERE id = ?
        """, (kbb, round(discount_pct, 1), is_flagged, draft, lid))

    conn.commit()
    conn.close()
    print("✅ Evaluated all listings & generated draft messages.")

if __name__ == "__main__":
    evaluate_and_draft()
