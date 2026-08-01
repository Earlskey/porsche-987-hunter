import sqlite3
import os
import jinja2

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porsche 987.2 Hunter | Earlskey</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen p-6">
    <div class="max-w-6xl mx-auto">
        <header class="mb-8 border-b border-slate-800 pb-4 flex justify-between items-center">
            <div>
                <h1 class="text-3xl font-bold text-amber-500">Porsche 987.2 Deal Tracker</h1>
                <p class="text-slate-400 text-sm">Targeting clean 2009–2012 Cayman & Boxster listings</p>
            </div>
            <a href="https://porsche.earlskey.net" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-2 rounded text-slate-300">porsche.earlskey.net</a>
        </header>

        <h2 class="text-xl font-semibold text-emerald-400 mb-4">🔥 Flagged Deals (≥15% Under Market)</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
            {% for car in flagged %}
            <div class="bg-slate-800 border-2 border-emerald-500/50 rounded-lg p-5 shadow-lg">
                <div class="flex justify-between items-start mb-2">
                    <h3 class="font-bold text-lg text-white">{{ car.title }}</h3>
                    <span class="bg-emerald-500/20 text-emerald-400 font-bold px-2 py-1 text-xs rounded">-{{ car.discount_pct }}% OFF</span>
                </div>
                <p class="text-2xl font-black text-amber-400 mb-2">${{ "{:,.0f}".format(car.price) }} <span class="text-xs text-slate-400 font-normal">| {{ "{:,.0f}".format(car.mileage) }} mi</span></p>
                <p class="text-xs text-slate-400 mb-4">Est. KBB: ${{ "{:,.0f}".format(car.kbb_value) }} • {{ car.location }}</p>
                <div class="bg-slate-900 p-3 rounded mb-4 border border-slate-700">
                    <p class="text-xs font-semibold text-slate-400 mb-1">Outreach Draft:</p>
                    <p class="text-xs text-slate-300 italic">"{{ car.negotiation_draft }}"</p>
                </div>
                <a href="{{ car.url }}" target="_blank" class="block text-center bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold py-2 rounded text-sm transition">View Listing →</a>
            </div>
            {% else %}
            <p class="text-slate-500 text-sm italic">No flagged deals today. Scraper running daily.</p>
            {% endfor %}
        </div>

        <h2 class="text-xl font-semibold text-slate-200 mb-4">All Active 987.2 Listings</h2>
        <div class="overflow-x-auto bg-slate-800 rounded-lg border border-slate-700">
            <table class="w-full text-left text-sm text-slate-300">
                <thead class="bg-slate-950 text-slate-400 uppercase text-xs">
                    <tr>
                        <th class="p-3">Car</th>
                        <th class="p-3">Price</th>
                        <th class="p-3">Mileage</th>
                        <th class="p-3">KBB Valuation</th>
                        <th class="p-3">Location</th>
                        <th class="p-3">Action</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-700">
                    {% for car in all_cars %}
                    <tr class="hover:bg-slate-700/50">
                        <td class="p-3 font-medium text-white">{{ car.year }} {{ car.model }} {{ car.trim }}</td>
                        <td class="p-3 font-bold text-amber-400">${{ "{:,.0f}".format(car.price) }}</td>
                        <td class="p-3">{{ "{:,.0f}".format(car.mileage) }} mi</td>
                        <td class="p-3 text-slate-400">${{ "{:,.0f}".format(car.kbb_value) }}</td>
                        <td class="p-3">{{ car.location }}</td>
                        <td class="p-3"><a href="{{ car.url }}" target="_blank" class="text-amber-400 hover:underline">Link</a></td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" class="p-4 text-center text-slate-500 text-sm">No listings recorded yet. Run scraper to populate data.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

def build():
    os.makedirs("data", exist_ok=True)
    db_path = "data/listings.db"
    
    if not os.path.exists(db_path):
        print("⚠️ listings.db missing. Generating blank dashboard template...")
        rendered = jinja2.Template(TEMPLATE).render(flagged=[], all_cars=[])
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listings'")
        if not cursor.fetchone():
            flagged, all_cars = [], []
        else:
            flagged = cursor.execute("SELECT * FROM listings WHERE is_flagged = 1 ORDER BY discount_pct DESC").fetchall()
            all_cars = cursor.execute("SELECT * FROM listings ORDER BY scraped_at DESC").fetchall()
        
        rendered = jinja2.Template(TEMPLATE).render(flagged=flagged, all_cars=all_cars)
        conn.close()

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(rendered)
    print("✅ Dashboard generated at index.html")

if __name__ == "__main__":
    build()
