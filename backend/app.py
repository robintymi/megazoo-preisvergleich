"""
Megazoo Price Comparison Tool - Backend
Vergleicht Preise von megazoo-shop.de mit Konkurrenten via Google Shopping.
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os
import json
from database import Database
from scraper import GoogleShoppingScraper

app = Flask(__name__, static_folder="../frontend")
CORS(app)

db = Database()
scraper = GoogleShoppingScraper()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory(os.path.join(app.static_folder, "static"), path)


@app.route("/api/search", methods=["POST"])
def search_product():
    """Sucht ein Produkt bei Google Shopping und vergleicht Preise."""
    data = request.get_json()
    product_name = data.get("product_name", "").strip()

    if not product_name:
        return jsonify({"error": "Produktname ist erforderlich"}), 400

    try:
        results = scraper.search(product_name)

        if not results:
            return jsonify({"error": "Keine Ergebnisse gefunden"}), 404

        # Separate Megazoo from competitors
        megazoo_results = []
        competitor_results = []

        for r in results:
            source_lower = r.get("source", "").lower()
            if "megazoo" in source_lower:
                megazoo_results.append(r)
            else:
                competitor_results.append(r)

        # Sort competitors by price
        competitor_results.sort(key=lambda x: x.get("price", float("inf")))

        # Calculate stats from up to 6 competitors
        top_competitors = competitor_results[:6]
        competitor_prices = [c["price"] for c in top_competitors if c.get("price")]

        avg_price = None
        deviation = None
        recommended_price = None
        megazoo_price = megazoo_results[0]["price"] if megazoo_results else None

        if competitor_prices:
            avg_price = round(sum(competitor_prices) / len(competitor_prices), 2)

            if megazoo_price and avg_price:
                deviation = round(
                    ((megazoo_price - avg_price) / avg_price) * 100, 1
                )

            # Recommended price: slightly below average to be competitive
            recommended_price = round(avg_price * 0.97, 2)

        comparison = {
            "product_name": product_name,
            "megazoo_price": megazoo_price,
            "megazoo_source": megazoo_results[0].get("source") if megazoo_results else None,
            "megazoo_link": megazoo_results[0].get("link") if megazoo_results else None,
            "competitors": top_competitors,
            "avg_competitor_price": avg_price,
            "deviation_percent": deviation,
            "recommended_price": recommended_price,
            "total_results": len(results),
        }

        # Save to database
        db.save_comparison(comparison)

        return jsonify(comparison)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def get_history():
    """Gibt die letzten Vergleiche zurueck."""
    limit = request.args.get("limit", 50, type=int)
    history = db.get_history(limit)
    return jsonify(history)


@app.route("/api/history/<int:comparison_id>", methods=["DELETE"])
def delete_comparison(comparison_id):
    """Loescht einen Vergleich."""
    db.delete_comparison(comparison_id)
    return jsonify({"status": "deleted"})


@app.route("/api/export", methods=["GET"])
def export_csv():
    """Exportiert alle Vergleiche als CSV."""
    import csv
    import io

    history = db.get_history(limit=1000)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Produkt", "Megazoo Preis", "Konkurrent 1", "Konkurrent 2",
        "Konkurrent 3", "Konkurrent 4", "Konkurrent 5", "Konkurrent 6",
        "Durchschnitt Konkurrenz", "Abweichung %", "Empfohlener Preis", "Datum"
    ])

    for item in history:
        row = [item["product_name"], item.get("megazoo_price", "")]
        competitors = item.get("competitors", [])
        for i in range(6):
            if i < len(competitors):
                row.append(f"{competitors[i].get('price', '')} ({competitors[i].get('source', '')})")
            else:
                row.append("")
        row.append(item.get("avg_competitor_price", ""))
        row.append(item.get("deviation_percent", ""))
        row.append(item.get("recommended_price", ""))
        row.append(item.get("created_at", ""))
        writer.writerow(row)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=megazoo_preisvergleich.csv"}
    )


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Gibt die aktuellen Einstellungen zurueck."""
    return jsonify(scraper.get_settings())


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """Aktualisiert die Einstellungen."""
    data = request.get_json()
    scraper.update_settings(data)
    return jsonify({"status": "updated"})


if __name__ == "__main__":
    print("=" * 50)
    print("Megazoo Preisvergleich Tool")
    print("Oeffne http://localhost:5000 im Browser")
    print("=" * 50)
    app.run(debug=True, port=5000)
