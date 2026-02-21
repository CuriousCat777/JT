from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Lead
from ..emailer import send_email

router = APIRouter(prefix="/contact", tags=["contact"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def contact_form(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})


@router.post("/", response_class=HTMLResponse)
async def contact_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(""),
    message: str = Form(""),
    cv_requested: str = Form("yes"),
    db: Session = Depends(get_db),
):
    lead = Lead(
        name=name,
        email=email,
        organization=organization,
        message=message,
        cv_requested=cv_requested,
    )
    db.add(lead)
    db.commit()

    send_email(
        subject=f"New contact: {name}",
        body=f"Name: {name}\nEmail: {email}\nOrg: {organization}\n\n{message}",
    )

    return templates.TemplateResponse(
        "contact_thanks.html", {"request": request, "name": name}
    )
