from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BookingRequest
from ..emailer import send_email

router = APIRouter(prefix="/booking", tags=["booking"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def booking_form(request: Request):
    return templates.TemplateResponse("booking.html", {"request": request})


@router.post("/", response_class=HTMLResponse)
async def booking_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    requested_datetime: str = Form(...),
    topic: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    booking = BookingRequest(
        name=name,
        email=email,
        requested_datetime=requested_datetime,
        topic=topic,
        notes=notes,
    )
    db.add(booking)
    db.commit()

    send_email(
        subject=f"New booking request: {name}",
        body=f"Name: {name}\nEmail: {email}\nWhen: {requested_datetime}\nTopic: {topic}\n\n{notes}",
    )

    return templates.TemplateResponse(
        "booking_thanks.html", {"request": request, "name": name}
    )
