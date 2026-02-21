# Amidala (Company Scaffold) — drjeremytabernero.com

This is a deployable consulting-company website scaffold built for:
- clean brand presence
- contact intake (CV available upon request)
- booking request intake
- payment scaffold (Stripe placeholder)
- admin dashboard
- legal template pack (attorney review required)

## Quickstart (local)
```bash
cd amidala_company
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your secrets
uvicorn app.main:app --reload
```

## Debug / Preview Mode
```bash
python3 debug_preview.py          # dry-run: shows all routes, config, DB schema
python3 debug_preview.py --live   # starts server with debug toolbar at /debug
```

## Project Structure
```
amidala_company/
├── app/
│   ├── __init__.py
│   ├── config.py          # Pydantic settings from .env
│   ├── db.py              # SQLAlchemy engine + session
│   ├── models.py          # Lead, BookingRequest tables
│   ├── emailer.py         # Optional SMTP notifier
│   ├── main.py            # FastAPI app + all routes
│   └── routers/
│       ├── __init__.py
│       ├── contact.py     # /contact
│       ├── booking.py     # /booking
│       ├── payment.py     # /payment (Stripe placeholder)
│       └── admin.py       # /admin (password-protected)
├── templates/             # Jinja2 HTML templates
├── static/                # CSS/JS assets
├── legal/                 # Legal template docs
├── debug_preview.py       # Protected debug/preview runner
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Notes
- All secrets loaded from `.env` — never commit `.env` to git
- Admin dashboard is password-protected via `ADMIN_PASSWORD` in `.env`
- Stripe integration is a placeholder — add your keys to `.env` when ready
- Legal templates require attorney review before use
- Licensed under Apache 2.0
