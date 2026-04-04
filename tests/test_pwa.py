"""Tests for PWA support — manifest, service worker, meta tags."""

import json
import pytest
from pathlib import Path


WEB_DIR = Path(__file__).resolve().parent.parent / "guardian_one" / "web"


class TestPWAManifest:
    """Validate manifest.json for PWA installability."""

    def test_manifest_exists(self):
        manifest_path = WEB_DIR / "static" / "manifest.json"
        assert manifest_path.exists(), "manifest.json must exist in static/"

    def test_manifest_valid_json(self):
        manifest_path = WEB_DIR / "static" / "manifest.json"
        data = json.loads(manifest_path.read_text())
        assert isinstance(data, dict)

    def test_manifest_required_fields(self):
        data = json.loads((WEB_DIR / "static" / "manifest.json").read_text())
        assert "name" in data
        assert "short_name" in data
        assert "start_url" in data
        assert "display" in data
        assert "icons" in data

    def test_manifest_display_standalone(self):
        data = json.loads((WEB_DIR / "static" / "manifest.json").read_text())
        assert data["display"] == "standalone"

    def test_manifest_has_192_and_512_icons(self):
        data = json.loads((WEB_DIR / "static" / "manifest.json").read_text())
        sizes = {icon["sizes"] for icon in data["icons"]}
        assert "192x192" in sizes
        assert "512x512" in sizes

    def test_manifest_icons_exist(self):
        data = json.loads((WEB_DIR / "static" / "manifest.json").read_text())
        for icon in data["icons"]:
            filename = Path(icon["src"]).name
            assert (WEB_DIR / "static" / "icons" / filename).exists(), f"Icon {filename} missing"


class TestServiceWorker:
    """Validate service worker file."""

    def test_sw_exists(self):
        assert (WEB_DIR / "static" / "sw.js").exists()

    def test_sw_has_install_handler(self):
        content = (WEB_DIR / "static" / "sw.js").read_text()
        assert "addEventListener('install'" in content

    def test_sw_has_fetch_handler(self):
        content = (WEB_DIR / "static" / "sw.js").read_text()
        assert "addEventListener('fetch'" in content

    def test_sw_has_activate_handler(self):
        content = (WEB_DIR / "static" / "sw.js").read_text()
        assert "addEventListener('activate'" in content

    def test_sw_caches_root(self):
        content = (WEB_DIR / "static" / "sw.js").read_text()
        assert "'/'," in content or "'/'" in content


class TestPWAMetaTags:
    """Validate panel.html has PWA meta tags."""

    def test_panel_has_manifest_link(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert 'rel="manifest"' in content
        assert "manifest.json" in content

    def test_panel_has_theme_color(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert 'name="theme-color"' in content

    def test_panel_has_apple_meta(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert "apple-mobile-web-app-capable" in content
        assert "apple-touch-icon" in content

    def test_panel_has_sw_registration(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert "serviceWorker.register" in content

    def test_chat_has_manifest_link(self):
        content = (WEB_DIR / "templates" / "chat.html").read_text()
        assert 'rel="manifest"' in content

    def test_chat_has_sw_registration(self):
        content = (WEB_DIR / "templates" / "chat.html").read_text()
        assert "serviceWorker.register" in content


class TestMobileNavigation:
    """Validate mobile navigation support."""

    def test_hamburger_button_exists(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert 'class="hamburger"' in content

    def test_mobile_overlay_exists(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert 'class="mobile-overlay"' in content

    def test_toggle_function_exists(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert "toggleMobileNav" in content

    def test_sidebar_has_id(self):
        content = (WEB_DIR / "templates" / "panel.html").read_text()
        assert 'id="sidebar"' in content


class TestIconFiles:
    """Validate icon PNG files."""

    def test_icon_192_exists(self):
        assert (WEB_DIR / "static" / "icons" / "icon-192.png").exists()

    def test_icon_512_exists(self):
        assert (WEB_DIR / "static" / "icons" / "icon-512.png").exists()

    def test_icon_192_is_png(self):
        data = (WEB_DIR / "static" / "icons" / "icon-192.png").read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n', "icon-192.png must be a valid PNG"

    def test_icon_512_is_png(self):
        data = (WEB_DIR / "static" / "icons" / "icon-512.png").read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n', "icon-512.png must be a valid PNG"
