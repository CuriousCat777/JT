"""Guardian One — Document Search API routes.

Provides Flask blueprint with search endpoints backed by
Typesense and/or Meilisearch. Register with the main app:

    from guardian_one.web.search_routes import search_bp
    app.register_blueprint(search_bp)
"""

from __future__ import annotations

import os
from flask import Blueprint, jsonify, request, render_template

search_bp = Blueprint("search", __name__, url_prefix="/search")

# ── Engine config (env-overridable) ─────────────────────────
TYPESENSE_HOST = os.getenv("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT = os.getenv("TYPESENSE_PORT", "8108")
TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "guardian-search-key")
# Search-only key for browser clients (scoped, no write/admin access)
TYPESENSE_SEARCH_KEY = os.getenv("TYPESENSE_SEARCH_KEY", TYPESENSE_API_KEY)

MEILI_HOST = os.getenv("MEILI_HOST", "http://localhost:7700")
MEILI_API_KEY = os.getenv("MEILI_API_KEY", "guardian-meili-key")
# Search-only key for browser clients (never expose master key to browser)
MEILI_SEARCH_KEY = os.getenv("MEILI_SEARCH_KEY", MEILI_API_KEY)


def _get_typesense_client():
    import typesense
    return typesense.Client({
        "api_key": TYPESENSE_API_KEY,
        "nodes": [{"host": TYPESENSE_HOST, "port": TYPESENSE_PORT, "protocol": "http"}],
        "connection_timeout_seconds": 5,
    })


def _get_meili_client():
    import meilisearch
    return meilisearch.Client(MEILI_HOST, MEILI_API_KEY)


# ── Typesense search endpoint ──────────────────────────────
@search_bp.route("/typesense", methods=["GET"])
def search_typesense():
    """Search via Typesense. Query params: q, category, doc_type, page, per_page."""
    q = request.args.get("q", "*")
    category = request.args.get("category", "")
    doc_type = request.args.get("doc_type", "")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(100, int(request.args.get("per_page", 10))))
    except (ValueError, TypeError):
        per_page = 10

    filter_by = []
    if category:
        safe_cat = category.replace("`", "").replace("\\", "")
        filter_by.append(f"category:=`{safe_cat}`")
    if doc_type:
        safe_dt = doc_type.replace("`", "").replace("\\", "")
        filter_by.append(f"doc_type:=`{safe_dt}`")

    try:
        client = _get_typesense_client()
        results = client.collections["documents"].documents.search({
            "q": q,
            "query_by": "title,content,author,tags",
            "filter_by": " && ".join(filter_by) if filter_by else "",
            "sort_by": "_text_match:desc",
            "page": page,
            "per_page": per_page,
            "highlight_full_fields": "title,content",
        })
        return jsonify({
            "engine": "typesense",
            "found": results["found"],
            "page": results["page"],
            "hits": [
                {
                    "id": h["document"]["id"],
                    "title": h["document"]["title"],
                    "author": h["document"]["author"],
                    "category": h["document"]["category"],
                    "doc_type": h["document"]["doc_type"],
                    "compliance_status": h["document"]["compliance_status"],
                    "date_modified": h["document"]["date_modified"],
                    "snippet": h.get("highlights", [{}])[0].get("snippet", "")
                    if h.get("highlights") else "",
                }
                for h in results["hits"]
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Meilisearch search endpoint ────────────────────────────
@search_bp.route("/meilisearch", methods=["GET"])
def search_meilisearch():
    """Search via Meilisearch. Query params: q, category, doc_type, page, per_page."""
    q = request.args.get("q", "")
    category = request.args.get("category", "")
    doc_type = request.args.get("doc_type", "")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(100, int(request.args.get("per_page", 10))))
    except (ValueError, TypeError):
        per_page = 10

    filters = []
    if category:
        filters.append(f'category = "{category}"')
    if doc_type:
        filters.append(f'doc_type = "{doc_type}"')

    try:
        client = _get_meili_client()
        results = client.index("documents").search(q, {
            "filter": " AND ".join(filters) if filters else None,
            "limit": per_page,
            "offset": (page - 1) * per_page,
            "attributesToHighlight": ["title", "content"],
            "attributesToCrop": ["content"],
            "cropLength": 60,
        })
        return jsonify({
            "engine": "meilisearch",
            "found": results.get("estimatedTotalHits", 0),
            "page": page,
            "hits": [
                {
                    "id": h["id"],
                    "title": h["title"],
                    "author": h["author"],
                    "category": h["category"],
                    "doc_type": h["doc_type"],
                    "compliance_status": h["compliance_status"],
                    "date_modified": h["date_modified"],
                    "snippet": h.get("_formatted", {}).get("content", ""),
                }
                for h in results["hits"]
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── UI routes ──────────────────────────────────────────────
@search_bp.route("/ui/typesense")
def ui_typesense():
    """Serve the Typesense search UI."""
    return render_template("search/typesense.html",
                           typesense_host=TYPESENSE_HOST,
                           typesense_port=TYPESENSE_PORT,
                           typesense_api_key=TYPESENSE_SEARCH_KEY)


@search_bp.route("/ui/meilisearch")
def ui_meilisearch():
    """Serve the Meilisearch search UI."""
    return render_template("search/meilisearch.html",
                           meili_host=MEILI_HOST,
                           meili_api_key=MEILI_SEARCH_KEY)
