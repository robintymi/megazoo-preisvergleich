"""
Megazoo Price Comparison Tool - Backend
Automatisch Produkte von megazoo-shop.de crawlen und mit Google Shopping vergleichen.
"""

from flask import Flask, jsonify, request, send_from_directory, Response
import os
import sys
import json
import csv
import io
import threading

# Support both direct run and import from root
sys.path.insert(0, os.path.dirname(__file__))
from database import Database
from scraper import MegazooCrawler, GoogleShoppingScraper

# Resolve frontend path relative to this file's directory
_FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"))
app = Flask(__name__, static_folder=_FRONTEND_DIR)

db = Database()
crawler = MegazooCrawler()
scraper = GoogleShoppingScraper()

# Track crawl/comparison progress
progress = {
    "crawl": {"running": False, "current": 0, "total": 0, "found": 0},
    "compare": {"running": False, "current": 0, "total": 0, "errors": []},
}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory(os.path.join(app.static_folder, "static"), path)


# ---- Product Crawling ----

@app.route("/api/products", methods=["GET"])
def get_products():
    """Get cached megazoo products."""
    cache = crawler.load_products_cache()
    if cache:
        return jsonify(cache)
    return jsonify({"products": [], "count": 0, "crawled_at": None})


@app.route("/api/products/crawl", methods=["POST"])
def start_crawl():
    """Start crawling megazoo-shop.de for all products (runs in background)."""
    if progress["crawl"]["running"]:
        return jsonify({"error": "Crawl laeuft bereits"}), 409

    def run_crawl():
        progress["crawl"] = {"running": True, "current": 0, "total": 0, "found": 0}
        try:
            def on_progress(current, total, found):
                progress["crawl"]["current"] = current
                progress["crawl"]["total"] = total
                progress["crawl"]["found"] = found

            crawler.crawl_all_products(progress_callback=on_progress)
        finally:
            progress["crawl"]["running"] = False

    thread = threading.Thread(target=run_crawl, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/products/crawl/status", methods=["GET"])
def crawl_status():
    """Get current crawl progress."""
    return jsonify(progress["crawl"])


# ---- Price Comparison ----

@app.route("/api/compare/start", methods=["POST"])
def start_comparison():
    """Start comparing products with Google Shopping."""
    if progress["compare"]["running"]:
        return jsonify({"error": "Vergleich laeuft bereits"}), 409

    data = request.get_json() or {}
    product_indices = data.get("indices")
    offset = data.get("offset", 0)
    limit = data.get("limit", scraper.settings.get("batch_size", 20))

    cache = crawler.load_products_cache()
    if not cache or not cache.get("products"):
        return jsonify({"error": "Keine Produkte geladen. Zuerst Crawl starten."}), 400

    products = cache["products"]

    if product_indices:
        selected = [products[i] for i in product_indices if i < len(products)]
    else:
        selected = products[offset:offset + limit]

    if not selected:
        return jsonify({"error": "Keine Produkte im angegebenen Bereich"}), 400

    def run_comparison():
        progress["compare"] = {"running": True, "current": 0, "total": len(selected), "errors": []}
        try:
            for i, product in enumerate(selected):
                try:
                    result = scraper.compare_product(product)
                    db.save_comparison(result)
                except Exception as e:
                    progress["compare"]["errors"].append({
                        "product": product["name"],
                        "error": str(e),
                    })
                progress["compare"]["current"] = i + 1

                if i < len(selected) - 1:
                    import time
                    time.sleep(scraper.settings.get("delay_between_requests", 2))
        finally:
            progress["compare"]["running"] = False

    thread = threading.Thread(target=run_comparison, daemon=True)
    thread.start()
    return jsonify({"status": "started", "count": len(selected)})


@app.route("/api/compare/status", methods=["GET"])
def compare_status():
    """Get current comparison progress."""
    return jsonify(progress["compare"])


# ---- Results & History ----

@app.route("/api/results", methods=["GET"])
def get_results():
    """Get all comparison results."""
    limit = request.args.get("limit", 200, type=int)
    results = db.get_history(limit)
    return jsonify(results)


@app.route("/api/results/<int:comparison_id>", methods=["DELETE"])
def delete_result(comparison_id):
    db.delete_comparison(comparison_id)
    return jsonify({"status": "deleted"})


@app.route("/api/results/clear", methods=["DELETE"])
def clear_results():
    db.clear_all()
    return jsonify({"status": "cleared"})


@app.route("/api/export", methods=["GET"])
def export_csv_file():
    """Export all comparisons as CSV."""
    results = db.get_history(limit=5000)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Produkt", "Megazoo Preis", "Megazoo URL",
        "Konkurrent 1", "Preis 1", "Konkurrent 2", "Preis 2",
        "Konkurrent 3", "Preis 3", "Konkurrent 4", "Preis 4",
        "Konkurrent 5", "Preis 5", "Konkurrent 6", "Preis 6",
        "Durchschnitt Konkurrenz", "Abweichung %", "Empfohlener Preis", "Datum"
    ])

    for item in results:
        row = [item["product_name"], item.get("megazoo_price", ""), item.get("megazoo_url", "")]
        competitors = item.get("competitors", [])
        for i in range(6):
            if i < len(competitors):
                row.extend([competitors[i].get("source", ""), competitors[i].get("price", "")])
            else:
                row.extend(["", ""])
        row.append(item.get("avg_competitor_price", ""))
        row.append(item.get("deviation_percent", ""))
        row.append(item.get("recommended_price", ""))
        row.append(item.get("created_at", ""))
        writer.writerow(row)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=megazoo_preisvergleich.csv"}
    )


# ---- Settings ----

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(scraper.get_settings())


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json()
    scraper.update_settings(data)
    return jsonify({"status": "updated"})


if __name__ == "__main__":
    print("=" * 50)
    print("Megazoo Preisvergleich Tool")
    print("Oeffne http://localhost:5000 im Browser")
    print("=" * 50)
    app.run(debug=True, port=5000)
