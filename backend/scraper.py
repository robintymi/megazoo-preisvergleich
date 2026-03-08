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

            # Extract product name from title tag (may have attributes like <title lang="de">)
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ""

            # Fallback: og:title
            if not title:
                og_match = re.search(r'property="og:title"\s+content="([^"]+)"', html)
                title = og_match.group(1).strip() if og_match else ""

            # Fallback: extract name from URL slug
            if not title:
                slug = url.rstrip("/").split("/")[-1]
                title = slug.replace("-", " ")

            # Clean title: remove " | megazoo-shop.de" suffix etc
            title = re.split(r"\s*[\|–]\s*megazoo", title, flags=re.IGNORECASE)[0].strip()

            # Remove trailing price from title (format: "Name, 6,49 €")
            title = re.sub(r",?\s*[\d.,]+\s*[\x80-\xff€]\s*$", "", title).strip()

            # Extract price from dataLayer (Google Tag Manager)
            price_match = re.search(r"['\"]price['\"]:\s*([\d.]+)", html)
            price = float(price_match.group(1)) if price_match else None

            # Extract EAN/GTIN from structured data
            ean_match = re.search(r'itemprop="gtin13"[^>]*>(\d{13})<', html)
            ean = ean_match.group(1) if ean_match else None

            # Fallback: any 13-digit EAN on the page
            if not ean:
                ean13_matches = re.findall(r'\b(\d{13})\b', html)
                ean = ean13_matches[0] if ean13_matches else None

            if not title or price is None or price == 0:
                return None

            result = {
                "name": title,
                "price": round(price, 2),
                "url": url,
            }
            if ean:
                result["ean"] = ean
            return result
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

    def _search_shopping(self, query):
        """Execute a Google Shopping search via SerpAPI."""
        api_key = self.settings.get("serpapi_key", "")
        if not api_key:
            raise ValueError(
                "SerpAPI Key fehlt! Bitte unter Einstellungen einen API-Key eintragen. "
                "Kostenlos: https://serpapi.com (100 Suchen/Monat gratis)"
            )

        params = {
            "engine": "google_shopping",
            "q": query,
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

        return data.get("shopping_results", [])

    def _extract_competitors(self, shopping_results, megazoo_price=None):
        """Extract and filter competitor results."""
        competitors = []
        for item in shopping_results:
            price = self._parse_price(item.get("extracted_price") or item.get("price"))
            if price is None:
                continue

            source = item.get("source", "Unbekannt")
            if "megazoo" in source.lower():
                continue

            # Price tolerance filter: skip results >200% or <20% of megazoo price
            # (likely a different product)
            if megazoo_price and megazoo_price > 0:
                ratio = price / megazoo_price
                if ratio > 3.0 or ratio < 0.2:
                    continue

            competitors.append({
                "title": item.get("title", ""),
                "price": price,
                "source": source,
                "link": item.get("link", ""),
            })

        competitors.sort(key=lambda x: x["price"])
        return competitors[:6]

    def search_competitors(self, product_name, ean=None, megazoo_price=None):
        """Search Google Shopping for competitor prices.
        Strategy: 1) Search by EAN (exact match), 2) Fallback to product name.
        Uses only 1 API call - EAN search if available, otherwise name search.
        """
        # Strategy 1: Search by EAN (most accurate, exact product match)
        if ean:
            results = self._search_shopping(ean)
            competitors = self._extract_competitors(results, megazoo_price)
            if competitors:
                return competitors, "ean"

        # Strategy 2: Search by product name
        results = self._search_shopping(product_name)
        competitors = self._extract_competitors(results, megazoo_price)
        return competitors, "name"

    def compare_product(self, megazoo_product):
        """Compare a single megazoo product with Google Shopping competitors."""
        competitors, search_method = self.search_competitors(
            megazoo_product["name"],
            ean=megazoo_product.get("ean"),
            megazoo_price=megazoo_product.get("price"),
        )

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
            "ean": megazoo_product.get("ean"),
            "search_method": search_method,
            "competitors": competitors,
            "avg_competitor_price": avg_price,
            "deviation_percent": deviation,
            "recommended_price": recommended,
            "competitor_count": len(competitors),
        }
