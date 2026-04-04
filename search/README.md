# Guardian One — Document Search

Two open-source search engines running side-by-side so you can evaluate which fits best.

## Quick Start

### 1. Start the search engines

```bash
cd search/
docker compose up -d
```

This launches:
- **Typesense** on `http://localhost:8108` (API key: `guardian-search-key`)
- **Meilisearch** on `http://localhost:7700` (API key: `guardian-meili-key`)

### 2. Install Python dependencies

```bash
pip install -r search/requirements.txt
```

### 3. Seed sample documents

```bash
python search/seed_documents.py --both
```

Seeds 10 sample clinical/compliance/operational documents into both engines.

### 4. Open the search UI

Open in your browser:
- **Typesense UI**: `search/frontend/typesense-search.html`
- **Meilisearch UI**: `search/frontend/meilisearch-search.html`

Or if running via the Flask dev panel:
- `http://localhost:5100/search/ui/typesense`
- `http://localhost:5100/search/ui/meilisearch`

### 5. Test the API

```bash
# Typesense
curl "http://localhost:5100/search/typesense?q=readmission"

# Meilisearch
curl "http://localhost:5100/search/meilisearch?q=readmission"

# With filters
curl "http://localhost:5100/search/typesense?q=*&category=Compliance%20%26%20Legal"
```

## What's Included

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Runs Typesense 27.1 + Meilisearch 1.12 |
| `seed_documents.py` | Seeds 10 sample docs into both engines |
| `requirements.txt` | Python client libraries |
| `frontend/typesense-search.html` | Full search UI with faceted filters (Typesense) |
| `frontend/meilisearch-search.html` | Full search UI with faceted filters (Meilisearch) |

### Flask Integration

`guardian_one/web/search_routes.py` — Blueprint with:
- `GET /search/typesense?q=...` — JSON search API
- `GET /search/meilisearch?q=...` — JSON search API
- `GET /search/ui/typesense` — Search UI page
- `GET /search/ui/meilisearch` — Search UI page

Register in your Flask app:
```python
from guardian_one.web.search_routes import search_bp
app.register_blueprint(search_bp)
```

## Features Implemented (from Design Spec)

- Full-text search with highlighted snippets
- Faceted filters: category, document type, compliance status, access level, author
- Fuzzy matching / typo tolerance (both engines)
- Cmd/Ctrl+K keyboard shortcut to focus search
- Empty state with helpful suggestions
- Result cards with doc type icons, metadata, compliance badges
- Sort by relevance, date newest, date oldest
- Mobile-responsive layout

## Comparison

| Feature | Typesense | Meilisearch |
|---------|-----------|-------------|
| Typo tolerance | Built-in | Built-in |
| Faceted search | Yes | Yes |
| Self-hosted | Yes | Yes |
| CORS | Configurable | Built-in |
| Speed | ~5ms p99 | ~20ms p50 |
| Best for | Production + compliance | Fast prototyping |

## Stopping

```bash
docker compose down        # Stop engines
docker compose down -v     # Stop + delete data
```
