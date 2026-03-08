"""
SQLite Database for storing price comparisons.
"""

import sqlite3
import json
import os
from datetime import datetime

# On Vercel (serverless), use /tmp for writable storage
if os.environ.get("VERCEL"):
    DATA_DIR = "/tmp/data"
else:
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

DB_PATH = os.path.join(DATA_DIR, "comparisons.db")


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                megazoo_price REAL,
                megazoo_url TEXT,
                ean TEXT,
                search_method TEXT,
                competitors_json TEXT,
                avg_competitor_price REAL,
                deviation_percent REAL,
                recommended_price REAL,
                competitor_count INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def save_comparison(self, comparison):
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO comparisons
            (product_name, megazoo_price, megazoo_url, ean, search_method,
             competitors_json, avg_competitor_price, deviation_percent,
             recommended_price, competitor_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comparison["product_name"],
            comparison.get("megazoo_price"),
            comparison.get("megazoo_url"),
            comparison.get("ean"),
            comparison.get("search_method"),
            json.dumps(comparison.get("competitors", []), ensure_ascii=False),
            comparison.get("avg_competitor_price"),
            comparison.get("deviation_percent"),
            comparison.get("recommended_price"),
            comparison.get("competitor_count"),
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()

    def get_history(self, limit=200):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM comparisons ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()

        results = []
        for row in rows:
            item = dict(row)
            item["competitors"] = json.loads(item.get("competitors_json", "[]"))
            del item["competitors_json"]
            results.append(item)
        return results

    def delete_comparison(self, comparison_id):
        conn = self._get_conn()
        conn.execute("DELETE FROM comparisons WHERE id = ?", (comparison_id,))
        conn.commit()
        conn.close()

    def clear_all(self):
        conn = self._get_conn()
        conn.execute("DELETE FROM comparisons")
        conn.commit()
        conn.close()
