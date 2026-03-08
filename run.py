"""Start the Megazoo Price Comparison Tool."""
import subprocess
import sys
import os

def install_deps():
    """Install required packages."""
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "-q"])

if __name__ == "__main__":
    print("Installiere Abhaengigkeiten...")
    install_deps()

    # Add backend to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

    from app import app
    app.run(debug=True, port=5000)
