"""
OfisArama v2 — FastAPI backend
PostgreSQL-backed clean architecture baseline.
"""
import os

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.admin import mount_admin_routes, router as admin_router
from app.api_v1 import router as api_v1_router
from app.config import settings
from app.db import SessionLocal, get_session
from app.models import AdminUser, Lead, Office
from app.security import hash_password
from app.services import (
    get_featured_locations,
    get_locations,
    get_office_by_id,
    get_offices_by_ids,
    get_related_offices,
    search_offices,
)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="OfisArama v2", version="2.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
mount_admin_routes(templates := Jinja2Templates(directory=os.path.join(BASE_DIR, "templates")))
app.include_router(api_v1_router)
app.include_router(admin_router)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def get_compare_ids(request: Request) -> list[int]:
    compare_ids = request.session.get("compare_ids", [])
    cleaned = [office_id for office_id in compare_ids if isinstance(office_id, int)]
    if cleaned != compare_ids:
        request.session["compare_ids"] = cleaned
    return cleaned


def get_favorite_ids(request: Request) -> list[int]:
    favorite_ids = request.session.get("favorite_ids", [])
    cleaned = [office_id for office_id in favorite_ids if isinstance(office_id, int)]
    if cleaned != favorite_ids:
        request.session["favorite_ids"] = cleaned
    return cleaned


def office_compare_rows(offices: list[dict]) -> list[tuple[str, list[str]]]:
    fields = [
        ("Lokasyon", "location"),
        ("Kira", "asking_rent"),
        ("Aidat", "service_charge"),
        ("GLA", "gross_leasable_area"),
        ("Kat Alanı", "floor_size"),
        ("Mülkiyet", "ownership"),
        ("Sertifika", "certificate"),
        ("Teslim Tipi", "delivery_type"),
        ("Yıl", "year_built"),
        ("Kiracılar", "tenants"),
    ]
    rows = []
    for label, key in fields:
        rows.append((label, [office.get(key) or "—" for office in offices]))
    return rows


def ensure_bootstrap_admin() -> None:
    with SessionLocal() as db:
        existing_admin = db.scalar(select(AdminUser).where(AdminUser.email == settings.bootstrap_admin_email))
        if existing_admin:
            return
        db.add(
            AdminUser(
                email=settings.bootstrap_admin_email,
                full_name=settings.bootstrap_admin_name,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role="owner",
                is_active=True,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

ensure_bootstrap_admin()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_session)):
    total = db.scalar(select(func.count()).select_from(Office)) or 0
    locations = get_locations(db)
    featured_locations = get_featured_locations(db)
    curated_searches = [
        {"label": "Levent", "search": "", "location": "LEVENT"},
        {"label": "Maslak", "search": "", "location": "MASLAK"},
        {"label": "Servisli Ofis", "search": "regus", "location": ""},
        {"label": "Sertifikalı Bina", "search": "leed", "location": ""},
        {"label": "Büyük Metrekare", "search": "plaza", "location": ""},
    ]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "total": total,
            "locations": locations,
            "featured_locations": featured_locations,
            "curated_searches": curated_searches,
            "compare_ids": get_compare_ids(request),
            "favorite_ids": get_favorite_ids(request),
        },
    )


@app.get("/sebastian")
async def sebastian_redirect():
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/ofis/{office_id}", response_class=HTMLResponse)
async def office_detail(request: Request, office_id: int, db: Session = Depends(get_session)):
    office, extra_sections = get_office_by_id(db, office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")
    related_offices = get_related_offices(db, office_id, office.get("location"))
    return templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={
            "office": office,
            "extra_sections": extra_sections,
            "related_offices": related_offices,
            "compare_ids": get_compare_ids(request),
            "favorite_ids": get_favorite_ids(request),
            "lead_success": request.query_params.get("lead") == "ok",
            "lead_error": request.query_params.get("lead") == "error",
        },
    )


@app.post("/compare/{office_id}")
async def toggle_compare(
    request: Request,
    office_id: int,
    next_url: str = Form("/"),
):
    compare_ids = get_compare_ids(request)
    if office_id in compare_ids:
        compare_ids = [item for item in compare_ids if item != office_id]
    else:
        compare_ids = (compare_ids + [office_id])[-4:]
    request.session["compare_ids"] = compare_ids
    return RedirectResponse(url=next_url or "/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request, db: Session = Depends(get_session)):
    compare_ids = get_compare_ids(request)
    offices = get_offices_by_ids(db, compare_ids)
    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "offices": offices,
            "compare_ids": compare_ids,
            "compare_rows": office_compare_rows(offices),
        },
    )


@app.post("/favorites/{office_id}")
async def toggle_favorite(
    request: Request,
    office_id: int,
    next_url: str = Form("/"),
):
    favorite_ids = get_favorite_ids(request)
    if office_id in favorite_ids:
        favorite_ids = [item for item in favorite_ids if item != office_id]
    else:
        favorite_ids = (favorite_ids + [office_id])[-24:]
    request.session["favorite_ids"] = favorite_ids
    return RedirectResponse(url=next_url or "/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request, db: Session = Depends(get_session)):
    favorite_ids = get_favorite_ids(request)
    offices = get_offices_by_ids(db, favorite_ids)
    return templates.TemplateResponse(
        request=request,
        name="favorites.html",
        context={
            "offices": offices,
            "favorite_ids": favorite_ids,
            "compare_ids": get_compare_ids(request),
        },
    )


@app.post("/ofis/{office_id}/lead")
async def create_lead(
    office_id: int,
    full_name: str = Form(...),
    email: str = Form(...),
    company: str = Form(""),
    phone: str = Form(""),
    message: str = Form(""),
    db: Session = Depends(get_session),
):
    office = db.get(Office, office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")

    db.add(
        Lead(
            office_id=office_id,
            full_name=full_name.strip(),
            email=email.strip().lower(),
            company=company.strip() or None,
            phone=phone.strip() or None,
            message=message.strip() or None,
            source="website",
            status="new",
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url=f"/ofis/{office_id}?lead=error", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/ofis/{office_id}?lead=ok", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/htmx/offices", response_class=HTMLResponse)
async def htmx_offices(
    request: Request,
    search: str = Query(""),
    location: str = Query(""),
    certificate: str = Query(""),
    ownership: str = Query(""),
    delivery: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
    db: Session = Depends(get_session),
):
    total, offices = search_offices(db, search, location, certificate, ownership, delivery, page, per_page)
    pages = max(1, -(-total // per_page))
    return templates.TemplateResponse(
        request=request,
        name="partials/office_grid.html",
        context={
            "offices": offices,
            "total": total,
            "page": page,
            "pages": pages,
            "search": search,
            "location": location,
            "certificate": certificate,
            "ownership": ownership,
            "delivery": delivery,
        },
    )


@app.get("/api/offices")
async def api_offices(
    search: str = Query(""),
    location: str = Query(""),
    certificate: str = Query(""),
    ownership: str = Query(""),
    delivery: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
    db: Session = Depends(get_session),
):
    total, offices = search_offices(db, search, location, certificate, ownership, delivery, page, per_page)
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
    lead_count = db.scalar(select(func.count()).select_from(Lead)) or 0
    return {
        "total_offices": total,
        "total_locations": location_count,
        "total_leads": lead_count,
    }
