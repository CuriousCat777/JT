from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import Base, engine
from .routers import contact, booking, payment, admin

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Register routers
app.include_router(contact.router)
app.include_router(booking.router)
app.include_router(payment.router)
app.include_router(admin.router)


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "settings": settings})
