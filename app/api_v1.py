"""
OfisArama API v1
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Office, OfficeExtraValue
from app.services import get_locations, get_office_by_id, search_offices, normalize


router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/offices")
def list_offices(
    search: str = Query("", description="Arama: isim, lokasyon, kiracı"),
    location: str = Query("", description="İlçe filtresi"),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_session),
):
    total, offices = search_offices(db, search, location, page, per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),
        "items": offices,
    }


@router.get("/offices/{office_id}")
def get_office(office_id: int, db: Session = Depends(get_session)):
    office, extras = get_office_by_id(db, office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")
    return {"office": office, "extras": extras}


@router.get("/offices/map/pins")
def map_pins(
    location: str = Query(""),
    search: str = Query(""),
    db: Session = Depends(get_session),
):
    """Harita için hafif endpoint — sadece id, name, location, asking_rent, image_url, lat, lng."""
    stmt = select(
        Office.id, Office.name, Office.location,
        Office.asking_rent, Office.image_url, Office.lat, Office.lng
    ).where(Office.lat.is_not(None), Office.lng.is_not(None))

    if location and location != "all":
        stmt = stmt.where(Office.location.ilike(f"%{location}%"))

    if search:
        from sqlalchemy import or_
        from app.services import normalized_column
        term = f"%{normalize(search)}%"
        stmt = stmt.where(or_(
            normalized_column(Office.name).like(term),
            normalized_column(Office.location).like(term),
            normalized_column(Office.tenants).like(term),
        ))

    rows = db.execute(stmt.order_by(Office.name)).all()
    return {"pins": [
        {"id": r.id, "name": r.name, "location": r.location,
         "asking_rent": r.asking_rent, "image_url": r.image_url,
         "lat": r.lat, "lng": r.lng}
        for r in rows
    ]}


@router.get("/locations")
def list_locations(db: Session = Depends(get_session)):
    return get_locations(db)


@router.get("/stats")
def stats(db: Session = Depends(get_session)):
    total = db.scalar(select(func.count()).select_from(Office)) or 0
    locations = db.scalar(select(func.count(func.distinct(Office.location)))) or 0
    enriched_count = db.scalar(
        select(func.count(func.distinct(Office.id)))
        .select_from(Office)
        .join(OfficeExtraValue, OfficeExtraValue.office_id == Office.id, isouter=True)
        .where(OfficeExtraValue.field_id.is_not(None))
    ) or 0
    return {
        "total_offices": total,
        "total_locations": locations,
        "offices_with_extra_data": enriched_count,
    }
