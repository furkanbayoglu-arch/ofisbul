from sqlalchemy import String, cast, func, literal, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Office, OfficeExtraValue


TR_MAP = str.maketrans({
    "ç": "c",
    "Ç": "c",
    "ğ": "g",
    "Ğ": "g",
    "ı": "i",
    "I": "i",
    "İ": "i",
    "ö": "o",
    "Ö": "o",
    "ş": "s",
    "Ş": "s",
    "ü": "u",
    "Ü": "u",
})
TR_TRANSLATE_FROM = "çÇğĞıIİöÖşŞüÜ"
TR_TRANSLATE_TO = "ccggiiioossuu"


def normalize(text: str) -> str:
    return text.lower().translate(TR_MAP)


def office_to_dict(office: Office) -> dict:
    return {
        "id": office.id,
        "name": office.name,
        "location": office.location,
        "description": office.description,
        "ownership": office.ownership,
        "year_built": office.year_built,
        "certificate": office.certificate,
        "gross_leasable_area": office.gross_leasable_area,
        "floor_size": office.floor_size,
        "efficiency": office.efficiency,
        "delivery_type": office.delivery_type,
        "asking_rent": office.asking_rent,
        "service_charge": office.service_charge,
        "car_park_ratio": office.car_park_ratio,
        "tenants": office.tenants,
        "image_url": office.image_url,
        "picture1_url": office.picture1_url,
        "picture2_url": office.picture2_url,
        "alias_names": office.alias_names,
        "lat": office.lat,
        "lng": office.lng,
        "created_at": office.created_at,
    }


def normalized_column(column):
    return func.lower(
        func.translate(
            func.coalesce(cast(column, String), literal("")),
            TR_TRANSLATE_FROM,
            TR_TRANSLATE_TO,
        )
    )


def search_offices(
    db: Session,
    search: str = "",
    location: str = "",
    page: int = 1,
    per_page: int = 24,
):
    stmt = select(Office)

    if location and location != "all":
        stmt = stmt.where(Office.location.ilike(f"%{location}%"))

    if search:
        normalized_term = f"%{normalize(search)}%"
        stmt = stmt.where(
            or_(
                normalized_column(Office.name).like(normalized_term),
                normalized_column(Office.location).like(normalized_term),
                normalized_column(Office.description).like(normalized_term),
                normalized_column(Office.alias_names).like(normalized_term),
                normalized_column(Office.tenants).like(normalized_term),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offices = db.scalars(
        stmt.order_by(Office.name.asc()).offset((page - 1) * per_page).limit(per_page)
    ).all()
    return total, [office_to_dict(office) for office in offices]


def get_locations(db: Session):
    stmt = (
        select(Office.location)
        .where(Office.location.is_not(None))
        .distinct()
        .order_by(Office.location.asc())
    )
    return [location for location in db.scalars(stmt).all() if location]


def get_office_by_id(db: Session, office_id: int):
    stmt = (
        select(Office)
        .options(joinedload(Office.extra_values).joinedload(OfficeExtraValue.field))
        .where(Office.id == office_id)
    )
    office = db.scalars(stmt).unique().first()
    if not office:
        return None, {}

    extra_sections = {}
    sorted_values = sorted(
        office.extra_values,
        key=lambda item: ((item.field.section or "Diğer"), item.field.sort_order, item.field.label),
    )
    for extra in sorted_values:
        section_name = extra.field.section or "Diğer"
        extra_sections.setdefault(section_name, []).append(
            {"label": extra.field.label, "value": extra.value, "key": extra.field.key}
        )

    return office_to_dict(office), extra_sections
