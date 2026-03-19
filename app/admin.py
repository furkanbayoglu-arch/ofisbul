from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AdminUser, AuditLog, Lead, Office
from app.security import verify_password
from app.services import normalize


router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_user(request: Request, db: Session) -> AdminUser | None:
    admin_user_id = request.session.get("admin_user_id")
    if not admin_user_id:
        return None
    return db.get(AdminUser, admin_user_id)


def log_admin_action(db: Session, admin_user: AdminUser, action: str, entity_type: str, entity_id: int | None):
    db.add(
        AuditLog(
            admin_user_id=admin_user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )
    db.commit()


def parse_optional_float(raw_value: str) -> float | None:
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned.replace(",", "."))
    except ValueError:
        return None


def mount_admin_routes(templates: Jinja2Templates) -> None:
    @router.get("/login", response_class=HTMLResponse)
    async def admin_login_page(request: Request, db: Session = Depends(get_session)):
        admin_user = get_admin_user(request, db)
        if admin_user and admin_user.is_active:
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "error": None,
            },
        )

    @router.post("/login", response_class=HTMLResponse)
    async def admin_login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_session),
    ):
        admin_user = db.scalar(select(AdminUser).where(AdminUser.email == email.strip().lower()))
        if not admin_user or not admin_user.is_active or not verify_password(password, admin_user.password_hash):
            return templates.TemplateResponse(
                "admin/login.html",
                {
                    "request": request,
                    "error": "E-posta veya sifre hatali.",
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        admin_user.last_login_at = datetime.now(timezone.utc)
        db.add(admin_user)
        db.commit()
        request.session["admin_user_id"] = admin_user.id
        log_admin_action(db, admin_user, "login", "admin_user", admin_user.id)
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/logout")
    async def admin_logout(request: Request, db: Session = Depends(get_session)):
        admin_user = get_admin_user(request, db)
        if admin_user:
            log_admin_action(db, admin_user, "logout", "admin_user", admin_user.id)
        request.session.clear()
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    @router.get("", response_class=HTMLResponse)
    async def admin_dashboard(request: Request, db: Session = Depends(get_session)):
        admin_user = get_admin_user(request, db)
        if not admin_user or not admin_user.is_active:
            return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
        recent_leads = db.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(20)).all()
        recent_logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)).all()
        office_count = db.scalar(select(func.count()).select_from(Office)) or 0
        return templates.TemplateResponse(
            "admin/dashboard.html",
            {
                "request": request,
                "admin_user": admin_user,
                "recent_leads": recent_leads,
                "recent_logs": recent_logs,
                "office_count": office_count,
            },
        )

    @router.get("/offices", response_class=HTMLResponse)
    async def admin_offices(
        request: Request,
        q: str = "",
        page: int = 1,
        db: Session = Depends(get_session),
    ):
        admin_user = get_admin_user(request, db)
        if not admin_user or not admin_user.is_active:
            return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

        stmt = select(Office)
        if q.strip():
            term = f"%{normalize(q.strip())}%"
            from app.services import normalized_column
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    normalized_column(Office.name).like(term),
                    normalized_column(Office.location).like(term),
                    normalized_column(Office.tenants).like(term),
                )
            )

        per_page = 25
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        offices = db.scalars(
            stmt.order_by(Office.name.asc()).offset((page - 1) * per_page).limit(per_page)
        ).all()
        pages = max(1, -(-total // per_page))

        return templates.TemplateResponse(
            "admin/offices.html",
            {
                "request": request,
                "admin_user": admin_user,
                "offices": offices,
                "page": page,
                "pages": pages,
                "q": q,
                "total": total,
            },
        )

    @router.get("/offices/{office_id}", response_class=HTMLResponse)
    async def admin_office_edit(request: Request, office_id: int, db: Session = Depends(get_session)):
        admin_user = get_admin_user(request, db)
        if not admin_user or not admin_user.is_active:
            return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

        office = db.get(Office, office_id)
        if not office:
            return RedirectResponse(url="/admin/offices", status_code=status.HTTP_303_SEE_OTHER)

        return templates.TemplateResponse(
            "admin/office_edit.html",
            {
                "request": request,
                "admin_user": admin_user,
                "office": office,
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @router.post("/offices/{office_id}")
    async def admin_office_update(
        request: Request,
        office_id: int,
        name: str = Form(...),
        location: str = Form(""),
        description: str = Form(""),
        ownership: str = Form(""),
        year_built: str = Form(""),
        certificate: str = Form(""),
        gross_leasable_area: str = Form(""),
        floor_size: str = Form(""),
        efficiency: str = Form(""),
        delivery_type: str = Form(""),
        asking_rent: str = Form(""),
        service_charge: str = Form(""),
        car_park_ratio: str = Form(""),
        tenants: str = Form(""),
        alias_names: str = Form(""),
        image_url: str = Form(""),
        picture1_url: str = Form(""),
        picture2_url: str = Form(""),
        lat: str = Form(""),
        lng: str = Form(""),
        db: Session = Depends(get_session),
    ):
        admin_user = get_admin_user(request, db)
        if not admin_user or not admin_user.is_active:
            return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

        office = db.get(Office, office_id)
        if not office:
            return RedirectResponse(url="/admin/offices", status_code=status.HTTP_303_SEE_OTHER)

        office.name = name.strip()
        office.location = location.strip() or None
        office.description = description.strip() or None
        office.ownership = ownership.strip() or None
        office.year_built = year_built.strip() or None
        office.certificate = certificate.strip() or None
        office.gross_leasable_area = gross_leasable_area.strip() or None
        office.floor_size = floor_size.strip() or None
        office.efficiency = efficiency.strip() or None
        office.delivery_type = delivery_type.strip() or None
        office.asking_rent = asking_rent.strip() or None
        office.service_charge = service_charge.strip() or None
        office.car_park_ratio = car_park_ratio.strip() or None
        office.tenants = tenants.strip() or None
        office.alias_names = alias_names.strip() or None
        office.image_url = image_url.strip() or None
        office.picture1_url = picture1_url.strip() or None
        office.picture2_url = picture2_url.strip() or None
        office.lat = parse_optional_float(lat)
        office.lng = parse_optional_float(lng)

        db.add(office)
        db.commit()
        log_admin_action(db, admin_user, "office_update", "office", office.id)
        return RedirectResponse(url=f"/admin/offices/{office.id}?saved=1", status_code=status.HTTP_303_SEE_OTHER)
