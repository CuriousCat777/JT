import secrets

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Lead, BookingRequest

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

# Simple session tokens (in-memory; resets on restart)
_active_sessions: set[str] = set()


def _require_auth(request: Request):
    token = request.cookies.get("admin_session")
    if not token or token not in _active_sessions:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@router.post("/login")
async def admin_login(password: str = Form(...)):
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin password not configured")
    if not secrets.compare_digest(password, settings.admin_password):
        raise HTTPException(status_code=403, detail="Invalid password")

    token = secrets.token_urlsafe(32)
    _active_sessions.add(token)

    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie("admin_session", token, httponly=True, samesite="strict")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request, _=Depends(_require_auth), db: Session = Depends(get_db)
):
    leads = db.query(Lead).order_by(Lead.created_at.desc()).limit(50).all()
    bookings = (
        db.query(BookingRequest)
        .order_by(BookingRequest.created_at.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "leads": leads, "bookings": bookings},
    )


@router.get("/logout")
async def admin_logout(request: Request):
    token = request.cookies.get("admin_session")
    if token:
        _active_sessions.discard(token)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("admin_session")
    return response
