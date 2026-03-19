"""
OfisArama v2 — FastAPI backend
PostgreSQL-backed clean architecture baseline.
"""
import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_v1 import router as api_v1_router
from app.db import Base, engine, get_session
from app.models import Office
from app.services import get_locations, get_office_by_id, search_offices


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="OfisArama v2", version="2.0.0")
app.include_router(api_v1_router)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_session)):
    total = db.scalar(select(func.count()).select_from(Office)) or 0
    locations = get_locations(db)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "total": total,
            "locations": locations,
        },
    )


@app.get("/ofis/{office_id}", response_class=HTMLResponse)
async def office_detail(request: Request, office_id: int, db: Session = Depends(get_session)):
    office, extra_sections = get_office_by_id(db, office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")
    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "office": office,
            "extra_sections": extra_sections,
        },
    )


@app.get("/htmx/offices", response_class=HTMLResponse)
async def htmx_offices(
    request: Request,
    search: str = Query(""),
    location: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
    db: Session = Depends(get_session),
):
    total, offices = search_offices(db, search, location, page, per_page)
    pages = max(1, -(-total // per_page))
    return templates.TemplateResponse(
        "partials/office_grid.html",
        {
            "request": request,
            "offices": offices,
            "total": total,
            "page": page,
            "pages": pages,
            "search": search,
            "location": location,
        },
    )


@app.get("/api/offices")
async def api_offices(
    search: str = Query(""),
    location: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
    db: Session = Depends(get_session),
):
    total, offices = search_offices(db, search, location, page, per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),
        "offices": offices,
    }


@app.get("/api/offices/{office_id}")
async def api_office_detail(office_id: int, db: Session = Depends(get_session)):
    office, extra_sections = get_office_by_id(db, office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")
    return {"office": office, "extras": extra_sections}


@app.get("/api/locations")
async def api_locations(db: Session = Depends(get_session)):
    return get_locations(db)


@app.get("/api/stats")
async def api_stats(db: Session = Depends(get_session)):
    total = db.scalar(select(func.count()).select_from(Office)) or 0
    location_count = db.scalar(select(func.count(func.distinct(Office.location)))) or 0
    return {"total_offices": total, "total_locations": location_count}
