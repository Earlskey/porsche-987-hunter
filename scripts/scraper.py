import asyncio
import re
import sqlite3
import os
import sys
import json
import html
from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

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
    clean = re.sub(r"[^\d.]", "", str(price_str))
    try:
        return float(clean)
    except ValueError:
        return 0.0

def parse_mileage(mile_str):
    if not mile_str:
        return 0
    clean = re.sub(r"[^\d]", "", str(mile_str))
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

def parse_embedded_json(page_content, default_model):
    """Extract listing records directly from Cars.com embedded JSON state."""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', page_content, re.DOTALL)
    target_json = None

    for s in scripts:
        if "srp_results" in s:
            try:
                target_json = json.loads(s.strip())
                break
            except Exception:
                pass

    if not target_json:
        return []

    results = target_json.get("srp_results", {}).get("results", [])
    extracted = []

    for r in results:
        raw_ctx = r.get("analytics", {}).get("context")
        if not raw_ctx:
            continue
        
        clean_json_str = html.unescape(raw_ctx)
        try:
            payload = json.loads(clean_json_str)
        except Exception:
            continue

        price_val = float(payload.get("price") or 0)
        mileage_val = int(payload.get("mileage") or 0)
        year_val = int(payload.get("year") or 2009)
        make_val = payload.get("make") or "Porsche"
        model_val = payload.get("model") or default_model
        trim_raw = payload.get("trim") or "Base"
        listing_id = payload.get("listingId") or ""
        seller_info = payload.get("seller") or {}
        dealer_name = seller_info.get("dealerName", "Dealer") if isinstance(seller_info, dict) else "Dealer"
        zip_code = seller_info.get("zip", "") if isinstance(seller_info, dict) else ""
        location = f"{dealer_name} ({zip_code})".strip() if zip_code else dealer_name

        # Determine trim accurately from trim_raw, title, or vin details
        trim = "Base"
        combined_text = f"{trim_raw} {r.get('analytics', {}).get('context', '')}".upper()

        if "BLACK EDITION" in combined_text:
            trim = "Black Edition"
        elif "SPYDER" in combined_text:
            trim = "Spyder"
        elif "CAYMAN R" in combined_text or "BOXSTER R" in combined_text or " R " in combined_text:
            trim = "R"
        elif "CAYMAN S" in combined_text or "BOXSTER S" in combined_text or " S " in combined_text or combined_text.endswith(" S"):
            trim = "S"

        title = f"{year_val} Porsche {model_val} {trim}"
        url = f"https://www.cars.com/vehicledetail/{listing_id}/" if listing_id else ""
        photo_url = payload.get("primaryThumbnail") or ""

        if price_val > 0 and url:
            extracted.append({
                "id": listing_id,
                "title": title,
                "year": year_val,
                "model": model_val,
                "trim": trim,
                "price": price_val,
                "mileage": mileage_val,
                "location": location,
                "seller_type": "Dealer",
                "url": url,
                "photo_url": photo_url
            })

    return extracted

async def scrape_target(page, target):
    print(f"🔎 Fetching live listings for Porsche {target['model']} from Cars.com...")
    os.makedirs("data", exist_ok=True)

    try:
        response = await page.goto(target["url"], wait_until="domcontentloaded", timeout=60000)
        status_code = response.status if response else 0
        page_title = await page.title()
        print(f"   Response Status: {status_code} | Page Title: '{page_title}'")
    except Exception as e:
        print(f"⚠️ Page load failed for {target['model']}: {e}")
        return

    # Wait briefly for dynamic scripts
    await asyncio.sleep(3)

    content = await page.content()

    # Strategy 1: Parse embedded JSON state (fast & full data accuracy)
    json_listings = parse_embedded_json(content, target["model"])
    if json_listings:
        print(f"   ⚡ Parsed {len(json_listings)} listings via embedded SRP JSON state.")
        for car in json_listings:
            save_listing(car)
        print(f"✅ Found & saved {len(json_listings)} {target['model']} listings.")
        return

    # Strategy 2: Fallback DOM query matching
    CARD_SELECTORS = [
        "fuse-card",
        "div[data-cmp='vehicle-card']",
        ".vehicle-card",
        "div.vehicle-card-main",
        ".spark-card",
        "div[class*='vehicle-card']"
    ]

    cards = []
    found_selector = None
    for sel in CARD_SELECTORS:
        try:
            matched = await page.query_selector_all(sel)
            if matched and len(matched) > 0:
                cards = matched
                found_selector = sel
                break
        except Exception:
            continue

    if not cards:
        print(f"⚠️ Could not find vehicle card elements for {target['model']}.")
        debug_html_path = f"data/debug_{target['model'].lower()}.html"
        debug_png_path = f"data/debug_{target['model'].lower()}.png"
        with open(debug_html_path, "w", encoding="utf-8") as f:
            f.write(content)
        await page.screenshot(path=debug_png_path, full_page=True)
        print(f"   📸 Saved diagnostic HTML to '{debug_html_path}' and screenshot to '{debug_png_path}'.")
        return

    print(f"   Found {len(cards)} cards using DOM selector '{found_selector}'")
    scraped_count = 0

    for card in cards:
        try:
            card_text = await card.inner_text()
            title = ""
            for title_sel in [".title", "h2", ".spark-card-title", "a.vehicle-card-link", "a[href*='/vehicledetail/']"]:
                t_elem = await card.query_selector(title_sel)
                if t_elem:
                    t_text = (await t_elem.inner_text()).strip()
                    if len(t_text) > 3:
                        title = t_text
                        break
            if not title:
                title = f"Porsche {target['model']}"

            year_match = re.search(r"\b(2009|2010|2011|2012)\b", title or card_text)
            year = int(year_match.group(1)) if year_match else 2009

            trim = "Base"
            t_up = title.upper()
            if "BLACK EDITION" in t_up: trim = "Black Edition"
            elif "SPYDER" in t_up: trim = "Spyder"
            elif " R" in t_up: trim = "R"
            elif " S" in t_up or t_up.endswith(" S"): trim = "S"

            price_str = ""
            for price_sel in [".primary-price", "[data-cmp='price']", "span.primary-price", ".spark-card-price"]:
                p_elem = await card.query_selector(price_sel)
                if p_elem:
                    price_str = await p_elem.inner_text()
                    if "$" in price_str: break
            if not price_str:
                p_match = re.search(r"\$[\d,]+", card_text)
                if p_match: price_str = p_match.group(0)

            price = parse_price(price_str)

            mileage_str = ""
            for mile_sel in [".mileage", "[data-cmp='mileage']", "span.mileage", ".spark-card-mileage"]:
                m_elem = await card.query_selector(mile_sel)
                if m_elem:
                    mileage_str = await m_elem.inner_text()
                    if "mi" in mileage_str.lower(): break
            if not mileage_str:
                m_match = re.search(r"[\d,]+\s*(?:mi|miles)", card_text, re.IGNORECASE)
                if m_match: mileage_str = m_match.group(0)

            mileage = parse_mileage(mileage_str)

            location = "Private / Dealer"
            for loc_sel in [".dealer-name", ".seller-name", "[data-cmp='dealer-name']"]:
                l_elem = await card.query_selector(loc_sel)
                if l_elem:
                    loc_txt = (await l_elem.inner_text()).strip()
                    if loc_txt:
                        location = loc_txt
                        break

            rel_url = ""
            for link_sel in ["a.vehicle-card-link", "a[href*='/vehicledetail/']", "a.spark-card-link", "a"]:
                l_elem = await card.query_selector(link_sel)
                if l_elem:
                    href = await l_elem.get_attribute("href")
                    if href and "/vehicledetail/" in href:
                        rel_url = href
                        break

            if not rel_url:
                continue

            full_url = f"https://www.cars.com{rel_url}" if rel_url.startswith("/") else rel_url
            listing_id_match = re.search(r"vehicledetail/([^/]+)", full_url)
            listing_id = listing_id_match.group(1) if listing_id_match else full_url

            photo_url = ""
            img_elem = await card.query_selector("img")
            if img_elem:
                src = await img_elem.get_attribute("src") or await img_elem.get_attribute("data-src")
                if src and src.startswith("http"):
                    photo_url = src

            if price > 0 and full_url:
                save_listing({
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
                })
                scraped_count += 1
        except Exception:
            continue

    print(f"✅ Found & saved {scraped_count} {target['model']} listings via DOM.")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }
        )
        page = await context.new_page()

        for idx, target in enumerate(TARGET_URLS):
            if idx > 0:
                # Add delay between targets to avoid Cloudflare rate limiting
                print("⏳ Waiting 5 seconds before next search query...")
                await asyncio.sleep(5)
            await scrape_target(page, target)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
