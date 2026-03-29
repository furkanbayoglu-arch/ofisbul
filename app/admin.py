from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import AdminUser, AuditLog, ExtraField, Lead, Office, OfficeExtraValue
from app.security import hash_password, verify_password
from app.services import normalize


router = APIRouter(prefix="/admin", tags=["admin"])
LEAD_STATUS_OPTIONS = ["new", "contacted", "qualified", "proposal", "won", "lost", "archived"]
ROLE_OPTIONS = ["owner", "admin"]


def get_admin_user(request: Request, db: Session) -> AdminUser | None:
    admin_user_id = request.session.get("admin_user_id")
    if not admin_user_id:
        return None
    return db.get(AdminUser, admin_user_id)


def require_active(request: Request, db: Session) -> AdminUser | RedirectResponse:
    """Returns admin user if active, else a redirect to login."""
    admin_user = get_admin_user(request, db)
    if not admin_user or not admin_user.is_active:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    return admin_user


def require_owner(request: Request, db: Session) -> AdminUser | RedirectResponse:
    """Returns admin user if owner, else redirect to dashboard with 403."""
    result = require_active(request, db)
    if isinstance(result, RedirectResponse):
        return result
    if result.role != "owner":
        return RedirectResponse(url="/admin?error=yetkisiz", status_code=status.HTTP_303_SEE_OTHER)
    return result


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


def get_extra_field_sections(db: Session, office: Office) -> list[dict]:
    fields = db.scalars(select(ExtraField).order_by(ExtraField.section.asc(), ExtraField.sort_order.asc(), ExtraField.label.asc())).all()
    value_map = {item.field_id: item.value for item in office.extra_values}
    sections: dict[str, list[dict]] = {}
    for field in fields:
        sections.setdefault(field.section or "Diğer", []).append(
            {
                "id": field.id,
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "value": value_map.get(field.id, "") or "",
            }
        )
    return [{"name": name, "fields": items} for name, items in sections.items()]


def mount_admin_routes(templates: Jinja2Templates) -> None:

    # ── Auth ──────────────────────────────────────────────────────────────────

    @router.get("/login", response_class=HTMLResponse)
    async def admin_login_page(request: Request, db: Session = Depends(get_session)):
        admin_user = get_admin_user(request, db)
        if admin_user and admin_user.is_active:
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            request=request,
            name="admin/login.html",
            context={"error": None},
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
                request=request,
                name="admin/login.html",
                context={"error": "E-posta veya şifre hatalı."},
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

    # ── Dashboard ─────────────────────────────────────────────────────────────

    @router.get("", response_class=HTMLResponse)
    async def admin_dashboard(request: Request, db: Session = Depends(get_session)):
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        recent_leads = db.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(20)).all()
        office_count = db.scalar(select(func.count()).select_from(Office)) or 0
        lead_count = db.scalar(select(func.count()).select_from(Lead)) or 0
        error = request.query_params.get("error")

        # Logs only for owner
        recent_logs = []
        if admin_user.role == "owner":
            recent_logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)).all()

        return templates.TemplateResponse(
            request=request,
            name="admin/dashboard.html",
            context={
                "admin_user": admin_user,
                "recent_leads": recent_leads,
                "recent_logs": recent_logs,
                "office_count": office_count,
                "lead_count": lead_count,
                "error": error,
            },
        )

    # ── Leads ─────────────────────────────────────────────────────────────────

    @router.get("/leads", response_class=HTMLResponse)
    async def admin_leads(
        request: Request,
        q: str = "",
        status_filter: str = "",
        page: int = 1,
        db: Session = Depends(get_session),
    ):
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        stmt = select(Lead).options(joinedload(Lead.office), joinedload(Lead.assigned_admin_user))
        if q.strip():
            term = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                func.lower(Lead.full_name).like(term) |
                func.lower(Lead.email).like(term) |
                func.lower(func.coalesce(Lead.company, "")).like(term)
            )
        if status_filter.strip():
            stmt = stmt.where(Lead.status == status_filter.strip())

        per_page = 25
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        leads = db.execute(
            stmt.order_by(Lead.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        ).unique().scalars().all()
        pages = max(1, -(-total // per_page))
        admins = db.scalars(select(AdminUser).where(AdminUser.is_active.is_(True)).order_by(AdminUser.full_name.asc())).all()

        return templates.TemplateResponse(
            request=request,
            name="admin/leads.html",
            context={
                "admin_user": admin_user,
                "leads": leads,
                "admins": admins,
                "page": page,
                "pages": pages,
                "q": q,
                "status_filter": status_filter,
                "status_options": LEAD_STATUS_OPTIONS,
                "total": total,
            },
        )

    @router.get("/leads/{lead_id}", response_class=HTMLResponse)
    async def admin_lead_edit(request: Request, lead_id: int, db: Session = Depends(get_session)):
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        lead = db.execute(
            select(Lead)
            .options(joinedload(Lead.office), joinedload(Lead.assigned_admin_user))
            .where(Lead.id == lead_id)
        ).unique().scalar_one_or_none()
        if not lead:
            return RedirectResponse(url="/admin/leads", status_code=status.HTTP_303_SEE_OTHER)

        admins = db.scalars(select(AdminUser).where(AdminUser.is_active.is_(True)).order_by(AdminUser.full_name.asc())).all()
        return templates.TemplateResponse(
            request=request,
            name="admin/lead_edit.html",
            context={
                "admin_user": admin_user,
                "lead": lead,
                "admins": admins,
                "status_options": LEAD_STATUS_OPTIONS,
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @router.post("/leads/{lead_id}")
    async def admin_lead_update(
        request: Request,
        lead_id: int,
        status_value: str = Form(..., alias="status"),
        assigned_admin_user_id: str = Form(""),
        admin_notes: str = Form(""),
        last_contacted_at: str = Form(""),
        db: Session = Depends(get_session),
    ):
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        lead = db.get(Lead, lead_id)
        if not lead:
            return RedirectResponse(url="/admin/leads", status_code=status.HTTP_303_SEE_OTHER)

        lead.status = status_value if status_value in LEAD_STATUS_OPTIONS else lead.status
        lead.admin_notes = admin_notes.strip() or None
        lead.assigned_admin_user_id = int(assigned_admin_user_id) if assigned_admin_user_id.strip() else None
        lead.last_contacted_at = datetime.fromisoformat(last_contacted_at) if last_contacted_at.strip() else None
        lead.updated_at = datetime.now(timezone.utc)

        db.add(lead)
        db.commit()
        log_admin_action(db, admin_user, "lead_update", "lead", lead.id)
        return RedirectResponse(url=f"/admin/leads/{lead.id}?saved=1", status_code=status.HTTP_303_SEE_OTHER)

    # ── Offices ───────────────────────────────────────────────────────────────

    @router.get("/offices", response_class=HTMLResponse)
    async def admin_offices(
        request: Request,
        q: str = "",
        page: int = 1,
        db: Session = Depends(get_session),
    ):
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

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
            request=request,
            name="admin/offices.html",
            context={
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
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        office = db.execute(
            select(Office)
            .options(joinedload(Office.extra_values))
            .where(Office.id == office_id)
        ).unique().scalar_one_or_none()
        if not office:
            return RedirectResponse(url="/admin/offices", status_code=status.HTTP_303_SEE_OTHER)

        return templates.TemplateResponse(
            request=request,
            name="admin/office_edit.html",
            context={
                "admin_user": admin_user,
                "office": office,
                "extra_sections": get_extra_field_sections(db, office),
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
        result = require_active(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        office = db.execute(
            select(Office)
            .options(joinedload(Office.extra_values))
            .where(Office.id == office_id)
        ).unique().scalar_one_or_none()
        if not office:
            return RedirectResponse(url="/admin/offices", status_code=status.HTTP_303_SEE_OTHER)

        form_data = await request.form()

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

        existing_extra_map = {item.field_id: item for item in office.extra_values}
        extra_fields = db.scalars(select(ExtraField)).all()
        for field in extra_fields:
            raw_value = form_data.get(f"extra__{field.key}")
            if raw_value is None:
                continue
            cleaned_value = str(raw_value).strip()
            existing_value = existing_extra_map.get(field.id)
            if cleaned_value:
                if existing_value:
                    existing_value.value = cleaned_value
                else:
                    db.add(OfficeExtraValue(office_id=office.id, field_id=field.id, value=cleaned_value))
            elif existing_value:
                db.delete(existing_value)

        db.add(office)
        db.commit()
        log_admin_action(db, admin_user, "office_update", "office", office.id)
        return RedirectResponse(url=f"/admin/offices/{office.id}?saved=1", status_code=status.HTTP_303_SEE_OTHER)

    # ── User Management (owner only) ──────────────────────────────────────────

    @router.get("/users", response_class=HTMLResponse)
    async def admin_users(request: Request, db: Session = Depends(get_session)):
        result = require_owner(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        users = db.scalars(select(AdminUser).order_by(AdminUser.created_at.asc())).all()
        return templates.TemplateResponse(
            request=request,
            name="admin/users.html",
            context={
                "admin_user": admin_user,
                "users": users,
                "role_options": ROLE_OPTIONS,
                "saved": request.query_params.get("saved") == "1",
                "error": request.query_params.get("error"),
            },
        )

    @router.post("/users/create")
    async def admin_user_create(
        request: Request,
        full_name: str = Form(...),
        email: str = Form(...),
        password: str = Form(...),
        role: str = Form("admin"),
        db: Session = Depends(get_session),
    ):
        result = require_owner(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        if role not in ROLE_OPTIONS:
            role = "admin"
        existing = db.scalar(select(AdminUser).where(AdminUser.email == email.strip().lower()))
        if existing:
            return RedirectResponse(url="/admin/users?error=bu+email+zaten+kayıtlı", status_code=status.HTTP_303_SEE_OTHER)

        new_user = AdminUser(
            email=email.strip().lower(),
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(new_user)
        db.commit()
        log_admin_action(db, admin_user, "user_create", "admin_user", new_user.id)
        return RedirectResponse(url="/admin/users?saved=1", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/users/{user_id}/update")
    async def admin_user_update(
        request: Request,
        user_id: int,
        full_name: str = Form(...),
        role: str = Form("admin"),
        is_active: str = Form("off"),
        new_password: str = Form(""),
        db: Session = Depends(get_session),
    ):
        result = require_owner(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        target = db.get(AdminUser, user_id)
        if not target:
            return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

        # Prevent owner from demoting themselves
        if target.id == admin_user.id and role != "owner":
            return RedirectResponse(url="/admin/users?error=kendinizi+demote+edemezsiniz", status_code=status.HTTP_303_SEE_OTHER)

        target.full_name = full_name.strip()
        target.role = role if role in ROLE_OPTIONS else target.role
        target.is_active = is_active == "on"
        if new_password.strip():
            target.password_hash = hash_password(new_password.strip())

        db.add(target)
        db.commit()
        log_admin_action(db, admin_user, "user_update", "admin_user", target.id)
        return RedirectResponse(url="/admin/users?saved=1", status_code=status.HTTP_303_SEE_OTHER)

    # ── Audit Logs (owner only) ────────────────────────────────────────────────

    @router.get("/logs", response_class=HTMLResponse)
    async def admin_logs(
        request: Request,
        page: int = 1,
        db: Session = Depends(get_session),
    ):
        result = require_owner(request, db)
        if isinstance(result, RedirectResponse):
            return result
        admin_user = result

        per_page = 50
        total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
        logs = db.scalars(
            select(AuditLog)
            .options(joinedload(AuditLog.admin_user))
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        pages = max(1, -(-total // per_page))

        return templates.TemplateResponse(
            request=request,
            name="admin/logs.html",
            context={
                "admin_user": admin_user,
                "logs": logs,
                "page": page,
                "pages": pages,
                "total": total,
            },
        )

    # ── API Docs (owner only) ──────────────────────────────────────────────────

    @router.get("/openapi.json")
    async def admin_openapi(request: Request, db: Session = Depends(get_session)):
        from fastapi.openapi.utils import get_openapi
        result = require_owner(request, db)
        if isinstance(result, RedirectResponse):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        from app.main import app as main_app
        return get_openapi(title=main_app.title, version=main_app.version, routes=main_app.routes)

    @router.get("/api-docs", response_class=HTMLResponse)
    async def admin_api_docs(request: Request, db: Session = Depends(get_session)):
        from fastapi.openapi.docs import get_swagger_ui_html
        result = require_owner(request, db)
        if isinstance(result, RedirectResponse):
            return result
        return get_swagger_ui_html(openapi_url="/admin/openapi.json", title="API Docs")
