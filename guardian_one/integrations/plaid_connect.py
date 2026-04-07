"""Plaid Link — Local connection server for bank OAuth.

Launches a small local HTTP server that serves the Plaid Link UI.
The user opens their browser, selects their bank, logs in, and Plaid
returns an access token that the CFO agent uses for read-only data pulls.

Usage:
    python main.py --connect               # Start connection flow
    python main.py --connect --port 8234   # Custom port

Security:
    - Server binds to 127.0.0.1 only (never exposed to the network)
    - Only read-only Plaid products are requested (transactions, auth)
    - Access tokens are stored in data/plaid_tokens.json
    - No money movement products are ever requested

Flow:
    1. Server creates a Plaid Link token via API
    2. Serves an HTML page that opens Plaid Link in the browser
    3. User logs into their bank through Plaid's secure UI
    4. Plaid returns a public_token to the server
    5. Server exchanges public_token for a permanent access_token
    6. Access token is saved for the CFO sync loop
"""

from __future__ import annotations

import http.server
import json
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

from guardian_one.integrations.financial_sync import PlaidProvider


# HTML template for the Plaid Link page
_LINK_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>Guardian One — Connect Bank Account</title>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 600px; margin: 80px auto; padding: 20px;
            background: #0a0a0a; color: #e0e0e0;
        }}
        h1 {{ color: #4fc3f7; font-size: 24px; }}
        h2 {{ color: #81c784; font-size: 18px; margin-top: 30px; }}
        .info {{ background: #1a1a2e; padding: 16px; border-radius: 8px; margin: 16px 0; }}
        .security {{ background: #1a2e1a; border-left: 3px solid #4caf50; }}
        .btn {{
            display: inline-block; padding: 14px 28px;
            background: #4fc3f7; color: #000; font-weight: bold;
            border: none; border-radius: 6px; cursor: pointer;
            font-size: 16px; margin-top: 20px;
        }}
        .btn:hover {{ background: #81d4fa; }}
        .btn:disabled {{ background: #555; cursor: not-allowed; }}
        .status {{ margin-top: 20px; padding: 12px; border-radius: 6px; display: none; }}
        .success {{ background: #1a2e1a; border: 1px solid #4caf50; color: #81c784; }}
        .error {{ background: #2e1a1a; border: 1px solid #f44336; color: #ef9a9a; }}
        ul {{ padding-left: 20px; }}
        li {{ margin: 6px 0; }}
    </style>
</head>
<body>
    <h1>Guardian One — Connect Bank Account</h1>

    <div class="info security">
        <strong>Read-Only Access</strong>
        <ul>
            <li>Guardian One only reads account balances and transaction history</li>
            <li>No money transfers, payments, or account changes — ever</li>
            <li>You can disconnect any bank at any time</li>
            <li>Connection runs through Plaid's bank-grade security</li>
        </ul>
    </div>

    <div class="info">
        <strong>What happens next:</strong>
        <ol>
            <li>Click "Connect Bank Account" below</li>
            <li>Select your bank (Bank of America, Wells Fargo, Capital One, etc.)</li>
            <li>Log in with your bank credentials (sent directly to your bank, not to us)</li>
            <li>Guardian One receives read-only access to view your balances</li>
        </ol>
    </div>

    <button class="btn" id="connect-btn" onclick="openPlaidLink()">Connect Bank Account</button>

    <div class="status success" id="success-msg"></div>
    <div class="status error" id="error-msg"></div>

    <h2>Connected Banks</h2>
    <div id="connected-list">
        <em>Loading...</em>
    </div>

    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <script>
        const LINK_TOKEN = "{link_token}";

        function openPlaidLink() {{
            const handler = Plaid.create({{
                token: LINK_TOKEN,
                onSuccess: function(public_token, metadata) {{
                    // Send to our local server
                    fetch('/exchange', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            public_token: public_token,
                            institution_id: metadata.institution.institution_id,
                            institution_name: metadata.institution.name,
                        }})
                    }})
                    .then(r => r.json())
                    .then(data => {{
                        if (data.success) {{
                            document.getElementById('success-msg').style.display = 'block';
                            document.getElementById('success-msg').textContent =
                                'Connected: ' + data.institution + ' — You can close this tab.';
                            loadConnected();
                        }} else {{
                            document.getElementById('error-msg').style.display = 'block';
                            document.getElementById('error-msg').textContent = 'Error: ' + data.error;
                        }}
                    }});
                }},
                onExit: function(err) {{
                    if (err) {{
                        document.getElementById('error-msg').style.display = 'block';
                        document.getElementById('error-msg').textContent = 'Cancelled or error: ' + err.display_message;
                    }}
                }},
            }});
            handler.open();
        }}

        function loadConnected() {{
            fetch('/status')
                .then(r => r.json())
                .then(data => {{
                    const list = document.getElementById('connected-list');
                    if (data.institutions && data.institutions.length > 0) {{
                        list.innerHTML = '<ul>' + data.institutions.map(i =>
                            '<li><strong>' + i.name + '</strong> — connected ' + i.connected_at.split('T')[0] + '</li>'
                        ).join('') + '</ul>';
                    }} else {{
                        list.innerHTML = '<em>No banks connected yet.</em>';
                    }}
                }});
        }}

        loadConnected();
    </script>
</body>
</html>"""


class PlaidLinkHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the Plaid Link local server."""

    plaid: PlaidProvider
    link_token: str

    def log_message(self, fmt: str, *args: Any) -> None:
        # Suppress default logging
        pass

    def do_GET(self) -> None:
        if self.path == "/":
            self._serve_link_page()
        elif self.path == "/status":
            self._serve_json(self.plaid.status())
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/exchange":
            self._handle_exchange()
        else:
            self.send_error(404)

    def _serve_link_page(self) -> None:
        html = _LINK_PAGE.format(link_token=self.link_token)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_json(self, data: dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _handle_exchange(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._serve_json({"success": False, "error": "Invalid Content-Length"})
            return
        if length > 1_000_000:  # 1 MB max
            self._serve_json({"success": False, "error": "Request body too large"})
            return
        body = json.loads(self.rfile.read(length)) if length else {}

        public_token = body.get("public_token", "")
        inst_id = body.get("institution_id", "")
        inst_name = body.get("institution_name", "")

        if not public_token:
            self._serve_json({"success": False, "error": "Missing public_token"})
            return

        result = self.plaid.exchange_public_token(public_token, inst_id, inst_name)
        self._serve_json(result)


def run_plaid_link_server(
    plaid: PlaidProvider,
    port: int = 8234,
    open_browser: bool = True,
) -> dict[str, Any]:
    """Start the Plaid Link local server and open the browser.

    Returns status dict when the server is shut down (Ctrl+C).
    """
    if not plaid.has_credentials:
        return {
            "success": False,
            "error": "Set PLAID_CLIENT_ID and PLAID_SECRET in .env first. "
                     "Get them free at https://dashboard.plaid.com/signup",
        }

    # Create link token
    link_result = plaid.create_link_token()
    if not link_result.get("success"):
        return {
            "success": False,
            "error": f"Failed to create link token: {link_result.get('error', 'unknown')}",
        }

    # Configure handler class
    PlaidLinkHandler.plaid = plaid
    PlaidLinkHandler.link_token = link_result["link_token"]

    server = http.server.HTTPServer(("127.0.0.1", port), PlaidLinkHandler)
    url = f"http://127.0.0.1:{port}"

    print(f"\n  Plaid Link server running at {url}")
    print(f"  Opening browser for bank connection...")
    print(f"  Press Ctrl+C when done connecting banks.\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

    connected = plaid.connected_institutions
    print(f"\n  Connected {len(connected)} institution(s).")
    return {
        "success": True,
        "connected": len(connected),
        "institutions": [
            plaid._item_metadata.get(i, {}).get("institution_name", i)
            for i in connected
        ],
    }
