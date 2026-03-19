"""
OfisBul API v1
"""
from fastapi import APIRouter, Query, HTTPException
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "offices_clone.db")

router = APIRouter(prefix="/api/v1", tags=["v1"])

TR_MAP = str.maketrans({
    'ç': 'c', 'Ç': 'c', 'ğ': 'g', 'Ğ': 'g',
    'ı': 'i', 'I': 'i', 'İ': 'i', 'ö': 'o',
    'Ö': 'o', 'ş': 's', 'Ş': 's', 'ü': 'u', 'Ü': 'u',
})

def normalize(text: str) -> str:
    return text.lower().translate(TR_MAP)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Offices list ─────────────────────────────────────────────────────────────

@router.get("/offices")
def list_offices(
    search: str = Query("", description="Arama: isim, lokasyon, kiracı"),
    location: str = Query("", description="İlçe filtresi"),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
):
    conn = get_db()
    try:
        params, conditions = [], []

        if location and location != "all":
            conditions.append("UPPER(location) LIKE ?")
            params.append(f"%{location.upper()}%")

        if search:
            norm = normalize(search)
            conditions.append("""(
                LOWER(name) LIKE ? OR LOWER(location) LIKE ? OR
                LOWER(description) LIKE ? OR
                LOWER(IFNULL(alias_names,'')) LIKE ? OR
                LOWER(IFNULL(tenants,'')) LIKE ?
            )""")
            like = f"%{norm}%"
            params.extend([like, like, like, like, like])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM offices {where}", params).fetchone()[0]
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT id, name, location, description, asking_rent, service_charge,
                gross_leasable_area, floor_size, image_url, picture1_url,
                delivery_type, lat, lng
                FROM offices {where} ORDER BY name ASC LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, -(-total // per_page)),
            "items": [dict(r) for r in rows],
        }
    finally:
        conn.close()


# ── Office detail ─────────────────────────────────────────────────────────────

@router.get("/offices/{office_id}")
def get_office(office_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM offices WHERE id = ?", (office_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ofis bulunamadı")
        office = dict(row)

        extras = conn.execute("""
            SELECT ef.label, ef.key, ef.section, oev.value
            FROM office_extra_values oev
            JOIN extra_fields ef ON ef.id = oev.field_id
            WHERE oev.office_id = ?
            ORDER BY ef.section, ef.sort_order
        """, (office_id,)).fetchall()

        sections: dict = {}
        for e in extras:
            sec = e["section"] or "Diğer"
            sections.setdefault(sec, []).append({"label": e["label"], "key": e["key"], "value": e["value"]})

        return {"office": office, "extras": sections}
    finally:
        conn.close()


# ── Map pins (lightweight) ────────────────────────────────────────────────────

@router.get("/offices/map/pins")
def map_pins(
    location: str = Query("", description="İlçe filtresi"),
    search: str = Query(""),
):
    """Harita için sadece id, name, lat, lng, asking_rent döner — hızlı yükleme için."""
    conn = get_db()
    try:
        params, conditions = [], []
        conditions.append("lat IS NOT NULL AND lng IS NOT NULL")

        if location and location != "all":
            conditions.append("UPPER(location) LIKE ?")
            params.append(f"%{location.upper()}%")

        if search:
            norm = normalize(search)
            conditions.append("""(
                LOWER(name) LIKE ? OR LOWER(location) LIKE ? OR
                LOWER(IFNULL(tenants,'')) LIKE ?
            )""")
            like = f"%{norm}%"
            params.extend([like, like, like])

        where = "WHERE " + " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT id, name, location, asking_rent, image_url, lat, lng FROM offices {where} ORDER BY name",
            params
        ).fetchall()
        return {"pins": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── Locations ─────────────────────────────────────────────────────────────────

@router.get("/locations")
def list_locations():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT location FROM offices WHERE location IS NOT NULL ORDER BY location"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def stats():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM offices").fetchone()[0]
        locations = conn.execute("SELECT COUNT(DISTINCT location) FROM offices").fetchone()[0]
        with_coords = conn.execute("SELECT COUNT(*) FROM offices WHERE lat IS NOT NULL").fetchone()[0]
        return {
            "total_offices": total,
            "total_locations": locations,
            "offices_with_coords": with_coords,
        }
    finally:
        conn.close()
