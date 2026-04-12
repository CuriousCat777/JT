"""Entry point for the Archivist agent sandbox."""

import sys
from pathlib import Path

# Ensure the package is importable when running from ai-sandbox/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from archivist_agent.api.app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
