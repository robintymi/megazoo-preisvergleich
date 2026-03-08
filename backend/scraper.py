"""
Megazoo Product Crawler + Google Shopping Price Comparison.
- Crawls megazoo-shop.de sitemap to get all products & prices
- Compares each product via SerpAPI Google Shopping (Free Tier: 100/month)
"""

import os
import json
import re
import gzip
import time
import requests
from io import BytesIO
from xml.etree import ElementTree as ET

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")
PRODUCTS_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "megazoo_products.json")

DEFAULT_SETTINGS = {
    "serpapi_key": "",
    "country": "de",
    "language": "de",
    "price_deviation_target": 0.97,
    "batch_size": 20,
    "delay_between_requests": 2,
}

SITEMAP_INDEX_URL = "https://www.megazoo-shop.de/sitemap_index.xml"
MEGAZOO_BASE = "https://www.megazoo-shop.de"


class MegazooCrawler:
    """Crawls megazoo-shop.de to get all products and their prices."""

    def get_product_urls_from_sitemap(self):
        """Fetch all product URLs from sitemap."""
        # First get sitemap index
        resp = requests.get(SITEMAP_INDEX_URL, timeout=30)
        resp.raise_for_status()

        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        root = ET.fromstring(resp.content)
        sitemap_urls = [loc.text for loc in root.findall(".//ns:loc", ns)]

        product_urls = []
        for sitemap_url in sitemap_urls:
            resp = requests.get(sitemap_url, timeout=30)
            resp.raise_for_status()

            # Handle gzipped content
            if sitemap_url.endswith(".gz"):
                content = gzip.decompress(resp.content)
            else:
                content = resp.content

            root = ET.fromstring(content)
            for url_elem in root.findall(".//ns:loc", ns):
                url = url_elem.text
                # Skip homepage and category pages (products have specific patterns)
                if url and url != MEGAZOO_BASE + "/" and not url.endswith("/"):
                    product_urls.append(url)

        return product_urls

    def scrape_product_price(self, url):
        """Scrape price from a single megazoo product page via dataLayer."""
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                return None

            html = resp.text

            # Extract product name from title tag
            title_match = re.search(r"<title>([^<]+)</title>", html)
            title = title_match.group(1).strip() if title_match else ""
            # Clean title: remove " | megazoo-shop.de" suffix etc
            title = re.split(r"\s*[\|–-]\s*megazoo", title, flags=re.IGNORECASE)[0].strip()

            # Extract price from dataLayer (Google Tag Manager)
            # Pattern: 'price': 6.49 or "price": 6.49
            price_match = re.search(r"['\"]price['\"]:\s*([\d.]+)", html)
            price = float(price_match.group(1)) if price_match else None

            # Also try to get price from the page title format "Name, 6,49 €"
            if price is None:
                title_price = re.search(r"([\d.,]+)\s*€", title)
                if title_price:
                    price_str = title_price.group(1).replace(".", "").replace(",", ".")
                    try:
                        price = float(price_str)
                        # Remove price from title
                        title = re.sub(r",?\s*[\d.,]+\s*€", "", title).strip()
                    except ValueError:
                        pass

            # Remove trailing price from title if present
            title = re.sub(r",?\s*[\d.,]+\s*€\s*$", "", title).strip()

            if not title or price is None:
                return None

            return {
                "name": title,
                "price": round(price, 2),
                "url": url,
            }
        except Exception:
            return None

    def crawl_all_products(self, progress_callback=None):
        """Crawl all products from megazoo-shop.de. Returns list of products."""
        urls = self.get_product_urls_from_sitemap()

        products = []
        total = len(urls)

        for i, url in enumerate(urls):
            product = self.scrape_product_price(url)
            if product:
                products.append(product)

            if progress_callback:
                progress_callback(i + 1, total, len(products))

            # Small delay to be polite
            if i % 10 == 0 and i > 0:
                time.sleep(0.5)

        # Cache products
        self._save_products_cache(products)
        return products

    def _save_products_cache(self, products):
        os.makedirs(os.path.dirname(PRODUCTS_CACHE_PATH), exist_ok=True)
        with open(PRODUCTS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "products": products,
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(products),
            }, f, indent=2, ensure_ascii=False)

    def load_products_cache(self):
        if os.path.exists(PRODUCTS_CACHE_PATH):
            with open(PRODUCTS_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return None


class GoogleShoppingScraper:
    """Searches Google Shopping via SerpAPI for price comparisons."""

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
        if settings.get("serpapi_key"):
            key = settings["serpapi_key"]
            settings["serpapi_key_masked"] = key[:4] + "..." + key[-4:] if len(key) > 8 else "****"
        else:
            settings["serpapi_key_masked"] = ""
        return settings

    def update_settings(self, new_settings):
        for key in ["serpapi_key", "country", "language"]:
            if key in new_settings:
                self.settings[key] = new_settings[key]
        if "batch_size" in new_settings:
            self.settings["batch_size"] = int(new_settings["batch_size"])
        if "price_deviation_target" in new_settings:
            self.settings["price_deviation_target"] = float(new_settings["price_deviation_target"])
        self._save_settings()

    def _parse_price(self, price_str):
        """Parse price string like '12,99 €' or '$12.99' to float."""
        if not price_str:
            return None
        cleaned = re.sub(r"[€$£\s]", "", str(price_str))
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return round(float(cleaned), 2)
        except (ValueError, TypeError):
            return None

    def search_competitors(self, product_name):
        """Search Google Shopping for competitor prices for a product."""
        api_key = self.settings.get("serpapi_key", "")
        if not api_key:
            raise ValueError(
                "SerpAPI Key fehlt! Bitte unter Einstellungen einen API-Key eintragen. "
                "Kostenlos: https://serpapi.com (100 Suchen/Monat gratis)"
            )

        params = {
            "engine": "google_shopping",
            "q": product_name,
            "gl": self.settings.get("country", "de"),
            "hl": self.settings.get("language", "de"),
            "api_key": api_key,
            "num": 20,
        }

        response = requests.get("https://serpapi.com/search", params=params, timeout=30)

        if response.status_code == 401:
            raise ValueError("Ungueltiger SerpAPI Key.")
        elif response.status_code == 429:
            raise ValueError("SerpAPI Rate-Limit erreicht. Spaeter erneut versuchen.")
        elif response.status_code != 200:
            raise ValueError(f"SerpAPI Fehler: HTTP {response.status_code}")

        data = response.json()
        if "error" in data:
            raise ValueError(f"SerpAPI: {data['error']}")

        shopping_results = data.get("shopping_results", [])

        competitors = []
        for item in shopping_results:
            price = self._parse_price(item.get("extracted_price") or item.get("price"))
            if price is None:
                continue

            source = item.get("source", "Unbekannt")
            # Skip megazoo results
            if "megazoo" in source.lower():
                continue

            competitors.append({
                "title": item.get("title", ""),
                "price": price,
                "source": source,
                "link": item.get("link", ""),
            })

        # Sort by price
        competitors.sort(key=lambda x: x["price"])
        return competitors[:6]

    def compare_product(self, megazoo_product):
        """Compare a single megazoo product with Google Shopping competitors."""
        competitors = self.search_competitors(megazoo_product["name"])

        competitor_prices = [c["price"] for c in competitors]
        avg_price = round(sum(competitor_prices) / len(competitor_prices), 2) if competitor_prices else None

        megazoo_price = megazoo_product["price"]
        deviation = None
        recommended = None

        if avg_price:
            deviation = round(((megazoo_price - avg_price) / avg_price) * 100, 1)
            target = self.settings.get("price_deviation_target", 0.97)
            recommended = round(avg_price * target, 2)

        return {
            "product_name": megazoo_product["name"],
            "megazoo_price": megazoo_price,
            "megazoo_url": megazoo_product["url"],
            "competitors": competitors,
            "avg_competitor_price": avg_price,
            "deviation_percent": deviation,
            "recommended_price": recommended,
            "competitor_count": len(competitors),
        }
