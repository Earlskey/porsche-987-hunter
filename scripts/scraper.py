import asyncio
import re
import sqlite3
import os
from playwright.async_api import async_playwright

TARGET_URLS = [
    {
        "model": "Cayman",
        "url": "https://www.cars.com/shopping/results/?list_price_max=&maximum_distance=all&makes[]=porsche&models[]=porsche-cayman&year_min=2009&year_max=2012"
    },
    {
        "model": "Boxster",
        "url": "https://www.cars.com/shopping/results/?list_price_max=&maximum_distance=all&makes[]=porsche&models[]=porsche-boxster&year_min=2009&year_max=2012"
    }
]

def parse_price(price_str):
    if not price_str:
        return 0.0
    clean = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(clean)
    except ValueError:
        return 0.0

def parse_mileage(mile_str):
    if not mile_str:
        return 0
    clean = re.sub(r"[^\d]", "", mile_str)
    try:
        return int(clean)
    except ValueError:
        return 0

def save_listing(car_data):
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/listings.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO listings (id, title, year, model, trim, price, mileage, location, seller_type, url, photo_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            price = excluded.price,
            mileage = excluded.mileage
    """, (
        car_data["id"],
        car_data["title"],
        car_data["year"],
        car_data["model"],
        car_data["trim"],
        car_data["price"],
        car_data["mileage"],
        car_data["location"],
        car_data["seller_type"],
        car_data["url"],
        car_data["photo_url"]
    ))
    
    conn.commit()
    conn.close()

async def scrape_target(page, target):
    print(f"🔎 Fetching live listings for Porsche {target['model']}...")
    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector(".vehicle-card", timeout=15000)
    except Exception as e:
        print(f"⚠️ Could not load card elements for {target['model']}: {e}")
        return

    cards = await page.query_selector_all(".vehicle-card")
    scraped_count = 0

    for card in cards:
        try:
            title_elem = await card.query_selector(".title")
            title = await title_elem.inner_text() if title_elem else f"Porsche {target['model']}"
            
            year_match = re.search(r"\b(2009|2010|2011|2012)\b", title)
            year = int(year_match.group(1)) if year_match else 2009
            
            trim = "S" if " S" in title else "Base"
            if "R" in title: trim = "R"
            if "Spyder" in title: trim = "Spyder"
            if "Black Edition" in title: trim = "Black Edition"

            price_elem = await card.query_selector(".primary-price")
            price_str = await price_elem.inner_text() if price_elem else "$0"
            price = parse_price(price_str)

            mileage_elem = await card.query_selector(".mileage")
            mileage_str = await mileage_elem.inner_text() if mileage_elem else "0 mi"
            mileage = parse_mileage(mileage_str)

            location_elem = await card.query_selector(".dealer-name")
            location = await location_elem.inner_text() if location_elem else "Private / Dealer"

            link_elem = await card.query_selector("a.vehicle-card-link")
            rel_url = await link_elem.get_attribute("href") if link_elem else ""
            full_url = f"https://www.cars.com{rel_url}" if rel_url.startswith("/") else rel_url

            img_elem = await card.query_selector("img.vehicle-image")
            photo_url = await img_elem.get_attribute("src") if img_elem else ""

            listing_id = full_url.split("/")[-2] if "/" in full_url else full_url

            if price > 0 and full_url:
                car_data = {
                    "id": listing_id,
                    "title": title.strip(),
                    "year": year,
                    "model": target["model"],
                    "trim": trim,
                    "price": price,
                    "mileage": mileage,
                    "location": location.strip(),
                    "seller_type": "Dealer",
                    "url": full_url,
                    "photo_url": photo_url
                }
                save_listing(car_data)
                scraped_count += 1
        except Exception:
            continue

    print(f"✅ Found & saved {scraped_count} {target['model']} listings.")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for target in TARGET_URLS:
            await scrape_target(page, target)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
