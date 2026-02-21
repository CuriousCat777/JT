from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import settings

router = APIRouter(prefix="/payment", tags=["payment"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def payment_page(request: Request):
    stripe_configured = bool(settings.stripe_secret_key)
    return templates.TemplateResponse(
        "payment.html",
        {"request": request, "stripe_configured": stripe_configured},
    )


@router.get("/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return templates.TemplateResponse("payment_success.html", {"request": request})


@router.get("/cancel", response_class=HTMLResponse)
async def payment_cancel(request: Request):
    return templates.TemplateResponse("payment_cancel.html", {"request": request})
