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
from app.services import get_locations, get_office_by_id, search_offices


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="OfisArama v2", version="2.1.0")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
mount_admin_routes(templates := Jinja2Templates(directory=os.path.join(BASE_DIR, "templates")))
app.include_router(api_v1_router)
app.include_router(admin_router)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


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
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "total": total,
            "locations": locations,
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
    return templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={
            "office": office,
            "extra_sections": extra_sections,
            "lead_success": request.query_params.get("lead") == "ok",
            "lead_error": request.query_params.get("lead") == "error",
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
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
    db: Session = Depends(get_session),
):
    total, offices = search_offices(db, search, location, page, per_page)
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
    lead_count = db.scalar(select(func.count()).select_from(Lead)) or 0
    return {
        "total_offices": total,
        "total_locations": location_count,
        "total_leads": lead_count,
    }
