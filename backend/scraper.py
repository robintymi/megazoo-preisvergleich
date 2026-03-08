"""
Google Shopping Scraper using SerpAPI (Free Tier: 100 searches/month).
"""

import os
import json
import re
import time
import requests

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")

DEFAULT_SETTINGS = {
    "serpapi_key": "",
    "country": "de",
    "language": "de",
    "price_deviation_target": 0.97,  # 3% unter Durchschnitt
}


class GoogleShoppingScraper:
    def __init__(self):
        self.settings = self._load_settings()

    def _load_settings(self):
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                return {**DEFAULT_SETTINGS, **saved}
        return DEFAULT_SETTINGS.copy()

    def _save_settings(self):
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)

    def get_settings(self):
        settings = self.settings.copy()
        # Mask API key for security
        if settings.get("serpapi_key"):
            key = settings["serpapi_key"]
            settings["serpapi_key_masked"] = key[:4] + "..." + key[-4:] if len(key) > 8 else "****"
        else:
            settings["serpapi_key_masked"] = ""
        return settings

    def update_settings(self, new_settings):
        if "serpapi_key" in new_settings:
            self.settings["serpapi_key"] = new_settings["serpapi_key"]
        if "country" in new_settings:
            self.settings["country"] = new_settings["country"]
        if "language" in new_settings:
            self.settings["language"] = new_settings["language"]
        if "price_deviation_target" in new_settings:
            self.settings["price_deviation_target"] = float(new_settings["price_deviation_target"])
        self._save_settings()

    def _parse_price(self, price_str):
        """Parse price string like '12,99 €' or '$12.99' to float."""
        if not price_str:
            return None
        # Remove currency symbols and whitespace
        cleaned = re.sub(r"[€$£\s]", "", str(price_str))
        # Handle German format (comma as decimal separator)
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return round(float(cleaned), 2)
        except (ValueError, TypeError):
            return None

    def search(self, product_name):
        """Search Google Shopping for a product via SerpAPI."""
        api_key = self.settings.get("serpapi_key", "")

        if not api_key:
            raise ValueError(
                "SerpAPI Key fehlt! Bitte unter Einstellungen einen API-Key eintragen. "
                "Kostenlos registrieren auf: https://serpapi.com (100 Suchen/Monat gratis)"
            )

        params = {
            "engine": "google_shopping",
            "q": product_name,
            "gl": self.settings.get("country", "de"),
            "hl": self.settings.get("language", "de"),
            "api_key": api_key,
            "num": 30,
        }

        response = requests.get("https://serpapi.com/search", params=params, timeout=30)

        if response.status_code == 401:
            raise ValueError("Ungueltiger SerpAPI Key. Bitte Key pruefen.")
        elif response.status_code == 429:
            raise ValueError("SerpAPI Rate-Limit erreicht. Bitte spaeter erneut versuchen.")
        elif response.status_code != 200:
            raise ValueError(f"SerpAPI Fehler: HTTP {response.status_code}")

        data = response.json()

        if "error" in data:
            raise ValueError(f"SerpAPI: {data['error']}")

        shopping_results = data.get("shopping_results", [])

        results = []
        for item in shopping_results:
            price = self._parse_price(item.get("extracted_price") or item.get("price"))
            if price is None:
                continue

            results.append({
                "title": item.get("title", ""),
                "price": price,
                "source": item.get("source", "Unbekannt"),
                "link": item.get("link", ""),
                "thumbnail": item.get("thumbnail", ""),
                "rating": item.get("rating"),
                "reviews": item.get("reviews"),
            })

        return results
