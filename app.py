"""Vercel + local entrypoint for the Megazoo Price Comparison Tool."""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from backend.app import app

if __name__ == "__main__":
    app.run(debug=True, port=5000)
