#!/usr/bin/env python3
"""
Amidala Scaffold — Protected Debug & Preview Tool

Usage:
    python3 debug_preview.py            # Dry-run: inspect config, routes, DB schema
    python3 debug_preview.py --live     # Start server with /debug introspection endpoint

This script lets you safely inspect the application without modifying data.
All sensitive values (passwords, keys) are masked in output.
"""

import argparse
import importlib
import os
import sys
import textwrap


def mask(value: str) -> str:
    """Mask a sensitive string, showing only first 3 chars."""
    if not value:
        return "(not set)"
    if len(value) <= 4:
        return "****"
    return value[:3] + "*" * (len(value) - 3)


def dry_run():
    """Print a complete diagnostic report without starting the server."""
    print("=" * 60)
    print("  AMIDALA SCAFFOLD — DEBUG PREVIEW (dry-run)")
    print("=" * 60)

    # --- 1. Environment / Config ---
    print("\n[1] CONFIGURATION (.env)")
    print("-" * 40)
    try:
        from app.config import settings
        safe_fields = ["app_name", "base_url", "smtp_port",
                       "stripe_success_url", "stripe_cancel_url"]
        secret_fields = ["admin_password", "smtp_host", "smtp_user",
                         "smtp_pass", "smtp_from", "smtp_to",
                         "stripe_secret_key"]
        for f in safe_fields:
            print(f"  {f}: {getattr(settings, f, '?')}")
        for f in secret_fields:
            print(f"  {f}: {mask(getattr(settings, f, ''))}")
    except Exception as e:
        print(f"  ERROR loading config: {e}")

    # --- 2. Database Schema ---
    print("\n[2] DATABASE SCHEMA")
    print("-" * 40)
    try:
        from app.db import Base, engine
        from app.models import Lead, BookingRequest
        print("  Tables defined:")
        for table_name, table in Base.metadata.tables.items():
            cols = ", ".join(c.name for c in table.columns)
            print(f"    {table_name}: [{cols}]")
        print(f"  Engine URL: {engine.url}")
        print("  Note: Tables are created on app startup (create_all)")
    except Exception as e:
        print(f"  ERROR loading models: {e}")

    # --- 3. Routes ---
    print("\n[3] REGISTERED ROUTES")
    print("-" * 40)
    try:
        from app.main import app
        for route in app.routes:
            methods = getattr(route, "methods", None)
            path = getattr(route, "path", getattr(route, "path_regex", "?"))
            if methods:
                for m in sorted(methods):
                    print(f"  {m:6s} {path}")
    except Exception as e:
        print(f"  ERROR loading app: {e}")

    # --- 4. File inventory ---
    print("\n[4] FILE INVENTORY")
    print("-" * 40)
    count = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__", ".git")]
        for f in sorted(files):
            rel = os.path.join(root, f)
            size = os.path.getsize(rel)
            print(f"  {rel:50s} ({size:,} bytes)")
            count += 1
    print(f"  Total: {count} files")

    # --- 5. Dependency check ---
    print("\n[5] DEPENDENCY CHECK")
    print("-" * 40)
    deps = ["fastapi", "uvicorn", "jinja2", "pydantic", "pydantic_settings",
            "sqlalchemy", "dotenv", "multipart"]
    pkg_map = {"dotenv": "dotenv", "multipart": "multipart"}
    for dep in deps:
        mod_name = pkg_map.get(dep, dep)
        try:
            mod = importlib.import_module(mod_name)
            ver = getattr(mod, "__version__", "installed")
            print(f"  {dep:25s} {ver}")
        except ImportError:
            print(f"  {dep:25s} MISSING — run: pip install -r requirements.txt")

    # --- 6. Security notes ---
    print("\n[6] SECURITY CHECKLIST")
    print("-" * 40)
    checks = []
    try:
        from app.config import settings as s
        if not s.admin_password:
            checks.append("WARNING: ADMIN_PASSWORD is empty — admin login disabled")
        if s.base_url.startswith("http://") and "127.0.0.1" not in s.base_url:
            checks.append("WARNING: BASE_URL uses HTTP on non-localhost — use HTTPS")
    except Exception:
        pass
    if os.path.exists(".env"):
        checks.append("OK: .env file exists")
    else:
        checks.append("INFO: No .env file — copy .env.example to .env")
    if os.path.exists(".gitignore"):
        gi = open(".gitignore").read()
        if ".env" in gi:
            checks.append("OK: .env is in .gitignore")
        else:
            checks.append("WARNING: .env NOT in .gitignore — secrets may leak")
    for c in checks:
        print(f"  {c}")

    print("\n" + "=" * 60)
    print("  Dry-run complete. No data was modified.")
    print("=" * 60)


def live_server():
    """Start uvicorn with a /debug introspection endpoint injected."""
    try:
        from app.main import app
        from app.config import settings
        from fastapi import Request
        from fastapi.responses import JSONResponse

        @app.get("/debug", tags=["debug"])
        async def debug_endpoint(request: Request):
            """Protected introspection endpoint — visible only in debug mode."""
            from app.db import Base
            routes = []
            for route in app.routes:
                methods = getattr(route, "methods", None)
                path = getattr(route, "path", "?")
                if methods:
                    routes.append({"methods": sorted(methods), "path": path})
            return JSONResponse({
                "app_name": settings.app_name,
                "base_url": settings.base_url,
                "admin_configured": bool(settings.admin_password),
                "smtp_configured": bool(settings.smtp_host),
                "stripe_configured": bool(settings.stripe_secret_key),
                "tables": list(Base.metadata.tables.keys()),
                "routes": routes,
            })

        print("Starting Amidala in DEBUG mode...")
        print("Debug endpoint available at: http://127.0.0.1:8000/debug")
        print("Press Ctrl+C to stop.\n")

        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8000)

    except ImportError as e:
        print(f"Cannot start live server — missing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amidala Scaffold Debug Tool")
    parser.add_argument("--live", action="store_true",
                        help="Start the server with /debug endpoint")
    args = parser.parse_args()

    # Ensure we're in the project directory
    if not os.path.exists("app/main.py"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)

    if args.live:
        live_server()
    else:
        dry_run()
